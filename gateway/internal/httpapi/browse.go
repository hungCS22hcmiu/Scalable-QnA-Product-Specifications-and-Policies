package httpapi

import (
	"encoding/json"
	"net/http"
	"sync/atomic"

	"github.com/hung/thesis/gateway/internal/catalog"
)

// Endpoints the demo UI needs and nothing else does (the demo UI contract).
//
// ⚠️ Neither is on a measured path. `/stats` in particular is NOT the measurement channel: every
// reported number comes from the per-request evaluation log (interfaces.md §H), which is
// write-once and survives the process. These counters are in-memory, reset on restart, and exist
// so the demo's required counters sidebar can show a live figure. If a number from here ever
// reaches a slide, that is the failure mode `make dev`'s non-citable banner exists to prevent.

// Counters back the demo's required sidebar: total requests, hit rate, generations avoided.
//
// They live on the gateway rather than in the browser because the demo drives the system from
// SEVERAL TABS AT ONCE. A per-tab counter would show each tab its own private slice of the
// traffic, which is exactly wrong for a demonstration whose point is that concurrent duplicate
// questions collapse onto one generation -- the tab that gets coalesced would show nothing
// interesting, and no tab would show the total.
type Counters struct {
	Requests  atomic.Int64
	Tier1     atomic.Int64
	Tier2     atomic.Int64
	Miss      atomic.Int64
	Shed      atomic.Int64
	Coalesced atomic.Int64
	Generated atomic.Int64
}

type statsResponse struct {
	Requests int64 `json:"requests"`
	Tier1    int64 `json:"tier1_hits"`
	Tier2    int64 `json:"tier2_hits"`
	Miss     int64 `json:"misses"`
	Shed     int64 `json:"shed"`

	// Coalesced counts requests that were duplicates of an in-flight generation and were served
	// its result. Reported separately from hits because it is a different mechanism: a hit reuses
	// a STORED answer, a coalesced follower rides along on one still being produced.
	Coalesced int64 `json:"coalesced"`

	// Generated is the number of times the model actually ran. This is the quantity the whole
	// system exists to reduce.
	Generated int64 `json:"generations_run"`

	// GenerationsAvoided = served requests that did not cause a generation. It is the
	// load-conversion ratio of proposal §3 as a single number, which is what makes it the
	// cheapest scalability evidence visible during the live steps of the demo.
	GenerationsAvoided int64 `json:"generations_avoided"`

	// HitRate excludes shed requests from the denominator: a shed request was never served, so
	// counting it as a miss would let the hit rate be improved by shedding harder
	// (the evaluation keeps goodput and sheds separate for the same reason).
	HitRate float64 `json:"hit_rate"`
}

// record bumps the counters from a finished request's evaluation record. Called from Ask's
// single deferred exit point, so every path -- hit, miss, shed, abandoned, failed -- lands here
// exactly once and no path can forget to.
func (c *Counters) record(cacheOutcome string, coalesced bool) {
	c.Requests.Add(1)
	switch cacheOutcome {
	case cacheTier1Hit:
		c.Tier1.Add(1)
	case cacheTier2Hit:
		c.Tier2.Add(1)
	case cacheMiss:
		c.Miss.Add(1)
		// A miss that was coalesced rode along on someone else's generation; only the leader
		// actually ran the model.
		if coalesced {
			c.Coalesced.Add(1)
		} else {
			c.Generated.Add(1)
		}
	case cacheShed:
		c.Shed.Add(1)
	}
	// ABANDONED and GENERATION_FAILED are counted in Requests and nowhere else. They were neither
	// served nor shed, and folding them into either bucket would misreport one of the two.
}

func (c *Counters) snapshot() statsResponse {
	t1, t2 := c.Tier1.Load(), c.Tier2.Load()
	shed, coalesced := c.Shed.Load(), c.Coalesced.Load()
	served := t1 + t2 + c.Miss.Load()

	var hitRate float64
	if served > 0 {
		hitRate = float64(t1+t2) / float64(served)
	}
	return statsResponse{
		Requests:           c.Requests.Load(),
		Tier1:              t1,
		Tier2:              t2,
		Miss:               c.Miss.Load(),
		Shed:               shed,
		Coalesced:          coalesced,
		Generated:          c.Generated.Load(),
		GenerationsAvoided: t1 + t2 + coalesced,
		HitRate:            hitRate,
	}
}

// Stats serves GET /stats for the demo's counters sidebar.
func (h *Handler) Stats(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, h.Counters.snapshot())
}

// Products serves GET /products for the demo's product list.
//
// Degrades to an empty list rather than a 500 when the catalogue is unavailable, for the same
// reason the Tier-2 cascade degrades to a miss: an unavailable convenience must not take down the
// page whose actual subject is the cache.
func (h *Handler) Products(w http.ResponseWriter, r *http.Request) {
	if h.Catalog == nil {
		writeJSON(w, []catalog.Product{})
		return
	}
	products, err := h.Catalog.Products(r.Context())
	if err != nil {
		writeJSONStatus(w, http.StatusServiceUnavailable, map[string]string{
			"error":  "catalog_unavailable",
			"reason": err.Error(),
		})
		return
	}
	writeJSON(w, products)
}

// writeJSONStatus is writeJSON plus an explicit status. Kept separate rather than changing
// writeJSON's signature, because every /ask response is a 200 by construction -- a shed is
// written by its own path -- and widening that helper would invite a status argument at call
// sites that must not have one.
func writeJSONStatus(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
