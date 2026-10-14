"""Append a beat (a JSON list of actions, from argv[1]) to script.json, play it, and show what happened."""
import sys, json, subprocess, os
H = os.path.dirname(os.path.abspath(__file__))
sc = json.load(open(os.path.join(H, "script.json")))
if sys.argv[1] != "-":
    new = json.loads(sys.argv[1])
    sc.append(new)
    json.dump(sc, open(os.path.join(H, "script.json"), "w"), indent=0)
r = subprocess.run([sys.executable, os.path.join(H, "plan.py"), "202", "none"], capture_output=True, text=True, cwd="/home/user/FightSim")
if r.returncode:
    print(r.stderr[-3000:])
    sys.exit(1)
n = len(sc)
print(subprocess.run([sys.executable, os.path.join(H, "brief.py"), str(n)], capture_output=True, text=True, cwd=H).stdout)
view = r.stdout
# the short state: each fighter's OVERALL line, energy, posture, and her worst parts
import re
for blk in re.split(r"\n(?=\S+ \[)", view):
    m = re.match(r"(\S+) \[.*?OVERALL: ([^\n]*?)\.", blk, re.S)
    if not m:
        continue
    body = re.search(r"body \(resistance%/damage%\): (.*)", blk)
    hurt = []
    if body:
        for p, r_, d in re.findall(r"([A-Z][\w ]+?) (\d+)/(\d+)", body.group(1)):
            if int(d) >= 30:
                hurt.append((int(d), f"{p} {d}%/{r_}"))
    rest = [l.strip() for l in blk.splitlines() if l.strip().startswith(("energy", "ON ", "DOWN", "PINNED", "IN THE", "Status", "status", "CAUGHT", "GUARDING", "STAGGER", "   ")) and "moves:" not in l and "body (" not in l]
    print(f"{m.group(1)}: {m.group(2)} | hurt: " + ", ".join(x for _, x in sorted(hurt, reverse=True)[:6]))
    for l in rest[:6]:
        print("   ", l[:180])
for l in view.splitlines():
    if l.startswith(("ACTIVE HOLDS", "PINS", "POSITIONS")) or "OPENING" in l:
        print(l[:220])
