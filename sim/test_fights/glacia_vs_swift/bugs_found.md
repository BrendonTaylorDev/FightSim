# Bugs found in test fight 6 (Glacia vs Swift, mountain shelf, knockouts only, no pins)

The full fight with narration, damage and the fighter cards is `Glacia_vs_Swift_full_fight.html`: the game's own
export, made by `replay.py`. It replays `plan.py` with `narration.md` as the narrator's text. Fixed in build 208 unless
marked otherwise.

## A bird's body, said as a furred body with paws
- **Fixed:** the opponent-watch signs said "the ribs working under the fur" and "the ears flick back" for birds. The
  signs are now filtered for her body, and her own covering replaces "fur". A fighter in the air gets signs of a hurt
  flyer instead of standing ones: ragged wingbeats, losing height, flying lopsided.
- **Fixed:** STILL FEELING IT said "a paw pressed to it" (and, after the first fix, "a wing pressed to" her wing). A
  bird now keeps the hurt guarded and turned away, her beak going to it to smooth the feathers. In the air it says "as
  she turns in the air", not "as she gets up".
- **Fixed:** the old-wound notes said "a paw clamped to her ribs" and "hissing through her teeth" for a bird. They now
  say a wing and her beak.
- **Beats 16, 20 (fixed):** an old wound on the forked tail said "she grabs at the leg" and "the leg nearly folds".
  Tails now have their own row.
- **Beat 13 (fixed):** a stagger ended "she has to put a hand or paw down to stop" for a bird. The choice is now
  fitted to her body, and a wing flung out against the ground has been added.
- **Beat 3 (fixed):** "favoring it and testing weight on it" for a thigh hit in mid-air. In the air it now says the
  leg is drawn up tight under her.

## Flight
- **Beats 9, 10 (fixed):** when a flyer's time in the air ran out, the note said "Glacia shakes off being in the air:
  show it wearing off". It is now a landing: she comes down at the end of the beat, on her feet, tired, not knocked
  down.
- **Beat 5 (fixed):** a dodge in mid-air said "She stays on her feet". It now says "She stays up in the air".
- **Not fixed:** a Peck with count 3 ("hovers in her face and pecks three times") became one dive. A flyer's close
  move from the air is always a dive, and the count is dropped (beat 15).

## Moves and hits
- **Beat 7 (fixed):** Steel Wing was "(Delivered with her CLAWS, as the move says)" because the director's order
  said "rakes". A move that strikes with wings no longer takes a weapon from the order's words.
- **Beat 6 (fixed):** Air Slash's body detail began "the claws catch first". A slash thrown from a distance now has
  its own "blade" wording.
- **Beat 4 (fixed):** Blizzard's "Hardest hit: Throat (a heavy blow), Right Eye (a heavy blow)…" disagreed with the
  per-part lines ("a solid blow"). The list now uses the same capped size as each hit's own line.
- **Beat 16 (fixed):** HER REACTIONS BUILD on a whole-body Blizzard ("they climb to the worst one, hit 21"). A
  whole-body surge is one moment, so it no longer gets the climb note.
- **Not fixed:** "Glacia raking back as they cross → she rakes back" was rolled in beat 5, but the dodge and counter
  took that beat and the rake never showed.

## Scene and summary
- **Fixed:** every beat said "on dry land, not in the water (no swimming)" on a mountain shelf with no water. That
  line now appears only where the arena has water, and never for a fighter in the air.
- **Fixed:** the injury report said "Glacia's flash-freezes the target". An `about` that starts with a verb is now
  replaced by the move's name ("Glacia's Freeze-Dry").
