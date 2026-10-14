package main

import (
	"strings"
	"testing"

	"github.com/hung/thesis/gateway/internal/reuse"
)

// Item 2.4 (docs/work/2026-10-14-support-gate-switch/): SUPPORT_GATE=on|off selects the support gate's
// arm for the life of the process. gateFromEnv is pure, on retiredEnv's pattern, so the rule is testable:
// a log.Fatalf inside main() is not. It takes os.LookupEnv's shape, not getenv's, because getenv reads
// an empty value as unset, and "SUPPORT_GATE=" must stop the gateway, not quietly choose the default.

func lookupFrom(env map[string]string) func(string) (string, bool) {
	return func(k string) (string, bool) {
		v, ok := env[k]
		return v, ok
	}
}

func TestGateFromEnv(t *testing.T) {
	for _, c := range []struct {
		name    string
		env     map[string]string
		want    reuse.Gate
		wantErr bool
	}{
		{"unset is on", map[string]string{}, reuse.GateOn, false},
		{"other variables do not matter", map[string]string{"CONFIG_ID": "4", "MUTATION": "off"}, reuse.GateOn, false},
		{"on", map[string]string{"SUPPORT_GATE": "on"}, reuse.GateOn, false},
		{"off", map[string]string{"SUPPORT_GATE": "off"}, reuse.GateOff, false},
		// Set but empty: `make dev SUPPORT_GATE=` exports an empty value. That is an error, not "on".
		{"set but empty", map[string]string{"SUPPORT_GATE": ""}, reuse.GateOn, true},
		{"capital letters", map[string]string{"SUPPORT_GATE": "ON"}, reuse.GateOn, true},
		{"a trailing space", map[string]string{"SUPPORT_GATE": "off "}, reuse.GateOn, true},
		{"a number", map[string]string{"SUPPORT_GATE": "0"}, reuse.GateOn, true},
		{"true", map[string]string{"SUPPORT_GATE": "true"}, reuse.GateOn, true},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, err := gateFromEnv(lookupFrom(c.env))
			if (err != nil) != c.wantErr {
				t.Fatalf("err = %v, wantErr %v", err, c.wantErr)
			}
			// On error the value is GateOn: a caller that ignored the error would still run the gate.
			if got != c.want {
				t.Errorf("gate = %v, want %v", got, c.want)
			}
			if err != nil {
				msg := err.Error()
				for _, must := range []string{"SUPPORT_GATE", `"on"`, `"off"`} {
					if !strings.Contains(msg, must) {
						t.Errorf("the error %q does not mention %s; an operator needs the variable and the two allowed values", msg, must)
					}
				}
			}
		})
	}
}

// The error must show what was set, so `SUPPORT_GATE=Off` is found at a glance.
func TestGateFromEnvErrorShowsTheValue(t *testing.T) {
	_, err := gateFromEnv(lookupFrom(map[string]string{"SUPPORT_GATE": "Off"}))
	if err == nil || !strings.Contains(err.Error(), `"Off"`) {
		t.Errorf("err = %v, want it to quote the offending value", err)
	}
}
