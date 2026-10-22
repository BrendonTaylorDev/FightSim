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
    e, problems = s.eng, []
    a, d = e.get("Nerine"), e.get("Ripples")
    e.rules["finish"]["submission"]["enabled"] = True
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
    if len(levels) < 3 or levels != sorted(levels) or levels[0] != 1 or chances[0] != 0:
        problems.append(f"the tap meter doesn't climb from 1 at 0% on her first beat: levels {levels}, chances {chances}")
    snap = H.play.fight_snapshot(s)["fighters"]
    import fightexport
    body = fightexport._gauges(next(f for f in snap if f["name"] == "Ripples"))
    if e.holds and ("chance this beat" not in body or 'class="grip"' not in body):
        problems.append("the export has no tap meter or hold panel")
    e.rules["window"]["hold_panel"]["enabled"] = False
    if any(f.get("grips") for f in H.play.fight_snapshot(s)["fighters"]):
        problems.append("with window.hold_panel off the cards still carry it")
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
