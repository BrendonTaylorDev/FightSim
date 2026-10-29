"""
Director: the model decides WHO does WHAT next, as structured JSON.
It picks moves and severity words; the engine turns those into numbers and resolves them.
The director can SEE the numbers but never calculates anything.
"""
import json
import re
from engine import note_failure, ordinal, short_phrase, poss_word, body_region, _BODY_REGION_NEAR as _BODY_NEAR, match_part, \
    _REGIONS as ENGINE_REGIONS
from blocks import kind_of

import llm
import userprompt

ACTIONS = ["strike", "combo", "hold_start", "hold_adjust", "hold_release", "pin", "struggle", "throw", "slam", "drag",
           "grapple", "submission", "eliminate", "breather"]
LAUNCHES = ["none", "staggered", "knocked down", "thrown", "launched"]
REPOSITIONS = ["none", "roll over", "onto her back", "onto her front", "onto her side", "sit her up", "pick up",
               "stand her up", "take off", "land"]


def director_actions(engine):
    """The actions the director may choose. Eliminating someone directly is off unless rules.json allows it:
    then only a completed pin puts a fighter out."""
    if engine.rules.get("pin", {}).get("director_can_eliminate", False):
        return ACTIONS
    return [a for a in ACTIONS if a != "eliminate"]

DIRECTOR_PROMPT = """You are the fight director for an ongoing story. You decide what happens NEXT, one beat at a time.
There are no turns. Anyone can act as many times in a row as the story calls for: a fighter with momentum can
keep pressing, a hurt fighter can be overwhelmed, an opening can flip the fight in one move.

Also return "positions": WHERE every fighter still in the fight is after this beat, one short clause each (the
place, what's near her, what she's touching), e.g. "Nocturne: on the dry center ledge, favoring her left
foreleg; Ripples: in the shallow pool, under Nocturne". Only fighters listed under CURRENT CONDITIONS exist. The ENGINE
decides who is standing, who is on the ground, which way she lies, and who is pinned: those are the CAPITALS in
POSITIONS NOW, and they are certain. Only this beat's actions change them (a knockdown, throw, launch, pin, roll,
or lift); getting up and breaking a pin are rolled by the engine afterwards. So never stand anyone up, lay anyone
down, turn anyone over, or end a pin in this line: describe the place, and plan from POSITIONS NOW.

Return the next beat as JSON with an "actions" list. A beat is usually ONE action. Use 2 or 3 actions only
when several things happen together, in order: two fighters attacking at the same time, a strike that knocks
someone down followed by a pin, a throw followed by the hard landing (an environmental hit with "move": "none"),
a grab followed by what it sets up, or a CHAIN of attacks by one fighter (see CHAINS below; only a chain may
run past three actions).
If the user asks for several things at once ("both attack", "knock her down and pin her"), put each in the list.

BIG HITS MOVE BODIES. Pokemon moves are powerful: a solid hit rarely touches just one spot.
- List every part a blow really catches: a jaw uppercut also snaps the head back and jars the neck; a body
  charge catches chest, shoulder and ribs. (The engine also adds a lighter knock to the parts right next to a
  single named target.)
- "launch" says what a strike does to the defender's body: "none", "staggered" (rocked but on their feet),
  "knocked down", "thrown", or "launched" (sent flying). Use knockdowns, throws and launches OFTEN for heavy
  hits, slams, charges, tail sweeps and water blasts. A "knocked down" is not certain: the engine rolls whether
  she keeps her feet (likelier while she is strong or the blow is light), and the story follows the roll.
- "reposition" (usually "none"): before the action, the attacker moves an opponent who is ON THE GROUND:
  "roll over" (flip her), "onto her back", "onto her front", "onto her side"; "sit her up" (haul her up to
  sitting: she is still on the ground, but her chest, belly and throat in front and her back and neck behind are
  all in reach, for a strike or for a choke from behind); "pick up" (lift her bodily off the ground: to slam her
  back down or throw her); or "stand her up" (drag her onto her feet and hold her there to be hit standing).
  The last three can't be done to a fighter who is pinned.
- "feint" (usually false): true when the attacker FAKES first and then throws the real blow. If the defender bites,
  she can't dodge, clash or guard it and it lands on her caught open; if she reads it, it's an ordinary attack.
  Use it now and then, never every beat. A JUGGLE: a strike that "launch"es her as the first link of a CHAIN and a
  second strike on her as the next link catches her in the air, helpless, and smashes her back down (both land
  harder). A WINGED fighter may instead "take off" (she rises
  into the air before her action: only beams, blasts and streams reach her there, and her close moves become
  dives from above) or "land" (she comes down by choice). A fighter in the air can't be grabbed or pinned; a
  wing hurt badly enough brings her down. Carry moves (Sky Drop) need her in the air first. "carry" (usually
  false): true on a close STRIKE by a winged fighter already in the air, with talons, feet or hands to grip: she
  seizes the one on the ground and hauls her up (the engine rolls whether she can lift her) and lets her fall.
  The higher she takes her, the harder she lands. As she falls, the NEXT links of the same CHAIN can catch her:
  slashes on the way down (from high up, more than one), or a SPIKE: a dive, a charge, or a held stream from
  ABOVE that drives her straight down into the ground faster than she'd fall (big damage, a far harder landing).
  "leap_from" (usually ""): a fighter ON THE GROUND whose foe is IN THE AIR may climb something high in the arena (a
  boulder, a tree, a pillar: the arena's high ground is listed in the notes) and LEAP at her with a close STRIKE: put
  the thing she climbs here. The engine rolls whether she reaches her (she may drag the flyer down with her); if she
  falls short she drops from the height and lands badly. It costs her energy; use it now and then, not every beat.
  A rare, big moment, not a habit. Flying is a winged
  fighter's strength: she takes to the air every few beats, not rarely. The other repositions: use one NOW AND THEN, rarely, when it serves the moment
  (rolling her to reach her throat or chest for a pin, flipping her face-down to press her back, sitting her up
  for a blow to the chest, lifting her for a slam): most beats leave her where she lies. A running pin's presses
  follow a roll. A fighter who is sitting up is knocked flat again by the next blow that lands on her.
- "landing" lists what a knocked-down, thrown or launched fighter crashes into, in order, using the SCENE's
  features: e.g. [{"surface": "a stalactite", "parts": ["Upper Back", "Head"], "severity": "heavy"},
  {"surface": "a fallen boulder", "parts": ["Left Shoulder", "Left Ribs"], "severity": "solid"},
  {"surface": "the stone floor", "parts": ["Back", "Left Hip", "Tail Base"], "severity": "solid"}].
  Each surface hits its own set of parts (2-5 parts each). Water cushions: a landing in a pool is "light".
  Leave "landing" empty when there's no fall.

MOVES: these are Pokemon. Most attacks should be one of the ATTACKER's own named moves (listed under their
name), put in "move". The engine applies type effectiveness and targeting:
- targeted moves hit ONE body part hard (put it in "part"; use "count" for rapid repeats like Fury Swipes).
  If the strike drags across neighboring parts (a claw rake across arm, fin and paw), also list those in
  "hits": they take a lighter carry-over hit;
- spread moves hit several parts at once (list them in "hits"), e.g. a water blast across chest, shoulders, neck;
- whole_body moves hit EVERY body part (e.g. Thunderbolt) - no parts needed;
- hold moves start a hold or pin (list the pressed parts in "hits").
- SUSTAINED moves (only moves marked "sustainable": streams and beams like Hydro Pump, Flamethrower, Ice Beam):
  NOW AND THEN, for a big moment, hold it: "sustain": 2-4 pulses (0 = a normal single blast). Put a SCENE feature
  in "pinned_against" ("a fallen boulder", "a stalagmite", "the cave wall") to drive the target back and press her
  into it: each pulse hits again AND slams her into it (extra environmental damage), and it may break under her,
  ending the move early. Be creative with it: blast her off her feet into a boulder and hold her there, pin her
  to the wall with a stream, catch her mid-charge. It costs extra energy per pulse. Most beats use sustain 0.
  A stream or beam is NEVER a hold_start or a pin (those are grips with the body: jaws, coils, tails, weight).
  To keep one on her or press her against something with it, use the move itself (action "combo", the parts it
  hits in "hits") with "sustain" and "pinned_against".
- status moves (Hypnosis, Thunder Wave, Will-O-Wisp, Toxic, Confuse Ray...) do no damage; they may put the target
  to sleep, paralyze, confuse, burn, or poison her (the engine rolls it). A sleeping or frozen fighter can't act or
  dodge; a confused one may hurt herself; burns and poison wear her down every beat. Some moves also knock down,
  throw, or launch on their own (listed with the move).
- CHARGES (moves marked "charge": Take Down, Aqua Jet, Dragon Rush...; or an improvised charge such as "shoulder
  ram" or "body charge"): NOW AND THEN, for a big moment, the charge doesn't stop at the hit. Put a SCENE feature
  in "charge_into" ("a fallen boulder", "a stalagmite", "the cave wall"): the attacker keeps driving the target
  backward across the ground and SLAMS her into it, her own body crushing against the target's front while the
  surface takes her back (extra environmental damage; it may break). Both must be on their feet. The target is
  left pressed against it for a moment: a second action in the same beat (a follow-up strike or bite, or a pin if
  one is allowed) lands BEFORE she falls and can't be dodged. The fighter who was charged can't act in that beat:
  she is pinned to the surface until it ends. At the end of the beat she usually crumples to the ground; the
  engine rolls it. For the beat after that she is REELING: she can strike back, but can't start or join a pin. Leave "charge_into" empty for an ordinary hit, and don't also set "launch".
IMPROVISED MOVES: fighters are not limited to their move list. Invent attacks that fit their bodies and
the moment - a headbutt, a pounce, a shoulder check, a tail-whip to the ear, a horn hook, a scratch across the
face, a shove into a pool, a throw, a pin-breaking kick - with "move": "improvised", a short "improvised_name"
(2-4 words), an "improvised_type" (usually Normal, or the fighter's own type), a severity for how hard it
lands, and the part(s) it hits. The engine tracks it like any other move.
Use "move": "none" only for environmental damage: slammed into a wall, landing on stone, dragged across rock.
Improvise from what her body really has (a Buizel's twin tails, forearm fins and jaws; a bird's beak, talons and
wings) and from a power she really has: an improvised move is Normal or Fighting, or a type of her own or of a move
she knows. "conjure" (usually ""): she MAKES A WEAPON of her own element and keeps it a few beats, named here (a
Water and Ice fighter freezing lake water into a blade, a Water fighter spinning a whip of water): it goes with an
improvised strike of that type that uses it, and her improvised blows with it land as that type, a little harder,
until it is gone.

RANGE: mix close-range attacks (claws, bites, tackles, holds) with ranged and special ones (beams, blasts, pulses,
waves, lightning, sound, status moves like Hypnosis or Thunder Wave). Pokemon battles use both; roughly a third
or more of attacks should be ranged when the fighters have ranged moves. Each move is marked close or ranged.
VARIETY: never use the same move three beats in a row, and don't let any fighter lean on one or two moves.
Rotate named moves and improvised techniques, mix strikes with grapples, throws, feints, holds, and using the
terrain and water. Check RECENT ATTACKS and pick something different unless the story demands a repeat.
Think about type matchups: super-effective moves are a smart choice; a fighter standing in water is
very vulnerable to Electric moves.

Beat types:
- strike: one fighter hits ONE body part one or more times (use "count" for rapid repeats, e.g. three jabs).
- NECK AND THROAT BITES are fair game, standing or in a pin: a bite that clamps the neck or throat and twists or
  wrenches (head shaking side to side) is a strike on Neck/Throat (with the jarred parts around it), or a hold on
  those parts when the jaws stay locked on. Use them now and then, like any other technique.
- WHERE BLOWS LAND: unless a TARGET FOCUS line tells you where to aim, no part of the body comes first. Choose each
  target from the moment (what is in reach, what is turned toward her, what the move suits) and let the fight
  range over the whole body, the parts fights tend to forget included: a tail, a hock or an ankle, an ear, a hip,
  the base of a fin or a wing, the small of the back, a forepaw stamped on, the ribs from the side. Vary the MOVES
  as well: a fighter with four moves and a body full of weapons has more to use than one bite.
- EVERY OTHER ATTACK CAN BE AS BRUTAL AS THAT, AND NO MORE: a limb seized and wrenched or twisted, a hurt part
  ground into the floor or stamped on, a body slammed and held down, a grip worried at and tightened, a blow
  driven into a spot that is already swollen. Say it in "flavor" and give it the severity it deserves (heavy,
  brutal, crushing). A throat bite is the ceiling: nothing is torn off, dislocated, or broken by your choice.
- combo: one action that hits SEVERAL body parts (use "hits"), e.g. thrown down stairs, slammed through a table.
  Each hit names its own defender, so one action can catch more than one fighter (a tail sweep, a dive
  onto two opponents, crashing into a pile).
- throw / slam / drag: one fighter MOVES another by force and the arena does the damage. No "move" or "part"
  is needed: put what she hits in "landing", in order, using the SCENE's features (each with its parts and a
  severity). The attacker must be on her feet; neither fighter may be pinned.
    throw: she is seized (by the scruff, a limb, the tail, round the body) and HURLED: she crashes into each surface
           in "landing" and ends on the ground. A fighter lying down is hauled up first. A standing target may slip
           the grab.
    slam:  she is LIFTED and driven straight down at the attacker's feet: onto the floor, a rock, a ledge's edge,
           into the shallows.
    drag:  she is ON THE GROUND and is hauled across it by a limb, the scruff or the tail: over rough stone, through
           the water, and INTO or AGAINST an obstacle (a stalagmite, a boulder, the cave wall). She stays down, lying
           as she was; a grip already on her stays on. The first surface scrapes the side she is lying on.
  Use these NOW AND THEN, not often: they are big, physical moments, best on an opponent who is already down or
  dazed. A fighter on the ground with strength left may fight the grab off; a thrown fighter with strength left
  may roll through the landing and come up on her feet (the engine rolls both).
- grapple: one fighter SEIZES another and KEEPS HOLD of her, both on their feet (a paw locked on an arm, jaws in the
  scruff, an arm round the neck, tails round a wrist). Put the gripped part in "part" and what grips it in the first
  entry of "hits" ("with": "her forepaw", "her jaws", "her twin tails"). The grab itself barely hurts. What it does
  is keep her at POINT-BLANK: while it lasts NEITHER of the two can dodge the other. The fighter holding on can
  then work her over, in the same beat (actions 2 and 3) and in the beats after: a close move thrown again and
  again (a strike with "count" 2-4: each of those short blows lands lighter than one full blow), a bite, a knee,
  a stream or beam held on her at no distance ("sustain" 2-4, no "pinned_against" needed), or a throw or a slam,
  which she can't slip. The held fighter can hit back just as freely, and the engine rolls her wrenching free
  every beat. Use it NOW AND THEN, not often. A standing target may slip the grab.
- PUMMELS are not only for a grab. The same close move thrown again and again ("count" 2-4) also works on a fighter
  who is DOWN (sitting or lying, not pinned: standing or kneeling over her), and on one still PRESSED AGAINST the
  scenery after a charge (she has nowhere to go). Not inside a pin: a pin holds her, it doesn't rain blows. The
  engine decides how long it lasts.
- CHAINS: now and then one fighter strings attacks together in ONE beat, each leading into the next: a jab that
  opens her guard, a second blow to the same spot or the part beside it, then something bigger (a named move, a
  bite, a knee; a throw or a slam can be the last link). Usually two or three links; a fighter who is well on top
  of a tiring opponent may keep one going for four or five. Put them as actions 1, 2, 3..., all with the same
  attacker and the same defender, different moves or different parts. A link that lands makes the next harder to
  dodge; a link she dodges ENDS the chain (the rest doesn't happen), and the longer a chain runs the likelier the
  engine is to end it: sooner when the attacker is tired or the defender still fresh. Most beats are still ONE action.
- TUMBLES: a fighter who is thrown or launched hard doesn't always stop where she lands. The engine sometimes has
  her tumble on across the ground and fetch up against something; you don't need to ask for it. You can also write
  one yourself by listing more surfaces in "landing", in the order she hits them.
- hold_start: a continuous attack (choke, lock, crush). Put each body part being pressed in "hits" with a hold
  severity (one part or several) and "with" = what she grips or presses with. Use a "ramp" for whether it tightens
  over time. The grip hurts from the beat it closes, and every beat after until it ends.
- ANY LIMB CAN GRIP ANY PART. A choke doesn't need jaws: twin tails or a tail looped round the neck, a forearm
  barred across the throat, coils, a paw or a knee pressed on the windpipe ("with": "her twin tails", "her forearm",
  "her coils", "her forepaw"). And jaws aren't only for the neck: jaws clamped on a forearm, a paw, a hock, an ear or
  a tail hold that limb fast and pin it to the ground, as a hold of its own or as one of a pin's contacts
  ("with": "her jaws"). Vary who grips what with what; the body part in "hits" is always the DEFENDER's.
- hold_adjust: change an active hold (by hold_id): new severity and/or ramp (tightening, steady, easing).
- hold_release: holds end: escape, rope break, released, broken up. Give a hold_id to end one hold, or
  hold_id 0 to end ALL of the attacker's holds on the defender (e.g. breaking free of a whole pin). Say how in flavor.
- submission: VERY RARE, and only when the beat's notes say there is a SUBMISSION OPENING. A wrestling hold that
  WRENCHES (a camel clutch, a crossface, a Boston crab, an armbar, a leg lock, a tail crank, a limb wrench): it does
  damage every beat, harder each beat, and it is NOT a pin (no clock; only a choke on her neck can make her pass
  out, and chokes are the rare ones: most are locks on a limb or the body). Put the hold's name
  in "improvised_name" ("camel clutch"); the engine sets the grips. While it's on, the holder can use what she still
  has free on her at point-blank as a second action in the same beat or later (a jet of water into the back of the
  head during a camel clutch): she can't cover up, so it lands hard.
- pin: the attacker pins the defender, pressing several body parts at once. Usually use most of her body: three,
  four, five points of contact, every limb she has free (her paws gripping the other's forelegs with the claws
  digging in, jaws pressed hard into the neck, chest against chest, her feet or hind paws pressed into both flanks,
  tails across the legs); now and then a simple two-point pin. List every point of contact in
  "hits": the defender's part, a hold severity, and "with" = what the attacker presses it with ("her full
  weight", "both knees", "teeth", "forepaws", "coils"). Match the contacts to the defender's position: someone
  pinned on their BACK (face-up) has chest, belly, neck, and limbs pressed; someone pinned FACE-DOWN has their
  upper back, lower back, hips, and the back of the neck pressed, never the chest. If an attack in the same beat
  knocked them down, decide which way they landed and choose contacts to match. VARY THE SHAPE of your pins:
  jaws on the throat with weight on the chest is one of many. Jaws can pin a paw or a forearm to the ground while a
  forepaw or forearm bars the throat; tails or coils can loop the neck while paws pin the shoulders; an arm can be
  wrenched out straight and trapped; both legs can be tangled; now and then (rarely) a leg is hooked and hauled up
  off the ground, folded back toward her chest. Other shapes: standing on her throat with a foot or a paw; a knee
  driven across the neck; legs locked round the neck (a leg scissor) or round the middle (a body scissor); a
  headlock or an arm locked round the neck from behind (hands and arms that can lock only); a four-legged fighter
  lying on her side behind her with both forelegs hooked round the sides of her neck; both arms trapped at once.
  Say it in "with" ("her jaws", "her forearm", "her twin tails",
  "her foreleg hauling the leg up"). The engine then
  holds her until she breaks out or passes out (no fixed length), and rolls her escape attempts every beat. While a pin is in progress,
  continue it with 'breather' or 'hold_adjust' (never start a second pin), and let the pinned fighter strike
  back sometimes.
- PIN TECHNIQUES (now and then, not every beat): while pinning, the pinner can attack the pinned fighter with a
  targeted technique that hurts and may lock her down: trapping a paw and driving a claw into a nerve cluster,
  grinding a knee into a joint, a bite that clamps a limb, jaws clamped on the neck or throat and twisting,
  pressing a pressure point. It deals damage and sometimes
  leaves her restrained (harder to escape) for a couple of beats. Vary it with plain holds, adjustments, and
  letting the struggle play out.
- (Don't start a hold AND a pin on the same fighter in one beat: a pin already includes all its contacts.)
- WHO CAN DO WHAT (the engine enforces this; see each fighter's line under CURRENT CONDITIONS):
  a PINNED fighter can only 'struggle' or strike the fighter on top of her; she can't pin, throw, launch, or knock
  anyone down, and nothing knocks down, throws, launches, or picks up a pinned fighter (she's already held to the
  ground). A fighter ON THE GROUND (not pinned) can still attack from where she lies, but can't pick anyone up,
  and can only pin someone who is also on the ground. A fighter already on the ground can't be "knocked down"
  again: hit her where she lies, or throw or launch her. If a pinner is knocked down, thrown, or put to sleep, her
  pin ends. One fighter pins one opponent at a time.
- struggle: the PINNED fighter (as "attacker") makes a real attempt to break free of the pin this beat; the
  engine rolls whether it fails, partly breaks loose, or escapes. Use it whenever the user asks for an escape
  attempt. If the pin starts in this same beat, add the struggle as the next action in the list.
- Nobody is knocked out by hits. Fighters stay conscious however hurt they are; the ONLY way to put someone
  out is a pin held until she passes out.
- breather: no new attack this beat (circling, recovering, trash talk, or simply holding a pin or hold
  as time passes). Active holds and pins still deal damage.

Guidance:
- You can see every body part's exact resistance and damage. Lower resistance means a part takes much more
  damage per hit. Some parts (a throat, a thin fin) are soft from the start; that is how the body is built,
  and fighters go for a weak spot SOMETIMES (a WEAK SPOT line will now and then point one out), not every time.
  Hurt or tired fighters are slower and
  more vulnerable. You never calculate anything yourself: the engine does all math.
- Each species has DIFFERENT body parts. Only target parts listed under the DEFENDER's own name: a Buizel
  has paws and knees, not forepaws or hocks; a Milotic has no legs at all.
- Match severity to the move: a jab is light, a chair shot is heavy or brutal. Do not default to the strongest option.
- A fighter attacks and holds with what still works. A limb listed at excruciating or worse (150%+ damage) isn't
  her weapon: she doesn't slam, claw, or press with it; she uses her other limbs, her jaws, her tail, her moves.
- A blow is a strike or combo, never a hold: "slam", "punch", "kick", "swipe" land once and are over. hold_start is
  only for something that stays on (a grip, a coil, a bite that locks, weight pressed down).
- A running, full-body charge (Take Down, Aqua Jet, Dragon Rush, a tackle) needs the attacker on her feet. From
  the ground or from under a pin she bites, kicks, lashes her tail, or uses a blast instead.
- An active hold keeps hurting every beat until it ends, and it has NO time limit: a choke or a coil can go on for
  many beats. The ENGINE rolls every beat whether the held fighter wrenches free (the odds are listed with each
  hold under ACTIVE HOLDS: low when she is worn down or the grip is crushing, higher when she is the stronger
  one). So don't end a hold just because it has run a while, and don't have the held fighter "escape" it with
  hold_release: leave that to the roll. The HOLDER may let go by choice (hold_release) when she wants her limb or
  jaws back for something else. hold_adjust only changes how hard it presses; the grip stays on. Don't send
  hold_start again for a grip that is already on: leave it running, adjust it, or release it. While a hold runs,
  both fighters can still act: the holder strikes or squeezes, the held one hits back.
- PIN RULES (the engine enforces them; check "can be pinned now" under each fighter, and follow its reason when
  it says NO). A pin can come at ANY point in the fight, but only when there is an opening: openings are rare
  against a fighter who is on her feet and still strong, likelier when she has just been knocked down, and much
  likelier once she is under half her strength. A standing opponent is taken down straight into the pin (action
  'pin': a tackle, a trip, dragging her to the ground), or knocked down first with the pin as the second action;
  one already on the ground is pinned where she lies. A fighter above half strength usually breaks out within a
  beat or two and hits the pinner on her way out, so early pins are pressure, position, and near-falls; pins WIN
  fights once she is worn down. After a pin attempt she must take at least one attack before the next one. During
  a pin, the pinned fighter can fight back with strikes of her own while the pin holds.
- DODGES, STATUS, STAMINA (the engine handles these; plan around them): any single-target or spread attack
  can be DODGED (the engine rolls it; a dodge may come with a counter-hit). Fighters on the ground, pinned, or
  paralyzed can't dodge; whole-body moves can't be dodged. Electric hits may PARALYZE, Ice may CHILL, Water
  SOAKS (and soaked fighters take far more from Electric), Dark may make the target FLINCH (a flinched
  fighter cannot attack next beat). Every move costs ENERGY (big moves cost more; resting restores it): a
  fighter short on energy must use cheap moves or catch her breath. A fighter whose strength drops very low
  gets one ADRENALINE SURGE: she hits harder and fights back hard for a few beats.
- SHARE THE FIGHT. Every fighter is a real threat until a pin finishes them. Compare fighters ONLY by their
  OVERALL "% of full strength", never by raw health numbers (fighters start with different totals). A fighter
  with high overall strength recovers fast from big hits, gets up, and hits back, even with a badly hurt part.
  Check MOMENTUM: if one side has made most of the recent attacks, the other side should get openings,
  counters, reversals and escapes.
- Worn-down parts take far more damage, and a fighter may go back to a hurt spot now and then, the way a real
  fighter tests a hurt leg or ribs, and a WEAK SPOT line will sometimes suggest one. But nothing is a constant
  priority unless a TARGET FOCUS line says so: with no order, the attacks range over the whole body and the moves
  vary. Working one spot again and again (the injured parts,
  the soft places, the throat) is for when a TARGET FOCUS line asks for it.
- With more than two fighters, spread the action around: anyone can attack anyone still in the fight.
  Fighters on the same team are allies: they do not attack each other and can double-team an opponent
  over consecutive beats. Eliminated fighters cannot act or be targeted.
- If the user gives a direction, follow it exactly (the right attacker, the right kind of action: a "hold
  attack" means hold_start or pin, an escape means struggle). If they ask for several attacks or a flurry, use "count"
  (repeated hits on one part), carry-over parts, or a spread move so the beat really contains several hits.
- Match the intensity the user asks for. "Very severe", "vicious", "a lot of damage" means the attacker's
  strongest suitable moves, super-effective types if available, several hits, and the defender's weakest
  (lowest-resistance) parts. "Light" or "testing" means weak moves on sturdy parts.
- "flavor" names the move in a few words (under 15), e.g. "raking claw swipe" or "tail coil around her
  chest". It must agree with the body parts you chose. It is a label, not narration: never copy sentences
  from the story.
- "intent" is one short sentence on why this happens now. When a fighter is setting something up (soaking her
  opponent before using lightning, calling rain before using water) or cashing in a setup, say the plan here.
Use only the fighter names, body parts, severities and hold_ids listed. Fill every field; fields that don't apply
to the chosen beat are ignored (use 0 for hold_id and an empty list for hits when unused).
"""


def schema(engine):
    """A beat: 1-3 actions that happen in order."""
    return {"type": "object",
            "properties": {"actions": {"type": "array", "minItems": 1, "maxItems": 3,
                                       "items": action_schema(engine)},
                           "positions": {"type": "string"}},
            "required": ["actions", "positions"]}


def action_schema(engine):
    parts = engine.all_part_names()
    names = [f.name for f in engine.active()]
    sev = engine.rules["severity"]
    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "action": {"type": "string", "enum": director_actions(engine)},
            "attacker": {"type": "string", "enum": names},
            "defender": {"type": "string", "enum": names},
            "part": {"type": "string", "enum": parts},
            "severity": {"type": "string", "enum": list(sev["instant"]) + list(sev["hold"])},
            "move": {"type": "string",
                     "enum": ["none", "improvised"] + sorted({m["name"] for f in engine.active() for m in f.moves})},
            "improvised_name": {"type": "string"},
            "improvised_type": {"type": "string", "enum": sorted(engine.rules.get("moves", {}).get("type_chart", {"Normal": {}}))},
            "count": {"type": "integer", "minimum": 1, "maximum": 6},
            "hits": {"type": "array", "items": {
                "type": "object",
                "properties": {"defender": {"type": "string", "enum": names},
                               "with": {"type": "string"},
                               "part": {"type": "string", "enum": parts},
                               "severity": {"type": "string",
                                            "enum": list(sev["instant"]) + list(sev["hold"])}},
                "required": ["defender", "part", "severity"]}},
            "launch": {"type": "string", "enum": LAUNCHES},
            "reposition": {"type": "string", "enum": REPOSITIONS},
            "sustain": {"type": "integer", "minimum": 0,
                        "maximum": int(engine.rules.get("moves", {}).get("sustain", {}).get("max_pulses", 4))},
            "pinned_against": {"type": "string"},
            "charge_into": {"type": "string"},
            "landing": {"type": "array", "maxItems": 4, "items": {
                "type": "object",
                "properties": {"surface": {"type": "string"},
                               "parts": {"type": "array", "maxItems": 6, "items": {"type": "string", "enum": parts}},
                               "severity": {"type": "string", "enum": list(sev["instant"])}},
                "required": ["surface", "parts", "severity"]}},
            "hold_id": {"type": "integer"},
            "ramp": {"type": "string", "enum": list(sev["hold_ramp"])},
            "flavor": {"type": "string"},
            "feint": {"type": "boolean"},
            "carry": {"type": "boolean"},
            "leap_from": {"type": "string"},
            "conjure": {"type": "string"},
        },
        # Every field is required: local models tend to skip optional ones.
        # Fields that don't apply to the chosen action are simply ignored by the engine.
        "required": ["intent", "action", "move", "improvised_name", "improvised_type", "attacker", "defender", "part", "severity",
                     "count", "hits", "launch", "reposition", "landing", "sustain", "pinned_against", "charge_into", "hold_id",
                     "ramp", "flavor", "feint", "carry", "leap_from", "conjure"],
    }


# If the model uses a hold word for a strike (or vice versa), translate instead of failing.
_TO_INSTANT = {"firm": "solid", "crushing": "heavy"}
_TO_HOLD = {"solid": "firm", "heavy": "crushing", "brutal": "crushing"}


def _severity(engine, kind, word, default):
    word = (word or default).lower()
    table = engine.rules["severity"][kind]
    if word not in table:
        word = (_TO_INSTANT if kind == "instant" else _TO_HOLD).get(word, default)
    return engine.power_for(kind, word)


def _fit_part(engine, defender, part):
    """Body part names are matched to the defender's real anatomy inside the engine."""
    return engine.get(defender).part(part).name


# where a grab's own words put it: "round the white hind legs", "seizes the otter's arm", "clamps onto her scruff"
_GRIP_ON = r"round|around|about|on|onto|upon|at|by"
_GRIP_AT = re.compile(r"\b(" + _GRIP_ON + r"|seiz\w*|grab\w*|catch\w*|clamp\w*|lock\w*|wrap\w*|grip\w*|snag\w*|tie\w*|"
                      r"bind\w*|trap\w*)\s+(?=((?:[\w'’-]+\s+){0,4}[\w'’-]+))", re.I)
# what she grips WITH, never the part gripped ("clamps her jaws on the scruff": not her jaw)
_WEAPON_WORDS = {"jaw", "jaws", "teeth", "claw", "claws", "coil", "coils", "talon", "talons", "horn", "tail", "tails"}
# and what she grips with: "whips her twin tails", "her jaws"
_GRIP_WITH = re.compile(r"\bher\s+((?:[a-z-]+\s+){0,2}?(?:tails?|jaws|teeth|arms?|paws?|forepaws?|claws|coils|legs|wings?|"
                        r"horn|fins?|talons|hands?))\b", re.I)
_PART_QUALIFIERS = {"left", "right", "hind", "fore", "front", "upper", "lower", "back", "twin", "sickle"}


def _flavor_grip(engine, att, dfn, flavor):
    """A grab whose order names no part: the part and the grip its own words name ('she whips her twin tails round
    the white hind legs': a hind leg, with her twin tails), the way a strike lands where it is aimed. (None, '')
    when the words name no part of hers."""
    text = str(flavor or "")
    names = list(engine.get(dfn).parts)
    body = ({w for trig, _ in ENGINE_REGIONS for t in trig for w in t.split()}
            | {w for p in names for w in p.lower().split()}) - {"left", "right"}
    part, span = None, None
    # "round the white hind legs" before "whips her twin tails": a preposition says where far more surely than a verb
    found = sorted(_GRIP_AT.finditer(text), key=lambda m: (not re.fullmatch(_GRIP_ON, m.group(1), re.I), m.start()))
    for m in found:
        toks = [re.sub(r"(?:'s|’s|'|’)$", "", t) for t in m.group(2).lower().split()]
        for i, t in enumerate(toks):
            if i and toks[i - 1] in ("her", "its") and t in _WEAPON_WORDS and not re.fullmatch(_GRIP_ON, m.group(1), re.I):
                break       # "clamps her jaws": her own weapon, not where it closes
            stem = t[:-2] if t.endswith("es") and t[:-2] in body else t[:-1] if t.endswith("s") and t[:-1] in body else t
            if stem in body and stem not in _PART_QUALIFIERS:
                phrase = " ".join(([toks[i - 1]] if i and toks[i - 1] in _PART_QUALIFIERS else []) + [stem])
                part = match_part(names, phrase)
                break
        if part:
            span = (m.start(), m.end(2))
            break
    with_ = ""
    if part:
        w = next((g for g in _GRIP_WITH.finditer(text) if not (span[0] <= g.start() < span[1])), None)
        with_ = f"her {w.group(1).lower()}" if w else ""
    return part, with_


def _fill_defender(engine, att, dfn):
    """With exactly two fighters left, the defender is obviously the other one."""
    names = [f.name for f in engine.active()]
    if (not dfn or str(dfn).lower() == str(att).lower()) and len(names) == 2:
        return next(n for n in names if n.lower() != str(att).lower())
    return dfn


# improvised "moves" that aren't attacks at all (the director describing someone getting up as a strike)
NOT_AN_ATTACK = re.compile(r"\b(push[- ]?up|get(?:ting)? up|stand(?:ing)? up|rise|rising (?:up|to (?:her|his) feet)|recover\w*|brac\w*|dodg\w*|"
                           r"retreat\w*|back(?:ing)? away|crawl\w*|rest\w*|breath\w*|struggl\w* to (?:stand|rise)|"
                           r"attempt(?:ed)? to (?:stand|rise|get up))\b", re.I)

# a "move" that is only somebody landing ("hard landing", "the landing", "crash landing"): how a throw ends, not an
# attack. Filed as a strike it would hit the OTHER fighter for it
LANDING_NAME = re.compile(r"^\s*(?:a |an |the |her )?(?:hard |rough |heavy |bad |crash |crash-|splash |awkward )?"
                          r"(?:landing|lands?|fall|falls|touchdown|splashdown)\s*$", re.I)


def _multi_hit(engine, move):
    """Moves that strike several times in one go (rules.json moves.multi_hit, or 'repeatedly' in their description)."""
    names = {n.lower() for n in engine.rules.get("moves", {}).get("multi_hit", [])}
    about = str(move.get("about", "")).lower()
    # an improvised move repeats only when what it is says so (a flurry of jabs); otherwise a count on it is a pummel
    # (each blow lighter, the run rolled) like any other close move
    return (move["name"].lower() in names
            or any(w in about for w in ("times", "repeated", "2-5", "multiple", "twice", "flurry", "rapid")))


def _apply_focus(engine, att, dfn, b):
    """/focus: an attack aimed off the focus zone is moved onto it some of the time (director.focus_strength)."""
    zones = engine.focus_for(att)
    strength = float(engine.rules.get("director", {}).get("focus_strength", 0.6) or 0)
    if not zones or strength <= 0:
        return b
    b = dict(b)

    def fix(who, part):
        try:
            body = list(engine.get(who).parts)
        except ValueError:
            return part
        allowed = engine.zone_parts(who, zones)
        if not allowed or not part:
            return part
        try:
            name = _fit_part(engine, who, part)
        except ValueError:
            return part
        if name in allowed or engine.rng.random() >= strength:
            return part
        if any(str(z).lower() in engine.INJURED_WORDS for z in zones):
            hurt = engine.injured_targets(who)[0]  # the worse a part is hurt, the likelier she goes back to it
            return engine.rng.choices(allowed, [hurt.get(p, 15.0) for p in allowed])[0]
        return engine.rng.choice(allowed)
    if b.get("part"):
        b["part"] = fix(dfn, b["part"])
    if b.get("hits"):
        b["hits"] = [dict(h, part=fix(_fill_defender(engine, att, h.get("defender")) or dfn, h.get("part")))
                     for h in b["hits"]]
    return b


# where a charge (Take Down, an Aqua Jet ram) can be moved to: the trunk, which a body slamming into her catches
CHARGE_REGIONS = ("chest", "shoulder", "belly", "back_up", "back_low", "hind_up")


def _apply_variety(engine, att, dfn, b):
    """With no /focus set: a blow aimed at a region this attacker has just been hitting is moved, some of the time,
    to a part she has left alone (director.target_variety; 0 = never). What she aimed at is remembered either way."""
    from engine import body_region
    try:
        a, d = engine.get(att), engine.get(dfn)
        name = _fit_part(engine, dfn, b.get("part")) if b.get("part") else None
    except (ValueError, KeyError):
        return b
    if not name:
        return b
    log = engine.__dict__.setdefault("aim_log", {}).setdefault(a.name, [])
    v = float(engine.rules.get("director", {}).get("target_variety", 0.35) or 0)
    recent = [p for who, p in log[-3:] if who == d.name]
    lately = {body_region(p) for p in recent}
    runs = int(b.get("count") or 1) > 1     # a pummel or a flurry picks its own spots blow by blow: not re-aimed
    # a blow whose flavor already tells where it lands ("cracks her wing across the head") is meant there: moving it
    # would leave the narrator two places for one blow
    said = re.search(r"\b%s\b" % re.escape(name.lower().split()[-1]), str(b.get("flavor") or "").lower())
    if (v > 0 and not runs and not said and not engine.focus_for(att) and name not in (getattr(engine, "weak_aim", None) or ())
            and body_region(name) in lately and not engine.pinned_by(a.name)
            and a.name not in engine.downed and not engine.grab_between(a.name, d.name)
            and engine.rng.random() < v):
        fresh = [p for p in d.parts if body_region(p) not in lately]
        mv = engine.find_move(a.name, b.get("move")) if b.get("move") else None
        if mv and mv.get("charge"):
            # a full-body ram lands on the body, not on a fin or a paw: it is moved only onto another part of the trunk
            fresh = [p for p in fresh if body_region(p) in CHARGE_REGIONS]
        if d.name in engine.downed and fresh:     # only what is turned toward her attacker
            fitted, _ = engine.fit_to_facing(d.name, fresh)
            # (and not her tail: lying down, she is on it or it is out behind her, not under her attacker's hands)
            fresh = [p for p in dict.fromkeys(fitted) if body_region(p) not in lately and body_region(p) != "tail"]
        if fresh:
            # the less a part has been hurt so far, the likelier she goes for it
            new = engine.rng.choices(fresh, [1.0 / (1.0 + d.parts[p].damage / 60.0) for p in fresh])[0]
            b = dict(b, part=new)
            if b.get("hits"):
                b["hits"] = [dict(h, part=new) if h.get("part") and _same_part(engine, dfn, h["part"], name) else h
                             for h in b["hits"]]
            name = new
    log.append((d.name, name))
    del log[:-6]
    return b


# (since build 266) what a nameless blow is, from its own words: the build-264 log's "A Plain Blow" was a bite
_PLAIN_NAMES = ((r"\b(?:jaws?|teeth|fangs?|bit(?:es?|ing)?|chomp\w*)\b", "Bite"),
                (r"\bknee", "Knee Strike"), (r"\b(?:kick\w*|heel|stomp\w*|stamp\w*)\b", "Kick"),
                (r"\bhead ?butt\w*|\bforehead\b", "Head Butt"), (r"\btails?\b", "Tail Strike"),
                (r"\b(?:claws?|rak\w+|scratch\w*|swip\w+|slash\w*)\b", "Claw Rake"),
                (r"\belbow", "Elbow Strike"), (r"\b(?:punch\w*|fist|jab\w*|paw|forearm|fin)\b", "Punch"))


def _plain_name(flavor):
    """A name for a blow the director didn't name, from what its words say she hits with ("a plain blow" when they
    say nothing)."""
    fl = str(flavor or "").lower()
    return next((n for rx, n in _PLAIN_NAMES if re.search(rx, fl)), "a plain blow")


def _apply_hold_mix(engine, att, dfn, b, act):
    """finish.submission.hold_mix (since build 265): in a submission match, a CHOKE or a JAW HOLD the director chose
    (a named one, one of her own, or a hold_start on the neck or with her jaws) stands only hold_mix.choke /
    hold_mix.jaws of the time; otherwise a lock that fits goes on instead (no choke, and no jaws when one without
    fits), so the usual finish is a limb, the back or the body cranked with paws, legs, tails or her weight. Returns
    the beat (changed or not); a choke or bite with nothing else that fits stands."""
    if not engine.hold_mix() or not engine.submission_match():
        return b
    if act == "hold_start" and any(h.attacker == engine.get(att).name and h.defender == engine.get(dfn).name
                                   for h in engine.holds.values()):
        return b      # (a grip added to a hold she already has on her: not a new hold to swap)
    name = str(b.get("improvised_name") or b.get("submission") or "").strip().lower()
    hits = [h for h in (b.get("hits") or []) if isinstance(h, dict) and h.get("part")]
    shapes = engine.submission_shapes(att, dfn)
    if act == "submission" and name in shapes:
        choke, jaws = engine.sub_is_choke(shapes[name]), engine.sub_uses_jaws(shapes[name])
    elif hits and (act == "hold_start" or name not in engine.SUBMISSIONS):
        parts = [_fit_part(engine, dfn, h["part"]) or h["part"] for h in hits]
        choke = body_region(parts[0]) == "neck" if act == "submission" else any(body_region(p) == "neck" for p in parts)
        choke = choke or bool(act == "submission" and re.search(
            r"(?i)\b(?:choke|throat|sleeper|guillotine|strangle\w*)\b", name))
        jaws = any(engine.JAWS_GRIP.search(str(h.get("with") or "")) for h in hits)
    else:
        return b
    if not (choke or jaws) or engine.rng.random() < engine.mix_keep(choke, jaws):
        return b
    alt = {n: v for n, v in shapes.items() if not engine.sub_is_choke(v)}
    alt = {n: v for n, v in alt.items() if not engine.sub_uses_jaws(v)} or (alt if choke else {})
    if not alt:
        return b
    new = engine.pick_submission(alt, defender=dfn)
    # (its words were written for the choke or the bite: the engine's own words for the lock tell it instead)
    return dict(b, action="submission", improvised_name=new, submission=new, hits=[], flavor="",
                _mixed_from=name or "a hold")


def _apply_tap_steer(engine, att, dfn, b, kind):
    """finish.submission.taps.steer: with taps that must come from different body parts, the fight is pushed onto
    the part of hers that still counts (engine.tap_target). A blow aimed at a part her taps have used up always
    moves onto it, and any other blow moves there taps.steer.strikes of the time; a grip on a used-up part moves
    onto it, and any other grip taps.steer.holds of the time (kind "strikes" or "holds")."""
    try:
        aim = engine.tap_target(dfn)
    except (ValueError, KeyError):
        return b
    if not aim:
        return b
    spent = set(engine.spent_tap_parts(dfn))
    chance = engine.tap_steer(kind)

    def fit(p):
        try:
            return _fit_part(engine, dfn, p)
        except ValueError:
            return None
    if dfn in engine.downed:
        fitted, _ = engine.fit_to_facing(dfn, [aim])
        if fitted and fitted[0] != aim:
            return b      # (she is lying on it: not where a blow or a grip can get at it this beat)
    if kind == "strikes":
        name = fit(b.get("part")) if b.get("part") else None
        if engine.tap_ready(dfn):
            # steer.ready: the target is ruined already, and more blows there are wasted: they soften the next
            # part instead (the one the tap after this one will come from)
            nxt = engine.tap_next(dfn)
            if nxt and (name in spent or (name == aim and engine.rng.random() < chance)):
                aim = nxt
            elif name != nxt and name not in spent and nxt and engine.rng.random() < chance * 0.5:
                aim = nxt
            else:
                return b
            if dfn in engine.downed:
                fitted, _ = engine.fit_to_facing(dfn, [aim])
                if fitted and fitted[0] != aim:
                    return b
        elif name == aim or (name not in spent and engine.rng.random() >= chance):
            return b
        old = [x for x in [b.get("part")] + [h.get("part") for h in (b.get("hits") or []) if isinstance(h, dict)] if x]
        b = dict(b, part=aim, _aimed=True, _steered_from=old[0] if old else None)
        if b.get("hits"):
            hs = [dict(h) for h in b["hits"] if isinstance(h, dict)]
            if hs:
                hs[0]["part"] = aim
            # a strike's other parts were the path of the blow the director aimed (an ear, then the other ear): moved
            # onto the target, they no longer touch it and were only rolled for and dropped. A combo's are blows
            b["hits"] = hs[:1] if b.get("action") == "strike" else hs
        return _steered_words(engine, dfn, b, old, aim)
    hs = [dict(h) for h in (b.get("hits") or []) if isinstance(h, dict) and h.get("part")]
    if not hs and b.get("part"):
        hs = [{"part": b["part"], "severity": b.get("severity")}]
    if not hs or any(fit(h["part"]) == aim for h in hs):
        return b
    i = next((k for k, h in enumerate(hs) if fit(h["part"]) in spent), None)
    if i is None and engine.rng.random() < chance:
        i = 0
    if i is None:
        return b
    was = hs[i]["part"]
    hs[i]["part"] = aim
    # (_steered_from, since build 272: a grip moved too, so resolve takes the words put right with it; the build-271
    # log had "wraps her twin tails around Ripples' left knee" on a grip moved onto her tails)
    return _steered_words(engine, dfn, dict(b, hits=hs, part=hs[0]["part"], _steered_from=was), [was], aim) \
        if i == 0 else dict(b, hits=hs, part=hs[0]["part"], _steered_from=was)


_REGION_WORDS = {"head": r"head|skull|face|cheek|jaw|muzzle|snout|temple|ears?|eyes?|nose|brow",
                 "neck": r"neck|throat", "chest": r"chest|ribs?", "belly": r"belly|stomach|gut|midsection",
                 "back_up": r"back|spine", "back_low": r"lower back", "tail": r"tails?",
                 "hind_low": r"knee|foot|feet|ankle|shin", "hind_up": r"thigh|hip",
                 "fore_low": r"forearm|paw|wrist|arm", "fore_up": r"upper arm|arm", "shoulder": r"shoulder"}


def _steered_words(engine, dfn, b, old, aim):
    """finish.submission.taps.steer moved a blow onto the part being worked: the director's words for it ("drives her
    knee into the side of her head", why: "rake her cheek") still named where it was aimed, and the story followed
    them instead of where it landed. The old part, and the words for its region, become the part it lands on."""
    from engine import body_region
    if not old or not aim:
        return b
    alts = sorted({str(p).lower() for p in old if p}, key=len, reverse=True)
    regs = {body_region(str(p)) for p in old if p} - {body_region(aim), "other"}
    pats = [re.escape(p) for p in alts] + [_REGION_WORDS[r] for r in regs if r in _REGION_WORDS]
    if not pats:
        return b
    rx = re.compile(r"\b(?:(?:left|right|other|both)\s+)?(?:%s)\b" % "|".join(pats), re.I)
    for key in ("flavor", "intent", "improvised_about"):
        v = b.get(key)
        if isinstance(v, str) and rx.search(v):
            b = dict(b, **{key: rx.sub(aim.lower(), v, count=1)})
            b[key] = rx.sub("", b[key]).replace(" and ,", ",")
            b[key] = re.sub(r"\s+([,.;])", r"\1", re.sub(r"\b(?:and|her|the)\s+(?=[,.;]|$)", "", b[key])).strip(" ,")
    return b


HEAD_BLOW = re.compile(r"(?i)\b(?:head ?butt\w*|skull bash|head smash|iron head|head slam|zen headbutt|ram(?:s|med)? "
                       r"(?:her|its) head)\b")
# what a head swung by a fighter on her feet reaches on another on her feet: not her legs, feet or tail
HEAD_REACH = ("head", "neck", "chest", "shoulder", "belly", "back_up", "fore_up", "fore_low")


def _head_reach(engine, att, dfn, b):
    """moves.head_reach (since build 261): a head butt thrown by a fighter on her feet at one on her feet lands where
    a head can get to (the build-260 log: Nerine head-butted Ripples' left foot and launched her). A part out of
    reach becomes her chest."""
    from engine import body_region
    if not ((engine.rules.get("moves") or {}).get("head_reach") or {}).get("enabled", True):
        return b
    said = f"{b.get('move') or ''} {b.get('improvised_name') or ''} {b.get('flavor') or ''}"
    if not HEAD_BLOW.search(said) or att in engine.downed or dfn in engine.downed:
        return b
    try:
        d = engine.get(dfn)
        low = [p for p in [b.get("part")] + [h.get("part") for h in b.get("hits") or [] if isinstance(h, dict)]
               if p and body_region(_fit_part(engine, dfn, p)) not in HEAD_REACH]
        to = _fit_part(engine, dfn, "chest") if "Chest" in d.parts or any("chest" in n.lower() for n in d.parts) else None
    except ValueError:
        return b
    if not low or not to:
        return b
    old = [_fit_part(engine, dfn, p) for p in low]
    b = dict(b, part=to if b.get("part") in low else b.get("part"))
    if b.get("hits"):
        b["hits"] = [dict(h, part=to) if h.get("part") in low else h for h in b["hits"] if isinstance(h, dict)]
    return _steered_words(engine, dfn, b, old, to)


def _words_to_parts(engine, dfn, b):
    """director.words_to_parts (since build 261): the director's words name one part of hers and the action
    another (told to work her right hip, it wrote "wrapping tightly around Nerine's left knee"; "Brick Break slams
    Ripples' head" on her right hip): the engine resolves the action's parts, so the words are put right to them.
    Only her parts named as hers ("Nerine's left knee") are changed, never what the attacker uses."""
    from engine import body_region
    if not ((engine.rules.get("director") or {}).get("words_to_parts") or {}).get("enabled", True):
        return b
    try:
        d = engine.get(dfn)
        parts = [_fit_part(engine, dfn, p) for p in [b.get("part")] + [h.get("part") for h in b.get("hits") or []
                                                                     if isinstance(h, dict)] if p]
    except ValueError:
        return b
    parts = list(dict.fromkeys(parts))
    if not parts:
        return b
    words = sorted({w for n in d.parts for w in [n.lower(), n.lower().split()[-1]]}
                   | {"head", "knee", "foot", "leg", "arm", "hip", "back", "face", "neck", "tail", "tails"},
                   key=len, reverse=True)
    rx = re.compile(r"\b" + re.escape(d.name) + r"(?:'s|’s|'|’)\s+((?:(?:left|right)\s+)?(?:"
                    + "|".join(re.escape(w) for w in words) + r"))\b", re.I)
    regions = {body_region(p) for p in parts}
    out = {}
    for key in ("flavor", "intent"):
        v = b.get(key)
        if not isinstance(v, str):
            continue

        def fix(m):
            said = m.group(1)
            try:
                got = _fit_part(engine, dfn, said)
            except ValueError:
                return m.group(0)
            if got in parts or body_region(got) in regions:
                return m.group(0)
            return m.group(0)[:m.start(1) - m.start(0)] + parts[0].lower()
        new = rx.sub(fix, v)
        if new != v:
            out[key] = new
    return dict(b, **out) if out else b


def _same_part(engine, who, asked, name):
    try:
        return _fit_part(engine, who, asked) == name
    except ValueError:
        return False


def low_health_hint(engine):
    """low_health (since build 246): what the director must know this beat about a fighter at the end of her strength:
    a limb that isn't answering, a last stand, the one left wide open after it, and how the other one reads her."""
    out = []
    for f in engine.active():
        dl = f.learned.get("dead_limb") or {}
        if dl and int(dl.get("turn", -1)) == engine.turn:
            out.append(f"{poss_name(f.name)} {str(dl.get('part', '')).lower()} isn't answering her this beat: no move "
                       f"thrown with it.")
        if engine.has(f, "overextended"):
            out.append(f"{f.name} is WIDE OPEN after her last stand: anything aimed at her now lands.")
        rd = f.learned.get("foe_read") or {}
        if rd and int(rd.get("turn", -1)) == engine.turn:
            out.append({"finish": f"{f.name} reads {rd['of']} as done: she goes for the finish now.",
                        "wary": f"{f.name} reads {rd['of']} as dangerous still: she stays careful, expecting one "
                                f"desperate attack.",
                        "still_standing": f"{f.name} is shaken that {rd['of']} is still standing: she hesitates, or "
                                          f"presses harder to put her down."}.get(rd.get("kind"), ""))
    return "\n".join(x for x in out if x)


def coil_size_hint(engine):
    """holds.coil.size (since build 275): a serpent that dwarfs her opponent coils her middle, never one limb alone."""
    out = []
    act = engine.active()
    for a in act:
        for d in act:
            if a is not d and not (a.team and a.team == d.team) and engine.coil_dwarfs(a.name, d.name):
                out.append(f"{a.name} is many times {poss_word(d.name)} size: her body is thicker than "
                           f"{poss_word(d.name)} limbs, so her coils can't wrap one arm, leg or tail alone. When she "
                           f"coils {d.name}, the coils go round {poss_word(d.name)} MIDDLE (chest or belly), and a "
                           f"limb can be bound in under them")
    if (((engine.rules.get("holds") or {}).get("busy_limbs") or {}).get("coils_use_tail", True)):
        # (since build 311) her coils are her tail: while they hold someone, she has no tail to strike with
        for f in engine.active():
            st, h = engine.coil_tail(f)
            if st == "busy":
                out.append(f"{poss_word(f.name)} coils are wound round {h.defender}: her tail is IN them, so she "
                           f"has no tail strike (Dragon Tail, Iron Tail, Aqua Tail...) while they hold, and nothing "
                           f"she does sends {h.defender} flying out of them. She strikes with what is free (her jaws, "
                           f"her head, a move fired from her mouth) or squeezes")
            elif st == "free":
                out.append(f"{poss_word(f.name)} one coil round {h.defender} is her middle: the END of her tail is "
                           f"still loose, so a tail strike is a flick of that free end (weaker, no body behind it), "
                           f"and it can't send {h.defender} flying out of the coil")
    if engine.coil_contest_cfg():
        # (since build 279, holds.coil.contest) a serpent in another's coils can wind her own round her holder
        for h in engine.holds.values():
            if not h.coil:
                continue
            held, holder = engine.get(h.defender), engine.get(h.attacker)
            if engine.body_plan(held) != "serpent" or any(
                    x.coil and x.attacker == held.name and x.defender == holder.name for x in engine.holds.values()):
                continue
            out.append(f"{held.name} is a serpent wound in {poss_word(holder.name)} coils: she can wind her OWN coils "
                       f"round {holder.name} (a hold_start on {poss_word(holder.name)} middle) and fight it out, coil "
                       f"against coil; each beat one may out-coil the other and take over")
            break
        for h in engine.holds.values():
            if h.coil and any(x.coil and x.attacker == h.defender and x.defender == h.attacker
                              for x in engine.holds.values()):
                out.append(f"{h.attacker} and {h.defender} are coiled round EACH OTHER: a contest of coils. The engine "
                           f"decides each beat who out-coils whom; your actions are the straining, crushing and "
                           f"tightening, not strikes")
                break
    return "\n".join(out)


def taps_hint(engine):
    """finish.submission.taps: the tap tally for the director (how many each fighter has given, how many end it),
    which parts no longer count, and the part to work toward the next one: soften it with blows, then hold it."""
    if not engine._taps_rule():
        return ""
    need, distinct = engine.taps_needed(), max(engine.taps_distinct_needed(f) for f in engine.active())
    out = [f"TAP COUNT: this match is won by the {ordinal(need)} tap-out" + ("" if need == 1 else ", not the first") + (f", and her taps must come from {distinct} different body parts" if distinct > 1
                                         else "") + ". A tap before that ends the hold, not the match."]
    for f in engine.active():
        foe = next((x for x in engine.active() if x.team != f.team), None)
        given, spent, aim = engine.taps_given(f), engine.spent_tap_parts(f), engine.tap_target(f)
        line = f"{f.name} has tapped {len(given)} of {need}" + (f" ({', '.join(p.lower() for p in given)})"
                                                                  if given else "")
        if spent:
            line += (f"; a hold on her {', '.join(p.lower() for p in spent)} can NO LONGER make her tap (those "
                     f"parts are used up)")
        if aim and foe and engine.tap_ready(f):
            nxt = engine.tap_next(f)
            line += (f". Her {aim.lower()} is READY: it is hurt enough, and more blows on it are wasted. {foe.name} "
                     f"PUTS A HOLD ON HER {aim.upper()} now (a lock, a submission, an improvised grip with that part "
                     f"first in \"hits\") and keeps it on until she taps"
                     + (f"; her blows go to her {nxt.lower()}, softening it for the tap after" if nxt else ""))
        elif aim and foe:
            line += (f". {foe.name} WORKS HER {aim.upper()} next: strikes aimed at it to wear it down, then a hold "
                     f"on it (a lock, a submission, an improvised grip with that part first in \"hits\"), kept on and "
                     f"tightened until she taps")
        out.append(line + ".")
    return "\n".join(out)


def variety_hint(engine):
    """Now and then, with no /focus set: name what each fighter has NOT been hit on yet (director.target_variety)."""
    from engine import body_region
    v = float(engine.rules.get("director", {}).get("target_variety", 0.35) or 0)
    if v <= 0 or engine.pins or engine.rng.random() >= v:
        return ""
    words = {"head": "head", "neck": "neck", "chest": "chest", "belly": "stomach and sides", "back_up": "back",
             "back_low": "lower back", "shoulder": "shoulders", "fore_up": "forelimbs", "fore_low": "forepaws",
             "hind_up": "thighs and hips", "hind_low": "lower legs", "tail": "tail"}
    out = []
    for f in engine.active():
        if any(engine.focus_for(o.name) for o in engine.active() if o is not f):
            continue
        regs = {}
        for p in f.parts.values():
            regs.setdefault(body_region(p.name), []).append(p.damage)
        clean = [words[r] for r in words if r in regs and max(regs[r]) < 10]
        if len(clean) >= 2 and any(max(v_) >= 40 for v_ in regs.values()):
            engine.rng.shuffle(clean)
            out.append(f"{f.name} has not been touched yet on her {', '.join(clean[:5])}")
    if not out:
        return ""
    return ("TARGETS (an idea, not an order): " + "; ".join(out) + ". A blow that goes somewhere new now and then "
            "keeps a fight from being about one spot: the same move can land on a different part.")


FACE_PARTS = re.compile(r"(?i)\b(?:muzzle|nose|snout|beak)\b")


def face_hint(engine):
    """director.face_chance (since build 308): now and then, when no other target idea ran, a reminder that her
    opponent has a face (a muzzle, a nose, a snout, a beak) as well as a head: the director tends to pick Head, Neck and
    Chest and leave the face alone. Never an order; and only between two fighters in the air or on the ground together."""
    c = float(engine.rules.get("director", {}).get("face_chance", 0.12) or 0)
    if c <= 0 or engine.pins or engine.rng.random() >= c:
        return ""
    pairs = []
    for f in engine.active():
        if engine.focus_for(f.name) or engine.pinned_by(f.name) or f.name in engine.downed:
            continue
        for foe in engine.active():
            if foe.team == f.team or engine.has(foe, "airborne") != engine.has(f, "airborne"):
                continue
            face = [n for n in foe.parts if FACE_PARTS.search(n)]
            if face:
                pairs.append((f, foe, face))
    if not pairs:
        return ""
    f, foe, face = engine.rng.choice(pairs)
    return (f"THE FACE (an idea, not an order): {poss_word(foe.name)} " + " and ".join(face[:2]) + " are there to be hit "
            f"as well as her Head: a blow on the nose or the muzzle stings, waters her eyes and can bloody her nose, and "
            f"blow after blow there wears her down. If {f.name} goes for the face this time, name the part itself.")


def weak_spot_menu(engine, foe, soft):
    """The parts a WEAK SPOTS hint offers (director.weak_spot_menu: how many of each kind): badly hurt ones, ones only
    hurt so far, and soft places not yet touched; shuffled, so the worst is not always first."""
    m = engine.rules.get("director", {}).get("weak_spot_menu") or {}
    parts = sorted(foe.parts.values(), key=lambda p: -p.damage)
    bad = [p for p in parts if p.damage >= 150][:int(m.get("badly_hurt", 2))]
    hurt = [p for p in parts if 30 <= p.damage < 150]
    hurt = engine.rng.sample(hurt, min(len(hurt), int(m.get("hurt", 3))))
    fresh = [p for p in soft if p.damage < 30][:int(m.get("soft", 1))]
    out = [(p, "badly hurt already") for p in bad] + [(p, "hurt, not yet badly") for p in hurt] + \
          [(p, "soft and badly protected") for p in fresh]
    if len(out) < 2:
        out += [(p, "soft and badly protected") for p in soft if p not in [q for q, _ in out]][:2]
    engine.rng.shuffle(out)
    return out


def weak_spot_hint(engine):
    """Now and then, with no /focus set: point one fighter at her opponent's weak spots (soft parts, or ones already
    worn down), so weak spots are gone for sometimes, never constantly (director.weak_spot_chance). Some of these
    nudges (director.weak_spot_repeat) are for a run of blows (a pummel, a combo, a chain, a grapple worked at, a
    charge, a held stream):
    one weak spot hit again and again, a group of parts worked together, or a few weak spots in turn."""
    from engine import body_region
    cfg = engine.rules.get("director", {})
    c = float(cfg.get("weak_spot_chance", 0.2) or 0)
    engine.weak_aim = set()
    if c <= 0 or engine.rng.random() >= c:
        return ""
    out = []
    for f in engine.active():
        if engine.focus_for(f.name) or engine.pinned_by(f.name) or f.name in engine.downed:
            continue
        for foe in [x for x in engine.active() if x.team != f.team]:
            out.append((f, foe))
    if not out:
        return ""
    f, foe = engine.rng.choice(out)
    # the softest parts first, a little less for the ones hard to reach (moves.aim): a throat or an ear is soft, but a
    # blow aimed at it often lands beside it (director.weak_spot_reach: 0 = reach doesn't count)
    reach = float(cfg.get("weak_spot_reach", 0.35) or 0)
    soft = sorted(foe.parts.values(), key=lambda p: p.resistance / (engine.aim_ease(p.name) ** reach if reach else 1))[:4]
    why = lambda p: "already worn down" if p.damage >= 30 else "soft and badly protected"
    if engine.rng.random() >= float(cfg.get("weak_spot_repeat", 0.25) or 0):
        # a short MENU to choose from, not one spot: a badly hurt place or two, some that are only hurt so far, and a
        # soft place not yet touched (director.weak_spot_menu), so the blows spread over what is hurt instead of all
        # landing on the worst of it
        menu = weak_spot_menu(engine, foe, soft)
        engine.weak_aim = {p.name for p, _ in menu}
        return (f"WEAK SPOTS TO CHOOSE FROM (an idea, not an order): if {f.name} goes for a weak spot this time, any "
                f"ONE of these would do: " + "; ".join(f"{poss_word(foe.name)} {p.name} ({w})" for p, w in menu)
                + ". Pick whichever suits the move and the angle, or none of them; the next blow can land anywhere.")
    kind = engine.rng.choice(["same", "group", "several"])
    run = ("if she lands a run of blows this beat (a pummel with a count, a combo, a chain, a grapple she keeps "
           "working at, a charge that drives into it, a stream she holds on it)")
    if kind == "same":
        p = engine.rng.choice(soft[:3])
        engine.weak_aim = {p.name}
        return (f"WEAK SPOT, WORKED (an idea, not an order): {run}, {f.name} could bring it back to {poss_word(foe.name)} "
                f"{p.name} ({why(p)}) again and again, every blow on the same place. Just this beat.")
    if kind == "group":
        # a group of parts that belong together: one region, or one side's limb top to bottom
        seed = engine.rng.choice(soft[:3]).name
        reg = body_region(seed)
        side = "left" if "left" in seed.lower().split() else "right" if "right" in seed.lower().split() else None
        grp = [n for n in foe.parts if body_region(n) == reg and (side is None or side in n.lower().split())]
        if len(grp) < 2 and side:
            grp = [n for n in foe.parts if side in n.lower().split()
                   and body_region(n)[:4] == reg[:4]] or grp
        if len(grp) < 2:
            from engine import neighbor_parts
            same, near = neighbor_parts(list(foe.parts), seed)
            grp = [seed] + (same + near)[:2]
        grp = list(dict.fromkeys(grp))[:4]
        engine.weak_aim = set(grp)
        return (f"WEAK SPOT, WORKED (an idea, not an order): {run}, {f.name} could work one area of {foe.name}: "
                f"{', '.join(grp)}, the blows landing up and down it in turn. Just this beat.")
    pick = soft[:3]
    engine.weak_aim = {p.name for p in pick}
    return (f"WEAK SPOTS, WORKED (an idea, not an order): {run}, {f.name} could go from weak spot to weak spot on "
            f"{foe.name}: " + ", ".join(f"{p.name} ({why(p)})" for p in pick) + ", each hit more than once. Just this beat.")


def _held_not_holder(engine, att, hold_id, dfn):
    """True if this hold_release comes from the fighter a plain hold is ON (not the one gripping), and the break
    roll is switched on: letting go is the holder's to choose, getting out is the dice's."""
    if float(engine.rules.get("holds", {}).get("break", {}).get("base", 0.12)) <= 0:
        return False
    me = engine.get(att).name
    if hold_id in engine.holds:
        h = engine.holds[hold_id]
        return h.defender == me and h.attacker != me
    mine = [h for h in engine.holds.values() if h.attacker == me and (not dfn or h.defender.lower() == str(dfn).lower())]
    on_me = [h for h in engine.holds.values() if h.defender == me and (not dfn or h.attacker.lower() == str(dfn).lower())]
    return bool(on_me) and not mine


ESCAPE_WORDS = re.compile(r"\b(?:escape\w*|writh\w*|twists? (?:free|loose|out)|head ?-?butt\w*|break\w* free|"
                          r"wrench\w* free|struggl\w*|squirm\w*|thrash\w*|wriggl\w*)\b", re.I)


TAKEDOWN_WORDS = re.compile(r"\b(?:throw\w*|threw|hurl\w*|slam\w*|toss\w*|flip\w*|(?:take|takes|taking|took|bring\w*|"
                            r"brought|drag\w*|knock\w*|sweep\w*|swept|pull\w*|yank\w*|wrestl\w*) (?:her|\w+) (?:down|over|"
                            r"off her feet)|to the ground|off (?:her|its) feet|onto (?:her|its) (?:back|side|front)|"
                            r"pin\w*)\b", re.I)
GRIP_WORDS = re.compile(r"\b(?:jaws|teeth|fangs|grip|hold|coils?|tails? (?:round|around)|clutch\w*|grasp|clamp\w*|"
                        r"vice|vise)\b", re.I)


def _drop_clauses(flavor, rx):
    """The director's words with every clause matching rx taken out ("..., and uses her momentum to throw her to the
    ground" goes); "" when nothing is left."""
    bits = re.split(r"(,\s*(?:and\s+|then\s+)?|\s+and\s+(?:then\s+)?|;\s*)", str(flavor or ""))
    keep = [b.strip() for k, b in enumerate(bits) if not k % 2 and b.strip() and not rx.search(b)]
    if not keep:
        return ""
    return keep[0] if len(keep) == 1 else ", ".join(keep[:-1]) + " and " + keep[-1]


def _unrolled_words(engine, act, att, flavor):
    """holds.unrolled_words: the director's words for a hold telling a takedown the engine didn't roll ("uses her
    momentum to throw Nerine to the ground") lose that clause; a breather's words about a grip on her ("wriggling
    free of Nerine's jaws") lose it when nothing holds her any more."""
    if not (engine.rules.get("holds", {}).get("unrolled_words") or {}).get("enabled", True) or not flavor:
        return flavor
    if act in ("hold", "submission", "grapple_hold") and (engine.rules.get("holds", {}).get("unrolled_words")
                                                         or {}).get("blows", True):
        # (since build 283) a hold whose words strike or charge her first ("whips Ripples with the tail, and charges
        # her into a tall pine, then presses her into the beach"): blows the engine never resolved. Those clauses
        # go, and with no grip left in what remains the hold is named by the engine instead
        foes = [re.escape(f.name) for f in engine.active() if f.name.lower() != str(att).lower()]
        who = r"(?:her|" + "|".join(foes) + r")" if foes else r"her"
        blow = re.compile(r"\b(?:whip\w*|strik(?:e|es|ing)|struck|punch\w*|kick\w*|smash\w*|head[- ]?butt\w*|charg\w*|"
                          r"tackl\w*|batter\w*|pound\w*)\s+(?:at\s+|into\s+)?" + who + r"\b|\b(?:charg\w*|ram\w*|driv\w*|"
                          r"drove|press\w*|smash\w*|slam\w*|crash\w*|hurl\w*|carr\w*|pin\w*)\s+" + who
                          + r"\s+(?:back\s+|hard\s+)?into\s+(?:a|an|the)\b", re.I)
        if blow.search(flavor):
            left = _drop_clauses(flavor, blow)
            grip = re.compile(r"\b(?:hold\w*|grip\w*|clamp\w*|coil\w*|wrap\w*|lock\w*|squeez\w*|bind\w*|bound|chok\w*|"
                              r"crush\w*|latch\w*|clutch\w*|constrict\w*|jaws?|teeth|fangs|wound|round|around)\b", re.I)
            flavor = left if left and grip.search(left) else ("" if act == "submission" else "a tight grip")
            if not flavor:
                return flavor
    if act in ("hold", "grapple_hold") and TAKEDOWN_WORDS.search(flavor):
        return _drop_clauses(flavor, TAKEDOWN_WORDS) or "a tight grip"
    if act == "breather":
        # a pause's words striking the other ("Head butts Ripples in the nose"): a blow the engine never resolved
        foes = [re.escape(f.name) for f in engine.active() if f.name.lower() != str(att).lower()]
        if foes:
            blow = re.compile(r"\b(?:head[- ]?butt\w*|butts?|butted|strik(?:es|ing)|struck|hits?|punch\w*|kicks?|kicked|"
                              r"slams?|slammed|bites?|bit|claws?|clawed|rakes?|raked|swipes?|swiped|smash\w*|jabs?|"
                              r"jabbed|elbows?|lashes|lashed|chops?|chopped|batters?|pounds?)\s+(?:at\s+|into\s+)?(?:"
                              + "|".join(foes) + r")\b", re.I)
            if blow.search(flavor):
                flavor = _drop_clauses(flavor, blow) or "catching her breath"
    if act == "breather" and GRIP_WORDS.search(flavor):
        me = engine.get(att).name
        if not any(me in (h.attacker, h.defender) for h in engine.holds.values()) and not engine.pinned_by(me) \
                and not engine.pinning(me):
            return _drop_clauses(flavor, GRIP_WORDS) or "catching her breath"
    return flavor


def _escape_worded(engine, att, hold_id, dfn, flavor):
    """The held fighter's name when this hold_release comes from the HOLDER but its words are the held fighter
    fighting free (holds.release_as_escape); else ""."""
    if not (engine.rules.get("holds", {}).get("release_as_escape") or {}).get("enabled", True):
        return ""
    if not ESCAPE_WORDS.search(str(flavor or "")) or re.search(r"\blet(?:s|ting)? go\b|\breleas\w* (?:her|the) "
                                                               r"(?:grip|hold) to\b", str(flavor or ""), re.I):
        return ""
    me = engine.get(att).name
    hs = ([engine.holds[hold_id]] if hold_id in engine.holds else
          [h for h in engine.holds.values() if h.attacker == me and (not dfn or h.defender.lower() == str(dfn).lower())])
    hs = [h for h in hs if h.attacker == me and h.defender != me]
    return hs[0].defender if hs else ""


def _own_pin(engine, att, hold_id, dfn):
    """True if this hold_release would free `att` from a pin she is under (which only a struggle can do)."""
    me = engine.get(att).name
    on_top = engine.pinned_by(me)
    if not on_top:
        return False
    if hold_id in engine.holds:
        h = engine.holds[hold_id]
        return h.defender == me and h.attacker in on_top
    # no id: it would end everything between the pair, whichever way round; her own grips on the pinner are hers to drop
    mine = [h for h in engine.holds.values() if h.attacker == me and (not dfn or h.defender.lower() == str(dfn).lower())]
    return not mine


EVENT_IN_PAUSE = re.compile(r"\b(gives? out|gave out|collaps\w*|falls?|fell|buckl\w*|gets? up|getting up|stands? up|"
                            r"ris(?:es|ing)|rose|tries to (?:rise|stand|get up)|goes down|topples?|crumples?|faints?|"
                            r"passes out|recovers? from)\b", re.I)
STREAM_WORDS = re.compile(r"\b(stream|beam|torrent|geyser|water (?:blast|jet|pressure|cannon)|(?:jet|blast|column|wall) of "
                          r"(?:water|ice|fire|flame))\b", re.I)


def _stream_for(engine, att, b, move):
    """A 'hold' or 'pin' that is really a stream or beam kept on the target ("Hydro Pump stream, pin against the
    stalagmite"): the sustainable move it should have been, or None. A grip needs a body; a stream is the move
    itself held for several pulses, with its own power, uses, energy cost, and the scenery behind her."""
    streams = [m for m in engine.get(att).moves if m.get("sustainable") and m.get("target") in ("spread", "targeted")]
    if not streams:
        return None
    if move is not None and not move.get("improvised"):
        return move if move in streams else None  # a real hold move (or a bite that stays locked on) is a hold
    said = " ".join([str(b.get("flavor") or ""), str(b.get("improvised_name") or "")]
                    + [str(h.get("with") or "") for h in (b.get("hits") or []) if isinstance(h, dict)])
    named = [m for m in streams if re.search(r"\b" + re.escape(m["name"]) + r"\b", said + " " + str(b.get("intent") or ""),
                                             re.I)]
    if named:
        return named[0]
    if not STREAM_WORDS.search(said):
        return None
    f = engine.get(att)
    usable = [m for m in streams if f.move_uses.get(m["name"], 1) > 0] or streams
    dfn = _fill_defender(engine, att, b.get("defender"))
    try:
        return max(usable, key=lambda m: engine.move_math(att, dfn, m)["effective"])
    except (ValueError, KeyError, TypeError):
        return usable[0]


BLOW_WORDS = re.compile(r"\b(slam|slams|smash\w*|strike|strikes|punch\w*|kick\w*|slash\w*|swipe\w*|swat\w*|shove\w*|"
                        r"stomp\w*|headbutt\w*|uppercut|jab\w*|chop\w*|ram|rams|rake\w*)\b", re.I)
GRIP_WORDS = re.compile(r"\b(hold\w*|grip\w*|grab\w*|pin\w*|press\w*|clamp\w*|coil\w*|wrap\w*|lock\w*|squeez\w*|bind\w*|"
                        r"chok\w*|crush\w*|latch\w*|clutch\w*|constrict\w*|trap\w*|weight|stand\w* on|step\w* on|kneel\w*|"
                        r"sit\w* on|grind\w*|twist\w*|wrench\w*|bite|bites|biting|jaws?|teeth|drag\w*|hook\w* (?:her|his)|"
                        r"pressure|stranglehold|headlock|scruff|around|onto|down on|against)\b", re.I)


def _is_a_blow(b, move):
    """A 'hold_start' with no hold move whose label describes a single blow ("Forepaw slam to the head") and
    nothing that holds on: it should have been a strike."""
    if move is not None:
        return False
    said = " ".join([str(b.get("flavor") or ""), str(b.get("improvised_name") or "")]
                    + [str(h.get("with") or "") for h in (b.get("hits") or []) if isinstance(h, dict)])
    return bool(BLOW_WORDS.search(said)) and not GRIP_WORDS.search(said)


def _as_stream(engine, b, move):
    """Rewrite a hold/pin beat as the sustained move it describes."""
    said = " ".join(str(b.get(k) or "") for k in ("pinned_against", "flavor", "intent"))
    against = str(b.get("pinned_against") or "").strip()
    if against.lower() in ("", "none", "no", "n/a", "nothing"):
        against = scene_feature(engine, said)
    hits = [h for h in (b.get("hits") or []) if isinstance(h, dict) and h.get("part")]
    out = dict(b, action="combo", move=move["name"], sustain=max(2, int(b.get("sustain") or 0) or 3),
               pinned_against=against, launch="none", landing=[], charge_into="", count=1, hits=hits)
    if not hits and b.get("part"):
        out["hits"] = [{"defender": b.get("defender"), "part": b["part"], "severity": "solid"}]
    return out


def resolve(engine, b):
    """Validate a director beat and apply it. Returns (result_dict, ids_of_holds_started_now).
    Raises ValueError with a readable message if the beat is invalid."""
    if isinstance(b.get("hits"), list) and any(isinstance(h, str) for h in b["hits"]):
        # a part named plainly ("Left Thigh") instead of {"part": "Left Thigh"}: read it as that
        b["hits"] = [{"part": h} if isinstance(h, str) else h for h in b["hits"]]
    act = b.get("action")
    if act in ("ally", "ally_end"):  # your /ally command: a temporary alliance begins or ends (a story beat)
        if act == "ally":
            res = engine.ally(b.get("members") or [], beats=b.get("beats"), until=b.get("until"))
        else:
            mine = [al for al in engine.alliances if not b.get("members")
                    or set(al["members"]) & {engine.get(n).name for n in b["members"]}]
            if not mine:
                raise ValueError("there is no alliance to end")
            res = engine.end_alliance(mine[0], "they called it off")
        res["flavor"] = " ".join(str(b.get("flavor", "")).split()[:20])
        res["intent"] = ""
        return res, ()
    if act not in ACTIONS and act not in ("quickpin", "pin_success", "pin_escape", "land", "down", "getup", "heal"):
        raise ValueError(f"action must be one of {ACTIONS}")
    att = b.get("attacker")
    flavor = short_phrase(b.get("flavor", ""), int(engine.rules.get("director", {}).get("flavor_words", 32)))
    # (keep it a label, not a paragraph, never ending on "and")
    dfn_ = str(b.get("defender") or "").split(",")[0].strip()
    mv_ = str(b.get("move") or b.get("improvised_name") or "").strip()
    if att and dfn_ and mv_ and mv_.lower() != "improvised":
        # "Ripples' Ice Fang lands..." on Nerine's own Ice Fang: the move is the attacker's
        flavor = re.sub(r"\b" + re.escape(dfn_) + r"(?:'s|'|’s|’) (" + re.escape(mv_) + r")\b",
                        lambda m: poss_word(att) + " " + m.group(1), flavor, flags=re.I)
    if att and re.search(r"\bkick", f"{mv_} {flavor}", re.I) and engine.get(att) is not None \
            and engine.body_plan(engine.get(att)) == "biped":
        # (since build 276) on two legs her paws are her hands: a kick is her foot ("Ripples drives her right paw")
        flavor = re.sub(r"\b(her |its )?((?:left |right )?)(?:hind )?paws?\b",
                        lambda m: (m.group(1) or "") + m.group(2) + "foot", flavor)
    intent = b.get("intent", "")
    was_involved = engine.get(att).name in engine.involved
    engine.get_active(att)
    manual = bool(b.get("_manual"))
    if act == "eliminate" and not manual and act not in director_actions(engine):
        raise ValueError("fighters can't be knocked out by the story: only a pin held for the full clock puts "
                         "someone out. Choose an attack, a knockdown, or a pin instead")
    if act == "eliminate":  # the defender IS the fighter who's out; never guess it
        dfn = b.get("defender")
        if not dfn:
            raise ValueError("'eliminate' needs the fighter who is out in 'defender'")
    else:
        dfn = _fill_defender(engine, att, b.get("defender"))
    if act == "struggle" and not manual and not any(p["defender"] == engine.get(att).name for p in engine.pins.values()):
        # nobody is pinning her: there is nothing to struggle out of. She gathers herself instead (a hold on her is
        # fought by the dice every beat anyway), rather than throwing the whole beat away as invalid
        act = "breather"
        b = dict(b, action="breather")
        if not any(h.defender == engine.get(att).name for h in engine.holds.values()):
            # (and nothing holds her at all: her flavor was written for a grip that isn't there, "thrashes on her back
            # and snaps at the feet that hold her", so it goes)
            b["flavor"], flavor = "", ""
    if act == "struggle":
        dfn = dfn or att
    elif act in ("strike", "combo", "hold_start", "pin", "eliminate", "quickpin", "pin_success", "pin_escape",
                 "throw", "slam", "drag", "grapple"):
        if not dfn:
            raise ValueError(f"'{act}' needs a defender")
        if dfn.lower() == att.lower() and act != "eliminate":
            raise ValueError("attacker and defender must be different fighters")
    if act == "hold_adjust" and dfn and dfn.lower() != att.lower() and not any(
            h.attacker == engine.get(att).name for h in engine.holds.values()):
        # (since build 278) "squeeze harder" with nothing held yet (Seraphina told to coil round Ripples' middle came
        # back as an adjust of a hold that wasn't there, and the beat was refused): it STARTS the grip instead, on the
        # parts it names, or for a coil on her middle
        hits_ = [h for h in (b.get("hits") or []) if isinstance(h, dict) and h.get("part")]
        if not hits_ and not b.get("part"):
            words = " ".join(str(b.get(k) or "") for k in ("flavor", "part", "with"))
            d_ = engine.get(dfn)
            named = [p for p in d_.parts if re.search(r"\b" + re.escape(p.lower()) + r"\b", words.lower())]
            if not named and (engine.body_plan(engine.get(att)) == "serpent"
                              or re.search(r"\b(?:coil|constrict|wrap|squeez|middle|midsection|body|waist)\w*", words, re.I)):
                named = [p for p in d_.parts if body_region(p) in ("belly", "chest")][:2]
            hits_ = [{"part": p, "severity": b.get("severity")} for p in named]
        if hits_:
            act = "hold_start"
            b = dict(b, action="hold_start", hits=hits_)
            b.pop("hold_id", None)
    if act in ("hold_adjust", "hold_release"):
        if not engine.holds:
            raise ValueError(f"'{act}' needs an active hold, and there are none. Choose another action")
        if (b.get("hold_id") not in engine.holds and len(engine.holds) == 1
                and act == "hold_adjust"):
            b["hold_id"] = next(iter(engine.holds))  # only one hold, so it must be that one

    b_aimed_at = b      # (what she aimed at, before any re-aiming below)
    if not manual and act in ("strike", "combo") and engine.get(att).name not in (getattr(engine, "ordered", None) or ()):
        # (a player's own order lands where she said: no re-aiming for the fighters you play)
        b = _apply_focus(engine, att, dfn, b)
        if not b.get("_aimed"):
            b = _apply_variety(engine, att, dfn, b)
    if (not manual and dfn and engine._taps_rule() and act in ("strike", "combo", "hold_start", "submission")
            and engine.get(att).name not in (getattr(engine, "ordered", None) or ())):
        b = _apply_tap_steer(engine, att, dfn, b, "strikes" if act in ("strike", "combo") else "holds")
        if b.get("_steered_from"):
            # (moved onto the part being worked: its words were put right with it)
            flavor = short_phrase(b.get("flavor", ""), int(engine.rules.get("director", {}).get("flavor_words", 32)))
    mv_aim = engine.find_move(att, b.get("move") or "") if b is not b_aimed_at and act in ("strike", "combo") \
        and dfn else None
    if mv_aim is not None:
        # (since build 298) re-aimed (focus, variety, tap steer) onto a part she can't reach from where she holds her or
        # is held: the blow goes where she aimed it instead
        try:
            a_, d_ = engine.get(att), engine.get(dfn)
            from engine import match_part as _match
            new = [p for p in ([b.get("part")] + [h.get("part") for h in b.get("hits") or [] if isinstance(h, dict)])
                   if p and _match(list(d_.parts), p)]
            new = [d_.part(p).name for p in new]
            if new and (engine.held_reach_block(a_, d_, mv_aim, new) or engine.holder_reach_block(a_, d_, mv_aim, new)):
                b = b_aimed_at
        except ValueError as e:
            note_failure("checking a re-aimed blow is still in reach", e)
            intent = b.get("intent", intent)
    if not manual and dfn and act in ("strike", "combo", "hold_start"):
        # (since build 261) a head butt reaches what a head can reach, and the words name the parts the engine
        # resolves (director.words_to_parts)
        b2 = _words_to_parts(engine, dfn, _head_reach(engine, att, dfn, b))
        if b2.get("flavor") != b.get("flavor"):
            flavor = short_phrase(b2.get("flavor", ""), int(engine.rules.get("director", {}).get("flavor_words", 32)))
        b = b2
    if not manual and dfn and act in ("submission", "hold_start") \
            and engine.get(att).name not in (getattr(engine, "ordered", None) or ()):
        b = _apply_hold_mix(engine, att, dfn, b, act)
        if b.get("_mixed_from"):
            act, flavor = "submission", ""
    started = ()
    if not manual and act in ("grapple", "hold_start", "pin", "submission", "throw", "slam", "drag"):
        # confusion spoils a grab, a pin or a throw as surely as a blow: she may hurt herself instead
        me = engine.get(att)
        what = {"grapple": "a grab", "hold_start": "a hold", "pin": "a pin", "submission": "a submission hold",
                "throw": "a throw", "slam": "a slam", "drag": "dragging her"}[act]
        own = engine._confusion(me, {"name": what}, True, me.energy)
        if own:
            own["intent"] = intent
            return own, ()
    if act == "submission":
        if not dfn:
            raise ValueError("'submission' needs a defender")
        if not manual:
            flavor = _unrolled_words(engine, "submission", att, flavor)
        name = str(b.get("improvised_name") or b.get("submission") or "").strip().lower()
        grips = [(_fit_part(engine, dfn, h["part"]), short_phrase(h.get("with") or "", 9))
                 for h in (b.get("hits") or []) if isinstance(h, dict) and h.get("part")]
        if name and name not in engine.SUBMISSIONS and grips and not any(n in name for n in engine.SUBMISSIONS):
            # a hold of the director's own invention: the engine checks it against both bodies
            res = engine.start_custom_submission(att, dfn, name, grips, flavor, enforce=not manual,
                                                 upright=b.get("upright") if isinstance(b.get("upright"), bool) else None)
            res["intent"] = intent
            return res, tuple(res.get("hold_ids") or ())
        if name not in engine.SUBMISSIONS:
            fits = list(engine.submission_shapes(att, dfn))
            name = next((n for n in engine.SUBMISSIONS if n in f"{name} {b.get('flavor', '')}".lower()),
                        fits[0] if fits else name)
        if not manual and engine._taps_rule() and engine.get(att).name not in (getattr(engine, "ordered", None) or ()):
            # finish.submission.taps.steer: a named hold that grips only used-up parts (or misses the part being
            # worked, taps.steer.holds of the time) gives way to one that grips the part being worked
            shapes = engine.submission_shapes(att, dfn)
            aim, spent = engine.tap_target(dfn), set(engine.spent_tap_parts(dfn))
            cts = [c[0] for c in (shapes.get(name) or {}).get("contacts") or ()]
            if shapes and cts and (all(c in spent for c in cts) or (aim and aim not in cts)):
                alt = engine.pick_submission(shapes, defender=dfn)
                alt_cts = [c[0] for c in shapes[alt]["contacts"]]
                if all(c in spent for c in cts) or (aim in alt_cts and engine.rng.random() < engine.tap_steer("holds")):
                    name = alt
        res = engine.start_submission(att, dfn, name, flavor, enforce=not manual)
        res["intent"] = intent
        return res, tuple(res.get("hold_ids") or ())
    started = ()
    if act == "grapple":
        hits = [h for h in (b.get("hits") or []) if h.get("part")]
        part = b.get("part") or (hits[0]["part"] if hits else None)
        flavor_with = ""
        if not part:   # the order's own words name it ("round the white hind legs"): that part, and that grip
            part, flavor_with = _flavor_grip(engine, att, dfn, flavor)
        if not part:   # nothing named: an arm, the scruff, a shoulder
            body = list(engine.get(dfn).parts)
            reach = [p for p in body if body_region(p) in ("fore_up", "fore_low", "neck", "shoulder")] or body
            part = engine.rng.choice(reach)
        with_ = short_phrase((hits[0].get("with") if hits else "") or b.get("with") or flavor_with or "", 9)
        sev = str((hits[0].get("severity") if hits else None) or b.get("severity") or "light").lower()
        table = engine.rules["severity"]["hold"]
        if sev not in table or table[sev] > table.get("firm", 15):
            sev = "light" if "light" in table else min(table, key=table.get)   # a grab holds; it doesn't crush
        res = engine.grapple(att, dfn, _fit_part(engine, dfn, part), engine.power_for("hold", sev), with_, flavor,
                             enforce=not manual)
        res["intent"] = intent
        return res, tuple(res.get("hold_ids") or ())
    mv_name = str(b.get("move", "none")).lower()
    if not manual and act in ("strike", "combo") and (LANDING_NAME.match(mv_name) or (
            mv_name == "improvised" and LANDING_NAME.match(str(b.get("improvised_name") or "")))):
        # the director wrote someone's landing as an attack: the landing comes from the throw itself, so this
        # action is only a moment's pause (dropped when the beat has a real action)
        act, b = "breather", dict(b, action="breather", flavor="")
    move = None
    if mv_name == "improvised":
        if not manual and NOT_AN_ATTACK.search(str(b.get("improvised_name") or "")):
            raise ValueError(f"'{b.get('improvised_name')}' is not an attack: getting up, bracing, or recovering does no "
                             f"damage. If she attacks, name the attack (a kick, a bite, a tail strike); otherwise use "
                             f"'breather'")
        named_ = str(b.get("improvised_name") or "").strip()
        exact_ = " ".join(named_.lower().replace("-", " ").split())
        # (a real move she doesn't know, and one no body makes by itself: a Thunderbolt, not a Headbutt)
        if not manual and exact_ and any(" ".join(m["name"].lower().replace("-", " ").split()) == exact_
                                         and str(m.get("type") or "Normal") not in ("Normal", "Fighting")
                                         for m in engine.movedex) and not engine.find_move(b.get("attacker"), named_):
            # a real move she doesn't know ("Thunderbolt" for a Buizel): it would land as a plain Normal blow under
            # that move's name, and the story would tell the move
            own_ = ", ".join(m["name"] for m in engine.get(b.get("attacker")).moves)
            raise ValueError(f"'{named_}' is a move {b.get('attacker')} doesn't know. Use one of hers ({own_}), or "
                             f"name an improvised blow by what it is (a kick, a tail swipe, a shoulder)")
        if not manual and exact_:
            why = engine.strike_problem(engine.get(b.get("attacker")), named_)
            if why:
                raise ValueError(f"'{named_}' can't be done: {why}. Name an improvised blow by what her body has: "
                                 f"{', '.join(engine.get(b.get('attacker')).parts)}")
            ty_ = str(b.get("improvised_type") or "Normal")
            if not engine.can_wield_type(b.get("attacker"), ty_):
                raise ValueError(f"{b.get('attacker')} has no {ty_} power to improvise with: an improvised move is "
                                 f"Normal or Fighting, or a type of her own or of a move she knows "
                                 f"({', '.join(engine.wieldable_types(b.get('attacker')))})")
        conj_ = str(b.get("conjure") or "").strip()
        if conj_ and conj_.lower() not in ("none", "no", "false"):
            # she makes a weapon of her own element and keeps it a few beats (an ice blade frozen out of the water)
            engine.conjure(b.get("attacker"), conj_, b.get("improvised_type") or "Normal")
        target = "spread" if act == "combo" and len([h for h in (b.get("hits") or []) if h.get("part")]) > 1 else "targeted"
        move = engine.improvised_move(b.get("improvised_name"), b.get("improvised_type"), b.get("severity"),
                                      target, b.get("flavor", ""), who=b.get("attacker"))
        if conj_ and move.get("weapon"):
            move["conjured_now"] = True
    elif mv_name in ("none", "") and act in ("strike", "combo") and not manual:
        # a plain blow with no move named: it lands as a plain close technique, so every rule applies to it like any
        # close move (a dive from the air and who can reach whom, guards, feints, a pummel's lighter blows and rolled
        # length, the grind against what is behind her) instead of a bare hit that skipped them. Your own /strike
        # with no move stays a plain hit you control
        target = ("spread" if act == "combo" and len([h for h in (b.get("hits") or []) if h.get("part")]) > 1
                  else "targeted")
        fl = str(b.get("flavor") or "").strip()
        sev = b.get("severity") or next((h.get("severity") for h in (b.get("hits") or []) if h.get("severity")), None)
        move = engine.improvised_move(fl if fl and len(fl) <= 40 else _plain_name(fl), "Normal", sev, target,
                                      fl or "a plain close blow")
    elif mv_name != "none":
        move = engine.find_move(att, b.get("move"))
        dex = engine.dex_move(b.get("move")) if move is None and not manual and act in ("strike", "combo") else None
        if dex is not None and (float(dex.get("power", 0) or 0) <= 0 or dex.get("target") in ("status", "self")
                                or (dex.get("type") not in ("Normal", "Fighting", "Dark")
                                    and dex.get("type") not in engine.get(att).types)):
            # a move she doesn't know that is no plain blow (Hypnosis, a Flamethrower from a Water type): it must not
            # land as a generic hit under that name. A bite, a punch, a scratch she can always throw
            raise ValueError(f"{engine.get(att).name} doesn't know {b.get('move')}. Her moves: "
                             f"{', '.join(m['name'] for m in engine.get(att).moves)} (or an improvised technique)")
        if move is None and not manual and act in ("strike", "combo") and mv_name not in ("", "attack", "strike", "blow"):
            # a plain blow the director named in its own words ("a claw rake", "a kick to the hip"): it lands as an
            # improvised technique, so every rule applies to it (a dive from the air, feints, guards, the scenery)
            # instead of a bare hit that skips them
            target = ("spread" if act == "combo" and len([h for h in (b.get("hits") or []) if h.get("part")]) > 1
                      else "targeted")
            why_ = engine.strike_problem(engine.get(att), b.get("move"))
            if why_:
                # (since build 309) a Knee Strike from a Milotic: name the blow by what her body has
                raise ValueError(f"'{b.get('move')}' can't be done: {why_}. Name the blow by what her body has: "
                                 f"{', '.join(engine.get(att).parts)}")
            move = engine.improvised_move(b.get("move"), "Normal", b.get("severity"), target, b.get("flavor", ""))
        elif move is None and not manual and act in ("strike", "combo") and mv_name in ("attack", "strike", "blow"):
            target = ("spread" if act == "combo" and len([h for h in (b.get("hits") or []) if h.get("part")]) > 1
                      else "targeted")
            move = engine.improvised_move(_plain_name(b.get("flavor")), "Normal", b.get("severity"), target,
                                          b.get("flavor") or "a plain blow")
        if move is None and manual and act in ("strike", "combo"):
            # a typed /move the fighter doesn't know: use it from moves.json for this one attack (not learned)
            dex = engine.dex_move(b.get("move"))
            if dex is not None and dex.get("target") != "hold":
                move = dict(dex, one_off=True)
    if move is not None and act in ("strike", "combo") and move.get("target") == "hold":
        act = "hold_start"  # a hold move used as an attack means starting the hold
    if (move is not None and act == "hold_start" and move.get("target") == "hold"
            and re.search(r"\bpin", move["name"], re.I)):
        act = "pin"  # a pinning move is a pin, with the pin rules and the clock, not a plain hold
    was_hold = None
    if act in ("hold_start", "pin") and not manual:
        stream = _stream_for(engine, att, b, move)
        if stream is not None:
            # "holds her against the stalagmite with Hydro Pump" is the MOVE, held: not a grip
            was_hold, act, move = act, "combo", stream
            b = _as_stream(engine, b, stream)
    if act == "hold_start" and not manual and _is_a_blow(b, move):
        # "Forepaw slam to the head" filed as a hold: it lands as the blow it is (damage now, nothing left gripping)
        was_hold, act = act, "combo"
        b = dict(b, action="combo")
    if act == "hold_start" and not manual and move is not None and move.get("target") != "hold":
        # a grip filed under an attack move ("hold_start" with Aqua Jet): the grip is her paws or tails on her, not
        # the move, so it doesn't carry the move's name (the story then told a charge and a grip at once)
        if re.fullmatch(r"(?i)\s*(?:an? |her )?%s\s*[.!]?\s*" % re.escape(move["name"]), str(flavor or "")):
            flavor = "grabs hold"
        move = None
        b = dict(b, move="none")
    if (move is not None and act == "strike" and b.get("carry") is True and not engine.is_ranged(move)
            and not move.get("charge") and not move.get("carry") and move.get("target", "targeted") == "targeted"
            and engine.can_carry(att, dfn)[0]):
        # she seizes her in her talons (feet, hands) on the way past and tries to haul her up: rolled (flight.carry)
        move = dict(move, grab_carry=True)
    lf = str(b.get("leap_from") or "").strip()
    if (move is not None and act == "strike" and lf and lf.lower() not in ("none", "false", "no", "")
            and engine.has(engine.get(dfn), "airborne") and not engine.has(engine.get(att), "airborne")
            and not engine.is_ranged(move)):
        move = dict(move, leap_from=lf)
    if move is not None and act in ("strike", "combo"):
        hits = [h for h in (b.get("hits") or []) if h.get("part")]
        if manual and not hits and not b.get("part") and move.get("target") in ("targeted", "spread"):
            # a typed /move with no parts named: the dice pick where it lands
            body = list(engine.get(dfn).parts)
            pick = engine.rng.sample(body, min(len(body), 1 if move["target"] == "targeted" else 3))
            hits = [{"defender": dfn, "part": p} for p in pick]
            b = dict(b, part=pick[0])
        by_def = {}
        if move.get("target") == "spread" and hits:
            for h in hits:
                who = _fill_defender(engine, att, h.get("defender")) or dfn
                by_def.setdefault(who, []).append(h["part"])
        else:
            first = b.get("part") or (hits[0]["part"] if hits else None)
            extra = [h["part"] for h in hits if h["part"] != first
                     and (_fill_defender(engine, att, h.get("defender")) or dfn) == dfn]
            by_def[dfn] = ([first] if first else []) + (extra if move.get("target") == "targeted" else [])
        count = int(b.get("count", 1) or 1)
        if not manual:
            count = max(1, min(count, 6))      # the director's limit (its schema says 1-6); your own /move can go higher
        pummel = False
        place = (engine.pummel_place(att, dfn) if count > 1 and not _multi_hit(engine, move) and len(by_def) == 1
                 and move.get("target") == "targeted" and not move.get("charge") else None)
        if place:
            # the same close move, thrown again and again at no distance: inside a grab, from on top in a pin, on
            # a fighter pressed against the scenery, or on one who is down (sitting or lying)
            pummel = place
        elif not manual and count > 1 and not _multi_hit(engine, move):
            count = 1  # a single charge or slash lands once; only flurry moves (Fury Swipes...) repeat
        results = [engine.move_attack(att, who, move["name"], parts, count, flavor,
                                      move=move if (move.get("improvised") or move.get("one_off")
                                                     or move.get("grab_carry") or move.get("leap_from")) else None,
                                      enforce=not manual,
                                      sustain=int(b.get("sustain") or 0), against=b.get("pinned_against") or "",
                                      charge_into=str(b.get("charge_into") or "").strip()
                                      if str(b.get("charge_into") or "").strip().lower() not in ("none", "no", "n/a") else "",
                                      pummel=pummel, feint=bool(b.get("feint")) and len(by_def) == 1)
                   for who, parts in by_def.items()]
        res = results[0]
        if len(results) > 1:  # one spread move catching several fighters
            res = dict(res, defender=", ".join(r["defender"] for r in results),
                       defenders=[r["defender"] for r in results],
                       hits=[h for r in results for h in r["hits"]],
                       move_by_defender={r["defender"]: r["move"] for r in results})
            res["hit_count"] = len(res["hits"])
        res["intent"] = intent
        if was_hold:
            res["was_hold"] = was_hold  # the director filed it as a hold or pin; it ran as the held move
        return res, started
    if act == "strike":
        if not b.get("part"):
            raise ValueError("strike needs 'part'")
        power = _severity(engine, "instant", b.get("severity"), "solid")
        res = engine.instant(att, dfn, _fit_part(engine, dfn, b["part"]), power, int(b.get("count", 1) or 1), flavor,
                             enforce=not manual)
    elif act == "combo":
        hits = b.get("hits") or []
        if not hits and b.get("part"):
            hits = [{"part": b["part"], "severity": b.get("severity", "solid")}]
        if not hits:
            raise ValueError("combo needs a non-empty 'hits' list")
        pairs = []
        for h in hits:
            who = _fill_defender(engine, att, h.get("defender")) or dfn
            pairs.append((who, _fit_part(engine, who, h["part"]),
                          _severity(engine, "instant", h.get("severity"), "solid")))
        res = engine.multi(att, dfn, pairs, flavor, enforce=not manual)
        if was_hold:
            res["was_hold"] = was_hold
    elif act in ("hold_start", "pin"):
        hits = [h for h in (b.get("hits") or []) if h.get("part")]
        if not hits and b.get("part"):
            hits = [{"part": b["part"], "severity": b.get("severity")}]
        if not hits and act == "pin":
            # a bare /pin: one of the pin shapes this pinner's body allows (what presses where, filled out), as the
            # director would choose it, so the story knows what she pins her with
            try:
                shapes = pin_shapes(engine, engine.get(att), engine.get(dfn))
            except Exception as e:
                note_failure("choosing a pin shape", e)
                shapes = {}
            weights = {k: float(v) for k, v in ((engine.rules.get("director") or {}).get("pin_shape_weights") or {}).items()
                       if not str(k).startswith("_")}
            shapes = {k: v for k, v in shapes.items() if weights.get(k, 1.0) > 0}     # a shape set to 0 is never used
            if shapes:
                name = engine.rng.choices(sorted(shapes), weights=[weights.get(k, 1.0) for k in sorted(shapes)])[0]
                look, cts = shapes[name]
                hits = [{"part": p, "severity": "crushing" if i == 0 else "firm", "with": w}
                        for i, (p, w) in enumerate(cts)]
                # the shape's words are an idea written for the director: its asides ("say so with ...") are not
                # part of the label
                look = re.sub(r"\s*\([^)]*\)", "", look).strip(" ,;")
                if name == "dunk" and not b.get("pinned_against"):
                    pool = next((h["name"] for h in (engine.scene_cfg.get("hazards") or [])
                                 if any(w in ("pool", "shallows", "water") for w in h.get("words", []))), None)
                    if pool:
                        b["pinned_against"] = pool
                if str(flavor or "").strip() in ("", "pins them down"):
                    flavor = look
                b["_bare_pin"] = True
        if not hits:  # nothing named: press the defender's most-damaged parts, or their core if unhurt
            hits = [{"part": p, "severity": "crushing" if i == 0 else "firm"}
                    for i, p in enumerate(engine.default_pin_parts(dfn, 3 if act == "pin" else 1))]
        ramp = engine.ramp_for(b.get("ramp") or "steady")
        move_power, move_info = (engine.hold_power(att, dfn, move["name"])
                                 if move is not None and move.get("target") == "hold" else (None, None))
        merged = {}  # the same body part listed twice -> one hold at the stronger pressure
        from engine import match_part
        body = list(engine.get(dfn).parts)
        for h in hits:
            part = _fit_part(engine, dfn, h["part"])
            exact = any(n.lower() == " ".join(str(h["part"]).replace("_", " ").split()).lower() for n in body)
            if part.lower() in merged and not exact:
                # a borrowed part name landed on a spot that's already pressed: use the next nearby part
                alt = match_part(body, h["part"], avoid={m[0] for m in merged.values()})
                part = alt or part
            key = part.lower()
            power = move_power if move_power is not None else _severity(engine, "hold", h.get("severity"), "firm")
            if key not in merged or power > merged[key][1]:
                merged[key] = (part, power, ramp, short_phrase(h.get("with", ""), 9))
        contacts = list(merged.values())
        if len(contacts) == 1 and not contacts[0][3]:
            # a grip with nothing named to hold it with ("wraps her twin tails around her knee", and no "with"): the
            # limb the flavor names, so the story and the checks know what holds her
            m_ = re.search(r"\b(?:her |its |their )?((?:twin |sickle |long )?tails?|jaws|teeth|fangs|fore ?paws|paws|"
                           r"claws|hind legs|legs|arms|horn|wings|talons|coils)\b", str(flavor or ""), re.I)
            if re.search(r"\bbit(?:e|es|ing|ten)\b|\bsinks? (?:her )?teeth\b", str(flavor or ""), re.I):
                contacts = [contacts[0][:3] + ("her jaws",)]     # (she bites her tail: her jaws, not the tail)
            elif m_:
                contacts = [contacts[0][:3] + ("her " + m_.group(1).lower(),)]
        if not manual:
            for c in contacts:
                why = engine.grip_problem(engine.get(att), c[3] if len(c) > 3 else "")
                if why:
                    raise ValueError(f"that grip can't go on as described: {why}. Grip with what she has: "
                                     f"{', '.join(engine.get(att).parts)}")
        if not manual and act in ("hold_start", "pin"):
            # (holds.coil.size, since build 275) a serpent that dwarfs her can't coil one of her limbs alone: her
            # coils go round the middle first, the limbs bound in under them or not
            contacts, coil_note = engine.coil_body_first(att, dfn, contacts, move_info or move, flavor)
            if coil_note:
                bits = ["her coils wound round her middle"] + [
                    f"her {c[0].lower()} bound in under them" if str(c[3]).startswith("her coils, binding")
                    else f"{c[3] or 'pressure'} on her {c[0].lower()}" for c in contacts[1:]]
                flavor = ", ".join(bits)
        if not manual:
            # a face-down fighter can't have her chest pressed (and a face-up one her back): fit the contacts
            fitted, note = engine.fit_to_facing(dfn, [c[0] for c in contacts], flavor)
            if note:
                best = {}
                for fp, c in zip(fitted, contacts):  # two presses landing on the same spot -> keep the stronger
                    if fp not in best or c[1] > best[fp][1]:
                        best[fp] = (fp,) + tuple(c[1:])
                contacts = list(best.values())
        else:
            note = None
        if act == "pin" and (not manual or b.get("_bare_pin")) and contacts:
            # a pin the director wrote with too few points of contact (twin tails round one foreleg) is filled out
            # from what the pinner still has free, like any pin shape; its label is rebuilt from the real grips
            least = int(((engine.rules.get("pin") or {}).get("contacts") or {}).get("min", 3))
            # only a pin that is starting is filled out: a grip added to a running pin, or a second pinner piling
            # on, is just that grip (the pin already has its points of contact)
            if engine.pin_on(engine.get(dfn).name) is not None:
                least = 0
            if len(contacts) < least:
                _, filled = fuller_pin(engine, engine.get(att), engine.get(dfn), "",
                                       [(c[0], c[3] if len(c) > 3 else "") for c in contacts], at_least=least)
                have = {c[0] for c in contacts}
                firm = _severity(engine, "hold", None, "firm")
                contacts = list(contacts) + [(p, firm, ramp, w) for p, w in filled if p not in have]
            if len(contacts) > 1 and (len(str(flavor or "")) > 90 or len(contacts) > len(merged)):
                bits = [f"{(c[3] or 'pressure').split(',')[0]} on her {c[0].lower()}" for c in contacts]
                flavor = ", ".join(bits[:-1]) + " and " + bits[-1]
        if not manual and act == "hold_start":
            # (since build 261) what her limbs can really do (engine.check_grips: holds.invented_check)
            ok_, why_ = engine.check_grips(att, dfn, [(c[0], c[3] if len(c) > 3 else "") for c in contacts])
            if why_:
                keep_ = {p for p, _w in ok_}
                contacts = [c for c in contacts if c[0] in keep_]
                b["_grips_dropped"] = why_
        if not manual and act == "hold_start":
            # (since build 260) the hold as bodies can do it: a push with nothing behind her goes, one limb on
            # several parts splits its pressure (engine.shape_hold: holds.backstop, holds.grip_share)
            contacts, gone = engine.shape_hold(att, dfn, contacts, against=b.get("pinned_against") or "")
            if gone or b.get("_grips_dropped"):
                # (the words rebuilt from the grips that are left: one limb's parts said together)
                by_limb = {}
                for c in contacts:
                    by_limb.setdefault((c[3] if len(c) > 3 and c[3] else "a grip").split(",")[0], []).append(c[0].lower())
                bits = [f"{w} on her " + (" and ".join(ps) if len(ps) < 3 else ", ".join(ps[:-1]) + " and " + ps[-1])
                        for w, ps in by_limb.items()]
                flavor = (", ".join(bits[:-1]) + " and " + bits[-1]) if len(bits) > 1 else bits[0]
        if not manual and act != "pin":
            flavor = _unrolled_words(engine, "hold", att, flavor)
        res = engine.start_holds(att, dfn, contacts, flavor, pin=(act == "pin"), move=move_info, enforce=not manual)
        res["facing"] = engine.facing_of(dfn)
        # a takedown that turned her over moved the presses (throat -> neck) and their words with them
        hf = next((engine.holds[i].flavor for i in res.get("hold_ids") or [] if i in engine.holds), None)
        if hf and res.get("flavor") and hf != res["flavor"] and hf.lower() != str(res["flavor"]).lower():
            res["flavor"] = hf
        if act == "pin" and not res.get("continuing"):
            found = _pin_against(engine, b, flavor)
            pin_now = engine.pin_on(engine.get(dfn).name)
            if found and pin_now is not None and not pin_now.get("against"):
                prop, water = found
                pin_now["against"] = prop      # jammed against something solid (or held under): harder to escape
                res["against"] = prop
                if water:
                    # a DUNK: her face held down in the water. It soaks her and she comes up sputtering, for real
                    target = engine.get(dfn)
                    res["dunk"] = True
                    pin_now["dunk"] = True
                    res["hazard_status"] = engine.hazard_effects(target, [prop])
                    if not engine.has(target, "soaked"):
                        engine.set_status(target, "soaked", int(engine._cfg("status_effects").get("soaked_beats", 3)))
                    engine.set_status(target, "sputtering", 2)
        if note:
            res["facing_note"] = note
        started = tuple(res["hold_ids"])
    elif act == "hold_adjust":
        hid = b.get("hold_id")
        power = _severity(engine, "hold", b["severity"], "firm") if b.get("severity") else None
        ramp = engine.ramp_for(b["ramp"]) if b.get("ramp") else None
        # a grip that has ramped up past the severity table ("crushing" = 25, the grip is at 31) must not be
        # "adjusted" DOWN by a beat that means to squeeze harder: only an easing beat lowers it
        easing = str(b.get("ramp") or "").lower() == "easing" or bool(EASE_WORDS.search(flavor or ""))

        def at_least(h):
            return power if (manual or easing or power is None) else max(power, h.power)
        if hid in engine.holds:
            res = engine.set_intensity(int(hid), power=at_least(engine.holds[int(hid)]), change_per_turn=ramp)
        else:  # no/unknown id: tighten or ease every hold this attacker has on this defender
            mine = [h for h in engine.holds.values() if h.attacker.lower() == att.lower()
                    and (not dfn or h.defender.lower() == str(dfn).lower())]
            if not mine:
                raise ValueError(f"{att} has no active hold to adjust. Active holds: "
                                 f"{[f'#{h.id} {h.attacker}->{h.defender}' for h in engine.holds.values()]}")
            changes = [engine.set_intensity(h.id, power=at_least(h), change_per_turn=ramp) for h in mine]
            res = dict(changes[0], hold_ids=[c["hold_id"] for c in changes], part=", ".join(c["part"] for c in changes),
                       changes=changes)
        res["flavor"] = flavor
    elif act == "hold_release" and not manual and _own_pin(engine, att, b.get("hold_id"), dfn):
        # the pinned fighter "releasing" the pin on herself is an escape attempt: the engine rolls it
        res = engine.request_struggle(att, None)
        res["flavor"] = flavor
    elif act == "hold_release" and not manual and _held_not_holder(engine, att, b.get("hold_id"), dfn):
        # the HELD fighter "releasing" a grip that is on her: that is a break-out, and the engine rolls those at
        # the end of every beat. This beat she strains against it; the roll says whether it gives.
        res = {"type": "breather", "focus": engine.get(att).name, "flavor": "straining against the hold"}
    elif act == "hold_release" and not manual and _escape_worded(engine, att, b.get("hold_id"), dfn, flavor):
        # the HOLDER "releasing" a grip in words that are the held fighter fighting free ("Head butts Ripples in the
        # nose ... she writhes and twists to escape the hold"): that is her break-out try, and the dice decide it
        held = _escape_worded(engine, att, b.get("hold_id"), dfn, flavor)
        res = {"type": "breather", "focus": held, "flavor": flavor or "straining against the hold"}
    elif act == "hold_release":
        hid = b.get("hold_id")
        if hid in engine.holds:
            res = engine.release(int(hid), flavor or "released")
        else:  # 0 / unknown: end everything between this pair, whichever way round it is
            holders = {(h.attacker.lower(), h.defender.lower()) for h in engine.holds.values()}
            pair = next(((x, y) for x, y in holders if att.lower() in (x, y)
                         and (not dfn or dfn.lower() in (x, y))
                         and (manual or not engine.pinned_by(engine.get(att).name) or x == att.lower())), None)
            if pair is None:
                raise ValueError(f"no active hold involving {att}. Active: {list(engine.holds)}")
            res = engine.release_between(pair[0], pair[1], flavor or "released")
    elif act == "eliminate":
        if not manual and engine.ko_only():
            raise ValueError("only a knockout ends a fight now (finish.knockout_only): no one is simply declared out. "
                             "Keep fighting: a hard blow on a badly worn fighter can knock her out")
        res = engine.eliminate(dfn, flavor)
    elif act == "struggle":
        pinner = b.get("defender") if b.get("defender") and str(b.get("defender")).lower() != att.lower() else None
        res = engine.request_struggle(att, pinner if pinner and any(
            p["attacker"].lower() == str(pinner).lower() for p in engine.pins.values()) else None)
        res["flavor"] = flavor
    elif act in ("pin_success", "pin_escape"):
        contacts = None
        hits = [h for h in (b.get("hits") or []) if h.get("part")]
        if hits:
            firm = engine.rules["severity"]["hold"].get("firm", 15)
            contacts = [(_fit_part(engine, dfn, h["part"]), _severity(engine, "hold", h.get("severity"), "firm")
                         if h.get("severity") else firm, 0.0, h.get("with", "")) for h in hits]
        res = engine.force_pin(att, dfn, "success" if act == "pin_success" else "escape", contacts, flavor)
    elif act in ("throw", "slam", "drag"):
        impacts = [(x.get("surface"), x.get("parts") or [], x.get("severity")) for x in (b.get("landing") or [])
                   if isinstance(x, dict) and str(x.get("surface") or "").strip()]
        held = engine.grabbed_by(att, dfn)
        res = engine.manhandle(att, dfn, act, impacts, flavor, enforce=not manual,
                               tumble=True if b.get("tumble") else None)
        if held:
            res["from_grab"] = True
    elif act == "land":
        impacts = [(x.get("surface"), x.get("parts") or [], x.get("severity")) for x in (b.get("landing") or [])]
        res = engine.land(att, impacts or [("the ground", [], "solid")], how=flavor, thrown=True,
                          tumble=bool(b.get("tumble")))
        res["launch"] = "thrown"
    elif act == "heal":
        res = engine.heal(att, b.get("heal_parts") or [], float(b.get("heal_amount") or 0),
                          float(b.get("heal_res") or 0), float(b.get("heal_health") or 0), flavor)
    elif act == "getup":
        res = engine.force_get_up(att, b.get("count") or None)
    elif act == "down":
        who = engine.get(att).name
        already = who in engine.downed
        facing = engine.knock_down(who, facing=b.get("facing"), why=f"{who} went down")
        res = {"type": "knockdown", "fighter": who, "flavor": flavor, "facing": facing, "already_down": already,
               "knock_on": engine._knock_on}
        engine._knock_on = []
    elif act == "quickpin":
        res = engine.pinfall(att, dfn)
        res["flavor"] = flavor
    else:  # breather
        if not manual and EVENT_IN_PAUSE.search(flavor):
            # "collapsed leg gives out again": a pause can't make anyone fall, rise, or fail to rise (the engine rolls
            # those); it is only a pause
            flavor = "catching her breath"
        if not manual:
            flavor = _unrolled_words(engine, "breather", att, flavor)
        res = {"type": "breather", "focus": att, "flavor": flavor}
        who = engine.get(att).name
        if not was_involved and not engine.pinned_by(who) and not engine.pinning(who) and not any(
                who in (h.attacker, h.defender) for h in engine.holds.values()):
            engine.involved.discard(who)   # a real pause: she rests (energy.rest_bonus), no exertion

    res["intent"] = intent
    return res, started


GROUND_LIKE = re.compile(r"floor|ground|stone|rock|pool|water|ledge|channel|shallows|sand|mud|puddle|grating|deck|"
                         r"plating|planks?|planking|boards|ice|snow|grass|gravel|flagstones?|basalt|shelf|earth|dirt", re.I)


def _juggle_next(engine, b, res, actions, i, limit):
    """Is this strike a launch that the NEXT action follows up on her in the air (a juggle)? moves.vulnerable.juggled"""
    if not isinstance(res, dict) or res.get("type") != "instant" or not res.get("hits") or res.get("dodged") \
            or res.get("environment") or len(res.get("defenders") or [1]) > 1 or i >= min(limit, len(actions)):
        return False
    launch = str(b.get("launch") or "none").lower()
    if launch in ("none", "staggered", ""):
        launch = str(res.get("auto_launch") or "")
    if launch != "launched" or (b.get("landing") or []) or _low_blow(engine, res):
        return False
    who = res.get("defender")
    if not who or engine.get(who).eliminated or engine.pinned_by(engine.get(who).name):
        return False
    nxt = actions[i] if i < len(actions) and isinstance(actions[i], dict) else {}
    try:
        from_above = engine.has(engine.get(nxt.get("attacker")), "airborne")
    except (ValueError, KeyError, TypeError, AttributeError):
        from_above = False
    if not from_above and (str(nxt.get("charge_into") or "").strip() or (
            int(nxt.get("sustain") or 0) > 1 and str(nxt.get("pinned_against") or "").strip())):
        # from the ground, a charge drives her back along it and a held stream pins her to the scenery: neither can
        # follow up on a fighter up in the air, so this launch lands first and the next action meets her down
        # (from ABOVE they are a spike that drives her down: still a juggle)
        return False
    return _next_on(actions, i, who)


def _next_on(actions, i, who):
    """Is the action after this one a strike on `who`?"""
    if i >= len(actions):
        return False
    nxt = actions[i]
    return (nxt.get("action") in ("strike", "combo") and str(nxt.get("defender") or "").lower() == str(who).lower()
            and str(nxt.get("move") or "none").lower() != "none")


def _low_blow(engine, res):
    """moves.low_launch: the blow's main hit is on her lower legs or feet (it can sweep her, not launch her)."""
    from engine import body_region
    if not ((engine.rules.get("moves") or {}).get("low_launch") or {}).get("enabled", True):
        return False
    hits = [h for h in res.get("hits") or [] if isinstance(h, dict) and h.get("part")]
    return bool(hits) and body_region(str(hits[0]["part"])) == "hind_low"


def _landing(engine, b, res):
    """A strike that knocks down, throws, or launches: the defender crashes into the arena (environmental hits)."""
    if (res.get("type") != "instant" or res.get("environment") or not res.get("hits") or res.get("confused_self_hit")
            or (res.get("sustain") and res["sustain"].get("against"))  # already slammed into the scenery
            or res.get("ground_into")  # held against the scenery with nowhere to give: she isn't sent flying
            or (res.get("charge") and not res["charge"].get("skipped"))):  # driven into it by the charge itself
        return None  # nothing landed (dodged, or no effect): nobody goes flying
    launch = str(b.get("launch") or "none").lower()
    fell = False
    if launch in ("none", "staggered", "") and res.get("auto_launch"):
        launch = res["auto_launch"]  # the move itself knocks down, throws, or launches (moves.json)
        fell = bool(res.get("fell_from_air"))  # the throw roll failed: she was knocked out of the air, not thrown
    impacts = [x for x in (b.get("landing") or []) if isinstance(x, dict)]
    if launch in ("thrown", "launched") and not b.get("_manual") and not res.get("auto_launch") and _low_blow(engine, res):
        # (since build 261) a blow to her feet or lower legs takes her legs out from under her: she goes down where
        # she stood, not up into the air (moves.low_launch)
        launch, res["swept"] = "knocked down", True
    if launch in ("none", "staggered", "") and not impacts:
        return None
    if launch in ("none", "staggered", ""):
        launch = "knocked down"  # they crashed into something, so they went down
    who = (res.get("defenders") or [res.get("defender")])[0]
    if not who or engine.get(who).eliminated:
        return None
    who = engine.get(who).name
    manual = bool(b.get("_manual"))
    if not manual and not res.get("auto_launch") and not res.get("spiked_by") and engine.has(engine.get(who), "airborne") \
            and engine._rights_herself(engine.get(who), {}, launch, engine.rules.get("flight") or {}):
        # the director's launch on a flyer still in the air: she may catch herself on her wings, as she would from a
        # move that launches (flight.air_recover)
        res["righted"] = launch
        return None
    thrown = launch in ("thrown", "launched")
    explicit = bool(impacts)
    in_place = False
    att = res.get("attacker")
    if (res.get("guard") or {}).get("kind") == "block" and not impacts:
        res["launch_blocked"] = f"{who} caught it on her guard and kept her feet"
        return None   # a blocked blow doesn't knock her down or throw her (a crash into scenery still happens)
    if not manual and att and engine.pinned_by(engine.get(att).name):
        res["launch_blocked"] = "the attacker is pinned: only a struggle gets her out"
        return None  # a pinned fighter can't throw her pinner off with a strike; escapes are rolled
    if not manual and att and not res.get("auto_launch") and not impacts \
            and engine._held_on_ground(engine.get(att), engine.get(who)) \
            and ((engine.rules.get("holds") or {}).get("held_reach") or {}).get("enabled", True):
        # held on the ground in her grip: a blow from down there hurts her, it doesn't send her flying (breaking
        # out is the struggle's roll)
        res["launch_blocked"] = "the attacker is held down in her grip: a blow from there can't throw her off"
        return None
    if not manual and att and ((engine.rules.get("holds") or {}).get("held_no_launch") or {}).get("enabled", True):
        mine = [h for h in engine.holds.values() if h.attacker == engine.get(att).name and h.defender == who]
        if mine:
            # (since build 311, holds.held_no_launch) she is in the attacker's own grip: the blow can't send her flying
            # or into the scenery, the grip holds her where she is (a throw out of a hold is a hold_release first)
            res["launch_blocked"] = (f"{who} is held in {poss_word(engine.get(att).name)} "
                                     f"{'coils' if any(h.coil for h in mine) else 'grip'}: she can't be {launch} out of it")
            return None
    if engine.pinned_by(who) and not (manual and thrown):
        # held down: she can't be knocked down, thrown, or launched. At most she's driven into the ground under her
        ground = engine.scene_word("ground").split()[-1].lower()
        impacts = [x for x in impacts if GROUND_LIKE.search(str(x.get("surface") or ""))
                   or ground in str(x.get("surface") or "").lower()]
        if not impacts:
            res["launch_blocked"] = f"{who} is pinned: she can't be {launch}"
            return None
        in_place, thrown = True, False
    elif who in engine.downed and not thrown:
        if not explicit:
            return None  # already on the ground: there's nowhere further to fall
        in_place = True  # already down: smashed against what's beside her, not knocked down again
    if in_place and impacts:
        # driven into what she lies on: the blow and the drive are one impact, so the part the blow struck isn't
        # struck a second time; what meets the ground is what she lies on (her underside)
        struck = {h.get("part") for h in res.get("hits") or [] if h.get("defender", who) == who}
        under = [p for p in engine.underside_parts(who, 4) if p not in struck]
        fixed = []
        for x in impacts:
            ps = [p for p in (x.get("parts") or []) if str(p).title() not in struck and p not in struck]
            if x.get("parts") and len(ps) < len(x["parts"]):
                ps += [p for p in under if p not in ps][:len(x["parts"]) - len(ps)]
            fixed.append(dict(x, parts=ps))
        impacts = fixed
    if not in_place and not manual and launch == "knocked down" and not explicit and not res.get("auto_launch") \
            and not res.get("spiked_by") and not res.get("drop_severity") and not engine.has(engine.get(who), "airborne"):
        # down.keep_feet: the director wanted her down, but she may stagger and stay up (likelier strong, or a light blow)
        kept, ch = engine.keeps_feet(engine.get(who), res.get("hits"))
        if kept:
            res["stayed_up"] = {"chance": ch, "manner": engine.vary("keeps_feet")}
            res["launch_blocked"] = f"{who} staggers under it but stays on her feet"
            res.pop("rocked", None)     # (the stagger is how the blow moved her: no "feet stay where they are" too)
            return None
    if not in_place:
        # knocked off her feet: that is how the blow moved her, so no rock or stagger on top of it (moves.stumble)
        res.pop("rocked", None)
        if res.get("moved"):
            res["moved"] = "launch"
        if res.get("status_applied"):
            res["status_applied"] = [x for x in res["status_applied"] if not (x.get("stumble") and x.get("fighter") == who)]
        engine.get(who).status.pop("staggered", None)
    force, spiked = 1.0, bool(res.get("spiked_by") and res.get("spike"))
    if not impacts and res.get("spiked_by"):
        # knocked up into the air and smashed back down out of it by the next blow: the landing is a hard one. From
        # a height it is at least as hard as the fall; driven straight down (a SPIKE: a dive, a charge, a held stream
        # from above) it is harder still (flight.spike: severity_bump, landing_force)
        order = ["light", "solid", "heavy", "brutal"]
        sev = "heavy"
        if res.get("drop_severity") in order and order.index(res["drop_severity"]) > order.index(sev):
            sev = res["drop_severity"]
        if spiked:
            sp = (engine.rules.get("flight") or {}).get("spike") or {}
            sev = order[min(len(order) - 1, order.index(sev) + int(sp.get("severity_bump", 1)))]
            force = float(sp.get("landing_force", 1.3))
        impacts = [{"surface": engine.scene_word("ground"), "parts": [], "severity": sev}]
        launch = "thrown"
    if not impacts and res.get("drop_severity"):
        # dropped out of the air (carried up and let go, or a wing gave out): the height decides how hard
        impacts = [{"surface": engine.scene_word("ground"), "parts": [], "severity": res["drop_severity"]}]
    if not impacts:
        if launch == "knocked down":  # dropped where they stand: just marked as down, a light landing
            impacts = [{"surface": "the ground", "parts": [], "severity": "light"}]
        else:
            impacts = [{"surface": engine.scene_word("ground"), "parts": [], "severity": "solid"}]
    word = "driven into" if in_place else "knocked out of the air" if fell and not res.get("spiked_by") \
        else (launch if launch != "none" else "knocked down")
    out = engine.land(who, [(x.get("surface"), x.get("parts") or [], x.get("severity")) for x in impacts],
                      credited=res.get("spiked_by") or res["attacker"], thrown=thrown, in_place=in_place, can_recover=(thrown or launch == "knocked down") and not manual,
                      tumble=False if spiked else True if b.get("tumble") else (None if not manual else False),
                      force=force,
                      how=f"{word}: " + " → ".join(short_phrase(x.get("surface"), default="the ground") for x in impacts))
    out["launch"] = "driven down" if out.get("in_place") else "knocked out of the air" if fell and not res.get("spiked_by") \
        else launch
    if res.get("spiked_by"):
        out["spiked_by"] = res["spiked_by"]
    if spiked:
        out["spiked_down"] = True
    return out


_WHERE = re.compile(r"\s*[,;:]?\s+(?:at|to|on|onto|across|into|against|over|along|under|through|toward|towards|in|for)\s+"
                    r"(?:her|his|its|the|[A-Z][\w-]+(?:'s|’s|'|’)?)\s+[^,;]*(?=[,;]|$)")


def true_label(engine, label, hits):
    """The director's few words for an attack, kept honest: if they name a side or a body part the attack did NOT
    land on (the target was moved by /focus, or fitted onto another species' body), the wrong place is cut out of
    the label. "Raking claw swipe at her right flank" on a Left Hip hit -> "Raking claw swipe"."""
    label = str(label or "")
    parts = [h.get("part") for h in hits or [] if isinstance(h, dict) and h.get("part")]
    if not label or not parts:
        return label
    low = label.lower()
    hit_sides = {x for x in ((re.search(r"\b(left|right)\b", p.lower()) or [None])[0] for p in parts) if x}
    said_sides = set(re.findall(r"\b(left|right)\b", low))
    wrong = bool(said_sides and hit_sides and not (said_sides & hit_sides))
    if not wrong:
        # only the TARGET's body counts ("her flank", "the chest"): "jaws", "a paw", "tail whip" are the attacker's
        hit_regions = {body_region(p) for p in parts}
        hit_words = {w for p in parts for w in p.lower().split()}
        for m in re.finditer(r"\b(?:her|his|its|the|[A-Z][\w-]+(?:'s|’s|'|’))\s+((?:(?:left|right|upper|lower)\s+)*)([a-z]+)", label):
            w = m.group(2).lower()
            if w in hit_words or w.rstrip("s") in hit_words:
                continue
            r = body_region(w)
            if r != "other" and r not in hit_regions:
                wrong = True
                break
    if not wrong:
        return label
    cut = re.sub(r"^[\s,;]+|[\s,;]+$", "", _WHERE.sub("", label)).strip()
    return cut if cut and cut != label and len(cut.split()) >= 1 else ""


_BITE_WORDS = re.compile(r"\b(?:teeth|fangs?|jaws?|bit(?:e|es|ing)|bitten|chomp\w*|maw)\b", re.I)


def _move_of(engine, res):
    """The move behind a result: its own dict when the fighter knows it, else what the result carries."""
    mv = res.get("move") or {}
    try:
        return engine.find_move(res.get("attacker"), mv.get("name")) or mv
    except (ValueError, KeyError):
        return mv


def _knockouts(engine, results, hp0):
    """After the beat's actions: did what landed on someone knock her out cold? (moves.knockout; very rare)"""
    out = []
    for who in dict.fromkeys(r.get("defender") for r in results if isinstance(r, dict) and r.get("defender")):
        try:
            f = engine.get(str(who).split(",")[0].strip())
        except (ValueError, KeyError):
            continue
        if f.eliminated:
            continue
        mine = [r for r in results if isinstance(r, dict) and r.get("defender") == f.name
                and (r.get("hits") or r.get("landings"))]
        if not mine:
            continue
        kinds = []
        for r in mine:
            if r.get("sustain"):
                kinds.append("held stream")
            if r.get("pummel"):
                kinds.append("pummel")
            if (r.get("chain") or {}).get("link", 1) > 1:
                kinds.append("chain")
            if r.get("charge") and not r["charge"].get("skipped"):
                kinds.append("charge")
            if r.get("spiked_down") or (r.get("juggle") or {}).get("spiked"):
                kinds.append("spike")
            elif r.get("juggle"):
                kinds.append("blow in mid-air")
            if r.get("carried") or (r.get("environment") and any(l.get("severity") in ("heavy", "brutal")
                                                                for l in r.get("landings") or [])):
                kinds.append("drop" if r.get("carried") or r.get("drop_severity") else "slam")
            if r.get("manhandle") == "slam":
                kinds.append("slam")
            if r.get("grounded") and not r.get("carried"):
                kinds.append("fall out of the sky")     # struck down from flying height: a drop, as much as a carry is
        dev = any(h.get("devastating") for r in mine for h in (r.get("hits") or []))
        ko = engine.knockout_roll(f.name, hp0.get(f.name, f.health) - f.health, list(dict.fromkeys(kinds)), dev)
        if ko:
            ko["by"] = next((r.get("attacker") for r in reversed(mine) if r.get("attacker") != f.name), None)
            out.append(ko)
            # out cold on that blow: she doesn't stagger or rock on her feet after it (moves.stumble)
            f.status.pop("staggered", None)
            for r in mine:
                if r.get("status_applied"):
                    r["status_applied"] = [x for x in r["status_applied"]
                                           if not (x.get("fighter") == f.name and x.get("stumble"))]
                if (r.get("rocked") or {}).get("fighter") == f.name:
                    r.pop("rocked", None)
    return out


def honest_move_name(engine, res, label):
    """A label that names ANOTHER of her moves ("Flare Blitz" on what was really a Flamethrower): the real move's
    name goes in its place, so the narrator isn't told one move while the engine ran another."""
    label = str(label or "")
    real = str((res.get("move") or {}).get("name") or "")
    if not label or not real:
        return label
    try:
        mine = [m["name"] for m in engine.get(res.get("attacker")).moves]
    except (ValueError, KeyError, TypeError):
        return label
    for name in sorted(mine, key=len, reverse=True):
        if name.lower() != real.lower() and re.search(r"\b" + re.escape(name) + r"\b", label, re.I) \
                and not re.search(r"\b" + re.escape(real) + r"\b", label, re.I):
            label = re.sub(r"\b" + re.escape(name) + r"\b", real, label, flags=re.I)
    return label


def honest_weapon(label, move):
    """The director's few words for an attack, kept to the weapon the move really uses: "she rolls her over, her
    teeth clamping down" on a Hip Roll has no bite in it, so the clause about teeth is cut (the narrator would
    otherwise tell a bite nobody threw)."""
    label = str(label or "")
    if not label or not _BITE_WORDS.search(label):
        return label
    about = f"{(move or {}).get('name', '')} {(move or {}).get('about', '')} {(move or {}).get('description', '')}"
    if "bite" in kind_of(about, "") or _BITE_WORDS.search(about):
        return label
    bits = re.split(r"(,\s*|;\s*|\s+and\s+|\s+then\s+|\s+while\s+)", label)
    keep, i = [], 0
    while i < len(bits):
        part, sep = bits[i], (bits[i + 1] if i + 1 < len(bits) else "")
        if not _BITE_WORDS.search(part):
            keep.append(part + sep)
        i += 2
    out = re.sub(r"(?:,\s*|;\s*|\s+(?:and|then|while))\s*$", "", "".join(keep)).strip()
    return out or str((move or {}).get("name") or "")


def resolve_many(engine, actions):
    """Apply several actions in order, all or nothing: if any one is invalid, nothing changes.
    Returns (results, ids_of_holds_started_now)."""
    if isinstance(actions, dict):
        actions = [actions]
    if not actions:
        raise ValueError("a beat needs at least one action")
    # (since build 261) the same action sent twice in a row (the build-260 log told "Ripples wrenches at the grip"
    # twice): it happens once
    once = []
    for x in actions:
        if once and isinstance(x, dict) and isinstance(once[-1], dict) and x.get("action") in ("breather", "struggle") \
                and all(str(x.get(k) or "").strip().lower() == str(once[-1].get(k) or "").strip().lower()
                        for k in ("attacker", "defender", "action", "flavor")):
            continue
        once.append(x)
    actions = once
    # (since build 293, moves.head) a STUNNED fighter does nothing this beat, whatever she was given: she sways there
    stunned_ = []
    for b in actions:
        f_ = engine.fighters.get(str((b or {}).get("attacker") or "").lower()) if isinstance(b, dict) else None
        if f_ is not None and engine.has(f_, "stunned") and b.get("action") not in ("breather", "wait"):
            if not any(x.get("attacker") == f_.name and x.get("action") == "breather" for x in stunned_):
                stunned_.append({"action": "breather", "attacker": f_.name,
                                 "flavor": "stunned, swaying where she is, nothing in her answering yet"})
            continue
        stunned_.append(b)
    actions = stunned_
    if not actions:
        raise ValueError("a beat needs at least one action")
    # a hold followed by a pin on the same fighter in one beat is really one pin: fold the hold's contacts in
    pins = {(str(b.get("attacker")).lower(), str(b.get("defender")).lower()): b for b in actions if b.get("action") == "pin"}
    merged = []
    for b in actions:
        key = (str(b.get("attacker")).lower(), str(b.get("defender")).lower())
        if b.get("action") == "hold_start" and key in pins:
            pins[key]["hits"] = list(b.get("hits") or []) + list(pins[key].get("hits") or [])
            continue
        merged.append(b)
    actions = merged
    # finish.submission.taps.respite: after a tap that wasn't the last, nobody strikes or grips her this beat:
    # whatever the director had the others do to her becomes a step back while she gets up
    resp = []
    for b in actions:
        dn = str(b.get("defender") or "").split(",")[0].strip()
        try:
            held_off = (not b.get("_manual") and dn and b.get("action") in
                        ("strike", "combo", "hold_start", "submission", "grapple", "pin", "quickpin", "throw", "slam",
                         "drag") and engine.get(dn).name != engine.get(b.get("attacker")).name
                        and engine.tap_respite(dn))
        except ValueError:
            held_off = False
        if held_off:
            b = {"action": "breather", "attacker": b.get("attacker"),
                 "flavor": f"steps back and lets {engine.get(dn).name} get up after the tap", "_respite": True}
        resp.append(b)
    actions = resp
    # (since build 277) director.plan_dominate: a beat that belongs to the winner of /plan dominate. An attack the
    # director still gave the other one on her becomes a struggle (held) or a step back
    if getattr(engine, "_dominate_turn", None) and engine._dominate_turn == (engine.turn, False):
        win_ = str((engine.plan or {}).get("winner") or "")
        dom = []
        for b in actions:
            try:
                att_ = engine.get(b.get("attacker")) if b.get("attacker") else None
                dn_ = engine.get(str(b.get("defender") or "").split(",")[0].strip()) if b.get("defender") else None
            except ValueError:
                att_ = dn_ = None
            if (not b.get("_manual") and att_ and dn_ and win_ and dn_.name.lower() == win_.lower()
                    and att_.name != dn_.name and engine.dominated(att_.name) < 1.0
                    and b.get("action") in ("strike", "combo", "hold_start", "submission", "grapple", "pin", "quickpin",
                                            "throw", "slam", "drag", "charge")):
                held_ = any(h.defender == att_.name and h.attacker == dn_.name for h in engine.holds.values())
                b = ({"action": "struggle", "attacker": att_.name, "defender": dn_.name,
                      "flavor": f"fights {poss_word(dn_.name)} grip with what little room she has", "_dominated": True}
                     if held_ else
                     {"action": "breather", "attacker": att_.name,
                      "flavor": f"is given no room to answer {dn_.name}: she covers up and gives ground", "_dominated": True})
            dom.append(b)
        actions = dom
    # someone's landing written as an attack ("hard landing"): it comes from the throw, not from a blow
    landings = [b for b in actions if not b.get("_manual") and b.get("action") in ("strike", "combo")
                and (LANDING_NAME.match(str(b.get("move") or "")) or (str(b.get("move") or "").lower() == "improvised"
                                                                     and LANDING_NAME.match(str(b.get("improvised_name") or ""))))]
    if landings and len(landings) < len(actions):
        actions = [b for b in actions if b not in landings]
    # a pause tacked onto a beat that has a real action adds nothing but a line: the action is the beat
    real = [b for b in actions if b.get("action") != "breather" or b.get("_manual")
            or str(b.get("reposition") or "none").lower() != "none"]
    if real and len(real) < len(actions):
        actions = real
    snap = engine.snapshot_state()
    hp0 = {f.name: f.health for f in engine.fighters.values()}
    results, started = [], ()
    # a CHAIN: two or three attacks in a row by one fighter on one opponent (a grab may open it, a throw or a slam
    # may close it). Each link leads into the next: a link that lands makes the next harder to dodge, and a link
    # that is dodged (or that she has no breath left for) ends it there.
    # only a chain may run past three actions (director.chain.hard_cap: a distant limit, 0 = none)
    ccfg = engine.rules.get("director", {}).get("chain", {}) or {}
    cap = int(ccfg.get("hard_cap", 6) or 0)
    limit = 3
    if len(actions) > 3:
        whole = _chain_links(actions[:cap] if cap else actions)
        if whole.get(0) and whole.get(3) and whole[0][1] == whole[3][1]:
            limit = whole[0][1]          # one run from the first action on: all of it is played
    links = _chain_links(actions[:limit])
    engine._chain_on = None
    engine._juggle, engine._feint_open = None, None
    dropped = []      # links of a chain that could not be thrown: (move, why)
    try:
        for i, b in enumerate(actions[:limit], start=1):
            link = links.get(i - 1)
            if link and link[0] > 1:
                prev = next((r for r in reversed(results) if isinstance(r, dict) and r.get("chain")), None)
                if prev is not None and ((prev.get("hits") and not prev.get("confused_self_hit"))
                                         or prev.get("type") == "grapple_start"):
                    try:
                        engine._chain_on = (engine.get(b.get("attacker")).name,
                                            engine.get(_fill_defender(engine, b.get("attacker"), b.get("defender"))).name)
                    except Exception:
                        engine._chain_on = None
            was_sitting = {n for n in engine.downed if engine.facing.get(n) == "sitting up"}
            try:
                how = str(b.get("reposition") or "none").lower()
                how = {"sit up": "sit her up", "sit": "sit her up", "stand up": "stand her up",
                       "stand": "stand her up"}.get(how, how)
                if how in ("take off", "land"):
                    # the ATTACKER herself goes up into the air, or comes down out of it (winged fighters only)
                    me = engine.get(b.get("attacker"))
                    if how == "take off" and not engine.has(me, "airborne"):
                        try:
                            results.append(engine.take_off(me.name, enforce=True))
                        except ValueError:
                            if b.get("_manual"):
                                raise
                    elif how == "land" and engine.has(me, "airborne"):
                        me.status.pop("airborne", None)
                        results.append({"type": "land_flight", "fighter": me.name})
                    if b.get("action") == "breather" and any(x.get("action") != "breather" for x in actions):
                        continue
                elif how != "none" and b.get("action") in ("strike", "combo", "hold_start", "pin", "breather",
                                                          "hold_adjust", "throw", "slam", "drag"):
                    who = _fill_defender(engine, b.get("attacker"), b.get("defender"))
                    if who:
                        ev = engine.reposition(b.get("attacker"), who, how, force=bool(b.get("_manual")))
                        if ev:
                            told = " ".join(str(b.get("flavor") or "").split()[:15])
                            if b.get("action") == "breather" and told and told.lower() != how:
                                ev["told"] = told   # your own words for how she does it
                            results.append(ev)
                            if b.get("action") == "breather" and any(x.get("action") != "breather" for x in actions):
                                continue   # moving her WAS this action; the rest of the beat follows it
                        elif b.get("_manual"):
                            raise ValueError(f"can't {how} {who} right now (she has to be on the ground; not pinned for "
                                             f"a pick-up, a sit-up or a stand-up; and not already that way)")
                        elif re.search(r"\b(haul|lift|pick|roll|flip|turn|sit|sat|stand|stood|drag)\w*\b.{0,12}\bher\b|"
                                       r"\bher\b.{0,12}\b(up|over)\b", str(b.get("flavor") or ""), re.I):
                            # the move didn't happen (she's pinned, or it's too soon to move her again): the
                            # director's words for it mustn't reach the story either
                            b["flavor"] = str(b.get("move") or "") if str(b.get("move") or "none").lower() not in (
                                "none", "improvised") else ""
                if link and link[0] >= 3 and not b.get("_manual") and results and engine._chain_on:
                    # a chain that has run this far may end at any link: the longer it is, the likelier; a tired
                    # attacker and a fresh defender both end it sooner
                    how = engine.chain_break(*engine._chain_on, link[0])
                    if how == "spent":
                        dropped.append((str(b.get("move") or b.get("action") or "attack"),
                                        "she has nothing left to follow it with"))
                        last = next((r for r in reversed(results) if isinstance(r, dict) and r.get("chain")), None)
                        if last is not None:
                            last["chain"]["ended"] = "no follow-through"
                            last["chain"]["of"] = last["chain"]["link"]
                        engine._chain_on = None
                        break
                    engine._force_dodge = how == "dodge"
                if link and link[0] > 1 and not b.get("_manual") and b.get("action") == "strike" and b.get("part") \
                        and not getattr(engine, "directed", False):
                    # a chain link after the first: the dice decide whether it goes back to the spot the last link
                    # landed on or somewhere new (moves.repeat_target). A part you named stays as you said.
                    prev = next((r for r in reversed(results) if isinstance(r, dict) and r.get("chain")
                                 and r.get("hits")), None)
                    try:
                        who = _fill_defender(engine, b.get("attacker"), b.get("defender"))
                        last = prev["hits"][0]["part"] if prev and prev.get("defender") == engine.get(who).name else None
                        if last:
                            want = _fit_part(engine, who, b["part"])
                            got = engine.next_target(who, last, f"chain link {link[0]}")
                            mv_, a_, d_ = engine.find_move(b["attacker"], b.get("move") or ""), \
                                engine.get(b["attacker"]), engine.get(who)
                            if got == last and mv_ and (engine.held_reach_block(a_, d_, mv_, [got])
                                                        or engine.holder_reach_block(a_, d_, mv_, [got])):
                                got = want      # (since build 298) the old spot is out of reach from her hold now
                            if got == last or want == last:
                                hl = [dict(h) for h in (b.get("hits") or []) if isinstance(h, dict)]
                                if hl and hl[0].get("part"):
                                    hl[0]["part"] = got     # (a spread move lands where its hit list says)
                                b = dict(b, part=got, _aimed=True, **({"hits": hl} if hl else {}))
                            else:
                                b = dict(b, _aimed=True)      # somewhere new: where the director aimed it
                    except (ValueError, KeyError):
                        pass
                pb = None
                try:
                    g = engine.grab_between(b.get("attacker"), _fill_defender(engine, b.get("attacker"), b.get("defender")))
                    pb = g.attacker if g else None
                except Exception:
                    pb = None
                try:
                    res, st = resolve(engine, b)
                    if pb and isinstance(res, dict) and res.get("type") == "instant" and not res.get("environment") \
                            and res.get("hits") and b.get("action") in ("strike", "combo"):
                        res["point_blank"] = pb
                except ValueError as e:
                    if (b.get("action") == "pin" and not b.get("_manual") and results
                            and "no opening for a pin" in str(e)):
                        continue  # the rest of the beat stands; there was simply no opening to follow it with a pin
                    if not b.get("_manual") and results and "still pressed against it" in str(e):
                        continue  # the charge stands; the fighter it crushed doesn't get to answer in the same beat
                    if link and link[0] > 1 and not b.get("_manual") and results:
                        dropped.append((str(b.get("move") or b.get("action") or "attack"), str(e)))
                        if "times in a row" in str(e) and i < len(actions[:limit]) and links.get(i):
                            # only THAT move is barred (the same move a third time running): the link that was to
                            # come after it is still hers to throw, straight out of the last one that landed
                            continue
                        # she can't follow through (no breath left, she went down, the move isn't hers to use
                        # again): the chain simply ends with the links that landed
                        last = next((r for r in reversed(results) if isinstance(r, dict) and r.get("chain")), None)
                        if last is not None:
                            last["chain"]["ended"] = "no follow-through"
                            last["chain"]["of"] = last["chain"]["link"]
                        engine._chain_on = None
                        break
                    raise
                finally:
                    engine._chain_on = None
                    engine._force_dodge = False
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"action {i} ({b.get('action')}): {e}" if len(actions) > 1 else str(e)) from e
            if isinstance(res, dict) and res.get("type") == "instant" and res.get("hits") and res.get("flavor") \
                    and not res.get("environment"):
                res["flavor"] = honest_move_name(engine, res, honest_weapon(
                    true_label(engine, res["flavor"], res["hits"]), _move_of(engine, res))) or (
                    (res.get("move") or {}).get("name") or "attack")
            if link and isinstance(res, dict):
                res["chain"] = {"link": link[0], "of": link[1]}
            results.append(res)
            started += tuple(st)
            if link and isinstance(res, dict) and res.get("dodged") and link[0] < link[1]:
                res["chain"]["ended"] = "dodged"      # she slipped this one: what was meant to follow never comes
                break
            jg = engine._juggle
            if jg and isinstance(res, dict) and res.get("type") == "instant" and res.get("defender") == jg["who"]:
                # the follow-up caught her in the air: it smashes her back down (her landing from the launch, harder)
                engine._juggle = None
                res["juggle"] = {"launched_by": jg["res"].get("attacker")}
                if jg["res"].get("carried"):
                    res["juggle"]["falling"] = jg["res"]["carried"].get("height")   # struck as she falls
                if res.get("spiked_down"):
                    res["juggle"]["spiked"] = True
                    jg["res"]["spike"] = True
                left = int(jg.get("falls_left", 0))
                if res.get("hits") and not res.get("spiked_down") and left > 0 and i < limit \
                        and _next_on(actions, i, jg["who"]) and not engine.get(jg["who"]).eliminated:
                    # dropped from high enough, she is still falling: the next blow can catch her too
                    engine._juggle = dict(jg, falls_left=left - 1,
                                          mid=left - 1 > 0 and _next_on(actions, i + 1, jg["who"]))
                    jg["res"]["spiked_by"] = res.get("attacker")
                    res["still_falling"] = True
                    land = None
                else:
                    jg["res"]["spiked_by"] = res.get("attacker") if (res.get("hits") or jg["res"].get("spiked_by")) else None
                    land = _landing(engine, jg["b"], jg["res"])
            elif jg:
                engine._juggle = None       # nothing followed her up: she lands from the launch as usual
                jg["res"].pop("juggled_up", None)
                land0 = _landing(engine, jg["b"], jg["res"])
                if land0:
                    results.append(land0)
                land = _landing(engine, b, res)
            elif _juggle_next(engine, b, res, actions, i, limit):
                engine._juggle = {"who": engine.get((res.get("defenders") or [res.get("defender")])[0]).name,
                                  "b": b, "res": res,
                                  "falls_left": int((((engine.rules.get("flight") or {}).get("carry") or {})
                                                     .get("fall_strikes") or {}).get(res.get("drop_severity"), 0))
                                  if res.get("carried") else 0}
                fl = engine._juggle["falls_left"]
                sp = (engine.rules.get("flight") or {}).get("spike") or {}
                # a slash on the way down when more are coming; the last blow from above may drive her down (rolled
                # once: flight.spike.close_chance; a charge or a held stream from above always does)
                engine._juggle["mid"] = fl > 0 and _next_on(actions, i + 1, engine._juggle["who"])
                engine._juggle["close_spike"] = engine.rng.random() < float(sp.get("close_chance", 0.6))
                res["juggled_up"] = True
                land = None
            else:
                land = _landing(engine, b, res)
            if land:
                results.append(land)
            if isinstance(res, dict) and res.get("leap_fall") and res.get("attacker") \
                    and not engine.get(res["attacker"]).eliminated:
                # her leap fell short: she drops from the height she climbed and lands badly
                fall = engine.land(res["attacker"], [(engine.scene_word("ground"), [], res["leap_fall"])],
                                   credited="", thrown=False, can_recover=True,
                                   how=f"falling from {(res.get('leap') or {}).get('from', 'the height')}: "
                                       f"{short_phrase(engine.scene_word('ground'), default='the ground')}")
                fall["launch"] = "fell"
                fall["leap_fall"] = (res.get("leap") or {}).get("from")
                results.append(fall)
            # a hard enough hit shakes loose whatever the fighter it lands on was holding with
            for r in ([res] + ([land] if land else [])):
                if not isinstance(r, dict) or r.get("type") != "instant":
                    continue
                lost = {}
                for h in r.get("hits") or []:
                    who = h.get("defender") or r.get("defender")
                    lost[who] = lost.get(who, 0.0) + float(h.get("health_loss") or 0.0)
                for h in r.get("counter_hits") or []:
                    lost[r.get("attacker")] = lost.get(r.get("attacker"), 0.0) + float(h.get("health_loss") or 0.0)
                mv = r.get("move") or {}
                why = (mv.get("name") or r.get("flavor") or "the hit") if not r.get("environment") else "the landing"
                # a fighter who was sitting up doesn't stay sitting through a blow: it knocks her flat
                for who in list(lost):
                    hit = [h["part"] for h in (r.get("hits") or []) if (h.get("defender") or r.get("defender")) == who]
                    # (only a fighter who was sitting BEFORE this action; a landing that ends with her sitting
                    # against a wall has just put her there)
                    flat = (engine.flatten(who, hit) if who and hit and not r.get("dodged") and who in was_sitting
                            and not (r.get("environment") and not r.get("in_place")) else None)
                    if flat:
                        r["knock_on"] = list(r.get("knock_on") or []) + [flat]
                for who, amount in lost.items():
                    loose = engine.shake_grips(who, amount, why) if who else []
                    if loose:
                        r["knock_on"] = list(r.get("knock_on") or []) + loose
                        started = tuple(i for i in started if i in engine.holds)
        if engine._juggle:
            # launched for a follow-up that never came (cut short, dodged, refused): she comes down from the launch
            jg, engine._juggle = engine._juggle, None
            land = _landing(engine, jg["b"], jg["res"])
            jg["res"].pop("juggled_up", None)
            if land:
                results.append(land)
        results += _knockouts(engine, results, hp0)
    except Exception:
        engine._chain_on = None
        engine._juggle = None
        engine.restore_state(snap)
        raise
    engine._chain_on = None
    engine._juggle, engine._feint_open = None, None
    if dropped:
        # the chain as it really went: number the links that happened, and say what was left out and why. A "chain"
        # with one link left is simply an attack
        ch = [r for r in results if isinstance(r, dict) and r.get("chain")]
        for k, r in enumerate(ch, start=1):
            more = max(0, int(r["chain"]["of"]) - int(r["chain"]["link"])) if r["chain"].get("ended") == "dodged" else 0
            r["chain"]["link"], r["chain"]["of"] = k, len(ch) + more
        if ch:
            ch[-1]["chain_dropped"] = [{"move": m, "why": w} for m, w in dropped]
            if len(ch) == 1 and ch[0]["chain"].get("ended") != "dodged":
                ch[0].pop("chain")
            elif ch[-1]["chain"].get("ended") == "no follow-through" and len(dropped) == 1 \
                    and "times in a row" in dropped[0][1]:
                ch[-1]["chain"].pop("ended")    # nothing was cut short in the story: one link was simply never thrown
    _note_big_moments(engine, results)
    return results, started


def _chain_links(actions):
    """{index: (link number, links planned)} for a run of two or more attacking actions by ONE fighter on ONE
    opponent. A grab may open the run; a throw or a slam may only close it."""
    def key(b):
        return (str(b.get("attacker") or "").lower(), str(b.get("defender") or "").lower())
    run, out = [], {}

    def close():
        if len(run) >= 2:
            for n, j in enumerate(run, start=1):
                out[j] = (n, len(run))
    for j, b in enumerate(actions):
        act = b.get("action")
        ok = act in ("strike", "combo", "throw", "slam", "grapple") and key(b)[0] and key(b)[1]
        if ok and run and key(actions[run[0]]) == key(b) and act != "grapple" \
                and actions[run[-1]].get("action") not in ("throw", "slam") \
                and not str(actions[run[-1]].get("charge_into") or "").strip():
            run.append(j)
            continue
        close()
        run = [j] if ok and act not in ("throw", "slam") else []
    close()
    return out


def big_moment_kinds(results):
    """The big moments in a beat's results: a held stream, a charge into the scenery, a throw or slam, a grapple, a
    chain of at least two landed links."""
    kinds = []
    landed = 0
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get("sustain") and int(r["sustain"].get("held") or 0) > 1:
            kinds.append("held stream")
        if r.get("charge") and not r["charge"].get("skipped"):
            kinds.append("charge")
        if r.get("manhandle") in ("throw", "slam") and r.get("hits"):
            kinds.append("throw or slam")
        if r.get("type") == "grapple_start" and not r.get("existing"):
            kinds.append("grapple")
        if r.get("chain") and (r.get("hits") or r.get("type") == "grapple_start"):
            landed += 1
    if landed >= 2:
        kinds.append("chain")
    return list(dict.fromkeys(kinds))


def _note_big_moments(engine, results):
    kinds = big_moment_kinds(results)
    if kinds:
        engine.tally["big|moments"] = int(engine.tally.get("big|moments", 0)) + 1
        engine.tally["big|last"] = int(engine.turn)
        for r in results:
            if isinstance(r, dict):
                r.setdefault("big_moment", kinds)
                break


def story_line(engine):
    """HOW THE FIGHT STANDS, for the director: the same plain account the narrator gets (director.story_state)."""
    if not engine.rules.get("director", {}).get("story_state", True):
        return ""
    try:
        ss = engine.story_peek()
    except Exception as e:
        note_failure("the story line for the director", e)
        ss = None
    if not ss:
        return ""
    return ("HOW THE FIGHT STANDS (the shape of the whole, worked out by the program. It changes no rule and no "
            "number; let it colour WHAT each fighter would try: one who is ahead presses, one who is behind and "
            "worried gets careful or desperate, one who is shaken wants distance):\n- " + ss["stage"] + ".\n"
            + "\n".join(f"- {n} {t}" for n, t in ss["fighters"].items()) + "\n\n")


class Director:
    def __init__(self, model, host="http://localhost:11434", temperature=0.9, retries=3):
        self.model, self.host = model, host
        self.temperature, self.retries = temperature, retries

    def next_beat(self, engine, scene, story_so_far, direction="", recent_attacks=None, players=None):
        """Ask the model for the next beat and apply it. Returns (beat_json, result, started_ids).
        players: {fighter: what her player ordered (text), "WAIT" (she holds back), or None (the director chooses)}
        for the fighters the user plays (/play)."""
        recent = "\n".join(f"- {x}" for x in (recent_attacks or [])[-8:]) or "(none yet)"
        players = {k: v for k, v in (players or {}).items() if any(f.name == k for f in engine.active())}
        # is there an opening for a pin on anyone this beat? (rolled once, so retries don't re-roll it; a typed
        # direction always may pin). When you play a fighter they were rolled as you were asked, and shown to you.
        if getattr(engine, "_windows_ready", False):
            engine._windows_ready = False
        else:
            engine.roll_pin_windows(open_all=bool(direction) and getattr(engine, "dice_mode", "fair") != "strict")
        # "a devastating hit" in your direction: the first blow that lands this beat is one (no roll), unless the dice
        # are strict (/play dice strict)
        engine._force_dev = bool(direction and re.search(r"\bdevastat\w*", direction, re.I)
                                 and getattr(engine, "dice_mode", "fair") != "strict")
        # your words decide where blows land; the dice only fill in what you left open
        engine.directed = bool(direction) or any(v and v != "WAIT" for v in players.values())
        engine.ordered = {n for n, v in players.items() if v and v != "WAIT"}   # fighters acting on a player's order
        hint = initiative_hint(engine) if not direction else ""
        urged = encourage_hint(engine) if not direction else ""
        steer = plan_hint(engine)
        if not direction and not hint:
            # a submission (rarer) is offered before a pin when both are open; one already on comes first too
            hint = submission_urge(engine) or tactic_hint(engine, payoff_only=True) or pin_urge(engine) \
                or tactic_hint(engine)
        rng_hint = range_hint(engine) if not direction else ""
        bite = throat_hint(engine) if not direction else ""
        if bite:
            rng_hint = (rng_hint + "\n" + bite).strip()
        move_her = reposition_hint(engine) if not direction else ""
        if move_her:
            rng_hint = (rng_hint + "\n" + move_her).strip()
        low = low_health_hint(engine)
        if low:
            rng_hint = (rng_hint + "\n" + low).strip()
        big = coil_size_hint(engine)
        if big:
            rng_hint = (rng_hint + "\n" + big).strip()
        for extra in ((grudge_hint(engine), drag_to_pin_hint(engine), flight_hint(engine)) if not direction else ()):
            if extra:
                rng_hint = (rng_hint + "\n" + extra).strip()
        fresh = variety_hint(engine) if not direction else ""
        engine.weak_aim = set()    # last beat's weak-spot aim never carries over (the hint sets it again if it runs)
        weak = weak_spot_hint(engine) if not direction and not fresh else ""
        if weak:
            rng_hint = (rng_hint + "\n" + weak).strip()
        if fresh:
            rng_hint = (rng_hint + "\n" + fresh).strip()
        face = face_hint(engine) if not direction and not fresh and not weak else ""
        if face:
            rng_hint = (rng_hint + "\n" + face).strip()
        plan_pull = game_plan_hint(engine) if not direction else ""
        if plan_pull:
            rng_hint = (rng_hint + "\n" + plan_pull).strip()
        styled = style_hint(engine) if not direction else ""
        if styled:
            rng_hint = (rng_hint + "\n" + styled).strip()
        if not direction and "PIN " not in hint:
            m = re.search(r"\b(" + "|".join(re.escape(f.name) for f in engine.active()) + r")\b", hint or "")
            dcfg = engine.rules.get("director", {})
            who = m.group(1) if m else None
            if dominate_turn(engine) is False:
                who = engine.plan.get("winner")     # (/plan dominate: the big moment is hers this beat)
            held = big_moment_hint(engine, prefer=who)
            if held:
                rng_hint = (rng_hint + "\n" + held).strip()
        if not direction and engine.submission_match() and engine.sub_knockouts():
            # (since build 282, finish.submission.allow_knockouts) anything goes
            rng_hint = (rng_hint + "\nANYTHING GOES: a KNOCKOUT blow, a PIN held to its end" if not engine.no_pins() else
                        rng_hint + "\nANYTHING GOES: a KNOCKOUT blow") + (
                ", or a TAP-OUT (or pass-out) in a submission all end this fight. Mix them as the fight goes: blows "
                "to wear her down and maybe knock her out, and holds, submissions and coils when there is an opening.")
        elif not direction and engine.submission_match():
            # a submission match: only a tap-out or a pass-out ends it, so the fight has to come to holds
            rng_hint = (rng_hint + "\nSUBMISSION MATCH: no blow ends this fight, only a TAP-OUT or a PASS-OUT. Blows "
                        "only soften her up for the hold. Work toward grips: take the submission openings, and put on "
                        "submissions, locks on a limb or the body and coils, and keep them on and tighten them: the "
                        "longer one stays on and the more the gripped part hurts, the likelier she is to tap. A CHOKE "
                        "(a grip on the neck or throat) is the RARE finish, now and then, not the usual one: most "
                        "matches are won by an arm, a leg, a tail, the back or the body cranked until she taps. "
                        + ("A JAW HOLD (a bite clamped on and held) is rare too: most grips are paws, legs, tails, "
                           "coils and her weight. " if engine.hold_mix() else "") +
                        "Be inventive with them: these are Pokemon, so a hold can use tails, jaws, coils, a held stream "
                        "or the scenery (a knee levered back over a root, an arm wrenched round a trunk, her face ground "
                        "into the dirt, pressed against a tree), and an improvised hold_start with any limb is as good "
                        "as a named one. Never the same hold twice running.").strip()
            if engine.choke_tried():
                rng_hint += ("\nA CHOKE HAS ALREADY BEEN TRIED in this match: the holds from here on go on a limb, the "
                             "back or the body, not the neck.")
            tally = taps_hint(engine)
            if tally:
                rng_hint += "\n" + tally
            done_ = sorted(engine.subs_used().items(), key=lambda x: -x[1])
            if done_:
                rng_hint += ("\nHOLDS USED SO FAR (a nudge, not a rule: something new reads better than a repeat): "
                             + ", ".join(f"{n} ({k}x)" for n, k in done_) + ".")
            for f in engine.active():
                foe = next((x for x in engine.active() if x.name != f.name), None)
                if not foe or tally:
                    continue      # (with a tap count, the TAP COUNT lines name the part to work)
                limbs = [p for p in foe.parts.values() if body_region(p.name) in ("hind_up", "hind_low", "fore_up",
                                                                                 "fore_low", "neck")]
                worst = max(limbs, key=lambda p: p.damage, default=None)
                if not worst or worst.damage < 30:
                    continue
                grips = []
                if foe.name in engine.downed:
                    grips = [n for n, sh in engine.submission_shapes(f.name, foe.name).items()
                             if any(c[0] == worst.name for c in sh["contacts"])]
                rng_hint += (f"\nWORK THE HURT PART: {poss_word(foe.name)} {worst.name.lower()} is her worst "
                             f"({'badly hurt' if worst.damage >= 90 else 'hurting'}). {f.name} should keep punishing it: "
                             f"strikes and stomps aimed at it, and a hold that wrenches it"
                             + (f" ({', '.join(grips)} grips it as she lies now)" if grips else
                                " (a choke, if it is her neck)" if body_region(worst.name) == "neck" else "")
                             + ", kept on until she gives.")
        worn_ = worn_attacks_hint(engine) if not direction else ""
        if worn_:
            rng_hint = (rng_hint + "\n" + worn_).strip()
        unused = move_variety_hint(engine, skip=[n for n, o in players.items() if o]) if not direction else ""
        if unused:
            rng_hint = (rng_hint + "\n" + unused).strip()
        if rng_hint:
            hint = (hint + "\n" + rng_hint).strip()
        if urged:
            hint = (urged + "\n" + hint).strip()     # the author's /encourage comes first
        if players:
            # an idea for what a PLAYED fighter should do is the player's to have: keep only the ones for the
            # fighters the director runs (and the ones for a played fighter the player handed to the director)
            mine = [n for n, o in players.items() if o]
            hint = "\n".join(l for l in (hint or "").split("\n") if not any(re.search(
                r"\b" + re.escape(n) + r"\b(?: could| should| can| has an? (?:opening|chance)| keeps| takes| goes| strings| "
                r"seizes| charges| is (?:pointed|told))", l) or re.match(r"[A-Z ]+:?\s*" + re.escape(n) + r"\b", l)
                for n in mine))
        names = [f.name for f in engine.active()]
        engine.nudges = []
        for line in (hint or "").split("\n"):
            m = re.match(r"([A-Z][A-Z ]{3,}[A-Z])", line)
            if m:
                label = m.group(1).lower()
                if label.startswith("big moment"):
                    label = ("big moment: a charge into the scenery" if "CHARGES" in line else
                             "big moment: a grapple" if "TAKES HOLD" in line else
                             "big moment: a chain of attacks" if "STRINGS" in line else
                             "big moment: a throw or a slam" if "SEIZES" in line else "big moment: a held stream")
                    if "OVERDUE" in line:
                        label += " (overdue)"
                elif label.startswith("the author wants"):
                    m2 = re.match(r"THE AUTHOR WANTS \(([^)]*)\): ([^:]+): ([^.;(]+)", line)
                    label = (f"your /encourage: {m2.group(3).split(':')[0].strip().lower()} ({m2.group(2).strip()}, {m2.group(1)})" if m2
                             else "your /encourage")
                    engine.nudges.append(label)
                    continue
                who = [n for n in sorted(names, key=lambda n: line.find(n) if n in line else 10 ** 6) if n in line][:2]
                if label.startswith(("pin opportunity", "pin setup", "reposition idea", "submission opening")):
                    who = who[::-1]   # those lines name the fighter to be pinned first: show "pinner on pinned"
                engine.nudges.append(label + (f" ({' on '.join(who)})" if who else ""))
        user = (f"SCENE:\n{scene_block(engine, scene)}\n\n"
                f"CURRENT CONDITIONS:\n{engine.director_view()}\n\n"
                + story_line(engine) +
                f"RECENT ATTACKS (most recent last; vary from these):\n{recent}\n\n"
                f"STORY SO FAR (end of the most recent beat):\n"
                f"{('...' + story_so_far[-1500:]) if len(story_so_far or '') > 1500 else (story_so_far or '(the fight is just starting)')}\n\n"
                + (f"{steer}\n\n" if steer else "")
                + (f"{hint}\n\n" if hint else "")
                + (play_block(engine, players) + "\n\n" if players else "")
                + f"USER DIRECTION FOR THIS BEAT (follow it exactly): {direction or '(none — your call)'}\n\n"
                "Return the next beat as JSON.")
        story = userprompt.story_prompt(engine.rules)
        system = director_prompt(engine) + (
            "\n\nTHE AUTHOR'S INSTRUCTIONS (follow these for pacing, pins, and what can happen):\n" + story
            if story else "")
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        last_err, last_actions = None, None
        bump = 0.0
        for _ in range(self.retries):
            raw = llm.chat(self.model, messages, host=self.host, temperature=min(1.2, self.temperature + bump),
                           fmt=schema(engine), num_predict=1500,
                           num_ctx=engine.rules.get("narration", {}).get("context_window", 8192))
            try:
                try:
                    beat = json.loads(raw)
                except json.JSONDecodeError as je:
                    beat = repair_json(raw)
                    if beat is None:
                        # cut off mid-reply (often a run of blank output): ask again from scratch, a little warmer,
                        # without showing it the broken reply (that only primes the same failure)
                        last_err, bump = je, bump + 0.15
                        continue
                actions = beat.get("actions") if isinstance(beat, dict) and "actions" in beat else [beat]
                if direction and re.search(r"\b(sustain\w*|held (?:stream|beam|blast|attack)|keeps? (?:it|the \w+) (?:on|going))\b",
                                           direction, re.I):
                    # you asked for a SUSTAINED attack: a stream or beam the director chose is held, not fired once
                    for b in actions if isinstance(actions, list) else []:
                        if not (isinstance(b, dict) and b.get("action") in ("strike", "combo")) or int(b.get("sustain") or 0):
                            continue
                        try:
                            mv = engine.find_move(b.get("attacker"), b.get("move"))
                        except (ValueError, KeyError, AttributeError):
                            mv = None
                        if mv and mv.get("sustainable"):
                            b["sustain"] = 3
                if players:
                    actions = apply_players(engine, actions, players)
                try:
                    results, started = resolve_many(engine, actions)
                except Exception:
                    engine._force_dev_used = None       # (refused and undone: the retry may use it)
                    raise
                engine._force_dev, engine._force_dev_used = False, None   # (one beat only, used or not)
                pos = " ".join(str(beat.get("positions", "") if isinstance(beat, dict) else "").split())
                if len(pos) >= 15 and pos.lower().strip(". ") not in ("same", "unchanged", "no change", "as before"):
                    engine.set_positions(pos[:500])  # "same" or a blank keeps the previous positions
                return actions, results, started
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                last_err = e
                if "too worn out for" in str(e) and isinstance(actions, list):
                    last_actions = actions
                messages += [{"role": "assistant", "content": raw},
                             {"role": "user", "content": f"That beat is invalid: {e}. Return a corrected beat."}]
        if direction or any(v and v != "WAIT" for v in players.values()):
            # the user asked for something specific: don't silently replace it with a pause
            if not direction:
                raise ValueError(f"the director couldn't turn your move into a valid beat ({last_err}). Try wording "
                                 f"it differently, or use a /command for direct control")
            raise ValueError(f"the director couldn't turn that direction into a valid beat ({last_err}). "
                             f"Try wording it differently, or use a /command")
        if last_actions and "too worn out for" in str(last_err):
            # it kept choosing a move she can't afford: keep its beat, with the nearest move she can (the same kind
            # of attack if she has one, else her strongest), rather than stall the story with a pause
            try:
                swapped = _afford(engine, last_actions)
                if swapped:
                    results, started = resolve_many(engine, swapped)
                    print(f"[director kept choosing a move she couldn't afford ({last_err}); "
                          f"using {', '.join(str(b.get('move')) for b in swapped if isinstance(b, dict) and b.get('move'))}]")
                    return swapped, results, started
            except (ValueError, KeyError, TypeError) as e:
                last_err = e
        # Don't stall the story: fall back to a quiet beat (holds still tick) and say why.
        print(f"[director made {self.retries} invalid choices ({last_err}); continuing with a pause beat]")
        fallback = {"action": "breather", "attacker": engine.active()[0].name,
                    "flavor": "the fighters reset, circling and catching their breath", "intent": "reset"}
        results, started = resolve_many(engine, [fallback])
        return [fallback], results, started


def _afford(engine, actions):
    """The director's beat with each move its attacker can't afford swapped for one she can: the same kind of attack
    (blocks.kind_of) if she has one, else one that reaches as far, else her strongest. None when nothing needed (or could take) a swap."""
    out, changed = [], False
    for b in actions:
        if not isinstance(b, dict) or b.get("action") not in ("strike", "combo") or not b.get("attacker"):
            out.append(b)
            continue
        try:
            f = engine.get(b["attacker"])
            mv = engine.find_move(f.name, b.get("move"))
        except (ValueError, KeyError, AttributeError):
            out.append(b)
            continue
        if not mv or engine.energy_cost(mv) <= f.energy:
            out.append(b)
            continue
        can = [m for m in f.moves if engine.energy_cost(m) <= f.energy and f.move_uses.get(m["name"], 1) > 0
               and m.get("target") not in ("self",) and m.get("power")]
        if not can:
            return None
        kind = kind_of(mv["name"], mv.get("about", ""))
        same = ([m for m in can if kind & kind_of(m["name"], m.get("about", ""))]
                or [m for m in can if engine.is_ranged(m) == engine.is_ranged(mv)])   # (a flyer is out of reach of the rest)
        pick = max(same or can, key=lambda m: float(m.get("power") or 0))
        nb = {k: v for k, v in b.items() if k not in ("flavor", "sustain", "with")
              and not (k == "charge_into" and "charge" not in kind_of(pick["name"], pick.get("about", "")))}
        nb["move"] = pick["name"]
        out.append(nb)
        changed = True
    return out if changed else None


def repair_json(raw):
    """A reply cut off before its end (an unterminated string, unclosed brackets): close what is open and parse it.
    None if it still can't be read."""
    t = str(raw or "").rstrip()
    if not t.startswith(("{", "[")):
        return None
    stack, in_str, esc = [], False, False
    for ch in t:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    fixed = t + ('"' if in_str else "")
    fixed = re.sub(r'(?<=[{,])\s*"[^"]*"\s*:?\s*$', "", fixed)    # a key left hanging with no value
    fixed = re.sub(r",\s*$", "", fixed)
    fixed += "".join(reversed(stack))
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None


def move_variety_hint(engine, skip=()):
    """Now and then (director.move_variety, 0 = off): name moves a fighter hasn't used yet this fight, so she doesn't
    lean on her strongest two or three. Hold-only moves (used inside pins and holds) aren't named."""
    v = float(engine.rules.get("director", {}).get("move_variety", 0.35) or 0)
    if v <= 0 or engine.pins or engine.rng.random() >= v:
        return ""
    used = {m for _, m in engine.move_log}
    out = []
    for f in engine.active():
        if f.name in skip or f.name in engine.downed:
            continue
        fresh = [m["name"] for m in f.moves if m["name"] not in used and m.get("target") != "hold"
                 and f.move_uses.get(m["name"], 1) > 0 and engine.energy_cost(m) <= f.energy]
        if fresh:
            engine.rng.shuffle(fresh)
            out.append(f"{f.name} hasn't used {', '.join(fresh[:4])} lately")
    if not out:
        return ""
    return ("MOVES NOT USED LATELY (an idea, not an order): " + "; ".join(out) + ". A fighter who uses all she has, "
            "status and set-up moves too, is more interesting than one who leans on her strongest two or three.")


def worn_attacks_hint(engine):
    """director.worn_after (0 = off): attacks a fighter has thrown that many times lately (the last twenty attacks)
    are not new any more:
    named, with how many times, so the director reaches for something she hasn't done, an improvised technique of her
    own body or a use of the scenery. Every beat once one is worn, not by chance."""
    k = int(engine.rules.get("director", {}).get("worn_after", 4) or 0)
    if k <= 0:
        return ""
    counts = {}
    for who, m in engine.move_log:
        counts.setdefault(who, {}).setdefault(m, 0)
        counts[who][m] += 1
    out = []
    for f in engine.active():
        worn = sorted(((m, n) for m, n in (counts.get(f.name) or {}).items() if n >= k), key=lambda x: -x[1])
        if worn:
            out.append(f"{f.name}: " + ", ".join(f"{m} ({n}x)" for m, n in worn))
    if not out:
        return ""
    return ("ATTACKS WORN OUT (used a lot already this fight, not new any more: reach for something else): "
            + "; ".join(out) + ". Be inventive: these are Pokemon, so an improvised technique of her own body (tails, "
            "jaws, fins, a coil, a held stream) or a use of the scenery (driving her into a tree or a rock, grinding her "
            "into the ground, the water) is better than the same move again.")


def play_block(engine, players):
    """The part of the director's prompt that says who the user plays and what each played fighter does."""
    run = [f.name for f in engine.active() if f.name not in players]
    lines = ["PLAYERS: the user is PLAYING as " + ", ".join(players) + ". A played fighter does ONLY what her player "
             "ordered: never invent, add or change an action for her, and never make her choices for her. Any hint "
             "above about what a played fighter should do does not apply to her (it is only for the fighters you "
             "run). Put the played fighters' actions FIRST, in this order:"]
    for name, order in players.items():
        if order == "WAIT":
            lines.append(f"- {name} (player): holds back this beat. NO action for her at all.")
        elif order:
            lines.append(f"- {name} (player) orders: \"{order}\". Turn exactly this into her action(s), using her "
                         f"moves and the rules ('I', 'me', 'my' in the order mean {name}). If the order says how it "
                         f"turns out, still only choose the action: the dice decide what happens.")
        else:
            lines.append(f"- {name} (player): the player lets you choose her action this beat, as you normally would.")
    cfg = engine.rules.get("play", {})
    if run:
        lines.append("Fighters you run: " + ", ".join(run) + ". After the played fighters' actions, "
                     + ("give each of them who can act ONE action that answers what just happened (a counter, a "
                        "strike, a grab, a struggle if pinned), or more only for a held moment or a combo as you "
                        "normally would."
                        if cfg.get("ai_answers", True) else
                        "you may add an action for them if the moment calls for it."))
    else:
        lines.append("Every fighter is played: add NO actions beyond the ones ordered (and the ones you were told to "
                     "choose).")
    return "\n".join(lines)


# (since build 278) a played fighter's order that is doing nothing, that is a grip, or that is fighting back
# (since build 278; much fuller since build 292) the words a player's order is read by: holding back, fighting
# (any attack, struggle or getting away), and gripping
PASSIVE_ORDER = re.compile(r"(?i)\b(?:(?:does|do|doing|did) nothing|(?:doesn't|does not|don't|do not|won't|will not) "
                           r"(?:do|fight|struggle|move|resist|react|respond)\w*|nothing|(?:can't|cannot|can not) "
                           r"(?:do|move|fight)|(?:gets?|is|am|being) (?:constricted|held|squeezed|crushed|coiled|wrapped|"
                           r"pinned|choked|grabbed|gripped|bound)|lets? (?:her|it|them|herself) (?:happen|be|squeeze|"
                           r"hold|coil|crush|win)|takes? it|stays? (?:still|limp|put|down|quiet)|holds? still|gives? in|"
                           r"goes? limp|(?:lies|lie|lay|lays) still|relax\w*|rests?|resting|waits?|waiting|endur\w*|"
                           r"accepts? it|(?:catch\w*|gets?) (?:her|my) breath|just breathes?|watch\w*|stand\w* there|"
                           r"(?:sits?|sat) there|freez\w* up|playing dead|plays? dead)\b")
ACTIVE_ORDER = re.compile(r"(?i)\b(?:struggl\w*|break\w*|escap\w*|wrench\w*|fights? (?:back|it|her)|fighting|bit(?:e|es|ing)?|"
                          r"chomp\w*|gnaw\w*|snap\w* at|nip\w*|attack\w*|strik\w*|struck|hits?|hitting|smack\w*|slap\w*|"
                          r"swat\w*|kick\w*|claw\w*|scratch\w*|rak(?:e|es|ed|ing)|slash\w*|swip\w*|twist\w* (?:free|away|out|loose)|"
                          r"pr(?:y|ies|ied) |head[- ]?butt\w*|butts?|punch\w*|jabs?|jabb\w*|uppercut\w*|slam\w*|smash\w*|"
                          r"bash\w*|batter\w*|pound\w*|hammer\w*|pummel\w*|whip\w*|lash\w* (?:at|out)|rams?|ramm\w*|"
                          r"charg\w*|tackl\w*|chop\w*|stomp\w*|stamp\w*|knee\w* (?:her|ripples|\w+ in)|elbow\w*|shov\w*|"
                          r"push\w* (?:her|off|away|back)|throw\w*|threw|toss\w*|hurl\w*|flip\w* (?:her|over)|squirm\w*|"
                          r"wriggl\w*|thrash\w*|buck\w*|writh\w*|flail\w*|kick\w* free|spit\w*|spray\w*|shoot\w*|"
                          r"blast\w*|fir(?:e|es|ing) (?:at|a|her)|beam\w*|breath(?:es)? (?:fire|ice)|gor(?:e|es|ing)|peck\w*|"
                          r"stings?|stinging|tear\w* (?:at|into|free)|rip\w* (?:at|into|free)|cut\w* (?:at|into)|dodg\w*|"
                          r"duck\w*|block\w*|parr\w*|counter\w*|retreat\w*|back\w* away|jump\w*|leap\w*|dives?|diving|"
                          r"flee\w*|runs? away|rolls? (?:away|free|out)|break\w* free|pulls? (?:free|away|loose)|"
                          r"slips? (?:free|out|away|loose)|tries to get (?:free|out|away|up)|gets? up|stands? up)\b")
GRIP_ORDER = re.compile(r"(?i)\b(?:coil\w*|constrict\w*|wrap\w*|squeez\w*|crush\w* (?:her|ripples|\w+) in|bind\w*|"
                        r"grab\w*|grip\w*|holds? (?:her|onto|on to|tight)|wind\w* (?:round|around)|wound (?:round|around)|"
                        r"tighten\w*|clamp\w*|lock\w* (?:on|her|onto|round|around)|chok(?:e|es|ing)|strangl\w*|smother\w*|"
                        r"cinch\w*|latch\w*|(?:bear )?hug\w*|envelop\w*|encircl\w*|entwin\w*|ensnar\w*|entangl\w*|"
                        r"seiz\w*|snatch\w*|clutch\w*|grasp\w*|embrac\w*|engulf\w*|loop\w* (?:round|around|over)|"
                        r"press\w* (?:harder|tighter)|crank\w*|wring\w*)\b")


def apply_players(engine, actions, players):
    """Keep the director to the players' orders: no actions for a fighter who holds back, at least one for every
    fighter given an order, and the played fighters' actions first, in the order they were asked."""
    if not isinstance(actions, list):
        actions = [actions]
    def who(b):
        return str(b.get("attacker") or "") if isinstance(b, dict) else ""
    names = {n.lower(): n for n in players}
    waiting = {n.lower() for n, o in players.items() if o == "WAIT"}
    kept = [b for b in actions if who(b).lower() not in waiting]
    for n, o in players.items():
        if o and o != "WAIT" and not any(who(b).lower() == n.lower() for b in kept):
            raise ValueError(f"{n}'s player ordered \"{o}\", but there is no action for {n} (her action must have "
                             f"\"attacker\": \"{n}\")")
    # (since build 278) the order's own kind of action wins over the director's: a player who says her fighter does
    # nothing (or lets herself be held) gets a beat of doing nothing, not a struggle that breaks the grip; one who
    # orders a coil, a wrap or a squeeze gets a grip, not a tail strike
    passive = set()
    engine._passive = (engine.turn, passive)
    for n, o in players.items():
        if not o or o == "WAIT":
            continue
        mine = [b for b in kept if who(b).lower() == n.lower()]
        if PASSIVE_ORDER.search(o) and not ACTIVE_ORDER.search(o):
            passive.add(engine.get(n).name)
            kept = [b for b in kept if b not in mine] + [{"action": "breather", "attacker": engine.get(n).name,
                                                          "flavor": "does nothing to fight it", "_passive": True}]
        elif GRIP_ORDER.search(o) and mine and not any(b.get("action") in ("hold_start", "hold_adjust", "pin",
                                                                            "submission", "grapple") for b in mine):
            foe = next((f for f in engine.active() if f.team != engine.get(n).team), None)
            if foe is None:
                continue
            me_ = engine.get(n).name
            moves_ = [m["name"] for m in engine.get(n).moves]
            active_ = bool(ACTIVE_ORDER.search(o) or any(re.search(r"\b" + re.escape(m) + r"\b", o, re.I) for m in moves_))
            if any(h.attacker == me_ and h.defender == foe.name for h in engine.holds.values()):
                # (since build 292) "squeeze harder" with her grip already on: it TIGHTENS what she has, it doesn't
                # put a new grip on whatever part the order names ("I headbutt Ripples' head four times and then
                # squeeze even tighter" became a grip on her head, and no headbutt was thrown)
                tight = {"action": "hold_adjust", "attacker": me_, "defender": foe.name, "severity": "crushing",
                         "ramp": "tightening", "flavor": "the coils drawn tighter" if engine.body_plan(engine.get(n))
                         == "serpent" else "the grip drawn tighter"}
                kept = kept + [tight] if active_ else [tight if b is mine[0] else b for b in kept]
                continue
            # (the part to grip is named AFTER the grip word: "headbutts her head and then coils round her chest")
            gm = GRIP_ORDER.search(o)
            tail_ = o[gm.start():] if gm and active_ else o
            named = [p for p in foe.parts if re.search(r"\b" + re.escape(p.lower()) + r"\b", tail_.lower())]
            if not named and re.search(r"\b(?:midsection|middle|body|waist|torso|stomach|belly)\b", tail_, re.I):
                named = [p for p in foe.parts if body_region(p) in ("belly", "chest")][:2]
            if not named:
                continue
            b0 = mine[0]
            grip = {"action": "hold_start", "attacker": engine.get(n).name, "defender": foe.name,
                    "hits": [{"part": p} for p in named], "flavor": str(b0.get("flavor") or o)}
            if active_:
                grip["flavor"] = o
                kept = kept + [grip]          # an attack AND a grip ordered: the attack, then the grip
            else:
                kept = [grip if b is b0 else b for b in kept]
    order = [n.lower() for n in players]
    kept.sort(key=lambda b: order.index(who(b).lower()) if who(b).lower() in names else len(order))
    if not kept:
        kept = [{"action": "breather", "attacker": next(iter(players)), "flavor": "nobody presses; they watch each "
                 "other", "intent": "reset"}]
    return kept


def initiative_hint(engine, roll=None):
    """When one side has made several attacks in a row while an opponent is still strong, SOMETIMES tell the
    director to hand the opponent the initiative. Streaks are allowed; the longer one runs, the likelier the shift
    (rules.json director: initiative_after, initiative_chance, initiative_step, initiative_max)."""
    cfg = engine.rules.get("director", {})
    n = int(cfg.get("initiative_after", 3) or 0)
    if n <= 0 or len(engine.momentum) < n:
        return ""
    who = [m.split(">")[0] for m in engine.momentum]
    streak = 0
    for w in reversed(who):
        if w != who[-1]:
            break
        streak += 1
    if streak < n:
        return ""
    last = [m.split(">") + [""] for m in engine.momentum[-streak:]]
    hog = engine.get(last[0][0])
    chance = min(float(cfg.get("initiative_max", 0.95)),
                 float(cfg.get("initiative_chance", 0.4)) + float(cfg.get("initiative_step", 0.2)) * (streak - n))
    if engine.plan.get("shape") == "dominate" and engine.plan.get("winner") == hog.name:
        chance *= float(cfg.get("initiative_dominate_factor", 0.3))  # the author asked for this fighter to dominate
    if roll is None:
        roll = engine.rng.random()
        engine.note_roll(f"director nudge: the initiative shifts away from {hog.name}", chance, roll,
                         "it shifts" if roll < chance else "none")
    if roll >= chance:
        return ""
    floor = float(cfg.get("initiative_min_strength", 35))
    rivals = [f for f in engine.active() if f.team != hog.team and engine.strength(f) >= floor]
    if not rivals:
        return ""
    counts, total = engine.momentum_counts()
    victims = [v for x in reversed(last) for v in x[1].split(",") if v]
    # the fighter who's been on the receiving end gets the comeback; otherwise the strongest opponent
    f = next((r for v in victims for r in rivals if r.name == v), None) or max(rivals, key=engine.strength)
    pinned = any(p["defender"] == f.name for p in engine.pins.values())
    how = ("a struggle or a strike at the pinner with a free limb" if pinned else
           "a counterattack, a reversal, a dodge into a strike of her own, or a throw")
    return (f"INITIATIVE (important): {hog.name} has made the last {streak} attacks; {f.name} has made "
            f"{counts.get(f.name, 0)} of the last {total} and is still at {engine.strength(f):.0f}% of full strength. "
            f"This beat, the momentum shifts: {f.name} takes the initiative: {how}.")


FANG_WORDS = ("bite", "crunch", "fang", "jaw lock", "hyper fang", "super fang")
EASE_WORDS = re.compile(r"\b(eas\w+|loosen\w*|relax\w*|slack\w*|lets? up|letting up|gentl\w+|soften\w*|lighten\w*)\b", re.I)


def _grip_tools(engine, f):
    """What this fighter can grip, press and choke with, by the shape of her body. A limb at 150%+ isn't used."""
    plan = engine.body_plan(f)

    def works(*keys):
        ps = [p for p in f.parts.values() if any(k in p.name.lower() for k in keys)]
        return not ps or any(p.damage < 150 for p in ps)
    tools = {"jaws": "her jaws" if works("jaw") else "", "weight": "her full weight"}
    if plan == "avian":
        tools.update(fore="a wing" if works("wing") else "", fores="her talons" if works("talon") else "",
                     hind="her talons" if works("talon") else "", hook="a talon hooked round the leg" if works("talon") else "",
                     jaws="her beak" if works("beak") else "")
    elif plan == "serpent":
        tools.update(coil="her coils", fore="a loop of her body", fores="her coils", hind="her tail", hook="her tail hauling the leg up",
                     weight="the weight of her body")
    elif plan == "biped":
        tools.update(fore="her forearm" if works("arm", "forearm") else "", fores="both paws" if works("paw") else "",
                     hind="her knees" if works("knee") else "", hook="her arm hauling the leg up" if works("arm") else "")
        tails = [p for p in f.parts.values() if "tail" in p.name.lower() and "base" not in p.name.lower()]
        if tails and any(p.damage < 150 for p in tails):
            tools["coil"] = "her twin tails" if any("twin" in p.name.lower() for p in tails) else "her tail"
    else:
        tools.update(fore="her forepaw" if works("forepaw", "foreleg") else "",
                     fores="both forepaws" if works("forepaw", "foreleg") else "",
                     hind="her hind paws" if works("hind paw", "hock") else "",
                     hook="her foreleg hauling the leg up" if works("foreleg") else "")
    return {k: v for k, v in tools.items() if v}


def _spots(target):
    """The defender's parts by what a grip can do with them."""
    from engine import body_region
    names = list(target.parts)

    def pick(test):
        return [n for n in names if test(n.lower(), body_region(n))]
    return {"neck": pick(lambda n, r: "neck" in n or "throat" in n),
            "front": pick(lambda n, r: r in ("chest", "belly") and "ruff" not in n and "flank" not in n and "rib" not in n),
            "arm": pick(lambda n, r: r in ("fore_up", "fore_low") and "fin" not in n),
            "upper_arm": pick(lambda n, r: r == "fore_up"),
            "shoulder": pick(lambda n, r: r == "shoulder"),
            "thigh": pick(lambda n, r: r == "hind_up"),
            "leg": pick(lambda n, r: r in ("hind_up", "hind_low")),
            "tail": pick(lambda n, r: r == "tail" and "base" not in n and "fan" not in n)}


def fuller_pin(engine, pinner, target, look, contacts, at_least=0):
    """Fill a pin out with every limb the pinner still has free (pin.contacts: how many points of contact to aim
    for, weighted): jaws on the neck, her chest or her weight on the front (or the back, face-down), her paws gripping
    the other's forelimbs with the claws in, her feet or hind paws on both flanks, her tails or tail across the legs.
    Nothing is used twice and no part is pressed twice. Returns (look, contacts)."""
    from engine import body_region
    cfg = (engine.rules.get("pin") or {}).get("contacts") or {}
    weights = {int(k): float(v) for k, v in (cfg.get("weights") or {"2": 15, "3": 30, "4": 30, "5": 15, "6": 10}).items()
               if not str(k).startswith("_")}
    if not cfg.get("enabled", True) or not weights:
        return look, contacts
    want = max(engine.rng.choices(list(weights), list(weights.values()))[0], int(at_least or 0))
    if len(contacts) >= want:
        return look, contacts
    plan = engine.body_plan(pinner)
    t = _grip_tools(engine, pinner)
    used_w = " ".join(str(w).lower() for _, w in contacts)
    used_p = {p for p, _ in contacts}
    names = list(target.parts)
    regions = {n: body_region(n) for n in names}
    # which way she lies: what is already pressed says so, or how she lies on the ground now, or face-up
    if any(regions.get(p) in ("back_up", "back_low") for p in used_p):
        down = True
    elif any(regions.get(p) in ("chest", "belly") for p in used_p):
        down = False
    else:
        down = engine.facing_of(target.name) == "face-down" if target.name in engine.downed else False
    def free(ns):
        return [n for n in ns if n not in used_p]
    feet = {"biped": "her feet", "quadruped": "her hind paws", "avian": "her talons", "serpent": ""}.get(plan, "")
    fore_hold = {"biped": "her paws, gripping it tight, claws digging in", "quadruped": "her forepaw, claws digging in",
                 "avian": "her talons, gripping it"}.get(plan, "")
    options = [
        ("jaw", t.get("jaws"), [] if any(regions.get(p) == "neck" for p in used_p) else
         free([n for n in names if regions[n] == "neck" and not (down and "throat" in n.lower())]),
         1, lambda w: f"{w}, {'the hooked tip' if plan == 'avian' or 'beak' in str(w) else 'teeth'} pressed hard into it"),
        ("weight|chest", t.get("weight"),
         free([n for n in names if regions[n] in (("back_up", "back_low") if down else ("chest",))]), 1,
         lambda w: ("her full weight, bearing down" if down else
                    ("her chest, pressed hard against it" if plan in ("biped", "quadruped") else w))),
        ("paw|claw|talon", fore_hold,
         free([n for n in names if regions[n] == "fore_low" and any(k in n.lower() for k in ("paw", "hand", "forearm"))
               and "fin" not in n.lower()] or [n for n in names if regions[n] in ("fore_low", "fore_up")]), 2,
         lambda w: w),
        ("feet|hind paw|hind leg|knee|talon|legs, locked", feet,
         free([n for n in names if any(k in n.lower() for k in ("flank", "rib", "hip"))]), 2,
         lambda w: f"{w}, pressed into it"),
        ("tail|coil", t.get("coil"), free([n for n in names if regions[n] in ("hind_up", "hind_low")]), 2,
         lambda w: f"{w}, across it"),
    ]
    extra = []
    for keys, tool, parts, n, how in options:
        if len(contacts) + len(extra) >= want:
            break
        if not tool or not parts or any(k in used_w for k in keys.split("|")):
            continue
        # two of a pair at once (both forepaws gripped, a foot on each flank)
        pick = parts[:2] if n == 2 and len(parts) >= 2 else parts[:1]
        if n == 2:
            lefts = [p for p in parts if "left" in p.lower()]
            rights = [p for p in parts if "right" in p.lower()]
            if lefts and rights:
                pick = [lefts[0], rights[0]]
        for p in pick[:max(1, want - len(contacts) - len(extra))]:
            extra.append((p, how(tool)))
            used_p.add(p)
    if not extra:
        return look, contacts
    look = look + "; and " + ", ".join(f"{w.split(',')[0]} on her {p}" for p, w in extra)
    return look, list(contacts) + extra


def pin_shapes(engine, pinner, target, skip=()):
    """Every way THIS pinner could pin THIS target that her body allows: {name: (what it looks like, contacts)}.
    Contacts are (target part, what the pinner presses or grips it with)."""
    t, sp, rng = _grip_tools(engine, pinner), _spots(target), engine.rng
    one = lambda key: rng.choice(sp[key]) if sp.get(key) else None
    out = {}
    neck, front, arm, thigh = one("neck"), one("front"), one("arm"), one("thigh")
    thighs = [n for n in sp["thigh"] if "thigh" in n.lower()]
    thigh = rng.choice(thighs) if thighs else thigh
    hips = [n for n in sp["thigh"] if "hip" in n.lower()][:2]
    if t.get("jaws") and neck and front:
        out["throat_bite"] = (f"{t['jaws'].replace('her ', '', 1)} clamped on her {neck} as the choke, her weight on her {front}"
                              + (f", {t['hind']} on her hips" if t.get("hind") and hips else ""),
                              [(neck, t["jaws"]), (front, t["weight"])] + [(h, t.get("hind", "")) for h in hips if t.get("hind")])
    if t.get("jaws") and arm and neck and t.get("fore"):
        out["trapped_arm"] = (f"{t['jaws'].replace('her ', '', 1)} clamped on her {arm}, pinning that limb to the ground, while {t['fore']} bars across her "
                              f"{neck} as the choke" + (f" and her weight settles on her {front}" if front else ""),
                              [(arm, t["jaws"]), (neck, t["fore"])] + ([(front, t["weight"])] if front else []))
    if t.get("coil") and neck:
        arms = sp["shoulder"][:2] or sp["upper_arm"][:2]
        out["tail_choke"] = (f"{t['coil']} looped round her {neck} as the choke"
                             + (f", {t['fores']} pinning her {' and '.join(arms)}" if arms and t.get("fores") else "")
                             + (f", her weight on her {front}" if front else ""),
                             [(neck, t["coil"] + ", looped round it")] + [(a, t["fores"]) for a in arms if t.get("fores")]
                             + ([(front, t["weight"])] if front else []))
    if t.get("coil") and front:
        # constriction as a pin: wound round her chest and arms, squeezing, bearing her down in the coils
        arms = sp["upper_arm"][:2] or sp["shoulder"][:2]
        out["coil_crush"] = (f"{t['coil']} wound round her {front}" + (f" and both her {' and '.join(arms)}" if arms else "")
                             + ", tightening, bearing her down inside the coils so every breath is squeezed shorter",
                             [(front, t["coil"] + ", wound round her")] + [(a, t["coil"] + ", wound round her") for a in arms])
    upper = one("upper_arm") or one("shoulder")
    if upper and t.get("fore") and front:
        out["twisted_arm"] = (f"her {upper} wrenched out straight and pinned under {t['fore']}, her weight across her {front}"
                              + (f", jaws on her {neck}" if t.get("jaws") and neck else ""),
                              [(upper, t["fore"] + ", the limb wrenched straight"), (front, t["weight"])]
                              + ([(neck, t["jaws"])] if t.get("jaws") and neck else []))
    legs = [n for n in sp["leg"] if "thigh" in n.lower() or "knee" in n.lower()][:2]
    if len(legs) == 2 and (t.get("coil") or t.get("hind")) and front:
        w = t.get("coil") or t["hind"]
        out["leg_tangle"] = (f"{w} trapping both her legs ({' and '.join(legs)}) so she can't kick or bridge, her weight on "
                             f"her {front}" + (f", {t['fore']} across her {neck}" if t.get("fore") and neck else ""),
                             [(l, w) for l in legs] + [(front, t["weight"])]
                             + ([(neck, t["fore"])] if t.get("fore") and neck else []))
    if thigh and t.get("hook") and front:
        out["lifted_leg"] = (f"one of her legs hooked and hauled up off the ground ({thigh}, {t['hook']}), folded back toward "
                             f"her own chest so her hips can't turn, with her weight on her {front}"
                             + (f" and {t['jaws'].replace('her ', '')} on her {neck}" if t.get("jaws") and neck else ""),
                             [(thigh, t["hook"]), (front, t["weight"])]
                             + ([(neck, t["jaws"])] if t.get("jaws") and neck else []))
    from engine import body_region
    backs = [n for n in target.parts if body_region(n) == "back_up"]
    plan = engine.body_plan(pinner)
    # a sleeper needs an arm that can lock round a neck: a four-legged fighter's foreleg can only press down
    if t.get("fore") and neck and backs and "sleeper" not in skip and plan in ("biped", "serpent"):
        back = rng.choice(backs)
        out["sleeper"] = (f"a sleeper hold from behind: {t['fore']} hooked under her chin and locked round her {neck}, "
                          f"squeezing the sides of it shut, her weight along her {back} so she can't turn",
                          [(neck, t["fore"] + ", locked round it from behind"), (back, t["weight"])])
    throat = next((n for n in sp["neck"] if "throat" in n.lower()), neck)
    tailp = [p for p in pinner.parts.values() if "tail" in p.name.lower() and "base" not in p.name.lower()
             and p.damage < 150]
    # standing on her throat: a foot or a paw planted on it, the weight on it, another on her chest
    if throat and front and plan in ("biped", "quadruped"):
        foot = ("her foot" if plan == "biped" else rng.choice(["a forepaw", "a hind paw"]))
        other = "her other foot" if plan == "biped" else ("her other forepaw" if "fore" in foot else "her forepaws")
        out["throat_stand"] = (f"standing over her with {foot} planted on her {throat}, her weight on it, {other} on "
                               f"her {front}",
                               [(throat, f"{foot}, standing on the throat"), (front, other)])
    # a knee driven across her neck, both hands pinning an arm
    if plan == "biped" and t.get("hind") and neck and arm:
        out["knee_on_neck"] = (f"her knee driven across her {neck}, her weight behind it, {t.get('fores', 'her paws')} "
                               f"pinning her {arm} out to the side",
                               [(neck, "her knee, driven across the neck"), (arm, t.get("fores", "her paws"))])
    # a cat's clutch: lying on her side behind her, forelegs hooked round the sides of her neck and hugging it in,
    # hind paws braced against her hips (a four-legged fighter can wrap that way only from her side or on top)
    if plan == "quadruped" and t.get("fore") and neck:
        hip = hips[0] if hips else thigh
        out["foreleg_clutch"] = (f"lying on her side behind her, both forelegs hooked round the sides of her {neck} and "
                                 f"hugging it in"
                                 + (f", {t['hind']} braced against her {hip}" if t.get("hind") and hip else ""),
                                 [(neck, "her forelegs, hooked round the sides of it, hugging it in")]
                                 + ([(hip, t["hind"])] if t.get("hind") and hip else []))
    # the flat of a tail barred across the throat (a tail that isn't wound round anything), forepaws on her chest
    if tailp and plan == "quadruped" and throat and front and not t.get("coil"):
        tname = tailp[0].name.lower()
        out["tail_bar"] = (f"the flat of her {tname} pressed across her {throat}, {t.get('fores', 'her forepaws')} on "
                           f"her {front}",
                           [(throat, f"the flat of her {tname}, pressed across the throat"),
                            (front, t.get("fores", "her forepaws"))])
    # a headlock pin: her arm locked round head and neck from the side, her weight across the chest
    if plan == "biped" and t.get("fore") and neck and front:
        out["headlock_pin"] = (f"her arm locked round her head and {neck} from the side, her weight across her {front}",
                               [(neck, "her arm, locked round it"), (front, t["weight"])])
    # a crucifix: both arms trapped (one under a knee or paw, one in her paws or jaws), her weight across the chest
    arms2 = sp["upper_arm"][:2] if len(sp["upper_arm"]) >= 2 else []
    if len(arms2) == 2 and front and (t.get("hind") or t.get("fore")) and (t.get("fores") or t.get("jaws")):
        limbs = "forelegs" if engine.body_plan(target) == "quadruped" else "arms"
        out["crucifix"] = (f"both her {limbs} trapped, her {arms2[0]} under {t.get('hind') or t['fore']} and her {arms2[1]} "
                           f"in {t.get('jaws') or t['fores']}, her weight across her {front}",
                           [(arms2[0], t.get("hind") or t["fore"]), (arms2[1], t.get("jaws") or t["fores"]),
                            (front, t["weight"])])
    # a body scissor: legs locked round her middle, squeezing the ribs, from her side
    ribs = [n for n in target.parts if "rib" in n.lower() or "flank" in n.lower()] or sp["front"]
    if plan in ("biped", "quadruped") and t.get("hind") and ribs:
        legs_w = "her legs" if plan == "biped" else "her hind legs"
        mid = rng.choice(ribs)
        out["body_scissor"] = (f"{legs_w} locked round her middle from the side, squeezing her {mid}"
                               + (f", jaws on her {neck}" if t.get("jaws") and neck else ""),
                               [(mid, f"{legs_w}, locked round her middle")] + ([(neck, t["jaws"])] if t.get("jaws") and neck else []))
    # throttled: hands closed round the sides of the neck (a body with hands to do it), knees on her chest
    if plan == "biped" and t.get("fores") and neck and front:
        out["throttle"] = (f"{t['fores']} closed round the sides of her {neck}, squeezing it shut, "
                           f"{t.get('hind') or t['weight']} on her {front}",
                           [(neck, t["fores"] + ", closed round the sides of it"), (front, t.get("hind") or t["weight"])])
    # a leg scissor: legs locked round her neck from the side, squeezing the sides of it shut. Any fighter whose
    # legs still work can do it (a four-legged fighter with her hind legs)
    scissor = {"biped": "her legs" if t.get("hind") else "", "quadruped": "her hind legs" if t.get("hind") else ""}.get(plan, "")
    if scissor and neck:
        arms = sp["upper_arm"][:1] or sp["shoulder"][:1]
        grab = t.get("fore") or t.get("jaws")
        out["leg_scissor"] = (f"{scissor} locked round her {neck} from the side, squeezing the sides of it shut"
                              + (f", {grab} trapping her {arms[0]}" if arms and grab else ""),
                              [(neck, scissor + ", locked round it")] + ([(arms[0], grab)] if arms and grab else []))
    # the dunk: held face-down in the shallows, her head pushed under and let up and pushed under again (a choke by
    # water; never drowning). Only where the arena has shallow water to do it in
    pools = [h.get("name") for h in ((getattr(engine, "scene_cfg", None) or {}).get("hazards") or [])
             if isinstance(h, dict) and re.search(r"pool|shallow|puddle|stream|creek|surf|marsh|spring",
                                                  " ".join([str(h.get("name", ""))] + list(h.get("words") or [])), re.I)
             and not re.search(r"\bdeep\b|plunge", str(h.get("name", "")), re.I)]
    from engine import body_region as _br
    backs2 = [n for n in target.parts if _br(n) in ("back_up", "back")]
    if pools and t.get("fore") and neck and backs2 and "dunk" not in skip:
        pool = rng.choice(pools)
        out["dunk"] = (f"{target.name} hauled to {pool} and held there FACE-DOWN in the shallow water, {t['fore']} on the "
                       f"back of her {neck} pushing her head under, letting her up for one gasp and pushing her under "
                       f"again, her weight across her {backs2[0]} (say so with \"pinned_against\": \"{pool}\")",
                       [(neck, t["fore"] + ", holding her head under the shallow water"), (backs2[0], t["weight"])])
    props = [p for p in ((getattr(engine, "scene_cfg", None) or {}).get("props") or []) if p and not engine.is_broken(p)]
    if props and t.get("fore") and neck and front and "wall_choke" not in skip:
        prop = rng.choice(props)
        out["wall_choke"] = (f"{target.name} driven back against {prop} and held there on the ground at the foot of it, "
                             f"her head and shoulders jammed against it so she has nowhere to push back to, "
                             f"{t['fore']} barred across her {neck} as the choke and her weight crushing her {front} "
                             f"(say so with \"pinned_against\": \"{prop}\")",
                             [(neck, t["fore"]), (front, t["weight"])])
    # a fighter already lying on her front has her throat, chest and belly against the ground, and one on her back
    # can't be held "from behind": only the shapes that fit the way she lies
    if target.name in engine.downed:
        fc = engine.facing_of(target.name)
        if fc == "face-down":
            # her throat is against the ground: a grip there takes the back of her neck instead
            nape = next((p for p in target.parts if p.lower() == "neck"), None)
            if nape:
                out = {k: (re.sub(r"\b[Tt]hroat\b", nape, look),
                           [(nape if p.lower() == "throat" else p, w) for p, w in contacts])
                       for k, (look, contacts) in out.items()}
            out = {k: v for k, v in out.items() if not any(
                re.search(r"\b(throat|chest|belly|stomach)\b", (p + " " + w).lower()) for p, w in v[1])
                and not re.search(r"face-up|on her back|on her chest|on her belly", v[0], re.I)} or out
        elif fc == "face-up":
            out = {k: v for k, v in out.items() if not re.search(r"from behind|face-down|on her front", v[0], re.I)} or out
    # most pins use far more of her than two points: whatever she has free goes on too (pin.contacts)
    return {k: fuller_pin(engine, pinner, target, look, contacts) for k, (look, contacts) in out.items()}


def _pin_against(engine, b, flavor):
    """The thing in the arena a pin is jammed against, if the beat says so and the arena has it standing: one of its
    props (not one that has broken), or water it has (a dunk in the shallows). Returns (name, is_water) or None."""
    asked = str(b.get("pinned_against") or "").strip().lower()
    if asked in ("none", "no", "n/a"):
        asked = ""
    m = re.search(r"\bagainst ((?:the |a |an )?(?:[\w-]+ ){0,4}[\w-]+)", str(flavor or "").lower())
    said = asked or (m.group(1) if m else "")
    if not said:
        return None
    prop = engine.scene_prop_for(said)
    if prop:
        return short_phrase(prop), False
    h = engine.hazard_for(said)
    if h and (h.get("cushion") or any(e.get("status") == "soaked" for e in h.get("effects") or [])):
        return h["name"], True
    return None


def pin_shape_hint(engine, pinner, target):
    """One way to build the pin, picked so pins don't all look alike (director.pin_shape_weights: how often each
    kind is suggested; 0 = never)."""
    cfg = engine.rules.get("director", {})
    weights = {"throat_bite": 3, "trapped_arm": 3, "tail_choke": 3, "twisted_arm": 2, "leg_tangle": 2, "lifted_leg": 1,
               "sleeper": 1, "wall_choke": 0.6, "throat_stand": 1.5, "knee_on_neck": 1.5, "foreleg_clutch": 1.5,
               "tail_bar": 1, "headlock_pin": 1.5, "crucifix": 1, "body_scissor": 1, "throttle": 1.5, "leg_scissor": 1.5}
    weights.update({k: v for k, v in (cfg.get("pin_shape_weights") or {}).items() if not str(k).startswith("_")})
    shapes = {k: v for k, v in pin_shapes(engine, pinner, target,
                                          skip=[k for k, w in weights.items() if float(w) <= 0]).items()
              if float(weights.get(k, 1)) > 0}
    last = getattr(engine, "last_pin_shape", None)
    if len(shapes) > 1:
        shapes.pop(last, None)   # never the same shape twice running
    if not shapes:
        return ""
    name = engine.rng.choices(list(shapes), weights=[float(weights.get(k, 1)) for k in shapes])[0]
    engine.last_pin_shape = name
    look, contacts = shapes[name]
    hits = "; ".join(f"{part} with \"{w}\"" for part, w in contacts if w)
    return (f"PIN SHAPE IDEA (pins shouldn't all look alike; use this one, or another of your own that isn't the "
            f"last pin over again): {pinner.name} pins {target.name} with {look}. In \"hits\": {hits}. Any limb can "
            f"press or grip any part: jaws can pin a paw, a forearm or a tail can choke.")


def grudge_hint(engine, roll=None):
    """PAYBACK, now and then (director.grudge_chance): a fighter with one part badly hurt may go for the same place on
    the one who did it. An idea, never an order."""
    from engine import body_region
    ch = float(engine.rules.get("director", {}).get("grudge_chance", 0.15))
    act = engine.active()
    if ch <= 0 or len(act) != 2 or (roll if roll is not None else engine.rng.random()) >= ch:
        return ""
    for me in sorted(act, key=lambda f: -max(p.damage for p in f.parts.values())):
        foe = next(f for f in act if f is not me)
        worst = max(me.parts.values(), key=lambda p: p.damage)
        if worst.damage < 150 or engine.pinned_by(me.name) or me.name in engine.downed:
            continue
        match = next((p for p in foe.parts if p.lower() == worst.name.lower()), None) or next(
            (p for p in foe.parts if body_region(p) == body_region(worst.name)), None)
        if match:
            return (f"PAYBACK idea (optional): {poss_name(me.name)} {worst.name.lower()} is wrecked, and she knows who did "
                    f"it. She might go for {poss_name(foe.name)} {match} to give back exactly what she got.")
    return ""


def drag_to_pin_hint(engine, roll=None):
    """Now and then (director.drag_to_pin_chance), when an opponent is down and not pinned: drag her somewhere worse
    first (a wall, the water) and pin her there next."""
    ch = float(engine.rules.get("director", {}).get("drag_to_pin_chance", 0.12))
    if ch <= 0 or (roll if roll is not None else engine.rng.random()) >= ch:
        return ""
    cfg = getattr(engine, "scene_cfg", None) or {}
    props = [p for p in (cfg.get("props") or []) if p and not engine.is_broken(p)]
    pools = [h["name"] for h in (cfg.get("hazards") or []) if any(w in ("pool", "shallows", "water") for w in h.get("words", []))]
    for d in engine.active():
        if d.name not in engine.downed or engine.pinned_by(d.name):
            continue
        a = next((f for f in engine.active() if f is not d and f.name not in engine.downed
                  and not engine.pinned_by(f.name)), None)
        if not a or not (props or pools):
            continue
        where = engine.rng.choice(pools + props)
        return (f"GROUND IDEA (optional): {d.name} is down. {a.name} could DRAG her (action \"drag\", into {where}) "
                f"this beat and pin her against it or in it on the next (\"pinned_against\": \"{where}\").")
    return ""


poss_name = poss_word   # (one possessive rule for the whole game: engine.poss_word)


def throat_hint(engine, roll=None):
    """Now and then (never demanded), suggest a bite at the neck or throat: a pin technique while pinning, or a
    fang/bite move (Ice Fang, Crunch...) in open fighting. rules.json director: throat_bite_chance (open fighting),
    throat_bite_pin_chance (while pinning)."""
    cfg = engine.rules.get("director", {})
    roll = engine.rng.random() if roll is None else roll
    # with a /focus on the throat (neck, vulnerable, head) the idea comes three times as often; otherwise the
    # throat is just one target among many and the idea is rare
    zs = {z for v in (cfg.get("focus") or {}).values() for z in (v or [])}
    if zs & {"neck", "vulnerable", "head"}:
        roll /= 3.0
    if engine.submission_match() and engine.hold_mix():
        # (hold_mix.hints) in a submission match the bite and choke ideas come that much less often
        roll /= max(0.01, float(engine.hold_mix().get("hints", 0.35)))
    for key, pin in engine.pins.items():
        if roll < float(cfg.get("throat_bite_pin_chance", 0.25)):
            a, d = pin["attacker"], pin["defender"]
            spots = [p for p in engine.get(d).parts if re.search(r"\b(neck|throat)\b", p.lower())]
            # what she already presses stays; the idea is something she isn't doing yet
            held = {h.part for h in engine.holds.values() if h.attacker == a and h.defender == d}
            t, sp = _grip_tools(engine, engine.get(a)), _spots(engine.get(d))
            if any(h.attacker == a and re.search(r"\b(jaws?|teeth|fangs?|mouth|bite)\b", str(h.with_part or "").lower())
                   for h in engine.holds.values()):
                t = dict(t, jaws=None)      # her jaws are already clamped on her: no second bite to suggest
            free = lambda key: [x for x in sp.get(key, []) if x not in held]
            ideas = []
            if t.get("jaws") and [x for x in spots if x not in held]:
                ideas += [(3, f"clamp her jaws on {poss_word(d)} {' or '.join([x for x in spots if x not in held][:2])} and "
                              f"twist (a pin technique: a bite hold on that part)")]
            if t.get("jaws") and free("arm"):
                ideas += [(3, f"clamp her jaws on {poss_word(d)} {engine.rng.choice(free('arm'))} and pin that limb to the "
                              f"{engine.scene_word('ground').split()[-1]} (add it to the pin: action 'pin', that part in \"hits\", \"with\": \"her jaws\")")]
            if (t.get("coil") or t.get("fore")) and [x for x in spots if x not in held]:
                w = t.get("coil") or t["fore"]
                ideas += [(3, f"get {w} across {poss_word(d)} {[x for x in spots if x not in held][0]} as a choke (add it to "
                              f"the pin: action 'pin', that part in \"hits\", \"with\": \"{w}\")")]
            if t.get("hook") and free("thigh"):
                leg = engine.rng.choice(free("thigh"))
                ideas += [(1, f"hook {poss_word(d)} leg and haul it up off the ground, folding it back toward her chest so "
                              f"her hips can't turn (add it to the pin: action 'pin', {leg} in \"hits\", \"with\": "
                              f"\"{t['hook']}\")")]
            if ideas:
                pick = engine.rng.choices(ideas, weights=[w for w, _ in ideas])[0][1]
                return f"TECHNIQUE IDEA (optional, if it fits): while pinning, {a} could {pick}."
        return ""
    if roll >= float(cfg.get("throat_bite_chance", 0.12)):
        return ""
    active = engine.active()
    options = []
    for f in active:
        fangs = [m["name"] for m in f.moves if any(w in m["name"].lower() for w in FANG_WORDS)
                 and m.get("target") in ("targeted", "hold")]
        foes = [x for x in active if x.team != f.team]
        if foes and not engine.pinned_by(f.name) and not any(engine.has(f, st) for st in ("asleep", "frozen", "flinched")):
            options.append((f, fangs, foes))
    if not options:
        return ""
    f, fangs, foes = engine.rng.choice(options)
    foe = engine.rng.choice(foes)
    spots = [p for p in foe.parts if re.search(r"\b(neck|throat)\b", p.lower())]
    t, sp = _grip_tools(engine, f), _spots(foe)
    held = {h.part for h in engine.holds.values() if h.attacker == f.name and h.defender == foe.name}
    ideas = []
    if fangs and spots:
        ideas.append(f"{f.name} could go for {poss_word(foe.name)} {' or '.join(spots[:2])} with "
                     f"{' or '.join(fangs[:2])}: a bite that clamps and twists")
    # a grip doesn't need a move from her list: any limb can hold any part (hold_start, "with" says what grips)
    if (t.get("coil") or t.get("fore")) and [x for x in spots if x not in held]:
        w = t.get("coil") or t["fore"]
        ideas.append(f"{f.name} could get a choke on {foe.name} without using her jaws: {w} locked round "
                     f"{poss_word(foe.name)} {[x for x in spots if x not in held][0]} (action hold_start, that part in "
                     f"\"hits\", \"with\": \"{w}\")")
    limbs = [x for x in sp["arm"] + sp["tail"] if x not in held]
    if t.get("jaws") and limbs:
        limb = engine.rng.choice(limbs)
        ideas.append(f"{f.name} could clamp her jaws on {poss_word(foe.name)} {limb} and hold that limb fast, dragging "
                     f"at it (action hold_start, {limb} in \"hits\", \"with\": \"her jaws\")")
    if not ideas:
        return ""
    return f"TECHNIQUE IDEA (optional, if it fits the moment): {engine.rng.choice(ideas)}."


def reposition_hint(engine, roll=None):
    """Now and then, when an opponent is lying on the ground, point the director at MOVING her first: rolling her
    over to reach the other side of her, or hauling her up for a slam or a throw. Always the director's choice.
    rules.json director: reposition_chance (0 = never suggested)."""
    cfg = engine.rules.get("director", {})
    chance = float(cfg.get("reposition_chance", 0.12))
    if chance <= 0:
        return ""
    cool = int(cfg.get("reposition_cooldown", 2) or 0)
    options = []
    for d in engine.active():
        if d.name not in engine.downed:
            continue
        last = getattr(engine, "_last_reposition", {}).get(d.name)
        if last is not None and engine.turn - last < cool:
            continue
        pinned = any(p["defender"] == d.name for p in engine.pins.values())
        for a in engine.active():
            if a is d or a.team == d.team or engine.pinned_by(a.name) or a.name in engine.pressed \
                    or any(engine.has(a, st) for st in ("asleep", "frozen", "flinched")):
                continue
            if pinned and d.name not in engine.pinning(a.name):
                continue   # someone else has her pinned: this fighter isn't the one handling her
            options.append((a, d, pinned))
    if not options:
        return ""
    r = engine.rng.random() if roll is None else roll
    if roll is None:
        engine.note_roll("director nudge: moving a downed opponent (roll her over / haul her up)", chance, r,
                         "suggested" if r < chance else "none")
    if r >= chance:
        return ""
    a, d, pinned = engine.rng.choice(options)
    fc = engine.facing_of(d.name)
    other = {"face-up": ("onto her front", "her back, the back of her neck and her hips"),
             "face-down": ("onto her back", "her chest, belly and throat")}.get(fc, ("onto her back", "her chest, belly and throat"))
    ideas = [f"roll her {other[0]} first (\"reposition\": \"{other[0]}\") to get at {other[1]}, then "
             + ("carry on the pin on that side" if pinned else "attack or pin her there")]
    if not pinned and fc != "sitting up":
        ideas.append(f"haul her up to sitting first (\"reposition\": \"sit her up\"): her chest, belly and throat are "
                     f"open in front and her back and neck behind, for one clean strike or a choke from behind")
    if not pinned and a.name not in engine.downed:
        ideas.append(f"drag her up onto her feet first (\"reposition\": \"stand her up\") and hit her standing")
        last = getattr(engine, "_last_manhandle", {}).get(a.name)
        if last is None or engine.turn - last >= int(cfg.get("manhandle_cooldown", 0) or 0):
            ideas.append(f"haul her up off the ground and THROW her (action \"throw\"): list what she crashes into in "
                         f"\"landing\", using the scene")
            ideas.append(f"lift her and SLAM her back down (action \"slam\"): onto the ground, a rock, or into the "
                         f"shallows (\"landing\")")
            ideas.append(f"take her by a leg, the scruff or the tail and DRAG her across the ground (action \"drag\"): "
                         f"over the rough stone and into or against something in the scene (\"landing\")")
    return (f"REPOSITION IDEA (optional, if it fits the moment): {d.name} is on the ground ({fc or 'down'}). {a.name} "
            f"could {engine.rng.choice(ideas)}.")


SCENE_PROPS = (("boulder", "a fallen boulder"), ("stalagmite", "a stalagmite"), ("wall", "the cave wall"),
               ("ledge", "the edge of the ledge"), ("pillar", "a pillar"), ("tree", "a tree"), ("rock", "a rock"))


def scene_props(engine, n=3):
    """A few solid things in this arena to be driven, thrown or pressed into (scenes.json props)."""
    return engine.scene_props()[:n] or ["the nearest wall"]


def scene_feature(engine, said):
    """The arena feature some words mean ("into the pipes" -> "the steam pipes"), or ""."""
    low = str(said or "").lower()
    h = engine.hazard_for(low)
    if h:
        return h["name"]
    for label in engine.scene_props():
        if label.split()[-1].lower() in low:
            return label
    return next((label for word, label in SCENE_PROPS if re.search(r"\b" + word, low)), "")


def director_prompt(engine):
    """The director's instructions, with the examples drawn from THIS arena. (Written for the sea cave; any other
    scene swaps the cave's stalactites and boulders for its own features, so the model isn't handed things that
    aren't there.)"""
    if engine.scene_name == "sea cave":
        return _air_grab_text(engine, DIRECTOR_PROMPT)
    props = engine.scene_props()
    ground, rough = engine.scene_word("ground"), engine.scene_word("rough")
    hz = [h["name"] for h in engine.scene_cfg.get("hazards") or []]
    a = (hz + props + [ground])[0]
    b = next((x for x in props if x != a), ground)
    three = ", ".join(f'"{x}"' for x in (props[:3] or [ground]))
    soft = next((h["name"] for h in engine.scene_cfg.get("hazards") or [] if h.get("cushion")), None)
    swaps = [
        ('"Nocturne: on the dry center ledge, favoring her left\nforeleg; Ripples: in the shallow pool, under Nocturne"',
         f'"Nocturne: beside {b}, favoring her left\nforeleg; Ripples: on {ground}, under Nocturne"'),
        ('{"surface": "a stalactite", "parts"', '{"surface": "' + a + '", "parts"'),
        ('{"surface": "a fallen boulder", "parts"', '{"surface": "' + b + '", "parts"'),
        ('{"surface": "the stone floor", "parts"', '{"surface": "' + ground + '", "parts"'),
        ('Water cushions: a landing in a pool is "light".',
         (f'A soft landing is "light": {soft}, for one.' if soft else "Nothing here is soft to land on.")),
        ('in "pinned_against" ("a fallen boulder", "a stalagmite", "the cave wall")', f'in "pinned_against" ({three})'),
        ("blast her off her feet into a boulder and hold her there, pin her\n  to the wall with a stream",
         f"blast her off her feet into {b} and hold her there, pin her\n  against {props[0] if props else ground} with a stream"),
        ('in "charge_into" ("a fallen boulder", "a stalagmite", "the cave wall")', f'in "charge_into" ({three})'),
        ("a shove into a pool", f"a shove into {a}"),
        ("onto the floor, a rock, a ledge's edge,\n           into the shallows.", f"onto {ground}, across {b}."),
        ("over rough stone, through\n           the water, and INTO or AGAINST an obstacle (a stalagmite, a boulder, the cave wall).",
         f"over {rough},\n           and INTO or AGAINST an obstacle ({', '.join(props[:3] or [ground])})."),
    ]
    out = DIRECTOR_PROMPT
    for old, new in swaps:
        out = out.replace(old, new)
    return _air_grab_text(engine, out)


def _air_grab_text(engine, text):
    """flight.air_grab: a flyer in the air CAN be grabbed by another flyer up there with talons or feet."""
    if not ((engine.rules.get("flight") or {}).get("air_grab") or {}).get("enabled", True):
        return text
    return text.replace("A fighter in the air can't be grabbed or pinned; a",
                        "A fighter in the air can't be grabbed or pinned, except that another flyer up there with "
                        "talons, feet or hands can \"grapple\" her: they lock together and tumble down to the ground; a")


def scene_block(engine, scene):
    """The scene as the director reads it: the description, then the features the program tracks, by name."""
    brief = engine.scene_brief()
    if not brief:
        return scene
    return (scene + "\n\nWHAT THIS PLACE DOES (tracked by the program; use these exact names as a \"surface\" in "
            "\"landing\", or in \"charge_into\" / \"pinned_against\", and the effect in brackets is rolled):\n" + brief
            + "\nNow and then the place also does something by itself; you never choose that.")


ENCOURAGE = {
    "sustain": "a HELD STREAM: a beam, stream or blast move held on her with \"sustain\": 2 to 4 (she keeps it on her "
               "pulse after pulse, maybe pinning her against the scenery)",
    "pummel": "a PUMMEL: one close strike with \"count\": {n} on her at no distance (inside a grab, against the scenery, or "
              "on her while she is down). If they are apart, get there first in a chain: grab her, or knock her down",
    "charge": "a CHARGE into the scenery: a charging move (or an improvised body charge) with \"charge_into\" set to a "
              "scene feature, driving her into it",
    "chain": "a CHAIN of {n} links: {n} quick actions in a row by the same attacker on her, each following the last",
    "throw": "a THROW: \"action\": \"throw\", hurling her into the scenery",
    "slam": "a SLAM: \"action\": \"slam\", lifting her and driving her down",
    "grab": "a GRAB: \"action\": \"grapple\", seizing her and keeping her at point-blank",
    "hold": "a HOLD: \"action\": \"hold_start\", a grip that squeezes",
    "pin": "a PIN, whenever one is allowed",
    "submission": "a SUBMISSION hold (an armbar, a crab, a crossface...), whenever an opening allows one",
    "feint": "a FEINT: \"feint\": true on a strike",
    "dive": "flying and DIVING: take off (\"reposition\": \"take off\") and strike down at her from the air",
    "carry": "a CARRY: from the air, a close strike with \"carry\": true, hauling her up to drop her",
    "spike": "a SPIKE: from the air, a carry (\"carry\": true) and then, as the next link, a dive, charge or held stream "
             "driving her straight down into the ground",
    "juggle": "a JUGGLE: a strike that \"launch\"es her as one link of a chain, and the next link catching her in the air",
    "launch": "a LAUNCH: a heavy strike with \"launch\": \"launched\" or \"thrown\"",
}
ENCOURAGE_ALIASES = {"stream": "sustain", "held": "sustain", "beam": "sustain", "pummels": "pummel", "charges": "charge",
                     "chains": "chain", "combo": "chain", "throws": "throw", "slams": "slam", "grapple": "grab",
                     "grabs": "grab", "holds": "hold", "pins": "pin", "submissions": "submission", "sub": "submission",
                     "feints": "feint", "flight": "dive", "dives": "dive", "fly": "dive", "carries": "carry",
                     "spikes": "spike", "juggles": "juggle", "launches": "launch"}


def style_hint(engine):
    """(since build 280) traits: how each fighter likes to fight (fighters.json style) and the moves she reaches for
    most (favors), so the director picks the way she would."""
    if not engine.traits_cfg():
        return ""
    out = []
    for f in engine.active():
        fav = sorted(((m, w) for m, w in (f.favors or {}).items() if float(w) > 1 and any(x["name"] == m for x in f.moves)),
                     key=lambda kv: -float(kv[1]))
        rare = [m for m, w in (f.favors or {}).items() if float(w) < 1 and any(x["name"] == m for x in f.moves)]
        if not f.style and not fav:
            continue
        out.append(f"HOW {f.name.upper()} FIGHTS: {f.style}".rstrip()
                   + (f" She reaches most for {', '.join(m for m, _ in fav[:5])}." if fav else "")
                   + (f" She seldom uses {', '.join(rare[:4])}." if rare else ""))
    return "\n".join(out)


def game_plan_hint(engine):
    """director.game_plan: now and then (nudge of the beats, rolled from the names and the beat so it never moves the
    fight's own dice), remind the director what each fighter came in meaning to take apart. Not for a fighter with a
    /focus: that one already says so."""
    import zlib
    cfg = engine.rules.get("director", {}).get("game_plan") or {}
    if not cfg.get("enabled", True):
        return ""
    out = []
    for f in engine.active():
        if engine.focus_for(f.name) or f.name in engine.downed:
            continue
        plan = engine.game_plan(f.name)
        if not plan or zlib.crc32(f"{f.name}|{engine.turn}".encode()) % 1000 >= 1000 * float(cfg.get("nudge", 0.35)):
            continue
        o = engine.get(plan["against"])
        worst = max((o.parts[p] for p in plan["parts"] if p in o.parts), key=lambda p: p.damage, default=None)
        so_far = (f" So far the worst of them is her {worst.name} ({worst.damage:.0f}%)." if worst and worst.damage >= 20
                  else "")
        end = (" and finish it with a hold on one of them, until she gives" if plan["finish"] == "hold" else
               " and wear them down until they give out under her")
        out.append(f"GAME PLAN (her own, from before the fight): {f.name} came in meaning to take {poss_word(o.name)} "
                   f"{plan['zone']} apart ({', '.join(plan['parts'][:6])}){end}.{so_far} A pull, not an order: she comes "
                   f"back to them when she can, and still takes a better opening where it is.")
    return "\n".join(out)


def encourage_hint(engine):
    """The author's /encourage: for its beats, the director is pointed hard at that kind of attack (who on whom, if
    named). A strong nudge, never an order: the rules and the dice still decide whether it works."""
    keep, lines = [], []
    for e in getattr(engine, "encouraged", None) or []:
        if engine.turn >= int(e.get("until", 0)):
            continue
        keep.append(e)
        att, dfn = e.get("attacker"), e.get("defender")
        try:
            if (att and engine.get(att).eliminated) or (dfn and engine.get(dfn).eliminated):
                continue
        except (ValueError, KeyError):
            continue
        what = ENCOURAGE.get(e["kind"], e["kind"]).replace("{n}", str(e.get("count") or (3 if e["kind"] == "pummel" else 2)))
        who = (f"{att}" if att else "whoever acts") + (f" on {dfn}" if dfn else "")
        left = int(e["until"]) - engine.turn
        lines.append(f"THE AUTHOR WANTS ({left} more beat{'s' if left != 1 else ''}): {who}: {what}. Do it this beat "
                     f"if it can be done at all; if it can't yet, set it up (close in, take off, knock her down, wait "
                     f"for the opening) so it comes soon.")
    engine.encouraged = keep
    return "\n".join(lines)


def flight_hint(engine, roll=None):
    """Flying is a winged fighter's strength: now and then point the director at it (rules.json director:
    flight_chance for one on the ground who could take off, more when the opponent has nothing that reaches the air;
    air_attack_chance for one already up: dive in, or seize and drop her)."""
    cfg = engine.rules.get("director", {})
    roll = engine.rng.random() if roll is None else roll
    if engine.pins:
        return ""
    lines = []
    for f in engine.active():
        if not any("wing" in p.lower() for p in f.parts) or f.name in engine.downed:
            continue
        foes = [x for x in engine.active() if x.team != f.team or not x.team]
        foes = [x for x in foes if x.name != f.name and not x.eliminated]
        if not foes:
            continue
        foe = min(foes, key=lambda x: x.health)
        reach = [m["name"] for m in foe.moves if engine.is_ranged(m) and foe.move_uses.get(m["name"], 1) > 0]
        if engine.has(f, "airborne"):
            if roll >= float(cfg.get("air_attack_chance", 0.35)):
                continue
            carry = [m["name"] for m in f.moves if m.get("carry") and f.move_uses.get(m["name"], 1) > 0]
            close = [m["name"] for m in f.moves if not engine.is_ranged(m) and not m.get("carry")
                     and m.get("target") not in ("self", "status", "hold") and f.move_uses.get(m["name"], 1) > 0][:3]
            lines.append(f"FLIGHT IDEA (optional): {f.name} is in the air ({f.status.get('airborne', 0)} beat(s) "
                         f"left up there). From above, her close moves are DIVES that land harder"
                         + (f" ({', '.join(close)})" if close else "")
                         + (f", or {carry[0]} can seize {foe.name} and drop her from a height" if carry and
                            foe.name not in engine.downed else
                            f", or a close strike with \"carry\": true can seize {foe.name} and haul her up to drop "
                            f"her (a second link can strike her as she falls, or SPIKE her down from above)"
                            if engine.can_carry(f, foe)[0] else "")
                         + f". {foe.name} can only reach her with "
                         + (", ".join(reach) if reach else "nothing she has (no beams, blasts or streams)")
                         + (f", or by climbing {' or '.join(engine.high_ground()[:3])} and LEAPING at her with a close "
                            f"strike (\"leap_from\")" if engine.high_ground() and foe.name not in engine.downed else "")
                         + ".")
        elif engine.can_fly(f) and not engine.pinning(f.name) and not engine.pinned_by(f.name):
            vig = engine.flight_vigour(f, "takeoff_mult", 1.0)
            ch = min(0.95, float(cfg.get("flight_chance", 0.3)) * (1.5 if not reach else 1.0) * vig)
            if roll >= ch:
                continue
            strong = vig >= 1.5      # still strong: flying is how she fights, not a gamble
            lines.append((f"FLIGHT (her way of fighting while she is strong): {f.name} should take off this beat "
                          f"unless the moment plainly needs her on the ground " if strong else
                          f"FLIGHT IDEA (optional, a winged fighter's strength): {f.name} could take off this beat ")
                         + 
                         f"(\"reposition\": \"take off\" on her own action, with her attack). Up there only beams, "
                         f"blasts and streams reach her ({foe.name} has "
                         + (", ".join(reach) if reach else "none: she would be out of reach") + "), and her close "
                         f"moves become dives from above that land harder."
                         + (f" Her wing is badly hurt, though: flying costs her {engine.takeoff_cost(f):.0f} energy and "
                            f"tears it worse every beat she stays up, so it's a gamble." if engine.wing_damage(f) >= float(
                                ((engine.rules.get("flight") or {}).get("strain") or {}).get("from", 100)) else ""))
    return "\n".join(lines[:1])


def sustain_hint(engine, prefer=None, roll=None):
    """Now and then, point the director at a HELD ranged attack: a stream or beam (a move marked sustainable) kept
    on the target for a few pulses, driving her back and pressing her into something in the scene, which adds
    environmental damage every pulse and may break. rules.json director: sustain_chance per beat."""
    cfg = engine.rules.get("director", {})
    roll = engine.rng.random() if roll is None else roll
    if engine.pins or roll >= float(cfg.get("sustain_chance", 0.10)):
        return ""
    per_pulse = float(engine.rules.get("moves", {}).get("sustain", {}).get("energy_per_pulse", 6))
    options = []
    for f in engine.active():
        if f.name in engine.downed or any(engine.has(f, st) for st in ("flinched", "asleep", "frozen")):
            continue
        moves = [m for m in f.moves if m.get("sustainable") and m.get("target") in ("spread", "targeted")
                 and f.move_uses.get(m["name"], 1) > 0 and f.energy >= engine.energy_cost(m) + 2 * per_pulse]
        foes = [x for x in engine.active() if x.team != f.team and x.name not in engine.downed]
        if moves and foes:
            options.append((f, moves, foes))
    if not options:
        return ""
    mine = [o for o in options if prefer and o[0].name == prefer]
    f, moves, foes = engine.rng.choice(mine or options)
    foe = engine.rng.choice(foes)
    # the strongest stream she has against this opponent, then the next one
    moves = sorted(moves, key=lambda m: -engine.move_math(f.name, foe.name, m)["effective"])[:2]
    props = scene_props(engine)
    return (f"BIG MOMENT IDEA (take it unless the story clearly calls for something else): {f.name} keeps "
            f"{' or '.join(m['name'] for m in moves)} pouring into {foe.name} instead of firing one blast. Write it as "
            f"the move itself: \"action\": \"combo\", \"move\": \"{moves[0]['name']}\", the parts it hits in \"hits\", "
            f"\"sustain\": 3 (2-4 pulses), and \"pinned_against\": one of {', '.join(props)}, so the stream drives "
            f"{foe.name} back and presses her against it. Every pulse hits again and grinds her into it; it may crack "
            f"and give way under her. (NOT \"hold_start\" and NOT \"pin\": those are grips with the body.)")


def charge_hint(engine, prefer=None, roll=None):
    """Now and then, point the director at a charge that carries the target into the scenery (rules.json director:
    charge_chance per beat)."""
    cfg = engine.rules.get("director", {})
    roll = engine.rng.random() if roll is None else roll
    if engine.pins or roll >= float(cfg.get("charge_chance", 0.08)):
        return ""
    options = []
    for f in engine.active():
        if (f.name in engine.downed or engine.pinned_by(f.name)
                or any(engine.has(f, st) for st in ("flinched", "asleep", "frozen"))):
            continue
        # a charge on the ground can't reach a fighter in the air (one in the air can dive-charge anyone)
        foes = [x for x in engine.active() if x.team != f.team and x.name not in engine.downed
                and (engine.has(f, "airborne") or not engine.has(x, "airborne"))]
        if foes and f.energy >= 25:
            options.append((f, foes))
    if not options:
        return ""
    mine = [o for o in options if prefer and o[0].name == prefer]
    f, foes = engine.rng.choice(mine or options)
    foe = engine.rng.choice(foes)
    named = [m["name"] for m in f.moves if m.get("charge") and f.move_uses.get(m["name"], 1) > 0]
    how = ((" or ".join(named[:2]) + " (or an improvised charge)") if named else
           "an improvised charge (\"move\": \"improvised\", e.g. \"shoulder ram\" or \"body charge\")")
    props = scene_props(engine)
    return (f"BIG MOMENT IDEA (take it unless the story clearly calls for something else): {f.name} CHARGES {foe.name} "
            f"with {how} and doesn't stop at the hit: \"charge_into\": one of {', '.join(props)}. She drives {foe.name} "
            f"backward and slams her into it, crushing her between her own body and the surface. {foe.name} is left "
            f"pressed there for a moment: you may add a second action (a follow-up strike or bite before she falls); "
            f"she usually crumples to the ground at the end of the beat.")


def grapple_hint(engine, prefer=None, roll=None):
    """Now and then, point the director at a fighter on her feet seizing another and throwing her into the scenery or
    slamming her down (rules.json director: grapple_chance per beat; 0 = never suggested)."""
    cfg = engine.rules.get("director", {})
    roll = engine.rng.random() if roll is None else roll
    if engine.pins or roll >= float(cfg.get("grapple_chance", 0.05)):
        return ""
    cool = int(cfg.get("manhandle_cooldown", 0) or 0)
    options = []
    for f in engine.active():
        last = getattr(engine, "_last_manhandle", {}).get(f.name)
        if (f.name in engine.downed or engine.pinned_by(f.name) or f.name in engine.pressed or f.energy < 20
                or (last is not None and engine.turn - last < cool)
                or any(engine.has(f, st) for st in ("flinched", "asleep", "frozen", "airborne"))):
            continue
        foes = [x for x in engine.active() if x.team != f.team and x.name not in engine.downed
                and not engine.has(x, "airborne")]
        if foes:
            options.append((f, foes))
    if not options:
        return ""
    mine = [o for o in options if prefer and o[0].name == prefer]
    f, foes = engine.rng.choice(mine or options)
    foe = engine.rng.choice(foes)
    props = scene_props(engine)
    if engine.rng.random() < 0.5:
        what = (f"THROWS her (action \"throw\"): list what she crashes into in \"landing\", in order, e.g. "
                f"{props[0]} and then {engine.scene_word('ground')}, each with the parts it hits and a severity")
    else:
        what = (f"LIFTS her and SLAMS her down at her own feet (action \"slam\"): put what she comes down on in "
                f"\"landing\" ({engine.scene_word('ground')}, {props[-1]}), with the parts it hits and a severity")
    return (f"BIG MOMENT IDEA (optional, if it fits the moment): {f.name} SEIZES {foe.name} (by the scruff, a limb, the "
            f"tail, or round the body) and {what}. {foe.name} may slip the grab; if she doesn't, she ends on the ground.")


def clinch_hint(engine, prefer=None, roll=None):
    """Now and then, point the director at a grapple: one fighter taking hold of another who is on her feet and
    working her over at point-blank (rules.json director: clinch_chance; 0 = never suggested)."""
    cfg = engine.rules.get("director", {})
    roll = engine.rng.random() if roll is None else roll
    if engine.pins or roll >= float(cfg.get("clinch_chance", 0.05)):
        return ""
    options = []
    for f in engine.active():
        if (f.name in engine.downed or engine.pinned_by(f.name) or f.name in engine.pressed or f.energy < 25
                or any(engine.has(f, st) for st in ("flinched", "asleep", "frozen", "airborne"))):
            continue
        foes = [x for x in engine.active() if x.team != f.team and x.name not in engine.downed
                and not engine.grab_between(f.name, x.name) and not engine.has(x, "airborne")]
        if foes:
            options.append((f, foes))
    if not options:
        return ""
    mine = [o for o in options if prefer and o[0].name == prefer]
    f, foes = engine.rng.choice(mine or options)
    foe = engine.rng.choice(foes)
    close = [m["name"] for m in f.moves if m.get("target") == "targeted" and not m.get("charge")]
    streams = [m["name"] for m in f.moves if m.get("sustainable") and f.move_uses.get(m["name"], 1) > 0]
    ways = [f"short blows with one close move thrown again and again (a strike with \"count\" 3"
            + (f", e.g. {engine.rng.choice(close)}" if close else ", e.g. an improvised jab") + ")",
            "an improvised flurry (jabs, knees, a headbutt) and then one bigger blow that knocks her down or launches her"]
    if streams:
        ways.append(f"{engine.rng.choice(streams)} held on her at no distance (\"sustain\" 3; no \"pinned_against\" needed)")
    ways.append("a throw or a slam out of the grab, which she can't slip")
    props = scene_props(engine)
    if props and close:
        # held against the scenery: driven back into something solid and pummelled there, nowhere to give
        ways.append(f"she drives {foe.name} back against {engine.rng.choice(props)} and holds her there while she "
                    f"pummels her ({engine.rng.choice(close)} with \"count\" 3 or 4 and \"pinned_against\" that, so every "
                    f"blow grinds her into it)")
    engine.rng.shuffle(ways)
    return (f"BIG MOMENT IDEA (optional, if it fits the moment): {f.name} TAKES HOLD of {foe.name} (action \"grapple\" "
            f"as the first action: the part she grips in \"part\", what she grips it with in \"hits\") and works her "
            f"over at point-blank in the SAME beat (actions 2 and 3): {ways[0]}, or {ways[1]}. While the grab holds "
            f"neither can dodge the other. {foe.name} may slip the grab; if she does, nothing follows.")


def chain_hint(engine, prefer=None, roll=None):
    """Now and then, point the director at a chain: two or three attacks by one fighter in one beat, each leading
    into the next (rules.json director: chain_chance; 0 = never suggested)."""
    cfg = engine.rules.get("director", {})
    roll = engine.rng.random() if roll is None else roll
    if engine.pins or roll >= float(cfg.get("chain_chance", 0.05)):
        return ""
    options = []
    for f in engine.active():
        if (engine.pinned_by(f.name) or f.name in engine.pressed or f.energy < 30
                or any(engine.has(f, st) for st in ("flinched", "asleep", "frozen"))):
            continue
        foes = [x for x in engine.active() if x.team != f.team]
        if foes:
            options.append((f, foes))
    if not options:
        return ""
    mine = [o for o in options if prefer and o[0].name == prefer]
    f, foes = engine.rng.choice(mine or options)
    foe = engine.rng.choice(foes)
    close = [m["name"] for m in f.moves if m.get("target") == "targeted" and not m.get("charge")]
    engine.rng.shuffle(close)
    shape = engine.rng.choice([
        "a quick improvised blow that opens her guard, then " + (close[0] if close else "a harder one") + " into the gap",
        "two fast blows to the same spot or the part beside it, then something bigger that knocks her down or launches her",
        (close[0] if close else "a named move") + ", and straight out of it " + (close[1] if len(close) > 1 else "an improvised follow-up")
        + (", then a throw or a slam to finish" if f.name not in engine.downed and foe.name not in engine.downed else ""),
    ] + ([
        # a JUGGLE: launched off her feet, and caught in the air before she comes down
        "a rising blow (an uppercut to the jaw, a horn or a head driven up under her chest) that LAUNCHES her "
        "(\"launch\": \"launched\", no \"landing\" yet), then " + (close[0] if close else "a second blow")
        + " catches her in the air before she lands and smashes her back down (that link gets the \"landing\"): the juggle"
    ] if f.name not in engine.downed and foe.name not in engine.downed and not engine.has(foe, "airborne") else []))
    ahead = engine.strength(f) - engine.strength(foe)
    more = (" She is well on top: this one can run to four or five links if she keeps finding openings."
            if ahead >= 25 and engine.strength(f) >= 50 else "")
    return (f"BIG MOMENT IDEA (optional, if it fits the moment): {f.name} STRINGS two or three attacks together on "
            f"{foe.name} this beat, each leading into the next: {shape}. Put them as actions 1, 2 (and 3), all with "
            f"{f.name} as attacker and {foe.name} as defender, different moves or different parts. If {foe.name} "
            f"dodges one, the rest doesn't happen.{more}")


def big_moment_hint(engine, prefer=None):
    """At most one big-moment idea a beat: a held stream pressed into the scenery, a charge that carries her into
    it, a grab that ends in a throw or a slam, a grapple, or a chain. One roll decides which, by the five chances in
    rules.json -> director. When the fight has gone director.big_moment_overdue beats without any big moment, the
    roll is skipped: one is suggested for certain, and more firmly."""
    dcfg = engine.rules.get("director", {})
    kinds = [("held stream", float(dcfg.get("sustain_chance", 0.10)), sustain_hint),
             ("charge", float(dcfg.get("charge_chance", 0.08)), charge_hint),
             ("throw or slam", float(dcfg.get("grapple_chance", 0.05)), grapple_hint),
             ("grapple", float(dcfg.get("clinch_chance", 0.05)), clinch_hint),
             ("chain", float(dcfg.get("chain_chance", 0.05)), chain_hint)]
    kinds = [k for k in kinds if k[1] > 0]
    total = sum(k[1] for k in kinds)
    if not kinds or engine.pins:
        return ""
    due_after = int(dcfg.get("big_moment_overdue", 10) or 0)
    since = int(engine.turn) - int(engine.tally.get("big|last", 0))
    overdue = due_after > 0 and since >= due_after
    big = engine.rng.random()
    pick, acc = None, 0.0
    scale = (1.0 / total) if overdue else 1.0     # overdue: the same proportions, stretched to certainty
    for name, ch, fn in kinds:
        acc += ch * scale
        if big < acc:
            pick = (name, fn)
            break
    engine.note_roll("director nudge: a big moment (held stream, charge, throw, grapple or chain)"
                     + (f": none for {since} beats, so one is due" if overdue else ""),
                     1.0 if overdue else min(1.0, total), big, pick[0] if pick else "none")
    if not pick:
        return ""
    text = pick[1](engine, prefer=prefer, roll=0.0)
    if not text and overdue:
        # the one drawn can't happen right now (nobody on her feet, no stream to hold...): try the others
        for name, ch, fn in kinds:
            text = fn(engine, prefer=prefer, roll=0.0)
            if text:
                break
    if text and overdue:
        text = re.sub(r"BIG MOMENT IDEA \([^)]*\):",
                      f"BIG MOMENT IDEA, OVERDUE (the fight has gone {since} beats without one: do this now unless "
                      f"it truly can't happen):", text, count=1)
    return text


def pin_urge(engine, roll=None):
    """Point the director at a pin when the engine rolled an opening for one this beat (engine.roll_pin_windows:
    rare against a strong fighter on her feet, likelier after a knockdown, much likelier under half strength)."""
    if engine.pins:
        # a pin is running: now and then, point a free fighter at piling on for a double pin
        cfg = engine.rules.get("director", {})
        r = engine.rng.random() if roll is None else roll
        for p in engine.pins.values():
            crew = engine.pin_members(p)
            if len(crew) >= int(engine.rules.get("pin", {}).get("max_pinners", 2)):
                continue
            pinned = engine.get(p["defender"])
            free = [f.name for f in engine.active() if f.name not in crew and f is not pinned and f.team != pinned.team
                    and f.name not in engine.downed and not engine.pinned_by(f.name) and not engine.pinning(f.name)
                    and not any(engine.has(f, st) for st in ("flinched", "asleep", "frozen", "reeling"))]
            if free and roll is None:
                engine.note_roll(f"director nudge: {free[0]} joins the pin", float(cfg.get("double_pin_chance", 0.35)), r,
                                 "suggested" if r < float(cfg.get("double_pin_chance", 0.35)) else "none")
            if free and r < float(cfg.get("double_pin_chance", 0.35)) * float((cfg.get("pin_urge") or {}).get("scale", 1.0)):
                return (f"DOUBLE PIN IDEA (take it unless the story clearly calls for something else): {free[0]} piles "
                        f"onto {pinned.name} as well, joining {' and '.join(crew)}: action 'pin' with {free[0]} as "
                        f"attacker and {pinned.name} as defender, pressing parts that are still free. Both hold her "
                        f"down on the same clock, and she has half the chance to get out.")
        return ""
    best = None
    for target in engine.active():
        if engine.pin_window.get(target.name) is not True or not engine.pin_allowed(target.name)[0]:
            continue
        pinners = [f for f in engine.active() if f.team != target.team and not engine.has(f, "flinched")
                   and not engine.has(f, "asleep") and not engine.has(f, "frozen") and not engine.has(f, "reeling")
                   and not engine.pinned_by(f.name)
                   and (f.name not in engine.downed or target.name in engine.downed)]
        if not pinners:
            continue
        chance = engine.pin_chance(target)
        if best is None or chance > best[0]:
            best = (chance, target, max(pinners, key=engine.strength))
    if best is None:
        return ""
    _, target, pinner = best
    strong = engine.strength(target) >= 50
    odds = (f" She's still strong (about {engine.escape_base(target) * 100:.0f}% of her escape tries work), so she will "
            f"probably fight her way out: this is pressure and position, not the finish." if strong else
            f" She's worn down (only about {engine.escape_base(target) * 100:.0f}% of her escape tries work): this pin "
            f"can win.")
    shape = pin_shape_hint(engine, pinner, target)
    shape = ("\n" + shape) if shape else ""
    if target.name in engine.downed:
        return (f"PIN OPPORTUNITY: {target.name} is on the ground and there is an opening (she's at "
                f"{engine.strength(target):.0f}% of full strength). Unless the story clearly calls for something else, "
                f"{pinner.name} goes for the pin this beat (action 'pin', several points of contact).{odds}{shape}")
    if engine.rules.get("pin", {}).get("require_downed", False):
        return (f"PIN SETUP: there is an opening to pin {target.name} (she's at {engine.strength(target):.0f}% of full "
                f"strength). Unless the story clearly calls for something else, {pinner.name} knocks her down this "
                f"beat (a strike with launch 'knocked down' or 'thrown') and pins her as the second action in the "
                f"same beat.{odds}{shape}")
    return (f"PIN OPENING: {pinner.name} has an opening to pin {target.name} this beat (she's at "
            f"{engine.strength(target):.0f}% of full strength). Unless the story clearly calls for something else, "
            f"{pinner.name} takes her down into a pin: either action 'pin' on its own (a tackle, a trip, dragging her "
            f"to the ground and pinning her there), or a knockdown strike first and the pin as the second action.{odds}"
            f"{shape}")


def tactic_hint(engine, payoff_only=False):
    """Plans (tactics): a PAYOFF nudge while a setup is waiting for it (her opponent soaked and her lightning ready;
    the rain called and her water ready), or now and then (tactics.idea_chance) an idea for a setup or a read."""
    cfg = engine.rules.get("tactics") or {}
    if not cfg.get("enabled", True):
        return ""
    for s in engine.tactic_payoffs():
        who = engine.fighters.get(s["who"].lower())
        if who is None or who.eliminated or who.name in engine.downed or engine.pinned_by(who.name):
            continue
        # (the director chooses before the beat's clock moves on: the setup was made at the end of a beat already counted)
        left = max(1, s["until"] - engine.turn)
        ago = max(1, engine.turn - s["made"] + 1)
        return (f"PAYOFF (a plan in motion): {s['setup']} {ago} beat(s) ago. Now: {s['payoff']} "
                f"(it has {left} beat(s) left before the chance is gone). Unless the story clearly calls for something "
                f"else, {who.name} does it this beat, and says so in 'intent' (the plan, in a few words).")
    if payoff_only:
        return ""
    ideas = engine.tactic_ideas()
    if not ideas or engine.rng.random() >= float(cfg.get("idea_chance", 0.3)):
        return ""
    reads = [i for i in ideas if i["step"] == "read"]
    i = engine.rng.choice(reads or ideas)
    return (f"TACTIC IDEA ({'a read' if i['step'] == 'read' else 'a setup, with a payoff to come'}): {i['text']}. If "
            f"{i['who']} does it, put the plan in 'intent' in a few words, so the story can show it was meant.")


def submission_urge(engine):
    """Point the director at a submission hold when the engine rolled one of its very rare openings this beat."""
    for h0 in list(engine.holds.values()):
        if not h0.sub:
            continue
        hs = [h for h in engine.holds.values() if h.sub and h.attacker == h0.attacker and h.defender == h0.defender]
        held = engine.get(h0.defender)
        beats = max(h.turns_active for h in hs)
        free = (engine.SUBMISSIONS.get(h0.sub) or {}).get("free", {}).get(engine.body_plan(engine.get(h0.attacker)), "")
        kinds = engine.held_reach_kinds(held, engine.get(h0.attacker))
        words = {"bite": "her jaws", "arm": "her paws", "leg": "a kick", "tail": "her tail"}
        reach = ("" if kinds is None else
                 f" Held down there, {held.name} can only reach {h0.attacker} with "
                 f"{' or '.join(words[k] for k in kinds)} (moves fired across the gap aside)." if kinds else
                 f" Held down there, nothing of {poss_name(held.name)} reaches {h0.attacker} but a move fired across "
                 f"the gap: she struggles.")
        if engine.sub_stuck(held, hs):
            return (f"SUBMISSION, AND SHE CAN'T GET OUT: {held.name} has been in {poss_name(h0.attacker)} {h0.sub} for "
                    f"{beats} beat(s) and has nothing left to break it with. Don't just keep cranking it: {h0.attacker} "
                    f"lets it go and PINS her (action 'pin': the hold comes off for it; there is an opening), or hurts "
                    f"her another way while she's locked in it (a strike with what she has free: {free}).") + reach
        return (f"SUBMISSION ON: {poss_name(h0.attacker)} {h0.sub} on {held.name} has been on {beats} beat(s); the "
                f"longer it stays on, the likelier she wrenches out of it. {h0.attacker} keeps cranking it ('breather' "
                f"keeps every grip on), or uses what she has free on her ({free}) as a strike.") + reach
    for target in engine.active():
        if (getattr(engine, "sub_window", None) or {}).get(target.name) is not True:
            continue
        holders = [f for f in engine.active() if f.team != target.team
                   and (f.name not in engine.downed or engine.ground_lock_ok(f.name, target.name))
                   and not engine.regrab_wait(f, target)
                   and not engine.sub_caught(f)
                   and not engine.pinned_by(f.name) and not engine.pinning(f.name)
                   and not any(engine.has(f, st) for st in ("flinched", "asleep", "frozen", "reeling"))
                   and engine.submission_shapes(f.name, target.name)]
        if not holders:
            continue
        h = max(holders, key=engine.strength)
        shapes = engine.submission_shapes(h.name, target.name)
        name = engine.pick_submission(shapes, defender=target.name)
        s = shapes[name]
        choke_ = engine.sub_is_choke(s)
        where = (f"is DOWN on the ground, the best moment there is for a hold, before she can get up: {h.name} "
                 f"can lock her in a {name.upper()}" if target.name in engine.downed else
                 f"is on her feet but open (a worn part, a stumble, a moment's opening), and {h.name} can TAKE HER DOWN "
                 f"into a {name.upper()} (the engine puts her on the ground for it)")
        return (f"SUBMISSION OPENING{' (very rare)' if not engine.submission_match() else ''}: {target.name} {where} "
                f"({s['look']}). Unless the story clearly calls for something else, {h.name} does it this beat: action "
                f"'submission' with \"improvised_name\": \"{name}\". It wrenches her ({s['strain']}) every beat, "
                f"harder each beat, for a few beats; it is not a pin. {h.name} still has {s['free']} free: she can use "
                f"it on her as a second action in the same beat. Other holds that fit: "
                f"{', '.join(n for n in shapes if n != name and (choke_ or not engine.sub_is_choke(shapes[n]))) or 'none'}"
                + ("" if choke_ else " (a lock, not a choke: most submissions are won on a limb or the body, and a "
                   "choke only now and then)")
                + f". Or INVENT one of her own that her body and "
                f"the place allow: give it a short name in \"improvised_name\" and put the parts of {target.name} it "
                f"grips in \"hits\", the worst first, each with \"with\" = what of {h.name} grips it (her paws, "
                f"her twin tails, her jaws, her weight). The engine checks it against both bodies."
                + (f" {target.name} is on her feet: a hold put on her standing (a full nelson, a headlock, a bear "
                   f"hug, one of your own) keeps her up, with \"upright\": true, and may bear her down as it goes on; "
                   f"any other takes her down into it." if target.name not in engine.downed else ""))
    return ""


TARGETING_TEXT = {
    "one": "TARGETING STYLE (author's choice): focused. Each attack hits ONE body part; work the same spot again and "
           "again.",
    "few": "TARGETING STYLE (author's choice): each attack catches a FEW parts (2-3): the target and what's right "
           "next to it.",
    "many": "TARGETING STYLE (author's choice): spread it out. Attacks catch MANY parts (4-6): sweeping blows, "
            "slams, throws and landings across the body.",
    "all": "TARGETING STYLE (author's choice): everything. Prefer whole-body moves, big slams, launches and "
           "landings that hit as much of the body as possible.",
}


def dominate_turn(engine):
    """(since build 277) director.plan_dominate: under /plan dominate, whether the one being dominated may attack this
    beat at all (True), or the beat is the winner's (False); None when no such plan is on. Rolled once a beat
    (rival_turn_chance)."""
    cfg = (engine.rules.get("director") or {}).get("plan_dominate") or {}
    plan = engine.plan or {}
    if plan.get("shape") != "dominate" or not plan.get("winner") or not cfg.get("enabled", True):
        return None
    if getattr(engine, "directed", False):
        engine._dominate_turn = (engine.turn, True)    # your own direction this beat: it goes as you wrote it
        return None
    got = getattr(engine, "_dominate_turn", None)
    if got and got[0] == engine.turn:
        return got[1]
    ch = float(cfg.get("rival_turn_chance", 0.15))
    roll = engine.rng.random()
    engine.note_roll(f"the dominated fighter getting a beat of her own against {plan['winner']} (/plan dominate)", ch,
                     roll, "she gets one" if roll < ch else f"the beat is {plan['winner']}'s")
    engine._dominate_turn = (engine.turn, roll < ch)
    return engine._dominate_turn[1]


def plan_hint(engine):
    """The author's nudge on how the fight should go, turned into a concrete note for this beat. It only steers
    the director's choices; the engine's rolls (dodges, escapes, statuses) still decide what actually happens."""
    plan = engine.plan or {}
    out = []
    shape, winner = plan.get("shape", ""), plan.get("winner", "")
    active = engine.active()
    w = next((f for f in active if f.name == winner), None)
    rivals = [f for f in active if w is None or f.team != w.team]
    if shape and len(active) >= 2:
        if w is not None and rivals:
            ws = engine.strength(w)
            rs = max(engine.strength(f) for f in rivals)
            rival = max(rivals, key=engine.strength).name
        if shape == "close":
            if w is None:
                out.append("STORY PLAN (author's nudge): a CLOSE fight. Keep it back-and-forth: whoever is ahead "
                           "should get hit back soon; nobody pulls far ahead.")
            elif ws - rs > 15:
                out.append(f"STORY PLAN (author's nudge): a CLOSE fight that {w.name} should edge out in the end. "
                           f"{w.name} is ahead too early ({ws:.0f}% vs {rs:.0f}%): give {rival} the next exchange.")
            elif rs - ws > 25:
                out.append(f"STORY PLAN (author's nudge): a CLOSE fight that {w.name} should edge out in the end. "
                           f"{w.name} has fallen behind ({ws:.0f}% vs {rs:.0f}%): she fights back now.")
            else:
                out.append(f"STORY PLAN (author's nudge): a CLOSE, back-and-forth fight; {w.name} should win it late, "
                           f"by a narrow margin. Trade blows evenly for now.")
        elif shape == "dominate" and w is not None:
            out.append(f"STORY PLAN (author's nudge): {w.name} DOMINATES. Most of the attacks are hers; {rival} gets "
                       f"only brief, desperate counters. {w.name} should land big hits, knockdowns, and pins.")
            if dominate_turn(engine) is False:
                out.append(f"THIS BEAT BELONGS TO {w.name.upper()} (the author's plan): {rival} gets no attack, grab or "
                           f"pin of her own this beat; {w.name} acts, and {rival} can only take it, cover up or give "
                           f"ground.")
        elif shape == "comeback" and w is not None:
            if ws > 50 and ws >= rs - 10:
                out.append(f"STORY PLAN (author's nudge): a COMEBACK for {w.name}. For now, {rival} is on top: "
                           f"{w.name} takes heavy punishment and is pushed toward the edge.")
            else:
                out.append(f"STORY PLAN (author's nudge): a COMEBACK for {w.name}. She's been beaten down; now she "
                           f"turns it around: fierce counters, reversals, and her best moves.")
        elif shape == "even":
            out.append("STORY PLAN (author's nudge): an even fight. Share the attacks fairly and let the dice decide.")
    elif winner and w is not None and rivals:
        out.append(f"STORY PLAN (author's nudge): {w.name} should win this fight in the end, but make it earned.")
    for att in active:
        zones = engine.focus_for(att.name)
        if not zones:
            continue
        foes = [f for f in active if f.team != att.team]
        if any(str(z).lower() in engine.INJURED_WORDS for z in zones):
            for f in foes:
                hurt, side = engine.injured_targets(f.name)
                worst = sorted((p for p in f.parts.values() if p.damage >= 30), key=lambda p: -p.damage)[:6]
                if not worst:
                    continue  # nothing is hurt yet: aim anywhere
                around = [p for p in hurt if p not in {w.name for w in worst}][:6]
                out.append(f"TARGET FOCUS (author's nudge): {att.name} goes after what is ALREADY HURT on {f.name}, the "
                           f"way a fighter works a bad leg: " + ", ".join(f"{p.name} ({p.damage:.0f}%)" for p in worst)
                           + (f"; and the parts right around them: {', '.join(around)}" if around else "")
                           + (f". Her whole {side.upper()} side is badly hurt: keep working that side." if side else ".")
                           + " Vary the moves; an occasional hit elsewhere is fine.")
            zones = [z for z in zones if str(z).lower() not in engine.INJURED_WORDS]
            if not zones:
                continue
        per = []
        for f in foes:
            parts = engine.zone_parts(f.name, zones)
            per.append(f"{poss_word(f.name)}: {', '.join(parts)}" if parts else f"{f.name} has no such parts (aim anywhere)")
        out.append(f"TARGET FOCUS (author's nudge): {att.name} aims her attacks mostly at the {' + '.join(zones)}. "
                   + "; ".join(per) + ". Choose moves and body parts that fit; an occasional hit elsewhere is fine.")
    if plan.get("targeting") in TARGETING_TEXT:
        out.append(TARGETING_TEXT[plan["targeting"]])
    if out:
        out.append("(These are nudges for your choices only. The engine's rolls still decide what lands, who "
                   "escapes, and who wins.)")
    return "\n".join(out)


def move_range(move):
    """close: claws, bites, tackles, holds; ranged: beams, blasts, waves, whole-body and status moves."""
    if move is None:
        return "close"
    if "ranged" in move:
        return "ranged" if move["ranged"] else "close"
    return "close" if move.get("target", "targeted") in ("targeted", "hold", "self") else "ranged"


def range_hint(engine, run=3):
    """If the last few attacks were all up close, nudge toward a ranged or special move."""
    recent = engine.move_log[-run:]
    if len(recent) < run:
        return ""
    kinds = []
    for who, name in recent:
        f = engine.fighters.get(str(who).lower())
        m = next((x for x in (f.moves if f else []) if x["name"] == name), None)
        kinds.append(move_range(m) if m else "close")
    if any(k != "close" for k in kinds):
        return ""
    has_ranged = [f.name for f in engine.active() if any(move_range(m) == "ranged" and m.get("target") != "hold"
                                                        for m in f.moves)]
    if not has_ranged:
        return ""
    return (f"RANGE VARIETY: the last {run} attacks were all up close. This beat, use a ranged or special move (a "
            f"beam, blast, pulse, wave, lightning, or a status move), or knock the opponent away to open the distance. "
            f"Fighters with ranged moves: {', '.join(has_ranged)}.")
