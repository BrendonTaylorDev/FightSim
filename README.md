# Fight Sim: local fight director + combat engine + narrator

Three parts, all running on your own PC:

1. **Director** (your local model): decides who does what next. There are no turns. Anyone can act as
   many times in a row as the story calls for. It picks the move, the target body part, and a
   severity word ("light jab", "brutal chair shot"). It never picks numbers.
2. **Engine** (Python): turns severity words into numbers and does all the math: damage, resistance,
   health, holds, pinfalls. This is why stats stay accurate.
3. **Narrator** (your local model again): writes the prose, with reactions forced to match each
   fighter's pain and exhaustion levels.

## One-time setup (Windows, RTX 5080)

1. **Install Python 3.10+** from python.org. Tick "Add Python to PATH" during install.
2. **Install Ollama** from ollama.com and let it run in the background.
3. **Download the model** (about 14 GB). In a terminal:
   ```
   ollama pull mistral-small:24b
   ```
4. Unzip this folder somewhere, e.g. `C:\fightsim`.

## Run it

```
cd C:\fightsim
python play.py
```

At the `>` prompt:
- **Press Enter**: the director decides what happens next.
- **Type a direction**: e.g. `Ripples drags Nocturne away from the water`. The director follows it for the next beat.
- **`/auto 5`**: let the director run five beats on its own.
- **`/status`**: see every body part's exact damage and resistance.
- **`/help`**: all commands, including manual beats such as `/strike Ripples Nocturne Muzzle light 3 "three quick bites"`.

**More than one fight, and who is in it:**
- **`/fighters`** lists everyone in `fighters.json` and who is in the current fight.
- **`/newfight Nocturne Ripples`** starts a fresh fight between just those two without restarting the program:
  full health, no injuries, a new story. `/newfight` alone repeats the same line-up; `/newfight all` brings
  everyone in. Or start that way: `python play.py --fighters Nocturne,Ripples`.
- **`/autofight 3 4`** has the director play three whole fights, one after another, each followed by four
  aftermath beats, and then shows who won each and how long it took. `/autofight 3 2 Nocturne Ripples` picks the
  line-up too. A fight with no winner after `director.autofight_max_beats` (150) is stopped. The interrupt
  button (Ctrl+C) stops the run and keeps the beats already played.
- **`/results`** shows the winners so far. `/export` writes every fight of the session.
- Your settings carry from fight to fight (`/plan`, `/focus`, `/scale`, `/talk`...); `/undo` doesn't reach back
  into an earlier fight.

Options: `--hide-math` starts with stat blocks off. `--model qwen3:14b` tries a
different model (pull it first). `--no-llm` disables the models so you can test rules with manual commands.

## Fixing mistakes and keeping your fights

- `/undo` takes back the last beat completely: stats, story, pins, positions. `/undo 3` takes back three.
- `/reroll` rewrites the last beat's narration with the same events and the same stats. Use it when the
  prose misses something or you just want a better take.
- If the model fails mid-beat (Ollama crash, out of memory), the beat's stats still stand and the program says
  so; `/reroll` narrates it once the model is back, or `/undo` takes the whole beat back. Brief Ollama crashes
  are retried automatically.
- The fight **autosaves every beat** to autosave.json. After a crash or restart: `/load autosave`.
- `/save myfight` and `/load myfight` keep named saves next to play.py.
- `/export` writes the whole fight (prose and stats) to story_export.md; `/export mystory prose` writes just
  the story.
- `/status` shows everyone's health, worst injuries, limited moves, pins, and positions at a glance;
  `/status full` or `/status Ripples` for every body part.
- `/health` prints every fighter's health (raw and as a share of their own full health) and every damaged
  body part with resistance and damage, worst first. `/health Ripples` for one fighter.
- `/look` has the narrator describe the scene right now, without advancing the fight: where everyone is,
  how they hold themselves, breathing, visible injuries, any pin in progress. `/look Ripples` focuses on one
  fighter. With the models off (`--no-llm`) it prints the same information as plain text. (`/describe` works too.)

## Pin damage

`/pinpower 0.5` halves all pin damage (the pressure on every point of contact each beat, the extra hit when the
pinner punishes a failed struggle, and `/pinsuccess`); `/pinpower 2` doubles it; `/pinpower` shows it. Saved to
`rules.json -> pin -> damage_mult`. The pressure also grows each beat a pin holds (the director's "ramp"), and
the punishment hit's strength is `pin -> struggle -> punish_severity` (light, solid, heavy, brutal).
When the pinned fighter breaks free, the blow that frees her lands on the pinner (`pin -> struggle -> escape_hit`,
`escape_severity`); when she only breaks loose for a moment, her hit is `counter_severity`.

## Steering the story

These nudge the director's choices; the engine's rolls (dodges, escapes, statuses, pins) still decide what
actually happens, so a planned winner can still lose.

- `/plan close [winner]`: a back-and-forth fight. With a winner, the director is told each beat whether that
  fighter is ahead too early (give the other side the next exchange) or too far behind (fight back now).
- `/plan dominate <name>`: that fighter controls the fight (the momentum rule stops forcing turns for the other).
- `/plan comeback <name>`: that fighter takes heavy punishment first, then turns it around once she's below about 50%.
- `/plan even`, `/plan winner <name>`, `/plan off`, and `/plan` alone to see the current plan.
- `/targeting one | few | many | all | auto`: how many body parts attacks spread across. It tells the director
  and also changes how many neighbors a single hit jars (one: none, few: 2, many: 4, all: 6).
- `/getup <name> [tries]`: stand a fighter up now, in 1-3 tries (worked out from her injuries if you leave it out).

### Sustained moves

Streams and beams marked `"sustainable"` (Hydro Pump, Flamethrower, Ice Beam, Thunderbolt, Water Gun, Dragon Pulse,
Solar Beam, Hyper Beam, and more) can occasionally be held for 2-4 pulses. Each extra pulse hits the same parts at
×0.6 and costs extra energy. If the target is pressed against something (a boulder, a stalagmite, the wall), each
pulse also slams her into it, and it may break (boulder 20% per pulse, stalagmite 35%, wall 5%): a heavy extra
hit, the move ends early, and she goes down. The director decides when (occasionally); you can force one with
`/sustain Seraphina Ripples "Hydro Pump" 3 "a fallen boulder"`. Tune it in `rules.json -> moves -> sustain`.

### Pin techniques

While a pin runs, the director now and then has the pinner attack the pinned fighter with a technique (trapping a
paw and driving a claw into a nerve cluster, grinding a knee into a joint, clamping a limb in its jaws). Half the
time (`chance`) it also leaves her 🔗 RESTRAINED for 2 beats: escape chance down to ×0.6, but only fully
once she's at 30% strength or below (`full_effect_below`); a healthy fighter barely notices it. Tune it in
`rules.json -> pin -> restrain`.

### Healing (your commands only)

- `/heal Ripples "Right Paw,Chest" 100` takes 100% damage off each of those parts; add a second number to restore
  resistance too (`/heal Ripples worst 80 20`: her 3 worst parts lose 80% damage and regain 20% resistance, never
  above where they started). `all` heals every part.
- `/restore Ripples 300` gives back 300% health (never above her max).
- Each is a narrated beat: the narrator picks a believable way (Rest, Aqua Ring, Recover, a berry, the cold
  water, a second wind), or add your own at the end: `/restore Ripples 300 "eats an Oran Berry"`.

### Pin requirements (optional)

`/secure on 6 150 50` turns on a rule that a pin can only be WON once the pinned fighter has at least 6 body
parts at 150%+ damage AND her strength is 50% or less (all three numbers are yours to pick; saved to
`rules.json -> pin -> secure`). Until then, her escape chance is doubled every beat (`unmet_escape_mult`), and if
the clock runs out she kicks out at the last second 85% of the time (`final_kickout_chance`), so fights need to
spread the damage before a pin is likely to finish them. Early breakouts still happen as normal. The director sees what's still missing. `/secure off`
turns it off; `/secure` alone shows the setting.

## Changing things from the console

- **Several commands at once:** separate them with `&&`, and typed directions can be mixed in:
  `/scale 5 && /pinbeat 5 && Nocturne goes for the pin`. If one fails, the rest stop (the earlier ones still happened).
- **Pins:** `/extendpin 30` adds 30 seconds to the running pin; `/pinclock 90` gives it a new total. Name the
  fighters if more than one pin is running (`/extendpin Nocturne Ripples 30`). `/pinlength` changes the default.
- **Any rule:** `/get` lists the rule sections; `/get pin.struggle` shows one; `/set pin.struggle.escape_chance 0.5`
  changes it live and saves it to rules.json (add `nosave` to change it just for this session). Works for any
  number, true/false, or word setting, e.g. `/set evasion.enabled false`, `/set narration.best_of_two always`.
- **Fighters:** `/fighter Ripples health 900`, `/fighter Ripples energy 40`, `/fighter Nocturne status paralyzed 2`,
  `/fighter Nocturne clearstatus`, `/fighter Ripples down` / `up`, `/fighter Ripples recovery 2`,
  `/fighter Seraphina revive` (back into the fight).
- **Body parts:** `/part Ripples "Right Paw" damage 120`, `/part Ripples "Right Paw" resistance 50`.
- All of these can be taken back with `/undo`.

## Positions and limited moves

- After every beat the director records WHERE everyone is ("Ripples: in the shallow pool"). WHO IS UP, DOWN,
  WHICH WAY SHE LIES, AND WHO IS PINNED comes from the engine, not from the director's sentence: the line both
  models read looks like `Nocturne: ON TOP of Ripples, pinning her down, on the dry ledge; Ripples: ON THE
  GROUND, face-up, PINNED under Nocturne, in the shallow pool`. If the director's sentence disagrees with the
  engine (it's written before get-ups and escapes are rolled), only the place it names is kept.
- `/posture` shows it for everyone at any time. `/status` shows 🧍 up, ⬇️ down (and which way), 📌 pinned / on top.
- The posture rules the engine enforces:
  - A fighter who is knocked down, thrown, taken down into a pin, or put to sleep loses every pin and hold she
    had on anyone (`💥 Nocturne's pin on Ripples is broken at 20 / 60 s`). Thrown or launched also tears her out
    of holds on her. A fighter who falls asleep on her feet slumps to the ground; a sleeping or frozen fighter
    doesn't try to get up.
  - A pinned fighter can't be knocked down, thrown, launched, or picked up: at most a blow drives her into the
    ground under her (the impact lands, she doesn't fall again). A fighter who is already down isn't "knocked
    down" a second time either; she can still be thrown or launched.
  - A pinned fighter can struggle, or strike or grab the one on top of her. She can't attack anyone else, pin
    anyone, lift anyone, or throw her pinner off with a strike (escapes are rolled). If the director has her
    "release" the pin on herself, that becomes a rolled struggle.
  - A fighter on the ground attacks from where she lies. She can't lift anyone, and can only pin an opponent
    who is on the ground too (she comes up on top). One fighter pins one opponent at a time.
  - A pin's presses always match the way the pinned fighter lies. The director's presses move to the exposed
    side; the parts YOU name in /pin or /hold turn her instead. When no side fits both, she's on her side.
  - A knocked-out fighter keeps the way she fell (shown in /status and told to the narrator) until she's back on
    her feet. `/fighter <name> revive` puts her back in the fight on the ground if she hadn't got up yet.
  - These rules bind the director. Your own /commands still do what you say (a /land throws a pinned fighter
    clear and ends the pin; /pin from underneath is a reversal), and the engine tidies up whatever that ends.
- Moves with `"uses": N` in fighters.json run out after N uses (Thunderbolt 3, Hydro Pump 4 by default).
  The attack header shows how many are left.

## Telling the storyteller what you want

Open **story_prompt.txt** in Notepad (or Spyder) and write instructions in plain English: how long each
beat's narration should be, whose perspective to use, how pins work, tone, anything. Both the director
(who decides what happens) and the narrator (who writes it) read this file before every beat, so you can
edit it mid-fight and the next beat follows the new instructions.

**style_sample.txt** is writing for the narrator to imitate. It starts with the prose from your online example
(no stats, no gore). Your original passage is in style_sample_intense.txt; rename it to switch. Stat lines are
stripped from samples automatically so the model can't copy them.
Swap in any passage whose voice you want. Only the first 4,000 characters are used
(`rules.json -> narration -> style_sample_chars`), because the model's working memory is limited.

Python still tracks every number. The storyteller decides *what* happens; the engine decides *how much it hurts*.

Narration settings in `rules.json -> narration`:
- `max_words`: hard cap per response (the story prompt sets the target length).
- `context_window`: the model's working memory. Longer narration and longer style samples need more.
  8192 fits comfortably on a 16 GB card with Mistral Small; 12288 may work but can slow things down.
- `recent_beats_remembered`: how many previous beats the models re-read for continuity.

## Several things in one beat

A beat can hold up to three actions in order (a chain of attacks by one fighter may run longer since build 110),
so directions like these happen in the engine, not just
in the prose:
- `Have Nocturne and Seraphina both attack Ripples`
- `Nocturne knocks Ripples onto her back, then pins her`
- `Seraphina throws Ripples into the wall` (the throw, then the landing as an environmental hit)

If any action in a beat is invalid, the whole beat is rejected and nothing changes.

## Getting up

A fighter knocked down, thrown, or launched stays on the ground until she gets back up, which is rolled at the
end of each later beat from her overall strength and how hurt the limbs she pushes up with are (arms and legs for
Ripples, legs for Nocturne, tail and body for Seraphina). Fresh: up on the first try. Hurt: she falls on the
first try, nearly makes it and stumbles on the second, and gets up on the third, winded and wincing. Badly
beaten: she fails all three and stays down until next beat (each beat down makes it easier). She grabs a
boulder, a stalagmite, the wall, or the ledge to do it. The stat block shows `🧗 Ripples gets up on the third
try (using a fallen boulder)`. Tune it in `rules.json -> getting_up`. While she's down, she can be pinned.
A pinned fighter doesn't get a get-up roll (she has to escape first), and `/getup` on a pinned fighter is refused.

## The move list (moves.json)

257 main-series Pokemon moves across all 18 types, each with its type, power (on this engine's scale), how it
targets (one spot, spread, whole body, hold, or a status move with no damage), whether it's close or ranged, and
its effects: paralyze, sleep, confuse, burn, poison, freeze, flinch, chill, or knocking down / throwing /
launching the target, each with a chance. Healing moves are left out on purpose.

- `/moves fire`, `/moves sleep`, `/moves launched`, `/moves status`, `/moves Nocturne` (what she knows now)
- `/moveinfo "Dragon Tail"`
- `/learn Nocturne "Dark Pulse"` lends her the move for THIS fight only (it travels with this fight's saves,
  never into fighters.json). `/forget Nocturne "Dark Pulse"` takes it away.
- The director sees every move with its range and effects, and is nudged toward a ranged or special move when
  the last three attacks were all up close.

New statuses from moves: **asleep** and **frozen** (can't act or dodge, barely fight a pin), **confused** (a third of
the time she hurts herself instead of attacking), **burned** (weaker hits, and the burn flares on a hurt spot each
beat), **poisoned** (loses 1% of her max health each beat). Tune them in `rules.json -> status_effects`.

## Dodges, status effects, stamina, and adrenaline

- **Dodges and counters** (`rules.json -> evasion`): the director's single-target and spread attacks can miss.
  The chance is 18% for a fresh fighter, lower when she's hurt, has damaged legs, is chilled, or is low on
  energy (max 35%). Nobody dodges while down, pinned, or paralyzed, or a whole-body move. After a dodge, 35%
  chance of a counter-hit. The stat block shows `💨 Ripples dodges Nocturne's NIGHT SLASH` and any counter.
  A dodged attack doesn't count toward the 3-attacks-before-a-pin rule. Your own /commands always land.
- **Status effects** (`rules.json -> status_effects`): Electric hits may PARALYZE (weaker attacks, no dodging,
  worse pin escapes), Ice may CHILL (half the dodge chance), Water SOAKS (Electric does ×1.5), Dark may make
  the target FLINCH (she can't attack next beat). Anyone the director places in water, or who lands in a pool or
  the channel, is soaked too. The stat block shows `⚡ Ripples is paralyzed (2 beats)` and the math shows
  `× 1.5 (soaked)`.
- **Stamina** (`rules.json -> energy`): every move costs energy (Thunderbolt 30, Hydro Pump 18, a targeted move
  10, a quick strike 6), and everyone gets some back each beat, more if they sat it out. A move can set its own
  cost with `"energy": N` in fighters.json. The attack header shows `energy 100→70`; `/status` and `/health`
  show everyone's energy and statuses.
- **Adrenaline** (`rules.json -> adrenaline`): the first time a fighter drops below 25% strength, she gets one
  surge for 3 beats: harder hits, better escapes and dodges, and an energy refill.

## Narration helpers

- **Pain tiers** go minor 🟢 → sore 🟡 → hurting 🟠 → very painful 🔴 → excruciating 🟣 → devastated ⚫ →
  **numb with shock ⚪ (1000%+)**: past a certain point the part goes numb and new hits there land as a dull,
  sickening jolt instead of more screaming. Edit them in `rules.json -> pain_tiers`.

- **Reaction tracker**: the narrator is told which reactions the last beats already used (ears pinned, eyes
  squeezed shut, gasps, the flotation sac...), and to pick different ones.
- **Movement that stays consistent**: once a limb or tail is very painful or worse, the program writes how she
  moves into her condition every beat ("limps badly, keeping weight off her left hock", "guards her right
  forearm fin").
- **Breaking points**: the first time a part becomes excruciating or devastated, the narrator gives it its own
  focused moment.
- **Voices**: each fighter has a `voice` in fighters.json that shapes her thoughts and cries.
- **Best of two** (`rules.json -> narration -> best_of_two`): for big moments (a pin starting or ending, a
  launch, a breaking point, an adrenaline surge) the narrator writes two drafts and keeps the better one.
  `"always"` does it every beat (twice as slow); `"off"` turns it off.

## After the win

The story doesn't stop when someone wins. Keep pressing Enter (or `/wait`, or type what happens, e.g.
`Nocturne nudges Ripples with her horn`) for aftermath beats: no attacks, time passes, and the loser slowly
comes around through four stages: **out cold → stirring → awake but down → back on her feet**. Each beat the
chance to move up a stage is 50% at full health, halved for every 50 points of health lost (never below 3%), so
a fighter pinned at -500% may lie there a long time. Getting up doesn't change who won. Settings:
`rules.json -> recovery`. `/status` shows each fighter's stage. Attack commands are refused once the match is
over; `/undo` takes you back into the fight.

## Fair fights and believable reactions

- **Strength is relative.** Fighters start with different health totals (Seraphina 2800%, Ripples 1400%), so
  the director and narrator see each fighter's health as a share of their *own* full health ("78% of full
  strength"). Ripples at 1400% is just as fresh as Seraphina at 2800%.
- **Momentum.** The director sees who made the recent attacks. If one fighter makes `initiative_after` (3)
  attacks in a row while an opponent still has at least `initiative_min_strength` (35%) of their strength, the
  director is told to hand that opponent the initiative: a counter, a reversal, an escape. Your own
  directions always win. Settings: `rules.json -> director`.
- **Overall strength outranks part pain.** Body-part damage decides how that part feels (screaming, favoring
  it, not using it). Overall strength decides what the fighter can still do. A fresh fighter with a wrecked
  shoulder cries out and guards it, but stays up and keeps fighting. Collapsing and being unable to rise are
  only for fighters who are spent or past the limit. The wording is in `rules.json -> health_tiers`.
- **Nobody is knocked out by hits.** Only a pin held for the full clock puts a fighter out
  (`rules.json -> pin -> director_can_eliminate: false`). Your `/eliminate` command still works.

## Launches, throws, and landing in the arena

Big hits move bodies. The director can mark a strike as `staggered`, `knocked down`, `thrown`, or `launched`,
and list what the fighter crashes into, in order: a stalagmite, then a boulder, then the stone floor. Each
surface hits its own set of body parts, using `rules.json -> severity -> environment` for power. The landing
gets its own stat block (`Impact — Ripples launched: a stalagmite → a fallen boulder → the stone floor`) and
leaves the fighter **on the ground**.

A targeted strike on one body part also jars the parts right next to it (a jaw strike catches the head and
neck): `rules.json -> moves -> auto_spill` (`parts`: how many, `factor`: their power as a share of the
move's base power; set `parts` to 0 to turn it off). The stat block lists them as "Jarred next to it".

Manual: `/land Ripples "a stalactite=Upper Back+Head:heavy; a boulder=Left Shoulder:solid; the floor:solid"`
(parts are optional). `/down Ripples` marks a fighter as on the ground without damage.

A fighter who is already lying on the ground can't be knocked down again: with no surfaces listed nothing more
happens, and with surfaces listed she is `driven into` them where she lies (the damage lands, her position and
the way she faces stay the same). A pinned fighter is only ever driven into the ground under her.

## Moves, types, and targeting

Each fighter in fighters.json has `types` and a list of `moves` (name, type, power, target, and a short
`about` the storyteller reads). The engine calculates every attack like this:

**Effective power = move power × type effectiveness × targeting**

- Type effectiveness uses the full Pokemon type chart (rules.json -> moves -> type_chart): Electric vs
  Water ×2, Fighting vs Dark ×2, Water vs Water ×0.5, and so on.
- `targeted` moves hit one body part ×2; if the strike drags across neighboring parts, those take a
  lighter ×1 carry-over hit (`/move Nocturne Ripples Slash "Left Upper Arm,Left Forearm Fin,Left Paw"`). `spread` moves hit several parts ×1. `whole_body` moves (like
  Thunderbolt) hit every body part ×1. `hold` moves start a hold or pin that presses every beat.
- Damage to each part = effective power × that part's resistance multiplier; resistance then drops by
  effective power × 0.8.
- Hits that aren't named moves (landing on stone, slamming into a wall) use the severity words instead.

Each attack prints a header (`Attack 3 — Nocturne → Ripples: THUNDERBOLT (whole body)`), the narration,
then the stat block with the type math. Whole-body attacks get a table grouped by resistance.

Manual: `/move Seraphina Nocturne "Hydro Pump" "Chest,Left Shoulder,Right Shoulder,Neck"`,
`/move Ripples Nocturne "Aqua Jet" "Right Flank"`, `/move Nocturne Ripples Thunderbolt`.

Pressing Enter the first time narrates the arena and the fighters arriving; the next Enter starts the fight.

## Damage speed

`rules.json -> damage -> damage_scale` multiplies every hit's damage (default 2.5). `resistance_scale` (default 1) separately
multiplies how fast resistance wears down; change it with `/resscale 1.5`. Change it mid-fight with
`/scale 3` (it's saved to rules.json); `/scale` alone shows the current value. It doesn't change how fast
resistance wears down, so the escalation on worn-down parts stays the same shape, just bigger.

If **health** is what feels slow, lower the fighters' starting `health` in fighters.json (your online
example used 1000% each), or raise `health -> loss_per_damage_point` in rules.json (0.2 means every 1% of
body-part damage costs 0.2% health).

## Getting better narration

**Try a creative-writing model.** Cydonia 24B is a storytelling fine-tune of the same Mistral Small,
with the same size (14.3 GB at Q4_K_M), so it fits a 16 GB card. In Command Prompt:
```
ollama pull hf.co/TheDrummer/Cydonia-24B-v4.3-GGUF:Q4_K_M
```
Then run play.py with the command line option `--model hf.co/TheDrummer/Cydonia-24B-v4.3-GGUF:Q4_K_M`
(in Spyder: Run → Configuration per file → Command line options).

**Longer and more detailed:** `/words 1000` (saved to rules.json). Long beats are written in focused parts of
~300 words: the attacker's side, the receiver's side, the aftermath, and (at 4 parts) the lead-up. Short
parts keep the detail dense instead of thinning out. Above ~900 words, raise `context_window` to 12288 if your GPU
has room. Pin beats are kept to `pin_words_per_second` x seconds per beat (in rules.json -> pin).

**Fitting the model's memory:** the narrator gets only the rules each beat needs (the story prompt's PINS section
only on pin beats; a fighter who's out shows up as one line until the aftermath), and before every call the program
checks the prompt plus the answer fits `context_window`. If not, it shortens the recap of earlier beats first,
then the start of this beat's earlier parts, then the style sample, and says so ("trimmed older story context").
This beat's events, the fighters, their conditions, and the rules are never cut.

**Settings that shape the prose** (`rules.json -> narration`):
- `words_per_beat`: target length (default 500); `words_per_pass`: size of each part (default 300).
- `two_pass_pov`: writes the attacker's side and the receiver's side as two separate halves. Keeps long
  beats coherent and gives you the dual perspective. Turn off for faster, single-pass beats.
- `repeat_penalty`: raise it (1.15-1.2) if you still see repeated phrases; lower it (1.05) if the prose
  gets strange word choices.
- `temperature`: 0.7 for steadier prose, 0.9 for wilder.

**Sharper story prompt = sharper prose.** Local models respond to blunt, concrete instructions. Add
examples of what you want and don't want to story_prompt.txt.

## Pins

A pin presses several body parts at once, each with something: `/pin Nocturne Ripples
"Chest:crushing=her full weight,Neck:firm=teeth,Right Ribs:firm=claws in a pressure point"`.
Every pressed part takes damage every beat. Then the engine runs the pin:

- **Clock:** each beat covers `seconds_per_beat` of the `duration_seconds` pin (10 of 60 by default).
  Change it live: `/pinbeat 5`, `/pinbeat 1`, `/pinlength 90`. Pressure damage and struggle odds scale
  with the beat length, so 1-second beats show more, smaller moments with about the same outcome.
- **Struggles:** every beat the pinned fighter may try to escape. The engine rolls it: a failed attempt
  (the pinner punishes it with extra pressure), a partial break (the pinned fighter lands a hit on the
  pinner), or a full escape (the pin ends).
- **Escape odds follow her health.** Each try works 65% of the time at full health, sliding to 40% at half
  health; below half it halves for every 20 points of health she loses (about 28% at 40% health, 17% at 25%,
  10% at 10%, 7% at 0, and on into negative health). Over a whole 60-second pin by a fresh pinner, that comes to:

  | her health when the pin starts | she escapes |
  |---|---|
  | 100% | about 95% |
  | 80% | about 88% |
  | 65% | about 72% |
  | 50% | about 54% |
  | 40% | about 39% |
  | 25% | about 34% |
  | 15% | about 20% |
  | 5% | about 10% |

  So a healthy fighter nearly always breaks out, around half health it is anyone's guess, and a badly hurt one
  usually goes the full 60 seconds, struggles and all. (The pin's own pressure keeps draining her while it runs,
  and a hurt pinner or an adrenaline surge raises her odds a little.) If the escape fails, she may break loose
  for a moment and hit the pinner (50% at full health, falling on the same curve); that gives her momentum:
  ×1.5 escape chance on the next beat (`break_loose_buff`, `break_loose_buff_beats`). Settings:
  `rules.json -> pin -> struggle` (`escape_chance`, `escape_easy_above`, `escape_chance_at_edge`,
  `escape_halves_every`, `attempt_chance`, `partial_chance`, `escape_steps`). `escape_easy_above 0` with
  `escape_halves_every 25` gives back the old curve.
- **Full duration:** the pinned fighter faints and is out.
- **When the director may pin** (`rules.json -> pin`, and `director -> pin_urge`): a pin can come at any point
  in the fight, but only when there is an OPENING, which the engine rolls for every fighter at the start of each
  beat: 6% of beats while she is on her feet with at least half her strength, 30% while she is knocked down, 45%
  on her feet under half strength, 85% knocked down under half strength, and those last two climb toward 95% as
  she nears nothing. A standing opponent is taken down straight into the pin (or knocked down first, with the pin
  as the second action). When there is an opening and you just press Enter, the director is told to go for it;
  when there isn't, a pin it tries anyway is refused (if it came after a strike in the same beat, the strike
  still happens). After a pin attempt she must take one attack before the next (`attacks_between_pins`).
  `require_downed: true` brings back "only on the ground". The director sees "can be pinned now: YES/NO (why)"
  and her escape odds for every fighter. Your `/pin` and `/pinsuccess` commands and anything you type as a
  direction skip these rules.

While a pin is running, just press Enter (or `/wait`): the director keeps the pin going and the engine
rolls the struggle. Tune the odds in `rules.json -> pin -> struggle`.

## Stats display

`/math auto` (default): full before/calculations/after blocks for attacks, one compact line for pin and
hold beats (`Chest 25→50🟡 · Neck 116→172🟣 · ❤️ 356% → 305%`). Also `/math full`, `/math compact`,
`/math both`, `/math off`. The program prints all stats itself; the narrator never writes numbers.

## Multiple fighters

- Add as many fighters as you want to `fighters.json`. It comes set up with Nocturne (Absol), Ripples (Buizel), and Seraphina (Milotic).
- With no `team` set, it's every fighter for themselves. Give fighters the same `"team": "Blue"` to make
  them allies; the director won't have allies attack each other and may have them double-team.
- An eliminated fighter can't act or be targeted, and any holds involving them end.
  The fight continues until only one fighter or one team is left.
- One action can hit several fighters (a tail sweep, a dive onto two people). Manually:
  `/combo Seraphina Nocturne "Left Thigh:heavy,Ripples>Left Thigh:solid" "tail sweep takes out both"`
  (`Name>Part` hits a different fighter). The stat block shows a section for each fighter hit.

## The stat block

After each beat's prose, the program prints the exact numbers in this format:

```
**Before:** (Nocturne)
- Sickle Tail: 🟦 180% | 🟢 10%
**Calculations:**
- Sickle Tail: Res 180% (>100% bracket, 0.15× mult). Damage: 40 × 0.15 = 6%. New damage: 10 + 6 = **16%**. Res: 180 - 32 = **148%**
**After:**
- Sickle Tail: 🟦 148% | 🟢 16%
- ❤️ Nocturne Health: 1800% → **1798.8%**
```

- Colored **squares** = resistance, colored **circles** = body-part damage, ❤️ = overall health only (a percentage that starts at each fighter's starting health and can go below 0%).
- These blocks come from the Python engine, never from the model, so they can't get mixed up.
- `/math off` hides them, `/math on` brings them back. `/status` shows every body part for every fighter.

## Customizing

- **fighters.json**: the scene, plus each fighter's description, `appearance` (exact colors and anatomy the narrator must use), body template ("human", "tailed",
  or your own), starting health, per-part resistance overrides, and `extra_parts` for anything unusual.
- **rules.json**: everything numeric.
  - `body_templates`: body part lists with starting resistance (%). Add your own templates.
  - `resistance.brackets`: the multiplier and icon for each resistance range.
  - `resistance.loss_per_power`: resistance lost per hit = power x this (0.8 means power 40 costs 32).
  - `severity`: attack power behind each word the director can choose ("light", "heavy", "crushing"...).
  - `health`: how damage, exhaustion, and badly hurt parts drain overall health.
  - `pain_tiers`: damage thresholds, icons, and the reaction the narrator must follow at each level.
  - `pinfall`: kickout odds.
  Values marked GUESS are placeholders until the real rule is known.

## How the math works

- A "beat" is one thing happening in the story.
- Named moves: effective power = move power x type effectiveness x targeting (see "Moves, types, and targeting").
- Damage taken (%) = effective power x the multiplier for the part's current resistance bracket
  (>100%: 0.15x, 70-100%: 0.40x, 50-70%: 0.75x, 30-50%: 1.20x, below 30%: 1.50x).
- Then that part's resistance drops by effective power x 0.8.
- Multi-hit attacks resolve in order, so the second hit uses the resistance left after the first.
- Holds deal damage every beat (including beats where something else happens) until released,
  and can tighten or ease over time.
- Health drops by 0.2 per 1% of damage taken, 0.5 per beat of exertion (only for fighters involved in that
  beat), and more each beat for every part at 90%+ or 150%+.
- Pinfall: at each count, kickout chance = remaining health fraction x (1.0, 0.75, 0.5).

## Build 52
- New accuracy check: if a fighter took no hits this beat (she dodged, or nobody attacked her), the narrator may not give her new wounds (claws scraping her, skin splitting, "where those claws had grazed"). The draft is rewritten, and any line that still slips through is dropped.
- More falls are caught: "fell sideways", "fell into the water", "toppled", "went sprawling".
- Counters are described as their own quick strike, separate from the countering fighter's next attack.
- The "what it feels like" part of a beat only covers fighters who were actually hit.
- A fighter eliminated before taking damage stays in the cave: no trainers, Poké Balls, or recalls (she can still recover in the aftermath).
- Fixes the model's "tail hashing" typo to "lashing".
- Wounds have to be real: cuts, blood, or claw marks on a body part with no damage (like "the shoulder still burned where Nocturne's claws had grazed it" after a dodge) get rewritten or dropped, so invented wounds can't carry forward into later beats.
- More collapse and fall wording is caught: "crashed face-down onto the ledge", "knees buckling", "consciousness slipping".
- Each move is told as its own type: Nocturne's stored electricity only shows up in Electric moves.
- /move works with any move in moves.json, even one the fighter doesn't know (used once, not learned). If you leave out the body parts, the dice pick them.
- Getting up on the first try is one clean attempt that ends on her feet; extra failed tries get rewritten.

## Build 53
- The memory budget learns the model's real token count from Ollama after the first call, instead of a cautious guess. The guess had been overestimating prompts by roughly 15–25% and trimming the story recap when it didn't need to.
- Lines where the model talks to you instead of telling the story ("This is an incomplete response… Let me try again", "I'll narrate the continuation…") are removed.
- A beat that's only an elimination is written in one pass. Splitting it in two left the model nothing for part 2, which is what produced that meta-text.
- No stray electricity: if no Electric move happens in a beat, lines about electricity, lightning, or crackling current get rewritten or dropped.
- /sustain: a comma list of body parts in the 5th slot (/sustain Nocturne Ripples "Hydro Pump" 3 "Chest, Neck, Head") is read as the parts to hit, not as something she's pressed against. Use "none" for no surface.
- Fighter names forgive small typos ("Nocturn" → Nocturne), so a chained command no longer stops on one.

## Build 54
- Broken-prose check: if a draft falls into run-on chains ("…cascading damage cascades multiplying exponentially—"), drops "the" and "a", copies whole phrases from earlier beats, or keeps trailing off on dashes, it gets rewritten. Any leftover broken sentences are dropped, as long as most of the beat survives.
- Prompts never overflow the model's memory. If trimming the recap isn't enough, the style sample is left out for that call, and then the earlier parts of the beat are shortened further. Ollama used to cut off the start of an oversized prompt (the rules!), which is what made the prose fall apart.
- repeat_penalty lowered from 1.12 to 1.03 (repeat_last_n 256). A high repeat penalty punishes common words like "the", "a", and the period, which pushes the model into telegraphic, dash-chained run-ons. Repetition is handled by the program's own checks instead.

## Build 55
- /numb on|off switches the "numb with shock" pain level (1000%+ damage). Off: those parts stay "devastated" ⚫, the ⚪ icon leaves the stat blocks and legend, and the narrator is told the worst parts stay sharply painful instead of going numb. Saved to rules.json as narration.numb_tier (also settable with /set narration.numb_tier false).

## Build 56
- Lingering reactions: in about 30% of beats, one blow gets a long, slow reaction (about 200 extra words). That covers the contact, the sensation spreading, breath, body, thoughts, the look at her opponent, and how she gathers herself. Any kind of hit can be picked: strikes, pin or hold pressure, landings. Heavier blows are likelier picks, but light ones get chosen too. The reaction stays true to size: the length comes from detail, not from making the injury worse. Tune it with /set narration.linger_chance 0.5 or /set narration.linger_words 300; linger_chance 0 turns it off.

## Build 57
- No retelling between parts: if the first part of a beat already showed every hit landing, the second part is told to continue from there (aftermath, pain, breath, thoughts) instead of telling the attack and fall again.
- A fighter knocked out this beat keeps her full description for that beat, so the narrator knows she's a serpent (no "legs buckled" on Seraphina). She shrinks to one line from the next beat on.
- More invented falls are caught ("her hip slammed into the stalagmite", "her side hit the water", "lay half in the water"), except for a fighter really thrown into the scenery this beat.
- Surface labels no longer end mid-phrase ("the slick algae-covered stone of the" → "the slick algae-covered stone").

## Build 58
- One strike stays one strike: when a blow jars the parts next to it, the narrator is told it's a single impact spreading, not extra swings ("bringing her claws down again" / "three hits in one exchange").
- A dodge is told once: if the attack part already showed the miss, the next part continues from there instead of retelling the dodge.
- Ripples' description says her "paws" are her hands and she walks on her feet, so a hurt paw isn't narrated as a hurt leg.

## Build 59
- Swearing that slipped through ("Damn it", "what the hell") is now caught like the rest of the tone rules.
- Falls into water count as falls ("crashed into the shallow pool"), so a fighter who wasn't knocked down can't be narrated into the pool.
- A stray, unmatched * around a thought ("But slow now.*") is fixed.

## Build 60
- Pin starts: the narrator is no longer handed "0 of 60 seconds" (which it copied into the prose) or the "there is NO pin" rule (which contradicted the pin). It's told the pin has just begun and to mention no clock or seconds yet. "Pin clock", "0 of 60 seconds", and "started its countdown" are caught as game terms.
- Echoed short lines inside one beat ("*Damn it.*" … "*Damn it.*", "Nothing moved." twice) keep only the first.

## Build 61
- Neck and throat bites: the director is told they're fair game, standing or in a pin (jaws clamped on the neck or throat, twisting and wrenching), as a strike or as a hold when the jaws stay locked. They're also in the pin-technique list. The narrator may write them brutally (teeth sinking in, the wrench, the choked gasp) within the tone rule: nothing torn out, and the neck never snaps or bends at a wrong angle unless it's allowed to break.
- "Teeth sank through the thick ruff" is no longer mistaken for extreme gore; teeth going through the neck or throat itself still is.

## Build 62
- Pin seconds only move forward: a draft that marks "Thirty seconds." and then "22 seconds..." gets rewritten, and any leftover backward marks are dropped.
- No time-remaining talk during pins ("Just ten more, and this ends", "ten more seconds", "N seconds left"): the fighters don't know how long is left.
- Pain-level labels can't leak into the prose as labels: "*Devastated.*", "Numb with shock.", "her hip—devastated, barely holding", and "*Adrenaline surge.*" are caught like other game terms. Ordinary uses of the words ("a devastated look") are fine.
- A strike during a pin (like a bite) isn't told twice anymore: the no-retelling check now looks at the strike's hits only, so ongoing pin pressure doesn't stop it from kicking in.
- "Blood—warm and coppery—flooded her mouth" is caught as extreme gore even with words or dashes in between; a trickle or bead of blood is still fine.

## Build 63
- Swearing is allowed, but rare: at most one curse per beat, in a thought or spoken line, and none again for the next 5 beats (narration.swearing_gap). Anything beyond that is rewritten or dropped. Change it with /set narration.swearing never (none at all) or free (no limit).

## Build 64
- After the match, /getup <loser> brings her back to her feet (narrated the hard way: grabbing onto rock, a failed try, finally standing shakily, knowing she lost). /recover <loser> moves her up one stage (out cold → stirring → awake but down → back on her feet), or straight to one: /recover Ripples awake. Neither changes who won.
- Thoughts and spoken lines already used in recent beats (or earlier in the same beat) are removed, along with their "she thought, ..." tag. No more "*Still breathing. Good.*" three beats running.
- Pain-level labels in pairs ("hurting, not devastated") are caught like other game terms.
- Fixed: the rare-swearing spacing counted each beat twice.

## Build 65
- /help is reorganized into sections: Playing, Attacks you choose, Holds and pins, Steering, Moves, Healing and after the match, Rules and fighters, Looking around, Undo/files/quit. Every command is still there.
- Aftermath beats are full length again (the build 64 shortening is undone). Instead, each one is asked to find new details: a different injury, an unused sense, small changes in breathing or posture, a specific memory from the fight.

## Build 66
- /focus aims attacks at body zones: head, core, arms, legs, paws, tail, limbs (arms + legs + paws), upper (head + core). Combine them (/focus core head), set it for everyone or for one attacker (/focus Nocturne limbs), and turn it off with /focus off or /focus Nocturne off. It's saved to rules.json (director.focus), so it carries over between runs.
  - The director is told which of each opponent's parts are in the zone.
  - With focus_strength (default 0.6), an attack the director aims off the zone is moved onto it that often; /focus strength 0 makes it a pure nudge, 1 makes it firm. Your own /move, /strike, and /combo commands are never changed.
  - A fighter without that zone (Seraphina has no legs or paws) is simply open everywhere.
  - The zones live in rules.json under body_zones (body regions and/or words in part names), so you can edit them or add your own.
- /status, /status full, /status <name>, and /health now show knocked-out fighters in full (health, every body part, their recovery stage) instead of just "eliminated".

## Build 67
- Single-hit moves land once: the director can only repeat a move (count > 1) if it's a flurry move (rules.json moves.multi_hit: Fury Swipes, Double Kick, Bullet Seed...). An Aqua Jet no longer slams the same leg three times in one beat. Your own /move commands can still use a count.
- A get-up that succeeds has to end with her standing; a draft that leaves her on the ground ("Third time's the charm. Has to be.") is rewritten.
- More invented falls are caught ("crashed backward onto the dry ledge", "Ripples hit the water hard").
- More bone breaks on parts that can't break yet are caught ("the bone clearly broken", "hung at an angle that...").
- Game-time talk like "*Three beats. She'll be soaked.*" is caught as a game term.
- Momentum: a fighter can now attack 3, 4, 5+ times in a row, but the longer the streak runs, the likelier the director is told to shift the momentum to the opponent (40% once she's made 3 in a row, +20% per extra attack, up to 95%). In practice most streaks end by the 4th or 5th attack and almost never pass 6. With /plan dominate the winner's streaks shift far less often. Tune it in rules.json under director (initiative_chance, initiative_step, initiative_max, initiative_dominate_factor).

## Build 68
- Faster without cutting anything: the narrator's system prompt now puts the parts that never change (rules, style sample) first and the per-beat lines last, so consecutive calls in a beat (part 2, second drafts, rewrites) share an identical opening that Ollama can reuse instead of re-reading ~4,500 tokens each time.
- New launch options: --director-model and --narrator-model let the director (picks attacks, writes JSON) and the narrator (writes the story) use different models. Default is still one --model for both.
- Spread moves (Water Gun across chest, ruff, and belly) are described as one blast catching several parts, not three separate shots.
- When the first part of a two-attack beat already showed some hits, the second part is told which hits are done and which are still to show, so it doesn't retell the first attack.
- More breaks on parts that can't break yet are caught ("*Broken. Completely broken.*", "like a thick branch breaking").
- Swearing limits now count earlier parts of the same beat in the final cleanup too ("Damn it" in part 1 and another curse in part 2).
- Status names used as labels in thoughts ("*Flinched.*") are caught like game terms.
- Short spoken lines repeated across beats ("Again," Nocturne snarled… three beats running) are removed like longer ones.
- The rewrite note now names the "useless too early" check instead of the vague "draft".

## Build 69
- Facing: a fighter on the ground is now face-down, face-up (on her back), or on her side. It comes from how she landed (back first = face-up; chest, belly, or face first = face-down; otherwise rolled), and it's saved, undone, and shown in /status and /health.
  - The director sees it, and the narrator is told it every beat ("lying FACE-DOWN: chest, belly and face against the ground; her back, hips, tail and the back of her neck are exposed").
  - Pins follow it: on a face-down fighter, the director's presses on the chest or belly move to her back (throat → neck), and the reverse face-up. If every press is on the hidden side and the director says she's rolled over, she's turned over instead.
  - A draft that puts her the wrong way round ("on her back, staring up at the stalactites" while she's face-down) is rewritten, unless it shows her rolling over.
  - /down <fighter> down|up|side puts her down a given way; /face <fighter> down|up|side rolls someone already down; /face shows who's how.
- Rewrites are checked too: the one rewrite per draft used to be trusted blindly, and in a playtest it dropped the pin escape the first draft had shown. Now if the rewrite breaks something that changes what happened (an escape, a hit, a get-up, an invented fall...), the draft is kept instead and its smaller slips are cleaned up.
- Rebalanced damage (all in rules.json; the old values are kept under resistance._previous):
  - Body parts wear down slower: resistance lost per power 0.8 → 0.5.
  - Hits on worn-down parts hurt the part more: bracket multipliers 0.15/0.4/0.75/1.2/1.5 → 0.2/0.45/0.8/1.3/1.8.
  - Health loss now depends on how worn the part is: damage × 0.18 × a per-bracket health_mult (0.7 armored, 1.0 sturdy, 1.3 weakened, 1.7 thin, 2.2 fragile). Hammering a weakened limb drains health fast; spreading hits over fresh parts costs much less.
  - Spread moves hit each part at ×1.25 (was ×1), so ranged multi-part moves (Water Gun, Ice Beam, Dark Pulse) keep up with single-target strikes.
  - Type advantages are unchanged.
  - Measured with 200 simulated fights each: knocking Ripples from full to 0 health took about 39 hits spread around (was), now 30; about 32 hits when focusing a worn limb, now 18. The worst single part at the end dropped from about 4,200% to 2,800% on the focused runs. The stat math now shows each hit's health cost and its multiplier.
- Throat and neck bites, encouraged but never demanded: on about 12% of beats (when someone has Bite, Crunch, Ice Fang...) the director gets an optional idea to go for the neck or throat, and on about 25% of pin beats an idea to clamp the jaws on the neck or throat as a pin technique. Tune with director.throat_bite_chance and director.throat_bite_pin_chance.

## Build 70
- The director decides when to move a fighter who's down, as part of any attack or pin beat (a new "reposition" choice, "none" most of the time):
  - roll over / onto her back / onto her front / onto her side: she's turned, and a running pin's presses move with her (chest presses go to her back when she's rolled face-down, and the reverse);
  - pick up: hauls her up off the ground to slam, throw, or hold her up for a strike (not while she's pinned). If the strike throws her, she lands again and her facing comes from that landing.
  - It's told to use these now and then, when they serve the moment, and the same fighter can't be moved again for 2 beats (director.reposition_cooldown), so it never becomes an every-beat thing.
  - The narrator has to show the roll or the lift before the attack; a draft that skips it is rewritten. The stat block shows 🔄 rolls (with any pin presses that moved) and 🏋️ lifts.
- /roll <attacker> <defender> over|back|front|side|up makes it happen as a narrated beat on your command (no cooldown). /face still sets it silently.
- Fixed: a pin started on a standing fighter now infers the right facing from the presses (chest pressed = she's on her back).

## Build 71
- Short beats get topped up: when a beat ends up under 55% of its target length (in practice because copied or repeated lines were removed, as in a long pin where the model starts reusing the previous stretch), one more pass continues it with new detail: one body part and how it feels now, breathing, shifts of weight, the cave, a new thought. Cleanup no longer costs length. narration.top_up_below sets the threshold (0 = off).
- Pin beats rotate their focus so consecutive stretches don't read the same: the pinner's own effort and injuries, one pressed body part, breath and sound, what the pinned fighter tries, what they see in each other up close, the ground under them.
- "Twenty to go" style time-remaining lines are caught (the earlier check needed the word "seconds").

## Build 72
- For a fighter who stands upright with arms (Ripples), every hit on an arm part is spelled out for the narrator: "Left Paw (her HAND, at the end of her arm: she doesn't stand on it)", "Left Forearm Fin (on her ARM, not a leg)", and leg parts as "(her leg: she stands on it)". A slash to her paws should no longer be told as a hurt foot or a buckling leg.

## Build 73
- More invented falls are caught: "hammered her down onto the slick stone", "hit the shallow water hard", "lay there", "her leg went out from under her".
- The director can't pass off getting up as an attack: an improvised move called "Attempted Push-Up" (or get up, stand up, recover, brace, retreat...) is rejected, and it has to pick a real attack or a pause.
- "Bone grating against bone" is caught on parts that can't break yet, and "electrified" counts as stray electricity.

## Build 113
- **Aqua Jet keeps touching her until it's over.** A charge wrapped in its element (Aqua Jet, Wave Crash, Flame Wheel,
  Flare Blitz, Spark, Wild Charge, Volt Tackle...) never leaves the one it hits between the hit and the slam: she is
  carried inside the water (fire, current), and it keeps pressing, stinging and scouring at the struck part and the
  parts round it the whole way. Those contacts are in the stat block as "carried inside the water". The narrator is
  told there is no gap and no second strike, so she is never hit "again" as if the attacker had outpaced her.
  `moves.charge.sheath` (`power` 0.25 of the main hit, on `parts` 3 round it; power 0 = off).
- **Aqua Jet costs 40 energy** (48 with the charge into something; it was 18). Twice in a row leaves Ripples winded
  even with a beat of rest between. Set `"energy"` on the move in fighters.json to change it.
- **Pummels anywhere close.** Short blows thrown again and again (a strike with a count) now work on a fighter who is
  DOWN (lying or sitting, not pinned), and on one still PRESSED AGAINST the scenery after a charge, not only inside a
  standing grab. The stat block and the narrator say where. Inside a pin they are off by default (a pin holds her;
  it doesn't rain blows): `grapple.pummel_in_pin` true allows the director to do it; your own commands always can.
- **Pins wear her down; they don't wreck her** (`pin.pressure_cap`). A pin's steady pressure, and the extra press
  that punishes a failed struggle, no longer bite into a worn-down part as hard as a blow does: they never use more
  than ×0.45 damage (`mult`, as if the part were only sturdy) and ×1.0 health (`health_mult`), however ruined the
  part is. Before, a forepaw on a destroyed stomach did about 99% damage and ~86 health a pin beat at `/scale 5`
  (a fighter could end a pin at −875%); now it is about a quarter of that, and presses on healthy parts are
  unchanged. `/pinpower` is still the overall dial on top. Blows thrown during a pin (techniques, the escape hit)
  are not capped. The stat block marks a capped press "(pin cap)". `enabled` false brings back the old rule.
- **Each blow of a pummel and each link of a chain picks its own spot.** After the first, the dice decide whether it
  lands on the same part again or somewhere new (usually right next to it). Parts you name (in a /command, or in a
  direction you type) are kept as you said. `moves.repeat_target` (`stay_chance` 0.5, `near_share` 0.7). The
  rolls are listed with the others.
- **No hard caps on pummels and chains by default** (`grapple.pummel_hard_cap` and `director.chain.hard_cap` are 0).
  They still end on their own: the longer they run, the likelier; set a number to bring a cap back.
- **Raw reactions.** A real blow on a part that is ALREADY very painful, excruciating or devastated gets a visceral
  reaction, scaled by three things: how hurt the part was, how big this blow is (a brush on a ruined part is far less
  than a real blow there), and how much strength she has left AS THE BLOW LANDS. With most of her strength she fights
  to keep it in (a hiss, a bitten-off cry); worn down, a real scream and shaking; nearly spent, a raw scream that
  cracks, shaking she cannot stop, streaming eyes. One big reaction per fighter per beat; later blows that beat build
  on it. Never sobbing or weeping. 14 new story blocks for it. `narration.raw_reactions` false turns it off.
- **No wild health swings** (`health.soft_cap`). A blow on a badly hurt part still costs a lot of health (its low
  resistance sees to that), but health one hit costs past 5% of the fighter's own full health, and health everything
  that lands on her in one beat costs past 12%, counts only at 30%. In a long test fight a five-blow pummel on a
  destroyed chest had cost 855 health in one beat (half her health); across 60 fights at your settings the worst beat
  is now about 155-365, and fights run about 40-50 beats. The stat block shows "softened from" on a hit it applies to.
  `per_hit`, `per_beat`, `above`; `enabled` false = the old rule. The health it keeps from her isn't simply lost:
  `to_resistance` (0.1) resistance points come off the hit part for every point of health softened away, so a ruined
  part keeps getting softer ("+N from the softened health" in the stat block).
- **Whose eyes these are.** Each part of a beat's narration is headed with whose side it is told from: a line
  `— Nocturne —`, `— Ripples —`, or `— Both —` for a part about both of them. Beats already came in two parts (the
  attacker's side, then the receiver's); now you can see where one ends and the other begins. A beat where nobody is
  hit (one of them catches her breath) is now told in two parts too, one for each fighter, at the same length. The
  labels are put in after every check and only for you: the models read earlier beats without them, so they don't
  start copying them. `narration.pov_labels` false turns them off.
- **Fixes found in a long stand-in fight:** a strike with a count on a fighter who could not be pummelled (standing,
  not held) landed every blow at full power; a nearly spent fighter in a pin was described as having "plenty of fight";
  blows on a pinned or downed fighter were told "nobody stays latched on"; the build-on-it reaction named "the same
  hurt" when it was a different part; a charge that carried on through what it broke listed the second slam as part of
  the first hit in the stat block.
- **sim/**: run scripted fights on the real engine without Ollama (`python sim/long_fight.py 7`): every roll is the
  engine's; the narrator's prompts can be saved to read.
- **Limbs that can't do the job.** A move thrown with a badly hurt limb (paw, arm, foreleg, tail, jaw, wing) loses
  power: ×0.8 once that limb is past 150%, ×0.6 past 300% (`moves.limb_limits`). It's in the move math line.
- **What a pin leaves behind.** Breaking out of a pin held two beats or more leaves her **stiff** 🪵 (weaker blows,
  slower dodges) for a beat; four beats or more, **cramped** 🦵 too. The pinner tires: holding a pin costs her energy
  each beat (`pin.pinner_energy_per_beat`), and a tired pinner is easier to break (😮‍💨). A fighter who has broken a pin
  of one shape **knows it** 🧠 and escapes that shape more easily the next time (`learning`); she also dodges a move
  she has felt a few times a little better.
- **Coils and constriction.** A serpent (or anything wrapping with coils or tails) that holds or pins with them
  tightens beat by beat; she is **constricted** 🐍: her blood held back, energy draining, arms trapped, and her heart
  slowing (never stopping). A pin of coils (`coil_crush`, `tail_choke`) can put her out by constriction. `holds.coil`.
- **Water in the mouth.** A water attack to the face, or on a fighter lying face-up or held at point-blank, can go
  into her mouth and nose: **sputtering** 💦, coughing it up (no breath back, weaker blows and escapes). Never drowning.
  `moves.into_mouth`.
- **Clashes.** A ranged attack can be met head-on with one of the defender's own: the two meet in the air and one
  pushes through (weakened), they cancel out, or the defender's turns it back onto the attacker. Whole-body and
  wide moves weigh more. `moves.clash`.
- **The arena joins in.** Deep water helps a swimmer dodge and hinders a non-swimmer; slick ground can make a dodger
  slip (the attack still misses, but she's down); a hard slam into the scenery can shake something loose (a
  stalactite comes down at the end of the beat); a new pin shape holds her head under the shallow water (the dunk).
  `arena`.
- **Flight.** A fighter with wings (Talon) can "take off" (a reposition on her own action): in the air only ranged
  moves reach her, her close moves become **dives** (×1.3), after which she climbs back up or lands, and the one she
  dove at may catch her and drag her down. Nobody can hold or pin her in the air. A wing hurt to 150% grounds her,
  and if it happens in the air she falls. **Sky Drop** carries the other up and drops her from a height (the higher,
  the harder she lands). `flight`.
- **New moves** (moves.json, lend them with /learn): **Protect / Detect** (the next attack stops against it; less
  reliable used twice running), **Counter** (the next close blow is sent back harder) and **Mirror Coat** (the same
  for blasts and beams), **Rain Dance / Sunny Day / Hail** (weather for 5 beats: rain strengthens Water and weakens
  Fire, sun the reverse, hail stings everyone not Ice-type each beat). Sky Drop. `stances`, `weather`. Roost and other
  healing moves are left out on purpose, as before. A move can now say `"ranged": false` (Close Combat is a close
  flurry even though it hits several parts).
- **New fighters** (on the bench: `"bench": true` keeps them out of the default fight; `/newfight Talon Nocturne`
  brings them in): **Talon** (Staraptor, flyer), **Vesper** (Arbok, coils and venom), **Blaze** (Arcanine), **Aura**
  (Lucario), **Undertow** (Floatzel). Ripples, Nocturne and Seraphina are unchanged.
- **New arenas**: the **mud swamp** (sucking mud, black water, gas bursts), the **tidal beach** (surf, barnacled rock,
  big waves), the **mountain shelf** (open sky for flyers, gusts, rockfall) and the **ruined temple** (pillars that
  topple, vines, moss).
- **/simulate [fights] [names]**: balance checks with no model at all. A dice-driven stand-in picks the actions; the
  real engine rolls everything else on copies of your rules and arena (your fight is untouched). It reports wins,
  fight length, pins, escapes and the worst single beat. `/simulate 50 Nocturne Ripples`.
- **Story blocks and samples for the new moments**: clashes, take-offs, dives, being carried, falling out of the air,
  guards, water in the mouth, constriction by how far gone she is, weather, and the stiff moment after an escape; wing,
  beak and talon moves. New sample sections (clash, dive, sputter, coil, escape aftermath) are shown when one of those
  happens.
- **Staying with the damage.** When a blow (or a squeeze) lands on someone already badly hurt (at 55% strength or
  less, or the part it hit now excruciating or worse), the beat may get an extra part from HER side that stays with
  what it did: nothing new happens; the hurt arriving and settling, what her body does on its own, her heavy breathing,
  the sounds she tries to hold in (and by the end can't), her thoughts, how she looks at her opponent now. Another
  extra part may come from the side of the one who did it, WATCHING: studying every twitch and flinch, the breath
  hitching, what she guards, what each sign tells her. The watcher comes for any attack on someone badly hurt, and
  also for holds, pins and grapples on the ground. Each part is labelled with whose side it is. `narration.dwell`
  (chance 0.6, 260 words), `narration.watch` (chance 0.5, 220 words), `narration.moment_cooldown_beats` (1: never two
  beats running). New story blocks for both (what the hurt does by body zone, sounds held in by how spent she is,
  ragged breathing, what the watcher sees, her thoughts) and two new sample sections ("dwell", "watch").
- **Blocks and redirects (rare).** Now and then the one attacked gets something in the way instead of dodging: she
  BLOCKS a close blow on a forearm, foreleg, wing, horn or coils (it lands there at ×0.45), or TURNS IT ASIDE (nothing
  lands, and the attacker is OFF BALANCE 🌀 for a beat: slower to dodge, weaker next blow); a beam or blast is very
  occasionally batted aside too. Only when she is on her feet, free and fresh enough; about one block a fight and a
  redirect every other fight. `moves.guard`.
- **Charges that miss.** A charge that is dodged or turned aside may carry the charger on into the scenery (or the
  ground): she hurts her own head, shoulders or chest, and may go down. More likely when she was aiming to drive her
  opponent into something. `moves.missed_charge`.
- **Recoil.** Reckless moves (Take Down, Double-Edge, Brave Bird, Flare Blitz, Wild Charge, Volt Tackle, Head Smash,
  Wave Crash, Submission) jar back into the user when they land: a small share of their power on her own front.
  `moves.recoil`.
- **More story blocks** across the thin categories: breathing by where it hurts, back and tail sensations, how pain
  travels, late-fight thoughts, struggling, landings, dodges, getting up, sputtering, clashes, guards, crashes.
- **Caught open.** A blow on someone who has no chance to roll with it, twist away or soften it lands harder (only the
  biggest one counts): helpless in the air ×1.3, fooled by a feint ×1.25, doubled over or off balance ×1.2, dazed or
  flinching ×1.15, lying on the ground ×1.1 for a single close blow and ×1.08 for each blow of a pummel (`down_pummel`; not in pins). It's in the move math line.
  `moves.vulnerable`.
- **Feints.** The director can mark a strike as a feint (`"feint": true`, or just tell it "she feints, then bites"). It
  costs a little energy. If the defender bites (likelier the more worn down she is, less likely each time she's seen
  that fighter feint), she can't dodge, clash or guard, and the blow lands on her caught open. `moves.feint`.
- **Juggles.** A strike that launches her as one link of a chain, followed by a strike on her as the next link: she is
  caught helpless in the air (×1.3, no dodge) and smashed back down for a hard landing. An uppercut to the jaw, then
  a tail slash across the stomach before she comes down.
- **What a hard hit does for a beat.** The wind knocked out of her 😮 (chest or belly: no breath back, weaker blows and
  escapes), dazed 💫 (head: slow to dodge, weaker), doubled over 🤕 (a blow on a part that was already devastated: guard
  down). `moves.jolts`.
- **Guarding a wound.** Below 60% strength, a fighter shields her worst part once it's excruciating: blows there land a
  little lighter, and what she leaves open a little harder: her other side for a left or right part, her back while
  she curls over her chest, belly or throat, her front while she shields her back. The director is told what is open.
  Not while she is held (nothing free to cover it with). `moves.guarding_wound`.
- **Last stand.** Once a fight, a fighter below 15% may put everything into one blow (×1.3), then has no energy at
  all. `moves.last_stand`.
- **Wet fur.** A soaked fighter slips holds and pins a little more easily, and a soaked fighter's own grips slide.
- **Callbacks.** The dwell part remembers the FIRST thing that ever hurt that part, if it was 3 or more beats ago: the
  old hurt and the new one meet, and she remembers it (`narration.dwell.callback_after`).
- **Fighter-specific story blocks.** A block can say `fighter: nocturne`: it is offered only for her, and preferred
  when it fits. Nocturne, Ripples, Seraphina and the new fighters each have their own way of watching, their own
  thoughts, the sounds they hold in, what their bodies do.
- **Visible wear.** The narrator is told how each fighter looks by now (grit ground into her coat from every landing,
  soaked or singed fur, the worst parts swollen and matted) so it stays the same from beat to beat.
- **Fading thoughts.** Below 20% strength, on some beats (40%), a fighter's italic thoughts come in fragments. Only the
  thoughts: the prose around them keeps its full detail. `narration.fading_thoughts`.
- **Camera.** Each part of a beat is told close (tight on bodies) or, about a third of the time, wide (both of them and
  the place). The dwell and watch parts are always close. `narration.camera`.
- **How each place sounds.** Every arena has `acoustics` in scenes.json (the cave hands a whimper back from the dark;
  the wind on the mountain shelf tears a cry away), used for the sounds fighters make and try to hold in.
- **Pummel frenzies (rare).** Now and then a pummel doesn't stop: blow after blow, mostly on the same spot or the one
  beside it, usually 6-10 blows, once in a while 15-20. About 1 pummel in 10 on someone lying on the ground, 1 in 12
  elsewhere. The per-beat health cap still keeps one beat's health loss in bounds; the parts take it all, which is
  what the reactions feed on. Ground pummels run as long as any other and land harder (×1.08 a blow, plus the softer
  parts she has turned up): about a third more damage than the same pummel in a grab. `grapple.frenzy`,
  `grapple.ground_end_mult`.
- **Payback.** Now and then the director gets the idea that a fighter with a wrecked part goes for the same place
  on the one who did it (`director.grudge_chance`).
- **Drag, then pin.** When someone is down and not pinned, now and then the director gets the idea to drag her into a
  wall or the water and pin her there on the next beat (wall choke, the dunk) (`director.drag_to_pin_chance`).
- **Fury after a long pin.** Breaking a pin held 3 beats or more may leave her FURIOUS 😤 for a beat: harder blows
  (`pin.second_wind`).
- **Wariness.** A move that left one of her parts excruciating makes her wary of it: she dodges it more, but jumps
  at a feint of it more (`learning.wary`).
- **Exhaustion mistakes.** A very tired fighter sometimes overcommits: the blow lands sloppy (×0.6) and she is off
  balance after it (`moves.exhaustion_mistakes`).
- **Held, can't cover up.** A fighter in someone's hold takes blows ×1.1 (`moves.vulnerable.held`), and can't
  guard a wound.
- **How they move now.** Every beat the narrator is told what each fighter's injuries do to how she moves (favouring
  a leg, an arm tucked in, a tail hanging low).
- **Arena memory.** What the fight breaks stays broken (a stalagmite driven through, a pillar that toppled), and the
  narrator is reminded every beat.
- **Injury report.** When the fight is won, the console shows what each fighter will feel when it's over, and the
  narrator gets it for the aftermath.
- **Balance and pins (corrected).** /simulate never rolled the per-beat pin openings, so in it every beat was an
  opening and pins were far too easy; my earlier balance numbers were measured on that. Fixed, and its stand-in now
  takes an opening the way the director does. Measured properly at your settings, Nocturne's ORIGINAL body (the +5 and
  +2 resistance I had added are taken back out) wins about 61% against Ripples. Pin openings are a little more frequent
  (director.pin_urge standing 0.06 -> 0.1, downed 0.3 -> 0.4): about 5 pins a fight, most fights 4 or more, and about 3
  to 4 escapes. Still all dice; nothing forces a number.
- **Devastating blows (rare).** Now and then a blow lands far harder than it should (×1.7-2.2) and the health cap is
  much looser for that one hit, so it can swing the fight. About 1.5% of landed attacks, more when there is a reason:
  she is caught open (in the air, off balance, fooled by a feint, down), or it lands on a part that is already
  excruciating or devastated (a weak point in a weak point). A hard landing on someone with several badly hurt parts
  can find every sore spot at once. Pummels never roll it (frenzies are their big moment). The narrator is told the
  reason, gets about 150 more words, and is given ways to sell it chosen for where she is in the fight (fresh, worn,
  spent) and how hurt the part ends up: the delay before it hurts, the silence, her body betraying her, the attacker
  feeling it go in, the stare between them, the place answering. Reactions stay true to size: fresh and with the part
  not ruined, it's a real, visible reaction (shock, a cry she can't stop, a stagger, a change in her), never a scream
  or a breakdown; worn, her hold on the pain slips; spent, the rawest. The aftermath part (dwell) always follows one.
  New story blocks for every combination, and two sample sections. `moves.devastating`.
- **Wraps: what's wrapped decides it.** Coils round her body (chest, belly, back) constrict, as before: blood held
  back, heart slowing (never stopping), energy draining, and they can put her out in a pin. Round her throat they
  squeeze her air and blood. Round ONE limb or a tail (Ripples' twin tails round a foreleg) they only BIND it 🪢: that
  limb numb and weak (×0.9 on her blows, dodges ×0.75), no energy drain, no heart slowing. Before, any wrap counted as
  a full-body coil.
- **Resistance as a gradient.** A part's damage and health multipliers now slide smoothly with its resistance instead
  of jumping at bracket edges (a part at 101 used to take less than half the damage of one at 99). Straight lines
  between anchor points in the middle of each bracket: 120+ resistance ×0.2 damage / ×0.7 health, 85 ×0.45 / ×1.0,
  60 ×0.8 / ×1.3, 40 ×1.3 / ×1.7, 15 and below ×1.8 / ×2.2. The brackets still give the icons, labels and the
  narrator's words. Same pace (about 51 beats against 53, about 5 pins a fight), and the worst single beat roughly halves
  (at most about 25% of full health against 45%). `resistance.smooth` (anchors editable; enabled false = the old
  thresholds). With the gradient, Nocturne's original body measured 50% against Ripples and +3 63% (600 fights at your
  settings), so her body parts are +2 over the original (about 60%). Ripples untouched.

## Build 112
- **An ending broken off on purpose is kept.** When the narrator ends on an unfinished thought ("Three strides. If
  her legs would only"), the program used to trim it, taking it for an answer cut off by the word limit. Now it
  asks Ollama why the answer ended: if the model stopped there by itself, the fragment stays and is closed with a
  dash ("…would only—"); if the word limit cut it, it is trimmed as before.
- **How much a body part matters to overall health** (`health.part_weights`, `/vital`). Until now an ear cost her
  MORE overall health than the chest: it is soft, so the same blow does several times the damage there, and every
  point of damage cost the same health wherever it was. Now the health a hit costs (and the per-beat drain from a
  badly hurt part) is multiplied by how vital the part is: throat 1.7, neck 1.6, chest 1.4, stomach and flanks
  1.3, head and ribs 1.2, back 1, shoulders 0.9, hips and thighs 0.8, upper limbs and jaw 0.7, muzzle 0.6, nose,
  cheeks, knees and lower forelegs 0.5, paws, feet and tails 0.4, fins 0.3, ears and horn 0.2. The part itself
  takes the same damage and hurts as much as before; only what it costs her overall changes. The same blow that
  cost 7 times as much health on an ear as on the chest now costs about the same.
  `/vital` lists every part's weight; `/vital ear 0.3` changes one (a word in the part's name, or a region);
  `/vital off` = every part counts the same, as before.
  In simulation at your settings fights are about as long as before and a little more even between the two.
- **Wear by the damage done** (`resistance.loss_per_damage`, `/wear`; 0 = off, the default). Resistance has always
  dropped by the blow's POWER only, however much damage it did. With `/wear 0.05` it also drops by 0.05 for every
  1% of damage the hit really does, so a part that is being taken apart softens faster.
- **If parts take too much damage and lose too little resistance**, that is mostly `/scale 5` with `/resscale 0.75`:
  damage is multiplied by 5, wear by 0.75. What 150 simulated fights give at the end of a fight (five worst parts
  of each fighter):

  | settings | beats | damage on them | resistance lost | parts devastated |
  |---|---|---|---|---|
  | `/scale 5` `/resscale 0.75` `/healthloss 0.2` (yours) | 33 | 458% | 26 points | 4.4 |
  | the same with `/wear 0.05` | 27 | 485% | 40 points | 4.2 |
  | `/scale 3.5` `/resscale 1.5` `/healthloss 0.3` | 28 | 337% | 44 points | 2.4 |
  | `/scale 3` `/resscale 2` `/healthloss 0.35` | 27 | 307% | 56 points | 2.2 |
  | `/scale 3` `/resscale 1.25` `/wear 0.06` `/healthloss 0.35` | 28 | 302% | 54 points | 2.1 |

  The fourth line is the one to try first: a third less damage on the parts, twice the wear, and fights a little
  shorter. (`/healthloss` goes up as `/scale` comes down so that fights do not get longer.)

## Build 111
Fixes from a live test fight on build 110 (Ripples against Nocturne, ten narrated beats, with a stand-in writing
as the narrator against the program's real prompts), and three things you asked for.

**What you asked for**
- **Sleeper holds are uncommon**: suggested for about 7 pins in 100 (`director.pin_shape_weights.sleeper`, now 1).
- **Pain pass-outs are a setting**: `pin.fade.pain_out_share` (0.22). With a grip on her neck, that is how often
  the pain still gets there first (less when nothing under the press is badly hurt). With no grip on her neck it is
  always the pain. Together that comes to about 3 pass-outs in 10 by pain at your settings. Raise it for more,
  lower it for fewer; 0 = always the choke when there is one; 1 = always the pain.
- **Pummels are mostly one-sided, not always**: about 4 in 5 the held fighter only takes it (the attacker runs out
  of breath, or she twists enough to spoil the next blow). About 1 in 5 she ANSWERS: a short blow of her own lands
  on the one working on her, and that is what stops it (`grapple.pummel_answer_chance`; 0 = never).

**A real bug, and an old one**
- Any paragraph of the story that began with the word "Before" or "After" was silently deleted (a filter meant for
  stat lines such as "Before: 10% → After: 35%"). Fixed: only real stat lines go.

**Rewrites that were not needed** (each one is a model call you wait for). In the test fight the checks asked for
11 rewrites; 9 were false alarms. All nine are fixed, and that fight now replays with only the two real slips sent
back:
- "her tails wound tight" was read as a wound; "a wide red ache" as a colour-coded pain level.
- Sparks still on a fighter who is PARALYSED, and an earlier Thunderbolt remembered ("the place the lightning had
  left sore"), were flagged as electricity in a move that has none.
- "to lift off was to let go" (what she must NOT do) and "she let it go" (a bolt) were read as a grip released;
  "a stalagmite stood up out of the grey" as the pinned fighter standing up.
- "not yet" in plain narration counted as a repeated stock line (now only thoughts and speech count).
- A failed try at getting up was not credited to its fighter when the sentence also named the other one as its
  object ("…sank back onto her elbows, dragging Ripples a step with her"), and was then CUT from the story.
- A pass-out shown as "her eyes closed, and this time she did not go and fetch them back", "went soft", "did not
  stir" was not recognised; and a making-sure moment was added by the program although one was already written.

**Building blocks that did not fit the moment.** About a third of those offered were wrong in ways the program
can know. Now:
- what an opponent "can see before she strikes" uses the damage BEFORE this beat's first hit;
- thoughts and feelings know how far along the fight is, who is ahead, and (for a pinned fighter) how far gone
  she is: no "anger at being made to work this hard" on the first exchange, no plotting from a fighter who is
  nearly out;
- blocks for a pinned fighter know which way up she lies (no "the face above her" when she is face-down), and
  opening and ending images know standing from lying;
- a discharge such as Thunderbolt gets stagings for a discharge, not a horn strike; a pummel gets stagings for
  blows thrown at no distance, not a full wind-up;
- "how her own injury shows" knows striking from holding;
- in a beat where the PINNED fighter acts (she strikes from underneath, she breaks out), the first part's blocks
  are hers and the second part's are the pinner's (they were the other way round);
- a pin is as old as the pin, not as the grab that came before it;
- a fighter who goes out is no longer offered blocks for a serpent's coils;
- on the beat she goes under the blocks follow the cause (her air for a choke, the hurt part for pain);
- a block that is one of the reactions just used is not offered; the older random "THOUGHT ANGLES" line is gone
  while the blocks are on (the two used to disagree); no arena detail carries a unit of time; no block assumes a
  cold place.

**Smaller things**
- How the fight stands: "badly hurt, and she knows it" needs real strength lost (at a high damage scale parts are
  in pain long before that); early on it is "has had the worse of it so far".
- A fighter gets up against the thing she went down at (the stalagmite), not a random part of the arena.
- A grab kept by a fighter who has just been pinned is a plain grip from underneath, no longer "both on their
  feet"; after an escape the two are not told to "end apart" while one still has the other's arm in her teeth.
- A takedown fits the way she ends up lying (two new ones put her on her front), and gives way when the beat's own
  line already says how she is taken down.
- The beat's line is kept to 24 words (it was 15) and never ends on "and".
- `/pinsuccess` now also says why she goes out.

## Build 110
Mechanics. A pin is still the only way a fighter passes out and the only way a fight ends.

- **Pummels have no fixed length.** After the second blow every further one may be the last. The chance that it
  ends grows with each blow, and BOTH fighters' condition counts: a tired attacker cannot keep it up, a fresh
  defender spoils it sooner. Two fresh fighters average about 4 blows (the old limit); a fresh attacker on a spent
  defender about 5 to 6; a spent attacker on a fresh one about 3. It ends because she twists enough in the grip to
  spoil the next one, or because the attacker has to breathe, and the story is told which. A distant limit of 10
  remains (`grapple.pummel_hard_cap`; 0 = none). `grapple.pummel_max 4` brings the old limit back. Your own
  `/move ... 6` still throws exactly six.
- **Chains can run past three links.** Before the third link and each later one the engine rolls whether the chain
  ends there: 8% before link 3 between two fresh fighters, rising to about 40% before link 6; twice that with a
  tired attacker, about half against a spent defender. It ends with her dodging that link (and perhaps countering)
  or, when she cannot dodge where she is, with the attacker having nothing left to follow with. A distant limit of
  6 links (`director.chain.hard_cap`; 0 = none). Only a chain may run past three actions in a beat, and a long one
  gets 70 more words per extra link.
- **A charge may not stop at what it breaks.** If the first thing she is driven into breaks, the charge can carry
  on THROUGH it into the next thing in the arena, and the next: each a little less hard, three at most
  (`moves.charge`: `carry_on_chance`, `carry_on_power`, `max_obstacles`). It is rare: a strong charger, a long
  run, and something that breaks.
- **Takedowns vary and often hurt.** A standing fighter is taken down into a pin in one of eight ways (tackle, a
  hooked leg, a sweep, over a hip, a shoulder driven into her middle, dragged down, spun down, walked backward off
  her feet). Four times in ten the landing itself hurts: two parts on the side she lands on take a solid blow from
  the ground before the pin closes (`pin.takedown`; `hard_landing_chance 0` = never).
- **Two more pin shapes**: a sleeper hold from behind (uncommon since build 111), and (rarely) a choke with her jammed
  against something in the arena: she is on the ground at the foot of it, her head and shoulders against it, with
  nowhere to push back to, and it is a little harder to break out of (`pin.against_escape_mult`).
- **Why she goes out.** A fighter held to the end goes out from one of two things, and the story and the stat
  block say which: the CHOKE (a grip on her neck or throat) or the PAIN (the worst-hurt part under the press). How
  often the pain wins when there is a choke on is a setting since build 111 (`pin.fade.pain_out_share`).
  When the part under the press is in agony, each beat takes her under up to 15% faster (`pin.fade.pain_mult`).
- **Targets vary.** With no `/focus` set, a blow aimed at a region the attacker has just been hitting is moved,
  about a third of the time, to a part she has left alone (the less hurt, the likelier), so Slash also lands on the
  back, head, neck, sides and stomach; and the director is reminded now and then what has not been touched
  (`director.target_variety`; 0 = off). With `/focus` set, the focus decides, as before: it already picks freely
  among the parts of the zones you named.
- Every new roll, set to 0, leaves the fight's dice exactly as they were in build 109.
- Balance (300 simulated fights at your settings): 30 beats a fight against 32 before; who wins is unchanged
  within the noise.

## Build 109
The program now leads the narrator much further: what to build each part of a beat out of, where the fight stands
as a story, and what the story has been overusing. None of it decides anything; the dice still do.

- **Story building blocks** (`story_blocks.txt`, about 1,050 of them): reactions by the size of the blow, what a hurt
  feels like by how bad it is and where it is, how a hurt spreads from one part to the next, breath, what an opponent
  can see of an injury (healthy, hurt, on the ground), ways to stage a move, thoughts, feelings, how an injury shows
  when she moves, takedowns, what a pin is like for the one holding it and the one under it (and what it costs both,
  changing as the pin goes on), landings, dodges, the aftermath. Before each part of a beat the program offers the
  ones that FIT the fight as it stands, preferring the ones offered least and never one offered in the last 8
  beats. What has been offered is remembered between fights (`blocks_memory.json`).
  The file is plain text: add a line under a heading and it is in the pool the next beat. `/blocks` shows the
  counts; `/blocks off`, `/blocks 6` (how many per part), `/blocks reset`.
- **The blocks come as a plan**: numbered steps, in an order that changes from beat to beat, with an image to OPEN
  the beat on and one to END it on. They are colour for the events, never new events, and the checks that guard
  the numbers are unchanged.
- **The fight so far**: before each beat the narrator is told how far along the fight is, how each fighter is doing
  ("has had much the better of it and is barely marked", "is well behind and badly hurt, and she knows it"), who has
  been pressing, how it sits with her (confident, wary, worried, shaken, desperate, relieved to be out of a pin…),
  and how much THIS beat matters. In a few hundred simulated fights at your settings: about 1 beat in 10 is a
  turning point (a fighter pinned for the first time, a pin broken after it had begun to tell, the pressing
  changing hands), 1 in 5 holds a big move, 1 in 10 is the tense end of a pin, and nearly half are ordinary
  exchanges, told in full detail but without borrowed drama. A turning point and the beat that ends the fight get
  1.3 times the words (`narration.turning_point_length`); no beat ever gets fewer.
- The **director** is told how the fight stands too, so what a fighter tries fits how she is doing
  (`director.story_state`).
- **A glimpse of the place**: one detail of the arena that the story has not used lately, as background. Each
  arena in `scenes.json` has a `details` list; add your own.
- **One memory**: when a part that an earlier blow hurt is hurt again, the narrator is pointed at that earlier blow,
  once per part in a long while.
- **Words leaned on**: describing words the last few beats used five times or more are named, so the narrator
  reaches for others.
- **More sample passages** (32, up from 19), and the passage shown for each kind of moment takes turns.
- All of these can be switched off in `rules.json` under `narration` (`story_state`, `blocks`, `arena_detail`,
  `callback_memory`, `leaned_words`).

## Build 108
How long each beat takes, so two models can be compared.

- After every beat one line says how long it took, how many model calls it needed, how fast the model wrote and
  read (as Ollama reports it), any time spent loading models, and what had to be written again:
  `⏱ This beat took 1 min 42 s: 6 model calls, writing 38 tokens/s, reading the notes 2000 tokens/s · written
  again: 1 paragraph, 1 second draft · narrator: ...`
- `/timing` shows the averages so far by narrator model: time per beat, calls per beat, writing speed, and
  paragraphs, whole parts, second drafts and top-ups written again per beat. To compare two models, play some
  beats on each (`/model narrator <name>`) and then type `/timing`. `/timing off` hides the line (saved);
  `/timing clear` starts the count again.

## Build 107
Better narration: a new style sample that shows the narrator the kind of passage it is about to write.

- **A style sample in sections (`style_sample_scenes.txt`, now the default).** The narrator imitates the sample
  more than any instruction. The old sample was one passage, shown the same way before every part of every beat.
  The new one has 19 passages, each showing ONE kind of moment: the opening; a strike from the attacker's side
  and from the side of the one who is hit; a chain; a part crossing its breaking point; a grab and a stream held
  inside it; a pummel; a throw and the tumble after it; a get-up; a dodge; a pin going on, held, fought and
  escaped; passing out with the pinner making sure; the aftermath. Before each part the program shows the passage
  that fits (and a second one if it also fits and there is room; `style_sample_chars` in all, as before). The
  passages come from the test fight of builds 105 and 106, so nothing in them contradicts the rules: no
  flotation sac, no pin clock, no numbness, nobody who may not be in the fight. The old sample had all four.
  Edit the file freely or add sections; its first lines explain the format.
- **Your earlier samples are untouched.** `/sample` lists every `style_sample*.txt` in the folder and marks the
  one in use; `/sample style_sample.txt` (or `/sample 1`, `/sample intense`) switches, and is saved. A plain
  sample works exactly as before.
- **Copied lines are cut.** A sentence the narrator lifts word for word from the sample (five words or more) is
  taken out, and the narrator is told the passage is from a different fight: its manner, none of its events.
  `narration` → `sample_copy_check` false turns it off.
- **More reactions, and stronger ones for the worst hits.** The impact examples the narrator is offered now
  include a mouth wide open in a silent scream with the eyes squeezed shut, a shriek that breaks off into a
  wheeze, the back arching off the blow, every limb going rigid, a keening whine with tears starting, and more
  for lighter hits too. The tracker that tells it which reactions the last beats used knows the new ones.
- **Craft rules.** With `/numb off` the rules still taught "past pain into numb, wrong quiet" two lines above
  the rule that forbids numbness; they no longer do. New: no refrains (two paragraphs ending on the same line,
  "The pin held." ... "And the pin held.") and no strings of one-word sentences ("Firm. Unbreakable."); and
  proportion (a light hit gets a wince, only the worst gets a cry and a long passage). The examples no longer
  quote a move that may never have happened in your fight.
- **`/model`** shows which Ollama model narrates and which directs; `/model narrator <name>` switches the
  narrator for this session, so you can compare models inside one fight. To keep it, start with
  `--narrator-model <name>`.
- **Models that think before they answer** (Gemma 4, Qwen 3 and others) spent the story's word budget on
  thinking and could come back with half an answer. The first time a model is seen thinking, the program asks
  again with thinking off and keeps it off for the session. Cydonia is not affected.

**Trying a bigger narrator.** Not tested here. One that fits a 16 GB card with the overflow in system memory is
Gemma 4 31B (about 19 GB): `ollama pull gemma4:31b`, then `/model narrator gemma4:31b` (Cydonia stays the
director). Expect it to be several times slower, because part of it runs on the CPU. Compare a few beats of the
same fight, then `/model narrator hf.co/TheDrummer/Cydonia-24B-v4.3-GGUF:Q4_K_M` to go back. A different model can
also do only the second reading (`/reader model gemma4:31b`), so the reader does not share the narrator's blind
spots; Ollama then swaps the two models in and out each beat, which is slow.

## Build 106
The test fight, carried on to its end. The same stand-in fight as build 105 was picked up from the pin and played
for 8 more beats (same seed, same settings, a stand-in writing the director's and narrator's answers on the real
engine and checks): Ripples kicks free and gets up on her second try; her three-move chain is dodged at the first
move; Nocturne answers with a chain in which the director asked for Night Slash twice running; a second pin, typed
as `/pin`, with `/pinclock 80`; a pin beat with Ripples nearly out; the beat she passes out, with Nocturne holding
on a moment to make sure; and the aftermath. Nothing new to learn or type. What it found:

- **A dodged attack could be told as a hit and nothing caught it.** On a beat where the only attack misses, "The
  rush struck Nocturne in the chest and drove her back a step" went straight into the story. A blow shown landing
  on a named fighter whom nothing touches this beat is now sent back and taken out.
- **A dodge could go untold.** Part 1 of a two-part beat stops "at contact". When the attack is dodged there is no
  contact, and part 2 was told "the attack has ALREADY been shown above, miss and all" even when part 1 had stopped
  a stride short. Part 2 is now told to narrate the dodge unless part 1 really did.
- **A chain with one refused move lost every move after it.** The director asked for Night Slash, Night Slash,
  Bite. The second Night Slash is refused (the same move a third time running), and the whole rest of the chain was
  dropped: the stat block read "Chain, link 1 of 1 — nothing left to follow it with" and the narrator was told she
  "strings 1 attacks together". Now only the refused move is left out, the Bite follows as link 2 of 2, and the stat
  block says which move was left out and why. A "chain" with one move left is shown as a plain attack.
- **Beats where nobody attacks had the wrong two parts.** The split "her side up to the instant each hit connects /
  the other's side from contact" was used on three kinds of beat that have no hit to stop at. Each now has its own:
  - the beat a pin is ESCAPED: the pin as it stands, from the pinner's side; then the escape, the blow that frees
    her, and the get-up tries;
  - the beat she PASSES OUT: the pin as it stands; then her last moments, the pinner making sure, and letting go;
  - the AFTERMATH: the winner in the quiet after; then the fallen and the place (it was "the actions from the
    attackers' bodies", then "the attack has already been shown").
- **Notes on the beat she passes out contradicted themselves.** They said she ends the beat "nearly out", told the
  narrator to show her "gathering strength, plotting", and asked for a long lingering moment on a squeeze, all on
  the beat she faints. They now say she is out cold by the end and has nothing left to try with, and there is no
  lingering on that beat. The posture line left the fainting fighter off; she is on it. A try to break free by a
  fighter who is nearly gone is described as a slow, late try. After the pin, her position no longer reads "on top
  of Ripples".
- **"She" again.** "Nothing lay on Ripples now. She threw her right arm over the ledge" gave the get-up to
  Nocturne (and reported it as not finished); "Her own breath... The Absol's, big and rough, above." handed the
  next "she" to Nocturne, so "Her eyes were closed" was read as Nocturne's and the faint as never shown. A sentence
  that names one fighter and has no "she" in it now hands the story to her; a name that only owns something
  ("The Absol's") hands over nothing.
- **False alarms removed** (each is still caught when it is real; the test puts the real thing into the same
  prose): "Two strides. One." cut as a pin count on a beat with no pin; "a drop fell into the channel" sent back
  as Nocturne falling; "the knee buckled a half-inch and caught" sent back as a fall (the notes themselves suggest
  a limb buckling); "Nocturne let go of the foot" (last beat's bite) read as the new pin's grip on the throat
  coming off; "the cut thigh" under the pinner's paw read as a wound on the pinner; "the faint push of her throat"
  read as someone fainting. "closed her teeth on that foot" was counted as landing on BOTH feet when both were hit
  that beat; it now counts for the one the bite was aimed at.
- **Stat block.** A throw out of a grab is headed "no dodging it" (it said the dodge was halved).

Seen and left as it is: after a pin with no clock the banner still reads "Ripples faints after
20 seconds pinned by Nocturne": that is the stat block's count for you, not something the story is told.

## Build 105
Fixes from a full test fight. Build 104 was played for 8 beats with a stand-in writing both models' answers (the
real engine, dice, notes and checks; your settings: `/scale 5`, `/numb off`, `/resscale 0.75`, `/healthloss 0.2`,
`/focus core head legs`, `/focus strength 0.8`; the sleek Ripples; the sea cave). It covered a held Dark Pulse that
broke a stalagmite, a three-link chain, a grab with Water Gun held at point-blank, a pummel, a throw with a
tumble, a pin going on, and a pin beat with a partial break. Nothing new to learn or type. What it found:

- **A blow could go untold and nothing noticed.** In a two-part beat, part 1 is told to stop at contact. If it
  stopped there but had named the parts it was aiming at ("pointed at the middle of the Buizel's chest"), part 2
  was told "every hit has ALREADY been shown landing above", so the impact, the breaking stalagmite and the fall
  could be skipped, and the check for missing hits was satisfied by the same mention. A part now counts as told
  only when a sentence shows the blow LANDING on it (the impact and the part in one clause, not "aimed at",
  "pointed at", "toward"). The same goes for the told-twice check, which took the aiming for a first landing.
- **"She" in the second half of a beat belonged to the wrong fighter.** Each part is written from one fighter's
  side, but the checks carried "she" over from the end of the part before, and a name that was only an object
  ("as the Buizel swallowed", "the Absol's breathing") took the story over. A correct get-up was reported as
  unfinished and rewritten; "Her sickle tail stood out stiff" in Nocturne's own part was sent back as Ripples
  having no sickle tail. The checks now know whose side each part is told from, and inside a part "she" changes
  hands only when the other fighter becomes the SUBJECT of a sentence.
- **False alarms that forced rewrites, all removed:** "pale where it had broken" (a stalagmite) read as her head
  broken; "coils" of twin tails wound round a leg read as another species' anatomy; "a whine she strangled
  halfway" read as counting a pin's seconds; "shoved off the stone with her shoulder blade" read as an escape;
  "her breath cut off" and "blood beat in her face" read as wounds; "She opened her mouth and let it go" (a Water
  Gun, while her TAILS held the grip) read as the grip coming off; "closed her teeth in the scruff, not to bite"
  read as remembering the move Bite. Each of these is still caught when it is real: the test puts a slipped
  grip, fins on Nocturne, a remembered Bite, an invented cut, counted seconds, an escape and pain in an unhit part
  into the same prose and every one is sent back.
- **Notes to the narrator.** After a held stream it now gets where each part ENDS after all the pulses, not only
  the first impact. A beat with a grab in it no longer says "nobody is still latched on afterward", and the grab's
  squeeze is listed again. One breaking point per part, at the level it ends on. The beat a pin goes on gets its
  own second part (the pinned fighter's side, under it). Pin notes had a stray "{a}" and "is still has plenty of
  fight in her"; both fixed.
- **Stat block.** A chain link thrown inside a grab says "at point-blank in the grab: no dodging it" (it said the
  dodge was halved).
- **`/grapple` on a fighter who is lying down** now turns her so the gripped part can be reached, like `/hold`
  with a named part (it could leave a grip on a part that was against the ground). A grab only locks two
  fighters who are both on their feet; on a downed fighter it is an ordinary grip until she is up.

Seen in that fight and left as it is, because it follows from the settings: at `/scale 5` a "light" improvised
cuff is described as a tremendous blow, and three super-effective Brick Breaks in a grab took an unhurt jaw
straight to devastated. If pummels feel too strong at that scale, lower `grapple` → `pummel_power` in rules.json
(0.6 now) or set `pummel_max` (0 = no fixed length since build 110; 4 was the old limit). Pressure from a pin or hold that carries a part across a pain level gets no
breaking-point note; only blows do.

## Build 104
Grapples, chains and tumbles, and big moments that come due.

- **Grapple (`grapple`, `/grapple`).** One fighter seizes another and keeps hold of her, both on their feet: a
  paw locked on an arm, jaws in the scruff, tails round a wrist. The grab itself squeezes only lightly. What it
  does is keep her at point-blank. While it holds:
  - neither of the two can dodge the other;
  - the one holding can throw the same close move again and again, a **pummel**: (since build 110 with no fixed
    length, see Build 110; before that) up to 4 blows in a beat, each
    at 60% of one full blow, each after the first costing 3 more energy (three Night Slashes in a grab do 1.8
    times the damage of one);
  - a stream or beam can be held on her at no distance (no scenery needed), by either of them;
  - a throw or a slam out of the grab can't be slipped;
  - the held fighter can hit back just as surely, and rolls to wrench free every beat (the usual hold-break
    roll times 1.6: fresh against fresh about 29% a beat instead of 18%).
  The director's grab can be slipped like any attack; your own always takes hold.
  `/grapple Nocturne Ripples "Left Upper Arm=her jaws"`, then `/move Nocturne Ripples "Night Slash" "Chest" 3`.
- **Chains.** Two or three attacks in one beat by one fighter on one opponent are a chain (a grab may open it; a
  throw or a slam may close it). A link that lands halves her chance to dodge the next; a link she dodges ends
  the chain and the rest never happens; a link the attacker has no breath for ends it too. The narrator is told
  it is one flowing sequence, link by link. Your own: join commands with `+`.
- **Tumbles.** A fighter who is thrown or launched (not slammed, not dragged) tumbles on across the ground 30%
  of the time: a light scrape on 2-3 more parts, and half of those times she fetches up against something in the
  arena (a solid knock; water, snow or sand is a light one; a hazard does what it does, so a tumble into the
  plunge pool soaks her). A fighter who tumbles doesn't roll through to her feet. In your own commands, end the
  list with `; tumble`. `/tumble 0.5`, `/tumble off`.
- **Big moments, a little more often, and never too long without one.** The director is now pointed at one of
  five kinds on one roll: a held stream into the scenery 10%, a charge into the scenery 9%, a throw or slam 6%,
  a grapple 5%, a chain 5% of open beats (35% together; it was 23% for the first three). It may still decline.
  And when a fight has gone 10 beats without any big moment, one is suggested for certain, and firmly.
  Simulated with a stand-in director that takes up 40% to 70% of what it is offered: 4.5 to 6.1 big moments in a
  55-beat fight at the default scale (two or more in 98% of fights), and 2.6 to 3.6 in a 36-beat fight at
  `/scale 5` `/healthloss 0.2` (two or more in 80% to 93%). That is about one beat in ten: ordinary attacks are
  still most of the fight. Nocturne won 55% to 61% of those fights (60% before). `/bigmoments` shows the five
  chances and this fight's count; `/bigmoments more | less | off`, `/bigmoments due 8`, `/bigmoments chain 0.08`.
- **Two accuracy gaps closed on the way.** A fighter who ends the beat on the ground and has no get-up this beat
  could be written back onto her feet ("She got up at once", "Ripples sprang back up") and nothing caught it;
  that is now sent back and cut. And a blow driven into a named fighter nothing hits this beat ("drove her paw
  into the Absol's ribs") is caught even when the other fighter was hit in the same region.

## Build 103
A Ripples with no flotation sac.

- **The sleek variant (the default from this build).** Ripples now comes in two versions, both in
  `fighters.json` under her entry: `original` (as she was) and `sleek`, a river-bred Buizel with no flotation sac
  and no collar. `/variant` lists them; `/variant Ripples original` goes back, `/variant Ripples sleek` returns.
  Before the first beat the change is immediate; in the middle of a fight it waits for the next one. The choice
  is saved (`variants` in rules.json), and a saved fight loads with whichever Ripples it was saved with.
- **Body.** The Flotation Sac part is gone. In its place she has a Throat (63), next to her Neck, as Nocturne
  does. A command or a director choice aimed at "Flotation Sac" lands on her neck.
- **Tells.** Breath no longer shows in a sac. It shows in her ribs and her bare throat (quick and shallow when
  the air is knocked out, a ragged gulp as it comes back, her throat working as she swallows); her forearm fins
  flare when she braces and clamp flat to her arms when she is hurt; she tucks her chin and hunches her
  shoulders to cover her throat; the fur on the back of her neck stands up. The tails, ears, cheek marks,
  webbed paws and her voice are as before.
- **The story can't give her one.** With nobody in the fight who has a sac, "flotation sac", "sac" and "collar"
  are treated like scales on fur: the sentence is asked for again and cut if it comes back. The narrator's
  standing rules no longer suggest a sac as something to be clever with, and the style samples are read with
  their sac passages retold (the escape by venting the sac becomes an escape by whipping water up with her
  tails; the same rhythm). The sample files themselves are unchanged, and with the original Ripples nothing
  changes at all.
- **Balance.** A bare throat is a real weak point: blows that jar into her neck area and chokes on it hurt
  more than they did through the sac. Untuned, Nocturne won 67% of 400 simulated fights instead of 60%. The
  sleek Ripples has 1700 health instead of 1600 to make up for it: 60% again, 55 beats a fight as before.
- **Also fixed.** "NO antennae, no horn" in a description used to count as that fighter having antennae, so
  antennae and hooves could turn up in a two-fighter story unchecked; what a description rules out no longer
  counts. "Her forearm fins flared wide" is no longer read as pain flaring in a part nothing hit.

## Build 102
The three slips left open after build 101, the pin beat that repeated itself, and two requests.

- **Why "Something broke." got through.** The narrator sometimes puts a word in italics inside a sentence
  ("Something *broke*.", "a tremendous *CRACK*"). On screen the marks become real italics, so the log shows
  nothing, but every check was reading the text with the marks still in it and no longer recognised the words.
  Marks round a word or two inside a sentence are now taken off before anything is checked. A whole thought in
  italics (*Not yet.*) keeps them.
- **Where it came from.** The note for a breaking point asked the narrator for "the instant something gives".
  It now asks for the instant the pain becomes too much, and says that nothing breaks, snaps or gives way.
- **More ways of saying a bone gave** are caught: "the muzzle gave way", "something giving way beneath the
  surface", "something in her upper lip buckled", "an audible snap", "her jaw cracked sideways". A leg giving
  way under her is still fine.
- **Counts.** The engine now counts, per fighter, how often she has been thrown, slammed, dragged, charged into
  something, knocked down and pinned (saved with the fight, undone with a beat you take back). "Had just been
  thrown—twice—" when it was once loses the count and keeps the sentence; a count of something that never
  happened at all loses the sentence. The count is read generously ("thrown" counts slams too).
- **The wrong fighter's body by "her".** "Her flotation sac deflated" in a stretch that has only named Nocturne
  for the last three paragraphs is cut. Right after Ripples is named, the same words stay.
- **Pin beats.** A pin beat written in two parts used to give both parts the same job, so the second retold the
  first. Part one is now the pin itself, each place pressed told once; part two is the pinned fighter's side:
  her attempt and how it fails (or what the pin does to her when she makes none), told not to tell the
  pressing again. The third and later sentences that tell the same jaws on the same neck or the same paws on
  the same hips are sent back to be written again (never cut). "Her right hip bore the worst of it" when the
  other hip is far worse hurt is caught. A refrain that says again what a line above said ("The pin held.
  Firm. Unbreakable." after "The pin held firm.") is told once, and so is a sentence that opens like one above
  and says the same ("Then the blast struck her muzzle…" / "Then the blast slammed into her muzzle.").
  Under a pin, "she couldn't move" is no longer cut as a fighter going limp.
- **"Finish her"** is fine: the author's instructions now say that "finish her", "finish it" and "end this"
  mean winning, not killing, and "finish it" and "end this" are off the list of stock phrases.
- **Making sure (`/makesure`, on by default).** When the pinned fighter passes out, the pinner keeps her grip
  and her weight on for a moment or two longer to be sure it isn't a trick, and only then lets go. Story only:
  it adds no damage. If the passage has her let go at once, the moment is put in before the release.
  `/makesure off` goes back to easing off at once (`pin.make_sure` in rules.json).

## Build 101
Arenas to choose from, and fixes for what the build 100 logs showed.

**Arenas (`scenes.json`, a new file)**
- At the start of a run you are shown ten arenas and asked which one (a number, a name, `r` for random, or
  Enter to stay where you were). `/scene` lists them and switches; `/scene <a sentence>` makes an arena of
  your own from a description. `--scene 3` on the command line skips the question, and
  `/set scene.ask_at_start false` turns it off. The choice is remembered, and a `/newfight` stays in it.
- The ten: the flooded sea cave (as before), the waterfall gorge, the abandoned power plant, the caldera vents,
  the frozen lake, the forest clearing in a storm, the wreck on the reef, the ruins in the sandstorm, the
  crystal mine, and the clock tower works.
- **Hazards.** Each arena has six to eight tracked features. When a fighter lands on one, or is thrown,
  dragged, charged or pressed into it, it does what it is: steam pipes and lava crust burn, live cables
  paralyze, thin ice and deep water soak and chill, toadstool spores and sulfur poison, the great bell
  confuses, brambles and cactus stun for a beat. Soft things (deep water, snow, a sand pit) make any landing
  on them light. Each says how easily it breaks under a charge or a held stream, and whether a fighter can
  end slumped sitting against it. The director is given every hazard by name with what it does; the narrator
  is told when one bites. `/hazards` lists them for the arena you are in.
- **The place acts by itself.** Now and then (5% of beats, never within 4 beats of the last, never on a beat
  with a pin or a hold in it, not in the first two beats) the arena does something: a stalactite falls, a wave
  sweeps the deck, a steam joint bursts, the pendulum comes through, lightning strikes close. It is a light or
  solid hit, or a status, on one fighter or on everyone, and it knocks nobody down. In 300 simulated fights in
  the sea cave it happened about once a fight and cost about 11 health points each time; balance and fight
  length did not move. `/hazards off` stops it, `/hazards chance 0.1` changes how often, and
  `/hazard <event> [fighter]` makes one happen at the end of the next beat. The arena has its own dice, so
  turning events on or off does not change how a fight's other rolls fall.
- The notes to both models now use the arena's own words (its ground, its props, its sounds), and the
  director's examples are drawn from the arena you are in, so a power plant is never offered a stalactite.
- "The deep channel wall" is a wall. A landing was being soaked by the word "channel" in a surface's name; a
  surface now counts as water only when the water is the thing she lands in ("the edge of the pool" is not).
- Add your own arena by copying one in `scenes.json`; the comment at the top explains each field.

**Accuracy (from logs c930c2fe, 50ab5da3, 2873819f, 6b15c6a8, 75ef5faf)**
- **The same blow told twice.** A hit that lands once and is landed again several paragraphs later is caught,
  and the "linger on one blow" note now says to tell it once and add no movement the beat doesn't list.
- **Get-up tries.** A get-up on the second or third try has to show the earlier tries failing; a passage that
  has her simply stand is sent back. "The Absol's hackles lay flat again" no longer counts as her lying down
  again (it was adding a second get-up paragraph).
- **Repeats inside a beat.** Short lines used again as they stand ("The pin held. Firm. Unbreakable." three
  times) are told once, and a species name and a fighter's name count as the same ("The Buizel's jaw clenched
  tight." / "Ripples' jaw clenched tight.").
- **A move remembered on the wrong fighter** ("where the earlier Ice Fang had bitten", said of the fighter who
  used it) is caught; the same memory on the fighter it did hit is left alone.
- **"Pinned" with no pin**, the whole body **going limp or unable to move** while she still has most of her
  strength, a part **breaking** above zero health ("her nose broke further"), a part **cracking** that nothing
  hit that beat, **pain in a part that has never been hit** ("her jaw—hurting now" when it was the muzzle), a
  **blow that isn't listed** ("drove her hind paws into Ripples' belly"), and **tails shown spinning** while
  they are coiled round a throat are each caught. Figures of speech are left alone ("pinned by pain", ears
  pinned flat, a tail cracking like a whip).
- **The notes' own words** copied into the story ("rattled and a half-second behind", "this beat") are removed,
  and a reaction left as a stage direction between dashes ("slammed into the wall—grunt—and...") is taken out
  of its sentence.
- **Tone.** "pulped", "torn edges", "her muzzle was gone", "tearing through the sac's surface" and "teeth met
  bone" are now past the limit.
- **Stat block.** A label that names a place the attack did not land loses it ("Raking claw swipe at her right
  flank" on a Left Hip hit becomes "Raking claw swipe"; `/focus` had moved the target). A pin struggle is no
  longer worded as a dodge.
- A thought's lead-in left hanging by a cut ("...and thought one cold, hard thing:") goes with it.
- The check notes name the new findings (same blow told twice, get-up tries skipped, wrong move remembered...).

## Build 100
More ways for every outcome to play out, picked by the engine so the story varies and still matches the numbers.
- **The idea.** The dice still decide WHAT happens. For most outcomes the engine now also picks HOW, from several
  ways that are all true to the result, and tells the narrator "this time: ...". Where a way changes anything
  real (sitting instead of lying, a looser grip), the engine tracks it. `/variety` lists every set with its
  mix and changes a weight (`/variety dodge duck 0`); they are also under `variety` in rules.json.
- **After a charge into the scenery** (was: crumples, or staggers off it):
  - keeps her feet four ways: staggers clear; sags upright against it and pushes off; a knee touches down and
    she shoves back up; rebounds off it and stumbles forward past the attacker;
  - goes down four ways: on her side, face-down, face-up, or slid down it to SITTING with her back against it.
- **Thrown, launched or knocked down** (was: always flat on the ground):
  - thrown into a wall, boulder, stalagmite or pillar, she ends slumped sitting against it 35% of the time;
  - a plain knockdown sits her down hard on her haunches 15% of the time;
  - a thrown or launched fighter can roll through the landing and come up on her feet: 20% at full strength,
    about 9% at half, about 2% when nearly spent. She still takes every impact. Never on your own commands.
- **Holds** (was: holds, or breaks). A near miss on the break-free roll now loosens the grip: it stays on and
  presses at three quarters of its strength from then on. A wider miss is a visible struggle that changes
  nothing. In a fresh choke on a fresh fighter, one beat: holds firm 63%, fought but holds 18%, broken 11%,
  loosened 8%. A break is told one of four ways (wrenched, pried open, slipped out as it shifts, shoved off).
- **Getting up.** A failed get-up gets her as far as sitting 40% of the time. Failed tries differ (a limb gives
  out, a slip on wet stone, dizziness, no air), and so does the final rise.
- **Pins.** What she tries differs beat to beat (buck, bridge, twist, wrench a limb, kick, slide out). When
  she breaks out, the pinner is thrown down beside her 25% of the time instead of keeping her feet (never on
  `/pinescape`).
- **Dodges** are told five ways (sidestep, duck, spring back, turn it aside, twist out of its line).
- **Being handled.** When the director rolls, lifts, throws or drags a fighter who is on the ground, she can
  fight it off: 25% at full strength, 12% at half, 4% when nearly spent. Your own commands always work.
- **No cooldown** on throws, slams and drags (`director.manhandle_cooldown` is 0; set it to 3 for build 99's).
- **Room for the narrator.** Its rules now say what is fixed (who acts, the move, the parts hit, hit or miss,
  grips and pins at the end of the beat, who ends up, down, sitting or out) and what is its own (the approach,
  the angle, what a grab catches, footwork, how a body travels, the arena, sounds, looks, thoughts). A fighter who
  ends on her feet may stumble, be driven back, catch herself on a wall, or touch a knee down for an instant.
  The checks were brought in line: "her knees buckled, but she caught herself", "she almost went down", and
  "the jaws slackened for an instant, then clamped down again" are no longer cut, and "cut nothing but air" is
  no longer read as a wound. The second reading is told the same.
- **New check.** A passage has to leave a downed fighter sitting or lying as the engine says (the last thing it
  says about her decides).
- **Brutality.** Any attack may be told as brutally as a throat bite and no more: narrator rule, director rule,
  and a line in `story_prompt.txt`. Past that ceiling (a joint popped out, anything torn) is still removed.
- Fixed: a landing that ended with her sitting against a wall was knocked flat again by its own impact.
- Balance over 600 simulated fights is unchanged within noise (Nocturne 58%, 54 beats a fight).

## Build 99
One fighter moving another: by your command, and by the fighters themselves now and then.
- **Commands, named for what they do.** Name just the fighter being moved and the other one does it; with three
  or more in the fight, name who does it first (`/situp Nocturne Ripples`). Add your own wording in quotes
  (`/rollover Ripples "with a hooked forepaw under her ribs"`) and the narrator is given it.
  - On a fighter who is on the ground, no damage: `/rollover`, `/onback`, `/onfront`, `/onside`, `/situp`,
    `/pickup`, `/standup`. The old `/roll <att> <def> over|back|front|side|sit|up|stand` still works.
  - **Sitting up is new.** She is hauled upright but still on the ground, with her chest, belly and throat open
    in front and her back and neck behind. The next blow that lands knocks her flat again (onto her back if it
    came from the front); a hold put on her keeps her sitting (a choke from behind); a pin bears her flat. She
    can't be sat up, picked up or stood up while pinned. `/down Ripples sit` and `/face Ripples sit` work too.
  - **Standing her up** is dragging her onto her feet; the narrator is told she did not get up by herself.
  - Through the arena, with damage: `/throw`, `/slam`, `/drag`, each taking surfaces written like `/land`
    (`/throw Ripples "a stalagmite=Upper Back+Head:heavy; the stone floor:solid"`). A throw hurls her (a fighter
    lying down is hauled up first); a slam lifts her and drives her down at the thrower's feet (heavy unless you
    say otherwise); a drag hauls her across the ground where she lies and into or against what you name, she stays
    down, and a hold already on her stays on. With no parts named, the first stretch of ground scrapes the side
    she is lying on. The damage is credited to the fighter who did it, and it costs her energy.
  - As a setup, join one to an attack with `+`: `/situp Ripples + /move Nocturne Ripples "Night Slash" "Chest"`.
- **The fighters do it themselves.** `throw`, `slam` and `drag` are actions the director can pick like a strike
  or a pin, and `sit her up` and `stand her up` join the ways it can move a downed opponent. A standing target
  can slip the grab (the usual dodge roll); a fighter on the ground can't. Kept occasional three ways: when
  someone is down, the director is pointed at moving her on 12% of beats (was 15%, with more to choose from now:
  roll, sit up, stand up, throw, slam, drag, about evenly); a throw or slam of a standing fighter is suggested on
  5% of beats, sharing the one big-moment roll with the held stream and the charge; and a fighter who has just
  thrown, slammed or dragged someone can't do another for 3 beats. All optional to the director. rules.json:
  `director.reposition_chance`, `director.grapple_chance`, `director.manhandle_cooldown`, and the energy costs
  under `energy.costs` (throw 12, slam 12, drag 8).
- **The narration checks know about it.** A beat that should show a throw, slam, drag, sit-up or stand-up and
  doesn't is written again. Jaws on the scruff or a leg while carrying or dragging her are a grip, not an
  invented bite (this was cutting the pick-up sentence in earlier builds too). And on a beat where someone is
  thrown, a sentence like "Her back struck the rock" belongs to the fighter who landed, even when the last name
  before it was the thrower's (it was being read as the thrower falling, and cut).
- When a move-her command is joined to an attack, the empty "Breather" line between them is gone.

## Build 98
- **Pins have no fixed length, and the story has no clock.** The 60-second rule gave the narrator a finish line
  to count toward ("Fifty-five now. Fifty."), and nobody in the cave could know when the other would pass out.
  Now each beat of a pin (still 10 seconds of real time) brings the pinned fighter closer to going under by a
  varying amount, and she passes out when it reaches 100%. In simulation, a pin she can't break lasts 6 beats most
  often (43%), 5 beats 9% of the time, 7 beats 35%, 8 or more 12%; with her health below zero it is 5 or 6 beats
  eight times in ten. A beat where she breaks loose for a moment counts for less than half, so near-escapes
  stretch a pin; a double pin goes faster; it never takes fewer than 3 beats.
  - The narrator is told there is no clock and is given how far gone she is in words (weakening, fading, nearly
    out), never a number. Any counted time in a pin beat is removed: "Thirty seconds.", "held for forty
    seconds", "Twenty more to go.", "halfway", "a full minute". "A few seconds" is fine.
  - The stat block shows it instead of a clock: "Pin: Nocturne on Ripples, beat 3 of it (30 s held) · going
    under 40% → 53.8% (+13.8 this beat; she passes out at 100%)".
  - Escape odds fade with how far gone she is, as they used to fade with the clock.
  - `/pinfade` explains it and lists running pins. `/pinfade 8` makes pins usually last 8 beats; `/pinfade 6 0.3`
    makes them more alike (0.55 is the default spread); `/pinfade off` brings back the fixed clock with the
    seconds marked in the story. `/pinclock 80` sets how far gone she is; `/extendpin 30` gives her 30 points back.
  - `story_prompt.txt`: the PINS section no longer says "60 seconds", "the clock" or "mark the passing seconds".
- **Moving a downed opponent.** Rolling her over or hauling her up was always the director's choice, but nothing
  ever suggested it and it almost never happened. Each beat an opponent is on the ground there is now a 15%
  chance the director is pointed at it (roll her to reach her other side, or pick her up to slam or throw her).
  It stays optional. `director.reposition_chance` in rules.json; 0 turns the suggestion off.
- **Neck and Throat** are two parts on purpose. The Throat is the soft front of the neck (windpipe; resistance
  55%), and can only be reached when she is on her back or on her feet. The Neck is the rest of it, back and
  sides (75%), and can be pressed whichever way she lies. Ripples has only a Neck (her flotation sac sits where a
  throat would); Seraphina has a Throat and an Upper and Lower Neck.

## Build 97
The last beat of a fight (pin held to 60 seconds, the loser faints) came out at 142 of about 500 words and never
showed the faint.
- **The faint was being cut by the checks.** Once a fighter is out she was no longer counted among the fighters a
  sentence could be about, so "the Buizel went limp" was read as the WINNER collapsing, flagged as an invented
  collapse or fall, rewritten, and then cut. Fighters who are out are now named like anyone else, so her going
  limp is hers. (Replayed on the old build: the same draft loses its faint; on this one it keeps it.)
- **The faint is always told.** A last beat that doesn't show her passing out is written again ("faint not
  shown"), and if it still isn't there after the cuts, a closing passage is written for it: her struggle giving
  out, her body going limp, her eyes closing, the winner easing off. If the model can't, plain sentences say it.
- **A wrong clock mark costs one sentence, not the rest of the beat.** "Forty seconds." in a beat that covers
  50 to 60 used to end the passage right there, and everything after it was thrown away, which is the main reason
  pin beats came out short. Now only the sentence with the wrong second goes. Bare counting below the window
  ("One. Two.") is left alone: it is usually tries or breaths.

## Build 96
From the rest of the same build 93 run (beats 9 to 13). The numbers were right on every beat; these are story slips.
- **A grip is told on the part it is really on.** The pin had Nocturne's jaws on Ripples' left paw and a forepaw
  across her throat; two beats later the story had "her jaw locked tight around the Buizel's throat". For grips
  made with jaws, tails or coils, a sentence that puts them on a different kind of body part (and doesn't name
  the right one) is written again, with the right part named. A paw told as a wrist or foreleg is fine.
- **Letting go of nothing.** "Nocturne's jaw released and she stepped back" on a beat where she was holding
  nothing is written again. Jaws opening to snarl and tails uncoiling on their own are left alone.
- **More notes leaking into the prose** are sent back: "Seconds 10 to 20. Halfway.", "past excruciating into
  something else", "sore squeezes", "the contact point". The narrator's notes no longer say "point of contact".
- **Leftovers of a cut.** "Nocturne thought, her red eyes narrowing…" after its thought was removed, and "The
  number echoed in her mind…" after its count was removed, now go with the line they hung on.
- The pin block's facing note no longer says the same thing twice.

## Build 95
From a build 93 run at `/scale 5`: a tail choke stayed on while the fighter holding it took a Thunderbolt that cost
her half her health, the story said the tails let go, and the program had them on for another beat.
- **A hard hit can shake a hold loose.** A fighter who is holding someone and is hit rolls to keep her grip:
  the chance to lose it is the share of her full health that one attack cost × 2.5, never above 95% (10% of her
  health at once = 25%, 20% = 50%). Hits that cost under 3% don't roll, so at the default damage scale grips are
  rarely shaken; at `/scale 5` that Thunderbolt (51% of her health) tears the choke loose 95 times in 100, and a
  single Slash almost never does. The roll is on the 🎲 line, the break gets a 💥 line under the attack that
  caused it, and the narrator shows the grip coming off as the blow lands. Pins are not shaken this way (a pin
  ends when its pinner is knocked down or thrown). `/holdshake <number>` changes the 2.5; `/holdshake 0` = never.
- **When the hold does stay on, the story can't let it go.** "Her tails finally released Nocturne's neck" got
  past the check because it named the fighter being held, not the one holding. Caught now, with "went slack",
  "slid off", "fell away", "peeled away".
- **A collapse into the pool is a fall.** "She collapsed backward into the pool with a splash" passed because a
  badly hurt fighter is allowed to sag. Going down INTO or ONTO something is a fall whatever shape she is in, and
  is written again when nothing knocked her down.
- **A move that missed isn't remembered as a hit.** "Still shaking off the Night Slash's sting" came a beat after
  Night Slash was dodged. The narrator is now told which attacks missed and what the last attack that landed on
  each fighter was, and a sentence that speaks of a dodged move as a blow is written again.
- **A pin's own contacts can't open mid-pin.** "Her jaw releasing Ripples' left paw" on a beat where the pin
  held was not checked, because pins had their own, narrower check. A pin's contacts now count as grips that stay
  on (except on a beat where the pinned fighter breaks loose for a moment).
- **The second look is off by default.** The second reading found a real mistake (a claw rake on Ripples' hip
  that never happened: it was her own rake on Nocturne from the beat before), the program's gate agreed, and
  the "is this fine?" second ask then talked it out of it. A finding only ever causes a paragraph to be written
  again, so the gate alone now decides. `/reader confirm on` brings the second ask back.
- A sentence that reuses a seven-word run from earlier in the same beat is told once ("...swelled again, once,
  twice, each breath shallow and burning through her chest").
- Pain levels used as labels ("from sore to very painful", "the very painful one", "the contact point") and a
  strength word standing alone ("Tremendous.") are written again.
- **"Do a sustained attack"** in a direction is honoured: if the director picks a stream or beam (any move marked
  sustainable) and forgets to hold it, it is held for 3 pulses.

## Build 94
- **Holds have no time limit, and no guaranteed length either.** A plain hold (jaws on a throat, tails round a
  neck, coils) never had a limit, but nothing rolled for the held fighter to get out of one either: how long it
  lasted was whatever the director felt like (in the last run, one bite stayed on for eleven beats). Now, every
  beat after the one it starts in, once its pressure has landed, the held fighter gets one roll to wrench free:
  - 12% fresh against fresh; more when she is in better shape than the one holding her, when the grip is light,
    or when the limb that grips is hurt (tails at 150% damage: twice as easy to break);
  - less when she is worn down or the grip is crushing, and a quarter of that once her health is below zero;
  - +1.5% for every beat the grip has already been on, never above 60%; none while she is asleep or frozen.
  In simulation a tail choke between two fresh fighters lasts 5 beats at the median, ends on its second beat about
  one time in six, and is still on at beat 10 about one time in six. On a fighter at a quarter of her health,
  one in three is still on at beat 10. (Those figures are for a hold nothing else interrupts: a knockdown or a
  throw still tears a grip loose, and the holder can still let go.)
- The roll is on the 🎲 line every beat ("Nocturne breaking Ripples' hold on her 14%, rolled 62 → it holds"), a
  break gets its own 💥 line, and the narrator shows it as the last thing in the beat.
- The director is told holds have no time limit and sees the odds beside each hold. It can no longer end a hold
  on behalf of the fighter being held (that becomes "straining against the hold"; the roll decides); the holder
  can still let go by choice.
- `/holdbreak` shows the odds for the holds that are on. `/holdbreak <base> [per beat] [max]` changes them:
  `/holdbreak 0.06 0.01` for long holds, `/holdbreak 0 0` for no roll at all.
- Other limits, unchanged: a pin is 60 seconds (`/pinlength`); a held stream is at most 4 pulses in one beat
  (`/set moves.sustain.max_pulses 6` raises it; each pulse costs energy).

## Build 93
From a run with the second reading on (build 91, `/scale 5`).

**Holds and pins**
- **A hold hurts from the beat it starts.** Jaws clamped on a throat used to do nothing until the next beat. The
  clamp itself now lands as one beat of pressure ("the grip closing: beat 1 of the hold"). `/holdstart <mult>`
  sets how much (1 = a full beat, 0 = the old way). A pin's presses still start on the pin's next beat;
  `/pinstart <mult>` changes that.
- **A pin never runs its clock on the beat it starts.** When a pin took over a bite the pinner already had, the
  clock ran 0 → 10 and a struggle was rolled and punished in the same beat the pin began. The older grip keeps
  pressing that beat; the clock and the first struggle wait for the next one.
- **A grip already on stays what it is.** The same pin asked for "her horn" on a neck that was already in her
  jaws, and the bite silently became a horn. The director's beats now keep what is already there (your own
  commands can still change it), and the narrator is told.
- **"Clamping down harder" can't loosen a grip.** A bite that had tightened to 31 was "adjusted" to *crushing*
  (25) by a beat that meant to squeeze harder, shown as "loosens", and the story then let the bite go. The
  director's adjustments only lower a grip when the beat says easing.
- **Any limb can grip any part.** This was always possible; the director is now told so and pointed at it:
  chokes with tails, a forearm, coils or a paw; jaws clamped on a paw, forearm or tail, in a pin or in open
  fighting. None of it needs a move from the list.
- **Pin shapes.** With every pin opening the director is handed one way to build the pin, never the same twice
  running: jaws on the throat; jaws pinning a paw while a forepaw bars the throat; a tail choke; a twisted arm;
  tangled legs; and, rarely, a leg hooked and hauled up off the ground. `/pinshape` shows how often each is
  suggested; `/pinshape lifted_leg 0` turns one off.

**Getting up**
- Knockdowns already end in a get-up most of the time (about two in three at `/scale 5` in simulation, three in
  four at the default scale), usually on the very next beat. Two things hid it:
  - **A get-up the story never told.** The 🧗 line said "gets up on the third try" and the passage ended with
    her on her back. A passage that doesn't end with her on her feet now gets the get-up written as a closing
    paragraph. "Stood over her", "tried to stand" and a rise she then loses don't count as standing.
  - **Getting up with a grip on her.** The narrator is told the grip stays on while she rises.

**The story**
- **A grip can't be let go by the story.** "Her bite came free", "released her jaws", "jaws now empty" on a
  beat where the hold is still on are written again. In the beats after a grip really ends, "still bound by
  those twin tails" is written again too.
- **A cut can't hand a sentence to the wrong fighter.** When a sentence naming Ripples was cut, the next one
  ("Her devastated chest hit the boulder") read as Nocturne's. The name is put back.
- **A bite is checked per fighter.** A beat with Nocturne's bite in it no longer lets Ripples bite too.
- **Paragraph repair can't duplicate.** A rewritten paragraph that re-told its neighbours left the same
  sentences twice. Copied sentences are dropped from the rewrite, near-repeats inside one beat are told once,
  and a cry left with one quote mark gets the other.
- "Fifty more remained" counts as time left on the clock and is cut like the other countdowns.

**The second reading**
- In that run it was wrong far more often than right: it judged the start of a beat by how the beat ends, and
  called a twitching paw a posture. It is now given a timeline (how each fighter starts and ends the beat, and
  which grips stay on), and each finding has to pass three checks before a paragraph is rewritten:
  1. it states an opposite fact, not a remark ("not mentioned in the facts", "should be noted" are set aside);
  2. the program's own look at the quoted sentence agrees it could be that kind of mistake (`reader_gate`);
  3. asked a second time, the other way round, the model still calls it a contradiction (`/reader confirm`).
  Everything set aside is shown in the log with the reason. Two new kinds: a grip let go, and a wrong time on
  the pin clock.

**The numbers on screen**
- `/layout clear` is the new default: every hit as three labelled rows (damage, resistance, health, each with
  before → after and the math that gives it), grouped under what caused it (the charge, the slam, pulse 2...),
  with space between blocks, one chance roll per line, and no line wider than about 100 characters, so nothing
  wraps. `/layout tight` and `/layout classic` are still there.
- The "director was pointed at: pin opportunity" line names the pinner first.

## Build 92
- **The second reading has to be specific.** Its first finding in a real run read "The facts list a specific
  sequence of hits and impacts..." about a sentence that was probably fine: a remark, not a contradiction. Each
  finding must now name its kind (wrong posture, attack or wound not listed, wrong body part or side, wrong
  attacker or weapon, injury worse than listed, someone who isn't there), state the opposite fact itself, and say
  whether the reader is sure. Only "sure" findings send a paragraph back; the unsure ones are shown in the log
  ("second reading wasn't sure about (left as written): ...") and nothing is done with them.
- The log shows each finding in full (it was cut at 90 characters), with its kind in front.

## Build 91
- **A failed escape told as an escape.** On a pin beat where the engine rolled "fails; Ripples punishes it" (pin
  clock 40 → 50), the story had Nocturne buck Ripples off, lunge, and claw her arm, and Ripples dive into the pool.
  Nothing checked for that: the escape check only ran on beats where an escape DID happen. Now, on every beat
  where the pin is still on at the end:
  - the narrator is told so in plain words ("THE PIN STILL HOLDS when this beat ends ... nothing follows the
    struggle: no escape, no chase, no new attack");
  - a draft that has the pinned fighter get loose, get up, or attack from her feet, or the pinner thrown off,
    backing away, or letting go, is written again (it counts as getting the events wrong);
  - if it is still there after that, the part ends just before the invented escape, because everything after it
    is invented too, and the beat is topped up from there.
  "Tried to roll free", "couldn't get to her feet", "almost lost her grip" are left alone.
- `/reader cpu on`: when `/reader model <name>` names a different model for the second reading, run that model
  on the CPU in system memory, so the narrator stays loaded on the graphics card instead of being swapped out for
  every reading. Untested here; it passes Ollama's `num_gpu: 0` for those calls.

## Build 90
More checking for fewer mistakes, at the cost of some time per beat, and without cutting more.

- **A mistake is fixed in its paragraph, not by rewriting the part.** Until now any problem sent the whole part
  back to be rewritten; the log shows what that did ("the rewrite broke something the draft had right: keeping
  the draft"), after which the wrong sentences were simply cut. Now the program writes ONLY the paragraph that
  holds the mistake again, with the mistake named and the paragraphs around it shown, up to twice; every other
  paragraph stays word for word. A new paragraph is accepted only if the program finds nothing wrong with it.
  Only if both tries fail is the wrong sentence cut, as before. So less is cut than before, not more.
  A whole new draft is still written when something is MISSING (a hit never shown, the escape, the get-up).
  `/repair off` goes back to the old way.
- **A second reading.** After each part, the model is given the beat's facts (what happens, who is up and who is
  down, everyone's condition) and its own passage with numbered paragraphs, and asked to list contradictions:
  someone on the ground who should be standing, an attack that isn't listed, the wrong side, an injury far worse
  than listed. This is what catches wordings no pattern was written for ("lay soaked and trembling", "pulled
  herself upright"). What it finds is written again like any other paragraph and checked by the program; nothing
  is ever cut on its word alone, and a "quote" that isn't really in the passage is ignored. One short extra call
  per part. The log shows what it found: `[second reading found: "..." → the facts say ...]`.
  `/reader off` turns it off; `/reader model <name>` has a different Ollama model do the reading.
  This is the part of the build that most needs your logs: how often it is right can only be seen with the real
  model.
- **Pins matter more below zero health.** Under zero, the escape and break-loose chances halve again for every 5
  points (percent of her own full health) she is under. Getting out of a whole 60-second pin, pinner at half
  strength: 71% at 25% health, 39% at zero (both unchanged), then 19% at 5% under zero (was 33%), 11% at 9% under
  (was 29%), 3% at 20% under (was 19%), 0.3% at 34% under (was 13%).
  `pin.struggle.escape_halves_every_below_zero` in rules.json (1000 = off).
- **From the log (the Aqua Jet on a downed Nocturne, the Hydro Pump to the head, the Crunch and pin):**
  - Nocturne got up at the end of one beat and the story never showed it, so the next beat told her as still
    lying down ("lay soaked and trembling", "pulled herself upright"). The get-up check only looked for anyone
    standing; Ripples standing satisfied it. It now has to be the fighter who got up. Those wordings of lying
    down are caught, and "The pool lay flat" no longer counts as a fighter lying down.
  - The director added pauses to an attack beat and used them to narrate ("collapsed leg gives out again"), which
    told a failed get-up nobody rolled. Pauses tacked onto a beat with a real action are dropped, and a pause
    can't describe a fall or a get-up.
  - "No pressure had built yet, no seconds ticked by" and "Not even excruciating anymore" (the instructions'
    wording and a pain level as a word) are cut.
- Balance is unchanged: Nocturne 57% (random moves) and 63% (type-smart) over 300 simulated fights; at
  `/scale 3` with `/resscale 0.75`, 57% over 200, about 31 beats a fight.

## Build 89
From the build 87 log (Tail Bind plus the held Hydro Pump, the two pins, the Aqua Jet from the floor).

- **A line of the instructions was printed in the story** ("POSTURE THIS BEAT (certain; the program tracks it):
  ..."). The narrator had copied it in. Lines that begin with the prompt's own headings are now removed.
- **No body charge from the ground.** Ripples used Aqua Jet the beat after failing to get up, so the story had her
  launch, tumble, stand, lie sprawled and get up, all in one beat. A running, full-body charge (any move marked
  `charge`) now needs the attacker on her feet and not pinned; the director is told to bite, kick, lash, or blast
  from the ground instead. Typed commands still can.
- **A blow filed as a hold lands as a blow.** "Forepaw slam to the head" was a `hold_start`: no damage that beat,
  and the story pressed a standing Ripples' head to the floor. A hold with no hold move whose label is a single
  blow (slam, punch, kick, swipe...) and nothing that grips now runs as the strike. Coils, bites that lock,
  presses and anything "around" or "against" something stay holds.
- The director is told that a limb at 150% damage or worse isn't a weapon (Nocturne slammed with the forepaw of
  her ruined leg).
- Broken-bone wording that slipped through is now caught: "felt the bone give way", "a snap she could hear", "the
  joint had given way", "a tremendous CRACK", "felt something shift".
- The pinner "tumbled to the right ... hit hard against a fallen boulder" after an escape counts as an invented
  fall (she keeps her feet).
- "Nocturne is no longer adrenaline" now reads "Nocturne's adrenaline surge is over". `/rescale` works as a
  spelling of `/resscale`.
- Balance over 300 simulated fights is unchanged (Nocturne 57%, or 63% with type-smart moves).

## Build 88
The stat display, redone to take less room without dropping anything. `/layout classic` brings the old one back;
`/layout tight` is the new default (saved like your other settings).

- **One row per body part.** The old Before / Calculations / After blocks named every part three times. Now each
  hit is one row: resistance before → after, damage before → after, the math, and the health it cost.

      ⚔️ Nocturne → Ripples: Slash across the shoulder
        Power: base 30 · Normal vs Water ×1 · targeted ×2 → 60 (res loss 15 = power × 0.25) · jarred Upper Back, Flotation Sac ×0.5 → 15 (res loss 3.75)
        Left Shoulder   🟦 103 → 🟩 88%       🟢 0 → 🟢 15%     60 × 0.20 × 1.25 = +15%     ❤️ -5.25 (×0.7)
        Upper Back      🟦 113 → 🟦 109.25%   🟢 0 → 🟢 3.75%   15 × 0.20 × 1.25 = +3.75%   ❤️ -1.31 (×0.7)
        Flotation Sac   🟦 148 → 🟦 144.25%   🟢 0 → 🟢 3.75%   15 × 0.20 × 1.25 = +3.75%   ❤️ -1.31 (×0.7)
        Σ +22.5% damage · ❤️ Ripples 1600% → 1592.12% (-7.88)

  Reading a row: part | resistance before → after | damage before → after | power × the resistance bracket's
  multiplier × the damage scale = damage dealt | health lost (× the part's health multiplier). The square in front
  of the "before" resistance is the bracket the multiplier comes from. This key is printed under the legend.
- **Rows say where they come from** when one attack has several sources: "the charge", "slam: a fallen boulder",
  "crush", "pulse 2", "pulse 2: a stalagmite". The long sentence explaining which lines were which is gone.
- **Pin and hold beats are shown in full.** The classic layout cut them to a one-line summary (damage only). In
  the tight layout every beat has its rows. A pin's pressure rows also say where the power comes from
  ("press 12 × 0.5 pin damage").
- **🎲 Rolls: every chance the dice decided that beat**, with the chance, the roll, and the outcome. New here (they
  were never shown before): the pin opening on each fighter, dodges that failed, statuses that didn't take, the
  scenery holding or breaking, whether a pinned fighter made an attempt at all, the counter after a dodge, the
  restrain chance of a pin technique. A roll under the chance succeeds. Escape rolls stay on the pin clock line,
  the get-up roll on its own line. This line is in the classic layout too.
- **💡 Director was pointed at:** which idea the program put in front of the director that beat (a pin opening, a
  charge or held stream, the initiative shifting, range variety), with the roll behind it on the 🎲 line.
- **Full body lists wrap.** The opening roster and `/status full` put several parts on a line: the three-fighter
  roster at start-up goes from about 90 lines to about 30.
- The same five beats (a Slash, a charge into the boulder, Dark Pulse, a pin starting, a pin beat) take 71 lines
  instead of 115, with the pin beat in full and the rolls added.
- The dice themselves are untouched: the same seed gives the same fight as build 87.

## Build 87
From the last build 82 log (the pins on Ripples) and your questions about it.

- **Pin damage is halved by default, and your command settings now survive a new build.**
  - `pin.damage_mult` ships at 0.5 (it was 1). It scales everything the pinner does to the fighter she is pinning:
    the pressure each beat, the punishment for a failed struggle, `/pinsuccess`, and now also any strike or
    technique the pinner lands on her while the pin runs. `/pinpower <number>` changes it as before.
  - In your beat (Ripples at 405 health, chest at 425% damage): a beat cost about 51 health, or about 80 when a
    failed struggle was punished (135 at worst). At 0.5 it is about 30, or 45 with a punishment (72 at worst).
    The big drops you saw were failed struggles being punished on top of the pressure. Yes, it feeds back into
    her escapes: the escape chance follows her strength, so heavy pin damage made each next try less likely.
  - Over 300 simulated fights the balance doesn't move: Nocturne 59% -> 58% (moves picked at random), 64% -> 63%
    (super-effective moves favoured); fights run about one beat longer.
  - **my_settings.json.** Anything you change with a command (`/pinpower`, `/numb`, `/scale`, `/words`, `/team`...)
    is still written to rules.json, and now also to my_settings.json next to it. A new build replaces rules.json
    but never contains my_settings.json, and that file is laid over rules.json at every start (the start-up text
    says how many values were applied). `/settings` lists them; `/settings forget` drops them. Settings made
    before this build were only in your old rules.json, so set those once more.
- **Get-up rolls are visible.** Every beat a downed fighter tries to rise, the line now shows the roll:
  "can't get up this beat (3 tries; down 1 beats) — get-up roll 0.12 (needs 0.7 / 0.45 / 0.2 to rise on try
  1 / 2 / 3)". On the beat she goes down there is no roll, and it says so ("stays down this beat: ... the first
  one is next beat"). These lines also appear on pin and hold beats, which used to hide them.
- **No invented get-up tries.** In the log Ripples "tried to push herself upright—and failed" on the beat she
  crumpled, when no roll had been made. The narrator is now told she doesn't try that beat; a draft that shows
  a try (made or failed) is rewritten, and the sentence is cut if it is still there.
- **A minor hurt told as a serious one.** "Crack. Something gave way... the right hip shifted wrong... a sound
  like splitting wood" for a hip at 3% -> 6%. A part that is only minor and took no strike that beat can no
  longer be the place something gives, cracks, twists, or makes her scream: rewrite, then cut (with a lone
  "Crack." in front of it). "Something gave", "shifted wrong", "a wet pop" now count as broken-bone wording.
- With the numb level off, "numb" and "past pain" are now checked (before, the narrator was only told).
- "Forty more." (the time left on a pin, as its own little sentence) is caught, and so are the instructions'
  own words turning up as prose ("The pin had only just begun", "an instant hit").
- A sentence naming both fighters no longer counts as an invented fall for the one who is really down.

## Build 86
From the rest of the build 82 log (the charge at attack 19, then Ripples' pin).

- **What happened.** Nocturne's Take Down drove Ripples into the boulder; Ripples kept her feet (a 25% roll). The
  very next beat the engine rolled a pin opening on Nocturne (6% per beat while she is strong), and Ripples, at
  55% strength and just crushed, took an 82%-strength Nocturne down into a pin. Legal under the old rules.
- **Reeling.** A fighter driven into the scenery by a charge is REELING for the next beat: she can strike, but
  can't start or join a pin (the director is told, and isn't pointed at a pin for her). It lasts exactly one
  beat, comes only from a charge, and never from damage or tiredness, so two worn-down fighters can always
  still pin each other. `moves.charge.reeling_beats` in rules.json (0 = off). In charge-heavy simulated fights
  every fight still ended in a win, at about the same length (39-40 beats against 44 with it off).
- **The short display also shows what else happened that beat:** who got up, who crumpled or is reeling, a status
  ending. Before, pin and hold beats showed only the damage line and the clock.
- **The pin clock inside sentences.** The escape at second 10 was told as "at fifteen seconds ... on her feet by
  thirty seconds". Clock marks outside the beat's window now trigger a rewrite, and what is left is taken out of
  its sentence without cutting the sentence ("Nocturne was on her feet, unsteady").
- **A badly hurt part called fine.** "Her right paw—still good, still strong" while it was at 201% (a left/right
  mix-up): rewrite, then cut.
- **Wrong weapon, horn.** Iron Tail told as a horn-first headbutt now triggers a rewrite, like the tail did for
  Night Slash.
- "Crashed forward onto her side" for a fighter the engine has on her feet counts as an invented fall.

## Build 85
- **A fighter who has just been charged into the scenery can't act in that same beat.** The charger's follow-up
  (a strike, or a pin when there is an opening) was meant to land before she falls, but nothing stopped the
  fighter who was crushed against the wall from answering in the same beat: with an opening on the charger she
  could even pin her from against the wall, which also skipped her crumple roll. Now the director's action for her
  is dropped (the charge stands), she can't be made to roll or lift anyone, and the director's instructions say so.
  Typed commands still can. The next beat is unchanged: if she kept her feet she may attack, and may pin if the
  engine rolls an opening; if she crumpled she can't pin a standing opponent.

## Build 84
From the build 82 log (three pieces).

- **A stream held on someone is the move, not a grip.** In the log the director filed "Hydro Pump stream, pin
  against stalagmite" as a `hold_start`. That made four weak grips called "the water blast" (power 13-14, no
  damage that beat, no Hydro Pump used up, no stalagmite damage), which then kept ticking for beats after the
  story had moved on. Now a hold or pin whose move is a stream or beam (any move marked `sustainable`), or whose
  label names one, runs as that move held for 3 pulses against the scenery it names. The director's instructions
  and the "big moment" hint say so too. Real grips (Tail Bind, a bite that stays locked, a headlock) and typed
  `/hold` commands are untouched.
- **`/auto 2 3 Nocturne Ripples` now does what it looks like.** `/auto` only ever took a number of beats, so that
  line ran `/auto 2` with all three fighters: this is where Seraphina came from. `/auto` with a second number or
  names is now read as `/autofight` (and says so). `/auto 2` on a fresh start runs the opening and then two beats
  (the opening used to count as one). A first `/autofight` with a different line-up is Fight 1, not Fight 2.
- **A pin starting is shown in the short number display.** Tail Bind did not turn into a pin: the next beat the
  director chose a pin (Nocturne was down), and the grips the pinner already has join it, by design. The short
  display used on pin and hold beats showed only the clock, so it looked like the hold became the pin. It now
  prints the pin block (contacts, clock start, and "Grips Ripples already had on her join the pin: ..."), and
  likewise a hold starting, a release, or a roll on those beats.
- **Loose lines left behind by cleanup.** When a sentence is cut, short follow-ups that leaned on it are cut with
  it ("But she couldn't. Not yet."), and a paragraph left as a dangling word ("The—") is dropped. A beat or part
  no longer opens by repeating the last line before it ("And then—", "The blade struck.") or with last beat's
  closing thoughts standing as loose lines ("Good." / "It held.").
- **New checks (rewrite first, then the sentence is cut if it's still there):**
  - a bite in a beat where no move uses teeth (the Slash that ended with jaws on the neck);
  - a part called useless or "the only one that still worked" below excruciating: until now this was only sent
    back for a rewrite and stayed if the rewrite kept it;
  - Ripples putting her weight on a paw (her paws are her hands; she is told so every beat as well);
  - features nobody in the fight has (scales, coils, antennae in a Nocturne-Ripples fight);
  - "Can't attack yet." as a game term.
  - Rewrite only: the strike landed with the tail when the move uses claws or horn (Night Slash in the log). The
    narrator is now told "Delivered with her CLAWS or her HORN: not a bite, not a tail strike" under the move.
  - "wasn't finished ... whipped again" counts as an extra swing, and an extra swing now counts as getting the
    events wrong (it gets the third rewrite). A pinner "flying backward into the pool" after an escape counts as
    an invented fall.
- A typed `/hold` or `/pin` by a fighter who is asleep or frozen wakes her (she can't be out cold and holding on
  at once; the random audit found this one). The director was already refused such a move.
- **Repeats across the whole fight.** A short sentence (4-10 words) already used word for word in this fight is
  cut the next time ("The cave held its breath.", "Her ears pinned flat against her skull."). Before, only the
  last three beats were checked. `narration.repeat_memory: false` in rules.json turns it off.

## Build 83
- **A fighter who isn't in the fight stays out of the story.** With `/autofight ... Ripples Nocturne` (or
  `/newfight`, or `--fighters`) the engine did leave Seraphina out, but the narrator could still write her in:
  her name was in an example in story_prompt.txt and in the style samples, and nothing told the narrator she
  wasn't there. Now:
  - the narrator is told every time who is NOT in this fight, by name and species;
  - a draft that mentions her (the opening included) is rewritten, and any sentence that still does is cut;
  - the example in story_prompt.txt no longer names a fighter, and the director's example lists two fighters and
    says only the listed ones exist. If you keep your own story_prompt.txt, the rule and the check still cover it.
- `/autofight 3 Ripples and Nocturne` and `/newfight Nocturne vs Ripples` now work: "and", "vs", "&" and commas
  between names are ignored.

## Build 82
- **Nocturne against Ripples: 61% to 65%.** In build 81 Nocturne won about 55% of simulated fights when moves were
  picked at random and about 70% when super-effective moves were favoured, because Thunderbolt (whole body,
  doubled against Water) was doing most of the work in the second case. Two small changes in fighters.json bring
  both into the low 60s (600 simulated fights each: 61% and 65%):
  - Nocturne's Thunderbolt: power 10 → 8 (still her strongest move against Ripples, three uses);
  - Ripples' body parts: +8 resistance over her original numbers instead of +10 (Chest 103, Shoulders 103...).
  Ripples keeps 1600 health and Hydro Pump. The note under Ripples in fighters.json lists how to go back.
  Simulated fights run about 42 to 48 beats at the default settings.

## Build 81
Built on build 80.
- **Charges that carry her into the scenery.** A charging move (Take Down, Aqua Jet, Dragon Rush, and 21 more in
  moves.json marked `"charge"`), or any improvised charge, can keep going after the hit: the attacker drives the
  target backward ("a few strides", "a dozen strides", "the whole way across": the further, the harder) and slams
  her into a boulder, a stalagmite, the wall. Her back takes the surface (three parts, environmental damage), and
  in the same instant the attacker's own body crushes the parts the charge struck, pressing her between the two.
  The surface may break under her (a heavier hit, and she goes down with it).
  - **She usually crumples afterwards, and you can hit her before she does.** After the slam she is left pressed
    against the surface until the end of the beat. A second action in the same beat (a strike, a bite, a pin)
    lands while she is still up against it, and she can't dodge it. At the end of the beat she crumples to the
    ground 60% of the time when fresh, about 78% at half strength, 95% near nothing; otherwise she staggers off
    it on her feet. The narrator is told which, and a text that has her slide down when she kept her feet is
    rewritten.
  - Nocturne gets **Take Down** and Seraphina **Dragon Rush**; Ripples' Aqua Jet is a charge already.
  - About one beat in twelve (when you just press Enter and no pin is running) the director is pointed at a charge;
    at most one "big moment" idea (held stream or charge) per beat. `rules.json -> director -> charge_chance`,
    and `moves -> charge` for the slam, the crush, the distances, and the crumple odds.
  - Typed: `/charge Nocturne Ripples "Take Down" "the cave wall"`. To hit her before she falls, join a second
    command with ` + ` so both happen in the same beat:
    `/charge Ripples Nocturne "Aqua Jet" "a fallen boulder" + /move Ripples Nocturne "Ice Fang" "Throat"`.
    (` + ` works for any attack commands, up to three in a beat; `&&` still means one beat each.)
  - Both fighters must be on their feet; a fighter on the ground or pinned can't be charged across the arena (it
    becomes an ordinary hit and the stat block says why).
- **`/focus injured`**: the attacker goes back to what is already hurt, the parts right around it, and, when one
  side of the body is badly hurt, that whole side. The worse a part is, the more often it is picked. It combines
  with zones (`/focus injured legs`) and works per fighter (`/focus Nocturne injured`). Until something is hurt
  it does nothing. `rules.json -> director -> injured_focus`.
- **Two can pin one.** While a pin is running, a second fighter can pile on (action "pin" on the same fighter, or
  your `/pin`): a double pin on the same clock, both pressing, and the pinned fighter's escape and break-loose
  chances are halved (`pin -> double_pin_escape_mult`). From full health she still gets out of a double pin about
  70% of the time, against 95% for a single one. If one pinner is knocked away or put out, the other carries on;
  an escape frees her from both, and the blow lands on one of them. The director is told when a second pinner
  could join (`director -> double_pin_chance`).
- **Sides.** Teams already existed in fighters.json; now you can set them while playing, and the engine refuses
  any attack between fighters on one side (your own commands still can).
  - `/team Nocturne Ripples as Shadows`: for good, in every fight (saved to rules.json). They win together.
    `/team Ripples solo`, `/team off`, `/team` to see.
  - `/ally Nocturne Ripples until Seraphina` or `/ally Nocturne Ripples 6`: a temporary alliance, told as a story
    beat. It ends when the named fighter is out or the beats run out, and always the moment nobody else is left
    to fight; then the two are opponents again and the fight goes on. `/ally off` ends it.
  - Only you make and end alliances; the director doesn't form them on its own.
- **`/more` (or just `+`): stay in the moment.** Instead of pressing Enter, type `+` and the narrator adds a few
  paragraphs on the stillness and what the last blows left behind, without the fight moving on: no new attack, no
  time on a pin clock, no get-up roll. Use it as often as you like; `/more 400` sets the length, and
  `/more "Ripples' shoulder, and Nocturne watching her"` says what to dwell on. `/more auto 1` adds one such
  passage after every attack beat on its own (in `/auto` and `/autofight` too). The text joins the last beat, and
  `/undo` takes it away. It is checked like any beat: a new wound or a fall in it is rewritten.

## Build 80
- **Held streams into the scenery.** Both fighters already had moves that can be held (Nocturne: Dark Pulse, Hydro
  Pump, Thunderbolt; Ripples: Water Gun, Water Pulse, Ice Beam), but the director almost never held one. Now:
  - Ripples has **Hydro Pump** too (power 40, 4 uses, like Nocturne's and Seraphina's), so she can blast Nocturne
    back into a boulder and hold her there.
  - About one beat in ten (when you just press Enter, and no pin is running or about to start), the director is
    pointed at a held stream: "Ripples HOLDS Hydro Pump on Nocturne: sustain 3, pinned against a fallen boulder,
    a stalagmite, or the cave wall". Every pulse hits again and also grinds her into it (environmental damage on
    her back, shoulders and hips), it may crack and give way under her (a heavier hit), and she ends up on the
    ground. A three-pulse Hydro Pump into a boulder costs Nocturne about 4-5% of her health, three times an
    ordinary hit. `rules.json -> director -> sustain_chance` (0.1; 0 = never suggested), and
    `moves -> sustain` for pulses, strength per pulse, energy per pulse, and how easily each kind of scenery
    breaks. Typed: `/sustain Ripples Nocturne "Hydro Pump" 3 "a fallen boulder"`.
- **Balance, again:** with Hydro Pump in hand Ripples' +10% attack power from build 79 made her too strong, so
  her other move powers are back to the originals. She keeps 1600 health and +10 resistance. Nocturne now wins
  about 56% of simulated fights with moves picked at random and about 67% when the director favours
  super-effective moves (400 fights each).
- **Fight length.** Simulated Nocturne-Ripples fights now run about 40 to 50 beats at the default settings. For
  about 35:

  | setting | beats (type-smart to random move choice) | what else it changes |
  |---|---|---|
  | defaults (`/scale 1.25`, `/healthloss 0.5`) | 40 to 51 | |
  | `/healthloss 0.8` | 31 to 39 | health drops faster; body parts wear at the same pace |
  | `/scale 1.75` | 32 to 41 | every hit also wrecks body parts faster |
  | `/scale 2` | 30 to 38 | |
  | `/scale 3` | 24 to 31 | |

  Fewer pin openings don't shorten fights (escaped pins are replaced by more attacks). The real director isn't
  the stand-in, so check `/results` after a few fights and nudge the number.

## Build 79
- **Ripples evened out against Nocturne** (fighters.json only; no rules changed). Nocturne was winning about 85%
  of simulated one-on-one fights; she now wins about 63% when moves are picked at random and about 69% when the
  director favours super-effective moves (500 simulated fights each). What changed for Ripples:
  - health 1400 → 1600;
  - every body part +10 resistance (Chest 95 → 105, Left Shoulder 95 → 105, Forearm Fins 60 → 70...);
  - attack powers +10%: Aqua Jet 30 → 33, Brick Break 35 → 38, Crunch 40 → 44, Ice Fang 30 → 33, Water Gun, Water
    Pulse and Swift 20 → 22, Ice Beam 30 → 33. Her holds are unchanged, and so is everything about Nocturne.
  - Why she was losing so badly: an ordinary Nocturne attack took about 2.0% of Ripples' health while an
    ordinary Ripples attack took about 1.3% of Nocturne's (Nocturne has more health and many parts above 100%
    resistance, which take less than half the damage), and each Thunderbolt took about 15%. Now the ordinary
    attacks are about even (1.3% against 1.4%) and Nocturne's edge is her Thunderbolt (about 10% a use, three
    uses) and her larger health pool. Whoever falls under half strength first gets pinned far more often, so
    a small edge per hit becomes a large edge in wins; that is why the numbers needed to be this close.
  - The old numbers are noted in fighters.json under Ripples (`_balance_note`) if you want them back.
  - For reference, with the same stand-in director Seraphina beats Nocturne about 72% of the time and Ripples
    about 69%. She wasn't changed.
  - Fights between the two now run longer: about 50 beats in the simulation instead of 40.

## Build 78
- **More escapes while she's healthy, a coin flip around half, likely to submit when badly hurt.** See "Escape
  odds follow her health" under Pins for the curve and the whole-pin numbers. Before, the chance halved for every
  25 points lost from full health, so a fighter at 75% already escaped only a third of her tries.
- **Pins can come at any point.** The old rules (on the ground first, three attacks since the last pin) are
  replaced by a rolled opening each beat: rare on a strong standing fighter, likelier after a knockdown, much
  likelier under half strength. A standing fighter is taken down into the pin. In 24 simulated fights with a
  stand-in director that pinned at every opening: about six pin attempts a fight; pins started above half
  strength were escaped 98% of the time, between 25% and 50% about 70%, under 25% about 35% (a hurt pinner makes
  escapes easier than the table above).
- **Several fights in one session:** `/newfight`, `/fighters`, `/autofight`, `/results`, and `--fighters` (see
  "Run it"). Choosing the fighters replaces `/eliminate Seraphina` at the start of every fight.
- Ctrl+C (the interrupt button) now stops a long run and returns to the prompt instead of ending the program.

## Build 77
From your build 75 log (Nocturne's four attacks, the knockdown, the throw into the boulder):
- A fighter who is out and never landed a blow stays out of the story. In beat 3 the model invented a history
  for Seraphina ("When Seraphina had hit her with that Thunderbolt", "the worst of the Milotic's Wrap earlier")
  and in beat 1 it checked on her breathing. Sentences that bring her up are now flagged, rewritten, and cut if
  they survive. A fighter who DID hurt someone before going out can still be remembered, and the beat she goes
  out on and the aftermath are not checked.
- Thought marks stay in pairs. Cutting one sentence out of a thought (a repeated line, a stray curse) left
  half-marked thoughts such as `Of course. She got me good.*` and `*Slow.`; these are re-paired at the end, so
  they print as italics again.
- "The next strike" no longer counts as a second swing (it set off a needless rewrite in beat 1).
- A drooping tail, flat ears, or a deflated flotation sac described as "limp" or "hanging" is a tell, not a
  disabled limb, so it no longer sets off "parts called useless too early". "Useless", "ruined", "wouldn't
  move" still do.
- Thrown or launched from the ground: in beat 4 Ripples was lying on her back when Iron Tail threw her into the
  boulder. That is allowed (a blow can hurl a lying fighter), but the narrator is now told she was on the ground
  when it hit, so she skids and tumbles across the floor rather than flying off her feet. The stat block says
  "thrown: ..., from the ground".
- A counter-hit after a dodge was recorded under the attacker's own move (Nocturne's foreleg "from Nocturne's
  Iron Tail"). It is now recorded as the dodger's counter, so the narrator's injury notes name the right cause.

## Build 76
- Real bold and italic on screen. The stat blocks mark headings with `**two asterisks**` and the story marks
  thoughts with `*one*`; Spyder's console doesn't understand those marks and printed them as-is. The program now
  turns them into the console's own bold and italic as it prints (Spyder, Jupyter, and ordinary terminals).
  - `/style` shows the setting and a sample line; `/style on | off | auto` changes it (auto, the default, is on
    in Spyder). Saved in `rules.json -> console -> styled_text`.
  - `/style color yellow` (or cyan, green, magenta, red, blue, white, none) also colours the bold parts, for a
    console or font that doesn't draw bold any heavier.
  - `/export`, saves, and what the models read keep the plain asterisks, so exported text still pastes into
    anything that understands Markdown.
  - A thought the model left unclosed (`*Can't move.` with no closing asterisk) stays as it is.

## Build 75
A full audit of everything the engine tracks about bodies: who is up, down, which way she lies, who is pinned,
who holds whom. A new checker throws random director beats and typed commands at the engine (three fighters,
about 14,000 accepted beats out of 42,000 tried) and after each one compares every piece of tracked state with
every other. On build 74 it found more than a dozen kinds of contradiction; on this build it finds none.
- Fixed (each was real on build 74):
  - A pinner who was knocked down, thrown, or launched kept her pin running. Now the pin breaks, and the stat
    block and the narrator are told.
  - A pinned fighter could be "knocked down", thrown, or launched (her position was re-rolled under the pin, so
    presses could end up on the side against the ground). Now she can't; a blow can only drive her into the floor.
  - A fighter already on the ground could be "knocked down" again: the narrator was told she fell a second time
    and her get-up count restarted.
  - A pinned fighter could attack or grab a third fighter, start a pin of her own, lift someone, throw her
    pinner off with a launching strike, or simply "release" the pin on herself, skipping the escape roll.
  - Pinning someone who was herself pinning a third fighter left both pins running.
  - A fighter on the ground could pick an opponent up.
  - A hold kept from before a fall could sit on the side now against the ground.
  - A sleeping fighter kept pinning and holding, stayed "standing", and rolled get-ups in her sleep.
  - A knocked-out fighter lost the way she was lying (the aftermath didn't know if she was face-down or on her
    back), and /quickpin left her "down" and pinned after she was out.
  - /getup and /fighter up on a pinned fighter stood her up with the pin still on her.
  - The director's positions sentence could contradict the engine ("standing by the pool" for a fighter who is
    down, "pinned under Nocturne" after an escape), and both models read it as fact. See "Positions" above.
  - Standing BESIDE the pool counted as soaked. Now only being in the water does.
  - Saves didn't keep the recent-move list or the last roll-over; undo didn't restore "just knocked down".
    Loading a save now also repairs any posture this build wouldn't allow.
- Breaking free of a pin now hurts the pinner: the blow that frees her lands somewhere a pinned fighter can
  reach (face, neck, chest, belly, forelimbs) at `pin.struggle.escape_severity` (default heavy, about the
  weight of a named move; a break-loose hit that doesn't free her stays solid). The stat block
  shows it under the pin clock line; `pin.struggle.escape_hit: false` turns it off. The narrator is told the
  pinner is knocked off but stays on her feet and the freed fighter is still on the ground unless she also gets
  up, and a text that puts her back under the pin after the escape is rewritten.
- The narrator is told, first thing every beat, each fighter's posture at the start and end ("Ripples: ON HER
  FEET all beat", "starts ON HER FEET; ends ON THE GROUND, face-down"), and that a standing fighter never lies
  down, is never under anyone, and never has to get up. In your build 73 log the model had Ripples lying on her
  side, pinned, and unable to stand through beats 2 to 4 while the engine had her on her feet; those sentences
  are now flagged as wrong posture or an invented pin, rewritten, and cut if they survive the rewrite.
- "The Buizel", "the Absol", "the Milotic" now count as the fighter's name when the checks decide who a sentence
  is about, so "the Buizel went down" is caught the same as "Ripples went down".
- When two drafts are compared on a big beat, the one that gets the events right now wins, even if it has more
  small wording slips (it used to count slips, so one invented fall could beat two repeated phrases).
- One strike told as several ("then she struck again", "this time she aimed lower", "the second hit") is now
  flagged and rewritten when the beat is a single blow whose force carries into the neighbouring parts.
- rules.json now ships with narration.context_window 12288 (what you've been setting by hand each session).
- The reaction half of a beat was asked to describe "any fall or landing", which invited falls that never
  happened. It now says: only if one is listed.
- Falls and blows landed inside a pin (the escape hit, a break-loose hit) are now in the "fight so far" list
  the narrator may refer back to.
- New: /posture. /face now also works on a knocked-out fighter, and moves a pin's presses when you turn her.
- Not tracked (so not checked): how far apart fighters are. Range is still the director's judgement from the
  positions line.

## Build 74
- Tougher body parts, faster health (so you no longer need a high /scale to make fights move):
  - damage_scale 2.5 → 1.25 (each hit does half the body-part damage), resistance wears at half the rate again (loss_per_power 0.5 → 0.25), and each point of body-part damage costs much more health (0.18 → 0.5, still ×0.7 to ×2.2 by how worn the part is).
  - One sturdy part hit over and over now goes sore → hurting → very painful → excruciating → excruciating → devastated across six strikes (it used to be hurting → excruciating → devastated in three, and numb by the sixth).
  - A full fight takes about the same number of hits (21 vs 23 in 150 simulated fights), but the worst part ends near 900% instead of 2,100%, and about 12 parts end up hurt instead of 20.
  - A 60-second pin costs about the same health as before with half the part damage.
  - New: /healthloss [n] changes how much health each point of part damage costs (higher = fights end sooner without wrecking parts faster). /scale still scales part damage. If you had /scale 5 or 7 saved, the zip's rules.json resets it to 1.25.
- Quieter fighters: at most one spoken line in a beat, none for the next two beats, and up to two italic thoughts per part; the narrator is told they're mostly silent and to carry feeling through body and breath. Extra lines are rewritten or removed (with their "she chittered" tags). /talk quiet | less | normal | free changes it (default: less). Single emphasised words like *snap* aren't counted as thoughts.
- When a text still gets the events wrong after its rewrite (an invented fall, a missing hit), it gets one more rewrite aimed only at that, and the best of the three is kept (narration.max_rewrites).
- More invented falls and holds are caught: "tried to push herself upright—and failed", "pinning her upper body against the shallow pool".
