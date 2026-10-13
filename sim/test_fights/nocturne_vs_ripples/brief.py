"""What happened in the last beat, in short: attacks, results, rolls."""
import sys, re
n = int(sys.argv[1])
t = open(f"out/beat{n:02d}.txt").read()
keep = re.compile(r"^(Attack|💨|🥴|↪️|⬇️|💥|🛡|🔗|👊|🪵|📌|🔒|⛓|🌊|⚡|💧|😵|🫨|🤕|😮|💫|🔥|❄|🏆|\*\*\*|- )|DODG|dodges|→ (?:it lands|DODGED|she stumbles|it moves her|KNOCKED|she bites|it ENDS|FRENZY)|blocked|deflect|guard|Total:|health:", re.U)
for line in t.splitlines():
    s = line.strip()
    if s and keep.search(s) and "narrator is" not in s and "Calculations" not in s and not s.startswith("- Res"):
        print(s[:200])
