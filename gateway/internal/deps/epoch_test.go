package deps

import (
	"os"
	"path/filepath"
	"testing"
)

func writeEpoch(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

// TestEpochFileRereadsEveryCall guards against a cached epoch. A gateway that read the file once at
// start would miss every later advance, and a write-back stamped before an edit would then pass the
// guard against the old value, with no trace (item 4.2, design failure mode 4).
func TestEpochFileRereadsEveryCall(t *testing.T) {
	path := filepath.Join(t.TempDir(), "dataset-epoch")
	writeEpoch(t, path, "3\n")

	f, opened, err := OpenEpochFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if opened != 3 {
		t.Fatalf("OpenEpochFile read %d, want 3", opened)
	}
	if got, err := f.Current(); err != nil || got != 3 {
		t.Fatalf("Current() = %d, %v; want 3", got, err)
	}

	writeEpoch(t, path, "4\n")
	if got, err := f.Current(); err != nil || got != 4 {
		t.Fatalf("after the file was rewritten, Current() = %d, %v; want 4", got, err)
	}

	// A file that goes missing is an error, not the last value: the guard then fails closed.
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if got, err := f.Current(); err == nil {
		t.Fatalf("after the file was removed, Current() = %d, nil; want an error", got)
	}
}

func TestEpochFileOpenRefuses(t *testing.T) {
	dir := t.TempDir()
	for _, c := range []struct {
		name    string
		path    string // "" means a file this test writes
		content string
	}{
		{name: "relative", path: "data/dataset-epoch"},
		{name: "missing", path: filepath.Join(dir, "no-such-file")},
		{name: "not an integer", content: "abc\n"},
		{name: "zero", content: "0\n"},
		{name: "empty", content: ""},
		{name: "negative", content: "-1\n"},
	} {
		t.Run(c.name, func(t *testing.T) {
			path := c.path
			if path == "" {
				path = filepath.Join(t.TempDir(), "dataset-epoch")
				writeEpoch(t, path, c.content)
			}
			f, v, err := OpenEpochFile(path)
			if err == nil {
				t.Fatalf("OpenEpochFile(%q) = %v, %d, nil; want an error", path, f, v)
			}
			if f != nil {
				t.Errorf("OpenEpochFile returned a file with its error")
			}
		})
	}
}

func TestEpochFileOpenAcceptsTrailingNewline(t *testing.T) {
	for _, content := range []string{"5\n", "  5  \n", "5"} {
		path := filepath.Join(t.TempDir(), "dataset-epoch")
		writeEpoch(t, path, content)
		f, v, err := OpenEpochFile(path)
		if err != nil {
			t.Fatalf("OpenEpochFile with %q: %v", content, err)
		}
		if v != 5 {
			t.Errorf("OpenEpochFile with %q read %d, want 5", content, v)
		}
		if f.Path() != path {
			t.Errorf("Path() = %q, want %q", f.Path(), path)
		}
	}
}
