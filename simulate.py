"""/simulate: whole fights played with no model at all, for checking balance quickly.

A plain dice-driven stand-in picks every action (a random usable move at a random part, a pin when one is allowed,
a breather when she is winded, a take-off for a winged fighter); the real engine rolls everything else exactly as in
a story fight. Nothing touches the fight in progress or your settings: each fight is a fresh engine with a copy of
the current rules and arena. It reports who won, how long it took, and how pins, escapes and health swings went."""
import copy
import random

from engine import Engine
from director import resolve_many, pin_shapes


def _usable(eng, f, d, budget=None):
    """The moves f could throw at d right now (rules on repeats, uses, energy, reach and flight all kept). budget: the
    energy she has for it (less than she has when a take-off comes first)."""
    budget = f.energy if budget is None else budget
    out = []
    mine = [m for who, m in eng.move_log if who == f.name][-2:]
    for m in f.moves:
        if len(mine) == 2 and all(x == m["name"] for x in mine):
            continue
        if f.move_uses.get(m["name"], 1) <= 0 or m.get("target") == "hold":
            continue
        if eng.energy_cost(m) > budget or eng.busy_with(f, m):     # (her jaws can't bite while they hold)
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
    flying = eng.has(f, "airborne")
    # a submission opening (rarer than a pin, so offered first): usually taken, and now and then something free is used on her as well
    if (getattr(eng, "sub_window", None) or {}).get(d.name) and not flying and f.name not in eng.downed \
            and rng.random() < 0.7:
        shapes = eng.submission_shapes(f.name, d.name)
        if shapes:
            return dict(a, action="submission", improvised_name=rng.choice(sorted(shapes)))
    held = [h for h in eng.holds.values() if h.sub and h.attacker == f.name and h.defender == d.name]
    if held and not eng.sub_stuck(d, held) and rng.random() < 0.5:
        return dict(a, action="breather")    # keeps cranking the submission
    ok, _ = eng.pin_allowed(d.name)
    # like the director: when there is an opening it is told to go for it, and usually does
    if ok and not flying and f.name not in eng.downed and not eng.has(f, "reeling") and rng.random() < 0.85:
        shapes = pin_shapes(eng, f, d)
        if shapes:
            look, contacts = rng.choice(list(shapes.values()))
            sev = ["crushing"] + ["firm"] * (len(contacts) - 1)
            return dict(a, action="pin", flavor=look[:80],
                        hits=[{"part": p, "severity": s, "with": w} for (p, w), s in zip(contacts, sev)])
    budget = f.energy
    if not eng.has(f, "airborne") and eng.can_fly(f) and rng.random() < 0.3:     # any winged fighter, dragons too
        cost = eng.takeoff_cost(f)
        if f.energy - cost >= 12:     # only with breath left for a move once she is up (the take-off is paid first)
            a["reposition"] = "take off"
            budget = f.energy - cost
    moves = _usable(eng, f, d, budget)
    if a.get("reposition") == "take off":
        # once up she can't reach a fighter on the ground with a plain close blow unless she dives: keep what works
        moves = [m for m in moves if m.get("target") in ("status", "self") or eng.is_ranged(m)
                 or m.get("target") == "targeted"] or moves
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
    # as the director does now and then: a held stream or beam, or a pummel on a fighter with nowhere to go
    if m.get("sustainable") and m.get("target") != "self" and rng.random() < 0.2:
        a.update(action="combo", sustain=rng.choice([2, 3, 3, 4]))
        a.setdefault("hits", [{"part": a.pop("part")}] if "part" in a else a.get("hits"))
    elif m.get("target") == "targeted" and not eng.is_ranged(m) and not m.get("charge") and not a.get("feint") \
            and not a.get("reposition") and eng.pummel_place(f.name, d.name) and rng.random() < 0.35:
        a["count"] = rng.choice([2, 3, 3, 4])
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


CHAIN_CHANCE = 0.12      # a strike now and then strings one or two more links on (director chains)
GRAPPLE_CHANCE = 0.04    # now and then a grab first, and the strike becomes a pummel at point-blank


def _chain_links(eng, rng, f, d, first):
    """One or two more attacks by f on d after `first`, each a different move she can still afford."""
    used = {first["move"]}
    m0 = eng.find_move(f.name, first["move"])
    spent = (eng.energy_cost(m0) if m0 else 0) + (eng.takeoff_cost(f) if first.get("reposition") == "take off" else 0)
    out = []
    for _ in range(rng.choice([1, 1, 2])):
        opts = [m for m in _usable(eng, f, d, f.energy - spent) if m["name"] not in used
                and m.get("target") == "targeted" and not m.get("charge")]
        if not opts:
            break
        m = rng.choice(opts)
        used.add(m["name"])
        spent += eng.energy_cost(m)
        last = (out or [first])[-1].get("part") or rng.choice(list(d.parts))
        out.append({"attacker": f.name, "defender": d.name, "flavor": "", "_sim": True, "action": "strike",
                    "move": m["name"], "part": last if rng.random() < 0.4 else rng.choice(list(d.parts))})
    return out


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
        elif act.get("action") == "strike" and not act.get("count") and not act.get("carry") \
                and not act.get("launch") and not act.get("charge_into") \
                and not (eng.find_move(f.name, act["move"]) or {}).get("charge") and rng.random() < CHAIN_CHANCE:
            acts += _chain_links(eng, rng, f, d, act)
        elif act.get("action") == "strike" and not act.get("reposition") and not eng.has(f, "airborne") \
                and not eng.has(d, "airborne") and f.name not in eng.downed and d.name not in eng.downed \
                and not eng.pinned_by(d.name) and not eng.regrab_wait(f, d) and rng.random() < GRAPPLE_CHANCE:
            # a grab, then the held fighter worked over at point-blank (the move picked becomes the pummel)
            m = eng.find_move(f.name, act["move"])
            if m and m.get("target") == "targeted" and not eng.is_ranged(m) and not m.get("charge"):
                grab = {"attacker": f.name, "defender": d.name, "action": "grapple", "flavor": "", "_sim": True,
                        "part": rng.choice(list(d.parts)), "hits": [{"with": rng.choice(["her forepaw", "her jaws",
                                                                                         "her tail"])}]}
                acts = [grab, dict(act, count=rng.choice([2, 3, 3, 4]), launch="none")]
        try:
            results, started = resolve_many(eng, acts)
            stats["carries"] = stats.get("carries", 0) + sum(1 for r in results if isinstance(r, dict) and r.get("carried"))
            stats["spikes"] = stats.get("spikes", 0) + sum(1 for r in results if isinstance(r, dict) and r.get("spiked_down")
                                                            and r.get("type") == "instant" and r.get("move"))
            stats["pins"] += sum(1 for r in results if isinstance(r, dict) and r.get("type") == "pin_start")
            if stats["pins"] and "first_pin" not in stats:
                stats["first_pin"] = eng.turn     # how early in the fight the first pin came
            stats["subs"] += sum(1 for r in results if isinstance(r, dict) and r.get("submission"))
            for r in results:
                if not isinstance(r, dict):
                    continue
                for k, hit in (("chain_links", (r.get("chain") or {}).get("link", 1) > 1), ("pummels", r.get("pummel")),
                               ("sustains", r.get("sustain")), ("grapples", r.get("type") == "grapple_start")):
                    if hit:
                        stats[k] = stats.get(k, 0) + 1
        except Exception:
            results = []
            stats["errors"] += 1
            try:
                _, started = resolve_many(eng, [{"attacker": f.name, "defender": d.name, "action": "breather",
                                                 "flavor": ""}])
            except Exception:
                started = ()
        events = eng.beat(skip_hold_ids=started)
        bad = eng.check_state()
        if bad:     # a rule that must always hold was broken (engine.check_state): count it, keep the first few
            stats["state_problems"] = stats.get("state_problems", 0) + len(bad)
            stats.setdefault("state_examples", []).extend(f"beat {eng.turn}: {b}" for b in bad[:2])
            eng.repair_state()
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
    got = lambda k: sum(r.get(k, 0) for r in runs) / n
    out.append(f"  per fight: chain links {got('chain_links'):.1f}, pummels {got('pummels'):.1f}, held streams "
               f"{got('sustains'):.1f}, grapples {got('grapples'):.1f}, carries {got('carries'):.1f}, collapses "
               f"{got('collapses'):.2f}")
    probs = sum(r.get("state_problems", 0) for r in runs)
    if probs:
        ex = [x for r in runs for x in r.get("state_examples", [])][:3]
        out.append(f"  STATE CHECK: {probs} broken rule(s) found and put right, e.g. " + "; ".join(ex))
    errs = sum(r["errors"] for r in runs)
    if errs:
        out.append(f"  ({errs} stand-in choices were refused by the rules and replaced by a breather)")
    return "\n".join(out)
