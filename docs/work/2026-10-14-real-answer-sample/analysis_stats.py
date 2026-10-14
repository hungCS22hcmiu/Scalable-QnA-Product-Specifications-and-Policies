import json, re, sys, math
rows = [json.loads(m.group(1)) for l in open(sys.argv[1], encoding="utf-8") for m in [re.search(r"SAMPLE (\{.*\})\s*$", l)] if m]
def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return max(0.0, c-h), min(1.0, c+h)
floor = [r for r in rows if r["Part"]=="a" or (r["Part"]=="b" and r["Kind"]=="own")]
a = [r for r in rows if r["Part"]=="a"]
b_par = [r for r in rows if r["Part"]=="b" and r["Kind"]=="paraphrase"]
c = [r for r in rows if r["Part"]=="c"]
def rep(name, rs):
    s = sorted(round(r["LexScore"],3) for r in rs)
    below = sum(r["LexRefuses"] for r in rs); num = sum(r["NumRefuses"] for r in rs)
    nl = sum(r["NumericRefusesWhereLexicalAdmit"] for r in rs)
    lo, hi = wilson(below, len(rs)); nlo, nhi = wilson(num, len(rs))
    print(f"{name}: n={len(rs)}  S_lex sorted={s}")
    print(f"   below 0.6: {below}/{len(rs)}  Wilson95 [{lo:.3f}, {hi:.3f}]   numeric refuses: {num}/{len(rs)}  Wilson95 [{nlo:.3f}, {nhi:.3f}]   numeric refuses where lexical admits: {nl}")
    print(f"   exactly at tau_s (0.600): {[r['ID'] for r in rs if abs(r['LexScore']-0.6)<1e-9]}   median={s[len(s)//2]}  min={s[0]}")
rep("floor (a + b own)", floor)
rep("part a only", a)
rep("part b paraphrase (the reuse case)", b_par)
yn = [r for r in a if r["YesNo"]]
print(f"\nyes/no in part a: {[(r['ID'], round(r['LexScore'],3)) for r in yn]}  below 0.6: {sum(r['LexRefuses'] for r in yn)}/{len(yn)}")
print("non-yes/no in part a below 0.6:", [(r['ID'], round(r['LexScore'],3)) for r in a if not r['YesNo'] and r['LexRefuses']])
print("\n--- part c ---")
for r in c:
    print(f"{r['ID']} {r['Kind']:<20} gate-would-refuse={r['LexRefuses'] or r['NumRefuses']} (lex={r['LexRefuses']}, num={r['NumRefuses']})  system-namespaces-equal={r['SameNamespace']}")
ref = [r for r in c if r["LexRefuses"] or r["NumRefuses"]]
print(f"refused by either arm: {len(ref)}/6; admitted: {[r['ID'] for r in c if r not in ref]}")
sn = [r for r in c if r["SameNamespace"]]
print(f"pairs whose namespaces the system really assigned equal (the gate sees them in config 4): {[r['ID'] for r in sn]}  refused: {[r['ID'] for r in sn if r['LexRefuses'] or r['NumRefuses']]}")
print("\n--- does the word 'context' in the answer go with a low S_lex? (all 32 rows; descriptive only) ---")
w = [r for r in rows if re.search(r"\bcontext\b", r["Answer"], re.I)]
wo = [r for r in rows if not re.search(r"\bcontext\b", r["Answer"], re.I)]
avg = lambda rs: sum(r["LexScore"] for r in rs)/len(rs)
print(f"with 'context': n={len(w)} mean S_lex={avg(w):.3f} refused by lexical={sum(r['LexRefuses'] for r in w)}  ids={[r['ID']+('p' if r['Kind']=='paraphrase' else '') for r in w]}")
print(f"without       : n={len(wo)} mean S_lex={avg(wo):.3f} refused by lexical={sum(r['LexRefuses'] for r in wo)}")
print("\nlexical refusals (all rows):", [(r['ID'], r['Kind'][:9], round(r['LexScore'],3), 'context' in r['Answer'].lower()) for r in rows if r['LexRefuses']])

print("\n--- what the numeric arm had to work with (floor rows: part a + part b own) ---")
fl = [r for r in rows if r["Part"]=="a" or (r["Part"]=="b" and r["Kind"]=="own")]
withnum = [r for r in fl if r["NumNumbers"]>0]
unitless = [r for r in fl if r["NumUnitless"]>0]
print(f"answers with at least one number: {len(withnum)}/{len(fl)}   answers with at least one 'unitless' number (checked by value only): {len(unitless)}/{len(fl)}  ids={[r['ID'] for r in unitless]}")
print(f"numbers in total: {sum(r['NumNumbers'] for r in fl)}, unsupported: {sum(r['NumUnsupported'] for r in fl)}, unreadable: {sum(r['NumUnreadable'] for r in fl)}, unitless: {sum(r['NumUnitless'] for r in fl)}")
