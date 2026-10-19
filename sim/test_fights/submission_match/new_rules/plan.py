import random as _rnd
_r = _rnd.Random(77)
def foe_of(x): return R if x == N else N
# each one's target: Nerine works Ripples' left leg, Ripples works Nerine's neck and throat
TARGET = {N: ["Left Knee", "Left Thigh", "Left Foot"], R: ["Neck", "Throat"]}
STRIKES = {
 N: [("Brick Break", "Left Knee"), ("Bite", "Left Thigh"), ("Aqua Tail", "Left Knee"), ("Quick Attack", "Left Thigh"),
     ("imp:low heel kick|Fighting|heavy|a whipping kick into the side of the hurt knee", "Left Knee"),
     ("imp:tail lash|Normal|solid|both tails cracked across the hurt shin like a whip", "Left Foot"),
     ("imp:knee to the thigh|Fighting|heavy|she drives her knee into the meat of the hurt thigh", "Left Thigh"),
     ("Bite", "Left Knee")],
 R: [("Crunch", "Neck"), ("Brick Break", "Neck"), ("Ice Fang", "Throat"),
     ("imp:fin slash|Water|solid|the hard edge of her forearm fin raked across the throat", "Throat"),
     ("imp:tail crack|Normal|heavy|her twin tails spun up and cracked across the side of the neck", "Neck"),
     ("Water Gun", "Head"), ("Aqua Jet", "Chest")]}
def strike(att, mv, part):
    if mv.startswith("imp:"):
        nm, ty, sv, fl = mv[4:].split("|")
        return A(att, "strike", move="improvised", improvised_name=nm, improvised_type=ty, part=part, severity=sv, flavor=fl)
    if mv in ("Water Gun",):
        return A(att, "strike", move=mv, hits=[{"part": "Head", "severity": "solid"}, {"part": "Throat", "severity": "solid"}], flavor="a jet of water straight into her face and throat")
    return A(att, "strike", move=mv, part=part, flavor="")
CRANK = {N: ["she leans back and cranks it, teeth gritted", "she shifts her grip and wrenches it tighter",
             "she sits her weight down into it", "she bears down on it, panting, refusing to ease off"],
         R: ["she tightens the tails a notch, patient", "she settles her weight and squeezes, saying nothing",
             "her tails cinch another turn", "she breathes slowly and does not let go"]}
FIGHT = {N: ["Nerine thrashes and twists, snarling, trying to rip loose", "she claws at the ground and bucks",
             "she wrenches her whole body against it", "she goes still for a breath, then heaves against it"],
         R: ["Ripples twists, slow and careful, looking for the angle out", "she braces a foot and pushes against it",
             "she squirms, hissing through her teeth", "she pries at the grip with her free paw"]}
def has_hold(eng, a, d): return any(h.attacker == a and h.defender == d for h in eng.holds.values())
def pinned(eng, who): return bool(eng.pinned_by(who))
def auto(att, phase):
    def f(eng):
        foe = foe_of(att)
        # someone is held: the beat is the hold
        for a_, d_ in ((att, foe), (foe, att)):
            if has_hold(eng, a_, d_) or eng.pinning(a_) and d_ in eng.pinning(a_):
                if _r.random() < 0.15 and a_ not in eng.downed:
                    mv = "Brick Break" if a_ == N else "Crunch"
                    return [A(a_, "strike", move=mv, part=_r.choice(["Head", "Neck", "Chest"]),
                              flavor="with what she has free, she drives a short blow in while she holds her")]
                return [A(d_, "struggle", defender="", flavor=_r.choice(FIGHT[d_]))]
        # an opening on the one who is down: lock a submission
        for a_ in (att, foe):
            d_ = foe_of(a_)
            if (eng.__dict__.get("sub_window") or {}).get(d_) and a_ not in eng.downed and phase >= 1:
                shapes = eng.submission_shapes(a_, d_)
                aimed = [n for n, sh in shapes.items() if any(c[0] in TARGET[a_] for c in sh["contacts"])]
                if _r.random() < 0.3:
                    inv = {N: [("riverbank knee crank", [("Left Knee", "both paws, twisting it against the grain"),
                                                         ("Left Foot", "her twin tails, wound round it and hauling the other way")]),
                               ("heel hook and bite", [("Left Foot", "her arm, hooked under the heel and wrenching"),
                                                       ("Left Knee", "her jaws, clamped on the side of it")])],
                           R: [("fin-edge throat press", [("Throat", "the hard edge of her forearm fin, pressed across it"),
                                                          ("Neck", "her other paw, hauling the head back onto it")]),
                               ("twin-tail garrote", [("Neck", "her twin tails, crossed behind it and drawn tight"),
                                                      ("Upper Back", "her knees, driven into it")])]}[a_]
                    nm, gr = _r.choice(inv)
                    if eng.sub_uses(nm) < 1:
                        return [A(a_, "submission", improvised_name=nm, flavor=nm,
                                  hits=[{"part": p, "with": w, "severity": "crushing"} for p, w in gr])]
                if shapes and (aimed or a_ == N):
                    pool = sorted(aimed or shapes)
                    low = min(eng.sub_uses(n) for n in pool)
                    name = _r.choice([n for n in pool if eng.sub_uses(n) == low])
                    return [A(a_, "submission", improvised_name=name, flavor=shapes[name]["look"][:140])]
        if att in eng.downed:
            return [A(att, "breather", flavor="she gets her feet back under her")]
        f_ = eng.get(foe)
        if att == R and phase >= 1 and not eng.has(eng.get(R), "armed") and _r.random() < 0.12 and foe not in eng.downed:
            return [A(R, "strike", move="improvised", improvised_name="ice blade slash", improvised_type="Ice",
                      part=TARGET[R][0], severity="heavy", conjure="ice blade",
                      flavor="she drags lake water up her forearm fin with a flick of Ice Fang's cold and freezes it into a blade")]
        if att == R and eng.has(eng.get(R), "armed") and _r.random() < 0.7 and foe not in eng.downed:
            return [A(R, "strike", move="improvised", improvised_name=_r.choice(["ice blade slash", "ice blade cut"]),
                      improvised_type="Ice", part=_r.choice(TARGET[R]), severity="heavy", flavor="the ice blade again")]
        # Ripples: tails round the throat or a limb once the other is worn
        if att == R and phase >= 1 and _r.random() < 0.22 and foe not in eng.downed:
            if _r.random() < 0.6:
                return [A(R, "hold_start", move="Tail Bind", part="Neck", ramp="tightening",
                          hits=[{"part": "Neck", "with": "her twin tails", "severity": "crushing"},
                                {"part": "Throat", "with": "her twin tails", "severity": "firm"}],
                          flavor="her tails whip up and round the throat and cinch")]
            return [A(R, "hold_start", move="Tail Bind", part="Neck", ramp="tightening",
                      hits=[{"part": "Neck", "with": "her twin tails", "severity": "firm"}],
                      flavor="her tails loop round the neck from behind and cinch")]
        # Nerine: a standing hold on the hurt leg, worked with whatever she can
        if att == N and phase >= 1 and _r.random() < 0.18 and foe not in eng.downed:
            way = _r.choice([("standing knee wrench", "she catches the hurt leg as it comes up, traps it under her arm and wrenches the knee"),
                             ("leg grapevine", "she hooks her own leg round the hurt one from behind and bends it against the joint"),
                             ("trunk knee bar", "she drives her back against the fallen trunk, the hurt leg trapped across it, and leans")])
            return [A(N, "hold_start", move="improvised", improvised_name=way[0], improvised_type="Fighting",
                      part=TARGET[N][0], ramp="tightening",
                      hits=[{"part": TARGET[N][0], "with": "both paws", "severity": "firm"},
                            {"part": TARGET[N][1], "with": "her arm", "severity": "firm"}], flavor=way[1])]
        # Nerine: takedowns
        if att == N and _r.random() < (0.5 if phase else 0.3) and foe not in eng.downed:
            if _r.random() < 0.5:
                return [A(N, "slam", landing=[{"surface": "the grass", "parts": ["Upper Back", "Lower Back"],
                                              "severity": "heavy"}], flavor="she gets under her and slams her down on her back")]
            return [A(N, "throw", landing=[{"surface": _r.choice(["an old oak", "the fallen trunk", "the root-knotted ground"]),
                                           "parts": ["Upper Back", "Left Shoulder"], "severity": "heavy"},
                                          {"surface": "the grass", "parts": ["Left Hip"], "severity": "solid"}],
                      flavor="she hauls her off her feet and throws her")]
        if foe in eng.downed:
            if att == N and _r.random() < 0.4:
                return [A(N, "drag", landing=[{"surface": "the root-knotted ground", "parts": ["Left Knee", "Left Thigh"],
                                              "severity": "solid"}], flavor="she grabs the hurt leg by the ankle and drags her across the roots by it")]
            return [A(att, "strike", move="improvised", improvised_name="knee stomp" if att == N else "pouncing bite",
                      improvised_type="Normal" if att == N else "Dark", part=TARGET[att][0],
                      severity="heavy", flavor=("she stamps down on the hurt knee while she is down" if att == N else
                                                "she pounces and bites down on the back of the neck while she is down"))]
        if att == N and foe in eng.downed and _r.random() < 0.3:
            return [A(N, "drag", landing=[{"surface": "the root-knotted ground", "parts": ["Left Knee", "Left Thigh"],
                                          "severity": "solid"}], flavor="she grabs the hurt leg by the ankle and drags her across the roots by it")]
        if att == N and _r.random() < 0.12 and foe not in eng.downed:
            return [A(N, "strike", move="improvised", improvised_name="root trip", improvised_type="Normal",
                      part="Left Knee", severity="solid", launch="knocked down",
                      flavor="she hooks the hurt leg and trips her backward over a humped root")]
        last = getattr(eng, "move_log", [])[-2:]
        opts = [x for x in STRIKES[att] if not any(m == (x[0] if not x[0].startswith("imp:") else x[0][4:].split("|")[0].title()) for _w, m in last if _w == att)]
        mv, part = _r.choice(opts or STRIKES[att])
        return [strike(att, mv, part)]
    return f
PLAN = []
for i in range(1, 61):
    att = N if _r.random() < 0.55 else R
    PLAN.append(auto(att, 0 if i <= 8 else 1))
