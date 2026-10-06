"""Regression suite: every kind of attack and combination played through the real game (engine, director rules,
display and narrator checks), with a stand-in for the model. Run it before every push:

    python sim/regress.py            # everything, a few seeds each (about a minute)
    python sim/regress.py pummel     # only the cases whose name has "pummel" in it
    python sim/regress.py -v         # say what each case did

Each case plays a few scripted beats over several seeds. A case passes when, on every seed:
  - no beat raises an error (a beat refused by the rules counts only where the case says it must be allowed),
  - the state check (engine.check_state) finds nothing wrong after any beat,
  - the narrator was asked to write every beat,
  - the fight saves and loads back to the same state, and a save from an older build (newer fields stripped) loads
    and plays on;
and, on at least one seed, what the case is for actually happened (a pummel ran, a carry lifted her, a pin
started...). Exit code 0 when everything passed."""
import contextlib, io, json, os, sys, tempfile, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H          # (works in a throwaway copy of the game: your settings and saves are never touched)
from engine import Engine


def _quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


SEEDS = (1, 2, 3, 4)


def A(att, dfn, action, **kw):
    return dict({"attacker": att, "defender": dfn, "action": action, "flavor": kw.pop("flavor", "")}, **kw)


def _results(s):
    """What the last beat did, as the narrator was given it."""
    ln = s.last_narration or {}
    args = ln.get("args") or ()
    b = args[0] if args else {}
    return list(b.get("actions") or []), list(b.get("also_this_beat") or [])


def _any(rs, test):
    return any(isinstance(r, dict) and test(r) for r in rs)


# ---------- the cases ----------
# each: name, fighters, setup(s) or None, beats: a list of (actions or a function of the session giving them),
# saw(results, also, s) -> True when what the case is for happened in that beat

def _down(name, facing="face-up"):
    def go(s):
        s.eng.knock_down(name, facing=facing)
        s.eng._fresh_down.discard(name)
    return go


def _airborne(name, beats=3):
    def go(s):
        s.eng.set_status(s.eng.get(name), "airborne", beats)
    return go


def _no_guard(s):
    s.eng.rules["moves"].setdefault("guard", {})["enabled"] = False


def _all(*fns):
    def go(s):
        for f in fns:
            f(s)
    return go


def _open_pins(s):
    s.eng.roll_pin_windows(open_all=True)


CASES = [
    ("named strike", "Nocturne,Ripples", None,
     [[A("Nocturne", "Ripples", "strike", move="Night Slash", part="Left Shoulder")]],
     lambda r, e, s: _any(r, lambda x: x.get("hits"))),
    ("plain blow (no move)", "Nocturne,Ripples", None,
     [[A("Nocturne", "Ripples", "strike", move="none", part="Right Ribs", flavor="a hard shoulder into her ribs")]],
     lambda r, e, s: _any(r, lambda x: (x.get("move") or {}).get("improvised"))),
    ("improvised move", "Nocturne,Ripples", None,
     [[A("Nocturne", "Ripples", "strike", move="improvised", improvised_name="Headbutt", improvised_type="Normal",
         severity="heavy", part="Muzzle")]],
     lambda r, e, s: _any(r, lambda x: x.get("type") == "instant")),
    ("feint", "Nocturne,Ripples", None,
     [[A("Nocturne", "Ripples", "strike", move="Slash", part="Neck", feint=True)]],
     lambda r, e, s: _any(r, lambda x: x.get("feint"))),
    ("spread move", "Ripples,Nocturne", None,
     [[A("Ripples", "Nocturne", "combo", move="Swift", hits=[{"part": "Chest"}, {"part": "Left Flank"}, {"part": "Head"}])]],
     lambda r, e, s: _any(r, lambda x: len(x.get("hits") or []) > 1)),
    ("whole-body move", "Nocturne,Ripples", None,
     [[A("Nocturne", "Ripples", "strike", move="Thunderbolt", part="Chest")]],
     lambda r, e, s: _any(r, lambda x: len(x.get("hits") or []) > 3)),
    ("knocked down by a blow", "Nocturne,Ripples", None,
     [[A("Nocturne", "Ripples", "strike", move="Iron Tail", part="Head", launch="knocked down")]],
     lambda r, e, s: _any(r, lambda x: x.get("launch") == "knocked down")),    # (strong fighters may spring up)
    ("chain of three", "Nocturne,Ripples", _no_guard,
     [[A("Nocturne", "Ripples", "strike", move="Slash", part="Left Shoulder"),
       A("Nocturne", "Ripples", "strike", move="Bite", part="Left Upper Arm"),
       A("Nocturne", "Ripples", "strike", move="Night Slash", part="Chest")]],
     lambda r, e, s: _any(r, lambda x: (x.get("chain") or {}).get("link", 1) >= 2)),
    ("pummel on a downed fighter", "Nocturne,Ripples", _all(_no_guard, _down("Ripples")),
     [[A("Nocturne", "Ripples", "strike", move="Bite", part="Chest", count=3)]],
     lambda r, e, s: _any(r, lambda x: x.get("pummel"))),
    ("grapple then pummel", "Nocturne,Ripples", _no_guard,
     [[A("Nocturne", "Ripples", "grapple", part="Left Upper Arm", hits=[{"with": "her jaws"}]),
       A("Nocturne", "Ripples", "strike", move="Slash", part="Chest", count=3)],
      [A("Nocturne", "Ripples", "strike", move="Night Slash", part="Neck", count=2)]],
     lambda r, e, s: _any(r, lambda x: x.get("pummel") or x.get("type") == "grapple_start")),
    ("held stream", "Ripples,Nocturne", None,
     [[A("Ripples", "Nocturne", "combo", move="Hydro Pump", sustain=3, hits=[{"part": "Chest"}, {"part": "Head"}])]],
     lambda r, e, s: _any(r, lambda x: x.get("sustain"))),
    ("stream pinned against the scenery", "Ripples,Nocturne", None,
     [[A("Ripples", "Nocturne", "combo", move="Water Pulse", sustain=3, pinned_against="the cave wall",
         hits=[{"part": "Chest"}, {"part": "Belly"}])]],
     lambda r, e, s: _any(r, lambda x: (x.get("sustain") or {}).get("against"))),
    ("charge into the scenery", "Ripples,Nocturne", None,
     [[A("Ripples", "Nocturne", "strike", move="Aqua Jet", part="Chest", charge_into="a stalagmite")],
      [A("Ripples", "Nocturne", "strike", move="Crunch", part="Neck", count=3)]],
     lambda r, e, s: _any(r, lambda x: x.get("charge") and not x["charge"].get("skipped"))),
    ("throw", "Nocturne,Ripples", None,
     [[A("Nocturne", "Ripples", "throw", landing=[{"surface": "a fallen boulder", "parts": ["Upper Back", "Head"],
                                                  "severity": "heavy"}])]],
     lambda r, e, s: _any(r, lambda x: x.get("environment") or x.get("manhandle"))),
    ("slam", "Nocturne,Ripples", _down("Ripples"),
     [[A("Nocturne", "Ripples", "slam", landing=[{"surface": "the cave floor", "parts": ["Upper Back"],
                                                 "severity": "heavy"}])]],
     lambda r, e, s: _any(r, lambda x: x.get("environment") or x.get("manhandle"))),
    ("drag", "Nocturne,Ripples", _down("Ripples"),
     [[A("Nocturne", "Ripples", "drag", landing=[{"surface": "the cave wall", "parts": ["Left Hip", "Left Shoulder"],
                                                 "severity": "moderate"}])]],
     lambda r, e, s: _any(r, lambda x: x.get("environment") or x.get("manhandle"))),
    ("hold, tighten, release", "Ripples,Nocturne", None,
     [[A("Ripples", "Nocturne", "hold_start", move="Tail Bind", part="Left Upper Foreleg",
         hits=[{"part": "Left Upper Foreleg", "with": "her twin tails"}])],
      [A("Ripples", "Nocturne", "breather")],
      [A("Ripples", "Nocturne", "hold_release")]],
     lambda r, e, s: _any(r, lambda x: x.get("type") == "hold_start")),
    ("pin and struggle", "Nocturne,Ripples", _all(_down("Ripples"), _open_pins),
     [[A("Nocturne", "Ripples", "pin", hits=[{"part": "Chest", "severity": "crushing", "with": "her forepaws"},
                                             {"part": "Left Upper Arm", "severity": "firm", "with": "a hind paw"},
                                             {"part": "Right Upper Arm", "severity": "firm", "with": "her weight"}])],
      [A("Ripples", "Nocturne", "struggle")],
      [A("Ripples", "Nocturne", "struggle")],
      [A("Ripples", "Nocturne", "struggle")]],
     lambda r, e, s: _any(r, lambda x: x.get("type") == "pin_start")),
    ("submission", "Nocturne,Ripples", _all(_down("Ripples"), lambda s: s.eng.roll_sub_windows(open_all=True)),
     [[A("Nocturne", "Ripples", "submission", improvised_name="limb wrench")],
      [A("Nocturne", "Ripples", "breather")],
      [A("Nocturne", "Ripples", "breather")],
      [A("Nocturne", "Ripples", "breather")]],
     lambda r, e, s: _any(r, lambda x: x.get("submission"))),
    ("take off and dive", "Talon,Ripples", _no_guard,
     [[A("Talon", "Ripples", "breather", reposition="take off")],
      [A("Talon", "Ripples", "strike", move="Aerial Ace", part="Head")],
      [A("Ripples", "Talon", "combo", move="Ice Beam", hits=[{"part": "Left Wing"}, {"part": "Chest"}])]],
     lambda r, e, s: _any(r, lambda x: x.get("type") == "take_off" or x.get("dive"))),
    ("carry, fall and spike", "Talon,Ripples", _all(_no_guard, _airborne("Talon")),
     [[A("Talon", "Ripples", "strike", move="Aerial Ace", part="Head", carry=True, flavor="talons first"),
       A("Talon", "Ripples", "strike", move="Wing Attack", part="Chest", flavor="a slash as she falls"),
       A("Talon", "Ripples", "strike", move="Brave Bird", part="Upper Back", flavor="straight down")]],
     lambda r, e, s: _any(r, lambda x: x.get("carried"))),
    ("flyer hit out of the air", "Cinder,Talon", _airborne("Talon"),
     [[A("Cinder", "Talon", "combo", move="Flamethrower", hits=[{"part": "Left Wing"}, {"part": "Chest"}],
         launch="knocked down")]],
     lambda r, e, s: _any(r, lambda x: x.get("hits"))),
    ("knocked flat with wear (collapse, knockout paths)", "Nocturne,Ripples",
     lambda s: [setattr(s.eng.get("Ripples"), "health", s.eng.get("Ripples").max_health * 0.04), _no_guard(s)],
     [[A("Nocturne", "Ripples", "strike", move="Iron Tail", part="Head", launch="knocked down")],
      [A("Nocturne", "Ripples", "strike", move="Bite", part="Throat", count=4)],
      [A("Nocturne", "Ripples", "breather")]],
     lambda r, e, s: True),
    ("/encourage, then the director's rules", "Nocturne,Ripples",
     lambda s: H.play.handle_command(s, "/encourage pummel 3 Nocturne Ripples 2"),
     [[A("Nocturne", "Ripples", "strike", move="Slash", part="Chest")]],
     lambda r, e, s: True),
]


# ---------- checks ----------
def _state(eng):
    """What a save must bring back exactly."""
    return json.dumps({
        "turn": eng.turn,
        "fighters": {f.name: {"health": round(f.health, 4), "energy": round(f.energy, 4), "status": f.status,
                              "out": f.eliminated, "parts": {p.name: [round(p.damage, 4), round(p.resistance, 4)]
                                                             for p in f.parts.values()}}
                     for f in eng.fighters.values()},
        "holds": sorted([h.attacker, h.defender, h.part, round(h.power, 4), h.sub, h.locked] for h in eng.holds.values()),
        "pins": sorted(eng.pins), "downed": eng.downed, "facing": eng.facing}, sort_keys=True, default=str)


def _round_trip(s, names, problems):
    tmp = tempfile.mkdtemp(prefix="fightsim_regress_")
    path = os.path.join(tmp, "save.json")
    s.eng.save(path, s._extra())
    e2 = Engine(seed=0, only=names)
    e2.load(path)
    if _state(e2) != _state(s.eng):
        problems.append("save/load changed the state")
    for b in e2.check_state():
        problems.append(f"after loading: {b}")
    # a save from an older build: the newer fields missing
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for k in ("more", "chronicle", "setups", "broken_props", "weather", "arena_marks", "alliances", "last_reposition",
              "tally", "scene_name"):
        data.pop(k, None)
    for f in data["fighters"].values():
        for k in ("learned", "out_beats", "adrenaline_used", "voice", "tells", "move_uses"):
            f.pop(k, None)
        f["from_a_newer_build"] = True      # a field this build has never heard of
    for h in data["holds"].values():
        for k in ("locked", "sub", "coil", "grab"):
            h.pop(k, None)
    old = os.path.join(tmp, "old.json")
    with open(old, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    s2 = _quiet(H.session, 7, fighters=",".join(names))
    try:
        _quiet(s2.load, old)
        out, prompts = H.beat(s2, [A(names[0], names[1], "breather")], [], roll=True)
        if not prompts:
            problems.append("an old save loaded, but its next beat wasn't narrated")
        for b in s2.eng.check_state():
            problems.append(f"old save, next beat: {b}")
    except Exception as e:
        problems.append(f"an old save would not load and play on: {e!r}")


def run_case(case, verbose=False):
    name, fighters, setup, beats, saw = case
    names = fighters.split(",")
    seen, problems = False, []
    for seed in SEEDS:
        s = _quiet(H.session, seed, fighters=fighters)
        if setup:
            _quiet(setup, s)
        for i, acts in enumerate(beats, start=1):
            acts = acts(s) if callable(acts) else [dict(a) for a in acts]
            if not s.eng.active() or s.eng.winner():
                break
            # the case's own setup may already have rolled this beat's openings
            roll = not (i == 1 and setup is not None)
            try:
                out, prompts = H.beat(s, acts, [], roll=roll)
            except ValueError as e:
                # refused by the rules: fine for a chance that didn't come (an opening not there, a fighter moved),
                # but noted, so a case that is ALWAYS refused shows up as never having happened
                if verbose:
                    print(f"    seed {seed} beat {i}: refused: {e}")
                continue
            except Exception:
                problems.append(f"seed {seed} beat {i}: crashed:\n" + traceback.format_exc(limit=6))
                break
            if "[state check" in out:
                problems.append(f"seed {seed} beat {i}: " + next(l for l in out.splitlines() if "[state check" in l).strip())
            if not prompts:
                problems.append(f"seed {seed} beat {i}: the narrator was never asked to write it")
            r, e = _results(s)
            try:
                if saw(r, e, s):
                    seen = True
            except Exception:
                pass
        try:
            _round_trip(s, names, problems)
        except Exception:
            problems.append(f"seed {seed}: save/load crashed:\n" + traceback.format_exc(limit=6))
    if not seen:
        problems.append("what this case is for never happened on any seed (refused every time?)")
    return problems


def sim_fights(n=6):
    """Whole fights with the dice-driven stand-in (simulate.py), the state checked every beat."""
    import simulate
    from engine import load_json
    rules = load_json(os.path.join(H.ROOT, "rules.json"))
    problems = []
    for pair in (["Nocturne", "Ripples"], ["Cinder", "Talon"], ["Glacia", "Kitsune"]):
        for seed in range(n):
            st = _quiet(simulate.one_fight, pair, rules, None, 500 + seed)
            if st.get("state_problems"):
                problems.append(f"{' vs '.join(pair)} seed {500 + seed}: " + "; ".join(st["state_examples"][:2]))
            if st.get("errors"):
                problems.append(f"{' vs '.join(pair)} seed {500 + seed}: {st['errors']} stand-in choice(s) refused")
            if not st.get("winner"):
                problems.append(f"{' vs '.join(pair)} seed {500 + seed}: no winner after {st['beats']} beats")
    return problems


def main(argv):
    verbose = "-v" in argv
    want = [a.lower() for a in argv if not a.startswith("-")]
    t0, failed = time.time(), 0
    for case in CASES:
        if want and not any(w in case[0].lower() for w in want):
            continue
        t = time.time()
        probs = run_case(case, verbose)
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  {case[0]}  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p.replace("\n", "\n      "))
    if not want or any(w in "whole fights" for w in want):
        t = time.time()
        probs = sim_fights()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  whole fights, state checked every beat  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    print(f"\n{'ALL PASSED' if not failed else f'{failed} FAILED'} in {time.time() - t0:.0f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
