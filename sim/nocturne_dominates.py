"""Nocturne dominates Ripples: a scripted director (the choices) on the real engine (every roll).
Usage: python sim/nocturne_dominates.py [seed]   (no seed: search for a run that ends in a pain pass-out)"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE_SIM = os.path.dirname(os.path.abspath(__file__))
from harness import session, beat, CAPTURE

N, R = "Nocturne", "Ripples"
SETTINGS = ["/variant Ripples sleek", "/scale 5", "/resscale 0.75", "/healthloss 0.2", "/numb off", "/plan dominate Nocturne"]


def A(**k):
    k.setdefault("attacker", N)
    k.setdefault("defender", R if k["attacker"] == N else N)
    return k


def stages():
    """(name, [action lists to try in order])"""
    return [
        ("chain", [[A(action="strike", move="Sucker Punch", part="Stomach", flavor="a feint, then a forepaw driven into the belly"),
                    A(action="strike", move="Night Slash", part="Left Thigh", flavor="the horn raked across the thigh on the way past"),
                    A(action="strike", move="Iron Tail", part="Upper Back", flavor="the sickle tail brought down across her back")]]),
        ("aqua jet", [[A(attacker=R, action="strike", move="Aqua Jet", part="Chest", charge_into="a stalagmite",
                         flavor="Aqua Jet, straight into the Absol's chest")]]),
        ("grapple + pummel", [[A(action="grapple", part="Right Upper Arm", hits=[{"part": "Right Upper Arm", "with": "her jaws", "severity": "light"}],
                                 flavor="jaws clamp on her right arm and drag her in"),
                               A(action="strike", move="Slash", part="Stomach", count=4, flavor="short raking blows into the belly, no room to wind up")]]),
        ("point-blank stream", [[A(action="strike", move="Hydro Pump", hits=[{"part": "Stomach"}, {"part": "Chest"}, {"part": "Left Hip"}],
                                   sustain=4, flavor="Hydro Pump held point-blank into her belly while the jaws keep her there")],
                                [A(action="grapple", part="Left Upper Arm", hits=[{"part": "Left Upper Arm", "with": "her forepaw", "severity": "light"}],
                                   flavor="a forepaw hooks her arm and hauls her back in"),
                                 A(action="strike", move="Hydro Pump", hits=[{"part": "Stomach"}, {"part": "Chest"}, {"part": "Left Hip"}],
                                   sustain=4, flavor="Hydro Pump held point-blank into her belly")]]),
        ("ripples fights back", [[A(attacker=R, action="strike", move="Brick Break", part="Muzzle", flavor="a desperate chop at the Absol's face")]]),
        ("knockdown", [[A(action="strike", move="Iron Tail", part="Left Knee", launch="knocked down",
                          flavor="the tail sweeps the left knee out from under her")]]),
        ("ground pummel", [[A(action="strike", move="Bite", part="Stomach", count=3, flavor="standing over her, biting down into the belly again and again")]]),
        ("pin", [[A(action="pin", hits=[{"part": "Stomach", "severity": "crushing", "with": "her left forepaw"},
                                        {"part": "Left Thigh", "severity": "firm", "with": "her right hind paw"},
                                        {"part": "Chest", "severity": "firm", "with": "her chest and ruff"}],
                    flavor="pinned flat, a forepaw ground into the ruined belly")]]),
    ]


def run(seed, verbose=False):
    s = session(seed, settings=SETTINGS)
    eng = s.eng
    log, done, beats, caps = [], [], 0, []
    plan = stages()
    i = 0
    while beats < 24 and not s.over:
        noc = eng.get(N)
        if (N in eng.downed or noc.energy < 30) and not eng.pin_on(R) and not eng.pinning(N):
            acts, tag = [A(action="breather", flavor="Nocturne gathers herself, eyes never leaving the Buizel")], "breather"
        elif eng.pin_on(R):
            # the pin runs: now and then Nocturne rains blows from on top
            acts = ([A(action="strike", move="Night Slash", part="Stomach", count=3, flavor="from on top, short blows into the belly")]
                    if "pin pummel" not in done else
                    [A(action="breather", flavor="bears down and holds")])
            tag = "pin pummel" if "pin pummel" not in done else "pin"
        elif i < len(plan):
            tag, options = plan[i]
            acts = None
        else:
            # after the plan: get her down and pin again
            tag = "re-pin" if R in eng.downed else "re-knockdown"
            acts = (plan[-1][1][0] if R in eng.downed else plan[5][1][0])
        tried = [acts] if acts else options
        if tag == "breather":
            out, cap = beat(s, acts, log); caps.append((tag, cap)); beats += 1; done.append(tag); continue
        ok = False
        for a in tried:
            try:
                out, cap = beat(s, a, log)
            except ValueError as e:
                if verbose:
                    print(f"[{tag}] refused: {e}")
                continue
            ok = True
            caps.append((tag, cap))
            break
        if not ok:
            if tag == "pin" and R not in eng.downed:
                i = 5          # knock her down first
                continue
            # fall back to a plain strike so the fight moves on
            try:
                out, cap = beat(s, [A(action="strike", move="Dark Pulse", hits=[{"part": "Stomach"}, {"part": "Head"}, {"part": "Neck"}],
                                      flavor="a pulse of dark force")], log)
                caps.append(("fallback", cap))
            except ValueError:
                return None
            tag = "fallback"
        beats += 1
        done.append(tag)
        if acts is None:
            i += 1
    winner = eng.winner()
    cause = None
    for t in log:
        m = re.search(r"goes out from (?:the )?(\w+)|passes out from (\w+)|out cause: (\w+)", t)
    for ev in getattr(eng, "last_out", []) or []:
        pass
    return s, log, done, caps


def dump_prompts(caps, folder):
    os.makedirs(folder, exist_ok=True)
    for n, (tag, cap) in enumerate(caps, 1):
        user = [m["content"] for msgs in cap[:1] for m in msgs if m["role"] == "user"]
        with open(os.path.join(folder, f"beat{n:02d}_{tag.replace(' ', '_').replace('+', '')}.txt"), "w") as fh:
            fh.write("\n\n=====\n\n".join(user))


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    s, log, done, caps = run(seed, verbose=True)
    print("\n\n".join(log))
    print(done, "winner:", s.eng.winner())
    if len(sys.argv) > 2:
        dump_prompts(caps, os.path.join(os.path.dirname(os.path.abspath(__file__)), sys.argv[2]))
