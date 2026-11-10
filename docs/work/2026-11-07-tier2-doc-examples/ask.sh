#!/bin/bash
# usage: ask.sh <label> <question> [product_id]
# Sends one /ask, saves the response, prints it and the gateway log lines it caused.
S="$(cd "$(dirname "$0")" && pwd)"
L=$S/dev.log
mkdir -p $S/runs
label=$1; q=$2; pid=$3
before=$(wc -l < $L)
if [ -n "$pid" ]; then
  body=$(jq -nc --arg q "$q" --arg p "$pid" '{question:$q, product_id:$p}')
else
  body=$(jq -nc --arg q "$q" '{question:$q}')
fi
echo "pressure=$(sysctl -n kern.memorystatus_vm_pressure_level)  label=$label  product_id=${pid:-none}"
echo "Q: $q"
curl -sS -X POST localhost:8080/ask -H 'content-type: application/json' -d "$body" > $S/runs/$label.json
jq -c '{cache, latency_ms, similarity, source_overlap, sources}' $S/runs/$label.json
echo "ANSWER: $(jq -r .answer $S/runs/$label.json)"
# give the background writes a moment, then show the new log lines
sleep 1
tail -n +$((before+1)) $L
echo "-----"
