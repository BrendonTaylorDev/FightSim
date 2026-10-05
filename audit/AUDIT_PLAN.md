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
- [x] A (report_A.md; fixed)  [x] B (report_B.md; fixed)  [ ] C  [ ] D  [ ] E: reports go in `audit/report_X.md` as they come in. (First run: all five were stopped by a usage limit before reporting. Now run ONE group at a time to limit usage, in order A, B, C, D, E; each saves findings to scratchpad audit_X/report.md as it goes, copied here as audit/report_X.md.)
- [ ] Coverage cross-check against the inventories; anything not exercised goes to a second round.
- [ ] Fix every confirmed bug, rerun the regression checks and balance, commit and push.

Balance is checked once, after ALL groups' bugs are fixed (user's call), not after each group. Balance targets: Nocturne wins about 60% against Ripples (never change Ripples' stats); about 8 pins and 1 submission a fight. Check with 400 simulated fights (simulate.one_fight, lakeside forest).

## Requests added during the audit
- **Twisting, worrying and wrenching** in pins and submissions: jaws on the neck twisting, a limb twisted further, a grip worried at. The damage ramp already exists, so this is mostly about showing the tightening in more ways (screen and narrator notes), plus any small damage it should add.
- **Grip continuity after a pin breakout** (from a live log): Ripples' jaws stayed on Nocturne's throat in the story after Nocturne broke out, but the engine had ended every grip. Next beat Ripples had to bite again for a second pin. Either the engine keeps a grip that survives the breakout (and tracks it), or the narrator is told plainly that every grip, jaws included, is off.
- From the same log, checked against the build in use:
  - A pin said "Pressure starts next beat" (first-beat damage is now on).
  - Beats ran 12–15 minutes and the ⏱ line had no breakdown. That log came from a build before the time budget. Confirm the user is on the latest build.
  - Nocturne went far below 0% health (-106%) and the fight went on into a new pin. Is that intended (the fight ends only by pin or pass-out)? Check how health below 0 is handled.

## Later
Speed mechanics: a faster fighter attacks or dodges more, and a stronger one hits harder. Do this after the audit.
