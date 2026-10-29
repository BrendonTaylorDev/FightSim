"""
Fight story loop. There are no turns: the director model decides who acts next, every beat.
After each beat's prose, the program prints the exact stat block (before / calculations / after).

Run:  python play.py                 director + narrator from Ollama, with stat blocks
      python play.py --hide-math     prose only (toggle anytime with /math on|off)
      python play.py --no-llm        manual /commands only, for testing your rules

At the prompt:
  [Enter]            let the director decide what happens next
  any text           steer the next beat, e.g.  Ripples drags Nocturne away from the water
  /command           manual control and tools (type /help)
"""
import argparse
import collections
import os
import time
import json
import re
import random
import shlex
import sys
import threading

from director import Director, resolve_many
from display import Display
from engine import Engine, BALANCE, body_region as body_region_of, species_of, poss_word, note_failure
from narrator import Narrator, strip_pov, _is_sound
import narrator as narrator_mod
import llm
import polish
import body as _body

VERSION = "2026-10-29 build 318 (simulated body: blood loss, adrenaline, swelling, broken bones)"

HELP = """
=============================================================================================
 PLAYING
=============================================================================================
  [Enter]                     the director picks the next beat
  <any text>                  your direction for the next beat ("Ripples goes for the throat")
  /play <names | all | off>   PLAY AS one, several or all fighters. Each beat you're asked for each one's move
                              ("Nocturne > "), with her strength, state, moves and this beat's pin openings shown
                              first. Type the move in plain words ("slash at her face", "I bite her throat and
                              hold"); Enter lets the director choose for her this beat; "wait" = she holds back. The
                              director turns your words into actions and runs everyone you don't play; the dice still
                              decide what lands. Every /command works at those prompts too, for direct control over
                              what happens (/strike, /pin, /down, /getup, /undo...).
                                /play Nocturne      /play Nocturne Ripples      /play all      /play off      /play
  /play dice fair|strict|free how the dice treat the fighters you play. fair (default): the dice decide, and your
                              /commands can still force outcomes. strict: at the mercy of the dice: pins,
                              submissions, getting up and escapes only when the dice allow; commands follow the same
                              rules as the director, and the ones that decide an outcome (/pinsuccess, /getup, /down,
                              /eliminate, /undo...) are refused. free: the dice are off for your fighters: their
                              attacks always land, openings are always there, they rise at the first try and break
                              any pin or hold they try to (rolls against them still count).
  /auto <n>                   let the director run n beats on its own (for whole fights: /autofight)
  /auto pin                   play the running pin out, beat by beat, until it ends
  /stop                       (in the window, while /auto or /autofight runs) end the run after this beat
  /wait [what happens]        a beat with no new attack (holds and pins keep going)
  /more [words] [what to dwell on]   (or just +)  STAY in the moment instead of moving on: more paragraphs about
                              the stillness and what the last blows left behind. Nothing happens and no time passes
                              (no new attack, no pin seconds, no get-up roll); use it as often as you like.
                                +        /more 400        /more "Ripples' ruined shoulder, and Nocturne watching"
  /more auto <0-3>            add that many such passages after every beat with an attack, on their own
  /interlude [now [words] ["what to dwell on"]|next|chance x|words n|gap n|on|off]
                      a long passage where the fight draws breath (sometimes on its own; now = one at once)
  cmd && cmd && ...           run several commands in a row, one beat each
                                e.g.  /scale 3 && /pinbeat 5 && Nocturne goes for the pin
  /cmd + /cmd [+ /cmd]        up to three attack commands in the SAME beat, in order
                                e.g.  /down Ripples up + /pin Nocturne Ripples

=============================================================================================
 FIGHTS: WHO IS IN THEM, STARTING OVER, WHOLE FIGHTS ON THEIR OWN
=============================================================================================
  /fighters                   who is in fighters.json, and who is in this fight
  /variant [fighter name]     which version of a fighter is used. Ripples comes as "sleek" (no flotation sac: a bare
                              throat; the default) and "original" (with the sac).   /variant Ripples original
  /newfight [names | all]     start a fresh fight without restarting: everyone back to full health, the story
                              starts over. With names, only those fighters take part (two or more):
                                /newfight Nocturne Ripples      /newfight all      /newfight (same line-up again)
  /summary                    after a win: the fight summary again (key moments, the finish, the turning point,
                              damage dealt, the biggest blow, the loser's worst injuries, what decided it)
  /simulate [fights] [names]  balance check with NO model: whole fights played by dice-driven stand-in choices on
                              the real engine (copies of your rules and arena; the fight in progress is untouched),
                              then win rates, lengths, pins, escapes and the worst health swing:
                                /simulate 50 Nocturne Ripples      /simulate 20 Talon Blaze
  /autofight <fights> [aftermath beats] [names]
                              the director runs whole fights start to finish, one after another, each followed
                              by that many aftermath beats (default 2), then shows the results:
                                /autofight 3 4                     three fights, four aftermath beats each
                                /autofight 5 2 Nocturne Ripples    five fights between those two
                              Stop it with the interrupt button (Ctrl+C); the beats already played stay.
  /results                    winners and lengths of the fights played this session
  /team <names> [as <name>]   put fighters on one side for good: they never attack each other, and win together
                              (saved to rules.json, so it holds for every fight).  /team Nocturne Ripples as Shadows
                              /team <name> solo   takes her off her team.   /team off   ends all teams.   /team  shows
  /ally <names> [beats] [until <name>]   a TEMPORARY alliance, as a story beat: they stop attacking each other and
                              work together for that many beats, or until the fighter you name is out; it always
                              ends when nobody else is left to fight, and then they are opponents again.
                                /ally Nocturne Ripples until Seraphina      /ally Nocturne Ripples 6      /ally off
  (Your settings carry from fight to fight: /plan, /focus, /scale, /talk... Use /plan off to drop a story plan.
   Start with a line-up straight away:  --fighters Nocturne,Ripples  on the command line.)

=============================================================================================
 ATTACKS YOU CHOOSE
=============================================================================================
  Quote anything with spaces. Severity words (light, solid, heavy, brutal...) come from rules.json.

  /move <att> <def> "<Move>" ["Part,Part"] [count]
        A named move. Any move in moves.json works, even one she doesn't know (used once).
        Leave out the parts and the dice pick them; whole-body moves never need parts.
          /move Ripples Nocturne "Aqua Jet" "Right Flank"
          /move Seraphina Nocturne "Hydro Pump" "Chest,Left Shoulder,Neck"
          /move Nocturne Ripples Thunderbolt
          /move Ripples Nocturne "Tail Bind" "Left Hock,Right Hock"      (a hold move starts a hold)

  /charge <att> <def> "<Move>" "<what she's driven into>" ["Part,Part"]
        A charge that doesn't stop at the hit: she is driven back and slammed into the scenery, crushed between the
        attacker and it, and usually crumples at the end of the beat. Any charging move (Take Down, Aqua Jet...),
        or any name for an improvised one. Join a second command with  +  to hit her BEFORE she falls (same beat):
          /charge Nocturne Ripples "Take Down" "the cave wall"
          /charge Ripples Nocturne "Aqua Jet" "a fallen boulder" "Chest" + /move Ripples Nocturne "Ice Fang" "Throat"
          /charge Seraphina Ripples "body ram" "a stalagmite"

  /sustain <att> <def> "<Move>" <pulses 2-4> ["what she's pressed into"] ["Part,Part"]
        Hold a stream or beam move for several pulses. The surface can break.
          /sustain Seraphina Ripples "Hydro Pump" 3 "a fallen boulder"
          /sustain Nocturne Ripples "Hydro Pump" 3 "Chest, Neck, Head"   (a part list = where it hits)

  /strike <att> <def> <part> <severity> [count] ["flavor"]
          /strike Ripples Nocturne Muzzle light 3 "three quick bites"

  /combo <att> <def> "<Part:severity,...>" ["flavor"]
          /combo Seraphina Nocturne "Back:heavy,Left Ribs:heavy" "slams her whole weight down"
          /combo Seraphina Nocturne "Left Thigh:heavy,Ripples>Left Thigh:solid" "tail sweep takes out both"
          (Name>Part hits a different fighter)

  /land <fighter> "<surface=Part+Part:severity; ...>"
        Crash into the arena (she was thrown). Leaves her on the ground, and tears her out of any hold or pin,
        hers or anyone's on her. Parts are optional.
          /land Ripples "a stalactite=Upper Back+Head:heavy; the floor=Lower Back+Left Hip:solid"
          /land Ripples "the floor:solid"

  /down <fighter> [down|up|side|sit]   put her on the ground (no damage), optionally face-down, on her back, on
                              her side, or sitting up. Any pin or hold she had on someone else ends.
  /face <fighter> down|up|side|sit set which way a fighter on the ground lies, no beat; a pin's presses move
                                   to the side that's now exposed
  /posture  (or /face alone)       how everyone is placed right now: up, down and which way, pinned, on top
  /getup <fighter> [tries]    stand her up now (1-3 tries, or worked out from her injuries); not while pinned
  /eliminate <fighter> [why]  she's out of the fight

=============================================================================================
 ONE FIGHTER MOVING ANOTHER
=============================================================================================
  Each is a narrated beat. Name just the fighter being moved and the other one does it; with three or more in
  the fight, name who does it first:  /situp Nocturne Ripples   = Nocturne sits Ripples up.
  Add "how" in quotes to steer the telling:  /rollover Ripples "with a hooked forepaw under her ribs"

  She has to be on the ground for these (no damage; they set up what comes next):
  /rollover <fighter>      flip her: face-up <-> face-down. A running pin's presses follow the roll.
  /onback <fighter>        onto her back (chest, belly and throat exposed)
  /onfront <fighter>       onto her front (back, hips and the back of her neck exposed)
  /onside <fighter>        onto her side
  /situp <fighter>         hauled up to sitting: still on the ground, front and back both in reach. The next blow
                           that lands knocks her flat again; a hold put on her keeps her sitting. Not while pinned.
  /pickup <fighter>        lifted bodily off the ground (she is no longer down). Not while pinned.
  /standup <fighter>       dragged up onto her feet and held there. Not while pinned.

  These do damage through the arena. The surfaces are written like /land; leave them out for the plain floor:
  /throw <fighter> ["surface=Part+Part:severity; ..."]   seized and hurled; a fighter lying down is hauled up first.
          /throw Ripples "a stalagmite=Upper Back+Head:heavy; the stone floor:solid"
  /slam <fighter> ["surface..."]                         lifted and driven down at the thrower's feet (heavy)
          /slam Nocturne Ripples "the edge of the ledge=Lower Back+Left Hip:brutal"
  /drag <fighter> ["surface..."]                         hauled across the ground where she lies and into or
          against whatever you name; she stays down, and a hold already on her stays on.
          /drag Ripples "the rough stone floor:light; a stalagmite=Chest+Left Shoulder:heavy"
          /drag Nocturne Ripples "the cave wall"

  /grapple <attacker> <defender> ["Part=what grips it"]   she takes hold of her and KEEPS hold, both on their feet.
          While the grab lasts neither can dodge the other, and she can work her over:
          /grapple Nocturne Ripples "Left Upper Arm=her jaws"
          /move Nocturne Ripples "Night Slash" "Chest" 3       a pummel: 3 short blows, each lighter than a full one
          /sustain Ripples Nocturne "Water Gun" 3               a stream held on her at no distance
          /throw Nocturne Ripples "a stalagmite:heavy"          out of the grab: it can't be slipped
          The held fighter rolls to wrench free every beat. /release Nocturne Ripples lets go.
  A CHAIN is two or three attacks by one fighter joined with  +  : each leads into the next.
          /grapple Nocturne Ripples + /move Nocturne Ripples "Night Slash" "Jaw" 3 + /throw Nocturne Ripples
  A TUMBLE: end a /throw or /land list with "; tumble" and she doesn't stop where she lands:
          /throw Ripples "the cave wall=Left Hip:heavy; tumble"
  /tumble [chance|on|off]     how often a thrown or launched fighter tumbles on by herself (30%)
  /bigmoments [more|less|off|due <beats>|<kind> <chance>]    how often the fighters go for a held stream, a charge
          into the scenery, a throw, a grapple or a chain, and how long the fight may go without one (10 beats)

  As a setup, join one to an attack with  +  (same beat, in order):
          /situp Ripples + /move Nocturne Ripples "Night Slash" "Chest"
          /onfront Ripples + /pin Nocturne Ripples
          /pickup Ripples + /slam Nocturne Ripples "a fallen boulder=Upper Back:heavy"
  The fighters also do all of this on their own, now and then. How often:
          /set director.reposition_chance 0.12    moving a downed opponent is suggested on this share of beats
          /set director.grapple_chance 0.05       a throw or slam of a standing opponent is suggested
          /set director.manhandle_cooldown 0      beats before the same fighter may throw, slam or drag again
                                                  (0 = no wait; build 99 had 3)
  When the FIGHTERS choose it (never on your own commands), a fighter on the ground with strength left may fight
  the grab off, and a thrown fighter with strength left may roll through the landing and come up on her feet.
  A fall into a wall, boulder or stalagmite can end with her slumped sitting against it. See /variety.
  /roll <att> <def> over|back|front|side|sit|up|stand     the older spelling of the first seven

=============================================================================================
 HOLDS AND PINS
=============================================================================================
  /hold <att> <def> "<Part:severity,...>" [easing|steady|tightening] ["flavor"]
          /hold Seraphina Ripples "Chest:firm,Stomach:firm" tightening "coils around her"

  /pin <att> <def> "<Part:severity=what presses it,...>" ["flavor"]
        A pin: several parts pressed every beat while the clock runs. Then press Enter or /wait.
          /pin Ripples Nocturne "Chest:crushing=her full weight,Neck:firm=teeth" "sits on her chest"
        The parts you name decide how she lies: press the chest of a face-down fighter and she is turned onto
        her back. If the PINNED fighter pins her pinner, that's a reversal: the old pin ends, she ends up on top.

  /adjust <hold_id> [severity] [ramp]       change one hold
  /release <hold_id> ["how"]                end one hold
  /release <att> <def> ["how"]              end every hold att has on def (breaks a whole pin)
  /struggle <pinned>                        she tries to break free this beat (result rolled)
  /pins [number|off|default]                how often pins come: 1 = twice as many, 0.25 = half (default 0.5)
  /pinsuccess <att> <def> ["Part:sev=with,..."]   the pin wins now (starts one if none is running)
  /pinescape <att> <def>                    the pinned fighter breaks free right now (her blow lands on the pinner)
  /quickpin <att> <def>                     old-style three count, rolled by the engine

  Pin clock and pin damage:
  /extendpin [pinner pinned] <n>            give the pinned fighter n points back (she passes out at 100)   /extendpin 30
  /pinclock [pinner pinned] <n>             set how far gone she is, 0-99          /pinclock 80
                                            (with /pinfade off these add seconds / set the clock's total, as before)
  /variety [set] [way number]               how each outcome plays out (ways of dodging, of keeping her feet after a
                                            charge, of failing to get up...) and how often; lists the other rolled
                                            outcomes too (sitting against a wall, rolling through a throw...)
  /pinfade [beats] [spread] | on | off      pins have no fixed length: each beat brings the pinned fighter closer to
                                            passing out, usually about <beats> (6) of them, sometimes more or fewer;
                                            no clock in the story.   /pinfade 8   /pinfade off = the old fixed clock
  /makesure [on|off]                        after a pass-out the pinner keeps her grip a moment or two longer to be
                                            sure it isn't a trick, then lets go (on by default; story only)
  /pinbeat [secs]                           seconds each beat of a pin covers (1, 5, 10...)
  /pinlength [secs]                         total length of new pins (only with /pinfade off)
  /pinpower [mult]                          scale all pin damage                   /pinpower 0.5
  /holdstart [mult]                         damage a hold does on the beat it starts (1 = a full beat of pressure,
                                            0 = none until the next beat)          /holdstart 0.5
  /holdbreak [base] [per beat] [max]        holds have no time limit; each beat the held fighter rolls to break free.
                                            base = the chance fresh against fresh (0.12), + per beat held (0.015),
                                            never above max (0.6).   /holdbreak 0.08 0.01   /holdbreak 0 = no roll
  /holdshake [number]                       a hard hit can shake loose what the fighter it lands on is holding:
                                            chance = share of her health lost at once × number (2.5)   /holdshake 0
  /pinstart [mult]                          the same for a pin's presses (1 by default: the presses land the beat the pin starts)
  /pinshape [name number]                   how often each way of building a pin is suggested (jaws on the throat, jaws
                                            pinning a paw, a tail choke, a twisted arm, tangled legs, a lifted leg)
  /secure on [parts] [part%] [strength%] | off
        Pins can only be WON once she's worn down enough (early escapes still happen).
          /secure on 6 150 50     (6 parts at 150%+ and strength at 50% or less)

=============================================================================================
 STEERING THE STORY   (nudges for the director; the dice still decide)
=============================================================================================
  /plan <shape> [name]   the shape of the whole fight, told to the director every beat (/plan alone: what is set)
          /plan close            back and forth, nobody pulls far ahead (/plan close Ripples: and she edges it)
          /plan dominate Seraphina   she DOMINATES: the other gets a beat of her own only now and then
                                 (director.plan_dominate.rival_turn_chance, 0.15), and her dodges, counters and
                                 break-free rolls are cut (defence_mult 0.4). A direction you type is never changed.
          /plan comeback Ripples     beaten down first, then she turns it around
          /plan winner Nerine        she should win in the end, but make it earned
          /plan even             share the attacks fairly          /plan off   no plan
  /encourage <kind> [blows/links] [attacker] [defender] [beats]   point the director hard at one kind of attack
          for a few beats (default 3; a nudge, not an order). Kinds: sustain pummel charge chain throw slam grab hold
          pin submission feint dive carry spike juggle launch, or your own words in quotes.
          /encourage sustain 3   /encourage sustain Nocturne Ripples 3   /encourage pummel 3 5 Nocturne Ripples
          (3 blows, 5 beats)   /encourage "bites to the tail" 4   /encourage list   /encourage off
  /targeting one|few|many|all|auto          how many body parts attacks spread across
  /reason [list|<n or id> [holder]|swap|new|"your own"|off|on]   why the two are fighting (off by default)
  /focus [fighter] <zones...|off>           where attacks aim: head, neck, core, belly, back, arms, wrists,
                                            legs, ankles, paws, tail, limbs, upper (combine: /focus core head).
                                            Saved to rules.json.
          /focus injured           go back to what's already hurt and the parts around it (and a badly hurt
                                   side as a whole); the worse a part is, the more often. Combines: /focus injured legs
          /focus core              everyone aims at the body
          /focus neck              the throat and neck (with no /focus, no part of the body comes first)
          /focus vulnerable        the soft places: throat, eyes, nose, ears, belly, knees and hocks
          /focus weakened          the same as injured
          /focus Nocturne limbs    only Nocturne's attacks go for arms, legs and paws
          /focus strength 0.8      how firmly off-target picks get moved onto the zone (0 = nudge only)
          /focus                   shows what is set now, and every zone
          /focus off               no zone: attacks go anywhere
  /weakspots [0-1|off]                      how often the director is nudged at one weak spot (default 0.2);
                                            with no /focus, nothing else is aimed at first
  /weakspots worked [0-1]                   how many of those nudges are for a run of blows (pummel, combo, chain,
                                            grapple): one weak spot again and again, a group of parts, or several

=============================================================================================
 MOVES   (moves.json: 250+ Pokemon moves)
=============================================================================================
  /moves [type|effect|name|fighter]         browse   /moves fire   /moves sleep   /moves Nocturne
  /moveinfo "<Move>"                        one move's details
  /learn <fighter> "<Move>"                 lend a move for THIS fight only (never saved)
  /forget <fighter> "<Move>"                take a move away for this fight

=============================================================================================
 HEALING AND AFTER THE MATCH
=============================================================================================
  /heal <name> <"Part,Part"|worst|all> <damage> [resistance] ["how"]    a narrated healing beat
          /heal Ripples "Right Paw,Chest" 100
          /heal Ripples worst 80 20 "finds an Oran Berry"
  /restore <name> <health %> ["how"]        restore overall health (capped at her max)
  /getup <loser>                            after the match: she gets back to her feet
  /recover <loser> [stirring|awake|up]      after the match: one recovery stage, or straight to one
  (After the match, Enter keeps the aftermath going; the loser may come around on her own.)

=============================================================================================
 BALANCE: HOW HARD HITS LAND, HOW FIGHTS END   (saved to rules.json unless noted)
=============================================================================================
  /scale [n]          how hard every hit lands on body parts (3 is what the fighters are tuned at; /scale alone
                      shows the current value)
  /length [beats|default]   how long fights run: presets for about 30, 35, 40, 45, 50 or 60 beats (default 40)
  /healthloss [n]     how much health each point of body-part damage costs (/healthloss alone shows it)
  /resscale [n]       how fast body-part resistance wears down (separate from /scale)
  /wear [n]           resistance ALSO lost per 1% of damage a hit really does (0 = off)   /wear 0.05
  /vital [word n | on | off]   how much each body part matters to overall health (a throat more, an ear far less)
                      /vital = show every part's weight      /vital ear 0.3      /vital off = all parts count the same
  /numb [on|off]      the "numb with shock" pain level at 1000%+ (off: those parts stay devastated)
  /fighter <name> <field> [value] [beats]
        fields: health, maxhealth, energy, status, clearstatus, down, up, recovery, revive
          /fighter Ripples health 900     /fighter Nocturne status paralyzed 2
  /part <name> "<Part>" damage|resistance <value>      /part Ripples "Right Paw" damage 120
  How a fight can end, and other switches: /help switches

=============================================================================================
 NARRATION: HOW THE STORY IS WRITTEN
=============================================================================================
  /words [n]          narration length per beat
  /talk quiet|less|normal|free   how much the fighters speak and think in italics (default: less)
  /sounds always|often|sometimes|rarely   how often a hurt fighter makes a sound (default: always)
  /sounds write often|sometimes|rarely|never   how often a sound is written out, *Nngh* (default: often)
  /sample [name]      which style sample the narrator imitates. /sample lists them; /sample 1 or /sample
                      style_sample.txt switches (saved). style_sample_scenes.txt is written in sections, and the
                      narrator is shown the passage that fits the part it is about to write.
  /style <text>       an extra style note for the narrator this session
  /blocks [on|off|n|reset]   story building blocks (story_blocks.txt): ideas for reactions, sensations, what an
                      opponent can see of an injury, ways to stage a move, thoughts and more, offered to the
                      narrator a few at a time when they fit the fight, the least-offered first. /blocks shows the
                      counts; /blocks 6 = at most six per part; /blocks reset forgets what has been offered.
  /passages [on|off|0.3|reset]   story passages (story_passages.txt): finished showpieces for the big moments (a
                      heavy blow, a cut, a bite, a choke, a hold, a pin, a landing, a knockout), now and then offered to
                      the narrator to set in word for word or to draw on. /passages shows the counts.
  /phrases [forget]   the stock phrases the story has used, with running totals (kept between fights and runs);
                      a recently used one is rested for a while, then allowed back. /phrases forget starts over
  /model [narrator|director] [name]   which Ollama model writes the story / picks what happens (this session).
                      /model narrator gemma4:31b   /model   (shows both)
  Checking and speed:
  /budget [min|off]   a beat's time budget (default 6): past it, the optional extra checking passes stop;
                      /budget timing on|off shows where each beat's time went
  /timing [on|off|clear]   after each beat the program says how long it took, how fast the model wrote, and what
                      had to be written again. /timing alone: the averages so far, by narrator model (for
                      comparing two models: play some beats on each, then /timing).
  /checks [clear]     which mistakes the narrator's checks keep finding, and how often the paragraph fixes for
                      each kind work and what they cost (this fight, and all fights so far)
  /polish ...         a stronger online model (Venice.ai by default) improves each beat's prose without changing
                      what happens (narration.polish; off until you turn it on). /polish alone: how it is set.
                      /polish key <key>, /polish models, /polish model <name>, /polish on|off,
                      /polish when every|big (big: taps, knockouts, the finish and other big moments only),
                      /polish now (the last beat, now). /polish prompt shows the instructions the editor gets;
                      /polish prompt edit opens them to change (polish_prompt.txt), /polish prompt reset brings
                      back the built-in ones. By hand instead: /polish copy (the request into
                      polish_request.txt and your clipboard: paste it into Venice's chat), then put its answer
                      into polish_reply.txt and type /polish paste. Several beats: /polish copy 5-9,
                      /polish copy 7, /polish copy last 4 or /polish copy all; /polish paste puts each back by
                      its number (/polish paste 7: an unmarked answer for beat 7). Either way the program's checks decide
  /compare            whether the polished version is kept. /compare: the last beat before and after polishing
  /repair on|off      on (default): a paragraph with a mistake is written again by itself and the rest of the
                      part stays word for word. off: the whole part is rewritten for any problem
  /reader on|off      on (default): after each part, the model reads it back against the beat's facts and
                      the paragraphs it finds contradictions in are written again (one short extra call)
  /reader model <name>  have a different Ollama model do that reading (/reader model same = the narrator's)
  /reader cpu on|off    run that other model on the CPU, in system memory, so the narrator stays on the graphics card
  /reader confirm on|off  off (default): on = each thing the reading finds is asked about a second time before
                        any paragraph is rewritten for it (fewer rewrites, but it can talk itself out of a real find)
  More narration switches (guided narration, shorter notes, the extra "staying with the damage" parts...):
  /help switches

=============================================================================================
 SETTINGS, SCREEN AND ARENAS
=============================================================================================
  /set <rule.path> <value> [nosave]     change any rule in rules.json (and keep it in my_settings.json, so a new
                      build doesn't undo it); nosave = this session only. A value is a number, true/false, a word,
                      or JSON. A mistyped path says what it could be. Examples:
                        /set narration.swearing never              /set finish.knockout_only true
                        /set damage.damage_scale 4                 /set director.plan_dominate.rival_turn_chance 0.3
                        /set traits.quirks.cocky.enabled false     /set narration.character.history false
                        /set holds.coil.contest.stall_chance 0.5   /set narration.polish.when big
                        /set moves.side_spill.power_mult 0.5 nosave
                      Find the path first: /sets <word> (/sets coil), or /get <section> (/get holds.coil)
  /get [rule.path]                      show rules                          /get pin.struggle    /get traits.quirks
  The setup questions (setup.enabled, on by default): before a run begins the game asks, one short question at a
                      time, where and who (arena, fighters, versions, whether you play one fighter, several or all,
                      and with which dice), the match (opening passage, kind of match, taps, how often pins come),
                      the story (plan, focus, targeting, why they fight), balance (length, damage scale), the
                      writing (traits, personality and history, swearing and gore, how much is written, hazards,
                      Venice) and anything else, then whether to go beat by beat or let the director run. Enter keeps
                      what is set at every question; at the first one, Enter skips them all and a preset name asks
                      only where, who and how you play. Fewer questions: /set setup.questions (a list), or
                      /set setup.enabled false (only the arena question, as before).
  /preset [name]      a whole kind of match at once (submission, submission3, knockout, pins, anything):
                      /preset lists them, /preset submission ? shows what it changes. /help presets
  /bench [beats] <setting=value> ...   the narration test bench: your last saved beats (2 by default) told twice,
                      as your settings are (A) and with the changes (B), compared on words, paragraphs, model calls,
                      time, rewrites, the checks that fired and repeated phrases; both tellings go to bench_reports/.
                      Nothing in the fight changes. Slow: each beat is two whole narrations.
                        /bench 2 narration.rich.length_mult=1.0      /bench 3 narration.rich.enabled=false
                      (narration.bench: save, keep, folder; each beat's inputs are kept in bench_cases/)
  /sets [section | word | all [file]]   every /set there is, ready to copy, with its current value and what it does:
                      /sets  the sections and how many settings each has     /sets narration.rich  one section
                      /sets pin  every setting with "pin" in its name or note
                      /sets all  writes all of them (about 1,200) to all_settings.md, section by section
  /settings [forget]  what you changed with commands (kept in my_settings.json; a new build doesn't reset it);
                      forget drops them, so the next build's defaults apply
  /style on|off|auto  real bold and italic on screen instead of **asterisks** (auto: on in Spyder and terminals)
  /style color <name> give the bold parts a colour too (yellow, cyan, green...; none = plain bold)
  /layout clear|tight|classic  how the stat math is laid out. clear (default): each hit as three labelled rows
                        (damage, resistance, health: before → after, then the math), blocks spaced out, one chance
                        roll per line. tight: one unlabelled row per hit, packed. classic: the long Before /
                        Calculations / After blocks
  /math auto|full|compact|both|off      how much of the stat math to show
  /scene [name|number|random]   the arenas (scenes.json): /scene lists them; /scene 3 or /scene power plant
                      switches. /scene <a sentence of your own> makes an arena from your description (things
                      named in it can be landed on; nothing in it is tracked as a hazard).
  /hazards [on|off|chance <n>]  what this arena does: its hazards (burns, chills, drenches... when a fighter lands
                      on or is driven into them) and its events (things the place does by itself now and then)
  /hazard <event> [fighter]     make one of the arena's events happen at the end of the next beat

=============================================================================================
 SWITCHES   (the on/off settings people ask about; each is a /set, kept in my_settings.json)
=============================================================================================
  How fights end (or all at once with a preset: /preset submission | submission3 | knockout | pins | anything):
    knockouts only            /set finish.knockout_only true     (a fight ends only when a blow knocks her out)
    no pins at all            /set finish.no_pins true           (with knockouts only)
    submission match          /set finish.submission.enabled true   (only a tap-out or a pass-out ends it; no pins
                                                                     unless /set finish.submission.no_pins false)
    how often pins come       /pins 1 (twice as many)   /pins 0.25 (half)   /pins default
  The narration:
    guided narration          /set narration.guided.enabled false   (the paragraph plan, fact lines, marks, reads;
                                                                     trial branch only)
    shorter notes             /set narration.compact.enabled false  (the shorter-notes trial)
    tactical reads            /set narration.guided.read_chance 0.2  (how often the attacker gets one)
    "staying with the damage" parts (each adds a part to the beat, and time):
                              /set narration.watch.chance 0.3   /set narration.read.chance 0.2
                              /set narration.dwell.chance 0.3   (0 turns one off)
    stock-phrase memory       /set narration.phrase_memory.enabled false     (/phrases shows it)
    swearing                  /set narration.swearing never      (or rare, free)
    setting the scene         /intro off   (or /set narration.scene_intro false): no opening passage, the first
                                           Enter starts the fight.   /intro on brings it back
  Richer narration (slower beats; /sets narration.rich for every part of it):
    all of it                 /set narration.rich.enabled false
    how long a beat is        /set narration.rich.length_mult 2.0    (1.0 = the plain length, 1.5 shorter)
    paragraphs                /set narration.rich.words_per_paragraph 110   (smaller = more paragraphs a part)
    the body under each blow  /set narration.rich.body_detail false
    thoughts from the fight   /set narration.rich.inner false        (INNER LIFE: what she has learned this fight)
    one sense a part          /set narration.rich.senses false
    closing thoughts          /set narration.rich.closing_thoughts false
    the arena question        /set scene.ask_at_start false      (don't ask for an arena at start-up)
  Speed:
    context window            /set narration.context_window 16384   (smaller fits the graphics card better;
                                                                      12288 if it's still tight)
    time budget               /budget 6     (minutes; past it the optional checks stop)
  Every other setting:        /sets   (the sections)    /sets <word>   (search)    /sets all   (all of them, to a file)

=============================================================================================
 LOOKING AROUND
=============================================================================================
  /status [full|name]   health, worst injuries, pins and positions
  /explain [name|status]   what each status on her does and what her heart, blood pressure and breathing mean
  /traits [name]        how each fighter fights: her traits, quirks, style and favourite moves (since build 280)
  /profile [name]       all that, and who she is: personality, history, relationships (the window: Profiles)
  /health [name]        every damaged body part, in stat format
  /energy <name> [n]     give her n energy (25 if no number; -n takes it away; =n sets it), up to 100 (since build 298)
  /look [name]          the narrator describes the scene right now (doesn't advance the fight)
  /effects [what] [on|off]  the living cards and the settling-in notes (since build 306): alone, what is on; with
                        on/off, all of them; or one: breathing, pulse, impact, grey, grips, monitor, settling
                        (the window: the Effects button above the cards)

=============================================================================================
 UNDO, FILES, QUIT
=============================================================================================
  /undo [n]             take back the last beat (or n beats): stats, story, pins, everything
  /reroll               rewrite the last beat's narration (stats unchanged)
  /export [file] [prose]    write every fight this session to a .md file ("prose" = story only)
  /exportfight [file] [all] save this fight (or every fight: all) beat by beat, with each fighter's picture,
                            health, and every body part's damage and resistance, as a page for your browser
  /save [file]   /load [file]   (every beat autosaves: /load autosave)
  /help   /quit

=============================================================================================
 MATCH PRESETS   (rules.json presets: each sets several /set lines at once and keeps them)
=============================================================================================
  /preset                    the list, with what each kind of match is
  /preset submission         only a tap-out or a pass-out ends it; no knockouts, no pins
  /preset submission3        won by the third tap-out, from three different body parts (two for a serpent)
  /preset knockout           only a knockout blow ends it; no pins, no submissions
  /preset pins               a pin held to the end of its clock wins, and a knockout blow can still end it
  /preset anything           whatever happens first: a knockout, a pin held to its end, or a tap-out
  /preset knockout ?         what a preset would change, without changing anything
  /preset pins nosave        for this session only
  Your own: add one to rules.json -> presets (a name, a description, and its settings: rule path -> value).

=============================================================================================
 EXAMPLES   (ways to do common things, start to finish)
=============================================================================================
  A whole fight on its own, as a submission match in the lakeside clearing:
    /preset submission   /scene lakeside   /newfight Nerine Ripples   /auto 30
  Steer it: Seraphina dominates, and her coils go for the middle:
    /plan dominate Seraphina   /focus Seraphina core   /encourage hold 3 Seraphina Ripples
  Play as one fighter and let the director run the other:
    /play Ripples    then at "Ripples >" type her move: "Aqua Jet into her chest, then bite her arm"
    (Enter lets the director choose for her; "wait" holds back; "does nothing" lets the other act on her)
  Exactly the attack you want:
    /move Nocturne Ripples "Night Slash" "Chest"         /move Nocturne Ripples "Slash" "Left Upper Arm" 3
    /sustain Seraphina Ripples "Hydro Pump" 3 "an old oak" "Stomach, Chest"
    /charge Ripples Nocturne "Aqua Jet" "an old oak"  +  /move Ripples Nocturne "Crunch" "Throat"
  A hold, a coil, a pin:
    /hold Seraphina Ripples "Stomach,Chest" crushing "her coils wound round her middle"
    /release Seraphina Ripples      (she lets go)       /pin Nerine Ripples   then   /struggle Ripples   (fight the pin)
  Better prose with Venice (narration.polish):
    /polish key <your key>   /polish models   /polish model <name>   /polish on
    /polish when big         (only the big moments: taps, knockouts, the finish)
    /polish now              (polish the last beat now)     /polish off
    By hand, no key: /polish copy (paste it into Venice's chat), put the answer in polish_reply.txt, /polish paste
  Who they are:
    /profile Ripples   /traits   (the window: the Profiles button, to edit personality, history, relationships)
    /set traits.enabled false          (fight without traits and quirks)
  Change any number, find it first:
    /sets dominate      /get director.plan_dominate      /set director.plan_dominate.defence_mult 0.25
  Fix a beat:
    /undo   /reroll   /undo 3      /save before_finish   /load before_finish
  Balance check with no model:
    /simulate 50 Nocturne Ripples      /simulate 20 Seraphina Nerine
"""


HERE = os.path.dirname(os.path.abspath(__file__))
AUTOSAVE = os.path.join(HERE, "autosave.json")


def _path(name, ext=".json"):
    """Accept 'myfight', 'myfight.json' or a full path; plain names live next to play.py."""
    if not os.path.splitext(name)[1]:
        name += ext
    return name if os.path.isabs(name) else os.path.join(HERE, name)



BEAT_TALLY = collections.Counter()


def _span(sec):
    sec = int(round(sec))
    return f"{sec} s" if sec < 60 else f"{sec // 60} min {sec % 60:02d} s"


def timing_line(row):
    """'⏱ This beat took 1 min 42 s: ...' from one beat's timings."""
    out_rate = row["out_tokens"] / row["out_seconds"] if row.get("out_seconds") else 0
    in_rate = row["in_tokens"] / row["in_seconds"] if row.get("in_seconds") else 0
    again = [f"{row[k]} {k[:-1] if row[k] == 1 else k}" for k in ("paragraphs", "whole parts", "second drafts", "top-ups") if row.get(k)]
    bits = [f"{row['calls']} model call{'s' if row['calls'] != 1 else ''}"]
    if out_rate:
        bits.append(f"writing {out_rate:.0f} tokens/s")
    if in_rate:
        bits.append(f"reading the notes {in_rate:.0f} tokens/s")
    if row.get("load_seconds", 0) >= 1:
        bits.append(f"{_span(row['load_seconds'])} loading models")
    return (f"⏱ This beat took {_span(row['seconds'])}: " + ", ".join(bits)
            + " · written again: " + (", ".join(again) if again else "nothing")
            + f" · narrator: {row['narrator']}"
            + (f"\n   {row['where']}" if row.get("where") else ""))


def timing_summary(rows):
    """Average beat by narrator model, for /timing."""
    if not rows:
        return "No beats timed yet (timing needs the models: it counts their calls)."
    out = ["Timing so far, by narrator model:"]
    for name in dict.fromkeys(r["narrator"] for r in rows):
        mine = [r for r in rows if r["narrator"] == name]
        n = len(mine)
        tot = lambda k: sum(r.get(k, 0) for r in mine)
        rate = tot("out_tokens") / tot("out_seconds") if tot("out_seconds") else 0
        out.append(f"  {name}: {n} beat{'s' if n != 1 else ''}, {_span(tot('seconds') / n)} a beat on average "
                   f"(shortest {_span(min(r['seconds'] for r in mine))}, longest {_span(max(r['seconds'] for r in mine))}); "
                   f"{tot('calls') / n:.1f} model calls a beat"
                   + (f", writing {rate:.0f} tokens/s" if rate else "")
                   + f"; written again per beat: {tot('paragraphs') / n:.1f} paragraphs, {tot('whole parts') / n:.1f} whole "
                   f"parts, {tot('second drafts') / n:.1f} second drafts, {tot('top-ups') / n:.1f} top-ups"
                   + (f"; {_span(tot('load_seconds'))} spent loading models" if tot("load_seconds") >= 1 else ""))
    return "\n".join(out)


def _marks_of(eng, f):
    try:
        return eng.picture_marks(f)
    except Exception as e:
        note_failure("working out the damage marks for the pictures", e)
        return {}


def fight_snapshot(s, label=None):
    """Every fighter as she stands right now (plain data): health, energy, statuses, posture, and each body part's
    damage and resistance. Kept for every beat (/exportfight, the window's history)."""
    eng = s.eng
    out = []
    for f in eng.fighters.values():
        down = f.name in eng.downed
        try:
            pinned_by, pinning = eng.pinned_by(f.name), eng.pinning(f.name)
        except Exception:
            pinned_by, pinning = [], []
        try:
            facing = eng.facing_of(f.name) if down else ""
        except Exception:
            facing = ""
        posture = ("OUT" if f.eliminated else "in the air" if eng.has(f, "airborne") else
                   f"pinned by {', '.join(pinned_by)}" if pinned_by else f"pinning {', '.join(pinning)}" if pinning else
                   f"down ({facing})" if down else "on her feet")
        sub_ = next((h for h in eng.holds.values() if h.sub and h.attacker == f.name), None)
        if posture == "on her feet" and sub_ is not None:
            # (since build 265) a fighter working a submission isn't standing free: on the ground with her in it,
            # or holding her up close in an upright one
            posture = (f"locked onto {sub_.defender} in her {sub_.sub}"
                       + (", down with her" if sub_.defender in eng.downed else ", holding her up"))
        out.append({
            "name": f.name, "species": species_of(f.description, f.appearance), "types": list(f.types or []),
            "health": round(float(f.health), 2), "max": float(f.max_health or 1), "energy": round(float(f.energy), 1),
            "status": {k: v for k, v in (f.status or {}).items()}, "out": bool(f.eliminated), "posture": posture,
            "body": _body.card(f),      # (since build 314: her air and how tired each limb is)
            "parts": [(p.name, round(float(p.damage), 2), round(float(p.resistance), 2)) for p in f.parts.values()],
            # for the pictures: which way she lies, and the marks on each hurt part (window.poses, window.damage_marks)
            "facing": facing, "marks": _marks_of(eng, f),
            # (since build 306) her resting heart rate, for the heart monitor on her card (window.alive)
            "heart_rest": float(getattr(f, "heart_rest", 0) or 0) or None,
            # a submission match: her tap-outs so far and how many end it (the window's tap tally)
            "taps": ({"given": list(eng.taps_given(f)), "needed": int(eng.taps_needed())}
                     if eng.submission_match() else None),
            # how much pain she is in against what she can bear (window.pain_gauge): the window's pain gauge
            "pain": eng.pain_gauge(f) if hasattr(eng, "pain_gauge") else None,
            # the grips on her and by her, a pin, how near she is to tapping, how far from the others
            # (window.hold_panel): the window's hold panel and tap meter
            "grips": eng.card_state(f) if hasattr(eng, "card_state") else None,
        })
    return {"turn": int(getattr(eng, "turn", 0) or 0), "fighters": out,
            "label": label or f"after beat {getattr(eng, 'turn', 0)}"}


class Session:
    def __init__(self, args):
        self.args = args
        pick = [x for x in re.split(r"[,\s]+", getattr(args, "fighters", "") or "") if x]
        self.eng = Engine(seed=args.seed, only=pick or None)
        self.fight_no = 1           # fights played in this session, counting the current one
        self.results = []           # one entry per finished fight: who, winner, how long
        self.story_before = []      # the prose of earlier fights this session (for /export prose)
        self.use_llm = not args.no_llm
        # one model for both by default; --director-model / --narrator-model split them
        saved = self.eng.rules.get("models") or {}   # what /model last chose (kept in my_settings.json)
        self.director = Director(getattr(args, "director_model", None) or saved.get("director") or args.model,
                                 host=args.host)
        self.narrator = Narrator(getattr(args, "narrator_model", None) or saved.get("narrator") or args.model,
                                 self.eng.rules, host=args.host)
        self.narrator.progress = self.progress
        self.story = []
        self.over = False
        self.display = Display(self.eng.rules)
        self.show_math = not args.hide_math
        self.math_mode = "auto"  # auto: full blocks for attacks, compact lines for pin/hold beats
        self.attacks = 0
        self.recent_attacks = []  # for the director's variety check
        self.transcript = []      # everything shown, for /export
        self.beat_records = []    # every beat: its text and how each fighter stood after it (/exportfight)
        self._export_paths = {}   # fight number -> where that fight was exported (re-written as it goes on)
        self.timings = []         # one row per beat: seconds, model calls, what was written again
        self.history = []         # snapshots for /undo
        self.last_narration = None  # what the last beat's prose was written from, for /reroll
        self.pending = None         # a beat whose narration failed, waiting for /reroll
        self.autosave_enabled = not getattr(args, "no_autosave", False)
        self.players = []           # fighters you play yourself (/play); the director runs the rest
        self._play_rot = 0          # with several played fighters, who is asked first turns over each beat

    # ---------- output ----------
    def out(self, text=""):
        print(text)
        self.transcript.append(text)

    @staticmethod
    def progress(msg):
        print(f"  [{msg}]", flush=True)
        # what the narrator had to do again this beat, for the "this beat took..." line
        m = re.search(r"writing (\d+) paragraphs? again", msg)
        if m:
            BEAT_TALLY["paragraphs"] += int(m.group(1))
        elif "writing a second draft" in msg:
            BEAT_TALLY["second drafts"] += 1
        elif "writing it again" in msg or "one more rewrite" in msg or "rewriting to fix" in msg:
            BEAT_TALLY["whole parts"] += 1
        elif "writing more" in msg:
            BEAT_TALLY["top-ups"] += 1

    def play_beat(self, direction="", manual=None, orders=None):
        """One beat, and then how long it took and what had to be written again (console -> timing, /timing)."""
        before, t0 = dict(llm.stats), time.time()
        BEAT_TALLY.clear()
        try:
            del narrator_mod.CALL_LOG[:]     # (a beat stopped before its narration must not show the last one's steps)
        except Exception:
            pass
        if not any(r.get("fight") == self.fight_no for r in self.beat_records):
            # (since build 301) the fight as it stood before anything happened, kept first, so the window's beat
            # history (and an exported fight) can go back to before the first blow
            self._record_beat(len(self.transcript), label="the start")
        tlen = len(self.transcript)
        try:
            return self._play_beat(direction, manual, orders)
        finally:
            last = self.beat_records[-1] if self.beat_records else None
            self._record_beat(tlen)
            if self.beat_records and self.beat_records[-1] is not last:
                # the beat's own autosave ran before its record was kept: save again, or loading that save loses it
                self.autosave()
            d = {k: llm.stats[k] - before.get(k, 0) for k in llm.stats}
            if d["calls"] > 0:
                row = {"seconds": time.time() - t0, "narrator": self.narrator.model, "director": self.director.model,
                       **d, **{k: BEAT_TALLY.get(k, 0) for k in ("paragraphs", "whole parts", "second drafts", "top-ups")}}
                if self.eng.rules.get("narration", {}).get("show_timing", True) and hasattr(self.narrator, "beat_timing"):
                    row["where"] = self.narrator.beat_timing()
                self.timings.append(row)
                if self.eng.rules.get("console", {}).get("timing", True):
                    print(timing_line(row))
                    self._speed_check()

    def _speed_check(self):
        """console.speed_check (since build 286): when part of the narrator model is running in system memory
        instead of on the graphics card, say so once (and again if it gets worse), with what to do about it. That
        alone can make a beat several times slower, without anything being written differently."""
        cfg = (self.eng.rules.get("console") or {}).get("speed_check") or {}
        if not cfg.get("enabled", True):
            return
        try:
            got = llm.loaded(self.narrator.host, self.narrator.model)
        except Exception as e:
            note_failure("asking Ollama where the model is loaded", e)
            return
        if not got or not got[0]:
            return
        size, vram = got
        off = 1.0 - vram / size
        if off < float(cfg.get("warn_from", 0.05)) or off <= getattr(self, "_offload_said", 0.0) + 0.05:
            return
        self._offload_said = off
        ctx = int((self.eng.rules.get("narration") or {}).get("context_window", 8192))
        print(f"⚠️ Speed: {off:.0%} of {self.narrator.model} ({size / 2**30:.1f} GB in all) is running in system "
              f"memory, not on the graphics card: that part works many times slower, and it is likely most of why "
              f"beats take so long. Nothing about the writing needs to change to fix it. What helps, from the most to "
              f"the least: (1) close other programs using the graphics card (a browser with video, games, ComfyUI); "
              f"(2) let Ollama keep its working memory smaller: set the Windows environment variables "
              f"OLLAMA_FLASH_ATTENTION=1 and OLLAMA_KV_CACHE_TYPE=q8_0, then quit Ollama from the tray and start it "
              f"again; (3) a slightly smaller download of the same model (a q4_K_S or IQ4_XS version). The notes "
              f"need a context of {ctx} tokens. (`ollama ps` shows the split; /set console.speed_check.enabled false "
              f"turns this off.)")

    def _record_beat(self, tlen, label=None):
        """Keep this beat for /exportfight: what was shown, and every fighter as she stands now. A finished fight
        is exported by itself (rules export.auto), and again after each aftermath beat."""
        text = "\n".join(self.transcript[tlen:])
        if not text.strip() and label is None:
            return
        self.beat_records.append({"fight": self.fight_no, "lineup": self.lineup(), "turn": int(self.eng.turn or 0),
                                  "label": label or f"beat {self.eng.turn}", "text": text,
                                  "snapshot": fight_snapshot(self, "at the start" if label == "the start" else None)})
        self.beat_records = self.beat_records[-1500:]
        if self.over and (self.eng.rules.get("export") or {}).get("auto", True):
            try:
                import fightexport
                path = fightexport.write(self, self._export_paths.get(self.fight_no), fights=[self.fight_no])
                if self.fight_no not in self._export_paths:
                    print(f"(The whole fight, with every beat's pictures and stats, was saved to {path}; it is "
                          f"updated as the aftermath goes on. /exportfight saves it again anywhere you like.)")
                self._export_paths[self.fight_no] = path
            except Exception as e:
                print(f"[the fight could not be exported: {e}]")

    # ---------- playing as fighters (/play) ----------
    def play_order(self):
        """The fighters you play who are still in the fight, the first one asked turning over each beat."""
        names = [f.name for f in self.eng.active() if f.name in self.players]
        if len(names) > 1:
            k = self._play_rot % len(names)
            names = names[k:] + names[:k]
        return names

    DICE_MODES = {"fair": "the dice decide what happens; your /commands can still force any outcome",
                  "strict": "you are at the mercy of the dice: pins, submissions, getting up and escapes only when the "
                            "dice allow, and no command forces an outcome",
                  "free": "the dice are off for the fighters you play: their attacks always land, openings are always "
                          "there, they get up at the first try and break any pin or hold they try to"}

    def dice_mode(self):
        m = str((self.eng.rules.get("play") or {}).get("dice", "fair")).lower()
        return m if m in self.DICE_MODES else "fair"

    def sync_dice(self):
        """Tell the engine how the dice treat the fighters you play (/play dice)."""
        on = self.play_order() if self.players else []
        mode = self.dice_mode() if on else "fair"
        self.eng.lucky = set(on) if mode == "free" else set()
        self.eng.dice_mode = mode

    def strict(self):
        return bool(self.players) and self.dice_mode() == "strict" and not self.over

    def playing(self):
        # (with the models and an opening passage, the first Enter writes that passage before you are asked)
        intro = self.use_llm and self.eng.rules.get("narration", {}).get("scene_intro", True)
        return bool(self.play_order()) and not self.over and not self.pending and bool(self.story or not intro)

    def play_panel(self, name, first=False):
        """What your fighter has to work with before you choose: her state, her moves, and this beat's openings."""
        e = self.eng
        self.sync_dice()
        if first and not getattr(e, "_windows_ready", False):
            # the openings are rolled now (once for the whole beat, however many times you're asked), so you can
            # see them before you choose
            e.rolls = []
            e.roll_pin_windows(open_all=False)
            cfg = e.rules.get("play", {})
            if cfg.get("free_pins", False):
                for o in e.active():
                    if o.name not in self.players and not e.pinned_by(o.name):
                        e.pin_window[o.name] = True
            e._pre_rolls, e._windows_ready = list(e.rolls), True
        f = e.get(name)
        foes = [o for o in e.active() if o is not f and not (f.team and o.team == f.team)]
        moves = [m["name"] + (f" ({f.move_uses[m['name']]} left)" if m["name"] in f.move_uses else "")
                 + (" (hold: for pins and grips)" if m.get("target") == "hold" else "")
                 + (" (too tired)" if e.energy_cost(m) > f.energy else "")
                 for m in f.moves if f.move_uses.get(m["name"], 1) > 0]
        pinner = e.pinned_by(name)
        state = e.posture_text(name, short=True)
        lines = [f"🎮 {name} — {e.strength(f):.0f}% strength · energy {f.energy:.0f} · {state}"
                 + ("" if self.dice_mode() == "fair" else f" · dice: {self.dice_mode()}")]
        conds = [f"{k.replace('_', ' ')} ({v} beat{'s' if v != 1 else ''})" for k, v in f.status.items() if v > 0]
        if conds:
            lines.append("   condition: " + ", ".join(conds))
        stop = next((w for k, w in (("asleep", "ASLEEP"), ("frozen", "FROZEN SOLID"), ("flinched", "FLINCHED"))
                     if e.has(f, k)), None)
        if stop:
            lines.append(f"   {stop}: she can't act this beat. Press Enter or type wait (or a /command)")
        if pinner:
            lines.append(f"   PINNED: you can struggle to break free, or strike at the one on top of you")
        held = [h for h in e.holds.values() if h.defender == name]
        holding = [h for h in e.holds.values() if h.attacker == name]
        if held:
            lines.append("   held: " + "; ".join(f"{h.attacker} has your {h.part}" for h in held)
                         + "".join(f" (a SUBMISSION: {h.sub.replace('_', ' ')})" for h in held[:1] if h.sub))
        if holding:
            lines.append("   holding: " + "; ".join(f"your grip on {poss_name(h.defender)} {h.part}" for h in holding))
        lines.append("   moves: " + ", ".join(moves))
        ops = []
        for o in ([] if pinner or e.pinning(name) else foes):   # pinned, or already pinning: no new pin to open
            pin, why = e.pin_allowed(o.name)
            sub = (getattr(e, "sub_window", None) or {}).get(o.name)
            wait = "she has to take a blow since the last pin attempt" if "attacks needed" in why else ""
            ops.append(f"{o.name} ({e.strength(o):.0f}%): pin {'OPEN' if pin else ('not yet: ' + wait) if wait else 'no'}"
                       + (", submission OPEN" if sub else ""))
        if ops:
            lines.append("   openings: " + " · ".join(ops))
        elif e.pinning(name):
            lines.append("   you're pinning her: hold her down, strike at what you can reach, or let her go")
        lines.append("   (type her move · Enter: the director chooses for her · wait: she holds back · "
                     "/command: direct control)")
        print("\n".join(lines))

    @staticmethod
    def _order(text):
        t = text.strip()
        if not t:
            return None
        if t.lower() in ("wait", "-", "pass", "hold back", "nothing", "skip"):
            return "WAIT"
        return t

    def play_turn(self, first, line, read=None):
        """Your move for the first fighter you play is `line`; ask for the others, then play the beat."""
        names = self.play_order()
        orders = {first: self._order(line)}
        for name in names[1:]:
            self.play_panel(name)
            try:
                more = (read or input)(f"{name} > ").strip()   # (looked up now: the window routes input)
            except (EOFError, KeyboardInterrupt):
                print("(beat cancelled)")
                self.eng._windows_ready = False
                return
            if more.startswith("/"):
                # direct control instead: the command runs as it would anywhere else, and this beat's asks are dropped
                self.eng._windows_ready = False
                return handle_command(self, more)
            orders[name] = self._order(more)
        self._play_rot += 1
        self.play_beat(orders=orders)

    # ---------- undo / reroll / save ----------
    def _snapshot(self):
        return (self.eng.snapshot_state(), list(self.story), self.attacks, list(self.recent_attacks), self.over,
                len(self.transcript), self.last_narration, self.pending, len(self.beat_records))

    def push_history(self):
        self.history.append(self._snapshot())
        self.history = self.history[-30:]

    def undo(self):
        if not self.history:
            raise ValueError("nothing to undo")
        (eng, story, attacks, recent, over, tlen, last, pending, *more) = self.history.pop()
        if more:
            self.beat_records = self.beat_records[:more[0]]
        self.eng.restore_state(eng)
        self.story, self.attacks, self.recent_attacks, self.over = story, attacks, recent, over
        self.transcript = self.transcript[:tlen]
        self.last_narration, self.pending = last, pending
        if not self.over:  # undone back into the fight: its result isn't in yet
            self.results = [r for r in self.results if r["fight"] != self.fight_no]
        self.autosave()

    def more(self, words=None, direction=""):
        """Stay with the moment: the narrator adds paragraphs about what the last beat left behind. Nothing happens
        in the fight and no time passes; the text joins the last beat's story (and /undo takes it away)."""
        if not self.use_llm:
            raise ValueError("the narrator is off (--no-llm)")
        if not self.story:
            raise ValueError("nothing has happened yet: press Enter to begin")
        if self.pending:
            print("[The last beat still has no narration. /reroll to write it, or /undo to take it back.]")
            return
        self.push_history()
        self._rising = set()
        self._start_down = set(self.eng.downed) | {p["defender"] for p in self.eng.pins.values()}
        self._posture_start = {f.name: self.eng.posture_text(f.name, short=True) for f in self.eng.active()}
        self.sync_narrator()
        try:
            text = self.narrator.more(self.eng.narrator_condition(), self.notes(), self.eng.scene, self.recent_story(),
                                      words, direction)
        except Exception:
            self.history.pop()
            raise
        if not (text or "").strip():
            self.history.pop()
            print("(The narrator had nothing new to add here.)")
            return
        self.story[-1] = self.story[-1].rstrip() + "\n\n" + text
        self.out("\n" + text + "\n")
        self.autosave()

    def _interlude_due(self):
        """Should a long interlude follow this beat? narration.interlude: chance per beat, never in the first
        from_beat beats, at least min_gap beats apart, never once the fight is decided. /interlude next forces one."""
        cfg = self.eng.rules.get("narration", {}).get("interlude") or {}
        if self.eng.winner() or self.over:
            return False
        if getattr(self, "interlude_next", False):
            self.interlude_next = False
            return True
        if not cfg.get("enabled", True):
            return False
        if cfg.get("not_in_holds", True) and (self.eng.pins or any(not h.grab for h in self.eng.holds.values())):
            return False     # a hold or a pin is grinding on: the fight isn't drawing breath
        turn, last = self.eng.turn, getattr(self, "_last_interlude", -999)
        if turn < int(cfg.get("from_beat", 3)) or turn - last < int(cfg.get("min_gap", 4)):
            return False
        return random.random() < float(cfg.get("chance", 0.1))

    def interlude(self, words=None, direction="", auto=False):
        """A long passage where the fight draws breath (narration.interlude, /interlude): thoughts, the body taking
        stock, the place in detail. Nothing happens in the fight; the text joins the last beat's story."""
        if not self.use_llm:
            raise ValueError("the narrator is off (--no-llm)")
        if not self.story:
            raise ValueError("nothing has happened yet: press Enter to begin")
        if not auto:
            self.push_history()
        self._rising = set()
        self._start_down = set(self.eng.downed) | {p["defender"] for p in self.eng.pins.values()}
        self._posture_start = {f.name: self.eng.posture_text(f.name, short=True) for f in self.eng.active()}
        self.sync_narrator()
        try:
            text = self.narrator.interlude(self.eng.narrator_condition(), self.notes(full_reason=True), self.eng.scene,
                                           self.recent_story(), words, direction)
        except Exception:
            if not auto:
                self.history.pop()
            raise
        self._last_interlude = self.eng.turn
        if not (text or "").strip():
            if not auto:
                self.history.pop()
            return
        self.story[-1] = self.story[-1].rstrip() + "\n\n" + text
        self.out("\n~ ~ ~\n\n" + text + "\n")
        if not auto:
            self.autosave()

    def _save_cfg(self):
        return (self.eng.rules.get("save") or {}) if self.eng else {}

    def _history_json(self):
        """save.history (since build 301): the /undo history as save-file data, so a loaded fight can be undone back
        through its beats as before it was saved (the newest save.history_beats of them). Each beat is worked out
        once and kept (autosave writes every beat). What the narration was written from (for /reroll) stays out."""
        cfg = self._save_cfg()
        if not cfg.get("history", True):
            return []
        cache = self.__dict__.setdefault("_hist_cache", {})
        out, keep = [], set()
        for h in self.history[-int(cfg.get("history_beats", 30)):]:
            key = id(h)
            keep.add(key)
            if key not in cache:
                eng, story, attacks, recent, over, tlen, _last, _pending, *more = h
                try:
                    item = {"engine": self.eng.snapshot_to_json(eng), "story": list(story), "attacks": attacks,
                            "recent_attacks": list(recent), "over": over, "tlen": tlen,
                            "records": more[0] if more else None}
                    json.dumps(item)
                    cache[key] = (h, item)          # (the tuple kept too, so its id can't be reused)
                except (TypeError, ValueError) as e:
                    note_failure("writing a beat of the /undo history into the save", e)
                    out = []
                    continue
            out.append(cache[key][1])
        for key in [k for k in cache if k not in keep]:
            del cache[key]
        return out

    def _history_from(self, saved):
        """The other way, on /load: the saved /undo history back as it was."""
        out = []
        for item in saved or []:
            try:
                out.append((self.eng.snapshot_from_json(item["engine"]), list(item.get("story") or []),
                            item.get("attacks", 0), list(item.get("recent_attacks") or []), bool(item.get("over")),
                            int(item.get("tlen") or 0), None, None, item.get("records")))
            except (KeyError, TypeError, ValueError, IndexError) as e:
                note_failure("reading a beat of the /undo history from the save", e)
                return []
        return out

    def _extra(self):
        return {"story": self.story, "style": self.narrator.style, "over": self.over,
                "transcript": self.transcript[-4000:], "attacks": self.attacks,
                "recent_attacks": self.recent_attacks, "fight_no": self.fight_no, "results": self.results,
                "story_before": self.story_before[-400:], "reason": getattr(self, "reason", None),
                "reason_pick": getattr(self, "reason_pick", None), "reason_off": getattr(self, "reason_off", False),
                "beat_records": self.beat_records[-400:],
                "history": self._history_json(),
                "fight_keys": dict(getattr(self, "_fight_keys", None) or {}),
                "polish_history": [{k: v for k, v in e.items() if k not in ("rejected", "_nstate")}
                                   for e in (getattr(self, "_polish_hist", None) or [])]}

    # ---------- more than one fight ----------
    def lineup(self):
        return [f.name for f in self.eng.fighters.values()]

    def record_result(self, note=""):
        """Note how the current fight ended (once), for /results and the /autofight summary."""
        if any(r["fight"] == self.fight_no for r in self.results):
            return
        self.results.append({
            "fight": self.fight_no, "fighters": self.lineup(), "winner": self.eng.winner() or "", "beats": self.eng.turn,
            "attacks": self.attacks, "note": note,
            "strength": {f.name: round(self.eng.strength(f)) for f in self.eng.fighters.values()}})

    def results_text(self, last=None):
        rows = self.results[-last:] if last else self.results
        if not rows:
            return "No fight has finished yet this session."
        out = []
        for r in rows:
            left = ", ".join(f"{n} {v}%" for n, v in r["strength"].items())
            out.append(f"Fight {r['fight']}: {' vs '.join(r['fighters'])} — "
                       + (f"**{r['winner']} won**" if r["winner"] else f"no winner ({r['note'] or 'unfinished'})")
                       + f" after {r['beats']} beats, {r['attacks']} attacks (strength left: {left})")
        wins = {}
        for r in rows:
            if r["winner"]:
                wins[r["winner"]] = wins.get(r["winner"], 0) + 1
        if len(rows) > 1:
            out.append("Wins: " + (", ".join(f"{n} {c}" for n, c in sorted(wins.items(), key=lambda x: -x[1])) or "none")
                       + f"   (average length {sum(r['beats'] for r in rows) / len(rows):.0f} beats)")
        return "\n".join(out)

    def new_fight(self, names=None):
        """A fresh fight in the same session: everyone back to full health, a new story. names: who takes part
        (default: the same line-up). Rules, the story plan, /focus and the style note carry over."""
        if self.eng.turn and not self.over:
            self.record_result("stopped early")
        # nothing has happened yet (no beat, no opening scene, no result): this replaces fight 1, it isn't fight 2
        fresh_start = not self.eng.turn and not self.story and not self.over and not self.results
        old = self.eng
        self.reason = None      # a new fight, a new reason (unless /reason chose one)
        seed = None if self.args.seed is None else self.args.seed + self.fight_no
        eng = Engine(seed=seed, rules=old.rules, only=list(names) if names else self.lineup())
        eng.set_scene(old.scene if old.scene_name == "custom" else old.scene_name, fallback=old.scene)   # same arena
        plan = dict(old.plan)
        if plan.get("winner") and plan["winner"].lower() not in eng.fighters:
            plan.pop("winner", None)
            plan.pop("shape", None)  # the plan was about a fighter who isn't in this one
        eng.plan = plan
        if self.story:
            self.story_before += [f"## Fight {self.fight_no}: {' vs '.join(self.lineup())}"] + self.story
        self.eng = eng
        fresh = Narrator(self.narrator.model, eng.rules, host=self.narrator.host, style=self.narrator.style)
        fresh.progress = self.narrator.progress
        if hasattr(self.narrator, "_cpt"):
            fresh._cpt = self.narrator._cpt  # what it has learned about this model's prompt sizes
        self.narrator = fresh
        self.story, self.over, self.attacks, self.recent_attacks = [], False, 0, []
        self.history, self.last_narration, self.pending = [], None, None
        self._was_in, self._rising, self._start_down, self._posture_start = set(), set(), set(), {}
        self.fight_no += 0 if fresh_start else 1
        self.out("\n" + "═" * 60 + f"\n**Fight {self.fight_no}: {' vs '.join(self.lineup())}**\n" + "═" * 60)
        self.out(self.display.status_brief(self.eng))
        if len(self.eng.scenes) > 1:
            self.out(f"🏟️ Arena: {self.eng.scene_cfg.get('title', 'your own scene')} (/scene to change it, /hazards for what it does)")
        if variant_lines(self.eng):
            self.out(variant_lines(self.eng))
        self._record_beat(len(self.transcript), label="the start")
        if plan.get("shape") or plan.get("winner"):
            self.out(f"(Story plan carried over: {plan.get('shape') or 'winner'}"
                     + (f", {plan['winner']} to win" if plan.get("winner") else "") + ". /plan off clears it.)")
        self.autosave()

    def auto_fights(self, count, aftermath=2, names=None):
        """Run whole fights on the director's own choices, one after another, each followed by `aftermath` beats."""
        if not self.use_llm:
            raise ValueError("/autofight needs the models (it's the director who fights); you started with --no-llm")
        cap = int(self.eng.rules.get("director", {}).get("autofight_max_beats", 150))
        start = len(self.results)
        STOP.clear()
        for i in range(count):
            if STOP.is_set():
                break
            untouched = self.eng.turn == 0 and not self.over
            same = not names or [self.eng.match_roster(n) for n in names] == self.lineup()
            if not (i == 0 and untouched and same):
                self.new_fight(names)
            self.out(f"\n[autofight {i + 1} of {count}: {' vs '.join(self.lineup())}]")
            stalled = 0
            while not self.over and self.eng.turn < cap and stalled < 3:
                before = (self.eng.turn, len(self.story))
                self.play_beat()
                if self.pending:
                    raise ValueError("the narration failed, so the run stopped here. /reroll writes that beat; then "
                                     "/autofight again to carry on")
                stalled = stalled + 1 if (self.eng.turn, len(self.story)) == before else 0
                if STOP.is_set():
                    break
            if STOP.is_set():
                _stopped(self)
                break
            if not self.over:
                self.record_result(f"stopped after {self.eng.turn} beats" if self.eng.turn >= cap else "stalled")
                self.out(f"*** Fight {self.fight_no}: no winner after {self.eng.turn} beats "
                         f"(director.autofight_max_beats is {cap}) ***")
            for _ in range(max(0, aftermath)):
                if self.over:
                    self.play_beat()
            self.out("\n" + self.results_text(last=1))
        if count > 1:
            self.out("\n" + "═" * 60 + f"\n**{count} fights**\n" + self.results_text(last=len(self.results) - start))

    def autosave(self):
        if self.autosave_enabled:
            try:
                self.eng.save(AUTOSAVE, self._extra())
            except OSError as e:
                print(f"[autosave failed: {e}]")

    def load(self, path):
        extra = self.eng.load(path)
        self.story, self.over = extra.get("story", []), extra.get("over", False)
        self.narrator.fight_seen = set()
        self.narrator.remember(self.story)
        self.narrator.style = extra.get("style", "")
        self.transcript = extra.get("transcript", [])
        self.attacks = extra.get("attacks", 0)
        self.recent_attacks = extra.get("recent_attacks", [])
        self.fight_no = extra.get("fight_no", self.fight_no)
        self.results = extra.get("results", self.results)
        self.story_before = extra.get("story_before", self.story_before)
        self.reason, self.reason_pick = extra.get("reason"), extra.get("reason_pick")
        self.reason_off = extra.get("reason_off", False)
        self.beat_records = extra.get("beat_records", [])
        self._polish_hist = list(extra.get("polish_history") or [])
        self._fight_keys = dict(extra.get("fight_keys") or {})
        if self._polish_hist:
            self._polish_last = self._polish_hist[-1]
        self.last_narration, self.pending = None, None
        # (since build 301) the /undo history comes back too, so a loaded fight can be undone as before
        self.history = self._history_from(extra.get("history"))

    # ---------- the narration test bench (narration.bench; /bench) ----------
    BENCH_FILES = ("blocks_memory.json", "lines_memory.json", "phrase_memory.json", "check_counts.json")

    def _bench_cfg(self):
        return (self.eng.rules.get("narration") or {}).get("bench") or {}

    def _bench_save(self, args):
        """Keep this beat's narrator inputs (the notes and everything the narrator knows right now) in bench_cases/,
        so /bench can tell the same beat again under other settings. The last narration.bench.keep are kept."""
        cfg = self._bench_cfg()
        if not cfg.get("save", True):
            return
        import pickle
        try:
            folder = os.path.join(HERE, cfg.get("folder", "bench_cases"))
            os.makedirs(folder, exist_ok=True)
            state = {}
            for k, v in self.narrator.__dict__.items():
                if callable(v) or k in ("progress",):
                    continue
                try:
                    pickle.dumps(v)
                    state[k] = v
                except Exception:
                    continue        # (something that can't be kept: the bench runs without it)
            name = f"fight{self.fight_no}_beat{self.eng.turn:03d}_{time.strftime('%Y%m%d_%H%M%S')}.pkl"
            with open(os.path.join(folder, name), "wb") as fh:
                pickle.dump({"args": args, "state": state, "version": VERSION, "beat": self.eng.turn,
                             "fight": self.fight_no}, fh)
            old = sorted((f for f in os.listdir(folder) if f.endswith(".pkl")),
                         key=lambda f: os.path.getmtime(os.path.join(folder, f)))     # (by when, not by name)
            for f in old[:max(0, len(old) - int(cfg.get("keep", 30)))]:
                os.remove(os.path.join(folder, f))
        except Exception as e:
            note_failure("saving a beat for /bench", e)

    def _bench_run(self, case, overrides, seed):
        """Tell one saved beat again with the rules changed by `overrides` ([(path, value)]): (text, stats). The
        narrator, its memories (stock phrases, story blocks, check counts) and their files are put back after."""
        import copy as _copy, shutil, tempfile, pickle
        import narrator as narrator_mod
        keep_dict = {}
        for k, v in self.narrator.__dict__.items():
            if k == "rules":
                keep_dict[k] = v        # (shared with the game: a /set afterwards still reaches the narrator)
                continue
            try:
                keep_dict[k] = _copy.deepcopy(v)
            except Exception:
                keep_dict[k] = v
        tmp = tempfile.mkdtemp(prefix="bench_")
        saved = [f for f in self.BENCH_FILES if os.path.exists(os.path.join(HERE, f))]
        for f in saved:
            shutil.copy2(os.path.join(HERE, f), os.path.join(tmp, f))
        log = []
        rstate = random.getstate()
        try:
            self.narrator.__dict__.update(pickle.loads(pickle.dumps(case["state"])))
            # today's model and a phrase memory built from today's (and the override's) rules, not the saved ones
            for k in ("model", "host", "style"):
                if k in keep_dict:
                    self.narrator.__dict__[k] = keep_dict[k]
            self.narrator.__dict__.pop("_pm", None)
            rules = _copy.deepcopy(self.eng.rules)
            for path, value in overrides:
                node, key, _ = _rule_path(rules, path)
                node[key] = value
            self.narrator.rules = rules
            self.narrator.progress = log.append
            random.seed(seed)
            t0 = time.time()
            text = self.narrator.narrate(*case["args"]) or ""
            secs = time.time() - t0
            calls = len(narrator_mod.CALL_LOG)
        finally:
            random.setstate(rstate)
            self.narrator.__dict__.clear()
            self.narrator.__dict__.update(keep_dict)
            self.narrator.__dict__.pop("_pm", None)     # (rebuilt on next use, reading the live rules again)
            for f in self.BENCH_FILES:
                p = os.path.join(HERE, f)
                if f in saved:
                    shutil.copy2(os.path.join(tmp, f), p)
                elif os.path.exists(p):
                    os.remove(p)
            shutil.rmtree(tmp, True)
        prose = re.sub(r"(?m)^— [^\n]{1,40} —\s*$", "", text)
        words = re.findall(r"[A-Za-z']+", prose)
        grams = collections.Counter(" ".join(w.lower() for w in words[i:i + 5]) for i in range(len(words) - 4))
        checks = collections.Counter()
        for line in log:
            m = re.search(r"checking the draft: (.+)", str(line))
            if m:
                checks.update(x.strip() for x in m.group(1).split(","))
        stats = {"words": len(words), "paragraphs": len([p for p in prose.split("\n\n") if p.strip()]),
                 "calls": calls, "seconds": round(secs), "repeats": sum(1 for g, c in grams.items() if c > 1),
                 "rewrites": sum(1 for line in log if re.search(r"again|rewrite", str(line))), "checks": checks}
        return text, stats

    def bench(self, n, overrides):
        """/bench: the last n saved beats, each told twice (your settings as they are, then with the changes) and
        compared: words, paragraphs, model calls, time, rewrites, the checks that fired, repeated 5-word runs. Both
        tellings go to bench_reports/ side by side. Nothing in the fight changes."""
        import pickle
        cfg = self._bench_cfg()
        folder = os.path.join(HERE, cfg.get("folder", "bench_cases"))
        files = sorted((f for f in os.listdir(folder) if f.endswith(".pkl")),
                       key=lambda f: os.path.getmtime(os.path.join(folder, f))) if os.path.isdir(folder) else []
        if not files:
            print("No saved beats yet: play a beat or two first (narration.bench.save keeps them)."); return
        files = files[-n:]
        label_b = ", ".join(f"{p}={json.dumps(v, ensure_ascii=False)}" for p, v in overrides)
        print(f"Bench: {len(files)} beat(s), each told twice (A: your settings; B: {label_b}). That is "
              f"{2 * len(files)} whole narrations: it takes a while. Nothing in the fight changes.")
        rows, report = [], [f"# Bench {time.strftime('%Y-%m-%d %H:%M')}", "", f"- A: your settings as they are",
                            f"- B: {label_b}", f"- {VERSION.split(' (')[0]}", ""]
        for i, f in enumerate(files):
            try:
                with open(os.path.join(folder, f), "rb") as fh:
                    case = pickle.load(fh)
            except Exception as e:      # (a broken file, or one from a build whose classes have changed)
                note_failure(f"/bench reading {f}", e)
                print(f"  [{f}: can't be read, skipped]")
                continue
            seed = 1000 + i
            out = {}
            for side, ov in (("A", []), ("B", overrides)):
                print(f"  [{f}: telling it as {side}]")
                try:
                    out[side] = self._bench_run(case, ov, seed)
                except Exception as e:
                    note_failure(f"/bench on {f}", e)
                    out[side] = ("", {"words": 0, "paragraphs": 0, "calls": 0, "seconds": 0, "repeats": 0,
                                      "rewrites": 0, "checks": collections.Counter({"(failed)": 1})})
            rows.append((f, out))
            report += [f"## {f}", "", "| | words | paragraphs | calls | seconds | rewrites | repeats | checks |",
                       "|---|---|---|---|---|---|---|---|"]
            for side in ("A", "B"):
                st = out[side][1]
                report.append(f"| {side} | {st['words']} | {st['paragraphs']} | {st['calls']} | {st['seconds']} | "
                              f"{st['rewrites']} | {st['repeats']} | "
                              + (", ".join(f"{k} {v}" for k, v in st["checks"].most_common()) or "none") + " |")
            for side in ("A", "B"):
                report += ["", f"### {side}", "", out[side][0].strip(), ""]
        tot = {s: {k: sum(o[s][1][k] for _f, o in rows) for k in ("words", "paragraphs", "calls", "seconds",
                                                                 "rewrites", "repeats")} for s in ("A", "B")}
        lines = ["", "Totals      words  paragraphs  calls  seconds  rewrites  repeats"]
        for s in ("A", "B"):
            t = tot[s]
            lines.append(f"  {s}        {t['words']:>6}  {t['paragraphs']:>10}  {t['calls']:>5}  {t['seconds']:>7}  "
                         f"{t['rewrites']:>8}  {t['repeats']:>7}")
        report[6:6] = ["```"] + lines[1:] + ["```", ""]
        rep_dir = os.path.join(HERE, cfg.get("reports", "bench_reports"))
        path = os.path.join(rep_dir, f"bench_{time.strftime('%Y%m%d_%H%M%S')}.md")
        try:
            os.makedirs(rep_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(report))
        except OSError as e:
            note_failure("/bench writing its report", e)
            path = f"(not written: {e})"
        print("\n".join(lines) + f"\n(repeats: 5-word runs used twice in one beat; rewrites: fixes the checks asked for)"
              f"\nBoth tellings of every beat, side by side: {path}")

    def _write_prose(self, args):
        """Run the narrator. On a model failure the beat's stats still stand; /reroll can narrate it later."""
        try:
            text = self.narrator.narrate(*args)
            if text is not None and not text.strip():
                # (since build 265) say so, never a silent blank beat; /reroll writes it again
                self.out("\n[the narration came back empty for this beat. Type /reroll to write it again.]\n")
            return text
        except llm.LLMError as e:
            self.pending = {"args": args}
            self.out(f"\n[narration failed: {e}]\n[The stats below are already applied. Type /reroll to narrate "
                     f"this beat, or /undo to take the whole beat back.]\n")
            return None

    # ---------- narration.polish (since build 268): a stronger online model improves the prose ----------
    def polish_facts(self, results, also, headers):
        """What really happened this beat, in short plain lines, for the polishing model: the attacks, the holds,
        the taps, the get-ups and falls, and where each fighter ends up."""
        facts = []
        pc = (self.eng.rules.get("narration") or {}).get("polish") or {}
        if pc.get("setting", True):
            # (since build 269) who they are and where: her body as the game knows it (so nothing she lacks turns up
            # on her), and the arena
            for f in self.eng.fighters.values():
                if not f.eliminated:
                    look = re.sub(r"\s+", " ", str(f.appearance or f.description or "")).strip()
                    cut = int(pc.get("look_chars", 800))
                    if len(look) > cut:
                        look = look[:cut].rsplit(". ", 1)[0] + "."     # (whole sentences only)
                    facts.append(f"WHO: {f.name}: {look}")
                    ch_ = self.character_note(f, short=True) if pc.get("character", True) else ""
                    if ch_:
                        # (since build 281) who she is, so the editor can give her prose her own personality
                        facts.append(f"CHARACTER: {f.name}: {ch_}")
            sc = getattr(self.eng, "scene_cfg", None) or {}
            if sc.get("text"):
                place = re.sub(r"\s+", " ", str(sc["text"])).strip()
                if len(place) > int(pc.get("place_chars", 400)):
                    place = place[:int(pc.get("place_chars", 400))].rsplit(". ", 1)[0] + "."
                facts.append(f"WHERE: {sc.get('title') or 'the arena'}: {place}")
        facts += [re.sub(r"\s+", " ", re.sub(r"[*_`]", "", h)).strip() for h in headers or [] if str(h).strip()]
        for r in results or []:
            t = r.get("type")
            mv = r.get("move") if isinstance(r.get("move"), dict) else {}
            if t == "instant" and mv.get("about") and mv.get("name"):
                facts.append(f"{mv['name']} is {mv['about']}")
            aim = r.get("aim") if isinstance(r.get("aim"), dict) else {}
            if aim.get("aimed") and aim.get("landed") and aim["aimed"] != aim["landed"]:
                facts.append(f"{r.get('attacker')} aimed at {poss_word(r.get('defender') or '')} "
                             f"{str(aim['aimed']).lower()}, and it landed off target on her "
                             f"{str(aim['landed']).lower()}")
            if t == "hold_start" and r.get("attacker"):
                parts = [str(x.get("part")) for x in r.get("parts") or [] if isinstance(x, dict) and x.get("part")]
                what = r.get("submission") or "a hold"
                facts.append(f"{r['attacker']} puts {what} on {poss_word(r.get('defender') or '')} "
                             f"{', '.join(p.lower() for p in parts) or 'body'}")
            elif t == "grapple_start" and r.get("attacker"):
                facts.append(f"{r['attacker']} grabs {poss_word(r.get('defender') or '')} "
                             f"{str(r.get('part') or 'body').lower()}" + (f" with {r['with']}" if r.get("with") else "")
                             + (" (a grip she already had, kept on)" if r.get("existing") else ""))
            elif t == "breather" and r.get("attacker"):
                facts.append(f"{r['attacker']} takes a breather")
            elif t in ("throw", "slam", "drag", "pin_start", "pin_forced", "struggle", "pickup") and r.get("attacker"):
                facts.append(f"{r['attacker']}: {t.replace('_', ' ')}"
                             + (f" on {r['defender']}" if r.get("defender") and r.get("defender") != r["attacker"] else ""))
            if t == "instant" and r.get("dodged") and not r.get("hits"):
                facts.append(f"{r.get('defender')} DODGES {poss_word(r.get('attacker') or '')} "
                             f"{(mv or {}).get('name') or 'attack'}: it never touches her")
        for e in also or []:
            t, who = e.get("type"), e.get("fighter") or e.get("defender")
            if t in ("tap_out", "tap_count"):
                facts.append(f"{e.get('defender')} {'TAPS OUT' if e.get('how') == 'tap' else 'PASSES OUT'} in "
                             f"{poss_word(e.get('attacker') or '')} {e.get('submission') or 'hold'}"
                             + (" (the grip comes off; the match goes on)" if t == "tap_count" else ""))
            elif t == "tap_resist":
                facts.append(f"{e.get('defender')} refuses to tap in {poss_word(e.get('attacker') or '')} "
                             f"{e.get('submission') or 'hold'} (she does NOT tap this beat)")
            elif t == "constriction":
                facts.append(f"{poss_word(e.get('attacker') or '')} coils round {poss_word(who or '')} body hold back her "
                             f"blood (not her air): her heart " + {"pounding": "pounding with fear and effort",
                                                                     "slowing": "slowing and stumbling, her head swimming",
                                                                     "greying": "slow and uneven, the grey closing in, "
                                                                                "close to blacking out"}.get(
                                 e.get("stage"), "labouring") + " (she does NOT black out unless it says so)")
            elif t == "quirk_moment":
                facts.append(f"(her character, to show in how she does it, not a new event) {e.get('note')}")
            elif t == "tap_urge":
                facts.append(f"{e.get('defender')} fights the urge to tap (she does NOT tap this beat)")
            elif t == "get_up":
                facts.append(f"{who} " + (f"gets up (on try {e.get('tries')})" if e.get("stands") else
                                          "tries to get up and can't: she stays down"))
            elif t == "hold_end":
                facts.append(f"{poss_word(e.get('attacker') or '')} hold on {e.get('defender')} ends"
                             + (": she breaks free" if e.get("broke_free") else ""))
            elif t in ("collapse", "crumple") and (t == "collapse" or e.get("down")):
                facts.append(f"{who} goes down")
            elif t == "adrenaline":
                facts.append(f"{who} gets a surge of adrenaline" + (" (a second wind)" if e.get("second") else ""))
        for f in self.eng.fighters.values():
            if f.eliminated:
                facts.append(f"{f.name}: out of the fight")
            else:
                st = float(self.eng.strength(f) or 0)
                how = ("fresh, barely touched" if st >= 85 else "hurt, but still strong" if st >= 60 else
                       "worn down" if st >= 30 else "nearly spent")
                facts.append(f"{f.name} ends the beat: {self.eng.posture_text(f.name, short=True).lower()}; {how}")
        if (self.eng.rules.get("narration") or {}).get("polish", {}).get("condition", True):
            # (since build 269) how each one is by the end of the beat: her health, her pain overall, and her worst
            # parts in the story's own pain words (with the numbers), so the editor can size what she feels
            from engine import pain_tiers, tier_for
            tiers = pain_tiers(self.eng.rules)
            for f in self.eng.fighters.values():
                if f.eliminated:
                    continue
                g = (self.eng.pain_gauge(f) or {}).get("overall") or {}
                worst = sorted((p for p in f.parts.values() if p.damage >= 10), key=lambda p: -p.damage)[:4]
                parts = ", ".join(f"{p.name.lower()} {tier_for(p.damage, tiers)['label']} ({p.damage:.0f}%)"
                                  for p in worst) or "no part hurt yet"
                facts.append(f"{poss_word(f.name)} condition: health {self.eng._health_pct(f):.0f}% of full"
                             + (f"; pain overall {g.get('label')} ({g.get('shown') or str(g.get('pct')) + '%'} of what "
                                f"she can bear)" if g else "")
                             + f"; worst parts: {parts}")
        for f in self.eng.fighters.values():
            sts = [k.replace("_", " ") for k in (f.status or {}) if not f.eliminated]
            if sts:
                facts.append(f"{f.name} is {', '.join(sts)} at the end of the beat")
            if self.eng._taps_rule() and not f.eliminated:
                given = self.eng.taps_given(f)
                facts.append(f"{f.name} has tapped {len(given)} of {self.eng.taps_needed()} times"
                             + (f" (on her {', '.join(p.lower() for p in given)})" if given else ""))
        try:
            gap = self.eng.gap_text(card=True)
        except Exception as e:
            note_failure("the distance line for the polish facts", e)
            gap = ""
        if gap:
            facts.append(f"distance at the end: {gap}")
        for h in self.eng.holds.values():
            facts.append(f"still on at the end: {poss_word(h.attacker)} {h.sub or 'grip'} on {poss_word(h.defender)} "
                         f"{h.part.lower()}" + (f" ({h.with_part})" if h.with_part else ""))
        return list(dict.fromkeys(facts))

    def _maybe_polish(self, text, results, also, headers):
        """Polish this beat's prose if narration.polish is on (and, with when "big", only a big moment). Returns
        the text to show: the polished one if the checks keep it, else the local one as it was."""
        cfg = polish.cfg_of(self.eng.rules)
        facts = self.polish_facts(results, also, headers)
        self._polish_last = {"local": text, "facts": facts, "prior": self.recent_story()[-1500:], "polished": None,
                             "why": "", "turn": int(self.eng.turn or 0), "fight": self.fight_no,
                             "index": len(self.story)}     # (where this beat's story will sit)
        self._polish_last["shown"] = text
        # (since build 271) the beats kept for /polish copy 4 (several at once), saved with the game
        # (since build 272) what the narrator knew about THIS beat, so a polish of it pasted back later (/polish copy
        # 5-9) gets the same full sentence checks as the latest beat
        self._polish_last["_nstate"] = self._narrator_state()
        self._save_nstate(self._polish_last)
        hist = self.__dict__.setdefault("_polish_hist", [])
        hist.append(self._polish_last)
        keep_ = int(cfg.get("history", 0) or 0)      # (0: every beat, no limit)
        if keep_ > 0:
            del hist[:-keep_]
        if not cfg.get("enabled"):
            return text
        if str(cfg.get("when", "every")).lower() == "big" and not getattr(self.narrator, "_important", False) \
                and not any(e.get("type") in ("tap_out", "tap_count") for e in also or []):
            return text
        out = self._polish_now(text) or text
        self._polish_last["shown"] = out
        return out

    _NSTATE_SKIP = {"_block_store", "_line_store", "_passage_store", "_sample_keys", "rules", "_pm", "_deferred",
                    "scene_cfg", "progress", "model", "host", "style", "check_tally", "_check_new",
                    # (the cleanup's own memory of every note's wording, which only grows: the checks don't read it)
                    "_beat_note_grams", "_beat_notes_low"}

    def _narrator_state(self):
        """A copy of what the narrator holds about the beat it just wrote (its facts, grips, hits, who rose, the
        tap...), without its big shared libraries: enough to run its sentence checks on this beat later. Kept in
        memory only."""
        import copy
        out = {}
        for k, v in self.narrator.__dict__.items():
            if k in self._NSTATE_SKIP or callable(v):
                continue
            try:
                out[k] = copy.deepcopy(v)
            except Exception:
                continue      # (something that can't be copied: the checks don't read it)
        return out

    # (since build 273) those copies on disk too, for the last keep_fights fights (polish_states/, one small
    # compressed file a beat), so a polish pasted back after the game was closed still gets every check
    STATE_DIR = os.path.join(HERE, "polish_states")

    def _fight_key(self):
        keys = self.__dict__.setdefault("_fight_keys", {})
        k = str(self.fight_no)
        if k not in keys:
            keys[k] = time.strftime("%Y%m%d-%H%M%S") + f"-fight{self.fight_no}"
        return keys[k]

    def _save_nstate(self, entry):
        cfg = polish.cfg_of(self.eng.rules)
        keep = int(cfg.get("keep_fights", 3) or 0)
        if keep <= 0 or not entry.get("_nstate"):
            return
        import gzip
        import pickle
        import shutil
        try:
            entry["fkey"] = self._fight_key()
            folder = os.path.join(self.STATE_DIR, entry["fkey"])
            os.makedirs(folder, exist_ok=True)
            data = {}
            for k_, v_ in entry["_nstate"].items():
                try:
                    pickle.dumps(v_)
                    data[k_] = v_
                except Exception:
                    continue      # (what can't be kept on disk: the checks don't need it)
            with gzip.open(os.path.join(folder, f"beat_{int(entry.get('turn') or 0)}.pkl.gz"), "wb",
                           compresslevel=6) as fh:
                pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
            # only the latest keep_fights fights are kept; older ones go, so the drive doesn't fill
            fights = sorted((d for d in os.listdir(self.STATE_DIR) if os.path.isdir(os.path.join(self.STATE_DIR, d))),
                            key=lambda d: os.path.getmtime(os.path.join(self.STATE_DIR, d)), reverse=True)
            for old in fights[keep:]:
                if old != entry["fkey"]:
                    shutil.rmtree(os.path.join(self.STATE_DIR, old), ignore_errors=True)
        except (OSError, pickle.PicklingError) as e:
            note_failure("saving a beat's polish checks (polish_states)", e)

    def _load_nstate(self, entry):
        """A beat's copy of what the narrator knew, read back from polish_states/ (None when it isn't there)."""
        if not entry.get("fkey"):
            return None
        import gzip
        import pickle
        path = os.path.join(self.STATE_DIR, entry["fkey"], f"beat_{int(entry.get('turn') or 0)}.pkl.gz")
        try:
            with gzip.open(path, "rb") as fh:
                return pickle.load(fh)
        except FileNotFoundError:
            return None
        except (OSError, EOFError, pickle.UnpicklingError, AttributeError, ImportError) as e:
            note_failure("reading a beat's polish checks back (polish_states)", e)
            return None

    def _judge_as_then(self, entry, fn):
        """Run fn() with the narrator put back to how it was on that beat (entry["_nstate"]), then as it is now."""
        snap = entry.get("_nstate") if entry else None
        if not snap:
            return fn()
        N = self.narrator
        missing = object()
        before = {k: N.__dict__.get(k, missing) for k in snap}
        N.__dict__.update(snap)
        try:
            return fn()
        finally:
            for k, v in before.items():
                if v is missing:
                    N.__dict__.pop(k, None)
                else:
                    N.__dict__[k] = v

    def _polish_now(self, text, reply=None, entry=None):
        """Send this beat to the online model (or take a reply pasted in by hand) and judge it. Returns the
        polished text when it is kept, else None (and says why). entry: an earlier beat (/polish copy 4): judged
        without the narrator's sentence checks, which know only the last beat."""
        last = entry if entry is not None else (getattr(self, "_polish_last", None) or {})
        latest = last is getattr(self, "_polish_last", None) and bool(last.get("_nstate"))
        if not last.get("_nstate"):
            last["_nstate"] = self._load_nstate(last)      # (a beat from before the game was closed)
        try:
            if reply is None:
                self.progress("polishing the prose with " + (polish.cfg_of(self.eng.rules).get("model") or "?"))
                reply = polish.call(self.eng.rules, polish.messages(text, last.get("facts") or [], last.get("prior"),
                                                                     self.eng.rules))
        except polish.PolishError as e:
            note_failure("polishing the beat (narration.polish)", e)
            print(f"[polish not used: {e}]")
            last["why"] = str(e)
            return None
        names = [f.name for f in self.eng.fighters.values()]
        out = polish.tidy(reply, names, text)
        full = latest or bool(last.get("_nstate"))     # (an earlier beat: checked as the narrator saw it then)

        def check():
            k_, w_ = polish.judge(self.narrator if full else None, text, out, names, self.eng.rules,
                                  last.get("facts") or ())
            o_ = out
            if k_:
                try:
                    o_ = self.narrator._mend_move_names(out)
                except Exception as e:
                    note_failure("the move-name mend on the polished beat", e)
            return k_, w_, o_
        keep, why, out = check() if latest else self._judge_as_then(last, check)
        if not full:
            print(f"[beat {last.get('turn')}: its full checks weren't kept (an older fight than the last "
                  f"{polish.cfg_of(self.eng.rules).get('keep_fights', 3)}, or played before build 273), so only its "
                  f"labels, fighters, length and hit parts can be checked]")
        last.update(polished=out, why="" if keep else why, rejected=None if keep else out)
        at = "" if latest else f" (beat {last.get('turn')})"
        print(f"[polished{at}: kept the improved version]" if keep else
              f"[polish not used{at}: {why}. The beat stays as the local model wrote it; /compare shows both]")
        return out if keep else None

    def _replace_last_beat(self, new, entry=None):
        """Put a polished version in place of a beat's story everywhere it is kept: the story the models
        remember, and the beat's record (/exportfight, the saved fight). entry: an earlier beat; else the last."""
        last = entry if entry is not None else (getattr(self, "_polish_last", None) or {})
        old = last.get("shown") or last.get("local") or ""
        i = last.get("index")
        if isinstance(i, int) and 0 <= i < len(self.story) and self.story[i] == old:
            self.story[i] = new
        elif old in self.story:
            self.story[len(self.story) - 1 - self.story[::-1].index(old)] = new
        elif entry is None and self.last_narration and self.last_narration.get("index", -1) < len(self.story):
            self.story[self.last_narration["index"]] = new
        for r in reversed(self.beat_records):
            if old and old in r.get("text", ""):
                r["text"] = r["text"].replace(old, new, 1)
                break
        last["shown"] = new
        self.autosave()

    def sync_narrator(self):
        """Tell the narrator how hurt every body part is, so it can catch 'useless' on a part that's only sore."""
        dmg = {}
        for f in self.eng.fighters.values():
            for part in f.parts.values():
                k = part.name.lower()
                dmg[k] = max(dmg.get(k, 0), part.damage)
        self.narrator.part_damage = dmg
        self.narrator.damage_by = {f.name: {part.name.lower(): part.damage for part in f.parts.values()}
                                   for f in self.eng.active()}
        self.narrator.strengths = {f.name: self.eng.strength(f) for f in self.eng.active()}
        try:
            self.narrator.game_plans = {f.name: dict(pl) for f in self.eng.active() for pl in [self.eng.game_plan(f.name)]
                                        if pl}
        except Exception as exc:    # (a plan is only a story aid: the beat goes on without it)
            note_failure("working out the fighters' game plans", exc)
            self.narrator.game_plans = {}
        # parts gone NUMB for now (numbness): the story may show them dull, and must not give them fresh agony
        self.narrator.numb_parts = {(f.name, part.name.lower()) for f in self.eng.fighters.values()
                                    for part in f.parts.values() if int(getattr(part, "numb", 0) or 0) > 0}
        sc = getattr(self.eng, "scene_cfg", None) or {}
        self.narrator.scene_words = " ".join([str(sc.get("text") or ""), str(sc.get("ambience") or ""),
                                              str(sc.get("acoustics") or "")] + [str(x) for x in sc.get("details") or []])
        self.narrator.max_health = {f.name: f.max_health for f in self.eng.fighters.values()}
        self.narrator.fighter_types = {f.name: [str(t).lower() for t in (f.types or [])] for f in self.eng.fighters.values()}
        self.narrator.on_ground = set(self.eng.downed) | {pin["defender"] for pin in self.eng.pins.values()}
        self.narrator.on_ground |= set(getattr(self, "_rising", set()))
        # anyone who was down when the beat began (then got up, was hauled up, or broke free) may be shown lying too
        self.narrator.on_ground |= set(getattr(self, "_start_down", set()))
        self.narrator.facing = {f.name: self.eng.facing_of(f.name) for f in self.eng.fighters.values()
                                if self.eng.facing_of(f.name)}
        self.narrator.aliases = {self.eng.species(f): f.name for f in self.eng.fighters.values() if self.eng.species(f)}
        self.narrator.species_of = {f.name: self.eng.species(f) for f in self.eng.fighters.values() if self.eng.species(f)}
        self.narrator.plans = {f.name: self.eng.body_plan(f) for f in self.eng.fighters.values()}   # (serpent, biped...)
        # (since build 281, narration.character.history) who has fought before: her memories of it may stay
        import narrator as _nmod
        hist_on = self._character_cfg().get("history", True)
        _nmod.VETERANS.clear()
        _nmod.VETERANS.update(f.name for f in self.eng.fighters.values() if hist_on and getattr(f, "veteran", False))
        _nmod.IN_FIGHT.clear()
        _nmod.IN_FIGHT.update(f.name for f in self.eng.fighters.values() if not f.eliminated)
        self.narrator.inner = {f.name: self.eng.inner_state(f.name) for f in self.eng.active()}
        self._sync_absent()
        self.narrator.out_names = [f.name for f in self.eng.fighters.values() if f.eliminated]
        try:
            self.narrator.story_state = None if self.over else self.eng.story_state()
        except Exception as e:
            note_failure("the story state (how each fighter feels about the fight)", e)
            self.narrator.story_state = None
        self.narrator.silent_out = [] if self.over else [
            w for f in self.eng.fighters.values()
            if f.eliminated and f.name not in getattr(self, "_was_in", set()) and not self.eng.has_hurt_anyone(f.name)
            for w in (f.name, self.eng.species(f)) if w]
        self.narrator.posture_end = {f.name: self.eng.posture_text(f.name, short=True) for f in self.eng.active()}
        self.narrator.gap_card = self.eng.gap_text(card=True)   # how far apart they are, for the beat card
        self.narrator.scene_cfg = self.eng.scene_cfg   # the arena's own words (ground, place, ambience)
        self.narrator.broken_heads = self.eng._broken_heads()   # what has broken: nobody stands on it any more
        # who is in the water (None / "shallow" / "deep", from where the director placed her): nobody swims on land
        self.narrator.in_water = {f.name: self.eng.in_water(f.name) for f in self.eng.active()}
        self.narrator.pinned_now = {pin["defender"] for pin in self.eng.pins.values()} | {h.defender for h in self.eng.holds.values()}
        self.narrator.cant_act = {f.name for f in self.eng.active()
                                  if any(self.eng.has(f, st) for st in ("asleep", "frozen", "paralyzed"))}
        # which named moves have actually hurt whom (and where): a move is only remembered on a fighter it landed on
        names = {m["name"] for f in self.eng.fighters.values() for m in f.moves}
        hit, where = {}, {}
        for key, causes in self.eng.injury_log.items():
            who, _, part = key.partition("|")
            for c in causes:
                for mv in names:
                    if mv.lower() in str(c).lower():
                        hit.setdefault(mv, set()).add(who)
                        where.setdefault((mv, who), []).append(part.lower())
        self.narrator.move_victims, self.narrator.move_parts = hit, where
        # whose wounds are cold, fire or electricity (a hit of that type, or the status on her now), and which moves
        # each fighter has used: for narration.wrong_owner
        elem, kinds = {}, {"Ice": "cold", "Fire": "fire", "Electric": "electricity"}
        for key, causes in self.eng.injury_log.items():
            who = key.partition("|")[0]
            for c in causes:
                m = re.match(r"^.+?'s? (.+?)(?: \(.*\))?$", str(c or ""))
                t = ((self.eng.dex_move(m.group(1)) if m else None) or {}).get("type")
                if t in kinds:
                    elem.setdefault(who, set()).add(kinds[t])
        for f in self.eng.fighters.values():
            for st, kind in (("chilled", "cold"), ("frozen", "cold"), ("burned", "fire"), ("paralyzed", "electricity")):
                if self.eng.has(f, st):
                    elem.setdefault(f.name, set()).add(kind)
        self.narrator.elem_on = elem
        used = {}
        for x in self.recent_attacks:
            m = re.match(r"([^:→]+): (.+?)(?: \((?:improvised|a charge[^)]*)\))* → ", x)
            if m and m.group(2).strip() in names:
                used.setdefault(m.group(1).strip(), set()).add(m.group(2).strip())
        self.narrator.used_by = used
        self.narrator.known_moves = {f.name: [m["name"] for m in f.moves] for f in self.eng.fighters.values()}
        self.narrator.injury_log = {k: list(v) for k, v in self.eng.injury_log.items()}   # for one memory a beat
        # (the few causes the notes name for each part, the same as CURRENT CONDITION's: the hardest and the latest)
        self.narrator.injury_main = {k: self.eng.injury_causes(k) for k in self.eng.injury_log}
        # what kind of wound each part carries (claw, bite, blunt, grip, shock, cold): blood needs a claw or a bite
        self.narrator.wound_kinds = {k: {self.eng._mark_kind(c) for c in v if c} for k, v in self.eng.injury_log.items()}
        # (since build 308, moves.reactions) who is bleeding from a reaction (a nosebleed, a cut eye, bite wounds)
        self.narrator.bleeding = {f.name: [s for s in ("nosebleed", "blood_in_eye", "bite_wounds", "stinging_cuts",
                                                       "bleeding")
                                           if self.eng.has(f, s)] for f in self.eng.fighters.values()}
        self.narrator.bleeding = {k: v for k, v in self.narrator.bleeding.items() if v}
        self.narrator.first_hurt = {f.name: dict(f.learned.get("first_hurt") or {}) for f in self.eng.fighters.values()}
        self.narrator.beat_now = self.eng.turn      # (synced after the beat ran: this beat's number)
        self.narrator.voices = {f.name: getattr(f, "voice", "") for f in self.eng.fighters.values()}
        self.narrator.tally = dict(getattr(self.eng, "tally", {}) or {})   # for counts in the story ("thrown twice")
        # every grip that is still on now: the story may not let one go on its own
        self.narrator.grips = [(h.attacker, h.defender, h.part, h.with_part) for h in self.eng.holds.values()]
        # who has been down at all this fight (None: a save from before build 252, which didn't keep it)
        ed = self.eng.__dict__.get("ever_down")
        self.narrator.ever_down = (set(ed or ()) | set(self.eng.downed) if ed is not None or self.eng.turn <= 1 else None)
        # moves that have only ever been dodged in this fight: the story may not remember them as blows that landed
        dodged = {m.group(1).strip() for x in self.recent_attacks
                  for m in [re.match(r"[^:]+: (.+?)(?: \(improvised\))? → .* DODGED it", x)] if m}
        landed = {m.group(1).strip() for x in self.recent_attacks if "DODGED it" not in x
                  for m in [re.match(r"[^:]+: (.+?)(?: \((?:improvised|a charge[^)]*)\))* → ", x)] if m}
        self.narrator.missed_moves = sorted(dodged - landed)
        self.narrator.posture_start = dict(getattr(self, "_posture_start", {}))
        self.narrator.part_names = {p for f in self.eng.fighters.values() for p in f.parts}
        eyes = {}
        for f in self.eng.fighters.values():
            look = " ".join(str(getattr(f, k, "") or "") for k in ("description", "appearance", "tells"))
            m = re.search(r"\b(red|black|blue|green|gold(?:en)?|amber|yellow|brown|violet|purple|pink|white|grey|gray|"
                          r"silver|orange|dark)(?:\s[\w-]+){0,2}\s+eyes\b", look, re.I)
            if m:
                eyes[f.name] = m.group(1).lower()
        self.narrator.eye_colors = eyes
        # (since build 276) the colour of her fur, from her appearance ("Mostly WHITE fur"): "the dark fur" on a white
        # Absol is caught
        furs = {}
        for f in self.eng.fighters.values():
            m = re.search(r"\b(?:mostly |primarily )?([A-Z]{3,})(?:\s+[a-z]+)?\s+fur\b", str(f.appearance or ""))
            if m:
                furs[f.name] = m.group(1).lower()
        self.narrator.fur_colors = furs
        # what each of them is covered in, for the notes that say whether she is wet ("Glacia's feathers DRY")
        self.narrator.coats = {}
        for f in self.eng.fighters.values():
            look = " ".join(str(getattr(f, k, "") or "") for k in ("description", "appearance")).lower()
            self.narrator.coats[f.name] = next((w for rx, w in ((r"feather|plumage", "feathers"), (r"\bscal", "scales"),
                                                                 (r"\bfur\b|\bpelt\b|\bcoat\b(?! of)", "fur"),
                                                                 (r"\bskin\b|\bhide\b", "skin")) if re.search(rx, look)), "")
        self.narrator.body_colors = {f.name: set(re.findall(
            r"\b(red|black|blue|green|gold(?:en)?|amber|yellow|brown|violet|purple|pink|white|grey|gray|silver|orange|"
            r"cream|tan|crimson|scarlet|teal|navy)\b", " ".join(str(getattr(f, k, "") or "") for k in (
                "description", "appearance")).lower())) for f in self.eng.fighters.values()}
        soaked = {f.name for f in self.eng.fighters.values() if self.eng.has(f, "soaked")}
        if getattr(self.narrator, "_soak_fight", None) != (self.fight_no, id(self.eng)):
            self.narrator._soak_fight = (self.fight_no, id(self.eng))   # a new fight: everyone starts dry
            self.narrator.soaked_before, self.narrator._soaked_last = set(), set()
        if getattr(self.narrator, "_soak_turn", None) != self.eng.turn:
            self.narrator._soak_turn = self.eng.turn
            self.narrator.soaked_before = set(self.narrator.soaked_before) | set(self.narrator._soaked_last)
            self.narrator._soaked_last = soaked
        self.narrator.soaked_now = soaked
        # confused or dazed now: her world swims (no 'the world doesn't blur', no steady, unmoved ideas for her)
        self.narrator.dizzy = {f.name for f in self.eng.fighters.values()
                               if any(self.eng.has(f, st) for st in ("confused", "dazed"))}
        self.narrator.water_types = {f.name for f in self.eng.fighters.values()
                                     if "water" in {str(t).lower() for t in (getattr(f, "types", None) or [])}}
        self.narrator.rain_wet = (self.eng.scene_cfg.get("wets") or
                                  ("the rain" if (getattr(self.eng, "weather", None) or {}).get("kind") == "rain" else None))
        self.narrator.winners = ({f.name for f in self.eng.fighters.values() if not f.eliminated}
                                 if self.eng.winner() else set())   # (the fight is won: they stand, they don't fade)
        if getattr(self.narrator, "_part_names_seen", None) != len(self.narrator.part_names):
            self.narrator._part_words_cache = None   # new fighters: their part names are not repeated phrases
            self.narrator._part_names_seen = len(self.narrator.part_names)
        self.narrator.breakable = {x.lower() for f in self.eng.fighters.values() for x in self.eng.breakable_parts(f)}

    def reroll(self):
        self.sync_narrator()
        if self.pending:
            args = self.pending["args"]
            text = self.narrator.narrate(*args)
            self.pending = None
            self.story.append(text)
            self.last_narration = {"args": args, "index": len(self.story) - 1}
            self.out("\n" + text + "\n")
            self.autosave()
            return
        if not self.last_narration:
            raise ValueError("nothing to reroll yet")
        args, idx = self.last_narration["args"], self.last_narration["index"]
        text = self.narrator.narrate(*args)
        if idx < len(self.story):
            self.story[idx] = text
        self.out("\n(rerolled narration; the stats are unchanged)\n\n" + text + "\n")
        self.autosave()

    # ---------- story ----------
    # ---------- why they fight (fight_reasons.txt, /reason) ----------
    def fight_reason(self):
        """This fight's reason (filled in with the names), picked the first time it is needed: one that fits the
        arena, the holder and the comer chosen at random among the two sides. None when off or not a duel."""
        cfg = self.eng.rules.get("story", {}).get("reasons") or {}
        if not cfg.get("enabled", False) or getattr(self, "reason_off", False):
            return None
        sides = [f for f in self.eng.fighters.values()]
        if len(sides) != 2:
            return None
        names = [f.name for f in sides]
        r = getattr(self, "reason", None)
        if r and {r.get("holder_name"), r.get("comer_name")} == set(names):
            return r
        import reasons as R
        want = getattr(self, "reason_pick", None)
        if want and want.get("custom"):
            base = {"id": "custom", "title": "", "setup": want["custom"], "thoughts": []}
        else:
            rs = R.load(os.path.join(HERE, cfg.get("file", "fight_reasons.txt")))
            base = next((x for x in rs if want and x["id"] == want.get("id")), None) or R.pick(
                random, self.eng.scene_name or self.eng.scene_cfg.get("title", ""), rs,
                avoid=getattr(self, "reasons_used", []))
        if not base:
            return None
        holder = (want or {}).get("holder") if (want or {}).get("holder") in names else random.choice(names)
        comer = next(n for n in names if n != holder)
        place = self.eng.scene_cfg.get("place") or self.eng.scene_cfg.get("title") or "this place"
        self.reason = R.fill(base, holder, comer, place)
        self.reasons_used = (list(getattr(self, "reasons_used", [])) + [base["id"]])[-12:]
        return self.reason

    def reason_note(self, full=False):
        """The reason for the story: in full for the opening and interludes; short every beat (with now and then one
        thought either of them might have); and the ending once the fight is decided."""
        r = self.fight_reason()
        if not r:
            return ""
        h, c = r["holder_name"], r["comer_name"]
        if full:
            out = (f"WHY THEY ARE FIGHTING" + (f" ({r['title']})" if r.get("title") else "") + f": {r['setup']}"
                   + (f" {r['holder']}" if r.get("holder") else "") + (f" {r['comer']}" if r.get("comer") else "")
                   + (f" What is at stake: {r['stakes']}" if r.get("stakes") else ""))
        else:
            out = (f"WHY THEY ARE FIGHTING (background: let it show in what they want, how they fight and what they "
                   f"think, now and then, never retold in full): " + (f"{r['title']}. " if r.get("title") else "")
                   + (r.get("stakes") or r["setup"].split(". ")[0] + "."))
            cfg = self.eng.rules.get("story", {}).get("reasons") or {}
            if r.get("thoughts") and random.random() < float(cfg.get("thought_chance", 0.25)):
                out += (f" A THOUGHT one of them might have this beat (only if it fits the moment; in her own words, "
                        f"not copied): \"{random.choice(r['thoughts'])}\"")
        if self.over and r.get("end"):
            out += f" HOW IT ENDS (now the fight is decided, let the aftermath show it): {r['end']}"
        return out

    def notes(self, full_reason=False):
        multi_team = any(f.team != f.name for f in self.eng.fighters.values())
        lines = []
        for f in self.eng.fighters.values():
            if f.eliminated and not self.over and f.name not in getattr(self, "_was_in", set()):
                # out of the fight and out of the story until the aftermath (but not on the beat they go down)
                lines.append(f"{f.name} [OUT of the fight; not part of this story now]: "
                             + (f.appearance.split(".")[0] + "." if f.appearance else ""))
                continue
            lines.append(self._note(f, multi_team))
        why = self.reason_note(full_reason)
        if why:
            lines.append("\n" + why)
        return "\n".join(lines)

    def _character_cfg(self):
        c = (self.eng.rules.get("narration") or {}).get("character") or {}
        return c if c.get("enabled", True) else {"moments": False, "personality": False, "history": False,
                                                  "relationships": False}

    def character_note(self, f, short=False):
        """(since build 281, narration.character) who she is beyond her body: her personality, her history, and what
        she is to the others in this fight (fighters.json personality, history, relationships). short: one line each,
        for the polishing model."""
        c = self._character_cfg()
        others = [o.name for o in self.eng.fighters.values() if o is not f and not o.eliminated]
        bits = []
        if c.get("personality", True) and getattr(f, "personality", ""):
            bits.append(f"PERSONALITY: {f.personality}")
        if c.get("history", True) and getattr(f, "history", ""):
            h = f.history
            if short and len(h) > 300:
                h = h[:300].rsplit(". ", 1)[0] + "."
            bits.append(f"HISTORY (her only past: she may remember it, never anything beyond it): {h}")
        if c.get("relationships", True):
            for o in others:
                r = (getattr(f, "relationships", None) or {}).get(o)
                if r:
                    bits.append(f"{o.upper()} TO HER: {r}")
        return " ".join(bits)

    def _note(self, f, multi_team):
        return (
            f"{f.name}{f' (team {f.team})' if multi_team else ''}"
            f"{' [ELIMINATED]' if f.eliminated else ''}: {f.description}"
            + (f" APPEARANCE: {f.appearance}" if getattr(f, "appearance", "") else "")
            + (f" TELLS (how she shows pain and effort): {f.tells}" if getattr(f, "tells", "") else "")
            + (f" VOICE: {f.voice}" if getattr(f, "voice", "") else "")
            + (" " + self.character_note(f) if self.character_note(f) else "")
            + self._body_note(f))

    @staticmethod
    def _body_note(f):
        """What her body is NOT, said plainly, for the bodies the narrator gets wrong (a bird given teeth and fur)."""
        names = " ".join(f.parts).lower()
        if "beak" in names:
            return (f" BODY: {f.name} is a BIRD. She has a BEAK (no teeth, fangs, jaw, lips, muzzle or cheeks: she "
                    f"clacks or snaps her beak, hisses or screams through it), FEATHERS (no fur and no hackles: her "
                    f"feathers fluff, flatten or ruffle), WINGS (no arms, hands or paws) and TALONS on her feet "
                    f"(call them talons, never claws or paws).")
        if "wing" in names and re.search(r"\barm\b|upper arm|forearm", names):
            return (f" BODY: {f.name} has wings on her back AND arms with clawed hands; she is scaled or smooth-skinned, "
                    f"not furred.")
        return ""

    def recent_story(self, n=None):
        n = n or self.eng.rules.get("narration", {}).get("recent_beats_remembered", 2)
        n = max(n, 3)  # the repeat filter checks at least the last 3 beats
        return strip_pov("\n\n".join(self.story[-n:]))   # the models read the prose without the "— Name —" labels

    def _sync_absent(self):
        """Tell the narrator who is in fighters.json but NOT in this fight, so she never turns up in the story."""
        self.narrator.absent_words = [w for x in self.eng.absent() for w in (x["name"], x["species"]) if w]
        # features nobody in this line-up has (scales, coils, antennae...) can't turn up on anyone either
        from narrator import ANATOMY_WORDS
        have = " ".join(" ".join([f.description or "", getattr(f, "appearance", "") or "", getattr(f, "tells", "") or ""]
                                 + list(f.parts)) for f in self.eng.fighters.values()).lower() + " " + (self.eng.scene or "").lower()
        # "NO flotation sac and no collar", "NO antennae, no horn": what a description rules OUT is not something she has
        have = re.sub(r"\b(?:no|not|never) (?:[\w-]+ ){0,2}[\w-]+", " ", have)
        self.narrator.foreign_words = [w for w, stem in ANATOMY_WORDS.items() if stem not in have]

    def intro(self):
        """Opening narration: the arena and the fighters arriving, before the first attack."""
        self._sync_absent()
        self.push_history()
        try:
            text = self.narrator.intro(self.eng.scene, self.notes(full_reason=True))
        except llm.LLMError:
            self.history.pop()
            raise
        self.out("\n" + text + "\n")
        self.story.append(text)
        self.autosave()

    def _play_beat(self, direction="", manual=None, orders=None):
        aftermath = self.over
        self.eng._quirks_now = []      # (since build 281) the quirks that decide something this beat
        forced_recovery = None
        if not aftermath and isinstance(manual, dict) and manual.get("action") == "recover":
            print("/recover is for after the match. During the fight, use /getup to stand someone up.")
            return
        if aftermath and isinstance(manual, dict) and manual.get("action") in ("getup", "recover"):
            # after the match: bring the loser around on your command (narrated like any aftermath beat)
            stages = self.eng.rules.get("recovery", {}).get("stages") or self.eng.RECOVERY_DEFAULT
            want = manual.get("to")
            if manual.get("action") == "getup":
                want = len(stages) - 1
            forced_recovery = self.eng.force_recover(manual["attacker"], want)
            manual = {"action": "breather", "flavor": manual.get("flavor", "")}
        if aftermath and manual is not None and (manual if isinstance(manual, dict) else {}).get("action") != "breather":
            print("The match is over, so no more attacks. Press Enter (or /wait, or type what happens) to keep watching "
                  "the aftermath, or /undo to go back into the fight.")
            return
        if self.pending:
            print("[The last beat still has no narration. /reroll to write it, or /undo to take it back.]")
            return
        if manual is None and self.use_llm and not self.story \
                and self.eng.rules.get("narration", {}).get("scene_intro", True):
            self.intro()  # first Enter sets the scene; the next one starts the fight
            if not direction:
                return
        self.sync_dice()
        if manual is not None and self.strict():
            if not getattr(self.eng, "_windows_ready", False):
                # the openings for this beat haven't been rolled yet (you weren't asked first): roll them now
                self.eng.rolls = []
                self.eng.roll_pin_windows()
                self.eng._pre_rolls, self.eng._windows_ready = list(self.eng.rolls), True
            for b in (manual if isinstance(manual, list) else [manual]):
                if isinstance(b, dict):
                    b.pop("_manual", None)   # at the mercy of the dice: your commands follow the same rules as the director
        self.push_history()
        # this beat's dice, from here on (the openings rolled when your fighters were asked for their moves count too)
        self.eng.rolls = list(getattr(self.eng, "_pre_rolls", None) or []) if getattr(self.eng, "_windows_ready", False) else []
        self.eng.nudges = []
        self._was_in = {f.name for f in self.eng.active()}  # anyone knocked out this beat keeps their full profile
        # how everyone is placed as the beat begins, so the story can tell "was down, got up" from "never fell"
        self._posture_start = {f.name: self.eng.posture_text(f.name, short=True) for f in self.eng.active()}
        self._start_down = set(self.eng.downed) | {p["defender"] for p in self.eng.pins.values()}
        try:
            if aftermath:  # after the win: time passes, nobody attacks, the loser may come around
                champ = self.eng.winner()
                beats = [{"action": "aftermath", "attacker": champ, "flavor": direction or
                          (manual or {}).get("flavor", "")}]
                results, started = [{"type": "aftermath", "winner": champ, "focus": champ,
                                     "flavor": direction or (manual or {}).get("flavor", "")}], ()
            elif manual is not None:
                beats = manual if isinstance(manual, list) else [manual]
                results, started = resolve_many(self.eng, beats)
            else:
                if not self.use_llm:
                    self.history.pop()
                    print("Director is off (--no-llm). Use /commands.")
                    return
                self.progress("director is choosing the next beat")
                beats, results, started = self.director.next_beat(
                    self.eng, self.eng.scene, self.recent_story(), direction, self.recent_attacks, players=orders)
        except Exception:
            self.history.pop()  # nothing happened, so there's nothing to undo
            self.eng.ordered = set()
            raise   # (this beat's openings stay as they were: trying again doesn't roll them again)
        self.eng._windows_ready = False  # the openings were used: the next beat rolls fresh ones
        self.eng.ordered = set()
        if direction:
            self.transcript.append(f"> {direction}")  # you already see what you typed; keep it for /export
        history_before = list(self.recent_attacks)  # what had happened before this beat, for the narrator

        for res in results:
            if res.get("type") == "instant" and res.get("environment"):
                # the fall belongs to the attack that caused it: note it on that line
                if res.get("manhandle"):
                    self.recent_attacks.append(f"{res['attacker']} → {res['defender']}: {res['manhandle']} "
                                               f"({' → '.join(l['surface'] for l in res.get('landings', []))})")
                elif self.recent_attacks and len(self.recent_attacks) > len(history_before):
                    self.recent_attacks[-1] += (f" ({res.get('flavor', 'knocked down')}"
                                                + (", from where she lay" if res.get("from_ground") else "") + ")")
                else:
                    self.recent_attacks.append(f"{res['defender']}: {res.get('flavor', 'went down hard')}")
                continue
            if res.get("type") == "instant":
                m = res.get("move")
                what = (m["name"] + (" (improvised)" if m.get("improvised") else "")) if m else (res.get("flavor") or "hit")
                parts = []
                for h in res["hits"]:
                    if h["part"] not in parts:
                        parts.append(h["part"])
                if len(parts) > 3:
                    # a whole-body or spread move: the parts it hit hardest, not the first three in the body's list
                    took = {}
                    for h in res["hits"]:
                        took[h["part"]] = took.get(h["part"], 0) + float(h.get("damage_taken") or 0)
                    parts = ["whole body, worst on " + sorted(parts, key=lambda p: -took[p])[0]] + \
                        sorted(parts, key=lambda p: -took[p])[1:3]
                if res.get("charge") and not res["charge"].get("skipped"):
                    what += f" (a charge that drove her into {res['charge']['into']})"
                self.recent_attacks.append(f"{res['attacker']}: {what} → {poss_name(res['defender'])} {', '.join(parts[:3])}"
                                           if parts else
                                           f"{res['attacker']}: {what}" + ("" if (m or {}).get("target") == "self"
                                                                           else f" → nothing landed on {res['defender']}")
                                           if not res.get("dodged") else
                                           (f"{res['attacker']}: {what} → {res['defender']} fought it off (braced, "
                                            f"nothing landed)" if res.get("resisted") else
                                            f"{res['attacker']}: {what} → {res['defender']} DODGED it"
                                            + (" and countered" if res.get("counter_hits") else "")))
                rake = res.get("air_rake") or {}
                if rake.get("hits"):
                    # her rake back as they crossed landed after the attack did: it is the last thing to hit the attacker
                    rp = list(dict.fromkeys(h["part"] for h in rake["hits"]))
                    self.recent_attacks.append(f"{rake['by']}: rake as they crossed → {poss_name(res['attacker'])} "
                                               f"{', '.join(rp[:3])}")
            elif res.get("type") in ("hold_start", "pin_start"):
                self.recent_attacks.append(f"{res['attacker']}: {'pin' if res['type'] == 'pin_start' else 'hold'} on "
                                           f"{res['defender']}")
        also = self.eng.beat(skip_hold_ids=started)
        if self._character_cfg().get("moments", True):
            # (since build 281, narration.character.moments) her quirks, where they decided something
            also = list(also) + [{"type": "quirk_moment", "fighter": f_, "quirk": q_, "note": n_}
                                 for f_, q_, n_ in (getattr(self.eng, "_quirks_now", None) or [])]
        self.state_check()
        self.eng.record_beat(results, also)   # key moments and the strength track, for the end-of-fight summary
        self.eng.record_inner(results)        # what each fighter has learned this fight (narration.rich.inner)
        try:
            self.eng.note_gap(results, also)  # how far apart they end the beat (narration.match_state.distance)
        except Exception as e:
            note_failure("working out how far apart the fighters are", e)
        for e in also:  # blows landed inside a pin are real attacks too: the story may refer back to them
            if e.get("type") == "hold_end" and e.get("broke_free"):
                self.recent_attacks.append(f"{e['defender']}: wrenched free of {poss_name(e['attacker'])} hold")
            if e.get("type") != "pin_progress":
                continue
            where = ", ".join(dict.fromkeys(h["part"] for h in e.get("hits_on_pinner", [])))
            if e["struggle"] == "escape":
                self.recent_attacks.append(f"{e['defender']}: broke free of {poss_name(e['attacker'])} pin"
                                           + (f", hitting {poss_name(e['attacker'])} {where} on the way out" if where else ""))
            elif e["struggle"] == "partial" and where:
                self.recent_attacks.append(f"{e['defender']}: broke loose for a moment in the pin and hit "
                                           f"{poss_name(e['attacker'])} {where}")
            if e.get("complete"):
                self.recent_attacks.append(f"{e['attacker']}: held the pin on {e['defender']} to the end")
        self.recent_attacks = self.recent_attacks[-12:]
        if forced_recovery:
            also = [e for e in also if not (e.get("type") == "recovery" and e["fighter"] == forced_recovery["fighter"])]
            also.insert(0, forced_recovery)
        tactics = [] if aftermath else self.eng.track_tactics(results)   # plans made and paid off this beat
        for t in tactics:
            ago = t.get("ago", 0)
            self.out("🧠 " + (f"Plan: {t['text']}." if t["stage"] == "setup" else
                              f"Payoff ({ago} beat{'s' if ago != 1 else ''} in the making): {t['who']}: {t['text']}."
                              if t["stage"] == "payoff" else f"Read: {t['who']} {t['text']}."))
        bundle = {"actions": results, "also_this_beat": also, "after_win": aftermath, "tactics": tactics}
        headers = []
        for res in results:
            if res.get("type") == "instant":
                if not res.get("environment"):
                    self.attacks += 1
                headers.append(self.display.header({"action": res}, self.attacks))
        if headers:
            self.out("\n" + "─" * 40 + "\n" + "\n".join(headers))

        if self.args.json:
            print(json.dumps(bundle, indent=1, ensure_ascii=False))

        if self.use_llm:
            past = "\n".join(f"- {x}" for x in history_before[-10:]) or "- nothing yet: this is the first exchange"
            head = ("FIGHT SO FAR (the ONLY earlier attacks that really happened; never mention any other past attack "
                    "or move):" if len(history_before) <= 10 else
                    f"FIGHT SO FAR (the last 10 of {len(history_before)} earlier attacks; the older ones are in the story "
                    f"already; never mention a past attack or move that is in neither):")
            condition = self.eng.narrator_condition() + "\n" + head + "\n" + past
            # what each fighter is still feeling is the LAST thing that landed on her, never an attack that missed
            last_on, missed = {}, []
            for x in history_before:
                m = re.match(r"([^:]+): (.+?) → ([A-Z][\w-]+?)(?:'s|’s|'|’)?\s", x)
                if not m:
                    continue
                if "DODGED it" in x:
                    missed.append(f"{poss_name(m.group(1))} {m.group(2)} at {m.group(3)}")
                else:
                    last_on[m.group(3)] = f"{poss_name(m.group(1))} {m.group(2)}"
            if last_on:
                condition += ("\nTHE LAST ATTACK THAT LANDED on each fighter before this beat: "
                              + "; ".join(f"on {who}: {what}" for who, what in last_on.items())
                              + ". If the story looks back at what she is still reeling from, it is that one.")
            if missed:
                condition += ("\nMISSED (dodged: these never touched her, so they left no mark, no sting, and nothing to "
                              "shake off; never speak of them as hits): " + "; ".join(dict.fromkeys(missed[-4:])) + ".")
            self._rising = {e["fighter"] for e in also if e.get("type") == "get_up"}  # falling while rising is fine
            self.sync_narrator()
            args = (self.for_narrator(bundle), condition, self.notes(), self.eng.scene, self.recent_story())
            self._bench_save(args)     # (for /bench: this beat can be told again under other settings)
            text = self._write_prose(args)
            try:
                self.narrator.save_check_tally(HERE)     # (/checks)
            except Exception as e:
                note_failure("saving the /checks tally", e)
            if text is not None:
                text = self._maybe_polish(text, results, also, headers)
                self.out("\n" + text + "\n")
                self.story.append(text)
                self.last_narration = {"args": args, "index": len(self.story) - 1}
                if self._interlude_due():
                    try:
                        self.interlude(auto=True)
                    except llm.LLMError as e:
                        self.out(f"[the interlude could not be written: {e}]\n")
        else:
            self.story.append(" / ".join(f"{b.get('attacker')}: {b.get('action')} — {b.get('flavor', '')}"
                                         for b in beats))

        if self.show_math:
            mode = self.math_mode
            if mode == "auto":
                pressure_only = not any(r.get("type") == "instant" for r in results) and any(
                    e["type"] in ("hold_ongoing", "pin_progress") for e in also)
                # the tight layout is short enough to show every beat in full; the classic one shortens pin beats
                mode = "compact" if pressure_only and self.display.layout() == "classic" else "full"
            if mode == "compact":
                # a pin or hold STARTING, a roll, a release: say so even when the numbers are in short form
                for res in results:
                    if res.get("type") not in ("instant", "breather", "none", None):
                        block = self.display.beat({"action": res, "also_this_beat": []}).strip()
                        if block:
                            self.out(block + "\n")
            if mode in ("compact", "both"):
                line = self.display.compact(bundle)
                if line:
                    self.out(line + "\n")
                for e in also:  # struggle outcome in one line too
                    if e["type"] == "pin_progress" and mode == "compact":
                        pb = self.display.pin_block(e)
                        extra = " " + pb[-1].lstrip("- ") if e.get("complete") else ""
                        self.out(pb[0] + "  " + pb[1].lstrip("- ").rstrip(":. ") + "." + extra + "\n")
                if mode == "compact":
                    # who got up, who crumpled, which status ended: these change what you can do next
                    side = [e for e in also if e["type"] in ("get_up", "stays_down", "crumple", "adrenaline", "status_tick", "hold_end",
                                                             "status_end", "recovery", "alliance_end", "numb_end")]
                    tail = self.display.beat({"action": {"type": "none"}, "also_this_beat": side}).strip() if side else ""
                    if tail:
                        self.out(tail + "\n")
            dice = self.display.rolls_line(self.eng.rolls, getattr(self.eng, "nudges", []))
            if mode in ("full", "both"):
                self.out("-" * 40)
                blocks = [self.display.beat({"action": res, "also_this_beat": []}) for res in results]
                tail = self.display.beat({"action": {"type": "none"}, "also_this_beat": also}).strip()
                gap = "\n" if self.display.tight() else "\n\n"
                self.out(gap.join(b for b in blocks + [tail, dice] if b))
                self.out("-" * 40 + "\n")
            elif dice:
                self.out(dice + "\n")

        for result in results:
            if result.get("type") == "pin_forced" and result.get("elimination"):
                self.out((f"*** {result['defender']} passes out under {poss_name(result['attacker'])} pin after "
                          f"{result.get('seconds_to')} seconds. ***") if result.get("fade_mode") else
                         (f"*** {result['defender']} faints, pinned the full {result['duration']} seconds by "
                          f"{result['attacker']}. ***"))
            if result.get("type") == "pin_forced" and result.get("struggle") == "escape":
                self.out(f"*** {result['defender']} breaks free of {poss_name(result['attacker'])} pin! ***")
            if result.get("type") == "eliminated":
                self.out(f"*** {result['fighter']} is out: {result.get('reason', '')} ***")
            if result.get("type") == "pinfall" and result.get("result") == "pinned":
                self.out(f"*** {result['defender']} is eliminated by {result['attacker']}. ***")
        for e in also:
            if e.get("type") == "pin_progress" and e.get("elimination"):
                held = (f"{e.get('beats') or 1} beat{'s' if (e.get('beats') or 1) != 1 else ''}" if e.get("fade_mode")
                        else f"{e['duration']} seconds")
                self.out(f"*** {e['defender']} faints after {held} pinned by {e['attacker']}. ***")
            if e.get("type") == "pin_progress" and e.get("struggle") == "escape":
                self.out(f"*** {e['defender']} kicks out at the last second of {poss_name(e['attacker'])} pin! "
                         f"(can't be won yet: {e.get('why_not', '')}) ***" if e.get("last_second") else
                         f"*** {e['defender']} breaks free of {poss_name(e['attacker'])} pin "
                         + (f"after {e.get('beats') or 1} beat{'s' if (e.get('beats') or 1) != 1 else ''}" if e.get("fade_mode")
                            else f"at second {e['seconds_to']}") + "! ***")
        for e in also:
            if e.get("type") == "recovery" and aftermath:
                self.out(f"*** {e['fighter']}: {e['from']} → {e['to']} ***")
        if not aftermath and any(r.get("type") == "eliminated" or r.get("elimination")
               or (r.get("type") == "pinfall" and r.get("result") == "pinned") for r in results) or any(
                e.get("type") in ("pin_progress", "tap_out") and e.get("elimination") for e in also):
            winner = self.eng.winner()
            if winner:
                self.over = True
                self.record_result()
                self.out(f"*** Winner: {winner} ***\n(The match is over. Keep pressing Enter to watch the aftermath: "
                         f"the loser may stir and even get back up. Type what happens to steer it, or /undo.)\n")
                self.out("🩹 " + self.eng.injury_report().replace(" | ", "\n   ") + "\n")
                self.out(self.eng.fight_summary() + "\n")
            else:
                self.out(f"Still in the fight: {', '.join(f.name for f in self.eng.active())}\n")
        for e in also:
            if e.get("type") == "alliance_end" and len(e.get("still_in") or []) > 1:
                self.out(f"*** The alliance is over ({e['why']}): {' and '.join(e['still_in'])} are opponents again. ***")
        self.autosave()
        stay = int(self.eng.rules.get("narration", {}).get("more_after_attacks", 0) or 0)
        if (stay > 0 and self.use_llm and not aftermath and not self.pending and self.story
                and any(r.get("type") == "instant" and r.get("hits") for r in results)):
            for _ in range(min(stay, 3)):  # /more auto: dwell on what the attack left behind before moving on
                self.more()

    def state_check(self):
        """After every beat: do the rules that must always hold still hold (nobody pinned in mid-air, no grip on a
        fighter who is out...)? Anything wrong is written to state_check.log, shown in one line, and put right the
        way a loaded save is. Costs nothing when all is well."""
        try:
            bad = self.eng.check_state()
        except Exception as e:      # the check must never stop a fight
            bad = [f"the check itself failed: {e!r}"]
        if not bad:
            return
        try:
            self.eng.repair_state()
            left = self.eng.check_state()
        except Exception as e:
            left = [f"the repair failed: {e!r}"]
        try:
            with open(os.path.join(HERE, "state_check.log"), "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M')} build {VERSION} fight {self.fight_no} beat "
                         f"{self.eng.turn}: " + "; ".join(bad) + (f" | STILL WRONG after repair: {'; '.join(left)}"
                                                                   if left else " | repaired") + "\n")
        except OSError:
            pass
        print(f"  [state check, beat {self.eng.turn}: {bad[0]}" + (f" (+{len(bad) - 1} more)" if len(bad) > 1 else "")
              + ("; put right" if not left else "; could NOT be put right") + ", see state_check.log]")

    @staticmethod
    def for_narrator(bundle):
        """The narrator only needs time effects when someone's exhaustion level actually changed."""
        also = []
        for e in bundle["also_this_beat"]:
            if e["type"] == "time_passes":
                shifted = {n: {"now": f["health_tier"], "reaction_guide": f["reaction_guide"]}
                           for n, f in e["fighters"].items() if f["health_tier_changed"]}
                if shifted:
                    also.append({"type": "fatigue_shift", "fighters": shifted})
            elif e["type"] == "recovery" and not bundle.get("after_win"):
                continue  # someone knocked out earlier stirring offstage: not part of the fight's story
            else:
                also.append(e)
        return {"actions": bundle["actions"], "also_this_beat": also}


poss_name = poss_word   # (one possessive rule for the whole game: engine.poss_word)


USAGE = {
    "strike": ('/strike <attacker> <defender> <part> <severity> [count] ["flavor"]', 4),
    "combo": ('/combo <attacker> <defender> "Part:severity,Part:severity" ["flavor"]', 3),
    "move": ('/move <attacker> <defender> "<Move>" ["Part,Part"] [count]', 3),
    "hold": ('/hold <attacker> <defender> ["Part:severity=with,..."] [easing|steady|tightening] ["flavor"]', 2),
    "pin": ('/pin <attacker> <defender> ["Part:severity=with,..."] ["flavor"]   (parts optional)', 2),
    "adjust": ("/adjust <hold_id> [severity] [ramp]", 1),
    "release": ('/release <hold_id> ["how"]   or   /release <attacker> <defender> ["how"]', 1),
    "eliminate": ('/eliminate <fighter> ["reason"]', 1),
    "struggle": ('/struggle <pinned fighter> ["how"]   (they WILL try to break free; the result is rolled)', 1),
    "pinsuccess": ('/pinsuccess <pinner> <pinned> ["Part:severity=with,..."]', 2),
    "pinescape": ("/pinescape <pinner> <pinned>", 2),
    "quickpin": ("/quickpin <attacker> <defender>", 2),
    "wait": ('/wait ["what happens"]', 0),
    "land": ('/land <fighter> "surface=Part+Part:severity; surface=Part+Part:severity"', 2),
    "down": ("/down <fighter>", 1),
    "roll": ('/roll <attacker> <defender> over|back|front|side|sit|up|stand', 2),
    "rollover": ('/rollover [who does it] <fighter> ["how"]', 1),
    "onback": ('/onback [who does it] <fighter> ["how"]', 1),
    "onfront": ('/onfront [who does it] <fighter> ["how"]', 1),
    "onside": ('/onside [who does it] <fighter> ["how"]', 1),
    "situp": ('/situp [who does it] <fighter> ["how"]', 1),
    "pickup": ('/pickup [who does it] <fighter> ["how"]', 1),
    "standup": ('/standup [who does it] <fighter> ["how"]', 1),
    "grapple": ('/grapple <attacker> <defender> ["Part=what grips it"] ["how"]   (both on their feet)', 2),
    "throw": ('/throw [who does it] <fighter> ["surface=Part+Part:severity; surface...; tumble"] ["how"]', 1),
    "slam": ('/slam [who does it] <fighter> ["surface=Part+Part:severity; surface..."] ["how"]', 1),
    "drag": ('/drag [who does it] <fighter> ["surface=Part+Part:severity; surface..."] ["how"]', 1),
    "getup": ("/getup <fighter> [tries 1-3]   (after the match: brings the loser back to her feet)", 1),
    "recover": ("/recover <fighter> [stirring|awake|up]   (after the match: one recovery stage, or straight to one)", 1),
    "sustain": ('/sustain <attacker> <defender> "<Move>" <pulses 2-4> ["what she is pressed against"] ["Part,Part"]', 4),
    "charge": ('/charge <attacker> <defender> "<Move or a name for an improvised charge>" "<what she is driven into>" ["Part,Part"]', 4),
    "heal": ('/heal <fighter> <"Part,Part" | worst | all> <damage to remove> [resistance to restore] ["how"]', 3),
    "restore": ('/restore <fighter> <health %> ["how"]', 2),
}


def scene_list(eng):
    """The arenas, numbered, with the first few things each one has in it."""
    out = ["ARENAS"]
    for i, (name, sc) in enumerate(eng.scenes.items(), start=1):
        bits = [h["name"] for h in sc.get("hazards") or []][:4]
        mark = "  ◀ now" if name == eng.scene_name else ""
        out.append(f"  {i:>2}. {sc.get('title', name)}  ({name}){mark}\n        {', '.join(bits)}...")
    return "\n".join(out)


def scene_summary(eng, full=False):
    """One arena in a few lines: its name, and what it does."""
    sc = eng.scene_cfg
    hz, evs = sc.get("hazards") or [], sc.get("events") or []
    head = f"{sc.get('title', 'Your own scene')}" + (f" ({eng.scene_name})" if eng.scene_name != "custom" else "")
    if not full:
        return head + (f": {len(hz)} hazards, {len(evs)} things it does by itself (/hazards lists them)" if hz or evs else
                       ": nothing tracked (your own description)")
    lines = [head, "Hazards (they act when a fighter lands on, is thrown, dragged, driven or pressed into them):"]
    lines += ["  " + l for l in (eng.scene_brief().split("\n") if hz else ["- none"])]
    lines.append("By itself, now and then:")
    for i, e in enumerate(evs, start=1):
        does = ([f"{e['severity']} hit"] if e.get("severity") else []) + [
            f"{round(100 * float(x.get('chance', 1)))}% {x['status']}" for x in e.get("effects") or []]
        who = {"anyone": "one fighter", "standing": "one fighter on her feet", "down": "one fighter on the ground",
               "all": "everyone"}.get(e.get("who", "anyone"), "one fighter")
        lines.append(f"  {i}. {e['name']} ({who}: {', '.join(does) or 'a scare'})")
    if not evs:
        lines.append("  - nothing")
    return "\n".join(lines)


def variant_lines(eng):
    """One line for each fighter in this fight who is not in her original version."""
    out = []
    for name, kind in getattr(eng, "variant_of", {}).items():
        if kind != "original" and any(f.name == name for f in eng.fighters.values()):
            label = eng.variants.get(name, {}).get(kind, "")
            out.append(f"🧬 {name}: the {kind} version" + (f" ({label})" if label else "")
                       + f". /variant {name} original goes back.")
    return "\n".join(out)


def ask_scene(s, read=None):
    """At the start of a run: which arena? Enter keeps the last one."""
    eng = s.eng
    print(scene_list(eng))
    print(f"Type a number or a name, r for a random one, or just press Enter to stay in "
          f"{eng.scene_cfg.get('title', 'the same arena')}. (Turn this question off: /set scene.ask_at_start false)")
    wrong = 0
    while wrong < 4:
        try:
            line = (read or input)("Scene> ").strip()   # (looked up now: the window routes input)
        except (EOFError, KeyboardInterrupt):
            return
        if not line:
            return
        if line.startswith("/") and not re.match(r"/scenes?\b", line, re.I):
            # any other command works here too (/set, /model, /settings...); then the question is asked again
            turn0 = s.eng.turn
            try:
                handle_command(s, line)
            except ValueError as e:
                print(f"Error: {e}")
            if s.eng.turn != turn0 or re.match(r"/(?:newfight|auto|autofight|load|fight)\b", line, re.I):
                # (since build 276) a fight has started from here (/newfight, /auto): the arena question is over
                return
            print("(Now the arena: a number or a name, r for random, or Enter to stay.)")
            continue
        if line.startswith("/"):
            line = line.lstrip("/").replace("scene", "", 1).strip() or ""
            if not line:
                continue
        wrong += 1
        try:
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):   # the arena is printed once, just below
                handle_command(s, "/scene " + line)
            return
        except ValueError as e:
            print(f"Error: {e}")


def _match_kind(eng):
    """What kind of match the rules make now, in a few words (for the setup questions)."""
    if eng.submission_match():
        if eng.sub_knockouts():
            return "anything goes (knockout, " + ("" if eng.no_pins() else "pin, ") + "or tap-out)"
        return f"submission ({eng.taps_needed()} taps)" if eng.taps_needed() > 1 else "submission"
    if eng.ko_only():
        return "knockout only" + (", no pins" if eng.no_pins() else "")
    return "pins and knockouts"


def setup_questions(s, read=None):
    """(since build 282, setup.enabled) the questions asked before a run begins: a preset or the questions or
    nothing, then the arena, the fighters, the opening passage, the kind of match, the story plan, the important
    settings and anything more. Enter keeps what is set at every question; any /command works at any of them."""
    # (s.eng, never a copy of it: /newfight at the fighters question puts a new engine in its place)
    cfg = s.eng.rules.get("setup") or {}
    ask = list(cfg.get("questions") or ["scene", "fighters", "variants", "players", "intro", "match", "taps", "pins",
                                        "plan", "focus", "targeting", "reason", "length", "damage", "traits",
                                        "character", "words", "story", "hazards", "polish", "more", "begin"])
    rd = read or input
    started = {"yes": False}

    def line_(prompt):
        try:
            return rd(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return None

    def cmd_(c, quiet=False):
        turn0 = s.eng.turn
        try:
            if quiet:
                import contextlib, io
                with contextlib.redirect_stdout(io.StringIO()):
                    handle_command(s, c)
            else:
                handle_command(s, c)
        except ValueError as e:
            print(f"Error: {e}")
            return False
        if s.eng.turn != turn0 or re.match(r"/(?:auto|autofight|load|fight)\b", c, re.I):
            started["yes"] = True        # a fight began from here: the questions are over
        return True

    def ask_(prompt, apply):
        """One question: Enter keeps it; a /command runs and the question comes again; anything else is the
        answer, given to apply (which says False when it couldn't use it)."""
        for _ in range(4):
            got = line_(prompt)
            if got is None or got == "":
                return
            if got.startswith("/"):
                cmd_(got)
                if started["yes"]:
                    return
                continue
            if apply(got) is not False:
                return
    pres = [k for k, v in (s.eng.rules.get("presets") or {}).items() if not str(k).startswith("_") and isinstance(v, dict)]
    print("SETUP (Enter at any question keeps what is set; any /command works too; /set setup.enabled false turns "
          "these questions off)")
    print("  Match presets: " + "   ".join(f"{i}) {k}" for i, k in enumerate(pres, 1)))
    first = line_(f"Start> Enter = begin now as things are ({_match_kind(s.eng)}), a preset number or name = that "
                  f"kind of match, o = go through the setup questions: ")
    if first is None or first == "":
        return
    if first.startswith("/"):
        cmd_(first)
        if started["yes"]:
            return
        first = "o"
    if first.lower() not in ("o", "options", "q", "questions", "all"):
        pick = pres[int(first) - 1] if first.isdigit() and 0 < int(first) <= len(pres) else first.lower()
        if cmd_(f"/preset {pick}"):
            ask = [q for q in ask if q in ("scene", "fighters", "players", "begin")]   # a preset: where, who, begin
    rules = s.eng.rules
    nar = rules.get("narration") or {}

    def yesno(got):
        return got.lower() in ("on", "y", "yes", "true", "1")

    def q_scene():
        if len(s.eng.scenes) > 1:
            ask_scene(s, read=rd)

    def q_fighters():
        roster = list(s.eng.roster)
        now = " vs ".join(f.name for f in s.eng.fighters.values())
        print("  Fighters: " + "   ".join(f"{i}) {n}" for i, n in enumerate(roster, 1)))

        def fighters(got):
            names = [roster[int(w) - 1] if w.isdigit() and 0 < int(w) <= len(roster) else w
                     for w in re.split(r"[\s,]+", got) if w and w.lower() not in ("vs", "and")]
            if len(names) < 2:
                print("Two or more fighters, by name or number (e.g. 3 7, or Nerine Ripples).")
                return False
            if not cmd_("/newfight " + " ".join(names), quiet=True):   # (shown in full once the questions end)
                return False
            print(f"  Fighters: {' vs '.join(f.name for f in s.eng.fighters.values())}")
        ask_(f"Fighters> who fights (names or numbers; Enter keeps {now}): ", fighters)

    def q_variants():
        for f in s.eng.fighters.values():
            vs = [k for k in ((s.eng.variants or {}).get(f.name) or {}) if not str(k).startswith("_")] \
                if isinstance(getattr(s.eng, "variants", None), dict) else []
            if vs:
                ask_(f"Variant> which {f.name}: {' | '.join(vs)} (Enter keeps {s.eng.variant_of.get(f.name, 'the one set')}): ",
                     lambda got, n=f.name: cmd_(f"/variant {n} {got}"))

    def q_players():
        names = [f.name for f in s.eng.fighters.values()]
        ask_(f"Players> will you play as a fighter yourself? one or more names ({', '.join(names)}), all, or Enter "
             f"for none (the director runs everyone): ", lambda got: cmd_("/play " + got))
        if getattr(s, "players", None):
            ask_("Dice> for the fighters you play: fair (the dice decide; your /commands can still force things), "
                 f"strict (no forcing), or free (their tries always work) (Enter keeps {s.dice_mode()}): ",
                 lambda got: cmd_("/play dice " + got.lower()))

    def q_intro():
        on = nar.get("scene_intro", True)
        ask_(f"Intro> an opening passage that sets the scene, on or off (Enter keeps {'on' if on else 'off'}): ",
             lambda got: cmd_(f"/intro {'on' if yesno(got) else 'off'}"))

    def q_match():
        print("  Match type: " + "   ".join(f"{i}) {k}" for i, k in enumerate(pres, 1)))
        ask_(f"Match> which kind (Enter keeps {_match_kind(s.eng)}): ",
             lambda got: cmd_("/preset " + (pres[int(got) - 1] if got.isdigit() and 0 < int(got) <= len(pres)
                                            else got.lower())))

    def q_taps():
        if s.eng.submission_match():
            ask_(f"Taps> how many tap-outs win it (Enter keeps {s.eng.taps_needed()}): ",
                 lambda got: (cmd_(f"/set finish.submission.taps.enabled {'true' if int(got) > 1 else 'false'}"),
                              cmd_(f"/set finish.submission.taps.needed {max(1, int(got))}")) if got.isdigit() else False)

    def q_pins():
        if not s.eng.no_pins():
            sc = ((rules.get("director") or {}).get("pin_urge") or {}).get("scale", 0.5)
            ask_(f"Pins> how often pin openings come: a number (0.5 = the default, 1 = twice as often, 0 = never), "
                 f"or default (Enter keeps {sc:g}): ", lambda got: cmd_("/pins " + got))

    def q_plan():
        pl = s.eng.plan or {}
        now = (pl.get("shape") or "none") + (f" {pl.get('winner')}" if pl.get("winner") else "")
        ask_(f"Plan> the shape of the fight: close [name] | dominate <name> | comeback <name> | winner <name> | even | "
             f"off (Enter keeps {now}): ", lambda got: cmd_("/plan " + got))

    def q_focus():
        ask_("Focus> where attacks aim: injured, vulnerable, core, head, neck, legs, arms, tail... (one fighter: "
             "Nocturne legs), or off (Enter: wherever the fight takes them): ", lambda got: cmd_("/focus " + got))

    def q_targeting():
        ask_("Targeting> how many body parts each attack catches: one, few, many, all or auto (Enter keeps it): ",
             lambda got: cmd_("/targeting " + got.lower()))

    def q_reason():
        if len(s.eng.fighters) == 2:
            ask_("Reason> why they are fighting: on (one picked for you), list, a number from the list, your own "
                 "words in quotes, or off (Enter keeps it): ", lambda got: cmd_("/reason " + got))

    def q_length():
        ask_("Length> about how many beats the fight runs: 30, 35, 40, 45, 50 or 60 (Enter keeps it): ",
             lambda got: cmd_("/length " + got))

    def q_damage():
        sc = (rules.get("damage") or {}).get("damage_scale", 3)
        ask_(f"Damage> how hard every hit lands, the damage scale (3 = the balanced default; Enter keeps {sc:g}): ",
             lambda got: cmd_("/scale " + got))

    def q_traits():
        on = (rules.get("traits") or {}).get("enabled", True)
        ask_(f"Traits> each fighter's traits and quirks (speed, grip, stubbornness...) on or off (Enter keeps "
             f"{'on' if on else 'off'}): ", lambda got: cmd_(f"/set traits.enabled {'true' if yesno(got) else 'false'}"))

    def q_character():
        on = (nar.get("character") or {}).get("enabled", True)
        ask_(f"Character> their personality, history and relationships in the story, on or off (Enter keeps "
             f"{'on' if on else 'off'}; /profile shows them): ",
             lambda got: cmd_(f"/set narration.character.enabled {'true' if yesno(got) else 'false'}"))

    def q_words():
        ask_(f"Swearing> never, rare or free (Enter keeps {nar.get('swearing', 'rare')}): ",
             lambda got: cmd_("/set narration.swearing " + got.lower()) if got.lower() in ("never", "rare", "free")
             else False)
        ask_(f"Gore> none, mild or off (off = no limit) (Enter keeps {nar.get('gore_level', 'mild')}): ",
             lambda got: cmd_("/set narration.gore_level " + got.lower()) if got.lower() in ("none", "mild", "off")
             else False)

    def q_story_length():
        lm = (nar.get("rich") or {}).get("length_mult", 1.5)
        ask_(f"Story> how much is written each beat: short, normal or long (Enter keeps it; now x{lm:g}): ",
             lambda got: cmd_("/set narration.rich.length_mult " + {"short": "2.0", "normal": "1.5", "long": "1.0"}
                              [got.lower()]) if got.lower() in ("short", "normal", "long") else False)

    def q_hazards():
        on = (rules.get("scene") or {}).get("events", True)
        ask_(f"Hazards> the arena doing things by itself now and then, on or off (Enter keeps "
             f"{'on' if on else 'off'}): ", lambda got: cmd_(f"/hazards {'on' if yesno(got) else 'off'}"))

    def q_polish():
        try:
            import polish as _pol
            has_key = bool(_pol.api_key(rules))
        except Exception:
            has_key = False
        on = bool((nar.get("polish") or {}).get("enabled", False))
        if not has_key:
            print("  (Venice polish: no key yet. /polish key <your key> sets one; /help examples shows the steps.)")
            return
        ask_(f"Polish> Venice improves the prose: on, off, or big (only the big moments) (Enter keeps "
             f"{'on' if on else 'off'}): ",
             lambda got: (cmd_("/polish on"), cmd_("/polish when big")) if got.lower() == "big"
             else cmd_("/polish " + ("on" if yesno(got) else "off")))

    def q_more():
        print("More> any other /commands, one per line (/encourage, /weakspots, /set ..., /help examples); Enter when "
              "done.")
        for _ in range(20):
            got = line_("More> ")
            if not got:
                break
            cmd_(got if got.startswith("/") else "/" + got)
            if started["yes"]:
                return

    def q_begin():
        got = line_("Begin> Enter = start, and press Enter for each beat; a number = let the director run that many "
                    "beats on its own: ")
        if got and got.isdigit():
            s._setup_auto = int(got)      # (the run loop starts /auto with it once the fight is shown)

    table = {"scene": q_scene, "fighters": q_fighters, "variants": q_variants, "players": q_players,
             "intro": q_intro, "match": q_match, "taps": q_taps, "pins": q_pins, "plan": q_plan, "focus": q_focus,
             "targeting": q_targeting, "reason": q_reason, "length": q_length, "damage": q_damage,
             "traits": q_traits, "character": q_character, "words": q_words, "story": q_story_length,
             "hazards": q_hazards, "polish": q_polish, "more": q_more, "begin": q_begin,
             # (the first version's grouping, still understood)
             "important": lambda: (q_length(), q_damage(), q_players(), q_polish())}
    heads = {"scene": "WHERE AND WHO", "intro": "THE MATCH", "plan": "THE STORY", "length": "BALANCE",
             "traits": "THE WRITING", "more": "ANYTHING ELSE"}
    for q in ask:
        if started["yes"]:
            return
        if q in heads:
            print(f"\n— {heads[q]} —")
        fn = table.get(q)
        if fn is None:
            continue
        try:
            fn()
        except (ValueError, KeyError, IndexError) as e:
            print(f"Error: {e}")

HELP_TOPICS = [   # (key, words that find it, one line for the menu) in the order of HELP's sections
    ("play", "playing play enter direction auto wait more interlude lull long", "playing: Enter, typed directions, /play as a fighter, /auto, /more, /interlude"),
    ("fights", "fights fight newfight autofight simulate team ally results", "fights: who is in them, /newfight, /autofight, /simulate, teams"),
    ("attacks", "attacks attack move charge sustain strike combo land pummel", "attacks you choose: /move (pummels), /charge, /sustain, /strike, /combo, /land"),
    ("moving", "moving move throw slam drag grapple roll situp chain tumble", "one fighter moving another: /throw, /slam, /drag, /grapple, chains, rolling her over"),
    ("pins", "pins pin holds hold release struggle pinrate frequency", "holds and pins: /pin, /hold, /release, /struggle, /pins (how often), the pin clock"),
    ("story", "story plan focus targeting steering weakspots weak reason reasons why", "steering the story: /reason, /plan, /focus, /weakspots, /targeting"),
    ("moves", "moves moveinfo learn forget", "moves: /moves, /moveinfo, /learn, /forget"),
    ("healing", "healing heal restore recover aftermath", "healing and after the match: /heal, /restore, /recover"),
    ("balance", "balance scale length damage health healthloss resscale wear vital numb fighter part hard", "balance: /scale, /length, how hard hits land, /fighter and /part"),
    ("narration", "narration story words talk sounds sample blocks phrases model reader repair budget timing checks slow speed", "narration: /words, /talk, /sounds, /sample, /phrases, /model, the checks and their cost"),
    ("settings", "settings set sets get options layout math style scene arena hazards", "settings, screen, arenas: /set, /sets (every setting), /get, /settings, /layout, /scene, /hazards"),
    ("switches", "switches switch toggle knockout knockouts ko pins guided compact reads swearing context window intro rich", "switches: knockouts only, no pins, the opening passage, richer narration, guided narration, speed..."),
    ("looking", "looking status health look traits", "looking around: /status, /health, /look, /traits"),
    ("files", "files undo reroll save load export exportfight quit", "undo, files, quit: /undo, /reroll, /save, /load, /export, /exportfight"),
    ("presets", "presets preset match matches submission knockout anything", "match presets: /preset submission | submission3 | knockout | pins | anything"),
    ("examples", "examples example howto how recipes recipe", "examples: whole fights, steering, playing, attacks, holds, Venice polish, settings"),
]

HELP_QUICK = """
QUICK START
  [Enter]                    the next beat (the director chooses)
  Ripples goes for the throat   type what you want to happen next; the director makes it so if it can
  /autofight 1 3 Nocturne Ripples   a whole fight on its own (then 3 beats of aftermath)
  /move Nocturne Ripples "Slash" "Chest" 4      an attack you choose (4 = a pummel of 4 blows)
  /charge Ripples Nocturne "Aqua Jet" "an old oak"     a charge into the scenery
  /throw Ripples "an old oak=Chest:heavy; the grass:solid"   thrown into the arena, surface by surface
  /pin Nocturne Ripples      a pin (the engine fills in the grips)
  a + b                      join up to three commands into one beat
  /auto 20   /stop           let the director run 20 beats; /stop (in the window) ends the run after this beat
  /undo   /reroll   /status  take a beat back, rewrite its narration, see where everyone stands
  /help switches             the on/off settings: knockouts only, no pins, the opening passage, richer narration...
  /sets   /sets <word>       every setting there is, ready to copy as a /set line (/sets all: all of them, to a file)
  /preset submission         a whole kind of match at once (submission, submission3, knockout, pins, anything)
  (at start-up)              the setup questions: arena, fighters, who you play, match type, plan... Enter skips any
  /help examples             ways to do common things: steering, playing a fighter, holds, Venice polish, settings

TOPICS   /help <topic>   ·   /help <command> (/help charge)   ·   /help <any word> searches everything
         (/help knockout, /help tumble)   ·   /help all = everything
"""


def help_text(arg=""):
    """/help: a short menu; /help <topic>: that section; /help <command>: the lines about it; /help all: everything."""
    arg = arg.strip().lower().lstrip("/")
    bar = "=" * 20
    secs = [s for s in re.split(r"\n=+\n", HELP) if s.strip()]
    # pair each title with its body: the text alternates title, body, title, body
    sections = []
    for i in range(0, len(secs) - 1, 2):
        sections.append((secs[i].strip(), secs[i + 1]))
    if not arg:
        return HELP_QUICK + "\n".join(f"  {k:<9} {line}" for k, _, line in HELP_TOPICS)
    if arg == "all":
        return HELP
    for idx, (key, words, _) in enumerate(HELP_TOPICS):
        if arg == key or arg in words.split()[:1]:
            if idx < len(sections):
                title, body = sections[idx]
                return f"{bar}\n {title}\n{bar}\n{body.rstrip()}\n\n(/help for the menu, /help all for everything)"
    # a command: every block of help that mentions it
    hits, own = [], []
    for title, body in sections:
        blocks = re.split(r"\n(?=  /)", body)
        for b in blocks:
            if re.match(r"\s*/" + re.escape(arg) + r"\b", b):
                own.append(b.rstrip())          # the command's own entry
            elif re.search(r"(?<![\w-])/" + re.escape(arg) + r"\b", b):
                hits.append(b.rstrip())         # an entry that only mentions it
    hits = own or hits
    if hits:
        return "\n\n".join(hits) + "\n\n(/help for the menu)"
    for idx, (key, words, _) in enumerate(HELP_TOPICS):
        if arg in words.split() and idx < len(sections):
            title, body = sections[idx]
            return f"{bar}\n {title}\n{bar}\n{body.rstrip()}"
    # anything else: every entry in the help that mentions it (an entry is a command line and the lines under it)
    words_ = [w for w in re.findall(r"[a-z0-9_.]+", arg) if len(w) > 2]
    found = []
    for title, body in sections:
        for b in re.split(r"\n(?=  \S)", body):
            low = b.lower()
            if words_ and all(w in low for w in words_):
                found.append((title.split("   ")[0].title(), b.rstrip()))
    if found:
        out, last = [], None
        for title, b in found[:14]:
            if title != last:
                out.append(f"-- {title} --")
                last = title
            out.append(b)
        more = f"\n(and {len(found) - 14} more: /help all)" if len(found) > 14 else ""
        return "\n".join(out) + more + "\n\n(/help for the menu)"
    return f"Nothing in the help about '{arg}'. /help for the menu, /help all for everything."


def _clean_name(x):
    return str(x).strip().strip("<>[]").strip()


# ---------- bold and italic on screen ----------
ANSI_COLORS = {"red": 31, "green": 32, "yellow": 33, "blue": 34, "magenta": 35, "cyan": 36, "white": 37}
_BANNER = re.compile(r"\*\*\*[ \t]*([^*\n]+?)[ \t]*\*\*\*")
_BOLD = re.compile(r"\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?![\s*])([^*\n]+?)(?<![\s*])\*(?![*\w])")


def style_text(text, color="", thought_color="", sound_color=""):
    """Turn the **bold** and *italic* marks in a piece of output into the codes a console understands. Italics in the
    story are thoughts or written-out sounds; each can also get a colour, for consoles (Spyder's) that don't slant
    text, so they still stand out from the narration."""
    on = "\x1b[1m" + (f"\x1b[{ANSI_COLORS[color]}m" if color in ANSI_COLORS else "")
    off = "\x1b[22m" + ("\x1b[39m" if color in ANSI_COLORS else "")
    text = _BANNER.sub(lambda m: f"{on}{m.group(1)}{off}", text)
    text = _BOLD.sub(lambda m: f"{on}{m.group(1)}{off}", text)

    def italic(m):
        c = sound_color if _is_sound(m.group(1)) else thought_color
        if c in ANSI_COLORS:
            return f"\x1b[3m\x1b[{ANSI_COLORS[c]}m{m.group(1)}\x1b[39m\x1b[23m"
        return f"\x1b[3m{m.group(1)}\x1b[23m"
    return _ITALIC.sub(italic, text)


class StyledOut:
    """Stands in for the screen: everything printed passes through style_text first. Saved text (the transcript,
    /export, saves) never goes through here, so it keeps its plain asterisks."""

    def __init__(self, stream, rules):
        self.stream, self.rules = stream, rules

    def _on(self):
        mode = str(self.rules.get("console", {}).get("styled_text", "auto")).lower()
        if mode in ("off", "false", "no"):
            return False
        if mode in ("on", "true", "yes"):
            return True
        tty = getattr(self.stream, "isatty", lambda: False)()
        return "ipykernel" in sys.modules or "spyder_kernels" in sys.modules or tty

    def write(self, text):
        if isinstance(text, str) and "*" in text and self._on():
            con = self.rules.get("console", {})
            text = style_text(text, str(con.get("bold_color", "") or "").lower(),
                              str(con.get("thought_color", "") or "").lower(), str(con.get("sound_color", "") or "").lower())
        return self.stream.write(text)

    def __getattr__(self, name):  # flush, isatty, encoding... all come from the real screen
        return getattr(self.stream, name)


MOVE_HER = {"rollover": "roll over", "flip": "roll over", "turnover": "roll over",
            "onback": "onto her back", "onfront": "onto her front", "onbelly": "onto her front",
            "onside": "onto her side", "putonside": "onto her side",
            "situp": "sit her up", "sit": "sit her up", "prop": "sit her up",
            "pickup": "pick up", "lift": "pick up",
            "standup": "stand her up", "stand": "stand her up"}
CMD_ALIASES = {"flip": "rollover", "turnover": "rollover", "onbelly": "onfront", "putonside": "onside", "sit": "situp",
               "prop": "situp", "lift": "pickup", "stand": "standup", "toss": "throw", "hurl": "throw",
               "bodyslam": "slam"}


def _impacts(text, mark=False):
    """'a stalagmite=Upper Back+Head:heavy; the floor:solid' -> the landing list the engine takes."""
    impacts = []
    for chunk in str(text or "").split(";"):
        chunk = chunk.strip()
        if not chunk or re.fullmatch(r"(?i)tumbl(?:e|es|ing)(?: on)?", chunk):
            continue   # "tumble" is not a surface: it asks for a tumble after the last one (see _wants_tumble)
        spec, _, sev = chunk.rpartition(":") if ":" in chunk else (chunk, "", "solid")
        surface, _, parts = spec.partition("=")
        impacts.append({"surface": surface.strip() or "the ground",
                        "parts": [p.strip() for p in parts.split("+") if p.strip()],
                        "severity": (sev or "solid").strip().lower()})
        if mark:
            impacts[-1]["_given"] = ":" in chunk
    return impacts


def _wants_tumble(text):
    """True when a landing list ends by asking for a tumble: "the cave wall=Left Hip:heavy; tumble"."""
    return any(re.fullmatch(r"(?i)tumbl(?:e|es|ing)(?: on)?", c.strip()) for c in str(text or "").split(";"))


def _is_fighter(eng, word):
    try:
        eng.get(word)
        return True
    except Exception:
        return False


def _is_part(eng, fighter, word):
    try:
        eng.get(fighter).part(word)
        return True
    except Exception:
        return False


def _doer_and_target(eng, a, cmd):
    """One name = the fighter being moved, and the other fighter does it. Two names = who does it, then who is moved.
    Returns (doer, target, the rest of the words)."""
    if eng is None or len(a) > 1 and _is_fighter(eng, a[1]):
        if len(a) < 2:
            raise ValueError(f"/{cmd} needs the fighter being moved")
        return a[0], a[1], a[2:]
    target = eng.get(a[0])
    others = [f for f in eng.active() if f.name != target.name and getattr(f, "team", None) != getattr(target, "team", 0)]
    others = others or [f for f in eng.active() if f.name != target.name]
    free = [f for f in others if not eng.pinned_by(f.name) and f.name not in eng.downed] or others
    if len(free) != 1:
        names = ", ".join(f.name for f in others) or "nobody else"
        raise ValueError(f"who does it? /{cmd} <who does it> {target.name} ...   (it could be: {names})")
    return free[0].name, target.name, a[1:]


def manual_beat(cmd, a, eng=None):
    """Turn a /command into the same beat dict the director produces."""
    cmd = CMD_ALIASES.get(cmd, cmd)
    if cmd in USAGE:
        usage, need = USAGE[cmd]
        a = [_clean_name(x) for x in a]
        if len(a) < need:
            raise ValueError(f"/{cmd} needs more. Usage: {usage}")
        if cmd == "release" and not a[0].isdigit() and len(a) < 2:
            raise ValueError(f"Usage: {usage}")
    rest = lambda i: " ".join(a[i:])
    if cmd == "strike":
        b = {"action": "strike", "attacker": a[0], "defender": a[1], "part": a[2].lower(),
             "severity": a[3].lower(), "count": 1}
        i = 4
        if len(a) > 4 and a[4].isdigit():
            b["count"], i = int(a[4]), 5
        b["flavor"] = rest(i)
    elif cmd == "combo":
        hits = []
        for c in a[2].split(","):
            who = None
            if ">" in c:  # Name>Part:severity hits a different fighter
                who, c = c.split(">", 1)
            part, sev = c.rsplit(":", 1)
            hits.append({"defender": who or a[1], "part": part.strip(), "severity": sev.strip().lower()})
        b = {"action": "combo", "attacker": a[0], "defender": a[1], "hits": hits, "flavor": rest(3)}
    elif cmd in ("hold", "pin"):
        hits = []
        if len(a) < 3 or ":" not in a[2] and "=" not in a[2] and a[2].lower() in ("easing", "steady", "tightening"):
            a = a[:2] + [""] + a[2:]  # no parts given: the engine picks sensible ones
        for c in (a[2].split(",") if a[2] else []):
            c, _, with_ = c.partition("=")
            part, sev = c.rsplit(":", 1) if ":" in c else (c, "firm")
            hits.append({"part": part.strip(), "severity": sev.strip().lower(), "with": with_.strip()})
        b = {"action": "hold_start" if cmd == "hold" else "pin", "attacker": a[0], "defender": a[1],
             "hits": hits, "ramp": "steady"}
        if not " ".join(a[3:]).strip():
            a = a + ["pins them down" if cmd == "pin" else "locks a hold"]
        i = 3
        if len(a) > 3 and a[3].lower() in ("easing", "steady", "tightening"):
            b["ramp"], i = a[3].lower(), 4
        b["flavor"] = rest(i)
    elif cmd == "adjust":
        b = {"action": "hold_adjust", "hold_id": int(a[0])}
        for w in a[1:]:
            b["ramp" if w.lower() in ("easing", "steady", "tightening") else "severity"] = w.lower()
    elif cmd == "release":
        if a[0].isdigit():
            b = {"action": "hold_release", "hold_id": int(a[0]), "flavor": rest(1) or "released"}
        else:
            b = {"action": "hold_release", "attacker": a[0], "defender": a[1], "hold_id": 0,
                 "flavor": rest(2) or "released"}
    elif cmd == "move":
        # /move <att> <def> "<Move Name>" ["Part,Part,..."] [count]
        count = int(a[-1]) if len(a) > 3 and a[-1].isdigit() else 1
        # parts as one list ("Chest,Neck") or each in its own quotes ("Chest" "Neck"): both work
        tail = a[3:-1] if len(a) > 3 and a[-1].isdigit() else a[3:]
        parts = [x.strip() for t in tail for x in str(t).split(",") if x.strip()]
        b = {"action": "combo", "attacker": a[0], "defender": a[1], "move": a[2], "count": count,
             "part": parts[0] if parts else None,
             "hits": [{"defender": a[1], "part": x, "severity": "solid"} for x in parts], "flavor": a[2]}
    elif cmd == "eliminate":
        b = {"action": "eliminate", "attacker": a[0], "defender": a[0],
             "flavor": rest(1) or "faints, unable to continue"}
    elif cmd == "struggle":
        b = {"action": "struggle", "attacker": a[0], "defender": "", "flavor": rest(1) or "tries to break free"}
    elif cmd in ("pinsuccess", "pinescape"):
        hits = []
        if len(a) > 2:
            for c in a[2].split(","):
                c, _, with_ = c.partition("=")
                part, sev = c.rsplit(":", 1) if ":" in c else (c, "firm")
                hits.append({"part": part.strip(), "severity": sev.strip().lower(), "with": with_.strip()})
        b = {"action": "pin_success" if cmd == "pinsuccess" else "pin_escape", "attacker": a[0], "defender": a[1],
             "hits": hits, "flavor": " ".join(a[3:])}
    elif cmd == "quickpin":
        b = {"action": "quickpin", "attacker": a[0], "defender": a[1], "flavor": "goes for the cover"}
    elif cmd == "land":
        b = {"action": "land", "attacker": a[0], "defender": a[0], "landing": _impacts(a[1]),
             "flavor": " ".join(a[2:]), "tumble": _wants_tumble(a[1])}
    elif cmd == "grapple":
        # /grapple Nocturne Ripples "Left Upper Arm=her jaws" "catches her arm and hauls her in"
        spec = a[2] if len(a) > 2 and ("=" in a[2] or (eng is not None and _is_part(eng, a[1], a[2]))) else ""
        part, _, with_ = spec.partition("=")
        more = a[3:] if spec else a[2:]
        b = {"action": "grapple", "attacker": a[0], "defender": a[1], "part": part.strip() or None,
             "hits": [{"part": part.strip(), "severity": "light", "with": with_.strip()}] if part.strip() else [],
             "flavor": " ".join(more) or "takes hold of her"}
    elif cmd in MOVE_HER:
        # /situp Ripples   /rollover Nocturne Ripples "with a shove of her muzzle"
        who, target, more = _doer_and_target(eng, a, cmd)
        b = {"action": "breather", "attacker": who, "defender": target, "reposition": MOVE_HER[cmd],
             "flavor": " ".join(more) or MOVE_HER[cmd]}
    elif cmd in ("throw", "slam", "drag"):
        # /throw Ripples "a stalagmite=Upper Back+Head:heavy; the floor:solid"   /drag Nocturne Ripples "the cave wall"
        who, target, more = _doer_and_target(eng, a, cmd)
        landing, tumble = [], False
        if more and (re.search(r"[=:;]", more[0]) or re.match(r"(?i)(the|a|an|into|against|across|through|onto|tumble)\b", more[0])):
            tumble = cmd == "throw" and _wants_tumble(more[0])
            landing, more = _impacts(re.sub(r"(?i)^(into|against|across|through|onto)\s+", "", more[0]), mark=True), more[1:]
        for x in landing:
            if not x.pop("_given", True):   # no severity typed: a scrape along the ground is light, a slam is heavy
                x["severity"] = ("heavy" if cmd == "slam" else "solid" if cmd == "throw" else "light" if re.search(
                    r"floor|ground|stone|gravel|sand|water|pool|shallows", x["surface"], re.I) else "solid")
        b = {"action": cmd, "attacker": who, "defender": target, "landing": landing, "flavor": " ".join(more),
             "tumble": tumble}
    elif cmd == "heal":
        target = a[1]
        parts = target.lower() if target.lower() in ("all", "worst") else [x.strip() for x in target.split(",") if x.strip()]
        nums = []
        rest = a[2:]
        while rest and re.fullmatch(r"\d+(?:\.\d+)?", rest[0]) and len(nums) < 2:
            nums.append(float(rest.pop(0)))
        b = {"action": "heal", "attacker": a[0], "defender": a[0], "heal_parts": parts,
             "heal_amount": nums[0] if nums else 50, "heal_res": nums[1] if len(nums) > 1 else 0,
             "flavor": " ".join(rest)}
    elif cmd == "restore":
        b = {"action": "heal", "attacker": a[0], "defender": a[0], "heal_parts": [], "heal_amount": 0,
             "heal_health": float(a[1]), "flavor": " ".join(a[2:])}
    elif cmd == "charge":
        parts = [x.strip() for x in a[4].split(",") if x.strip()] if len(a) > 4 else []
        known = eng is not None and (eng.find_move(a[0], a[2]) is not None or eng.dex_move(a[2]) is not None)
        if not parts and eng is not None:
            body = eng.get(a[1])
            front = [p for p in body.parts if body_region_of(p) in ("chest", "belly", "shoulder")]
            parts = [eng.rng.choice(front or list(body.parts))]
        b = {"action": "combo", "attacker": a[0], "defender": a[1], "move": a[2] if known else "improvised",
             "improvised_name": a[2], "improvised_type": "Normal", "severity": "heavy", "charge_into": a[3],
             "part": parts[0] if parts else None,
             "hits": [{"defender": a[1], "part": x, "severity": "heavy"} for x in parts], "flavor": f"{a[2]} into {a[3]}"}
    elif cmd == "sustain":
        parts = [x.strip() for x in a[5].split(",")] if len(a) > 5 else []
        against = a[4] if len(a) > 4 else ""
        if against and not parts and eng is not None and _looks_like_parts(eng, a[1], against):
            parts, against = [x.strip() for x in against.split(",") if x.strip()], ""  # body parts, not a surface
        if against.strip().lower() in ("-", "none", "nothing", "no"):
            against = ""
        b = {"action": "combo", "attacker": a[0], "defender": a[1], "move": a[2], "sustain": int(a[3]),
             "pinned_against": against, "part": parts[0] if parts else None,
             "hits": [{"defender": a[1], "part": x, "severity": "solid"} for x in parts], "flavor": a[2]}
        if not parts:
            b["hits"] = [{"defender": a[1], "part": x, "severity": "solid"} for x in ("Chest", "Neck", "Stomach")]
    elif cmd == "recover":
        to = None
        if len(a) > 1:
            to = {"up": 99, "out": 0, "stirring": 1, "awake": 2}.get(a[1].lower(), int(a[1]) if a[1].isdigit() else None)
        b = {"action": "recover", "attacker": a[0], "defender": a[0], "to": to, "flavor": ""}
    elif cmd == "getup":
        b = {"action": "getup", "attacker": a[0], "defender": a[0],
             "count": int(a[1]) if len(a) > 1 and a[1].isdigit() else None, "flavor": ""}
    elif cmd == "roll":
        # /roll <att> <def> over|back|front|side|up
        word = (a[2].lower() if len(a) > 2 else "over")
        how = {"over": "roll over", "back": "onto her back", "up": "pick up", "lift": "pick up", "pickup": "pick up",
               "front": "onto her front", "belly": "onto her front", "side": "onto her side",
               "sit": "sit her up", "situp": "sit her up", "stand": "stand her up", "standup": "stand her up",
               "feet": "stand her up"}.get(word)
        if not how:
            raise ValueError("use /roll <attacker> <defender> over|back|front|side|sit|up|stand")
        b = {"action": "breather", "attacker": a[0], "defender": a[1], "reposition": how,
             "flavor": " ".join(a[3:]) or how}
    elif cmd == "down":
        facing = None
        if len(a) > 1 and a[1].lower() in ("up", "down", "side", "face-up", "face-down", "back", "front", "sit",
                                           "sitting"):
            facing, a = _facing_word(a[1]), a[:1] + a[2:]
        b = {"action": "down", "attacker": a[0], "defender": a[0], "facing": facing,
             "flavor": " ".join(a[1:]) or "goes down"}
    elif cmd == "wait":
        b = {"action": "breather", "flavor": rest(0) or "both fighters circle, catching their breath"}
    else:
        return None
    if "attacker" not in b:  # adjust/release/wait: attacker is whoever holds or anyone
        b["attacker"] = None
    b["_manual"] = True  # your commands skip the director's pin rules (testing and storytelling)
    return b


MY_SETTINGS = os.path.join(HERE, "my_settings.json")
_BARE_KEYS = {"damage_scale": ["damage", "damage_scale"], "resistance_scale": ["damage", "resistance_scale"],
              "words_per_beat": ["narration", "words_per_beat"], "seconds_per_beat": ["pin", "seconds_per_beat"],
              "duration_seconds": ["pin", "duration_seconds"]}


def _remember(keys, value):
    """Keep a setting you changed with a command in my_settings.json too. A new build replaces rules.json; it never
    touches my_settings.json, and that file is laid over rules.json every time the program starts."""
    try:
        data = {}
        if os.path.exists(MY_SETTINGS):
            with open(MY_SETTINGS, encoding="utf-8") as fh:
                data = json.load(fh)
        node = data
        for k in keys[:-1]:
            if not isinstance(node.get(k), dict):
                node[k] = {}
            node = node[k]
        node[keys[-1]] = value
        data.setdefault("balance", BALANCE)     # (what units these numbers are in: engine.migrate_settings)
        with open(MY_SETTINGS, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except (OSError, ValueError, TypeError) as e:
        print(f"[couldn't update my_settings.json: {e}]")


def _first_sentence(text, n=110):
    """The first sentence of a _comment, cut to n characters (for the /sets lists)."""
    t = " ".join(str(text or "").split())
    m = re.match(r"(.{12,}?[.!?])(?:\s|$)", t)
    t = m.group(1) if m else t
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def _rule_leaves(node, prefix=""):
    """Every setting under a rules section: (path, value, its note). A note is the "_<key>" line beside a setting,
    if it has one. Lists are one setting (set them as a whole)."""
    out = []
    for k, v in (node or {}).items():
        if k.startswith("_"):
            continue
        path = prefix + k
        if isinstance(v, dict):
            out += _rule_leaves(v, path + ".")
        else:
            out.append((path, v, node.get("_" + k) or ""))
    return out


def _set_line(path, value, note="", width=70):
    """'/set path value' ready to copy, with the setting's note after it when it has one."""
    line = f"  /set {path} {json.dumps(value, ensure_ascii=False)}"
    return line + (f"   ({_first_sentence(note, width)})" if note else "")


def _sets_text(rules, what=""):
    """/sets: the rules sections; one section's settings as /set lines; or every setting whose path or note has the
    word in it."""
    if not what:
        rows = []
        for k, v in rules.items():
            if k.startswith("_"):
                continue
            n = len(_rule_leaves(v)) if isinstance(v, dict) else 1
            note = _first_sentence((v.get("_comment") if isinstance(v, dict) else "") or rules.get("_" + k, ""), 80)
            rows.append(f"  {k:<16} {n:>4} setting{'s' if n != 1 else ' '}  {note}")
        return ("Every rule can be changed with /set <path> <value> (saved; add nosave for this session only).\n"
                "Sections:\n" + "\n".join(rows) + "\n/sets <section> lists one (e.g. /sets narration.rich), "
                "/sets <word> searches (e.g. /sets pin), /sets all [file] writes every one to a file.")
    try:
        node, key, _ = _rule_path(rules, what)
        val = node[key]
    except ValueError:
        val = None
    if isinstance(val, dict):
        rows = [_set_line(what + "." + p, v, n) for p, v, n in _rule_leaves(val)]
        # (the section's own explanation, whole: most settings are explained there rather than one by one)
        import textwrap
        note = " ".join(str(val.get("_comment") or "").split())
        head = what + (":\n" + textwrap.fill(note, 116, initial_indent="  ", subsequent_indent="  ") if note else "")
        return head + "\n" + "\n".join(rows)
    if val is not None:
        return _set_line(what, val, node.get("_" + key, ""), 400)
    word = what.lower()
    hits = [(p, v, n) for p, v, n in _rule_leaves(rules) if word in p.lower() or word in str(n).lower()]
    if not hits:
        return f"No setting has '{what}' in its name or note. /sets lists the sections."
    rows = [_set_line(p, v, n) for p, v, n in hits[:60]]
    more = f"\n  ... and {len(hits) - 60} more: narrow it down (e.g. /sets {hits[0][0].split('.')[0]})" if len(hits) > 60 else ""
    return f"Settings with '{what}' in them ({len(hits)}):\n" + "\n".join(rows) + more


def _sets_file(rules, path):
    """/sets all: every setting, section by section, as a Markdown file of /set lines with their notes."""
    out = ["# FightSim settings", "",
           "Every setting in rules.json. Change one in the game with `/set <path> <value>` (it is saved; add `nosave` to "
           "change it for this session only). The values shown are the ones in use when this file was written.", ""]
    for k, v in rules.items():
        if k.startswith("_"):
            continue
        out += [f"## {k}", ""]
        note = (v.get("_comment") if isinstance(v, dict) else "") or rules.get("_" + k, "")
        if note:
            out += [" ".join(str(note).split()), ""]
        leaves = _rule_leaves(v, k + ".") if isinstance(v, dict) else [(k, v, "")]
        for p, val, n in leaves:
            out.append(f"- `/set {p} {json.dumps(val, ensure_ascii=False)}`" + (f": {' '.join(str(n).split())}" if n else ""))
        out.append("")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out))
    except OSError as e:        # (open in another program, a folder that isn't there): an error message, not a crash
        raise ValueError(f"can't write {path}: {e}")
    return sum(1 for x in out if x.startswith("- `/set"))


def _settings_lines(data, prefix=""):
    out = []
    for k, v in (data or {}).items():
        if isinstance(v, dict) and v and prefix.count(".") < 3:
            out += _settings_lines(v, prefix + k + ".")
        else:
            out.append(f"  {prefix}{k} = {json.dumps(v, ensure_ascii=False)}")
    return out


def _save_rule(key, value):
    """Write damage_scale back into rules.json without disturbing the rest of the file."""
    import os, re
    if key in _BARE_KEYS:
        _remember(_BARE_KEYS[key], value)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text, n = re.subn(rf'("{key}"\s*:\s*)[-0-9.]+', lambda m: m.group(1) + repr(value), text, count=1)
    if n:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def _rule_path(rules, path):
    """'pin.struggle.escape_chance' -> (parent dict, key). Raises with the available keys if a step is wrong."""
    keys = [k for k in path.replace("->", ".").replace("/", ".").split(".") if k]
    node = rules
    for i, k in enumerate(keys[:-1]):
        if not isinstance(node, dict) or k not in node:
            raise ValueError(f"no rule '{'.'.join(keys[:i + 1])}'.{_rule_guess(rules, path)} Options: "
                             f"{', '.join(x for x in node if not x.startswith('_')) if isinstance(node, dict) else '(none)'}")
        node = node[k]
    if not isinstance(node, dict) or keys[-1] not in node:
        raise ValueError(f"no rule '{path}'.{_rule_guess(rules, path)} Options here: "
                         f"{', '.join(x for x in node if not x.startswith('_')) if isinstance(node, dict) else '(none)'}")
    return node, keys[-1], keys


def _rule_guess(rules, path):
    """" Did you mean finish.submission.enabled?" for a mistyped /set path (an underscore for a dot, a letter out),
    or "" when nothing is close."""
    import difflib
    found = []

    def walk(node, pre):
        for k, v in node.items():
            if str(k).startswith("_"):
                continue
            found.append(pre + k)
            if isinstance(v, dict):
                walk(v, pre + k + ".")
    walk(rules, "")
    flat = {p.replace("_", "").replace(".", ""): p for p in found}
    want = path.replace("->", ".").replace("/", ".")
    best = flat.get(want.replace("_", "").replace(".", "")) or next(iter(difflib.get_close_matches(want, found, 1, 0.8)), None)
    return f" Did you mean {best}?" if best and best != want else ""


def _parse_value(text):
    t = text.strip()
    if t.lower() in ("true", "on", "yes"):
        return True
    if t.lower() in ("false", "off", "no"):
        return False
    if t.lower() in ("null", "none"):
        return None
    try:
        return json.loads(t)
    except ValueError:
        return t


def _save_rules_key(keys, value):
    """Save one value (a list or dict too) into rules.json, rewriting the file as JSON."""
    if _save_rule_path(keys, value):
        return True
    path = os.path.join(HERE, "rules.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    node = data
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return True


# /effects and the window's Effects button (since build 306): each piece of window.alive, and the settling-in notes
EFFECTS = {"all": ["window", "alive", "enabled"], "breathing": ["window", "alive", "breathing"],
           "pulse": ["window", "alive", "pulse"], "impact": ["window", "alive", "impact"],
           "grey": ["window", "alive", "grey_in"], "grips": ["window", "alive", "grip_outline"],
           "monitor": ["window", "alive", "heart_monitor"], "settling": ["narration", "settling_in", "enabled"]}


def effects_state(rules):
    """[(effect, on)] for /effects and the window's Effects button ("all" is the switch for the cards' pieces)."""
    out = []
    for k, keys in EFFECTS.items():
        node = rules
        for x in keys[:-1]:
            node = (node or {}).get(x) or {}
        out.append((k, bool(node.get(keys[-1], True))))
    return out


def set_effect(rules, what, on):
    """Turn one effect on or off (or every one, with "all": the cards' pieces and the settling-in notes), in this
    session's rules and kept for next time (my_settings.json, as /set does)."""
    for k in (list(EFFECTS) if what == "all" else [what]):
        keys = EFFECTS[k]
        node = rules
        for x in keys[:-1]:
            node = node.setdefault(x, {})
        node[keys[-1]] = bool(on)
        _save_rule_path(keys, bool(on))


def _save_rule_path(keys, value):
    """Write one nested value back into rules.json, keeping the file's layout and comments.
    Returns False if it couldn't (the change still applies to this session)."""
    _remember(list(keys), value)
    if isinstance(value, (dict, list)):
        return False
    path = os.path.join(HERE, "rules.json")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    pos = 0
    for k in keys:  # walk down: each key is searched for after the previous one
        m = re.compile(r'"' + re.escape(k) + r'"\s*:\s*').search(text, pos)
        if not m:
            return False
        pos = m.end()
    m = re.compile(r'-?[0-9.]+(?:[eE][-+]?\d+)?|"(?:[^"\\]|\\.)*"|true|false|null').match(text, pos)
    if not m:
        return False
    text = text[:pos] + json.dumps(value, ensure_ascii=False) + text[m.end():]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True


def _move_text(m):
    fx = []
    for x in m.get("effects", []):
        fx.append(f"{x['chance'] * 100:.0f}% {x['status']} for {x['beats']} beat(s)" if x.get("status")
                  else f"{x['chance'] * 100:.0f}% {x['launch']}")
    rng_word = ("on herself or the arena" if m.get("target") == "self" else
                "ranged" if Engine.is_ranged(m) else "close")
    return (f"{m['name']} — {m['type']}, power {m['power']}, {m.get('target', 'targeted')}, {rng_word}"
            + (f"; {', '.join(fx)}" if fx else "") + f" — {m.get('about', '')}")


def split_commands(line):
    """'a && b && c' -> ['a', 'b', 'c'], ignoring && inside quotes."""
    out, cur, quote, i = [], "", None, 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif line.startswith("&&", i):
            out.append(cur.strip())
            cur, i = "", i + 2
            continue
        cur += ch
        i += 1
    out.append(cur.strip())
    return [x for x in out if x]


def _facing_word(word):
    w = str(word).lower().replace("_", "-")
    if w in ("down", "face-down", "facedown", "front", "belly", "prone"):
        return "face-down"
    if w in ("up", "face-up", "faceup", "back", "supine"):
        return "face-up"
    if w in ("side", "on-her-side", "left", "right"):
        return "on her side"
    if w in ("sit", "sitting", "situp", "sitting-up", "sat"):
        return "sitting up"
    raise ValueError("facing is down (face-down), up (on her back), side, or sit (sitting up)")


def _looks_like_parts(eng, defender, text):
    """True when a /sustain argument is a list of body parts rather than something to be pressed against."""
    try:
        names = [p.lower() for p in eng.get(defender).parts]
    except ValueError:
        return False
    bases = {re.sub(r"^(left|right) ", "", n) for n in names} | set(names)
    items = [x.strip().lower() for x in text.split(",") if x.strip()]
    hits = sum(1 for x in items if x in bases or x.rstrip("s") in bases)
    return bool(items) and hits * 2 >= len(items) and ("," in text or hits == len(items))


SAME_BEAT = re.compile(r"\s\+\s+(?=/)")  # "/charge ... + /move ...": both in ONE beat, in order


# /stop, typed in the window while /auto or /autofight runs: the run ends once the beat being written is finished
STOP = threading.Event()


def _stopped(s):
    """Has /stop been asked for? (Said once, and cleared.)"""
    if STOP.is_set():
        STOP.clear()
        s.out("\n(Stopped after this beat, as you asked. Everything so far is kept; /auto carries on.)")
        return True
    return False


def _autofight(s, a):
    """/autofight <fights> [aftermath beats] [fighter names]"""
    if not a or not a[0].isdigit():
        raise ValueError("Usage: /autofight <fights> [aftermath beats] [fighter names]   e.g. /autofight 3 4   or   "
                         "/autofight 3 2 Nocturne Ripples")
    count, rest = int(a[0]), a[1:]
    after = 2
    if rest and rest[0].isdigit():
        after, rest = int(rest[0]), rest[1:]
    names = [_clean_name(x).strip(",") for x in rest
             if x.strip(",").lower() not in ("", "and", "vs", "vs.", "v", "&", "against", "versus")]
    if names and names[0].lower() in ("all", "everyone"):
        names = list(s.eng.roster)
    if names:
        names = [s.eng.match_roster(n) for n in names]  # a wrong name stops it before anything is reset
        if len(set(names)) < 2:
            raise ValueError("a fight needs at least two different fighters")
    if count < 1:
        raise ValueError("at least one fight")
    s.auto_fights(count, after, names or None)


STRICT_BLOCK = {"eliminate", "pinsuccess", "pinescape", "land", "down", "getup", "heal", "restore", "face", "part",
                "fighter", "extendpin", "pinclock", "hazard", "undo", "energy"}


def _strict_check(s, cmd):
    """At the mercy of the dice (/play dice strict): commands that decide an outcome or change the fight's state
    are refused while you play a fighter."""
    if s.strict() and cmd in STRICT_BLOCK and not (s.over and cmd in ("getup", "recover")):
        raise ValueError(f"/{cmd} decides the outcome itself, and you're playing at the mercy of the dice "
                         f"(/play dice strict). /play dice fair allows it again.")


def _to_clipboard(text):
    """Copy text to the clipboard if the system has a way (Windows clip, macOS pbcopy, xclip): True if it did."""
    import subprocess
    for cmd, enc in ((["clip"], "utf-16"), (["pbcopy"], "utf-8"), (["xclip", "-selection", "clipboard"], "utf-8")):
        try:
            subprocess.run(cmd, input=text.encode(enc), check=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
    return False


def _polish_command(s, a):
    """/polish: narration.polish (a stronger online model improves the prose of each beat)."""
    cfg = s.eng.rules.setdefault("narration", {}).setdefault("polish", {})
    c = polish.cfg_of(s.eng.rules)
    sub = a[0].lower() if a else ""
    if not sub:
        key = polish.api_key(s.eng.rules)
        print(f"Polish: {'ON' if c['enabled'] else 'off'} · when: {c['when']} · service: {c['base_url']} · model: "
              f"{c['model'] or '(none chosen yet)'} · key: {'set' if key else 'not set'}\n"
              f"/polish key <key>, /polish models, /polish model <name>, /polish on|off, /polish when every|big, "
              f"/polish now, /polish copy, /polish paste, /polish prompt [edit|reset], /compare\n"
              f"Prompt: {'your own (polish_prompt.txt)' if polish.prompt_is_custom() else 'the built-in one'}"); return
    if sub == "prompt":
        # (since build 269) the instructions the editor gets: yours in polish_prompt.txt, or the built-in ones
        act = a[1].lower() if len(a) > 1 else ""
        if act == "reset":
            try:
                os.remove(polish.PROMPT_FILE)
            except OSError:
                pass
            print("The polish prompt is back to the built-in one (polish_prompt.txt removed)."); return
        if act == "edit":
            if not polish.prompt_is_custom():
                with open(polish.PROMPT_FILE, "w", encoding="utf-8") as fh:
                    fh.write(polish.SYSTEM + "\n")
            try:
                os.startfile(polish.PROMPT_FILE)      # (Windows: opens it in your text editor)
                opened = True
            except (AttributeError, OSError):
                opened = False
            print(f"The polish prompt is in {polish.PROMPT_FILE}" + (" (opened for you)" if opened else "")
                  + ". Change it, save it, and the next polish uses it. /polish prompt reset brings back the "
                    "built-in one. (The facts and the beat are added after it by the game; don't paste them in.)")
            return
        print(("Your own polish prompt (polish_prompt.txt):" if polish.prompt_is_custom() else
               "The built-in polish prompt (yours would go in polish_prompt.txt):") + "\n\n" + polish.system_prompt()
              + "\n\n/polish prompt edit to change it, /polish prompt reset to go back to the built-in one."); return
    if sub == "key":
        if len(a) < 2:
            raise ValueError("/polish key <your API key>")
        path = polish.save_key(a[1])
        print(f"Key saved to {path} (kept out of rules.json and git). Next: /polish models, then /polish model "
              f"<name>, then /polish on"); return
    if sub == "models":
        names = polish.list_models(s.eng.rules)
        print("Models the service offers:\n  " + "\n  ".join(names or ["(none listed)"])
              + "\nPick one with /polish model <name> (a larger model edits better)."); return
    if sub == "model":
        if len(a) < 2:
            raise ValueError("/polish model <name> (/polish models lists them)")
        cfg["model"] = a[1]
        saved = _save_rule_path(["narration", "polish", "model"], a[1])
        print(f"Polishing model: {a[1]} " + ("(saved)" if saved else "(this session)")); return
    if sub in ("on", "off"):
        cfg["enabled"] = sub == "on"
        saved = _save_rule_path(["narration", "polish", "enabled"], cfg["enabled"])
        print(f"Polish is {'ON' if cfg['enabled'] else 'OFF'} " + ("(saved)" if saved else "(this session)")
              + ("" if not cfg["enabled"] or (c["model"] and polish.api_key(s.eng.rules)) else
                 ". It still needs " + " and ".join(x for x, ok in (("a key (/polish key)", polish.api_key(s.eng.rules)),
                                                                    ("a model (/polish model)", c["model"])) if not ok)))
        return
    if sub == "when":
        if len(a) < 2 or a[1].lower() not in ("every", "big"):
            raise ValueError("/polish when every|big")
        cfg["when"] = a[1].lower()
        saved = _save_rule_path(["narration", "polish", "when"], cfg["when"])
        print(f"Polishing {'every beat' if cfg['when'] == 'every' else 'only the big moments'} "
              + ("(saved)" if saved else "(this session)")); return
    last = getattr(s, "_polish_last", None)
    if not last:
        raise ValueError("no beat to polish yet: play a beat first")
    if sub == "now":
        new = s._polish_now(last.get("local", ""))
        if new:
            s._replace_last_beat(new)
            print("\n" + new + "\n")
        return
    hist = [e for e in (getattr(s, "_polish_hist", None) or []) if e.get("fight") == last.get("fight")]
    if sub == "copy" and len(a) > 1:
        # (since build 271) several beats at once, by beat number: /polish copy 5-9, /polish copy 7,
        # /polish copy last 4, /polish copy all (up to batch_max of them)
        cap = int(polish.cfg_of(s.eng.rules).get("batch_max", 6))
        spec = " ".join(a[1:]).lower().replace(" ", "")
        if spec == "all":
            pick = hist
        elif spec.startswith("last") and spec[4:].isdigit():
            pick = hist[-int(spec[4:]):]
        elif re.fullmatch(r"\d+(?:-\d+)?", spec):
            lo, _, hi = spec.partition("-")
            lo, hi = int(lo), int(hi or lo)
            pick = [e for e in hist if lo <= int(e.get("turn") or 0) <= hi]
        else:
            raise ValueError("/polish copy 5-9 (beats 5 to 9), /polish copy 7, /polish copy last 4, /polish copy all")
        if not pick:
            have = ", ".join(str(e.get("turn")) for e in hist) or "none yet"
            raise ValueError(f"no such beats to copy (the beats this game has kept for polishing: {have})")
        if len(pick) > cap:
            print(f"(that is {len(pick)} beats: only the first {cap} go in this request, polish.batch_max; copy the "
                  f"rest after)")
            pick = pick[:cap]
        req = polish.batch_request([(int(e.get("turn") or 0), e.get("shown") or e.get("local", ""),
                                     e.get("facts") or [], e.get("prior")) for e in pick], s.eng.rules)
        with open(polish.REQUEST_FILE, "w", encoding="utf-8") as fh:
            fh.write(req)
        try:
            open(polish.REPLY_FILE, "a", encoding="utf-8").close()
        except OSError:
            pass
        clip = _to_clipboard(req)
        turns = ", ".join(str(e.get("turn")) for e in pick)
        print(f"The request for beats {turns} ({len(req.split())} words) is in {polish.REQUEST_FILE}"
              + (" and on your clipboard" if clip else "")
              + f". Paste it into a NEW Venice chat, copy its whole answer into {polish.REPLY_FILE} (replacing what "
                f"is there), save it, and type /polish paste. Each beat goes back to its own place by its number, "
                f"and each is checked and kept or not by itself."); return
    if sub == "copy":
        req = polish.request_text(last.get("local", ""), last.get("facts") or [], last.get("prior"), s.eng.rules)
        with open(polish.REQUEST_FILE, "w", encoding="utf-8") as fh:
            fh.write(req)
        try:
            open(polish.REPLY_FILE, "a", encoding="utf-8").close()
        except OSError:
            pass
        clip = _to_clipboard(req)
        print(f"The request for beat {last.get('turn')} is in {polish.REQUEST_FILE}"
              + (" and on your clipboard" if clip else "")
              + f". Paste it into Venice's chat, copy its whole answer into {polish.REPLY_FILE} (replacing what is "
                f"there), save it, and type /polish paste. The fight waits here meanwhile."); return
    if sub == "paste":
        try:
            with open(polish.REPLY_FILE, encoding="utf-8") as fh:
                reply = fh.read()
        except OSError:
            raise ValueError(f"no {polish.REPLY_FILE}: put the answer in it first (/polish copy makes it)")
        if not reply.strip():
            raise ValueError(f"{polish.REPLY_FILE} is empty: paste the answer into it and save it first")
        parts = polish.split_batch(reply)
        target = None
        if len(a) > 1 and a[1].isdigit():
            # /polish paste 7: an answer with no beat markers, for beat 7
            target = next((e for e in reversed(hist) if int(e.get("turn") or 0) == int(a[1])), None)
            if target is None:
                raise ValueError(f"beat {a[1]} isn't one this game has kept for polishing")
        if parts:
            # several beats (or one, marked): each judged against its own local version and put back by its number
            kept, done = 0, 0
            for k, text_ in sorted(parts.items()):
                e = next((x for x in reversed(hist) if int(x.get("turn") or 0) == k), None)
                if e is None:
                    print(f"[polish not used (beat {k}): this game hasn't kept that beat for polishing]")
                    continue
                done += 1
                new = s._polish_now(e.get("local", ""), reply=text_, entry=e)
                if new:
                    s._replace_last_beat(new, entry=e)
                    kept += 1
            print(f"{kept} of {done} beats polished. /exportfight shows the whole fight with them in.")
            try:
                with open(polish.REPLY_FILE, "w", encoding="utf-8") as fh:
                    fh.write("")
            except OSError:
                pass
            return
        if target is not None and target is not last:
            new = s._polish_now(target.get("local", ""), reply=reply, entry=target)
            if new:
                s._replace_last_beat(new, entry=target)
                print("\n" + new + "\n")
            return
        new = s._polish_now(last.get("local", ""), reply=reply)
        if new:
            s._replace_last_beat(new)
            print("\n" + new + "\n")
            try:
                with open(polish.REPLY_FILE, "w", encoding="utf-8") as fh:
                    fh.write("")       # (emptied, so the next /polish paste can't reuse this answer by mistake)
            except OSError:
                pass
        return
    raise ValueError("/polish [key|models|model|on|off|when|now|copy|paste|prompt]")


def _unbracket(text):
    """(since build 278) Square brackets typed round an argument, as the usage lines show the optional ones
    ("/sustain Seraphina Ripples "Hydro Pump" 4 [Tree] [Stomach, chest]"), count as quotes: [Stomach, chest] is the
    one argument "Stomach, chest"."""
    return re.sub(r'\[([^\[\]"]*)\]', lambda m: '"' + m.group(1).strip() + '"', text)


def handle_command(s, line):
    if re.search(r"\s&&\s+/", line):
        # (since build 276) "/stop && /plan dominate Ripples": several commands typed on one line run one after another
        for piece in re.split(r"\s+&&\s+(?=/)", line.strip()):
            try:
                handle_command(s, piece.strip())
            except ValueError as e:
                print(f"Error ({piece.strip().split()[0]}): {e}")
        return
    if SAME_BEAT.search(line):
        for piece in SAME_BEAT.split(line)[:3]:
            bits = shlex.split(_unbracket(piece.strip()[1:]))
            if bits:
                _strict_check(s, bits[0].lower())
        # several attack commands joined with " + " happen in the same beat (up to three), so a follow-up can land
        # before the first one's consequences play out: before a charged fighter crumples, say
        beats = []
        for piece in SAME_BEAT.split(line)[:3]:
            bits = shlex.split(_unbracket(piece.strip()[1:]))
            if not bits:
                continue
            b = manual_beat(bits[0].lower(), bits[1:], s.eng)
            if b is None:
                raise ValueError(f"/{bits[0]} can't share a beat: only attack commands can be joined with + "
                                 f"(/strike, /move, /charge, /combo, /sustain, /hold, /pin, /land, /down, /situp, "
                                 f"/pickup, /throw, /slam, /drag...)")
            if b.get("attacker") is None:
                b["attacker"] = s.eng.active()[0].name
            beats.append(b)
        if beats:
            s.play_beat(manual=beats)
        return
    # (backslashes kept: a Windows path such as C:\Users\night\out.md must come through whole)
    parts = shlex.split(_unbracket(line[1:]).replace("\\", "\\\\"))
    if not parts:
        return
    cmd, a = parts[0].lower(), parts[1:]
    _strict_check(s, cmd)
    if cmd in ("quit", "exit"):
        return "quit"
    if cmd == "help":
        print(help_text(" ".join(a))); return
    if cmd == "play":
        names = [f.name for f in s.eng.fighters.values()]
        if not a:
            print(("You play: " + ", ".join(s.players) + ". The director runs the rest.") if s.players else
                  "You aren't playing anyone: the director runs every fighter. /play <name> [name...] or /play all")
            return
        if a[0].lower() == "dice":
            if len(a) < 2:
                print(f"Dice for the fighters you play: {s.dice_mode()} ({s.DICE_MODES[s.dice_mode()]}).\n"
                      "  /play dice fair     the dice decide; /commands can still force outcomes (default)\n"
                      "  /play dice strict   at the mercy of the dice: no forcing, pins and getting up only when "
                      "the dice allow, no /undo\n"
                      "  /play dice free     ignore the dice for your fighters: their own tries always work")
                return
            mode = a[1].lower()
            if mode not in s.DICE_MODES:
                raise ValueError("/play dice fair | strict | free")
            s.eng.rules.setdefault("play", {})["dice"] = mode
            _save_rule_path(["play", "dice"], mode)
            s.eng._windows_ready = False   # openings are rolled again under the new rule
            s.sync_dice()
            print(f"Dice for the fighters you play: {mode}: {s.DICE_MODES[mode]} (saved)")
            return
        if a[0].lower() == "off":
            s.players, s.eng._windows_ready = [], False
            s.sync_dice()
            print("Play-as is off: the director runs every fighter again."); return
        if a[0].lower() == "all":
            want = [f.name for f in s.eng.active()]
        else:
            want = []
            for x in a:
                n = next((m for m in names if m.lower() == _clean_name(x).lower()), None)
                if n is None:
                    raise ValueError(f"no fighter called {x} (in this fight: {', '.join(f.name for f in s.eng.active())})")
                want.append(n)
        s.players, s.eng._windows_ready = want, False
        s.sync_dice()
        print(f"Dice: {s.dice_mode()} ({s.DICE_MODES[s.dice_mode()]}). /play dice to change it.")
        if not s.use_llm:
            print("(The director is off (--no-llm), so your moves can only be /commands for now.)")
        print("You play: " + ", ".join(want) + (". Every fighter is yours." if len(want) >= len(s.eng.active()) else
                                                ". The director runs the rest.")
              + " Each beat you're asked for their moves; /commands still work for direct control. /play off to stop.")
        return
    if cmd in ("traits", "profile", "profiles"):
        # (since build 280) how each fighter fights: her traits, her quirks, her style and favourite moves
        e = s.eng
        want = [e.get(x) for x in a] if a else e.active()
        for f in want:
            tr = ", ".join(f"{k} ×{v:g}" for k, v in (f.traits or {}).items() if float(v) != 1.0) or "all as normal"
            qs = ", ".join(q + ("" if e.quirk(f, q) else " (off)") for q in (f.quirks or [])) or "none"
            fav = ", ".join(f"{m} ×{w:g}" for m, w in sorted((f.favors or {}).items(), key=lambda kv: -float(kv[1])))
            print(f"{f.name}: traits {tr}\n   quirks: {qs}" + (f"\n   style: {f.style}" if f.style else "")
                  + (f"\n   favours: {fav}" if fav else ""))
            if cmd != "traits":
                # (since build 281) who she is: personality, history, and what the others are to her
                print((f"   personality: {f.personality}\n" if f.personality else "")
                      + (f"   history{' (has fought before)' if f.veteran else ''}: {f.history}\n" if f.history else "")
                      + "".join(f"   {o} to her: {r}\n" for o, r in (f.relationships or {}).items()), end="")
        if not e.traits_cfg():
            print("(traits are switched off: /set traits.enabled true)")
        return
    if cmd == "explain":
        # (since build 312) the window's hover tips, as text: every status on her, and her vitals
        import explain, cards
        word = " ".join(a).strip().lower().replace(" ", "_")
        if word and word in s.eng.STATUS_LOOK:
            print(explain.status_text(word, None, s.eng.rules)); return
        snap = fight_snapshot(s)["fighters"]
        rows = [f for f in snap if not word or f["name"].lower() == _clean_name(" ".join(a)).lower()]
        if not rows:
            raise ValueError(f"no fighter or status called '{' '.join(a)}' (statuses: "
                             f"{', '.join(sorted(s.eng.STATUS_LOOK))})")
        for f in rows:
            m = cards.tap_meter(f) or {}
            print(f"=== {f['name']} ===\n" + explain.statuses_text(f.get("status") or {}, s.eng.rules) + "\n\n"
                  + explain.vitals_text(cards.body_signs(f, cards.alive_opts(s.eng.rules)), m.get("vitals")) + "\n")
        return
    if cmd == "status":
        if not a:
            print(s.display.status_brief(s.eng)); return
        print(s.display.status(s.eng, None if a[0].lower() in ("full", "all") else _clean_name(a[0]))); return
    if cmd == "pinfade":
        cfg = s.eng.rules.setdefault("pin", {}).setdefault("fade", {})
        if not a:
            on = cfg.get("enabled", True)
            running = [f"  {' and '.join(s.eng.pin_members(p))} on {p['defender']}: going under {p.get('fade', 0):g}% "
                       f"after {p.get('beats', 0)} beat(s)" for p in s.eng.pins.values()]
            print(("A pin has NO fixed length: each beat brings the pinned fighter closer to passing out by a varying "
                   f"amount. It usually takes about {cfg.get('typical_beats', 6):g} beats (each beat is worth between "
                   f"{100 * (1 - cfg.get('spread', 0.55)):.0f}% and {100 * (1 + cfg.get('spread', 0.55)):.0f}% of an "
                   "average one), never fewer than "
                   f"{cfg.get('min_beats', 3):g}. Slower when she breaks loose for a moment or is still above half "
                   "strength; faster in a double pin or with her health below zero. The story has no clock and no "
                   "seconds.\n" if on else
                   "Pins run on the old clock: a fixed length (/pinlength), with the seconds marked in the story.\n")
                  + ("\n".join(running) + "\n" if running else "")
                  + "/pinfade <beats> [spread 0-0.95]   e.g. /pinfade 8 0.6      /pinfade off = the old fixed clock      "
                    "/pinfade on"); return
        word = a[0].lower()
        if word in ("on", "off"):
            cfg["enabled"] = word == "on"
            _save_rule_path(["pin", "fade", "enabled"], word == "on")
            print("Pins: no fixed length, no clock in the story (saved)" if word == "on" else
                  "Pins: the old fixed clock, seconds marked in the story (saved)"); return
        beats = float(word)
        if beats < 1:
            raise ValueError("the usual number of beats must be 1 or more")
        said = [f"usual length {cfg.get('typical_beats', 6):g} → {beats:g} beats"]
        cfg["typical_beats"] = beats
        _save_rule_path(["pin", "fade", "typical_beats"], beats)
        if len(a) > 1:
            spread = float(a[1])
            if not 0 <= spread <= 0.95:
                raise ValueError("spread is between 0 (every pin the same length) and 0.95")
            said.append(f"spread {cfg.get('spread', 0.55):g} → {spread:g}")
            cfg["spread"] = spread
            _save_rule_path(["pin", "fade", "spread"], spread)
        print("Pin length: " + ", ".join(said) + " (saved; kept across new builds in my_settings.json)"); return
    if cmd in ("extendpin", "pinclock") and s.eng.fade_mode():
        nums = [x for x in a if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", x)]
        pins = list(s.eng.pins.values())
        if not pins:
            raise ValueError("no pin is running")
        if not nums:
            raise ValueError(f"pins have no fixed clock now. /{cmd} <percent> moves how far gone the pinned fighter is: "
                             f"/extendpin 30 gives her 30 points back, /pinclock 80 sets her at 80% of the way to "
                             f"passing out. (/pinfade off brings the fixed clock back.)")
        names = [_clean_name(x) for x in a if x not in nums]
        pin = next((p for p in pins if not names or {p["attacker"].lower(), p["defender"].lower()} >= {n.lower() for n in names}), None)
        if pin is None:
            raise ValueError("no pin is running between " + " and ".join(names))
        s.push_history()
        old = float(pin.get("fade", 0.0))
        v = float(nums[0])
        pin["fade"] = max(0.0, min(99.0, old - v if cmd == "extendpin" else v))
        print(f"📌 Pin: {pin['attacker']} on {pin['defender']} — going under {old:g}% → **{pin['fade']:g}%** "
              f"(she passes out at 100%)")
        s.autosave(); return
    if cmd in ("extendpin", "pinclock"):
        nums = [x for x in a if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", x)]
        names = [_clean_name(x) for x in a if x not in nums]
        if not nums:
            raise ValueError(f"Usage: /{cmd} [pinner pinned] <seconds>   e.g. /{cmd} 30")
        pins = [p for p in s.eng.pins.values() if not names or
                {p["attacker"].lower(), p["defender"].lower()} >= {n.lower() for n in names}]
        if not pins:
            raise ValueError("no pin is running" + (f" between {' and '.join(names)}" if names else ""))
        if len(pins) > 1:
            raise ValueError("several pins are running; name them: /" + cmd + " <pinner> <pinned> <seconds>")
        pin = pins[0]
        s.push_history()
        old = pin["duration"]
        secs = float(nums[0])
        new = old + secs if cmd == "extendpin" else secs
        new = int(new) if new == int(new) else new
        if new <= pin["seconds"]:
            s.history.pop()
            raise ValueError(f"the pin is already at {pin['seconds']} s; the new total must be later than that")
        pin["duration"] = new
        print(f"📌 Pin clock: {pin['attacker']} on {pin['defender']} — {pin['seconds']} / {old} s → "
              f"{pin['seconds']} / **{new}** s (this pin only; /pinlength changes the default)")
        s.autosave(); return
    if cmd == "plan":
        if not a:
            pl = s.eng.plan
            print(f"Story plan: {pl.get('shape') or 'none'}" + (f", winner {pl['winner']}" if pl.get("winner") else "")
                  + f"; targeting {pl.get('targeting') or 'auto'}\nUse: /plan close [winner] | /plan dominate <name> | "
                  "/plan comeback <name> | /plan even | /plan winner <name> | /plan off"); return
        shape = a[0].lower()
        if shape in ("off", "none", "clear"):
            s.eng.plan.pop("shape", None); s.eng.plan.pop("winner", None)
            print("Story plan cleared (the director decides freely; targeting setting kept)."); s.autosave(); return
        if shape not in ("close", "dominate", "comeback", "even", "winner"):
            raise ValueError("use /plan close [winner] | dominate <name> | comeback <name> | even | winner <name> | off")
        who = s.eng.get(_clean_name(a[1])).name if len(a) > 1 else ""
        if shape in ("dominate", "comeback", "winner") and not who:
            raise ValueError(f"/plan {shape} needs a fighter's name")
        if shape == "winner":
            s.eng.plan["winner"] = who
        else:
            s.eng.plan["shape"] = shape
            s.eng.plan["winner"] = who
        print(f"Story plan: {s.eng.plan.get('shape', 'none')}" + (f", {who} to win" if who else "")
              + ". (A nudge for the director; the dice still decide.)"); s.autosave(); return
    if cmd in ("posture", "where"):
        a = []
        cmd = "face"
    if cmd in ("face", "facing"):
        if not a:
            print("Posture right now:\n" + "\n".join(f"  {f.name}: {s.eng.posture_text(f.name)}"
                                                    for f in s.eng.fighters.values()) +
                  "\nUse: /face <fighter> down|up|side|sit   (only for a fighter on the ground)")
            return
        f = s.eng.get(a[0])
        if s.eng.facing_of(f.name) is None and f.name not in s.eng.downed:
            raise ValueError(f"{f.name} is on her feet. Use /down {f.name} {a[1] if len(a) > 1 else 'down'} to put her down that way")
        if len(a) < 2:
            print(f"{f.name} is {s.eng.posture_text(f.name)}"); return
        if _facing_word(a[1]) == "sitting up" and any(p["defender"] == f.name for p in s.eng.pins.values()):
            raise ValueError(f"{f.name} is pinned flat: she can't sit up until the pin ends")
        s.push_history()
        s.eng.facing[f.name] = _facing_word(a[1])
        moved = s.eng._settle_facing(f.name)  # presses on the side now against the ground move to the exposed side
        print(f"{f.name} is now {s.eng.facing[f.name]} (pins and the story will follow)"
              + (f"; presses moved: {', '.join(moved)}" if moved else ""))
        s.autosave(); return
    if cmd in ("reason", "reasons", "why"):
        import reasons as R
        cfg = s.eng.rules.setdefault("story", {}).setdefault("reasons", {})
        rs = R.load(os.path.join(HERE, cfg.get("file", "fight_reasons.txt")))
        w = a[0].lower() if a else ""
        if not a:
            r = s.fight_reason()
            if not r:
                print("No reason for this fight (" + ("off: /reason on turns it on, /reason list shows them"
                      if getattr(s, "reason_off", False) or not cfg.get("enabled", False)
                      else "it's for one-on-one fights") + ")."); return
            print(f"Why they fight: {r.get('title', '')} [{r.get('id', '')}]\n  {r['setup']}\n  "
                  f"Holder: {r['holder_name']}. Comer: {r['comer_name']}."
                  + (f"\n  Stakes: {r['stakes']}" if r.get("stakes") else "")
                  + "\nUse: /reason list   /reason <number or id> [holder name]   /reason swap   /reason new   "
                    "/reason \"your own reason\"   /reason off|on"); return
        if w == "list":
            here = s.eng.scene_name or ""
            for k, x in enumerate(rs, 1):
                print(f"  {k:>2}. {x.get('title', x['id'])} [{x['id']}]" + ("" if R.fits(x, here) else "  (not for this arena)"))
            print("Choose with /reason <number> (it takes effect now, for this fight's story)."); return
        if w in ("off", "on"):
            s.reason_off = w == "off"
            cfg["enabled"] = w == "on"
            _save_rules_key(["story", "reasons", "enabled"], w == "on")
            print(f"Fight reasons {w} (saved)."); return
        if w == "swap":
            r = s.fight_reason()
            if not r:
                raise ValueError("no reason to swap")
            s.reason_pick = {"id": r["id"], "holder": r["comer_name"]} if r["id"] != "custom" else \
                dict(s.reason_pick or {}, holder=r["comer_name"])
            s.reason = None
            r = s.fight_reason()
            print(f"Swapped: {r['holder_name']} is now the holder, {r['comer_name']} the comer."); return
        if w in ("new", "random", "reroll"):
            s.reason_pick, s.reason = None, None
            r = s.fight_reason()
            print(f"New reason: {r.get('title', '')}" if r else "No reason fits."); return
        hold = None
        if len(a) > 1:
            try:
                hold = s.eng.get(a[-1]).name
                a = a[:-1]
            except ValueError:
                pass
        text = " ".join(a).strip().strip('"')
        x = None
        if text.isdigit() and 1 <= int(text) <= len(rs):
            x = rs[int(text) - 1]
        else:
            x = next((y for y in rs if y["id"] == text.lower() or y.get("title", "").lower() == text.lower()), None)
        if x is not None:
            s.reason_pick = {"id": x["id"], "holder": hold}
        elif len(text.split()) >= 4:
            s.reason_pick = {"custom": text, "holder": hold}
        else:
            raise ValueError(f"no reason called '{text}' (/reason list); a reason of your own needs a sentence or more")
        s.reason, s.reason_off = None, False
        if not cfg.get("enabled", False):    # choosing one turns reasons on
            cfg["enabled"] = True
            _save_rules_key(["story", "reasons", "enabled"], True)
        r = s.fight_reason()
        print(f"This fight's reason: {r.get('title') or 'your own'}. Holder {r['holder_name']}, comer {r['comer_name']}."
              " The story picks it up from the next passage."); s.autosave(); return
    if cmd in ("interlude", "lull"):
        cfg = s.eng.rules.setdefault("narration", {}).setdefault("interlude", {})
        if not a:
            print(f"Interludes (a long passage where the fight draws breath: thoughts, the body taking stock, the place): "
                  f"{'on' if cfg.get('enabled', True) else 'off'}, chance {cfg.get('chance', 0.1)} a beat, about "
                  f"{cfg.get('words', 900)} words, at least {cfg.get('min_gap', 4)} beats apart, not before beat "
                  f"{cfg.get('from_beat', 3)}.\nUse: /interlude now [words] [\"what to dwell on\"]   /interlude next   "
                  "/interlude chance <0-1>   /interlude words <n>   /interlude gap <beats>   /interlude on|off"); return
        w = a[0].lower()
        if w in ("now", "force"):
            rest = a[1:]
            words = int(rest[0]) if rest and rest[0].isdigit() else None
            direction = " ".join(rest[1:] if words else rest).strip().strip('"')
            s.interlude(words, direction); return
        if w == "next":
            s.interlude_next = True
            print("An interlude will follow the next beat."); return
        if w in ("on", "off"):
            cfg["enabled"] = w == "on"
            _save_rules_key(["narration", "interlude", "enabled"], w == "on")
            print(f"Interludes {w} (saved). /interlude now still writes one when you ask."); return
        if w in ("chance", "words", "gap") and len(a) > 1:
            key = {"chance": "chance", "words": "words", "gap": "min_gap"}[w]
            val = float(a[1].rstrip("%")) / (100 if a[1].endswith("%") else 1) if w == "chance" else int(a[1])
            if w == "chance" and not 0 <= val <= 1:
                raise ValueError("a chance between 0 and 1")
            cfg[key] = val
            _save_rules_key(["narration", "interlude", key], val)
            print(f"Interlude {w} {val} (saved)"); return
        raise ValueError("use /interlude now|next|chance|words|gap|on|off")
    if cmd in ("budget", "beatbudget"):
        n = s.eng.rules.setdefault("narration", {})
        if not a:
            print(f"Beat time budget: {n.get('beat_budget_minutes', 6)} min (past it, the optional extra passes stop: a "
                  "second whole rewrite, wording-only fixes, the second reading; nothing is shortened). Timing line: "
                  f"{'on' if n.get('show_timing', True) else 'off'}.\nUse: /budget <minutes|off>   /budget timing on|off"); return
        if a[0].lower() == "timing":
            on = len(a) < 2 or a[1].lower() in ("on", "yes", "true")
            n["show_timing"] = on
            _save_rules_key(["narration", "show_timing"], on)
            print(f"Timing line {'on' if on else 'off'} (saved)"); return
        val = 0.0 if a[0].lower() in ("off", "none", "0") else float(a[0].rstrip("m"))
        if val < 0:
            raise ValueError("minutes, 0 or more")
        n["beat_budget_minutes"] = val
        _save_rules_key(["narration", "beat_budget_minutes"], val)
        print(f"Beat time budget {'off' if not val else f'{val:g} min'} (saved)"); return
    if cmd in ("length", "fightlength"):
        fl = s.eng.rules.setdefault("fight_length", {})
        presets = {k: v for k, v in (fl.get("presets") or {}).items() if not str(k).startswith("_")}
        base = fl.get("base") or {"loss_per_damage_point": 0.46, "resistance_scale": 1.0}
        now = (s.eng.rules["health"].get("loss_per_damage_point"), s.eng.rules["damage"].get("resistance_scale"))
        if not a:
            cur = next((k for k, v in presets.items() if (round(base["loss_per_damage_point"] * v["health_loss"], 4),
                                                         round(base["resistance_scale"] * v["wear"], 3)) == now), None)
            print(f"Fight length: {('about ' + cur + ' beats') if cur else 'custom'} (health per damage point {now[0]}, "
                  f"wear x{now[1]}). Presets: {', '.join(presets)} beats (default {fl.get('default', '60')}).\n"
                  "Use: /length <beats|default>   e.g. /length 35. Fighters lose health and wear down faster; "
                  "pin openings and escapes are unchanged, so a pin simply wins sooner."); return
        w = a[0].lower().rstrip("beats").strip() if a[0].lower() not in ("default", "normal", "reset") else str(fl.get("default", "60"))
        if w not in presets:
            raise ValueError(f"no preset for {a[0]}: choose one of {', '.join(presets)} (beats), or default")
        v = presets[w]
        hl, wear = round(base["loss_per_damage_point"] * v["health_loss"], 4), round(base["resistance_scale"] * v["wear"], 3)
        s.eng.rules["health"]["loss_per_damage_point"] = hl
        s.eng.rules["damage"]["resistance_scale"] = wear
        _save_rules_key(["health", "loss_per_damage_point"], hl)
        _save_rules_key(["damage", "resistance_scale"], wear)
        print(f"Fight length: about {w} beats (saved). Health per damage point {hl}, wear x{wear}. From simulated fights: "
              f"{v.get('_measured', '')}"); return
    if cmd in ("pins", "pinrate"):
        pu = s.eng.rules.setdefault("director", {}).setdefault("pin_urge", {})
        if not a:
            print(f"Pin frequency: x{pu.get('scale', 1.0)} (0.5 = the default, about 5 pins a fight; 1 = twice as many "
                  "openings, about 8 a fight; 0 = the director never starts a pin, your /pin still does).\n"
                  "Use: /pins <number|off|default>   e.g. /pins 0.5"); return
        w = a[0].lower().lstrip("x")
        val = 0.5 if w in ("default", "normal", "reset") else 0.0 if w in ("off", "none", "never") else \
            float(w.rstrip("%")) / (100 if w.endswith("%") else 1)
        if not 0 <= val <= 5:
            raise ValueError("a multiplier between 0 and 5 (0.5 = the default)")
        pu["scale"] = val
        _save_rules_key(["director", "pin_urge", "scale"], val)
        print(f"Pin frequency x{val} (saved). Pin openings and pile-ons come {'at the default rate' if val == 0.5 else f'{val / 0.5:g} times as often as the default'}."); return
    if cmd in ("weakspots", "weakspot"):
        cfg = s.eng.rules.setdefault("director", {})
        if not a:
            print(f"Weak-spot nudge: {cfg.get('weak_spot_chance', 0.2)} per beat (the chance the director is pointed at "
                  f"one soft or worn-down part, just that once).\nWorked (a run of blows on one weak spot, a group of parts, or a few weak spots): {cfg.get('weak_spot_repeat', 0.4)} of those nudges; /weakspots worked <0-1>.\nUse: /weakspots <0-1|off>   For weak spots ALL the "
                  "time: /focus vulnerable (soft places) or /focus injured (what is already hurt)."); return
        key = "weak_spot_chance"
        if a[0].lower() in ("worked", "repeat", "runs") and len(a) > 1:
            key, a = "weak_spot_repeat", a[1:]
        val = 0.0 if a[0].lower() in ("off", "none", "never") else float(a[0].rstrip("%")) / (100 if a[0].endswith("%") else 1)
        if not 0 <= val <= 1:
            raise ValueError("a chance between 0 and 1 (or a percent, like 30%)")
        cfg[key] = val
        _save_rules_key(["director", key], val)
        print(f"Weak-spot nudge {val} per beat (saved)" if key == "weak_spot_chance" else
              f"Worked weak spots: {val} of the nudges are for a run of blows (saved)"); return
    if cmd == "focus":
        cfg = s.eng.rules.setdefault("director", {})
        focus = cfg.setdefault("focus", {})
        zones_cfg = {k for k in s.eng.rules.get("body_zones", {}) if not k.startswith("_")} | {"injured"}
        names = {f.name.lower(): f.name for f in s.eng.fighters.values()}
        if not a:
            lines = [f"  {('everyone' if k == '*' else k)}: {' + '.join(v)}" for k, v in focus.items() if v]
            print("Target focus: " + ("\n" + "\n".join(lines) if lines else "none (attacks go anywhere)")
                  + f"\nStrength {cfg.get('focus_strength', 0.6)} (0 = nudge only, 1 = always moved onto the zone)."
                  + f"\nZones: {', '.join(sorted(zones_cfg))}   (combine them: /focus core head)"
                  + "\nUse: /focus [fighter] <zones...|off>   /focus strength <0-1>")
            return
        if a[0].lower() == "strength":
            val = float(a[1])
            if not 0 <= val <= 1:
                raise ValueError("strength is between 0 and 1")
            cfg["focus_strength"] = val
            _save_rules_key(["director", "focus_strength"], val)
            print(f"Focus strength {val} (saved to rules.json)"); return
        who = "*"
        try:
            who = s.eng.get(a[0]).name  # a fighter's own focus
            a = a[1:]
        except ValueError:
            pass
        if not a:
            raise ValueError("name the zones: " + ", ".join(sorted(zones_cfg)) + "  (or off)")
        if a[0].lower() in ("off", "none", "any", "anywhere"):
            if who == "*":
                focus.clear()          # off for everyone: every fighter's own focus too
            elif "*" in focus:
                focus[who] = []        # her own "off" outranks the focus set for everyone
            else:
                focus.pop(who, None)
            msg = "off"
        else:
            zones = [z.lower() for z in " ".join(a).replace("+", " ").replace(",", " ").split()]
            zones = ["injured" if z in ("hurt", "wounded", "injuries", "weakened", "weak") else
                     "neck" if z in ("throat", "throats", "necks") else "vulnerable" if z in ("weak-spots", "soft") else z
                     for z in zones]
            bad = [z for z in zones if z not in zones_cfg]
            if bad:
                raise ValueError(f"unknown zone(s) {', '.join(bad)}. Zones: {', '.join(sorted(zones_cfg))} "
                                 f"(add your own under body_zones in rules.json)")
            focus[who] = zones
            msg = " + ".join(zones)
            preview = []
            for f in s.eng.active():
                if who != "*" and f.name == who:
                    continue
                parts = s.eng.zone_parts(f.name, zones)
                side = s.eng.injured_targets(f.name)[1] if "injured" in zones else None
                preview.append(f"{f.name}: {', '.join(parts) if parts else '(none yet: open everywhere)'}"
                               + (f"  [her {side} side is badly hurt: that whole side is in play]" if side else ""))
        _save_rules_key(["director", "focus"], focus)
        print(f"Target focus for {'everyone' if who == '*' else who}: {msg} (saved to rules.json)"
              + ("".join("\n  " + p for p in preview) if msg != "off" else ""))
        s.autosave(); return
    if cmd == "targeting":
        mode = (a[0].lower() if a else "")
        if mode not in ("one", "few", "many", "all", "auto"):
            raise ValueError("use /targeting one | few | many | all | auto   (now: "
                             f"{s.eng.plan.get('targeting') or 'auto'})")
        if mode == "auto":
            s.eng.plan.pop("targeting", None)
        else:
            s.eng.plan["targeting"] = mode
        print(f"Targeting: {mode}" + {"one": " (one part per attack, no jarred neighbors)",
                                       "few": " (2-3 parts per attack)", "many": " (4-6 parts per attack)",
                                       "all": " (as much of the body as possible)", "auto": " (director's choice)"}[mode])
        s.autosave(); return
    if cmd in ("learn", "teach"):
        if len(a) < 2:
            raise ValueError('Usage: /learn <fighter> "<Move>"   (for this fight only; /moves to browse)')
        s.push_history()
        try:
            m = s.eng.learn(_clean_name(a[0]), " ".join(a[1:]))
        except ValueError:
            s.history.pop()
            raise
        print(f"{s.eng.get(_clean_name(a[0])).name} learns {m['name']} for this fight: {_move_text(m)}")
        s.autosave(); return
    if cmd == "forget":
        if len(a) < 2:
            raise ValueError('Usage: /forget <fighter> "<Move>"')
        s.push_history()
        m = s.eng.forget(_clean_name(a[0]), " ".join(a[1:]))
        print(f"{s.eng.get(_clean_name(a[0])).name} forgets {m['name']}" + ("" if m.get("learned") else
              " (for this fight; it's still in fighters.json)"))
        s.autosave(); return
    if cmd == "moves":
        q = " ".join(a).lower()
        if q in ([f.name.lower() for f in s.eng.fighters.values()]):
            f = s.eng.get(q)
            print(f"{poss_name(f.name)} moves:\n" + "\n".join(f"- {_move_text(m)}" + ("  [lent]" if m.get("learned") else "")
                                                      for m in f.moves)); return
        found = [m for m in s.eng.movedex if not q or q in m["name"].lower() or q == m["type"].lower()
                 or q in (m.get("target", "")) or any(q in str(x.get("status", x.get("launch", ""))) for x in
                                                       m.get("effects", []))]
        if not found:
            raise ValueError(f"no moves match '{q}'. Try a type (/moves fire), an effect (/moves sleep, /moves "
                             f"launched), a target (/moves status), or a fighter's name")
        print(f"{len(found)} move(s){' matching ' + repr(q) if q else ''}:")
        for m in found[:80]:
            print(f"- {_move_text(m)}")
        if len(found) > 80:
            print(f"... and {len(found) - 80} more; narrow it down (e.g. /moves {found[0]['type'].lower()})")
        return
    if cmd == "moveinfo":
        m = s.eng.dex_move(" ".join(a))
        if m is None:
            raise ValueError("no such move in moves.json")
        print(_move_text(m)); return
    if cmd in ("blocks", "block"):
        cfg = s.eng.rules.setdefault("narration", {}).setdefault("blocks", {})
        B = s.narrator._blocks()
        word = a[0].lower() if a else ""
        if word in ("on", "off"):
            cfg["enabled"] = word == "on"
            saved = _save_rule_path(["narration", "blocks", "enabled"], cfg["enabled"])
            print(f"Story building blocks {'ON' if cfg['enabled'] else 'OFF'} " + ("(saved to rules.json)" if saved else "(this session)")); return
        if word in ("reset", "clear", "forget"):
            B.uses.clear(); B.last.clear()
            try:
                os.remove(B.memory)
            except OSError:
                pass
            print("The count of which blocks have been offered starts again from nothing."); return
        if word.replace(".", "", 1).isdigit():
            cfg["per_part"] = max(0, int(float(word)))
            saved = _save_rule_path(["narration", "blocks", "per_part"], cfg["per_part"])
            print(f"Up to {cfg['per_part']} building blocks are offered for each part of a beat " + ("(saved)" if saved else "(this session)")); return
        B.load()
        counts = B.counts()
        offered = sum(1 for k, v in B.uses.items() if v > 0)
        print(f"Story building blocks: {'ON' if cfg.get('enabled', True) else 'OFF'}. {sum(counts.values())} blocks in "
              f"{os.path.basename(B.path)}, up to {cfg.get('per_part', 10)} offered for each part of a beat; "
              f"{offered} have been offered at least once so far.")
        for k in sorted(counts, key=lambda x: -counts[x]):
            print(f"  {k:<18} {counts[k]:>4}")
        print("/blocks off | on, /blocks 6 (how many per part), /blocks reset (forget what has been offered). Add your own "
              "lines to the file at any time; it is read again every beat."); return
    if cmd in ("passages", "passage"):
        cfg = s.eng.rules.setdefault("narration", {}).setdefault("passages", {})
        P = s.narrator._passages()
        word = a[0].lower() if a else ""
        if word in ("on", "off"):
            cfg["enabled"] = word == "on"
            saved = _save_rule_path(["narration", "passages", "enabled"], cfg["enabled"])
            print(f"Story passages {'ON' if cfg['enabled'] else 'OFF'} " + ("(saved to rules.json)" if saved else "(this session)")); return
        if word in ("reset", "clear", "forget"):
            P.uses.clear(); P.last.clear()
            try:
                os.remove(P.memory)
            except OSError:
                pass
            print("The count of which passages have been offered starts again from nothing."); return
        if word.replace(".", "", 1).isdigit():
            cfg["chance"] = max(0.0, min(1.0, float(word)))
            saved = _save_rule_path(["narration", "passages", "chance"], cfg["chance"])
            print(f"A part with a big moment gets a passage {cfg['chance']:.0%} of the time " + ("(saved)" if saved else "(this session)")); return
        P.load()
        counts = P.counts()
        offered = sum(1 for k, v in P.uses.items() if v > 0)
        print(f"Story passages: {'ON' if cfg.get('enabled', True) else 'OFF'}. {sum(counts.values())} passages in "
              f"{os.path.basename(P.path)}; a part with a big moment gets one {float(cfg.get('chance', 0.3)):.0%} of the "
              f"time, {float(cfg.get('place_share', 0.35)):.0%} of those to set in word for word (the rest to draw on); "
              f"{offered} have been offered at least once so far.")
        for k in sorted(counts, key=lambda x: -counts[x]):
            print(f"  {k:<18} {counts[k]:>4}")
        print("/passages off | on, /passages 0.3 (how often), /passages reset (forget what has been offered). Add your "
              "own to the file at any time; it is read again every beat."); return
    if cmd in ("sample", "samples"):
        import glob
        import userprompt
        cfg = s.eng.rules.setdefault("narration", {})
        now = cfg.get("style_sample_file", "style_sample.txt")
        files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(HERE, "style_sample*.txt")))
        if now not in files and os.path.exists(os.path.join(HERE, now)):
            files.append(now)
        if not a:
            print("Style samples (the writing the narrator imitates):")
            for i, f in enumerate(files, start=1):
                raw = userprompt._read(f)
                secs = userprompt.sample_sections(raw)
                print(f"  {'●' if f == now else '○'} {i}. {f}  "
                      + (f"(in {len(secs)} sections: before each part the narrator is shown the passage that fits it)"
                         if secs else f"(plain: its first {cfg.get('style_sample_chars', 3000)} characters are shown every time)"))
            print("Change with /sample <number or file name>, e.g. /sample 1   /sample style_sample.txt"); return
        word = " ".join(a).strip().strip('"')
        pick = (files[int(word) - 1] if word.isdigit() and 1 <= int(word) <= len(files) else
                next((f for f in files if f.lower() == word.lower()), None)
                or next((f for f in files if word.lower() in f.lower().replace("style_sample", "")), None)
                or (word if os.path.exists(os.path.join(HERE, word)) else None))
        if not pick:
            raise ValueError(f"no style sample called '{word}'. /sample lists them")
        cfg["style_sample_file"] = pick
        saved = _save_rule_path(["narration", "style_sample_file"], pick)
        print(f"Style sample: {pick} " + ("(saved to rules.json)" if saved else "(this session only)")
              + ". It applies from the next beat."); return
    if cmd == "checks":
        path = os.path.join(HERE, Narrator.CHECKS_FILE)
        if a and a[0].lower() in ("clear", "reset"):
            try:
                os.remove(path)
            except OSError:
                pass
            s.narrator.check_tally = {}
            print("Check counts cleared."); return
        try:
            with open(path, encoding="utf-8") as fh:
                book = json.load(fh)
        except (OSError, ValueError):
            book = {}
        print("What the narrator's checks found, and how the paragraph fixes went (drafts: times a draft had it; "
              "fixes: paragraphs rewritten for it; worked: how many came back right; calls: model calls spent).\n"
              "This fight:\n" + Narrator.checks_table(getattr(s.narrator, "check_tally", {}) or {})
              + "\nAll fights so far (check_counts.json; /checks clear starts again):\n" + Narrator.checks_table(book))
        return
    if cmd == "polish":
        return _polish_command(s, a)
    if cmd == "compare":
        last = getattr(s, "_polish_last", None) or {}
        if not last:
            raise ValueError("no beat yet")
        other = last.get("polished") or last.get("rejected")
        print(f"=== BEAT {last.get('turn')}: AS THE LOCAL MODEL WROTE IT ===\n{last.get('local', '')}\n")
        if other:
            kept = last.get("shown") == other
            print(f"=== POLISHED ({'kept' if kept else 'not used: ' + (last.get('why') or '')}) ===\n{other}\n")
        else:
            print("(no polished version of this beat" + (f": {last['why']}" if last.get("why") else "") + ")")
        return
    if cmd == "timing":
        cfg = s.eng.rules.setdefault("console", {})
        if a and a[0].lower() in ("on", "off"):
            cfg["timing"] = a[0].lower() == "on"
            saved = _save_rule_path(["console", "timing"], cfg["timing"])
            print(f"The 'this beat took...' line is {'ON' if cfg['timing'] else 'OFF'} "
                  + ("(saved to rules.json)" if saved else "(this session)")); return
        if a and a[0].lower() in ("clear", "reset"):
            s.timings.clear(); print("Timings cleared."); return
        print(timing_summary(s.timings)); return
    if cmd in ("model", "models"):
        nm, dm = s.narrator.model, s.director.model
        if not a:
            print(f"Narrator (writes the story): {nm}\nDirector (picks what happens): {dm}\n"
                  f"Change for this session with /model narrator <name>, /model director <name>, or /model <name> for "
                  f"both (pull it in Ollama first). The choice is kept for next time."); return
        which = a[0].lower() if a[0].lower() in ("narrator", "director", "both") and len(a) > 1 else "both"
        rest = a[1:] if a[0].lower() in ("narrator", "director", "both") and len(a) > 1 else a
        # a model name has no spaces: anything after it is another command pasted on the same line
        name, more = rest[0].strip(), " ".join(rest[1:]).strip()
        if which in ("narrator", "both"):
            s.narrator.model = name
            _save_rule_path(["models", "narrator"], name)
        if which in ("director", "both"):
            s.director.model = name
            _save_rule_path(["models", "director"], name)
        print(f"Narrator: {s.narrator.model}\nDirector: {s.director.model}\n(kept for next time; the first beat on a "
              f"new model is slow while Ollama loads it. /model narrator mistral-small:24b goes back)")
        if more.startswith("/"):
            handle_command(s, more)
        elif more:
            print(f"(ignored after the model name: {more})")
        return
    if cmd in ("variant", "variants"):
        eng = s.eng
        if not eng.variants:
            print("No fighter in fighters.json has a \"variants\" section."); return
        if not a:
            for name, kinds in eng.variants.items():
                now = eng.variant_of.get(name, "original")
                nxt = str((eng.rules.get("variants") or {}).get(name, now) or "original")
                print(f"{name}:")
                for k, label in kinds.items():
                    print(f"  {'●' if k == now else '○'} {k}" + (f": {label}" if label else "")
                          + ("   ← from the next fight" if k.lower() == nxt.lower() and k != now else ""))
            print("Change with /variant <fighter> <name>, e.g. /variant Ripples original"); return
        name = eng.match_roster(a[0])
        if name not in eng.variants:
            raise ValueError(f"{name} has only one version. Fighters with variants: {', '.join(eng.variants)}")
        if len(a) < 2:
            raise ValueError(f"which one? {name} comes as: {', '.join(eng.variants[name])}")
        want = next((k for k in eng.variants[name] if k.lower() == a[1].lower()), None) \
            or next((k for k in eng.variants[name] if k.lower().startswith(a[1].lower())), None)
        if want is None:
            raise ValueError(f"{name} has no variant '{a[1]}'. She comes as: {', '.join(eng.variants[name])}")
        eng.rules.setdefault("variants", {})[name] = want
        saved = _save_rule_path(["variants", name], want)
        label = eng.variants[name].get(want, "")
        how = "(saved to rules.json)" if saved else "(this session only)"
        if want == eng.variant_of.get(name):
            print(f"{name} is already the {want} version {how}."); return
        fresh = not eng.turn and not s.story and not s.over
        if fresh and any(f.name == name for f in eng.fighters.values()):
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                s.new_fight()
            print(f"{name}: the {want} version" + (f" ({label})" if label else "") + f" {how}. Nothing had happened yet, "
                  f"so this fight starts with her that way."); return
        print(f"{name}: the {want} version" + (f" ({label})" if label else "") + f" {how}. It takes effect in the next "
              f"fight (/newfight); this one goes on with her as she is."); return
    if cmd == "tumble":
        cfg = s.eng.rules.setdefault("down", {})
        if a:
            word = a[0].lower()
            val = 0.0 if word in ("off", "no", "never") else 0.3 if word == "on" else None
            if val is None:
                try:
                    val = float(word)
                except ValueError:
                    raise ValueError("use /tumble <chance 0-1>, /tumble on or /tumble off") from None
            val = max(0.0, min(1.0, val / 100.0 if val > 1 else val))
            cfg["tumble_chance"] = val
            saved = _save_rule_path(["down", "tumble_chance"], val)
            print(f"Tumbles: {val * 100:.0f}% of throws and launches " + ("(saved to rules.json)" if saved else "(this session only)"))
            return
        print(f"Tumbles: a fighter who is thrown or launched tumbles on across the ground {float(cfg.get('tumble_chance', 0.3)) * 100:.0f}% "
              f"of the time, and {float(cfg.get('tumble_into', 0.5)) * 100:.0f}% of those times fetches up against something in "
              f"the arena. /tumble 0.5 changes it, /tumble off stops it. In your own /throw or /land, end the list with "
              f"\"; tumble\" to make her tumble.")
        return
    if cmd in ("bigmoments", "bigmoment"):
        d = s.eng.rules.setdefault("director", {})
        kinds = (("stream", "sustain_chance", "a held stream pressed into the scenery"),
                 ("charge", "charge_chance", "a charge that carries her into the scenery"),
                 ("throw", "grapple_chance", "a throw or a slam"),
                 ("grapple", "clinch_chance", "a grab, then blows or a stream at point-blank"),
                 ("chain", "chain_chance", "two or three attacks, each leading into the next"))
        if a:
            word = a[0].lower()
            if word in ("more", "less", "off"):
                for _, key, _ in kinds:
                    new = 0.0 if word == "off" else round(float(d.get(key, 0)) * (1.25 if word == "more" else 0.8), 3)
                    d[key] = new
                    _save_rule_path(["director", key], new)
            elif word in ("due", "overdue"):
                if len(a) < 2:
                    raise ValueError("use /bigmoments due <beats>   (0 = never forced)")
                d["big_moment_overdue"] = int(float(a[1]))
                _save_rule_path(["director", "big_moment_overdue"], d["big_moment_overdue"])
            else:
                hit = next((k for k in kinds if k[0].startswith(word)), None)
                if hit is None or len(a) < 2:
                    raise ValueError("use /bigmoments more | less | off | due <beats> | <stream|charge|throw|grapple|chain> <chance>")
                val = float(a[1])
                d[hit[1]] = max(0.0, min(1.0, val / 100.0 if val > 1 else val))
                _save_rule_path(["director", hit[1]], d[hit[1]])
        total = sum(float(d.get(key, 0)) for _, key, _ in kinds)
        print("Big moments: on a beat with no pin and no direction from you, one roll may point the director at one of these:")
        for name, key, what in kinds:
            print(f"  {name:<8} {float(d.get(key, 0)) * 100:>4.0f}%   {what}")
        due = int(d.get("big_moment_overdue", 10) or 0)
        print(f"  together {total * 100:.0f}% of such beats. "
              + (f"After {due} beats with none, one is suggested for certain." if due else "Never forced."))
        print(f"  So far this fight: {int(s.eng.tally.get('big|moments', 0))}"
              + (f" (the last on beat {int(s.eng.tally.get('big|last', 0))})" if s.eng.tally.get("big|moments") else "") + ".")
        print("  /bigmoments more | less | off      /bigmoments due 8      /bigmoments chain 0.08")
        return
    if cmd == "makesure":
        cfg = s.eng.rules.setdefault("pin", {})
        on = cfg.get("make_sure", True) is not False
        if not a:
            print(f"Making sure after a pass-out: {'ON' if on else 'OFF'}. "
                  + ("When the pinned fighter passes out, the pinner holds on a moment or two longer to be sure it isn't "
                     "a trick, then lets go (story only, no extra damage)." if on else
                     "The pinner eases off as soon as she feels her go limp.") + " Use /makesure on or /makesure off"); return
        word = a[0].lower()
        if word not in ("on", "off", "true", "false", "yes", "no"):
            raise ValueError("use /makesure on or /makesure off")
        new = word in ("on", "true", "yes")
        cfg["make_sure"] = new
        saved = _save_rule_path(["pin", "make_sure"], new)
        print(f"Making sure after a pass-out {'ON' if new else 'OFF'} "
              + ("(saved to rules.json)" if saved else "(this session only: rules.json has no pin.make_sure yet)")
              + (": the pinner keeps her grip a moment or two longer before letting go" if new else
                 ": the pinner lets go as soon as she feels her go limp")); return
    if cmd == "numb":
        cfg = s.eng.rules.setdefault("narration", {})
        on = cfg.get("numb_tier", True) is not False
        if not a:
            print(f"Numb-with-shock level (1000%+ damage): {'ON' if on else 'OFF'}. Use /numb on or /numb off"); return
        word = a[0].lower()
        if word not in ("on", "off", "true", "false", "yes", "no"):
            raise ValueError("use /numb on or /numb off")
        new = word in ("on", "true", "yes")
        cfg["numb_tier"] = new
        saved = _save_rule_path(["narration", "numb_tier"], new)
        print(f"Numb-with-shock level {'ON' if new else 'OFF'} "
              + ("(saved to rules.json)" if saved else "(this session only: rules.json has no narration.numb_tier yet)")
              + ("" if new else ": parts at 1000%+ now stay 'devastated' ⚫")); return
    if cmd in ("settings", "mysettings"):
        have = {}
        if os.path.exists(MY_SETTINGS):
            with open(MY_SETTINGS, encoding="utf-8") as fh:
                have = json.load(fh)
        if a and a[0].lower() in ("forget", "reset", "clear"):
            if os.path.exists(MY_SETTINGS):
                os.remove(MY_SETTINGS)
            print("my_settings.json removed. Your settings stay as they are for now (they are in rules.json too); the "
                  "next build you install will bring its own defaults."); return
        rows = _settings_lines(have)
        print("Settings you changed with commands (kept in my_settings.json; a new build doesn't touch them):\n"
              + ("\n".join(rows) if rows else "  (none yet)")
              + "\n/settings forget   drops them, so the next build's defaults apply"); return
    if cmd == "bench":
        n_, ov = 2, []
        for x in a:
            if re.fullmatch(r"\d+", x):
                n_ = max(1, int(x))
            elif "=" in x:
                path, val = x.split("=", 1)
                _rule_path(s.eng.rules, path)          # (a wrong path is said now, not after the first run)
                ov.append((path, _parse_value(val)))
            else:
                raise ValueError(f"'{x}' is not a setting=value or a number")
        if not ov:
            raise ValueError("Usage: /bench [beats] <setting=value> [...]   e.g. /bench 2 narration.rich.length_mult=1.0\n"
                             "  tells your last saved beats twice, as your settings are (A) and with the changes (B), and "
                             "compares them (words, paragraphs, model calls, time, rewrites, checks, repeats)")
        if not s.use_llm:
            raise ValueError("/bench needs the narration model (it is off in this session)")
        s.bench(n_, ov); return
    if cmd in ("sets", "setlist", "options"):
        if a and a[0].lower() == "all":
            path = os.path.join(HERE, a[1] if len(a) > 1 else "all_settings.md")
            n = _sets_file(s.eng.rules, path)
            print(f"Wrote all {n} settings, section by section, to {path}"); return
        print(_sets_text(s.eng.rules, a[0] if a else "")); return
    if cmd == "intro":
        if not a or a[0].lower() not in ("on", "off"):
            on = s.eng.rules.get("narration", {}).get("scene_intro", True)
            print(f"The opening passage that sets the scene before the first beat is {'on' if on else 'off'}. "
                  f"/intro off skips it (the first Enter starts the fight); /intro on brings it back."); return
        on = a[0].lower() == "on"
        s.eng.rules.setdefault("narration", {})["scene_intro"] = on
        _save_rule_path(["narration", "scene_intro"], on)
        print("The fight now opens with a passage setting the scene." if on else
              "No opening passage: the first Enter starts the fight. (/intro on brings it back.)"); return
    if cmd in ("phrases", "stock"):
        pm = s.narrator._phrase_mem() if hasattr(s.narrator, "_phrase_mem") else None
        if pm is None:
            print("The stock-phrase memory is off (/set narration.phrase_memory.enabled true turns it on)."); return
        if a and a[0].lower() in ("forget", "reset", "clear"):
            pm.book, pm.clock = {}, 0
            pm.save()
            print("Stock-phrase memory cleared: every phrase starts fresh."); return
        rows = pm.report(int(a[0]) if a and a[0].isdigit() else 20)
        print(f"Stock phrases the story has used (phrase_memory.json, {pm.clock} beats counted; heat halves every "
              f"{pm.cfg.get('half_life_beats', 12)} beats, and a warm phrase is rested for a while):")
        for g, uses, heat, kind in rows:
            state = ("RESTED" if heat >= float(pm.cfg.get("always_rest", 1.5)) else
                     "often rested" if heat >= float(pm.cfg.get("rest_from", 0.35)) else "free")
            print(f"  {g:<40} used {uses:>3}×  heat {heat:4.2f}  {state}{'  (learned)' if kind == 'learned' else ''}")
        if not rows:
            print("  (none yet)")
        print("Add your own to stock_phrases.txt. /phrases forget starts over."); return
    if cmd == "pinpower":
        cfg = s.eng.rules.setdefault("pin", {})
        if not a:
            print(f"Pin damage multiplier is {cfg.get('damage_mult', 1.0)}: it scales everything the pinner does to the "
                  f"fighter she is pinning (pressure each beat, the punishment for a failed struggle, her strikes and "
                  f"techniques, /pinsuccess). Change it with /pinpower <number>: 1 = full, 0.5 = half"); return
        new = float(a[0])
        if new < 0:
            raise ValueError("must be 0 or more")
        old = cfg.get("damage_mult", 1.0)
        cfg["damage_mult"] = new
        _save_rule_path(["pin", "damage_mult"], new)
        print(f"Pin damage ×{old} → ×{new} (saved; kept across new builds in my_settings.json)"); return
    if cmd in ("holdstart", "pinstart"):
        sect, word = ("holds", "hold") if cmd == "holdstart" else ("pin", "pin")
        cfg = s.eng.rules.setdefault(sect, {})
        default = 1.0 if cmd == "holdstart" else 0.0
        if not a:
            print(f"A new {word} deals ×{cfg.get('first_beat_damage', default)} of one beat's pressure on the beat it "
                  f"starts (0 = nothing until the next beat, 1 = a full beat's worth, the clamp itself).\n"
                  f"Change it with /{cmd} <number>"); return
        new = float(a[0])
        if new < 0:
            raise ValueError("must be 0 or more")
        old = cfg.get("first_beat_damage", default)
        cfg["first_beat_damage"] = new
        _save_rule_path([sect, "first_beat_damage"], new)
        print(f"First-beat damage of a new {word}: ×{old} → ×{new} (saved; kept across new builds in my_settings.json)")
        return
    if cmd == "holdshake":
        cfg = s.eng.rules.setdefault("holds", {}).setdefault("shaken", {})
        if not a:
            k = cfg.get("per_health_share", 2.5)
            print(f"A fighter who is holding someone and takes a hard hit rolls to keep her grip. Chance to lose it = "
                  f"the share of her full health that one attack cost × {k:g}, never above "
                  f"{cfg.get('max', 0.95) * 100:g}% (10% of her health at once: {min(95, k * 10):g}%; 20%: "
                  f"{min(95, k * 20):g}%). Hits that cost under {cfg.get('min_share', 0.03) * 100:g}% don't roll. Pins "
                  f"are not shaken this way.\n/holdshake <number>   higher = grips are lost more easily; 0 = never"); return
        new = float(a[0])
        if new < 0:
            raise ValueError("must be 0 or more")
        old = cfg.get("per_health_share", 2.5)
        cfg["per_health_share"] = new
        _save_rule_path(["holds", "shaken", "per_health_share"], new)
        print(f"Grip shaken by a hit: ×{old:g} → ×{new:g} (saved; kept across new builds in my_settings.json)"); return
    if cmd == "holdbreak":
        cfg = s.eng.rules.setdefault("holds", {}).setdefault("break", {})
        if not a:
            lines = [f"  #{h.id} {h.attacker} on {h.defender}'s {h.part}: "
                     f"{s.eng.hold_break_chance(h.attacker, h.defender) * 100:.0f}% this beat"
                     for h in s.eng.holds.values() if not any(p["defender"] == h.defender for p in s.eng.pins.values())]
            print(f"Holds have no time limit. Each beat the held fighter gets one roll to break a plain hold: "
                  f"{cfg.get('base', 0.12) * 100:g}% fresh against fresh (the base), more when she is the stronger "
                  f"one, the grip is light, or the gripping limb is hurt, +{cfg.get('per_beat', 0.015) * 100:g}% for "
                  f"every beat it has been on, never above {cfg.get('max', 0.6) * 100:.0f}%; less when she is worn "
                  f"down or the grip is crushing, and ×{cfg.get('below_zero_mult', 0.25)} once her health is below "
                  f"zero.\n" + ("\n".join(lines) + "\n" if lines else "")
                  + "/holdbreak <base> [per beat] [max]   e.g. /holdbreak 0.08 0.01 for long holds, /holdbreak 0 so only "
                    "the director and knockdowns end a hold"); return
        vals = [float(x) for x in a[:3]]
        if any(v < 0 or v > 1 for v in vals):
            raise ValueError("chances are between 0 and 1 (0.12 = 12%)")
        said = []
        for key, v in zip(("base", "per_beat", "max"), vals):
            old = cfg.get(key, {"base": 0.12, "per_beat": 0.015, "max": 0.6}[key])
            cfg[key] = v
            _save_rule_path(["holds", "break", key], v)
            said.append(f"{key.replace('_', ' ')} {old:g} → {v:g}")
        print("Hold break-free roll: " + ", ".join(said) + " (saved; kept across new builds in my_settings.json)"); return
    if cmd in ("pinshape", "pinshapes"):
        cfg = s.eng.rules.setdefault("director", {}).setdefault("pin_shape_weights", {})
        names = ("throat_bite", "trapped_arm", "tail_choke", "twisted_arm", "leg_tangle", "lifted_leg")
        for k, v in zip(names, (3, 3, 3, 2, 2, 1)):
            cfg.setdefault(k, v)
        if not a:
            print("How often each pin shape is suggested to the director (compared with the others; 0 = never):\n"
                  + "\n".join(f"  {k:<12} {cfg[k]:g}" for k in names)
                  + "\nthroat_bite: jaws on the throat, weight on the chest · trapped_arm: jaws pin a paw or forearm, a "
                    "forepaw or forearm bars the throat · tail_choke: tails or coils round the neck · twisted_arm: an arm "
                    "wrenched straight and pinned · leg_tangle: both legs trapped · lifted_leg: a leg hooked and hauled up"
                    "\nChange one with /pinshape <name> <number>"); return
        key = a[0].lower().replace("-", "_")
        if key not in names or len(a) < 2:
            raise ValueError("use /pinshape <name> <number>, with one of: " + ", ".join(names))
        new = float(a[1])
        if new < 0:
            raise ValueError("must be 0 or more")
        old = cfg[key]
        cfg[key] = new
        _save_rule_path(["director", "pin_shape_weights", key], new)
        print(f"Pin shape {key}: {old:g} → {new:g} (saved; kept across new builds in my_settings.json)"); return
    if cmd in ("variety", "ways"):
        cfg = s.eng.rules.setdefault("variety", {})
        about = {"charge_stands": "keeps her feet after a charge into the scenery",
                 "charge_falls": "crumples after a charge (lying, or sitting against it)",
                 "dodge": "how an attack is avoided", "hold_break": "how a hold is broken",
                 "hold_strain": "how a held fighter fights a grip that stays on",
                 "struggle": "what a pinned fighter tries", "getup_fail": "how a try at getting up fails",
                 "getup_rise": "how she finally rises", "bite_rock": "how a bite rocks her where she stands"}
        for k, table in s.eng.VARIETY.items():
            cfg.setdefault(k, dict(table))
        def row(k):
            t = {w: float(v) for w, v in cfg[k].items() if not str(w).startswith("_")}
            tot = sum(t.values()) or 1.0
            return (f"  {k:<14} {about.get(k, '')}\n      "
                    + " · ".join(f"{w} {v:g} ({100 * v / tot:.0f}%)" for w, v in t.items()))
        d = s.eng.rules.get("down", {})
        if not a:
            print("How each outcome plays out (the engine picks one way each time and the narrator tells it):\n"
                  + "\n".join(row(k) for k in s.eng.VARIETY)
                  + "\nChange a weight with /variety <set> <way> <number>   e.g. /variety dodge duck 0\n"
                  + "Other outcomes that are rolled, as chances (change with /set):\n"
                  + f"  down.slump_sitting {d.get('slump_sitting', 0.35):g}   thrown into something upright, she ends sitting against it\n"
                  + f"  down.sit_down {d.get('sit_down', 0.15):g}   a plain knockdown sits her down hard instead of laying her flat\n"
                  + f"  down.roll_through {d.get('roll_through', 0.2):g}   thrown at full strength, she rolls through and comes up on her feet\n"
                  + f"  down.resist_handling {d.get('resist_handling', 0.25):g}   on the ground at full strength, she fights off being moved or thrown\n"
                  + f"  getting_up.sit_up_chance {s.eng.rules.get('getting_up', {}).get('sit_up_chance', 0.4):g}   a failed get-up gets her as far as sitting\n"
                  + f"  pin.struggle.pinner_down_chance {s.eng.rules.get('pin', {}).get('struggle', {}).get('pinner_down_chance', 0.25):g}   an escape throws the pinner down too\n"
                  + f"  holds.break.loosen_band {s.eng.rules.get('holds', {}).get('break', {}).get('loosen_band', 0.6):g}   a near miss on the break-free roll loosens the grip"); return
        key = a[0].lower()
        if key not in s.eng.VARIETY:
            raise ValueError("use /variety, or /variety <set> [<way> <number>], with one of: " + ", ".join(s.eng.VARIETY))
        if len(a) < 3:
            print(row(key)); return
        way_ = " ".join(a[1:-1]).lower().replace(" ", "_")
        way_ = way_ if way_ in cfg[key] else " ".join(a[1:-1]).lower()
        if way_ not in cfg[key]:
            raise ValueError(f"'{' '.join(a[1:-1])}' isn't one of: " + ", ".join(k for k in cfg[key] if not k.startswith("_")))
        new = float(a[-1])
        if new < 0:
            raise ValueError("must be 0 or more")
        if new == 0 and sum(float(v) for w, v in cfg[key].items() if w != way_ and not str(w).startswith("_")) <= 0:
            raise ValueError("at least one way has to stay above 0")
        old = float(cfg[key][way_])
        cfg[key][way_] = new
        _save_rule_path(["variety", key, way_], new)
        print(f"{key}: {way_} {old:g} → {new:g} (saved)\n" + row(key)); return
    if cmd == "secure":
        cfg = s.eng.rules.setdefault("pin", {}).setdefault("secure", {})
        if not a:
            print(f"Pin requirements: {'ON' if cfg.get('enabled') else 'OFF'} — {cfg.get('min_parts', 6)} parts at "
                  f"{cfg.get('part_damage', 150)}%+ and strength {cfg.get('max_strength', 50)}% or less.\n"
                  "Use: /secure on [parts] [part damage %] [max strength %]   /secure off"); return
        if a[0].lower() in ("off", "false", "no"):
            cfg["enabled"] = False
        elif a[0].lower() in ("on", "true", "yes"):
            cfg["enabled"] = True
            for key, val in zip(("min_parts", "part_damage", "max_strength"), a[1:4]):
                cfg[key] = int(float(val)) if key == "min_parts" else float(val)
        else:
            raise ValueError("use /secure on [parts] [part damage %] [max strength %]  or  /secure off")
        for key in ("enabled", "min_parts", "part_damage", "max_strength"):
            _save_rule_path(["pin", "secure", key], cfg.get(key))
        print(f"Pin requirements {'ON' if cfg['enabled'] else 'OFF'}"
              + (f": until the opponent has {cfg.get('min_parts', 6)} parts at {cfg.get('part_damage', 150):g}%+ and "
                 f"strength {cfg.get('max_strength', 50):g}% or less, her escape chance is ×"
                 f"{cfg.get('unmet_escape_mult', 2.0):g} and she kicks out at the last second "
                 f"{cfg.get('final_kickout_chance', 0.85) * 100:.0f}% of the time."
                 if cfg["enabled"] else "") + " (saved to rules.json)"); return
    if cmd == "get":
        if not a:
            print("Rule sections: " + ", ".join(k for k in s.eng.rules if not k.startswith("_"))
                  + "\n/get <section> to see one, e.g. /get pin.struggle"); return
        node, key, _ = _rule_path(s.eng.rules, a[0])
        val = node[key]
        if isinstance(val, dict):
            val = {k: v for k, v in val.items() if not k.startswith("_")}
        print(f"{a[0]} = {json.dumps(val, indent=1, ensure_ascii=False)}"); return
    if cmd in ("preset", "presets", "match"):
        # (since build 282) a whole kind of match at once: rules.json presets
        pres = {k: v for k, v in (s.eng.rules.get("presets") or {}).items() if not str(k).startswith("_")
                and isinstance(v, dict)}
        if not a:
            print("Match presets (/preset <name>; /preset <name> ? shows what it changes; add nosave for this session):")
            for k, v in pres.items():
                print(f"  {k:<12} {v.get('description', '')}")
            return
        name = a[0].lower()
        if name not in pres:
            raise ValueError(f"no preset called '{a[0]}': {', '.join(pres)}")
        settings = pres[name].get("settings") or {}
        if len(a) > 1 and a[1] in ("?", "show", "what"):
            print(f"/preset {name}: {pres[name].get('description', '')}")
            for path, v in settings.items():
                try:
                    node, key, _ = _rule_path(s.eng.rules, path)
                    now = node[key]
                except (KeyError, ValueError, TypeError):
                    now = "(not set)"
                print(f"  /set {path} {json.dumps(v)}" + ("" if now == v else f"     (now {json.dumps(now)})"))
            return
        nosave = a[-1].lower() == "nosave"
        changed = []
        for path, v in settings.items():
            node, key, keys = _rule_path(s.eng.rules, path)
            if node.get(key) != v:
                changed.append(f"{path} {json.dumps(node.get(key))} → {json.dumps(v)}")
            node[key] = v
            if not nosave:
                _save_rule_path(keys, v)
        print(f"Preset {name}: {pres[name].get('description', '')}"
              + (f"\n  changed: " + "; ".join(changed) if changed else "\n  (already set that way)")
              + ("\n  (this session only)" if nosave else "\n  (saved: kept for new fights and new builds)"))
        return
    if cmd == "set":
        if len(a) < 2:
            raise ValueError("Usage: /set <rule.path> <value>   e.g. /set pin.struggle.escape_chance 0.5  "
                             "(/get shows the rules; add 'nosave' to change it for this session only)")
        nosave = a[-1].lower() == "nosave"
        node, key, keys = _rule_path(s.eng.rules, a[0])
        value = _parse_value(" ".join(a[1:-1] if nosave else a[1:]))
        old = node[key]
        if isinstance(old, (int, float)) and not isinstance(old, bool) and not isinstance(value, (int, float)):
            raise ValueError(f"{a[0]} is a number (now {old})")
        node[key] = value
        saved = False if nosave else _save_rule_path(keys, value)
        print(f"{a[0]}: {json.dumps(old, ensure_ascii=False)} → {json.dumps(value, ensure_ascii=False)}"
              + (" (saved to rules.json)" if saved else " (this session only)")); return
    if cmd == "fighter":
        if len(a) < 2:
            raise ValueError("Usage: /fighter <name> <health|maxhealth|energy|status|clearstatus|down|up|recovery|"
                             "revive> [value] [beats]\n  e.g. /fighter Ripples health 900   /fighter Ripples status "
                             "paralyzed 2   /fighter Ripples down   /fighter Seraphina revive")
        f = s.eng.get(_clean_name(a[0]))
        what = a[1].lower()
        s.push_history()
        try:
            if what in ("health", "hp"):
                f.health = float(a[2])
            elif what in ("maxhealth", "max"):
                f.max_health = float(a[2])
            elif what == "energy":
                f.energy = max(0.0, min(100.0, float(a[2])))
            elif what == "status":
                s.eng.set_status(f, a[2].lower(), int(a[3]) if len(a) > 3 else 2)
                s.eng._fresh_status.discard((f.name, a[2].lower()))
                for e in s.eng._knock_on:
                    print("  (" + (e.get("note") or (f"{e['fighter']} slumps to the ground" if e["type"] == "slumps"
                                                     else f"{e['attacker']} loses her grip on {e['defender']}")) + ")")
                s.eng._knock_on = []
            elif what == "clearstatus":
                f.status.pop(a[2].lower(), None) if len(a) > 2 else f.status.clear()
            elif what == "down":
                if f.eliminated:
                    raise ValueError(f"{f.name} is out of the fight; use /face {f.name} down|up|side to turn her")
                s.eng.knock_down(f.name, facing=_facing_word(a[2]) if len(a) > 2 else None, why=f"{f.name} went down")
                for e in s.eng._knock_on:
                    print("  (" + (e.get("note") or f"{e['attacker']} loses her grip on {e['defender']}") + ")")
                s.eng._knock_on = []
            elif what == "up":
                s.eng.stand_up(f.name)
            elif what == "recovery":
                stages = s.eng.rules.get("recovery", {}).get("stages") or s.eng.RECOVERY_DEFAULT
                f.recovery = max(0, min(len(stages) - 1, int(a[2])))
            elif what == "revive":  # back into the fight (undoes an elimination)
                s.eng.revive(f.name)
                if not s.eng.winner():
                    s.over = False  # more than one side standing again: the match is back on
            else:
                raise ValueError(f"unknown field '{what}'")
        except (IndexError, ValueError) as e:
            s.history.pop()
            raise ValueError(f"/fighter {what}: {e}")
        print(s.display.health(s.eng, f.name).split("\n")[0])
        s.autosave(); return
    if cmd == "part":
        if len(a) < 4:
            raise ValueError('Usage: /part <fighter> "<Part>" <damage|resistance> <value>   e.g. /part Ripples '
                             '"Right Paw" damage 120')
        f = s.eng.get(_clean_name(a[0]))
        part = f.part(a[1])
        what, val = a[2].lower(), float(a[3])
        s.push_history()
        if what.startswith("dam"):
            part.damage = max(0.0, val)
        elif what.startswith("res"):
            part.resistance = max(0.0, val)
        else:
            s.history.pop()
            raise ValueError("use damage or resistance")
        print(f"{f.name}: " + s.display.part_line(part.name, part.resistance, part.damage)[2:])
        s.autosave(); return
    if cmd == "health":
        print(s.display.health(s.eng, _clean_name(a[0]) if a else None)); return
    if cmd == "energy":
        # (since build 298) energy straight onto a fighter, no beat played: /energy Seraphina 30, /energy Ripples -10,
        # /energy Nocturne =100. Alone, it lists everyone's energy
        if not a:
            print("  ".join(f"{f.name} {round(f.energy)}" for f in s.eng.fighters.values())); return
        f = s.eng.get(_clean_name(a[0]))
        amt = a[1] if len(a) > 1 else "25"
        m = re.fullmatch(r"(=)?([+-]?\d+(?:\.\d+)?)", amt.strip())
        if not m:
            raise ValueError("/energy <name> [amount]: a number to add (25 if left out), -n to take away, =n to set")
        before = f.energy
        f.energy = max(0.0, min(100.0, float(m.group(2)) if m.group(1) else f.energy + float(m.group(2))))
        print(f"{f.name}'s energy: {round(before)} -> {round(f.energy)}"); return
    if cmd == "effects":
        # (since build 306) the window.alive pieces and narration.settling_in on or off, kept like /set
        if not a:
            print("Effects: " + "   ".join(f"{k} {'on' if on else 'off'}" for k, on in effects_state(s.eng.rules)))
            return
        words = [x.lower() for x in a]
        on = next((_parse_value(x) for x in words if x in ("on", "off", "true", "false", "yes", "no")), None)
        what = [x for x in words if x not in ("on", "off", "true", "false", "yes", "no")] or ["all"]
        bad = [x for x in what if x not in EFFECTS]
        if bad or on is None:
            raise ValueError("/effects [breathing|pulse|impact|grey|grips|monitor|settling|all] on|off")
        for x in what:
            set_effect(s.eng.rules, x, on)
        print("Effects: " + "   ".join(f"{k} {'on' if v else 'off'}" for k, v in effects_state(s.eng.rules)))
        return
    if cmd in ("look", "describe"):
        who = _clean_name(a[0]) if a else None
        if who:
            s.eng.get(who)
        if not s.use_llm:
            print(s.display.look_text(s.eng, who)); return
        s.sync_narrator()
        print("\n" + s.narrator.look(s.eng.narrator_condition(), s.notes(), s.eng.scene, s.recent_story(), who) + "\n")
        return
    if cmd == "undo":
        steps = int(a[0]) if a and a[0].isdigit() else 1
        for _ in range(steps):
            s.undo()
        print(f"Undid {steps} beat{'s' if steps > 1 else ''}.\n{s.display.status_brief(s.eng)}"); return
    if cmd == "reroll":
        if not s.use_llm:
            raise ValueError("the narrator is off (--no-llm)")
        s.reroll(); return
    if cmd == "exportfight":
        import fightexport
        every = any(x.lower() == "all" for x in a)
        names = [x for x in a if x.lower() != "all"]
        path = fightexport.write(s, (_path(names[0], ".html") if names else None),
                                 fights=None if every else [s.fight_no])
        print(f"Saved {'every fight this session' if every else 'this fight'}, beat by beat with each fighter's "
              f"picture, health, and every body part's damage and resistance, to {path} (open it in a browser; the "
              f"same data is in the .json file beside it)"); return
    if cmd == "export":
        prose_only = any(x.lower() == "prose" for x in a)
        names = [x for x in a if x.lower() != "prose"]
        path = _path(names[0] if names else "story_export", ".md")
        with open(path, "w", encoding="utf-8") as fh:
            now = ([f"## Fight {s.fight_no}: {' vs '.join(s.lineup())}"] if s.story_before else []) + s.story
            fh.write("\n\n".join(s.story_before + now) if prose_only else "\n".join(s.transcript))
        print(f"Exported {'the story (prose only)' if prose_only else 'everything (prose and stats)'} to {path}"); return
    if cmd == "encourage":
        import director as _dir
        enc = s.eng.__dict__.setdefault("encouraged", [])
        enc[:] = [e for e in enc if s.eng.turn < int(e.get("until", 0))]
        if not a or a[0].lower() in ("list", "show"):
            if not enc:
                print("Nothing is being encouraged. /encourage <kind> [blows/links] [attacker] [defender] [beats]"); return
            for e in enc:
                print(f"  {e['kind']}" + (f" ×{e['count']}" if e.get("count") else "")
                      + (f" by {e['attacker']}" if e.get("attacker") else "") + (f" on {e['defender']}" if e.get("defender") else "")
                      + f": {int(e['until']) - s.eng.turn} beat(s) left")
            return
        if a[0].lower() in ("off", "clear", "none", "stop"):
            enc.clear()
            print("Encouragements cleared."); return
        kind = a[0].lower().strip('"')
        kind = _dir.ENCOURAGE_ALIASES.get(kind, kind)
        if kind not in _dir.ENCOURAGE and " " not in kind and len(a[0]) < 12 and not a[0].startswith('"'):
            print(f"(No kind called '{a[0]}': passing it on to the director in your words. Known kinds: "
                  f"{', '.join(_dir.ENCOURAGE)}.)")
        nums, names = [], []
        for x in a[1:]:
            if x.isdigit():
                nums.append(int(x))
                continue
            try:
                names.append(s.eng.get(x).name)
            except ValueError:
                raise ValueError(f"/encourage: '{x}' is neither a number nor a fighter in this fight")
        count = nums[0] if len(nums) >= 2 and kind in ("pummel", "chain") else None
        beats = max(1, nums[-1]) if nums else 3
        if count is not None:
            count = max(2, min(count, 6 if kind == "pummel" else 4))
        if names:
            f0 = s.eng.get(names[0])
            if kind in ("dive", "carry", "spike") and not s.eng.can_fly(f0):
                print(f"(Note: {f0.name} can't fly ({s.eng.can_fly(f0, why=True)}), so {kind} won't happen for her.)")
            if kind == "sustain" and not any(m.get("sustainable") for m in f0.moves):
                print(f"(Note: {f0.name} has no move she can hold on someone, so a held stream won't happen for her.)")
        e = {"kind": kind, "attacker": names[0] if names else None, "defender": names[1] if len(names) > 1 else None,
             "count": count, "until": s.eng.turn + beats}
        enc[:] = [x for x in enc if not (x["kind"] == kind and x.get("attacker") == e["attacker"])] + [e]
        print(f"Encouraging {kind}" + (f" ({count} {'blows' if kind == 'pummel' else 'links'})" if count else "")
              + (f" by {e['attacker']}" if e["attacker"] else "") + (f" on {e['defender']}" if e["defender"] else "")
              + f" for the next {beats} beat{'s' if beats != 1 else ''}. (A nudge: the dice and the rules still decide.)")
        return
    if cmd == "scale":
        cur = s.eng.rules.setdefault("damage", {}).get("damage_scale", 1.0)
        if not a:
            print(f"Damage scale is {cur}. Change it with /scale <number>, e.g. /scale 2.5, or /scale default (3, what "
                  f"the fighters and /length are tuned at)"); return
        if str(a[0]).lower() in ("default", "reset", "normal"):
            new = 3.0      # the scale the fighters and /length presets are tuned at (build 146 on)
        else:
            try:
                new = float(a[0])
            except ValueError:
                raise ValueError("/scale takes a number (e.g. /scale 3) or 'default' (3, what the win rates are tuned at)")
        if new <= 0:
            raise ValueError("scale must be above 0")
        s.eng.rules["damage"]["damage_scale"] = new
        if new > 3:
            # what a solid blow (power 60) really does now, on a fresh sturdy part and on one already worn down
            pts = sorted((s.eng.rules["resistance"].get("smooth") or {}).get("points") or [[50, 1.0, 1.0]])
            def mult(res):
                if res <= pts[0][0]:
                    return pts[0][1]
                for (r0, m0, _), (r1, m1, _) in zip(pts, pts[1:]):
                    if r0 <= res <= r1:
                        return m0 + (m1 - m0) * (res - r0) / (r1 - r0)
                return pts[-1][1]
            print(f"Note: at {new:g}x a solid blow does about {round(60 * mult(95) * new)}% to a fresh, sturdy body part, "
                  f"about {round(60 * mult(45) * new)}% once that part is worn down, and about "
                  f"{round(60 * mult(15) * new)}% to a ruined one. Fights end much sooner and the numbers get very large. "
                  f"/scale 3 is the default (the win rates are tuned at 3); for shorter fights, /length is the "
                  f"balanced way.")
        _save_rule("damage_scale", new)
        print(f"Damage scale {cur} → {new} (saved to rules.json)"); return
    if cmd in ("reader", "secondreading"):
        n = s.eng.rules.setdefault("narration", {})
        if not a:
            print(f"Second reading: {'ON' if n.get('reader_check', True) else 'OFF'}"
                  + (f", read by {n['reader_model']}" if n.get("reader_model") else " (read by the narrator's own model)")
                  + ".\nAfter each part is written, the model reads it back against the beat's facts and lists what "
                    "contradicts them; those paragraphs are written again. One short extra call per part.\n"
                    "  /reader on | off          /reader model <ollama model name>   (/reader model same = the narrator's)\n"
                    "  /reader cpu on | off      run that other model on the CPU so the narrator stays on the graphics card"
                    + (f"   (now: {'on' if n.get('reader_on_cpu') else 'off'})")
                    + "\n  /reader confirm on | off  ask about each finding a second time before rewriting for it"
                    + (f"   (now: {'on' if n.get('reader_confirm', False) else 'off'})"))
            return
        word = a[0].lower()
        if word == "cpu":
            on = len(a) < 2 or a[1].lower() in ("on", "yes", "true")
            n["reader_on_cpu"] = on
            _save_rules_key(["narration", "reader_on_cpu"], on)
            print(f"Second reading on the CPU: {'ON' if on else 'OFF'} (saved). It only applies when /reader model names a "
                  f"different model: that model then runs in system memory and the narrator stays on the graphics card.")
            return
        if word == "confirm":
            on = len(a) < 2 or a[1].lower() in ("on", "yes", "true")
            n["reader_confirm"] = on
            _save_rules_key(["narration", "reader_confirm"], on)
            print(f"Second reading, second look at each finding: {'ON' if on else 'OFF'} (saved)")
            return
        if word == "model":
            name = "" if len(a) < 2 or a[1].lower() in ("same", "none", "narrator", "default") else a[1]
            n["reader_model"] = name
            _save_rules_key(["narration", "reader_model"], name)
            print(f"Second reading is done by: {name or 'the narrator model'} (saved)"); return
        if word not in ("on", "off"):
            raise ValueError("use /reader on, /reader off, /reader model <name>, /reader cpu on|off, or "
                             "/reader confirm on|off")
        n["reader_check"] = word == "on"
        _save_rules_key(["narration", "reader_check"], word == "on")
        print(f"Second reading {word.upper()} (saved)"); return
    if cmd == "repair":
        n = s.eng.rules.setdefault("narration", {})
        if not a:
            print(f"Paragraph repair: {'ON' if n.get('paragraph_repair', True) else 'OFF'}. ON: when a draft has a mistake "
                  f"the program can point at, only that paragraph is written again and the rest stays word for word. OFF: "
                  f"the whole part is rewritten for any problem (the old way).   /repair on | off"); return
        if a[0].lower() not in ("on", "off"):
            raise ValueError("use /repair on or /repair off")
        n["paragraph_repair"] = a[0].lower() == "on"
        _save_rules_key(["narration", "paragraph_repair"], a[0].lower() == "on")
        print(f"Paragraph repair {a[0].upper()} (saved)"); return
    if cmd == "layout":
        cfg = s.eng.rules.setdefault("console", {})
        if not a:
            print(f"Stat layout: {s.display.layout()}.\n"
                  "  /layout clear     every hit as three labelled rows (damage, resistance, health: before → after, then the "
                  "math), grouped under what caused it, space between the blocks, one chance roll per line, no line "
                  "wider than about 100 characters. Every beat in full.\n"
                  "  /layout tight     one unlabelled row per hit and everything packed together: shortest, needs a wide "
                  "window.\n"
                  "  /layout classic   the Before / Calculations / After blocks, with the one-line summary on pin and "
                  "hold beats.\n" + s.display.KEY); return
        word = a[0].lower()
        if word in ("readable", "roomy", "spaced", "new", "default"):
            word = "clear"
        if word in ("compact", "dense", "short"):
            word = "tight"
        if word in ("old", "long", "full"):
            word = "classic"
        if word not in ("clear", "tight", "classic"):
            raise ValueError("use /layout clear, /layout tight or /layout classic")
        cfg["layout"] = word
        _save_rules_key(["console", "layout"], word)
        print(f"Stat layout: {word} (saved)"); return
    if cmd == "style":
        cfg = s.eng.rules.setdefault("console", {})
        if not a:
            print(f"Styled text: {cfg.get('styled_text', 'auto')}" + (f", bold in {cfg['bold_color']}" if cfg.get("bold_color") else "")
                  + ". This line shows it: **bold** and *italic*.\n"
                  "Use: /style on | off | auto      /style color yellow|cyan|green|magenta|red|blue|white|none"); return
        word = a[0].lower()
        if word in ("color", "colour"):
            c = (a[1].lower() if len(a) > 1 else "none")
            if c not in ANSI_COLORS and c not in ("none", "off", ""):
                raise ValueError("use /style color " + "|".join(ANSI_COLORS) + "|none")
            cfg["bold_color"] = c if c in ANSI_COLORS else ""
            _save_rules_key(["console", "bold_color"], cfg["bold_color"])
            print(f"Bold text is now **{'in ' + c if c in ANSI_COLORS else 'plain bold'}** (saved to rules.json)"); return
        if word not in ("on", "off", "auto"):
            raise ValueError("use /style on | off | auto, or /style color <name>")
        cfg["styled_text"] = word
        _save_rules_key(["console", "styled_text"], word)
        print(f"Styled text {word} (saved to rules.json): **bold** and *italic* look like this now"); return
    if cmd in ("sounds", "sound"):
        cfg = s.eng.rules.setdefault("narration", {}).setdefault("sounds", {})
        hows, writes = ("always", "often", "sometimes", "rarely"), ("often", "sometimes", "rarely", "never")
        if not a:
            print(f"Pained sounds: {'on' if cfg.get('enabled', True) else 'off'}; how often she makes one: "
                  f"{cfg.get('how_often', 'always')}; written out (*Nngh*, *Hss*): {cfg.get('write_out', 'often')}.\n"
                  "Use: /sounds always | often | sometimes | rarely      /sounds write often | sometimes | rarely | never"
                  "      /sounds on | off"); return
        word = a[0].lower()
        if word in ("on", "off"):
            cfg["enabled"] = word == "on"
        elif word == "write" and len(a) > 1 and a[1].lower() in writes:
            cfg["write_out"] = a[1].lower()
        elif word in hows:
            cfg["how_often"] = word
        else:
            raise ValueError("use /sounds always|often|sometimes|rarely, /sounds write often|sometimes|rarely|never, "
                             "or /sounds on|off")
        _save_rules_key(["narration", "sounds"], cfg)
        print(f"Sounds: {cfg.get('how_often', 'always')}, written out {cfg.get('write_out', 'often')}"
              f"{'' if cfg.get('enabled', True) else ' (off)'} (saved to rules.json)"); return
    if cmd == "talk":
        cfg = s.eng.rules.setdefault("narration", {}).setdefault("talk", {})
        presets = {"quiet": (True, 0, 0, 1), "less": (True, 1, 2, 2), "normal": (True, 2, 0, 4), "free": (False, 9, 0, 9)}
        if not a:
            print(f"Talking: {'limited' if cfg.get('enabled', True) else 'no limit'}: up to "
                  f"{cfg.get('spoken_per_beat', 1)} spoken line(s) per beat, none for {cfg.get('spoken_gap', 2)} beat(s) "
                  f"after one, up to {cfg.get('thoughts_per_part', 3)} thoughts per part.\n"
                  "Use: /talk quiet | less | normal | free"); return
        word = a[0].lower()
        if word not in presets:
            raise ValueError("use /talk quiet | less | normal | free")
        on, spoken, gap, thoughts = presets[word]
        cfg.update({"enabled": on, "spoken_per_beat": spoken, "spoken_gap": gap, "thoughts_per_part": thoughts})
        _save_rules_key(["narration", "talk"], cfg)
        print(f"Talking set to {word} (saved to rules.json)"); return
    if cmd in ("healthloss", "healthscale"):
        cur = s.eng.rules["health"].get("loss_per_damage_point", 0.5)
        if not a:
            print(f"Health lost per point of body-part damage: {cur} (times 0.7 to 2.2 depending on how worn the part "
                  f"is). Change it with /healthloss <number>: higher = fights end sooner without wrecking parts faster."); return
        new = float(a[0])
        if new < 0:
            raise ValueError("must be 0 or more")
        s.eng.rules["health"]["loss_per_damage_point"] = new
        _save_rule_path(["health", "loss_per_damage_point"], new)
        print(f"Health loss per damage point {cur} → {new} (saved to rules.json)"); return
    if cmd in ("vital", "vitals", "partweight", "partweights"):
        cfg = s.eng.rules["health"].setdefault("part_weights", {"enabled": True, "regions": {}, "words": {}})
        if a and a[0].lower() in ("on", "off"):
            cfg["enabled"] = a[0].lower() == "on"
            _save_rules_key(["health", "part_weights"], cfg)
            print("Body parts now " + ("count toward overall health by how vital they are" if cfg["enabled"] else
                                       "all count the same toward overall health (the old rule)") + " (saved to rules.json)"); return
        if len(a) >= 2:
            word, new = " ".join(a[:-1]).lower(), float(a[-1])
            if new < 0:
                raise ValueError("a weight can't be negative")
            where = "regions" if word in (cfg.get("regions") or {}) else "words"
            old = cfg.setdefault(where, {}).get(word)
            cfg[where][word] = new
            _save_rules_key(["health", "part_weights"], cfg)
            print(f"Parts named '{word}' now count ×{new:g} toward overall health"
                  + (f" (was ×{old:g})" if old is not None else "") + " (saved to rules.json)"); return
        print("How much each body part matters to OVERALL health (health lost from a hit, and the per-beat drain from a "
              "badly hurt part, are multiplied by this; the part's own damage and pain are unchanged)"
              + ("" if cfg.get("enabled", True) else " — currently OFF: every part counts ×1") + ":")
        for f in s.eng.fighters.values():
            by = {}
            for p in f.parts:
                by.setdefault(s.eng.part_weight(p), []).append(p)
            print(f"  {f.name}: " + "; ".join(f"×{w:g} {', '.join(ps)}" for w, ps in sorted(by.items(), reverse=True)))
        print("/vital ear 0.3 (any word in a part's name, or a region: head, neck, chest, belly, back_up, back_low, shoulder, "
              "fore_up, fore_low, hind_up, hind_low, tail)   /vital off | on"); return
    if cmd in ("wear", "wearbydamage"):
        cur = float(s.eng.rules["resistance"].get("loss_per_damage", 0) or 0)
        if not a:
            print(f"Resistance lost per 1% of damage a hit really does: {cur:g} (0 = off: wear depends on the blow's power "
                  f"only). With it on, a part that takes a lot of damage softens faster. Change it with /wear <number>, "
                  f"e.g. /wear 0.05"); return
        new = float(a[0])
        if new < 0:
            raise ValueError("must be 0 or more")
        s.eng.rules["resistance"]["loss_per_damage"] = new
        _save_rule_path(["resistance", "loss_per_damage"], new)
        print(f"Wear by damage {cur:g} → {new:g} (saved to rules.json)"); return
    if cmd in ("resscale", "resistancescale", "rescale", "resistscale"):
        cur = s.eng.rules.setdefault("damage", {}).get("resistance_scale", 1.0)
        if not a:
            print(f"Resistance scale is {cur} (how fast body-part resistance wears down; damage_scale is separate). "
                  f"Change it with /resscale <number>"); return
        new = float(a[0])
        if new < 0:
            raise ValueError("resistance scale can't be negative")
        s.eng.rules["damage"]["resistance_scale"] = new
        _save_rule("resistance_scale", new)
        print(f"Resistance scale {cur} → {new} (saved to rules.json)"); return
    if cmd == "words":
        cfg = s.eng.rules.setdefault("narration", {})
        if not a:
            print(f"Narration length is about {cfg.get('words_per_beat')} words per beat "
                  f"(written in parts of ~{cfg.get('words_per_pass', 300)}). Change it with /words <number>"); return
        new = int(float(a[0]))
        if new < 50:
            raise ValueError("use at least 50 words")
        cur = cfg.get("words_per_beat")
        cfg["words_per_beat"] = new
        _save_rule("words_per_beat", new)
        parts = max(1, min(4, round(new / max(150, cfg.get("words_per_pass", 300)))))
        print(f"Narration length {cur} → {new} words per beat, written in {parts} part(s) (saved to rules.json)")
        if new > 900 and cfg.get("context_window", 8192) <= 8192:
            print("Tip: for beats this long, raise narration -> context_window in rules.json to 12288 if your GPU has room.")
        return
    if cmd in ("pinbeat", "pinlength"):
        key = "seconds_per_beat" if cmd == "pinbeat" else "duration_seconds"
        cfg = s.eng.rules.setdefault("pin", {})
        cur = cfg.get(key)
        if not a:
            print(f"Pin {'seconds per beat' if cmd == 'pinbeat' else 'length (seconds)'} is {cur}. "
                  f"Change it with /{cmd} <number>"
                  + (" (the fixed length only applies with /pinfade off; pins now run until she passes out: see /pinfade)"
                     if cmd == "pinlength" and s.eng.fade_mode() else "")); return
        new = float(a[0])
        new = int(new) if new == int(new) else new
        if new <= 0:
            raise ValueError("must be above 0")
        cfg[key] = new
        _save_rule(key, new)
        print(f"Pin {key.replace('_', ' ')}: {cur} → {new} (saved to rules.json)"); return
    if cmd == "math":
        choice = a[0].lower() if a else "auto"
        if choice in ("off", "no", "false"):
            s.show_math = False
        elif choice in ("on", "yes", "true", "auto", "full", "compact", "both"):
            s.show_math, s.math_mode = True, ("auto" if choice in ("on", "yes", "true") else choice)
        else:
            raise ValueError("use /math auto, full, compact, both, or off")
        print(f"Stats: {s.math_mode if s.show_math else 'off'}"); return
    if cmd == "style":
        s.narrator.style = " ".join(a); print(f"Style: {s.narrator.style}"); return
    if cmd in ("scene", "scenes", "arena"):
        if not a:
            print(scene_list(s.eng) + "\n\nNow: " + scene_summary(s.eng)
                  + "\n/scene <number or name> switches; /scene random; /scene <a sentence> describes your own."); return
        which = " ".join(a)
        if which.lower() in ("random", "r", "any"):
            which = s.eng.rng.choice([n for n in s.eng.scenes if n != s.eng.scene_name] or list(s.eng.scenes))
        key = s.eng.find_scene(which)
        if key is None and len(which.split()) < 5:
            raise ValueError(f"no scene called '{which}'. /scene lists them; to describe your own arena, write a full "
                             f"sentence (five words or more)")
        s.push_history()
        s.eng.set_scene(key or which)
        if s.eng.turn:
            s.eng.positions = ""   # where everyone stood belonged to the old arena
        s.eng.rules.setdefault("scene", {})["current"] = s.eng.scene_name if key else s.eng.rules.get("scene", {}).get("current", "sea cave")
        if key:
            _save_rule_path(["scene", "current"], key)
        s.sync_narrator()
        print("Scene: " + scene_summary(s.eng) + "\n\n" + s.eng.scene); return
    if cmd in ("hazards", "hazard"):
        cfg = s.eng.rules.setdefault("scene", {})
        if cmd == "hazard" and a and a[0].lower() not in ("on", "off", "chance"):
            who = a[-1] if len(a) > 1 and _is_fighter(s.eng, a[-1]) else None
            ev = s.eng.force_event(" ".join(a[:-1] if who else a), who)
            print(f"At the end of the next beat: {ev['name']}" + (f", on {s.eng.get(who).name}" if who else "")
                  + ". (Press Enter, or give the beat a command or a direction.)"); return
        if a and a[0].lower() in ("on", "off"):
            cfg["events"] = a[0].lower() == "on"
            _save_rule_path(["scene", "events"], cfg["events"])
            print(f"The arena acting by itself: {'ON' if cfg['events'] else 'OFF'} (saved). Its hazards still work when a "
                  f"fighter lands on or is driven into them."); return
        if a and a[0].lower() == "chance":
            new = float(a[1])
            if not 0 <= new <= 1:
                raise ValueError("a chance between 0 and 1, e.g. /hazards chance 0.08")
            old, cfg["event_chance"] = cfg.get("event_chance", 0.05), new
            _save_rule_path(["scene", "event_chance"], new)
            print(f"Chance per beat that the arena does something by itself: {old:g} → {new:g} (saved)"); return
        print(scene_summary(s.eng, full=True)
              + f"\n\nThe arena acting by itself is {'ON' if cfg.get('events', True) else 'OFF'}: "
                f"{float(cfg.get('event_chance', 0.05)) * 100:g}% a beat, at least {cfg.get('event_gap', 4)} beats apart, never "
                f"during a pin or a hold.\n/hazards on|off · /hazards chance 0.08 · /hazard <event> [fighter] makes one happen"); return
    if cmd == "save":
        path = _path(a[0] if a else "fight")
        s.eng.save(path, s._extra())
        print(f"Saved to {path}"); return
    if cmd == "load":
        path = _path(a[0] if a else "autosave")
        if not os.path.exists(path):
            raise ValueError(f"no save file at {path}")
        s.load(path)
        print(f"Loaded {path}\n{s.display.status_brief(s.eng)}"); return
    if cmd in ("more", "stay", "dwell"):
        cfg = s.eng.rules.setdefault("narration", {})
        if a and a[0].lower() == "auto":
            if len(a) < 2:
                print(f"After every attack beat, {cfg.get('more_after_attacks', 0)} extra passage(s) are added on their "
                      f"own. Change it with /more auto <0-3>"); return
            n = max(0, min(3, int(a[1])))
            cfg["more_after_attacks"] = n
            _save_rules_key(["narration", "more_after_attacks"], n)
            print(f"Extra passages after every attack beat: {n} (saved to rules.json)"); return
        words = None
        if a and a[0].isdigit():
            words, a = max(60, int(a[0])), a[1:]
        s.more(words, " ".join(a)); return
    if cmd == "team":
        names = [_clean_name(x) for x in a]
        if not names:
            print("Sides: " + (s.eng.sides_text() or "everyone fights alone.")
                  + "\nUse: /team <names> [as <team name>]   /team <name> solo   /team off   (/ally for a temporary one)")
            return
        s.push_history()
        try:
            if names[0].lower() in ("off", "none", "clear"):
                for f in s.eng.fighters.values():
                    s.eng.leave_team(f.name)
                msg = "All teams ended: everyone fights alone"
            elif len(names) == 2 and names[1].lower() in ("solo", "alone", "none", "off", "out"):
                msg = f"{s.eng.leave_team(names[0])} fights alone now"
            else:
                label = None
                low = [n.lower() for n in names]
                if "as" in low:
                    i = low.index("as")
                    label, names = " ".join(names[i + 1:]) or None, names[:i]
                ev = s.eng.set_team(names, label)
                msg = f"Team {ev['team']}: {' and '.join(ev['members'])} fight together and win together"
                for k in ev["knock_on"]:
                    msg += f"\n  ({k.get('note') or (k['attacker'] + ' lets go of ' + k['defender'])})"
        except ValueError:
            s.history.pop()
            raise
        teams = {f.name: f.team for f in s.eng.fighters.values() if f.team != f.name
                 and not any(f.name in al["members"] for al in s.eng.alliances)}
        s.eng.rules["teams"] = teams
        _save_rules_key(["teams"], teams)
        print(msg + " (saved to rules.json; it holds for every fight)")
        s.autosave(); return
    if cmd in ("ally", "alliance", "truce"):
        if not a:
            lines = [f"  {' and '.join(al['members'])}: {s.eng.alliance_terms(al)}" for al in s.eng.alliances]
            print("Alliances: " + ("\n" + "\n".join(lines) if lines else "none")
                  + "\nUse: /ally <names> [beats] [until <name>]   /ally off"); return
        if a[0].lower() in ("off", "end", "none", "over"):
            b = {"action": "ally_end", "attacker": s.eng.active()[0].name, "defender": "",
                 "members": [_clean_name(x) for x in a[1:]], "flavor": "", "_manual": True}
        else:
            names, beats, until, i = [], None, None, 0
            while i < len(a):
                w = _clean_name(a[i])
                if w.isdigit():
                    beats = int(w)
                elif w.lower() in ("until", "till", "against"):
                    until = _clean_name(a[i + 1]) if i + 1 < len(a) else None
                    i += 1
                elif w.lower() not in ("and", "for", "beats", "beat", "+", "&"):
                    names.append(w)
                i += 1
            if len(names) < 2:
                raise ValueError("Usage: /ally <name> <name> [beats] [until <name>]   e.g. /ally Nocturne Ripples until Seraphina")
            b = {"action": "ally", "attacker": names[0], "defender": "", "members": names, "beats": beats,
                 "until": until, "flavor": "", "_manual": True}
        s.play_beat(manual=b); return
    if cmd in ("fighters", "roster"):
        inn = s.lineup()
        sp = getattr(s.eng, "roster_species", {}) or {}
        print("In fighters.json: " + ", ".join(f"{n}{f' ({sp[n]})' if sp.get(n) else ''}{' [in this fight]' if n in inn else ''}"
                                               for n in s.eng.roster)
              + f"\nThis is fight {s.fight_no}. /newfight <names> starts a fresh one with the fighters you name "
                "(two or more); /newfight all brings everyone in."); return
    if cmd in ("newfight", "rematch", "restart"):
        names = [_clean_name(x).strip(",") for x in a if x.strip(",").lower() not in ("", "and", "vs", "vs.", "v", "&", "against", "versus")]
        if names and names[0].lower() in ("all", "everyone"):
            names = list(s.eng.roster)
        s.new_fight(names or None)
        print("Press Enter to begin."); return
    if cmd == "summary":
        print(s.eng.fight_summary() or "No winner yet: the summary comes when the fight is over."); return
    if cmd in ("simulate", "sim"):
        from simulate import simulate
        count = int(a[0]) if a and a[0].isdigit() else 20
        names = [_clean_name(x).strip(",") for x in (a[1:] if a and a[0].isdigit() else a)
                 if x.strip(",").lower() not in ("", "and", "vs", "vs.", "v", "&", "against", "versus")]
        names = [s.eng.match_roster(n) for n in names] if names else s.lineup()
        if len(set(names)) < 2:
            raise ValueError("a fight needs at least two different fighters")
        print(simulate(names, s.eng.rules, s.eng.scene_name if s.eng.scene_name in s.eng.scenes else None,
                       count=max(1, min(count, 1000))))
        return
    if cmd == "results":
        print(s.results_text()); return
    if cmd in ("autofight", "autofights"):
        return _autofight(s, a)
    if cmd == "auto" and a and a[0].isdigit() and len(a) > 1:
        # "/auto 2 3 Nocturne Ripples" is the whole-fights command: /auto alone only takes a number of beats
        print(f"(/auto takes only a number of beats. Reading this as: /autofight {' '.join(a)})")
        return _autofight(s, a)
    if cmd == "auto":
        if a and a[0].lower() == "pin":
            if not s.eng.pins:
                raise ValueError("no pin is running. Start one first (e.g. type: Nocturne pins Ripples)")
            STOP.clear()
            for _ in range(40):  # plays the pin out beat by beat until it ends: escape, faint, or release
                if s.over or not s.eng.pins:
                    break
                s.play_beat("continue the pin")
                if _stopped(s):
                    break
            return
        if a and not a[0].isdigit():
            raise ValueError("Usage: /auto <beats>   (or /auto pin).   For whole fights: /autofight <fights> "
                             "[aftermath beats] [names]")
        STOP.clear()
        if s.use_llm and not s.story and not s.over:
            s.play_beat()  # the opening scene doesn't count as one of the beats
        for _ in range(int(a[0]) if a else 5):
            if s.over or _stopped(s):
                break
            s.play_beat()
        _stopped(s)
        return
    if cmd == "stop":
        print("Nothing is running. (/stop ends /auto or /autofight after the beat being written: type it in the "
              "window while one runs. In a console window, Ctrl+C stops at once.)"); return
    b = manual_beat(cmd, a, s.eng)
    if b is None:
        raise ValueError(f"Unknown command '/{cmd}'")
    if b["attacker"] is None:
        # holds belong to their attacker; otherwise pick the first fighter as focus
        hid = b.get("hold_id")
        b["attacker"] = (s.eng.holds[hid].attacker if hid in s.eng.holds
                         else s.eng.active()[0].name)
    s.play_beat(manual=b)


def build_args(argv=None):
    """The command-line options (play.py and window.py take the same ones)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="mistral-small:24b")
    ap.add_argument("--director-model", default=None,
                    help="a different model for the director (picks attacks, JSON); default: --model")
    ap.add_argument("--narrator-model", default=None,
                    help="a different model for the narrator (writes the story); default: --model")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--hide-math", action="store_true", help="don't print stat blocks (toggle with /math)")
    ap.add_argument("--json", action="store_true", help="also print the raw engine result")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-autosave", action="store_true", help="don't write autosave.json every beat")
    ap.add_argument("--fighters", default="", help="who is in the first fight, e.g. Nocturne,Ripples (default: all)")
    ap.add_argument("--scene", default="", help="the arena, by name or number (see scenes.json); default: ask at the start")
    return ap.parse_args(argv)


def main():
    args = build_args()
    s = Session(args)
    if os.name == "nt":
        os.system("")  # lets a plain Windows terminal understand the bold/italic codes (Spyder already does)
    screen = sys.stdout
    if not isinstance(screen, StyledOut):
        sys.stdout = StyledOut(screen, s.eng.rules)
    try:
        _run(s, args)
    finally:
        sys.stdout = screen  # hand the console back as it was (matters when re-running inside Spyder)


def _run(s, args):
    print(f"Fight sim version: {VERSION}")
    print(f"Running: {os.path.abspath(__file__)}")
    if getattr(s.eng, "settings_applied", 0):
        print(f"Your saved settings: {s.eng.settings_applied} value(s) from my_settings.json applied over rules.json "
              f"(/settings lists them)")
    dm, nm = s.director.model, s.narrator.model   # what this run really uses (a /model choice is kept)
    print(f"Model: {nm}" + (f"  (director: {dm})" if dm != nm else "")
          + f"{'  (models off: --no-llm)' if args.no_llm else ''}\n")
    if getattr(args, "scene", ""):
        try:
            handle_command(s, "/scene " + args.scene)
        except ValueError as e:
            print(f"--scene: {e}")
    elif (s.eng.rules.get("setup") or {}).get("enabled", True):
        setup_questions(s)        # (since build 282) the questions before the run: preset, arena, fighters...
        print()
    elif len(s.eng.scenes) > 1 and s.eng.rules.get("scene", {}).get("ask_at_start", True):
        ask_scene(s)
        print()
    print(f"SCENE — {scene_summary(s.eng)}\n{s.eng.scene}\n")
    if variant_lines(s.eng):
        print(variant_lines(s.eng) + "\n")
    print(s.display.status(s.eng))
    if os.path.exists(AUTOSAVE):
        print("\n(A previous fight was autosaved. Type /load autosave to pick it up where it left off.)")
    print("\nPress Enter to begin. Type a direction to steer, or /help for commands.\n")
    if getattr(s, "_setup_auto", 0):
        # (since build 282) the setup's last question: let the director run that many beats now
        n_, s._setup_auto = s._setup_auto, 0
        try:
            handle_command(s, f"/auto {n_}")
        except ValueError as e:
            print(f"Error: {e}")

    while True:
        asked = s.play_order()[0] if s.use_llm and s.playing() else None
        try:
            if asked:
                s.play_panel(asked, first=True)
            line = input(f"{asked} > " if asked else "> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if asked and not line.startswith("/") and line not in ("+", "++", "...") and "&&" not in line:
            try:
                if s.play_turn(asked, line) == "quit":
                    break
            except llm.LLMError as e:
                print(f"[model unavailable: {e}]")
            except KeyboardInterrupt:
                print("\n(Stopped. Everything up to the last finished beat is kept; if a beat was cut off halfway, "
                      "/undo takes it back or /reroll writes its story.)")
            except (ValueError, IndexError, KeyError) as e:
                print(f"Error: {e}  (type /help)")
            continue
        pieces = split_commands(line) if "&&" in line else [line]
        quit_now = False
        for piece in pieces:
            if len(pieces) > 1:
                print(f"» {piece}")
            try:
                if piece in ("+", "++", "..."):
                    piece = "/more"  # stay in the moment instead of moving on
                if piece.startswith("/"):
                    if handle_command(s, piece) == "quit":
                        quit_now = True
                        break
                else:
                    s.play_beat(direction=piece)
            except llm.LLMError as e:
                print(f"[model unavailable: {e}]")
                break  # don't run the rest of the chain on a dead model
            except KeyboardInterrupt:
                print("\n(Stopped. Everything up to the last finished beat is kept; if a beat was cut off halfway, "
                      "/undo takes it back or /reroll writes its story.)")
                break
            except (ValueError, IndexError, KeyError) as e:
                print(f"Error: {e}  (type /help)")
                if len(pieces) > 1:
                    print("(stopped here; the commands before this one still happened)")
                break
        if quit_now:
            break


if __name__ == "__main__":
    main()
