# Work in progress (kept in the repo so nothing is lost if a session stops)

Last updated: 2026-10-13, build 186 on branch `claude/kind-bell-r5ehx4`.

## Running now
Nothing. Sweep 2 (engine, body2, ideas2) was merged into build 184.

## Still to do
1. (Done in build 180) The sweep was merged. The notes were regenerated and spot-checked, and the fight replays with the same rolls.
2. (Done in build 181) A strike counts the limb she actually uses (`moves.limb_limits.struck_limb`). The user said twitches while out cold are fine. The idea cooldown is now 14 beats.
3. (Done in build 182) Faster fights with damage spread out are now the default: about 40 beats, wear 0.7, health loss x3.2, with the /length presets re-tuned. Weak-spot hints now offer a menu of hurt and soft parts. Nocturne vs Ripples now comes out about 43/56 (60 fights; it was 55-62% Nocturne): watch it.
4. (Done in build 183) Test fight 4, Nocturne vs Ripples: narrated and exported. Its bug list (about 190 notes) was fixed in build 184 (sweep 2). Note: the fight's script no longer replays past beat 10 on build 184, because three engine fixes change the dice. Rebalance: Brick Break 28. The resistance curve's low end is flattened.
5. Older pending tasks:
   - The card view chooser: Front / Back / Both (side by side), set per card.
   - Dice-rolled attacker assessment lines: how long she'll last, focus, wear her down, surprise that she keeps going.
   - The trial branch `claude/kind-bell-r5ehx4-shorter-notes` (shorter notes) is waiting for the user's test with mistral.
   - The old Aura vs Dusk script no longer replays past beat 27 on build 179: the dice changed, and beat 28 fails with "Aura already has hold of Dusk".

6. (Build 186) The user's lakeside log (Nocturne vs Glacia, build 184), fixed:
   - a director launch on a flyer rolls air_recover;
   - "THE END" lines are cut;
   - memories of past fights are cut;
   - a driven-into landing skips the part just struck;
   - an unaffordable move is swapped instead of a pause beat;
   - wound and blood claims are dropped from the direction;
   - "her horns" becomes "horn" when nobody has two.
   Still open:
   - speed (notes grow to 49k characters; up to 10 minutes a beat);
   - species names in prose ("the Absol"): asked the user;
   - invented facts and body slips in "Both" parts.

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
