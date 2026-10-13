#!/bin/bash
# step.sh '<json>' : add a beat, show the short state and the rolls
cd "$(dirname "$0")"
n=$(python3 -c "import json;print(len(json.load(open('script.json')))+1)")
python3 add.py "$1" 2>&1 | grep -v "can be pinned\|^PINS\|^POSITIONS\|IN THE AIR\|^ACTIVE HOLDS: none" | tail -12
f=$(printf "out/beat%02d.txt" $n)
grep -n "rolled\|🪽\|🦅\|🌋\|KNOCKOUT\|📌\|🧗" $f | grep -v "the shelf doing something by itself.*nothing" | head -24
