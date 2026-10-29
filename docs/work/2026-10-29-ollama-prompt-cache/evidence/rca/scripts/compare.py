import json, statistics as s, sys
def load(p): return [json.loads(l) for l in open(p) if '"wall_s"' in l]
A, B = load(sys.argv[1]), load(sys.argv[2])
for name, k in [("wall_s", "wall_s"), ("prompt_s", "prompt_s"), ("eval_s", "eval_s")]:
    a, b = [r[k] for r in A], [r[k] for r in B]
    print(f"{name:9s} median on={s.median(a):.3f} off={s.median(b):.3f} diff={(s.median(b)-s.median(a))/s.median(a)*100:+.1f}%")
pa = [r["prompt_tokens"] / r["prompt_s"] for r in A]; pb = [r["prompt_tokens"] / r["prompt_s"] for r in B]
print(f"prefill tok/s median on={s.median(pa):.0f} off={s.median(pb):.0f}")
ea = [r["eval_tokens"] / r["eval_s"] for r in A]; eb = [r["eval_tokens"] / r["eval_s"] for r in B]
print(f"decode tok/s median on={s.median(ea):.1f} off={s.median(eb):.1f}")
print("same prompt tokens per i:", all(x["prompt_tokens"] == y["prompt_tokens"] for x, y in zip(A, B)))
print("eval tokens total on/off:", sum(r["eval_tokens"] for r in A), sum(r["eval_tokens"] for r in B))
print("footprint first/last on:", A[0]["footprint_mb"], A[-1]["footprint_mb"], " off:", B[0]["footprint_mb"], B[-1]["footprint_mb"])
print("pressure after (set) on:", sorted({r["pressure_after"] for r in A}), " off:", sorted({r["pressure_after"] for r in B}))
