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

**In a window, with pictures:** `python window.py` (in Spyder: `%runfile window.py`). It takes the same options as
`play.py`. On the left, each fighter's picture, with a line from every body part out to a label showing its damage
(the coloured fill) and resistance (the coloured frame); hurt parts glow on the picture, yellow to orange to red to
purple. Health, energy, statuses and posture sit underneath. On the right, the story and stat lines with the command
box. Scroll back through the story and the pictures show each fighter as she was in the beat you are reading (or
use the slider and arrows; "Follow the fight" jumps back to the latest beat). The official artwork is downloaded
once into `images/`; put your own picture there as `<fighter name>.png` (`Ripples.png`) or `<species>.png` to use
it instead. If a part's point sits in the wrong place, click its label and then click the picture where the part
is: it is kept in `images/anchors.json`. Absol and Buizel come with their points placed; others start from a guess.

**Saving a whole fight:** `/exportfight` writes the fight so far into the `exports` folder as a page you open in
your browser: every beat's story and stat lines next to each fighter as she stood after that beat (picture, glow,
health, energy, statuses, and every body part's damage and resistance), plus a `.json` file of the same data. A
finished fight is saved there by itself. `/exportfight all` saves every fight this session; `/exportfight myname`
picks the file name. The window has an Export button for it.

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

## Build 325
- **Fix: her breathing stopped showing in a hard stretch of the fight.** A fast, shallow breath (her ribs guarded
  past 150% damage, coils squeezing her, a choke) made her picture rise about one pixel, which rounds to nothing, so
  the card looked still while the monitor said 40 to 70 breaths a minute. Now the top of every breath lifts her at
  least window.alive.breath_min_px (3) pixels: a shallow breath is quick and small, but you can see it. Out cold
  or with her heart stopped she is still as before.
- **The online editor (narration.polish) now knows her body.** Its fact sheet has a BODY line for each fighter:
  her heart rate against her own resting rate and what it means (pounding, racing, slowing under the coils, uneven,
  stopped), her blood pressure, her breathing (how fast, how deep, why), her core heat, her air, her blood and where
  she bleeds, her footing, her composure, her adrenaline; in coils, how far she is squeezed in, the blood flow cut
  off, the pressure, her girth against normal, her heart's strength left, and each grip's pressure and how fast it
  tightens. It is told to show all of this in what she feels and what can be seen and heard, never as numbers or
  medical words. narration.polish.body false = no BODY lines.

## Build 324
More of the fight you can see without remembering it, and a fix to the hold picture.
- **Replay hits** (a button beside Effects): the blows of the beat shown flash and jolt on the cards again. It
  works on any beat in the history. It needs the Effects menu's "Blows: flash and jolt" on.
- **Each part in detail.** Hover over a part's label, or its dot on her picture, for that part's report:
  - its damage and resistance, and what its wounds have cost her in health;
  - what did it and when;
  - how it looks now;
  - what it is doing: throbbing with her heartbeat, swelling, bleeding, singed, frost-numbed, cut, punctured,
    numb, broken, tired from use, wet;
  - the grips on it;
  - what it does to the rest of her, with the numbers: her blows and dodging with that limb, her pain, her blood
    and breath, her nerve (composure), and the statuses it has given her.
  - The console has the same: /limb Ripples left hip (or /limb Ripples for every hurt part).
  - window.limb_report.enabled false = the old two-number tip.
- **Each status its own hover.** The status line under each card is now one hover per status: what it is, what it
  does to her numbers, and, for the body's own statuses, where she is right now (keyed up: her adrenaline and how
  much harder she hits; unnerved: her composure and how much sooner she gives in; flushed: her core temperature;
  unsteady: her footing; short of air: her air; pale: her blood). /explain prints the same. Hovering her posture
  still shows them all at once.
- **The match badge.** A line over the cards, and at the top of the console's stat block, saying what kind of fight
  it is and how it ends (knockout only, submission, pins and knockouts...), the arena and the weather.
  window.match_badge, or the Effects menu.
- **The hold picture can be switched off** from the Effects menu ("Hold picture"), or /effects holdpic off. Only
  the body figure beside a grip goes; the coils' squeeze picture and the heart monitor stay.
- **Fix:** a coil submission (Seraphina's upright coil round Ripples' ribs and hip) was drawn as "forcing a joint",
  with her leg bent back. A coil now squeezes in the picture: round her body, it crushes; round a limb alone, it
  binds; round her neck, it chokes.
- **Fix:** the status lines in the numbers read as sentences: "Ripples has a dead arm", "Ripples has stinging
  cuts", "Ripples' ribs are aching", "Ripples is rocked by the blow to her right hip", not "Ripples is dead arm" or
  "Ripples rocked by the right hip hit".

## Build 323
The setup questions at the start now ask the weather and the body, and both are kept in my_settings.json (so they
hold across new builds, and override rules.json, as everything you set does).
- **Weather>** after the arena: the arena's own (the default), random, clear, rain, storm, snow, heat or wind. Not
  asked for an indoor arena. A preset asks it too.
- **THE BODY:** each part of the simulated body listed with whether it is on: air, heart, blood, adrenaline, tissue
  (swelling), bones, footing, heat, mind (composure), limbs. Enter keeps them; all, none, off <names> or on <names>
  (e.g. off heat mind).
- **The same at any time:** /weather and /body (new), both saved.
- A questions list kept in my_settings.json from before still gets the two new questions, where they go
  (setup.skip lists any you never want added that way).

## Build 322
Weather over the whole fight (arena_weather in rules.json; /weather to choose). A move's weather (Rain Dance, Sunny
Day, Hail) still takes over while it lasts.
- **Which weather.** By default the arena's own: the storm forest has its thunderstorm, the desert ruins their wind,
  most arenas none. /weather picks one for every fight (rain, storm, snow, heat, wind), random, or clear. Indoor
  arenas (the sea cave, the power plant, the crystal mine, the clock tower) never have any.
- **The kinds:**
  - **Rain:** the ground slick, everyone soaked (Electric hits harder), her body cooled. Water moves stronger, Fire
    weaker.
  - **Thunderstorm:** rain as above, gusts, and lightning. A bolt very rarely strikes a fighter, likelier one up in
    the air: it hurts, may stun her, throws her down. A Ground type is untouched; an Electric type takes it in. Now
    and then a bolt strikes close by: both flinch and lose some composure. It never ends a fight by itself.
  - **Snow:** slick, cold. Ice moves stronger, Fire weaker.
  - **Summer heat:** heats her and slows her cooling. Fire moves stronger, Ice weaker.
  - **Strong wind:** gusts knock her footing (less for a big body) and buffet a flyer (BUFFETED: dodging slower).
    Flying moves stronger, Fire weaker; it chills a little.
- **Her own type in it.** A Water type in the rain is in her element: her blows a touch stronger, her strength back
  sooner. A Fire type is doused. In summer heat a Water or an Ice type wilts and heats faster, unless she is
  standing in water; a Fire type thrives. An Ice type is at home in the snow; Dragon and Grass types are slowed by it.
- **Coils heat her.** In any weather, coils round her warm her (the constrictor's body pressed round hers, and the
  friction), three times as much in summer heat. A long constriction in the heat can leave her heat-exhausted.
  Past flushed she also gives in to a hold a little sooner.
- **Told.** The weather goes to the narrator and the director every beat and into the opening passage; lightning
  and gusts are told when they happen. /weather and /scene show it.
- **Measured** (Nocturne against Ripples, 40 to 60 fights each):
  - Clear: Ripples won 38%. In rain she won 55%, the Water type in her element.
  - Thunderstorm: about one strike every two fights, a near miss about once a fight, a gust 2 or 3 times.
  - Summer heat: both flushed most of the fight, heat-exhausted a beat or two.
  - Seraphina's coils in summer heat: Ripples ran hotter than Seraphina and was heat-exhausted about 8 beats a fight.
- The default arena (the lakeside clearing) has no weather, so ordinary fights are as before.

## Build 321
Her mind simulated (body.mind, its own switch in rules.json), footing and heat given more weight, and Glacia made
sturdier.
- **Composure.** A running number, 100 calm. A beat that hurts her, being held or pinned, a choke or coils with her
  air going, and being knocked down all cost her some. Landing her own blows gives some back.
  - It settles back toward calm every beat, never goes below a floor, and the same blow costs less late in a long
    fight: always temporary, never grinding her down for good.
  - Low, she is UNNERVED: her blows and dodges a little weaker, the fear reactions (shaken, panicking) likelier, a
    smaller blow enough to shake her, and she gives in to a hold a little sooner.
- **Edge.** Who the fight is going for, from the health dealt and taken; with it on her side, emboldened is likelier.
- These drive the mind reactions from build 308 rather than adding rival ones. The head blow's own "rattled" is
  unchanged.
- **More weight for builds 319 and 320**, as asked: footing knocks harder and matters more when it is low; hard
  fighting heats her more, so a long, hard fight can leave her flushed; and the mind as above.
- **Glacia (Articuno) made sturdier, like the legendary she is:**
  - Health 2700 (was 2300), her parts 10% tougher, toughness 1.2, stamina 1.1. Her moves are unchanged.
  - Fire still hits her hard, a clear weakness: Cinder (Charizard) now wins 63 of 100 against her, from about 90.
- **Measured:**
  - Nocturne won 181 of 300 against Ripples with all three on, 170 with them off.
  - Per fight, about 4 beats unnerved and 1.8 staggers (1.4 off). Ordinary fights now get her flushed now and then;
    a fire-heavy one does so more.

## Build 320
Her body heat simulated (body.heat, its own switch in rules.json): her core temperature, carried from beat to beat.
- **What heats and cools her.** Hard fighting warms her a little. Fire that hits her heats her and ice cools her,
  less for her own type (a Fire type shrugs off heat, an Ice type the cold). The sun warms her; rain, hail and
  standing in water cool her; bodies pressed together in a hold warm a little. She settles back toward normal every
  beat, more slowly straight after a hard one.
- **What it does.** Hot, she is FLUSHED, and past that HEAT-EXHAUSTED: her energy and breath come back slower, her
  blows and dodges a touch weaker, her heart quicker. Cold, she is SHIVERING, then NUMBED: her blows and dodges
  weaker. It stays within a few degrees of normal: never a danger to her life.
- **Where to see it.** Her temperature is in the heart monitor's hover tip and /explain. Nothing new on screen.
- With it on, the older one-off "overheated" and "numb with cold" reactions to a fire or ice hit are left to it, so
  the heat isn't told twice.
- **Measured:**
  - In an ordinary fight she hardly ever gets hot enough to matter. Nocturne won 173 of 300 against Ripples with it
    on and off alike.
  - Under a fire-heavy fight (Cinder against Glacia) Glacia was flushed about 7 or 8 beats of a 35-beat fight, and the
    results hardly moved (Cinder won 90 of 100 with it, 91 without).

## Build 319
Her footing simulated (body.footing, its own switch in rules.json): how steady she is on her feet, 0 to 100, carried
from beat to beat.
- **What knocks it.** Every blow, by the damage it does: blows to her legs and head most, blunt blows and blasts
  more than cuts. Four legs or a serpent's coils hold steadier. Being knocked staggering costs more on top, and so
  does a blow turned aside.
- **What brings it back.** A little each beat she isn't hit. It comes back slower with her energy low and her legs
  tired, swollen or broken. It can't come all the way back while she is light-headed, dazed or on slick ground.
  Getting up, she starts unsteady.
- **What it does.** Low on footing, a blow staggers her more easily, a knockdown blow puts her down more often, she
  slips more on slick ground, and her blows and dodges are a little weaker. Very low, she is UNSTEADY and the story
  says so. It only counts on her feet: down, pinned or in the air it doesn't.
- **Measured:** Nocturne won 173 of 300 knockout fights against Ripples with it on and 170 with it off. Staggers went
  from 1.4 to 1.6 a fight.

## Build 318
More of her body simulated: blood loss, adrenaline, swelling and broken bones. Each is its own switch in rules.json
(body.blood, body.adrenaline, body.tissue, body.bones), is told to the story and shows on her card (hover the status
line).
- **Blood (body.blood).** A bite or a claw opens the part it hurts to bleed. Each wound clots over a few beats, more
  slowly while a grip is on it. She is BLEEDING while it runs fast, PALE once she has lost enough, LIGHT-HEADED past
  that. Losing blood weakens her blows and dodges a little, quickens her heart and lowers her blood pressure on the
  monitor. It never goes below a floor: never a death. The card draws blood running from a bleeding wound.
- **Adrenaline (body.adrenaline).** It rises with a hard beat, with being held or pinned, and with her health low, and
  ebbs every beat. It dulls the pain (she resists a tap harder), adds a little to her blows and quickens her heart;
  high, she is KEYED UP. When a big rush runs out, a short CRASH. The one-time surge at her last strength is still its
  own thing.
- **Swelling (body.tissue).** A blow sets how far a part will swell, and it swells toward that over the next beats,
  blunt blows most, then going down slowly. A swollen limb is stiff (its blows weaker), and swollen legs dodge worse.
  On her card the bruises spread as the part swells and age: angry red-purple when fresh, then purple, then dark with
  a yellowing edge.
- **Broken bones (body.bones).**
  - Very rarely in a fight: a blow or a grip that takes a bone past 320% damage.
  - At the end of her match: on parts worn past 220%, likelier the worse they are. Ribs inside coils are likelier,
    so a constrictor's match tends to break ribs, and so is a limb held in a grip.
  - At most two at the end. A broken limb hits much weaker, and a broken leg dodges worse.
  - Never her spine, back, neck or skull. Told plainly and without gore. It heals: nothing permanent.
- **Measured:**

  | | New systems off | New systems on |
  |---|---|---|
  | Nocturne vs Ripples, 300 knockout fights | Nocturne 186 wins, 39.4 beats | Nocturne 178 wins, 39.8 beats |

  Bones broken in a fight: 2 in 100 normal fights, 6 in 60 three-tap constrictor matches (those run about 100
  beats). At the end of the match: about 1 in 5 normal fights, about one per constrictor match, mostly ribs.

## Build 317
How matches end: pins still the usual way, knockouts by where the blows land, pins worn down by what they really do,
and each special match closed to the other endings.
- **Knockouts by where they land (moves.knockout.sim).** Blows to her head (jaw, muzzle, temple) and to her body (gut,
  flanks, ribs, chest: the liver, the solar plexus) each build a shock that fades between beats. A hard shot where it
  has piled up is what puts her out, the more so if her head is already rattled or dazed, or her body is doubled over
  or winded. A beat of blows only to her limbs, back or tail hardly ever does it (x0.3). A clean hard shot can do it on
  its own. A **head** knockout is out cold. A **body** knockout folds her round it, unable to rise, and the story is
  told it that way. The health gates are unchanged, so knockouts stay rare.
- **Pins worn down by what they do (pin.fade.sim).**
  - The pain under the press counts the whole way, not only once a part is in agony.
  - Claws, talons or teeth driven into a paw or a foot, where the nerves bunch, wear her down a little faster.
  - A grip on her neck in a pin chokes her slowly: at a third of a real choke's rate (body.air.pin_choke). It is a pin,
    not a choke, but held long enough it puts her out.
  - What she passes out from (the choke or the pain) now follows which has really gone further.
  - A pin still never ends in a tap.
- **Neck grips in pins (pin.neck).** When a pin the director starts has no grip on her throat or neck, 4 times in 10
  the pinner adds one with what she has free: her jaws first, else a forearm barred across it, else coils looped round.
  Face-down she has only the back of her neck.
- **Special matches stay closed.** In a submission match the director can't put anyone out, even with
  pin.director_can_eliminate on. Pins were already off there, and knockouts are off unless allow_knockouts is on.
  Knockout-only fights still end only by knockouts.
- **Measured:**

  | Matches | Fights | How they ended |
  |---|---|---|
  | Normal (Nocturne, Seraphina, Nerine against Ripples) | 450 | 433 pins (331 passing out from the pain, 56 from a neck grip, 46 from coils), 17 knockouts (7 of them body shots); about 5% shorter than before |
  | Knockout-only (Nocturne vs Ripples) | 100 | all knockouts, 21 by body shots |
  | Submission (Nerine vs Ripples) | 100 | only taps and pass-outs in holds |
  | Three-tap submission (Seraphina vs Ripples) | 40 | 94 of Seraphina's 108 taps and pass-outs came from her coils |

## Build 316
Her heart rate carried from beat to beat, and blood chokes as their own thing.
- **The heart rate is a running number (body.heart).** It used to be worked out fresh each beat from her state. Now
  each beat it moves toward what her body asks of it (her resting rate, pushed up by effort, pain, fear or panic, short
  of air), quickly when it has to rise and slowly as it settles, with a little natural unevenness. A hard exchange
  leaves it racing for a few beats after, and a rest brings it down gradually. Under coils it is the constriction's
  own heart. The monitor shows it, and with build 315's live trace each beat comes at the rate she has then.
- **Blood chokes have their own gauge.** A grip closing on the sides of her neck (legs, arms or coils round it, hands
  or jaws round it) cuts off the blood to her head. She can still breathe a little, and she goes under by whichever of
  her blood and her air runs out first. They are a little faster than an air choke, not dramatically so: in testing a
  blood choke put her out at beat 6 with three-quarters of her air left, a windpipe choke at beat 7 with none.
- **Blood chokes are the usual kind now:** a neck grip whose words don't say it presses across the front of her
  throat counts as one (body.air.blood_default).
- Balance: in 150 submission matches Nerine beat Ripples 83 times (92 in build 314's run). Part of that is chance,
  because the new heart draws on the same dice and changes every fight's rolls.

## Build 315
The window: a heart monitor that looks simulated, and zoomed cards that stay alive.
- **The heart trace is laid down beat by beat (window.live_ecg).** Before, one fixed pattern was drawn twice and slid
  along, and the "irregular" pattern was picked by the heart rate, so the same rate always drew the same trace,
  repeating every six seconds. Now each beat is drawn as its time comes, at her rate then:
  - a healthy heart's gaps vary by a few percent and each beat is a touch taller or shorter;
  - an irregular heart's gaps are uneven, a beat is now and then skipped, and now and then one comes early, wide and
    odd-shaped, with a pause after it;
  - a stopped heart is a flat line with a faint wander;
  - a new rate shows from the next beat on, never as a jump.

  The beating heart beside the squeeze and the throb of her hurts beat on the same beats.
- **Zoomed cards stay alive (window.live_zoom).** At any size but 100% (Cards − / +), the card used to be a still
  picture borrowed from the fight export. Her breathing and throbbing stopped, and in dark mode it was white behind
  her. Now it is drawn as at full size and scaled, its pictures made at that size, so everything still moves, on the
  window's own background.

## Build 314
The first of the simulated-body builds: her breath and each limb's tiredness are running numbers now (body.air,
body.limbs, each switchable). The dice still decide how hard each blow and each struggle is; these are what the dice
act on.
- **Air (0 to 100).** Fighting hard spends it, a grip on her throat cuts it off (faster the tighter the grip and the
  more worn she is), coils squeezing her chest let her breathe only shallowly, and being winded, coughing up water or
  panicking costs her some. Breathing freely brings it back quickly. Under 40% she hits softer, dodges slower and gets
  her energy back slower. Under 35% she is SHORT OF AIR, under 15% STARVED OF AIR, and the story is told so.
- **Chokes go by the air really left in her.** She can go under once it is nearly gone, in place of the old fixed
  count of beats. A fighter already out of breath from the fight goes under sooner.
- **Limbs (0 to 100 each: arms, legs, jaws, head, tail, wings).** Every blow thrown with a limb tires it, more for a
  heavier move, and every beat she holds a grip with it. A limb she isn't using recovers, slower when her energy is
  low. From 30 its blows weaken (down to x0.75) and a grip held with it is easier to break. Tired legs dodge worse.
  From 55 the story is told: her ARMS HEAVY, her JAWS ACHING. Coils go by their own energy cost, as before.
- **On the card:** air shows beside her breathing on the heart monitor once it drops under 95% (red under 35%). The
  new statuses sit on her status line; hover for what they do.
- **Measured:**

  | | Body systems off | Body systems on |
  |---|---|---|
  | Nocturne vs Ripples, 300 knockout fights | Nocturne 167 wins, 42.9 beats | Nocturne 167 wins, 43.1 beats |
  | Nerine vs Ripples, 150 submission matches | Nerine 94 wins, 40.2 beats, 10 choke pass-outs | Nerine 92 wins, 40.5 beats, 12 choke pass-outs |

  Low air comes mostly from chokes, then from long hard exchanges.

## Build 313
Her heart under the coils, simulated; the coils staying on her after it stops; and the writing weaknesses from the
IQ4_XS paste.
- **The heart is its own number now (constriction.heart).** Instead of a 60% roll when she blacks out, her heart
  wears down beat by beat. How fast depends on what the coils press with (mmHg) against her blood pressure, how far
  she is squeezed in, chest or middle, the number of coils, and how long they have held. Her health and energy slow
  it, and a small wobble each beat keeps it from playing out the same way twice. It races at first, then slows, then
  goes uneven, and while uneven it can now and then give out early. When it reaches zero it stops, and she blacks out
  with it.
- **The black-out is almost always her heart.** The blood gauge can still put her out first, at a tenth of its old
  chance (`gauge_out_mult`).
- **The card shows it coming:** the line under the coils' monitor reads "Her heart is slowing: 125/min; it stops at
  about 40/min", then "failing", then "nearly gone". Hovering explains what drives it.
- **The coils stay on after her heart stops (after_hold).** For `beats_min` to `beats_max` more beats (1 to 3), the
  coiler keeps holding her limp body. She can't act, nobody strikes her, and the coils do her no more harm. The story
  is told what that looks like, without gore. Then the coils come off, her heart starts again on its own, and she
  comes round. In the match's final black-out it is told rather than played. It is never a death.
- **Measured:** in 80 three-tap Seraphina vs Ripples matches, 153 of 155 coil black-outs came with her heart stopping
  (96 of 154 before). Taps in coils went from 23 to 13. Match length was unchanged (94.7 beats against 94.6).
- **Writing fixes:**
  - **A dialogue tag after a quote is no longer deleted.** `"No," she hissed.` used to lose "she hissed" to the clean-up
    rule for sentences left starting mid-clause. That is how "Give up, little one," was left with no speaker.
  - **Cut seams are mended:** a clause ending on its article ("slow and even, a deliberate."), a line of speech whose
    speaker was cut, and a sentence leaning on a cut one ("She glanced down at it") go with it.
  - **Repeats across beats (narration.repeat_across):** a phrase from the last two beats is caught like one repeated
    within a beat, and five-word runs count too ("her vision greying at the edges").
  - **Blunt blows (narration.blow_feel):** "a line of fire drawn in one swift, brutal stroke" for a head-butt is
    caught when nothing that cuts landed this beat.
  - **Room in the coils (narration.coil_room):** at 80% squeezed in or more, twisting round to look, spinning,
    arching or thrashing is caught and rewritten to small movements.

## Build 312
What the card shows, explained, without anything new drawn on it (window.explain, on by default).
- **Hover over her status line** to see each status on her: what it is, how many beats it has left, and what it does
  to the numbers, read from the rules in force. For example: "Staggered (2 more beats): knocked a step or more by the
  last blow... Effect: her dodging 40% worse; her blows 15% weaker."
- **Hover over a vital** (heart rate, blood pressure, breathing, blood flow cut off, the squeeze, the coils' mmHg) to
  see what the number means, what is normal and what hers means right now. 139/90, for instance, reads as "raised: her
  heart pushing hard with the effort, the pain and the fear"; in the coils, a heart slowing below her resting rate is
  called out as the danger sign.
- **/explain** in the console gives the same as text: `/explain` for everyone, `/explain Ripples` for one fighter,
  `/explain dazed` for one status.
- **The coils' strip at high display scaling:** its lines ran into each other at 4K with Windows scaling (and the
  black-out line I moved in build 311 landed on the squeeze text). Each line is now placed under the one above it by
  its real height, long lines wrap and push the rest down, and the BP column is as wide as its words.
- Tips that would run off the right or bottom of the screen open the other way.

## Build 311
Fixes and answers from the third paste of the Seraphina vs Ripples fight.
- **A Dragon Tail from inside her own coils:** Seraphina had two coils round Ripples and still whipped her with her
  tail, hurling her into a pine. Her coils count as her tail now (holds.busy_limbs.coils_use_tail). With two coils or
  more her tail is used up, so she has no tail strike. With one coil, usually her middle, the end of her tail is left
  loose half the time (`tail_free_chance`, rolled once when the coil goes on). She can flick that free end at 0.6 of
  the power (`tail_free_power`). The director is told which.
- **No throw out of the attacker's own grip:** a fighter held in the attacker's grip or coils can't be knocked down,
  thrown or sent into the scenery by that attacker's blow (holds.held_no_launch). Throws and slams from a hold are
  unchanged.
- **Breathing on the coils' monitor:** while coils hold her, the heart monitor gives way to the constriction strip,
  which had no breathing on it. It shows her breathing rate now, shallow as the coils close in, beside her normal rate.
- **The tap explanation (ⓘ):** it described the old ceiling formula. It now describes the one in use (tap.blend).

## Build 310
Fixes from the second paste of the Seraphina vs Ripples fight.
- **A paragraph in the present tense got through:** "Seraphina's antennae droop slightly... Her scales shimmer... The
  warm breeze rustles the grass and carries..." The check didn't know these verbs (droop, shimmer, glint, gleam,
  glisten, sparkle, flicker, sway, flutter, glow, shine, rustle, stiffen) or that "antennae" is a plural. It knows them
  now, and puts them into the past itself. An older false alarm is fixed along the way: "the faintest tremble in the
  air" was being read as a verb.
- **Bones "jutting out at odd angles, ... it was broken"** now count as a broken bone. Like any other, it's cut unless
  that part is hurt badly enough to break.
- The "coat torn and bleeding where Seraphina's coils had dug in" came from her grip "with her full body weight and
  claws". Build 309 already rules that grip out for a Milotic.

## Build 309
Fixes from your build-307 Seraphina vs Ripples submission fight.
- **A Milotic has no knees or claws:** the director gave Seraphina a "Knee Strike" with her "right foreleg" (power 45,
  the strongest blow of the fight) and a grip "with her full body weight and claws". An improvised blow whose name
  asks for a limb she has none of (a kick, a knee, a punch, a claw swipe, from a body with no legs or arms) is now
  refused, and the director is told to name the blow by what her body has. A grip with claws needs paws, hands, feet
  or talons.
- **No borrowed twin tails:** Seraphina's Tail Whip came with "twin tails slam across Ripples' left foot", which are
  Ripples' tails, and the prose followed it. Twin tails are now dropped from the attack's direction for a fighter who
  has one tail.
- **"Breather: is given no room to answer Seraphina"** had lost its subject on the screen: it now reads "Ripples is
  given no room...".
- **Taps come a little sooner when the pain is far past her limit** (`finish.submission.tap.blend.past_limit`): with
  her foot crushed past 500% and almost no health left, Ripples' tap chance on a hold's third beat was 1%. The chance
  builds up over a hold's first eight beats, and that build-up started over every time the grip was let go and put
  back on. It now runs up to 1.35 times faster the further past her resistance the pain is. Bigger values made 3-tap
  matches a sixth shorter or more in testing, so it is kept small. Not for coils round her body (below).
- **In coils, she blacks out more than she taps** (`constriction.tap_mult` 0.35, `constriction.heart_stop.chance`
  0.35 → 0.6): coils round her chest or middle make her tap only about a third as often as other holds would. When she
  blacks out in them, her heart now stops for a moment (and starts again on its own) more often than not. In 80 3-tap
  Seraphina vs Ripples matches, coils ended a round:
  - before: 50 taps, 79 black-outs, 40 black-outs with her heart stopping;
  - after (with the recovery below): 14 taps, 75 black-outs, 78 black-outs with her heart stopping.
- **Coils wound on again soon after start where her body still is** (`constriction.recovery`): before, each new coil
  started from nothing, even one wound on a beat after the last let go. What the last coils did to her blood now fades
  by half each beat, and how far her chest was squeezed in fades faster. Coils back on within four beats start part of
  the way along: her heart is still raised (racing as the blood came back, never below her resting rate), and it slows
  and greys sooner than the first time.
- **Balance** (3-tap submission matches, 80 no-model fights each, build 308 against this build):

  | Pairing | Wins | Fight length |
  |---|---|---|
  | Seraphina vs Ripples | Seraphina 44, Ripples 28 (8 unfinished) → Seraphina 41, Ripples 32 (7 unfinished) | 107 → 101 beats |
  | Nerine vs Ripples | Nerine 43, Ripples 36 → Nerine 41, Ripples 39 | 83 → 77 beats |

  Knockout matches don't change.

## Build 308
Attacks now cause the body and mind reactions you'd expect, small and short-lived, so fights run as long as before.
Coils and submissions can last longer, and the face gets hit sometimes. Everything is a switch in rules.json
(`moves.reactions`, `holds.endurance`, `moves.head.concussion.min_blows`, `director.face_chance`), each with a comment.
- **The body (reactions.py):** what a hit leaves depends on what it was and where it landed:
  - a blunt blow to the nose can start a nosebleed;
  - a cut above the eye runs blood into it; sand or stone in the face leaves grit in her eyes;
  - a blow to the throat makes her cough and gag;
  - an electric hit that didn't paralyze her leaves her twitching.
  - Some only come once enough of it has built up over the fight: a sick stomach after blows to the gut, cuts that
    sting, overheating from fire, paws numb with cold, a headache from Psychic attacks, stings swelling.
  - So one claw never has her bleeding all over.
- **The mind:**
  - a huge blow (or a stun) can shake her, and the one who landed it feels bolder;
  - three blows in a row she couldn't answer make her angry: she hits harder and guards less;
  - three misses in a row frustrate her;
  - two beats with no air (in a choke, or in coils round her chest or throat) can tip her into panic, which burns
    her energy.
- **Being held:** the narrator is told what each kind of hold is doing to her body, stage by stage (from its first,
  second and fourth beat), once each.
  - Coils round her chest: each time she breathes out, the coils take up the slack; her face and ears burn hot with
    blood that can't get back down; later her ribs creak and a sick, swimming feeling rises.
  - A choke has an air, a blood or a full version. There are also lines for a joint lock, a bite, a bound limb and a
    plain grip.
- **When a hold comes off** after two beats or more, it leaves its aftermath:
  - a head rush as the blood floods back after coils or a blood choke;
  - pins and needles in a limb that was bound or trapped;
  - a raw throat after a choke;
  - a strained joint after a lock;
  - throbbing bite wounds;
  - wariness of the grip that had her.
- **Limits:** at most two body reactions and one mind reaction on her at a time, and the same one never comes back
  within a few beats. What each does to the numbers is small: a few per cent on power or dodging, a little more
  missing for blood or grit in her eyes, a little less breath back. `moves.reactions.effects false` keeps them in the
  story only. `moves.reactions.tune.<name>` changes any one of them, e.g. `/set moves.reactions.tune.nosebleed.chance 0.2`.
- **No concussion from one hit:** concussion also needs at least three separate blows to her head this fight
  (`concussion.min_blows`), however hard any one of them is.
- **Longer coils and submissions (`holds.endurance`):** the break-free roll against them now depends on how strong
  she is against the one holding her (strength, size, energy). Against an equal she gets out about half as often, so
  holds can run on. A fighter much stronger than her holder can still tear out early, about as easily as before. It
  stays a dice roll every beat. Coils also cost the coiler less energy to keep on, and a submission's escape chance
  grows more slowly, and a blow to the coiler or the one holding the lock shakes it loose less often. Plain grips
  are unchanged.
- **The face (`director.face_chance`):** nothing in the code kept muzzles and noses from being hit. The director
  model just tends to name Head, Neck and Chest. Now and then, when no other target idea ran, it's reminded that the
  opponent has a Muzzle and a Nose, and what a blow there does. It's an idea, never an order.
- **Balance** (no-model simulations; everything off first, then on):

  | Pairing | Wins | Fight length | Submissions held |
  |---|---|---|---|
  | Nocturne vs Ripples (300 fights) | 57.7% → 55% | 42.9 → 42.9 beats | 2.75 → 3.4 beats on average |
  | Nerine vs Ripples | 58% → 63% | 44.8 → 44.0 beats | 3.1 → 3.9 beats |
  | Seraphina vs Ripples | 88% → 84% | 50.1 → 50.1 beats | |

  Fights run as long as before. The longest coils and submissions now go 11–14 beats. Ripples' stats are untouched.

## Build 307
The effects from build 306 can each be turned off without editing settings.
- **The Effects button** above the cards (beside Poses) opens a list with a tick for each: breathing, pain pulsing
  with her heart, the flash and jolt of blows, the grey closing in, grip rings in the holder's colours, the heart
  monitor, and the injuries settling in (the story). "All of them" turns every one off or on. The cards change at once.
- **`/effects`** does the same from the game's prompt: `/effects` alone shows what is on, `/effects off` (or `on`)
  turns them all off, `/effects monitor off` or `/effects breathing grey off` turns off just those. The names are
  breathing, pulse, impact, grey, grips, monitor and settling. The window picks the change up within a second.
- Either way the choice is kept for next time (in my_settings.json, as /set keeps things).

## Build 306
The fighter cards come alive, all from her own artwork (nothing new drawn over it), and the prose shows hurts coming
on. Every piece is a switch in rules.json `window.alive` (with `enabled` false for none of it).

- **A heart monitor on every card** (`heart_monitor`), under her bars, always there: her heart rate with a trace
  moving at it, her blood pressure and her breathing, each with its normal beside it, and what is doing it (winded,
  spent, the pain she is in, her statuses, guarding her ribs, no air getting in). Her heart rises from her resting
  rate (fighters.json `heart_rest`) with exertion, pain and adrenaline, and slows when she is asleep, frozen or out.
  While coils squeeze her, the constriction's own monitor and squeeze picture take its place.
- **Breathing** (`breathing`): her picture rises and falls at her breathing rate. It's slow at rest, quicker as she
  tires, fast and shallow in the coils, in a choke or guarding hurt ribs, and slow and faint once she is out.
- **Pain pulsing** (`pulse`): the glow on her hurt parts throbs with each beat of her heart, more the more pain she
  is in.
- **Impact** (`impact`): when the window moves on a beat (or you step forward one), every part that was hit flashes
  and her picture jolts, harder for bigger blows, for under half a second.
- **The grey closing in** (`grey_in`): as a choke or the coils near her black-out, her picture loses its colour and a
  dark edge closes in round it. Exported fights show it too, still.
- **Grips in the holder's colours** (`grip_outline`): the rings on her gripped parts are in the holder's own colours
  and pulse.
- **Injuries settling in** (`narration.settling_in`): a part hit a beat or more ago and untouched since, whose damage
  has passed the next step (60 stiffening, 150 swelling and favored, 300 barely used), gets one note for the story to
  show as it comes on, by where it is: a hitch as she puts her weight on a hurt foot, each breath catching at her
  ribs, swelling coming up at her jaw. Each step is told once, the worst first; lying down or in the air a leg is
  never told by her weight on it. A reroll gets the same note, and undo puts it back.

## Build 305
Fixes from the Seraphina vs Ripples submission fight.

Things that happened and weren't told:
- **A black-out that counts as one tap of several was never checked**: Ripples blacked out in the coils (tap 1 of 3)
  and the story only had the coils loosening. The check that the prose shows her going under only ran for a
  black-out that ends the fight. It now runs for every one; a passage that still doesn't show it is asked for once
  more, then the program says it plainly. The note for it no longer says "show the tap", and the stat line gives the
  constriction's own numbers, not "the choke built to 0 against her endurance 0".
- **Being borne down in a hold** (to her knees, then flat) is now something the prose must show, like any fall.
- **She no longer gets up out of a grip that bore her down** while it is still on her: she rose in the coils one beat
  and was borne flat again in the same beat, and neither was told.

Slips the checks now catch or mend:
- the present tense with a plural subject ("The coils around Ripples tighten", "Her paws scrabble"), "can" and "will"
  ("She can see"), and after "and" ("and works by feel", "and nearly gets there"), mended by the program itself;
- a feature on the wrong fighter in a sentence that opens on "Her" ("Ripples was bent double. Her antennae
  drooped": the antennae are Seraphina's), and "tails" for a fighter with one tail (Seraphina's upper and lower tail
  are one tail);
- her own wrist, her own ankle, her free paw while her arms are pinned in coils; the story-line libraries no longer
  offer lines that need her arms then ("she locks her free paw round her own ankle");
- a head strike in a beat whose blows are all with her tail ("she snapped her head forward, striking Ripples' jaw");
- a note's label left in brackets ("(her stomach)", "(a glancing squeeze, still minor)", "(ruined)"); a sound in
  brackets stays.

Thoughts (`narration.mend_thoughts`): a thought loses a "voice" ("she thought, her voice calm and measured"), a
first-person thought in the past goes back to her present ("*I needed to finish this soon*" becomes "*I need to*"), a
thought said again a moment later goes, and a thought one fighter had is taken out of the other's part ("*This time,
I won't be gentle*" in both). A paragraph of narration set in italics is made plain even when it doesn't start with a
fighter's name.

Notes the model copied word for word are now worded so they can't be: the coiler's heartbeat lines are whole
sentences ("It was a frantic flutter" had lost its heart), the holder's feelings in a hold ("Seraphina's grip tiring
and holding anyway"), where a tap would land ("She was on her feet in the hold: the ground was out of reach"), and an
emotion line that claimed a blow had landed short.

## Build 304
The grips on her as a picture (`window.hold_picture`, on by default): while a hold, a submission, a grab or a pin is
on her, her card (and an exported fight) shows her body from the front, drawn by the program, with each part in a
grip outlined in the holder's colours and what the grip does drawn on it. There are far too many holds for a picture
each, so they are drawn by what they do, from the hold's name first and then the parts it grips:
- a joint lock (hammerlock, arm bar, knee bar, full nelson...): the limb bent past where it should go, further the
  nearer her pain is to what she can bear, with an arrow round the joint;
- a choke (sleeper, guillotine...): arrows pressing in at her neck, a band round it;
- a crush (bear hug, body lock...): her body squeezed from both sides;
- a head hold (headlock...): her head clamped;
- coils round a limb: bands wound round it (coils round her body keep the squeeze picture);
- a grab: grip marks on the part; a pin: weight bearing down on her.

Beside it, side by side, each grip (who, what, on which parts, how many beats), a gauge (her pain against what she
can bear, with her limit marked; her air for a choke; a pin's count against its length) and this beat's tap chance.

## Build 303
The polish (Venice) may make a beat longer. Before, a polished beat more than 1.5 times the local one's length was
thrown out ("it changed the length too much"), however good it was; `narration.polish.max_ratio` is now 0, no upper
limit (set a number to bring a cap back). And with `narration.polish.expand` (on by default) the editor is told it is
not held to the draft's length: more of what each fighter sees, feels and thinks, the big moments given room, never
anything new happening. Everything else that decides whether its version is kept is as before: the part labels,
every fighter, every part a blow landed on, no fewer than about half the words, and the program's own sentence
checks finding nothing more wrong in it.

## Build 302
How close she is to blacking out in the coils, and to her heart stopping:
- the blood-flow bar has a line at her limit: past it she can black out (and her heart stop as she does);
- under it, a line: before the limit, how much more has to be cut off before she can ("Black-out: not yet (12% more
  cut off before she can)"); past it, this beat's chances ("Past her limit: black-out 16%, heart stopping 5.6% this
  beat"), coloured as they climb; once her heart has stopped, that.

The heart-stop chance is the black-out chance x `constriction.heart_stop.chance`. On the card and in exported fights.

With the squeeze picture on, the strip is laid out side by side: the picture and her heart on the left, the monitor,
the black-out line and the readings to their right (178 pixels tall instead of over 200). Exported fights put the
monitor and the picture side by side where the page is wide enough.

## Build 301
A saved fight loads back whole:
- The /undo history is kept in the save (`save.history`, the newest 30 beats), so a loaded fight can be undone back
  through its beats, to its start, as before it was saved. Each beat is about 40 KB in the file; it is worked out once,
  so the autosave after every beat stays quick.
- The window rebuilds its story pane and its beat slider from the save's record of every beat (its text and every
  fighter's numbers as they stood after it), so the story, the pictures, the gauges and the numbers of each earlier
  beat can be looked at again after loading.
- /undo rebuilds them too, so an undone beat no longer stays on the slider.

Every fight's beat history now begins with the fight as it stood before anything happened ("at the start"), on the
window's slider and in exported fights: before, the first place you could go back to was the end of the first beat.

What a beat's narration was written from isn't kept in the save, so /reroll works only on beats written after loading.

## Build 300
The squeeze picture shows only the coils wound round her, no longer the rest of the coiler trailing off to one side.

How tight the squeeze is, in real-world numbers, beside the squeeze picture (rough, like the rest of the vitals, never
rolled against; `finish.submission.constriction.vitals.pressure` and `.girth`):
- what the coils press on her with, in mmHg so it reads straight against her blood pressure, on a gauge with her
  pressure marked: once the coils press harder than her blood pressure, blood can't get back to her heart. It grows
  with the squeeze and with how big the coiler is against her: a coiler her own size reaches about 90 mmHg at a full
  squeeze, Seraphina on Ripples about 170;
- her girth round her chest or middle, now and normally ("Chest and middle 38 cm (normal 49 cm, 11 cm squeezed
  out)").

Her healthy numbers are shown with every reading: her resting heart rate under her heart rate, a normal 120/80 under
her blood pressure, on the card, in exported fights and on the stat line. A heart that stops keeps the rest of its
last reading (the squeeze, the normal numbers).

## Build 299
The squeeze as a picture (`window.squeeze_figure`, on by default). While coils squeeze her, her card shows, under the
heart monitor and in place of the old squeeze bar, a picture of its own (drawn by the program, not her artwork, which
may face any way):
- her torso from the front in her own colours (taken from her picture): head, shoulders, her arms pinned to her sides,
  a lighter belly;
- the coiler's loops wound round her in a spiral, in the coiler's colours, as thick as the coiler is big against her:
  Seraphina's loops cover most of Ripples' chest (only the coils on her are drawn, not the rest of the coiler);
- each loop pressing her in and her flesh bulging between them, harder as the squeeze builds; her ribs showing once it
  is crushing; her body paling toward a cold grey-blue as her blood flow is cut off;
- beside it, her heart: beating at her own rate (uneven and skipping when irregular), clenching on each beat,
  flattened between the coils when they are round her chest, smaller as less blood gets back to fill it, and still
  and grey once it stops.

Exported fights (`/exportfight`) show the same picture, the heart beating there too. false = the plain bar, as before.

## Build 298
Keeping coils on is work (`holds.coil.energy`, on by default). Each beat a coil costs the coiler 6 energy plus 0.4 for
every beat it has been on, less the bigger she is than the one in her coils, more for a second coil; and she gets no
rest bonus while she coils, only the ordinary 5 a beat back. A tired coiler (under 25) holds less surely, and one with
5 or less has to let go: "she is spent". Unless she can feel the fight about to end (a tap or black-out chance of 15%
or more, the grey closing in on her, or her health at 20% or less): then she digs deep and hangs on, a 60% chance, less
each beat she already has. Coils now last as long as the coiler has breath for them instead of a flat 10 beats.
Seraphina is so much bigger than Ripples that she barely tires: at full energy every coil ended before she was spent,
so nothing changed there; started at 25 energy, about half her coils on a fresh Ripples ended with her spent. Knockout
fights barely move (Seraphina beats Ripples 85% of the time, 82% before).

The 10-beat limit on other submissions is now told honestly: she has worked the hold as long as one can be kept on and
lets go to reset her grip, not "she can't keep it on any longer".

`/energy <name> [n]` gives a fighter energy straight away (25 if no number; `-n` takes it away, `=n` sets it, up to
100); `/energy` alone lists everyone's.

Fixed: a serpent's pin grip "her tail hauling the leg up" was refused because "the leg" (the one being held) was read
as a leg she grips with. Words for the other fighter's body ("the leg", "the other leg", "Ripples' leg") are no longer
counted. The dice stand-in also aims a spread of blows only at parts she can reach from where she holds her.

Fixed: a blow the game re-aims on its own (/focus, target variety, the tap steer, or a chain follow-up going back to
the last spot) could be moved onto a part she can't reach from her hold, and was then refused. It now stays where she
aimed it.

## Build 297
A coil round her body wears the whole band it goes round, not only the part it was put on
(`finish.submission.constriction.compression.ring_wear`, 0.5 by default): half of its pressure each beat stays on that
part and half is shared evenly over the rest of the band (her ribs on both sides and her upper back, or both flanks
and her lower back). The stat line lists every part it wears, and the narrator is told the ache builds evenly all
round her rather than in one sore spot. 0 = all of it on the one part, as before.

A coil wears her down before it hurts her (`holds.coil.wear_first`, on by default). While the parts it lies on are in
better than 40% condition, its damage (and so her health) is cut to 12% and its wear on their resistance doubled; the
bite climbs steeply from there to full at 15% and below. It takes the place of the slow-bite and submission-grind
curves for coils. A fresh fighter comes out of a long coil softened all round but with much of her health; a worn-down
one is in real trouble, and her worn band lets the squeeze close in faster too. Ten coils on a fresh Ripples: 4-19% of
her health lost (15-28% before), and in half of them the coiler gave out before she did; on a worn Ripples the coil
finishes her as fast as before and takes more health doing it. Knockout fights barely move (Seraphina beats Ripples
82% of the time, 81% before). The narrator is told which it is: pressure and soreness, pain starting, or worn through.

The dice stand-in (`simulate.py`) no longer picks a move with a limb that isn't answering her that beat.

## Build 296
A coil round her body touches her all the way round, not only the part it was put on
(`finish.submission.constriction.compression.ring`, on by default). Round her chest it lies on her chest (and ruff),
her ribs on both sides and her upper back; round her middle, on her belly, both flanks and her lower back. She braces
with the whole band, and the worst-hurt part anywhere in it counts against her endurance. A coil put on her back or
flank counts as round her chest or her middle, so "back" is no longer a place of its own. The narrator is told every
part it touches and that the pressure is even all round: front, sides and back. The stat line says "all round her
chest", and the squeeze bar draws the coils along her front and back as well as at her flanks. Off, only the parts
the coils were put on count, as before.

## Build 295
The squeeze bar is drawn the way it happens: her body (tan) in the middle, narrowing as she is squeezed in, with the
coil's blue edge wrapped round it, and the coils (blue blocks) pressing in from both ends, filling the room she has
lost, a stripe a side for each coil round her. Before, the coil was a block in the middle of her body. The label is
shorter: "chest 52%", "belly 30%", "both 92%".

## Build 294
Compression in a constriction (`finish.submission.constriction.compression`). Before, the constriction built from how
hard the coils pressed and how many beats they had held; nothing tracked how far she was squeezed in. Now it does,
from 0 to 92%, and that is what drives the rest:
- Each beat the coils gain on her: more the harder they press, the bigger the coiler is than her and the more coils
  there are; less the sturdier the parts they are on and the more strength she has to brace with. Each breath out
  they take up the room she gave up, and more when she fights it: struggling spends breath, and the coils take it.
  It closes in over about six beats.
- The blood gauge builds by how far she is squeezed in: little while the coils are only snug, fast once they have her
  in tight. Her heart and blood pressure follow the gauge, as before.
- It makes the coils harder to break (up to half her chance gone, squeezed all the way in) and costs her more breath
  (her energy loss x0.5 to x1.5).
- Chest and belly differ, a little in the numbers and mostly in the telling: round her chest, her ribs can't spring
  back out and the pressure bears straight in on her heart (the gauge a little faster); round her belly, her gut is
  driven up under her ribs and the breath is pushed out of her from below (a little slower on the heart); both; or her
  back bowed.
- The story is told how far in she is (snug, tight, crushing, held almost flat) and where, and whether she fought it
  this beat. The stat line says it, and the vitals strip draws it: her chest or belly as a band narrowing from both
  sides as the coils close in, the coils across it, "chest squeezed 61%". The strip now shows from a coil's first
  beat, before the squeeze has started on her blood.
- Timing kept as before: fresh about 9.5 beats to the end, worn down about 6.

No nausea anywhere: the nauseous body effect from build 293 is gone, and the old wording of a lurch of nausea (a
numb, devastated part hit again; poison) is now a cold rush of shock and weakness.

## Build 293
Head and body effects (`moves.head`, `moves.body_jolts`, both on by default; what each does is in `status_effects`).

A hard blow to the head rolls ONE of these, by how hard it landed, what landed (a blunt blow far more than a cut), where
(the jaw most of all, then the side of the head), whether her head was held and couldn't roll with it, her toughness,
an adrenaline surge, and a concussion already:
- rattled: a hard blink and a shake of the head; a little slower to dodge;
- dazed: her eyes won't focus, everything a beat late: far slower to dodge, more misses, weaker blows;
- stunned: the lights flicker; she loses her next action entirely: no attack, no grab, no dodge, no escape from a hold
  or pin, no get-up. The director's orders for her become her swaying there. After it, her legs go (wobbly: worse at
  dodging and getting up, easier to bear down in a hold) and she stays dazed a while.

Then what that spot does besides: watering eyes from the nose (more misses), ringing ears from an ear or the side of the
head, a rattled jaw (weaker bites), double vision after a dazing or a stun (far more misses), whiplash from a held head
or a throw. Dazed or stunned three times, or a head part at 300%, and she is CONCUSSED for the rest of the fight: later
head blows rattle her far more easily, getting up is harder, and the story carries the fog and the headache.

The rest of her: a dead leg (a thigh), a limp (a knee or foot already badly hurt), a dead arm, aching ribs, a back in
spasm, a numb tail base, an eye swelling shut. Each has its own effect, its icon on screen, its
look, thought and opponent's read for the story, and its line when it wears off. Sizes go by the damage scale, so /scale
15 doesn't make every blow the biggest. Balance (200 no-model fights a pair, effects on against off): Seraphina vs Ripples
84% / 84%, Nocturne vs Ripples 55% / 56%, Nerine vs Ripples 59% / 64%.

The heartbeat in a constriction (`narration.constriction_feel`):
- each beat the story gets what the coiler feels of the other's heart through her coils and does about it (waiting for
  the breath out, easing a fraction, holding it there), and what the one held feels of her own heart (loud in her ears,
  then slowing and skipping, then faint with gaps), stage by stage;
- the heart rate and blood pressure the screen shows go to the story as words (racing, slowed; up, falling, low), never
  as numbers, so the two agree;
- the coiler makes sure before she lets go (`verify`): she holds a while longer after the blackout, feeling for any fight
  left, then unwinds.

Her heart can stop (`constriction.heart_stop`, a third of blackouts): as she goes under, the slow, stumbling beat
stops. The coiler holds on through the silence, and as the coils come away it starts again on its own. It is never a
death: it ends the match like any blackout. The card shows "♥ stopped" and a flat line.

The monitor moves (`window.vitals_animate`): the heart trace runs like a real monitor's at her own heart rate, in the
window and in exported fights. It is one line redrawn a few times a second, so it uses no graphics-card memory.

## Build 292
Fixes from the played Seraphina vs Ripples log:
- "I headbutt Ripples' head four times and then squeeze even tighter" became a GRIP on her head, and no headbutt was
  thrown: "headbutt" wasn't one of the words read as an attack, and "squeeze" took the part from the whole order. Now
  a squeeze, tighten or coil order while she already holds the other TIGHTENS what she has (crushing, tightening),
  after the attack when there is one; a new grip takes its part from the words after the grip word.
- The words an order is read by are much fuller: attacks and getting away (headbutt, slam, punch, whip, charge,
  tackle, stomp, shove, throw, squirm, thrash, dodge, flee and many more), grips (tighten, clamp, choke, strangle,
  hug, seize, clutch, engulf, crank...) and holding back (relax, go limp, wait, rest, endure, catch her breath...).
- New story checks:
  - a body constriction told as her air being cut off ("cutting off her air supply"): the coils hold back her
    blood;
  - her heart told as slowing while it is still racing;
  - a fighter given a body part she doesn't have ("Ripples' antennae", "Seraphina's gills", "Seraphina's fur").
- The window's cards repaint as soon as a beat is drawn. They sit in a scrolling area, and on Windows a change inside
  it (a strip appearing, growing or shrinking) only showed once the cards were scrolled.

## Build 291
- The vitals strip is dark in dark mode too: its dark background had been turned light by the dark-mode colours, which
  hid its blood pressure.
- Its heartbeat trace always shows about six seconds, however wide the card, so a fast heart on a wide card is no longer
  a solid wall of beats: about 21 beats at 210 a minute, 7 at 70.

## Build 290
Dark mode for the newer parts of the window:
- The words on the pain gauges, the health bar and the energy bar get a dark edge, so the light letters can be read
  over a bright bar and over the dark background alike. The pain gauge's grey bar is a dark grey.
- The tap meter's words in its darkest colours (the dark red of "fighting the dark") are a lighter shade on the dark
  background.
- The Profiles window is dark too: its tabs, its background and its text boxes.

## Build 289
The vitals strip (heart, blood flow, blood pressure) shows from a coil's first beat. Before, it waited for the
second, although the part gauge already showed the blood flow; a choke's air on the tap meter likewise.

## Build 288
The vitals strip's second bar is labelled "pressure", with the dashed mark at a resting 120 in exported fights
too.

## Build 287
The constriction drawn, in the window and in exported fights. Under the tap meter, while coils hold back her blood, is
a small dark strip:
- her heart rate, with a trace of it, its beats spreading out as her heart slows and uneven once it starts to skip;
- a bar of how much of her blood flow the coils have cut off;
- her blood pressure, with a bar labelled "pressure": it fills with the first number (systolic) out of 160, with a
  dashed mark at a resting 120.

Its colour goes from green to red as the blood flow goes. The numbers came out of the tap meter's line, which is
shorter for it. The part pain gauge now says "blood flow cut off" for a constriction, not "air gone".

## Build 286
Speed without touching the writing (`console.speed_check`). After a beat the game asks Ollama how much of the
narrator model sits on the graphics card. When part of it is running in system memory instead, it says so once
(and again only if it gets worse), with what helps. That alone can make a beat several times slower: the build-285
log wrote at 14 tokens a second, slow for mistral-small:24b on a card that holds all of it. What helps:
- close other programs that use the graphics card;
- set `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` (Windows environment variables), then restart
  Ollama, so its working memory for the notes takes about half the room;
- use a slightly smaller download of the same model.

In the window, the tap meter's line under the steps is now as tall as its words: the longer notes (what keeps the
chance down, the refusals, the blood flow and heart) were cut off after two lines.

The notes themselves were checked for a coil beat: about 40,000 characters a part with nothing repeated worth cutting,
and every call already uses the same context size, so the model is not reloaded between calls.

## Build 285
Constriction (`finish.submission.constriction`, on by default in a submission match). Coils round her chest, belly or
back now put her out the way a real constrictor does: mostly by her blood, not her breath. The squeeze stops blood
getting back to her heart, her blood pressure falls, and her heart, racing at first with fear and effort, slows and
stumbles until she blacks out. Her breaths grow shallow too (the coils take up the slack each time she breathes out),
but that is not what takes her.
- A gauge builds each beat the coils are on, like a choke's air. It builds faster with more coils, a harder squeeze
  and a coiler much bigger than her, against her endurance. What sets it apart from a submission (pain against her
  will) and a pin (a clock) is that it goes mostly by the squeeze and her energy left to fight it (struggling spends
  it). Her health and the coiled parts still count, but less than in a submission.
- Past her endurance she may black out. As the grey closes in, panic can make her tap too.
- Measured with Seraphina's upright coil on Ripples, no breaking free, 20 fights each:

  | Ripples | Beats until it ends |
  |---|---|
  | fresh | about 10 (a plain submission: 10) |
  | half health | about 8 |
  | half health, energy 40 | about 7 |
  | a quarter, energy 30 | about 6 |

  Most end in a blackout.
- The story is told in stages, in the order it really goes: her heart pounding; then slowing and stumbling, her head
  swimming, pins and needles; then slow and uneven, the grey closing in. The blackout is told as the blood ("no
  gasping for air"), and when the coils come off, her blood coming back: her heart catching and racing, her head
  pounding, the tingling, the grey draining away.
- Rough numbers on the screen (never in the prose, never rolled against): heart rate and blood pressure, rising at
  first and then falling, irregular once her heart begins to slow (`constriction.vitals`; resting rates in
  fighters.json `heart_rest`: Ripples 140, Nerine 120, Nocturne 110, Seraphina 60).
- The tap meter's chance is now of the hold ENDING this beat, a tap or a blackout, with each shown beside it. It also
  shows the blood flow cut off and her heart and blood pressure.
- Coils on her neck are still a choke; on a limb they bind it.

Fixes from the played log:
- A serpent "standing tall" or with a "stance" is caught even in a sentence naming both fighters.
- Two fighters locked in a hold get no thoughts about footwork or the next blow ("Make her turn. She hates turning."
  inside Seraphina's coils).

## Build 284
The tap meter follows the real chance now. Ripples read "at the edge of tapping, 0% chance this beat": her pain
was far past what she could bear, but the chance was 0.3% (the hold's third beat, x0.06 while it builds; still on
her feet, x0.35; stubborn, x0.6), shown rounded to 0. The steps and words now follow this beat's chance (a tap is
far off, a small chance, a real chance, close, at the edge), the line under it says when the pain is past what she
can bear and what keeps the chance down, and a small chance is shown as it is (0.3%), not 0%.
`window.hold_panel.meter_by pain` brings back the old steps.

## Build 283
Fixes from the first real run of the setup questions:
- After you chose the fighters, the later questions still looked at the old fight: the players question offered
  Nocturne, Ripples, Nerine and Seraphina for a Seraphina vs Ripples fight. They now follow the fight you chose.
- Choosing the fighters no longer prints the fight's banner and "Press Enter to begin." in the middle of the
  questions; it says who fights, and the fight is shown in full when the questions end.
- The dice question says the mode that is set (it said "Enter keeps fair" when free was set).
- With the opening passage off, the fighters you play are asked from the very first beat (the director used to take
  the first beat as if nobody were playing).
- A hold's words no longer tell blows the engine never resolved. Seraphina's upright coil was labelled "whips
  Ripples with the tail, and charges her into a tall pine, then presses her into the beach": none of it happened
  (the director was nudged towards a charge and wrote it into the hold's words instead). Those clauses are now cut,
  and when no grip is left in the words the engine names the hold itself (`holds.unrolled_words.blows`).
- A beat of grips alone with "the impact came first as a dull thud" in it is caught and written again: no blow
  landed.
- The story blocks for blows thrown at no distance ("short strokes, elbow to wrist") are offered only to fighters
  with arms: Seraphina was given one for a coil.

## Build 282
Setup questions before a run, match presets, an anything-goes match, and a fuller help with examples.
- **The setup questions** (`setup`, on by default). Before a run begins, the game asks one short question at a time:
  - **Where and who:** the arena; the fighters; which version of a fighter, when she has more than one; whether you play as one fighter, several or all, and then with which dice.
  - **The match:** the opening passage on or off; the kind of match; how many taps win (in a submission match); how often pin openings come (when there are pins).
  - **The story:** the plan (close, dominate, comeback, winner...); where attacks aim; how many parts an attack catches; why they fight.
  - **Balance:** about how many beats the fight runs; the damage scale.
  - **The writing:** traits and quirks on or off; personality and history on or off; swearing; gore; how much is written each beat; the arena acting by itself; Venice (when you have a key).
  - **Anything else:** any /commands you like; then Enter to go beat by beat, or a number of beats for the director to run on its own.

  Enter keeps what is set at every question, and any /command works at any of them. At the first question, Enter skips them all, a preset name or number asks only the arena, the fighters and how you play, and `o` goes through the lot. `setup.questions` lists them, so you can drop any. `/set setup.enabled false` goes back to only the arena question.
- **Match presets** (`presets` in rules.json, `/preset`). Each sets several /set lines at once and keeps them:
  - `submission`: only a tap-out or a pass-out ends it.
  - `submission3`: won by the third tap, from three different parts.
  - `knockout`: only a knockout blow ends it; no pins.
  - `pins`: a pin held to its end, or a knockout.
  - `anything`: a knockout, a pin, or a tap-out, whichever comes first.

  `/preset` lists them, `/preset knockout ?` shows what one would change, and `nosave` makes it last this session only. You can add your own.
- **Anything goes** needed one new switch: `finish.submission.allow_knockouts` (off by default) lets a knockout blow end a submission match. The anything preset also sets `submissions.becomes_pin_after 0`. Without it, a submission held four beats turned into a pin before a tap could come, so no fight ever ended in a tap. In the no-model simulation, pins still finish most of these fights: when she can't break a submission, the holder may let go and pin her, and the stand-in nearly always does. The director is told that any of the three endings counts.
- **Help.** `/help examples` is new: ways to do common things, start to finish (a whole fight, steering it, playing a fighter, exact attacks, holds and pins, Venice polish, finding and changing a setting, fixing a beat, a balance check). `/help presets` is new too. `/set` now has a page of examples, `/plan` explains every shape (with what dominate does), and the switches list starts with the presets. Every example was run against the game, and a test now fails if a command has no help or an example names something that isn't a command.

## Build 281
Personality in the prose: who each fighter is, for the narrator and for Venice, and a Profiles window to edit it.
- **Personality, history and relationships** (`narration.character`, on by default; each part switchable). New fields in fighters.json, drafted from your descriptions for Ripples, Nerine, Nocturne and Seraphina (edit them freely):
  - `personality`: how she thinks and behaves.
  - `history`: her past, as far as the story may use it.
  - `veteran`: she has fought before.
  - `relationships`: what each other fighter is to her.

  The narrator gets them with her description and voice. A relationship is given only when both fighters are in the fight.
- **Venice gets them too.** Each fighter has a CHARACTER line in the polishing request, along with an instruction to give her thoughts, manner and movement that personality, without ever adding an event. The instruction is in the request itself, so it also works with your own polish prompt. `narration.polish.character false` leaves it out.
- **Quirk moments.** When one of her quirks decides something, the story is told in one line, to show in what she does. The screen shows it with a ✨. The moments:
  - Ripples' stubbornness keeping her from tapping, and a hold she has never met.
  - Nocturne's ambush striking the moment the other is caught open.
  - Seraphina's huge wind-up being seen coming, or landing like a falling tree, and a blow that would stagger anyone else barely moving her.
  - Nerine working close in.
  - A patient constrictor taking the knot.
- **Veterans may remember.** The program normally cuts memories of earlier fights ("she had faced worse before"). Now a fighter with `veteran: true` keeps hers. Nerine, Nocturne and Seraphina are veterans; Ripples is new, so hers are still cut. The narrator is told she may remember only what her history gives her.
- **Profiles window.** The Profiles button opens a tab for each fighter in the fight. You can edit her personality, her history, whether she has fought before, and what each other fighter is to her, and read her traits, quirks and style. Save writes it all to fighters.json, and the story uses it from the next beat. In the console, `/profile [name]` shows the same.

## Build 280
Traits and quirks: how each fighter fights. Ripples, Nerine, Nocturne and Seraphina are rewritten from your descriptions.
- **Traits** (`traits`, on by default) are set per fighter in fighters.json. Each is a multiplier on today's rolls, 1.0 = as before:
  - `speed`: her dodge, her counter after a dodge, meeting a move with her own.
  - `hold`: how hard her grips bite, and how hard they are to break.
  - `escape`: her chance to break a hold or escape a pin.
  - `toughness`: how easily she is staggered or rocked.
  - `stamina`: what her moves cost her.
  - `striking`: landing where she aims, and her chance of a devastating blow.
  - `learning`: at 1.4 or more, she reads a move after seeing it once, not twice.

  Fighters without traits are unchanged. The roll lines show a trait when it changes a chance ("(speed ×1.25)").
- **Quirks** are named rules of her own, each switchable in `traits.quirks`, with its numbers and an explanation there:
  - stubborn, out_of_depth, cocky, water_born.
  - ring_sense, clinch_fighter, works_the_hold, predictable.
  - weak_paw_grip, disaster_sense, ambusher, hates_water.
  - overwhelming, patient_constrictor, unshakeable.
- **Style and favourite moves.** Each fighter has a `style` sentence and a `favors` table (move → how much she prefers it). The director is told both, and `/simulate` picks moves by them.
- **/traits [name]** lists a fighter's traits, quirks, style and favourite moves.
- **The four fighters:**
  - **Ripples** is young, fast, energetic, a quick learner and a little cocky, with a varied style.
    - Traits: speed 1.25, stamina 1.15, learning 1.5, toughness 0.95, escape 0.8.
    - Quirks: **stubborn** (holds out against tapping longer), **out of her depth** (bad at escaping holds at first, better with each one she's caught in), **cocky** (after a good hit she sometimes overreaches), **water born** (quicker and slipperier in the water).
    - Her description and voice are rewritten to match, for both versions of her.
  - **Nerine** is young but experienced: a grappler and brawler, less varied, sure of what she does.
    - Traits: speed 1.1, toughness 1.05.
    - Quirks: **ring sense** (rarely gets sloppy when tired), **clinch fighter** (more free blows while she holds), **works the hold** (her holds build faster), **predictable** (opponents read her moves sooner).
    - She favours tail binds, pins, chops, bites and Aqua Tail, and seldom uses ranged moves.
    - Her description and voice are rewritten.
  - **Nocturne** fights dark and close, with her jaws; she has few holds, because her paws aren't made for gripping.
    - Traits: speed 1.3, striking 1.35, escape 1.15, toughness 1.1, hold 0.75.
    - Health: 1680 → 1800.
    - Quirks: **weak paw grip** (paw grips are weaker and easier to break; jaw grips are normal), **disaster sense** (devastating blows land on her less often), **ambusher** (Sucker Punch and Night Slash land devastatingly far more often on someone caught open), **hates water**.
  - **Seraphina** is graceful, confident and overwhelming: very big attacks and constriction.
    - Traits: hold 1.2, toughness 1.25, escape 1.1, speed 0.85, stamina 0.9.
    - Quirks: **overwhelming** (her big moves hit ×1.06 but are easier to dodge), **patient constrictor** (stronger in a contest of coils), **unshakeable**.
    - Her tells now say she shows very little until she is badly hurt.
- **Balance** (simulated, traits off → on):

  | Pair | Traits off | Traits on |
  |---|---|---|
  | Nocturne vs Ripples | 57% | 58% |
  | Nerine vs Ripples | 54% | 59% |
  | Seraphina vs Ripples | 80% | 87% |
  | Nocturne vs Nerine | 61% | 62% |
  | Nocturne vs Seraphina | 31% | 32% |
  | Seraphina vs Nerine | 86% | 81% |

  Ripples' traits were set once from your description and never tuned; everyone else was tuned around her. A larger-strengths-with-costs approach (Seraphina's big blows at 1.25× but costlier and easier to dodge) was discussed and kept for later.

## Build 279
The contest of coils, writing for constriction and for serpents coiling serpents, and the narration slips left over from the build-276 played log.
- **The contest of coils** (`holds.coil.contest`, on by default). When two fighters are coiled round each other, each beat after both coils have been on for a beat:
  - Both spend 4 energy, and 35% of the time neither gives (`stall_chance`).
  - Otherwise one out-coils the other. The chance goes by each one's strength, her size (to the power `size_weight`, 0.5), how much energy she has left, and adrenaline.
  - The loser's coils are forced off her. The winner's tighten by 3 and take over: the loser gets no roll to break them that beat.
  - Seraphina (6.2 m) wins 59% of the contests that are decided against an Arbok (3.5 m).
  - The screen shows "🐍 ... out-coils ..." or "strain coil against coil". The narrator gets a note for each outcome, and the director is told that a serpent wound in another's coils can wind her own back round her.
- **Writing for constriction, by how many coils and how hard.** Story blocks have three new conditions:
  - `coils:` one, two or many coils on her.
  - `squeeze:` light, firm or crushing, from the grip's power.
  - `body:` serpent, when the one in the coils is a serpent herself.

  The library now has:
  - Blocks for the one in the coils (`constriction`), for the one squeezing (`coiling`), and for the contest (`coil_contest`: stall, or won from the winner's and the loser's side).
  - Finished story lines for all three.
  - Sample passages (style_sample_scenes.txt): one or two coils, many coils crushing, a serpent in a serpent's coils, a contest where neither gives, and two where one wins (one of them won by the smaller serpent).
  - A crushing squeeze (power 22 or more) asks for the "coil crushing" passages first. A contest asks for "coil contest stall" or "coil contest won", as the beat went.
- **A serpent that "stood firm" is caught**: she holds her ground on her coils, rears, or braces.
- **One tail told as tails is caught** ("Seraphina's tails hung lower"), for any fighter with one tail.
- **The get-up told out of order is caught.** "Up onto her hands and knees, then rolled onto her front" is wrong when she rolls onto her front first.
- **A grip told as still on after she tore free is caught** ("The Milotic's coils were still tight around Ripples' middle", after Ripples wrenched loose).
- **A bite made up during a hold is caught.** During a hold, a bite was let through as part of the struggle. Now it counts only if the one biting holds with her jaws. Ripples, wound in coils, "bit at the coils, her teeth sinking into the scaled flesh".

## Build 278
Fixes from the build-276 played Ripples vs Seraphina log, Buizel ribs and flanks, and big blows that carry on into her side.
- **Buizels have ribs and flanks.** Ripples (both versions) and Nerine now have Left and Right Ribs (88), the side of the chest, and Left and Right Flank (83), the soft side below them at the waist. Over 400 simulated fights Nocturne still wins 59.5% against Ripples (59% before), so nothing else was rebalanced. Your clicked part points (images/anchors.json) don't have the new parts yet: their marks go where the picture's outline guesses until you place them.
- **A big blow on the shoulder or upper arm carries on into her side** (`moves.side_spill`, on by default). A blunt blow or a blast of 30 damage or more that really moves her (it staggers her, launches her, drives her back in a charge, or rocks her hard) also hits the ribs on that side at 0.35 of its power, and the flank below them half the time. Bites, claws and blades stop where they land. The screen says "The blow carries on into her side", and the narrator is told it is the same blow moving her.
- **A squeeze with nothing held yet starts the grip.** "Coils around Ripples' midsection and constricts" came back as an adjustment of a hold that wasn't there, and the beat was refused ("'hold_adjust' needs an active hold"). It now starts the coil on the parts it names, or on her middle.
- **Your fighters' orders keep their kind.** "Does nothing", "I get constricted" or "I am constricted and cannot do anything" is a beat of doing nothing: no struggle, no break-free roll, no pin escape. Ripples had torn free twice while you had her do nothing. An order for a coil, a wrap or a squeeze gets a grip, not a tail strike. With an attack in the same order ("a Hydro Pump on her stomach and then I coil around her midsection"), you get both.
- **`/play dice free` on both sides no longer breaks every hold.** A dice-free fighter breaks any hold she tries to, except one from a dice-free holder.
- **A left-out passage is put into the past tense** like the rest ("Ripples' paws scrabble at the ground... she pries the tail fan off"). More verbs are known to the program's own tense swap.
- **Square brackets on a command count as quotes**: `/sustain Seraphina Ripples "Hydro Pump" 4 [Tree] [Stomach, chest]` now hits the stomach and chest. Before, the parts were dropped and the blast went anywhere.
- **A plain word for a kind of thing means the arena's own one**: "Tree" in the lakeside clearing is the old oak, not a new surface called "Tree". The same goes for rock, stone, wall, log, post and pillar.
- **A big serpent's tail fan binding an arm is a coil round her middle.** "Seraphina's tail binds Ripples' left upper arm, with her broad iridescent tail fan" was a clamp on one arm. A serpent many times her size has nothing to grip with but her coils, so the grip goes round her middle, with the arm bound in under it half the time.
- **No claws for a body with no limbs.** The library line "Her claws slid out and stayed out." was given to Seraphina.
- **"IOStream.flush timed out" in Spyder.** The window skips flushing Spyder's console from its own threads. Since build 269 it recognised that console by one attribute, which newer consoles (IPython 9 in Spyder 6) may not have. It now also knows the console by its type.

## Build 277
The four leftovers from the build-273 lakeside log, fixes from the build-275 Seraphina vs Ripples log, and a stronger `/plan dominate`.
- **`/plan dominate` makes the opponent rarely fight back** (`director.plan_dominate`, on by default). The opponent gets a beat of her own only 15% of the time (`rival_turn_chance`). On the other beats the director is told the beat belongs to the winner, and the winner gets that beat's big-moment idea. If the director still gives the opponent an attack on her, it becomes a struggle against the grip on her, or a step back. Her chances to fight back on the dice (dodging, countering after a dodge, meeting a move with her own, breaking a hold, escaping a pin) are multiplied by 0.4 (`defence_mult`). A direction you type yourself is never changed.
- **Serpents need fewer different parts for their taps** (`finish.submission.taps.serpent_different_parts`, 50 by default). In a match that needs several taps from different body parts, a Milotic or an Arbok has no limbs to put in a hold. A serpent now goes by this lower percentage: with 3 taps, two different parts are enough. `null` = serpents follow `different_parts` like everyone else.
- **Blood in the mouth only for the one who bit.** In the lakeside log, Nocturne tasted blood when only Ripples had used her teeth. Each fighter's own weapons now count, not the whole beat's.
- **"For once" is cut on the first beat**, where she has no past to measure against.
- **Landing or lying on her side is caught** when the engine has her face-up or face-down.
- **A fighter's colour changing is caught** ("Nocturne's colour was changing").
- **A kept hold is named for what holds.** "Hold kept: Ripples' Right Forearm Fin on her right hock" was shown while her twin tails held it. A hold line that names one of the holder's own parts as the grip, when no grip is made with it, is rebuilt from the grips.
- **An attack told without a part named counts as told.** "The water hit, spreading across Ripples" is the Hydro Pump. Before, beat 1 got an extra passage for an attack that was already there, so it was told three times.
- **A sentence told again with the names and pronouns swapped is cut** ("She watched as the water hit, spreading across Ripples..." then "Seraphina watched the water hit Ripples, spreading across her body...").
- **No balance or stance line for a fighter on the ground or in a grip.** The program had swapped in "She tested her balance, found it, and kept it." for Ripples, who had just been knocked flat.
- **Standing firm is caught for the one a blow knocks down** ("Ripples stood firm, her feet planted").
- **Coils squeezing with no coil on are caught.** In beat 2, Seraphina's coils "tightened around Ripples, squeezing her ribs", one beat before the coil crush began.
- **A serpent with legs is caught** ("She kicked off from the solid ground" for a Milotic).
- **Trapped arms stay trapped.** With her arms pinned inside the coils, Ripples "clutched at the coils with her webbed paws". That is caught now, and the note says plainly that her arms strain and can't come free.
- **A drag at the water's edge goes over the wet sand**, not the root-knotted ground at the treeline. Seraphina was in the shallows.
- **A paragraph cut off on a comma** ("This is mine, she thought,") gets its full stop.
- The library line "the way an animal does when it understands it is caught" became "like a caught animal". Turning it into the past tense had left it half in the present.

## Build 276
Fixes from the build-273 lakeside Ripples vs Nocturne log.
- **The arena question ends once a fight starts.** Typing /newfight or /auto at the "Scene>" question played the fight inside the question, so "(Now the arena: ...)" and "Scene>" came back after every beat. Now the question closes as soon as a fight starts from it.
- **Commands joined with `&&` run one after another.** For example, `/stop && /plan dominate Ripples`. Before, only the first one ran.
- **A left-out passage never retells a get-up that was already told.** In beat 4, a short passage written for something the drafts missed retold Nocturne sinking back and rising again. Another passage, added after she stood, had her on her back. Now such a passage loses its get-up sentences, and it goes in front of the sentence where she rises.
- **A grip told with a limb that holds nothing is caught.** For example, "her webbed paws curled tightly around Nocturne's leg" when only her twin tails hold the hock. The check now also knows "Nocturne's leg" for a grip on her hock, and "curled around" as a grip.
- **A standing fighter told lying down is caught**, as in "her back coming off the ground", "the grass beneath her back" and "wouldn't put any weight through it to rise". "The hurt leg lay still" no longer counts as her lying down. That false match had also counted as showing Nocturne crumpling at the oak, so the missing crumple went uncaught. It must now come after the passage reaches the oak.
- **Forelegs given to a biped holding on are caught** ("her forelegs straining with the effort of maintaining the grip").
- **A fur colour nobody has is caught.** "The dark fur" in a fight between a white Absol and an orange Buizel is flagged. Each fighter's fur colour comes from her appearance.
- **Memories from before the fight are caught**: "honed from countless battles", "she had been in worse situations before" and "when stalking prey in the river".
- **A hold she wrenched out of is not told as the holder letting go.** Before, the story could say "Ripples' twin tails releasing their grip" when Nocturne broke free with one hard wrench.
- **A biped's kick is her foot.** The director's "Ripples drives her right paw" for a kick now says "her right foot".

## Build 275
- **A serpent many times her size coils her middle, not one of her limbs** (`holds.coil.size`, on by default).
  - A Milotic's body is thicker than a Buizel's arm, so it can't wrap that arm alone. A coiler with no limbs (Milotic, Arbok) that is at least `ratio` (3) times her length wraps her belly or chest first, at the full pressure the director asked for.
  - The arm, leg, tail or neck it aimed at stays bound in under the coils half the time (`limbs_too`); otherwise it slips free.
  - A grab with its coils becomes a loop round her middle. An invented submission keeps its limb, worked from coils round her middle. A coil already round her middle is left alone, and grips can be added to it. Your own commands are never changed.
  - Sizes are in metres, by species or fighter name (`sizes`). A Milotic (6.2 m) dwarfs a Buizel or a Charizard, but not a Dragonite (2.2 m). An Arbok (3.5 m) dwarfs a Buizel, but not an Absol.
  - The director is told about it, so it plans coils round the middle.
  - Wound round the middle by such a serpent, her chance to wrench or buck free is x0.6 (`escape_mult`). Before, a Buizel had about a 64% chance a beat to buck a fresh Milotic's coil pin off.
- **Her arms trapped in coils round her body: nothing needs a free paw.** Before, a Buizel in a Milotic's coil crush was told raising a paw to tap and yanking it back, with her arms pinned inside the coils.
  - The signs of fighting the tap are now picked from the ones without a paw (her breath, her eyes, a word she swallows, her tail).
  - The tap itself is her tail slapping, saying it out loud, or going slack and crying out that she is done.
  - The ladder of how hard to tell it has its own wording for this.
  - What she tries to get out of a serpent's coils is a set of its own: going small and sliding down, arching against the loop, working a shoulder free, biting the scales. It no longer has her getting both paws on the grip.
- **The narrator no longer gives a serpent feet, limbs, an arm or a shoulder.**
  - Drawing a hold's position, a Milotic "has her head and forebody raised off the ground", not "on her feet", and "her coils, head and tail" do the gripping, not her limbs.
  - A tap on a standing serpent lands on her coils, not her arm or shoulder.
  - Her struggle claws at "the coils", not "the gripping limb".
  - After a tap she draws her coils back and rears over the loser.
- **A one-grip hold that wraps the very limb it grips with is a coil.** "Wraps her twin tails round the tail", with "her twin tails", used to count as a plain grip. Now it binds or constricts like any coil.
- Constricted, her stamina line reads "short of breath: the coils squeeze every breath short", not "no breath in her right now" (that one is for the wind knocked out of her).

## Build 274
- **The tap meter now shows every hold that counts toward a tap, from its first beat.** In a submission match a squeeze, a crushing headlock, a coil or a held bite counts toward a tap, not only a named submission. Before, the meter only appeared for those holds on their second beat. Now it shows on the first beat too, with "first beat in it: she can't tap yet, but this hold counts toward one". Nothing extra is narrated that beat (`finish.submission.tap.meter_all`; false = as before).
- **A grab that can't make her tap yet says so on the hold panel.** For example: "a grab: no tap until it is 100% hurt (now 42%)". A grab only counts once the part it holds is hurt that badly (`tap.grabs.min_damage`), or once her health is gone. Until then no meter appears for it.

## Build 273
- **The full polish checks now survive closing the game.**
  - What the narrator knew about each beat is saved in the polish_states folder, one small compressed file a beat (about 30-40 KB).
  - Only the last 3 fights are kept (`narration.polish.keep_fights`). Older fights' files are removed as new ones come, so three 40-beat fights take about 4-5 MB.
  - A polish pasted back after a restart gets every check, the same as one pasted right away. The folder is left out of git.
- **Cards − and Cards + above the fighter cards** make them smaller or bigger, 10% at a time from 40% to 160%, so both fit on one screen. The size is kept for next time (`window.card_zoom`).
  - At 100% the cards are drawn as before.
  - At any other size, each card's pictures and labels are drawn the way the exported fight draws them, then scaled. The bars underneath shrink to the same width.
  - Placing a part's point by clicking uses full size for that card.
  - The story text has its own A− and A+, as before.
- **The exported fight's pain gauges no longer hide their text.** Each label sat below its bar and was cut off at the bottom. Now it sits inside the bar, and a long one wraps onto a second line. `/exportfight` writes a fight again with the fix.
- The polish copies no longer include the cleanup's record of the notes' wording, which grew every beat and isn't used by the checks.

## Build 272
- **No limit on beats kept for polishing.** Every beat of a fight is kept, however long it runs (`narration.polish.history` 0). A number there keeps only that many of the latest.
- **Earlier beats get the same full checks as the latest.** With each beat the game keeps a copy of what the narrator knew about it (its facts, grips, hits, who got up, the tap). When a polish of that beat is pasted back later, the checks run as they would have then, then the narrator is put back. That copy stays in memory, not in the save, so beats from before a restart get only the label, fighter, length and hit-part checks. The game says so when that happens.
- Fixes from your fight so far (Nerine vs Ripples, 22 beats):
  - **Beat 7:** the tap count's steering moved Nerine's tail grip from Ripples' left knee onto her tails (the part being worked), but the words still said "around Ripples' left knee". A grip moved that way now has its words put right too, as a blow already did.
  - **Beat 10:** Ripples' free blow during the chicken wing was a Water Gun to Nerine's throat while Nerine lay face-down, with her throat against the ground. Face-down, a free blow no longer finds her throat, stomach or chest; face-up, it no longer finds her back.
  - **Beat 7 story:** "the space between them, unchanged, a few paces of grass" while Nerine's tails held Ripples'. A new story check (`narration.story_checks.locked_gap`) catches a distance told while a grip joins them.

## Build 271
- **Polish several beats at once on Venice's website.**
  - `/polish copy 5-9` copies beats 5 to 9. You can also use `/polish copy 7`, `/polish copy last 4` or `/polish copy all`.
  - Each beat goes into one request between `=== BEAT 7 ===` and `=== END BEAT 7 ===` lines, with its own facts.
  - Paste the request into a new Venice chat, put the whole answer into polish_reply.txt, and type `/polish paste`.
- **Each answer goes back to its own beat by that number.** It's checked and kept or not by itself, and it replaces the beat in the story the models remember and in the saved and exported fight. A beat missing from the answer is simply left as it was.
- **An answer with no markers** can be put on a chosen beat with `/polish paste 7`.
- **The game keeps the last 40 beats for this** (`narration.polish.history`), saved with the game, so a restart doesn't lose them.
- **One request holds up to 6 beats** (`batch_max`), because a chat window may cut off a long answer.
- Earlier beats are judged by the label, fighter, length and body-part checks. The program's sentence checks only know the latest beat, so they're used for that one alone.

## Build 270
From comparing three of your Venice polishes. The prose came out better each time, but Venice was editing line by line and kept every mistake the draft had.
- **The built-in polish prompt now tells Venice to put the draft's mistakes right.** It tells one blow once (your third sample told the Ice Fang twice). It gives each attack to the right fighter and limb ("Nerine's jaws ground down on Ripples' paw" when Nerine only kneed). It leaves a grip on when the facts say it's still on ("Ripples' grip opened" while her tails still held Nerine's nose). Anything the draft has happen that the facts don't support goes. Before, "never move or remove anything" stopped it from fixing any of that.
- **Less chopped-up prose.** Venice is told to write mostly full sentences rather than strings of fragments ("Muscles taut. Joints strained. Clarity. Control."), and to go easy on dashes.
- **The fact sheet now covers grabs, dodges, throws, slams, drags and pins.** Your second sample had no line at all for Ripples grabbing Nerine's nose, so Venice had nothing to check it against.
- Your own prompt in polish_prompt.txt isn't changed. `/polish prompt reset` picks up the new built-in one.

## Build 269
Fixes from the first real Venice polish you tried by hand. Its version was better, but `/polish paste` would have thrown it out twice:
- **A part label that lost a dash** ("Nerine —" instead of "— Nerine —") is put right, and text from the chat page that got copied along with the answer ("Worked for 22s · 1 step") is cut. Before, that counted as "it changed the part labels".
- **Cutting filler is allowed.** The shortest kept length went from 70% to 55% of the local beat (`min_ratio`). Venice cut 770 words to 485, nearly all of it the repeated sun, breeze and heartbeat lines. The editor is now told it may cut filler freely but must keep every event and concrete detail, and not go below about two thirds.
- **A body part a blow landed on must still be there.** If the local beat tells it and the polish drops it, the polish is thrown out. This is the guard that goes with letting it be shorter.
- **The fact sheet now says what each move is and when a blow landed off target** ("Knee Kick is ...", "aimed at her left paw, landed on her left upper arm"), so the editor doesn't keep a fist in a knee kick.
- **The editor is told to go easy on dashes** and use commas and full stops like the rest of the story.
- **Your own polish prompt.** `/polish prompt` shows the instructions Venice gets. `/polish prompt edit` puts them in polish_prompt.txt and opens it for you to change; the next polish uses your version. `/polish prompt reset` brings back the built-in one. The game still adds the facts and the beat after your instructions.
- **Venice now gets each fighter's condition.** The fact sheet gives her health, her pain overall, and her four worst-hurt parts in the story's pain words with their damage ("left upper arm very painful (95%)"), so every hurt is sized right (`narration.polish.condition`). It also says whether each fighter is fresh, hurt, worn down or nearly spent.
- **Venice now has everything the local narrator knows about the scene.** The fact sheet starts with WHO each fighter is (her appearance from fighters.json, whole sentences, so it gives her only the body she has: no flotation sac on a Buizel, the notch in Nerine's fin) and WHERE they are (the arena). It ends with her statuses (soaked, chilled...), the tap count in a match of several taps, and how far apart they are (`narration.polish.setting`, `look_chars`, `place_chars`). The story just before the beat was already in it.
- **No more "how much did Ripples have left in her?" on the opening beat.** A new story check (`narration.story_checks.fresh_worn`) catches a fighter still fresh (`fresh_from`: 85% strength) being told as tiring, fading or running out. It works on the local model's own draft, and Venice is told to cut such lines too.
- **"IOStream.flush timed out" in the Spyder console.** These came from the window asking Spyder's console to flush, which it already does by itself. They were harmless, and the window no longer asks.

## Build 268
- **A stronger online model can polish each beat** (`narration.polish`). It's off until you turn it on.
  - The local model writes the beat as always, with the engine and every check behind it. Then the finished beat and a short fact sheet of what really happened go to an online model to improve the prose without changing events.
  - Venice.ai is the default service. Any service that uses the OpenAI chat format works (`base_url`).
- **Only a polish that passes the checks is kept.** It is thrown out, and the local version stands, when it:
  - is a refusal,
  - drops or changes a "— Name —" part label, or leaves out a fighter,
  - is much shorter or longer (`min_ratio`, `max_ratio`),
  - or gets more wrong by the program's own sentence checks than the local version did (`allow_new_slips`).
  - The game says which reason it was, and `/compare` shows both versions of the last beat.
- **Setting it up:**
  - `/polish key <your key>` saves the key to polish_key.txt. That file is left out of git and never goes in rules.json. You can use the `VENICE_API_KEY` environment variable instead.
  - `/polish models` lists the service's models, and `/polish model <name>` picks one. A larger model edits better.
  - `/polish on` turns it on. `/polish when big` polishes only taps, knockouts, the finish and other big moments, which uses fewer requests.
  - `/polish now` polishes the last beat on demand.
- **By hand, without an API:**
  - `/polish copy` puts the whole request for the last beat in polish_request.txt and on your clipboard. Paste it into Venice's chat.
  - Copy its answer into polish_reply.txt, save the file, and type `/polish paste`.
  - The same checks decide. The polished beat replaces the old one in the story the models remember and in the saved and exported fight, and the fight carries on in the game and its window.

## Build 267
- **New story checks** (`narration.story_checks`, each one switchable). They catch mistakes the model made in the saved fight even though the notes had it right. A paragraph caught by one is written again with the mistake named.
  - `getup_order`: a failed try at getting up told after she is already up. In beat 10 Ripples stood, then "her third attempt to rise was no more successful than the first two".
  - `after_tap`: the holder still pressing or striking after the tap. In beat 22, "Nerine's knee drove into Ripples' right shoulder" came after the tap. The tap ends the grip, so the rest of the beat is told before it.
  - `bite_place`: a bite told landing somewhere it never touched ("her teeth sank between the toes" for a bite on her back). A part next to where it landed is fine.
  - `move_names`: in beat 4, "Nerine's Aqua Jet" when she threw a Water Gun and had never used Aqua Jet. This one is fixed with no model call, and only when she used just one move that beat.
  - Tested on the saved fight's own story: they catch those three beats and flag nothing in any other beat.
- **More in the writing libraries**, mostly where they were thinnest.
  - story_blocks.txt: 8,951 → 9,343 ideas. The submission and tap groups doubled or tripled; for example, `sub_lock_hold` went 7 → 24, `tap_after_held` 6 → 14 and `sub_hold` 17 → 36. Off-target blows, last stands, frenzies, sputtering, feints, juggles, crashes, collapses and a dozen more groups also grew.
  - story_lines.txt: 3,220 → 3,425 finished lines, again mostly the submission and tap groups, plus breath, resolve, closing lines, landings, pins, staggers and collapses.
  - story_passages.txt: 125 → 164 showpieces. Every group that had 3 to 7 now has 5 to 11.
- **New groups for moments that had no ideas at all.** Each is offered only when the engine says it is happening, and only from that fighter's side:
  - breaking out of a submission (`sub_escape_held`, `sub_escape_hold`, with finished lines too);
  - a choke from the inside, by how near the dark is (`choke_fight`);
  - an adrenaline surge or a second wind (`surge`);
  - her sight greying (`grey_out`);
  - running on nothing below zero (`running_on_empty`);
  - a failed try at getting up (`getup_fail`).
  - The switch is `narration.inner_blocks`. The choke and escape groups go with `narration.sub_blocks`.

## Build 266
Fixes from the saved fight (fight2_Ripples_vs_Nerine, 35 beats):
- **Beat 25 had no story because Ollama wasn't running.** The game couldn't reach it ("actively refused"), most likely because it crashed between the director and the narrator.
  - When Ollama doesn't answer at all, the game now retries five times over about a minute. Before, it gave up at once.
  - The exported fight now says why a beat has no story ("the narration failed (Can't reach Ollama...) and was never rerolled").
- **Limbs locked in her own hold can't strike as well** (`holds.busy_limbs`).
  - Nerine threw two Knee Strikes with both legs wrapped round Ripples in a triangle choke. Now that's refused, and the director is told to strike with something free.
  - Both paws in a chicken wing can't punch, and twin tails wound round a knee can't Aqua Tail. A grip with one paw leaves the other free. A Knee Strike now counts as a leg move.
- **No charge from inside a hold.** Nerine threw an Aqua Jet, a full-body charge, while holding Ripples in a chicken wing.
- **The holder's blows land near the hold** (`holds.holder_reach`). On Ripples' back in a chicken wing, Nerine bit her foot. A bite now reaches only one step from the parts she grips (`bite_near`), and a paw, knee or tail two steps (`strike_near`). Moves fired from a distance aren't limited.
- **The arm caught in a wrist lock doesn't throw the blow.** Ripples' Brick Break came from the arm Nerine had locked (×0.6 for that arm). A strike now comes from her free side.
- **A blow the director didn't name is named from its words.** Ripples' bite came out as "A Plain Blow". Now it's a Bite, and likewise a Kick, Knee Strike, Claw Rake, Tail Strike or Punch. The rules for that limb then apply to it.
- **Jaws added to a submission already on are rarer too** (`hold_mix.jaws`). The tail-bound knee crank grew "and jaws" partway through the hold.
- **A choke's pass-out counts for the neck.** The tail strangle's pass-out was credited to her upper back.
- **The stat line on a hold's first beat** said "far from her limit (pain 378 against her resistance 64)". Now it says "on the hold's first beat, before she can give in" when the pain is already past her limit.
- **Her own fall isn't a blow.** The injury report said her right upper arm "took Ripples' blow". That was her fall trying to get up, and it now reads "her own fall trying to get up".

## Build 265
- **Fewer chokes and jaw holds in a submission match** (`finish.submission.hold_mix`, on by default). They still happen, just less often than the usual locks on a limb, the back or the body.
  - A choke the director puts on (a named one, one of her own, or a hold on the neck) stands 35% of the time (`hold_mix.choke`). Once a choke has been tried in the match, it's half that (`after_first`).
  - A jaw hold (a bite clamped on and held) stands 50% of the time (`hold_mix.jaws`).
  - Otherwise the engine puts on a lock that fits instead, without jaws where one fits. The beat is then told with the lock's own words.
  - The submission openings pick a jaw hold half as often. The bite and choke ideas come 35% as often (`hints`). The director is told jaw holds are rare too.
  - Your own orders, and a grip added to a hold she already has on, are left alone.
  - In the log you sent, three of the six submissions were chokes (triangle choke, side headlock, tail strangle), although the director had been told after the first that one had been tried.
- **A choke on a fighter at zero health** read "air 2200% gone" on its first beat, because she had no endurance at all. She now always keeps some (`choke.endure_min`, 30).
  - "Air gone" on the meter now measures how close she is to blacking out for sure. It never shows more than 99% while she is awake. Before, it read 119% and 169% with her still conscious.
- **The tap meter says when the chance is still building**: "still building: up to 34% as it stays on". Before, it showed "very close to tapping · 0% chance" early in a hold.
- **A limb already gripping her can't grip her somewhere else too** (`holds.invented_check.same_target`). In the log, both of Nerine's paws were in a chicken wing, and "her paw and knee" still went on Ripples' thigh as well.
- **What grips her, in short**: the hold lines show "both paws, twin tails and her knee" instead of every grip's whole description strung together.
- **The fighter working a submission** shows "locked onto Ripples in her triangle choke, down with her" instead of "on her feet".
- **No more blank beats**: beat 25 of your log had no story at all. If the cuts leave nothing of a beat, the model's own telling now stands, and the failure goes in errors.log. If the telling still comes back empty, the game says so and /reroll writes it again.

## Build 264
- **The tap chance now comes from both the gripped part and her overall health** (`finish.submission.tap.blend`, on by default):
  - Fresh, with a ruined part in the grip: about 30% a beat once the hold has built up. She can fight it, but not for ever.
  - Worn out, with a healthy part: about 8%. That's harder than fresh, but still resistible.
  - Worn out, with a ruined part: about 85%. Fresh, with a healthy part: next to nothing.
- **There's a build-up.** She never taps on a hold's first beat. After that the chance is scaled up over 8 beats: 2% of it on the second beat, 6% on the third, 25% on the fifth, and all of it from the ninth.
  - The dice still decide every beat, so a quick tap is possible, just rare.
  - In 80 stand-in Ripples vs Nerine submission fights, holds that ended in a tap or pass-out had been on for a median of 6 beats and up to 10. Before, it was 4, with some at 2.
- **Chokes build up the same way** (`blend.chokes`). Before, a hurt fighter could black out on a choke's second beat.
- From `blend.near` she is shown refusing it, as near her limit. The meter's chance is now the real, climbing one.
- With blend on, the breaking point (`tap.overwhelm`, the "0% then 95%" jump), the climbing ceiling and the beat of holding on through it are not used. Set `enabled` to false to bring them back.

## Build 263
- **Holding herself back from tapping** (`tap_hold_back` in story_blocks.txt and story_lines.txt): what her body DOES to keep from tapping, offered every beat of a submission beside the engine's own sign and the thoughts: pressing her free paw flat against her side, grabbing a fistful of the fur on her own side and twisting it, digging her claws into her own flank, wedging her paw under her body and lying on it, clawing up a clump of grass and holding it crushed, gripping her own wrist and holding her paw down by force, clinging to the fur of the one holding her. By level (1-2, 3, 4-5: harder and more desperate as she nears the tap), by her body (arms, forelegs, a tail) and by whether she is down (the ground in reach) or on her feet (only her own body, or the holder's). None of them is ever a tap.
- The tap check reads "wasn't" and "isn't" as not a tap too.

## Build 262
- **Submission sells in the story libraries**: new material in story_blocks.txt, story_lines.txt and story_passages.txt, offered every beat of a submission beside the engine's own sign of the tap fight (her paw rising and yanked back), so it is the rest of it: her breath, her eyes, her thoughts, the sounds, what she is holding on for, and what the holder feels.
  - **The lock going on** (`sub_lock_held`, `sub_lock_hold`): the instant it locks, from each side ("she feels the angle more than the pressure at first: her left thigh turned one notch past where it goes").
  - **Her fight against the tap, by level** (`tap_fight`, tap: 1-5; about ten ideas a level and five or six finished lines): from "the urge to give in is there already, faint and far off, like a sound in another room" at 1, through "her thoughts come in short hard pieces: not yet, not to her, not like this" at 3, to "a part of her has already given in, and the rest of her won't let it" at 5. Two ideas a beat from level 3.
  - **The holder feeling it** (`tap_fight_hold`): "she can feel the trembling now, up through her own arms, fast and fine and getting worse".
  - **The tap** (`tap_out_held`, `tap_out_hold`): what finally breaks her, the act (on the ground when she is down, on the one holding her when she is on her feet), the shame and the relief; the holder feeling it and letting go.
  - **After a tap that doesn't end the match** (`tap_after_held`): "she has given once now, and she is not going to give the same thing twice".
  - **Showpiece passages** (`tap_edge` at levels 4-5, and `tap_out`): offered now and then for the moment itself, to draw on or to set in.
- **A tap check fix**: "the thought of giving in" no longer counts as her giving in (the regress check now reads every library line: a tap line has to show a tap, a tap-fight line must never).

## Build 261
- **Invented holds checked against what limbs can do** (`holds.invented_check`, on): every hold the director writes, and every submission it invents, is checked grip by grip, and a grip that can't happen is left off (a hold with none left is refused, and the director tries again). Trapped: a paw caught in the other one's grip can't grip back. Wrecked: a devastated limb can't take hold. Busy: one limb grips one part, a pair (both paws, twin tails) two, counting what it already grips on someone else. Reach: one limb can't grip her neck and her foot at once. An invented submission's main grip has to work a joint, a limb, the back, the tail or the neck, never an ear or a nose.
- **Words that match the grips**: a submission from the engine's own list told with a limb it doesn't use ("Nerine's twin tails wrap round her leg" for a heel hook turned with her arm and legs) is told in its own words. And the director's words for any blow or hold are put right to the parts the engine resolves (`director.words_to_parts`): told to work Nerine's right hip, it wrote "wrapping tightly around Nerine's left knee" three times in the build-260 log, and "Brick Break slams Ripples' head" for a blow to her right hip.
- **A head butt reaches what a head can** (`moves.head_reach`): thrown standing at a fighter standing, it lands on her head, neck, chest, shoulders, belly, back or arms; aimed at her foot, it lands on her chest.
- **No launch from a blow to the feet** (`moves.low_launch`): a blow whose main hit is on her lower legs or feet takes her legs out from under her (knocked down where she stood), and nothing catches her up in the air after it. In the log a head butt to Ripples' foot launched her for a Brick Break juggle.
- **Her fight against the tap, every beat** (`narration.tap_fight_shown`): each beat of a submission must show her fighting the tap, and the more it hurts the more of the passage it takes: at least 1, 2, 2, 3 and 4 sentences for levels 1 to 5. A draft that gives it less gets a short passage of its own; if that still leaves it out, the program tells this beat's sign plainly ("Ripples' paw rose toward the ground, shaking, and she yanked it back down to her side, hard, as if telling it no.").
- **Smaller fixes**: a grip told before a dodged blow that came first is moved after it too, and a blow told in its kind's words ("a high-pressure water blast" for Hydro Pump) is recognised; the same breather sent twice in one beat happens once.

## Build 260
- **Holds as bodies can do them** (`holds.backstop`, on): a press with something that only pushes (a chest, a side, a knee, an elbow, a head) hurts only when something behind her pushes back. That can be the ground she is down on, scenery she is driven into, or the holder's own arms, tails or legs wrapped round her body or neck, hauling her into it (a bear hug, a sleeper from behind: the chest is the anvil, at half its pressure). Otherwise the press is dropped. In the Ripples vs Nerine log, Ripples' chest "pressed" a standing Nerine's twin tails and shoulder in the open. Now that hold is her forepaws on Nerine's lower back and her twin tails on both forearms. A hold that is nothing but such presses is refused, and the director tries again. Weight bearing down counts as backed (gravity). The engine's own submissions were checked against the same rule, and each has a backstop: the ground, gravity, or a lever or wrap pulling the other way.
- **One hold, one body's strength** (`holds.grip_share`, on): one limb on several parts splits its pressure, every grip after the first is a lesser one, and a hold has at most 4 grips. The five-grip body lock did 36% damage in its first beat, three times the Aqua Jet before it; the same hold now presses at about a third of that.
- **The grip after the blow** (`narration.engine_mends.order`): a blow and then a grip from the same fighter, with the grip told first ("Her grip on Nerine was tight..." two paragraphs before the Aqua Jet it followed): the grip's paragraph moves to after the one where the blow lands.
- **Keeping her feet is shown**: when the engine rolls that she nearly goes down and stays up ("buckles at the knee, nearly touches down, and forces herself straight"), a draft that never shows it gets a short passage for it, like a left-out tap or fall.
- **Mends**: "It was a familiar sensation, but today it felt heavier" lost only "familiar" and read "It was a sensation"; the clause now goes whole ("Today it felt heavier"). The director's "secure a submission opening" reads "an opening for a hold". "Harmlessly" goes from a beat where the blow did damage (`engine_mends.harmless`).

## Build 259
- **The prose checked against the engine** (`narration.engine_mends`, on): after every beat and interlude, the finished text is held up against what the engine knows (each fighter's species and body, which parts are hurt, who holds whom and where), and the slips are put right in place, with no extra call to the model. From the build-254 Ripples vs Nocturne log:
  - **Who is who** (`species`): "The Buizel's fur was matted with sweat and dirt" told of Nocturne becomes "Nocturne's fur...". It changes only when the sentence says so: a part only the other one has, a hurt only she has, the other's grip, or, in a part told from the Buizel's own side, right after a sentence about the other alone. "The Buizel's own forearm fin" and "Nocturne glared. The Buizel stood tall" are left alone.
  - **The held part** (`grip_part`): "the twin tails whipped around Nocturne's right knee" when the grip is on her left forepaw is told on the left forepaw. Where it grips several parts, the nearest one on that side is used (a knee is the hock). Weight on a sore leg ("putting pressure on her right knee") is left alone.
  - **Who holds** (`roles`): "Ripples wriggled..., but Nocturne's grip was unyielding" when Ripples holds Nocturne: the two names trade places in that sentence.
- **Interludes don't retell their beat** (`narration.interlude.retold_cut`, 0.55): an interlude sentence that says again what the story just said in other words goes, along with a "But it..." leaning on it. Beat 9's interlude lost its five retold lines ("The breeze picked up again, carrying with it the scent of the pine needles and the lake") and kept the new ones.

## Build 258
- **Dark mode** (`window.dark`, on): the window in dark colours. Backgrounds go dark and text goes light. The blues, reds and violets that mark things go a shade lighter so they still stand out. The damage fill, the bars and the tap steps keep their colours. It is read when the window opens; `/set window.dark.enabled false` and reopen it for the light window.
- **Taps the story never showed** (from the build-254 Ripples vs Nocturne log): the taps at beats 18 and 25 counted, but the story never told them. The check took "it was not enough" and "I'll make her tap." as her tapping. Now a tap only counts as shown when it happens; one that is wanted, refused or still to come doesn't. A mid-match tap the drafts leave out is asked for once more, then written in.
- **A hold named for a part grips it** (`submissions.invented_fit`, on): the director's own "standing knee lock" went on Nocturne's left shoulder. A hold of its own invention named for her leg, arm, neck or tail is refused unless one of its grips is there, and the director tries again.
- **300%+ on the pain gauge** (`window.pain_gauge.show_max`, 300): once she is worn to nothing, what she can bear sinks to its floor and the share ran into the thousands (8920%). Past 300% it now reads "300%+: far past what she can bear".
- **Mends**: the model's "And now, to continue from where you left off:" (the end of beat 9's interlude) is taken out; a stray ", and" left by a cut sentence (". , and Ripples felt the tremor") is mended; and the fallback grip line no longer puts the holder's name in her own grip ("Then Ripples closed her Ripples' twin tails on...").

## Build 257
- **A tap meter on the card** (`window.hold_panel`, on; the window and exported fights): the pain gauge only says how much it hurts against what she can bear, not how close she is to tapping. Now, while she is held in a submission match, a TAP row under the pain gauges shows five steps filled to how near she is: the same ladder the narrator tells it by (1 holding easily, 2 getting to her, 3 close to her limit, 4 very close, 5 at the edge of tapping; a choke near her limit reads "fighting the dark"), coloured from yellow to dark red, with this beat's real tap chance ("22% chance this beat"). It says 0% on a beat she can't tap and why: her first beat in it, the first beat past her limit that she holds on through, or holding out at her breaking point (which stage). Under it: the hold, the pain against what she can bear, how many times she has refused, and air gone in a choke.
- **The hold panel**: who holds which of her parts, in what hold and with what ("Held: Nerine's boston crab on her left thigh, right thigh, lower back (her arms...), beat 5"), said when it is on her throat; the grips she has on others, with how near that one is to tapping ("· Ripples: at the edge of tapping, 22% to tap"); a pin's count against its length; and how far she is from each other fighter (build 255's distance).
- **Held parts ringed**: her parts in a grip get a violet ring on her picture, in the window and in the exported card images.

## Build 256
- **Fighting the tap all through a submission** (`finish.submission.tap.urge`, on): before, nothing about tapping was told until the pain reached `tap.near` (75%) of her resistance, so the first beats of a submission (and the whole of one on a part not yet badly hurt) showed no fight against the tap at all. Now every beat a submission is on, from the first, the narrator is told she is fighting the urge, with one sign of it picked by the program (never repeated soon): a fist squeezed so tight it trembles, a paw that lifts off the ground and is yanked back down to her side, claws dug in and held still, counting breaths and losing count. In other holds that hurt it shows on about half the beats (`urge.chance`) once the pain is `urge.from` (30%) of her resistance. It doesn't count as a refusal and doesn't bring the tap nearer.
- **One ladder, more visceral the nearer the tap**: each beat the narrator is also told HOW HARD to tell it, from 1 to 5, with what she looks like and what she thinks. 1: felt and held easily, a thought that she can take this. 2: getting to her, the paw starting to rise and pulled back. 3: near her limit, the paw shaking as it rises and yanked back to her side as if telling it no. 4: very close, the paw nearly there, cries she can't keep in, her thoughts down to single words. 5: the edge, the paw trembling over the tap, a plea in her head. 1-2 come from this build; 3-5 are the refusals near and past her limit (and the breaking point's last beats are always 5). Two new refusal signs: the paw yanked back as if telling it no, and a paw shaking so hard she drags it back by force.

## Build 255
- **The breaking point** (`finish.submission.tap.overwhelm`, replacing build 254's instant jump): once a gripped part is in horrible condition (`part_damage` 300, devastated) and the pain is past her resistance, the tap is coming, but not at once. First she holds out a few beats and cannot tap at all. How many comes from her: `hold_min` to `hold_max` (2-4), longer the more strength she has left (an adrenaline surge counts), with a little luck in it. Each of those beats the narrator is told how far her resistance has broken down: the first of it, cracking, or the last of it. The pain, the struggle, the tells and the refusals then show it giving way, and the story never knows how long she'll last. After that her chance is at least `chance` (95%) a beat. The count carries on through a regrip by the same holder. A part that isn't wrecked keeps the slow climb as before.
- **How far apart they are** (`narration.match_state.distance`, on): the engine keeps track of the distance between each pair of fighters: locked together, in reach, a few strides apart, or well apart. A blow that lands or is slipped leaves them in reach, a throw or a launch puts a few strides between them, a breather taken in reach opens some room (`breather_room`), a grip or a pin locks them together, and breaking out of one leaves them in reach. A ranged move changes nothing. The narrator gets a DISTANCE line in the condition notes and on the beat card, with how far apart they were when the beat began, so nobody "closes the gap" on someone already in reach. The director sees DISTANCE NOW. It is saved and undone with the fight.
- **The opening told as the opening** (`narration.match_state.fresh_is_early`, on): a few beats in with both fighters all but untouched (above 97%), the story notes no longer say "the middle: both have been hurt" (until beat 9).

## Build 254
- **Tap-outs under unbearable pain** (`finish.submission.tap.overwhelm`, on): the chance to tap climbs slowly over the beats a hold is on (20%, then +10% a beat). That climb was also capping a fighter whose pain was far past anything she could bear: in the build-253 lakeside fight Ripples, far below zero health, rolled at 26%, 35%, 39% and 50% with pain 754 against a resistance of 10, refused every time, and never tapped. Now, once the pain is `ratio` (4) times her resistance or more, the ceiling jumps to `ceiling` (85%). `enabled: false` puts back the old cap.

## Build 253

The rest of the build-251 Ripples vs Nerine log.

### The engine

- **No "shoves her back" break with someone lying down** (`holds.break.shove_needs_standing`). Ripples broke Nerine's
  tail bind by "shoving her back half a step" while Nerine lay face-down. That way of breaking free is now picked only
  when both of them are on their feet.

### The narration

- **A head snaps back only from a blow or grip on the head** (`narration.body_slips.head_snap`). When nothing reached
  her head, face or neck this beat, "her head snapped back" becomes "her head jerked back" (pain can toss a head; only
  an impact snaps it), and a "the force of it jolting through her skull" clause after it goes.
- **One rise, told once** (`narration.body_slips.one_rise`). Nerine got up once in beat 8, and the story told it twice
  in the same part ("pushed herself up onto her feet", then "with a final heave, she lurched upright"). The second
  telling goes.
- **Nobody favours a part nothing has hurt** (`narration.body_slips.favor`). "She's favoring something, maybe her leg"
  in beat 1, before any blow, and a fighter favouring the other's wounded thigh, are cut.
- **Whose water she is wet with** (`narration.body_slips.wet_source`). "The water from the aqua jet still dripped
  from Ripples' fur" after Nerine's Water Gun soaked her: the move named is now the one that really soaked her last.
- **"Nerine, she thinks to herself, You can't give up now."** becomes the marked thought it is, with the present-tense
  lines that carry it on. "she thinks" after a thought becomes "she thought".
- **No stepping tells for a fighter crouched over another on the ground** (`narration.stand_signs.holder_down`).
  Nerine, holding Ripples' knee in her jaws, was seen with "an uneven step" and "her weight off the hurt leg".

## Build 252

From your build-251 submission match (Ripples vs Nerine, the lakeside clearing, 10 beats).

### The engine

- **A blow moved by the tap steer no longer keeps where it was aimed.** With `finish.submission.taps` on, the steer
  moves a blow onto the part being worked (Nerine's right thigh). It moved only the first part: the rest (both ears,
  the left foot) were rolled for and dropped, and the director's words ("drives her knee into her head", "rakes her
  cheek") stayed, so the story told the head and the cheek. Now the blow keeps only the new part, and its words name it.
- **Plain body moves land as Normal** (`moves.plain_body`). The director typed a Head Twist as Water: it hit as
  Water, soaked Nerine and went into her mouth. An improvised move with no word of her element in it is Normal now. A
  conjured weapon still sets the type.
- **A lost beat in the export.** Each beat's autosave ran before that beat was recorded for `/exportfight`, so a fight
  loaded from that save was missing its last beat (your beat 4). The beat is saved again once it is recorded.

### The export (`export.gauges`)

- Beside each fighter, the window's **tap pips** and its **two pain gauges** (overall, and the part held or struck),
  as they were after that beat. Beats saved before build 249 have no gauge.

### Narration

- **Thoughts built by the engine are the part's own fighter's.** "*Go for the right thigh*" in Nerine's head about her
  own thigh, and "*Not the aqua jet again*" in Ripples' head about her own move, came from the other fighter's notes.
- **No stepping tells for one lying down** ("the uneven step, her weight off the hurt leg" for Ripples, face-down).
- **The notes' wording taken out of the prose:** "in a few words of her own", "Then what it left on the right hip:",
  "She was the one gripping, pressing and keeping it on...", and the model's "That is the paragraph rewritten."
- **Nouns stay nouns** in the past-tense pass: "short, sharp gasps", "the frantic heaves and kicks". "Her chest heaves
  and shakes" still becomes "heaved and shook".
- **Small mends:** "the faint the taste of" becomes "the faint taste of"; "snapped back came up" becomes "snapped back
  and came up"; "forearms fin" becomes "forearm fins"; "over right thigh" becomes "over her right thigh"; "grinded"
  becomes "ground"; "felt the smell of" becomes "caught the smell of".
- **New checks (sentence cut):**
  - A grip told the wrong way round: "Nerine's foot curled as Ripples' twin tails tightened round it", when the tails
    were Nerine's. Part of `narration.wrong_owner`, which also catches "a chilled patch" on one no cold touched.
  - A fighter who "got back up" when she has never been down this fight (`narration.never_down`). Saves from before
    this build aren't checked, since they didn't record it.
- **Fewer repeated body lines:** the leg's "the shock ran down into the foot and the ground felt strange under it"
  came five times in ten beats. The leg list has more lines, and one offered in the last three beats waits while
  others are left.

## Build 251

From the narration in your build-249 submission match (Ripples vs Nerine, the lakeside clearing).

### Padding (`narration.stock_limit`, `narration.paragraph_cap`)

- **Stock phrases are capped.** The list is `padding_phrases.txt`: "her mind raced", "she could feel", "her breath
  came in ragged gasps", "every muscle screaming", "she wouldn't give up" and more. Edit it, one per line. Each is
  allowed once a beat (`per_beat`), and not at all once the last 3 beats used it twice (`window_beats`,
  `per_window`).
- **Past the cap it is mended with no model call:**
  - "could feel the X" becomes "felt the X" (and "could see" "saw").
  - A phrase in a side clause loses just that clause ("She gritted her teeth, her breath coming in short, sharp
    bursts" becomes "She gritted her teeth.").
  - A sentence that is nothing but padding is either swapped for a line built from the fight (`swap_chance` 0.5)
    or cut.
  - A sentence that also tells something that happened (a hurt part, a sound, a move) only ever loses the clause.
- **The swapped lines come from the engine:**
  - her real worst wound and what it does to her ("She kept the weight off her right knee, and shifted it again
    when it complained.");
  - her breath by how far gone she is;
  - a short thought from what she has learned this fight: the move that keeps hitting her ("*Not the bite
    again.*"), the one that works, the part she can see her opponent favouring.
  No swapped line comes back within 3 beats.
- **Paragraphs:** with rich narration on, each part was asked for at least N paragraphs; now also at most N + 2
  (`extra`), and it ends when it has nothing more to tell.

### Mends

- **Past tense:** a noun stays a noun. "The frantic heaves of her body" had become "the frantic heaved of her body".
- **Fragments:** a sentence that already has a verb is no longer given "came up" ("Nerine's ears flicked back
  came up").
- **Thought marks:** a closing `*` with no opening one gets its opening at the start of the thought
  ("I can't hold on much longer.*").
- **Leftovers:** "Hnk, escaping her lips." becomes "Hnk escaped her lips."; a last clause that repeats the sentence
  goes ("her step was uneven, …, and her step was uneven"); "The thought was a frantic plea" with no thought
  before it goes.

### Places (`narration.positions_check`)

- A position on, against or beside something that has broken goes. Nerine stood "on the boulder" every beat after
  she was driven through it. The narrator is told what has broken too, and a sentence with someone standing,
  sitting or leaning on it is cut.
- While she is down, held or holding at the foot of what a charge drove her into, the director's "in the shallows"
  becomes "by an old oak".
- The soaked line names only the place ("pinned face-down by )" came from the director's words cut at 60
  characters).

### Whose it is (`narration.wrong_owner`)

These sentences are now cut:
- a frost, burn or shock wound on the one that element never touched (Nerine "feeling the sting of the icy
  wound");
- her "own" move that only the other used ("Ripples knew that her Aqua Jet should have done more");
- her sight swimming when nothing struck her this beat and she isn't dazed.

This beat's attack called by another move's name ("she threw an Aqua Jet" for a Water Gun) is sent back to be
rewritten.

### Smaller

- **The tap:** it lands on the holder's arm only when she grips with it. Jaws or tails on the knee: her shoulder.
- **Standing fighters:** a fighter on her feet all beat lifts no head "off the ground", doesn't "lie there", and
  doesn't think of getting back on her feet.
- **Hold names:** a hold whose move names one limb and whose grip is another is shown by what holds her ("A GRIP
  WITH HER JAWS", not "TAIL BIND").
- **Where a stream comes from:** what the director said ("from her mouth"), else the move's new `from` in
  moves.json (Water Gun, Hydro Pump: her mouth).

## Build 250

From your submission match (Ripples vs Nerine, the lakeside clearing). Nerine's jaws stayed on Ripples' right knee
for five beats while the knee went from 150% to 280%. Ripples stayed on her feet the whole time, even got up while
held, and tapped standing.

### Borne down in the hold (`submissions.upright`)

- **Any grip can bear her down now** (`plain_holds`), not only a named submission: jaws on her knee, tails round
  her hip. It goes stage by stage as before (sagging, on her knees, flat), with the grip kept on. A grab chest to
  chest and a pin's grips don't count.
- **A grip on a leg she stands on takes it out from under her** (`leg`: +15%). The more that part is hurt, the
  likelier it is (`per_100_worn`: +10% for every 100% on the worst gripped part, up to 3). Jaws on a knee at 150%
  for four beats bring her down most of the time (the new test: at least 12 of 20).
- **A hold that carries her weight holds her up instead** (`supporting`: the bear hug and the shoulder ride, ×
  `support_mult` 0.3). You can add others to the list.
- **Rising with a grip on her leg is much harder** (`held_getup`: −0.3 on the get-up roll).
- **She rarely taps still on her own feet** (`standing_tap_mult` 0.35): she has her legs to fight it with, so most
  holds bear her down before she gives in. A supporting hold isn't damped.
- **More holds start while she is down:**
  - On her feet, most openings take her down into a hold on the ground. Only `pick_share` (40%) offer one that keeps
    her standing.
  - In a submission match an opening on a fighter already down is likelier (`submissions.match.down_mult` 1.3, up to
    `down_max` 0.9).
  - The director is told this is the best moment for a hold, before she can get up.
  - With the stand-in driver over 30 three-tap matches: 74% of taps on the ground (71% before); holds started on a
    fighter already down 46% (34%). It mostly takes its holds on fighters already down, so the change is bigger
    with the director, which puts holds on standing fighters as in your log.

### Two pain gauges (`window.pain_gauge`)

The single gauge added up her worst parts, so a ruined knee kept it over 300% for the rest of the fight. It is now
two gauges:
- **Overall pain:** what she feels now. Each blow and grip adds its sting, and it fades every beat (`decay`: half is
  left each beat). It sits over a low floor her injuries keep up (`chronic` 0.15 × her worst parts). Ripples as in
  your log (knee 310%, hip 130%, half health) rests at 63% (hurting badly). A blow on the hip spikes it to 77%,
  then it settles back over the next beats.
- **Part pain:** the part being held, pinned or struck this beat.
  - In a submission it is the tap check's own number, which comes only from the gripped parts (with a choke's air
    beside it). A tap is decided by the held part's pain against her resistance; her other injuries only weaken
    that resistance, through her health.
  - Struck, it is that part's damage plus the blow's sting.
  - When nothing is on her or at her, it says so.

## Build 249

The three things left over from Build 248, a pain gauge in the window, and most of the smaller findings from the
reviews of the narrated three-tap match.

### How far a held fighter can reach (`holds.held_reach`)

- **The holder is where her grips are.** Face-down in a heel hook, Nerine bit Ripples' shoulder and throat, though
  Ripples was tangled round her leg. Now a fighter held on the ground can hurt her holder only with what reaches the
  part being held. Each weapon has its own list of her body regions it reaches from the ground (jaws, paws, legs,
  tail). In a heel hook that leaves kicks and her tail, and her jaws and paws are refused ("Ripples is at her legs,
  out of reach of her jaws"). Sitting up she reaches further (`sitting_adds`). A bite also has to land near the limbs
  holding her (`bite_near`): her paw, not her throat.
- **What isn't limited.** Moves fired across the gap aren't limited, and neither is a hold on a standing fighter,
  since the holder is right against her.
- **The director is told** what she can still reach. `/simulate` only picks what reaches.
- **A blow from down there throws no one off.** A fighter held down in someone's grip can't send her holder flying
  with a bite.

### Held, down and still counting

- **"Down N beats" counts every beat on the ground**, pinned and held ones too. It used to freeze while she was in a
  submission. The get-up roll's own easing still counts only the beats she was free to try.
- **No footwork for a fighter held or down.** The building blocks for her blow drop strides, circling, sidesteps,
  planted feet and lunges when she is held in a grip or on the ground.

### A pain gauge (`window.pain_gauge`)

A bar under each fighter's energy bar shows how much pain she is in against how much she can bear, as a share. The
dashed mark is 100%, all she can bear. It has a word too: bearable, hurting badly, near her limit, past what she can
bear. It decides nothing: it shows numbers the engine already uses.
- **In a submission** (in a submission match), it shows the tap check's own pain against her resistance. In a choke
  it also shows how much of her air is gone.
- **Everywhere else** it uses her worst part plus a share of the next two, and any grip or pin pressing on her. It
  also adds the fresh sting of this beat's blows (`sting`), so a big hit spikes it and it settles the next beat.
  ("+31 from this beat" says how much came from the blows.)
- **What it is measured against:** the same resistance as the tap check (`finish.submission.tap`: her will, which
  her strength carries).

### Smaller fixes

- **Taps in the fight summary:** each tap and each bear-down in an upright hold is a key moment, and a several-tap
  match tells every tap.
- **Tap signs:** the signs she shows while refusing to tap aren't reused for a while, and no longer start over after
  each tap.
- **No interlude while a hold or pin is on** (`narration.interlude.not_in_holds`).
- **The long-match ramp no longer lags a beat** behind the blows.
- **The Total line counts the ramps:** "(the parts count +N with the ramp)".
- **Labels:**
  - A submission's cap is labelled "submission cap", not "pin cap".
  - A roll that equals its chance shows "30%", not "30.000%".
  - "It lands differently because" now says whose state it is ("Ripples: choking on water").
- **Wording:**
  - "Her Bite has found her 2 times out of 2: it keeps getting through" (it said "it works on her", which read like
    type effectiveness).
  - HOW EACH HAS FOUGHT counts a hold as a grab, and no longer counts the scenery's doing as her attack. "None from
    range" is "only one from range" when there was one.
  - No "wing flung out" for a fighter without wings.

## Build 248

The rest of the fixes from the narrated three-tap match (`sim/test_fights/three_tap/`). Three review agents read
every beat's screen output and narrator notes; their findings are in `findings_A.md`, `findings_B.md` and
`findings_C.md` there.

### Engine

- **Upright holds need the holder up.** A fighter lying on the ground was given a standing armbar, a standing
  sleeper and a rear chinlock "kneeling behind her". A holder who is down now gets only ground holds, and an upright
  hold can't bear anyone down while its holder lies there herself.
- **Takedowns into a hold fit the way she lands.** A leg hook (she goes over backward) was picked for a face-down
  landing. The takedown is now one that fits.
- **A coil is only the grip that wraps.** In a tail-bound knee crank, the paws turning the foot were marked as coils
  too, because the hold's overall description mentions the tails. So "her right foot bound" showed up while the
  tails bound the knee. A grip with its own words is now judged by them alone.
- **The holder's posture is told right.** "LOCKED ONTO … (down on her, wrapped round her)" is now "holding her on her
  feet" for an upright hold, and "down with her on the ground" when the holder is down too.
- **The ending.** "Nerine was taps out; Ripples was left standing over her" is now "Nerine taps out …; Ripples was
  down on the ground herself, too spent to rise" when that is so.
- **Notes put right:**
  - "Only a completed pin puts her out" in a match with no pins is now "Only a tap-out or a pass-out ends it".
  - "Refuses to go down" for a fighter already down is now "refuses to give in".

### Narrator

- **A tap that doesn't end the match is checked for**, so a draft that leaves it out is sent back, as the final tap
  already was.
- **Garbled lines fixed:**
  - The inserted hold sentence ("Then Ripples' the same twist, carried up into it closed on…") is now "Then Ripples
    closed both paws on…", or "her grip".
  - "Then and she goes down again" is fixed.
  - "Nerine's TURNS IT BACK", "a ARMBAR", "SPENT, Curls" and "shakes off being on an adrenaline surge" are fixed.
  - "Ripples still has Ripples' twin tails" is now "her own".
- **Every grip of a hold gets a step in the plan**, up to three; before, the third grip was dropped.
- **No lines that put her on her feet** (footing, stepping back, bouncing on her legs) when she is down or held.
- **Whole-body "in the coils" lines** are used only for coils round her body or neck, not tails round a knee.
- **The water and the cold are told on parts the move hit**, never on a part only the landing hurt.
- **Right words for her position and her injuries:**
  - The get-up note no longer says the other fighter "is on her feet" when she was thrown down that same beat.
  - A part at 300–499% is DEVASTATED, not RUINED. Ruined starts at 500%.
  - "Ear" no longer matches inside "forearm", which had a forearm fin get the head reaction.
  - A resisted knockdown no longer also says "her feet stay where they are".
- **Smaller fixes:**
  - The final tap note names the part the tap counted for.
  - The takedown retry no longer says "pin" in a no-pins match.
  - An electric "charge crackled" line was being offered for a Water Gun.

Not done yet:
- How far a held fighter can reach. Face-down in a heel hook, Nerine bit Ripples' shoulder and throat.
- Building blocks written for a fighter standing free, used while she is held.
- "Down N beats" not counting while she is held.

## Build 247

Fixes and two changes from a fully narrated three-tap submission match: Ripples vs Nerine, the lakeside clearing,
seed 8, each tap from a new part. The engine's own stand-in chose every beat, and Ripples won 3–2 in 78 beats. The
fight, its driver and the narration are in `sim/test_fights/three_tap/`.

### Fixes

- **No submission from inside a submission.** A fighter locked in someone's submission could lock one of her own on
  the holder: at beat 63 Nerine, in a standing armbar, armbarred Ripples back, and at beat 65 Ripples, in that
  armbar, put a rear chinlock on Nerine. At beat 66 both tapped in the same beat. Now it is refused ("break free, or
  hurt the one holding her with what she has free"). The director is no longer offered such an opening, and
  `/simulate` doesn't take one.
- **One last stand, not two.** The engine already had `moves.last_stand`: once a fight, below 15% strength, one blow
  with everything she has left. It fired for both fighters in this match. Build 246's `low_health.last_stand` was a
  second, separate one. It now only adds what was new: the beat after her last-stand blow, she is wide open
  (`open_dodge_mult`).
- **No squirming the beat she goes down.** `low_health.squirm` was told the same beat she was thrown down. It checked
  a list that is emptied before it runs.
- **The aftermath report:** a winner lying on the ground is no longer "the one still standing, if only just". She
  "won, from flat on the ground, and can't get up yet".

### A long submission match comes to an end

- **`finish.submission.long_ramp`:** past beat 40, the damage blows and grips do to body parts (not health) grows
  ×0.15 every 10 beats, up to ×2.5. The stat lines show "×1.60 for a long match". By default this applies only in
  several-tap matches. Measured alone it changes little, because a hold has to start first, so the next change
  matters more.
- **`submissions.match.late`:** past beat 30 of a submission match, the chance of an opening on a standing fighter
  rises by 3% every 10 beats, and its ceiling goes up from 20% to 35%.

## Build 246

What a fighter does at the very end of her strength, and a tap tally in the window. Each of the five is on by default
and has its own switch under `low_health` (`low_health.enabled` false turns them all off).

### The very end of her strength (`low_health`)

They apply once she is at `at_pct` (10%) of her full health or less. Each is a told event, at most once every few beats
(`cooldown`).

1. **Left alone, she shows it** (`idle`: 35%, every 3 beats). On her feet, on a beat when she neither acts nor is
   acted on, she sways, leans on something nearby, blinks blood away, spits, tests a badly hurt leg, or fights for
   breath. The other fighter sees it and closes in, waits, or circles.
2. **Down, she squirms** (`squirm`: 40%, every 2 beats). Down and free, but not the beat she went down or got up, she
   drags herself toward the other fighter or away, claws at the ground, or curls around her worst part.
3. **Her body gives her away** (`tells`: 20%, every 4 beats). Shaking, ragged breath, or a limb that doesn't answer.
   That needs a limb at 100% damage or more (`dead_limb_damage`), and moves thrown with it can't be used the next
   beat. The engine refuses them, and the director is told.
4. **A last stand, once a fight** (`last_stand`). Below -50% (`at_pct`), on her feet and free, 15% a beat. Her next
   beat's moves get ×1.5 power (`power_mult`). The beat after, she is wide open: dodge ×0.2 (`open_dodge_mult`). The
   director is told both, and the stat blocks show 🩸 and then 🫥.
5. **The other fighter reads her** (`foe_read`: 30%, every 6 beats). One of three thoughts: "she's done, finish it";
   "careful, she has one more in her"; or "why is she still standing?" (only while she stands below zero). The read
   is shown in the story and passed to the director, which then goes for the finish, stays wary, or hesitates.

Each comes with a note for the narrator and a 🥀/👁️ line on screen. In 20 no-model knockout fights they came a
handful of times each. In three-tap matches, where fighters spend long stretches near the end, they come more.

### Tap tally in the window

In a submission match, each fighter's panel shows a row of pips under her energy bar. There is one pip per tap-out
the match needs, filled red for each she has given, with the count ("1 of 3") and the parts the taps came from. It
isn't shown in other fights.

## Build 245

Submissions can be put on a fighter who is still upright, and may bear her down while the grip stays on. Switchable
with `submissions.upright.enabled`.

### Upright holds (20 new)

These are put on a fighter **on her feet or sitting up**. Before, every submission needed her lying down.

| Holder's body | Holds |
|---|---|
| Two legs | full nelson, standing sleeper, bear hug, hammerlock, side headlock, guillotine, cobra clutch, abdominal stretch*, standing armbar, standing wrist lock, octopus hold*, rear chinlock (sitting only) |
| Four legs | scruff hold, foreleg bite, flank crush, shoulder ride*, hind leg hook* |
| Two or four legs | tail haul |
| Serpent | upright coil |
| Bird | talon shoulder clamp |

\* on a standing fighter only.

- **The director can invent upright holds.** It can mark one with `"upright": true`, or describe it as standing (a
  nelson, a headlock, a bear hug, "on her feet"). The engine still checks every grip against both bodies.
- **What the narrator is told:** she is still upright in the hold, and she isn't to be put on the ground unless the
  events say so.
- **In a submission match,** an opening on her feet (Build 244) offers these holds as they are. Any other hold still
  takes her down first.
- **A sitting fighter** could take no submission before. Now upright holds fit her, in any fight.

### Going down in the hold, in stages

From the beat after it locks, each beat an upright hold may **bear her down one stage, with the grip kept on**. The
stages are a list in rules.json (`submissions.upright.stages`), not hard-coded. Each has a name, a posture and a line
for the narrator, and you can add, remove or reorder them. The engine only knows three postures:

- **standing:** still on her feet, off balance for a beat;
- **knees:** down, sitting up;
- **flat:** lying on the ground.

The defaults:

1. **Sagging** (standing): her legs start to go; she bends, still fighting to stay up.
2. **On her knees** (knees): she sinks to her knees, still locked in it.
3. **Flat** (flat): forced all the way down, the hold riding her down.

How it rolls:

- **Where she starts:** a fighter already sitting starts from the knees stage.
- **Each drop is its own roll:** `base` (15%), plus `per_beat` (8%) for each later beat, plus `weak` (25%) × how much of
  her strength is gone. Never above `max` (60%). So a hold usually takes her down over a few beats.
- **`skip` (20%):** a drop takes two stages at once.
- **`readjust` (25%):** at a drop, the holder has to shift her grip. The grips lose 30% of their pressure
  (`readjust_mult` 0.7) and a beat of their build, but stay on.
- **How it's told:** the narrator gets the stage ("stage 2 of 3: on her knees"), its line, whether she dropped fast,
  the readjust, and where she is now (still on her feet, on her knees, flat). The screen shows ⬇️ with the stage.

In 20 no-model three-tap matches (Nocturne vs Ripples), 25 of 79 taps came in upright holds. Three-tap matches
averaged 69 beats (longest 140), single-tap ones 41. No stand-in action was refused, and the knockout balance is
unchanged (Nocturne 62%).

## Build 244

Submission matches move faster. Each change is switchable.

### More submission starts (`submissions.match`, only in submission matches)

Before, an opening for a submission came only while she was down. Now one can come while she is **on her feet**: the
holder takes her down into it (a tackle, a sweep, a drag to the ground), and the hold locks where she lands.

- **The chance each beat:** `standing_base` (4%), plus `per_100_worn` (4%) for every 100% damage on her worst-hurt part.
  Only parts that can still make her tap count, and at most 300% of it. Never above `standing_max` (20%). That is
  about 4% fresh, 8% with a part at 100%, and 16% with one at 300%.
- **Openings while she is down** are unchanged.
- **Who can take one:** a fighter who is down herself can't take down someone still on her feet.
- **How it's told:** the narrator is told she was on her feet and is taken down into the hold. The screen says "taken
  down into the hold". The director is told she is open and can be taken down into it, and in a submission match the
  opening is no longer called "very rare".

### Her parts give way faster deep below zero (`below_zero.part_ramp`)

Below zero health, the damage each blow or grip does to her body parts is multiplied. It is ×1 + `per_10` (0.08) for
every 10% below zero: ×1.4 at -50%, ×1.8 at -100%, ×2.6 at -200%, never above `max` (×3).

- **Health is untouched.** Her parts just wear out sooner, so the pain builds and the next tap comes sooner.
- **`only`:** `taps` (the default) applies it only in a submission match needing more than one tap. `submission`
  applies it in every submission match, and `all` in every fight.
- **On screen,** the damage row says "the part counts +N: ×1.80 below zero".

### Smaller fixes

- The director is no longer offered a submission by a fighter who must still wait before grabbing her again (she has
  just torn free).
- `/simulate` now has the one who can take a submission opening act on it most of the time, as the director is told
  to. Before, its no-model fights ran slower than real ones would.

### Effect (30 no-model fights, Nocturne vs Ripples)

| | Before build 243 | Build 243 | Build 244 |
|---|---|---|---|
| Single-tap match, average beats | 70 | 65 | 42 (longest 72) |
| Three-tap match, average beats | 164 (one never ended) | 112 | 76 (longest 134) |

## Build 243

Fighters no longer spend much of a fight on the ground, and several-tap submission matches finish. All of it is
switchable.

### Why

In 30 no-model three-tap matches (Nocturne vs Ripples), one ran 300 beats without an end, with both fighters near
-2000%. They averaged 164 beats, and both fighters were down at once a quarter of the time. Two things caused it:

- Below zero, her body gave out on its own up to 40% a beat. It came again five beats after the last collapse, often
  the beat she got back up.
- Nobody on the ground could lock a submission, so while both were down no tap could happen.

The stand-in fights now average 112 beats, the longest is 235, and every one finishes. Single-tap matches and
knockout fights were already fine. Nocturne vs Ripples knockout balance: 62% (it was 67%).

### Collapses are rarer (`health.collapse`)

- **`stand_grace` (5):** once she is back on her feet after a collapse, her body can't give out on its own for 5
  beats. Blows can still knock her down at any time.
- **`repeat_mult` (0.6):** each collapse this fight makes the next less likely. The second is 60% as likely, the
  third 36%.
- **Lower chances:** `base` 0.08 → 0.05, `per_10_below` 0.03 → 0.02, `max` 0.4 → 0.25.

### A knockdown isn't certain (`down.keep_feet`)

When the director says a blow knocks her down, she may stagger and stay up instead. This covers only a plain
"knocked down": throws, launches, crashes into the scenery and moves that knock down by themselves are unchanged.

- **The chance comes from her strength:** 50% at full health, 35% at half, 25% at 0% and below.
- **The blow's size changes it:** up to ×1.4 for a feather of a blow, down to ×0.5 for one that takes 10% or more of
  her full health.
- **Never above 75%.** Badly hurt, she goes down to a solid blow about three times in four, and to a huge one nearly
  nine in ten.
- **How she keeps her feet** is one of four ways (staggers back, a knee nearly touches down, sways, locks her legs).
  The screen shows it with 🦵, and the narrator is told not to put her on the ground.
- **The director is told** a knockdown is rolled, not certain.
- **Your own commands** always knock her down.

### Holds from the ground (`submissions.from_ground`)

In a submission match, a fighter who is down can lock a submission on someone who is down too. She rolls into it or
crawls onto her. While she works it, she stays down instead of rolling to get up. `match_only` (on) keeps this to
submission matches.

### Fewer repeated notes

- **`ruined.jar_cooldown` (3):** after a ruined part is jarred, no other jar for 3 beats.
- **`below_zero.grey_cooldown` (3):** after her sight greys, it can't again for 3 beats.

Before, deep in a fight these came almost every beat for both fighters.

## Build 242

Selling damage past devastated, and what happens once her health is gone. Both are switchable.

### Ruined: a damage tier past devastated (`ruined`)

Devastated used to cover everything from 300% up (the numb tier at 1000% is off by default), so a part at 400-700%
had nothing new to say. Now a part past `ruined.min` (500%) is **ruined** (🟤), and that changes what happens:

- **A ruined leg folds under her** when her weight comes onto it (`buckle_chance` 25% a beat while she stands free):
  she catches herself, off balance for a beat. She doesn't go down.
- **Her own movement jars it** (`jar_chance` 30%): a deep breath, a turn, her heartbeat; told in the story, no damage.
- **She can't hold it in any more**: a real blow on a ruined part gets at least a real scream, a brush at least a cry
  she can't swallow, however strong she still is. Grips on it have their own, rawer reactions.
- **The one who did it sees it**: a flicker of hesitation, or a cold, settled focus.
- **Getting up costs more** for each ruined leg (`getup_penalty`, up to two).
- **In a submission match**, a grip on a ruined part adds `tap_pain` (30) to the pain she must resist.
- The screen, the pictures and the legends show it in its own colour.

`ruined.enabled false` = those parts stay devastated, as before.

### Below zero health (`below_zero`)

She is never stopped from fighting by it, but past zero the fight changes by stage (her health as a % of her full):

| Stage | At | Her blows | Get-up roll | Tap chance | Each beat |
|---|---|---|---|---|---|
| running on nothing | 0% | ×0.9 | -0.1 | ×1 | |
| greying out | -20% | ×0.85 | -0.15 | ×1.25 | 20%: her sight greys out for a beat (she sways, dodges ×0.3, hits ×0.85); 15%: a second wind (once a fight) |
| her body overruling her | -50% | ×0.8 | -0.2 | ×1.5 | 25%: her sight greys out |

- **Once a fight, she refuses to go down** (`refuse_moment`): the first time she goes below zero, the story gives her
  one short passage of it, from what she holds on to: the one in front of her, the part screaming at her, what she
  came here to do.
- **A second wind** (`second_surge`): with her one adrenaline surge long spent, one more may come below -20%.
- **Each new stage is told** as she reaches it, and the health tiers tell them apart (past the limit, greying out, her
  body overruling her). `health.collapse` still has her body give out on its own now and then below zero.
- Nocturne against Ripples, 60 knockout fights each way: 32-28 with all of it off, 30-30 with it on.

`below_zero.enabled false` = none of it.

## Build 241

Two rules for matches that need several tap-outs.

- **Let go, and a beat to get up** (`finish.submission.taps.respite`). A tap that isn't the last already ended every
  grip the holder had on her. Now the holder also steps back: for `respite.beats` (1) nobody strikes or grips the one
  who tapped (whatever the director had them do to her becomes a step back), so she gets at least one clear try at
  getting up before the next hold. She also rolls to rise the beat she taps, once the grip is off. Your own commands
  still go through. `respite.enabled false` = the fight goes straight on.
- **Different parts, enforced to the end.** A grip on a used-up part already couldn't make her tap. But a hold on a
  used-up part AND a fresh one still counted the used-up part's pain, and the tap was then credited to the fresh
  part. Now a used-up part adds nothing (no pain, no pressure, no choke) toward the next tap: only the parts that
  still count can carry it.

## Build 240

The two changes picked after the build-238 three-tap match.

- **Faster beats: cut, don't rewrite** (`narration.cut_first`). Nearly every beat said "N of them still came back
  wrong: only the wrong sentences get cut": the paragraph rewrites cost a minute or two and mostly failed. Now a
  paragraph whose every slip is one a rewrite rarely mends loses just those sentences, with no model call, and is
  written again only if that would leave it empty. The slips: an invented wound, a game term or number, copied
  lines, a body part nobody in the fight has, blood with no wound, a thing not in this arena, a stock phrase
  (`cut_first.marks`; remove one to have it rewritten again). Mistakes about what happened (a missing hit, an
  invented fall) are still rewritten. `cut_first.enabled false` goes back.
- **No more blows wasted on a ruined part** (`finish.submission.taps.steer.ready`, 150%). In the build-238 match the
  steer kept every blow on the left thigh until it passed 700%, far more than a tap needs. Now, once the target part
  is past `ready` and more than one tap is still needed, it is READY:
  - blows move off it onto the NEXT part, the one the tap after this one will come from (it sticks from beat to beat
    too, and becomes the target after the tap);
  - holds still go onto the target;
  - the director is told to put a hold on it now and soften the next part with blows.
  `ready 0` keeps the blows on the target to the end.

## Build 239

Fixes from a build-238 Nerine vs Ripples match set to three tap-outs from three different parts. The match never
ended: Ripples sat in Nerine's jaws for ten beats with her left thigh past 700% damage and her health far below zero,
and never once rolled to tap.

- **A grab can make her tap** (`finish.submission.tap.grabs`). Until now only holds that hurt could, never a grab
  (jaws or paws simply holding on). Now a grab counts once the part it is clamped on is hurt past `min_damage`
  (100%), or once her health is gone. `grabs.enabled false` goes back.
- **No grace beat with no health left** (`tap.spent_no_grace`). The first beat past her limit is normally one she
  holds on through; with her health at zero or below it can already be the tap.
- **A kept grip presses as it was** (`holds.keep_as_is`). When the director only kept a grip on, it jumped back to
  the director's pressure, undoing the loosening Ripples had won, and a second limb on the spot ("her jaws and twin
  tails") was added again every time it was kept: Nerine's jaws went from 6 to 34.5 in one beat. Now the grip's own
  tightening does the climbing, and the second limb adds its share once.
- **More program cuts** (`narration.cuts`):
  - `run_on_thought` also mends a thought in its marks run into the next words ("*I can't give up now* She
    steeled", "*She's tiring* A satisfied smirk").
  - `caps`: a note's word copied in capitals ("Her left thigh was RUINED") is written as a word.
  - `salt`: no "saltwater" or "the saltiness of the water" in a lake or a pool.
  - `end_stop`: a paragraph that ends with no full stop ("*Let her feel it*") gets one.

## Build 238

Submission matches that need more than one tap-out, and fixes from a build-237 Ripples vs Nerine fight.

- **Several tap-outs** (`finish.submission.taps`, off until you turn it on):
  - `taps.needed` sets how many tap-outs end the match. With 3, the third tap wins. A tap before that makes the
    holder let go, and the fight goes on. Her limit and her refusals start again for the next hold.
  - `taps.different_parts` is the share of those taps (a percentage) that must come from a body part no earlier tap
    used. It is rounded up to a number of parts. With 3 taps: up to 33 means any parts, 34–66 means at least two
    different parts, and 67–100 means all three different.
  - A tap counts for the worst-hurt gripped part. Once no repeats are left, a grip on a used-up part can't make her
    tap at all.
  - `taps.pass_out_counts`: a pass-out in a choke counts as one of the taps (on by default).
  - The screen says "tap 1 of 3" and which parts can't count again. The story is told the match is not over.
- **Steering onto a part that still counts** (`taps.steer`). Each fighter has a target part: the worst-hurt part
  that still counts, a limb first. It sticks from beat to beat so the damage builds there, and is picked again after
  each tap.
  - The director is told the tally, the used-up parts, and to soften the target with blows and then hold it.
  - A blow aimed at a used-up part always moves onto the target. Any other blow moves there `steer.strikes` of the
    time (0.6).
  - A grip on a used-up part moves onto the target. Any other grip moves there `steer.holds` of the time (0.9).
  - The submission openings offered favour holds that grip the target.
- **Cuts the program makes by itself** (`narration.cuts`, each switchable):
  - **First beat:** a past that can't be there is cut ("still sore from the earlier blows", "from her last dive").
  - **Repeated aches:** only two sentences a beat may just say how one hurt part feels (`cuts.ache_repeat`). In the
    last log the right-thigh ache was told four times.
  - **Copied labels:** "Nerine's plain blow hit" becomes "Nerine's blow hit".
  - **Hand-over lines:** "Nerine's reaction would follow." is cut.
  - **Run-on thoughts:** "That leg needs to go Her mind…" gets its full stop.
- **Other fixes:**
  - "Ripple's body" becomes "Ripples' body" (a name ending in s, given the wrong possessive).
  - A grip the director filed under an attack move (a hold called "Aqua Jet") is a plain grip. Before, the story
    told a charge and a grip at once.
  - The only blow on a part, told without its name ("her right thigh took the brunt of it"), counts as told. The
    Knee Stomp is no longer written a second time.
  - A failed get-up says her paws skid out from under her, not "what she pushes off with skids".
  - An empty "Breather:" line now says who catches her breath.
  - A mistyped `/set` path gets a guess: `finish_submission.enabled` → "Did you mean finish.submission.enabled?"

## Build 237

A more readable story pane in the window (`python window.py`), with pointers to where the numbers come from. All of
it is in rules.json `window.text`.

- **The story and the numbers look different.** The story is in a reading face with room between paragraphs. Each
  block of numbers sits on a shaded band in a fixed face, with its first line in bold. In the damage, resistance and
  health rows, the row name and its change are coloured: damage red, resistance blue, health green. A roll that came
  in under its chance is shown in green; one that didn't, in grey.
- **Switches above the pane:**
  - **Numbers** hides every stat line, leaving only the story. The lines stay in the pane, so the beat slider still
    works.
  - **Progress** hides the narrator's "[writing part 1/2]" lines.
  - **Pointers** turns the notes below on or off.
  - **A− / A+** change the text size. `window.text.font_size` sets the starting size.
- **Pointers** (`window.text.pointers`: occasional, always or off): a short teal note under a set of numbers, using
  those same numbers. For example: "Damage +17.76 = the hit's power 49.49 (the dice moved it ×0.99) × 0.12, what this
  part takes at its resistance of 113% × the damage scale 3". There are notes for a part's three rows, a tap refusal
  or tap-out (pain against her resistance, and the chance), a pass-out (air against her endurance), a blow's power, a
  grip's power, the beat's health drain, the rolls and a loosened hold. "occasional" shows each kind once, then
  again only after `pointer_gap` beats (6).
- **Hover tips** (`window.text.hover`): the underlined terms in the numbers (the damage roll, scale, vital, the
  resistance scale, a submission's grind, pain against her resistance, air against her endurance, exertion,
  injuries, a grip's ramp, a move's power, a break-free chance) show what the number is and which setting it comes
  from when you rest the mouse on them.
- **No more broken lines** (`window.text.unwrap`): in the window, stat lines are no longer cut at 100 characters as
  on the console. The pane wraps them itself, with the rest indented under the line's start.
- **Fixed: resistance rows said "(it can't go lower)" when it could.** That note appeared whenever the wear wasn't
  the plain power × 0.3 × 0.7. Holds, submissions and soft parts wear faster, and some hits hit the per-hit cap. The
  row now gives the real working, such as "× 2 (a submission grinds it down)" or "(capped: at most 24.5 a hit)". It
  says "it can't go lower" only when the part really is at its minimum.

## Build 236

- **The tap-out or pass-out is told last** (`narration.tap_last`, on): in beat 31 of your build-228 Ripples vs Nerine
  fight, part 1 had Nerine go limp in Ripples' choke, and part 2 then had her wrench Ripples' knee. Now, when a beat is
  written in parts, every part before the last is told the ending isn't its to tell, the check that the ending was
  shown waits for the end, and a part that tells it anyway has those sentences cut (with the holder letting go right
  after). The end of the beat then tells it, after everything else. `/set narration.tap_last false` lets any part
  tell it, as before.

## Build 235

Fixes from your Ripples vs Nerine submission fight (played on build 228). Each problem was checked against the current
code first; several were already fixed in builds 229-234 (a hold with no limb named takes it from the director's
words; a pause's words about a grip that isn't there go; no throat grip from the ground).

- **A held stream into the scenery** (`moves.sustain.crumple`, on): Nerine's Water Gun pressed Ripples into a pine
  twice, and both times she ended up on the ground with nothing on screen saying so. She always slid down it. Now she
  is left pressed against it and, at the end of the beat, crumples or keeps her feet with the same roll as a charge
  (the weaker she is, the likelier she goes down), shown on screen either way. Off: she always slides down.
- **No tap after the match is won:** in the beat Nerine passed out, Ripples was still rolled to "refuse to tap" in
  Nerine's hold. Once the match is won, or the one holding her is out, nobody rolls to tap.
- **Tails, not coils:** the injury report said "Nerine's coils" for a Buizel's Tail Bind. A coil made of tails is
  now "her tails".
- **A pause that strikes:** a breather worded as a blow on the other ("Head butts Ripples in the nose") loses that
  clause; nothing resolved it.
- **A copied note label:** "What kept her holding on: that it was HER." (the tap-refusal note's label) is mended to
  "She held on for one reason: that it was HER."

## Build 234

Submission matches end in a choke only now and then, for variety: most are won by a lock on a limb, the back or the
body.

- **`finish.submission.choke_share`** (0.1): when a submission opening is offered (to the director, and in
  `/simulate`), it offers a choke (a sleeper, a triangle, head scissors, a camel clutch: a hold whose main grip is on
  the neck) only this share of the time when a lock on a limb or the body also fits. A lock's offer lists only the
  other locks. 1 = any fitting hold, as before.
- **The director** is told a choke is the rare finish, not the usual one (the submission-match hint used to push it
  toward chokes), and once a choke has been tried in a match, to go for a limb or the body.
- **Game plans:** in a submission match the plan to finish on her neck is half as likely (`director.game_plan.
  match_weights.neck` 1.5 to 0.75).
- **Measured** with `/simulate`-style fights (Ripples, Nerine and Nocturne in pairs, 115 submission matches): 17% end
  in a choke (taps and pass-outs on the neck), 79% in a tap to a limb or body lock. A choke finishes far more surely
  than a lock once it is on: offered every time it fits, chokes ended 72% of matches; never offered, 8%.

## Build 233

Chokes can go all the way, the two kinds of choke are told apart, and two Swellows fought in the clock tower
(`sim/test_fights/swift_vs_gale`: the script, the beat files and a full narration of the 24 beats).

- **Full chokes** (`narration.full_chokes`, on): the hard rule on breathing no longer says "only for a few seconds".
  A choke may cut off her air or the blood to her head completely, and held long enough she passes out, which is
  how a choke ends a pin or a submission match. She only faints, only when the events say so, and breathes again
  once it lets go. Off: the old rule.
- **Air or blood:** every beat a grip is on her neck, the notes name its kind (the engine's `choke_kind`, now on
  every hold event) and how far it has gone: an AIR choke shuts the windpipe (no breath, slow, panic first), a BLOOD
  choke squeezes the sides of the neck (she still breathes, but her head fills, roars and greys, quick), and jaws,
  hands or a bird's talons closed round the throat do both. A submission hold on the neck is told as a choke that can
  take her out, not as one she "will not pass out from".
- **The choke comes off:** when the grip on her neck is broken, slammed loose or escaped, the narrator is told her air
  and blood rush back (the whooping breaths, the grey pulling back).
- **Talons in the air** (`flight.air_grab`, on): a flyer can grab another flyer up there if she has talons, feet,
  claws, or the hands and arms some flyers have (a Charizard). Locked together they tumble down and land on their
  feet, the grip still on. Before, every grab in the air was refused.
- **Passages:** chokes by kind and by how long (`choke: air, blood, both`; `air: gone` for one held long), the
  pass-out itself (`choke_out`), and for birds a hard blow on a wing or a beak (`limb: wing, beak`), the fall when she
  is knocked out of the air (`air_fall`) and the tumble down locked together (`air_tumble`).
- **Fixes:**
  - A "struggle" when nothing holds her becomes a breather without its flavor ("thrashes on her back and snaps at
    the feet holding her" with nobody holding her).
  - A bird nursing a hurt beak or head no longer "smooths it with her beak": she shakes her head or works her beak.
- **New fighter:** Gale, a second Swellow: older, patient, a talon fighter (Pluck and Endeavor in place of Facade and
  Peck).

## Build 232

Story passages: a new library, `story_passages.txt`, of 88 finished showpieces, each two to four sentences long. They
cover the big moments of a fight: a heavy blow (by pain level, and by head, chest or belly, neck, back, leg, arm or
tail), a cut, a bite (with its own neck bites), a choke, a hold and the one holding it, the pin coming down, the
pinned fighter as her fight runs out, the one on top, a landing, and a knockout. Switches are under
`narration.passages`; `/passages` shows the counts and turns them on or off.

- **Rare:** in a part with such a moment, `chance` (0.3) of the time, never two beats running (`min_gap_beats`), and
  one a beat at most. The receiving side comes first: the pinner's or holder's side gets one only when nothing in the
  beat happens to the other.
- **Fitted to what the engine resolved:** the same conditions as the blocks (the part, how hard it landed, how badly it
  hurts afterwards, her body, the kind of move, how long a hold or pin has been on, how much fight she has left). Her
  injuries' pain ceiling, her body (no paws on a bird) and the scene all filter them, as they filter the blocks.
- **Set in, or drawn on:** `place_share` (0.35) of them are offered to be set in word for word, in place of the
  narrator's own telling of that moment. The rest are offered to draw on (their senses and their pacing), and with
  `copy_check` a sentence copied from one of those anyway is cut.
- **Repetition:** a passage offered once is not offered again for `cooldown_beats` (300) beats, and the least-offered
  come first. What has been offered is remembered between fights in passages_memory.json.
- **Kept to the hard rules:** every passage is written so it is true whenever its conditions hold. None adds an event
  (nobody falls, steps or gets free unless that is the moment), cuts stay small (a sting, a thin line of red), breath
  only ever stops for a moment, and a submission hold's choke never darkens toward fainting. A new regress check reads
  the file: only the slots the program fills, only moments it offers, at most four sentences, and no tearing,
  breaking, gore or killing words.

## Build 231

Shorter notes for the narrator, with every rule kept, plus three fixes from the Ripples vs Nerine fight. On a scripted
six-beat test, the average call went from 40.3k to 34.8k characters (-14%), and the parts where no blow lands from
about 45k to 36k. All switches are under `narration.compact`.

- **rules_trim:** the hard rules in fewer words. Rules that were said two or three times (only the listed events, in
  order; the tone; nobody dying) are said once. None is dropped, and the program's checks still catch a slip of any of
  them afterwards.
- **author_trim:** story_prompt.txt as the narrator reads it leaves out its TONE section (the hard rules now carry
  every point of it), the note on where the length is set, and the grapple/chain/tumble bullet in a beat that has
  none. The file is untouched, and the director still reads all of it.
- **blow_detail_where_landed:** how each blow lands (the body under it, how it moves her, its sound, the reaction
  ideas, the ways to sell a devastating blow) goes only to the part where it lands. The attacker's side, the
  aftermath and a watcher's part get what each blow is, where, and how hard. The "keep writing" top-up gets the
  short version too.
- **repair_lean:** a call that writes one paragraph again keeps the facts, the plan and the beat card, but not
  the part's building blocks, depth or camera notes.
- **Near-repeats:** a short sentence that opens with the same named subject doing the same thing ("Nerine's right
  hip throbbed, ..." twice) is told once.
- **The attacker's part stops at contact** (`narration.trim_past_contact`): sentences after her blow lands about the
  one hit feeling it are cut from her part, when the next part tells it anyway.
- **Fragments mended** (`narration.mend_fragments`): "Nerine's left paw, her forearm fin flaring wide as..." gets a
  plain verb ("came up"; tails "swept round").

## Build 230

Fixes from the 20-beat Ripples vs Nerine submission fight (build 228).

- **No throat grip from the ground** (`holds.ground_reach`): a fighter lying down can't put a new grip on a standing
  fighter's head, neck, throat, shoulders or back (sitting up, only her head is out of reach). The director is told to
  grip low or get up first. Beat 19 had Ripples, face-down, choking a standing Nerine and then getting up inside it.
- **The director's words no longer tell what wasn't rolled** (`holds.unrolled_words`): a hold worded as a throw to the
  ground loses that clause, and a breather "wriggling free of her jaws" loses it once nothing holds her.
- **Get-up tries in order:** a left-out first try goes in front of a "second attempt" already told, not in front of
  the moment she stands. "Lurched up" counts as on her feet, so the get-up isn't added twice.
- **A blow on one side isn't told by the other** (`narration.guided.sided_check`): Aqua Tail on her right thigh was
  counted as told by "her left thigh twitched", and a fact line for a part a blow only jarred no longer stands for the
  whole blow.
- **Made-up hit counts put right** (`narration.hit_counts`): "Ripples had landed one hit so far" takes the real count.
- **A missed or turned-aside bite never meets her:** "the solid resistance of Nerine's leg against her teeth" after
  a bite she turned aside is caught.
- **Tense mended by the program first** (`narration.tense_words_first`): more common verbs, thoughts and speech left
  alone; the copy-editing call is made only when the swap can't mend it.

## Build 229

Fixes from a 20-beat Ripples vs Nerine submission match (lakeside, both on the legs, a tail knee lock, a root lever and a tail choke).

**Engine and director:**

- **A held fighter's escape never ends the hold by itself** (`holds.release_as_escape`, on). In beat 11 the director wrote a release of Ripples' root lever in words that were Nerine's escape ("head butts Ripples in the nose ... she writhes and twists to escape the hold"), and the lever simply ended after one beat. Now a release given to the holder in such words is the held fighter's try at breaking out, and the end-of-beat break roll decides it. A release that says she lets go is still a release.
- **A grip knows what holds her.** "Wraps her twin tails around her knee" came with no limb named, so the stat block said only "Left Knee", the beat card said "Ripples' grip", and the story had her claws tear loose from it. When the director names none, the limb is taken from its own words (a bite is the jaws).
- **The notes' feelings come in note form.** What a hurt part costs her ("her left knee badly hurt: worse footing, slower to push off") and her own grip held through a get-up are no longer whole sentences, because the model copied them in word for word ("Nerine's left knee was badly hurt: she couldn't push off or spring away as she could"; "Ripples' own grip on Nerine's Throat stayed on too: she did not let go of it"). "Put on the ground 3 times" is said in words.
- **The tap on her feet has one place:** the holder's arm. The story had copied "toward Ripples' arm or shoulder".

**Narration cleanups:**

- **Thoughts that run on are mended:** "*She's favoring that hip* Noting the slight limp" becomes "*She's favoring that hip*, noting the slight limp", and "*...* Ripples noted," gets its comma.
- **More of her past is cut:** "I've taken worse than this", "I've been here before, and I got out", "I've been hit before", "endured many times before", "a sound Ripples had heard before", "from the long day's running".
- **The tense editor leaves thoughts alone:** "*I need to end this.*" had come back as "I needed to end this".
- **Held, not pinned:** with no pin on (none in a submission match), "despite being pinned" and "keep her pinned" say held. Ears pinned back stay.
- **Left-out hits go before the fall they caused:** Nerine's foot was struck after she had already crumpled at the pine.
- **Smaller fixes:**
  - The narrator talking about its own parts ("That was for the next part.") is cut.
  - Body parts copied with capitals ("Nerine's Throat") are lower case.
  - "To a water type" is just her.
  - "But minor:" and "in a way that was still minor" are said plainly.
  - The "what the last moment left in her" idea is reworded: the story kept opening on "The last moment left her...".

## Build 228

Fixes from a Nerine vs Ripples submission fight (lakeside, legs focus, a knee bite that ended in a tap).

- **The tap-out is always told.** The draft left out the tap, and the short passage asked for it came back as one more blow ("Her muzzle took the next blow"), which nothing checked. Now that passage has to show the tap (or the pass-out): it is asked for once more, then said in one plain sentence. It always goes at the very end of the beat (`narration.tap_shown`).
- **The beat card names what the holds do** (`narration.card.hold_events`, on). The card listed only the blows, and because it "wins" over the notes, the model left out her refusals to tap (beats 4 and 5) and the tap itself. Every part after contact now gets a HOLDS THIS BEAT line: a grip closing (marked new, so it is shown clamping on, not already there), its pressure, her refusing to tap, a break-out, and, in the last part, the tap-out. A fighter who taps out or is knocked out that beat stays in the card's WHO and WHERE lines.
- **A second limb on a held spot keeps its grip** (`holds.second_limb`, on). Nerine's Tail Bind round the knee her jaws already held was folded into the bite, and its pressure was lost. Now both stay on ("her jaws and twin tails"), pressing at the stronger plus half the weaker.
- **Tapped out, not out cold.** The injury report said Ripples "is out cold" after she tapped out awake. It now says she tapped out.
- **Narration cleanups:**
  - "Ripples' thought: …" labels are cut, as "Her thought:" already was.
  - Pain levels copied as words ("was already very painful before this") become "already badly hurt".
  - Comparisons with her life before the fight go: "unlike anything she had ever felt", "from anything she'd felt before", "like she used to".
  - "Tasting blood" counts as blood in the mouth, so it needs a hurt mouth.
  - "It's going to break." counts as breaking bones.
  - "Ripples could see the damage she had inflicted", in a beat only Nerine struck, gets the right name.

## Build 227

**A full submission match, narrated by hand, and the engine fed from it.** `sim/test_fights/submission_varied/full_fight.md` is Ripples vs Nerine on seed 21, all 28 beats, about 17,700 words. Each beat is told in the same parts the program asks the narrator for: the side of the one who acts, up to the moment of contact, then the side of the one it happens to. It follows the engine's notes for every beat: hit sizes, lasting pain levels, sounds, which way she falls, and the refusal signs the dice picked. `Ripples_vs_Nerine_full_fight.html` is the same fight exported with both fighters' cards on every beat. `replay.py` rebuilds it.

**Submission holds get their own ideas and finished lines** (`narration.sub_blocks`, on). Before, a beat with a submission hold on got only general ideas: reactions, thoughts, breath. Now each part is also offered one idea and one finished line for what the hold is like by now, from the side the part is told from:

- `sub_held` (story_blocks.txt and story_lines.txt) is for the one in the hold: she works out that nobody is counting; the slack she won was only a breath before the next crank; she watches a cloud because it is easier than the knee; pride is the last thing holding her.
- `sub_hold` is for the one holding it: she settles into it like someone threading a needle; her own grip tires and she holds anyway; a refusal only means the hold needs more; she feels a give in the joint and doesn't like it.
- They go by how long the hold has been on (`held: early, middle, long`) and how badly the worst held part hurts (`level`).
- In a beat where the engine has already picked her sign of refusing to tap, ideas that are a second sign (a bitten lip, a "no", stopping fighting the hold, tears) aren't offered.
- `false` turns them off.

**More sample passages.** `style_sample_scenes.txt` has 16 new sections from this fight, written with {A} and {B} so they show in any fight:

- `sub start` and `sub start take` are new tags, for a submission hold locking on. They are asked for ahead of the coil and grab passages, so a hold that also binds with a tail no longer gets a chest-coil passage.
- Three new `tap resist take` passages, two `tap resist`, one each of `tap out` and `tap out take`.
- One each of `strike act` (a chop), `strike take mid` (a leg), `throw take`, `getup` (a failed try, then the slow way up), `dodge`, `resisted take` (water against a water body) and `breaking point`.

**More ideas and lines for the rest of a fight:** get-ups, landings, dodges, a watcher's thoughts, a weak water or ice hit on a water body, an off-target blow that missed the place it wanted, and leg hurts.

## Build 226

**Refusing to tap no longer runs the same three steps every match** (`narration.tap_build.vary`, on). Before, the first refusal was always a paw twitching toward the ground, the second always a paw touching it, and the third on always a flat, shaking paw. Now each refusal shows ONE sign picked by dice from a set for how near she is (`variety.tap_tell_first`, `tap_tell_closer`, `tap_tell_edge`): claws curling, a swallowed word, a paw she traps under herself, half a word turned into a snarl, a 'no' said out loud, tears she doesn't notice, and more. She never shows a sign she used in her last few refusals. How near she is goes mostly by how often she has refused. Pain far past what she can bear pushes it a step nearer, and one time in five she finds a little more in herself and it drops a step back.

- Past her limit she also gets a reason she is holding on (`variety.tap_reason`): pride, anger, that it is HER, hoping the grip slips, plain stubbornness, or a plea for it to stop on its own. The last two only come after she has refused a few times.
- The holder gets a feeling about it (`variety.tap_holder`): cold, respect, pity, impatience, worry that the limb is about to give, or her own tiredness.
- A choke's fight against the dark (`variety.tap_dark`) and the tap itself (`variety.tap_way`: slaps, frantic pats, a cry, one quiet word, her body giving in first) vary the same way.
- The narrator is told these are the program's picks, to tell in its own way or swap for a sign of the same weight. A general rule joins the prompt as well: what happens twice in a fight never looks the same twice, and stays plain rather than strange.
- `vary false` brings back the fixed three steps.

**High and low damage rolls are told** (`narration.roll_notes`, on). Every hit already rolls ±17% (`damage.roll`). A blow that comes up in the outer 30% of that range is now told why: it caught her just right, landed flush, found her breathing out; or she turned a fraction, half rolled with it, braced in time. Landings get the same (came down on an edge, or on the flat). Each hit keeps its own pick across the prompts it appears in, and recent picks aren't reused. The numbers don't change, so the balance doesn't either.

**Sample passages for submission matches.** `style_sample_scenes.txt` has new sections: `tap resist`, `tap resist take`, `tap out` and `tap out take`, written with {A} and {B} so they show in any fight. Each shows a different sign of refusing. A part of a beat now gets the passage for the side it is told from.

- Fixed: a beat where a fighter was only held, with no new attack, used the "two fighters sizing each other up" passages. It now gets hold passages.
- The hand-written narration of the scripted test fight (Ripples vs Nerine, seed 21: a heel hook, an escape, then a knee crank and the tap) is in `sim/test_fights/submission_varied/narration.md`.

## Build 225

**The beat card is on by default** (`narration.card.enabled`, now true). On the build-222 bench it was the better of the two: it stayed with the fight (both fighters' wounds, Nerine stirring, Ripples' bad footing) where the plain prompt drifted into scenery. Its thoughts were cleaner, and it had fewer warnings on the last beat. Its two faults there are what build 224 fixes:

- An earlier blow remembered as the wrong move: the INNER LIFE note now says an attack keeps the move it was. The card prompt gets this note as well.
- Stock tails and scenery lists: the filler trim cuts them after the model writes.

It costs a little more, about 20% more calls and time on that bench. With the card on, the WHO HOLDS WHOM note is left out, because the card's WHO and CONTACTS lines already name each grip's owners. `/set narration.card.enabled false` goes back to the plain prompt.

## Build 224

**Holds wear the part down before they tear into it** (`holds.slow_bite`, on). In the Ripples vs Nerine match, one grip on Nerine's hip took it from 10% to 293% damage in eight beats. As the hip's resistance fell, the hold's damage multiplier climbed about 4–5×, on top of the grip's own tightening. Now every hold that presses (submissions, coils and plain grips; not a pin's own presses) gets three changes:

- **A flatter climb.** The multiplier still climbs as the part softens, but only as (worn ÷ sound) ^ `exp`. At 0.5, a ×4 climb becomes ×2.
- **A light start.** A hold that doesn't already grind (submissions do) bites at `start_mult` (0.5) on a sound part, rising to its full bite on a worn-out one.
- **More wear.** Such a hold wears the part's resistance ×`wear_mult` (1.4).

The same hip grip held 8 beats now leaves the hip at 151% damage with 15 resistance left, instead of 277% with 40 left. Its damage still climbs every beat (6, 8, 11, 16, 17, 25, 33, 35%). Nocturne vs Ripples balance is unchanged: Nocturne wins 164 of 300, against 163 before.

**Narration:**

- **Filler trimmed** (`narration.filler_trim`, on).
  - The stock tails go: ", a stark contrast to…", ", a constant reminder of…", ", a testament to…". Whatever follows a ", but" stays.
  - A sentence that is only scenery (breeze, leaves, birds, lapping water, light, with nobody in it) is kept at most `max_ambient` (2) times a beat and once a paragraph.
  - A scenery sentence that repeats one from this beat or the last is cut.
  - The narrator is also asked for fewer of both.
- **Who holds whom** (`narration.roles_note`, on). While a grip is on, every part of the beat is told plainly who is gripping and who is held, so the two don't swap (the kimura beat had Nerine both holding and held).
- **Earlier blows stay what they were.** The notes on what has hit her before now say an attack keeps its own move. "The knee she had bitten into twice" was really a Quick Attack and a Water Gun.
- **Scraps from cuts are removed.** A sentence left starting mid-clause ("drifted to her, …") goes, and so does a paragraph left as one or two words with no ending ("I").

## Build 223

Fixes from the Ripples vs Nerine submission match (legs vs tail).

- **A tap-out ends the match.** The game loop only looked for knockouts and pins, so after Nerine tapped, `/auto` kept asking the director for beats with one fighter left ("attacker and defender must be different fighters") and wrote empty pause beats. Now the tap-out (or a pass-out) prints the winner and moves into the aftermath, like a knockout. `/undo` was working; it only had those empty beats to step back through first.
- **She taps out awake.** A fighter who taps starts the aftermath "awake but down", not "out cold". `finish.submission.tap_awake` (on); a pass-out still starts out cold.
- **The tap-out is always told.** A beat that ends in a tap-out or pass-out the prose left out gets a short passage for it, like any left-out event (`narration.tap_shown`, on).
- **Ended grips leave the positions line.** The director's "jaws on Nerine's tail base" stayed in it after every hold had ended; a grip on someone she no longer holds is cut, and "ON HER FEET, ON HER FEET" is said once.
- **Thoughts no longer run into the next words.** "*Shit* Her ears flattening as she grunted" becomes "*Shit*, her ears flattening as she grunted"; "*This is what I do best* A surge..." gets its full stop.

## Build 222

- **Wrist and ankle holds are harder to lock in and easier to get out of** (`submissions.small_joints`). This covers a submission whose hardest grip is on a paw, a hand, a foot or a talon, like the wrist lock, heel hook, toe hold or wrist bite.
  - **Locking it in:** when she goes for one, it locks only about half the time (`set_chance` 0.5). The more health the defender has lost, the more often it locks (+ `set_hurt` 0.4 × the health she has lost). When it doesn't lock, she gets her hands on it and the limb slips out: she turns with it, yanks it back, stiffens it, or scrambles free. Nothing is wrenched, no damage is done, and the opening is spent.
  - **Getting out:** once one is on, her break-free chance is ×1.5 (`escape_mult`).

## Build 221

More kinds of holds, on more of the body:

- **19 new submission holds:**
  - **Wrists:** wrist lock, kimura.
  - **Ankles:** heel hook, toe hold.
  - **Stomach:** body scissors, rear waist crush, stomach claw, knee on belly.
  - **Back:** bow and arrow, and a backbreaker over whatever she lies against.
  - **Tail:** tail fold, tail and leg stretch, and a tail bind, where twin tails bind her tail to her ankle.
  - **Quadrupeds:** wrist bite, hamstring hold, tail bite.
  - **Birds** (who had none before): talon clamp, talon wrist pin, tail stomp.

  Each one only goes on a body that has those parts and lies the right way.
- **New zones** for `/focus` and the fighters' game plans: `belly`, `back`, `wrists`, `ankles`. The game plan now picks from all of them, and in a submission match leans more toward the wrists, ankles, tail and back (`director.game_plan`).
- **Escape tries for the new holds** (`narration.hold_tries`): wrist, ankle, stomach and back holds have their own ways out, and tail holds have more.

## Build 220

Three things from Claude's own test-fight narration, put into the engine and the narrator:

- **What she tries to get out of a hold** (`narration.hold_tries`). Each beat she's held, the narrator is told one real way out of that kind of hold:
  - a choke: tuck the chin, haul the arm down for a breath;
  - a leg lock: turn with the twist, drop her weight, peel back a finger.

  Arm locks, tails, body holds and the head have their own. The tries she already made in this hold are listed, so she never tries the same thing twice. They go from thought-out, to wild once she's hurting or a few beats in, to spent near the end. The engine's "she fights the grip" note uses the same try.
- **The hold under the blow** (`narration.hold_tries.under_blow`). A blow that lands on her while she's held brings the reader back to the grip afterwards, still on under everything.
- **Game plans** (`director.game_plan`, `narration.plan_notes`):
  - Each fighter comes in meaning to take one part of the other apart: legs, neck, head, core, arms or tail. In a submission match it's mostly legs, arms or neck, finished with a hold.
  - A fighter with a `/focus` has her focus as her plan.
  - The plan is rolled from a copy of the dice, so it never changes the fight's own rolls.
  - The director is reminded of it on about a third of the beats.
  - The first beat shows each plan as a look and a thought.
  - On the 2nd, 4th, 7th and 11th time she lands on that part, the narrator is told it's her plan working. From the 3rd, the other knows it too.

## Build 219

- **Breaking out of a submission goes by her own health, like a pin.** Before, a fresh fighter had only about a 10% chance a beat to break a submission, and it barely changed with her health. Now a beat's chance comes from her health: about 33% at full, 25% at three quarters, 17% at half, 10% at a quarter. Below that it keeps falling, but never under 3%: very unlikely, never impossible. Over the three tries before the hold would turn into a pin, she gets out about 70% of the time from full health, 55% from three quarters, 38% from half, 12% from a quarter. It is a little higher when the holder is hurt or the grip is light, and still grows with every beat the hold stays on. In a submission match, any hold that hurts (a choke, a plain grip) is broken the same way, since any of them can make her tap (`match_holds`). Settings: `submissions.escape` (`points`, `grow`, `holder_hurt`, `grip_weight`, `floor`); `/set submissions.escape.enabled false` brings back the old chance.
- **No pins in a submission match.** With `finish.submission.enabled` on, there are no pins at all now. A submission held a long time stays a submission instead of turning into a pin, so only a tap-out or a pass-out ends the fight. `/set finish.submission.no_pins false` brings pins back. `/help switches` lists the submission match.
- **Words while she fights the tap.** In a beat where she fights not to tap out (or taps), up to two short spoken lines are allowed between the two, even if someone spoke the beat before. The holder can tell her low to give up, and she can answer through her teeth. The notes invite it. Her paw twitching toward the tap and stopping, touching it, then lying on it shaking, was already there. Setting: `narration.talk.hold_exchange` (`spoken` 2).
- **A submission goes on the side the direction names.** "Ripples hauls Nerine's left leg across a root" used to grip the right knee and hip (the more hurt leg). Now the grips go on the left one. With no side named, it still picks the hurt leg.

## Build 218

- **A hold costs even less health.** `holds.health_cap.health_mult` is now 1.1, down from 1.3. In the seed-11 submission match, health lost per beat of the second hold is now 42, 83, 68, 90, 89, then 143 in the last beat. Ripples taps at 637. The tap chances stay at 20%, 28%, 36% and 47%.

## Build 217

- **A hold on a worn part costs less health.** The extra health a soft, worn-down part costs (the bracket's health multiplier) went as high as x2.07 under a long hold. That multiplier did most of the late climb, more than `holds.build`. A hold (not a pin) now uses at most x1.3 there (`holds.health_cap`, `health_mult` 1.3). Named submissions take the lower of this and `submissions.damage_cap`.
- **Unchanged:** the part still takes its full damage and wear, and the pain behind a tap-out still climbs at its full rate.
- **In the seed-11 submission match**, health lost per beat of the second hold is now 44, 87, 75, 100, 100, then 166 in the last beat, where it was 232 in build 215. Ripples taps at 581 instead of 448. The tap chances are the same (20%, 28%, 37%, 48%).
- **Switch:** `/set holds.health_cap.enabled false` turns it off.

## Build 216

- **A long hold builds at three rates.** `holds.build` (a hold kept on bites deeper every beat it lasts) used one rate for everything: 0.08 a beat, up to x1.5. In the seed-11 submission match that put 232 damage into the last beat. It now has three:
  - **Pain** (what she must resist to keep from tapping): still 0.08 a beat, up to x1.5 (`pain_per_beat`, `pain_max`). The pressure to tap climbs as before.
  - **The gripped part** (its damage and wear): 0.04 a beat, up to x1.25 (`per_beat`, `max`). The limb still gets worse the longer it is worked.
  - **Her overall health**: 0.02 a beat, up to x1.1 (`health_per_beat`, `health_max`). A long hold wrecks the limb and makes her want to tap long before it empties her.
- Put the old behaviour back with `/set holds.build.per_beat 0.08`, `/set holds.build.max 1.5`, `/set holds.build.health_per_beat 0.08` and `/set holds.build.health_max 1.5`.

## Build 215

Holds you can picture. Switch it all off with `narration.hold_position.enabled false`.

- **Draw the position:** on a hold's first beat, the narrator is asked to set it out plainly, once: where each
  fighter is and which way she faces, what each of the holder's limbs grips and what she has free, where the trapped
  part points, and which way the force goes on it. Everything the held fighter does in it has to fit.
- **Blows from inside a hold:** a strike by a fighter whose hold is still on is told as coming from what she has
  free. If it needs a gripping paw, that paw comes off for the blow alone and the grip holds.
- **Taps she can reach:** a fighter held on her feet taps the holder's arm or shoulder, not the ground she can't
  reach. Refusals climb the same way as before.
- The re-run of the seed-11 submission match is rewritten to match: the first hold is drawn plainly in beat 19, and its
  taps in beats 20–22 and all of beats 27–32 follow it.

## Build 214

Tap-outs now build with the hold instead of jumping to a high chance.

- **The grip adds pain** (`finish.submission.tap.press`): how hard the hold is pressing right now counts as pain on
  top of the damage the part already carries.
- **Holds bite deeper** (`holds.build`): any hold kept on without breaking presses 8% harder each beat, up to 1.5×.
  This is on top of a tightening grip's own climb.
- **A ceiling that climbs** (`tap.climb`): the tap chance starts at no more than 20% on the first beat she can tap.
  It rises 10% each beat the hold stays on, up to `tap.max`. The ceiling is lowered by the health she has left:
  fresh, it is cut to 40% of that; at 57% health, to 66%. She can still break out every beat.
- `tap.span` is explained in the section's comments: how far past her limit the pain must go for a 100% chance.
- In the seed-11 submission match, Ripples now tapped on the second hold's fifth beat at a 40% chance (before: its
  third beat, at 70%).

## Build 213

- **Tap refusals that climb** (`narration.tap_build`): in a submission match, each refusal to tap to the same
  opponent is told further along than the last. The first time, her paw twitches toward the ground and stops. The
  second, it touches the ground and she drags it back. From the third, it lies flat on the ground, shaking, and she
  holds it still.
- **The holder's side:** from the second refusal past what she can bear, the holder feels the twitch through her own
  arms and her grip tiring. She thinks something of the other still refusing, and may say one low word.
- **After the tap:** the loser lies curled round the hurt part, and the winner stands over her.
- **Fixed:** on the beat a fighter tapped out, her posture line said "OUT COLD". It now says she is down and awake.
- The submission match's narration is rewritten in full as a sample. The match's scripts and bug list are in
  `sim/test_fights/submission_match/`.

## Build 212

- **Drawn-out cries** (`narration.sounds.drawn_out`): when a part that is very painful or worse is hit or wrenched on
  a fighter at or under 65% of her strength, her sounds can be long ones. That means an elongated yelp
  (*Yiiiiip—*), a scream that goes on, a choking squeal dragged out of her with every crank of a hold. Both the hit
  sounds and the reactions under holds use this.
- **Fixed:** a blow with a conjured weapon (the ice blade), or with a fin's edge, was told as "delivered with her
  teeth" or "with her claws" because of words in the order.
- The submission-match test fight is in `sim/test_fights/submission_match/`.

## Build 211

More variety without hard caps, and new things checked against the fighters' bodies so nothing impossible goes on.

- **No caps.** No hold or move is ever locked out for being used. The director is shown which holds have been used,
  and which attacks a fighter keeps reaching for (`director.worn_after`), only as a nudge toward something new.
- **Invented submissions.** At a submission opening, the director may make up a hold of its own: a name, the parts it
  grips, and what grips each. The engine checks every grip against both bodies:
  - the parts must be hers;
  - the grip must use a part the holder really has, so no paws on a bird, no jaws on a beak, no tails on a fighter
    without one.

  An invented hold is then a submission like any other: it wrenches every beat, can make her tap, and counts among
  the holds used.
- **Every grip is checked the same way:** holds and pins too.
- **Improvised attacks:**
  - Their names must use a body she has ("talon rake" is refused for a Buizel).
  - Their type must be Normal, Fighting, one of her own types, or the type of a move she knows. Ripples (Water, and
    Ice Fang) can improvise Ice; Nerine can't improvise Fire.
- **Conjured weapons** (`moves.conjure`): a fighter may make a weapon of her own element and keep it for a few beats:
  an ice blade frozen out of the lake, a whip of water. While she is ARMED, her improvised blows land as its type, x1.2.
  The narrator is told when she makes it, that she still has it, and when it gives out.
- **More holds:** sleeper hold, head scissors, triangle choke, knee bar, and a coil crush (tails wound round the ribs).
- **Grinding holds** (`submissions.grind`): a submission works a part down rather than smashing it:
  - about half the usual damage on a part that's still sound, rising to x1.3 on a part worn to nothing;
  - the part's toughness worn twice as fast.

  So a hold hurts little at first and more every beat it stays on, and a second hold on a limb already worked bites
  far harder.
- **A higher bar for fresh fighters:** tap-out resistance at full health is now 160 (was 130). A healthy fighter
  still can tap, but later.
- **Fixed:** a pin by a bird could be told as "her beak, teeth pressed hard into it".

## Build 210

**Submission matches** (`finish.submission.enabled`, off by default: `/set finish.submission.enabled true`). Only a
TAP-OUT or a PASS-OUT ends the fight, and no blow knocks anyone out.

- **Tap-outs are resisted while she can.** Each beat after the second in a submission, choke, coil or any other hold
  that hurts (not a grab, not a pin), two things are weighed:
  - **The pain she must resist:** the gripped part's damage, a share of the other gripped parts, and more each beat
    the hold stays on.
  - **Her resistance:** her overall health. An adrenaline surge raises it.

  Only pain past her resistance can make her tap, and never on the first beat it gets there: that beat she holds on
  through it. Near or past her limit, the narrator is told she is fighting the urge ("SHE WON'T TAP"). A healthy
  fighter can still tap, but only to a part that is very badly hurt and a hold that has been cranked.
- **Pass-outs.** A choke (a grip on the neck or throat) builds air hunger every beat against her endurance, which is
  also her health. Past that she may pass out ("SHE FIGHTS THE DARK" while she holds on). A pin held to its end still
  puts her out.
- **The stat lines and notes** show the tap-out or pass-out, and the winner by submission or by pass-out.

**New submission holds:** figure-four leg lock, ankle lock, scorpion lock, chicken wing, surfboard stretch, and:
- Ones a Pokémon's body makes possible: a tail-bound knee crank and a tail strangle (for a fighter with tails), and a
  jaw lock on the knee.
- Ones that use the scenery: a root lever (the knee bent back over a humped root or a ridge of rough ground), and a
  trunk arm wrench (round whatever she lies against).

**Holds go on the hurt side.** A leg lock grips the leg that's already damaged, and its second grip is on the same
side.

**Variety:** the director is shown the holds used so far as a nudge toward new ones (build 211: no cap on any of
them).

**The director in a submission match** is told:
- Blows only soften her up.
- Work toward holds, and be inventive with them: tails, jaws, coils, streams, the scenery, improvised holds with any
  limb.
- Which holds are used up.
- **Work the hurt part:** each opponent's worst limb, which holds grip it as she lies, and to keep punishing it
  until she gives.

**For every fight:** an attack a fighter has thrown `director.worn_after` (4) times among the last twenty is named
to the director as worn out, with a push toward an improvised technique of her own body or a use of the scenery.

## Build 209

The Glacia vs Swift fight, narrated a second time from only what happened in each beat, without the narrator's
notes: `sim/test_fights/glacia_vs_swift/Glacia_vs_Swift_unguided.html`, from `narration_unguided.md`. It has the same
view as the guided export. Set against the guided version, two things stood out, and both are now in the program and
switchable:

- **What she has learned of her** (`narration.style_read.opponent_read`, from `read_from`, every `every` beats). In
  the unguided telling, the thoughts are mostly each fighter reading the other: she laughs when she's hurt, she keeps
  going for my wing, she keeps getting up, and the reader's view changes as the fight goes. The narrator now gets
  each fighter's read of the other from what has really happened:
  - the part she keeps coming back to;
  - the move she reaches for again and again;
  - how many times she has been put down and got back up;
  - how many attacks she has slipped.

  It also gets permission to let her view of the other shift: wariness, respect, irritation, pity or wanting it over.
- **Quiet beats told short** (`narration.rich.quiet_mult`, 0.55). A beat where nobody is hurt (a breather, two
  attacks cancelling out) used to be asked for the full ~750 words and came out padded. It is now about 410, which
  usually means one part.

Also fixed: `replay.py` (the export of a hand-narrated fight) dropped the last beat's narration. The Glacia vs Swift
export sent with build 208 had no story for beat 26; both exports are now complete.

## Build 208

From test fight 6: Glacia (Articuno) against Swift (Swellow) on the mountain shelf, knockouts only, no pins. It is in
`sim/test_fights/glacia_vs_swift/`:
- **`Glacia_vs_Swift_full_fight.html`:** the full fight as the game's own export. It has the hand-written narration,
  each beat's health and part damage, the fighter cards with damage marks, and the stat lines and rolls.
- **`replay.py`:** remakes the export from `narration.md`.
- The bug list.

This fight is meant as the baseline for comparing the real narrator's output.

Notes fitted to the fighter's body:
- One helper now rewords the newer notes for the body they describe: a wing for a paw, a beak for teeth, her own
  covering for fur, and nothing about standing or getting up while she is in the air. It covers the opponent-watch
  signs, still feeling it, old wounds, stumbles and where-it-shows tells.
- A bird nursing a hurt keeps it guarded, her beak smoothing the feathers there.
- A hurt flyer seen from outside has signs of her own: ragged wingbeats, losing height, flying lopsided.
- A tail now has its own old-wound reaction, so it is no longer treated as a leg.

Flight:
- When a flyer's time in the air runs out, she comes down and lands, and the note says so. It no longer says she
  "shakes off being in the air".
- A dodge in the air says she stays up, not that she stays on her feet.

Moves:
- Wing moves (Steel Wing) no longer take a weapon from the director's words ("rakes" made it a claw strike).
- Slashes thrown from range (Air Slash) have their own body detail, not "the claws catch first".
- A whole-body move's "hardest hit" sizes now match its per-part lines.
- Whole-body moves no longer get the "reactions climb" note.

Scene and summary:
- "On dry land, not in the water" appears only where the arena has water.
- The injury report names a move whose description starts with a verb by its name ("Glacia's Freeze-Dry", not
  "Glacia's flash-freezes the target").

## Build 207

From test fight 5: Ripples against Nerine in the lakeside clearing, knockouts only and no pins, with Nerine played as
a brawler. It is in `sim/test_fights/ripples_vs_nerine/`: the narration written by hand from the engine's notes, the
engine log, the scripts that played it, and the bug list.

New, and switchable (`narration.style_read`, on by default):
- **How each has fought so far.** From the fourth beat on, every third beat, the narrator is told how each fighter has
  really been fighting, counted from her attacks: up close and physical (grabs, throws, slams, charges into the
  scenery), from range, or trading blows. That way a fighter keeps the style she has shown, even when her description
  says she usually fights another way.
- **The same place again.** A fighter put into a tree, rock or wall she was put into earlier remembers it as she hits
  it.

Narration fixes:
- The opponent-watch signs rotate and come in one part of the beat, not every part.
- Taking stock of her own wounds happens once a beat, and a wound comes up again only when it gets worse or after
  `narration.rich.wound_watch_again` (5) beats.
- "Her reactions climb" no longer says the last blow is the worst when it wasn't. It names the worst blow instead.
- "Still feeling it" names at most the worst two parts, and says "them" for two.
- A fighter held only by the leg or neck is no longer "held with nothing free to cover herself".
- A blow that shakes her grip loose no longer also says "she keeps her grip". One grip on two parts comes off in
  one line.
- No percentages are given to the narrator when a grip is shaken loose.
- "Not very effective" no longer says her body shrugs off a charge into a tree or a blow that did a lot of damage.
- The off-balance wear-off has a lying-down version.
- Light grips on the neck or throat get choke reactions, not "unbothered".
- A hit on a downed fighter no longer says "she stays down" when she gets up later in the beat.
- "Ripples's" is fixed in about a dozen notes, stat lines and story-line slots.

Engine fixes:
- BOUND and CONSTRICTED end once the coil that caused them is off.
- "Arms trapped in the coils" now applies only to coils round the body.
- A slam says "slammed down", not "thrown".
- The injury report's words follow the pain level, so an excruciating chest is no longer "sore and stiff tomorrow".

## Build 206
**Hurt that shows, and builds.** Each part is switchable in rules.json.
- **Her own wounds** (`narration.rich.wound_watch`): from the second beat, the fighter whose part it is takes stock
  once of her worst wounds: how they feel, what they stop her doing, a glance at them, what she thinks. Only wounds
  that are new or worse are offered, so the same sore head isn't gone over every beat.
- **Reading the other fighter**: two or three visible signs of the opponent's hurt are picked from how far gone she
  is and where her worst wound is: her body rising and falling with each breath, an eye half-closing on each breath
  out, winces, a sway, weight kept off a leg, a limb held close. The watcher notices them and makes something of them.
- **Struggles that build** (`narration.build_up.holds`): every beat a hold, pin or coil goes on, the held fighter
  fights it harder: she tests it, then squirms, then thrashes, then fights in desperation. When it is very painful,
  the struggle also climbs within the part.
- **Old wounds** (`build_up.old_wounds`): a hard blow or landing on a part that was already hurting can take her over
  for a moment, depending on where it is. A hurt back: she twists and arches, or rolls and curls on the ground, grabs
  at the spot and rubs it, gasping. A hurt side: she curls round it. A hurt leg: she hops off it. It happens 60% of
  the time, more for a landing, throw or slam.
- **Reactions that climb** (`build_up.climb`): several blows in one attack get reactions that grow, the last the worst.
- **Still feeling it** (`build_up.carry_on`): a part hurt like that, or left excruciating, is felt for two beats after.
  She nurses it, winces when she moves it, and favours it as she gets up.

Fixes from an audit of the narrator, the stat blocks and the engine:
- The get-up note, the arm and paw words, and the claw and blast words are matched more exactly.
- The body detail for a blow fits the body, and no motion is suggested for a fighter in the air.
- /more and interludes reset the get-up state.
- The stat blocks show two close numbers with enough decimals to tell them apart, and use "an" before lowercase vowels.
- Deep water: "across" no longer counts as being in the water, and "shallow" water isn't taken as deep.
- The inner-life and fight-chronicle tallies skip self-hits and confused hits, count a landed status move, and credit
  reflected hits to the right fighter.
- An early return from a guard gives a last stand back. A pin takedown clears where she was lying.
- The fight summary names the loser correctly in fights of more than two.

## Build 205
Fixes from an audit of `/bench` and `/sets`:
- **The newest saved beats are kept.** Saved beats were sorted by file name, so after a few fights (fight10 before
  fight2, a new run's fight1 before last week's) the newest could be deleted the moment they were saved, and `/bench`
  told old beats. They are sorted by when they were saved now.
- **A saved beat that can't be read is skipped** (a broken file, or one from an older build) instead of closing the
  game. A report or `/sets all` file that can't be written gives a message instead of a crash.
- **Both tellings use the model you have now**, not the one active when the beat was saved, and an override of
  `narration.phrase_memory.*` takes effect.
- **After `/bench`, `/set narration.phrase_memory.*` works again** (the phrase memory had kept a detached copy of the
  settings), and the game's dice are no longer left on the bench's fixed seed.
- **Windows paths keep their backslashes** in commands (`/sets all C:\Users\night\out.md`).

## Build 204
An audit of the code added in builds 198-203. Seven bugs, all in the new clean-ups and checks, each of which could
spoil good prose or miss what it was meant to catch:
- **The camera clean-up cut real movement.** "Pulling back, she struck again" lost "Pulling back". Only a real camera
  move ("Pulling back from the fighters, the clearing...") is cut now.
- **"Eight beats ago" was missed** at the start of a sentence (capitals), and "a few beats ago" would have become
  "a few earlier".
- **The blood clean-up could leave a broken sentence** ("The fur was matted with blood." became "The fur was.");
  it now keeps "The fur was matted."
- **The italics fix could strip real thoughts.** A thought about the other fighter ("*Ripples is favoring her left
  arm; she can't hold that guard forever*") lost its italics. Only past-tense narration that opens with a name does.
- **Aqua Jet counted as swimming on dry land.** A fighter using a Water move this beat may be carried by water on land.
- **The wrong-limb check misread whose paws were whose.** "Ripples' paws scrabbled at the grip" (her own paws) was
  treated as the holder's, and "Nerine's paws" was read as Ripples' paws, which hid a real mistake.
- **The beat card listed landings and scenery as attacks** with no attacker ("?'s"). They are left to their own lines.

## Build 203
- **A takedown is never left out.** When a pin starts on a fighter who was on her feet and neither the drafts nor
  the fixes told how she was taken down (beat 3 of the build-201 fight started with her already pinned), the program
  puts in a plain sentence of its own at the start: who took whom down, the way the engine rolled (a shoulder drive,
  a sweep...), and the parts the hard landing hit.
- **The wrong-limb check reads both sides at once** ("her paws dug into Ripples' upper arms" when knees hold one arm
  and jaws the other), and also checks the grips that an escape ended this beat.

## Build 202
Fixes from the first fight on build 201 (Ripples vs Nerine, 4 beats):
- **The type matchup is never named in the story** ("but she knew it was not very effective on her").
- **Any short sound in brackets is set as a sound** ("a quick chirrup of surprise (Prrt)" -> "*Prrt*"), not only the
  ones on the old list. Fighters' names in brackets are left alone.
- **A menu of reactions copied from the notes keeps its first choice** ("her eyes squeezed shut or watered").
- **A thought left open is closed after its first sentence** ("...sharp and clear: *Not stuck. She could feel..."),
  and the marks are checked once more after the last cuts of a beat.
- **Narration is never set in italics.** A paragraph in italics that talks about a fighter by name in the third person
  ("*Nerine's eyes narrowed as she watched her opponent...*") loses the marks; real thoughts keep them.
- **The attacker's part stops at contact.** The parts before the receiving one are told that how the blow lands on her
  belongs to the next part (beat 1 had the Aqua Jet's effect on Nerine told twice, once from each side).
- **The "bruise that was already there" pin idea** is only offered when she already carries a hurt.

## Build 201
- **The beat card (`narration.card`, off by default).** A short block at the very end of each part's prompt, right
  before the model writes:
  - WHO: each fighter, her kind and her role (holding, held, free);
  - WHERE: posture, and in the water or on land;
  - CONTACTS: every grip as owner's limb -> owner's part, both named;
  - THIS PART: what lands in this part and how much it hurts now (dodges, counters and new grips included), or that
    nothing lands yet;
  - MIND: two INNER LIFE facts for the fighter the part is told from;
  - JOB: the part's number, length, side and focus.

  With two of the same kind it asks for every paw, tail and jaw to be named with its owner. Nothing in it is new: it
  repeats the notes' facts in one place. Try it with `/bench 3 narration.card.enabled=true`, or turn it on with
  `/set narration.card.enabled true`.
- **No swimming on dry land.** The narrator now knows who is in the water (from where the director places each
  fighter), the posture line says it, and a sentence that has a fighter on land swimming, diving in or driven through
  the water by her tails is caught. The old tails check let any sentence that mentioned water through.
- **The wrong limb on a grip is caught** ("the twin tails tightening on her left upper arm" when the tails are round
  her right paw and her paws hold the arm).
- **Grips are said with their owner in the notes** ("with Nerine's twin tails", not "with her twin tails").
- INNER LIFE no longer says "nothing of Ripples' has touched her yet" after a counter has hit her.

## Build 200
The problems left open after build 199:
- **A pin that starts after this beat's attack isn't told before it.** The parts before the blow lands are told that
  the pinner is not on her yet (beat 22 had Nerine "settling onto Ripples' chest" before the Water Pulse).
- **A bite is never told as a claw stroke.** The director's flavor for a bite move ("ice-fang swipe") has its
  swipe/slash/claws turned into a bite and fangs.
- **The "stroke from hip to shoulder" story block** is only offered for a blow to the chest, belly or back (it was
  offered for an ear slash, and the narrator turned it round onto the attacker).
- **No blood where nothing has cut.** "Matted with blood and dirt" on a fighter, or a named part, that only blunt
  blows, water and grips have hurt loses the blood (a bite or a claw anywhere on her lets it stand).
- **No salt by a lake.** "The salty tang of the lake" and "brackish" lose the salt, unless the place is the sea.
- **A lone present-tense sentence is mended.** The copy-editing call only runs when a part has two or more of them;
  one on its own ("Her heartbeat thuds in her ears") now has its common verbs put into the past without a call.
- **A pain change copied from the notes is cut** ("a brutal squeeze, hurting → very painful").

## Build 199
Fixes from the 29-beat Ripples vs Nerine fight:
- **A grip torn off by a hit is no longer told tightening first.** The notes had said both "the hold tightens" and
  "the hit breaks her grip", and the prose had Nerine clamp down harder after the ear slash freed Ripples.
- **After a pin knockout, the loser stays out.** Any part after she faints is told from the winner's side, with the
  loser out cold (no eyes opening, no last thought).
- **Left-out passages go before the escape.** A pin press the drafts skipped is put in front of the paragraph where
  she breaks out, not after it.
- **Scenery that breaks under a held stream has to be named** (the fallen trunk in beat 13 was never mentioned).
- **No blackout in a beat where nobody goes out** ("And then, nothing.", "everything went black").
- **More cleanups:**
  - the model's own remarks ("It is now written.", "The paragraph above has a word count of 60.");
  - the notes' labels ("Inside it and past it:", "Her thought:", "Her voice:");
  - camera moves ("Pulling back from the fighters, ...");
  - "eight beats ago";
  - runs of bare sounds ("Pip. Yp. Eek.");
  - a sentence cut off at a name;
  - "a sound she knew well", "not one she was unfamiliar with", "a familiar and comforting smell";
  - INNER LIFE's wording copied ("it's the place to go for") and the look-at-her-body idea copied word for word;
  - empty paragraphs.
- **Interludes get the same last clean-up as beats** (the leaked word-count line came from one).
- INNER LIFE now asks for thoughts in the fighter's own words, never the line as written.

## Build 198
- **No more Spyder kernel crash after closing the window mid-beat.** A closed window (or one from an earlier run)
  could be cleaned up from the game's thread while it was still writing its last beat. Tk only allows that on the
  main thread, so the kernel died with "Tcl_AsyncDelete: async handler deleted by the wrong thread". Windows are now
  kept until the session ends, and their check-box settings never clean up off the main thread.

## Build 197
- **`/bench`: the narration test bench.** Each beat's narrator inputs are now kept in bench_cases/ (the last 30;
  `narration.bench`). `/bench 2 narration.rich.length_mult=1.0` tells your last 2 beats twice, once with your settings
  as they are (A) and once with the changes (B), and compares them:
  - words and paragraphs;
  - model calls and seconds;
  - rewrites;
  - which checks fired;
  - repeated 5-word runs.

  Both tellings of each beat go side by side to bench_reports/bench_<time>.md. Nothing in the fight changes, and the
  stock-phrase, story-block and check memories are put back after each telling, so a bench never wears them. Slow:
  each beat is two whole narrations. More beats give a fairer comparison, since the model's own sampling varies
  between tellings.

## Build 196
- **Build 195 would not start** (a quote mark in the version line): fixed.
- **Things in order:** a passage for something the drafts left out (an attack, a landing) is put in front of the
  get-up, not after it.
- **The get-up is told once:** the parts that don't tell it are told so (before it: she is still down; after it: she
  is up).
- **Fragments cut:** a sentence left starting in lower case where another was cut ("was the only thing that moved...")
  goes.
- **Story lines that fit:** "I've been slow all fight" only for a fighter who is losing or level; the feint line no
  longer speaks of a feint.
- **Shorter interlude with rich narration** (`narration.rich.interlude_words`, 500), and it gets the INNER LIFE facts.
- **Console:** the director's line no longer gives the attacker's move to the defender ("Ripples' Ice Fang" on
  Nerine's Ice Fang); the summary lists the knockout last in its beat.

## Build 195
Fixes from the user's full Ripples vs Nerine fight (10 beats, 2.5-7.5 minutes each):
- The body note no longer ends on a fixed line ("the sting or ache settling into the neck, the fur lying wrong over
  it" came back word for word); it asks for what the blow leaves, in the narrator's own words.
- The grip-stays-on note for a get-up is in note form ("GRIP STAYS ON: ...") instead of a sentence the model pasted in.
- "Familiar" is cleaned in any form ("a familiar comfort", "the familiar smell of her home"); sound tags "(Yaah)",
  "(Waah)", "(Yowl)" become italics like the others.
- Nerine's Bite reads "a hard bite, quick as a snap" (the injury report cut "a hard, quick bite" to "Nerine's hard").
- The console no longer says "a Aqua Tail".

## Build 194
Fixes from the user's Nerine vs Ripples beat 1 (10.5 minutes, the same blow told four times):
- **Richer narration is shorter by default:** `narration.rich.length_mult` 1.5 (was 2.0).
- **One telling a blow:** with the rich body detail on there is no "linger on one moment" note as well
  (`narration.rich.no_linger`); the body note says it belongs to the blow's one telling; a fighter who rolls through a
  fall is told falling and rolling once, never "staggering" from the blow again later in the beat.
- **Quicker checks:** the body-detail ideas no longer say "bone" (it set off the broken-bones check and its rewrites).
- **"Not very effective" isn't a shrug** when the blow knocks her down or throws her into something.
- **Hands are hands in a landing:** a Buizel's paw in a landing is marked as her hand, thrown out to catch herself.
- **The first beat has no past:** the first beat says nobody has been hit yet (no old injury or favoured side); "a
  familiar and comforting aroma" / "a smell she knew well" lose the "familiar" and the "knew well".

## Build 193
- **`/sets`: every setting there is.** `/sets` lists the rules sections and how many settings each has; `/sets
  narration.rich` shows one section's explanation and each of its settings as a `/set` line ready to copy, with its
  current value; `/sets pin` finds every setting with "pin" in its name or note; `/sets all` writes all ~1,200 of them,
  section by section with their explanations, to all_settings.md.
- **`/intro off`** skips the opening passage that sets the scene (the first Enter starts the fight); `/intro on` brings
  it back. Same as `/set narration.scene_intro false`.
- **/help** has the richer-narration switches under `/help switches`, `/sets` under `/help settings`, and both in the
  quick start.

## Build 192
- **Richer narration (`narration.rich`, on; `/set narration.rich.enabled false` turns it all off).** Slower beats,
  longer prose:
  - **Longer beats:** twice the words by default (`length_mult` 2.0, so most beats are told in three parts), each part
    asked for at least one paragraph per ~110 words, and the beat's time budget doubled to match (`budget_mult`).
  - **The body under each blow:** every blow that lands gets ideas for how it works on the body in that instant,
    picked by the dice from where it lands, what kind of blow it is and how hard: the pressure of contact, the head
    snapping round from a blow to the cheek, fur and skin stretching along a cut or round teeth, and what it does inside
    and past the part (the shock ringing through her teeth, a clenched jaw knocked open, eyes watering from a blow to
    the nose, the arm going dead from a shoulder hit, a cut that stings a beat late). The narrator may invent more like
    them; a fighter held fast gets the pressure and the give, not the movement, and nothing is added that the engine
    didn't resolve. `body_detail` false turns it off.
  - **Inner life from the engine:** the engine keeps what each fighter has learned this fight (`fight_record`, undone
    and saved with the fight): her moves that land and miss, the move that keeps hitting her, the attacks she has
    dodged, what her worst wounds now stop her doing, how tired she is, the wound she can see on her opponent, what
    the last beat cost her. The narrator gets it as INNER LIFE, for thoughts and plans that reason from the fight.
  - **One sense a part:** sound, smell, touch, temperature, taste or light, whichever the fight has used least.
  - **Closing thoughts:** the last part of a beat gives each conscious fighter a few sentences of her own mind, and one
    more italic thought is allowed per part.
- **A new fighter: Nerine,** a second Buizel with no flotation sac. A quick, showy hit-and-run striker: Quick Attack,
  Aqua Tail and Bite in place of Ripples' Crunch, Hydro Pump and Ice Beam; harder paws, fins and tails, a little
  thinner through the back and hips. Health 1775: she beats Ripples about half the time in simulated fights. `/newfight Nerine Ripples`.
- **Fixes from the full-fight review:**
  - Carry-over damage only to parts that touch the one hit (the right upper arm no longer carries over to the left
    fin; `moves.auto_spill.carry_next_to_only`).
  - A fighter knocked down onto the beach or into the shallows is driven down into THAT (and gets up off it), not the
    arena's ground word.
  - A fighter who attacks from the ground gets up only after her blows, in the prose too.
  - The pummel's answer is printed after the blows it stops; the last-stand header shows energy going to 0.
  - Summary: a whole-body move isn't named for one part, a last-stand blow isn't listed twice, the knockout blow is
    listed.
  - Soaked is topped up in the water but still counts down; no "now exhausted" after the fight is won.
  - Guarding notes give one way of covering a part ("a shoulder hunched up over it"), and "her shoulder or limb or body"
    menus copied into the prose are cut to the first; a reminder that her past is this fight only.

## Build 191
Fixes from the full Ripples vs Nocturne fight (23 beats):
- **Soaked is said when it starts.** A fighter placed IN the water by the director's positions ("in the shallows")
  gets a console line, "💧 Ripples is soaked: she is standing in the water", so a later ×1.5 electric hit has a cause.
- **No borrowed elemental moves.** An improvised blow named after a real Electric/Fire/Water/etc. move the fighter
  doesn't know (Ripples' "Thunderbolt") is refused and the director told to use her own moves or name the blow by what
  it is. Body blows that are also move names (Headbutt) are still fine.
- **Get-ups happen where she lies:** "using the shallows" or "the sand" from the director's positions, not always the
  arena's ground word ("the grass").
- **No status on a fighter already out** (the frozen that never ended).
- **Console:** rolls that round to the same whole number show a decimal (63.2 vs 63.0), so a "tie" no longer looks
  decided both ways; hold changes read "power 8 → 26, then steady"; the "(moves.aim)" code name is gone.
- **Prose clean-up, no extra calls:** pain sounds in brackets, "(Hnk)", become *Hnk* in italics; camera lines on their
  own ("Wide shot.") and bracketed asides about "this part" / "the next part" are cut; "the other Absol" becomes "the
  Absol" when there is only one; a NOT VERY EFFECTIVE blow that was devastating or left a part very painful is no longer
  described as one her body shrugs off.
- Not changed: the grab's "about 25% now" was right when the grab started; the second chain link tightened it to power
  26, so the next roll was 11%.

## Build 190
- **Builds 188-189 merged with the latest trial fixes.** Everything from 188 (undo and saves keep all state, audit F)
  and 189 (damage marks, status looks and poses on the pictures) is here, together with:
  - **Your direction can ask for a devastating blow:** "devastating" in a typed direction makes the first blow that
    lands that beat devastating, no roll (`/play dice strict` keeps it to the dice).
  - **A submission on a fighter put down that beat:** a direction opens it even when she was standing as the beat began.
  - **Holds in the paragraph plan** (guided narration): a grip taken this beat is a step of the plan, and put back if
    the draft never shows it closing.
  - **Notes copied word for word are cut:** a sentence copying ten words in a row of the beat's notes goes.
  - **Kicks get no hand staging,** and "her arm" on a four-legged fighter becomes her foreleg.
  - **`/stop`** in the window ends an `/auto` run after the beat being written.
  - **The stock-phrase memory** (`/phrases`): stock phrases are rested for a while after use, across fights and runs.
- **A rebuilt /help.**
  - The long rules section is now four topics: balance, narration, settings, switches.
  - `/help switches` lists the on/off settings people ask about, each with its command (knockouts only, no pins,
    guided narration, shorter notes, the "staying with the damage" parts, the context window...).
  - `/help <any word>` searches every entry (`/help knockout`, `/help tumble`), and `/help <command>` shows that
    command's own entry first.
  - Stale defaults are gone (/scale, /healthloss, /length), and /length moved out of the pins section.

## Build 189
- **Damage marks on the pictures** (the **Damage marks** switch in the window; `window.damage_marks`). From
  `marks_from` (30%) damage on, each hurt part shows the marks of what hurt it, and they get worse as the damage climbs:
  - claw slashes that bleed and trickle
  - bite punctures in two jaw rows
  - bruises that darken and split
  - scorch and char from fire
  - lightning burns
  - frost crystals
  - grip marks from holds and pins

  A ruined part (300%+) is swollen and dark. Fresh wounds (this beat or the last) look brighter. Each part's marks
  stay in the same place from beat to beat and only grow. They show in the window, in its history, and in
  `/exportfight` pages. Fights exported before this build show the glow only (they have no wound data).
- **Statuses show on her** (`window.status_look`): frozen is iced blue with crystals, chilled a frosty tint, soaked
  wet with droplets, paralyzed crackles with sparks, poisoned and burned tint her.
- **The glow is half as strong while the marks are on**, so the marks read (`window.glow` false turns it off).
- **Poses** (the **Poses** switch; `window.poses`). How a fighter is placed changes her picture:
  - **With your own picture:** `images/<name>_pinned`, `_pinning`, `_faceup`, `_facedown`, `_side`, `_sitting`,
    `_air` (or `<species>_...`), each falling back to the nearest one you have, then to `_down`. Click a label, then
    the picture, to place her parts on a pose picture: they are kept separately for each picture.
  - **Without one** (`window.pose_fallback`), the program poses her own picture:
    - on her back (turned over), flat on her front, on her side, sitting
    - braced on top when she is pinning someone
    - raised high when flying
    - on a ground line with a soft shadow

    The marks follow her parts into the pose.
- **Lying on her side actually lies down now.** Before, every picture tipped over by only 16°: the artwork comes on
  a square canvas, so the old rule always thought she was already lying flat. Now it goes by the shape of her body.
- **Damage marks know more attacks:** a move missing from `moves.json` is still read by its name (a plain Slash is
  claws, not a bruise).

## Build 188
- **/undo and saves bring back everything.** Before, some state lived outside what /undo and saves knew about,
  so an undone beat could leave traces and a loaded fight could lose them:
  - which prop a fighter collapsed against
  - where a burn sits
  - the story's memory of how each fighter feels (an undone pin left her "just out of a pin" and "relieved")
  - tactical reads
  - when the arena last acted, and the arena's own dice (an undone arena event didn't come again when replayed)
  - who is off balance or rocked, stiff-but-not-cold slowness
  - the last pin shape
  - when a grip was torn free (it was never saved at all)

  Saves now write sets properly, and anything that still can't be written is reported instead of dropped.
- **The regression suite guards it** (`python sim/regress.py`):
  - Every attribute the engine holds must be listed in `engine.py` as either undone and saved (`_SNAP_FIELDS`,
    `_SNAP_EXTRA`) or per-beat scratch (`_NOT_SNAPPED`). New state can't be forgotten without a failing test.
  - Save/load must bring all of it back exactly.
  - A beat undone and played again the same way must give the same stat block and state.
- **A frozen flyer drops out of the air** (so does one put to sleep). Before, she stayed IN THE AIR, frozen solid,
  out of reach of every close attack.
- **Taking off says what it lets go of.** A grab or hold she had ends on screen and in the story ("lets go as she
  takes off"). Before, it vanished between beats.
- **A reversed grab is told.** Two fighters grabbing each other in one beat: the first grab turning round on its
  owner is shown and narrated.
- **A diving flyer can't also pummel.** A strike with a count from the air on a fighter who is down is one dive, not
  a dive and a flurry of blows "over her".
- **No charge into a fighter up in the air.** After a launch, a charge (or a held stream pinned against the scenery)
  from the ground doesn't follow up in the air: she lands first. From above it is still a spike that drives her down.
- **Your own /pin or /grapple on (or by) a flyer brings her down** for it, on screen and in the story. Before, she
  could be pinned and still in the air, out of reach of the pinner's own blows.
- **Failures aren't silent.** A few steps that fall back quietly when something breaks now write what happened to
  `errors.log` and say so once:
  - the story state, the pin shapes, the /checks tally
  - the narrator's last review
  - saving a picture's part points
  - an unknown arena in /simulate
- **One possessive rule** (`engine.poss_word`) instead of five copies.
- **The folder is a git repository now.** The first commit is build 187 exactly as it was, so any change can be
  looked at or taken back (`git log`, `git diff`).

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
  and if it happens in the air she falls. In the air she dodges on her wings, not her legs: a hurt wing (the worse one counts most), hurt flight muscles (shoulders, chest, back) and, a little, a hurt head all make her swerve late, and the edge the air gives her fades as her wings fail (`flight.dodge`). **Sky Drop** carries the other up and drops her from a height (the higher,
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
- **Fewer pins, faster wear** (build 133). Pin openings now come at half the old rate by default (`/pins`: 0.5, about 5 pins a fight instead of 8; `/pins 1` brings back the old rate). Body parts lose resistance faster (`resistance.loss_per_power` 0.25 -> 0.4) and the damage curve is steeper both ways: a solid blow on a fresh, sturdy part does little (an Iron Tail on Ripples' chest: about 25%), but each blow wears the part and the next lands harder (40, 90, 185, 330%...). No single blow takes a part from sturdy to red (`max_loss_per_hit` 35). To keep fights about as long as before, each point of damage costs a little less health (`health.loss_per_damage_point` 0.2 -> 0.155). The stomach and belly weigh more on overall health (1.3 -> 1.5); crests, plumes, beaks, wingtips, tail feathers and flames weigh little.
- **Reactions follow health AND the hurt part** (build 133, `narration.reaction_caps`). At 70%+ health a fighter covers even a ruined part: clearly in deep pain, a sharp cry at most; a devastating blow lifts that one step, to a brief scream. At 40-70% she may scream but doesn't writhe or convulse (a devastating blow doesn't lift it further). Under 40% there is no limit. More impact, pain and held-in reactions in story_blocks.txt, including covered pain for strong fighters and raw pain for spent ones.
- **Collateral is a roll** (`moves.auto_spill.chance` 0.9): most single-spot blows jar one or two parts around them at half power, some land clean. A spread move aimed at one spot jars too, and an eye, ear or jaw hit usually jars the head itself.
- **Flying is encouraged** (build 133). Each beat there is a chance (`director.flight_chance` 0.3, x1.5 when the opponent has nothing that reaches the air) that the director is reminded a winged fighter on the ground could take off, with what her opponent could still hit her with up there; one already in the air is pointed at a dive or Sky Drop (`director.air_attack_chance` 0.35). The director is told flying is a winged fighter's strength, used every few beats rather than rarely. Charizard and Dragonite count as winged.
- **Knocked out of the sky; flying on a hurt wing** (build 133). A blow that lands on a fighter in the air may knock her down (`flight.knock_from_air`: 25%, plus more the harder the hit and the worse her wings, at most 90%); she falls and lands. A hurt wing no longer grounds her outright: past 100% damage on her worse wing, taking off costs more energy (20 instead of 8 at 250%) and every beat she stays up tears that wing further (`flight.strain`). Only a shredded wing (600%+) can't lift her. The director is told the cost, so flying on a ruined wing is a gamble it can choose. Cinder's moves were given back a little power (Ripples now beats her about 57%).
- **Roster balance** (build 133). Every fighter's body now averages 92-100 resistance (Nocturne and Ripples sit at 93-96), each body keeping its own shape: tough parts stay tough (up to about 170) and soft ones soft. What a fighter lacks otherwise is made up in her move power: each fighter's own moves were scaled (x0.5 for Tidecrest and Gloam up to x2.2 for Sable) until she wins roughly half her fights against Nocturne and Ripples, so type matchups still decide a lot (Ripples beats Cinder about 64%, Aura's Fighting moves beat Nocturne, Dark Nocturne shrugs off Sable's Psychic moves). Tidecrest and Gloam: health 2100; Kindle and Sable: 1450. Nocturne: health 1680, winning about 60-64% against Ripples (Ripples unchanged).
- **Fight length (`/length`)** (build 133). Presets for fights of about 30, 35, 40, 45, 50 or 60 beats (60 is the default). A shorter preset makes fighters lose health and wear down faster; pin openings and escapes stay the same, so because a pin's success follows the pinned fighter's remaining health, pins simply win sooner and there are fewer of them. Measured over 200 simulated fights each: 30 -> 31 beats, 2.7 pins; 35 -> 36, 3.2; 40 -> 41, 3.6; 45 -> 45, 4.0; 50 -> 49, 4.4; 60 -> 62, 5.6. Nocturne won 60-68% at every length. Below about 27 beats fights stop getting shorter: pin openings set the floor.
- **Submissions that become pins** (build 133). A submission still on after `submissions.becomes_pin_after` beats (4) becomes a pin: the pin clock and pass-out start, but the grips don't ease into lighter pin pressure: they keep wrenching at full power and keep building, so a submission left on too long gets dangerous.
- **Free blows during pins and submissions** (`holds.free_blow`). Now and then (5% a beat) the one holding her gets a quick extra blow in with what she has free: one of her own moves at 40% power. Separate from the punishment for a failed escape.
- **More fighters** (also on the bench). Flyers: **Cygnet** (Swanna), **Duchess** (Unfezant), **Valor** (Braviary,
  Sky Drop), **Swift** (Swellow), **Zephyr** (Pidgeot), **Pyra** (Moltres), **Glacia** (Articuno), **Ember**
  (Talonflame), and the winged dragons **Cinder** (Charizard) and **Tidecrest** (Dragonite), who have arms as well
  as wings: they hold and pin like bipeds and can still take off. On the ground: **Gloam** (Goodra), **Kitsune**
  (Ninetales), **Kindle** (Vulpix), **Sable** (Fennekin), **Dusk** (Lycanroc, Midday Form), **Vixen** (Thievul).
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
- **Reactions follow the gradient.** How tough a part still is now comes in finer words that soften as gradually as
  the numbers ("sturdy, barely marked", "starting to give", "soft, giving under blows", "thin, close to giving way").
  A part that has gone soft but doesn't hurt much yet gets its own note: it's holding, and won't hold many more. A
  blow coming at a part that is soft or badly hurt: she sees it coming and flinches before it lands, and the attacker
  sees her protecting it (new story blocks for both sides). A ruined part hurts at the slightest touch: even a brush
  gets a real reaction (fresh, a cry; worn, a scream; spent, the rawest), and steady pressure on it in a hold or pin
  is agony. Under 30% strength she is past restraining her body's reactions: the rawest level now has her body
  reacting on its own (jerking and curling, a limb scrabbling, shaking she can't stop). Still no sobbing, and no
  vomiting or retching (the narrator's checks now catch those words too). This rawness is only WHERE she is badly
  hurt: a blow on a part that was untouched still stings and jars what's round it, but it isn't agony however
  worn she is; even a devastating blow on an untouched part is a deep shock and a cry, not the raw breakdown.
- **Status effects are told in three parts.** When a fighter is flinched, dazed, off balance, doubled over,
  breathless, sputtering, stiff, cramped, bound, constricted (and the old ones: paralysed, frozen, asleep, confused),
  the narrator is told the visible tell (her head jerks away, her eyes lose focus, she stumbles past her own blow),
  that she knows it is happening to her, and that her opponent sees the opening. A blow thrown into that opening (the
  engine's caught-open bonus) is called out: she tries to cover it and is too late, and it lands harder for it. When
  the status wears off, she shakes it off on the page too ("the world settles back into one piece; she finds Nocturne
  again"). New story blocks for the tell and for the opponent reading it. Nothing about the numbers changed.
- **End-of-fight summary.** Under the injury report after a win: the key moments in order (devastating blows, big
  hits, juggles, bitten feints, last stands, clashes, reflects, blocks, crashed charges, frenzies, pins, escapes,
  adrenaline), how it was finished (who pinned whom, how long, what put her out and at what strength), the turning
  point (the beat the winner went ahead by 5+ points for good, or "ahead from the first beat"), damage dealt by each,
  the biggest blow, the loser's worst injuries and what caused them, pins and escapes for each, and what decided it.
  `/summary` shows it again. The narrator gets a version without numbers for the aftermath, so the fighters can look
  back on a moment or two. It is kept through /undo, saves and loads. `rules.json` "summary" sets how many moments
  (10, at most 3 of a kind) and what counts as a big hit (9% of max health) or a lead (5 points). It only reads what
  happened: no dice, no balance change (`/simulate` gives the same results as before).
- **Fixes found in test fight 2:** a BLOCK now lands once on the blocking limb (it used to land there once for the
  blow and again for each knock it would have jarred around the target, and the screen still named those other
  parts), and a blocked blow no longer knocks her down or throws her: she caught it on her guard and kept her feet.
  This makes blocks slightly more protective than before; they are still rare (4% at full strength). A move she
  uses on herself (Mirror Coat, Protect, the weather moves) no longer shows a type matchup against her opponent
  ("Psychic vs Dark: no effect"). Status lines read as words ("doubled over", "off balance", "furious") instead
  of "doubled_over"; the fury after a long pin says what it is instead of borrowing the cramp's line; "down 1 beat".
  For the narrator: the fury after a pin was being described as a cramp from bearing down (to the one who'd been
  pinned); it is now a cold anger with harder blows. Statuses wearing off read as words ("shakes off being
  furious", "the surge drains out of her") instead of "being fury" / "being adrenaline". "For the third time",
  not "3th". Self moves no longer appear in the fight-so-far list as "Rain Dance → Nocturne's" with nothing after.
  Who is ahead, late in a fight: a few points of strength now count for more when both are low (9% against 15% is
  no longer called "ahead" for the one at 9% just because she has fewer badly hurt parts). Story only: no balance
  change.
- **Throat pins with tails or coils finish as a choke.** A pin can hold the throat with anything that fits the
  body: jaws closed on it, a forearm or foreleg barred across it, tails or coils looped round it. All of them choke
  her out. Tails or coils round the throat used to be told as a "constriction" (her circulation cut off, her heart
  slowing), the way coils round the chest are; now they are the choke: her air going. Coils round her body are
  still the constriction. As before, about a fifth of the time the pain under the press gets there first when
  the pressed parts are badly hurt. The pass-out line no longer repeats the part ("her jaws, closed on the throat",
  not "...on the throat on her Throat").
- **Blood choke or windpipe choke, by the grip.** A throat pass-out is now told the way that grip would really do
  it. Anything that closes round the SIDES of the neck is a blood choke (the blood to her head cut off: pressure
  behind the eyes, a roaring in the ears, the world greying and shrinking to a point, quick at the very end, often
  before she is short of air): tails or coils looped round it, jaws closed over it (either fighter), Ripples' paws
  closed round it or her arm locked round it, and legs locked round it (Ripples' legs, Nocturne's hind legs). A
  forearm, foreleg, knee or weight barred or pressed across the FRONT is the windpipe (the breath that won't come,
  whistling and burning, then the grey as the blood goes too). A four-legged fighter's forepaws and forelegs can't
  close round the sides, so they always press the front. The console, the fight summary and the narrator all say
  which. Tails wound round the throat during a hold now feel like the blood choke too.
  The director's pin options follow the same bodies: the sleeper hold (an arm locked round the neck from behind)
  is now only offered to a fighter with arms that can lock (Ripples, not Nocturne); new options are a throttle
  (both paws closed round the sides of the neck, knees on the chest) for a fighter with hands, and a leg scissor
  (legs locked round the neck from the side) for any fighter whose legs still work. How fast she goes under is
  unchanged: this is how it is told. Check after these and the block fix: 400 fights at your settings, Nocturne
  63.5% (±2.5), pins 4.8 a fight, 73% of fights with 4+.
- **Breaking points from squeezes, too.** When a part first turns excruciating or devastated, the narrator gets a
  BREAKING POINT (slow down, the sound she makes, her body and thoughts). It used to fire only for blows: a hold or
  a pin pressing a part over the line (tails tightening on a throat, a pin's weight on a ruined chest) went by
  without one, and so did whole-body hits. Now all of them count. At most two a beat as before, but the worst go
  first: a part turning devastated is never dropped in favour of one turning excruciating.
- More pin positions: standing on the throat (a foot or a paw), a knee across the neck, a four-legged fighter's
  foreleg clutch from her side, the flat of a tail across the throat, a headlock, a crucifix (both arms trapped),
  a body scissor. Jaws or hands closed round the throat are told as both chokes at once (air and blood).
- **Submission holds (very rare).** Wrestling holds that WRENCH rather than pin: a camel clutch (sitting on her
  back, hauling her head and chest up by the chin, or by the scruff in the jaws), a crossface, a Boston crab, an
  armbar, a leg lock, a tail crank, and for a four-legged fighter a limb wrench (a limb clamped in the jaws, twisted
  and shaken). Which ones fit depends on both bodies and on how she is lying (face-down for a camel clutch, face-up
  for an armbar...). They do damage every beat, harder each beat (power 16 +3 a beat on the main grips, 9 +1 on
  the bracing ones), for at most 3 beats, then the holder lets go, spent. They are NOT pins: no clock, nobody passes
  out. The one held can't get up while it's on, breaks out at 0.8x the usual hold chance, and anything thrown at
  her meanwhile lands x1.25 ("locked in a submission hold, nothing free to cover up with"). The holder can use what
  she still has free: Ripples in a camel clutch has her mouth right at the back of the Absol's head (a jet of water
  there as a second action in the same beat); Nocturne holding one with her jaws still has her horn and her tail.
  An opening is rolled each beat on a fighter who is down and not pinned or held (3%, x1.5 under half strength);
  the director is told the hold, what it does and what's left free. At your settings that is about one
  submission in 30 fights. Director action "submission" with the hold's name in "improvised_name";
  rules.json "submissions" holds every number. 400 fights at your settings with them in: Nocturne 62%, pins 4.9 a
  fight, 75% of fights with 4+.
- **Pins use more of her.** Most pins now press three to six points at once, filled out from whatever the pinner
  has free: jaws pressed into the neck (unless something else already has the neck), her chest against the other's
  chest (or her weight on the back, face-down), her paws gripping the other's forelimbs with the claws digging in,
  her feet or hind paws pressed into both flanks, tails across the legs. About one pin in seven stays a simple two-
  point pin; 85% have three or more, over half four or more (rules.json pin.contacts.weights). The director is told
  the same. More presses means more pressure: 400 fights at your settings, Nocturne 58% (it was 62%; within the
  noise, ±2.5), pins 4.8 a fight, 71% of fights with 4+.
- **Submissions, final build.** No cap on how many: the opening chance on a fighter who is down and not pinned or
  held went from 3% to 60% a beat (rules.json submissions.chance), and a submission opening is now offered BEFORE a
  pin when both are open (it used to lose to the pin every time). That gives about one submission a fight (0.88 in
  400 fights). They run up to 10 beats (was 3). Breaking out: the plain-hold chance x0.8, growing +30% for every
  beat it has been on (up to 85%), so a long one gets harder to keep on. Unless she is STUCK (under 25% strength,
  or a part it wrenches is at 300%+ damage): then it doesn't grow (x0.6 instead), a pin opening on her is always
  there, and the director is told to let it go into a pin or hurt her another way with what is free. A pin the
  holder starts replaces the submission. In the dice fights they last about 3 beats (longest 10): about 60% end with
  the holder letting go into a pin, 40% with the held one breaking out.
- **More pins: about 8 a fight, and they follow how hurt she is.** The chance of a pin opening each beat now slides
  with her strength instead of jumping at half strength: on her feet 12% at full strength, 27% at 85%, 50% at 70%,
  76% at 55%, 86% under half; on the ground 50%, 59%, 73%, 89%, 95%. Each badly hurt part (150%+ damage) adds 3.5%
  (up to 30%): her opponent knows where she's hurt. There is no time factor: pins come more often late in a fight
  only because she is more hurt by then. (director.pin_urge: standing 0.1 → 0.12, downed 0.4 → 0.5, weak_standing
  0.45 → 0.85, weak_downed 0.85 → 0.95, new curve 1.3, hurt_bonus 0.035, hurt_cap 0.3.) 400 fights at your
  settings: 8.0 pins a fight (was 4.8), 95% of fights with 4+, 0.86 submissions a fight, Nocturne 59.5%. Fights are
  shorter in beats (about 50, was about 75) because pins end them sooner.
- **Plans: setups and payoffs.** The engine now notices when a fighter has set something up, watches for the
  payoff, and tells the director and the narrator, so a plan can run over several beats and actually pay off:
  - Setups it recognises: her opponent SOAKED (dragged into water, a water move, a wave) while she has lightning
    (it goes through a soaked body far worse); the RAIN called by a fighter with water moves; the SUN by one with
    fire. Each one waits up to 3 beats for its payoff (tactics.payoff_beats; a soak only as long as it lasts).
  - The director gets a PAYOFF nudge while a setup is waiting ("Ripples got soaked through 1 beat ago. Now:
    Thunderbolt into her while she is still soaked"), ahead of a pin opening. Now and then (30%) it also gets an
    idea: drag a downed opponent into the water to set up the lightning, call the weather before using its
    moves, or READ a trap: don't throw a blast into a Mirror Coat, wait out a Protect, strike from range at a
    Counter. It is asked to put the plan in "intent".
  - The narrator is told when a beat is a setup ("THE PLAN": one short thought shows it, in her own words), when it
    is the payoff ("THE PAYOFF": it was planned, and the other realises too late what the earlier move was for),
    and when a fighter reads a trap and goes round it.
  - The screen shows them as 🧠 lines (Plan / Payoff / Read). Kept through /undo, saves and loads.
- **The injury report reads like a person wrote it.** Each fighter gets a lead that fits how it ended ("won, and it
  cost her", "won, barely, and every step home will tell her so", "lies out cold, and when she wakes it will all be
  waiting for her"), then her worst parts with WHAT DID THEM in plain words (from the moves' own descriptions: "the
  weight of Ripples' pin", "Ripples' crushing bite", "the blow Nocturne struck breaking free", "her own dark blast,
  sent back at her") and what she'll feel, worded differently from part to part and fighter to fighter ("black
  with bruising, stiff and swollen for days", "stiff by morning and tender to the touch", "a dull ache, gone in a day
  or two"). It is the same on the screen and for the narrator's aftermath.
- **Pained sounds are described, not just mentioned.** Every narrator prompt now says: never just "a small sound";
  say what it is (a hiss through the teeth, a whine high in the nose, a choked gasp, a yelp, a growl ground out, a
  cry that cracks in the middle), where it comes from, and its shape and pitch, bigger and less controlled the worse
  it hurts; and now and then write it out as one italic word mid-sentence (*Hhk*, *Nngh*, *Hss*, *Kh-hah*), never in
  quotes (that would count as speech) and never ending a paragraph (that would trip the trailing-dash check). It is
  fitted to each fighter's voice from fighters.json (Nocturne growls and hisses until it breaks through; Ripples
  chitters, squeaks and barks). About 180 tokens a prompt; rules.json narration.sounds.enabled turns it off.
- **Sounds more often, and your call.** By default every hit, grip or squeeze that hurts now gets a sound (it used to
  be left to the model), and about every other sound is written out. /sounds always | often | sometimes | rarely
  sets how often a hurt fighter makes a sound (the badly hurt places always get one, except on "rarely"); /sounds
  write often | sometimes | rarely | never sets how often it is written out; /sounds on | off. Saved to rules.json
  (narration.sounds.how_often / write_out).
- **Bodies you can see.**
  - Every press in a pin or a hold now says what it LOOKS like, by how hard it is: light, the fur flattened and
    parted, the grip's shape printed into it; firm, the muscle pressed flat and the flesh bulging round the edges;
    heavy, sunk deep and everything round it pushed out of shape. On a joint (shoulder, knee, hock, hip, upper limb,
    tail), a firm or heavy press forces it toward the edge of where it bends, the limb at an unnatural angle (bent,
    never broken); on the throat, a visible dip.
  - VISIBLE WEAR now shows the marks of what did the damage, deeper the worse the part is: claws leave scratches,
    then raked furrows, then the fur torn away in strips; teeth leave tooth marks, then puffy rings of them; blows
    ruffle the fur, then show bruising dark through it wherever it parts; grips crush the fur flat in the shape of
    the grip, then ruffle it into ridges with bruising beneath; lightning frizzes and singes it; cold leaves
    frost-burned patches. Ears, noses and fins get creased, bent or pushed crooked for now. Up to four parts per
    fighter, kept the same from beat to beat.
  - Shaking is never vague any more: whenever a fighter shakes, trembles, jerks, thrashes or writhes, the narrator is
    told to say where and how (a foreleg trembling at the elbow, the head shaking side to side, claws scraping at the
    ground again and again, twisting at the hips, the back arching) and how hard and fast.
  - Wording variety: eight ways to describe each strength of press (light, firm, heavy), eight for a joint forced
    toward its limit, five for the throat; five for each depth of each kind of mark (claws, teeth, blows, grips,
    lightning, cold) and four for each creased or swollen ear, nose, fin, cheek, muzzle and jaw. Which one is used
    changes from beat to beat and part to part, and the same part keeps its look for the same damage.
- **Blows move bodies.** Now and then (40%, more when it hits hard or she is under half strength) a blow that lands
  comes with how it MOVES her, as part of the same instant: a slash sweeps the struck limb along the line of the cut,
  spins her a quarter turn or sends her staggering sideways; a blunt blow knocks her back a step, snaps her head
  back or buckles her knees; a bite yanks her toward the biter; a blast shoves her back skidding; lightning locks
  her rigid; cold makes her recoil; on the ground she is rolled half over or shunted along. Five or six wordings for
  each. Never with a knockdown, throw or launch, never while she is pinned, held at point-blank or pressed against
  scenery, and she always stays where the engine has her (on her feet, or down where she lies).
  rules.json narration.impact_motion sets the chance.

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
- **More of everything (reactions, voices, blow sounds, breakouts).**
  - **Impact reactions:** about 20 wordings for each size of blow (glancing, solid, heavy, tremendous). Each hit also gets a body-region tell, with 5 to 8 options per region.
  - **Her voice on every hit:** each hit line carries the sound she makes, written out (for example *Hff*, *Ki-ki*, *KYAAAAH*). It depends on how hurt the part now is and how much strength she has left.
    - The four tiers are low, mid, high and raw. A fighter under 30% strength never goes below mid.
    - The voice is fitted to the fighter: growling, chirping, or other. There are 6 to 10 sounds per tier for each voice.
  - **The sound of the blow:** a line on every landed attack, by kind: claw, bite, blunt, blast, water, shock or cold, with 4 to 6 wordings each.
  - **Hold reactions:** every press in a pin or hold now says how she reacts, by pain level. There are 10 to 12 wordings at every level, low pain included.
  - **Breakout attempts:** 16 kinds of escape try instead of 6. The new kinds are headbutt, bite, hip escape (shrimp), roll, claw, pry the grip, tuck a leg in, go limp then explode, reach and haul, and a point-blank burst of power. Each kind has 3 or 4 wordings.
    - A failed bite, claw, headbutt, kick or burst is told as doing no damage. The engine never rolled damage for a failed try, so the story mustn't invent any.
    - The mix is under `variety.struggle` in engine.py.
  - **Impact motion:** `narration.impact_motion.chance` raised from 0.4 to 0.55.
- **Failed get-ups can hurt.** When a failed try drops her back down hard (her legs give out, or she slips), there's a 60% chance it jars something (`getting_up.fall_chance`).
  - It hits the limb that gave out, or what she lands on, with a small jolt (`fall_power` 8, ±25%).
  - Sinking back dizzy or out of breath never hurts.
  - It shows on screen as "💥 the drop on try N hurts" and goes to the narrator as a real hit.
  - Balance check after these changes (400 fights at your settings): Nocturne 59.0%, 7.6 pins a fight, 93.5% of fights with 4+ pins, 0.82 submissions a fight.
- **Fix:** the 🧠 plan line crashed whenever a new setup was made, because the payoff text was built even for setups. It now only builds the line it needs.
- **Play as fighters (`/play`).** Play as one fighter (`/play Nocturne`), several, or all of them (`/play all`). `/play off` hands everyone back to the director.
  - **Each beat:**
    - The prompt becomes `Nocturne > `.
    - Before it, a panel shows her strength, her state (standing, down, pinned, held, holding), her moves with any uses left, and this beat's openings on each opponent: whether a pin is open, and a submission when one is.
    - Type her move in plain words, for example "slash at her face" or "I bite her throat and hold".
    - Press Enter to let the director choose for her this beat, or type `wait` to have her hold back.
    - With several played fighters you're asked for each in turn, and who goes first rotates every beat.
  - **The director's job:** it turns your words into actions and never adds, changes or chooses actions for a played fighter. It then runs the fighters you don't play; by default each of them answers your moves every beat (`play.ai_answers`).
    - The dice still decide what lands, dodges and escapes.
    - If the director can't turn your words into a valid action (for example, a pin with no opening), you get the reason and can try again.
  - **Openings:** a played fighter gets the same dice-rolled pin and submission openings as everyone else, shown to you before you choose. `play.free_pins: true` lets her always try a pin.
  - **Direct control:** every /command still works at the `Nocturne > ` prompt (/strike, /pin, /down, /getup, /undo, /auto…), so you can decide outcomes yourself at any time. A /command typed at a later fighter's prompt runs instead of that beat.
- **Dice for the fighters you play (`/play dice fair|strict|free`).** The setting is saved as `play.dice`.
  - **fair** (the default): the dice decide, and your /commands can still force any outcome.
  - **strict** (at the mercy of the dice):
    - Pins, submissions, getting up and escapes happen only when the dice allow.
    - Your commands follow the same rules as the director's choices, and their openings are rolled first.
    - Typed directions no longer open a pin.
    - Commands that decide an outcome or edit the fight are refused while you play: /pinsuccess, /pinescape, /getup, /down, /land, /eliminate, /heal, /restore, /face, /part, /fighter, /extendpin, /pinclock, /hazard and /undo. After the match, /getup and /recover still work.
  - **free** (the dice are off for your fighters):
    - Their attacks always land, with no dodge, block or deflect.
    - Pin and submission openings on their opponents are always there.
    - They get up at the first try.
    - A pin breaks whenever they try to escape it, and any hold on them breaks at once.
    - Rolls against them, such as their own dodges, still count.
  - In every mode, a beat's openings are rolled once. A refused attempt doesn't roll them again, so retrying can't fish for an opening.
- **Play-as test (Ripples, fair dice) and the fixes it found.** The fight is in `sim/play_ripples_fight.py`, played through the real play-as path. Run 2 (seed 2) is narrated in `sim/play_ripples/`, with its transcript.
  - **Play-as fixes:**
    - A player's order is never refused for repeating a move, and it lands where she said; the director doesn't re-aim it.
    - The director's ideas for played fighters are filtered out of its prompt. A new hint for the fighters it runs names moves they haven't used lately (`director.move_variety`, 0.35).
    - The panel shows energy and conditions. It marks moves she's too tired for and hold-only moves, and says plainly when she can't act (flinched, asleep, frozen).
    - The panel hides pin openings while she is pinned or pinning, and shows a pin as OPEN only when the pin rules allow one.
  - **Engine fixes:**
    - Pin descriptions match how she lies: no foot on the throat of a fighter lying on her front (the grip takes the back of her neck instead), and no hold "from behind" on one lying on her back.
    - A sleeper or dunk turns her onto her front.
    - Two fighters locked in a hold or a submission can't dodge, block, deflect or clash with each other.
    - A fighter working a submission gets her own posture line (LOCKED ONTO … in a …) instead of ON HER FEET.
  - **Wording fixes:**
    - Pins are told in beats, not seconds (the screen banners and the fight summary).
    - Self moves have no target in the notes.
    - Breather and hold-continues lines name who is resting and aren't repeated.
    - No movement line when the blow itself knocks her down, or for a fighter who has hold of someone.
    - An escape is no longer called "a pin is kicked off".
    - Possessives fixed ("Ripples's").
  - **Balance after the fixes** (400 fights): Nocturne 57.0%, 7.5 pins a fight, 93% of fights with 4+ pins, 0.88 submissions a fight.
- **Condition-based sensitivity and building pin pressure.**
  - **Condition (`resistance.relative`):** a part's resistance is measured against how it started.
    - A part starting at or above `sound` (85, a normal sturdy part) behaves exactly as before.
    - A part starting lower, such as a soft throat, a fin or a fighter's weak spot, counts as sound and shows green while untouched, so a gentle brush there is little.
    - Its condition falls a bit faster than a normal part's: it wears ×(start/85)^`wear_exp` (0.6).
    - Every blow on it lands ×(85/start)^`vulnerability` (0.35) harder: a start of 63 gives ×1.11, a start of 25 gives ×1.53.
    - The damage and health curve, the colour icons and the narrator's "toughness" all follow condition. The screen still prints the real resistance number.
  - **Per-hit cap (`resistance.max_loss_per_hit`, 0 = off):** the most one blow can wear a part. It counts in condition terms, so no part is spared.
    - At 35 it is what keeps a green part out of the red after one devastating blow: with the recommended curve it lands at condition 50, at the yellow/orange edge.
  - **Pin pressure ramp (`pin.ramp`):** each press of a pin bites ×(1 + 0.12 per beat held), up to ×1.6 by the fifth beat. This evens out pins against the struggles and blows of the one underneath.
  - **Balance** (your settings):
    - Current curve: Nocturne 58.5% (200 fights).
    - Recommended curve (`resistance.smooth.points` [[15,2.0,2.8],[40,1.35,1.9],[60,0.75,1.15],[85,0.3,0.7],[120,0.12,0.5]], `/resscale 1`, `max_loss_per_hit` 35): Nocturne 62% over 400 fights, about 64 beats a fight, 9.3 pins and 1.1 submissions a fight.
- **Part damage numbers climb slowly past 300%, and numbness is temporary.**
  - **Part curve (`damage.part_curve`):** a part's damage number counts every blow in full up to 300% (devastated). Past that it climbs ever more slowly: about 630% after another 700% of blows, and about 1,100% after 3,000%.
    - Health, the size of the blow in the story, and everything that reads the blow use the full amount, so fighters lose exactly as much health as before.
    - The screen shows both: "+X = power × …, (the part counts +Y)".
    - In a full test fight the highest part reached 567%.
  - **Numbness (`numbness`):** a devastated part (300%+) hit hard (40%+) goes numb 30% of the time, for 1–3 beats.
    - The pain cuts out, replaced by a dead, strange heaviness and shock, and blows there land as a dull jolt and a lurch of nausea.
    - Then it wears off and the pain floods back: the narrator gets THE FEELING COMES BACK, and the screen shows 🫥 … the numbness wears off.
    - It can't go numb again for 4 beats.
    - The old permanent "numb with shock" level at 1000%+ is not used while this is on.
  - **Balance:** Nocturne 57.5% on the current curve, 60% on the recommended one (200 fights each).
- **Bigger narrator window (`narration.context_window` 12288 → 20480).**
  - At 12k the prompts were full, about 10,400 tokens on a typical part and up to 11,900. The story so far was being trimmed to almost nothing, so the model wrote each part with almost no memory of earlier beats.
  - 20k fits everything with real story memory, and no detail is cut.
  - To make it fit on a 16 GB card, start Ollama with `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0`. That stores the context at half size, so 20k takes about the memory 12k did.
  - Check with `ollama ps` while a fight is running: it should say 100% GPU. If it shows a CPU share, set `/set narration.context_window 16384`.
- **Faster beats, nothing dropped (`narration.reader_timing` "beat").**
  - The second reading now checks each part once the whole beat is written: each part against the text before it, with the same rules and limits.
  - Before, it ran between parts, and its prompt pushed the narrator's long prompt (about 10,000 tokens) out of Ollama's memory, so every part re-read it. On a partly-CPU setup that's about 45 s a part.
  - Paragraph rewrites already reuse the cached prompt. `"part"` = the old order.
- **Defaults are now the settings the balance is tuned for:** damage scale 5, health loss 0.2, resistance scale 1, the recommended resistance curve with `max_loss_per_hit` 35, and the permanent numb level off (temporary numbness replaces it). Your own `my_settings.json` still wins for anything you saved; `/settings` lists those, and `/settings forget` drops them.
- **Fewer wasted rewrites (build 114).** False alarms that cost rewrite calls, found in a live fight log:
  - **"stray electricity":** the defender's clash move (a Thunderbolt meeting a Hydro Pump) now counts as this beat's electricity, and lightning seen earlier in the fight may be remembered later.
  - **"pin clock":** in a beat with no pin, an ordinary sentence like "Two seconds later…" is no longer taken for a pin count. Only an actual countdown is.
  - **"broken bones":** "something in her snapped" (her temper) no longer counts as a bone.
  - **Prose checks relaxed:** stock phrases and small sensory touches are guidance only, never a rewrite.
  - **"too much talking" (the most common rewrite in the log):** the narrator was checked against a limit on italic thoughts and spoken lines that it was never told. Each part's prompt now states the allowance up front ("TALK IN THIS PART: at most N italic thoughts…"). Written-out sounds (*Eek-*, *Nngh*, *Hhaaah-hah*) no longer count as thoughts. Nothing is cut; the model just gets the limit before writing instead of after.
  - **Version line** now says build 114.
- **Fewer rewrites, nothing cut (build 115).** In the live log, flagged paragraphs often got two rewrite tries, came back wrong both times, and were cut anyway: three writing calls for nothing. Three causes are fixed:
  - **Limits told before writing:** each beat's prompt now has a line "CHECKED IN THIS BEAT: …" giving the limits the draft is checked against: no electricity when no move is Electric (a shock from earlier may still be remembered), which bones may break, and no swearing just after a curse. Together with the talk allowance, the first draft can get these right instead of being rewritten.
  - **"Copied lines" that the notes asked for:** the prose check counted a phrase as copied when it matched earlier story, even when that phrase is the notes' own wording (an injury described the same way each beat, a building block). Phrases from this beat's notes are now allowed. Real copies from earlier beats are still caught.
  - **"Something in her snapped" (her temper):** the draft check already let this through, but the paragraph repair and the final cut still treated it as a broken bone. All three now use the same check.
- **A takedown that is never shown is now caught.** In a live log, Ripples was standing when an opening let Nocturne pin her (the engine picked a hip throw), but the narration went straight to "She leaned into the pin". The narrator had been told to show the takedown, but nothing checked that it did. Now, if no part of the beat shows her being taken to the ground (thrown, swept, tackled, hitting the grass, and so on), the beat is written again with that named ("missing takedown").
- **Fixes from a live log (build 116):**
  - **Clash shown as a hit.** When the two moves cancel, the notes now say a gust or mist may reach them but neither fighter is struck, soaked, burned or stung. A beat that never shows the defender's own move (for example her Thunderbolt: its name, or lightning, sparks, a bolt) is written again ("missing clash move").
  - **Pin label that puts the jaws in the wrong place.** The director wrote "jaw lock across her throat" while the jaws were on her right paw. When the label puts the jaws on a part they aren't on, it is rebuilt from the real grips ("her jaws on her right paw, her forepaw on her throat and her full weight on her chest"), so the screen, the hold and the story agree.
  - **Move names leaking into the prose as labels** ("her throat swelled—Hydro Pump—with the force"): flagged and rewritten, then cut if they survive. The name used normally ("the Hydro Pump tore across the grass") is fine.
  - **Pain from a miss.** The dodge note now says a miss costs the attacker balance or breath, not pain of her own.
  - **"Invented bite" false alarms.** Teeth closing on a cry, a groan, her own lip or empty air no longer count as a bite.
- **Skip setting the scene:** `/set narration.scene_intro false`. The first Enter goes straight to the first beat (the first beat's notes already say it is the start of the fight). `true` brings it back.
- **Commands at the arena question (build 117):** typing a command such as `/set …` or `/model …` at the `Scene>` prompt now runs it and asks for the arena again. Before, the command was taken as an arena name.
- **`/model` is kept (build 118):** `/model narrator <name>` and `/model director <name>` are now saved (rules.json `models`, and my_settings.json), so the next run starts on the same models. This matters when you start from Spyder, where there's no `--narrator-model`. Two `/model` commands pasted on one line are now run as two commands; before, the second was swallowed into the narrator's model name.
- **From a live log on the new model (build 119):**
  - **Thoughts and sounds stand out on screen.** Spyder's console doesn't slant italic text, so a written-out sound like *Eek* looked like a stray word. Thoughts are now shown in cyan and sounds in yellow, as well as in italics. Change them with `/set console.thought_color …` and `/set console.sound_color …` (empty for none). Saved text keeps its plain asterisks.
  - **One strike told as one moment.** A Night Slash that jars the hip and foot was told as three blows with reactions in between ("She set the limb down and shook it… The blow to her foot came next"). The note now says every jarred place lands together, before any reaction, and "the blow to her foot came next" counts as a second swing.
  - **Sounds tied to who makes them.** The notes now ask for each written-out sound inside a sentence that says it's hers ("a thin *eek* broke out of her"). A sound left standing alone between sentences is flagged, and that paragraph is written again.
- **Repeats, scenery, eyes (build 120):**
  - **The same phrase twice in one beat** ("the sound of cloth tearing" three times): a phrase used again word for word is sent back to be rewritten, with the phrase named and "say it a different way, or leave it out if it adds nothing". When it's one of the program's own blow sounds, a different sound of the same kind is suggested ("the scrape of claw on hide"). Only phrases with at least three meaningful words count, so saying again where she hurts ("her right thigh") never does. Building blocks give variety before the writing; this catches repeats after it.
  - **Scenery she hits must be shown:** thrown into an old oak and then the grass, the narration had only the ground. Every surface that isn't just the floor of the arena now has to appear (a tree also counts as trunk or bark).
  - **No retelling the throw after the landing:** a sentence that has her in mid-air after the passage has already landed her is rewritten. Bouncing and tumbling on are fine.
  - **Eye colours:** each beat lists the fighters' eye colours (taken from their descriptions), and "Ripples' red eyes" is caught.
  - **No lightning in a beat with no move** (a throw, a slam, a pin): the electricity check used to switch off when no move was used, so "as if struck by lightning" got through. Arenas that spark themselves (the power plant) are left alone.
- **The engine sets the limits (build 121).** Problems with the narration are fixed from the engine's own numbers where possible:
  - **Reactions sized to the injury.** A hip at 76% (HURTING) was told as "exploded", "a wave of agony", "a raw, desperate cry of pure, unfiltered agony" with the world blurring. A Water Gun doing 15% to a chest ruff was told as brutal and breath-stealing. Each beat now states each fighter's worst injury and what that allows ("how much it hurts: Ripples HURTING (right hip), Nocturne MINOR (chest ruff) at worst, so no crying out, no screams…"). Words above that level are flagged and the paragraph is rewritten: crying out, "exploded", "searing" and waves of pain need VERY PAINFUL (90%+); screams, agony, writhing and a blurring world need EXCRUCIATING (150%+). Pins, fainting and fighters worn out overall (under 40% strength) aren't limited.
  - **Wet or dry fur.** "The steady drip of water from Nocturne's fur" came before anything had wet her. Each beat now says who is dry, soaked, soaked by this beat's water, or damp and drying (from the engine's soaked status), so a fighter isn't wet before she's hit.
  - **No memories of things that didn't happen.** "Remember how that last Water Gun sent her reeling?" on the first Water Gun of the fight is flagged and rewritten.
  - **Attack labels that name the wrong weapon.** The director called an Iron Tail "claws raking down the side". A label naming a different natural weapon from the move's own is dropped, and the move's name is used instead.
- **Filler handled by the engine (build 122):**
  - **Told resolve and drama** ("She was ready. She was determined. She would not be defeated.", "a steely resolve", "every muscle screamed", "refused to give her the satisfaction", "nothing else mattered"): a short sentence that is only that is cut, since it adds no detail. A longer one is sent back with two concrete ideas from a new `resolve_shown` list ("she sets her feet again, wider than before", "her ears come forward, both of them, and stay up"), so the paragraph shows it instead. Italic thoughts may still say it.
  - **Reactions above the pain limit are never offered:** the reaction ideas handed to the narrator are filtered by the same limit that checks the prose, so a fighter who is only HURTING is never offered a scream to begin with.
  - **Pain shown by level:** a new `pain_show` list of how each pain level shows, from MINOR to DEVASTATED, by body area and by species feature. Two of them, sized to the worst place the beat left her with, are offered after each blow.
  - **Samples sized to the blow:** a blow that leaves a part only sore asks for a `strike take light` sample, and one that leaves it hurting or very painful asks for `strike take mid`. Each falls back to `strike take` when there is none.
- **More samples to rotate through (build 123):** 41 new passages in style_sample_scenes.txt: 10 attacks (5 each, every move), 8 light takes, 5 moderate takes, 3 knockdowns, 3 dodges, 2 throws, 2 landings from a throw, 3 pin holds, 3 pin struggles and 2 get-ups, across the cave, the lakeside, the gorge, the frozen lake, the swamp and the storm. Passages where the blow puts her down are tagged `knockdown take` and shown only when a blow really does, so they don't teach the narrator to invent falls.
- **A library of finished sentences (build 124):** story_lines.txt holds 937 whole sentences in the house voice, with the same conditions as the blocks:
  - after a hit, sized to the pain level from MINOR to DEVASTATED, by body area and species feature (356)
  - before a strike, by kind of move (136)
  - breath, by how worn she is (80)
  - closing lines (101)
  - resolve shown in the body (80)
  - holding a pin, early, middle or long (60)
  - under a pin, from still fighting to nearly out (80)
  - landings (44)

  How they're used:
  - **Offered word for word:** each part of a beat gets at most one that fits the real moment, marked "use it word for word if it fits, or leave it". So far that's after a blow, as a strike is made, and holding or under a pin.
  - **Dropped in by the program:** a bare line of told resolve that the program cuts ("She would not be defeated.") is replaced by a `resolve` line, with no model call.

  A line isn't offered again for 40 beats (`narration.lines.cooldown_beats`), and use is remembered between fights in lines_memory.json. Lines that call the part "it" are skipped when the part is plural ("twin tails"). Add your own lines to the file at any time: it is re-read while the program runs. The breath, closing and landing lines are in the file but not yet offered.
- **From a live fight (build 125):**
  - **A pin needs at least three points of contact** (`pin.contacts.min`). The director had Ripples pin Nocturne with her twin tails round one foreleg and nothing else. A pin written with fewer contacts is now filled out from what the pinner has free (jaws on the neck, her chest on the front, and so on), and its label is rebuilt from the real grips instead of a long, cut-off sentence.
  - **Rewrites for wording alone are capped:** at most 2 paragraphs a part (`narration.style_repairs_max`) are sent back for filler, a repeated phrase, a stray label or a lone sound. Mistakes about what happened, reactions bigger than her injuries and wrong anatomy are always fixed.
  - **Blood with no wound:** "the taste of blood… a thin trickle from her lip" on a fighter nothing had hurt is flagged. A fighter who has just bitten someone may still taste blood.
  - **A foreleg called an arm** (on a fighter with forelegs) is flagged.
  - **The takedown must be shown happening:** "she lay flat on her back" no longer counts as showing it. Rolled, thrown or knocked onto her back does.
  - **Pain limits inside pins:** the limit used to be off for any beat with a pin, so "a wave of agony" got through on a hold that hadn't pressed yet. It now applies, except to a fighter a pin has held for two beats or more.
  - **Pins on the first beat stay possible.** `pin.openings_from_beat` can turn them off, but in 300 simulated fights that moved Nocturne from about 60% to 69% wins, so it is left at 1.
- **Pins rarer early, rising with wear (build 126).** Results from 400 simulated fights.
  - **Pin chances:** a pin opening on a fresh fighter on her feet is now 4% a beat, down from 12%. Knocked down while still strong, it's 7%, down from 50%: she is up again in a moment. Both rise along a curve as her strength falls, and each part at 90%+ damage adds 2.5% (her opponent knows where she's hurt).
  - **Springing back up** (`down.spring_up`): a fighter knocked or thrown down may come straight back up on her feet in the same moment. She still takes every impact. The chance is 55% at full strength, falling to 0 at 55% strength.
  - **What changed:** the first pin comes at about beat 11.5 instead of 7.7. Fights with a pin in the first 5 beats fell from 46% to 23%, and pins per fight from 9.5 to 8.7. Submissions are still about one a fight, and Nocturne still wins about 61%.
- **Sounds always marked:** the narrator sometimes wrote a sound bare ("she hissed through her teeth, hss," / "a low growl, Grr." / "a thin eek breaking out of her"), so it wasn't coloured. The program now puts these in italics itself. The two sound examples in the notes also change every beat, because a fixed one ("a thin *eek* broke out of her") was being copied.
- **Order of events stated:** when a beat has several steps, the notes list them in order ("ORDER: 1) Nocturne's Night Slash is caught on Ripples' raised right upper arm; 2) Ripples goes down (the grass then a boulder); 3) Nocturne pins Ripples"). A live beat had told the pin before the blow that made it possible.
- **Smaller fixes:** a story block that came "from the blind side of the last injury" when nobody was hurt yet now reads "from the side the other is guarding least". Notes wording leaking into the prose ("a quick strike of her own, separate from any other move") is caught.
- **No more second drafts (build 127).** `narration.best_of_two` now defaults to `never`. A big moment (a pin, a knockdown, a breaking point, an escape) used to write every part twice and keep the better draft. A 4-part beat took 29 model calls and 9.5 minutes, and all the engine help now does that job instead. Big moments get two finished lines per part instead of one, on top of their samples, blocks and checks. To bring second drafts back: `/set narration.best_of_two important`.
- **The same hurt told again and again:** a part already described in pain 3 times in a beat (4 if it is EXCRUCIATING or worse) gets the next mention sent back with "show something new instead". This counts as a wording-only rewrite, so the cap of 2 per part applies, and nothing is cut. In a live beat Ripples' right thigh "throbbed", "flared", "was on fire" and "was a living thing" about eight times.
- **Anatomy and blood:**
  - A two-legged fighter with arms "fighting on three legs", or given a hind leg or all fours, is flagged.
  - Blood in her mouth ("copper and grit filled her mouth") now needs a hurt head, jaw, muzzle, cheek, nose or throat, not just any wound.
- **/help is a menu now (build 128).** `/help` shows a quick start (the dozen commands used most, with examples) and a list of topics. `/help attacks`, `/help pins`, `/help moving` and so on show one section. `/help charge` (any command name) shows just the help for that command. `/help all` is the old full list.
- **Build 129 fixes from a live log:**
  - **Instruction text in the story:** "Don't mention a clock, a count, or any seconds yet. Every press listed … must appear in the prose." is caught and cut, as are sentences about "the notes", "word for word" or what "this part must" do.
  - **A part cut off mid-sentence** ("…her full weight bearing down on Ripples'"): the ending apostrophe was taken for a closing quote, so the half sentence was kept. It is now trimmed like any other unfinished ending.
- **/move with several parts (build 130):** parts can be one list ("Chest,Neck") or each in its own quotes ("Chest" "Neck"). With a count, the blows go round the named parts in order, and the count is the total. `/move Nocturne Ripples "Slash" "Chest" "Stomach" "Leg" "Head" "Neck" 10` is 10 blows, two on each. It used to be 10 on the chest plus one more on each other part. Loose words like "Leg" find the nearest real part (Left Thigh).
- **Build 131 fixes from a live log:**
  - **Every attack in a busy beat is told.** Ripples' Aqua Jet, then Nocturne's 4-pulse Hydro Pump (403% of Ripples' health), then a pin, all in one beat: the narration told the charge and the pin and skipped the Hydro Pump completely. With two or more attacks in a beat, each must now appear, either by its name or by its element hitting one of the parts it hit, in a sentence about the attacker or the one hit. If one is missing, the beat is written again ("missing attack").
  - **A bare /pin builds a real pin.** `/pin Nocturne Ripples` with no parts now picks one of the pin shapes her body allows (jaws on a paw, a forepaw on the neck, her full weight on the chest, her hind paws on a hip), the same way the director does, with that as the label. Before, it was three parts with nothing saying what pressed them.
  - **More present tense caught:** "Nocturne's weight presses down", "Her twin tails stutter" (a possessive subject) now count toward the present-tense check, so a passage that slips into the present is written again.
- **Not done: one call for several flagged paragraphs.** Paragraph rewrites already reuse Ollama's cached prompt, so batching would save only about 2 seconds a paragraph, and it risks paragraphs coming back tangled. Not worth it.
- **Build 132:**
  - **Why they fight (`/reason`).** `fight_reasons.txt` holds 50 reasons two wild Pokémon end up fighting: a stolen catch, the last pool in a drought, a flooded den, an old scar, a clutch of eggs, a misread scent trail. Off by default: `/reason on`, or choosing one, turns it on. Then one that fits the arena is picked for each one-on-one fight. One fighter becomes the holder (there first, or holding what is wanted) and the other the comer.
    - The opening is built on it.
    - Every beat's notes carry a short line. About a quarter of beats also offer one thought either fighter might have.
    - Interludes get the reason in full, and the aftermath gets its ending.
    - The second reader treats the reason as true background, so it isn't flagged as an invented past.
    - Commands:
      - `/reason` shows the reason; `/reason list` lists them all.
      - `/reason 12 Ripples` picks number 12 with Ripples as holder.
      - `/reason swap` swaps the roles; `/reason new` rerolls.
      - `/reason "your own sentence"` uses your own reason; `/reason off` turns it off.
    - Add your own reasons to the file in the same format.
  - **Interludes (`/interlude`).** Now and then (`narration.interlude`: 10% a beat, at least 4 beats apart, not before beat 3) a beat is followed by a long passage of about 900 words where nobody attacks. It holds thoughts, the body taking stock, what each makes of the other, the place in detail, and the reason they fight. A running pin holds throughout.
    - `/interlude now [words] ["what to dwell on"]` writes one at once.
    - `/interlude next` writes one after the next beat.
    - `/interlude chance|words|gap <n>` changes the settings; `/interlude off` turns it off.
  - **Targeting.**
    - **No body part comes first** unless `/focus` says so. The director had been told to go back to weak, low-resistance parts "again and again", and the throat is soft from the start, so blows and jaw clamps kept landing there. Now soft parts are described as just how the body is built, and the director is told to range over the whole body, including parts fights forget: tails, hocks, ears, hips, the base of a fin.
    - **Weak spots are still nudged sometimes** (`director.weak_spot_chance` 0.2 a beat): one soft or worn-down part, just that once. 40% of those nudges (`weak_spot_repeat`) are for a run of blows, such as a pummel, combo, chain or grapple worked at: one weak spot hit again and again, a group of parts worked together, or a few weak spots in turn. Change them with `/weakspots <0-1>` and `/weakspots worked <0-1>`.
    - **To aim on purpose:** `/focus neck`, `/focus vulnerable` (throat, eyes, nose, ears, belly, knees, hocks), or `/focus weakened` (the same as injured).
    - **Throat-bite ideas are rarer:** 6% a beat in open fighting (was 12%) and 15% in a pin (was 25%). They come three times as often with a neck, head or vulnerable focus.
  - **How often pins come (`/pins`).** `/pins 0.5` halves every pin-opening chance and `/pins 2` doubles them. `/pins off` means the director never starts one, though your `/pin` still does. In 100 simulated fights, `/pins 0.5` gave 6.4 pins a fight instead of 8.8, with the win rate unchanged.
  - **Pins press from their first beat.** `pin.first_beat_damage` is now 1 (was 0), so the presses land the beat the pin closes. Change it with `/pinstart`. In 400 simulated fights Nocturne still wins 59.8%, with 8.1 pins and 0.94 submissions a fight.
  - **A broken hold can't be re-grabbed at once.** `holds.break.regrab_after` is 2 beats. The screen said Ripples broke free, and the same grip was back on the next beat.
  - **The escape blow must be told.** When a pinned fighter breaks out with a blow, the passage has to show it landing (where, with what, and the reaction). If it doesn't, the passage is written again.
  - **Beat time.**
    - **Why later beats get slower:**
      - Damage piles up, so more parts of the beat are added to stay with the damage (her side, the watcher).
      - The notes get longer with every injury: about 35k characters, read at about 600–1,000 tokens a second.
      - More checks fire, and each can mean a paragraph rewrite or a second reading.
    - **The fix:** `narration.beat_budget_minutes` (6) is a time budget per beat. Past it, the optional extra passes stop: a second whole rewrite, wording-only fixes and the second reading. Past 1.5 times the budget, no whole part is written again; only the paragraphs that need it are fixed. Every part is still written in full, and the program's own checks and cleanup still run.
    - **Settings:** `/budget <minutes|off>` sets the budget. The ⏱ line now has a second line saying where the time went (drafts, rewrites, paragraph fixes, second reading, interlude), and `/budget timing off` hides it.
- **Ranked checks and lighter notes (after build 132):**
  - **Checks are ranked.**
    - **Always fixed:** anything wrong about what happened (a missing hit, attack, escape or escape blow, an invented fall or pin), wrong anatomy, and pain past the limit.
    - **Fixed by rewriting that paragraph:** tense, too much talk, the same hurt told again, blood with no wound. Wording-only ones stay capped at 2 a part.
    - **Never cost a model call** (`narration.cleanup_only`): filler, a leaked move label and a bare sound. The program's cleanup swaps the filler for a finished line, cuts the label and puts the sound in italics.
  - **The second reading runs on big beats only** (`narration.reader_when` "big"): a pin starting or ending, a knockdown or takedown, a devastating blow, the arena, a grip closing, someone out. `/set narration.reader_when always` brings it back for every beat.
  - **Small details fade from the notes** (`narration.notes_decay`, **off by default**: it shortened late notes by only about 5%, so the full notes are kept; `/set narration.notes_decay.enabled true` turns it on):
    - How a part was hurt ("from Ripples' Ice Beam, then her pin") is kept while that part was hit in the last 4 beats. After that only its pain level stays, unless one huge hit did it (150%+ part damage at once), which is remembered for the rest of the fight.
    - Visible marks on a part left alone shorten to the main one.
    - Surface details like grit or a scuff last 6 beats.
    - The "barely touched" list shows 6 parts and the movement list 3.
    - Pain levels, injuries, posture and everything that happens are never trimmed.
- **The wounds that matter most** (`narration.big_wounds`): each fighter's notes name her few hardest single hits (150%+ part damage at once, biggest first, up to 3), for example "Left Hock (Ripples' Brick Break)". The story gives these more weight than the rest, in how she moves, what she guards and what she thinks about. It is one short line, with no extra model calls and no new checks.
- **Damage roll, juggles, and pummels against the scenery:**
  - **Every instance of damage is rolled** (`damage.roll` 0.17): a move, each press of a pin or hold, a landing and an impact land within about ±17% of their number, so a base of 30 lands as 25 to 35. Severity words (environment hits, strikes without a move) already varied by `severity.variance`. Chances like "30% to be knocked down" are not jittered: a random chance and then a roll works out exactly the same as rolling at the average, so it would change nothing.
  - **Juggle nudge:** one of the chain ideas is now a rising blow (an uppercut to the jaw, a horn driven up under her chest) that launches her, then a second blow that catches her in the air and smashes her back down. Juggles were in the director's instructions but never suggested.
  - **Held against the scenery:** a strike or pummel with `pinned_against` now drives her back into it with every blow (`moves.grind`): an extra light hit on her back per blow. The thing may break (at half the held-stream chance), giving a heavy hit as she goes down with it. Before, `pinned_against` only did anything for held streams, so "pummels her against the oak" never touched the oak. The grab idea now offers this as one of its ways.
- **Audit, group A (grappling, holds, manhandling):** 16 bugs fixed. See `audit/report_A.md`.
  - Plain blows with a count now follow the pummel rules.
  - Holds: tightening holds cap at 35; easing holds let go at 0.
  - Dodging: no dodging while held by your attacker or just after being hauled up.
  - Grabs keep the regrab cooldown.
  - Jaws already clamped in a grip can't bite.
  - Scenery: grinding works only into real, unbroken scenery, and broken scenery stays broken all fight.
  - Throws, slams and drags can't reach a fighter in the air.
  - Confusion can spoil a grab or throw.
  - Rescale: `holds.shaken` (hard hits shake a grip loose).
  - **Tuning:** after the damage roll, Nocturne's win rate had slipped to about 57.6%. Her health went from 1800 to 1860, which brings her back to 60.4% over 800 simulated fights, with 8.2 pins and 0.97 submissions a fight. Ripples is unchanged.
- **Audit, group B (pins):** 16 bugs fixed. See `audit/report_B.md`.
  - **The jaws after a breakout (from your log):**
    - When a pinned fighter breaks out, the pinner's jaws now hang on 8% of the time (`pin.struggle.keep_jaws`), never when the pinner is thrown down. The bite goes on as an ordinary hold, shown on screen ("🦷 Ripples hangs on") and told to the story. Otherwise every grip comes off.
    - A new check catches the story keeping her jaws on when they came off.
  - **Pins against scenery:** "an old oak", "the log" and "a boulder" now match the arena's scenery. Broken scenery can't be pinned against.
  - **Dunks:** a dunk in the shallows really soaks her and leaves her sputtering.
  - **Coil pins** by tailed fighters now constrict.
  - **Adding a grip to a running pin** no longer pads it out to a full new pin.
  - **Jaws:** a fighter can't bite down on a second part while her jaws hold one.
  - **Sleeping or frozen fighters** can't struggle.
  - **Pinners:** a pinner can't dodge or guard against a third fighter.
  - **Double pins:** the escape blow names the pinner it actually hit.
  - **Labels:** the pin label follows the presses when she's turned over.
  - **Bare `/pin`:** uses the shape weights and 3 contacts, with no hint text in its label.
  - **`/pins off`** holds even when a submission is stuck.
  - **No-clock pins** no longer leak seconds.
  - **Pin-escape learning** works (it never recorded anything before).
  - **Balance:** Nocturne wins 61.4% over 800 simulated fights, with 8.1 pins and 0.96 submissions a fight.
