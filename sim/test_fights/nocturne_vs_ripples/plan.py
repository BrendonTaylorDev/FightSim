"""Replay script.json in the real engine (narrator skipped) and, for the LAST beat, build the narrator's notes.
Writes out/beatNN.txt (console), out/notesNN.txt (the narrator's prompts), out/snapNN.json, and prints the
director's view of the fight as it now stands so the next beat can be chosen.
    python3 plan.py <seed> [show-only]"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/user/FightSim/sim")
import harness as H
SEED = int(sys.argv[1])
script = json.load(open(os.path.join(HERE, "script.json")))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
s = H.session(SEED, scene="14", fighters="Nocturne,Ripples", settings=[])
real = s.narrator.narrate
n = len(script)
ALL = len(sys.argv) > 2 and sys.argv[2] == "all"
NONE = len(sys.argv) > 2 and sys.argv[2] == "none"
for i, b in enumerate(script, 1):
    if (i < n and not ALL) or NONE:
        s.narrator.narrate = lambda *a, **k: "(skipped)"
    else:
        s.narrator.narrate = real
    if b == "aftermath":             # after the win: Enter, no attack (the aftermath beat)
        out, caps = H.beat(s, None, [], roll=False)
        open(os.path.join(OUT, f"beat{i:02d}.txt"), "w").write(out)
        if ALL or (i == n and not NONE):
            with open(os.path.join(OUT, f"notes{i:02d}.txt"), "w") as fh:
                for m in caps:
                    fh.write("\n=========== CALL\n")
                    for x in m:
                        fh.write(f"--- {x['role']}\n{x['content']}\n")
        json.dump(H.play.fight_snapshot(s), open(os.path.join(OUT, f"snap{i:02d}.json"), "w"))
        continue
    if isinstance(b, dict):          # {"commands": [...typed before the beat], "actions": [...]}
        for c in b.get("commands") or []:
            H.play.handle_command(s, c)
        b = b["actions"]
    out, caps = H.beat(s, b, [])
    open(os.path.join(OUT, f"beat{i:02d}.txt"), "w").write(out)
    if ALL or (i == n and not NONE):
        with open(os.path.join(OUT, f"notes{i:02d}.txt"), "w") as fh:
            for m in caps:
                fh.write("\n=========== CALL\n")
                for x in m:
                    fh.write(f"--- {x['role']}\n{x['content']}\n")
    json.dump(H.play.fight_snapshot(s), open(os.path.join(OUT, f"snap{i:02d}.json"), "w"))
print("OVER" if s.over else "", "beats:", n)
print(s.eng.director_view())
