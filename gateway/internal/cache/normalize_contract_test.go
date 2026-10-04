package cache

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// The Go side of the cross-language normalization contract, contracts/normalize/cases.json.
//
// Normalize runs on the hit path here and is mirrored in Python by the corpus gate's G3 check
// (data-card.md §7), which is the only thing that stops two differently-grounded queries from
// collapsing onto one Tier-1 key. Nothing in either build forces the two implementations to
// agree, and a divergence is silent in both directions: a looser mirror lets the gate pass a
// corpus that collides in production, a tighter one rejects a corpus Tier 1 would have handled.
//
// So both sides assert against the same file. TestNormalize above is still the readable statement
// of the intent; this is the machine-checkable statement that Python matches it.
func TestNormalizeMatchesCrossLanguageContract(t *testing.T) {
	path := filepath.Join("..", "..", "..", "contracts", "normalize", "cases.json")
	blob, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("reading the normalization contract: %v", err)
	}

	var contract struct {
		Contract string `json:"contract"`
		Cases    []struct {
			Name string `json:"name"`
			In   string `json:"in"`
			Out  string `json:"out"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(blob, &contract); err != nil {
		t.Fatalf("parsing %s: %v", path, err)
	}
	if contract.Contract != "tier1-query-normalization" {
		t.Fatalf("contract names %q; this test asserts tier1-query-normalization", contract.Contract)
	}
	if len(contract.Cases) == 0 {
		t.Fatal("the contract has no cases -- an empty file would pass vacuously on both sides")
	}

	for _, tc := range contract.Cases {
		t.Run(tc.Name, func(t *testing.T) {
			if got := Normalize(tc.In); got != tc.Out {
				t.Errorf("Normalize(%q) = %q, contract says %q", tc.In, got, tc.Out)
			}
		})
	}
}
