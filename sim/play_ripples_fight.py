"""Play-as test: the user's seat is Ripples (/play Ripples, /play dice fair) against Nocturne in the lakeside clearing.
Every beat goes through the real play-as path: the panel and its openings, the "Ripples > " order, Session.play_turn,
the director's PLAYERS block and apply_players. Claude plays Ripples (orders written in plain words, the way a player
types them, with the action the director should turn each into). The director's own choices for Nocturne come from
the /simulate stand-in (simulate._pick_action), standing in for the local director model.
Usage: python sim/play_ripples_fight.py SEED [beats]"""
import sys, os, json, random, io, contextlib, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import session
import director as D
import simulate
import llm

N, R = "Nocturne", "Ripples"
SETTINGS = ["/variant Ripples sleek", "/scale 5", "/resscale 0.75", "/healthloss 0.2", "/numb off",
            '/learn Nocturne "Sunny Day"', '/learn Nocturne "Counter"', '/learn Ripples "Rain Dance"',
            '/learn Ripples "Protect"', '/learn Ripples "Mirror Coat"']
SCENE = "lakeside forest"

STATE = {"plan": None, "eng": None, "rng": None, "director_prompts": [], "refusals": []}


def fake_chat(model, messages, **kw):
    if not kw.get("fmt"):
        return harness.fake_chat(model, messages, **kw)
    # the director: the player's order turned into Ripples' action(s), then Nocturne's answer
    eng, plan = STATE["eng"], STATE["plan"]
    STATE["director_prompts"].append(messages[-1]["content"] if len(messages) > 2 else messages[1]["content"])
    retry = len(messages) > 2
    acts = [dict(a) for a in plan["acts"]]
    if not retry:
        n_act = simulate._pick_action(eng, STATE["rng"], eng.get(N), eng.get(R))
        n_act.pop("_sim", None)
        if eng.pinning(R) and n_act.get("action") == "breather":
            n_act = {"action": "struggle", "attacker": N, "defender": "", "flavor": "tries to throw her off"}
        STATE["n_act"] = n_act
        acts.append(n_act)
    else:
        STATE["refusals"].append(messages[-1]["content"][:200])
    return json.dumps({"actions": acts, "positions": "same"})


for mod in (llm, D.llm, harness._n.llm):
    mod.chat = fake_chat


def A(**k):
    k.setdefault("attacker", R)
    k.setdefault("flavor", "")
    return k


def strength(eng, n):
    return eng.strength(eng.get(n))


def choose(eng, s, rng, st):
    """Ripples' move this beat: (order text, [actions], fallback options). Played to win."""
    me, foe = eng.get(R), eng.get(N)
    my, her = strength(eng, R), strength(eng, N)
    opts = []
    if any(eng.has(me, k) for k in ("asleep", "frozen", "flinched")):
        return [("wait", [])]       # the panel says she can't act this beat
    if eng.pinned_by(R):
        if rng.random() < 0.8 or my < 30:
            opts.append(("I fight to get out from under her", [A(action="struggle", defender="", flavor="fights to throw her off")]))
        opts.append(("I bite whatever of her I can reach", [A(action="strike", defender=N, move="Crunch", part="Right Upper Foreleg",
                                                              flavor="a bite at the foreleg holding her down")]))
        return opts
    if eng.pinning(R):
        if rng.random() < 0.25 and me.energy > 25:
            opts.append(("keep her down and hit her throat while she's under me",
                         [A(action="strike", defender=N, move="Brick Break", part="Throat", flavor="a chop to the throat as she holds her")]))
        opts.append(("hold her down, all my weight on her", [A(action="breather", defender=N, flavor="bears down and holds the pin")]))
        return opts
    held = [h for h in eng.holds.values() if h.sub and h.attacker == R]
    if held:
        if eng.sub_stuck(foe, held):
            shapes = D.pin_shapes(eng, me, foe)
            if shapes and eng.pin_allowed(N)[0]:
                k = sorted(shapes)[rng.randrange(len(shapes))]
                look, contacts = shapes[k]
                opts.append((f"let the hold go and pin her ({look.split(';')[0]})",
                             [A(action="pin", defender=N, flavor=look[:80], hits=[{"part": p, "severity": v, "with": w}
                              for (p, w), v in zip(contacts, ["crushing"] + ["firm"] * (len(contacts) - 1))])]))
        if rng.random() < 0.4:
            opts.append(("water gun into the back of her head while I hold her",
                         [A(action="strike", defender=N, move="Water Gun", hits=[{"part": "Head"}, {"part": "Neck"}],
                            flavor="a jet of water into the back of her head")]))
        opts.append(("crank it harder", [A(action="breather", defender=N, flavor=f"cranks the {held[0].sub} harder")]))
        return opts
    if me.energy < 18:
        return [("back off and get my breath back", [A(action="breather", defender=N, flavor="backs off and breathes")])]
    if (getattr(eng, "sub_window", None) or {}).get(N) and R not in eng.downed:
        shapes = eng.submission_shapes(R, N)
        if shapes:
            k = sorted(shapes)[rng.randrange(len(shapes))]
            opts.append((f"lock her in a {k.replace('_', ' ')}", [A(action="submission", defender=N, improvised_name=k,
                                                                     flavor=shapes[k]["look"][:120])]))
    ok, _ = eng.pin_allowed(N)
    if ok and R not in eng.downed and not eng.has(me, "reeling") and (N in eng.downed or her < 70 or rng.random() < 0.5):
        shapes = D.pin_shapes(eng, me, foe)
        if shapes:
            throat = [k for k in shapes if "throat" in k or "neck" in k or k in ("throttle", "headlock_pin", "sleeper")]
            k = rng.choice(sorted(throat)) if throat and her < 55 else sorted(shapes)[rng.randrange(len(shapes))]
            look, contacts = shapes[k]
            opts.append((f"pin her: {look.split(';')[0]}",
                         [A(action="pin", defender=N, flavor=look[:80], hits=[{"part": p, "severity": v, "with": w}
                          for (p, w), v in zip(contacts, ["crushing"] + ["firm"] * (len(contacts) - 1))])]))
    if not st["rain"]:
        st["rain"] = True
        opts.append(("call the rain in off the lake first", [A(action="strike", defender=N, move="Rain Dance", part="Head",
                                                                 flavor="clouds dragged in off the lake")]))
    k = st["k"]
    st["k"] += 1
    down = R in eng.downed
    plan = [
        ("Brick Break, chop her across the neck", A(action="strike", defender=N, move="Brick Break", part="Neck", flavor="a chop across the neck")),
        ("Water Pulse into her face", A(action="strike", defender=N, move="Water Pulse", hits=[{"part": "Muzzle"}, {"part": "Throat"}, {"part": "Neck"}],
                                        flavor="a ring of water into her face")),
        ("Aqua Jet into her chest and drive her back", A(action="strike", defender=N, move="Aqua Jet", part="Chest",
                                                         flavor="a streak of water across the grass")),
        ("Ice Fang on her foreleg", A(action="strike", defender=N, move="Ice Fang", part="Right Upper Foreleg", flavor="a freezing bite")),
        ("Brick Break low, take her hind leg out", A(action="strike", defender=N, move="Brick Break", part="Left Hock", launch="knocked down",
                                                     flavor="a low chop at the hock")),
        ("Crunch her throat", A(action="strike", defender=N, move="Crunch", part="Throat", flavor="a lunge for the throat")),
        ("Hydro Pump, all of it, at her head and neck", A(action="strike", defender=N, move="Hydro Pump",
                                                          hits=[{"part": "Head"}, {"part": "Neck"}, {"part": "Throat"}], flavor="Hydro Pump at point-blank")),
    ]
    if down:
        plan = [p for p in plan if p[1]["move"] in ("Water Pulse", "Hydro Pump", "Crunch", "Ice Fang")]
    if her < 45:
        plan = [p for p in plan if p[1]["move"] in ("Brick Break", "Crunch", "Hydro Pump", "Water Pulse")] or plan
    if me.move_uses.get("Hydro Pump", 1) <= 0:
        plan = [p for p in plan if p[1]["move"] != "Hydro Pump"]
    if st["last_protect"] < eng.turn - 6 and my < 60 and rng.random() < 0.25:
        st["last_protect"] = eng.turn
        opts.append(("throw up Protect", [A(action="strike", defender=N, move="Protect", part="Head", flavor="a shimmering shell")]))
    for i in range(len(plan)):
        text, act = plan[(k + i) % len(plan)]
        mv = next((m for m in me.moves if m["name"] == act.get("move")), None)
        if mv and eng.energy_cost(mv) > me.energy:
            continue        # the panel marks it "too tired"
        opts.append((text, [act]))
    return opts


def run(seed, verbose=False, max_beats=90):
    with contextlib.redirect_stdout(io.StringIO()):
        s = session(seed, scene=SCENE, settings=SETTINGS)
        import play
        play.handle_command(s, "/play Ripples")
        play.handle_command(s, "/play dice fair")
    eng = s.eng
    STATE.update(eng=eng, rng=random.Random(seed * 7919 + 1), director_prompts=[], refusals=[])
    rng = random.Random(seed * 37 + 11)
    st = {"rain": False, "k": 0, "last_protect": -99}
    log, caps, tags = [], [], []
    s.story = ["(opening)"]
    while len(log) < max_beats and not s.over:
        harness.CAPTURE.clear()
        buf = io.StringIO()
        done = False
        with contextlib.redirect_stdout(buf):
            s.play_panel(R, first=True)
            for text, acts in choose(eng, s, rng, st):
                STATE["plan"] = {"text": text, "acts": acts}
                print(f"Ripples > {text}")
                try:
                    s.play_turn(R, "wait" if text == "wait" else text)
                    done = True
                    break
                except ValueError as e:
                    print(f"Error: {e}  (type /help)")
            if not done:
                print("Ripples > wait")
                STATE["plan"] = {"text": "wait", "acts": []}
                s.play_turn(R, "wait")
        out = buf.getvalue()
        log.append(out)
        caps.append(("beat", list(harness.CAPTURE)))
        tags.append(STATE["plan"]["text"][:40])
        if verbose:
            errs = re.findall(r"Error: (.*)", out)
            print(f"{len(log):3d} R {strength(eng, R):5.1f}% N {strength(eng, N):5.1f}% | {STATE['plan']['text'][:55]:55s} | N: "
                  f"{(STATE.get('n_act') or {}).get('action')} {(STATE.get('n_act') or {}).get('move', '')}"
                  + (f" | pins {list(eng.pins)}" if eng.pins else "") + (f" | ERR {errs}" if errs else ""))
    return s, log, caps, tags


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    s, log, caps, tags = run(seed, verbose=True, max_beats=int(sys.argv[2]) if len(sys.argv) > 2 else 90)
    print("winner:", s.eng.winner(), "beats:", len(log), "refusals:", len(STATE["refusals"]))
