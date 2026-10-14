import json, re, sys
rows = [json.loads(m.group(1)) for l in open(sys.argv[1], encoding="utf-8") for m in [re.search(r"SAMPLE (\{.*\})\s*$", l)] if m]
by = {}
for r in rows:
    by[(r["ID"], "own" if r["Kind"]=="own" else ("paraphrase" if r["Kind"]=="paraphrase" else "c"))] = r
def show(i, k, n=330):
    r = by[(i, k)]
    print(f'\n[{i} {r["Kind"]}] Q: {r["Question"]}')
    if r["EvidenceQuestion"]: print(f'   evidence from: {r["EvidenceQuestion"]}')
    print(f'   S_lex={r["LexScore"]:.3f}/{r["LexContentTokens"]} numRef={r["NumRefuses"]}  evidence={r["EvidenceChunks"]}')
    print(f'   A: {r["Answer"][:n].strip()!r}')
for i, k in [("a03","own"),("a15","own"),("a12","own"),("a01","own"),("c1","c"),("c2","c"),("c3","c"),("c4","c"),("c5","c"),("c6","c")]:
    show(i, k)
print("\n=== same-evidence check (the answered question's own chunks, from part a, same question text) ===")
for c, a in [("c1","a01"),("c4","a09"),("c5","a07")]:
    ev_c = set(by[(c,"c")]["EvidenceChunks"])
    ev_a = set(by[(a,"own")]["EvidenceChunks"])
    print(f'{c} evidence(p) vs {a} own(q): identical={ev_c==ev_a}  shared={sorted(ev_c&ev_a)}  only_p={sorted(ev_c-ev_a)}  only_q={sorted(ev_a-ev_c)}')
print("\n=== part b: is the paraphrase retrieval the same chunks as the question's own? ===")
for i in ["b1","b2","b3","b4","b5"]:
    o, p = by[(i,"own")], by[(i,"paraphrase")]
    print(i, "same chunks:", o["EvidenceChunks"]==p["EvidenceChunks"], len(o["EvidenceChunks"]), "chunks")
