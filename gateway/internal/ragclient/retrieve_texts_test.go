package ragclient

import (
	"context"
	"errors"
	"slices"
	"testing"

	"github.com/hung/thesis/gateway/internal/ragpb"
	"google.golang.org/grpc"
)

// textsFake returns a configured RetrieveResponse. It is separate from retrieve_test.go's
// fakeRagServiceClient, which always returns an empty response, because that file is immutable
// (docs/work/2026-10-05-carry-chunk-text/design.md 3b).
type textsFake struct {
	ragpb.RagServiceClient
	resp *ragpb.RetrieveResponse
}

func (f *textsFake) Retrieve(_ context.Context, _ *ragpb.RetrieveRequest, _ ...grpc.CallOption) (*ragpb.RetrieveResponse, error) {
	return f.resp, nil
}

// TestRetrieveTexts pins the one part of the texts invariant a client can see: texts is either
// absent entirely or exactly as long as chunk_ids (interfaces.md B: "there is no partial
// population"). Alignment itself cannot be checked here; seam_live_test.go checks it against Redis.
//
// The aligned fixture is neither sorted nor a palindrome, by id or by text, so a client that sorts
// or reverses Texts fails it.
func TestRetrieveTexts(t *testing.T) {
	ids := []string{"product-laptops-02#chunk-0", "policy-returns#chunk-2", "product-kitchen-05#chunk-0"}
	texts := []string{"13-inch display, 1.2 kg.", "Opened items: 15 days.", "1800W at full heat."}

	cases := []struct {
		name    string
		ids     []string
		texts   []string
		wantErr bool
	}{
		{name: "aligned", ids: ids, texts: texts},
		// A non-nil empty slice, so the test also pins that absence is normalised to nil.
		{name: "absent", ids: ids, texts: []string{}},
		{name: "empty retrieval", ids: nil, texts: nil},
		{name: "short", ids: ids, texts: texts[:2], wantErr: true},
		{name: "long", ids: ids, texts: append(append([]string(nil), texts...), "extra"), wantErr: true},
		{name: "texts without ids", ids: nil, texts: texts[:2], wantErr: true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			// The fake gets copies. Retrieve may hand back the wire slice itself, so without them a
			// client that reordered Texts in place would rewrite the expected values too, and the
			// comparison below would pass against itself (found by mutation M9).
			resp := &ragpb.RetrieveResponse{ChunkIds: slices.Clone(tc.ids), Texts: slices.Clone(tc.texts)}
			c := &Client{rpc: &textsFake{resp: resp}}

			r, err := c.Retrieve(context.Background(), "q", 0, "")

			if tc.wantErr {
				if !errors.Is(err, ErrTextsMisaligned) {
					t.Fatalf("err = %v, want ErrTextsMisaligned", err)
				}
				if r != nil {
					t.Fatalf("result = %+v, want nil alongside the error", r)
				}
				return
			}
			if err != nil {
				t.Fatalf("Retrieve returned error: %v", err)
			}
			if len(r.ChunkIDs) != len(tc.ids) {
				t.Fatalf("len(ChunkIDs) = %d, want %d", len(r.ChunkIDs), len(tc.ids))
			}
			if len(tc.texts) == 0 {
				if r.Texts != nil {
					t.Fatalf("Texts = %#v, want nil when the service sent none", r.Texts)
				}
				return
			}
			if len(r.Texts) != len(tc.texts) {
				t.Fatalf("len(Texts) = %d, want %d", len(r.Texts), len(tc.texts))
			}
			for i := range tc.texts {
				if r.Texts[i] != tc.texts[i] {
					t.Fatalf("Texts[%d] = %q, want %q (the text of %s)", i, r.Texts[i], tc.texts[i], tc.ids[i])
				}
			}
		})
	}
}
