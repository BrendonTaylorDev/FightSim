# Shared brief for mechanics auditors (FightSim)

You are auditing a Pokémon story-fight simulator in /home/user/FightSim (Python). DO NOT edit any file in /home/user/FightSim. Write test scripts and notes only in your own folder: /tmp/claude-0/-home-user-FightSim/d2e1d57a-2374-5322-b4cf-0e9b328e1377/scratchpad/audit_<GROUP>/. A previous auditor for your group was stopped by a usage limit before it reported. Its scripts are already in your folder, so read and rerun them first to recover what it found, then finish the group.

SAVE AS YOU GO: append each CONFIRMED bug to audit_<GROUP>/report.md the moment you confirm it, so nothing is lost if you are stopped. Finish by rewriting report.md as the full final report.

Find real bugs, not style issues: a field or mechanic that is accepted but silently does nothing, does the wrong thing, crashes, contradicts another mechanic, doesn't show on screen, isn't told to the narrator (check the captured notes), or that the director is never nudged toward or is told something the engine doesn't do. Model bug, already fixed: a strike or pummel with "pinned_against": "an old oak" ignored the oak. Blows against scenery now grind her into it (engine._grind, result key ground_into).

Architecture:
- engine.py: the mechanics.
- director.py: resolve()/resolve_many() turn the director's JSON actions into engine calls; DIRECTOR_PROMPT lists every action field; the *_hint/*_urge functions nudge the LLM director.
- narrator.py: builds the narrator's notes from each beat's results, and runs the checks.
- display.py: the stats block on screen.
- play.py: Session, the commands in handle_command, and the HELP text.
- rules.json: tuning. scenes.json, fighters.json, moves.json: data.

Harness (fake LLM, real engine, display and notes):
```
import sys; sys.path.insert(0, "/home/user/FightSim/sim")
import harness as H, play
s = H.session(1, scene="lakeside forest", settings=[], fighters="Nocturne,Ripples")
log = []
out, caps = H.beat(s, [ {action dict}, ... ], log, roll=False)   # out = screen text; caps[i][-1]["content"] = narrator notes
play.handle_command(s, "/pin Nocturne Ripples")
s.eng   # the Engine
```
Action dicts look like {"attacker":..,"defender":..,"action":"strike"|"combo"|"hold_start"|"hold_adjust"|"hold_release"|"pin"|"struggle"|"throw"|"slam"|"drag"|"grapple"|"submission"|"breather","move":..,"part":..,"count":..,"hits":[{"part":..,"with":..,"severity":..}],"launch":..,"landing":[..],"reposition":..,"pinned_against":..,"sustain":..,"charge_into":..,"feint":..,"flavor":..}. Check DIRECTOR_PROMPT and resolve() for exact formats.

- Fighters: Nocturne (Absol, quadruped, Dark) and Ripples (Buizel, biped, Water); others are in fighters.json.
- The harness runs on a temp copy of the repo, so saving settings is safe.
- Force dice by setting chances in s.eng.rules to 0 or 1.
- Current settings: damage.roll 0.17 (±17% on every instance of damage), pin.first_beat_damage 1.0.

FINAL REPORT (in report.md and as your reply, under 1800 words):
1. CONFIRMED bugs: what's wrong, a minimal repro (script path), the likely file:line, severity (breaks the fight / wrong story / cosmetic), and a suggested fix.
2. Mechanics verified working, one line each.
3. Appendix "COVERED:": every method, rules key and director function from the inventories (/home/user/FightSim/audit/engine_methods.txt, rules_keys.txt, director_funcs.txt) that belongs to your group and that you exercised. Then "IN MY AREA BUT NOT EXERCISED:" for any you skipped. Anything in your area counts, even if it isn't named.
