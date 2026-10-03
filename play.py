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
import shlex
import sys

from director import Director, resolve_many
from display import Display
from engine import Engine, body_region as body_region_of
from narrator import Narrator
import llm

VERSION = "2026-10-03 build 113 (Aqua Jet stays on her and costs more; pummels on the ground, in a pin and against the scenery; each blow picks its own spot; raw reactions on hurt parts. Build 112: body parts weigh on overall health by how vital they are: /vital; wear by damage: /wear; an ending broken off on purpose is kept. Build 111: fixes from a live test fight: paragraphs opening with Before/After are no longer deleted, nine kinds of needless rewrite gone, blocks that follow the moment; pain pass-out share, answered pummels, rarer sleeper. Build 110: mechanics. Build 109: story blocks)"

HELP = """
=============================================================================================
 PLAYING
=============================================================================================
  [Enter]                     the director picks the next beat
  <any text>                  your direction for the next beat ("Ripples goes for the throat")
  /auto <n>                   let the director run n beats on its own (for whole fights: /autofight)
  /auto pin                   play the running pin out, beat by beat, until it ends
  /wait [what happens]        a beat with no new attack (holds and pins keep going)
  /more [words] [what to dwell on]   (or just +)  STAY in the moment instead of moving on: more paragraphs about
                              the stillness and what the last blows left behind. Nothing happens and no time passes
                              (no new attack, no pin seconds, no get-up roll); use it as often as you like.
                                +        /more 400        /more "Ripples' ruined shoulder, and Nocturne watching"
  /more auto <0-3>            add that many such passages after every beat with an attack, on their own
  cmd && cmd && ...           run several commands in a row, one beat each
                                e.g.  /scale 5 && /pinbeat 5 && Nocturne goes for the pin
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
  /pinstart [mult]                          the same for a pin's presses (0 by default: a pin starts hurting next beat)
  /pinshape [name number]                   how often each way of building a pin is suggested (jaws on the throat, jaws
                                            pinning a paw, a tail choke, a twisted arm, tangled legs, a lifted leg)
  /secure on [parts] [part%] [strength%] | off
        Pins can only be WON once she's worn down enough (early escapes still happen).
          /secure on 6 150 50     (6 parts at 150%+ and strength at 50% or less)

=============================================================================================
 STEERING THE STORY   (nudges for the director; the dice still decide)
=============================================================================================
  /plan close [winner]   /plan dominate <name>   /plan comeback <name>
  /plan even             /plan winner <name>     /plan off
  /targeting one|few|many|all|auto          how many body parts attacks spread across
  /focus [fighter] <zones...|off>           where attacks aim: head, core, arms, legs, paws, tail,
                                            limbs, upper (combine: /focus core head). Saved to rules.json.
          /focus injured           go back to what's already hurt and the parts around it (and a badly hurt
                                   side as a whole); the worse a part is, the more often. Combines: /focus injured legs
          /focus core              everyone aims at the body
          /focus Nocturne limbs    only Nocturne's attacks go for arms, legs and paws
          /focus strength 0.8      how firmly off-target picks get moved onto the zone (0 = nudge only)

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
 RULES AND FIGHTERS   (changes are saved to rules.json unless noted)
=============================================================================================
  /scale [n]          how hard every hit lands on body parts (default 1.25)
  /healthloss [n]     how much health each point of body-part damage costs (default 0.5)
  /resscale [n]       how fast body-part resistance wears down (separate from /scale)
  /wear [n]           resistance ALSO lost per 1% of damage a hit really does (0 = off)   /wear 0.05
  /vital [word n | on | off]   how much each body part matters to overall health (a throat more, an ear far less)
                      /vital = show every part's weight      /vital ear 0.3      /vital off = all parts count the same
  /talk quiet|less|normal|free   how much the fighters speak and think in italics (default: less)
  /style on|off|auto  real bold and italic on screen instead of **asterisks** (auto: on in Spyder and terminals)
  /style color <name> give the bold parts a colour too (yellow, cyan, green...; none = plain bold)
  /numb [on|off]      the "numb with shock" pain level at 1000%+ (off: those parts stay devastated)
  /words [n]          narration length per beat
  /blocks [on|off|n|reset]   story building blocks (story_blocks.txt): ideas for reactions, sensations, what an
                      opponent can see of an injury, ways to stage a move, thoughts and more, offered to the
                      narrator a few at a time when they fit the fight, the least-offered first. /blocks shows the
                      counts; /blocks 6 = at most six per part; /blocks reset forgets what has been offered.
  /sample [name]      which style sample the narrator imitates. /sample lists them; /sample 1 or /sample
                      style_sample.txt switches (saved). style_sample_scenes.txt is written in sections, and the
                      narrator is shown the passage that fits the part it is about to write.
  /timing [on|off|clear]   after each beat the program says how long it took, how fast the model wrote, and what
                      had to be written again. /timing alone: the averages so far, by narrator model (for
                      comparing two models: play some beats on each, then /timing).
  /model [narrator|director] [name]   which Ollama model writes the story / picks what happens (this session).
                      /model narrator gemma4:31b   /model   (shows both)
  /repair on|off        on (default): a paragraph with a mistake is written again by itself and the rest of the
                        part stays word for word. off: the whole part is rewritten for any problem
  /reader on|off        on (default): after each part, the model reads it back against the beat's facts and
                        the paragraphs it finds contradictions in are written again (one short extra call)
  /reader model <name>  have a different Ollama model do that reading (/reader model same = the narrator's)
  /reader cpu on|off    run that other model on the CPU, in system memory, so the narrator stays on the graphics card
  /reader confirm on|off  off (default): on = each thing the reading finds is asked about a second time before
                        any paragraph is rewritten for it (fewer rewrites, but it can talk itself out of a real find)
  /layout clear|tight|classic  how the stat math is laid out. clear (default): each hit as three labelled rows
                        (damage, resistance, health: before → after, then the math), blocks spaced out, one chance
                        roll per line. tight: one unlabelled row per hit, packed. classic: the long Before /
                        Calculations / After blocks
  /math auto|full|compact|both|off      how much of the stat math to show
  /get [rule.path]                      show rules            /get pin.struggle
  /set <rule.path> <value> [nosave]     change any rule       /set narration.swearing never
  /fighter <name> <field> [value] [beats]
        fields: health, maxhealth, energy, status, clearstatus, down, up, recovery, revive
          /fighter Ripples health 900     /fighter Nocturne status paralyzed 2
  /part <name> "<Part>" damage|resistance <value>      /part Ripples "Right Paw" damage 120
  /style <text>       an extra style note for the narrator this session
  /scene [name|number|random]   the arenas (scenes.json): /scene lists them; /scene 3 or /scene power plant
                      switches. /scene <a sentence of your own> makes an arena from your description (things
                      named in it can be landed on; nothing in it is tracked as a hazard).
  /hazards [on|off|chance <n>]  what this arena does: its hazards (burns, chills, drenches... when a fighter lands
                      on or is driven into them) and its events (things the place does by itself now and then)
  /hazard <event> [fighter]     make one of the arena's events happen at the end of the next beat

=============================================================================================
 LOOKING AROUND
=============================================================================================
  /status [full|name]   health, worst injuries, pins and positions
  /health [name]        every damaged body part, in stat format
  /look [name]          the narrator describes the scene right now (doesn't advance the fight)

=============================================================================================
 UNDO, FILES, QUIT
=============================================================================================
  /undo [n]             take back the last beat (or n beats): stats, story, pins, everything
  /reroll               rewrite the last beat's narration (stats unchanged)
  /export [file] [prose]    write every fight this session to a .md file ("prose" = story only)
  /settings             what you changed with commands (kept in my_settings.json; a new build doesn't reset it)
  /settings forget      drop them, so the next build's defaults apply
  /save [file]   /load [file]   (every beat autosaves: /load autosave)
  /help   /quit
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
            + f" · narrator: {row['narrator']}")


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
        self.director = Director(getattr(args, "director_model", None) or args.model, host=args.host)
        self.narrator = Narrator(getattr(args, "narrator_model", None) or args.model, self.eng.rules, host=args.host)
        self.narrator.progress = self.progress
        self.story = []
        self.over = False
        self.display = Display(self.eng.rules)
        self.show_math = not args.hide_math
        self.math_mode = "auto"  # auto: full blocks for attacks, compact lines for pin/hold beats
        self.attacks = 0
        self.recent_attacks = []  # for the director's variety check
        self.transcript = []      # everything shown, for /export
        self.timings = []         # one row per beat: seconds, model calls, what was written again
        self.history = []         # snapshots for /undo
        self.last_narration = None  # what the last beat's prose was written from, for /reroll
        self.pending = None         # a beat whose narration failed, waiting for /reroll
        self.autosave_enabled = not getattr(args, "no_autosave", False)

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

    def play_beat(self, direction="", manual=None):
        """One beat, and then how long it took and what had to be written again (console -> timing, /timing)."""
        before, t0 = dict(llm.stats), time.time()
        BEAT_TALLY.clear()
        try:
            return self._play_beat(direction, manual)
        finally:
            d = {k: llm.stats[k] - before.get(k, 0) for k in llm.stats}
            if d["calls"] > 0:
                row = {"seconds": time.time() - t0, "narrator": self.narrator.model, "director": self.director.model,
                       **d, **{k: BEAT_TALLY.get(k, 0) for k in ("paragraphs", "whole parts", "second drafts", "top-ups")}}
                self.timings.append(row)
                if self.eng.rules.get("console", {}).get("timing", True):
                    print(timing_line(row))

    # ---------- undo / reroll / save ----------
    def _snapshot(self):
        return (self.eng.snapshot_state(), list(self.story), self.attacks, list(self.recent_attacks), self.over,
                len(self.transcript), self.last_narration, self.pending)

    def push_history(self):
        self.history.append(self._snapshot())
        self.history = self.history[-30:]

    def undo(self):
        if not self.history:
            raise ValueError("nothing to undo")
        (eng, story, attacks, recent, over, tlen, last, pending) = self.history.pop()
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

    def _extra(self):
        return {"story": self.story, "style": self.narrator.style, "over": self.over,
                "transcript": self.transcript[-4000:], "attacks": self.attacks,
                "recent_attacks": self.recent_attacks, "fight_no": self.fight_no, "results": self.results,
                "story_before": self.story_before[-400:]}

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
        for i in range(count):
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
        self.history, self.last_narration, self.pending = [], None, None

    def _write_prose(self, args):
        """Run the narrator. On a model failure the beat's stats still stand; /reroll can narrate it later."""
        try:
            return self.narrator.narrate(*args)
        except llm.LLMError as e:
            self.pending = {"args": args}
            self.out(f"\n[narration failed: {e}]\n[The stats below are already applied. Type /reroll to narrate "
                     f"this beat, or /undo to take the whole beat back.]\n")
            return None

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
        self.narrator.max_health = {f.name: f.max_health for f in self.eng.fighters.values()}
        self.narrator.on_ground = set(self.eng.downed) | {pin["defender"] for pin in self.eng.pins.values()}
        self.narrator.on_ground |= set(getattr(self, "_rising", set()))
        # anyone who was down when the beat began (then got up, was hauled up, or broke free) may be shown lying too
        self.narrator.on_ground |= set(getattr(self, "_start_down", set()))
        self.narrator.facing = {f.name: self.eng.facing_of(f.name) for f in self.eng.fighters.values()
                                if self.eng.facing_of(f.name)}
        self.narrator.aliases = {self.eng.species(f): f.name for f in self.eng.fighters.values() if self.eng.species(f)}
        self._sync_absent()
        self.narrator.out_names = [f.name for f in self.eng.fighters.values() if f.eliminated]
        try:
            self.narrator.story_state = None if self.over else self.eng.story_state()
        except Exception:
            self.narrator.story_state = None
        self.narrator.silent_out = [] if self.over else [
            w for f in self.eng.fighters.values()
            if f.eliminated and f.name not in getattr(self, "_was_in", set()) and not self.eng.has_hurt_anyone(f.name)
            for w in (f.name, self.eng.species(f)) if w]
        self.narrator.posture_end = {f.name: self.eng.posture_text(f.name, short=True) for f in self.eng.active()}
        self.narrator.scene_cfg = self.eng.scene_cfg   # the arena's own words (ground, place, ambience)
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
        self.narrator.injury_log = {k: list(v) for k, v in self.eng.injury_log.items()}   # for one memory a beat
        self.narrator.tally = dict(getattr(self.eng, "tally", {}) or {})   # for counts in the story ("thrown twice")
        # every grip that is still on now: the story may not let one go on its own
        self.narrator.grips = [(h.attacker, h.defender, h.part, h.with_part) for h in self.eng.holds.values()]
        # moves that have only ever been dodged in this fight: the story may not remember them as blows that landed
        dodged = {m.group(1).strip() for x in self.recent_attacks
                  for m in [re.match(r"[^:]+: (.+?)(?: \(improvised\))? → .* DODGED it", x)] if m}
        landed = {m.group(1).strip() for x in self.recent_attacks if "DODGED it" not in x
                  for m in [re.match(r"[^:]+: (.+?)(?: \((?:improvised|a charge[^)]*)\))* → ", x)] if m}
        self.narrator.missed_moves = sorted(dodged - landed)
        self.narrator.posture_start = dict(getattr(self, "_posture_start", {}))
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
    def notes(self):
        multi_team = any(f.team != f.name for f in self.eng.fighters.values())
        lines = []
        for f in self.eng.fighters.values():
            if f.eliminated and not self.over and f.name not in getattr(self, "_was_in", set()):
                # out of the fight and out of the story until the aftermath (but not on the beat they go down)
                lines.append(f"{f.name} [OUT of the fight; not part of this story now]: "
                             + (f.appearance.split(".")[0] + "." if f.appearance else ""))
                continue
            lines.append(self._note(f, multi_team))
        return "\n".join(lines)

    def _note(self, f, multi_team):
        return (
            f"{f.name}{f' (team {f.team})' if multi_team else ''}"
            f"{' [ELIMINATED]' if f.eliminated else ''}: {f.description}"
            + (f" APPEARANCE: {f.appearance}" if getattr(f, "appearance", "") else "")
            + (f" TELLS (how she shows pain and effort): {f.tells}" if getattr(f, "tells", "") else "")
            + (f" VOICE: {f.voice}" if getattr(f, "voice", "") else ""))

    def recent_story(self, n=None):
        n = n or self.eng.rules.get("narration", {}).get("recent_beats_remembered", 2)
        n = max(n, 3)  # the repeat filter checks at least the last 3 beats
        return "\n\n".join(self.story[-n:])

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
            text = self.narrator.intro(self.eng.scene, self.notes())
        except llm.LLMError:
            self.history.pop()
            raise
        self.out("\n" + text + "\n")
        self.story.append(text)
        self.autosave()

    def _play_beat(self, direction="", manual=None):
        aftermath = self.over
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
        if manual is None and self.use_llm and not self.story:
            self.intro()  # first Enter sets the scene; the next one starts the fight
            if not direction:
                return
        self.push_history()
        self.eng.rolls, self.eng.nudges = [], []  # this beat's dice, from here on
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
                    self.eng, self.eng.scene, self.recent_story(), direction, self.recent_attacks)
        except Exception:
            self.history.pop()  # nothing happened, so there's nothing to undo
            raise
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
                if res.get("charge") and not res["charge"].get("skipped"):
                    what += f" (a charge that drove her into {res['charge']['into']})"
                self.recent_attacks.append(f"{res['attacker']}: {what} → {poss_name(res['defender'])} {', '.join(parts[:3])}"
                                           if not res.get("dodged") or res.get("hits") else
                                           f"{res['attacker']}: {what} → {res['defender']} DODGED it"
                                           + (" and countered" if res.get("counter_hits") else ""))
            elif res.get("type") in ("hold_start", "pin_start"):
                self.recent_attacks.append(f"{res['attacker']}: {'pin' if res['type'] == 'pin_start' else 'hold'} on "
                                           f"{res['defender']}")
        also = self.eng.beat(skip_hold_ids=started)
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
        bundle = {"actions": results, "also_this_beat": also, "after_win": aftermath}
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
            condition = (self.eng.narrator_condition() + "\nFIGHT SO FAR (the ONLY earlier attacks that really "
                         "happened; never mention any other past attack or move):\n" + past)
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
            text = self._write_prose(args)
            if text is not None:
                self.out("\n" + text + "\n")
                self.story.append(text)
                self.last_narration = {"args": args, "index": len(self.story) - 1}
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
                                                             "status_end", "recovery", "alliance_end")]
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
                self.out(f"*** {e['defender']} faints after {e['seconds_to'] if e.get('fade_mode') else e['duration']} "
                         f"seconds pinned by {e['attacker']}. ***")
            if e.get("type") == "pin_progress" and e.get("struggle") == "escape":
                self.out(f"*** {e['defender']} kicks out at the last second of {poss_name(e['attacker'])} pin! "
                         f"(can't be won yet: {e.get('why_not', '')}) ***" if e.get("last_second") else
                         f"*** {e['defender']} breaks free of {poss_name(e['attacker'])} pin at second {e['seconds_to']}! ***")
        for e in also:
            if e.get("type") == "recovery" and aftermath:
                self.out(f"*** {e['fighter']}: {e['from']} → {e['to']} ***")
        if not aftermath and any(r.get("type") == "eliminated" or r.get("elimination")
               or (r.get("type") == "pinfall" and r.get("result") == "pinned") for r in results) or any(
                e.get("type") == "pin_progress" and e.get("elimination") for e in also):
            winner = self.eng.winner()
            if winner:
                self.over = True
                self.record_result()
                self.out(f"*** Winner: {winner} ***\n(The match is over. Keep pressing Enter to watch the aftermath: "
                         f"the loser may stir and even get back up. Type what happens to steer it, or /undo.)\n")
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


def poss_name(name):
    return f"{name}'" if name.endswith("s") else f"{name}'s"


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


def ask_scene(s, read=input):
    """At the start of a run: which arena? Enter keeps the last one."""
    eng = s.eng
    print(scene_list(eng))
    print(f"Type a number or a name, r for a random one, or just press Enter to stay in "
          f"{eng.scene_cfg.get('title', 'the same arena')}. (Turn this question off: /set scene.ask_at_start false)")
    for _ in range(4):
        try:
            line = read("Scene> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not line:
            return
        if line.startswith("/"):
            line = line.lstrip("/").replace("scene", "", 1).strip() or ""
            if not line:
                continue
        try:
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):   # the arena is printed once, just below
                handle_command(s, "/scene " + line)
            return
        except ValueError as e:
            print(f"Error: {e}")


def _clean_name(x):
    return str(x).strip().strip("<>[]").strip()


# ---------- bold and italic on screen ----------
ANSI_COLORS = {"red": 31, "green": 32, "yellow": 33, "blue": 34, "magenta": 35, "cyan": 36, "white": 37}
_BANNER = re.compile(r"\*\*\*[ \t]*([^*\n]+?)[ \t]*\*\*\*")
_BOLD = re.compile(r"\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?![\s*])([^*\n]+?)(?<![\s*])\*(?![*\w])")


def style_text(text, color=""):
    """Turn the **bold** and *italic* marks in a piece of output into the codes a console understands."""
    on = "\x1b[1m" + (f"\x1b[{ANSI_COLORS[color]}m" if color in ANSI_COLORS else "")
    off = "\x1b[22m" + ("\x1b[39m" if color in ANSI_COLORS else "")
    text = _BANNER.sub(lambda m: f"{on}{m.group(1)}{off}", text)
    text = _BOLD.sub(lambda m: f"{on}{m.group(1)}{off}", text)
    return _ITALIC.sub(lambda m: f"\x1b[3m{m.group(1)}\x1b[23m", text)


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
            text = style_text(text, str(self.rules.get("console", {}).get("bold_color", "") or "").lower())
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
        parts = [x.strip() for x in a[3].split(",")] if len(a) > 3 and not a[3].isdigit() else []
        count = int(a[-1]) if len(a) > 3 and a[-1].isdigit() else 1
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
        with open(MY_SETTINGS, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except (OSError, ValueError, TypeError) as e:
        print(f"[couldn't update my_settings.json: {e}]")


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
            raise ValueError(f"no rule '{'.'.join(keys[:i + 1])}'. Options: "
                             f"{', '.join(x for x in node if not x.startswith('_')) if isinstance(node, dict) else '(none)'}")
        node = node[k]
    if not isinstance(node, dict) or keys[-1] not in node:
        raise ValueError(f"no rule '{path}'. Options here: "
                         f"{', '.join(x for x in node if not x.startswith('_')) if isinstance(node, dict) else '(none)'}")
    return node, keys[-1], keys


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
    rng_word = "close" if m.get("target", "targeted") in ("targeted", "hold") else "ranged"
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


def handle_command(s, line):
    if SAME_BEAT.search(line):
        # several attack commands joined with " + " happen in the same beat (up to three), so a follow-up can land
        # before the first one's consequences play out: before a charged fighter crumples, say
        beats = []
        for piece in SAME_BEAT.split(line)[:3]:
            bits = shlex.split(piece.strip()[1:])
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
    parts = shlex.split(line[1:])
    if not parts:
        return
    cmd, a = parts[0].lower(), parts[1:]
    if cmd in ("quit", "exit"):
        return "quit"
    if cmd == "help":
        print(HELP); return
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
            focus.pop(who, None)
            msg = "off"
        else:
            zones = [z.lower() for z in " ".join(a).replace("+", " ").replace(",", " ").split()]
            zones = ["injured" if z in ("hurt", "wounded", "injuries") else z for z in zones]
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
                  f"both (pull it in Ollama first). To keep it, start play.py with --narrator-model <name>."); return
        which = a[0].lower() if a[0].lower() in ("narrator", "director", "both") and len(a) > 1 else "both"
        name = " ".join(a[1:] if a[0].lower() in ("narrator", "director", "both") and len(a) > 1 else a).strip()
        if which in ("narrator", "both"):
            s.narrator.model = name
        if which in ("director", "both"):
            s.director.model = name
        print(f"Narrator: {s.narrator.model}\nDirector: {s.director.model}\n(this session; the first beat on a new "
              f"model is slow while Ollama loads it)"); return
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
                 "getup_rise": "how she finally rises"}
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
    if cmd == "export":
        prose_only = any(x.lower() == "prose" for x in a)
        names = [x for x in a if x.lower() != "prose"]
        path = _path(names[0] if names else "story_export", ".md")
        with open(path, "w", encoding="utf-8") as fh:
            now = ([f"## Fight {s.fight_no}: {' vs '.join(s.lineup())}"] if s.story_before else []) + s.story
            fh.write("\n\n".join(s.story_before + now) if prose_only else "\n".join(s.transcript))
        print(f"Exported {'the story (prose only)' if prose_only else 'everything (prose and stats)'} to {path}"); return
    if cmd == "scale":
        cur = s.eng.rules.setdefault("damage", {}).get("damage_scale", 1.0)
        if not a:
            print(f"Damage scale is {cur}. Change it with /scale <number>, e.g. /scale 3"); return
        new = float(a[0])
        if new <= 0:
            raise ValueError("scale must be above 0")
        s.eng.rules["damage"]["damage_scale"] = new
        if new >= 10:
            print(f"Note: at {new}x a single solid hit does roughly {round(60 * 0.4 * new)}% to a sturdy body part; "
                  f"fights will end in a few hits. /scale 1.25 is the default.")
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
        print("In fighters.json: " + ", ".join(f"{n}{' (in this fight)' if n in inn else ''}" for n in s.eng.roster)
              + f"\nThis is fight {s.fight_no}. /newfight <names> starts a fresh one with the fighters you name "
                "(two or more); /newfight all brings everyone in."); return
    if cmd in ("newfight", "rematch", "restart"):
        names = [_clean_name(x).strip(",") for x in a if x.strip(",").lower() not in ("", "and", "vs", "vs.", "v", "&", "against", "versus")]
        if names and names[0].lower() in ("all", "everyone"):
            names = list(s.eng.roster)
        s.new_fight(names or None)
        print("Press Enter to begin."); return
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
            for _ in range(40):  # plays the pin out beat by beat until it ends: escape, faint, or release
                if s.over or not s.eng.pins:
                    break
                s.play_beat("continue the pin")
            return
        if a and not a[0].isdigit():
            raise ValueError("Usage: /auto <beats>   (or /auto pin).   For whole fights: /autofight <fights> "
                             "[aftermath beats] [names]")
        if s.use_llm and not s.story and not s.over:
            s.play_beat()  # the opening scene doesn't count as one of the beats
        for _ in range(int(a[0]) if a else 5):
            if s.over:
                break
            s.play_beat()
        return
    b = manual_beat(cmd, a, s.eng)
    if b is None:
        raise ValueError(f"Unknown command '/{cmd}'")
    if b["attacker"] is None:
        # holds belong to their attacker; otherwise pick the first fighter as focus
        hid = b.get("hold_id")
        b["attacker"] = (s.eng.holds[hid].attacker if hid in s.eng.holds
                         else s.eng.active()[0].name)
    s.play_beat(manual=b)


def main():
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
    args = ap.parse_args()

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
    dm, nm = args.director_model or args.model, args.narrator_model or args.model
    print(f"Model: {nm}" + (f"  (director: {dm})" if dm != nm else "")
          + f"{'  (models off: --no-llm)' if args.no_llm else ''}\n")
    if getattr(args, "scene", ""):
        try:
            handle_command(s, "/scene " + args.scene)
        except ValueError as e:
            print(f"--scene: {e}")
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

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
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
