package telemetry

// A MEASUREMENT, not an assertion (item 1.5, plan step 7; interfaces.md §H v0.11, ADR-005). Skipped
// unless MEASURE_DRAIN=1.
//
// Question: does storing answers make the writer goroutine slow enough to push Dropped() above 0?
// A tight Log loop would not answer it: it enqueues in ~100 ns while the writer already pays one
// write(2) per record, so a drop count from such a loop is produced by the producer, not the
// gateway. So this times the writer's DRAIN instead: n records are enqueued (n is below the buffer,
// so nothing is dropped) and Close, which drains, is timed.
//
// Three kinds of record, each a fresh logger, medians of several repetitions:
//
//	no answer      the pre-1.5 cost: one JSONL line
//	already seen   a hash whose file exists: a map lookup, then the line (the control)
//	first seen     a new hash: create, write, chmod, close, link, remove, then the line
//
// The sustainable first-sighting rate is 1 / (first seen). It is the rate at which the writer keeps
// up if EVERY request were a first sighting, which is the worst case the real workload cannot exceed:
// distinct answers are bounded by MISSes plus first sightings of pre-warmed entries (<= 0.25 K).

import (
	"fmt"
	"os"
	"sort"
	"strings"
	"testing"
	"time"
)

func TestMeasureWriterDrain(t *testing.T) {
	if os.Getenv("MEASURE_DRAIN") != "1" {
		t.Skip("a measurement, not an assertion: set MEASURE_DRAIN=1")
	}
	const n = 3000 // below bufferSize (4096): no drops, so the timing is the drain
	const reps = 9
	fixed := "an answer that is reused for the already-seen control: " + strings.Repeat("x", 160)

	mk := func(i int) Record {
		return Record{
			RequestID: fmt.Sprintf("r%06d", i), Cache: "MISS",
			QueryRaw:          "How long is the warranty period on the XPS 13?",
			QueryNormalized:   "how long is the warranty period on the xps 13",
			T1Key:             "t1:9f2c0000000000000000000000000000000000000000000000000000deadbeef",
			RetrievedChunkIDs: []string{"policy-warranty-electronics#chunk-1", "product-xps13#chunk-0", "product-xps13#chunk-2"},
			EntrySources:      []string{"policy-warranty-electronics#chunk-1"},
			EntryID:           "01JABCDEFGHJKMNPQRSTVWXYZ0",
		}
	}
	kinds := []struct {
		name  string
		build func(i int) Record
	}{
		{"no answer (pre-1.5: the line only)", func(i int) Record { return mk(i) }},
		{"already seen (map lookup + line)", func(i int) Record { r := mk(i); r.SetAnswer(fixed); return r }},
		{"first seen (file + line)", func(i int) Record {
			r := mk(i)
			r.SetAnswer(fmt.Sprintf("Answer %d: %s", i, strings.Repeat("y", 200)))
			return r
		}},
	}

	medians := make([]time.Duration, len(kinds))
	for k, kind := range kinds {
		var per []time.Duration
		for rep := 0; rep < reps; rep++ {
			l, err := Open(t.TempDir(), "m")
			if err != nil {
				t.Fatal(err)
			}
			recs := make([]Record, n) // built outside the timed region
			for i := range recs {
				recs[i] = kind.build(i)
			}
			start := time.Now()
			for _, r := range recs {
				l.Log(r)
			}
			if err := l.Close(); err != nil {
				t.Fatal(err)
			}
			elapsed := time.Since(start)
			if d := l.Dropped(); d != 0 {
				t.Fatalf("%s: Dropped() = %d with n=%d: the timing is not the drain", kind.name, d, n)
			}
			per = append(per, elapsed/time.Duration(n))
		}
		sort.Slice(per, func(a, b int) bool { return per[a] < per[b] })
		medians[k] = per[len(per)/2]
		fmt.Printf("MEASURE %-40s median %8.1f us/record   (min %.1f, max %.1f, n=%d x %d)\n",
			kind.name, float64(medians[k])/1e3, float64(per[0])/1e3, float64(per[len(per)-1])/1e3, n, reps)
	}
	fmt.Printf("MEASURE added by a first sighting:   %8.1f us   (first seen - no answer)\n", float64(medians[2]-medians[0])/1e3)
	fmt.Printf("MEASURE added by an already-seen:    %8.1f us   (already seen - no answer)\n", float64(medians[1]-medians[0])/1e3)
	fmt.Printf("MEASURE sustainable first-sighting rate: %.0f records/s   (1 / first seen)\n", 1e9/float64(medians[2]))
	fmt.Printf("MEASURE sustainable already-seen rate:   %.0f records/s\n", 1e9/float64(medians[1]))
	fmt.Printf("MEASURE sustainable pre-1.5 line rate:   %.0f records/s\n", 1e9/float64(medians[0]))
}
