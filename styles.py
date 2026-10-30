"""Fighting styles (rules.json styles, since build 335): how each fighter likes to fight, beyond the moves she favours.

A fighter's styles are set in fighters.json, "fighting": {style name: how strongly, 0 to 1}. Each style is described in
rules.json styles.list, where it can be switched off or retuned. A style steers four things:
- what she reaches for: kinds of move (close or ranged, big or quick, heavy blows that wear a part down or cutting ones
  that tear into it, holds) by the moment (her opponent down, held, off balance, fresh). The director is told, and the
  no-model fights (simulate.py) weigh her moves by it;
- where she aims: a blow aimed somewhere else is moved, some of the time, to where her style wants it (the one part she
  is taking apart, the worst-hurt part, the head, the body, the legs, somewhere still fresh);
- what she sets up: grabs, chains, pummels, feints, throws, how often;
- a few small things the engine does: the brunt of a dismantler's blow on the part she is taking apart, a setup
  fighter's big blow let go at point-blank, a counter-puncher's counters, an opportunist's blows on an opening.

Move profiles (moves.profile) live here too: a heavy blunt blow wears a part's resistance down more than it injures it,
a cutting one (claws, a blade, teeth) injures more, and more again on a part already worn down. Health is untouched by
the profile: it splits what a blow does to the part between the two.

Everything is worked out from the engine as it stands; the only state kept is the part each dismantler is taking apart
(engine.style_aim, saved and undone with the fight)."""
import re
import zlib

QUICK_RX = re.compile(r"\bquick\b|\bjet\b|sucker|extreme speed|fake out|mach punch|accelerock|shadow sneak|ice shard"
                      r"|bullet punch|vacuum wave|first impression", re.I)
OPEN_STATES = ("staggered", "off_balance", "dazed", "flinched", "stunned", "winded", "reeling", "breathless",
               "doubled_over")
LEG_REGIONS = ("hind_low", "hind_up", "fore_low")
AIM_REGIONS = {"head_hunter": {"head": 3.0, "neck": 1.0}, "body_worker": {"chest": 2.0, "belly": 2.5},
               "hobbler": {"hind_low": 2.5, "hind_up": 1.5, "fore_low": 1.0}}


def cfg(eng):
    """rules.json styles, or None when it is off."""
    c = eng.rules.get("styles") or {}
    return c if c.get("enabled", False) else None


def spec(eng, name):
    return ((cfg(eng) or {}).get("list") or {}).get(name) or {}


def of(eng, f):
    """Her styles that are switched on: {name: how strongly, 0-1}."""
    c = cfg(eng)
    if not c or f is None:
        return {}
    out = {}
    for k, v in (getattr(f, "fighting", None) or {}).items():
        s = (c.get("list") or {}).get(k)
        if not s or not s.get("enabled", True) or str(k).startswith("_"):
            continue
        try:
            w = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            continue
        if w > 0:
            out[k] = w
    return out


def w(eng, f, name):
    return of(eng, f).get(name, 0.0)


def num(eng, name, key, default):
    try:
        return float(spec(eng, name).get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _roll(eng, *keys):
    """A roll from the fight's state and the keys: it never moves the fight's own dice."""
    return zlib.crc32("|".join([str(getattr(eng, "_seed0", 0)), str(eng.turn)] + [str(k) for k in keys]).encode()) \
        % 100000 / 100000.0


# ---------------------------------------------------------------------------------------------------- move profiles

def profile_cfg(eng):
    c = (eng.rules.get("moves") or {}).get("profile") or {}
    return c if c.get("enabled", False) else None


def profile(eng, move, part=None):
    """How a move's blow splits between the part's resistance and the part itself: (damage mult, wear mult, kind).
    A move can set its own ("profile": {"damage": x, "wear": y} in its entry); else it goes by the kind of blow."""
    c = profile_cfg(eng)
    if not c or not move:
        return None
    own = move.get("profile") if isinstance(move.get("profile"), dict) else None
    kind = eng._blow_kind(move)
    k = dict((c.get("kinds") or {}).get(kind) or {})
    if own:
        k.update(own)
    dm, wm = float(k.get("damage", 1.0)), float(k.get("wear", 1.0))
    worn_b = float(k.get("worn_bonus", 0.0))
    if worn_b and part is not None:
        # a cutting blow tears deeper into a part already worn down
        start = float(getattr(part, "start_resistance", 0) or part.resistance or 1.0)
        worn = 1.0 - max(0.0, min(1.0, float(part.resistance) / max(1.0, start)))
        dm *= 1.0 + worn_b * worn
    if abs(dm - 1.0) < 0.005 and abs(wm - 1.0) < 0.005:
        return None
    return round(dm, 3), round(wm, 3), kind


def profile_word(dm, wm):
    """For the narrator: what this kind of blow does more of."""
    if wm >= 1.2 and dm <= 1.0:
        return "a heavy blow that pounds the part and wears it down (it softens it for later more than it injures it now)"
    if dm >= 1.1 and wm <= 0.9:
        return "a cutting blow that tears into a part already worn down: it goes deep"
    if dm >= 1.0 and wm <= 0.85:
        return "a cutting blow: it injures the part more than it wears it down"
    return ""


# ------------------------------------------------------------------------------------------------------ move kinds

def classes(eng, f, m):
    """The kinds a move is, for the styles: close / ranged, big, quick, breaker (heavy, blunt: wears a part down),
    cutter (claws, blades, teeth), bite, charge, wide (catches several parts), hold, status."""
    t = m.get("target")
    if t in ("status", "self"):
        return {"status"}
    if t == "hold":
        return {"hold"}
    out = set()
    ranged = eng.is_ranged(m)
    out.add("ranged" if ranged else "close")
    pw = float(m.get("power", 0) or 0)
    pows = sorted(float(x.get("power", 0) or 0) for x in (f.moves if f else ())
                  if x.get("target") not in ("status", "self", "hold"))
    mid = pows[len(pows) // 2] if pows else pw
    if pw >= 1.2 * mid:
        out.add("big")
    if QUICK_RX.search(str(m.get("name") or "")) or (pw <= 0.75 * mid and not ranged):
        out.add("quick")
    k = eng._blow_kind(m)
    if k == "blunt" or (k == "blast" and "big" in out):
        out.add("breaker")
    if k in ("claw", "blade", "bite"):
        out.add("cutter")
    if k == "bite":
        out.add("bite")
    if m.get("charge"):
        out.add("charge")
    if t in ("spread", "whole_body"):
        out.add("wide")
    return out


def situation(eng, f, d):
    """How things stand between her and her opponent, in the words the styles' "when" tables use."""
    s = set()
    if d.name in eng.downed:
        s.add("down")
    if eng.pinned_by(d.name):
        s.add("pinned")
    try:
        if eng.grab_between(f.name, d.name):
            s.add("grab")
    except Exception:
        pass
    if any(h.attacker == f.name and h.defender == d.name for h in eng.holds.values()):
        s.add("holding")
    if any(eng.has(d, st) for st in OPEN_STATES):
        s.add("open")
    if (getattr(eng, "pressed", None) or {}).get(d.name):
        s.add("against")
    hp = eng._health_pct(d)
    if hp < 40:
        s.add("hurt")
    if hp > 70 and not s & {"down", "pinned", "open"}:
        s.add("fresh")
    return s


def ko_match(eng):
    """A knockout-only match (finish.knockout_only with finish.no_pins, not a submission match)."""
    fin = eng.rules.get("finish") or {}
    sub = fin.get("submission") if isinstance(fin.get("submission"), dict) else {}
    return bool(fin.get("knockout_only") and fin.get("no_pins") and not sub.get("enabled"))


def ko_cfg(eng):
    """styles.knockout_match, when this is a knockout-only match and it is on, else None."""
    c = (eng.rules.get("styles") or {}).get("knockout_match") or {}
    return c if c.get("enabled", False) and ko_match(eng) else None


def move_mult(eng, f, d, m, sit=None):
    """How much more (or less) her styles make her reach for move m now (1 = no change). In a knockout-only match
    (styles.knockout_match) everyone reaches for her heavier blows, and no style steers her off them."""
    kc = ko_cfg(eng)
    st = of(eng, f)
    if not st and not kc:
        return 1.0
    sit = situation(eng, f, d) if sit is None else sit
    cl = classes(eng, f, m)
    if kc:
        k0 = float(kc.get("big", 1.6)) if "big" in cl else float(kc.get("quick", 0.85)) if "quick" in cl else 1.0
        k0 *= float(kc.get("status", 0.6)) if "status" in cl else 1.0
        if not st:
            return k0
    k = 1.0
    for name, wt in st.items():
        sp = spec(eng, name)
        tables = [sp.get("moves") or {}] + [t for when, t in (sp.get("when") or {}).items()
                                           if when in sit and isinstance(t, dict)]
        for tb in tables:
            for c_, x in tb.items():
                if c_ in cl:
                    if kc and c_ == "big" and float(x) < 1.0:
                        continue      # (a knockout match: no style talks her out of a heavy blow)
                    k *= 1.0 + (float(x) - 1.0) * wt
        if name == "dismantler":
            # heavy blows to soften a fresh part, cutting ones once it is worn
            p = dismantle_target(eng, f, d)
            if p and p in d.parts:
                fresh = eng.condition(d.parts[p]) >= num(eng, name, "soft_at", 55)
                if fresh and "breaker" in cl:
                    k *= 1.0 + num(eng, name, "breaker_first", 0.6) * wt
                elif not fresh and "cutter" in cl:
                    k *= 1.0 + num(eng, name, "cut_worn", 0.8) * wt
    if kc:
        k *= k0
    return max(0.1, min(4.0, k))


def chance_mult(eng, f, key):
    """grab / chain / pummel / feint / launch: how much likelier her styles make it (1 = as it is)."""
    k = 1.0
    for name, wt in of(eng, f).items():
        x = (spec(eng, name).get("chances") or {}).get(key)
        if x is not None:
            k *= 1.0 + (float(x) - 1.0) * wt
    return max(0.0, k)


# ---------------------------------------------------------------------------------------------------------- aiming

def dismantle_target(eng, f, d):
    """The one part a dismantler is taking apart: kept until it has given (styles.list.dismantler.done_at damage),
    then the part beside it that is least hurt so far, and so on. The first comes from her game plan if she has one,
    else a leg (take her legs and the rest follows)."""
    from engine import neighbor_parts, body_region
    if w(eng, f, "dismantler") <= 0:
        return None
    mem = eng.__dict__.setdefault("style_aim", {})
    key = f"{f.name}|{d.name}"
    cur = mem.get(key)
    done = num(eng, "dismantler", "done_at", 170)
    if cur in d.parts and d.parts[cur].damage < done:
        return cur
    parts = list(d.parts)
    nxt = None
    if cur in d.parts:
        same, near = neighbor_parts(parts, cur)
        cands = [p for p in same + near if d.parts[p].damage < done and body_region(p) != "tail"]
        if cands:
            nxt = min(cands, key=lambda p: (d.parts[p].damage, cands.index(p)))
    if nxt is None:
        plan = eng.game_plan(f.name) if hasattr(eng, "game_plan") else None
        pool = [p for p in ((plan or {}).get("parts") or []) if p in d.parts and d.parts[p].damage < done]
        if not pool:
            pool = [p for p in parts if body_region(p) in ("fore_up", "fore_low", "hind_up", "hind_low", "shoulder")
                    and d.parts[p].damage < done and not re.search(r"(?i)paw|foot|fin|hand", p)]
        pool = pool or [p for p in parts if d.parts[p].damage < done] or parts
        nxt = pool[zlib.crc32(f"{f.name}|{d.name}|{len(mem)}".encode()) % len(pool)]
    mem[key] = nxt
    return nxt


def aim_part(eng, f, d, m, part, roll=None):
    """Where her styles move a blow aimed at `part` (or None to leave it): (new part, which style, why). Rolled
    from the fight's state, never its dice."""
    from engine import body_region
    st = of(eng, f)
    if not st or not d.parts:
        return None
    roll = _roll(eng, f.name, d.name, m.get("name") if m else "", part or "") if roll is None else roll
    opts = []
    for name, wt in st.items():
        ch = num(eng, name, "aim", 0.0) * wt
        if ch > 0:
            opts.append((name, ch))
    if not opts:
        return None
    # the strongest pull wins the roll first; the roll is spent through them in turn
    opts.sort(key=lambda x: -x[1])
    acc = 0.0
    pick = None
    for name, ch in opts:
        acc += ch * (1.0 - acc)
        if roll < acc:
            pick = name
            break
    if not pick:
        return None
    parts = list(d.parts)
    if pick == "dismantler":
        t = dismantle_target(eng, f, d)
        return (t, pick, "the part she is taking apart") if t and t != part else None
    if pick == "opportunist":
        hurt = sorted(parts, key=lambda p: -d.parts[p].damage)
        if hurt and d.parts[hurt[0]].damage >= num(eng, pick, "hurt_from", 60) and hurt[0] != part:
            return hurt[0], pick, "her worst-hurt part"
        return None
    if pick == "wear_down":
        # somewhere still fresh: she spreads the punishment over all of her
        fresh = sorted(parts, key=lambda p: (-eng.condition(d.parts[p]), p))[:6]
        if part in fresh or not fresh:
            return None
        return fresh[int(roll * 997) % len(fresh)], pick, "somewhere still fresh"
    regs = AIM_REGIONS.get(pick)
    if regs:
        if part and body_region(part) in regs:
            return None
        cands = [p for p in parts if body_region(p) in regs]
        if not cands:
            return None
        weights = [regs[body_region(p)] * (1.0 + d.parts[p].damage / 150.0) for p in cands]
        x = (roll * 7919) % 1.0 * sum(weights)
        for p, wt in zip(cands, weights):
            x -= wt
            if x <= 0:
                return p, pick, {"head_hunter": "her head", "body_worker": "her body",
                                 "hobbler": "her legs"}[pick]
        return cands[-1], pick, "her legs"
    return None


# ------------------------------------------------------------------------------------------------- engine effects

def power_mods(eng, a, d, move, plan, powers):
    """The engine side of a blow's styles, on the powers of the parts it lands on: (new powers, notes for the story).
    dismantler: the part she is taking apart takes the brunt, the parts round it less. setup_artist: a big blow let
    go at point-blank on a fighter who is down, held, pinned or driven against something. ground_pounder: blows on a
    fighter who is down."""
    st = of(eng, a)
    if not st or not plan or not powers:
        return powers, []
    notes = []
    powers = list(powers)
    sit = situation(eng, a, d)
    cl = classes(eng, a, move)
    wt = st.get("dismantler", 0.0)
    if wt and len(plan) > 1 and plan[0] == dismantle_target(eng, a, d):
        b, s = num(eng, "dismantler", "brunt", 0.3) * wt, num(eng, "dismantler", "shed", 0.35) * wt
        powers = [round(pw * (1 + b if i == 0 else 1 - s), 2) for i, pw in enumerate(powers)]
        rest = plan[1:3]
        notes.append(f"she aims it at the one part she is taking apart, {poss(d.name)} {plan[0]}: that part takes the "
                     f"brunt, and the {' and the '.join(rest)} {'is' if len(rest) == 1 else 'are'} only caught by the "
                     f"edge of it")
    elif wt and plan[0] == dismantle_target(eng, a, d):
        notes.append(f"she keeps working the same part, {poss(d.name)} {plan[0]}, the one she is taking apart")
    wt = st.get("setup_artist", 0.0)
    if wt and "big" in cl and sit & {"down", "pinned", "grab", "holding", "against"}:
        k = 1.0 + num(eng, "setup_artist", "point_blank", 0.15) * wt
        powers = [round(pw * k, 2) for pw in powers]
        # (only the engine's own grind, a held stream or a blow driven home against something, is told as a grind:
        # its notes say so; this one says why it is let go now)
        where = ("with her down under it" if sit & {"down", "pinned"} else
                 "with her pressed against something" if "against" in sit else "with her held, nowhere to go")
        notes.append(f"the payoff of her setup: the big one let go at point-blank, {where}")
    wt = st.get("ground_pounder", 0.0)
    if wt and "close" in cl and sit & {"down", "pinned"}:
        k = 1.0 + num(eng, "ground_pounder", "on_down", 0.08) * wt
        powers = [round(pw * k, 2) for pw in powers]
        notes.append("she stays on top of her and pounds her where she lies")
    return powers, notes


def wear_mult(eng, a, move):
    """wear_down: her heavy blows wear a part's resistance down further."""
    wt = w(eng, a, "wear_down")
    if not wt or not move or "breaker" not in classes(eng, a, move):
        return 1.0
    return 1.0 + num(eng, "wear_down", "wear", 0.3) * wt


def counter_mult(eng, d):
    """counter_puncher: her counters after a dodge."""
    wt = w(eng, d, "counter_puncher")
    return 1.0 + num(eng, "counter_puncher", "counter", 0.4) * wt if wt else 1.0


def opening_mult(eng, a, d):
    """opportunist: a devastating blow is likelier when her opponent is caught open (down, staggered, off balance)."""
    wt = w(eng, a, "opportunist")
    if not wt or not situation(eng, a, d) & {"down", "open", "against"}:
        return 1.0
    return 1.0 + num(eng, "opportunist", "devastating", 0.35) * wt


def slip_mult(eng, d):
    """out_fighter: she slips grabs more often (she hates being held)."""
    wt = w(eng, d, "out_fighter")
    return 1.0 + num(eng, "out_fighter", "slip", 0.25) * wt if wt else 1.0


def poss(name):
    from engine import poss_word
    return poss_word(name)


# --------------------------------------------------------------------------------------------------------- director

def strength_word(x):
    return "above all" if x >= 0.8 else "strongly" if x >= 0.6 else "often" if x >= 0.35 else "now and then"


def hint(eng):
    """For the director: each fighter's styles in a line, and what they point her at right now."""
    if not cfg(eng) and not ko_cfg(eng):
        return ""
    out = []
    if ko_cfg(eng):
        out.append("KNOCKOUT MATCH: only a knockout ends this, so both of them reach for their HEAVY blows (their "
                   "biggest moves, full-power strikes to the head and body) far more than light, quick ones; whatever "
                   "their styles, they don't hold back the big ones.")
    for f in eng.active():
        st = of(eng, f)
        if not st:
            continue
        foes = [x for x in eng.active() if x.name != f.name and (not x.team or x.team != f.team)]
        if not foes:
            continue
        d = foes[0]
        names = sorted(st.items(), key=lambda kv: -kv[1])
        about = "; ".join(f"{spec(eng, n).get('label', n.replace('_', ' '))} ({strength_word(x)})" for n, x in names[:4])
        now = []
        sit = situation(eng, f, d)
        t = dismantle_target(eng, f, d)
        if t:
            pt = d.parts[t]
            soft = eng.condition(pt) < num(eng, "dismantler", "soft_at", 55)
            now.append(f"she is taking apart {poss(d.name)} {t} ({pt.damage:.0f}% damage"
                       + (", worn soft" if soft else ", still sound") + "): her blows go there, "
                       + ("cutting ones now (claws, blades, teeth) to tear into it" if soft else
                          "heavy ones first to soften it")
                       + ", the parts round it only jarred; once it gives, the part beside it is next")
        if st.get("setup_artist") and sit & {"down", "pinned", "grab", "holding", "against"}:
            big = [m for m in f.moves if "big" in classes(eng, f, m) and f.move_uses.get(m["name"], 1) > 0]
            if big:
                stream = next((m for m in big if m.get("sustainable")), None)
                downish = bool(sit & {"down", "pinned"})
                now.append(f"her setup has paid off ({d.name} is {'down' if downish else 'held'}): this is when she "
                           f"lets {big[0]['name']} go at point-blank"
                           + (f" (or holds {stream['name']} on her, \"sustain\" 2-3 with \"pinned_against\" the "
                              f"ground under her, grinding her into it)" if stream and downish else ""))
        elif st.get("setup_artist", 0) >= 0.4:
            now.append("she builds to her big blows: a takedown, a grab or a charge into something first")
        if st.get("grappler", 0) >= 0.4 and not sit & {"grab", "holding", "pinned"}:
            now.append("she wants hold of her: a grab, a bind, a takedown, then close blows from inside it")
        elif st.get("grappler") and sit & {"grab", "holding"}:
            now.append("she has hold of her: short close blows from inside the grip, never letting go to strike from range")
        if st.get("opportunist") and sit & {"down", "open", "against"}:
            now.append(f"{d.name} is caught open: an opportunist goes for the big blow NOW")
        if st.get("ground_pounder") and sit & {"down", "pinned"}:
            now.append(f"{d.name} is down: she stays on top and pounds her there rather than let her up")
        if st.get("out_fighter") and sit & {"grab", "holding"}:
            now.append("she hates being this close: she wants out and back to range")
        line = f"FIGHTING STYLE: {f.name}: {about}."
        if now:
            line += " Right now: " + "; ".join(now[:3]) + "."
        out.append(line)
    return "\n".join(out)


def describe(eng, f):
    """One line for her card or the stat block: her styles by name."""
    st = of(eng, f)
    if not st:
        return ""
    return ", ".join(spec(eng, n).get("label", n.replace("_", " ")) for n, _ in sorted(st.items(), key=lambda kv: -kv[1]))


# ------------------------------------------------------------------------------------------- the Profiles sheet
# (since build 339) what each trait, quirk, style and reaction does in a fight, in plain words, for the Profiles window

TRAIT_WHAT = {
    "speed": "dodging, countering after a dodge, and meeting a move with her own",
    "hold": "how hard her grips bite when they close, and how hard they are to break",
    "escape": "breaking holds and getting out from under pins",
    "toughness": "keeping her feet: how easily blows stagger or rock her",
    "stamina": "what her moves cost her in energy",
    "striking": "landing where she aims, and her chance of a devastating blow",
    "learning": "reading an opponent's move (at 1.4 or more, after seeing it once instead of twice)",
}
QUIRK_WHAT = {
    "stubborn": "past her limit in a submission she holds out longer before tapping",
    "out_of_depth": "new to submission holds: she escapes them poorly at first, better each time she's caught",
    "cocky": "after a big blow of hers, her next attack may overreach (sloppy, half force, off balance)",
    "water_born": "in the water she is quicker and harder to hold",
    "ring_sense": "experience: she rarely overcommits when tired",
    "clinch_fighter": "holding someone, she lands short free blows far more often",
    "works_the_hold": "her holds tighten faster beat by beat",
    "predictable": "an opponent reads her moves after one sight of them",
    "weak_paw_grip": "her paws were never made for gripping: paw grips press lighter and break easier (jaws are fine)",
    "disaster_sense": "she feels the worst blows coming: devastating blows land on her less often",
    "ambusher": "her ambush moves land devastatingly far more often on someone staggered, off balance or down",
    "hates_water": "soaked or in the water she is slower and strikes worse",
    "overwhelming": "her big moves hit harder but are easier to see coming",
    "patient_constrictor": "stronger in a contest of coils",
    "unshakeable": "very hard to stagger or rock",
}
STYLE_WHAT = {
    "dismantler": "picks one part and keeps at it until it gives, then the part beside it: heavy blows to soften it, "
                  "cutting ones once it's worn; blows aimed elsewhere are pulled to it, and it takes the brunt when a "
                  "blow catches several parts",
    "grappler": "grabs and holds far more, and throws short close blows from inside the grip",
    "setup_artist": "knockdowns, grabs and charges first, then her biggest blow at point-blank (a little harder there)",
    "wear_down": "spreads heavy blows over every fresh part; they wear her opponent's resistance down further",
    "opportunist": "goes for the worst-hurt part, and for big blows the moment her opponent is caught open "
                   "(devastating blows likelier then)",
    "head_hunter": "aims for the head and neck",
    "body_worker": "aims for the ribs and belly",
    "hobbler": "aims for the legs, to take her opponent's footing",
    "swarmer": "fast and relentless: quick blows, chains and flurries",
    "counter_puncher": "counters after a dodge far more often",
    "out_fighter": "keeps to range, grabs little, and twists out of grabs",
    "ground_pounder": "stays on top of a downed opponent and pounds her there",
    "biter": "reaches for her jaws first, above all in close or with her opponent down",
    "trickster": "feints and misdirection: status moves and feints far more often",
    "thrower": "throws and slams far more often",
}
REACT_WHAT = {
    "stoic": "keeps the pain in: her reactions show smaller and quieter (never past real agony); under a pin she lies "
             "quiet and saves herself for a sudden heave, and wears down a little slower",
    "expressive": "shows everything: her reactions are a size bigger",
    "vocal": "the pain comes out of her mouth: cries and yelps",
    "quiet": "makes little sound, even hurt",
    "squirmer": "writhes and squirms with pain; never still under a pin (tries more, but tires faster)",
    "recoils": "jerks away from what hurts her",
    "curls": "folds round the hurt",
    "rigid": "locks up and goes still with pain",
    "lashes_out": "turns pain straight back on whoever did it: snarling, snapping",
}


def strength_of(x):
    x = float(x)
    return "very strong" if x >= 0.8 else "strong" if x >= 0.6 else "moderate" if x >= 0.35 else "slight"


def fighter_sheet(eng, f):
    """Everything about how she fights, as [(heading, [lines])], each line what it does in a fight. Things switched off
    in rules.json are marked so."""
    import reacts as _r
    out = []
    tcfg = eng.traits_cfg() if hasattr(eng, "traits_cfg") else True
    off = "" if tcfg else " (traits are switched off in rules.json)"
    lines = []
    for k, v in (f.traits or {}).items():
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if abs(v - 1.0) < 0.005:
            continue
        how = "better" if v > 1.0 else "worse"
        lines.append(f"{k.capitalize()} ×{v:g} ({how} than normal): {TRAIT_WHAT.get(k, k)}.")
    out.append(("Traits" + off, lines or ["All as normal."]))
    q = [f"{n.replace('_', ' ').capitalize()}: {QUIRK_WHAT.get(n, '')}." for n in (f.quirks or [])]
    out.append(("Quirks" + off, q or ["None."]))
    fav = sorted(((m, float(w)) for m, w in (f.favors or {}).items() if float(w) > 1), key=lambda kv: -kv[1])
    rare = [m for m, w in (f.favors or {}).items() if float(w) < 1]
    mv = []
    if f.style:
        mv.append(f.style)
    if fav:
        mv.append("Reaches most for: " + ", ".join(m for m, _ in fav[:6]) + ".")
    if rare:
        mv.append("Seldom uses: " + ", ".join(rare[:6]) + ".")
    out.append(("Style and favourite moves", mv or ["No particular favourites."]))
    sc = cfg(eng)
    raw = {k: v for k, v in (getattr(f, "fighting", None) or {}).items() if not str(k).startswith("_")}
    st = []
    for k, v in sorted(raw.items(), key=lambda kv: -float(kv[1])):
        sp = ((eng.rules.get("styles") or {}).get("list") or {}).get(k) or {}
        label = sp.get("label", k.replace("_", " "))
        st.append(f"{label[0].upper() + label[1:]}, {strength_of(v)} ({float(v):g}): {STYLE_WHAT.get(k, '')}."
                  + ("" if sp.get("enabled", True) else " (switched off)"))
    out.append(("Fighting styles" + ("" if sc else " (switched off in rules.json)"),
                st or ["None set (fighters.json \"fighting\")."]))
    rc = _r.cfg(eng)
    tr = _r.traits(f)
    rx = [f"{k.replace('_', ' ').capitalize()}, {strength_of(v)} ({float(v):g}): {REACT_WHAT.get(k, '')}."
          for k, v in sorted(((k, v) for k, v in tr.items() if k != "sensitive"), key=lambda kv: -float(kv[1]))]
    sens = tr.get("sensitive") or {}
    if isinstance(sens, dict) and sens:
        def word(k):
            # a kind of damage, or a word in a part's name (her tail, her ears)
            return f"{k} (×{float(sens[k]):g})" if k in _r.KIND_MOVES else f"hits to her {k} (×{float(sens[k]):g})"
        more = [k for k, v in sens.items() if float(v) > 1]
        less = [k for k, v in sens.items() if float(v) < 1]
        if more:
            rx.append("Reacts more to: " + ", ".join(word(k) for k in more) + ".")
        if less:
            rx.append("Reacts less to: " + ", ".join(word(k) for k in less) + ".")
    if rc and (rc.get("finished") or {}).get("enabled"):
        rx.append("Like everyone, a big reaction when she is low can leave her FINISHED for a beat or two: down, wide "
                  "open to a pin, a submission or a knockout. Hers would look like "
                  + {"still": "lying still and staring", "agony": "curling round the pain",
                     "thrash": "thrashing on the ground"}[_finished_kind(f)] + ".")
    out.append(("Reactions to being hurt" + ("" if rc else " (switched off in rules.json)"),
                rx or ["None set (fighters.json \"reacting\")."]))
    # at a glance: her strongest style and her strongest way of taking pain, in one line, first
    glance = []
    if raw:
        k0 = max(raw, key=lambda k: float(raw[k]))
        sp0 = ((eng.rules.get("styles") or {}).get("list") or {}).get(k0) or {}
        glance.append("fights by " + {"dismantler": "taking her opponent apart one part at a time",
                                       "grappler": "grabbing and holding",
                                       "setup_artist": "setting up her big blows",
                                       "wear_down": "wearing her opponent down all over",
                                       "opportunist": "waiting for an opening and punishing it",
                                       "head_hunter": "going for the head", "body_worker": "working the body",
                                       "hobbler": "taking her opponent's legs", "swarmer": "swarming her opponent with fast blows",
                                       "counter_puncher": "countering", "out_fighter": "keeping her distance",
                                       "ground_pounder": "pounding a downed opponent", "biter": "biting",
                                       "trickster": "feints and tricks", "thrower": "throws and slams"}.get(
            k0, sp0.get("label", k0)))
    rt = {k: float(v) for k, v in tr.items() if k != "sensitive"}
    if rt:
        k1 = max(rt, key=rt.get)
        glance.append({"stoic": "hides her pain", "expressive": "shows every hurt", "vocal": "cries out when hurt",
                       "quiet": "makes little sound when hurt", "squirmer": "squirms and writhes when hurt",
                       "recoils": "jerks away from pain", "curls": "curls round her hurts", "rigid": "locks up when hurt",
                       "lashes_out": "turns pain into fury"}.get(k1, k1))
    fav1 = fav[0][0] if fav else ""
    if glance or fav1:
        line = f"{f.name} " + " and ".join(glance) + (f"; her favourite move is {fav1}" if fav1 else "") + "."
        out.insert(0, ("At a glance", [line]))
    return out


def _finished_kind(f):
    import reacts as _r
    tr = _r.traits(f)
    moves = {mv: float(tr.get(t, 0) or 0) for t, mv in _r.TRAIT_MOVE.items()}
    top = max(moves, key=moves.get) if any(moves.values()) else "curl"
    kind = _r.NATURE_FINISHED.get(top, "agony")
    if float(tr.get("stoic", 0) or 0) >= 0.5 and kind == "thrash":
        kind = "still"
    return kind
