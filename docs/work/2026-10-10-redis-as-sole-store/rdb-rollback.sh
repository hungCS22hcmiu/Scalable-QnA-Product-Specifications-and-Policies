#!/bin/bash
set -u
SP="$1"
BIN=/opt/homebrew/Caskroom/redis-stack-server/7.4.0-v8/bin/redis-server
P=6399
r() { redis-cli -p $P "$@"; }

pkill -f "redis-server \*:$P" 2>/dev/null
sleep 0.5
rm -f "$SP/redistest"/*.rdb
mkdir -p "$SP/redistest"

# save '' => NO automatic snapshots. Every snapshot below is explicit, so the timeline is controlled.
"$BIN" --port $P --dir "$SP/redistest" --dbfilename t.rdb --appendonly no --save '' --daemonize yes
sleep 1
echo "ping: $(r PING)   (isolated instance on :$P -- project Redis on :6379 untouched)"

echo
echo "=== t0: entry A + its dep record + corpus chunk + epoch=7, then explicit SNAPSHOT ==="
r HSET t2:entryA answer "pre-edit answer" t1_key "t1:hashA" dataset_epoch 7 >/dev/null
r SADD 'dep:policy-returns#chunk-0' entryA >/dev/null
r SET 'corpus::policy-returns#chunk-0' "pre-edit corpus text" >/dev/null
r SET epoch_counter 7 >/dev/null
r SAVE >/dev/null
echo "snapshot taken (LASTSAVE=$(r LASTSAVE))"

echo
echo "=== t1: AFTER the snapshot -- a source edit fires: epoch advances, purge deletes A, B written ==="
r SET epoch_counter 8 >/dev/null
r SET 'corpus::policy-returns#chunk-0' "EDITED corpus text" >/dev/null
r DEL t2:entryA >/dev/null
r SREM 'dep:policy-returns#chunk-0' entryA >/dev/null
r HSET t2:entryB answer "post-edit answer" t1_key "t1:hashB" dataset_epoch 8 >/dev/null
r SADD 'dep:policy-returns#chunk-0' entryB >/dev/null

echo "state immediately BEFORE the crash:"
printf '  %-36s exists=%s\n' "t2:entryA (purged)"  "$(r EXISTS t2:entryA)"
printf '  %-36s exists=%s\n' "t2:entryB (new)"     "$(r EXISTS t2:entryB)"
printf '  %-36s %s\n'        "epoch_counter"        "$(r GET epoch_counter)"
printf '  %-36s %s\n'        "corpus chunk text"    "$(r GET 'corpus::policy-returns#chunk-0')"
printf '  %-36s [%s]\n'      "dep set members"      "$(r SMEMBERS 'dep:policy-returns#chunk-0' | tr '\n' ' ')"

echo
echo "=== CRASH: kill -9, no shutdown, no final snapshot ==="
PID=$(r INFO server | awk -F: '/^process_id/{print $2}' | tr -d '\r')
kill -9 "$PID"
sleep 1
redis-cli -p $P PING 2>&1 | head -1

echo
echo "=== RESTART from t.rdb ==="
"$BIN" --port $P --dir "$SP/redistest" --dbfilename t.rdb --appendonly no --save '' --daemonize yes
sleep 1
echo "state AFTER restart:"
printf '  %-36s exists=%s\n' "t2:entryA (was purged!)" "$(r EXISTS t2:entryA)"
printf '  %-36s exists=%s\n' "t2:entryB (was new)"     "$(r EXISTS t2:entryB)"
printf '  %-36s %s\n'        "epoch_counter"            "$(r GET epoch_counter)"
printf '  %-36s %s\n'        "corpus chunk text"        "$(r GET 'corpus::policy-returns#chunk-0')"
printf '  %-36s [%s]\n'      "dep set members"          "$(r SMEMBERS 'dep:policy-returns#chunk-0' | tr '\n' ' ')"
printf '  %-36s %s\n'        "entryA.dataset_epoch"     "$(r HGET t2:entryA dataset_epoch)"

echo
echo "=== teardown ==="
r SHUTDOWN NOSAVE 2>/dev/null
sleep 0.5
redis-cli -p $P PING 2>&1 | head -1
echo "project Redis on :6379 still up? $(redis-cli -p 6379 PING 2>&1 | head -1)"
