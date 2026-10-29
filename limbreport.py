"""(since build 324) One body part in detail, for the window's hover over a part's label and /limb in the console
(window.limb_report): how hurt it is and what that has cost her, what it looks like now, what it is doing (throbbing,
swelling, bleeding, singed, numb, tired from use, held), the grips on it, and what it does to the rest of her: her
blows and dodging, her pain, her blood and breath, her nerve, and the statuses it has given her.

Everything is read from the engine's own state, so it says nothing the fight hasn't done. Nothing reads it back."""
import re

import body as _body
from engine import body_region, note_failure

# how hurt: the window's own damage steps (cards.DMG_STEPS), in words
_HURT = [(500, "ruined"), (300, "devastated"), (150, "excruciating"), (90, "very painful"), (60, "hurting"),
         (30, "sore"), (0.5, "barely hurt"), (-1e9, "unhurt")]

# the statuses a blow to each region gives her (moves.head, moves.body_jolts)
_REGION_STATUS = {
    "head": ("rattled", "dazed", "stunned", "wobbly", "eyes_watering", "ears_ringing", "jaw_rattled", "seeing_double",
             "swollen_eye"),
    "neck": ("whiplash",), "hind_up": ("limping",), "hind_low": ("limping",), "fore_up": ("dead_arm",),
    "fore_low": ("dead_arm",), "shoulder": ("dead_arm",), "chest": ("ribs_aching", "winded"), "belly": ("winded",),
    "back_up": ("back_spasm",), "back_low": ("back_spasm",), "tail": ("tail_numb",),
}

# what each kind of wound is doing to the part now, by how deep (sore, bad, terrible): written for fur
_DOING = {
    "burn": ("warm and tender, the fur singed at the tips", "scorched: the fur singed and curling, the skin under it "
             "hot and tight", "burned raw: the fur burned away in patches, the skin blistered and weeping"),
    "cold": ("chilled and a little stiff", "frost-numbed: cold to the touch, the fur rimed and stiff",
             "frozen deep: white with frost, stiff, the feeling dulled out of it"),
    "shock": ("tingling where the current ran", "twitching now and then where the current went through, the fur "
              "standing on end", "jerking in spasms, the fur scorched in branching lines"),
    "claw": ("scratched, the fur ruffled and parted", "cut: the fur parted along the gashes, the edges raw",
             "laid open: deep gashes, the fur matted dark around them"),
    "bite": ("nipped, a few tooth marks", "punctured where teeth went in, the fur wet and clumped",
             "torn by teeth: deep punctures, the flesh around them ragged"),
    "blunt": ("tender, the fur ruffled", "bruised under the fur, aching with each move",
              "battered: deep bruising, every movement of it hurting"),
    "grip": ("the fur pressed flat and ruffled where she was held", "grip-marked: the fur crushed flat, the skin "
             "under it reddened", "crushed: deep grip marks, the flesh under them bruised dark"),
}


def enabled(rules):
    return bool(((rules or {}).get("window") or {}).get("limb_report", {}).get("enabled", True))


def _hurt_word(dmg):
    return next(w for at, w in _HURT if dmg >= at)


def _limb_of(eng, f, part):
    """Which of her limbs (body.limbs) the part belongs to, for how tired it is: arms, legs, wings, jaws, tail."""
    reg = body_region(part)
    if reg in ("fore_up", "fore_low", "shoulder"):
        return "wings" if "wing" in part.lower() or eng.body_plan(f) == "avian" else "arms"
    if reg in ("hind_up", "hind_low"):
        return "legs"
    if reg == "tail":
        return "tail"
    if reg == "head":
        return "jaws" if re.search(r"(?i)jaw|muzzle|snout|beak", part) else "head"
    if reg == "neck":
        return "head"
    return None


def _pct(m):
    return f"{(1 - m) * 100:.0f}%"


def report(eng, f, part):
    """The whole report for one part of hers, as lines of plain text (a heading, then sections)."""
    p = f.parts.get(part)
    if p is None:
        return [f"{f.name} has no {part.lower()}."]
    st = f.learned.get("body") or {}
    key = f"{f.name}|{part}"
    dmg, res = float(p.damage), float(p.resistance)
    start = float(getattr(p, "start_resistance", 0) or res)
    say = lambda t: eng.in_her_covering(f, t)
    out = [f"{f.name.upper()}: {part.upper()}"]

    # ---- how hurt, and what it has cost her ----
    line = f"Damage {dmg:.0f}% ({_hurt_word(dmg)}). Resistance {res:.0f}%"
    line += (f", down from {start:.0f}%: blows here get through more than they did" if start - res >= 3 else
             ", as sound as at the start")
    out.append(line + ".")
    lost = (f.learned.get("hp_by_part") or {})
    mine = float(lost.get(part, 0.0))
    if mine >= 1:
        all_ = sum(float(v) for v in lost.values()) or mine
        out.append(f"Health: the blows and grips here have cost her \u2665 {mine:.0f}%, {mine / all_ * 100:.0f}% of "
                   f"all her wounds have cost her (she has {f.health / max(1.0, f.max_health) * 100:.0f}% of her full "
                   f"health left).")
    causes = eng.injury_causes(key, 3)
    t = (getattr(eng, "hit_turn", None) or {}).get(key)
    if causes:
        when = ("" if t is None else " (hit this beat)" if t >= eng.turn else
                f" (last hit in beat {t}, {eng.turn - t} beat{'s' if eng.turn - t != 1 else ''} ago)")
        out.append("Done by: " + ", ".join(causes) + when + ".")
    ranked = sorted(f.parts.values(), key=lambda q: -q.damage)
    if dmg >= 30 and ranked and ranked[0] is p:
        out.append("Her worst injury.")

    # ---- what it looks like ----
    if dmg >= 20:
        try:
            look = eng.visible_marks(f, p)
            out.append("\nLooks: " + look.split(": ", 1)[-1] + ".")
        except Exception as e:
            note_failure("describing how a part looks (limb report)", e)
    else:
        out.append("\nLooks: " + say("unmarked, the fur smooth") + ".")

    # ---- what it is doing now ----
    doing = []
    lvl = 2 if dmg >= 300 else 1 if dmg >= 90 else 0
    if dmg >= 20:
        kinds = []
        for c in causes:
            k = eng.wound_kind(c)
            if k not in kinds:
                kinds.append(k)
        for k in kinds[:2] or ["blunt"]:
            doing.append(say(_DOING.get(k, _DOING["blunt"])[lvl]))
    if getattr(p, "numb", 0):
        doing.append("numb: no feeling in it for now (the pain will flood back when it wears off)")
    elif dmg >= 30:
        hr, rest = st.get("heart"), float(getattr(f, "heart_rest", 0) or 100)
        if hr and float(hr) >= rest * 1.15:
            doing.append(f"throbbing with every beat of her racing heart ({float(hr):.0f} a minute)")
        elif dmg >= 60:
            doing.append("aching steadily" + (", throbbing with her pulse" if dmg >= 150 else ""))
        if t is not None and t >= eng.turn:
            doing.append("still stinging from the blow this beat")
    sw = float((st.get("swell") or {}).get(part, 0.0))
    if sw >= 5:
        doing.append(("swollen tight and stiff" if sw >= 55 else "swelling" if sw >= 25 else "puffing up a little")
                     + f" (swelling {sw:.0f})")
    bl = float((st.get("bleed") or {}).get(part, 0.0))
    if bl > 0.05:
        doing.append("bleeding freely" if bl >= 1.0 else "bleeding steadily" if bl >= 0.4 else "oozing a little blood")
    fr = (f.learned.get("fractures") or {}).get(part)
    if fr is not None:
        doing.append(f"broken (since beat {fr}): she favours it")
    limb = _limb_of(eng, f, part)
    tired = float((st.get("limbs") or {}).get(limb, 0.0)) if limb else 0.0
    if tired >= 30:
        doing.append(f"her {_body.LIMB_WORD.get(limb, limb)} {'heavy and slow to answer' if tired >= 55 else 'tiring'}"
                     f" from use ({tired:.0f}% worn)")
    if eng.has(f, "soaked"):
        doing.append(say("wet, the fur slicked flat"))
    out.append("Now: " + ("; ".join(doing) if doing else "nothing: it works as it should") + ".")

    # ---- the grips on it, and what she holds with it ----
    grips = []
    for h in eng.holds.values():
        if h.defender == f.name and h.part == part:
            what = h.sub or ("coils" if h.coil else "grab" if h.grab else "hold")
            wp = h.with_part.lower()
            grips.append(f"{h.attacker}'s {what}" + (f" (with {'' if wp.startswith('her ') else 'her '}{wp})"
                                                      if wp else "")
                         + f", {h.turns_active} beat{'s' if h.turns_active != 1 else ''}, pressing at {h.power:.0f}"
                         + (" and tightening" if h.change_per_turn > 0 else "") + (", locked on" if h.locked else ""))
        elif h.attacker == f.name and h.with_part and h.with_part.lower() in part.lower():
            grips.append(f"she is holding {h.defender}'s {h.part.lower()} with it (it tires as she holds)")
    pin = eng.pinned_by(f.name)
    if pin and body_region(part) in ("back_up", "back_low", "chest", "belly", "shoulder"):
        grips.append(f"pinned under {' and '.join(pin)}, the weight bearing on it")
    if grips:
        out.append("\nGrips: " + "; ".join(grips) + ".")

    # ---- what it does to the rest of her ----
    eff = []
    lim = (eng.rules.get("moves") or {}).get("limb_limits") or {}
    if limb and lim.get("enabled", True):
        steps = sorted(((float(k), float(v)) for k, v in (lim.get("at") or {"150": 0.8, "300": 0.6}).items()),
                       reverse=True)
        m = next((v for at, v in steps if dmg >= at), None)
        if m is not None and m < 1:
            eff.append(f"Blows thrown with it land {_pct(m)} weaker (moves.limb_limits)")
    ct = _body.cfg(eng, "tissue")
    if ct and limb and sw > float(ct["from"]):
        k = min(1.0, (sw - float(ct["from"])) / max(1.0, 100 - float(ct["from"])))
        eff.append(f"the swelling stiffens her {_body.LIMB_WORD.get(limb, limb)}: blows with them "
                   f"{_pct(1 - (1 - float(ct['power_min'])) * k)} weaker"
                   + (f", dodging {k * float(ct['dodge_legs']) * 100:.0f}% worse" if limb == "legs" else ""))
    cl = _body.cfg(eng, "limbs")
    if cl and limb and tired > float(cl["from"]):
        k = _body._tired(cl, tired)
        eff.append(f"tiredness: blows with her {_body.LIMB_WORD.get(limb, limb)} "
                   f"{_pct(1 - (1 - float(cl['power_min'])) * k)} weaker"
                   + (f", dodging {k * float(cl['dodge_legs']) * 100:.0f}% worse" if limb == "legs" else ""))
    cb = _body.cfg(eng, "bones")
    if cb and fr is not None:
        eff.append(f"the break: blows with it {_pct(float(cb['power_mult']))} weaker"
                   + (f", dodging {_pct(float(cb['dodge_legs']))} worse" if limb == "legs" else ""))
    if bl > 0.05:
        eff.append(f"Blood: it is draining her (her blood at {float(st.get('blood', 100)):.0f}%; under "
                   f"{float((_body.cfg(eng, 'blood') or {}).get('low', 85)):.0f}% she weakens and pales)")
    gauge = eng.pain_gauge(f) if hasattr(eng, "pain_gauge") else None
    if gauge and dmg >= 30:
        g = gauge.get("part") or {}
        if part in (g.get("parts") or ()):
            eff.append(f"Pain: it is where the pain is this beat, {g.get('shown')} of what she can bear "
                       f"({g.get('label')})")
        elif ranked and p in ranked[:3]:
            eff.append(f"Pain: one of the injuries keeping up the ache under everything (overall "
                       f"{(gauge.get('overall') or {}).get('shown', '?')} of what she can bear)")
    held_here = [h for h in eng.holds.values() if h.defender == f.name and h.part == part]
    if held_here and re.search(r"(?i)neck|throat", part):
        eff.append(f"Breath: the grip on her throat cuts her air (air {float(st.get('air', 100)):.0f}%)")
    if any(h.coil for h in held_here):
        if body_region(part) in ("chest", "belly", "back_up", "back_low", "shoulder"):
            eff.append("Body: the coils round it squeeze her breath and, in time, her heart and blood flow "
                       f"(air {float(st.get('air', 100)):.0f}%)")
        elif not re.search(r"(?i)neck|throat", part):
            eff.append("Body: the coils round it cut off the blood to it: it goes numb, weak and slow to answer")
    cm = _body.cfg(eng, "mind")
    if cm and (held_here or dmg >= 150):
        eff.append(f"Mind: {'being held there' if held_here else 'an injury this bad'} wears on her nerve "
                   f"(composure {float(st.get('composure', 100)):.0f}"
                   + (", unnerved" if f.status.get("unnerved") else "") + ")")
    reg = body_region(part)
    if reg == "head" and dmg >= 60:
        eff.append("Head: hits here can daze, rattle or stun her, and in a knockout match knock her out")
    tied = [s for s in _REGION_STATUS.get(reg, ()) if f.status.get(s)]
    if f.status.get("swollen") and f.learned.get("swollen_part") == part:
        tied.append("swollen")
    if f.status.get("bound") and f.learned.get("bound_part") == part:
        tied.append("bound")
    if tied:
        try:
            import explain
            eff += [explain.status_text(s, f.status.get(s), eng.rules).replace("\n", ": ", 1).replace("\n", " ")
                    for s in tied]
        except Exception as e:
            note_failure("explaining a part's statuses (limb report)", e)
            eff += [s.replace("_", " ") for s in tied]
    if eff:
        out.append("\nWhat it does to her:")
        out += ["- " + e[:1].upper() + e[1:] for e in eff]
    elif dmg < 30:
        out.append("\nWhat it does to her: nothing yet.")
    return out


def reports(eng, f):
    """{part: report text} for every part of hers (the snapshot, so the window can show any beat's)."""
    out = {}
    for name in f.parts:
        try:
            out[name] = "\n".join(report(eng, f, name))
        except Exception as e:
            note_failure("writing a part's report (window.limb_report)", e)
            return {}
    return out


def find_part(f, words):
    """Her part named by words ("left foreleg", "tail", "head"): an exact name, else the best partial match."""
    w = " ".join(words).lower().strip()
    if not w:
        return None
    names = list(f.parts)
    exact = next((n for n in names if n.lower() == w), None)
    if exact:
        return exact
    hits = [n for n in names if all(x in n.lower() for x in w.split())]
    return min(hits, key=len) if hits else None
