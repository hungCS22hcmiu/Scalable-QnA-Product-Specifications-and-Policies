package main

import (
	"os"
	"strings"
	"testing"

	"github.com/hung/thesis/gateway/internal/reuse"
)

// Item 4.5 (docs/work/2026-10-27-mixed-arm-field/): the MIXED lane is an on/off arm (ADR-016), and the
// gateway runs only the two pinned bands, [0.20, 0.20) (off, the default) and [0.20, 0.60) (on). bandFromEnv
// is pure, on gateFromEnv's pattern, so the rule is testable: a log.Fatalf inside main() is not. It takes
// os.LookupEnv's shape, not getenvFloat's, because getenvFloat reads an empty value as unset and runs the
// default, so `LANE_SIGMA_HI=` or `LANE_SIGMA_HI=0,60` would quietly run the off arm under a run id meant for
// the on arm. lookupFrom is the helper in gate_env_test.go.

func TestBandFromEnv(t *testing.T) {
	off := reuse.LaneBand{Lo: 0.20, Hi: 0.20}
	on := reuse.LaneBand{Lo: 0.20, Hi: 0.60}

	for _, c := range []struct {
		name    string
		env     map[string]string
		want    reuse.LaneBand
		wantArm string
	}{
		{"unset is off", map[string]string{}, off, "off"},
		{"both at 0.20 is off", map[string]string{"LANE_SIGMA": "0.20", "LANE_SIGMA_HI": "0.20"}, off, "off"},
		{"LANE_SIGMA alone at 0.20 is off", map[string]string{"LANE_SIGMA": "0.20"}, off, "off"},
		{"LANE_SIGMA_HI alone at 0.20 is off", map[string]string{"LANE_SIGMA_HI": "0.20"}, off, "off"},
		{"LANE_SIGMA_HI=0.60 is on", map[string]string{"LANE_SIGMA_HI": "0.60"}, on, "on"},
		{"0.20 and 0.60 is on", map[string]string{"LANE_SIGMA": "0.20", "LANE_SIGMA_HI": "0.60"}, on, "on"},
		{"LANE_SIGMA_HI=0.6 is on", map[string]string{"LANE_SIGMA_HI": "0.6"}, on, "on"},
		{"other variables do not matter", map[string]string{"CONFIG_ID": "4", "SUPPORT_GATE": "off"}, off, "off"},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, err := bandFromEnv(lookupFrom(c.env))
			if err != nil {
				t.Fatalf("err = %v, want none", err)
			}
			if got != c.want {
				t.Errorf("band = %+v, want %+v", got, c.want)
			}
			if arm := got.Arm(); arm != c.wantArm {
				t.Errorf("Arm() = %q, want %q", arm, c.wantArm)
			}
		})
	}

	// Every one of these is refused. offending is the value as the error must show it, quoted, so a
	// wrong value is found at a glance.
	for _, c := range []struct {
		name      string
		env       map[string]string
		offending string
	}{
		{"hi above the pinned on band", map[string]string{"LANE_SIGMA_HI": "0.70"}, `"0.70"`},
		{"lo moved, hi unset", map[string]string{"LANE_SIGMA": "0.30"}, `"0.30"`},
		{"lo at 0.60, hi unset: the band [0.60, 0.60)", map[string]string{"LANE_SIGMA": "0.60"}, `"0.60"`},
		{"hi below lo", map[string]string{"LANE_SIGMA_HI": "0.10"}, `"0.10"`},
		{"hi is not a number", map[string]string{"LANE_SIGMA_HI": "abc"}, `"abc"`},
		{"a decimal comma", map[string]string{"LANE_SIGMA_HI": "0,60"}, `"0,60"`},
		// Set but empty: `make dev LANE_SIGMA_HI=` exports an empty value. That is an error, not the default.
		{"hi set but empty", map[string]string{"LANE_SIGMA_HI": ""}, `LANE_SIGMA_HI=""`},
		{"lo set but empty", map[string]string{"LANE_SIGMA": ""}, `LANE_SIGMA=""`},
		{"a leading space", map[string]string{"LANE_SIGMA_HI": " 0.60"}, `" 0.60"`},
		{"almost the pinned hi", map[string]string{"LANE_SIGMA_HI": "0.6000001"}, `"0.6000001"`},
	} {
		t.Run("refuses "+c.name, func(t *testing.T) {
			got, err := bandFromEnv(lookupFrom(c.env))
			if err == nil {
				t.Fatalf("band = %+v and no error, want an error", got)
			}
			// On error the band is the closed one: a caller that ignored the error would still run off.
			if got != (reuse.LaneBand{Lo: 0.20, Hi: 0.20}) {
				t.Errorf("band on error = %+v, want the closed band [0.20, 0.20)", got)
			}
			msg := err.Error()
			for _, must := range []string{"ADR-016", "LANE_SIGMA=", "LANE_SIGMA_HI=", c.offending} {
				if !strings.Contains(msg, must) {
					t.Errorf("the error %q does not contain %s; an operator needs both values, the ADR and the offending value", msg, must)
				}
			}
		})
	}
}

// The band is read BEFORE anything with a side effect, as gateFromEnv is: a band that is refused must not
// leave a run directory behind, and one that is refused after Redis is opened wastes a start. main() has no
// test of its own, so this reads its source. Comment lines are dropped first, so a comment that names a
// call cannot satisfy or break the order.
func TestBandFromEnvRunsBeforeSideEffects(t *testing.T) {
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

	call := "bandFromEnv(os.LookupEnv)"
	at := strings.Index(src, call)
	if at < 0 {
		t.Fatalf("main.go does not call %s", call)
	}
	gate := "gateFromEnv(os.LookupEnv)"
	gateAt := strings.Index(src, gate)
	if gateAt < 0 {
		t.Fatalf("main.go does not call %s", gate)
	}
	if at < gateAt {
		t.Errorf("%s comes before %s; the band check follows the gate check", call, gate)
	}
	for _, effect := range []string{"redis.NewClient(", "ragclient.New(", "telemetry.Open("} {
		effectAt := strings.Index(src, effect)
		if effectAt < 0 {
			t.Fatalf("main.go does not contain %s, so the order cannot be checked", effect)
		}
		if at > effectAt {
			t.Errorf("%s comes after %s: a refused band would already have opened it", call, effect)
		}
	}
}
