package reuse

import "testing"

// Item 4.5 (docs/work/2026-10-27-mixed-arm-field/): ADR-016 pins two lane bands and treats the MIXED lane
// as an on/off arm. Pinned says which bands are allowed, Arm names the arm the record carries, and the
// last test shows that the arm Arm names is the behaviour Classify has, which is what makes the label
// true. This file is new on purpose: the existing reuse tests are not edited.

func TestPinnedBands(t *testing.T) {
	for _, c := range []struct {
		name string
		band LaneBand
		want bool
	}{
		{"off arm, the closed default", LaneBand{Lo: 0.20, Hi: 0.20}, true},
		{"on arm", LaneBand{Lo: 0.20, Hi: 0.60}, true},
		{"the constants", LaneBand{Lo: PinnedLo, Hi: PinnedHiOn}, true},
		{"hi too high", LaneBand{Lo: 0.20, Hi: 0.70}, false},
		{"lo moved, closed", LaneBand{Lo: 0.30, Hi: 0.30}, false},
		{"hi below lo", LaneBand{Lo: 0.20, Hi: 0.10}, false},
		{"the zero band", LaneBand{}, false},
		{"hi almost 0.60", LaneBand{Lo: 0.20, Hi: 0.6000001}, false},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := c.band.Pinned(); got != c.want {
				t.Errorf("%+v.Pinned() = %v, want %v", c.band, got, c.want)
			}
		})
	}
}

func TestBandArm(t *testing.T) {
	for _, c := range []struct {
		name string
		band LaneBand
		want string
	}{
		{"closed band is off", LaneBand{Lo: 0.20, Hi: 0.20}, "off"},
		{"zero band is off, as Classify treats it", LaneBand{}, "off"},
		{"open band is on", LaneBand{Lo: 0.20, Hi: 0.60}, "on"},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := c.band.Arm(); got != c.want {
				t.Errorf("%+v.Arm() = %q, want %q", c.band, got, c.want)
			}
		})
	}
}

// One policy chunk in three is a fraction of 1/3, which is inside [0.20, 0.60). Under the on band it is
// MIXED. Under the off band, closed at 0.20, every fraction at or above 0.20 goes to POLICY. The arm each
// band carries is the arm of the behaviour it gives.
func TestPinnedBandsClassifyMixedGrounding(t *testing.T) {
	grounding := []string{
		"product-kettle-01#chunk-0",
		"policy-returns-01#chunk-0",
		"product-kettle-01#chunk-1",
	}
	on := LaneBand{Lo: PinnedLo, Hi: PinnedHiOn}
	off := LaneBand{Lo: PinnedLo, Hi: PinnedLo}

	if !on.Pinned() || !off.Pinned() {
		t.Fatalf("both bands under test must be pinned: on=%v off=%v", on.Pinned(), off.Pinned())
	}
	if got := Classify(grounding, on); got != LaneMixed {
		t.Errorf("Classify under the on band = %q, want %q", got, LaneMixed)
	}
	if got := Classify(grounding, off); got != LanePolicy {
		t.Errorf("Classify under the off band = %q, want %q", got, LanePolicy)
	}
	if got := on.Arm(); got != "on" {
		t.Errorf("the on band's Arm() = %q, want \"on\"", got)
	}
	if got := off.Arm(); got != "off" {
		t.Errorf("the off band's Arm() = %q, want \"off\"", got)
	}
}
