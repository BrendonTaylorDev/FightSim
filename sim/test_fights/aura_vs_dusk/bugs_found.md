# Aura vs Dusk test fight (build 174): bugs found

Storm forest clearing, scale 4, knockout-only, no pins, seed 91. Dusk won by knockout on beat 36 at -22% health after an adrenaline surge and a last stand. Beat numbers are the export's beats.

## What worked
- Aim: 3 blows slid off target (throat→chest spur twice, ear→dodge), told as OFF TARGET with the console 🎯 line.
- Get-ups used where she lay (the muddy ground, the split oak, the rotten log), never a random prop.
- Whole-body Rock Slide: no rock named by one part. Knockout blow: no stagger left on her. Ground-back under a face-down pummel: ribs and chest, as it should.
- Window, history, back view, weakened look, export: all ran; the window replay matched the plan beat for beat.

## Bugs
 1. Beat 17: Dusk lay FACE-DOWN; the get-up said "rolls onto her front first" (she is already on her front).
 2. Beats 5/10/18: the clash roll reads "meeting Dusk's Rock Slide with one of her own" for a fighter who has no such move (wording of the roll).
 3. Beat 23: Aura "springs back" out of a bite on a knee at 514% (a dodge manner that needs both legs, rolled with no regard for wrecked legs).
 4. Beats 3, 21, 27: every bite that rocks her reads "the jaws drag her toward Dusk before they let go": the bite rock has one wording.
 5. Beat 30: target variety re-aimed a chop at the jaw (the flavor: "up under the jaw") to the Left Hind Paw; the flavor no longer fits what the engine did (the narrator has to drop it).
 6. Beat 32: target variety again moved a punch the flavor puts in the chest to the Right Thigh. Variety overrides a part the director chose 35% of the time, flavor and all.
 7. Beat 1 (the first blow of the fight): "OPEN this part on: the place where the last blow still stings" (there has been no last blow).
 8. Beat 3: Fire Fang (a bite) was offered staging for a fire BLAST: "a ball of flame forms in her mouth and she hurls it", "the fire spits from her in short bursts" (build 174's beam filter misses these wordings).
 9. Beat 3: the movement idea "her head turns with it and comes back slowly" for a chest-spur bite whose engine movement was "the jaws drag her toward Dusk".
10. Beats 2-3: "ALREADY SAID in recent beats: "Aura"" (a fighter's name listed as a used line).
11. Beat 4: for a "springs back" dodge, the ideas offered were "a lean, just enough" and "she sways from the hips": leaning and swaying belong to no dodge family in build 174's filter, so they pass for any dodge.
12. Beat 5: Rock Slide's whole-body list says "Hardest hit: Left Ear, Muzzle, Throat, Jaw" and then "Barely felt: Head, Left Ear, Right Ear, Muzzle, Jaw, Neck": the same parts in both lists.
13. Beat 5: Rock Slide (falling boulders) staged as "a jagged spike of stone erupts from the earth" (that is Stone Edge); rock staging ideas aren't matched to the rock move.
14. Beat 7: Close Combat (a close-range flurry, spread over four parts) was told as "ONE blast that catches all of these parts at once, not separate shots": a spread move that is not ranged is a flurry of blows, not a blast.
15. Beat 8: Stone Edge (a spike of stone) was labelled "Delivered with her CLAWS, as the move says" because the flavor said she "rakes the ground" (raking the ground is not raking her: a weapon word aimed at the ground or scenery should not count), and was offered "She hurled a heavy slab with a grunt of effort".
16. Beat 9: for a pummel whose knee hits took the knee to HURTING, a matchup idea said "her right knee hardly marks; a flush of warmth, and gone".
17. Beat 15: for a "slips to one side" dodge, "she hops the sweep and lands lightly" was offered (a jump: no dodge family covers hops, spins or jumps, so they pass for any dodge).
18. Beat 16: Extreme Speed's notes say "It lands differently because: her hurt right knee" with no "whose": it is the attacker's knee (Aura's), but it reads as the defender's.
19. Beat 18: Rock Tomb leaves her CHILLED (moves.json uses "chilled" for Rock Tomb's slowing), and the notes tell it as "frost in her fur, shivering": a rock move's slow is told as cold.
20. Beat 20: a thought idea "something she was taught once and only now understands" invites a memory from before the fight (another one for the old-memories switch).
21. Beat 25: Fire Fang (a bite) again offered fire-breath staging: "the heat on her own fur makes her eyes water, and she keeps pouring it out", "She drew a long breath, and the air around her began to shimmer".
22. Beat 27: a matchup idea for Dark on a Fighting/Steel body: "like being struck with the very stuff she grew up in" (she is not Dark; and it is a memory of her past).
23. Beat 28: part 3 is Dusk watching from her side, but its END idea is labelled "(from Aura's side)".
24. Beat 31: the devastating-blow "selling it" idea ("she shakes, a deep, steady shaking she can't stop, from the chest spur outward") was offered in the ATTACKER's part (Dusk's side), about the defender's body.
25. Beat 32: a self-look idea "she sees a thin line of blood at the right thigh" after a blunt punch (blood the engine never caused). Part 3 (Dusk's side) again ends "(from Aura's side)".
26. Beat 36 (and others): in a thunderstorm with rain "in sheets", the notes say "fur: Dusk DRY (nothing has wet her yet)": wetness is only tracked from water moves and the creek, not from the arena's weather.
27. Beats 37-38 (aftermath): "FADING THOUGHTS: this beat, Dusk is fading" for the WINNER, who is standing and not going anywhere (she is past the limit on health, but a winner no longer collapses).
28. Beat 38: for Aura, who is "OUT COLD: unresponsive" with no change listed, an idea "the first thing to come back is sound: water, wind, her own breathing far away" (that is coming round).
29. (engine) After the win, Dusk keeps losing about 28 health a beat to pain drain (-22% → -25% over two aftermath beats). Planned change: it eases off once the fight is won.
