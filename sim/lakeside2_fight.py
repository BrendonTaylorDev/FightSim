"""Test fight 2: Nocturne vs the sleek Ripples in the lakeside clearing again, on the newest build (gradient
resistance, status tells, the fight summary). A director-like stand-in: set pieces from both sides (feints, a juggle,
weather, Protect / Counter / Mirror Coat, a tail coil on the throat, a grab and a pummel, a drag into the shallows
and the dunk, charges into the trees, sustained streams, Will-O-Wisp), and both of them taking pin openings when the
dice give them one. Either can win; the one ahead at the end knocks the other down and finishes it with a pin whose
grip is on the THROAT, held until she passes out.
Usage: python sim/lakeside2_fight.py SEED            python sim/lakeside2_fight.py search 1 60"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import session, beat

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
    (R, [[A(R, action="strike", move="Aqua Jet", part="Chest", flavor="Aqua Jet across the sand, straight at the Absol's chest")]]),
    (N, [[A(N, action="strike", move="Night Slash", part="Right Upper Arm", feint=True, flavor="a feint at the face, then the cut low at her arm")]]),
    (R, [[A(R, action="strike", move="Rain Dance", part="Head", flavor="clouds pulled in off the lake, and rain")]]),
    (N, [[A(N, action="strike", move="Thunderbolt", hits=H("Chest", "Stomach", "Left Shoulder"), flavor="lightning into the rain-soaked Buizel")]]),
    (R, [[A(R, action="strike", move="Brick Break", part="Head", flavor="a chop down onto the Absol's head")]]),
    (N, [[A(N, action="strike", move="Iron Tail", part="Jaw", launch="launched", flavor="the sickle tail swung up under her jaw"),
          A(N, action="strike", move="Psycho Cut", hits=H("Stomach", "Chest", "Left Thigh"), flavor="a blade of force from the horn as she hangs in the air")],
         [A(N, action="strike", move="Iron Tail", part="Jaw", launch="knocked down", flavor="the sickle tail up under her jaw")]]),
    (R, [[A(R, action="strike", move="Water Gun", hits=H("Muzzle", "Nose", "Throat"), flavor="a jet of water straight into the Absol's face")]]),
    (N, [[A(N, action="strike", move="Counter", part="Head", flavor="she sets her feet and waits for it")]]),
    (R, [[A(R, action="strike", move="Crunch", part="Right Upper Foreleg", flavor="a lunge and a crushing bite at the foreleg")]]),
    (N, [[A(N, action="strike", move="Sucker Punch", part="Stomach", feint=True, flavor="a feint high, the forepaw driven low")]]),
    (N, [[A(N, action="strike", move="Iron Tail", part="Left Knee", launch="knocked down", flavor="the tail sweeps her knee out")]]),
    (N, [[A(N, action="drag", part="Left Upper Arm", landing=[{"surface": "the shallows", "parts": ["Upper Back", "Left Hip"], "severity": "light"}],
            flavor="dragged by the arm down the beach into the shallows")]]),
    (N, [[A(N, action="pin", pinned_against="the shallows",
            hits=[{"part": "Neck", "severity": "firm", "with": "her forepaw, holding her head under the shallow water"},
                  {"part": "Upper Back", "severity": "crushing", "with": "her full weight"}],
            flavor="held face-down in the shallows, her head pushed under")]]),
    (R, [[A(R, action="hold_start", move="Tail Bind", hits=[{"part": "Throat", "severity": "crushing", "with": "her twin tails, wound round it"}],
            flavor="her twin tails whip round the Absol's throat and pull tight")],
         [A(R, action="strike", move="Ice Fang", part="Throat", flavor="a freezing bite at the throat")]]),
    (R, [[A(R, action="strike", move="Ice Fang", part="Neck", flavor="a freezing bite at the neck while her tails squeeze")]]),
    (N, [[A(N, action="strike", move="Dark Pulse", hits=H("Head", "Chest", "Twin Tails"), flavor="a ring of dark force to break the coil")]]),
    (R, [[A(R, action="strike", move="Protect", part="Head", flavor="a shimmering shell thrown up around her")]]),
    (N, [[A(N, action="strike", move="Sunny Day", part="Head", flavor="the clouds burn off and the sun comes down white")]]),
    (N, [[A(N, action="strike", move="Will-O-Wisp", part="Chest", flavor="pale blue flames drifting at her")]]),
    (N, [[A(N, action="grapple", part="Left Upper Arm", hits=[{"part": "Left Upper Arm", "with": "her jaws", "severity": "light"}],
            flavor="jaws clamp on her left arm and haul her in"),
          A(N, action="strike", move="Slash", part="Stomach", count=4, flavor="short raking blows at no distance")]]),
    (R, [[A(R, action="strike", move="Mirror Coat", part="Head", flavor="a sheen spreading over her wet fur")]]),
    (N, [[A(N, action="strike", move="Psycho Cut", hits=H("Head", "Chest", "Stomach"), flavor="a blade of force from the horn")]]),
    (N, [[A(N, action="strike", move="Take Down", part="Chest", charge_into="an old oak", flavor="a shoulder-first ram across the clearing")]]),
    (R, [[A(R, action="strike", move="Hydro Pump", hits=H("Head", "Chest", "Throat"), sustain=3, flavor="Hydro Pump held into her")]]),
    (R, [[A(R, action="strike", move="Brick Break", part="Right Hock", launch="knocked down", flavor="a low chop that takes her hind leg out")]]),
    (R, [[A(R, action="strike", move="Crunch", part="Neck", count=3, flavor="bites on her where she lies")],
         [A(R, action="strike", move="Crunch", part="Neck", flavor="a bite at the neck")]]),
    (R, [[A(R, action="strike", move="Ice Beam", hits=H("Head", "Chest", "Left Shoulder"), sustain=2, flavor="Ice Beam held into her")]]),
    (R, [[A(R, action="strike", move="Aqua Jet", part="Stomach", charge_into="a tall pine", flavor="Aqua Jet low into the Absol's belly")]]),
    (N, [[A(N, action="strike", move="Night Slash", part="Throat", flavor="a cut at the throat")]]),
    (R, [[A(R, action="strike", move="Swift", hits=H("Throat", "Chest", "Head"), flavor="a spray of stars")]]),
]

# when the planned one can't act, or the other one gets the beat
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

# pins taken on the dice's openings during the fight (no throat grip: those are for the end)
PINS = {
    N: [[{"part": "Chest", "severity": "crushing", "with": "her forepaws"}, {"part": "Left Thigh", "severity": "firm", "with": "her hind paw"}],
        [{"part": "Upper Back", "severity": "crushing", "with": "her full weight"}, {"part": "Right Upper Arm", "severity": "firm", "with": "her jaws"}],
        [{"part": "Stomach", "severity": "crushing", "with": "her left forepaw"}, {"part": "Left Shoulder", "severity": "firm", "with": "her right forepaw"}]],
    R: [[{"part": "Chest", "severity": "crushing", "with": "her knees"}, {"part": "Left Upper Foreleg", "severity": "firm", "with": "her paws"}],
        [{"part": "Back", "severity": "crushing", "with": "her full weight"}, {"part": "Sickle Tail", "severity": "firm", "with": "her twin tails"}],
        [{"part": "Belly", "severity": "crushing", "with": "her feet"}, {"part": "Right Shoulder", "severity": "firm", "with": "her paws"}]],
}
PIN_LOOK = {N: ["pinned flat on the sand, forepaws on her chest", "pinned face-down, jaws on her arm",
                "pinned on her back, a forepaw in her belly"],
            R: ["kneeling on the Absol's chest", "flat across the Absol's back", "standing on the Absol's belly"]}

# the finish: the throat pin, held until she goes under
THROAT_PIN = {
    N: [{"part": "Throat", "severity": "crushing", "with": "her jaws, closed on the throat"},
        {"part": "Chest", "severity": "firm", "with": "her forepaws"}],
    R: [{"part": "Throat", "severity": "crushing", "with": "her forearm, pressed across the throat"},
        {"part": "Chest", "severity": "firm", "with": "her knees"}],
}
THROAT_LOOK = {N: "pinned on her back, jaws closed on her throat", R: "kneeling on the Absol's chest, forearm across her throat"}
KNOCK = {N: [A(N, action="strike", move="Iron Tail", part="Stomach", launch="knocked down", flavor="the tail across her middle")],
         R: [A(R, action="strike", move="Brick Break", part="Left Hock", launch="knocked down", flavor="a low chop that takes her legs")]}
GROUND = {N: [A(N, action="strike", move="Slash", part="Throat", count=3, flavor="raking blows at her throat where she lies")],
          R: [A(R, action="strike", move="Crunch", part="Throat", count=3, flavor="bites at the throat where she lies")]}


def run(seed, verbose=False, finish_at=14.0):
    s = session(seed, scene=SCENE, settings=SETTINGS)
    eng = s.eng
    rng = random.Random(seed * 31 + 7)
    log, caps, tags = [], [], []
    st = {"i": 0, "ans": {R: 0, N: 0}, "pin": {R: 0, N: 0}, "tries": 0, "fin": 0}

    def play(acts, tag):
        out, cap = beat(s, acts, log, roll=False)
        caps.append((tag, cap))
        tags.append(tag)

    def try_all(options, tag):
        why = ""
        for acts in options:
            try:
                play(acts, tag)
                return True, ""
            except ValueError as e:
                why = str(e)
                if verbose:
                    print(f"[{tag}] refused: {str(e)[:120]}")
        return False, why

    def answer(who, tag):
        k = st["ans"][who]
        opts = ANSWERS[who][k % len(ANSWERS[who]):] + ANSWERS[who][:k % len(ANSWERS[who])]
        ok, _ = try_all(opts, tag)
        if ok:
            st["ans"][who] += 1
        return ok

    def strength(name):
        return eng.strength(eng.get(name))

    def try_pin(who, throat=False):
        foe = R if who == N else N
        if who in eng.downed or eng.pinned_by(who) or eng.pinning(who):
            return False
        ok, _ = eng.pin_allowed(foe)
        if not ok:
            return False
        if throat:
            hits, look = THROAT_PIN[who], THROAT_LOOK[who]
        else:
            k = st["pin"][who] % len(PINS[who])
            hits, look = PINS[who][k], PIN_LOOK[who][k]
        done, _ = try_all([[A(who, action="pin", hits=hits, flavor=look)]], f"{who.lower()} pins" + (" (throat)" if throat else ""))
        if done:
            st["pin"][who] += 1
        return done

    beats = 0
    while beats < 110 and not s.over:
        beats += 1
        eng.roll_pin_windows()
        holding = next(((p["attacker"], p["defender"]) for p in eng.pins.values()), None)
        if holding:
            att = holding[0]
            # the pinner mostly bears down; now and then she works the pinned one over inside the pin
            if rng.random() < 0.25 and eng.get(att).energy > 30:
                part = rng.choice(["Throat", "Chest", "Neck"]) if st["fin"] else rng.choice(["Chest", "Stomach" if holding[1] == R else "Belly", "Neck"])
                mv = rng.choice(["Slash", "Bite", "Night Slash"] if att == N else ["Crunch", "Ice Fang", "Brick Break"])
                ok, _ = try_all([[A(att, action="strike", move=mv, part=part, count=2, flavor="blows driven in while she holds her down")]], "in-pin blows")
                if ok:
                    continue
            play([A(att, action="breather", flavor="bears down and holds the pin")], "pin holds")
            continue
        finishing = st["i"] >= len(STEPS) or min(strength(N), strength(R)) < finish_at
        if finishing:
            lead = N if strength(N) >= strength(R) else R
            foe = R if lead == N else N
            if eng.get(lead).energy < 20 and lead not in eng.downed:
                play([A(lead, action="breather", flavor=f"{lead} catches her breath")], "breather")
                continue
            if try_pin(lead, throat=True):
                st["fin"] += 1
                continue
            if lead in eng.downed or eng.pinned_by(lead):
                play([A(lead, action="breather", flavor=f"{lead} gets her legs back under her")], "breather")
                continue
            # the loser fights back now and then
            if rng.random() < 0.25 and foe not in eng.downed and answer(foe, f"{foe.lower()} fights back"):
                continue
            plan = GROUND[lead] if foe in eng.downed else KNOCK[lead]
            ok, _ = try_all([plan], "finish")
            if not ok and not answer(lead, f"{lead.lower()} presses"):
                play([A(lead, action="breather", flavor=f"{lead} circles")], "breather")
            continue
        who, options = STEPS[st["i"]]
        other = R if who == N else N
        # an opening: either may take it (like the director, who is told to go for it, usually does)
        for taker in ([who, other] if rng.random() < 0.5 else [other, who]):
            if rng.random() < 0.7 and try_pin(taker):
                break
        else:
            taker = None
        if taker and tags and tags[-1].endswith("pins"):
            continue
        actor = eng.get(who)
        if actor.energy < 25 and who not in eng.downed:
            st["rests"] = st.get("rests", 0) + 1
            if not (st["rests"] % 2 == 1 and eng.get(other).energy >= 20 and other not in eng.downed
                    and answer(other, f"{other.lower()} presses")):
                play([A(who, action="breather", flavor=f"{who} catches her breath")], "breather")
            continue
        ok, why = try_all(options, f"step {st['i'] + 1}")
        if ok:
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
            "is guarding her", "blocks", "Recoil", "carries her on into", "ESCAPES", "sputtering", "breathless",
            "dazed", "doubled", "off balance", "overcommits", "CLASH", "LAST STAND", "dragged", "shallows",
            "caught open", "Hold", "constricted", "burned", "Protect", "adrenaline")


def finish_info(s):
    fin = (s.eng.chronicle or {}).get("finish") or {}
    return fin


def summary(s, log, tags):
    text = "\n".join(log)
    hit = [f for f in FEATURES if f.lower() in text.lower()]
    fin = finish_info(s)
    return {"winner": s.eng.winner(), "beats": len(tags), "ripples": round(s.eng.strength(s.eng.get(R))),
            "nocturne": round(s.eng.strength(s.eng.get(N))), "features": len(hit),
            "missing": [f for f in FEATURES if f.lower() not in text.lower()],
            "finish": (fin.get("cause"), fin.get("part")), "pins": dict(s.eng.chronicle.get("pins", {})),
            "escapes": dict(s.eng.chronicle.get("escapes", {}))}


if __name__ == "__main__":
    if sys.argv[1] == "search":
        for sd in range(int(sys.argv[2]), int(sys.argv[3])):
            try:
                s, log, caps, tags = run(sd)
            except Exception as e:
                print(sd, "ERROR", repr(e)[:300], flush=True)
                continue
            sm = summary(s, log, tags)
            print(sd, sm["winner"], sm["beats"], "N", sm["nocturne"], "R", sm["ripples"], "feat", sm["features"],
                  sm["finish"], "pins", sm["pins"], "esc", sm["escapes"], flush=True)
    else:
        s, log, caps, tags = run(int(sys.argv[1]), verbose=True)
        sm = summary(s, log, tags)
        print(sm)
        print(tags)
