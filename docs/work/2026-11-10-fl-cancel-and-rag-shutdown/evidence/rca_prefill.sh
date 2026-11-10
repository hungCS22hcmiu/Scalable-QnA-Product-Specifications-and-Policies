#!/usr/bin/env bash
# RCA for plan.md step 4.2 (DC 5 still shows a 1.26 s gap after the fix), 2026-11-10. citable: no.
# Straight to Ollama: no gateway, no rag.server.
#
# Hypothesis: the runner (llama-server under Ollama 0.33.2, -b 1024 -ub 1024) acts on a cancel only
# between its update steps. A prompt of at most 1024 tokens is prefilled in ONE decode call, so a
# client that leaves during prefill still holds the one slot until prefill ends. A cut that lands in
# decoding frees the slot within one token.
#
#   0. Build A's exact served prompt: rag.retrieve.retrieve(A, top_k=TOP_K, product_id=PRODUCT) and
#      rag.generate._build_prompt. The body carries corpus text (Amazon-PQA, redistribution not
#      granted), so it is written to WORK, outside the repository; only its hash and sizes print here.
#   1. A once, uncut: prompt_eval_count/duration, eval_count/duration, total_duration.
#   2. B alone, 3 times (and 3 more at the end).
#   3. Cuts, 3 repetitions each: curl --max-time T on A, then B at once (as fl_probe.sh does).
#      (a) T = 1.0 s   (c) T = halfway between 1.0 s and the end of prefill   (b) T = prefill end + 1.0 s
#      After each, the runner's own log lines for that cut (prompt size, cancel, release point).
# Pressure is read before every command that calls Ollama; 4 stops the script.
#
# Usage: bash rca_prefill.sh WORKDIR   (WORKDIR outside the repository)
set -u

ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
WORK=${1:?usage: rca_prefill.sh WORKDIR -- outside the repo, it holds the body of A, which carries corpus text}
mkdir -p "$WORK"
OLLAMA=http://localhost:11434/api/generate
LOG=$HOME/.ollama/logs/server.log
PRODUCT=product-laptops-b07qvm5x8w
A_Q="Explain in full detail every specification of this laptop, one by one, and what each means for a buyer, then its return and warranty policy."
B='{"model":"qwen3.5:2b-q4_K_M","prompt":"Reply with exactly one word: OK.","stream":false,"think":false,"options":{"num_ctx":8192}}'
REPS=3

gate() {
  local p
  p=$(sysctl -n kern.memorystatus_vm_pressure_level)
  echo "  [pressure before $1: $p]"
  if [ "$p" = 4 ]; then echo "STOP: pressure 4 (red)"; exit 2; fi
}
timeB() { curl -s -o /dev/null -w '%{time_total}' -X POST "$OLLAMA" -d "$B"; }
median() { python3 -c 'import statistics,sys; v=[float(x) for x in sys.argv[1:]]; print(f"{statistics.median(v):.3f}")' "$@"; }
runner_lines() {  # the runner's lines since line $1, without any prompt text
  tail -n +"$(($1 + 1))" "$LOG" | grep -E 'task\.n_tokens|stop: cancel task|stop processing|GIN.*/api/generate' \
    | sed -E 's/^slot +//; s/^srv +//' | sed 's/^/    log: /'
}

echo "rca_prefill.sh, $(date '+%Y-%m-%d %H:%M:%S'), citable: no"
echo "runner: $(ps -axo command | grep -E 'llama-server.*-c 8192' | grep -v grep | grep -oE '(-c|-np|-b|-ub) [0-9]+' | tr '\n' ' ')"

# 0. A's exact prompt.
echo "== 0. A's prompt, built as rag.server builds it"
gate "retrieval (embeds the query)"
(cd "$ROOT/rag" && PYTHONPATH=src python3 - "$A_Q" "$PRODUCT" "$WORK/a_body.json" <<'EOF'
import hashlib
import json
import sys

from rag import config, generate, retrieve

query, product, out = sys.argv[1:4]
chunks, ep = retrieve.retrieve(query, top_k=config.TOP_K, product_id=product)
prompt = generate._build_prompt(query, chunks)
body = {"model": "qwen3.5:2b-q4_K_M", "prompt": prompt, "stream": False, "think": False,
        "options": {"num_ctx": 8192}}
assert body == generate._request_body(query, chunks), "body differs from the served one"
with open(out, "w") as f:
    json.dump(body, f)
print(f"  chunks ({len(chunks)}): {[c.chunk_id for c in chunks]}")
print(f"  epoch {ep}; prompt {len(prompt)} chars, sha256 {hashlib.sha256(prompt.encode()).hexdigest()}")
print("  body == generate._request_body(query, chunks): True")
EOF
) || { echo "STOP: could not build A's prompt"; exit 1; }

# 1. A uncut.
echo "== 1. A once, uncut, straight to Ollama"
gate "A uncut"
curl -s -o "$WORK/a_uncut.json" -w '  curl time_total %{time_total} s\n' -X POST "$OLLAMA" -d @"$WORK/a_body.json"
read -r PE_COUNT PE_S EV_COUNT EV_S TOT_S LOAD_S PF_END < <(python3 - "$WORK/a_uncut.json" <<'EOF'
import json
import sys

r = json.load(open(sys.argv[1]))
ns = 1e9
pf_end = (r["total_duration"] - r["eval_duration"]) / ns  # request start -> end of prefill, per Ollama
print(r["prompt_eval_count"], f'{r["prompt_eval_duration"] / ns:.3f}', r["eval_count"],
      f'{r["eval_duration"] / ns:.3f}', f'{r["total_duration"] / ns:.3f}',
      f'{r["load_duration"] / ns:.3f}', f"{pf_end:.3f}")
EOF
)
echo "  prompt_eval_count $PE_COUNT, prompt_eval_duration $PE_S s ($(python3 -c "print(f'{$PE_COUNT/$PE_S:.0f}')") tok/s)"
echo "  eval_count $EV_COUNT, eval_duration $EV_S s ($(python3 -c "print(f'{$EV_COUNT/$EV_S:.1f}')") tok/s)"
echo "  total_duration $TOT_S s, load_duration $LOAD_S s"
echo "  prefill ends at about $PF_END s after the request starts (total_duration - eval_duration)"

# 2. B alone.
echo "== 2. B alone"
alone=()
for i in $(seq "$REPS"); do gate "B alone #$i"; t=$(timeB); alone+=("$t"); echo "  B alone #$i: $t s"; done

# 3. Cuts.
T_A=1.0
T_C=$(python3 -c "print(f'{(1.0 + $PF_END) / 2:.2f}')")
T_B=$(python3 -c "print(f'{$PF_END + 1.0:.2f}')")
declare -a res_a res_c res_b
cut() {  # $1 label, $2 T
  local label=$1 T=$2 i n0 ta tb
  echo "== 3($label). T = $T s: A cut at T, then B at once; predicted gap = max(0, $PF_END - T)"
  for i in $(seq "$REPS"); do
    gate "cut $label #$i"
    n0=$(wc -l < "$LOG")
    ta=$(curl -s -o /dev/null --max-time "$T" -w '%{time_total}' -X POST "$OLLAMA" -d @"$WORK/a_body.json")
    tb=$(timeB)
    echo "  #$i: A held $ta s, B after $tb s"
    runner_lines "$n0"
    eval "res_$label+=(\"$tb\")"
  done
}
cut a "$T_A"
cut c "$T_C"
cut b "$T_B"

echo "== 2'. B alone, again"
for i in $(seq "$REPS"); do gate "B alone (end) #$i"; t=$(timeB); alone+=("$t"); echo "  B alone (end) #$i: $t s"; done

# Result.
m_alone=$(median "${alone[@]}")
echo "== Result (citable: no)"
echo "  B alone, median of ${#alone[@]}: $m_alone s"
for label in a c b; do
  eval "vals=(\"\${res_$label[@]}\")"
  eval "T=\$T_$(echo $label | tr a-c A-C)"
  m=$(median "${vals[@]}")
  gap=$(python3 -c "print(f'{$m - $m_alone:.3f}')")
  pred=$(python3 -c "print(f'{max(0.0, $PF_END - $T):.3f}')")
  echo "  ($label) T = $T s: B after, median of ${#vals[@]}: $m s; gap $gap s; predicted $pred s"
done
echo "  pressure at end: $(sysctl -n kern.memorystatus_vm_pressure_level)"
