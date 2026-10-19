import re, json
MAX = {"Ripples": 1700.0, "Nerine": 1775.0}
health = dict(MAX); out = {}
for b in range(1, 30):
    t = open(f"b{b:02d}.txt").read().split("##### PROMPT")[0]
    start = dict(health); parts = {}; pend = []
    lines = t.splitlines()
    for i, l in enumerate(lines):
        m = re.match(r"^    ([A-Z][A-Za-z ]+?)(?: \(hit \d+\))?\s*$", l)
        if m and i + 1 < len(lines):
            d = re.search(r"damage\s+\S+ (-?[\d.]+)% → \S+ (-?[\d.]+)%", lines[i + 1])
            if d: pend.append((m.group(1), float(d.group(1)), float(d.group(2))))
            continue
        m = re.search(r"each: ([A-Z][A-Za-z ]+?) (-?[\d.]+)→(-?[\d.]+)%", l)
        if m:
            pend.append((m.group(1), float(m.group(2)), float(m.group(3)))); continue
        m = re.search(r"Total: .*❤️ (\w+) (-?[\d.]+)% → \*\*(-?[\d.]+)%\*\*", l)
        if m:
            who = m.group(1)
            for p, a, z in pend:
                parts.setdefault((who, p), [a, z])[1] = z
            pend = []; health[who] = float(m.group(3))
        m = re.search(r"(?:strains her hurt|drop on try \d+ hurts:) ?([A-Za-z ]+?)(?: to stay in the air)? (?:→ \+[\d.]+% damage|damage (-?[\d.]+)% → \*\*(-?[\d.]+)%\*\*)", l)
        if m and m.group(2):
            who = next((w for w in MAX if f"**{w} gets up" in t or f"**{w} can't get up" in t), None) or "Ripples"
            parts.setdefault((who, m.group(1).strip()), [float(m.group(2)), 0])[1] = float(m.group(3))
        m = re.search(r"⏳ Beat \d+ health: (.*)", l)
        if m:
            for who, v in re.findall(r"❤️ (\w+) (-?[\d.]+)%", l + " " + (lines[i + 1] if i + 1 < len(lines) else "")):
                health[who] = float(v)
    out[b] = {"start": start, "end": dict(health), "parts": {f"{w}|{p}": v for (w, p), v in parts.items()}}
    if False: print(b, {k: round(v) for k, v in health.items()}, len(parts))
json.dump(out, open("stats.json", "w"), indent=0)
