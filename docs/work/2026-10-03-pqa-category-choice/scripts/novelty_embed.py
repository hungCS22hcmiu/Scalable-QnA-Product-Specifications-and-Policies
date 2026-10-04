"""Embedding-based novelty: of the first N questions about a product, how many have no earlier
question at cosine >= tau? Frozen nomic-embed-text, 'search_query: ' prefix as in
gateway/internal/embed/client.go. Exploratory (author-approved under yellow pressure) -- not citable."""

import hashlib
import json
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import pqa_category_probe as P  # noqa: E402

RAW = Path("/Users/hung/Desktop/Sem1/thesis/data/raw/pqa")
LEAVES = ["unlocked_cell_phones", "traditional_laptops", "led_&_lcd_tvs", "over-ear_headphones",
          "chairs", "home_office_desks"]
SAMPLE, N, TAUS, NS = 150, 100, [0.80, 0.85, 0.90, 0.95], [10, 20, 50, 100]
PREFIX = "search_query: "


def embed(texts, batch=128):
    out = []
    for i in range(0, len(texts), batch):
        body = json.dumps({"model": "nomic-embed-text", "input": [PREFIX + t for t in texts[i:i + batch]]})
        req = urllib.request.Request("http://localhost:11434/api/embed", body.encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            out.extend(json.load(r)["embeddings"])
    e = np.asarray(out, dtype=np.float32)
    assert e.shape[1] == 768, e.shape
    return e / np.linalg.norm(e, axis=1, keepdims=True)


def lexical_new(qs):
    toks, new = [P.content_tokens(q) for q in qs], []
    for i, a in enumerate(toks):
        new.append(not any(a and b and (a == b or P.ND_LO <= P.jaccard(a, b) <= P.ND_HI) for b in toks[:i]))
    return np.array(new)


results, examples = {}, {}
t0 = time.time()
for leaf in LEAVES:
    rows = defaultdict(list)
    for line in open(RAW / f"amazon_pqa_{leaf}.json", "rb"):
        r = json.loads(line)
        q = (r.get("question_text") or "").strip()
        if r.get("asin") and q:
            rows[r["asin"]].append(q)
    asins = sorted((a for a, v in rows.items() if len(v) >= N),
                   key=lambda a: hashlib.sha1(a.encode()).hexdigest())[:SAMPLE]
    qs_all = [rows[a][:N] for a in asins]
    emb = embed([q for qs in qs_all for q in qs])
    per = {("emb", t, n): [] for t in TAUS for n in NS} | {("lex", None, n): [] for n in NS}
    ex = []
    for k, qs in enumerate(qs_all):
        e = emb[k * N:(k + 1) * N]
        s = e @ e.T
        prev_max = np.array([s[i, :i].max() if i else -1.0 for i in range(N)])
        lex = lexical_new(qs)
        for n in NS:
            per[("lex", None, n)].append(int(lex[:n].sum()))
            for t in TAUS:
                per[("emb", t, n)].append(int((prev_max[:n] < t).sum()))
        # pairs the embedding merges at >= 0.90 that the lexical test does not
        if len(ex) < 8:
            for i in range(1, N):
                j = int(s[i, :i].argmax())
                if s[i, j] >= 0.90 and lex[i] and P.jaccard(P.content_tokens(qs[i]), P.content_tokens(qs[j])) < P.ND_LO:
                    ex.append((round(float(s[i, j]), 3), qs[j][:70], qs[i][:70]))
                    break
    results[leaf] = {f"{m}|{t}|{n}": float(np.mean(v)) for (m, t, n), v in per.items()}
    results[leaf]["products"] = len(asins)
    examples[leaf] = ex
    print(f"{leaf}: {len(asins)} products, {emb.shape[0]} embeddings, {time.time()-t0:.0f}s", flush=True)

(HERE / "novelty_embed.json").write_text(json.dumps({"results": results, "examples": examples}, indent=1))
print("\nNEW questions per 100 (first 100 questions per product) — lower = more re-asking")
print(f"{'leaf':22}{'n':>5}{'lexical':>9}" + "".join(f"{'cos>='+str(t):>11}" for t in TAUS))
for leaf, r in results.items():
    print(f"{leaf:22}{r['products']:>5}{r['lex|None|100']:>9.1f}" + "".join(f"{r[f'emb|{t}|100']:>11.1f}" for t in TAUS))
print("\ncurve at cos>=0.90:  new/10  new/20  new/50  new/100")
for leaf, r in results.items():
    print(f"  {leaf:22}" + "".join(f"{r[f'emb|0.9|{n}']:>8.1f}" for n in NS))
print("\nmerged by embedding (>=0.90) but NOT by the lexical test:")
for leaf, ex in examples.items():
    for s, a, b in ex[:3]:
        print(f"  [{leaf[:12]}] {s}  {a!r}  ~  {b!r}")
