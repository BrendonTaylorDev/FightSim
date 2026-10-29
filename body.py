"""body (since build 314): parts of her body the engine now keeps as running numbers, beat by beat, instead of
deciding them with one roll. The dice are still in it (how hard a blow was, how hard she fought); these are what
the dice act on. Each is its own switch in rules.json (body.<name>.enabled), and each is told to the story and shown
on her card.

- air: how much breath she has in her, 0 to 100. Fighting hard spends it, a choke cuts it off, coils squeezing her
  chest let her take only shallow breaths, being winded or coughing up water costs her some; breathing freely brings
  it back fast. Short of air she hits softer, dodges slower and gets her energy back slower. Under a choke she
  passes out when it runs out (it replaces the choke's fixed count of beats).
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
            "blood_back": 40, "blood_default": True},
    "heart": {"enabled": True, "exert": 0.45, "pain": 0.3, "air": 0.35, "max": 1.85, "rise": 0.5, "settle": 0.2,
              "wobble": 0.02},
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
}
ENDS = {"short_of_air": "she gets her breath back", "starved_of_air": "air comes back into her",
        "tired_arms": "her arms have come back to her", "tired_legs": "her legs have come back to her",
        "tired_jaws": "her jaws have come back to her", "tired_head": "her neck has eased",
        "tired_tail": "her tail has come back to her", "tired_wings": "her wings have come back to her"}
WORD = {k: k.replace("_", " ") for k in LOOK}
ICON = {"short_of_air": "😮‍💨", "starved_of_air": "🫁", "tired_arms": "💪", "tired_legs": "🦵", "tired_jaws": "🦷",
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
    return out


def dodge_mult(eng, d):
    m = 1.0
    st = d.learned.get("body") or {}
    ca = cfg(eng, "air")
    if ca and float(st.get("air", 100)) < float(ca["low"]):
        m *= float(ca["dodge_min"]) + (1 - float(ca["dodge_min"])) * float(st.get("air", 100)) / float(ca["low"])
    cl = cfg(eng, "limbs")
    if cl:
        m *= 1 - float(cl["dodge_legs"]) * _tired(cl, (st.get("limbs") or {}).get("legs", 0))
    return m


def regen_mult(eng, f):
    ca = cfg(eng, "air")
    a = float((f.learned.get("body") or {}).get("air", 100))
    if not ca or a >= float(ca["low"]):
        return 1.0
    return float(ca["regen_min"]) + (1 - float(ca["regen_min"])) * a / float(ca["low"])


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
    if not ca and not cl and not cfg(eng, "heart"):
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
            if choked:
                tight = max(0.5, min(2.0, max(h.power for h in choked) / 16.0)) ** 0.5
                loss += float(ca["choke"]) * tight * (1 + float(ca["health_drain"]) * (1 - share))
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
                    * (1 + float(ca["health_drain"]) * (1 - share))
            else:
                hb += float(ca.get("blood_back", 40))
            st["head_blood"] = round(max(0.0, min(100.0, hb)), 1)
            if choked and not (kinds & {"air", "both"}):
                # (a blood choke leaves her windpipe open: she can still breathe, if badly)
                loss -= float(ca["choke"]) * 0.75 * tight
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
    target = rest * (1.0 + float(c["exert"]) * exert + float(c["pain"]) * pain + sm
                     + float(c["air"]) * max(0.0, 1.0 - air / 100.0))
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
            "head_blood": round(float(st.get("head_blood", 100))), "limbs": {k: round(v) for k, v in (st.get("limbs") or {}).items()
                                                               if v >= 1}}
