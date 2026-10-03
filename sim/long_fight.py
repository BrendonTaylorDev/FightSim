"""A longer fight: Nocturne vs the sleek Ripples in the sea cave. A scripted director (the choices) on the real engine
(every roll). Both fighters land real blows; Nocturne takes control in the second half.
Usage: python sim/long_fight.py SEED [prompts_folder]     python sim/long_fight.py search 1 200"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import session, beat

N, R = "Nocturne", "Ripples"
SETTINGS = ["/variant Ripples sleek", "/scale 5", "/resscale 0.75", "/healthloss 0.2", "/numb off"]


def A(att, **k):
    k["attacker"] = att
    k.setdefault("defender", R if att == N else N)
    return k


def H(*parts):
    return [{"part": p} for p in parts]


STAGES = [
    (N, [[A(N, action="strike", move="Night Slash", part="Left Shoulder", flavor="a long probing cut at the shoulder")]]),
    (R, [[A(R, action="strike", move="Water Gun", hits=H("Head", "Chest Ruff", "Neck"), flavor="a hard jet of water into the face")]]),
    (R, [[A(R, action="strike", move="Aqua Jet", part="Chest", charge_into="a stalagmite", flavor="Aqua Jet, straight into the Absol's chest")]]),
    (N, [[A(N, action="strike", move="Thunderbolt", flavor="the stored lightning let go through the Buizel")]]),
    (R, [[A(R, action="strike", move="Ice Fang", part="Left Upper Foreleg", flavor="a darting bite at the foreleg"),
          A(R, action="strike", move="Brick Break", part="Chest", flavor="a chop to the bruised chest"),
          A(R, action="strike", move="Crunch", part="Neck", flavor="jaws at the side of the neck")]]),
    (N, [[A(N, action="strike", move="Sucker Punch", part="Stomach", flavor="a feint, then a forepaw driven into the belly"),
          A(N, action="strike", move="Night Slash", part="Left Thigh", flavor="the horn raked across the thigh"),
          A(N, action="strike", move="Iron Tail", part="Upper Back", flavor="the sickle tail brought down across her back")]]),
    (N, [[A(N, action="grapple", part="Right Upper Arm", hits=[{"part": "Right Upper Arm", "with": "her jaws", "severity": "light"}],
            flavor="jaws clamp on her right arm and drag her in"),
          A(N, action="strike", move="Slash", part="Stomach", count=4, flavor="short raking blows, no room to wind up")]]),
    (N, [[A(N, action="strike", move="Hydro Pump", hits=H("Stomach", "Chest", "Left Hip"), sustain=4,
            flavor="Hydro Pump held point-blank while the jaws keep her there")],
         [A(N, action="grapple", part="Left Upper Arm", hits=[{"part": "Left Upper Arm", "with": "her forepaw", "severity": "light"}],
            flavor="a forepaw hooks her arm and hauls her back in"),
          A(N, action="strike", move="Hydro Pump", hits=H("Stomach", "Chest", "Left Hip"), sustain=4, flavor="Hydro Pump held point-blank")]]),
    (R, [[A(R, action="strike", move="Brick Break", part="Muzzle", flavor="a desperate chop at the Absol's face")]]),
    (N, [[A(N, action="strike", move="Iron Tail", part="Left Knee", launch="knocked down", flavor="the tail sweeps the knee out from under her")]]),
    (N, [[A(N, action="strike", move="Bite", part="Stomach", count=3, flavor="standing over her, biting down again and again")]]),
    (N, [[A(N, action="pin", hits=[{"part": "Chest", "severity": "crushing", "with": "her forepaws"},
                                   {"part": "Left Thigh", "severity": "firm", "with": "her hind paw"},
                                   {"part": "Right Upper Arm", "severity": "firm", "with": "her jaws"}],
            flavor="pinned flat on her back, forepaws planted on her chest")]]),
    (R, [[A(R, action="strike", move="Ice Beam", hits=H("Head", "Chest", "Neck"), sustain=3,
            flavor="Ice Beam held into the Absol's face and chest")]]),
    (N, [[A(N, action="strike", move="Take Down", part="Chest", charge_into="a fallen boulder", flavor="a shoulder-first ram across the ledge")]]),
    (R, [[A(R, action="strike", move="Aqua Jet", part="Belly", charge_into="the cave wall", flavor="a second Aqua Jet, low, into the belly")],
         [A(R, action="strike", move="Swift", hits=H("Head", "Chest", "Belly"), flavor="a spray of stars")]]),
    (N, [[A(N, action="strike", move="Dark Pulse", hits=H("Head", "Chest", "Stomach"), flavor="a ring of dark force")]]),
    (N, [[A(N, action="grapple", part="Left Upper Arm", hits=[{"part": "Left Upper Arm", "with": "her jaws", "severity": "light"}],
            flavor="the jaws find her arm again"),
          A(N, action="strike", move="Night Slash", part="Chest", count=3, flavor="short cuts at no distance")]]),
    (N, [[A(N, action="strike", move="Iron Tail", part="Right Knee", launch="knocked down", flavor="the tail takes her other knee")]]),
    (N, [[A(N, action="pin", hits=[{"part": "Stomach", "severity": "crushing", "with": "her left forepaw"},
                                   {"part": "Left Thigh", "severity": "firm", "with": "her right hind paw"},
                                   {"part": "Chest", "severity": "firm", "with": "her chest and ruff"}],
            flavor="pinned flat, a forepaw ground into the ruined belly")]]),
]


# what the other one does while the planned attacker catches her breath (in turn)
ANSWERS = {
    R: [[A(R, action="strike", move="Crunch", part="Right Upper Foreleg", flavor="a hard bite at the foreleg")],
        [A(R, action="strike", move="Water Pulse", hits=H("Head", "Neck", "Chest Ruff"), flavor="a ring of water into the face")],
        [A(R, action="strike", move="Ice Fang", part="Right Flank", flavor="a darting, freezing bite to the side")],
        [A(R, action="strike", move="Swift", hits=H("Head", "Chest", "Right Shoulder"), flavor="a spray of stars")],
        [A(R, action="strike", move="improvised", improvised_name="tail lash", improvised_type="Normal", severity="solid",
           part="Head", flavor="both tails whipped across the face")]],
    N: [[A(N, action="strike", move="Psycho Cut", hits=H("Chest", "Left Shoulder", "Neck"), flavor="a blade of force from the horn")],
        [A(N, action="strike", move="Sucker Punch", part="Head", flavor="a quick forepaw to the head")],
        [A(N, action="strike", move="Bite", part="Right Thigh", flavor="a snap at the thigh")]],
}


def run(seed, verbose=False):
    answers = {R: 0, N: 0}
    rests = [0]
    s = session(seed, settings=SETTINGS)
    eng = s.eng
    log, caps, tags = [], [], []
    pins_started, i, beats, pin_pummel = 0, 0, 0, False

    def play(acts, tag):
        out, cap = beat(s, acts, log)
        caps.append((tag, cap))
        tags.append(tag)

    while beats < 40 and not s.over:
        beats += 1
        n, r = eng.get(N), eng.get(R)
        if eng.pin_on(R):
            if False and pins_started >= 2 and not pin_pummel:     # pummels inside a pin are off by default (build 113)
                pin_pummel = True
                try:
                    play([A(N, action="strike", move="Night Slash", part="Stomach", count=3,
                            flavor="from on top, short blows rained down")], "pin pummel")
                    continue
                except ValueError:
                    pass
            play([A(N, action="breather", flavor="bears down and holds the pin")], "pin")
            continue
        if eng.pin_on(N):
            play([A(R, action="breather", flavor="holds her down")], "ripples' pin")
            continue
        if i >= len(STAGES):
            # past the plan: put her down and pin again
            stage = STAGES[-2] if R not in eng.downed else STAGES[-1]
        else:
            stage = STAGES[i]
        who, options = stage
        actor = eng.get(who)
        if who in eng.downed or actor.energy < 30:
            # she has to catch her breath (or get up): the other one gets the beat, if she has anything to do it with
            other = R if who == N else N
            o = eng.get(other)
            rests[0] += 1
            if rests[0] % 2 == 1 and other not in eng.downed and o.energy >= 20 and not eng.pinned_by(other):
                for acts in ANSWERS[other][answers[other] % len(ANSWERS[other]):] + ANSWERS[other]:
                    try:
                        play(acts, f"{other.lower()} presses")
                        answers[other] += 1
                        break
                    except ValueError:
                        continue
                else:
                    play([A(who, action="breather", flavor=f"{who} gathers herself")], "breather")
                continue
            play([A(who, action="breather", flavor=f"{who} gathers herself")], "breather")
            continue
        ok, why = False, ""
        for acts in options:
            try:
                play(acts, f"stage {i + 1}")
                ok = True
                break
            except ValueError as e:
                why = str(e)
                if verbose:
                    print(f"[stage {i + 1}] refused: {e}")
        if not ok and "FLINCHED" in why:
            # she can't attack this beat: she shakes it off, and tries the same thing next beat
            play([A(who, action="breather", flavor=f"{who} shakes it off")], "breather")
            continue
        if ok and acts[-1].get("action") == "pin":
            pins_started += 1
        i += 1
        if not ok:
            beats -= 1
            fails = locals().get("fails", 0) + 1
            if i > len(STAGES) + 8:
                break
    return s, log, caps, tags


def dump_prompts(caps, folder):
    os.makedirs(folder, exist_ok=True)
    for n, (tag, cap) in enumerate(caps, 1):
        user = [m["content"] for msgs in cap[:1] for m in msgs if m["role"] == "user"]
        with open(os.path.join(folder, f"beat{n:02d}_{tag.replace(' ', '_')}.txt"), "w") as fh:
            fh.write("\n\n=====\n\n".join(user))


def summary(s, log, tags):
    text = "\n".join(log)
    cause = re.search(r"It was the (\w+)", text)
    return {"winner": s.eng.winner(), "beats": len(tags), "cause": cause.group(1) if cause else None,
            "escapes": len(re.findall(r"breaks free of Nocturne's pin", text)),
            "nocturne": round(s.eng.strength(s.eng.get(N))), "pin_pummel": "pin pummel" in tags}


if __name__ == "__main__":
    if sys.argv[1] == "search":
        for seed in range(int(sys.argv[2]), int(sys.argv[3])):
            s, log, caps, tags = run(seed)
            print(seed, summary(s, log, tags), flush=True)
    else:
        seed = int(sys.argv[1])
        s, log, caps, tags = run(seed, verbose=True)
        print("\n".join(log))
        print(summary(s, log, tags), tags)
        if len(sys.argv) > 2:
            dump_prompts(caps, os.path.join(os.path.dirname(os.path.abspath(__file__)), sys.argv[2]))
