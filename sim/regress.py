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
    known = {"hit", "cut", "bite", "choke", "choke_out", "held", "holding", "pinned_start", "pinned", "pinning", "landing", "air_fall", "air_tumble", "knockout"}
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
    h.grab, h.turns_active = True, 4
    d.parts["Left Thigh"].damage, d.health = 300.0, -50.0
    e.rules["finish"]["submission"]["tap"]["climb"]["start"] = 1.0
    rolled = []
    for _ in range(12):
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
