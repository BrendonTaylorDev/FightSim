# Brief: narrating the Nocturne vs Ripples test fight

You are writing the finished prose for a test fight played in FightSim, a fight-story engine. A rules engine decided every event. Your job:
- write the story of your beats, very detailed, the way the best local narrator ought to;
- note anything in the engine's notes that is wrong, contradictory or missing (a bug report).

The author writes an original story with varied creatures. These fighters are stand-ins, but describe them as the bodies below. Never use the words "Pokémon", "Absol" or "Buizel", and no game words (HP, damage, percent, super effective, level).

## Where everything is (folder W = /tmp/claude-0/-home-user-FightSim/d2e1d57a-2374-5322-b4cf-0e9b328e1377/scratchpad/wt4)
- **W/outline.md:** the whole fight, beat by beat (orders, events, every roll). Read it all first, so you know what came before and after your beats.
- **W/out/beatNN.txt:** the engine's console for beat NN: every blow, the parts hit, damage before → after with a coloured pain level, health, statuses, falls and get-ups, and the dice. This is the truth.
- **W/out/notesNN.txt:** what the program sends the local narrator for beat NN. It is split into CALLs, one per part of the beat, each with a point of view ("— Name —"), a checklist, story blocks (ideas) and sample passages. Use it as your guide: write each part from the POV it gives, cover what its checklist requires, and use the ideas that fit.
- **W/out/snapNN.json:** the state after beat NN, if you need it.
- **Style model:** the previous test fight's narration, /tmp/claude-0/-home-user-FightSim/d2e1d57a-2374-5322-b4cf-0e9b328e1377/scratchpad/wt2/narration/beat05.md, beat17.md and beat37.md. Match its quality, voice and format: "— Name —" headers for each POV part, past tense, third person, concrete physical detail, short italic thoughts, sounds written out sparingly.

## The fighters
- **Nocturne** (she, wins by pin):
  - **Body:** a proud, furious, fast four-legged hunter with mostly white fur and a dark blue-grey face. A scythe-shaped horn juts from one side of her head. Her sickle-bladed tail can be hardened like steel. A thick white ruff covers her neck and chest, with a tuft on her head. Red almond eyes. Broad furred paws with three claws each, and spikes on her heels and elbows.
  - **Fighting:** raking claws, horn, tail-blade, bites. She can let out stored electricity in limited bursts, and hates water.
- **Ripples** (she, loses):
  - **Body:** a small, wiry, stubborn, patient otter-like fighter who walks upright. Orange fur with a cream face and stomach, small black eyes, black cheek marks and cream spots above her eyes. A blue fin on each forearm. Arms ending in webbed paws (her hands), and she stands on her feet. Twin cream-tipped tails she spins like a propeller. She has no flotation sac: her neck and throat are bare, and she guards her throat by habit, chin tucked, shoulders up.
  - **Fighting:** water charges, bites, chops. She binds limbs with her twin tails and never lets go of a grip.
- Their voices come from the notes: use the voice and tells the notes give.

## The place
The roofless hall of a ruined stone temple deep in a jungle. A cracked flagstone floor runs between two rows of tall carved pillars; some still stand, some lean, and two lie toppled in broken sections. Vines hang from the tops of the walls. An altar stone stands at the far end under a cracked statue. Moss grows in the cracks, puddles of rainwater stand in the hollows of the floor, the light is warm and green, and birdsong comes from outside.

## Hard rules
- **The engine decides everything.** Never add a blow, a dodge, a fall, a movement or a wound that the console doesn't show. Never leave out one that it does.
  - Where she was hit, how much it hurt (the pain level after), whether she moved: true to the console.
  - A part at a high pain level on a fighter who is still strong overall: pained but half hidden, never a raw collapse. Raw reactions only when she is worn down.
  - Overall strength shows in everything: fresh, then winded, then tired, then spent. Follow the per-beat health lines.
- **Gore:** only a little. Bruises, swelling, scorched and frost-burned feathers or scales, small cuts, a thin trickle of blood at most. No torn flesh, no broken bones.
- **No memories** from before the fight, and no backstory.
- **Length:** one file per beat, 350 to 700 words for a normal beat. A big beat (a fall, the pin, the finish) can run longer.
- **Beat 0** (only the first agent writes it) is an opening: the place, the two of them, before the first move. About 400 to 600 words.

## Output (save as you go: the author may run out of tokens)
- Write each beat to W/narration/beatNN.md (two digits) as soon as it is done. Never batch them.
- Bugs: write them to W/narr_bugs_<your range>.md as you go, one bullet each, with the beat number. A bug is something in notesNN.txt that:
  - contradicts the console;
  - offers an idea that doesn't fit (the wrong body, the wrong kind of attack, too big or too small for the pain or strength, movement the engine didn't decide);
  - mislabels something;
  - repeats itself;
  - leaves out something important.
  Quote the exact text from the notes. Don't fix code.
- Finally, reply with a short summary: the beats written, word counts, and the bugs you found.

## Notes for this fight
- "PREVIOUS BEATS" and "THE PASSAGE SO FAR" in the notes hold placeholder prose from the test harness, and the rewrite-loop reports come from it too. Ignore both; they are not bugs.
- This test is also checking new settings: faster fights, and damage spread over more parts. If the notes or the console show damage piling onto one part far too fast, or a part reaching a pain level much bigger than its blows seem to justify, note it in your bug file with the numbers.
