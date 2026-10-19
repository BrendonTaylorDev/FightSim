# Submission match (Ripples vs Nerine, seed 11): bugs and notes

## Fixed in build 213
- **Tap-out told as a knockout.** On the beat Ripples tapped out, the posture line said she "ends OUT COLD". The
  tap-out note said she was awake, so the two notes contradicted each other. The posture line now says she ends
  down and awake, beaten, not knocked out.
- **Every tap refusal read the same.** Four refusals got the same "her paw twitches toward the ground" line. The
  refusals are now counted against the same opponent (`tap_refused` in `learned`), and the line climbs: a twitch,
  then the paw touching the ground, then the paw lying flat and shaking.

## Still open
- **Fin Slash soaks the target.** A Water-typed Fin Slash soaks her, even when it is the fin's edge doing the work.
- **The ice blade wore off early.** It wore off on the slam in beat 15. That was right by its clock (3 beats), but
  the stand-in plan's later blade slashes never ran, so the blade was only used once.

## Narration lessons drawn from the hand-written sample (narration.md)
- **Refusals climb, beat by beat.** Twitch, then the paw touching the grass, then the paw lying flat, shaking, held
  still. The last refusals have no reason left in them, only stubbornness or a plea. (Now `narration.tap_build`.)
- **The holder's side.** Nerine feels the twitch through her own arms. Her grip is tiring. Her view of Ripples
  shifts from cold to something near pity ("Just tap", said low). (Now `tap_build`, from the second refusal.)
- **After the tap.** The loser curls round the ruined part. The winner stands over her, tired and hurting, and
  doesn't gloat. (Now added to the tap-out note.)
- **Not yet built:** the beaten fighter looking at her own part "the way you look at something that belongs to
  somebody else". A blow while she is held on one leg rocks her so that the hang wrenches the held part. The
  breaking-point beat given room: a sound she never made before, then shoving the rest down.
