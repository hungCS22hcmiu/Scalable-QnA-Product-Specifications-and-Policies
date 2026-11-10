#!/usr/bin/env bash
# RCA follow-up to rca_prefill.sh, 2026-11-10. citable: no. Straight to Ollama, the model already loaded.
# rca_prefill.sh's first call paid a 2.87 s model load, so its "predicted" column is wrong; this run
# measures warm prefill first. Two questions:
#   (m) A cut INSIDE prefill at T = 1.5 s. If the runner acts on a cancel only when its one decode call
#       for the prompt ends, the gap is about (prefill end - 1.5) and the slot is released at
#       n_tokens = 987. If instead the runner noticed the close by a 1 s poll, the gap would be near
#       1 s and a few tokens would be decoded (n_tokens > 987).
#   (L) A prompt longer than one batch (-b 1024): A's chunks twice (about 1,970 tokens, two batches).
#       Cut at T = 1.0 s, inside batch 1. Released at n_tokens = 1024: the cancel is honoured at a
#       batch boundary. Released at the full count: only at the end of the prompt.
# Prefill is measured with num_predict 1 (one token after the prompt); the cuts use the served
# options. The bodies carry corpus text and are written to WORK, outside the repository.
# Usage: bash rca_prefill2.sh WORKDIR
set -u

ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
WORK=${1:?usage: rca_prefill2.sh WORKDIR -- outside the repo}
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
runner_lines() {
  tail -n +"$(($1 + 1))" "$LOG" | grep -E 'task\.n_tokens|stop: cancel task|stop processing|GIN.*/api/generate' \
    | sed -E 's/^slot +//; s/^srv +//' | sed 's/^/    log: /'
}
prefill() {  # $1 body file: one call with num_predict 1, prints count, prefill s, load s, total s
  python3 - "$1" "$WORK/pf_body.json" <<'EOF'
import json, sys
b = json.load(open(sys.argv[1])); b["options"] = dict(b["options"], num_predict=1)
json.dump(b, open(sys.argv[2], "w"))
EOF
  curl -s -o "$WORK/pf.json" -X POST "$OLLAMA" -d @"$WORK/pf_body.json"
  python3 - "$WORK/pf.json" <<'EOF2'
import json, sys
r = json.load(open(sys.argv[1]))
n = 1e9
print(r["prompt_eval_count"], f'{r["prompt_eval_duration"] / n:.3f}', f'{r["load_duration"] / n:.3f}',
      f'{r["total_duration"] / n:.3f}')
EOF2
}

echo "rca_prefill2.sh, $(date '+%Y-%m-%d %H:%M:%S'), citable: no"
echo "runner: $(ps -axo command | grep 'llama-server' | grep 'sha256-7a3a8d55' | grep -oE ' (-c|-np|-b|-ub) [0-9]+' | tr '\n' ' ')"

echo "== 0. bodies (A as served; L = A's chunks twice), written to WORK"
gate "retrieval (embeds the query)"
(cd "$ROOT/rag" && PYTHONPATH=src python3 - "$A_Q" "$PRODUCT" "$WORK" <<'EOF'
import hashlib, json, sys
from rag import config, generate, retrieve
query, product, work = sys.argv[1:4]
chunks, _ = retrieve.retrieve(query, top_k=config.TOP_K, product_id=product)
for name, cs in (("a", chunks), ("long", chunks + chunks)):
    body = generate._request_body(query, cs)
    json.dump(body, open(f"{work}/{name}_body.json", "w"))
    p = body["prompt"]
    print(f"  {name}: {len(cs)} chunks, {len(p)} chars, sha256 {hashlib.sha256(p.encode()).hexdigest()[:16]}")
EOF
) || { echo "STOP: could not build the bodies"; exit 1; }

echo "== 1. warm-up B, then warm prefill of each prompt (num_predict 1)"
gate "warm-up B"; echo "  warm-up B: $(timeB) s"
gate "prefill A"; read -r A_N A_PF A_LOAD A_TOT < <(prefill "$WORK/a_body.json")
echo "  A:    prompt_eval_count $A_N, prompt_eval_duration $A_PF s, load $A_LOAD s, total $A_TOT s"
gate "prefill L"; read -r L_N L_PF L_LOAD L_TOT < <(prefill "$WORK/long_body.json")
echo "  L:    prompt_eval_count $L_N, prompt_eval_duration $L_PF s, load $L_LOAD s, total $L_TOT s"

echo "== 2. B alone"
alone=()
for i in $(seq "$REPS"); do gate "B alone #$i"; t=$(timeB); alone+=("$t"); echo "  B alone #$i: $t s"; done

declare -a res_m res_L
cut() {  # $1 label, $2 body, $3 T
  local label=$1 body=$2 T=$3 i n0 ta tb
  for i in $(seq "$REPS"); do
    gate "cut $label #$i"
    n0=$(wc -l < "$LOG")
    ta=$(curl -s -o /dev/null --max-time "$T" -w '%{time_total}' -X POST "$OLLAMA" -d @"$body")
    tb=$(timeB)
    echo "  #$i: A held $ta s, B after $tb s"
    runner_lines "$n0"
    eval "res_$label+=(\"$tb\")"
  done
}
echo "== 3(m). A cut at T = 1.5 s (inside its prefill)"
cut m "$WORK/a_body.json" 1.5
echo "== 3(L). L cut at T = 1.0 s (inside its first batch)"
cut L "$WORK/long_body.json" 1.0

m_alone=$(median "${alone[@]}")
m_m=$(median "${res_m[@]}"); m_L=$(median "${res_L[@]}")
echo "== Result (citable: no)"
echo "  B alone, median of ${#alone[@]}: $m_alone s"
echo "  (m) A at T = 1.5 s: B after, median $m_m s; gap $(python3 -c "print(f'{$m_m - $m_alone:.3f}')") s; if the runner waits for the end of prefill: about $(python3 -c "print(f'{$A_TOT - 1.5:.3f}')") s (A's warm total with num_predict 1, minus 1.5)"
echo "  (L) L at T = 1.0 s: B after, median $m_L s; gap $(python3 -c "print(f'{$m_L - $m_alone:.3f}')") s; whole prompt would give about $(python3 -c "print(f'{$L_TOT - 1.0:.3f}')") s; first batch only about $(python3 -c "print(f'{$L_PF * 1024 / $L_N - 1.0:.3f}')") s (linear share of 1024 tokens)"
echo "  pressure at end: $(sysctl -n kern.memorystatus_vm_pressure_level)"
