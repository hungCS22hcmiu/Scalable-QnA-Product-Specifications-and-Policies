package httpapi

import (
	"net/http"
	"testing"
)

// Item 4.3, done condition 8. A Tier-2 hit promotes into Tier 1 through the conditional write
// (cache.Entry.Promotion), never a plain Put: the condition ("only while t2:{entry_id} exists") closes
// the race between the background promotion and an eviction or purge of the same entry. A plain Put
// would leave that race open, and nothing else would show it.
//
// The fake store records the entry it is given, so it shows which kind of write the handler asked for.
// Whether the real store honours the flag is cache/'s own test (TestPromotionNeedsTier2).
func TestTier2HitPromotesConditionally(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	hit := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
	hs.records(t)

	if hit.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", hit.w.Code, hit.w.Body)
	}
	hit.response(t).str("cache", "TIER2_HIT")
	writes := hs.store.tier1Written()
	if len(writes) != 1 {
		t.Fatalf("%d Tier-1 writes after a Tier-2 hit, want 1 (the promotion)", len(writes))
	}
	if !writes[0].entry.Promotion {
		t.Fatal("the Tier-2 hit wrote Tier 1 with a plain Put: Promotion is false, so the write is unconditional")
	}

	// The other Tier-1 write, the miss write-back, is a plain Put: it creates the entry, so there is
	// no t2: record to wait for.
	ms := newHarness(t, 1, 0)
	const q = "Does the Aurora Kettle switch itself OFF?"
	ms.embedFresh(q)
	miss := ms.ask(t, askReq{question: q, productID: kettle.id})
	ms.records(t)

	miss.response(t).str("cache", "MISS")
	missWrites := ms.store.tier1Written()
	if len(missWrites) != 1 {
		t.Fatalf("%d Tier-1 writes after a miss, want 1", len(missWrites))
	}
	if missWrites[0].entry.Promotion {
		t.Fatal("the miss write-back set Promotion: it would be refused when no t2: record exists yet")
	}
}
