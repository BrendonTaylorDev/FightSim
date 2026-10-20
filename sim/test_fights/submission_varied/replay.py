"""Replay the seed-21 submission match with the hand-written narration (full_fight.md), then export it with cards."""
import sys, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
NAR = open(os.path.join(HERE, "full_fight.md")).read()
OUTP = sys.argv[1]
secs = {int(m.group(1)): (m.group(2), m.group(3).strip()) for m in
        re.finditer(r"^## Beat (\d+) — ([^\n]*)\n(.*?)(?=^---\s*$|\Z)", NAR, re.S | re.M)}
src = open(os.path.join(HERE, "drive.py")).read().replace('if __name__ == "__main__":\n    run()', "")
G = {"__file__": os.path.join(HERE, "drive.py"), "__name__": "replay"}
exec(compile(src, "drive.py", "exec"), G)
def my_narrate(*a, **k):
    b = G["RUN"]["beat"]
    title, prose = secs.get(b, ("", "(no narration written for this beat)"))
    return f"**Beat {b}: {title}**\n\n{prose}"
os.environ["SEED"] = "21"
s = G["run"](narrate=my_narrate, quiet=True)
import fightexport
for r in s.beat_records:
    r["text"] = re.sub(r"\n*~ ~ ~\s*\n+Placeholder prose\.?", "", r["text"])
    r["text"] = re.sub(r"\n*(Placeholder prose\. ?)+", "", r["text"])
print("records", len(s.beat_records))
print("wrote", fightexport.write(s, OUTP))
print({f.name: round(f.health) for f in s.eng.fighters.values()}, s.eng.winner())
