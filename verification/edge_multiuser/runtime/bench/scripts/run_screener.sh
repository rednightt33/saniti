#!/bin/bash
# Fresh-process screener cold starts (data part), sequential so runs do not share CPUs. Output raw/screener_k<K>_r<i>.json
B=/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/mu_runtime/bench
cd $B
N="node --experimental-strip-types --no-warnings --expose-gc --import /home/user/saniti/apps/backtest-worker/loader/register.mjs scripts/screener_cold.mts data/xsection_price.json.gz data/xsection_price.meta.json"
for i in 1 2 3; do node scripts/run_proc.mjs raw/screener_k1_r$i.json ready -1 -- $N --threads 1 --hold $([ $i = 1 ] && echo 60 || echo 0); done
for k in 2 4; do for i in 1 2; do node scripts/run_proc.mjs raw/screener_k${k}_r$i.json ready -1 -- $N --threads $k --hold $([ $i = 1 ] && echo 30 || echo 0); done; done
echo DONE
