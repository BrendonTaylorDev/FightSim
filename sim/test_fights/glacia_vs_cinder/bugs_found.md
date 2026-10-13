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

## Narrator-note bugs the writers logged (being fixed now)

The four writers logged 315 notes in total. Many are duplicates, and many were already fixed by the changes above. The full lists:


### narr_bugs_00-11

- General: the brief says each CALL carries a POV header ("— Name —"); none of notes01-11 has one. Each CALL gives a part focus ("from the attackers' bodies" / "what each fighter who is actually HIT feels") but no single POV fighter.
- General: FIGHTERS calls them "A female Articuno" / "A female Charizard", and the move lines say "SUPER EFFECTIVE" and "(Ice-type move ...)". The story's author wants no species or game words; the notes push them at the narrator.
- Beat 1 (call 1, item 2): "Cinder's Left Wing (on her ARM, not a leg)". Her wings grow from her upper back; she also has separate arms.
- Beat 1 (call 1, item 3): Cinder's take-off says "Show her rising and her opponent left on the ground looking up." Glacia already took off in item 1; she is in the air.
- Beat 1 (call 1, Hit 1): "a hit here shows as a hand or paw pressed to the chest". Glacia has no hands or paws (her own BODY note says so).
- Beat 1 (call 1, CHECKED): "fur: Glacia DRY ..., Cinder DRY". Neither has fur (feathers; scales).
- Beat 1 (call 1, ORDER): "2) Cinder's Flamethrower lands on Glacia's chest." Leaves out the right wing, the worse of the two hits and the burned part.
- Beat 1 (call 1, TELLING THE HURT): "as one long breathless sentence carrying the whole flurry". There is no flurry: two single hits.
- Beat 1 (call 2, blocks 2-3): "she flexes the limb once and plants it again"; "she smooths her stance with a small roll of her weight". Cinder is in the air; a wing is not planted and she has no stance.
- Beat 1 (call 2, blocks 6, 10): "her eyes go wet and blank, and then focused and furious"; "a wild urge to run, felt all through her". Far too big for a minor hit on a fresh fighter.
- Beat 1 (call 2, block 11): "she takes a breath and holds it, wound tight, before the move". Part 2 starts after both moves are made.
- Beat 1 (call 2): 11 of 12 blocks are Cinder's. Glacia, who took the worse hits (sore wing, burn, chest), gets one block; nothing for her chest or the burn.
- Beat 1 (call 6): "Cinder throwing it" for a Flamethrower, a stream of fire.
- Beat 2 (call 1, Hits 1-2): "a snarl of pain"; "a sharp exhale through the teeth, the lips drawn back"; "a ripple of the skin across the back". Glacia is a bird: no teeth, no lips, feathered skin.
- Beat 2 (call 1, block 2): "her wings sit tight and neat along her back, ready to snap open". Glacia is flying all beat; her wings are open and beating.
- Beat 2 (call 1, block 3): "a flicker of something like regret" for Cinder, fresh and cocky, after one clean exchange. Doesn't fit her.
- Beat 2 (calls 1-2, CAMERA): "one paw, one breath, an eye, the fur over a wound". Neither fighter has paws or fur. (Same generic line in every beat.)
- Beat 2 (call 2, focus): "the fall or landing ONLY if one is listed ... (otherwise she keeps her feet)". She is in the air; there are no feet to keep.
- Beat 2 (call 2, blocks 2 and 5): "her crest flattens and rises in slow pulses" and "her crest flares bolt upright and stays there, quivering". Two crest reactions in one part, and they contradict.
- Beat 3 (call 1, Hit 1): "Cinder's Left Wing (on her ARM, not a leg)" again (also beats 7, 9, 10 wherever her left wing is hit).
- Beat 3 (call 1): "Glacia's burn flares on her right shoulder" (console agrees: "Glacia's burn: Right Shoulder 10.52% → 12.96%"). The burn came from the Flamethrower on her right wing; the shoulder was only jarred by the claws. CURRENT CONDITION still lists the burn under Right Wing.
- Beat 3 (call 1): "It lands differently because: burned." Doesn't say the burn makes Glacia's beam WEAKER (×0.85). Reads as if Cinder were burned.
- Beat 3 (call 1, block 5): "She hurled the cold forward in a sharp, freezing gust." Ice Beam is a beam, not a gust.
- Beat 3 (call 2, block 9): "the ache in her tail flame sits at the base of her horn, a dull pressure behind her eyes". Wrong body part: the tail flame is at the end of her tail.
- Beat 3 (call 2, block 10): "her left wing screams" for a part that is only hurting. Too big.
- Beat 4 (call 1): "THE SOUND OF THE BLOW: the scrape of claw on hide." Air Slash is blades of wind, no claws, and Glacia has feathers, not hide.
- Beat 4 (call 1, Hit 2): "a yowl, the head whipping round". A yowl is a cat sound, not a bird's (also beat 1, Cinder's Hit).
- Beat 4 (call 1, LINGER): "she isn't driven anywhere new and doesn't leave the ground". She is in the air all beat. Same line in other airborne beats.
- Beat 4 (call 2, block 8): "her right wing will not close into a grip without shaking". A wing can't grip.
- Beat 4 (call 2, block 1): "she takes the limb out of the front of her guard". Glacia has no guard of limbs; she is flying on that wing.
- Beat 4 (call 2, block 12): "outrage, sharp and almost comic, as if she had been cheated at a game". Doesn't fit her calm, detached voice.
- Beat 4 (call 2, block 13): "END this part on ... the dust settling round her". She is high in the air; there is no dust.
- Beat 5 (call 1, LINGER): "slow time down on the blow to Glacia's beak". It lingers on the smallest hit (a minor rake-back), not the main blow. It also sits in part 1 (Glacia attacking, "STOP at contact"), and part 2 is Cinder's side, so neither part can hold it.
- Beat 5 (call 1): the rake-back block doesn't say what Cinder rakes with (claws? tail?). Console only says "Cinder rakes back at Glacia" and hits the Beak. The console also prints the rake before the Wing Attack's hits, while ORDER says "1) Glacia's Wing Attack ... 2) Cinder rakes back".
- Beat 5 (call 1, Hit 1): "a tremendous blow (impact, e.g. a keening whine through clenched teeth, tears starting" for a hit that ends only sore on a fresh fighter. Too big.
- Beat 5 (call 1): "Right Wing (hurting; from the burn, then Cinder's Air Slash)". This drops the Flamethrower, which caused the burn. Beat 4 said "from Cinder's Flamethrower, then the burn".
- Beat 5 (call 1, block 2): "the shape of the ground behind the other, and where it dips". Both are in the air.
- Beat 5 (call 2, blocks 3, 8): "her muzzle takes the strain her head can no longer take" is too big for sore. "her horn goes up and wide": she has two horns.
- Beat 6 (call 1, item 1): "IN THE AIR, BOTH OF THEM: ... then they are past each other and turning. Both stay up." The next line says "the blow KNOCKS Glacia OUT OF THE AIR ... She FALLS". These contradict.
- Beat 6 (call 1, item 2): "Glacia is THROWN by that blow". Console rolled "Flare Blitz: thrown 40%, rolled 94 → no"; she fell because she was knocked out of the air. The console header "Impact — Glacia thrown: the bare rock" has the same mislabel.
- Beat 6 (calls 1-5): the recoil on Cinder (Right Horn, Left Shoulder) has no part to live in. Part 1 stops at contact, part 2 is Glacia's side, part 3 is Cinder watching. ORDER leaves it out too, and in the item it is listed before the chest hit it comes from.
- Beat 6 (call 1): "THE LAST ATTACK THAT LANDED ... on Glacia: Cinder's Air Slash." Wrong: Cinder's rake-back on her beak in beat 5 came after it.
- Beat 6 (call 1, VISIBLE WEAR): "her chest: the feathers raked off in strips, the skin beneath raw-looking". "Raked off in strips" is claw work, not fire, and goes close to the gore limit ("torn ... flesh").
- Beat 6 (call 1, CHECKED): "a sharp cry, bared teeth, eyes watering". Glacia has no teeth.
- Beat 6 (call 1, block 5): "Her claws dug in for purchase and threw her forward." Cinder is in the air; there is nothing to dig into.
- Beat 6 (call 2, blocks 6, 7, 4): "her eyes are dull and wet and do not quite focus", "Every touch to her chest ... wrung a cry from her", "comes down limp". These conflict with the same call's MEASURED PAIN ("she is still STRONG ... recovers within a breath").
- Beat 6 (call 2, block 8): "her stance stays where it is, but her weight eases off the hurt side". She is knocked out of the sky and lands on her back; she has no stance.
- Beat 6 (call 5, focus): "she watches from where she stands". Cinder is in the air.
- Beat 6 (call 5, block 5): "she stands light on her feet, knees soft, ready to spring". This is labelled "what Cinder can see of Glacia", but Glacia is on her back and Cinder is flying.
- Beat 6 (call 5, block 3): "the effort it takes just to turn over". Glacia stays exactly where she fell; nothing turns her over.
- Beat 7 (call 1, GETTING UP): "Cinder is on her feet when it happens". Cinder is in the air.
- Beat 7 (calls 1-5): the get-up has no part. Part 1 is Glacia attacking up to contact, part 2 is Cinder hit, and part 3 is Cinder watching with "no getting up". The console's checker then flagged "get-up not finished".
- Beat 7 (call 1, VISIBLE WEAR): "Cinder: her left wing: frost-stiff scales, the scales mussed where it landed". The wing hurt is the membrane, and Cinder hasn't landed.
- Beat 7 (call 1, Hit 2): "her knees dipping under it (a limp if it is a leg)" and "a yowl bitten off short". She is flying.
- Beat 7 (call 1, block 5): "care, almost fussy, in how she places each paw". Glacia has no paws, and she is lying on her back.
- Beat 7 (call 1, blocks 7-8): "the beam leaves a line of churned, smoking ground behind it" (Freeze-Dry is a mist breathed straight up into the air) and "she moves in on the other's breath out" (she is flat on the rock and can't move in).
- Beat 7 (call 2, blocks 2, 6): "she backs off a step" (she is in the air); "the blow numbs her forearm and her paw opens on its own, fingers splayed". The hit is on her wing, not her arm (the wing-on-ARM label again).
- Beat 7 (call 6): "a terrible, devastating blow". The left wing ends very painful, not devastated.
- Beat 7 (call 1, FIGHT SO FAR): "Flare Blitz → Glacia's Chest (thrown: the bare rock)". She was knocked out of the air, not thrown (see beat 6).
- Beat 8 (call 1, item 2): the per-part list gives Head, Right Horn, Muzzle, Eyes and Throat, but no entry for the Left Wing (to excruciating, the BREAKING POINT) or the Tail Flame (to hurting). These are the two hits that matter most.
- Beat 8 (call 1, item 2 vs MEASURED PAIN): "describe the whole body seizing" vs "no whole-body seizing or shuddering". These contradict.
- Beat 8 (call 1): "THE SOUND OF THE BLOW: a booming impact that rolls away through the trees." There are no trees, only a few stunted pines, and nothing echoes here (SOUND IN THIS PLACE).
- Beat 8 (call 1, item 3): "Cinder is THROWN by that blow". Console rolled "Hurricane: thrown 20%, rolled 67 → no"; she fell when she was knocked out of the air.
- Beat 8 (call 1, ORDER): "Glacia's Hurricane lands on Cinder's head". It hits her whole body, and the worst is the left wing. CALL 5 likewise: "on the head, left horn, right horn, a terrible, devastating blow". Nothing became devastated.
- Beat 8 (call 1, LINGER): "the blow to Cinder's muzzle" (sore). Wrong choice when the left wing hits its breaking point this beat.
- Beat 8 (call 1, Hits): "an irritated flick of the ears" (twice). Cinder has no ears in her APPEARANCE. Also "the limb snatched up off the ground" for the thigh while she is falling.
- Beat 8 (call 1, block 7): "anger at being made to work this hard, in the set of her ears". Glacia has no ears.
- Beat 8 (call 2, blocks 6-8): "she holds that arm tucked" (it is a wing), "she shudders hard", "a whimper came out of her whenever it swung". The last two break MEASURED PAIN for a fighter at 92%.
- Beat 8 (call 1): the MEASURED PAIN block for Glacia's chest is repeated, though Glacia takes no hit this beat.
- Beat 7-8 (CURRENT CONDITION): "Left Wing (excruciating; from Cinder's straining her hurt wing to stay up, then Glacia's Hurricane)". Only the last two causes are kept, so the Ice Shard, Ice Beam and Freeze-Dry that did most of it drop out (same for Glacia's chest and right wing).
- Beat 9 (call 1, PREVIOUS BEATS): "(none: this is the FIRST beat of the fight. Nobody has attacked anyone yet, so nobody has any earlier injuries ...)". This is beat 9, and the same call's FIGHT SO FAR lists 8 attacks.
- Beat 9 (call 1, GETTING UP): "Glacia is on her feet when it happens". She is in the air.
- Beat 9 (call 1, GETTING UP): "Try 1: partway up, her left wing and right wing give out". She "plants her hands on the bare rock and pushes herself up", so her wings don't hold her up and can't give out.
- Beat 9 (call 1): "CHILLED: frost in her fur" and Left Horn "the fur rippling where it landed". Cinder has scales.
- Beat 9 (call 1): Left Wing and Tail Flame are "Hardest hit" but get no per-part entry (same as beat 8). The checker then reports them missing (call 7).
- Beat 9 (call 2, block 3): "*Count her steps. She steps before she swings.*" Glacia is hovering; she neither steps nor swings.
- Beat 9 (call 5): Icy Wind "striking Cinder on the head, left horn, right horn, a terrible, devastating blow". This is the weakest attack so far (power 7), and nothing became devastated.
- Beat 10 (call 1): Glacia "MOVES LIKE THIS EVERY BEAT: limps badly, keeping weight off her right wing", and HOW THEY MOVE NOW: "keeps her right wing tucked in and uses it as little as she can". She is flying on that wing (WING STRAIN). A wing doesn't limp.
- Beat 10 (call 1): the PAIN GUIDE "excruciating = Overwhelming pain: screams, may collapse or writhe" is printed next to MEASURED PAIN "no ... writhing or collapse, no 'overwhelming'". These contradict (also beats 8-9).
- Beat 10 (call 1, FIGHT SO FAR): "Icy Wind → Cinder's Head, Left Horn, Right Horn". It hit her whole body (same for Hurricane in beat 9's list).
- Beat 10 (call 1, block 2): "a promise to herself not to try the same trick a third time". No trick of Cinder's has been used twice.
- Beat 10 (call 2, blocks 5, 7): "she holds the limb clear of everything" and "She could not lift her right wing; she tried, and the cry ... ended the trying". She stays up on that wing all beat.
- Beat 10 (call 2, blocks 2 and 6): "every feather on her body lifts at once" and "her feathers puff out all over her, every one on end". The same reaction twice.
- Beat 10 (call 5): "this right wing was first hurt 10 beats ago" (it was beat 1, 9 beats ago), "cold sweat under the fur", "her own paw or limb shaking". No fur or paws.
- Beat 10 (call 5, blocks 10, 12): "a tearing cramp ... that doubles her over it" (breaks MEASURED PAIN; she is flying) and "END this part on ... the ground under her" (she is in the air).
- Beat 10 (call 6): "a terrible, devastating blow". The right wing ends excruciating, not devastated.
- Beat 11 (call 1): the breather says "she stops beating and spreads her wings flat on the updraft ... gliding", but WING STRAIN says "Show the effort and the pain of each wingbeat". Gliding costs the wing more (+50.94%) than flapping did last beat (+45.97%).
- Beat 11 (call 1): Glacia's Right Wing goes from excruciating to DEVASTATED this beat (CURRENT CONDITION), but there is no BREAKING POINT note, and CHECKED gives only "Glacia DEVASTATED (chest)".
- Beat 11 (call 1): "MOVES LIKE THIS EVERY BEAT: won't put any weight on her right wing". She is gliding on it.
- Beat 11 (call 1): Cinder "Stamina: fresh breath", up from "breathing hard" in beat 10, though she took no breather and strained her wing again.
- Beat 11 (call 1, block 1): "OPEN this part on ... the other's weight, settling". Cinder is in the air; there is nothing for her to settle on.

### narr_bugs_12-23

- Beat 12 (all calls): PREVIOUS BEATS / "The beat so far" / "THE PASSAGE SO FAR" contain only "Placeholder prose." and one stray line ("Cinder got her feet under her at last and stood, swaying."). The narrator gets no real prior prose, and that stray line describes Cinder standing, when she is in the air at the start of beat 12 (she took off in beat 10).
- Beat 12 (call 1): Cinder's MOVES LIKE THIS EVERY BEAT says "keeps her left wing tucked in, unusable", and HOW THEY MOVE NOW says "keeps her left wing tucked in and uses it as little as she can". But she is IN THE AIR and the WING STRAIN line says she flies on that wing. A dragon can't fly with one wing tucked.
- Beat 12 (call 1, Hit 1 impact): "a keening whine through clenched teeth, tears starting". Glacia has a beak, no teeth (her own BODY note says so).
- Beat 12 (call 1, Hit 3 impact): "the muzzle wrinkling hard, the teeth showing". This is wrong for a bird with no muzzle and no teeth.
- Beat 12 (call 1, Hit 1): "her knees dipping under it (a limp if it is a leg)". She is in the air when the punch lands, so there are no knees to dip.
- Beat 12 (call 1, block 2): "she cannot stand straight; her chest folds her". Glacia is gliding in the air, not standing.
- Beat 12 (call 1, block 6): "She jabbed once to measure, then threw the real one." This invents a second blow. The console shows a single Thunder Punch.
- Beat 12 (call 2, block 5): "her legs fold and unfold under her as if they were arguing". This is a standing reaction, but she is knocked out of the air and falling.
- Beat 12 (call 2, block 4): "her wings flare out wide and stay there, shaking". This conflicts with "won't put any weight on her right wing" / "keeps her right wing tucked in", and with the fall: her hurt wing "can't catch her".
- Beat 12 (call 5): "she watches from where she stands". Cinder is in the air all beat.
- Beat 12 (call 5, block 4): "she sees the other glance at the ground, measuring a fall that has not come yet". By part 3 Glacia has already fallen and lies face-up on the rock.
- Beat 12 (call 5, block 5): "her crest is raised and bright, standing tall above her eyes". This doesn't fit a bird just knocked flat by a very painful neck blow. The crest has not been hurt, but "raised and bright" reads as confident or display.
- Beat 12 (call 6): it calls the Thunder Punch "a terrible, devastating blow". The Neck ends at very painful (123%), the Throat stays minor and the Left Eye is sore. "Devastating" mislabels it.
- Beat 12 (call 1, CHECKED): "fur: Glacia DRY". Glacia has feathers, not fur. CAMERA lines also say "one paw ... the fur over a wound", and the PART text says "(ears, tails, fins, claws, eyes)". These are generic, not fitted to a bird.
- Beat 12 (calls 3, 4, 7): the rewrite loop reports the same missing hits three times ("it never showed these hits landing: Neck, Throat, Left Eye, Upper Back, Right Shoulder, Right Thigh"). Part 2 alone can't show the punch landing, because part 1 is told to stop at contact. So the checker ran the parts as if each one should hold all the hits. It repeats itself and wastes rewrites.
- Beat 13 (call 1): PREVIOUS BEATS says "(none: this is the FIRST beat of the fight. Nobody has attacked anyone yet, so nobody has any earlier injuries...)". This is beat 13, and the same notes list ten earlier attacks and many old injuries.
- Beat 13 (call 1, GETTING UP): "Cinder is on her feet when it happens". Cinder is IN THE AIR all beat.
- Beat 13 (call 1): Cinder's MOVES LIKE THIS EVERY BEAT still says "keeps her left wing tucked in, unusable" while she is in the air and straining that wing (same as beat 12; it recurs every airborne beat).
- Beat 13 (call 1): FIGHT SO FAR is called "the ONLY earlier attacks that really happened", but it drops Glacia's Ice Shard and Cinder's Flamethrower from beat 1 (beat 12's list had the Flamethrower, now it's gone too). The list looks capped at 10.
- Beat 13 (call 1, block 9): "the beam narrows to a point as she bears down on one spot". Air Slash is blades of wind, not a beam. Block 8 "leaves, grit and loose grass": there's no grass on the bare rock shelf.
- Beat 13 (call 1, drop on try 2): "the fur rippling where it landed". Glacia has feathers.
- Beat 13 (call 2): part 2 is "Cinder's side ... what it feels like to receive it", but the clash means nothing reaches Cinder; Glacia takes all three hits. The part plan also never puts the three get-up tries in any part, which is why the checker kept asking for them (calls 3-6, 8).
- Beat 13 (call 1): Glacia is "winded" and "Shakes off big hits within a moment and gets straight back up", yet the console has her need three tries to rise.
- Beat 14 (all calls): the system HARD RULES say "Pain never goes numb: even the worst-hurt parts stay sharply, terribly painful, never numb or past feeling", but Hit 3 says "her chest GOES NUMB with it: the pain cuts out all at once". The two orders contradict.
- Beat 14 (call 5): the chest has just gone numb, yet part 3 asks for "the hurt arriving, spreading and settling, the chest first", and block 4 gives "her heart seems to beat against the sore place". Neither fits a numb chest.
- Beat 14 (call 5): "this chest was first hurt 14 beats ago, by Cinder's Flamethrower". The Flamethrower was beat 1, so that is 13 beats ago.
- Beat 14 (call 5): "cold sweat under the fur", "her own paw or limb shaking". Glacia has feathers and no paws.
- Beat 14 (call 5, block 5): "her talons feel loose and far away, as if the hurt in her right wing had cut the strings to them". A wing injury has nothing to do with her talons.
- Beat 14 (call 2, blocks 5, 8; call 5, block 1): "each breath brings a whimper", "a shudder runs from it right through her", "a fine tremor that starts at the chest and runs out through the rest of her". MEASURED PAIN in the same notes forbids whole-body shuddering at 74%.
- Beat 14 (call 2, block 4): "the force crashes into her with a roar". This is a claw rake (sound given as "a ripping hiss"), not a roaring blow.
- Beat 14 (call 1, Hit 3): the Chest is a jarred side hit at half power (power 11.8), but it is labelled "a tremendous blow", while the aimed Belly hit is only "a heavy blow". Call 7 again calls the whole Dragon Claw "a terrible, devastating blow" (the Belly ends only sore).
- Beat 15 (call 1): Glacia's chest went numb in beat 14 for 3 beats (console: numb until beat 17), but CURRENT CONDITION lists only "Chest (devastated ...)" and CHECKED says "Glacia DEVASTATED (chest) ... in deep pain and it shows". Nothing tells the narrator the chest is numb.
- Beat 15 (call 1): "THE SOUND OF THE BLOW: a creak of freezing fur". Cinder has scales.
- Beat 15 (call 1, block 4): "she holds the hurt arm folded close against her body and fights with the other". It is her left WING that is hurt, not an arm.
- Beat 15 (call 1, block 8): "a short burst first, to find the range, and then the long one". This invents a second shot; the notes themselves say "ONE blast".
- Beat 15 (call 2, block 9): "tears ... running into her fur". Scales again. Block 7, "she flinches from her opponent's next feint", invents a feint the engine didn't decide.
- Beat 15 (call 5, block 4): "she blinks and watches the world slide and come back, and checks it again, and again". CHECKED says "the world doesn't blur or spin", and Cinder wasn't dazed (no daze roll this beat).
- Beat 15 (call 6): Ice Beam again called "a terrible, devastating blow" (Neck ends hurting, Head very painful).
- Beat 16 (call 1, Hit 8 Chest): "her voice: a scream (*Aaah*); her reaction: small: a wince, a grunt or a sharp breath". A scream and a small reaction contradict each other. The same hit says "lasting pain still numb with shock", while CURRENT CONDITION lists "Chest (devastated ...)".
- Beat 16 (call 1, Hit 5 / Hit 7): "an irritated flick of the ears", "the muzzle wrinkling hard, the teeth showing". Glacia has no ears, muzzle or teeth.
- Beat 16 (call 1): PAIN GUIDE "excruciating = ... screams, may collapse or writhe" against CHECKED "no writhing", and Glacia's line still says "Shakes off big hits within a moment and gets straight back up" next to MEASURED PAIN "she is worn now, so more of it gets out".
- Beat 16 (call 1, block 8): "the left wing comes through the strike late and weak". Seismic Toss is a grab and throw with the arms; the wing takes no part in it.
- Beat 16 (call 1): "She lies where she fell", but the same notes say she ends "SITTING, slumped sitting against the cliff face ... She does not end lying flat".
- Beat 16 (call 5): part 3 is all about "that blow to her chest", which is numb and the smallest-feeling hit of the beat. The BREAKING POINT ("Glacia's Neck has just become EXCRUCIATING ... It is the biggest moment of this beat") gets no part of its own. Blocks 1 and 6 ("the ache settles into the chest", "it only lies there and hurts") and call 2 blocks 1, 6, 9 (bruise "aches with every heartbeat", whimpers) don't fit a numb chest.
- Beat 16 (call 5): "this chest was first hurt 16 beats ago" (it was 15), "cold sweat under the fur", "her own paw or limb". Same off-by-one and fur/paw text as beat 14.
- Beat 16 (call 6): Seismic Toss called "a terrible, devastating blow", with the Throat sore and the Left Shoulder minor.
- Beat 17 (calls 1-2): the part plan has only "Glacia acts, up to contact" and "Cinder receives ... bring the beat to rest". Neither part holds the three get-up tries or "THE FEELING COMES BACK in Glacia's chest", which the notes call a moment to give "its own moment". The checker then asks for the get-up again in calls 3, 4, 6, 7 and 9. Same structural gap as beat 13.
- Beat 17 (call 1): the notes don't say where the numbness wearing off falls against the get-up (the console has it after she stands).
- Beat 17 (call 1, Hit 2 Belly): the impact "a yelp that cracks in the middle" against the voice "a grunt, more surprise than pain (*Uff*)". The two clash for one sore hit.
- Beat 17 (call 2, block 9): "she clutches at the spot with both paws, her breath gone". Too big for a sore belly, and she is not breathless (no roll). Block 10, "her head snaps round with it", contradicts HOW IT MOVES HER (flinches in on herself, square at once); her head was not hit. Block 1, "a faint buzz ... like a limb that has been slept on", reads as numbness, not cold.
- Beat 17 (call 2, block 11): "END this part on: a drop, falling" could read as somebody falling. Nobody falls this beat.
- Beat 17 (call 1, block 5): "frost creeps over the ground ahead of the beam". Freeze-Dry here is a breathed mist (the order says so), not a beam.
- Beat 17 (call 1, GETTING UP): "she beats her wings against the bare rock". She is slumped in the loose scree against the cliff face (beat 16), so the surface is wrong.
- Beat 18 (all calls): the console rolls "Glacia's right wing going numb 30%, rolled 10 → it goes NUMB" (it wears off in beat 21), but the notes never mention it. Leaves out something important; beat 19's order even says "her right wing has gone dead and numb".
- Beat 18 (call 1): "Hardest hit: Chest ..., Neck ..., Right Wing ..." but only Head, Crest, both Eyes, Neck and Throat get a hit line. Chest and Right Wing get no detail, yet the checker then demands "these hits landing: Chest, Neck" (calls 3, 4, 7).
- Beat 18 (call 6): "Cinder's Heat Wave ... striking Glacia on the head, crest, beak". Those are the first parts in the list, not the main ones (Chest, Neck, Right Wing); this mislabels where the blow landed. It is also again "a terrible, devastating blow".
- Beat 18 (call 1, block 9): "she fires in short pulses, each one aimed at the last place she hit". Heat Wave is one whole-body surge; the notes themselves say "Do not narrate it as a series of separate strikes". Block 8, "a gout of flame", doesn't fit a wave of heat either.
- Beat 18 (call 2, block 4): "the beam pours onto her head". Heat Wave is not a beam. Block 2, "her crest feels heavy and hot, the hurt in her right wing beating at its roots", mixes crest and wing.
- Beat 18 (call 2, block 9): "she screams and clutches the chest, rocking over it". She has no hands to clutch with, and rocking is past MEASURED PAIN ("does not collapse or writhe").
- Beat 18 (call 1, Head / Left Eye): "the muzzle wrinkling hard, the teeth showing" again for a beaked bird. Call 5 block 4, "the snarl is gone": Glacia never snarled.
- Beat 19 (call 1): "It lands differently because: Glacia's hurt right wing", and MOVES LIKE THIS "won't put any weight on her right wing". The order has her strike with her LEFT wing because the right has gone numb (beat 18). The console applies "× 0.6 (Glacia's hurt right wing)" too, so the engine may pick the wrong wing. The right wing's numbness is still not mentioned anywhere.
- Beat 19 (call 1, block 7): "a double strike, both wings at once, from either side". Her right wing is numb and devastated, and the notes say "This is ONE strike, not several".
- Beat 19 (call 1, block 2): "she holds her left wing with her other paw, wrist in palm". Cinder's wings grow from her back; she can't hold one in her hand like an arm.
- Beat 19 (call 1): Glacia's status "OFF BALANCE: her last blow was turned aside". It wasn't turned aside: it landed, and she overcommitted.
- Beat 19 (call 1): for Cinder's head, MEASURED PAIN forbids "overwhelming" and says she keeps it in, while PAIN GUIDE "excruciating = Overwhelming pain: screams, may collapse or writhe" and BREAKING POINT "the instant the pain becomes too much to hold in" say the opposite.
- Beat 19 (call 2, block 6): "she shakes her head and nearly falls". The engine says "her feet stay where they are, no stumble". Call 5 block 5, "the movement makes the whole place swing", contradicts CHECKED ("the world doesn't blur or spin"); her daze roll failed.
- Beat 19 (call 5): "this head was first hurt 15 beats ago, by Glacia's Wing Attack". That was beat 5, so 14 beats ago (the same off-by-one as beats 14 and 16). It also has "cold sweat under the fur" for a scaled dragon.
- Beat 20 (call 1): "THE SOUND OF THE BLOW: the dry rip of claws through fur". Air Slash is blades of wind thrown from above; there are no claws and Glacia has no fur.
- Beat 20 (call 1, block 3): "she flinches when her own right wing brushes her ribs". The right wing is numb until beat 21 (console), so she can't feel it brush her; the numbness is still never mentioned.
- Beat 20 (call 2, block 2): "the swooping blow rakes over her upper back and leaves a long scrape". Cinder doesn't swoop; she slashes from above at range. Block 4, "a hot ache", fits fire, not a wind-blade.
- Beat 20 (call 1, Long Tail): "the tail whipping round as if to strike back" against MOVES LIKE THIS "keeps her long tail stiff and close".
- Beat 20 (call 5): Air Slash is again "a terrible, devastating blow" (Upper Back ends hurting).
- Beat 20 (calls 1, 2): Cinder's "MOVES LIKE THIS EVERY BEAT: keeps her left wing tucked in, unusable" in the same notes that have her take off and fly on it (WING STRAIN). This recurs every airborne beat.
- Beat 21 (call 1, Hit 1): "Cinder's Left Wing (on her ARM, not a leg)". Her wing grows from her back; it is not on her arm (the notes' own BODY says "wings on her back AND arms").
- Beat 21 (call 1, Hit 2 Left Upper Arm): "a shiver along the coat; a hit here shows as a limp in the next step". She has scales, not a coat, she is in the air, and an arm doesn't limp.
- Beat 21 (call 2, block 6): "the paw drags along the ground". Cinder is IN THE AIR all beat.
- Beat 21 (call 2, block 10): the left wing was "already hurt before this beat, by Cinder's straining her hurt wing to stay up". That leaves out Glacia's Ice Shard (beat 1), Ice Beam, Freeze-Dry and Icy Wind. Call 5 then says "first hurt 21 beats ago, by Glacia's Ice Shard" (beat 1, so 20 beats ago).
- Beat 21 (call 1, block 11): "irritation at a blow that landed short". No blow of Glacia's landed short.
- Beat 21 (call 1, block 4): "the wing on the hurt side is held out from her body, stiff", in the same notes as MOVES LIKE THIS "keeps her left wing tucked in".
- Beat 21 (call 1): "THE FEELING COMES BACK in Glacia's right wing ... Give it its own moment", but parts 2 and 3 are both Cinder's side, so no part holds it. Same gap as beat 17.
- Beat 21 (call 9, interlude): "If both are on their feet they may circle a little". Cinder is in the air on a devastated wing, and the interlude says nothing about holding her there for "about 900 words" of stillness (no WING STRAIN). Its examples, "sweat or water cooling on fur", "trampled ground, a broken branch, water clouded", are generic and don't fit a bare rock shelf or these bodies.
- Beat 22 (call 1): Glacia is at her lowest yet (32%, exhausted), but there is no MEASURED PAIN line for her, and CHECKED gives a pain cap only for Cinder. Nothing caps how big her reactions should be.
- Beat 22 (call 1): "She SEES it coming at her chest ... and flinches", but Cinder aims at the NECK and it strays onto the chest ("OFF TARGET"). Then "Glacia is GUARDING her chest ... which leaves her back open", yet the bite lands on the chest. These contradict each other.
- Beat 22 (call 1): both Chest and Neck "GO NUMB" in the same hit (against the hard rule "Pain never goes numb"). The Neck gets "a raw scream (*AAAH*)" as it goes numb. Call 2 blocks 1-2, "each twitch is its own separate agony", "her neck burns and freezes by turns, and she cannot bear either", and call 5 block 1, "the stillness aches", all contradict two parts that have just gone numb.
- Beat 22 (call 1, Chest): "a hand or paw pressed to the chest"; block 2 "she is clutching her chest openly now"; call 2 block 6 "she staggers, arms out". Glacia has no hands, paws or arms.
- Beat 22 (call 1): Cinder's status "OFF BALANCE: her last blow was turned aside". It wasn't turned aside: it landed off target and she overcommitted (same mislabel as beat 19).
- Beat 22 (call 6): Fire Fang is again "a terrible, devastating blow" (here at least it fits the chest).
- Beat 23 (calls 1-2): "Cinder shakes off being off balance: show it wearing off (she gets her feet back under her ...)". Cinder is IN THE AIR all beat.
- Beat 23 (calls 1-2): Glacia's chest and neck went numb in beat 22 for 3 beats, but CURRENT CONDITION lists both only as "devastated" and nothing says they are numb. There is again no MEASURED PAIN or pain cap for Glacia (CHECKED covers only Cinder).
- Beat 23 (call 2, block 1): "she holds the hurt wing stiff, gliding on it instead of beating, and loses height steadily". This is word for word the same block as beat 13 call 2.

### narr_bugs_24-35

- Beat 24 (both calls): Cinder is IN THE AIR with WING STRAIN on the left wing, but MOVES LIKE THIS EVERY BEAT says "keeps her left wing tucked in, unusable" and HOW THEY MOVE NOW says "keeps her left wing tucked in and uses it as little as she can". She can't fly with it tucked. (Same as beat 12, still there.)
- Beat 24: FIGHT SO FAR says "Cinder: Heat Wave → Glacia's Head, Crest, Beak". The beat 18 console shows Heat Wave hit 22 parts; the worst were Chest, Neck and Right Wing (all past 300%). Head, Crest and Beak were among the lightest. Mislabeled.
- Beat 24: FIGHT SO FAR claims to be "the ONLY earlier attacks that really happened; never mention any other", but it lists only the last 10 (from beat 13). The same notes cite older attacks as causes ("Chest (Cinder's Flare Blitz)", "from Glacia's Hurricane, then Glacia's Icy Wind", "from Cinder's Thunder Punch"), which that list forbids mentioning.
- Beat 24: the console (beat 22) put Glacia's Chest and Neck NUMB for 3 beats (and her Right Wing NUMB in beat 18). The notes never say so, and the hard rule says "Pain never goes numb: even the worst-hurt parts stay sharply, terribly painful, never numb". Contradicts the console.
- Beat 24: Cinder's VISIBLE WEAR says her head has "cold-burned patches gone numb and white". Same clash with "Pain never goes numb".
- Beat 24 (call 2): the STYLE SAMPLE shows a fighter being struck in the face ("The blow came from her blind side and rocked her head round"). Beat 24 is a breather with no blow. Wrong kind of moment.
- Beat 24 (call 1): CHECKED "fur: Glacia DRY", CAMERA "one paw ... the fur over a wound", focus line "(ears, tails, fins, claws, eyes)": generic, not fitted to a bird (Glacia) or a scaled dragon (Cinder). (Same as beat 12.)
- Beat 25 (call 1): PREVIOUS BEATS says "(none: this is the FIRST beat of the fight. Nobody has attacked anyone yet...)". This is beat 25. Not the placeholder: a wrong claim that contradicts the CURRENT CONDITION in the same call.
- Beat 25: "Hardest hit: Left Wing, Head, Tail Flame, Right Eye". Right Eye only ends sore; the Neck (to very painful) is left out, though part 3 is built on the neck. There are no per-part lines at all for Left Wing, Head, Tail Flame, or the Belly (sore → hurting in the console).
- Beat 25 (Neck line): "her knees dipping under it (a limp if it is a leg)". Cinder is in the air.
- Beat 25 (part 2, block 2): "the strike lands squarely on her horn and it hums". Blizzard is a whole-body storm, not a strike on a horn.
- Beat 25 (part 2, block 6): "as if she had been struck by lightning". This clashes with CHECKED "no electricity... lightning".
- Beat 25 (part 2, blocks 3/4): "she cradles the limb against herself" and "holds it half open, unable to fold it cleanly". She is flying on that wing, and the notes also say it is "tucked in". All three contradict each other.
- Beat 25 (call 6): "Glacia's Blizzard ... striking Cinder on the head, left horn, right horn, a terrible, devastating blow". The console hit 36 parts. The Left Horn only went minor (13→23), and "landing devastatingly → no". Wrong parts and wrong size.
- Beat 25: the console shows "Cinder's left wing going numb ... it goes NUMB". The notes don't mention it, and they still say "Pain never goes numb".
- Beat 25: THE FEELING COMES BACK is given twice, word for word, once for the neck and once for the chest ("She cannot hold this in: a raw sound torn out of her..."). That repeats, and it asks for two separate seizures in one beat.
- Beat 25 (part 3): "cold sweat under the fur". Cinder has scales. Block 2 "makes her whimper" doesn't fit Cinder's voice (a bellow that breaks into a growl).
- Beat 25: Cinder's MOVES LIKE THIS EVERY BEAT adds "keeps her tail flame stiff and close". The flame is the tail's tip, so it can't be held "close" by itself (it should be the tail).
- Beat 26 (part 3): "she watches from where she stands. She does not close in". Cinder has just been dragged out of the air and lies face-down on the stone.
- Beat 26: no part is given the catch and the drag-down. Part 2 says "the fall or landing ONLY if one is listed (otherwise she keeps her feet)" and is about Glacia, who doesn't fall. Cinder's fall gets no part of its own. The notes don't say how a wingless-armed bird "catches" her, or what Cinder lands on. (The console shows no landing hurt either, though the author's rules say the ground hits back.)
- Beat 26: "This beat is an ordinary exchange... with no more drama than it carries". Cinder is pulled out of the sky. That is a turning point.
- Beat 26: "THE SOUND OF THE BLOW: a raspy swish and the tug of fur parting". Glacia has feathers. Hit 2 voice "a yelp (*Yip*)" is a dog sound, not a bird's.
- Beat 26 (Hit 3, Chest): "a tremendous blow ... a raw scream". This is only the half-power jar from a wing rake (power 14.59); the console says "more than a blow that size should". "Tremendous" oversizes it.
- Beat 26 (call 6): "Dragon Claw ... a terrible, devastating blow". The console says "landing devastatingly → no", and the Left Wing ends hurting. Mislabel (also in beat 25).
- Beat 27 (pin presses): "SHE REACTS: her ears flatten" (Cinder has no ears in her description), "LOOKS: the fur pushed flat round it" (neck) and "the fur ruffled the wrong way" (left wing). Cinder is scaled, and her wing is membrane.
- Beat 27 (Left Wing press): "still numb with shock — the part is RUINED: even steady pressure on it is agony". This contradicts itself, and the hard rule says "Pain never goes numb". The console says "NUMB: it lands dull".
- Beat 27 (part 1, block 6): "She kept her head up and out of reach of anything that might snap at it." Her beak is pressed into Cinder's neck as part of the pin.
- Beat 27 (part 2, block 5): "She kicked at anything she could reach." This is struggling, but the struggle is beat 28. No struggle is listed in beat 27.
- Beat 28: "THE PIN GOES ON: Glacia's pin on Cinder holds through this beat" sits just above "YOU MUST SHOW THIS: Cinder BREAKS FREE!". These contradict each other.
- Beat 28 (part 1): the focus is "the pin as it stands, from Glacia's side", but every block is Cinder's: "OPEN this part on (from Cinder's side)", "Cinder's thought", "what Cinder feels". Wrong POV.
- Beat 28 (part 3): "she WATCHES what she has just done to Cinder. Her grip and her weight stay exactly as they are: she watches from where she holds her." The pin has just been broken and Glacia was knocked off, and Glacia did nothing to Cinder this beat.
- Beat 28 (pin presses): "the coat creased under it, the fur parting", "the coat dimpled under it, the hairs bent over flat". Cinder is scaled.
- Beat 29: "THE SOUND OF THE BLOW: a ripping hiss as the claws drag." Air Slash is blades of air thrown from a distance. Glacia has no claws and isn't touching Cinder.
- Beat 29 (part 1, blocks 6/7): "she shoves into it" and "she follows the stagger in, keeping her off balance". Glacia takes off and strikes from range. Cinder only staggers because of this blow, so there's no stagger to follow. These invent contact and movement.
- Beat 29 (part 1, block 3): "she holds the hurt arm folded close". The hurt part is Cinder's left WING.
- Beat 29 (Head stagger): "her paws scraping and skidding for grip". Cinder stands on her feet, and the notes' own rule says her paws are her hands.
- Beat 29: there are two BREAKING POINT blocks (Head, Neck), and each says "It is the biggest moment of this beat".
- Beat 29: Glacia is in the air with WING STRAIN on her right wing, but MOVES LIKE THIS still says "won't put any weight on her right wing". This is the same flying-with-a-tucked-wing clash as Cinder's.
- Beat 30 (part 1, block 11): "She leapt up and brought both wings down at once". Glacia is diving out of the air, not leaping, and the order says only the left wing strikes (her right is ruined). Block 10 "aims under the breath" points at the chest, but the target is the Head.
- Beat 30 (part 2, block 9): "broken gasps and sobs". Sobbing is forbidden by the hard rules.
- Beat 30 (part 3, block 2): "she yelps, then whimpers". This doesn't fit Cinder's voice (a bellow breaking into a growl).
- Beat 30 (part 4, block 5): "how she places each paw". Glacia has talons; the notes' own BODY rule says never paws. Block 3 "her wings droop loose at her sides and the tips trail" contradicts the left wing "tucked in".
- Beat 30: Cinder's CURRENT CONDITION says "OVERALL 21% ... (exhausted) ... Gasping" and then "Stamina: fresh breath". These contradict each other (the surge refilled energy, but the label reads as if she's rested).
- Beat 30 (Head hit): it's "a tremendous blow ... a raw scream", yet HOW IT MOVES HER says "her head rocks back, more than a blow that size should". The two size it differently.
- Beat 31 (part 1, block 3): "the guilt of a clean hit on someone already hurt". Nothing lands; the attacks cancel out. Block 7 "she feels the other give a little, then come back, then give again" is a tug-of-war, but the engine has them cancel at once.
- Beat 31 (part 2): "The attack has ALREADY been shown above, miss and all". It wasn't a miss, it was a clash. Also, part 1 is told to "STOP at contact: leave how it lands", so no part is told to show the clash itself, and the rewrite loop then asks for it (call 5).
- Beat 31: "Don't add another element: no electricity, fire, ice, or water unless the move itself is that type". The clash needs Glacia's Ice Shard (ice), so the rule clashes with the event.
- Beat 31: "It lands differently because: dazed; Cinder is riding an adrenaline surge". Nothing lands.
- Beat 31 (part 2, block 1): "a pebble skittering off the edge and not landing" repeats beat 24's block word for word.
- Beat 32: "This beat is an ordinary exchange in the run of the fight". Nobody attacks, and Glacia drops to SPENT for the first time, which is the moment this beat should carry. The label doesn't fit.
- Beat 32: Cinder's "Stamina: fresh breath" sits next to "OVERALL 20% (exhausted) ... Gasping" (same clash as beat 30). Her FIGHT SO FAR line "running out of fight" also clashes with the surge she is still riding.
- Beat 33 (part 1, blocks 7/8): "a hook round the outside of the guard, into the side" and "she comes from the side the other is guarding least". The punch is aimed at, and lands on, the guarded Chest.
- Beat 33: "This beat is an ordinary exchange... no more drama". Cinder's surge ends and she drops to SPENT, and Glacia's ruined chest takes the biggest hit of the fight. This mislabel repeats beats 26 and 32.
- Beat 33 (part 1): block 10 "a small, fierce joy" and block 12 "frustration; she hits harder than she needs to" pull opposite ways in the same moment.
- Beat 34: the order is cut off: "she does the one thing she was made for: spreads her ragged wings and drags herself up off." (the outline has "...up off the shelf into the wind").
- Beat 34 (part 1): "Focus of this part: the actions as they happen, in order, from the attackers' bodies". Nobody attacks. Part 2: "The attack has ALREADY been shown above, miss and all". There is no attack and no miss.
- Beat 34 (part 1, block 1): "OPEN this part on: the other's limb, drawing back" suggests Cinder winding up a strike. None is listed.
- Beat 34: "wings snap open and beat hard ... she climbs out of reach" is too big for a SPENT fighter whose order says she "drags herself up".
- Beat 34: FIGHT SO FAR gives both fighters "cornered, and at her most dangerous for it", including Cinder, who "has had much the better of it". It also says "an ordinary exchange" again.
- Beat 35 (part 2, block 7): "she drops her chin and the blow meant for her throat thuds into her jaw instead". The blow is aimed at the Chest and lands on the Left Wing, and Glacia has no jaw.
- Beat 35 (part 2, block 8): "her left wing was glad of the bad placing". The blow landed ON the left wing (to excruciating). Part 1 block 8 "her best blow spends itself on the meaty side instead of the hurt one" is wrong for the same reason.
- Beat 35 (part 1, block 7): "the wind of her rising throws grit in the other's face". Glacia is already in the air, out over the drop.
- Beat 35: "THE SOUND OF THE BLOW: the dry rip of claws through fur". Glacia has feathers. Hit 1 "a limb scrabbling at the ground" and Hit 2 "her knees dipping under it" are ground reactions, but both fighters are in the air.
- Beat 35 (part 2, block 11): "Glacia's left wing was already hurt ... by Cinder's Air Slash and then Cinder's Thunder Punch". Air Slash (beat 20) hit the Upper Back and Long Tail. The left wing was hurt by Heat Wave, Dragon Claw (beat 26) and Thunder Punch.
- Beat 35: "Cinder TAKES TO THE AIR: wings snap open and beat hard" is too big for a SPENT dragon on a devastated wing, whose order says she "hauls herself up". Cinder's "Stamina: fresh breath" again next to "spent". Glacia (3%, in the air) gets "Barely able to stand, swaying". And it says "an ordinary exchange" again.

### narr_bugs_36-47

- Beat 36 (all calls, CURRENT CONDITION): Glacia "limps badly, keeping weight off her left wing". A wing is not a leg, and she is in the air.
- Beat 36 (CURRENT CONDITION): Cinder is "IN THE AIR" but her strength line says "Barely able to stand, swaying, slow to rise", and her MOVES line says "keeps her left wing tucked in, unusable" while WING STRAIN has her flying on it.
- Beat 36 (CURRENT CONDITION): Cinder "Stamina: fresh breath" while she is "spent" at 12% and has been straining a ruined wing for beats.
- Beat 36 (HOW THEY MOVE NOW): Cinder's line repeats itself: "holds her head carefully, the head making every turn of it a decision; holds her head carefully, the neck making every turn of it a decision".
- Beat 36 (FIGHT SO FAR): calls itself "the ONLY earlier attacks that really happened" but lists only the last 10. Flare Blitz, Hurricane etc. are missing, yet the same notes cite "Chest (Cinder's Flare Blitz)" as the wound that matters most, and part 2 block 10 cites "Glacia's Hurricane".
- Beat 36 (call 2, block 10 vs CURRENT CONDITION): jaw history is given two ways: "already hurt ... by Glacia's Hurricane and then Glacia's Blizzard" vs "Jaw (hurting; from Glacia's Blizzard, then Glacia's Ice Shard)".
- Beat 36 (call 1, Hit 1/Hit 2): "her knees dipping under it (a limp if it is a leg)". Cinder is in the air. Hit 2 (muzzle, "a solid blow") gets the same "strong: a real cry" reaction as the heavier Hit 1.
- Beat 36 (call 1): "THE SOUND OF THE BLOW: a creak of freezing fur." Cinder has scales.
- Beat 36 (call 1, block 3): "anger ... in the set of her ears". Glacia has no ears.
- Beat 36 (call 1, TELLING THE HURT): "through the scenery: the bark, mud or water". No bark, mud or water on a rock shelf, and both are in the air.
- Beat 36 (call 2, block 6): "It was sent at the middle of her and landed on her jaw." The shard was aimed at her head.
- Beat 36 (call 2, block 7): "spray or grit flies off her in a burst". She is in mid-air, dry.
- Beat 36 (call 5): "she watches from where she stands". Glacia is in the air. Block 6 "eagerness that makes her shift her weight" does not fit a fighter past the limit and "desperate".
- Beat 36 (call 5): the style sample for a watching part is a pin passage ("Lying across Sorrel, pressing her down"). No pin this beat.
- Beat 36 (VISIBLE WEAR): Cinder's head "the scales clawed ragged, whole tufts gone". Scales have no tufts, and the head was hit by Air Slash and Wing Attack, not claws.
- Beat 37 (call 1): "IN THE AIR, BOTH OF THEM: ... Both stay up." contradicts the next line, "the blow KNOCKS Glacia OUT OF THE AIR ... She FALLS".
- Beat 37 (call 1, blocks 2-3): "she cannot stand straight; her chest folds her" and "her right wing hangs, and she turns her body so that it is furthest from the fight". Glacia is flying on that wing at this point.
- Beat 37 (call 1, Hit 1): "a limb scrabbling at the ground". The bite lands in mid-air.
- Beat 37 (call 1, Hit 2 and all three landing hits): "her reaction: strong: a real cry, her knees dipping under it ... the rest of her still fighting". Glacia is past the limit, and lying on her back for the landing hits. Left Thigh "shows as a limp in the next step": she takes no step.
- Beat 37 (call 2, block 10): "Glacia's neck was already hurt before this beat, by Cinder's Thunder Punch and then Cinder's Fire Fang", but CURRENT CONDITION says "Neck (devastated; from Cinder's Heat Wave, then Cinder's Fire Fang)".
- Beat 37 (call 2, block 9): "her tail barely twitches" offered as how the devastated NECK shows.
- Beat 37 (call 5): "cold sweat under the fur" (she has feathers). Block 8 thought "*Shake it off. Shake it off.*" is not Glacia's calm, detached voice.
- Beat 37 (call 5, style sample): "each one ending in a sob she could not stop. Her face was wet ... her own tears" breaks the notes' own rule "no sobbing or weeping".
- Beat 37 (missing): no part covers Cinder after the last stand ("afterwards she has nothing left at all, barely able to stay up"). Part 3 is Glacia only.
- Beat 37 (CURRENT CONDITION): Glacia "favors her left shoulder (a slight limp)" and "limps badly, keeping weight off her left wing". She is lying on her back; a wing or shoulder gives no limp.
- Beat 38 (call 2): "The attack has ALREADY been shown above, miss and all: do NOT describe any attack, dodge, impact". There is no attack and no miss this beat (a landing and a breather).
- Beat 38 (call 1): "the actions as they happen, in order, from the attackers' bodies". Nobody attacks this beat, and the part gets no POV.
- Beat 38 (rewrite calls): "she tries to rise ... and can't, so she ends the beat still on the ground" leaves out that she gets as far as sitting up.
- Beat 39 (get-up): "she ends on the ground, gathering herself for the next try" does not say she is still SITTING UP, which beat 40 relies on ("sitting up → face-up"). The rewrite text says the same.
- Beat 39 (call 1, blocks 9-10): "she lets her foot slip on the bad footing and uses the slip" and "She narrowed her stance". Glacia is sitting and cannot stand.
- Beat 39 (call 2, block 10 vs CURRENT CONDITION): "Cinder's belly was already hurt ... by Glacia's Hurricane and then Glacia's Blizzard", but the condition says "Belly (... from Glacia's Blizzard, then Glacia's Ice Beam)", and beat 36 said "from Glacia's Freeze-Dry, then Glacia's Blizzard". The memory line seems to say "Hurricane then Blizzard" for every part (same in beat 36 for the jaw).
- Beat 39 (call 5, block 1): "a hot, deep ache all the way down the arm, and her shoulder has taken it up too". The beam hit chest and belly; no arm.
- Beat 39 (call 5): "cold sweat under the fur" for a scaled dragon; (call 6, block 1) "the sweat darken along the other's sides".
- Beat 39 (call 6): "she watches from where she stands". Glacia is sitting. Block 2 "jerk at a sound from somewhere else": there is nobody and nothing else on the shelf. Block 3 "her horn" (singular): Cinder has two.
- Beat 40 (call 1, pin LOOKS): "the fur ruffled the wrong way", "a light print sunk into the fur", "the fur pushed flat round it". Glacia has feathers.
- Beat 40 (call 1): the PIN line says Glacia "is fading: her limbs are heavy, her sight is greying", but FIGHT SO FAR says "pinned and furious, and far from done", and FADING THOUGHTS names only Cinder as fading.
- Beat 40 (call 2, blocks 2-3): "she shoves at the ground ... and gains a hair's width" and "Her whole spine arched, lifting both of them a fraction." No struggle is rolled this beat (it starts in beat 41), so this is movement the engine did not decide.
- Beat 40 (CURRENT CONDITION): Glacia "Stamina: breathing hard", better than "gasping" in beats 37-39, just as a crushing weight lands on her chest.
- Beat 41 (pin presses): "paws clawing at anything", "the fur smoothed down hard", "the coat creased under it, the fur parting". Glacia has no paws, fur or coat.
- Beat 41 (WHAT HAPPENS): "described under PIN CLOCK, if the pin is already running". There is no PIN CLOCK section; the section is "THE PIN GOES ON", and it says there is no clock.
- Beat 41 (call 1, block 5): "she braces with the left wing and it trembles under the load". Cinder's left wing is devastated and "tucked in, unusable".
- Beat 41 (part 3, block 7): "END this part on ... something in the place settling: dust, water, an echo dying". No water on the shelf, and SOUND IN THIS PLACE says "nothing echoes".
- Beat 42 (break-loose): the notes say "she flails a free limb at the body on top of her", and the rewrite asks "what she hits with", but they never name it. The console says "she kicks out". Glacia has no arms, one wing is pinned and the other is devastated, so the notes should name the legs/talons.
- Beat 42 (call 2, block 3): "She made a small movement that might have been an attempt to rise." This undercuts the "hard and wild" break-loose the same part must show.
- Beat 42 (call 2, block 7): "a hawk circling far out". This adds a creature that is not in the scene.
- Beat 42 (Cinder's throat hit): "her knees dipping under it (a limp if it is a leg) ... the rest of her still fighting". Cinder is lying on top of Glacia and has just gone past the limit.
- Beat 42 (pin LOOKS): "pressed in so the flesh rolls up round it in a thick fold" on Glacia's chest is too fleshy for a bird and heavier than the gore rule. Also "the fur flattened", "the fur fanned out" again.
- Beat 42 (FADING THOUGHTS): only Glacia is fading, although Cinder goes past the limit this beat.
- Beat 43 (struggle): "she lashes out with whatever she can still move: hind legs, tail, a free paw". Glacia has no paws and no "hind" legs (a bird has only legs).
- Beat 43 (call 2, block 7): "Glacia's chest was already hurt ... by Cinder's Fire Fang and then Cinder's pin", but WHAT HURT WHERE says "chest (Cinder's Thunder Punch and Cinder's pin)". The last Fire Fang (beat 37) hit the neck.
- Beat 43 (part 3, blocks 4-5): "*Look at her pretend.*" and "contempt, in the way she turns half away before the other has recovered". These don't fit a bird who is "nearly gone under the pin", nor Cinder's proud, respectful voice, nor a pinner who must keep her weight on.
- Beat 43 (Left Wing press): "she twists so hard her back comes off the ground, then slams back". This clashes with "a slow, late try, not a strong one" in the same beat.
- Beat 43 (pin LOOKS): "a trench in the fur", "the fur and flesh squeezed out round it in a ridge", "the fur ruffled the wrong way". Fur again.
- Beat 44 (free blow): "Cinder gets one quick, short extra blow in on Glacia's Upper Back ... (Flamethrower, at point-blank)". Glacia is face-up with "her back against the ground", so the engine picked a part the pinner can't reach. Also, neither part's instructions say where the free blow goes (part 2 ends on the failed struggle).
- Beat 44 (struggle, Chest hit): "a hit here shows as a hand or paw pressed to the chest". Glacia has neither.
- Beat 44 (call 1, blocks 3 and 5): "read through her paws"; "she keeps her face out of reach of the other's teeth". Glacia has a beak, not teeth.
- Beat 44 (call 2, blocks 2-3): "her body has stopped answering, and she has stopped asking" and "they no longer fought to open". Both come before the struggle that the same part must show, and FIGHT SO FAR says "still refusing".
- Beat 44 (pin LOOKS): "the coat dimpled under it, the hairs bent over flat in a ring", "the fur at the throat". Feathers.
- Beat 42-45 (CURRENT CONDITION): Cinder, lying on top in a pin, is "wobbling, dropping to the ground between efforts". This is the standing text for past-the-limit, not fitted to a pinner.
- Beat 45 (parts): neither part is given the struggle. Part 1 says "STOP before Glacia goes out ... and Cinder strikes nobody in this beat", although Cinder punishes the bridge with her forearm (Neck, a heavy blow). Part 2 lists breath, sight and the faint, but not the bridge. The rewrite then flags "it skipped the struggle".
- Beat 45 (call 1, block 2): "she has stopped struggling and is saving something". She bridges this beat, and "saving something" suggests a trick that never comes.
- Beat 45 (call 1, block 7): "her left wing lags, and the move comes out lopsided". Cinder makes no move; she is lying on top.
- Beat 45 (pin LOOKS): "the fur and flesh squeezed out round it in a ridge", "a jerk under the fur", "sunk into the fur". Fur again.
- Beat 46 (AFTER THE MATCH): "a sense not used yet (wind, ... the cry of a hawk; an echo ...)". A hawk adds a creature, and the place has "nothing echoes".
- Beat 46 (call 2): "the water, the light and the sounds of the place". There is no water on the shelf.
- Beat 46 (call 2, block 1): "a small whimper escapes her on the breath out". Glacia is "OUT COLD ... unresponsive".
- Beat 46-47 (VISIBLE WEAR): only Cinder's wear is listed. Glacia's (scorched chest, bitten neck, clawed wing) drops out once she is eliminated, just when the aftermath is supposed to describe how she lies.
- Beat 46-47 (CURRENT CONDITION): Cinder "Stamina: breathing hard", and part 1 asks for "her breath coming back". But the console shows her still getting worse (health -61.54 → -66.17 → -68.49, from injuries). The notes never say that she keeps weakening. Her strength line still says "Only a completed pin puts her out" after the match is over.
- Beat 47: the notes are a near copy of beat 46 (same frame, same AFTER THE MATCH text, same style samples); only the building blocks change. Block "her mouth is slightly open": she has a beak.
