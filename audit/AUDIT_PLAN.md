# Mechanics audit (in progress)

Goal: every mechanic works, fits with the rest of the engine and the arena, shows on screen, and reaches the
narrator's notes. Model bug: a strike or pummel with `pinned_against` ran without error but ignored the scenery.
That is now fixed: `engine._grind`, result key `ground_into`.

## How the auditors work
They are read-only: they write test scripts, never edit the repo, and report CONFIRMED bugs, each with a repro, the likely file:line, a severity and a suggested fix. Each report ends with "COVERED:" and "IN MY AREA BUT NOT EXERCISED:", checked against the inventories in this folder:
- `engine_methods.txt` (260 engine functions)
- `rules_keys.txt` (355 settings)
- `director_funcs.txt` (57 director functions)

Tool: `sim/harness.py`. `H.session(seed, scene=..., settings=[...])` and `H.beat(s, [actions], log, roll=False)` return the screen text and the captured narrator prompts. The harness runs on a temp copy of the repo.

## Groups
- **A, grappling and holds:**
  - Grabs: grab_between, slips, point-blank.
  - Pummels: open, in a grab, on the ground, in a pin, against scenery (grind); answered pummels.
  - Moving her: throw, slam, drag, drag to pin, landings; repositions (roll, sit up, pick up, stand up).
  - Holds: start, adjust, release, breaks, regrab_after; coils.
  - Submissions.
- **B, pins:**
  - Openings: pin_chance, pin_urge, `pin_urge.scale` and `/pins`.
  - Pin shapes and the 3-contact minimum; against scenery, wall choke, dunk.
  - Damage: first_beat_damage, ramp, pressure_cap, damage roll.
  - Fade and pass-out.
  - Escapes and the escape blow; pinner fatigue; aftereffects; double pins; in-pin blows; throat hints.
- **C, strikes, falls and reactions:**
  - Launches and landings, auto_launch, knock_on; juggles (including the new chain idea); chains; combos; spillover; devastating blows.
  - Dodges, guards, clashes, feints, caught-open, flinch.
  - Falls: crumple and partial crumple, tumbles, spring_up, getting up.
  - All statuses; stamina; the damage roll on screen.
  - Limping and favouring; limb limits (using ruined parts); pain reactions against the numbers.
  - Damage scaling: `/scale`, resistance, vital weights, caps.
- **D, ranged, charges, environment, targeting:**
  - Ranged and spread moves; held streams; charges (crush, sheath, breaks, onward, crumple); held streams compared with charges.
  - Environment: hazards, arena events, props breaking and staying broken, dunk, weather.
  - Types and STAB; flight.
  - Targeting: focus, variety, weak spots, throat_hint.
  - Director: big moments, tactics, plans, initiative, grudge.
- **E, everything else:**
  - After the win: aftermath, recovery, healing, the summary.
  - Learning and stances; teams and 3+ fighters.
  - Modes: `/play` and its modes, `/autofight`, `/simulate`, `/newfight`.
  - Energy and health; evasion counters; slips and shake; scene events; pinfall; variants.
  - Move rules: recoil, missed charge, repeat limits, multi_hit, jolts, guarding_wound, into_mouth, improvised and one-off moves, `/learn`.
  - Persistence: undo, reroll, save, load, autosave.
  - Sweep of every command in HELP.
- **Afterwards:** a pass over the narrator's own checks (tense, missing hits, anatomy...), same approach.

## Status
- [ ] A  [ ] B  [ ] C  [ ] D  [ ] E: reports go in `audit/report_X.md` as they come in.
- [ ] Coverage cross-check against the inventories; anything not exercised goes to a second round.
- [ ] Fix every confirmed bug, rerun the regression checks and balance, commit and push.

Balance targets: Nocturne wins about 60% against Ripples (never change Ripples' stats); about 8 pins and 1 submission a fight. Check with 400 simulated fights (simulate.one_fight, lakeside forest).

## Later
Speed mechanics: a faster fighter attacks or dodges more, and a stronger one hits harder. Do this after the audit.
