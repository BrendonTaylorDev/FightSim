"""arena_weather (since build 322): the weather over the whole fight, not just the few beats a move like Rain Dance
calls up. Each kind is in rules.json (arena_weather.kinds), with what it does:

- rain: the ground slick, everyone soaked (an Electric hit goes in harder), her body cooled; Water moves stronger,
  Fire weaker.
- storm: a thunderstorm. Rain as above, gusts now and then, and lightning: very rarely a bolt strikes a fighter
  (likelier one up in the air; a Ground type it can't hurt, an Electric type takes it in with little harm), and now
  and then one strikes close by, a flash and a crack of thunder that makes both flinch.
- snow: the ground slick with it, her body chilled; Ice moves stronger, Fire weaker.
- heat: summer heat. Her body heats and sheds it slowly; Fire moves stronger. Coils round her heat her far more
  (the constrictor's body pressed round hers, the friction of it), so a long constriction can overheat her.
- wind: strong wind. Gusts knock her footing and buffet a flyer; Flying moves stronger, Fire weaker; it chills.

Each kind also sits well or badly with her own type (kinds.<kind>.fighters): a Water type in the rain is in her
element (her blows a touch stronger, her strength back sooner), a Fire type doused; in the summer heat a Water or an
Ice type wilts, heating faster, unless she is in the water, and a Fire type thrives; an Ice type is at home in the
snow.

Which kind: arena_weather.kind. "scene" (the default) is the arena's own weather (scenes.json weather; none for most);
"random" picks one for the fight; "clear" is none; or a kind by name. An indoor arena (scenes.json indoors) has
none, whatever is chosen. A move's weather (Rain Dance, Sunny Day, Hail) still takes over while it lasts."""

DEFAULTS = {
    "enabled": True, "kind": "scene", "random": ["clear", "clear", "rain", "storm", "snow", "heat", "wind"],
    "coil_heat": 0.05, "coil_limb": 0.4,
    "kinds": {
        "rain": {"word": "steady rain", "say": "rain coming down steadily, the ground wet and slick, every fighter "
                 "soaked to the skin", "type_mult": {"Water": 1.15, "Fire": 0.8}, "heat": -0.1, "slick": True,
                 "soaks": True,
                 "fighters": {"Water": {"power": 1.04, "regen": 1.1, "heat": 0.8, "say": "in her element in the rain"},
                              "Fire": {"power": 0.95, "regen": 0.9, "say": "doused and steaming in the rain"}}},
        "storm": {"word": "thunderstorm", "say": "a thunderstorm: rain in sheets, the ground slick, gusts tearing "
                  "across, thunder rolling and lightning flashing overhead", "type_mult": {"Water": 1.15, "Fire": 0.75,
                                                                                         "Electric": 1.15},
                  "heat": -0.12, "slick": True, "soaks": True,
                  "lightning": {"strike": 0.006, "air_mult": 3.0, "near": 0.03, "power": 45, "stun": 0.6,
                                "down": 0.6, "immune_types": ["Ground"], "absorb_types": ["Electric"], "absorb": 0.25,
                                "fear": 20},
                  "gusts": {"chance": 0.07, "footing": 14, "buffet": 0.5},
                  "fighters": {"Water": {"power": 1.04, "regen": 1.1, "heat": 0.8, "say": "in her element in the rain"},
                               "Electric": {"power": 1.05, "say": "charged by the storm"},
                               "Fire": {"power": 0.95, "regen": 0.9, "say": "doused and steaming in the rain"}}},
        "snow": {"word": "falling snow", "say": "snow falling thick and steady, the ground white and slick with it, "
                 "breath steaming", "type_mult": {"Ice": 1.15, "Fire": 0.85}, "heat": -0.15, "slick": True,
                 "fighters": {"Ice": {"power": 1.04, "regen": 1.1, "say": "at home in the snow"},
                              "Dragon": {"power": 0.96, "regen": 0.9, "say": "slowed by the cold"},
                              "Grass": {"power": 0.96, "regen": 0.9, "say": "slowed by the cold"}}},
        "heat": {"word": "summer heat", "say": "a heavy summer heat: the air thick and still, the ground hot "
                 "underfoot, the light glaring", "type_mult": {"Fire": 1.15, "Ice": 0.9}, "heat": 0.04,
                 "cool_mult": 0.8, "coil_mult": 3.0,
                 "fighters": {"Fire": {"power": 1.04, "regen": 1.1, "say": "thriving in the heat"},
                              "Water": {"power": 0.95, "regen": 0.85, "heat": 1.4, "wet_ok": True,
                                        "say": "wilting in the heat, out of the water"},
                              "Ice": {"power": 0.94, "regen": 0.85, "heat": 1.4, "wet_ok": True,
                                      "say": "wilting in the heat"}}},
        "wind": {"word": "strong wind", "say": "a strong wind tearing across the arena in gusts, flattening the "
                 "grass, snatching at fur and feathers", "type_mult": {"Flying": 1.1, "Fire": 0.9}, "heat": -0.05,
                 "gusts": {"chance": 0.16, "footing": 18, "buffet": 0.6},
                 "fighters": {"Flying": {"regen": 1.05, "say": "riding the wind"}}},
    },
}

LOOK = {"buffeted": "BUFFETED by the wind: shoved about in the air, fighting to hold her line; slower to dodge"}
STORY = {"buffeted": ("the wind shoving her about in the air, her wings fighting it", "she can't hold her line",
                      "{other} sees her thrown off course")}
ENDS = {"buffeted": "she gets her line back"}
ICON = {"buffeted": "🌬️"}


def cfg(eng):
    c = eng.rules.get("arena_weather") or {}
    if c.get("enabled", True) is False:
        return None
    out = dict(DEFAULTS, **{k: v for k, v in c.items() if not str(k).startswith("_")})
    kinds = {k: dict(v) for k, v in DEFAULTS["kinds"].items()}
    for k, v in (c.get("kinds") or {}).items():
        if isinstance(v, dict) and not str(k).startswith("_"):
            kinds[k] = dict(kinds.get(k) or {}, **v)
    out["kinds"] = kinds
    return out


def kind(eng):
    """The arena's weather this fight (a kind name), or None: clear, off, or indoors."""
    c = cfg(eng)
    sc = getattr(eng, "scene_cfg", None) or {}
    if not c or sc.get("indoors"):
        return None
    k = str(c.get("kind") or "scene").lower()
    if k == "scene":
        k = str(sc.get("weather") or "clear").lower()
    elif k == "random":
        got = getattr(eng, "arena_wx", None)
        if not got or got.get("scene") != sc.get("name"):
            got = {"scene": sc.get("name"), "kind": eng.rng.choice(list(c.get("random") or ["clear"]))}
            eng.arena_wx = got
        k = got["kind"]
    return k if k in c["kinds"] else None


def kcfg(eng):
    k = kind(eng)
    return (cfg(eng)["kinds"][k], k) if k else (None, None)


def word(eng):
    kc, k = kcfg(eng)
    return kc.get("word", k) if kc else ""


def text(eng):
    """For the narrator and the director: the weather as part of every moment."""
    kc, k = kcfg(eng)
    if not kc:
        return ""
    return (f"WEATHER (all fight): {kc.get('say') or kc.get('word', k)}. It is part of every moment: show it in "
            f"how they move, what the ground does under them, the light and the sound.")


def type_mult(eng, mtype):
    """(label, multiplier) for a move of this type in the arena's weather, or None."""
    kc, k = kcfg(eng)
    m = float(((kc or {}).get("type_mult") or {}).get(mtype, 1.0))
    return (f"in the {kc.get('word', k)}", m) if kc and m != 1.0 else None


def fighter_entry(eng, f):
    """(since build 322) How the weather sits with her own type (arena_weather.kinds.<kind>.fighters.<type>: power,
    regen, heat: x on what the weather does to her body heat, say). The strongest effect among her types counts. A
    wet_ok entry (a Water type in the heat) doesn't apply while she stands in water or is soaked."""
    kc, _ = kcfg(eng)
    if not kc:
        return None
    got = []
    for t in f.types or []:
        e = (kc.get("fighters") or {}).get(t)
        if not e:
            continue
        if e.get("wet_ok") and (eng.in_water(f.name) or eng.has(f, "soaked")):
            continue
        got.append(e)
    return max(got, key=lambda e: abs(float(e.get("power", 1)) - 1) + abs(float(e.get("regen", 1)) - 1),
               default=None)


def fighter_mult(eng, f, what):
    e = fighter_entry(eng, f)
    return float(e.get(what, 1.0)) if e else 1.0


def slick(eng):
    kc, _ = kcfg(eng)
    return bool(kc and kc.get("slick"))


def heat_drift(eng, f, ch):
    """(body.heat) What the weather does to her temperature this beat, and how her cooling goes in it:
    (gain, cool multiplier). Coils round her heat her in any weather (arena_weather.coil_heat a coil round her
    body, x coil_limb round a limb; the constrictor's body and the friction of it), more in the heat (coil_mult)."""
    kc, k = kcfg(eng)
    c = cfg(eng)
    gain, cool = 0.0, 1.0
    types = f.types or []
    if kc:
        h = float(kc.get("heat", 0.0))
        own = "Fire" if h > 0 else "Ice"
        gain += h * (float(ch["own_type"]) if own in types else 1.0) * fighter_mult(eng, f, "heat")
        cool = float(kc.get("cool_mult", 1.0))
    if c:
        coils = [h for h in eng.holds.values() if h.coil and h.defender == f.name]
        n = sum(1.0 if eng.coil_scope(h.part) in ("body", "throat") else float(c["coil_limb"]) for h in coils)
        gain += float(c["coil_heat"]) * min(3.0, n) * float((kc or {}).get("coil_mult", 1.0)) \
            * (float(ch["own_type"]) if "Fire" in types else 1.0)
    return gain, cool


def dodge_mult(eng, d):
    return 0.85 if d.status.get("buffeted") else 1.0


def tick(eng):
    """End of a beat: rain soaks everyone; the storm's lightning; the gusts of a strong wind or a storm."""
    kc, k = kcfg(eng)
    if not kc or eng.winner():
        return []
    events = []
    act = [f for f in eng.active()]
    if kc.get("soaks"):
        for f in act:
            if f.status.get("soaked", 0) < 2:
                f.status["soaked"] = 2
    lt = kc.get("lightning")
    if lt:
        events += _lightning(eng, act, lt, kc)
    gu = kc.get("gusts")
    if gu and eng.rng.random() < float(gu["chance"]):
        events += _gust(eng, act, gu, k)
    return events


def _lightning(eng, act, lt, kc):
    import body
    ev = []
    for f in eng.rng.sample(act, len(act)):        # (in no fixed order: a bolt favours neither)
        ch = float(lt["strike"]) * (float(lt["air_mult"]) if eng.has(f, "airborne") else 1.0)
        if eng.rng.random() >= ch:
            continue
        if any(t in (lt.get("immune_types") or []) for t in f.types or []):
            ev.append({"type": "lightning", "fighter": f.name, "grounded": True})
            continue
        absorb = any(t in (lt.get("absorb_types") or []) for t in f.types or [])
        high = [p for p in f.parts if any(w in p.lower() for w in ("head", "crest", "back", "shoulder", "wing",
                                                                    "horn", "ear"))]
        part = eng.rng.choice(high or list(f.parts))
        keep, eng._source = eng._source, "the lightning"
        hit = eng._apply_damage(f, part, float(lt["power"]) * (float(lt["absorb"]) if absorb else 1.0))
        eng._source = keep
        e = {"type": "lightning", "fighter": f.name, "part": part, "hits": [hit], "absorbed": absorb,
             "airborne": eng.has(f, "airborne")}
        if not absorb:
            if eng.rng.random() < float(lt["stun"]):
                eng.set_status(f, "stunned", 1)
                e["stunned"] = True
            free = not eng.pinned_by(f.name) and not any(h.defender == f.name for h in eng.holds.values())
            if free and f.name not in eng.downed and (e["airborne"] or eng.rng.random() < float(lt["down"])):
                e["facing"] = eng.knock_down(f.name, why=f"lightning struck {f.name}")
                e["down"] = True
        st = body.state(f)
        st["composure"] = max(15.0, float(st.get("composure", 100.0)) - float(lt["fear"]) * 1.5)
        eng.involved.add(f.name)
        ev.append(e)
        return ev            # (one bolt a beat at most)
    if act and eng.rng.random() < float(lt["near"]):
        for f in act:
            st = body.state(f)
            st["composure"] = max(15.0, float(st.get("composure", 100.0)) - float(lt["fear"]))
        ev.append({"type": "lightning", "near": True, "fighters": [f.name for f in act]})
    return ev


def _gust(eng, act, gu, k):
    import body
    hit = []
    for f in act:
        if eng.has(f, "airborne"):
            if eng.rng.random() < float(gu["buffet"]):
                eng.set_status(f, "buffeted", 1)
                hit.append({"fighter": f.name, "air": True})
        elif f.name not in eng.downed and not eng.pinned_by(f.name):
            st = body.state(f)
            heavy = max(0.5, min(1.5, f.max_health / 2000.0))     # (a big body stands up to it better)
            st["footing"] = round(max(0.0, float(st.get("footing", 100.0)) - float(gu["footing"]) / heavy), 1)
            hit.append({"fighter": f.name, "air": False})
    return [{"type": "gust", "kind": k, "hit": hit, "fighters": [x["fighter"] for x in hit]}] if hit else []


def line(e):
    """The story's note for a lightning or a gust event."""
    if e["type"] == "gust":
        bits = [f"{x['fighter']} is shoved about in the air, fighting to hold her line" if x["air"] else
                f"{x['fighter']} braces and is pushed off her footing" for x in e.get("hit") or []]
        return ("A HARD GUST of wind slams across the arena, driving grit and rain before it: " + "; ".join(bits)
                + ".")
    if e.get("near"):
        return ("LIGHTNING strikes close by: a blinding white flash and a crack of thunder in the same instant, the "
                "ground shaking with it; both of them flinch, their fur standing on end (it hits neither).")
    if e.get("grounded"):
        return (f"LIGHTNING strikes {e['fighter']}: a blinding flash, and the bolt runs through her and into the "
                f"ground without harm; she is a Ground type, and it can't hurt her.")
    if e.get("absorbed"):
        return (f"LIGHTNING strikes {e['fighter']}: a blinding flash and a crack of thunder, and the Electric-type "
                f"takes the bolt into herself, crackling with it; it hardly hurts her.")
    from engine import poss_word
    out = (f"LIGHTNING STRIKES {e['fighter']}: a blinding white flash and a crack of thunder in the same instant; "
           f"the bolt hits {poss_word(e['fighter'])} {e['part'].lower()}, every muscle locking at once, her fur "
           f"standing and smoking")
    if e.get("down"):
        out += "; it throws her down" + (" out of the air" if e.get("airborne") else "")
    if e.get("stunned"):
        out += "; for a moment she is senseless"
    return out + ". (It does not kill her or end the fight by itself.)"
