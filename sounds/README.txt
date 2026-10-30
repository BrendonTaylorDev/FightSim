(since build 329, window.sounds) Sounds for the fighters' bodies: the gasp of a light hit, the grunt and the cry of
harder ones, the scream when something is ruined, straining and whimpering in a hold, choking in coils, the breath
coming back when her heart starts again, panting when she is spent. No impact sounds: only her.

The sound files are yours: put .wav files (or .mp3) in sounds/<kind>/ (any number; one is picked at random each
time). A fighter's own voice goes in sounds/<her name>/<kind>/ or sounds/<species>/<kind>/ and is used first. Kinds
with no files are simply silent. The window plays each beat's sounds as the beat lands; an exported fight carries
them too (window.sounds.export).

Nothing here changes the fight: it only reads the cards' data, beat to beat.

The kinds:
  gasp/  a light hit: a sharp breath in
  grunt/  a solid hit: the breath knocked out of her
  cry/  a heavy hit: a cry of pain
  scream/  a devastating hit, or a part ruined
  strain/  fighting a hold or a grip: effort through her teeth
  whimper/  held near her limit, refusing to tap
  choke/  coils squeezing her in hard, or a choke on her
  breath_back/  her heart starting again, or coming round: a long shuddering breath in
  pant/  spent or short of air: hard breathing (now and then, not every beat)
