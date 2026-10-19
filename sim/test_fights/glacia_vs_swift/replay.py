"""Replay the scripted fight with the hand-written narration as the narrator's text, then export it."""
import sys, os, json, re
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/user/FightSim/sim")
import harness as H
G, W = "Glacia", "Swift"
def A(att, action, **k):
    k["attacker"] = att; k["action"] = action
    k.setdefault("defender", W if att == G else G); k.setdefault("flavor", "")
    return k
exec(open(os.path.join(OUT, "plan.py")).read())
NAR = open(sys.argv[1]).read()
secs = {int(m.group(1)): (m.group(2), m.group(3).strip()) for m in
        re.finditer(r"^## Beat (\d+) — ([^\n]*)\n(.*?)(?=^## Beat |^---\s*$|\Z)", NAR, re.S | re.M)}
S = json.load(open(os.path.join(OUT, "stats.json")))
MAX = {G: 2300.0, W: 1550.0}
TIERS = [(300, "devastated"), (150, "excruciating"), (90, "very painful"), (60, "hurting"), (30, "sore"), (0, "minor")]
def tier(d): return next(n for t, n in TIERS if d >= t)
def block(b):
    s = S[str(b)]
    hl = []
    for w in (G, W):
        a, z = s["start"][w], s["end"][w]
        ch = z - a
        hl.append(f"{w} {a:.0f} → {z:.0f} ({100*z/MAX[w]:.0f}% of full{'' if abs(ch) < 1 else f', {ch:+.0f}'})")
    out = ["**Health:** " + " · ".join(hl)]
    for w in (G, W):
        ps = sorted(((k.split("|")[1], v) for k, v in s["parts"].items() if k.startswith(w + "|")),
                    key=lambda x: -(x[1][1] - x[1][0]))
        if not ps: continue
        bits = []
        for p, (a, z) in ps[:8]:
            ta, tz = tier(a), tier(z)
            bits.append(f"{p.lower()} {a:.0f} → {z:.0f} ({tz if ta == tz else ta + ' → ' + tz.upper()})")
        more = f"; and {len(ps) - 8} more parts, lightly" if len(ps) > 8 else ""
        out.append(f"**Damage to {w}:** " + "; ".join(bits) + more)
    return "\n\n".join(out)
cur = {"b": 0}
def my_narrate(*a, **k):
    b = cur["b"]
    title, prose = secs.get(b, ("", "(no narration written for this beat)"))
    return f"**Beat {b} — {title}**\n\n{block(b)}\n\n{prose}"
s = H.session(int(os.environ.get("SEED", "7")), scene="13", fighters="Glacia,Swift",
              settings=["/set finish.knockout_only true", "/set finish.no_pins true"])
s.narrator.narrate = my_narrate
eng = s.eng
for i, acts in enumerate(PLAN, 1):
    if s.over: break
    cur["b"] = i
    try:
        out, _ = H.beat(s, acts, [])
    except Exception as e:
        acts = [A(acts[0]["attacker"], "breather", flavor="she has nothing left for that: she hangs back and drags in air")]
        out, _ = H.beat(s, acts, [])
    st = {f.name: round(f.health) for f in eng.fighters.values()}
    exp = {k: round(v) for k, v in S[str(i)]["end"].items()}
    print(i, st, "OK" if all(abs(st[k] - exp[k]) <= 1 for k in st) else f"DIFF expected {exp}")
import fightexport
for r in s.beat_records:
    r["text"] = re.sub(r"\n*~ ~ ~\s*\n+Placeholder prose\.?", "", r["text"])
    r["text"] = re.sub(r"\n*(Placeholder prose\. ?)+", "", r["text"])
p = fightexport.write(s, sys.argv[2])
print("wrote", p)
