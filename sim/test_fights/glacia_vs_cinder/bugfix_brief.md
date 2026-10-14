# Brief: fixing bugs in FightSim (shared by several agents)

FightSim is a fight-story engine. engine.py, the rules engine, decides events. director.py turns orders into engine calls. narrator.py builds the notes and prompts that a local LLM (mistral-small) turns into prose. blocks.py picks short "story blocks" (ideas) and "story lines" from story_blocks.txt and story_lines.txt by conditions. display.py prints the console lines. rules.json holds every tunable, each with a `_comment` key beside it. sim/regress.py is the regression suite (about 150 s).

You work in your OWN git worktree (your current directory). It is a copy of the repo on its own branch. Do all edits there, never in /home/user/FightSim.

## Principles (the author's)
- Understand the code before changing it. Fix the root cause with the smallest change that fits the code around it, in the same style: comment density, naming, the `(parenthetical)` comment idiom.
- Do not change intended behaviour. If a "bug" is really a design choice, leave it and say so in your report.
- Every new tunable goes in rules.json with a `_name_comment` explaining it, and the code reads it with a default.
- Don't make processing slower, and don't reduce narration quality.
- Story-material rules: no gore beyond small cuts or bruises, no memories from before the fight, no game words.

## Reproducing (the test fight the bugs come from)
- The test fight: /tmp/claude-0/-home-user-FightSim/d2e1d57a-2374-5322-b4cf-0e9b328e1377/scratchpad/wt2 (Aura vs Dusk, seed 91).
- Its script is script.json, one list of actions per beat.
- plan.py replays it and writes out/beatNN.txt (the console) and out/notesNN.txt (the narrator's prompts).
- Do NOT write into wt2. Copy it to a folder of your own under the scratchpad (e.g. scratchpad/fix_<yourname>/), then edit the copies:
  - plan.py and add.py: change `/home/user/FightSim` to your worktree path.
  - sim/harness.py: check whether it uses a hard-coded path or the cwd.
- To see one beat's notes: trim script.json to the first N beats and run `python3 plan.py 91`. The last beat gets notes. Or run `python3 plan.py 91 all` for every beat (slow).
- The beat numbers in the bug list are the export's beat numbers. They match the script.json beat numbers, except for the aftermath beats at the end ("aftermath" entries).

## Save your work as you go (the author may run out of tokens mid-task)
- Commit in your worktree after EACH bug you fix: `git add -A && git commit -qm "Fix: <bug n>: <what>"`. Small commits.
- Do not push, and do not touch other branches.
- Before your final commit, run `python3 sim/regress.py`. It must end with "ALL PASSED". If a test fails because of your change, fix the change, never the test (unless the test checked the buggy behaviour; then say so).
- Do not bump VERSION in play.py.

## Your report
For each bug in your list:
- **fixed:** what you changed (file:function).
- **already fine:** why.
- **left alone:** why (for example, a design choice). Include a one-line suggestion.

Also give your branch name and the last commit hash.
