package main

import (
	"strings"
	"testing"
)

// The guard's predicate (docs/work/2026-10-05-retire-unfiltered-phase/, design.md §3). Whether main
// still calls it is checked by acceptance 1's grep and by the recorded binary run, not here.
func TestRetiredEnvRefusesTauHigh(t *testing.T) {
	for _, tc := range []struct {
		name   string
		env    map[string]string
		refuse bool
	}{
		{"unset", map[string]string{}, false},
		{"set", map[string]string{"REUSE_TAU_HIGH": "0.95"}, true},
		// getenvFloat reads "" as unset, so an empty value never enabled the short-circuit and
		// nobody can have relied on it as a configuration-3 run.
		{"empty", map[string]string{"REUSE_TAU_HIGH": ""}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			err := retiredEnv(func(k string) string { return tc.env[k] })
			if !tc.refuse {
				if err != nil {
					t.Fatalf("retiredEnv = %v, want nil", err)
				}
				return
			}
			if err == nil {
				t.Fatal("retiredEnv = nil, want a refusal")
			}
			for _, want := range []string{"REUSE_TAU_HIGH", "retired"} {
				if !strings.Contains(err.Error(), want) {
					t.Errorf("retiredEnv = %q, want it to name %q", err, want)
				}
			}
		})
	}
}
