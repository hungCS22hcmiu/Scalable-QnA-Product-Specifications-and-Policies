package telemetry

// Tests for the answer store (item 1.5, ADR-005): the text behind every non-empty answer_sha256
// is written to raw/answers/{sha}.txt, before the line that names it.
//
// Two rules these tests keep:
//   - The oracle hash is crypto/sha256 called directly (shaOf), never this package's helper. The
//     guard and SetAnswer share that helper, so a mutation that changed it would agree with itself.
//   - The seams (linkFile, removeFile) are set after Open and before the first Log. The writer
//     goroutine reads them only after receiving a record, so the channel send orders the write.

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

const emptySHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

func shaOf(text string) string {
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])
}

// recordWith builds a record the way the handler does: through SetAnswer.
func recordWith(id, text string) Record {
	r := Record{RequestID: id, Cache: "MISS"}
	r.SetAnswer(text)
	return r
}

// openRun opens a fresh run and returns the logger and its raw/ directory.
func openRun(t *testing.T) (*Logger, string) {
	t.Helper()
	dir := t.TempDir()
	l, err := Open(dir, "run-answers")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { _ = l.Close() })
	return l, filepath.Join(dir, "run-answers", "raw")
}

// names lists a directory's entries, sorted; a missing directory is an empty list.
func names(t *testing.T, dir string) []string {
	t.Helper()
	ents, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		t.Fatalf("ReadDir %s: %v", dir, err)
	}
	var out []string
	for _, e := range ents {
		out = append(out, e.Name())
	}
	sort.Strings(out)
	return out
}

func readFile(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(b)
}

// waitFor polls a condition with a deadline. The writer goroutine is asynchronous, so a state that
// only exists mid-run (a hash missing before its retry) can only be observed by waiting for it.
func waitFor(t *testing.T, what string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for !cond() {
		if time.Now().After(deadline) {
			t.Fatalf("timed out waiting for %s", what)
		}
		time.Sleep(time.Millisecond)
	}
}

func TestSetAnswerSetsTheHashAndTheTextFromOneValue(t *testing.T) {
	for _, text := range []string{"an answer", ""} {
		var r Record
		r.SetAnswer(text)
		if r.AnswerSHA256 != shaOf(text) {
			t.Errorf("SetAnswer(%q): AnswerSHA256 = %q, want %q", text, r.AnswerSHA256, shaOf(text))
		}
		if r.answerText != text {
			t.Errorf("SetAnswer(%q): answerText = %q", text, r.answerText)
		}
	}
	// "" in the hash means NO answer was served; an empty answer is a real one and hashes to the
	// empty string's digest. Conflating them would make a served empty answer look like a shed.
	var r Record
	r.SetAnswer("")
	if r.AnswerSHA256 != emptySHA {
		t.Fatalf("SetAnswer(\"\"): AnswerSHA256 = %q, want the empty string's SHA-256", r.AnswerSHA256)
	}
}

// Acceptance 7: byte-exact.
func TestAnswerTextRoundTripsByteExact(t *testing.T) {
	texts := []string{
		"a plain answer",
		"windows line\r\nending",
		"a trailing newline\n",
		"no trailing newline",
		"héllo — 日本語 🙂",
		"  surrounding space  \n\n",
		"",
	}
	l, raw := openRun(t)
	for i, text := range texts {
		l.Log(recordWith(string(rune('a'+i)), text))
	}
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	for _, text := range texts {
		want := shaOf(text)
		got := readFile(t, filepath.Join(raw, "answers", want+".txt"))
		if got != text {
			t.Errorf("answer %q: file holds %q", text, got)
		}
	}
	if n := l.AnswersMissing(); n != 0 {
		t.Errorf("AnswersMissing() = %d after a clean run", n)
	}
	if n := len(names(t, filepath.Join(raw, "answers"))); n != len(texts) {
		t.Errorf("answers/ holds %d files, want %d (one per distinct text)", n, len(texts))
	}
}

func TestAnEmptyAnswerIsAFileNamedForTheEmptyHash(t *testing.T) {
	l, raw := openRun(t)
	l.Log(recordWith("empty", ""))
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	b, err := os.ReadFile(filepath.Join(raw, "answers", emptySHA+".txt"))
	if err != nil {
		t.Fatalf("the empty answer has no file: %v", err)
	}
	if len(b) != 0 {
		t.Fatalf("the empty answer's file holds %d bytes", len(b))
	}
}

// Acceptance 3: no text, no file. A record that served no answer carries "" and creates nothing.
func TestARecordWithNoAnswerCreatesNoFile(t *testing.T) {
	l, raw := openRun(t)
	l.Log(Record{RequestID: "shed", Cache: "SHED"}) // AnswerSHA256 is ""
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	if got := names(t, filepath.Join(raw, "answers")); len(got) != 0 {
		t.Fatalf("a record with no answer created %v", got)
	}
	if n := l.AnswersMissing(); n != 0 {
		t.Fatalf("AnswersMissing() = %d for a record that named no hash", n)
	}
}

// Acceptance 4: ten requests served the same text produce one file, written once. Counted at the
// seam, not inferred from the directory, because a second write of identical bytes is invisible
// there.
func TestIdenticalAnswersAreWrittenOnce(t *testing.T) {
	l, raw := openRun(t)
	var links atomic.Int64
	l.linkFile = func(old, new string) error {
		links.Add(1)
		return os.Link(old, new)
	}
	for i := range 10 {
		l.Log(recordWith(string(rune('a'+i)), "the same answer"))
	}
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	if n := links.Load(); n != 1 {
		t.Fatalf("the file was linked %d times, want 1", n)
	}
	if got := names(t, filepath.Join(raw, "answers")); len(got) != 1 {
		t.Fatalf("answers/ holds %v, want one file", got)
	}
	if lines := strings.Count(readFile(t, filepath.Join(raw, "requests.jsonl")), "\n"); lines != 10 {
		t.Fatalf("requests.jsonl has %d lines, want 10: dedupe is for files, never for records", lines)
	}
}

// Acceptance 5: for each record its file is visible before its line is.
func TestTheFileIsVisibleBeforeTheLineThatNamesIt(t *testing.T) {
	l, raw := openRun(t)
	idOf := map[string]string{} // sha -> request id
	const n = 6
	for i := range n {
		text := "answer number " + string(rune('0'+i))
		idOf[shaOf(text)] = "r" + string(rune('0'+i))
	}
	var calls atomic.Int64
	var violations []string
	var vmu sync.Mutex
	l.linkFile = func(old, new string) error {
		err := os.Link(old, new)
		calls.Add(1)
		sha := strings.TrimSuffix(filepath.Base(new), ".txt")
		if _, statErr := os.Stat(new); statErr != nil {
			vmu.Lock()
			violations = append(violations, "file not visible after link: "+sha)
			vmu.Unlock()
		}
		line := `"request_id":"` + idOf[sha] + `"`
		if strings.Contains(readFile(t, filepath.Join(raw, "requests.jsonl")), line) {
			vmu.Lock()
			violations = append(violations, "the line for "+idOf[sha]+" was written before its file")
			vmu.Unlock()
		}
		return err
	}
	for i := range n {
		l.Log(recordWith("r"+string(rune('0'+i)), "answer number "+string(rune('0'+i))))
	}
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	// Vacuity check: a store that never ran would pass the loop above with zero calls.
	if got := calls.Load(); got != n {
		t.Fatalf("the link step ran %d times, want %d: the order check observed nothing", got, n)
	}
	vmu.Lock()
	defer vmu.Unlock()
	if len(violations) > 0 {
		t.Fatalf("order violated: %v", violations)
	}
}

// Acceptance 6: a failed write is loud, never silent; the request is still logged; a later record
// with the same hash retries, and a retry that succeeds clears it.
func TestAFailedLinkIsCountedAndALaterRecordRetries(t *testing.T) {
	l, raw := openRun(t)
	var failing atomic.Bool
	failing.Store(true)
	l.linkFile = func(old, new string) error {
		if failing.Load() {
			return errors.New("no space left on device")
		}
		return os.Link(old, new)
	}
	l.Log(recordWith("first", "the answer"))
	waitFor(t, "the hash to be counted missing", func() bool { return l.AnswersMissing() == 1 })

	// Not a file, and not a temp residue: nothing in answers/ at all.
	if got := names(t, filepath.Join(raw, "answers")); len(got) != 0 {
		t.Fatalf("a failed link left %v in answers/", got)
	}
	failing.Store(false)
	l.Log(recordWith("second", "the answer"))
	waitFor(t, "the retry to clear the hash", func() bool { return l.AnswersMissing() == 0 })

	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	if got := readFile(t, filepath.Join(raw, "answers", shaOf("the answer")+".txt")); got != "the answer" {
		t.Fatalf("the retried file holds %q", got)
	}
	jsonl := readFile(t, filepath.Join(raw, "requests.jsonl"))
	for _, id := range []string{"first", "second"} {
		if !strings.Contains(jsonl, `"request_id":"`+id+`"`) {
			t.Errorf("the record %q was not written: a failed answer must not lose its line", id)
		}
	}
	if l.GuardRefusals() != 0 || l.WriteErrors() != 0 {
		t.Errorf("a failed link is neither a guard refusal (%d) nor a write error (%d)", l.GuardRefusals(), l.WriteErrors())
	}
}

// A Link that succeeded and a Remove of the temp file that then failed is NOT a missing answer: the
// file exists. Marking it missing would void a good run, and at temperature 1 nothing would ever
// clear it.
func TestAFailedTempRemovalAfterALinkIsNotAMissingAnswer(t *testing.T) {
	l, raw := openRun(t)
	l.removeFile = func(string) error { return errors.New("cannot remove") }
	l.Log(recordWith("a", "kept answer"))
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	if n := l.AnswersMissing(); n != 0 {
		t.Fatalf("AnswersMissing() = %d although the file was linked", n)
	}
	if got := readFile(t, filepath.Join(raw, "answers", shaOf("kept answer")+".txt")); got != "kept answer" {
		t.Fatalf("file holds %q", got)
	}
}

// The real CreateTemp failure: an unwritable directory. Read after Close has drained, with no retry.
func TestAnUnwritableAnswersDirectoryIsCountedMissing(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root ignores directory permissions")
	}
	l, raw := openRun(t)
	answers := filepath.Join(raw, "answers")
	if err := os.Chmod(answers, 0o500); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(answers, 0o755) })

	l.Log(recordWith("a", "cannot be stored"))
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	if n := l.AnswersMissing(); n != 1 {
		t.Fatalf("AnswersMissing() = %d, want 1", n)
	}
	if !strings.Contains(readFile(t, filepath.Join(raw, "requests.jsonl")), `"request_id":"a"`) {
		t.Fatal("the record was lost with its answer; it must still be written")
	}
}

// The guard: a record whose text does not hash to its AnswerSHA256 is refused, counted, and the
// count is never cleared. Setting the exported field without SetAnswer is the call-site defect it
// exists for: without it the writer would publish an empty file under another text's name.
func TestTheGuardRefusesAMismatchAndNeverForgets(t *testing.T) {
	l, raw := openRun(t)
	l.Log(Record{RequestID: "bad", Cache: "MISS", AnswerSHA256: shaOf("one")}) // no text
	waitFor(t, "the guard refusal", func() bool { return l.GuardRefusals() == 1 })
	if got := names(t, filepath.Join(raw, "answers")); len(got) != 0 {
		t.Fatalf("the guard let %v through", got)
	}
	if n := l.AnswersMissing(); n != 1 {
		t.Fatalf("AnswersMissing() = %d after a refusal, want 1", n)
	}

	// A well-formed record with the same hash retries the write and clears `missing` ...
	l.Log(recordWith("good", "one"))
	waitFor(t, "the retry", func() bool { return l.AnswersMissing() == 0 })
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	// ... but the refusal itself stays: a call site skipped SetAnswer, and that voids the run.
	if n := l.GuardRefusals(); n != 1 {
		t.Fatalf("GuardRefusals() = %d after a later good record, want 1: it must never be cleared", n)
	}
}

// Acceptance 9a: an existing file is never rewritten. The sentinel differs from the text, so both a
// rename-over and an in-place truncate change what is on disk, and a rename also changes the inode.
func TestAnExistingAnswerFileIsNeverRewritten(t *testing.T) {
	l, raw := openRun(t)
	target := filepath.Join(raw, "answers", shaOf("the real text")+".txt")
	if err := os.WriteFile(target, []byte("SENTINEL"), 0o644); err != nil {
		t.Fatal(err)
	}
	before, err := os.Stat(target)
	if err != nil {
		t.Fatal(err)
	}

	l.Log(recordWith("a", "the real text"))
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	if got := readFile(t, target); got != "SENTINEL" {
		t.Fatalf("an existing file was rewritten: it now holds %q", got)
	}
	after, err := os.Stat(target)
	if err != nil {
		t.Fatal(err)
	}
	if !os.SameFile(before, after) {
		t.Fatal("an existing file was replaced (its inode changed)")
	}
	if n := l.AnswersMissing(); n != 0 {
		t.Fatalf("AnswersMissing() = %d: an existing file is the file", n)
	}
	for _, name := range names(t, filepath.Join(raw, "answers")) {
		if strings.HasSuffix(name, ".tmp") {
			t.Fatalf("temp residue %q after a clean Close", name)
		}
	}
}

func TestOpenCreatesTheAnswersDirectory(t *testing.T) {
	dir := t.TempDir()
	l, err := Open(dir, "run-dir")
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	fi, err := os.Stat(filepath.Join(dir, "run-dir", "raw", "answers"))
	if err != nil || !fi.IsDir() {
		t.Fatalf("raw/answers/ was not created: %v", err)
	}
}

// Acceptance 9b, fixture A: a raw/ that holds requests.jsonl and NO answers/. Open refuses at the
// exclusive create, and it must create nothing inside that run. (A fixture with answers/ present
// would pass for the wrong reason: the directory create would refuse first.)
func TestOpenOnAnExistingRunFileCreatesNothingInsideIt(t *testing.T) {
	dir := t.TempDir()
	raw := filepath.Join(dir, "run-old", "raw")
	if err := os.MkdirAll(raw, 0o755); err != nil {
		t.Fatal(err)
	}
	jsonl := filepath.Join(raw, "requests.jsonl")
	if err := os.WriteFile(jsonl, []byte("{}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := Open(dir, "run-old"); err == nil {
		t.Fatal("Open succeeded on a run that already has a requests.jsonl")
	}
	if got := names(t, raw); len(got) != 1 || got[0] != "requests.jsonl" {
		t.Fatalf("Open left %v in a finished run's raw/; it must create nothing there", got)
	}
	if got := readFile(t, jsonl); got != "{}\n" {
		t.Fatalf("a finished run's requests.jsonl was touched: %q", got)
	}
}

// Fixture B: answers/ exists but requests.jsonl does not. A half-finished earlier attempt must not
// donate its files to this run: Open refuses, and removes only the requests.jsonl it just made.
func TestOpenRefusesAPreexistingAnswersDirectoryAndRemovesOnlyWhatItMade(t *testing.T) {
	dir := t.TempDir()
	answers := filepath.Join(dir, "run-half", "raw", "answers")
	if err := os.MkdirAll(answers, 0o755); err != nil {
		t.Fatal(err)
	}
	stray := filepath.Join(answers, shaOf("left over")+".txt")
	if err := os.WriteFile(stray, []byte("left over"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := Open(dir, "run-half"); err == nil {
		t.Fatal("Open accepted a run whose answers/ already exists")
	}
	raw := filepath.Join(dir, "run-half", "raw")
	if got := names(t, raw); len(got) != 1 || got[0] != "answers" {
		t.Fatalf("raw/ holds %v after the refusal, want only the pre-existing answers/", got)
	}
	if got := readFile(t, stray); got != "left over" {
		t.Fatalf("the pre-existing file was touched: %q", got)
	}
}

// D3: a line that fails to encode is counted. The file was linked first, so a file now exists that
// no record names; without the count that would be silent.
func TestAnEncodeFailureIsCountedAndLeavesAnUnnamedFile(t *testing.T) {
	l, raw := openRun(t)
	bad := recordWith("nan", "text of the unlogged record")
	nan := math.NaN()
	bad.SourceOverlap = &nan // json: unsupported value: NaN
	l.Log(bad)
	l.Log(recordWith("fine", "text of a record that lands"))
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	if n := l.WriteErrors(); n != 1 {
		t.Fatalf("WriteErrors() = %d, want 1", n)
	}
	jsonl := readFile(t, filepath.Join(raw, "requests.jsonl"))
	if strings.Contains(jsonl, `"request_id":"nan"`) {
		t.Fatal("the record that cannot be encoded was written")
	}
	if !strings.Contains(jsonl, `"request_id":"fine"`) {
		t.Fatal("the writer stopped after one encode failure")
	}
	// The unnamed file is exactly why the count must exist.
	if _, err := os.Stat(filepath.Join(raw, "answers", shaOf("text of the unlogged record")+".txt")); err != nil {
		t.Fatalf("expected the linked file to exist: %v", err)
	}
}

func TestTheAnswerAccessorsAreNilSafe(t *testing.T) {
	var l *Logger // make dev runs with a nil Logger and main calls these
	if l.AnswersMissing() != 0 || l.GuardRefusals() != 0 || l.WriteErrors() != 0 {
		t.Fatal("an accessor on a nil Logger returned nonzero")
	}
}

// Acceptance 8: a record logged after Close creates no file (an extension of
// TestLogAfterCloseIsSafe, which stays as it is).
func TestAnAnswerLoggedAfterCloseCreatesNoFile(t *testing.T) {
	l, raw := openRun(t)
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	l.Log(recordWith("late", "an answer logged too late"))
	if got := names(t, filepath.Join(raw, "answers")); len(got) != 0 {
		t.Fatalf("a record logged after Close created %v", got)
	}
}

// Under -race this proves nothing about `missing`'s mutex unless a reader runs while Log calls are
// still being processed, so one does. It asserts nothing itself: it can fail only under -race, which
// `make verify` does not run, so the race run of plan step 7 is what gives it meaning.
func TestTheAccessorsAreSafeWhileTheWriterIsRunning(t *testing.T) {
	l, _ := openRun(t)
	var n atomic.Int64
	l.linkFile = func(old, new string) error {
		if n.Add(1)%2 == 0 { // half fail, so `missing` is written as well as read
			return errors.New("injected")
		}
		return os.Link(old, new)
	}
	stop := make(chan struct{})
	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			select {
			case <-stop:
				return
			default:
				_ = l.AnswersMissing()
				_ = l.GuardRefusals()
				_ = l.WriteErrors()
			}
		}
	}()
	for i := range 200 {
		l.Log(recordWith("r", "answer "+strings.Repeat("x", i)))
	}
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	close(stop)
	<-done
}

// The write/chmod/close failure branch: ENOSPC or a quota on WriteString or Close. A file linked
// from a truncated temp would sit under {sha}.txt, pass every "file exists" check, and be wrong; the
// whole temp-then-link design exists to prevent it. A closed *os.File makes WriteString fail the way
// a full disk does, deterministically (found by the implementation review: no test reached this branch).
func TestAFailedTempWriteNeverPublishesAFile(t *testing.T) {
	l, raw := openRun(t)
	l.createTemp = func(dir, pattern string) (*os.File, error) {
		f, err := os.CreateTemp(dir, pattern)
		if err != nil {
			return nil, err
		}
		_ = f.Close() // a write to a closed file fails, as a full disk would
		return f, nil
	}
	l.Log(recordWith("a", "must not be published half-written"))
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	if n := l.AnswersMissing(); n != 1 {
		t.Fatalf("AnswersMissing() = %d after a failed temp write, want 1", n)
	}
	if got := names(t, filepath.Join(raw, "answers")); len(got) != 0 {
		t.Fatalf("a failed temp write left %v: neither a published file nor a temp residue is allowed", got)
	}
	if !strings.Contains(readFile(t, filepath.Join(raw, "requests.jsonl")), `"request_id":"a"`) {
		t.Fatal("the record was lost with its answer; it must still be written")
	}
}
