# Group B report: pins

16 confirmed bugs. Repro scripts were in the session scratchpad (audit_B/).

## Answers to the open questions
- **Grips after an escape:** the escape removes every hold the pinner had on her (engine.py ~6034), and the notes say so. The live-log contradiction was the narrator's own, and no check caught it (B4).
- **Health below 0%:** intended. The ❤️ figure is health points, so -106% on Nocturne (max 1860) is about 5.7% under zero. Only a finished pin ends the fight. Below zero, her escape chance is about 3% and pin openings come 95% of the time; she went out in 4–7 beats in 28 of 30 test pins.
- **first_beat_damage 1.0:** the screen now says the presses land now. "Pressure starts next beat" appears only at 0.

## Bugs
1. **B1:** `_pin_against` only matches a prop's last word when it has 4+ letters ("an old oak" fails), and "a boulder" doesn't match the long prop name. The wall_choke hint is dropped. Fix: use `engine.scene_prop_for`.
2. **B2:** an asleep or frozen pinned fighter still struggles and breaks loose (attempt_p, part_try, a director struggle).
3. **B3:** an escape that throws the pinner down always says "no jaws, apart", even when a kept grip is listed.
4. **B4:** no check catches the pinner's jaws "still locked" after an escape (the live-log item).
5. **B5:** in a double pin, the escape blow lands on a random pinner, but the screen, notes, checks and stats name the lead. Also: "is thrown off" grammar; the helper's position isn't stated; the faint line names only the lead.
6. **B6:** a bare /pin:
   - leaks the director's hint text into the label (`(say so with "pinned_against"...)`);
   - a bare dunk sets no pinned_against;
   - ignores contacts.min and shape weights of 0;
   - pin_shapes can give 2 contacts.
7. **B7:** the dunk is narration only. No soaked, no sputtering, and in_water is unset. The notes say both "dunk" and "fur DRY".
8. **B8:** the pin label isn't rebuilt after `_refit_holds` moves presses (Throat to Neck).
9. **B9:** pins and hints still use a prop that has already broken.
10. **B10:** coil_crush by a tailed fighter makes no coil holds: short_phrase cuts "wound round" before is_coil sees it.
11. **B11:** adding one grip to a running pin pads it to 3+ more presses (8 presses, pressure x2.7). A pile-on is filled onto parts already pressed.
12. **B12:** a pinner can dodge and counter a third fighter at the full rate (the same gap in _guard).
13. **B13:** two jaws grips in one pin. throat_hint suggests it, and pin/hold_start accept it.
14. **B14:** `/pins off` is bypassed by a stuck submission, which forces the pin opening.
15. **B15:** the no-clock pin mode leaks "(second 10)" when a double-pin pinner is knocked off.
16. **B16:** pin-escape learning never records anything (the shape is computed after the holds are removed).

## Verified working
- **Openings:** openings and /pins, pin_chance by strength, pin_allowed refusals.
- **Starting a pin:** director contacts are filled to 3; the takedown is told.
- **Pressure:** damage (ramp, cap, mult, time factor).
- **Passing out:** choke kinds; pain share; elimination.
- **Escapes:** escape odds and modifiers; the escape blow is shown and checked.
- **Pinners:** double pin with a pinner knocked off; pinner asleep; a throw or slam on the pinner; a hold that joins the pin; pin energy.
