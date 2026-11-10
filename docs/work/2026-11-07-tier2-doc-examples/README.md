# Tier 2 doc examples — live run of 7 Nov 2026

**What:** the run behind the worked examples of `docs/1-System Docs/Tier 2.md` §9, §10 and §11a. It is a
doc edit, not a super-plan task. **Citable: no.** This was a functional run (`make dev`, evaluation log
off), and memory pressure was 2 (yellow) for every request.

**Setting:** corpus `v1`, code at commit `d642c45` (retrieval with ADR-020 and ADR-021), epoch 2,
τ = 0.85, `SUPPORT_GATE=on`, MIXED off, cache capacity unbounded.

**How it ran:**
1. `make cache-reset`, with no gateway running. It deleted 213 `t1:`, 166 `t2:`, 167 `lru:`, 315 `dep:`
   and 538 `entry:` keys. The 539 `corpus:` keys and both indexes stayed.
2. `make dev`, with its output redirected to `dev.log`. `evidence/gateway.log` is that file without
   the `redisvl` INFO lines.
3. `./ask.sh <label> "<question>" <product_id>` for each request, in the order of `evidence/responses.jsonl`.
   The script reads `dev.log` from this folder.
4. `python3 details.py lex sim` and `python3 details.py ret` (run from `rag/`). These are read-only
   checks, and their output is below.

**Files:**
- `evidence/gateway.log`: the cascade line of every judged candidate, with its cause and `S_lex`.
- `evidence/responses.jsonl`: the 12 HTTP responses, with their answers.
- `evidence/t2-state.txt`: the 8 Tier-2 entries the run left behind.

## Output of `details.py`

The gate's words. They reproduce every `S_lex` in the gateway log.

```
[A3 judged A1's entry] content=32 found=18 lex=0.5625
   missing: according cases coverable get like mail packaging receipt receiving require returned specific via yes
[A5 judged A1's entry] content=32 found=18 lex=0.5625   (same missing words)
[B3 judged B2's entry] content=38 found=33 lex=0.8684
   missing: automatically failing like specifically though
[B4 judged B2's entry] content=38 found=32 lex=0.8421
   missing: automatically failing like soundcore specifically though
[D2 judged D1's entry] content=11 found=10 lex=0.9091
   missing: card
"soundcore" appears only in product-electronics-b07zj7qg33#chunk-1
```

Question similarities. `nomic-embed-text` with the `search_query: ` prefix, as the gateway embeds them.

```
A1-A3 0.9932   A1-A4 0.8469   A1-B1 0.8206   A1-B2 0.7293   B1-B2 0.8043
B2-B3 0.9256   A1-B3 0.6981   D1-D2 0.9105   D1-D3 0.7821   D2-D3 0.7553
```

Retrieval, without and with `product_id` (score, chunk). The gateway got the "with" lists.

```
A1 without: 0.7763 policy-return-electronics#0 · 0.7308 #1 · 0.7190 #2 · 0.7029 policy-return-laptops-new#0 · 0.6996 policy-return-phones-opened#0
A1 with:    0.6166 product-electronics-b07zj7qg33#1 · 0.7763 policy-return-electronics#0 · 0.7308 #1 · 0.7190 #2 · 0.6735 policy-warranty-electronics#2
A4 without: 0.7448 policy-return-furniture-opened#0 · 0.7325 unopened#0 · 0.7088 opened#2 · 0.7066 unopened#2 · 0.7038 unopened#1
A4 with:    0.6134 product-furniture-b019x98zxm#0 · 0.7448 opened#0 · 0.7325 unopened#0 · 0.7088 opened#2 · 0.7066 unopened#2
B2 without: 0.7788 policy-warranty-electronics#0 · 0.7225 product-electronics-b07b63r768#2 · 0.7112 policy-warranty-phones-domestic#0 · 0.7091 product-electronics-b081pspwj9#2 · 0.7089 policy-warranty-laptops#0
B2 with:    0.6781 product-electronics-b07zj7qg33#1 · 0.7788 policy-warranty-electronics#0 · 0.6904 policy-return-electronics#0 · 0.6674 policy-warranty-electronics#1
D1 without: 0.7710 product-laptops-b01ld4mgoy#0 · 0.7659 product-laptops-b00ep09b4m#0 · 0.7617 product-laptops-b01bm8g3uy#0 · 0.7504 product-laptops-b07qvm5x8w#0 · 0.7473 product-laptops-b07bp9b1nt#0
D1 with:    0.7504 product-laptops-b07qvm5x8w#0 · 0.6400 #1 · 0.6377 #2
```

The model words its answers differently on each run, so a re-run gives other answers and other `S_lex`
values. Retrieval, lanes and namespaces should repeat. Which entries exist, and so which candidate a
later question meets, can change.

## Example E — the MIXED lane (same day, second run)

The run behind Tier 2.md §11b. It is still **citable: no**. Memory pressure was 1 for the first request
and 2 for the rest.

1. `python3 mixed_probe.py`, from `rag/`. This read-only probe found questions that land in MIXED. The
   battery and warranty questions retrieve 2 chunks (fraction 0.50, MIXED). A GPU and return question on
   the laptop has 4 of 5 policy chunks (0.80, POLICY). A warranty and Bluetooth question on H1 has no
   policy chunk (SPEC).
2. **On arm.** `make cache-reset`, then `make dev` with nothing set: the gateway logged
   `lane_band=[0.20,0.60) mixed_lane=on`. Then E1 to E5. Files: `evidence/mixed-on-gateway.log` and
   `evidence/mixed-on-t2-state.txt`.
3. **Off arm.** Stop, `make cache-reset`, then `LANE_SIGMA_HI=0.20 make dev`. Then F1 (E1's question on
   H1) and F3 (the same words on H2). File: `evidence/mixed-off-gateway.log`.

All seven responses are in `evidence/mixed-responses.jsonl`.

**The gate's words** (they reproduce the log):
- E2 and E4 judged E1's answer: 30/43 = 0.6977.
- F3 judged F1's answer: 10/15 = 0.6667, but the numeric arm failed. F1 says "4 hours" and "60 hours",
  and H2's chunk has neither (it says 30 hours).
