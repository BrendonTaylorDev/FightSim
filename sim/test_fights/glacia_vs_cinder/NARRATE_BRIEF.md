# Brief: narrating the Glacia vs Cinder test fight

You are writing the finished prose for a test fight played in FightSim, a fight-story engine. A rules engine decided every event. Your job:
- write the story of your beats, very detailed, the way the best local narrator ought to;
- note anything in the engine's notes that is wrong, contradictory or missing (a bug report).

The author writes an original story with varied creatures. These fighters are stand-ins, but describe them as the bodies below. Never use the words "Pokémon", "Articuno" or "Charizard", and no game words (HP, damage, percent, super effective, level).

## Where everything is (folder W = /tmp/claude-0/-home-user-FightSim/d2e1d57a-2374-5322-b4cf-0e9b328e1377/scratchpad/wt3)
- **W/outline.md:** the whole fight, beat by beat (orders, events, every roll). Read it all first, so you know what came before and after your beats.
- **W/out/beatNN.txt:** the engine's console for beat NN: every blow, the parts hit, damage before → after with a coloured pain level, health, statuses, falls and get-ups, and the dice. This is the truth.
- **W/out/notesNN.txt:** what the program sends the local narrator for beat NN. It is split into CALLs, one per part of the beat, each with a point of view ("— Name —"), a checklist, story blocks (ideas) and sample passages. Use it as your guide: write each part from the POV it gives, cover what its checklist requires, and use the ideas that fit.
- **W/out/snapNN.json:** the state after beat NN, if you need it.
- **Style model:** the previous test fight's narration, /tmp/claude-0/-home-user-FightSim/d2e1d57a-2374-5322-b4cf-0e9b328e1377/scratchpad/wt2/narration/beat05.md, beat17.md and beat37.md. Match its quality, voice and format: "— Name —" headers for each POV part, past tense, third person, concrete physical detail, short italic thoughts, sounds written out sparingly.

## The fighters
- **Glacia** (she; loses):
  - Appearance: a large, elegant ice bird with pale icy-blue plumage and a crest of three long, darker blue feathers. A short sharp grey beak and calm deep-red eyes. Huge translucent pale-blue wings that glitter with frost; no arms. A very long streaming tail of blue feathers, thin grey legs with small talons. Frost and drifting snowflakes follow her.
  - Voice: quiet, distant, icy; she thinks in calm, detached observations even when hurt. A clear, bell-like cry when she attacks; in pain, a thin, cracking wail.
  - Tells: her breath steams; frost spreads across her feathers when she is angry; her long tail ripples; a hurt wing sheds a sparkle of loose frost; she holds unnaturally still before she strikes.
- **Cinder** (she; wins, barely):
  - Appearance: a large upright dragon with orange scales and a cream-yellow belly. A long neck, two short backward horns, blue eyes and a wide jaw of small fangs. Bat-like wings with blue-green membranes. Short strong arms with three-clawed hands, heavy legs, and a long tail tipped with a burning flame that flares with her mood and never goes out.
  - Voice: proud, cocky, fierce; she thinks in challenges. A deep rumbling roar when she attacks; in pain, a roaring bellow that breaks into a hoarse growl.
  - Tells: her tail flame flares white-hot when angry and gutters low when hurt or tired; smoke from her nostrils; her wings flare to loom; a hurt wing hangs half-folded.

## The place
A wide shelf of bare rock high on a mountainside, open to the sky. On one side a sheer cliff face, on the other a drop into cloud. Loose scree along the foot of the cliff, a few stunted pines in the cracks. The air is thin and cold, the wind gusts hard, and there is nothing overhead but sky. Most of the fight is in the air above the shelf: show the height, the wind, the cloud below, the wingbeats, the effort of flying hurt.

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
