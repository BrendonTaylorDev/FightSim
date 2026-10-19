import sys, re
for n in sys.argv[1:]:
    t = open(f"b{int(n):02d}.txt").read()
    out = t.split("##### PROMPT")[0]
    out = re.sub(r"\n— \w+ —\n\nPlaceholder prose\.\n", "", out)
    print(f"################ BEAT {n}\n" + "\n".join(l for l in out.splitlines() if l.strip() and not re.match(r"\s+(damage|resistance|health) ", l)))
    u = t.split("##### PROMPT 0 user",1)[-1].split("##### PROMPT 1",1)[0]
    m = re.search(r"\nWHAT HAPPENS IN THIS BEAT.*?(?=\nPAIN GUIDE|\nTELLING THE HURT)", u, re.S)
    if m: print(m.group(0)[:7000])
    for k in ("STILL FEELING IT","STRUGGLE BUILDS","ON AN OLD WOUND","REACTIONS CLIMB","HER OWN WOUNDS","SEES OF"):
        for l in sorted(set(re.findall(r"[^\n]*%s[^\n]*" % k, t))): print("  >>", l.strip()[:600])
