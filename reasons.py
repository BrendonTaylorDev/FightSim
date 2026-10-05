"""Why two wild Pokémon end up fighting (no trainers): reasons from fight_reasons.txt, one picked for each fight to
fit the arena, with one fighter as the holder (there first, or holding what is wanted) and the other as the comer.
The story is told the reason (the intro, a short note every beat, now and then a thought, and the ending)."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
FIELDS = ("title", "setup", "holder", "comer", "stakes", "thoughts", "end")


def load(path=None):
    """[{id, places, title, setup, holder, comer, stakes, thoughts: [...], end}] from the reasons file."""
    path = path or os.path.join(HERE, "fight_reasons.txt")
    if not os.path.exists(path):
        return []
    out, cur = [], None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("#") or not line.strip():
                continue
            m = re.match(r"==\s*([^|]+?)\s*(?:\|\s*places:\s*(.*))?$", line)
            if m:
                cur = {"id": m.group(1).strip(), "places": [p.strip().lower() for p in (m.group(2) or "any").split(",")
                                                            if p.strip()]}
                out.append(cur)
                continue
            m = re.match(r"(\w+):\s*(.*)$", line)
            if cur is not None and m and m.group(1).lower() in FIELDS:
                key, val = m.group(1).lower(), m.group(2).strip()
                cur[key] = [t.strip() for t in val.split(" / ") if t.strip()] if key == "thoughts" else val
    return [r for r in out if r.get("setup")]


def fits(reason, scene_name):
    """Does this reason suit the arena? 'any' always does; otherwise a place word must be in the arena's name
    ('ruins' matches 'ruined temple' too)."""
    name = str(scene_name or "").lower()
    for p in reason.get("places") or ["any"]:
        if p == "any":
            return True
        if p and (p in name or p[:4] in name):
            return True
    return False


def pick(rng, scene_name, all_reasons=None, avoid=()):
    """One reason for this arena (arena-specific ones a little likelier), not one used recently if avoidable."""
    rs = all_reasons if all_reasons is not None else load()
    ok = [r for r in rs if fits(r, scene_name)]
    fresh = [r for r in ok if r["id"] not in set(avoid)] or ok
    if not fresh:
        return None
    weights = [1.0 if r["places"] == ["any"] else 1.6 for r in fresh]
    return rng.choices(fresh, weights=weights)[0]


def fill(reason, holder, comer, place):
    """The reason's words with the fighters' names and the place put in."""
    def sub(t):
        return (str(t).replace("{holder}", holder).replace("{comer}", comer).replace("{place}", place))
    out = {k: (sub(v) if isinstance(v, str) else [sub(x) for x in v] if isinstance(v, list) else v)
           for k, v in reason.items()}
    out["holder_name"], out["comer_name"] = holder, comer
    return out
