# Work in progress (kept in the repo so nothing is lost if a session stops)

Last updated: 2026-10-13, build 179+ on branch `claude/kind-bell-r5ehx4`.

## Running now
Three bug-sweep agents, each in its own git worktree (`.claude/worktrees/agent-*`, branches `worktree-agent-*`). They are fixing the narrator-note bugs logged in `glacia_vs_cinder/narr_bugs_*.md`, split by theme:
- **body:** wrong body or posture (fur, teeth or paws on the bird; standing ideas in the air; wings treated as arms).
- **structure:** events with no part, numbness, pins, aftermath, repeats.
- **labels:** labels, history and sizes (thrown vs knocked, cause lists, invented blows, scene words, samples).

The brief they follow is `glacia_vs_cinder/sweep_brief.md`.

Every 10 minutes their commits are saved as patches in `wip_patches/<branch>/` and pushed. If a session dies:
1. Make a branch from this one.
2. Apply the patches: `git am sim/test_fights/wip_patches/<branch>/*.patch`.
3. Merge the branches, run `python3 sim/regress.py`, and push.

## Still to do
1. Merge the three sweep branches (or their patches), run regress, bump VERSION, push. Then regenerate the Glacia vs Cinder notes (`glacia_vs_cinder/plan.py 202 all`) and spot-check that the logged bugs are gone.
2. Give the user the sweep results: what was fixed, already fixed, or left alone.
3. Open question for the user: should aftermath ideas that show small twitches for a fighter who is out cold be tagged waking-only?
4. Older pending tasks:
   - The card view chooser: Front / Back / Both (side by side), set per card.
   - Dice-rolled attacker assessment lines: how long she'll last, focus, wear her down, surprise that she keeps going.
   - The trial branch `claude/kind-bell-r5ehx4-shorter-notes` (shorter notes) is waiting for the user's test with mistral.
   - The old Aura vs Dusk script no longer replays past beat 27 on build 179: the dice changed, and beat 28 fails with "Aura already has hold of Dusk".

## Done in this stretch (builds 177-179 and after)
- Hit reactions weigh the hurt part as well as overall strength. A strong fighter with a ruined part gets a half-hidden reaction, a capped voice, and only concealed ideas.
- Flight:
  - healthy flyers stay up far more;
  - a flyer a blow would hurl can catch herself;
  - a fighter can always take off, but below 10% strength it is a hard roll;
  - wing strain is capped.
- 13 engine bugs from this test (`glacia_vs_cinder/bugs.md`) and 24 from the Aura vs Dusk test.
- 20 attacker-side "strike act" sample passages, and 24 concealed-reaction blocks.

## Test fights kept here
- `glacia_vs_cinder/`:
  - `script.json`, the director's orders, beat by beat;
  - `narration/beatNN.md`, the hand-written narration;
  - `outline.md`, the beat outline;
  - `bugs.md`, the engine bugs fixed;
  - `narr_bugs_*.md`, the writers' bug notes;
  - the replay and window tools.

  The replay tools expect to sit in a scratch folder: copy them out and fix the paths at the top before running.
- `aura_vs_dusk/`: the earlier test (script, narration, bugs).
