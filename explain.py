"""window.explain (since build 312): plain-English explanations of what is on a fighter's card, for hover tips in the
window and for /explain in the console. Two kinds:
- statuses: what it is (the story's own words for it, engine.STATUS_LOOK) and what it does to the numbers, read
  from the rules in force (status_effects.<status>_<what>_mult, else the engine's own default for it), and how
  many beats it has left.
- the vitals: what a heart rate, a blood pressure, a breathing rate, the blood flow cut off, the squeeze, the
  pressure in mmHg and the girth mean, what is normal, and what is pushing hers where it is.
Reading only: nothing here changes the fight."""

import os
import re

# what a status_effects key's last word works on, and how to say a multiplier on it
_WHAT = {
    "power": ("her blows", "weaker", "harder"),
    "bite": ("her bites", "weaker", "harder"),
    "charge": ("her charges", "weaker", "harder"),
    "dodge": ("her dodging", "worse", "better"),
    "aim": ("her misses", "rarer", "more often"),        # (x on her miss chance: above 1 she misses more)
    "escape": ("her breaking free", "less likely", "more likely"),
    "regen": ("getting her breath back", "slower", "faster"),
    "grip": ("grips slipping off her", "less", "more"),
    "slip": ("her slipping", "less", "more"),
    "electric": ("Electric attacks on her", "weaker", "stronger"),
}

# what some statuses do that isn't a multiplier
_EXTRA = {
    "stunned": "she can't act this beat at all: no attack, no dodge, no escape, no get-up",
    "limp": "she can't act, and nobody may strike her; the coils do her no more harm, and when they come off her "
            "heart starts again on its own",
    "flinched": "she can't attack this beat",
    "asleep": "she can't act or dodge until she wakes",
    "frozen": "she can't act or dodge until the ice breaks",
    "paralyzed": "she can't dodge",
    "constricted": "she gets no energy back while the coils hold, and loses {constricted_energy_loss} a beat",
    "burned": "the burn costs her health every beat",
    "poisoned": "the poison costs her {poison_health_pct}% of her health every beat",
    "soaked": "lasts {soaked_beats} beats once she is out of the water",
    "confused": "{confused_self_hit_chance:.0%} of the time she hurts herself instead of attacking",
    "adrenaline": "the pain counts for less: she resists a tap or a choke harder, and hits harder",
    "concussed": "for the rest of the fight: every blow to the head rattles her more easily, and getting up is harder",
    "wobbly": "getting up or staying up is harder",
    "dead_leg": "getting up is harder",
    "back_spasm": "getting up is harder",
    "protecting": "the next attack on her stops against the barrier",
    "countering": "a close blow on her is returned twice as hard",
    "mirroring": "a blast or beam on her is sent back",
    "airborne": "only blasts, beams and streams reach her; she dives on her opponent",
    "reeling": "she can't wrestle anyone down or pin this beat",
    "restrained": "her struggles under the pin have less to work with",
    "greyed": "a moment from blacking out",
    "overextended": "wide open: her dodging is down to a fraction",
    "bound": "that limb is numb and weak",
    "bleeding": "her open wounds (bites and claws) are losing blood; they clot over a few beats, slower while a "
                "grip is on them (body.blood)",
    "pale": "she has lost enough blood to show it: her blows and dodges a little weaker, her heart quicker, her blood "
            "pressure lower; it is never a death (body.blood)",
    "light_headed": "she has lost a lot of blood: weaker and slower, her heart racing, her pressure low (body.blood)",
    "keyed_up": "adrenaline running high: the pain counts for less against her, her blows a touch harder, her heart "
                "fast; when it runs out there is a crash (body.adrenaline)",
    "adrenaline_crash": "the rush has run out: her strength comes back slower and her blows are a little weaker for "
                        "a few beats (body.adrenaline)",
    "broken_bone": "a bone broken in the fight or found broken after it: blows with that limb much weaker, a "
                   "broken leg dodges worse; it heals, nothing permanent, and never her spine (body.bones)",
    "buffeted": "the wind shoving her about in the air: her dodging slower for a beat (arena_weather)",
    "unnerved": "her composure frayed by big blows, being held, her air going, being knocked down: her blows and dodges "
               "a touch weaker, fear reactions (shaken, panicking) likelier, and she gives in to a hold a little "
               "sooner; it settles back within a few beats, and less and less as a long fight goes on (body.mind)",
    "flushed": "hot from the fight (or the fire she has taken): her energy and breath come back slower, her blows and "
               "dodges a touch weaker, her heart quicker; she cools as she eases off (body.heat)",
    "heat_exhausted": "dangerously hot: her energy and breath come back much slower and she is weaker and slower; "
                      "never a danger to her life (body.heat)",
    "shivering": "chilled (ice, water, rain): her blows and dodges a little weaker until she warms (body.heat)",
    "numbed": "chilled through: her blows and dodges weaker until she warms (body.heat)",
    "unsteady": "her feet not under her after the blows (worst to her legs and head): a blow staggers her more "
                "easily, a knockdown is likelier to put her down, she slips more on slick ground, and her blows and "
                "dodges are a little weaker; it comes back as she sets herself (body.footing)",
    "swollen": "a beaten part swelling up over the beats after the blow: stiff, its blows weaker, swollen legs dodge "
               "worse; it goes down slowly (body.tissue)",
    "short_of_air": "her blows softer, her dodging slower and her energy coming back slower, the less air she has "
                    "(body.air); it comes back when she can breathe freely",
    "starved_of_air": "everything she does weaker and slower; under a choke she is close to going under (body.air)",
    "tired_arms": "blows with her arms weaker, and a grip she holds with them easier to break; they come back as she "
                  "rests them (body.limbs)",
    "tired_legs": "kicks weaker and her dodging slower; they come back as she rests them (body.limbs)",
    "tired_jaws": "bites weaker, and a grip with her teeth easier to break (body.limbs)",
    "tired_head": "blows with her head weaker (body.limbs)",
    "tired_tail": "tail strikes weaker, and a grip with it easier to break (body.limbs)",
    "tired_wings": "wing strikes weaker (body.limbs)",
}

_DEFAULTS = None


def _engine_defaults():
    """{status_effects key: its default}, read once from the engine's own code (so a key the user hasn't set in
    rules.json still shows the number the engine uses)."""
    global _DEFAULTS
    if _DEFAULTS is None:
        _DEFAULTS = {}
        try:
            src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine.py"), encoding="utf-8").read()
            for k, v in re.findall(r'\.get\("([a-z_]+_(?:' + "|".join(_WHAT) + r')_mult)", ([\d.]+)\)', src):
                _DEFAULTS.setdefault(k, float(v))
        except (OSError, ValueError):
            pass
    return _DEFAULTS


def _pct(m, what):
    """'her blows 15% weaker' for x0.85 on her power."""
    name, down, up = _WHAT[what]
    if what == "aim":           # (a miss multiplier: above 1 is worse for her)
        return f"she misses {round(abs(m - 1) * 100)}% {'more' if m > 1 else 'less'} often"
    if what == "dodge" and m <= 0.05:
        return "she can't dodge"
    return f"{name} {round(abs(1 - m) * 100)}% {down if m < 1 else up}"


def status_effects(key, rules):
    """What a status does to the numbers, as short phrases."""
    sc = (rules or {}).get("status_effects") or {}
    out = []
    keys = {k for k in list(_engine_defaults()) + list(sc) if k.startswith(key + "_")}
    for k in sorted(keys):
        what = k[len(key) + 1:].rsplit("_", 1)[0] if k.endswith("_mult") else None
        if what not in _WHAT:
            continue
        try:
            m = float(sc.get(k, _engine_defaults().get(k, 1.0)))
        except (TypeError, ValueError):
            continue
        if abs(m - 1.0) > 0.005:
            out.append(_pct(m, what))
    import reactions
    rc = ((rules or {}).get("moves") or {}).get("reactions")
    if key in reactions.REACT and isinstance(rc, dict) and rc.get("effects", True):
        t = reactions.tune(rc, key)
        for what in ("power", "dodge", "aim", "regen"):
            m = float(t.get(what, 1.0))
            if abs(m - 1.0) > 0.005:
                out.append(_pct(m, what))
        if t.get("drain"):
            out.append(f"she loses {num(t['drain'])} more energy a beat")
    x = _EXTRA.get(key)
    if x:
        try:
            out.append(x.format(**{k: v for k, v in sc.items() if not k.startswith("_")}))
        except (KeyError, ValueError, IndexError):
            out.append(re.sub(r"\{[^}]*\}", "some", x))
    return out


def num(x):
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:.2f}".rstrip("0").rstrip(".")


def look(key):
    """The story's own words for a status (what it is), without its shouted name in front."""
    from engine import Engine
    t = Engine.STATUS_LOOK.get(key, "")
    t = t.split(": ", 1)[1] if ": " in t else t
    return t[:1].upper() + t[1:]


def status_text(key, left, rules):
    """The whole tip for one status: its name, beats left, what it is, what it does."""
    name = key.replace("_", " ")
    head = name.capitalize() + (f" ({left} more beat{'s' if left != 1 else ''})"
                                if isinstance(left, (int, float)) and not isinstance(left, bool) and 0 < left < 99 else "")
    parts = [head]
    what = look(key)
    if what:
        parts.append(what + ".")
    eff = status_effects(key, rules)
    if eff:
        parts.append("Effect: " + "; ".join(eff) + ".")
    return "\n".join(parts)


def statuses_text(status, rules):
    """Every status she has, one tip each, for a hover over her status line."""
    if not status:
        return "No statuses: nothing is changing her numbers right now."
    return "\n\n".join(status_text(k, v, rules) for k, v in status.items())


# ---- the vitals ----
def heart_text(heart, rest, irregular=False, stopped=False, coiled=False):
    if stopped:
        return ("Heart: stopped. Under the coils, with no blood coming back to it, her heart stopped for a moment as "
                "she went under. It starts again on its own once the coils come off.")
    r = heart / rest if rest else 1.0
    how = ("far above her resting rate: effort, pain and fear at full stretch" if r >= 1.55 else
           "well above resting: she is working hard, hurting or afraid" if r >= 1.3 else
           "a little above resting" if r >= 1.08 else
           "about her resting rate" if r >= 0.9 else
           "BELOW her resting rate: under the coils that is the danger sign, her heart slowing because the blood "
           "can't get back to it" if coiled else "below her resting rate")
    return (f"Heart rate: {heart} beats a minute; at rest hers is {rest} (a small fighter's heart runs faster than a "
            f"big one's). Now {how}."
            + (" It is beating unevenly: beats skipping as it struggles." if irregular else "")
            + ("\nUnder coils it first races, then slows as the squeeze stops the blood getting back to her heart."
               if coiled else "\nEffort, pain and fear push it up; it settles as she rests."))


def bp_text(bp, rest=(120, 80), coiled=False):
    s, d = (int(x) for x in bp)
    s0, d0 = (int(x) for x in rest)
    how = ("very low: her heart isn't getting enough blood back to push out, so her head runs short of it. This is "
           "what greys her sight and makes her black out" if s < 80 else
           "low: less blood is reaching her head; she may feel faint" if s < 95 else
           "normal" if s <= s0 + 10 else
           "raised: her heart pushing hard with the effort, the pain and the fear" if s < s0 + 35 else
           "high: everything she has is going into this")
    return (f"Blood pressure {s}/{d}: how hard her blood presses on her arteries. The first number is while her heart "
            f"beats, the second between beats. Normal is {s0}/{d0}. Hers is {how}."
            + ("\nIn coils it rises at first, then falls once the squeeze keeps the blood from getting back to her "
               "heart: the falling number is the one that matters." if coiled else ""))


def temp_text(temp, normal=38.5):
    """(body.heat, since build 320) Her core temperature, for the heart monitor's tip."""
    if temp is None:
        return ""
    d = temp - normal
    how = ("dangerously hot: heat-exhausted, everything slower" if d >= 2.4 else
           "hot: flushed, her energy and breath slower to come back" if d >= 1.5 else
           "warm from the fight" if d >= 0.5 else
           "chilled through: numbed, stiff and slow" if d <= -2.2 else
           "cold: shivering, a little slower" if d <= -1.2 else
           "a little cool" if d <= -0.5 else "normal")
    return (f"Temperature: {temp:.1f}°C (normal {normal:.1f}): {how}. Hard fighting and fire heat her; ice, water and "
            f"rain cool her; she settles back toward normal as she eases off (body.heat).")


def breath_text(breath, rest, depth, words=(), air=None):
    deep = ("very shallow: the air barely gets in" if depth < 0.3 else "shallow: she can't fill her chest"
            if depth < 0.6 else "deep and heavy" if depth > 1.2 else "normal depth")
    if not breath:
        return "Breathing: none."
    why = [w for w in words if re.search(r"breath|winded|spent|ribs|coils|air", w)]
    return (f"Breathing: {breath} breaths a minute; at rest {rest}. Each breath is {deep}. Fast and shallow means she "
            f"is short of air; fast and deep, working hard." + (f"\nWhy: {', '.join(why)}." if why else "")
            + (f"\nAir {air}%: the breath she has in her (body.air). Fighting hard spends it, a choke cuts it off, "
               f"coils let her breathe only shallowly; breathing freely brings it back. Under 40% she hits and dodges "
               f"slower; under a choke she goes under when it runs out." if air is not None else ""))


def heart_wear_text(v):
    """constriction.heart (since build 313): her heart under the coils, worn down beat by beat."""
    r = v.get("heart_reserve")
    if r is None:
        return ""
    return (f"Her heart under the coils: {round(float(r) * 100)}% of its strength left. Every beat the coils take some: "
            f"more the harder they press past her blood pressure, the further in she is squeezed, round her chest more "
            f"than her middle, more coils, a bigger coiler, the longer they stay on; less the more health and energy she "
            f"has. It races at first, then slows, then goes uneven; at about {v.get('stop_at')}/min it stops, and she "
            f"blacks out with it. Coils off, it comes back. It never kills: it always starts again.")


def blood_text(blood, out_at=None):
    return (f"Blood flow cut off: {blood}%. The coils squeeze so hard the blood can't flow back to her heart, so less "
            f"reaches her head."
            + (f" Her limit on the gauge is ({num(out_at)}%): past it she can black out, and her heart can stop for "
               f"a moment as she goes under. Her strength, energy and health decide where it sits." if out_at else ""))


def squeeze_text(squeeze, where=None, mmhg=None, girth=None):
    out = [f"Squeezed in: {num(squeeze)}%. How far the coils have pressed her chest or middle in. Each time she "
           f"breathes out they take up the slack; struggling spends breath faster, so it tightens faster."]
    if where:
        out.append({"chest": "Round her chest: straight on her heart and lungs.",
                    "belly": "Round her middle: her gut driven up under her ribs, the breath pushed out from below.",
                    "both": "Round her chest and her middle.", "back": "Across her back."}.get(where, ""))
    if mmhg is not None:
        out.append(f"Pressing about {mmhg} mmHg: once that is past her blood pressure, blood can't get back to her "
                   f"heart.")
    if girth:
        out.append(f"Girth {girth[1]} cm round, against {girth[0]} cm normally.")
    return " ".join(x for x in out if x)


def grey_text(grey):
    return (f"The grey: {round(grey * 100)}% of the way to blacking out. Her sight greys at the edges and sounds go "
            f"far away as her head runs short of blood or air.")


def vitals_text(sg, v=None):
    """The whole monitor, for /explain: her heart, pressure and breathing (body_signs), and the coils' numbers when
    she is in them (the tap meter's vitals)."""
    out = [heart_text(sg["heart"], sg["heart_rest"], sg.get("irregular"), sg.get("stopped"), sg.get("coiled")),
           bp_text(sg["bp"], sg.get("bp_rest") or (120, 80), sg.get("coiled")),
           breath_text(sg["breath"], sg["breath_rest"], sg["depth"], sg.get("words") or ())]
    if sg.get("temp") is not None:
        out.append(temp_text(sg["temp"]))
    if sg.get("grey"):
        out.append(grey_text(sg["grey"]))
    if v:
        out.append(blood_text(v.get("blood", 0), v.get("out_at")))
        if v.get("squeeze") is not None:
            out.append(squeeze_text(v["squeeze"], v.get("where"), v.get("pressure"), v.get("girth")))
    out.append("(These are the story's numbers: they follow the gauges that decide the fight, but nothing is rolled "
               "against them.)")
    return "\n\n".join(out)


def status_tips(eng, f):
    """(since build 324) {status: its tip} for every status on her, each with what it is doing to her right now in
    her own numbers where the body runs it (body.status_numbers: her composure, her core heat, her adrenaline...),
    for the window's hover over each status (kept in the snapshot, so a past beat shows its own)."""
    import body
    out = {}
    for k, v in (f.status or {}).items():
        t = status_text(k, v, eng.rules)
        try:
            now = body.status_numbers(eng, f, k)
        except Exception as e:
            from engine import note_failure
            note_failure("working out a status's numbers (window.explain)", e)
            now = []
        if now:
            t += "\nRight now: " + "; ".join(now) + "."
        out[k] = t
    return out
