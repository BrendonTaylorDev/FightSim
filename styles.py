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


def move_mult(eng, f, d, m, sit=None):
    """How much more (or less) her styles make her reach for move m now (1 = no change)."""
    st = of(eng, f)
    if not st:
        return 1.0
    sit = situation(eng, f, d) if sit is None else sit
    cl = classes(eng, f, m)
    k = 1.0
    for name, wt in st.items():
        sp = spec(eng, name)
        tables = [sp.get("moves") or {}] + [t for when, t in (sp.get("when") or {}).items()
                                           if when in sit and isinstance(t, dict)]
        for tb in tables:
            for c_, x in tb.items():
                if c_ in cl:
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
    if not cfg(eng):
        return ""
    out = []
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
