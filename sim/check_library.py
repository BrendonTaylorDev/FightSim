"""Check story material against the library's rules before adding it (gore, memories before the fight, feet moving
in categories where only the engine moves her, unknown conditions or slots, duplicates, species and game words).
    python3 sim/check_library.py blocks|lines|samples FILE"""
import sys, re, json, collections
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
import blocks, narrator, userprompt
kind, path = sys.argv[1], sys.argv[2]
names = [f["name"] for f in json.load(open(__import__("os").path.join(sys.path[0], "fighters.json")))["fighters"]]
species = set()
for f in json.load(open(__import__("os").path.join(sys.path[0], "fighters.json")))["fighters"]:
    m = re.match(r"\s*(?:An?|The)\s+(?:female\s+|male\s+)?([A-Z][\w'-]+)", f.get("description", ""))
    if m: species.add(m.group(1))
NAMES = re.compile(r"\b(?:Pok[eé]mon|" + "|".join(map(re.escape, sorted(set(names) | species))) + r")\b")
GAME = re.compile(r"\b(?:super[- ]effective|not very effective|HP|hit points|stats?|damage|percent|%|level \d)\b", re.I)
SLOT = re.compile(r"\{(\w+)\}")
MOVES = narrator.MOVES_HER
NO_MOVE = {"reaction", "pain_show", "sensation", "tell", "held_in", "raw", "breath", "impact_mark", "dwell", "after_hit",
           "devastated_reaction", "self_look", "status_tell"}
problems = collections.Counter()
def bad(why, where):
    problems[why] += 1
    if problems[why] <= 6:
        print(f"  [{why}] {where[:170]}")
if kind in ("blocks", "lines"):
    B = blocks.Blocks({"narration": {"blocks": {"file": path}}})
    base = blocks.Blocks({"narration": {"blocks": {"file": __import__("os").path.join(sys.path[0], "story_") + ("blocks" if kind == "blocks" else "lines") + ".txt"}}})
    have = {(c, t.lower()) for c, _, t in base.entries}
    keys_by_cat = collections.defaultdict(set)
    for c, co, _ in base.entries:
        keys_by_cat[c] |= set(co)
    seen = set()
    for c, co, t in B.entries:
        low = t.lower()
        if (c, low) in have: bad("duplicate of existing", f"{c}: {t}")
        if (c, low) in seen: bad("duplicate within file", f"{c}: {t}")
        seen.add((c, low))
        if c not in keys_by_cat: bad("NEW category (check the program picks it)", c)
        else:
            extra = set(co) - keys_by_cat[c] - {"has"}
            if extra: bad("condition key the category never used", f"{c} {sorted(extra)}: {t}")
        for s in SLOT.findall(t):
            if s not in ("part", "next", "foe"): bad("unknown slot", t)
        if narrator.GORE.search(t): bad("gore", f"{c}: {t}")
        if narrator.INVENTED_PAST.search(t) or blocks.PAST_MEMORY.search(t): bad("memory before the fight", f"{c}: {t}")
        if NAMES.search(t): bad("species/name/Pokemon", t)
        if GAME.search(t): bad("game word", t)
        if c in NO_MOVE and MOVES.search(t): bad("moves her feet in a no-move category", f"{c}: {t}")
        if kind == "blocks" and (t[:1].isupper() and not t.startswith("*")) : bad("block starts capitalised", t)
        if kind == "lines" and not t.startswith("*") and not t.rstrip().endswith((".", "!", "?", "*", "…")): bad("line not a sentence", t)
        if kind == "lines" and re.search(r"\b(?:she|her) (?:is|are|has|does|looks|feels|takes|goes)\b", t) and not t.startswith("*"):
            bad("line in present tense?", t)
    print(f"{path}: {len(B.entries)} entries; " + ", ".join(f"{c}={n}" for c, n in collections.Counter(c for c, _, _ in B.entries).most_common()))
else:
    S = userprompt.sample_sections(open(path).read())
    for tags, body in S:
        if narrator.GORE.search(body): bad("gore", body[:120])
        if narrator.INVENTED_PAST.search(body) or blocks.PAST_MEMORY.search(body): bad("memory before the fight", body[:120])
        if NAMES.search(body): bad("species/name", NAMES.search(body).group(0))
        if GAME.search(body): bad("game word", GAME.search(body).group(0))
        conds = [t for t in tags if ":" in t]
        anat = re.search(r"\b(wings?|feathers?|beak|talons?|coils?|scales?|fins?|horn|mane|shell|tails?|antennae|flames?|paws?|hands?|hooves)\b", body, re.I)
        if anat and not conds: bad("body feature with no condition", f"{tags}: {anat.group(0)}")
        n = len(body.split())
        if n < 120 or n > 420: bad("length", f"{tags} {n} words")
        if "{A}" not in body and "{B}" not in body: bad("no {A}/{B}", str(tags))
    print(f"{path}: {len(S)} passages; " + ", ".join(f"{t}={n}" for t, n in collections.Counter(t for tags, _ in S for t in tags if ':' not in t).most_common()))
print("PROBLEMS:", dict(problems) if problems else "none")
