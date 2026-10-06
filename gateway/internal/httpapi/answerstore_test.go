package httpapi

// The exit test of item 1.5 (ADR-005): every answer Ask serves is recoverable from raw/ alone.
//
// Why three distinct texts matter. The 1.2 fakes serve ONE text per product everywhere: the fake
// Answer returns p.answer and hitFixture seeds p.answer. With that, a writer that stored text only
// on a MISS, or a call site left on the old assignment, is hidden: another path serving the same
// text creates the file anyway. So here each serving path serves a text that no other path serves,
// and the test checks that precondition itself rather than trusting the fixture.
//
//	TIER1_HIT  an entry seeded with kettle.otherAnswer
//	TIER2_HIT  an entry seeded with headphones.otherAnswer, in the headphones namespace
//	MISS       the fake Answer: kettle.answer (leader) and headphones.answer (a coalesced pair)
//
// The harness is not edited: everything here is built from what it already offers.

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/cache"
)

var answerFileName = regexp.MustCompile(`^[0-9a-f]{64}\.txt$`)

func TestEveryServedAnswerIsRecoverableFromRawAlone(t *testing.T) {
	hs := newHarness(t, 1, 0)

	// TIER1_HIT: an entry with its own text.
	const qTier1 = "What is the Aurora kettle made of, exactly?"
	hs.store.seedTier1(qTier1, kettle.id, cache.Entry{
		Answer:         kettle.otherAnswer,
		SourceChunkIDs: kettle.answerSources(),
		ModelUsed:      testModel,
		EntryID:        cache.NewEntryID(),
	})

	// TIER2_HIT: the fixture for a headphones question, carrying a third text. It obeys the fixture
	// rule (a verbatim substring of chunk 0, no numerals), as otherAnswer always does.
	tier2 := hitFixture(headphones, "Which tips come with the EarBuds Pop?")
	tier2.Answer = headphones.otherAnswer
	hs.store.seedTier2(tier2, float32s(basis(1)))
	const qTier2 = "What ear tips ship with the EarBuds?"
	hs.embedder.learn(qTier2, toward(1, 2, hitCos))

	hs.ask(t, askReq{question: qTier1, productID: kettle.id})
	hs.ask(t, askReq{question: qTier2, productID: headphones.id})

	// MISS, then a coalesced pair on another question: one generation, two records, one text.
	const qMiss = "Is the Aurora kettle cordless?"
	hs.embedFresh(qMiss)
	hs.ask(t, askReq{question: qMiss, productID: kettle.id})

	const qCoalesced = "Do the EarBuds Pop come with a case?"
	hs.embedFresh(qCoalesced)
	g := hs.holdAnswers()
	key := cache.Key(cache.Normalize(qCoalesced), headphones.id)
	leader := hs.start(askReq{question: qCoalesced, productID: headphones.id})
	follower := hs.start(askReq{question: qCoalesced, productID: headphones.id})
	waitFor(t, "the follower to wait on the leader", func() bool { return hs.h.Generations.Waiters(key) == 1 })
	g.open()
	leader.wait(t)
	follower.wait(t)

	// A request that serves no text: the answer fails. It must leave a record and NO file.
	const qFail = "How long is the Aurora kettle warranty?"
	hs.embedFresh(qFail)
	hs.rag.onAnswer(func(context.Context) error { return status.Error(codes.Internal, "the model crashed") })
	hs.ask(t, askReq{question: qFail, productID: kettle.id})

	hs.records(t) // joins every call, closes the Logger, and decodes the log into each call's rec

	raw := filepath.Dir(hs.logPath)
	answers := filepath.Join(raw, "answers")

	// Everything below reads only raw/ and the responses. The store is never consulted.
	named := map[string]bool{}               // every non-empty answer_sha256 in the log
	servedBy := map[string]map[string]bool{} // served text -> the cache labels that served it
	sawFailure := false
	hs.mu.Lock()
	calls := append([]*call(nil), hs.calls...)
	hs.mu.Unlock()
	for _, c := range calls {
		label, _ := c.rec["cache"].(string)
		sha, _ := c.rec["answer_sha256"].(string)

		if label == "GENERATION_FAILED" {
			sawFailure = true
			if sha != "" {
				t.Errorf("a GENERATION_FAILED record carries answer_sha256 %q; no text was served", sha)
			}
			continue
		}
		if sha == "" {
			t.Errorf("a %s record has an empty answer_sha256", label)
			continue
		}
		named[sha] = true

		// For every response that really carried an answer (an F-D follower's recorder is untouched
		// yet reports 200), the file is that answer, byte for byte, and hashes to its own name.
		if c.w.touched && c.w.Code == 200 {
			answer, _ := c.resp["answer"].(string)
			got, err := os.ReadFile(filepath.Join(answers, sha+".txt"))
			if err != nil {
				t.Errorf("%s record names %s but %v", label, sha, err)
				continue
			}
			if string(got) != answer {
				t.Errorf("%s: the file holds %q, the client received %q", label, got, answer)
			}
			sum := sha256.Sum256([]byte(answer))
			if hex.EncodeToString(sum[:]) != sha {
				t.Errorf("%s: the record's answer_sha256 %s is not the hash of the served answer", label, sha)
			}
			if servedBy[answer] == nil {
				servedBy[answer] = map[string]bool{}
			}
			servedBy[answer][label] = true
		}
	}
	if !sawFailure {
		t.Fatal("the failing request never produced a GENERATION_FAILED record: the test did not reach that path")
	}

	// The precondition that gives this test its power: no text is served by two paths.
	want := map[string]string{
		kettle.otherAnswer:     "TIER1_HIT",
		headphones.otherAnswer: "TIER2_HIT",
		kettle.answer:          "MISS",
		headphones.answer:      "MISS",
	}
	if len(servedBy) != len(want) {
		t.Fatalf("served %d distinct texts, want %d: %v", len(servedBy), len(want), servedBy)
	}
	for text, label := range want {
		labels := servedBy[text]
		if len(labels) != 1 || !labels[label] {
			t.Errorf("text %q was served by %v, want only %s: a path that shares a text hides a missing write", text, labels, label)
		}
	}

	// The invariant, in both directions: every named hash has a file, and every file is named.
	var onDisk []string
	ents, err := os.ReadDir(answers)
	if err != nil {
		t.Fatalf("raw/answers/ is unreadable: %v", err)
	}
	for _, e := range ents {
		if !answerFileName.MatchString(e.Name()) {
			t.Errorf("answers/ holds %q, which is not {sha}.txt (temp residue after a clean Close?)", e.Name())
			continue
		}
		onDisk = append(onDisk, e.Name()[:64])
	}
	var namedList []string
	for sha := range named {
		namedList = append(namedList, sha)
	}
	sort.Strings(onDisk)
	sort.Strings(namedList)
	if len(onDisk) != len(namedList) {
		t.Fatalf("answers/ holds %d files, the log names %d distinct hashes\n  files: %v\n  named: %v", len(onDisk), len(namedList), onDisk, namedList)
	}
	for i := range onDisk {
		if onDisk[i] != namedList[i] {
			t.Fatalf("answers/ and the log disagree at %d: file %s, named %s", i, onDisk[i], namedList[i])
		}
	}

	// A guard refusal means a call site set a hash without the text; it never clears, and it voids
	// the run. Mutation M3 (one site left on the old assignment) fails here whatever the order.
	if n := hs.h.Eval.GuardRefusals(); n != 0 {
		t.Errorf("GuardRefusals() = %d, want 0: a serving path set answer_sha256 without the text", n)
	}
	if n := hs.h.Eval.AnswersMissing(); n != 0 {
		t.Errorf("AnswersMissing() = %d, want 0", n)
	}
	if n := hs.h.Eval.WriteErrors(); n != 0 {
		t.Errorf("WriteErrors() = %d, want 0", n)
	}
	if n := hs.h.Eval.Dropped(); n != 0 {
		t.Errorf("Dropped() = %d, want 0", n)
	}
}

// Rule 3 of interfaces.md v0.11 names this path: a MISS whose generation COMPLETED though the client
// left (err == nil and ctx.Err() != nil at the outcome switch, abandon_test.go T5). It shares the MISS
// call site with the exit test above, so reverting or guarding that site on the context would pass
// the exit test; this one drives the path itself.
func TestAMissWhoseClientLeftStillStoresItsAnswer(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	hs.h.Cache = &leavingStore{fakeStore: hs.store, afterPut: q, leave: cancel}

	c := hs.ask(t, askReq{question: q, productID: kettle.id, ctx: ctx})
	hs.records(t)

	c.record(t).str("cache", "MISS") // not ABANDONED: the generation finished
	sha, _ := c.rec["answer_sha256"].(string)
	if sha == "" {
		t.Fatal("a completed generation whose client left carries no answer_sha256")
	}
	got, err := os.ReadFile(filepath.Join(filepath.Dir(hs.logPath), "answers", sha+".txt"))
	if err != nil {
		t.Fatalf("the record names %s but %v", sha, err)
	}
	if string(got) != kettle.answer {
		t.Fatalf("the file holds %q, want the generated %q", got, kettle.answer)
	}
	if n := hs.h.Eval.GuardRefusals() + int64(hs.h.Eval.AnswersMissing()); n != 0 {
		t.Fatalf("guard refusals + missing = %d, want 0", n)
	}
}
