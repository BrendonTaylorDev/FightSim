"""Per-beat summary of a run's console output (for writing and checking the narration)."""
import re, sys
t = open(sys.argv[1]).read()
cur = []; part = None
for line in t.split("\n"):
    m = re.match(r"\s{2}▸ (.*)", line)
    if m: cur.append("[" + m.group(1) + "]")
    m = re.match(r"\s{4}([A-Z][A-Za-z ]+?)( \(hit \d+\))?\s*$", line)
    if m: part = m.group(1)
    m = re.match(r"\s+damage\s+\S+ ([\d.]+)% → \S+ ([\d.]+)%", line)
    if m and part: cur.append(f"{part} {float(m.group(1)):.0f}→{float(m.group(2)):.0f}")
    if line.startswith("⏳ Beat"):
        b = re.match(r"⏳ Beat (\d+)", line).group(1)
        hp = " ".join(f"{a[0]}{float(a[1]):.0f}" for a in re.findall(r"(Nocturne|Ripples) (-?[\d.]+)%", line))
        print(f"B{b} [{hp}]: " + ", ".join(cur)); cur = []
    if re.match(r"^(⚔️|🤼|📌|⏸️|🧗|🧱|🪨|💨|👊|🌊|🐏|🔥|⚡|💥|↩️|😵|🔗|🫳|💢|🌋|⬇️|❄️|- Ripples struggles|- Nocturne struggles|- ⏱️|- Ripples|- Nocturne)", line):
        cur.append("|" + line[:120])
    if re.search(r"→ (it BREAKS|DODGED|she counters|she breaks free|flinched|paralyzed|restrained|she crumples|same spot|somewhere new|it ENDS here|she keeps her feet|she goes down too|she stays lying|frozen|burned|OPEN)\b", line):
        cur.append("~" + line.strip()[:100])
