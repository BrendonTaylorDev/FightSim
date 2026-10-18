# Fight Sim

A local, story-first Pokémon fight simulator. Three parts:
1. The **director** (an Ollama model, director.py) picks who does what each beat as JSON: moves, target parts, severity
   words. It never picks numbers.
2. The **engine** (engine.py) turns those into numbers and resolves everything: damage, resistance, health, holds,
   pins, statuses, falls, flight, scenery.
3. The **narrator** (an Ollama model, narrator.py) writes the prose. A long chain of checks and rewrites keeps it true
   to what the engine resolved.

There are no turns: one "beat" is one thing happening.

## Running things
- **Python:** use `C:\Users\night\AppData\Local\spyder-6\envs\spyder-runtime\python.exe`. It is the game's runtime
  (3.12, with Pillow). `python` on PATH is the Microsoft Store stub. `spyder-6\python.exe` works for the tests but has
  no Pillow, so no pictures.
- **Console output:** set `PYTHONIOENCODING=utf-8`. The game prints emoji and the Windows console is cp1252.
- **Tests:** `python sim/regress.py` (about 90 s, must print ALL PASSED; `regress.py pin` runs only the matching
  cases). Pipe the output through `grep -E 'FAIL|ALL PASSED|FAILED|^      '`: it is long.
- **Repro scripts:** `sim/harness.py` plays scripted beats through the real game with a stand-in model.
  - `H.session(seed, fighters="A,B")` starts a fight; `H.beat(s, [actions])` plays a beat.
  - It runs in a throwaway copy of the repo and changes directory into it, so give output files absolute paths.
- **Balance:** `simulate.one_fight` plays fights with no model.
  - Target: Nocturne wins about 60% against Ripples.
  - Never change Ripples' stats to get there.
  - rules.json currently has knockout-only fights with pins off (`finish.knockout_only`, `finish.no_pins`). Tests
    that need pins switch them on themselves.

## Where things are
- **play.py:** the console game, the beat loop (`Session._play_beat`), every /command (`handle_command`), and
  `fight_snapshot` (the per-beat data the pictures and exports use).
- **engine.py (8.4k lines):** the `Engine` class.
  - `_apply_damage` is the core damage maths. `move_math` works out effective power.
  - `beat()` is the end-of-beat tick: holds, pins, get-ups, drain, statuses.
- **director.py:** prompt building from many `*_hint` functions, then `resolve`/`resolve_many`, which check the
  director's JSON and apply it.
- **narrator.py (12.5k lines):** search it, never read it whole. `narrate()` is the entry point; `_knock_on_lines`
  and `_describe_action_core` turn events into the narrator's notes.
- **display.py:** the stat blocks. Its `knock_on_lines` mirrors the narrator's for the screen.
- **window.py, cards.py, fightexport.py:** the window with fighter pictures, the picture logic shared by the window and
  exports (poses, glow, damage marks: `paint`, `card_panels`, `PictureBook`), and `/exportfight`.
- **Data files:**
  - `rules.json` holds every tunable number, each section with a `_comment`.
  - The user's own `/set` changes live in `my_settings.json`, which overrides rules.json. Don't edit it.
  - Also: fighters.json, moves.json, scenes.json, story_blocks.txt, style_sample_scenes.txt.
- **images/:** the artwork, plus `anchors.json` (part positions the user placed by clicking). Pose pictures are named
  `<name>_<pose>.png`.
- **audit/:** the mechanics audit. Groups A–D and F are fixed; E is on hold.

## Rules of the codebase
- **Engine state:** every attribute the engine holds must be listed in exactly one of `Engine._SNAP_FIELDS`,
  `_SNAP_EXTRA` (undone and saved with it) or `_NOT_SNAPPED` (per-beat scratch, settings).
  - regress.py fails on anything unlisted.
  - Sets survive saves through `_to_json`/`_from_json`.
- **New behaviour is switchable:** a `rules.json` key with defaults and an explanation in the section's `_comment`.
  The user wants new features optional.
- **Silent fallbacks:** a step that falls back when something breaks calls `engine.note_failure(where, exc)` (written
  to errors.log, said once), never a bare `except: pass`.
- **Style:** comments and docstrings in plain English, the fighters called "she". Match the surrounding density.
- **Possessives:** use `engine.poss_word`.
- **Each build:**
  - Bump `VERSION` in play.py (the current one is build 189).
  - Add a `## Build N` section to README.md above the previous build's (search for `## Build 189`).
  - Run regress.py, then make one git commit.
- **Editing:** prefer the Edit tool. Scripted edits through bash heredocs have mangled backslashes: `\b` became a
  backspace character. After a scripted edit, check with `grep -c $'\x08'`.

## ComfyUI (pose pictures)
- **Setup:** a local Comfy Desktop install. The server is `http://127.0.0.1:8188` while it is open.
- **Model:** `noobaiXLNAIXL_epsilonPred11Version.safetensors`, in
  `C:\Users\night\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\checkpoints`.
- **Settings:** 1024×1024, 28 steps, CFG 5, euler_ancestral.
- **Prompts:** comma-separated tags. Always `general` in the positive prompt and `nsfw, explicit, questionable,
  suggestive` in the negative: pin and on-top poses drift otherwise. One fighter per picture is far more reliable
  than two.
- **Workflow:** "FightSim poses" is saved in ComfyUI.
