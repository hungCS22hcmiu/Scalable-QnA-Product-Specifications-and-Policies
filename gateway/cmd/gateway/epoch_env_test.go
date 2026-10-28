package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Item 4.2 (docs/work/2026-10-28-epoch-guard/): no epoch, no start. epochFromEnv is pure apart from one
// file read, on bandFromEnv's pattern, so the rule is testable: a log.Fatalf inside main() is not. It takes
// os.LookupEnv's shape because getenv reads an empty value as unset. Here an empty DATASET_EPOCH_FILE must
// stop the gateway: with no epoch the write-back guard could only discard every request or never fire,
// and neither is a run to start. lookupFrom is the helper in gate_env_test.go.

func TestEpochFromEnv(t *testing.T) {
	dir := t.TempDir()
	write := func(name, content string) string {
		t.Helper()
		p := filepath.Join(dir, name)
		if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
		return p
	}
	valid := write("valid", "7\n")

	for _, c := range []struct {
		name    string
		env     map[string]string
		wantErr bool
	}{
		{"unset", map[string]string{}, true},
		{"empty", map[string]string{"DATASET_EPOCH_FILE": ""}, true},
		{"relative", map[string]string{"DATASET_EPOCH_FILE": "data/dataset-epoch"}, true},
		{"missing", map[string]string{"DATASET_EPOCH_FILE": filepath.Join(dir, "no-such-file")}, true},
		{"not an integer", map[string]string{"DATASET_EPOCH_FILE": write("abc", "abc\n")}, true},
		{"zero", map[string]string{"DATASET_EPOCH_FILE": write("zero", "0\n")}, true},
		{"valid", map[string]string{"DATASET_EPOCH_FILE": valid}, false},
	} {
		t.Run(c.name, func(t *testing.T) {
			f, n, err := epochFromEnv(lookupFrom(c.env))
			if c.wantErr {
				if err == nil {
					t.Fatalf("epochFromEnv(%v) = %v, %d, nil; want an error", c.env, f, n)
				}
				if f != nil {
					t.Errorf("an error came back with a file")
				}
				if !strings.Contains(err.Error(), "DATASET_EPOCH_FILE") {
					t.Errorf("error %q does not name DATASET_EPOCH_FILE", err)
				}
				return
			}
			if err != nil {
				t.Fatalf("epochFromEnv: %v", err)
			}
			if n != 7 {
				t.Errorf("value = %d, want 7", n)
			}
			if f.Path() != valid {
				t.Errorf("Path() = %q, want %q", f.Path(), valid)
			}
		})
	}
}

// TestEpochFromEnvRunsBeforeSideEffects reads main.go as text, as TestBandFromEnvRunsBeforeSideEffects
// does. A refused epoch file must stop the process before it opens Redis, dials the RAG service or
// creates a run directory, and the start-up line must name the path (design failure mode 6: two services
// reading different files is findable only if both say which one they read).
func TestEpochFromEnvRunsBeforeSideEffects(t *testing.T) {
	raw, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatal(err)
	}
	var code []string
	for _, line := range strings.Split(string(raw), "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "//") {
			continue
		}
		code = append(code, line)
	}
	src := strings.Join(code, "\n")

	call := "epochFromEnv(os.LookupEnv)"
	at := strings.Index(src, call)
	if at < 0 {
		t.Fatalf("main.go does not call %s", call)
	}
	for _, effect := range []string{"redis.NewClient(", "ragclient.New(", "telemetry.Open("} {
		effectAt := strings.Index(src, effect)
		if effectAt < 0 {
			t.Fatalf("main.go does not contain %s, so the order cannot be checked", effect)
		}
		if at > effectAt {
			t.Errorf("%s comes after %s: a refused epoch file would already have opened it", call, effect)
		}
	}
	if !strings.Contains(src, "dataset_epoch_file=") {
		t.Errorf("main.go does not log dataset_epoch_file=, so a run cannot show which file the gateway read")
	}
}
