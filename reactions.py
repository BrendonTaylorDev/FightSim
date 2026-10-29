"""moves.reactions (since build 308): what a body and a mind do with what is done to them, beyond the damage.

Four kinds, each its own switch in rules.json:
- body: what a hit leaves behind by what it was and where it landed (a nosebleed, cuts that sting, a gut gone sick,
  muscles still twitching after a shock, the heat of the fire on her, paws numb with cold, a headache behind her eyes).
  Most of them need the hurt to build up over the fight first (the dose): one claw does not leave her bleeding all
  over, a third or a fourth does.
- mind: what she feels about it (shaken by a big blow, the one who landed it emboldened, angry after a run of hits she
  couldn't answer, frustrated after a run of misses, panicking with no air in a choke or the coils).
- holds: what being held does to her, told in stages while it goes on (the coils taking up the slack every time she
  breathes out, her face burning with blood that can't get back down; a choke's burning throat; a joint lock's pull).
- aftermath: what a hold leaves when it comes off (the head rush and pins and needles after the coils, a raw throat
  after a choke, a strained joint, the bite's punctures throbbing, a wariness of the grip that had her).

Every reaction is short, at most a few at a time on her, never the same one again for a while, and its effect on
the numbers is small (switch effects off and they are told and nothing else). The tables here are the defaults;
moves.reactions.tune.<status> changes any of them (chance, beats, from, power, dodge, aim, regen)."""

import re

# status: kind, chance, beats, from (the dose or the blow size it needs, at /scale 3), what it does (power, dodge,
# aim: x on her misses, regen: x on the breath she gets back, drain: extra energy lost a beat), and how it looks.
REACT = {
    # ---- body, from hits ----
    "nosebleed": dict(kind="body", chance=0.45, beats=5, size=25,
                      look="a NOSEBLEED: blood running from her nose over her lip; she breathes through her mouth"),
    "blood_in_eye": dict(kind="body", chance=0.35, beats=3, size=30, aim=1.15,
                         look="BLOOD IN HER EYE from the cut above it: she blinks and wipes and it runs back in"),
    "grit_in_eyes": dict(kind="body", chance=0.5, beats=2, size=15, aim=1.2,
                         look="GRIT IN HER EYES: sand or stone dust, stinging; she blinks and squints through it"),
    "throat_struck": dict(kind="body", chance=0.4, beats=1, size=30, power=0.95, regen=0.6,
                          look="her THROAT STRUCK: coughing and gagging, every swallow hurting, her breath short"),
    "nauseous": dict(kind="body", chance=0.3, beats=2, size=30, dose=150, power=0.93, regen=0.7,
                     look="SICK TO HER STOMACH from the blows to her gut: bile at the back of her throat, a cold sweat, "
                          "wanting to fold round it"),
    "stinging_cuts": dict(kind="body", chance=0.4, beats=4, size=15, dose=120,
                          look="her CUTS STINGING: blood seeping into her fur from them, every stretch pulling them open"),
    "twitching": dict(kind="body", chance=0.4, beats=2, size=20, dodge=0.93,
                      look="TWITCHING after the shock: muscles jumping on their own, her fur standing on end, a metal "
                           "taste in her mouth"),
    "overheated": dict(kind="body", chance=0.35, beats=3, size=20, dose=150, regen=0.7,
                       look="OVERHEATED from the fire: panting, her mouth dry, the burnt places tight and hot"),
    "numb_cold": dict(kind="body", chance=0.35, beats=3, size=20, dose=120, power=0.93,
                      look="NUMB WITH COLD: her paws clumsy and slow to close, shivering in spite of herself"),
    "headache": dict(kind="body", chance=0.35, beats=3, size=20, dose=100, dodge=0.95,
                     look="a HEADACHE from the mind attacks: a pressure behind her eyes, a ringing ache that won't clear"),
    "sting_swelling": dict(kind="body", chance=0.35, beats=4, size=15, dose=60,
                           look="the STINGS SWELLING: hot, puffy and throbbing where the venom went in"),
    # ---- mind ----
    "shaken": dict(kind="mind", chance=0.35, beats=2, size=80, power=0.97, dodge=0.95,
                   look="SHAKEN by that blow: a cold flicker of doubt, a half-step of hesitation before she commits"),
    "emboldened": dict(kind="mind", chance=0.35, beats=2, power=1.03,
                       look="EMBOLDENED: she felt that one land, and she presses in, surer of herself"),
    "angry": dict(kind="mind", chance=0.5, beats=2, run=3, power=1.03, dodge=0.93,
                  look="ANGRY after taking blow after blow without answering: her jaw set, hitting harder and guarding "
                       "less"),
    "frustrated": dict(kind="mind", chance=0.5, beats=2, run=3, aim=1.1,
                       look="FRUSTRATED after missing again and again: forcing it, her blows wider and wilder"),
    "panicking": dict(kind="mind", chance=0.35, beats=1, held=2, drain=3,
                      look="PANICKING for air: the animal part of her takes over, thrashing and clawing at what holds "
                           "her, burning breath she doesn't have"),
    "wary_of_grip": dict(kind="mind", chance=0.6, beats=3,
                         look="WARY of the grip that had her: she keeps her distance from it and flinches when it comes "
                              "near"),
    # ---- aftermath, when a hold comes off ----
    "head_rush": dict(kind="body", chance=0.8, beats=1, held=2, dodge=0.85,
                      look="a HEAD RUSH as the blood floods back: dizzy, sparks in her sight, her limbs fizzing with "
                           "pins and needles"),
    "pins_and_needles": dict(kind="body", chance=0.7, beats=2, held=2, power=0.95,
                             look="PINS AND NEEDLES as feeling comes back into the limb: prickling, hot, clumsy"),
    "throat_raw": dict(kind="body", chance=0.75, beats=3, held=2, regen=0.75,
                       look="her THROAT RAW from the choke: coughing, rasping every breath, swallowing hurts"),
    "joint_strained": dict(kind="body", chance=0.7, beats=4, held=2, power=0.95,
                           look="the JOINT STRAINED from the lock: aching deep, weak, she won't fully trust it"),
    "bite_wounds": dict(kind="body", chance=0.7, beats=4, held=2,
                        look="the BITE WOUNDS throbbing: punctures where the teeth were, bleeding into her fur"),
}

# how each one shows, and how it ends (the narrator's STATUS_STORY and STATUS_ENDS)
STORY = {
    "nosebleed": ("a warm trickle from her nose, the taste of copper; she snorts it clear and it comes back",
                  "she can't breathe through her nose now and it makes every breath work", "{other} sees the blood on "
                  "her lip"),
    "blood_in_eye": ("blood runs from the cut into her eye; she blinks it away and it runs back in",
                     "half her sight is red and smeared", "{other} sees her blinking on that side"),
    "grit_in_eyes": ("grit in her eyes: she squeezes them shut, blinks hard, tears streaking her face",
                     "she can barely keep them open against the sting", "{other} sees her squinting"),
    "throat_struck": ("she coughs and gags, a paw going to her throat, unable to swallow",
                      "for a moment there is no air through it at all", "{other} sees her choke on nothing"),
    "nauseous": ("her stomach turns over: bile at the back of her throat, a cold sweat breaking under her fur",
                 "she wants to fold round it and stay folded", "{other} sees her go pale and hunch"),
    "stinging_cuts": ("the cuts sting all at once, the blood in them seeping into her fur",
                      "every stretch pulls them open again", "{other} sees the red lines on her"),
    "twitching": ("muscles jump under her skin on their own, her fur standing on end, a tang of metal in her mouth",
                  "her body won't stay still when she tells it", "{other} sees the twitches run through her"),
    "overheated": ("she pants, her mouth dry, the heat of the fire still in her and the burnt places tight",
                   "she can't get cool, can't get a good breath of it", "{other} sees her panting"),
    "numb_cold": ("her paws go numb and clumsy with the cold, a shiver running through her",
                  "she can't feel her grip properly", "{other} sees her shiver"),
    "headache": ("a pressure builds behind her eyes, an ache that throbs with her pulse",
                 "it is hard to think round it", "{other} sees her squint and shake her head"),
    "sting_swelling": ("the stings swell up hot and puffy, throbbing", "they ache with every heartbeat",
                       "{other} sees the swelling"),
    "shaken": ("something cold goes through her: a flicker of doubt in her eyes, a half-step back",
               "for the first time she wonders whether she can take many more like that", "{other} sees the flicker"),
    "emboldened": ("she felt that land, and it lifts her: her stance squares, her eyes narrow on her opponent",
                   "she has her now, she thinks", "{other} sees her come on surer"),
    "angry": ("her jaw sets and her eyes go hard: she is done just taking it",
              "she wants to hurt her back, now, and she stops caring what it costs", "{other} sees the anger come up"),
    "frustrated": ("a snarl of frustration: she can't land anything, and she starts to force it",
                   "why won't it land?", "{other} sees her forcing it"),
    "panicking": ("panic takes her: she thrashes and claws at what holds her, wild, wasting what breath she has",
                  "there is no thought now, only air, she needs air", "{other} feels the panic in her"),
    "wary_of_grip": ("she keeps clear of what held her, eyes on it, flinching when it comes near",
                     "she does not want to be in that again", "{other} sees her keep her distance"),
    "head_rush": ("the blood floods back into her all at once: the world tilts, sparks in her sight, her limbs fizzing",
                  "she has to wait for the ground to settle under her", "{other} sees her sway"),
    "pins_and_needles": ("feeling floods back into the limb, prickling and hot, clumsy as she tries to use it",
                         "it fizzes and won't do quite what she tells it", "{other} sees her shake it out"),
    "throat_raw": ("she coughs, hard, rasping, each breath dragged through a throat rubbed raw",
                   "swallowing hurts; breathing hurts", "{other} hears the rasp"),
    "joint_strained": ("the joint aches deep from the lock; she tests it, wincing, and doesn't trust it",
                       "she will not put her full weight behind it", "{other} sees her favour it"),
    "bite_wounds": ("the punctures throb where the teeth were, blood welling and running into her fur",
                    "she can feel each one", "{other} sees the bite marks"),
}
ENDS = {"nosebleed": "the bleeding from her nose stops", "blood_in_eye": "the cut stops running into her eye",
        "grit_in_eyes": "she blinks the last of the grit out", "throat_struck": "she can swallow again",
        "nauseous": "her stomach settles", "stinging_cuts": "the cuts settle to a dull sting",
        "twitching": "the last twitches go out of her muscles", "overheated": "she gets her breath and some coolness back",
        "numb_cold": "warmth comes back into her paws", "headache": "the pressure behind her eyes eases",
        "sting_swelling": "the swelling stops throbbing", "shaken": "she steadies herself, the doubt pushed down",
        "emboldened": "the lift of it fades", "angry": "the anger cools to something steadier",
        "frustrated": "she makes herself settle and pick her moment", "panicking": "she gets hold of herself",
        "wary_of_grip": "she stops watching for it", "head_rush": "the world steadies under her",
        "pins_and_needles": "the prickling fades and the limb is hers again", "throat_raw": "the rasp eases",
        "joint_strained": "the joint feels sound enough to use", "bite_wounds": "the bites stop bleeding"}
WORD = {k: k.replace("_", " ") for k in REACT}
WORD.update({"throat_struck": "throat struck", "wary_of_grip": "wary of the grip", "numb_cold": "numb with cold"})
ICON = {"nosebleed": "🩸", "blood_in_eye": "🩸", "grit_in_eyes": "😣", "throat_struck": "😖", "nauseous": "🤢",
        "stinging_cuts": "🩹", "twitching": "⚡", "overheated": "🥵", "numb_cold": "🥶", "headache": "🤕",
        "sting_swelling": "🐝", "shaken": "😨", "emboldened": "😤", "angry": "😠", "frustrated": "😣",
        "panicking": "😱", "wary_of_grip": "👀", "head_rush": "💫", "pins_and_needles": "✨", "throat_raw": "😷",
        "joint_strained": "🦴", "bite_wounds": "🦷"}

# what being held feels like, by the kind of hold, in stages (from beat 1, 2 and 4 of it): told once each
HOLD_FEEL = {
    "coil_body": ("each time she breathes out, the coils take up the slack, and the next breath in is smaller",
                  "the blood trapped above the coils: her face and ears burn hot, her eyes feel full, her heartbeat "
                  "loud in her head",
                  "her ribs creak and flex under it; her lips and tongue tingle, and a sick, swimming feeling rises in "
                  "her"),
    "coil_throat": ("a pressure building in her head, her face hot and full", "a roaring in her ears, the edges of "
                    "her sight flickering", "her tongue thick, a swimming lightness, her thoughts going far away"),
    "choke_air": ("her throat burns; each breath is a thin whistle and she can't swallow",
                  "her face hot and swelling, her eyes streaming, her chest heaving for air that barely comes",
                  "her lungs on fire, spots swimming in front of her eyes"),
    "choke_blood": ("a pressure behind her eyes, a pounding in her temples", "a roaring in her ears, the world going "
                    "far away and grey at the edges", "her limbs heavy and far off, her thoughts slipping"),
    "choke_both": ("her throat crushed and the sides squeezed: no air through it, the blood pounding in her head",
                   "her face hot and swelling, her eyes streaming, a roaring in her ears",
                   "her chest heaving uselessly, spots in her sight, her limbs going heavy"),
    "joint": ("the joint burns, the tendons drawn tight as wire", "she rises and twists into it to ease the pull, "
              "sweat breaking under her fur", "something deep in the joint creaks; the limb trembles"),
    "bite": ("the teeth sunk in: a deep stabbing ache and warm blood under her fur", "every pull tears at it, so she "
             "stops pulling", "the flesh round the bite going numb and swollen"),
    "bound": ("the limb prickles where it is wound", "the limb cold and heavy, slow to answer", "the limb numb, as if it "
              "were someone else's"),
    "crush": ("the grip's pressure aching deep in the part", "the part going numb under it, the ache spreading",
              "the part throbbing, swollen under the grip"),
}
FEEL_AT = (1, 2, 4)
HOLD_WORD = {"coil_body": "coils", "coil_throat": "coils round her throat", "choke_air": "choke", "choke_blood": "choke",
             "choke_both": "choke", "joint": "lock", "bite": "bite", "bound": "coil round her limb", "crush": "grip"}


def cfg(eng):
    c = (eng.rules.get("moves") or {}).get("reactions")
    return c if isinstance(c, dict) and c.get("enabled", True) else None


def tune(c, st):
    return dict(REACT[st], **(((c or {}).get("tune") or {}).get(st) or {}))


def mult(eng, f, what):
    """The product of what her reactions do to `what` (power, dodge, aim, regen), 1.0 when off."""
    c = cfg(eng)
    if not c or not c.get("effects", True) or f is None:
        return 1.0
    m = 1.0
    for st in REACT:
        if eng.has(f, st):
            m *= float(tune(c, st).get(what, 1.0))
    return m


def drain(eng, f):
    c = cfg(eng)
    if not c or not c.get("effects", True):
        return 0.0
    return sum(float(tune(c, st).get("drain", 0)) for st in REACT if eng.has(f, st))


def _s3(eng):
    return float((eng.rules.get("damage") or {}).get("damage_scale", 3) or 3) / 3.0


def _can(eng, f, st, c):
    """Not on her already, not too soon after the last time, and room for it (max_body / max_mind at once)."""
    t = tune(c, st)
    if f is None or f.eliminated or eng.has(f, st) or not c.get(t["kind"], True):
        return False
    last = (f.learned.get("react_at") or {}).get(st)
    if last is not None and eng.turn - int(last) < int(t["beats"]) + int(c.get("cooldown", 4)):
        return False
    on = sum(1 for s in REACT if eng.has(f, s) and REACT[s]["kind"] == t["kind"])
    return on < int(c.get("max_" + t["kind"], 2 if t["kind"] == "body" else 1))


def _give(eng, f, st, c, why, part="", extra=1.0, roll=True):
    """Roll for it and put it on her: the status record, or None."""
    if not _can(eng, f, st, c):
        return None
    t = tune(c, st)
    if t["kind"] == "mind":
        import body as _body
        extra *= _body.mind_chance(eng, f, st)      # (since build 321) her composure and the fight's edge
    ch = min(0.95, float(t["chance"]) * float(c.get("chance_mult", 1.0)) * extra)
    if roll and not eng._chance(ch, f"{f.name} {WORD[st]} ({why})", WORD[st], "no"):
        return None
    eng.set_status(f, st, int(t["beats"]))
    f.learned.setdefault("react_at", {})[st] = eng.turn
    rec = {"fighter": f.name, "status": st, "beats": int(t["beats"]), "reaction": True, "why": why}
    if part:
        rec["part"] = part
    return rec


def _dose(f, key, add):
    d = f.learned.setdefault("dose", {})
    d[key] = round(float(d.get(key, 0)) + add, 2)
    return d[key]


def on_hits(eng, a, d, move, hits, jolts=()):
    """After a move lands on d: the body reactions it may leave on her, and the mind's (her shaken, her anger after a
    run she couldn't answer). The attacker's own (emboldened) go to the beat's events. Returns d's status records."""
    c = cfg(eng)
    if not c:
        return []
    from engine import body_region
    import blocks as _bl
    s3 = _s3(eng)
    mine = [h for h in hits if h.get("defender", d.name) == d.name and float(h.get("damage_taken", 0)) > 0]
    # the run of blows she has taken without landing one, and a's run of misses ends
    d.learned["unanswered"] = int(d.learned.get("unanswered", 0)) + (1 if mine else 0)
    a.learned["unanswered"], a.learned["missed"] = 0, 0
    if not mine:
        return []
    move = move or {}
    kinds = _bl.kind_of(str(move.get("name", "")), str(move.get("about", "")))
    mtype = str(move.get("type", ""))
    name = f"{move.get('name', '')} {move.get('about', '')}".lower()
    sharp = bool(kinds & {"claw", "bite", "talon", "beak", "horn"}) or bool(re.search(r"\bcut|slash|blade|leaf|razor", name))
    blunt = not sharp and not kinds & {"beam"}
    big = max(mine, key=lambda h: float(h.get("damage_taken", 0)))
    size = float(big.get("damage_taken", 0)) / s3
    reg = body_region(big["part"])
    out = []

    def add(rec):
        if rec:
            out.append(rec)
    if c.get("body", True):
        for h in mine:
            taken = float(h.get("damage_taken", 0)) / s3
            r_ = body_region(h["part"])
            if sharp:
                _dose(d, "cut", taken)
            if blunt and r_ == "belly":
                _dose(d, "gut", taken)
            for t_, k_ in (("Fire", "fire"), ("Ice", "cold"), ("Psychic", "mind"), ("Poison", "sting"), ("Bug", "sting")):
                if mtype == t_:
                    _dose(d, k_, taken)
        dose = d.learned.get("dose") or {}

        def ready(st, key=None):
            t = tune(c, st)
            return size >= float(t.get("size", 0)) * float(c.get("size_mult", 1.0)) and (
                key is None or float(dose.get(key, 0)) >= float(t.get("dose", 0)) * float(c.get("dose_mult", 1.0)))
        spot = eng.head_spot(big["part"]) if reg == "head" else ""
        if reg == "head" and spot == "nose" and blunt and ready("nosebleed"):
            add(_give(eng, d, "nosebleed", c, f"the blow to her {big['part'].lower()}", big["part"]))
        if reg == "head" and sharp and spot in ("side", "crown") and ready("blood_in_eye"):
            add(_give(eng, d, "blood_in_eye", c, f"the cut on her {big['part'].lower()}", big["part"]))
        if reg == "head" and (mtype in ("Ground", "Rock") or re.search(r"sand|mud|dirt|dust", name)) and ready("grit_in_eyes"):
            add(_give(eng, d, "grit_in_eyes", c, f"{move.get('name', 'the blow')} in her face", big["part"]))
        if reg == "neck" and blunt and not any(x.defender == d.name and body_region(x.part) == "neck"
                                               for x in eng.holds.values()) and ready("throat_struck"):
            add(_give(eng, d, "throat_struck", c, f"the blow to her {big['part'].lower()}", big["part"]))
        if reg == "belly" and blunt and ready("nauseous", "gut"):
            add(_give(eng, d, "nauseous", c, "the blows to her gut", big["part"]))
        if sharp and ready("stinging_cuts", "cut"):
            add(_give(eng, d, "stinging_cuts", c, "the cuts adding up"))
        if mtype == "Electric" and not eng.has(d, "paralyzed") and ready("twitching"):
            add(_give(eng, d, "twitching", c, f"the shock of {move.get('name', 'it')}"))
        # (since build 320) with body.heat on, her core temperature tells the heat and the cold (flushed,
        # shivering...): these two would only say it again
        import body as _body
        core = bool(_body.cfg(eng, "heat"))
        if mtype == "Fire" and not core and ready("overheated", "fire"):
            add(_give(eng, d, "overheated", c, "the fire she has taken"))
        if mtype == "Ice" and not core and not eng.has(d, "frozen") and ready("numb_cold", "cold"):
            add(_give(eng, d, "numb_cold", c, "the cold she has taken"))
        if mtype == "Psychic" and ready("headache", "mind"):
            add(_give(eng, d, "headache", c, "the mind attacks"))
        if mtype in ("Poison", "Bug") and sharp and ready("sting_swelling", "sting"):
            add(_give(eng, d, "sting_swelling", c, "the stings", big["part"]))
    if c.get("mind", True):
        tough = max(0.3, eng.trait(d, "toughness"))
        stunned = any(j.get("status") == "stunned" for j in jolts or ())
        import body as _body
        if size >= float(tune(c, "shaken")["size"]) * float(c.get("size_mult", 1.0)) * _body.shaken_size_mult(eng, d) \
                or stunned:
            rec = _give(eng, d, "shaken", c, f"the force of {move.get('name', 'that blow')}", extra=1.0 / tough)
            add(rec)
            if rec:
                won = _give(eng, a, "emboldened", c, f"feeling {move.get('name', 'it')} land on {d.name}")
                if won:
                    eng._pending_events.append(dict(won, type="reaction"))
        if int(d.learned.get("unanswered", 0)) >= int(tune(c, "angry")["run"]) and not eng.has(d, "shaken") \
                and not any(eng.has(d, s) for s in ("stunned", "asleep", "frozen")):
            rec = _give(eng, d, "angry", c, f"{d.learned['unanswered']} blows in a row with no answer")
            if rec:
                d.learned["unanswered"] = 0
                add(rec)
    return out


def on_miss(eng, a, d):
    """a's blow missed d: a run of them frustrates her (to the beat's events)."""
    c = cfg(eng)
    if not c:
        return
    a.learned["missed"] = int(a.learned.get("missed", 0)) + 1
    if c.get("mind", True) and a.learned["missed"] >= int(tune(c, "frustrated")["run"]):
        rec = _give(eng, a, "frustrated", c, f"{a.learned['missed']} misses in a row")
        if rec:
            a.learned["missed"] = 0
            eng._pending_events.append(dict(rec, type="reaction"))


def hold_kind(eng, h):
    """What kind of hold it is, for HOLD_FEEL and its aftermath."""
    from engine import body_region
    if h.coil:
        return {"body": "coil_body", "throat": "coil_throat"}.get(eng.coil_scope(h.part), "bound")
    if body_region(h.part) == "neck":
        ck = eng._hold_choke_kind(h)
        if ck:
            return "choke_" + ck
    if eng._limb_kind(h.with_part) == "jaws":
        return "bite"
    if h.sub or h.locked:
        return "joint"
    return "crush"


AFTER = {"coil_body": ("head_rush", "pins_and_needles", "wary_of_grip"), "coil_throat": ("head_rush", "throat_raw",
         "wary_of_grip"), "choke_air": ("throat_raw", "wary_of_grip"), "choke_blood": ("head_rush", "wary_of_grip"),
         "choke_both": ("throat_raw", "head_rush", "wary_of_grip"), "joint": ("joint_strained",),
         "bite": ("bite_wounds",), "bound": ("pins_and_needles",), "crush": ()}


def tick(eng):
    """End of a beat, before statuses count down: how each hold on her feels at this stage (told once a stage), the
    panic when the air is gone, and what a hold that came off since last beat leaves on her. Returns beat events."""
    c = cfg(eng)
    if not c or eng.winner():
        return []
    events = []
    for f in eng.active():
        mine = [h for h in eng.holds.values() if h.defender == f.name]
        was = f.learned.get("held_by") or {}
        now = {}
        for h in mine:
            k = hold_kind(eng, h)
            now[str(h.id)] = [k, int(h.turns_active), h.part, h.attacker]
            prev = was.get(str(h.id)) or []
            told = int(prev[4]) if len(prev) > 4 else 0
            stage = sum(1 for x in FEEL_AT if h.turns_active >= x)
            if c.get("holds", True) and stage > told and k in HOLD_FEEL:
                events.append({"type": "hold_feel", "fighter": f.name, "attacker": h.attacker, "kind": k,
                               "part": h.part, "stage": stage, "says": HOLD_FEEL[k][stage - 1],
                               "beats_held": int(h.turns_active)})
            now[str(h.id)].append(max(told, stage))
        # the air gone (a choke, coils round her throat or her chest) for long enough: panic
        if c.get("mind", True) and any(now[i][0].startswith(("choke", "coil_body", "coil_throat"))
                                       and now[i][1] >= int(tune(c, "panicking")["held"]) for i in now):
            rec = _give(eng, f, "panicking", c, "no air for too long", extra=1.0 / max(0.3, eng.trait(f, "toughness")))
            if rec:
                events.append(dict(rec, type="reaction"))
        if c.get("aftermath", True):
            for hid, (k, beats, part, by, *_rest) in was.items():
                if hid in now or any(h.attacker == by and hold_kind(eng, h) == k for h in mine):
                    continue      # (still on, or the same kind of grip only moved)
                for st in AFTER.get(k, ()):
                    if beats < int(tune(c, st).get("held", 2)):
                        continue
                    if REACT[st]["kind"] == "mind" and not c.get("mind", True):
                        continue
                    rec = _give(eng, f, st, c, f"{poss(by)} {HOLD_WORD.get(k, 'hold')}, {beats} beats of it", part)
                    if rec:
                        events.append(dict(rec, type="reaction", after=k, by=by))
        if now:
            f.learned["held_by"] = now
        else:
            f.learned.pop("held_by", None)
    return events


def poss(name):
    return f"{name}'" if str(name).endswith("s") else f"{name}'s"
