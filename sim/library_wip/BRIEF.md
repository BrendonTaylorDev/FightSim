# Brief: new story material for FightSim's narrator

FightSim is a fight-story engine. A rules engine decides every event: who hits whom, which body part, how hard,
how much each part hurts now, the fighter's overall strength, who falls, who is pinned or held. A local LLM
(mistral-small 24b) then writes the prose. To help that small model, the program hands it, before each part of a
beat, a few **story blocks** (short jotted ideas), a **finished line** (one sentence it may use word for word), and
**sample passages** (a few paragraphs showing how this kind of moment is told). The author is writing an
ORIGINAL story with a wide variety of creature body types (bipeds with arms and paws, four-legged beasts, winged
and feathered flyers with beaks and talons, serpents with coils and scales, finned swimmers, horned, maned, ruffed,
shelled, spiked, antennaed, crested creatures, creatures with flames or several tails) and attack types (claws,
bites, punches, kicks, tails, horns, wings, beaks, talons, charges, throws, grabs, holds, pins, beams, and
elemental attacks: fire, ice/cold, electric, water, psychic, poison, rock, ground, wind/flying, grass, ghost,
dragon, fairy, steel, dark, bug, normal). Pokemon are used as stand-ins in testing; never use the word Pokemon,
and never name a species.

The author's priorities: VARIETY above all; SELLING HITS so a reader feels them, sized to the body part's damage
level AND to the fighter's overall strength (a fresh fighter shrugs off what makes a spent one tremble); the
visible RESULTS of an impact on the body (ruffled or flattened fur/feathers/scales, skin twitching, the push of
the blow, breath driven out, a head turned, a stumble when the engine says she stumbles); and the STRUGGLE of a
hurt body (gripping a hurt part, heavy or catching breath, eyes squeezing shut or drifting closed, gasps, gentle
or constant trembling, swaying, sagging, rocking, whimpers, holding still).

## Hard content rules (every entry must obey)
- Tone: an intense, physical battle with only a LITTLE gore. Allowed: bruising, swelling, scratches, small cuts, a
  thin trickle of blood, a split lip, the sting of a bite, singed fur, frost on fur. Never: torn or shredded flesh,
  exposed bone or insides, broken or cracking bones, blood pooling/spraying/soaking, anything severed, death or
  dying, killing language. Throats can be bitten hard; nothing torn out.
- Nobody faints, blacks out, collapses or loses consciousness unless the category is about exactly that
  (knockout, collapse, faint, aftermath_fallen, knockout_watch).
- Never invent movement the engine did not decide: in reaction, pain_show, sensation, tell, held_in, raw, breath,
  after_hit and impact_mark entries, her FEET do not move (no stepping, staggering, stumbling, falling, being
  knocked back or off her feet, sent sliding, lifted). Swaying, sagging, leaning, rocking ON THE SPOT, flinching,
  curling, folding a little, a head turning, shoulders shoved back are fine. Only `moved | how: stagger` and the
  stagger lines and stagger take samples may move her feet.
- No memories from before the fight (no old fights, training, teachers, lessons, "long ago", childhood). No
  backstory, no relationships, no other opponents.
- One blow is one blow: never imply extra strikes ("two quick ones", "the real one", "again and again" unless the
  category is a flurry/pummel/frenzy).
- No numbers, percentages, game words (HP, damage, level, stats, "super effective"), no species names, no
  "Pokemon". No colors as pain levels ("red pain").
- An entry must be TRUE every time its conditions hold. If it only fits a body with wings, condition it on wings.
- Avoid stock phrases ("a symphony of", "palpable tension", "a wave of pain washed over her" as filler). Concrete,
  physical, specific. Each entry different from every other: different image, different verb, different body
  part detail. Do not repeat entries that already exist (check the existing file when unsure).
- The subject fighter is always "she". Others are "the other", "her opponent", or {foe} in lines that allow it.

## Format
Files are plain text. A line `== category | condition: values | condition: values` starts a group; every line
under it is one entry, until the next `==` line. An entry may add its own conditions after a ` | ` at its end
(e.g. `her wings snap open on their own | has: wings`). Lines starting with # are comments: add a short comment
above each new section. Leave a blank line between groups.

- STORY BLOCKS (story_blocks.txt): short ideas, PRESENT tense, lower case start, no final period, jotted not
  polished ("her ears clamp flat and her eyes water"). 8 to 25 words each.
- FINISHED LINES (story_lines.txt): one complete sentence, PAST tense, capitalised, ending with a period. Usable
  word for word in a story. Italic thoughts are written *like this* and may be present tense.
- SAMPLE PASSAGES (style_sample_scenes.txt): `== tag, tag | conditions` then 150-350 words of finished prose,
  past tense, third person, using {A} for the one who ACTS in the passage and {B} for the one it happens to (they
  are shown as two neutral names). Paragraphs separated by blank lines. Show bodies, sounds, breath, thoughts in
  italics, the place in passing.

Slots: `{part}` = the body part in question (lower case, e.g. "left thigh"), `{next}` = a part beside it (only in
categories whose examples use it), `{foe}` = the opponent's name (finished lines only, and only where the
existing lines in that category use it). Never use any other slot. Use {part} naturally ("her {part}").

## Condition vocabulary (only these keys and values; a key the program does not pass for a category makes the
entry never shown, so ONLY use the keys that the gap report shows existing entries of that category using, plus
`has:` which is passed nearly everywhere a body is involved)
- size: glancing, solid, heavy, tremendous (how hard the blow landed)
- level: minor, sore, hurting, very painful, excruciating, devastated (how much the part hurts after)
- state: fresh, winded, tired, spent (overall strength: fresh >= 80%, winded 60-80, tired 20-60, spent < 40)
- zone: head, neck, chest, belly, back, arm, leg, tail
- has: wings, feathers, beak, talons, coils, tail, tails, fins, horn, mane, ruff, hood, antennae, crest, flame,
  scales, shell, spikes, arms, forelegs, legs, ears (a body feature the fighter has)
- kind (blocks: movement, impact_mark): claw, bite, charge, tail, beam, punch, horn, wing, beak, talon, throw,
  grab, close, fire, ice, wind, rock, AND for impact_mark only also the move's type: electric, water, psychic,
  poison, ground, grass, ghost, dragon, fairy, steel, dark, bug, normal, fighting, flying
- kind (moved only, the engine's blow kind): blunt, claw, blade, bite, blast, shock, fire, cold, mind
- how (moved): rock, stagger, ground; where (moved, with how: rock): standing, down, held, holding
- posture: standing, down, pinned
- role: attacker, receiver, pinner, pinned, winning, losing
- stage: early, middle, late, end
- raw (raw, held_in): contained, cry, scream, raw
- effect (effect_* lines/blocks): super, weak, none; type: the attack's type; vs: her own type
- status (status_tell, status_seen): flinched, dazed, off_balance, doubled_over, breathless, stiff, bound,
  sputtering, cramped, paralyzed, confused, constricted, staggered, burned, poisoned, chilled, frozen, asleep
- moment (juggle: up, caught; feint: bit, read), fade (fighting, weakening, fading, nearly out), held (early,
  middle, long), health (fresh, worn, spent) and partlevel (light, hurt, ruined) for devastating_sell

Sample passage conditions (after the tags): `| has_b: wings` (the one it happens to, {B}, has wings), `| has_a:
coils` (the one who acts, {A}), `| has: fins` (anyone in the fight), `| kind: fire, electric` (a move of that kind
or type is in the beat; kinds as for impact_mark). Give a passage conditions whenever it shows a specific body
feature or attack type, so it is never shown in a fight without them. A passage with no conditions must fit ANY
body: no wings, tails, fins, horns, paws or hands named; use fur sparingly (feathered or scaled bodies exist) or
condition on it.

## Where to look
- The existing files: /home/user/FightSim/story_blocks.txt, story_lines.txt, style_sample_scenes.txt. Read the
  sections for your categories before writing so you match their voice and never duplicate them.
- Gap report (every category, its count, the conditions its entries use, how the program calls it, examples):
  /tmp/claude-0/-home-user-FightSim/d2e1d57a-2374-5322-b4cf-0e9b328e1377/scratchpad/lib/gap_report.txt
- Body-feature and attack-kind coverage: .../scratchpad/lib/body_kind_coverage.txt
- Sample passages per tag: .../scratchpad/lib/sample_tags.txt

## Output
Write ONLY to your own output file (given in your task) in the exact file format, ready to append. Do NOT edit
the project files. When done, reply with a short summary: categories covered and how many entries each.
