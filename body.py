"""body (since build 314): parts of her body the engine now keeps as running numbers, beat by beat, instead of
deciding them with one roll. The dice are still in it (how hard a blow was, how hard she fought); these are what
the dice act on. Each is its own switch in rules.json (body.<name>.enabled), and each is told to the story and shown
on her card.

- air: how much breath she has in her, 0 to 100. Fighting hard spends it, a choke cuts it off, coils squeezing her
  chest let her take only shallow breaths, being winded or coughing up water costs her some; breathing freely brings
  it back fast. Short of air she hits softer, dodges slower and gets her energy back slower. Under a choke she
  passes out when it runs out (it replaces the choke's fixed count of beats).
- footing (since build 319): how steady she is on her feet; see _footing_tick.
- limbs: how tired each limb is, 0 to 100: her arms, legs, jaws, head, tail and wings. Every blow thrown with a
  limb tires it, and every beat she holds a grip with it; a limb she isn't using recovers. A tired limb throws
  weaker blows, and a grip held with tired limbs is easier to break.

Its state lives in f.learned["body"] (saved and undone with the fighter)."""

import re

# what a move is thrown with (engine.LIMB_KINDS) and what a grip holds with (engine.GRIP_LIMBS) -> the limb that tires
MOVE_LIMB = {"bite": "jaws", "beak": "head", "horn": "head", "arm": "arms", "leg": "legs", "talon": "legs",
             "tail": "tail", "wing": "wings", "charge": "legs"}
GRIP_LIMB = {"jaws": "jaws", "feet": "legs", "legs": "legs", "paws": "arms", "arms": "arms", "tails": "tail",
             "wings": "wings", "talons": "legs", "horn": "head"}
LIMB_WORD = {"arms": "arms", "legs": "legs", "jaws": "jaws", "head": "neck and head", "tail": "tail",
             "wings": "wings"}

DEFAULTS = {
    "air": {"enabled": True, "regen": 14, "spent_regen": 0.6, "per_energy": 0.5, "choke": 16, "coils": 8,
            "winded": 6, "low": 40, "power_min": 0.8, "dodge_min": 0.8, "regen_min": 0.5, "short": 35, "starved": 15,
            "chokes": True, "out_from": 15, "out_max": 0.85, "health_drain": 0.3, "blood_choke": 20,
            "blood_back": 40, "blood_default": True, "pin_choke": 0.35},
    "heart": {"enabled": True, "exert": 0.45, "pain": 0.3, "air": 0.35, "max": 1.85, "rise": 0.5, "settle": 0.2,
              "wobble": 0.02},
    "blood": {"enabled": True, "per_damage": 0.025, "part_max": 1.6, "clot": 0.72, "held_clot": 0.9, "regen": 0.15,
              "floor": 55, "low": 85, "power_min": 0.88, "dodge_min": 0.88, "pale": 80, "faint": 68, "bleeding": 0.5,
              "heart": 0.6},
    "adrenaline": {"enabled": True, "per_loss": 4.0, "held": 6, "low_health": 40, "low_rate": 0.5, "decay": 0.8,
                   "power": 0.06, "pain": 0.25, "heart": 0.35, "high": 55, "crash_from": 60, "crash_below": 25,
                   "crash_beats": 3, "crash_regen": 0.7},
    "tissue": {"enabled": True, "per_damage": 0.6, "kinds": {"blunt": 1.0, "grip": 0.8, "bite": 0.6, "claw": 0.5,
                                                             "burn": 0.4, "shock": 0.2, "cold": 0.3},
               "rise": 0.35, "fade": 0.97, "from": 35, "power_min": 0.85, "dodge_legs": 0.15, "swollen": 55},
    "bones": {"enabled": True, "during_from": 320, "during_chance": 0.012, "end_from": 220, "end_span": 180,
              "end_chance": 0.5, "end_max": 0.6, "coil_mult": 1.6, "trapped_mult": 1.4, "blunt_mult": 1.5,
              "cut_mult": 0.5, "max_end": 2, "power_mult": 0.6, "dodge_legs": 0.8},
    "footing": {"enabled": True, "per_damage": 0.18,
                "regions": {"hind_low": 1.6, "hind_up": 1.3, "head": 1.4, "neck": 1.0, "fore_low": 0.6, "tail": 0.4},
                "region_other": 0.8, "kinds": {"blunt": 1.2, "blast": 1.3, "grip": 0.6, "bite": 0.7, "claw": 0.5,
                                               "burn": 0.5, "shock": 0.9, "cold": 0.6},
                "plans": {"biped": 1.0, "avian": 1.0, "quadruped": 0.75, "serpent": 0.5}, "stagger": 18,
                "off_balance": 10, "regen": 16, "getup": 55, "slick_top": 85, "dazed_top": 70, "faint_top": 75,
                "low": 60, "power_min": 0.9, "dodge_min": 0.85, "stumble": 0.6, "keep_feet": 0.5, "slip": 1.0,
                "unsteady": 35},
    "limbs": {"enabled": True, "strike": 7, "grip": 5, "rest": 6, "from": 30, "power_min": 0.75, "grip_break": 0.6,
              "dodge_legs": 0.25, "tired": 55},
}

# the statuses that tell it (looked at by the narrator, the stat lines and the card)
LOOK = {
    "short_of_air": "SHORT OF AIR: she can't get enough breath in; her mouth is open, every breath ragged, her blows "
                    "and her feet slower for it",
    "starved_of_air": "STARVED OF AIR: her lungs burning, her sight swimming, she can hardly think past the next "
                      "breath; everything she does is slow and heavy",
    "tired_arms": "her ARMS HEAVY with use: her blows with them slower and weaker, her grip with them loosening",
    "tired_legs": "her LEGS HEAVY with use: her kicks weaker, her feet slower, a step behind when she dodges",
    "tired_jaws": "her JAWS ACHING from biting and holding on: her bites weaker, her grip with her teeth loosening",
    "tired_head": "her NECK AND HEAD aching from the blows she has thrown with them: weaker each time",
    "tired_tail": "her TAIL HEAVY with use: its strikes weaker, its grip loosening",
    "tired_wings": "her WINGS HEAVY with use: their beats weaker, their strikes softer",
    "bleeding": "BLEEDING: blood running from her open wounds, matting her fur and dripping",
    "pale": "PALE from the blood she has lost: her gums and the skin inside her ears gone pale, her heart quick",
    "light_headed": "LIGHT-HEADED from the blood she has lost: the world tilting, her legs unsure, a cold sweat",
    "keyed_up": "KEYED UP: adrenaline running hot, the pain dulled and far away, everything sharp and fast",
    "adrenaline_crash": "the ADRENALINE CRASH: the rush gone out of her, shaky and heavy, the pain flooding back",
    "unsteady": "UNSTEADY: her feet not under her, her weight in the wrong place, swaying as she tries to set "
                "herself",
    "swollen": "SWELLING: the beaten part puffed up, hot and tight, stiff to move",
    "broken_bone": "a BROKEN BONE: the limb held close and useless, a deep hot ache, any weight on it agony",
}
STORY = {
    "short_of_air": ("her mouth open, her breaths quick and ragged and never quite enough",
                     "she can't get enough air in, and everything she does is slower for it",
                     "{other} hears her breathing"),
    "starved_of_air": ("her lungs burning, her sight swimming, every breath a gasp",
                       "she can hardly think past the next breath", "{other} sees how she gasps"),
    "tired_arms": ("her arms heavy, slower to come up", "every blow with them costs more than the last",
                   "{other} sees them dropping"),
    "tired_legs": ("her legs heavy, her feet a step slow", "she has to think about every step",
                   "{other} sees her flat-footed"),
    "tired_jaws": ("her jaws aching from biting and holding on", "her bite has lost its strength",
                   "{other} feels the bite weaker"),
    "tired_head": ("her neck stiff and aching from the blows thrown with her head", "each one costs her more",
                   ""),
    "tired_tail": ("her tail heavy, slower to swing", "it doesn't answer as it did", "{other} sees it drag"),
    "tired_wings": ("her wings heavy, each beat a labour", "she can feel them failing her", "{other} sees them falter"),
    "bleeding": ("blood running from her wounds, matting her fur, dripping where she moves",
                 "she can feel it warm and wet, and every movement opens them a little", "{other} sees the blood"),
    "pale": ("pale under her fur, her gums gone pale, her heart quick and light", "a cold, hollow feeling creeping in",
             "{other} sees how pale she has gone"),
    "light_headed": ("swaying, blinking, a cold sweat on her", "the ground won't stay level under her",
                     "{other} sees her unsteady"),
    "keyed_up": ("eyes wide and bright, quick and twitchy, the pain hardly touching her", "everything is sharp and slow "
                 "and she feels she could go on for ever", "{other} sees the wild light in her"),
    "adrenaline_crash": ("the fire gone out of her: shaky, heavy-limbed, the pain all coming back at once",
                         "everything she pushed away catches up with her", "{other} sees her sag"),
    "broken_bone": ("the broken limb held close, useless", "every movement jars it", "{other} sees she can't use it"),
    "unsteady": ("her feet not quite under her, swaying as she tries to plant them", "the ground feels wrong under "
                 "her, and she can't set herself", "{other} sees her sway"),
    "swollen": ("the beaten part puffed up, hot and tight under the fur", "it is stiff and won't move as it should",
                "{other} sees the swelling"),
}
ENDS = {"unsteady": "she gets her feet under her again", "bleeding": "the bleeding slows and stops", "pale": "some colour comes back into her",
        "light_headed": "the world steadies", "keyed_up": "the rush ebbs", "adrenaline_crash": "she steadies",
        "swollen": "the swelling eases a little", "broken_bone": "it is set and starts to heal",
        "short_of_air": "she gets her breath back", "starved_of_air": "air comes back into her",
        "tired_arms": "her arms have come back to her", "tired_legs": "her legs have come back to her",
        "tired_jaws": "her jaws have come back to her", "tired_head": "her neck has eased",
        "tired_tail": "her tail has come back to her", "tired_wings": "her wings have come back to her"}
WORD = {k: k.replace("_", " ") for k in LOOK}
ICON = {"unsteady": "🌀", "bleeding": "🩸", "pale": "🫥", "light_headed": "😵‍💫", "keyed_up": "⚡", "adrenaline_crash": "📉",
        "swollen": "🔴", "broken_bone": "🦴", "short_of_air": "😮‍💨", "starved_of_air": "🫁", "tired_arms": "💪", "tired_legs": "🦵", "tired_jaws": "🦷",
        "tired_head": "🤕", "tired_tail": "〰️", "tired_wings": "🪽"}


def cfg(eng, part):
    """body.<part> with its defaults, or None when it (or body as a whole) is off."""
    b = (eng.rules.get("body") or {})
    if b.get("enabled", True) is False:
        return None
    c = dict(DEFAULTS.get(part) or {}, **(b.get(part) or {}))
    return c if c.get("enabled", True) else None


def state(f):
    st = f.learned.setdefault("body", {})
    st.setdefault("air", 100.0)
    st.setdefault("limbs", {})
    return st


def on_damage(eng, d, part, added, source):
    """(since build 318) A part hurt by `added` damage: a cut or a bite opens it to bleed (body.blood), and any blow
    starts it swelling over the next beats (body.tissue), each by what did it."""
    cb, ct, cf = cfg(eng, "blood"), cfg(eng, "tissue"), cfg(eng, "footing")
    if not cb and not ct and not cf and not cfg(eng, "bones"):
        return
    kind = eng.wound_kind(source)
    st = state(d)
    if cf and _on_feet(eng, d):
        k = float((cf.get("regions") or {}).get(_region(part), cf["region_other"])) \
            * float((cf.get("kinds") or {}).get(kind, 0.8)) * float((cf.get("plans") or {}).get(eng.body_plan(d), 1.0))
        knock = float(cf["per_damage"]) * added * k / max(0.5, float(eng.trait(d, "toughness")))
        st["footing"] = round(max(0.0, float(st.get("footing", 100.0)) - knock), 1)
    if cb and kind in ("claw", "bite"):
        bl = st.setdefault("bleed", {})
        bl[part] = round(min(float(cb["part_max"]), float(bl.get(part, 0.0)) + float(cb["per_damage"]) * added), 3)
    if ct:
        k = float((ct.get("kinds") or {}).get(kind, 0.5))
        sw = st.setdefault("swell_to", {})
        sw[part] = round(min(100.0, float(sw.get(part, 0.0)) + float(ct["per_damage"]) * k * added), 1)
    during_fracture(eng, d, part, added, kind)


NO_FRACTURE = re.compile(r"(?i)\b(?:spine|back|neck|throat|vertebra|skull)\b")


def can_break(eng, part):
    """A part whose bone may break (body.bones): it has a bone in it (not her belly, an ear, a fin...), and it is not
    her spine, back, neck or skull: no break here is ever one that would leave her paralysed or worse."""
    return not eng.BONELESS.search(part) and not NO_FRACTURE.search(part)


def poss_word(name):
    from engine import poss_word as _pw
    return _pw(name)


def _break(eng, d, part, why, end=False):
    fr = d.learned.setdefault("fractures", {})
    if part in fr:
        return False
    fr[part] = eng.turn
    eng.set_status(d, "broken_bone", 999)
    eng._pending_events.append({"type": "fracture", "fighter": d.name, "part": part, "why": why, "end": end})
    return True


def during_fracture(eng, d, part, added, kind):
    """Very rarely a blow or a grip breaks a bone in the fight itself: only when it takes the part past during_from
    damage, during_chance of the time (blunt and crushing x blunt_mult, cuts x cut_mult), at most once a fight."""
    c = cfg(eng, "bones")
    if not c or d.learned.get("fractures") or d.eliminated or not can_break(eng, part):
        return
    p = d.parts.get(part) if hasattr(d.parts, "get") else None
    if p is None or p.damage < float(c["during_from"]) or p.damage - added >= float(c["during_from"]) or added < 10:
        return
    ch = float(c["during_chance"]) * (float(c["blunt_mult"]) if kind in ("blunt", "grip") else
                                      float(c["cut_mult"]) if kind in ("claw", "bite") else 1.0)
    if eng._chance(min(0.5, ch), f"{poss_word(d.name)} {part.lower()} breaking under it", "IT BREAKS", "it holds"):
        _break(eng, d, part, "the blow")


def end_fractures(eng, d):
    """At the end of her match (body.bones): bones the fight has worn past breaking may be found broken. Each bone
    part past end_from damage, end_chance x how far past it over end_span (at most end_max), x coil_mult for her ribs
    or chest inside coils, x trapped_mult for a limb held in a grip at the end; at most max_end of them. Never her
    spine or neck; it all heals."""
    c = cfg(eng, "bones")
    if not c or d.learned.get("bones_checked"):
        return
    d.learned["bones_checked"] = True
    held = {h.part: h for h in eng.holds.values() if h.defender == d.name}
    coiled = any(h.coil and eng.coil_scope(h.part) == "body" for h in held.values())
    ring = set(eng.coil_ring_parts(d, [h for h in held.values() if h.coil])) if coiled else set()
    got = len(d.learned.get("fractures") or {})
    for p in sorted(d.parts.values(), key=lambda x: -x.damage):
        if got >= int(c["max_end"]):
            break
        if p.damage < float(c["end_from"]) or not can_break(eng, p.name):
            continue
        ch = float(c["end_chance"]) * min(1.0, (p.damage - float(c["end_from"])) / max(1.0, float(c["end_span"])))
        if coiled and (p.name in ring or re.search(r"(?i)\brib|chest", p.name)):
            ch *= float(c["coil_mult"])
        elif p.name in held:
            ch *= float(c["trapped_mult"])
        ch = min(float(c["end_max"]), ch)
        if ch > 0 and eng._chance(ch, f"{poss_word(d.name)} {p.name.lower()} found broken after the match",
                                  "BROKEN", "only bruised"):
            if _break(eng, d, p.name, "what the match did to it", end=True):
                got += 1


def _limb_of_move(eng, move):
    if not move or eng.is_ranged(move) or move.get("target") in ("whole_body", "status", "hold", "self"):
        return None
    text = f"{move.get('name', '')} {move.get('about', '')}".lower()
    kind = next((k for k, rx in eng.LIMB_KINDS if rx and re.search(rx, text)), None)
    if kind is None and move.get("charge"):
        kind = "charge"
    return MOVE_LIMB.get(kind)


def on_attack(eng, a, move):
    """A blow thrown: the limb it was thrown with tires (body.limbs.strike, more for a heavier move)."""
    c = cfg(eng, "limbs")
    limb = _limb_of_move(eng, move) if c else None
    if not limb:
        return
    st = state(a)
    p = float(move.get("power") or 40)
    add = float(c["strike"]) * (0.6 + 0.4 * min(2.0, p / 40.0))
    st["limbs"][limb] = round(min(100.0, float(st["limbs"].get(limb, 0.0)) + add), 1)
    st.setdefault("used", {})[limb] = eng.turn


def _tired(c, x):
    """0 below `from`, rising to 1 at 100."""
    lo = float(c["from"])
    return max(0.0, min(1.0, (float(x) - lo) / max(1.0, 100.0 - lo)))


def power_mult(eng, a, move):
    """(label, multiplier) pairs for her blow: short of air, and the limb she throws it with tired."""
    out = []
    ca = cfg(eng, "air")
    st = a.learned.get("body") or {}
    if ca and float(st.get("air", 100)) < float(ca["low"]):
        m = float(ca["power_min"]) + (1 - float(ca["power_min"])) * float(st.get("air", 100)) / float(ca["low"])
        out.append(("short of air", round(m, 3)))
    cl = cfg(eng, "limbs")
    limb = _limb_of_move(eng, move) if cl and move else None
    if limb:
        t = _tired(cl, (st.get("limbs") or {}).get(limb, 0))
        if t > 0:
            out.append((f"her {LIMB_WORD[limb]} tired", round(1 - (1 - float(cl["power_min"])) * t, 3)))
    cb = cfg(eng, "blood")
    if cb and float(st.get("blood", 100)) < float(cb["low"]):
        out.append(("weak from the blood she has lost", round(_blood_k(cb, st, "power_min"), 3)))
    cd = cfg(eng, "adrenaline")
    if cd and float(st.get("adrenaline", 0)) > 5:
        out.append(("adrenaline", round(1 + float(cd["power"]) * float(st["adrenaline"]) / 100.0, 3)))
    if cd and a.status.get("adrenaline_crash"):
        out.append(("the adrenaline crash", 0.95))
    cf = cfg(eng, "footing")
    if cf and move and not eng.is_ranged(move) and _on_feet(eng, a) and _footing(a) < float(cf["low"]):
        out.append(("her feet not under her", round(_footing_k(cf, a, "power_min"), 3)))
    cbn = cfg(eng, "bones")
    limb3 = _limb_of_move(eng, move) if cbn and move else None
    if limb3 and any(_region(p) in LIMB_REGIONS.get(limb3, ())
                     for p in (a.learned.get("fractures") or {})):
        out.append((f"a broken bone in her {LIMB_WORD[limb3]}", float(cbn["power_mult"])))
    ct = cfg(eng, "tissue")
    limb2 = _limb_of_move(eng, move) if ct and move else None
    if limb2:
        sw = _limb_swelling(eng, a, limb2)
        t = max(0.0, min(1.0, (sw - float(ct["from"])) / max(1.0, 100.0 - float(ct["from"]))))
        if t > 0:
            out.append((f"her {LIMB_WORD[limb2]} swollen and stiff", round(1 - (1 - float(ct["power_min"])) * t, 3)))
    return out


LIMB_REGIONS = {"arms": ("fore_up", "fore_low", "shoulder"), "legs": ("hind_up", "hind_low"), "jaws": ("head",),
                "head": ("head", "neck"), "tail": ("tail",), "wings": ("fore_up", "fore_low", "shoulder")}


def _region(part):
    from engine import body_region
    return body_region(part)


def _limb_swelling(eng, f, limb):
    """The worst swelling on the parts a limb is made of (body.tissue)."""
    from engine import body_region
    sw = (f.learned.get("body") or {}).get("swell") or {}
    return max([float(v) for p, v in sw.items() if body_region(p) in LIMB_REGIONS.get(limb, ())] or [0.0])


def _blood_k(cb, st, key):
    lo, fl = float(cb["low"]), float(cb["floor"])
    t = max(0.0, min(1.0, (lo - float(st.get("blood", 100))) / max(1.0, lo - fl)))
    return 1 - (1 - float(cb[key])) * t


def pain_resist_mult(eng, f):
    """(body.adrenaline) adrenaline running: the pain counts for less against her (tap and resist checks)."""
    cd = cfg(eng, "adrenaline")
    if not cd:
        return 1.0
    return 1 + float(cd["pain"]) * float((f.learned.get("body") or {}).get("adrenaline", 0)) / 100.0


def dodge_mult(eng, d):
    m = 1.0
    st = d.learned.get("body") or {}
    ca = cfg(eng, "air")
    if ca and float(st.get("air", 100)) < float(ca["low"]):
        m *= float(ca["dodge_min"]) + (1 - float(ca["dodge_min"])) * float(st.get("air", 100)) / float(ca["low"])
    cl = cfg(eng, "limbs")
    if cl:
        m *= 1 - float(cl["dodge_legs"]) * _tired(cl, (st.get("limbs") or {}).get("legs", 0))
    cb = cfg(eng, "blood")
    if cb and float(st.get("blood", 100)) < float(cb["low"]):
        m *= _blood_k(cb, st, "dodge_min")
    cf = cfg(eng, "footing")
    if cf and _on_feet(eng, d) and _footing(d) < float(cf["low"]):
        m *= _footing_k(cf, d, "dodge_min")
    cbn = cfg(eng, "bones")
    if cbn and any(_region(p) in ("hind_up", "hind_low") for p in (d.learned.get("fractures") or {})):
        m *= float(cbn["dodge_legs"])
    ct = cfg(eng, "tissue")
    if ct:
        sw = _limb_swelling(eng, d, "legs")
        m *= 1 - float(ct["dodge_legs"]) * max(0.0, min(1.0, (sw - float(ct["from"])) / max(1.0, 100 - float(ct["from"]))))
    return m


def _on_feet(eng, f):
    """Standing on her own feet: not down, not in the air, not pinned (footing only counts then)."""
    return not (f.name in eng.downed or eng.has(f, "airborne") or eng.pinned_by(f.name))


def _footing(f):
    return float((f.learned.get("body") or {}).get("footing", 100.0))


def _footing_k(cf, f, key):
    lo = float(cf["low"])
    t = max(0.0, min(1.0, (lo - _footing(f)) / max(1.0, lo)))
    return 1 - (1 - float(cf[key])) * t


def footing_mult(eng, f, what):
    """(body.footing) How her footing changes a roll on her feet: "stumble" (a blow staggering her: x1 up to
    x1 + stumble with no footing left), "keep_feet" (staying up under a knockdown: x1 down to x1 - keep_feet) and
    "slip" (slipping on slick ground as she dodges: x1 up to x1 + slip)."""
    cf = cfg(eng, "footing")
    if not cf or not _on_feet(eng, f):
        return 1.0
    lost = 1.0 - _footing(f) / 100.0
    return 1 - float(cf["keep_feet"]) * lost if what == "keep_feet" else 1 + float(cf[what]) * lost


def regen_mult(eng, f):
    m = 1.0
    ca = cfg(eng, "air")
    a = float((f.learned.get("body") or {}).get("air", 100))
    if ca and a < float(ca["low"]):
        m *= float(ca["regen_min"]) + (1 - float(ca["regen_min"])) * a / float(ca["low"])
    cd = cfg(eng, "adrenaline")
    if cd and f.status.get("adrenaline_crash"):
        m *= float(cd["crash_regen"])
    return m


def grip_break_mult(eng, holder, holds):
    """How much easier her grip is to break with the limbs it holds with tired (x1 fresh)."""
    cl = cfg(eng, "limbs")
    if not cl or holder is None:
        return 1.0
    lm = (holder.learned.get("body") or {}).get("limbs") or {}
    worst = 0.0
    for h in holds:
        lb = eng.grip_limb(holder, h.with_part)
        limb = GRIP_LIMB.get(lb[0]) if lb else None
        if limb:
            worst = max(worst, _tired(cl, lm.get(limb, 0)))
    return 1 + float(cl["grip_break"]) * worst


def choke_air(eng, d, kinds=()):
    """For the choke's pass-out (body.air.chokes): (how far she has gone, where she can start to go under). A blood
    choke (the sides of her neck squeezed: kinds has "blood" or "both") goes by the blood reaching her head, which
    runs out within a few beats; an air choke (the windpipe pressed) by the air left in her. The one nearer the end
    counts."""
    ca = cfg(eng, "air")
    if not ca or not ca.get("chokes", True):
        return None
    st = d.learned.get("body") or {}
    a = float(st.get("air", 100))
    hb = float(st.get("head_blood", 100))
    lost = 100.0 - a
    if set(kinds) & {"blood", "both"}:
        lost = max(lost, 100.0 - hb)
    return lost, 100.0 - float(ca["out_from"])


def choke_out_chance(eng, d, kinds=()):
    ca = cfg(eng, "air")
    st = d.learned.get("body") or {}
    a = float(st.get("air", 100))
    if set(kinds) & {"blood", "both"}:
        a = min(a, float(st.get("head_blood", 100)))
    lo = float(ca["out_from"])
    if a > lo:
        return 0.0
    return min(float(ca["out_max"]), 0.15 + (float(ca["out_max"]) - 0.15) * (lo - a) / max(1.0, lo))


def tick(eng):
    """End of a beat, before her energy comes back: her air and her limbs, and the statuses that tell them."""
    ca, cl = cfg(eng, "air"), cfg(eng, "limbs")
    events = []
    if not any(cfg(eng, k) for k in DEFAULTS):
        return events
    for f in eng.fighters.values():
        if f.eliminated:
            continue
        st = state(f)
        if ca:
            spent = max(0.0, float(st.get("e_last", f.energy)) - float(f.energy))
            a = float(st["air"])
            choked = [h for h in eng.holds.values() if h.defender == f.name and not h.grab
                      and re.search(r"(?i)neck|throat", h.part)]
            coils = eng.compression_on(f) if eng.has(f, "constricted") and eng.compress_cfg() else 0.0
            share = max(0.0, min(1.0, eng._health_pct(f) / 100.0))
            loss = float(ca["per_energy"]) * spent
            # (since build 317) a grip on her neck that is part of a pin holds her down more than it chokes her:
            # it drains her at pin_choke of a choke's rate (a slow choke that ends her only if held long)
            pinners = set(eng.pinned_by(f.name) or ())
            pin_k = float(ca.get("pin_choke", 0.35)) if choked and all(h.attacker in pinners for h in choked) else 1.0
            if choked:
                tight = max(0.5, min(2.0, max(h.power for h in choked) / 16.0)) ** 0.5
                loss += float(ca["choke"]) * tight * (1 + float(ca["health_drain"]) * (1 - share)) * pin_k
            loss += float(ca["coils"]) * coils / 100.0
            if any(eng.has(f, s) for s in ("breathless", "sputtering", "throat_struck", "panicking")):
                loss += float(ca["winded"])
            # (since build 316) the blood to her head: a blood choke (the sides of her neck squeezed) cuts it off
            # fast, whatever air she has; free of it, it comes rushing back
            kinds = {eng._hold_choke_kind(h) for h in choked}
            hb = float(st.get("head_blood", 100.0))
            if kinds & {"blood", "both"}:
                tight = max(0.5, min(2.0, max(h.power for h in choked) / 16.0)) ** 0.5
                hb -= float(ca.get("blood_choke", 20)) * tight * (0.7 if "blood" not in kinds else 1.0) \
                    * (1 + float(ca["health_drain"]) * (1 - share)) * pin_k
            else:
                hb += float(ca.get("blood_back", 40))
            st["head_blood"] = round(max(0.0, min(100.0, hb)), 1)
            if choked and not (kinds & {"air", "both"}):
                # (a blood choke leaves her windpipe open: she can still breathe, if badly)
                loss -= float(ca["choke"]) * 0.75 * tight * pin_k
            gain = 0.0
            if not choked:
                gain = float(ca["regen"]) * (float(ca["spent_regen"]) if spent > 10 else 1.0)
                if coils:
                    gain *= max(0.2, 1 - coils / 100.0)
                if any(eng.has(f, s) for s in ("breathless", "sputtering", "throat_struck")):
                    gain *= 0.4
            st["air"] = round(max(0.0, min(100.0, a - loss + gain)), 1)
            now_ = ("starved_of_air" if st["air"] < float(ca["starved"]) else
                    "short_of_air" if st["air"] < float(ca["short"]) else None)
            for s_ in ("starved_of_air", "short_of_air"):
                if s_ != now_:
                    f.status.pop(s_, None)
            if now_:
                if now_ not in f.status:
                    events.append({"type": "reaction", "fighter": f.name, "status": now_, "beats": 1,
                                   "reaction": True, "why": "fighting hard and not getting enough breath"
                                   if not choked else "the grip on her throat"})
                eng.set_status(f, now_, 2)
        events += _blood_tick(eng, f, st)
        events += _adrenaline_tick(eng, f, st)
        events += _tissue_tick(eng, f, st)
        events += _footing_tick(eng, f, st)
        ch_ = cfg(eng, "heart")
        if ch_:
            _heart_tick(eng, f, st, ch_)
        if cl:
            used = st.get("used") or {}
            for h in eng.holds.values():
                if h.attacker == f.name and not h.coil:
                    lb = eng.grip_limb(f, h.with_part)
                    limb = GRIP_LIMB.get(lb[0]) if lb else None
                    if limb:
                        st["limbs"][limb] = round(min(100.0, float(st["limbs"].get(limb, 0)) + float(cl["grip"])), 1)
                        used[limb] = eng.turn
            rest = float(cl["rest"]) * (0.5 + 0.5 * max(0.0, min(1.0, f.energy / 100.0)))
            for limb in list(st["limbs"]):
                if used.get(limb) != eng.turn:
                    st["limbs"][limb] = round(max(0.0, float(st["limbs"][limb]) - rest), 1)
                s_ = "tired_" + limb
                if float(st["limbs"][limb]) >= float(cl["tired"]):
                    if s_ not in f.status:
                        events.append({"type": "reaction", "fighter": f.name, "status": s_, "beats": 1,
                                       "reaction": True, "why": f"using her {LIMB_WORD[limb]} so much"})
                    eng.set_status(f, s_, 2)
                elif s_ in f.status:
                    f.status.pop(s_, None)
            st["used"] = {k: v for k, v in used.items() if v == eng.turn}
    return events


def _status(eng, f, st_, on, why, events):
    """Put a body status on (with a reaction event the first beat) or take it off."""
    if on:
        if st_ not in f.status:
            events.append({"type": "reaction", "fighter": f.name, "status": st_, "beats": 1, "reaction": True,
                           "why": why})
        eng.set_status(f, st_, 2)
    else:
        f.status.pop(st_, None)


def _blood_tick(eng, f, st):
    """body.blood (since build 318): the blood she has lost, 0 to 100 (100 = none). Every open wound bleeds its rate
    a beat, and clots (x clot a beat; more slowly, held_clot, while a grip is on it); with little bleeding the body
    makes a little back (regen). Never below floor: it is never a death. Under low she is weaker and slower, under
    pale PALE, under faint LIGHT-HEADED; a fast bleed shows as BLEEDING."""
    cb = cfg(eng, "blood")
    ev = []
    if not cb:
        return ev
    bl = st.setdefault("bleed", {})
    held = {h.part for h in eng.holds.values() if h.defender == f.name}
    loss = sum(bl.values())
    for p in list(bl):
        bl[p] = round(bl[p] * (float(cb["held_clot"]) if p in held else float(cb["clot"])), 3)
        if bl[p] < 0.02:
            del bl[p]
    b = float(st.get("blood", 100.0)) - loss
    if loss < 0.2:
        b += float(cb["regen"])
    st["blood"] = round(max(float(cb["floor"]), min(100.0, b)), 2)
    _status(eng, f, "bleeding", loss >= float(cb["bleeding"]), "her open wounds", ev)
    lvl = st["blood"]
    _status(eng, f, "light_headed", lvl < float(cb["faint"]), "the blood she has lost", ev)
    _status(eng, f, "pale", float(cb["faint"]) <= lvl < float(cb["pale"]), "the blood she has lost", ev)
    return ev


def _adrenaline_tick(eng, f, st):
    """body.adrenaline (since build 318): how much adrenaline is running in her, 0 to 100. It rises with the health a
    beat costs her (per_loss for every % of her full health), with being held or pinned (held), and with her health
    low (under low_health %, low_rate for every % under it); it ebbs x decay a beat. It dulls the pain (pain: her
    resistance x1 + that share) and lends her blows a little (power), and quickens her heart; above high she is
    KEYED UP. When it falls from crash_from or more to under crash_below, the CRASH: crash_beats of shakiness, her
    strength coming back slower. (The one-time adrenaline surge at her last strength is still its own thing.)"""
    cd = cfg(eng, "adrenaline")
    ev = []
    if not cd:
        return ev
    a = float(st.get("adrenaline", 0.0))
    hp = float(f.health)
    lost = max(0.0, float(st.get("hp_last", hp)) - hp) / max(1.0, f.max_health) * 100.0
    st["hp_last"] = round(hp, 2)
    pct = eng._health_pct(f)
    held = any(h.defender == f.name for h in eng.holds.values()) or bool(eng.pinned_by(f.name))
    a = a * float(cd["decay"]) + float(cd["per_loss"]) * lost + (float(cd["held"]) if held else 0.0) \
        + max(0.0, float(cd["low_health"]) - pct) * float(cd["low_rate"])
    if eng.has(f, "adrenaline"):
        a = 100.0
    a = max(0.0, min(100.0, a))
    peak = max(float(st.get("adr_peak", 0.0)) * 0.97, a)
    if a < float(cd["crash_below"]) and peak >= float(cd["crash_from"]):
        eng.set_status(f, "adrenaline_crash", int(cd["crash_beats"]))
        ev.append({"type": "reaction", "fighter": f.name, "status": "adrenaline_crash", "beats": int(cd["crash_beats"]),
                   "reaction": True, "why": "the rush running out"})
        peak = 0.0
    st["adrenaline"], st["adr_peak"] = round(a, 1), round(peak, 1)
    _status(eng, f, "keyed_up", a >= float(cd["high"]) and not eng.has(f, "adrenaline"), "the fight's danger", ev)
    return ev


def _tissue_tick(eng, f, st):
    """body.tissue (since build 318): swelling in her hurt parts. A blow sets how far a part will swell; it swells
    toward that over the next beats (rise of the way a beat), and the swelling goes down slowly (x fade a beat). A
    swollen limb (from `from`) is stiff: its blows weaker (down to power_min), swollen legs dodge worse (dodge_legs);
    from swollen the story is told. The card's bruises grow with it and darken as they age."""
    ct = cfg(eng, "tissue")
    ev = []
    if not ct:
        return ev
    to = st.setdefault("swell_to", {})
    sw = st.setdefault("swell", {})
    for p in list(to):
        cur = float(sw.get(p, 0.0))
        cur += (float(to[p]) - cur) * float(ct["rise"])
        to[p] = round(float(to[p]) * float(ct["fade"]), 1)
        sw[p] = round(cur, 1)
        if to[p] < 1 and cur < 1:
            to.pop(p, None)
            sw.pop(p, None)
    worst = max(sw.items(), key=lambda kv: kv[1], default=(None, 0.0))
    if worst[0] and worst[1] >= float(ct["swollen"]):
        f.learned["swollen_part"] = worst[0]
    _status(eng, f, "swollen", worst[1] >= float(ct["swollen"]), f"the blows to her {str(worst[0] or '').lower()}",
            ev)
    return ev


def _footing_tick(eng, f, st):
    """body.footing (since build 319): how steady she is on her feet, 0 to 100. A blow knocks it down by the damage
    it does (per_damage, x by where it landed: her legs and head most, x by what it was: blunt and blasts most, x
    by her build: four legs or a serpent's coils hold steadier, over her toughness); being knocked staggering costs
    stagger more, a blow turned aside off_balance. It comes back regen a beat, slower with her energy low, her legs
    tired, swollen or broken; and it can't come all the way back while she is light-headed (faint_top), dazed
    (dazed_top) or on slick ground (slick_top). Getting up she starts at getup at best. Under low her blows lose
    their footing (down to power_min) and her dodging too (dodge_min); a blow staggers her more easily, a knockdown
    keeps her up less often, and she slips more on slick ground (footing_mult). Under unsteady she is UNSTEADY."""
    cf = cfg(eng, "footing")
    ev = []
    if not cf:
        return ev
    if eng.has(f, "airborne"):
        st["footing"] = 100.0           # (on her wings: her feet aren't what holds her up)
        f.status.pop("unsteady", None)
        return ev
    fo = float(st.get("footing", 100.0))
    if f.learned.get("rose_turn") == eng.turn:
        fo = min(fo, float(cf["getup"]))
    if not _on_feet(eng, f):
        st["footing"] = round(fo, 1)
        f.status.pop("unsteady", None)
        return ev
    if f.status.get("staggered") and st.get("stag_turn") != eng.turn:
        fo -= float(cf["stagger"])
        st["stag_turn"] = eng.turn
    if f.status.get("off_balance") and st.get("ob_turn") != eng.turn:
        fo -= float(cf["off_balance"])
        st["ob_turn"] = eng.turn
    legs = 1.0
    cl = cfg(eng, "limbs")
    if cl:
        legs *= 1 - 0.5 * _tired(cl, (st.get("limbs") or {}).get("legs", 0))
    ct = cfg(eng, "tissue")
    if ct:
        sw = _limb_swelling(eng, f, "legs")
        legs *= 1 - 0.4 * max(0.0, min(1.0, (sw - float(ct["from"])) / max(1.0, 100 - float(ct["from"]))))
    if any(_region(p) in ("hind_up", "hind_low") for p in (f.learned.get("fractures") or {})):
        legs *= 0.5
    top = 100.0
    if eng.has(f, "light_headed") or eng.has(f, "starved_of_air"):
        top = min(top, float(cf["faint_top"]))
    if any(eng.has(f, s_) for s_ in ("dazed", "concussed", "confused")):
        top = min(top, float(cf["dazed_top"]))
    if eng.on_slick(f.name):
        top = min(top, float(cf["slick_top"]))
    gain = float(cf["regen"]) * legs * (0.5 + 0.5 * max(0.0, min(1.0, f.energy / 100.0)))
    fo = max(0.0, fo) if fo > top else min(top, max(0.0, fo) + gain)
    if fo > top:
        fo = max(top, fo - gain)        # (above where she can stand steady: it slips down to it)
    st["footing"] = round(fo, 1)
    _status(eng, f, "unsteady", fo < float(cf["unsteady"]), "the blows and her own legs", ev)
    return ev


def _heart_tick(eng, f, st, c):
    """body.heart (since build 316): her heart rate as a running number. Each beat it moves toward what her body
    is asking of it (her resting rate, pushed up by how hard she has fought, the pain she is in, fear, panic or a
    surge, short of air, a choke), quickly when it has to rise and slowly as it settles, with a little natural
    unevenness; so a hard exchange leaves it racing for a few beats after, and a rest brings it down only
    gradually. Under coils round her body it is the constriction's own heart (constriction.heart)."""
    rest = float(getattr(f, "heart_rest", 0) or 100)
    hr = float(st.get("heart", rest * 1.1))
    coil = f.learned.get("coil_heart") or {}
    if coil.get("turn") == eng.turn:
        st["heart"] = float(coil.get("bpm") or 0)
        return
    if coil.get("stopped") or eng.has(f, "limp"):
        st["heart"] = 0.0
        return
    if st.get("heart") == 0.0:
        hr = rest * 1.5           # (started again: racing as the blood comes back)
    exert = 1.0 - max(0.0, min(100.0, f.energy)) / 100.0
    worst = max((p.damage for p in f.parts.values()), default=0.0)
    pain = min(1.5, worst / 200.0 + (1.0 - max(0.0, min(1.0, eng._health_pct(f) / 100.0))) * 0.5)
    try:
        import cards as _cards
        signs = _cards.STATUS_SIGNS
    except Exception as exc:          # (no pictures library: the statuses' share is left out)
        eng.note_failure("body.heart status signs", exc)
        signs = {}
    sm = sum(signs.get(k, (0.0, 0.0, None))[0] for k in f.status)
    air = float(st.get("air", 100))
    cb, cd = cfg(eng, "blood"), cfg(eng, "adrenaline")
    target = rest * (1.0 + float(c["exert"]) * exert + float(c["pain"]) * pain + sm
                     + float(c["air"]) * max(0.0, 1.0 - air / 100.0)
                     + (float(cb["heart"]) * (1.0 - float(st.get("blood", 100)) / 100.0) if cb else 0.0)
                     + (float(cd["heart"]) * float(st.get("adrenaline", 0)) / 100.0 if cd else 0.0))
    target = max(rest * 0.6, min(rest * float(c["max"]), target))
    k = float(c["rise"]) if target > hr else float(c["settle"])
    hr += (target - hr) * k + eng.rng.gauss(0.0, rest * float(c["wobble"]))
    st["heart"] = round(max(rest * 0.5, min(rest * float(c["max"]), hr)), 1)


def mark(eng):
    """After her energy has come back this beat: what she starts the next one with (for the air she spends)."""
    if not cfg(eng, "air"):
        return
    for f in eng.fighters.values():
        state(f)["e_last"] = round(float(f.energy), 2)


def card(f):
    """For the card and the snapshot: her air and her limbs."""
    st = f.learned.get("body") or {}
    return {"air": round(float(st.get("air", 100))), "heart": (round(float(st["heart"])) if st.get("heart") is not None
                                                              else None),
            "head_blood": round(float(st.get("head_blood", 100))), "blood": round(float(st.get("blood", 100)), 1),
            "bleeding": {k: round(v, 2) for k, v in (st.get("bleed") or {}).items()},
            "adrenaline": round(float(st.get("adrenaline", 0))), "footing": round(float(st.get("footing", 100))),
            "swell": {k: round(v) for k, v in (st.get("swell") or {}).items() if v >= 5},
            "fractures": sorted((f.learned.get("fractures") or {})), "limbs": {k: round(v) for k, v in (st.get("limbs") or {}).items()
                                                               if v >= 1}}
