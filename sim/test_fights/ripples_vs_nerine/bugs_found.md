# Bugs found in test fight 5 (Ripples vs Nerine, lakeside clearing, knockouts only, no pins)

Fixed in build 207 unless marked otherwise. The beat numbers refer to `engine_log.txt` (the run before the fixes).

## Engine
- **Beats 15–16 (fixed):** a coil's BOUND status outlived the coil. Nerine broke the Tail Bind on her leg in beat 14,
  yet her shoulder barge and pummel were still marked "× 0.9 (her right thigh bound)". CONSTRICTED did the same after
  the neck coils came off in beat 23. Both now end with the beat once no coil of that kind is on her.
- **Beat 23 (fixed):** "× 0.75 (arms trapped in the coils)" was applied to a fighter whose NECK was coiled. Now it only
  applies to coils round the body.
- **Beat 11 (fixed):** "Nerine loses her grip … Ripples was thrown" on a slam. It now says "slammed down".
- **Beat 23 (fixed):** the grip-shaken note told the narrator "it cost her 3% of her health at once", a number in the
  prose notes. The number now stays in the math display only.
- **Beat 29 (fixed):** the injury report called an excruciating chest "sore and stiff tomorrow". The words now follow
  the pain level (excruciating or worse = deep, very painful = sore), and hurting parts are listed too.

## Display (stat lines)
- **Fixed:** "aimed at Ripples's Head", plus the same in seven more display lines and the director's hold list. These
  now use poss_word.
- **Not fixed:** an Aqua Tail with the director's own "knocked down" still shows the move's own knock-down roll as "→
  no", which reads as a contradiction (beat 18).

## Narrator notes
- **Beats 10–21 (fixed):** WHAT … SEES OF … HURT repeated nearly the same three signs every beat, always ending "she
  breathes shallow, not letting her chest fill". It also came in both parts of a beat with different signs. Now it
  comes in one part of the beat, the signs rotate (none offered two beats running when there are others), and the
  worst wound's own sign comes every other time at most.
- **Fixed:** HER OWN WOUNDS was asked for in both parts of a beat. Ripples also took stock of her chest and stomach
  alternately, almost every beat. Now it is one part per beat, and a wound comes up again only when it gets worse or
  after `wound_watch_again` (5) beats.
- **Beat 16 (fixed):** HER REACTIONS CLIMB said "the last one is the worst" for a 7-blow pummel whose worst blow was
  the second. When the worst blow is not last, the note now names it and has the later blows add to it.
- **Beats 17, 27 (fixed):** STILL FEELING IT listed four parts and said "she nurses it". Now it lists the worst two
  and says "them".
- **Beat 14 (fixed):** "THE OPENING: Nerine is held, with nothing free to cover herself", when only her leg was
  bound. A grip that holds only a leg or the neck now says she can't step away, and that her arms are free.
- **Beat 23 (fixed):** "it rocks her back, but she keeps her grip" on the same blow that broke her grip. When the
  same hit shakes her grip loose, the rock line now says the grip goes with it.
- **Beat 23 (fixed):** two "THE HIT BREAKS HER GRIP" lines appeared for one pair of tails round the neck and throat.
  Now there is one line, naming both parts.
- **Beat 26 (fixed):** "she gets her feet back under her" as off-balance wore off on a fighter lying in the roots.
  There is now a lying-down version.
- **Beats 8, 27 (fixed):** NOT VERY EFFECTIVE said "her body shrugs much of it off" for an Aqua Jet that charged her
  into a pine and crumpled her, and for an Aqua Tail that took a sixth of her health. A charge into the scenery, or a
  blow whose parts add up to a lot, now gets the "the water doesn't get in, but the blow still hurts" version.
- **Beat 5 (fixed):** "She stays down where she is" sat next to a get-up later in the same beat. It now says "She
  stays down under it (a get-up, if one is listed, comes after)".
- **Beats 20–21 (fixed):** the tail choke's reactions came from the general grip pool: "she huffs and plants her
  paws, unbothered for now" while "her sight greys at the edges". Light grips on the neck or throat now use choke
  reactions (a stuck swallow, a thin whistling breath, paws flying to it).
- **Fixed:** "Ripples's" in the HOLDS line, in story-line slots ("under {foe}'s weight"), in the missing-attack
  rewrite and in "wet or dry: Ripples's fur".

## Not bugs, but worth knowing
- Nerine's description calls her "a hit-and-run striker rather than a grappler". In this fight she brawled, so
  the notes contradicted the director. The new HOW EACH HAS FOUGHT SO FAR note (`narration.style_read`) now tells the
  narrator how each has really been fighting.
- The pummel against the trunk ran to 7 blows when the director asked for 3. That is by design (the engine decides how
  long a pummel lasts), but it was the single biggest swing of the fight (−17%).
