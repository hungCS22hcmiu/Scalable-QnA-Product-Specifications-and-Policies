package reuse

import "testing"

// ADR-024: the POLICY namespace names the product too. With a product_id it is
// "{policy_doc}@{product_id}", so a policy answer is reused only for the product it was written
// for. These pin the form, the no-product case, and that a POLICY and a MIXED namespace can never
// be equal (the pure-lane rule has no lane check, so equality would let the two lanes meet with no
// error).

const (
	kettleID      = "product-kettle-01"
	headphonesID  = "product-headphones-03"
	policyDocName = "policy-returns-01"
)

var (
	policyOnly = []string{"policy-returns-01#chunk-0", "policy-returns-01#chunk-1"}
	policyFlip = []string{"policy-returns-01#chunk-1", "policy-returns-01#chunk-0"}
	mixedSet   = []string{"product-kettle-01#chunk-0", "policy-returns-01#chunk-0", "product-kettle-01#chunk-1"}
)

func TestPolicyNamespaceNamesTheProduct(t *testing.T) {
	t.Run("two_products_two_namespaces", func(t *testing.T) {
		kettle := Namespace(LanePolicy, policyOnly, kettleID)
		headphones := Namespace(LanePolicy, policyOnly, headphonesID)
		if kettle == headphones {
			t.Fatalf("two products share the POLICY namespace %q", kettle)
		}
		if again := Namespace(LanePolicy, policyFlip, kettleID); again != kettle {
			t.Fatalf("same product and same rank-1 policy document gave %q, want %q", again, kettle)
		}
	})

	t.Run("no_product_is_the_policy_doc", func(t *testing.T) {
		if got := Namespace(LanePolicy, policyOnly, ""); got != policyDocName {
			t.Fatalf("POLICY namespace with no product_id = %q, want %q", got, policyDocName)
		}
	})

	t.Run("the_form", func(t *testing.T) {
		want := "policy-returns-01@product-kettle-01"
		if got := Namespace(LanePolicy, policyOnly, kettleID); got != want {
			t.Fatalf("POLICY namespace = %q, want %q", got, want)
		}
	})
}

func TestPolicyAndMixedNamespacesNeverMeet(t *testing.T) {
	// Built from the same chunks and the same product, the two lanes must give different strings.
	// A pair is compared only when both are non-empty: an empty namespace is unmatchable anyway.
	compared := 0
	for _, product := range []string{kettleID, headphonesID, ""} {
		for name, set := range map[string][]string{"policyOnly": policyOnly, "mixed": mixedSet} {
			pol := Namespace(LanePolicy, set, product)
			mix := Namespace(LaneMixed, set, product)
			if pol == "" || mix == "" {
				continue
			}
			compared++
			if pol == mix {
				t.Errorf("set %s, product %q: POLICY and MIXED namespaces are both %q", name, product, pol)
			}
		}
	}
	if compared == 0 {
		t.Fatal("no pair had both namespaces non-empty, so nothing was compared")
	}
}

func TestPolicyEntryOfAnotherProductIsRefused(t *testing.T) {
	th := Thresholds{Tau: 0.85, Theta: 0.60}

	queryNS := Namespace(LanePolicy, policyOnly, kettleID)
	otherNS := Namespace(LanePolicy, policyOnly, headphonesID)
	ownNS := Namespace(LanePolicy, policyFlip, kettleID)

	other := th.DecideLane(LaneInput{
		Similarity: 1.0,
		QueryLane:  LanePolicy, QueryNS: queryNS,
		EntryLane: LanePolicy, EntryNS: otherNS,
	})
	if other.Reuse {
		t.Fatalf("a POLICY entry of product B was served to a POLICY query of product A (query %q, entry %q)", queryNS, otherNS)
	}

	own := th.DecideLane(LaneInput{
		Similarity: 1.0,
		QueryLane:  LanePolicy, QueryNS: queryNS,
		EntryLane: LanePolicy, EntryNS: ownNS,
	})
	if !own.Reuse {
		t.Fatalf("product A's own POLICY entry was refused (query %q, entry %q)", queryNS, ownNS)
	}
}
