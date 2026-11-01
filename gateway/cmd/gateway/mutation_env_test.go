package main

import (
	"os"
	"strings"
	"testing"
)

// interfaces.md v0.25: MUTATION=on|off labels the run, and a run is identified by (config_id, mutation).
// mutationFromEnv is pure, on gateFromEnv's pattern, so the rule is testable: a log.Fatalf inside main()
// is not. It takes os.LookupEnv's shape, because "MUTATION=" must stop the gateway, not quietly read "off".

func TestMutationFromEnv(t *testing.T) {
	for _, c := range []struct {
		name    string
		env     map[string]string
		want    string
		wantErr bool
	}{
		{"unset is off", map[string]string{}, "off", false},
		{"other variables do not matter", map[string]string{"CONFIG_ID": "5", "SUPPORT_GATE": "on"}, "off", false},
		{"off", map[string]string{"MUTATION": "off"}, "off", false},
		{"on", map[string]string{"MUTATION": "on"}, "on", false},
		{"set but empty", map[string]string{"MUTATION": ""}, "off", true},
		{"capital letters", map[string]string{"MUTATION": "On"}, "off", true},
		{"a leading space", map[string]string{"MUTATION": " on"}, "off", true},
		{"a number", map[string]string{"MUTATION": "1"}, "off", true},
		{"yes", map[string]string{"MUTATION": "yes"}, "off", true},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, err := mutationFromEnv(lookupFrom(c.env))
			if (err != nil) != c.wantErr {
				t.Fatalf("err = %v, wantErr %v", err, c.wantErr)
			}
			if got != c.want {
				t.Errorf("mutation = %q, want %q", got, c.want)
			}
			if err != nil {
				msg := err.Error()
				for _, must := range []string{"MUTATION", `"on"`, `"off"`} {
					if !strings.Contains(msg, must) {
						t.Errorf("the error %q does not mention %s; an operator needs the variable and the two allowed values", msg, must)
					}
				}
			}
		})
	}
}

// The error must show what was set, so `MUTATION=On` is found at a glance.
func TestMutationFromEnvErrorShowsTheValue(t *testing.T) {
	_, err := mutationFromEnv(lookupFrom(map[string]string{"MUTATION": "On"}))
	if err == nil || !strings.Contains(err.Error(), `"On"`) {
		t.Errorf("err = %v, want it to quote the offending value", err)
	}
}

// The mutation arm is read BEFORE anything with a side effect, as the band is: a refused value must not leave
// a run directory behind. main() has no test of its own, so this reads its source, with comment lines dropped
// so a comment that names a call cannot satisfy or break the order. The handler must take the parsed value,
// never a second read of the environment.
func TestMutationFromEnvRunsBeforeSideEffects(t *testing.T) {
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

	call := "mutationFromEnv(os.LookupEnv)"
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
			t.Errorf("%s comes after %s: a refused value would already have opened it", call, effect)
		}
	}
	if !strings.Contains(src, "handler.Mutation = mutation") {
		t.Errorf("main.go does not set handler.Mutation from the parsed value")
	}
	if strings.Contains(src, `getenv("MUTATION"`) {
		t.Errorf("main.go still reads MUTATION through getenv, which takes an empty value as unset")
	}
}
