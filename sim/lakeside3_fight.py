"""Test fight 3: Nocturne vs the sleek Ripples in the lakeside clearing, on the final build (submissions, fuller
pins, the new pin positions, chokes by grip, breaking points from squeezes). The stand-in director acts the way the
local director is pointed by the system: it takes the pin openings and submission openings the engine rolls (with the
engine's own pin shapes, filled out with every free limb), works a submission while it's on and lets it go into a pin
when she's stuck, uses what the holder has free on her, and plays a few set pieces in between. The one ahead at the
end finishes it with a pin held until she passes out.
Usage: python sim/lakeside3_fight.py SEED            python sim/lakeside3_fight.py search 1 60"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import session, beat
import director as D

N, R = "Nocturne", "Ripples"
SETTINGS = ["/variant Ripples sleek", "/scale 5", "/resscale 0.75", "/healthloss 0.2", "/numb off",
            '/learn Nocturne "Sunny Day"', '/learn Nocturne "Counter"', '/learn Ripples "Rain Dance"',
            '/learn Ripples "Protect"', '/learn Ripples "Mirror Coat"']
SCENE = "lakeside forest"


def A(att, **k):
    k["attacker"] = att
    k.setdefault("defender", R if att == N else N)
    k.setdefault("flavor", "")
    return k


def H(*parts):
    return [{"part": p} for p in parts]


STEPS = [
    (N, [[A(N, action="strike", move="Night Slash", part="Left Shoulder", feint=True, flavor="a feint at the eyes, then the claws low across the shoulder")]]),
    (R, [[A(R, action="strike", move="Aqua Jet", part="Chest", charge_into="an old oak", flavor="Aqua Jet across the grass, into the Absol's chest")]]),
    (R, [[A(R, action="strike", move="Rain Dance", part="Head", flavor="clouds dragged in off the lake, and rain")]]),
    (N, [[A(N, action="strike", move="Iron Tail", part="Right Knee", launch="knocked down", flavor="the sickle tail swept low through her knee")]]),
    (R, [[A(R, action="strike", move="Brick Break", part="Horn", flavor="a chop at the base of the horn")]]),
    (N, [[A(N, action="strike", move="Thunderbolt", flavor="lightning off the horn into the rain-soaked Buizel")]]),
    (R, [[A(R, action="strike", move="Water Pulse", hits=H("Muzzle", "Nose", "Throat"), flavor="a ring of water into the Absol's face")]]),
    (N, [[A(N, action="strike", move="Iron Tail", part="Jaw", launch="launched", flavor="the sickle tail up under her jaw"),
          A(N, action="strike", move="Psycho Cut", hits=H("Stomach", "Chest", "Right Thigh"), flavor="a blade of force off the horn as she hangs there")],
         [A(N, action="strike", move="Iron Tail", part="Jaw", launch="knocked down", flavor="the sickle tail up under her jaw")]]),
    (R, [[A(R, action="strike", move="Protect", part="Head", flavor="a shimmering shell thrown up")]]),
    (N, [[A(N, action="strike", move="Sunny Day", part="Head", flavor="the clouds burned off, the sun hard and white")]]),
    (R, [[A(R, action="strike", move="Crunch", part="Right Upper Foreleg", flavor="a lunge and a crushing bite at the foreleg")]]),
    (N, [[A(N, action="grapple", part="Right Upper Arm", hits=[{"part": "Right Upper Arm", "with": "her jaws", "severity": "light"}],
            flavor="jaws clamp on her right arm and haul her in"),
          A(N, action="strike", move="Slash", part="Stomach", count=4, flavor="short raking blows at no distance")]]),
    (R, [[A(R, action="strike", move="Mirror Coat", part="Head", flavor="a sheen spreading over her fur")]]),
    (N, [[A(N, action="strike", move="Dark Pulse", hits=H("Head", "Chest", "Stomach"), flavor="a ring of dark force")]]),
    (R, [[A(R, action="strike", move="Hydro Pump", hits=H("Head", "Chest", "Throat"), sustain=2, flavor="Hydro Pump held into her")]]),
    (N, [[A(N, action="strike", move="Take Down", part="Chest", charge_into="a tall pine", flavor="a shoulder-first ram across the clearing")]]),
    (R, [[A(R, action="strike", move="Brick Break", part="Left Hock", launch="knocked down", flavor="a low chop that takes her hind leg")]]),
    (R, [[A(R, action="strike", move="Ice Fang", part="Neck", flavor="a freezing bite at the neck")]]),
    (N, [[A(N, action="strike", move="Sucker Punch", part="Stomach", feint=True, flavor="a feint high, the forepaw driven low")]]),
    (R, [[A(R, action="strike", move="Swift", hits=H("Head", "Chest", "Right Shoulder"), flavor="a spray of stars")]]),
]

ANSWERS = {
    R: [[A(R, action="strike", move="Crunch", part="Right Upper Foreleg", flavor="a hard bite at the foreleg")],
        [A(R, action="strike", move="Water Pulse", hits=H("Head", "Neck", "Throat"), flavor="a ring of water into the face")],
        [A(R, action="strike", move="Brick Break", part="Neck", flavor="a chop at the neck")],
        [A(R, action="strike", move="Swift", hits=H("Head", "Chest", "Right Shoulder"), flavor="a spray of stars")]],
    N: [[A(N, action="strike", move="Psycho Cut", hits=H("Chest", "Left Shoulder", "Throat"), flavor="a blade of force from the horn")],
        [A(N, action="strike", move="Slash", part="Chest", flavor="a rake across the chest")],
        [A(N, action="strike", move="Bite", part="Neck", flavor="a lunge for the neck")],
        [A(N, action="strike", move="Night Slash", part="Right Thigh", flavor="a cut at the thigh")]],
}
# what the holder has free during a submission, used on her at point-blank
FREE = {R: [("Water Gun", "Head", "a jet of water straight into the back of her head"),
            ("Swift", "Head", "stars spat into her face from point-blank")],
        N: [("Psycho Cut", "Back", "a blade of force off the horn into her back"),
            ("Thunderbolt", "", "lightning off the horn into her, held fast as she is")]}
KNOCK = {N: [A(N, action="strike", move="Iron Tail", part="Stomach", launch="knocked down", flavor="the tail across her middle")],
         R: [A(R, action="strike", move="Brick Break", part="Left Hock", launch="knocked down", flavor="a low chop that takes her legs")]}


def run(seed, verbose=False, finish_at=14.0):
    s = session(seed, scene=SCENE, settings=SETTINGS)
    eng = s.eng
    rng = random.Random(seed * 37 + 11)
    log, caps, tags = [], [], []
    st = {"i": 0, "ans": {R: 0, N: 0}, "tries": 0, "last_shape": None}

    def play(acts, tag):
        out, cap = beat(s, acts, log, roll=False)
        caps.append((tag, cap))
        tags.append(tag)

    def try_all(options, tag):
        for acts in options:
            try:
                play(acts, tag)
                return True
            except ValueError as e:
                if verbose:
                    print(f"[{tag}] refused: {str(e)[:120]}")
        return False

    def answer(who, tag):
        k = st["ans"][who]
        opts = ANSWERS[who][k % len(ANSWERS[who]):] + ANSWERS[who][:k % len(ANSWERS[who])]
        if try_all(opts, tag):
            st["ans"][who] += 1
            return True
        return False

    def strength(name):
        return eng.strength(eng.get(name))

    def pin_action(who):
        foe = R if who == N else N
        shapes = D.pin_shapes(eng, eng.get(who), eng.get(foe))
        shapes.pop(st["last_shape"], None)
        shapes = {k: v for k, v in shapes.items() if k not in ("dunk", "wall_choke")} or shapes
        if not shapes:
            return None
        name = rng.choice(sorted(shapes))
        look, contacts = shapes[name]
        st["last_shape"] = name
        sev = ["crushing"] + ["firm"] * (len(contacts) - 1)
        return A(who, action="pin", flavor=look.split("; and ")[0], hits=[{"part": p, "severity": v, "with": w}
                                                              for (p, w), v in zip(contacts, sev)])

    def try_pin(who):
        foe = R if who == N else N
        if who in eng.downed or eng.pinned_by(who) or eng.pinning(who) or eng.has(eng.get(who), "reeling"):
            return False
        if not eng.pin_allowed(foe)[0]:
            return False
        act = pin_action(who)
        return bool(act) and try_all([[act]], f"{who.lower()} pins")

    def try_sub(who):
        foe = R if who == N else N
        if (getattr(eng, "sub_window", None) or {}).get(foe) is not True or who in eng.downed:
            return False
        shapes = eng.submission_shapes(who, foe)
        if not shapes:
            return False
        name = rng.choice(sorted(shapes))
        acts = [A(who, action="submission", improvised_name=name, flavor=shapes[name]["look"][:120])]
        if rng.random() < 0.5:
            mv, part, fl = rng.choice(FREE[who])
            acts.append(A(who, action="strike", move=mv, flavor=fl, **({"part": part} if part else {})))
        return try_all([acts, acts[:1]], f"{who.lower()} submission")

    beats = 0
    while beats < 110 and not s.over:
        beats += 1
        eng.roll_pin_windows()
        pin = next(iter(eng.pins.values()), None)
        if pin:
            att = pin["attacker"]
            if rng.random() < 0.2 and eng.get(att).energy > 30:
                mv = rng.choice(["Slash", "Bite", "Night Slash"] if att == N else ["Crunch", "Ice Fang", "Brick Break"])
                part = rng.choice(["Chest", "Neck", "Throat"])
                if try_all([[A(att, action="strike", move=mv, part=part, count=2, flavor="blows driven in while she holds her down")]], "in-pin blows"):
                    continue
            play([A(att, action="breather", flavor="bears down and holds the pin")], "pin holds")
            continue
        sub = next((h for h in eng.holds.values() if h.sub), None)
        if sub:
            att, dfn = sub.attacker, sub.defender
            hs = [h for h in eng.holds.values() if h.sub and h.attacker == att]
            if eng.sub_stuck(eng.get(dfn), hs) and rng.random() < 0.7 and try_pin(att):
                continue
            if rng.random() < 0.35:
                mv, part, fl = rng.choice(FREE[att])
                if try_all([[A(att, action="strike", move=mv, flavor=fl, **({"part": part} if part else {}))]], "submission + free move"):
                    continue
            play([A(att, action="breather", flavor=f"cranks the {sub.sub} harder")], "submission holds")
            continue
        lead = N if strength(N) >= strength(R) else R
        finishing = st["i"] >= len(STEPS) or min(strength(N), strength(R)) < finish_at
        # openings first, the way the system points the director: a submission (rarer), then a pin
        order = [lead, R if lead == N else N] if finishing else ([N, R] if rng.random() < 0.5 else [R, N])
        took = False
        for who in order:
            if rng.random() < 0.8 and try_sub(who):
                took = True
                break
        if not took:
            for who in order:
                foe_ = R if who == N else N
                take = 1.0 if (finishing and who == lead) else (0.75 if foe_ in eng.downed else 0.4)
                if rng.random() < take:
                    if try_pin(who):
                        took = True
                        break
        if took:
            continue
        if finishing:
            foe = R if lead == N else N
            if eng.get(lead).energy < 20 and lead not in eng.downed:
                play([A(lead, action="breather", flavor=f"{lead} catches her breath")], "breather")
                continue
            if lead in eng.downed:
                play([A(lead, action="breather", flavor=f"{lead} gets her legs back under her")], "breather")
                continue
            if rng.random() < 0.25 and foe not in eng.downed and answer(foe, f"{foe.lower()} fights back"):
                continue
            if foe not in eng.downed and try_all([KNOCK[lead]], "finish"):
                continue
            if not answer(lead, f"{lead.lower()} presses"):
                play([A(lead, action="breather", flavor=f"{lead} circles")], "breather")
            continue
        who, options = STEPS[st["i"]]
        other = R if who == N else N
        if eng.get(who).energy < 25 and who not in eng.downed:
            st["rests"] = st.get("rests", 0) + 1
            if not (st["rests"] % 2 == 1 and eng.get(other).energy >= 20 and other not in eng.downed
                    and answer(other, f"{other.lower()} presses")):
                play([A(who, action="breather", flavor=f"{who} catches her breath")], "breather")
            continue
        if try_all(options, f"step {st['i'] + 1}"):
            st["i"] += 1
            st["tries"] = 0
            continue
        if not (other not in eng.downed and answer(other, f"{other.lower()} presses")):
            play([A(who, action="breather", flavor=f"{who} gathers herself")], "breather")
        st["tries"] += 1
        if st["tries"] >= 2:
            st["i"] += 1
            st["tries"] = 0
    return s, log, caps, tags


FEATURES = ("Feint", "JUGGLE", "Counter", "Mirror Coat", "**RAIN**", "**SUN**", "Pummel", "FRENZY", "DEVASTATING",
            "is guarding her", "blocks", "Recoil", "ESCAPES", "sputtering", "breathless", "dazed", "doubled over",
            "off balance", "overcommits", "CLASH", "LAST STAND", "caught open", "SUBMISSION HOLD", "locked in a submission",
            "breaks", "Protect", "adrenaline")


def summary(s, log, tags):
    text = "\n".join(log)
    fin = (s.eng.chronicle or {}).get("finish") or {}
    subs = [t for t in tags if "submission" in t]
    return {"winner": s.eng.winner(), "beats": len(tags), "N": round(s.eng.strength(s.eng.get(N))),
            "R": round(s.eng.strength(s.eng.get(R))),
            "features": sum(f.lower() in text.lower() for f in FEATURES),
            "missing": [f for f in FEATURES if f.lower() not in text.lower()],
            "finish": (fin.get("cause"), fin.get("kind"), fin.get("part")), "pins": dict(s.eng.chronicle.get("pins", {})),
            "escapes": dict(s.eng.chronicle.get("escapes", {})), "sub_beats": len(subs),
            "sub_free": tags.count("submission + free move")}


if __name__ == "__main__":
    if sys.argv[1] == "search":
        for sd in range(int(sys.argv[2]), int(sys.argv[3])):
            try:
                s, log, caps, tags = run(sd)
            except Exception as e:
                print(sd, "ERROR", repr(e)[:300], flush=True)
                continue
            sm = summary(s, log, tags)
            print(sd, sm["winner"], sm["beats"], "N", sm["N"], "R", sm["R"], "feat", sm["features"], sm["finish"],
                  "pins", sm["pins"], "esc", sm["escapes"], "sub", sm["sub_beats"], "free", sm["sub_free"], flush=True)
    else:
        s, log, caps, tags = run(int(sys.argv[1]), verbose=True)
        print(summary(s, log, tags))
        print(tags)
