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
                                if isinstance(left, (int, float)) and not isinstance(left, bool) and left > 0 else "")
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


def breath_text(breath, rest, depth, words=()):
    deep = ("very shallow: the air barely gets in" if depth < 0.3 else "shallow: she can't fill her chest"
            if depth < 0.6 else "deep and heavy" if depth > 1.2 else "normal depth")
    if not breath:
        return "Breathing: none."
    why = [w for w in words if re.search(r"breath|winded|spent|ribs|coils|air", w)]
    return (f"Breathing: {breath} breaths a minute; at rest {rest}. Each breath is {deep}. Fast and shallow means she "
            f"is short of air; fast and deep, working hard." + (f"\nWhy: {', '.join(why)}." if why else ""))


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
    if sg.get("grey"):
        out.append(grey_text(sg["grey"]))
    if v:
        out.append(blood_text(v.get("blood", 0), v.get("out_at")))
        if v.get("squeeze") is not None:
            out.append(squeeze_text(v["squeeze"], v.get("where"), v.get("pressure"), v.get("girth")))
    out.append("(These are the story's numbers: they follow the gauges that decide the fight, but nothing is rolled "
               "against them.)")
    return "\n\n".join(out)
