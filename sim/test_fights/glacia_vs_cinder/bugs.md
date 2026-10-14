# Bugs found in the Articuno vs Charizard test (wt3)

1. **A charge between two flyers became a dive** (beat 6, Flare Blitz). Fixed.
   - What happened: the blow knocked Glacia out of the sky first. The air-pass/dive check after the hit then saw a grounded defender, so it ran the dive: "she comes down to land", the ground-catch and strike-back rolls, and the climb-or-land roll.
   - Fix: move_attack records whether the defender was airborne before the blow (`d_up`) and uses that.
2. **A flyer knocked out of the sky still rolled to rake back "as they cross"** (beat 6). Fixed: no rake-back once the blow has grounded her.
3. **Ice Shard listed as "close"** in the move lists while the engine treats it as ranged. Fixed: both lists use is_ranged.
4. **Healthy flyers fell out of the sky too often** (three times in eight beats, at 91-98% strength). Tuned.
   - Cause: the knock-from-air chance added up the damage of every part a blow hit. A whole-body Hurricane (427% spread over 15 parts) counted like one crushing blow and hit the 90% cap before the strength easing.
   - Fix: the worst hit counts in full and the rest at 30% (`flight.knock_from_air.spread_share`).
5. **A flyer hit by a "thrown" effect (Flare Blitz 40%, Hurricane 20%) always fell**, whatever her strength. Added `flight.air_recover`: she may catch herself on her wings.
   - The chance is 60% at full strength, 30% at half and 0 when spent, lower with a hurt wing.
   - Moves that always throw (Seismic Toss) still bring her down.
   - It shows in the console and in the narrator's notes ("she catches herself on her wings").
6. **Flight tuning, measured over 40 auto-played Articuno vs Charizard fights:**

   | Strength | Time in the air (before → after) | Fall chance per hit in the air (before → after) |
   |---|---|---|
   | 90%+ | 40% → 58% | 26% → 12% |
   | 70-90% | 23% → 34% | 42% → 23% |
   | 50-70% | 15% → 14% | 74% → about 45% |
   | below 50% | 3% → 4% | above 75% → above 75% |

   - Worn flyers still come down easily.
   - New knock_from_air settings: base 0.25→0.15, per_damage 0.004→0.003, per_wing_damage 0.0025→0.0015, health_mult full 0.4→0.3 and half 1.0→0.8.
7. **Seismic Toss got a ranged "clash" roll** because the new is_ranged rule matched "hurls". Anchor Shot ("an anchor-like strike") was also counted as ranged. Fixed: grabs, grips, seizes, swings and strikes are close moves.
8. **Flight at any strength (your request: only below 10% should it be very hard).**
   - A wing at 600% no longer bans flight. This is now a switch, `strain.max_wing_grounds`, off by default.
   - The take-off cost for a hurt wing is capped at 2× (it was about 30 energy at 370%, which blocked flight in practice).
   - Wing strain stops snowballing: it counts the wing's damage only up to 250%.
   - Below 10% strength, taking off is a roll: 30% just under 10%, falling to 5% at nothing left (`flight.weak_takeoff`). A failed try shows in the console and the narrator's notes.
   - Hurt flyers get knocked down less often, and the director is pointed at taking off more when hurt.
   - Measured in auto-played fights:

   | Strength | Time in the air | Fall chance per air hit |
   |---|---|---|
   | 90%+ | 58% | 14% |
   | 70-90% | 38% | 23% |
   | 50-70% | 26% | 36% |
   | below 50% | 11% | 40-57% |

   - Below 50%, fighters spend half their beats lying down, which is what limits flying there.
9. **"Lands on her talons"** was in the narrator's landing note for every flyer, dragons included. It now says "on her feet". The take-off note no longer says "her opponent left on the ground looking up" when the opponent is already flying.
10. **The director's variety pass re-aimed a blow whose flavor text named its target** (beat 19: "across the frosted head" landed on the shoulder), so the narrator got two places for one blow. Fixed: a blow whose flavor names its part is not re-aimed.
11. **Pin shape descriptions said "jaws clamped on her neck" for a beaked pinner** (the contacts already said "her beak"). Fixed: the description uses her own biting part.
12. **A flyer knocked out of the sky could not be knocked out by the fall.** A knockout is rolled only for blows that pile up or hit all at once, including a drop from a height, but being struck out of the air didn't count as a drop. Fixed: it counts as "fall out of the sky".
13. **Every harness and regress run left a full copy of the game in /tmp** (about 500 copies and 5,000 save folders, about 4 GB of the session's disk). Fixed: both are deleted when the run ends. Old ones were cleared.
