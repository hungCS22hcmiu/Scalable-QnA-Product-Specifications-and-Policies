"""What does each cosine band actually merge? Earlier-question pairs per band, small sample. Scratch."""
import hashlib
import json
import random
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np

RAW = Path("/Users/hung/Desktop/Sem1/thesis/data/raw/pqa")


def embed(texts):
    out = []
    for i in range(0, len(texts), 128):
        body = json.dumps({"model": "nomic-embed-text", "input": ["search_query: " + t for t in texts[i:i + 128]]})
        req = urllib.request.Request("http://localhost:11434/api/embed", body.encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            out.extend(json.load(r)["embeddings"])
    e = np.asarray(out, dtype=np.float32)
    return e / np.linalg.norm(e, axis=1, keepdims=True)


BANDS = [(0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1.01)]
rnd = random.Random(20261003)
for leaf in sys.argv[1:]:
    rows = defaultdict(list)
    for line in open(RAW / f"amazon_pqa_{leaf}.json", "rb"):
        r = json.loads(line)
        q = (r.get("question_text") or "").strip()
        if r.get("asin") and q:
            rows[r["asin"]].append(q)
    asins = sorted((a for a, v in rows.items() if len(v) >= 100),
                   key=lambda a: hashlib.sha1(a.encode()).hexdigest())[:10]
    pairs = defaultdict(list)
    for a in asins:
        qs = rows[a][:100]
        s = embed(qs)
        s = s @ s.T
        for i in range(1, 100):
            j = int(s[i, :i].argmax())
            for lo, hi in BANDS:
                if lo <= s[i, j] < hi:
                    pairs[(lo, hi)].append((round(float(s[i, j]), 3), qs[j][:62], qs[i][:62]))
    print(f"\n######## {leaf} (10 products x 100 questions; each question vs its most similar EARLIER one)")
    for b in BANDS:
        ps = pairs[b]
        print(f"--- cos [{b[0]:.2f}, {min(b[1],1):.2f}): {len(ps)} questions; 6 random:")
        for p in rnd.sample(ps, min(6, len(ps))):
            print(f"   {p[0]}  {p[1]!r}  ~  {p[2]!r}")
