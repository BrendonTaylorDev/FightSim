"""How she reacts to being hurt (rules.json reacting, since build 336): her temperament under pain, beyond what a
blow does to her body.

A fighter's reaction traits are set in fighters.json, "reacting": {trait: 0 to 1, ..., "sensitive": {kind of damage
or part: x}}. Traits:
- stoic: keeps it in (her reactions shown smaller, quieter); expressive: shows everything (bigger, louder).
- vocal / quiet: how much of it comes out of her mouth.
- squirmer, recoils, curls, rigid, lashes_out: how she MOVES with the pain: writhing and squirming, jerking away
  from it, folding round the hurt, locking up and going still, or turning it straight back on whoever did it.
- sensitive: kinds of damage (blunt, claw, blade, bite, blast, fire, cold, shock, mind, grip) and parts (by a word
  in the part's name: ears, tail, paw...) that she reacts to more (over 1) or less (under 1).

Each blow that lands gets one reaction: how big (barely, small, marked, big, violent), how she moves, and what sound
she makes. Its size comes from the real thing: how much the blow did, how hurt that part now is, and how hurt she is
overall. Her temperament shifts what shows, but never past what is real: a part in agony, a huge blow or her health
nearly gone always shows big, however stoic she is.

In a pin or a hold her nature shows too: a squirmer is never still, a stoic lies quiet and saves it for a sudden
heave. Small effects on the numbers (pin_effects), each switchable: a squirmer wears herself out a little faster in
a pin and tries a little more often; a stoic a little slower."""
import zlib

SIZES = ("barely", "small", "marked", "big", "violent")
MOVES = ("squirm", "recoil", "curl", "rigid", "lash")
TRAIT_MOVE = {"squirmer": "squirm", "recoils": "recoil", "curls": "curl", "rigid": "rigid", "lashes_out": "lash"}

# by the kind of damage, how a body moves with the pain before temperament (weights)
KIND_MOVES = {
    "blunt": {"recoil": 2, "curl": 1.5, "squirm": 0.5},
    "claw": {"recoil": 2, "squirm": 1, "lash": 1},
    "blade": {"recoil": 2, "squirm": 1, "lash": 0.8},
    "bite": {"squirm": 2, "recoil": 1.5, "lash": 1},
    "blast": {"recoil": 2.5, "curl": 0.8},
    "fire": {"recoil": 3, "squirm": 1.2},
    "cold": {"curl": 2, "rigid": 2},
    "shock": {"rigid": 3, "recoil": 0.8},
    "mind": {"rigid": 1.5, "curl": 1.5},
    "grip": {"squirm": 3, "rigid": 0.8},
}

# how each way of moving looks, by size (the story writes it in its own words; these are what it is). All of them
# are her body moving where she is: none moves her feet, takes her anywhere or puts her down (the engine says when a
# blow staggers her, knocks her down or moves her, and the story tells that from its own notes)
LOOKS = {
    "squirm": ("a small shift, the hurt part drawn in", "a quick wriggle of her body away from the blow",
               "she squirms, twisting her body away from the hurt",
               "she writhes, squirming and twisting, unable to keep still",
               "she thrashes and writhes, all of her twisting against the pain"),
    "recoil": ("a tiny flinch", "a sharp flinch away from the blow",
               "she jerks the hurt part back",
               "she recoils hard, her whole body wrenching back from where it landed",
               "a violent full-body jerk back from the blow that she can't stop"),
    "curl": ("her body tightens round the hurt spot", "she hunches a little round the hurt",
             "she folds round the hurt, her body curling in to guard it",
             "she hunches right over the hurt, guarding it with everything",
             "for a moment she curls in round the hurt as far as her body will go, guarding it with everything"),
    "rigid": ("she stiffens for an instant", "she goes stiff, holding still",
              "she locks up, rigid, breath held",
              "she freezes, every muscle locked, shaking with the effort of holding still",
              "her whole body locks rigid and trembles, unable to move at all for a moment"),
    "lash": ("her eyes narrow", "a snap of anger, her lips peeling back",
             "she snarls at whoever did it, teeth bared",
             "fury floods through the pain: her head whips round to her attacker, snarling, teeth bared",
             "she goes wild with it, snapping and snarling, more rage than sense"),
}
# held or lying down, what changes: she can't jerk back or whip round, only strain against what holds her
HELD_LOOKS = {
    "recoil": ("a tiny flinch", "a sharp flinch against {on}",
               "she jerks against {on}, the hurt part straining away as far as it can",
               "she wrenches against {on} with her whole body, getting nowhere",
               "a violent full-body jerk against {on} that she can't stop"),
    "lash": ("her eyes narrow", "a snap of anger, her lips peeling back",
             "she snarls up at whoever did it, teeth bared, straining against {on}",
             "fury floods through the pain: snarling, snapping at anything near her mouth, heaving against {on}",
             "she goes wild with it, snapping and snarling and heaving against {on}, more rage than sense"),
}
SOUNDS = ("no sound at all", "a sharp breath through her teeth", "a grunt or a short yelp", "a cry she can't hold in",
          "a scream")


def cfg(eng):
    c = eng.rules.get("reacting") or {}
    return c if c.get("enabled", False) else None


def traits(f):
    return {k: v for k, v in (getattr(f, "reacting", None) or {}).items() if not str(k).startswith("_")}


def t(f, name):
    try:
        return max(0.0, min(1.0, float(traits(f).get(name, 0.0))))
    except (TypeError, ValueError):
        return 0.0


def sensitivity(f, kind, part):
    s = traits(f).get("sensitive") or {}
    k = float(s.get(kind, 1.0)) if isinstance(s, dict) else 1.0
    pl = str(part or "").lower()
    for word, x in (s.items() if isinstance(s, dict) else ()):
        if word not in KIND_MOVES and word.lower() in pl:
            k *= float(x)
    return k


def severity(eng, d, hit, kind):
    """(the real size, 0-4; the floor no temperament can hide; why) of her reaction to one landed blow."""
    c = cfg(eng) or {}
    added = max(0.0, float(hit.get("damage_after", 0)) - float(hit.get("damage_before", 0)))
    after = float(hit.get("damage_after", 0))
    hp = eng._health_pct(d)
    score = (float(c.get("blow", 1.0)) * min(3.0, added / float(c.get("blow_ref", 40)))
             + float(c.get("part", 0.6)) * min(3.0, after / 100.0)
             + float(c.get("overall", 0.6)) * min(2.0, max(0.0, 100.0 - hp) / 50.0))
    score *= sensitivity(d, kind, hit.get("part"))
    cuts = [float(x) for x in c.get("steps", [0.6, 1.4, 2.4, 3.5])]
    real = sum(1 for x in cuts if score >= x)
    why = []
    floor = max(0, real - 1) if real >= 3 else 0
    if after >= float(c.get("agony_at", 200)):
        floor = max(floor, 3); why.append("that part is in agony")
    if added >= float(c.get("huge_blow", 120)):
        floor = max(floor, 3); why.append("a huge blow")
    if hp < float(c.get("spent_below", 15)):
        floor = max(floor, 3); why.append("she has almost nothing left")
    floor = min(4, floor)
    return max(min(4, real), floor), floor, why


def _pick(weights, key):
    tot = sum(weights.values())
    if tot <= 0:
        return "recoil"
    x = zlib.crc32(key.encode()) % 100000 / 100000.0 * tot
    for k, v in sorted(weights.items()):
        x -= v
        if x <= 0:
            return k
    return sorted(weights)[-1]


def on_hit(eng, a, d, move, hits, kind, held=False, down=False):
    """Her reaction to the biggest blow of an attack: {"size", "move", "how", "sound", "hidden", "why"}, or None."""
    if not cfg(eng) or not hits:
        return None
    h = max(hits, key=lambda x: float(x.get("damage_after", 0)) - float(x.get("damage_before", 0)))
    if h.get("defender", d.name) != d.name:
        return None
    real, floor, why = severity(eng, d, h, kind)
    pre = max(0, min(4, real - round(2 * t(d, "stoic")) + round(t(d, "expressive"))))
    shown = max(floor, pre)
    if shown <= 0 and real <= 0:
        return None
    w = dict(KIND_MOVES.get(kind) or KIND_MOVES["blunt"])
    for tr, mv in TRAIT_MOVE.items():
        x = t(d, tr)
        if x:
            w[mv] = w.get(mv, 0.0) + 3.0 * x
    if held or down:
        w["recoil"] = w.get("recoil", 0) * 0.5        # (nowhere to jerk away to: she squirms or locks up instead)
        w["squirm"] = w.get("squirm", 0) + 1.0
    mv = _pick(w, f"{getattr(eng, '_seed0', 0)}|{eng.turn}|{d.name}|{h.get('part')}|react")
    on = "the grip on her" if held else "the ground"
    how = (HELD_LOOKS.get(mv) or LOOKS[mv])[shown].format(on=on) if held or down else LOOKS[mv][shown]
    if (held or down) and mv not in HELD_LOOKS and shown >= 2:
        how += " against " + on
    snd = shown + round(t(d, "vocal")) - round(t(d, "quiet")) - round(t(d, "stoic"))
    snd = max(0 if shown < 3 else 1 if t(d, "quiet") or t(d, "stoic") else 2, min(4, snd))
    sound = SOUNDS[snd]
    from engine import body_region
    air = float((d.learned.get("body") or {}).get("air", 100))
    if snd >= 2 and (air < 25 or any(h.defender == d.name and body_region(h.part) == "neck"
                                      for h in eng.holds.values())):
        # (a grip on her throat, or no air left: the cry comes out as a strangled wheeze or not at all)
        sound = "a strangled sound, all the grip on her throat (or the air she has left) lets out"
    hidden = ""
    if floor > pre and t(d, "stoic"):
        hidden = "she tries to keep it in, but this is past what she can hide"
    elif real > shown:
        hidden = "she keeps most of it in: it hurts more than she lets show"
    elif pre > real:
        hidden = "she shows every bit of it, and more"
    return {"fighter": d.name, "part": h.get("part"), "size": SIZES[shown], "real": SIZES[real], "move": mv,
            "how": how, "sound": sound, "hidden": hidden, "why": why}


def pin_nature(eng, d):
    """In a pin or a hold: how her nature shows in the way she fights it (one line for the story), or ""."""
    if not cfg(eng):
        return ""
    if t(d, "squirmer") >= 0.4:
        return ("a squirmer: she is never still under it, always wriggling, twisting, testing, even when it gets "
                "her nowhere")
    if t(d, "stoic") >= 0.5:
        return ("stoic: she lies quiet under it for long stretches, saving herself, and then throws everything into "
                "one sudden heave")
    if t(d, "lashes_out") >= 0.4:
        return "she fights it with fury: snarling, snapping at anything near her mouth, wild heaves"
    if t(d, "rigid") >= 0.4:
        return "she goes tight and rigid under it, braced, straining against it more than squirming"
    if t(d, "expressive") >= 0.5:
        return "she lets all of it show: cries, gasps, every struggle loud and desperate"
    return ""


def pin_mults(eng, d):
    """(pin_effects) her nature on a pin's numbers: (fade x, escape tries x)."""
    c = cfg(eng)
    pe = (c or {}).get("pin_effects") or {}
    if not c or not pe.get("enabled", True):
        return 1.0, 1.0
    sq, st = t(d, "squirmer"), t(d, "stoic")
    fade = 1.0 + float(pe.get("squirm_fade", 0.1)) * sq - float(pe.get("stoic_fade", 0.08)) * st
    tries = 1.0 + float(pe.get("squirm_tries", 0.1)) * sq
    return fade, tries


# (finished) how it looks, by the way she moves with pain
FINISHED_LOOKS = {
    "still": "FINISHED for the moment: she lies where she fell and does not move, only her ribs heaving and her eyes "
             "open, staring, the fight gone out of her limbs",
    "agony": "FINISHED for the moment: curled round the pain on the ground, in horrible pain, a thin keening sound "
             "coming out of her, nothing in her answering but the hurt",
    "thrash": "FINISHED for the moment: thrashing and squirming on the ground with the pain, rolling and kicking at "
              "nothing, unable to get her legs under her or think of anything but the hurt",
}
NATURE_FINISHED = {"rigid": "still", "curl": "agony", "squirm": "thrash", "recoil": "thrash", "lash": "thrash"}


def finished_cfg(eng):
    c = (cfg(eng) or {}).get("finished") or {}
    return c if c.get("enabled", False) else None


def maybe_finished(eng, a, d, rx):
    """(finished) After a big or violent reaction when she is already low: a chance she is FINISHED for the moment:
    down, unable to act, dodge, get up or fight a grip off for a beat or two, wide open to a pin, a submission or a
    knockout. Its look follows her nature (lying still, curled in agony, thrashing). Never twice running: cooldown
    beats from the last one. The status record, or None."""
    c = finished_cfg(eng)
    if not c or rx is None or d.eliminated or eng.has(d, "finished"):
        return None
    size = SIZES.index(rx.get("real") or rx["size"])     # (how hurt she really is, not how much she shows)
    if size < 3:
        return None
    last = d.learned.get("finished_at")
    if last is not None and eng.turn - int(last) < int(c.get("cooldown", 5)):
        return None
    hp = eng._health_pct(d)
    below = float(c.get("below", 35))
    if hp >= below and size < 4:
        return None
    ch = float(c.get("violent" if size == 4 else "big", 0.15))
    ch *= 1.0 + max(0.0, min(2.0, (below - hp) / max(1.0, below)))      # the lower she is, the likelier
    ch /= max(0.5, float(eng.trait(d, "toughness")))
    if eng.has(d, "adrenaline"):
        ch *= float(c.get("adrenaline_mult", 0.4))
    ch = min(float(c.get("max", 0.6)), ch)
    if not eng._chance(ch, f"{d.name} finished for the moment by it", "FINISHED", "she fights on"):
        return None
    lo, hi = (int(x) for x in c.get("beats", [1, 2]))
    beats = lo if hi <= lo else lo + int(eng.rng.random() * (hi - lo + 1))
    eng.set_status(d, "finished", beats)
    d.learned["finished_at"] = eng.turn
    kind = NATURE_FINISHED.get(rx["move"], "agony")
    if t(d, "stoic") >= 0.5 and kind == "thrash":
        kind = "still"
    d.learned["finished_look"] = kind
    return {"fighter": d.name, "status": "finished", "beats": beats, "reaction": True, "look": FINISHED_LOOKS[kind],
            "why": "a " + rx["size"] + " reaction with so little left in her", "part": rx.get("part")}
