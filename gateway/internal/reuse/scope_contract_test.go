package reuse

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sort"
	"testing"
)

// The Go side of the cross-language scope contract, contracts/scope/cases.json (item 6.0a, ADR-030,
// done condition 7). rag/src/rag/docmeta.py builds the bound-word lists and experiments/scripts/
// scope_calibrate.py calibrates tau_P on the same tokenizer and projection; this package applies them to
// every miss and every shared request. A divergence is silent in both directions (a bound word is never
// found; tau_P is wrong by a constant), so both sides assert against this one file.

type scopeContract struct {
	Contract string `json:"contract"`
	Tokenize []struct {
		Name string   `json:"name"`
		In   string   `json:"in"`
		Out  []string `json:"out"`
	} `json:"tokenize"`
	Scope []struct {
		Name    string `json:"name"`
		Lane    string `json:"lane"`
		Answer  string `json:"answer"`
		Product struct {
			Category    string   `json:"category"`
			HasTitleVec bool     `json:"has_title_vec"`
			BoundWords  []string `json:"bound_words"`
		} `json:"product"`
		Policy struct {
			Category string `json:"category"`
		} `json:"policy"`
		HasPolicy bool   `json:"has_policy"`
		Out       string `json:"out"`
	} `json:"scope"`
	Project []struct {
		Name string    `json:"name"`
		V    []float64 `json:"v"`
		T    []float64 `json:"t"`
		Out  []float64 `json:"out"`
		Tol  float64   `json:"tol"`
	} `json:"project"`
}

func loadScopeContract(t *testing.T) scopeContract {
	t.Helper()
	path := filepath.Join("..", "..", "..", "contracts", "scope", "cases.json")
	blob, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("reading the scope contract: %v", err)
	}
	var c scopeContract
	if err := json.Unmarshal(blob, &c); err != nil {
		t.Fatalf("parsing %s: %v", path, err)
	}
	if c.Contract != "scope-by-evidence" {
		t.Fatalf("contract names %q; this test asserts scope-by-evidence", c.Contract)
	}
	if len(c.Tokenize) < 8 || len(c.Scope) < 8 || len(c.Project) < 6 {
		t.Fatalf("the contract has %d tokenize, %d scope and %d project cases -- an empty or thin file would pass vacuously on both sides",
			len(c.Tokenize), len(c.Scope), len(c.Project))
	}
	return c
}

func f32(v []float64) []float32 {
	if v == nil {
		return nil
	}
	out := make([]float32, len(v))
	for i, x := range v {
		out[i] = float32(x)
	}
	return out
}

func TestScopeTokensMatchesCrossLanguageContract(t *testing.T) {
	for _, tc := range loadScopeContract(t).Tokenize {
		t.Run(tc.Name, func(t *testing.T) {
			got := make([]string, 0)
			for tok := range ScopeTokens(tc.In) {
				got = append(got, tok)
			}
			sort.Strings(got)
			if len(got) != len(tc.Out) {
				t.Fatalf("ScopeTokens(%q) = %v, contract says %v", tc.In, got, tc.Out)
			}
			for i := range got {
				if got[i] != tc.Out[i] {
					t.Fatalf("ScopeTokens(%q) = %v, contract says %v", tc.In, got, tc.Out)
				}
			}
		})
	}
}

func TestDecideScopeMatchesCrossLanguageContract(t *testing.T) {
	for _, tc := range loadScopeContract(t).Scope {
		t.Run(tc.Name, func(t *testing.T) {
			product := DocMeta{Category: tc.Product.Category, BoundWords: map[string]struct{}{}}
			if tc.Product.HasTitleVec {
				product.TitleVec = []float32{1, 0, 0}
			}
			for _, w := range tc.Product.BoundWords {
				product.BoundWords[w] = struct{}{}
			}
			policy := DocMeta{Category: tc.Policy.Category}
			got := DecideScope(Lane(tc.Lane), tc.Answer, product, policy, tc.HasPolicy)
			if string(got) != tc.Out {
				t.Errorf("DecideScope = %q, contract says %q", got, tc.Out)
			}
		})
	}
}

func TestProjectMatchesCrossLanguageContract(t *testing.T) {
	for _, tc := range loadScopeContract(t).Project {
		t.Run(tc.Name, func(t *testing.T) {
			got := Project(f32(tc.V), f32(tc.T))
			if tc.Out == nil {
				if got != nil {
					t.Fatalf("Project = %v, contract says nil", got)
				}
				return
			}
			if got == nil {
				t.Fatalf("Project = nil, contract says %v", tc.Out)
			}
			if len(got) != len(tc.Out) {
				t.Fatalf("Project has %d components, contract says %d", len(got), len(tc.Out))
			}
			var norm, dot, normT float64
			for i := range got {
				if d := math.Abs(float64(got[i]) - tc.Out[i]); d > tc.Tol {
					t.Errorf("component %d = %v, contract says %v (tol %v)", i, got[i], tc.Out[i], tc.Tol)
				}
				norm += float64(got[i]) * float64(got[i])
				normT += tc.T[i] * tc.T[i]
				dot += float64(got[i]) * tc.T[i]
			}
			// The two properties of the projection, whatever the expected numbers are.
			if math.Abs(math.Sqrt(norm)-1) > 1e-6 {
				t.Errorf("|v'| = %v, want 1", math.Sqrt(norm))
			}
			if math.Abs(dot/math.Sqrt(normT)) > 1e-6 {
				t.Errorf("|v'.t^| = %v, want under 1e-6", math.Abs(dot/math.Sqrt(normT)))
			}
		})
	}
}

func TestProjectRefusesAVectorOfAnotherWidth(t *testing.T) {
	if got := Project([]float32{1, 1, 0}, []float32{1, 0}); got != nil {
		t.Errorf("v of 3 and t of 2 gave %v, want nil", got)
	}
}

func TestSharedNamespaceIsThePolicyDocumentAlone(t *testing.T) {
	ids := []string{"policy-return-electronics#chunk-0", "product-electronics-b000tnfaq2#chunk-0"}
	doc := Namespace(LanePolicy, ids, "")
	if SharedNamespace(doc) != "policy-return-electronics" {
		t.Errorf("SharedNamespace = %q", SharedNamespace(doc))
	}
	// A shared namespace is never a product-scope one: they differ by the separator.
	if SharedNamespace(doc) == Namespace(LanePolicy, ids, "product-electronics-b000tnfaq2") {
		t.Error("the shared and the product-scope namespace are the same string")
	}
}

func TestCanShareNeedsTheSameNonEmptyCategoryAMetadataRecordAndATitleVector(t *testing.T) {
	product := DocMeta{Category: "electronics", TitleVec: []float32{1}}
	policy := DocMeta{Category: "electronics"}
	if !CanShare(product, policy, true) {
		t.Fatal("the base case must share")
	}
	for name, tc := range map[string]struct {
		product, policy DocMeta
		hasPolicy       bool
	}{
		"no policy metadata":     {product, policy, false},
		"another category":       {product, DocMeta{Category: "furniture"}, true},
		"empty categories":       {DocMeta{TitleVec: []float32{1}}, DocMeta{}, true},
		"no title vector":        {DocMeta{Category: "electronics"}, policy, true},
		"empty product category": {DocMeta{TitleVec: []float32{1}}, policy, true},
	} {
		if CanShare(tc.product, tc.policy, tc.hasPolicy) {
			t.Errorf("%s: CanShare = true, want false", name)
		}
	}
}
