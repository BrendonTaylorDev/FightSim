"""/simulate: whole fights played with no model at all, for checking balance quickly.

A plain dice-driven stand-in picks every action (a random usable move at a random part, a pin when one is allowed,
a breather when she is winded, a take-off for a winged fighter); the real engine rolls everything else exactly as in
a story fight. Nothing touches the fight in progress or your settings: each fight is a fresh engine with a copy of
the current rules and arena. It reports who won, how long it took, and how pins, escapes and health swings went."""
import copy
import random

from engine import Engine
from director import resolve_many, pin_shapes


def _usable(eng, f, d):
    out = []
    mine = [m for who, m in eng.move_log if who == f.name][-2:]
    for m in f.moves:
        if len(mine) == 2 and all(x == m["name"] for x in mine):
            continue
        if f.move_uses.get(m["name"], 1) <= 0 or m.get("target") == "hold":
            continue
        if eng.energy_cost(m) > f.energy:
            continue
        if m.get("carry") and not eng.has(f, "airborne"):
            continue
        if eng.has(d, "airborne") and not eng.has(f, "airborne") and not eng.is_ranged(m) \
                and m.get("target") not in ("status", "self"):
            continue
        if (f.name in eng.downed or eng.pinned_by(f.name)) and m.get("charge"):
            continue
        out.append(m)
    return out


def _pick_action(eng, rng, f, d):
    """One action for fighter f against d, chosen by dice."""
    a = {"attacker": f.name, "defender": d.name, "flavor": "", "_sim": True}
    if eng.pinned_by(f.name) or eng.pinning(f.name) or f.energy < 12:
        return dict(a, action="breather")
    # a submission opening (rarer than a pin, so offered first): usually taken, and now and then something free is used on her as well
    if (getattr(eng, "sub_window", None) or {}).get(d.name) and f.name not in eng.downed and rng.random() < 0.7:
        shapes = eng.submission_shapes(f.name, d.name)
        if shapes:
            return dict(a, action="submission", improvised_name=rng.choice(sorted(shapes)))
    held = [h for h in eng.holds.values() if h.sub and h.attacker == f.name and h.defender == d.name]
    if held and not eng.sub_stuck(d, held) and rng.random() < 0.5:
        return dict(a, action="breather")    # keeps cranking the submission
    ok, _ = eng.pin_allowed(d.name)
    # like the director: when there is an opening it is told to go for it, and usually does
    if ok and f.name not in eng.downed and not eng.has(f, "reeling") and rng.random() < 0.85:
        shapes = pin_shapes(eng, f, d)
        if shapes:
            look, contacts = rng.choice(list(shapes.values()))
            sev = ["crushing"] + ["firm"] * (len(contacts) - 1)
            return dict(a, action="pin", flavor=look[:80],
                        hits=[{"part": p, "severity": s, "with": w} for (p, w), s in zip(contacts, sev)])
    if not eng.has(f, "airborne") and eng.can_fly(f) and rng.random() < 0.3:     # any winged fighter, dragons too
        a["reposition"] = "take off"
    moves = _usable(eng, f, d)
    if not moves:
        return dict(a, action="breather")
    m = rng.choice(moves)
    parts = list(d.parts)
    a.update(action="strike", move=m["name"])
    if m.get("target") in ("spread",):
        a["hits"] = [{"part": p} for p in rng.sample(parts, min(3, len(parts)))]
    else:
        a["part"] = rng.choice(parts)
    if m.get("target") in ("targeted",) and not m.get("charge") and rng.random() < 0.1:
        a["feint"] = True
    if eng.has(f, "airborne") and m.get("target") == "targeted" and not eng.is_ranged(m) and not m.get("charge") \
            and not m.get("carry") and eng.can_carry(f, d)[0] and rng.random() < 0.25:
        a["carry"] = True      # seize her and haul her up (one_fight may follow it with a blow as she falls)
    if m.get("target") != "self" and m.get("power", 0) >= 30 and rng.random() < 0.3:
        a["launch"] = rng.choice(["knocked down", "knocked down", "thrown"])   # as the director does for heavy hits
    if m.get("charge") and rng.random() < 0.3:
        props = (getattr(eng, "scene_cfg", None) or {}).get("props") or []
        if props:
            a["charge_into"] = rng.choice(props)
    return a


def one_fight(names, rules, scene, seed, max_beats=150):
    eng = Engine(seed=seed, rules=copy.deepcopy(rules), only=names)
    if scene:
        try:
            eng.set_scene(scene)
        except Exception:
            pass
    rng = random.Random(seed * 7919 + 1)
    stats = {"pins": 0, "escapes": 0, "worst_beat": 0.0, "errors": 0, "beats": 0, "subs": 0}
    last = None
    while not eng.winner() and eng.turn < max_beats:
        eng.roll_pin_windows()      # once a beat, as in the game: is there an opening for a pin on anyone?
        active = eng.active()
        # whoever acts: usually not the one who just did, now and then the same one pressing on
        movers = [f for f in active if not any(eng.has(f, st) for st in ("asleep", "frozen", "flinched"))] or active
        pool = [f for f in movers if f.name != last] if last and rng.random() < 0.65 else movers
        f = rng.choice(pool or movers)
        foes = [x for x in active if x is not f and (not x.team or x.team != f.team)]
        if not foes:
            break
        d = rng.choice(foes)
        before = {x.name: x.health for x in eng.fighters.values()}
        act = _pick_action(eng, rng, f, d)
        acts = [act]
        if act.get("carry") and rng.random() < 0.6:
            nxt = _pick_action(eng, rng, f, d)
            if nxt.get("action") == "strike" and nxt.get("move") != act.get("move"):
                acts.append(dict(nxt, carry=False, launch="none"))
        try:
            results, started = resolve_many(eng, acts)
            stats["carries"] = stats.get("carries", 0) + sum(1 for r in results if isinstance(r, dict) and r.get("carried"))
            stats["spikes"] = stats.get("spikes", 0) + sum(1 for r in results if isinstance(r, dict) and r.get("spiked_down")
                                                            and r.get("type") == "instant" and r.get("move"))
            stats["pins"] += sum(1 for r in results if isinstance(r, dict) and r.get("type") == "pin_start")
            if stats["pins"] and "first_pin" not in stats:
                stats["first_pin"] = eng.turn     # how early in the fight the first pin came
            stats["subs"] += sum(1 for r in results if isinstance(r, dict) and r.get("submission"))
        except Exception:
            results = []
            stats["errors"] += 1
            try:
                _, started = resolve_many(eng, [{"attacker": f.name, "defender": d.name, "action": "breather",
                                                 "flavor": ""}])
            except Exception:
                started = ()
        events = eng.beat(skip_hold_ids=started)
        eng.record_beat(results, events)
        for e in events:
            if e.get("struggle") == "escape":
                stats["escapes"] += 1
            if e.get("type") == "collapse":
                stats["collapses"] = stats.get("collapses", 0) + 1
            if e.get("type") == "sub_to_pin":     # a submission held so long it became a pin
                stats["pins"] += 1
                stats["subs_to_pin"] = stats.get("subs_to_pin", 0) + 1
                stats.setdefault("first_pin", eng.turn)
        for x in eng.fighters.values():
            lost = (before.get(x.name, x.health) - x.health) / max(1.0, x.max_health) * 100
            stats["worst_beat"] = max(stats["worst_beat"], lost)
        last = f.name
    stats["beats"] = eng.turn
    stats["winner"] = eng.winner() or ""
    stats["summary"] = eng.fight_summary()
    stats["end"] = {x.name: round(x.health / x.max_health * 100) for x in eng.fighters.values()}
    return stats


def simulate(names, rules, scene, count=20, seed=None, max_beats=150):
    base = seed if seed is not None else random.randrange(10 ** 6)
    runs = [one_fight(names, rules, scene, base + i, max_beats) for i in range(count)]
    wins = {}
    for r in runs:
        wins[r["winner"] or "no winner"] = wins.get(r["winner"] or "no winner", 0) + 1
    n = len(runs)
    avg = lambda k: sum(r[k] for r in runs) / n
    out = [f"/simulate: {n} fights, {' vs '.join(names)}" + (f" in {scene}" if scene else "")
           + f" (seeds {base}..{base + n - 1}; no model, dice-driven choices)",
           "  wins: " + ", ".join(f"{k} {v} ({v * 100 // n}%)" for k, v in sorted(wins.items(), key=lambda kv: -kv[1])),
           f"  beats: average {avg('beats'):.0f} (shortest {min(r['beats'] for r in runs)}, longest "
           f"{max(r['beats'] for r in runs)})",
           f"  pins started: {avg('pins'):.1f} a fight; escapes: {avg('escapes'):.1f} a fight; submission holds: "
           f"{avg('subs'):.2f} a fight",
           f"  worst single beat: {max(r['worst_beat'] for r in runs):.0f}% of max health "
           f"(average worst {avg('worst_beat'):.0f}%)"]
    errs = sum(r["errors"] for r in runs)
    if errs:
        out.append(f"  ({errs} stand-in choices were refused by the rules and replaced by a breather)")
    return "\n".join(out)
