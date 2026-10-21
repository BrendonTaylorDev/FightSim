"""A short digest of every beat (bNN.txt) for narrating: the actions, the screen's event lines, each hurt part's
damage after the beat, the totals, and the rolls. Writes digest.txt."""
import glob, re, os
HERE = os.path.dirname(os.path.abspath(__file__))
out = []
for path in sorted(glob.glob(os.path.join(HERE, "b[0-9][0-9].txt"))):
    txt = open(path, encoding="utf-8").read()
    std = txt.split("##### STDOUT", 1)[1].split("##### PROMPT", 1)[0]
    acts = txt.split("##### ACTIONS", 1)[1].split("##### STDOUT", 1)[0].strip()
    n = int(re.search(r"b(\d+)", os.path.basename(path)).group(1))
    out.append(f"\n================ BEAT {n}\nACTIONS {acts[:400]}")
    part = None
    skip_prose = False
    rolls = False
    for line in std.splitlines():
        s = line.rstrip()
        if s.startswith("🎲"):
            rolls = True
            continue
        if rolls:
            if s.startswith("    ") and s.strip():
                out.append("  roll: " + s.strip())
                continue
            rolls = False
        if not s.strip() or s.startswith("─") or s.startswith("---") or "[narrator" in s or "[the beat" in s \
                or "[a blow" in s or "Placeholder" in s:
            continue
        if re.match(r"^— .+ —$", s.strip()):
            skip_prose = True
            continue
        if s.startswith("⚔️") or s.startswith("Attack") or s.startswith("🎲"):
            skip_prose = False
        if skip_prose and not re.match(r"^[^\w\s]", s):
            continue
        skip_prose = False
        m = re.match(r"^ {4}(\S.*)$", s)
        if m and not s.startswith("     "):
            part = m.group(1).strip()
            continue
        m = re.match(r"^ {8}damage\s+(.*?)\s{2,}", s)
        if m and part:
            out.append(f"    {part}: {m.group(1)}")
            continue
        if re.match(r"^ {8}(resistance|health)\b", s) or s.startswith("              "):
            continue
        if re.match(r"^\s+Power \*\*|^\s+Jarred next", s):
            continue
        out.append(s)
open(os.path.join(HERE, "digest.txt"), "w", encoding="utf-8").write("\n".join(out))
print(len(out), "lines")
