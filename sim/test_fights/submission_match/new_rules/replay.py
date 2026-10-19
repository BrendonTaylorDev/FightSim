"""Replay the submission match (seed 11) with the hand-written narration, then export it."""
import sys, os, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
NAR = open(sys.argv[1]).read()
OUTP = sys.argv[2]
secs = {int(m.group(1)): (m.group(2), m.group(3).strip()) for m in
        re.finditer(r"^## Beat (\d+) — ([^\n]*)\n(.*?)(?=^## Beat |^---\s*$|\Z)", NAR, re.S | re.M)}
S = json.load(open(os.path.join(HERE, "stats.json")))
MAX = {"Ripples": 1700.0, "Nerine": 1775.0}
TIERS = [(300, "devastated"), (150, "excruciating"), (90, "very painful"), (60, "hurting"), (30, "sore"), (0, "minor")]
def tier(d): return next(n for t, n in TIERS if d >= t)
def block(b):
    s = S[str(b)]
    hl = []
    for w in MAX:
        a, z = s["start"][w], s["end"][w]
        ch = z - a
        hl.append(f"{w} {a:.0f} → {z:.0f} ({100*z/MAX[w]:.0f}% of full{'' if abs(ch) < 1 else f', {ch:+.0f}'})")
    out = ["**Health:** " + " · ".join(hl)]
    for w in MAX:
        ps = sorted(((k.split("|")[1], v) for k, v in s["parts"].items() if k.startswith(w + "|")),
                    key=lambda x: -(x[1][1] - x[1][0]))
        if ps:
            out.append(f"**Damage to {w}:** " + "; ".join(
                f"{p.lower()} {a:.0f} → {z:.0f} ({tier(z) if tier(a) == tier(z) else tier(a) + ' → ' + tier(z).upper()})"
                for p, (a, z) in ps[:8]))
    return "\n\n".join(out)
sys.argv = [sys.argv[0]]
src = open(os.path.join(HERE, "drive.py")).read().replace('if __name__ == "__main__":\n    run()', "")
G = {"__file__": os.path.join(HERE, "drive.py"), "__name__": "replay"}
exec(compile(src, "drive.py", "exec"), G)
def my_narrate(*a, **k):
    b = G["RUN"]["beat"]
    title, prose = secs.get(b, ("", "(no narration written for this beat)"))
    return f"**Beat {b} — {title}**\n\n{block(b)}\n\n{prose}"
s = G["run"](narrate=my_narrate, quiet=True)
for i in range(1, 30):
    pass
import fightexport
for r in s.beat_records:
    r["text"] = re.sub(r"\n*~ ~ ~\s*\n+Placeholder prose\.?", "", r["text"])
    r["text"] = re.sub(r"\n*(Placeholder prose\. ?)+", "", r["text"])
print("wrote", fightexport.write(s, OUTP))
print({f.name: round(f.health) for f in s.eng.fighters.values()}, s.eng.winner())
