# Group A report: grappling, holds, manhandling

16 confirmed bugs. Repro scripts were in the session scratchpad (audit_A/t*.py) and are not kept in the repo.

1. **A1** `grapple` ignores the regrab cooldown. The check is only in start_holds, engine.py:4709.
2. **A2** `count` is unclamped for move "none" and for improvised moves. They skip the pummel rules, and count 6 did 25% of max health for 2 energy. resolve() doesn't clamp count either. Move "none" also ignores pinned_against.
3. **A3** A fighter in a plain hold can dodge, and even counter, her holder's blows. Fix in dodge_chance.
4. **A4** Mutual grabs coexist. The comment says the reverse grab ends, but nothing ends it.
5. **A5** An easing hold drains to power 0 and stays on forever.
6. **A6** A tightening hold ramp has no cap (+3 a beat forever; power 77 after 20 beats).
7. **A7** The jaws (or any limb) can strike while clamped in a hold, pin or submission.
8. **A8** After "pick up" or "stand her up", she can dodge the follow-up.
9. **A9** A refused reposition is dropped silently, but the director's words still reach the narrator.
10. **A10** Grind accepts any surface ("the ground" for a standing fighter, props not in the scene), and counts spill parts as blows.
11. **A11** A broken prop can be ground into and break again (it stays in scene_props).
12. **A12** `holds.shaken` never fires at the current health scale.
13. **A13** throw, slam and drag work on an airborne defender.
14. **A14** hold_adjust on several holds shows only the first on screen.
15. **A15** Grabs, manhandling, holds and pins skip confusion.
16. **A16** "braces flat against the stone" is hardcoded. A resisted drag is listed as dodged and missed.

## Twisting and worrying grips
- **Exists:** tone rules; JOINT_LOOK; submission "cranks it harder"; coil "TIGHTEN"; hold_adjust "TIGHTENS".
- **Missing:**
  - No twist mechanic.
  - Plain hold and pin ramps are never told to the narrator.
  - Press looks don't escalate with what is gripping or how long.
  - The screen never says a grip is ramping.
- **Suggestion:** a per-beat escalating line keyed to the gripping limb, the same on screen, and an optional twist on hold_adjust.

## Verified working (summary)
Grab slip, point-blank, grapple refusals, throw and slam from a grab, landings and tumbles, drags (resist, soak, scrape, drag to pin), every pummel type, grind breaking in a grab, repositions and press refit, coils, first-beat damage, break roll, hold_release becoming a strain or struggle, submissions (shapes, urge, ramp, sub_stuck, regrab).
