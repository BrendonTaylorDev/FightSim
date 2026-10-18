# Next steps (narration ideas, not started)

Written after build 193 (branch `claude/kind-bell-r5ehx4-anchors`). Nothing below is built yet; the user hasn't
picked. Suggested order: 3 → 1 → 2 → 5 → 7. Every one must be switchable in rules.json (see CLAUDE.md).

## Where things stand (build 197)
- Build 192: `narration.rich` (longer beats, INNER LIFE from `engine.inner_state` / `fight_record`, one sense a part,
  closing thoughts, per-blow body detail: `narrator._impact_body`, `BODY_MOVES` / `BODY_GIVES` / `BODY_DEEP`).
- Build 193: `/sets` (every setting), `/intro on|off`.
- Builds 194-196: fixes from the user's Nerine vs Ripples fights (see the sections below).
- Build 197: `/bench`, the test bench (play.py `_bench_save` / `_bench_run` / `bench`; cases in bench_cases/,
  reports in bench_reports/). Tested here only with the stand-in model, not yet with the real one.
- New fighter Nerine (a second Buizel, no flotation sac), health 1775. The user doesn't want more balance testing.
- None of this is on the other branches yet (`claude/kind-bell-r5ehx4`, `-shorter-notes`).
- Next: idea 1, the beat card, behind a switch so `/bench` can compare it with the current layout. Ask the user for a
  bench baseline first.
- The user asked: commit once per build, not after every fix.

## The ideas
(Build 197 built idea 3, the test bench: `/bench`.)
1. **One beat card layout.** Every part's prompt in fixed blocks: FACTS (mandatory, note form) / BODY / MIND
   (inner life) / IDEAS (optional, "never quote") / THIS PART'S JOB (last). Fixed rules first so Ollama's KV cache is
   reused (speed). Biggest change: build behind a switch and measure with (3).
2. **Situation-matched examples from the user's own fights.** `/keep <paragraph>` saves a paragraph of the last beat,
   tagged from that beat's events (move kind, part region, species, scene, knockdown/get-up...). Later beats with
   matching tags get 1-2 kept passages as style examples, with a cooldown. Builds on `_sample_tags` /
   style_sample_scenes.txt.
3. **Test bench.** Replay a saved beat's narrator inputs (play.py `last_narration["args"]`, or the export JSON) through
   the narrator with settings A vs B; report words, checks fired, rewrites, time, repeated phrases. Needs Ollama, so
   the user runs it locally.
4. **Plan, then write.** For the part where blows land: a 4-6 line outline first (focus, sense, thought per
   paragraph), checked against the facts by the program, then the prose.
5. **Variety in shape.** The engine picks a rhythm per part from the events (staccato for a flurry, long for a dwell,
   a one-line paragraph for a devastating blow), plus a "recent paragraph openings" don't-repeat list.
6. **A thread for each fighter.** A motif picked at fight start (Nerine's notched fin, the old oak), brought back every
   few beats and changing as the fight goes.
7. **A short history for each wound.** For each badly hurt part: first hit, what worsened it, what it does now (from
   `engine.injury_log` / `injury_causes`), for accurate callbacks.
8. **Sensory details for each arena.** A bank per sense in scenes.json, drawn by the sense rotation (`_sense_pick`).
9. **Body language for each species.** Movement, pain sounds, threat displays, how it gets up.
10. **Different temperatures for different parts:** warmer for thought and aftermath parts, cooler for the part
    where blows land.
11. **Expand the thinnest part instead of rewriting:** when a rich beat comes out short, expand the thinnest
    paragraph rather than adding a passage at the end.
12. **Grow story blocks and lines only with narrow tags** (event, region, species), so each beat draws a few that fit.

## Still open from the full-fight review
- The model still sometimes:
  - tells a blow twice;
  - swaps the fighters' injuries;
  - writes in the present tense;
  - pastes in pieces of the notes.

  The beat card (1) and the outline (4) are aimed at these.

## From the user's Nerine vs Ripples beat 1 (build 193; 10.5 min, 24 calls, 4 parts)
Fixed already (commit after build 193):
- The body ideas no longer say "bone", which likely set off the broken-bones check: 2 checks, 5 paragraph rewrites.
- "Not very effective" is no longer told as a shrug when the blow knocks her down or throws her into something
  (her body was "a rock" while she was slammed into the pine).
- The body note now says it belongs to the blow's ONE telling.

Build 194 then fixed: the linger note dropped when body detail is on (`narration.rich.no_linger`), rich length
1.5, a no-past reminder on the first beat, "familiar" smells cleaned, hands marked in landings, a roll-through told
once. Still to look at (the rest of the list below, apart from those):
- **The same cheek blow is told 3-4 times in Ripples' part.** The linger note, the impact-motion note, the body note
  and the matchup note all describe the same blow, so the model tells it several times. Idea: merge them into one
  block for each blow (part of the beat card, idea 1), or skip the linger when rich body detail is on.
- **Too slow:** 4 parts (linger + rich length) and 12 paragraph fixes. Ideas:
  - fewer parts when rich is on (count words per part, not parts);
  - give the paragraph-repair pass a budget per beat;
  - `narration.rich.length_mult` 1.5.
- **Invented history on beat 1:** "a slight favoring of her left side, a remnant of the last hit". Nothing had hit
  her yet.
- **Familiar smells:** "a familiar sensation", "a familiar and comforting aroma". The no-past note isn't enough; a
  scrub for "familiar" next to smell or sensation words might be.
- **Hands treated as feet:** "her left paw hit the ground first ... into her hip", although a Buizel's paws are her
  hands.
- **Rolled to her feet, told as staggering:** "she took the blow, staggered" after she was knocked down, rolled
  through and came up standing.
- **The first part is labelled "— Both —"** before the two sides are told.
- **16 present-tense sentences** in one beat: the model drifts more over long parts.

## From the user's full Ripples vs Nerine fight (build 194; 10 beats, 2.5-7.5 min each)
Build 195 fixed: copied body-note and grip-note lines, "familiar" in any form, more sound tags, Nerine's Bite name in
the injury report, "a Aqua Tail". Still to look at:
- **Events told twice:**
  - beat 7: the get-up tries are told in both fighters' parts;
  - beat 7: the knee is told again at the end;
  - beat 10: the missed Crunch is told twice.
- **Events out of order:**
  - beat 4: the get-up is told before the pine impact and the nose bite;
  - beat 7: the get-up is told before the knee.

  Cause: passages for left-out events are added at the end. Idea: insert them where they belong.
- **Fragments left after cut sentences:** "was the only thing that moved...", "seemed to echo the rhythm of her
  heartbeat...". After a cut, check that the next sentence starts like a sentence.
- **Wrong state in the prose:**
  - beat 2: "Ripples' feet were planted" while she lay down;
  - beat 3: "Nerine's grip tightened ... jaws clamped on her chest" in the interlude, after that hold broke;
  - beat 10: "Nerine could feel the adrenaline", which was Ripples' surge.
- **Invented past or events:**
  - "showing where Nerine had launched her Aqua Jet" (never used);
  - "earth damp from the recent rain";
  - "She had seen one like it before";
  - "one that she had seen work before";
  - "There. She flinched at the feint." (a story-block line, though no feint happened).
- **Untrue story lines:**
  - "I've been slow all fight" for the fighter who was dominating;
  - "Her legs throbbed in sympathy".

  Ideas: tag those lines with when they fit (losing or winning), and drop feint lines unless there was a feint.
- **The interlude is long and repeats itself** (about 900 words). Shorten `narration.interlude.words`, or don't run
  an interlude in rich mode.
- **Console:**
  - the flavor names the wrong fighter: "Ripples' Ice Fang lands and Nerine's jaw..." on Nerine's attack;
  - the summary lists the knockout before the deflected Crunch from the same beat.

Build 196 fixed:
- left-out passages now go in order, before the get-up;
- the get-up is told once;
- fragments left after a cut are removed;
- the "slow all fight" and feint lines only appear when they fit;
- a shorter interlude, with the INNER LIFE facts;
- the director's line no longer gives the attacker's move to the defender;
- the summary puts the knockout last in its beat.

Still open from that fight:
- **Adrenaline given to the wrong fighter:** "Nerine could feel the adrenaline", which was Ripples' surge.
- **"Recent rain" on a sunny day.**
- **Body parts next to a hit that don't fit:** "her legs throbbed in sympathy" after a neck hit (the story block's
  `{next}` part).
