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
import atexit, contextlib, io, json, os, shutil, sys, tempfile, time, traceback

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
    # (a pin case tests pins whatever the fights are set to: rules.json may have them off, finish.no_pins)
    s.eng.rules.setdefault("finish", {})["no_pins"] = False
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
    ("second limb on a held spot", "Nerine,Ripples", None,
     [[A("Nerine", "Ripples", "hold_start", part="Right Knee", improvised_name="knee bite",
         hits=[{"part": "Right Knee", "with": "her jaws"}])],
      [A("Nerine", "Ripples", "hold_start", move="Tail Bind", part="Right Knee",
         hits=[{"part": "Right Knee", "with": "her twin tails"}])]],
     lambda r, e, s: _any(r, lambda x: x.get("type") == "hold_start" and any(
         "jaws" in str(p.get("with")) and "tails" in str(p.get("with")) for p in x.get("parts") or []))),
    ("no throat grip from the ground", "Ripples,Nerine", _down("Ripples", "face-down"),
     [[A("Ripples", "Nerine", "hold_start", part="Throat", hits=[{"part": "Throat", "with": "her twin tails"}])],
      [A("Ripples", "Nerine", "hold_start", part="Right Foot", hits=[{"part": "Right Foot", "with": "her twin tails"}])]],
     lambda r, e, s: not any(h.part == "Throat" for h in s.eng.holds.values()) and _any(
         r, lambda x: x.get("type") == "hold_start" and x.get("attacker") == "Ripples")),
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
    ("talons lock on in the air (flight.air_grab)", "Gale,Swift", _all(_no_guard, _airborne("Gale"), _airborne("Swift")),
     [[A("Gale", "Swift", "grapple", part="Right Wing", hits=[{"part": "Right Wing", "with": "her talons, clamped on it"}])]],
     lambda r, e, s: _any(r, lambda x: x.get("type") == "grapple_start" and any(
         k.get("tumble") for k in x.get("knock_on") or ())) and not s.eng.has(s.eng.get("Swift"), "airborne")),
    ("a grip on the neck says its kind of choke", "Nocturne,Ripples", _down("Ripples"),
     [[A("Nocturne", "Ripples", "hold_start", part="Neck", hits=[{"part": "Neck", "with": "her jaws", "severity": "firm"}])],
      [A("Nocturne", "Ripples", "breather")]],
     lambda r, e, s: _any(r, lambda x: x.get("type") == "hold_start" and any(
         p.get("choke_kind") == "both" for p in x.get("parts") or ())) or _any(
         e, lambda x: x.get("type") == "hold_ongoing" and x.get("choke_kind") == "both")),
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
        "pins": sorted(eng.pins), "downed": eng.downed, "facing": eng.facing,
        # everything else that must survive (story memory, burns, props lain against, the arena's dice...)
        "extra": _quiet(eng._saveable_extra), "event_rng": eng.event_rng.getstate()[1][:4]},
        sort_keys=True, default=str)


def _unclassified(eng):
    """Engine attributes in none of the groups engine.py keeps (_SNAP_FIELDS, _SNAP_EXTRA, _NOT_SNAPPED): new state
    that /undo and saves would quietly leave behind."""
    known = set(Engine._SNAP_FIELDS) | set(Engine._SNAP_EXTRA) | set(Engine._NOT_SNAPPED)
    return sorted(k for k in eng.__dict__ if k not in known)


def _undo_replay(seed, problems):
    """A beat taken back with /undo and played again the same way comes out the same: same screen, same state."""
    acts = [A("Nocturne", "Ripples", "strike", move="Slash", part="Chest"),
            A("Ripples", "Nocturne", "strike", move="Aqua Jet", part="Chest")]
    s = _quiet(H.session, seed, fighters="Nocturne,Ripples")
    for i in range(4):
        first, _ = H.beat(s, [dict(a) for a in acts[i % 2:i % 2 + 1]], [], roll=False)   # (openings rolled outside a beat aren't undone)
        after = _state(s.eng)
        _quiet(s.undo)
        again, _ = H.beat(s, [dict(a) for a in acts[i % 2:i % 2 + 1]], [], roll=False)
        # the engine's side of the beat: its stat block (the prose differs: the narrator's variety memory isn't undone)
        strip = lambda t: (t.split("-" * 40 + "\n")[1:2] or [""])[0].splitlines()
        if strip(first) != strip(again) or _state(s.eng) != after:
            diff = next((f"{x!r} / {y!r}" for x, y in zip(strip(first), strip(again)) if x != y), "the state differs")
            problems.append(f"seed {seed} beat {i + 1}: undo and replay came out different: {diff[:300]}")
            return


def _round_trip(s, names, problems):
    tmp = tempfile.mkdtemp(prefix="fightsim_regress_")
    atexit.register(shutil.rmtree, tmp, True)      # (cleared away when the run ends)
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
        # (a save of a fight already won goes on with an aftermath beat: there are no attacks left to make)
        done = s2.eng.winner()
        out, prompts = H.beat(s2, None if done else [A(names[0], names[1], "breather")], [], roll=not done)
        if not prompts:
            problems.append("an old save loaded, but its next beat wasn't narrated"
                            + (" (an aftermath beat)" if done else ""))
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
            loose = _unclassified(s.eng)
            if loose:
                problems.append(f"seed {seed} beat {i}: engine state that /undo and saves don't know about: "
                                f"{', '.join(loose)} (add each to _SNAP_EXTRA, or to _NOT_SNAPPED if it is per-beat scratch)")
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


def passage_check():
    """story_passages.txt: every passage fills only the slots the program has, belongs to a moment the program
    offers, stays short, and says nothing the hard rules forbid (no tearing, breaking, gore or killing words)."""
    import re
    import blocks
    import narrator
    with open(os.path.join(H.ROOT, "story_passages.txt"), encoding="utf-8") as fh:
        entries = blocks.parse(fh.read())
    known = {"hit", "cut", "bite", "choke", "choke_out", "held", "holding", "pinned_start", "pinned", "pinning", "landing", "air_fall", "air_tumble", "knockout", "tap_edge", "tap_out"}
    bad = re.compile(r"\b(?:gaping|torn|tore|tears? (?:open|into)|shred\w*|snap\w*|broke|broken|break\w*|fractur\w*|"
                     r"shatter\w*|sever\w*|kill\w*|die|dies|dying|dead|death|pool\w*|spray\w*|soak\w*|expos\w*|"
                     r"gush\w*|stream\w*|beat|sob\w*|weep\w*|wept)\b", re.I)
    problems = [] if entries else ["story_passages.txt has no passages"]
    for cat, conds, text in entries:
        where = f"{cat}: {text[:60]}..."
        if cat not in known:
            problems.append(f"{where} belongs to no moment the program offers")
        if set(blocks.SLOT.findall(text)) - {"part", "foe"}:
            problems.append(f"{where} has a slot the program never fills")
        m = bad.search(text)
        if m:
            problems.append(f"{where} says '{m.group(0)}'")
        if len([x for x in narrator._SENT.split(text) if x.strip()]) > 4:
            problems.append(f"{where} is longer than four sentences")
    return problems


def tap_last_check():
    """narration.tap_last: a part before the last that tells the match-ending pass-out or tap has it taken out (and
    the holder letting go right after), for the end of the beat to tell; a refusal to tap stays."""
    import json
    import narrator
    with open(os.path.join(H.ROOT, "rules.json"), encoding="utf-8") as fh:
        n = narrator.Narrator("none", json.load(fh))
    n.strengths, problems = {"Ripples": 600, "Nerine": 300}, []
    n._tap_end = ("Nerine", "Ripples", "pass_out", "choke")
    out = n._cut_early_end("Ripples felt Nerine's struggles weaken. Her limbs stopped answering, and she went limp. "
                           "Ripples let go of her neck. The other Buizel slid down, her body limp.\n\nThe wind blew.")
    if "went limp" in out or "let go" in out or "slid down" in out or "struggles weaken" not in out:
        problems.append(f"the early pass-out was not taken out cleanly: {out!r}")
    n._tap_end = ("Nerine", "Ripples", "tap", "armbar")
    out = n._cut_early_end("Nerine would not tap. Nerine's paw slapped the ground, again and again. Ripples let go.")
    if out != "Nerine would not tap.":
        problems.append(f"the early tap was not taken out cleanly: {out!r}")
    return problems


def taps_check():
    """finish.submission.taps: the tally, the used-up parts, the target the fight is pushed onto, and the cuts the
    program makes by itself (narration.cuts), and the /set guess for a mistyped path."""
    import director, play as P
    path = os.path.join(H.ROOT, "rules.json")
    with open(path, encoding="utf-8") as fh:
        before = fh.read()
    try:
        return _taps_check(director, P)
    finally:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(before)      # (its /set lines save to rules.json: the fights after it must not be submission matches)


def _taps_check(director, P):
    s = H.session(3, fighters="Nerine,Ripples", settings=["/set finish.submission.enabled true",
                                                           "/set finish.submission.taps.enabled true",
                                                           "/set finish.submission.taps.needed 3",
                                                           "/set finish.submission.taps.different_parts 50"])
    e, problems = s.eng, []
    if (e.taps_needed(), e.taps_distinct_needed()) != (3, 2):
        problems.append(f"3 taps at 50% should need 2 different parts, got {e.taps_distinct_needed()}")
    d = e.get("Ripples")
    d.learned["taps_given"] = ["Right Thigh"]
    if e.spent_tap_parts(d):
        problems.append("one repeat is allowed at 50%, but the first tap's part is already used up")
    d.learned["taps_given"] = ["Right Thigh", "Right Thigh"]
    if e.spent_tap_parts(d) != ["Right Thigh"]:
        problems.append(f"after the one repeat, the right thigh should be used up: {e.spent_tap_parts(d)}")
    aim = e.tap_target(d)
    if not aim or aim == "Right Thigh":
        problems.append(f"the target should be a part that still counts, not {aim}")
    b = director._apply_tap_steer(e, "Nerine", "Ripples", {"part": "Right Thigh"}, "strikes")
    if b.get("part") != aim:
        problems.append(f"a blow on a used-up part should move onto the target {aim}: {b.get('part')}")
    b = director._apply_tap_steer(e, "Nerine", "Ripples", {"hits": [{"part": "Right Thigh"}]}, "holds")
    if b["hits"][0]["part"] != aim:
        problems.append(f"a grip on a used-up part should move onto the target {aim}: {b['hits']}")
    if "TAP COUNT" not in director.taps_hint(e) or "NO LONGER" not in director.taps_hint(e):
        problems.append("the director is not told the tally and the used-up parts")
    n = s.narrator
    n.strengths, n.beat_now, n.damage_by = {"Ripples": 90, "Nerine": 100}, 1, {"Ripples": {"Right Thigh": 60}}
    out = n._program_cuts(["Her right thigh ached. Her right thigh throbbed. Her right thigh burned. Her legs were "
                           "still sore from the earlier blows. Nerine's plain blow hit her. Nerine's reaction would "
                           "follow."])[0]
    for bad in ("burned", "earlier blows", "plain blow", "would follow"):
        if bad in out:
            problems.append(f"'{bad}' was not cut: {out!r}")
    if n._name_possessives("Ripple's body") != "Ripples' body":
        problems.append("Ripple's was not mended to Ripples'")
    try:
        P._rule_path(e.rules, "finish_submission.enabled")
    except ValueError as x:
        if "finish.submission.enabled" not in str(x):
            problems.append(f"no guess for the mistyped path: {x}")
    # build 240: a target hurt past steer.ready sends the blows to the next part; the holds stay on it
    d.learned["taps_given"] = ["Right Thigh", "Right Thigh"]
    e.rules["finish"]["submission"]["taps"].update(needed=4, different_parts=100)   # (two still to go)
    aim = e.tap_target(d)
    d.parts[aim].damage = 400.0
    nxt = e.tap_next(d)
    if not e.tap_ready(d) or not nxt or nxt == aim:
        problems.append(f"a target at 400% should be ready, with a next part: {aim} -> {nxt}")
    b = director._apply_tap_steer(e, "Nerine", "Ripples", {"part": "Right Thigh"}, "strikes")
    if b.get("part") != nxt:
        problems.append(f"with the target ready, a blow on a used-up part should go to the next part {nxt}: {b}")
    b = director._apply_tap_steer(e, "Nerine", "Ripples", {"hits": [{"part": "Right Thigh"}]}, "holds")
    if b["hits"][0]["part"] != aim:
        problems.append(f"with the target ready, a grip should still go onto it ({aim}): {b['hits']}")
    if "READY" not in director.taps_hint(e):
        problems.append("the director is not told the target is ready for a hold")
    n.progress = None
    # build 240: narration.cut_first: a slip a rewrite rarely mends is cut with no model call
    calls = []
    n._rewrite_paragraph = lambda *a, **k: calls.append(1) or ""
    n._bad_sentences = lambda text, prior="": {"Her wing ached.": "Ripples: nobody in this fight has that"}
    out = n._repair_paragraphs("", "Ripples gasped. Her wing ached. She stood.", "")
    del n._rewrite_paragraph, n._bad_sentences
    if calls or "wing" in out or "She stood." not in out:
        problems.append(f"cut_first should cut the sentence with no rewrite: {out!r} ({len(calls)} calls)")
    d.parts[aim].damage = 0.0
    e.rules["finish"]["submission"]["taps"].update(needed=3, different_parts=50)
    # build 239: a grab on a ruined part (or once her health is gone) can make her tap; a kept grip with a second
    # limb adds that limb once, and stays as loose as she worked it
    d.learned.pop("taps_given", None)
    st = e.start_hold("Nerine", "Ripples", "Left Thigh", 8, with_part="her jaws")
    h = e.holds[st["hold_id"]]
    h.grab, h.turns_active = True, 10     # (long on: since build 264 the tap chance builds up over the hold's beats)
    d.parts["Left Thigh"].damage, d.health = 300.0, -50.0
    e.rules["finish"]["submission"]["tap"]["climb"]["start"] = 1.0
    rolled = []
    for _ in range(12):
        e.turn += 1           # (beats go by: since build 255 a wrecked part first holds out a few of them)
        evs = e._tap_out_tick()
        rolled += [ev["type"] for ev in evs]
        if any(t in ("tap_count", "tap_out") for t in rolled):
            break
    if not any(t in ("tap_count", "tap_out") for t in rolled):
        problems.append(f"a grab on a ruined thigh with no health left never made her tap: {rolled}")
    e.holds.clear()
    st = e.start_hold("Nerine", "Ripples", "Left Thigh", 6, with_part="her jaws")
    for _ in range(3):
        e.start_hold("Nerine", "Ripples", "Left Thigh", 23, with_part="her twin tails", keep_with=True)
    h = e.holds[st["hold_id"]]
    if h.power > 6 + 0.5 * 6 + 1e-6 or "twin tails" not in h.with_part:
        problems.append(f"a kept grip with a second limb should press 6 + half of 6 once: {h.power} ({h.with_part})")
    # build 240: a used-up part in the grip adds no pain toward the next tap; after a tap that isn't the last she
    # is let go and left alone a beat (taps.respite)
    e.holds.clear()
    d.health = d.max_health * 0.3
    d.learned.update(taps_given=["Left Thigh"], tap_limit="x")
    e.rules["finish"]["submission"]["taps"].update(needed=3, different_parts=100)
    for p_ in d.parts.values():
        p_.damage = 0.0
    d.parts["Left Thigh"].damage = 600.0
    for part_, w_ in (("Left Thigh", "her jaws"), ("Left Knee", "her twin tails")):
        st = e.start_hold("Nerine", "Ripples", part_, 8, with_part=w_)
        e.holds[st["hold_id"]].turns_active = 5
    evs = e._tap_out_tick()
    if any(ev["type"] in ("tap_count", "tap_out") for ev in evs) or any(
            ev["type"] == "tap_resist" and ev["pain"] > 300 for ev in evs):
        problems.append(f"the used-up left thigh still carried the pain toward a tap: {[ev for ev in evs if 'pain' in ev]}")
    e.holds.clear()
    d.learned.update(taps_given=[], tap_respite=["Nerine", e.turn + 1])
    try:
        res, _ = director.resolve_many(e, [{"action": "hold_start", "attacker": "Nerine", "defender": "Ripples",
                                            "hits": [{"part": "Left Knee", "severity": "firm"}], "flavor": "grabs her knee"}])
        if any(r.get("type") == "hold_start" for r in (res if isinstance(res, list) else [res])) or e.holds:
            problems.append("during the respite after a tap the holder put a new grip on her")
    except ValueError as x:
        problems.append(f"the respite step back was refused: {x}")
    e.holds.clear()
    d.learned.pop("tap_respite", None)
    d.parts["Left Thigh"].damage = 0.0
    d.health = d.max_health
    n.scene_cfg = {"kind": "lakeside forest", "name": "The lakeside clearing"}
    out = n._program_cuts(["*I can't give up now* She steeled herself. Her left thigh was RUINED and raw. "
                           "The saltwater stung her nose. *Let her feel it*"])[0]
    for bad in ("now* She", "RUINED", "saltwater", "feel it*"):
        if bad in out and not (bad == "feel it*" and "feel it.*" in out):
            problems.append(f"'{bad}' was not mended: {out!r}")
    return problems


def ruined_check():
    """Build 242: the ruined tier past devastated (a leg that folds, a part jarred by her own movement, more tap
    pain) and the stages below zero health (her refusal once, sight greying, a second wind)."""
    s = H.session(5, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    from engine import tier_for, pain_tiers
    if tier_for(520, pain_tiers(e.rules))["label"] != "ruined":
        problems.append(f"520% should be ruined: {tier_for(520, pain_tiers(e.rules))['label']}")
    d = e.get("Ripples")
    d.parts["Left Thigh"].damage = 600.0
    e.rules["ruined"].update(buckle_chance=1.0, jar_chance=1.0)
    evs = e._ruined_tick()
    if not any(ev["type"] == "ruined_buckle" and ev["fighter"] == "Ripples" for ev in evs) or not e.has(d, "off_balance"):
        problems.append(f"a ruined leg should fold under her (off balance): {evs}")
    d.health = -0.3 * d.max_health
    st = e.zero_stage(d)
    if not st or st.get("label") != "greying out":
        problems.append(f"-30% of full should be the greying-out stage: {st}")
    if not any(lab == "greying out" and m < 1 for lab, m in e.power_extras(d, e.get("Nerine"), "Water")):
        problems.append(f"the stage below zero doesn't soften her blows: {e.power_extras(d, e.get('Nerine'), 'Water')}")
    evs = e._below_zero_tick()
    if not any(ev["type"] == "refuses_to_fall" for ev in evs):
        problems.append(f"the first time below zero she should refuse to go down: {evs}")
    evs2 = e._below_zero_tick()
    if any(ev["type"] == "refuses_to_fall" for ev in evs2):
        problems.append("the refusal came twice")
    e.rules["ruined"]["enabled"] = False
    if tier_for(520, pain_tiers(e.rules))["label"] != "devastated":
        problems.append("with ruined off, 520% should stay devastated")
    return problems


def downtime_check():
    """Build 243: fighters aren't left down most of the fight (a collapse can't come again right after she rises, and
    each is rarer; a director's knockdown may leave her standing), a fighter on the ground can lock a submission on
    one who is down too in a submission match, and the ruined jar is told at most every few beats."""
    s = H.session(5, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    d = e.get("Ripples")
    d.health = -0.6 * d.max_health
    e.rules["health"]["collapse"].update(base=1.0, max=1.0, repeat_mult=1.0)
    e.downed.pop(d.name, None)
    d.learned.update(collapse_turn=e.turn - 10, rose_turn=e.turn - 1)
    if any(ev["type"] == "collapse" for ev in e._collapse_tick()):
        problems.append("she collapsed again one beat after getting up (health.collapse.stand_grace)")
    d.learned["rose_turn"] = e.turn - 6
    if not any(ev["type"] == "collapse" for ev in e._collapse_tick()):
        problems.append("past stand_grace, a sure collapse didn't come")
    e.rules["health"]["collapse"]["repeat_mult"] = 0.5
    if e.times("collapse", d.name) != 1:
        problems.append(f"collapses aren't counted: {e.times('collapse', d.name)}")
    e.downed.pop(d.name, None)
    d.health = d.max_health
    _, ch = e.keeps_feet(d, [])
    if abs(ch - 0.7) > 0.01:
        problems.append(f"at full health a feather of a blow should keep her up 70% of the time: {ch}")
    d.health = -0.5 * d.max_health
    _, ch = e.keeps_feet(d, [{"defender": d.name, "health_loss": 0.2 * d.max_health}])
    if not 0 < ch < 0.2:
        problems.append(f"badly hurt, a huge blow should still leave a small chance she stays up: {ch}")
    e.rules["finish"]["submission"]["enabled"] = True
    e.downed.update({"Nerine": 0, "Ripples": 0})
    if not e.ground_lock_ok("Nerine"):
        problems.append("in a submission match a fighter on the ground should be able to lock one on (from_ground)")
    e.rules["finish"]["submission"]["enabled"] = False
    if e.ground_lock_ok("Nerine"):
        problems.append("outside a submission match from_ground (match_only) should be off")
    d.parts["Left Thigh"].damage = 600.0
    e.rules["ruined"].update(buckle_chance=0.0, jar_chance=1.0)
    first = [ev for ev in e._ruined_tick() if ev["type"] == "ruined_jar" and ev["fighter"] == d.name]
    again = [ev for ev in e._ruined_tick() if ev["type"] == "ruined_jar" and ev["fighter"] == d.name]
    if not first or again:
        problems.append(f"the ruined jar should come once, then wait (jar_cooldown): {first} then {again}")
    return problems


def tap_meter_all_check():
    """Build 274: in a submission match a plain hold that hurts shows on the tap meter from its first beat (it counts
    toward a tap), and a grab that can't count yet says on the hold panel how hurt the part must be first."""
    s = H.session(5, fighters="Nerine,Ripples")
    import cards
    e, problems = s.eng, []
    a, d = e.get("Nerine"), e.get("Ripples")
    e.rules["finish"]["submission"]["enabled"] = True
    st = e.start_hold(a.name, d.name, "Left Thigh", 12.0)
    e.holds[st["hold_id"]].turns_active = 1
    e._tap_out_tick()
    m = cards.tap_meter({"grips": e.card_state(d)})
    if not m or "counts toward one" not in m["note"]:
        problems.append(f"a plain hold's first beat should show on the tap meter: {m}")
    e.rules["finish"]["submission"]["tap"]["meter_all"] = False
    d.learned.pop("tap_state", None)
    e._tap_out_tick()
    if e.card_state(d)["tap"]:
        problems.append("with meter_all off the first beat of a plain hold should stay off the meter")
    e.release(st["hold_id"], "test")
    st = e.start_hold(a.name, d.name, "Right Arm" if "Right Arm" in d.parts else next(iter(d.parts)), 8.0)
    e.holds[st["hold_id"]].grab = True
    lines = [t for t, _ in cards.grip_lines({"grips": e.card_state(d)})]
    if not any("no tap until it is 100% hurt" in t for t in lines):
        problems.append(f"a grab that can't count yet should say so on the hold panel: {lines}")
    return problems


def coil_size_check():
    """Build 275: a serpent many times her size coils her middle, never one of her limbs alone (holds.coil.size); it
    is harder to wrench out of; with her arms trapped in the coils no tap sign or tap needs a free paw; and the
    narrator never gives a serpent feet, limbs, an arm or a shoulder."""
    import director
    from narrator import Narrator
    from engine import body_region
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    e = s.eng
    e.rules["finish"]["submission"]["enabled"] = True
    for _ in range(20):
        e.holds.clear()
        e.get("Seraphina").energy = 100.0
        director.resolve_many(e, [{"action": "hold_start", "attacker": "Seraphina", "defender": "Ripples", "move": "Wrap",
                                   "hits": [{"part": "Left Upper Arm", "severity": "firm", "with": "her coils"}]}])
        mid = [h for h in e.holds.values() if h.coil and body_region(h.part) in e.MIDDLE_REGIONS]
        if not mid:
            problems.append(f"a Milotic's coil on a Buizel's arm should go round her middle first: "
                            f"{[(h.part, h.with_part) for h in e.holds.values()]}")
            break
    plain = e.hold_break_chance("Seraphina", "Ripples")
    e.rules["holds"]["coil"]["size"]["enabled"] = False
    if not plain < e.hold_break_chance("Seraphina", "Ripples"):
        problems.append("wound in the coils of something many times her size should be harder to wrench out of")
    e.holds.clear()
    e.get("Seraphina").energy = 100.0
    director.resolve_many(e, [{"action": "hold_start", "attacker": "Seraphina", "defender": "Ripples", "move": "Wrap",
                               "hits": [{"part": "Left Upper Arm", "severity": "firm", "with": "her coils"}]}])
    if [h.part for h in e.holds.values()] != ["Left Upper Arm"]:
        problems.append("with holds.coil.size off, a coil should go where it is put")
    e.rules["holds"]["coil"]["size"]["enabled"] = True
    e.get("Seraphina").energy = 100.0
    t = H.session(3, fighters="Seraphina,Tidecrest").eng
    director.resolve_many(t, [{"action": "hold_start", "attacker": "Seraphina", "defender": "Tidecrest", "move": "Wrap",
                               "hits": [{"part": "Left Upper Arm", "severity": "firm", "with": "her coils"}]}])
    if [h.part for h in t.holds.values()] != ["Left Upper Arm"]:
        problems.append("a Milotic is not three times a Dragonite's size: her arm can be coiled alone")
    # her arms trapped: no sign of the urge, and no tap, needs a free paw
    e.holds.clear()
    director.resolve_many(e, [{"action": "hold_start", "attacker": "Seraphina", "defender": "Ripples", "move": "Wrap",
                               "hits": [{"part": "Stomach", "severity": "firm", "with": "her coils"}]}])
    d = e.get("Ripples")
    e.set_status(d, "constricted", 2)
    if not e.arms_trapped(d):
        problems.append("coils round her stomach with her constricted should trap her arms")
    picks = {e._tell(k, d, []) for k in ("tap_tell_urge", "tap_tell_urge2", "tap_tell_first", "tap_tell_closer",
                                         "tap_tell_edge") for _ in range(30)}
    if picks & set(e.PAW_TELLS):
        problems.append(f"with her arms trapped no tap sign should need a free paw: {sorted(picks & set(e.PAW_TELLS))}")
    if not e._wraps_with("her twin tails", "wraps her twin tails round the tail") or \
            e._wraps_with("both paws", "her twin tails wound round the knee"):
        problems.append("a one-grip hold wrapping the very limb it grips with should be a coil (and only that limb)")
    n = Narrator.__new__(Narrator)
    n.rules, n.plans, n.posture_start, n.on_ground, n.grips = e.rules, {"Seraphina": "serpent"}, {}, set(), []
    if "coils" not in n._tap_spot("Ripples", "Seraphina"):
        problems.append(f"a tap on a serpent standing should land on her coils: {n._tap_spot('Ripples', 'Seraphina')}")
    if "paw" in n._tap_intensity(3, {"arms_trapped": True}).split("(")[0]:
        problems.append("with her arms trapped the tap ladder should not have a paw rising")
    return problems


def presets_help_check():
    """Build 282: match presets (/preset), the anything-goes match (finish.submission.allow_knockouts), and the help:
    every command the game takes is in it, with the new examples and presets topics."""
    import re as _re
    import play
    problems = []
    s = H.session(3, fighters="Nerine,Ripples")
    e = s.eng
    with contextlib.redirect_stdout(io.StringIO()):
        play.handle_command(s, "/preset knockout nosave")
    if not (e.ko_only() and e.no_pins() and not e.submission_match()):
        problems.append("/preset knockout should make a knockout-only match with no pins")
    with contextlib.redirect_stdout(io.StringIO()):
        play.handle_command(s, "/preset submission3 nosave")
    if not (e.submission_match() and e.taps_needed() == 3 and not e.ko_only()):
        problems.append("/preset submission3 should make a three-tap submission match")
    with contextlib.redirect_stdout(io.StringIO()):
        play.handle_command(s, "/preset anything nosave")
    if not (e.submission_match() and e.sub_knockouts() and not e.no_pins() and not e.ko_only()):
        problems.append("/preset anything: taps, pins and knockouts should all be possible")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        play.handle_command(s, "/preset pins ?")
    if "/set finish.submission.enabled false" not in out.getvalue():
        problems.append(f"/preset pins ? should show the /set lines: {out.getvalue()[:200]}")
    src = open(os.path.join(os.path.dirname(play.__file__), "play.py"), encoding="utf-8").read()
    cmds = set(_re.findall(r'cmd == "([a-z_]+)"', src))
    for grp in _re.findall(r'cmd in \(([^)]*)\)', src):
        names = _re.findall(r'"([a-z_]+)"', grp)
        if names and not any(_re.search(r"/" + n + r"\b", play.HELP) for n in names):
            problems.append(f"no help for /{names[0]} (or {', '.join(names[1:])})")
    for c in cmds:
        if c not in ("exit",) and not _re.search(r"/" + c + r"\b", play.HELP) and not any(
                c in _re.findall(r'"([a-z_]+)"', g) for g in _re.findall(r'cmd in \(([^)]*)\)', src)):
            problems.append(f"no help for /{c}")
    for topic in ("examples", "presets"):
        if "EXAMPLES" not in play.help_text("examples") or "MATCH PRESETS" not in play.help_text("presets"):
            problems.append(f"/help {topic} should show its section")
    for c in _re.findall(r"(?m)^    (/[a-z]+)", play.help_text("examples")):
        if c.lstrip("/") not in cmds and not any(c.lstrip("/") in _re.findall(r'"([a-z_]+)"', g)
                                                  for g in _re.findall(r'cmd in \(([^)]*)\)', src)):
            problems.append(f"an example uses {c}, which is not a command")
    # (the setup questions: all of them asked in order, Enter keeping everything; a preset asks only a few)
    s2 = H.session(3, fighters="Nocturne,Ripples")
    asked = []

    def rd(prompt, answers=iter(["o"] + [""] * 40)):
        asked.append(prompt.split(">")[0])
        return next(answers, "")
    with contextlib.redirect_stdout(io.StringIO()):
        play.setup_questions(s2, read=rd)
    for want in ("Start", "Scene", "Fighters", "Players", "Intro", "Match", "Plan", "Focus", "Length", "Damage",
                 "Traits", "Character", "Swearing", "Story", "Hazards", "More", "Begin"):
        if want not in asked:
            problems.append(f"the setup should ask {want}: {asked}")
    asked.clear()
    ans = iter(["knockout", "", "Nerine Ripples", "Ripples", "fair", "12"])
    with contextlib.redirect_stdout(io.StringIO()):
        play.setup_questions(s2, read=lambda p: (asked.append(p.split(">")[0]), next(ans, ""))[1])
    if asked != ["Start", "Scene", "Fighters", "Players", "Dice", "Begin"] or not s2.eng.ko_only() \
            or s2.players != ["Ripples"] or getattr(s2, "_setup_auto", 0) != 12:
        problems.append(f"a preset at the start should ask only where, who, players and begin, and apply them: {asked} "
                        f"{s2.players} {getattr(s2, '_setup_auto', 0)}")
    # build 283 (the user's log): the questions after the fighters one use the new fight, and its banner waits
    s3 = H.session(3, fighters="Nocturne,Ripples,Nerine,Seraphina")
    full, ans = [], iter(["1", "", "Seraphina Ripples", "all", "", ""])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        play.setup_questions(s3, read=lambda p: (full.append(p), next(ans, ""))[1])
    pl = next((p for p in full if p.startswith("Players")), "")
    dice = next((p for p in full if p.startswith("Dice")), "")
    if "Nocturne" in pl or "Seraphina, Ripples" not in pl or sorted(s3.players) != ["Ripples", "Seraphina"]:
        problems.append(f"the players question should name the fighters just chosen: {pl!r} {s3.players}")
    if f"Enter keeps {s3.dice_mode()}" not in dice:
        problems.append(f"the dice question should say the mode that is set: {dice!r}")
    if "Press Enter to begin" in out.getvalue():
        problems.append("choosing the fighters in the setup shouldn't print the fight's banner mid-questions")
    s3.use_llm, s3.story = True, []
    s3.eng.rules["narration"]["scene_intro"] = False
    if not s3.playing():
        problems.append("with no opening passage, the fighters you play are asked from the very first beat")
    s3.eng.rules["narration"]["scene_intro"] = True
    if s3.playing():
        problems.append("with an opening passage, the first Enter writes it before you are asked")
    return problems


def reactions_308_check():
    """Build 308 (moves.reactions, holds.endurance, concussion.min_blows, director.face_chance): a blow leaves what it
    should by what it was and where it landed, the ones that add up only once they have, never more than a few at once
    or the same one again too soon; a hold is felt in stages and leaves its aftermath when it comes off; panic with no
    air; one huge head blow never concusses; coils and submissions are harder to break against an equal, about as easy
    as before for a much stronger fighter; the switches turn it all off."""
    import director as D
    import narrator as N
    import reactions as R
    from engine import Hold
    problems = []
    e = Engine(seed=3, only=["Nocturne", "Ripples"])
    e._chance = lambda p, *a, **k: p > 0
    n, r = e.get("Nocturne"), e.get("Ripples")
    hit = lambda part, dmg, after=None: {"defender": "Ripples", "part": part, "damage_taken": dmg,
                                         "damage_after": after if after is not None else dmg, "damage_before": 0}
    punch = {"name": "Mach Punch", "type": "Fighting", "about": "a fast punch"}
    got = [x["status"] for x in R.on_hits(e, n, r, punch, [hit("Nose", 40)])]
    if "nosebleed" not in got or not e.has(r, "nosebleed") or "NOSEBLEED" not in e.status_look("Ripples", "nosebleed"):
        problems.append(f"a hard punch on the nose should bloody it: {got}")
    claw = {"name": "Night Slash", "type": "Dark", "about": "a slashing claw"}
    got = [x["status"] for x in R.on_hits(e, n, r, claw, [hit("Left Flank", 20)])]
    if "stinging_cuts" in got:
        problems.append("one small cut should not leave her cuts stinging: the cuts have to add up first")
    for _ in range(6):
        R.on_hits(e, n, r, claw, [hit("Left Flank", 25)])
    if not e.has(r, "stinging_cuts"):
        problems.append("cut after cut should leave her cuts stinging")
    on = [s for s in R.REACT if e.has(r, s) and R.REACT[s]["kind"] == "body"]
    if len(on) > 2:
        problems.append(f"at most max_body body reactions should be on her at once: {on}")
    r.status.pop("nosebleed", None)
    if R.on_hits(e, n, r, punch, [hit("Nose", 40)]) and e.has(r, "nosebleed"):
        problems.append("the same reaction should not come again within its beats + cooldown")
    # mind: shaken by a big blow, the one who landed it emboldened; anger after a run with no answer
    e2 = Engine(seed=4, only=["Nocturne", "Ripples"])
    e2._chance = lambda p, *a, **k: p > 0
    n2, r2 = e2.get("Nocturne"), e2.get("Ripples")
    R.on_hits(e2, n2, r2, punch, [hit("Chest", 120)])
    if not (e2.has(r2, "shaken") and e2.has(n2, "emboldened")
            and any(x.get("status") == "emboldened" for x in e2._pending_events)):
        problems.append("a huge blow should shake her and embolden the one who landed it (told in the beat)")
    e3 = Engine(seed=5, only=["Nocturne", "Ripples"])
    e3._chance = lambda p, *a, **k: p > 0
    n3, r3 = e3.get("Nocturne"), e3.get("Ripples")
    for _ in range(3):
        R.on_hits(e3, n3, r3, punch, [hit("Chest", 10)])
    if not e3.has(r3, "angry"):
        problems.append("three blows in a row she couldn't answer should make her angry")
    for _ in range(3):
        R.on_miss(e3, r3, n3)
    if not e3.has(r3, "frustrated") and not e3.has(r3, "angry"):
        problems.append("three misses in a row should frustrate her")
    if R.mult(e3, r3, "power") <= 1.0:
        problems.append("anger should put a little more behind her blows")
    # one huge head blow never concusses her
    e4 = Engine(seed=6, only=["Nocturne", "Ripples"])
    r4 = e4.get("Ripples")
    r4.part("Head").damage = 500
    e4._head_jolts(r4, [hit("Head", 400, 500)], punch, e4.get("Nocturne"))
    if e4.has(r4, "concussed"):
        problems.append("one blow, however hard, should never concuss her (concussion.min_blows)")
    # a hold felt in stages, panic, and its aftermath
    e5 = Engine(seed=7, only=["Seraphina", "Ripples"])
    e5._chance = lambda p, *a, **k: p > 0
    s5, r5 = e5.get("Seraphina"), e5.get("Ripples")
    e5.holds[1] = h = Hold(1, "Seraphina", "Ripples", "Chest", 15, 0, "", turns_active=1, with_part="her coils", coil=True)
    ev = R.tick(e5)
    if not any(x["type"] == "hold_feel" and x["kind"] == "coil_body" and x["stage"] == 1 for x in ev):
        problems.append(f"the coils round her chest should be felt from their first beat: {ev}")
    if any(x["type"] == "hold_feel" for x in R.tick(e5)):
        problems.append("a stage of a hold should be told once, not every beat")
    h.turns_active = 2
    ev = R.tick(e5)
    if not any(x["type"] == "hold_feel" and x["stage"] == 2 for x in ev):
        problems.append("the next stage of the coils should be told when it comes")
    if not e5.has(r5, "panicking"):
        problems.append("two beats with the coils squeezing her breath should panic her")
    e5.holds.pop(1)
    ev = R.tick(e5)
    if not (e5.has(r5, "head_rush") and any(x.get("after") == "coil_body" for x in ev)):
        problems.append(f"the coils coming off should leave a head rush as the blood floods back: {ev}")
    for st in ("head_rush", "nosebleed", "panicking", "shaken"):
        if st not in N.Narrator.STATUS_STORY or st not in N.Narrator.STATUS_ENDS:
            problems.append(f"the narrator should know how {st} shows and how it ends")
    # endurance: against an equal she breaks free less; much stronger, about as before; a plain grip unchanged
    e6 = Engine(seed=8, only=["Nocturne", "Ripples"])
    n6, r6 = e6.get("Nocturne"), e6.get("Ripples")
    sub = [Hold(2, "Nocturne", "Ripples", "Left Arm", 15, 0, "", sub="armbar")]
    eq = e6.hold_endurance(n6, r6, sub)
    n6.health = n6.max_health * 0.15
    n6.energy = 10
    strong = e6.hold_endurance(n6, r6, sub)
    if not (eq < 0.8 and strong > 0.9 and strong > eq):
        problems.append(f"a submission should be harder to break against an equal ({eq:.2f}) than for a fighter far "
                        f"stronger than the holder ({strong:.2f})")
    if e6.hold_endurance(n6, r6, [Hold(3, "Nocturne", "Ripples", "Left Arm", 15, 0, "")]) != 1.0:
        problems.append("a plain grip should not be changed by holds.endurance")
    # the face hint
    e6.rules["director"]["face_chance"] = 1.0
    n6.health = n6.max_health
    fh = D.face_hint(e6)
    if "Muzzle" not in fh and "Nose" not in fh:
        problems.append(f"the face hint should name her muzzle or nose: {fh!r}")
    # switches
    e7 = Engine(seed=9, only=["Nocturne", "Ripples"])
    e7._chance = lambda p, *a, **k: p > 0
    e7.rules["moves"]["reactions"]["effects"] = False
    R.on_hits(e7, e7.get("Nocturne"), e7.get("Ripples"), punch, [hit("Chest", 120)])
    if R.mult(e7, e7.get("Nocturne"), "power") != 1.0:
        problems.append("reactions.effects false should leave the numbers alone")
    e7.rules["moves"]["reactions"]["enabled"] = False
    if R.on_hits(e7, e7.get("Nocturne"), e7.get("Ripples"), punch, [hit("Nose", 60)]) or R.tick(e7):
        problems.append("reactions.enabled false should give no reactions at all")
    return problems


def alive_306_check():
    """Build 306 (window.alive, narration.settling_in): her signs for the heart monitor rise with exertion and pain,
    the grey closes in near a black-out and a choke, a stopped heart reads stopped; what landed since the beat
    before is found for the jolt; breathing and greying keep her picture's size and outline; a hurt comes on in the
    notes a beat or more after the hit, once per step, the same on a reroll, lying down told without her weight."""
    import copy
    import cards as K
    problems = []
    f = {"name": "Ripples", "health": 1700, "max": 1700, "energy": 100, "status": {}, "out": False,
         "parts": [("Left Foot", 0, 80), ("Chest", 0, 90)], "pain": {"overall": {"pct": 0}}, "grips": None}
    calm = K.body_signs(f)
    if not (95 <= calm["heart"] <= 106 and calm["colour"] == "#22c55e" and calm["grey"] == 0 and calm["breath"] == 16):
        problems.append(f"a fresh fighter should read near her resting heart and breathing, green: {calm}")
    hurt = copy.deepcopy(f)
    hurt.update(energy=20, status={"adrenaline": 2}, pain={"overall": {"pct": 120, "label": "near her limit"}})
    hs = K.body_signs(hurt)
    if not (hs["heart"] > calm["heart"] * 1.4 and hs["breath"] > 30 and "winded" in hs["words"]
            and "near her limit" in hs["words"] and "adrenaline" in hs["words"] and hs["throb"] == 1.0):
        problems.append(f"exertion, pain and adrenaline should raise her heart and breathing and say so: {hs}")
    if hs["heart"] > 100 * K.ALIVE["heart_max"] + 1:
        problems.append("the heart rate should be capped at heart_max of her resting rate")
    coiled = copy.deepcopy(f)
    coiled["grips"] = {"tap": {"vitals": {"heart": 60, "irregular": True, "bp": [70, 45], "squeeze": 90,
                                          "blood": 58, "out_at": 60}}}
    cs = K.body_signs(coiled)
    if not (cs["coiled"] and cs["heart"] == 60 and cs["grey"] > 0.8 and cs["depth"] < 0.5):
        problems.append(f"near her black-out in the coils the grey should close in and her breath go shallow: {cs}")
    coiled["grips"]["tap"]["vitals"]["stopped"] = True
    st = K.body_signs(coiled)
    if not (st["heart"] == 0 and st["grey"] == 1.0 and st["breath"] == 0):
        problems.append(f"a stopped heart should read stopped, no breath, fully grey: {st}")
    choke = copy.deepcopy(f)
    choke["grips"] = {"tap": {"choke": True, "circ": False, "air": 85}}
    ch = K.body_signs(choke)
    if not (ch["grey"] > 0.5 and "no air getting in" in ch["words"]):
        problems.append(f"a choke near her limit should grey her and say no air is getting in: {ch}")
    hit = copy.deepcopy(f)
    hit["parts"] = [("Left Foot", 45, 70), ("Chest", 0, 90)]
    hit["health"] = 1600
    hits, jolt = K.impacts(f, hit)
    if not (hits and hits[0][0] == "Left Foot" and 0.5 < hits[0][1] <= 1.0 and jolt > 0.5):
        problems.append(f"a blow since the beat before should be found for the jolt: {hits, jolt}")
    if K.impacts(None, hit) != ([], 0.0) or K.impacts(hit, hit)[0]:
        problems.append("nothing new landed: no jolt")
    if not all(0.0 <= K.breath_phase(16, t / 10.0) <= 1.0 for t in range(60)) or K.breath_phase(0, 3) != 0:
        problems.append("the breath should run between out and in")
    if K.Image is not None:
        img = K.Image.new("RGBA", (120, 120), (0, 0, 0, 0))
        K.ImageDraw.Draw(img).rectangle((40, 30, 80, 100), fill=(200, 120, 60, 255))
        b = K.breathe_image(img, (40, 30, 81, 101), 0.05)
        g = K.grey_image(img, 0.9)
        if b.size != img.size or g.size != img.size or b.getchannel("A").getbbox()[3] != 101:
            problems.append("breathing should keep her feet where they are and the picture its size")
        px = g.getpixel((60, 60))
        if not (abs(px[0] - px[2]) < abs(200 - 60) * 0.4 and px[3] == 255):
            problems.append(f"the grey should take the colour out of her and keep her outline: {px}")
    # narration.settling_in
    s = H.session(3, fighters="Seraphina,Ripples")
    e = s.eng
    rp = e.get("Ripples")
    foot = next(p for p in rp.parts.values() if p.name == "Left Foot")
    foot.damage = 80
    e.turn = 5
    e.__dict__.setdefault("hit_turn", {})["Ripples|Left Foot"] = 3
    t1 = e.settling_text()
    if not ("left foot" in t1 and "hitch" in t1 and "beat 3" in t1):
        problems.append(f"a foot hit two beats ago should come on in the notes: {t1!r}")
    if e.settling_text() != t1:
        problems.append("the same beat (a reroll) should give the same settling-in notes")
    e.turn = 6
    if "left foot" in e.settling_text():
        problems.append("a step already told should not be told again")
    foot.damage = 170
    e.turn = 7
    if "favors" not in e.settling_text():
        problems.append("the next step should be told once it is that bad")
    e.turn = 8
    e.__dict__["hit_turn"]["Ripples|Left Foot"] = 8
    foot.damage = 400
    if "left foot" in e.settling_text():
        problems.append("a part hit this beat has nothing settling in yet")
    e.turn, e.__dict__["hit_turn"]["Ripples|Left Foot"] = 10, 8
    e.knock_down("Ripples", facing="on her side", why="test")
    t3 = e.settling_text()
    if "weight" in t3 or "barely moving" not in t3:
        problems.append(f"lying down, a leg settling in should not be told by her weight on it: {t3!r}")
    e.rules["narration"]["settling_in"]["enabled"] = False
    if e.settling_text():
        problems.append("narration.settling_in false should give no notes")
    import play
    snap = play.fight_snapshot(s)
    if not all("heart_rest" in x for x in snap["fighters"]):
        problems.append("the snapshot should carry each fighter's resting heart rate")
    # /effects: each piece, or all of them, on and off
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        play.handle_command(s, "/effects grey off")
        play.handle_command(s, "/effects")
    al = e.rules["window"]["alive"]
    if al["grey_in"] is not False or al["breathing"] is not True or "grey off" not in out.getvalue():
        problems.append(f"/effects grey off should turn only the grey off and say so: {out.getvalue()!r}")
    with contextlib.redirect_stdout(io.StringIO()):
        play.handle_command(s, "/effects off")
    if al["enabled"] or al["heart_monitor"] or e.rules["narration"]["settling_in"]["enabled"]:
        problems.append("/effects off should turn every effect off, the settling-in notes too")
    with contextlib.redirect_stdout(io.StringIO()):
        play.handle_command(s, "/effects on")
    if not (al["enabled"] and al["grey_in"] and e.rules["narration"]["settling_in"]["enabled"]):
        problems.append("/effects on should turn them all back on")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            play.handle_command(s, "/effects sparkles off")
        problems.append("/effects with an unknown effect should say what it takes")
    except ValueError:
        pass
    return problems


def narration_305_check():
    """Build 305 (from the Seraphina vs Ripples submission fight): a black-out that counts as one tap of several must
    be shown; being borne down in a hold must be shown, and it keeps her down while the grip is on; the present tense
    in plural, "can" and "and ..." forms is caught and mended; a feature given to the wrong fighter by "Her ..."
    and "tails" for a one-tailed fighter are caught; her free-arm lines go while her arms are pinned; thoughts lose
    their "voice", stay in her present, aren't said twice or by the other fighter; italic narration is made plain;
    a note's label in brackets goes; a head strike in a tail-blow beat is caught."""
    import narrator as N
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    e, n = s.eng, s.narrator
    n.strengths = {"Seraphina": 90, "Ripples": 60}
    # a counted black-out: _shown_out now checks the fighter named, not only one fainting for good
    n._faint = None
    if n._shown_out("The coils loosened and the relief was dizzying.", "Ripples"):
        problems.append("a black-out that counts as one tap should have to be shown")
    if not n._shown_out("Ripples went limp in the coils, gone for a long moment.", "Ripples"):
        problems.append("a black-out told should count as shown")
    if not all(N.BORNE_DOWN.search(t) for t in ("Seraphina pressed her down onto the ground.",
                                                 "Ripples was borne down, her legs folding under her.")) \
            or N.BORNE_DOWN.search("She fought to stay upright."):
        problems.append("being borne down in a hold should be recognised when told")
    # borne down in a plain grip: no get-up while it holds
    e.rules["finish"]["submission"]["enabled"] = True
    e.start_submission("Seraphina", "Ripples", "upright coil")
    for h in e.holds.values():
        h.sub = ""
    hid = min(e.holds)
    rp = e.get("Ripples")
    rp.learned["sub_stage"] = {"hold": hid, "at": 1}
    e.knock_down("Ripples", facing="sitting up", why="test")
    e.downed["Ripples"] = 3
    if any(x.get("fighter") == "Ripples" for x in e.get_up_tick() if x.get("type") == "get_up"):
        problems.append("a fighter borne down in a grip shouldn't get up while it holds her")
    # present tense
    txt = ("The coils around Ripples tighten with a slow pressure, the weight behind every squeeze. She can see Ripples "
           "breathing in tiny, careful sips. She leaned in close, her forehead nearly touching Ripples' fur, and works by "
           "feel. Her paw shook hard and nearly gets there, but she forced it back. Her body jerks inside the coils. "
           "Her paws scrabble for purchase. Her legs would shake if she let them.")
    flagged = [x for x, w in n._bad_sentences(txt).items() if "present tense" in str(w)]
    fixed = n._past_words(txt, flagged)
    for want in ("tightened", "could see", "worked by feel", "nearly got there", "body jerked", "scrabbled",
                 "would shake"):
        if want not in fixed:
            problems.append(f"the present tense should be mended ({want}): {fixed[:200]}")
            break
    # body: "Her antennae" after a sentence about Ripples; "her tails" for one-tailed Seraphina
    n.damage_by = {"Ripples": {p: 0 for p in rp.parts}, "Seraphina": {p: 0 for p in e.get("Seraphina").parts}}
    n._hurt_now = {}
    n._calm_beat = False
    bad = dict(n._log_slips("Ripples was bent nearly double over her stomach. Her antennae drooped, a sure sign of pain. "
                            "Seraphina's coils tightened. Her tails hung low behind her."))
    if not any("antennae" in str(w) for w in bad.values()) or not any("ONE tail" in str(w) for w in bad.values()):
        problems.append(f"a feature on the wrong fighter and tails on a one-tailed one should be caught: {bad}")
    # pinned arms: no free-arm lines, and the slips caught
    n._trapped = {"Ripples"}
    n.__dict__.pop("_feats_cache", None)
    if "arms" in n._blk_feats("Ripples"):
        problems.append("a fighter with her arms pinned in coils should get no lines that need her arms")
    if not N.TRAPPED_PAWS.search("She locked her free paw round her own ankle and held herself shut."):
        problems.append("a free paw with her arms pinned should be caught")
    # thoughts
    t = ("— Seraphina —\n\nThe sound was loud. *This time, I'll not be gentle.*\n\n*Not finished. Not yet.*\n\n"
         "*Not finished.*\n\n*I needed to finish this soon,* she thought, her voice a low, resonant hum.\n\n"
         "— Ripples —\n\nShe felt the ache. *This time, I won't be gentle.* The thought echoed through her mind.\n\n"
         "*The world narrowed to the pressure points, the sharp, grinding ache in her stomach and chest, and the "
         "coils.*")
    m_ = N._mend_thoughts(N._unitalic_narration(t, ["Seraphina", "Ripples"]))
    if "her voice" in m_ or "I need to finish" not in m_ or m_.count("gentle") != 1 or m_.count("Not finished") != 1 \
            or "*The world" in m_ or "echoed" in m_:
        problems.append(f"thoughts should be mended: {m_}")
    lo = N.Narrator._mend_leftovers(n, "She braced (her stomach) hard. It hurt (a glancing squeeze, still minor). "
                                       "A yelp tore out of her (Yaaiip—).")
    if "(her stomach)" in lo or "still minor" in lo or "(Yaaiip—)" not in lo:
        problems.append(f"a note's label in brackets should go, a sound in brackets stay: {lo}")
    if not N.HEAD_STRIKE.search("She snapped her head forward, striking Ripples' jaw with brutal force."):
        problems.append("a head strike should be recognised")
    return problems


def save_history_check():
    """Build 301: a saved fight loads back whole: its beat records (the window's history: the start, each beat's text
    and numbers), its story and every number, and its /undo history, back to the start of the fight."""
    problems = []
    s = H.session(5, fighters="Nocturne,Ripples")
    for mv in ("Night Slash", "Bite", "Night Slash"):
        H.beat(s, [{"attacker": "Nocturne", "defender": "Ripples", "action": "strike", "move": mv, "part": "Chest"}], [])
    labels = [r["label"] for r in s.beat_records if r["fight"] == s.fight_no]
    if not labels or labels[0] != "the start":
        problems.append(f"a fight's beat history should begin with the start, before the first blow: {labels}")
    path = os.path.abspath("save_history_check.json")
    s.eng.save(path, s._extra())
    s2 = H.session(9, fighters="Nocturne,Ripples")
    s2.load(path)
    if [r["label"] for r in s2.beat_records] != [r["label"] for r in s.beat_records] or s2.story != s.story:
        problems.append("a loaded fight should have its beat history and its story back")
    if [round(f.health, 2) for f in s2.eng.fighters.values()] != [round(f.health, 2) for f in s.eng.fighters.values()]:
        problems.append("a loaded fight should have every number back")
    if len(s2.history) != len(s.history):
        problems.append(f"a loaded fight should keep its /undo history: {len(s2.history)} of {len(s.history)}")
    for _ in range(3):
        s2.undo()
    if s2.eng.turn != 0 or any(f.health < f.max_health for f in s2.eng.fighters.values()) \
            or [r["label"] for r in s2.beat_records] != ["the start"]:
        problems.append(f"undoing a loaded fight should go back to its start: turn {s2.eng.turn}, "
                        f"{[r['label'] for r in s2.beat_records]}")
    return problems


def compression_check():
    """Build 294: compression in a constriction: it builds beat by beat (more when she fights it), drives the blood
    gauge, makes the coils harder to break, tells the chest and the belly apart in the story, and never brings
    nausea."""
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    e = s.eng
    e.rules["finish"]["submission"]["enabled"] = True
    e._hold_break_tick = lambda *a, **k: []
    e.start_submission("Seraphina", "Ripples", "upright coil")
    comps = []
    for _ in range(5):
        e.turn += 1
        ev = e.beat()
        c = next((x for x in ev if x["type"] == "constriction"), None)
        if c:
            comps.append(c["compress"])
    if len(comps) < 4 or comps != sorted(comps) or comps[0] >= comps[-1] or comps[-1] > 92:
        problems.append(f"the squeeze should build beat by beat, up to its max: {comps}")
    if not c or c.get("where") != "chest":
        problems.append(f"coils on her chest are told as her chest: {c}")
    n = s.narrator
    chest = n._squeeze_words(70, "chest", "Ripples", "Seraphina", True)
    belly = n._squeeze_words(70, "belly", "Ripples", "Seraphina", False)
    if "heart" not in chest or "from below" not in belly or "took up" not in chest or "keeping still" not in belly:
        problems.append(f"the chest and the belly read differently: {chest!r} {belly!r}")
    if e.compression_on(e.get("Ripples"), "Seraphina") <= 0:
        problems.append("compression_on should give the squeeze while the coils are on")
    # build 296 (compression.ring): a coil goes all the way round her, front, sides and back
    rp = e.get("Ripples")
    if e.coil_ring(rp, "Left Flank") != ("belly", ["Stomach", "Left Flank", "Right Flank", "Lower Back"]) or \
            e.coil_ring(rp, "Upper Back") != ("chest", ["Chest", "Left Ribs", "Right Ribs", "Upper Back"]):
        problems.append(f"a coil should touch the whole band: {e.coil_ring(rp, 'Left Flank')} {e.coil_ring(rp, 'Upper Back')}")
    if c and set(c.get("ring_parts") or ()) != {"Chest", "Left Ribs", "Right Ribs", "Upper Back"}:
        problems.append(f"the constriction event names every part the coil lies on: {c and c.get('ring_parts')}")
    rw = n._squeeze_words(70, "belly", "Ripples", "Seraphina", False, ["Stomach", "Left Flank", "Right Flank", "Lower Back"])
    if "both her flanks" not in rw or "lower back" not in rw or "all the way round" not in rw:
        problems.append(f"the story should name her flanks and back too: {rw!r}")
    # build 297 (compression.ring_wear): the coil wears the rest of the band too
    worn = {p for p in ("Left Ribs", "Right Ribs", "Upper Back") if rp.parts[p].damage > 0}
    if worn != {"Left Ribs", "Right Ribs", "Upper Back"}:
        problems.append(f"a coil round her chest should wear her ribs and upper back too: {worn}")
    # build 297 (holds.coil.wear_first): on a sound part a coil wears more than it hurts; on a worn one it bites fully
    wf = e.rules["holds"]["coil"]["wear_first"]
    e.rng.seed(1)
    sound = e._apply_damage(rp, "Stomach", 20, wear_first=wf)
    rp.parts["Lower Back"].resistance = 5
    e.rng.seed(1)
    worn_hit = e._apply_damage(rp, "Lower Back", 20, wear_first=wf)
    e.rng.seed(1)
    plain = e._apply_damage(rp, "Left Flank", 20)
    if not (sound["damage_taken"] < 0.2 * plain["damage_taken"] and worn_hit["damage_taken"] > plain["damage_taken"]) \
            or sound["res_before"] - sound["res_after"] <= plain["res_before"] - plain["res_after"]:
        problems.append(f"a coil should wear a sound part more and hurt it far less, and bite a worn one fully: "
                        f"{sound['damage_taken']} {plain['damage_taken']} {worn_hit['damage_taken']}")
    # build 298 (holds.coil.energy): coils cost the coiler, a spent one lets go, and one who can feel the end hangs on
    s2 = H.session(4, fighters="Seraphina,Ripples")
    e2 = s2.eng
    e2.rules["finish"]["submission"]["enabled"] = True
    e2._hold_break_tick = lambda *a, **k: []
    e2.rules["holds"]["endurance"]["coil_energy_mult"] = 1.0    # (build 308's cheaper coils: tested at full cost here)
    e2.start_submission("Seraphina", "Ripples", "upright coil")
    sr2 = e2.get("Seraphina")
    sr2.energy = 12
    spent = hung = False
    for _ in range(4):
        e2.turn += 1
        ev2 = e2.beat()
        spent = spent or any(x["type"] == "hold_end" and x.get("spent") for x in ev2)
    if not spent or any(h.coil for h in e2.holds.values()):
        problems.append("a coiler with no energy left should have to let go")
    s3 = H.session(4, fighters="Seraphina,Ripples")
    e3 = s3.eng
    e3.rules["finish"]["submission"]["enabled"] = True
    e3._hold_break_tick = lambda *a, **k: []
    e3.rules["holds"]["coil"]["energy"]["hang_on"] = 1.0
    e3.start_submission("Seraphina", "Ripples", "upright coil")
    e3.get("Seraphina").energy = 3
    e3.get("Ripples").health = e3.get("Ripples").max_health * 0.1
    e3.turn += 1
    hung = any(x["type"] == "coil_hang_on" for x in e3.beat())
    if not hung or not any(h.coil for h in e3.holds.values()):
        problems.append("a spent coiler who can feel the end coming should be able to hang on")
    import play as _play
    rp3 = e3.get("Ripples")
    rp3.energy = 40
    _play.handle_command(s3, "/energy Ripples 25")
    _play.handle_command(s3, "/energy Ripples -5")
    if round(rp3.energy) != 60:
        problems.append(f"/energy should add and take away energy: {rp3.energy}")
    _play.handle_command(s3, "/energy Ripples =100")
    if round(rp3.energy) != 100:
        problems.append(f"/energy =n should set it: {rp3.energy}")
    import cards
    # build 299 (window.squeeze_figure): the squeeze as a body, loops as thick as the coiler is big, a beating heart
    if not c or c.get("coiler") != "Seraphina" or not (c.get("coil_ratio") or 0) > 3:
        problems.append(f"the constriction should say who coils her and how much bigger: {c and c.get('coil_ratio')}")
    # build 300: real-world numbers for the squeeze, and her healthy ones to read them against
    if not c or not c.get("pressure") or not c.get("girth") or c["girth"][1] >= c["girth"][0] \
            or not c.get("heart_rest") or c.get("bp_rest") != [120, 80]:
        problems.append(f"the constriction should give the coil pressure, her girth and her normal numbers: "
                        f"{c and {k: c.get(k) for k in ('pressure', 'girth', 'heart_rest', 'bp_rest')}}")
    rp_ = e.get("Ripples")
    if not (e.squeeze_numbers(rp_, 80, 6.2, 0.7)["pressure"] > e.squeeze_numbers(rp_, 80, 0.7, 0.7)["pressure"]
            > e.squeeze_numbers(rp_, 30, 0.7, 0.7)["pressure"]):
        problems.append("the coils should press harder the bigger the coiler and the tighter the squeeze")
    rd = cards.squeeze_readout(dict(c or {}, squeeze=70, where="chest"), 0, 0, 200) if c else []
    if not any(sh[0] == "text" and "normal" in sh[3] for sh in rd):
        problems.append("the squeeze readout should show her normal numbers")
    # build 302: how close she is to blacking out, and to her heart stopping
    if not c or not 0 < int(c.get("out_at") or 0) < 100:
        problems.append(f"the constriction should say where her limit is on the blood-flow gauge: {c and c.get('out_at')}")
    early = cards.blackout_text({"blood": 20, "out_at": 60, "out_chance": 0, "stop_chance": 0})[0]
    late = cards.blackout_text({"blood": 70, "out_at": 60, "out_chance": 0.3, "stop_chance": 0.105})[0]
    gone = cards.blackout_text({"stopped": True, "out_at": 60})[0]
    if "40%" not in early or "30%" not in late or "10%" not in late or "stopped" not in gone:
        problems.append(f"the black-out line should say how far off it is, then the chances: {early!r} {late!r} {gone!r}")
    vo = e._vitals_with_odds(e.get("Ripples"), 0.4)
    if vo is not None and abs(vo.get("stop_chance", 0) - 0.4 * 0.35) > 1e-6:
        problems.append(f"the heart-stop chance is the black-out chance x heart_stop.chance: {vo}")
    # build 304: the grips on her as a picture, by what each does to her
    kinds = {cards.grip_kind(g) for g in (
        {"what": "standing sleeper", "parts": ["Neck"]}, {"what": "full nelson", "parts": ["Neck", "Left Shoulder"]},
        {"what": "hammerlock", "parts": ["Left Upper Arm"]}, {"what": "bear hug", "parts": ["Chest"]},
        {"what": "side headlock", "parts": ["Head"]}, {"what": "grab", "parts": ["Left Paw"]},
        {"what": "coils", "parts": ["Left Thigh"]})}
    if kinds != {"choke", "lock", "crush", "head", "grab", "bound"}:
        problems.append(f"each kind of grip should be told apart: {kinds}")
    fh = {"parts": [("Left Upper Arm", 60, 80)], "grips": {"held": [{"by": "Nerine", "what": "hammerlock",
          "parts": ["Left Upper Arm"], "beats": 2}], "pin": {"by": "Nerine", "seconds": 10, "of": 60},
          "tap": {"by": "Nerine", "pain": 300, "resist": 200, "chance": 0.2}}}
    shp, _ = cards.hold_shapes(fh, 0, 0, 90, 150, 100, 300)
    texts = " ".join(x[3] for x in shp if x[0] == "text")
    if "Hammerlock by Nerine" not in texts or "Pinned by Nerine" not in texts or "past what she can bear" not in texts \
            or "<svg" not in cards.shapes_svg(shp, 400, 160):
        problems.append(f"the hold picture should name each grip, its gauge and a pin: {texts}")
    if cards.hold_shapes({"parts": [], "grips": {"held": [{"by": "S", "what": "coils", "parts": ["Chest"]}]}},
                         0, 0, 90, 150, 100, 300)[0]:
        problems.append("coils round her body have the squeeze picture, not the hold picture")
    giant = cards.squeeze_figure(70, "both", 1, 0, 0, 80, 120, ratio=8.9)
    same = cards.squeeze_figure(70, "both", 1, 0, 0, 80, 120, ratio=1.0)
    if not (len(giant["loops"]) < len(same["loops"])) or "trail" in giant:
        problems.append(f"a giant coiler should wind fewer, thicker loops, only the coils drawn: {len(giant['loops'])} "
                        f"{len(same['loops'])}")
    loose, tight = (cards.squeeze_figure(q, "chest", 1, 0, 0, 80, 120) for q in (5, 90))
    if not (max(x for x, _ in tight["body"]) < max(x for x, _ in loose["body"]) and tight["ribs"] and not loose["ribs"]):
        problems.append("a hard squeeze should press her in and show her ribs")

    def _span(hs):
        return max(x for x, _ in hs["heart"]) - min(x for x, _ in hs["heart"])
    free = cards.heart_shapes(0, 0, 20, 80, False, 0)
    pressed = cards.heart_shapes(0, 0, 20, 80, True, 0)
    drained = cards.heart_shapes(0, 0, 20, 0, False, 90)
    beating = cards.heart_shapes(0, 0, 20, 0, False, 0, beat=1.0)
    if not (_span(pressed) < _span(free) and pressed["press"] and not free["press"] and _span(drained) < _span(free)
            and _span(beating) < _span(free)):
        problems.append("her heart should flatten between coils on her chest, shrink as it fills less, clench on a beat")
    if cards.heart_beat(0, 1.3) != 0 or max(cards.heart_beat(60, t / 100) for t in range(200)) < 0.9:
        problems.append("a stopped heart stays still; a beating one clenches")
    vv = {"heart": 90, "squeeze": 70, "where": "chest", "coils": 1, "blood": 40, "coiler": "Seraphina", "coil_ratio": 8.9}
    if "animateTransform" not in cards.squeeze_svg(vv) or "animateTransform" in cards.squeeze_svg(dict(vv, stopped=True)):
        problems.append("the exported heart should beat, and not once it has stopped")
    _, body_box, coil_boxes = cards.squeeze_shapes(60, 1, 0, 100, 0, 10, ring=True)
    if not any(b[1] == 0 and b[2] - b[0] == 100 for b in coil_boxes) or body_box[1] <= 1:
        problems.append(f"the bar should draw the coils across her front and back too: {coil_boxes}")
    import json as _json
    if "nause" in open("rules.json", encoding="utf-8").read().lower().replace("nauseous", "nause") and \
            ("nausea" in str(e.rules["finish"]["submission"]["constriction"]) or "nauseous" in str(e.rules["moves"]["body_jolts"])):
        problems.append("no nausea, from the coils or a blow")
    return problems


def head_body_check():
    """Build 293: head effects (rattled, dazed, stunned and its wobbly legs, seeing double, watering eyes, ringing
    ears, a rattled jaw, whiplash, concussed), body effects (dead leg, limp, dead arm, aching ribs, back spasm, numb
    tail, a swelling eye), what they do, the director's stunned fighter swaying, the heartbeat words for the
    story, and a heart that stops in a constriction blackout and starts again."""
    import collections, cards, director as D
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    e = s.eng
    r, sr = e.get("Ripples"), e.get("Seraphina")
    blunt, cut = collections.Counter(), collections.Counter()
    for i in range(300):
        for mv, cnt in (({"name": "Iron Tail", "about": ""}, blunt), ({"name": "Night Slash", "about": ""}, cut)):
            r.status.clear()
            r.learned.pop("head_jolts", None)
            for x in e._jolts(r, [{"defender": "Ripples", "part": "Jaw", "damage_taken": 60, "damage_after": 60}], mv, sr):
                cnt[x["status"]] += 1
    if not blunt["stunned"] or blunt["stunned"] <= cut["stunned"] or not blunt["jaw_rattled"]:
        problems.append(f"a blunt blow to the jaw should stun more than a cut, and rattle the jaw: {blunt} {cut}")
    if not blunt["wobbly"] or blunt["wobbly"] != blunt["stunned"]:
        problems.append(f"every stun leaves her legs gone: {blunt}")
    r.status.clear()
    e.set_status(r, "stunned", 1)
    if e.dodge_chance(sr, r) > 0:
        problems.append("a stunned fighter can't dodge")
    try:
        e._can_act(r, True)
        problems.append("a stunned fighter can't act")
    except ValueError:
        pass
    r.status.clear()
    body = collections.Counter()
    for i in range(300):
        r.status.clear()
        for x in e._jolts(r, [{"defender": "Ripples", "part": "Left Thigh", "damage_taken": 60, "damage_after": 100},
                              {"defender": "Ripples", "part": "Left Ribs", "damage_taken": 60, "damage_after": 130},
                              {"defender": "Ripples", "part": "Stomach", "damage_taken": 60, "damage_after": 200}],
                          {"name": "Iron Tail", "about": ""}, sr):
            body[x["status"]] += 1
    for st in ("dead_leg", "ribs_aching"):
        if not body[st]:
            problems.append(f"no {st} from a hard blow there: {body}")
    e.set_status(r, "back_spasm", 2)
    if not any("spasm" in lbl for lbl, _ in e.power_extras(r, sr, "Normal", {"name": "Aqua Jet"})):
        problems.append("a back spasm should weaken her blows")
    e.rules["moves"]["head"]["enabled"] = False
    e.rules["moves"]["body_jolts"]["enabled"] = False
    r.status.clear()
    for i in range(50):
        for x in e._jolts(r, [{"defender": "Ripples", "part": "Left Thigh", "damage_taken": 60, "damage_after": 100}],
                          {"name": "Iron Tail", "about": ""}, sr):
            if x["status"] == "dead_leg":
                problems.append("moves.body_jolts.enabled false = no body effects")
                break
    # the heart in a constriction: words for the story, and the stop
    s2 = H.session(4, fighters="Seraphina,Ripples")
    e2 = s2.eng
    e2.rules["finish"]["submission"]["enabled"] = True
    e2.rules["finish"]["submission"]["constriction"]["heart_stop"]["chance"] = 1.0
    e2._hold_break_tick = lambda *a, **k: []
    e2.start_submission("Seraphina", "Ripples", "upright coil")
    out = None
    for _ in range(30):
        e2.turn += 1
        ev = e2.beat()
        out = next((x for x in ev if x["type"] == "tap_out"), None)
        if out:
            break
    if not out or out["how"] != "pass_out" or not out.get("heart_stopped"):
        problems.append(f"with heart_stop.chance 1 a constriction blackout stops her heart: {out}")
    else:
        m = cards.tap_meter({"grips": e2.card_state(e2.get("Ripples"))})
        if not m or not (m.get("vitals") or {}).get("stopped") or len(cards.ecg_points(0, False, 100, 20)) != 2:
            problems.append(f"the card should show the stopped heart, a flat trace: {m}")
    return problems


def orders_check():
    """Build 292 (the user's log): a player's order read right. "I headbutt Ripples' head four times and then squeeze
    even tighter" keeps the headbutts and tightens the coils she already has (it had become a grip on her head, and no
    headbutt was thrown); the word lists are fuller; and the prose checks for a constriction told as her air, her
    heart slowing while it races, and a body part she doesn't have."""
    import director as D
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    e = s.eng
    e.start_holds("Seraphina", "Ripples", [("Stomach", 8, 0, "her coils"), ("Upper Back", 8, 0, "her coils")], "coils")
    acts = [{"action": "combo", "attacker": "Seraphina", "defender": "Ripples", "move": "Dragon Rush",
             "hits": [{"part": "Head"}] * 4, "flavor": "headbutts"}]
    got = D.apply_players(e, acts, {"Seraphina": "I headbutt Ripples head four times and then squeeze even tighter."})
    if [b["action"] for b in got] != ["combo", "hold_adjust"]:
        problems.append(f"the headbutts and a tightening: {[b['action'] for b in got]}")
    for o, want in (("I squirm and try to wriggle free", "A"), ("I lie still and let her squeeze", "P"),
                    ("I relax and catch my breath", "P"), ("I tighten my coils", "G"), ("I slam her into the oak", "A"),
                    ("I bite her tail", "A"), ("I clamp down on her neck", "G")):
        rx = {"A": D.ACTIVE_ORDER, "P": D.PASSIVE_ORDER, "G": D.GRIP_ORDER}[want]
        if not rx.search(o):
            problems.append(f"{o!r} should read as {want}")
    n = s.narrator
    n.strengths = {"Seraphina": 100, "Ripples": 90}
    n.damage_by = {f.name: {p.lower(): 0 for p in f.parts} for f in e.fighters.values()}
    n.plans = {"Seraphina": "serpent", "Ripples": "biped"}
    n.coats = {"Seraphina": "scales", "Ripples": "fur"}
    n._hurt_now, n._calm_beat = set(), False
    n._circ_on, n._circ_stage = {"Ripples"}, {"Ripples": "pounding"}
    n.grips = [("Seraphina", "Ripples", "stomach", "her coils")]
    for sent, want in (("Ripples' antennae drooped, flat against her neck.", "gives Ripples antennae"),
                       ("Seraphina's fur bristled.", "gives Seraphina fur"),
                       ("The coils tightened again, cutting off Ripples' air supply.", "BLOOD"),
                       ("Ripples felt her pulse slowed to a throb.", "RACING")):
        if not any(want in str(x) for x in n._log_slips(sent)):
            problems.append(f"{sent!r} should be caught ({want})")
    for sent in ("Ripples' ears flattened.", "Seraphina's scales flared.", "Ripples' twin tails lashed."):
        if n._log_slips(sent):
            problems.append(f"{sent!r} is fine: {n._log_slips(sent)}")
    return problems


def speed_check_check():
    """Build 286: when part of the narrator model runs in system memory, the player is told once, with what helps."""
    import io, contextlib
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    real = H.llm.loaded
    try:
        H.llm.loaded = lambda host, model: (16 * 2**30, 12 * 2**30)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            s._speed_check()
            s._speed_check()
        if out.getvalue().count("system memory") != 1 or "OLLAMA_KV_CACHE_TYPE" not in out.getvalue():
            problems.append(f"25% in system memory should be said once, with what helps: {out.getvalue()[:200]!r}")
        H.llm.loaded = lambda host, model: (16 * 2**30, 16 * 2**30)
        s._offload_said = 0.0
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            s._speed_check()
        if out.getvalue():
            problems.append("all of it on the graphics card: nothing to say")
    finally:
        H.llm.loaded = real
    return problems


def constriction_check():
    """Build 283: coils round her body put her out by her blood, as a real constriction does: the stages in order
    (her heart pounding, then slowing, then the grey), rough heart and blood-pressure numbers rising and then
    falling, a blackout told as the blood, the tap meter counting blackouts, and the switch."""
    import cards
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    e = s.eng
    e.rules["finish"]["submission"]["enabled"] = True
    e._hold_break_tick = lambda *a, **k: []
    e.start_submission("Seraphina", "Ripples", "upright coil")
    stages, hearts, out, meters = [], [], None, []
    for _ in range(30):
        e.turn += 1
        ev = e.beat()
        c = [x for x in ev if x["type"] == "constriction"]
        if c:
            stages.append(c[0]["stage"])
            hearts.append(c[0]["heart"])
        m = cards.tap_meter({"grips": e.card_state(e.get("Ripples"))})
        if m:
            meters.append(m)
        out = next((x for x in ev if x["type"] == "tap_out"), None)
        if out or not e.holds:
            break
    order = ["pounding", "slowing", "greying"]
    if not stages or [order.index(x) for x in stages] != sorted(order.index(x) for x in stages) or "slowing" not in stages:
        problems.append(f"the stages should run pounding, slowing, greying and never back: {stages}")
    if len(hearts) < 4 or max(hearts) <= hearts[0] or hearts[-1] >= max(hearts):
        problems.append(f"her heart should race first and then slow: {hearts}")
    if not out:
        problems.append("a long constriction should end the match")
    elif out["how"] == "pass_out" and out.get("cause") != "constriction":
        problems.append(f"a blackout in body coils is the constriction's: {out}")
    # (since build 287 drawn, not written: the vitals strip; since build 289 from the hold's first beat)
    if not meters or not meters[0].get("vitals"):
        problems.append(f"the vitals strip should show from the coil's first beat: {meters[:1]}")
    vs = [m["vitals"] for m in meters if m.get("vitals")]
    if not vs or not all(k in vs[-1] for k in ("heart", "bp", "blood")) or any("heart about" in m["note"] for m in meters):
        problems.append(f"the tap meter should carry her heart, blood pressure and blood flow for the strip: {vs[-1:]}")
    pts = cards.ecg_points(60, False, 200, 20)
    if len(pts) < 10 or len(cards.ecg_points(180, False, 200, 20)) <= len(pts):
        problems.append("a faster heart should draw more beats in the trace")
    import fightexport
    fs = {f["name"]: f for f in H.play.fight_snapshot(s)["fighters"]}
    import narrator as N
    n = s.narrator
    lines = "\n".join(N.Narrator.CONSTRICT_STAGE.values())
    if "choke" not in lines or "SLOW" not in lines:
        problems.append("the constriction's notes should say it is the blood, not a choke, and the heart slowing")
    n._circ_on = {"Ripples"}
    off = n._choke_off_lines("Ripples", ["Chest"])
    if not off or "blood comes back" not in off[0]:
        problems.append(f"the coils coming off should bring her blood back: {off}")
    # (the user's log) a serpent "standing tall" in a sentence naming both of them, and her "stance"
    n.strengths = {"Seraphina": 100, "Ripples": 80}
    n.plans = {"Seraphina": "serpent", "Ripples": "biped"}
    n._hurt_now, n._calm_beat = set(), False
    slips = [str(x) for x in n._log_slips("Seraphina stood tall and unyielding, her red eyes locked onto Ripples.")]
    if not any("serpent" in x for x in slips):
        problems.append(f"a serpent standing tall beside another's name should be caught: {slips}")
    import blocks
    b = s.narrator.blocks if getattr(s.narrator, "blocks", None) else None
    if N.FOOTWORK_THOUGHT.search("*Make her turn. She hates turning.*") is None:
        problems.append("a footwork thought should be kept from two fighters locked in a hold")
    e2 = H.session(3, fighters="Seraphina,Ripples").eng
    e2.rules["finish"]["submission"]["enabled"] = True
    e2.rules["finish"]["submission"]["constriction"]["enabled"] = False
    e2.start_submission("Seraphina", "Ripples", "upright coil")
    e2.turn += 1
    if any(x["type"] == "constriction" for x in e2.beat()):
        problems.append("constriction.enabled false = no constriction")
    return problems


def tap_meter_check():
    """Build 283 (the user's window): the tap meter follows this beat's real chance, not how the pain feels: past what
    she can bear at 0.3% it doesn't read "at the edge of tapping", and it says what keeps the chance down."""
    import cards
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    e = s.eng
    e.rules["finish"]["submission"]["enabled"] = True
    e.rules["finish"]["submission"]["constriction"]["enabled"] = False     # (the pain alone here)
    e.start_submission("Seraphina", "Ripples", "upright coil")
    for p in ("Chest", "Left Hip"):
        e.get("Ripples").parts[p].damage = 150
    for _ in range(3):
        e.turn += 1
        e.beat()
    r = e.get("Ripples")
    m = cards.tap_meter({"grips": e.card_state(r)})
    if not m or m["level"] > 2 or "edge" in m["label"] or "kept down by" not in m["note"] \
            or "past what she can bear" not in m["note"]:
        problems.append(f"a tiny chance past her limit should read far off and say why: {m}")
    line = cards.grip_lines({"grips": e.card_state(e.get("Seraphina"))})[0][0]
    if "edge" in line or " 0% to tap" in line:
        problems.append(f"the holder's line should give the real small chance: {line}")
    if cards.chance_level(0) != 0 or cards.chance_level(0.3) != 1 or cards.chance_level(30) != 4 \
            or cards.chance_level(60) != 5 or cards.pct_text(0.28) != "0.3%":
        problems.append("the chance steps or the percentage text are off")
    e.rules["window"]["hold_panel"]["meter_by"] = "pain"
    if "edge" not in cards.tap_meter({"grips": e.card_state(r)})["label"]:
        problems.append("meter_by pain keeps the pain ladder")
    return problems


def unrolled_blows_check():
    """Build 283 (the user's log): a submission whose words whip her and charge her into a pine the engine never
    resolved loses those words; a coil's own words stay."""
    import director as D
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    e = s.eng
    f = ("A massive wave of power and motion as Seraphina whips Ripples with the tail, and charges her into a tall "
         "pine, then presses her into the beach and the pine tree, before")
    if D._unrolled_words(e, "submission", "Seraphina", f) != "":
        problems.append(f"a submission's unresolved blows should go: {D._unrolled_words(e, 'submission', 'Seraphina', f)!r}")
    got = D._unrolled_words(e, "hold", "Seraphina", "her coils wound round Ripples, then she slams her into the oak")
    if got != "her coils wound round Ripples":
        problems.append(f"a hold keeps its grip and loses the slam: {got!r}")
    if D._unrolled_words(e, "hold", "Seraphina", "jaws clamped on her neck, biting hard") != "jaws clamped on her neck, biting hard":
        problems.append("a jaw hold's biting is its grip, not a blow")
    e.rules["holds"]["unrolled_words"]["blows"] = False
    if D._unrolled_words(e, "submission", "Seraphina", f) != f:
        problems.append("holds.unrolled_words.blows false keeps the words")
    return problems


def character_check():
    """Build 281: who each fighter is in the story (narration.character): personality, history and relationships in
    the narrator's notes and in the polishing model's facts; a quirk that decides something is told to the story;
    a veteran's memory of past fights is kept, anyone else's is cut; /profile lists it all."""
    import play
    import narrator as N
    import polish
    problems = []
    s = H.session(3, fighters="Ripples,Nerine")
    e = s.eng
    note = s.notes()
    for want in ("PERSONALITY: Eager", "HISTORY", "NERINE TO HER:", "RIPPLES TO HER:"):
        if want not in note:
            problems.append(f"the narrator's notes should have {want!r}")
    facts = s.polish_facts([], [], [])
    if not any(f.startswith("CHARACTER: Ripples") for f in facts):
        problems.append(f"the polishing model should get each fighter's CHARACTER line: {facts[:3]}")
    msgs = polish.messages("draft", facts)
    if "Give her thoughts, her manner" not in msgs[1]["content"]:
        problems.append("the polishing request should say what to do with the CHARACTER lines")
    e.rules["narration"]["character"]["enabled"] = False
    if "PERSONALITY" in s.notes():
        problems.append("with narration.character off, no personality in the notes")
    e.rules["narration"]["character"]["enabled"] = True
    e._quirks_now = []
    with contextlib.redirect_stdout(io.StringIO()):
        e.start_hold("Nerine", "Ripples", "Left Upper Arm", 10, 1, "grip", "both paws")
    if not any(q[1] == "out_of_depth" for q in e._quirks_now):
        problems.append(f"a hold on Ripples should tell her quirk to the story: {e._quirks_now}")
    N.VETERANS.clear(); N.IN_FIGHT.clear()
    N.VETERANS.add("Nerine"); N.IN_FIGHT.update({"Nerine", "Ripples"})
    kept = N._clean("Nerine had faced worse opponents than this before. Ripples had faced worse opponents than this before.") \
        if hasattr(N, "_clean") else None
    if kept is not None and ("Nerine had faced" not in kept or "Ripples had faced" in kept):
        problems.append(f"a veteran's past fights should stay and a newcomer's go: {kept!r}")
    if not N._veteran_said("Nerine had faced worse") or N._veteran_said("Ripples had faced worse"):
        problems.append("only a veteran's memory of past fights is hers to keep")
    N.VETERANS.clear(); N.IN_FIGHT.clear()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        play.handle_command(s, "/profile Nerine")
    if "has fought before" not in out.getvalue() or "Ripples to her" not in out.getvalue():
        problems.append(f"/profile should show her history and relationships: {out.getvalue()[:300]}")
    return problems


def traits_check():
    """Build 280: traits and quirks (fighters.json traits, quirks, style, favors; rules.json traits). A fighter
    without traits is as before; the traits scale her rolls; quirks are switchable one by one and all at once; the
    director is told each one's style; /traits lists them."""
    import director
    import play
    problems = []
    s = H.session(3, fighters="Ripples,Nocturne,Seraphina,Nerine")
    e = s.eng
    if e.trait("Ripples", "speed") != 1.25 or e.trait("Ripples", "made_up") != 1.0:
        problems.append(f"Ripples' speed trait: {e.trait('Ripples', 'speed')}")
    other = next((f for f in e.fighters.values() if not f.traits), None)
    if other is not None and e.trait(other, "speed") != 1.0:
        problems.append("a fighter with no traits should be as before")
    with contextlib.redirect_stdout(io.StringIO()):
        st = e.start_hold("Seraphina", "Ripples", "Stomach", 10, 1, "coils", "her coils")
        sp = e.start_hold("Nocturne", "Nerine", "Left Upper Arm", 10, 1, "paws", "both forepaws")
    want_ = round(10 * e.trait("Seraphina", "hold"), 2)
    if abs(st["power"] - want_) > 0.01 or want_ == 10:
        problems.append(f"Seraphina's hold trait should scale a 10 grip to {want_}: {st['power']}")
    if abs(sp["power"] - 10 * 0.75 * 0.75) > 0.01:
        problems.append(f"Nocturne's paw grip should be weaker (hold 0.75, paws 0.75): {sp['power']}")
    if abs(st["change_per_beat"] - 1) > 0.01:
        problems.append("only works_the_hold adds to a hold's tightening")
    e.rules["traits"]["quirks"]["stubborn"]["enabled"] = False
    if e.quirk("Ripples", "stubborn") or not e.quirk("Ripples", "cocky"):
        problems.append("a quirk switched off should be off, and only that one")
    e.rules["traits"]["quirks"]["stubborn"]["enabled"] = True
    e.rules["traits"]["enabled"] = False
    if e.trait("Ripples", "speed") != 1.0 or e.quirk("Ripples", "cocky"):
        problems.append("traits switched off should change nothing")
    e.rules["traits"]["enabled"] = True
    hint = director.style_hint(e)
    if "HOW NERINE FIGHTS" not in hint or "Tail Bind" not in hint:
        problems.append(f"the director should be told each one's style and favourite moves: {hint[:200]}")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        play.handle_command(s, "/traits Nocturne")
    if "weak_paw_grip" not in out.getvalue():
        problems.append(f"/traits should list her quirks: {out.getvalue()[:200]}")
    d = e.get("Ripples")
    d.learned["held_count"] = 0
    low = e.trait(d, "escape")
    d.learned["held_count"] = 3
    if not e.trait(d, "escape") > low:
        problems.append("out_of_depth: she should get better at escaping each hold she is caught in")
    return problems


def coil_contest_check():
    """Build 279: the contest of coils (two fighters coiled round each other fight it out each beat; the loser's coils
    are torn off and the winner's tighten), the constriction and contest writing (story blocks by how many coils and
    how hard, story lines, sample tags), and the narration slips from the build-276 played log: a serpent standing
    firm, one tail told as tails, the get-up told out of order, a grip still told after she tore free, a bite at
    the coils made up."""
    import blocks
    import narrator as N
    problems = []
    s = H.session(3, fighters="Seraphina,Vesper")
    e, n = s.eng, s.narrator
    won = stall = 0
    for i in range(60):
        for h in list(e.holds):
            e.release(h, "test")
        with contextlib.redirect_stdout(io.StringIO()):
            e.start_hold("Seraphina", "Vesper", "Midsection", 10, 1, "coils", "her coils")
            e.start_hold("Vesper", "Seraphina", "Midsection", 10, 1, "coils", "her coils")
            for h in e.holds.values():
                h.coil = True
            evs = e._coil_contest_tick(())
        ev = next((x for x in evs if x["type"] == "coil_contest"), None)
        if ev is None:
            problems.append("two fighters coiled round each other should have a contest")
            break
        if ev["result"] == "won":
            won += 1
            left = {(h.attacker, h.defender) for h in e.holds.values()}
            if left != {(ev["winner"], ev["loser"])}:
                problems.append(f"the loser's coils should be torn off and the winner's stay: {left}")
                break
        else:
            stall += 1
        e.get("Seraphina").energy = e.get("Vesper").energy = 100
    if not (won and stall):
        problems.append(f"the contest should sometimes stall and sometimes be won: {won} won, {stall} stalled")
    e.rules["holds"]["coil"]["contest"]["enabled"] = False
    if e._coil_contest_tick(()):
        problems.append("with the contest switched off there should be none")
    e.rules["holds"]["coil"]["contest"]["enabled"] = True
    import json as _json
    b = blocks.Blocks(_json.load(open("rules.json")), memory=os.path.join(os.getcwd(), "_mem_test.json"))
    for cat, ctx in (("constriction", {"coils": "many", "squeeze": "crushing", "body": "other"}),
                     ("coiling", {"coils": "two", "squeeze": "firm", "body": "serpent"}),
                     ("coil_contest", {"result": "won", "role": "loser"}), ("coil_contest", {"result": "stall"})):
        if not b.pick(cat, 1, **ctx):
            problems.append(f"no story block for {cat} {ctx}")
    n.strengths = {"Seraphina": 97, "Vesper": 90}
    n.plans = {"Seraphina": "serpent", "Vesper": "serpent"}
    n.damage_by = {"Seraphina": {"upper tail": 10}, "Vesper": {"midsection": 10}}
    n._hurt_now, n._calm_beat = set(), False
    slips = [str(x) for x in n._log_slips("Seraphina stood firm, her coils shifting slightly under her. "
                                          "Seraphina's tails hung lower now and had bunched together behind her.")]
    if not any("serpent" in x for x in slips) or not any("ONE tail" in x for x in slips):
        problems.append(f"a serpent standing firm and one tail told as tails should be caught: {slips}")
    n._broke_free = [("Seraphina", "Vesper")]
    slips = [str(x) for x in n._log_slips("With one hard wrench of her whole body, Vesper tore herself free. Seraphina's "
                                          "coils were still tight around Vesper's middle.")]
    if not any("still on" in x for x in slips):
        problems.append(f"a grip told as still on after she tore free should be caught: {slips}")
    n._broke_free = []
    n._getup_who, n._getup_rise = "Vesper", "roll"
    slips = [str(x) for x in n._log_slips("Vesper pushed herself up onto her hands and knees, then rolled onto her front.")]
    if not any("front first" in x for x in slips):
        problems.append(f"rolling onto her front after her knees should be caught: {slips}")
    n._getup_who = n._getup_rise = None
    # build 283 (the user's log): an impact told in a beat of grips alone
    n._strike_parts, n.grips = [], [("Seraphina", "Vesper", "chest", "her coils")]
    slips = [str(x) for x in n._log_slips("The impact came first as a dull thud against Vesper's chest.")]
    if not any("no blow lands" in x for x in slips):
        problems.append(f"an impact in a beat of grips alone should be caught: {slips}")
    n._strike_parts = ["chest"]
    if any("no blow lands" in str(x) for x in n._log_slips("The impact came first as a dull thud against Vesper's chest.")):
        problems.append("an impact in a beat with a blow is fine")
    n._strike_parts, n.grips = [], []
    if not N.SERPENT_STOOD.search("Seraphina stood firm") or N.SERPENT_STOOD.search("Seraphina reared up"):
        problems.append("standing words for a serpent")
    tags = n._sample_tags("all", [], [], [{"type": "coil_contest", "result": "won", "fighters": ["A", "B"]}])
    if "coil contest won" not in tags:
        problems.append(f"a contest beat should ask for the contest passage: {tags}")
    return problems


def played276_check():
    """Build 278: fixes from the build-276 played Ripples vs Seraphina log, Buizel ribs and flanks, and a big blow
    on the shoulder carrying on into her side. A squeeze ordered with no hold yet starts the coil; an order to do
    nothing gets nothing (and no break-free, even with the dice free); a coil ordered with a strike gets the grip;
    a left-out passage in the present tense is put in the past; [brackets] on a command; "Tree" for the arena's
    oak; a tail fan binding an arm is a coil round the middle; no claws for a serpent."""
    import director
    import play
    import blocks
    from engine import body_region
    problems = []
    s = H.session(3, fighters="Seraphina,Ripples")
    e, n = s.eng, s.narrator
    with contextlib.redirect_stdout(io.StringIO()):
        play.handle_command(s, "/scene 15")
        r, _ = director.resolve_many(e, [{"action": "hold_adjust", "attacker": "Seraphina", "defender": "Ripples",
                                          "flavor": "coils around Ripples' midsection and constricts"}])
    if not any(h.attacker == "Seraphina" and h.defender == "Ripples" for h in e.holds.values()):
        problems.append(f"a squeeze with no hold yet should start the coil: {[x.get('type') for x in r]}")
    for h in list(e.holds):
        e.release(h, "test")
    acts = director.apply_players(e, [{"action": "struggle", "attacker": "Ripples", "defender": "Seraphina"}],
                                  {"Ripples": "Does nothing"})
    if acts[0].get("action") != "breather" or "Ripples" not in e._passive[1]:
        problems.append(f"an order to do nothing should be a beat of doing nothing: {acts}")
    acts = director.apply_players(e, [{"action": "strike", "attacker": "Seraphina", "defender": "Ripples",
                                       "move": "Hydro Pump", "part": "Stomach"}],
                                  {"Seraphina": "Hydro Pump on her stomach and then I coil around her midsection"})
    if [a.get("action") for a in acts] != ["strike", "hold_start"]:
        problems.append(f"an attack and a coil ordered should give both: {[a.get('action') for a in acts]}")
    n.strengths = {"Seraphina": 97, "Ripples": 80}
    t = n._to_past("Ripples' paws scrabble at the ground as she writhes against the hold. With a sharp twist, she "
                   "pries the tail fan off her arm. She staggers back, gasping for breath.")
    if "staggered" not in t:
        problems.append(f"a left-out passage should be put in the past: {t!r}")
    if play._unbracket('sustain A B "Hydro Pump" 4 [Tree] [Stomach, chest]') != \
            'sustain A B "Hydro Pump" 4 "Tree" "Stomach, chest"':
        problems.append("square brackets on a command should count as quotes")
    if e.scene_prop_for("Tree") not in (e.scene_cfg.get("props") or []):
        problems.append(f"'Tree' should be the arena's own tree: {e.scene_prop_for('Tree')}")
    cs, note = e.coil_body_first("Seraphina", "Ripples", [("Left Upper Arm", 21, 3, "with her broad iridescent tail fan")],
                                 flavor="Seraphina's tail binds Ripples' left upper arm")
    if not note or not any(body_region(c[0]) in e.MIDDLE_REGIONS for c in cs):
        problems.append(f"a big serpent's tail fan on an arm should be a coil round the middle: {cs}")
    if not blocks.body_bans({"scales", "coils", "tail", "fins"}).search("Her claws slid out and stayed out."):
        problems.append("a serpent has no claws for a library line")
    rip = e.get("Ripples")
    if not {"Left Ribs", "Right Ribs", "Left Flank", "Right Flank"} <= set(rip.parts):
        problems.append(f"a Buizel should have ribs and flanks: {sorted(rip.parts)[:8]}")
    s2 = H.session(4, fighters="Nocturne,Ripples")
    e2 = s2.eng
    mv = next(m for m in e2.get("Nocturne").moves if m["name"] == "Iron Tail")
    side = e2._side_spill(e2.get("Ripples"), mv, [{"part": "Left Shoulder", "damage_taken": 50, "power": 40,
                                                   "defender": "Ripples"}], {"moved": "stagger"})
    if not side or side[0]["part"] != "Left Ribs":
        problems.append(f"a big blow that staggers her from the shoulder should carry into her ribs: {side}")
    bite = next((m for m in e2.get("Nocturne").moves if m["name"] == "Bite"), None)
    if bite and e2._side_spill(e2.get("Ripples"), bite, [{"part": "Left Shoulder", "damage_taken": 50, "power": 40,
                                                          "defender": "Ripples"}], {"moved": "stagger"}):
        problems.append("a bite stops where it lands")
    return problems


def seraphina275_check():
    """Build 277: the leftovers from the build-273 lakeside log and fixes from the build-275 Seraphina vs Ripples log.
    Blood in the mouth of one who only clawed, "for once" on the first beat, landing on her side while face-up, a
    colour changing, a kept hold named for the wrong limb, an attack told without a part named, a retold sentence
    with the names swapped, a balance line for a downed fighter, standing firm while knocked down, coils squeezing
    with no coil on, a serpent's feet, trapped paws clawing, a paragraph cut off on a comma, a drag at the water's
    edge, and /plan dominate taking the fight-back away."""
    import director
    import narrator as N
    from engine import Engine
    problems = []
    if N.Narrator.FIRST_BEAT_CLAUSE.sub("", "She flinched the right way for once, and it paid.") != \
            "She flinched the right way, and it paid.":
        problems.append("'for once' should go on the first beat")
    if not N.SAYS_ON_SIDE.search("She landed hard on her side, and it throbbed.") or \
            N.SAYS_ON_SIDE.search("A jolt ran into her side."):
        problems.append("landing on her side should be caught, a jolt into her side not")
    if not N.COLOUR_CHANGE.search("Nocturne's colour was changing."):
        problems.append("a fighter's colour changing should be caught")

    class A_:
        parts = {"Right Forearm Fin": 1, "Twin Tails": 1}
    fixed = Engine._holder_part_fix("Ripples' Right Forearm Fin on her right hock", A_,
                                    [{"part": "Right Hock", "with": "with her twin tails"}])
    if "fin" in fixed.lower() or "twin tails" not in fixed:
        problems.append(f"a kept hold should be named for what holds it: {fixed!r}")
    t = ("She watched as the water hit, spreading across Ripples in a cascade of force.\n\nSeraphina watched the "
         "water hit Ripples, spreading across her body in a cascade of force. The power was immense.")
    if "cascade" in N.Narrator._drop_inner_repeats(t).split("\n\n")[-1]:
        problems.append("the same sentence with names and pronouns swapped should be told once")
    for t in ("Seraphina's coils tightened around Ripples, squeezing her ribs.", "Her coils constricted Ripples' ribs."):
        if not N.COIL_SQUEEZE.search(t):
            problems.append(f"coils squeezing not caught: {t}")
    if N.COIL_SQUEEZE.search("Seraphina's coils tightened, and her body undulated across the water."):
        problems.append("a serpent bunching her own coils is not a squeeze")
    if not N.SERPENT_LIMB.search("She kicked off from the solid ground behind her."):
        problems.append("a serpent kicking should be caught")
    if not N.TRAPPED_PAWS.search("She clutched at the coils with her webbed paws, her claws scraping."):
        problems.append("trapped paws clutching at the coils should be caught")
    if not N.STOOD_FIRM.search("Ripples stood firm, her feet planted on the ground.") or \
            not N.UPRIGHT_LINE.search("She tested her balance, found it, and kept it."):
        problems.append("standing firm, and a balance line, should be recognised")
    s = H.session(3, fighters="Seraphina,Ripples")
    n, e = s.narrator, s.eng
    n.strengths = {"Seraphina": 100, "Ripples": 98}
    n.damage_by = {"Seraphina": {"chest": 10}, "Ripples": {"right upper arm": 30}}
    n._biters = {"Ripples"}
    if not n._blood_lines("Seraphina tasted blood in her mouth."):
        problems.append("blood in the mouth of one who didn't bite (and wasn't hit there) should be caught")
    if n._blood_lines("Ripples tasted blood in her mouth."):
        problems.append("the one who bit may taste blood")
    cuts = n._program_cuts(["This is mine, she thought,"])
    if not cuts[0].endswith("thought."):
        problems.append(f"a paragraph cut off on a comma should end in a full stop: {cuts[0]!r}")
    e.positions = "Seraphina: in the shallows; Ripples: on the soft beach"
    with contextlib.redirect_stdout(io.StringIO()):
        e.knock_down("Ripples")
    e.rules.setdefault("director", {})["manhandle_cooldown"] = 0
    with contextlib.redirect_stdout(io.StringIO()):
        res = e.manhandle("Seraphina", "Ripples", "drag", enforce=False)
    if "root" in str(res):
        problems.append("a drag at the water's edge should not go over the root-knotted ground")
    e.plan = {"shape": "dominate", "winner": "Seraphina"}
    if not (e.dominated("Ripples") < 1.0 and e.dominated("Seraphina") == 1.0):
        problems.append(f"/plan dominate should cut only the loser's fight-back: {e.dominated('Ripples')}")
    e.directed = False
    e._dominate_turn = (e.turn, False)
    e.downed.pop("Ripples", None)
    r, _ = director.resolve_many(e, [{"action": "strike", "attacker": "Ripples", "defender": "Seraphina",
                                      "move": "Aqua Jet", "part": "Chest"}])
    if any(x.get("type") == "instant" and x.get("attacker") == "Ripples" for x in r):
        problems.append("on the winner's beat the dominated one's attack should become a step back")
    e.plan = {}
    taps = e.rules["finish"]["submission"]["taps"]
    taps.update(enabled=True, needed=3, different_parts=100, serpent_different_parts=50)
    if (e.taps_distinct_needed(e.get("Seraphina")), e.taps_distinct_needed(e.get("Ripples"))) != (2, 3):
        problems.append(f"a serpent should need fewer different parts for her taps: "
                        f"{e.taps_distinct_needed(e.get('Seraphina'))} / {e.taps_distinct_needed(e.get('Ripples'))}")
    taps["enabled"] = False
    return problems


def lakeside273_check():
    """Build 276: fixes from the build-273 lakeside Ripples vs Nocturne log. A grip told with paws that hold nothing,
    a standing fighter told lying down, a biped given forelegs, a fur colour nobody has, memories
    from before the fight, a left-out passage that retells a get-up already told, a hold she wrenched out of told as
    let go, a biped's kick with a paw, and commands joined with &&."""
    import director
    import narrator as N
    problems = []
    s = H.session(3, fighters="Ripples,Nocturne")
    n = s.narrator
    n.grips = [("Ripples", "Nocturne", "Right Hock", "her twin tails")]
    if not n._grip_limb_wrong("Her webbed paws curled tightly around Nocturne's leg."):
        problems.append("paws told gripping her leg, when only twin tails hold it, should be caught")
    if n._grip_limb_wrong("Her webbed paws dug into the grass as her tails held Nocturne's leg."):
        problems.append("paws in the grass beside a tail grip is not a wrong limb")
    for t in ("Nocturne's body twisted, her back coming off the ground.", "The grass beneath her back was soft.",
              "She wouldn't put any weight through it to rise."):
        if not N.GROUNDED.search(t):
            problems.append(f"lying down not caught: {t}")
    if N.GROUNDED.search("The hurt leg lay still."):
        problems.append("a leg lying still is not her lying down")
    for t in ("Her instincts took over, honed from countless battles.",
              "She had been in worse situations before.", "the interest she had when stalking prey in the river"):
        if not N.PAST_FIGHTS.search(t):
            problems.append(f"a memory from before the fight not caught: {t}")
    n.strengths = {"Ripples": 98, "Nocturne": 90}
    kept = n._drop_rise_retold("Ripples' tails dug deep. Nocturne sank back down. She pushed herself up onto her feet.",
                               "Nocturne", "Nocturne got to her feet at last, unsteady.")
    if "feet" in kept or "sank" in kept or "tails dug deep" not in kept:
        problems.append(f"a left-out passage should not retell a get-up already told: {kept!r}")
    n.fur_colors = {"Ripples": "orange", "Nocturne": "white"}
    sl = [str(x) for x in n._bad_sentences("The horn was a stark contrast, a gleaming white against the dark fur.")]
    if not any("fur" in w for w in sl):
        problems.append(f"dark fur, which nobody here has, should be caught: {sl}")
    e = s.eng
    r, _ = director.resolve_many(e, [{"action": "strike", "attacker": "Ripples", "defender": "Nocturne",
                                      "improvised_name": "Kick To The Hock", "part": "Right Hock",
                                      "flavor": "Ripples drives her right paw into the hock"}])
    if "paw" in str(r[0].get("flavor") or ""):
        problems.append(f"a Buizel's kick is her foot: {r[0].get('flavor')}")
    import play
    with contextlib.redirect_stdout(io.StringIO()):
        play.handle_command(s, "/set holds.break.base 0.13 && /set holds.break.base 0.14")
    if s.eng.rules["holds"]["break"].get("base") != 0.14:
        problems.append(f"commands joined with && should run in turn: {s.eng.rules['holds']['break'].get('base')}")
    return problems


def sub_match_check():
    """Build 244: in a submission match, openings on her feet too (more once a part is worn) with the holder taking
    her down into it, and, in a several-tap match, her parts giving way faster the deeper below zero she is."""
    s = H.session(5, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    a, d = e.get("Nerine"), e.get("Ripples")
    if e.sub_chance(d) != 0:
        problems.append("outside a submission match there should be no opening on her feet")
    e.rules["finish"]["submission"]["enabled"] = True
    fresh = e.sub_chance(d)
    d.parts["Left Thigh"].damage = 200.0
    worn = e.sub_chance(d)
    if not (0 < fresh < worn <= 0.2):
        problems.append(f"an opening on her feet should come now and then, more once a part is worn: {fresh} then {worn}")
    e.rules["submissions"]["small_joints"]["enabled"] = False
    shapes = e.submission_shapes(a.name, d.name)
    ground = {n: x for n, x in shapes.items() if "standing" not in e.SUBMISSIONS[n]["facing"]}
    if not ground or not all(x.get("lands") for x in ground.values()):
        problems.append(f"on her feet the ground holds should say how she lands when taken down into them: "
                        f"{sorted(ground)[:6]}")
    else:
        e.sub_window = {d.name: True}
        name = next(iter(ground))
        res = e.start_submission(a.name, d.name, name, enforce=True)
        if d.name not in e.downed or not res.get("taken_down") or not any(h.sub for h in e.holds.values()):
            problems.append(f"the takedown into the {name} didn't put her down and lock it: {res.get('type')}")
    e.rules["finish"]["submission"]["taps"].update(enabled=True, needed=3)
    d.health = -1.0 * d.max_health
    if abs(e.zero_part_ramp(d) - 1.8) > 0.01:
        problems.append(f"at -100% her parts should take x1.8 in a three-tap match: {e.zero_part_ramp(d)}")
    e.rules["finish"]["submission"]["taps"]["enabled"] = False
    if e.zero_part_ramp(d) != 1.0:
        problems.append("with one tap needed, part_ramp (only: taps) should be off")
    return problems


def upright_check():
    """Build 245: holds put on a fighter still on her feet (or sitting up) keep her upright, and may bear her down
    each beat with the grip kept on (now and then the holder has to readjust); invented ones can be upright too."""
    s = H.session(5, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    a, d = e.get("Nerine"), e.get("Ripples")
    e.rules["submissions"]["small_joints"]["enabled"] = False
    shapes = e.submission_shapes(a.name, d.name)
    up = [n for n in shapes if "standing" in e.SUBMISSIONS[n]["facing"]]
    if len(up) < 3:
        problems.append(f"too few holds to put on her standing: {up}")
        return problems
    res = e.start_submission(a.name, d.name, up[0])
    if d.name in e.downed or res.get("taken_down") or res["submission"].get("upright") != "on her feet":
        problems.append(f"the {up[0]} should keep her on her feet: {res.get('taken_down')}, {res['submission']}")
    hs = [h for h in e.holds.values() if h.sub]
    for h in hs:
        h.turns_active = 2
    before = [h.power for h in hs]
    e.rules["submissions"]["upright"].update(base=1.0, max=1.0, readjust=1.0, skip=0.0)
    seen = []
    for _ in range(4):
        for h in e.holds.values():
            h.turns_active = max(h.turns_active, 2)
        seen += [(ev["stage"], d.name in e.downed, e.facing.get(d.name)) for ev in e._upright_sub_tick()
                 if ev["type"] == "sub_collapse"]
    if [x[0] for x in seen] != ["sagging", "on her knees", "flat"] or seen[0][1] or seen[1][2] != "sitting up" \
            or seen[2][2] not in ("face-down", "face-up"):
        problems.append(f"a hold should bear her down stage by stage (sagging on her feet, knees, flat): {seen}")
    if len([h for h in e.holds.values() if h.sub]) != len(hs):
        problems.append("the hold came off when she went down in it")
    if not all(h.power < p for h, p in zip(hs, before)):
        problems.append("a readjust should loosen the grips for a moment")
    for hid in [h.id for h in e.holds.values()]:
        e.holds.pop(hid)
    e.downed.pop(d.name, None)
    e.facing.pop(d.name, None)
    res = e.start_custom_submission(a.name, d.name, "spine crank", [("Chest", "both arms")], "", enforce=False,
                                    upright=True)
    if d.name in e.downed:
        problems.append("an invented hold marked upright should keep her on her feet")
    return problems


def held_reach_check():
    """Build 249: a fighter held on the ground reaches her holder only with what the hold leaves near her (a heel
    hook: kicks and her tail, not her jaws); the down counter keeps counting while she is held; the pain gauge; taps
    in the chronicle; no wings on a Buizel; no footwork for a fighter held or down."""
    import blocks
    import narrator
    s = H.session(5, fighters="Ripples,Nerine")
    e, problems = s.eng, []
    a, d = e.get("Ripples"), e.get("Nerine")
    e.downed[d.name] = 0
    e.facing[d.name] = "face-down"
    e.start_submission(a.name, d.name, "heel hook")
    bite = e.find_move(d.name, "Bite")
    tail = e.find_move(d.name, "Aqua Tail")
    try:
        e.move_attack(d.name, a.name, "Bite", ["Throat"], enforce=True)
        problems.append("face-down in a heel hook, her bite still reached the holder's throat")
    except ValueError as exc:
        if "out of reach" not in str(exc):
            problems.append(f"the bite was refused for another reason: {exc}")
    if tail and e.held_reach_block(d, a, tail, ["Head"]):
        problems.append("her tail should reach the one tangled round her leg")
    e.facing[d.name] = "sitting up"
    if bite and not e.held_reach_block(d, a, bite, ["Throat"]):
        problems.append("sitting up, her bite should reach only the limbs holding her, not the throat")
    if bite and e.held_reach_block(d, a, bite, ["Left Paw"]):
        problems.append("sitting up, she should be able to bite the paw turning her foot")
    e.rules["holds"]["held_reach"]["enabled"] = False
    if bite and e.held_reach_block(d, a, bite, ["Throat"]):
        problems.append("held_reach off should limit nothing")
    e.rules["holds"]["held_reach"]["enabled"] = True
    d.learned.pop("down_for", None)
    for _ in range(3):
        e.get_up_tick()
    if d.learned.get("down_for") != 2:
        problems.append(f"the time down should count while she is held: {d.learned.get('down_for')}")
    g = e.pain_gauge(d)
    if not g or "heel hook" not in g["overall"].get("where", "") or not g.get("part") \
            or not set(g["part"]["parts"]) & {"Left Foot", "Left Knee", "Left Hip"}:
        problems.append(f"the pain gauges should say she is in the heel hook, and name the held parts: {g}")
    s2 = H.session(6, fighters="Ripples,Nerine")
    e2 = s2.eng
    ne = e2.get("Nerine")
    calm = e2.pain_gauge(ne)["overall"]["pct"]
    e2._apply_damage(ne, "Head", 60)
    e2.beat()
    hit = e2.pain_gauge(ne)
    e2.beat()
    e2.beat()
    later = e2.pain_gauge(ne)
    if hit["overall"]["pct"] <= calm or not hit["part"] or hit["part"]["parts"] != ["Head"]:
        problems.append(f"a blow should spike the overall pain and show the struck part: {calm} -> {hit}")
    if later["overall"]["pct"] >= hit["overall"]["pct"] or later["part"]:
        problems.append(f"the pain should fade over the beats after it: {hit} -> {later}")
    e.record_beat([], [{"type": "tap_count", "how": "tap", "attacker": a.name, "defender": d.name,
                        "submission": "heel hook", "part": "Left Foot", "tap_no": 1, "needed": 3}])
    if not any(m["kind"] == "tap" for m in e.chronicle["moments"]):
        problems.append("a tap should be one of the fight's key moments")
    # a plain grip on a standing fighter's worn leg bears her down (submissions.upright.plain_holds); a bear hug,
    # which holds her weight, much less often; a held leg makes rising harder
    downs, hugs = 0, 0
    for seed in range(20):
        s3 = H.session(100 + seed, fighters="Nerine,Ripples")
        e3 = s3.eng
        r3 = e3.get("Ripples")
        r3.parts["Right Knee"].damage = 150
        e3.start_hold("Nerine", "Ripples", "Right Knee", 20, with_part="her jaws")
        for h in e3.holds.values():
            h.turns_active = 2
        for _ in range(4):
            e3._upright_sub_tick()
            for h in e3.holds.values():
                h.turns_active += 1
        downs += r3.name in e3.downed
    if downs < 12:
        problems.append(f"jaws on a worn knee for four beats should mostly bring her down: {downs} of 20")
    uc = e.rules["submissions"]["upright"]
    if "bear hug" not in (uc.get("supporting") or ()):
        problems.append("a bear hug should count as holding her weight")
    ban = blocks.body_bans({"arms", "ears", "tails", "fins"})
    if not ban or not ban.search("a wing flung out against the ground to stop herself"):
        problems.append("a Buizel was offered a wing flung out")
    if not narrator.FOOTWORK.search("three strides to build it, and the fourth is all thrust"):
        problems.append("strides aren't counted as footwork")
    return problems


def narration_mends_check():
    """Build 251: the fixes from the build-249 Ripples vs Nerine log. A noun after "the" stays a noun in the past-tense
    pass; a sentence with a verb isn't given "came up"; orphan thought marks are paired; a sound left with a participle,
    an echoed clause and a "The thought" with no thought are mended; the director's places are put right (a broken
    boulder, the shallows while she is held by the oak); a tap lands on the shoulder of one gripping with her jaws;
    frost on the one Ice Fang never touched and her 'own' move that was the other's are caught; a standing fighter
    lifts no head off the ground; and padding is capped (narration.stock_limit)."""
    import re
    import blocks
    import narrator as N
    problems = []
    s = H.session(5, fighters="Ripples,Nerine")
    e, n = s.eng, s.narrator
    one = "She saw the frantic heaves of her body as her chest heaves."
    if n._past_words(one, [one]) != "She saw the frantic heaves of her body as her chest heaved.":
        problems.append(f"past tense: {n._past_words(one, [one])}")
    s.sync_narrator()
    fr = n._mend_fragments("Nerine's ears flicked back, her body tensing as she spun away.")
    if "came up" in fr:
        problems.append(f"a sentence with a verb got 'came up': {fr}")
    bm = N._balance_marks("She was lost. I can't hold on much longer.* The pain grew.")
    if "*I can't hold on much longer.*" not in bm:
        problems.append(f"an orphan closing mark wasn't paired: {bm}")
    ml = n._mend_leftovers("Her step was uneven, her weight off the hurt leg, and her step was uneven. Hnk, escaping "
                           "her lips.\nThe thought was a frantic plea. She bucked.")
    if ml != "Her step was uneven, her weight off the hurt leg. Hnk escaped her lips.\nShe bucked.":
        problems.append(f"leftovers not mended: {ml!r}")
    # places: a broken boulder, and the shallows while she is held at the foot of the oak
    e.mark_arena("a boulder at the edge lies broken where Ripples was driven through it")
    if "boulder" in e._place_checked("Nerine", "standing tall on the boulder at the edge, watching"):
        problems.append("a position on a broken boulder was kept")
    e.lying_at = {"Ripples": "an old oak"}
    e.downed["Ripples"] = 0
    pc = e._place_checked("Ripples", "in the shallows, favoring her left leg")
    if pc != "by an old oak, favoring her left leg":
        problems.append(f"the shallows while down by the oak: {pc!r}")
    e.downed.pop("Ripples", None)
    e.lying_at = {}
    # the tap: on the shoulder of one biting her knee, on the arm of one holding her with it
    n.posture_start = {"Ripples": "ON HER FEET"}
    n.grips = [("Nerine", "Ripples", "Right Knee", "her jaws")]
    if n._tap_spot("Ripples", "Nerine") != "Nerine's shoulder":
        problems.append(f"a jaw grip gave the tap to: {n._tap_spot('Ripples', 'Nerine')}")
    n.grips = [("Nerine", "Ripples", "Right Arm", "both arms")]
    if n._tap_spot("Ripples", "Nerine") != "Nerine's arm":
        problems.append("an arm grip should take the tap on her arm")
    # what belongs to one given to the other
    n.elem_on = {"Ripples": {"cold"}}
    n.used_by = {"Nerine": {"Aqua Jet", "Ice Fang"}, "Ripples": {"Water Gun"}}
    n._acts_now = [{"attacker": "Ripples", "defender": "Nerine", "move": {"name": "Water Gun"}}]
    bad = n._bad_sentences("Nerine flexed her paw, feeling the sting of the icy wound. Ripples knew that her Aqua Jet "
                           "should have done more. With a hiss of water, she threw an Aqua Jet straight at Nerine.")
    for want in ("icy wound", "her Aqua Jet", "threw an Aqua Jet"):
        if not any(want in k for k in bad):
            problems.append(f"not caught: {want} ({list(bad)[:4]})")
    ban = blocks.body_bans({"arms", "tails", "standing"})
    if not ban or not ban.search("Ripples' head snapped up off the ground"):
        problems.append("a standing fighter lifted her head off the ground")
    # padding: one 'mind raced' a beat, 'could feel' becomes 'felt' past the first
    n.beat_now = 40
    n._stock_hist = []
    out = n._stock_limit("Her mind raced. She could feel the grass.\nShe watched. Her mind raced as she thought. "
                         "She could feel the wind. Her mind was racing again.")
    if len(re.findall(r"mind (?:raced|was racing)", out)) > 1 or "She felt the wind" not in out:
        problems.append(f"stock phrases not capped: {out!r}")
    e.rules["narration"]["stock_limit"]["enabled"] = False
    if n._stock_limit("Her mind raced. Her mind raced.") != "Her mind raced. Her mind raced.":
        problems.append("stock_limit off should leave the text as it is")
    e.rules["narration"]["stock_limit"]["enabled"] = True
    return problems


def log_fixes_252_check():
    """Build 252: the fixes from the build-251 Ripples vs Nerine log. A blow the tap steer moves keeps no words or path
    parts of where it was aimed; a head twist typed Water lands as Normal; no stepping tells for one lying down; the
    notes' wording and the model's own remarks are taken out, and nouns stay nouns in the past-tense pass; a thought
    swapped in is the part's own fighter's; a grip told the wrong way round and 'getting back up' for one never down
    are caught; the export carries the tap tally and pain gauges."""
    import re, director, fightexport
    problems = []
    s = H.session(5, fighters="Ripples,Nerine")
    e, n = s.eng, s.narrator
    e.rules = __import__("copy").deepcopy(e.rules)       # (this check's own settings, never saved for the others)
    sub = e.rules["finish"]["submission"]
    sub["enabled"] = True
    sub["taps"].update(enabled=True)
    sub["taps"]["steer"].update(strikes=1)
    e.get("Nerine").parts["Right Thigh"].damage = 70
    b = director._apply_tap_steer(e, "Ripples", "Nerine", {"action": "strike", "part": "Left Ear", "hits": [
        {"part": "Left Ear"}, {"part": "Right Ear"}], "flavor": "drives her knee into the side of Nerine's head"},
                                  "strikes")
    aim = e.tap_target("Nerine")
    if b.get("part") != aim or len(b.get("hits") or []) != 1 or "head" in b.get("flavor", "") \
            or aim.lower() not in b.get("flavor", ""):
        problems.append(f"a steered blow kept where it was aimed: {b}")
    if e.improvised_move("Head Twist", "Water", "solid", about="twists her head hard")["type"] != "Normal":
        problems.append("a head twist typed Water should land as Normal")
    if e.improvised_move("Water Whip", "Water", "solid", about="a lash of water")["type"] != "Water":
        problems.append("a water whip should stay Water")
    one = "Her breath came in short, sharp gasps, and the frantic heaves and kicks did nothing. Her chest heaves and shakes."
    got = n._past_words(one, [one])
    if "sharp gasps" not in got or "frantic heaves and kicks" not in got or "chest heaved and shook" not in got:
        problems.append(f"past tense: {got}")
    ml = n._mend_leftovers("Then what it left on the right hip, in a few words of her own, was a dull ache. That is the "
                           "paragraph rewritten. She was the one gripping, pressing and keeping it on; Ripples was the one "
                           "held, hurting in it and fighting it. She could taste the faint the taste of water. Her head "
                           "snapped back came up. The fur over right thigh dented.")
    if ml != ("On her right hip it left a dull ache. She could taste the faint taste of water. Her head snapped back "
              "and came up. The fur over her right thigh dented."):
        problems.append(f"copied notes not mended: {ml!r}")
    s.sync_narrator()
    n.grips = [("Ripples", "Nerine", "Head", "her arm"), ("Nerine", "Ripples", "Left Foot", "her twin tails")]
    n.ever_down = set()
    n.on_ground = set()
    bad = n._bad_sentences("Nerine's left foot curled as Ripples' twin tails tightened around it. Ripples knew she had "
                           "let Nerine get back up too quickly. Nerine's tails wrapped tighter.")
    if len(bad) != 2 or any("Nerine's tails" in x for x in bad):
        problems.append(f"reversed grip / never down: {bad}")
    n.facing = {"Ripples": "face-down"}
    n.strengths = {"Ripples": 40, "Nerine": 60}
    if any(n.STAND_SIGN.search(x) for x in [n._limb_fit(x, "Ripples") for x in n.SEEN_HURT["badly"]
                                            if not n.STAND_SIGN.search(x)]):
        problems.append("stand signs not recognised")
    # the export: the tally and the gauges
    f = {"name": "Ripples", "taps": {"given": ["Head"], "needed": 3},
         "pain": {"overall": {"pct": 80, "label": "near her limit"}, "part": {"pct": 120, "parts": ["Left Knee"],
                                                                              "label": "past what she can bear"}}}
    g = fightexport._gauges(f)
    if g.count('class="pip') != 3 or "Pain 80%" not in g or "Left knee 120%" not in g:
        problems.append(f"export gauges: {g[:200]}")
    return problems


def log_fixes_253_check():
    """Build 253: the rest of the build-251 Ripples vs Nerine log. No 'shoves her back' break with either one lying
    down; a head snaps back only from a blow or grip on her head (else it jerks); one rise told once; nobody favours a
    part nothing has hurt; whose water she is wet with; 'she thinks to herself' marked as a thought; no stepping tells
    for one holding a fighter on the ground."""
    import copy
    problems = []
    s = H.session(5, fighters="Ripples,Nerine")
    e, n = s.eng, s.narrator
    e.rules = copy.deepcopy(e.rules)
    ways = set()
    for k in range(40):
        e.holds.clear()
        e.start_hold("Nerine", "Ripples", "Left Foot", 10)
        for h in e.holds.values():
            h.turns_active = 3
        e.downed = {"Nerine": 2}
        e.lucky = {"Ripples"}
        for ev in e._hold_break_tick():
            if ev.get("broke_free"):
                ways.add(ev.get("manner"))
    e.lucky = set()
    e.downed = {}
    if not ways or "shove" in ways:
        problems.append(f"break ways with the holder down: {ways}")
    n.rules = copy.deepcopy(n.rules)
    n.strengths = {"Ripples": 60, "Nerine": 40}
    n.damage_by = {"Ripples": {"left knee": 30}, "Nerine": {"right thigh": 130, "right hip": 60}}
    n._parts_now = {"Nerine": {"right thigh"}}
    n.grips = []
    n._rose_now = {"Nerine"}
    n._wet_from = {"Ripples": "Water Gun"}
    n._move_names = set(getattr(n, "_move_names", None) or ()) | {"Aqua Jet", "Water Gun"}
    t = ("Nerine's body bucked once. Her head snapped back, the force of it jolting through her skull.\n"
         "Nerine pushed herself up onto her feet, unsteady. She favored her right thigh.\n"
         "She pushed herself up, her thigh screaming. With a final heave, she lurched upright.\n"
         "Ripples favored her right thigh as she circled. The water from the aqua jet still dripped from Ripples' fur.")
    got = n._mend_body_slips(t)
    want = ("Nerine's body bucked once. Her head jerked back.\nNerine pushed herself up onto her feet, unsteady. She "
            "favored her right thigh.\nThe water from the water gun still dripped from Ripples' fur.")
    if got != want:
        problems.append(f"body slips: {got!r}")
    n._parts_now = {"Nerine": {"neck"}}
    if "snapped back" not in n._mend_body_slips("Nerine's head snapped back with the twist."):
        problems.append("a head twisted by the neck should still snap back")
    n.damage_by = {"Ripples": {}, "Nerine": {}}
    if "favoring" in n._mend_body_slips("She watched. She's favoring something, maybe her leg. Then she moved."):
        problems.append("favouring before anyone is hurt")
    th = n._mend_copied("Nerine, she thinks to herself, You can't give up now. Ripples' headlock is tight. She gritted "
                        "her teeth.")
    if th != "*You can't give up now. Ripples' headlock is tight.* She gritted her teeth.":
        problems.append(f"thinks to herself: {th!r}")
    # no stepping tells for Nerine, holding Ripples on the ground
    s.sync_narrator()
    n.strengths = {"Ripples": 40, "Nerine": 60}
    n.facing = {"Ripples": "face-down"}
    n.grips = [("Nerine", "Ripples", "Left Knee", "her jaws")]
    n.damage_by = {"Ripples": {"left knee": 80}, "Nerine": {"right thigh": 140}}
    if not n._not_stepping("Nerine") or not n._not_stepping("Ripples"):
        problems.append("stepping tells allowed for one holding a fighter down")
    n.grips = []
    if n._not_stepping("Nerine"):
        problems.append("stepping tells taken from one on her feet and holding nobody")
    return problems


def low_health_check():
    """Build 246: at the very end of her strength she shows it alone, squirms when down, her body gives her away (a
    limb that doesn't answer blocks its moves a beat), makes one last stand (then wide open), and the other reads her."""
    s = H.session(5, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    a, d = e.get("Nerine"), e.get("Ripples")
    lc = e.rules["low_health"]
    for k in ("idle", "squirm", "tells", "foe_read"):
        lc[k].update(chance=1.0, cooldown=0)
    d.health = 0.05 * d.max_health
    e.involved = set()
    kinds = {ev["type"] for ev in e._low_health_tick()}
    if not {"low_idle", "low_tell", "foe_read"} <= kinds:
        problems.append(f"left alone at 5%, she should show it, her body give her away, and the other read her: {kinds}")
    if not (a.learned.get("foe_read") or {}).get("kind") or "reads" not in __import__("director").low_health_hint(e):
        problems.append("the director isn't told how the other one reads her")
    e.downed[d.name] = 1
    e._fresh_down.discard(d.name)
    if "low_squirm" not in {ev["type"] for ev in e._low_health_tick()}:
        problems.append("down at 5% and free, she should squirm")
    e.downed.pop(d.name, None)
    arm = next(p for p in d.parts if e._LIMB_OF.get(__import__("engine").body_region(p)) == "arm")
    d.learned["dead_limb"] = {"part": arm, "kind": "arm", "turn": e.turn}
    mv = next((m for m in d.moves if e.dead_limb(d, m)), None)
    if mv is None:
        problems.append(f"no move of hers is thrown with her {arm}: can't test the dead limb")
    else:
        try:
            e._move_attack(d.name, a.name, mv["name"], ["Chest"], enforce=True)
            problems.append(f"{mv['name']} went through with her {arm} not answering")
        except ValueError as exc:
            if "answering" not in str(exc):
                problems.append(f"refused for the wrong reason: {exc}")
    d.learned.pop("dead_limb", None)
    for k in ("idle", "squirm", "tells", "foe_read"):
        lc[k]["chance"] = 0.0
    e.rules["moves"]["last_stand"].update(chance=1.0, below_strength=200)
    d.health = 0.05 * d.max_health
    if e._last_stand(d, {"name": "Brick Break", "target": "targeted"}) != d.name:
        problems.append("a sure last stand didn't come")
    e.turn += 1
    evs = e._low_health_tick()
    if not any(ev["type"] == "overextended" for ev in evs) or not e.has(d, "overextended"):
        problems.append(f"the beat after her last stand she should be wide open: {evs}")
    if e._last_stand(d, {"name": "Brick Break", "target": "targeted"}):
        problems.append("the last stand came twice")
    return problems


def tap_overwhelm_check():
    """Build 254 (tap.overwhelm, the breaking point): a gripped part in horrible condition does not make her tap at
    once: she holds out a few beats, how many from her strength left (no tap roll at all, and the narrator is told she is at her breaking point),
    then the tap is near certain. A part not yet that bad keeps the slow climb."""
    s = H.session(5, fighters="Nerine,Ripples")
    s.eng.rules["traits"]["enabled"] = False     # (the base rules: no stubborn quirk on her tap)
    e, problems = s.eng, []
    a, d = e.get("Nerine"), e.get("Ripples")
    e.rules["finish"]["submission"]["enabled"] = True
    e.rules["finish"]["submission"]["tap"]["blend"]["enabled"] = False     # (build 264: the breaking point is the old way)
    e.downed["Ripples"] = 0
    e.facing["Ripples"] = "sitting up"
    e.start_submission(a.name, d.name, "standing armbar")
    seen = []

    def beat(dmg):
        seen.clear()
        e.turn += 1
        for h in e.holds.values():
            h.turns_active += 1
            d.parts[h.part].damage = dmg
        real = e._chance
        e._chance = lambda p, what, *a_, **k: (seen.append(p) if "tapping out" in what else None) or False
        try:
            evs = e._tap_out_tick()
        finally:
            e._chance = real
        return (max(seen) if seen else 0.0), next((x for x in evs if x.get("type") == "tap_resist"), None)

    d.health = d.max_health * 0.3
    beat(120.0)                      # (the hold's first beats: a hurt part, nowhere near wrecked)
    beat(120.0)
    got = [beat(400.0) for _ in range(6)]
    if got[0][0] > 0 or got[1][0] > 0:
        problems.append(f"she could tap at once on a wrecked part: chances {[g[0] for g in got]}")
    if not (got[0][1] and got[0][1].get("breaking")):
        problems.append(f"the beats she holds out are not marked as her breaking point: {got[0][1]}")
    n = int(d.learned["breaking"][3])
    stages = [g[1].get("breaking") for g in got[:n] if g[1]]
    if not 2 <= n <= 4 or stages[0] != "first" or stages[-1] != "last" or any(x != "cracking" for x in stages[1:-1]):
        problems.append(f"the holding-out beats ({n}) don't go first ... last: {stages}")
    if any(g[0] > 0 for g in got[:n]) or got[n][0] < 0.9:
        problems.append(f"after holding out, the tap is not near certain: chances {[g[0] for g in got]}")
    e.rules["finish"]["submission"]["tap"]["overwhelm"]["enabled"] = False
    off = beat(400.0)[0]
    if off >= 0.9:
        problems.append(f"with tap.overwhelm off the slow climb no longer caps it: {off}")
    return problems


def tap_blend_check():
    """Build 264 (tap.blend): the tap chance comes from both the gripped part's damage and her health overall, and
    builds up over the hold's first beats: never on the first, rare on the second and third, all of it only from the ninth.
    Fresh with a ruined part: a fair chance she can still fight; worn out with a healthy part: harder than fresh but
    resistible; worn out with a ruined part: near certain once it has built."""
    s = H.session(5, fighters="Nerine,Ripples")
    s.eng.rules["traits"]["enabled"] = False     # (the base rules: no stubborn quirk on her tap)
    e, problems = s.eng, []
    a, d = e.get("Nerine"), e.get("Ripples")
    e.rules["finish"]["submission"]["enabled"] = True
    e.downed["Ripples"] = 0
    e.facing["Ripples"] = "sitting up"

    def run(health, dmg, n=6):
        e.holds.clear()
        d.learned.clear()
        d.health = d.max_health * health
        e.start_submission(a.name, d.name, "standing armbar")
        out = []
        for _ in range(n):
            seen = []
            e.turn += 1
            for h in e.holds.values():
                h.turns_active += 1
                d.parts[h.part].damage = dmg
            real = e._chance
            e._chance = lambda p, what, *a_, **k: (seen.append(p) if "tapping out" in what else None) or False
            try:
                e._tap_out_tick()
            finally:
                e._chance = real
            out.append(round(max(seen) if seen else 0.0, 3))
        return out

    worst = run(0.0, 400.0, 10)
    if worst[0] > 0 or worst[1] > 0.05 or worst != sorted(worst) or worst[-1] < 0.75:
        problems.append(f"worn out on a ruined part doesn't build from nothing to near certain: {worst}")
    fresh_ruined = run(1.0, 400.0, 10)[-1]
    worn_healthy = run(0.05, 10.0, 10)[-1]
    fresh_healthy = run(1.0, 10.0)[-1]
    if not 0.2 <= fresh_ruined <= 0.45:
        problems.append(f"fresh on a ruined part should be a fair chance she can fight: {fresh_ruined}")
    if not fresh_healthy < worn_healthy <= 0.2:
        problems.append(f"worn out on a healthy part should be harder than fresh but resistible: {worn_healthy} vs {fresh_healthy}")
    mid = run(0.5, 200.0, 10)[-1]
    if not fresh_healthy < mid < worst[-1]:
        problems.append(f"half hurt on a hurt part isn't between: {mid}")
    e.rules["finish"]["submission"]["tap"]["blend"]["enabled"] = False
    if run(0.0, 400.0)[:4] == worst[:4]:
        problems.append("with tap.blend off the chance is unchanged")
    return problems


def hold_mix_check():
    """Build 265: fewer chokes and jaw holds in a submission match (finish.submission.hold_mix): a choke or a bite hold
    the director picks stands only some of the time and a lock goes on instead, the openings favour holds without
    jaws, a choke on a fighter at zero health has endurance left (no "air 2200% gone"), and a limb already gripping
    her in one hold can't grip her somewhere else too."""
    import director
    s = H.session(3, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    e.rules["finish"]["submission"]["enabled"] = True
    e.downed["Ripples"] = 0
    e.facing["Ripples"] = "face-down"
    sh = e.submission_shapes("Nerine", "Ripples")
    jaws = [n for n, v in sh.items() if e.sub_uses_jaws(v) and not e.sub_is_choke(v)]
    if not jaws or "tail strangle" not in sh:
        return [f"the test needs a jaw hold and a tail strangle that fit: {sorted(sh)}"]
    picks = [e.pick_submission(sh) for _ in range(600)]
    share = sum(n in jaws for n in picks) / len(picks)
    plain = len(jaws) / max(1, sum(not e.sub_is_choke(v) for v in sh.values()))
    if not share < 0.8 * plain:
        problems.append(f"the openings pick a jaw hold as often as another: {share:.2f} (an even share is {plain:.2f})")
    kept = sum(director._apply_hold_mix(e, "Nerine", "Ripples", {"attacker": "Nerine", "defender": "Ripples",
                                                              "action": "submission", "improvised_name": "tail strangle"},
                                        "submission").get("improvised_name") == "tail strangle" for _ in range(300)) / 300
    if not 0.2 <= kept <= 0.5:
        problems.append(f"a choke the director picks should stand about hold_mix.choke of the time: {kept:.2f}")
    b = director._apply_hold_mix(e, "Nerine", "Ripples", {"attacker": "Nerine", "defender": "Ripples",
                                                          "action": "submission", "improvised_name": "ankle gnaw",
                                                          "hits": [{"part": "Left Foot", "with": "her jaws"}]}, "submission")
    for _ in range(40):
        if b.get("_mixed_from"):
            break
        b = director._apply_hold_mix(e, "Nerine", "Ripples", {"attacker": "Nerine", "defender": "Ripples",
                                                              "action": "submission", "improvised_name": "ankle gnaw",
                                                              "hits": [{"part": "Left Foot", "with": "her jaws"}]},
                                     "submission")
    if not b.get("_mixed_from") or e.sub_uses_jaws(sh[b["improvised_name"]]) or e.sub_is_choke(sh[b["improvised_name"]]):
        problems.append(f"a bite hold swapped should become a lock with no jaws: {b.get('improvised_name')}")
    e.rules["finish"]["submission"]["hold_mix"]["enabled"] = False
    if any(director._apply_hold_mix(e, "Nerine", "Ripples", {"attacker": "Nerine", "defender": "Ripples",
                                                             "action": "submission", "improvised_name": "tail strangle"},
                                    "submission").get("_mixed_from") for _ in range(50)):
        problems.append("with hold_mix off a choke is still swapped")
    # a choke at zero health: some endurance left, and the meter never past 99% while she is awake
    d = e.get("Ripples")
    d.health = 0.0
    e.start_submission("Nerine", "Ripples", "tail strangle")
    for _ in range(2):
        e.turn += 1
        for h in e.holds.values():
            h.turns_active += 1
        e._tap_out_tick()
    sg = d.learned.get("sub_gauge") or {}
    if float(sg.get("endure") or 0) < 30:
        problems.append(f"a choke at zero health left her no endurance: {sg}")
    g = (e.pain_gauge(d) or {}).get("part")
    if g and g.get("air") is not None and not 0 < g["air"] <= 99:
        problems.append(f"the air gone reads {g['air']}%")
    # a limb busy in one hold on her can't grip her elsewhere too
    e.holds.clear()
    e.sub_window = {"Ripples": True}
    e.rules["finish"]["submission"]["hold_mix"]["enabled"] = True
    director.resolve_many(e, [{"attacker": "Nerine", "defender": "Ripples", "action": "submission",
                               "improvised_name": "chicken wing"}])
    e.turn += 1
    try:
        director.resolve_many(e, [{"attacker": "Nerine", "defender": "Ripples", "action": "hold_start",
                                   "hits": [{"part": "Right Thigh", "with": "her paw", "severity": "firm"},
                                            {"part": "Lower Back", "with": "her knee", "severity": "firm"}]}])
    except ValueError:
        pass
    if any(h.part == "Right Thigh" for h in e.holds.values()):
        problems.append("both paws in a chicken wing still gripped her thigh as well")
    return problems


def busy_limbs_check():
    """Build 266: a holder's limbs locked in her own submission can't strike too (both legs in a triangle choke: no
    Knee Strike), her blows land near the hold (on Ripples' back in a chicken wing her jaws can't reach the foot), no
    charge from inside a hold, a strike from the side whose paw is caught comes from the other side, a nameless bite
    is named Bite, and a choke's pass-out counts for the neck."""
    import director
    s = H.session(3, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    e.rules["finish"]["submission"]["enabled"] = True
    e.downed["Ripples"] = 0
    e.facing["Ripples"] = "face-up"
    e.start_submission("Nerine", "Ripples", "triangle choke")
    knee = e.improvised_move("Knee Strike", "Normal", "hard", "targeted", "her knee drives in")
    try:
        e.move_attack("Nerine", "Ripples", knee["name"], ["Right Knee"], move=knee, enforce=True)
        problems.append("a Knee Strike went in with both legs locked in a triangle choke")
    except ValueError as x:
        if "legs" not in str(x):
            problems.append(f"the refusal doesn't say her legs are busy: {x}")
    e.holds.clear()
    e.facing["Ripples"] = "face-down"
    e.start_submission("Nerine", "Ripples", "chicken wing")
    bite = e.improvised_move("Bite", "Normal", "hard", "targeted", "her jaws snap shut")
    if not e.holder_reach_block(e.get("Nerine"), e.get("Ripples"), bite, ["Left Foot"]):
        problems.append("from a chicken wing her jaws still reached Ripples' foot")
    if e.holder_reach_block(e.get("Nerine"), e.get("Ripples"), bite, ["Upper Back"]):
        problems.append("from a chicken wing her jaws couldn't reach the back she is on")
    jet = dict(e.find_move("Nerine", "Aqua Jet") or e.dex_move("Aqua Jet"))
    try:
        e.move_attack("Nerine", "Ripples", jet["name"], ["Lower Back"], move=jet, enforce=True)
        problems.append("an Aqua Jet charge went off from inside a chicken wing")
    except ValueError:
        pass
    if director._plain_name("Ripples clamps her jaws down, her teeth sinking in") != "Bite":
        problems.append("a nameless bite isn't named Bite")
    # the paw caught in a wrist lock doesn't throw the blow
    e.holds.clear()
    r = e.get("Ripples")
    r.parts["Right Upper Arm"].damage = 320.0
    e.start_submission("Nerine", "Ripples", "wrist lock")
    chop = e.improvised_move("Chop", "Fighting", "hard", "targeted", "a chop")
    lm = e.limb_mult(r, chop)
    if lm and "right" in lm[0]:
        problems.append(f"the blow came from the arm caught in the wrist lock: {lm}")
    with_off = dict(e.rules["holds"]["busy_limbs"])
    e.rules["holds"]["busy_limbs"]["enabled"] = False
    e.holds.clear()
    e.facing["Ripples"] = "face-up"
    e.start_submission("Nerine", "Ripples", "triangle choke")
    if e.busy_with(e.get("Nerine"), knee):
        problems.append("with busy_limbs off the legs are still busy")
    e.rules["holds"]["busy_limbs"] = with_off
    return problems


def story_checks_check():
    """Build 267 (narration.story_checks): a failed get-up told after she is already up, the holder still pressing
    after the tap, a bite told on a part it never touched, and a move she never used named instead of the one she
    did; and the new story_blocks groups are there to be offered."""
    import narrator, blocks as blocks_
    problems = []
    rules = json.load(open(os.path.join(H.ROOT, "rules.json"), encoding="utf-8"))
    N = narrator.Narrator("x", rules)
    N.strengths = {"Ripples": 10, "Nerine": 80}
    N._landed, N._tap_end, N.grips = set(), None, []
    N._rose_now, N._tap_mid, N._acts_now = {"Ripples"}, [], []
    s1 = ["Ripples dragged herself up, and at last she was on her feet.",
          "Ripples' third attempt to rise was no more successful than the first two."]
    if not any("already UP" in w for _s, w in N._order_slips(s1)):
        problems.append("a failed get-up told after she was up wasn't caught")
    if N._order_slips(list(reversed(s1))):
        problems.append("the failed try told BEFORE the get-up was flagged")
    N._rose_now, N._tap_mid = set(), [("Ripples", "Nerine", "tap", "chicken wing", 1, 3)]
    s2 = ["Ripples tapped, her paw slapping the ground.", "Nerine's knee drove into Ripples' right shoulder."]
    if not any("tap ends it" in w for _s, w in N._order_slips(s2)):
        problems.append("the holder pressing after the tap wasn't caught")
    if N._order_slips(["Nerine's knee drove into Ripples' right shoulder.", "Ripples tapped, her paw slapping the ground.",
                       "Nerine let go at once."]):
        problems.append("the pressure told before the tap was flagged")
    N._tap_mid = []
    N.strengths = {"Ripples": 100, "Nerine": 100}
    if not N._order_slips(["Doubt flickered: how much did Ripples have left in her?"]):
        problems.append("a fresh fighter wondered about as running out wasn't caught")
    N.strengths = {"Ripples": 30, "Nerine": 80}
    if N._order_slips(["Doubt flickered: how much did Ripples have left in her?"]):
        problems.append("wondering how much a worn fighter has left was flagged")
    N._acts_now = [{"attacker": "Nerine", "move": {"name": "Bite"}, "hits": [{"part": "Upper Back"}]}]
    if not N._order_slips(["Nerine's teeth sank between Ripples' toes."]):
        problems.append("a bite told on the toes when it hit her back wasn't caught")
    if N._order_slips(["Nerine's teeth sank into Ripples' shoulder.", "Nerine's jaw set hard."]):
        problems.append("a bite next to where it landed (or a set jaw) was flagged")
    N.known_moves, N.used_by = {"Nerine": ["Water Gun", "Aqua Jet"]}, {"Nerine": set()}
    N._acts_now = [{"attacker": "Nerine", "move": {"name": "Water Gun"}}]
    if "Nerine's Water Gun" not in N._mend_move_names("The force of Nerine's Aqua Jet drove her back."):
        problems.append("a move she never used wasn't put right")
    N.used_by = {"Nerine": {"Aqua Jet"}}
    if "Aqua Jet" not in N._mend_move_names("She still felt Nerine's Aqua Jet from before."):
        problems.append("a move she really used earlier was changed")
    B = blocks_.parse(open(os.path.join(H.ROOT, "story_blocks.txt"), encoding="utf-8").read())
    have = {c for c, _k, _t in B}
    for c in ("surge", "grey_out", "running_on_empty", "getup_fail", "choke_fight", "sub_escape_held", "sub_escape_hold"):
        if c not in have:
            problems.append(f"story_blocks.txt has no {c} group")
    return problems


def polish_check():
    """Build 268 (narration.polish): a polished beat is kept when it passes the checks and replaces the local one
    in the story and the beat's record; a refusal, a dropped part label or a much shorter answer leaves the local
    one; /polish copy writes the request and /polish paste takes a reply pasted in by hand; off, nothing is sent."""
    import polish
    s = H.session(2, fighters="Ripples,Nerine")
    problems = []
    _quiet(H.beat, s, [{"attacker": "Ripples", "defender": "Nerine", "action": "breather"}], [])
    local = ("— Ripples —\nRipples breathed slowly and watched Nerine across the clearing, waiting.\n\n"
             "— Nerine —\nNerine circled to the left, her eyes never leaving Ripples, and waited too.")
    better = ("— Ripples —\nRipples let her breath out slow and kept her eyes on Nerine across the clearing.\n\n"
              "— Nerine —\nNerine drifted to the left, eyes fixed on Ripples, patient as stone.")
    # build 303: no upper limit on length by default, and the editor told it may write more
    longer = local.replace("waiting.", "waiting, every muscle in her slim body drawn tight, her twin tails stirring "
                           "behind her as she weighed each step Nerine took and the wet grass cooled under her paws, "
                           "her heart steady and her breath held low and even. " * 3)
    ok_long, why_long = polish.judge(None, local, longer, ["Ripples", "Nerine"], s.eng.rules)
    if not ok_long or "LENGTH:" not in polish.messages(local, [], "", s.eng.rules)[1]["content"]:
        problems.append(f"a longer polished beat should be kept, and the editor told it may write more: {why_long}")
    s.eng.rules["narration"]["polish"]["max_ratio"] = 1.5
    if polish.judge(None, local, longer, ["Ripples", "Nerine"], s.eng.rules)[0]:
        problems.append("max_ratio, when set, should still cap the length")
    s.eng.rules["narration"]["polish"]["max_ratio"] = 0
    sent = []
    real = polish.call
    polish.call = lambda rules, msgs: (sent.append(msgs), answer[0])[1]
    answer = [better]
    try:
        cfg = s.eng.rules["narration"]["polish"]
        out = s._maybe_polish(local, [], [], [])
        if sent or out != local:
            problems.append("with polish off something was sent or changed")
        cfg.update(enabled=True, model="test-model")
        out = s._maybe_polish(local, [], [], [])
        if out != better:
            problems.append(f"a good polished beat wasn't kept: {s._polish_last.get('why')}")
        if not sent or "FACTS" not in sent[-1][1]["content"] or "Ripples" not in sent[-1][1]["content"]:
            problems.append("the request doesn't carry the facts and the draft")
        for bad, why in (("I'm sorry, but I can't help with that.", "refusal"),
                         (better.replace("— Nerine —\n", ""), "a dropped part label"),
                         ("— Ripples —\nShe breathed.\n\n— Nerine —\nNerine waited.", "a much shorter answer")):
            answer[0] = bad
            if s._maybe_polish(local, [], [], []) != local:
                problems.append(f"{why} was kept instead of the local beat")
        # (build 269) a label that lost its first dash and the chat page's own text copied along with the answer
        fixed = polish.tidy("Worked for 22s · 1 step\nRipples —\nRipples breathed.\n— Nerine —\nNerine waited.",
                            ["Ripples", "Nerine"], local)
        if not fixed.startswith("— Ripples —\nRipples breathed.") or "Worked for" in fixed:
            problems.append(f"a half label or the chat page's text wasn't tidied: {fixed[:60]!r}")
        answer[0] = better.replace("Ripples let her breath out slow", "She let her breath out slow").replace(
            "eyes fixed on Ripples", "eyes fixed ahead")
        if s._maybe_polish(local, [], [], []) == answer[0]:
            problems.append("a polish that left out a fighter was kept")
        # (build 269) your own prompt, and back to the built-in one
        with open(polish.PROMPT_FILE, "w", encoding="utf-8") as fh:
            fh.write("MY OWN EDITOR RULES")
        if polish.messages("x", [])[0]["content"] != "MY OWN EDITOR RULES":
            problems.append("a prompt of your own in polish_prompt.txt isn't used")
        _quiet(H.play.handle_command, s, "/polish prompt reset")
        if polish.messages("x", [])[0]["content"] != polish.SYSTEM:
            problems.append("/polish prompt reset didn't bring back the built-in prompt")
        if not any("condition: health" in f for f in s.polish_facts([], [], [])):
            problems.append("the fact sheet doesn't give each fighter's condition")
        # by hand: /polish copy, then the answer pasted into polish_reply.txt and /polish paste
        cfg["enabled"] = False
        s._maybe_polish(local, [], [], [])
        s.story.append(local)
        s.last_narration = {"args": None, "index": len(s.story) - 1}
        s.beat_records.append({"fight": 1, "lineup": [], "turn": 9, "label": "beat 9", "text": "\n" + local + "\n",
                               "snapshot": {"fighters": []}})
        _quiet(H.play.handle_command, s, "/polish copy")
        if not os.path.exists(polish.REQUEST_FILE) or "DRAFT" not in open(polish.REQUEST_FILE, encoding="utf-8").read():
            problems.append("/polish copy didn't write the request")
        with open(polish.REPLY_FILE, "w", encoding="utf-8") as fh:
            fh.write("Here is the revised beat:\n" + better + "\n")
        _quiet(H.play.handle_command, s, "/polish paste")
        if s.story[-1] != better or better not in s.beat_records[-1]["text"]:
            problems.append("/polish paste didn't put the polished beat in the story and the beat's record")
        # (build 271) several beats by hand: /polish copy 1-3, then one marked answer pasted back beat by beat
        s._polish_hist = []
        beats_ = {}
        for t_ in (1, 2, 3):
            s.eng.turn = t_
            loc_ = local.replace("waiting", f"waiting ({t_})")
            s._maybe_polish(loc_, [], [], [])
            s.story.append(loc_)
            s.beat_records.append({"fight": s.fight_no, "lineup": [], "turn": t_, "label": f"beat {t_}",
                                   "text": "\n" + loc_ + "\n", "snapshot": {"fighters": []}})
            beats_[t_] = len(s.story) - 1
        _quiet(H.play.handle_command, s, "/polish copy 1-3")
        req_ = open(polish.REQUEST_FILE, encoding="utf-8").read()
        if not all(f"=== BEAT {t_} ===" in req_ for t_ in (1, 2, 3)):
            problems.append("/polish copy 1-3 didn't put the three beats in the request by number")
        new_ = {t_: better.replace("patient as stone", f"patient as stone ({t_})") for t_ in (1, 3)}
        with open(polish.REPLY_FILE, "w", encoding="utf-8") as fh:
            fh.write("".join(f"=== BEAT {t_} ===\n{new_[t_]}\n=== END BEAT {t_} ===\n\n" for t_ in (1, 3)))
        _quiet(H.play.handle_command, s, "/polish paste")
        if s.story[beats_[1]] != new_[1] or s.story[beats_[3]] != new_[3] or "(2)" not in s.story[beats_[2]]:
            problems.append("/polish paste didn't put each marked beat back on its own beat (and leave the rest)")
        if not any(new_[1] in r["text"] for r in s.beat_records):
            problems.append("a polished earlier beat didn't reach its record (/exportfight)")
        # (build 272) an earlier beat is checked as the narrator saw it then, and the narrator is put back after
        e1 = s._polish_hist[0]
        e1["_nstate"]["strengths"] = {"Ripples": 100.0, "Nerine": 100.0}
        s.narrator.strengths = {"Ripples": 20.0, "Nerine": 20.0}
        seen_now = s._judge_as_then(e1, lambda: dict(s.narrator.strengths))
        if seen_now != {"Ripples": 100.0, "Nerine": 100.0} or s.narrator.strengths != {"Ripples": 20.0, "Nerine": 20.0}:
            problems.append(f"an earlier beat isn't judged with its own narrator state ({seen_now}, then "
                            f"{s.narrator.strengths})")
        worn_ = e1["local"].replace("and waited too", "and wondered how much Ripples had left in her")
        if s._polish_now(e1["local"], reply=worn_, entry=e1):
            problems.append("an earlier beat's polish with a slip the full checks catch (a fresh fighter called "
                            "worn) was kept")
        # (build 273) the copies on disk: read back after a restart, and only the last keep_fights fights kept
        e2 = s._polish_hist[1]
        if not e2.get("fkey") or not s._load_nstate(dict(e2, _nstate=None)):
            problems.append("a beat's copy of what the narrator knew wasn't saved to polish_states")
        s._polish_hist[1] = dict(e2)
        s._polish_hist[1].pop("_nstate", None)
        if s._polish_now(e2["local"], reply=e2["local"].replace("and waited too",
                                                                "and wondered how much Ripples had left in her"),
                         entry=s._polish_hist[1]):
            problems.append("after a restart an earlier beat's polish didn't get its full checks back from disk")
        for k_ in range(4):
            s.fight_no += 1
            s._save_nstate(dict(e2))
        kept_ = [d for d in os.listdir(s.STATE_DIR) if os.path.isdir(os.path.join(s.STATE_DIR, d))]
        if len(kept_) != int(polish.cfg_of(s.eng.rules).get("keep_fights", 3)):
            problems.append(f"polish_states keeps {len(kept_)} fights, not keep_fights")
    finally:
        polish.call = real
    return problems


def hold_panel_check():
    """Build 257 (window.hold_panel): each card carries the grips on her and by her (which parts, with what, how
    long), how near she is to tapping (the narrator's 1-5 ladder and this beat's real tap chance, 0 on her first
    beat in it), the holder sees it too, her held parts are ringed, the export shows it, and off it is gone."""
    import cards
    s = H.session(1, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    e.rules["finish"]["submission"]["enabled"] = True     # (not /set: that would stay on for the checks after this)
    e.downed["Ripples"] = 0
    e.facing["Ripples"] = "face-down"
    e.start_submission("Nerine", "Ripples", "boston crab")
    levels, chances, log = [], [], []
    for _ in range(5):
        H.beat(s, [{"attacker": "Nerine", "defender": "Ripples", "action": "breather", "flavor": "leans in"}], log)
        if not e.holds:
            break
        fs = {f["name"]: f for f in H.play.fight_snapshot(s)["fighters"]}
        m = cards.tap_meter(fs["Ripples"])
        if not m:
            problems.append(f"no tap meter while she is in the submission: {fs['Ripples'].get('grips')}")
            break
        levels.append(m["level"])
        chances.append(m["chance"])
        held = cards.grip_lines(fs["Ripples"])
        if not held or not held[0][0].startswith("Held: Nerine's boston crab on her ") or "thigh" not in held[0][0]:
            problems.append(f"her card doesn't say who holds which part: {held}")
        if not cards.held_parts(fs["Ripples"]) or cards.held_parts(fs["Nerine"]):
            problems.append(f"the wrong parts are ringed: {cards.held_parts(fs['Ripples'])}")
        hl = cards.grip_lines(fs["Nerine"])
        if not hl or not hl[0][0].startswith("Holding: boston crab on Ripples'") or "% to tap" not in hl[0][0]:
            problems.append(f"the holder's card doesn't show the hold and how near the tap is: {hl}")
        if cards.tap_meter(fs["Nerine"]):
            problems.append("the holder has a tap meter of her own")
    # (since build 283 the steps follow the real chance: none on her first beat, then climbing with it)
    if len(levels) < 3 or levels != sorted(levels) or levels[0] != 0 or chances[0] != 0 or levels[-1] < 1:
        problems.append(f"the tap meter doesn't climb from 0 at 0% on her first beat: levels {levels}, chances {chances}")
    snap = H.play.fight_snapshot(s)["fighters"]
    import fightexport
    body = fightexport._gauges(next(f for f in snap if f["name"] == "Ripples"))
    if e.holds and ("chance this beat" not in body or 'class="grip"' not in body):
        problems.append("the export has no tap meter or hold panel")
    e.rules["window"]["hold_panel"]["enabled"] = False
    if any(f.get("grips") for f in H.play.fight_snapshot(s)["fighters"]):
        problems.append("with window.hold_panel off the cards still carry it")
    return problems


def sub_sells_check():
    """Build 262: the submission sells in story_blocks.txt, story_lines.txt and story_passages.txt (the lock going
    on, her fight against the tap by level, the holder feeling it, the tap, after a tap) are there, true to what
    they are for (a tap line shows a tap; a tap-fight line never does), and offered in a submission beat."""
    import re as re_
    import narrator as N
    import blocks
    problems = []
    lib = {f: blocks.Blocks({"narration": {"blocks": {"file": f, "memory_file": ""}}})
           for f in ("story_blocks.txt", "story_lines.txt", "story_passages.txt")}
    want = {"story_blocks.txt": ["sub_lock_held", "sub_lock_hold", "tap_fight", "tap_fight_hold", "tap_out_held",
                                 "tap_out_hold", "tap_after_held", "tap_hold_back"],
            "story_lines.txt": ["sub_lock_held", "tap_fight", "tap_out_held", "tap_out_hold", "tap_after_held",
                                "tap_hold_back"],
            "story_passages.txt": ["tap_edge", "tap_out"]}
    for f, cats in want.items():
        have = {c for c, _k, _t in lib[f].entries}
        for c in cats:
            if c not in have:
                problems.append(f"{f} has no {c} group")
    for lv in "12345":
        if not lib["story_blocks.txt"].pick("tap_fight", 1, tap=lv, fmt={"part": "left thigh", "foe": "Nerine"}):
            problems.append(f"no tap_fight block for level {lv}")
    for f in ("story_lines.txt", "story_passages.txt"):
        for c, conds, t in lib[f].entries if f != "story_passages.txt" else lib[f].entries:
            if c in ("tap_fight", "tap_hold_back") and N.tap_really_shown(t):
                problems.append(f"a tap-fight line reads as a tap: {t[:70]!r}")
            if c in ("tap_out", "tap_out_held") and re_.search(r"(?i)\btap|slap|beat", t) and not N.tap_really_shown(t):
                problems.append(f"a tap line doesn't read as a tap: {t[:70]!r}")
    # (build 269: over a few seeds, since which side a beat is told from is partly chance, and the held one's ideas
    # come only when the telling reaches her side)
    seen_ = set()
    for seed_ in (1, 2, 3):
        s = H.session(seed_, fighters="Nerine,Ripples")
        e = s.eng
        e.rules["finish"]["submission"]["enabled"] = True
        e.downed["Ripples"], e.facing["Ripples"] = 0, "face-down"
        e.sub_window = {"Ripples": True}
        _out, caps = H.beat(s, [{"attacker": "Nerine", "defender": "Ripples", "action": "submission",
                                 "submission": "boston crab", "flavor": "locks a boston crab"}], [], roll=False)
        txt = "\n".join(m["content"] for msgs in caps for m in msgs if isinstance(m.get("content"), str))
        seen_ |= {lb for lb in ("as it locks on", "fighting the tap (1 of 5)", "holding herself back from tapping")
                  if lb in txt}
        if len(seen_) == 3:
            break
    for label in ("as it locks on", "fighting the tap (1 of 5)", "holding herself back from tapping"):
        if label not in seen_:
            problems.append(f"the first beat of a submission offers no '{label}' idea")
    return problems


def build_261_check():
    """Build 261, from the user's build-260 Ripples vs Nerine log: invented holds checked against what limbs can do
    (holds.invented_check), the director's words put right to the parts it resolves (director.words_to_parts), a
    head butt reaching only what a head can (moves.head_reach), no launch from a blow to the feet (moves.low_launch),
    a catalog submission told with the limbs it uses, the fight against the tap given room every beat
    (narration.tap_fight_shown), and an action sent twice happening once."""
    import director
    problems = []

    def fresh():
        return H.session(1, fighters="Ripples,Nerine").eng

    def hold(e, hits):
        try:
            res, ids = director.resolve(e, {"attacker": "Ripples", "defender": "Nerine", "action": "hold_start",
                                            "flavor": "grabs hold", "hits": hits})
            return [e.holds[i].part for i in ids]
        except ValueError as x:
            return "refused: " + str(x)
    e = fresh()
    if hold(e, [{"part": "Neck", "with": "both paws, squeezing"}, {"part": "Left Foot", "with": "both paws"}]) != ["Neck"]:
        problems.append("one pair of paws gripped her neck and her foot at once")
    e = fresh()
    e.start_holds("Nerine", "Ripples", [("Right Paw", 15, 0, "her paws, clamped on it")])
    if hold(e, [{"part": "Neck", "with": "her right paw"}, {"part": "Chest", "with": "her twin tails, wrapped round"}]) != ["Chest"]:
        problems.append("a paw caught in her grip still gripped")
    e = fresh()
    e.get("Ripples").parts["Left Paw"].damage = e.get("Ripples").parts["Right Paw"].damage = 350
    if "Neck" in str(hold(e, [{"part": "Neck", "with": "her paws"}, {"part": "Stomach", "with": "her twin tails, wrapped round"}])):
        problems.append("devastated paws still took hold")
    e = fresh()
    e.downed["Nerine"], e.facing["Nerine"] = 0, "face-down"
    try:
        e.start_custom_submission("Ripples", "Nerine", "ear wrench", [("Left Ear", "her paws, twisting it")], enforce=True)
        problems.append("an invented submission worked through her ear")
    except ValueError as x:
        if "main grip" not in str(x) and "its main" not in str(x):
            problems.append(f"the ear submission was refused for something else: {x}")
    e = fresh()
    res, ids = director.resolve(e, {"attacker": "Ripples", "defender": "Nerine", "action": "strike", "move": "Tail Bind",
                                    "part": "Right Hip", "flavor": "Ripples' twin tails wrap tightly around Nerine's "
                                                                  "left knee"})
    if "left knee" in str(res.get("flavor")) or "right hip" not in str(res.get("flavor")):
        problems.append(f"the words still name a part the grip isn't on: {res.get('flavor')!r}")
    e = fresh()
    res, _ = director.resolve(e, {"attacker": "Nerine", "defender": "Ripples", "action": "strike", "move": "improvised",
                                  "improvised_name": "Head Butt", "part": "Left Foot",
                                  "flavor": "Nerine rams her head into Ripples' left foot"})
    if [h.get("part") for h in res.get("hits") or []][:1] != ["Chest"]:
        problems.append(f"a standing head butt landed on her foot: {[h.get('part') for h in res.get('hits') or []]}")
    if not director._low_blow(e, {"hits": [{"part": "Left Foot"}]}) or director._low_blow(e, {"hits": [{"part": "Chest"}]}):
        problems.append("a blow to the foot isn't told apart from one to the body for a launch")
    e = fresh()
    e.downed["Ripples"], e.facing["Ripples"] = 0, "face-up"
    r = e.start_submission("Nerine", "Ripples", "heel hook", "Nerine's twin tails wrap tightly round Ripples' left leg")
    if "tails" in str(r.get("flavor")):
        problems.append(f"a heel hook turned with her arm and legs was told with her tails: {r.get('flavor')!r}")
    n = H.session(2, fighters="Ripples,Nerine").narrator
    if n._tap_fight_count("She fought the urge to tap, her fist clenched. Nerine leaned in. Her paw rose and she "
                          "pulled it back.", "Ripples") != 2:
        problems.append("the sentences showing her fighting the tap aren't counted")
    said = n._sign_said("Ripples", n.TAP_URGE["claws"].format(spot="the ground"))
    if said != "Ripples' claws dug into the ground and held there, and she made them stay put.":
        problems.append(f"the program's own tap sign doesn't read right: {said!r}")
    e = fresh()
    acts = [{"attacker": "Ripples", "defender": "Nerine", "action": "breather", "flavor": "wrenches at the grip"}] * 2
    res, _ = director.resolve_many(e, acts)
    if len([r for r in res if isinstance(r, dict) and r.get("type") == "breather"]) > 1:
        problems.append("the same breather sent twice happened twice")
    return problems


def holds_real_check():
    """Build 260, from the user's build-259 Ripples vs Nerine log: a hold as bodies can do it (holds.backstop: a
    chest pressing a standing fighter in the open goes; on the ground or in a bear hug it stays; holds.grip_share:
    one hold, one body's strength), the grip told after the blow that came first, "harmlessly" gone when it hurt,
    the "familiar" clause and the director's "submission opening" mended, and keeping her feet checked as shown."""
    import director
    problems = []
    hits = [{"part": "Twin Tails", "severity": "crushing", "with": "her chest, pressed on it"},
            {"part": "Right Shoulder", "severity": "crushing", "with": "her chest"},
            {"part": "Lower Back", "severity": "crushing", "with": "her forepaws, digging in"},
            {"part": "Left Forearm Fin", "severity": "crushing", "with": "her twin tails, binding them"},
            {"part": "Right Forearm Fin", "severity": "firm", "with": "her twin tails, binding them"}]

    def hold(down=False, wrap=False, only_chest=False):
        s = H.session(1, fighters="Ripples,Nerine")
        e = s.eng
        if down:
            e.downed["Nerine"], e.facing["Nerine"] = 0, "face-down"
        hs = [dict(h) for h in hits]
        if wrap:
            hs[2] = {"part": "Belly", "severity": "crushing", "with": "her arms, wrapped round her middle, hauling her back"}
        if only_chest:
            hs = hs[:2]
        res, ids = director.resolve(e, {"attacker": "Ripples", "defender": "Nerine", "action": "hold_start",
                                        "flavor": "chest on her back", "hits": hs})
        return e, res, [e.holds[i] for i in ids]
    e, res, hs = hold()
    if any("chest" in h.with_part for h in hs) or len(hs) != 3:
        problems.append(f"a chest pressing a standing fighter in the open stayed in the hold: {[(h.part, h.with_part) for h in hs]}")
    if sum(h.power for h in hs) > 60:
        problems.append(f"the hold's grips aren't shared out: {sum(h.power for h in hs):.0f} pressure in all")
    if "chest" in str(res.get("flavor")) or "twin tails on her left forearm fin and right forearm fin" not in str(res.get("flavor")):
        problems.append(f"the hold's words still tell the dropped press, or repeat the limb: {res.get('flavor')!r}")
    e, res, hs = hold(down=True)
    if not any("chest" in h.with_part for h in hs) or len(hs) > 4:
        problems.append(f"on the ground the chest press should stay (and at most 4 grips): {[(h.part, h.with_part) for h in hs]}")
    e, res, hs = hold(wrap=True)
    ch = [h for h in hs if "chest" in h.with_part]
    if not ch or max(h.power for h in ch) > 12:
        problems.append(f"in a bear hug the chest should stay as the anvil at a share: {[(h.part, h.with_part, round(h.power)) for h in hs]}")
    try:
        hold(only_chest=True)
        problems.append("a hold that is only chest presses on a standing fighter went on")
    except ValueError as x:
        if "nothing behind her" not in str(x):
            problems.append(f"the chest-only hold was refused for something else: {x}")
    s = H.session(2, fighters="Ripples,Nerine")
    n = s.narrator
    n.progress = None
    n.species_of = {"Ripples": "Buizel", "Nerine": "Buizel"}
    n._grips_beat, n.grips, n._pov_marks, n._hurt_now, n._strike_parts = {}, [], [], set(), ["Twin Tails"]
    n._blow_then_grip = ("Ripples", "Nerine", "Aqua Jet", ["twin tails", "lower back"], ["her forepaws, digging in"])
    text = ("Ripples eyed her.\n\nHer grip on Nerine was tight, her forepaws dug into her lower back.\n\nRipples "
            "coiled to unleash her Aqua Jet.\n\nAs Ripples charged, the water hit, rippling harmlessly off her.\n\n"
            "Nerine grunted.")
    got = n._engine_mends(text).split("\n\n")
    if got[3:4] != ["Her grip on Nerine was tight, her forepaws dug into her lower back."] or "harmlessly" in got[2]:
        problems.append(f"the grip wasn't put after the blow, or 'harmlessly' stayed: {got}")
    out = n._last_scrub("It was a familiar sensation, but today it felt heavier. The charge would secure a submission opening.")
    if "It was a sensation" in out or not out.startswith("Today it felt heavier") or "submission opening" in out:
        problems.append(f"the familiar clause or the game words weren't mended: {out!r}")
    if not n.STAYED_UP_SAID.search("Her knee buckled and she forced herself straight.") or \
            n.STAYED_UP_SAID.search("She drew herself up to her full height and held there."):
        problems.append("keeping her feet isn't told apart from standing tall")
    return problems


def engine_mends_check():
    """Build 259 (narration.engine_mends, interlude.retold_cut), from the build-254 Ripples vs Nocturne log: the
    prose put right against the engine: "the Buizel" told of the Absol, a grip told on a part it isn't on, the held
    one given the grip; and an interlude sentence that retells the beat in other words goes."""
    s = H.session(2, fighters="Ripples,Nocturne")
    n, problems = s.narrator, []
    n.progress = None
    n.damage_by["Nocturne"]["right hip"] = 120

    def run(text, grips, marks=()):
        n._grips_beat, n.grips, n._pov_marks, n._hurt_now, n._strike_parts = grips, [], list(marks), set(), []
        return n._engine_mends(text)
    cases = [
        ("She could see the wear on Nocturne. The Buizel's fur was matted with sweat and dirt.", {},
         [("She could see the wear", "Ripples")], "Nocturne's fur was matted"),
        ("Ripples watched Nocturne closely. The Buizel's own left forearm fin ached dully.", {},
         [("Ripples watched", "Ripples")], "The Buizel's own left forearm fin"),
        ("Nocturne glared. The Buizel stood tall in the water.", {}, [("Nocturne glared.", "Nocturne")],
         "The Buizel stood tall"),
        ("The Buizel's horn dipped. The Buizel's right hip throbbed.", {}, (), "Nocturne's horn dipped. Nocturne's right hip"),
        ("The twin tails whipped around Nocturne's right knee, wrapping tight.",
         {("Ripples", "Nocturne"): {"left forepaw"}}, (), "around Nocturne's left forepaw"),
        ("Her twin tails tightened around Nocturne's right knee.", {("Ripples", "Nocturne"): {"right hock", "right thigh"}},
         (), "around Nocturne's right hock"),
        ("Ripples wriggled her body, trying to ease the pain, but Nocturne's grip was unyielding.",
         {("Ripples", "Nocturne"): {"right hock"}}, (), "Nocturne wriggled her body, trying to ease the pain, but Ripples' grip"),
        ("Nocturne's grip on the ground slipped as Ripples' hold tightened.", {("Ripples", "Nocturne"): {"left forepaw"}},
         (), "Nocturne's grip on the ground slipped"),
        ("She winced, putting pressure on her right knee.", {("Ripples", "Nocturne"): {"left forepaw"}}, (),
         "pressure on her right knee"),
    ]
    for text, grips, marks, want in cases:
        got = run(text, grips, marks)
        if want not in got:
            problems.append(f"engine mends: {text[:50]!r} became {got!r}, not {want!r}")
    n.rules["narration"]["engine_mends"]["enabled"] = False
    if run(cases[0][0], {}, cases[0][2]) != cases[0][0]:
        problems.append("engine_mends off still changes the prose")
    n.rules["narration"]["engine_mends"]["enabled"] = True
    beat = ("The wind had picked up slightly, carrying with it the scent of the pine needles and the lake. Her left "
            "forearm fin ached dully, but it was a distant pain, overshadowed by the thrill of the fight.")
    inter = ("The breeze picked up again, carrying with it the scent of the pine needles and the lake. A heron lifted "
             "off the far shore, slow wingbeats over flat water. Her left forearm fin ached dully, a distant pain, "
             "overshadowed by the thrill of the fight. But it was nothing.")
    got = n._drop_retold(inter, beat, 0.55)
    if "scent of the pine" in got or "forearm fin" in got or "But it was nothing" in got or "heron" not in got:
        problems.append(f"the retold interlude sentences weren't cut (or the new one was): {got!r}")
    if n._drop_retold(inter, beat, 0) != inter:
        problems.append("retold_cut 0 still cuts")
    return problems


def log_fixes_258_check():
    """Build 258, from the user's build-254 Ripples vs Nocturne log: a tap only counts as shown when it happens
    ("I'll make her tap." and "it was not enough" are not taps); the model's "to continue from where you left off"
    and a stray ", and" left by a cut go; the holder's own name stays out of the grip line ("closed her Ripples' twin
    tails"); an invented hold named for a part has to grip it (no "standing knee lock" on her shoulder); a pain share
    past show_max is shown as 300%+; and the window has its dark colours."""
    import narrator as N
    problems = []
    for text, who, want in (("Ripples set her jaw. I'll make her tap.", "Nocturne", False),
                            ("Nocturne tried everything she had left, but it was not enough.", "Nocturne", False),
                            ("She would not be the one to tap out, Nocturne swore.", "Nocturne", False),
                            ("Nocturne's paw slapped the ground again and again.", "Nocturne", True),
                            ("Nocturne tapped out.", "Nocturne", True)):
        if N.tap_really_shown(text, who) != want:
            problems.append(f"the tap check reads {text!r} as {'no ' if want else ''}tap")
    s = H.session(2, fighters="Ripples,Nocturne")
    e, n = s.eng, s.narrator
    out = n._last_scrub("She waited.\n\nAnd now, to continue from where you left off:\n\nThe pain traced her gaze. "
                        ", and Ripples felt the tremor.")
    if "left off" in out or ", and" in out or "Ripples felt the tremor" not in out:
        problems.append(f"the last clean-up left the meta line or the stray clause: {out!r}")
    n._paragraph_plan("take", [{"type": "hold_start", "attacker": "Ripples", "defender": "Nocturne",
                                "parts": [{"part": "Chest Ruff", "with": "Ripples' twin tails"}]}])
    said = " ".join(x for _, _, x in (getattr(n, "_fact_lines", None) or []))
    if "her Ripples'" in said or "closed" not in said:
        problems.append(f"the grip line names the holder in her own grip: {said!r}")
    e.downed["Nocturne"] = 0
    e.facing["Nocturne"] = "sitting up"
    try:
        e.start_custom_submission("Ripples", "Nocturne", "standing knee lock",
                                  [("Left Shoulder", "her paws, levering it")], enforce=True)
        problems.append("a knee lock on her shoulder went on")
    except ValueError as x:
        if "named for her leg" not in str(x):
            problems.append(f"the knee lock on her shoulder was refused for something else: {x}")
    try:
        e.start_custom_submission("Ripples", "Nocturne", "standing knee lock",
                                  [("Right Hock", "her paws, twisting it")], enforce=True)
    except ValueError as x:
        if "named for" in str(x):
            problems.append(f"a knee lock on her knee was refused: {x}")
    f = e.get("Nocturne")
    f.learned["pain_felt"] = 5000.0
    g = e.pain_gauge(f)["overall"]
    if g.get("shown") != "300%+" or g["pct"] != 300 or not g["label"].startswith("far past"):
        problems.append(f"a share in the thousands isn't shown as 300%+: {g}")
    try:
        import window
    except ImportError:      # (no tkinter in this Python: the window can't be checked here)
        return problems
    window._THEME["dark"] = True
    if window.C("#ffffff") == "#ffffff" or window.C("#111827") == "#111827" or window.C("#22c55e") != "#22c55e":
        problems.append("dark mode doesn't swap the backgrounds and text, or swaps the bright marks")
    window._THEME["dark"] = False
    if window.C("#ffffff") != "#ffffff":
        problems.append("the light window's colours change")
    if not window.dark_on({"window": {"dark": {"enabled": True}}}) is True:
        problems.append("window.dark.enabled isn't read")
    return problems


def tap_urge_check():
    """Build 256 (tap.urge): a hold that hurts but is nowhere near her limit shows the urge to tap now and then (a
    small sign, easily refused, not counted as a refusal), and the narrator is told it; off, nothing shows there."""
    s = H.session(3, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    a, d = e.get("Nerine"), e.get("Ripples")
    e.rules["finish"]["submission"]["enabled"] = True
    e.downed["Ripples"] = 0
    e.facing["Ripples"] = "sitting up"
    e.start_submission(a.name, d.name, "standing armbar")

    def beat():
        e.turn += 1
        for h in e.holds.values():
            h.turns_active += 1
            d.parts[h.part].damage = 0.0
        return e._tap_out_tick()

    urges = []
    for h in e.holds.values():
        h.turns_active = 0                   # (from the hold's very first beat)
    for _ in range(5):                       # (pain up to about 0.73 of her resistance: far from her limit)
        evs = beat()
        if any(x.get("type") == "tap_resist" for x in evs):
            problems.append(f"she is shown fighting not to tap while far from her limit: {evs}")
        urges += [x for x in evs if x.get("type") == "tap_urge"]
    if len(urges) != 5 or urges[0].get("beats_held") != 1 or {u.get("level") for u in urges} != {1, 2}:
        problems.append(f"a submission does not show her fighting the urge every beat from the first, light then "
                        f"heavier: {[(u.get('beats_held'), u.get('level')) for u in urges]}")
    elif any(not u.get("tell") for u in urges) or d.learned.get("tap_refused"):
        problems.append(f"the urge has no sign picked, or counted as a refusal: {urges}, {d.learned.get('tap_refused')}")
    else:
        for u in urges:
            if u["tell"] not in s.narrator.TAP_URGE:
                problems.append(f"the narrator has no words for the sign {u['tell']}")
        for k in ("tap_tell_urge", "tap_tell_urge2", "tap_tell_first", "tap_tell_closer", "tap_tell_edge"):
            missing = set(e.VARIETY[k]) - set(s.narrator.TAP_URGE) - set(s.narrator.TAP_TELLS)
            if missing:
                problems.append(f"signs in {k} with no words in the narrator: {sorted(missing)}")
    e.rules["finish"]["submission"]["tap"]["urge"]["enabled"] = False
    for h in e.holds.values():
        h.turns_active = 1
    if any(x.get("type") == "tap_urge" for _ in range(4) for x in beat()):
        problems.append("with tap.urge off the urge still shows")
    return problems


def match_distance_check():
    """Build 255 (narration.match_state): the engine tracks how far apart the fighters are from what each beat
    resolved, says it to the narrator and the director, and survives an undo snapshot; a fresh fight a few beats in
    is still told as its opening."""
    s = H.session(7)
    e, problems = s.eng, []
    N, R = "Nocturne", "Ripples"
    if e.gap_of(N, R) != "near":
        problems.append(f"before anything has happened they are {e.gap_of(N, R)}, not a few strides apart")
    e.note_gap([{"type": "instant", "attacker": N, "defender": R, "move": {"name": "Slash", "target": "targeted"}}])
    if e.gap_of(N, R) != "close":
        problems.append(f"a blow that landed left them {e.gap_of(N, R)}, not in reach")
    if "a few strides apart; now they are IN REACH" not in e.gap_text():
        problems.append("the narrator's note does not say how far apart they were when the beat began: " + e.gap_text())
    if "DISTANCE NOW" not in e.director_view():
        problems.append("the director is not told how far apart they are")
    e.note_gap([{"type": "breather", "focus": R}])
    if e.gap_of(N, R) != "near":
        problems.append(f"a breather taken in reach left them {e.gap_of(N, R)}")
    e.note_gap([{"type": "instant", "attacker": R, "defender": N, "launch": "thrown", "move": {"name": "x"}}])
    if e.gap_of(N, R) != "near":
        problems.append(f"a throw left them {e.gap_of(N, R)}, not a few strides apart")
    e.note_gap([{"type": "instant", "attacker": R, "defender": N, "move": {"name": "Water Gun", "target": "spread"}}])
    if e.gap_of(N, R) != "near":
        problems.append(f"a ranged move changed the gap to {e.gap_of(N, R)}")
    e.rules["narration"]["match_state"]["enabled"] = False
    if e.gap_text() or "DISTANCE" in e.director_view():
        problems.append("match_state off still says the distance")
    e.rules["narration"]["match_state"]["enabled"] = True
    e.turn = 6
    st = e.story_state()
    if st and not st["stage"].startswith("early"):
        problems.append(f"two untouched fighters at beat 6 are told as: {st['stage']}")
    return problems


def three_tap_check():
    """Builds 247-248, from the narrated three-tap match (sim/test_fights/three_tap): no submission from inside one,
    no upright hold by a holder lying down, takedowns into a hold fit the way she lands, a coil is only the grip that
    wraps, and the holder's posture is told right."""
    s = H.session(5, fighters="Nerine,Ripples")
    e, problems = s.eng, []
    a, d = e.get("Nerine"), e.get("Ripples")
    e.rules["finish"]["submission"]["enabled"] = True
    e.rules["submissions"]["small_joints"]["enabled"] = False
    e.downed.update({"Nerine": 0, "Ripples": 0})
    e.facing.update({"Nerine": "face-up", "Ripples": "sitting up"})
    up = [n for n in e.submission_shapes(a.name, d.name) if set(e.SUBMISSIONS[n]["facing"]) <= {"standing", "sitting up"}]
    if up:
        problems.append(f"a holder lying down was offered upright holds: {up}")
    e.downed.pop("Nerine")
    e.facing.pop("Nerine")
    res = e.start_submission(a.name, d.name, "standing armbar")
    if "holding her on her feet" in e.posture_text(a.name):
        problems.append("the holder of a hold on a sitting fighter is told as holding her on her feet")
    e.sub_window = {a.name: True}
    e.downed[a.name] = 0
    e.facing[a.name] = "face-up"
    try:
        e.start_submission(d.name, a.name, next(iter(e.submission_shapes(d.name, a.name))), enforce=True)
        problems.append("a fighter in a submission locked one of her own on the holder")
    except (ValueError, StopIteration):
        pass
    for _ in range(30):
        tk = e._sub_takedown(a, d, "face-down")
        if tk["how"] == "leg_hook":
            problems.append("a leg hook (a fall backward) was picked for a face-down landing")
            break
        e.downed.pop(d.name, None)
    for hid in list(e.holds):
        e.holds.pop(hid)
    e.downed.update({"Ripples": 0})
    e.facing["Ripples"] = "face-down"
    e.start_submission(a.name, d.name, "tail-bound knee crank") if "tail-bound knee crank" in e.submission_shapes(a.name, d.name) else None
    coils = {h.part: h.coil for h in e.holds.values()}
    if coils and any(v for k, v in coils.items() if "foot" in k.lower()):
        problems.append(f"the paws turning the foot were marked a coil too: {coils}")
    if e.a_an("ARMBAR") != "an ARMBAR":
        problems.append("a/an: " + e.a_an("ARMBAR"))
    return problems


def textpane_check():
    """The window's story pane (textpane.py): story and numbers told apart, the rows' changes and the rolls'
    outcomes coloured, the pointers' numbers taken from the lines they explain, and shown only now and then."""
    import json
    import textpane as T
    with open(os.path.join(H.ROOT, "rules.json"), encoding="utf-8") as fh:
        rules = json.load(fh)
    problems = []
    lines = ["Nocturne's jaws caught Ripples on the left thigh.",
             "    Left Thigh",
             "        damage      🟢 0% → 🟢 17.76%           +17.76 = power 49.49 (rolled ×0.99) × 0.12 × scale 3",
             "        resistance  🟦 113% → 🟦 102.61%        -10.39 = power 49.49 × 0.3 × 0.7 resistance scale",
             "        health      ❤️ 1700% → ❤️ 1686.62%      -13.38 = damage 17.76 × 1.84 × 0.51 × vital 0.8",
             "  Total: +27.61% damage  ·  ❤️ Ripples 1700% → **1677.52%** (-22.48)",
             "⏳ Beat 1 health: ❤️ Nocturne 1679.5% (-0.5% exertion)",
             "    Ripples dodging Nocturne's attack 18%, rolled 26 → it lands"]
    want = ["story", "part", "row", "row", "row", "total", "head", "mech"]
    got = [T.kind_of(x) for x in lines]
    if got != want:
        problems.append(f"lines sorted as {got}, not {want}")
    if "miss" not in [t for _, _, t in T.spans(lines[-1])]:
        problems.append("a roll over its chance is not shown as a miss")
    P, notes = T.Pointers(rules), []
    for x in lines:
        notes += P.feed(x)
    if not any("+17.76" in n and "49.49" in n and "113%" in n for n in notes):
        problems.append(f"no damage pointer with the row's own numbers: {notes}")
    again = []
    for x in lines[1:5]:
        again += P.feed(x)
    if again:
        problems.append("the part pointer came back at once (it should wait pointer_gap beats)")
    if not T.tip(T.term_key("(rolled ×0.99)"), lines[2], rules):
        problems.append("no hover tip for the damage roll")
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
    if not want or any(w in "undo and replay" for w in want):
        t, probs = time.time(), []
        for seed in SEEDS:
            try:
                _undo_replay(seed, probs)
            except Exception:
                probs.append(f"seed {seed}: crashed:\n" + traceback.format_exc(limit=6))
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  undo and replay give the same beat  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p.replace("\n", "\n      "))
    if not want or any(w in "story passages" for w in want):
        t = time.time()
        probs = passage_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  story passages keep to the hard rules  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "tap told last" for w in want):
        t = time.time()
        probs = tap_last_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  the tap or pass-out is told last  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "story pane" for w in want):
        t = time.time()
        probs = textpane_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  the window's story pane sorts and explains the numbers  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "ruined below zero" for w in want):
        t = time.time()
        probs = ruined_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  ruined parts past devastated, and the stages below zero health  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "three tap fight" for w in want):
        t = time.time()
        probs = three_tap_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  three-tap fight fixes: no hold from inside one, upright holds need the holder up, takedowns fit, coils  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "held reach gauge" for w in want):
        t = time.time()
        probs = held_reach_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  held on the ground: reach, the down count, the pain gauge, taps told, body words  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "log fixes 252 steer export" for w in want):
        t = time.time()
        probs = log_fixes_252_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 252 log fixes: steered blows, plain-body type, mends, whose grip, export gauges  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "match distance" for w in want):
        t = time.time()
        probs = match_distance_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 255 match state: how far apart they are, the opening told as the opening  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "sub sells" for w in want):
        t = time.time()
        probs = sub_sells_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 262 submission sells: lock, tap fight by level, the tap, after it  ({time.time() - t:.1f}s)")
        for p in probs[:8]:
            print("      " + p)
    if not want or any(w in "build 261" for w in want):
        t = time.time()
        probs = build_261_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 261: invented holds checked, words to parts, head reach, low launch, the tap fight shown  ({time.time() - t:.1f}s)")
        for p in probs[:8]:
            print("      " + p)
    if not want or any(w in "holds real" for w in want):
        t = time.time()
        probs = holds_real_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 260 holds real: a backstop for every press, grips shared, the grip after the blow, mends  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "engine mends" for w in want):
        t = time.time()
        probs = engine_mends_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 259 engine mends: who is who, the held part, who holds, retold interludes  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "log 258" for w in want):
        t = time.time()
        probs = log_fixes_258_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 258 log fixes: taps really shown, meta lines, grip names, named holds, 300%+, dark window  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "hold panel" for w in want):
        t = time.time()
        probs = hold_panel_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 257 hold panel: grips, parts and tap meter on the cards and the export  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "tap urge" for w in want):
        t = time.time()
        probs = tap_urge_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 256 tap urge: a submission shows her fighting the urge every beat, harder the nearer the tap  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "tap blend" for w in want):
        t = time.time()
        probs = tap_blend_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 264 tap chance from part and health, with a build-up  ({time.time() - t:.1f}s)")
        for p in probs:
            print("      " + p)
    if not want or any(w in "hold mix" for w in want):
        t = time.time()
        probs = hold_mix_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 265 fewer chokes and jaw holds, endurance under a choke, busy limbs  ({time.time() - t:.1f}s)")
        for p in probs:
            print("      " + p)
    if not want or any(w in "busy limbs" for w in want):
        t = time.time()
        probs = busy_limbs_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 266 the holder's busy limbs, her reach from the hold, no charge from a hold  ({time.time() - t:.1f}s)")
        for p in probs:
            print("      " + p)
    if not want or any(w in "story checks" for w in want):
        t = time.time()
        probs = story_checks_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 267 story checks: get-up order, after the tap, the bite's place, move names  ({time.time() - t:.1f}s)")
        for p in probs:
            print("      " + p)
    if not want or any(w in "polish" for w in want):
        t = time.time()
        probs = polish_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 268 polish: kept when it passes the checks, else the local beat; copy and paste by hand  ({time.time() - t:.1f}s)")
        for p in probs:
            print("      " + p)
    if not want or any(w in "tap overwhelm" for w in want):
        t = time.time()
        probs = tap_overwhelm_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 255 tap breaking point: holds out a few beats on a wrecked part (from her strength), then near-certain  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "log fixes 253 body slips" for w in want):
        t = time.time()
        probs = log_fixes_253_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 253 log fixes: break ways, head snaps, one rise, favouring, wet with, thoughts  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "narration mends padding" for w in want):
        t = time.time()
        probs = narration_mends_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  narration mends: tense, fragments, marks, places, the tap, whose it is, padding  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "low health last stand" for w in want):
        t = time.time()
        probs = low_health_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  low health: alone, squirming, tells and a dead limb, wide open after a last stand, the other's read  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "upright nelson" for w in want):
        t = time.time()
        probs = upright_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  upright holds: kept on her feet, borne down in the hold, readjust, invented ones  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "sub match standing ramp" for w in want):
        t = time.time()
        probs = sub_match_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  submission matches: openings on her feet, takedown into the hold, part ramp below zero  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "lakeside273 lakeside" for w in want):
        t = time.time()
        probs = lakeside273_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build-273 lakeside log: wrong limb, posture, paws, fur, memories, retold get-up, kick, &&  ({time.time() - t:.1f}s)")
        for p in probs[:8]:
            print("      " + p)
    if not want or any(w in "presets preset help examples" for w in want):
        t = time.time()
        probs = presets_help_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  match presets, anything-goes match, every command in the help, examples  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "reactions308 endurance face" for w in want):
        t = time.time()
        probs = reactions_308_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 308 body and mind reactions, holds felt and their aftermath, longer holds, the face  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "alive306 monitor settling" for w in want):
        t = time.time()
        probs = alive_306_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 306 living cards and heart monitor, injuries settling in  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "narration305 seraphina305 blackout borne" for w in want):
        t = time.time()
        probs = narration_305_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build 305 narration fixes: black-outs and bearing down shown, tense, bodies, thoughts  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "save load history" for w in want):
        t = time.time()
        probs = save_history_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  a saved fight loads back whole: beat history, story, numbers, /undo  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "compression squeeze constriction" for w in want):
        t = time.time()
        probs = compression_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  compression in a constriction: builds, drives the blood, chest or belly, no nausea  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "head stun body jolts heart" for w in want):
        t = time.time()
        probs = head_body_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  head and body effects, a stunned fighter, the heart stopping and starting again  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "orders players words features" for w in want):
        t = time.time()
        probs = orders_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  players' orders read right; constriction told as blood; parts she has  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "speed offload gpu timing" for w in want):
        t = time.time()
        probs = speed_check_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  the model partly in system memory is pointed out, once  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "constriction coil blood" for w in want):
        t = time.time()
        probs = constriction_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  constriction: the blood, not the breath; heart racing then slowing; blackout; meter  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "tapmeter meter window" for w in want):
        t = time.time()
        probs = tap_meter_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  the tap meter follows the real chance and says what keeps it down  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "unrolled blows preset" for w in want):
        t = time.time()
        probs = unrolled_blows_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  a hold's words don't tell blows the engine never resolved  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "character personality history profile" for w in want):
        t = time.time()
        probs = character_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  character: personality, history, relationships to narrator and Venice, quirk moments, veterans' memories, /profile  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "traits quirks style" for w in want):
        t = time.time()
        probs = traits_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  traits and quirks: rolls scaled, holds, paw grips, switches, style for the director, /traits  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "coilcontest contest coil serpent" for w in want):
        t = time.time()
        probs = coil_contest_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  contest of coils, constriction writing, serpent standing, one tail, grip after it ended, get-up order  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "played276 played ribs side" for w in want):
        t = time.time()
        probs = played276_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build-276 played log: coil orders, doing nothing, past tense, brackets, Tree, tail fan, claws, ribs, side spill  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "seraphina275 seraphina dominate" for w in want):
        t = time.time()
        probs = seraphina275_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  build-275 Seraphina log: blood, for once, side, colour, kept-hold name, coils, serpent feet, trapped paws, dominate  ({time.time() - t:.1f}s)")
        for p in probs[:10]:
            print("      " + p)
    if not want or any(w in "coil size serpent" for w in want):
        t = time.time()
        probs = coil_size_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  big serpents: coils round her middle, harder to escape, no paw to tap with  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "tap meter all" for w in want):
        t = time.time()
        probs = tap_meter_all_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  tap meter: plain holds from their first beat, grabs that don't count yet  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "downtime collapse" for w in want):
        t = time.time()
        probs = downtime_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  not down most of the fight: collapse grace, keeping her feet, holds from the ground  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
    if not want or any(w in "tap count" for w in want):
        t = time.time()
        probs = taps_check()
        failed += bool(probs)
        print(f"{'FAIL' if probs else 'ok  '}  several taps from different parts, and the program's own cuts  ({time.time() - t:.1f}s)")
        for p in probs[:6]:
            print("      " + p)
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
