#!/bin/bash
# s.sh '<json>' : a beat, then just the state lines and the key events
cd "$(dirname "$0")"
./step.sh "$1" > last.txt 2>&1
grep -E "^(Nocturne|Ripples):|ON THE GROUND|PINNED|staggered|STAGGER|⚠|Error|Traceback|ValueError|KNOCK|📌|🔒|breaks free|Winner|faints|ADRENALINE|CLASH|🧗|→ (she stumbles|it moves her|KNOCKED|DODGED|she falls|she catches)" last.txt | grep -v "can be pinned now: YES; if" | cut -c1-170 | head -16
