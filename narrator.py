"""
Narrator: turns an already-resolved beat into prose. It may not change any outcome.

Two things keep a mid-size local model writing well:
  1. It gets a plain-English list of exactly what happened, not raw JSON.
  2. Long beats are written in two halves: first the acting fighter's side, then the receiving side,
     with the second half continuing from the first. Short generations stay coherent; long ones drift.
How it writes (perspective, pins, tone) comes from story_prompt.txt and style_sample.txt.
"""
import json
import random
import re

import blocks as story_blocks
import llm
import userprompt
from engine import tier_for, pain_tiers, Engine, body_region

CRAFT_RULES = """You are the narrator of a fight story. A rules engine has ALREADY decided what happens.
You turn WHAT HAPPENS IN THIS BEAT into prose.

Hard rules (these override everything else):
- Narrate ONLY the events listed under WHAT HAPPENS IN THIS BEAT, in order. The previous beats are context
  you have already told: never retell, summarize, or repeat them.
- The listed body parts are the truth. If a move description names a different body part, follow the list.
- Never invent extra hits, injuries, escapes, or outcomes. Do not decide what happens after this beat.
- Each hit has an IMPACT (how the moment of the blow looks: a heavy blow makes them cry out and stagger even
  on fresh tissue) and a LASTING pain level (how it feels afterward). Show both: a big hit can land hard and
  still leave only a dull ache. "Very painful" and worse lasting pain must visibly change how the fighter
  moves, breathes, and sounds from then on.
  Older injuries listed under CURRENT CONDITION keep hurting and keep affecting movement.
- No numbers, percentages, or game terms in the prose, and never use colors as pain levels ("red pain", "went
  black", "a yellow ache", "orange"): describe the feeling itself. The pain-level names (minor, sore, hurting, very painful,
  excruciating, devastated, numb with shock) and toughness words are guidance for you: show them, never quote them as labels.
- TONE (hard rule): a Pokemon battle, intense and physical, with only a LITTLE gore. Allowed: bruising,
  swelling, scratches, small cuts, a thin trickle of blood, a split lip, the sting of a bite. Never extreme:
  no torn or shredded flesh, no exposed bone or insides, no broken or cracking bones, no blood pooling,
  spraying, or soaking, nothing severed or detached, no death or dying. Show heavy damage through pain,
  trembling, strained breathing, cries, and finally fainting.
- BREATHING can be knocked out, choked off, or blocked by a hold, but only for a few seconds at a time: the
  fighter always gets air again. Breathing never stops for good.
- NECK AND THROAT BITES are allowed and can be brutal: jaws clamping the neck or throat, teeth sinking in, the
  attacker twisting and wrenching her head side to side, the choked gasp, the pain flaring through neck and
  shoulders. Keep it within the TONE rule: nothing torn out, the neck never bends at a wrong angle or snaps.
- EVERY OTHER ATTACK MAY BE AS BRUTAL AS THAT, AND NO MORE. A strike, slam, throw, drag, hold or pin can be told
  with the same force as a throat bite: a limb wrenched and twisted to its limit, a body ground into the floor, a
  blow that folds her and drives the air out, a grip that crushes until she cries out, the attacker bearing
  down, worrying at it, refusing to ease. How brutal follows the hit's IMPACT and pain level: a light hit is never
  brutal. The throat bite is the CEILING: nothing torn, no joint bent the wrong way or popped out, nothing broken
  that CURRENT CONDITION doesn't allow, no more blood than the TONE rule allows.
- BONES can be bruised or cracked (a cracked rib, a jarred joint). Broken, fractured, or shattered bones are
  allowed ONLY for parts CURRENT CONDITION says "can break". Every other part stays unbroken.
- Anatomy and colors come ONLY from each fighter's APPEARANCE under FIGHTERS. Never give a fighter a feature,
  color, or body part from another species (no hooves on an Absol, no antennae on a Buizel).
- The SCENE's features are fixed: use them for visual detail (its ground, its water, its light, whatever stands
  or hangs in it) and never invent a different arena or add things the SCENE does not name.
- Respect POSITIONS: fighters are exactly where it says (standing, face-down, in water, coiled...). Movement
  between positions happens only through the listed actions.
- WHAT IS FIXED AND WHAT IS YOURS. FIXED by the program: who acts and with which move; which parts are hit and how
  hard; whether an attack lands or misses; which grips and pins are on or off when the beat ends; who ends the
  beat on her feet, on the ground (and which way she lies, or sitting), or out. YOURS, every beat: how it gets
  there. The approach, the angle, the feint, what a grab catches hold of, footwork on bad ground, how a body
  twists, slides, skids, bounces or folds on the way to where it ends, what the arena does (spray, echo, grit,
  a loosened pebble), sounds, breath, looks, thoughts. A fighter who ends the beat on her feet may stumble, be
  driven back, catch herself on a wall, even touch a knee or a paw to the ground for an instant, as long as she
  is plainly up again before the beat ends. A fighter who is held or pinned may fight it in any way that fits
  her body, as long as the grip is as the notes say when the beat ends. When a note says "this time" or "one
  way", it is the program's pick for variety: tell it, in your own staging. When a note gives examples in
  brackets, they are only examples. Never trade a fixed fact for a better picture.
- Plain prose only: no headings, no "# Beat", no "From X's perspective:" labels, no horizontal rules.
- The MOVE decides how each hit lands: a body charge (Aqua Jet) hits with the whole body, a bite with teeth,
  a slash with claws, a tail move with the tail. Don't swap in claws or teeth the move doesn't use.
- Hits happen in the listed order: Hit 1 first, then Hit 2. A carry-over part is struck by the same motion,
  just after the main target.
- The moment of impact can be dramatic, but the LASTING state must match the pain level. Never call a part
  useless, ruined, broken, crushed, or dead, or have it drag or stop working, unless its lasting pain is
  EXCRUCIATING or DEVASTATED. "Hurting" means slower and guarded, not disabled.
- Only refer back to events that actually appear in PREVIOUS BEATS. Never mention past attacks, exchanges, or
  injuries that did not happen.
- Never predict or hint at outcomes the engine hasn't decided yet: no "there would be no escape", "she knew
  she'd lose", "this was over". Whether a pin holds or someone escapes is rolled later.
- Never invent attacks, falls, or events that aren't listed. (New attacks are created by the director so the
  engine can track them; anything you add would be untracked.) Make each listed attack feel distinct. Nobody dies, drowns, or disappears: the worst
  outcome is fainting.
- Never invent backstory, shared history, friendships, alliances, or signals between fighters that aren't in
  their descriptions. Fighters only cooperate if they are on the same team.
- When a beat lists several numbered actions, narrate them in that order, each with its own impact.
- Follow the author's TONE instructions on how graphic injuries may be. When in doubt, less graphic.
- OVERALL STRENGTH OUTRANKS PART PAIN (hard rule). CURRENT CONDITION gives each fighter an OVERALL strength and
  what they can still do. Part pain decides how that PART feels (screams, flinching, favoring it, not using
  it); overall strength decides how the WHOLE fighter copes. A fighter who is fresh or winded overall stays in
  the fight even with an agonizing part: knocked down, they get back up; hit hard, they recover within moments
  and keep attacking with everything else. Collapsing, going limp, being unable to rise, eyes rolling back, or
  losing consciousness are only for fighters who are spent or past the limit overall.
- Nobody blacks out, faints, or stays unconscious unless a pin has just been completed on them, or they lost the
  match and CURRENT CONDITION says they are still out cold or stirring. Even a
  fighter past the limit stays conscious: dazed, wobbling, dropping to the ground, but awake and trying.
- NO HEALING unless a recovery is listed in this beat: injuries never fade, close, or stop hurting on their own,
  nobody eats a berry or uses a healing move, and lost strength doesn't come back.
- NOTHING carries over unless CURRENT CONDITION or POSITIONS says so: no lingering grips, bites, locked jaws,
  or holds from earlier prose. If it isn't listed as a hold or pin, it has been let go.
- VOICES: each fighter's thoughts, cries, and any words follow their VOICE under FIGHTERS.
- THOUGHTS: give each fighter who acts or is hit at least one brief thought in italics (*like this*), in their
  own voice, reacting to what just happened: surprise, anger, a plan, stubbornness. Never a prediction of
  how the fight will end.
- REACTIONS: vary them and fit them to the species (see each fighter's TELLS): gasps, winces, eyes squeezing
  shut, ears pinning, tails lashing, breath hissing out, a stagger caught. Never the same reaction twice in a
  beat, and never the same opening image as the previous beat.

Craft:
- Third person, PAST tense ("she lunged", not "she lunges").
- INTENT: let the attacker read the opponent before striking: what she notices (a guarded side, a limb held
  wrong, a part nothing has touched yet), and why she picks that target. A long look, then the strike.
- CALLBACKS: when an injured part is hit again or aches, remember where that injury came from (CURRENT
  CONDITION says "from ..."), in a few words: the thigh her teeth had already found. Only real causes.
- BODY INVENTORY: after a big hit, walk through how the worst parts feel NOW, one after another, each in its
  own words, escalating with the pain level: a dull ache, then a building, spreading pressure, then sharp and
  hot, then pounding and sick, then past pain into numb, wrong quiet. Words only, never levels or numbers.
- RHYTHM: give the biggest moments a short paragraph of their own, sometimes a single line.
  Pile long, comma-linked sentences for sensation; cut to short, flat ones for impact and decisions.
- NO REFRAINS: never end two paragraphs, or two parts, on the same line or an echo of it ("The pin held." ...
  "And the pin held."), and never string one-word sentences together for effect ("Firm. Unbreakable. Complete.").
  One short line lands; three in a row are a tic. Each paragraph tells something the one before did not.
- PROPORTION: a light hit gets a wince and a line; only the worst gets a cry and a long passage. If every blow is
  shattering, none is. A blow on a part that is ALREADY badly hurt hurts far more than the same blow on a fresh part,
  and its note says how raw the reaction is: a fighter with most of her strength fights to keep it in; one who is
  spent cannot. A ruined part hurts at the slightest touch, though a brush there is still less than a real blow.
  Being worn down makes her rawer only WHERE she is badly hurt: a blow on a part that was NOT hurt still stings,
  jars what is round it, and is one more thing her trembling body didn't need, but it is not agony and she does
  not come apart over it. Screams, shaking and streaming eyes are allowed when the note asks; sobbing and weeping
  are not.
- CLEVERNESS: a fighter with no good options thinks; she uses the arena, her species' body (a flotation sac,
  a tail, a coil), and her opponent's injuries. Show the idea forming, then the attempt.
- Concrete physical detail: exactly where contact lands, weight, grip, texture, temperature, sound, breath,
  the specific quality of each pain (sharp, hot, deep, numb, grinding). Show it, don't announce it.
- Never write filler like "she knows she has to", "she feels the pain", "she does not falter", "but she
  is tough", "as fast as". Never repeat a sentence or image. Never stack the same phrase.
- Vary sentence length: short sentences for impacts, longer ones for sustained pressure and exhaustion.
- Stop when this beat's events are fully told.
"""

# EXTREME: always rewritten (unless gore_check is off): mutilation, exposed insides, broken bones, heavy blood,
# death, swearing.
GORE = re.compile(
    r"\b(gore|gory|guts|entrails|organs?|ruptur\w*|bone[- ]ends?|exposed bone|"
    r"sever(?:ed|ing|s)?|"
    r"(?:torn|tore|tearing|tear|ripp\w*|rip)\s+(?:through|into|from|clean from|away from|open)?\s*(?:the\s+)?(?:muscle|flesh|fat|tendon\w*|sinew)|"
    r"(?:muscle|flesh|sinew)\s+(?:tore|tears?|tearing|ripp\w*|separat\w*|split\w*|gave way|torn)|tissue separat\w*|"
    r"muscle and fat|gristle|wet (?:crunch|tearing)|bones? (?:poking|jutting|sticking) (?:out|through)|"
    r"holes? (?:in|through) (?:her|his|its|the)|open wounds?|gaping|gash\w* (?:open|to the bone)|"
    r"blood\w*(?:\s*[—–-]\s*|\s+)(?:[\w,]+(?:\s*[—–-]\s*|\s+)){0,4}(?:pool\w*|spray\w*|gush\w*|pour\w*|fountain\w*|splatter\w*|spurt\w*|soak\w*|flood\w*|stream\w*)|"
    r"pools? of blood|covered in blood|soaked in blood|blood loss|bled out|vomit\w*|retch\w*|puk(?:e|ed|ing)\b|throw(?:s|ing)? up\b|threw up\b|"
    r"corpse|dead body|(?:was|is|lay|lies|she's|he's) dying|to (?:her|his|its) death|death|kill(?:s|ed|ing)?|"
    r"charred flesh|skin (?:bubbl\w*|peel\w*)|"
    r"split (?:it |her |the |\w+ )?(?:nearly |almost |half ?way |halfway )?(?:clean )?(?:through|in two|apart)|"
    r"(?:wet )?ripping sound|tear\w* (?:through|open) (?:the )?(?:webbing|skin|fur and|her)|torn (?:open|skin)|"
    r"(?:shape|limb|arm|leg|paw|shoulder|joint|fin|tail) (?:\w+ ){0,3}(?:distorted|deformed|misshapen)|"
    r"distorted beyond|misshapen|deformed|"
    r"open(?:ing|ed|s)? (?:up )?(?:the )?(?:fur and )?(?:the )?flesh|flesh beneath in|teeth (?:went|sank|sunk|tore) "
    r"(?:right )?through (?!(?:the |her |his |its )?(?:thick |white |wet |dense )?(?:fur|ruff|scales|hide|coat))|bones? (?:\w+ )?grinding|splintering|"
    r"shredd\w*|detach\w*|pulp(?:ed|y)\b|torn (?:edges?|face|ears?|muzzle|nose|lips?|fur and)|tearing through (?:the |her |his )?(?:\w+(?:'s|’s) )?(?:sac|surface|"
    r"tissue|hide|membrane)|(?:muzzle|nose|ear|face|jaw|paw|tail) was gone\b|teeth met bone|(?:strands|threads|ribbons) of (?:muscle|skin|tissue|sinew|flesh)|"
    r"pop of cartilage|cartilage (?:gave|yield\w*|snapp\w*|crack\w*|tore)|"
    r"no longer breathing|(?:never|not) (?:breathe|breathing) again|breathing (?:had )?stopped (?:for good|entirely|completely)|"
    r"stopped breathing (?:for good|entirely|completely)|lifeless|(?:I|she|he|you|we)(?:'ll| will| would| could)? die|"
    r"(?:was|is|lay|looked|she's|he's) dead|"
    r"(?!x)x)\b", re.I)

# SWEARING: allowed rarely by default (narration.swearing: "rare" | "never" | "free")
SWEAR = re.compile(r"\b(fuck\w*|shit\w*|bitch\w*|bastard\w*|god ?damn\w*|damn(?:it|ed)?|dammit|crap|"
                   r"(?:the|to|like|bloody|what the) hell|hell (?:no|yes|of a))\b", re.I)

# MILD: allowed by default (gore_level "mild"); only rewritten when gore_level is "none".
MILD_GORE = re.compile(
    r"\b(blood\w*|bleed\w*|bloody|wounds?|wounded|punctur\w*|lacerat\w*|cuts?|split (?:lip|skin)|"
    r"seep\w*|ooz\w*|weeping|fluid|froth\w*|taste[sd]? (?:of )?(?:copper|iron|blood)|copper(?:y)? taste|metallic tang|"
    r"tang of (?:copper|iron)|smell of iron|(?:into|through) (?:the )?(?:soft |tender |raw )?flesh|skin (?:split\w*|tore|torn)|"
    r"blister\w*|(?:audible|sickening|wet) (?:crack|pop|snap|sound)|audible pops?|"
    r"flesh part\w*|fib(?:er|re)s? (?:\w+ )?(?:separat|part|tear|tore|split|ripp)\w*|"
    r"(?:tearing|tore|ripping) (?:\w+ )?through (?:the )?(?:muscle|tissue|tendon)\w*|audible tear|"
    r"tendons? (?:\w+ ){0,3}(?:tore|tear\w*|gave|giving|snapp\w*|rupt\w*)|bone (?:\w+ )?(?:giving|gave) way|"
    r"(?:popped|cracked) in (?:her|his|its) neck|"
    r"rib\w*\s+crack\w*|crack\w*\s+(?:a\s+|her\s+|the\s+)?rib\w*|bone\s+(?:shifted|gave|bruis\w*)|hairline|"
    r"foam\w*(?: \w+)? (?:at|around|from|on) (?:her|his|its|the) (?:mouth|jaws?|lips|muzzle))\b", re.I)


# SEVERE BONE DAMAGE: allowed only in a sentence about a part that may break (devastated, on a fighter whose
# overall health is below the limit); anywhere else it is rewritten.
BONE_SEVERE = re.compile(
    r"\b(shatter\w*|fractur\w*|splinter\w*|broken (?:bones?|limbs?|legs?|arms?|ribs?|forelegs?|jaw|tail|fin)|"
    r"bones? (?:\w+ )?(?:snapp\w*|snap|broken|broke|break\w*|grind\w*|ground)|at (?:an? )?(?:\w+ )?angle that|"
    r"(?:completely|totally|clearly|definitely) broken|like a (?:\w+ )?(?:branch|stick|twig) (?:breaking|snapping|cracking)|(?:snapp\w*|broke) (?:the |her |his )?bone|"
    r"bone grinding|grinding bone|bone against bone|bones? (?:grating|scraping|grinding|rasping) (?:against|on) bone|scraping bone|scrape[sd]? (?:against )?bone|bone yield\w*|"
    r"(?:an? )?(?:unnatural|impossible|sickening|wrong) angle|bent (?:back(?:ward)?|wrong)|bending wrong|"
    r"joints? that (?:shouldn't|should not) bend|something (?:\w+ ){0,3}(?:snapped|cracked|broke)|cartilage (?:grind|pop)\w*|neck snapp\w*|"
    r"something (?:\w+ ){0,2}gave(?: way)?\b|gave (?:way )?with a (?:\w+ )?(?:pop|crack|snap|crunch)|(?:a |the )?sound like "
    r"(?:splitting|snapping|breaking|cracking)|joint (?:twist\w+|popp\w+|gave)|(?:shifted|sat|moved|twisted) wrong|"
    r"(?:wet|sickening|sharp) (?:pop|crack|snap|crunch)\b|bones? (?:\w+ )?(?:give|gave|giving|given) way|"
    r"joints? (?:had |has )?(?:given|gave|give) way|a snap (?:she|he) could (?:hear|feel)|"
    r"felt something (?:\w+ ){0,2}(?:shift|give|snap|pop|tear)\b|(?:tremendous|loud|sharp|sickening) CRACK|"
    r"something (?:\w+ ){0,4}(?:giving|gives|give) way|"
    r"something (?:deep )?(?:in|inside|under|beneath|behind) (?:her|his|its|the) (?:\w+ ){1,3}(?:buckl\w+|gave|snapp\w+|"
    r"crack\w+|broke|popp\w+|crunch\w+|crumpl\w+|collaps\w+)|"
    r"(?:muzzle|snout|nose|jaw|skull|cheek(?:bone)?s?|face|ribs?|ribcage|sternum|spine|horn|eye socket|brow) "
    r"(?:\w+ ){0,2}(?:gave way|caved(?: in)?|buckled in(?:ward)?|folded in(?:ward)?|collapsed in(?:ward)?|crumpled in(?:ward)?|"
    r"crack\w* sideways|was (?:gone|ruined|wrecked|destroyed))|"
    r"(?:an? |the )?audible (?:snap|crack|pop|crunch)|with an? (?:\w+ )?(?:snap|crunch) of (?:bone|cartilage))\b",
    re.I)


def gore_pattern(rules):
    """The tone check for this setting: None (off), extreme only ("mild", default), or everything ("none")."""
    n = rules.get("narration", {})
    if not n.get("gore_check", True) or str(n.get("gore_level", "mild")).lower() == "off":
        return None
    if str(n.get("gore_level", "mild")).lower() == "none":
        return re.compile(GORE.pattern + "|" + MILD_GORE.pattern + "|" + BONE_SEVERE.pattern, re.I)
    return GORE


# reactions the narrator leans on; the tracker tells it which ones the last beats already used
REACTIONS = {
    "silent scream": r"silent (?:scream|cry|howl)|scream\w* (?:without|with no) (?:sound|voice)|mouth (?:\w+ ){0,2}open\w* (?:in|on|around) a",
    "back arching": r"(?:back|body|spine) (?:\w+ )?arch\w*|arch\w* (?:off|away from|against)",
    "limbs rigid": r"(?:limbs?|legs?|body) (?:\w+ )?(?:went|going|gone) rigid|every limb",
    "ears pinned/flattened": r"ears? (?:\w+ )?(?:pinn|flatten|press)\w*|(?:pinn|flatten)\w* (?:her |its )?ears?",
    "eyes squeezed shut": r"eyes? (?:\w+ )?squeez\w*|squeez\w* (?:her |its )?eyes",
    "eyes narrowing": r"eyes? narrow\w*|narrow\w* (?:her |its )?eyes",
    "hackles rising": r"hackles",
    "tail lashing": r"tail\w* (?:\w+ )?lash\w*|lash\w* (?:her |its )?tail",
    "growl/snarl": r"growl\w*|snarl\w*",
    "hiss": r"hiss\w*",
    "gasp": r"gasp\w*",
    "whimper/whine": r"whimper\w*|whin(?:e|ed|ing)\b",
    "teeth gritted/clenched": r"(?:grit|clench)\w* (?:her |its )?teeth|teeth (?:\w+ )?(?:grit|clench)\w*",
    "flotation sac deflating/puffing": r"sac (?:\w+ )?(?:deflat|puff|inflat|collaps)\w*",
    "forearm fins flaring/clamping": r"fins? (?:\w+ )?(?:flar|clamp|flatten|snapp)\w*",
    "throat working/swallowing": r"throat (?:\w+ )?(?:work|bobb)\w*|swallow\w*",
    "chin tucked": r"(?:tuck\w* (?:her |its )?chin|chin (?:\w+ )?tuck\w*)",
    "tails stuttering": r"tails? (?:\w+ )?stutter\w*",
    "antennae drooping/stiffening": r"antenna\w* (?:\w+ )?(?:droop|snap|stiff|went rigid)\w*",
    "breath hitching/catching": r"breath (?:\w+ )?(?:hitch|catch|caught)\w*",
    "staggering/stumbling": r"stagger\w*|stumbl\w*",
    "wincing": r"winc\w*",
    "trembling/shaking": r"trembl\w*|shudder\w*",
    "lips peeling back": r"lips? (?:\w+ )?peel\w*",
    "yelp/cry out": r"yelp\w*|cried out|cry(?:ing)? out",
    "scream": r"scream\w*",
}
_REACTION_RX = {k: re.compile(r"\b(?:" + v + r")", re.I) for k, v in REACTIONS.items()}


def reactions_used(text):
    return {k for k, rx in _REACTION_RX.items() if rx.search(text or "")}


# whole-body collapse: only for fighters who are spent or past the limit overall
COLLAPSE = re.compile(r"\b(went (?:limp|slack)|go(?:es|ing)? limp|lay (?:limp|motionless|still)|collaps\w*|"
                      r"(?<!face )(?<!expression )(?<!features )(?<!brow )crumpl\w*|eyes rolled back|blacked out|lost consciousness|passed out|"
                      r"(?:couldn't|could not|can't) (?:get up|rise|stand|move)|consciousness (?:slipp\w*|tried to slip|waver\w*|fad\w*|"
                      r"flicker\w*|dimm\w*)|(?:nearly|almost) (?:passed|blacked) out)\b", re.I)

# falling down (allowed only for fighters the program actually has on the ground)
FALL = re.compile(r"\b(collaps\w+ (?:backward |back |forward |sideways |face-first |down )?(?:into|onto|in|on) (?:the|a) |went down|go(?:es|ing)? down hard|fell (?:back|over|hard|to the|onto|on|sideways|backward|into (?:the |deeper |the deeper )?(?:water|pool|channel))|toppl(?:ed|ing|es)|went sprawling|"
                  r"flew (?:backward|back|sideways)s? (?:into|onto|across|through)|landed (?:hard |heavily )?on (?:her|his) "
                  r"(?:back|side|belly|stomach|front|rump|haunches)|(?:hit|hitting) the (?:water|pool) with|"
                  r"(?:sent|sending) (?:her|him) (?:flying|sprawling|tumbling)|"
                  r"tumbl(?:ed|ing|es) (?:to the (?:left|right|side|ground|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss)|backward|back|sideways|over|across|into|onto|away)|"
                  r"crash(?:ed|ing)? (?:forward |backward |back |down |sideways |hard )*(?:onto|on) (?:her|his) (?:side|back|belly|"
                  r"stomach|front|face)|"
                  r"crash(?:ed|ing)? (?:[\w-]+ )?(?:to|onto|into) (?:the )?(?:\w+ )?(?:ground|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|stone|rock|ledge|pool|water|channel)|"
                  r"face-(?:down|first) (?:on|onto|into|in)|knees? buckl\w*|"
                  r"(?<!jet )(?<!stream )(?<!blast )(?<!spray )\b(?:hit|struck) the (?:\w+ )?(?:ground|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|water|pool|stone) hard|"
                  r"hammer\w* (?:her|him) down|(?:tried|trying|struggl\w+|fought|failed) to (?:push|get|haul|drag|lever) "
                  r"(?:herself|himself) (?:back )?(?:up|upright)|to push (?:herself|himself) upright|"
                  r"pin(?:ned|ning)? (?:her|him|(?:her|his) \w+(?: \w+)?) (?:down|against the (?:\w+ )?(?:pool|stone|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|ground|ledge))|(?:slamm|knock|dropp|dragg)\w* (?:her|him) (?:down )?(?:onto|to) the (?:\w+ )?"
                  r"(?:ground|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|stone|rock|ledge)|went out from under|lay there\b|hit the (?:ground|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss)|knocked (?:off (?:her|his) feet|flat)|sprawl(?:ed|ing)|"
                  r"(?:her|his) (?:left |right )?(?:head|hip|side|back|flank|shoulder|ribs) (?:struck|hit|slammed into|crashed into|smacked) "
                  r"(?:the |a )?(?:\w+ )?(?:rock|stone|floor|ground|water|pool|stalagmite|wall|boulder|ledge|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|pillar|column|trunk|tree|pipes?|railing|hull|crates?|turbine|housing|cart|timbers?|props?|statue|cliff|log|logjam|bell|gears?|derrick|cactus|crystals?)|"
                  r"(?:lay|lying|sprawled) (?:half )?(?:in|on|across) the (?:water|pool|ledge|stone|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|ground))\b", re.I)


# signs of a NEW wound being dealt (for fighters nothing hit this beat)
HURT_NEW = re.compile(r"\b(felt (?:the|those) (?:claws?|teeth|fangs|tips|talons|blade|blow|strike|impact)|"
                      r"(?<!her )(?<!his )(?<!own )(?:claws?|teeth|fangs|tips|talons|blade)\s+(?:\w+\s+)?"
                      r"(?:scraped?|raked?|tore|sank|bit|grazed?|sliced?|cut|slashed?|caught)\s+(?:across|into|through|along)\s+(?:her|his)|"
                      r"(?:skin|fur|flesh|hide|scales?) (?:split|tore|parted)|split in (?:\w+ )?(?:thin )?lines|"
                      r"where (?:those|the|\w+'s) (?:claws|teeth|fangs|talons) had|fresh (?:wounds?|cuts?|gashes))", re.I)

# electricity in a beat that has no Electric move
ELECTRIC = re.compile(r"\b(electric\w*|electrif\w*|lightning|voltage|volts?|static (?:charge|crackl\w*)|current (?:pour|surg|crackl|ran|"
                      r"flood)\w*|sparks? (?:flew|danced|crackl\w*|arced)|crackl\w* with (?:power|energy|charge))\b", re.I)


def degeneration_run_on(x):
    """A sentence that has turned into a dash-chained run-on (long sentences alone are fine)."""
    words = x.split()
    n = len(words)
    if n > 120:
        return True
    arts = sum(1 for w in words if w.lower().strip(".,;:—-") in ("the", "a", "an"))
    chained = x.count("—") + x.count(" - ") >= 2 or x.rstrip().endswith(("—", "-"))
    return n > 40 and chained and arts / n < 0.04  # long, dash-chained, and dropping its articles


def _ngrams(text, n=7):
    words = re.findall(r"[a-z']+", (text or "").lower())
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def degeneration(text, earlier=""):
    """Signs a local model's prose is breaking down: run-on chains, dropped articles, copied phrases.
    Returns a list of short descriptions (empty if the prose looks healthy)."""
    out = []
    words = re.findall(r"[A-Za-z']+", text)
    sents = [x for x in re.split(r"(?<=[.!?…])\s+|\n+", text) if x.strip()]
    long_ = [x for x in sents if degeneration_run_on(x)]
    if long_:
        out.append(f"{len(long_)} run-on sentence(s) chained with dashes (\"{' '.join(long_[0].split()[:12])}…\")")
    if len(words) >= 120:
        arts = sum(1 for w in words if w.lower() in ("the", "a", "an"))
        if arts / len(words) < 0.03:
            out.append("telegraphic wording that drops 'the' and 'a'")
    if earlier:
        copied = _ngrams(text) & _ngrams(earlier)
        if len(copied) >= 3:
            out.append(f"whole phrases copied from earlier in the story (\"{sorted(copied)[0]}…\")")
    dash_end = sum(1 for p in text.split("\n") if p.strip().endswith(("—", "-")))
    if dash_end >= 3:
        out.append("paragraphs that trail off on a dash instead of ending")
    return out


# a fighter shown lying on the ground (the state, not the fall): wrong for anyone the program has on her feet
GROUNDED = re.compile(
    r"\b((?:lay|lying|lies) (?:curled|sprawled|crumpled|slumped|flat|still|there|motionless|on (?:her|his) "
    r"(?:left |right )?(?:side|back|belly|stomach|front)|(?:half )?in the (?:water|pool|shallows|channel))|"
    r"curled (?:up )?on (?:her|his) (?:left |right )?side|flat on (?:her|his) (?:back|belly|stomach|face)|"
    r"(?:lay|lying) (?:soaked|trembling|gasping|panting|limp|helpless|dazed|stunned|winded|prone|shaking|shivering|"
    r"dripping|bleeding|broken|beaten)\b|\bprone (?:form|body|figure)|pulled (?:herself|himself) (?:up|upright|to (?:her|his) "
    r"feet|back up)|"
    r"(?:can't|couldn't|could not|cannot) (?:even )?(?:stand|rise|get up)|"
    r"(?:tried|trying|tries|struggl\w+|fought|fighting) to (?:roll|sit up|rise|stand|get (?:back )?up|"
    r"(?:push|lever|drag|haul) (?:herself|himself) (?:back )?(?:up|upright))|"
    r"roll(?:ed|ing|s)? onto (?:her|his) (?:left |right )?(?:side|back|belly|stomach|front)|"
    r"from where (?:she|he) lay|(?:still|already|was|is|stayed) on the (?:ground|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss)|"
    r"(?:\b[Ss]he|\b[Hh]e|(?-i:[A-Z])\w+) got (?:back )?up\b(?! to| on| close| in)|got (?:back )?to (?:her|his) feet|picked (?:herself|himself) up|"
    r"(?:pushed|levered|dragged|hauled) (?:herself|himself) (?:back )?(?:up|upright|to (?:her|his) feet)|"
    r"(?:\b[Ss]he|\b[Hh]e|[Tt]he (?-i:[A-Z])\w+|(?-i:[A-Z])\w+) (?:was|is|stayed) (?:still |already )?down\b"
    r"(?! to| on| at| in| by| from| low| and out))", re.I)

# someone held down or stood over: wrong in a beat with no pin and nobody on the ground
PINNED_SAID = re.compile(
    r"\b((?:stood|standing|stands|crouched|crouching) over (?:her|him|the \w+)|"
    r"(?:struggl|squirm|writh|thrash|trapp|pinn)\w* (?:beneath|underneath|under) (?:her|him|the \w+)|"
    r"pinned (?:down|to the)|"
    r"(?:was|were|been|being|lay|stayed|still) pinned(?! (?:back|flat|flush|tight|close|useless|to (?:her|his) "
    r"(?:skull|head|neck|side|chest|body)|against (?:her|his) (?:skull|head|neck|side|chest|body)))|"
    r"(?:had|has) pinned (?:her|him)\b|pin(?:s|ned|ning) (?:her|him)(?=[.,;:!?—]|\s+(?:down|to|against|there|in place)\b)|"
    r"held (?:her|him) down|hold(?:s|ing)? (?:her|him) down|the pin (?:held|holds|tightened))\b", re.I)


# sliding or crumpling to the ground (wrong for a fighter who was driven into the scenery but kept her feet)
SLID_DOWN = re.compile(r"\b((?:slid|slides|sliding|sank|sinks|sinking|slump\w*|crumpl\w*|collaps\w*|dropp\w*|fold\w*|"
                       r"fell|falls) (?:limply |bonelessly |slowly |heavily |down )*(?:down (?:the|its|it)\b|to the (?:ground|"
                       r"floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|stone|water|base)|onto the (?:ground|floor|stone)|(?:in|into) a heap|at (?:the|its) (?:foot|"
                       r"base))|crumpled\b|in a heap\b)", re.I)

# one strike told as several
EXTRA_SWING = re.compile(r"\b((?:struck|strikes|hit|hits|slashed|slashes|swung|swings|lashed out|raked|whipped|whips|snapped|"
                         r"cracked|swept|slammed|smashed|hammered|chopped|stabbed|kicked|came (?:down|around|back|in)) "
                         r"(?:(?:her|him|out|down|around|back|in) )?again|(?:wasn't|was not) (?:finished|done)\b|"
                         r"then (?:she|he) struck|this time (?:she|he) (?:aimed|went|struck)|"
                         r"(?:a |the |her |his )(?:second|third) (?:blow|strike|slash|swipe|swing|rake|hit|cut)|"
                         r"(?:two|three|four) (?:quick |fast |brutal |savage )?"
                         r"(?:blows|strikes|slashes|swipes|rakes|hits)|struck (?:twice|three times))\b", re.I)

# after an escape: words that put her back under the pin
STILL_PINNED = re.compile(r"\b((?:arms?|legs?|chest|shoulders?|hips?|body|back|neck|tails?) (?:was |were |still |stayed )*"
                          r"pinned(?! (?:back|flat))|(?:still|again|stayed|remained|lay) pinned|pinned (?:her|him) "
                          r"(?:down )?again|the pin (?:held|holds|tightened|clamped)|(?:forc|clamp|slamm)\w+ the pin back|"
                          r"back (?:under|beneath) (?:her|him|the))\b", re.I)


# which way someone lies, for the facing check
SAYS_FACE_UP = re.compile(r"\b(on (?:her|his) back|face-up|belly-up|stared? up at|staring up at|looking up at the "
                          r"(?:ceiling|stalactites)|pinned on (?:her|his) back)\b", re.I)
SAYS_FACE_DOWN = re.compile(r"\b(face-?down|face-first|on (?:her|his) (?:belly|stomach|front)|face (?:pressed|ground|"
                            r"mashed|shoved) (?:into|against)|(?:face|muzzle|cheek) (?:in|into|against) the (?:water|stone|"
                            r"floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|rock|pool)|chest (?:pressed|crushed|flat) (?:against|to|into) the (?:stone|floor|ground|rock))\b", re.I)
SAYS_SITTING = re.compile(r"\b(sat (?:up|upright|slumped|propped|there|back|hard|down hard|against)|sitting (?:up|upright|"
                          r"against|there|slumped|propped|on|in|at)|(?:was|ended|stayed|remained|left) sitting|ended (?:up )?"
                          r"sitting|on (?:her|his) haunches|propped (?:upright|up|against)|slumped (?:upright )?against)\b", re.I)
SAYS_FLAT = re.compile(r"\b((?:lay|lying|sprawled) (?:flat|sprawled|there|still|on (?:her|his) (?:side|back|belly|front|"
                       r"stomach|flank)|face-?(?:down|up)|in a heap|where she)|flat on (?:her|his) (?:back|belly|stomach|"
                       r"front|side)|face-?down (?:on|in)|crumpled (?:in a heap|on (?:her|his) side)|stretched out on)\b", re.I)
LIFTING = re.compile(r"\b(haul\w*|lift\w*|hoist\w*|heav\w* (?:her|him) up|pick\w* (?:her|him) up|pull\w* (?:her|him) up|"
                     r"prop\w* (?:her|him)|sat (?:her|him) up|(?:onto|to) (?:her|his) feet|upright|"
                     r"dragg?\w* (?:her|him) up|(?:off|up from) the (?:ground|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|stone|water|pool)|by the scruff)\b", re.I)
MANHANDLED = {
    "throw": re.compile(r"\b(threw|thrown|throw\w*|hurl\w*|flung|fling\w*|toss\w*|heav\w*|launch\w*|sent (?:her|him) "
                        r"(?:flying|tumbling|sailing|skidding|crashing)|pitch\w*|swung (?:her|him)|whip\w* (?:her|him))\b", re.I),
    "slam": re.compile(r"\b(slam\w*|drove (?:her|him)|driv\w* (?:her|him)|smash\w*|dump\w*|spik\w*|brought (?:her|him) "
                       r"(?:crashing )?down|dropp\w* (?:her|him)|crash\w*)\b", re.I),
    "drag": re.compile(r"\b(drag\w*|haul\w*|pull\w*|tow\w*|tug\w*|scrap\w*|yank\w*|drew (?:her|him))\b", re.I),
}
# --- slips seen in the build 100 logs ---
# "pinned" said of a fighter when no pin and no hold exists (ears pin flat; pain can pin: those are fine)
PINNED_FREE = re.compile(r"\b(pinned|pinning (?:her|him)|pins (?:her|him)|held (?:her|him) down|holding (?:her|him) down)\b", re.I)
PINNED_OK = re.compile(r"\bears?\b[^.!?;]{0,25}\bpinn|\bpinn(?:ed|ing) (?:(?:her|his|both|its) )?ears|\bpinned (?:flat|back|tight|close)\b|"
                       r"\bpinned (?:by|with|under) (?:pain|fear|exhaustion|shock|dread|the cold|the weight of (?:her|his) own|"
                       r"(?:her|his) own|nothing)|\b(?:as if|as though|like (?:a|something|someone)) pinned|\bpinned "
                       r"(?:her|him|the \w+) with (?:a |her |his )?(?:look|stare|glare|gaze|eyes)|\b(?:not|never|wasn't|isn't) "
                       r"pinned|\bpinned (?:her|his) (?:gaze|eyes|stare)", re.I)
# the whole body giving out, said of a fighter who still has most of her strength
LIMP_BODY = re.compile(r"\b(?:she|he|(?:her|his) (?:whole )?body|[A-Z][\w-]+(?:'s|’s|'|’) (?:whole )?body|[A-Z][\w-]+|the "
                       r"[A-Z][\w-]+)\s+(?:went|goes|had gone) (?:limp|slack|boneless)\b|\b(?:couldn(?:'|’)t|could not|"
                       r"can(?:'|’)t|cannot|unable to) move\b(?!\s+(?:her|his|the|a|an|it|that|them|one|either|any)\b)", re.I)
# a part breaking (allowed only where CURRENT CONDITION says it can)
PART_BROKE = re.compile(r"\b(?:nose|ribs?|jaw|legs?|arms?|paws?|tail|horn|skull|muzzle|hip|shoulder|knee|ankle|wrist|foreleg|"
                        r"spine|cartilage|\w+bone)\b[^.!?;]{0,22}?(?:[—–-]+\s*)?\b(?:broke|broken)\b(?!\s+(?:free|loose|away|"
                        r"off|out|into|through|the|from|in a|across|against|her|his|its)\b)|\bbroke further\b", re.I)
# a fresh crack or pop (as opposed to remembering one)
CRACK_NOW = re.compile(r"\b(?:cracked|cracking|popped|popping)\b", re.I)
PAIN_NOW = re.compile(r"\b(?:hurting|ach(?:ed|ing)|throbb(?:ed|ing)|scream(?:ed|ing)|burn(?:ed|ing)|blaz(?:ed|ing)|flar(?:ed|ing)|"
                      r"on fire|agony)\b", re.I)
# a hit landing (for "the same blow told twice")
IMPACT_NOW = re.compile(r"\b(?:struck|hit|raked|slammed|crashed|smashed|hammered|caught|landed|tore|ripped|sank|connected|"
                        r"slashed|sliced|bit|drove|exploded (?:with|in) pain|erupted (?:with|in) pain)\b", re.I)
RECALLED = re.compile(r"\b(?:had|where|which|that|when|since|after|from|earlier|already|still|again)\b", re.I)
# a blow driven into a named part ("drove her knee up into Nocturne's belly")
BLOW_INTO = re.compile(r"\b(?:drove|driving|slamm\w+|smash\w+|ramm\w+|kick\w+|punch\w+|hammer\w+|stomp\w+|stamp\w+|sank|"
                       r"buried|rak\w+|slash\w+)\b[^.!?;]{0,40}?\b(?:into|against|across|onto|down on)\s+(?:the |her |his |"
                       r"[A-Z][\w-]+(?:'s|’s|'|’) )(?:(?:left|right|upper|lower|exposed|soft|unprotected|white|cream) )*"
                       r"([a-z]+)", re.I)
# a tail or coil that is wrapped round someone can't also be spinning free
FREE_TAIL = re.compile(r"\b(?:tails?|coils?)\b[^.!?;]{0,30}\b(?:spinn?ing|spun|spin|whirl\w*|churn\w*|propell\w*|lash\w*|"
                       r"whipp\w*)\b", re.I)
# body words anyone has, whatever the species (the rest of a fighter's part names are hers alone)
COMMON_BODY = {"left", "right", "upper", "lower", "back", "belly", "stomach", "throat", "neck", "rib", "ribs", "knee", "foot",
               "feet", "arm", "leg", "cheek", "flank", "paw", "paws", "hand", "hip", "thigh", "shoulder", "chest", "head",
               "ear", "jaw", "nose", "muzzle", "tail", "tails", "base", "twin", "hind", "forepaw", "foreleg", "forearm",
               "side", "spine", "face", "eye", "eyes", "mouth", "lip", "skull", "body"}
# a count the story gives ("been thrown—twice—", "had pinned her a second time"): checked against the fight so far
_CNT_WORD = (r"(?P<c{0}>twice|two times|three times|thrice|four times|five times|a second time|a third time|a fourth time|"
             r"for the (?:second|third|fourth|fifth) time|again and again|over and over|time and again|time after time)")
_CNT_GAP = r"(?:\s*[—–-]+\s*|\s*,\s*|\s+(?:[^\s.!?;,—–]+\s+){{0,{0}}}?)"
COUNT_CLAIM = re.compile(
    r"\b(?:been|was|were|got|gotten|being)\s+(?:just\s+|already\s+|now\s+)?"
    r"(?P<v1>thrown|tossed|hurled|flung|slammed|pinned|dragged|floored|knocked (?:down|flat|off (?:her|his) (?:feet|paws))|"
    r"taken (?:down|off (?:her|his) (?:feet|paws))|put (?:down|on (?:her|his) back))"
    + _CNT_GAP.format(5) + _CNT_WORD.format(1) + r"\b"
    r"|\b(?:had|has|'d|’d)\s+(?:just\s+|already\s+|now\s+)?(?P<v2>thrown|tossed|hurled|flung|slammed|pinned|dragged|floored|"
    r"knocked)\s+(?:her|him|the \w+|[A-Z][\w-]+)(?:\s+(?:down|flat))?" + _CNT_GAP.format(4) + _CNT_WORD.format(2) + r"\b", re.I)
_CNT_N = {"twice": 2, "two times": 2, "a second time": 2, "for the second time": 2, "three times": 3, "thrice": 3,
          "a third time": 3, "for the third time": 3, "four times": 4, "a fourth time": 4, "for the fourth time": 4,
          "five times": 5, "for the fifth time": 5}
_CNT_KINDS = (("thrown", ("thrown", "slammed")), ("tossed", ("thrown", "slammed")), ("hurled", ("thrown", "slammed")),
              ("flung", ("thrown", "slammed")), ("slammed", ("slammed", "thrown", "charged")), ("pinned", ("pinned",)),
              ("dragged", ("dragged",)), ("", ("down",)))
# one part said to have the worst of it
WORST_OF = re.compile(r"\b(?:bore|took|caught|got|had|taking|bearing|bears|takes) the (?:worst|brunt)\b|"
                      r"\b(?:hurt|ached|throbbed|burned|screamed) (?:the )?(?:worst|most)\b", re.I)
# a grip pressing (for "the same pressing told again")
PRESS_VERB = re.compile(r"\b(?:press\w*|dig(?:s|ging)?|dug|driv\w+|drove|clamp\w*|tighten\w*|squeez\w*|s[aiu]nk|sinking|"
                        r"bore down|bear(?:ing|s)? down|lean\w*|grind\w*|ground|crush\w*|bit(?:ing|es)? down|anchor\w*)\b", re.I)
GRIP_NOUNS = (("jaws", r"jaws?|teeth|fangs?|bite"), ("paws", r"paws?|spikes?|dewclaws?|claws?|feet|foot|hands?"),
              ("tails", r"tails?|coils?"), ("weight", r"weight|bulk|body"))
# after she passes out under a pin: the pinner holding on a moment longer to be sure, and then letting go
HELD_ON = re.compile(r"\b(?:did(?:n't|n’t| not) (?:let go|release|ease|loosen|lift|move|trust)|held (?:on|it|her|the|a moment|another|"
                     r"for|there|still|longer|fast)|kept (?:her|the|it|them|that|hold|still)\b|stayed (?:on|where|there|put|"
                     r"clamped|locked|closed)|waited|a (?:moment|breath|heartbeat|second|beat|little) longer|"
                     r"(?:one|two|three|a few|several) (?:more )?(?:breaths?|heartbeats?|moments?)|to (?:be|make) (?:sure|"
                     r"certain)|in case|trick\w*|feint\w*|fak(?:e|ed|ing)|playing (?:dead|possum)|pretend\w*|ruse|"
                     r"test(?:ed|ing)|only then|not yet)\b", re.I)
FREED_HER = re.compile(r"\b(?:let (?:her |it |them )?go|releas\w+|eas(?:ed|ing|es) (?:off|her|back|up|away)|loosen\w*|"
                    r"opened her jaws|jaws (?:opened|parted|came away)|unclamp\w*|uncoil\w*|unwound|unwrapp\w*|lift(?:ed|ing) "
                    r"(?:her|herself|away|off)|stepped (?:off|back|away)|drew back|backed (?:off|away)|slid off|climbed off|"
                    r"rolled off|pulled (?:back|away)|withdrew|got off|rose (?:off|from))\b", re.I)
# the notes' own wording, copied into the story
BEAT_WORD = re.compile(r"\b(?:this|next) beat\b", re.I)
# a reaction left in the prose as a stage direction between dashes: "her thigh slammed into the wall—grunt—and..."
STAGE_WORD = re.compile(r"\s*[—–]\s*(?:a |an )?(?:choked |sharp |startled |ragged |surprised |strangled )?(?:grunt|hiss|gasp|"
                        r"wince|yelp|huff|groan|whimper|flinch|snarl|cry)\s*[—–]\s*", re.I)
# a blow that is told as missing
MISSED_HER = re.compile(r"\b(miss(?:ed|es|ing)|nothing but (?:air|water|spray)|(?:cut|caught|struck|hit|found|bit|raked|"
                        r"slashed|closed on) (?:nothing|only (?:air|water|stone|fur)|empty air)|(?:hissed|whistled|"
                        r"swept|passed|went|sailed|slid|flashed) (?:harmlessly )?(?:past|over|wide of|short of)|a (?:hair|"
                        r"whisker)(?:'s breadth)? from|wide of (?:her|his)|without touching)\b", re.I)
# a fall that doesn't happen: "almost went down", "her knees buckled, but she caught herself"
NEARLY = re.compile(r"\b(nearly|almost|all but|threatened to|about to|close to|came close to|would have|might have|"
                    r"did not|didn't|refused to|wouldn't|would not|not going to|instead of)\b[^.;]*$", re.I)
RECOVERED = re.compile(r"\b(caught (?:herself|himself)|kept (?:her|his) (?:feet|footing|balance)|stayed (?:up|upright|standing|on "
                       r"(?:her|his) feet)|(?:locked|straightened) (?:her|his|them|again)|held (?:her|him) up|"
                       r"(?:pushed|shoved|forced|hauled|levered) (?:herself|himself) (?:back )?(?:up|upright)|righted "
                       r"(?:herself|himself)|steadied|found (?:her|his) (?:feet|footing|balance)|got (?:her|his) (?:legs|"
                       r"feet|paws) (?:back )?under (?:her|him)|did not (?:fall|go down)|didn't (?:fall|go down)|"
                       r"refused to (?:fall|go down|fold)|back on (?:her|his) feet|stood again|was up again)\b", re.I)
ROLLING = re.compile(r"\b(roll\w*|flip\w*|turn\w* over|twist\w* onto)\b", re.I)


# signs that a fighter is back on her feet
STANDING = re.compile(r"\b(on (?:her|his|its) (?:feet|paws|legs)|(?:stood|stands|standing|upright)|got (?:up|to (?:her|his) "
                      r"feet)|made it up|hauled (?:herself|himself) up|(?:rose|risen) (?:to|up|unsteadily|shakily)|"
                      r"back up|to (?:her|his) feet|(?:regained|found|kept) (?:her|his) (?:feet|footing)|"
                      r"(?:pushed|levered|dragged|pulled|forced) (?:herself|himself) (?:up|upright)|was up)\b", re.I)


# signs of more than one attempt at getting up
GETUP_RETRY = re.compile(r"\b(third time|second (?:time|try|attempt)|(?:try|tries|tried) again|another (?:try|attempt)|"
                         r"(?:fell|dropped|slid|sank|collapsed|slumped) back (?:down|to)|once more she|"
                         r"gravity (?:won|took over|remembered))\b", re.I)


# words that make a sentence about a body part an INJURY (checked against parts that have no damage at all)
WOUND = re.compile(r"\b(wounds?(?! (?:tight\w*|round|around|about|up|down|in|into|through|itself|themselves|"
                   r"her|his|its|their|back|once|twice|them|it|closer|close|together)\b)|gash\w*|cuts?(?! (?:off|short|out)\b)|scratch(?:es|ed)?|claw marks|grazed?|bleed\w*|"
                   r"blood(?:ied|y)?(?! (?:beat|beating|pound\w+|roar\w+|rush\w+|hammer\w+|thudd\w+|sang|singing|drain\w+|"
                   r"(?:ran|went|turned) cold)\b)|"
                   r"split (?:open|in)|(?:thin|red|parallel) lines|puncture\w*|bite marks)\b", re.I)


# collapse words strong enough to blame on "she" when the sentence doesn't name anyone
COLLAPSE_STRONG = re.compile(r"\b(went (?:limp|slack)|collaps\w*|(?<!face )(?<!expression )(?<!features )(?<!brow )crumpl\w*|eyes rolled back|blacked out|"
                             r"lost consciousness|passed out|consciousness (?:slipp\w*|tried to slip|waver\w*|fad\w*))\b", re.I)


_OBJ_BEFORE = re.compile(r"\b(?:of|on|onto|under|over|at|to|from|with|against|toward|towards|into|above|beside|behind|below|"
                         r"beneath|across|around|round|past|through|off|for|by|than|like|near|between|upon|in)\s+(?:the\s+)?$", re.I)


def _subject(sent, names, aliases=None, last=False, opening=False):
    """The fighter who is the SUBJECT of this sentence, if it says: it opens with her name (or "The Absol", or
    "Nocturne's eyes..."), or a later clause does ("...and the Absol came down on her"). None when every name in it
    is an object or an owner. last=True gives the subject of its LAST such clause, the one a following "she"
    carries on from ("Nocturne's claws opened her chest and Ripples staggered back. Her fins..." is Ripples)."""
    tags = [(n, n) for n in names] + [(a, n) for a, n in (aliases or {}).items() if n in names]
    found = []
    for word, who in tags:
        if re.match(r"[\s*_\"“(]*(?:(?:And|But|Then|So|Still|Yet|Only|Now|For a moment|Above (?:her|them)|Below (?:her|them)),?\s+)?"
                    r"(?:the\s+)?" + re.escape(word) + r"\b(?!['’]s?[,.;:!?—–])", sent, re.I):
            if not last or opening:
                return who
            found.append((0, who))
    if opening:
        return None       # opening=True: only a fighter the sentence OPENS with ("Nocturne's jaws stayed closed...")
    for word, who in tags:
        for m in re.finditer(r"\b" + re.escape(word) + r"\b(?!['’])", sent, re.I):
            before = sent[:m.start()]
            if _OBJ_BEFORE.search(before):
                continue
            if re.search(r"(?:[,;:—–]|\b(?:and|but|as|while|when|until|then|before|after|because|so)\b)\s+(?:the\s+)?$", before, re.I):
                found.append((m.start(), who))
            elif 0 < len(before.split()) <= 6 and not re.search(r"\b(?:she|her|hers|herself)\b|[.!?]", before, re.I) \
                    and re.match(r"\s+(?!and\b|or\b)[a-z]+", sent[m.end():]):
                # a short opener before her name ("On the rock the Absol got her forelegs under her"): still the subject
                found.append((m.start(), who))
    if not found:
        return None
    return (max(found) if last else min(found))[1]


def _who_said(text, names, aliases=None, leads=None):
    """Each sentence with the fighter it's about: the one named in it (by name, or by a species word such as "the
    Buizel" when aliases maps it to a fighter), or else the last one named before it. leads: {sentence: fighter}
    for the first sentence of a part of the beat that is written from one fighter's side ("Ripples' side, picking up
    at contact"): from there on, until someone is named, "she" is that fighter, whoever the part before ended on."""
    out, last, side = [], None, None
    aliases = {a: n for a, n in (aliases or {}).items() if n in names}
    for sent in re.split(r"(?<=[.!?…])\s+|\n+", text):
        named = [n for n in names if re.search(r"\b" + re.escape(n) + r"\b", sent)]
        for a, n in aliases.items():
            if n not in named and re.search(r"\b" + re.escape(a) + r"\b", sent, re.I):
                named.append(n)
        if leads and sent.strip() in leads and leads[sent.strip()] in names:
            side = leads[sent.strip()]       # from here the beat is told from this fighter's side
            if not named:
                last = side
        if named and side:
            # inside a part told from one fighter's side, "she" stays that fighter until ANOTHER becomes the subject
            # of a sentence. A name that is only an object or an owner there ("the Absol's breathing", "pulled the
            # Buizel with her", "found the Buizel through the water") doesn't take the story over
            if last in names and last not in named and _object_only(sent, named, aliases):
                # "Halfway up she stopped ... and sank back, dragging Ripples a step with her": the sentence is
                # still about the fighter "she" has been; the name in it is only what her action touched
                out.append((sent, [last], False))
                continue
            subj = _subject(sent, names, aliases, last=True)
            if not subj and len(named) == 1 and not re.search(r"\b(?:she|her|hers|herself)\b", sent, re.I) and any(
                    re.search(r"\b" + re.escape(t) + r"\b(?!['’])", sent, re.I)
                    for t in [named[0]] + [a_ for a_, n_ in aliases.items() if n_ == named[0]]):
                # "Nothing lay on Ripples now. She threw her arm...": nobody else is in the sentence. (A name that
                # only OWNS something there, "The Absol's, big and rough, above", hands nothing over.)
                subj = named[0]
            last = subj or (last if last in names else side)
            out.append((sent, named, True))
        elif named:
            last = named[0] if len(named) == 1 else None
            out.append((sent, named, True))
        else:
            out.append((sent, [last] if last else [], False))
    return out


# an action that is only NAMED in its sentence (refused, feared, equated with something else), not done:
# "to lift off was to let go", "she refused to let go", "without letting go"
_ONLY_NAMED = re.compile(r"\b(?:was|is|be|were|meant|means|mean|want\w*|refus\w+|afraid|fear\w*|dared?|afford)\s+(?:not\s+)?to\s+$|"
                         r"\b(?:not|never|n't|n’t|without|instead of|rather than|before she could|if she|would not|"
                         r"did not|could not)\s+(?:\w+\s+)?$", re.I)
_OBJ_LEAD = (r"(?:\b\w+ing|\b(?:of|with|on|onto|at|to|toward|towards|from|against|over|under|into|past|behind|beside|"
               r"above|below|off|by|for|round|around|across|near|between|through))\s+(?:the\s+|that\s+)?")


def _object_only(sent, named, aliases=None):
    """Is every fighter named in this sentence only an OBJECT in it, after a "she" that began it? ("She sank back,
    dragging Ripples with her", "she set her teeth deeper in the Buizel's arm")."""
    first = re.search(r"\b(?:she|her)\b", sent, re.I)
    if not first:
        return False
    for n in named:
        words = [n] + [a_ for a_, n_ in (aliases or {}).items() if n_ == n]
        hits = [m for w in words for m in re.finditer(r"\b" + re.escape(w) + r"\b", sent, re.I)]
        if not hits:
            return False
        for m in hits:
            if m.start() < first.start():
                return False          # named before the pronoun: she may well be the subject
            owner = sent[m.end():m.end() + 2] in ("'s", "’s") or sent[m.end():m.end() + 1] in ("'", "’")
            if not owner and not re.search(_OBJ_LEAD + r"$", sent[:m.start()], re.I):
                return False
    return True


# thoughts (*...*), spoken lines ("..."), and pain sounds, so the narrator can be told what's already been said
_THOUGHT = re.compile(r"\*([^*\n]{2,90})\*")
_SPEECH = re.compile(r"[\"“]([^\"”\n]{2,90})[\"”]")
_SOUND = re.compile(r"\b((?:[HhNnGgRrAaUu])[hngrau]{3,}\w*!?)", re.I)


def said_lines(text):
    out = []
    for rx in (_THOUGHT, _SPEECH):
        out += [m.group(1).strip(" .…—-") for m in rx.finditer(text or "")]
    out += [m.group(1) for m in _SOUND.finditer(text or "") if re.fullmatch(r"[hngrau!]+", m.group(1).lower())]
    return [x for x in out if x]


def _norm_line(s):
    return " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())


THOUGHT_ANGLES = ["a quick tactical plan", "a sharp read on the opponent's weakness", "a jab or taunt aimed at the "
                  "opponent (thought or said aloud)", "pride, or refusing to look weak", "an honest assessment of her own "
                  "injury", "noticing something in the arena she could use", "irritation at her own mistake",
                  "grudging respect for the opponent", "a flash of surprise at what just happened", "a stubborn joke",
                  "focusing on her breathing and her body", "a short line spoken aloud to the opponent"]


# stat leakage: percentages, and colors used as pain levels
GAME_TERMS = re.compile(
    r"\b(?:one|two|three|four|five|six|\d+) (?:more )?beats?\b|\b(?:minor|sore|hurting|very painful|excruciating|devastated),? (?:but )?not (?:minor|sore|hurting|very painful|"
    r"excruciating|devastated)\b|\bnumb with shock\b|(?:^|(?<=[\n*.!?]\s)|(?<=[\n*]))(?:devastated|excruciating|very painful|adrenaline surge|"
    r"super effective|critical hit|flinched|paralyzed|confused|restrained)[.!]|\b(?:can(?:'|’)?t|cannot|couldn(?:'|’)?t) attack\b|—(?:devastated|excruciating|very painful)\b|\bpin clock\b|\b\d+ (?:of|out of) \d+ seconds\b|\b(?:started|starts|began) (?:its|the) count(?:down)?\b|\d+(?:\.\d+)?\s*%|\bpercent\b|\b(?:orange|yellow|green|black|purple|violet)\s+(?:pain|ache|agony|fire|"
    r"hurt|line of pain|void|sun|bell|band of pain)\b|\b(?:red|white)\s+(?:pain|agony|hurt|line of pain|band of pain)\b|\b(?:went|turned|crossed into|gone|going|plunged into|became)\s+"
    r"(?:black|red|orange|yellow|green|purple)\b(?!\s+(?:fur|scales?|eyes?|stone|rock|water|light|horn|spots?|"
    r"marks?|tips?|collar|sac|fins?))|\b(?:excruciating|devastated|very painful) (?:level|tier)\b|"
    r"\b(?:painful|numb|grinding|burning|aching|stinging|deep|hot|dull)-(?:red|orange|yellow|green|black|white)\b", re.I)


# words that say a body part stopped working; only allowed once that part is excruciating or worse
DISABLED = re.compile(r"\b(useless|limp|dangl\w*|dead weight|ruined|broken|wouldn't (?:move|work|obey|respond)|"
                      r"couldn't (?:move|use|feel) (?:it|her|his)|refused to (?:work|move|obey)|gave out|"
                      r"folded (?:beneath|under) her|collaps\w* (?:beneath|under) her|no longer (?:work|respond)\w*)\b", re.I)

# the strong half of DISABLED (really not working), and the parts that show feeling by drooping
DISABLED_HARD = re.compile(r"\b(useless|dead weight|ruined|broken|wouldn't (?:move|work|obey|respond)|"
                           r"couldn't (?:move|use|feel) (?:it|her|his)|refused to (?:work|move|obey)|gave out|"
                           r"folded (?:beneath|under) her|collaps\w* (?:beneath|under) her|no longer (?:work|respond)\w*)\b", re.I)
EXPRESSIVE = re.compile(r"\b(sac|tails?|ears?|antennae?|head fin|ruff|whiskers?|tail fan)\b", re.I)
# the same claim with no part named ("It hung useless now. Couldn't use it."): wrong while nothing is that badly hurt
def _said_of(sent, part):
    """Is the "useless / broken / gave out" in this sentence said OF this part? "Her left arm hung useless" and "her
    useless arm" are; "a stump stood a paw's length from her head, pale where it had broken" is not (another clause,
    another subject)."""
    words = [w for w in re.findall(r"[a-z]+", part.lower()) if w not in ("left", "right")]
    if not words:
        return False
    rx = re.compile(r"\b" + r"\s+".join(re.escape(w) for w in words) + r"(?:s|es)?\b", re.I)
    for pm in rx.finditer(sent):
        for dm in DISABLED.finditer(sent):
            gap = sent[pm.end():dm.start()] if dm.start() >= pm.end() else sent[dm.end():pm.start()]
            after = dm.start() >= pm.end()
            if re.search(r"[,;:—–()]", gap) or re.search(r"\b(?:it|that|which|where|who|while|as|and|but)\b", gap, re.I):
                continue
            if len(gap.split()) <= (6 if after else 3):
                return True
    return False


DISABLED_VAGUE = re.compile(r"\b(hung useless|(?:couldn't|could not|can't) (?:use|move|feel) it|"
                            r"the only one that (?:still )?(?:worked|works|would work)|wouldn't (?:move|work|obey|respond))\b", re.I)

# a fighter who stands upright on two feet, shown standing on a hand
HAND_WEIGHT = re.compile(r"\bweight\b[^.!?]{0,25}?\b(?:on|onto|off|from)\b (?:of )?(?:her|his|the|that|one|each|both) "
                         r"(?:\w+ ){0,2}?(?:paws?|arms?|forearms?|hands?|forearm fins?)\b", re.I)

# the natural weapons a move can be delivered with, and the words that name them in a move's description
WEAPONS = (("claws", r"\bclaw|\btalon|\bscratch|\brak(?:e|es|ed|ing)\b|\bswipe"),
           ("teeth", r"\bbit(?:e|es|ing)?\b|\bfang|\bteeth|\bjaws?\b|\bcrunch|\bmaw\b"),
           ("tail", r"\btails?\b"),
           ("horn", r"\bhorn|\bgore"))
WEAPON_SAY = {"claws": "her CLAWS", "teeth": "her TEETH", "tail": "her TAIL", "horn": "her HORN"}
WEAPON_NOT = {"claws": "a claw swipe", "teeth": "a bite", "tail": "a tail strike"}
# an attack with the teeth, as it happens (not "the teeth marks", not "bit down on a cry")
BITING = re.compile(r"\b((?:fangs|teeth|jaws?|muzzle|mouth) (?:sank|sinking|sink|clamp\w*|clos\w+|lock\w*|snapp\w+|fasten\w+|"
                    r"latch\w+) (?:down |shut |hard |tight )*(?:on|onto|around|into|over)\b|(?:fangs|teeth) (?:sank|sinking|"
                    r"pierc\w+|punctur\w+|dug|driving|drove)\b|(?:sank|sinks|sinking|sunk|buried|drove) (?:her|his) "
                    r"(?:fangs|teeth)|\b(?:bit|bites|biting) (?:down )?(?:hard )?(?:on|into) (?:her|his|the)\b"
                    r"(?! (?:own |lower |bottom )?(?:cry|whimper|scream|snarl|yelp|sound|lip|tongue|pain|urge|growl|cheek)))", re.I)
HORN_STRIKE = re.compile(r"\bhorn[- ]first\b|\bled with (?:her|his) horn\b|\bhorn\b[^.!?,;—]{0,30}?\b(?:struck|slashed|"
                         r"sliced|cut|gored|rammed|slammed|caught|hit|drove|came down|hooked)\b", re.I)
# big words for a hurt that is only minor
OVERBLOWN = re.compile(r"\b(scream\w*|shriek\w*|howl\w*|agon\w+|white-hot|explod\w+|excruciating|unbearable|blinding|"
                       r"ruined|shatter\w*|snapp\w+|gave way|splitting|shifted wrong|twist\w+ wrong|crack(?:ed|ing)?|"
                       r"searing|tore through|ripped through)\b", re.I)
# a sound standing alone as its own paragraph ("Crack.")
# an impact word from the beat's notes standing as a sentence of its own ("Tremendous.")
BARE_IMPACT = re.compile(r"^[\s*_\"“]*(?:Tremendous|Devastating|Solid|A (?:tremendous|heavy|solid) blow)[.!…]+[\s*_\"”]*$", re.I)
SOUND_PARA = re.compile(r"^[\s*_\"“]*(?:crack|snap|pop|crunch|thunk|thud|click)[.!…—]*[\s*_\"”]*$", re.I)
# a get-up attempt (made, or failed) by someone the engine has not rolled one for this beat
TRY_UP = re.compile(r"\b((?:tried|trying|tries|struggl\w+|fought|fighting|attempt\w+|managed|failed) to (?:push|get|haul|drag|"
                    r"lever|force|lift) (?:herself|himself) (?:back )?(?:up|upright|to (?:her|his) feet)|(?:tried|trying|tries|"
                    r"attempt\w+|fail\w+) to (?:rise|stand|get (?:back )?up)|push(?:ed|ing)? (?:herself|himself) (?:back )?"
                    r"(?:up|upright)|(?:collaps|dropp|fell|sank|slump)\w* back (?:down|onto)|unable to rise|halfway up|"
                    r"got (?:back )?to (?:her|his) (?:feet|knees)|hauled (?:herself|himself) up)", re.I)
# pain going numb (off when the numb level is off)
NUMB = re.compile(r"\b(numb(?:ed|ing|ness)?|past (?:pain|feeling|hurting)|beyond pain|no feeling (?:left|at all)|"
                  r"(?:couldn't|could not|can't) feel (?:it|her|his|the))\b", re.I)
# the instructions' own wording turning up as prose
PROMPT_ECHO = re.compile(r"\b(past (?:excruciating|very painful|devastated)\b|seconds \d+ (?:to|through|until|–|—|-) ?\d+\b|"
                         r"sore squeezes?\b|(?:a|an|the|in a wild,?) improvisational\b|from (?:minor|sore|hurting|very painful|excruciating) to (?:sore|hurting|very painful|"
                         r"excruciating|devastated)\b|the (?:very painful|excruciating|devastated|hurting|sore) one\b|"
                         r"the contact point\b|the pin ha[sd] only just begun|real damage (?:would|will|builds?|built|was going to)\b[^.!?]{0,25}"
                         r"over the coming|an instant hit\b|pressure (?:was|is) only just landing|no seconds (?:had )?"
                         r"tick\w* (?:by|past)|no pressure had built|(?:not|no longer) (?:even |just )?(?:excruciating|"
                         r"devastated)\b|(?:excruciating|devastated) anymore)", re.I)
# a badly hurt part called fine
HEALTHY = re.compile(r"\b(still (?:good|strong|fine|whole|sound|working)|(?:was|were|felt) (?:good|fine|strong|whole)\b|"
                     r"(?:her|his) good (?:paw|arm|leg|side|hand|foot|ear|eye)|unhurt|uninjured|undamaged|untouched)", re.I)
TAIL_STRIKE = re.compile(r"\btails?(?: blade| tip)?\b[^.!?,;—]{0,30}?\b(?:struck|slashed|sliced|cut|smacked|slammed|cracked|"
                         r"caught|hit|came down|whipped (?:across|into|through|down)|swept (?:across|into|through))\b", re.I)
# features nobody in this fight may have (filled in by the program from who is fighting)
ANATOMY_WORDS = {"scales": "scale", "scaled": "scale", "coils": "coil", "antennae": "antenna", "antenna": "antenna",
                 "feathers": "feather", "wings": "wing", "hooves": "hoo", "beak": "beak", "serpentine": "serpent",
                 "flotation sac": "sac", "sac": "sac", "collar": "collar"}
# a style sample is written with the original fighters: when nobody in the fight has a flotation sac, the passages
# built on one are told with what she does have (first few words of the paragraph -> the paragraph without a sac)
SAMPLE_NO_SAC = (
    ("But the thing between her chest and her neck", "But her tails were hers."),
    ("The flotation sac. The thick yellow collar", "The twin tails. They lay in the shallows behind her, the one part of her "
     "the lightning had barely touched, and nothing was holding them. And they could spin."),
    ("She started drawing air", "She started them turning—not fast, she couldn't—a slow stir under the surface, each turn a "
     "fight against the weight on her hips, each one gathering a little more water round the cream tips."),
    ("Nocturne felt something shift under her jaw", "Nocturne felt something shift under her and pressed down harder, not "
     "understanding."),
    ("The sac vented.", "The tails whipped. Both of them, at once, a propeller-blast of cold water straight up into the "
     "Absol's face, and Nocturne's head jerked back on reflex, and her teeth came free of the neck, and the Buizel's "
     "arm—numb, heavy—swung up from below wrapped in crackling frost, straight into the Absol's flank."),
)
SAMPLE_NO_SAC_BITS = (
    (", the yellow flotation sac around her neck already half-inflated with excitement", ", forearm fins flared wide with excitement"),
    ("the thick pads of her paws, the rubbery flotation sac, and the dense muscle", "the thick pads of her paws and the dense muscle"),
)
SAC_WORD = re.compile(r"\b(?:flotation sac|sac|collar)\b", re.I)


def sample_without_sac(sample):
    """The style sample for a fight in which nobody has a flotation sac: the passages built on one are swapped for
    their sac-less telling, and any other sentence that mentions it is left out."""
    for old, new in SAMPLE_NO_SAC_BITS:
        sample = sample.replace(old, new)
    paras = []
    for para in sample.split("\n"):
        swap = next((new for start, new in SAMPLE_NO_SAC if para.strip().startswith(start)), None)
        if swap is not None:
            para = swap
        elif SAC_WORD.search(para):
            para = " ".join(x for x in re.split(r"(?<=[.!?…])\s+", para) if not SAC_WORD.search(x))
        paras.append(para)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip()

# parts of a body-part name that don't help find it in prose
_SKIP_WORDS = {"left", "right", "upper", "lower", "middle", "front", "back", "hind", "the"}
STRUGGLE_WORDS = re.compile(r"\b(buck|bridg|twist|wrench|thrash|kick|struggl|heav|arch|squirm|writh|jerk|strain|"
                            r"shove|wriggl|lurch|surg|thrust|scrabbl|claw(?:ed|ing) at|fought|fight(?:s|ing)? (?:to|against)|"
                            r"pull(?:ed|ing)? free|tore free|broke free|breaks? free|slip(?:ped|s)? free)", re.I)


# what an escape or a break-loose must actually show (not just straining)
ESCAPE_WORDS = re.compile(r"\b(broke free|breaks? free|tore free|tearing free|wrenched (?:herself |her \w+ )?free|"
                          r"slipped free|slipped out|squirmed free|twisted free|rolled free|scrambled (?:free|clear|away|out)|"
                          r"out from under|threw (?:her|\w+) off|thrown off|bucked (?:her|\w+) off|"
                          r"(?:the )?pin (?:broke|was broken|gave way|is broken|shattered)|free of (?:the|her|\w+'s?) pin|"
                          r"lost (?:her|the) (?:grip|hold)|(?:grip|hold) (?:broke|slipped|gave))\b", re.I)
# on a beat where the pin HOLDS: the pinned fighter loose, or the pinner off her
PINNED_UP = re.compile(r"\b(lunged|lunges|sprang|leapt|leaped|pounced|charged|got (?:back )?(?:up|to (?:her|his) feet)|"
                       r"(?:scrambled|staggered|pushed|hauled|rose|climbed|surged) (?:back )?(?:up|upright|to (?:her|his) feet)|"
                       r"(?:back )?on (?:her|his) feet|rolled (?:free|clear|away|out|immediately|sideways)|stood (?:up|over)|"
                       r"was (?:free|loose|out)\b|circled|backed away|wriggled (?:free|out|loose))\b", re.I)
PINNER_OFF = re.compile(r"\b(scrambled (?:backward|back|away|clear)|(?:thrown|flung|knocked|tossed|bucked|kicked|shoved|hurled|"
                        r"sent) (?:her |him )?(?:off|clear|back|backward|aside|away|flying|tumbling|sprawling)|slammed onto the|"
                        r"hit the (?:stone|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|ground|water)|tumbl\w+|rolled off|backed (?:away|off)|dove|dived|retreat\w*|"
                        r"leapt (?:back|away|clear)|let (?:her )?go\b|released (?:her|him|the pin|her grip)|landed (?:hard )?on "
                        r"(?:her|his) (?:back|side|rump)|lost (?:her|his) (?:grip|hold|balance))\b", re.I)
_NOT_REALLY = re.compile(r"\b(tried|trying|tries|attempt\w*|couldn't|could not|can't|cannot|unable|wanted|want(?:s|ing)? to|"
                         r"fail(?:ed|s|ing)?|not|never|no|if only|almost|nearly|struggl\w+ to|fought to|strain\w+ to|"
                         r"would(?:n't| not)?|before she could|refus\w+)\b[^.!?]{0,45}$", re.I)
# a grip that is still on when the beat ends, shown coming off: the holder lets go, or the held one gets free
LET_GO = re.compile(
    r"\b((?:bite|jaws?|grip|hold|teeth|fangs|tails?|coils?|lock|clamp) (?:finally |suddenly |at last )?(?:(?:came|comes|"
    r"slipped|slips|tore|pulled|ripped|fell|went|worked|sprang) (?:free|loose|away|off|open|slack)|broke\b|failed\b|"
    r"gave way|gave out|let go|releas(?:ed|ing|es)|went slack|slackened|slid (?:off|away|free)|fell away|dropped away|"
    r"peeled (?:off|away))|let (?:her |him |it |the \w+ )?go\b|releas(?:ed|ing|es) (?:her|him|the|his|[A-Z][\w-]+(?:'s|’s|'|’))(?=\s)|"
    r"jaws (?:now |were |hung )?(?:empty|open)\b|opened (?:her|his) (?:jaws|mouth)|unclamp\w*|uncoil\w*|unwound|"
    r"lost (?:her|his) (?:grip|hold)|pulled (?:her|his) (?:jaws|teeth|fangs|tails?) (?:free|away|back|out))", re.I)
GOT_FREE = re.compile(r"\b((?:tore|pulled|ripped|wrenched|yanked|slipped|twisted|wriggled|jerked|broke) (?:herself |himself |"
                      r"her \w+ |his \w+ )?(?:free|loose)\b|was (?:free|loose) of)", re.I)
RECLAMPED = re.compile(r"\b(?:then|but|before|only to|and)\b[^.;]{0,60}\b(?:clamp\w*|tighten\w*|clos\w*|bit|bore|"
                       r"settl\w*|lock\w*|cinch\w*|squeez\w*|constrict\w*) (?:down|again|back|deeper|harder|tighter|shut)\b", re.I)
_MOUTH_OPENS = re.compile(r"\b(?:opened (?:her|his) (?:jaws|mouth)|(?:her|his) (?:jaws|mouth) (?:opened|came open|gaped))\b", re.I)
GRIP_OFF = re.compile(LET_GO.pattern + "|" + GOT_FREE.pattern, re.I)
# a grip that is told as ON: what it is made with (by family) and the words for holding
GRIP_FAMILY = (("tails", r"\btails?\b|\b(?:cream|tail)[- ]tips?\b"), ("coils", r"\bcoils?\b|\bloops? of her body\b"),
               ("jaws", r"\bjaws?\b|\bteeth\b|\bfangs\b|\bbite\b|\bmuzzle\b"))
# body parts by class, for "her jaws are on the PAW, not the throat"
PART_CLASS = (("neck", r"\b(?:neck|throat|windpipe|scruff|collar)\b"), ("paw", r"\b(?:paws?|forepaws?|wrists?|fingers?|hands?)\b"),
              ("arm", r"\b(?:arms?|forearms?|forelegs?|fins?|elbows?)\b"),
              ("leg", r"\b(?:legs?|thighs?|knees?|hocks?|hips?|foot|feet|ankles?)\b"), ("shoulder", r"\bshoulders?\b"),
              ("ear", r"\bears?\b"), ("body", r"\b(?:chest|belly|stomach|back|ribs?|flanks?|midsection|waist)\b"))
PART_NEAR = {"paw": {"arm"}, "arm": {"paw", "shoulder"}, "shoulder": {"arm"}, "leg": set(), "neck": set(), "ear": set(),
             "body": set()}
GRIP_ON = re.compile(r"\b(coil\w*|wrapp\w*|wound|bound|gripp\w*|grip|lock\w*|clamp\w*|squeez\w*|tighten\w*|held|holding|"
                     r"trapp\w*|shackl\w*|vice|vise|latched|constrict\w*|clung|clinging|looped)\b", re.I)
GRIP_PAST = re.compile(r"\b(had|no longer|slipp\w*|lost|loosen\w*|uncoil\w*|unwound|let go|released|fell away|slid off|"
                       r"free|freed|gone|empty|remember\w*|earlier|not|never|without|tried|trying|wanted|reach\w*)\b", re.I)
# a rise that doesn't happen: "tried to stand", "almost on her feet" (a comma or dash ends the reach of the word)
NOT_UP = re.compile(r"\b(tried to|trying to|tries to|attempt\w* to|couldn't|could not|can't|cannot|unable to|wanted to|"
                    r"failed to|not|never|almost|nearly|struggl\w+ to|fought to|before she could|if she|halfway|half)\b"
                    r"[^.!?,;—]{0,30}$", re.I)
# she passes out: what the last beat of a completed pin has to show
OUT_SAID = re.compile(
    r"\b(faint(?:ed|s|ing)|(?:a dead|in a|into a) faint|passed out|pass(?:es|ing) out|blacked out|black(?:ness)? (?:took|claimed|swallowed|closed)|went (?:limp|slack|"
    r"still|dark|out|quiet)|goes (?:limp|slack|still)|out cold|unconscious\w*|consciousness (?:slipped|left|fled|faded|went|"
    r"gave)|eyes (?:rolled back|slid shut|fell shut|drifted shut|fluttered shut|closed and (?:stayed|did not)|did not open|"
    r"(?:were|stayed|had) (?:closed|shut))|"
    r"lids (?:came down|slid shut|closed|(?:did not|didn't|would not|wouldn't) (?:answer|lift|open|come up))|darkness (?:took|closed|swallowed|rushed|claimed)|world went (?:dark|black|grey|gray)|"
    r"slipped (?:under|away|into (?:the )?(?:dark|black))|did not (?:move|stir) again|stopped (?:fighting|moving|struggling)|"
    r"(?:the )?(?:fight|struggle|tension|strength) (?:went|drained|ran|bled|left|leaked) out of (?:her|him)|"
    r"eyes (?:closed|shut)(?:,| and)[^.!?]{0,45}(?:did not|didn't|stayed|for good|no more)|went soft|"
    r"limp (?:chin|body|weight|form|neck|head|paws?|tails?)|did not stir|felt it go out of (?:her|him))\b", re.I)
# back down after a try at getting up, or simply lying there: she is NOT on her feet at this point of the passage
DOWN_AGAIN = re.compile(r"\b((?:dropped|fell|went|sank|slumped|collapsed|crumpled|slid|thudded) back(?: down)?\b|back (?:down )?"
                        r"(?:to|onto|on) (?:the|her|his) (?:ground|stone|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|back|belly|side|knees?)|(?:lay|lying) (?:there|"
                        r"still|flat|on (?:her|his))|stayed down|couldn't rise|could not rise)", re.I)
STAND_OVER = re.compile(r"\b(?:stood|stands|standing|loom\w+|tower\w+) (?:over|above)\b", re.I)
# what a sentence has to SAY before a second reading may call it a contradiction of that kind
POSTURE_SAID = re.compile(
    r"\b(on (?:her|his|its) (?:feet|back|belly|side|stomach|front|knees)|stood|stands|standing|upright|got (?:back )?up|"
    r"gets (?:back )?up|to (?:her|his) feet|rose\b|rises\b|(?:lay|lies|lying)\b|sprawl\w*|prone|flat on|face-?down|"
    r"face-?up|on the (?:ground|floor|sand|grass|ice|snow|mud|deck|plating|planks|planking|boards|gravel|dirt|earth|grating|concrete|rubble|flagstones|basalt|shelf|scree|turf|moss|stone)|pinned|held (?:her |him )?down|pins? (?:her|him)|broke free|slipped free|"
    r"got free|was free|fell\b|falls\b|fallen|collaps\w*|crumpl\w*|toppl\w*|went down|knocked (?:her |him )?down|"
    r"dropped to|slumped|slid down|stood over)", re.I)
ATTACK_SAID = re.compile(
    r"\b(hit|hits|struck|strikes?|slamm\w+|smash\w+|bit\b|bites?\b|biting|claw\w*|rak(?:ed|es|ing)|kick\w*|headbutt\w*|"
    r"slash\w*|punch\w*|stab\w*|gored?|whipp\w+|lash\w+ (?:across|into|against)|blast\w*|sank (?:her|his)|tore (?:into|"
    r"across|through)|cut (?:into|across|through)|wound\w*|gash\w*|bleed\w*|blood|bruis\w*|broke\b|broken|crack\w*|snapp\w+)",
    re.I)
WORSE_SAID = re.compile(
    r"\b(broke\b|broken|breaks?\b|crack\w*|snapp\w+|shatter\w*|fractur\w*|disloc\w*|useless|dead weight|ruined|numb\w*|"
    r"limp\b|dangl\w*|torn|ripped|crushed|gave way|gave out|couldn't (?:move|feel|use)|could not (?:move|feel|use)|"
    r"wouldn't (?:move|work|respond))", re.I)
# a remark about the passage or the facts, not the opposite fact
READER_REMARK = re.compile(
    r"\b(not a contradiction|no contradiction|not (?:really |necessarily )?contradict|should be noted|the passage should|"
    r"should (?:show|describe|mention|include|say)|is consistent|agrees with|does(?:n't| not) (?:specify|say|state)|"
    r"not (?:mentioned|specified|described|stated)|no mention|the facts (?:list|describe|mention|give) (?:a|the) (?:specific|"
    r"sequence|series|number)|unclear|may or may not|so this (?:\w+ ){0,3}contradicts (?:her|his) posture)\b", re.I)
# loose vocabularies for a second reading's posture findings: the sentence has to say SOMETHING about being down / up
DOWNISH = re.compile(r"\b(lay|lying|lies|sprawl\w*|stretched out|flat|floor|ground|puddle|fell|falls?|fallen|falling|"
                     r"collaps\w*|crumpl\w*|slump\w*|toppl\w*|knees?|prone|dropp\w+|sank|sinks?|sinking|slid|went down|"
                     r"knocked down|on (?:her|his) (?:back|belly|side|stomach|front|face)|face-?(?:down|up|first)|"
                     r"pinned|held down|couldn't (?:rise|stand|get up))\b", re.I)
UPISH = re.compile(r"\b(stood|stands?|standing|feet|upright|rose|rises?|rising|got up|gets up|back up|legs under|paced|"
                   r"pacing|circl\w+|stepped|steps|strode|walk\w*|ran\b|leapt|leaped|lunged|charged|sprang|backed away|"
                   r"free of|broke free|slipped free)\b", re.I)
# what falls is a thing, not a fighter: "a drop fell into the channel", "grit fell onto the ledge"
_THING_FALLS = re.compile(r"\b(?:(?:a|an|the|each|every|one|another|some|more|its|their|that|this|loose|fine|cold)\s+)+"
                          r"(?:[\w-]+\s+){0,2}?(?:drops?|droplets?|drips?|water|spray|rain|mist|dust|grit|sand|pebbles?|"
                          r"stones?|chips?|shards?|flakes?|splinters?|lea(?:f|ves)|snow|ice|icicles?|light|shadows?|silence|"
                          r"hush|quiet|sounds?|echo(?:es)?|stalactites?)\s+$", re.I)
# the telling of a dodge: she is not where the blow goes
_DODGE_TOLD = re.compile(r"\b(dodg\w+|sidestep\w*|side-?stepp\w+|evad\w+|(?:slipp?ed|slid|twisted|leapt|sprang|jumped|"
                         r"swayed|ducked|rolled|stepped|spun|skipped|flowed) (?:\w+ )?(?:aside|away|clear|out of (?:the|its) "
                         r"way|out from under|to one side|under it|past it|round it)|was(?:n't| not) there|"
                         r"no longer there|already gone)\b", re.I)
MISSED = re.compile(r"\b(empty (?:space|air)|missed|misses|met (?:only |nothing but )?air|nothing but air|fell short|"
                    r"went wide|wide of|whistled past|passed over|didn't land|did not land)\b", re.I)
HIT_WORDS = re.compile(r"\b(hit|struck|strikes?|slammed|smashed|bit|bites?|clawed|raked|kicked|headbutt\w*|"
                       r"caught (?:her|\w+)|connected|landed|cracked into|drove (?:her|a|an))\b", re.I)


def _mentions(text_lower, part):
    """Does the prose mention this body part (or its key word, singular or plural)?"""
    words = [w for w in re.findall(r"[a-z]+", part.lower()) if w not in _SKIP_WORDS] or part.lower().split()
    for w in words:
        stem = w[:-1] if w.endswith("s") and len(w) > 4 else w
        if re.search(r"\b" + re.escape(stem) + r"(?:s|es)?\b", text_lower):
            return True
    return False


def _mentions_exact(text_lower, part):
    """Stricter than _mentions: the part's full name minus left/right (e.g. "forearm fin", "tail base")."""
    words = [w for w in re.findall(r"[a-z]+", part.lower()) if w not in ("left", "right")]
    if not words:
        return False
    return re.search(r"\b" + r"\s+".join(re.escape(w) for w in words) + r"(?:s|es)?\b", text_lower) is not None


# a countdown in a beat with no pin running ("Twenty seconds.", "eight seconds remaining", "Second 40")
_COUNTDOWN_SRC = (r"(?:(?:^|\n)\s*[*_]*\s*" + "{num}" + r"\s+seconds?\s*[.!…]?\s*[*_]*\s*(?=\n|$)|"
                        r"\b" + "{num}" + r"\s+seconds?\s+(?:left|remaining|to go|more)\b|\bjust\s+" + "{num}" + r"\s+more\b|\bsecond\s+\d+\b)",
                  )

_NUM_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_NUM = (r"(\d+|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|"
        r"eight|nine))?|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
        r"sixteen|seventeen|eighteen|nineteen|a hundred|one hundred)")
# clock markers: "Second 30", or "Thirty seconds." starting a line or sentence (not durations like "for two seconds")
_TIME_MARK = re.compile(r"(?:(?<=^)|(?<=\n)|(?<=[.!?…]\s)|(?<=[*_]))\s*[*_]*\s*(?:second\s+" + _NUM + r"\b|" + _NUM
                        + r"\s+seconds?\b)", re.I)


# "Forty more." : the time remaining, counted as its own little sentence
_BARE_MORE = re.compile(r"(?:^|(?<=\n)|(?<=[.!?…]\s)|(?<=[*_\"“]))\s*[*_\"“]*\s*" + _NUM + r"\s+more\s*[.!…]", re.I)
# the clock inside a sentence: "At fifteen seconds, ..." / "on her feet by thirty seconds"
_CLOCK_AT = re.compile(r"\b(?:at|by|past|around) " + _NUM + r" seconds?\b,?\s*", re.I)


def _clock_at_overrun(text, start, end):
    """In-sentence clock marks ("at twenty seconds") outside this beat's window: the matched phrases."""
    return [m.group(0).strip(" ,") for m in _CLOCK_AT.finditer(text or "") if not start <= _to_int(m.group(1)) <= end]


def _strip_clock_at(text, start, end):
    """Take out-of-window clock phrases out of their sentences, leaving the sentences: "At fifteen seconds, her legs
    scraped" -> "Her legs scraped"; "on her feet by thirty seconds, unsteady" -> "on her feet, unsteady"."""
    def fix(m):
        if start <= _to_int(m.group(1)) <= end:
            return m.group(0)
        before = m.string[:m.start()].rstrip(" ")
        opens = not before or before[-1] in ".!?…\n\"”*—"   # the phrase opens its sentence: drop it whole
        return "\x00" if m.group(0).rstrip().endswith(",") and not opens else ""
    out = _CLOCK_AT.sub(fix, text)
    out = re.sub(r" ?\x00", ", ", out)                      # mid-sentence: keep one comma
    out = re.sub(r" +([,.;!?])", r"\1", out)
    out = re.sub(r"(^|[.!?…]\s+|\n)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)  # a new sentence start
    return re.sub(r"[ \t]{2,}", " ", out)


def _drop_clock_outside(text, start, end):
    """Remove only the sentences that mark a second outside this beat's window ("Forty seconds." in a beat that
    covers 50 to 60, "Thirty." in one that ends at 20). What follows them stays. A bare small number below the
    window is left alone: it is usually counting something else (tries, breaths)."""
    def wrong(sent):
        for m in _TIME_MARK.finditer(sent):
            v = _to_int(m.group(1) or m.group(2))
            if v > end or v < start:
                return True
        return any(_to_int(m.group(1)) > end for m in _BARE_COUNT.finditer(sent))
    out = []
    for para in text.split("\n"):
        out.append(" ".join(x for x in _SENT.split(para.strip()) if x and not wrong(x)))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _to_int(word):
    w = word.lower().replace("-", " ").strip()
    if w.isdigit():
        return int(w)
    if w in ("a hundred", "one hundred"):
        return 100
    parts = w.split()
    total = _TENS.get(parts[0], _NUM_WORDS.get(parts[0], 0))
    if len(parts) > 1:
        total += _NUM_WORDS.get(parts[1], 0)
    return total


def _time_overrun(text, start, end):
    """First clock marker outside [start, end]: (position of its sentence, the marker text), or None."""
    marks = [(m.start(), _to_int(m.group(1) or m.group(2)), m.group(0)) for m in _TIME_MARK.finditer(text)]
    marks += [(m.start(), _to_int(m.group(1)), m.group(0)) for m in _BARE_COUNT.finditer(text)]
    for start_pos, value, raw in sorted(marks):
        if value > end or value < start:
            pos = max(text.rfind("\n", 0, start_pos), text.rfind(". ", 0, start_pos) + 1, 0)
            return pos, raw.strip(" *_\n")
    return None

_COUNTDOWN = re.compile("".join(_COUNTDOWN_SRC).replace("{num}", _NUM), re.I)


NO_CLOCK_RULE = ("- A pin has NO clock in this story. Nobody is counting and nobody knows when the pinned fighter will pass "
                 "out: never write seconds, a count (up or down), \"N seconds\", \"time left\", or \"halfway\". Show time "
                 "passing only through bodies: breath getting shorter, struggles getting weaker, sight greying.")
NO_PIN_RULE = ("- There is NO pin in this beat, so there is NO pin clock: never count seconds down or mark \"N seconds "
               "left\".")


def _story_sections(text, keep_pins):
    """The author's story prompt, minus the PINS section on beats that have nothing to do with a pin."""
    if keep_pins:
        return text
    out, skipping = [], False
    for line in text.splitlines():
        if re.fullmatch(r"[A-Z][A-Z &/-]{2,}", line.strip()):
            skipping = line.strip().startswith("PIN")
        if not skipping:
            out.append(line)
    return "\n".join(out).strip()


_DEPENDENT = re.compile(r"^[\s*_\"“”'(]*(?:but|yet|still|instead|so|and|or|nor|then|not|until|because|which|though|"
                        r"except|only|neither|either|it|that|this)\b", re.I)
_STUB_PARA = re.compile(r"^[\s*_\"“”']*(?:the|a|an|her|his|its|their|and|but|then|she|he|it|they|with|of|to|in|on|at|as|"
                        r"that|this)?[\s*_\"“”',.—-]*$", re.I)
_SENT = re.compile(r"(?<=[.!?…])\s+")


# a sentence with no subject of its own, leaning on the one before it: "Then opened again, fixing on her gaze."
_HEADLESS = re.compile(r"^[\s*_\"“]*(?:and\s+|but\s+)?then\s+(?!she\b|he\b|her\b|his\b|the\b|a\b|an\b|it\b|they\b|there\b|"
                       r"nothing\b|something\b|every\w*\b)[a-z]+(?:ed|pt|lt|nt)\b", re.I)


# "Nocturne thought, her red eyes narrowing..." / "The number echoed in her mind..." once what they hung on is cut
_LEFT_HANGING = re.compile(r"^[\s*_\"“]*(?:(?:[A-Z][\w'’-]+|She|He|The \w+) (?:thought|said|whispered|muttered|growled|hissed|"
                           r"snarled|added|told herself)\b\s*,|(?:The|That|Those|These) (?:number|count|word|words|thought|"
                           r"thoughts) (?:echoed|rang|hung|sat|stayed|lingered|came)\b)")


def _is_stub(sent):
    """A short line that only makes sense after the sentence before it: "But she couldn't." / "Not yet." / "It held."."""
    words = re.findall(r"[\w'’]+", sent)
    m = _DEPENDENT.match(sent)
    if not words or not m:
        return False
    lead = re.sub(r"\W", "", m.group(0)).lower()
    return len(words) <= (4 if lead in ("it", "that", "this", "so", "and", "then", "only") else 7)


SLIP_LABELS = (("SECOND time", "same blow told twice"), ("NO pin and no hold", "invented pin"),
               ("go limp or unable to move", "limp while still strong"), ("nothing of hers can break", "broken bones"),
               ("cracks or pops", "invented crack"), ("has never been hit", "pain in a part never hit"),
               ("was never landed on her", "wrong move remembered"), ("word from the notes", "game terms"),
               ("copies the notes", "notes copied"), ("nothing hits that part", "blow that isn't listed"),
               ("tails are round", "gripping tails shown free"), ("body, not hers", "wrong fighter's anatomy"),
               ("failed tries at getting up", "get-up tries skipped"), ("did by itself this beat", "arena event not shown"),
               ("coming up on her feet", "roll-through not shown"), ("left out the tumble", "tumble not shown"),
               ("nobody gets up this beat", "invented get-up"), ("nothing lands on", "blow that isn't listed"),
               ("in this fight so far", "wrong count"), ("is the one far worse hurt", "wrong part called the worst"),
               ("this stretch is about", "wrong fighter's anatomy"), ("it has been told", "same pressing told again"),
               ("never showed", None))


def _slip_label(issue):
    """The short name for a finding added since build 99 (None = one of the older ones)."""
    for mark, label in SLIP_LABELS:
        if mark in issue:
            return label
    return None


def _drop_hanging_leadins(text):
    """A sentence that ends in a colon promises something ("...and thought one cold, hard thing:"). When a cut took
    what it promised and the next paragraph is plain narration, the lead-in goes too."""
    paras = text.split("\n")
    for i, p in enumerate(paras):
        if not p.rstrip().endswith(":"):
            continue
        nxt = next((q.strip() for q in paras[i + 1:] if q.strip()), "")
        if nxt[:1] in ("*", "_", '"', "“", "'", "‘") or not nxt:
            if nxt:
                continue
        sents = [x for x in _SENT.split(p.strip()) if x]
        if len(sents) > 1 and re.search(r"\b(?:thought|thing|said|whispered|one word|knew|realized|understood)\b[^.!?]*:$", sents[-1]):
            paras[i] = " ".join(sents[:-1])
        elif len(sents) == 1 and re.search(r"\b(?:thought|thing|one word)\b[^.!?]*:$", sents[0]):
            paras[i] = ""
    return re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip()


def _drop_orphans(before, after):
    """`after` is `before` with sentences cut out. A short follow-up that leaned on a cut sentence ("But she
    couldn't. Not yet.") is cut with it, and so is a paragraph left holding nothing but a dangling word ("The—")."""
    if not after:
        return after
    paras = [[x for x in _SENT.split(p.strip()) if x] for p in after.split("\n")]
    if before and before != after:
        import collections
        have = collections.Counter(x for p in paras for x in p)
        doomed, cut = collections.Counter(), False
        for para in before.split("\n"):
            for x in _SENT.split(para.strip()):
                if not x:
                    continue
                if have[x] > 0:
                    have[x] -= 1
                    if cut and (_is_stub(x) or _LEFT_HANGING.match(x) or (_HEADLESS.match(x) and not re.match(r"[\s*_\"“]*(?:and |but )?then [A-Z]", x))):
                        doomed[x] += 1   # and whatever leans on IT goes too
                    else:
                        cut = False
                else:
                    cut = True
        # a lone sound ("Crack.") that led straight into a cut sentence goes with it
        flat = [x for para in before.split("\n") for x in _SENT.split(para.strip()) if x]
        left = collections.Counter(x for p in paras for x in p)
        for i, x in enumerate(flat[:-1]):
            if SOUND_PARA.match(x) and left[x] > 0 and left[flat[i + 1]] == 0:
                # the very next sentence is still cut: look one further (the sound may sit two lines up)
                doomed[x] += 1
            elif SOUND_PARA.match(x) and left[x] > 0 and i + 2 < len(flat) and left[flat[i + 2]] == 0 \
                    and len(flat[i + 1].split()) <= 9:
                doomed[x] += 1
        if doomed:
            kept = []
            for p in paras:
                row = []
                for x in p:
                    if doomed[x] > 0:
                        doomed[x] -= 1
                    else:
                        row.append(x)
                kept.append(row)
            paras = kept
    out = [" ".join(p) for p in paras]
    out = [p for p in out if not (p and _STUB_PARA.match(p))]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _drop_matching(text, pattern):
    """Remove only the sentences that match `pattern`."""
    out = []
    for para in text.split("\n"):
        kept = [s for s in re.split(r"(?<=[.!?…])\s+", para) if not pattern.search(s)]
        out.append(" ".join(kept).strip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


# a number standing alone as a count: "Nine." / "Eight..." / "“Ten,” she counted" / "*Seven.*"
_BARE_COUNT = re.compile(r"(?:^|(?<=\n)|(?<=[.!?…]\s)|(?<=[.!?…]”\s)|(?<=[.!?…]\"\s))\s*[*_\"“]*\s*(" + _NUM
                         + r")\s*[*_\"”]*\s*(?:[.,!…]+|—)\s*[*_\"”]*\s*(?=$|\n|[A-Z“\"*_])", re.I)


def _counts(text):
    """Every clock-like number in order: 'Thirty seconds.', 'Second 40', and bare counted numbers."""
    found = [(m.start(), _to_int(m.group(1) or m.group(2))) for m in _TIME_MARK.finditer(text)]
    found += [(m.start(), _to_int(m.group(1))) for m in _BARE_COUNT.finditer(text)]
    return [v for _, v in sorted(found)]


def _counts_down(text):
    """True if the prose counts DOWN (10, 9, 8...) like a referee's count instead of the pin clock counting up:
    two drops in a row (a single drop is usually just a repeated paragraph)."""
    vals = _counts(text)
    return any(a > b > c for a, b, c in zip(vals, vals[1:], vals[2:]))


_REMAINING = re.compile(r"\b" + _NUM + r"\s+(?:more\s+)?seconds?\s+(?:left|remaining|to go|more)\b|\b" + _NUM
                        + r"\s+(?:to go|left|remaining)\b|\bjust\s+" + _NUM
                        + r"\s+more\b|\b" + _NUM + r"\s+more\s+seconds?\b|\b" + _NUM
                        + r"\s+(?:more\s+)?(?:seconds?\s+)?(?:remained|remain|were left|was left|still to go)\b", re.I)


# with no pin clock at all, any counted time in a pin beat is wrong: "held for forty seconds", "Thirty-five now.",
# "Twenty more to go.", "halfway", "a full minute" ("a few seconds", "a second" are fine)
_FADE_CLOCK = re.compile(
    r"\b(?:\d{2,}|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?\s+(?:more\s+)?seconds?\b|\b"
    + _NUM + r"\s+(?:now|more to go|to go|left|remaining|more)\b[.!…,—]|\b(?:past|at|only|not even|barely) halfway\b|"
    r"\bhalf[- ]?way (?:there|through|done|gone|point|mark|to (?:the end|passing out|out))\b|"
    r"\b(?:a|one|the|another|half a|a full|nearly a|almost a) minute\b|\bseconds? (?:left|remaining|to go)\b|"
    r"\bsecond \d+\b|\bthe (?:clock|count)\b", re.I)


def _out_of_order(text):
    """The first clock mark that goes backward ('Thirty seconds.' ... '22 seconds...'), or None."""
    best = -1
    for v in _counts(text):
        if v < best:
            return v
        best = max(best, v)
    return None


def _drop_backward_marks(text):
    """Remove sentences whose clock mark goes back below one already given."""
    best, out = -1, []
    for para in text.split("\n"):
        kept = []
        for sent in re.split(r"(?<=[.!?…])\s+", para):
            vals = _counts(sent)
            if vals and min(vals) < best:
                continue
            if vals:
                best = max(best, max(vals))
            kept.append(sent)
        out.append(" ".join(kept).strip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _bare_count(text, pin=True):
    """A number standing alone as a sentence ("Nine."), read as a count. Under a pin one is enough. With no pin on, a
    lone "One." is just prose ("Two strides. One."): there it takes two of them to be somebody counting."""
    m = _BARE_COUNT.search(text)
    if m and not pin and len(_BARE_COUNT.findall(text)) < 2:
        return None
    return m


def _drop_countdown(text, pin=True):
    """Remove sentences that count a pin clock when no pin is running."""
    out = []
    bare = bool(_bare_count(text, pin))
    for para in text.split("\n"):
        kept = [s for s in re.split(r"(?<=[.!?…])\s+", para)
                if not (_COUNTDOWN.search(s) or (bare and _BARE_COUNT.search(s)) or _TIME_MARK.search(s) or _REMAINING.search(s)
                        or _BARE_MORE.search(s))]
        out.append(" ".join(kept).strip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


WHITESPACE = re.compile(r"\s+")


DETAIL = ("Slow time down and spend the words on concrete detail: exactly where each contact lands and with what, "
          "weight, grip, texture, temperature, sound, breath, the specific quality of each pain, and small physical "
          "tells (ears, tails, fins, claws, eyes). Detail, not filler: no summarizing, no repeating.")


def poss(name):
    """Ripples -> Ripples', Nocturne -> Nocturne's"""
    return f"{name}'" if name.endswith("s") else f"{name}'s"


META_TALK = re.compile(r"(?i)\b(incomplete response|let me try again|you haven'?t provided|i(?:'ll| will| need to| am going to) "
                       r"(?:narrate|write|continue|describe)|what happens in this beat|as an ai|here(?:'s| is) (?:part|the "
                       r"(?:continuation|next part))|(?:the )?(?:user|prompt|instructions) (?:asked|said|wants))")


READER_PROMPT = """You check a passage of a fight story against FACTS that a program has already decided. The facts are
certain. List the places where the passage CONTRADICTS them:
- a fighter falls, is knocked down, lies on the ground, gets up, is pinned or held down, or breaks free, when the
  facts say otherwise;
- a grip, bite, or hold that the facts say STAYS ON is let go, slips off, or is broken;
- an attack, hit, bite, grab, or wound that the facts do not list; or a listed attack made by the wrong fighter or
  with the wrong part of her body (claws for a tail move, teeth when nothing bites);
- a hit on a body part the facts don't list, or on the wrong side (left / right);
- an injury far worse than the facts say (something breaks, a part is useless, dead, or numb, when it is only
  sore, hurting, or very painful);
- a pin clock that runs past the seconds this beat covers, or counts the time left;
- a fighter or creature the facts don't have.
A BEAT TAKES TIME. The TIMELINE at the top of the facts says how each fighter is placed when the beat STARTS and
when it ENDS. A fighter who starts on the ground and ends on her feet is lying down in the first paragraphs and
standing in the last ones: both are correct. Only call a posture wrong if it fits NO moment of the beat.
THE STAGING IS THE WRITER'S. The facts fix what happens and where everyone ENDS; how it gets there is free. These
are NOT contradictions: a fighter who ends on her feet staggering, being driven back, catching herself on a wall or
a boulder, almost falling, or touching a knee or a paw to the ground for an instant before she is up again; a held
or pinned fighter clawing, twisting, bucking or prying at a grip that then stays on; a grip that shifts or slackens
for a moment and clamps down again, still on when the passage ends; the way a grab, a throw or a dodge is carried out; a
blow told with great force when the facts list that blow.
Do NOT list: style, repetition, missing details, feelings, thoughts, breathing, sounds, scenery, small movements
(a paw twitching, a tail stirring, eyes closing: these happen in any posture), figures of speech, or anything the
facts simply don't mention. If a sentence can be read as agreeing with the facts, leave it out.
Most passages have NO real contradiction: an empty list is the usual, correct answer.
For each one give the paragraph number, the exact sentence from the passage, which kind of contradiction it is,
what the facts say instead (the opposite fact itself, such as "Ripples is ON HER FEET from start to end" or "the
hit is on the LEFT shoulder", never a remark about the facts or the passage), and whether you are sure. Say "sure"
only when the facts state the opposite in so many words; otherwise say "unsure"."""
READER_KINDS = ["wrong posture (up / down / pinned)", "a grip that stays on is let go", "attack or wound that is not listed",
                "wrong body part or side", "wrong attacker or weapon", "injury worse than listed",
                "wrong time on the pin clock", "someone who is not there"]
READER_SCHEMA = {"type": "object",
                 "properties": {"problems": {"type": "array", "maxItems": 4, "items": {
                     "type": "object",
                     "properties": {"paragraph": {"type": "integer"}, "sentence": {"type": "string"},
                                    "kind": {"type": "string", "enum": READER_KINDS},
                                    "facts_say": {"type": "string"},
                                    "sure": {"type": "string", "enum": ["sure", "unsure"]}},
                     "required": ["paragraph", "sentence", "kind", "facts_say", "sure"]}}},
                 "required": ["problems"]}
CONFIRM_PROMPT = """A checker says ONE sentence of a fight story contradicts the FACTS a program decided. Checkers are
often wrong, so look again, slowly. Answer "fine" unless the sentence plainly states something and the facts plainly
state the opposite about the same fighter at the same moment.
It is "fine" when: the sentence fits ANY moment of the beat (see the TIMELINE: a fighter can start the beat lying
down and end it standing); it is about breathing, pain, thoughts, sounds, or small movements; it is a figure of
speech; it only tries, wants, nearly does, or fails to do the thing; or the facts simply say nothing about it.
It is a "contradiction" only when no reading of the sentence agrees with the facts."""
CONFIRM_SCHEMA = {"type": "object",
                  "properties": {"reading": {"type": "string"},
                                 "verdict": {"type": "string", "enum": ["fine", "contradiction"]}},
                  "required": ["reading", "verdict"]}
# problems that mean something is MISSING from a draft (it needs writing again, not a paragraph fixed)
MISSING_MARKS = ("never showed", "ESCAPE", "skipped the struggle", "finally getting up", "THE PIN HOLDS this beat",
                 "left out the tumble")
# she is back on her feet (a get-up nobody rolled)
GOT_UP = re.compile(r"\b(?:got (?:back )?(?:up|to her feet|on(?:to)? her feet)|(?:rolled|sprang|leapt|leaped|jumped|scrambled|"
                    r"climbed|pushed(?: herself)?|hauled herself|came|bounced|flipped|surged|rose|lurched|staggered) "
                    r"(?:back )?(?:up(?:right)?|to her feet|on(?:to)? her feet)|(?:back|up) on her feet|on her feet again|"
                    r"regained her feet|found her feet again|stood (?:back )?up|rose to (?:her|all four) (?:feet|paws))\b", re.I)
_UP_TRY = re.compile(r"\b(?:tried|trying|tries|try|struggl\w+|fought|fighting|wanted|want\w*|couldn't|could not|can't|cannot|"
                     r"failed|unable|before she could|if she|would|needed to|had to|meant to|began to|started to|half|"
                     r"halfway|almost|nearly|not|never|no)\b", re.I)
# a blow driven into a part of a fighter named by the sentence ("into the Absol's ribs", "into Nocturne's belly")
BLOW_AT = re.compile(r"\b(?:drove|driving|slamm\w+|smash\w+|ramm\w+|kick\w+|punch\w+|hammer\w+|stomp\w+|stamp\w+|sank|"
                     r"buried|rak\w+|slash\w+)\b[^.!?;]{0,40}?\b(?:into|against|across|onto|down on)\s+(?:the )?"
                     r"([A-Z][\w-]+)(?:'s|’s|'|’) (?:(?:left|right|upper|lower|exposed|soft|unprotected|white|cream) )*"
                     r"([a-z]+)", re.I)
# a body going on across the ground after it lands
TUMBLED = re.compile(r"\b(?:tumbl\w+|roll(?:ed|ing|s) (?:over|across|on|along|end|away|twice|once|again)|skidd?\w*|bounc\w+|"
                     r"cartwheel\w+|skipp\w+ (?:across|over)|sl(?:id|ides|iding) (?:across|along|on|over)|end over end|"
                     r"over and over|spinning across|fetch\w* up|came to rest|came to a stop|rolled to a stop)\b", re.I)


PROMPT_LINE = re.compile(r"^\s*[*_\-\s]*(?:POSTURE THIS BEAT|WHAT HAPPENS IN THIS BEAT|CURRENT CONDITION|PREVIOUS BEATS|"
                         r"FIGHT SO FAR|POSITIONS(?: NOW)?\b|GETTING UP:|LINGER ON ONE MOMENT|MORE HARD RULES|STYLE SAMPLE|"
                         r"THE AUTHOR'S INSTRUCTIONS|EXTRA STYLE NOTE|YOUR (?:PREVIOUS|LAST TWO) DRAFTS?|SCENE:|FIGHTERS:|"
                         r"OVERALL \d|STAY IN THIS MOMENT|THE STORY SO FAR)")


def _balance_marks(text):
    """Keep the * marks around thoughts in pairs. A thought can lose one end when a sentence inside it is cut
    (a repeated line, a stray curse) or when the model forgets to close it:
    '*Slow.' -> '*Slow.*'      'Of course. She got me good.*' -> '*Of course. She got me good.*'"""
    fixed = []
    for line in text.split("\n"):
        # a spoken line that lost its closing mark when what followed it was cut: "AAAHHH!  ->  "AAAHHH!"
        bare = line.strip()
        if bare.count('"') == 1 and "“" not in bare and "”" not in bare:
            if bare.startswith('"'):
                line = line.rstrip() + '"'
            elif bare.endswith('"') and len(bare.split()) <= 12:
                line = line[:len(line) - len(line.lstrip())] + '"' + bare
        elif bare.count("“") == bare.count("”") + 1 and '"' not in bare and bare.startswith("“"):
            line = line.rstrip() + "”"
        if line.count("*") % 2 == 0:
            fixed.append(line)
            continue
        body = line.strip()
        lead = line[:len(line) - len(line.lstrip())]
        sents = re.split(r"(?<=[.!?…])\s+", body)
        short = len(body.split()) <= 25
        if body.startswith("*") and body.count("*") == 1:
            if short or len(sents) == 1:
                body = body + "*"                         # a whole-line thought left open
            else:
                body = sents[0] + "* " + " ".join(sents[1:])  # the thought is the first sentence; prose follows
        elif body.endswith("*") and body.count("*") == 1:
            if short or len(sents) == 1:
                body = "*" + body                         # a whole-line thought missing its opening mark
            else:
                body = " ".join(sents[:-1]) + " *" + sents[-1]
        else:
            body = re.sub(r"\*(?=[^*]*$)", "", body, count=1)  # a lone mark in the middle: drop it
        fixed.append(lead + body)
    return "\n".join(fixed)


_EMPH_IN = re.compile(r"(?<![*\w])\*{1,2}(?![\s*])([^*\n]{1,40}?)(?<![\s*])\*{1,2}(?![*\w])"
                      r"|(?<![_\w])_(?![\s_])([^_\n]{1,40}?)(?<![\s_])_(?![_\w])")


def _plain_emphasis(text):
    """Something *broke*. / a tremendous *CRACK* that... -> the marks go when they wrap a word or two INSIDE a
    sentence. With them on, no check could read the words (the bone check looks for "something broke", and saw
    "something *broke*"). A thought in italics keeps its marks: a whole line, anything with its own full stop inside
    (*Not yet.*), or a short one that opens a sentence and stands alone (*Now*, she thought)."""
    def fix(line):
        def one(m):
            inner = m.group(1) or m.group(2)
            if len(inner.split()) > 3 or re.search(r"[.!?…]", inner):
                return m.group(0)
            before, after = line[:m.start()].rstrip(), line[m.end():]
            starts = not before or before[-1] in ".!?…\"“”:"
            if starts and not after.strip(" .!?…—\"”"):
                return m.group(0)                      # the whole line (or its last sentence) is the thought
            if starts and not inner.isupper() and re.match(r"\s*[,.!?…—]", after):
                return m.group(0)                      # *Now*, she thought.
            return inner
        return _EMPH_IN.sub(one, line) if ("*" in line or "_" in line) else line
    return "\n".join(fix(l) for l in (text or "").split("\n"))


def _clean(text, cut_off=None, open_end=False):
    """Strip any <thinking> block and drop repeated sentences (a safety net against loops).
    cut_off: True when the model was stopped by the word limit (its last half-sentence is cut), False when it ended
    there by itself (a last sentence left open is a thought broken off on purpose: it is kept, closed with a dash),
    None when that is not known (the old rule: cut, unless open_end says an unfinished thought was asked for)."""
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.S | re.I).strip()
    text = re.sub(r"</?thinking>", "", text, flags=re.I)
    text = re.sub(r"(?im)^\s*\**\s*part\s+\d+\s+of\s+\d+\s*\**\s*:?\s*$", "", text)  # "PART 1 OF 2" labels
    # the model talking about the task instead of telling the story
    text = re.sub(r"(?im)^\s*[\[(][^\])\n]*(?:understood|i will|i'll|narrat|part \d|beat \d|hard rules|as instructed)"
                  r"[^\])\n]*[\])]\s*$", "", text)
    text = re.sub(r"(?i)[*_(\[]*\s*(?:later part to follow|to be continued|continued in the next part|"
                  r"end of part \d+|part \d+ ends here)\.?\s*[*_)\]]*|\((?:continued|cont\.?)\)", "", text)
    # the prompt's own lines copied into the story ("POSTURE THIS BEAT (certain; the program tracks it): ...")
    text = "\n".join(l for l in text.split("\n") if not PROMPT_LINE.match(l))
    # the model talking to the user mid-story ("This is an incomplete response... Let me try again")
    text = "\n".join(l for l in text.split("\n") if not META_TALK.search(l))
    # a stray, unmatched * (a thought marker the model opened or closed by itself)
    text = _balance_marks(text)
    text = _plain_emphasis(text)   # Something *broke*. -> Something broke. (so the checks can read it)
    # common model slips: a tail "hashing" is a tail lashing
    text = re.sub(r"(?i)\b(tails?\W+(?:\w+\W+){0,2}?)hash(ing|ed|es)\b", r"\1lash\2", text)
    text = re.sub(r"(?i)\bhash(ing|ed|es) (behind|back and forth|once|hard|side to side)", r"lash\1 \2", text)
    # drop markdown scaffolding the model sometimes adds: headings, rules, perspective labels
    text = userprompt.strip_stats(text)  # invented stat lines never reach the reader
    text = "\n".join(l for l in text.split("\n")
                     if not re.match(r"^\s*(#{1,6}\s|-{3,}\s*$|\*{3,}\s*$|_{3,}\s*$)", l)
                     and not re.match(r"^\s*\**\s*(from\s+.{1,40}?perspective|beat\s+\d+)\s*:?\**\s*:?\s*$", l, re.I))
    out_paras, seen = [], set()
    for para in text.split("\n"):
        sentences = re.split(r"(?<=[.!?…])\s+", para.strip())
        kept = []
        for s in sentences:
            key = WHITESPACE.sub(" ", re.sub(r"[^\w\s]", "", s.lower())).strip()
            if key in seen and (len(key) > 12 or (len(key) > 4 and len(sentences) == 1)):
                continue  # a repeated sentence, or a repeated one-line beat like "*Damn it.*" / "Nothing moved."
            seen.add(key)
            kept.append(s)
        out_paras.append(" ".join(kept).strip())
    text = "\n".join(out_paras)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # cut a dangling half-sentence if generation stopped mid-thought
    if text and text[-1] not in ".!?…\"'”’—)]*" and re.search(r"[.!?…]", text):
        at = max(text.rfind("."), text.rfind("!"), text.rfind("?"), text.rfind("…")) + 1
        tail = text[at:].strip()
        deliberate = (cut_off is False or (cut_off is None and open_end)) and 2 <= len(tail.split()) <= 14 \
            and "\n" not in tail and re.match(r"[*_\"“]?[A-Z]", tail)
        if deliberate:
            text = text.rstrip(" ,;:") + "—" + ("*" if tail.startswith("*") and tail.count("*") == 1 else "")
        elif cut_off is False and len(tail.split()) > 14:
            text = text.rstrip(" ,;:") + "."     # she ended there herself: a whole sentence that only lacks its stop
        else:
            text = text[:at]
    return text


_PLAIN_WORDS = frozenset("""
that this then than them they were been with from into onto upon over under have having what when where while which who whom
whose there their theirs here herself himself itself yourself your yours mine ours about above after again against
almost along already also although always among another anything around away back because before behind being below
beneath beside between beyond both cannot could does doing done down during each either else enough even ever every
everything first from further gave give given goes going gone half hard have just keep kept knew know known last
least left less like little long made make many might more most much must near nearly neither never next none nothing
once only other others ought over part past rather right same seem seemed second shall should since some something
somewhere soon still such sure take taken tell than that the then these thing things think this those though thought
three through time times together told took toward towards twice under until very want wanted well went were what whatever
whether will with within without would came come comes coming felt feel feels feeling find found gets getting got held
hold holding holds look looked looking looks moved move moves moving put said saw see seeing seen sees set tried tries
try trying turn turned turning turns used went she her hers him his its was had did not but and for are you all any can
out one two now how off too way own let yet has who why got get put set saw see say ran run lay lie sat sit far few
old new big low end top bit per nor may our use ago yes met led hit cut side face body head neck chest belly back tail tails paw paws leg legs foot
feet arm arms shoulder shoulders eye eyes mouth jaw jaws teeth claw claws throat ribs stomach hip hips knee knees ear ears
fur skin breath breathe breathing air ground floor weight place beat beats front hind upper lower inside outside small
""".split())


# how a takedown into a pin goes (the engine picks one: variety.takedown)
TAKEDOWN_WAYS = {
    "tackle": "a low tackle that takes both of them to the ground, her underneath",
    "leg_hook": "a limb hooked behind her leg and her own weight shoved back over it",
    "sweep": "her legs swept out from under her from the side, so she drops where she stood",
    "hip_throw": "caught round the middle, turned over a hip or a shoulder, and put down on the ground",
    "shoulder_drive": "a shoulder driven into her middle that folds her and carries her down backward",
    "drag_down": "seized and dragged down by sheer weight, fighting it all the way to the ground",
    "spin_down": "caught, spun half round by her own momentum, and brought down off balance",
    "trip_back": "walked backward faster than her feet can go until they tangle and she goes over",
    "pull_forward": "hauled forward off her feet by the limb or the scruff, so she goes down on her front",
    "ride_down": "taken from behind, her legs folded under the weight on her back until she is flat on her front",
}


class Narrator:
    def __init__(self, model, rules, host="http://localhost:11434", style=""):
        self.model, self.rules, self.host, self.style = model, rules, host, style
        self.progress = None  # optional callback: shows "writing part 2/3" while the model works
        self._tiers_used = set()
        self._must_parts = []       # body parts this beat's prose has to show being hit (accuracy check)
        self._must_struggle = None  # a pin struggle the prose has to show
        self._time_window = None    # (from, to) seconds of a pin clock this beat covers
        self._no_clock = False      # True when no pin runs this beat: no countdowns allowed
        self.facing = {}            # downed fighter -> face-down / face-up / on her side (after this beat)
        self.damage_by = {}         # fighter -> {body part (lowercase) -> damage}, set before each beat
        self.part_damage = {}       # body part (lowercase) -> highest damage on any fighter, set before each beat
        self.breakable = set()      # body parts (lowercase) whose bones may now break
        self._part_leads, self._lead_now, self._prior_now = {}, None, ""   # whose side each part of a beat is told from
        self.tally = None           # "thrown|Ripples" -> times so far this fight (None = not known: counts unchecked)
        self.recent_reactions = []  # reaction labels used in each of the last beats (repetition tracker)
        self.strengths = {}         # fighter -> % of full strength, set before each beat (collapse check)
        self.recent_lines = []      # thoughts, spoken lines and pain sounds from the last beats (dialogue variety)
        self._beat_no = 0
        self.on_ground = set()      # fighters the program has on the ground (or pinned) at any point this beat
        self.grips = []             # (holder, held, part, with) for every hold still on when the beat ends
        self._grip_seen = {}        # (holder, held) -> (part, with) of the last grip she had on her
        self._grip_gone = {}        # (holder, held) -> the beat that grip ended in
        self.aliases = {}           # species word -> fighter ("Buizel" -> "Ripples"), so "the Buizel" is attributed
        self.out_names = []         # fighters who are out of the fight (sentences about them aren't posture-checked)
        self.silent_out = []        # names and species of fighters who are out and never hurt anyone: not to be mentioned
        self.absent_words = []      # names and species of fighters who are NOT in this fight at all: never mentioned
        self.posture_start = {}     # fighter -> posture when this beat began (from the engine)
        self.posture_end = {}       # fighter -> posture when it ends
        self._no_electric = False   # True when this beat's moves have nothing electric in them
        self._getup_tries = None    # how many tries a get-up this beat takes (1 = no failed attempts)
        self._strike_parts = []     # parts hit by strikes this beat (not pin pressure)
        self.fight_seen = set()     # short sentences this fight has already used, word for word
        self.foreign_words = []     # body features nobody in this fight has ("scales" with no Milotic in it)
        self._weapons_ok = None     # claws / teeth / tail / horn named by this beat's moves (None: not a fight beat)
        self._attackers = set()
        self._landed = set()        # fighters who crash into scenery this beat (their impacts are real)
        self._linger_pool = []      # (fighter, part, damage, pain label, kind) for every hit this beat
        self._hurt_now = None       # fighters actually hit this beat (None = not a fight beat)
        self._breaking = []         # parts that just crossed into excruciating/devastated this beat
        self._important = False     # big beats get two drafts (best_of_two)

    # ---------- turning engine results into plain English ----------
    def _pain(self, dmg):
        return tier_for(dmg, pain_tiers(self.rules))

    # how hard the moment of impact is, independent of WHERE it lands (the region tell covers that)
    IMPACTS = {
        "glancing": ["barely registers", "a flick of annoyance", "a sharp breath", "a twitch, nothing more",
                     "a blink and a shake of the head"],
        "solid": ["a grunt and a half-step back", "a hiss through the teeth", "a wince that tightens the whole face",
                  "a jolt that runs through the whole body", "a startled huff", "a sharp, surprised yelp",
                  "a flinch and a bitten-off sound", "a quick breath sucked in through the nose"],
        "heavy": ["a sharp cry and a stagger", "a choked gasp and a lurch sideways", "a full-body jerk away from the blow",
                  "a snarl of pain, balance lost and found again", "eyes squeezed shut for a heartbeat, a ragged breath",
                  "a yelp that cracks in the middle", "teeth clenched on a cry that gets out anyway",
                  "the breath punched out in one bark, eyes watering",
                  "a flinch so hard the whole body curls round the spot"],
        "tremendous": ["a scream as the body is knocked off balance", "a cry cut short by the force of it",
                       "the whole body rocking with the force of it", "a howl, the body folding around the blow",
                       "a stunned half-second of silence, then a ragged cry", "a sound that is more shock than pain",
                       "mouth wide open in a silent scream, eyes squeezed shut",
                       "a shriek that breaks off into a wheeze", "the head thrown back, a raw cry at the sky",
                       "every limb going rigid for a heartbeat, then a ragged gulp of breath",
                       "a keening whine through clenched teeth, tears starting",
                       "the back arching off the blow, a cry with no air behind it"],
    }

    # how a hit to each body region tends to show, so reactions fit WHERE the blow landed
    REGION_TELLS = [
        (("ear",), "ears flattening or ringing, the head jerking away"),
        (("eye", "face", "muzzle", "nose", "cheek", "jaw", "head", "horn", "spike", "antenna", "head fin"),
         "eyes squeezing shut or watering, the whole face flinching, teeth gritted"),
        (("neck", "throat", "sac"), "the breath catching, a choked cough, swallowing hard"),
        (("chest", "rib", "ruff"), "the breath knocked out, then shallow, careful breathing"),
        (("belly", "stomach", "midsection", "flank", "scales"), "folding or curling around the spot, a hollow, sick feeling"),
        (("back", "spine", "shoulder"), "arching away from it, a stiff, guarded posture after"),
        (("hip", "thigh", "leg", "foreleg", "hock", "knee", "paw", "foot", "arm", "fin"),
         "a limb buckling or jerking back, then favoring it and testing weight on it"),
        (("tail", "fan"), "the tail jerking, curling in protectively, or going still"),
    ]

    def _limb_note(self, defender, part):
        """For a fighter who stands upright with arms, say plainly whether a part is on her arm or her leg, so a hurt
        'paw' (hand) isn't narrated as a foot, or the reverse."""
        parts = " ".join((getattr(self, "damage_by", {}) or {}).get(defender, {}))
        if "arm" not in parts:
            return ""
        region = body_region(part)
        if region in ("fore_up", "fore_low"):
            hand = re.search(r"\b(paw|hand)\b", part.lower())
            return (" (her HAND, at the end of her arm: she doesn't stand on it)" if hand
                    else " (on her ARM, not a leg)")
        if region in ("hind_up", "hind_low"):
            return " (her leg: she stands on it)"
        return ""

    def _region_tell(self, part):
        p = part.lower()
        for keys, tell in self.REGION_TELLS:  # whole words: "forearm" must not count as an "ear"
            if any(re.search(r"\b\w*" + re.escape(k) + r"(?:s|es)?\b", p) for k in keys):
                return tell
        return "a flinch away from the spot"

    def _relative(self, taken):
        """Damage relative to the damage scale, so /scale doesn't make every hit 'tremendous'."""
        scale = float(self.rules.get("damage", {}).get("damage_scale", 2.5) or 2.5)
        return taken * 2.5 / scale

    def _strength_key(self, taken):
        t = self._relative(taken)
        return "glancing" if t < 5 else "solid" if t < 15 else "heavy" if t < 30 else "tremendous"

    def _strength(self, taken):
        return "a " + self._strength_key(taken)

    def _impact(self, taken, seed=""):
        """A suggested moment-of-impact reaction, varied from hit to hit."""
        options = self.IMPACTS[self._strength_key(taken)]
        return options[sum(map(ord, seed)) % len(options)]

    def _hold_word(self, power):
        table = self.rules["severity"]["hold"]
        return min(table, key=lambda k: abs(table[k] - power))

    FEEL_STEPS = [(120, "armored"), (100, "sturdy, barely marked"), (85, "sturdy"), (72, "starting to give"),
                  (60, "weakened"), (50, "soft, giving under blows"), (40, "thin and vulnerable"),
                  (28, "thin, close to giving way"), (-1e9, "fragile and exposed")]

    def _feel(self, res):
        """How tough a part still is, in words. With resistance.smooth on, finer steps that follow the gradient (so the
        story softens a part as gradually as the numbers do); otherwise the bracket's own word."""
        if (self.rules.get("resistance", {}).get("smooth") or {}).get("enabled", False):
            return next(w for at, w in self.FEEL_STEPS if float(res) >= at)
        return tier_for(res, self.rules["resistance"]["brackets"]).get("feel", "")

    def _hit_line(self, h, n=None, how=None):
        before, after = self._pain(h["damage_before"]), self._pain(h["damage_after"])
        self._tiers_used.add(after["label"])
        change = (f"lasting pain {before['label']} → {after['label'].upper()}" if before["label"] != after["label"]
                  else f"lasting pain still {after['label']}")
        fb, fa = self._feel(h["res_before"]), self._feel(h["res_after"])
        tough = (f"; its toughness drops from {fb} to {fa} (it will take the next hit worse)"
                 if fb != fa and fa else "")
        if float(h.get("res_after", 100)) <= 55 and after["label"] in ("minor", "sore", "hurting"):
            tough += ("; it doesn't hurt much yet, but it has gone SOFT: it's holding for now and won't hold many more "
                      "(she can feel it, and so can a careful opponent)")
        label = f"Hit {n}: " if n else ""
        if before["label"] != after["label"] and after["label"] in ("excruciating", "devastated", "numb with shock"):
            self._breaking.append((h["defender"], h["part"], after["label"]))
        seed = f"{h['defender']}{h['part']}{h['damage_after']:.1f}"
        self._must_parts.append(h["part"])
        self._strike_parts.append(h["part"])
        self._hurt_now.add(h["defender"])
        self._linger_pool.append((h["defender"], h["part"], h["damage_taken"], after["label"], "blow"))
        impact = self._impact(h["damage_taken"], seed)
        if after["label"] == "numb with shock" and before["label"] == "numb with shock":
            impact = "a dull, sickening jolt she barely feels as pain, then a lurch of nausea and shallow breath"
        raw = self._raw_reaction(h, before["label"])
        if raw:
            impact = raw
        if how:
            # not a blow: something that stays on her and keeps working (the water of a charge that carries her)
            return (f"  - {label}{poss(h['defender'])} {h['part']}{self._limb_note(h['defender'], h['part'])}: "
                    f"{how}, {self._strength_key(h['damage_taken'])} in size"
                    + (f" ({raw})" if raw else "") + f"; {change}{tough}.")
        return (f"  - {label}{poss(h['defender'])} {h['part']}{self._limb_note(h['defender'], h['part'])}: "
                f"{self._strength(h['damage_taken'])} blow "
                f"(impact, e.g. {impact}; a hit here shows as "
                f"{self._region_tell(h['part'])}); {change}{tough}.")

    # a blow on a part that was ALREADY badly hurt. Three things set how raw the reaction is: how hurt the part was
    # (very painful < excruciating < devastated), how big THIS blow is (a brush on a ruined part still hurts, but far
    # less than a real blow there), and how much she has left overall. A fighter with most of her strength does her
    # best to keep it in; only a fighter who is nearly spent has nothing left to hold it in with.
    RAW_LEVELS = [
        ("contained", "it hurts far more than a blow like that should, because the part was already hurt: a sharp hiss "
                      "through her teeth, the part snatched away from it, a flinch she cannot hide, then she sets her "
                      "jaw and keeps it in"),
        ("cry", "a cry she cannot keep in, bitten off as soon as it is out; the part jerked away, a hard shudder through "
                "her, and she makes herself go on, which costs her and shows"),
        ("scream", "a real scream, her whole body jerking round the hurt part; she shakes afterwards, her breath comes in "
                   "ragged pulls, and it is a moment before she can do anything at all"),
        ("raw", "a raw scream that cracks in the middle, all of her clenching round the hurt; her body reacts on its own "
                "now, past anything she can restrain: jerking and curling round it, a limb scrabbling at the ground, "
                "shaking she cannot stop, eyes streaming, a long moment where there is nothing in her head but "
                "that part"),
    ]

    def _raw_reaction(self, h, before_label):
        """The impact note for a real blow on a part that was already very painful or worse, or None (the ordinary
        note stands). narration.raw_reactions false turns it off."""
        ncfg = self.rules.get("narration", {})
        dev = bool(h.get("devastating"))
        if not ncfg.get("raw_reactions", True) or (before_label not in ("very painful", "excruciating", "devastated")
                                                   and not dev):
            return None
        who = h["defender"]
        size = self._strength_key(h["damage_taken"])
        part_score = {"very painful": 0, "excruciating": 1, "devastated": 2}.get(before_label, 1)
        size_score = {"glancing": -2, "solid": 0, "heavy": 1, "tremendous": 2}[size]
        # how much she has left as THIS blow lands (not at the end of the beat: in a long pummel the first blow
        # finds her stronger than the last)
        top = h.get("max_health") or (getattr(self, "max_health", None) or {}).get(who)
        if top and h.get("health_before") is not None:
            left = 100.0 * float(h["health_before"]) / float(top)
        else:
            left = float((getattr(self, "strengths", None) or {}).get(who, 100))
        cond_score = 0 if left >= 60 else 1 if left >= 30 else 2
        level = max(0, min(3, (part_score + size_score + 2 * cond_score + 1) // 2))
        # overall strength caps it: a fighter who still has most of her strength holds it in, a middling one can
        # scream but not come apart, only a spent one has the rawest reactions
        level = min(level, 1 + cond_score)
        if size == "glancing":
            if before_label == "devastated":
                # a part this ruined hurts at the slightest touch: even a brush gets a real reaction, and the less
                # she has left the less of it she can hold in
                level = max(min(level, 1 + cond_score), cond_score, 1)
            elif before_label == "excruciating" and cond_score == 2:
                level = min(max(level, 1), 2)
            else:
                level = min(level, 1)
        # the part wasn't hurt before this blow, or isn't badly hurt even now: a shock and a cry, never the rawest
        held_up = dev and (float(h.get("damage_before", 0)) < 90 or float(h.get("damage_after", 0)) < 150)
        if held_up:
            # devastating, but the part isn't ruined and she still has most of her strength: a cry she can't stop,
            # not a scream
            level = 1
        elif dev:
            # a devastating blow: nobody holds that in. At least a scream, and one step past what her strength
            # would normally allow
            level = max(2, min(3, max(level, 2 + cond_score)))
        self.__dict__.setdefault("_raw_done", {})
        self.__dict__.setdefault("_raw_parts", {})
        done = self._raw_done.get(who)
        if done is not None:
            # the first raw blow this beat had its moment: later ones on her build on it instead of each getting a
            # fresh scream, so a beat never becomes a string of them
            first = self._raw_parts.get(who)
            what = ("the same hurt struck again" if first == h["part"] else
                    f"another hurt part ({h['part'].lower()}) struck")
            return (f"{what} before the last has faded; it adds to what is already happening to her (a fresh jolt "
                    f"through the shaking, the sound she is making catching and going higher) rather than a whole "
                    f"new reaction")
        self._raw_done[who] = level
        self._raw_parts[who] = h["part"]
        name, text = self.RAW_LEVELS[level]
        lead = {"glancing": ("only a brush, but on a part this ruined even a touch is agony: "
                             if before_label == "devastated" else "only a brush, on a part that is already "
                             f"{before_label}: smaller than a full blow there would be, but "),
                "solid": f"a real blow on a part that was already {before_label}: ",
                "heavy": f"a heavy blow on a part that was already {before_label}: ",
                "tremendous": f"a tremendous blow on a part that was already {before_label}: "}[size]
        if dev:
            lead = ("a DEVASTATING blow" + (f" on a part that was already {before_label}"
                                            if before_label in ("very painful", "excruciating", "devastated") else "")
                    + ", far worse than anything like it before: ")
        held = ((" She still has most of her strength and the part isn't ruined: the cry is out before she can stop it, "
                 "but she clamps down on the rest. No scream." if cond_score == 0 else
                 (" The part was untouched before this blow" if float(h.get("damage_before", 0)) < 90 else
                  " The part itself isn't badly hurt") +
                 ": it is a deep shock through a body already trembling, a cry that gets out, the rest of her jolting "
                 "with it, but not the raw breakdown a part that was already ruined would bring.")
                if held_up
                else " Even with most of her strength left, she can't keep this one in." if dev and cond_score == 0
                else " She still has most of her strength, so she fights to keep it in, and mostly does." if cond_score == 0
                else " She is too worn to hold all of it in." if cond_score == 1
                else " She has almost nothing left to hold it in with.")
        return (lead + text + "." + held + " It is pain, nothing more: nothing breaks or tears unless listed, she "
                "stays conscious, and there is no sobbing or weeping")

    def _pressure_line(self, h, with_=""):
        """One compact line per pin/hold contact, so long pins don't drown the beat in repetition."""
        before, after = self._pain(h["damage_before"]), self._pain(h["damage_after"])
        self._tiers_used.add(after["label"])
        self._must_parts.append(h["part"])
        self._hurt_now.add(h["defender"])
        self._linger_pool.append((h["defender"], h["part"], h["damage_taken"], after["label"], "pressure"))
        change = (f"{before['label']} → {after['label'].upper()}" if before["label"] != after["label"]
                  else f"still {after['label']}")
        if before["label"] != after["label"] and after["label"] in ("excruciating", "devastated", "numb with shock") \
                and not any(b[:2] == (h["defender"], h["part"]) for b in self._breaking):
            # a squeeze can push a part over the line too: a grip or a pin's press, not only a blow
            self._breaking.append((h["defender"], h["part"], after["label"]))
        note = ""
        top = h.get("max_health") or (getattr(self, "max_health", None) or {}).get(h["defender"])
        left = (100.0 * float(h["health_before"]) / float(top)) if top and h.get("health_before") is not None else 100.0
        if float(h["damage_before"]) >= 300:
            note = (" — the part is RUINED: even steady pressure on it is agony"
                    + (", and she is past holding back her body's reactions to it (jerking, a raw sound with every "
                       "breath, the limb trying to pull away on its own)" if left < 30 else
                       ", and it shows however hard she tries to keep it in" if left < 60 else
                       ", and keeping it in takes everything she has"))
        elif float(h["damage_before"]) >= 150:
            note = " — the part can't bear pressure: every bit of it tells"
        return (f"    • {h['part']}" + (f" ({with_})" if with_ else "") + f": {self._strength(h['damage_taken'])} squeeze, "
                f"{change}{note}")

    def _many_hits(self, hits):
        """Whole-body attacks: summarize instead of listing 30+ lines."""
        changed = [h for h in hits if h["pain_tier_changed"] or self._feel(h["res_before"]) != self._feel(h["res_after"])]
        worst = sorted(hits, key=lambda h: -h["damage_taken"])[:4]
        lines = [f"  - It hits EVERY part of {hits[0]['defender']} at once ({len(hits)} body parts): ONE surge through "
                 f"the whole body, all at the same instant. Do not narrate it as a series of separate strikes on "
                 f"each part; describe the whole body seizing, then where it hurts most afterward."]
        mark = len(self._must_parts)
        for h in hits:      # a whole-body hit can push parts over the line as well
            b_, a_ = self._pain(h["damage_before"])["label"], self._pain(h["damage_after"])["label"]
            if b_ != a_ and a_ in ("excruciating", "devastated", "numb with shock"):
                self._breaking.append((h["defender"], h["part"], a_))
        lines.append("  - Hardest hit: " + ", ".join(f"{h['part']} ({self._strength(h['damage_taken'])} blow)" for h in worst))
        tough = [h for h in hits if h["damage_taken"] < 5]
        if tough:
            lines.append("  - Barely felt: " + ", ".join(h["part"] for h in tough[:6]))
        for h in changed[:6]:
            lines.append(self._hit_line(h))
        self._must_parts[mark:] = [h["part"] for h in worst[:2]]  # only the worst spots must be named
        return lines

    def describe(self, bundle):
        self._ongoing = any(e["type"] in ("pin_progress", "hold_ongoing") for e in bundle.get("also_this_beat", []))
        self._tiers_used = set()
        self._must_parts = []
        self._must_struggle = None
        self._struggle_kind = None
        self._breaking = []
        self._hurt_now = set()
        self._strike_parts = []
        self._linger_pool = []
        self._raw_done = {}         # fighter -> the raw reaction already asked for this beat (one big one per beat)
        self._raw_parts = {}        # fighter -> the part that had it
        self._getup_tries = None
        self._getup_who = None
        self._getup_event = None
        self._faint = None          # (who faints, who pinned her, seconds) on the beat a pin is held to the end
        self._must_reposition = None
        self._must_manhandle = None
        self._must_rise = None      # thrown, rolled through the landing: the passage has to end with her on her feet
        self._must_event = None     # the arena did something by itself this beat: it has to be in the passage
        self._any_grip = bool(getattr(self, "grips", None)) or any(
            isinstance(x, dict) and x.get("type") in ("pin_start", "pin_forced", "pin_progress", "hold_start",
                                                      "hold_ongoing", "hold_end", "pin_broken", "pin_left",
                                                      "grapple_start")
            for x in self._all_dicts(bundle))
        self._getup_failed = {e["fighter"] for e in bundle.get("also_this_beat", []) or []
                              if e.get("type") == "get_up" and not e.get("stands")}
        self._one_strike = None
        self._chain_beat = False    # several attacks by one fighter this beat (a chain, a pummel): "again" is right
        self._must_tumble = None    # thrown and tumbling on: the passage has to show her going on across the ground
        actions = bundle.get("actions") or [bundle["action"]]
        self._weapons_ok = self._weapons_named(bundle)
        if any(isinstance(a, dict) and (a.get("type") == "reposition" or a.get("manhandle")) for a in actions):
            self._weapons_ok = set(self._weapons_ok) | {"teeth"}   # hauled by the scruff: jaws are a way to carry her
        self._bite_victims = self._bitten(bundle)
        # pairs whose hold really did end or was shaken loose this beat (so a "let go" between them is right)
        self._grips_ended = {(x.get("attacker"), x.get("defender")) for x in self._all_dicts(bundle)
                             if x.get("type") in ("hold_end", "pin_broken", "pin_left") and x.get("attacker")}
        # which grips are on, and which have gone: a grip that ended must not be told as still on in later beats
        live = {(g[0], g[1]) for g in (getattr(self, "grips", None) or [])}
        seen, gone = getattr(self, "_grip_seen", None), getattr(self, "_grip_gone", None)
        if seen is None or gone is None:
            seen, gone = self._grip_seen, self._grip_gone = {}, {}
        for g in (getattr(self, "grips", None) or []):
            seen[(g[0], g[1])] = (g[2], g[3] or "")
            gone.pop((g[0], g[1]), None)
        for pair in self._grips_ended:
            if pair not in live:
                gone.setdefault(pair, self._beat_no)
        self._parts_now = self._parts_hit(bundle)
        self._pin_holds = None   # (pinners, pinned, how the struggle went) when a pin is still on as the beat ends
        evs = bundle.get("also_this_beat", []) or []
        rolled = {e["fighter"] for e in evs if e.get("type") == "get_up"}
        # down this beat with no get-up roll: she doesn't try to rise (not even a failed try)
        self._no_getup = {e["fighter"] for e in evs if e.get("type") == "stays_down"} - rolled
        self._attackers = {a.get("attacker") for a in actions if a.get("type") == "instant" and a.get("attacker")}
        # the aftermath, or a beat where someone drops out: bodies lie around, so the "she's on her feet" check rests
        self._calm_beat = bool(bundle.get("after_win")) or any(
            a.get("type") in ("eliminated", "aftermath", "pinfall") or a.get("elimination") for a in actions) or any(
            e.get("elimination") or e.get("type") == "recovery" for e in bundle.get("also_this_beat", []))
        # fighters thrown into the scenery this beat may hit walls or stone without that being an invented fall
        self._landed = {a.get("defender") for a in actions if a.get("environment") or a.get("sustain")}
        # a pinner thrown down by an escape goes to the ground this beat too
        self._landed |= {e["pinner_down"]["fighter"] for e in evs if isinstance(e.get("pinner_down"), dict)}
        # a fighter who slips as she dodges on slick footing really does go down
        self._landed |= {a.get("defender") for a in actions if a.get("slipped")}
        self._rolled_up = {a.get("defender") for a in actions if a.get("environment") and a.get("kept_feet")}
        # holds worked looser this beat (still on): "the coil slackened" is right for these, "let go" is not
        self._loosened = {(e.get("attacker"), e.get("defender")) for e in evs if e.get("type") == "hold_loosened"}
        # charged into the scenery: she hits it either way; whether she then goes down is the crumple roll
        rammed = {a.get("defender"): a["charge"] for a in actions if a.get("charge") and not a["charge"].get("skipped")}
        fell = {e["fighter"] for e in bundle.get("also_this_beat", []) if e.get("type") == "crumple" and e.get("down")}
        self._landed |= {d for d, ch in rammed.items() if ch.get("broke") or d in fell}
        self._slammed = {d for d in rammed if d not in self._landed}  # hit the scenery but kept her feet
        self._charge_beat = bool(rammed)
        moves = [m for a in actions for m in [a.get("move")] + list((a.get("move_by_defender") or {}).values()) if m]
        self._no_electric = bool(moves) and not any(str(m.get("type", "")).lower() == "electric" for m in moves) \
            and not any(a.get("status_move") for a in actions)
        # anyone touched by a tick, landing, pin, or the like counts as hurt (only clean beats get the check)
        for e in bundle.get("also_this_beat", []):
            for k in ("fighter", "defender"):
                if e.get(k):
                    self._hurt_now.add(e[k])
            for who in e.get("fighters") or []:
                self._hurt_now.add(who)   # the arena itself caught her this beat
        lines = self._posture_lines()
        for i, a in enumerate(actions):
            part = self._describe_action(a)
            if len(actions) > 1:
                part[0] = (f"{i + 1}. " if i == 0 else f"{i + 1}. Then, ") + part[0]
            lines += part
        pins = [e for e in bundle.get("also_this_beat", []) if e["type"] == "pin_progress"]
        for e in pins:  # the struggle outcome goes first so it can't get lost under the pressure lines
            lines += self._pin_lines(e)
        pairs = {}
        eng = getattr(self, "engine", None)
        self._sub_of = {}
        for e in bundle.get("also_this_beat", []):
            if e["type"] == "hold_ongoing" and e.get("sub"):
                self._sub_of[(e["attacker"], e["defender"])] = e["sub"]
        for e in bundle.get("also_this_beat", []):
            if e["type"] == "hold_ongoing":
                pairs.setdefault((e["attacker"], e["defender"]), []).append(e)
        for (att, dfn), evs in pairs.items():
            pinned = any(p["attacker"] == att and p["defender"] == dfn for p in pins)
            kind = "pin" if pinned else "hold"
            old = [e for e in evs if not e.get("first")]
            new = [e for e in evs if e.get("first")]
            if old and all(e.get("grab") for e in old) and not pinned:
                lines.append(f"{poss(att)} GRAB keeps hold of {dfn} (held {max(e['beats_held'] for e in old)} beat(s)): "
                             f"the two are still locked together at point-blank"
                             + ("" if dfn in getattr(self, "on_ground", ()) else ", both on their feet")
                             + f". The grip itself only pinches, on these spots (it is not a strike):")
                lines += [self._pressure_line(e["hits"][0], e.get("with", "")) for e in old]
            elif old and getattr(self, "_sub_of", {}).get((att, dfn)):
                name = self._sub_of[(att, dfn)]
                lines.append(f"{poss(att)} {name.upper()} goes on (held {max(e['beats_held'] for e in old)} beat(s)): "
                             f"she cranks it harder, and the strain on these spots is WORSE than the beat before "
                             f"(a hold, not a strike; she is wrenched, not hit):")
                lines += [self._pressure_line(e["hits"][0], e.get("with", "")) for e in old]
            elif old:
                # (a pin is as old as its newest press: a grip that was on before the pin began does not age it)
                lines.append(f"{poss(att)} {kind} keeps pressing {dfn} (held {(min if pinned else max)(e['beats_held'] for e in old)} "
                             f"beat(s)); pressure lands ONLY on these spots, no new strikes:")
                lines += [self._pressure_line(e["hits"][0], e.get("with", "")) for e in old]
            coiled = [e for e in evs if e.get("coil")]
            scopes = {Engine.coil_scope(e["hits"][0]["part"]) for e in coiled if e.get("hits")}
            if coiled and scopes == {"limb"}:
                e0 = coiled[0]
                what = re.sub(r"\s*,.*$", "", e0.get("with") or "her coils").replace("her ", f"{poss(att)} ", 1)
                part = e0["hits"][0]["part"].lower()
                lines.append(f"  - BOUND: {what} wound tight round {poss(dfn)} {part}"
                             + (" and TIGHTEN again this beat" if max(e["beats_held"] for e in coiled) > 1 else "")
                             + f". Only that limb is caught: it goes numb and tingling, weak and slow to answer, "
                             f"and she can't move freely with it held. Her breath, her blood and the rest of her are "
                             f"her own. Squeezing, not striking: no new wounds.")
            elif coiled:
                beats = max(e["beats_held"] for e in evs)
                throat = scopes == {"throat"}
                more = ", worse than the beat before" if beats > 1 else ""
                if throat:
                    feel = (f". They squeeze the SIDES of her NECK: the blood to her head held back, pressure pounding "
                            f"behind her eyes, a roaring in her ears, her sight greying at the edges, her breath "
                            f"thin as well{more}. Squeezing, not striking: no new wounds.")
                else:
                    feel = (f". They work on her BLOOD more than her breath: her circulation cut off where they hold, "
                            f"the trapped limbs going cold, heavy and tingling, her pulse pounding in her ears and then "
                            f"slowing, her sight greying at the edges, each breath shorter{more}. Her heart slows; it "
                            f"never stops. Squeezing, not striking: no new wounds.")
                lines.append(f"  - COILS: {poss(att)} "
                             + ("tails are wound round her throat" if throat else f"coils are wound round {dfn}")
                             + (" and TIGHTEN again this beat" if beats > 1 else ", and they will tighten every beat")
                             + feel)
            if new:
                lines.append(f"{poss(att)} {'press' if pinned else 'grip'} CLOSES on {dfn} this beat and hurts at once: the "
                             f"clamp itself lands on these spots (it is the grip biting in, not a separate strike), and it "
                             f"stays on:")
                lines += [self._pressure_line(e["hits"][0], e.get("with", "")) for e in new]
        for e in bundle.get("also_this_beat", []):
            if e["type"] == "hold_ongoing":
                pass  # listed above, grouped per attacker
            elif e["type"] == "pin_progress":
                pass  # already listed first
            elif e["type"] == "weather_end":
                lines.append(f"The {e['kind']} eases off and clears over the arena.")
            elif e["type"] == "status_tick":
                if e["status"] == "burned":
                    lines.append(f"{poss(e['fighter'])} burn flares on her {e['hits'][0]['part'].lower()}: a hot, "
                                 f"stinging throb she can't shake.")
                elif e["status"] == "poisoned":
                    lines.append(f"The poison works through {e['fighter']}: a wave of nausea and shakiness.")
                else:
                    lines.append(f"The {e['status']} keeps coming down: hailstones sting {e['fighter']} on her "
                                 f"{e['hits'][0]['part'].lower()}.")
            elif e["type"] == "alliance_end":
                lines += self._alliance_end_lines(e)
            elif e["type"] == "get_up":
                lines += self._get_up_lines(e)
            elif e["type"] == "crumple" and e.get("down"):
                fc = e.get("facing")
                if fc == "sitting up":
                    lines.append(f"CRUMPLE: once {e['by']} is no longer holding her up, {e['fighter']} slides down "
                                 f"{e['surface']} and ends SITTING at its foot, her back against it, legs out in front "
                                 f"of her: {Engine.FACING_LOOK[fc]}. She does not end lying flat and does not stay "
                                 f"standing. Show her sliding down; it does no new damage.")
                else:
                    lines.append(f"CRUMPLE: once {e['by']} is no longer holding her up, {e['fighter']} slides down "
                                 f"{e['surface']} and crumples to the ground at its foot"
                                 + (f", ending up {Engine.FACING_LOOK[fc]}" if fc in Engine.FACING_LOOK else "")
                                 + ". Show her going down; it does no new damage.")
                lines += self._knock_on_lines(e.get("knock_on"))
            elif e["type"] == "hold_end" and e.get("released") and e.get("submission"):
                lines.append(f"THE {e['submission'].upper()} ENDS at the END of this beat: {e['attacker']} lets it go, "
                             f"spent; she can't keep it on any longer. {e['defender']} is left on the ground where she "
                             f"was, hurting from it, free to try to get up from the next beat. Show it as the last thing "
                             f"that happens.")
            elif e["type"] == "hold_end" and e.get("broke_free"):
                parts = " and ".join(e.get("parts") or [])
                with_ = " and ".join(dict.fromkeys(e.get("with") or []))
                lines.append(f"THE HOLD BREAKS at the END of this beat: after the pressure listed above, {e['defender']} "
                             f"wrenches her {parts} free of {poss(e['attacker'])} grip"
                             + (f" ({with_})" if with_ else "") + f", which had been on for {e['beats_held']} beat(s). "
                             f"Show it as the last thing that happens. This time: "
                             + {"wrench": "one hard wrench of her whole body tears her out of it",
                                "pry": "she gets a paw (or a tail, a coil) under it and pries it open",
                                "slip": "she goes slack for an instant, the grip shifts to re-settle, and she slips out "
                                        "through the gap",
                                "shove": f"she braces against {e['attacker']} and shoves her back half a step, and the "
                                         f"grip comes away"}.get(e.get("manner"), "the twist, pull, or shove that gets her loose")
                             + f"; {e['attacker']} is left with nothing in her grip. It does no damage, nobody falls, and "
                             f"no new attack follows it. When the beat ends, nothing of {poss(e['attacker'])} is on her.")
            elif e["type"] in ("hold_loosened", "hold_strain"):
                parts = " and ".join(e.get("parts") or [])
                with_ = " and ".join(dict.fromkeys(e.get("with") or []))
                how = {"pry": "works at it with whatever she has free, trying to pry it loose",
                       "twist": "twists and wrenches her body against it",
                       "claw": "claws at the grip itself and scrabbles at the ground for purchase",
                       "brace": "braces and strains against it with everything she has"}.get(e.get("manner"),
                                                                                           "fights against it")
                if e["type"] == "hold_loosened":
                    lines.append(f"THE GRIP LOOSENS BUT STAYS ON: after the pressure listed above, {e['defender']} {how}, "
                                 f"and wins a little slack. {poss(e['attacker'])} grip on her {parts}"
                                 + (f" ({with_})" if with_ else "") + f" is not as tight as it was: she gets a fuller "
                                 f"breath, a little room. It does NOT come off: {e['attacker']} keeps hold. No damage "
                                 f"from this, nobody falls, nobody gets free.")
                else:
                    lines.append(f"{e['defender']} FIGHTS THE GRIP this beat: she {how}. It does not work: "
                                 f"{poss(e['attacker'])} grip on her {parts}" + (f" ({with_})" if with_ else "")
                                 + " stays exactly as it was. No damage from this, nobody gets free.")
            elif e["type"] == "stays_down":
                lines.append(f"{e['fighter']} has ONLY JUST gone down: she does NOT try to get up in this beat. No pushing "
                             f"herself up, no failed attempt, no rising to her knees. She lies where she fell, getting her "
                             f"breath back; her first attempt to rise comes next beat (the program rolls it).")
            elif e["type"] == "crumple":
                way = {"staggers": f"she staggers off {e['surface']}, winded and hurting",
                       "leans": f"she stays slumped UPRIGHT against {e['surface']}, held up by it and by her own locked "
                                f"legs, and pushes herself off it only as the beat ends",
                       "knee": f"one leg buckles and a knee touches the ground for an instant; she catches herself on "
                               f"{e['surface']} and shoves back up, so she is standing again before the beat ends",
                       "rebounds": f"she rebounds off {e['surface']} and stumbles forward a few steps, past {e['by']}, "
                                   f"before she finds her balance"}.get(e.get("manner"),
                                                                        f"she staggers off {e['surface']}, winded and hurting")
                lines.append(f"{e['fighter']} does NOT fall: when {e['by']} pulls back, this time {way}. She KEEPS HER "
                             f"FEET and ends the beat standing: no sliding down to the ground, no crumpling, no lying "
                             f"there, no getting up.")
            elif e["type"] == "scene_event":
                lines += self._scene_event_lines(e)
            elif e["type"] == "adrenaline":
                lines.append(f"ADRENALINE SURGE: {e['fighter']} has been pushed past her limit and something kicks in: "
                             f"for the next {e['beats']} beats she moves faster, hits harder, and the pain falls away "
                             f"behind sheer will. Make this a turning point: show it rising in her body.")
            elif e["type"] == "status_end":
                other = next((w for w in (getattr(self, "strengths", None) or {}) if w != e["fighter"]), "her opponent")
                end = self.STATUS_ENDS.get(e["status"])
                lines.append(f"{e['fighter']} shakes off being {self.STATUS_WORDS.get(e['status'], e['status'].replace('_', ' '))}: show it wearing off"
                             + (f" ({end.format(other=other)})" if end else "") + ".")
            elif e["type"] == "recovery":
                lines.append(f"{e['fighter']} COMES AROUND {'' if e.get('forced') else 'A LITTLE '}this beat: from "
                             f"{e['from'].upper()} to {e['to'].upper()} ({e['look']}). Show that change happening "
                             f"slowly, in detail.")
                if e.get("rising"):
                    lines.append(f"  - She gets all the way up: the hard way, grabbing onto whatever is in reach, a try that "
                                 f"fails, then finally standing, shaky and favoring every injury. She knows she lost.")
            elif e["type"] == "fatigue_shift":
                for name, f in e["fighters"].items():
                    lines.append(f"{poss(name)} overall condition worsens to {f['now'].upper()}: {f['reaction_guide']}")
        for t in bundle.get("tactics") or []:
            if t["stage"] == "setup" and t.get("planned"):
                lines.append(f"THE PLAN: {t['text']}. {t['who']} means it: let one short thought of hers show the plan "
                             f"(in her own words: no move names, no rules), and let {t['on']} see it coming or not.")
            elif t["stage"] == "setup":
                lines.append(f"AN OPENING FOR LATER: {t['text']}. {t['who']} notices it: one short thought of hers can "
                             f"show she has seen what it means (in her own words: no move names, no rules).")
            elif t["stage"] == "payoff":
                lines.append(f"THE PAYOFF: this is what {t['who']} has been waiting for since {t['ago']} beat(s) ago "
                             f"({t['setup']}). Show that it was planned: the moment she has been waiting for, and "
                             f"{t['on']} realising, too late, what the earlier move was for.")
            elif t["stage"] == "read":
                lines.append(f"A READ: {t['who']} {t['text']}. Show her seeing it and choosing; {t['on']} sees her "
                             f"trap go unused.")
        last_level = {}
        for who, part, level in self._breaking:
            last_level[(who, part)] = level      # hit twice in one beat: the level it ENDS at
        # at most two a beat, the worst first (devastated before excruciating), so the biggest crossing is never dropped
        rank = {"numb with shock": 3, "devastated": 2, "excruciating": 1}
        for (who, part), level in sorted(last_level.items(), key=lambda kv: -rank.get(kv[1], 0))[:2]:
            lines.append(f"BREAKING POINT: {poss(who)} {part} has just become {level.upper()} for the first time. Slow "
                         f"down and give this its own focused moment: the instant the pain becomes too much to hold in, the "
                         f"sound she makes, how her body and her thoughts react. It is the biggest moment of this "
                         f"beat. It is PAIN crossing a line, not a bone: nothing breaks, snaps, gives way or caves in"
                         + ("" if any(_mentions_exact(part.lower(), b) for b in (getattr(self, "breakable", None) or []))
                            else " (this part can't break yet)") + ".")
        if self.recent_lines:
            lines.append("ALREADY SAID in recent beats (do NOT reuse or echo these thoughts, lines, or sounds; write new "
                         "ones): " + "; ".join(f"\"{x}\"" for x in list(dict.fromkeys(self.recent_lines))[-14:]) + ".")
        people = []
        for a in bundle.get("actions") or [bundle.get("action") or {}]:
            for k in ("attacker", "defender", "fighter", "focus"):
                for who in str(a.get(k) or "").split(", "):
                    if who and who not in people:
                        people.append(who)
        if people and not (self._blocks().enabled and self._blocks().entries):
            lines.append("THOUGHT ANGLES this beat (to keep inner voices varied): " + "; ".join(
                f"{who}: {THOUGHT_ANGLES[(self._beat_no * 3 + sum(map(ord, who))) % len(THOUGHT_ANGLES)]}"
                for who in people[:3]) + ".")
        if self.recent_reactions:
            used = sorted(set().union(*self.recent_reactions[-2:]))
            if used:
                lines.append("RECENTLY USED REACTIONS (the last beats already showed these; pick DIFFERENT ones now): "
                             + ", ".join(used) + ".")
        if self._tiers_used:
            guide = [f"{t['label']} = {t['reaction']}" for t in pain_tiers(self.rules) if t["label"] in self._tiers_used]
            lines.append("PAIN GUIDE (how each lasting pain level shows from now on):\n  " + "\n  ".join(guide))
        lines.append("Impact examples are suggestions: pick reactions that fit each fighter's species (their TELLS) and "
                     "the moment, and never reuse the same reaction twice in a beat. Scale how fast each fighter recovers "
                     "to their OVERALL strength under CURRENT CONDITION: a strong fighter cries out, then fights on.")
        return "\n".join(lines)

    def _knock_on_lines(self, events):
        """What a fall, a throw, a takedown, or falling asleep knocked loose this beat."""
        out = []
        for k in events or []:
            if k["type"] == "pin_broken":
                out.append(f"  - THE PIN ENDS HERE: {k['note']}. {k['defender']} is no longer held (she is still on "
                           f"the ground where she lay); no pin clock runs any more. Show the pin coming apart.")
            elif k["type"] == "pin_left":
                out.append(f"  - {k['attacker']} COMES OFF THE PIN: {k['note']}. The pin itself goes on, same clock; show "
                           f"her weight leaving and the other still holding {k['defender']} down.")
            elif k["type"] == "flattened":
                out.append(f"  - {k['fighter']} was SITTING UP: the blow knocks her flat again. She ends "
                           f"{Engine.FACING_LOOK.get(k['facing'], k['facing'])}. It is part of this hit, not a new fall "
                           f"and no new damage.")
            elif k["type"] == "hold_end" and k.get("shaken"):
                out.append(f"  - THE HIT BREAKS HER GRIP: {k['attacker']} LOSES HER HOLD on {poss(k['defender'])} {k['part']}"
                           + (f" ({k['with']})" if k.get("with") else "") + f": {k['reason']}. Show it come off as the "
                           f"blow lands (it goes slack, slides away, is torn loose); {k['defender']} is free of it "
                           f"from that moment, and it is NOT on her when the beat ends.")
            elif k["type"] == "hold_end":
                out.append(f"  - {k['attacker']} LOSES HER GRIP on {poss(k['defender'])} {k['part']} ({k['reason']}): "
                           f"that hold is over.")
            elif k["type"] == "slumps":
                fc = k.get("facing")
                out.append(f"  - {k['fighter']} slumps to the ground as it takes her"
                           + (f": she ends up {Engine.FACING_LOOK[fc]}." if fc in Engine.FACING_LOOK else "."))
        return out

    def _describe_action(self, a):
        lines = self._describe_action_core(a)
        att, dfn = a.get("attacker"), a.get("defender")
        ch = a.get("chain")
        if ch and att and dfn:
            k, n = ch["link"], ch["of"]
            self._chain_beat = True
            if ch.get("ended") == "dodged":
                head = (f"CHAIN, link {k}: this was meant to lead into more, but {dfn} slips it, and that ENDS the "
                        f"chain: nothing else comes from {att} this beat.")
            elif k == 1:
                head = (f"A CHAIN: {att} strings {n} attacks together on {dfn} this beat, and this is the FIRST. They "
                        f"are ONE flowing sequence: each comes straight out of the one before, with no pause and no "
                        f"reset between them. Tell them in order; each lands once.")
            else:
                head = (f"CHAIN, link {k} of {n}: this comes STRAIGHT OUT of the one before, with no pause: {dfn} has "
                        f"had no time to recover or set her feet."
                        + (" It is the last of the sequence." if k == n else ""))
            if ch.get("ended") == "no follow-through":
                head += f" {att} has nothing left to follow it with: the sequence ends here."
            lines.insert(0, head)
        if a.get("pummel"):
            self._chain_beat = True
            pm = a["pummel"]
            n = pm["count"]
            where = pm.get("where") or "grab"
            lie = {"face-down": "face-down", "face-up": "on her back", "on her side": "on her side",
                   "sitting up": "sitting"}.get(pm.get("lying") or "", "on the ground")
            place = {"grab": ("at no distance, inside the grab", "in the grip", "the grab is still on"),
                     "pin": (f"rained down from on top, inside the pin: {att} stays on her and {dfn} is pinned under "
                             f"every one", "under the weight", "the pin is still on"),
                     "against": (f"with {dfn} still pressed against {pm.get('against') or 'the scenery'}, nowhere to go "
                                 f"and nothing to give with", f"against {pm.get('against') or 'it'}",
                                 f"she is still against {pm.get('against') or 'it'}"),
                     "down": (f"on {dfn} where she is down ({lie}), {att} over her or down beside her", "where she lies",
                              "she is still down"),
                     }.get(where)
            lines.append(f"  - A PUMMEL: {n} short blows of the same move, one after another, {place[0]}, with no room "
                         f"to wind up; each is lighter than one full blow would be. Tell it as a flurry of {n} (that "
                         f"count is right), not as one big hit."
                         + (" They do not all land in one place; in order: " + ", ".join(pm["parts"])
                            + ". Show each blow finding its spot." if len(set(pm.get("parts") or [])) > 1 else
                            " Every one lands on the same spot." if len(pm.get("parts") or []) > 1 else "")
                         + {"spoiled": f" It stops when {dfn} twists enough {place[1]} to spoil the next one: she turns "
                                       f"the struck part away or gets a limb in the road. She is NOT free, {place[2]}, "
                                       f"and nothing lands on {att}.",
                            "out of breath": f" It stops because {att} has to breathe: the last blow comes slower than "
                                             f"the first, and she stays where she is, heaving; {place[2]}.",
                            "limit": f" It stops only when {poss(att)} arm will not lift for another.",
                            "answered": f" It is NOT one-sided to the end: {dfn} takes the blows and then ANSWERS, one "
                                        f"short blow of her own from where she is, and that is what stops it (listed "
                                        f"below). She is NOT free; {place[2]}.",
                            }.get(pm.get("ended") or "", ""))
            if pm.get("frenzy"):
                lines.append(f"  - A FRENZY: {att} does not stop. Past the point where she would normally stop, she "
                             f"keeps going, blow after blow, mostly on the same place, something gone cold or wild in "
                             f"her. Let the count be felt: the rhythm, the same spot taking it again and again, how "
                             f"{poss(dfn)} reactions change from the first blows to the last (sharp at first, then "
                             f"rawer, then she can't keep anything in), and what it costs {att} to keep it up.")
            if a["pummel"].get("answer"):
                lines.append(f"  - {poss(dfn)} answering blow lands on {att} (a paw, an elbow, her head: whatever she can "
                             f"reach with from where she is held):")
                lines += [self._hit_line(h) for h in a["pummel"]["answer"]]
        if a.get("point_blank") and att and dfn:
            holder = a["point_blank"]
            held = dfn if holder == att else att
            lines.append(f"  - POINT-BLANK: {holder} has hold of {held} (the grab), and they are locked together at arm's "
                         f"length or closer. There is no room to dodge between them: this lands. Show how close they "
                         f"are and the grip that keeps them there.")
        if a.get("from_grab") and att and dfn:
            lines.append(f"  - It comes out of the grab {att} already had on her: {dfn} could not slip it.")
        if self._chain_beat:
            self._one_strike = None
        events = list(a.get("knock_on") or []) + [k for s in a.get("status_applied") or [] for k in s.get("knock_on") or []]
        if a.get("launch_blocked"):
            lines.append(f"  - Nobody is knocked down, thrown, or lifted by this: {a['launch_blocked']}. Bodies stay "
                         f"where they are.")
        return lines + self._knock_on_lines(events)

    def _describe_action_core(self, a):
        lines = []
        t = a["type"]
        intent = f" (why: {a['intent']})" if a.get("intent") else ""
        if t == "instant" and a.get("environment") and a.get("manhandle"):
            self._must_manhandle = a
            att, dfn, kind = a["attacker"], a["defender"], a["manhandle"]
            route = "; then ".join(("tumbling on: " if l.get("tumble") else "") + f"{l['surface']} ({', '.join(l['parts'])})"
                                   for l in a.get("landings", []))
            fc = a.get("facing")
            lies = f", {Engine.FACING_LOOK[fc]}" if fc in Engine.FACING_LOOK else ""
            grab = ("by the scruff, a limb, the tail, or bodily round the middle: whatever fits their two bodies")
            told = f" How it goes (the author's words): {a['told']}." if a.get("told") else ""
            if kind == "drag":
                lines.append(f"{att} TAKES HOLD of {dfn} ({grab}) and DRAGS her across the ground"
                             + ("" if a.get("was_down") else ", pulling her off her feet first")
                             + f". She is hauled over, into or against, in this order: {route}. Each surface scrapes or "
                             f"hits those body parts. She is NOT lifted and NOT thrown: she stays on the ground the whole "
                             f"way and ends up there{lies}, beside the last thing named. Show {poss(att)} grip and the "
                             f"pull, the ground under {dfn}, and each thing she is dragged against. This is {poss(att)} "
                             f"doing, no named move.{told}{intent}")
            elif kind == "slam":
                lines.append(f"{att} SEIZES {dfn} ({grab})"
                             + (", HAULS her up off the ground where she lay," if a.get("from_ground") else ", LIFTS her off her feet,")
                             + f" and SLAMS her straight down at her own feet, onto, in this order: {route}. Each surface "
                             f"hits those body parts. She ends up ON THE GROUND{lies}, right in front of {att}. Show the "
                             f"lift, her weight in the air for a moment, and the impact. This is {poss(att)} doing, no "
                             f"named move.{told}{intent}")
            else:
                lines.append(f"{att} SEIZES {dfn} ({grab})"
                             + (", HAULS her up off the ground where she lay," if a.get("from_ground") else "")
                             + f" and THROWS her: she leaves {poss(att)} grip, flies, and crashes into the arena in this "
                             f"order: {route}. Each surface hits those body parts. " + self._ends_line(a)
                             + f" She lands away from {att}. Show the grab, the heave, her body in the air, and each impact. This is "
                             f"{poss(att)} doing, no named move.{told}{intent}")
            lines += self._tumble_line(a)
            lines += self._devastating_line(a)
            lines += [self._hit_line(h, i + 1) for i, h in enumerate(a["hits"])]
            lines += self._arena_status_lines(a.get("status_applied"))
            return lines
        if t == "instant" and a.get("environment") and a.get("in_place"):
            route = "; then ".join(f"{l['surface']} ({', '.join(l['parts'])})" for l in a.get("landings", []))
            fc = a.get("facing")
            lines.append(f"{a['defender']} is ALREADY ON THE GROUND, and that blow DRIVES HER INTO it where she lies: "
                         f"{route}. Each surface hits those body parts. She does NOT fall again and is not thrown "
                         f"anywhere: she stays where she was"
                         + (f", {Engine.FACING_LOOK[fc]}" if fc in Engine.FACING_LOOK else "") + ".")
            lines += [self._hit_line(h, i + 1) for i, h in enumerate(a["hits"])]
            lines += self._arena_status_lines(a.get("status_applied"))
            return lines
        if t == "instant" and a.get("environment"):
            how = a.get("launch") or "knocked down"
            verb = {"launched": "is LAUNCHED through the air", "thrown": "is THROWN",
                    "knocked down": "is KNOCKED DOWN"}.get(how, "goes down")
            if a.get("spiked_by"):
                verb = (f"is SMASHED BACK DOWN out of the air by {poss(a['spiked_by'])} blow (she never landed from the "
                        f"launch: this is her landing, and a hard one)")
            if a.get("from_ground"):
                verb = ("was LYING ON THE GROUND when it hit (she was never standing this beat): the blow smashes into "
                        "her where she lies and sends her skidding, rolling, and tumbling across the ground")
            route = "; then ".join(("tumbling on: " if l.get("tumble") else "") + f"{l['surface']} ({', '.join(l['parts'])})"
                                   for l in a.get("landings", []))
            lines.append(f"{a['defender']} {verb} by that blow and crashes into the arena, in this order: {route}. "
                         f"Each surface hits those body parts. " + self._ends_line(a)
                         + " How she travels between the surfaces (skidding, tumbling, bouncing, spinning) is yours.")
            lines += self._tumble_line(a)
            lines += [self._hit_line(h, i + 1) for i, h in enumerate(a["hits"])]
            lines += self._arena_status_lines(a.get("status_applied"))
            return lines
        if t == "aftermath":
            return [f"AFTER THE MATCH: {a.get('winner')} has won. No attacks, no new injuries, no new pins. Time passes "
                    f"quietly: the winner catches her breath, feels her injuries, and reacts to the fallen; the loser lies "
                    f"as CURRENT CONDITION describes. "
                    + (f"What happens (the author's direction): {a['flavor']}. " if a.get("flavor") else "")
                    + "Keep each fighter at their listed recovery stage unless a change is listed below. Keep the full "
                    "detail of a fight beat, but find NEW things to show each time instead of circling back: a different "
                    "injury flaring or stiffening, a sense not used yet (" + self._sw("ambience", "a smell, a sound, the light") + "; an "
                    "echo, the light shifting), small changes in breathing or posture, a new thought or memory of a "
                    "specific moment of the fight, how the winner's own wounds are settling in."]
        if t == "heal":
            parts = [c["part"] for c in a.get("parts", [])]
            big = [c["part"] for c in a.get("parts", []) if c["damage_before"] - c["damage_after"] >= 60]
            out = [f"{a['fighter']} RECOVERS SOME STRENGTH this beat. "
                   + (f"How: {a['flavor']}. " if a.get("flavor") else
                      f"Choose a believable way that fits a Pokemon battle, {poss(a['fighter'])} species and moves, and the "
                      f"arena: a healing move (Rest, Aqua Ring, Recover, Moonlight...), a berry she had tucked away, "
                      f"something in {self._sw('place', 'the arena')} easing her, or a hard-won second wind while her opponent hesitates. ")
                   + "No attacks this beat; show the relief spreading through her body and her opponent's reaction."]
            if parts:
                out.append(f"  - These parts feel better: {', '.join(parts[:8])}"
                           + (f" (most of all: {', '.join(big[:4])})" if big else "") + ". They still ache, but "
                           "less; show the change in how she moves and breathes.")
            if a["health_after"] > a["health_before"]:
                out.append(f"  - Her overall strength comes back noticeably: steadier breathing, sharper eyes.")
            return out
        if t == "get_up":
            return self._get_up_lines(a)
        if t == "weather_end":
            return [f"The {a['kind']} eases off and clears over the arena."]
        if t == "take_off":
            return [f"{a['fighter']} TAKES TO THE AIR: wings snap open and beat hard, dust and spray kicked up, and she "
                    f"climbs out of reach above the arena. Show her rising and her opponent left on the ground looking up."]
        if t == "land_flight":
            return [f"{a['fighter']} comes DOWN out of the air by choice: wings flared, she drops and lands on her talons."]
        if t == "reposition":
            if a.get("resisted"):
                verb = {"pick up": "haul her up off the ground", "stand her up": "drag her up onto her feet",
                        "sit her up": "haul her up to sitting"}.get(a["how"], "roll her over")
                way = {"pry": f"tears {poss(a['attacker'])} grip off her",
                       "twist": "twists out of her hold",
                       "claw": "digs into the ground and clings",
                       "brace": "braces flat against the stone and will not be turned or lifted"}.get(a.get("manner"),
                                                                                                    "fights it off")
                return [f"FIRST, {a['attacker']} TRIES to {verb.replace('her', a['defender'], 1)}, and {a['defender']} "
                        f"FIGHTS IT OFF: this time she {way}. She is NOT moved: she stays exactly as she lay"
                        + (f" ({Engine.FACING_LOOK[a['before']]})" if a.get("before") in Engine.FACING_LOOK else "")
                        + ". Show the attempt and the refusal; it does no damage. Then the next action, on her as she lies."]
            self._must_reposition = a
            told = [f"  - How she does it (the author's words): {a['told']}."] if a.get("told") else []
            if a["how"] == "pick up":
                out = [f"FIRST, {a['attacker']} HAULS {a['defender']} UP off the ground (grabbing her by the scruff, "
                        f"an arm, a leg, her body: whatever fits their bodies) so the next action can land: show the lift, "
                        f"her weight, her struggling. She is off the ground now, not lying down."]
                return out + told
            if a["how"] == "stand her up":
                out = [f"FIRST, {a['attacker']} DRAGS {a['defender']} UP ONTO HER FEET (by the scruff, an arm, under her "
                        f"chest: whatever fits their bodies) and holds her there, swaying, legs barely under her, so the "
                        f"next action lands on her standing. Show the haul and her weight. She is on her feet now, not "
                        f"lying down, and she did not get up by herself."]
                return out + told
            if a["how"] == "sit her up":
                out = [f"FIRST, {a['attacker']} HAULS {a['defender']} UP TO SITTING (from {a.get('before') or 'where she lay'}): "
                        f"pulled up by the scruff, an arm or her shoulders and propped upright on the ground, her legs "
                        f"still out in front of her. She is {Engine.FACING_LOOK['sitting up']}. Show the pull and how "
                        f"she sags or braces. She is not standing."]
                return out + told
            out = [f"FIRST, {a['attacker']} ROLLS {a['defender']} over: from {a.get('before') or 'where she lay'} to "
                    f"{Engine.FACING_LOOK.get(a['after'], a['after'])}. Show the shove or wrench that turns her, and "
                    f"what's exposed now."
                    + (f" The pin shifts with her: {', '.join(a['holds_moved'])}." if a.get("holds_moved") else "")]
            return out + told
        if t == "knockdown":
            fc = a.get("facing")
            if a.get("already_down"):
                return [f"{a['fighter']} is already on the ground and stays there: {a.get('flavor', '')}"
                        + (f"; she is {Engine.FACING_LOOK[fc]}" if fc in Engine.FACING_LOOK else "")
                        + ". No damage, no new attack, no new fall."]
            return [f"{a['fighter']} goes down to the ground: {a.get('flavor', '')}"
                    + (f"; she ends up {Engine.FACING_LOOK[fc]}" if fc in Engine.FACING_LOOK else "")
                    + ". No damage, no new attack."]
        if t == "instant" and a.get("confused_self_hit"):
            lines.append(f"{a['fighter'] if a.get('fighter') else a['attacker']} is CONFUSED: she {a.get('flavor', '')}. "
                         f"The attack goes wrong, a stumble, a wild swing, a collision with the arena or her own body:")
            lines += [self._hit_line(h) for h in a["hits"]]
            return lines
        if t == "instant" and a.get("status_move") and not a.get("dodged"):
            m = a["move"]
            got = a.get("status_applied") or []
            lines.append(f"{a['attacker']} uses {m['name'].upper()} ({m['type']}-type: {m['about']}) on {a['defender']}. "
                         f"It does no damage. " + ("It WORKS." if got else f"It doesn't take hold: {a['defender']} "
                                                   f"resists or shakes it off.") + intent)
            for s in got:
                lines.append(f"  - This leaves {s['fighter']} {Engine.STATUS_LOOK.get(s['status'], s['status'].upper())} "
                             f"(for the next {s['beats']} beat(s)). Show it taking hold.")
                lines += self._status_story(s, a.get("attacker") if s.get("fighter") == a.get("defender") else a.get("defender"))
            return lines
        if t == "grapple_start":
            att, dfn = a["attacker"], a["defender"]
            with_ = f" with {a['with']}" if a.get("with") else ""
            if a.get("existing"):
                lines.append(f"{att} tightens the hold she already has on {poss(dfn)} {a['part']}{with_}.{intent}")
                return lines
            lines.append(f"{att} TAKES HOLD of {dfn}: she seizes her {a['part']}{with_} and KEEPS HOLD. It is a GRAB, not a "
                         f"crush: by itself it barely hurts. What it does is keep {dfn} at POINT-BLANK. Both stay ON "
                         f"THEIR FEET, locked together; {dfn} is not pinned, not down and not lifted, and she can hit "
                         f"back. While the grip holds, neither of them can dodge the other. Show the grab closing and "
                         f"the two of them held face to face"
                         + (f" ({a['flavor']})" if a.get("flavor") else "") + f".{intent}")
            lines.append(f"  - The grip is STILL ON when this beat ends unless something listed below breaks it: {att} "
                         f"does not let go.")
            return lines
        if t == "instant" and a.get("dodged") and not a.get("hits"):
            m = a.get("move")
            who = ", ".join(a.get("dodged_by") or [a["defender"]])
            what = f"{m['name'].upper()} ({m['about']})" if m else (a.get("flavor") or "an attack")
            if a.get("grapple"):
                what = "a grab, reaching to seize her and keep hold" + (f" ({a['flavor']})" if a.get("flavor") else "")
            if a.get("resisted"):
                way = {"pry": f"tears {poss(a['attacker'])} grip off her before it can close",
                       "twist": "twists out of it where she lies",
                       "claw": "digs into the ground and clings, and cannot be shifted",
                       "brace": "braces flat against the stone and makes herself too heavy to lift"}.get(a.get("manner"),
                                                                                                    "fights it off")
                lines.append(f"{a['attacker']} goes to seize {who} where she lies, to {a.get('manhandle') or 'move'} her, "
                             f"but {who} FIGHTS THE GRAB OFF: this time she {way}. She is not lifted, thrown or moved; "
                             f"she stays on the ground exactly as she lay. No damage either way. Show the attempt and "
                             f"the refusal.{intent}")
                return lines
            way = {"sidestep": "slips to one side and lets it pass",
                   "duck": "drops low and it goes over her",
                   "spring_back": "springs back out of its reach",
                   "turn_aside": "turns it aside at the last instant (a forearm, a shoulder, the flat of a tail knocking "
                                 "it off its line), so it glances away without hurting her",
                   "twist": "twists her body out of its line, so it passes a hair from her fur"}.get(a.get("manner"))
            g = a.get("guard") or {}
            if g.get("kind") == "deflect":
                way = (f"TURNS IT ASIDE with {g['how']}: she meets it and redirects it off its line, so it spends itself "
                       f"on nothing" + (f", and {a['attacker']} is carried past and left OFF BALANCE, stumbling to "
                                        f"recover her footing" if g.get("off_balance") else ""))
            sl = a.get("slipped")
            turned = (a.get("guard") or {}).get("kind") == "deflect"
            if a.get("wary") and not turned:
                way = (f"{way}; " if way else "") + ("she was already moving before it came: that move hurt her badly "
                                                     "before, and she flinches away from it early now")
            lines.append(f"{a['attacker']} goes for {who} with {what}, but {who} "
                         + (f"{way}" if turned else "DODGES" + (f" (this time she {way})" if way else ""))
                         + ": it misses completely and "
                         f"does no damage. "
                         + (f"But the footing is slick, and as she gets out of its way her feet go out from under her: "
                            f"she GOES DOWN, ending up "
                            + (Engine.FACING_LOOK.get(sl.get("facing"), "on the ground") if isinstance(sl, dict) else "on the ground")
                            + ". The fall hurts nothing new. Show the near miss AND the slip." if sl else
                            "She stays on her feet. Show the near miss: the move, the dodge, how close it came.")
                         + intent)
            mc = a.get("missed_charge")
            if mc:
                lines.append(f"  - Her charge finds nothing, and {a['attacker']} can't stop: her own momentum carries "
                             f"her on and she SLAMS INTO {mc['surface'].upper()} herself, "
                             + ("and GOES DOWN, ending up " + Engine.FACING_LOOK.get(mc.get("facing"), "on the ground")
                                if mc.get("down") else "but stays on her feet")
                             + f". Nobody else touches her: this is her own charge. It hurts her:")
                lines += [self._hit_line(h) for h in mc["hits"]]
            if a.get("counter_hits"):
                lines.append(f"  - Out of the dodge, {who} COUNTERS and catches {a['attacker']} (a quick strike of its own, "
                             f"separate from any attack {who} makes later in this beat; {a['attacker']} is the only one hurt here):")
                lines += [self._hit_line(h) for h in a["counter_hits"]]
            return lines
        if t == "instant":
            m = a.get("move")
            if m:
                eff = {"super effective": " It is SUPER EFFECTIVE.", "not very effective": " It is not very effective.",
                       "no effect": " It has NO EFFECT at all."}.get(m["effectiveness"], "")
                aim = {"targeted": "aimed at one spot", "spread": "spread across several parts",
                       "whole_body": "hitting the whole body"}.get(m["target"], "")
                kind = "an improvised move" if m.get("improvised") else f"{m['type']}-type move"
                lines.append(f"{a['attacker']} uses {m['name'].upper()} ({kind}: {m['about']}) on "
                             f"{a['defender']}, {aim}.{eff}{intent}")
                mine = {w for w, rx in WEAPONS
                        if re.search(rx, " ".join([str(a.get("flavor") or ""), str(m.get("about") or ""), m["name"]]), re.I)}
                if mine and len(mine) <= 2 and not a.get("dodged"):
                    nots = [WEAPON_NOT[w] for w in ("claws", "teeth", "tail") if w not in mine]
                    lines.append("  (Delivered with " + " or ".join(WEAPON_SAY[w] for w, _ in WEAPONS if w in mine)
                                 + ", as the move says" + (": not " + ", not ".join(nots) if nots else "") + ".)")
                if not m.get("improvised") and m.get("type"):
                    lines.append(f"  (Show it as the {m['type']}-type move it is. Don't add another element: no "
                                 f"electricity, fire, ice, or water unless the move itself is that type.)")
            else:
                lines.append(f"{a['attacker']} attacks {a['defender']}: {a.get('flavor', '')}{intent}")
            if a.get("point_blank"):
                lines.append("  (The blow itself is not a hold: nothing NEW latches on with it. The grab that is already "
                             "on stays on.)")
            elif (a.get("pummel") or {}).get("where") in ("pin", "down", "against"):
                keep = {"pin": "The pin that is already on stays on", "down": "She stays down where she is",
                        "against": "She stays pressed where she is"}[a["pummel"]["where"]]
                lines.append(f"  (The blows themselves are not a hold: nothing NEW latches on with them. {keep}.)")
            else:
                lines.append("  (An instant hit: any bite, grab, or grip lets go as soon as it lands. It is NOT a hold, so "
                             "nobody is still latched on afterward.)")
            if a.get("recoil"):
                lines.append(f"  - RECOIL: the {(m or {}).get('name', 'attack')} was reckless, and as it lands the force "
                             f"jars back into {a['attacker']} herself (her own move, nobody else's blow):")
                lines += [self._hit_line(h) for h in a["recoil"]["hits"]]
            if a.get("reflected"):
                rf = a["reflected"]
                lines.append(f"  - {rf['kind'].upper()} (after the hits below land on her): {rf['by']} TAKES the hit and "
                             f"SENDS IT BACK harder; the force returns onto {a['attacker']}:")
                lines += [self._hit_line(h) for h in rf["hits"]]
            if a.get("feint"):
                fe = a["feint"]
                lines.append(f"  - A FEINT first: {a['attacker']} fakes one way before the real blow. " + (
                    f"{a['defender']} BITES on it: she commits to answering the fake, and the real blow comes in while "
                    f"she is turned the wrong way, wide open, with no time to twist, roll with it or soften it (it "
                    f"lands harder for that)." if fe["bit"] else
                    f"{a['defender']} READS it and doesn't commit; the real blow comes as an ordinary attack."))
            lines += self._devastating_line(a)
            lines += self._anticipation_line(a)
            lines += self._opening_line(a)
            if a.get("juggled_up"):
                lines.append(f"  - The blow knocks {a['defender']} UP OFF HER FEET into the air: she is still in the air, "
                             f"helpless, when the next blow comes (listed next). She does not land before it.")
            if a.get("juggle"):
                lines.append(f"  - A JUGGLE: {a['defender']} is still in the air from the last blow, helpless, nothing "
                             f"under her to push from, and this one catches her there (it lands harder for that) and "
                             f"smashes her back down to the ground (the landing below).")
            if a.get("overcommit"):
                worn = (getattr(self, "strengths", None) or {}).get(a["attacker"], 0) < 60
                lines.append(f"  - {a['attacker']} is so {'tired' if worn else 'out of breath'} she OVERCOMMITS: the blow is "
                             f"sloppy, badly timed, half its "
                             f"usual force, and she overbalances on it and has to catch herself (OFF BALANCE after it).")
            if a.get("last_stand"):
                lines.append(f"  - LAST STAND: {a['attacker']} is nearly spent, and she puts EVERYTHING she has left into "
                             f"this one blow: it is harder than anything she has thrown in a while, and afterwards she "
                             f"has nothing left at all, emptied out, barely able to stay up.")
            if a.get("guarding"):
                gd = a["guarding"]
                lines.append(f"  - {a['defender']} is GUARDING her {gd['part'].lower()} without thinking, shoulder or "
                             f"limb or body curled to cover it" + (f", which leaves her {gd['open_side']}{' side' if gd['open_side'] in ('left', 'right') else ''} open"
                                                                    if gd.get("open_side") else "") + ".")
            g = a.get("guard") or {}
            if g.get("kind") == "block":
                lines.append(f"  - A BLOCK: {a['defender']} sees it coming and gets her {g['part'].lower()} in its way "
                             f"({g['manner']}): it does not reach where it was aimed, and lands on the "
                             f"{g['part'].lower()} instead, much lighter than it would have been. Show the guard coming "
                             f"up and the blow jarring into it (the hit below).")
            if a.get("protected"):
                lines.append(f"  - {str(a['protected']).upper() if isinstance(a['protected'], str) else 'PROTECT'}: the attack STOPS against the barrier {a['defender']} threw up (a shimmering "
                             f"shell, braced paws): NOTHING reaches her. Show it breaking against it and the barrier "
                             f"guttering out with it.")
            st = a.get("stance")
            if st:
                lines.append({"protecting": f"  - {a['attacker']} does not attack: she braces and throws up a PROTECT "
                                            f"barrier around herself (a hard, shimmering shell)",
                              "countering": f"  - {a['attacker']} does not attack: she sets herself to COUNTER, weight "
                                            f"back, eyes on her opponent, waiting for the next close blow to send it back",
                              "mirroring": f"  - {a['attacker']} does not attack: she sets a MIRROR COAT, a sheen spreading "
                                           f"over her body, waiting for a blast or beam"}[st["kind"]]
                             + ("." if st["ok"] else ", but it FAILS: it flickers and is gone before it forms (she used it "
                                                     "too many times in a row)."))
            if a.get("weather"):
                lines.append({"rain": f"  - {a['attacker']} calls RAIN: clouds pull in and it starts to pour over the "
                                      f"whole arena, everything streaming wet.",
                              "sun": f"  - {a['attacker']} calls HARSH SUNLIGHT: the clouds burn off and heat beats down "
                                     f"on the arena.",
                              "hail": f"  - {a['attacker']} calls HAIL: the air turns bitter and hailstones begin to "
                                      f"rattle down over the arena."}.get(a["weather"]["kind"], ""))
            if a.get("dive"):
                lines.append(f"  - A DIVE: {a['attacker']} comes down OUT OF THE AIR at her, wings folded, the whole drop "
                             f"behind the blow. "
                             + (f"But {a['dragged_down']['by']} CATCHES her as she comes in and drags her down out of the "
                                f"air: {a['attacker']} hits the ground with her." if a.get("dragged_down") else
                                f"Then she beats her wings and climbs straight back up out of reach." if a.get("climbs") else
                                f"She does not climb again: she comes down to land, wings spread to stop."))
            if a.get("carried"):
                lines.append(f"  - CARRIED UP: {a['attacker']} seizes her in her talons and hauls her up off the ground, "
                             f"{a['carried']['height']}, wings labouring, then LETS GO. {a['defender']} falls and hits "
                             f"the ground (the landing below).")
            if a.get("grounded"):
                lines.append(f"  - {poss(a['defender'])} wing gives out under the blow: she can't hold herself up any "
                             f"more and FALLS out of the air (the landing below).")
            cl = a.get("clash")
            if cl:
                atk_mv = (m or {}).get("name", "the attack")
                lines.append(f"  - A CLASH: {a['defender']} does not dodge it. She meets it head-on with her own "
                             f"{cl['move'].upper()} ({cl['move_type']}-type: {cl['about']}), and the two attacks SLAM "
                             f"TOGETHER in the air between them: light, spray, force, the shock of it felt by both. "
                             + {"through": f"{poss(a['attacker'])} {atk_mv} is the stronger: it tears through what is "
                                           f"left of {poss(a['defender'])} and still reaches her, but WEAKENED (the hits "
                                           f"below are what gets through).",
                                "cancel": f"Neither gives way: the two attacks break against each other and burst apart "
                                          f"in the middle. NOTHING reaches either of them; no damage to anyone. Show "
                                          f"the meeting and the burst, and both of them braced against the blast of it.",
                                "back": f"{poss(a['defender'])} {cl['move']} is the stronger: it drives {atk_mv} back and "
                                        f"what is left of it hits {a['attacker']} instead. NOTHING reaches "
                                        f"{a['defender']}. It lands on {a['attacker']}:"}[cl["outcome"]])
                if cl.get("hits_on_attacker"):
                    lines += [self._hit_line(h) for h in cl["hits_on_attacker"]]
            if a.get("into_mouth"):
                lines.append(f"  - INTO HER MOUTH: the water finds {poss(a['defender'])} open mouth and goes up her nose "
                             f"and down her throat. She chokes on it: coughing, sputtering, spitting it out, eyes and "
                             f"nose burning, a gasp that pulls in more water before air. She coughs it up; nothing about "
                             f"it is drowning. It leaves her SPUTTERING (short of breath for a little while).")
            sus = a.get("sustain")
            if sus:
                later = sum(len(p["hits"]) for p in sus["pulses"])
                first = a["hits"][:len(a["hits"]) - later]
                lines.append(f"  - It is HELD, not a single blast: {m['name'] if m else 'the attack'} keeps pouring into "
                             f"{a['defender']} for {sus['held']} pulses (several seconds)"
                             + ((f", grinding her against {sus['against']} where she lies" if sus.get("was_down") else
                                 f", driving her back and pressing her against {sus['against']}") if sus["against"] else "")
                             + ". First impact:")
                lines += [self._hit_line(h) for h in first]
                for p in sus["pulses"]:
                    parts = ", ".join(dict.fromkeys(h["part"] for h in p.get("move_hits", p["hits"])))
                    lines.append(f"  - Pulse {p['n']}: it keeps hammering ({parts})"
                                 + (f"; she is ground into {sus['against']} ("
                                    + ", ".join(h["part"] for h in p["surface_hits"]) + ")" if p["surface_hits"] else "")
                                 + ".")
                    for h in p["surface_hits"]:
                        self._must_parts.append(h["part"])
                    if p.get("broke"):
                        lines.append(f"  - {sus['against'].upper()} BREAKS under her: it cracks and gives way, she "
                                     f"crashes through and down with it (a heavy extra hit), and the move ends early. "
                                     f"She ends up on the ground.")
                final, start = {}, {}
                for h in a["hits"]:
                    start.setdefault(h["part"], self._pain(h["damage_before"])["label"])
                    final[h["part"]] = self._pain(h["damage_after"])["label"]
                moved = {p: lab for p, lab in final.items() if lab != self._pain(
                    next(h["damage_after"] for h in a["hits"] if h["part"] == p))["label"]}
                if moved:
                    for lab in moved.values():
                        self._tiers_used.add(lab)
                    lines.append("  - AFTER ALL THE PULSES her lasting pain is (this is where each part ENDS, past its "
                                 "first impact): " + ", ".join(f"{p} {lab.upper()}" for p, lab in final.items()) + ".")
                    for p, lab in moved.items():
                        if lab in ("excruciating", "devastated", "numb with shock") and start.get(p) != lab \
                                and not any(b[1] == p for b in self._breaking):
                            self._breaking.append((a["defender"], p, lab))
                    self._linger_pool = [(d_, p_, dmg_, final.get(p_, lab_) if d_ == a["defender"] else lab_, k_)
                                         for d_, p_, dmg_, lab_, k_ in self._linger_pool]
                fc = sus.get("facing")
                lie = f", ending up {Engine.FACING_LOOK[fc]}" if fc in Engine.FACING_LOOK else ""
                if sus["against"] and not sus["broke"] and sus.get("was_down"):
                    lines.append(f"  - When it finally stops, she is still on the ground where she was{lie}.")
                elif sus["against"] and not sus["broke"]:
                    lines.append(f"  - When it finally stops, she slides down {sus['against']} to the ground{lie}.")
            elif a.get("charge") and not a["charge"].get("skipped"):
                ch = a["charge"]
                first = a["hits"][:len(a["hits"]) - len(ch["hits"])]
                sh = ch.get("sheath")
                lines.append(f"  - The charge connects:")
                lines += [self._hit_line(h, i + 1 if len(first) > 1 else None) for i, h in enumerate(first)]
                if sh:
                    lines.append(f"  - CONTACT NEVER BREAKS: {a['attacker']} is still wrapped in {sh} and still against "
                                 f"{a['defender']} from the first hit to the end of the move. She is carried INSIDE it "
                                 f"backward for {ch['distance']}, and all the way the {sh} keeps working on her: "
                                 f"pressing, stinging, scouring at the struck part and round it, not letting up while "
                                 f"the move lasts. There is no gap and no second strike: {a['attacker']} never pulls "
                                 f"back, never lands again, never overtakes her. While she is carried:")
                    work = {"water": "the water pressing, stinging and scouring at it the whole way",
                            "fire": "the fire searing and licking at it the whole way",
                            "electricity": "the current biting and crawling through it the whole way"
                            }.get(sh, f"the {sh} working at it the whole way")
                    lines += [self._hit_line(h, how=work) for h in ch.get("drive_hits") or []]
                    lines.append(f"  - Still inside the {sh}, still being driven, {a['defender']} is SLAMMED into "
                                 f"{ch['into']}. Her back takes {ch['into']}:")
                else:
                    lines.append(f"  - It is a CHARGE THAT DOESN'T STOP at the hit: {a['attacker']} keeps driving {a['defender']} "
                                 f"backward for {ch['distance']}, her feet scrabbling, and SLAMS her into {ch['into']}. Her "
                                 f"back takes {ch['into']}:")
                lines += [self._hit_line(h) for h in ch["surface_hits"]]
                if ch["crush_hits"] and sh:
                    lines.append(f"  - In the same instant the full weight of {poss(a['attacker'])} charge, {sh} and "
                                 f"body together, crushes into her front where it has been the whole time (the SAME "
                                 f"contact still pushing, not a new hit): {a['defender']} is pressed hard between it "
                                 f"and {ch['into']} with nowhere to go, the {sh} still pouring over her, until the move "
                                 f"is spent:")
                    lines += [self._hit_line(h) for h in ch["crush_hits"]]
                elif ch["crush_hits"]:
                    lines.append(f"  - In the same instant {poss(a['attacker'])} own body crushes against her front: "
                                 f"{a['defender']} is pressed hard between {a['attacker']} and {ch['into']}, held there "
                                 f"for a long moment with nowhere to go:")
                    lines += [self._hit_line(h) for h in ch["crush_hits"]]
                last = ch.get("last") or ch["into"]
                for st in ch.get("onward") or []:
                    # the charge does not stop at what it broke: she is driven on through it into the next thing
                    lines.append(f"  - {st['through'].upper()} BREAKS behind her: it cracks and gives way:")
                    lines += [self._hit_line(h) for h in (ch["break_hits"] if st["through"] == ch["into"] else
                                                          next((o["break_hits"] for o in ch["onward"]
                                                                if o["into"] == st["through"]), []))]
                    lines.append(f"  - AND THE CHARGE DOES NOT STOP: {a['attacker']} keeps driving, THROUGH the wreck of "
                                 f"{st['through']}, {a['defender']} still on her feet and still going backward in front "
                                 f"of her, and slams her into {st['into']} as well (a little less hard than the first "
                                 f"time: the first one took some of it). Her back takes {st['into']}:")
                    lines += [self._hit_line(h) for h in st["surface_hits"]]
                if ch["broke"]:
                    fc = ch.get("facing")
                    lines.append(f"  - {last.upper()} BREAKS behind her: it cracks and gives way, and she goes down "
                                 f"with it in the rubble"
                                 + (f", ending up {Engine.FACING_LOOK[fc]}" if fc in Engine.FACING_LOOK else "") + ":")
                    lines += [self._hit_line(h) for h in (ch["onward"][-1]["break_hits"] if ch.get("onward") else ch["break_hits"])]
                else:
                    lines.append(f"  - {a['defender']} is still UPRIGHT, held against {last} by {poss(a['attacker'])} "
                                 f"weight. Whether she falls once that weight comes off is listed further down.")
            elif len(a["hits"]) > 8 and len({h["part"] for h in a["hits"]}) == len(a["hits"]):
                lines += self._many_hits(a["hits"])
            else:
                multi = len(a["hits"]) > 1
                lines += [self._hit_line(h, i + 1 if multi else None) for i, h in enumerate(a["hits"])]
            if m and m.get("target") == "spread" and len(a.get("hits") or []) > 1 and not a.get("sustain"):
                lines.append(f"  - ONE blast that catches all of these parts at once, not separate shots one after "
                             f"another.")
            if a.get("charge") and a["charge"].get("skipped"):
                lines.append(f"  - It is an ordinary hit: nobody is driven into the scenery ({a['charge']['skipped']}).")
            if a.get("target_against"):
                lines.append(f"  - {a['defender']} is STILL PRESSED AGAINST {a['target_against']} from the charge when this "
                             f"lands: she hasn't fallen yet, has nowhere to go, and can't dodge it.")
            jar = (m or {}).get("auto_spill_parts") or (m or {}).get("spillover_parts")
            if jar and a.get("hits") and len(a["hits"]) > 1:
                if sum(1 for h in a["hits"] if h["part"] == a["hits"][0]["part"]) == 1:
                    self._one_strike = a["attacker"]  # checked afterwards: no second or third swing
                lines.append(f"  - This is ONE strike, not several: it lands on {a['hits'][0]['part']} and the force "
                             f"jars {', '.join(jar)} next to it in the same instant. Don't narrate extra swings or "
                             f"separate blows for those parts.")
            if m and m.get("extras"):
                lines.append("  - It lands differently because: " + "; ".join(
                    {"paralyzed": f"{a['attacker']} is paralyzed, so it comes out weaker and stiffer",
                     "adrenaline": f"{a['attacker']} is riding an adrenaline surge, so it hits harder",
                     "soaked": f"{a['defender']} is soaked, so the electricity tears through her far worse",
                     "pin damage": f"it is delivered from on top of the pin, short and cramped"
                     }.get(label, label) for label, _ in m["extras"]) + ".")
            if a.get("counter_hits"):
                lines.append(f"  - It caught one target, but another dodged and countered {a['attacker']}:")
                lines += [self._hit_line(h) for h in a["counter_hits"]]
        elif t in ("hold_start", "pin_start"):
            kind = "PINS" if t == "pin_start" else "locks a hold on"
            if t == "pin_start" and a.get("continuing"):
                kind = "keeps pinning (adjusting the pin on)"
            if t == "pin_start" and a.get("joined"):
                kind = (f"PILES ON TOO, joining {' and '.join(a['joined'])} in a DOUBLE PIN (both pressing at once, each "
                        f"on her own spots) on")
            kept = t == "hold_start" and a.get("parts") and all(p.get("existing") for p in a["parts"])
            if kept:
                kind = ("KEEPS the hold she already has on (it never came off: she shifts, renews or tightens the same "
                        "grip, she does not let go and grab again)")
            parts = ", ".join(f"{p['part']} ({self._hold_word(p['power'])} pressure"
                              + (f", with {p['with']})" if p.get("with") else ")") for p in a["parts"])
            cfg_first = float((self.rules.get("pin" if t == "pin_start" else "holds", {}) or {}).get(
                "first_beat_damage", 0.0 if t == "pin_start" else 1.0))
            mv = f" with {a['move']['name'].upper()} ({a['move']['about']})" if a.get("move") else ""
            lines.append(f"{a['attacker']} {kind} {a['defender']}{mv}: {a.get('flavor', '')}{intent}")
            sub = a.get("submission")
            if sub:
                lines.append(f"  - A SUBMISSION HOLD: a {sub['name'].upper()}, {sub['look']}. It is NOT a pin: there is "
                             f"no clock, nobody is counting, and she will not pass out from it. It is about the STRAIN: "
                             f"{sub['strain']}, more every beat it stays on. Show exactly how their bodies lock together, "
                             f"and the first wrench of it. {a['defender']} can't get up while it's on. {a['attacker']} "
                             f"still has {sub['free']} free.")
            if a.get("taken_down"):
                td = a.get("takedown") or {}
                how = (TAKEDOWN_WAYS.get(td.get("how") or "") + "; fit it to their bodies" if td.get("how") in TAKEDOWN_WAYS
                       else "as the line above already says" if td.get("told")
                       else "a tackle, a leg hooked out from under her, a drag to the ground: whatever fits their bodies")
                lines.append(f"  - {a['defender']} was ON HER FEET: {a['attacker']} first TAKES HER DOWN ({how}), "
                             f"then pins her where she lands. Show the takedown"
                             + ("; it does no damage of its own." if not td.get("hits") else
                                f": she is put down HARD, and the ground itself hurts her as she lands (before the pin "
                                f"closes):"))
                lines += [self._hit_line(h) for h in td.get("hits") or []]
            if a.get("against") and t == "pin_start":
                lines.append(f"  - This pin is AGAINST {a['against'].upper()}: {a['defender']} is on the ground at the "
                             f"foot of it, her head and shoulders jammed against it, so there is nowhere to push back "
                             f"to and no rolling away on that side. It is solid at her back the whole time she is held.")
            if kept:
                lines.append(f"  - Still pressing on: {parts}. The same grip as before, still on.")
            elif cfg_first > 0 and not a.get("continuing"):
                lines.append(f"  - Pressing on: {parts}. The grip bites as it closes: it hurts NOW (how much is listed "
                             f"further down), and it keeps hurting every beat it stays on. It is still on when the beat "
                             f"ends: nobody lets go.")
            else:
                lines.append(f"  - Pressing on: {parts}. The pressure is only just landing; the real damage builds "
                             f"over the coming beats.")
            carried = [p for p in a["parts"] if p.get("existing")] if t == "pin_start" else []
            if carried:
                lines.append(f"  - ALREADY ON from before, and it stays exactly as it was (it becomes part of the pin; it "
                             f"is not let go and taken again, and nothing else replaces it): "
                             + ", ".join(f"{p['part']}" + (f" with {p['with']}" if p.get("with") else "")
                                         + (f" (NOT {p['asked_with']})" if p.get("asked_with") else "") for p in carried)
                             + ". That grip keeps pressing this beat, as listed further down.")
            if t == "pin_start" and a.get("absorbed"):
                lines.append(f"  - {a['attacker']} keeps the grips she already had on her, now as part of the pin: "
                             + ", ".join(x["part"] + (f" ({x['with']})" if x.get("with") else "") for x in a["absorbed"])
                             + ". They don't let go.")
            if a.get("facing") in Engine.FACING_LOOK:
                lines.append(f"  - {a['defender']} is {Engine.FACING_LOOK[a['facing']]}"
                             + (f" ({a['facing_note']})" if a.get("facing_note", "").startswith("rolled") else "")
                             + ". Every contact must match that.")
            if t == "pin_start" and a.get("joined"):
                lines.append(f"  - The pin was already running: {a['attacker']} adds her weight to it. {a['defender']} now "
                             f"has two bodies on her and far less room to struggle. Every press listed (which "
                             f"part, pressed with what) must appear in the prose.")
            elif t == "pin_start" and not a.get("continuing"):
                lines.append(f"  - The pin has only just begun: no time passes on it in this beat. Don't mention a "
                             f"clock, a count, or any seconds yet. Every press listed (which part, pressed with what) "
                             f"must appear in the prose.")
        elif t == "hold_change":
            how = {"tightens": "TIGHTENS: she bears down harder",
                   "loosens": "eases a little, and STAYS ON: she shifts her grip without letting go (it is not broken, "
                              "it does not slip off, and nobody gets free)",
                   "holds steady": "holds steady"}.get(a["direction"], a["direction"])
            label = str(a.get("flavor") or "").strip()
            lines.append(f"{poss(a['attacker'])} hold on {poss(a['defender'])} {a['part']} {how}"
                         + (f" ({label.rstrip('.')})" if label else "")
                         + ". The grip is on for the whole beat and still on when it ends.")
        elif t == "hold_end":
            parts = ", ".join(a.get("parts") or [a.get("part", "")])
            lines.append(f"{poss(a['attacker'])} hold on {a['defender']} ({parts}) ENDS: {a.get('reason', '')}")
            if a.get("pin_ended"):
                lines.append(f"  - That was the pin: it is OVER"
                             + ("" if self.rules.get("pin", {}).get("fade", {}).get("enabled", True)
                                else f" at second {a['pin_ended']['seconds']}") + f". {a['defender']} "
                             f"is no longer held, though she is still on the ground. No clock runs any more.")
        elif t == "eliminated" and a.get("unhurt"):
            lines.append(f"{a['fighter']} is OUT of the fight before taking any real damage (the author's decision: "
                         f"{a.get('reason', '')}). Do NOT invent a cause, an earlier exchange, or injuries: show "
                         f"{a['fighter']} simply dropping out of the battle (backing off, sinking down, or slumping out of it) "
                         f"while clearly still alive and breathing. She stays where she ends up: there are "
                         f"no trainers, no Poké Balls, and no recall in this story. Then the remaining fighters size each other up. Nobody "
                         f"attacks yet; end on the tension before the first move.")
        elif t == "eliminated":
            lines.append(f"{a['fighter']} is OUT of the fight: {a.get('reason', '')}. This is final. No attack happens "
                         f"in this beat unless one is listed above: show {a['fighter']} fainting or being unable to "
                         f"continue from the injuries and exhaustion they already have. Pokemon faint; nobody dies, "
                         f"drowns, or disappears."
                         + (f" She ends up {Engine.FACING_LOOK[a['facing']]}, and stays lying that way."
                            if a.get("facing") in Engine.FACING_LOOK else ""))
            if a.get("winner"):
                lines.append(f"  - {a['winner']} has won.")
        elif t == "alliance":
            who, foes = " and ".join(a["members"]), " and ".join(a.get("against") or [])
            terms = (f"until {a['until']} is out of the fight" if a.get("until") else
                     f"for the next {a['beats']} beats" if a.get("beats") else "until nobody else is left to fight")
            lines.append(f"AN ALLIANCE FORMS: {who} turn on {foes or 'the rest'} together, {terms}. No attack happens in "
                         f"this beat. Show it happen without a speech: a look held a moment too long, a step that puts "
                         f"them shoulder to shoulder, both turning the same way, and {foes or 'the other'} seeing it. "
                         f"They do not trust each other; it is a truce of convenience. "
                         + (f"The author's direction: {a['flavor']}." if a.get("flavor") else ""))
        elif t == "alliance_end":
            lines += self._alliance_end_lines(a)
        elif t == "struggle_request":
            lines.append(f"{a['fighter']} gathers everything for an escape attempt from {poss(a['pinner'])} pin "
                         f"(the attempt itself and its result are described under PIN CLOCK, if the pin is already "
                         f"running).")
        elif t == "pin_forced":
            if a.get("started_now"):
                parts = ", ".join(a["pressed"])
                lines.append(f"{a['attacker']} PINS {a['defender']}: {a.get('flavor', '')} (pressing {parts}).")
            lines += self._pin_lines(a)
            if a.get("pressure_hits"):
                lines.append(f"  - The pressure through the rest of the pin, part by part:")
                lines += [self._hit_line(h) for h in a["pressure_hits"]]
        elif t == "pinfall":
            res = (f"{a['defender']} kicks out at {a['kicked_out_at']}" if a["result"] == "kickout"
                   else f"{a['defender']} is pinned and eliminated")
            lines.append(f"{a['attacker']} goes for a quick pin on {a['defender']}: {res}.")
        elif t == "breather" and getattr(self, "_ongoing", False):
            lines.append(f"No new attack: only the pin or hold listed below continues. {a.get('flavor', '')}{intent}")
        elif t == "breather":
            lines.append(f"No new attack, and nothing new happens to anyone's body: no new grips, bites, holds, falls, "
                         f"or injuries. Fighters reposition, breathe, size each other up, and feel what they already "
                         f"have. {a.get('flavor', '')}{intent}")

        for s in a.get("status_applied") or []:
            if s.get("hazard"):
                lines += self._arena_status_lines([s])
                continue
            look = Engine.STATUS_LOOK.get(s["status"], s["status"].upper())
            lines.append(f"  - This leaves {s['fighter']} {look} (for the next {s['beats']} beat(s)). Show it.")
            lines += self._status_story(s, a.get("attacker") if s.get("fighter") == a.get("defender") else a.get("defender"))
        return lines or [f"({t})"]

    # what a status looks like, how she takes it, and what her opponent reads in it (an opening, mostly): told when it
    # lands, so it is never just a word. {who} = the one it is on, {other} = her opponent
    STATUS_STORY = {
        "flinched": ("her head or whole body jerks away from it on its own and she can't make it come back for a moment",
                     "she knows she has frozen and hates every heartbeat of it",
                     "{other} sees the flinch: an opening, and {other} means to use it"),
        "dazed": ("her eyes lose their focus, she blinks and shakes her head and the world won't settle",
                  "she can't find {other} properly; everything is a beat late",
                  "{other} sees the glazed eyes and the late reactions: she is slow now"),
        "off_balance": ("she stumbles past her own blow, weight on the wrong foot, arms out to catch herself",
                        "she knows she is wide open while she gets her feet back",
                        "{other} sees her stagger and the open side she can't cover"),
        "doubled_over": ("she folds round the hurt, head down, guard gone for a moment",
                         "she can't straighten yet, and she knows exactly how that looks",
                         "{other} sees her fold and the guard drop"),
        "breathless": ("her chest heaves and nothing goes in; her mouth opens on air that won't come",
                       "she can't get a breath and every movement costs her",
                       "{other} sees her gasping and knows she has nothing behind her blows for a moment"),
        "sputtering": ("she coughs and chokes, water streaming from her nose and mouth, eyes running",
                       "she can't stop coughing long enough to fight properly",
                       "{other} sees her choking and closes in while she can't"),
        "stiff": ("she moves stiffly, the limbs that were trapped slow and numb to answer",
                  "she can feel how slow she is and can't hurry it",
                  "{other} sees how stiffly she moves"),
        "cramped": ("her muscles have locked from holding on so long; she shakes them out and they won't loosen",
                    "every movement pulls at the cramp",
                    "{other} sees the cramped, careful way she moves"),
        "bound": ("one limb held tight, numb and tingling, dragging when she moves",
                  "she can feel the limb going dead under the grip",
                  "{other} feels the limb weaken in the grip"),
        "constricted": ("the coils press the breath and blood out of her; her movements go slow and heavy",
                        "she can feel her strength draining out with every squeeze",
                        "{other} feels her weaken inside the coils"),
        "paralyzed": ("her muscles lock and jerk, sparks crawling over her",
                      "her body won't do what she tells it",
                      "{other} sees her seize up"),
        "frozen": ("ice locks her in place", "she can't move at all", "{other} sees her held fast in the ice"),
        "asleep": ("her eyes close and her body goes slack", "", "{other} sees her slump, helpless"),
        "confused": ("her eyes swim and she sways, unsure where anything is", "she can't trust her own sense of where things are",
                     "{other} sees her swaying, lost"),
    }
    STATUS_WORDS = {"fury": "furious", "adrenaline": "on an adrenaline surge", "protecting": "behind her Protect barrier",
                    "countering": "set to counter", "mirroring": "behind her Mirror Coat", "airborne": "in the air"}
    STATUS_ENDS = {
        "flinched": "the freeze lets go of her and she can move again; {other} sees her come back",
        "dazed": "the world settles back into one piece; she finds {other} again, sharp and single",
        "off_balance": "she gets her feet back under her and her guard back up",
        "doubled_over": "she makes herself straighten, slowly, the hurt still there",
        "breathless": "breath finally comes back into her, ragged but real",
        "sputtering": "she gets the last of the water out and can breathe clean again",
        "stiff": "the stiffness works out of her limbs",
        "cramped": "the cramp lets go",
        "bound": "feeling floods back into the limb, prickling and hot",
        "constricted": "blood and breath come back into her in a rush",
        "paralyzed": "the last of the sparks fade and her muscles answer again",
        "confused": "her head clears; she knows where she is again",
        "fury": "the cold anger drains out of her and leaves her just tired",
        "adrenaline": "the surge drains out of her and every hurt comes back at full size",
        "protecting": "the barrier thins and is gone",
        "countering": "she lets the set go; nothing came to send back",
        "mirroring": "the sheen fades off her fur",
    }

    def _status_story(self, s, other=None):
        """The three-part telling for a status that just landed (the tell, her taking it, her opponent reading it)."""
        st = s.get("status")
        if st not in self.STATUS_STORY:
            return []
        who = s.get("fighter")
        other = other or next((w for w in (getattr(self, "strengths", None) or {}) if w != who), "her opponent")
        tell, mine, seen = self.STATUS_STORY[st]
        out = f"    show it: {tell}"
        if mine:
            out += f"; {who} knows it: {mine.format(other=other, who=who)}"
        if seen and other:
            out += f"; {seen.format(other=other, who=who)}"
        return [out + "."]

    def _sw(self, key, default=""):
        """A word for this arena (scenes.json): place, ground, rough, slick, ambience."""
        return (getattr(self, "scene_cfg", None) or {}).get(key) or default

    def _arena_status_lines(self, statuses):
        """What the arena did to a fighter who landed on or was driven into one of its hazards."""
        out = []
        for s in statuses or []:
            look = Engine.STATUS_LOOK.get(s["status"], s["status"].upper())
            src = s.get("hazard")
            if src:
                out.append(f"  - {src[:1].upper() + src[1:]} does more than hit her ({s.get('about') or 'see the SCENE'}): it "
                           f"leaves {s['fighter']} {look} (for the next {s['beats']} beat(s)). Show it happen as part of "
                           f"the impact, and show it on her afterward.")
            elif s["status"] == "soaked":
                out.append(f"  - The water leaves {s['fighter']} SOAKED: drenched, heavier, badly exposed to Electric.")
            else:
                out.append(f"  - This leaves {s['fighter']} {look} (for the next {s['beats']} beat(s)). Show it.")
                out += self._status_story(s)
        return out

    def _scene_event_lines(self, e):
        """The arena doing something by itself at the end of the beat (scenes.json events)."""
        who = e.get("fighters") or []
        self._must_event = e
        both = " and ".join(who)
        lines = [f"THE PLACE ITSELF ACTS, as the LAST thing in this beat, after everything above: {e.get('text', e.get('name'))}. "
                 f"Nobody caused it and nobody could have known; it is {e.get('place') or 'the arena'} doing what it does. "
                 + (f"It catches {both}" if e.get("hits") else f"It reaches {both}")
                 + (" (everyone)" if e.get("who") == "all" and len(who) > 1 else "")
                 + ". YOU MUST SHOW THIS: the warning (a sound, a movement), the thing happening, and what it does to "
                 + ("them" if len(who) > 1 else "her") + ". It knocks nobody down and moves nobody; the fight goes on."]
        lines += [self._hit_line(h, i + 1 if len(e.get("hits") or []) > 1 else None) for i, h in enumerate(e.get("hits") or [])]
        for s in e.get("status_applied") or []:
            look = Engine.STATUS_LOOK.get(s["status"], s["status"].upper())
            lines.append(f"  - It leaves {s['fighter']} {look} (for the next {s['beats']} beat(s)). Show it.")
            lines += self._status_story(s)
        if not e.get("hits") and not e.get("status_applied"):
            lines.append("  - It hurts nobody this time: a near thing, a shock, and both of them wary of the place now.")
        return lines

    def _get_up_lines(self, e):
        """Getting up off the ground, try by try, so it reads as hard as the injuries make it."""
        who, grab = e["fighter"], e["grab"]
        how = {"biped": f"grabs onto {grab} and hauls herself up with her arms",
               "quadruped": f"gets her legs under her, leaning her weight against {grab}",
               "serpent": f"braces her coils against {grab} and lifts her body",
               "avian": f"beats her wings against the ground and pushes up off {grab} onto her talons"}[e["plan"]]
        hurt = " and ".join(p.lower() for p in e.get("hurting", [])) or "battered body"
        self._getup_tries = e["tries"] if e["stands"] else None
        self._getup_who = who if e["stands"] else None
        self._getup_event = e if e["stands"] else None
        if e["stands"] and e["tries"] == 1:
            lines = [f"GETTING UP: {who} is on the ground and rises; she {how}. ONE smooth attempt: no failed tries, "
                     f"no slipping back down, no counting attempts, and she ends fully on her feet, not on her knees:"]
        else:
            lines = [f"GETTING UP: {who} is on the ground and tries to rise; she {how}. Show each try in its own short "
                     f"paragraph, with the strain in her {hurt}. Exactly {e['tries'] if e['stands'] else 3} tries, no "
                     f"more:"]
        verb = "give" if " and " in hurt else "gives"
        fails = list(e.get("fails") or [])
        fail_way = lambda k, i: {
            "gives_out": f"partway up, her {hurt} {verb} out and she drops back down hard",
            "slips": f"what she pushes off with skids on {self._sw('slick', 'the ground')} and she goes down again",
            "dizzy": "she gets partway up, everything tilts around her, and she sinks back down",
            "breath": "she gets partway up, has no air for it, and folds back down, gasping",
        }.get(fails[i] if i < len(fails) else None, f"partway up, her {hurt} {verb} out and she drops back down hard")
        rise = {"roll": "she rolls onto her front first, gathers herself under her, and pushes up",
                "lean": f"she drags herself to {grab} and climbs it, leaning her weight on it",
                "lurch": "she lurches up in one ugly heave, nearly overbalancing"}.get(e.get("rise"))
        if e["stands"] and e["tries"] == 1:
            lines.append(f"  - First try: she makes it up, quickly, shaking it off" +
                         (", though her breathing is rough and she favors the hurt spots." if e.get("hurting") else ".")
                         + (f" This time {rise}." if rise else ""))
        elif e["stands"]:
            lines.append(f"  - Try 1: {fail_way(None, 0)}.")
            if e["tries"] == 3:
                lines.append(f"  - Try 2: she gets nearly all the way up, then {fail_way(None, 1).split(', ', 1)[-1]}.")
            lines.append(f"  - Try {e['tries']}: she finally makes it onto her feet, unsteady: winded, wincing, sides "
                         f"heaving, favoring her {hurt}, using {grab} for balance."
                         + (f" This time {rise}." if rise else ""))
        elif e.get("sits"):
            lines.append(f"  - Three tries, each one shorter and weaker (the first: {fail_way(None, 0)}). Her {hurt} "
                         f"won't hold her. She does NOT make it to her feet this beat, but she gets as far as SITTING "
                         f"UP: she ends the beat sitting on the ground, propped on what will still bear her, "
                         f"{Engine.FACING_LOOK['sitting up']}. Not standing, not crouched ready to spring.")
        else:
            lines.append(f"  - Three tries, each one shorter and weaker (the first: {fail_way(None, 0)}). Her {hurt} "
                         f"won't hold her. She does NOT make it up this beat: she ends on the ground, gathering herself "
                         f"for the next try.")
        for g in e.get("held") or []:
            lines.append(f"  - {poss(g['by'])} grip on her {g['part']}" + (f" ({g['with']})" if g.get("with") else "")
                         + f" STAYS ON through every try" + (" and after she is up" if e["stands"] else "")
                         + f": {g['by']} does not let go and is not shaken off; {who} "
                         + ("rises with it still clamped on, dragging against it." if e["stands"] else
                            "strains against it."))
        for g in e.get("holding") or []:
            lines.append(f"  - {poss(who)} own grip on {poss(g['on'])} {g['part']}"
                         + (f" ({g['with']})" if g.get("with") else "") + " stays on too: she does not let go of it.")
        if e["stands"]:
            lines.append(f"  - This MUST be in the passage: its last paragraphs show {who} standing.")
        return lines

    def _pin_lines(self, e):
        a, d = e["attacker"], e["defender"]
        if e.get("helpers"):
            a = " and ".join([a] + list(e["helpers"]))  # a double pin: both of them are on her
        fm = bool(e.get("fade_mode"))
        if fm:
            went = e.get("fade_to", 0) - e.get("fade_from", 0)
            out = [f"THE PIN GOES ON: {poss(a)} pin on {d} holds through this beat, a short stretch of it. THERE IS NO "
                   f"CLOCK. Nobody here is counting and nobody knows how long {d} can last, so write NO seconds, "
                   f"no numbers of any kind for time, no count up or down, no 'time left', no 'halfway'. Time shows "
                   f"only in her body. How {d} is by the end of this beat: "
                   + ("OUT COLD: she passes out before it ends (told below). Up to that moment she is going fast, "
                      "barely moving, her eyes sliding shut and dragging open again"
                      if e.get("complete") and e.get("elimination") else
                      f"{e.get('fade_words') or 'still fighting'}"
                      + (" (this stretch took a lot out of her)" if went >= 22 else
                         " (she lost little ground in this stretch)" if 0 < went <= 9 else ""))
                   + f". Against the pin itself she is {e['fight_left'].upper()}."
                   + (f" {a} is running short of breath from holding it so long: show the effort it costs her."
                      if e.get("pinner_tired") else "")
                   + (f" {d} has broken out of a pin like this before, and she knows where it gives: show her "
                      f"looking for that place." if e.get("knows_pin") else "")]
        else:
            out = [f"PIN CLOCK: this beat covers ONLY seconds {e['seconds_from']} to {e['seconds_to']} of {e['duration']} "
                   f"of {poss(a)} pin on {d}. The clock counts UP (seconds held so far), never down like a referee's count. "
                   f"Mark the passing seconds in rising order, and STOP at second {e['seconds_to']}: never write a "
                   f"later second, never skip ahead. {d} is {e['fight_left'].upper()}."]
        angles = [
            f"the pinner's side: {poss(a)} own effort, her injuries under the strain, how she shifts and keeps the pin",
            f"one body part of {poss(d)} at a time: pick the worst-pressed spot and stay with exactly how it feels",
            f"breath and sound: {poss(d)} breathing against the weight, the noises both make, the place around them",
            f"what {d} tries, small and specific: a paw working for purchase, a twist of the hips, testing each contact",
            f"what each one sees in the other up close: eyes, teeth, fur, trembling, a look that passes between them",
            f"the ground under them: what it is made of against {poss(d)} body, what's within reach, what slips",
        ]
        step = (int(e.get("beats") or 0) if fm else
                int(e["seconds_to"] // max(1, e["seconds_to"] - e["seconds_from"])) if e["seconds_to"] > e["seconds_from"] else 0)
        out.append(f"  - To keep this stretch from repeating the last one, build it around: {angles[step % len(angles)]}. "
                   f"Use fresh sentences; never reuse lines from earlier pin beats.")
        s = e["struggle"]
        if e.get("buffed"):
            out.append(f"  - {d} still has momentum from breaking loose a moment ago: the pin is shakier, and {a} "
                       f"is working harder to keep it.")
        if s == "none":
            low = e.get("fight_left") in ("fading", "nearly gone")
            out.append(f"  - {d} makes no escape attempt this stretch: she has nothing left to try with. Show the last "
                       f"of her strength running out, not a plan." if e.get("complete") and e.get("elimination") else
                       f"  - {d} makes no real escape attempt this stretch: she has little left. Show her enduring, "
                       f"fighting to stay awake, the small things she can still do." if low else
                       f"  - {d} makes no real escape attempt this stretch: show her gathering strength, testing the "
                       f"weight, breathing, enduring, plotting.")
        elif s == "fail":
            self._must_struggle = f"{d} tries to break free and fails"
            self._struggle_kind = "fail"
            out.append(f"  - YOU MUST SHOW THIS: {d} TRIES TO BREAK FREE (" + self._try_how(e) + ") and FAILS. "
                       + ("It is everything she has left, and it is not much: a slow, late try, not a strong one. "
                          if e.get("fight_left") in ("fading", "nearly gone") else "")
                       + f"{a} feels it coming and punishes it, bearing down harder"
                       + (f" with {e['punish_with']}" if e.get("punish_with") else "") + ":")
            out += [self._hit_line(h) for h in e.get("punish_hits", [])]
        elif s == "partial":
            self._must_struggle = f"{d} partly breaks loose and hits {a}"
            self._struggle_kind = "partial"
            out.append(f"  - YOU MUST SHOW THIS: {d} PARTLY BREAKS LOOSE for a moment (" + self._try_how(e) + f") and "
                       f"lands a hit on {a} before {a} forces the pin back down. The pin holds:")
            out += [self._hit_line(h) for h in e.get("hits_on_pinner", [])]
        elif s == "overpowered":
            out.append(f"  - {d} fights it, but every attempt is overpowered; the struggles weaken second by second "
                       f"until they stop.")
        elif s == "escape" and e.get("last_second"):
            self._must_struggle = f"{d} kicks out at the very last second"
            self._struggle_kind = "escape"
            out.append(f"  - YOU MUST SHOW THIS: at the very last moment, "
                       + ("on the edge of passing out" if fm else "with the clock nearly run out") + f", {d} KICKS OUT "
                       f"and breaks the pin. {a} had her, almost; she isn't beaten down enough yet to be held. "
                       f"The pin is OVER.")
            out += self._escape_lines(e)
        elif s == "escape":
            self._must_struggle = f"{d} breaks free"
            self._struggle_kind = "escape"
            out.append(f"  - YOU MUST SHOW THIS: {d} BREAKS FREE" + ("" if fm else f" at second {e['seconds_to']}")
                       + f"! The pin is over; {a} is thrown off or loses the hold. How it starts (" + self._try_how(e)
                       + "); show the rest your way.")
            out += self._escape_lines(e)
        if any("under the" in str(g[3]).lower() and "water" in str(g[3]).lower()
               for g in (getattr(self, "grips", None) or []) if g[1] == d):
            out.append(f"  - THE DUNK: {poss(d)} face is held down in the shallow water. She is pushed under and let up "
                       f"for a gasp, pushed under and let up again: water up her nose and in her mouth, coughing, "
                       f"spluttering, the cold of it. It is a choke by water; she is NEVER drowning, and every time "
                       f"her head comes up she gets air.")
        elif e.get("against"):
            out.append(f"  - The pin is against {e['against']}: {poss(d)} head and shoulders are jammed against it, "
                       f"hard at her back, with nowhere to push back to.")
        if s in ("none", "fail", "partial", "overpowered") and not e.get("complete"):
            self._pin_holds = ([e["attacker"]] + list(e.get("helpers") or []), d, s)
            out.append(f"  - THE PIN STILL HOLDS when this beat ends. {d} is still on the ground under {a}"
                       + ("" if fm else f" at second {e['seconds_to']}") + f": she does NOT get out, roll clear, get up, or attack from her feet, and {a} is "
                       f"NOT thrown off, does not back away, and does not let go. Nothing follows the struggle: no "
                       f"escape, no chase, no new attack. End the beat with {d} still pinned.")
        if e.get("complete"):
            if e.get("elimination"):
                self._faint = (d, a, e["duration"])
                oc = e.get("out_cause") or {}
                if oc.get("cause") == "choking":
                    grip = f"the grip on her {oc.get('part') or 'neck'}" + (f" ({oc['with']})" if oc.get("with") else "")
                    if oc.get("kind") == "blood":
                        out.append(f"  - WHY SHE GOES OUT: a BLOOD CHOKE. It is {grip} that takes her under: it squeezes "
                                   f"the SIDES of her neck and cuts off the blood to her head. Show it that way: pressure "
                                   f"swelling behind her eyes, a roaring in her ears, the edges of everything going grey "
                                   f"and the world shrinking to a point, the strength draining out of her limbs. She may "
                                   f"still get a little air; it doesn't matter. It is quick at the very end, quicker "
                                   f"than she expects: she goes out almost before she knows it. The pain is still there, "
                                   f"but it is not what ends it. She is out cold, breathing, and she will wake.")
                    elif oc.get("kind") == "both":
                        out.append(f"  - WHY SHE GOES OUT: the CHOKE, air and blood together. It is {grip} that takes "
                                   f"her under: it crushes the front of her throat and squeezes the sides at once. Show "
                                   f"both: the breath that will not come, whistling and burning, AND the pressure "
                                   f"swelling behind her eyes, the roaring in her ears, the grey closing in and the world "
                                   f"shrinking to a point, her limbs going heavy. The pain is still there, but it is not "
                                   f"what ends it. She is out cold, breathing again once it is off her, and she will wake.")
                    else:
                        out.append(f"  - WHY SHE GOES OUT: the CHOKE ON HER WINDPIPE. It is {grip} that takes her under: "
                                   f"it presses the FRONT of her throat in. Show it that way: the breath that will not "
                                   f"come, whistling and burning, the panic of it, and then the grey coming in from the "
                                   f"sides as the blood is cut off too: her sight narrowing, sounds going far away, her "
                                   f"limbs getting heavy. The pain is still there, but it is not what ends it. She is out "
                                   f"cold, breathing again once it is off her, and she will wake.")
                elif oc.get("cause") == "constriction":
                    out.append(f"  - WHY SHE GOES OUT: the CONSTRICTION. The coils"
                               + (f" round her {oc['part']}" if oc.get("part") else "")
                               + f" have cut off her circulation: the blood held back, her limbs gone cold and heavy, her "
                               f"pulse pounding in her ears and then slowing, slower, her sight greying in from the "
                               f"edges, until she slips under. Her heart SLOWS; it never stops, and nothing about it is "
                               f"fatal: she is out cold, breathing, her pulse slow and steady, and she will wake.")
                elif oc.get("cause") == "pain":
                    out.append(f"  - WHY SHE GOES OUT: the PAIN. Nothing is stopping her breath enough to matter; it "
                               f"is the hurt"
                               + (f" in her {oc['part']}, under {oc.get('with') or 'the press'}," if oc.get("part") else "")
                               + f" that becomes more than her body will stay awake for. Show it that way: the pain "
                                 f"climbing past anything she can brace against, her body shaking with it, and then "
                                 f"everything dropping away at once. She is breathing the whole time.")
                out.append("  - " + ("This is the beat she goes under: nothing announces it, her body simply gives out."
                                    if fm else f"The full {e['duration']} seconds pass.")
                           + f" {d} FAINTS under the pin and is OUT. YOU MUST "
                           f"SHOW THIS, and it is the end of the passage: her last " + ("moments" if fm else "seconds") + f", the moment her body goes "
                           f"limp and still and her eyes close (she is breathing, out cold), then "
                           + (f"{a} feeling it and NOT letting go at once: she keeps her grip and her weight where they "
                              f"are for a moment or two longer to be sure it isn't a trick (watching, listening, "
                              f"feeling for anything pushing back; it adds no hurt), and only when nothing comes does "
                              f"she let go and ease off"
                              if self.rules.get("pin", {}).get("make_sure", True) else f"{a} feeling it and easing off")
                           + f", and the quiet after, from both fighters' perspectives. Don't stop before she is out.")
            else:
                out.append(("  - " + (f"{d} has nothing left: " if fm else f"The full {e['duration']} seconds pass. "))
                           + f"{a} has held the pin to the end.")
        return out

    @staticmethod
    def _alliance_end_lines(e):
        left = e.get("still_in") or []
        if len(left) < 2:
            return [f"The alliance between {' and '.join(e['members'])} is over ({e['why']})."]
        return [f"THE ALLIANCE ENDS ({e['why']}): from this moment {' and '.join(left)} are OPPONENTS again. No attack "
                f"happens because of it in this beat; show the shift: the look between them changing, a step apart, "
                f"each one turning to face the other and measuring her."]

    def more(self, condition, fighter_notes, scene, story_so_far, words=None, direction=""):
        """Stay in the moment: more paragraphs on what the last beat left behind, without the fight moving on.
        Nothing new happens: no attack, no fall, no get-up, no seconds on a pin clock."""
        n = self.rules.get("narration", {})
        words = int(words or n.get("more_words", n.get("words_per_pass", 300)))
        self._time_window, self._no_clock, self._important = None, True, False
        self._pin_beat = "PIN:" in condition
        self._must_parts, self._must_struggle, self._struggle_kind = [], None, None
        self._landed, self._slammed, self._charge_beat, self._one_strike = set(), set(), False, None
        self._weapons_ok, self._attackers, self._no_getup = None, set(), set()
        self._calm_beat, self._no_electric, self._getup_tries, self._must_reposition = False, False, None, None
        self._must_manhandle = None
        self._must_rise, self._rolled_up, self._loosened, self._must_event = None, set(), set(), None
        self._hurt_now = set()  # nobody is hit in this passage, so any NEW wound in it is invented
        self._calm_beat = len(self.strengths) < 2  # after the match the loser lies where she fell: no posture check
        self._story_tail = _tail(story_so_far, 6000)
        if self.progress:
            self.progress("narrator is staying with the moment")
        pin = (" A pin is running: it holds exactly as it is. No seconds pass in this passage, so don't mark or count "
               "any; no escape attempt, no new press." if self._pin_beat else "")
        msg = (f"SCENE: {scene}\n\nFIGHTERS:\n{fighter_notes}\n\n"
               f"CURRENT CONDITION (right now):\n{condition}\n\n"
               f"THE STORY SO FAR (the last part of it; continue from its final line):\n"
               f"{_tail(story_so_far, 3000) or '(nothing yet)'}\n\n"
               + "\n".join(self._posture_lines()) + "\n\n"
               f"STAY IN THIS MOMENT. No time has passed since the text above ended, and NOTHING NEW HAPPENS: no attack, "
               f"no new move, no new grip or bite, nobody falls, gets up, escapes, or changes position, and nobody is "
               f"hurt anew.{pin} Write about {words} more words that continue directly from the last line and go deeper "
               f"into the stillness after what just happened: how each hurt part feels now that the first shock is "
               f"settling (throbbing, heat, swelling, stiffness, trembling, a limb that won't take weight), breath "
               f"slowing or catching, what each fighter sees in the other and notices in her own body, small "
               f"involuntary movements, and the place around them ({self._sw('ambience', 'its sounds, its light, its cold or heat')}). "
               f"Move between the fighters. Use only injuries listed under CURRENT CONDITION. Do not repeat or rephrase "
               f"anything already written: find what hasn't been described yet. End on stillness, not on someone "
               f"starting to move."
               + (f" What the author wants this passage to dwell on: {direction}." if direction else "")
               + f" {DETAIL}")
        self._pin_holds = None
        self._facts = ("NOTHING NEW HAPPENS in this passage: no attack, no new hit or wound, nobody falls, gets up, "
                       "escapes, or changes position.\n" + "\n".join(self._posture_lines())
                       + "\n\nCURRENT CONDITION (right now):\n" + condition)
        text = self._call(msg, words)
        text = _balance_marks(self._drop_said_repeats(self._drop_seen(self._drop_sample_copies(
            self._drop_repeats(text, story_so_far)))))
        self.recent_lines = (self.recent_lines + said_lines(text))[-24:]
        return text

    def _ends_line(self, a):
        """Where a fighter who was knocked down, thrown or launched ends up: usually on the ground the way the engine
        says; sometimes slumped sitting against what she hit, sat down hard, or (rolled through it) on her feet."""
        d, fc = a["defender"], a.get("facing")
        if a.get("kept_feet"):
            self._must_rise = d
            return (f"But this time {d} ROLLS THROUGH the landing: she takes every impact, tumbles, gets her feet under "
                    f"her and comes up ON HER FEET, shaken and hurting, turned back toward her opponent. She does NOT "
                    f"stay down, nobody stands over her, and she needs no get-up. Show the impacts, the roll, and her "
                    f"coming up; the passage ends with her standing.")
        ends = str(a.get("ends") or "")
        if fc == "sitting up" and ends.startswith("slumped"):
            return (f"This time she ends SITTING, {ends}: her back against it, legs out in front of her "
                    f"({Engine.FACING_LOOK[fc]}). She does not end lying flat.")
        if fc == "sitting up":
            return (f"This time the blow SITS HER DOWN: her legs go and she drops hard onto her haunches, ending SITTING "
                    f"on the ground ({Engine.FACING_LOOK[fc]}). She does not end lying flat.")
        return "She ends up ON THE GROUND" + (f", {Engine.FACING_LOOK[fc]}" if fc in Engine.FACING_LOOK else "") + "."

    def _tumble_line(self, a):
        """She doesn't stop where she lands: the note for a fall that goes on across the ground."""
        tb = a.get("tumble")
        if not tb:
            return []
        self._must_tumble = a
        how = {"rolling": "rolling over and over", "skidding": "skidding on her side",
               "bouncing": "bouncing off the ground and coming down again",
               "cartwheeling": "end over end, limbs flung wide"}.get(tb.get("manner"), "rolling over and over")
        d = a["defender"]
        return [f"  - SHE TUMBLES ON. {d} does not land and lie still: the throw carries her on across "
                f"{tb['across']}, {how}, body loose, the arena going round her, "
                + (f"until she FETCHES UP against {tb['into']} and stops there" if tb.get("into") else
                   "until she rolls to a stop in the open, well away from where she first hit")
                + ". The surfaces above marked 'tumbling on' are that stretch: tell it as its own part of the fall, "
                  "after the first impact and before she lies still."]

    @staticmethod
    def _try_how(e):
        """How the pinned fighter goes about this try (the engine's pick, for variety between beats)."""
        return {"buck": "this time she bucks her whole body under the weight",
                "bridge": "this time she bridges, driving her middle up off the ground",
                "twist": "this time she twists hard to one side, trying to turn under her",
                "limb": "this time she wrenches at one trapped limb to get it out",
                "kick": "this time she lashes out with whatever she can still move: hind legs, tail, a free paw",
                "squirm": "this time she tries to slide out from under, backward or sideways",
                }.get(e.get("try_how"), "buck, bridge, twist, wrench a limb loose") + "; stage it your way"

    def _escape_lines(self, e):
        """An escape: the blow that frees her, and where both fighters are once the pin is gone."""
        a, d = e["attacker"], e["defender"]
        out = []
        if e.get("hits_on_pinner"):
            out.append(f"  - The blow that frees her lands on {a} (a kick, a bite, a swung limb, a blast at point-blank: "
                       f"whatever fits {poss(d)} body), and it hurts {a}:")
            out += [self._hit_line(h) for h in e["hits_on_pinner"]]
        for x in e.get("aftereffects") or []:
            out.append(f"  - WHAT THE PIN LEAVES BEHIND: {x['fighter']} is "
                       + {"stiff": "STIFF: the limbs that were trapped are numb, pins and needles coming back into them, "
                                   "slow to answer her (show it in how she gets up and moves).",
                          "fury": "FURIOUS: held down that long has left a cold, hard anger in her; her next blows come "
                                  "harder for it (show it in her face and how she moves; she is not cramped or stiff "
                                  "from it).",
                          }.get(x["status"], "CRAMPED from bearing down so long: her legs and shoulders locked, stiff "
                                             "to straighten (show it as she comes off).") + " No new injury.")
        pd = e.get("pinner_down")
        if isinstance(pd, dict):
            out.append(f"  - AFTER THE ESCAPE: this time {pd['fighter']} is THROWN OFF and GOES DOWN: she lands ON THE "
                       f"GROUND beside {d}"
                       + (f", {Engine.FACING_LOOK[pd['facing']]}" if pd.get("facing") in Engine.FACING_LOOK else "")
                       + f", and does not get up in this beat. {d} is loose but still ON THE GROUND where she was "
                       f"pinned, unless a GETTING UP line below says she rises. Nothing is pressing on {d} any more: no "
                       f"weight, no paws, no jaws. End with them apart, both down.")
            return out
        kept = [(ga, gd, gp, gw) for ga, gd, gp, gw in (getattr(self, "grips", None) or [])
                if {ga, gd} == {e["attacker"], d}]
        out.append(f"  - AFTER THE ESCAPE: {a} is shoved or knocked off her but STAYS ON HER FEET (she doesn't fall and "
                   f"doesn't need to get up). {d} is loose but still ON THE GROUND where she was pinned, unless a "
                   f"GETTING UP line below says she rises. Nothing is pressing on {d} any more: no weight, no paws, "
                   + ("no jaws. End with them apart." if not kept else
                      "nothing of the pin. But they do NOT end apart: " + "; ".join(
                          f"{ga} still has {gw or 'her grip'} on {poss(gd)} {gp}" for ga, gd, gp, gw in kept)
                      + ", so the two of them stay joined by that, at arm's length or closer."))
        return out

    @staticmethod
    def actors(bundle):
        """Who is acting this beat, and who is on the receiving end. Two-pass narration needs ONE actor;
        a beat where different fighters act gets a single combined pass (returns no actor)."""
        actions = bundle.get("actions") or [bundle["action"]]
        doers = {a.get("attacker") or a.get("fighter") or a.get("focus") for a in actions}
        if len(doers) != 1:
            return None, []
        actor = doers.pop()
        receivers = []
        for a in actions:
            for r in (a.get("defenders") or ([a["defender"]] if a.get("defender") else [])):
                if r not in receivers:
                    receivers.append(r)
        for e in bundle.get("also_this_beat", []):
            if e["type"] == "hold_ongoing" and e["defender"] not in receivers and e["defender"] != actor:
                receivers.append(e["defender"])
        return actor, [r for r in receivers if r != actor]

    # ---------- prompting ----------
    def _said(self, text):
        # fighters who are out are named too: on the beat Ripples faints, "the Buizel went limp" is about HER, not a
        # collapse of the fighter still standing (who used to inherit the sentence, and have it cut as invented)
        names = list(self.strengths) + [n for n in (getattr(self, "out_names", None) or []) if n not in self.strengths]
        return _who_said(text, names, getattr(self, "aliases", None), self._leads_for(text))

    def _leads_for(self, text):
        """{first sentence of a part: the fighter whose side that part is told from}, for the parts of this beat
        already written and for the one being checked now."""
        leads = dict(getattr(self, "_part_leads", None) or {})
        lead, prior = getattr(self, "_lead_now", None), getattr(self, "_prior_now", "") or ""
        if lead:
            body = text[len(prior):] if (prior and text.startswith(prior)) else text
            first = next((x.strip() for x in re.split(r"(?<=[.!?…])\s+|\n+", body) if x.strip()), None)
            if first:
                leads[first] = lead
        return leads

    def _absent_mentions(self, text):
        """Sentences that bring in a fighter who isn't in this fight at all: [(word, sentence)]. Always checked:
        the opening, every beat, the aftermath."""
        words = [w for w in (getattr(self, "absent_words", None) or []) if w]
        if not words:
            return []
        rx = re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b", re.I)
        return [(m.group(1), sent) for sent in re.split(r"(?<=[.!?…])\s+|\n+", text) for m in [rx.search(sent)] if m]

    def _out_mentions(self, text):
        """Sentences that bring up a fighter who is out of the fight and never landed a blow (so there is nothing of
        hers to remember): [(word, sentence)]. Not checked in the aftermath or on the beat she goes out."""
        words = [w for w in (getattr(self, "silent_out", None) or []) if w]
        if not words or getattr(self, "_calm_beat", False) or getattr(self, "_hurt_now", None) is None:
            return []
        rx = re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b", re.I)
        return [(m.group(1), sent) for sent in re.split(r"(?<=[.!?…])\s+|\n+", text) for m in [rx.search(sent)] if m]

    def _posture_lines(self):
        """Who is up and who is down this beat, straight from the engine, as the first thing the narrator reads."""
        ps, pe = getattr(self, "posture_start", {}) or {}, getattr(self, "posture_end", {}) or {}
        if not pe:
            return []
        bits = []
        for who, end in pe.items():
            start = ps.get(who)
            if who in (getattr(self, "_rolled_up", None) or set()):
                bits.append(f"{who}: is THROWN to the ground this beat, rolls through it, and ends {end}")
                continue
            bits.append(f"{who}: {end} all beat" if not start or start == end else f"{who}: starts {start}; ends {end}")
        for who, start in ps.items():
            if who not in pe and start:     # she is knocked out this beat: where she starts is where she stays
                bits.append(f"{who}: starts {start}; ends OUT COLD, lying where she was (she does not get up)")
        return ["POSTURE THIS BEAT (certain; the program tracks it): " + " | ".join(bits) + ". A fighter listed as ON "
                "HER FEET or UP stays up the whole beat: she never lies on the ground, is never under anyone, nobody "
                "stands over her, and she never has to get up. A fighter ON THE GROUND stays down unless a get-up or "
                "a lift is listed below. Earlier beats may have said otherwise: this line is right."]

    def _posture_problems(self, text):
        """Sentences that put a standing fighter on the ground, or pin someone when nobody is pinned:
        [(fighter or None, matched words, 'lying' | 'pinned', sentence)]."""
        if not self.strengths or not self.rules.get("narration", {}).get("accuracy_check", True):
            return []
        if getattr(self, "_hurt_now", None) is None or getattr(self, "_calm_beat", False):
            return []  # not a fight beat (intro, look, the aftermath, or the beat someone goes out)
        landed = getattr(self, "_landed", set())
        up = [w for w in self.strengths if w not in self.on_ground and w not in landed]
        if not up:
            return []
        all_up = len(up) == len(self.strengths)
        gone = [n for n in (getattr(self, "out_names", None) or []) if n not in self.strengths]
        out = []
        for sent, whos, named in _who_said(text, list(self.strengths) + gone, getattr(self, "aliases", None)):
            if any(w in gone for w in whos):
                continue  # about a fighter who's out and lying where she fell
            m = GROUNDED.search(sent)
            if m and re.search(r"\b(?:never|not|no|refus\w+|wouldn't|won't|without)\b[^.]{0,30}$", sent[:m.start()], re.I):
                m = None  # "she would not stay down"
            if m and re.match(r"(?:lay|lying|lies)\b", m.group(0), re.I):
                # "The pool lay flat." / "the water lay still": something that isn't a fighter is lying there
                before = re.findall(r"[A-Za-z']+", sent[:m.start()])
                subj = before[-1].lower() if before else ""
                people = {"she", "he", "they", "who", "and", "body", "form", "herself", "himself", "then", "still",
                          "just", "now"} | {n.lower() for n in list(self.strengths) + gone} \
                    | {a.lower() for a in (getattr(self, "aliases", None) or {})}
                if subj and subj not in people:
                    m = None
            if m and all_up:
                out.append((whos[0] if len(whos) == 1 else None, m.group(0), "lying", sent))
                continue
            if m and named and len(whos) == 1 and whos[0] in up:
                out.append((whos[0], m.group(0), "lying", sent))
                continue
            if all_up and not getattr(self, "_pin_beat", False) and not getattr(self, "_charge_beat", False):
                m2 = PINNED_SAID.search(sent)
                if m2:
                    out.append((None, m2.group(0), "pinned", sent))
        return out

    @staticmethod
    def _weapons_named(bundle):
        """Which natural weapons (claws, teeth, tail, horn) anything in this beat names: move names and
        descriptions, the director's labels, what a hold presses with."""
        words = []

        def walk(x, key=""):
            if isinstance(x, dict):
                for k, v in x.items():
                    walk(v, k)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    walk(v, key)
            elif isinstance(x, str) and key not in ("intent", "part", "surface", "positions", "attacker", "defender",
                                                    "fighter", "facing"):
                words.append(x)
        walk(bundle)
        blob = " ".join(words)
        return {w for w, rx in WEAPONS if re.search(rx, blob, re.I)}

    def _disabled_lines(self, text, sure=False):
        """Sentences that call a part useless or not working while it is only sore or hurting:
        [(part or None, sentence)]. sure=True keeps only the unmistakable wording (for cutting, not for a rewrite)."""
        if not self.rules.get("narration", {}).get("accuracy_check", True) or not self.part_damage:
            return []
        worst = max(self.part_damage.values(), default=0)
        strong = re.compile(r"\b(useless|dead weight|wouldn't (?:move|work|obey|respond)|(?:couldn't|could not) "
                            r"(?:move|use|feel) (?:it|her|his)|refused to (?:work|move|obey)|no longer (?:work|respond)\w*)\b",
                            re.I)
        out = []
        for sent in re.split(r"(?<=[.!?…])\s+|\n+", text):
            if not DISABLED.search(sent) and not DISABLED_VAGUE.search(sent):
                continue
            low_s = sent.lower()
            soft = not DISABLED_HARD.search(sent)  # only "limp", "dangling": how a tail or sac hangs, not a failure
            hit = False
            if DISABLED.search(sent) and (not sure or strong.search(sent)):
                for part, dmg in self.part_damage.items():
                    if soft and EXPRESSIVE.search(part):
                        continue  # a drooping tail, flat ears, a deflated sac are TELLS, not disabled limbs
                    if dmg < 150 and _mentions_exact(low_s, part) and _said_of(sent, part):
                        out.append((part, sent))
                        hit = True
            if not hit and worst < 150 and DISABLED_VAGUE.search(sent):
                out.append((None, sent))  # nothing on anyone is hurt badly enough to stop working
        return out

    def _hand_weight_lines(self, text):
        """A fighter who stands upright on two feet, shown putting weight on a paw or arm (her hand):
        [(fighter, matched words, sentence)]."""
        by = getattr(self, "damage_by", {}) or {}
        bipeds = {n for n, parts in by.items() if any("arm" in p for p in parts)}
        if not bipeds or not self.rules.get("narration", {}).get("accuracy_check", True):
            return []
        only_hers = {p for n in bipeds for p in by[n] if re.search(r"\b(paw|arm|hand)\b", p)
                     and not any(p in by[o] for o in by if o not in bipeds)}
        out = []
        for sent, whos, named in self._said(text):
            m = HAND_WEIGHT.search(sent)
            if not m:
                continue
            who = whos[0] if len(whos) == 1 and whos[0] in bipeds else None
            if who and not named and len(bipeds) < len(by):
                # "she" could be the other fighter: only sure when the words name a part that is the biped's alone
                if not any(re.search(r"\b" + re.escape(p) + r"\b", m.group(0).lower()) for p in only_hers):
                    who = None
            if who:
                out.append((who, m.group(0), sent))
        return out

    def _weapon_lines(self, text):
        """Sentences that attack with something this beat's moves don't use: [(kind, matched words, sentence)].
        kind 'bite': teeth going in when nothing in the beat bites. kind 'tail': the tail landing a strike that
        the move delivers with claws, horn, or teeth."""
        ok = getattr(self, "_weapons_ok", None)
        if ok is None or not self.rules.get("narration", {}).get("accuracy_check", True):
            return []
        out = []
        strikes = list(dict.fromkeys(getattr(self, "_strike_parts", []) or []))
        for sent, whos, named in self._said(text):
            if ("teeth" not in ok and not getattr(self, "_pin_beat", False) and not getattr(self, "_ongoing", False)
                    and not re.search(r"\b(had|memory|remember\w*|earlier|before|still)\b", sent, re.I)):
                m = BITING.search(sent)
                if m:
                    out.append(("bite", m.group(0), sent))
                    continue
            elif not getattr(self, "_pin_beat", False) and not re.search(
                    r"\b(had|memory|remember\w*|earlier|before)\b", sent, re.I):
                # teeth ARE in this beat: a bite still has to land on the fighter those teeth are on
                m = BITING.search(sent)
                victim = self._owner_after(sent, m.end()) if m else None
                if victim and victim not in (getattr(self, "_bite_victims", None) or {victim}):
                    out.append(("bite on " + victim, m.group(0), sent))
                    continue
            if ok and "tail" not in ok:
                m = TAIL_STRIKE.search(sent)
                others = [w for w in whos if w not in self._attackers]
                # the attacker's tail, not the tail of the fighter being hit ("Ripples' tails whipped...")
                theirs = (not named and others) or any(
                    re.search(r"\b" + re.escape(w) + r"(?:'s|’s|'|’) (?:\w+ )?tails?\b", sent) for w in others)
                if m and not theirs and any(_mentions(sent.lower(), p) for p in strikes):
                    out.append(("tail", m.group(0), sent))
                    continue
            if ok and "horn" not in ok:
                m = HORN_STRIKE.search(sent)
                if m and any(_mentions(sent.lower(), p) for p in strikes):
                    out.append(("horn", m.group(0), sent))
        return out

    @staticmethod
    def _all_hits(x, out=None):
        """Every hit record anywhere in a beat's results."""
        out = [] if out is None else out
        if isinstance(x, dict):
            if "part" in x and "damage_taken" in x:
                out.append(x)
            for v in x.values():
                Narrator._all_hits(v, out)
        elif isinstance(x, (list, tuple)):
            for v in x:
                Narrator._all_hits(v, out)
        return out

    @staticmethod
    def _all_dicts(x, out=None):
        out = [] if out is None else out
        if isinstance(x, dict):
            out.append(x)
            for v in x.values():
                Narrator._all_dicts(v, out)
        elif isinstance(x, (list, tuple)):
            for v in x:
                Narrator._all_dicts(v, out)
        return out

    def _parts_hit(self, bundle):
        """{fighter: {lower-case part names that take damage this beat}}."""
        out = {}
        for h in self._all_hits(bundle):
            if h.get("defender"):
                out.setdefault(h["defender"], set()).add(str(h["part"]).lower())
        return out

    def _bitten(self, bundle):
        """Fighters who have teeth on them this beat: the target of a move, label or grip that names jaws, teeth
        or a bite. In a pin both of them may bite (the pinner's contacts, the pinned one's fight back)."""
        teeth = re.compile(dict(WEAPONS)["teeth"], re.I)
        out = set()

        def words(x):
            m = x.get("move") or {}
            bits = [x.get("flavor", ""), x.get("with", ""), m.get("name", ""), m.get("about", "")]
            bits += [p.get("with", "") for p in x.get("parts") or [] if isinstance(p, dict)]
            return " ".join(str(b) for b in bits if b)
        for x in list(bundle.get("actions") or []) + list(bundle.get("also_this_beat") or []):
            if not isinstance(x, dict):
                continue
            if x.get("type") in ("pin_progress", "pin_start", "pin_forced"):
                out |= {x.get("attacker"), x.get("defender")} | set(x.get("helpers") or [])
            elif x.get("type") == "reposition" or x.get("manhandle"):
                out.add(x.get("defender"))   # carried, hauled or dragged: jaws on the scruff or a limb are a grip, not a bite
            elif teeth.search(words(x)):
                out |= set(x.get("defenders") or []) | {x.get("defender")}
                out |= {h.get("defender") for h in x.get("hits") or [] if isinstance(h, dict)}
        for att, dfn, part, with_ in getattr(self, "grips", None) or []:
            if teeth.search(str(with_)):
                out.add(dfn)
        return out - {None}

    def _owner_after(self, sent, at):
        """The fighter whose body is named right after position `at`: "...on the Absol's paw" -> Nocturne."""
        m = re.search(r"\b(?:the )?([A-Z]?[\w-]+)(?:'s|’s|'|’)\s", sent[at:at + 60])
        if not m:
            return None
        word = m.group(1)
        if word in self.strengths:
            return word
        for a, n in (getattr(self, "aliases", None) or {}).items():
            if a.lower() == word.lower() and n in self.strengths:
                return n
        return None

    def _grip_released_lines(self, text):
        """A grip that is still on when the beat ends, shown coming off: [(holder, held, part, words, sentence)].
        Pins have their own check (the pinned fighter may break loose for a moment); this is for plain holds."""
        grips = [g for g in (getattr(self, "grips", None) or []) if g[0] in self.strengths and g[1] in self.strengths]
        ended = getattr(self, "_grips_ended", set())
        # a pin's own contacts count too while the pin holds (jaws on a paw don't open mid-pin), except on a beat
        # where the pinned fighter breaks loose for a moment: then a contact may slip and come back
        pinned = {d for (pinners, d, k) in [getattr(self, "_pin_holds", None) or ((), None, None)] if d and k == "partial"}
        grips = [g for g in grips if g[1] not in pinned and (g[0], g[1]) not in ended]
        if not grips or not self.rules.get("narration", {}).get("accuracy_check", True) \
                or getattr(self, "_hurt_now", None) is None or getattr(self, "_calm_beat", False):
            return []
        out = []
        let_by = {x[0] for x in ended}     # fighters who really did let go of someone this beat
        freed = {x[1] for x in ended}      # ... and the ones who really were let go
        for sent, whos, named in self._said(text):
            m, g = LET_GO.search(sent), None
            if m and _ONLY_NAMED.search(sent[:m.start()]):
                m = None   # "to lift off was to let go": named as the thing she will not do
            if m and re.match(r"let it go\b", m.group(0), re.I) and (
                    re.match(r"\s+(?:straight|up|out|into|through|at|toward|towards|all at once|in a)\b", sent[m.end():], re.I)
                    or not re.search(r"\b(?:jaws?|teeth|fangs|grip|hold|bite|mouth|paws?|arm|leg|tails?|coils?|neck|throat|"
                                     r"limb|wrist|scruff)\b", sent, re.I)):
                m = None   # "she let it go straight up, into everything that touched her": a bolt, a breath, not a grip
            if m and getattr(self, "_loosened", None) and re.search(r"slack", m.group(0), re.I):
                m = None   # the grip was worked looser this beat (and stayed on): "slackened" is what happened
            if m:      # the holder lets go
                if any(w in let_by for w in whos):
                    continue
                g = (next((g for g in grips if g[0] in whos), None) if whos else
                     grips[0] if len(grips) == 1 else None)
                if g is None and (re.match(r"(?:bite|jaws?|grip|hold|teeth|fangs|tails?|coils?|lock|clamp)\b", m.group(0), re.I)
                                  or re.match(r"releas(?:ed|ing|es) [A-Z]", m.group(0))):
                    # "Her tails finally released Nocturne's neck": the sentence names the one being held
                    g = next((g for g in grips if g[1] in whos), None)
            if g is None:
                m = GOT_FREE.search(sent)
                if not m or any(w in freed for w in whos):
                    continue
                g = (next((g for g in grips if g[1] in whos), None) if whos else
                     grips[0] if len(grips) == 1 else None)
            if g is None or _NOT_REALLY.search(sent[:m.start()]):
                continue
            if re.search(r"\b(if|until|unless|when she finally|would have to)\b", sent[:m.start()], re.I):
                continue
            if _MOUTH_OPENS.search(sent) and not re.search(GRIP_FAMILY[2][1], str(g[3] if len(g) > 3 else "") or "", re.I):
                continue   # "She opened her mouth and let it go": tails are doing the holding, and the mouth lets a
                           # jet of water go, not the grip
            what = re.match(r"\s+(?:of|from) (?:the|her|his|that|this|its) ((?:[\w-]+ ){0,2}[\w-]+)", sent[m.end():])
            if what and not any(_mentions(what.group(1).lower(), x[2]) or any(
                    len(tw) > 2 and (tw in pw or pw in tw) for tw in re.findall(r"[a-z]+", what.group(1).lower())
                    for pw in re.findall(r"[a-z]+", str(x[2]).lower()) if pw not in ("left", "right", "upper", "lower"))
                    for x in grips if x[0] == g[0]):
                continue   # "let go of the foot" (last beat's bite ending) while what she HOLDS is the throat
            if re.search(r"slack", m.group(0), re.I) and RECLAMPED.search(sent[m.end():]):
                continue   # "the coil slackened for a heartbeat, then clamped down again": it is still on
            out.append((g[0], g[1], g[2], m.group(0), sent))
        return out

    def _missed_move_lines(self, text):
        """A move that only ever MISSED in this fight, spoken of as something that landed ("still shaking off the
        Night Slash's sting"): [(move, sentence)]. The move is matched as the narrator writes move names (Night
        Slash / NIGHT SLASH), and a sentence that says it missed is fine."""
        missed = [m for m in (getattr(self, "missed_moves", None) or []) if m]
        if not missed or not self.rules.get("narration", {}).get("accuracy_check", True):
            return []
        rx = re.compile(r"\b(" + "|".join(re.escape(m) + "|" + re.escape(m.upper()) for m in missed) + r")\b")
        out = []
        for sent in (x for para in text.split("\n") for x in _SENT.split(para.strip()) if x):
            m = rx.search(sent)
            if m and m.start() > 0 and not MISSED.search(sent) and not re.search(
                    r"\b(miss\w*|dodg\w+|evad\w+|avoid\w+|wide|empty air|nothing but|slipp\w+ (?:past|under|aside)|"
                    r"never (?:landed|touched|connected)|whiff\w*|next|again|another|ready|prepar\w+|would|could)\b", sent, re.I):
                out.append((m.group(1), sent))
        return out

    def _grip_place_lines(self, text):
        """A grip shown on the wrong part of her: the jaws are on her PAW and the story has them round her THROAT.
        [(holder, held, part, words, sentence)]. Only for grips with something of their own to name (jaws, tails,
        coils), and only when the sentence names a different kind of body part and not the right one."""
        if not self.rules.get("narration", {}).get("accuracy_check", True) or getattr(self, "_hurt_now", None) is None \
                or getattr(self, "_calm_beat", False):
            return []
        grips = [g for g in (getattr(self, "grips", None) or []) if g[0] in self.strengths and g[1] in self.strengths]
        rows = []
        for holder, held, part, with_ in grips:
            fam = next(((k, rx) for k, rx in GRIP_FAMILY if re.search(rx, with_ or "", re.I)), None)
            if fam is None:
                continue
            # the same holder gripping the same fighter with the same thing in two places: either part is right
            parts = [g[2] for g in grips if g[0] == holder and g[1] == held and re.search(fam[1], g[3] or "", re.I)]
            own = {k for k, rx in PART_CLASS for p in parts if re.search(rx, p, re.I)}
            if not own:
                continue
            ok = set(own)
            for k in own:
                ok |= PART_NEAR.get(k, set())
            noun, grip = "(?:" + fam[1] + ")", GRIP_ON.pattern
            near = re.compile(noun + r"(?:\s+[\w'’-]+){0,2}\s+(?:" + grip + r"|sunk|sank|buried|closed|shut|fastened)"
                              + "|" + grip + r"(?:\s+[\w'’-]+){0,4}\s+" + noun, re.I)
            rows.append((holder, held, part, near, ok, fam[0]))
        out = []
        for sent, whos, named in self._said(text) if rows else []:
            for holder, held, part, near, ok, fam in rows:
                m = near.search(sent)
                if not m or GRIP_PAST.search(sent[:m.start()]):
                    continue
                after = sent[m.end():m.end() + 70]
                here = [(k, x.group(0)) for k, rx in PART_CLASS for x in [re.search(rx, after, re.I)] if x]
                if not here or any(re.search(rx, sent, re.I) for k, rx in PART_CLASS if k in ok):
                    continue   # no part named after it, or the right one is in the sentence
                k, word = min(here, key=lambda kv: after.lower().find(kv[1].lower()))
                if fam == "tails" and k == "leg" and "tail" in word.lower():
                    continue
                out.append((holder, held, part, f"{' '.join(m.group(0).split())} … {word}", sent))
                break
        return out

    def _phantom_release_lines(self, text):
        """A fighter letting go with her jaws, tails or coils when she is holding nothing with them: the story is
        ending a grip that isn't there. [(fighter, words, sentence)]. Only when the sentence says whose they are."""
        if not self.rules.get("narration", {}).get("accuracy_check", True) or getattr(self, "_hurt_now", None) is None \
                or getattr(self, "_calm_beat", False) or not self.strengths:
            return []
        holders = {g[0] for g in (getattr(self, "grips", None) or [])} | {a for a, _d in getattr(self, "_grips_ended", set())}
        alias = {a.lower(): n for a, n in (getattr(self, "aliases", None) or {}).items()}
        # only wording that can't be anything but a grip ending: jaws open to snarl and tails uncoil on their own
        rx = re.compile(r"\b(?:the )?([A-Z]?[\w-]+)(?:'s|’s|'|’) (?:\w+ )?(?:(jaws?|teeth|fangs) (?:finally |suddenly |at last )?"
                        r"(releas(?:ed|ing|es)|let go|came (?:free|loose)|unclamped)|(tails?|coils?) (?:finally |suddenly |"
                        r"at last )?(releas(?:ed|ing|es)|let go))\b", re.I)
        out = []
        for sent in (x for para in text.split("\n") for x in _SENT.split(para.strip()) if x):
            m = rx.search(sent)
            if not m:
                continue
            who = m.group(1) if m.group(1) in self.strengths else alias.get(m.group(1).lower())
            if who and who in self.strengths and who not in holders and not _NOT_REALLY.search(sent[:m.start()]):
                out.append((who, f"{m.group(2) or m.group(4)} {m.group(3) or m.group(5)}", sent))
        return out

    def _grip_gone_lines(self, text):
        """A grip that ENDED in an earlier beat, told as if it were still on ("her foreleg still bound by those
        twin tails"): [(holder, held, part, words, sentence)]. Only grips with something of their own to name
        (tails, coils, jaws), for three beats after they end, and never when that fighter grips her again."""
        gone = getattr(self, "_grip_gone", None) or {}
        if not gone or not self.rules.get("narration", {}).get("accuracy_check", True) \
                or getattr(self, "_hurt_now", None) is None or getattr(self, "_calm_beat", False):
            return []
        live = {(g[0], g[1]) for g in (getattr(self, "grips", None) or [])}
        ok = getattr(self, "_weapons_ok", None) or set()
        pins = {p for pinners, d, _k in [getattr(self, "_pin_holds", None) or ((), None, None)] for p in pinners}
        rows = []
        for (holder, held), at in gone.items():
            part, with_ = (getattr(self, "_grip_seen", {}) or {}).get((holder, held), ("", ""))
            if not (0 < self._beat_no - at <= 3) or (holder, held) in live or holder in pins \
                    or holder not in self.strengths or held not in self.strengths:
                continue
            fam = next(((k, rx) for k, rx in GRIP_FAMILY if re.search(rx, with_, re.I)), None)
            if fam is None or (fam[0] == "jaws" and "teeth" in ok) or (fam[0] != "jaws" and "tail" in ok):
                continue   # nothing of its own to name, or teeth / a tail really are in this beat
            words = [w for w in re.findall(r"[a-z]+", part.lower()) if w not in ("left", "right", "upper", "lower")]
            noun, grip = "(?:" + fam[1] + ")", GRIP_ON.pattern
            # the noun and the holding word have to belong together: "tails still coiled", "bound by those twin tails"
            # (not "her jaws were clenched, her gaze locked on Ripples")
            near = re.compile(noun + r"(?:\s+[\w'’-]+){0,2}\s+" + grip + "|" + grip + r"(?:\s+[\w'’-]+){0,4}\s+" + noun, re.I)
            rows.append((holder, held, part, near, words))
        out = []
        if not rows:
            return out
        limb = re.compile(r"\b(paws?|forepaws?|legs?|forelegs?|limbs?|wrists?|arms?|necks?|throats?|ankles?|hocks?)\b", re.I)
        aliases = getattr(self, "aliases", None) or {}
        for sent, whos, named in self._said(text):
            for holder, held, part, near, words in rows:
                m = near.search(sent)
                if not m or GRIP_PAST.search(sent):
                    continue
                low = sent.lower()
                theirs = [held.lower()] + [a.lower() for a, n in aliases.items() if n == held]
                if not (any(re.search(r"\b" + re.escape(x) + r"\b", low) for x in theirs)
                        or any(re.search(r"\b" + re.escape(w) + r"s?\b", low) for w in words) or limb.search(sent)):
                    continue   # nothing of the other fighter is in the sentence: her tails may coil under herself
                out.append((holder, held, part, " ".join(m.group(0).split()), sent))
                break
        return out

    @staticmethod
    def _fall_meant(sent):
        """Is a fall really told here? "Her knees buckled, but she caught herself" and "she almost went down" are a
        stagger: the fighter is still up when the sentence ends."""
        m = FALL.search(sent)
        if not m:
            return None
        if NEARLY.search(sent[:m.start()][-45:]) or RECOVERED.search(sent[m.end():]):
            return None
        if _THING_FALLS.search(sent[:m.start()]):
            return None     # "a drop fell into the channel": water falls, nobody goes down
        if re.match(r"knees? buckl", m.group(0), re.I):
            # a buckling knee is what a leg hit looks like (the notes themselves suggest it). It is a fall only when
            # the sentence goes on to put her on the ground; "buckled a half-inch and caught" is a stagger
            rest = sent[m.end():]
            later = FALL.search(rest)
            if later and not re.match(r"knees? buckl", later.group(0), re.I) and not NEARLY.search(
                    rest[:later.start()][-45:]) and not RECOVERED.search(rest[later.end():]):
                return later
            if not re.search(r"\b(?:down|to the (?:ground|floor|stone|sand|grit)|onto the|under her and|beneath her and|"
                             r"dropp\w+|collaps\w+|sprawl\w+|fell|folded (?:up|under))\b", rest, re.I):
                return None
        return m

    def _down_is_hers(self, whos, named=True):
        """A sentence that names two fighters, one of whom really is on the ground (or was thrown there) this beat:
        "When Nocturne stepped back, Ripples slid down the boulder and crumpled." The fall belongs to her, so the
        sentence isn't an invented fall for the other one. The same goes for a sentence that names NOBODY ("Her back
        struck the rock") on a beat where someone was thrown, slammed or dragged: "her" is the one who landed, even
        when the last name before it was the thrower's."""
        landed = set(getattr(self, "_landed", set())) - {None}
        if not named and landed and whos and not any(w in landed for w in whos):
            return True
        # (a fighter driven into the scenery by a charge counts too: "her back struck the wall with the Absol's
        # weight behind it" is her impact; whether she then slides down is checked on its own)
        down = set(self.on_ground) | landed | set(getattr(self, "_slammed", set()))
        return len(whos) > 1 and any(w in down for w in whos)

    def _overblown_lines(self, text):
        """Sentences that make a serious injury of a part that is only MINOR (under the first pain level) and took
        no strike this beat (light pin pressure, an old knock): [(fighter, part, matched words, sentence)]."""
        by = getattr(self, "damage_by", {}) or {}
        if not by or not self.rules.get("narration", {}).get("accuracy_check", True) or getattr(self, "_hurt_now", None) is None:
            return []
        struck = {p.lower() for p in (getattr(self, "_strike_parts", []) or [])}
        out = []
        for sent, whos, named in self._said(text):
            m = OVERBLOWN.search(sent)
            if not m or len(whos) != 1 or whos[0] not in by or not named:
                continue
            low = sent.lower()
            parts = by[whos[0]]
            here = [p for p in parts if re.match(r"(left|right) ", p) and re.search(r"\b" + re.escape(p) + r"\b", low)]
            if len(here) == 1 and parts[here[0]] < 30 and here[0] not in struck:
                if not any(d >= 60 and _mentions_exact(low, p) for p, d in parts.items() if p != here[0]):
                    out.append((whos[0], here[0], m.group(0), sent))
        return out

    def _getup_lines_invented(self, text):
        """Sentences where a fighter who went down THIS beat (no get-up roll yet) tries to rise:
        [(fighter, matched words, sentence)]."""
        down = getattr(self, "_no_getup", None) or set()
        if not down or not self.rules.get("narration", {}).get("accuracy_check", True):
            return []
        out = []
        for sent, whos, named in self._said(text):
            m = TRY_UP.search(sent)
            if m and len(whos) == 1 and whos[0] in down:
                out.append((whos[0], m.group(0), sent))
        return out

    def _pin_broken_lines(self, text):
        """On a beat where the pin HOLDS: sentences that have the pinned fighter get loose or up, or the pinner
        thrown off or backing away: [(who, matched words, sentence)], in order."""
        held = getattr(self, "_pin_holds", None)
        if not held or not self.rules.get("narration", {}).get("accuracy_check", True):
            return []
        pinners, pinned, kind = held
        out = []
        for sent, whos, named in self._said(text):
            m, who = None, None
            if kind != "partial":
                m = ESCAPE_WORDS.search(sent)
                who = pinned
            if not m and pinned in whos and (named or whos == [pinned]):
                m, who = PINNED_UP.search(sent), pinned
            if not m and any(p in whos for p in pinners) and (named or len(whos) == 1):
                m, who = PINNER_OFF.search(sent), next(p for p in pinners if p in whos)
                if m and re.match(r"(?:shoved|kicked|knocked|sent) off\s+(?:of\s+)?(?:the|a|her own|his own|that)\b",
                                  sent[m.start():], re.I):
                    m = None
            if m and _ONLY_NAMED.search(sent[:m.start()]):
                m = None      # "to lift off was to let go": what she must NOT do, not something that happens
            if m and re.search(r"\b(?:a|an|the|its|that|this|each|every|one)\s+(?:\w+\s+){0,2}(?:stalagmite|stalactite|"
                               r"boulder|rock|stone|pillar|column|wall|tree|trunk|crate|spike|ridge|shadow|wave|"
                               r"cloud|mist|dust|light|shape)\s+$", sent[:m.start()], re.I):
                m = None      # "a stalagmite stood up out of the grey": the scenery, not a fighter
            if m and not _NOT_REALLY.search(sent[:m.start()]):
                out.append((who, m.group(0), sent))
        return out

    @staticmethod
    def _down_again(sent):
        """Does this say SHE went back down? "The Absol's hackles lay flat again" doesn't: that is her fur."""
        m = DOWN_AGAIN.search(sent)
        if m and re.search(r"\b(?:hackles|fur|ears?|tails?|ruff|whiskers|fins?|coat|scales|mane)\s+(?:\w+\s+){0,2}$", sent[:m.start()], re.I):
            return None
        return m

    def _failed_tries(self, text, who):
        """How many failed attempts at getting up the passage shows for this fighter."""
        n = 0
        for sent, whos, named in self._said(text):
            if who not in whos:
                continue
            if self._down_again(sent) or re.search(
                    r"\b(?:gave out|buckl\w+|slipp\w+|skidd\w+|fold\w+) (?:under|beneath|again|and)|\b(?:sank|dropp\w+|fell|went|"
                    r"slumped|collapsed|crumpled|sat|slid|thumped|landed) (?:back )?(?:down|to (?:a|one|her|his) knees?|onto)|"
                    r"\bback (?:down|onto|on) (?:her|his|the)\b|\b(?:did not|didn't|would not|wouldn't) hold (?:her|him)\b|\b(?:first|second) (?:try|"
                    r"attempt)\b[^.!?]{0,60}\b(?:fail\w*|gave|buckl\w+|slipp\w+|dropp\w+|sank|fell)", sent, re.I):
                n += 1
        return n

    def _shown_standing(self, text, who=None):
        """Does the passage END with the fighter who gets up this beat on her feet? Only sentences about HER count
        (the other one "standing over her" doesn't), a try that fails doesn't, and a later "dropped back down"
        undoes an earlier rise."""
        who = who or getattr(self, "_getup_who", None)
        if not who or who not in self.strengths:
            return bool(STANDING.search(text))
        up = False
        for sent, whos, named in self._said(text):
            if who not in whos:
                continue
            m = STANDING.search(sent)
            if m and not STAND_OVER.search(sent) and not NOT_UP.search(sent[:m.start()]):
                up = True
                # "...made it up, then dropped back down" in one sentence
                if self._down_again(sent[m.end():]):
                    up = False
            elif self._down_again(sent) and (named or whos == [who]):
                up = False
        return up

    def _shown_out(self, text):
        """Did the prose show the fighter who faints this beat going out? Only sentences about HER count."""
        f = getattr(self, "_faint", None)
        if not f:
            return True
        who = f[0]
        names = list(dict.fromkeys(list(self.strengths) + [who]))
        for sent, whos, named in _who_said(text, names, getattr(self, "aliases", None), self._leads_for(text)):
            m = OUT_SAID.search(sent)
            if m and who in whos and not _NOT_REALLY.search(sent[:m.start()]):
                return True
        return False

    def _made_sure(self, text):
        """After the sentence that shows her out, is the pinner shown holding on a moment longer (pin.make_sure)?
        Returns (shown, the first later sentence that lets her go, or None)."""
        f = getattr(self, "_faint", None)
        if not f or not self.rules.get("pin", {}).get("make_sure", True):
            return True, None
        who = f[0]
        names = list(dict.fromkeys(list(self.strengths) + [who]))
        out, free = False, None
        for sent, whos, named in _who_said(text, names, getattr(self, "aliases", None), self._leads_for(text)):
            if not out:
                m = OUT_SAID.search(sent)
                if m and who in whos and not _NOT_REALLY.search(sent[:m.start()]):
                    out = True
                    if HELD_ON.search(sent[m.end():]):
                        return True, None
                    if FREED_HER.search(sent[m.end():]):
                        return False, sent
                continue
            if HELD_ON.search(sent):
                return True, None
            mf = FREED_HER.search(sent) if free is None else None
            if mf:
                # the fainting fighter's OWN tails or limbs going slack ("the tails slid off her hind legs and lay
                # where they fell") are not the pinner letting go of anything
                tool = re.search(r"\b(tails?|coils?|fins?|paws?|limbs?|legs?|arms?|ears?)\s+(?:\w+\s+)?$", sent[:mf.start()], re.I) \
                    or re.match(r"(tails?|coils?|fins?|paws?|limbs?|legs?|arms?)\b", mf.group(0), re.I)
                if tool and not any(tool.group(1).rstrip("s").lower() in str(w).lower()
                                    for a_, d_, p_, w in (getattr(self, "grips", None) or []) if d_ == who):
                    mf = None
            if mf:
                return False, sent     # she lets go with nothing before it: the moment of making sure is missing
        return False, None

    def _ensure_sure(self, text):
        """pin.make_sure: the pinner doesn't let go the instant she feels her go limp. When the passage has her
        release at once (or never says), the moment of making sure is put in, just before the release."""
        f = getattr(self, "_faint", None)
        if not f or not text:
            return text
        shown, free = self._made_sure(text)
        if shown:
            return text
        who, by = f[0], f[1]
        if self.progress:
            self.progress(f"{by} let go the moment {who} went limp: adding the moment she makes sure first")
        waits = random.choice([
            f"{by} did not let go at once. She kept her grip where it was a moment longer, waiting for the twitch of a "
            f"trick, and felt nothing push back.",
            f"{by} held on. One breath, then another, every sense on the body under her for the first sign of a "
            f"feint; none came.",
            f"For a moment longer {by} stayed exactly as she was, weight down, grip closed, in case it was a trick. "
            f"Nothing under her moved.",
        ])
        if free and free in text and not OUT_SAID.search(free):
            return text.replace(free, waits + " " + free, 1)
        if free:
            return text.rstrip() + "\n\n" + waits.replace("did not let go at once", "had not let go all at once") \
                   + " Only then did she draw fully away."
        return text.rstrip() + "\n\n" + waits + " Only then did she let go and ease her weight off."

    def _ensure_faint(self, text):
        """A pin held to the end puts her out, so the passage has to show it. When the cuts took it (or it was never
        written), a closing passage is written for it; if even that fails, plain sentences say it."""
        f = getattr(self, "_faint", None)
        if not f or not text or self._shown_out(text):
            return self._ensure_sure(text)
        who, by, secs = f
        if self.progress:
            self.progress(f"the passage never showed {who} fainting: adding the ending")
        ask = (getattr(self, "_last_context", "")
               + f"The beat so far (already written; never repeat or rephrase it):\n<<<\n{_tail(text, 2500)}\n>>>\n\n"
                 f"The ending is still missing: {who} FAINTS. Write ONLY that, about 150 words in two or three "
                 f"paragraphs, naming {who}: the last of her struggle giving out under {poss(by)} pin, her body going "
                 f"limp and still, her eyes closing (she is breathing, out cold); then {by} feeling it, holding a moment "
                 f"longer, and easing her weight off. No new attack, no clock or seconds, no speech, nobody gets up.")
        more = ""
        try:
            more = (self._generate(ask, 170) or "").strip() if getattr(self, "_last_context", "") else ""
        except llm.LLMError:
            more = ""
        more = re.sub(r"\n{3,}", "\n\n", more)
        if more and len(more.split()) <= 320 and self._shown_out(more) and not GAME_TERMS.search(more) \
                and not (_TIME_MARK.search(more) or _REMAINING.search(more) or _COUNTDOWN.search(more)):
            gore = gore_pattern(self.rules)
            if gore is None or not gore.search(more):
                return self._ensure_sure(text.rstrip() + "\n\n" + _balance_marks(more))
        plain = (f"{poss(who)} struggles faded. Her eyes slid shut, her body went limp under {by}, and she lay still, "
                 f"breathing but out cold.\n\n{by} held a moment longer, felt nothing push back, and eased her weight off.")
        return text.rstrip() + "\n\n" + plain

    def _ensure_getup(self, text):
        """The get-up is rolled by the program, so the passage has to end with her standing. When the cuts took
        that away (or it was never written), one short closing paragraph is written for it; if even that fails, a
        plain sentence says it."""
        e = getattr(self, "_getup_event", None)
        if not e or not text or not self.rules.get("narration", {}).get("accuracy_check", True) \
                or self._shown_standing(text):
            return text
        who, grab = e["fighter"], e["grab"]
        if self.progress:
            self.progress(f"the passage never ended with {who} on her feet: adding the get-up")
        held = "; ".join(f"{poss(g['by'])} grip on her {g['part']} is still on" for g in e.get("held") or [])
        ask = (getattr(self, "_last_context", "")
               + f"The beat so far (already written; never repeat or rephrase it):\n<<<\n{_tail(text, 2500)}\n>>>\n\n"
                 f"One thing is still missing: {who} finally getting up. Write ONLY that, as one closing paragraph of 40 "
                 f"to 70 words that names {who}: her last try succeeds, using {grab}, and she ends ON HER FEET, unsteady "
                 f"and hurting" + (f" ({held})" if held else "") + ". No attack, no fall, no speech, nothing else happens.")
        more = ""
        try:
            more = re.sub(r"\n+", " ", self._generate(ask, 70) or "").strip() if getattr(self, "_last_context", "") else ""
        except llm.LLMError:
            more = ""
        if more and len(more.split()) <= 130 and self._shown_standing(more) \
                and not any(sent in more for sent in self._bad_sentences(text + "\n\n" + more, "")):
            return text.rstrip() + "\n\n" + more
        plain = {"biped": f"{who} got her feet under her at last and stood, swaying, one paw braced against {grab}.",
                 "quadruped": f"{who} got her legs under her at last and stood, swaying, her shoulder against {grab}.",
                 "serpent": f"{who} braced her coils against {grab} at last and rose, swaying.",
                 "avian": f"{who} beat her wings hard at last and pushed up onto her talons, swaying."}[e.get("plan", "biped")]
        return text.rstrip() + "\n\n" + plain

    def _healthy_lines(self, text):
        """Sentences that call a badly hurt part (very painful or worse) good, strong, or unhurt:
        [(fighter, part, matched words, sentence)]. Usually a left/right mix-up."""
        by = getattr(self, "damage_by", {}) or {}
        if not by or not self.rules.get("narration", {}).get("accuracy_check", True):
            return []
        out = []
        for sent, whos, named in self._said(text):
            m = HEALTHY.search(sent)
            if not m or len(whos) != 1 or whos[0] not in by:
                continue
            low = sent.lower()
            for part, dmg in by[whos[0]].items():
                # the sided name must be in the sentence, close to the claim ("Her right paw—still good, still strong")
                at = low.find(part)
                if dmg >= 90 and re.match(r"(left|right) ", part) and at >= 0 and abs(at - m.start()) <= 45:
                    other = part.replace("left ", "right ") if part.startswith("left") else part.replace("right ", "left ")
                    if other in low and abs(low.find(other) - m.start()) < abs(at - m.start()):
                        continue  # the claim sits next to the other side's part
                    out.append((whos[0], part, m.group(0), sent))
                    break
        return out

    def _foreign_mentions(self, text):
        """Sentences that give someone a feature no fighter in this fight has: [(word, sentence)]."""
        words = [w for w in (getattr(self, "foreign_words", None) or []) if w]
        if any(re.search(r"\btails?\b", str(g[3] or ""), re.I) for g in (getattr(self, "grips", None) or [])):
            words = [w for w in words if w != "coils"]   # tails wound round a limb: "the coils" is a fair word for them
        if not words:
            return []
        rx = re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b", re.I)
        return [(m.group(1), sent) for sent in re.split(r"(?<=[.!?…])\s+|\n+", text) for m in [rx.search(sent)] if m]

    def remember(self, texts):
        """Note the short sentences of beats already told (after a /load), so they aren't used word for word again."""
        for t in ([texts] if isinstance(texts, str) else texts or []):
            self._drop_seen(strip_pov(t))

    def _beat_weight(self, bundle):
        """How much this beat matters in the fight: ("ends" | "turning" | "tense" | "big" | "hard" | "ordinary", why)."""
        ss = getattr(self, "story_state", None) or {}
        acts = bundle.get("actions") or []
        also = bundle.get("also_this_beat") or []
        if any(e.get("type") == "pin_progress" and e.get("complete") and e.get("elimination") for e in also):
            return "ends", ["the fight ends in this beat"]
        why, big = [], []
        # a TURNING POINT is rare: the first time a fighter is pinned, an escape from a pin that had really begun to
        # tell on her, or the pressing changing hands. Other pins and quick kick-outs are big moments, no more
        for a in acts:
            if a.get("type") in ("pin_start", "pin_forced") and not a.get("continuing"):
                first = bool(ss) and int((ss.get("pins") or {}).get(a.get("defender"), 1)) <= 1
                (why if first else big).append(f"{a.get('defender')} is pinned for the first time" if first else "a pin goes on")
        for e in also:
            if e.get("type") == "pin_progress" and e.get("struggle") == "escape":
                deep = float(e.get("fade_from") or 0) >= 35 or int(e.get("beats") or 0) >= 3
                (why if deep else big).append("she breaks a pin that had begun to tell on her" if deep else "a pin is kicked off")
        if ss.get("turned"):
            why.append(ss["turned"])
        if why:
            return "turning", why
        if ss.get("tense") and any(e.get("type") == "pin_progress" for e in also):
            return "tense", ["a pin is on and the one under it is far gone"]
        if big:
            return "big", big
        # a BIG moment is a move with real size to it: a throw or a slam, a charge that carries her into something,
        # a pummelling, a chain of three or more that all land. A grab, a two-blow chain or a held stream is ordinary
        if any((a.get("manhandle") in ("throw", "slam") and a.get("hits"))
               or (a.get("charge") and not (a.get("charge") or {}).get("skipped"))
               or a.get("pummel") for a in acts) \
                or sum(1 for a in acts if a.get("chain") and a.get("hits")) >= 3:
            return "big", ["one of the big moves of the fight"]
        worst = [(w, p) for w, p, lv in (getattr(self, "_breaking", None) or []) if lv in ("devastated", "numb with shock")]
        if worst:
            who = sorted({w for w, _ in worst})
            return "hard", [f"a part of {' and '.join(who)} is hurt past bearing for the first time"]
        return "ordinary", []

    def _story_note(self, bundle):
        """THE FIGHT SO FAR: how the story stands and how much this beat matters in it (narration.story_state)."""
        ss = getattr(self, "story_state", None)
        if not self.rules.get("narration", {}).get("story_state", True):
            return ""
        acts = bundle.get("actions") or []
        if acts and all(a.get("type") == "aftermath" for a in acts):
            return ""
        kind, why = self._beat_weight(bundle)
        if not ss:
            # the beat that ends the fight: there is no "how it stands" any more, only that this is the end
            return ("THE FIGHT SO FAR: THE FIGHT ENDS IN THIS BEAT. Give the ending room: nothing is rushed, and "
                    "nothing is added after it.\n\n") if kind == "ends" else ""
        weight = {
            "ends": "THE FIGHT ENDS IN THIS BEAT. Give the ending room: nothing is rushed, and nothing is added after it.",
            "turning": "THIS BEAT IS A TURNING POINT (" + "; ".join(why) + "): slow down for it, and let both of them "
                       "feel that something has changed.",
            "tense": "This is the tensest stretch of the fight so far (" + "; ".join(why) + "). Neither of them knows "
                     "how it will come out. Keep it close, quiet and exact.",
            "big": "This beat holds a big moment (" + "; ".join(why) + "): give it size and weight, and tell it in order.",
            "hard": "A hard moment (" + "; ".join(why) + "): that one thing gets its full weight. The rest of the "
                    "beat is told plainly round it.",
            "ordinary": "This beat is an ordinary exchange in the run of the fight: tell it in full detail, with no "
                        "more drama than it carries. Keep the largest reactions for the moments that change something.",
        }[kind]
        lines = [f"- Where it stands: {ss['stage']}."] + [f"- {n} {t}" for n, t in ss["fighters"].items()] + [f"- {weight}"]
        return ("THE FIGHT SO FAR (the shape of the whole, worked out by the program; let it colour how each of them "
                "moves, looks at the other and thinks. Never state it as a summary, never have a fighter know more "
                "than she could, and never predict how it ends: worry and confidence are fine, certainty is not):\n"
                + "\n".join(lines) + "\n\n")

    def _leaned_note(self, story_so_far, bundle):
        """WORDS THE STORY HAS LEANED ON: describing words the last few beats used again and again."""
        cfg = self.rules.get("narration", {}).get("leaned_words", {}) or {}
        if not cfg.get("enabled", True):
            return ""
        text = _tail(story_so_far or "", int(cfg.get("look_back_chars", 7000))).lower()
        skip = set(_PLAIN_WORDS)
        for who, parts in (self.damage_by or {}).items():
            skip |= set(re.findall(r"[a-z]+", who.lower()))
            for p in parts:
                skip |= set(re.findall(r"[a-z]+", p.lower()))
        for k, v in (getattr(self, "aliases", None) or {}).items():
            skip |= set(re.findall(r"[a-z]+", f"{k} {v}".lower()))
        try:      # the words of this beat's own events (move names and the like) are not the story's habit
            skip |= set(re.findall(r"[a-z]+", self.describe(bundle).lower())) if cfg.get("skip_event_words", True) else set()
        except Exception:
            pass
        cfg_scene = getattr(self, "scene_cfg", None) or {}
        skip |= set(re.findall(r"[a-z]+", " ".join(str(cfg_scene.get(k, "")) for k in ("place", "ground", "rough", "slick")).lower()))
        counts, shown = {}, {}
        for w in re.findall(r"[a-z]{3,}", text):
            stem = w[:-2] if w.endswith("ly") and len(w) > 5 else w[:-1] if w.endswith("s") and not w.endswith("ss") and len(w) > 4 else w
            if w in skip or stem in skip:
                continue
            counts[stem] = counts.get(stem, 0) + 1
            shown.setdefault(stem, w)
        need = max(int(cfg.get("min_count", 5)), len(text.split()) // 170)
        top = sorted((c, s_) for s_, c in counts.items() if c >= need)[::-1][:int(cfg.get("max", 6))]
        if not top:
            return ""
        return ("WORDS THE STORY HAS LEANED ON LATELY (each is in the last few beats several times; where another word "
                "will do the work this beat, use the other word): " + ", ".join(shown[s_] for _, s_ in top) + ".\n\n")

    # ---------- building blocks: ideas that fit the fight as it stands, the least-offered first ----------
    def _blocks(self):
        b = getattr(self, "_block_store", None)
        if b is None:
            b = self._block_store = story_blocks.Blocks(self.rules)
        b.cfg = (self.rules.get("narration", {}) or {}).get("blocks", {}) or {}
        b.enabled = bool(b.cfg.get("enabled", True))
        return b

    def _worst_parts(self, who, n=2, floor="hurting", skip=(), before=None):
        """Her n worst-hurt parts at `floor` or worse: [(part name in lower case, level, zone)]. before: {part:
        damage before this beat} for parts hit this beat (what an opponent could see BEFORE striking)."""
        order = [t["label"] for t in pain_tiers(self.rules)]
        out = []
        for part, dmg in (self.damage_by.get(who) or {}).items():
            if before is not None and part.lower() in before:
                dmg = before[part.lower()]
            level = self._pain(dmg)["label"]
            if part in skip or order.index(level) < order.index(floor):
                continue
            out.append((dmg, part, "devastated" if level == "numb with shock" else level,
                        story_blocks.ZONE_OF.get(body_region(part))))
        return [(p, lv, z) for _, p, lv, z in sorted(out, reverse=True)[:n]]

    def _blk_feats(self, who):
        """What her body has (for body-specific blocks). A fighter who goes out this beat is no longer in the list
        of bodies: what was known of her is remembered."""
        cache = self.__dict__.setdefault("_feats_cache", {})
        parts = self.damage_by.get(who) or {}
        if parts:
            cache[who] = story_blocks.features(parts)
        return cache.get(who, set())

    def _blk_posture(self, who, end=False):
        """standing | down | pinned: as the beat begins (what an opponent sees before she acts), or as it ends."""
        if end:
            if who in (getattr(self, "pinned_now", None) or ()):
                return {"pinned"}
            return {"down"} if who in (getattr(self, "out_names", None) or ()) or "GROUND" in str(
                (getattr(self, "posture_end", None) or {}).get(who, "")).upper() else {"standing"}
        start = str((getattr(self, "posture_start", None) or {}).get(who, "")).upper()
        return {"pinned"} if "PINNED" in start else {"down"} if ("ON THE GROUND" in start or "OUT" in start[:8]) else {"standing"}

    def _blk_stage(self):
        st = str((getattr(self, "story_state", None) or {}).get("stage", ""))
        return {"early"} if st.startswith("early") else {"late"} if st.startswith("late") else \
            {"end"} if st.startswith("near") else {"middle"}

    def _blocks_for(self, key, acts, pin_events, also=(), actor=None, receivers=(), first=True, last=True):
        """The BUILDING BLOCKS note for one part of a beat ("" when the blocks are off or nothing fits)."""
        B = self._blocks()
        if not B.enabled or not B.entries:
            return ""
        take, act = key in ("take", "all", "after"), key in ("act", "all", "setup")
        lines = []
        feats = self._blk_feats
        state = lambda who: story_blocks.state_of(self.strengths.get(who, 100 if who in self.damage_by else 0))
        stage = self._blk_stage()
        # reactions the last beats already used: a block that is one of them is not offered either
        worn = set().union(*(self.recent_reactions or [set()])) if getattr(self, "recent_reactions", None) else set()
        side = ["act"]

        def add(label, picks):
            slot = next((k for k, rx in self._SLOTS if re.search(rx, label)), "move")
            lines.extend((side[0], slot, f"{label}: {p}") for p in picks if not (reactions_used(p) & worn))

        posture = self._blk_posture

        def sore_core(who):      # where breathing itself hurts
            return {z for _, _, z in self._worst_parts(who, 8, "hurting") if z in ("chest", "neck", "belly")}

        def standing(who, other):
            a_, b_ = self.strengths.get(who), self.strengths.get(other)
            if a_ is None or b_ is None or abs(a_ - b_) < 15:
                return {"level"}
            return {"winning"} if a_ > b_ else {"losing"}

        def mind(who, role, other, **more):      # one thought and one feeling that fit where the fight stands
            st = standing(who, other) if other else {"level"}
            add(f"{poss(who)} thought", B.pick("thought", 1, role={role} | (st - {"level"}), stage=stage, standing=st,
                                                 fighter=who.lower(), **more))
            add(f"what {who} feels", B.pick("emotion", 1, role={role}, stage=stage, standing=st, fighter=who.lower(), **more))

        def hits_on(who):        # [(damage taken, part, damage BEFORE its first hit this beat, damage after, action index)]
            out, first_b4 = [], {}
            for i, a in enumerate(acts):
                extra = ((a.get("takedown") or {}).get("hits") or []) if a.get("type") in ("pin_start", "pin_forced") else []
                for h in list(a.get("hits") or []) + extra:
                    if (h.get("defender") or a.get("defender")) == who and h.get("part"):
                        first_b4.setdefault(h["part"], h.get("damage_before", 0))
                        out.append((h.get("damage_taken", 0), h["part"], first_b4[h["part"]], h.get("damage_after", 0), i))
            for e_ in pin_events or ():      # the blow that frees a pinned fighter, or the one she lands breaking loose
                for h in e_.get("hits_on_pinner") or []:
                    if e_.get("attacker") == who and h.get("part"):
                        first_b4.setdefault(h["part"], h.get("damage_before", 0))
                        out.append((h.get("damage_taken", 0), h["part"], first_b4[h["part"]], h.get("damage_after", 0), 99))
            return out

        def take_blocks(who, by):      # what a blow is like to the one it lands on
            mine = sorted(hits_on(who), reverse=True)
            best = {}
            for taken, part, b4, after, i in mine:      # one entry per part: the level it ends at
                best.setdefault(part, (taken, part, after, i))
            whole = len(best) > 8                        # a whole-body move: the event list names what hurt most
            top = list(best.values())[:2]
            if whole:
                order = [t["label"] for t in pain_tiers(self.rules)]
                top = sorted(best.values(), key=lambda x: (-self._strength_rank(x[0]), -x[2]))[:2]
            for taken, part, after, i in top:
                lv = self._pain(after)["label"]
                if lv == "minor":
                    continue
                add(f"how the hurt in {poss(who)} {part} may feel", B.pick(
                    "sensation", 1, fmt={"part": part.lower()}, level="devastated" if lv == "numb with shock" else lv,
                    zone=story_blocks.ZONE_OF.get(body_region(part)), has=feats(who),
                    part=set(re.findall(r"[a-z]+", part.lower()))))
            if not top:
                return False
            taken, part, after, i = top[0]
            near = next((p for t2, p, _, _, j in mine if j == i and p != part), None)
            if near and not whole:
                add("how it spreads", B.pick("travel", 1, fmt={"part": part.lower(), "next": near.lower()}))
            raw = (getattr(self, "_raw_done", None) or {}).get(who)
            if raw is not None:
                # a blow on a part that was already badly hurt: a reaction as raw as she can no longer keep in
                add(f"a reaction of that size from {who}", B.pick(
                    "raw", 1, fmt={"part": part.lower()}, raw=self.RAW_LEVELS[raw][0], has=feats(who))
                    + B.pick("reaction", 1, size=self._strength_key(taken), has=feats(who)))
            else:
                add(f"a reaction of that size from {who}", B.pick("reaction", 2, size=self._strength_key(taken), has=feats(who),
                                                                   fighter=who.lower()))
            mind(who, "receiver", by)
            if who not in (getattr(self, "pinned_now", None) or ()):
                add(f"{poss(who)} breath", B.pick("breath", 1, state=state(who), zone=sore_core(who)))
            return True

        def strike_blocks(who, target):      # staging a blow, from the one who throws it
            kinds, close = set(), False
            for a in acts:
                if a.get("attacker") != who or a.get("type") in ("pin_start", "pin_forced", "breather", "none"):
                    continue
                mv = a.get("move") or {}
                close = close or bool(a.get("pummel") or a.get("point_blank"))
                kinds |= story_blocks.kind_of(mv.get("name", ""), mv.get("about", ""), a.get("with", ""),
                                              a.get("manhandle") or "", a.get("type") == "grapple_start",
                                              close=bool(a.get("pummel")),
                                              ranged=str(mv.get("target", "")) in ("whole_body", "spread")
                                              or "ranged" in str(mv.get("range", "")) or bool(mv.get("ranged")))
            if close and "grab" not in kinds:
                kinds = {"close"}
            if {"grab", "close"} <= kinds:      # a grab and then blows inside it: an idea for each
                add(f"a way {who} might stage it", B.pick("movement", 1, kind={"grab"}, need=("kind",), has=feats(who))
                    + B.pick("movement", 1, kind={"close"}, need=("kind",), has=feats(who)))
            else:
                add(f"a way {who} might stage it", B.pick("movement", 2, kind=kinds, has=feats(who)) if kinds
                    else B.pick("movement", 1, has=feats(who)))
            return kinds

        if key in ("dwell", "watch"):
            m = next((x for x in getattr(self, "_moments", []) if x["key"] == key), None)
            if not m:
                return ""
            who = m["who"]
            other = next((x["who"] for x in self._moments if x["key"] != key), None)
            if key == "dwell":
                side[0] = "take"
                for p, lv, z in self._worst_parts(who, 2, "very painful"):
                    add(f"how the hurt in {poss(who)} {p} feels now", B.pick(
                        "sensation", 1, fmt={"part": p}, level=lv, zone=z, has=feats(who),
                        part=set(re.findall(r"[a-z]+", p))))
                    add(f"what it does to {poss(who)} body now", B.pick("dwell", 1, fmt={"part": p}, zone=z,
                                                                        has=feats(who), state=state(who),
                                                                        fighter=who.lower()))
                raw = (getattr(self, "_raw_done", None) or {}).get(who)
                add(f"a reaction of that size from {who}", B.pick("held_in", 2, state=state(who), has=feats(who),
                                                                   fighter=who.lower(),
                                                                   raw={self.RAW_LEVELS[raw][0]} if raw is not None else None))
                add(f"{poss(who)} breath", B.pick("breath", 1, state=state(who), zone=sore_core(who))
                    + B.pick("dwell_breath", 1, state=state(who)))
                mind(who, "receiver", other)
                return self._blocks_plan(lines, "take", False, last, who, other)
            side[0] = "act"
            victim = next((x[0] for x in sorted(((v_, sum(d for w_, _, d, _, _ in self._linger_pool if w_ == v_))
                                                  for v_ in {x[0] for x in self._linger_pool}), key=lambda t: -t[1])),
                          None)
            if victim:
                add(f"what {who} can see of {victim}", B.pick("watch", 2, fmt={"part": m.get("part", "wound")},
                                                               fighter=who.lower(),
                                                               has=feats(victim), state=state(victim),
                                                               posture=posture(victim, end=True)))
                add(f"what {who} can see of {victim}", B.pick("tell", 1, has=feats(victim), state=state(victim)))
            add(f"{poss(who)} thought", B.pick("watch_thought", 1, state=state(victim) if victim else None,
                                                 fighter=who.lower()))
            add(f"what {who} feels", B.pick("emotion", 1, role={"attacker"}, stage=stage))
            add(f"{poss(who)} breath", B.pick("breath", 1, state=state(who), zone=sore_core(who)))
            return self._blocks_plan(lines, "act", False, last, who, victim)
        types = [a.get("type") for a in acts]
        # --- the newer kinds of moment (clash, flight, stances, water in the mouth, coils, weather, a pin just
        # broken): one idea each, on the side of the beat it belongs to
        for a in acts:
            att_, dfn_ = a.get("attacker"), a.get("defender")
            if act and a.get("clash"):
                side[0] = "act"
                add("the clash itself", B.pick("clash", 1, has=feats(att_)))
            if act and a.get("type") == "take_off":
                side[0] = "act"
                add(f"{a.get('fighter')} taking off", B.pick("aerial", 1, moment={"takeoff"}))
            if act and a.get("dive"):
                side[0] = "act"
                add(f"{poss(att_)} dive", B.pick("aerial", 1, moment={"dive"}))
            if a.get("carried"):
                side[0] = "take" if take else "act"
                add(f"{dfn_}, carried up and dropped", B.pick("aerial", 1, moment={"carried"}))
            if take and a.get("grounded"):
                side[0] = "take"
                add(f"{dfn_} falling out of the air", B.pick("aerial", 1, moment={"grounded"}))
            if a.get("protected") or a.get("stance") or a.get("reflected"):
                side[0] = "act" if act else "take"
                add("the guard", B.pick("guard", 1, moment={"reflect"} if a.get("reflected") else {"block"}))
            g_ = a.get("guard") or {}
            if g_.get("kind"):
                side[0] = "take" if take else "act"
                add("the guard", B.pick("guard", 1, moment={"catch" if g_["kind"] == "block" else "turn"},
                                        has=feats(dfn_)))
            for st_ in (a.get("status_applied") or []):
                nm = st_.get("status")
                if nm in self.STATUS_STORY and nm not in ("asleep", "frozen"):
                    if take:
                        side[0] = "take"
                        add(f"{st_.get('fighter')}, {nm.replace('_', ' ')}", B.pick("status_tell", 1, status={nm},
                                                                                   has=feats(st_.get("fighter"))))
                    if act:
                        side[0] = "act"
                        add(f"the opening it gives", B.pick("status_seen", 1, status={nm}))
            if act and self._opening_line(a):
                side[0] = "act"
                add(f"{att_}, going for the opening", B.pick("status_seen", 1, status={"opening"}))
            if take and a.get("type") == "instant" and self._anticipation_line(a):
                side[0] = "take"
                add(f"{dfn_}, seeing it come", B.pick("anticipate", 1, has=feats(dfn_), fighter=(dfn_ or "").lower()))
            if act and a.get("type") == "instant" and self._anticipation_line(a):
                side[0] = "act"
                add(f"{att_}, seeing her protect it", B.pick("anticipate_seen", 1, fighter=(att_ or "").lower()))
            if a.get("devastating"):
                side[0] = "take" if take else "act"
                add("why it is so severe", B.pick("devastating", 2, reason={a["devastating"].get("reason", "angle")},
                                                  fmt={"part": str(a["devastating"].get("part") or "the hurt").lower()}))
                hb_, pb_ = self._dev_bands(a)
                add("selling it", B.pick("devastating_sell", 1, health={hb_}, partlevel={pb_},
                                         fmt={"part": str(a["devastating"].get("part") or "the hurt").lower()}))
                if take:
                    add(f"{dfn_}, after it", B.pick("devastated_reaction", 1, has=feats(dfn_), state=state(dfn_),
                                                    fighter=(dfn_ or "").lower()))
                    add(f"{poss(dfn_)} thought", B.pick("devastated_thought", 1, state=state(dfn_),
                                                        fighter=(dfn_ or "").lower()))
                if act and a["devastating"].get("reason") != "ground":
                    add(f"{poss(att_)} thought", B.pick("devastating_thought", 1, fighter=(att_ or "").lower()))
            if act and (a.get("pummel") or {}).get("frenzy"):
                side[0] = "act"
                add(f"{poss(att_)} frenzy", B.pick("frenzy", 1))
            if a.get("missed_charge"):
                side[0] = "act" if act else "take"
                add(f"{poss(att_)} charge, missing", B.pick("crash", 1, has=feats(att_)))
            if a.get("feint") and (a["feint"].get("bit") or act):
                side[0] = "act" if act else "take"
                add("the feint", B.pick("feint", 1, moment={"bit" if a["feint"].get("bit") else "read"},
                                        fighter=(att_ if act else dfn_ or "").lower()))
            if a.get("juggle") or a.get("juggled_up"):
                side[0] = "take" if take else "act"
                add(f"{dfn_} in the air", B.pick("juggle", 1, moment={"caught" if a.get("juggle") else "up"}))
            if take and a.get("last_stand"):
                side[0] = "take"
                add(f"{poss(att_)} last stand", B.pick("last_stand", 1))
            if take and a.get("into_mouth"):
                side[0] = "take"
                add(f"{dfn_}, choking on the water", B.pick("sputter", 1, has=feats(dfn_)))
            if a.get("weather"):
                side[0] = "act" if act else "take"
                add("the weather coming in", B.pick("weather", 1, weather={a["weather"]["kind"]}))
        for e_ in pin_events or ():
            if take and ((e_.get("out_cause") or {}).get("cause") == "constriction" or e_.get("coil")):
                side[0] = "take"
                add(f"{e_.get('defender')}, in the coils", B.pick("constriction", 1, fade={
                    "fighting hard": "fighting", "weakening": "weakening", "fading": "fading",
                    "nearly gone": "nearly out"}.get(e_.get("fight_left"), "fighting")))
            if take and e_.get("struggle") == "escape" and e_.get("aftereffects"):
                side[0] = "take"
                add(f"{e_.get('defender')}, free of it", B.pick("escape_after", 1))
        for e_ in also or ():
            if take and e_.get("type") == "hold_ongoing" and e_.get("coil"):
                side[0] = "take"
                add(f"{e_.get('defender')}, in the coils", B.pick("constriction", 1))
        # --- after the match
        if acts and all(t == "aftermath" for t in types):
            win = next((a.get("winner") for a in acts if a.get("winner")), None)
            if act and win:
                side[0] = "act"
                add(f"{win}, afterwards", B.pick("aftermath_winner", 3, has=feats(win), state=state(win)))
                for p, lv, z in self._worst_parts(win, 1, "very painful"):
                    add(f"how {poss(win)} {p} feels now", B.pick("sensation", 1, fmt={"part": p}, level=lv, zone=z,
                                                                has=feats(win), part=set(re.findall(r"[a-z]+", p))))
            if take:
                side[0] = "take"
                fallen = [w for w in list(getattr(self, "out_names", None) or []) + list(self.damage_by) if w != win]
                for who in list(dict.fromkeys(fallen))[:1]:
                    add(f"{who}, lying there", B.pick("aftermath_fallen", 2, has=feats(who) or None))
            return self._blocks_plan(lines, key, False, False)
        # --- a pin: going on, closing, escaped, or held to the end
        pin_now = [a for a in acts if a.get("type") in ("pin_start", "pin_forced")]
        if pin_events or pin_now:
            e = pin_events[0] if pin_events else None
            a_ = (e or pin_now[0])["attacker"]
            d_ = (e or pin_now[0])["defender"]
            fade = {"fighting hard": "fighting", "weakening": "weakening", "fading": "fading",
                    "nearly gone": "nearly out"}.get((e or {}).get("fight_left"), "fighting")
            ends = bool(e and e.get("complete") and e.get("elimination"))
            if ends:
                fade = "nearly out"
            cause = ((e or {}).get("out_cause") or {}).get("cause") if ends else None
            escaped = bool(e and e.get("struggle") == "escape")
            face = {"up"} if "up" in str((getattr(self, "facing", None) or {}).get(d_, "")) else {"down"}
            # how old the PIN is (a grip that was on before it began does not age it)
            held = int((e or {}).get("beats") or 0)
            held_w = "early" if held <= 1 else "middle" if held <= 3 else "long"
            # in a beat where the PINNED fighter acts (she strikes from underneath, she breaks out), the first part is
            # hers and the second is the pinner's: the blocks follow whose part it is
            hers_first = actor == d_ and any(a.get("attacker") == d_ and a.get("hits") for a in acts) or (actor == d_ and escaped)

            def pinner_side():
                if pin_now and any(x.get("taken_down") for x in pin_now) and not any((x.get("takedown") or {}).get("how") for x in pin_now) \
                        and not any((x.get("takedown") or {}).get("told") for x in pin_now):
                    add(f"a way {a_} might take her down", B.pick("takedown", 1, has=feats(a_)))
                if not escaped:
                    add(f"{a_}, holding the pin", B.pick("pin_hold", 1, has=feats(a_), state=state(a_), facing=face,
                                                         fighter=a_.lower()))
                    add(f"what holding it costs {a_}", B.pick("pin_strain", 1, held=held_w, has=feats(a_)))
                # (on the beat she breaks out, too: what the pinner sees and thinks just before it goes)
                add(f"what {a_} can see of {d_}", B.pick("tell", 1, has=feats(d_), posture={"pinned"},
                                                           state=state(d_) if d_ in self.strengths else {"spent"}))
                mind(a_, "pinner", d_, held=held_w)
                for p, lv, z in self._worst_parts(a_, 1, "very painful"):
                    add(f"how {poss(a_)} own {p} takes the strain", B.pick(
                        "carry", 1, fmt={"part": p}, zone=z, has=feats(a_), role={"pinner"},
                        part=set(re.findall(r"[a-z]+", p))))

            def pinned_side():
                if not escaped:
                    add(f"{d_}, under the pin", B.pick("pin_under", 2, fade=fade, has=feats(d_), facing=face,
                                                       fighter=d_.lower()))
                pressed = sorted(list((e or {}).get("pressure_hits") or []) + [
                    x["hits"][0] for x in also or () if x.get("type") == "hold_ongoing" and x.get("defender") == d_
                    and x.get("hits")], key=lambda h: -h.get("damage_after", 0))
                if cause == "choking":        # the choke (blood or windpipe): the press that counts is the one on her neck
                    pressed = [h for h in pressed if body_region(h["part"]) == "neck"]
                elif cause == "constriction":  # the coils: what counts is where they are wound tightest
                    oc_part = (((e or {}).get("out_cause") or {}).get("part") or "")
                    pressed = [h for h in pressed if h["part"] == oc_part][:1] or pressed[:1]
                elif cause == "pain":
                    pressed = [h for h in pressed if body_region(h["part"]) != "neck"][:1]
                seen_parts = []
                for h in pressed:
                    if h["part"] in seen_parts or escaped:
                        continue
                    seen_parts.append(h["part"])
                    if len(seen_parts) > 2:
                        break
                    # a pin HURTS, and more as it goes on: what each press is like at this stage of it
                    add(f"what the press on her {h['part']} is like by now", B.pick(
                        "pin_pain", 1, fmt={"part": h["part"].lower()}, fade=fade, has=feats(d_)))
                mind(d_, "pinned", None, fade=fade, facing=face)

            if hers_first:
                if act:      # her part: what she does from underneath
                    side[0] = "act"
                    pinned_side()
                    if any(a.get("attacker") == d_ and a.get("hits") for a in acts):
                        strike_blocks(d_, a_)
                if take:     # the pinner's part: what lands on her, and the pin she is losing or keeping
                    side[0] = "take"
                    took = take_blocks(a_, d_)
                    if not escaped:
                        add(f"what holding it costs {a_}", B.pick("pin_strain", 1, held=held_w, has=feats(a_)))
                    elif not took:
                        mind(a_, "receiver", d_)
            else:
                if act:
                    side[0] = "act"
                    pinner_side()
                if take:
                    side[0] = "take"
                    pinned_side()
            who_ends = (a_ if hers_first else d_) if key in ("take", "all", "after") else (d_ if hers_first else a_)
            return self._blocks_plan(lines, key, first, last and not ends, d_ if hers_first else a_, a_ if hers_first else d_,
                                     self._memory_line([d_], pin=True) if take and not hers_first and not ends else None)
        # --- strikes, grabs, throws, dodges
        hits = {}
        for a in acts:
            for h in a.get("hits") or []:
                who = h.get("defender") or a.get("defender")
                if who and h.get("part") and who not in hits:
                    hits[who] = hits_on(who)
        doers = [x for x in dict.fromkeys(a.get("attacker") for a in acts if a.get("attacker")) if x in self.damage_by]
        targets = [x for x in dict.fromkeys(list(receivers) + [a.get("defender") for a in acts if a.get("defender")])
                   if x in self.damage_by]
        if act:
            side[0] = "act"
            for who in doers[:2]:
                strike_blocks(who, None)
                for other in [t for t in targets if t != who][:1]:
                    before = {p.lower(): b4 for _, p, b4, _, _ in hits.get(other, [])}
                    seen = self._worst_parts(other, 2, "hurting", before=before)
                    for p, lv, z in seen:
                        add(f"what {who} can see of {other} before she strikes (her {p})",
                            B.pick("tell", 1, fmt={"part": p}, need=("zone",), level=lv, zone=z, has=feats(other),
                                   posture=posture(other), part=set(re.findall(r"[a-z]+", p))))
                    if not seen or posture(other) != {"standing"}:
                        add(f"what {who} can see of {other} before she strikes",
                            B.pick("tell", 1, has=feats(other), state=state(other), posture=posture(other)))
                    mind(who, "attacker", other)
                for p, lv, z in self._worst_parts(who, 1, "very painful"):
                    add(f"how {poss(who)} own {p} shows as she moves", B.pick(
                        "carry", 1, fmt={"part": p}, zone=z, has=feats(who), role={"attacker"},
                        part=set(re.findall(r"[a-z]+", p))))
        if take:
            side[0] = "take"
            dodged = [a for a in acts if a.get("dodged") and not a.get("hits")]
            for who in targets[:2]:
                if take_blocks(who, (doers or [who])[0]):
                    if any(a.get("environment") or a.get("manhandle") in ("throw", "slam") for a in acts):
                        add(f"how {who} lands", B.pick("landing", 1, has=feats(who)))
                elif any(a.get("defender") == who for a in dodged):
                    add(f"how {who} gets out of the way", B.pick("dodge", 2, has=feats(who)))
        memory = self._memory_line([w for w in targets if hits.get(w)], hits) if take else None
        return self._blocks_plan(lines, key, first, last, actor or (doers or [None])[0],
                                 receivers[0] if len(receivers) == 1 else (targets[0] if len(targets) == 1 else None), memory)

    def _strength_rank(self, taken):
        """The size of a blow as a number (for sorting): the order of the impact words."""
        order = ["glancing", "solid", "heavy", "tremendous"]
        k = self._strength_key(taken)
        return order.index(k) if k in order else len(order)

    # which kind of step a block is, read off its label
    _SLOTS = [("see", r"can see of"), ("mind", r"thought$|^what \S+ feels$"),
              ("body", r"holding the pin|holding it costs|own .* (?:shows|takes the strain)"),
              ("feel", r"how the hurt|what the press|how it spreads|feels now"),
              ("react", r"reaction of that size|under the pin"), ("breath", r"breath$"),
              ("after", r"afterwards|lying there"), ("move", r".")]
    # the order the steps of a part come in changes from beat to beat ("see" always before "move": she looks, then goes)
    _ACT_ORDERS = [("after", "see", "mind", "move", "body"), ("after", "body", "see", "move", "mind"),
                   ("after", "mind", "see", "body", "move"), ("after", "see", "body", "mind", "move"),
                   ("after", "see", "move", "body", "mind")]
    _TAKE_ORDERS = [("after", "move", "feel", "react", "breath", "mind"), ("after", "move", "react", "feel", "mind", "breath"),
                    ("after", "feel", "move", "react", "mind", "breath"), ("after", "react", "breath", "move", "feel", "mind"),
                    ("after", "feel", "mind", "move", "react", "breath")]

    def _memory_line(self, who_list, hits=None, pin=False):
        """ONE memory to call back to: a part hurt again this beat that an EARLIER beat's blow had already hurt (from
        the engine's injury log as it stood before this beat). Each part is offered once in a long while."""
        if not self.rules.get("narration", {}).get("callback_memory", True):
            return None
        before = getattr(self, "_injury_prev", None) or {}
        told = self.__dict__.setdefault("_memory_told", {})
        turn = self._blocks().turn
        if any(turn == t for t in told.values()):
            return None          # one memory a beat
        for who in who_list:
            parts = [p for _, p, b4, _, _ in sorted((hits or {}).get(who, []), reverse=True) if b4 >= 30]
            if pin:
                parts = [p for _, p, lv, _ in [(0,) + x for x in self._worst_parts(who, 2, "very painful")]]
            for part in parts:
                key = next((k for k in before if k.lower() == f"{who}|{part}".lower()), None)
                causes = [c for c in before.get(key, []) if c and "(held)" not in c and "pressed" not in c] if key else []
                if not causes or turn - told.get(key, -99) < 10:
                    continue
                told[key] = turn
                return (f"one memory, touched once and in passing (a clause, not a retelling): {poss(who)} "
                        f"{part.lower()} was already hurt before this beat, by {causes[0]}"
                        + (f" and then {causes[-1]}" if len(causes) > 1 and causes[-1] != causes[0] else "")
                        + ". She can know it by the way this new pain finds the old one")
        return None

    def _arena_detail(self):
        """One detail of the place that the story has not used lately (scenes.json: details, else ambience)."""
        if not self.rules.get("narration", {}).get("arena_detail", True):
            return None
        cfg = getattr(self, "scene_cfg", None) or {}
        pool = [str(x).strip() for x in (cfg.get("details") or []) if str(x).strip()] or [
            x.strip() for x in str(cfg.get("ambience") or "").split(",") if x.strip()]
        if not pool:
            return None
        used = self.__dict__.setdefault("_arena_used", {})
        turn = self._blocks().turn
        recent = (getattr(self, "_story_tail", "") or "")[-2500:].lower()

        def stale(d):        # is this detail's own word in the last few beats of the story already?
            words = [w for w in re.findall(r"[a-z]{5,}", d.lower()) if w not in _PLAIN_WORDS]
            return any(w in recent for w in words)
        fresh = [d for d in pool if turn - used.get(d, -99) >= max(3, len(pool) - 2)]
        fresh = [d for d in fresh if not stale(d)] or fresh
        if not fresh:
            return None
        pick = min(fresh, key=lambda d: (used.get(d, -99), self._blocks().rng.random()))
        used[pick] = turn
        return pick

    def _blocks_plan(self, lines, key, first, last, lead=None, other=None, memory=None):
        """The blocks for one part, laid out as numbered steps: an image to open on, the blocks in an order that
        changes from beat to beat, a glimpse of the place, a memory, an image to end on."""
        cfg = (self.rules.get("narration", {}) or {}).get("blocks", {}) or {}
        cap = int(cfg.get("per_part", 10))
        B = self._blocks()
        self._open_end = False
        lines = [x for x in lines if x][:cap]
        worn = set().union(*(self.recent_reactions or [set()])) if getattr(self, "recent_reactions", None) else set()
        steps = []
        for sd, orders in (("act", self._ACT_ORDERS), ("take", self._TAKE_ORDERS)):
            mine = [x for x in lines if x[0] == sd]
            if not mine:
                continue
            order = orders[B.rng.randrange(len(orders))]
            steps += [t for slot in order for s_, sl, t in mine if sl == slot]
        if not cfg.get("plan", True):
            return self._blocks_note([f"  - {t}" for t in steps])
        if not steps and not (first or last):
            return ""
        take_only = key == "take"
        if first and not take_only and cfg.get("open_and_end", True):
            for p in B.pick("open_on", 1, posture=self._blk_posture(lead) if lead else {"standing"}):
                if not (reactions_used(p) & worn):
                    steps.insert(0, f"OPEN this part on{f' (from {poss(lead)} side)' if lead else ''}: {p}")
        if first:
            self._arena_part = B.rng.choice(("first", "last"))
        place = None
        if (first and (last or getattr(self, "_arena_part", "first") == "first")) or (
                last and not first and getattr(self, "_arena_part", "first") == "last"):
            place = self._arena_detail()
        if place:
            at = B.rng.randrange(1, len(steps) + 1) if len(steps) > 1 else len(steps)
            steps.insert(at, f"the place, glimpsed in passing (one clause; background only: it touches no one and "
                             f"changes nothing): {place}")
        if memory:
            steps.insert(max(1, len(steps) - 1) if steps else 0, memory)
        if last and cfg.get("open_and_end", True) and steps:
            who = other if key in ("take", "all", "after") else lead
            for p in B.pick("end_on", 1, posture=self._blk_posture(who, end=True) if who else {"standing"}):
                if "does not finish" in p:
                    self._open_end = True     # an ending left open was asked for: it is not trimmed as a cut-off
                if not (reactions_used(p) & worn):
                    steps.append(f"END this part on{f' (from {poss(who)} side)' if who else ''}: {p}")
        if not steps:
            return ""
        return ("\n\nBUILDING BLOCKS for this part, laid out as a plan. The program picked them because they fit the "
                "fight as it stands (none has been offered lately), and their order is new each beat. The events listed "
                "above are ALL told, in their own order; these steps are the colour between and around them. Follow "
                "the order where the events allow, put each in your own words, and skip one that does not fit. They are "
                "never new events: no extra hit, fall, wound, grip or escape comes from them, and nobody else is "
                "touched.\n" + "\n".join(f" {i}. {t}" for i, t in enumerate(steps, start=1)))

    def _blocks_note(self, lines):
        cap = int(((self.rules.get("narration", {}) or {}).get("blocks", {}) or {}).get("per_part", 10))
        lines = [x for x in lines if x][:cap]
        if not lines:
            return ""
        return ("\n\nBUILDING BLOCKS for this part: ideas the program picked because they fit the fight as it stands "
                "(none has been offered lately). Work in the ones that fit, in your own words; leave the rest. They are "
                "colour for the events listed above, never new events: no extra hit, fall, wound, grip or escape comes "
                "from them, and nobody else is touched.\n" + "\n".join(lines))

    def _sample_tags(self, key, acts, pin_events, also=()):
        """What kind of passage this part of the beat is, as tags a sectioned style sample can answer to, best first
        (see style_sample_scenes.txt): the narrator is shown how a moment of this kind is told."""
        if key == "dwell":
            return ["dwell", "strike take hard", "strike take"]
        if key == "watch":
            return ["watch", "pin hold", "strike act"]
        take = key == "take"
        both = key in ("all", "after", "setup")
        tags = []

        def add(act_tag, take_tag=None):
            for t in ([act_tag, take_tag] if both else [take_tag if take else act_tag]):
                if t and t not in tags:
                    tags.append(t)
        types = [a.get("type") for a in acts]
        if acts and all(t == "aftermath" for t in types):
            add("aftermath", "aftermath take")
            self._sample_rounds = {}
            return tags
        if any(e.get("complete") and e.get("elimination") for e in pin_events):
            add("pin hold", "faint")
        elif any(e.get("struggle") == "escape" for e in pin_events):
            add("pin hold", "escape")
        elif pin_events:
            add("pin hold", "pin struggle")
        elif any(t in ("pin_start", "pin_forced") for t in types):
            add("pin start", "pin start take")
        if any((e.get("out_cause") or {}).get("cause") == "constriction" for e in pin_events) \
                or any(e.get("type") == "hold_ongoing" and e.get("coil") for e in also or ()):
            add("coil", "coil take")
        if any(e.get("struggle") == "escape" and e.get("aftereffects") for e in pin_events):
            add(None, "escape aftermath")
        if any(a.get("devastating") for a in acts):
            add("devastating", "devastating take")
        if any(a.get("clash") for a in acts):
            add("clash", "clash take")
        if any(a.get("dive") or a.get("carried") or a.get("grounded") or a.get("type") == "take_off" for a in acts):
            add("dive", "dive take")
        if any(a.get("into_mouth") for a in acts):
            add(None, "sputter take")
        if any(a.get("manhandle") in ("throw", "slam") for a in acts):
            add("throw", "throw take")
        if (take or both) and getattr(self, "_breaking", None):
            tags.append("breaking point")
        if any(t in ("grapple_start", "hold_start") for t in types) or any(a.get("point_blank") for a in acts) \
                or any(e.get("type") == "hold_ongoing" for e in also or ()):
            add("pummel" if any(a.get("pummel") for a in acts) else "grab", "grab take")
        if any(a.get("sustain") for a in acts):
            add("sustain act", "sustain take")
        hits = [a for a in acts if a.get("type") == "instant" and not a.get("environment")]
        if hits and all(a.get("dodged") and not a.get("hits") for a in hits):
            add("strike act", "dodge")
        if (take or both) and any(e.get("type") == "get_up" for e in also or ()):
            tags.append("getup")
        if any(a.get("chain") for a in acts):
            add("chain", None)
        hard = any(self._pain(h.get("damage_after", 0))["label"] in ("excruciating", "devastated", "numb with shock")
                   or self._strength_key(h.get("damage_taken", 0)) == "tremendous"
                   for a in acts for h in (a.get("hits") or []))
        if hard:
            add(None, "strike take hard")
        add("strike act", "strike take")
        tags = [t for t in dict.fromkeys(tags) if t]
        counts = self.__dict__.setdefault("_sample_counts", {})
        self._sample_rounds = {t: counts.get(t, 0) for t in tags}     # which of several passages for a tag is due
        for t in tags:
            counts[t] = counts.get(t, 0) + 1
        return tags

    def _drop_sample_copies(self, text):
        """Sentences lifted word for word from the style sample (five words or more) are cut: the sample shows a
        manner of telling, and its lines belong to another fight. narration.sample_copy_check turns it off."""
        if not text or not self.rules.get("narration", {}).get("sample_copy_check", True):
            return text

        def key(x):
            return WHITESPACE.sub(" ", re.sub(r"[^\w\s]", "", x.lower())).strip()
        name = self.rules.get("narration", {}).get("style_sample_file", "style_sample.txt")
        if getattr(self, "_sample_keys_for", None) != name:
            src = userprompt.sample_text(self.rules)
            self._sample_keys = {k for para in src.split("\n") for x in _SENT.split(para)
                                 for k in [key(x)] if len(k.split()) >= 5}
            self._sample_keys_for = name
        if not self._sample_keys:
            return text
        paras, cut = [], False
        for para in text.split("\n"):
            kept = [x for x in _SENT.split(para) if not (key(x) in self._sample_keys)]
            cut = cut or len(kept) != len([x for x in _SENT.split(para)])
            paras.append(" ".join(kept).strip())
        if not cut:
            return text
        out = re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip()
        return _drop_orphans(text, out)

    def _drop_seen(self, text):
        """Short sentences (4-10 words) this FIGHT has already used word for word are cut, however long ago: "The
        cave held its breath." / "Her ears pinned flat against her skull." The repeat filter above only looks back a
        few beats. Then this text's own short sentences are remembered. narration.repeat_memory turns it off."""
        if not text or not self.rules.get("narration", {}).get("repeat_memory", True):
            return text

        def key(x):
            return WHITESPACE.sub(" ", re.sub(r"[^\w\s]", "", x.lower())).strip()
        new, paras = set(), []
        for para in text.split("\n"):
            kept = []
            for x in _SENT.split(para):
                k = key(x)
                short = 4 <= len(k.split()) <= 10
                if short and k in self.fight_seen:
                    continue
                if short:
                    new.add(k)
                kept.append(x)
            paras.append(" ".join(kept).strip())
        self.fight_seen |= new
        out = re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip()
        return _drop_orphans(text, out) if out != text.strip() else text

    def _system(self, sample_chars=None):
        # Static text first and the per-beat lines last, so the start of the prompt stays identical from call to
        # call and Ollama can reuse its cached work on it (faster, nothing left out).
        no_sac = "sac" in (getattr(self, "foreign_words", None) or [])
        parts = [CRAFT_RULES.replace("(a flotation sac,\n  a tail, a coil)", "(a tail, a fin,\n  a horn)") if no_sac else CRAFT_RULES]
        if self.rules.get("narration", {}).get("numb_tier", True) is False:
            # /numb off: the craft rules must not teach numbness two lines above the rule that forbids it
            parts[0] = (parts[0].replace("then pounding and sick, then past pain into numb, wrong quiet.",
                                         "then pounding and sick, then a pain so large it crowds out everything else.")
                        .replace("(sharp, hot, deep, numb, grinding)", "(sharp, hot, deep, sick, grinding)")
                        .replace("excruciating, devastated, numb with shock)", "excruciating, devastated)"))
        extra = []
        if self._no_clock and not getattr(self, "_pin_beat", False):
            extra.append(NO_PIN_RULE)
        elif self._no_clock and getattr(self, "_fade_pin", False):
            extra.append(NO_CLOCK_RULE)
        mode = str(self.rules.get("narration", {}).get("swearing", "rare")).lower()
        if mode == "never":
            extra.append("- No swearing or crude language in narration, thoughts, or dialogue.")
        elif mode == "rare":
            extra.append("- Swearing is RARE: at most an occasional single curse in a thought or spoken line at a moment of "
                         "real pain or fury, never in the narration itself and never crude. Most beats have none.")
        per_beat, gap, thoughts, talk_on = self._talk_limits()
        if talk_on:
            extra.append(f"- THE FIGHTERS ARE MOSTLY SILENT. Most beats have no spoken lines at all; at most {per_beat} short "
                         f"spoken line in a beat, and not in back-to-back beats. Thoughts in italics are few (up to "
                         f"{thoughts} short ones per part) and only when they add something the body can't show. Carry "
                         f"the rest through action, breath, and expression.")
        absent = [w for w in (getattr(self, "absent_words", None) or []) if w]
        if absent:
            extra.append(f"- NOT IN THIS FIGHT: {', '.join(absent)}. She is not here and not part of this story: "
                         f"never mention her, by name or as her species, even if an example or the style sample does.")
        for name, body in (getattr(self, "damage_by", {}) or {}).items():
            if any("arm" in p for p in body):
                extra.append(f"- {name} stands and walks on her two FEET. Her paws are her HANDS, at the ends of her "
                             f"arms: she never stands on them or puts her weight on them. A hurt paw, fin, or arm "
                             f"changes how she grips, strikes, and guards, never how she stands or walks.")
        if self.rules.get("narration", {}).get("numb_tier", True) is False:
            extra.append("- Pain never goes numb: even the worst-hurt parts stay sharply, terribly painful, never "
                         "numb or past feeling.")
        # a plain sample is one passage (its first style_sample_chars characters); a sample written in sections gives
        # the passage that shows the KIND of part about to be written (a pin from the pinner's side, a dodge, ...)
        passages, left = [], sample_chars
        for sample in userprompt.style_passages(self.rules, getattr(self, "_sample_want", None),
                                                rounds=getattr(self, "_sample_rounds", None),
                                                skip=[w for w in (getattr(self, "absent_words", None) or []) if w]):
            if no_sac and sample:
                sample = sample_without_sac(sample)   # nobody here has a flotation sac: the sample doesn't show one either
            if self.rules.get("pin", {}).get("fade", {}).get("enabled", True):
                sample = re.sub(r"(?m)^\s*Second \d+:\s*", "", sample)   # no pin clock: don't show one in the sample
            if sample and left is not None:
                if passages and len(sample) > left:
                    continue      # (short of room: the passage that fits best stays, the extra one goes)
                if len(sample) > left:
                    cut = sample.rfind("\n", 0, left)
                    sample = sample[:cut if cut > left // 2 else left]
                left -= len(sample)
            if sample:
                passages.append(sample)
        if passages:
            sectioned = bool(userprompt.sample_sections(userprompt._read(
                self.rules.get("narration", {}).get("style_sample_file", "style_sample.txt"))))
            parts.append("STYLE SAMPLE. Match this voice: its rhythm, its concrete physical detail, how it moves "
                         "between the two fighters' bodies and minds. Do NOT match its level of gore or injury "
                         "detail; follow the author's TONE instructions for that. Never copy its characters, "
                         "names, events, or sentences."
                         + (" It is from a DIFFERENT fight and shows how a moment of this kind is told: nothing in it "
                            "happened in this fight, so take its manner and none of its events, injuries or lines."
                            if sectioned else "")
                         + "\n<<<\n" + "\n>>>\nAnother passage in the same voice:\n<<<\n".join(passages) + "\n>>>")
        story = _story_sections(userprompt.story_prompt(self.rules), getattr(self, "_pin_beat", True))
        if story:
            parts.append("THE AUTHOR'S INSTRUCTIONS (follow these too; the hard rules above still win):\n" + story)
        if extra:
            parts.append("MORE HARD RULES FOR THIS BEAT:\n" + "\n".join(extra))
        return "\n\n".join(parts)

    def _stray_electric(self, sent):
        """Electricity in a sentence of a beat whose moves have none. Not stray: sparks still on a fighter who is
        PARALYSED (the program's own words for that state), and an earlier Electric move that really landed,
        remembered ("the place the lightning had left sore")."""
        if not ELECTRIC.search(sent):
            return False
        if getattr(self, "_sparks_ok", False):
            return False
        hit_before = any(re.search(r"thunder|bolt|shock|spark|volt|electr|zap|discharge|charge beam|wild charge", str(mv), re.I)
                         for mv in (getattr(self, "move_victims", None) or {}))
        if hit_before and re.search(r"\b(?:had|earlier|before|still|left|last|remember\w*|again|since|after)\b", sent, re.I):
            return False
        return True

    def _bad_bones(self, text):
        """Severe bone damage in sentences that aren't about a part allowed to break."""
        bad = []
        for sent in re.split(r"(?<=[.!?…])\s+", text):
            m = BONE_SEVERE.search(sent)
            if m and not any(_mentions_exact(sent.lower(), p) for p in self.breakable):
                bad.append(m.group(0).lower())
        return bad

    def _review(self, text, coverage, prior=""):
        """Problems with a draft that the program can detect: gore, the pin clock, skipped hits or struggles."""
        n = self.rules.get("narration", {})
        issues = []
        gore = gore_pattern(self.rules)
        bones = self._bad_bones(text) if gore is GORE else []
        if bones:
            ok = ", ".join(p.title() for p in sorted(self.breakable)) or "none right now"
            issues.append("it broke bones that can't break yet (" + ", ".join(bones[:5]) + "). Bones may crack or bruise, "
                          "but only parts listed as able to break may be broken, fractured, or shattered: " + ok)
        if gore is not None:
            found = sorted({m.group(0).lower() for m in gore.finditer(text)})
            if found:
                mild = str(n.get("gore_level", "mild")).lower() != "none"
                issues.append("it broke the TONE rule with: " + ", ".join(found[:10]) + ". "
                              + ("A little blood, small cuts and bruises are fine, but nothing extreme: no torn or "
                                 "shredded flesh, no exposed or breaking bone, no pooling blood, nothing severed, "
                                 if mild else "Show injury only as impact, bruising, swelling, strain, trembling, and "
                                 "cries; no blood, cuts, or torn flesh, ")
                              + "no talk of dying or not breathing")
        window = getattr(self, "_time_window", None)
        if window:
            bad = _time_overrun(text, *window)
            if bad:
                issues.append(f"it got the time wrong (\"{bad[1]}\"): this beat covers ONLY seconds {window[0]} to "
                              f"{window[1]}, ending at second {window[1]}, and the pin is still going after that")
        window = getattr(self, "_time_window", None)
        if self._no_clock:
            found = _COUNTDOWN.search(text) or _bare_count(text, getattr(self, "_pin_beat", False)) or _TIME_MARK.search(text) or (
                _FADE_CLOCK.search(text) if getattr(self, "_fade_pin", False) and getattr(self, "_pin_beat", False) else None)
            if found:
                issues.append((f"it counted the pin in seconds (\"{found.group(0).strip()}\"), but a pin has NO clock: "
                               f"nobody knows how long she can last. No seconds, no counting, no time left"
                               if getattr(self, "_fade_pin", False) and getattr(self, "_pin_beat", False) else
                               f"it counted a pin clock (\"{found.group(0).strip()}\") but NO pin is running in this beat: "
                               f"no countdowns, no seconds left"))
        elif window and _REMAINING.search(text):
            issues.append(f"it counted the time REMAINING (\"{_REMAINING.search(text).group(0)}\"). Nobody watching the pin clock in the story "
                          f"knows how long is left: no 'N more seconds', 'just ten more', or 'N seconds left'")
        elif window and _out_of_order(text) is not None and not _counts_down(text):
            issues.append(f"it marked the seconds out of order (went back to {_out_of_order(text)}). The pin clock only "
                          f"moves forward: mark the seconds in rising order, or don't mark them")
        elif window and _counts_down(text):
            issues.append(f"it counted DOWN like a referee's count (\"{', '.join(str(v) for v in _counts(text)[:5])}\"). "
                          f"The pin clock counts UP: this beat runs from second {window[0]} to second {window[1]} of the "
                          f"pin. Mark the seconds as they pass, in rising order, or don't mark them; never count down")
        wrong = list(dict.fromkeys(p or "a limb" for p, _ in self._disabled_lines(text)))
        if wrong:
            issues.append("it showed " + ", ".join(w.title() for w in wrong[:5]) + " as useless, limp, or not working, "
                          "but those parts are only sore or hurting: they hurt and get favored, but still work. Only "
                          "excruciating or devastated parts stop working")
        hand = self._hand_weight_lines(text)
        if hand:
            issues.append(f"it had {hand[0][0]} putting her weight on a paw or arm (\"{hand[0][1]}\"), but she stands on "
                          f"her two FEET: her paws are her HANDS. A hurt paw or arm changes how she grips, strikes, and "
                          f"guards, never how she stands")
        weapon = self._weapon_lines(text)
        bites = [w for w in weapon if w[0] == "bite"]
        tails = [w for w in weapon if w[0] in ("tail", "horn")]
        if bites:
            issues.append(f"it added a bite that isn't in this beat (\"{bites[0][1]}\"): no move here uses teeth, so "
                          f"nobody bites, and no jaws close on anyone. Only the listed attacks happen, each delivered the "
                          f"way its move says")
        if tails:
            issues.append(f"it landed the strike with the wrong weapon (\"{tails[0][1]}\"): this move is delivered with "
                          f"{' or '.join(sorted(self._weapons_ok))}, not the {tails[0][0]} (see 'Delivered with' under the "
                          f"move)")
        big = self._overblown_lines(text)
        if big:
            worst = sorted((getattr(self, "damage_by", {}) or {}).get(big[0][0], {}).items(), key=lambda x: -x[1])[:3]
            issues.append(f"it made a serious injury that isn't there: {poss(big[0][0])} {big[0][1].title()} (\"{big[0][2]}\") "
                          f"is only MINOR this beat, light pressure and a dull ache at most. Nothing gives, cracks, or "
                          f"twists there. Her real pain is in: {', '.join(p.title() for p, _ in worst)}")
        loose = self._pin_broken_lines(text)
        if loose:
            pinners, pinned, kind = self._pin_holds
            issues.append(f"it broke the pin (\"{loose[0][1]}\"), but THE PIN HOLDS this beat: {pinned} "
                          + ("tries and FAILS" if kind == "fail" else "breaks loose only for a moment" if kind == "partial"
                             else "does not get out")
                          + f", and when the beat ends she is still on the ground under {' and '.join(pinners)}, who is "
                            f"not thrown off and does not back away. Nothing comes after the struggle: no escape, no "
                            f"chase, no new attack")
        tried = self._getup_lines_invented(text)
        if tried:
            issues.append(f"it showed {tried[0][0]} trying to get up (\"{tried[0][1]}\"), but she has only just gone down: "
                          f"she makes NO attempt to rise this beat, not even a failed one. She lies where she fell")
        if self.rules.get("narration", {}).get("numb_tier", True) is False:
            m = NUMB.search(text)
            if m:
                issues.append(f"it let pain go numb (\"{m.group(0)}\"). Pain never goes numb in this story: the worst-hurt "
                              f"parts stay sharply, terribly painful")
        if _BARE_MORE.search(text):
            issues.append(f"it counted the time REMAINING (\"{_BARE_MORE.search(text).group(0).strip()}\"). Nobody in the "
                          f"story knows how long is left on a pin: no 'forty more', no countdown")
        fine = self._healthy_lines(text)
        if fine:
            issues.append(f"it called {poss(fine[0][0])} {fine[0][1].title()} good or strong (\"{fine[0][2]}\"), but that part "
                          f"is badly hurt (see CURRENT CONDITION): it is the one she guards. Check LEFT and RIGHT")
        window = getattr(self, "_time_window", None)
        late = _clock_at_overrun(text, *window) if window else []
        if late and not any("got the time wrong" in i for i in issues):
            issues.append(f"it got the time wrong (\"{late[0]}\"): this beat covers ONLY seconds {window[0]} to "
                          f"{window[1]} of the pin. Everything in it, the escape included, happens inside those seconds")
        foreign = self._foreign_mentions(text)
        if foreign:
            issues.append(f"it gave a fighter {foreign[0][0]}, which nobody in this fight has. Anatomy comes only from "
                          f"each fighter's APPEARANCE: fur, paws, fins, tails as listed there")
        if n.get("accuracy_check", True) and self.strengths:
            strong, fallers = [], []
            for sent, whos, named in self._said(text):
                if self._down_is_hers(whos, named):
                    continue  # the sentence names someone who really is on the ground: the fall is hers
                if (COLLAPSE if named else COLLAPSE_STRONG).search(sent):
                    strong += [w for w in whos if self.strengths.get(w, 0) >= 40 and w not in strong
                               and w not in self.on_ground]
                if self._fall_meant(sent):
                    fallers += [w for w in whos if w not in self.on_ground and w not in fallers
                                and w not in getattr(self, "_landed", set())
                                and w not in getattr(self, "_slammed", set())]
            if fallers:
                issues.append("it had " + " and ".join(fallers) + " fall or go down, but nothing knocked "
                              + ("them" if len(fallers) > 1 else "her") + " down this beat. Only the listed actions "
                              "happen: she can stagger, but stays on her feet")
            if strong:
                issues.append("it had " + " and ".join(strong) + " collapse, go limp, or be unable to get up, but "
                              + ("they are" if len(strong) > 1 else "she is") + " still strong overall (see OVERALL "
                              "under CURRENT CONDITION): she cries out and favors the hurt part, but stays up and keeps "
                              "fighting")
        kept_feet = getattr(self, "_slammed", set())
        if kept_feet:
            slid = SLID_DOWN.search(text)
            if slid:
                issues.append(f"it had {' and '.join(sorted(kept_feet))} slide or crumple to the ground (\"{slid.group(0)}\"), "
                              f"but she KEEPS HER FEET this beat: she staggers off the surface she was driven into, hurt "
                              f"but standing (see POSTURE THIS BEAT)")
        nothere = self._absent_mentions(text)
        if nothere:
            issues.append(f"it brought in {nothere[0][0]}, who is NOT in this fight: she isn't here, she isn't "
                          f"watching, and nothing of hers happened. Only the fighters listed under FIGHTERS exist in "
                          f"this story")
        gone = self._out_mentions(text)
        if gone:
            who = gone[0][0]
            issues.append(f"it brought up {who}, who is out of this fight and never landed a blow on anyone: no attack, "
                          f"move, or injury of hers exists to remember. Leave her out completely; only the attacks "
                          f"listed under FIGHT SO FAR ever happened")
        swing = EXTRA_SWING.search(text) if getattr(self, "_one_strike", None) else None
        if swing:
            issues.append(f"it turned ONE strike into several (\"{swing.group(0)}\"): {self._one_strike} attacks once "
                          f"this beat. That single blow lands on the first part and its force carries into the parts "
                          f"next to it in the same motion: no second swing, no \"struck again\"")
        wrong_posture = self._posture_problems(text)
        lying = [x for x in wrong_posture if x[2] == "lying"]
        held = [x for x in wrong_posture if x[2] == "pinned"]
        if lying:
            who = " and ".join(sorted({x[0] for x in lying if x[0]})) or "a fighter"
            issues.append(f"it showed {who} lying on the ground or unable to stand (\"{lying[0][1]}\"), but she is ON HER "
                          f"FEET this whole beat (see POSTURE THIS BEAT). She may stagger, hunch, or drop to a crouch for "
                          f"an instant, but she is upright: never lying, never rolling over, never getting up")
        if held:
            issues.append(f"it wrote someone held down or stood over (\"{held[0][1]}\"), but NOBODY is pinned and nobody "
                          f"is on the ground this beat: both fighters are on their feet, apart, facing each other")
        if getattr(self, "_no_electric", False):
            m = next((ELECTRIC.search(x) for para in text.split("\n") for x in _SENT.split(para.strip())
                      if x and self._stray_electric(x)), None)
            if m:
                issues.append(f"it added electricity (\"{m.group(0)}\") to a move that isn't Electric-type. Show each move "
                              f"as its own type only")
        rep = getattr(self, "_must_reposition", None)
        if rep and coverage:
            full = (prior or "") + "\n" + text
            seen = (LIFTING.search(full) if rep["how"] in ("pick up", "sit her up", "stand her up")
                    else ROLLING.search(full))
            if not seen:
                issues.append(f"it never showed {rep['attacker']} " + ("hauling " + rep["defender"] + " up off the ground"
                              if rep["how"] == "pick up" else "hauling " + rep["defender"] + " up to sitting"
                              if rep["how"] == "sit her up" else "dragging " + rep["defender"] + " up onto her feet"
                              if rep["how"] == "stand her up" else "rolling " + rep["defender"] + " over")
                              + ": show it happen before the attack")
        man = getattr(self, "_must_manhandle", None)
        if man and coverage and not MANHANDLED[man["manhandle"]].search((prior or "") + "\n" + text):
            issues.append(f"it never showed {man['attacker']} "
                          + {"throw": "throwing", "slam": "lifting and slamming", "drag": "dragging"}[man["manhandle"]]
                          + f" {man['defender']}: that is what happens this beat. Show the grab and the "
                          + {"throw": "throw", "slam": "slam", "drag": "drag across the ground"}[man["manhandle"]])
        tb = getattr(self, "_must_tumble", None)
        if tb and coverage and not TUMBLED.search((prior or "") + "\n" + text):
            issues.append(f"it left out the tumble: {tb['defender']} doesn't stop where she lands this beat. She goes "
                          f"on across {tb['tumble']['across']}, rolling and skidding"
                          + (f", and fetches up against {tb['tumble']['into']}" if tb['tumble'].get('into') else "")
                          + ". Show that stretch of the fall")
        if getattr(self, "_faint", None) and coverage and not self._shown_out((prior or "") + "\n" + text):
            issues.append(f"it never showed {self._faint[0]} fainting: this is the beat she goes under, "
                          f"and she passes out under the pin. End with her last seconds, her body going limp and "
                          f"still, her eyes closing, and {self._faint[1]} easing off")
        sev = getattr(self, "_must_event", None)
        if sev and coverage:
            full = ((prior or "") + "\n" + text).lower()
            words = [str(w).lower() for w in sev.get("words") or []]
            if words and not any(w in full for w in words):
                issues.append(f"it never showed what {sev.get('place') or 'the arena'} did by itself this beat ({sev.get('name')}): "
                              f"{sev.get('text')}. Show it as the last thing that happens, and what it does to "
                              f"{' and '.join(sev.get('fighters') or [])}")
        up = getattr(self, "_must_rise", None)
        if up and coverage and not self._shown_standing((prior or "") + "\n" + text, who=up):
            issues.append(f"it never showed {up} coming up on her feet: this beat she is thrown, ROLLS THROUGH the "
                          f"landing and ends standing. Show the impact, the roll, and her back on her feet at the end")
        if getattr(self, "_getup_tries", None) and coverage and not self._shown_standing((prior or "") + "\n" + text):
            issues.append("it never showed her finally getting up: this beat she makes it onto her feet (after the "
                          "listed tries), so end with her standing, however shakily")
        seen_kinds = set()
        for sent, why in self._log_slips(text) + [x[:2] for x in self._count_slips(text)]:
            kind = _slip_label(why) or why[:30]
            if kind not in seen_kinds:
                seen_kinds.add(kind)
                issues.append(f"in \"{sent[:90]}\": {why}")
        tries = getattr(self, "_getup_tries", None)
        if tries and tries >= 2 and coverage and getattr(self, "_getup_who", None):
            got = self._failed_tries((prior or "") + "\n" + text, self._getup_who)
            if got < tries - 1:
                issues.append(f"it never showed the failed tries at getting up: {self._getup_who} makes it on try {tries}, so "
                              f"{'one attempt has' if tries == 2 else 'two attempts have'} to FAIL first, each in its own "
                              f"short paragraph (she gets partway up and goes back down), and only then does she stand. She "
                              f"must not simply get to her feet in one go")
        if getattr(self, "_getup_tries", None) == 1:
            m = GETUP_RETRY.search(text)
            if m:
                issues.append(f"it showed extra failed tries at getting up (\"{m.group(0)}\"), but she gets up on the "
                              f"FIRST try: one attempt, and she ends on her feet")
        broken = degeneration(text, (getattr(self, "_story_tail", "") or "") + "\n" + (prior or ""))
        if broken:
            issues.append("the prose broke down: " + "; ".join(broken) + ". Write normal, complete sentences with "
                          "'the' and 'a', each ending in a period; vary the wording and never copy earlier lines")
        wrong_way = self._facing_problems(text)
        if wrong_way:
            who, fc, bit = wrong_way[0]
            issues.append(f"it put {who} the wrong way round (\"{bit}\"): she is {fc} this beat (see CURRENT "
                          f"CONDITION). Keep her lying that way unless the beat says she's rolled over")
        sat = self._sitting_problems(text) if not wrong_way else []
        if sat:
            who, fc, bit = sat[0]
            issues.append(f"it put {who} the wrong way round (\"{bit}\"): she ends this beat "
                          + ("SITTING UP on the ground, not lying flat" if fc == "sitting up" else
                             f"lying {fc}, not sitting up") + " (see CURRENT CONDITION and the notes for this beat)")
        unhurt = self._unhurt_lines(text)
        if unhurt:
            names = sorted({w for w, _ in unhurt})
            issues.append("it showed " + " and ".join(names) + " with a wound that doesn't exist (\"" + unhurt[0][1]
                          + "\"). A dodged attack misses completely, and a part with no damage has no cuts, blood, or "
                          "marks from earlier either; only the listed hits land, and only hurt parts carry old injuries")
        talk = self._talk_problem(text, prior)
        if talk:
            issues.append(talk)
        swear = self._swear_problem((prior or "") + "\n" + text)  # one curse per beat across its parts
        if swear and SWEAR.search(text):
            issues.append(swear)
        leaks = sorted({m.group(0).lower() for m in GAME_TERMS.finditer(text)})
        if leaks:
            issues.append("it leaked game terms into the story (" + ", ".join(leaks[:6]) + "). No numbers, no "
                          "percentages, no colors as pain levels: describe how it actually feels")
        if n.get("variety_check", True):
            overused = [p.lower() for p in n.get("overused_phrases", [])]
            low_t = text.lower()
            recent = " || ".join(_norm_line(x) for x in self.recent_lines)
            bad = []
            said_now = " || ".join(_norm_line(x) for x in said_lines(text))
            for ph in overused:
                hits = len(re.findall(r"\b" + re.escape(ph) + r"\b", said_now))
                if hits > 1 or (hits and re.search(r"\b" + re.escape(ph) + r"\b", recent)):
                    bad.append(ph)
            seen_lines = {_norm_line(x) for x in self.recent_lines}
            repeats = [x for x in said_lines(text) if len(_norm_line(x)) > 6 and _norm_line(x) in seen_lines]
            if bad or repeats:
                issues.append("it repeated stock lines (" + ", ".join(f"\"{x}\"" for x in (bad + repeats)[:6])
                              + "). Give every thought and spoken line new words that fit this exact moment and the "
                                "fighter's VOICE; no catchphrases")
        if coverage and n.get("accuracy_check", True):
            low = (prior + "\n" + text).lower()
            missing = [p for p in dict.fromkeys(self._must_parts) if not _mentions(low, p)]
            if missing:
                issues.append("it never showed these hits landing: " + ", ".join(missing[:8])
                              + ". Every listed hit must appear, on that body part")
            kind = getattr(self, "_struggle_kind", None)
            full = prior + "\n" + text
            if self._must_struggle and kind == "escape" and not ESCAPE_WORDS.search(full):
                issues.append(f"it never showed the ESCAPE: {self._must_struggle}. The pin is OVER this beat: show her "
                              f"actually breaking out from under the pinner (throwing her off, wrenching free, rolling "
                              f"clear), not just straining")
            elif self._must_struggle and kind == "escape":
                last = list(ESCAPE_WORDS.finditer(full))[-1].end()
                again = STILL_PINNED.search(full[last:])
                if again and len(full) - last <= len(text):  # the slip is in this part, not an earlier one
                    issues.append(f"it put her back under the pin after the ESCAPE (\"{again.group(0)}\"): once she "
                                  f"breaks free the pin is over for good this beat. Nothing presses on her any more, and "
                                  f"the two end the beat apart")
            elif self._must_struggle and kind == "partial" and not (STRUGGLE_WORDS.search(full) and HIT_WORDS.search(full)):
                issues.append(f"it skipped the struggle: {self._must_struggle} (show her wrenching partly loose AND "
                              f"landing that hit before the pin clamps back down)")
            elif self._must_struggle and not STRUGGLE_WORDS.search(full):
                issues.append(f"it skipped the struggle: {self._must_struggle}")
        return issues

    def _facing_problems(self, text):
        """Sentences that show a downed fighter lying the other way: [(fighter, facing, words)]."""
        facing = getattr(self, "facing", {}) or {}
        if not facing or not self.strengths:
            return []
        out = []
        for sent, whos, named in self._said(text):
            if len(whos) != 1 or whos[0] not in facing or ROLLING.search(sent):
                continue
            fc = facing[whos[0]]
            m = (SAYS_FACE_UP.search(sent) if fc == "face-down" else
                 SAYS_FACE_DOWN.search(sent) if fc == "face-up" else None)
            if m:
                out.append((whos[0], fc, m.group(0)))
        return out

    def _echo_grams(self):
        """Five-word runs from the notes' own descriptions of statuses ("rattled and a half-second behind"): copied
        into the story they read as instructions, not prose."""
        got = getattr(Narrator, "_ECHO", None)
        if got is None:
            got = set()
            for txt in Engine.STATUS_LOOK.values():
                w = re.findall(r"[a-z'-]+", txt.split(":", 1)[-1].lower())
                got |= {" ".join(w[i:i + 5]) for i in range(len(w) - 4)}
            Narrator._ECHO = got
        return got

    def _log_slips(self, text):
        """Mistakes seen in real runs that the older checks let through. Returns [(sentence, what is wrong)]:
        'pinned' with no pin; the whole body going limp while she is still strong; a part breaking that can't; a
        fresh crack or fresh pain in a part nothing hit; a move remembered on the fighter it never touched; the
        notes' own words copied; the same blow told a second time."""
        if not self.rules.get("narration", {}).get("accuracy_check", True) or not self.strengths \
                or getattr(self, "_hurt_now", None) is None or getattr(self, "_calm_beat", False):
            return []
        out, seen = [], set()

        def add(sent, why):
            if sent not in seen:
                seen.add(sent); out.append((sent, why))
        struck = [p.lower() for p in (getattr(self, "_strike_parts", []) or []) + (getattr(self, "_must_parts", []) or [])]
        struck_nouns = {p.split()[-1].rstrip("s") for p in struck}
        echo = self._echo_grams()
        victims = getattr(self, "move_victims", None) or {}
        pinned = set(getattr(self, "pinned_now", None) or ())
        stuck = set(getattr(self, "cant_act", None) or ())
        all_nouns = {p.split()[-1].rstrip("s") for parts in self.damage_by.values() for p in parts}
        struck_regions = {body_region(p) for p in struck} | {body_region(str(g[2])) for g in (getattr(self, "grips", None) or [])}
        last_named = []
        for sent, whos, named in self._said(text):
            low = sent.lower()
            if BEAT_WORD.search(sent):
                add(sent, "it says 'this beat': that is a word from the notes, not the story")
            w5 = re.findall(r"[a-z'-]+", low)
            if any(" ".join(w5[i:i + 5]) in echo for i in range(len(w5) - 4)):
                add(sent, "it copies the notes' own description word for word: show it in your own words")
            m = PINNED_FREE.search(sent)
            if m and not getattr(self, "_any_grip", False) and not PINNED_OK.search(sent):
                add(sent, f"it says someone is pinned or held down (\"{m.group(0)}\"), but there is NO pin and no hold "
                          f"this beat: she lies there free, with nothing on her")
            if named:
                last_named = list(whos)
            m = PART_BROKE.search(sent)
            if m and not any(_mentions_exact(low, p) for p in (getattr(self, "breakable", None) or [])):
                add(sent, f"something breaks (\"{m.group(0)}\"), but nothing of hers can break yet: bruised, swollen, "
                          f"cracked at the very worst")
            m = BLOW_INTO.search(sent)
            if m and not RECALLED.search(sent[:m.start()]) \
                    and not MISSED_HER.search(sent) and not NEARLY.search(sent[:m.start()][-45:]):
                noun = m.group(1).lower().rstrip("s")
                region = body_region(noun)
                if noun in all_nouns and region != "other" and region not in struck_regions:
                    add(sent, f"a blow lands on someone's {m.group(1).lower()} (\"{' '.join(m.group(0).split())[:60]}\"), but "
                              f"nothing hits that part this beat: only the listed hits land")
            m = BLOW_AT.search(sent)
            if m and not RECALLED.search(sent[:m.start()]) and not MISSED_HER.search(sent) \
                    and not NEARLY.search(sent[:m.start()][-45:]):
                tag = m.group(1)
                owner = tag if tag in self.strengths else {a.lower(): n_ for a, n_ in (getattr(self, "aliases", None) or {}).items()}.get(tag.lower())
                noun = m.group(2).lower().rstrip("s")
                if owner in self.strengths and owner not in (self._hurt_now or ()) and noun in all_nouns:
                    add(sent, f"a blow lands on {poss(owner)} {m.group(2).lower()} (\"{' '.join(m.group(0).split())[:60]}\"), but "
                              f"nothing hits that part this beat: nothing lands on {owner} at all")
            for holder, held, part, with_ in (getattr(self, "grips", None) or []):
                if re.search(r"\btails?\b|\bcoils?\b", str(with_), re.I) and holder in whos and FREE_TAIL.search(sent) \
                        and (held not in whos or len(whos) == 1) and not RECALLED.search(sent):
                    add(sent, f"{poss(holder)} tails are round {poss(held)} {part} this beat: they can't also be spinning "
                              f"or lashing free")
                    break
            m = WORST_OF.search(sent)
            hurt1 = [w for w in (self._hurt_now or ()) if w in self.strengths]
            wf = whos[0] if len(whos) == 1 else hurt1[0] if len(hurt1) == 1 and not named else None
            if m and wf:
                mine = self.damage_by.get(wf) or {}
                on_her = {str(g[2]).lower() for g in (getattr(self, "grips", None) or []) if g[1] == wf}
                now = [p for p in mine if p in struck or p in on_her]
                said = [(low.rfind(p, 0, m.start()), p) for p in mine if re.search(r"\b" + re.escape(p) + r"\b", low[:m.start()])]
                if said and len(now) >= 2:
                    part = max(said)[1]
                    top = max(now, key=lambda p: mine[p])
                    if top != part and mine[part] < 0.6 * mine[top]:
                        add(sent, f"it says {poss(wf)} {part} has the worst of it, but her {top} is the one far worse "
                                  f"hurt: the {part} is the lesser of them")
            who = whos[0] if len(whos) == 1 else None
            if not who or who not in self.strengths:
                continue
            if named:
                # a part only the OTHER fighter has, given to this one by name ("Nocturne's flotation sac")
                mine = {w for p in (self.damage_by.get(who) or {}) for w in p.split()}
                tags = [who] + [a for a, n_ in (getattr(self, "aliases", None) or {}).items() if n_ == who]
                for other, theirs in self.damage_by.items():
                    if other == who:
                        continue
                    odd = {w for p in theirs for w in p.split() if w not in mine and w not in COMMON_BODY and len(w) > 2}
                    hit = next((w for w in odd for t in tags if re.search(
                        r"\b" + re.escape(t) + r"(?:'s|’s|'|’) (?:\w+ ){0,2}" + re.escape(w) + r"s?\b", sent, re.I)), None)
                    if hit:
                        add(sent, f"it gives {who} a {hit}, but that is {poss(other)} body, not hers: check who this "
                                  f"sentence is about")
                        break
            m = LIMP_BODY.search(sent)
            if m and self.strengths.get(who, 0) >= 40 and who not in pinned and who not in stuck \
                    and (named or not pinned):   # under a pin, an unnamed "she couldn't move" is the pinned one's
                add(sent, f"it has {who} go limp or unable to move (\"{m.group(0)}\"), but she still has most of her "
                          f"strength: hurt and winded, she can move, and she is trying to")
            parts = self.damage_by.get(who) or {}
            if CRACK_NOW.search(sent) and not re.search(r"\b(?:had|earlier|already|before|once)\b", sent, re.I):
                for p in parts:
                    noun = p.split()[-1].rstrip("s")
                    if len(noun) < 3 or noun in struck_nouns:
                        continue
                    if re.search(r"\b" + re.escape(noun) + r"s?\b[^.!?;,—]{0,22}\b(?:cracked|cracking|popped|popping)\b"
                                 r"(?!\s+(?:against|like|through|across|on|off|down|the air|in the air|open|out a|her|his))", low):
                        add(sent, f"{poss(who)} {noun} cracks or pops, but nothing hit it this beat: an old hurt only "
                                  f"aches, it doesn't crack again by itself")
                        break
            if PAIN_NOW.search(sent):
                p = self._untouched_part(who, sent)
                noun = p.split()[-1].rstrip("s") if p else ""
                if p and noun not in struck_nouns and re.search(
                        r"\b" + re.escape(noun) + r"s?\b\W+(?:\w+\W+){0,3}?(?:hurting|ach(?:ed|ing)|throbb(?:ed|ing)|"
                        r"scream(?:ed|ing)|burn(?:ed|ing)|blaz(?:ed|ing)|"
                        + ("" if noun in ("fin", "ear", "tail", "fan", "antenna", "nostril", "ruff") else   # these flare by moving
                           r"flar(?:ed|ing)(?! (?:wide|out|open|up|back|flat))|") + r"on fire)\b", low):
                    add(sent, f"{poss(who)} {p} is said to hurt, but it has never been hit: check which part the blow "
                              f"really landed on")
            for mv, got in victims.items():
                if who in got or not re.search(r"\b" + re.escape(mv) + r"\b", sent, re.I):
                    continue
                if " " not in mv and not any(not re.search(r"\b(?:to|not|n't|never|would|could|didn't|did not)\s+$", sent[:x.start()], re.I)
                                             for x in re.finditer(r"\b" + re.escape(mv) + r"\b", sent, re.I)):
                    continue   # "not to bite, only to hold": the verb, not the move called Bite
                if not re.search(r"\b(?:where|from|since|after|left by|of|earlier|had (?:bitten|struck|opened|caught|landed|hit|"
                                 r"cut|raked|burned|frozen))\b", low) and not re.search(re.escape(mv.lower()) + r"(?:'s|’s)", low):
                    continue
                others = [o for o in got if o != who]
                theirs = any(re.search(r"\b" + re.escape(x.split()[-1].rstrip("s")), low)
                             for o in others for x in (getattr(self, "move_parts", None) or {}).get((mv, o), []))
                if others and not theirs:
                    add(sent, f"it remembers {mv} as something that hurt {who}, but {mv} was never landed on her: it hit "
                              f"{' and '.join(others)}")
                    break
        # back on her feet with no get-up this beat: she ends the beat on the ground
        pe, ps = getattr(self, "posture_end", {}) or {}, getattr(self, "posture_start", {}) or {}
        rising = {getattr(self, "_getup_who", None), getattr(self, "_must_rise", None)} | set(getattr(self, "_getup_failed", ()) or ())
        lifted = getattr(self, "_must_reposition", None) or {}
        stuck_down = [w for w in self.strengths if str(pe.get(w, "")).upper().startswith("ON THE GROUND") and w not in rising
                      and w not in pinned and not (isinstance(lifted, dict) and lifted.get("defender") == w)]
        if stuck_down:
            fell = {w: str(ps.get(w, pe.get(w, ""))).upper().startswith("ON THE GROUND") for w in stuck_down}
            for sent, whos, named in self._said(text):
                for w in stuck_down:
                    if w not in whos:
                        continue
                    m = GOT_UP.search(sent)
                    if m and fell[w] and list(whos) == [w] and not _UP_TRY.search(sent[:m.start()]):
                        add(sent, f"it has {w} get back up (\"{m.group(0)}\"), but she is ON THE GROUND when this beat "
                                  f"ends and nobody gets up this beat: she stays down")
                    if not fell[w] and (FALL.search(sent) or GROUNDED.search(sent) or SLID_DOWN.search(sent) or re.search(
                            r"\b(?:hit|struck|crashed|slammed|smashed|landed|dropped|went down|fell|thrown|threw|hurled|"
                            r"flung|tumbl\w+|skidd\w+)\b", sent, re.I)):
                        fell[w] = True      # from here on in the passage she is down
        # "Her flotation sac deflated" said of the fighter who has no such thing. Whose stretch it is: the last
        # sentence before it (at most five back) that OPENS with a fighter as its subject, or else whose side this
        # part of the beat is told from. That is sure enough to act on unless the owner of the thing was named in
        # the sentence just before or earlier in the same paragraph ("...her hind paws on the Buizel's hips. Her
        # flotation sac hissed": the reader follows that). Without a sure subject, the older, wider test: the three
        # paragraphs before it name only the fighter who has none
        if len(self.damage_by) >= 2:
            tags = {w: [w] + [a_ for a_, n_ in (getattr(self, "aliases", None) or {}).items() if n_ == w] for w in self.damage_by}
            words_of = {w: {x for p in parts for x in p.split()} for w, parts in self.damage_by.items()}
            names = list(self.strengths)
            aliases = getattr(self, "aliases", None)
            leads = self._leads_for(text)

            def told(chunk, w):
                return any(re.search(r"\b" + re.escape(t) + r"\b", chunk, re.I) for t in tags[w])
            paras = [p for p in text.split("\n") if p.strip()]
            flat = [(i, x.strip()) for i, para in enumerate(paras) for x in _SENT.split(para.strip()) if x.strip()]
            for k, (i, sent) in enumerate(flat):
                m = re.match(r"[\s*_\"“]*(?:(?:And|But|Then|So)\s+)?Her\s+([\w-]+)(?:\s+([\w-]+))?", sent)
                if not m:
                    continue
                about, sure = None, False
                for back in range(k - 1, max(-1, k - 6), -1):
                    prev = flat[back][1]
                    about = _subject(prev, names, aliases, last=True)
                    if about:
                        sure = _subject(prev, names, aliases, opening=True) == about
                        break
                    if prev in leads:
                        about, sure = leads[prev], True
                        break
                if not about:
                    # nobody named for five sentences: deep inside a part told from one fighter's side, it is hers
                    about = next((leads[flat[j][1]] for j in range(k, -1, -1) if flat[j][1] in leads), None)
                    sure = bool(about)
                if about and about not in words_of:
                    about, sure = None, False
                near = " ".join(x for j, x in flat[max(0, k - 1):k + 1] if True) + " " + " ".join(x for j, x in flat[:k] if j == i)
                window = "\n".join(paras[max(0, i - 3):i]) + " " + " ".join(x for j, x in flat[:k + 1] if j == i)
                for w in [x.lower().rstrip("s") for x in m.groups() if x]:
                    owners = [f for f, ws in words_of.items() if w in ws or w + "s" in ws]
                    if not owners or len(owners) == len(words_of) or w in COMMON_BODY or w == "spike" or len(w) < 3:
                        continue
                    if about in owners:
                        continue
                    who = None
                    if about and sure:
                        who = about if not any(told(near, f) for f in owners) else None
                    elif i >= 2:    # (with less than two paragraphs before it there is too little to tell)
                        others = [f for f in words_of if f not in owners and told(window, f)]
                        who = others[0] if others and not any(told(window, f) for f in owners) else None
                    if who:
                        add(sent, f"it says \"her {w}\", but this stretch is about {who}, who has none: that "
                                  f"is {poss(owners[0])} body. Check who this sentence is about")
                        break
        # the same blow told twice: a second landing of a hit that happens once, well after the first telling
        once = [p for p in dict.fromkeys(getattr(self, "_strike_parts", []) or [])
                if (getattr(self, "_strike_parts", []) or []).count(p) == 1]
        if once and not getattr(self, "_ongoing", False):
            paras = [p for p in text.split("\n") if p.strip()]
            first = {}
            for i, para in enumerate(paras):
                for sent in (x for x in _SENT.split(para.strip()) if x):
                    low = sent.lower()
                    m = IMPACT_NOW.search(sent)
                    if not m or RECALLED.search(sent[:m.start()]):
                        continue
                    for p in once:
                        if re.search(r"\b" + re.escape(p.lower()) + r"\b", low):
                            near = [c for c in re.split(r"[,;:—–]", sent) if re.search(r"\b" + re.escape(p.lower()) + r"\b", c.lower())]
                            if near and all(_NOT_YET.search(c) for c in near):
                                continue    # "her horn pointed at the middle of the Buizel's chest": aimed, not landed
                            if p in first and i - first[p] >= 3:
                                add(sent, f"it tells the blow to the {p.lower()} a SECOND time: that hit landed once and "
                                          f"was already told above. Here, only what came after it")
                            first.setdefault(p, i)
        return out

    def _count_slips(self, text):
        """A count the fight doesn't bear out ("had just been thrown—twice—" when it was once). Returns
        [(sentence, what is wrong, the sentence with the count taken out, or None when it never happened at all)].
        The count is read generously: 'thrown' counts throws and slams, 'slammed' anything that drove her into
        something, and the fighter who has had the most of it is the one compared against."""
        tally = getattr(self, "tally", None)
        if tally is None or not self.rules.get("narration", {}).get("accuracy_check", True) \
                or getattr(self, "_calm_beat", False):
            return []
        out = []
        for para in (text or "").split("\n"):
            for sent in (x for x in _SENT.split(para.strip()) if x):
                m = COUNT_CLAIM.search(sent)
                if not m:
                    continue
                verb = (m.group("v1") or m.group("v2")).lower()
                word = (m.group("c1") or m.group("c2")).lower()
                kinds = next(k for v, k in _CNT_KINDS if verb.startswith(v))
                names = {key.split("|", 1)[1] for key in tally if "|" in key}
                real = max([sum(int(tally.get(f"{k}|{n}", 0)) for k in kinds) for n in names] or [0])
                if real >= _CNT_N.get(word, 3):
                    continue
                c = "c1" if m.group("c1") else "c2"
                v = "v1" if m.group("v1") else "v2"
                a, b = m.start(c), m.end(c)
                lead = sent[m.end(v):a] if v == "v1" else sent[:a][len(sent[:a].rstrip(" ,—–-")):]
                a -= len(lead) if v == "v1" else 0
                if v == "v2":
                    a = len(sent[:m.start(c)].rstrip(" ,—–-"))
                tail = sent[b:]
                dash = bool(re.search(r"[—–]", sent[a:m.start(c)])) and bool(re.match(r"\s*[—–]", tail))
                tail = re.sub(r"^\s*[—–]\s*", " ", tail) if dash else re.sub(r"^\s*,\s*", " ", tail) if "," in sent[a:m.start(c)] else tail
                fixed = (sent[:a] + (" " if v == "v1" and lead.strip(" ,—–-") else "") + (lead.strip(" ,—–-") if v == "v1" else "")
                         + tail)
                fixed = re.sub(r"\s{2,}", " ", fixed).replace(" .", ".").replace(" ,", ",").strip()
                out.append((sent, f"it says she was {verb} {word}, but that has happened "
                                  f"{'once' if real == 1 else 'never' if real == 0 else str(real) + ' times'} in this fight "
                                  f"so far: don't count it, or count it right", fixed if real >= 1 else None))
        return out

    def _pressed_again(self, text, prior=""):
        """A grip that is on from the start of the beat to the end can be told pressing once from each side. The third
        and later sentences that tell the same jaws on the same neck, or the same paws on the same hips, are asked
        for again (never cut: they may be the only place that part's pain is shown)."""
        grips = [g for g in (getattr(self, "grips", None) or []) if g[0] in self.strengths and g[1] in self.strengths]
        if not grips or getattr(self, "_calm_beat", False) or not self.rules.get("narration", {}).get("accuracy_check", True):
            return []
        out, seen_groups = [], set()
        for holder, held, part, with_ in grips:
            fam = next(((k, rx) for k, rx in GRIP_NOUNS if re.search(r"\b(?:" + rx + r")\b", str(with_ or ""), re.I)), None)
            noun = str(part).lower().split()[-1].rstrip("s")
            if fam is None or (holder, held, fam[0], noun) in seen_groups:
                continue
            seen_groups.add((holder, held, fam[0], noun))
            both = re.compile(r"\b(?:" + fam[1] + r")\b", re.I), re.compile(r"\b" + re.escape(noun) + r"s?\b", re.I)
            n = 0
            for chunk, mine in ((prior or "", False), (text or "", True)):
                for para in chunk.split("\n"):
                    for sent in (x for x in _SENT.split(para.strip()) if x):
                        if PRESS_VERB.search(sent) and both[0].search(sent) and both[1].search(sent):
                            n += 1
                            if mine and n >= 3:
                                out.append((sent, f"this is the {('third', 'fourth', 'fifth')[min(n, 5) - 3]} sentence that tells "
                                                  f"{poss(holder)} {fam[0]} pressing {poss(held)} {noun}: it has been told. "
                                                  f"Give this sentence to something not shown yet (her breath, a sound, "
                                                  f"another part, what she tries), or to how it FEELS without telling the "
                                                  f"pressing again"))
        return out

    def _sitting_problems(self, text):
        """The LAST thing the passage says about how a downed fighter is placed has to match the engine: a fighter
        who ends the beat SITTING UP is not left lying flat, and one who ends it lying is not left sitting. Earlier
        sentences may differ (she slid down to sitting; she was sitting and was knocked flat).
        Returns [(fighter, how she really ends, the words)]."""
        facing = getattr(self, "facing", {}) or {}
        if not facing or not self.strengths or getattr(self, "_calm_beat", False):
            return []
        last = {}
        for sent, whos, named in self._said(text):
            whos = [w for w in whos if facing.get(w)]   # only a fighter on the ground sits or lies
            if len(whos) != 1:
                continue
            sit, flat = SAYS_SITTING.search(sent), SAYS_FLAT.search(sent)
            if sit and flat:
                sit, flat = (sit, None) if sit.start() > flat.start() else (None, flat)   # the later one is how it ends
            if sit or flat:
                last[whos[0]] = ("sitting", sit.group(0)) if sit else ("flat", flat.group(0))
        out = []
        for who, (said, bit) in last.items():
            if facing[who] == "sitting up" and said == "flat":
                out.append((who, "sitting up", bit))
            elif facing[who] in ("face-up", "face-down", "on her side") and said == "sitting":
                out.append((who, facing[who], bit))
        return out

    def _unhurt_lines(self, text):
        """Sentences that wound a fighter nothing hit this beat: [(fighter, matched words)]."""
        if self._hurt_now is None or not self.strengths or not self.rules.get("narration", {}).get("accuracy_check", True):
            return []
        clean = [f for f in self.strengths if f not in self._hurt_now]
        out = []
        names = list(self.strengths)
        # a blow shown LANDING on a fighter nothing touches this beat ("The rush struck Nocturne in the chest" when she
        # dodged it): told by name, as the thing that is hit
        tags = {w: [w] + [a_ for a_, n_ in (getattr(self, "aliases", None) or {}).items() if n_ == w] for w in clean}
        for sent in (x for para in text.split("\n") for x in _SENT.split(para.strip()) if x):
            if MISSED.search(sent) or MISSED_HER.search(sent) or _DODGE_TOLD.search(sent):
                continue
            for w, ts in tags.items():
                m = re.search(r"\b(?:struck|hit|caught|clipped|punched|kicked|rammed|raked|slashed|bit|(?:slammed|smashed|"
                              r"crashed|hammered|ploughed|plowed|thudded|drove|tore|ripped|sank|bit) into|landed (?:\w+ )?on|"
                              r"connected with|took)\s+(?:the\s+)?(?:" + "|".join(map(re.escape, ts)) + r")\b"
                              r"(?:(?:'s|’s|'|’) |\s+(?:in|on|across|under|below|above|behind|square|full|flush|high|low)\b)",
                              sent, re.I)
                if not m:
                    continue
                before = sent[:m.start()]
                clause = re.split(r"[,;:—–]", before)[-1]      # (a recall is told inside its own clause)
                if NEARLY.search(before[-45:]) or RECALLED.search(clause) or re.search(
                        r"\b(?:had|if|would|could|should|might|meant to|tried to|trying to|wanted to|aimed to|going to|"
                        r"about to|to)\s+(?:\w+\s+)?$", before, re.I) or re.search(
                        r"\b(?:spray|wind|draught|draft|droplets?|mist|echo|sound|light|smell|gaze|eyes?|voice)\b",
                        before[-40:], re.I):
                    continue
                out.append((w, f"{m.group(0).strip()}: a blow shown landing on her, but nothing touches her this beat"))
                break
        for sent, whos, named in self._said(text):
            if len(whos) != 1:
                continue
            if named and len(names) == 2 and re.search(
                    r"\b" + re.escape(whos[0]) + r"(?:'s|’s|'|’) (?:\w+ )?(?:claws?|teeth|fangs|jaws?|horn|blade|tails?|paws?|"
                    r"talons|attack|strike|slash|bite)\b", sent):
                whos = [n for n in names if n != whos[0]]  # "where Nocturne's claws had..." is about the other one
            m = HURT_NEW.search(sent)
            if m and whos[0] in clean:
                out.append((whos[0], m.group(0)))
                continue
            w = WOUND.search(sent)
            if w and MISSED_HER.search(sent):
                w = None   # "the blade hissed past her ear and cut nothing but air": it says it missed
            part = self._untouched_part(whos[0], sent) if w else None
            if part:
                # "Under the left one the cut thigh had stopped jumping", told from the pinner's side: the thigh is
                # the one UNDER her paw, the pinned fighter's, and that one is hurt
                base = re.sub(r"^(left|right) ", "", part.lower())
                held = [g for g in (getattr(self, "grips", None) or []) if g[0] == whos[0] and g[1] in self.damage_by
                        and re.sub(r"^(left|right) ", "", str(g[2]).lower()) == base]
                if any((self.damage_by.get(g[1]) or {}).get(str(g[2]).lower(), 0) > 0 for g in held):
                    continue
                out.append((whos[0], f"{w.group(0)}, on her {part}, which has never been hurt"))
        return out

    def _untouched_part(self, fighter, sent):
        """A body part this sentence names on `fighter` that has taken no damage at all (side-less names count
        only when every side is untouched), or None."""
        dmg = self.damage_by.get(fighter) or {}
        low = sent.lower()
        groups = {}
        for p, d in dmg.items():
            base = re.sub(r"^(left|right) ", "", p)
            groups.setdefault(base, []).append((p, d))
        for base, items in groups.items():
            if not re.search(r"\b" + re.escape(base) + r"s?\b", low):
                continue
            sided = [p for p, _ in items if re.search(r"\b" + re.escape(p) + r"\b", low)]
            named = sided or [p for p, _ in items]
            if all(dmg[p] <= 0 for p in named):
                return named[0]
        return None

    @staticmethod
    def _spoken(text):
        """Spoken lines of two or more words (a bare cry like "Nnngh!" isn't talking)."""
        return [m for m in _SPEECH.finditer(text or "") if len(m.group(1).split()) >= 2]

    @staticmethod
    def _thoughts(text):
        """Italic thoughts, not single emphasised words like *snap* inside a sentence."""
        return [m for m in _THOUGHT.finditer(text or "")
                if len(m.group(1).split()) >= 2 or re.search(r"[.!?…—-]\s*$", m.group(1))]

    def _talk_limits(self):
        t = self.rules.get("narration", {}).get("talk", {}) or {}
        return (int(t.get("spoken_per_beat", 1)), int(t.get("spoken_gap", 2)), int(t.get("thoughts_per_part", 3)),
                bool(t.get("enabled", True)))

    def _talk_allowance(self, prior):
        """How many spoken lines this part may still have, and how many thoughts."""
        per_beat, gap, thoughts, on = self._talk_limits()
        if not on:
            return None, None
        since = getattr(self, "_beat_no", 0) - getattr(self, "_last_spoken", -999)
        allowed = 0 if (gap and since <= gap) else per_beat
        return max(0, allowed - len(self._spoken(prior or ""))), thoughts

    def _talk_problem(self, text, prior=""):
        spoken_left, thoughts = self._talk_allowance(prior)
        if spoken_left is None:
            return None
        said = self._spoken(text)
        many = self._thoughts(text)
        notes = []
        if len(said) > spoken_left:
            notes.append(f"too much talking ({len(said)} spoken lines; " + ("none fit here: someone spoke just a beat or "
                         "two ago" if spoken_left == 0 else f"at most {spoken_left} in this part") + ")")
        if thoughts and len(many) > thoughts:
            notes.append(f"too many thoughts in italics ({len(many)}; keep the {thoughts} that matter most)")
        if not notes:
            return None
        return ("it had " + " and ".join(notes) + ". These fighters are mostly silent: show what they feel through "
                "bodies, breath, and action instead of lines")

    def _trim_talk(self, text, prior=""):
        """Remove spoken lines and thoughts beyond the allowance (the earliest are kept), with their 'she said' tags."""
        spoken_left, thoughts = self._talk_allowance(prior)
        tag = (r"(\s*,?\s*(?:she|he|it|they|the \w+|[A-Z]\w+)\s+(?:thought|said|muttered|whispered|growled|hissed|snarled|"
               r"gasped|added|chittered|spat|barked|rasped|told herself)\b[^.!?*\"“]*[.!?])?")
        out = text
        for m in self._spoken(text)[spoken_left:]:
            out = re.sub(re.escape(m.group(0)) + tag, "", out, count=1)
        if thoughts:
            for m in self._thoughts(text)[thoughts:]:
                out = re.sub(re.escape(m.group(0)) + tag, "", out, count=1)
        paras = [re.sub(r"\s{2,}", " ", p).strip() for p in out.split("\n")]
        paras = [p for p in paras if p.strip(" .,;:—-*\"“”") or not p]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip()

    @staticmethod
    def _issue_weight(issues):
        """Problems that change what happened (a missing escape, hit, struggle, get-up; an invented fall or wound)
        count far more than wording slips, which the cleanup can fix."""
        heavy = ("ESCAPE", "never showed", "struggle", "finally getting up", "fall or go down", "doesn't exist",
                 "collapse", "wrong way round", "bones that can't", "ON HER FEET this whole beat", "NOBODY is pinned",
                 "KEEPS HER FEET this beat", "ONE strike into several", "a bite that isn't in this beat",
                 "NO attempt to rise", "serious injury that isn't there", "THE PIN HOLDS this beat")
        return sum(10 if any(h in i for h in heavy) else 1 for i in issues)

    def _swear_problem(self, text):
        """None if the swearing in this text is within the setting, else a note for the rewrite."""
        n = self.rules.get("narration", {})
        mode = str(n.get("swearing", "rare")).lower()
        found = [m.group(0) for m in SWEAR.finditer(text)]
        if not found or mode == "free":
            return None
        if mode == "never":
            return f"it swore (\"{found[0]}\"): no swearing at all"
        gap = int(n.get("swearing_gap", 5))
        since = getattr(self, "_beat_no", 0) - getattr(self, "_last_swear", -999)
        if len(found) > 1 or since <= gap:
            return (f"it swore too much (\"{', '.join(found[:3])}\"): swearing is rare, at most one curse every few "
                    f"beats, and there was one just recently. Use other words")
        return None

    def _call(self, user_msg, words, coverage=False, prior=""):
        text = self._generate(user_msg, words)
        issues = self._review(text, coverage, prior)
        mode = str(self.rules.get("narration", {}).get("best_of_two", "important")).lower()
        if mode == "always" or (mode == "important" and self._important):
            # a big moment: write a second draft and keep whichever has fewer problems
            if self.progress:
                self.progress("big moment: writing a second draft to compare")
            other = self._generate(user_msg, words)
            other_issues = self._review(other, coverage, prior)
            # the one that gets the EVENTS right wins (an invented fall outweighs any number of wording slips)
            if ((self._issue_weight(other_issues), len(other_issues), -len(other))
                    < (self._issue_weight(issues), len(issues), -len(text))):
                text, issues = other, other_issues
        repair = bool(self.rules.get("narration", {}).get("paragraph_repair", True))
        missing = []
        if issues:
            # one rewrite with every problem spelled out; a local model follows concrete notes far better than rules
            if self.progress:
                labels = [_slip_label(i) or ("faint not shown" if ("never showed" in i and "fainting" in i) else "invented escape" if "THE PIN HOLDS this beat" in i else "fighter who isn't in this fight" if "who is NOT in this fight" in i else "invented fall" if "KEEPS HER FEET this beat" in i else "fighter who is out" if "out of this fight and never landed" in i else "wrong posture" if "ON HER FEET this whole beat" in i else "invented pin" if "NOBODY is pinned" in i else "game terms" if "game terms" in i else "repeated lines" if "stock lines" in i else "too much talking" if "mostly silent" in i else "swearing" if "swore" in i else "broken prose" if "prose broke down" in i else "stray electricity" if "electricity (" in i else "get-up not finished" if "finally getting up" in i else "extra get-up tries" if "FIRST try" in i else "missing roll or lift" if ("rolling" in i or "hauling" in i) and "never showed" in i else "wrong way round" if "wrong way round" in i else "invented wound" if "doesn't exist" in i else "invented fall" if "fall or go down" in i else "collapse" if "collapse" in i else "broken bones" if "bones that can't" in i
                           else "graphic words" if "TONE" in i else "seconds counted in a pin" if "a pin has NO clock" in i else "pin clock" if "time wrong" in i or "pin clock" in i
                           else "missing escape" if "ESCAPE" in i
                           else "missing hits" if "never showed" in i else "missing struggle" if "struggle" in i
                           else "parts called useless too early" if "as useless" in i
                           else "wrong strike count" if "ONE strike" in i
                           else "invented bite" if "a bite that isn't" in i
                           else "wrong weapon" if "wrong weapon" in i
                           else "hurt part called fine" if "good or strong" in i
                           else "invented escape" if "THE PIN HOLDS this beat" in i
                           else "minor hurt made serious" if "serious injury that isn't there" in i
                           else "invented get-up try" if "NO attempt to rise" in i
                           else "numb pain" if "go numb" in i
                           else "pin clock" if "time REMAINING" in i
                           else "standing on a hand" if "her paws are her HANDS" in i
                           else "anatomy from another species" if "nobody in this fight has" in i
                           else "other") for i in issues]
                self.progress("checking the draft: " + ("" if repair else "rewriting to fix ")
                              + ", ".join(dict.fromkeys(labels)))
            missing = [i for i in issues if any(m in i for m in MISSING_MARKS)]
        if issues and (missing or not repair):
            # something that should be there is missing (a hit, the escape, the get-up): that needs writing again
            if repair and self.progress:
                self.progress("something is missing from the draft: writing it again")
            fix = (user_msg + "\n\nYOUR PREVIOUS DRAFT had problems: " + " ALSO, ".join(issues)
                   + ". Write it again with the same events, fixing all of that.")
            redo = self._generate(fix, words)
            # the rewrite is checked too: if it broke something the draft had right (dropped the escape, a hit...),
            # keep whichever has fewer problems, weighting the ones that change what happened
            redo_issues = self._review(redo, coverage, prior)
            if self._issue_weight(redo_issues) <= self._issue_weight(issues):
                text, issues = redo, redo_issues
            elif self.progress:
                self.progress("the rewrite broke something the draft had right: keeping the draft (its slips get cleaned up)")
            # still wrong about what happened (an invented fall, a missing hit...)? one more try, aimed only at that
            heavy = [i for i in issues if self._issue_weight([i]) >= 10
                     and (not repair or any(m in i for m in MISSING_MARKS))]
            if heavy and int(self.rules.get("narration", {}).get("max_rewrites", 2)) >= 2:
                if self.progress:
                    self.progress("still wrong about what happened: one more rewrite")
                fix2 = (user_msg + "\n\nYOUR LAST TWO DRAFTS got the events wrong: " + " ALSO, ".join(heavy)
                        + ". Write it again. Nothing happens in this beat except what is listed above: nobody falls, "
                          "is pinned, or is wounded unless it's listed. Keep all the listed events and their detail.")
                third = self._generate(fix2, words)
                third_issues = self._review(third, coverage, prior)
                if self._issue_weight(third_issues) < self._issue_weight(issues):
                    text, issues = third, third_issues
        if repair:
            # mistakes the program can point at: write just those paragraphs again; the rest stays word for word
            text = self._repair_paragraphs(user_msg, text, prior)
            text = self._second_reading(user_msg, text, prior)
        loose = self._pin_broken_lines(text)
        if loose:
            # still there after the rewrites: what follows an escape that never happened is all invented, so the part
            # ends just before it (a short beat is topped up afterwards)
            at = text.find(loose[0][2])
            if at >= 0:
                text = text[:at].rstrip()
                if self.progress:
                    self.progress("the pin holds, but the story still broke it: ending the part before that")
        chosen = text  # as written; everything below only cuts sentences that are still wrong
        window = getattr(self, "_time_window", None)
        if window:
            if _time_overrun(text, *window):
                # still wrong after the rewrite: the sentences that mark the wrong second go; the rest of the
                # passage stays (it used to be cut off at the first wrong mark, which could take the whole ending)
                text = _drop_clock_outside(text, *window)
        if self._no_clock and (_COUNTDOWN.search(text) or _bare_count(text, getattr(self, "_pin_beat", False))
                               or _TIME_MARK.search(text) or _REMAINING.search(text)):
            text = _drop_countdown(text, getattr(self, "_pin_beat", False))
        if self._no_clock and getattr(self, "_fade_pin", False) and getattr(self, "_pin_beat", False) \
                and _FADE_CLOCK.search(text):
            text = _drop_matching(text, _FADE_CLOCK)   # a pin has no clock: no counted time of any kind
        elif window and _counts_down(text):
            text = _drop_matching(text, _BARE_COUNT)
        if window and _out_of_order(text) is not None:
            text = _drop_backward_marks(text)
        if window and _REMAINING.search(text):
            text = _drop_matching(text, _REMAINING)
        gore = gore_pattern(self.rules)
        if gore is not None and gore.search(text):
            text = _drop_matching(text, gore)  # still too graphic after the rewrite: cut just those sentences
        if GAME_TERMS.search(text):
            text = _drop_matching(text, GAME_TERMS)
        if self._swear_problem((prior or "") + "\n" + text) and SWEAR.search(text):
            text = _drop_matching(text, SWEAR)
        if self._talk_problem(text, prior):
            text = self._trim_talk(text, prior)
        if degeneration(text, (getattr(self, "_story_tail", "") or "") + "\n" + (prior or "")):
            old = _ngrams((getattr(self, "_story_tail", "") or "") + "\n" + (prior or ""))
            keep = []
            for para in text.split("\n"):
                sents = re.split(r"(?<=[.!?…])\s+", para)
                keep.append(" ".join(x for x in sents if not degeneration_run_on(x) and len(_ngrams(x) & old) < 2))
            cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()
            if len(cleaned.split()) >= 0.4 * len(text.split()):
                text = cleaned  # only when enough of the beat survives
        if getattr(self, "_no_electric", False) and ELECTRIC.search(text):
            stray = {x for para in text.split("\n") for x in _SENT.split(para.strip()) if x and self._stray_electric(x)}
            if stray:   # electricity nobody threw: cut just those sentences
                text = re.sub(r"\n{3,}", "\n\n", "\n".join(
                    " ".join(x for x in _SENT.split(para) if x not in stray) for para in text.split("\n"))).strip()
        wrong_posture = ({x[3] for x in self._posture_problems(text)} | {x[1] for x in self._out_mentions(text)}
                         | {x[1] for x in self._absent_mentions(text)})
        if getattr(self, "_slammed", set()) and SLID_DOWN.search(text):
            wrong_posture |= {x for x in re.split(r"(?<=[.!?…])\s+|\n+", text) if SLID_DOWN.search(x)}
        if wrong_posture:  # a standing fighter still shown lying down or held: cut just those sentences
            text = re.sub(r"\n{3,}", "\n\n", "\n".join(
                " ".join(x for x in re.split(r"(?<=[.!?…])\s+", para) if x not in wrong_posture)
                for para in text.split("\n"))).strip()
        if self.rules.get("narration", {}).get("accuracy_check", True) and self.strengths:
            bad = set()
            for sent, whos, named in self._said(text):
                if self._down_is_hers(whos, named) and not self._unhurt_lines(sent):
                    continue
                if self._unhurt_lines(sent) or (self._fall_meant(sent) and any(
                        w not in self.on_ground and w not in getattr(self, "_landed", set())
                        and w not in getattr(self, "_slammed", set()) for w in whos)) or (
                        (COLLAPSE if named else COLLAPSE_STRONG).search(sent) and any(
                        self.strengths.get(w, 0) >= 40 and w not in self.on_ground for w in whos)):
                    bad.add(sent)
            if bad:
                text = "\n".join(" ".join(s for s in re.split(r"(?<=[.!?…])\s+", para) if s not in bad)
                                 for para in text.split("\n")).strip()
        if gore is GORE and self._bad_bones(text):
            keep = []
            for para in text.split("\n"):
                keep.append(" ".join(s for s in re.split(r"(?<=[.!?…])\s+", para)
                                     if not (BONE_SEVERE.search(s) and not any(_mentions_exact(s.lower(), p)
                                                                              for p in self.breakable))))
            text = re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()
        if window:
            text = _strip_clock_at(text, *window)  # "at thirty seconds" in a beat that ends at second ten
        still = ({x[1] for x in self._disabled_lines(text, sure=True)} | {x[2] for x in self._hand_weight_lines(text)}
                 | {x[3] for x in self._healthy_lines(text)} | {x[2] for x in self._getup_lines_invented(text)}
                 | {x[3] for x in self._overblown_lines(text)}
                 | {x[2] for x in self._weapon_lines(text) if x[0].startswith("bite")}
                 | {x[4] for x in self._grip_released_lines(text)} | {x[4] for x in self._grip_gone_lines(text)}
                 | {x[4] for x in self._grip_place_lines(text)} | {x[2] for x in self._phantom_release_lines(text)}
                 | {x[1] for x in self._foreign_mentions(text)} | {x[0] for x in self._log_slips(text)})
        for rx in ([PROMPT_ECHO, _BARE_MORE, BARE_IMPACT] + ([NUMB] if self.rules.get("narration", {}).get("numb_tier", True) is False
                                                  else [])):
            if rx.search(text):
                text = _drop_matching(text, rx)
        for sent, _, fixed in self._count_slips(text):
            if fixed and fixed not in still:
                text = text.replace(sent, fixed, 1)
            else:
                still.add(sent)
        if still:  # a limb called useless too early, weight on a hand, a bite nobody made, scales on fur
            text = re.sub(r"\n{3,}", "\n\n", "\n".join(
                " ".join(x for x in _SENT.split(para) if x not in still) for para in text.split("\n"))).strip()
        return self._keep_subjects(chosen, _drop_orphans(chosen, text))

    def _keep_subjects(self, before, after):
        """`after` is `before` with sentences cut. When a cut took the sentence that named a fighter, the next one
        ("Her chest hit the boulder...") now reads as being about whoever was named before that. Such a sentence
        gets its fighter's name back in place of the pronoun it opens with."""
        if not after or before == after or len(self.strengths) < 2:
            return after
        # sentence -> the fighter who was the SUBJECT of the sentence just before it in its paragraph, when that
        # sentence opened with her name ("Ripples collapsed forward. Her chest hit...") and named nobody else
        lead = {}
        alias = {a_.lower(): n for a_, n in (getattr(self, "aliases", None) or {}).items()}
        for para in before.split("\n"):
            sents = [x for x in _SENT.split(para.strip()) if x]
            for prev, cur in zip(sents, sents[1:]):
                m = re.match(r"(?:The )?([A-Z][\w-]+)", prev)
                who = m and (m.group(1) if m.group(1) in self.strengths else alias.get(m.group(1).lower()))
                rows = self._said(prev)
                if who and rows and rows[0][2] and list(rows[0][1]) == [who]:
                    lead.setdefault(cur.strip(), (prev.strip(), who))
        for _ in range(8):
            fix = None
            kept = {x.strip() for para in after.split("\n") for x in _SENT.split(para.strip()) if x}
            for sent, whos, named in self._said(after):
                old = lead.get(sent.strip())
                m = re.match(r"(Her|She)\b(?!self)", sent)
                if named or not old or not m or old[0] in kept or list(whos) == [old[1]]:
                    continue
                fix = (sent, (poss(old[1]) if m.group(1) == "Her" else old[1]) + sent[m.end():])
                break
            if not fix:
                break
            after = after.replace(fix[0], fix[1], 1)
        return after

    def _bad_sentences(self, text, prior=""):
        """Every sentence the program can pin a mistake on: {sentence: what is wrong}. These are the same findings
        the cuts at the end of _call act on (plus the milder ones that only ever asked for a rewrite)."""
        n = self.rules.get("narration", {})
        out = {}

        def add(sent, why):
            sent = (sent or "").strip()
            if sent and sent not in out:
                out[sent] = why
        sents = [x for para in text.split("\n") for x in _SENT.split(para.strip()) if x]
        gore = gore_pattern(self.rules)
        numb_off = n.get("numb_tier", True) is False
        swearing = bool(self._swear_problem((prior or "") + "\n" + text))
        old = _ngrams((getattr(self, "_story_tail", "") or "") + "\n" + (prior or ""))
        for x in sents:
            m = gore.search(x) if gore is not None else None
            if m:
                add(x, f"too graphic (\"{m.group(0)}\"): only a little blood, bruising, swelling; nothing torn or broken")
            m = GAME_TERMS.search(x)
            if m:
                add(x, f"a game term or number in the prose (\"{m.group(0).strip()}\"): describe the feeling instead")
            if getattr(self, "_no_electric", False) and self._stray_electric(x):
                add(x, "electricity in a move that isn't Electric-type")
            if PROMPT_ECHO.search(x) or _BARE_MORE.search(x):
                add(x, "it repeats the instructions' wording (a pain level used as a label, 'the contact point'), or "
                       "counts the time left on the pin: say how it FEELS instead")
            if BARE_IMPACT.search(x):
                add(x, "a strength word from the notes standing alone as a sentence: show the blow landing instead")
            if numb_off and NUMB.search(x):
                add(x, "pain going numb: here the worst-hurt parts stay sharply, terribly painful")
            if getattr(self, "_slammed", set()) and SLID_DOWN.search(x):
                add(x, "she slides or crumples to the ground, but she KEEPS HER FEET this beat")
            if self._no_clock and getattr(self, "_fade_pin", False) and getattr(self, "_pin_beat", False) and (
                    _FADE_CLOCK.search(x) or _TIME_MARK.search(x) or _REMAINING.search(x) or _COUNTDOWN.search(x)):
                add(x, "it counts the pin in seconds or time left, but a pin has NO clock here: nobody knows how long "
                       "she can last. Show time through her body instead (breath, strength, sight)")
            if getattr(self, "_one_strike", None) and EXTRA_SWING.search(x):
                add(x, f"a second swing: {self._one_strike} attacks only ONCE this beat; the force carries into the "
                       f"parts next to the one she hits")
            if swearing and SWEAR.search(x):
                add(x, "swearing: there was a curse just recently, use other words")
            if degeneration_run_on(x) or len(_ngrams(x) & old) >= 2:
                add(x, "it copies lines already written or runs on without articles: say something new, in plain "
                       "complete sentences")
            if gore is GORE and BONE_SEVERE.search(x) and not any(_mentions_exact(x.lower(), p) for p in self.breakable):
                add(x, "something breaks, cracks, or gives way, but that part can't break: bruised and hurting only")
        for who, words, kind, sent in self._posture_problems(text):
            add(sent, (f"it shows {who or 'a fighter'} lying down or unable to stand (\"{words}\"), but she is ON HER "
                       f"FEET this whole beat" if kind == "lying" else
                       f"someone is held down or stood over (\"{words}\"), but nobody is pinned or on the ground"))
        for w, sent in self._out_mentions(text):
            add(sent, f"{w} is out of the fight and never landed a blow: leave her out")
        for w, sent in self._absent_mentions(text):
            add(sent, f"{w} is not in this fight: she isn't there at all")
        for w, sent in self._foreign_mentions(text):
            add(sent, f"{w}: nobody in this fight has that")
        if n.get("accuracy_check", True) and self.strengths:
            for sent, whos, named in self._said(text):
                hers = self._down_is_hers(whos, named)
                wound = self._unhurt_lines(sent)
                if wound:
                    add(sent, f"a wound that doesn't exist ({wound[0][1]}): only the listed hits land")
                elif hers:
                    continue
                elif self._fall_meant(sent) and any(w not in self.on_ground and w not in getattr(self, "_landed", set())
                                               and w not in getattr(self, "_slammed", set()) for w in whos):
                    add(sent, f"{' and '.join(whos) or 'she'} falls or goes down (\"{FALL.search(sent).group(0)}\"), but "
                              f"nothing knocks her down this beat: she may stagger, and stays on her feet")
                elif (COLLAPSE if named else COLLAPSE_STRONG).search(sent) and any(
                        self.strengths.get(w, 0) >= 40 and w not in self.on_ground for w in whos):
                    add(sent, "she collapses or goes limp, but she is still strong overall: she stays up and fights")
        for part, sent in self._disabled_lines(text):
            add(sent, f"{(part or 'a limb').title()} is called useless or not working, but it is only sore or hurting: it "
                      f"hurts and is favored, and still works")
        for who, words, sent in self._hand_weight_lines(text):
            add(sent, f"{who} puts her weight on a paw or arm (\"{words}\"): she stands on her two FEET, her paws are her "
                      f"hands")
        for who, part, words, sent in self._healthy_lines(text):
            add(sent, f"{poss(who)} {part.title()} is called good or strong (\"{words}\"), but it is badly hurt: check "
                      f"LEFT and RIGHT")
        for who, words, sent in self._getup_lines_invented(text):
            add(sent, f"{who} tries to get up (\"{words}\"), but she has only just gone down: no attempt this beat")
        for who, part, words, sent in self._overblown_lines(text):
            add(sent, f"{poss(who)} {part.title()} is only MINOR this beat (\"{words}\" is far too much): a dull ache at "
                      f"most; her real pain is elsewhere")
        ok = " or ".join(sorted(getattr(self, "_weapons_ok", None) or []))
        for kind, words, sent in self._weapon_lines(text):
            add(sent, (f"a bite that isn't in this beat (\"{words}\"): no move here uses teeth" if kind == "bite" else
                       f"nobody bites {kind[8:]} this beat (\"{words}\"): the only teeth in this beat are the ones listed"
                       if kind.startswith("bite on ") else
                       f"the strike lands with the {kind} (\"{words}\"), but this move is delivered with {ok}"))
        for holder, held, part, words, sent in self._grip_released_lines(text):
            add(sent, f"{poss(holder)} grip on {poss(held)} {part} comes off (\"{words}\"), but it STAYS ON all through "
                      f"this beat: she never lets go, it doesn't slip or break, and {held} does not get free of it")
        for mv, sent in self._missed_move_lines(text):
            add(sent, f"it speaks of {mv} as a blow that landed, but {mv} MISSED: it was dodged and left no mark, no "
                      f"sting, and nothing to shake off")
        for holder, held, part, words, sent in self._grip_place_lines(text):
            add(sent, f"it puts {poss(holder)} grip in the wrong place (\"{words}\"): it is on {poss(held)} {part}, and "
                      f"nowhere else")
        for who, words, sent in self._phantom_release_lines(text):
            add(sent, f"{who} lets go of something (\"{words}\"), but she is not holding anything this beat: there is "
                      f"nothing for her to release")
        for holder, held, part, words, sent in self._grip_gone_lines(text):
            add(sent, f"{poss(holder)} grip on {poss(held)} {part} is shown as still on (\"{words}\"), but it ENDED "
                      f"earlier: nothing of {poss(holder)} is around or on {held} now, and {held} moves freely there")
        for sent, why in self._log_slips(text) + [x[:2] for x in self._count_slips(text)]:
            add(sent, why)
        for sent, why in self._pressed_again(text, prior):
            add(sent, why)
        return out

    def _rewrite_paragraph(self, user_msg, paras, i, reasons):
        """One paragraph written again with its mistake named, the paragraphs around it shown for the join."""
        para = paras[i]
        before = "\n".join(p for p in paras[max(0, i - 3):i] if p.strip())[-700:]
        after = "\n".join(p for p in paras[i + 1:i + 4] if p.strip())[:500]
        want = max(12, len(para.split()))
        ask = (user_msg + "\n\nThat part is written. ONE paragraph of it has to be written again; everything else stays "
               "exactly as it is.\n"
               + (f"JUST BEFORE IT:\n<<<\n{before}\n>>>\n" if before else "It is the first paragraph.\n")
               + f"THE PARAGRAPH TO WRITE AGAIN:\n<<<\n{para}\n>>>\n"
               + (f"JUST AFTER IT:\n<<<\n{after}\n>>>\n" if after else "")
               + "WHAT IS WRONG WITH IT: " + "; ".join(reasons) + ".\n"
               f"Write ONLY the new version of that one paragraph, about {want} words: the same moment, the same point "
               f"of view, and every detail of it that was right, with only the mistake corrected. Don't repeat the "
               f"paragraphs around it, add no new event, and write no commentary. Simply tell it right: never write a "
               f"sentence that only denies the mistake (\"Not standing over her\", \"She hadn't fallen\").")
        try:
            new = self._generate(ask, want)
        except llm.LLMError:
            return ""
        new = re.sub(r"\n{2,}", "\n", new.replace("<<<", "").replace(">>>", "")).strip()
        have = len(new.split())
        if not new or have > 2.2 * want + 25 or (want >= 20 and have < 0.4 * want):
            return ""   # it wrote the whole part again, or next to nothing
        rest = "\n".join(p for k, p in enumerate(paras) if k != i)
        fresh = self._drop_inner_repeats(self._drop_repeats(new, rest), rest).strip() if rest.strip() else new
        if len(fresh.split()) < 0.6 * have:
            return ""   # it copied the paragraphs around it
        # what it did copy from its neighbours is left out, and its own line breaks become real paragraph breaks
        return re.sub(r"\n+", "\n\n", fresh).strip()

    def _repair_paragraphs(self, user_msg, text, prior, found=None):
        """Write only the paragraphs that hold a mistake again, each with its mistake named; everything else stays
        word for word. found: {paragraph index: [reasons]} from the second reading; otherwise the program's own
        findings. A paragraph is replaced only by a version the program finds nothing wrong with; if none comes, it
        is left for the cuts at the end, as before."""
        n = self.rules.get("narration", {})
        tries, cap = int(n.get("repair_tries", 2)), int(n.get("repair_paragraphs_max", 6))
        paras = text.split("\n")
        if found is None:
            bad = self._bad_sentences(text, prior)
            found = {}
            for i, p in enumerate(paras):
                why = list(dict.fromkeys(w for sent, w in bad.items() if sent in p))
                if p.strip() and why:
                    found[i] = why
        if not found or tries <= 0:
            return text
        todo = sorted(found)[:cap]
        if self.progress:
            self.progress(f"writing {len(todo)} paragraph{'s' if len(todo) != 1 else ''} again (the rest stays as it is)")
        fixed = 0
        for i in todo:
            reasons = list(found[i])[:4]
            for _ in range(tries):
                new = self._rewrite_paragraph(user_msg, paras, i, reasons)
                if not new:
                    continue
                trial = "\n".join(paras[:i] + [new] + paras[i + 1:])
                still = [w for sent, w in self._bad_sentences(trial, prior).items() if sent in new]
                if still:
                    reasons = list(dict.fromkeys(still + reasons))[:4]   # tell it what the new version got wrong
                    continue
                paras[i] = new
                fixed += 1
                break
        if self.progress and fixed < len(todo):
            self.progress(f"{len(todo) - fixed} of them still came back wrong: only the wrong sentences get cut")
        return re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip()

    def _timeline(self):
        """How everyone is placed when the beat starts and when it ends, and which grips are still on: the first
        thing a second reading is given, so a fighter lying down early in the passage isn't called wrong because
        she is standing by the end."""
        ps, pe = getattr(self, "posture_start", {}) or {}, getattr(self, "posture_end", {}) or {}
        rows = []
        for who, end in pe.items():
            start = ps.get(who) or end
            rows.append(f"- {who}: {end} from start to end" if start == end else
                        f"- {who}: STARTS the beat {start}; ENDS it {end} (so the passage shows her both ways, in that "
                        f"order: both are correct)")
        for att, dfn, part, with_ in getattr(self, "grips", None) or []:
            rows.append(f"- STILL ON when the beat ends: {poss(att)} grip on {poss(dfn)} {part}"
                        + (f" ({with_})" if with_ else ""))
        return "TIMELINE (certain):\n" + "\n".join(rows) if rows else ""

    def _reader_gate(self, kind, sent, whos):
        """A second reading's finding only counts when the sentence it quotes really says something of that kind,
        and what the program itself knows doesn't already show the sentence to be right. Returns "" to accept, or
        why it is set aside."""
        k = kind.lower()
        on_ground = set(self.on_ground) | set(getattr(self, "_landed", set())) | set(getattr(self, "_slammed", set()))
        ps, pe = getattr(self, "posture_start", {}) or {}, getattr(self, "posture_end", {}) or {}

        def up_at(text_):
            return bool(text_) and not str(text_).upper().startswith(("ON THE GROUND", "OUT OF"))
        if getattr(self, "_calm_beat", False) and "posture" in k:
            return "someone goes out or the fight is over this beat: bodies lie where they fell"
        if "posture" in k:
            if not whos:
                return "it isn't clear which fighter the sentence is about"
            lying = bool(GROUNDED.search(sent) or FALL.search(sent) or COLLAPSE.search(sent) or SLID_DOWN.search(sent))
            m_down, m_up = DOWNISH.search(sent), UPISH.search(sent)
            standing = bool(STANDING.search(sent)) and not STAND_OVER.search(sent)
            mixed = False
            for w in whos:
                down_some = w in on_ground or not up_at(ps.get(w, pe.get(w))) or not up_at(pe.get(w))
                up_some = up_at(ps.get(w, pe.get(w))) or up_at(pe.get(w)) or w == getattr(self, "_getup_who", None)
                if down_some and up_some:
                    mixed = True
                    continue
                if not down_some and m_down and not (standing and not lying) \
                        and not _NOT_REALLY.search(sent[:m_down.start()]):
                    return ""      # she is on her feet from start to end, and the sentence may lay her down
                if not up_some and m_up and not lying and not _NOT_REALLY.search(sent[:m_up.start()]):
                    return ""      # she is on the ground from start to end, and the sentence may stand her up
            if getattr(self, "_pin_holds", None) and ESCAPE_WORDS.search(sent):
                return ""
            return ("she is both on the ground and on her feet in the course of this beat" if mixed else
                    "the sentence says nothing that puts her the wrong way up")
        if "grip" in k:
            return "" if any(x[4] == sent for x in self._grip_released_lines(" ".join(whos) + ". " + sent)) else \
                "no grip that stays on is let go in that sentence"
        if "clock" in k:
            window = getattr(self, "_time_window", None)
            if not window:
                return "" if (_TIME_MARK.search(sent) or _COUNTDOWN.search(sent) or _REMAINING.search(sent)) else \
                    "the sentence gives no time"
            return "" if (_time_overrun(sent, *window) or _REMAINING.search(sent) or _counts_down(sent)) else \
                "the time in that sentence is inside this beat's seconds"
        if "not listed" in k:
            m = ATTACK_SAID.search(sent)
            if not m:
                return "the sentence shows no attack or wound"
            if _NOT_REALLY.search(sent[:m.start()]) or MISSED.search(sent):
                return "the attack in that sentence doesn't land"
            low = sent.lower()
            if any(_mentions(low, p) for parts in (getattr(self, "_parts_now", None) or {}).values() for p in parts):
                return "the sentence is about a part that IS hit this beat"
            return ""
        if "body part" in k:
            low = sent.lower()
            now = getattr(self, "_parts_now", None) or {}
            for parts in now.values():
                for p in parts:
                    side = re.match(r"(left|right) (.+)", p)
                    if not side:
                        continue
                    other = ("right " if side.group(1) == "left" else "left ") + side.group(2)
                    if other in low and p not in low and other not in parts and ATTACK_SAID.search(sent):
                        return ""   # the blow is on one side, the sentence puts it on the other
            return "the sentence doesn't put a listed hit on the other side"
        if "weapon" in k or "attacker" in k:
            if not ATTACK_SAID.search(sent):
                return "the sentence shows no attack"
            if MISSED.search(sent) or _NOT_REALLY.search(sent[:ATTACK_SAID.search(sent).start()]):
                return "the attack in that sentence doesn't land"
            named = {w for w, rx in WEAPONS if re.search(rx, sent, re.I)}
            ok = getattr(self, "_weapons_ok", None) or set()
            if not named:
                return "the sentence names no claws, teeth, tail or horn"
            if not ok or named & ok or getattr(self, "_pin_beat", False):
                return "that weapon is in this beat (or the move names none)"
            return ""
        if "worse" in k:
            m = WORSE_SAID.search(sent)
            if not m:
                return "the sentence breaks or disables nothing"
            if re.search(r"\b(not|never|no|didn't|hadn't|wasn't|almost|nearly|as if|as though|like|felt like)\b[^.!?]{0,40}$",
                         sent[:m.start()], re.I):
                return "the sentence says it did NOT break, or only felt that way"
            if m.group(0).lower().startswith(("broke", "break", "gave")) and GRIP_OFF.search(sent):
                return "it is a grip that breaks in that sentence, not a bone (the grip check covers it)"
            if any(_mentions_exact(sent.lower(), p) for p in getattr(self, "breakable", ())):
                return "that part really is that badly hurt"
            return ""
        return "the program checks that itself"

    def _reader_confirm(self, facts, para, sent, kind, says):
        """One more look at a single finding, asked the other way round ('is this fine?'). True = still wrong."""
        n = self.rules.get("narration", {})
        try:
            raw = llm.chat(n.get("reader_model") or self.model,
                           [{"role": "system", "content": CONFIRM_PROMPT},
                            {"role": "user", "content": f"FACTS:\n{facts[:9000]}\n\nTHE PARAGRAPH IT IS IN:\n{para}\n\n"
                                                        f"THE SENTENCE: \"{sent}\"\n\nTHE CHECKER'S CLAIM ({kind}): {says}\n\n"
                                                        f"First say in one line what the sentence itself states, then "
                                                        f"give the verdict, as JSON."}],
                           host=self.host, temperature=0.1, fmt=CONFIRM_SCHEMA,
                           num_ctx=n.get("context_window", 8192), num_predict=160,
                           extra_options={"num_gpu": 0} if n.get("reader_model") and n.get("reader_on_cpu") else None)
            return str(json.loads(raw).get("verdict", "")).lower() == "contradiction"
        except (llm.LLMError, ValueError, AttributeError, TypeError):
            return False   # no clear answer: the sentence stands

    def _second_reading(self, user_msg, text, prior):
        """The model reads the passage back against the facts and lists contradictions, in its own words: this
        catches phrasings no pattern has been written for. Its word alone changes nothing. A finding counts only
        if it is marked sure, quotes a sentence that is really there, states an opposite fact (not a remark), passes
        the program's own look at that sentence (_reader_gate), and is confirmed when asked a second time. What is
        left is only ever REWRITTEN (a paragraph, checked by the program afterwards), never cut on its say-so.
        narration.reader_check turns it off; narration.reader_model names a different model to do the reading."""
        n = self.rules.get("narration", {})
        facts = getattr(self, "_facts", None)
        if not n.get("reader_check", True) or not facts or len(text.split()) < 25:
            return text
        facts = (self._timeline() + "\n\n" + facts).strip()
        paras = text.split("\n")
        index = [i for i, p in enumerate(paras) if p.strip()]
        numbered = "\n\n".join(f"[{k}] {paras[i]}" for k, i in enumerate(index, start=1))
        if self.progress:
            self.progress("second reading: checking the passage against the facts")
        try:
            raw = llm.chat(n.get("reader_model") or self.model,
                           [{"role": "system", "content": READER_PROMPT},
                            {"role": "user", "content": f"FACTS:\n{facts[:9000]}\n\nPASSAGE (numbered paragraphs):\n"
                                                        f"{numbered}\n\nList the contradictions as JSON."}],
                           host=self.host, temperature=0.1, fmt=READER_SCHEMA,
                           num_ctx=n.get("context_window", 8192), num_predict=450,
                           # reader_on_cpu: keep the reading model in system memory, so the narrator stays loaded
                           # on the graphics card instead of being swapped out for it every part
                           extra_options={"num_gpu": 0} if n.get("reader_model") and n.get("reader_on_cpu") else None)
            problems = json.loads(raw).get("problems") or []
        except (llm.LLMError, ValueError, AttributeError, TypeError):
            return text   # no answer, or not the form asked for: the passage stands as it is

        def norm(x):
            return WHITESPACE.sub(" ", re.sub(r"[^\w\s]", "", str(x).lower())).strip()
        rows = self._said(text) if self.strengths else []
        found, shown, aside = {}, [], []
        cap = int(n.get("reader_max_fixes", 3))
        for p in problems if isinstance(problems, list) else []:
            if not isinstance(p, dict):
                continue
            quoted = " ".join(str(p.get("sentence") or "").split())
            says = " ".join(str(p.get("facts_say") or "").split())[:200]
            kind = str(p.get("kind") or "").split(" (")[0]
            brief = f"\"{quoted[:70]}\""
            if str(p.get("sure", "sure")).lower() != "sure":
                aside.append(f"{brief} (it wasn't sure)")
                continue
            quote = norm(quoted)
            if len(quote.split()) < 3 or not says:
                continue
            probe = " ".join(quote.split()[:7])
            # it has to be quoting something that is really in the passage (and that says where it is)
            where = next((i for i in index if probe in norm(paras[i])), None)
            if where is None:
                aside.append(f"{brief} (not a sentence of the passage)")
                continue
            if READER_REMARK.search(says):
                aside.append(f"{brief} (a remark, not an opposite fact: {says[:70]})")
                continue
            # the sentence as the passage has it, and who it is about
            row = next(((x, w) for x, w, _ in rows if probe in norm(x)), None)
            sent = row[0] if row else quoted
            whos = [w for w in (row[1] if row else []) if w]
            why_not = self._reader_gate(kind or "", sent, whos) if n.get("reader_gate", True) else ""
            if why_not:
                aside.append(f"{brief} ({why_not})")
                continue
            if len(found) >= cap and where not in found:
                continue
            if n.get("reader_confirm", False) and not self._reader_confirm(facts, paras[where], sent, kind, says):
                aside.append(f"{brief} (on a second look it is fine)")
                continue
            found.setdefault(where, []).append(
                f"a second reading says \"{quoted[:160]}\" contradicts what happened"
                + (f" ({kind})" if kind else "") + f"; the facts: {says}")
            shown.append(f"[{kind or 'contradiction'}] \"{quoted[:90]}\" → {says}")
        if self.progress:
            if aside:
                self.progress("second reading, set aside (left as written): " + " | ".join(aside[:4]))
            self.progress("second reading: nothing wrong" if not found else
                          "second reading found: " + " | ".join(shown[:cap]))
        if not found:
            return text
        return self._repair_paragraphs(user_msg, text, prior, found=found)

    def _tokens(self, text):
        # characters per token, learned from what Ollama actually counts (starts cautious)
        return len(text) / getattr(self, "_cpt", 3.3)

    def _learn_ratio(self, chars, num_ctx, answer):
        """Calibrate characters-per-token from Ollama's own count of the last prompt. Counts that look cut short
        (a prompt that overflowed, or a reused cache) are ignored."""
        got = llm.last_prompt_tokens
        if not got or got >= num_ctx - answer - 50:
            return
        ratio = chars / got
        if 2.6 <= ratio <= 4.6:
            self._cpt = ratio if not hasattr(self, "_cpt_seen") else 0.7 * self._cpt + 0.3 * ratio
            self._cpt = min(self._cpt, 4.2) * 0.97  # a small safety margin
            self._cpt_seen = True

    @staticmethod
    def _shorten_block(msg, start_marker, end_marker, keep_chars, from_front=True):
        """Shorten the text between two markers to its last (or first) keep_chars, at a paragraph boundary."""
        i = msg.find(start_marker)
        if i < 0:
            return msg
        i += len(start_marker)
        j = msg.find(end_marker, i)
        if j < 0:
            return msg
        block = msg[i:j]
        if len(block) <= keep_chars:
            return msg
        if keep_chars <= 0:
            short = "(earlier story trimmed to fit the model's memory)"
        else:
            short = block[-keep_chars:] if from_front else block[:keep_chars]
            nl = short.find("\n")
            if from_front and 0 <= nl < keep_chars // 2:
                short = short[nl + 1:]
            short = "(...)\n" + short
        return msg[:i] + short + msg[j:]

    def _fit(self, user_msg, words):
        """Make sure the prompt plus the answer fit the model's memory (context_window). If not, shorten, in
        order: the recap of earlier beats, the start of this beat's earlier parts, then the style sample.
        This beat's events, the fighters, their conditions, and the rules are never cut."""
        n = self.rules.get("narration", {})
        limit = int(n.get("context_window", 8192)) - 150
        answer = int(words * 1.8) + 80
        system = self._system()
        steps = [("PREVIOUS BEATS (already told; context only, do NOT retell):\n", "\n\n", 900, True),
                 ("PREVIOUS BEATS (already told; context only, do NOT retell):\n", "\n\n", 0, True),
                 ("never repeat or rephrase it):\n<<<\n", "\n>>>", 1500, True),
                 ("never repeat or rephrase it):\n<<<\n", "\n>>>", 700, True)]
        trimmed = False
        for start, end, keep, front in steps:
            if self._tokens(system) + self._tokens(user_msg) + answer <= limit:
                break
            user_msg = self._shorten_block(user_msg, start, end, keep, front)
            trimmed = True
        for chars in (2500, 1500, 0):
            if self._tokens(system) + self._tokens(user_msg) + answer <= limit:
                break
            system = self._system(sample_chars=chars)
            trimmed = True
        for start, end, keep, front in [("never repeat or rephrase it):\n<<<\n", "\n>>>", 300, True)]:
            if self._tokens(system) + self._tokens(user_msg) + answer <= limit:
                break
            user_msg = self._shorten_block(user_msg, start, end, keep, front)
            trimmed = True
        if trimmed and self.progress:
            over = self._tokens(system) + self._tokens(user_msg) + answer - limit
            self.progress("trimmed older story context to fit the model's memory"
                          + (" (still tight: consider raising context_window)" if over > 0 else ""))
        return system, user_msg

    def _generate(self, user_msg, words):
        n = self.rules.get("narration", {})
        system, user_msg = self._fit(user_msg, words)
        out = llm.chat(self.model,
                       [{"role": "system", "content": system},
                        {"role": "user", "content": user_msg}],
                       host=self.host,
                       temperature=n.get("temperature", 0.8),
                       num_ctx=n.get("context_window", 8192),
                       num_predict=int(words * 1.8) + 80,
                       extra_options={k: n.get(k) for k in ("repeat_penalty", "repeat_last_n", "top_p", "min_p")})
        self._learn_ratio(len(system) + len(user_msg), int(n.get("context_window", 8192)), int(words * 1.8) + 80)
        return _clean(out, cut_off={"length": True, "stop": False}.get(getattr(llm, "last_done_reason", None)),
                      open_end=bool(getattr(self, "_open_end", False)))

    def intro(self, scene, fighter_notes):
        """The arena and the fighters arriving, before anyone attacks."""
        words = int(self.rules.get("narration", {}).get("words_per_beat", 500) * 0.7)
        self._calm_beat = True  # nothing to check posture against yet
        self._time_window, self._no_clock, self._important = None, False, False
        self._pin_beat = False
        self._facts = None
        self._pin_holds = None
        self._weapons_ok, self._attackers, self._no_getup = None, set(), set()
        self.fight_seen = set()
        self._sample_want, self._sample_rounds = ["opening"], {}
        if self.progress:
            self.progress("narrator is setting the scene")
        msg = (f"SCENE: {scene}\n\nFIGHTERS:\n{fighter_notes}\n\n"
               f"Write the OPENING of the battle in about {words} words: describe the arena vividly (sound, light, "
               f"smell, what the ground is), then each fighter arriving or taking position, one at a time, showing their "
               f"body, personality, and how they size up the others. End on the tense moment just before the first "
               f"move. NO attacks happen yet and nobody is hurt.")
        B = self._blocks()
        if B.enabled and B.entries:
            B.next_turn()
            msg += self._blocks_note([f"  - for the opening: {p}" for p in B.pick("opening", 3)])
        return self._call(msg, words)

    def look(self, condition, fighter_notes, scene, story_so_far, who=None):
        """Describe the scene as it stands right now, without advancing the fight."""
        words = int(self.rules.get("narration", {}).get("words_per_pass", 300))
        self._time_window, self._no_clock, self._important = None, not ("PIN:" in condition), False
        self._pin_beat = "PIN:" in condition
        self._must_parts, self._must_struggle = [], None
        self._landed, self._calm_beat = set(), False  # a still snapshot: nobody falls, postures are as the engine has them
        self._slammed, self._charge_beat, self._one_strike = set(), False, None
        self._weapons_ok, self._attackers, self._no_getup = None, set(), set()
        self._facts = None
        self._pin_holds = None
        if self.progress:
            self.progress("narrator is looking around")
        focus = f"Focus on {who}, with the others briefly placed around them." if who else "Cover every fighter."
        msg = (f"SCENE: {scene}\n\nFIGHTERS:\n{fighter_notes}\n\n"
               f"CURRENT CONDITION (right now):\n{condition}\n\n"
               f"PREVIOUS BEATS (context only):\n{_tail(story_so_far, 1500) or '(nothing yet)'}\n\n"
               f"Write a still snapshot of this exact moment in about {words} words, present in the story's past tense. "
               f"NOTHING HAPPENS: no attacks, no movement beyond breathing and small shifts of weight. {focus} For each "
               f"fighter: exactly where they are and how they are positioned (from POSITIONS), how they hold "
               f"themselves overall (from their OVERALL strength), their breathing, which parts they favor and how "
               f"those injuries look (bruising, swelling, trembling, matted fur or dulled scales), their expression "
               f"and one brief thought in italics. Mention any pin or hold in progress. Use only what CURRENT "
               f"CONDITION and POSITIONS say.")
        return self._call(msg, words)

    @staticmethod
    def _drop_repeats(text, earlier):
        """Remove sentences that already appeared in recent beats (the model sometimes recycles paragraphs)."""
        def key(s):
            return WHITESPACE.sub(" ", re.sub(r"[^\w\s]", "", s.lower())).strip()
        earlier_s = [key(s) for s in re.split(r"(?<=[.!?…])\s+|\n+", earlier or "") if len(key(s)) > 15]
        seen = set(earlier_s)
        word_sets = [set(k.split()) for k in earlier_s if len(k.split()) >= 7]

        def near_copy(k):  # reworded by a word or two: 75%+ of the same words
            w = set(k.split())
            return len(w) >= 7 and any(len(w & e) / len(w | e) >= 0.75 for e in word_sets)

        paras = []
        for para in text.split("\n"):
            kept = [s for s in re.split(r"(?<=[.!?…])\s+", para)
                    if not (len(key(s)) > 15 and (key(s) in seen or near_copy(key(s))))]
            paras.append(" ".join(kept).strip())
        # an opening that echoes what was just said: "And then—" again, "The blade struck." after "And the blade
        # struck.", or last beat's closing thoughts ("Good." / "It held.") standing at the top as loose lines
        every = {key(x) for x in re.split(r"(?<=[.!?…])\s+|\n+", earlier or "")} - {""}
        small = [set(k.split()) for k in every if len(k.split()) <= 9]

        def echo(x):
            k = key(x)
            w = set(k.split())
            return (not k or k in every
                    or any(len(w & e) >= 3 and len(w & e) / len(w | e) >= 0.5 for e in small))
        cut = 0
        for i, para in enumerate(paras):
            if not para:
                continue
            if cut < 4 and earlier and len(para.split()) <= 9 and all(echo(x) for x in _SENT.split(para) if x):
                paras[i], cut = "", cut + 1
                continue
            break
        out = re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip()
        return _drop_orphans(text, out) if out != (text or "").strip() else out

    @staticmethod
    def _drop_inner_repeats(text, earlier="", aliases=None):
        """A sentence the same passage has already used (word for word, nearly, or the same opening and half the
        same words: "Her tails didn't just squeeze; they locked..." twice) is told once. So is a short line used
        again as it stands ("The pin held. Firm. Unbreakable." three times; "The Buizel's jaw clenched tight." and
        then "Ripples' jaw clenched tight."). earlier: text that counts as already said (the paragraphs around a
        rewritten one). aliases: {"Buizel": "Ripples"}, so a species name and a fighter's name count as the same."""
        alias = {str(a).lower(): str(n).lower() for a, n in (aliases or {}).items()}

        def key(x):
            k = WHITESPACE.sub(" ", re.sub(r"[^\w\s]", "", x.lower().replace("’s", "").replace("'s", ""))).strip()
            if alias:
                k = " ".join(alias.get(w, w) for w in k.split() if not (w == "the" and alias))
            return k
        seen, paras, changed = [], [], False
        short_seen, para_seen = set(), set()
        for x in re.split(r"(?<=[.!?…])\s+|\n+", earlier or ""):
            w = key(x).split()
            if len(w) >= 6:
                seen.append((w, set(w)))
        for para in (text or "").split("\n"):
            kept = []
            pk = key(para)
            pw = pk.split()
            if 2 <= len(pw) <= 12 and (pk in para_seen or (len(pw) <= 4 and " ".join(sorted(pw)) in para_seen)
                                       or (len(pw) <= 6 and any(pk == k or pk.startswith(k + " ") for k in short_seen))):
                changed = True      # the whole short paragraph again ("The pin held. Firm. Unbreakable.")
                paras.append("")
                continue
            if 2 <= len(pw) <= 12:
                para_seen.update({pk, " ".join(sorted(pw))} if len(pw) <= 4 else {pk})
            for x in _SENT.split(para.strip()):
                if not x:
                    continue
                w = key(x).split()
                ws = set(w)
                if len(w) >= 6:
                    runs = {" ".join(w[i:i + 7]) for i in range(len(w) - 6)}
                    if any(w == w2 or len(ws & s2) / len(ws | s2) >= 0.75
                           or (w[:4] == w2[:4] and len(ws & s2) / len(ws | s2) >= 0.5)
                           # "Then the blast struck her muzzle full-force." / "Then the blast slammed into her muzzle."
                           or ([x for x in w if x != "the"][:2] == [x for x in w2 if x != "the"][:2]
                               and len(ws - {"the"}) >= 5 and len((ws & s2) - {"the"}) / len((ws | s2) - {"the"}) >= 0.5)
                           or (len(w2) >= 6 and w[1:6] == w2[1:6])   # the same clause after the subject
                           or (runs and any(r in " ".join(w2) for r in runs)) for w2, s2 in seen):
                        changed = True
                        continue
                    seen.append((w, ws))
                elif 3 <= len(w) <= 5 and not re.match(r"[\s*_\"“'‘]", x):
                    k = " ".join(w)
                    if k in short_seen:
                        changed = True   # a short line used a second time as it stands
                        continue
                    short_seen.add(k)
                kept.append(x)
            paras.append(" ".join(kept))
        if not changed:
            return text
        return _drop_orphans(text, re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip())

    def narrate(self, bundle, condition_summary, fighter_notes, scene, story_so_far):
        self._blocks().next_turn()
        raw = self._narrate(bundle, condition_summary, fighter_notes, scene, story_so_far)
        self._blocks().save()
        self._injury_prev = {k: list(v) for k, v in (getattr(self, "injury_log", None) or {}).items()}
        text = self._drop_repeats(raw, story_so_far)
        text = self._drop_inner_repeats(text, aliases=getattr(self, "aliases", None))
        text = self._drop_sample_copies(text)
        text = self._drop_seen(text)
        text = self._drop_said_repeats(text)
        text = self._keep_subjects(raw, text)   # a cut can take the sentence that said who "she" is
        text = self._ensure_faint(self._ensure_getup(self._top_up(text, story_so_far)))
        text = _balance_marks(text)  # cuts above can split a thought: re-pair its marks
        text = _drop_hanging_leadins(text)
        # "slammed into the wall—grunt—and the muscles spasmed": a reaction word from the notes left as a stage direction
        text = STAGE_WORD.sub(lambda m: " " if text[m.end():m.end() + 4].lower().startswith("and") else ", ", text)
        self.recent_reactions = (self.recent_reactions + [reactions_used(text)])[-3:]
        self.recent_lines = (self.recent_lines + said_lines(text))[-24:]
        self._beat_no += 1
        return self.pov_labels(text)

    def pov_labels(self, text):
        """Each part of the beat headed with whose side it is told from ("— Nocturne —", "— Both —"), so the reader
        always knows whose eyes these are. Put in after every check (they read the plain prose) and only where a part
        visibly starts; narration.pov_labels false turns them off."""
        marks = getattr(self, "_pov_marks", None) or []
        if not text or len(marks) < 2 or not self.rules.get("narration", {}).get("pov_labels", True):
            return text
        paras = text.split("\n\n")
        at, start = {}, 0
        for sents, who in marks:
            heads = [x[:60] for x in (sents if isinstance(sents, list) else [sents]) if x]
            # where this part starts: the paragraph with its first sentence (or its second or third, if the cleanup
            # took the first)
            j = next((k for h in heads for k in range(start, len(paras)) if h in paras[k]), None)
            if j is None:
                continue
            if j in at and at[j] != who:
                continue
            at[j], start = who, j + 1
        if not at:
            return text
        if 0 not in at:          # the first part's opening was cut: its label goes at the top all the same
            at[0] = marks[0][1]
        out, last = [], None
        for k, para in enumerate(paras):
            if k in at and at[k] != last:
                out.append(f"— {at[k]} —")
                last = at[k]
            out.append(para)
        return "\n\n".join(out)

    def _top_up(self, text, story_so_far):
        """A beat that came out much shorter than asked (usually because copied or repeated lines were removed)
        gets one more pass that continues it with new detail, so cleanup never costs length."""
        n = self.rules.get("narration", {})
        target = int(getattr(self, "_last_words", 0) or 0)
        floor = float(n.get("top_up_below", 0.55))
        have = len((text or "").split())
        context = getattr(self, "_last_context", "")
        if not text or not target or not context or floor <= 0 or have >= floor * target:
            return text
        need = max(120, target - have)
        if self.progress:
            self.progress(f"the beat came out short ({have} of ~{target} words) after removing repeats: writing more")
        ask = (f"The beat so far (already written; never repeat or rephrase it):\n<<<\n{_tail(text, 3000)}\n>>>\n\n"
               f"Continue this beat with about {need} more words. Everything listed above has ALREADY been shown: do "
               f"not show any hit, squeeze, or event again, and reuse no sentence from this beat or earlier ones. Go "
               f"deeper with NEW detail instead: one specific body part and exactly how it feels now, breathing, "
               f"small shifts of weight or grip, what each fighter notices about the other, the place (its sounds, its cold or heat, "
               f"sound, light), a thought that hasn't been thought yet. Stay inside this beat's moment. {DETAIL}")
        try:
            more = self._call(context + ask, need, coverage=False, prior=text)
        except llm.LLMError:
            return text
        more = self._drop_said_repeats(self._drop_seen(self._drop_repeats(more, (story_so_far or "") + "\n" + text)))
        self.recent_lines = (self.recent_lines + said_lines(text))[-24:]
        return (text + "\n\n" + more).strip() if more else text

    def _drop_said_repeats(self, text):
        """Remove thoughts and spoken lines already used in recent beats (or earlier in this one), like a third
        '*Still breathing. Good.*'. The rest of the paragraph stays."""
        seen = {_norm_line(x) for x in self.recent_lines if len(_norm_line(x)) > 3}
        out = text
        for rx in (_THOUGHT, _SPEECH):
            for m in list(rx.finditer(text)):
                key = _norm_line(m.group(1))
                if len(key) <= (3 if rx is _SPEECH else 6):
                    continue
                if key in seen:  # also take the "she thought, ..." tag that hung off it
                    out = re.sub(re.escape(m.group(0)) + r"(\s*(?:she|he|it|they)\s+(?:thought|said|muttered|whispered|"
                                 r"growled|hissed|snarled|gasped|added|told herself)\b[^.!?*\"“]*[.!?])?", "", out, count=1)
                seen.add(key)
        if out == text:
            return text
        paras = [re.sub(r"\s{2,}", " ", p).strip() for p in out.split("\n")]
        paras = [p for p in paras if p.strip(" .,;:—-*\"“”") or not p]
        return _drop_orphans(text, re.sub(r"\n{3,}", "\n\n", "\n".join(paras)).strip())

    DEV_SELL_ANY = [
        "THE DELAY: one heartbeat where nothing hurts at all and she almost thinks it missed, then it arrives all at once",
        "THE SILENCE: she goes completely quiet, no sound at all, and the quiet is worse than any cry; the attacker hears it",
        "THE BODY BETRAYS HER: a knee dips, a paw opens, the tail drops, without her permission, and she has to drag it back",
        "THE WRONGNESS: not just more pain but a different KIND, deep and wrong, something she has no word for yet",
        "THE ATTACKER'S SIDE OF IT: she feels it land differently through her own body: the give, the absence of resistance",
        "THE STARE: for one heartbeat they look at each other and both of them know exactly what just happened",
        "THE PLACE ANSWERS: the sound of it in this place (its echo, the water shivering, dust sifting down) marks it",
        "THE BREATH: the air goes out of her and does not come back for one, two, three heartbeats",
        "SLOW TIME: the instant of contact stretched out, every detail of it, then time snapping back",
        "THE TELL SHE CAN'T HIDE: her ears, fins, ruff or tail react in a way that tells the attacker everything",
        "THE OLD HURT DWARFED: every earlier blow on her suddenly feels small next to this one",
        "THE FIGHT CHANGES: from now on her stance, her distance and her eyes are different, and both of them see it",
    ]
    DEV_SELL_BAND = {
        "fresh": ["DISBELIEF: she is fresh and strong, and nothing has hurt her like this yet; the shock is that it COULD",
                  "STUNG PRIDE: a sharp cry she is furious at herself for, and then a new, hard wariness",
                  "THE REALISATION: she suddenly understands what her opponent can do to her, and it changes how she stands"],
        "worn": ["THE RESERVE SPENT: the strength she was saving to get through the next few blows goes all at once",
                 "THE GRIP SLIPS: the hold she has kept on her pain all fight loosens, and some of it gets out",
                 "THE FOLD: her body starts to fold round it before she catches herself, and catching herself costs her"],
        "spent": ["NOTHING TO BUFFER IT: there is no strength left to take it with; it goes straight through her",
                  "THE NARROWING: the world shrinks to the hurt and the next breath, and the edges go grey",
                  "THE BREAK IN HER: the scream, or the frightening silence where a scream should be, and shaking that won't stop"],
    }
    DEV_REACT = {
        "fresh": ("her reaction is clear and real but sized to someone still strong: shock, a sharp cry or a hiss she "
                  "can't stop, a stagger, a change in her eyes and her stance. A GOOD reaction, not a breakdown: no "
                  "screaming, no collapse, and she is steady again before long, but different"),
        "worn": ("her reaction is bigger than anything before it: the hold she has kept on her pain slips, a cry that "
                 "gets away from her, her body folding round it before she can stop it"),
        "spent": ("her reaction is the rawest of the fight: there is nothing left to hold it in with (the scream, or the "
                  "frightening silence, and shaking she can't stop)"),
    }
    DEV_SELL_PART = {
        "light": "the part itself isn't ruined (yet): the severity is in the SHOCK, the force, the stagger, the way it rattles her whole body",
        "hurt": "the part was already hurting and is now far worse: it stops working properly, and every use of it will remind her",
        "ruined": "the part is ruined now: it is the centre of everything, and her whole body arranges itself round protecting it",
    }

    def _dev_untouched(self, a):
        """Was the part a devastating blow landed on untouched before it (under 'very painful')?"""
        mine = [h for h in a.get("hits") or [] if h.get("devastating")]
        return bool(mine) and float(mine[0].get("damage_before", 0)) < 90

    def _dev_bands(self, a):
        """(health band, part band) for a devastating hit: fresh/worn/spent and light/hurt/ruined."""
        mine = [h for h in a.get("hits") or [] if h.get("devastating")] or list(a.get("hits") or [])
        top = max(mine, key=lambda h: h.get("damage_after", 0), default={})
        dmg = float(top.get("damage_after", 0))
        part = "ruined" if dmg >= 300 else "hurt" if dmg >= 90 else "light"
        mx, hp = top.get("max_health"), top.get("health_after", top.get("health_before"))
        left = 100.0 * float(hp) / float(mx) if mx and hp is not None else float(
            (getattr(self, "strengths", None) or {}).get(a.get("defender"), 100))
        return ("fresh" if left >= 60 else "worn" if left >= 30 else "spent"), part

    OPENING_WORDS = {"caught flinching": "still frozen in her flinch", "dazed, slow to react": "still dazed",
                     "caught off balance": "still off balance", "doubled over in pain": "still doubled over",
                     "held, can't cover up": "held, with nothing free to cover herself",
                     "down, nowhere to roll with it": "down, with nowhere to roll"}

    def _opening_line(self, a):
        """An attack thrown INTO an opening a status left (the engine's caught-open bonus): say that it is."""
        ex = [lbl for lbl, _ in ((a.get("move") or {}).get("extras") or [])]
        hit = next((self.OPENING_WORDS[x] for x in ex if x in self.OPENING_WORDS), None)
        if not hit or not a.get("hits"):
            return []
        return [f"  - THE OPENING: {a['defender']} is {hit}, and {a['attacker']} has seen it: this blow goes straight "
                f"into it. Show {a['defender']} trying to cover it and being too late, and the blow landing harder "
                f"for it."]

    def _anticipation_line(self, a):
        """A blow coming at a part that is already soft or badly hurt: she sees it coming and flinches before it lands
        (turning it away, a limb snatched in), and the attacker sees her protecting it. Not when she couldn't see it
        coming (a feint she bit on, caught in the air, pinned, asleep)."""
        hits = [h for h in a.get("hits") or [] if h.get("defender", a.get("defender")) == a.get("defender")]
        if not hits or a.get("juggle") or (a.get("feint") or {}).get("bit") or a.get("environment"):
            return []
        dfn = a.get("defender")
        if dfn in (getattr(self, "pinned_now", None) or ()) or dfn in (getattr(self, "cant_act", None) or ()):
            return []
        h = hits[0]
        soft = float(h.get("res_before", 100)) <= 60
        hurt = float(h.get("damage_before", 0)) >= 150
        if not (soft or hurt):
            return []
        why = "already badly hurt" if hurt else "gone soft"
        return [f"  - She SEES it coming at her {h['part'].lower()} ({why}) and flinches before it lands: the part "
                f"snatched in or turned away a fraction too late, her whole body bracing for it. {a.get('attacker')} "
                f"sees her protecting it, and knows exactly what that means."]

    def _devastating_line(self, a):
        """A blow (or a landing) that lands devastatingly: the story has to make the severity believable."""
        dv = a.get("devastating")
        if not dv:
            return []
        mine = [h for h in a.get("hits") or [] if h.get("devastating")]
        top = max(mine, key=lambda h: h.get("damage_after", 0), default=None)
        strong = bool(top and top.get("damage_after", 0) < 150 and top.get("max_health")
                      and float(top.get("health_after", top.get("health_before", 0))) >= 0.6 * float(top["max_health"]))
        size = (" TRUE TO SIZE: she still has most of her strength and the part is not ruined, so it is a deep shock and "
                "a sharp cry she can't stop, NOT a scream; she reels and fights her way back to steady."
                if strong else "")
        hb, pb = self._dev_bands(a)
        if (pb == "light" or self._dev_untouched(a)) and hb == "spent":
            hb = "worn"      # an untouched part: worn-down shock, not the rawest breakdown
        ways = random.sample(self.DEV_SELL_ANY, 2) + [random.choice(self.DEV_SELL_BAND[hb])]
        size += (f" WAYS TO SELL IT (use them, in your own words): " + "; ".join(ways) + f". And {self.DEV_SELL_PART[pb]}.")
        return [f"  - A DEVASTATING {'LANDING' if dv.get('reason') == 'ground' else 'BLOW'} (×{dv['mult']}, far worse "
                f"than this would normally be): the reason is {dv['why']}. MAKE THE SEVERITY BELIEVABLE: show exactly "
                f"why this one is so much worse than anything like it before (the angle, the timing, where she was, what "
                f"was already hurt there), and give the impact and what it does to her body real room. SELL IT IN "
                f"BOTH OF THEM: {self.DEV_REACT['fresh' if self._dev_bands(a)[0] == 'fresh' and (self._dev_bands(a)[1] == 'light' or self._dev_untouched(a)) else 'worn' if (self._dev_bands(a)[1] == 'light' or self._dev_untouched(a)) else self._dev_bands(a)[0]]}; her thoughts show how bad it is; the attacker FEELS "
                f"it land differently, knows at once that this one went in deep, and her thoughts show it (surprise, "
                f"savage satisfaction, even a flicker of something else). It changes the fight; let both of them feel "
                f"that.{size} (The usual rules on bones and injuries still hold: the "
                f"severity is in the pain, the shock and the strength going out of her.)"]

    BAD_LEVELS = ("very painful", "excruciating", "devastated", "numb with shock")

    def _sound_note(self):
        """How this place carries sound (scenes.json acoustics), and how to tell the sounds the fighters make (every
        pained sound described: what kind, where from, pitch and shape; now and then written out as it sounds)."""
        ac = str((getattr(self, "scene_cfg", None) or {}).get("acoustics") or "").strip()
        out = f"SOUND IN THIS PLACE (for the sounds they make, and the ones they try to keep in): {ac}\n\n" if ac else ""
        cfg = (self.rules.get("narration") or {}).get("sounds") or {}
        if not cfg.get("enabled", True):
            return out
        voices = []
        for name in list((getattr(self, "strengths", None) or {}))[:4]:
            v = str((getattr(self, "voices", None) or {}).get(name) or "")
            bit = next((s.strip() for s in re.split(r"(?<=[.;])\s+", v)
                        if re.search(r"growl|hiss|chitter|squeak|bark|cr(?:y|ies)|whine|yelp|snarl|screech|chirp", s, re.I)), "")
            if bit:
                voices.append(f"{name}: {bit.rstrip('.;, ')}")
        how = {"always": "Every hit, grip or squeeze that hurts gets a sound out of her, even a small one held behind "
                          "her teeth, and the badly hurt places get loud ones.",
               "often": "Most hits that hurt get a sound out of her; the badly hurt places always do.",
               "sometimes": "Some hits get a sound out of her; others she takes in silence; the badly hurt places "
                            "always do.",
               "rarely": "She mostly keeps quiet: only the worst moments get a sound out of her."}.get(
            str(cfg.get("how_often", "always")), "")
        write = {"often": "Often (about every other sound) write the sound out as it sounds",
                 "sometimes": "Now and then (not every time) write the sound out as it sounds",
                 "rarely": "Once in a while write a sound out as it sounds",
                 "never": ""}.get(str(cfg.get("write_out", "often")), "")
        return out + ("SOUNDS THEY MAKE: " + how + " Never just 'a small sound' or 'a noise'. Every pained sound is "
                      "described: what it is (a hiss through the teeth, a whine high in the nose, a choked gasp, a yelp, a "
                      "growl ground out, a ragged cry that cracks in the middle), where it comes from (throat, chest, nose, "
                      "teeth), and its shape and pitch (short, cut off, dragged out, rising, wet, rasping). The worse it "
                      "hurts, the bigger and less controlled the sound."
                      + (f" {write}, as ONE italic word in the middle of a sentence, never in quotes and never ending a "
                         f"paragraph: *Hhk*, *Nngh*, *Hss*, *Ahh*, *Kh-hah*, *Yip*." if write else
                         " Describe the sounds; don't write them out.")
                      + " Sounds only: no words, no sobbing or weeping."
                      + (" Fit them to who makes them: " + "; ".join(voices) + "." if voices else "") + "\n\n")

    def _fading_thoughts_note(self):
        """A fighter who is fading (narration.fading_thoughts): on some beats her THOUGHTS come in fragments. Only her
        thoughts: the prose around them keeps its full detail."""
        cfg = (self.rules.get("narration") or {}).get("fading_thoughts") or {}
        if not cfg.get("enabled", True):
            return ""
        low = [w for w, st in (getattr(self, "strengths", None) or {}).items()
               if st is not None and st < float(cfg.get("below_strength", 20))
               and random.random() < float(cfg.get("chance", 0.4))]
        if not low:
            return ""
        return (f"FADING THOUGHTS: this beat, {' and '.join(low)} {'is' if len(low) == 1 else 'are'} fading, and "
                f"{'her' if len(low) == 1 else 'their'} italic thoughts come in fragments (a word or two, broken off). "
                f"ONLY the thoughts: the prose around them keeps its full detail, body, breath and sound.\n\n")

    def _camera_note(self, key):
        """How close this part is told (narration.camera): close in on one body, or wide on both and the place."""
        cfg = (self.rules.get("narration") or {}).get("camera") or {}
        if not cfg.get("enabled", True):
            return ""
        if key in ("dwell", "watch"):
            close = True
        else:
            close = random.random() >= float(cfg.get("wide_chance", 0.35))
        return ("\nCAMERA for this part: CLOSE. Stay tight on bodies: one paw, one breath, an eye, the fur over a "
                "wound, the smallest movements." if close else
                "\nCAMERA for this part: WIDE. Pull back: both bodies at once, the distance and angle between them, "
                "the place around them, then come in for the detail that matters.")

    def _callback_clause(self, who, part):
        """For the dwell part: the FIRST time this part was hurt, if that was a good while ago (narration.dwell
        callback_after beats): the old hurt and the new one meet, and she remembers it."""
        first = ((getattr(self, "first_hurt", None) or {}).get(who) or {}).get(part)
        now = int(getattr(self, "beat_now", 0) or 0)
        gap = int(((self.rules.get("narration") or {}).get("dwell") or {}).get("callback_after", 3))
        if not first or now - int(first[1]) < gap:
            return ""
        cause, when = first
        return (f"; a CALLBACK, in a line or two (a memory, not a retelling): this {part.lower()} was first hurt "
                f"{now - int(when)} beats ago, by {cause}, and she feels the old hurt and this new one meet in the same "
                f"place, and remembers that first moment")

    def _extra_moments(self, bundle, acts, pin_events):
        """After a blow (or a squeeze) on someone already badly hurt: extra parts of the beat that stay with what it
        DID, with nothing new happening. 'dwell': her side, slowed right down (the hurt settling in, breath, the sounds
        she tries to keep in, her thoughts). 'watch': the one who did it, studying her: every twitch, what each tells
        her. rules.json narration.dwell / narration.watch. Returns [{"key", "who", "focus", "words"}]."""
        n = self.rules.get("narration", {}) or {}
        dcfg, wcfg = n.get("dwell") or {}, n.get("watch") or {}
        if getattr(self, "_faint", None) or not acts or all(a.get("type") == "aftermath" for a in acts):
            return []
        pool = [x for x in getattr(self, "_linger_pool", []) if x[2] > 0]
        if not pool:
            return []
        out_now = set(getattr(self, "out_names", None) or ())
        also = bundle.get("also_this_beat") or []
        rising = {e.get("fighter") for e in also if e.get("type") == "get_up"}
        # the victim: whoever took the most this beat and is still in it
        by_victim = {}
        for who, part, dmg, label, kind in pool:
            by_victim.setdefault(who, []).append((dmg, part, label, kind))
        cands = [w for w in by_victim if w not in out_now and w in (self.strengths or {})]
        if not cands:
            return []
        v = max(cands, key=lambda w: sum(d for d, *_ in by_victim[w]))
        hits = sorted(by_victim[v], reverse=True)
        dmg, part, label, kind = max(hits, key=lambda x: (self.BAD_LEVELS.index(x[2]) if x[2] in self.BAD_LEVELS else -1, x[0]))
        strength = float(self.strengths.get(v, 100))
        # who did it: the attacker of a hit on her, or the one pinning or holding her
        holder = next((e.get("attacker") for e in pin_events if e.get("defender") == v and not e.get("complete")
                       and e.get("struggle") != "escape"), None) or next(
            (e.get("attacker") for e in also if e.get("type") == "hold_ongoing" and e.get("defender") == v), None)
        holding = bool(holder) or any(a.get("type") in ("hold_start", "grapple_start", "pin_start") and a.get("defender") == v
                                      for a in acts)
        by = holder or next((a.get("attacker") for a in acts if a.get("defender") == v and a.get("attacker")
                             and (a.get("hits") or a.get("type") in ("hold_start", "grapple_start", "pin_start"))), None)
        if not by or by == v or by in out_now:
            by = None
        devastated = any(a.get("devastating") for a in acts)
        badly = devastated or strength <= float(dcfg.get("max_strength", 55)) or label in tuple(
            dcfg.get("part_levels") or ("excruciating", "devastated", "numb with shock"))
        down = "GROUND" in str((getattr(self, "posture_end", None) or {}).get(v, "")).upper() or holding
        what = "squeeze" if kind == "pressure" else "blow"
        moments, beat_no = [], getattr(self, "_beat_no", 0)
        last = self.__dict__.setdefault("_moment_last", {})
        cool = int(n.get("moment_cooldown_beats", 1) or 0)

        def ready(key, cfg, ok):
            if not cfg.get("enabled", True) or not ok:
                return False
            if devastated:
                return True      # a devastating blow always gets its aftermath, cooldown or not
            if cool and beat_no - last.get(key, -99) <= cool:
                return False
            return random.random() < float(cfg.get("chance", 0.6))

        stays = (f"She stays exactly where and how CURRENT CONDITION has her: no new fall, no getting up"
                 f"{' (her getting up comes after this, as listed)' if v in rising else ''}, and nothing new is "
                 f"thrown, gripped or pressed by anyone.")
        if v not in rising and ready("dwell", dcfg, badly):
            last["dwell"] = beat_no
            raw = (getattr(self, "_raw_done", None) or {}).get(v)
            moments.append({"key": "dwell", "who": v, "part": part.lower(), "words": int(dcfg.get("words", 260)), "focus": (
                f"{poss(v)} side, AFTER the {what} (it has been told above: do not tell it landing again). Slow time "
                f"right down and stay inside her body with what that {what} to her {part.lower()} has DONE to her: the "
                f"hurt arriving, spreading and settling, the {part.lower()} first and then what it drags with it; what "
                f"her body does on its own (shaking, curling round it, a limb that won't answer, muscles jumping, cold "
                f"sweat under the fur); her breathing, heavy and ragged, catching where it hurts; the sounds she tries "
                f"to keep in (a whine through her teeth, a hiss, a cry she bites off) and whether she manages to"
                + (" (by now she mostly can't)" if raw is not None and raw >= 2 else "")
                + self._callback_clause(v, part)
                + f"; her thoughts, short and in her own voice; how she looks at {by or 'her opponent'} now. TRUE TO "
                f"SIZE: her {part.lower()} is now {label} and she has about {strength:.0f}% of her strength left; the "
                f"length comes from attention and detail, not from making it worse. No sobbing or weeping. "
                + (f"This part itself was NOT badly hurt before: the blow is one more weight on a body already worn "
                   f"down (the trembling, the breath, the old hurts flaring with the jolt), but the {part.lower()} "
                   f"itself only stings; keep its own reaction modest. " if label in ("minor", "sore", "hurting") else "")
                + stays)})
        watch_ok = bool(by) and (badly or (holding and down and (strength <= float(wcfg.get("hold_max_strength", 80))
                                                                or label in self.BAD_LEVELS)))
        if watch_ok and ready("watch", wcfg, True):
            last["watch"] = beat_no
            grip = (f" Her grip and her weight stay exactly as they are: she watches from where she holds her."
                    if holding else f" She does not close in or start anything: she watches from where she stands.")
            moments.append({"key": "watch", "who": by, "part": part.lower(), "words": int(wcfg.get("words", 220)), "focus": (
                f"{poss(by)} side: she WATCHES what she has just done to {v}.{grip} She studies {v} closely, the "
                f"way her own nature has her do it (cold, curious, hungry, wary, pitiless, almost gentle): every "
                f"twitch and flinch, where the shaking starts and how far it spreads, the breath hitching and "
                f"catching, the {part.lower()} that {v} guards or can't move, the sounds {v} is trying to swallow, "
                f"her eyes; and what each sign tells {by} about how badly {v} is hurt and what still works. Her own "
                f"breathing and her own injuries as she watches; what she thinks and what she plans (no attack "
                f"begins). The damage is what it is: {poss(v)} {part.lower()} is {label}, and she has about "
                f"{strength:.0f}% of her strength left. " + stays.replace("She stays", f"{v} stays"))})
        return moments

    def _linger(self):
        """Sometimes one blow (any kind, light ones too) gets a long, slow reaction. Returns (note, extra words)."""
        n = self.rules.get("narration", {})
        chance = float(n.get("linger_chance", 0.3) or 0)
        pool = [x for x in self._linger_pool if x[2] > 0]
        if not pool or random.random() >= chance or getattr(self, "_faint", None):
            return "", 0
        # heavier blows are likelier picks, but a light one can still be the moment that stops her
        who, part, dmg, label, kind = random.choices(pool, weights=[d + 15 for _, _, d, _, _ in pool])[0]
        extra = int(n.get("linger_words", 200))
        what = "squeeze" if kind == "pressure" else "blow"
        return (f"LINGER ON ONE MOMENT: slow time down on the {what} to {poss(who)} {part.lower()} and give her reaction "
                f"its own long passage (about {extra} extra words): the instant of contact, the sensation arriving and "
                f"spreading, her breath, what her body does, what she thinks, how she looks at her opponent, and how "
                f"she gathers herself. Keep it TRUE TO SIZE: this part is now {label}, so the length comes from detail "
                f"and attention, not from making it worse. A light blow can be a long, vivid moment of surprise, "
                f"sting, anger, or wounded pride without real agony; she does not fall or collapse unless this beat "
                f"says so. TELL THE {what.upper()} ONCE: stretch the one telling where it lands in the passage. Do not "
                f"come back at the end and land it a second time, and give her body no movement the beat doesn't "
                f"list (she isn't driven anywhere new and doesn't leave the ground).\n\n"), extra

    def _is_important(self, bundle):
        acts = bundle.get("actions") or []
        evs = bundle.get("also_this_beat", [])
        return bool(self._breaking
                    or any(a.get("type") in ("pin_start", "pin_forced", "eliminated") or a.get("environment") for a in acts)
                    or any(e["type"] == "adrenaline" or (e["type"] == "pin_progress" and
                                                         (e.get("complete") or e["struggle"] == "escape")) for e in evs))

    def _narrate(self, bundle, condition_summary, fighter_notes, scene, story_so_far):
        self._pov_marks = []      # a beat told in one part has no labels; nothing carries over from the last beat
        text = self._narrate_beat(bundle, condition_summary, fighter_notes, scene, story_so_far)
        if text and SWEAR.search(text):
            self._last_swear = self._beat_no  # keeps swearing rare across beats
        if text and self._spoken(text):
            self._last_spoken = self._beat_no  # keeps talking occasional across beats
        return text

    def _narrate_beat(self, bundle, condition_summary, fighter_notes, scene, story_so_far):
        n = self.rules.get("narration", {})
        words = int(n.get("words_per_beat", 500))
        pin_events = [e for e in bundle.get("also_this_beat", []) if e["type"] == "pin_progress"]
        forced = [a for a in (bundle.get("actions") or []) if a.get("type") == "pin_forced"]
        # with no fixed pin length (pin.fade) there is no clock to mark: any second written in the prose is wrong
        self._fade_pin = any(e.get("fade_mode") for e in pin_events + forced) or (
            bool(self.rules.get("pin", {}).get("fade", {}).get("enabled", True)) and "PIN:" in condition_summary)
        windows = [] if self._fade_pin else [(e["seconds_from"], e["seconds_to"]) for e in pin_events + forced]
        self._time_window = (min(w[0] for w in windows), max(w[1] for w in windows)) if windows else None
        self._no_clock = not windows
        acts = bundle.get("actions") or []
        self._pin_beat = bool(windows or "PIN:" in condition_summary or any(
            a.get("type") in ("pin_start", "pin_forced", "struggle_request") for a in acts))
        if pin_events and not any(e.get("complete") or e["struggle"] == "escape" for e in pin_events):
            # a pin beat covers only a few seconds: keep it to a moment, like one "Second N:" entry
            pc = self.rules.get("pin", {})
            words = min(words, max(80, int(pc.get("pin_words_per_second", 50) * pc.get("seconds_per_beat", 10))))
        context = (
            f"SCENE: {scene}\n\n"
            f"FIGHTERS:\n{fighter_notes}\n\n"
            f"CURRENT CONDITION (after this beat):\n{condition_summary}\n\n"
            f"PREVIOUS BEATS (already told; context only, do NOT retell):\n"
            f"{_tail(story_so_far, 1800) or '(none: this is the FIRST beat of the fight. Nobody has attacked anyone yet, so nobody has any earlier injuries, hits, or history to mention.)'}\n\n"
            + (f"EXTRA STYLE NOTE FOR THIS SESSION: {self.style}\n\n" if self.style else "")
            + f"WHAT HAPPENS IN THIS BEAT (the only events you may narrate):\n{self.describe(bundle)}\n\n"
        )
        context += self._story_note(bundle)
        context += self._leaned_note(story_so_far, bundle)
        # a fighter who is paralysed (or just shaking it off) still has sparks on her: that is no new element
        self._sparks_ok = bool(re.search(r"PARALY[SZ]ED|being paralyzed", context)) or bool(
            re.search(r"paraly[sz]ed", condition_summary, re.I))
        # a chain longer than three links needs room: every link still gets its telling
        long_chain = sum(1 for a in acts if a.get("chain")) - 3
        if long_chain > 0:
            words += int(n.get("words_per_extra_link", 70)) * long_chain
        # a turning point, or the end of the fight, is given more room; nothing is ever given less
        if n.get("story_state", True) and self._beat_weight(bundle)[0] in ("turning", "ends"):
            words = int(words * float(n.get("turning_point_length", 1.3)))
        self._facts = ("WHAT HAPPENS IN THIS BEAT (nothing else happens):\n" + self.describe(bundle)
                       + "\n\nCURRENT CONDITION (after this beat):\n" + condition_summary)
        context += self._sound_note() + self._fading_thoughts_note()
        if any(a.get("devastating") for a in acts):
            words += int(((n.get("devastating") or {}).get("extra_words", 150)))
            if self.progress:
                self.progress("a devastating blow: giving it room")
        self._moments = self._extra_moments(bundle, acts, pin_events)
        linger, extra = self._linger() if not self._moments else ("", 0)
        if linger:
            context += linger
            words += extra
            if self.progress:
                self.progress("lingering on one blow this beat")
        self._important = self._is_important(bundle)
        self._story_tail = _tail(story_so_far, 6000)
        self._last_context, self._last_words = context, words  # for topping up a beat that comes out short
        actor, receivers = self.actors(bundle)
        plan = self._segments(actor, receivers, words, n)
        if acts and all(a.get("type") == "eliminated" for a in acts):
            plan = [("all", "everything in this beat", words)]  # nothing to split into attack and reaction
        pin_plan = False
        going = [e for e in pin_events if not e.get("complete") and e.get("struggle") != "escape"]
        if going and len(plan) >= 2 and all(a.get("type") in ("breather", "struggle_request", "none", "time_passes")
                                            for a in acts):
            # nothing lands in a pin beat, so "her side up to contact / the other's side from contact" had both parts
            # telling the same squeeze. Part one is the pin itself; part two is what the pinned fighter does about it.
            e = going[0]
            a_, d_ = e["attacker"], e["defender"]
            held = [str(g[2]).lower() for g in (getattr(self, "grips", None) or []) if g[1] == d_]
            places = (", ".join(dict.fromkeys(held))) or "each place she is held"
            kind = e.get("struggle")
            how = self._try_how(e) if kind in ("fail", "partial") else ""
            first = (f"the pin itself, from {poss(a_)} side: her weight and her grips on {d_}, each place she presses "
                     f"told ONCE ({places}), her own effort and how her injuries take the strain, what she sees of {d_} "
                     f"up close." + (f" STOP before {d_} makes her move: that belongs to the next part."
                                     if kind in ("fail", "partial") else ""))
            told = (f"The pressing has ALREADY been told above: do not tell {poss(a_)} jaws, paws or weight bearing "
                    f"down again, and reuse no line from above. ")
            second = (f"{poss(d_)} side, under the pin. " + told + (
                f"This part is her attempt to break free ({how}): how she gathers for it, the try itself, the moment it "
                f"fails, and {poss(a_)} answer to it (the punishing blow listed for this beat, told once), then how "
                f"she lies when it is over, still pinned." if kind == "fail" else
                f"This part is her breaking partly loose ({how}): the try, the hit she lands on {a_}, and {a_} forcing "
                f"the pin back down, then how she lies when it is over, still pinned." if kind == "partial" else
                f"This part is what the pin does to her: her breath against the weight, the one place it hurts most "
                f"and exactly how, what she can still see and hear, what she tests and gives up on, what she thinks. "
                f"She is still pinned when it ends."))
            jobs = {"act": first, "take": second}
            plan = [(k, jobs.get(k, f + f" The pin still holds: {d_} stays under {a_}."), w) for k, f, w in plan]
            pin_plan = True
        freed = [e for e in pin_events if not e.get("complete") and e.get("struggle") == "escape"]
        if freed and not going and len(plan) >= 2 and all(
                a.get("type") in ("breather", "struggle_request", "none", "time_passes") for a in acts):
            # the beat she breaks FREE: the pinner does not attack, so "her side up to the instant each hit connects"
            # had nothing to stop at. Part one is the pin as it stands; part two is the escape and what follows it
            e = freed[0]
            a_, d_ = e["attacker"], e["defender"]
            held = [str(p).lower() for p in (e.get("pressed") or [])]
            places = (", ".join(dict.fromkeys(held))) or "each place she is held"
            down = isinstance(e.get("pinner_down"), dict)
            rises = any(x.get("type") == "get_up" and x.get("fighter") == d_ for x in (bundle.get("also_this_beat") or []))
            first = (f"the pin as it stands, from {poss(a_)} side: her weight and her grips on {d_}, each place she "
                     f"presses told ONCE ({places}), her own effort and how her injuries take the strain, what she "
                     f"feels {d_} gathering under her. STOP before {d_} makes her move: the escape belongs to the next "
                     f"part, and {a_} strikes nobody in this beat.")
            second = (f"{poss(d_)} side. The pressing has ALREADY been told above: don't tell it again. This part is "
                      f"her breaking FREE ({self._try_how(e)}): the try itself, the blow that frees her landing on {a_} "
                      f"(exactly where, and what it does to {a_}), {a_} coming off her "
                      + ("and going down" if down else "but keeping her feet")
                      + (f", then {poss(d_)} tries to get up, each as listed" if rises else
                         f", then {d_} loose on the ground where she was pinned")
                      + ". End with the two of them apart.")
            jobs = {"act": first, "take": second}
            plan = [(k, jobs.get(k, f), w) for k, f, w in plan]
            pin_plan = True
            going = freed    # (whose side each part is told from: the pinner's, then the pinned fighter's)
        if len(plan) >= 2 and acts and all(a.get("type") == "aftermath" for a in acts):
            # after the match nobody attacks, so "the actions from the attackers' bodies / what each fighter who is
            # hit feels" had nothing to point at: one part for the winner, one for the fallen and the place
            win = next((a.get("winner") for a in acts if a.get("winner")), None) or "the winner"
            jobs = {"act": f"{win} in the quiet after: her breath coming back, each of her injuries settling in and how "
                           f"she carries it, what she does with herself now, what she thinks of the fight. Nothing new "
                           f"starts and nobody is touched.",
                    "take": "the fallen and the place: how each fighter who is down or out lies (exactly as CURRENT "
                            "CONDITION says: no change unless one is listed for this beat), her breathing, what the "
                            "winner notices of her, the water, the light and the sounds of the place. End on "
                            "stillness."}
            plan = [(k, jobs.get(k, f), w) for k, f, w in plan]
            pin_plan = True     # (these parts stand as written: no 'the attack has already been shown' after part one)
        others = [x for x in (getattr(self, "strengths", None) or {}) if x != actor]
        if (actor and not receivers and not pin_plan and len(plan) >= 2 and len(others) == 1 and acts
                and all(a.get("type") in ("breather", "none") for a in acts)
                and not [e for e in pin_events if e.get("complete") and e.get("elimination")]):
            # nobody is hit (she catches her breath, or circles): still both sides, one part each, same length
            o_ = others[0]
            receivers = [o_]
            jobs = {"act": f"{poss(actor)} side: what she does with this moment, her breath, how each of her injuries "
                           f"feels and shows as she moves or holds still, what she sees of {o_}, what she thinks and "
                           f"plans. Nothing is thrown.",
                    "take": f"{poss(o_)} side of the same moment: what she does, her breath, how each of her injuries "
                            f"feels and shows, what she sees of {actor}, what she thinks and plans. Nothing is thrown, "
                            f"and nothing that has not been listed happens."}
            plan = [(k, jobs.get(k, f), w) for k, f, w in plan]
            pin_plan = True     # (these parts stand as written)
        gone = [e for e in pin_events if e.get("complete") and e.get("elimination")]
        if gone and not pin_plan and len(plan) >= 2 and all(
                a.get("type") in ("breather", "struggle_request", "none", "time_passes") for a in acts):
            # the beat she passes out: nothing is thrown, so there is no "up to the instant each hit connects"
            e = gone[0]
            a_, d_ = e["attacker"], e["defender"]
            places = (", ".join(dict.fromkeys(str(p).lower() for p in (e.get("pressed") or [])))) or "each place she is held"
            sure = bool(self.rules.get("pin", {}).get("make_sure", True))
            first = (f"the pin as it stands, from {poss(a_)} side: her weight and her grips on {d_}, each place she "
                     f"presses told ONCE ({places}), her own effort and how her injuries take the strain, and what she "
                     f"sees and feels of {d_} fading under her. STOP before {d_} goes out: that belongs to the next "
                     f"part, and {a_} strikes nobody in this beat.")
            second = (f"{poss(d_)} last moments under the pin, from her side. The pressing has ALREADY been told "
                      f"above: don't tell it again. What is left of her breath, her sight and her hearing, and the "
                      f"moment her body goes limp and her eyes close (out cold, still breathing). Then {poss(a_)} "
                      f"side: feeling it happen, "
                      + ("keeping her grip and her weight where they are a moment or two longer to be sure, then "
                         if sure else "")
                      + "letting go and easing off her, and the quiet after.")
            jobs = {"act": first, "take": second}
            plan = [(k, jobs.get(k, f), w) for k, f, w in plan]
            pin_plan = True
            going = gone
        also_now = bundle.get("also_this_beat") or []
        if pin_plan and any(m["key"] == "dwell" for m in self._moments):
            # under a running pin her side of the beat is already what it does to her: the watcher is the new view
            self._moments = [m for m in self._moments if m["key"] != "dwell"]
        if self._moments:
            plan = list(plan) + [(m["key"], m["focus"], m["words"]) for m in self._moments]
            if self.progress:
                self.progress("staying with the damage: " + ", ".join(
                    {"dwell": f"{poss(m['who'])} side", "watch": f"{m['who']} watching"}[m["key"]] for m in self._moments))
        if len(plan) == 1:
            if self.progress:
                self.progress("narrator is writing")
            self._sample_want = self._sample_tags("all", acts, pin_events, also_now)
            return self._call(context + f"Write this beat in about {words} words. {DETAIL}"
                              + self._blocks_for("all", acts, pin_events, also_now, actor, receivers, True, True),
                              words, coverage=True)

        written = []
        self._part_leads = {}
        self._pov_marks = []      # (first sentence of a part, whose side it is told from), for the labels
        for i, (key, focus, seg_words) in enumerate(plan, start=1):
            if self.progress:
                self.progress(f"narrator is writing part {i}/{len(plan)}")
            so_far = "\n\n".join(written)
            # whose side this part is told from: its "she" is that fighter until someone is named
            self._lead_now = (actor if key == "act" else receivers[0] if key == "take" and len(receivers) == 1 else None)
            if pin_plan and going:
                self._lead_now = going[0]["attacker"] if key == "act" else going[0]["defender"] if key == "take" else None
            if key in ("dwell", "watch"):
                self._lead_now = next((m["who"] for m in self._moments if m["key"] == key), None)
            self._prior_now = so_far
            prior = (f"The beat so far (already written; continue directly from where it stops, never repeat or "
                     f"rephrase it):\n<<<\n{_tail(so_far, 3000)}\n>>>\n\n" if written else "")
            ask = (f"{prior}Write PART {i} of {len(plan)} of this beat, about {seg_words} words. "
                   f"Focus of this part: {focus} {DETAIL}"
                   + (" Do not finish the beat yet; later parts will continue it." if i < len(plan) else
                      " This is the final part: bring the beat to rest."))
            # the receiving side is where every hit has to have shown up by (checked against everything so far)
            check = key == "take" or (i == len(plan) and "take" not in [k for k, _, _ in plan])
            self._sample_want = self._sample_tags(key, acts, pin_events, also_now)
            ask += self._blocks_for(key, acts, pin_events, also_now, actor, receivers, i == 1, i == len(plan))
            ask += self._camera_note(key)
            part = self._call(context + ask, seg_words, coverage=check, prior=so_far)
            written.append(self._drop_repeats(part, so_far) if so_far else part)  # no re-telling earlier parts
            if written[-1]:
                first = next((x.strip() for x in re.split(r"(?<=[.!?…])\s+|\n+", written[-1]) if x.strip()), None)
                if first and self._lead_now:
                    self._part_leads[first] = self._lead_now
                sents = [x.strip() for x in re.split(r"(?<=[.!?…])\s+|\n+", written[-1]) if x.strip()][:3]
                if sents:
                    self._pov_marks.append((sents, self._lead_now or "Both"))
            self._lead_now, self._prior_now = None, ""
            if key == "act" and i < len(plan) and plan[i][0] == "take" and not pin_plan:
                # only the strikes count here: pin pressure can still be shown in the next part
                strikes = list(dict.fromkeys(getattr(self, "_strike_parts", []) or self._must_parts))
                # a hit is "already shown" only when a sentence LANDS it on that part. A part that is only looked at,
                # aimed at or about to be hit ("she had aimed for the chest", "the first ring reached her fur") is
                # not: this part was told to stop at contact, and a narrator who does must not be told afterwards
                # that everything has landed
                told = [p for p in strikes if _landed_on("\n".join(written), p)]
                # "closed her teeth on that foot" lands ONE foot. When both feet are hit this beat and the prose doesn't
                # say which, it is the one a blow was aimed at; the one that was only jarred is still to be shown
                aimed = {str((x.get("hits") or [{}])[0].get("part") or "") for x in acts if x.get("hits")}
                for p in list(told):
                    mm = re.match(r"(Left|Right) (.+)$", p)
                    twin = ({"Left": "Right ", "Right": "Left "}[mm.group(1)] + mm.group(2)) if mm else None
                    if twin and twin in told and p not in aimed and twin in aimed and not re.search(
                            r"\b" + mm.group(1).lower() + r"\b[^.!?\n]{0,40}\b" + re.escape(mm.group(2).split()[-1].lower()),
                            "\n".join(written).lower()):
                        told.remove(p)
                if strikes and told and len(told) < len(strikes):
                    k2, f2, w2 = plan[i]
                    left = [p for p in strikes if p not in told]
                    plan[i] = (k2, f2 + f" Hits ALREADY shown above (don't tell them again, only their after-effects): "
                                    f"{', '.join(told)}. Still to show landing: {', '.join(left)}.", w2)
                elif not strikes or len(told) == len(strikes):
                    # the attack part already showed every hit landing (or the miss): the next part must not retell it
                    k2, _, w2 = plan[i]
                    done = ("Every hit has ALREADY been shown landing above" if self._must_parts
                            else "The attack has ALREADY been shown above, miss and all")
                    pinned_now = next((x for x in acts if x.get("type") == "pin_start" and not x.get("continuing")), None)
                    if pinned_now and not strikes:
                        d_ = pinned_now["defender"]
                        plan[i] = (k2, f"{poss(d_)} side, under the pin that has just closed on her. The presses have "
                                       f"been told above from {poss(pinned_now['attacker'])} side: don't tell them "
                                       f"closing again. Tell what each one FEELS like to {d_} (every pressed part "
                                       f"listed), her breath, what she can still move and what she can't, what she sees "
                                       f"above her, what she thinks. No escape attempt yet and no new attack: she is "
                                       f"pinned when the beat ends.", w2)
                        continue
                    dodges = [x for x in acts if x.get("dodged") and x.get("attacker") and x.get("defender")]
                    if dodges and not strikes and not (MISSED.search("\n".join(written)) or MISSED_HER.search(
                            "\n".join(written)) or _DODGE_TOLD.search("\n".join(written))):
                        # the attack part stopped where it was told to, before anything connected, so the MISS has
                        # not been told yet: telling the next part "already shown, miss and all" would lose it
                        x = dodges[0]
                        plan[i] = (k2, f"{poss(x['defender'])} side, picking up at the instant the attack should "
                                       f"land. It does NOT land: tell the dodge (how {x['defender']} gets out of its "
                                       f"way, as listed, and how close it came), where the miss carries "
                                       f"{x['attacker']}, and then how the two of them stand and size each other up. "
                                       f"Nothing connects: no impact, no damage, no new pain from this attack, and "
                                       f"nothing else is thrown this beat.", w2)
                        continue
                    plan[i] = (k2, f"CONTINUE from the exact moment the text above stops. {done}: do NOT describe "
                                   "any attack, dodge, impact, or fall again (and add no new fall). Go deeper "
                                   "into what came after: how each hurt part feels now, breath, thoughts, how they move, "
                                   "guard injuries, and size each other up. No new attacks.", w2)
        return "\n\n".join(w for w in written if w).strip()

    @staticmethod
    def _segments(actor, receivers, words, n):
        """Split long narration into focused parts. Each part stays short enough for the model to keep
        its detail dense; together they reach the target length."""
        per = max(150, int(n.get("words_per_pass", 300)))
        count = max(1, min(4, round(words / per)))
        if not n.get("two_pass_pov", True) or count == 1:
            return [("all", "everything in this beat", words)]
        if actor and receivers:
            who = " and ".join(receivers)
            focus = {
                "setup": (f"the moment before: {actor} and {who} reading each other, footing, terrain, water, "
                          f"breath, old injuries, what each one notices and intends. Nothing lands yet.", 0.8),
                "act": (f"{poss(actor)} side: what {actor} sees, does, and feels in their own body while acting, "
                        f"up to the instant each hit or grip connects. Stay in {poss(actor)} head. STOP at contact: "
                        f"leave how it lands and how it feels to {who} (and any fall that is listed) for the next "
                        f"part.", 1.0),
                "take": (f"{poss(who)} side, picking up at the instant of contact (do not re-tell the attack): what "
                         f"it feels like to receive it, body part by body part, the fall or landing ONLY if one is "
                         f"listed for this beat (otherwise she keeps her feet), the exact quality of each pain, breath, "
                         f"thoughts, and the immediate reaction.", 1.1),
                "after": (f"the aftermath: how {actor} and {who} now move, breathe, guard injuries, and reassess; "
                          f"the space between them; what each one is planning. No new attacks: end on stillness or "
                          f"tension, never on someone starting a new move.", 0.8),
            }
            order = {2: ["act", "take"], 3: ["act", "take", "after"], 4: ["setup", "act", "take", "after"]}[count]
        else:
            focus = {
                "act": ("the actions as they happen, in order, from the attackers' bodies.", 1.0),
                "take": ("picking up at the instant of contact (do not re-tell the attacks): what each fighter who is "
                         "actually HIT feels, body part by body part, and their reactions. Anyone who dodged or wasn't "
                         "hit takes NO damage: no cuts, no blood, no new pain for them.", 1.1),
                "after": ("the aftermath: positions, breathing, guarded injuries, what each one plans next. "
                          "No new attacks.", 0.8),
                "setup": ("the moment before: everyone's positions, terrain, and intentions. Nothing lands yet.", 0.8),
            }
            order = {2: ["act", "take"], 3: ["act", "take", "after"], 4: ["setup", "act", "take", "after"]}[count]
        total = sum(focus[k][1] for k in order)
        return [(k, focus[k][0], max(100, int(words * focus[k][1] / total))) for k in order]


_NOT_YET = re.compile(r"\b(?:aim(?:ed|ing|s)?|would|will|going to|about to|meant|means? to|pointed|level(?:led|ed)|"
                      r"lined up|toward|towards|chose|picked|target\w*|ready to|before it)\b", re.I)
_FELT = re.compile(r"\b(?:pain|hurt\w*|ach(?:e|ed|ing)|burn\w*|throbb\w*|scream\w*|cried|cry|yelp\w*|gasp\w*|squeak\w*|"
                   r"howl\w*|stagger\w*|reel\w*|buckl\w*|folded|doubled|jolt\w*|snapped (?:back|sideways|round)|"
                   r"knocked|breath (?:left|went|burst)|hammer\w*|pound\w*|drove (?:into|the))\b", re.I)


def _landed_on(text, part):
    """Does some sentence of `text` show a blow LANDING on this part (the part named, with an impact or what it did to
    her), as opposed to naming it as a target that hasn't been reached yet?"""
    for para in (text or "").split("\n"):
        for sent in (x for x in _SENT.split(para.strip()) if x):
            for clause in re.split(r"[,;:—–]", sent):      # the impact has to be in the clause that names the part
                if not _mentions(clause.lower(), part) or _NOT_YET.search(clause):
                    continue
                if IMPACT_NOW.search(clause) or _FELT.search(clause) or re.search(
                        r"\b(?:took|clipped|punched|cracked|thudded|ploughed|plowed|broke over|burst (?:on|against|across)|"
                        r"found|met|opened|closed on|clamped)\b", clause, re.I):
                    return True
    return False


POV_LINE = re.compile(r"^— [^\n]{1,40} —[ \t]*$\n?", re.M)


def strip_pov(text):
    """The story without its perspective labels ("— Nocturne —"): what the models are shown of earlier beats, so they
    never copy the labels into the prose."""
    return re.sub(r"\n{3,}", "\n\n", POV_LINE.sub("", text or "")).strip()


def _tail(text, limit):
    """The last `limit` characters of the previous story, starting at a paragraph boundary."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[-limit:]
    nl = cut.find("\n")
    return cut[nl + 1:] if 0 <= nl < limit // 2 else cut
