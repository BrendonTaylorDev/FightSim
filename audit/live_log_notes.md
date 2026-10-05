# Notes from a live fight (Duchess vs Glacia, lakeside, /scale 10, mistral-small:24b), build 133

Not all fixes below were in the build this log came from. Pull claude/kind-bell-r5ehx4 before re-testing.

## Already fixed on the branch (re-check in a live run)
- **Bird anatomy.** Duchess got teeth, a jaw, fur and paws. Story blocks are now filtered by body, and the notes carry
  a BODY line for birds.
- **"Fighter who isn't in this fight".** It fired on ordinary words (talon, ember, swift, dusk). Now only a
  capitalized name counts.
- **"Wrong move remembered".** It fired on phrases like "icy wind". Now only a capitalized move name counts.
- **The skipped Wing Attack.** Now gets one focused narrator pass. The attack check also accepts wings, beaks and
  talons for Flying moves.

## Still open (seen in this log)
1. **Huge numbers at /scale 10.** /scale 10 combined with the new steep curve gives absurd damage: Ice Beam did +1393%
   to the head and took 209 health in one hit. The /scale warning text ("roughly 240% to a sturdy part") is out of
   date. Either cap the low-resistance multiplier at high scales or update the warning.
2. **Present tense keeps slipping in.** For example "Glacia lifts her head", "Duchess takes in". The tense check
   misses whole paragraphs.
3. **A dangling thought tag.** "She thought," was left with nothing after it (intro, Glacia). When a thought is cut,
   its tag must go with it.
4. **Block or instruction text leaking into prose.** For example "She walked it across the body, from one part to the
   next", "A thin careless? broke out of her", "a tremendous blow on a part that was already very painful". Find
   which blocks or notes these come from and reword them so they can't be pasted in.
5. **The same attack told twice.** The Aerial Ace dive was told twice in one part, and with "claws" for a bird.
6. **A blocked blow still knocked her down.** Glacia blocked Aerial Ace (x0.45) yet was "knocked down: the shallows".
   The director's landing ran on a guard block. Decide whether a block can knock someone down, and skip the landing
   if not.
7. **Speed.** Beats took 4-8 minutes, with 22-27 model calls, mostly paragraph fixes (15-21 a beat), and notes of
   34-46k characters. Ideas: cap paragraph fixes per beat lower, trim the notes, or let the time budget cut fixes
   sooner.
8. **Check targeting before changing it.** In this log the head took most hits through dice rolls (the chain stayed
   on the same spot after a roll of 1). The user considers that working as intended: see the design principles in
   AUDIT_PLAN.md.
