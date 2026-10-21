# Bugs I noticed while narrating (seed 8)

1. Two "last stand" features: the old moves.last_stand (below 15% strength, 50% per attack, x1.3, energy to 0) fires
   (beats 55, 56); Build 246's low_health.last_stand duplicates it and never fired. Merge: keep the old blow, make
   low_health.last_stand the "wide open the beat after it" part only.
2. Beat 40: Nerine, face-down in a heel hook (Ripples tangled round her leg), bites Ripples' left shoulder, throat
   and neck. A held fighter's reach isn't checked against where the holder is.
3. Beat 29: Ripples, her right arm in a kimura, throws Brick Break (an arm move): fine only with the free arm; the
   notes should say which arm (the free one).
4. Beats 63-66 (HIGH): a fighter held in a submission locks one of her own on the holder (63: Nerine, in Ripples'
   standing armbar, locks an armbar on Ripples; 65: Ripples, in Nerine's armbar, locks a rear chinlock on Nerine),
   and both tap in the same beat (66). start_submission/start_custom_submission don't refuse a holder who is
   herself in a submission.
5. Beat 59: low_squirm told the beat Ripples was thrown down (it should wait a beat: "not the beat she went down").
6. Beat 60: an upright hold ("standing armbar") locked by a holder who is lying down herself (from_ground) on a
   sitting fighter: the look ("at her side, ... bending her forward") assumes the holder is up.
7. Beat 76: the same as 4: Nerine, held in Ripples' root lever, locks an ankle lock on Ripples.
8. Aftermath injury report: "Ripples is the one still standing, if only just" while Ripples lies on the grass and
   can't get up (beat 78).
