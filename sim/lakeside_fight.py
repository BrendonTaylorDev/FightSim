"""A full-feature test fight: Nocturne vs the sleek Ripples in the lakeside clearing (warm, sunny, a breeze off the
lake). A scripted director (the choices) on the real engine (every roll): feints, a juggle, weather moves, Protect,
Counter and Mirror Coat, a grab and a pummel, ground pummels, a drag into the shallows and the dunk, a coil, a charge
into a tree (recoil, or a miss into the trunk), sustained streams, and Nocturne finishing it.
Usage: python sim/lakeside_fight.py SEED            python sim/lakeside_fight.py search 1 60"""
import sys, os, re
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


# each step: (who, [alternative action lists, tried in order])
STEPS = [
    (N, [[A(N, action="strike", move="Night Slash", part="Left Shoulder", flavor="a long probing cut at the shoulder")]]),
    (R, [[A(R, action="strike", move="Aqua Jet", part="Chest", charge_into="an old oak", flavor="Aqua Jet, straight into the Absol's chest")]]),
    (N, [[A(N, action="strike", move="Sunny Day", part="Head", flavor="the sun hardens to a white glare")]]),
    (R, [[A(R, action="strike", move="Rain Dance", part="Head", flavor="clouds pulled in off the lake, and rain")]]),
    (N, [[A(N, action="strike", move="Bite", part="Right Upper Arm", feint=True, flavor="a feint at the face, then the bite low at the arm")]]),
    (R, [[A(R, action="strike", move="Water Gun", hits=H("Muzzle", "Head", "Neck"), flavor="a jet of water straight into the Absol's face")]]),
    (N, [[A(N, action="strike", move="Iron Tail", part="Jaw", launch="launched", flavor="the sickle tail swung up under her jaw"),
          A(N, action="strike", move="Night Slash", part="Stomach", flavor="the claws across her stomach as she hangs in the air")],
         [A(N, action="strike", move="Iron Tail", part="Jaw", launch="knocked down", flavor="the sickle tail up under her jaw")]]),
    (R, [[A(R, action="strike", move="Protect", part="Head", flavor="a shimmering shell thrown up around her")]]),
    (N, [[A(N, action="strike", move="Bite", part="Neck", flavor="a lunge for the throat")]]),
    (R, [[A(R, action="strike", move="Ice Fang", part="Left Upper Foreleg", flavor="a freezing bite at the foreleg")]]),
    (N, [[A(N, action="grapple", part="Right Upper Arm", hits=[{"part": "Right Upper Arm", "with": "her jaws", "severity": "light"}],
            flavor="jaws clamp on her right arm and drag her in"),
          A(N, action="strike", move="Slash", part="Stomach", count=4, flavor="short raking blows at no distance")]]),
    (R, [[A(R, action="strike", move="Mirror Coat", part="Head", flavor="a sheen spreading over her fur")]]),
    (N, [[A(N, action="strike", move="Dark Pulse", hits=H("Head", "Chest", "Stomach"), flavor="a ring of dark force")]]),
    (N, [[A(N, action="strike", move="Iron Tail", part="Left Knee", launch="knocked down", flavor="the tail sweeps her knee out")],
         [A(N, action="strike", move="Sucker Punch", part="Stomach", launch="knocked down", flavor="a forepaw driven low")]]),
    (N, [[A(N, action="strike", move="Slash", part="Stomach", count=4, flavor="raking blows on her where she lies")],
         [A(N, action="strike", move="Night Slash", part="Chest", flavor="a cut across her chest")]]),
    (N, [("setup", [A(N, action="strike", move="Iron Tail", part="Left Knee", launch="knocked down",
                      flavor="the tail sweeps her legs again")]),
         [A(N, action="drag", part="Left Upper Arm", landing=[{"surface": "the shallows", "parts": ["Back", "Left Hip"], "severity": "light"}],
            flavor="dragged by the arm down the beach into the shallows")]]),
    (N, [[A(N, action="pin", pinned_against="the shallows",
            hits=[{"part": "Neck", "severity": "firm", "with": "her forepaw, holding her head under the shallow water"},
                  {"part": "Upper Back", "severity": "crushing", "with": "her full weight"}],
            flavor="held face-down in the shallows, her head pushed under")],
         [A(N, action="pin", hits=[{"part": "Chest", "severity": "crushing", "with": "her forepaws"},
                                   {"part": "Left Thigh", "severity": "firm", "with": "her hind paw"}],
            flavor="pinned flat, forepaws planted on her chest")]]),
    (N, [[A(N, action="strike", move="Counter", part="Head", flavor="she sets herself and waits for it")]]),
    (R, [[A(R, action="strike", move="Brick Break", part="Muzzle", flavor="a chop at the Absol's face")]]),
    (R, [[A(R, action="hold_start", move="Tail Bind", hits=[{"part": "Left Upper Foreleg", "severity": "crushing", "with": "her twin tails, wound round it"}],
            flavor="her twin tails coil round the Absol's foreleg")],
         [A(R, action="strike", move="Crunch", part="Left Upper Foreleg", flavor="a crushing bite on the foreleg")]]),
    (R, [[A(R, action="strike", move="Crunch", part="Neck", flavor="a crushing bite at the neck while her tails hold")]]),
    (N, [[A(N, action="strike", move="Take Down", part="Chest", charge_into="a tall pine", flavor="a shoulder-first ram across the clearing")]]),
    (R, [[A(R, action="strike", move="Hydro Pump", hits=H("Head", "Chest", "Stomach"), sustain=3, flavor="Hydro Pump held into her")]]),
    (N, [[A(N, action="strike", move="Thunderbolt", flavor="the stored lightning let go through the soaked Buizel")]]),
    (N, [[A(N, action="strike", move="Sucker Punch", part="Stomach", feint=True, flavor="a feint high, the forepaw driven low")]]),
    (R, [[A(R, action="strike", move="Ice Beam", hits=H("Head", "Chest", "Left Shoulder"), sustain=2, flavor="Ice Beam held into her")]]),
    (N, [[A(N, action="strike", move="Iron Tail", part="Right Knee", launch="knocked down", flavor="the tail takes her other knee")]]),
    (N, [[A(N, action="strike", move="Bite", part="Stomach", count=4, flavor="bites on her where she lies")],
         [A(N, action="strike", move="Slash", part="Stomach", flavor="a rake across her stomach")]]),
    (N, [[A(N, action="pin", hits=[{"part": "Stomach", "severity": "crushing", "with": "her left forepaw"},
                                   {"part": "Left Thigh", "severity": "firm", "with": "her right hind paw"},
                                   {"part": "Chest", "severity": "firm", "with": "her chest and ruff"}],
            flavor="pinned flat, a forepaw ground into the ruined belly")]]),
]

# what each does when the planned one can't act
ANSWERS = {
    R: [[A(R, action="strike", move="Crunch", part="Right Upper Foreleg", flavor="a hard bite at the foreleg")],
        [A(R, action="strike", move="Water Pulse", hits=H("Head", "Neck", "Chest Ruff"), flavor="a ring of water into the face")],
        [A(R, action="strike", move="Swift", hits=H("Head", "Chest", "Right Shoulder"), flavor="a spray of stars")],
        [A(R, action="strike", move="Brick Break", part="Head", flavor="a chop at the head")]],
    N: [[A(N, action="strike", move="Psycho Cut", hits=H("Chest", "Left Shoulder", "Neck"), flavor="a blade of force from the horn")],
        [A(N, action="strike", move="Slash", part="Chest", flavor="a rake across the chest")],
        [A(N, action="strike", move="Night Slash", part="Right Thigh", flavor="a cut at the thigh")]],
}
FINISH = [
    [A(N, action="strike", move="Iron Tail", part="Stomach", launch="knocked down", flavor="the tail across her middle")],
    [A(N, action="strike", move="Night Slash", part="Stomach", count=4, flavor="cuts on her where she lies")],
    [A(N, action="pin", hits=[{"part": "Chest", "severity": "crushing", "with": "her forepaws"},
                              {"part": "Stomach", "severity": "firm", "with": "her hind paw"}], flavor="pinned flat again")],
]


def run(seed, verbose=False):
    s = session(seed, scene=SCENE, settings=SETTINGS)
    eng = s.eng
    log, caps, tags = [], [], []
    state = {"i": 0, "ans": {R: 0, N: 0}, "fin": 0}

    def play(acts, tag):
        out, cap = beat(s, acts, log, roll=False)
        caps.append((tag, cap))
        tags.append(tag)

    def try_all(options, tag):
        """True when the step itself happened; "setup" when only its set-up action did (the step waits)."""
        why = ""
        for acts in sorted(options, key=lambda o: isinstance(o, tuple)):     # the step itself first
            setup = isinstance(acts, tuple)
            if setup:
                acts = acts[1]
            try:
                play(acts, tag + (" setup" if setup else ""))
                return ("setup" if setup else True), ""
            except ValueError as e:
                why = str(e)
                if verbose:
                    print(f"[{tag}] refused: {e}")
        return False, why

    def answer(who, tag):
        k = state["ans"][who]
        opts = ANSWERS[who][k % len(ANSWERS[who]):] + ANSWERS[who][:k % len(ANSWERS[who])]
        ok, _ = try_all(opts, tag)
        if ok:
            state["ans"][who] += 1
        return ok

    beats = 0
    while beats < 75 and not s.over:
        beats += 1
        eng.roll_pin_windows()
        if eng.pin_on(R):
            play([A(N, action="breather", flavor="bears down and holds the pin")], "pin")
            continue
        if eng.pin_on(N):
            play([A(R, action="breather", flavor="holds her down")], "ripples' pin")
            continue
        if state["i"] < len(STEPS):
            who, options = STEPS[state["i"]]
            tag = f"step {state['i'] + 1}"
        else:
            who, options = N, [FINISH[state["fin"] % len(FINISH)]]
            tag = "finish"
        actor = eng.get(who)
        other = R if who == N else N
        if actor.energy < 25 and who not in eng.downed:
            # she has to catch her breath: every other time, the other one uses the beat if she can
            state["rests"] = state.get("rests", 0) + 1
            if not (state["rests"] % 2 == 1 and eng.get(other).energy >= 20 and other not in eng.downed
                    and answer(other, f"{other.lower()} presses")):
                play([A(who, action="breather", flavor=f"{who} catches her breath")], "breather")
            continue
        ok, why = try_all(options, tag)
        if ok == "setup":
            state["tries"] = state.get("tries", 0) + 1
            if state["tries"] >= 3:
                state["i"] += 1
                state["tries"] = 0
            continue
        if ok:
            state["tries"] = 0
            if tag == "finish":
                state["fin"] += 1
            else:
                state["i"] += 1
            continue
        if "no opening for a pin" in why or "no pin allowed yet" in why:
            # like the director: no opening this beat, so she keeps working on her and waits for one
            if not answer(who, f"{who.lower()} presses"):
                play([A(who, action="breather", flavor=f"{who} circles, waiting")], "breather")
            state["pinwait"] = state.get("pinwait", 0) + 1
            if state["pinwait"] >= 5:
                state["i"] += 1
                state["pinwait"] = 0
            continue
        # refused (flinched, down, in the air, a rule): the other one acts instead, and the step waits a beat
        if not (other not in eng.downed and answer(other, f"{other.lower()} presses")):
            play([A(who, action="breather", flavor=f"{who} gathers herself")], "breather")
        state["tries"] = state.get("tries", 0) + 1
        if tag != "finish" and state["tries"] >= 2:
            state["i"] += 1          # a step that can't happen now is skipped, not retried forever
            state["tries"] = 0
    return s, log, caps, tags


FEATURES = ("Feint", "JUGGLE", "knocked up into the air", "is behind", "Counter", "Mirror Coat", "**RAIN**",
            "**SUN**", "Pummel", "FRENZY", "DEVASTATING", "is guarding her", "blocks", "turns", "Recoil",
            "carries her on into", "PIN: Nocturne", "ESCAPES", "is sputtering", "is breathless", "is dazed",
            "is doubled_over", "off balance", "overcommits", "😤", "CLASH", "LAST STAND", "dragged", "shallows",
            "caught open", "Hold", "constricted", "wary")


def summary(s, log, tags):
    text = "\n".join(log)
    hit = [f for f in FEATURES if f in text]
    return {"winner": s.eng.winner(), "beats": len(tags), "ripples": round(s.eng.strength(s.eng.get(R))),
            "nocturne": round(s.eng.strength(s.eng.get(N))), "features": len(hit), "hit": hit,
            "missing": [f for f in FEATURES if f not in text]}


if __name__ == "__main__":
    if sys.argv[1] == "search":
        best = []
        for sd in range(int(sys.argv[2]), int(sys.argv[3])):
            try:
                s, log, caps, tags = run(sd)
            except Exception as e:
                print(sd, "ERROR", repr(e)[:200])
                continue
            sm = summary(s, log, tags)
            print(sd, sm["winner"], sm["beats"], "N", sm["nocturne"], "R", sm["ripples"], "features", sm["features"], flush=True)
    else:
        s, log, caps, tags = run(int(sys.argv[1]), verbose=True)
        sm = summary(s, log, tags)
        print({k: v for k, v in sm.items() if k != "hit"})
        print(tags)
