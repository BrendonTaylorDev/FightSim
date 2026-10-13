# Work in progress (kept in the repo so nothing is lost if a session stops)

Last updated: 2026-10-13, build 179+ on branch `claude/kind-bell-r5ehx4`.

## Running now
Nothing. The three bug-sweep branches (body, structure, labels) were merged into build 180, and their WIP patches were removed.

## Still to do
1. (Done in build 180) The sweep was merged. The notes were regenerated and spot-checked, and the fight replays with the same rolls.
2. (Done in build 181) A strike counts the limb she actually uses (`moves.limb_limits.struck_limb`). The user said twitches while out cold are fine. The idea cooldown is now 14 beats.
3. Recommendation given to the user: use /scale 3 with /length 35 or 40 instead of /scale 4. Measured: /scale 4 /length 60 gives 46 beats with 3.3 devastated parts per fighter; /scale 3 /length 35 gives 34 beats with 1.8. Waiting on whether to make that the default.
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
