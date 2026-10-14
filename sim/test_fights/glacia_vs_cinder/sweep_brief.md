# Brief: the bug sweep after the Glacia vs Cinder test fight

Four writers narrated a 47-beat test fight (Glacia: an ice bird with a beak, feathers, wings, talons and no arms; Cinder: a winged fire dragon with scales, arms with clawed hands, horns, and a flame on her tail). While writing, they logged about 315 bug notes about the narrator's notes (the prompts FightSim builds for the local narration model).

## Files (S = /tmp/claude-0/-home-user-FightSim/d2e1d57a-2374-5322-b4cf-0e9b328e1377/scratchpad)
- Bug notes: S/wt3/narr_bugs_00-11.md, narr_bugs_12-23.md, narr_bugs_24-35.md, narr_bugs_36-47.md.
- The OLD notes the writers saw: S/wt3/out/notesNN.txt. The console for each beat (the engine's truth): S/wt3/out/beatNN.txt.
- NEW notes, regenerated on the current build (several fixes have already gone in): S/wt3n/out/notesNN.txt.
  - Already fixed:
    - body-word filters on the per-hit impact and tell examples;
    - the "aloft" ban on ground ideas for a fighter in the air all beat;
    - wing wording in HOW THEY MOVE;
    - "fur:" renamed "wet or dry:" with feathers or scales;
    - the camera line;
    - wind moves no longer staged as beams;
    - scene bans for grass, leaves, mud and sand;
    - FIGHT SO FAR now says "the last 10 of N";
    - the "FIRST beat" text on later beats;
    - "devastating" in the catch-up call;
    - get-up wording when the other fighter flies.
- Always check a bug against the NEW notes first. If it's gone, mark it "already fixed" and move on.
- Ignore these, they are test-harness artifacts: placeholder prose in PREVIOUS BEATS / THE PASSAGE SO FAR, and the rewrite-loop reports.
- The species names in the fighters' own descriptions ("A female Articuno") come from the author's fighter file. Leave them.

## How you work
- Work in your own git worktree (your current directory), never in /home/user/FightSim.
- Make your own replay folder:
  1. Copy S/wt3n to S/sweep_<yourname>/.
  2. In plan.py, change `/home/user/FightSim` to your worktree path. Check sim/harness.py too.
  3. Run `python3 plan.py 202 all` from your worktree (about 1 minute) to regenerate every beat's notes, or trim script.json to N beats and run `python3 plan.py 202` for just the last one.
- The code: narrator.py builds the notes; story_blocks.txt and story_lines.txt hold the ideas and lines; blocks.py picks them by conditions (body_bans, features, kind_of); engine.py and director.py decide events. rules.json holds the tunables, each with a `_comment`.
- Principles:
  - Fix root causes with small changes in the style of the code around them.
  - Don't change intended engine behaviour. The engine's decisions are right; the notes must follow them.
  - Don't slow things down.
  - Story text rules: little gore, no memories from before the fight, no game words.
  - New tunables go in rules.json with a comment.
- Save as you go: commit in your worktree after each fix, `git add -A && git commit -qm "Fix: <what>"`. Don't push or touch other branches. Don't bump VERSION.
- Before your final commit, `python3 sim/regress.py` must end "ALL PASSED". Run it at the end and after any big change.
- Final report:
  - each bug group: fixed (file:function, what), already fixed, or left alone (and why);
  - the branch name and the last commit hash.
  Keep it compact: group duplicates.

Only fix the bugs in YOUR theme (below); two other agents have the other themes.
