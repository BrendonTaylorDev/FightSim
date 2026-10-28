"""
Combat engine: the single source of truth for every number in the fight.
The models never calculate anything. The director picks moves, the narrator writes prose,
and the stat block you see is printed straight from here.
"""
import copy
import difflib
import json
import math
import os
import random
import re
from dataclasses import dataclass, field, asdict


_FAILED_ONCE = set()


def note_failure(where, exc):
    """A step that has a fallback failed (the story's mood, the pin shapes, a check of the prose...): the fight goes
    on with the fallback, but it isn't silent. Every failure goes into errors.log with its traceback; the first one
    from each place this session is also said in one line."""
    import time
    import traceback
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "errors.log"), "a", encoding="utf-8") as fh:
            fh.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {where}: {exc!r}\n"
                     + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except OSError:
        pass
    if where not in _FAILED_ONCE:
        _FAILED_ONCE.add(where)
        print(f"[{where} failed ({type(exc).__name__}: {exc}); carrying on without it. Details in errors.log]")


def _to_json(v):
    """State for a save file: sets become {"__set__": [...]} (JSON has no sets), tuples lists, the rest as it is."""
    if isinstance(v, (set, frozenset)):
        return {"__set__": sorted((_to_json(x) for x in v), key=str)}
    if isinstance(v, dict):
        return {k: _to_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_to_json(x) for x in v]
    return v


def _from_json(v):
    """The other way: {"__set__": [...]} back into a set (tuples stay lists; nothing that reads them minds)."""
    if isinstance(v, dict):
        if set(v) == {"__set__"}:
            return {tuple(x) if isinstance(x, list) else x for x in v["__set__"]}
        return {k: _from_json(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_from_json(x) for x in v]
    return v


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def norm(name):
    return " ".join(str(name).replace("_", " ").lower().split())


def _matches(value, t):
    return value > t["min"] if t.get("exclusive") else value >= t["min"]


_DANGLING = {"of", "the", "a", "an", "and", "with", "on", "in", "into", "to", "at", "by", "from", "near", "against",
             "beside", "under", "over", "its", "her", "his", "their", "that", "which", "or", "then", "but", "as", "while",
             "round", "around", "onto", "for", "so"}


def short_phrase(text, n=6, default=""):
    """The first n words of a label, without a dangling 'of the' at the end."""
    words = str(text or default).split()[:n]
    while len(words) > 1 and words[-1].lower().strip(",.;:") in _DANGLING:
        words.pop()
    return " ".join(words).rstrip(",;:")


def pain_tiers(rules):
    """The pain levels in use. narration.numb_tier = false drops the 'numb with shock' level (1000%+),
    so those parts simply stay 'devastated'."""
    tiers = rules["pain_tiers"]
    if (rules.get("narration", {}).get("numb_tier", True) is False
            or (rules.get("numbness") or {}).get("enabled", False)):
        tiers = [t for t in tiers if t.get("label") != "numb with shock"]
    rc = rules.get("ruined") or {}
    if not rc.get("enabled", True):
        tiers = [t for t in tiers if t.get("label") != "ruined"]    # (ruined off: those parts stay devastated)
    elif rc.get("min") is not None:
        tiers = [dict(t, min=float(rc["min"])) if t.get("label") == "ruined" else t for t in tiers]
    return tiers


def tier_for(value, tiers):
    """Highest tier the value qualifies for (respects 'exclusive' minimums)."""
    ordered = sorted(tiers, key=lambda t: t["min"], reverse=True)
    for t in ordered:
        if _matches(value, t):
            return t
    return ordered[-1]


# Body-region knowledge for mapping a part name onto a different species' anatomy.
# (words in the requested name) -> (keywords to look for in the defender's parts, best first)
_REGIONS = [
    (("hind paw", "hind foot", "foot", "feet", "toe"), ["foot", "hind paw", "tail fan"]),
    (("forepaw", "front paw", "hand", "paw", "claw", "finger"), ["forepaw", "paw", "forearm fin", "foot", "tail fan"]),
    (("knee", "hock", "ankle", "shin", "calf"), ["knee", "hock", "lower tail"]),
    (("thigh", "hip", "leg", "haunch", "rump"), ["thigh", "hip", "hock", "lower tail"]),
    (("foreleg", "arm", "forearm", "elbow", "wrist"), ["upper foreleg", "lower foreleg", "upper arm",
                                                       "forearm", "shoulder", "midsection"]),
    (("shoulder",), ["shoulder", "upper back", "lower neck"]),
    (("stomach", "belly", "abdomen", "gut", "midsection"), ["stomach", "belly", "midsection"]),
    (("chest", "sternum", "breast", "mane", "torso"), ["chest", "mane"]),
    (("rib", "side", "flank"), ["ribs", "flank", "midsection", "chest", "stomach", "belly"]),
    (("back", "spine"), ["upper back", "back", "lower back"]),
    (("tail",), ["tails", "sickle tail", "upper tail", "tail"]),
    (("neck", "throat", "collar", "sac", "scruff", "nape"), ["neck", "throat", "flotation sac"]),
    (("face", "muzzle", "snout", "mouth", "nose", "jaw", "cheek"), ["muzzle", "nose", "jaw", "head"]),
    (("ear", "antenna", "whisker"), ["ear", "antenna", "head fin"]),
    (("horn", "head", "skull", "brow"), ["horn", "head"]),
    (("fin",), ["fin"]),
]


def _has_word(text, phrase):
    words = text.split()
    if " " in phrase:
        return phrase in text
    return any(w == phrase or w == phrase + "s" or w == phrase + "es" for w in words)


def match_part(names, part, avoid=()):
    """Find the body part `part` refers to among `names`. Exact match first, then anatomy:
    species have different parts, so "Left Forepaw" on a Buizel means her "Left Paw".
    Returns None if nothing reasonable matches."""
    p = " ".join(str(part).replace("_", " ").split()).lower()
    for n in names:
        if n.lower() == p:
            return n
    side = "left" if "left" in p.split() else "right" if "right" in p.split() else None

    def pick(cands):
        cands = [n for n in cands if n not in avoid]
        same = [n for n in cands if side and side in n.lower().split()]
        return (same or cands or [None])[0]

    for triggers, keywords in _REGIONS:
        if any(_has_word(p, t) for t in triggers):
            for kw in keywords:
                hit = pick([n for n in names if kw in n.lower()])
                if hit:
                    return hit
    pool = [n for n in names if (side is None or side in n.lower().split()) and n not in avoid] or names
    m = difflib.get_close_matches(p, [n.lower() for n in pool], n=1, cutoff=0.75)
    return next((n for n in pool if n.lower() == m[0]), None) if m else None


# Which broad region of the body a part belongs to, and which regions touch, so a blow can spill onto
# the parts right next to where it lands (a jaw strike jars the muzzle and neck; a hip check catches the thigh).
_BODY_REGION_KEYS = [
    ("tail", ("tail", "fan")),
    ("hind_low", ("hind paw", "knee", "hock", "foot", "talon")),
    ("hind_up", ("hip", "thigh")),
    ("head", ("head fin", "horn", "ear", "muzzle", "snout", "nose", "jaw", "cheek", "antenna", "spike", "head", "eye", "face",
              "beak", "crest")),
    ("neck", ("throat", "neck", "sac", "hood", "mane")),
    ("shoulder", ("shoulder",)),
    ("fore_up", ("upper arm", "upper foreleg", "wing")),
    ("fore_low", ("forearm", "lower foreleg", "forepaw", "paw", "hand", "fin", "arm", "foreleg", "wingtip")),
    ("chest", ("ruff", "chest", "rib")),
    ("belly", ("belly", "stomach", "midsection", "flank", "scales")),
    ("back_low", ("lower back",)),
    ("back_up", ("upper back", "back", "spine")),
]
_BODY_REGION_NEAR = {
    "head": ["neck"], "neck": ["head", "chest", "shoulder", "back_up"],
    "shoulder": ["neck", "fore_up", "chest", "back_up"], "fore_up": ["shoulder", "fore_low", "chest"],
    "fore_low": ["fore_up"], "chest": ["neck", "shoulder", "belly", "fore_up"], "belly": ["chest", "hind_up", "back_low"],
    "back_up": ["shoulder", "neck", "back_low"], "back_low": ["back_up", "belly", "hind_up", "tail"],
    "hind_up": ["belly", "back_low", "tail", "hind_low"], "hind_low": ["hind_up"], "tail": ["back_low", "hind_up"],
}


def species_of(description, appearance=""):
    """'A female Buizel. ...' -> 'Buizel' (from a fighter's description, or else the first word of her appearance)."""
    m = (re.match(r"\s*(?:An?|The)\s+(?:female\s+|male\s+)?([A-Z][\w'-]+)", description or "")
         or re.match(r"\s*([A-Z][\w'-]+)\s*\.", appearance or ""))
    return m.group(1) if m and m.group(1).lower() not in ("female", "male") else ""


def ordinal(n):
    """3 -> "third", 11 -> "11th"."""
    words = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth",
             9: "ninth", 10: "tenth"}
    if n in words:
        return words[n]
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def poss_word(name):
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def body_region(part):
    p = part.lower()
    for region, keys in _BODY_REGION_KEYS:
        if any(re.search(r"\b" + re.escape(k) + r"(?:s|es)?\b", p) for k in keys):
            return region
    return "other"


_COVER_SWAP = {"feathers": [(r"\bfur\b", "feathers"), (r"\bcoat\b(?! of)", "plumage"), (r"\bhairs?\b(?!'s)", "feathers")],
               "scales": [(r"\bburnt hair\b", "scorched hide"), (r"\bfur\b", "scales"), (r"\bcoat\b(?! of)", "scales"),
                          (r"\bhairs?\b(?!'s)", "scales"), (r"\bwhole tufts\b", "whole patches"),
                          (r"\btufts?\b", "ragged patches"), (r"\bin (her|the) scales\b", r"on \1 scales")],
               "skin": [(r"\bfur\b", "skin"), (r"\bcoat\b(?! of)", "hide"), (r"\bhairs?\b(?!'s)", "skin"),
                        (r"\btufts?\b", "ragged patches")]}


def in_covering(cover, text):
    """Wording written for fur, said in her own covering (feathers, scales or skin): 'the fur parting' on a dragon
    becomes 'the scales parting'. Fur, or a covering not known, leaves it as it is."""
    swaps = _COVER_SWAP.get(cover)
    if not swaps or not text:
        return text
    for rx, word in swaps:
        text = re.sub(rx, word, text)
    return re.sub(r"\b(feathers|scales) (is|was|stands?|lies|parts)\b",
                  lambda m: m.group(1) + " " + {"is": "are", "was": "were", "stands": "stand", "stand": "stand",
                                                "lies": "lie", "parts": "part"}[m.group(2)], text)


def _side(part):
    w = part.lower().split()
    return "left" if "left" in w else "right" if "right" in w else None


def neighbor_parts(names, part):
    """Parts next to `part`: same region first, then touching regions; never the opposite side's twin."""
    region, side = body_region(part), _side(part)
    ok = [n for n in names if n != part and (side is None or _side(n) in (None, side))]
    same = [n for n in ok if body_region(n) == region]
    near = [n for r in _BODY_REGION_NEAR.get(region, []) for n in ok if body_region(n) == r]
    return same, near


@dataclass
class BodyPart:
    name: str
    damage: float
    resistance: float
    start_resistance: float


@dataclass
class Fighter:
    name: str
    description: str
    health: float
    max_health: float
    parts: dict = field(default_factory=dict)  # display name -> BodyPart
    team: str = ""          # fighters sharing a team are allies; blank = fights alone
    eliminated: bool = False
    types: list = field(default_factory=list)   # Pokemon types, e.g. ["Dark"]
    moves: list = field(default_factory=list)   # [{name, type, power, target, about}]
    appearance: str = ""                         # exact looks, so the narrator gets anatomy and colors right
    move_uses: dict = field(default_factory=dict)  # move name -> uses left, for limited moves
    tells: str = ""                              # how this species shows pain and effort (ears, tail, sounds...)
    recovery: int = 0                            # after being put out: 0 out cold, 1 stirring, 2 awake but down, 3 up
    status: dict = field(default_factory=dict)   # status effect -> beats left (paralyzed, chilled, soaked, ...)
    energy: float = 100.0                        # stamina for moves; big moves cost more, resting restores it
    adrenaline_used: bool = False                # the one-time surge when strength first drops low
    voice: str = ""                              # how this fighter sounds (thoughts, cries, speech)
    out_beats: int = 0                           # beats since being put out (or since the last recovery stage)
    learned: dict = field(default_factory=dict)  # what she has learned this fight: pin shapes broken, moves felt
    traits: dict = field(default_factory=dict)   # (since build 280) how she fights: speed, hold, escape... (1 = as now)
    quirks: list = field(default_factory=list)   # (since build 280) her named quirks (rules.json -> traits.quirks)
    style: str = ""                              # (since build 280) how she likes to fight, for the director
    favors: dict = field(default_factory=dict)   # (since build 280) move name -> how much she prefers it
    personality: str = ""                        # (since build 281) who she is, for the story (narration.character)
    history: str = ""                            # (since build 281) her past, as far as the story may use it
    relationships: dict = field(default_factory=dict)   # (since build 281) other fighter -> what she is to her
    veteran: bool = False                        # (since build 281) she has fought before: she may remember it
    heart_rest: float = 0.0                      # (since build 283) her resting heart rate, for the constriction's numbers

    def part(self, name):
        found = match_part(list(self.parts), name)
        if found is None:
            raise ValueError(f"{self.name} has no body part like '{name}'. "
                             f"{self.name}'s parts: {', '.join(self.parts)}")
        return self.parts[found]


@dataclass
class Hold:
    """A continuous attack: damage every beat until released."""
    id: int
    attacker: str
    defender: str
    part: str
    power: float
    change_per_turn: float
    flavor: str
    turns_active: int = 0
    with_part: str = ""      # what the attacker presses with (her knees, teeth, coils...)
    grab: bool = False       # a grapple: she is held at point-blank, on her feet (neither can dodge the other)
    coil: bool = False       # coils, tails or a body wrapped round her: it tightens every beat and squeezes her breath
    sub: str = ""            # a submission hold (engine.SUBMISSIONS): it wrenches, it doesn't pin
    locked: str = ""         # a submission held so long it became a pin: it keeps wrenching at full, still building


USER_SETTINGS = "my_settings.json"


def merge_settings(base, extra):
    """Lay saved settings over the rules: dicts merge key by key, anything else replaces. Returns how many values."""
    n = 0
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            n += merge_settings(base[k], v)
        else:
            base[k] = v
            n += 1
    return n


BALANCE = 146     # my_settings.json "balance": the damage units its saved numbers are in (see migrate_settings)
# build 146 lowered part damage (scale 5 -> 3, slower wear) and raised health per damage point to keep fights as long:
# a number saved before it is converted by these factors
_BALANCE_146 = {("damage", "damage_scale"): 0.6, ("health", "loss_per_damage_point"): 0.46 / 0.155,
                ("resistance", "loss_per_power"): 0.75}


def migrate_settings(path):
    """Read my_settings.json, converting what an older build saved into this build's units (and saying so once):
    a /scale or /length from before build 146 would otherwise undo the new balance."""
    data = load_json(path)
    if not isinstance(data, dict) or int(data.get("balance", 0) or 0) >= BALANCE:
        return data
    said = []
    for (sec, key), f in _BALANCE_146.items():
        v = (data.get(sec) or {}).get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            new = round(v * f, 4)
            data[sec][key] = new
            said.append(f"{sec}.{key} {v} -> {new}")
    for sec, key in (("resistance", "smooth"), ("health", "pain_drain")):
        if key in (data.get(sec) or {}):
            del data[sec][key]
            said.append(f"{sec}.{key} reset to the new default")
    data["balance"] = BALANCE
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass
    if said:
        print("[my_settings.json: build 146 changed how body-part damage is counted, so your saved settings were "
              "converted to keep the same effect: " + "; ".join(said) + "]")
    return data


class Engine:
    def __init__(self, rules_path=None, fighters_path=None, seed=None, rules=None, only=None):
        """rules: an already-loaded rules dict to keep using (a new fight in the same session). only: the names of
        the fighters from fighters.json who are in this fight (default: everyone in the file)."""
        here = os.path.dirname(os.path.abspath(__file__))
        self.rules = rules if rules is not None else load_json(rules_path or os.path.join(here, "rules.json"))
        self.settings_applied = 0
        mine = os.path.join(here, USER_SETTINGS)
        if rules is None and rules_path is None and os.path.exists(mine):
            # what you set with /commands (my_settings.json) wins over the rules.json a new build ships
            try:
                self.settings_applied = merge_settings(self.rules, migrate_settings(mine))
            except (ValueError, OSError) as e:
                print(f"[my_settings.json could not be read ({e}); using rules.json as it is]")
        fdata = load_json(fighters_path or os.path.join(here, "fighters.json"))
        # a fighter may come in more than one version (fighters.json "variants"); rules.json -> variants says which
        self.variants, self.variant_of = {}, {}
        chosen = self.rules.get("variants") or {}
        made = []
        for fd in fdata["fighters"]:
            kinds = {k: v for k, v in (fd.get("variants") or {}).items() if isinstance(v, dict)}
            if kinds:
                self.variants[fd["name"]] = {"original": "as first written"}
                self.variants[fd["name"]].update({k: v.get("label", "") for k, v in kinds.items()})
                want = str(chosen.get(fd["name"], "original") or "original").lower()
                pick = next((k for k in kinds if k.lower() == want), None)
                self.variant_of[fd["name"]] = pick or "original"
                if pick:
                    fd = {**fd, **{k: v for k, v in kinds[pick].items() if not k.startswith("_") and k != "label"}}
            made.append(fd)
        fdata = dict(fdata, fighters=made)
        self.roster = [fd["name"] for fd in fdata["fighters"]]  # everyone available, in or out of this fight
        self.roster_species = {fd["name"]: species_of(fd.get("description", ""), fd.get("appearance", ""))
                               for fd in fdata["fighters"]}
        if only:
            picked = []
            for want in only:
                name = self.match_roster(want)
                if name not in picked:
                    picked.append(name)
            if len(picked) < 2:
                raise ValueError(f"a fight needs at least two different fighters. Available: {', '.join(self.roster)}")
            fdata = dict(fdata, fighters=[fd for n in picked for fd in fdata["fighters"] if fd["name"] == n])
        elif sum(1 for fd in fdata["fighters"] if not fd.get("bench")) >= 2:
            # "bench": true keeps a fighter on the roster but out of the default fight (/newfight <names> brings her in)
            fdata = dict(fdata, fighters=[fd for fd in fdata["fighters"] if not fd.get("bench")])
        self.rng = random.Random(seed)
        self._seed0 = seed if seed is not None else random.randrange(10 ** 9)   # for choices of colour only
        self.fighters = {}
        self.holds = {}
        self.next_hold_id = 1
        self.turn = 0
        self.involved = set()  # fighters who acted or were acted on this beat (only they tire)
        self.pins = {}         # "Attacker>Defender" -> pin clock and struggle state
        self.positions = ""    # where everyone is after the last beat (written by the director)
        self.downed = {}       # fighter -> beats spent on the ground so far (knocked down, thrown, launched, pinned)
        self._fresh_down = set()  # knocked down this beat: no getting up until the next one
        self.facing = {}       # fighter on the ground -> "face-down", "face-up" or "on her side"
        self.since_pin = {}    # fighter -> attacks they've taken since the last pin attempt on them
        self.momentum = []     # who made each recent attack (oldest first), so the director can share the action
        self._fresh_status = set()  # (fighter, status) applied this beat: they don't tick down until the next one
        self.move_log = []     # (attacker, move name) of recent attacks, for the variety rule
        self.last_pin_end = {} # the most recent pin that ended: who, how, at what second, on which beat
        self.injury_log = {}   # "Fighter|Part" -> the moves/causes that hurt it, oldest first (for callbacks)
        self.tally = {}        # "thrown|Ripples" -> how many times this fight (thrown, slammed, dragged, charged, down, pinned)
        self.fight_record = {} # fighter -> what she has learned this fight: her moves that land or miss, the ones that hit her
        self.game_plans = {}   # fighter -> the part of the other she means to take apart (director.game_plan)
        self.plan = {}        # the author's nudges: shape (close/dominate/comeback), winner, targeting
        self._source = ""      # what is dealing damage right now (set by each attack)
        self.rolls = []        # every chance the dice decided this beat: what, the chance, the roll, how it came out
        self.nudges = []       # what the director was pointed at this beat (a pin opening, a big moment...)
        self._knock_on = []    # what the last change knocked loose (pins broken, grips lost), for the display and story
        self.pin_window = {}   # fighter -> is there an opening to start a pin on her THIS beat (rolled for the director)
        self.pressed = {}      # fighter -> {"surface", "by"}: driven into the scenery by a charge THIS beat, not fallen yet
        self.alliances = []    # temporary alliances: {"members", "name", "beats", "until", "home"}
        self.weather = {}      # {"kind": "rain"/"sun"/"hail", "beats": N, "by": name}: Rain Dance, Sunny Day, Hail
        self.arena_marks = []  # what the fight has done to the place (a broken stalagmite, a toppled pillar)
        self.chronicle = self.new_chronicle()  # key moments, damage dealt and the strength track, for the summary
        self.setups = []       # tactics: plans made (a soaked opponent and lightning ready...) waiting for their payoff
        self._pending_events = []  # things settled between beats (an alliance ending) that the next beat reports
        self._last_reposition = {}  # fighter -> the beat she was last rolled over or hauled up
        self.scenes = self._load_scenes(here)
        self.scene_cfg, self.scene_name = {}, ""
        self.scene = fdata.get("scene", "A fight.")
        self.set_scene(str(self.rules.get("scene", {}).get("current") or "sea cave"), fallback=self.scene)
        # the place acts by its own dice, so adding or removing arena events never changes how a fight's own rolls fall
        self.event_rng = random.Random(None if seed is None else int(seed) * 7919 + 13)
        self._last_event, self._forced_event = None, None
        self.lucky = set()     # fighters you play with the dice off for them (/play dice free): their own tries succeed
        mpath = os.path.join(here, "moves.json")
        self.movedex = load_json(mpath).get("moves", []) if os.path.exists(mpath) else []
        for fd in fdata["fighters"]:
            self._add_fighter(fd)
        # teams you set with /team (rules.json "teams": fighter -> team name) apply to every fight
        sides = {f.name: (self.rules.get("teams") or {}).get(f.name) or f.team for f in self.fighters.values()}
        if len(set(sides.values())) > 1:  # never a "fight" where everyone is on one side
            for f in self.fighters.values():
                f.team = sides[f.name]

    # ---------- setup ----------
    def match_roster(self, want):
        """The fighter in fighters.json that a typed name means: exact, then by how it starts, then anywhere in it."""
        w = str(want).strip().strip(",").lower()
        sp = [n for n in self.roster if w and (self.roster_species.get(n) or "").lower() == w]
        if len(sp) == 1:
            return sp[0]      # by species: "Charizard" -> Cinder
        for test in (lambda n: n.lower() == w, lambda n: n.lower().startswith(w), lambda n: w in n.lower()):
            hits = [n for n in self.roster if w and test(n)]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                raise ValueError(f"'{want}' could be {' or '.join(hits)}: type more of the name")
        raise ValueError(f"no fighter called '{want}' in fighters.json. Available: {', '.join(self.roster)}")

    def _add_fighter(self, fd):
        hp = fd.get("health", self.rules["health"]["start"])
        f = Fighter(fd["name"], fd.get("description", ""), hp, hp,
                    team=fd.get("team") or fd["name"],
                    types=list(fd.get("types", [])), moves=list(fd.get("moves", [])),
                    appearance=fd.get("appearance", ""), tells=fd.get("tells", ""), voice=fd.get("voice", ""),
                    move_uses={m["name"]: int(m["uses"]) for m in fd.get("moves", []) if m.get("uses")},
                    traits={k: v for k, v in (fd.get("traits") or {}).items() if not str(k).startswith("_")},
                    quirks=list(fd.get("quirks") or []), style=str(fd.get("style") or ""),
                    favors=dict(fd.get("favors") or {}), personality=str(fd.get("personality") or ""),
                    history=str(fd.get("history") or ""),
                    relationships={k: v for k, v in (fd.get("relationships") or {}).items() if not str(k).startswith("_")},
                    veteran=bool(fd.get("veteran", False)), heart_rest=float(fd.get("heart_rest", 0) or 0))
        body = fd.get("body", "human")
        template = dict(body) if isinstance(body, dict) else dict(self.rules["body_templates"][body])
        template.update(fd.get("extra_parts", {}))
        overrides = {norm(k): v for k, v in fd.get("resistance_overrides", {}).items()}
        for pname, res in template.items():
            if pname.startswith("_"):
                continue
            r = float(overrides.get(norm(pname), res))
            f.parts[pname] = BodyPart(pname, 0.0, r, r)
        self.fighters[f.name.lower()] = f

    def get(self, name):
        key = str(name).strip().strip("<>[]\"'").strip().lower()
        if key not in self.fighters and key:
            sp = [k for k, f in self.fighters.items()
                  if species_of(f.description, getattr(f, "appearance", "")).lower() == key]
            if len(sp) == 1:
                key = sp[0]   # by species: "Charizard" -> Cinder
        if key not in self.fighters and key:
            close = difflib.get_close_matches(key, list(self.fighters), n=2, cutoff=0.75)
            if len(close) == 1:
                key = close[0]  # a small typo like "Nocturn"
        if key not in self.fighters:
            raise ValueError(f"No fighter named '{name}'. Fighters: {', '.join(f.name for f in self.fighters.values())}")
        return self.fighters[key]

    def active(self):
        return [f for f in self.fighters.values() if not f.eliminated]

    def get_active(self, name):
        f = self.get(name)
        self.involved.add(f.name)
        if f.eliminated:
            raise ValueError(f"{f.name} has been eliminated and can't take part. "
                             f"Still in: {', '.join(x.name for x in self.active())}")
        return f

    def teams_left(self):
        return sorted({f.team for f in self.active()})

    def winner(self):
        """Team name (or fighter name) if only one side is left, else None."""
        t = self.teams_left()
        return t[0] if len(t) == 1 else None

    def all_part_names(self):
        names = []
        for f in self.fighters.values():
            for p in f.parts:
                if p not in names:
                    names.append(p)
        return names

    # ---------- core math ----------
    def _apply_damage(self, defender, part_name, power, cap=None, grind=None, health_scale=1.0, slow=None,
                      wear_first=None):
        """One instance of damage, using the bracket rules. Returns every number involved. cap: {"mult", "health_mult"}
        upper limits on the bracket's multipliers (a pin's steady pressure doesn't tear into a worn part the way a
        blow does: pin.pressure_cap). grind (submissions.grind): a wrench that hurts little while the part is still
        sound and wears it down fast, so it bites harder and harder the longer the part is worked: its damage x
        from_mult on a sound part up to to_mult on a worn-out one, its wear on the part x wear_mult. health_scale: the
        health lost x this, the part's damage and wear untouched (a long hold's build climbs slower in health).
        slow (holds.slow_bite): a hold's pressure wears the part's resistance first and bites into it only slowly:
        its damage mult climbs from what it was on the sound part only as (worn / sound) ** exp, and its wear x
        wear_mult (holds already grinding keep their own wear).
        wear_first (holds.coil.wear_first, since build 297): a coil's pressure goes almost all into wearing the part
        down while it is sound: its damage x min_mult down to `until` % condition, climbing steeply to the full bite at
        `full_at` % and below, and its wear on the part x wear_mult. In place of slow."""
        r = self.rules
        p = defender.part(part_name)
        # the damage roll: every instance of damage (a move, a press, a landing, an impact) lands a little harder or
        # softer than its number, so no two are quite alike (damage.roll: plus or minus this share; 0 = off)
        spread = float((r.get("damage") or {}).get("roll", 0.17) or 0)
        rolled = 1.0
        if spread > 0 and power > 0:
            rolled = self.rng.uniform(1 - spread, 1 + spread)
            power = power * rolled
        self.__dict__.setdefault("hit_turn", {})[f"{defender.name}|{p.name}"] = self.turn   # for the notes' decay
        res_b, dmg_b, hp_b = p.resistance, p.damage, defender.health
        pain_b = tier_for(dmg_b, pain_tiers(r))
        htier_b = tier_for(self._health_pct(defender), r["health_tiers"])

        cond_b = self.condition(p)
        bracket = tier_for(cond_b, r["resistance"]["brackets"])
        scale = float(r.get("damage", {}).get("damage_scale", 1.0))
        bmult, hmult = self.resistance_mults(cond_b, bracket)
        bmult *= self.vulnerability(p)
        if grind:
            worn_ = 1.0 - max(0.0, min(1.0, float(cond_b) / 100.0))
            bmult *= float(grind.get("from_mult", 0.5)) + (float(grind.get("to_mult", 1.3))
                                                           - float(grind.get("from_mult", 0.5))) * worn_
        if slow:
            # what this grip's mult was on the part while it was sound: the climb from there is flattened
            b0 = self.resistance_mults(self.condition(p, getattr(p, "start_resistance", 0) or p.resistance))[0]
            b0 *= self.vulnerability(p) * (float(grind.get("from_mult", 0.5)) if grind else 1.0)
            if b0 > 0 and bmult > b0:
                bmult = b0 * (bmult / b0) ** float(slow.get("exp", 0.6))
            if not grind:
                # and, like a submission's grind, it bites lightly while the part is sound (start_mult), fully on
                # a worn-out one
                worn_ = 1.0 - max(0.0, min(1.0, float(cond_b) / 100.0))
                bmult *= float(slow.get("start_mult", 0.6)) + (1.0 - float(slow.get("start_mult", 0.6))) * worn_
        if wear_first:
            # (a coil: the pressure softens the part first, and bites only once it is nearly worn through)
            hi, lo = float(wear_first.get("until", 40)), float(wear_first.get("full_at", 15))
            mn = float(wear_first.get("min_mult", 0.12))
            t = max(0.0, min(1.0, (hi - float(cond_b)) / max(1.0, hi - lo)))
            bmult *= mn + (1.0 - mn) * t * t
        capped = False
        if cap:
            if cap.get("mult") is not None and bmult > float(cap["mult"]):
                bmult, capped = float(cap["mult"]), True
            if cap.get("health_mult") is not None and hmult > float(cap["health_mult"]):
                hmult = float(cap["health_mult"])
                capped = capped or not cap.get("health_only")
        taken = power * bmult * scale
        zramp = self.zero_part_ramp(defender)    # below_zero.part_ramp: deep below zero, her parts give way faster
        lramp = self.long_match_ramp()           # finish.submission.long_ramp: a match that runs long wears faster
        p.damage = dmg_b + self._part_added(dmg_b, taken * zramp * lramp)
        # (the sting of this beat's blows and grips, for the window's pain gauge: which beat, and how much)
        now_ = self.turn + (0 if getattr(self, "_ticking", False) else 1)
        st_ = defender.learned.get("sting") or [now_, 0.0]
        defender.learned["sting"] = [now_, round((st_[1] if st_[0] == now_ else 0.0) + taken, 2)]
        sp_ = defender.learned.get("sting_parts") or [now_, {}]
        sp_ = sp_ if sp_[0] == now_ else [now_, {}]
        sp_[1][p.name] = round(float(sp_[1].get(p.name, 0.0)) + taken, 2)
        defender.learned["sting_parts"] = sp_
        was_numb = int(getattr(p, "numb", 0) or 0) > 0
        rscale = float(r.get("damage", {}).get("resistance_scale", 1.0))
        # resistance lost: by the blow's power, and (resistance.loss_per_damage, 0 = off) by the damage it really did,
        # so a part that takes a great deal of damage also softens faster
        wear = power * r["resistance"]["loss_per_power"] + taken * float(r["resistance"].get("loss_per_damage", 0) or 0)
        wear = wear * rscale
        wear_math = []      # what scaled the wear beyond power x loss_per_power x resistance_scale (for the stat lines)
        cap_res = float(r["resistance"].get("max_loss_per_hit", 0) or 0)
        rel = r["resistance"].get("relative") or {}
        start_r, sound = float(getattr(p, "start_resistance", 0) or 0), float(rel.get("sound", 85))
        if rel.get("enabled", True) and 0 < start_r < sound:
            # a part that starts low wears in proportion to what it has: its CONDITION falls at much the pace of a
            # sound part's (a little faster, by wear_exp), and the per-hit cap counts in condition too
            share = start_r / sound
            wear *= share ** float(rel.get("wear_exp", 0.6))
            wear_math.append(["a part that starts soft wears in proportion", round(share ** float(rel.get("wear_exp", 0.6)), 3)])
            cap_res = cap_res * share if cap_res > 0 else 0.0
        if grind:
            wear *= float(grind.get("wear_mult", 2.0))
            cap_res *= float(grind.get("wear_mult", 2.0))
            wear_math.append(["a submission grinds it down", float(grind.get("wear_mult", 2.0))])
        elif wear_first:
            wear *= float(wear_first.get("wear_mult", 2.0))
            cap_res *= float(wear_first.get("wear_mult", 2.0))
            wear_math.append(["coils wear it down first", float(wear_first.get("wear_mult", 2.0))])
        elif slow:
            wear *= float(slow.get("wear_mult", 1.5))
            cap_res *= float(slow.get("wear_mult", 1.5))
            wear_math.append(["a hold wears it first", float(slow.get("wear_mult", 1.5))])
        wear_cap = None
        if cap_res > 0 and wear > cap_res:
            wear = wear_cap = cap_res   # resistance.max_loss_per_hit: no single blow, however devastating, wears a part past this
        p.resistance = max(r["resistance"]["minimum"], res_b - wear)
        # health lost: damage x loss_per_damage_point x the bracket's health_mult (a soft, worn-down part costs more)
        # x how much the part matters to the whole body (health.part_weights: a throat far more than an ear)
        vital = self.part_weight(p.name)
        raw_loss = taken * r["health"]["loss_per_damage_point"] * hmult * vital * health_scale
        health_loss = self._soften_loss(defender, raw_loss, power)
        defender.health = self._floor(hp_b - health_loss)
        # the health the soft cap kept from her doesn't vanish: a share of it wears the part down further
        # (health.soft_cap.to_resistance resistance points per point of health softened away)
        over = max(0.0, raw_loss - health_loss)
        to_res = float((r["health"].get("soft_cap") or {}).get("to_resistance", 0.1) or 0)
        res_over = 0.0
        if over > 0 and to_res > 0:
            before_over = p.resistance
            room = (cap_res - (res_b - p.resistance)) if cap_res > 0 else over * to_res
            p.resistance = max(r["resistance"]["minimum"], p.resistance - max(0.0, min(over * to_res, room)))
            res_over = before_over - p.resistance

        pain_a = tier_for(p.damage, pain_tiers(r))
        htier_a = tier_for(self._health_pct(defender), r["health_tiers"])
        if self._source and taken >= 1:
            # the first thing that ever hurt this part, and when (for callbacks much later in the fight)
            defender.learned.setdefault("first_hurt", {}).setdefault(p.name, [self._source, self.turn + 1])
            key = f"{defender.name}|{p.name}"
            log = self.injury_log.setdefault(key, [])
            amt = self.__dict__.setdefault("injury_amt", {}).setdefault(key, {})
            amt[self._source] = round(float(amt.get(self._source, 0)) + max(0.0, p.damage - dmg_b), 2)
            if not log or log[-1] != self._source:
                if self._source in log:
                    log.remove(self._source)      # (once each, where it last hurt her: no "A, then B, then A")
                log.append(self._source)
                while len(log) > 6:
                    # (the record keeps what did the most: the lightest older cause goes, never the latest)
                    log.remove(min(log[:-1], key=lambda c: float(amt.get(c, 0))))
            # a huge hit on this part is remembered for the rest of the fight, however long ago it was
            # (narration.notes_decay.big_hit: part damage added in one go)
            added = p.damage - dmg_b
            big = defender.learned.setdefault("big_hits", {})
            if added >= float(((r.get("narration") or {}).get("notes_decay") or {}).get("big_hit", 150)) \
                    and added > (big.get(p.name) or [None, 0])[1]:
                big[p.name] = [self._source, round(added, 1)]
        numb_new = self._maybe_numb(defender, p, taken, was_numb)
        return {
            "numb": was_numb, "goes_numb": numb_new,
            "defender": defender.name,
            "part": p.name,
            "devastating": bool(getattr(self, "_dev_active", None)),
            "power": power,
            "roll": round(rolled, 2),
            "bracket": bracket["label"],
            "mult": bmult,
            "capped": capped, "cap_kind": str((cap or {}).get("kind") or "pin") if capped else "",
            "scale": scale,
            "res_scale": rscale,
            "damage_taken": round(taken, 2),
            "damage_before": round(dmg_b, 2), "damage_after": round(p.damage, 2),
            "damage_added": round(p.damage - dmg_b, 2),
            "res_before": round(res_b, 2), "res_after": round(p.resistance, 2),
            "res_start": round(float(getattr(p, "start_resistance", res_b) or res_b), 2),
            "cond_before": round(cond_b, 2), "cond_after": round(self.condition(p), 2),
            "health_mult": hmult, "vital": vital, "health_loss": round(health_loss, 2), "zero_ramp": round(zramp, 2), "long_ramp": round(lramp, 2),
            "health_raw": round(raw_loss, 2), "softened": round(raw_loss - health_loss, 2) > 0.01,
            "res_overflow": round(res_over, 2),
            "wear_math": wear_math, "wear_cap": round(wear_cap, 2) if wear_cap is not None else None,
            "res_floor": p.resistance <= r["resistance"]["minimum"] and res_b - wear < r["resistance"]["minimum"],
            "health_before": round(hp_b, 2), "health_after": round(defender.health, 2),
            "max_health": defender.max_health,
            "pain_tier": pain_a["label"],
            "pain_tier_changed": pain_a["label"] != pain_b["label"],
            "reaction_guide": pain_a["reaction"],
            "health_tier": htier_a["label"],
            "health_tier_changed": htier_a["label"] != htier_b["label"],
        }

    def _part_added(self, before, taken):
        """damage.part_curve: how much of a blow's damage the PART's number takes. Up to `knee` (300%: devastated) all
        of it; past that it climbs ever more slowly (a closed form of d(damage)/d(blow) = soften / (soften + over the
        knee)), so a ruined part's number stops running into the thousands. Health always uses the full blow."""
        pc = (self.rules.get("damage") or {}).get("part_curve") or {}
        if not pc.get("enabled", True) or taken <= 0:
            return taken
        knee, soft = float(pc.get("knee", 300)), max(1.0, float(pc.get("soften", 150)))
        lin = max(0.0, min(taken, knee - before))     # the part of the blow below the knee counts in full
        y0, x = max(0.0, before + lin - knee), taken - lin
        if x <= 0:
            return lin
        return lin + (((soft + y0) ** 2 + 2 * soft * x) ** 0.5 - soft) - y0

    def _maybe_numb(self, d, p, taken, was_numb):
        """numbness: a devastated part that takes a hard blow can go NUMB for a little while (1-3 beats): the pain
        cuts out, replaced by a dead, strange heaviness and shock. Then it wears off and the pain floods back. Returns
        the beats it goes numb for, or 0."""
        cfg = self.rules.get("numbness") or {}
        if not cfg.get("enabled", False) or was_numb or d.eliminated or getattr(p, "numb_cool", 0):
            return 0
        if p.damage < float(cfg.get("at_damage", 300)) or taken < float(cfg.get("hard_at", 40)):
            return 0
        if not self._chance(float(cfg.get("chance", 0.3)), f"{poss_word(d.name)} {p.name.lower()} going numb",
                            "it goes NUMB", "it doesn't"):
            return 0
        p.numb = self.rng.randint(int(cfg.get("beats_min", 1)), int(cfg.get("beats_max", 3)))
        p.numb_new = True
        return p.numb

    def numb_tick(self):
        """Numb parts count down; when one wears off the feeling comes back (numb_end), and it can't go numb again
        for numbness.cooldown beats."""
        cfg = self.rules.get("numbness") or {}
        events = []
        for f in self.fighters.values():
            for p in f.parts.values():
                if getattr(p, "numb_new", False):
                    p.numb_new = False
                    continue
                if int(getattr(p, "numb", 0) or 0) > 0:
                    p.numb -= 1
                    if p.numb <= 0:
                        p.numb_cool = int(cfg.get("cooldown", 4))
                        if not f.eliminated:
                            events.append({"type": "numb_end", "fighter": f.name, "part": p.name,
                                           "damage": round(p.damage, 2)})
                elif int(getattr(p, "numb_cool", 0) or 0) > 0:
                    p.numb_cool -= 1
        return events

    def condition(self, p, res=None):
        """How sound a part is, on the resistance scale, for how much a blow hurts it and how it looks
        (resistance.relative). A part that starts at or above `sound` (85: a normal, sturdy part) is judged by its
        resistance as it is. One that starts BELOW it (a soft throat, a thin fin, some fighters' weak spots) is judged
        against its own start: untouched it counts as sound, so a gentle brush there is nothing much; every point it
        loses is a bigger share of what it had, so it turns sensitive fast. Off: resistance as it is."""
        res = float(p.resistance if res is None else res)
        cfg = self.rules["resistance"].get("relative") or {}
        start = float(getattr(p, "start_resistance", 0) or 0)
        sound = float(cfg.get("sound", 85))
        if not cfg.get("enabled", True) or start <= 0 or start >= sound:
            return res
        return min(sound, res * sound / start)

    def vulnerability(self, p):
        """resistance.relative.vulnerability: a part that starts below `sound` takes this much more from a blow,
        (sound / start) ** vulnerability (0 = none). Untouched it is sound but fragile: real blows land harder there."""
        cfg = self.rules["resistance"].get("relative") or {}
        start = float(getattr(p, "start_resistance", 0) or 0)
        sound = float(cfg.get("sound", 85))
        v = float(cfg.get("vulnerability", 0.35) or 0)
        if not cfg.get("enabled", True) or start <= 0 or start >= sound or v <= 0:
            return 1.0
        return round((sound / start) ** v, 4)

    def resistance_mults(self, res, bracket=None):
        """(damage mult, health mult) for a part at this resistance. With resistance.smooth on, a gradient: straight
        lines between anchor points (resistance, mult, health_mult), flat beyond the first and last, so a few points
        of resistance change a hit a little instead of halving it at a bracket edge. Off: the bracket's own numbers."""
        r = self.rules["resistance"]
        sm = r.get("smooth") or {}
        if not sm.get("enabled", False):
            b = bracket or tier_for(res, r["brackets"])
            return float(b["mult"]), float(b.get("health_mult", 1.0))
        pts = sorted((float(a), float(m), float(h)) for a, m, h in (sm.get("points") or []))
        if not pts:
            b = bracket or tier_for(res, r["brackets"])
            return float(b["mult"]), float(b.get("health_mult", 1.0))
        x = float(res)
        if x <= pts[0][0]:
            return pts[0][1], pts[0][2]
        if x >= pts[-1][0]:
            return pts[-1][1], pts[-1][2]
        for (x0, m0, h0), (x1, m1, h1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                t = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
                return round(m0 + (m1 - m0) * t, 4), round(h0 + (h1 - h0) * t, 4)
        return pts[-1][1], pts[-1][2]

    def _soften_loss(self, defender, raw, power=None):
        """health.soft_cap: a hit on a ruined part costs a lot of health, but no single blow and no single beat swings
        wildly. Past per_hit (a share of HER OWN full health, rolled up or down by jitter, and smaller for a light
        hit: power_ref) the extra health levels off toward at most `room` x that cap more, however big the raw number
        (a true soft cap, not a share of the excess); the same for everything that lands in one beat past per_beat.
        A devastating blow gets a far looser cap (moves.devastating: cap_mult, room_mult). Nothing changes below."""
        cfg = self.rules.get("health", {}).get("soft_cap") or {}
        if not cfg.get("enabled", True) or raw <= 0 or not defender.max_health:
            return raw
        dv = getattr(self, "_dev_active", None)
        dcfg = (self.rules.get("moves") or {}).get("devastating") or {}
        room = float(cfg.get("room", 0.6))
        loose = float(dcfg.get("cap_mult", 3.0)) if dv else 1.0
        room *= float(dcfg.get("room_mult", 2.0)) if dv else 1.0

        def soft(x, cap):
            if cap <= 0 or x <= cap:
                return x
            r = room * cap
            return cap + (r * (1 - math.exp(-(x - cap) / r)) if r > 0 else 0.0)
        jit = float(cfg.get("jitter", 0.15) or 0)
        roll = self.rng.uniform(1 - jit, 1 + jit) if jit > 0 else 1.0
        light = 1.0
        ref = float(cfg.get("power_ref", 40) or 0)
        if ref > 0 and power is not None and not dv:
            # a light knock (a jolt getting up, a tumble, a press) can't cost what a full blow can, ruined part or not
            light = max(float(cfg.get("power_floor", 0.25)), min(1.0, float(power) / ref))
        loss = soft(raw, float(cfg.get("per_hit", 0.05)) * defender.max_health * loose * roll * light)
        tally = self.__dict__.setdefault("beat_loss", {})
        before = tally.get(defender.name, 0.0)
        cap = float(cfg.get("per_beat", 0.12)) * defender.max_health * loose
        out = soft(before + loss, cap) - soft(before, cap)
        tally[defender.name] = before + loss
        return out

    def part_weight(self, part_name):
        """How much a part matters to overall health (health.part_weights): a word in its name decides first (the
        longest that fits: "tail base" before "tail"), then its body region; 1 when nothing is listed or it is off."""
        cfg = self.rules.get("health", {}).get("part_weights") or {}
        if not cfg.get("enabled", True):
            return 1.0
        low = str(part_name).lower()
        best = None
        for w, v in (cfg.get("words") or {}).items():
            if not str(w).startswith("_") and re.search(r"\b" + re.escape(str(w).lower()) + r"s?\b", low):
                if best is None or len(w) > len(best[0]):
                    best = (w, float(v))
        if best:
            return best[1]
        return float((cfg.get("regions") or {}).get(body_region(part_name), 1.0))

    def _floor(self, health):
        m = self.rules["health"].get("minimum")
        return health if m is None else max(m, health)

    def _health_pct(self, f):
        return 100.0 * f.health / f.max_health if f.max_health else 0.0

    def injury_causes(self, key, n=3):
        """What hurt one part ("Fighter|Part"), oldest first, as the notes tell it: the causes that did the most
        damage to it and the latest one, at most n. The same few everywhere it is told, so they never disagree."""
        log = [c for c in self.injury_log.get(key, []) if c]
        amt = (self.__dict__.get("injury_amt") or {}).get(key) or {}
        if len(log) <= n or not amt:
            return log[-n:]
        keep = set(sorted(log[:-1], key=lambda c: -float(amt.get(c, 0)))[:n - 1]) | {log[-1]}
        return [c for c in log if c in keep]

    def _count(self, kind, name):
        """One more time this has happened to her this fight (the story may count: "thrown twice")."""
        key = f"{kind}|{name}"
        self.tally[key] = int(self.tally.get(key, 0)) + 1

    def times(self, kind, name):
        return int(self.tally.get(f"{kind}|{name}", 0))

    # ---------- all-or-nothing support for multi-action beats ----------
    def snapshot_state(self):
        return copy.deepcopy((self.fighters, self.holds, self.next_hold_id, self.turn, self.involved,
                              self.pins, self.positions, self.downed, self.since_pin, self.momentum,
                              self.move_log, self.last_pin_end, self.injury_log, self.plan, self.facing,
                              dict(getattr(self, "_last_reposition", {})),
                              self._fresh_down, self._fresh_status,
                              self.pressed, self.alliances, self._pending_events, list(getattr(self, "rolls", [])),
                              self.tally, getattr(self, "weather", {}), list(getattr(self, "arena_marks", [])),
                              getattr(self, "chronicle", None) or self.new_chronicle(),
                              list(self.__dict__.get("setups") or []), self.rng.getstate(),
                              {**{k: self.__dict__.get(k) for k in self._SNAP_EXTRA if k in self.__dict__},
                               "~event_rng": self.event_rng.getstate()}))

    # Every attribute the engine ever holds belongs to exactly one of these groups (sim/regress.py checks it, so a new
    # piece of state can't be forgotten by /undo and saves):
    # the main snapshot tuple above (save and load handle each of these by name)
    _SNAP_FIELDS = ("fighters", "holds", "next_hold_id", "turn", "involved", "pins", "positions", "downed", "since_pin",
                    "momentum", "move_log", "last_pin_end", "injury_log", "plan", "facing", "_last_reposition",
                    "_fresh_down", "_fresh_status", "pressed", "alliances", "_pending_events", "rolls", "tally",
                    "weather", "arena_marks", "chronicle", "setups")
    # engine state that lives outside the main snapshot tuple but must be undone (and saved) with it
    _SNAP_EXTRA = ("encouraged", "ever_down", "air_passes", "out_reason", "broken_props", "broke_free_at", "hit_turn", "hauled", "aim_log", "weak_aim", "won_turn",
                   "injury_amt", "lying_at", "lying_on", "burn_spot", "_story_prev", "_story_now", "_story_pinned", "_story_turned",
                   "_tac_status", "_last_event", "_forced_event", "_overbalanced", "_rock_open", "_slow_not_cold",
                   "_last_manhandle", "last_pin_shape", "fight_record", "game_plans", "gap", "_gap_before")
    # ...those of them that __init__ sets up: put back to this when a snapshot or save doesn't have them (never removed)
    _SNAP_INIT = {"_last_event": None, "_forced_event": None, "fight_record": {}, "game_plans": {}}
    # scratch for one attack or one beat (set fresh before it is read), or the session and its settings: never undone
    _NOT_SNAPPED = ("_aim_miss", "_chain_on", "_confusion_passed", "_dev_active", "_dive_now", "_feint_open",
                    "_force_dodge", "_juggle", "_last_stand_now", "_overcommit_now", "_pummel_now", "_strike_flavor",
                    "_sustain_now", "_source", "_knock_on", "_tac_before", "beat_loss", "sub_window", "pin_window",
                    "nudges", "_windows_ready", "_pre_rolls", "directed", "ordered", "dice_mode", "lucky",
                    "_sub_open_all", "_force_dev", "_force_dev_used", "_ticking", "_dominate_turn", "_passive", "_overcommit_why", "_quirks_now", "_ambush_try",
                    "rules", "roster", "roster_species", "scenes", "scene_cfg", "scene_name", "scene", "movedex",
                    "variants", "variant_of", "settings_applied", "_seed0", "rng", "event_rng")

    def _put_back_extra(self, src, keep=()):
        """The _SNAP_EXTRA state from a snapshot or a save: what it has goes back, what it lacks goes away (or back to
        its starting value). keep: names to leave as they are when `src` doesn't have them."""
        for k in self._SNAP_EXTRA:
            if k in src:
                self.__dict__[k] = _from_json(src[k])
            elif k in keep:
                continue
            elif k in self._SNAP_INIT:
                self.__dict__[k] = copy.deepcopy(self._SNAP_INIT[k])
            else:
                self.__dict__.pop(k, None)

    def restore_state(self, snap):
        self.beat_loss = {}   # a beat taken back takes its health.soft_cap tally with it
        (self.fighters, self.holds, self.next_hold_id, self.turn, self.involved,
         self.pins, self.positions, self.downed, self.since_pin, self.momentum, self.move_log, self.last_pin_end,
         self.injury_log, self.plan, self.facing, self._last_reposition, self._fresh_down, self._fresh_status,
         self.pressed, self.alliances, self._pending_events, self.rolls, self.tally, self.weather, self.arena_marks,
         self.chronicle, self.setups, rng, *more) = copy.deepcopy(snap)
        extra = more[0] if more else {}
        self._put_back_extra(extra)     # state added later than the tuple: put back what was there, drop what wasn't
        if extra.get("~event_rng"):
            self.event_rng.setstate(extra["~event_rng"])   # (an undone arena event comes the same way when replayed)
        self._knock_on = []
        self.rng.setstate(rng)

    def note_roll(self, what, p, r, result):
        """Write down a roll that was made somewhere else (the director's nudges)."""
        if 0 < p < 1:
            self.rolls.append({"what": what, "chance": round(float(p), 4), "roll": round(float(r), 4),
                               "ok": r < p, "result": result})
            del self.rolls[:-60]

    VARIETY = {
        # how an outcome plays out when the result itself is already decided. Weights; rules.json "variety" overrides.
        "charge_stands": {"staggers": 4, "leans": 3, "knee": 2, "rebounds": 2},
        "keeps_feet": {"staggers": 4, "knee": 3, "sways": 3, "braces": 2},
        # low_health: what she does at the very end of her strength, by itself
        "low_idle": {"sway": 3, "lean": 3, "blink": 3, "spit": 2, "test_leg": 2, "breath": 3},
        "low_watch": {"closes_in": 3, "waits": 3, "circles": 3},
        "low_squirm": {"crawl_at": 3, "crawl_away": 2, "claw": 3, "curl": 3},
        "low_tell": {"shaking": 3, "breath": 3, "dead_limb": 2},
        "foe_read": {"finish": 3, "wary": 2, "still_standing": 3},
        "charge_falls": {"on her side": 30, "face-down": 25, "face-up": 15, "sitting up": 30},
        "dodge": {"sidestep": 4, "duck": 3, "spring_back": 3, "turn_aside": 2, "twist": 2},
        "hold_break": {"wrench": 3, "pry": 2, "slip": 2, "shove": 2},
        "tumble": {"rolling": 4, "skidding": 3, "bouncing": 2, "cartwheeling": 2},
        "hold_strain": {"pry": 3, "twist": 3, "claw": 2, "brace": 2},
        "sub_slip": {"turn": 3, "yank": 3, "fist": 2, "kick": 2},
        "struggle": {"buck": 3, "bridge": 3, "twist": 3, "limb": 3, "kick": 2, "squirm": 2, "headbutt": 2,
                     "bite": 2, "shrimp": 2, "roll": 2, "claw": 2, "pry": 2, "tuck": 2, "limp": 1, "reach": 1,
                     "power": 1},
        "getup_fail": {"gives_out": 4, "slips": 2, "dizzy": 2, "breath": 2},
        "getup_rise": {"push": 4, "roll": 2, "lean": 3, "lurch": 2},
        "bite_rock": {"drag": 3, "shake": 2, "yank": 2, "wrench_free": 2},
        # fighting the urge to tap out (finish.submission): one sign a beat, from the set for how near she is
        "tap_tell_urge": {"fist": 3, "claws": 2, "grit": 3, "shake_head": 2, "hiss": 2, "breathe": 2},
        "tap_tell_urge2": {"reach": 3, "yank": 3, "fist_shake": 3, "squeeze_eyes": 2, "count": 2},
        "tap_tell_first": {"twitch": 3, "curl": 3, "word": 2, "breath": 2, "tail": 2, "eyes": 2},
        "tap_tell_closer": {"yank_back": 3, "touch": 3, "hover": 3, "pin_paw": 2, "half_word": 2, "bite": 2, "grab_ground": 2},
        "tap_tell_edge": {"shake_hard": 3, "flat": 3, "stops_fighting": 3, "no_aloud": 2, "tears": 2, "hangs": 2, "laugh": 1},
        "tap_reason": {"pride": 3, "anger": 3, "not_her": 3, "slip": 2, "stubborn": 2, "plea": 2},
        "tap_dark": {"grey": 3, "roar": 2, "heavy": 2, "claw": 3, "count": 2},
        "tap_holder": {"cold": 3, "respect": 3, "pity": 2, "impatient": 2, "worry": 2, "tired": 2},
        "tap_way": {"slap": 4, "frantic": 3, "cry": 3, "word": 2, "body": 2},
        # (since build 275) her arms trapped in coils round her body: no paw can reach anything to tap with
        "tap_way_trapped": {"tail": 3, "said": 3, "slack": 2},
        "takedown": {"tackle": 3, "leg_hook": 3, "sweep": 3, "hip_throw": 3, "shoulder_drive": 2, "drag_down": 2,
                     "spin_down": 2, "trip_back": 2, "pull_forward": 2, "ride_down": 2},
    }

    def vary(self, key, skip=(), scale=None):
        """Pick HOW an already-decided outcome plays out (one of several ways that are all true to the result).
        skip: ways that aren't true to it this time (rolling onto her front when she already lies on it); scale:
        weights multiplied for ways she is less able to do now (springing back on wrecked legs)."""
        table = dict(self.VARIETY.get(key, {}))
        over = self.rules.get("variety", {}).get(key)
        if isinstance(over, dict):
            table = {k: float(v) for k, v in over.items() if not str(k).startswith("_") and float(v) > 0} or table
        table = {k: v for k, v in table.items() if k not in skip} or table
        if scale:
            table = {k: v * float(scale.get(k, 1.0)) for k, v in table.items()}
        names = list(table)
        return self.rng.choices(names, [table[n] for n in names])[0]

    def _chance_r(self, p, what, yes="yes", no="no"):
        """Like _chance, but also returns the number rolled (for near misses)."""
        r = self.rng.random()
        ok = r < p
        if 0 < p < 1:
            self.rolls.append({"what": what, "chance": round(float(p), 4), "roll": round(r, 4), "ok": ok,
                               "result": yes if ok else no})
            del self.rolls[:-60]
        return ok, r

    def _chance(self, p, what, yes="yes", no="no"):
        """One roll of the dice, written down: True with probability p. Uses exactly one random number, like the
        plain comparison it replaces. Certain outcomes (0% or 100%) aren't listed."""
        r = self.rng.random()
        ok = r < p
        if 0 < p < 1:
            self.rolls.append({"what": what, "chance": round(float(p), 4), "roll": round(r, 4), "ok": ok,
                               "result": yes if ok else no})
            del self.rolls[:-60]
        return ok

    # ---------- moves and types ----------
    def dex_move(self, name):
        """A move from moves.json (forgiving about case and small misspellings), or None."""
        want = " ".join(str(name).lower().replace("-", " ").split())
        by = {" ".join(m["name"].lower().replace("-", " ").split()): m for m in self.movedex}
        if want in by:
            return by[want]
        close = difflib.get_close_matches(want, list(by), n=1, cutoff=0.8)
        return by[close[0]] if close else None

    def learn(self, fighter, name):
        """Lend a fighter a move for this fight (kept in saves of this fight, never written to fighters.json)."""
        f = self.get(fighter)
        m = self.dex_move(name)
        if m is None:
            raise ValueError(f"no move called '{name}' in moves.json (try /moves {str(name)[:4]})")
        if any(x["name"].lower() == m["name"].lower() for x in f.moves):
            raise ValueError(f"{f.name} already knows {m['name']}")
        f.moves.append(dict(m, learned=True))
        return m

    def forget(self, fighter, name):
        f = self.get(fighter)
        m = self.find_move(f.name, name)
        if m is None:
            raise ValueError(f"{f.name} doesn't know '{name}'")
        f.moves = [x for x in f.moves if x is not m]
        return m

    def find_move(self, fighter, name):
        """The fighter's move called `name` (forgiving about case and small misspellings), or None."""
        if not name:
            return None
        moves = self.get(fighter).moves
        want = " ".join(str(name).lower().split())
        for m in moves:
            if m["name"].lower() == want:
                return m
        close = difflib.get_close_matches(want, [m["name"].lower() for m in moves], n=1, cutoff=0.8)
        return next((m for m in moves if m["name"].lower() == close[0]), None) if close else None

    def type_multiplier(self, move_type, defender_types):
        chart = self.rules.get("moves", {}).get("type_chart", {})
        mult = 1.0
        for t in defender_types:
            mult *= chart.get(move_type, {}).get(t, 1.0)
        return mult

    def move_math(self, attacker, defender, move):
        """Effective power = power x type effectiveness x targeting (x same-type bonus if configured)."""
        a, d = self.get(attacker), self.get(defender)
        cfg = self.rules.get("moves", {})
        tmult = self.type_multiplier(move["type"], d.types)
        target = move.get("target", "targeted")
        aim = cfg.get("targeting", {}).get(target, 1.0)
        stab = cfg.get("same_type_bonus", 1.0) if move["type"] in a.types else 1.0
        extras = self.power_extras(a, d, move["type"], move)
        limb = self.limb_mult(a, move)
        if limb:
            extras = extras + [limb]
        wx = self.weather_mult(move["type"])
        if wx:
            extras = extras + [wx]
        vu = self.vulnerable(a, d, move)
        if vu:
            extras = extras + [vu]
        if getattr(self, "_overcommit_now", None) == a.name:
            extras = extras + [("overcommitted, sloppy with tiredness",
                                float(((self.rules.get("moves") or {}).get("exhaustion_mistakes") or {}).get("mult", 0.6)))]
        if getattr(self, "_last_stand_now", None) == a.name:
            extras = extras + [("last stand", float(((self.rules.get("moves") or {}).get("last_stand") or {}).get("mult", 1.5)))]
        if self.spike_ok(a, d, move):
            # she is falling (carried up and dropped, or knocked up into the air) and this comes straight down on
            # her from above: a dive, a charge, or a held stream that drives her into the ground faster than she
            # would fall (flight.spike.mult, in place of the dive's own edge)
            extras = extras + [("driven straight down out of the air",
                                float(((self.rules.get("flight") or {}).get("spike") or {}).get("mult", 1.4)))]
        elif self.has(a, "airborne") and not self.is_ranged(move) and not self.has(d, "airborne") \
                and move.get("target") not in ("status", "hold", "self") and not move.get("carry"):
            dm = float((self.rules.get("flight") or {}).get("dive_mult", 1.3))
            n = self.air_speed(a)
            if n:
                sp = (self.rules.get("flight") or {}).get("speed") or {}
                extras = extras + [(f"diving from above, with the speed of {n} pass{'es' if n != 1 else ''} behind it",
                                    round(dm * (1 + float(sp.get("per_pass", 0.1)) * n), 3))]
            else:
                extras = extras + [("diving from above", dm)]
        elif move.get("leap_from") and self.has(d, "airborne") and not self.has(a, "airborne"):
            lcfg = (self.rules.get("flight") or {}).get("leap") or {}
            extras = extras + [(f"leaping at her from {move['leap_from']}, all her weight in it",
                                float(lcfg.get("mult", 1.2)))]
        elif self.has(a, "airborne") and self.has(d, "airborne") and not self.is_ranged(move) \
                and move.get("target") not in ("status", "hold", "self") and not move.get("carry") \
                and (getattr(self, "_juggle", None) or {}).get("who") != d.name:
            # two flyers closing on each other in the air (flight.air_pass): the speed of both is in the blow
            ap = (self.rules.get("flight") or {}).get("air_pass") or {}
            if ap.get("enabled", True):
                n = self.air_speed(a)
                sp = (self.rules.get("flight") or {}).get("speed") or {}
                extras = extras + [("closing on her at speed in the air"
                                    + (f", {n} pass{'es' if n != 1 else ''} of speed behind it" if n else ""),
                                    round(float(ap.get("mult", 1.15)) * (1 + float(sp.get("per_pass", 0.1)) * n), 3))]
        q = self.quirk(a, "overwhelming")
        if q and target not in ("self", "status") and float(move.get("power") or 0) >= float(q.get("big_from", 22)):
            extras.append(("her overwhelming strength", float(q.get("power_mult", 1.12))))   # (since build 280)
        if move.get("improvised"):
            stab = 1.0    # a technique she makes up on the spot isn't one of her own type's moves: no same-type bonus
        xm = 1.0
        for _, m in extras:
            xm *= m
        effective = round(move["power"] * tmult * aim * stab * xm, 2)
        if target == "self":
            tmult = 1.0     # a move she uses on herself (Protect, Mirror Coat, a weather move) doesn't meet the foe's type
            effective = round(move["power"] * aim * stab * xm, 2)
        word = ("no effect" if tmult == 0 else "super effective" if tmult > 1
                else "not very effective" if tmult < 1 else "normal")
        return {"name": move["name"], "type": move["type"], "base": move["power"],
                "vs": f"{move['type']} vs {'/'.join(d.types) or 'typeless'}", "type_mult": tmult,
                "target": target, "target_mult": aim, "stab": stab, "effective": effective,
                "effectiveness": word, "about": move.get("about", ""), "improvised": bool(move.get("improvised")),
                "extras": extras, "extra_mult": xm,
                # (whose it is: her opponent's state for a blow on her while she's open, nobody's for the weather,
                # the attacker's for the rest)
                "extras_of": [d.name if x is vu else "" if x is wx else a.name for x in extras],
                # (what is_ranged reads, so the record of a blow says ranged or close the way the move does: Close
                # Combat is a spread delivered close, Flame Wheel a charge)
                **({"ranged": move["ranged"]} if "ranged" in move else {}),
                **({"charge": True} if move.get("charge") else {}),
                **({"weapon": move["weapon"], "conjured_now": bool(move.get("conjured_now"))} if move.get("weapon") else {})}

    def _use_move(self, fighter, move):
        """Limited moves (fighters.json 'uses') run out. Raises if none are left; otherwise uses one."""
        if move.get("improvised") or move["name"] not in fighter.move_uses:
            return
        if fighter.move_uses[move["name"]] <= 0:
            raise ValueError(f"{fighter.name} has no {move['name']} left (used up). Pick another move")
        fighter.move_uses[move["name"]] -= 1

    def uses_left(self, fighter, move_name):
        return self.get(fighter).move_uses.get(move_name)

    def spike_ok(self, a, d, move):
        """Is this blow a SPIKE: the one she is falling past (caught in the air by a chain, or carried up and
        dropped) comes down on her from above, a dive, a charge, or a held stream, driving her into the ground?"""
        sp = (self.rules.get("flight") or {}).get("spike") or {}
        if not sp.get("enabled", True) or not move or move.get("target") in ("status", "self", "hold") or a is d:
            return False
        jg = getattr(self, "_juggle", None) or {}
        if jg.get("who") != d.name or not self.has(a, "airborne") or jg.get("mid"):
            return False     # (mid: a slash on the way down, with more blows still to come before she lands)
        if move.get("charge") or (self.is_ranged(move) and int(getattr(self, "_sustain_now", 0) or 0) > 0):
            return True
        return not self.is_ranged(move) and bool(jg.get("close_spike", True))

    GRIPS = re.compile(r"talon|foot|feet|hand|claw|paw", re.I)

    def can_carry(self, a, d):
        """Can `a` snatch `d` up and carry her into the air (any winged fighter in the air with talons, feet or hands
        to grip with)? (ok, why not)"""
        a, d = (x if hasattr(x, "parts") else self.get(x) for x in (a, d))
        if not self.has(a, "airborne"):
            return False, f"{a.name} isn't in the air"
        if not any(self.GRIPS.search(p) for p in a.parts):
            return False, f"{a.name} has nothing to grip with"
        if self.has(d, "airborne"):
            return False, f"{d.name} is in the air herself"
        if self.pinned_by(d.name) or self.pinning(d.name):
            return False, f"{d.name} is in a pin"
        if any(d.name in (h.attacker, h.defender) for h in self.holds.values()):
            return False, f"{d.name} is in a hold"
        return True, ""

    def wieldable_types(self, who):
        """The types she can improvise with: Normal, Fighting, her own types, and the types of the moves she knows."""
        f = self.get(who)
        return list(dict.fromkeys(["Normal", "Fighting"] + list(f.types or []) + [str(m.get("type")) for m in f.moves
                                                                                 if m.get("type")]))

    def can_wield_type(self, who, mtype):
        return str(mtype or "Normal").lower() in {t.lower() for t in self.wieldable_types(who)}

    def conjure(self, who, weapon, mtype):
        """moves.conjure: she makes a weapon of her own element (an ice blade frozen out of the water, a whip of
        water) and holds it for conjure.beats beats (ARMED): her improvised blows with it land as its type, x
        conjure.power_mult. Only from a type she can wield; a new one replaces the old."""
        cfg = (self.rules.get("moves") or {}).get("conjure") or {}
        if not cfg.get("enabled", True):
            raise ValueError("conjured weapons are off (rules.json moves.conjure)")
        f = self.get_active(who)
        if not self.can_wield_type(f.name, mtype) or str(mtype).lower() in ("normal", "fighting"):
            raise ValueError(f"{f.name} can only conjure a weapon from an element she has "
                             f"({', '.join(t for t in self.wieldable_types(f.name) if t not in ('Normal', 'Fighting'))})")
        f.learned["weapon"] = {"name": " ".join(str(weapon).split()[:5]), "type": str(mtype).title()}
        self.set_status(f, "armed", int(cfg.get("beats", 3)))
        return f.learned["weapon"]

    ELEMENT_WORDS = re.compile(
        r"\b(?:water\w*|aqua|hydro|jet|splash\w*|spray\w*|stream\w*|wave|bubbl\w*|soak\w*|drench\w*|spout\w*|"
        r"fire|flam\w*|blaz\w*|burn\w*|ember\w*|heat\w*|scorch\w*|smoke|ice|icy|frost\w*|freez\w*|froz\w*|"
        r"chill\w*|cold|snow|hail|spark\w*|electr\w*|thunder\w*|shock\w*|static|lightning|volt\w*|"
        r"leaf|leaves|vine\w*|seed\w*|petal\w*|pollen|spore\w*|poison\w*|venom\w*|toxic|acid\w*|sludge|"
        r"rock\w*|stone\w*|mud\w*|sand\w*|earth\w*|psychic|psi|mind|telekine\w*|shadow\w*|dark\w*|ghost\w*|"
        r"dragon\w*|draconic|steel|metal\w*|iron|fairy|moon\w*|wind|gust\w*|air|bug|silk|web|"
        r"beam|blast|pulse|bolt|ray|breath|glow\w*|energy|aura)\b", re.I)

    def improvised_move(self, name, mtype, severity, target="targeted", about="", who=None):
        """A move the director invents on the spot. Power comes from how hard it lands. A fighter who is ARMED with a
        conjured weapon hits with it: its type, and moves.conjure.power_mult harder."""
        table = self.rules.get("moves", {}).get("improvised_power", {"light": 15, "solid": 25, "heavy": 35, "brutal": 45})
        wpn = (self.get(who).learned.get("weapon") if who and self.has(self.get(who), "armed") else None)
        if wpn:
            mtype = wpn.get("type") or mtype
        sev = str(severity or "solid").lower()
        sev = {"firm": "solid", "crushing": "heavy"}.get(sev, sev)
        chart = self.rules.get("moves", {}).get("type_chart", {})
        mtype = next((t for t in chart if t.lower() == str(mtype or "Normal").lower()), "Normal")
        name = " ".join(str(name or "improvised strike").split()[:5]).title()
        if (not wpn and mtype not in ("Normal", "Fighting") and self.rules.get("moves", {}).get("plain_body", True)
                and not self.ELEMENT_WORDS.search(f"{name} {about or ''}")):
            # moves.plain_body: a head twist or a knee strike with nothing of her element in it is a plain blow,
            # whatever type the director gave it (it must not soak her or fill her mouth with water)
            mtype = "Normal"
        # close unless it plainly crosses the distance: two quick jabs on two parts are not a beam (a spread move is
        # otherwise taken for one, and a ranged move reaches a fighter in the air)
        words = f"{name} {about or ''}".lower()
        far = bool(re.search(r"\b(?:beam|blast|pulse|jet|stream|spray|breath|wave|ray|bolt|gust|shot|spit|burst|"
                             r"torrent|volley|flamethrower|bubbles?)\b", words)) and not re.search(
            r"\b(?:punch|kick|bite|claw|slash|jab|knee|elbow|headbutt|tackle|slam|stomp|rake|chop|swipe|grab|"
            r"shove|ram|body)\b", words)
        power = table.get(sev, table.get("solid", 25))
        if wpn:
            power = round(power * float(((self.rules.get("moves") or {}).get("conjure") or {}).get("power_mult", 1.2)), 2)
        out = {"name": name, "type": mtype, "power": power,
               "target": target if target in ("targeted", "spread") else "targeted",
               "about": about or "an improvised attack", "improvised": True, "ranged": far}
        if wpn:
            out["weapon"] = wpn["name"]
        return out

    def move_attack(self, attacker, *args, **kw):
        """A named move (or an improvised `move` dict): see _move_attack. A confused attacker who passes her confusion
        check and attacks anyway has it on the result (through_confusion), so the story can show her doing it dizzy."""
        self._confusion_passed = None
        res = self._move_attack(attacker, *args, **kw)
        if self._confusion_passed and isinstance(res, dict) and not res.get("confused_self_hit"):
            res["through_confusion"] = True
        self._confusion_passed = None
        return res

    def _move_attack(self, attacker, defender, move_name, parts, count=1, flavor="", move=None, no_spill=False,
                     enforce=False, sustain=0, against="", charge_into="", pummel=False, feint=False):
        """A named move (or an improvised `move` dict). targeted: one part (count repeats);
        spread: the listed parts; whole_body: every body part the defender has."""
        a, d = self.get_active(attacker), self.get_active(defender)
        if a is d:
            raise ValueError(f"{a.name} can't attack themselves")
        move = move or self.find_move(a.name, move_name)
        if move is None:
            raise ValueError(f"{a.name} doesn't know '{move_name}'. Moves: {', '.join(m['name'] for m in a.moves)}")
        if move.get("target") == "hold":
            raise ValueError(f"{move['name']} is a hold; use it to start a hold or pin")
        self._can_act(a, enforce)
        d_up = self.has(d, "airborne")    # (before the blow: knocking her out of the sky must not make it a dive)
        busy = self.busy_with(a, move)
        if enforce and busy:
            raise ValueError(f"{poss_word(a.name)} {busy[0]} are {'clamped on' if busy[0] == 'jaws' else 'locked in her hold on'} "
                             f"{poss_word(busy[1])} {busy[2].lower()}: she can't {move['name']} with them while they "
                             f"hold. Strike with something free, or let go first (hold_release)")
        dead = self.dead_limb(a, move)
        if enforce and dead:
            raise ValueError(f"{poss_word(a.name)} {dead.lower()} isn't answering her this beat (low_health.tells): "
                             f"she can't {move['name']} with it. Use something else")
        if enforce and move.get("charge") and ((self.rules.get("holds") or {}).get("busy_limbs") or {}).get(
                "enabled", True):
            mine = [h for h in self.holds.values() if h.attacker == a.name and not h.grab]
            if mine:
                # (since build 266) a charge is her whole body launched across the gap: locked onto someone in a hold
                # she has no run-up to make (the build-264 log had an Aqua Jet thrown from inside a chicken wing)
                raise ValueError(f"{a.name} is locked onto {mine[0].defender} in her "
                                 f"{mine[0].sub or 'hold'}: {move['name']} is a full-body charge, and she has no "
                                 f"room to launch one while she holds her. Strike with something free, or let go first "
                                 f"(hold_release)")
        if enforce and move.get("charge") and (a.name in self.downed or self.pinned_by(a.name)):
            where = "PINNED" if self.pinned_by(a.name) else "ON THE GROUND"
            raise ValueError(f"{a.name} is {where}: {move['name']} is a running, full-body charge, and she can't launch one "
                             f"from there. Use something she can do where she lies (a bite, a kick, a tail strike, a "
                             f"blast), or let her get up first")
        self._no_friendly_fire(a, [d], enforce)
        self._pinned_reach(a, [d.name], enforce)
        if enforce:
            far = self.held_reach_block(a, d, move, [d.part(p).name for p in (parts or []) if isinstance(p, str)
                                                     and match_part(list(d.parts), p)])
            if far:
                raise ValueError(far)
            far = self.holder_reach_block(a, d, move, [d.part(p).name for p in (parts or []) if isinstance(p, str)
                                                       and match_part(list(d.parts), p)])
            if far:
                raise ValueError(far)
        leap = None
        if move.get("leap_from") and self.has(d, "airborne") and not self.has(a, "airborne") \
                and not self.is_ranged(move) and not move.get("carry") and move.get("target") not in ("status", "self", "hold"):
            lcfg = (self.rules.get("flight") or {}).get("leap") or {}
            if enforce and not lcfg.get("enabled", True):
                raise ValueError("leaps from high ground are turned off (/set flight.leap.enabled true)")
            if enforce and (a.name in self.downed or self.pinned_by(a.name) or self.pinning(a.name)):
                raise ValueError(f"{a.name} has to be on her feet and free to climb and leap")
            if enforce and a.energy < float(lcfg.get("energy", 10)):
                raise ValueError(f"{a.name} is too worn out to climb and leap (needs {lcfg.get('energy', 10)} energy)")
            leap = self._leap_spot(move.get("leap_from"))
            if leap is None and enforce:
                raise ValueError(f"there is nothing high enough in {self.scene_word('place', 'the arena')} to climb and "
                                 f"leap from")
            if leap:
                move = dict(move, leap_from=leap)
        if enforce and self.has(d, "airborne") and not self.has(a, "airborne") and not self.is_ranged(move) \
                and move.get("target") not in ("status", "self") and not leap:
            raise ValueError(f"{d.name} is IN THE AIR: {move['name']} can't reach her up there. Use a ranged move (a "
                             f"beam, a blast, a stream), wait for her to dive, or climb high ground and leap at her "
                             f"(\"leap_from\": one of: {', '.join(self.high_ground()) or 'nothing here is high enough'})")
        if enforce and move.get("carry") and not self.has(a, "airborne"):
            raise ValueError(f"{move['name']} carries her up into the air: {a.name} has to be in the air to do it "
                             f"(\"reposition\": \"take off\" first)")
        if enforce and move.get("carry") and self.pinned_by(d.name):
            raise ValueError(f"{d.name} is pinned: nobody can carry her off")
        still_against = (self.pressed.get(d.name) or {}).get("surface")  # a follow-up before she falls from a charge
        mine = [m for who, m in self.move_log if who == a.name][-2:]
        limit = int(self.rules.get("moves", {}).get("max_same_move_in_a_row", 2) or 0)
        if (enforce and limit and len(mine) >= limit and all(m == move["name"] for m in mine[-limit:])
                and a.name not in (getattr(self, "ordered", None) or ())):   # a player's own choice is hers to repeat
            raise ValueError(f"{a.name} just used {move['name']} {limit} times in a row. Pick a DIFFERENT move or an "
                             f"improvised technique (or let the opponent act)")
        self.move_log = (self.move_log + [(a.name, move["name"])])[-20:]
        energy_before = a.energy
        self._spend(a, self.energy_cost(move), enforce, move["name"])
        self._use_move(a, move)
        self._source = f"{poss_word(a.name)} {move['name']}"
        self._feint_open = None
        self._pummel_now = bool(pummel)
        # confusion first: a fighter who hurts herself throws no feint and spends no last stand on it
        confused = self._confusion(a, move, enforce, energy_before)
        if confused:
            return confused
        # a chain that ends here in a dodge (chain_break) ends it: no feint or clash gets the link through
        ending = bool(getattr(self, "_force_dodge", False))
        fe = self._feint(a, d, move) if feint and enforce and not ending else None
        self._last_stand_now = self._last_stand(a, move) if enforce else None
        self._overcommit_now = self._overcommit(a, move) if enforce and not self._last_stand_now else None
        self._sustain_now = int(sustain or 0)
        self._strike_flavor = str(flavor or "")       # (which limb she throws it with, when the order says: limb_mult)
        math = self.move_math(a.name, d.name, move)
        self._strike_flavor = ""
        spiking = self.spike_ok(a, d, move)
        self._sustain_now = 0
        target = math["target"]
        if target == "self":   # a stance or a weather move: on herself or the whole arena, not on the opponent
            return self._self_move(a, d, move, flavor, energy_before)
        guard = self._guarded(a, d, move)
        if guard:
            guard["flavor"] = flavor
            if self._last_stand_now:
                # (it went into a Protect: her once-a-fight last stand isn't spent, and doesn't hang over her next move)
                a.learned["last_stand_used"] = False
                self._last_stand_now = None
            return guard
        if target == "status":  # no damage: the move's effects either land or the target dodges
            dodge = self.dodge_roll(a, d, "targeted") if enforce else None
            self._attacked(a.name, [d.name], landed=False)
            res = {"type": "instant", "attacker": a.name, "defender": d.name, "defenders": [d.name],
                   "uses_left": a.move_uses.get(move["name"]), "energy": [round(energy_before), round(a.energy)],
                   "flavor": flavor, "move": math, "hit_count": 0, "hits": [], "status_move": True, "tags": []}
            if dodge:
                res.update(dodge)
            else:
                aimed = next((x for x in (parts or []) if isinstance(x, str) and match_part(list(d.parts), x)), None)
                res["status_applied"] = self._status_from_move(
                    d, move, force_roll=True, at=match_part(list(d.parts), aimed) if aimed else None)
                res["missed"] = not res["status_applied"]
            return res
        self._aim_miss = None
        if target == "whole_body":
            plan = list(d.parts)
        else:
            names = []
            for p in parts:
                n = d.part(p).name
                if n not in names:
                    names.append(n)
            if not names:
                raise ValueError(f"{move['name']} needs a body part to hit")
            if enforce and target == "targeted" and len(names) == 1 and not pummel:
                # one part aimed at: the smaller or harder to reach it is, the likelier the blow lands beside it
                # instead (moves.aim). A path of parts (a rake from cheek to hip) is not an aim: every part is hit
                landed = self._aim(a, d, names[0])
                if landed != names[0]:
                    self._aim_miss = {"aimed": names[0], "landed": landed}
                    names = [landed]
            elif enforce and target == "targeted" and len(names) > 1 and not pummel:
                # a path of parts is not an aim, but a small, hard-to-reach part on it (an eye, an ear, the throat)
                # is still no sure thing: each of those is rolled like an aim, and lands beside itself if it misses
                # (moves.aim.path_below: parts at or below this ease are rolled; 0 = never)
                below = float(((self.rules.get("moves") or {}).get("aim") or {}).get("path_below", 0.6))
                out = []
                for nm in names:
                    landed = self._aim(a, d, nm) if self.aim_ease(nm) <= below else nm
                    if landed != nm and not getattr(self, "_aim_miss", None):
                        # only one stretch of a blow across several parts strays: the rest lands as aimed
                        self._aim_miss = {"aimed": nm, "landed": landed, "path": True}
                    if landed not in out:
                        out.append(landed)
                names = out
            k_ = max(1, int(count or 1))
            # several blows over several named parts: they go round the parts in order, the count in all
            plan = ([names[i % len(names)] for i in range(k_)] if k_ > 1 and len(names) > 1 else [names[0]] * k_) \
                if target == "targeted" else names
        powers = [math["effective"]] * len(plan)
        pum = None
        if pummel and target == "targeted" and len(plan) > 1:
            # in a grab: the same close move thrown again and again with no room to wind up. Each lands lighter than
            # one full blow, and every one after the first costs more breath
            gcfg = self.rules.get("grapple", {})
            cap = int(gcfg.get("pummel_max", 0) or 0)          # 0 = no fixed length
            hard = int(gcfg.get("pummel_hard_cap", 10) or 0)   # a distant limit; 0 = none at all
            each = float(gcfg.get("pummel_power", 0.6))
            extra = float(gcfg.get("energy_per_extra_hit", 3))
            asked, ended = len(plan), None
            start_p, step_p = float(gcfg.get("pummel_end_start", 0.25)), float(gcfg.get("pummel_end_step", 0.10))
            where = pummel if isinstance(pummel, str) else "grab"
            fz = gcfg.get("frenzy") or {}
            # now and then a pummel doesn't stop: blow after blow, mostly on the same spot or two (grapple.frenzy);
            # otherwise one on someone lying on the ground runs a little shorter (ground_end_mult)
            frenzy = bool(enforce and fz.get("enabled", True) and self._chance(
                float(fz.get("ground_chance", 0.1) if where == "down" else fz.get("chance", 0.08)),
                f"{poss_word(a.name)} pummel turning into a frenzy", "FRENZY", "no"))
            end_mult = float(fz.get("end_mult", 0.3)) if frenzy else (
                float(gcfg.get("ground_end_mult", 1.0)) if where == "down" else 1.0)
            if frenzy:
                extra *= float(fz.get("energy_mult", 0.5))     # past tiredness: it costs her less breath than it should
            if enforce and start_p <= 0 and step_p <= 0:
                n = min(asked, cap or hard or asked)      # no chance to end: the count asked for stands (the old rule)
            elif enforce:
                # nobody decides the length beforehand: after the second blow, every further one may be the last.
                # The chance grows with each blow, a tired attacker ends sooner, a fresh defender spoils it sooner
                n = 2
                while True:
                    if (cap and n >= cap) or (hard and n >= hard):
                        ended = "limit"
                        break
                    if a.energy < extra * n:
                        ended = "out of breath"
                        break
                    p = min(0.95, self.run_break_chance(a, d, n - 2, start_p, step_p) * end_mult)
                    if p > 0 and self.rng.random() < p:
                        ended = "spoiled" if self.rng.random() < 0.5 + 0.4 * (self.strength(d) - self.strength(a)) / 100.0 \
                            else "out of breath"
                        # most pummels are one-sided: she only takes it. Now and then the one being hit ANSWERS: her
                        # own blow lands and that is what stops it (grapple.pummel_answer_chance, of the pummels
                        # she spoils)
                        ans = float(gcfg.get("pummel_answer_chance", 0.5))
                        if ended == "spoiled" and ans > 0 and self.rng.random() < ans:
                            ended = "answered"
                        break
                    n += 1
            else:
                n = min(asked, hard) if hard else asked     # your own command: the count you typed
            while enforce and n > 1 and a.energy < extra * (n - 1):
                n -= 1
            a.energy = max(0.0, a.energy - extra * (n - 1))
            if len(names) > 1:
                # the parts were named, in order (by you, or the director following your words): blow by blow
                plan = [names[k % len(names)] for k in range(n)]
            elif enforce and not getattr(self, "directed", False):
                # nobody said where each blow goes: after the first, the dice keep it on the same spot or move it
                plan = [names[0]]
                for k in range(1, n):
                    if frenzy:     # she keeps going back to the same place, or the one right beside it
                        plan.append(self.next_target(d.name, plan[-1], f"pummel blow {k + 1}",
                                                     stay=float(fz.get("stay_chance", 0.7)), near_only=True))
                    else:
                        plan.append(self.next_target(d.name, plan[-1], f"pummel blow {k + 1}"))
            else:
                plan = [names[0]] * n
            powers = [round(math["effective"] * each, 2)] * n
            pum = {"count": n, "each": each, "power": powers[0], "ended": ended, "answer": [], "parts": list(plan),
                   "where": where, "frenzy": frenzy,
                   "against": (self.pressed.get(d.name) or {}).get("surface") or "",
                   "lying": self.facing_of(d.name) if d.name in self.downed else None}
        spill_cfg = self.rules.get("moves", {}).get("auto_spill", {})
        if target == "targeted" and len(names) > 1 and not pum and int(count or 1) <= 1 \
                and spill_cfg.get("carry_next_to_only", True):
            # a strike drags across parts that touch: each carried-over part has to be next to the main part or to
            # one already on its path (auto_spill.carry_next_to_only); the others are dropped, not hit
            path = names[:1]
            for n_ in names[1:]:
                if any(n_ in sum(neighbor_parts(list(d.parts), p_), []) for p_ in path):
                    path.append(n_)
            if len(path) < len(names):
                math["carry_dropped"] = [n_ for n_ in names if n_ not in path]
                names = path
        auto_n = int(spill_cfg.get("parts", 0) or 0)
        auto_n = {"one": 0, "few": 2, "many": 4, "all": 6}.get(self.plan.get("targeting", ""), auto_n)
        # a real blow jars what's around it; so does a beam or a blast aimed at one spot (a spread move given one part)
        if target in ("targeted", "spread") and len(names) == 1 and int(count or 1) == 1 and auto_n > 0 and not no_spill:
            # a real blow jars what's around it: the parts next to the target take a lighter knock
            same, near = neighbor_parts(list(d.parts), names[0])
            self.rng.shuffle(same)
            self.rng.shuffle(near)
            # an eye, an ear, a jaw sits IN the head: the head itself usually feels the blow too
            head = next((p for p in same if p.lower() == "head"), None)
            if head and names[0].lower() != "head" and self.rng.random() < 0.75:
                same = [head] + [p for p in same if p != head]
            # collateral is a roll too: most solid blows jar something round them, some land clean
            jar_n = (self.rng.randint(1, auto_n) if self.rng.random() < float(spill_cfg.get("chance", 0.75)) else 0)
            extra = (same[:1] + near + same[1:])[:jar_n]
            if extra:
                jar = round(move["power"] * math["type_mult"] * math["stab"] * math["extra_mult"]
                            * float(spill_cfg.get("factor", 0.5)), 2)
                plan += extra
                powers += [jar] * len(extra)
                math["auto_spill_parts"] = extra
                math["auto_spill_effective"] = jar
                math["auto_spill_factor"] = float(spill_cfg.get("factor", 0.5))
        if target == "targeted" and len(names) > 1 and not pum and int(count or 1) <= 1:
            # a strike that drags across neighboring parts: main part x2, the parts it carries over x1
            spill = round(move["power"] * math["type_mult"] * math["stab"] * math["extra_mult"]
                          * self.rules.get("moves", {}).get("targeting", {}).get("spread", 1.0), 2)
            plan += names[1:]
            powers += [spill] * (len(names) - 1)
            math["spillover_parts"] = names[1:]
            math["spillover_effective"] = spill
        fed = bool(fe and fe["bit"])
        clash = self._clash(a, d, move, math) if enforce and not pum and not fed and not ending else None
        if clash and clash["outcome"] == "through":
            powers = [round(pw * clash["share"], 2) for pw in powers]
        self._dive_now = bool(self.has(a, "airborne") and not self.has(d, "airborne") and not self.is_ranged(move)
                              and move.get("target") not in ("status", "hold", "self") and not move.get("carry"))
        short = None
        if leap and enforce:
            lcfg = (self.rules.get("flight") or {}).get("leap") or {}
            reach = min(0.9, float(lcfg.get("reach", 0.55)) * (0.5 + 0.5 * max(0.0, min(1.0, self.strength(a) / 100.0))))
            if not self._chance(reach, f"{a.name} reaching {d.name} with the leap from {leap}", "she reaches her",
                                "falls short"):
                short = {"dodged": True, "dodge_chance": round(1 - reach, 2), "counter_hits": [],
                         "manner": "the leap falls short of her", "leap_short": True}
        try:
            dodge = short or (None if (clash or fed) else (self.dodge_roll(a, d, target, move["name"]) if enforce else None))
        finally:
            self._dive_now = False
        guard, dev = None, None
        if enforce and not clash and not dodge and not pum and not fed:
            guard = self._guard_roll(a, d, move, target)
        if guard and guard["kind"] == "block":
            # caught on the guard: the blow lands once on the blocking part (each blow, for a flurry), and nothing
            # jars past it (the knocks around the target never happen)
            plan = [guard["part"]] * max(1, int(count or 1)) if target == "targeted" else [guard["part"]]
            powers = [round(powers[0] * guard["share"], 2)] * len(plan)
            for k in ("auto_spill_parts", "auto_spill_effective", "auto_spill_factor", "spillover_parts",
                      "spillover_effective"):
                math.pop(k, None)
            charge_into = ""     # caught on a guard: she isn't driven anywhere
        shield = self.guarded_wound(d) if enforce and not fed and not pum else None
        if shield and not guard:
            gp = shield[0]
            cfgv = (self.rules.get("moves") or {}).get("guarding_wound") or {}
            powers = [round(pw * (float(cfgv.get("covered_mult", 0.85)) if p == gp else
                                  float(cfgv.get("open_mult", 1.1)) if self.left_open(gp, p) else 1.0), 2)
                      for p, pw in zip(plan, powers)]
        missed = None
        if enforce and move.get("charge") and (dodge or (guard and guard["kind"] == "deflect")):
            missed = self._missed_charge(a, d, move, math, charge_into)
        if dodge or (clash and clash["outcome"] != "through") or (guard and guard["kind"] == "deflect"):
            hits = []
        else:
            blocked = bool(guard and guard.get("kind") == "block")   # caught on a guard: no perfect angle
            dev = (self._devastating_roll(a, d, move, plan) if enforce and not pum and math["type_mult"] != 0
                   and not blocked
                   and move.get("target") not in ("status", "self") else None)
            if dev:
                powers = [round(pw * dev["mult"], 2) for pw in powers]
                self._dev_active = dev
            try:
                hits = [] if math["type_mult"] == 0 else [self._apply_damage(d, p, pw) for p, pw in zip(plan, powers)]
            finally:
                self._dev_active = None
            for h in hits[1:]:
                if h["part"] in (math.get("auto_spill_parts") or ()):
                    h["jarred"] = True     # only knocked by a blow aimed beside it (sized as such in the notes)
            if hits and not move.get("improvised"):    # she remembers what has landed on her (learning)
                felt = d.learned.setdefault("moves", {})
                felt[f"{a.name}|{move['name']}"] = felt.get(f"{a.name}|{move['name']}", 0) + 1
                wcfg = (self.rules.get("learning") or {}).get("wary") or {}
                if any(h.get("damage_after", 0) >= float(wcfg.get("at_damage", 150)) for h in hits):
                    d.learned.setdefault("wary", {})[f"{a.name}|{move['name']}"] = True   # that one hurt her badly
        sustained = None
        if hits and int(sustain or 0) > 1 and move.get("sustainable"):
            if against and (d.name in self.downed or self.pin_on(d.name) is not None) and \
                    short_phrase(against) != short_phrase((self.pressed.get(d.name) or {}).get("surface") or ""):
                against = ""       # down or pinned on the ground: no tree or wall behind her to grind her into
            sustained = self._sustain(a, d, move, plan, powers, int(sustain), against, enforce)
            hits = hits + [h for pulse in sustained["pulses"] for h in pulse["hits"]]
            if not sustained["pulses"] and not sustained.get("broke"):
                sustained = None     # out of breath after the first blast: a plain hit, nothing held
        charged = None
        if hits and charge_into and not sustained:
            charged = self._charge(a, d, move, plan, powers, charge_into)
            hits = hits + charged["hits"]
        ground = None
        behind = self.scene_prop_for(against) if against else None
        if hits and behind and not sustained and not charged and target == "targeted" \
                and not self.pinned_by(d.name) and not self.has(d, "airborne") and d.name not in self.downed:
            # blows driven home with her back to something solid in this arena (held against it, or cornered): each
            # one grinds her into it, and it may give way under her. Only the blows really thrown count, not the
            # parts a single blow carries over to; something that isn't here, or has already broken, does nothing
            # as many grinds as blows really thrown (a pummel the dice ended early drives her in fewer times)
            nb_ = min(int(pum["count"]) if pum else max(1, int(count or 1)) if int(count or 1) > 1 else 1, 4)
            ground = self._grind(a, d, behind, nb_, struck=list(plan[:nb_]))
            hits = hits + ground["hits"]
        gback = None
        if hits and not sustained and not charged and not ground and d.name in self.downed and target == "targeted":
            # lying on the ground, a blow driven down into her drives her into the ground too: what she lies on takes
            # a share of it (her back when she's face-up). moves.ground_back
            nb_ = min(int(pum["count"]) if pum else max(1, int(count or 1)) if int(count or 1) > 1 else 1, 4)
            gback = self._ground_back(a, d, move, hits, nb_, struck=list(plan[:nb_]))
            if gback:
                hits = hits + gback["hits"]
        self._attacked(a.name, [d.name], landed=bool(hits))
        flavor = self._flavor_fits_move(flavor, move)
        res = {"type": "instant", "attacker": a.name, "defender": d.name, "defenders": [d.name],
               "uses_left": a.move_uses.get(move["name"]), "energy": [round(energy_before), round(a.energy)],
               "flavor": flavor, "move": math, "hit_count": len(hits), "hits": hits,
               "tags": self._tags(hits) if hits else ["no_effect"]}
        if clash:
            res["clash"] = clash
        if hits and dev:
            res["devastating"] = dev
        if hits and self._aim_miss and any(h.get("part") == self._aim_miss["landed"] for h in hits):
            res["aim"] = dict(self._aim_miss)      # aimed at one part, landed on the one beside it (moves.aim)
        if fe:
            res["feint"] = fe
        if self.quirk(a, "cocky") and hits and max(float(h.get("damage_taken", 0)) for h in hits) >= float(
                (self.quirk(a, "cocky") or {}).get("big_hit", 30)):
            a.learned["landed_big"] = self.turn
        if self._overcommit_now:
            res["overcommit"] = True
            res["overcommit_why"] = getattr(self, "_overcommit_why", "tired")
            self.set_status(a, "off_balance", 1)      # she overbalances on it
            self._overbalanced = getattr(self, "_overbalanced", set()) | {a.name}   # (her own lunge, not turned aside)
        self._overcommit_now = None
        if self._last_stand_now and hits:
            res["last_stand"] = True
            a.energy = 0.0          # everything she had left went into it
            if isinstance(res.get("energy"), list) and res["energy"]:
                res["energy"] = [res["energy"][0], 0]     # (the header shows it: emptied, not just the move's cost)
        self._last_stand_now = None
        self._feint_open = None
        if shield and hits and not guard:
            res["guarding"] = {"part": shield[0], "open_side": self.open_side_word(shield[0])}
        if guard:
            res["guard"] = guard
            if guard["kind"] == "deflect":     # told and shown like a dodge, with its own manner
                res.update(dodged=True, manner="deflected", dodge_chance=guard["chance"], counter_hits=[])
        if missed:
            res["missed_charge"] = missed
        if pum:
            res["pummel"] = pum
            if pum.get("ended") == "answered" and hits and not dodge:
                # the held fighter's own short blow, at what she can reach of the one working on her
                reach = [x for x in a.parts if body_region(x) in ("head", "neck", "chest", "shoulder", "fore_up", "fore_low",
                                                                  "belly")] or list(a.parts)
                power = round(self.power_for("instant", self._cfg("evasion").get("counter_severity", "solid")) * pum["each"], 2)
                keep_src, self._source = self._source, f"{poss_word(d.name)} answering blow"
                pum["answer"] = [self._apply_damage(a, self.rng.choice(reach), power)]
                self._source = keep_src
        if dodge:
            res.update(dodge)
        elif hits:
            if sustained:
                res["sustain"] = sustained
                res["knock_on"] = sustained.get("knock_on") or []
            if ground:
                res["ground_into"] = ground
                res["knock_on"] = (res.get("knock_on") or []) + (ground.get("knock_on") or [])
            if gback:
                res["ground_back"] = gback
            if charged:
                res["charge"] = charged
                res["knock_on"] = (res.get("knock_on") or []) + (charged.get("knock_on") or [])
            if still_against:
                res["target_against"] = still_against
            mouth = self._into_mouth(a, d, move, hits, bool(sustained))
            if mouth:
                res["into_mouth"] = mouth
            blocked = bool(guard and guard.get("kind") == "block")   # a blocked blow passes on no status
            at = next((h.get("part") for h in hits if h.get("part") and h.get("defender", d.name) == d.name), None)
            res["status_applied"] = ((self._status_from_move(d, move, at=at) if not blocked else [])
                                     + self._restrain(a, d) + (mouth or [])
                                     + list((res.get("charge") or {}).get("hazard_status") or [])
                                     + list((res.get("sustain") or {}).get("hazard_status") or []))
            launch = self._launch_from_move(move)
            fcfg = self.rules.get("flight") or {}
            if launch and self.has(d, "airborne") and not d.eliminated and not move.get("grab_carry") \
                    and not move.get("carry") and self._rights_herself(d, move, launch, fcfg):
                res["righted"], launch = launch, None
            if launch:
                res["auto_launch"] = launch
            grab = move.get("grab_carry") and not move.get("carry") and not d.eliminated
            if grab:
                # a winged fighter in the air seizes her with whatever she grips with and tries to haul her up:
                # the stronger and fresher her wings, the likelier (flight.carry)
                cc = fcfg.get("carry") or {}
                ok, _ = self.can_carry(a, d)
                wing = 1.0 / (1.0 + self.wing_damage(a) / float(cc.get("wing_per", 150)))
                ch = float(cc.get("chance", 0.7)) * (0.5 + 0.5 * max(0.0, min(1.0, self.strength(a) / 100.0))) * wing \
                    * (0.5 + 0.5 * max(0.0, min(1.0, 1.0 - self.strength(d) / 100.0 + 0.5)))
                if ok and self._chance(min(0.95, ch), f"{a.name} hauling {d.name} up into the air", "she lifts her",
                                       "too heavy"):
                    a.energy = max(0.0, a.energy - float(cc.get("energy", 6)))
                    move = dict(move, carry=True)
                elif ok:
                    res["carry_failed"] = True     # she gets a grip but can't get her off the ground
            if move.get("carry") and not d.eliminated:
                # snatched up in her talons, carried up, and dropped: the higher, the harder she lands
                h = self.rng.choice(list((fcfg.get("drop_heights") or {"a body's length up": "solid",
                                                                       "twice her height": "heavy",
                                                                       "high over the arena": "brutal"}).items()))
                res["carried"] = {"height": h[0]}
                res["auto_launch"], res["drop_severity"] = "launched", h[1]
            kfa = fcfg.get("knock_from_air") or {}
            fall = (min(float(kfa.get("max", 0.9)), float(kfa.get("base", 0.25))
                        + float(kfa.get("per_damage", 0.004)) * self._fall_damage(hits, float(kfa.get("spread_share", 0.3)))
                        + float(kfa.get("per_wing_damage", 0.0025)) * self.wing_damage(d))
                    if self.has(d, "airborne") and not res.get("carried") and not d.eliminated else 0.0)
            hm = kfa.get("health_mult") or {}
            if fall > 0 and hm:
                # a strong flyer rides out a blow that would bring a worn one down (knock_from_air.health_mult: at full
                # strength, at half, and at nothing left, eased between)
                pct = max(0.0, min(100.0, self._health_pct(d)))
                full, half, empty = (float(hm.get(k, v)) for k, v in (("full", 1.0), ("half", 1.0), ("empty", 1.0)))
                m = half + (full - half) * (pct - 50) / 50 if pct >= 50 else empty + (half - empty) * pct / 50
                fall = min(float(kfa.get("max", 0.9)), fall * m)
            if fall > 0 and self._chance(fall, f"{d.name} knocked out of the air", "she falls", "she stays up"):
                # hit in the air with nothing under her: the blow knocks her out of the sky (harder, the more it hurt
                # and the worse her wings are: flight.knock_from_air)
                d.status.pop("airborne", None)
                res["grounded"] = True
                res["grounded_wing"] = self.wing_damage(d) >= float((fcfg.get("strain") or {}).get("from", 100))
                res["fell_from_air"] = not res.get("auto_launch")   # no throw rolled: she just fell (labels only)
                res["auto_launch"], res["drop_severity"] = res.get("auto_launch") or "thrown", res.get("drop_severity") or "solid"
        if hits and not d.eliminated:
            jolt = self._jolts(d, hits, move, a)
            if jolt:
                res["status_applied"] = (res.get("status_applied") or []) + jolt
        if hits and not d.eliminated and not dodge and not (guard and guard.get("kind") == "block") \
                and not any(res.get(k) for k in ("charge", "sustain", "ground_into", "ground_back", "into_mouth",
                                                  "auto_launch", "grounded", "carried", "righted")):
            reel = self._stumble(a, d, move, hits)
            if ((self.rules.get("moves") or {}).get("stumble") or {}).get("enabled", True):
                res["moved"] = "stagger" if reel and reel.get("status") else "rock" if reel else "still"
            if reel and reel.get("status"):
                res["status_applied"] = (res.get("status_applied") or []) + [reel]
            elif reel:
                res["rocked"] = reel
        qo = self.quirk(a, "overwhelming")
        if qo and hits and not dodge and float(move.get("power") or 0) >= float(qo.get("big_from", 22)):
            self.quirk_moment(a, "overwhelming", f"{a.name} hits with her whole enormous strength behind it: unhurried, "
                                                 f"sure of herself, and it lands like a falling tree")
        if hits and not d.eliminated and not dodge:
            side = self._side_spill(d, move, hits, res)
            if side:
                hits.extend(side)
                res["side_hits"] = [h["part"] for h in side]
                res["hit_count"] = len(hits)
        if hits and not move.get("improvised"):
            rc = self._recoil(a, move, math)
            if rc:
                res["recoil"] = rc
        if hits and not d.eliminated:
            back = self._reflect(a, d, move, math)
            if back:
                res["reflected"] = back
        if res.get("carried"):
            self.set_status(a, "airborne", max(a.status.get("airborne", 0), 2))   # she is up there with her
        elif self.has(a, "airborne") and not self.is_ranged(move) and not d_up \
                and move.get("target") not in ("status", "hold") and not move.get("carry"):
            if (getattr(self, "_juggle", None) or {}).get("who") == d.name:
                res["dive"], res["climbs"] = True, True    # she struck her in the air: there is no one to catch her
            else:
                self._after_dive(a, d, res, bool(hits))
                if res.get("climbs") and hits and not res.get("dodged"):
                    self._strafe(a, d, res, math)
        elif leap:
            self._leap_after(a, d, res, leap, bool(hits) and not res.get("dodged"))
        elif self.has(a, "airborne") and d_up and not self.is_ranged(move) \
                and move.get("target") not in ("status", "hold", "self") and not move.get("carry") \
                and (getattr(self, "_juggle", None) or {}).get("who") != d.name \
                and ((self.rules.get("flight") or {}).get("air_pass") or {}).get("enabled", True):
            self._air_pass(a, d, res, bool(hits) and not res.get("dodged"))
        if spiking and hits and not res.get("dodged"):
            res["spiked_down"] = True     # driven down into the ground (director: her landing is the harder for it)
        return res

    def _charge(self, a, d, move, plan, powers, into):
        """A charge that doesn't stop at the hit: the attacker keeps driving the defender backward for some distance
        and slams her into something in the scene. Her back takes the surface, and the attacker's own body crushes
        against the parts the charge struck, pressing her between the two. The surface may break (she goes down
        with it); otherwise she is left pressed against it until the end of the beat, when she usually crumples
        (see _crumple_tick), so a follow-up in the same beat lands before she falls."""
        cfg = self.rules.get("moves", {}).get("charge", {})
        into = short_phrase(into)
        why = None
        if not (move.get("charge") or move.get("improvised")):
            why = f"{move['name']} isn't a charging move"
        elif a.name in self.downed or self.pinned_by(a.name):
            why = f"{a.name} isn't on her feet"
        elif d.name in self.downed or self.pinned_by(d.name):
            why = f"{d.name} is on the ground, so there is nobody to drive anywhere"
        elif self.is_broken(into):
            why = f"{into} already lies broken: there is nothing standing there to drive her into"
        if why:
            return {"skipped": why, "into": into, "hits": []}
        table = self.rules["severity"].get("environment") or self.rules["severity"]["instant"]
        distances = cfg.get("distances") or {"a few strides": 0.8, "a dozen strides": 1.0, "the whole way across": 1.25}
        dist = self.rng.choice(list(distances))
        struck = list(dict.fromkeys(plan))
        # her whole body hits it, but first what is behind the spot the charge struck (her back behind her chest,
        # the struck arm itself...): _backing
        behind_ = [x for x in self._backing(d, struck[0]) if x in d.parts]
        back = (behind_ + self.landing_parts(d.name, 3, avoid=struck + behind_))[:3]
        # she is carried off across the arena: every grip on her and by her ends, and so does anything the charger held
        loose = (self._lose_grip(d.name, f"{d.name} was driven across the arena", on_her=True)
                 + self._lose_grip(a.name, f"{a.name} charged off after {d.name}"))
        a.energy = max(0.0, a.energy - float(cfg.get("energy", 8)))
        slam = round(float(table.get(cfg.get("slam_severity", "heavy"), 25)) * float(distances[dist]), 2)
        drive_hits, sheath = [], self.sheath_of(move)
        if sheath:
            # a charge wrapped in its element (Aqua Jet's water, Flame Wheel's fire, Spark's current) never leaves
            # her: it is still on her the whole way back, and the element keeps working on what it struck and what
            # is round it, pressing, stinging, scouring, until the move is done (moves.charge.sheath)
            scfg = cfg.get("sheath") or {}
            same, near = neighbor_parts(list(d.parts), struck[0])
            self.rng.shuffle(same)
            self.rng.shuffle(near)
            around = (same[:1] + near + same[1:])[:int(scfg.get("parts", 3) or 0)]
            base = next((pw for p, pw in zip(plan, powers) if p == struck[0]), powers[0])
            each = round(base * float(scfg.get("power", 0.25)) * float(distances[dist]), 2)
            self._source = f"{poss_word(a.name)} {move['name']} still driving into her"[:70]
            drive_hits = [self._apply_damage(d, p, each) for p in [struck[0]] + around if each > 0]
        self._source = f"being driven into {into}"[:60]
        surface_hits = [self._apply_damage(d, p, slam) for p in back]
        first = {}
        for p, pw in zip(plan, powers):
            first.setdefault(p, pw)
        self._source = f"{poss_word(a.name)} body crushing her against {into}"[:70]
        factor = float(cfg.get("crush_factor", 0.5))
        crush_hits = [self._apply_damage(d, p, round(pw * factor, 2)) for p, pw in first.items()] if factor > 0 else []
        chances = cfg.get("break_chance") or self.rules.get("moves", {}).get("sustain", {}).get("break_chance", {})
        brk = self.break_chance(into, chances)
        out = {"into": into, "distance": dist, "slam_power": slam, "surface_hits": surface_hits, "crush_hits": crush_hits,
               "sheath": sheath, "drive_hits": drive_hits,
               "break_hits": [], "broke": False, "knock_on": loose, "facing": None,
               "hazard_status": self.hazard_effects(d, [into])}
        out["onward"], out["last"] = [], into
        last, power = into, slam
        if self._chance(brk, f"{into} breaking under {d.name}", "it BREAKS", "it holds"):
            self.mark_arena(f"{into} lies broken where {d.name} was driven through it")
            self._source = f"{into} breaking"[:60]
            out["break_hits"] = [self._apply_damage(d, p, float(table.get("heavy", 25))) for p in back]
            broke, seen = True, [into]
            # a charge with enough behind it does not stop at what it broke: she is driven on THROUGH it into the
            # next thing in the way, and the next, each a little less hard (moves.charge: carry_on_chance,
            # carry_on_power, max_obstacles; 0 = no limit but the arena's own)
            limit = int(cfg.get("max_obstacles", 3) or 0)
            while broke and (not limit or len(seen) < limit):
                go = (float(cfg.get("carry_on_chance", 0.35)) * (0.5 + 0.5 * max(0.0, min(1.0, self.strength(a) / 100.0)))
                      * float(distances[dist]) * 0.7 ** (len(seen) - 1))
                if go <= 0 or not self._chance(go, f"the charge carrying on through {last}", "it CARRIES ON", "it ends there"):
                    break
                nxt = self._next_obstacle(seen)
                if not nxt:
                    break
                seen.append(nxt)
                power = round(power * float(cfg.get("carry_on_power", 0.75)), 2)
                a.energy = max(0.0, a.energy - float(cfg.get("carry_on_energy", 4)))
                self._source = f"being driven on into {nxt}"[:60]
                step = {"into": nxt, "through": last, "slam_power": power,
                        "surface_hits": [self._apply_damage(d, p, power) for p in back], "break_hits": [], "broke": False}
                out["hazard_status"] = (out.get("hazard_status") or []) + (self.hazard_effects(d, [nxt]) or [])
                broke = self._chance(self.break_chance(nxt, chances), f"{nxt} breaking under {d.name}", "it BREAKS", "it holds")
                if broke:
                    self.mark_arena(f"{nxt} lies broken where {d.name} was driven through it")
                    self._source = f"{nxt} breaking"[:60]
                    step["break_hits"] = [self._apply_damage(d, p, float(table.get("heavy", 25))) for p in back]
                    step["broke"] = True
                out["onward"].append(step)
                last = nxt
            out["last"] = last
            out["went_through"] = True          # the FIRST obstacle broke
            out["broke"] = broke                # ... and so did the last one: she goes down with it
            if broke:
                out["facing"] = self.knock_down(d.name, parts=back, why=f"{d.name} went down with {last}")
                out["knock_on"] = loose + self._knock_on
                self._knock_on = []
            else:
                self.pressed[d.name] = {"surface": last, "by": a.name}
        else:
            self.pressed[d.name] = {"surface": into, "by": a.name}
        # a slam that hard shakes the arena: something may come down (arena.shake_chance; the arena's own event
        # that drops something: a stalactite, a branch, debris), on her, at the end of the beat
        shake = float((self.rules.get("arena") or {}).get("shake_chance", 0.2))
        falls = [e for e in (self.scene_cfg.get("events") or []) if isinstance(e, dict)
                 and re.search(r"fall|drop|collapse|come down|comes over|debris|icicle|branch", f"{e.get('name', '')} {e.get('text', '')}", re.I)]
        if falls and shake > 0 and not getattr(self, "_forced_event", None) and re.search(
                r"wall|stalagmite|pillar|column|boulder|tree|trunk|rock|cliff|pylon|beam|mast", out.get("last") or into, re.I) \
                and self._chance(shake, f"the slam into {out.get('last') or into} shaking something loose", "something comes down", "no"):
            self._forced_event = (self.rng.choice(falls), d.name, "shaken loose")
            out["shook_loose"] = True
        self.involved.update({a.name, d.name})
        self._count("charged", d.name)
        out["hits"] = (drive_hits + surface_hits + crush_hits + out["break_hits"]
                       + [h for st in out["onward"] for h in st["surface_hits"] + st["break_hits"]])
        return out

    SHEATH_WORDS = (("water", re.compile(r"water|wave|aqua|jet", re.I)), ("fire", re.compile(r"fire|flame|flare|blaze", re.I)),
                    ("electricity", re.compile(r"electri|spark|volt|current", re.I)))

    def sheath_of(self, move):
        """What a charge is wrapped in ("water", "fire", "electricity"), or None for a bare-bodied charge. A move
        says so with "sheathed": true (moves.json), or its description does ("water-sheathed", "cloaked in flames")."""
        if not move or not move.get("charge"):
            return None
        dex = self.dex_move(move.get("name", "")) or {}
        about = " ".join(str(x) for x in (move.get("about"), dex.get("about"), move.get("name")))
        flagged = move.get("sheathed", dex.get("sheathed"))
        if flagged is False:
            return None
        if not flagged and not re.search(r"sheath|wrapped|cloak|shroud|wheel of|electrified|like a waterfall", about, re.I):
            return None
        return next((name for name, rx in self.SHEATH_WORDS if rx.search(about)), "its element")

    def _next_obstacle(self, seen):
        """Something else in the arena for a charge to carry on into: one of the scene's props not yet used."""
        used = {short_phrase(x).lower() for x in seen}
        props = [short_phrase(p) for p in ((getattr(self, "scene_cfg", None) or {}).get("props") or [])]
        left = [p for p in props if p and p.lower() not in used]
        return self.rng.choice(left) if left else None

    # ---------- the arena ----------
    GENERIC_PROPS = (("boulder", "a boulder"), ("stalagmite", "a stalagmite"), ("wall", "the wall"), ("pillar", "a pillar"),
                     ("tree", "a tree"), ("rock", "a rock"), ("ledge", "the edge of the ledge"), ("fence", "the fence"),
                     ("column", "a column"), ("crate", "a crate"))

    @staticmethod
    def _load_scenes(here):
        """The arenas in scenes.json, in file order (a missing or broken file just means no list)."""
        try:
            data = load_json(os.path.join(here, "scenes.json")).get("scenes", {})
        except (OSError, ValueError, AttributeError):
            data = {}
        return {k: dict(v, name=k) for k, v in data.items() if not str(k).startswith("_") and isinstance(v, dict)}

    def find_scene(self, which):
        """A scene by its name, its number in the list (1 = the first), or a few words of its name or title."""
        w = norm(which)
        names = list(self.scenes)
        if w.isdigit() and 1 <= int(w) <= len(names):
            return names[int(w) - 1]
        if w in names:
            return w
        hit = [n for n in names if w and (w == norm(self.scenes[n].get("title", "")) or n.startswith(w))]
        hit = hit or [n for n in names if w and len(w) >= 3 and (w in n or w in norm(self.scenes[n].get("title", "")))]
        return hit[0] if len(hit) == 1 else None

    def set_scene(self, which, fallback=None):
        """Choose the arena: one from scenes.json (by name, number or title), or any other text as an arena of your
        own (no tracked hazards; things named in it can still be landed on). Returns the scene's record."""
        key = self.find_scene(which) if which else None
        if key is None and fallback is None:
            text = " ".join(str(which or "").split())
            if not text:
                raise ValueError("name a scene, or describe one")
            low = text.lower()
            self.scene_cfg = {"name": "custom", "title": "Your own scene", "text": text, "place": "the arena",
                              "ground": "the ground", "rough": "the rough ground", "slick": "the ground",
                              "props": [label for word, label in self.GENERIC_PROPS if word in low],
                              "hazards": [], "events": [], "ambience": ""}
        elif key is None:
            # no scenes file (or the saved choice is gone): the arena text that came with the fighters
            key = next(iter(self.scenes), None)
            self.scene_cfg = dict(self.scenes[key]) if key else {"name": "custom", "title": "The arena", "text": fallback,
                                                                  "place": "the arena", "hazards": [], "events": []}
        else:
            self.scene_cfg = dict(self.scenes[key])
        self.scene_name = self.scene_cfg.get("name", "custom")
        self.scene = self.scene_cfg.get("text") or fallback or "A fight."
        return self.scene_cfg

    LIES_ON = re.compile(r"\b(?:in|on|across|into|at the edge of|half in)\s+(?:the|a|an)\s+(?:[a-z'-]+\s+){0,2}?"
                         r"(shallows|water|pool|stream|sand|beach|mud|bank|shingle|pebbles|gravel|snow|ice|moss|"
                         r"grass|stone|rock|rocks|floor|deck|planks|shelf|ledge|slope|leaves|needles)\b", re.I)

    def ground_under(self, name):
        """What a fighter lies on as she gets up: where the director last placed her (in the shallows, on the
        sand), else the arena's own ground word."""
        on = (getattr(self, "lying_on", None) or {}).get(name)
        if on and name in self.downed:
            return on if re.match(r"(?i)(?:the|a|an)\b", on) else "the " + on
        text = getattr(self, "positions", None) or ""
        m = re.search(re.escape(name) + r"\s*:\s*([^;]*)", text, re.I) if text else None
        place = self.LIES_ON.search(m.group(1)) if m else None
        if place:
            return "the " + place.group(1).lower()
        return self.scene_word("ground")

    def scene_word(self, key, default=None):
        """A word the notes use for this arena: place, ground, rough, slick, ambience."""
        return self.scene_cfg.get(key) or default or {"place": "the arena", "ground": "the ground",
                                                       "rough": "the rough ground", "slick": "the ground",
                                                       "ambience": ""}.get(key, "")

    HIGH_GROUND = re.compile(r"boulder|stalagmite|logjam|half-sunk rock|turbine housing|catwalk|basalt column|outcrop|"
                             r"ice pillar|ice cliff|cliff|\boak\b|\bpine\b|\btree\b|trunk|derrick|crates|deckhouse|"
                             r"pillar|statue|ore cart|crystal cluster|gear housing|bell frame|roof beam|barnacled rock|"
                             r"groyne|altar stone|frozen boulder|timber prop", re.I)

    def high_ground(self):
        """Things in this arena a fighter on the ground can climb to leap at a flyer from (flight.leap): the scene's
        own "high_ground" list if it has one, else its props and hazards that stand high enough."""
        sc = self.scene_cfg or {}
        if sc.get("high_ground"):
            return list(sc["high_ground"])
        names = list(sc.get("props") or []) + [h.get("name", "") for h in sc.get("hazards") or []]
        out = []
        for n in names:
            if n and self.HIGH_GROUND.search(n) and n not in out:
                out.append(n)
        return out

    def _leap_spot(self, want):
        """The high ground named for a leap (the closest match among this arena's), or None."""
        spots = self.high_ground()
        if not spots:
            return None
        w = str(want or "").lower()
        if w and w not in ("true", "yes"):
            for s in spots:
                if s.lower() in w or w in s.lower():
                    return s
            words = set(re.findall(r"[a-z]{3,}", w)) - {"the", "and", "from", "off", "top"}
            for s in spots:
                if words & set(re.findall(r"[a-z]{3,}", s.lower())):
                    return s
        return self.rng.choice(spots)

    def scene_props(self):
        """Solid things in this arena to be thrown or driven into, or to lean on getting up. One that has broken in
        this fight (an arena mark says it lies broken) is gone: it can't be driven into or break again."""
        props = list(self.scene_cfg.get("props") or [])
        live = [p for p in props if not self.is_broken(p)]
        return live or (props and [self.scene_word("ground")]) or [self.scene_word("ground")]

    _TRAIL = re.compile(r"\s+(?:at|by|near|beside|on|in|along|under|below|above) (?:the |a |an )?.*$")

    def feature_for(self, surface):
        """The tracked feature (hazard) some words mean, read from the thing itself: "a boulder at the edge of the
        beach" is the boulder, not the beach. None if the arena tracks no such feature."""
        s = " ".join(str(surface or "").lower().replace("’", "'").split())
        if not s:
            return None
        for h in self.scene_cfg.get("hazards") or []:        # its own name, said exactly
            if s == str(h.get("name", "")).lower():
                return h
        if self._EDGE_OF.match(s) or s.split()[-1] in self._EDGE_WORDS:
            return None        # "the rim of the well", "the rock pool's edge": a thing of its own, not the well
        head = self._TRAIL.sub("", s)    # "a boulder at the edge" is a boulder or nothing tracked, never the edge
        # the thing itself is the last word: "the bell frame" is a frame, not the great bell
        return next((h for h in self.scene_cfg.get("hazards") or [] if any(
            head.endswith(str(w).lower()) or head.endswith(str(w).lower() + "s") for w in h.get("words") or [])), None)

    def feature_key(self, surface):
        """One name per feature, for remembering what has broken: the feature's own name, else the words given."""
        h = self.feature_for(surface)
        return str(h["name"]).lower() if h else short_phrase(str(surface or "")).lower().strip()

    @staticmethod
    def _is_solid(h):
        """Something to be driven into, pinned against or broken: upright, or with a break chance of its own, and
        not water, sand or snow that gives under her."""
        return bool(h) and not h.get("cushion") and bool(h.get("upright") or h.get("break") is not None)

    def is_broken(self, surface):
        """Has this thing in the arena already broken in this fight? Compared feature by feature, so breaking an
        ice pillar leaves the thin ice whole."""
        key = self.feature_key(surface)
        gone = {self.feature_key(g) for g in list(getattr(self, "broken_props", []) or [])
                + [m.split(" lies broken")[0] for m in getattr(self, "arena_marks", []) or [] if " lies broken" in m]}
        return bool(key) and key in gone

    def scene_prop_for(self, surface):
        """The arena's own solid thing that some words mean ("the oak" -> "an old oak", "the icicles"), or None if
        the arena has no such thing standing (it isn't here, it has broken, or it is water or sand, not a solid)."""
        h = self.feature_for(surface)
        said = " ".join(str(surface or "").lower().replace("’", "'").split())
        for p in self.scene_cfg.get("props") or []:     # one of the arena's props, named as the arena names it
            if said == str(p).lower():
                return None if self.is_broken(p) else p
        if h and not self._is_solid(h):
            # water, sand, roots: only an edge or rim of it the arena lists as a prop ("the rim of the well")
            last = (re.findall(r"[a-z]{3,}", said) or [""])[-1]
            return next((p for p in self.scene_cfg.get("props") or [] if self.feature_for(p) is h
                         and last in re.findall(r"[a-z]{3,}", str(p).lower()) and last in self._EDGE_WORDS
                         and not self.is_broken(p)), None)
        if h:
            if self.is_broken(h["name"]):
                return None
            for p in self.scene_cfg.get("props") or []:     # the arena's own wording for it
                if self.feature_for(p) is h:
                    return p
            return h["name"]
        s = str(surface or "").lower()
        for p in self.scene_cfg.get("props") or []:
            if self.feature_for(p):
                continue          # a tracked feature: only matched through its own words above
            words = re.findall(r"[a-z]{3,}", str(p).lower())
            if words and re.search(rf"\b{re.escape(words[-1])}s?\b", s) and not self.is_broken(p):
                return p
        # (since build 278) a plain word for a kind of thing ("Tree" in the lakeside clearing): the arena's own one of
        # that kind (an old oak), not a new surface called "Tree"
        last = (re.findall(r"[a-z]{3,}", s) or [""])[-1]
        kinds = {"tree": r"oak|pine|tree|trunk|birch|willow|elm|ash|palm", "rock": r"boulder|rock|stone",
                 "stone": r"boulder|rock|stone|pillar", "boulder": r"boulder|rock", "wall": r"wall|cliff|face",
                 "log": r"log|trunk", "post": r"post|pillar|prop|column", "pillar": r"pillar|column"}
        for kind, rx in kinds.items():
            if last in (kind, kind + "s"):
                for p in self.scene_cfg.get("props") or []:
                    if re.search(rf"\b(?:{rx})s?\b", str(p).lower()) and not self.is_broken(p):
                        return p
        return None

    def hazard_for(self, surface):
        """The tracked feature of this arena that a surface name means ("a steam pipe" -> the steam pipes), or None."""
        s = " ".join(str(surface or "").lower().replace("’", "'").split())
        hz = self.scene_cfg.get("hazards") or []
        if not s or not hz:
            return None
        ends = lambda text: next((h for h in hz if any(text.endswith(str(w).lower()) or text.endswith(str(w).lower() + "s")
                                                       for w in h.get("words") or [])), None)
        # "the rim of the hot spring", "the edge of the pool": the thing she hits is the rim, not the water
        anywhere = next((h for h in hz if any(str(w).lower() in s for w in h.get("words") or [])), None)
        wet = lambda h: bool(h) and (h.get("cushion") or any(e.get("status") == "soaked" for e in h.get("effects") or []))
        m = self._EDGE_OF.match(s)
        if m:
            return ends(m.group(1)) or (None if wet(anywhere) else anywhere)
        # "the deep channel wall", "the channel's edge": the last word is the thing itself
        hit = ends(s)
        if hit or s.split()[-1] in self._EDGE_WORDS:
            return hit or (None if wet(anywhere) else anywhere)
        return anywhere

    _EDGE_WORDS = ("edge", "rim", "lip", "bank", "side", "foot", "base", "mouth", "wall", "floor", "bottom", "shore", "brink")
    _EDGE_OF = re.compile(r"(?:the |a |an )?(?:\w+ )?(edge|rim|lip|bank|side|foot|base|mouth|wall|floor|bottom|shore|brink) of\b")

    def is_upright(self, surface):
        h = self.hazard_for(surface)
        return bool(h.get("upright")) if h else bool(self.UPRIGHT_SURFACE.search(str(surface or "")))

    def break_chance(self, surface, table):
        """How likely something is to break when a fighter is driven or pressed into it: the arena's own number for
        that feature, else the rules' table by keyword."""
        h = self.feature_for(surface)
        if h and h.get("break") is not None:
            return float(h["break"])
        if h and not self._is_solid(h):
            return 0.0            # water, sand, roots: nothing there to break
        s = str(surface or "").lower()
        return next((float(v) for k, v in (table or {}).items() if k != "default" and k in s),
                    float((table or {}).get("default", 0.15)))

    def hazard_effects(self, d, surfaces, rng=None):
        """What the arena does to a fighter who lands on, is thrown, dragged, driven or pressed into these surfaces:
        each tracked hazard among them rolls its effects once (burned, chilled, soaked, poisoned, paralyzed...)."""
        out, seen = [], set()
        if d.eliminated:
            return out
        for s in surfaces:
            h = self.hazard_for(s)
            if not h or h["name"] in seen:
                continue
            seen.add(h["name"])
            for eff in h.get("effects") or []:
                ch = float(eff.get("chance", 1))
                if ch >= 1:
                    ok = True
                elif rng is not None:
                    r = rng.random(); ok = r < ch
                    self.note_roll(f"{d.name} {eff['status']} by {h['name']}", ch, r, eff["status"] if ok else "no")
                else:
                    ok = self._chance(ch, f"{d.name} {eff['status']} by {h['name']}", eff["status"], "no")
                if ok:
                    self.set_status(d, eff["status"], int(eff.get("beats", 2)))
                    out.append({"fighter": d.name, "status": eff["status"], "beats": int(eff.get("beats", 2)),
                                "hazard": h["name"], "about": h.get("about", ""), "knock_on": self._knock_on})
                    self._knock_on = []
        return out

    def scene_brief(self):
        """The arena's tracked features, for the director: what each one is called and what it does."""
        lines = []
        for h in self.scene_cfg.get("hazards") or []:
            does = [f"{round(100 * float(e.get('chance', 1)))}% {e['status']}" for e in h.get("effects") or []]
            if self.is_broken(h["name"]):   # it has given way in this fight: nothing standing to drive her into
                lines.append(f"- {h['name']}: BROKEN in this fight, lying in pieces: it can't be driven, pressed or "
                             f"pinned into any more" + (f" [landing in the wreckage still rolls: {'; '.join(does)}]"
                                                        if does else ""))
                continue
            if h.get("break"):
                does.append(f"breaks {round(100 * float(h['break']))}% of the time when someone is driven or pressed into it")
            if h.get("cushion"):
                does.append("a soft landing (always light)")
            lines.append(f"- {h['name']}: {h.get('about', '')}" + (f" [{'; '.join(does)}]" if does else ""))
        return "\n".join(lines)

    def _scene_event_tick(self, busy=False):
        """Now and then the place itself does something (scenes.json events): a stalactite falls, a wave sweeps the
        deck, a steam joint bursts. Never during a pin or a hold, never in the first beats, never twice close together
        (rules.json scene). It has its own dice. /hazard makes one happen."""
        cfg = self.rules.get("scene", {})
        evs = [e for e in (self.scene_cfg.get("events") or []) if isinstance(e, dict)]
        forced, self._forced_event = getattr(self, "_forced_event", None), None
        live = [f for f in self.active()]
        if len(live) < 2 or (not evs and not forced):
            return []
        rng = self.event_rng
        chance = float(self.scene_cfg.get("event_chance", cfg.get("event_chance", 0.05)))
        if not forced:
            if chance <= 0 or not cfg.get("events", True) or self.turn < int(cfg.get("event_from_beat", 3)):
                return []
            if busy or self.pins or self.holds or self.pressed:
                return []
            if self._last_event is not None and self.turn - self._last_event < int(cfg.get("event_gap", 4)):
                return []
            # only an event that has someone to happen to can come (one for a fighter lying down needs one down):
            # otherwise the roll would say "something happens" and nothing would
            pinned_now = {p["defender"] for p in self.pins.values()}
            down_now = [f for f in live if f.name in self.downed and f.name not in pinned_now]
            up_now = [f for f in live if f.name not in self.downed]
            evs = [e for e in evs if (down_now if e.get("who") == "down" else up_now if e.get("who") == "standing"
                                      else live)]
            if not evs:
                return []
            r = rng.random()
            self.note_roll(f"{self.scene_word('place')} doing something by itself", chance, r,
                           "something happens" if r < chance else "nothing")
            if r >= chance:
                return []
            ev = rng.choices(evs, [float(e.get("weight", 1)) for e in evs])[0]
            want = None
        else:
            ev, want = forced[0], forced[1]
        pinned = {p["defender"] for p in self.pins.values()}
        who = ev.get("who", "anyone")
        pool = ([f for f in live if f.name in self.downed and f.name not in pinned] if who == "down" else
                [f for f in live if f.name not in self.downed] if who == "standing" else live)
        if not pool and forced:
            pool = live      # your /hazard happens whoever it finds: it isn't lost because nobody is down
        if want:
            victims = [self.get_active(want)]
        elif who == "all":
            victims = pool
        else:
            victims = [rng.choice(pool)] if pool else []
        if not victims:
            return []
        self._last_event = self.turn
        table = self.rules["severity"].get("environment") or self.rules["severity"]["instant"]
        v = self.rules["severity"]["variance"]
        hits, status = [], []
        for f in victims:
            sev = ev.get("severity")
            if sev:
                cands = [p for p in f.parts if body_region(p) in (ev.get("regions") or [])] or list(f.parts)
                picked = rng.sample(cands, min(max(1, int(ev.get("parts", 2))), len(cands)))
                self._source = str(ev.get("name", "the arena"))[:60]
                power = max(1, round(float(table.get(sev, table.get("solid", 15))) * rng.uniform(1 - v, 1 + v)))
                hits += [self._apply_damage(f, p, power) for p in picked]
            for eff in ev.get("effects") or []:
                ch = float(eff.get("chance", 1))
                r = rng.random() if ch < 1 else 0.0
                if ch < 1:
                    self.note_roll(f"{f.name} {eff['status']} by {ev.get('name', 'the arena')}", ch, r,
                                   eff["status"] if r < ch else "no")
                if r < ch and eff["status"] not in ("asleep", "frozen"):
                    self.set_status(f, eff["status"], int(eff.get("beats", 2)))
                    self._knock_on = []
                    status.append({"fighter": f.name, "status": eff["status"], "beats": int(eff.get("beats", 2))})
            self.involved.add(f.name)
        if ev.get("severity") in ("solid", "heavy", "brutal") or ev.get("mark"):
            self.mark_arena(str(ev.get("mark") or f"{self.scene_word('place')} still shows where {ev.get('name', 'something happened')}"))
        return [{"type": "scene_event", "name": ev.get("name", "something happens"), "text": ev.get("text", ""),
                 "who": who, "fighters": [f.name for f in victims], "hits": hits, "status_applied": status,
                 "severity": ev.get("severity"), "words": list(ev.get("words") or []), "chance": chance,
                 "forced": bool(forced) and len(forced) < 3,         # your /hazard (not one a charge shook loose)
                 "shaken": bool(forced) and len(forced) >= 3, "place": self.scene_word("place")}]

    def force_event(self, which, fighter=None):
        """Make one of this arena's events happen at the end of the next beat (your /hazard command)."""
        evs = [e for e in (self.scene_cfg.get("events") or []) if isinstance(e, dict)]
        w = norm(which)
        hit = ([evs[int(w) - 1]] if w.isdigit() and 1 <= int(w) <= len(evs) else
               [e for e in evs if w and (w in norm(e.get("name", "")) or any(w == norm(x) for x in e.get("words") or []))])
        if len(hit) != 1:
            raise ValueError("which one? This arena's events: " + ("; ".join(f"{i + 1}. {e['name']}" for i, e in enumerate(evs))
                                                                    or "none"))
        self._forced_event = (hit[0], self.get_active(fighter).name if fighter else None)
        return hit[0]

    def _crumple_tick(self):
        """End of the beat: a fighter left pressed against the scenery by a charge either crumples to the ground or
        staggers off it on her feet. The weaker she is, the likelier she goes down."""
        cfg = self.rules.get("moves", {}).get("charge", {}).get("crumple", {})
        events = []
        for name, info in list(self.pressed.items()):
            self.pressed.pop(name, None)
            f = self.fighters.get(name.lower())
            if f is None or f.eliminated or name in self.downed:
                continue  # already taken down, pinned, or knocked off it by a follow-up
            share = max(0.0, min(1.0, self.strength(f) / 100.0))
            chance = float(cfg.get("base", 0.6)) + float(cfg.get("per_strength_lost", 0.35)) * (1.0 - share)
            if self.has(f, "asleep") or self.has(f, "frozen"):
                chance = 1.0
            chance = max(0.0, min(1.0, chance))
            ev = {"type": "crumple", "fighter": name, "surface": info["surface"], "by": info["by"],
                  "down": self._chance(chance, f"{name} crumpling at {info['surface']}", "she crumples",
                                       "she keeps her feet"),
                  "chance": round(chance, 2), "knock_on": []}
            if ev["down"]:
                # lying at its foot, or slid down it to sitting with her back against it
                lie = self.vary("charge_falls")
                ev["facing"] = self.knock_down(name, facing=lie, why=f"{name} crumpled at the foot of {info['surface']}")
                self.__dict__.setdefault("lying_at", {})[name] = info["surface"]
                ev["knock_on"], self._knock_on = self._knock_on, []
            else:
                ev["manner"] = self.vary("charge_stands")   # how she keeps her feet
            # crushed between a body and the scenery: for the next beat she can hit back, but she can't wrestle
            # anyone down into a pin (moves.charge.reeling_beats; 0 turns it off)
            beats = int(self.rules.get("moves", {}).get("charge", {}).get("reeling_beats", 1) or 0)
            if beats > 0:
                f.status["reeling"] = max(f.status.get("reeling", 0), beats)
                self._fresh_status.add((f.name, "reeling"))
                ev["reeling"] = beats
            events.append(ev)
        return events

    def _collapse_tick(self):
        """Below zero health she fights on, but her body may give out by itself (health.collapse): at the end of a
        beat a fighter on her feet below 0% may simply COLLAPSE, no blow needed. The deeper below zero, the likelier;
        she can get up again as usual, and it can't happen again for `cooldown` beats."""
        cfg = (self.rules.get("health") or {}).get("collapse") or {}
        if not cfg.get("enabled", True):
            return []
        events = []
        for f in self.active():
            pct = self._health_pct(f)
            if pct >= 0 or f.name in self.downed or self.pinned_by(f.name) or self.pinning(f.name) \
                    or self.has(f, "airborne") or any(f.name in (h.attacker, h.defender) for h in self.holds.values()):
                continue
            last = f.learned.get("collapse_turn")
            if last is not None and self.turn - int(last) < int(cfg.get("cooldown", 5)):
                continue
            # stand_grace: once she is back on her feet she gets that many beats before her body can give out on its
            # own again (blows can still put her down at any time)
            rose = f.learned.get("rose_turn")
            if last is not None and rose is not None and int(rose) >= int(last) \
                    and self.turn - int(rose) < int(cfg.get("stand_grace", 5)):
                continue
            chance = min(float(cfg.get("max", 0.4)),
                         float(cfg.get("base", 0.08)) + float(cfg.get("per_10_below", 0.03)) * (-pct) / 10.0)
            # repeat_mult: each earlier collapse this fight makes the next one less likely (she has found her floor)
            chance *= float(cfg.get("repeat_mult", 1.0)) ** int(self.times("collapse", f.name))
            if self.has(f, "adrenaline"):
                chance *= float(cfg.get("adrenaline_mult", 0.3))
            if not self._chance(chance, f"{f.name} collapsing on her own (below zero)", "she COLLAPSES", "she stays up"):
                continue
            f.learned["collapse_turn"] = self.turn
            self._count("collapse", f.name)
            facing = self.knock_down(f.name, why=f"{f.name} collapsed on her own, her body giving out")
            ev = {"type": "collapse", "fighter": f.name, "facing": facing, "chance": round(chance, 2),
                  "health": round(pct, 1), "knock_on": self._knock_on}
            self._knock_on = []
            events.append(ev)
        return events

    # what a blow on each region drives into the surface behind her (standing against it, or lying face-up)
    _BEHIND = {"chest": ("back_up", "back_low"), "belly": ("back_low", "back_up"), "neck": ("neck", "back_up"),
               "shoulder": ("shoulder", "back_up"), "head": ("head",), "back_up": ("back_up",), "back_low": ("back_low",)}
    # lying face-down, a blow from above lands on her back side and drives her front into the ground
    _BEHIND_DOWN = {"back_up": ("chest", "belly"), "back_low": ("belly", "chest"), "neck": ("neck",),
                    "head": ("head",), "shoulder": ("shoulder", "chest")}
    _LIMB_IN = {"fore_low": "fore_up", "fore_up": "shoulder", "hind_low": "hind_up", "hind_up": "hind_up",
                "tail": "back_low"}     # (a thigh hangs from the hip: the other hind_up part on that side)

    def _backing_mult(self, part, struck):
        """A part driven into the surface that is the struck part itself (her arm ground into the bark, the back of her
        neck into the tree): only the side of it we don't track takes this, so it takes a lighter share
        (moves.grind.self_mult)."""
        return float(((self.rules.get("moves") or {}).get("grind") or {}).get("self_mult", 0.5)) if part == struck else 1.0

    def _backing(self, d, struck, facing=None):
        """The parts a blow on `struck` drives into what is behind her (a tree, a wall, the ground she lies on): a
        blow on her chest drives her upper back into it, her belly her lower back, her face the back of her head; a
        blow on a limb MIGHT grind that limb into it, and might take the shoulder or hip it hangs from as well (dice:
        moves.grind.limb_chance, limb_root_chance). On her side, the matching part on her other side."""
        cfg = (self.rules.get("moves") or {}).get("grind") or {}
        names = list(d.parts)
        reg, side = body_region(struck), _side(struck)

        def find(regions, same_side=True, not_self=False):
            for r in regions:
                c = [n for n in names if body_region(n) == r and not (not_self and n == struck)
                     and (not same_side or not side or _side(n) in (None, side))]
                if r == "head":
                    c = [n for n in c if n.lower() == "head"] or c
                if r == "neck":
                    # the back of the neck goes into a tree or the ground behind her; her throat only face-down
                    want = "throat" if facing == "face-down" else "neck"
                    c = [n for n in c if want in n.lower()] or [n for n in c if "throat" not in n.lower()] or c
                if c:
                    return self.rng.choice(c)
            return None
        if facing == "on her side":
            if side:
                twin = re.sub(r"\b(Left|Right)\b", lambda m: "Right" if m.group(1) == "Left" else "Left", struck)
                return [twin] if twin in d.parts else [struck]
            if reg not in self._LIMB_IN:
                return [struck]      # a blow down on her uppermost flank presses that same stretch of her into it
        if (facing == "face-up" and reg in ("back_up", "back_low")) or (facing == "face-down" and (
                reg in ("chest", "belly") or "throat" in struck.lower())):
            return []                # that part is against the ground already: no blow comes down on it from above
        table = self._BEHIND_DOWN if facing == "face-down" else self._BEHIND
        if reg in table:
            got = find(table[reg])
            return [got] if got else []
        out = []
        # lying on the ground a limb is almost always against it; held against a tree or a wall, only maybe
        if self.rng.random() < float(cfg.get("limb_chance_down" if facing else "limb_chance", 0.85 if facing else 0.6)):
            out.append(struck)            # the limb itself ground into it
        root = self._LIMB_IN.get(reg)
        if root and self.rng.random() < float(cfg.get("limb_root_chance", 0.4)):
            got = find((root,), not_self=True)
            if got and got not in out:
                out.append(got)
        return out

    # how easy each part of a body is to land a blow on where it was aimed (moves.aim): the torso is the big, near
    # target; limbs move; the neck hides under the jaw and between the shoulders; small things (ears, nose, eyes,
    # paws, fins) are small
    AIM_EASE = {"chest": 0.95, "belly": 0.95, "back_up": 0.9, "back_low": 0.9, "shoulder": 0.85, "hind_up": 0.85,
                "fore_up": 0.8, "head": 0.75, "tail": 0.7, "hind_low": 0.7, "fore_low": 0.65, "neck": 0.55,
                "other": 0.8}
    AIM_SMALL = (("throat", 0.8), ("ear", 0.7), ("eye", 0.6), ("nose", 0.75), ("muzzle", 0.9), ("jaw", 0.9),
                 ("cheek", 0.9), ("paw", 0.85), ("hand", 0.85), ("foot", 0.85), ("fin", 0.8), ("horn", 0.85),
                 ("knee", 0.9), ("hock", 0.85))

    def aim_ease(self, part, cfg=None):
        """0-1: how likely a blow aimed at this part lands on it (before who is moving and who is held)."""
        cfg = cfg if cfg is not None else ((self.rules.get("moves") or {}).get("aim") or {})
        reg = body_region(part)
        ease = float((cfg.get("regions") or {}).get(reg, self.AIM_EASE.get(reg, 0.8)))
        low = part.lower()
        for w, m in (cfg.get("small") or self.AIM_SMALL):
            if re.search(r"(?:\b|(?<=fore)|(?<=hind))" + re.escape(w), low):   # a forepaw is a paw
                ease *= float(m)
                break
        return max(0.05, min(1.0, ease))

    def _aim(self, a, d, part):
        """Where a blow aimed at `part` really lands: the part itself, or (missing the small or hard to reach thing it
        was aimed at) one beside it, the bigger and easier the likelier. Easier on a fighter who is down, held,
        pinned or reeling; harder for an attacker who is dazed or off balance. moves.aim"""
        cfg = (self.rules.get("moves") or {}).get("aim") or {}
        if not cfg.get("enabled", True) or self.has(d, "airborne") and not self.has(a, "airborne"):
            return part
        miss = 1.0 - self.aim_ease(part, cfg)
        if d.name in self.downed or self.pinned_by(d.name):
            miss *= float(cfg.get("down_mult", 0.5))
        if any(h.defender == d.name for h in self.holds.values()):
            miss *= float(cfg.get("held_mult", 0.5))
        if any(self.has(d, st) for st in ("staggered", "dazed", "doubled_over", "off_balance", "flinched", "frozen",
                                           "asleep", "paralyzed")):
            miss *= float(cfg.get("open_mult", 0.6))
        if any(self.has(a, st) for st in ("dazed", "off_balance", "confused")):
            miss *= float(cfg.get("shaky_mult", 1.3))
        sc_ = self._cfg("status_effects")
        if self.has(a, "seeing_double"):
            miss *= float(sc_.get("seeing_double_aim_mult", 1.6))     # (since build 293) which of the two is her?
        if self.has(a, "eyes_watering"):
            miss *= float(sc_.get("eyes_watering_aim_mult", 1.3))
        if self.has(a, "swollen_eye"):
            miss *= float(sc_.get("swollen_eye_aim_mult", 1.2))
        if any(self.has(d, st) for st in ("stunned", "wobbly")):
            miss *= float(cfg.get("open_mult", 0.6))
        miss *= float(cfg.get("scale", 1.0)) / self.trait(a, "striking")
        if miss <= 0 or not self._chance(min(0.9, miss), f"{poss_word(a.name)} blow sliding off the {part} it was aimed at",
                                         "it lands beside it", "on target"):
            return part
        same, near = neighbor_parts(list(d.parts), part)
        facing = self.facing_of(d.name)
        hidden = {"face-up": ("back_up", "back_low"), "face-down": ("chest", "belly")}.get(facing, ())
        cands = [p for p in dict.fromkeys(near + same) if body_region(p) not in hidden] or [part]
        # the bigger and easier the likelier; a part harder to reach than the one she missed seldom takes it instead
        mine = self.aim_ease(part, cfg)
        weights = [e * e * (1.0 if e >= mine else float(cfg.get("harder_mult", 0.3)))
                   for e in (self.aim_ease(p, cfg) for p in cands)]
        return self.rng.choices(cands, weights)[0]

    def _ground_back(self, a, d, move, hits, blows, struck=None):
        """A blow driven down into a fighter who is lying on the ground drives her into the ground as well: what lies
        under the part it hit takes a light hit (her back under her chest when she is face-up, her chest under her
        back face-down, the arm itself under an arm: _backing), like a fighter held against a tree (_grind). Only blows that push down into her: a punch, a
        kick, a tail, a slam of a paw, a blast; not a rake across her or a bite that pulls her up. Not while she is
        sitting up, or lying in deep water (it gives under her); shallow water softens it. moves.ground_back."""
        cfg = (self.rules.get("moves") or {}).get("ground_back") or {}
        if not cfg.get("enabled", True):
            return None
        facing = self.facing_of(d.name)
        if facing not in ("face-up", "face-down", "on her side"):
            return None
        if self._blow_kind(move) not in ("blunt", "blast"):
            return None
        water = self.in_water(d.name)
        if water == "deep":
            return None
        lying_on = {"face-up": ("back_up", "back_low"), "face-down": ("chest", "belly")}.get(facing, ())
        struck = [s_ for s_ in (struck or [h["part"] for h in hits[:1]]) if body_region(s_) not in lying_on]
        if not struck:
            return None          # every blow fell on what's against the ground already: nothing to drive down
        table = self.rules["severity"].get("environment") or self.rules["severity"]["instant"]
        power = float(table.get(cfg.get("power", "light"), 10)) * float(cfg.get("mult", 1.0)) \
            * (float(cfg.get("shallow_mult", 0.5)) if water == "shallow" else 1.0)
        ground = self.ground_under(d.name)
        out = {"against": ground, "facing": facing, "blows": blows, "hits": [], "in_water": water}
        for s_ in struck[:blows]:
            self._source = f"being driven down into {ground}"
            # what is under the part this blow hit (her back under her chest, the arm itself under an arm)
            out["hits"] += [self._apply_damage(d, p_, power * self._backing_mult(p_, s_))
                            for p_ in self._backing(d, s_, facing)]
        return out if out["hits"] else None

    def _grind(self, a, d, against, blows, struck=None):
        """Blows landed while she is held or pressed against the scenery (a pummel against a tree, a strike that pins
        her to the wall): each one also drives her back into it (moves.grind: power, break_mult). If it breaks, a heavy
        extra hit and she goes down with it."""
        cfg = (self.rules.get("moves") or {}).get("grind") or {}
        against = short_phrase(self.scene_prop_for(against) or against)
        table = self.rules["severity"].get("environment") or self.rules["severity"]["instant"]
        back = self.landing_parts(d.name, 2)       # what goes through it if it breaks: her back, whatever was hit
        struck = list(struck or [])
        brk = self.break_chance(against, ((self.rules.get("moves") or {}).get("sustain") or {}).get("break_chance", {})) \
            * float(cfg.get("break_mult", 0.5))
        out = {"against": against, "blows": blows, "hits": [], "surface_hits": [], "break_hits": [], "broke": False,
               "hazard_status": self.hazard_effects(d, [against])}
        for i in range(1, blows + 1):
            self._source = f"being driven into {against}"
            # what THIS blow drives into it: what is behind the part it hit (her back behind her chest, an arm hit
            # may grind the arm itself and its shoulder); with nothing known, her back as before
            hit_ = struck[i - 1] if i - 1 < len(struck) else None
            into = self._backing(d, hit_) if hit_ else back[:1 + (i == 1)]
            sh = [self._apply_damage(d, p, float(table.get(cfg.get("power", "light"), 10)) * self._backing_mult(p, hit_))
                  for p in into]
            out["surface_hits"] += sh
            out["hits"] += sh
            if self._chance(brk, f"{against} breaking behind {d.name} (blow {i})", "it BREAKS", "it holds"):
                self.mark_arena(f"{against} lies broken where {d.name} was driven through it")
                self._source = f"{against} breaking"
                bh = [self._apply_damage(d, p, float(table.get("heavy", 25))) for p in back]
                out["break_hits"], out["broke"] = bh, True
                out["hits"] += bh
                self.knock_down(d.name, parts=back, why=f"{d.name} went down with {against}")
                out["knock_on"], self._knock_on = self._knock_on, []
                break
        out["facing"] = self.facing_of(d.name)
        return out

    def _sustain(self, a, d, move, plan, powers, pulses, against, enforce):
        """Hold a stream or beam on the target for more pulses: each one hits the same parts again (weaker), and if
        she's pressed against something (a boulder, a stalagmite, the wall) each pulse also grinds her into it.
        The thing behind her may break: a heavy extra hit, the move ends early, and she goes down."""
        cfg = self.rules.get("moves", {}).get("sustain", {})
        if against and self.scene_prop_for(against) is not None:
            against = self.scene_prop_for(against)     # (since build 278) "Tree" -> the arena's own "an old oak"
        pulses = max(1, min(int(cfg.get("max_pulses", 4)), pulses))
        mult = float(cfg.get("pulse_mult", 0.6))
        against = short_phrase(against)
        if against and self.is_broken(against):
            against = ""          # it already lies broken: nothing behind her to grind her into
        table = self.rules["severity"].get("environment") or self.rules["severity"]["instant"]
        back = self.landing_parts(d.name, 3) if against else []     # what goes through it or slides down it
        # what each pulse presses into it: what is behind the parts the stream hits (_backing), else her back
        press = []
        if against:
            facing_ = self.facing_of(d.name) if d.name in self.downed else None
            for s_ in dict.fromkeys(plan):
                press += [(x, self._backing_mult(x, s_)) for x in self._backing(d, s_, facing_)
                          if x not in [q[0] for q in press]]
            press = press[:3] or [(x, 1.0) for x in back[:1]]
        brk = self.break_chance(against, cfg.get("break_chance", {}))
        out = {"against": against, "pulses": [], "broke": False, "planned": pulses, "knock_on": [],
               "was_down": d.name in self.downed,
               "hazard_status": self.hazard_effects(d, [against]) if against else []}
        for i in range(2, pulses + 1):
            cost = float(cfg.get("energy_per_pulse", 6))
            if enforce and a.energy < cost:
                break  # out of breath: the stream sputters out
            a.energy = max(0.0, a.energy - cost)
            self._source = f"{poss_word(a.name)} {move['name']} (held)"
            hits = [self._apply_damage(d, p, round(pw * mult, 2)) for p, pw in zip(plan, powers)]
            pulse = {"n": i, "hits": hits, "move_hits": list(hits), "surface_hits": [], "break_hits": []}
            if back:
                self._source = f"being pressed into {against}"
                sh = [self._apply_damage(d, p, float(table.get("solid", 15)) * m) for p, m in press]
                pulse["surface_hits"] = sh
                pulse["hits"] = hits + sh
                if self._chance(brk, f"{against} breaking under {d.name} (pulse {i})", "it BREAKS", "it holds"):
                    self.mark_arena(f"{against} lies broken where {d.name} was pressed through it")
                    self._source = f"{against} breaking"
                    bh = [self._apply_damage(d, p, float(table.get("heavy", 25))) for p in back]
                    pulse["hits"] += bh
                    pulse["break_hits"] = bh
                    pulse["broke"] = True
                    out["broke"] = True
                    out["pulses"].append(pulse)
                    self.knock_down(d.name, parts=back, why=f"{d.name} went down with {against}")
                    out["knock_on"], self._knock_on = self._knock_on, []
                    break
            out["pulses"].append(pulse)
        out["held"] = 1 + len(out["pulses"])
        if back and not out["broke"] and out["pulses"]:
            if cfg.get("crumple", True) and not out["was_down"]:
                # moves.sustain.crumple: held there on her feet, she is left pressed against it, and at the end of the
                # beat she crumples or keeps her feet like anyone a charge has crushed against the scenery (the
                # stronger she is, the likelier she stays up)
                self.pressed[d.name] = {"surface": against, "by": f"{poss_word(a.name)} {move['name']}"}
                out["pressed"] = True
            else:
                # she slides down whatever she was pressed against (only if the stream really held her there)
                self.knock_down(d.name, parts=back, why=f"{d.name} was driven down against {against}")
                out["knock_on"], self._knock_on = self._knock_on, []
        out["facing"] = self.facing_of(d.name)
        return out

    def _confusion(self, a, move, enforce, energy_before):
        """A confused fighter sometimes hurts herself instead of attacking."""
        if not (enforce and self.has(a, "confused")):
            return None
        if not self._chance(float(self._cfg("status_effects").get("confused_self_hit_chance", 0.33)),
                            f"{a.name} hurting herself in her confusion", "she does", "she attacks normally"):
            self._confusion_passed = a.name     # (dizzy still, and attacking anyway: move_attack marks it)
            return None
        part = self.rng.choice([p for p in a.parts if body_region(p) in ("head", "fore_low", "fore_up", "shoulder",
                                                                         "chest", "tail")] or list(a.parts))
        self._source = f"{poss_word(a.name)} own confusion"
        hit = self._apply_damage(a, part, self.power_for("instant", "light"))
        self.involved.add(a.name)
        return {"type": "instant", "attacker": a.name, "defender": a.name, "defenders": [a.name],
                "confused_self_hit": True, "flavor": f"tries {move['name']} but hurts herself in her confusion",
                "energy": [round(energy_before), round(a.energy)], "hit_count": 1, "hits": [hit], "tags": []}

    def _launch_from_move(self, move):
        for eff in move.get("effects", []):
            if eff.get("launch") and self._chance(float(eff.get("chance", 1)), f"{move['name']}: {eff['launch']}",
                                                  "yes", "no"):
                return eff["launch"]
        return None

    # ---------- dodges, status effects, stamina ----------
    def _cfg(self, key):
        return self.rules.get(key, {})

    def has(self, f, status):
        return f.status.get(status, 0) > 0

    def set_status(self, f, status, beats):
        """Apply a status. Falling ASLEEP or being FROZEN also ends everything she was holding or pinning, and a
        fighter who falls asleep on her feet slumps to the ground. What that knocked loose is left in _knock_on.
        A fighter already out takes no new status (it would never tick off: she is out of the beats)."""
        if f.eliminated:
            self._knock_on = []
            return
        f.status[status] = max(f.status.get(status, 0), int(beats))
        self._fresh_status.add((f.name, status))
        if status == "chilled":
            (getattr(self, "_slow_not_cold", None) or set()).discard(f.name)   # (cold, unless the move says otherwise)
        self._knock_on = []
        if status in ("asleep", "frozen") and not f.eliminated:
            word = "fell asleep" if status == "asleep" else "froze solid"
            loose = self._lose_grip(f.name, f"{f.name} {word}")
            # asleep, she slumps wherever she is; frozen, she stands rigid on the ground, but in the air her wings
            # lock and she drops out of it
            from_air = self.has(f, "airborne")
            if (status == "asleep" or from_air) and f.name not in self.downed:
                self.knock_down(f.name, why=f"{f.name} {word}")
                f.status.pop("airborne", None)
                loose += self._knock_on + [{"type": "slumps", "fighter": f.name, "facing": self.facing.get(f.name),
                                            "from_air": from_air, "how": status}]
            self._knock_on = loose

    def _pin_mult(self, a, d):
        """pin.damage_mult for a strike the pinner lands on the fighter she is pinning (1.0 for anything else)."""
        if a is d or d.name not in self.pinning(a.name):
            return 1.0
        return float(self.rules.get("pin", {}).get("damage_mult", 1.0))

    LIMB_KINDS = (("charge", None), ("wing", r"\bwings?\b|aerial ace|air slash|brave bird|\bfly\b|sky attack|gust"),
                  ("talon", r"talons?|sky drop"), ("beak", r"beak|peck|drill"), ("bite", r"bite|fang|crunch|jaw"), ("horn", r"horn|scythe|night slash|psycho cut"),
                  ("tail", r"\btails?\b|iron tail|aqua tail|tail slap|dragon tail"),
                  ("arm", r"punch|chop|break|slash|claw|scratch|swipe|cut|paw|jab|fist|thrust|fury"),
                  ("leg", r"kick|stomp|stamp|\bknee"))

    def busy_with(self, a, move):
        """Is the one mouth she'd attack with already locked in one of her own grips (a hold, a pin's press, a
        submission)? Then that move can't be thrown. Returns (her jaws, the held fighter, the part) or None."""
        if not move or move.get("target") in ("whole_body", "status", "hold", "self"):
            return None
        text = f"{move.get('name', '')} {move.get('about', '')}".lower()
        kind = next((k for k, rx in self.LIMB_KINDS if rx and re.search(rx, text)), None)
        if kind == "bite":
            for h in self.holds.values():
                if h.attacker == a.name and re.search(r"\b(jaws?|teeth|fangs?|mouth|bite)\b", str(h.with_part or "").lower()):
                    return ("jaws", h.defender, h.part)
            return None
        keys = {"leg": ("legs", "feet"), "arm": ("paws", "arms"), "tail": ("tails", "coils"), "wing": ("wings",),
                "talon": ("talons",)}.get(kind)
        if not keys or not ((self.rules.get("holds") or {}).get("busy_limbs") or {}).get("enabled", True):
            return None
        # (holds.busy_limbs, since build 266) a pair of limbs she has locked in her own hold can't throw a blow too:
        # both legs in a triangle choke have no knee to strike with, both paws in a chicken wing no punch. One of the
        # pair still free (a grip with "her right paw") leaves the other for it.
        for key in keys:
            used, first = 0, None
            for h in self.holds.values():
                lb = self.grip_limb(a, h.with_part) if h.attacker == a.name else None
                if not lb or lb[0] != key or re.match(r"(?i)the same\b", str(h.with_part or "")):
                    continue
                w = str(h.with_part or "").lower().split(",")[0]
                pair = re.search(r"\b(?:both|twin|two)\b|\b(?:legs|paws|arms|forearms|feet|tails|wings|talons|hands)\b", w)
                used += lb[1] if pair else 1
                first = first or h
                if used >= lb[1]:
                    return (f"{key}", first.defender, first.part)
        return None

    _REACH_KIND = {"bite": "bite", "horn": "bite", "beak": "bite", "arm": "arm", "wing": "arm", "leg": "leg",
                   "talon": "leg", "tail": "tail"}

    def _held_reach_cfg(self):
        cfg = (self.rules.get("holds") or {}).get("held_reach") or {}
        return cfg if cfg.get("enabled", True) else None

    def _held_on_ground(self, a, d):
        """The grips `d` has on `a` while `a` lies or sits on the ground (an upright hold or a grab on her feet
        doesn't count: the holder is right against her there)."""
        if a.name not in self.downed or self.pinned_by(a.name):
            return []
        return [h for h in self.holds.values() if h.attacker == d.name and h.defender == a.name and not h.grab]

    def reach_kind(self, move):
        """bite / arm / leg / tail: what a move is thrown with, for held_reach; None for one fired across the gap."""
        if not move or self.is_ranged(move) or move.get("target") in ("whole_body", "status", "hold", "self"):
            return None
        text = f"{move.get('name', '')} {move.get('about', '')}".lower()
        kind = next((k for k, rx in self.LIMB_KINDS if rx and re.search(rx, text)), None)
        return self._REACH_KIND.get(kind)

    def held_reach_kinds(self, a, d):
        """What a fighter held on the ground can still hurt her holder with (holds.held_reach): a list of bite / arm
        / leg / tail, or None when nothing limits her."""
        cfg = self._held_reach_cfg()
        hs = self._held_on_ground(a, d) if cfg else []
        if not hs:
            return None
        sit = self.facing.get(a.name) == "sitting up"
        at = {body_region(h.part) for h in hs}
        out = []
        for kind in ("bite", "arm", "leg", "tail"):
            reach = set(cfg.get(kind) or []) | (set((cfg.get("sitting_adds") or {}).get(kind) or []) if sit else set())
            if at & reach:
                out.append(kind)
        return out

    def holder_reach_block(self, a, d, move, names=()):
        """holds.holder_reach (since build 266): from where she holds her in a submission, the holder's blows land
        near the hold: a bite within bite_near steps of the parts she grips, a paw, a knee or a tail within
        strike_near (on her upper back in a chicken wing, Nerine's jaws can't reach Ripples' foot). None when it
        fits, or why it doesn't."""
        cfg = (self.rules.get("holds") or {}).get("holder_reach") or {}
        kind = self.reach_kind(move)
        if not cfg.get("enabled", True) or not kind or not names:
            return None
        hs = [h for h in self.holds.values() if h.attacker == a.name and h.defender == d.name and h.sub]
        if not hs:
            return None
        near = int(cfg.get("bite_near" if kind == "bite" else "strike_near", 1 if kind == "bite" else 2))
        ok = {body_region(h.part) for h in hs}
        held = sorted({h.part.lower() for h in hs})
        for _ in range(max(0, near)):
            ok |= {r for g in list(ok) for r in _BODY_REGION_NEAR.get(g, [])}
        far = [n for n in names if body_region(n) not in ok]
        if not far:
            return None
        close = [p for p in d.parts if body_region(p) in ok and p.lower() not in held] or list(d.parts)
        return (f"{a.name} is working her {hs[0].sub} on {poss_word(d.name)} {', '.join(held[:2])}: from there her "
                f"{ {'bite': 'jaws', 'arm': 'paws', 'leg': 'legs', 'tail': 'tail'}.get(kind, 'blows') } can't reach "
                f"{poss_word(d.name)} {far[0].lower()}. Strike what is near the hold ({', '.join(close[:4]).lower()}), "
                f"or let go first")

    def held_reach_block(self, a, d, move, names=()):
        """Why a fighter held on the ground can't throw `move` at her holder, or None (holds.held_reach)."""
        kinds = self.held_reach_kinds(a, d)
        kind = self.reach_kind(move) if kinds is not None else None
        if not kind:
            return None
        hs = self._held_on_ground(a, d)
        h0 = hs[0]
        what = f"{poss_word(d.name)} {h0.sub}" if h0.sub else f"{poss_word(d.name)} grip"
        spots = list(dict.fromkeys(h.part.lower() for h in hs))
        where = ", ".join(spots[:-1]) + " and " + spots[-1] if len(spots) > 1 else spots[0]
        area = {"hind_low": "legs", "hind_up": "legs", "tail": "tail", "head": "head", "neck": "head",
                "shoulder": "shoulders", "fore_up": "arms", "fore_low": "arms", "chest": "middle", "belly": "middle",
                "back_up": "back", "back_low": "back"}.get(body_region(hs[0].part), "side")
        lie = "sitting" if self.facing.get(a.name) == "sitting up" else "lying"
        words = {"bite": "jaws", "arm": "paws", "leg": "legs", "tail": "tail"}
        other = [words[k] for k in kinds if k != kind]
        tail_ = (f"She can reach her with her {' or '.join(other)}, or 'struggle'" if other
                 else "Nothing of hers reaches her from there: 'struggle', or sit up first")
        if kind not in kinds:
            return (f"{a.name} is {lie} on the ground in {what} (on her {where}): {d.name} is at her {area}, out "
                    f"of reach of her {words[kind]}, so she can't {move['name']} her. {tail_}")
        near = int((self._held_reach_cfg() or {}).get("bite_near", 1))
        if kind != "bite" or near < 0 or not names:
            return None
        # a bite lands on the holder near the limbs she grips with: not on her throat while her paws turn a foot
        grip = {("hind_up" if re.search(r"\blegs?\b", h.with_part.lower()) and body_region(h.with_part) == "other"
                 else body_region(h.with_part)) for h in hs if h.with_part} - {"other"}
        if not grip:
            return None
        ok = set(grip)
        for _ in range(near):
            ok |= {r for g in list(ok) for r in _BODY_REGION_NEAR.get(g, [])}
        far = [n for n in names if body_region(n) not in ok]
        if not far:
            return None
        close = [p for p in d.parts if body_region(p) in grip]
        return (f"{a.name} is {lie} on the ground in {what}: her jaws reach only what {d.name} holds her with "
                f"({', '.join(close[:3]).lower() or h0.with_part}), not {poss_word(d.name)} {far[0].lower()}. Bite "
                f"that, or use something else")

    def limb_mult(self, a, move):
        """A move thrown with a badly hurt limb lands weaker (moves.limb_limits): a chop with a ruined paw, a charge
        on a ruined leg, a bite with a ruined jaw. Streams, beams and whole-body moves aren't thrown with a limb.
        Returns (label, multiplier) or None."""
        cfg = self.rules.get("moves", {}).get("limb_limits") or {}
        if not cfg.get("enabled", True) or not move or move.get("target") in ("whole_body", "status", "hold"):
            return None
        text = f"{move.get('name', '')} {move.get('about', '')}".lower()
        if move.get("target") == "spread" and not move.get("charge"):
            return None
        kind = "charge" if move.get("charge") else next((k for k, rx in self.LIMB_KINDS if rx and re.search(rx, text)), None)
        if kind == "charge" and self.body_plan(a) == "avian":
            kind = "wing"          # a bird's charge is flown, not run
        if not kind:
            return None
        regions = {"charge": ("hind_up", "hind_low"), "leg": ("hind_up", "hind_low"), "arm": ("fore_up", "fore_low"),
                   "tail": ("tail",)}.get(kind)
        words = {"bite": r"jaw|muzzle", "horn": r"\bhorn", "wing": r"\bwing", "talon": r"talon",
                 "beak": r"\bbeak"}.get(kind)
        parts = [p for p in a.parts.values()
                 if (regions and body_region(p.name) in regions) or (words and re.search(words, p.name.lower()))]
        if kind == "charge" and not parts:      # a serpent charges with her body
            parts = [p for p in a.parts.values() if body_region(p.name) in ("tail", "belly")]
        if not parts:
            return None
        if kind != "charge" and (cfg.get("struck_limb", True)):
            # one limb throws it (a wing, an arm, a talon, a horn): the one the order names ("her left wing"), or else
            # her sounder one, since a fighter favours a hurt limb; a charge is carried by all of them (the worst)
            said = str(getattr(self, "_strike_flavor", "") or "").lower()
            named = [p for p in parts if re.search(r"\b%s\b" % re.escape(p.name.lower()), said)]
            side = re.search(r"\b(left|right)\b", said)
            if not named and side:
                named = [p for p in parts if p.name.lower().startswith(side.group(1))
                         and re.search(r"\b(?:wing|arm|paw|hand|fist|claw|talon|horn|leg|foot|forearm|tail)\b", said)]
            # (since build 266) not the side caught in someone's grip: a paw folded back in a wrist lock throws
            # nothing; she strikes with the other one (the build-264 log's Brick Break came from the locked arm)
            held_sides = {h.part.split()[0].lower() for h in self.holds.values() if h.defender == a.name
                          and h.part in a.parts and h.part.split()[0].lower() in ("left", "right")
                          and any(h.part == p.name for p in parts)}
            free_ = [p for p in parts if p.name.split()[0].lower() not in held_sides]
            if free_ and held_sides:
                named = [p for p in named if p in free_]
                parts = free_
            parts = named or [min(parts, key=lambda p: p.damage)]
        worst = max(parts, key=lambda p: p.damage)
        steps = sorted(((float(k), float(v)) for k, v in (cfg.get("at") or {"150": 0.8, "300": 0.6}).items()),
                       reverse=True)
        mult = next((m for at, m in steps if worst.damage >= at), None)
        if mult is None or mult >= 1:
            return None
        return (f"{poss_word(a.name)} hurt {worst.name.lower()}", mult)   # (named: "her" reads as the defender's)

    def power_extras(self, a, d, move_type, move=None):
        """Status multipliers on a move's power: (label, multiplier) pairs."""
        cfg = self._cfg("status_effects")
        out = []
        # (since build 293) what the head and body effects (moves.head, moves.body_jolts) do to her blows
        import blocks as _bl
        kinds = _bl.kind_of(str((move or {}).get("name", "")), str((move or {}).get("about", ""))) if move else set()
        if self.has(a, "jaw_rattled") and "bite" in kinds:
            out.append(("her jaw rattled", float(cfg.get("jaw_rattled_bite_mult", 0.75))))
        if self.has(a, "dead_arm") and kinds & {"punch", "claw"}:
            out.append(("her arm gone numb", float(cfg.get("dead_arm_power_mult", 0.8))))
        if self.has(a, "limping") and kinds & {"charge"}:
            out.append(("limping", float(cfg.get("limping_charge_mult", 0.8))))
        if self.has(a, "back_spasm"):
            out.append(("her back in spasm", float(cfg.get("back_spasm_power_mult", 0.85))))
        if self.has(a, "ribs_aching"):
            out.append(("her ribs aching", float(cfg.get("ribs_aching_power_mult", 0.92))))
        if self.has(a, "stiff"):
            out.append(("stiff from the pin", float(cfg.get("stiff_power_mult", 0.85))))
        if self.has(a, "constricted") and any(h.coil and h.defender == a.name and self.coil_scope(h.part) == "body"
                                              for h in self.holds.values()):
            out.append(("arms trapped in the coils", float(cfg.get("constricted_power_mult", 0.75))))
        if self.has(a, "bound"):
            out.append((f"her {str(a.learned.get('bound_part') or 'limb').lower()} bound",
                        float(cfg.get("bound_power_mult", 0.9))))
        if self.has(a, "sputtering"):
            out.append(("choking on water", float(cfg.get("sputtering_power_mult", 0.9))))
        if self.has(a, "off_balance"):
            out.append(("off balance", float(cfg.get("off_balance_power_mult", 0.85))))
        if self.has(a, "staggered"):
            out.append(("still staggering", float(cfg.get("staggered_power_mult", 0.85))))
        if self.has(a, "fury"):
            out.append(("fury after the pin", float(cfg.get("fury_power_mult", 1.15))))
        if self.has(a, "breathless"):
            out.append(("the wind knocked out of her", float(cfg.get("breathless_power_mult", 0.85))))
        st0 = self.zero_stage(a)
        if st0 and float(st0.get("power", 1.0)) != 1.0:
            out.append((st0.get("label", "running on nothing"), float(st0.get("power", 1.0))))
        if self.has(a, "greyed"):
            out.append(("her sight greying out", float(cfg.get("greyed_power_mult", 0.85))))
        if self.has(a, "dazed"):
            out.append(("dazed", float(cfg.get("dazed_power_mult", 0.9))))
        if self.has(a, "wobbly"):
            out.append(("legs gone under her", float(cfg.get("wobbly_power_mult", 0.85))))
        if self._pin_mult(a, d) != 1.0:
            out.append(("pin damage", self._pin_mult(a, d)))
        if self.has(a, "paralyzed"):
            out.append(("paralyzed", float(cfg.get("paralyzed_power_mult", 0.75))))
        if self.has(a, "adrenaline"):
            out.append(("adrenaline", float(self._cfg("adrenaline").get("power_mult", 1.25))))
        if self.has(a, "burned"):
            out.append(("burned", float(cfg.get("burned_power_mult", 0.85))))
        if move_type == "Electric" and self.has(d, "soaked"):
            out.append(("soaked", float(cfg.get("soaked_electric_mult", 1.5))))
        return out

    def _status_from_move(self, d, move, force_roll=False, at=None):
        """The move's own effects (moves.json), or else the default for its type (rules.json). at: the part it
        touched (a burn stays on that spot)."""
        if d.eliminated:
            return []
        if isinstance(move, str):
            move = {"type": move}
        effs = [x for x in move.get("effects", []) if x.get("status")]
        default = self._cfg("status_effects").get("from_move_type", {}).get(move.get("type"))
        if not effs and not move.get("effects"):
            effs = [default] if default else []
        elif default and default.get("status") in self._cfg("status_effects").get("from_move_type_always", []) \
                and not any(x.get("status") == default["status"] for x in effs):
            effs = effs + [default]     # (water wets her, whatever else the move does: Water Pulse soaks as well)
        out = []
        for eff in effs:
            if self._chance(float(eff.get("chance", 0)), f"{d.name} {eff['status']} by {move.get('name', 'the move')}",
                            eff["status"], "no"):
                if eff["status"] == "burned" and not self.has(d, "burned"):
                    # the burn stays where the fire touched her: every later flare is on that spot
                    self.__dict__.setdefault("burn_spot", {})[d.name] = at
                self.set_status(d, eff["status"], eff.get("beats", 2))
                rec = {"fighter": d.name, "status": eff["status"], "beats": int(eff.get("beats", 2)),
                       "knock_on": self._knock_on}
                if eff["status"] == "chilled" and move.get("type") != "Ice":
                    # (the slow of a move that isn't cold, Rock Tomb's boulders or String Shot's silk, isn't frost)
                    if not hasattr(self, "_slow_not_cold"):
                        self._slow_not_cold = set()
                    self._slow_not_cold.add(d.name)
                    rec["look"] = self.status_look(d.name, "chilled")
                out.append(rec)
                self._knock_on = []
        return out

    @staticmethod
    def pin_members(p):
        """Everyone pressing in a pin: the one who started it, then anyone who joined."""
        return [p["attacker"]] + list(p.get("helpers") or [])

    def pin_on(self, name):
        """The pin this fighter is under, or None. There is at most one: a second pinner joins it."""
        return next((p for p in self.pins.values() if p["defender"] == name), None)

    def pinned_by(self, name):
        """Who is pinning this fighter right now (usually nobody, one, or two in a double pin)."""
        return [m for p in self.pins.values() if p["defender"] == name for m in self.pin_members(p)]

    def pinning(self, name):
        """Who this fighter is pinning right now (as the one who started the pin, or as a helper)."""
        return [p["defender"] for p in self.pins.values() if name in self.pin_members(p)]

    def _leave_pin(self, key, name, why, how="got free"):
        """One pinner comes off a pin (knocked away, put out, let go). Her presses end. If she was the only one the
        pin is over; if another fighter is still pressing, the pin goes on with her (same clock). Returns events."""
        p = self.pins.get(key)
        if p is None or name not in self.pin_members(p):
            return []
        for h in [h for h in self.holds.values() if h.attacker == name and h.defender == p["defender"]]:
            self.holds.pop(h.id, None)
        rest = [m for m in self.pin_members(p) if m != name]
        if not rest:
            del self.pins[key]
            note = f"{why}, so her pin on {p['defender']} broke " + self._pin_when(p)
            self.last_pin_end = {"pinner": name, "pinned": p["defender"], "how": how, "second": p["seconds"],
                                 "turn": self.turn, "note": note}
            return [{"type": "pin_broken", "attacker": name, "defender": p["defender"], "seconds": p["seconds"],
                     "duration": p["duration"], "why": why, "note": note}]
        del self.pins[key]
        p["attacker"], p["helpers"] = rest[0], rest[1:]
        self.pins[f"{rest[0]}>{p['defender']}"] = p
        note = (f"{why}, so she is off the pin on {p['defender']}; {' and '.join(rest)} still "
                f"{'has' if len(rest) == 1 else 'have'} her pinned"
                + ("" if self.fade_mode() else f" (second {p['seconds']})"))
        return [{"type": "pin_left", "attacker": name, "defender": p["defender"], "still": rest, "seconds": p["seconds"],
                 "duration": p["duration"], "why": why, "note": note}]

    def _pinned_reach(self, a, defenders, enforce, what="attack"):
        """A pinned fighter can only reach the one on top of her: no attacks, grabs, or pins on anyone else."""
        on_top = self.pinned_by(a.name)
        if not enforce or not on_top:
            return
        others = [d for d in defenders if d not in on_top]
        if others:
            raise ValueError(f"{a.name} is PINNED under {on_top[0]}: she can't {what} {others[0]} from there. She can "
                             f"'struggle', or strike {on_top[0]} with a free limb")

    # ---------- sides: teams that last, and alliances that don't ----------
    def allies(self, a, d):
        return a is not d and a.team == d.team

    def _no_friendly_fire(self, a, defenders, enforce):
        """The director can't have a fighter attack, hold, or pin someone on her own side."""
        if not enforce:
            return
        for d in defenders:
            d = d if isinstance(d, Fighter) else self.get(d)
            if self.allies(a, d):
                raise ValueError(f"{a.name} and {d.name} are on the same side ({a.team}): they don't attack each other. "
                                 f"Choose an opponent")

    def _let_go_between(self, fighters, why):
        """Fighters who are now on one side stop holding and pinning each other."""
        names = {f.name for f in fighters}
        out = []
        for key, p in list(self.pins.items()):
            if key in self.pins and p["defender"] in names:
                for m in [m for m in self.pin_members(p) if m in names]:
                    out += self._leave_pin(f"{p['attacker']}>{p['defender']}", m, why, how="was let go")
        for h in list(self.holds.values()):
            if h.attacker in names and h.defender in names and h.id in self.holds:
                del self.holds[h.id]
                out.append({"type": "hold_end", "hold_id": h.id, "attacker": h.attacker, "defender": h.defender,
                            "part": h.part, "beats_held": h.turns_active, "reason": why, "flavor": h.flavor})
        return out

    def _same_side(self, names, what):
        fs = []
        for n in names:
            f = self.get_active(n)
            if f not in fs:
                fs.append(f)
        if len(fs) < 2:
            raise ValueError(f"{what} needs at least two different fighters who are still in the fight")
        if not [f for f in self.active() if f not in fs]:
            raise ValueError(f"that would put everyone still fighting on one side: {what} needs someone left to fight")
        return fs

    def set_team(self, names, team=None):
        """Put fighters on one side until you change it: they don't attack each other, and they win together."""
        fs = self._same_side(names, "a team")
        label = str(team or " and ".join(f.name for f in fs))
        for f in fs:
            f.team = label
        self.alliances = [al for al in self.alliances if not set(al["members"]) & {f.name for f in fs}]
        return {"type": "team", "members": [f.name for f in fs], "team": label,
                "knock_on": self._let_go_between(fs, "they are on the same side now")}

    def leave_team(self, name):
        f = self.get(name)
        f.team = f.name
        self.alliances = [al for al in self.alliances if f.name not in al["members"]]
        return f.name

    def ally(self, names, beats=None, until=None):
        """A temporary alliance: these fighters work together and don't attack each other for `beats` beats, or
        until `until` is out; either way it ends the moment nobody else is left to fight, and then they are
        opponents again. Returns the event."""
        fs = self._same_side(names, "an alliance")
        if until:
            until = self.get_active(until).name
            if until in [f.name for f in fs]:
                raise ValueError(f"{until} is in the alliance: 'until' names the one they team up against")
        for al in list(self.alliances):  # nobody is in two alliances at once
            if set(al["members"]) & {f.name for f in fs}:
                self.end_alliance(al, "a new alliance replaced it")
        home = {f.name: f.team for f in fs}
        label = " and ".join(f.name for f in fs)
        for f in fs:
            f.team = label
        al = {"members": [f.name for f in fs], "name": label, "beats": int(beats) if beats else None, "until": until,
              "home": home}
        self.alliances.append(al)
        self.involved.update(al["members"])
        return {"type": "alliance", "members": al["members"], "beats": al["beats"], "until": until,
                "against": [f.name for f in self.active() if f.name not in al["members"]],
                "knock_on": self._let_go_between(fs, "they are allies now")}

    def end_alliance(self, al, why):
        if al in self.alliances:
            self.alliances.remove(al)
        for n in al["members"]:
            f = self.fighters.get(n.lower())
            if f is not None:
                home = al["home"].get(n, n)
                f.team = n if home == al["name"] else home
        return {"type": "alliance_end", "members": list(al["members"]), "why": why,
                "still_in": [n for n in al["members"] if not self.get(n).eliminated]}

    def alliance_terms(self, al):
        if al.get("until"):
            return f"until {al['until']} is out"
        if al.get("beats") is not None:
            return f"for {al['beats']} more beat{'s' if al['beats'] != 1 else ''}"
        return "until nobody else is left to fight"

    def _alliance_tick(self, count=True):
        """End alliances whose time is up, whose target is out, or that have nobody left to fight."""
        events = []
        for al in list(self.alliances):
            alive = [m for m in al["members"] if not self.get(m).eliminated]
            others = [f for f in self.active() if f.name not in al["members"]]
            why = None
            if len(alive) < 2:
                why = "only one of them is left"
            elif not others:
                why = "nobody else is left to fight"
            elif al.get("until") and self.get(al["until"]).eliminated:
                why = f"{al['until']} is out"
            elif count and al.get("beats") is not None:
                al["beats"] -= 1
                if al["beats"] <= 0:
                    why = "its time is up"
            if why:
                events.append(self.end_alliance(al, why))
        return events

    def sides_text(self):
        """Who is on whose side right now, in a sentence or two ('' when everyone fights alone)."""
        out = []
        temp = {al["name"]: al for al in self.alliances}
        teams = {}
        for f in self.active():
            teams.setdefault(f.team, []).append(f.name)
        for team, members in teams.items():
            if len(members) < 2:
                continue
            if team in temp:
                out.append(f"{' and '.join(members)} are ALLIES for now ({self.alliance_terms(temp[team])}): they work "
                           f"together and do not attack each other; when it ends they are opponents again")
            else:
                out.append(f"{' and '.join(members)} are a TEAM ({team}): they fight together, never against each "
                           f"other, and win together")
        return ". ".join(out) + ("." if out else "")

    def _can_act(self, a, enforce):
        if enforce and a.name in self.pressed:
            info = self.pressed[a.name]
            raise ValueError(f"{a.name} has just been driven into {info['surface']} by {info['by']} and is still pressed "
                             f"against it: she can't attack, grab, or pin anyone this beat (the engine rolls whether she "
                             f"crumples; she can hit back next beat)")
        if enforce and self.has(a, "flinched"):
            raise ValueError(f"{a.name} FLINCHED and can't attack this beat; let someone else act, or have {a.name} "
                             f"recover (breather)")
        if enforce and self.has(a, "stunned"):
            raise ValueError(f"{a.name} is STUNNED from the blow to her head and can't act this beat: no attack, no "
                             f"grab, no dodge; let someone else act, or have {a.name} sway there (breather)")
        for st in ("asleep", "frozen"):
            if enforce and self.has(a, st):
                raise ValueError(f"{a.name} is {st.upper()} and can't act; let someone else act (her opponent can "
                                 f"attack or pin her freely)")

    def energy_cost(self, move=None, kind=None):
        costs = self._cfg("energy").get("costs", {})
        if move is not None and move.get("energy") is not None:
            return float(move["energy"])
        if move is not None:
            kind = "improvised" if move.get("improvised") else move.get("target", "targeted")
        return float(costs.get(kind or "strike", 6))

    def _spend(self, f, cost, enforce, what="that"):
        if not self._cfg("energy").get("enabled", True):
            return
        if enforce and f.energy < cost:
            can = [m["name"] for m in f.moves if self.energy_cost(m) <= f.energy and f.move_uses.get(m["name"], 1) > 0
                   and m.get("target") not in ("self",)]
            raise ValueError(f"{f.name} is too worn out for {what} (energy {f.energy:.0f}, needs {cost:.0f}). "
                             + (f"Moves she can still afford: {', '.join(can)}; or an improvised blow (costs "
                                f"{self.energy_cost(kind='improvised'):.0f}), or let her catch her breath"
                                if can else "Let her catch her breath ('breather'), or an improvised blow if she "
                                f"has {self.energy_cost(kind='improvised'):.0f} energy"))
        f.energy = max(0.0, f.energy - cost / self.trait(f, "stamina"))

    def dodge_chance(self, a, d, target="targeted"):
        cfg = self._cfg("evasion")
        if (not cfg.get("enabled", True) or target in ("whole_body", "hold") or d.name in self.downed
                or d.name in self.pressed
                or any(p["defender"] == d.name for p in self.pins.values()) or self.has(d, "paralyzed")
                or self.has(d, "asleep") or self.has(d, "frozen")):
            return 0.0
        if self.grab_between(a.name, d.name):
            return 0.0   # held at point-blank: there is nowhere to go (it cuts both ways)
        if any(h.attacker == d.name and h.defender == a.name for h in self.holds.values()):
            return 0.0   # she has hold of her (a submission, a grip): locked on, she can't spring away
        if any(h.attacker == a.name and h.defender == d.name for h in self.holds.values()):
            return 0.0   # she is held by her (jaws on her arm, tails round her leg): she can't spring out of reach
        if self.pinning(d.name):
            return 0.0   # on top of someone, pinning her down: she can't spring away without letting go
        if (getattr(self, "hauled", None) or {}).get(d.name) == (a.name, self.turn):
            return 0.0   # hauled up and held there by this same attacker this beat
        if (getattr(self, "_juggle", None) or {}).get("who") == d.name:
            return 0.0   # knocked up into the air by the last blow: nothing to push off from
        sc = self._cfg("status_effects")
        slow = (float(sc.get("stiff_dodge_mult", 0.6)) if self.has(d, "stiff") else 1.0) * \
               (float(sc.get("cramped_dodge_mult", 0.7)) if self.has(d, "cramped") else 1.0) * \
               (float(sc.get("constricted_dodge_mult", 0.3)) if self.has(d, "constricted") else 1.0) * \
               (float(sc.get("bound_dodge_mult", 0.75)) if self.has(d, "bound") else 1.0) * \
               (float(sc.get("sputtering_dodge_mult", 0.8)) if self.has(d, "sputtering") else 1.0) * \
               (float(sc.get("off_balance_dodge_mult", 0.6)) if self.has(d, "off_balance") else 1.0) * \
               (float(sc.get("staggered_dodge_mult", 0.6)) if self.has(d, "staggered") else 1.0) * \
               (float(sc.get("dazed_dodge_mult", 0.4)) if self.has(d, "dazed") else 1.0) * \
               (0.0 if self.has(d, "stunned") else 1.0) * \
               (float(sc.get("dead_leg_dodge_mult", 0.75)) if self.has(d, "dead_leg") else 1.0) * \
               (float(sc.get("limping_dodge_mult", 0.85)) if self.has(d, "limping") else 1.0) * \
               (float(sc.get("ribs_aching_dodge_mult", 0.9)) if self.has(d, "ribs_aching") else 1.0) * \
               (float(sc.get("tail_numb_dodge_mult", 0.85)) if self.has(d, "tail_numb") else 1.0) * \
               (float(sc.get("rattled_dodge_mult", 0.85)) if self.has(d, "rattled") else 1.0) * \
               (float(sc.get("wobbly_dodge_mult", 0.7)) if self.has(d, "wobbly") else 1.0) * \
               (float(sc.get("ears_ringing_dodge_mult", 0.9)) if self.has(d, "ears_ringing") else 1.0) * \
               (float(sc.get("whiplash_dodge_mult", 0.9)) if self.has(d, "whiplash") else 1.0) * \
               (float(sc.get("doubled_over_dodge_mult", 0.5)) if self.has(d, "doubled_over") else 1.0) * \
               (float(sc.get("greyed_dodge_mult", 0.3)) if self.has(d, "greyed") else 1.0) * \
               (self._low_cfg("last_stand").get("open_dodge_mult", 0.2) if self.has(d, "overextended") else 1.0)
        s = max(0.0, min(1.0, self.strength(d) / 100))
        # what she runs on: a biped's or a bird's fore_low is arms or wingtips, not legs
        feet = ("hind_up", "hind_low", "tail") + (("fore_low",) if self.body_plan(d) == "quadruped" else ())
        legs = [p.damage for p in d.parts.values() if body_region(p.name) in feet]
        leg = 1.0 / (1.0 + (sum(legs) / len(legs) if legs else 0) / 150.0)
        flying = self.has(d, "airborne")
        if flying:
            # in the air she dodges on her wings, not her legs: a hurt wing beats unevenly and slow, hurt flight
            # muscles (shoulders, chest, back) and a ringing head make every swerve late (flight.dodge)
            fd = (self.rules.get("flight") or {}).get("dodge") or {}
            def avg(regions):
                xs = [p.damage for p in d.parts.values() if body_region(p.name) in regions]
                return sum(xs) / len(xs) if xs else 0.0
            wings = [p.damage for p in d.parts.values() if "wing" in p.name.lower()]
            w = (max(wings) + sum(wings) / len(wings)) / 2 if wings else 0.0   # the worse wing counts double
            leg = (1.0 / (1.0 + w / float(fd.get("wing_per", 100)))
                   / (1.0 + avg(("shoulder", "chest", "belly", "back_up", "back_low")) / float(fd.get("body_per", 250)))
                   / (1.0 + avg(("head", "neck")) / float(fd.get("head_per", 400))))
        ch = float(cfg.get("base", 0.18)) * (0.4 + 0.6 * s) * leg * slow
        if self.has(d, "chilled"):
            ch *= 0.5
        if d.energy < float(self._cfg("energy").get("tired_below", 25)):
            ch *= 0.7
        if self.has(d, "adrenaline"):
            ch *= 1.3
        if self.has(a, "paralyzed"):
            ch *= 1.3
        if flying and not self.has(a, "airborne"):
            # the edge the air gives her fades as her wings fail: gone by the time a wing would ground her
            fcfg = self.rules.get("flight") or {}
            left = max(0.0, 1.0 - self.wing_damage(d) / max(1.0, float(fcfg.get("ground_at", 150))))
            ch *= 1.0 + (float(fcfg.get("airborne_dodge_mult", 1.3)) - 1.0) * left
        wet = self.in_water(d.name)
        if wet:   # in the water a Water type is at home and everyone else is wading (arena.water_dodge)
            wcfg = (self.rules.get("arena") or {}).get("water_dodge") or {}
            native = "Water" in (d.types or [])
            ch *= float(wcfg.get(("native_" if native else "other_") + wet, 1.0))
        if target == "spread":
            ch *= 0.5
        if getattr(self, "_chain_on", None) == (a.name, d.name):
            ch *= float(cfg.get("chain_mult", 0.5))   # the blow before this one landed: she is still rocked by it
        return round(min(float(cfg.get("max", 0.35)), ch), 3)

    def run_break_chance(self, a, d, n, start, step):
        """The chance that a run of blows (a chain, a pummel) ends before its next one. It grows with every blow
        already thrown (n = how many past the point where the run may first end), and BOTH fighters' condition
        counts: a tired attacker can't keep it up, a fresh defender finds a way out sooner."""
        att = max(0.0, min(1.0, self.strength(a) / 100.0))
        de = max(0.0, min(1.0, self.strength(d) / 100.0))
        mult = (1.4 - 0.8 * att) * (0.6 + 0.8 * de)
        return round(max(0.0, min(0.95, (float(start) + float(step) * max(0, n)) * mult)), 3)

    def chain_break(self, attacker, defender, link):
        """Before link 3 and every later link of a chain: does the chain end here? None (it goes on), "dodge" (she
        gets clear of this one: the usual dodge, with its chance of a counter) or "spent" (she can't dodge where she
        is, so it is the attacker who has nothing left to follow with). director.chain: break_start, break_step."""
        cfg = self.rules.get("director", {}).get("chain", {}) or {}
        a, d = self.get(attacker), self.get(defender)
        p = self.run_break_chance(a, d, int(link) - 3, cfg.get("break_start", 0.10), cfg.get("break_step", 0.12))
        if p <= 0 or not self._chance(p, f"the chain ending before link {link}", "it ENDS here", "it goes on"):
            return None
        return "dodge" if self.dodge_chance(a, d, "targeted") > 0 else "spent"

    def dodge_roll(self, a, d, target, move_name=None):
        """None if the attack lands; otherwise the dodge (and maybe a counter-hit). A move that has already landed on
        her twice is one she has learned to read (learning.dodge_per_hit)."""
        if a.name in self.lucky:
            return None   # /play dice free: her attacks always land
        ch = self.dodge_chance(a, d, target) * self.dominated(d.name) * self.trait(d, "speed")
        q = self.quirk(a, "overwhelming")
        if q and float((move_name and next((m.get("power", 0) for m in a.moves if m["name"] == move_name), 0)) or 0) \
                >= float(q.get("big_from", 22)):
            ch *= float(q.get("dodge_mult", 1.15))     # (a big wind-up: easier to see coming)
        lcfg = self.rules.get("learning") or {}
        seen = (d.learned.get("moves") or {}).get(f"{a.name}|{move_name}", 0) if move_name else 0
        quick = 1 if (self.trait(d, "learning") >= 1.4 or self.quirk(a, "predictable")) else 2
        if ch > 0 and seen >= quick and lcfg.get("enabled", True):
            ch = min(float(self._cfg("evasion").get("max", 0.35)) * 1.3,
                     ch * min(float(lcfg.get("dodge_cap", 1.5)), 1 + float(lcfg.get("dodge_per_hit", 0.2)) * (seen - 1)))
        wcfg = (self.rules.get("learning") or {}).get("wary") or {}
        wary = bool(move_name and ch > 0 and wcfg.get("enabled", True)
                    and (d.learned.get("wary") or {}).get(f"{a.name}|{move_name}"))
        if wary:      # it hurt her badly before: she flinches away from it early
            ch = min(0.6, ch * float(wcfg.get("dodge_mult", 1.25)))
        forced, self._force_dodge = bool(getattr(self, "_force_dodge", False)) and ch > 0, False
        sp_ = self.trait(d, "speed")
        if not forced and (ch <= 0 or not self._chance(ch, f"{d.name} dodging {poss_word(a.name)} attack"
                                                       + (f" (speed ×{sp_:g})" if sp_ != 1 else ""), "DODGED",
                                                       "it lands")):
            return None
        # (the ways of dodging that need her legs, a step aside or a spring back, grow rarer as her legs are hurt;
        # in the air she dodges on her wings)
        if q and float((move_name and next((m.get("power", 0) for m in a.moves if m["name"] == move_name), 0)) or 0) \
                >= float(q.get("big_from", 22)):
            self.quirk_moment(a, "overwhelming", f"{poss_word(a.name)} huge wind-up gave the blow away: all that "
                                                 f"strength, and {d.name} saw it coming")
        ecfg = self._cfg("evasion")
        legw = 0.0 if self.has(d, "airborne") else self._leg_worst(d)
        legs_ok = 1.0 / (1.0 + legw / float(ecfg.get("leg_manner_halves_at", 80)))
        manner = self.vary("dodge", scale={m: legs_ok for m in ecfg.get("leg_manners", ["spring_back", "sidestep"])})
        out = {"dodged": True, "dodge_chance": ch, "counter_hits": [], "manner": manner, "wary": wary}
        if forced:
            out["chain_broken"] = True
        acfg = self.rules.get("arena") or {}
        if self.on_slick(d.name) and d.name not in self.downed:
            sp = float(acfg.get("slip_chance", 0.2)) * (float(acfg.get("slip_native_mult", 0.4))
                                                         if "Water" in (d.types or []) and self.in_water(d.name) else 1.0)
            if sp > 0 and self._chance(sp, f"{d.name} slipping as she dodges on the slick footing", "she slips", "she keeps her feet"):
                out["slipped"] = {"facing": self.knock_down(d.name, why=f"{d.name} slipped as she dodged")}
                return out      # she gets out of its way and goes down: no counter from the ground
        cfg = self._cfg("evasion")
        dc = ((self.rules.get("flight") or {}).get("dive_counter") or {})
        dive = bool(getattr(self, "_dive_now", False)) and dc.get("enabled", True)
        cch = float(dc.get("on_dodge", 0.45) if dive else cfg.get("counter_chance", 0.35)) * self.dominated(d.name) * self.trait(d, "speed")
        if not self.has(d, "flinched") and self._chance(cch, f"{d.name} countering after the dodge"
                                                             + (" as the dive goes past" if dive else ""),
                                                         "she counters", "no counter"):
            reach = [p for p in a.parts if body_region(p) in ("head", "neck", "chest", "shoulder", "fore_up", "fore_low",
                                                              "belly")] or list(a.parts)
            power = self.power_for("instant", cfg.get("counter_severity", "solid"))
            if dive:
                # she steps aside and strikes as the flyer streaks past: the flyer's own speed is in the blow, and it
                # finds whatever goes by (a wing, the belly, the tail) as much as the front of her
                reach = [p for p in a.parts if not re.search(r"\bhead\b|horn|antenna|ear|eye|nose", p, re.I)] or reach
                power = round(power * float(dc.get("momentum", 1.25)), 2)
                out["dive_counter"] = True
            mine, self._source = self._source, f"{poss_word(d.name)} counter"  # her blow, not the attack she dodged
            out["counter_hits"] = [self._apply_damage(a, self.rng.choice(reach), power)]
            self._source = mine
            self.involved.add(d.name)
        return out

    def _attacked(self, attacker, defenders, landed=True):
        """Bookkeeping for one attacking action: who has the momentum, attacks taken since the last pin,
        A fighter on the ground who attacks does it from the ground; getting up is rolled at the end of the beat."""
        self.momentum = (self.momentum + [f"{attacker}>{','.join(defenders)}"])[-20:]
        for n in defenders if landed else []:  # a dodged attack doesn't count toward the pin rule
            self.since_pin[n] = self.since_pin.get(n, 0) + 1

    FRONT_REGIONS = ("chest", "belly")
    BACK_REGIONS = ("back_up", "back_low")

    def _lose_grip(self, name, why, on_her=False, keep_on=None):
        """Everything `name` was pinning or holding ends (she was knocked down, thrown, taken down into a pin, put to
        sleep). on_her: holds and pins ON her end too (she was thrown clear of them). keep_on: a fighter she keeps
        her grip on (the one taking her down). Returns what ended, for the display and the story."""
        out = []
        for key, p in list(self.pins.items()):
            if key not in self.pins:
                continue
            if on_her and p["defender"] == name:  # thrown clear: the whole pin on her is over, whoever was pressing
                for h in self._pin_holds(p):
                    self.holds.pop(h.id, None)
                del self.pins[key]
                who = " and ".join(self.pin_members(p))
                note = f"{why}, clear of the pin {who} had on her " + self._pin_when(p)
                self.last_pin_end = {"pinner": p["attacker"], "pinned": p["defender"], "how": "got free",
                                     "second": p["seconds"], "turn": self.turn, "note": note}
                out.append({"type": "pin_broken", "attacker": p["attacker"], "defender": p["defender"],
                            "seconds": p["seconds"], "duration": p["duration"], "why": why, "note": note})
            elif name in self.pin_members(p) and p["defender"] != keep_on:
                out += self._leave_pin(key, name, why)
        for h in list(self.holds.values()):
            if (h.attacker == name and h.defender != keep_on) or (on_her and h.defender == name):
                del self.holds[h.id]
                out.append({"type": "hold_end", "hold_id": h.id, "attacker": h.attacker, "defender": h.defender,
                            "part": h.part, "beats_held": h.turns_active, "reason": why, "flavor": h.flavor})
        return out

    def knock_down(self, name, facing=None, parts=(), why="", thrown=False):
        """Put a fighter on the ground, landing face-down, face-up, or on her side: given, or worked out from the
        parts that hit the ground (back first = face-up; chest, belly or face first = face-down), else rolled.
        Going down ends every pin and hold she had on anyone; thrown=True (hurled through the air) also tears her
        out of any hold or pin ON her. A fighter who is already down stays as she lies (a named facing still
        applies); one who is pinned can't fall any further. What ended is left in _knock_on."""
        n = self.get(name).name
        self._knock_on = []
        down_ = self.__dict__.setdefault("ever_down", [])
        if n not in down_:
            down_.append(n)        # (who has been down at all this fight: the story can't have her "get back up" before)
        self.pressed.pop(n, None)  # she's off whatever a charge left her against
        self.get(n).status.pop("airborne", None)  # knocked out of the air: she's down, not flying
        if n not in self.downed:
            getattr(self, "lying_at", {}).pop(n, None)  # a new fall: not at the foot of whatever she fell by before
            getattr(self, "lying_on", {}).pop(n, None)  # ...nor on what she lay on last time
        if self.pinned_by(n) and not thrown:
            if facing:
                self.facing[n] = facing
                self._settle_facing(n)
            return self.facing.get(n)
        loose = self._lose_grip(n, why or f"{n} was {'thrown' if thrown else 'knocked down'}", on_her=thrown)
        already = n in self.downed
        if not already:
            self.downed[n] = 0
            self._count("down", n)
        if not already or thrown:
            self._fresh_down.add(n)  # just hit the ground: no getting up until the next beat
        if facing or not already or thrown or n not in self.facing or self.facing.get(n) == "sitting up":
            self.facing[n] = facing or self._guess_facing(n, parts)   # a sitting fighter is knocked flat
        self._settle_facing(n)
        self._knock_on = loose
        return self.facing[n]

    def stand_up(self, name):
        """Put a fighter back on her feet with no roll (your command). Not while she's pinned."""
        f = self.get(name)
        on_top = self.pinned_by(f.name)
        if on_top:
            raise ValueError(f"{f.name} is pinned under {on_top[0]}: end the pin first (/pinescape {on_top[0]} "
                             f"{f.name}, or /release {on_top[0]} {f.name})")
        self.downed.pop(f.name, None)
        self._fresh_down.discard(f.name)
        if not f.eliminated:
            self.facing.pop(f.name, None)

    def flatten(self, name, parts=()):
        """A fighter who was sitting up and has just been hit goes flat: onto her back if the blow came from the
        front, onto her front if it came from behind. Returns the event, or None if she wasn't sitting."""
        n = self.get(name).name
        if n not in self.downed or self.facing.get(n) != "sitting up":
            return None
        if any(h.defender == n for h in self.holds.values()):
            return None   # someone has hold of her: she is kept where she is
        regions = [body_region(p) for p in parts]
        front = sum(r in self.FRONT_REGIONS or r in ("neck", "head") for r in regions)
        back = sum(r in self.BACK_REGIONS for r in regions)
        self.facing[n] = "face-down" if back > front else "face-up"
        return {"type": "flattened", "fighter": n, "facing": self.facing[n]}

    def _settle_facing(self, name, parts_win=False):
        """Make the presses on a downed fighter agree with the way she lies. Normally presses on the side against
        the ground move to the exposed side; with parts_win (your own /pin or /hold with named parts) she is turned
        to match the presses instead. If neither works she's taken to be on her side, where both are reachable."""
        if name not in self.downed and not self.get(name).eliminated:
            return []
        on_her = [h for h in self.holds.values() if h.defender == name]

        def hidden_presses():
            fc = self.facing.get(name)
            if fc not in ("face-down", "face-up"):
                return []
            hid = self.FRONT_REGIONS if fc == "face-down" else self.BACK_REGIONS
            return [h for h in on_her if not re.search(r"\bflank|side\b", h.part.lower())
                    and (body_region(h.part) in hid or (fc == "face-down" and re.search(r"\bthroat\b", h.part.lower())))]
        moved = []
        if parts_win and hidden_presses():
            regions = [body_region(h.part) for h in on_her]
            front = any(r in self.FRONT_REGIONS for r in regions) or any("throat" in h.part.lower() for h in on_her)
            back = any(r in self.BACK_REGIONS for r in regions)
            self.facing[name] = "on her side" if front and back else "face-up" if front else "face-down"
        else:
            moved = self._refit_holds(name)
        if hidden_presses():
            self.facing[name] = "on her side"
        return moved

    def repair_state(self):
        """Bring every tracked posture back into agreement (after loading a save, or a hand edit): nobody out of the
        fight is pinned or held, every downed fighter has a way she lies, every pin has its presses."""
        active = {f.name for f in self.active()}
        for h in list(self.holds.values()):
            if h.attacker not in active or h.defender not in active or h.part not in self.get(h.defender).parts:
                del self.holds[h.id]
        for key, p in list(self.pins.items()):
            for m in self.pin_members(p):  # a pinner who is out, down, or no longer pressing is off the pin
                k = f"{p['attacker']}>{p['defender']}"
                if k in self.pins and (m not in active or m in self.downed or not any(
                        h.attacker == m and h.defender == p["defender"] for h in self.holds.values())):
                    self._leave_pin(k, m, "the pin fell apart")
            k = f"{p['attacker']}>{p['defender']}"
            if k in self.pins and p["defender"] not in active:
                for h in self._pin_holds(p):
                    self.holds.pop(h.id, None)
                del self.pins[k]
        for p in self.pins.values():
            self.downed.setdefault(p["defender"], 0)
        for n in list(self.downed):
            if n not in active:
                del self.downed[n]
            elif self.facing.get(n) not in self.FACING_LOOK:
                self.facing[n] = self._guess_facing(n)
        for n in list(self.facing):
            f = self.fighters.get(n.lower())
            if f is None or (n not in self.downed and not f.eliminated):
                del self.facing[n]
        for f in self.fighters.values():
            if f.eliminated and self.facing.get(f.name) not in self.FACING_LOOK:
                self.facing[f.name] = self._guess_facing(f.name)
            f.status = {k: v for k, v in f.status.items() if v > 0}
            f.energy = max(0.0, min(100.0, f.energy))
        for n in list(self.downed):
            self._settle_facing(n)

    def check_state(self):
        """The rules that must always hold between beats, checked without changing anything: a list of what is wrong
        (empty when all is well). Health may run below zero (health.collapse), so that is never flagged."""
        bad = []
        fin = lambda x: isinstance(x, (int, float)) and math.isfinite(x)
        active = {f.name for f in self.active()}
        for f in self.fighters.values():
            if not fin(f.health) or not fin(f.max_health) or f.max_health <= 0:
                bad.append(f"{f.name}: health is {f.health}/{f.max_health}")
            if not fin(f.energy) or not -0.01 <= f.energy <= 100.01:
                bad.append(f"{f.name}: energy is {f.energy}")
            for p in f.parts.values():
                if not fin(p.damage) or p.damage < -0.01 or not fin(p.resistance):
                    bad.append(f"{poss_word(f.name)} {p.name}: damage {p.damage}, resistance {p.resistance}")
            for st, n in f.status.items():
                if not isinstance(n, (int, float)) or n <= 0:
                    bad.append(f"{f.name}: status {st} has {n} beats left")
            if self.has(f, "airborne"):
                if f.name in self.downed:
                    bad.append(f"{f.name} is in the air and on the ground at once")
                if self.pin_on(f.name) or self.pinning(f.name):
                    bad.append(f"{f.name} is in the air and in a pin")
            if f.eliminated and f.name in self.downed:
                bad.append(f"{f.name} is out of the fight but still counted as knocked down")
        for h in self.holds.values():
            if h.attacker not in active or h.defender not in active:
                bad.append(f"hold {h.id} ({h.attacker} on {h.defender}) involves someone out of the fight")
            elif h.part not in self.get(h.defender).parts:
                bad.append(f"hold {h.id} grips {poss_word(h.defender)} '{h.part}', a part she doesn't have")
            if not fin(h.power) or h.power < 0:
                bad.append(f"hold {h.id} has power {h.power}")
        for key, p in self.pins.items():
            d = p.get("defender")
            if key != f"{p.get('attacker')}>{d}":
                bad.append(f"pin '{key}' is filed under the wrong names ({p.get('attacker')} on {d})")
            for m in self.pin_members(p):
                if m not in active:
                    bad.append(f"{m} is out of the fight but still pinning {d}")
                elif not any(h.attacker == m and h.defender == d for h in self.holds.values()):
                    bad.append(f"{m} is pinning {d} without pressing anything")
                if self.pinned_by(m):
                    bad.append(f"{m} is pinning {d} while pinned herself")
            if d not in active:
                bad.append(f"{d} is out of the fight but still pinned")
            elif d not in self.downed:
                bad.append(f"{d} is pinned but not on the ground")
        for n in self.downed:
            if n in active and self.facing.get(n) not in self.FACING_LOOK:
                bad.append(f"{n} is down with no way she lies ({self.facing.get(n)})")
        if len({p["defender"] for p in self.pins.values()}) < len(self.pins):
            bad.append("one fighter is under two separate pins")
        return bad

    def _guess_facing(self, name, parts=()):
        regions = [body_region(p) for p in parts]
        front = sum(r in self.FRONT_REGIONS for r in regions) + sum(
            1 for p in parts if re.search(r"\b(muzzle|nose|face|jaw|cheek|chin|sac|ruff)\b", p.lower()))
        back = sum(r in self.BACK_REGIONS for r in regions)
        if self.body_plan(self.get(name)) == "serpent" and not (front or back):
            return "on her side"
        if back > front:
            return "face-up"
        if front > back:
            return "face-down"
        return self.rng.choices(["face-down", "face-up", "on her side"], [0.4, 0.35, 0.25])[0]

    def lying_out(self, f):
        """A knocked-out fighter who hasn't made it back to her feet yet: still lying where she fell."""
        stages = self.rules.get("recovery", {}).get("stages") or self.RECOVERY_DEFAULT
        return f.eliminated and f.recovery < len(stages) - 1

    def facing_of(self, name):
        """Which way a fighter on the ground lies (a downed fighter, or one knocked out and not yet back up), or
        None if she's on her feet."""
        f = self.get(name)
        if f.name in self.downed or self.lying_out(f):
            return self.facing.get(f.name)
        return None

    FACING_LOOK = {
        "face-down": "lying FACE-DOWN: chest, belly and face against the ground; her back, hips, tail and the back of "
                     "her neck are exposed",
        "face-up": "lying on her BACK, face-up: her chest, belly, throat and face are exposed; her back is against "
                   "the ground",
        "on her side": "lying ON HER SIDE: one flank against the ground, the other side exposed",
        "sitting up": "SITTING UP on the ground (not lying, not standing): her chest, belly, throat and face are open "
                      "in front, her back and the back of her neck behind; she is NOT on her feet",
    }

    REPOSITIONS = ["none", "roll over", "onto her back", "onto her front", "onto her side", "sit her up", "pick up",
                   "stand her up", "take off", "land"]

    def reposition(self, attacker, defender, how, force=False):
        """The attacker moves a fighter who's down: rolls her over (or onto her back, front, or side), or hauls her up
        off the ground (to slam, throw, or hold her up for a strike). A running pin's presses follow the roll.
        Returns an event, or None if it doesn't apply. Limited by director.reposition_cooldown beats per fighter."""
        how = str(how or "none").lower()
        if how in ("", "none", "take off", "land"):
            return None   # her own flight, not moving anyone (director.resolve_many handles it)
        a, d = self.get_active(attacker), self.get_active(defender)
        if a is d:
            return None
        if self.pinned_by(a.name) or (how in ("pick up", "stand her up") and a.name in self.downed):
            return None  # she's held down herself, or on the ground: she can't haul anyone anywhere
        if not force and (a.name in self.pressed or any(self.has(a, st) for st in ("asleep", "frozen", "flinched"))):
            return None
        cool = int(self.rules.get("director", {}).get("reposition_cooldown", 2) or 0)
        last = getattr(self, "_last_reposition", {}).get(d.name)
        if not force and last is not None and self.turn - last < cool:
            return None  # just moved her: not every beat
        before = self.facing_of(d.name)
        def resisted():
            """She is on the ground and not pinned: with strength left she may fight off being moved (director only)."""
            if force or any(p["defender"] == d.name for p in self.pins.values()):
                return None
            rc = self.resist_chance(d)
            if rc > 0 and self._chance(rc, f"{d.name} fighting off being moved ({how})", "she won't be moved",
                                       "she is moved"):
                self._last_reposition = {**getattr(self, "_last_reposition", {}), d.name: self.turn}
                self.involved.update({a.name, d.name})
                return {"type": "reposition", "attacker": a.name, "defender": d.name, "how": how, "before": before,
                        "after": before, "resisted": True, "chance": rc, "manner": self.vary("hold_strain")}
            return None
        if how in ("pick up", "stand her up"):
            if d.name not in self.downed:
                return None
            if any(p["defender"] == d.name for p in self.pins.values()):
                return None  # she's pinned: the pin has to end first
            no = resisted()
            if no:
                return no
            self.downed.pop(d.name, None)
            self.facing.pop(d.name, None)
            self._fresh_down.discard(d.name)
            # held up in her hands for the rest of this beat: whatever she does to her next, there's no dodging it
            self.__dict__.setdefault("hauled", {})[d.name] = (a.name, self.turn)
            ev = {"type": "reposition", "attacker": a.name, "defender": d.name, "how": how, "before": before,
                  "after": "hauled up off the ground" if how == "pick up" else "dragged up onto her feet"}
        elif how == "sit her up":
            # hauled up to sitting: still on the ground, but everything above her hips is in reach, front and back.
            # A setup: the next blow knocks her flat again; a grip from behind keeps her there.
            if d.name not in self.downed or before == "sitting up":
                return None
            if any(p["defender"] == d.name for p in self.pins.values()):
                return None  # she's pinned flat: the pin has to end first
            no = resisted()
            if no:
                return no
            self.facing[d.name] = "sitting up"
            ev = {"type": "reposition", "attacker": a.name, "defender": d.name, "how": how, "before": before,
                  "after": "sitting up"}
        else:
            if d.name not in self.downed:
                return None
            target = {"roll over": {"face-down": "face-up", "face-up": "face-down", "on her side": "face-up",
                                    "sitting up": "face-down"}.get(before or "", "face-up"),
                      "onto her back": "face-up", "onto her front": "face-down", "onto her side": "on her side"}.get(how)
            if not target or target == before:
                return None
            no = resisted()
            if no:
                return no
            self.facing[d.name] = target
            moved = self._settle_facing(d.name)
            target = self.facing[d.name]
            ev = {"type": "reposition", "attacker": a.name, "defender": d.name, "how": how, "before": before,
                  "after": target, "holds_moved": moved}
        self._last_reposition = {**getattr(self, "_last_reposition", {}), d.name: self.turn}
        self.involved.update({a.name, d.name})
        return ev

    def resist_chance(self, d):
        """How likely a fighter lying on the ground (not pinned) is to fight off being rolled, hauled up, thrown or
        dragged when the DIRECTOR chooses it: down.resist_handling at full strength, less as she weakens. Your own
        commands always work."""
        if self.has(d, "asleep") or self.has(d, "frozen") or self.has(d, "paralyzed"):
            return 0.0
        base = float(self.rules.get("down", {}).get("resist_handling", 0.25))
        return round(max(0.0, min(0.9, base * max(0.0, min(1.0, self.strength(d) / 100.0)))), 3)

    def _refit_holds(self, defender):
        """After a roll or a fall, presses on the side that's now against the ground move to the exposed side. Two
        presses by the same fighter that end up on one spot become one (the stronger)."""
        moved = []
        for h in list(self.holds.values()):
            if h.defender != defender or h.id not in self.holds:
                continue
            new, note = self.fit_to_facing(defender, [h.part])
            if note and new and new[0] != h.part:
                moved.append(f"{h.part} → {new[0]}")
                h.part = new[0]
                for o in list(self.holds.values()):
                    if o.id != h.id and (o.attacker, o.defender, o.part) == (h.attacker, h.defender, h.part):
                        h.power, h.turns_active = max(h.power, o.power), max(h.turns_active, o.turns_active)
                        del self.holds[o.id]
        if moved:
            # the grips' own words still name the old spots ("her jaws in her throat"): point them at the new ones
            for pair in moved:
                old, new_ = [x.strip().lower() for x in pair.split("→")]
                for h in self.holds.values():
                    if h.defender == defender and h.flavor:
                        h.flavor = re.sub(r"\b" + re.escape(old) + r"\b", new_, h.flavor, flags=re.I)
        return moved

    def fit_to_facing(self, defender, part_names, flavor=""):
        """Pin/hold contacts that match how she's lying: on a face-down fighter, presses on the chest or belly move to
        her back (and the reverse face-up). If every contact is on the hidden side and the flavor says she's rolled
        over, she's turned over instead. Returns (new names, what changed)."""
        d = self.get(defender)
        facing = self.facing_of(d.name)
        if facing not in ("face-down", "face-up"):
            return list(part_names), None
        hidden = self.FRONT_REGIONS if facing == "face-down" else self.BACK_REGIONS
        regions = [body_region(p) for p in part_names]
        if part_names and all(r in hidden for r in regions) and re.search(
                r"\b(roll\w*|flip\w*|turn\w*|wrench\w*) (?:her |him |them )?(?:over|onto)", flavor or "", re.I):
            self.facing[d.name] = "face-up" if facing == "face-down" else "face-down"
            return list(part_names), f"rolled {d.name} over: now {self.facing[d.name]}"
        swap = ({"chest": "back_up", "belly": "back_low"} if facing == "face-down"
                else {"back_up": "chest", "back_low": "belly"})
        out, moved = [], []
        for p, r in zip(part_names, regions):
            if r in swap and not re.search(r"\bflank|side\b", p.lower()):  # flanks are reachable either way
                want = [x for x in d.parts if body_region(x) == swap[r] and not re.search(r"\bflank\b", x.lower())]
                if not want:  # e.g. an Absol has one "Back" instead of upper and lower
                    other = "back_up" if swap[r] == "back_low" else "back_low" if swap[r] == "back_up" else (
                        "belly" if swap[r] == "chest" else "chest")
                    want = [x for x in d.parts if body_region(x) == other and not re.search(r"\bflank\b", x.lower())]
                if want:
                    moved.append(f"{p} → {want[0]}")
                    out.append(want[0])
                    continue
            if facing == "face-down" and re.search(r"\bthroat\b", p.lower()):
                neck = [x for x in d.parts if re.search(r"\bneck\b", x.lower()) and x not in out]
                if neck:
                    moved.append(f"{p} → {neck[0]}")
                    out.append(neck[0])
                    continue
            out.append(p)
        return out, (f"{d.name} is {facing}: " + ", ".join(moved)) if moved else None

    def has_hurt_anyone(self, name):
        """True if any injury in this fight came from this fighter (so the story may refer back to her)."""
        me = self.get(name).name
        mine = poss_word(me)
        return any(str(src).startswith(mine) for key, srcs in self.injury_log.items()
                   if not key.startswith(me + "|") for src in srcs)

    def absent(self):
        """Fighters in fighters.json who are NOT in this fight (the story must never bring them in): name and
        species, with the species left out when someone who IS here shares it."""
        here = {f.name for f in self.fighters.values()}
        kinds = {self.species(f) for f in self.fighters.values()}
        return [{"name": n, "species": "" if sp in kinds else sp}
                for n, sp in getattr(self, "roster_species", {}).items() if n not in here]

    def species(self, f):
        """The species word the story uses for a fighter ("Buizel"), read from her description or appearance."""
        return species_of(f.description, getattr(f, "appearance", ""))

    def body_plan(self, f):
        names = " ".join(f.parts).lower()
        if "arm" in names:
            return "biped"      # arms first: a winged dragon (Charizard, Dragonite) holds and pins like a biped
        if "wing" in names:
            return "avian"
        if any(k in names for k in ("leg", "paw", "hock", "foot", "knee")):
            return "quadruped"
        return "serpent"

    def _getup_falls(self, f, ev, worst, cfg):
        """A failed try that drops her back down HARD (her legs give out, or she slips) can hurt: the limb that gave
        way, or what she lands on, takes a small jolt (getting_up.fall_chance, fall_power). A dizzy sinking-back or a
        breathless folding-down is soft and does no damage. Only the tries the narrator shows one by one count."""
        chance = float(cfg.get("fall_chance", 0.6) or 0)
        if chance <= 0:
            return
        shown = ev["fails"] if ev["stands"] else ev["fails"][:1]
        hits = []
        keep = self._source
        for i, kind in enumerate(shown):
            if kind not in ("gives_out", "slips"):
                continue
            if not self._chance(chance, f"{poss_word(f.name)} drop back down hurting", "it jars her", "it doesn't hurt"):
                continue
            hurt = [p for p in worst if p.damage >= 30]
            part = (hurt[0].name if kind == "gives_out" and hurt else
                    self.landing_parts(f.name, n=1)[0])
            power = float(cfg.get("fall_power", 8)) * self.rng.uniform(0.75, 1.25)
            self._source = f"{poss_word(f.name)} fall trying to get up"
            h = self._apply_damage(f, part, power)
            h["try"] = i + 1
            h["how"] = kind
            hits.append(h)
        self._source = keep
        if hits:
            ev["fall_hits"] = hits

    def get_up_tick(self):
        """Fighters on the ground try to get back up. How many tries it takes (1-3, or not this beat) comes from
        their overall strength and how hurt the limbs they push up with are; each beat down makes it easier."""
        cfg = self.rules.get("getting_up", {})
        events = []
        for f in self.fighters.values():
            if f.name not in self.downed:
                f.learned.pop("down_for", None)
        for name in list(self.downed):
            f = self.fighters.get(name.lower())
            if f is None or f.eliminated:
                self.downed.pop(name, None)
                continue
            # how long she has really been on the ground, pinned and held beats too (the get-up roll's own count,
            # self.downed, only runs while she is free to try)
            f.learned["down_for"] = int(f.learned["down_for"]) + 1 if "down_for" in f.learned else 0
            if any(p["defender"] == name for p in self.pins.values()):
                continue  # still pinned
            if any(h.defender == name and h.sub for h in self.holds.values()):
                continue  # locked in a submission hold: she can't rise until it's off
            if any(h.attacker == name and h.sub for h in self.holds.values()) and self.ground_lock_ok(name):
                continue  # working a submission from the ground (submissions.from_ground): she stays down with it
            if name in self._fresh_down:
                # just went down this beat: no get-up roll yet (said out loud, so nobody has to guess)
                events.append({"type": "stays_down", "fighter": name, "why": "fresh", "facing": self.facing.get(name)})
                continue
            if self.has(f, "asleep") or self.has(f, "frozen") or self.has(f, "stunned"):
                continue  # out of action: she isn't trying to rise
            beats = self.downed[name] = self.downed[name] + 1
            plan = self.body_plan(f)
            regions = {"biped": ("hind_up", "hind_low", "fore_up", "fore_low", "shoulder"),
                       "quadruped": ("hind_up", "hind_low", "fore_up", "fore_low", "shoulder"),
                       "serpent": ("tail", "belly", "back_low", "back_up"),
                       "avian": ("hind_up", "hind_low", "fore_up", "fore_low")}[plan]
            limbs = sorted((p for p in f.parts.values() if body_region(p.name) in regions), key=lambda p: -p.damage)
            worst = limbs[:3]
            avg = sum(p.damage for p in worst) / len(worst) if worst else 0.0
            strength = max(0.0, min(1.0, self.strength(f) / 100))
            score = strength / (1 + avg / float(cfg.get("limb_damage_halves_at", 200)))
            score += float(cfg.get("per_beat_down", 0.15)) * (beats - 1) + self.rng.uniform(-0.1, 0.1)
            if self.has(f, "adrenaline"):
                score += 0.2
            if self.has(f, "paralyzed"):
                score -= 0.3
            hsc = self._cfg("status_effects")
            if self.has(f, "wobbly"):
                score -= float(hsc.get("wobbly_getup", 0.25))     # (since build 293) her legs won't hold her yet
            if self.has(f, "concussed"):
                score -= float(hsc.get("concussed_getup", 0.1))
            if self.has(f, "dead_leg"):
                score -= float(hsc.get("dead_leg_getup", 0.2))
            if self.has(f, "back_spasm"):
                score -= float(hsc.get("back_spasm_getup", 0.15))
            # ruined: a leg past ruined.min folds under her as she pushes up on it; below zero she has less to rise with
            score -= self._ruined_getup(f, regions)
            ucfg = (self.rules.get("submissions") or {}).get("upright") or {}
            if any(h.defender == name and body_region(h.part) in ("hind_up", "hind_low") for h in self.holds.values()):
                # (since build 249) a grip on her leg holds that leg down: rising on it is much harder
                score -= float(ucfg.get("held_getup", 0.3))
            st0 = self.zero_stage(f)
            if st0:
                score += float(st0.get("getup", 0.0))
            cuts = cfg.get("thresholds", [0.7, 0.45, 0.2])
            tries = next((i + 1 for i, c in enumerate(cuts) if score >= c), None)
            if tries is None and beats >= int(cfg.get("max_beats_down", 4)):
                tries = 3  # nobody stays down forever unless pinned out
            if f.name in self.lucky:
                tries = 1  # /play dice free: she gets up at the first try
            props = self.scene_props()
            grab = self.rng.choice(props)
            # (the dice are rolled as before; but a fighter lying at the foot of something uses THAT to get up)
            # (and nobody lying out in the open has a prop to hand: a prop only where she lies at the foot of one)
            grab = (getattr(self, "lying_at", None) or {}).get(name) or None
            natural = next((i + 1 for i, c in enumerate(cuts) if score >= c), None)
            ev = {"type": "get_up", "fighter": name, "plan": plan, "grab": grab, "ground": self.ground_under(name),
                  "beats_down": max(beats, int(f.learned.get("down_for", beats))),
                  "score": round(score, 2), "cuts": list(cuts), "forced": natural is None and tries is not None,
                  "tries": tries or len(cuts), "stands": tries is not None,
                  "hurting": [p.name for p in worst if p.damage >= 30][:2],
                  # grips that are on her, and grips of her own, as she tries: they stay on whether she rises or not
                  "held": [{"by": h.attacker, "part": h.part, "with": h.with_part}
                           for h in self.holds.values() if h.defender == name],
                  "holding": [{"on": h.defender, "part": h.part, "with": h.with_part}
                              for h in self.holds.values() if h.attacker == name]}
            if tries is not None:
                del self.downed[name]
                f.learned["rose_turn"] = self.turn      # (health.collapse.stand_grace counts from here)
                lay = self.facing.pop(name, None)
                ev["rise"] = self.vary("getup_rise", ("roll",) if lay == "face-down" else ())  # (already on her front)
                ev["fails"] = [self.vary("getup_fail") for _ in range(max(0, tries - 1))]
            else:
                ev["fails"] = [self.vary("getup_fail") for _ in range(3)]
                # she doesn't make it to her feet, but she may get as far as sitting up
                if (self.facing.get(name) != "sitting up" and not ev["held"]
                        and self._chance(float(cfg.get("sit_up_chance", 0.4)), f"{name} getting as far as sitting up",
                                         "she sits up", "she stays lying")):
                    ev["from_facing"] = self.facing.get(name)
                    self.facing[name] = "sitting up"
                    ev["sits"] = True
            self._getup_falls(f, ev, worst, cfg)
            events.append(ev)
        self._fresh_down = set()
        return events

    def landing_parts(self, defender, n=3, avoid=()):
        """Sensible parts for a hard landing when none are named: back, shoulder, hip, head, spread out."""
        d = self.get(defender)
        picked = []
        for region in ("back_up", "shoulder", "hind_up", "back_low", "head", "chest", "belly", "tail", "fore_up", "neck"):
            cands = [p for p in d.parts if body_region(p) == region and p not in picked and p not in avoid]
            if cands:
                picked.append(self.rng.choice(cands))
            if len(picked) >= n:
                break
        return picked or list(d.parts)[:n]

    MANHANDLES = ("throw", "slam", "drag")

    def underside_parts(self, defender, n=3):
        """The parts scraping the ground under a fighter who is dragged where she lies: her back if she's face-up,
        her chest and belly if she's face-down, one flank if she's on her side."""
        d = self.get(defender)
        fc = self.facing_of(d.name)
        if fc == "face-down":
            regions = ("chest", "belly", "head", "fore_low", "hind_low", "shoulder")
        elif fc == "on her side":
            side = self.rng.choice(("left", "right"))
            cands = [p for p in d.parts if _side(p) == side and body_region(p) in ("shoulder", "chest", "belly", "hind_up")]
            self.rng.shuffle(cands)
            if len(cands) >= 2:
                return cands[:n]
            regions = ("shoulder", "chest", "hind_up", "belly")
        else:   # face-up, sitting (hauled backwards), or unknown
            regions = ("back_up", "back_low", "hind_up", "tail", "shoulder", "head")
        picked = []
        for region in regions:
            cands = [p for p in d.parts if body_region(p) == region and p not in picked]
            if cands:
                picked.append(self.rng.choice(cands))
            if len(picked) >= n:
                break
        return picked or self.landing_parts(d.name, n)

    def manhandle(self, attacker, defender, kind, impacts=(), flavor="", enforce=False, tumble=None):
        """One fighter moves another by force, and the arena does the damage:
          throw - she is grabbed (hauled up first if she was lying down) and hurled: she crashes into each surface;
          slam  - she is lifted and driven down at the attacker's feet;
          drag  - she is on the ground and is hauled across it, over or into whatever is named, staying down.
        impacts: (surface, [parts], severity) in order, like a landing. A standing target can slip the grab (the usual
        dodge roll) when the director chooses it; your own commands always land. Not while either fighter is pinned."""
        kind = str(kind or "").lower()
        if kind not in self.MANHANDLES:
            raise ValueError(f"unknown way to move a fighter: '{kind}' (throw, slam, drag)")
        past = {"throw": "thrown", "slam": "slammed", "drag": "dragged"}[kind]
        a, d = self.get_active(attacker), self.get_active(defender)
        if a is d:
            raise ValueError(f"{a.name} can't {kind} herself")
        self._can_act(a, enforce)
        self._no_friendly_fire(a, [d], enforce)
        if self.pinned_by(a.name):
            raise ValueError(f"{a.name} is pinned: she can't {kind} anyone until she is free")
        if a.name in self.downed:
            raise ValueError(f"{a.name} is on the ground: she has to be on her feet to {kind} anyone")
        if enforce and a.name in self.pressed:
            raise ValueError(f"{a.name} is still pressed against the scenery: she can't {kind} anyone this beat")
        if enforce and (self.has(d, "airborne") or self.has(a, "airborne")) and not self.grabbed_by(a.name, d.name):
            raise ValueError(f"{(d if self.has(d, 'airborne') else a).name} is in the air: nobody can {kind} her until "
                             f"she comes down")
        if any(p["defender"] == d.name for p in self.pins.values()):
            raise ValueError(f"{d.name} is pinned: the pin has to end before she can be {past}")
        down = d.name in self.downed
        if kind == "drag" and not down and enforce:
            raise ValueError(f"a drag needs {d.name} ON THE GROUND and she is on her feet: knock her down first, or "
                             f"throw or slam her instead")
        cool = int(self.rules.get("director", {}).get("manhandle_cooldown", 0) or 0)
        last = getattr(self, "_last_manhandle", {}).get(a.name)
        if enforce and last is not None and self.turn - last < cool:
            raise ValueError(f"{a.name} threw, slammed or dragged someone only {self.turn - last} beat(s) ago: choose a "
                             f"different kind of action this beat")
        impacts = [(s, list(p or []), sev) for s, p, sev in (impacts or [])]
        if kind == "drag":
            under = self.underside_parts(d.name, 3) if down else []
            # (since build 277) dragged at the water's edge: across the wet sand there, not the rough ground the
            # treeline has ("Seraphina is in the shallows" while Ripples is dragged over the root-knotted ground)
            wet = self.in_water(a.name) or self.in_water(d.name) or re.search(
                r"\b(?:beach|sand|shore|waterline|shallows)\b", " ".join([self._where(a.name), self._where(d.name),
                                                                    str((getattr(self, "lying_on", None) or {}).get(d.name) or "")]), re.I)
            impacts = impacts or [(self.scene_word("slick" if wet else "rough"), [], "light")]
            # the first stretch of ground scrapes whatever she is lying on, unless parts were named
            if under and not impacts[0][1]:
                impacts[0] = (impacts[0][0], under, impacts[0][2])
        elif not impacts:
            impacts = [(self.scene_word("ground"), [], "solid" if kind == "throw" else "heavy")]
        before = a.energy
        self._spend(a, float(self._cfg("energy").get("costs", {}).get(kind, 12 if kind != "drag" else 8)), enforce,
                    f"a {kind}")
        dodge = self.dodge_roll(a, d, "targeted") if enforce else None
        if enforce and down and not dodge:
            rc = self.resist_chance(d)   # on the ground she can't dodge, but she can fight the grab off
            if rc > 0 and self._chance(rc, f"{d.name} fighting off {poss_word(a.name)} grab ({kind})",
                                       "she fights it off", "she is taken"):
                dodge = {"dodged": True, "dodge_chance": rc, "counter_hits": [], "resisted": True,
                         "manner": self.vary("hold_strain")}
        self._attacked(a.name, [d.name], landed=not dodge)
        self._last_manhandle = {**getattr(self, "_last_manhandle", {}), a.name: self.turn}
        route = " → ".join(short_phrase(s, default="the ground") for s, _, _ in impacts)
        label = {"throw": f"thrown by {a.name}: {route}", "slam": f"lifted and slammed down by {a.name}: {route}",
                 "drag": f"dragged by {a.name}: {route}"}[kind]
        if dodge:
            return {"type": "instant", "attacker": a.name, "defender": d.name, "defenders": [d.name],
                    "flavor": flavor or f"a grab to {kind} her", "manhandle": kind,
                    "energy": [round(before), round(a.energy)], "hit_count": 0, "hits": [], "tags": [], **dodge}
        pre = []
        if kind == "drag" and not down:   # your command on a standing fighter: she is pulled off her feet first
            self.knock_down(d.name, why=f"{d.name} was pulled off her feet")
            pre, self._knock_on = self._knock_on, []
        res = self.land(d.name, impacts, credited=a.name, how=label, thrown=kind != "drag", in_place=kind == "drag",
                        can_recover=enforce and kind == "throw", slam=kind == "slam",
                        tumble=(tumble if tumble is not None else None if enforce else False) if kind == "throw" else False)
        if kind == "drag":
            self._count("dragged", d.name)
            if d.name in self.downed:
                self._fresh_down.add(d.name)   # hauled across the ground: she can't be getting up this same beat
        res.update({"manhandle": kind, "launch": {"throw": "thrown", "slam": "slammed", "drag": "dragged"}[kind],
                    "energy": [round(before), round(a.energy)], "told": flavor, "was_down": down,
                    "knock_on": pre + list(res.get("knock_on") or [])})
        self.involved.update({a.name, d.name})
        return res

    UPRIGHT_SURFACE = re.compile(r"wall|boulder|stalagmite|pillar|column|tree|trunk|rock face|cliff|fence|post|statue", re.I)

    def land(self, defender, impacts, credited="", how="", thrown=True, in_place=False, can_recover=False, slam=False,
             tumble=False, force=1.0):
        """Environmental damage after a launch or throw: each impact is (surface, [parts], severity).
        Every part listed on every surface takes a hit; the fighter ends up on the ground. thrown=False is a plain
        knockdown (she drops where she stands). in_place: she was already lying there and is driven into it: the
        impacts land, but she doesn't fall again and lies the way she did."""
        d = self.get_active(defender)
        self.note_wear(d, "grit and dust ground into her coat from the ground")
        if self.pinned_by(d.name) and not thrown:
            in_place = True  # held down: she can't be knocked any further down
        from_ground = d.name in self.downed and not in_place  # hurled from where she lay, not off her feet
        counted = None if in_place else "slammed" if slam else "thrown" if thrown else None
        table = self.rules["severity"].get("environment") or self.rules["severity"]["instant"]
        plan, used = [], set()
        for surface, parts, sev in impacts:  # validate everything before changing anything
            sev = str(sev or "solid").lower()
            sev = {"firm": "solid", "crushing": "heavy", "light": "light"}.get(sev, sev)
            if sev not in table:
                sev = "solid"
            names = []
            for p in parts or []:
                try:
                    n = d.part(p).name
                except ValueError:
                    continue  # a part this species doesn't have: skip it rather than reject the whole beat
                if n not in names:
                    names.append(n)
            names = names or self.landing_parts(d.name, 3, avoid=used)
            used.update(names)
            hz = self.hazard_for(surface)
            if hz and hz.get("cushion") and "light" in table:
                sev = "light"   # deep water, snow, soft sand: whatever threw her, the landing itself is soft
            plan.append((short_phrase(surface, default=self.scene_word("ground")), names, sev))
        # a TUMBLE: hurled hard enough, she doesn't stop where she lands. She goes on across the ground, end over end,
        # and may fetch up against something that stands in the way. tumble: None = roll it (down.tumble_chance),
        # True = she tumbles, False = she lands and stays
        tumbled = None
        dcfg0 = self.rules.get("down", {})
        if thrown and not slam and not in_place and plan and tumble is not False and not self.pinned_by(d.name):
            tc = float(dcfg0.get("tumble_chance", 0.3))
            if tumble is True or (tc > 0 and self._chance(tc, f"{d.name} tumbling on after the landing",
                                                          "she tumbles on", "she stops where she lands")):
                ground = self.scene_word("rough") if self.rng.random() < 0.5 else self.scene_word("ground")
                names = self.landing_parts(d.name, self.rng.choice([2, 3, 3]), avoid=used)
                used.update(names)
                plan.append((ground, names, "light"))
                tumbled = {"across": ground, "into": None, "from": len(plan) - 1}
                seen = " ".join(p[0].lower() for p in plan)
                stops = list(dict.fromkeys(self.scene_props() + [h["name"] for h in (self.scene_cfg.get("hazards") or [])
                                                                  if h.get("upright") or h.get("cushion")]))
                props = [p for p in stops if p.lower() not in seen and p.lower().split()[-1] not in seen]
                if props and self._chance(float(dcfg0.get("tumble_into", 0.5)), f"{d.name} fetching up against something",
                                          "she hits something", "she rolls to a stop in the open"):
                    prop = self.rng.choice(props)
                    hz = self.hazard_for(prop)
                    sev = "light" if (hz and hz.get("cushion")) else "solid"
                    names = self.landing_parts(d.name, self.rng.choice([1, 2]), avoid=used)
                    plan.append((short_phrase(prop, default=ground), names, sev))
                    tumbled["into"] = plan[-1][0]
        v = self.rules["severity"]["variance"]
        landings, hits = [], []
        if counted:
            self._count(counted, d.name)
        dev = self._devastating_landing(d, plan) if not in_place else None
        if dev:
            plan = dev.pop("plan")
        for surface, names, sev in plan:
            self._source = f"landing on {surface}"[:60]
            power = max(1, round(table[sev] * self.rng.uniform(1 - v, 1 + v) * (dev["mult"] if dev else 1.0)
                                 * (float(force) if not landings else 1.0)))   # force: a spike drives the first impact
            self._dev_active = dev
            try:
                these = [self._apply_damage(d, n, power) for n in names]
            finally:
                self._dev_active = None
            landings.append({"surface": surface, "severity": sev, "power": power, "parts": names})
            if tumbled and len(landings) > tumbled["from"]:
                landings[-1]["tumble"] = True
            hits += these
        dcfg = self.rules.get("down", {})
        ends, kept_feet = None, False
        last = plan[-1][0] if plan else ""
        awake = not (d.eliminated or self.has(d, "asleep") or self.has(d, "frozen") or self.has(d, "paralyzed"))
        if in_place:
            facing, loose = self.facing_of(d.name), []
        else:
            # how she ends up. Usually flat on the ground; sometimes slumped SITTING against the last upright thing she
            # hit, or sat down hard by a plain knockdown; and a thrown fighter with strength left may ROLL THROUGH the
            # landing and come up on her feet (she still takes every impact).
            why = f"{d.name} was {'slammed down' if slam else 'thrown' if thrown else 'knocked down'}"
            share = max(0.0, min(1.0, self.strength(d) / 100.0))
            rt = float(dcfg.get("roll_through", 0.2)) * share
            # a strong fighter knocked or thrown down often springs straight back up: the stronger, the likelier
            sp = dcfg.get("spring_up") if isinstance(dcfg.get("spring_up"), dict) else {}
            if sp.get("enabled", True):
                lo = float(sp.get("from", 55))
                t = max(0.0, min(1.0, (self.strength(d) - lo) / max(1.0, 100.0 - lo)))
                rt = max(rt, float(sp.get("max", 0.55)) * t)
            if (can_recover and awake and not from_ground and not slam and not self.is_upright(last)
                    and not tumbled and rt > 0 and self._chance(rt, f"{d.name} rolling through the landing", "she comes up on her feet",
                                                "she stays down")):
                kept_feet, ends = True, "rolled to her feet"
                self.pressed.pop(d.name, None)
                d.status.pop("airborne", None)  # she came down to land on her feet
                loose = self._lose_grip(d.name, why, on_her=True)
                facing = None
            else:
                sit = None
                if awake and not slam and self.is_upright(last):
                    if self._chance(float(dcfg.get("slump_sitting", 0.35)), f"{d.name} ending slumped against {last}",
                                    "sitting against it", "lying at its foot"):
                        sit, ends = "sitting up", "slumped sitting against " + last
                elif awake and not thrown and d.name not in self.downed and not self.pinned_by(d.name):
                    if self._chance(float(dcfg.get("sit_down", 0.15)), f"{d.name} sitting down hard",
                                    "dropped onto her haunches", "flat on the ground"):
                        sit, ends = "sitting up", "sat down hard"
                facing = self.knock_down(d.name, facing=sit, parts=[n for _, names, _ in plan for n in names][-4:],
                                         thrown=thrown, why=why)
                loose, self._knock_on = self._knock_on, []
                if facing != "sitting up":
                    ends = None
                if not self.is_upright(last):
                    # what she lies on now (the soft beach, the shallows): a blow driven down into her and her get-up
                    # use it, not the arena's own ground word
                    self.__dict__.setdefault("lying_on", {})[d.name] = short_phrase(last)
        self.involved.add(d.name)
        status = self.hazard_effects(d, [l["surface"] for l in landings])
        if (not self.scene_cfg.get("hazards") and not any(x["status"] == "soaked" for x in status)
                and any(re.search(r"pool|water|channel|shallows|stream|splash", l["surface"], re.I) for l in landings)):
            # an arena of your own (nothing tracked): water named in a landing still soaks
            self.set_status(d, "soaked", self._cfg("status_effects").get("soaked_beats", 3))
            status.append({"fighter": d.name, "status": "soaked", "beats": self._cfg("status_effects").get("soaked_beats", 3)})
        route = " → ".join(l["surface"] for l in landings)
        return {"type": "instant", "environment": True, "attacker": credited or d.name, "defender": d.name,
                "devastating": dev,
                "defenders": [d.name], "flavor": how or f"slams into {route}", "landings": landings,
                "status_applied": status, "facing": facing, "in_place": in_place, "knock_on": loose,
                "from_ground": from_ground, "kept_feet": kept_feet, "ends": ends,
                "tumble": ({"across": tumbled["across"], "into": tumbled["into"],
                            "manner": self.vary("tumble")} if tumbled else None),
                "hit_count": len(hits), "hits": hits, "tags": self._tags(hits)}

    def hold_power(self, attacker, defender, move_name):
        """Pressure per beat for a hold move, after type effectiveness. Returns (power, move_math)."""
        move = self.find_move(attacker, move_name)
        if move is None:
            raise ValueError(f"{attacker} doesn't know '{move_name}'")
        self._use_move(self.get(attacker), move)
        math = self.move_math(attacker, defender, move)
        return math["effective"], math

    def power_for(self, kind, label):
        """Turn a severity word ('heavy', 'crushing', ...) into a whole-number power with slight variance."""
        table = self.rules["severity"][kind]
        if label not in table:
            raise ValueError(f"Unknown {kind} severity '{label}'. Options: {', '.join(table)}")
        v = self.rules["severity"]["variance"]
        return max(1, round(table[label] * self.rng.uniform(1 - v, 1 + v)))

    def ramp_for(self, label):
        table = self.rules["severity"]["hold_ramp"]
        if label not in table:
            raise ValueError(f"Unknown hold ramp '{label}'. Options: {', '.join(table)}")
        return table[label]

    # ---------- actions ----------
    def _attacker_mult(self, a):
        m = 1.0
        for _, x in self.power_extras(a, a, "Normal"):
            m *= x
        return m

    def instant(self, attacker, defender, part, power, count=1, flavor="", enforce=False):
        """One or more hits on one part. Later hits land on the already-lowered resistance."""
        a, d = self.get_active(attacker), self.get_active(defender)
        self._can_act(a, enforce)
        self._no_friendly_fire(a, [d], enforce)
        self._pinned_reach(a, [d.name], enforce)
        still_against = (self.pressed.get(d.name) or {}).get("surface")
        before = a.energy
        self._spend(a, self.energy_cost(kind="strike"), enforce, "another strike")
        dodge = self.dodge_roll(a, d, "targeted") if enforce else None
        self._source = f"{poss_word(a.name)} {flavor or 'strike'}"[:60]
        power = round(power * self._attacker_mult(a) * self._pin_mult(a, d), 2)
        hits = [] if dodge else [self._apply_damage(d, part, power) for _ in range(count)]
        self._attacked(a.name, [d.name], landed=bool(hits))
        res = {"type": "instant", "attacker": a.name, "defender": d.name, "flavor": flavor, "defenders": [d.name],
               "energy": [round(before), round(a.energy)],
               "hit_count": len(hits), "hits": hits, "tags": self._tags(hits) if hits else []}
        if dodge:
            res.update(dodge)
        elif hits:
            res["status_applied"] = self._restrain(a, d)
            if still_against:
                res["target_against"] = still_against
        return res

    def _restrain(self, a, d):
        """Sometimes, when the pinner lands an attack on the fighter she's pinning (a claw in a nerve cluster, a
        trapped paw, a ground-down joint), it also locks her down: harder to escape for a couple of beats."""
        cfg = self.rules.get("pin", {}).get("restrain", {})
        if not cfg.get("enabled", True) or d.name not in self.pinning(a.name):
            return []
        if not self._chance(float(cfg.get("chance", 0.5)), f"{d.name} restrained by the pin technique", "restrained",
                            "no"):
            return []
        beats = int(cfg.get("beats", 2))
        self.set_status(d, "restrained", beats)
        return [{"fighter": d.name, "status": "restrained", "beats": beats}]

    def multi(self, attacker, defender, parts_and_powers, flavor="", enforce=False):
        """One action hitting several parts (thrown down stairs). Each entry is (part, power),
        or (defender, part, power) for an attack that catches more than one fighter."""
        a = self.get_active(attacker)
        plan = []
        for entry in parts_and_powers:  # validate everything before changing anything
            dname, part, power = entry if len(entry) == 3 else (defender, *entry)
            d = self.get_active(dname)
            if d is a:
                raise ValueError(f"{a.name} can't hit themselves")
            plan.append((d, d.part(part).name, power))
        self._can_act(a, enforce)
        self._no_friendly_fire(a, [d for d, _, _ in plan], enforce)
        self._pinned_reach(a, [d.name for d, _, _ in plan], enforce)
        before = a.energy
        self._spend(a, self.energy_cost(kind="strike"), enforce, "another strike")
        mult = self._attacker_mult(a)
        self._source = f"{poss_word(a.name)} {flavor or 'attack'}"[:60]
        dodged = {}
        for d, _, _ in plan:
            if enforce and d.name not in dodged:
                dodged[d.name] = self.dodge_roll(a, d, "spread" if len(plan) > 1 else "targeted")
        hits = [self._apply_damage(d, part, round(power * mult * self._pin_mult(a, d), 2))
                for d, part, power in plan if not dodged.get(d.name)]
        defenders = []
        for d, _, _ in plan:
            if d.name not in defenders:
                defenders.append(d.name)
        self._attacked(a.name, defenders, landed=bool(hits))
        dodge_info = next((x for x in dodged.values() if x), None)
        extra = {}
        if dodge_info:
            extra = dict(dodge_info, dodged=not hits, dodged_by=[n for n, x in dodged.items() if x])
        return {**extra, "energy": [round(before), round(a.energy)],
                "type": "instant", "attacker": a.name, "defender": ", ".join(defenders),
                "defenders": defenders, "flavor": flavor,
                "hit_count": len(hits), "hits": hits, "tags": self._tags(hits)}

    def start_hold(self, attacker, defender, part, power, change_per_turn=0.0, flavor="", with_part="",
                   keep_with=False):
        a, d = self.get_active(attacker), self.get_active(defender)
        pname = d.part(part).name
        for h in self.holds.values():  # already pressing that spot: strengthen it, don't stack a second hold
            if (h.attacker, h.defender, h.part) == (a.name, d.name, pname):
                as_is = keep_with and (self.rules.get("holds", {}).get("keep_as_is") or {}).get("enabled", True)
                if not as_is:
                    h.power = max(h.power, power)
                # (holds.keep_as_is: a grip the director only keeps on presses as it was: its own tightening does
                # the climbing, and a grip she has worked looser stays looser)
                h.change_per_turn = change_per_turn
                asked = with_part if (with_part and h.with_part and with_part.lower() != h.with_part.lower()) else ""
                # keep_with (the director's beats): jaws that are already on her neck stay jaws; they don't turn
                # into a horn because the new pin was worded that way. Your own commands may change it.
                h.with_part = (h.with_part or with_part) if keep_with else (with_part or h.with_part)
                sl = self.rules.get("holds", {}).get("second_limb") or {}
                if keep_with and asked and self.JAWS_GRIP.search(asked) and h.sub and self.submission_match() \
                        and self.hold_mix() and self.rng.random() >= float(self.hold_mix().get("jaws", 0.5)):
                    # (hold_mix.jaws, since build 266) her jaws clamped onto a submission she already has on: that
                    # much rarer too; the grip goes on as it was (and its words, written for the bite, go)
                    asked, flavor = "", ""
                if keep_with and asked and sl.get("enabled", True) and self._limb_kind(asked) and \
                        self._limb_kind(asked) not in self._limb_kinds(h.with_part):
                    # a second limb on the same spot (her tails bound round the knee her jaws already hold): both stay
                    # on it, and the new one adds a share of its own pressure (holds.second_limb)
                    h.with_part = f"{h.with_part} and {re.sub(r'^(?:with )?(?:her|their|its) ', '', asked)}"
                    h.power = (h.power if as_is else max(h.power, power)) + float(sl.get("add", 0.5)) * min(h.power, power)
                    asked = ""
                return {"type": "hold_start", "hold_id": h.id, "attacker": a.name, "defender": d.name,
                        "part": pname, "power": h.power, "change_per_beat": h.change_per_turn,
                        "flavor": flavor, "with": h.with_part, "existing": True,
                        "asked_with": asked if keep_with else "", "choke_kind": self._hold_choke_kind(h)}
        if self.traits_cfg():
            # (since build 280) traits.hold: how hard her grips bite; works_the_hold: hers build faster; a paw grip
            # of one whose paws aren't made for it is weaker
            power = round(power * self.trait(a, "hold"), 2)
            q = self.quirk(a, "weak_paw_grip")
            if q and re.search(r"\bpaws?\b|forepaws?|claws?", str(with_part or ""), re.I):
                power = round(power * float(q.get("power_mult", 0.75)), 2)
            q = self.quirk(a, "works_the_hold")
            if q:
                change_per_turn = change_per_turn + float(q.get("ramp_add", 1.0))
            if self.quirk(d, "out_of_depth"):
                d.learned["held_count"] = int(d.learned.get("held_count", 0)) + 1
                if d.learned["held_count"] <= 2:
                    self.quirk_moment(d, "out_of_depth", f"{d.name} has hardly ever been held like this: she doesn't "
                                                         f"know the way out of it yet, and it frightens and angers her")
                elif d.learned["held_count"] in (4, 5):
                    self.quirk_moment(d, "out_of_depth", f"{d.name} is learning holds the hard way: this time she "
                                                         f"knows a little better how to fight it")
        h = Hold(self.next_hold_id, a.name, d.name, pname, power, change_per_turn, flavor, 0, with_part)
        self.holds[h.id] = h
        self.next_hold_id += 1
        return {"type": "hold_start", "hold_id": h.id, "attacker": a.name, "defender": d.name,
                "part": pname, "power": power, "change_per_beat": change_per_turn, "flavor": flavor,
                "with": with_part, "existing": False, "choke_kind": self._hold_choke_kind(h)}

    def _hold_choke_kind(self, h):
        """For a grip on the neck or throat, which kind of choke it is (choke_kind: "blood", "air" or "both"), so the
        story can tell a squeeze on the sides of the neck from a windpipe crushed shut; "" for any other grip."""
        return self.choke_kind(h.attacker, h.with_part, h.coil) if body_region(h.part) == "neck" else ""

    @classmethod
    def _limb_kinds(cls, with_part):
        """Every kind a grip presses with ("jaws and twin tails" is both jaws and tails), so a second limb already
        on the spot is never added again each time the grip is kept."""
        return {cls._limb_kind(w) for w in re.split(r"\band\b|,", str(with_part or ""))} - {""}

    @staticmethod
    def _limb_kind(with_part):
        """What a grip presses with, as a kind (jaws, tails, paws, legs, wings, body), or "" when it doesn't say."""
        w = str(with_part or "").lower()
        for kind, rx in (("jaws", r"\b(?:jaws?|teeth|fangs?|bite|mouth)\b"), ("tails", r"\btails?\b|\bcoils?\b"),
                         ("paws", r"\b(?:paws?|hands?|claws?|arms?|forelegs?)\b"), ("legs", r"\b(?:legs?|knees?|thighs?|feet|foot)\b"),
                         ("wings", r"\bwings?\b"), ("body", r"\b(?:body|weight|chest)\b")):
            if re.search(rx, w):
                return kind
        return ""

    def grab_between(self, x, y):
        """The grab that links these two (either one holding the other), while both are still on their feet; or None."""
        x, y = self.get(x).name, self.get(y).name
        if x in self.downed or y in self.downed:
            return None
        return next((h for h in self.holds.values() if h.grab and {h.attacker, h.defender} == {x, y}), None)

    def grabbed_by(self, holder, held):
        """True while `holder` has a grab on `held` and both are on their feet."""
        h = self.grab_between(holder, held)
        return bool(h) and h.attacker == self.get(holder).name

    def next_target(self, defender, current, why="the next blow", stay=None, near_only=False):
        """Where the next blow of a pummel or the next link of a chain lands when nobody has said: the dice decide
        between the same spot again and a new one (moves.repeat_target: stay_chance, near_share). A new spot is
        usually right next to the last (near_share), otherwise anywhere she can be reached."""
        cfg = self.rules.get("moves", {}).get("repeat_target", {}) or {}
        d = self.get(defender)
        stay = float(cfg.get("stay_chance", 0.5)) if stay is None else float(stay)
        if stay >= 1 or self._chance(stay, f"{why} landing on {current} again", "same spot", "somewhere new"):
            return current
        same, near = neighbor_parts(list(d.parts), current)
        pool = [p for p in same + near if p != current]
        if not pool or (not near_only and self.rng.random() >= float(cfg.get("near_share", 0.7))):
            pool = [p for p in d.parts if p != current]     # (near_only: always the spot beside it, when there is one)
        if d.name in self.downed or self.pinned_by(d.name):
            fitted, _ = self.fit_to_facing(d.name, pool)      # only what is turned toward her attacker
            pool = [p for p in dict.fromkeys(fitted) if p != current] or pool
        return self.rng.choice(pool) if pool else current

    @staticmethod
    def is_ranged(move):
        """A move that crosses the distance: a beam, a blast, a pulse, a stream (spread or whole-body, or marked
        ranged). Not a charge, a hold or a status move."""
        if not move or move.get("charge") or move.get("target") in ("hold", "status", "self"):
            return False
        if "ranged" in move:   # moves.json can say so outright ("ranged": false for a close flurry like Close Combat)
            return bool(move["ranged"])
        if move.get("target") in ("spread", "whole_body"):
            return True
        # a single-target move that is thrown, shot or fired across the gap (Ice Shard, "a fast-flung chunk of ice"),
        # never one delivered by a fist, a fang or a body ("Bullet Punch")
        words = f"{move.get('name', '')} {move.get('about', '')}".lower()
        return bool(re.search(r"\b(?:flung|fling|shards?|shot|shoots?|bullets?|spits?|spat|hurl\w*|thrown|needles?|"
                              r"missiles?|darts?|gun|beams?|rays?|bolts?|blasts?|pulse|spheres?|orbs?|spray|jets? of)\b", words)
                    and not re.search(r"\b(?:punch|fist|fang|bite|claw|kick|tackle|slam|strike|headbutt|tail|grabs?|grips?|seiz\w*|swings?)\b",
                                      words))

    def _clash(self, a, d, move, math):
        """A ranged attack met head-on by one of the defender's own (moves.clash): the two meet in the air between
        them. Who wins is their power with some luck in it: the attack pushes THROUGH (landing weaker), the two
        CANCEL out (nothing lands), or the defender's TURNS IT BACK onto the attacker (weaker than it was).
        Returns the record, or None if she doesn't answer it."""
        cfg = self.rules.get("moves", {}).get("clash") or {}
        if not cfg.get("enabled", True) or not self.is_ranged(move) or math.get("type_mult", 1) == 0:
            return None
        if (d.name in self.downed or self.pinned_by(d.name) or self.pinning(d.name) or self.grab_between(a.name, d.name)
                or any(self.has(d, st) for st in ("paralyzed", "asleep", "frozen", "flinched", "constricted"))
                or d.name in self.pressed
                or any({h.attacker, h.defender} == {a.name, d.name} for h in self.holds.values())):
            return None   # (locked together in a hold or a submission: no room to meet it head-on)
        options = []
        for m in d.moves:
            if not self.is_ranged(m) or (d.move_uses.get(m["name"], 1) <= 0):
                continue
            if d.energy < self.energy_cost(m):
                continue
            options.append((self.move_math(d.name, a.name, m)["effective"], m))
        if not options:
            return None
        if not self._chance(float(cfg.get("chance", 0.15)) * self.dominated(d.name) * self.trait(d, "speed"), f"{d.name} meeting {poss_word(a.name)} {move['name']} "
                            f"with an attack of her own", "CLASH", "no"):
            return None
        # how much force a move puts out, all told: a whole-body discharge spreads its power over every part, so
        # it is weighed by how much of her it covers, not by one part's share
        weigh = lambda eff, m, who: eff * ({"whole_body": len(who.parts), "spread": 3}.get(m.get("target"), 1)) ** 0.5
        options = [(weigh(e, m, a), e, m) for e, m in options]
        _, eff_d, dm = max(options, key=lambda x: x[0])
        d.energy = max(0.0, d.energy - self.energy_cost(dm))
        self._use_move(d, dm)
        luck = float(cfg.get("luck", 0.25))
        pa = weigh(math["effective"], move, d) * (1 + self.rng.uniform(-luck, luck))
        pd = weigh(eff_d, dm, a) * (1 + self.rng.uniform(-luck, luck))
        win = float(cfg.get("win_ratio", 1.3))
        lo, hi = float(cfg.get("min_share", 0.25)), float(cfg.get("max_share", 0.8))
        out = {"move": dm["name"], "move_type": dm["type"], "about": dm.get("about", ""), "power": round(eff_d, 2),
               "attack_power": round(math["effective"], 2), "rolled": [round(pa, 1), round(pd, 1)], "hits_on_attacker": []}
        if pa >= pd * win:
            out.update(outcome="through", share=round(max(lo, min(hi, 1 - pd / pa)), 2))
        elif pd >= pa * win:
            share = round(max(lo, min(hi, 1 - pa / pd)), 2)
            out.update(outcome="back", share=share)
            reach = [x for x in a.parts if body_region(x) in ("head", "neck", "chest", "shoulder")] or list(a.parts)
            self.rng.shuffle(reach)
            mine, self._source = self._source, f"{poss_word(d.name)} {dm['name']} (turned back)"
            out["hits_on_attacker"] = [self._apply_damage(a, x, round(eff_d * share, 2)) for x in reach[:3]]
            self._source = mine
            self.involved.add(d.name)
        else:
            out.update(outcome="cancel", share=0.0)
        self.rolls.append({"what": f"the clash: {poss_word(a.name)} {move['name']} {round(pa)} against {poss_word(d.name)} "
                                   f"{dm['name']} {round(pd)}", "chance": 0, "roll": 0, "ok": True, "plain": True,
                           "result": {"through": "it pushes through", "cancel": "they cancel out",
                                      "back": "it is turned back"}[out["outcome"]]})
        return out

    def _into_mouth(self, a, d, move, hits, held):
        """A stream of water that finds her face (or her, lying face-up) may go into her open mouth and up her nose:
        she chokes on it and comes up SPUTTERING (moves.into_mouth). Likelier when it is held on her, when she is on
        her back or pinned face-up, or held at point-blank. Never drowning: she coughs it up. Returns the status record, or None."""
        cfg = self.rules.get("moves", {}).get("into_mouth") or {}
        if not cfg.get("enabled", True) or move.get("type") != "Water" or move.get("charge") or not hits or d.eliminated:
            return None
        face = any(re.search(r"muzzle|jaw|throat|nose|head|cheek|neck", str(h.get("part", "")).lower()) for h in hits)
        up = self.facing.get(d.name) == "face-up" and (d.name in self.downed or self.pinned_by(d.name))
        close = bool(self.grab_between(a.name, d.name))
        if not (face or up):
            return None        # a stream into her belly doesn't find her mouth, however close
        p = float(cfg.get("chance", 0.3)) * (float(cfg.get("held_mult", 1.8)) if held else 1.0) \
            * (float(cfg.get("face_up_mult", 1.5)) if up else 1.0) * (float(cfg.get("point_blank_mult", 1.4)) if close else 1.0)
        if not self._chance(min(0.9, p), f"{poss_word(a.name)} {move['name']} going into {poss_word(d.name)} mouth",
                            "into her mouth", "no"):
            return None
        beats = int(cfg.get("beats", 2))
        self.set_status(d, "sputtering", beats)
        return [{"fighter": d.name, "status": "sputtering", "beats": beats, "knock_on": []}]

    COIL_MOVES = ("wrap", "bind", "constrict", "tail bind", "squeeze", "coil")

    def is_coil(self, move, with_part="", flavor=""):
        """A hold made by wrapping round her (Wrap, Bind, Constrict, Tail Bind, or tails, coils or a body wound round
        her) rather than by pressing on her."""
        name = str((move or {}).get("name", "") if isinstance(move, dict) else move or "").lower()
        if any(w in name for w in self.COIL_MOVES):
            return True
        # (labels get cut short: "her twin tails, wound round her" can arrive as "her twin tails, wound")
        return bool(re.search(r"\bcoil|\bwrap|\bwound\b|\blooped\b|tails? (?:round|around|wrapped)",
                              f"{with_part} {flavor}".lower()))

    @staticmethod
    def _wraps_with(with_part, flavor):
        """(since build 275) a one-grip hold whose words wrap the very limb it grips with ("wraps her twin tails
        round the tail", with "her twin tails"): a coil, though the grip's own words don't say how it holds."""
        m = re.search(r"(\w+)\W*$", str(with_part or "").split(",")[0])
        if not m or not flavor or m.group(1).lower() in ("her", "it", "them"):
            return False
        k = re.escape(m.group(1).lower())
        f = str(flavor).lower()
        return bool(re.search(rf"\b{k}\b\W+(?:\w+\W+){{0,2}}?(?:round|around|wound|wrapped|coiled|looped)\b", f)
                    or re.search(rf"\b(?:wrap|coil|wind|wound|loop)\w*\s+(?:\w+\s+){{0,2}}?{k}\b", f))

    # ---------- tactics: setups and payoffs (a plan the director can follow and the narrator can show) ----------
    def _usable_moves(self, f, mtype=None, damaging=True):
        out = []
        for m in f.moves:
            if f.move_uses.get(m["name"], 1) <= 0 or m.get("target") == "hold":
                continue
            if damaging and (float(m.get("power", 0)) <= 0 or m.get("target") in ("status", "self")):
                continue
            if mtype and m.get("type") != mtype:
                continue
            out.append(m)
        return out

    def _knows_move(self, f, name):
        return next((m for m in f.moves if m["name"].lower() == name.lower() and f.move_uses.get(m["name"], 1) > 0), None)

    def _wet_hazards(self):
        return [h.get("name") for h in ((getattr(self, "scene_cfg", None) or {}).get("hazards") or [])
                if any((e or {}).get("status") == "soaked" for e in (h.get("effects") or []))]

    def tactic_ideas(self):
        """Plans a fighter could make right now, from the state of the fight: [{kind, who, on, step: "setup" or
        "read", text}]. A setup has a payoff that the engine then watches for (tactics.setups)."""
        out = []
        cfg = self.rules.get("tactics") or {}
        if not cfg.get("enabled", True):
            return out
        act = self.active()
        weather = (getattr(self, "weather", None) or {}).get("kind")
        for who in act:
            if who.name in self.downed or self.pinned_by(who.name) or any(self.has(who, s) for s in ("asleep", "frozen")):
                continue
            for on in act:
                if on is who or (who.team and on.team == who.team):
                    continue
                volt = self._usable_moves(who, "Electric")
                wet = self._wet_hazards()
                if volt and wet and not self.has(on, "soaked") and on.name in self.downed and not self.pinned_by(on.name):
                    out.append({"kind": "drag_wet", "who": who.name, "on": on.name, "step": "setup",
                                "text": f"{on.name} is down and {wet[0]} is right there: {who.name} drags her into it to "
                                        f"soak her (action 'drag', landing on {wet[0]}), meaning to use {volt[0]['name']} "
                                        f"next: lightning goes through a soaked body far worse"})
                rain = self._knows_move(who, "Rain Dance")
                if rain and weather != "rain" and self._usable_moves(who, "Water"):
                    out.append({"kind": "rain_water", "who": who.name, "on": on.name, "step": "setup",
                                "text": f"{who.name} calls the rain (Rain Dance) so her water hits harder from the next "
                                        f"beat on, and then uses it"})
                sun = self._knows_move(who, "Sunny Day")
                if sun and weather != "sun" and self._usable_moves(who, "Fire"):
                    out.append({"kind": "sun_fire", "who": who.name, "on": on.name, "step": "setup",
                                "text": f"{who.name} calls the sun (Sunny Day) so her fire hits harder, and then uses it"})
                if self.has(on, "mirroring") and self._usable_moves(who):
                    out.append({"kind": "read_mirror", "who": who.name, "on": on.name, "step": "read",
                                "text": f"{on.name} has a Mirror Coat on: a blast or beam would come straight back at "
                                        f"{who.name}. She reads it and uses a close blow (claws, teeth, a tail, a ram) "
                                        f"or waits it out"})
                if self.has(on, "protecting"):
                    out.append({"kind": "read_protect", "who": who.name, "on": on.name, "step": "read",
                                "text": f"{on.name} is behind a Protect barrier: the next attack stops against it. "
                                        f"{who.name} reads it: she feints, or waits it out (a breather), and strikes "
                                        f"when it drops"})
                if self.has(on, "countering"):
                    out.append({"kind": "read_counter", "who": who.name, "on": on.name, "step": "read",
                                "text": f"{on.name} is set to Counter: a close blow would come back harder. {who.name} "
                                        f"reads it and attacks from range (a blast, a beam, a spray) or waits"})
        return out

    def tactic_payoffs(self):
        """Setups still waiting for their payoff (tactics.setups), with what the payoff is."""
        return [s for s in (self.__dict__.get("setups") or []) if not s.get("paid") and self.turn <= s["until"]]

    def tactics_before(self):
        """Remember how things stand before the beat's actions (so track_tactics can see what an action changed)."""
        self._tac_before = {"soaked": {f.name for f in self.active() if self.has(f, "soaked")},
                            "weather": (getattr(self, "weather", None) or {}).get("kind")}

    def _new_setup(self, kind, who, on, setup, payoff, beats=None):
        cfg = self.rules.get("tactics") or {}
        s = {"kind": kind, "who": who, "on": on, "made": self.turn, "setup": setup, "payoff": payoff,
             "until": self.turn + int(beats or cfg.get("payoff_beats", 3))}
        lst = self.__dict__.setdefault("setups", [])
        lst[:] = [x for x in lst if not (x["kind"] == kind and x["who"] == who and x["on"] == on and not x.get("paid"))]
        lst.append(s)
        del lst[:-12]
        return s

    def track_tactics(self, results):
        """After the beat's actions: which setups were made (a fighter soaked where her opponent has lightning, the
        rain or the sun called by a fighter whose moves it powers up) and which earlier setups were paid off (the
        lightning into the soaked body, the water in the rain, the fire in the sun; a read of a Mirror Coat, a
        Protect or a Counter). Returns notes for the screen and the narrator: [{stage, who, on, text, ...}]."""
        cfg = self.rules.get("tactics") or {}
        if not cfg.get("enabled", True):
            return []
        before = getattr(self, "_tac_before", None) or {"soaked": set(), "weather": None}
        notes = []
        acts = [r for r in results or [] if isinstance(r, dict)]
        # payoffs first (a setup made this beat can't be paid in the same beat)
        for s in self.tactic_payoffs():
            for r in acts:
                if r.get("type") != "instant" or r.get("attacker") != s["who"] or not r.get("hits"):
                    continue
                if s["on"] not in ([r.get("defender")] + list(r.get("defenders") or [])):
                    continue
                mt = (r.get("move") or {}).get("type")
                if {"wet_shock": "Electric", "rain_water": "Water", "sun_fire": "Fire"}.get(s["kind"]) == mt:
                    s["paid"] = self.turn
                    notes.append({"stage": "payoff", "who": s["who"], "on": s["on"], "kind": s["kind"],
                                  "ago": self.turn - s["made"], "setup": s["setup"], "text": s["payoff"]})
                    break
        # reads: the attacker saw the trap and went round it
        for r in acts:
            if r.get("type") != "instant" or not r.get("attacker") or not r.get("defender"):
                continue
            mv = r.get("move") or {}
            on = self.fighters.get(str(r["defender"]).lower())
            if on is None:
                continue
            was = (getattr(self, "_tac_status", None) or {}).get(on.name, set())
            ranged = self.is_ranged(mv) if mv else False
            if "mirroring" in was and mv and not ranged and mv.get("target") not in ("self", "status"):
                notes.append({"stage": "read", "who": r["attacker"], "on": on.name, "kind": "read_mirror",
                              "text": f"saw the Mirror Coat and came in close instead of throwing anything it could send back"})
            if "countering" in was and mv and ranged:
                notes.append({"stage": "read", "who": r["attacker"], "on": on.name, "kind": "read_counter",
                              "text": "saw the Counter set and struck from range instead of walking into it"})
        # new setups
        for f in self.active():
            foes = [g for g in self.active() if g is not f and not (f.team and g.team == f.team)]
            if self.has(f, "soaked") and f.name not in before["soaked"]:
                for g in foes:
                    volt = self._usable_moves(g, "Electric")
                    if volt:
                        # on purpose only if it was HER action that soaked her (a water blow, a throw into the
                        # water), not just any action of hers in a beat where the other got wet some other way
                        by = next((r.get("attacker") for r in acts if r.get("attacker") == g.name and any(
                            x.get("fighter") == f.name and x.get("status") == "soaked"
                            for x in (r.get("status_applied") or []))), None)
                        setup = (f"{g.name} soaked {f.name} on purpose" if by else f"{f.name} got soaked through")
                        notes.append({"stage": "setup", "who": g.name, "on": f.name, "kind": "wet_shock",
                                      "text": f"{setup}: {g.name} has lightning ({volt[0]['name']}), and it goes through "
                                              f"a soaked body far worse", "planned": bool(by)})
                        self._new_setup("wet_shock", g.name, f.name, setup,
                                        f"{volt[0]['name']} into {f.name} while she is still soaked",
                                        beats=max(1, min(int(cfg.get("payoff_beats", 3)), f.status.get("soaked", 3))))
        wk = (getattr(self, "weather", None) or {}).get("kind")
        by = (getattr(self, "weather", None) or {}).get("by")
        if wk and wk != before["weather"] and by:
            f = self.fighters.get(str(by).lower())
            kind, mtype = {"rain": ("rain_water", "Water"), "sun": ("sun_fire", "Fire")}.get(wk, (None, None))
            if f is not None and kind and self._usable_moves(f, mtype):
                foe = next((g.name for g in self.active() if g is not f), "")
                notes.append({"stage": "setup", "who": f.name, "on": foe, "kind": kind, "planned": True,
                              "text": f"{f.name} called the {wk} so her {mtype.lower()} would hit harder"})
                self._new_setup(kind, f.name, foe, f"{f.name} called the {wk}",
                                f"{self._usable_moves(f, mtype)[0]['name']} on {foe} while the {wk} lasts")
        self._tac_status = {f.name: {s for s in ("mirroring", "countering", "protecting") if self.has(f, s)}
                            for f in self.active()}
        return notes

    # ---------- submission holds: very rare, a hold that WRENCHES (damage), not a pin ----------
    # each: which way she must lie, who can do it, the contacts (target part picker, role, what it is done with, by
    # the attacker's body plan), what the attacker still has free to use on her, and what it does to the body
    SUBMISSIONS = {
        # upright holds (since build 245): put on a fighter still on her feet or sitting up; each beat they may bear
        # her down to the ground while the grip stays on (submissions.upright)
        "full nelson": {
            "facing": ("standing", "sitting up"), "by": ("biped",),
            "look": {"biped": "behind her, both arms hooked up under hers and both paws locked behind her neck, "
                              "forcing her head down"},
            "contacts": [("neck", "main", {"biped": "both paws, locked behind her neck, forcing it down"}),
                         ("shoulder", "second", {"biped": "her arms, hooked up under them, levering them up"})],
            "free": {"biped": "her legs (a knee into the back of hers) and her tails"},
            "strain": "her neck forced down toward her chest and both shoulders levered up and back"},
        "standing sleeper": {
            "facing": ("standing", "sitting up"), "by": ("biped",),
            "look": {"biped": "behind her, one forearm across her throat and the other paw pressing her head forward "
                              "into it, chest to her back"},
            "contacts": [("neck", "main", {"biped": "her forearm across the throat, the other paw pressing the head"}),
                         ("back_up", "second", {"biped": "her chest, pressed hard into her back"})],
            "free": {"biped": "her legs and her tails"},
            "strain": "her throat squeezed shut against the forearm, her back arched against the holder"},
        "bear hug": {
            "facing": ("standing", "sitting up"), "by": ("biped",),
            "look": {"biped": "chest to chest, both arms locked round her middle and squeezing, lifting her onto her "
                              "toes"},
            "contacts": [("chest|belly", "main", {"biped": "both arms, locked round her ribs, crushing in"}),
                         ("back_low|back_up", "second", {"biped": "her locked paws, digging into her spine"})],
            "free": {"biped": "her head (it is right there) and her tails"},
            "strain": "her ribs crushed in, her breath squeezed out of her, her spine bent back"},
        "hammerlock": {
            "facing": ("standing", "sitting up"), "by": ("biped",), "needs": "arm",
            "look": {"biped": "behind her, one of her arms wrenched up between her shoulder blades, the other paw on "
                              "her shoulder"},
            "contacts": [("arm", "main", {"biped": "one paw, wrenching it up behind her back"}),
                         ("shoulder", "second", {"biped": "her other paw, bearing down on the shoulder"})],
            "free": {"biped": "her legs and her tails"},
            "strain": "her arm twisted up her back and the shoulder close to giving"},
        "side headlock": {
            "facing": ("standing", "sitting up"), "by": ("biped",),
            "look": {"biped": "at her side, an arm wrapped round her head and clamped tight, bending her over at the "
                              "waist"},
            "contacts": [("head:head|jaw|muzzle", "main", {"biped": "her arm, wrapped round the head, wrenching"}),
                         ("neck", "second", {"biped": "the crook of her elbow, squeezing"})],
            "free": {"biped": "her other paw (a punch to the face from point-blank) and her tails"},
            "strain": "her head crushed in the crook of the arm and her neck twisted down and sideways"},
        "guillotine": {
            "facing": ("standing", "sitting up"), "by": ("biped",),
            "look": {"biped": "in front of her, her head pulled down under one arm, the forearm under her throat and "
                              "both paws locked, hauling up"},
            "contacts": [("neck", "main", {"biped": "her forearm, up under the throat, both paws locked, hauling up"}),
                         ("back_up", "second", {"biped": "her chest, bearing down on the bent back"})],
            "free": {"biped": "her knees (into her chest, her head is right there) and her tails"},
            "strain": "her throat crushed up against the forearm, her back bent double"},
        "cobra clutch": {
            "facing": ("standing", "sitting up"), "by": ("biped",), "needs": "arm",
            "look": {"biped": "behind her, one of her arms dragged across her own throat and held there, the other paw "
                              "forcing her head forward over it"},
            "contacts": [("neck", "main", {"biped": "her own arm, dragged across the throat and held there"}),
                         ("arm", "second", {"biped": "one paw, holding the arm across her throat"})],
            "free": {"biped": "her legs and her tails"},
            "strain": "her own arm choking her and the shoulder wrenched across her body"},
        "abdominal stretch": {
            "facing": ("standing",), "by": ("biped",),
            "look": {"biped": "at her side, a leg hooked round hers and one of her arms hauled back over her head, "
                              "stretching her side open"},
            "contacts": [("belly|chest", "main", {"biped": "her weight, leaning into the stretched side"}),
                         ("arm", "second", {"biped": "one paw, hauling the arm up and back over her head"}),
                         ("hind_up", "second", {"biped": "her leg, hooked round the thigh"})],
            "free": {"biped": "her free paw (it can claw at the stretched ribs) and her tails"},
            "strain": "her whole side stretched open, the ribs and belly pulled taut"},
        "standing armbar": {
            "facing": ("standing", "sitting up"), "by": ("biped",), "needs": "arm",
            "look": {"biped": "at her side, her arm trapped straight under one armpit and wrenched up against the "
                              "elbow, bending her forward"},
            "contacts": [("arm", "main", {"biped": "her armpit and both paws, wrenching the arm straight"}),
                         ("shoulder", "second", {"biped": "her weight, bearing down on it"})],
            "free": {"biped": "her legs and her tails"},
            "strain": "the elbow forced past straight and the shoulder bent down with it"},
        "standing wrist lock": {
            "facing": ("standing", "sitting up"), "by": ("biped",),
            "look": {"biped": "in front of her, her paw bent back on itself at the wrist and twisted, the elbow held "
                              "so it can't turn"},
            "contacts": [("wrist", "main", {"biped": "both paws, bending it back and twisting"}),
                         ("arm", "second", {"biped": "her forearm, braced against the elbow"})],
            "free": {"biped": "her legs, her tails and her mouth"},
            "strain": "the wrist bent and twisted past where it turns, the elbow locked with it"},
        "octopus hold": {
            "facing": ("standing",), "by": ("biped",),
            "look": {"biped": "climbed onto her side, a leg wrapped over her neck, one arm trapped back, her weight "
                              "hanging from her"},
            "contacts": [("neck", "main", {"biped": "her leg, wrapped over it and bearing down"}),
                         ("arm", "second", {"biped": "her arms, trapping it back"}),
                         ("back_low|back_up", "second", {"biped": "her whole weight, hanging from her side"})],
            "free": {"biped": "her tails"},
            "strain": "her neck bent down sideways under the leg, her arm wrenched back, her spine twisted"},
        "rear chinlock": {
            "facing": ("sitting up",), "by": ("biped",),
            "look": {"biped": "kneeling behind her where she sits, both paws locked under her chin, a knee in her back, "
                              "hauling her head back"},
            "contacts": [("head:jaw|muzzle", "main", {"biped": "both paws, locked under the chin, hauling back"}),
                         ("back_up", "second", {"biped": "her knee, driven into it"})],
            "free": {"biped": "her tails"},
            "strain": "her head hauled back and her upper back bent over the knee"},
        "foreleg bite": {
            "facing": ("standing", "sitting up"), "by": ("quadruped",),
            "look": {"quadruped": "in front of her, jaws clamped round one foreleg and wrenching it out from under her"},
            "contacts": [("fore_low|fore_up", "main", {"quadruped": "her jaws, clamped round it, wrenching"}),
                         ("shoulder", "second", {"quadruped": "a forepaw, bearing down on it"})],
            "free": {"quadruped": "her hind legs and her tail"},
            "strain": "the foreleg wrenched and twisted in the jaws, the shoulder borne down with it"},
        "shoulder ride": {
            "facing": ("standing",), "by": ("quadruped",),
            "look": {"quadruped": "reared up onto her back, forepaws locked over her shoulders and jaws at the back of "
                                  "her neck, all her weight bearing down"},
            "contacts": [("shoulder", "main", {"quadruped": "her forepaws, locked over them, bearing down"}),
                         ("neck", "second", {"quadruped": "her jaws, at the back of it"}),
                         ("back_up|back_low", "second", {"quadruped": "her whole weight, riding it"})],
            "free": {"quadruped": "her tail"},
            "strain": "her shoulders and spine crushed down under the weight, her neck held in the jaws"},
        "hind leg hook": {
            "facing": ("standing",), "by": ("quadruped",),
            "look": {"quadruped": "pressed against her side, a hind leg hooked round hers from behind and jaws in her "
                                  "flank, twisting her off her line"},
            "contacts": [("hind_up|hind_low", "main", {"quadruped": "her hind leg, hooked round it, wrenching"}),
                         ("belly|chest", "second", {"quadruped": "her jaws, in the flank"})],
            "free": {"quadruped": "her forepaws and her tail"},
            "strain": "the leg twisted out from under her and her flank torn at"},
        "upright coil": {
            "facing": ("standing", "sitting up"), "by": ("serpent",),
            "look": {"serpent": "coiled up round her where she stands, loop over loop from her legs to her chest, "
                                "squeezing"},
            "contacts": [("chest|belly", "main", {"serpent": "her coils, wrapped round it, squeezing"}),
                         ("hind_up|hind_low", "second", {"serpent": "her lower coils, binding them together"})],
            "free": {"serpent": "her head and her jaws"},
            "strain": "her ribs squeezed in and her legs bound together under her"},
        "talon shoulder clamp": {
            "facing": ("standing", "sitting up"), "by": ("avian",),
            "look": {"avian": "above and behind her, talons clamped into both shoulders, beating her wings to drive "
                              "her down"},
            "contacts": [("shoulder", "main", {"avian": "her talons, clamped in, driving down"}),
                         ("back_up", "second", {"avian": "her weight and the downbeat of her wings"})],
            "free": {"avian": "her beak"},
            "strain": "talons sunk into her shoulders and her back driven down"},
        "flank crush": {
            "facing": ("standing", "sitting up"), "by": ("quadruped",),
            "look": {"quadruped": "against her side, forepaws hooked over her back and all her weight bearing down, "
                                  "jaws clamped on her shoulder"},
            "contacts": [("back_low|back_up", "main", {"quadruped": "her forepaws and her weight, bearing it down"}),
                         ("shoulder", "second", {"quadruped": "her jaws, clamped on it"})],
            "free": {"quadruped": "her hind legs and her tail"},
            "strain": "her back bowed under the weight and her shoulder held in the jaws"},
        "tail haul": {
            "facing": ("standing", "sitting up"), "by": ("quadruped", "biped"),
            "look": {"quadruped": "behind her, jaws clamped on her tail and hauling back, a forepaw braced on her hip",
                     "biped": "behind her, both paws locked round her tail and hauling back, a foot braced on her hip"},
            "contacts": [("tail_part", "main", {"quadruped": "her jaws, hauling it back",
                                                "biped": "both paws, hauling it back"}),
                         ("back_low", "second", {"quadruped": "a forepaw, braced against it",
                                                 "biped": "her foot, braced against it"})],
            "free": {"quadruped": "her forepaws", "biped": "her tails and her mouth"},
            "strain": "her tail wrenched back at the root and her lower back bent with it"},
        "scruff hold": {
            "facing": ("standing", "sitting up"), "by": ("quadruped",),
            "look": {"quadruped": "at her side, jaws clamped in her scruff and her forepaws bearing down on her "
                                  "shoulders, wrenching her head round"},
            "contacts": [("neck", "main", {"quadruped": "her jaws, clamped in the scruff, wrenching it round"}),
                         ("shoulder", "second", {"quadruped": "her forepaws, bearing her shoulders down"})],
            "free": {"quadruped": "her hind legs and her tail"},
            "strain": "her neck wrenched round and her shoulders borne down under the weight"},
        "camel clutch": {
            "facing": ("face-down",), "by": ("biped", "quadruped"),
            "look": {"biped": "sitting astride her back, both paws locked under her chin, hauling her head and chest up "
                              "and back",
                     "quadruped": "sitting her weight on her back, jaws locked in her scruff, hauling her head and chest "
                                  "up and back"},
            "contacts": [("neck", "main", {"biped": "both paws, locked under her chin, hauling back",
                                           "quadruped": "her jaws, locked in her scruff, hauling back"}),
                         ("back_low|back_up", "main", {"biped": "her weight, sitting on it, bending it",
                                                       "quadruped": "her weight, sitting on it, bending it"})],
            "free": {"biped": "her mouth, right at the back of her head (a bite, or a blast from point-blank)",
                     "quadruped": "her horn and her tail"},
            "strain": "her spine bent backward like a bow, her neck cranked up and back"},
        "boston crab": {
            "facing": ("face-down",), "by": ("biped",), "needs": "two_legs",
            "look": {"biped": "both her legs hauled up under her arms, sitting back on them, folding them back over "
                              "her own spine"},
            "contacts": [("legs", "main", {"biped": "her arms, the legs tucked under them, hauled back"}),
                         ("back_low|back_up", "main", {"biped": "her weight, sitting back on it"})],
            "free": {"biped": "her tails"},
            "strain": "her legs folded back toward her head and her lower back bent the wrong way under the weight"},
        "armbar": {
            "facing": ("face-up",), "by": ("biped",), "needs": "arm",
            "look": {"biped": "lying across her, one arm pulled out straight across her own hips and wrenched against "
                              "the joint, her legs pinning the shoulder"},
            "contacts": [("arm", "main", {"biped": "both paws, wrenching it straight across her hips"}),
                         ("shoulder", "second", {"biped": "her legs across it, pinning it"})],
            "free": {"biped": "her tails"},
            "strain": "the elbow forced straight and past straight, the shoulder wrenched in its socket"},
        "crossface": {
            "facing": ("face-down",), "by": ("biped",),
            "look": {"biped": "on her back with a forearm cranked across her face, pulling her head back and round, "
                              "her knees trapping one arm"},
            "contacts": [("head:jaw|muzzle", "main", {"biped": "her forearm, cranked across her face, pulling back"}),
                         ("neck", "main", {"biped": "the same forearm, cranking it back and round"}),
                         ("shoulder", "second", {"biped": "her knees, trapping it"})],
            "free": {"biped": "her tails"},
            "strain": "her head cranked back and round, her neck twisted to the edge of where it goes"},
        "leg lock": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped", "quadruped"), "needs": "leg",
            "look": {"biped": "sitting on her legs with one leg twisted round in both paws, the joint turned against "
                              "itself",
                     "quadruped": "one leg clamped in her jaws and twisted, her forepaws pinning the other"},
            "contacts": [("leg_joint", "main", {"biped": "both paws, twisting it", "quadruped": "her jaws, twisting it"}),
                         ("hind_up", "second", {"biped": "her weight, sitting on it", "quadruped": "her forepaw"})],
            "free": {"biped": "her mouth and her tails", "quadruped": "her horn"},
            "strain": "the joint twisted against itself, turned the way it doesn't go"},
        "tail crank": {
            "facing": ("face-down", "on her side"), "by": ("biped", "quadruped"), "needs": "tail",
            "look": {"biped": "her tail hauled up in both paws and twisted, a foot planted in the small of her back",
                     "quadruped": "her tail clamped in her jaws and wrenched up and round, a forepaw planted on her back"},
            "contacts": [("tail_part", "main", {"biped": "both paws, hauling it up and twisting it",
                                                "quadruped": "her jaws, wrenching it up and round"}),
                         ("tail:base", "main", {"biped": "the same grip, twisting it from its root",
                                                "quadruped": "the same jaws, wrenching it from its root"}),
                         ("back_low|back_up", "second", {"biped": "her foot, planted on it", "quadruped": "her forepaw, planted on it"})],
            "free": {"biped": "her mouth and her tails", "quadruped": "her horn"},
            "strain": "the tail hauled up and twisted from its root, the base of it wrenched"},
        # more holds, and nastier ones: what a Pokemon's body and the arena make possible ("has": the holder needs it;
        # "prop": it uses the scenery, {prop} in its words: "near" = what she lies against, "ground" = the rough ground)
        "figure-four leg lock": {
            "facing": ("face-up",), "by": ("biped",), "needs": "leg",
            "look": {"biped": "sitting at her feet with her legs figure-foured round one of hers, both their weights "
                              "bending the knee sideways against its hinge"},
            "contacts": [("leg_joint", "main", {"biped": "her legs, locked in a figure four round it, bending it sideways"}),
                         ("foot", "second", {"biped": "her own leg, hooked over it and holding it down"})],
            "free": {"biped": "her paws and her tails"},
            "strain": "the knee bent sideways against its hinge, the shin levered the way it doesn't go"},
        "ankle lock": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped",), "needs": "leg",
            "look": {"biped": "the foot trapped under her arm and wrenched back and round, her knees clamped on the "
                              "leg above it"},
            "contacts": [("foot", "main", {"biped": "her arm, hooked under the heel, wrenching the foot back and round"}),
                         ("leg_joint", "second", {"biped": "her knees, clamped on it"})],
            "free": {"biped": "her mouth and her tails"},
            "strain": "the ankle bent back and twisted at once, the whole leg rigid with it"},
        "tail-bound knee crank": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped", "quadruped"), "needs": "leg",
            "has": "tails",
            "look": {"biped": "her twin tails wound round the hurt knee and twisting one way while both paws turn "
                              "the foot the other",
                     "quadruped": "her tails wound round the hurt leg and twisting it while her jaws hold the foot"},
            "contacts": [("leg_joint", "main", {"biped": "her twin tails, wound round it and wrenching it sideways",
                                                "quadruped": "her tails, wound round it and wrenching it"}),
                         ("foot", "main", {"biped": "both paws, turning it against the twist of the tails",
                                           "quadruped": "her jaws, holding it against the twist"})],
            "free": {"biped": "her mouth", "quadruped": "nothing: all of her is in it"},
            "strain": "the knee wrenched two ways at once, the tails and the paws turning it against each other"},
        "root lever": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped", "quadruped"), "needs": "leg",
            "prop": "ground",
            "look": {"biped": "the hurt leg dragged across {prop} and levered back over it, her whole weight on the "
                              "shin, the knee bent backward across the hump",
                     "quadruped": "the hurt leg pinned across {prop} under her forepaws and leaned on, the knee bent "
                                  "backward over it"},
            "contacts": [("leg_joint", "main", {"biped": "her weight, levering it back over {prop}",
                                                "quadruped": "her forepaws and her weight, levering it back over {prop}"}),
                         ("hind_up", "second", {"biped": "both paws, pinning it down", "quadruped": "her jaws, holding it"})],
            "free": {"biped": "her tails", "quadruped": "her tail"},
            "strain": "the knee bent backward over {prop}, the leg used as a lever against the ground itself"},
        "trunk arm wrench": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped",), "needs": "arm", "prop": "near",
            "look": {"biped": "her arm hauled round {prop} and wrenched back against it, a knee pinning her shoulder to it"},
            "contacts": [("arm", "main", {"biped": "both paws, wrenching it back round {prop}"}),
                         ("shoulder", "second", {"biped": "her knee, pinning it against {prop}"})],
            "free": {"biped": "her mouth and her tails"},
            "strain": "the arm bent back round {prop}, the shoulder wrenched against it"},
        "tail strangle": {
            "facing": ("face-down", "on her side"), "by": ("biped", "quadruped"), "has": "tails",
            "look": {"biped": "kneeling on her back with her twin tails looped round the throat from behind and drawn "
                              "tight, both paws hauling the tails back like reins",
                     "quadruped": "standing over her with her tails looped round the throat and drawn tight"},
            "contacts": [("neck", "main", {"biped": "her twin tails, looped round from behind and drawn tight",
                                           "quadruped": "her tails, looped round and drawn tight"}),
                         ("back_up|back_low", "second", {"biped": "her knees, planted in her back",
                                                         "quadruped": "her forepaws, planted on her back"})],
            "free": {"biped": "her mouth", "quadruped": "her jaws"},
            "strain": "the throat closed by the tails, the head hauled back, the back bowed under the knees"},
        "chicken wing": {
            "facing": ("face-down",), "by": ("biped",), "needs": "arm",
            "look": {"biped": "kneeling on her back with one arm bent up behind it, hauled higher and higher toward "
                              "the shoulder blade"},
            "contacts": [("arm", "main", {"biped": "both paws, bending it up behind her back"}),
                         ("shoulder", "main", {"biped": "the same grip, wrenching it up out of its socket"}),
                         ("back_up|back_low", "second", {"biped": "her knee, in her back"})],
            "free": {"biped": "her mouth and her tails"},
            "strain": "the arm bent up behind her toward the shoulder blade, the shoulder forced out to the edge of its socket"},
        "scorpion lock": {
            "facing": ("face-down",), "by": ("biped",), "needs": "two_legs",
            "look": {"biped": "her legs crossed and folded up, the attacker stepping over and sitting back on them, "
                              "bending her lower back and knees together"},
            "contacts": [("legs", "main", {"biped": "her legs, crossed and folded under her arms as she sits back"}),
                         ("back_low|back_up", "main", {"biped": "her weight, sitting back and bending it"})],
            "free": {"biped": "her tails"},
            "strain": "the knees and the lower back bent together, the legs crossed and crushed back toward her head"},
        "jaw lock": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped", "quadruped"), "needs": "leg",
            "look": {"biped": "her jaws clamped on the hurt knee and twisting, worrying at it, both paws holding the leg "
                              "still for her teeth",
                     "quadruped": "her jaws clamped on the hurt knee, twisting and worrying at it"},
            "contacts": [("leg_joint", "main", {"biped": "her jaws, clamped on and twisting",
                                                "quadruped": "her jaws, clamped on and twisting"}),
                         ("hind_up", "second", {"biped": "both paws, holding the leg still", "quadruped": "her forepaws"})],
            "free": {"biped": "her tails", "quadruped": "her tail"},
            "strain": "teeth sunk into the joint and twisting it, the leg held still to take it"},
        "surfboard stretch": {
            "facing": ("face-down",), "by": ("biped",),
            "look": {"biped": "both her arms hauled back by the wrists, knees driven into her back, bending her up off "
                              "the ground like a drawn bow"},
            "contacts": [("shoulder", "main", {"biped": "both paws, hauling the arms back"}),
                         ("back_up|back_low", "main", {"biped": "her knees, driven into her back"})],
            "free": {"biped": "her tails"},
            "strain": "her shoulders hauled back to their limit, her spine bent up off the ground"},
        "sleeper hold": {
            "facing": ("face-down", "on her side"), "by": ("biped",),
            "look": {"biped": "behind her, one arm locked round her neck and the other pressing her head forward into "
                              "the crook of it, her legs hooked round her middle"},
            "contacts": [("neck", "main", {"biped": "her arm, locked round it from behind and squeezing"}),
                         ("chest|belly", "second", {"biped": "her legs, hooked round her middle"})],
            "free": {"biped": "her tails"},
            "strain": "the blood to her head squeezed off from both sides, the dark coming in at the edges"},
        "head scissors": {
            "facing": ("face-up", "on her side"), "by": ("biped", "quadruped"),
            "look": {"biped": "sitting with her legs scissored round the neck and squeezing, both paws hauling the head "
                              "back against them",
                     "quadruped": "lying with her hind legs scissored round the neck and squeezing"},
            "contacts": [("neck", "main", {"biped": "her legs, scissored round it and squeezing",
                                           "quadruped": "her hind legs, scissored round it"}),
                         ("head:head", "second", {"biped": "both paws, hauling it back", "quadruped": "her forepaws"})],
            "free": {"biped": "her tails", "quadruped": "her tail and her jaws"},
            "strain": "the neck crushed between the thighs, the head hauled back against them"},
        "triangle choke": {
            "facing": ("face-up",), "by": ("biped",), "needs": "arm",
            "look": {"biped": "her legs locked in a triangle round the neck and one trapped arm, pulling the head down "
                              "into the squeeze"},
            "contacts": [("neck", "main", {"biped": "her legs, locked in a triangle round it"}),
                         ("arm", "second", {"biped": "the same legs, trapping it against her own neck"})],
            "free": {"biped": "her paws and her tails"},
            "strain": "her own trapped arm pressed into her neck, the squeeze closing from both sides"},
        "knee bar": {
            "facing": ("face-down", "on her side"), "by": ("biped",), "needs": "leg",
            "look": {"biped": "the hurt leg trapped between her thighs and hugged to her chest as she arches back, "
                              "bending the knee the wrong way"},
            "contacts": [("leg_joint", "main", {"biped": "her hips, arching into it and bending it backward"}),
                         ("foot", "second", {"biped": "both arms, hugging it to her chest"})],
            "free": {"biped": "her tails"},
            "strain": "the knee bent backward against her hips, the leg hyperextended"},
        "coil crush": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped", "quadruped", "serpent"), "has": "tails",
            "look": {"biped": "her tails wound twice round her ribs and squeezing, both paws locking them tight",
                     "quadruped": "her tails wound round her ribs and squeezing",
                     "serpent": "coils wound round her ribs and tightening"},
            "contacts": [("chest", "main", {"biped": "her tails, wound round it and squeezing",
                                            "quadruped": "her tails, wound round it", "serpent": "her coils, wound round it"}),
                         ("belly", "second", {"biped": "the lower turn of the tails", "quadruped": "the lower turn of her tails",
                                              "serpent": "the lower coil"})],
            "free": {"biped": "her paws and her mouth", "quadruped": "her jaws", "serpent": "her jaws"},
            "strain": "the ribs squeezed in, each breath shorter than the last"},
        # the wrists, the ankles, the stomach and the back: holds that work the small joints and the soft middle
        "wrist lock": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped",), "needs": "arm",
            "look": {"biped": "her paw caught in both of hers and folded back on itself at the wrist, her elbow "
                              "pinned against her own ribs so there is nowhere for the bend to go"},
            "contacts": [("wrist", "main", {"biped": "both paws, folding it back on itself"}),
                         ("arm", "second", {"biped": "her forearm, pinning the elbow"})],
            "free": {"biped": "her mouth and her tails"},
            "strain": "the wrist bent back past where it goes, the fingers splayed and trembling"},
        "kimura": {
            "facing": ("face-up", "on her side"), "by": ("biped",), "needs": "arm",
            "look": {"biped": "one wrist gripped and cranked up behind her back, her other arm threaded under the "
                              "elbow and locked onto her own wrist, levering the shoulder round"},
            "contacts": [("wrist", "main", {"biped": "her paw, gripping it and cranking it up behind"}),
                         ("shoulder", "main", {"biped": "her other arm, threaded under the elbow, levering it round"})],
            "free": {"biped": "her tails"},
            "strain": "the shoulder turned round in its socket, the arm cranked up behind her by the wrist"},
        "heel hook": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped",), "needs": "leg",
            "look": {"biped": "her legs tangled round the hurt leg, the heel trapped in the crook of her arm and turned, "
                              "the twist running up through the ankle into the knee"},
            "contacts": [("foot", "main", {"biped": "her arm, hooked round the heel and turning it"}),
                         ("leg_joint", "main", {"biped": "the same twist, carried up into it"}),
                         ("hind_up", "second", {"biped": "her legs, tangled round it"})],
            "free": {"biped": "her mouth and her tails"},
            "strain": "the heel turned and the ankle and knee twisted with it, all one wrench up the leg"},
        "toe hold": {
            "facing": ("face-up", "on her side"), "by": ("biped",), "needs": "leg",
            "look": {"biped": "kneeling on her shin with the foot in both paws, twisting it sideways at the ankle"},
            "contacts": [("foot", "main", {"biped": "both paws, twisting it sideways at the ankle"}),
                         ("leg_joint", "second", {"biped": "her knee, kneeling on the shin below it"})],
            "free": {"biped": "her mouth and her tails"},
            "strain": "the ankle rolled sideways and held there, the foot turned the way it doesn't go"},
        "body scissors": {
            "facing": ("face-up", "on her side"), "by": ("biped", "quadruped"),
            "look": {"biped": "her legs scissored round the middle and locked at the ankles, squeezing, both paws "
                              "holding her shoulders down",
                     "quadruped": "her hind legs scissored round the middle and squeezing, her forepaws on her chest"},
            "contacts": [("belly", "main", {"biped": "her legs, scissored round it and squeezing",
                                            "quadruped": "her hind legs, scissored round it"}),
                         ("back_low|back_up", "second", {"biped": "the locked ankles, digging into it",
                                                         "quadruped": "her hind paws, locked under it"})],
            "free": {"biped": "her paws, her mouth and her tails", "quadruped": "her jaws"},
            "strain": "the stomach crushed in from both sides, the breath squeezed out of her a little more each time "
                      "she lets one go"},
        "rear waist crush": {
            "facing": ("face-down", "on her side"), "by": ("biped",),
            "look": {"biped": "behind her, both arms locked round her middle and crushing it, her chest driven into "
                              "her lower back"},
            "contacts": [("belly", "main", {"biped": "both arms, locked round it and crushing"}),
                         ("back_low", "main", {"biped": "her chest and her weight, driven into it"})],
            "free": {"biped": "her mouth and her tails"},
            "strain": "the middle crushed between her arms and her chest, the lower back bent in against it"},
        "stomach claw": {
            "facing": ("face-up",), "by": ("biped", "quadruped"),
            "look": {"biped": "kneeling over her with one paw clamped on the stomach, claws sunk in, kneading and "
                              "twisting, the other paw pinning her chest",
                     "quadruped": "standing over her with her jaws clamped on the stomach, worrying at it, her forepaws "
                                  "on her chest"},
            "contacts": [("belly", "main", {"biped": "her paw, claws sunk in, clamping and twisting",
                                            "quadruped": "her jaws, clamped on and worrying"}),
                         ("chest", "second", {"biped": "her other paw, pinning it", "quadruped": "her forepaws, pinning it"})],
            "free": {"biped": "her mouth and her tails", "quadruped": "her tail"},
            "strain": "the soft middle clamped and twisted, the gut clenching against the grip"},
        "knee on belly": {
            "facing": ("face-up",), "by": ("biped", "quadruped"),
            "look": {"biped": "one knee driven into the stomach with all her weight behind it, both paws pinning her "
                              "shoulders",
                     "quadruped": "both forepaws planted on the stomach and all her weight leaned onto them"},
            "contacts": [("belly", "main", {"biped": "her knee, all her weight driven into it",
                                            "quadruped": "her forepaws, all her weight on them"}),
                         ("shoulder", "second", {"biped": "both paws, pinning them", "quadruped": "her jaws, in the scruff"})],
            "free": {"biped": "her tails", "quadruped": "her tail"},
            "strain": "the weight crushing the breath out of her, nothing to push it off with"},
        "bow and arrow": {
            "facing": ("face-down", "on her side"), "by": ("biped",), "needs": "leg",
            "look": {"biped": "her knee in the small of the back, one arm round the neck and the other hauling a leg "
                              "back, bending her body like a drawn bow"},
            "contacts": [("back_low", "main", {"biped": "her knee, driven into it, the point of the bend"}),
                         ("neck", "second", {"biped": "one arm, hooked round it and hauling back"}),
                         ("hind_up", "second", {"biped": "her other paw, hauling the leg back"})],
            "free": {"biped": "her tails"},
            "strain": "the spine bent back like a drawn bow, the knee the point it bends over"},
        "backbreaker": {
            "facing": ("face-up",), "by": ("biped", "quadruped"), "prop": "near",
            "look": {"biped": "her back laid over {prop} and both paws bearing down on her middle, bending her "
                              "backward across it",
                     "quadruped": "her back laid over {prop} and her forepaws and weight bearing down on her middle"},
            "contacts": [("back_low|back_up", "main", {"biped": "the bend, over {prop}", "quadruped": "the bend, over {prop}"}),
                         ("belly", "second", {"biped": "both paws, bearing down on it", "quadruped": "her forepaws, bearing down"})],
            "free": {"biped": "her mouth and her tails", "quadruped": "her jaws"},
            "strain": "the back bent backward over {prop}, the spine arched past where it wants to go"},
        "wrist bite": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("quadruped",), "needs": "arm",
            "look": {"quadruped": "her jaws clamped on the wrist and twisting it, a forepaw pinning the elbow down"},
            "contacts": [("wrist", "main", {"quadruped": "her jaws, clamped on and twisting it"}),
                         ("arm", "second", {"quadruped": "her forepaw, pinning it"})],
            "free": {"quadruped": "her tail"},
            "strain": "the wrist held in teeth and turned, the small bones grinding"},
        "hamstring hold": {
            "facing": ("face-down", "on her side"), "by": ("quadruped",), "needs": "leg",
            "look": {"quadruped": "her jaws clamped in the back of the thigh and hauling, a forepaw pressing the knee "
                                  "down"},
            "contacts": [("hind_up", "main", {"quadruped": "her jaws, clamped in it and hauling"}),
                         ("leg_joint", "second", {"quadruped": "her forepaw, pressing it down"})],
            "free": {"quadruped": "her tail"},
            "strain": "the long muscle of the thigh stretched and torn at by the jaws, the knee held so it can't bend "
                      "with it"},
        "talon clamp": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("avian",),
            "look": {"avian": "standing on her with both talons sunk in and clenched, her wings spread for balance and "
                              "her beak at the back of the neck"},
            "contacts": [("back_up|chest", "main", {"avian": "her talons, sunk in and clenching"}),
                         ("neck", "second", {"avian": "her beak, clamped on it"})],
            "free": {"avian": "her wings"},
            "strain": "talons clenched deep into the muscle, the weight of the bird bearing down through them"},
        "talon wrist pin": {
            "facing": ("face-up", "on her side"), "by": ("avian",), "needs": "arm",
            "look": {"avian": "one talon clamped round the wrist and grinding it into the ground, the other foot on her "
                              "chest"},
            "contacts": [("wrist", "main", {"avian": "one talon, clamped round it and grinding"}),
                         ("chest", "second", {"avian": "her other foot, planted on it"})],
            "free": {"avian": "her beak and her wings"},
            "strain": "the wrist crushed in the talon and ground into the earth"},
        # the tail: a hold on it works the tail itself and the root it hangs from, which goes on up the spine
        "tail fold": {
            "facing": ("face-down", "on her side"), "by": ("biped",), "needs": "tail",
            "look": {"biped": "kneeling on her lower back with the tail folded back over itself in both paws, bent "
                              "double toward the root"},
            "contacts": [("tail_part", "main", {"biped": "both paws, folding it back over itself"}),
                         ("tail:base", "main", {"biped": "the fold, wrenching it at the root"}),
                         ("back_low", "second", {"biped": "her knee, kneeling on it"})],
            "free": {"biped": "her mouth and her tails"},
            "strain": "the tail bent double, the root of it wrenched and the pull running on up her spine"},
        "tail and leg stretch": {
            "facing": ("face-down",), "by": ("biped",), "needs": "tail",
            "look": {"biped": "standing over her with the tail hauled up in one paw and a leg hauled up and back in the "
                              "other, stretching the two apart over her own back"},
            "contacts": [("tail_part", "main", {"biped": "one paw, hauling it up and back"}),
                         ("hind_up", "main", {"biped": "her other arm, hauling the leg up the other way"}),
                         ("back_low", "second", {"biped": "her foot, planted on it"})],
            "free": {"biped": "her mouth and her tails"},
            "strain": "the tail and the leg stretched apart, the lower back bent between them"},
        "tail bind": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("biped", "quadruped"), "needs": "tail",
            "has": "tails",
            "look": {"biped": "her own twin tails wound round the other's tail and the ankle together, binding the two "
                              "and hauling them toward each other, both paws on her shoulders",
                     "quadruped": "her tails wound round the other's tail and one hind leg together, hauling them "
                                  "toward each other"},
            "contacts": [("tail_part", "main", {"biped": "her twin tails, bound round it and hauling",
                                                "quadruped": "her tails, bound round it"}),
                         ("tail:base", "main", {"biped": "the same pull, wrenching it at the root",
                                                "quadruped": "the same pull, wrenching it at the root"}),
                         ("foot", "second", {"biped": "the same tails, bound round it and hauling it to the tail",
                                             "quadruped": "the same tails, hauling it back"})],
            "free": {"biped": "her paws and her mouth", "quadruped": "her jaws"},
            "strain": "the tail and the leg bound together and hauled toward each other, the hip and the tail root "
                      "both wrenched"},
        "tail bite": {
            "facing": ("face-down", "on her side"), "by": ("quadruped",), "needs": "tail",
            "look": {"quadruped": "her jaws clamped on the tail and hauling back, both forepaws planted on her lower "
                                  "back"},
            "contacts": [("tail_part", "main", {"quadruped": "her jaws, clamped on it and hauling back"}),
                         ("back_low", "second", {"quadruped": "her forepaws, planted on it"})],
            "free": {"quadruped": "her horn"},
            "strain": "the tail hauled back in the teeth, the pull wrenching at its root"},
        "tail stomp": {
            "facing": ("face-down", "on her side"), "by": ("avian",), "needs": "tail",
            "look": {"avian": "one talon clamped on the tail and grinding it into the ground, the other foot on her "
                              "lower back"},
            "contacts": [("tail_part", "main", {"avian": "one talon, clamped on it and grinding"}),
                         ("back_low", "second", {"avian": "her other foot, on it"})],
            "free": {"avian": "her beak and her wings"},
            "strain": "the tail crushed in the talon, pinned to the ground"},
        "limb wrench": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("quadruped",), "needs": "arm",
            "look": {"quadruped": "one forelimb clamped in her jaws and twisted and shaken, a forepaw pinning her "
                                  "shoulder down"},
            "contacts": [("arm", "main", {"quadruped": "her jaws, twisting and shaking it"}),
                         ("shoulder", "second", {"quadruped": "her forepaw, pinning it"})],
            "free": {"quadruped": "her horn and her tail"},
            "strain": "the limb twisted and shaken in her jaws, the joint wrenched against itself"},
    }

    def _sub_part(self, d, spec, used=(), prefer=None):
        """The defender's part for one submission contact. Of a left and a right, the side the direction named
        (prefer), else the HURT one: a leg lock goes on the leg that is already damaged (a holder works the known
        injury); and once one contact has a side, the others take the same side (the knee and the hip of the same
        leg)."""
        names = [n for n in d.parts if n not in used]
        def region_of(n):
            return body_region(n)
        side_ = next((sd for u in used for sd in ("Left", "Right") if u.startswith(sd + " ")), None) or prefer
        def pick(cands):
            if not cands:
                return None
            if side_ and any(c.startswith(side_ + " ") for c in cands):
                cands = [c for c in cands if c.startswith(side_ + " ")]
            def limb_hurt(c):
                # the part's own damage, and the rest of that limb on that side (a hurt knee makes its foot the target)
                sd = next((x for x in ("Left", "Right") if c.startswith(x + " ")), None)
                grp = {"hind_up": "hind", "hind_low": "hind", "fore_up": "fore", "fore_low": "fore",
                       "shoulder": "fore"}.get(region_of(c))
                rest = sum(p.damage for n, p in d.parts.items() if sd and grp and n != c and n.startswith(sd + " ")
                           and {"hind_up": "hind", "hind_low": "hind", "fore_up": "fore", "fore_low": "fore",
                                "shoulder": "fore"}.get(region_of(n)) == grp)
                return d.parts[c].damage + 0.5 * rest
            return max(cands, key=lambda c: (limb_hurt(c), -cands.index(c)))
        if spec == "legs":
            legs = [n for n in names if region_of(n) == "hind_up" and "thigh" in n.lower()] or \
                   [n for n in names if region_of(n) in ("hind_up", "hind_low")]
            return legs[:2] if len(legs) >= 2 else None
        if spec == "arm":
            return pick([n for n in names if region_of(n) == "fore_up" and "wing" not in n.lower()])
        if spec == "leg_joint":
            return pick([n for n in names if region_of(n) == "hind_low" and any(k in n.lower() for k in ("knee", "hock"))])
        if spec == "wrist":
            # (a wrist is where the paw meets the forearm: the paw, the hand, the forearm itself; never a wingtip)
            low = [n for n in names if region_of(n) == "fore_low" and "wing" not in n.lower()]
            return pick([n for n in low if any(k in n.lower() for k in ("paw", "hand", "wrist", "claw"))]
                        or [n for n in low if "forearm" in n.lower()])
        if spec == "foot":
            return pick([n for n in names if region_of(n) == "hind_low" and any(k in n.lower() for k in ("foot", "ankle", "hind paw"))])
        if spec == "tail_part":
            t = [n for n in names if region_of(n) == "tail" and "base" not in n.lower()]
            return t[0] if t else None
        if spec == "tail:base":
            t = [n for n in names if "tail base" in n.lower()]
            return t[0] if t else None
        if spec.startswith("head:"):
            keys = spec.split(":", 1)[1].split("|")
            for k in keys:
                hit = [n for n in names if k in n.lower()]
                if hit:
                    return pick(hit)
            return None
        for reg in spec.split("|"):
            hit = [n for n in names if region_of(n) == reg and not (reg == "neck" and "throat" in n.lower()
                                                                     and any("neck" in m.lower() for m in names))]
            if hit:
                return pick(hit)
        return None

    @staticmethod
    def sub_is_choke(shape):
        """A submission shape whose main grip is on the neck or throat: a choke (a sleeper, a triangle, head scissors)."""
        return any(role == "main" and body_region(part) == "neck" for part, role, _ in shape.get("contacts") or ())

    JAWS_GRIP = re.compile(r"(?i)\b(?:jaws?|teeth|fangs?|bite|bit|biting|mouth)\b")

    @classmethod
    def sub_uses_jaws(cls, shape):
        """A submission shape gripped with her jaws (a bite hold: jaws clamped on a limb, the scruff, a tail)."""
        return any(cls.JAWS_GRIP.search(str(c[2] if len(c) > 2 else "")) for c in shape.get("contacts") or ())

    def hold_mix(self):
        """finish.submission.hold_mix (since build 265): how often a choke or a jaw hold stands when one is chosen
        ({} when off)."""
        m = (((self.rules.get("finish") or {}).get("submission") or {}).get("hold_mix") or {})
        return m if m.get("enabled", True) else {}

    def choke_tried(self):
        """Whether a choke has already gone on in this match (a hold on the neck, by its grips or its name)."""
        for n in self.subs_used():
            s = self.SUBMISSIONS.get(n)
            if (s and any(role == "main" and "neck" in spec for spec, role, _ in s.get("contacts") or ())) or (
                    not s and re.search(r"(?i)\b(?:choke|neck|throat|sleeper|guillotine|strangle\w*|headlock)\b", n)):
                return True
        return False

    def mix_keep(self, choke, jaws):
        """The chance a chosen choke or jaw hold stands (hold_mix.choke, halved by after_first once a choke has been
        tried; hold_mix.jaws for a bite hold). 1.0 for any other hold, or with hold_mix off."""
        m = self.hold_mix()
        if not m:
            return 1.0
        keep = 1.0
        if choke:
            keep *= float(m.get("choke", 0.35)) * (float(m.get("after_first", 0.5)) if self.choke_tried() else 1.0)
        if jaws:
            keep *= float(m.get("jaws", 0.5))
        return keep

    def pick_submission(self, shapes, rng=None, defender=None):
        """One submission to offer from `shapes`: a choke only choke_share of the time when there is anything else to
        offer (finish.submission.choke_share), so a submission match ends in a lock on a limb or the body far more
        often than in a choke. Returns its name, or None when there are no shapes."""
        if not shapes:
            return None
        rng = rng or self.rng
        if self._taps_rule():
            # finish.submission.taps: a hold whose every grip is on a part her taps have used up can't end anything:
            # keep to holds that still count, and (taps.steer.holds of the time) one on the part being worked
            defender = self.get(defender) if isinstance(defender, str) else defender
            if defender is not None:
                spent = set(self.spent_tap_parts(defender))
                live = {n: v for n, v in shapes.items() if any(c[0] not in spent for c in v["contacts"])}
                shapes = live or shapes
                aim = self.tap_target(defender)
                on_aim = {n: v for n, v in shapes.items() if any(c[0] == aim for c in v["contacts"])}
                if on_aim and rng.random() < self.tap_steer("holds"):
                    shapes = on_aim
        ucfg = (self.rules.get("submissions") or {}).get("upright") or {}
        ground = {n: v for n, v in shapes.items() if v.get("lands")}
        if ground and len(ground) < len(shapes) and rng.random() >= float(ucfg.get("pick_share", 0.4)):
            # (since build 249) on her feet, most openings take her down into a hold on the ground; one that keeps her
            # standing only upright.pick_share of the time
            shapes = ground
        chokes = sorted(n for n, v in shapes.items() if self.sub_is_choke(v))
        others = sorted(n for n in shapes if n not in chokes)
        share = float(((self.rules.get("finish") or {}).get("submission") or {}).get("choke_share", 0.1))
        if chokes and others:
            pool = chokes if rng.random() < share else others
        else:
            pool = chokes or others
        jw = float(self.hold_mix().get("jaws", 0.5)) if self.hold_mix() else 1.0
        if jw < 1.0 and any(not self.sub_uses_jaws(shapes[n]) for n in pool):
            # (hold_mix.jaws) a hold gripped with her jaws comes up that much less often than one with paws, legs,
            # tails or her weight
            return rng.choices(pool, weights=[jw if self.sub_uses_jaws(shapes[n]) else 1.0 for n in pool])[0]
        return rng.choice(pool)

    def submission_shapes(self, attacker, defender, side=None):
        """The submission holds THIS attacker could put on THIS defender as she lies now: {name: {"look",
        "contacts": [(part, role, with)], "free", "strain"}}. side ("Left"/"Right"): the side the direction named,
        taken over the hurt one."""
        a, d = self.get(attacker), self.get(defender)
        plan = self.body_plan(a)
        lie = self.facing_of(d.name) if d.name in self.downed else None if self.has(d, "airborne") else "standing"
        if lie in ("standing", "sitting up") and not self._upright_on():
            lie = None if lie == "standing" else lie     # (upright holds off: no hold on a fighter on her feet)
        # submissions.match.standing: on her feet, a hold she can be taken down into, landing as it needs her
        stand = d.name not in self.downed and self.standing_sub_on() and not self.has(d, "airborne")
        out = {}
        prop_near = (getattr(self, "lying_at", None) or {}).get(d.name)
        rough = str((self.scene_cfg or {}).get("rough") or "")
        prop_ground = (prop_near or ("a root humped out of the ground" if "root" in rough else
                                      f"a ridge of {rough}" if rough else ""))
        for name, s in self.SUBMISSIONS.items():
            if set(s["facing"]) <= {"standing", "sitting up"} and (not self._upright_on() or a.name in self.downed):
                continue     # (an upright hold needs the holder up: one lying on the ground can't stand behind her)
            lands = next((x for x in ("face-down", "face-up", "on her side") if x in s["facing"]), None) \
                if stand and lie not in s["facing"] else None
            if plan not in s["by"] or (lie not in s["facing"] and not lands):
                continue
            if s.get("has") == "tails" and not any(re.search(r"\btails?\b", n.lower()) for n in a.parts):
                continue
            prop = {"near": prop_near, "ground": prop_ground}.get(s.get("prop")) if s.get("prop") else ""
            if s.get("prop") and not prop:
                continue      # (nothing there to use)
            used, contacts, ok = [], [], True
            for spec, role, how in s["contacts"]:
                got = self._sub_part(d, spec, used, side)
                if not got:
                    ok = False
                    break
                for p in (got if isinstance(got, list) else [got]):
                    used.append(p)
                    contacts.append((p, role, how[plan].replace("{prop}", prop)))
            if ok and contacts:
                out[name] = {"look": s["look"][plan].replace("{prop}", prop), "contacts": contacts,
                             "free": s["free"][plan], "strain": s["strain"].replace("{prop}", prop),
                             "used": self.sub_uses(name)}
                if lands:
                    out[name]["lands"] = lands    # (she is on her feet: taken down into it, landing so)
        return out

    # what a grip's words need her body to have ("her twin tails" needs tails): (words, part names that show she has it)
    GRIP_NEEDS = [(r"\b(?:paws?|hands?|arms?|forearms?|fists?|elbows?|fingers?)\b", r"arm|paw|hand|foreleg"),
                  (r"\btails?\b", r"tail"), (r"\bwings?\b", r"wing"), (r"\btalons?\b", r"talon"),
                  (r"\bhorns?\b", r"horn"), (r"\bfins?\b", r"fin"),
                  (r"\b(?:legs?|knees?|feet|foot|heels?|thighs?|shins?)\b", r"thigh|leg|knee|foot|hock|talon"),
                  (r"\bcoils?\b", r"^(?!.*(?:thigh|leg|knee|foot|hock|talon)).*$")]

    def grip_problem(self, f, with_):
        """Why her body can't grip with this ('' when it can): the grip's words ask for a part she has none of."""
        names = " | ".join(n.lower() for n in f.parts)
        w = str(with_ or "").lower()
        if re.search(r"\b(?:teeth|fangs|jaws?)\b", w) and "beak" in names:
            return f"{f.name} has a beak, not teeth or jaws"
        for words, has in self.GRIP_NEEDS:
            m = re.search(words, w)
            if m and not re.search(has, names):
                return f"{f.name} has no {m.group(0)} to grip with"
        return ""

    # an invented hold's name and the regions of her body it has to grip (submissions.invented_fit)
    SUB_NAME_PARTS = (
        (r"\b(?:knee|kneebar|heel|ankle|hock|toe ?hold|calf|shin|leg ?lock|leglock)\b", ("hind_up", "hind_low"),
         "leg"),
        (r"\b(?:arm ?bar|armbar|arm ?lock|armlock|elbow|wrist|kimura|americana|hammerlock)\b",
         ("fore_up", "fore_low", "shoulder"), "arm"),
        (r"\b(?:choke|neck|throat|sleeper|guillotine|strangle\w*|headlock|head lock)\b", ("neck", "head"),
         "neck"),
        (r"\btail\b", ("tail",), "tail"),
    )

    UPRIGHT_WORDS = re.compile(r"(?i)\b(?:standing|upright|on (?:her|their) feet|nelson|headlock|bear ?hug|"
                               r"guillotine|from behind her as she stands|stood|lifts? her|sitting|seated)\b")

    def start_custom_submission(self, attacker, defender, name, grips, flavor="", enforce=False, upright=None):
        """A submission hold of the director's own invention (not in SUBMISSIONS): "grips" = [(her part, what grips
        it)], 1 to 3 of them; the first wrenches hardest. It is checked against both bodies, so nothing impossible goes
        on: every part must be hers, and every grip must use a part the holder really has (no paws on a bird, no
        tails on a fighter without one). Otherwise it is a submission like any other: it wrenches every beat, harder
        each beat, counts toward the holds used, and can make her tap."""
        a, d = self.get_active(attacker), self.get_active(defender)
        cfg = self.rules.get("submissions") or {}
        key = " ".join(str(name or "").lower().split())[:40] or "improvised hold"
        grips = [(p, w) for p, w in grips if p in d.parts][:3]
        if not grips:
            raise ValueError(f"an invented submission needs the parts of {d.name} it grips (in 'hits'), from her body: "
                             f"{', '.join(d.parts)}")
        for _p, w in grips:
            why = self.grip_problem(a, w)
            if why:
                raise ValueError(f"the {key} can't go on as described: {why}. Grip with what she has: "
                                 f"{', '.join(a.parts)}")
        if enforce:
            # (holds.coil.size, since build 275) a serpent that dwarfs her works the hold from coils round her middle
            cs_, note_ = self.coil_body_first(a.name, d.name, [(p, 1.0, 0.0, w) for p, w in grips], flavor=flavor,
                                              keep_limbs=1, rebind=False)
            if note_:
                grips = [(c[0], c[3]) for c in cs_][:3]
        if enforce:
            # (since build 261) what her limbs can really do: trapped, wrecked, already busy, out of reach, and a
            # main grip that can be wrenched (holds.invented_check)
            grips, _why = self.check_grips(a.name, d.name, grips, submission=True)
        if enforce:
            # (since build 260) a press with nothing behind her goes (holds.backstop), as in any hold
            kept_, gone_ = self.shape_hold(a.name, d.name, [(p, 1.0, 0.0, w) for p, w in grips], share=False)
            if gone_:
                grips = [(p, w) for p, w in grips if p not in gone_]
        if enforce and cfg.get("invented_fit", True):
            # (since build 258) a hold named for a part grips that part: a "standing knee lock" on her left shoulder
            # (the build-254 Ripples vs Nocturne log) is refused, and the director names it for what it grips
            for rx, regions, word in self.SUB_NAME_PARTS:
                hit = re.search(rx, key)
                if hit and not any(body_region(p) in regions for p, _w in grips):
                    raise ValueError(f"the {key} is named for her {word} but grips her "
                                     f"{', '.join(p.lower() for p, _w in grips)}: grip her {word} with it, or name the "
                                     f"hold for what it grips")
        if enforce:
            if not cfg.get("enabled", True):
                raise ValueError("submission holds are off (rules.json submissions.enabled)")
            if d.name not in self.downed and not (self.standing_sub_on() and not self.has(d, "airborne")):
                raise ValueError(f"{d.name} is on her feet: a submission hold needs her on the ground first (on her "
                                 f"feet, a hold_start is the way to grab and wrench)")
            if self.pinned_by(d.name) or (a.name in self.downed and not self.ground_lock_ok(a.name, d.name)) \
                    or self.pinned_by(a.name) or self.pinning(a.name):
                raise ValueError(f"{a.name} isn't free to lock a hold on {d.name} right now")
            self._sub_caught(a)
            if self.__dict__.get("sub_window", {}).get(d.name) is not True and not self.__dict__.get("_sub_open_all"):
                raise ValueError(f"no submission opening on {d.name} this beat. Choose another action")
            slip = self._small_joint_slip(a, d, key, [grips[0][0]], flavor or key)
            if slip:
                return slip
        takedown = None
        # an invented hold the director says is put on her upright ("upright": true, or its own words) keeps her up
        # (submissions.upright: it may bear her down later); any other is a takedown into it
        up = self._upright_on() and (bool(upright) if upright is not None
                                     else bool(self.UPRIGHT_WORDS.search(f"{name} {flavor or ''}")))
        if d.name not in self.downed and enforce and not up:
            takedown = self._sub_takedown(a, d, "face-down" if re.search(r"\bfrom behind\b|\bback\b", str(flavor or ""),
                                                                         re.I) else "face-up")
        main, second = float(cfg.get("power", 16)), float(cfg.get("second_power", 9))
        ramp, ramp2 = float(cfg.get("ramp", 3)), float(cfg.get("second_ramp", 1))
        contacts = [(p, main if i == 0 else second, ramp if i == 0 else ramp2, short_phrase(w, 9) if w else "")
                    for i, (p, w) in enumerate(grips)]
        res = self.start_holds(a.name, d.name, contacts, flavor or key, pin=False, enforce=enforce)
        for hid in res.get("hold_ids") or []:
            if hid in self.holds:
                self.holds[hid].sub = key
        self.__dict__.setdefault("sub_window", {})[d.name] = False
        self._count("submission", d.name)
        self._count(f"subname:{key}", a.name)
        if takedown:
            res["takedown"], res["taken_down"] = takedown, True
        res["submission"] = {"name": key, "look": flavor or key, "free": "", "invented": True,
                             "from_ground": a.name in self.downed, "takedown": (takedown or {}).get("how"),
                             "upright": self._upright_word(d),
                             "strain": f"the {', '.join(p.lower() for p, _ in grips)} wrenched where it is held",
                             "max_beats": int(cfg.get("max_beats", 3))}
        return res

    def subs_used(self):
        """{hold name: times put on} for every submission used this fight, the invented ones too."""
        out = {}
        for k, v in self.tally.items():
            if k.startswith("subname:"):
                n = k.split(":", 1)[1].rsplit("|", 1)[0]
                out[n] = out.get(n, 0) + int(v)
        return out

    def sub_uses(self, name):
        """How many times this submission hold has been put on anyone this fight."""
        return sum(int(v) for k, v in self.tally.items() if k.startswith(f"subname:{name}|"))

    def sub_chance(self, f):
        """The chance of an opening to lock a submission on her this beat: only while she is down and not pinned or
        held, and very rare (submissions.chance; x weak_mult once she is under half strength)."""
        cfg = self.rules.get("submissions") or {}
        if not cfg.get("enabled", True) or self.pinned_by(f.name) \
                or any(h.defender == f.name for h in self.holds.values()):
            return 0.0
        if f.name not in self.downed:
            if not self.standing_sub_on() or self.has(f, "airborne"):
                return 0.0
            return self.standing_sub_chance(f)
        cap = int(cfg.get("max_per_fight", 0) or 0)      # 0 = no cap: how often is the chance's job
        if cap and sum(self.times("submission", x.name) for x in self.fighters.values()) >= cap:
            return 0.0
        ch = float(cfg.get("chance", 0.03))
        if self.strength(f) < 50:
            ch *= float(cfg.get("weak_mult", 1.5))
        m = cfg.get("match") or {}
        if self.submission_match() and m.get("enabled", True):
            # (since build 249) a submission match: down on the ground is where a hold most often starts
            ch = min(float(m.get("down_max", 0.9)), ch * float(m.get("down_mult", 1.3)))
        return ch

    def _upright_on(self):
        return bool(((self.rules.get("submissions") or {}).get("upright") or {}).get("enabled", True))

    def _upright_word(self, d):
        """'on her feet' or 'sitting up' while she is upright, else '' (a submission's narration note)."""
        if d.name not in self.downed:
            return "" if self.has(d, "airborne") else "on her feet"
        return "sitting up" if self.facing.get(d.name) == "sitting up" else ""

    UPRIGHT_STAGES = [
        {"name": "sagging", "posture": "standing",
         "says": "her legs start to go under it: she sags, knees bending, still on her feet and fighting to stay there"},
        {"name": "on her knees", "posture": "knees",
         "says": "her legs give and she sinks to her knees, sitting back on her heels, still locked in it"},
        {"name": "flat", "posture": "flat",
         "says": "she is forced all the way down, flat on the ground, the hold riding her down"}]

    def upright_stages(self):
        """submissions.upright.stages: the steps a hold bears her down through, in order (rules.json; each a name, a
        posture: standing (still on her feet, off balance a beat), knees (down, sitting up) or flat (lying), and what
        the story is told). Falls back to UPRIGHT_STAGES."""
        st = ((self.rules.get("submissions") or {}).get("upright") or {}).get("stages")
        ok = [x for x in st or () if isinstance(x, dict) and x.get("posture") in ("standing", "knees", "flat")]
        return ok or self.UPRIGHT_STAGES

    def _upright_sub_tick(self):
        """submissions.upright: a submission on a fighter still upright (on her feet, or sitting up) may bear her
        down, a STAGE at a time (upright.stages: sagging, on her knees, flat), the grip kept on: each beat from its
        second, chance base, + per_beat for every beat after that, + weak x her lost strength (0 to 1), never above
        max. skip of the time she drops two stages at once. readjust of the time a drop makes the holder shift her
        grip: the grips lose readjust_mult of their pressure and a beat of their build, but stay on."""
        cfg = (self.rules.get("submissions") or {}).get("upright") or {}
        if not cfg.get("enabled", True):
            return []
        stages = self.upright_stages()
        groups = {}
        for h in self.holds.values():
            # (since build 249, plain_holds: any grip that isn't a grab chest to chest, jaws on her knee or tails
            # round her hip as much as a submission; a pin's own grips never)
            if h.sub or (cfg.get("plain_holds", True) and not h.grab and not h.locked):
                groups.setdefault((h.attacker, h.defender), []).append(h)
        events = []
        for (an, dn), hs in groups.items():
            d = self.get(dn)
            if d.eliminated or self.has(d, "airborne") or self.pinned_by(dn) or an in self.downed:
                continue     # (a holder lying on the ground can't bear anyone down: she is down already)
            key = min(h.id for h in hs)
            sitting = dn in self.downed and self.facing.get(dn) == "sitting up"
            if dn in self.downed and not sitting:
                continue
            # where she is in the stages: kept for this hold; else from how she is now
            mem = d.learned.get("sub_stage") or {}
            if mem.get("hold") == key:
                at = int(mem.get("at", -1))
            else:
                at = next((i for i, x in enumerate(stages) if x["posture"] == "knees"), -1) if sitting else -1
            if at >= len(stages) - 1:
                continue
            beats = max(h.turns_active for h in hs)
            if beats < 2:
                continue     # (locked this beat: she is held up in it a beat before it can bear her down)
            lost = 1.0 - max(0.0, min(1.0, self._health_pct(d) / 100.0))
            ch = float(cfg.get("base", 0.15)) + float(cfg.get("per_beat", 0.08)) * (beats - 2) \
                + float(cfg.get("weak", 0.25)) * lost
            # (since build 249) a grip on a leg she stands on takes it out from under her (leg), the more so the more
            # that part is hurt (per_100_worn for every 100% on the worst gripped part, up to 3)
            legs = ("hind_up", "hind_low") + (("fore_up", "fore_low") if self.body_plan(d) == "quadruped" else ())
            if self.body_plan(d) != "serpent" and any(body_region(h.part) in legs for h in hs):
                ch += float(cfg.get("leg", 0.15))
            worst = max((d.parts[h.part].damage for h in hs if h.part in d.parts), default=0.0)
            ch += float(cfg.get("per_100_worn", 0.1)) * min(3.0, worst / 100.0)
            if any(self.has(d, st) for st in ("wobbly", "dead_leg")):
                ch += float(self._cfg("status_effects").get("legs_gone_bear_down", 0.15))   # (since build 293)
            # a hold that carries her weight (a bear hug lifting her, a shoulder ride) holds her up rather than
            # bearing her down (supporting: those holds' names; support_mult)
            what = hs[0].sub or f"grip on her {hs[0].part.lower()}"
            if hs[0].sub and hs[0].sub in (cfg.get("supporting") or ()):
                ch *= float(cfg.get("support_mult", 0.3))
            ch = min(float(cfg.get("max", 0.6)), ch)
            if not self._chance(ch, f"{poss_word(an)} {what} bearing {dn} down", "she goes DOWN a stage",
                                "she holds where she is"):
                continue
            step = 2 if at + 2 < len(stages) and self._chance(float(cfg.get("skip", 0.2)), f"{dn} dropping two "
                                                              f"stages at once", "she drops FAST", "one stage") else 1
            to = min(len(stages) - 1, at + step)
            stage = stages[to]
            d.learned["sub_stage"] = {"hold": key, "at": to}
            if stage["posture"] == "standing":
                facing = None
                self.set_status(d, "off_balance", 1)
            elif stage["posture"] == "knees":
                facing = "sitting up"
            else:
                facing = "face-down" if self.rng.random() < 0.6 else "face-up"
            if facing and dn not in self.downed:
                self.knock_down(dn, facing=facing, why=f"{dn} was borne down in {poss_word(an)} {what}")
                self._fresh_down.add(dn)
                self._knock_on = []
            elif facing:
                self.facing[dn] = facing
            readjust = self._chance(float(cfg.get("readjust", 0.25)), f"{an} having to shift her grip as {dn} goes "
                                    f"down", "she has to READJUST", "she rides it down")
            if readjust:
                for h in hs:
                    h.power *= float(cfg.get("readjust_mult", 0.7))
                    h.turns_active = max(1, h.turns_active - 1)
            events.append({"type": "sub_collapse", "attacker": an, "defender": dn, "submission": what,
                           "plain": not hs[0].sub,
                           "from": "sitting" if sitting else "standing", "facing": facing, "readjust": readjust,
                           "stage": stage.get("name", ""), "says": stage.get("says", ""), "stage_no": to + 1,
                           "stages": len(stages), "posture": stage["posture"], "skipped": step > 1,
                           "last": to >= len(stages) - 1, "chance": round(ch, 2), "parts": [h.part for h in hs]})
        return events

    def standing_sub_on(self):
        """submissions.match.standing (since build 244): in a submission match an opening for a submission can come
        while she is on her feet too; the holder takes her down into it."""
        m = (self.rules.get("submissions") or {}).get("match") or {}
        return self.submission_match() and bool(m.get("enabled", True)) and bool(m.get("standing", True))

    def standing_sub_chance(self, f):
        """The chance of an opening on her feet (submissions.match): standing_base, + per_100_worn for every 100%
        damage on her worst-hurt part that can still make her tap (up to 3 of those), never above standing_max."""
        m = (self.rules.get("submissions") or {}).get("match") or {}
        spent = set(self.spent_tap_parts(f)) if self._taps_rule() else set()
        worn = max((p.damage for p in f.parts.values() if p.name not in spent), default=0.0)
        ch = float(m.get("standing_base", 0.04)) + float(m.get("per_100_worn", 0.04)) * min(3.0, worn / 100.0)
        # match.late (since build 247): the longer the match has run, the more they go for the hold
        late = m.get("late") or {}
        past = self.turn - int(late.get("after", 30)) if late.get("enabled", True) else 0
        cap = float(m.get("standing_max", 0.2))
        if past > 0:
            ch += float(late.get("per_10", 0.03)) * past / 10.0
            cap = max(cap, float(late.get("max", 0.35)))
        return max(0.0, min(cap, ch))

    @staticmethod
    def _takedown_fits(lies):
        """The takedowns that leave her lying this way (a leg hook puts her down backward, onto her back; a ride
        from behind puts her on her front). None = any."""
        return ({"drag_down", "spin_down", "sweep", "pull_forward", "ride_down"} if lies == "face-down" else
                {"tackle", "shoulder_drive", "trip_back", "sweep", "leg_hook", "hip_throw", "drag_down", "spin_down"}
                if lies == "face-up" else None)

    def _sub_takedown(self, a, d, lands):
        """A submission locked on a fighter on her feet: she is taken down into it first, landing `lands`, by a
        takedown that fits that landing."""
        fits = self._takedown_fits(lands)
        how = self.vary("takedown", tuple(k for k in self.VARIETY["takedown"] if fits and k not in fits))
        self.knock_down(d.name, facing=lands, why=f"{a.name} took {d.name} down into a hold")
        self._fresh_down.add(d.name)
        return {"how": how, "told": False, "hard": False, "hits": [], "into_sub": True}

    def roll_sub_windows(self, open_all=False):
        self.sub_window = {}
        self._sub_open_all = bool(open_all)   # (your direction this beat: a fighter put down during it is open too)
        for f in self.active():
            ch = self.sub_chance(f)
            if ch > 0:
                self.sub_window[f.name] = bool(open_all) or self._chance(ch, f"submission opening on {f.name}",
                                                                         "OPEN", "none")
        return self.sub_window

    def sub_caught(self, a):
        """Is she locked in someone's submission herself? Then she can't lock one of her own on anyone: she has to
        get out of it first (or hurt the holder with what she has free)."""
        a = self.get(a) if isinstance(a, str) else a
        return any(h.defender == a.name and h.sub for h in self.holds.values())

    def _sub_caught(self, a):
        if self.sub_caught(a):
            raise ValueError(f"{a.name} is locked in a submission herself: she can't put one on anyone until she is out "
                             f"of it. Break free, or hurt the one holding her with what she has free")

    def ground_lock_ok(self, name, on=None):
        """submissions.from_ground: True when fighter `name` is down herself and may still lock a submission on
        someone who is down too (she rolls into it, crawls onto her, hooks her from where she lies). Off, or outside
        a submission match while match_only is on, a fighter on the ground has to get up first."""
        fg = (self.rules.get("submissions") or {}).get("from_ground") or {}
        if not fg.get("enabled", True) or (fg.get("match_only", True) and not self.submission_match()):
            return False
        if on is not None and self.get(on).name not in self.downed:
            return False     # (from the ground she can't take down someone still on her feet)
        return name in self.downed

    def sub_stuck(self, d, hs):
        """True when the one in a submission can't hope to break it: she is very weak (submissions.stuck_below % of
        her strength) or the parts it wrenches are ruined (submissions.stuck_damage)."""
        cfg = self.rules.get("submissions") or {}
        ruined = any(h.part in d.parts and d.parts[h.part].damage >= float(cfg.get("stuck_damage", 300)) for h in hs)
        return self.strength(d) < float(cfg.get("stuck_below", 25)) or ruined

    SMALL_JOINT = re.compile(r"(?i)\b(?:paw|hand|wrist|foot|feet|ankle|heel|hoof|talon|claw)s?\b")

    def small_joint(self, part):
        """A wrist or an ankle (a paw, a hand, a foot, a talon): the small joints at the ends of the limbs."""
        return body_region(part) in ("fore_low", "hind_low") and bool(self.SMALL_JOINT.search(str(part)))

    def _small_joint_slip(self, a, d, key, parts, look=""):
        """submissions.small_joints: a hold whose hardest grip is on a wrist or an ankle is harder to lock in: she
        gets her hands on it, but the small joint turns out of the grip before it locks. set_chance of the time it
        locks, more the more hurt the defender is (set_hurt x her lost health). Returns the slip (an action of its
        own) or None when it locks."""
        sj = (self.rules.get("submissions") or {}).get("small_joints") or {}
        if not sj.get("enabled", True) or not parts or not self.small_joint(parts[0]):
            return None
        lost = 1.0 - max(0.0, min(1.0, d.health / max(1.0, d.max_health)))
        ch = min(0.95, float(sj.get("set_chance", 0.5)) + float(sj.get("set_hurt", 0.4)) * lost)
        if self._chance(ch, f"{a.name} locking the {key} on {poss_word(d.name)} {parts[0].lower()}", "it locks",
                        "it slips"):
            return None
        self.__dict__.setdefault("sub_window", {})[d.name] = False    # (the opening is spent on the try)
        return {"type": "sub_slipped", "attacker": a.name, "defender": d.name, "submission": key,
                "part": parts[0], "parts": list(parts), "look": look, "chance": round(ch, 2),
                "manner": self.vary("sub_slip")}

    def sub_break_chance(self, ch, d, hs):
        """The break-free chance against a submission. With submissions.escape on, it comes from her own health (the
        escape.points curve, like a pin's), a little higher when the holder is hurt or the grip light, never under
        escape.floor; off, it is the plain-hold chance x break_mult. Either way x (1 + grow per beat
        it has been on), so the longer it's on the likelier she gets out, up to max_break. Unless she is stuck
        (sub_stuck): then it does not grow (x stuck_mult), and the holder is pointed at a pin or other damage
        instead. Returns (chance, stuck)."""
        cfg = self.rules.get("submissions") or {}
        esc = cfg.get("escape") if isinstance(cfg.get("escape"), dict) else {}
        stuck = self.sub_stuck(d, hs)
        beats = max(h.turns_active for h in hs)
        on = esc.get("enabled", False) and ch > 0      # (asleep or frozen: she can't try at all)
        if on:
            # her own health decides it, as in a pin: easy to wrench out of while she is strong, harder and harder
            # as she is hurt, never quite hopeless
            a = self.get(hs[0].attacker)
            ch = self._curve(esc.get("points") or [[100, 0.45], [0, 0.06]], 100.0 * d.health / max(1.0, d.max_health))
            ch *= 1.0 + float(esc.get("holder_hurt", 0.5)) * (1.0 - max(0.0, min(1.0, a.health / a.max_health)))
            grip = float(self.rules.get("holds", {}).get("break", {}).get("reference_power", 15)) / max(
                1.0, max(h.power for h in hs))
            ch *= max(0.4, min(1.5, grip)) ** float(esc.get("grip_weight", 0.5))
            ch *= self._break_mods(a, d, hs)
        else:
            ch *= float(cfg.get("break_mult", 0.8))
        sj = cfg.get("small_joints") if isinstance(cfg.get("small_joints"), dict) else {}
        if sj.get("enabled", True) and self.small_joint(max(hs, key=lambda h: h.power).part):
            # a wrist or an ankle is easier to twist out of than a knee or a neck: a small grip, and she can turn
            # the whole limb with it (submissions.small_joints.escape_mult)
            ch *= float(sj.get("escape_mult", 1.5))
        if stuck:
            ch *= float(cfg.get("stuck_mult", 0.6))
        else:
            grow = float(esc.get("grow", cfg.get("grow", 0.3)) if on else cfg.get("grow", 0.3))
            ch *= 1.0 + grow * max(0, beats - 1)
        ch = min(float(cfg.get("max_break", 0.85)), ch)
        if on:
            ch = max(float(esc.get("floor", 0.03)), ch)
        return round(ch, 3), stuck

    @staticmethod
    def _curve(points, x):
        """A value from [x, y] points: straight lines between them, flat past either end."""
        pts = sorted((float(p[0]), float(p[1])) for p in points)
        if x <= pts[0][0]:
            return pts[0][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                return y0 + (y1 - y0) * (x - x0) / max(0.001, x1 - x0)
        return pts[-1][1]

    def in_submission(self, name):
        """The submission hold on her, if any: (holder, hold name)."""
        h = next((h for h in self.holds.values() if h.defender == name and h.sub), None)
        return (h.attacker, h.sub) if h else None

    def start_submission(self, attacker, defender, name, flavor="", enforce=False):
        """Lock a submission hold (SUBMISSIONS) on a downed fighter: two or three grips that WRENCH the parts they
        hold every beat, harder each beat (submissions.power / ramp), for at most submissions.max_beats beats, unless
        she breaks it first (the ordinary break-free roll, x submissions.break_mult). It is not a pin: no clock, no
        pass-out; she can't get up while it's on, and the holder can use what she has free on her at point-blank."""
        a, d = self.get_active(attacker), self.get_active(defender)
        cfg = self.rules.get("submissions") or {}
        key = str(name or "").strip().lower()
        # the side the direction names ("hauls her left leg across a root") is the side the grips go on, so the
        # story and the numbers agree; only one side named, or none
        sides = {w.capitalize() for w in re.findall(r"\b(left|right)\b", str(flavor or "").lower())}
        shapes = self.submission_shapes(a.name, d.name, side=sides.pop() if len(sides) == 1 else None)
        if key not in self.SUBMISSIONS:
            raise ValueError(f"no submission hold called '{name}'. Holds: {', '.join(self.SUBMISSIONS)}")
        if enforce:
            if not cfg.get("enabled", True):
                raise ValueError("submission holds are off (rules.json submissions.enabled)")
            if d.name not in self.downed and not (self.standing_sub_on() and not self.has(d, "airborne")):
                raise ValueError(f"{d.name} is on her feet: a submission hold needs her on the ground first")
            if self.pinned_by(d.name):
                raise ValueError(f"{d.name} is pinned: finish the pin or release it before a submission hold")
            if (a.name in self.downed and not self.ground_lock_ok(a.name, d.name)) or self.pinned_by(a.name) \
                    or self.pinning(a.name):
                raise ValueError(f"{a.name} isn't free to lock a hold on anyone right now")
            self._sub_caught(a)
            if self.__dict__.get("sub_window", {}).get(d.name) is not True and not self.__dict__.get("_sub_open_all"):
                raise ValueError(f"no submission opening on {d.name} this beat (they are very rare). Choose another "
                                 f"action")
        if key not in shapes:
            lie = self.facing_of(d.name) if d.name in self.downed else "on her feet"
            raise ValueError(f"{a.name} can't put {d.name} in a {key} as she is ({lie}). She could: "
                             f"{', '.join(shapes) or 'none right now'}")
        s = shapes[key]
        if enforce:
            slip = self._small_joint_slip(a, d, key, [p for p, role, _w in s["contacts"] if role == "main"], s["look"])
            if slip:
                return slip
        takedown = None
        if d.name not in self.downed and s.get("lands") and "standing" not in self.SUBMISSIONS[key]["facing"]:
            takedown = self._sub_takedown(a, d, s["lands"])
        main, second = float(cfg.get("power", 16)), float(cfg.get("second_power", 9))
        ramp, ramp2 = float(cfg.get("ramp", 3)), float(cfg.get("second_ramp", 1))
        contacts = [(p, main if role == "main" else second, ramp if role == "main" else ramp2, w)
                    for p, role, w in s["contacts"]]
        if flavor and ((self.rules.get("holds") or {}).get("invented_check") or {}).get("words", True):
            # (since build 261) the director's words for it grip with a limb the hold doesn't use ("Nerine's twin
            # tails wrap round her leg" for a heel hook turned with her arm and her legs): its own look is told
            said = {lb[0] for m in re.finditer(r"\b(?:" + re.escape(a.name) + r"(?:'s|’s|'|’)|her|its) ((?:(?:twin|both|"
                                               r"left|right|front|hind)\s+)?[a-z]+)", str(flavor), re.I)
                    for lb in [self.grip_limb(a, m.group(1))] if lb}
            real = {lb[0] for _p, w in [(c[0], c[3]) for c in contacts] for lb in [self.grip_limb(a, w)] if lb}
            free = {lb[0] for lb in [self.grip_limb(a, x) for x in re.split(r",| and ", str(s["free"].get(self.body_plan(a), "")
                                                                                       if isinstance(s.get("free"), dict) else ""))] if lb}
            hers = {lb[0] for p, _r, _w in s["contacts"] for lb in [self.grip_limb(a, p)] if lb}
            if said - real - free - hers:
                flavor = ""
        res = self.start_holds(a.name, d.name, contacts, flavor or s["look"], pin=False, enforce=enforce)
        for hid in res.get("hold_ids") or []:
            if hid in self.holds:
                self.holds[hid].sub = key
        self.__dict__.setdefault("sub_window", {})[d.name] = False
        self._count("submission", d.name)
        self._count(f"subname:{key}", a.name)
        res["submission"] = {"name": key, "look": s["look"], "free": s["free"], "strain": s["strain"],
                             "max_beats": int(cfg.get("max_beats", 3)), "from_ground": a.name in self.downed,
                             "upright": self._upright_word(d)}
        if takedown:
            res["takedown"], res["taken_down"] = takedown, True
            res["submission"]["takedown"] = takedown["how"]
        return res

    def _submission_tick(self):
        """A submission hold that has run submissions.max_beats beats is let go: she can't keep it on any longer. One
        that has held submissions.becomes_pin_after beats first becomes a PIN: she is held down in it, the pin's clock
        and pass-out start, and the grips go on wrenching as hard as before, still building (no lighter pin pressure)."""
        cfg = self.rules.get("submissions") or {}
        cap = int(cfg.get("max_beats", 3))
        events, done = [], {}
        after = int(cfg.get("becomes_pin_after", 0) or 0)
        if after > 0 and not self.no_pins():      # (no pins: a submission stays a submission)
            subs = {}
            for h in self.holds.values():
                if h.sub:
                    subs.setdefault((h.attacker, h.defender, h.sub), []).append(h)
            for (a, d, name), hs in subs.items():
                if (max(h.turns_active for h in hs) < after or self.pin_on(d) is not None or self.pinning(a)
                        or self.pinned_by(a) or self.has(self.get(d), "airborne") or self.get(d).eliminated):
                    continue
                key = f"{a}>{d}"
                self.pins[key] = {"attacker": a, "defender": d, "seconds": 0, "fade": 0.0, "beats": 0,
                                  "duration": self.rules.get("pin", {}).get("duration_seconds", 60),
                                  "started_turn": self.turn, "from_submission": name}
                self.since_pin[d] = 0
                self._count("pinned", d)
                self.downed.setdefault(d, 0)
                for h in hs:
                    h.locked, h.sub = name, ""
                events.append({"type": "sub_to_pin", "attacker": a, "defender": d, "submission": name,
                               "beats_held": max(h.turns_active for h in hs), "parts": [h.part for h in hs],
                               "with": [h.with_part for h in hs if h.with_part]})
        for h in list(self.holds.values()):
            if h.sub and h.turns_active >= cap:
                done.setdefault((h.attacker, h.defender, h.sub), []).append(h)
        for (a, d, name), hs in done.items():
            for h in hs:
                self.holds.pop(h.id, None)
            events.append({"type": "hold_end", "released": True, "attacker": a, "defender": d, "submission": name,
                           "hold_ids": [h.id for h in hs], "parts": [h.part for h in hs],
                           "with": [h.with_part for h in hs if h.with_part], "beats_held": max(h.turns_active for h in hs),
                           "reason": f"{a} lets the {name} go: she can't keep it on any longer"})
        return events

    def _free_blow_tick(self, skip_hold_ids=()):
        """Now and then, while a pin or a submission is on, the one holding her gets a quick extra blow in with what
        she has free (a paw, a short jab, a Water Gun at point-blank): holds.free_blow. Rare, light, and nothing to do
        with the punishment for a failed escape. Not on the beat the grip closes."""
        cfg = (self.rules.get("holds") or {}).get("free_blow") or {}
        ch = float(cfg.get("chance", 0) or 0)
        if ch <= 0:
            return []
        pairs = {}
        for h in self.holds.values():
            if h.id in skip_hold_ids:
                continue
            if (h.attacker, h.defender) in {(m, p["defender"]) for p in self.pins.values() for m in self.pin_members(p)}:
                pairs.setdefault((h.attacker, h.defender), "pin")
            elif h.sub:
                pairs.setdefault((h.attacker, h.defender), h.sub)
        events = []
        for (an, dn), what in pairs.items():
            a, d = self.get(an), self.get(dn)
            if a.eliminated or d.eliminated or any(self.has(a, st) for st in ("asleep", "frozen", "paralyzed", "flinched")):
                continue
            r = self.rng.random()
            q = self.quirk(a, "clinch_fighter")
            ch_ = min(0.9, ch * float(q.get("free_blow_mult", 1.6))) if q else ch
            self.note_roll(f"{an} getting a free blow in on {dn} during the {what}", ch_, r,
                           "she does" if r < ch_ else "no")
            if r < ch_ and q:
                self.quirk_moment(a, "clinch_fighter", f"{a.name} works close in like a seasoned brawler: holding on "
                                                       f"with one part of her and striking with another")
            if r >= ch_:
                continue
            usable = [m for m in a.moves if m.get("target") in ("targeted", "spread") and not m.get("charge")
                      and not m.get("carry") and float(m.get("power", 0) or 0) > 0
                      and a.move_uses.get(m["name"], 1) > 0 and a.energy >= self.energy_cost(m)]
            gripped = [h.part for h in self.holds.values() if h.attacker == an and h.defender == dn]
            same, near = neighbor_parts(list(d.parts), self.rng.choice(gripped)) if gripped else ([], [])
            # never the side she is lying on: a fighter pinned face-up has her back against the ground
            hidden = {"face-up": ("back_up", "back_low"), "face-down": ("chest", "belly")}.get(self.facing_of(dn), ())
            # (since build 272) and face-down her throat is against the ground too (the build-271 log: a Water Gun
            # on Nerine's throat while she lay face-down in a chicken wing)
            under = re.compile(r"(?i)throat|stomach|belly|chest") if self.facing_of(dn) == "face-down" else \
                re.compile(r"(?i)\bback\b|tail base") if self.facing_of(dn) == "face-up" else None
            ok_ = lambda x: body_region(x) not in hidden and not (under and under.search(x))
            spots = ([x for x in same + near if x not in gripped and ok_(x)]
                     or [x for x in d.parts if x not in gripped and ok_(x)]
                     or [x for x in d.parts if x not in gripped] or list(d.parts))
            part = self.rng.choice(spots)
            if usable:
                move = self.rng.choice(usable)
                self._use_move(a, move)
                self._spend(a, self.energy_cost(move) * float(cfg.get("energy_share", 0.5)), False, move["name"])
                base = self.move_math(an, dn, move)["effective"]
                label = move["name"]
            else:
                base, label = self.power_for("instant", "solid"), "a quick blow"
            power = round(base * float(cfg.get("power_mult", 0.4)), 2)
            self._source = f"{poss_word(an)} free blow ({label}) during the {what}"
            hit = self._apply_damage(d, part, power)
            events.append({"type": "free_blow", "attacker": an, "defender": dn, "during": what, "move_name": label,
                           "part": hit["part"], "power": power, "hits": [hit], "tags": self._tags([hit])})
        return events

    def choke_kind(self, pinner, with_part="", coil=False):
        """How a grip on the neck or throat puts her out: "both" (jaws or hands closed round it: the windpipe crushed
        and the sides squeezed together), "blood" (the sides of the neck squeezed, the blood to her
        head cut off: quick, a roaring and a greying, often before she is short of air) or "air" (the front of the
        throat pressed in, the windpipe: slow, gasping and burning, the blood cut too in the end). It follows the
        grip and the body doing it: anything wound round her neck, jaws closed over it, and paws, arms or legs that can
        close round the sides (a biped's hands and arms, any fighter's legs locked round it) are a blood choke; a
        forearm, foreleg, knee or weight barred or pressed across the front is the windpipe. A four-legged fighter's
        forepaws and forelegs can't close round the sides, so they press: the windpipe."""
        w = str(with_part or "").lower()
        if coil or re.search(r"\bcoil|\bwrap|wound round|wrapped round|looped round", w):
            return "blood"
        if re.search(r"\bjaws?\b|\bteeth\b|\bfangs?\b|\bbite\b|\bmouth\b", w):
            return "both"                        # jaws close on the front and the sides at once
        f = self.fighters.get(str(pinner or "").lower())
        plan = self.body_plan(f) if f else "biped"
        if plan == "quadruped" and re.search(r"\bfore ?legs?\b|\bforepaws?\b", w) and re.search(
                r"hooked round|hugging|sides of|locked round", w):
            return "blood"                       # a cat's clutch: from her side or on top, forelegs hooked round
        if re.search(r"closed round|throttl|round (?:the|her) throat", w):
            return "both"                        # hands round the throat: the windpipe and the sides together
        if re.search(r"\btalons?\b|\bclaws?\b|\bfeet\b|\bfoot\b", w) and plan == "avian":
            return "both"                        # a bird's grasping foot closes all the way round, like a hand
        rounds = re.search(r"\bround\b|\baround\b|\blocked\b|\bsqueez|\bgrip|\bclamp|\bboth sides\b|\bsides of\b|"
                           r"between her (?:thighs|legs|knees)", w)
        if re.search(r"\bhind ?legs?\b|\bthighs?\b|\blegs\b", w) and rounds:
            return "blood"                       # legs locked round the neck: anyone's legs can do that
        if plan == "quadruped" and re.search(r"\bfore ?(?:paws?|legs?)\b|\bpaws?\b|\bforearm", w):
            return "air"                         # she can only press down with those
        if re.search(r"\bacross\b|\bbarred?\b|\bpress|\bknees?\b|\bweight\b|\bon (?:the|her) throat\b", w) and not rounds:
            return "air"
        if plan in ("biped", "serpent") and (rounds or re.search(r"\bpaws?\b|\bhands?\b|\bfingers\b|\barms?\b", w)):
            return "blood"
        return "air"

    @staticmethod
    def coil_scope(part):
        """What a wrap is round: "body" (chest, belly, back: full constriction, the blood held back, her heart slowing),
        "throat" (neck: her air and blood squeezed), or "limb" (a leg, an arm, a tail, a wing: that limb BOUND)."""
        r = body_region(part)
        return "throat" if r == "neck" else "body" if r in ("chest", "belly", "back_up", "back_low") else "limb"

    def coil_size_cfg(self):
        """holds.coil.size (since build 275), or None when it is off."""
        c = ((self.rules.get("holds") or {}).get("coil") or {}).get("size")
        return c if isinstance(c, dict) and c.get("enabled", True) else None

    def size_m(self, f):
        """Her length or height in metres (holds.coil.size.sizes, by her name, else her species), or None."""
        sizes = (self.coil_size_cfg() or {}).get("sizes") or {}
        for k in (f.name, species_of(f.description, f.appearance)):
            if k and k in sizes:
                return float(sizes[k])
        return None

    def coil_dwarfs(self, attacker, defender):
        """A serpent big enough against her that its coils can't take one of her limbs alone (holds.coil.size):
        a Milotic's body is thicker than a Buizel's arm, so a coil goes round her middle first."""
        cfg = self.coil_size_cfg()
        a, d = self.get(attacker), self.get(defender)
        if not cfg or a is None or d is None or self.body_plan(a) != "serpent":
            return False
        sa, sd = self.size_m(a), self.size_m(d)
        return bool(sa and sd and sa >= float(cfg.get("ratio", 3.0)) * sd)

    MIDDLE_REGIONS = ("belly", "chest", "back_low", "back_up")

    def coil_body_first(self, attacker, defender, contacts, move=None, flavor="", keep_limbs=None, rebind=True):
        """holds.coil.size (since build 275): a coil from a serpent that dwarfs her goes round her MIDDLE first. A
        coil the director put on her limbs (or her neck, or her tail) alone gets a main coil round her belly or chest,
        at the strongest of its pressure, and each limb stays bound in under it limbs_too of the time (else that grip
        goes; rebind False keeps a limb's own words, as a submission's wrench). A coil she already has round her
        middle, or one that already takes it, is left alone. contacts: [(part, power, ramp, with)]. Returns
        (contacts, what changed or "")."""
        cfg = self.coil_size_cfg()
        if not cfg or not contacts or not self.coil_dwarfs(attacker, defender):
            return list(contacts), ""
        a, d = self.get(attacker), self.get(defender)

        def coil(c):
            w = str(c[3] if len(c) > 3 else "")
            # (since build 278) a serpent this much bigger than her has nothing else to grip with: her tail or her
            # tail fan "binding" an arm is a coil too (only her jaws, or her weight bearing down, are not)
            return self.is_coil(move, w, "" if w else flavor) or bool(re.search(r"(?i)\bcoils?\b|\bbody\b", w)) \
                or bool(w.strip() and re.search(r"(?i)\btail", w)
                        and not re.search(r"(?i)\bjaws?\b|teeth|fangs?|mouth|\bbit|weight|press|bulk", w))
        coils = [c for c in contacts if coil(c)]
        if not coils:
            return list(contacts), ""
        middle = lambda p: body_region(d.part(p).name) in self.MIDDLE_REGIONS
        if any(middle(c[0]) for c in coils) or any(
                h.coil and h.attacker == a.name and h.defender == d.name and body_region(h.part) in self.MIDDLE_REGIONS
                for h in self.holds.values()):
            return list(contacts), ""
        taken = {c[0] for c in contacts}
        body = [n for r in ("belly", "chest", "back_low", "back_up") for n in d.parts
                if body_region(n) == r and n not in taken]
        if not body:
            return list(contacts), ""
        top = max(coils, key=lambda c: c[1])
        main = (body[0], top[1], top[2], "her coils, wound round her middle")
        keep = float(cfg.get("limbs_too", 0.5)) if keep_limbs is None else float(keep_limbs)
        rest, gone = [], []
        for c in contacts:
            if c in coils and self.rng.random() >= keep:
                gone.append(c[0])
                continue
            rest.append((c[0], c[1], c[2], "her coils, binding it in under them") if c in coils and rebind else c)
        note = (f"{poss_word(a.name)} body is too big to coil round {poss_word(d.name)} "
                f"{', '.join(str(c[0]).lower() for c in coils)} alone: her coils go round {poss_word(d.name)} middle "
                f"({body[0].lower()})" + (f", and the {', '.join(g.lower() for g in gone)} slips free of them" if gone
                                          else ", binding it in under them"))
        return [main] + rest, note

    def pin_cap(self):
        """How hard a pin's steady pressure (and the punishment for a failed struggle) can bite into a worn-down part:
        pin.pressure_cap {"mult", "health_mult"} (null = no limit). A pin wears her down; it doesn't wreck her."""
        c = self.rules.get("pin", {}).get("pressure_cap")
        return c if isinstance(c, dict) and c.get("enabled", True) else None

    def sub_cap(self):
        """How hard a submission's wrench can bite into a worn-down part: submissions.damage_cap {"mult",
        "health_mult"}. Looser than a pin's (a wrench is meant to hurt), but it can't tear a ruined part apart."""
        c = (self.rules.get("submissions") or {}).get("damage_cap")
        return c if isinstance(c, dict) and c.get("enabled", True) else None

    STANCES = {"protect": "protecting", "counter": "countering", "mirror": "mirroring"}

    def weather_mult(self, mtype):
        """Rain strengthens Water and dampens Fire; sun the other way round (rules.json weather)."""
        w = getattr(self, "weather", {}) or {}
        cfg = (self.rules.get("weather") or {}).get(w.get("kind") or "", {})
        m = float((cfg.get("type_mult") or {}).get(mtype, 1.0))
        return (f"in the {cfg.get('word', w.get('kind'))}", m) if w and m != 1.0 else None

    def _self_move(self, a, d, move, flavor, energy_before):
        """Protect/Detect, Counter/Mirror Coat (a stance held until the next attack on her, or for a beat or two),
        or a weather move (Rain Dance, Sunny Day, Hail: the whole arena, for rules.json weather.beats)."""
        res = {"type": "instant", "attacker": a.name, "defender": d.name, "defenders": [d.name], "self_move": True,
               "uses_left": a.move_uses.get(move["name"]), "energy": [round(energy_before), round(a.energy)],
               "flavor": flavor, "move": self.move_math(a.name, d.name, move), "hit_count": 0, "hits": [], "tags": []}
        self.involved.add(a.name)
        if move.get("weather"):
            kind = move["weather"]
            beats = int((self.rules.get("weather") or {}).get("beats", 5))
            self.weather = {"kind": kind, "beats": beats, "by": a.name}
            res["weather"] = {"kind": kind, "beats": beats}
            return res
        stance = self.STANCES.get(move.get("stance") or "protect", "protecting")
        cfg = self.rules.get("stances") or {}
        streak = (a.learned.get("stance_streak") or 0) if stance == "protecting" else 0
        ch = float(cfg.get("protect_chance", 1.0)) * float(cfg.get("repeat_mult", 0.5)) ** streak
        ok = self._chance(ch, f"{poss_word(a.name)} {move['name']} holding", "it holds", "it fails") if ch < 1 else True
        if stance == "protecting":
            a.learned["stance_streak"] = streak + 1 if ok else 0
        if ok:
            a.learned["stance_move"] = move["name"]
            self.set_status(a, stance, 1)   # through the next beat (a status set this beat doesn't tick yet)
        res["stance"] = {"kind": stance, "ok": ok, "chance": round(ch, 2)}
        return res

    def _guarded(self, a, d, move):
        """She is behind Protect/Detect: this attack (whatever it is) stops against it and nothing lands."""
        if not self.has(d, "protecting") or move.get("target") == "self":
            return None
        d.status.pop("protecting", None)
        self._attacked(a.name, [d.name], landed=False)
        return {"type": "instant", "attacker": a.name, "defender": d.name, "defenders": [d.name], "flavor": "",
                "move": self.move_math(a.name, d.name, move), "hit_count": 0, "hits": [], "tags": [],
                "energy": [round(a.energy), round(a.energy)], "protected": d.learned.get("stance_move") or "Protect",
                "missed": True}

    def _reflect(self, a, d, move, math):
        """Counter (close blows) or Mirror Coat (blasts and beams): she takes the hit and sends it back harder onto
        the attacker's front (rules.json stances.reflect_mult). Used up by the first attack of the right kind."""
        ranged = self.is_ranged(move)
        stance = "mirroring" if ranged else "countering"
        if not self.has(d, stance) or move.get("target") in ("status", "self"):
            return None
        d.status.pop(stance, None)
        cfg = self.rules.get("stances") or {}
        power = round(math["effective"] * float(cfg.get("reflect_mult", 1.5)) / 2, 2)
        reach = [x for x in a.parts if body_region(x) in ("head", "neck", "chest", "shoulder", "belly")] or list(a.parts)
        self.rng.shuffle(reach)
        mine, self._source = self._source, f"{poss_word(d.name)} {'Mirror Coat' if ranged else 'Counter'}"
        hits = [self._apply_damage(a, x, power) for x in reach[:2]]
        self._source = mine
        self.involved.add(d.name)
        return {"by": d.name, "kind": "Mirror Coat" if ranged else "Counter", "power": power, "hits": hits}

    GUARD_KEYS = {"biped": ("forearm", "upper arm", "arm", "paw"), "quadruped": ("lower foreleg", "upper foreleg", "horn"),
                  "avian": ("wing",), "serpent": ("upper tail", "tail", "coil", "lower back", "upper back")}

    def _guard_roll(self, a, d, move, target):
        """Now and then (moves.guard) the one being attacked gets something in the way instead of dodging:
        BLOCK, catching a close blow on a forearm, a foreleg, a wing, her horn or her coils (it lands there, much
        lighter), or DEFLECT, turning it aside so it lands on nothing and the attacker is left OFF BALANCE for a beat
        (a beam or a blast is now and then batted aside too). Only a fighter on her feet, free, and able to see it
        coming; the fresher she is, the likelier. Returns the guard, or None."""
        cfg = (self.rules.get("moves") or {}).get("guard") or {}
        if not cfg.get("enabled", True) or move.get("target") in ("status", "self", "hold", "whole_body"):
            return None
        if a.name in self.lucky:
            return None   # /play dice free: nothing gets in the way of her attacks
        if any({h.attacker, h.defender} == {a.name, d.name} for h in self.holds.values()):
            return None   # locked together in a hold or a submission: nothing to put in the way, nowhere to step
        if self.pinning(d.name):
            return None   # her limbs are busy holding someone down
        if (d.name in self.downed or self.pinned_by(d.name) or self.grab_between(a.name, d.name)
                or any(h.defender == d.name for h in self.holds.values())
                or any(self.has(d, st) for st in ("asleep", "frozen", "paralyzed", "flinched", "constricted", "airborne",
                                                  "staggered"))
                or (self.pressed.get(d.name) or {}).get("surface")):
            return None       # (staggering, she is busy finding her feet: no guard comes up)
        fresh = 0.4 + 0.6 * max(0.0, min(1.0, self.strength(d) / 100))
        ranged = self.is_ranged(move)
        plan = self.body_plan(d)
        keys = self.GUARD_KEYS.get(plan, ())
        guards = [p for p in d.parts.values() if any(k in p.name.lower() for k in keys) and p.damage < 300]
        block_p = 0.0 if ranged or target != "targeted" or not guards else float(cfg.get("block_chance", 0.07)) * fresh
        defl_p = float(cfg.get("deflect_ranged_chance", 0.03) if ranged else cfg.get("deflect_chance", 0.04)) * fresh
        if self.has(d, "off_balance") or self.has(d, "stiff"):
            block_p, defl_p = block_p * 0.5, defl_p * 0.5
        r = self.rng.random()
        if r < block_p:
            self.note_roll(f"{d.name} getting a guard up against {poss_word(a.name)} {move['name']}", block_p, r, "BLOCKED")
            g = max(guards, key=lambda p: (p.resistance - p.damage / 4, self.rng.random()))
            return {"kind": "block", "part": g.name, "share": float(cfg.get("block_share", 0.45)), "chance": round(block_p, 4),
                    "manner": self.rng.choice(("braced", "crossed", "caught", "turned into"))}
        if r < block_p + defl_p:
            self.note_roll(f"{d.name} turning {poss_word(a.name)} {move['name']} aside", defl_p, r - block_p, "DEFLECTED")
            if not ranged:
                self.set_status(a, "off_balance", 1)
                getattr(self, "_overbalanced", set()).discard(a.name)
            how = (self.rng.choice(("a burst of her own power", "a sweep of her arm or paw", "a twist of her whole body"))
                   if ranged else self.rng.choice(("a paw or forearm across it", "a shoulder turned into it",
                                                   "a sidestep and a shove")))
            return {"kind": "deflect", "ranged": ranged, "how": how, "off_balance": not ranged, "chance": round(defl_p, 4)}
        return None

    def vulnerable(self, a, d, move):
        """Caught open (moves.vulnerable): a blow on someone who has no chance to roll with it, twist away or soften
        it lands harder. Only the biggest one counts. Returns (label, multiplier) or None."""
        cfg = (self.rules.get("moves") or {}).get("vulnerable") or {}
        if not cfg.get("enabled", True) or not move or move.get("target") in ("status", "self", "hold") or a is d:
            return None
        opts = []
        if (getattr(self, "_juggle", None) or {}).get("who") == d.name:
            opts.append(("caught helpless in the air", float(cfg.get("juggled", 1.3))))
        if getattr(self, "_feint_open", None) == d.name:
            opts.append(("caught open by the feint", float(cfg.get("feinted", 1.25))))
        # in a pummel every blow gets it, so each gets a share of it (like down_pummel): pummel_share of the bonus
        share = float(cfg.get("pummel_share", 0.5)) if getattr(self, "_pummel_now", False) else 1.0
        for st, label, key, dflt in (("doubled_over", "doubled over in pain", "doubled_over", 1.2),
                                     ("off_balance", "caught off balance", "off_balance", 1.2),
                                     ("staggered", "caught staggering", "staggered", 1.2),
                                     ("dazed", "dazed, slow to react", "dazed", 1.15),
                                     ("flinched", "caught flinching", "flinched", 1.15)):
            if self.has(d, st):
                opts.append((label, 1 + (float(cfg.get(key, dflt)) - 1) * share))
        holders = {h.attacker for h in self.holds.values() if h.defender == d.name}
        locked = any(h.defender == d.name and h.sub for h in self.holds.values())
        if locked and not self.pinned_by(d.name):
            opts.append(("locked in a submission hold, nothing free to cover up with", float(cfg.get("submission", 1.25))))
        elif holders and not getattr(self, "_pummel_now", False) and not self.pinned_by(d.name):
            opts.append(("held, can't cover up", float(cfg.get("held", 1.1))))
        if d.name in self.downed and not self.pinned_by(d.name) and not self.is_ranged(move):
            # a pummel on the ground lands blow after blow: each one gets its own, smaller bonus (down_pummel)
            opts.append(("down, nowhere to roll with it",
                         float(cfg.get("down_pummel", 1.04) if getattr(self, "_pummel_now", False) else cfg.get("down", 1.1))))
        ro = (getattr(self, "_rock_open", None) or {}).get(d.name)
        if ro and ro[0] == self.turn:
            # the blow before this one, this same beat, turned her head or locked her rigid: a sliver of an opening
            opts.append((ro[1], float(cfg.get("rigid" if ro[2] else "rocked", 1.1 if ro[2] else 1.05))))
        opts = [o for o in opts if o[1] != 1.0]
        return max(opts, key=lambda o: o[1]) if opts else None

    def _feint(self, a, d, move):
        """A feint before the real blow (moves.feint): it costs her a little breath. If the defender bites, her dodge is
        spent on the fake: no dodge, no clash, no guard, and the real blow lands on her caught open. A fighter who has
        seen feints from her before bites less often."""
        cfg = (self.rules.get("moves") or {}).get("feint") or {}
        if not cfg.get("enabled", True) or move.get("target") in ("status", "self", "hold"):
            return None
        a.energy = max(0.0, a.energy - float(cfg.get("energy", 4)))
        seen = int(d.learned.get("feints_seen", {}).get(a.name, 0))
        s = max(0.0, min(1.0, self.strength(d) / 100))
        ch = float(cfg.get("chance", 0.55)) * (1.25 - 0.5 * s) * (float(cfg.get("seen_mult", 0.8)) ** seen)
        if (d.learned.get("wary") or {}).get(f"{a.name}|{move['name']}"):
            ch *= float(((self.rules.get("learning") or {}).get("wary") or {}).get("feint_mult", 1.3))   # jumpy
        if any(self.has(d, st) for st in ("asleep", "frozen", "paralyzed")) or d.name in self.downed:
            ch = 0.0      # nothing to fool: she can't move to answer it anyway
        ch = max(0.0, min(0.9, ch))
        bit = ch > 0 and self._chance(ch, f"{d.name} biting on {poss_word(a.name)} feint", "she bites", "she reads it")
        d.learned.setdefault("feints_seen", {})[a.name] = seen + 1
        if bit:
            self._feint_open = d.name
        return {"bit": bit, "chance": round(ch, 3)}

    def _last_stand(self, a, move):
        """Once a fight, a nearly spent fighter may put everything she has left into one blow (moves.last_stand)."""
        cfg = (self.rules.get("moves") or {}).get("last_stand") or {}
        if (not cfg.get("enabled", True) or a.learned.get("last_stand_used") or move.get("target") in ("status", "self", "hold")
                or self.strength(a) >= float(cfg.get("below_strength", 15))):
            return None
        if not self._chance(float(cfg.get("chance", 0.5)), f"{a.name} throwing everything into one last blow",
                            "LAST STAND", "no"):
            return None
        a.learned["last_stand_used"] = True
        a.learned["last_stand_turn"] = self.turn    # (low_health.last_stand: she is wide open the beat after it)
        return a.name

    def guarded_wound(self, d):
        """A badly hurt fighter shields her worst part without thinking (moves.guarding_wound): (part, its side), or
        None. Blows there land a little lighter; the other side of her is open."""
        cfg = (self.rules.get("moves") or {}).get("guarding_wound") or {}
        if not cfg.get("enabled", True) or d.name in self.downed or self.pinned_by(d.name) \
                or any(h.defender == d.name for h in self.holds.values()):
            return None      # held: she has nothing free to cover it with
        if self.strength(d) >= float(cfg.get("below_strength", 60)):
            return None
        worst = max(d.parts.values(), key=lambda p: p.damage)
        if worst.damage < float(cfg.get("at_damage", 150)):
            return None
        return worst.name, _side(worst.name)

    FRONT_GUARD = ("chest", "belly", "neck")
    BACK_GUARD = ("back_up", "back_low")

    def left_open(self, guarded, part):
        """Is `part` on the side she leaves open while she shields `guarded`? The other side for a left or right part;
        her back while she curls over her chest, belly or throat; her front while she shields her back."""
        side = _side(guarded)
        if side:
            return bool(_side(part)) and _side(part) != side
        g, r = body_region(guarded), body_region(part)
        if g in self.FRONT_GUARD:
            return r in self.BACK_GUARD
        if g in self.BACK_GUARD:
            return r in self.FRONT_GUARD
        return False

    def open_side_word(self, guarded):
        side = _side(guarded)
        if side:
            return {"left": "right", "right": "left"}[side]
        g = body_region(guarded)
        return "back" if g in self.FRONT_GUARD else "front" if g in self.BACK_GUARD else ""

    # which way a blow sends her: away from the side it lands on, back from the front, forward from behind
    _REEL_DIR = {"head": "back", "neck": "back", "chest": "back", "belly": "back", "shoulder": "back", "fore_up": "back",
                 "back_up": "forward", "back_low": "forward", "hind_up": "sideways", "hind_low": "sideways",
                 "fore_low": "sideways", "tail": "sideways"}

    def _blow_kind(self, move):
        """How a move moves a body: blunt (pushes her away), claw (twists her away from the rake), bite (wrenches her
        toward the biter), blast (drives her back along its line), shock (locks her rigid), fire (she recoils from the
        heat), cold (she flinches and stiffens), mind (the head snaps back with nothing touching it)."""
        name = f"{move.get('name') or ''} {move.get('about') or ''}".lower()
        t = move.get("type")
        if re.search(r"bite|fang|crunch|jaws", name):
            return "bite"
        if re.search(r"slash|claw|swipe|scratch|rake|cut|cutter|scythe", name):
            return "blade" if self.is_ranged(move) else "claw"     # a blade thrown from afar (Psycho Cut, Air Slash)
        if t == "Electric":
            return "shock"
        if t == "Psychic" and self.is_ranged(move):
            return "mind"
        if t == "Fire":
            return "fire"
        if t == "Ice" and self.is_ranged(move):
            return "cold"
        return "blast" if self.is_ranged(move) else "blunt"

    def _stumble(self, a, d, move, hits):
        """How a hard blow moves her body, fitted to the blow and to where she is. Standing and free: her head snaps
        round with a blow to the head and she can be knocked a step or more the way the blow was going (STAGGERED for
        a beat: slower to dodge, the next blow lands harder, her own blows weaker), or just rocked where she stands.
        Down, held or pinned: she can't be knocked anywhere, but the blow still jars her where she is (rocked).
        Returns a staggered status record, a rocked record, or None. moves.stumble."""
        cfg = (self.rules.get("moves") or {}).get("stumble") or {}
        if not cfg.get("enabled", True) or not move or move.get("target") in ("status", "self", "hold"):
            return None
        mine = [h for h in hits if h.get("defender", d.name) == d.name]
        if not mine or self.has(d, "airborne"):
            return None
        big = max(mine, key=lambda h: h.get("damage_taken", 0))
        dmg, low = float(big.get("damage_taken", 0)), float(cfg.get("min_damage", 40))
        reg = body_region(big["part"])
        away = {"left": "right", "right": "left"}.get(_side(big["part"]))
        kind = self._blow_kind(move)
        held = self.pinned_by(d.name) or any(h.defender == d.name for h in self.holds.values())
        holding = any(h.attacker == d.name for h in self.holds.values())
        if d.name in self.downed or held or holding or dmg < low or kind in ("shock", "cold", "mind"):
            return self._rocked(a, d, big, dmg, cfg, reg, away, kind, held, holding)
        ch = (float(cfg.get("base", 0.12)) + float(cfg.get("per_damage", 0.004)) * (dmg - low)
              + float(cfg.get("weak", 0.25)) * (1 - max(0.0, min(100.0, self.strength(d))) / 100))
        ch *= float((cfg.get("kind_mult") or {}).get(kind, {"blunt": 1.3, "blast": 1.2, "claw": 0.7, "blade": 0.7, "bite": 0.5,
                                                            "fire": 0.6}.get(kind, 1.0)))
        ch *= float((cfg.get("region_mult") or {}).get(reg, {"head": 1.3, "hind_low": 1.2, "fore_low": 0.4,
                                                             "tail": 0.3}.get(reg, 1.0)))
        if self.has(d, "staggered"):
            ch *= float(cfg.get("again_mult", 1.3))     # still staggering from the last one: easier to send again
        # what she stands on: legs that are badly hurt can't brace against it, and a hurt place gives more
        legw = self._leg_worst(d)
        ch *= (float(cfg.get("bad_legs_mult", 1.35)) if legw >= float(cfg.get("bad_legs_at", 150)) else
               float(cfg.get("sore_legs_mult", 1.15)) if legw >= float(cfg.get("sore_legs_at", 90)) else 1.0)
        if float(big.get("damage_before", 0)) >= float(cfg.get("bad_legs_at", 150)):
            ch *= float(cfg.get("hurt_spot_mult", 1.15))
        ch /= self.trait(d, "toughness")
        if not self._chance(min(float(cfg.get("max", 0.75)), ch), f"{d.name} knocked staggering by the blow to her {big['part']}",
                            "she stumbles", "she holds her ground"):
            if self.quirk(d, "unshakeable") and dmg >= 1.5 * low:
                self.quirk_moment(d, "unshakeable", f"a blow that would have sent another fighter reeling barely moves "
                                                    f"{d.name}: her sheer bulk and composure take it")
            return self._rocked(a, d, big, dmg, cfg, reg, away, kind, held, holding)
        if kind == "bite":
            way = f"toward {a.name}, dragged by the jaws"
        elif kind == "blast":
            way = "backward along the line of the blast"
        elif kind == "fire":
            way = "back from the heat"
        elif away and reg not in ("back_up", "back_low"):
            way = f"to her {away}"
        else:
            way = {"back": "backward", "forward": "forward", "sideways": "sideways"}[self._REEL_DIR.get(reg, "back")]
        head = None
        if reg == "head":
            head = ("her head is wrenched round with the bite" if kind == "bite" else
                    f"her head snaps round to the {away}" if away else "her head snaps back")
        elif reg == "neck":
            head = f"her head whips {'round to the ' + away if away else 'back'} with it"
        tiers = ("a single step", "two or three steps", "several steps, close to going down")
        t = 0 if dmg < low * 1.6 or reg in ("fore_low", "tail") else 1 if dmg < low * 2.6 else 2
        s = self.strength(d)
        if s < float(cfg.get("weak_below", 30)) or legw >= float(cfg.get("bad_legs_at", 150)):
            t += 1        # worn out, or on legs that won't brace: the same blow carries her further
        elif s > float(cfg.get("strong_above", 75)):
            t -= 1        # strong and fresh: she catches it sooner
        steps = tiers[max(0, min(2, t))]
        self.set_status(d, "staggered", 1)
        return {"fighter": d.name, "status": "staggered", "beats": 1,
                "stumble": {"part": big["part"], "way": way, "head": head, "steps": steps,
                            "legs": reg in ("hind_low", "hind_up"), "kind": kind, "strength": round(s),
                            "bad_legs": legw >= float(cfg.get("bad_legs_at", 150))}}

    def _side_spill(self, d, move, hits, res):
        """moves.side_spill (since build 278): a big blunt blow (or a blast) on her shoulder or upper arm that
        really moves her (staggers her, launches her, drives her back in a charge, or rocks her hard) carries on
        into her side: the ribs on that side take part of it (power x power_mult), and the flank under them
        flank_chance of the time. Only a body with ribs or flanks; bites, claws and blades stop where they land."""
        cfg = (self.rules.get("moves") or {}).get("side_spill") or {}
        if not cfg.get("enabled", True) or not move or move.get("target") in ("status", "self", "hold"):
            return []
        mine = [h for h in hits if h.get("defender", d.name) == d.name and h.get("part")]
        if not mine or self._blow_kind(move) not in ("blunt", "blast"):
            return []
        big = max(mine, key=lambda h: h.get("damage_taken", 0))
        dmg = float(big.get("damage_taken", 0))
        if body_region(big["part"]) not in ("shoulder", "fore_up") or dmg < float(cfg.get("min_damage", 30)):
            return []
        rocked_hard = bool(res.get("rocked")) and dmg >= 1.5 * float(cfg.get("min_damage", 30))
        if not (res.get("moved") == "stagger" or res.get("auto_launch") or res.get("charge") or rocked_hard):
            return []
        side = _side(big["part"])
        hit = {h["part"] for h in mine}
        ribs = [p for p in d.parts if re.search(r"\bribs?\b", p, re.I) and _side(p) == side and p not in hit]
        flank = [p for p in d.parts if re.search(r"\bflanks?\b", p, re.I) and _side(p) == side and p not in hit]
        if not ribs and not flank:
            return []
        power = float(big.get("power") or 0) * float(cfg.get("power_mult", 0.35))
        if power <= 0:
            return []
        out = []
        keep, self._source = self._source, f"{poss_word(d.name)} side, the blow carrying on into it"
        for p in (ribs or flank)[:1]:
            out.append(self._apply_damage(d, p, power))
        if ribs and flank and self.rng.random() < float(cfg.get("flank_chance", 0.5)):
            out.append(self._apply_damage(d, flank[0], power * 0.7))
        self._source = keep
        for h in out:
            h["side_spill"] = True
        return out

    def _leg_worst(self, d):
        """The worst-hurt part she stands on (her hind legs; a four-legged fighter's forelegs too)."""
        feet = ("hind_up", "hind_low") + (("fore_low",) if self.body_plan(d) == "quadruped" else ())
        return max([p.damage for p in d.parts.values() if body_region(p.name) in feet] or [0.0])

    def _rocked(self, a, d, big, dmg, cfg, reg, away, kind, held=False, holding=False):
        """Less than a stumble: the blow turns her head or moves her body with it, and her feet (or the rest of her)
        stay where they are. Only how it looks (no status); rolled so not every hit gets it (rock_chance)."""
        if dmg < float(cfg.get("rock_from", 15)) or (reg in ("tail", "fore_low") and kind not in ("shock",)):
            return None
        s = self.strength(d)
        rc = float(cfg.get("rock_chance", 0.55))
        if s > float(cfg.get("strong_above", 75)) and dmg < float(cfg.get("min_damage", 40)):
            rc *= 0.7     # strong and fresh: a middling blow doesn't move her much
        elif s < float(cfg.get("weak_below", 30)) or self._leg_worst(d) >= float(cfg.get("bad_legs_at", 150)):
            rc = min(0.9, rc * 1.35)   # worn out, or on bad legs: even lighter blows move her
        rc /= self.trait(d, "toughness")
        if not self._chance(rc, f"{d.name} rocked by the blow to her {big['part']}",
                            "it moves her", "she takes it where she is"):
            return None
        down = d.name in self.downed
        side = f" to the {away}" if away else ""
        if kind == "shock":
            how = "her whole body jerks rigid, limbs locking straight for an instant, and lets go"
        elif kind == "mind":
            how = "her head snaps back as if struck, with nothing touching her"
        elif kind == "cold":
            how = "she flinches in on herself from the cold, muscles going tight around the spot"
        elif kind == "fire":
            how = "she recoils from the heat, twisting the burning spot away"
        elif kind == "bite" and (held or down):
            how = "the jaws wrench at her and her body goes with them as far as it can"
        elif kind in ("claw", "blade") and (held or down):
            how = (f"she twists{side} away from the {'cut' if kind == 'blade' else 'rake'}, as far as she can"
                   + (" against the ground" if down else ""))
        elif held:
            how = (f"her head is knocked{side or ' back'} against the ground, and she can't go with it any further"
                   if down and reg in ("head", "neck") else
                   f"her head snaps{side or ' back'} as far as the hold lets it, and the holder feels it" if reg in ("head", "neck")
                   else "her body jerks in the hold with the blow, and the grip on her has to take it")
        elif down:
            how = (f"her head is knocked{side or ' back'} against the ground" if reg in ("head", "neck") else
                   "it shoves her a little way along the ground where she lies" if kind in ("blunt", "blast") else
                   "her body jerks where she lies")
        elif kind == "bite":
            how = {"drag": f"the jaws drag her toward {a.name} before they let go",
                   "shake": "the jaws shake her where she stands, once, hard, and open",
                   "yank": f"the bite yanks her off her line, half a step toward {a.name}, and lets go",
                   "wrench_free": "she wrenches back against the teeth and her body jerks with them as she pulls free",
                   }[self.vary("bite_rock")]
        elif kind in ("claw", "blade"):
            how = f"she twists{side or ''} away from the {'cut' if kind == 'blade' else 'rake'} as it goes across her"
        elif holding:
            how = f"it rocks her{side or ' back'}, but she keeps her grip"
        elif reg == "head":
            how = f"her head turns{side} with the blow" if away else "her head rocks back"
        elif reg == "neck":
            how = f"her head is jerked{side or ' back'} and her shoulders follow"
        elif reg in ("hind_low", "hind_up"):
            how = "that leg buckles a little and her weight shifts off it, but it holds"
        elif reg in ("back_up", "back_low"):
            how = "it pushes her forward a little, her back arching away from it"
        elif kind == "blast":
            how = "it pushes her back on her heels, her feet bracing against it"
        else:
            how = (f"her body twists away{side} with it" if away else
                   "it rocks her back on her heels" if reg in ("chest", "belly") else "it leans her body away from it")
        if not down and not held and kind not in ("shock", "mind"):
            how += (", more than a blow that size should" if s < float(cfg.get("weak_below", 30)) else
                    ", and she is square again at once" if s > float(cfg.get("strong_above", 75)) else "")
        if not down and not held and (kind == "shock" or s <= float(cfg.get("strong_above", 75))):
            if not hasattr(self, "_rock_open"):
                self._rock_open = {}
            self._rock_open[d.name] = (self.turn, "caught locked rigid" if kind == "shock" else
                                       "caught with her head still turned", kind == "shock")
        return {"fighter": d.name, "part": big["part"], "how": how, "kind": kind, "strength": round(s),
                "where": "held" if held else "down" if down else "holding" if holding else "standing"}

    def _jolts(self, d, hits, move=None, a=None):
        """What a hard hit can do beyond the damage: the wind knocked out of her (chest or belly), dazed (head), or
        doubled over by a blow on a part that was already devastated (moves.jolts). Returns status records."""
        cfg = (self.rules.get("moves") or {}).get("jolts") or {}
        if not cfg.get("enabled", True):
            return []
        head_on = bool(self.head_cfg())
        out = self._head_jolts(d, hits, move, a) if head_on else []
        out += self._body_jolts(d, hits, move)
        for h in sorted(hits, key=lambda h: -h.get("damage_taken", 0)):
            if h.get("defender", d.name) != d.name or h.get("damage_taken", 0) < float(cfg.get("min_damage", 40)):
                continue
            reg = body_region(h["part"])
            for st, ok, key, dflt in (
                    ("breathless", reg in ("chest", "belly") and h.get("damage_after", 0) >= 90, "breathless", 0.3),
                    ("dazed", reg == "head" and h.get("damage_after", 0) >= 150 and not head_on, "dazed", 0.25),
                    ("doubled_over", h.get("damage_before", 0) >= 300, "doubled_over", 0.15)):
                if not ok or self.has(d, st) or any(x["status"] == st for x in out):
                    continue
                if self._chance(float(cfg.get(key, dflt)), f"{d.name} {st.replace('_', ' ')} by the blow to her {h['part']}",
                                st.replace("_", " "), "no"):
                    self.set_status(d, st, 1)
                    out.append({"fighter": d.name, "status": st, "beats": 1})
        return out

    # (since build 293, moves.head) what a blow to the head can do, from a passing rattle to a concussion
    HEAD_STATUSES = ("rattled", "dazed", "stunned", "wobbly", "seeing_double", "eyes_watering", "ears_ringing",
                     "jaw_rattled", "whiplash", "concussed")

    def head_cfg(self):
        """moves.head (since build 293), or None when it is off."""
        c = (self.rules.get("moves") or {}).get("head")
        return c if isinstance(c, dict) and c.get("enabled", True) else None

    @staticmethod
    def head_spot(part):
        """Where on the head a part is: "jaw" (jaw, chin, muzzle, beak: the knockout button), "nose", "ear",
        "side" (cheek, temple), or "crown" (the rest of the head)."""
        p = str(part).lower()
        return ("jaw" if re.search(r"jaw|chin|muzzle|beak|snout|mouth", p) else "nose" if "nose" in p else
                "ear" if re.search(r"\bears?\b", p) else "side" if re.search(r"cheek|temple", p) else "crown")

    def _head_jolts(self, d, hits, move=None, a=None):
        """moves.head: the hardest blow to her head this time rolls ONE of rattled, dazed or stunned (stunned brings
        wobbly legs after it), by how hard it landed, what landed (a blunt blow far more than a cut), where (the jaw
        most of all), whether her head was held and couldn't roll with it, and her toughness, a surge, a concussion
        already. Then what that spot does besides: a hit on the nose waters her eyes, on an ear rings it, on the jaw
        rattles her bite; a dazing or a stun may double her sight; a held head wrenched by the blow gets whiplash.
        Enough of it in one fight (head damage, or dazings and stuns) leaves her concussed for the rest of it.
        Returns status records like _jolts'."""
        cfg = self.head_cfg()
        if not cfg:
            return []
        scale0 = float((self.rules.get("damage") or {}).get("damage_scale", 3) or 3) / 3.0
        heads = [h for h in hits if h.get("defender", d.name) == d.name and body_region(h["part"]) == "head"
                 and float(h.get("damage_taken", 0)) >= float(cfg.get("min_damage", 15)) * scale0]
        if not heads:
            return []
        h = max(heads, key=lambda x: float(x.get("damage_taken", 0)))
        spot = self.head_spot(h["part"])
        # (the size of a blow against the damage scale: at /scale 15 every hit is five times the damage of one at 3)
        scale_ = float((self.rules.get("damage") or {}).get("damage_scale", 3) or 3)
        sev = min(float(cfg.get("max_size", 2.0)),
                  float(h.get("damage_taken", 0)) / max(1.0, float(cfg.get("size", 20)) * scale_))
        import blocks as _bl
        kinds = _bl.kind_of(str((move or {}).get("name", "")), str((move or {}).get("about", ""))) if move else set()
        m = cfg.get("mult") or {}
        mod = (float(m.get("blunt", 1.3)) if kinds & {"punch", "charge", "tail", "throw", "horn"} else
               float(m.get("sharp", 0.7)) if kinds & {"claw", "bite", "talon", "beak"} else
               float(m.get("beam", 0.85)) if "beam" in kinds else 1.0)
        held_head = any(x.defender == d.name and body_region(x.part) in ("head", "neck") for x in self.holds.values())
        if held_head:
            mod *= float(m.get("held", 1.3))     # she can't roll with it: the whole of it goes into her head
        mod /= max(0.3, self.trait(d, "toughness"))
        if self.has(d, "adrenaline"):
            mod *= float(m.get("adrenaline", 0.6))
        if self.has(d, "concussed"):
            mod *= float(m.get("concussed", 1.5))
        ch = cfg.get("chance") or {}
        stun = float(ch.get("stunned", 0.08)) * sev * mod * (float(m.get("jaw_stun", 1.8)) if spot == "jaw" else
                                                             float(m.get("side_stun", 1.2)) if spot == "side" else 1.0)
        if self.has(d, "dazed") or self.has(d, "rattled"):
            stun += float(ch.get("stun_when_dazed", 0.25)) * sev   # the second one, before the first has cleared
        daze = float(ch.get("dazed", 0.28)) * sev * mod
        rattle = float(ch.get("rattled", 0.5)) * sev * mod
        stun, daze, rattle = min(0.9, stun), min(0.9, daze), min(0.95, rattle)
        out, dur = [], cfg.get("beats") or {}

        def put(st, beats, look=None):
            beats = int(beats)
            if beats <= 0 or self.has(d, st) and int(d.status.get(st, 0)) >= beats:
                return
            self.set_status(d, st, beats)
            out.append(dict({"fighter": d.name, "status": st, "beats": beats, "head": spot, "part": h["part"]},
                            **({"look": look} if look else {})))
        roll = self.rng.random()
        worst = ("stunned" if roll < stun else "dazed" if roll < stun + daze else
                 "rattled" if roll < min(0.98, stun + daze + rattle) else None)
        self.note_roll(f"the blow to {poss_word(d.name)} {h['part'].lower()} (stunned {stun:.0%}, dazed {daze:.0%}, "
                       f"rattled {rattle:.0%})", min(0.98, stun + daze + rattle), roll, worst.upper() if worst else
                       "she shakes it off")
        if worst == "stunned":
            put("stunned", dur.get("stunned", 1))
            put("wobbly", dur.get("wobbly", 2))
            put("dazed", dur.get("dazed_after_stun", 2))
        elif worst == "dazed":
            put("dazed", dur.get("dazed", 1) + (1 if sev >= 1.2 else 0))
        elif worst == "rattled":
            put("rattled", dur.get("rattled", 1))
        side = cfg.get("side") or {}
        for st, ok, key, dflt in (("eyes_watering", spot == "nose", "eyes_watering", 0.6),
                                  ("ears_ringing", spot in ("ear", "side"), "ears_ringing", 0.5),
                                  ("jaw_rattled", spot == "jaw", "jaw_rattled", 0.45),
                                  ("seeing_double", worst in ("stunned", "dazed"), "seeing_double", 0.35),
                                  ("whiplash", held_head or kinds & {"throw"}, "whiplash", 0.4)):
            if ok and self._chance(min(0.95, float(side.get(key, dflt)) * max(0.5, sev)),
                                   f"{d.name} {st.replace('_', ' ')} from the blow to her {h['part'].lower()}",
                                   st.replace("_", " "), "no"):
                put(st, dur.get(st, 2))
        if worst in ("stunned", "dazed"):
            d.learned["head_jolts"] = int(d.learned.get("head_jolts", 0)) + 1
        cc = cfg.get("concussion") or {}
        if cc.get("enabled", True) and not self.has(d, "concussed"):
            hd = max((p.damage for p in d.parts.values() if body_region(p.name) == "head"), default=0.0)
            if hd >= float(cc.get("head_damage", 300)) or int(d.learned.get("head_jolts", 0)) >= int(cc.get("jolts", 3)):
                put("concussed", 999)
        return out

    # (since build 293, moves.body_jolts) what a hard blow can do to the rest of her for a few beats: (status, which
    # parts, the least the blow must do, or the least the part must be left at, and the default chance and beats)
    BODY_JOLTS = (("dead_leg", lambda p, plan: body_region(p) == "hind_up" or plan == "quadruped" and body_region(p) == "fore_up",
                   45, 0, 0.3, 2),
                  ("limping", lambda p, plan: body_region(p) == "hind_low" or plan == "quadruped" and body_region(p) == "fore_low",
                   0, 120, 0.35, 4),
                  ("dead_arm", lambda p, plan: plan in ("biped", "avian") and body_region(p) in ("shoulder", "fore_up", "fore_low"),
                   40, 0, 0.3, 2),
                  ("ribs_aching", lambda p, plan: bool(re.search(r"ribs|flank", p, re.I)), 40, 120, 0.35, 3),
                  ("back_spasm", lambda p, plan: body_region(p) == "back_low", 45, 0, 0.25, 2),
                  ("tail_numb", lambda p, plan: plan != "serpent" and bool(re.search(r"tail base|base of", p, re.I)), 40, 0, 0.3, 2),
                  ("swollen_eye", lambda p, plan: bool(re.search(r"cheek|eye|brow|temple", p, re.I)), 0, 150, 0.3, 8))

    def _body_jolts(self, d, hits, move=None):
        """moves.body_jolts (since build 293): beyond the head, what a hard blow can leave behind for a few beats: a
        dead leg (a thigh), a limp (a knee or a foot already badly hurt), a numb arm, aching ribs, a back in spasm, a
        numbed tail base, an eye swelling shut. Each one at most once at a time. Each its own
        chance (chances.<name>), with what it does in status_effects. Returns status records."""
        cfg = (self.rules.get("moves") or {}).get("body_jolts") or {}
        if not cfg.get("enabled", True):
            return []
        plan, out = self.body_plan(d), []
        ch, beats = cfg.get("chances") or {}, cfg.get("beats") or {}
        tough = max(0.3, self.trait(d, "toughness"))
        scale_ = float((self.rules.get("damage") or {}).get("damage_scale", 3) or 3) / 3.0   # (min_damage is at /scale 3)
        for st, fits, min_taken, min_after, dflt, dur in self.BODY_JOLTS:
            if self.has(d, st) or float(ch.get(st, dflt)) <= 0:
                continue
            h = next((h for h in sorted(hits, key=lambda h: -h.get("damage_taken", 0))
                      if h.get("defender", d.name) == d.name and fits(h["part"], plan)
                      and float(h.get("damage_taken", 0)) >= max(float(cfg.get("min_damage", 30)), min_taken) * scale_
                      and float(h.get("damage_after", 0)) >= min_after), None)
            if h is None:
                continue
            if self._chance(min(0.9, float(ch.get(st, dflt)) / tough), f"{d.name} {st.replace('_', ' ')} from the blow "
                            f"to her {h['part'].lower()}", st.replace("_", " "), "no"):
                self.set_status(d, st, int(beats.get(st, dur)))
                out.append({"fighter": d.name, "status": st, "beats": int(beats.get(st, dur)), "part": h["part"]})
        return out

    def note_wear(self, f, mark):
        """Something about how she LOOKS that stays for the rest of the fight (grit in her coat, scuffs)."""
        w = f.learned.setdefault("wear", [])
        f.learned.setdefault("wear_turn", {})[mark] = self.turn
        if mark not in w:
            w.append(mark)
            del w[:-6]

    def _decay(self, key, default):
        """narration.notes_decay: how many beats a small detail stays in the notes (0 = forever)."""
        cfg = (self.rules.get("narration") or {}).get("notes_decay") or {}
        if not cfg.get("enabled", True):
            return 0
        return int(cfg.get(key, default) or 0)

    def _stale(self, f, part, beats):
        """Has this part gone untouched for more than `beats` beats? (Unknown = not stale.)"""
        t = (getattr(self, "hit_turn", None) or {}).get(f"{f.name}|{part}")
        return bool(beats) and t is not None and self.turn - t > beats

    # what the damage looks like, by what did it: [light, worse, worst], three wordings each
    MARKS = {
        "claw": (["fine scratches through the fur", "thin claw lines combed through the coat",
                  "a few scratches, the fur split along them"],
                 ["raked furrows through the fur, the skin red beneath", "claw lines scored through the coat, red and "
                  "raised", "parallel scratches cutting the fur into tufts, the skin angry beneath"],
                 ["deep raked lines, the fur scraped thin along them", "the coat clawed ragged, whole tufts gone and the skin "
                  "welted", "deep claw furrows, the fur matted and parted round them, the skin welted"]),
        "bite": (["tooth marks pressed into the fur", "a crescent of dents where teeth closed",
                  "the fur pinched up in a line of small tooth prints"],
                 ["a ring of tooth marks, puffy and red round each one", "bite marks swollen into a raised ring",
                  "a double row of tooth prints, the skin round them puffed"],
                 ["deep tooth marks, the fur matted and clumped round them", "a deep bite mark, the fur matted and the "
                  "skin round it swollen tight", "deep tooth marks gone dark, the fur round them stiff and matted"]),
        "blunt": (["the fur ruffled up the wrong way", "the coat scuffed and standing up in a patch",
                   "a faint flattened patch where it struck"],
                  ["bruising showing dark through the fur wherever it parts", "a purpling under the coat you can see "
                   "when the fur shifts", "the skin dark beneath the fur, puffed and tender-looking"],
                  ["dark bruising under the fur, swollen out of its shape", "swollen and lumpy, the fur stretched over "
                   "the bruising", "a great dark bruise spreading under the coat, the shape of the part gone puffy"]),
        "grip": (["the fur crushed flat in the shape of what held it", "the coat pressed into a smooth print of the "
                  "grip", "fur flattened and twisted round where it was held"],
                 ["the fur ruffled into ridges, bruising beneath where it parts", "grip marks printed into the coat, "
                  "bruising coming up under them", "the fur twisted and crushed, red welts where the hold dug in"],
                 ["the fur crushed and matted, the flesh beneath bruised dark and puffy", "deep grip marks, the coat "
                  "mashed flat and the flesh round them swollen", "the shape of the hold bruised into her, fur crushed "
                  "into the skin"]),
        "shock": (["the fur frizzed and standing up", "the coat frizzed, every hair on end",
                   "a static-fluffed patch of fur"],
                  ["the fur singed and frizzed", "scorched tips to the fur, smelling of burnt hair",
                   "the coat frizzed and darkened at the ends"],
                  ["the fur singed in patches, the skin beneath angry red", "burnt, brittle fur over reddened skin",
                   "singed bare in spots, the skin shiny and red beneath"]),
        "cold": (["frost-stiff fur", "the fur rimed white and crunchy", "a patch of fur stiff with ice"],
                 ["frost-burned patches, the fur dull and stiff", "the coat frozen into stiff spikes, the skin pale "
                  "beneath", "cold-burned patches gone white and stiff"],
                 ["frost-burned patches gone red and raw-looking under stiff fur", "the skin blotched red and white "
                  "from the cold, the fur brittle", "cold-burned and swollen, the fur frozen into clumps"]),
    }
    # more wordings for each (merged into MARKS / CARTILAGE below): as much variety as the narrator can be given
    MARKS_MORE = {
        "claw": (["a light scoring of claw marks", "shallow nicks in the coat, the fur parted in thin lines"],
                 ["claw furrows crossing each other, the fur ragged", "long red scratches showing through the parted fur"],
                 ["deep claw tracks, the coat ragged round them", "the fur raked thin in stripes, the skin beneath "
                  "red and welted"]),
        "bite": (["small dents in the coat where fangs pressed", "a faint arc of bite marks"],
                 ["bite marks raised and reddened", "the fur bunched and wet round a ring of tooth marks"],
                 ["a crushing bite mark, the flesh round it swollen out", "deep fang marks, the coat round them clumped "
                  "and matted"]),
        "blunt": (["the coat mussed where it landed", "a dull patch where the fur was knocked flat"],
                  ["a bruise blooming under the coat, plain when the fur lifts", "the fur raised over a bruised swelling"],
                  ["bruised deep and swollen tight, the fur standing up over it", "the swelling pushing the fur apart, "
                   "dark beneath"]),
        "grip": (["the shape of the grip pressed into her coat", "fur smoothed flat in a band where it held"],
                 ["the coat creased into folds that won't lie down, bruising beneath", "grip-shaped bruises showing "
                  "through the flattened fur"],
                 ["the fur ground flat and the flesh puffed up dark round the grip lines", "crushed and swollen where "
                  "the hold was, the coat matted down hard"]),
        "shock": (["the fur puffed out and twitching", "hairs standing up in a frizzy halo"],
                  ["a burnt smell off the frizzed fur", "the fur curled and singed at the tips"],
                  ["the fur crisped away in patches", "scorched streaks through the coat, the skin hot and red"]),
        "cold": (["frost glittering in the coat", "the fur crusted white at the tips"],
                 ["the coat iced into hard clumps", "pale frost-bitten patches under stiff fur"],
                 ["the skin mottled and raw from the frost", "frostbitten patches gone dark red under brittle fur"]),
    }
    for _k, _more in MARKS_MORE.items():
        for _lvl, _words in enumerate(_more):
            MARKS[_k][_lvl].extend(_words)
    CARTILAGE = {"ear": ["folded and creased, not standing the way it should", "bent over at the tip",
                         "drooping, a crease across it"],
                 "nose": ["swollen and pushed a little crooked", "puffed up and sitting slightly askew",
                          "swollen, the tip bent a little to one side"],
                 "fin": ["bent along a crease, not lying flat", "crumpled at the edge", "creased and sticking out wrong"],
                 "cheek": ["puffed up", "swollen round", "puffy and lopsided"],
                 "muzzle": ["swollen", "puffed along its length", "swollen out of its line"],
                 "jaw": ["swollen along the line of it", "puffy along the hinge", "swollen under the jaw"]}

    CARTILAGE_MORE = {"ear": ["flopped sideways, not lifting"], "nose": ["puffed and tender, a little off true"],
                      "fin": ["folded back on itself at the edge"], "cheek": ["swollen up tight"],
                      "muzzle": ["thick and puffy"], "jaw": ["puffed up so it hangs a little crooked"]}
    for _k, _more in CARTILAGE_MORE.items():
        CARTILAGE[_k].extend(_more)

    def _mark_kind(self, src):
        s = str(src or "").lower()
        if re.search(r"\bpin\b|\bhold\b|coils|clutch|crab|armbar|crossface|lock|crank|wrench|squeez", s):
            return "grip"
        mv = None
        m = re.match(r"^.+?'s? (.+?)(?: \(.*\))?$", str(src or ""))
        if m:
            mv = self.dex_move(m.group(1))
        name = ((mv or {}).get("name") or "").lower() + " " + ((mv or {}).get("about") or "").lower()
        if re.search(r"slash|claw|swipe|scratch|rake|cut", name):
            return "claw"
        if re.search(r"bite|fang|crunch|jaws", name):
            return "bite"
        t = (mv or {}).get("type")
        if t == "Electric":
            return "shock"
        if t == "Ice":
            return "cold"
        return "blunt"

    def picture_marks(self, f, least=20):
        """What the window and exported cards draw on each hurt part (window.damage_marks): {part: {"kinds", "age"}}.
        kinds: the marks of what hurt it, up to two (claw, bite, blunt, grip, shock, cold, and burn for fire); age:
        beats since it was last hit (0 = this beat), or None. Only parts with at least `least` damage."""
        out = {}
        for p in f.parts.values():
            if p.damage < least:
                continue
            kinds = []
            for src in self.injury_causes(f"{f.name}|{p.name}", 2):
                k = self._mark_kind(src)
                if k == "blunt":
                    m = re.match(r"^.+?'s? (.+?)(?: \(.*\))?$", str(src or ""))
                    mv = (self.dex_move(m.group(1)) if m else None) or {}
                    s = str(src or "").lower()
                    # (a move missing from moves.json still says what it is in its own name)
                    k = ("burn" if mv.get("type") == "Fire" or re.search(r"flame|fire|ember|burn|scorch|heat", s) else
                         "claw" if re.search(r"slash|claw|swipe|scratch|rake|cut|talon", s) else
                         "bite" if re.search(r"bite|fang|crunch|jaws|teeth", s) else
                         "shock" if re.search(r"thunder|shock|spark|volt|electr", s) else
                         "cold" if re.search(r"\bice\b|icy|frost|freez|blizzard|hail", s) else k)
                if k not in kinds:
                    kinds.append(k)
            t = (getattr(self, "hit_turn", None) or {}).get(f"{f.name}|{p.name}")
            out[p.name] = {"kinds": kinds[:2] or ["blunt"], "age": None if t is None else max(0, self.turn - t)}
        return out

    def covering(self, f):
        """What her body is covered with, from her own description: fur, feathers, scales, or bare skin."""
        t = f"{getattr(f, 'appearance', '') or ''} {getattr(f, 'description', '') or ''}".lower()
        n = {"fur": len(re.findall(r"\bfur|\bpelt|\bcoat\b", t)),
             "feathers": len(re.findall(r"feather|plumage|\bdown\b", t)),
             "scales": len(re.findall(r"\bscale", t))}
        best = max(n, key=n.get)
        return best if n[best] else "skin"

    def in_her_covering(self, f, text):
        """Wound and wear wording is written for fur: say it in feathers, scales or skin for a body that has those."""
        return in_covering(self.covering(f), text)

    def visible_marks(self, f, p):
        """What the damage to one part LOOKS like by now: the marks of what did it (claws, teeth, blows, grips,
        lightning, cold), how deep, and cartilage (ears, nose, fins) creased or bent out of shape for now."""
        lvl = 2 if p.damage >= 300 else 1 if p.damage >= 150 else 0
        srcs = self.injury_causes(f"{f.name}|{p.name}", 2)
        kinds = list(dict.fromkeys(self._mark_kind(c) for c in srcs)) or ["blunt"]
        import zlib
        pick = lambda lst, salt: lst[zlib.crc32(f"{f.name}|{p.name}|{salt}".encode()) % len(lst)]
        marks = [pick(self.MARKS[k][lvl], k) for k in kinds[:2]]
        cart = next((pick(v, "c") for k, v in self.CARTILAGE.items() if k in p.name.lower() and v), "")
        if cart and lvl >= 1:
            marks.append(cart + " for now")
        if lvl == 2 and "swollen" not in " ".join(marks):
            marks.append("swollen")
        return self.in_her_covering(f, f"her {p.name.lower()}: " + ", ".join(marks))

    def _guided(self, what):
        """narration.guided: is this piece of the engine-led narration on?"""
        g = (self.rules.get("narration") or {}).get("guided") or {}
        return bool(g.get("enabled", False) and g.get(what, True))

    def _mark_age(self, f, p):
        """When the mark on this part was made (narration.guided.marks): " (new this beat)", " (from beat 7)", so a
        cut is fresh or old as it really is, and nothing on her has "begun to dry" that was made a moment ago."""
        if not self._guided("marks"):
            return ""
        t = (getattr(self, "hit_turn", None) or {}).get(f"{f.name}|{p.name}")
        if t is None:
            return ""
        return " (new this beat)" if t >= self.turn else f" (last hit in beat {t}, {self.turn - t} beat{'s' if self.turn - t != 1 else ''} ago)"

    def wear_text(self):
        """VISIBLE WEAR: how each fighter looks by now, so the narrator keeps it the same from beat to beat."""
        rows = []
        # after the match the one who lost is still there to be seen (the aftermath shows how she lies): her wear stays
        for f in (list(self.fighters.values()) if self.winner() else self.active()):
            # small surface details (grit in her coat, a scuff) fade from the notes after a few beats: the fight has
            # moved on and the fur has moved with it (narration.notes_decay.wear_beats)
            wb, wt = self._decay("wear_beats", 6), f.learned.get("wear_turn") or {}
            bits = [m for m in (f.learned.get("wear") or [])
                    if not (wb and m in wt and self.turn - wt[m] > wb)]
            if self.has(f, "soaked"):
                bits.append("fur soaked dark and plastered flat")
            if self.has(f, "burned"):
                bits.append("singed patches in her fur")
            if self.has(f, "chilled"):
                bits.append("moving stiff and heavy" if f.name in (getattr(self, "_slow_not_cold", None) or ())
                            else "frost in her fur, shivering")
            bad = sorted((p for p in f.parts.values() if p.damage >= 90), key=lambda p: -p.damage)[:4]
            # a mark on a part nobody has touched for a while is given in short: the first thing that shows
            ob = self._decay("origin_beats", 4)
            bits += [(self.visible_marks(f, p).split(", ")[0] if self._stale(f, p.name, ob) else self.visible_marks(f, p))
                     + self._mark_age(f, p) for p in bad]
            guided = self._guided("marks")
            if guided:
                # what she does NOT show matters as much: a fighter only ever struck with blunt blows has no cut and
                # no blood on her, and a part not listed carries no mark (narration.guided.marks)
                hurt = [p for p in f.parts.values() if p.damage >= 30]
                kinds = {self._mark_kind(c) for p in hurt for c in self.injury_causes(f"{f.name}|{p.name}", 3)}
                if hurt and not kinds & {"claw", "bite"}:
                    bits.append("no cuts and no blood anywhere on her: only bruising")
                if not bits:
                    bits.append("no marks that show yet" + (" (her hurts so far are under the skin)" if hurt else ""))
                elif bad:
                    bits.append("nothing else on her shows a mark")
            if bits:
                rows.append(f"{f.name}: " + self.in_her_covering(f, "; ".join(dict.fromkeys(bits))))
        return ("VISIBLE WEAR (how they look by now; keep it the same unless this beat changes it): "
                + " | ".join(rows)) if rows else ""

    def _overcommit(self, a, move):
        """A very tired fighter sometimes overcommits (moves.exhaustion_mistakes): the blow lands weak and she
        overbalances on it (off balance for a beat)."""
        cfg = (self.rules.get("moves") or {}).get("exhaustion_mistakes") or {}
        if not cfg.get("enabled", True) or move.get("target") in ("status", "self", "hold"):
            return None
        self._overcommit_why = "tired"
        q = self.quirk(a, "cocky")
        landed = (a.learned or {}).get("landed_big")
        if q and landed is not None and self.turn - int(landed) <= 1 and self.strength(a) >= float(q.get("until_below", 60)):
            # (since build 280) cocky: a good hit last beat, and she overreaches on the next one
            if self._chance(float(q.get("chance", 0.25)), f"{a.name} overreaching, cocky after her last hit",
                            "OVERREACHES", "no"):
                self._overcommit_why = "cocky"
                return a.name
        if a.energy >= float(cfg.get("below_energy", 20)) and self.strength(a) >= float(cfg.get("below_strength", 25)):
            return None
        ch = float(cfg.get("chance", 0.12))
        q = self.quirk(a, "ring_sense")
        if q:
            ch *= float(q.get("mult", 0.35))     # (experience: she doesn't get sloppy)
        if not self._chance(ch, f"{a.name} overcommitting, sloppy with tiredness", "SLOPPY", "no"):
            return None
        return a.name

    def _wing_way(self, f, p):
        """How a hurt wing shows in the way she moves: in the air she still flies on it, on the ground she holds it."""
        name, bad = p.name.lower(), p.damage >= 300
        if self.has(f, "airborne"):
            return (f"flies lopsided, her {name} labouring, every stroke of it ragged and short" if bad else
                    f"favours her {name} in the air, its strokes a little short and careful")
        return (f"her {name} hangs half-folded and trailing, held off the rock" if bad else
                f"keeps her {name} folded close, guarding it")

    def movement_text(self):
        """HOW THEY MOVE NOW: what each fighter's injuries do to the way she moves (favouring a leg, an arm held in),
        repeated every beat so the story keeps it up."""
        rows = []
        for f in self.active():
            bits = []
            for p in sorted(f.parts.values(), key=lambda p: -p.damage):
                if p.damage < 150 or len(bits) >= 3:
                    continue
                reg = body_region(p.name)
                if "wing" in p.name.lower():
                    bits.append(self._wing_way(f, p))
                elif self.has(f, "airborne") and reg in ("hind_low", "hind_up"):
                    bits.append(f"holds her {p.name.lower()} tucked up stiffly under her as she flies")   # (no limp aloft)
                elif reg == "tail" and "flame" in p.name.lower():
                    bits.append("the flame on her tail burns low and small")
                elif reg in ("neck", "head") and any(b.startswith("holds her head carefully") for b in bits):
                    continue          # (one line for a hurt head and neck, not the same line twice)
                elif reg in ("hind_low", "hind_up") or (reg in ("fore_low", "fore_up") and self.body_plan(f) == "quadruped"):
                    bits.append(f"favours her {p.name.lower()}, keeping weight off it (a limp when she moves)")
                elif reg in ("fore_low", "fore_up"):
                    bits.append(f"keeps her {p.name.lower()} tucked in and uses it as little as she can")
                elif reg == "tail":
                    bits.append(f"her {p.name.lower()} hangs low and heavy")
                elif reg in ("chest", "belly"):
                    bits.append(f"moves stiffly, guarding her {p.name.lower()}, breath short when she turns")
                elif reg in ("neck", "head"):
                    bits.append(f"holds her head carefully, the {p.name.lower()} making every turn of it a decision")
                elif reg in ("back_up", "back_low", "shoulder"):
                    bits.append(f"twists as little as she can, her {p.name.lower()} pulling with every movement")
            if bits:
                rows.append(f"{f.name}: " + "; ".join(bits))
        return ("HOW THEY MOVE NOW (their injuries; keep it up in every movement, unless she is fighting through it): "
                + " | ".join(rows)) if rows else ""

    def mark_arena(self, text):
        if " lies broken" in text:      # kept for the whole fight (the marks list only keeps the last few)
            gone = self.__dict__.setdefault("broken_props", [])
            what = text.split(" lies broken")[0].strip().lower()
            if what not in gone:
                gone.append(what)
        marks = self.__dict__.setdefault("arena_marks", [])
        if text not in marks:
            marks.append(text)
            del marks[:-6]

    def _cause_words(self, src, hurt=""):
        """'Ripples' Water Gun' -> "Ripples' jet of water": what did it, in plain words (moves.json 'about')."""
        s = str(src or "").strip()
        turned = "(turned back)" in s or "turned back" in s
        s = re.sub(r"\s*\((?:held|turned back)\)|\s+still driving into her", "", s)
        m = re.match(r"^(.+?'s?) (.+)$", s)
        if not m:
            return (s.replace("landing on ", "the fall onto ").replace("being driven into ", "being slammed into ")
                    .replace("being driven on into ", "being slammed on into ").replace("being pressed into ", "being "
                    "crushed against "))
        who, what = m.group(1), m.group(2)
        low = what.lower()
        if low == "pin":
            return f"the weight of {who} pin"
        if low in ("hold", "coils", "tails"):
            return f"{who} {low}"
        if low == "escape":
            return f"the blow {who[:-2] if who.endswith(chr(39) + 's') else who.rstrip(chr(39))} struck breaking free"
        if low == "struggle":
            return f"{who} struggling"
        if re.match(r"(?:fall|drop)\b", low):
            # (since build 266) her own fall ("Ripples' fall trying to get up") is no blow of anyone's
            return f"{'her own' if re.sub(chr(39) + r's?$', '', who) == str(hurt) else who} {what}"
        if low in self.SUBMISSIONS or self.sub_uses(low):
            return f"{who} {low}"
        # her own move first (the fighter's file), then the move list only under that very name: a near miss in the
        # list is another move ('Slash' is not 'Flash, a blinding flash of light')
        try:
            own = self.find_move(re.sub(r"(?:'s|')$", "", who), what)
        except ValueError:
            own = None
        dex = self.dex_move(what)
        if dex and " ".join(dex["name"].lower().replace("-", " ").split()) != " ".join(low.replace("-", " ").split()):
            dex = None
        mv = own or dex
        art = re.compile(r"(?:an?|the)\s", re.I)
        about = next((str(m.get("about") or "") for m in (own, dex) if m and art.match(str(m.get("about") or ""))),
                     "" if not own or re.match(r"[\w-]+s\b", str(own.get("about") or "")) else str(own.get("about") or ""))
        if about:
            noun = re.split(r"\s+(?:across|into|from|that|with|to|which)\b|[,:;(]", about, maxsplit=1)[0].strip()
            noun = re.sub(r"^(?:a|an|the)\s+", "", noun, flags=re.I)
        else:
            # (an 'about' that is a verb, "flash-freezes the target": the move by its own name)
            noun = "blow" if not mv or mv.get("type") in ("Normal", "Fighting") else mv.get("name") or what
        if turned:
            mine = who.rstrip("'s").rstrip("'") == str(hurt)
            return f"her own {noun}, sent back at her" if mine else f"{who} {noun}, turned back on her"
        return f"{who} {noun}"

    REPORT_LEAD = {
        "won_fresh": ["won, and has little to show for it", "won without much damage", "came out of it largely whole"],
        "won_hurt": ["won, and it cost her", "won, but she paid for it", "came out on top, though not cheaply"],
        "won_wrecked": ["won, barely, and every step home will tell her so", "won on what she had left, which was not much",
                        "is the one still standing, if only just"],
        "lost": ["lies out cold, and when she wakes it will all be waiting for her",
                 "is out cold; waking up will be the hard part",
                 "lost, and her body will remember every part of it"],
        "standing": ["is still on her feet, and feeling it", "made it through"],
        # she won, but is lying on the ground herself and can't get up yet
        "won_down": ["won, from flat on the ground, and can't get up yet", "won, though she is in no state to stand",
                     "won lying down, and her body has no more to give for now"],
        # she gave up awake (finish.submission.tap_awake): beaten, not knocked out
        "tapped": ["tapped out, awake for every second of it, and it will all be waiting for her",
                   "gave up in the end, awake and hurting", "lost by tapping out; she felt all of it"],
    }
    REPORT_HURT = {
        "deep": ["black with bruising, stiff and swollen for days", "swollen tight; it won't bear a touch for a week",
                 "it will throb every time she moves for days to come", "the first thing she'll feel every morning for "
                 "a while", "bruised deep and slow to mend"],
        "sore": ["sore and stiff tomorrow, tender for a few days", "bruised and aching; she'll favour it for days",
                 "stiff by morning and tender to the touch", "it will ache whenever she moves it for a few days"],
        "light": ["aching tomorrow, nothing worse", "a dull ache, gone in a day or two",
                  "bruised, and grumbling about it by morning"],
    }
    REPORT_FRAMES = [
        "her {part}, from {cause}: {hurt}",
        "{cause} did her {part}: {hurt}",
        "her {part} took {cause}: {hurt}",
        "the {part}, where {cause} landed: {hurt}",
    ]

    def injury_report(self):
        """After the fight: each fighter's worst parts, what did them, and what she'll feel tomorrow, in varied words
        (for the aftermath and the console)."""
        import zlib
        win = self.winner()
        rows = []
        for f in self.fighters.values():
            def pick(lst, salt):
                return lst[zlib.crc32(f"{f.name}|{salt}|{getattr(self, '_seed0', 0)}".encode()) % len(lst)]
            s = self.strength(f)
            lead_key = ("lost" if f.eliminated or (win and f.name != win and self.get(win).team != f.team) else
                        ("won_fresh" if s >= 70 else "won_hurt" if s >= 35 else "won_wrecked") if win else "standing")
            if lead_key.startswith("won") and f.name in self.downed:
                lead_key = "won_down"     # (not "the one still standing" while she lies there)
            if lead_key == "lost" and str((self.__dict__.get("out_reason") or {}).get(f.name, "")).startswith(
                    "taps out") and (self.rules.get("finish", {}).get("submission") or {}).get("tap_awake", True):
                lead_key = "tapped"
            lead = f"{f.name} {pick(self.REPORT_LEAD[lead_key], 'lead')}"
            worst = sorted((p for p in f.parts.values() if p.damage >= 60), key=lambda p: -p.damage)[:4]
            if not worst:
                rows.append(f"{lead}: bruised here and there, nothing that will last")
                continue
            bits = []
            for i, p in enumerate(worst):
                causes = [c for c in self.injury_log.get(f"{f.name}|{p.name}", []) if c]
                causes = list(dict.fromkeys(self._cause_words(c, f.name) for c in causes[-2:]))
                cause = " and ".join(causes) or "the fight"
                # by its pain level: excruciating or worse is deep, very painful sore, less than that light
                sev = "deep" if p.damage >= 150 else "sore" if p.damage >= 90 else "light"
                hurt = pick(self.REPORT_HURT[sev], p.name)
                frame = self.REPORT_FRAMES[(zlib.crc32(f"{f.name}|{p.name}".encode()) + i) % len(self.REPORT_FRAMES)]
                bits.append(frame.format(part=p.name.lower(), cause=cause, hurt=hurt))
            bits[0] = bits[0][0].upper() + bits[0][1:]
            rows.append(f"{lead}. " + "; ".join(bits))
        return "INJURY REPORT (what each will feel when it's over): " + " | ".join(rows)

    # ---------- how far apart they are (narration.match_state.distance) ----------
    GAP_STEPS = ("locked", "close", "near", "far")
    GAP_LOOK = {"locked": "LOCKED TOGETHER (a grip, a grab or a pin joins them: no space between them at all)",
                "close": "IN REACH of each other (close enough to strike without taking a step)",
                "near": "A FEW STRIDES APART (a step or a lunge is needed before anything but a ranged move can land)",
                "far": "WELL APART (a run across the ground lies between them)"}
    GAP_SHORT = {"locked": "locked together", "close": "in reach", "near": "a few strides apart", "far": "well apart"}

    def _gap_cfg(self):
        return ((self.rules.get("narration") or {}).get("match_state") or {})

    def _gap_on(self):
        cfg = self._gap_cfg()
        return bool(cfg.get("enabled", True) and cfg.get("distance", True))

    @staticmethod
    def _gap_key(a, b):
        return "|".join(sorted((a, b)))

    def _gap_joined(self, a, b):
        """True when a grip, a grab or a pin joins the two of them."""
        return (any({h.attacker, h.defender} == {a, b} for h in self.holds.values())
                or any(p["defender"] in (a, b) and ({a, b} - {p["defender"]}) <= set(self.pin_members(p))
                       for p in self.pins.values()))

    def gap_of(self, a, b):
        """How far apart two fighters are now: locked, close, near or far (narration.match_state.distance)."""
        if self._gap_joined(a, b):
            return "locked"
        start = str(self._gap_cfg().get("start", "near"))
        return (getattr(self, "gap", None) or {}).get(self._gap_key(a, b)) or (start if start in self.GAP_STEPS else "near")

    def note_gap(self, results, events=()):
        """Work out how far apart each pair of fighters ends this beat from what the beat resolved, so the story
        never has her 'close the gap' on someone already in reach, or strike from across the ground with a bite. It
        only reads what happened: a blow that lands or is slipped (not a ranged one) leaves them in reach, a throw or a
        launch puts a few strides between them, a breather opens a little room, a grip or a pin locks them together,
        and breaking out of one leaves them in reach. A ranged move changes nothing: it crosses whatever gap there is."""
        if not self._gap_on():
            return
        cfg = self._gap_cfg()
        names = [f.name for f in self.active()]
        gap = self.__dict__.setdefault("gap", {})
        self._gap_before = {self._gap_key(a, b): self.gap_of(a, b) for i, a in enumerate(names) for b in names[i + 1:]}
        now = dict(self._gap_before)

        def put(a, b, state):
            if a and b and a != b and a in names and b in names:
                now[self._gap_key(a, b)] = state

        for r in results or ():
            t, a, d = r.get("type"), r.get("attacker"), r.get("defender")
            if t == "breather" and cfg.get("breather_room", True):
                who = r.get("focus")
                for o in names:
                    k = self._gap_key(who, o) if who and o != who else None
                    # she gets her breath back by giving herself room, unless she is down or pinned where she lies
                    if k in now and now[k] == "close" and who not in self.downed and not self.pinned_by(who):
                        now[k] = "near"
                continue
            if t in ("grapple_start", "hold_start", "pin_start"):
                put(a, d, "locked")
                continue
            if t == "reposition" and not r.get("resisted"):
                put(a, d, "close")
                continue
            if t != "instant" or not isinstance(d, str) or a == d or r.get("self_move") or r.get("status_move"):
                continue
            launch = str(r.get("launch") or "")
            mv = r.get("move") if isinstance(r.get("move"), dict) else {}
            full = (self.find_move(a, mv.get("name")) if a in names and mv.get("name") else None) or mv
            ranged = bool(mv) and self.is_ranged(full)
            for dn in [x.strip() for x in d.split(",")] if "," in d else [d]:
                if launch in ("thrown", "launched"):
                    put(a, dn, "near")
                elif r.get("environment") or ranged:
                    continue      # (a fall where she stands, or a move that crosses the gap: the gap stays)
                else:
                    put(a, dn, "close")
        for e in events or ():
            t = e.get("type")
            if t == "hold_end" and (e.get("broke_free") or e.get("shaken")) or t == "pin_broken" or (
                    t == "pin_progress" and e.get("struggle") == "escape"):
                put(e.get("attacker"), e.get("defender"), "close")
        for k in list(now):
            a, b = k.split("|", 1)
            if self._gap_joined(a, b):
                now[k] = "locked"
            elif now[k] == "locked":
                now[k] = "close"      # a grip that has ended leaves them right there, in reach
        gap.update(now)

    def gap_text(self, card=False, now_only=False):
        """DISTANCE: how far apart each pair is now and, when it changed, how far apart they were when the beat began.
        "" when it is off or there is nobody to be apart from. card: the short form for the beat card."""
        if not self._gap_on():
            return ""
        names = [f.name for f in self.active()]
        before = {} if now_only else getattr(self, "_gap_before", None) or {}
        rows = []
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                k, now = self._gap_key(a, b), self.gap_of(a, b)
                was = before.get(k, now)
                words = self.GAP_SHORT if card else self.GAP_LOOK
                rows.append(f"{a} and {b}: " + (f"{'started' if card else 'at the start of this beat they were'} "
                                                f"{self.GAP_SHORT[was]}; {'now' if card else 'now they are'} {words[now]}"
                                                if was != now else words[now]))
        if not rows:
            return ""
        if card:
            return " | ".join(rows)
        if now_only:
            # (for the director: a bite or a claw from a few strides off means closing in first; a ranged move doesn't)
            return "DISTANCE NOW: " + " | ".join(rows) + "."
        return ("DISTANCE (where they are from each other, tracked by the program from what has happened; certain): "
                + " | ".join(rows) + ". Nobody already in reach 'closes the gap', 'crosses the distance' or charges in "
                "from across the ground; nobody a few strides off lands a bite, a claw or a blow without first covering "
                "that ground.")

    # ---------- the fight's story so far: key moments and what decided it (the end-of-fight summary) ----------
    @staticmethod
    def new_chronicle():
        return {"moments": [], "track": [], "dealt": {}, "pins": {}, "escapes": {}, "biggest": None, "finish": None}

    def _moment(self, kind, text, who="", to="", loss=0.0, weight=1):
        ch = self.__dict__.setdefault("chronicle", self.new_chronicle())
        ch["moments"].append({"beat": self.turn, "kind": kind, "text": text, "who": who, "to": to,
                              "loss": round(float(loss), 1), "weight": weight})
        del ch["moments"][:-80]

    def record_beat(self, results, events):
        """Write this beat's key moments into the chronicle (the end-of-fight summary reads it). Called once a beat,
        after the beat's actions and the clock have both run. It only reads what happened: no dice, no changes."""
        ch = self.__dict__.setdefault("chronicle", self.new_chronicle())
        for k, v in self.new_chronicle().items():
            ch.setdefault(k, v)
        big_at = float((self.rules.get("summary") or {}).get("big_hit_pct", 9.0))

        def pct(name, loss):
            f = self.fighters.get(str(name).lower())
            return float(loss) / max(1.0, f.max_health) * 100 if f else 0.0

        def deal(who, hits, default_to=""):
            total = {}
            for h in hits or []:
                to = h.get("defender") or default_to
                loss = float(h.get("health_loss") or 0.0)
                if not to or loss <= 0:
                    continue
                total[to] = total.get(to, 0.0) + loss
                if who:
                    ch["dealt"][who] = round(ch["dealt"].get(who, 0.0) + pct(to, loss), 2)
            return total

        for r in results or []:
            if not isinstance(r, dict):
                continue
            att, dfn = r.get("attacker", ""), r.get("defender", "")
            if r.get("type") == "pin_start":
                ch["pins"][att] = ch["pins"].get(att, 0) + 1
                took = " takes her down and" if r.get("taken_down") else ""
                self._moment("pin", f"{att}{took} pins {dfn}", att, dfn, weight=1.5)
                continue
            if r.get("type") == "eliminated" and r.get("knockout"):
                # the blow that ends it: the last one that landed on her this beat
                last = next((x for x in reversed(results) if isinstance(x, dict) and x.get("type") == "instant"
                             and x.get("defender") == r.get("fighter") and x.get("hits")), {})
                mv_, by = (last.get("move") or {}).get("name") or "", r.get("by") or last.get("attacker") or ""
                self._moment("knockout", f"{poss_word(by)} {mv_} knocks {r.get('fighter')} out cold" if by and mv_ else
                             f"{r.get('fighter')} is knocked out cold", by, r.get("fighter", ""), weight=3)
                continue
            if r.get("type") != "instant" or r.get("confused_self_hit") or (att and att == dfn):
                continue        # (a confused fighter hitting herself is nobody's blow on anyone)
            mv = (r.get("move") or {}).get("name") or "a blow"
            land = bool(r.get("environment"))
            if land:
                mv = "the landing"
            whose = f"{poss_word(dfn)} landing" if land else f"{poss_word(att)} {mv}"
            lost = deal(att, r.get("hits"), dfn)
            deal(dfn, r.get("counter_hits"), att)
            deal(dfn, (r.get("pass_counter") or {}).get("hits"), att)
            deal(dfn, (r.get("air_rake") or {}).get("hits"), att)
            # (a leap's landing hits are the leaper's own legs: nobody dealt them) a reflected blow is the defender's
            deal(dfn, (r.get("reflected") or {}).get("hits"), att)
            loss = pct(dfn, lost.get(dfn, 0.0))
            hits = r.get("hits") or []
            part = max(hits, key=lambda h: float(h.get("health_loss") or 0))["part"].lower() if hits else ""
            if (r.get("move") or {}).get("target") == "whole_body" and hits:
                part = "whole body"     # (a surge through all of her: not "on her throat" because the throat lost most)
            if loss > 0 and (ch["biggest"] is None or loss > ch["biggest"]["pct"]):
                ch["biggest"] = {"beat": self.turn, "who": att, "to": dfn, "move": mv, "part": part,
                                 "pct": round(loss, 1)}
            if r.get("devastating") and hits:
                dp = next((h["part"].lower() for h in hits if h.get("devastating")), part)
                self._moment("devastating", (f"{whose} comes down DEVASTATINGLY on her {dp}" if land else
                                             f"{whose} lands DEVASTATINGLY on {poss_word(dfn)} {dp}"),
                             att, dfn, loss, 3)
            elif loss >= big_at and not r.get("last_stand"):     # (the last-stand moment tells that blow)
                self._moment("big", (f"{whose} slams her {part} into the ground" if land else
                                     f"{whose} hammers {poss_word(dfn)} {part}"), att, dfn, loss, 1.5)
            if r.get("juggle") and hits:
                self._moment("juggle", f"{att} catches {dfn} helpless in the air with {mv}", att, dfn, loss, 2)
            if (r.get("feint") or {}).get("bit") and hits:
                self._moment("feint", f"{dfn} bites on {poss_word(att)} feint and eats the {mv}", att, dfn, loss, 1)
            if r.get("last_stand"):
                self._moment("last_stand", f"{att} throws everything she has left into one last {mv}"
                             + (f" on {poss_word(dfn)} {part}" if part and part != "whole body" else ""), att, dfn, loss, 2)
            if r.get("clash"):
                self._moment("clash", f"{att} and {dfn} meet head-on in a clash", att, dfn, loss, 1)
            if r.get("reflected"):
                self._moment("reflect", f"{dfn} turns {poss_word(att)} {mv} back on her", dfn, att, 0, 2)
            g = r.get("guard") or {}
            if g.get("kind") in ("block", "deflect"):
                self._moment("guard", f"{dfn} {'blocks' if g['kind'] == 'block' else 'turns aside'} "
                                      f"{poss_word(att)} {mv}", dfn, att, 0, 1)
            if r.get("missed_charge"):
                self._moment("crash", f"{poss_word(att)} {mv} misses and she crashes", att, dfn, 0, 1)
            if (r.get("pummel") or {}).get("frenzy"):
                self._moment("frenzy", f"{att} loses herself in a frenzy of blows on {dfn}", att, dfn, loss, 2)
        for e in events or []:
            t = e.get("type")
            if t == "hold_ongoing":
                deal(e.get("attacker"), e.get("hits"), e.get("defender"))
            elif t == "pin_progress":
                att, dfn = e.get("attacker", ""), e.get("defender", "")
                deal(att, e.get("punish_hits"), dfn)
                for h in e.get("hits_on_pinner") or []:      # each blow on the pinner it really hit (double pins)
                    deal(dfn, [h], h.get("defender") or att)
                if e.get("struggle") == "escape":
                    ch["escapes"][dfn] = ch["escapes"].get(dfn, 0) + 1
                    self._moment("escape", f"{dfn} breaks out of {poss_word(att)} pin"
                                + ((f" after {max(1, int(e.get('beats') or 1))} beat{'s' if int(e.get('beats') or 1) != 1 else ''}"
                                    if e.get("fade_mode") or self.fade_mode() else f" after {e['seconds_to']} seconds")
                                   if e.get("seconds_to") else ""), dfn, att,
                                 weight=1.5 + min(1.0, float(e.get("seconds_to") or 0) / 10.0))
                if e.get("complete"):
                    oc = e.get("out_cause") or {}
                    ch["finish"] = {"beat": self.turn, "who": att, "to": dfn, "fade": bool(e.get("fade_mode")),
                                    "seconds": e.get("seconds_to"), "beats": e.get("beats"),
                                    "cause": oc.get("cause", ""), "part": (oc.get("part") or "").lower(),
                                    "with": (oc.get("with") or "").lower(), "kind": oc.get("kind", ""),
                                    "strength": round(self.strength(self.fighters[dfn.lower()]), 1) if dfn.lower() in self.fighters else None}
                    how = {"choking": {"blood": "the blood choke", "air": "the choke on her windpipe", "both": "the choke"}.get(
                               oc.get("kind"), "the choke"), "constriction": "the constriction"}.get(oc.get("cause"), "the pain")
                    self._moment("finish", f"{att} holds {dfn} down until {how} puts her out", att, dfn, weight=3)
            elif t in ("tap_count", "tap_out"):
                # a tap (or a black-out) in a submission: one of the match's biggest moments
                did = "taps out" if e.get("how") == "tap" else "passes out"
                part_ = str(e.get("part") or "").lower()
                tally = (f" (tap {e.get('tap_no')} of {e.get('needed')})" if t == "tap_count" and e.get("needed")
                         else "")
                self._moment("tap", f"{e.get('defender')} {did} to {poss_word(e.get('attacker', ''))} "
                             f"{e.get('submission') or 'hold'}" + (f" on her {part_}" if part_ else "") + tally,
                             e.get("attacker", ""), e.get("defender", ""), weight=3 if t == "tap_out" else 2.5)
            elif t == "sub_collapse":
                self._moment("sub_collapse", f"{poss_word(e.get('attacker', ''))} {e.get('submission') or 'hold'} "
                             f"bears {e.get('defender')} down ({e.get('stage')})", e.get("attacker", ""),
                             e.get("defender", ""), weight=1)
            elif t == "adrenaline":
                self._moment("adrenaline", f"{e.get('fighter')} gets a surge of adrenaline", e.get("fighter"),
                             weight=1)
        ch["track"].append({"beat": self.turn, **{f.name: round(self.strength(f), 1)
                                                   for f in self.fighters.values()}})
        del ch["track"][:-400]

    def _turning_point(self, win, lose):
        """The beat after which the winner was clearly ahead (summary.lead_margin points of strength) for good, or None
        if she was from the very first beat."""
        track = (getattr(self, "chronicle", None) or {}).get("track") or []
        margin = float((self.rules.get("summary") or {}).get("lead_margin", 5.0))
        last_behind = None
        for row in track:
            if win in row and lose in row and row[win] - row[lose] < margin:
                last_behind = row["beat"]
        if last_behind is None:
            return None
        after = next((row for row in track if row["beat"] > last_behind), None)
        return {"beat": after["beat"] if after else last_behind, "win": after.get(win) if after else None,
                "lose": after.get(lose) if after else None}

    def fight_summary(self, for_story=False):
        """After the win: the key moments in order, how it was finished, the turning point and what decided it.
        for_story leaves out the numbers, for the narrator's aftermath."""
        win = self.winner()
        ch = getattr(self, "chronicle", None) or {}
        if not win or not ch.get("track"):
            return ""
        losers = [f for f in self.fighters.values() if f.name != win]
        if not losers:
            return ""
        # the one who went out (with three or more, never the winner's ally who is still standing): the weakest of them
        out_ = [f for f in losers if f.eliminated] or losers
        lose = min(out_, key=lambda f: self.strength(f)).name
        moments = [m for m in ch.get("moments", []) if m["kind"] != "finish"]
        cap = int((self.rules.get("summary") or {}).get("moments", 10))
        per_kind = int((self.rules.get("summary") or {}).get("per_kind", 3))
        keep, kinds = [], {}
        for m in sorted(moments, key=lambda m: -(m["weight"] + m["loss"] / 10.0)):
            k = "pin" if m["kind"] in ("pin", "escape") else m["kind"]
            if kinds.get(k, 0) < (per_kind + 1 if k == "pin" else per_kind + 3 if k == "tap" else per_kind) \
                    and len(keep) < cap:     # (every tap of a several-tap match is told)
                kinds[k] = kinds.get(k, 0) + 1
                keep.append(m)
        keep.sort(key=lambda m: (m["beat"], m["kind"] == "knockout"))     # (the knockout ends its beat)
        fin = ch.get("finish") or {}
        tp = self._turning_point(win, lose)
        dealt = ch.get("dealt", {})
        names = [f.name for f in self.fighters.values()]
        pins, esc = ch.get("pins", {}), ch.get("escapes", {})
        lf = self.get(lose)
        worst = sorted((p for p in lf.parts.values() if p.damage >= 90), key=lambda p: -p.damage)[:3]

        def causes(p):
            log = [c for c in self.injury_log.get(f"{lose}|{p.name}", []) if c]
            return ", ".join(log[-2:])

        reasons = []
        if fin:
            how = {"choking": ("the blood choke on her " + (fin.get("part") or "neck") if fin.get("kind") == "blood"
                               else "the choke on her windpipe" if fin.get("kind") == "air"
                               else "the choke on her " + (fin.get("part") or "throat")),
                   "constriction": "the constriction around her " + fin["part"] if fin.get("part") else "the constriction"
                   }.get(fin.get("cause"), f"the pain in her {fin['part']}" if fin.get("part") else "the pain")
            reasons.append(f"{win} got her pinned when {lose} had too little left to throw her off, and {how} "
                           f"took her the rest of the way")
        if esc.get(lose):
            reasons.append(f"{lose} broke out {esc[lose]} time{'s' if esc[lose] != 1 else ''} before the last one held")
        if worst:
            p = worst[0]
            c = causes(p)
            reasons.append(f"{poss_word(lose)} {p.name.lower()} was the wound that mattered: once it was ruined"
                           + (f" (by {c})" if c else "") + " every touch there sapped her")
        devs = [m for m in moments if m["kind"] == "devastating" and m["who"] == win and m["loss"] >= 5]
        if devs:
            reasons.append(f"{poss_word(win)} devastating blow{'s' if len(devs) > 1 else ''} "
                           f"swung it harder than anything else")
        dw, dl = dealt.get(win, 0), dealt.get(lose, 0)
        if dw > dl * 1.3:
            reasons.append(f"{win} simply hurt her more" + ("" if for_story else
                           f" ({dw:.0f}% of {poss_word(lose)} strength against {dl:.0f}%)"))
        elif dl > dw * 1.1:
            reasons.append(f"{lose} actually did more damage" + ("" if for_story else f" ({dl:.0f}% against {dw:.0f}%)")
                           + f", but {win} made what she landed count where it mattered")
        else:
            reasons.append("the damage was close" + ("" if for_story else f" ({dw:.0f}% to {dl:.0f}%)")
                           + ": it came down to who could hold the other down")
        if for_story:
            out = ["HOW THE FIGHT WENT (the key moments, for the aftermath to look back on; do not list them, "
                   "let the characters remember one or two): " + "; ".join(m["text"] for m in keep)]
            ko = (getattr(self, "out_reason", None) or {}).get(lose)
            if fin:
                out.append(f"HOW IT ENDED: {win} PINNED {lose}: {win} was ON TOP, holding her down, and {lose} was the "
                           f"one held down underneath until she passed out. Never the other way round.")
            elif ko:
                said = f"{lose} {ko}" if re.match(r"(?:taps|passes|gives|went|goes)\b", str(ko)) else f"{lose} was {ko}"
                out.append(f"HOW IT ENDED: {said}; " + (f"{win} was down on the ground herself, too spent to rise."
                                                         if win in self.downed else f"{win} was left standing over her."))
            if tp:
                out.append(f"THE TURNING POINT: {win} was behind or level until beat {tp['beat']}, then never again")
            out.append("WHAT DECIDED IT: " + "; ".join(reasons))
            return "\n".join(out)
        rows = ["📜 FIGHT SUMMARY", "  Key moments:"]
        rows += [f"   • beat {m['beat']}: {m['text']}" + (f" (−{m['loss']:.0f}%)" if m["loss"] >= 1 else "")
                 for m in keep] or ["   • (nothing out of the ordinary)"]
        if fin:
            how = {"choking": {"blood": "the blood choke", "air": "the choke on her windpipe",
                               "both": "the choke (air and blood)"}.get(fin.get("kind"), "the choke"),
                   "constriction": "the constriction"}.get(fin.get("cause"), "the pain")
            length = (f"{fin['beats']} beats" if fin.get("fade") and fin.get("beats") else
                      f"{fin['seconds']} seconds" if fin.get("seconds") else "")
            rows.append(f"  Finish: {win} pinned {lose}" + (f" for {length}" if length else "") + f"; {how}"
                        + (f" ({fin['part']})" if fin.get("part") else "") + " put her out at "
                        + ((f"{fin['strength']:.0f}% strength" + (", past her limit" if fin["strength"] < 0 else ""))
                           if fin.get("strength") is not None else "the end"))
        if tp:
            rows.append(f"  Turning point: beat {tp['beat']} — {win} took the lead for good"
                        + (f" ({tp['win']:.0f}% vs {tp['lose']:.0f}%)" if tp.get("win") is not None else ""))
        else:
            rows.append(f"  Turning point: none — {win} was ahead from the first beat")
        rows.append("  Damage dealt: " + ", ".join(f"{n} {dealt.get(n, 0):.0f}%" for n in names))
        b = ch.get("biggest")
        if b:
            rows.append(f"  Biggest blow: beat {b['beat']}, " + (f"{poss_word(b['to'])} landing on her {b['part']}"
                        if b["move"] == "the landing" else
                        f"{poss_word(b['who'])} {b['move']} on {poss_word(b['to'])} {b['part']}") + f" (−{b['pct']:.0f}%)")
        if worst:
            rows.append(f"  {poss_word(lose)} worst injuries: " + "; ".join(
                f"{p.name.lower()} ({tier_for(p.damage, pain_tiers(self.rules))['label']}"
                + (f", from {causes(p)}" if causes(p) else "") + ")" for p in worst))
        rows.append("  Pins / escapes: " + ", ".join(f"{n} {pins.get(n, 0)} / {esc.get(n, 0)}" for n in names))
        rows.append("  What decided it: " + ("; ".join(reasons) or "a long grind"))
        return "\n".join(rows)

    DEV_REASONS = {
        "position": "the position: {why}, she had no way to roll with it, twist away, or soften it, and it caught her "
                    "exactly where and when she could least take it",
        "weak_point": "a weak point in a weak point: it found the one place on her already-ruined {part} where the "
                      "damage was deepest, and drove straight into it",
        "angle": "the perfect angle and timing: it caught her mid-breath, mid-step, at the exact angle and instant that "
                 "let the whole force go in with nothing wasted",
        "ground": "the landing found every sore spot at once: she came down so that every part already hurt hit "
                  "first ({parts}), all of them together",
    }

    def _devastating_roll(self, a, d, move, plan):
        """Very rarely a blow lands DEVASTATINGLY (moves.devastating): x mult, and the health cap is much looser for
        it, so it can swing the fight. Likelier when there is a reason: she is caught open, or it lands on a part that
        was already badly hurt. Returns {"mult", "reason", "why"} or None."""
        cfg = (self.rules.get("moves") or {}).get("devastating") or {}
        if not cfg.get("enabled", True) or not plan:
            return None
        part = d.parts.get(plan[0]) if plan[0] in d.parts else None
        vu = self.vulnerable(a, d, move)
        ch = float(cfg.get("chance", 0.015))
        reason, why = "angle", ""
        if part is not None and part.damage >= 300:
            ch *= float(cfg.get("weak_point_mult", 2.0)); reason = "weak_point"
        elif part is not None and part.damage >= 150:
            ch *= float(cfg.get("hurt_part_mult", 1.4)); reason = "weak_point"
        if vu:
            ch *= float(cfg.get("open_mult", 2.0))
            if reason != "weak_point" or self.rng.random() < 0.5:
                reason, why = "position", vu[0]
        ch *= self.trait(a, "striking")
        q = self.quirk(a, "ambusher")
        if q and move.get("name") in (q.get("moves") or ["Sucker Punch", "Night Slash"]) and (
                d.name in self.downed or any(self.has(d, st) for st in ("staggered", "off_balance", "dazed", "flinched"))):
            ch *= float(q.get("mult", 2.5)); reason, why = "position", why or "caught open"
            self._ambush_try = (a.name, d.name)
        q = self.quirk(d, "disaster_sense")
        if q:
            ch *= float(q.get("mult", 0.6))      # (she feels the worst ones coming)
        ch = min(float(cfg.get("max_chance", 0.1)), ch)
        if self.__dict__.get("_force_dev") and not self.__dict__.get("_force_dev_used"):
            self._force_dev_used = True     # your direction asked for a devastating blow: this one is it
            self.rolls.append({"what": f"{poss_word(a.name)} {move['name']} landing devastatingly (your direction)",
                               "chance": 1.0, "roll": 0.0, "ok": True, "result": "DEVASTATING"})
        elif not self._chance(ch, f"{poss_word(a.name)} {move['name']} landing devastatingly", "DEVASTATING", "no"):
            self._ambush_try = None
            return None
        if getattr(self, "_ambush_try", None) == (a.name, d.name):
            self.quirk_moment(a, "ambusher", f"{a.name} waited for {d.name} to be caught open, and struck the instant "
                                             f"she was: this is how she likes to win")
        self._ambush_try = None
        lo, hi = cfg.get("mult", [1.7, 2.2])
        mult = round(self.rng.uniform(float(lo), float(hi)), 2)
        text = self.DEV_REASONS[reason].format(why=why or "caught open", part=(plan[0] or "").lower(), parts="")
        return {"mult": mult, "reason": reason, "why": text, "part": plan[0]}

    def _devastating_landing(self, d, plan):
        """A hard landing that, very rarely, finds every sore spot on her body at once (moves.devastating.ground_chance,
        only when she has two or more hurt parts): the landing goes onto the hurt parts, x mult."""
        cfg = (self.rules.get("moves") or {}).get("devastating") or {}
        sore = sorted((p for p in d.parts.values() if p.damage >= 150), key=lambda p: -p.damage)
        if not cfg.get("enabled", True) or len(sore) < 2 or not plan:
            return None
        ch = float(cfg.get("ground_chance", 0.05)) * (1.5 if len(sore) >= 4 else 1.0)
        if not self._chance(min(0.12, ch), f"the landing finding every sore spot on {d.name}", "DEVASTATING", "no"):
            return None
        n = max(len(plan[0][1]), 2)
        worst = [p.name for p in sore[:max(n, 3)]]
        new = [(plan[0][0], worst, plan[0][2])] + list(plan[1:])
        lo, hi = cfg.get("ground_mult", [1.5, 1.9])
        mult = round(self.rng.uniform(float(lo), float(hi)), 2)
        return {"mult": mult, "reason": "ground", "plan": new, "part": worst[0],
                "why": self.DEV_REASONS["ground"].format(parts=", ".join(p.lower() for p in worst), why="", part="")}

    def _recoil(self, a, move, math):
        """Reckless moves hurt the one who uses them when they land (moves.recoil: move name -> share of its power,
        or "recoil" on the move itself): the jolt comes back into her head, shoulders and chest."""
        cfg = (self.rules.get("moves") or {}).get("recoil") or {}
        share = move.get("recoil", (cfg.get("moves") or {}).get(move["name"]))
        if not cfg.get("enabled", True) or not share:
            return None
        # the jolt runs through the skull, neck, shoulders and chest: not into an eye, an ear or the nose
        front = [p for p in a.parts if body_region(p) in ("head", "shoulder", "chest", "neck")
                 and not re.search(r"\b(?:eye|ear|nose)s?\b", p, re.I)] or list(a.parts)
        self.rng.shuffle(front)
        power = round(math["effective"] * float(share), 2)
        keep, self._source = self._source, f"the recoil of her own {move['name']}"
        hits = [self._apply_damage(a, front[0], power)] + ([self._apply_damage(a, front[1], round(power * 0.5, 2))]
                                                            if len(front) > 1 else [])
        self._source = keep
        return {"power": power, "hits": hits}

    def _missed_charge(self, a, d, move, math, charge_into=""):
        """A charge that finds nothing to hit (dodged, or turned aside) may carry the charger on into whatever is
        behind (moves.missed_charge): she slams into it herself. The faster and heavier the charge, the worse."""
        cfg = (self.rules.get("moves") or {}).get("missed_charge") or {}
        if not cfg.get("enabled", True):
            return None
        ch = float(cfg.get("aimed_chance", 0.6) if charge_into else cfg.get("chance", 0.3))
        if not self._chance(ch, f"{a.name} carried on past by her missed {move['name']}", "she crashes", "she pulls up"):
            return None
        props = (getattr(self, "scene_cfg", None) or {}).get("props") or []
        surface = charge_into or (self.rng.choice(props) if props and self.rng.random() < 0.7 else self.scene_word("ground"))
        front = [p for p in a.parts if body_region(p) in ("head", "shoulder", "chest", "neck", "fore_up")] or list(a.parts)
        self.rng.shuffle(front)
        power = round(math["effective"] * float(cfg.get("power_share", 0.4)), 2)
        keep, self._source = self._source, f"{surface} (her own missed {move['name']})"
        hits = [self._apply_damage(a, p, power if i == 0 else round(power * 0.6, 2)) for i, p in enumerate(front[:2])]
        self._source = keep
        out = {"surface": surface, "power": power, "hits": hits}
        if self._chance(float(cfg.get("down_chance", 0.3)), f"{a.name} going down after crashing into {surface}",
                        "she goes down", "she stays up"):
            out["facing"] = self.knock_down(a.name, why=f"{a.name} crashed into {surface} with her own charge")
            out["down"] = True
        return out

    def wing_damage(self, f):
        """The worse of her wings (0 for a fighter without wings)."""
        wings = [p.damage for p in f.parts.values() if "wing" in p.name.lower()]
        return max(wings) if wings else 0.0

    def can_fly(self, f, why=False):
        """A fighter with wings, free to take off. A hurt wing still lifts her, at a cost (flight.strain); a shredded one
        (strain.max_wing) grounds her only if strain.max_wing_grounds is on. Nearly spent, she may try and fail
        (flight.weak_takeoff, rolled in take_off)."""
        cfg = self.rules.get("flight") or {}
        reason = None
        if not any("wing" in p.lower() for p in f.parts):     # a bird, or a winged dragon with arms too
            reason = f"{f.name} has no wings"
        elif (cfg.get("strain") or {}).get("max_wing_grounds", False) \
                and self.wing_damage(f) >= float((cfg.get("strain") or {}).get("max_wing", 600)):
            reason = f"{poss_word(f.name)} wings are shredded: they can't lift her at all"
        elif f.name in self.downed or self.pinned_by(f.name) or self.pinning(f.name):
            reason = f"{f.name} has to be up and free to take off"
        elif any(h.defender == f.name for h in self.holds.values()):
            reason = f"{f.name} is being held"
        elif any(self.has(f, st) for st in ("asleep", "frozen", "paralyzed", "constricted")):
            reason = f"{f.name} can't take off like this"
        elif f.energy < self.takeoff_cost(f):
            reason = f"{f.name} is too winded to take off"
        return reason if why else reason is None

    def takeoff_cost(self, f):
        """Energy to take off: flight.takeoff_energy, more with a hurt wing (flight.strain: energy_per_100 more for
        every 100% of damage on her worse wing past `from`)."""
        cfg = self.rules.get("flight") or {}
        st = cfg.get("strain") or {}
        over = max(0.0, self.wing_damage(f) - float(st.get("from", 100)))
        return float(cfg.get("takeoff_energy", 8)) * min(float(st.get("energy_max_mult", 2.0)),
                                                         1 + float(st.get("energy_per_100", 1.0)) * over / 100)

    def _wing_strain_tick(self):
        """Flying on a badly hurt wing tears it further: each beat in the air with her worse wing past flight.strain
        `from`, that wing takes damage (more, the worse it is). Her choice to stay up costs her."""
        st = (self.rules.get("flight") or {}).get("strain") or {}
        events = []
        for f in self.active():
            if not self.has(f, "airborne"):
                continue
            wings = [p for p in f.parts.values() if "wing" in p.name.lower()]
            if not wings:
                continue
            worst = max(wings, key=lambda p: p.damage)
            if worst.damage < float(st.get("from", 100)):
                continue
            self._source = f"{poss_word(f.name)} straining her hurt wing to stay up"
            # (counted only up to power_cap_at %: past it, the strain stops growing with the wing's own damage)
            power = round(float(st.get("power", 6)) * min(worst.damage, float(st.get("power_cap_at", 250))) / 100, 2)
            hit = self._apply_damage(f, worst.name, power)
            events.append({"type": "wing_strain", "fighter": f.name, "part": worst.name, "power": power,
                           "hits": [hit], "tags": self._tags([hit])})
        return events

    def take_off(self, name, enforce=True):
        """She takes to the air (flight.airborne_beats beats, then she has to come down to rest her wings). Every grip
        she had on anyone lets go."""
        f = self.get_active(name)
        why = self.can_fly(f, why=True)
        if why and enforce:
            raise ValueError(why + " (only a winged fighter who is up and free can 'take off')")
        cfg = self.rules.get("flight") or {}
        cost = self.takeoff_cost(f)
        f.energy = max(0.0, f.energy - cost)
        wt = cfg.get("weak_takeoff") or {}
        pct = self._health_pct(f)
        if wt.get("enabled", True) and pct < float(wt.get("below", 10)):
            # nearly spent: her wings can still lift her, but it is a struggle she often loses
            lo, hi = float(wt.get("at_zero", 0.05)), float(wt.get("at_below", 0.3))
            ch = lo + (hi - lo) * max(0.0, pct) / max(1.0, float(wt.get("below", 10)))
            if not self._chance(ch, f"{f.name} getting off the ground", "she lifts off", "she can't"):
                self.involved.add(f.name)
                return {"type": "take_off_failed", "fighter": f.name, "energy": round(cost, 1),
                        "hurt_wing": self.wing_damage(f) >= float((cfg.get("strain") or {}).get("from", 100))}
        # every grip she had lets go as she lifts away, and the screen and the story are told so
        loose = self._lose_grip(f.name, f"{f.name} took off")
        beats = int(cfg.get("airborne_beats", 3)) + self.flight_vigour(f, "extra_beats", 0)
        self._set_air_speed(f, 0)      # a fresh climb: no speed built yet
        self.set_status(f, "airborne", beats)
        self.involved.add(f.name)
        return {"type": "take_off", "fighter": f.name, "beats": beats, "energy": round(cost, 1),
                "hurt_wing": self.wing_damage(f) >= float((cfg.get("strain") or {}).get("from", 100)),
                "knock_on": loose}

    def flight_vigour(self, f, key, default):
        """flight.vigour: a flyer who is still strong flies more (longer in the air, back up after a dive more often;
        the director is pointed at taking off more often too). `key` from the band her strength is in: healthy (at or
        above healthy_at % of her full strength), fair (at or above fair_at), else low."""
        cfg = (self.rules.get("flight") or {}).get("vigour") or {}
        if not cfg.get("enabled", True):
            return default
        pct = self._health_pct(f)
        band = ("healthy" if pct >= float(cfg.get("healthy_at", 60)) else
                "fair" if pct >= float(cfg.get("fair_at", 35)) else "low")
        val = (cfg.get(band) or {}).get(key, default)
        return type(default)(val) if isinstance(default, (int, float)) else val

    def air_speed(self, f):
        """Passes she has built up in the air (flight.speed): every dive she lands and climbs back from adds one, up
        to max_passes; each makes her next dive land harder. Only while she is airborne."""
        if not self.has(f, "airborne"):
            return 0
        return int((self.__dict__.get("air_passes") or {}).get(f.name, 0))

    def _set_air_speed(self, f, n):
        sp = (self.rules.get("flight") or {}).get("speed") or {}
        book = self.__dict__.setdefault("air_passes", {})
        book[f.name] = max(0, min(int(sp.get("max_passes", 3)), int(n))) if sp.get("enabled", True) else 0

    def _strafe(self, a, d, res, math):
        """flight.strafe: her speed carries her round for a second, quicker pass before she climbs away: one more
        blow, lighter than the dive, on another part of the one she dove at. More often while she is strong."""
        cfg = (self.rules.get("flight") or {}).get("strafe") or {}
        if not cfg.get("enabled", True) or d.eliminated or self.pinned_by(d.name) or a.energy < 5:
            return
        ch = float(cfg.get("chance", 0.3)) * self.flight_vigour(a, "strafe_mult", 1.0)
        if not self._chance(min(0.9, ch), f"{a.name} coming round for a strafing pass", "she strafes", "no"):
            return
        struck = {h["part"] for h in res.get("hits") or []}
        options = [p for p in d.parts if p not in struck] or list(d.parts)
        part = self.rng.choice(options)
        power = round(float(math.get("effective", 0)) * float(cfg.get("power", 0.35)), 2)
        self._source = f"{poss_word(a.name)} strafing pass"
        h = self._apply_damage(d, part, power)
        h["strafe"] = True
        res["hits"] = list(res.get("hits") or []) + [h]
        res["strafe"] = {"part": part, "power": power}
        a.energy = max(0.0, a.energy - float(cfg.get("energy", 3)))

    def _leap_after(self, a, d, res, spot, landed):
        """She climbed {spot} and leapt at the flyer (flight.leap). Reached: the blow lands with her weight in it, she
        may drag the flyer down out of the air with her (drag_down), and she comes down hard on her feet (a light
        landing on her legs). Fell short (or the flyer got out of the way): she drops from the height and lands badly
        (the director adds the landing: leap_fall)."""
        cfg = (self.rules.get("flight") or {}).get("leap") or {}
        a.energy = max(0.0, a.energy - float(cfg.get("energy", 10)))
        res["leap"] = {"from": spot, "reached": landed}
        if not landed:
            res["leap_fall"] = str(cfg.get("miss_landing", "heavy"))
            return
        if self.has(d, "airborne") and not d.eliminated and self._chance(
                float(cfg.get("drag_down", 0.35)), f"{a.name} dragging {d.name} down out of the air with her",
                "she drags her down", "no"):
            d.status.pop("airborne", None)
            self._set_air_speed(d, 0)
            res["leap"]["dragged"] = True
            res["grounded"] = True
            res["auto_launch"], res["drop_severity"] = "launched", str(cfg.get("drag_landing", "solid"))
        # her own landing, on her feet: it jars her legs
        legs = [p for p in a.parts if body_region(p) in ("hind_up", "hind_low", "leg", "foot", "fore_low")
                or re.search(r"foot|feet|paw|knee|hock|ankle|thigh|leg", p, re.I)] or list(a.parts)
        sev = str(cfg.get("hit_landing", "light"))
        power = self.power_for("instant", sev)
        mine, self._source = self._source, f"the drop from {spot}"
        res["leap"]["landing_hits"] = [self._apply_damage(a, p, power) for p in self.rng.sample(legs, min(2, len(legs)))]
        self._source = mine

    def keeps_feet(self, d, hits):
        """down.keep_feet: a blow the director has knock her down ("knocked down") may not take her off her feet:
        she staggers and stays up. The chance comes from her strength left (full, half, empty, in between), x a
        light blow's more (a blow taking under big_blow_pct of her full health is light: up to x light_mult) or a
        big one's less (down to x big_mult), never above max. A throw, a launch and a crash into the scenery are
        not rolled. Returns (kept her feet, chance)."""
        cfg = (self.rules.get("down") or {}).get("keep_feet") or {}
        if not cfg.get("enabled", True):
            return False, 0.0
        pct = max(0.0, min(100.0, self._health_pct(d)))
        full, half, empty = (float(cfg.get(k, v)) for k, v in (("full", 0.5), ("half", 0.35), ("empty", 0.25)))
        ch = half + (full - half) * (pct - 50) / 50 if pct >= 50 else empty + (half - empty) * pct / 50
        lost = sum(float(h.get("health_loss") or 0) for h in hits or () if h.get("defender", d.name) == d.name)
        share = lost / max(1.0, d.max_health) * 100 / max(0.1, float(cfg.get("big_blow_pct", 10)))
        lm, bm = float(cfg.get("light_mult", 1.4)), float(cfg.get("big_mult", 0.5))
        ch *= max(bm, lm - (lm - bm) * min(1.0, share))
        ch = max(0.0, min(float(cfg.get("max", 0.75)), ch))
        return (ch > 0 and self._chance(ch, f"{d.name} keeping her feet under the blow", "she stays up",
                                        "she goes down")), round(ch, 2)

    def _rights_herself(self, d, move, launch, fcfg):
        """A flyer the blow would hurl (a launch effect) may catch herself on her wings before she hits the ground
        (flight.air_recover): likelier the stronger she is and the sounder her wings. A move that always throws (a
        launch at 100%, a seize-and-throw) can't be ridden out."""
        cfg = fcfg.get("air_recover") or {}
        if not cfg.get("enabled", True) or any(e.get("launch") == launch and float(e.get("chance", 1)) >= 1
                                               for e in move.get("effects", [])):
            return False
        pct = max(0.0, min(100.0, self._health_pct(d)))
        hm = cfg.get("by_strength") or {}
        full, half, empty = (float(hm.get(k, v)) for k, v in (("full", 0.6), ("half", 0.3), ("empty", 0.0)))
        ch = half + (full - half) * (pct - 50) / 50 if pct >= 50 else empty + (half - empty) * pct / 50
        ch /= 1.0 + self.wing_damage(d) / float(cfg.get("wing_halves_at", 300))
        return ch > 0 and self._chance(min(0.9, ch), f"{d.name} catching herself on her wings", "she rights herself",
                                       "she falls")

    @staticmethod
    def _fall_damage(hits, share):
        """How hard a blow's hits shake a flyer, for knock_from_air: the worst hit in full and the rest at `share`
        (a gust over her whole body is not a blow that crushes one wing), each as it would be at the default scale
        of 3 (a higher /scale makes every number bigger, and must not by itself bring flyers down more often)."""
        dmg = sorted((h.get("damage_taken", 0) * 3.0 / max(0.5, float(h.get("scale") or 3)) for h in hits), reverse=True)
        return (dmg[0] + share * sum(dmg[1:])) if dmg else 0.0

    def _air_pass(self, a, d, res, landed):
        """Two flyers meet in the air (flight.air_pass): they cross at speed, so the one struck may rake back at the
        other as they pass (rake_back, more often while she is strong), and a pass that lands builds the attacker's
        speed for the next one, as a dive does. Both stay up."""
        cfg = (self.rules.get("flight") or {}).get("air_pass") or {}
        res["air_pass"] = True
        if landed:
            self._set_air_speed(a, self.air_speed(a) + 1)
            res["air_speed"] = self.air_speed(a)
        if d.eliminated or res.get("grounded") or any(self.has(d, st) for st in ("asleep", "frozen", "paralyzed", "flinched")):
            return     # (knocked out of the sky by it, she is falling, not crossing)
        ch = float(cfg.get("rake_back", 0.3)) * self.flight_vigour(d, "strafe_mult", 1.0)
        if not self._chance(min(0.8, ch), f"{d.name} raking back at {a.name} as they cross", "she rakes back", "no"):
            return
        reach = [p for p in a.parts if not re.search(r"\bhead\b|horn|antenna|ear|eye|nose", p, re.I)] or list(a.parts)
        power = round(self.power_for("instant", self._cfg("evasion").get("counter_severity", "solid"))
                      * float(cfg.get("momentum", 1.2)), 2)
        mine, self._source = self._source, f"{poss_word(d.name)} blow as they crossed in the air"
        res["air_rake"] = {"by": d.name, "hits": [self._apply_damage(a, self.rng.choice(reach), power)]}
        self._source = mine
        self.involved.add(d.name)

    def _after_dive(self, a, d, res, landed):
        """A dive is done: the defender may catch her as she comes in and drag her out of the air
        (flight.counter_grab); otherwise she climbs back up (flight.climb_chance) or comes down to land."""
        cfg = self.rules.get("flight") or {}
        res["dive"], res["dive_mult"] = True, float(cfg.get("dive_mult", 1.3))
        if (landed and d.name not in self.downed and not self.pinned_by(d.name)
                and not any(self.has(d, st) for st in ("asleep", "frozen", "paralyzed", "flinched", "constricted"))
                and self._chance(float(cfg.get("counter_grab", 0.15)), f"{d.name} catching {a.name} as she dives",
                                 "she catches her", "no")):
            a.status.pop("airborne", None)
            res["dragged_down"] = {"by": d.name, "facing": self.knock_down(a.name, why=f"{a.name} was dragged out of the air")}
            return
        dc = cfg.get("dive_counter") or {}
        if (landed and dc.get("enabled", True) and d.name not in self.downed and not self.pinned_by(d.name)
                and not d.eliminated
                and not any(self.has(d, st) for st in ("asleep", "frozen", "paralyzed", "flinched", "constricted"))
                and self._chance(float(dc.get("on_hit", 0.1)), f"{d.name} striking back as {a.name} goes past",
                                 "she strikes back", "no")):
            # she takes the dive and still gets a blow in as the flyer streaks by
            reach = [p for p in a.parts if not re.search(r"\bhead\b|horn|antenna|ear|eye|nose", p, re.I)] or list(a.parts)
            power = round(self.power_for("instant", self._cfg("evasion").get("counter_severity", "solid"))
                          * float(dc.get("momentum", 1.25)), 2)
            mine, self._source = self._source, f"{poss_word(d.name)} blow as {a.name} went past"
            res["pass_counter"] = {"by": d.name, "hits": [self._apply_damage(a, self.rng.choice(reach), power)]}
            self._source = mine
            self.involved.add(d.name)
        climb = min(0.95, float(cfg.get("climb_chance", 0.55)) * self.flight_vigour(a, "climb_mult", 1.0))
        if self._chance(climb, f"{a.name} climbing back up after the dive", "back up", "she lands"):
            self.set_status(a, "airborne", max(a.status.get("airborne", 0), 2))
            res["climbs"] = True
            if landed:      # her speed builds: the next dive comes in harder (flight.speed)
                self._set_air_speed(a, self.air_speed(a) + 1)
                res["air_speed"] = self.air_speed(a)
        else:
            a.status.pop("airborne", None)
            self._set_air_speed(a, 0)
            res["lands_after_dive"] = True

    def pummel_place(self, attacker, defender):
        """Where `attacker` can rain short blows on `defender` at no distance, or None: "grab" (her grab on her, both
        standing), "pin" (from on top, in her pin), "against" (she is pressed against the scenery from a charge),
        "down" (she is on the ground, sitting or lying, and the attacker is over her or down beside her)."""
        a, d = self.get(attacker).name, self.get(defender).name
        if self.pinned_by(a):
            return None                      # pinned herself: she can hit her pinner, not pummel her
        if self.grabbed_by(a, d):
            return "grab"
        if self.has(self.get(a), "airborne"):
            return None                      # in the air: a dive is one drop and she climbs away, not a flurry over her
        if d in self.pinning(a):
            # blows rained down inside a pin: not how a pin usually goes (grapple.pummel_in_pin, off by default)
            return "pin" if self.rules.get("grapple", {}).get("pummel_in_pin", False) else None
        if d in self.pressed and a not in self.downed:
            return "against"
        if d in self.downed and not self.pinned_by(d):
            return "down"
        return None

    def grapple(self, attacker, defender, part, power, with_part="", flavor="", enforce=False):
        """One fighter SEIZES another and keeps hold of her, both on their feet: a paw locked on an arm, jaws in the
        scruff, tails round a wrist. It is a hold that squeezes only lightly; what it does is keep her at
        point-blank. While it lasts neither of the two can dodge the other, the one holding can rain short blows on
        her (several in a beat) or hold a stream on her at no distance, and a throw or a slam can't be slipped.
        The held fighter rolls to wrench free every beat (more easily than out of a clamp) and can hit back.
        The director's grab can be slipped like any attack; your own command always takes hold."""
        a, d = self.get_active(attacker), self.get_active(defender)
        if a is d:
            raise ValueError(f"{a.name} can't grab herself")
        for who, why in ((a, "grab anyone"), (d, "be grabbed like this")):
            if enforce and who.name in self.downed:
                raise ValueError(f"{who.name} is on the ground: a grapple is between two fighters on their feet. Use a "
                                 f"hold or a pin on a fighter who is down" if who is d else
                                 f"{who.name} is on the ground: she has to be on her feet to {why}")
        if any(p["defender"] in (a.name, d.name) for p in self.pins.values()):
            raise ValueError("there is a pin going on: no grapple until it ends")
        tumble = enforce and self._air_grab_ok(a, d)
        if enforce and not tumble and (self.has(d, "airborne") or self.has(a, "airborne")):
            raise ValueError(f"{(d if self.has(d, 'airborne') else a).name} is in the air: no grabbing until she comes down"
                             + (" (she can grab another flyer up there only with talons, feet, hands or arms to grab with)"
                                if self.has(d, "airborne") and self.has(a, "airborne") and self._air_grab_cfg().get(
                                    "enabled", True) else ""))
        if enforce and a.name in self.pressed:
            raise ValueError(f"{a.name} is still pressed against the scenery: she can't grab anyone this beat")
        if self.grabbed_by(a.name, d.name):
            raise ValueError(f"{a.name} already has hold of {d.name}: strike her, throw her, or let go")
        if enforce:
            self._regrab_check(a, d)
        coil_note = ""
        if enforce and self.coil_scope(d.part(part).name) == "limb":
            # (holds.coil.size, since build 275) a serpent that dwarfs her seizes her in a loop round her middle, not
            # round one paw
            cs, coil_note = self.coil_body_first(a.name, d.name, [(d.part(part).name, power, 0.0, with_part)],
                                                 flavor=flavor, keep_limbs=0)
            if coil_note:
                part, with_part = cs[0][0], cs[0][3]
                flavor = f"a loop of her coils thrown round {poss_word(d.name)} middle"
        before = a.energy
        if enforce:
            self._can_act(a, True)
            self._no_friendly_fire(a, [d], True)
            self._spend(a, float(self._cfg("energy").get("costs", {}).get("grapple", 6)), True, "a grab")
            dodge = self.dodge_roll(a, d, "targeted")
            if dodge:
                self._attacked(a.name, [d.name], landed=False)
                return {"type": "instant", "attacker": a.name, "defender": d.name, "defenders": [d.name],
                        "flavor": flavor or "a grab at her", "grapple": True,
                        "energy": [round(before), round(a.energy)], "hit_count": 0, "hits": [], "tags": [], **dodge}
        for st in ("asleep", "frozen"):
            if not enforce:
                a.status.pop(st, None)
        # (the director's grab in the air is refused above, unless it is talons locking on in the air: flight.air_grab)
        grounded = self._out_of_air((a, d), "the grab: locked together in the air, the two of them tumble down"
                                    if tumble else "the grab")
        for k in grounded if tumble else ():
            k["tumble"] = True
        pname = d.part(part).name
        # the grab she already had on her from the other side ends: you can't be held by her and holding her at once
        # (said on screen and in the story: knock_on)
        reversed_ = [self.release(h.id, "reversed: the grab turned round on her")
                     for h in [h for h in list(self.holds.values()) if h.grab and h.attacker == d.name
                               and h.defender == a.name]]
        st = self.start_hold(a.name, d.name, pname, power, 0.0, flavor, with_part, keep_with=enforce)
        self.holds[st["hold_id"]].grab = True
        if d.name in self.downed:
            # your own /grapple on a fighter who is lying down: it is an ordinary grip on her until she is up (a grab
            # only locks two fighters who are both on their feet), and she lies so that the gripped part can be reached
            self._settle_facing(d.name, parts_win=True)
            pname = self.holds[st["hold_id"]].part if st["hold_id"] in self.holds else pname
        self._attacked(a.name, [d.name], landed=True)
        self.involved.update({a.name, d.name})
        return {"type": "grapple_start", "attacker": a.name, "defender": d.name, "defenders": [d.name],
                **({"coil_moved": coil_note} if coil_note else {}),
                "part": pname, "with": st.get("with", ""), "power": st["power"], "hold_id": st["hold_id"],
                "hold_ids": [] if st.get("existing") else [st["hold_id"]], "existing": bool(st.get("existing")),
                "flavor": flavor, "energy": [round(before), round(a.energy)],
                "break_chance": self.hold_break_chance(a.name, d.name), "knock_on": grounded + reversed_}

    def _air_grab_cfg(self):
        return (self.rules.get("flight") or {}).get("air_grab") or {}

    def _air_grab_ok(self, a, d):
        """flight.air_grab: two flyers both in the air, and the one grabbing has something to grab with up there
        (talons, feet, or the hands and arms some flyers have): she can lock on in the air, and the two of them come down together."""
        cfg = self._air_grab_cfg()
        if not cfg.get("enabled", True) or not (self.has(a, "airborne") and self.has(d, "airborne")):
            return False
        return any(re.search(cfg.get("grip_parts", r"\btalons?\b|\bfeet\b|\bfoot\b|\bclaws?\b|\bhands?\b|\bpaws?\b|\barms?\b"), p, re.I)
                   for p in a.parts)

    def _out_of_air(self, fighters, what):
        """A grab or a pin happens on the ground: any of `fighters` still flying comes down for it. Returns a knock_on
        event for each, for the screen and the story."""
        out = []
        for f in fighters:
            if self.has(f, "airborne"):
                f.status.pop("airborne", None)
                self._set_air_speed(f, 0)
                out.append({"type": "out_of_air", "fighter": f.name, "why": what})
        return out

    def pin_securable(self, f):
        """With pin.secure enabled, a pin can only be WON once the pinned fighter is worn down enough: at least
        min_parts body parts at part_damage or more, and strength at or below max_strength %."""
        cfg = self.rules.get("pin", {}).get("secure", {})
        if not cfg.get("enabled", False):
            return True, ""
        need_parts, dmg = int(cfg.get("min_parts", 6)), float(cfg.get("part_damage", 150))
        max_s = float(cfg.get("max_strength", 50))
        have = sum(1 for p in f.parts.values() if p.damage >= dmg)
        why = []
        if have < need_parts:
            why.append(f"{have} of {need_parts} parts at {dmg:.0f}%+")
        if self.strength(f) > max_s:
            why.append(f"strength {self.strength(f):.0f}% (needs {max_s:.0f}% or less)")
        return (not why), "; ".join(why)

    def heal(self, name, parts, amount, resistance=0.0, health=0.0, how=""):
        """Your heal command: take `amount` damage off each chosen body part (never below 0), give back up to
        `resistance` resistance (never above where it started), and restore `health` (never above max)."""
        f = self.get_active(name)
        if parts == "all":
            chosen = list(f.parts.values())
        elif parts == "worst":
            chosen = sorted(f.parts.values(), key=lambda p: -p.damage)[:3]
        else:
            chosen = [f.part(p) for p in parts]
        changes = []
        for p in chosen:
            if amount <= 0 and resistance <= 0:
                break
            d0, r0 = p.damage, p.resistance
            p.damage = max(0.0, p.damage - amount)
            p.resistance = min(p.start_resistance, p.resistance + resistance)
            if (d0, r0) != (p.damage, p.resistance):
                changes.append({"part": p.name, "damage_before": round(d0, 2), "damage_after": round(p.damage, 2),
                                "res_before": round(r0, 2), "res_after": round(p.resistance, 2)})
        h0 = f.health
        f.health = min(f.max_health, f.health + max(0.0, health))
        return {"type": "heal", "fighter": f.name, "parts": changes, "health_before": round(h0, 2),
                "health_after": round(f.health, 2), "max_health": f.max_health, "flavor": how}

    def force_get_up(self, name, tries=None):
        """Stand a fighter up now (your command). tries: 1-3, or worked out from her condition."""
        f = self.get_active(name)
        on_top = self.pinned_by(f.name)
        if on_top:
            raise ValueError(f"{f.name} is pinned under {on_top[0]}: she can't just get up. End the pin first "
                             f"(/pinescape {on_top[0]} {f.name}, or /release {on_top[0]} {f.name})")
        self.downed.pop(f.name, None)
        self.facing.pop(f.name, None)
        self._fresh_down.discard(f.name)
        if tries is None:
            self.downed[f.name] = 0
            ev = next((x for x in self.get_up_tick_for(f.name)), None)
            tries = min(3, ev["tries"]) if ev else 1
            self.downed.pop(f.name, None)
        plan = self.body_plan(f)
        limbs = sorted((p for p in f.parts.values() if body_region(p.name) in (
            ("tail", "belly", "back_low") if plan == "serpent" else ("hind_up", "hind_low", "fore_up", "fore_low"))),
            key=lambda p: -p.damage)
        props = self.scene_props()
        return {"type": "get_up", "fighter": f.name, "plan": plan, "grab": self.rng.choice(props), "beats_down": 0,
                "tries": max(1, min(3, int(tries))), "stands": True,
                "hurting": [p.name for p in limbs[:2] if p.damage >= 30], "forced": True}

    def get_up_tick_for(self, name):
        """Roll one get-up for a single fighter without touching anyone else (used by /getup)."""
        keep = {k: v for k, v in self.downed.items() if k != name}
        fresh = set(self._fresh_down)
        self.downed = {name: self.downed.get(name, 0)}
        self._fresh_down = set()
        state = self.rng.getstate()
        try:
            return self.get_up_tick()
        finally:
            self.rng.setstate(state)
            self.downed = {**keep, **{k: v for k, v in self.downed.items()}}
            self._fresh_down = fresh

    def pin_allowed(self, defender):
        """(True, "") if the pin rules allow pinning `defender` now, else (False, why)."""
        d = self.get(defender)
        cfg = self.rules.get("pin", {})
        need = int(cfg.get("attacks_between_pins", 0) or 0)
        got = self.since_pin.get(d.name, need)  # the rule is about the gap BETWEEN pins: no pin yet, no wait
        why = []
        if self.no_pins():
            if self.submission_match():
                return False, ("pins are off in this submission match (finish.submission.no_pins): only a tap-out "
                               "or a pass-out ends it, so lock a submission or a choke on her instead")
            return False, ("pins are off in this fight (knockout-only, with finish.no_pins): wear her down with "
                           "blows, grapples and submissions, and knock her out")
        if self.has(d, "airborne"):
            why.append(f"{d.name} is in the air: she has to be brought down first")
        if self.pin_window.get(d.name, True) is False:
            why.append(f"there is no opening for a pin on {d.name} this beat (openings come more often when she's "
                       f"knocked down, and far more often once she's under half strength)")
        if cfg.get("require_downed", False) and d.name not in self.downed:
            why.append(f"{d.name} is not on the ground (knock them down first: a strike with launch "
                       f"'knocked down', 'thrown' or 'launched')")
        if got < need:
            why.append(f"{d.name} has taken only {got} of the {need} attacks needed since the last pin attempt")
        return (not why), "; ".join(why)

    _WEAPON_RX = {"claws": r"\bclaws?\b|\btalons?\b|\bscratch|\brak(?:e|es|ed|ing)\b|\bswipe",
                  "teeth": r"\bbit(?:e|es|ing)?\b|\bfangs?\b|\bteeth\b|\bjaws?\b|\bcrunch",
                  "tail": r"\btails?\b", "horn": r"\bhorn|\bgore"}

    @classmethod
    def _flavor_fits_move(cls, flavor, move):
        """The director's one-line label for an attack ("claws raking down the side") is dropped when it names a
        different natural weapon from the move's own (Iron Tail is the tail): the screen and the story then use
        the move's name, and the narrator isn't told two different weapons."""
        text = str(flavor or "")
        if not text or not move:
            return text
        own = " ".join(str(move.get(k) or "") for k in ("name", "description", "about", "flavor"))
        mine = {w for w, rx in cls._WEAPON_RX.items() if re.search(rx, own, re.I)}
        said = {w for w, rx in cls._WEAPON_RX.items() if re.search(rx, text, re.I)}
        return "" if mine and said and not (said & mine) else text

    @staticmethod
    def _grip_flavor_fix(flavor, d, started):
        """The pin's one-line description is written by the director; the grips are what the engine set. When the
        line puts the jaws on a part they aren't on ("jaw lock across her throat" with the jaws on her right paw),
        it is rebuilt from the grips themselves, so the screen and the story agree."""
        text = str(flavor or "")
        jaw_rx = r"\b(?:jaws?|teeth|bit(?:e|es|ing)?|fangs?|mouth)\b"
        jaw_parts = {str(st["part"]).lower() for st in started if re.search(jaw_rx, str(st.get("with") or ""), re.I)}
        if not text:
            return text
        if not jaw_parts:
            # jaws in the line with no grip that uses them ("jaw-clamping flanks" pressed with her full weight, her
            # jaws already clamped elsewhere): rebuilt from the grips
            if not re.search(jaw_rx, text, re.I) or not started:
                return text
            bits = [f"{st.get('with') or 'pressure'} on her {str(st['part']).lower()}" for st in started]
            return ", ".join(bits[:-1]) + (" and " if len(bits) > 1 else "") + bits[-1]
        names = sorted({str(p).lower() for p in getattr(d, "parts", {})}, key=len, reverse=True)
        wrong = False
        for clause in re.split(r",|;|\band\b", text):
            if not re.search(jaw_rx, clause, re.I):
                continue
            low = clause.lower()
            named = [p for p in names if re.search(r"\b" + re.escape(p) + r"\b", low)]
            if named and not any(p in jaw_parts for p in named):
                wrong = True
            # "jaws clamp around her right forelimb" with the jaws on her LEFT upper arm: the side is wrong
            sides = set(re.findall(r"\b(left|right)\b", low))
            jaw_sides = {s for jp in jaw_parts for s in re.findall(r"\b(left|right)\b", jp)}
            if sides and jaw_sides and not (sides & jaw_sides):
                wrong = True
        if not wrong:
            return text
        bits = [f"{st.get('with') or 'pressure'} on her {str(st['part']).lower()}" for st in started]
        return ", ".join(bits[:-1]) + (" and " if len(bits) > 1 else "") + bits[-1]

    @staticmethod
    def _holder_part_fix(flavor, a, started):
        """(since build 277) The line names one of the HOLDER's own parts as the grip ("Ripples' Right Forearm Fin on
        her right hock") while every grip is made with something else (her twin tails): rebuilt from the grips."""
        text = str(flavor or "")
        if not text or not started:
            return text
        withs = " ".join(str(st.get("with") or "") for st in started).lower()
        low = text.lower()
        for p in sorted({str(x).lower() for x in getattr(a, "parts", {})}, key=len, reverse=True):
            noun = p.split()[-1]
            if len(p.split()) < 2 or not re.search(r"\b" + re.escape(p) + r"s?\b(?: \w+){0,2} (?:on|round|around|about|"
                                                   r"over|gripping|clamp\w*|lock\w*|wrapp\w*|clutch\w*|holding)\b"
                                                   r"(?! the (?:ground|floor|earth|sand|grass))", low):
                continue
            if not re.search(r"\b" + re.escape(noun.rstrip("s")) + r"s?\b", withs):
                bits = [f"{st.get('with') or 'pressure'} on her {str(st['part']).lower()}" for st in started]
                return ", ".join(bits[:-1]) + (" and " if len(bits) > 1 else "") + bits[-1]
        return text

    # what pushes rather than grips (a press with it needs something behind her to push against), what can wrap round
    # her and haul her into it, and the parts of her body a wrap round her takes in
    # (her weight is not one: bearing down on a fighter, gravity is what pushes back)
    PUSH_WITH = re.compile(r"(?i)\b(?:chest|belly|stomach|body|torso|hips?|side|flank|shoulders?|back|"
                           r"knees?|elbows?|head|forehead|brow|horn)\b")
    GRIP_WITH = re.compile(r"(?i)\b(?:paws?|forepaws?|hands?|claws?|arms?|forearms?|forelegs?|tails?|coils?|jaws?|"
                           r"teeth|fangs|legs?|hind legs|thighs|wings?|talons?|beak|fingers|crook|weight)\b")
    WRAP_WORDS = re.compile(r"(?i)\b(?:around|round|wrapp\w*|wound|encircl\w*|hugg\w*|lock\w*|clasp\w*|cinch\w*|"
                            r"squeez\w*|hauling|pulling|crush\w*)\b")
    WRAP_REGIONS = ("chest", "belly", "back_up", "back_low", "shoulder", "neck", "head")

    # what a grip's words grip with: (words, the key it is counted under, how many of it she has, a test for her parts)
    GRIP_LIMBS = (
        (r"\b(?:jaws?|teeth|fangs|mouth|bite|bit)\b", "jaws", 1, r"\b(?:jaw|muzzle|beak)\b"),
        (r"\bhind (?:paws?|legs?|feet|foot)\b|\b(?:feet|foot)\b", "feet", 2, r"\b(?:foot|hind paw)\b"),
        (r"\b(?:fore ?paws?|paws?|hands?|claws?|fingers)\b", "paws", 2, r"(?:paw|hand|claw)\b"),
        (r"\b(?:arms?|forearms?|forelegs?|elbows?)\b", "arms", 2, r"\b(?:arm|forearm|foreleg)\b"),
        (r"\b(?:legs?|thighs?|knees?|hock)\b", "legs", 2, r"\b(?:thigh|knee|hock|leg)\b"),
        (r"\btails?\b", "tails", 1, r"\btails?\b"),
        (r"\bcoils?\b", "coils", 3, r"\b(?:coil|tail|body)\b"),
        (r"\bwings?\b", "wings", 2, r"\bwing\b"),
        (r"\btalons?\b", "talons", 2, r"\b(?:talon|foot)\b"),
        (r"\bhorn\b", "horn", 1, r"\bhorn\b"),
    )
    # body regions near enough together for one limb (or a pair) to grip both
    NEAR_REGIONS = (("head", "neck", "shoulder", "chest", "back_up", "fore_up"),
                    ("chest", "belly", "back_up", "back_low", "fore_up", "fore_low", "hind_up", "shoulder"),
                    ("back_low", "belly", "hind_up", "hind_low", "tail"),
                    ("shoulder", "fore_up", "fore_low"))
    SMALL_MAIN = re.compile(r"(?i)\b(?:ear|nose|cheek|eye|whiskers?|nostril|lip)\b")

    def grip_limb(self, f, with_):
        """What a grip's words grip with: (key, how many she has of it, her parts it is), or None (a press, or no
        limb named). 'both paws' or a pair named counts as two; a side named ('her right paw') keeps to that side.
        Twin tails count as one pair (two)."""
        w = str(with_ or "").lower()
        for rx, key, cap, part_rx in self.GRIP_LIMBS:
            if re.search(rx, w):
                mine = [n for n in f.parts if re.search(part_rx, n.lower()) and not (key == "paws" and "hind" in n.lower())]
                side = next((s for s in ("left", "right") if re.search(r"\b" + s + r"\b", w)), None)
                if side:
                    mine = [n for n in mine if n.lower().startswith(side)] or mine
                    cap = 1
                if key == "tails" and any(re.search(r"\b(?:twin|both|two)\b", x) for x in [w] + [n.lower() for n in mine]):
                    cap = 2
                return key, cap, mine
        return None

    def check_grips(self, attacker, defender, grips, submission=False):
        """holds.invented_check (since build 261): a hold the director wrote (or a submission it invented) checked
        against what bodies can do, grip by grip (grips = [(her part, what grips it)]). Returns (the grips kept, why
        each one dropped was dropped); raises ValueError when none is left or the submission's main grip can't be.
        - trapped: a limb caught in the other one's grip can't grip back with it.
        - wrecked: a limb at ruined_at damage or worse (devastated) can't take hold.
        - busy: one limb grips one part, a pair (both paws, twin tails) two; a limb already gripping someone else in
          another hold counts.
        - reach: one limb's (or one pair's) parts must be near each other (not her neck and her foot).
        - main grip: a submission works a joint, a limb, the back, the tail or the neck; an ear, a nose or a cheek
          can't be its main grip."""
        cfg = ((self.rules.get("holds") or {}).get("invented_check") or {})
        if not cfg.get("enabled", True):
            return list(grips), []
        a, d = self.get(attacker), self.get(defender)
        trapped = {h.part for h in self.holds.values() if h.attacker == d.name and h.defender == a.name}
        busy = {}
        for h in self.holds.values():
            if h.attacker == a.name and h.defender != d.name:
                lb = self.grip_limb(a, h.with_part)
                if lb:
                    busy[lb[0]] = busy.get(lb[0], 0) + 1
        ruined = float(cfg.get("ruined_at", 300))
        kept, why, used, where = [], [], dict(busy), {}
        if cfg.get("same_target", True):
            # (since build 265) a limb already gripping HER in another hold counts too: both paws bending her arm up
            # in a chicken wing have nothing left for her thigh (the build-264 log added "her paw and knee" to one)
            asked = {str(p) for p, _w in grips}
            for h in self.holds.values():
                if h.attacker == a.name and h.defender == d.name and h.part not in asked:
                    lb = self.grip_limb(a, h.with_part)
                    if lb:
                        # ("both paws" or "twin tails" on one part takes the pair)
                        n_ = lb[1] if re.search(r"\b(?:both|twin|two)\b", str(h.with_part or "").lower()) else 1
                        used[lb[0]] = used.get(lb[0], 0) + n_
                        where.setdefault(lb[0], []).append(h.part)
        for i, (p, w) in enumerate(grips):
            lb = self.grip_limb(a, w)
            if submission and i == 0 and cfg.get("main_grip", True) and self.SMALL_MAIN.search(str(p)):
                raise ValueError(f"a submission can't be worked through {poss_word(d.name)} {str(p).lower()}: its main "
                                 f"grip goes on a joint, a limb, her back, her tail or her neck")
            if not lb:
                kept.append((p, w))
                continue
            key, cap, mine = lb
            if cfg.get("trapped", True) and mine and all(m in trapped for m in mine):
                why.append(f"{poss_word(a.name)} {key} {'is' if key in ('jaws', 'horn') else 'are'} caught in "
                           f"{poss_word(d.name)} grip: she can't grip her {str(p).lower()} with them")
                continue
            if cfg.get("wrecked", True) and mine and all(a.parts[m].damage >= ruined for m in mine):
                why.append(f"{poss_word(a.name)} {key} {'is' if key in ('jaws', 'horn') else 'are'} too badly hurt to "
                           f"take hold of anything")
                continue
            if cfg.get("busy", True) and used.get(key, 0) >= cap:
                why.append(f"{poss_word(a.name)} {key} {'is' if cap == 1 else 'are'} already gripping"
                           + (" someone else" if busy.get(key) else f" {', '.join(where.get(key, []))}")
                           + f": nothing left to grip her {str(p).lower()} with")
                continue
            if cfg.get("reach", True) and key != "coils" and where.get(key):
                r_new = body_region(d.part(p).name)
                far = [q for q in where[key] if not any(body_region(d.part(q).name) in g and r_new in g
                                                        for g in self.NEAR_REGIONS)]
                if far:
                    why.append(f"{poss_word(a.name)} {key} can't reach both {poss_word(d.name)} {far[0].lower()} and "
                               f"her {str(p).lower()} at once")
                    continue
            used[key] = used.get(key, 0) + 1
            where.setdefault(key, []).append(str(p))
            kept.append((p, w))
        if not kept:
            raise ValueError(f"that hold can't go on as described: {'; '.join(why) or 'nothing grips her'}. Grip with "
                             f"what {a.name} has free")
        return kept, why

    def shape_hold(self, attacker, defender, contacts, against="", share=True):
        """holds.backstop and holds.grip_share (since build 260): a hold as bodies can really do it. Returns (the
        contacts to use, [the parts whose press was dropped]).
        - backstop: a press with something that only pushes (her chest, her weight, a knee, her head) hurts only with
          something behind the one pressed to push her against: the ground she is down on, scenery she is driven
          into (or named in pinned_against), or the holder's own arms, tails or legs wrapped round her body hauling
          her into it (a bear hug: the chest is the anvil, at anvil_share of the pressure). Otherwise the press is
          dropped: a chest against the back of a standing fighter in the open is contact, not a grip.
        - grip_share: one limb on several parts splits its pressure (each x 1 / n ** same_limb); every grip after
          the first is a lesser one (x second); at most max_grips grips."""
        hcfg = self.rules.get("holds") or {}
        bcfg, scfg = hcfg.get("backstop") or {}, hcfg.get("grip_share") or {}
        d = self.get(defender)
        out, dropped = list(contacts), []

        def with_of(c):
            return str(c[3] if len(c) > 3 else "")
        if bcfg.get("enabled", True) and d is not None:
            push = [c for c in out if self.PUSH_WITH.search(with_of(c)) and not self.GRIP_WITH.search(with_of(c))]
            backed = d.name in self.downed or bool(str(against or "").strip()) or d.name in self.pressed
            if push and not backed:
                wrapped = any(self.GRIP_WITH.search(with_of(c)) and self.WRAP_WORDS.search(with_of(c))
                              and body_region(d.part(c[0]).name) in self.WRAP_REGIONS for c in out if c not in push)
                share = float(bcfg.get("anvil_share", 0.5))
                if wrapped:
                    out = [(c[0], c[1] * share) + tuple(c[2:]) if c in push else c for c in out]
                else:
                    dropped = [c[0] for c in push]
                    out = [c for c in out if c not in push]
                    if not out:
                        raise ValueError(
                            f"{attacker} can't press {d.name} with {', '.join(with_of(c) or 'her body' for c in push)}: "
                            f"{d.name} is on her feet with nothing behind her to be pushed against. Wrap her up (arms, "
                            f"tails or legs round her body), drive her into something first, or take her down")
        if share and scfg.get("enabled", True) and len(out) > 1:
            def limb(c):
                w = with_of(c).lower()
                m = self.GRIP_WITH.search(w) or self.PUSH_WITH.search(w)
                return m.group(0).rstrip("s") if m else w
            counts = {}
            for c in out:
                counts[limb(c)] = counts.get(limb(c), 0) + 1
            exp, second = float(scfg.get("same_limb", 0.5)), float(scfg.get("second", 0.7))
            out = [(c[0], c[1] * (counts[limb(c)] ** -exp if limb(c) else 1.0) * (1.0 if i == 0 else second))
                   + tuple(c[2:]) for i, c in enumerate(out)]
            cap = int(scfg.get("max_grips", 4) or 0)
            if cap and len(out) > cap:
                dropped += [c[0] for c in out[cap:]]
                out = out[:cap]
        return out, dropped

    def start_holds(self, attacker, defender, contacts, flavor="", pin=False, move=None, enforce=False):
        """Several holds at once, e.g. a pin: weight on the chest, teeth in the neck, knees in the sides.
        contacts: list of (part, power, ramp) or (part, power, ramp, with_part). All are validated first.
        enforce: apply the pin rules (target on the ground, enough attacks since the last pin attempt)."""
        a, d = self.get_active(attacker), self.get_active(defender)
        if not contacts:
            raise ValueError("needs at least one body part to press")
        if enforce and not pin:
            self._regrab_check(a, d)
        if a is d:
            raise ValueError(f"{a.name} can't hold or pin herself")
        if enforce:
            # one mouth: jaws already clamped somewhere (or named twice in this pin) can't close on a second part
            jaws = lambda w: bool(re.search(r"\b(jaws?|teeth|fangs?|mouth|bite)\b", str(w or "").lower()))
            busy = any(h.attacker == a.name and jaws(h.with_part) for h in self.holds.values())
            kept, seen = [], busy
            for c in contacts:
                if len(c) > 3 and jaws(c[3]):
                    if seen:
                        continue
                    seen = True
                kept.append(c)
            if not kept:
                raise ValueError(f"{poss_word(a.name)} jaws are already clamped on someone: she can't bite down on a "
                                 f"second part. Use her free limbs, or let go first")
            contacts = kept
        key = f"{a.name}>{d.name}"
        host = self.pin_on(d.name)                                   # a pin already running on her, if any
        mine = host is not None and a.name in self.pin_members(host)  # ...that this fighter is already part of
        joining = bool(pin and host is not None and not mine)        # a second pinner piling on: a double pin
        new_pin = bool(pin and host is None)
        on_top = self.pinned_by(a.name)
        elsewhere = [x for x in self.pinning(a.name) if x != d.name] if (new_pin or joining) else []
        self._no_friendly_fire(a, [d], enforce)
        if enforce:
            if self.has(d, "airborne") or (self.has(a, "airborne") and not (move or {}).get("carry")):
                raise ValueError(f"{(d if self.has(d, 'airborne') else a).name} is in the air: no holds or pins until "
                                 f"she comes down ('reposition': 'land', or a ranged hit that grounds her)")
            if on_top and (pin or d.name not in on_top):
                raise ValueError(f"{a.name} is PINNED under {on_top[0]}: she can't {'pin' if pin else 'grab'} "
                                 f"{d.name} from there. Use 'struggle' for an escape attempt, or a strike at {on_top[0]}")
            if elsewhere:
                raise ValueError(f"{a.name} is already pinning {elsewhere[0]}: keep that pin going ('breather' or "
                                 f"'hold_adjust'), or release it before pinning someone else")
            if joining and len(self.pin_members(host)) >= int(self.rules.get("pin", {}).get("max_pinners", 2)):
                raise ValueError(f"{' and '.join(self.pin_members(host))} are already pinning {d.name}: there's no room "
                                 f"for another")
            if new_pin and a.name in self.downed and d.name not in self.downed:
                raise ValueError(f"{a.name} is on the ground and {d.name} is on her feet: {a.name} can't pin her from "
                                 f"down there. She attacks from where she lies, or gets up first")
            gr = self.rules.get("holds", {}).get("ground_reach") or {}
            if not pin and gr.get("enabled", True) and a.name in self.downed and d.name not in self.downed \
                    and not on_top:
                # lying on the ground, she can't put a new grip on a standing fighter's throat or head
                sit = self.facing.get(a.name) == "sitting up"
                high = set(gr.get("sitting" if sit else "lying") or [])
                have = {h.part for h in self.holds.values() if h.attacker == a.name and h.defender == d.name}
                far = [d.part(c[0]).name for c in contacts
                       if d.part(c[0]).name not in have and body_region(d.part(c[0]).name) in high]
                if far:
                    raise ValueError(f"{a.name} is {'sitting' if sit else 'lying'} on the ground and {d.name} is on "
                                     f"her feet: {a.name} can't reach {poss_word(d.name)} {far[0].lower()} from down "
                                     f"there. Grip something low (a leg, a foot, a hip, her tail), strike, or get up "
                                     f"first")
        woke = []
        if not enforce:
            # your own command has a sleeping or frozen fighter grab someone: then she is awake to do it (a
            # fighter can't be out cold and holding on at the same time)
            for st in ("asleep", "frozen"):
                if self.has(a, st):
                    a.status.pop(st, None)
                    woke.append(st)
        if enforce:
            self._can_act(a, True)
            if not any(h.attacker == a.name and h.defender == d.name for h in self.holds.values()):
                self._spend(a, self.energy_cost(kind="pin" if pin else "hold"), True, "a pin" if pin else "a hold")
        if enforce and (new_pin or joining) and self.has(a, "reeling"):
            raise ValueError(f"{a.name} is still REELING from being driven into the scenery: she can't take anyone down "
                             f"or pin this beat. She can strike, or catch her breath")
        if enforce and new_pin:  # joining a pin that's already running needs no opening
            ok, why = self.pin_allowed(d.name)
            if not ok:
                raise ValueError(f"no pin allowed yet: {why}. Choose an attack instead")
        cfg = self.rules.get("pin", {})
        continuing = bool(pin and mine)
        taken_down = bool(pin and not continuing and d.name not in self.downed)  # on her feet: dragged down into it
        loose = []
        lay = self.facing.get(d.name) if d.name in self.downed else None
        if pin and not continuing:
            if on_top:  # your command: a reversal. The pin on her ends and she comes out on top
                loose += self._lose_grip(a.name, f"{a.name} reversed it", on_her=True, keep_on=d.name)
            if elsewhere:  # your command: she lets the first one go to pin this one
                loose += self._lose_grip(a.name, f"{a.name} let go to pin {d.name}", keep_on=d.name)
            if a.name in self.downed:  # the pinner comes up onto her opponent: she's on top, not lying down
                self.downed.pop(a.name, None)
                self.facing.pop(a.name, None)
                self._fresh_down.discard(a.name)
            if d.name not in self.downed:
                # taken down into the pin: whatever she was pinning or holding (except her grip on the pinner) ends
                loose += self._lose_grip(d.name, f"{d.name} was taken down", keep_on=a.name)
            # (only your own command gets here with a flyer in the air: the director's pin is refused above)
            loose += self._out_of_air((a, d), "the pin")
        if new_pin:
            for h in [h for h in self.holds.values() if h.attacker == a.name and h.defender == d.name and h.sub]:
                self.holds.pop(h.id, None)      # the submission is let go for the pin
        names = [d.part(c[0]).name for c in contacts]
        # grips she already has on this fighter when a NEW pin starts: they become part of the pin
        had = ([{"hold_id": h.id, "part": h.part, "with": h.with_part, "flavor": h.flavor, "beats_held": h.turns_active}
                for h in self.holds.values() if h.attacker == a.name and h.defender == d.name]
               if (new_pin or joining) else [])
        started = []
        for pname, c in zip(names, contacts):
            started.append(self.start_hold(a.name, d.name, pname, c[1], c[2], flavor, c[3] if len(c) > 3 else "",
                                           keep_with=enforce))
            h = self.holds.get(started[-1]["hold_id"])
            # (a grip with words of its own is judged by them: "both paws, turning the foot" in a hold whose look
            # mentions the tails wound round the knee is not a coil)
            if h is not None and (self.is_coil(move, h.with_part, "" if h.with_part else flavor)
                                  or (len(contacts) == 1 and self._wraps_with(h.with_part, flavor))):
                h.coil = True
                started[-1]["coil"] = True
        if joining:
            host.setdefault("helpers", []).append(a.name)
            self.momentum = (self.momentum + [f"{a.name}>{d.name}"])[-20:]
        elif pin and not continuing:
            self.pins[key] = {"attacker": a.name, "defender": d.name, "seconds": 0, "fade": 0.0, "beats": 0,
                              "duration": cfg.get("duration_seconds", 60), "started_turn": self.turn}
            self.since_pin[d.name] = 0  # every pin attempt resets the count
            self._count("pinned", d.name)
            self.pressed.pop(d.name, None)  # dragged down from where the charge left her
            self.downed.setdefault(d.name, 0)  # pinned means on the ground
            self.__dict__.setdefault("lying_at", {}).pop(d.name, None)
            self.__dict__.setdefault("lying_on", {}).pop(d.name, None)   # (taken down here: not on the last fall's ground)
            for h in self.holds.values():      # nobody is "on her feet at point-blank" any more: a grab between these
                if h.grab and {h.attacker, h.defender} == {a.name, d.name}:     # two is now simply a grip
                    h.grab = False
            if self.facing.get(d.name) not in self.FACING_LOOK or self.facing.get(d.name) == "sitting up":
                # the presses are on the side facing UP: chest pressed = she's on her back (a sitting fighter is
                # borne down flat by the pin)
                guess = self._guess_facing(d.name, names)
                self.facing[d.name] = {"face-down": "face-up", "face-up": "face-down"}.get(guess, guess)
                if re.search(r"\bfrom behind\b|face-down", flavor or "", re.I):
                    self.facing[d.name] = "face-down"   # a hold from behind (a sleeper) bears her down onto her front
            self.momentum = (self.momentum + [f"{a.name}>{d.name}"])[-20:]
        # the presses and the way she lies must agree (your own named parts turn her; the director's follow her)
        self._settle_facing(d.name, parts_win=not enforce)
        mine = {h.id: h for h in self.holds.values() if h.attacker == a.name and h.defender == d.name}
        for st in started:  # a press may have moved to the exposed side, or merged with another
            h = mine.get(st["hold_id"])
            if h is not None:
                st["part"] = h.part
        started = [st for st in started if st["hold_id"] in mine]
        self._knock_on = []
        takedown = None
        if taken_down:
            # HOW she is taken down varies, and often the landing itself hurts (pin.takedown)
            tcfg = cfg.get("takedown", {}) or {}
            # (the manner is colour: it is picked without touching the fight's own dice)
            import zlib
            table = dict(self.VARIETY["takedown"])
            over = self.rules.get("variety", {}).get("takedown")
            if isinstance(over, dict):
                table = {k: float(v) for k, v in over.items() if not str(k).startswith("_") and float(v) > 0} or table
            pick = random.Random(zlib.crc32((f"{getattr(self, '_seed0', 0)}|{self.turn}|{a.name}|{d.name}|{self.times('pinned', d.name)}|"
                                                 f"{a.energy:.3f}|{a.health:.3f}|{d.health:.3f}").encode()))
            lies = self.facing_of(d.name)
            fits = self._takedown_fits(lies) or set(table)
            table = {k: v for k, v in table.items() if k in fits} or table
            told = bool(re.search(r"\b(?:drag\w*|haul\w*|pull\w*|sweep\w*|swept|trip\w*|tackl\w*|throw\w*|threw|hook\w*|"
                                  r"bowl\w*|bear\w* (?:her )?down|bore|rid\w+ (?:her )?down|tak\w+ (?:her )?down|"
                                  r"took (?:her )?down|down by|off her feet|legs? out|topple\w*|flip\w*|roll\w* her)\b",
                                  str(flavor or ""), re.I))
            takedown = {"how": None if told else pick.choices(list(table), [table[k] for k in table])[0],
                        "told": told, "hard": False, "hits": []}
            if enforce and float(tcfg.get("hard_landing_chance", 0.4)) > 0 and self._chance(float(tcfg.get("hard_landing_chance", 0.4)),
                                        f"{d.name} landing hard from the takedown", "a HARD landing", "put down clean"):
                table = self.rules["severity"].get("environment") or self.rules["severity"]["instant"]
                power = float(table.get(tcfg.get("landing_severity", "solid"), 12))
                pressed_now = {h.part for h in self.holds.values() if h.defender == d.name}
                under = [x for x in self.underside_parts(d.name, int(tcfg.get("landing_parts", 2)) + 2)
                         if x not in pressed_now][:int(tcfg.get("landing_parts", 2))]
                keep_src, self._source = self._source, f"the ground, when {a.name} took her down"
                takedown["hits"] = [self._apply_damage(d, x, power) for x in under]
                self._source = keep_src
                takedown["hard"] = bool(takedown["hits"])
        fixed = self._grip_flavor_fix(flavor, d, started)
        fixed = self._holder_part_fix(fixed, a, started)
        if fixed != flavor:
            flavor = fixed
            for st in started:
                if st["hold_id"] in self.holds and not st.get("existing"):
                    self.holds[st["hold_id"]].flavor = flavor
        return {"type": "pin_start" if pin else "hold_start", "attacker": a.name, "defender": d.name,
                "takedown": takedown,
                "flavor": flavor, "move": move, "continuing": continuing,
                "seconds": self.pin_on(d.name)["seconds"] if pin else None,
                "duration": self.pin_on(d.name)["duration"] if pin else None,
                "joined": [m for m in self.pin_members(host) if m != a.name] if joining else [],
                "facing": self.facing_of(d.name), "knock_on": loose, "taken_down": taken_down,
                "facing_note": (f"rolled {d.name} over to reach those spots: {lay} → {self.facing_of(d.name)}"
                                if lay and self.facing_of(d.name) != lay else ""),
                "woke": woke,
                "absorbed": [x for x in had if x["hold_id"] in self.holds
                             and x["hold_id"] not in {h["hold_id"] for h in started}],
                "hold_ids": [h["hold_id"] for h in started if not h["existing"]],
                "parts": [{"part": h["part"], "power": h["power"], "change_per_beat": h["change_per_beat"],
                           "with": h.get("with", ""), "existing": bool(h.get("existing")),
                           "asked_with": h.get("asked_with", ""), "choke_kind": h.get("choke_kind", "")}
                          for h in started]}

    def regrab_wait(self, a, d):
        """Beats left before `a` may grip `d` again after `d` tore free of her (holds.break.regrab_after); 0 = free."""
        wait = int((self.rules.get("holds", {}).get("break", {}) or {}).get("regrab_after", 2))
        broke = (getattr(self, "broke_free_at", {}) or {}).get(f"{a.name}>{d.name}")
        return 0 if broke is None else max(0, wait - (self.turn - broke))

    def _regrab_check(self, a, d):
        if self.regrab_wait(a, d) > 0:
            raise ValueError(f"{d.name} only just tore free of {poss_word(a.name)} grip: {a.name} can't simply take "
                             f"hold of her again so soon. Strike, move, or set something up instead")

    def release_between(self, attacker, defender, reason="released"):
        """End every hold one fighter has on another (e.g. breaking a whole pin)."""
        ids = [h.id for h in self.holds.values()
               if h.attacker.lower() == str(attacker).lower() and h.defender.lower() == str(defender).lower()]
        if not ids:
            raise ValueError(f"{attacker} has no holds on {defender}")
        ended = [self.release(i, reason) for i in ids]
        return {"type": "hold_end", "attacker": ended[0]["attacker"], "defender": ended[0]["defender"],
                "hold_ids": ids, "parts": [x["part"] for x in ended],
                "pin_ended": next((x["pin_ended"] for x in ended if x.get("pin_ended")), None),
                "beats_held": max(x["beats_held"] for x in ended), "reason": reason}

    def set_intensity(self, hold_id, power=None, change_per_turn=None):
        h = self._hold(hold_id)
        old = h.power
        if power is not None:
            h.power = max(0, power)
        if change_per_turn is not None:
            h.change_per_turn = change_per_turn
        direction = "tightens" if h.power > old else "loosens" if h.power < old else "holds steady"
        return {"type": "hold_change", "hold_id": h.id, "attacker": h.attacker, "defender": h.defender,
                "part": h.part, "power_before": old, "power_after": h.power,
                "change_per_beat": h.change_per_turn, "direction": direction, "flavor": h.flavor}

    def release(self, hold_id, reason="released"):
        h = self.holds.pop(self._hold(hold_id).id)
        p = self.pin_on(h.defender)
        ended = None
        if (p is not None and h.attacker in self.pin_members(p)
                and not any(x.attacker == h.attacker and x.defender == h.defender for x in self.holds.values())):
            # that was her last press: she is off the pin (and if nobody else is pressing, the pin is over)
            broke = "break" in str(reason).lower() or "escape" in str(reason).lower()
            left = self._leave_pin(f"{p['attacker']}>{p['defender']}", h.attacker, str(reason),
                                   how="broke free" if broke else "was let go")
            if any(e["type"] == "pin_broken" for e in left):
                self.last_pin_end.pop("note", None)
                ended = {"attacker": h.attacker, "defender": h.defender, "seconds": p["seconds"]}
        return {"type": "hold_end", "hold_id": h.id, "attacker": h.attacker, "defender": h.defender,
                "part": h.part, "beats_held": h.turns_active, "reason": reason, "flavor": h.flavor,
                "pin_ended": ended}

    def _grip_limb_damage(self, holder, holds):
        """How hurt the limb is that she grips with (jaws -> Jaw, twin tails -> Twin Tails, forepaw -> the better
        of her forepaws): 0 when the grip names no part of hers (her weight, her coils)."""
        skip = {"left", "right", "upper", "lower", "her", "his", "the", "both", "a", "with", "full", "twin"}
        worst = 0.0
        for h in holds:
            words = {w.rstrip("s") for w in re.findall(r"[a-z]+", (h.with_part or "").lower())} - skip
            hits = [p.damage for p in holder.parts.values() if "base" not in p.name.lower()
                    and words & ({w.rstrip("s") for w in re.findall(r"[a-z]+", p.name.lower())} - skip)]
            if hits:
                worst = max(worst, min(hits))
        return worst

    def hold_break_chance(self, holder, held):
        """The chance, each beat, that `held` wrenches free of the plain holds `holder` has on her (not a pin: a
        pin has its clock and its struggle). Fresh against fresh it is holds.break.base. It rises when she is in
        better shape than the one holding her, when the grip is light, when the limb that grips is hurt, and a
        little with every beat the grip has been on (per_beat); it falls when she is worn down, when the grip is
        crushing, and steeply once her health is below zero. So a hold can end next beat or run for a dozen."""
        cfg = self.rules.get("holds", {}).get("break", {})
        base = float(cfg.get("base", 0.12))
        a, d = self.get(holder), self.get(held)
        hs = [h for h in self.holds.values() if h.attacker == a.name and h.defender == d.name]
        if base <= 0 or not hs or self.has(d, "asleep") or self.has(d, "frozen"):
            return 0.0
        sa = max(0.0, min(1.0, a.health / a.max_health))
        sd = max(0.0, min(1.0, d.health / d.max_health))
        rel = max(0.3, min(2.5, (0.25 + sd) / (0.25 + sa)))
        grip = max(0.4, min(1.5, float(cfg.get("reference_power", 15)) / max(1.0, max(h.power for h in hs))))
        limb = 1.0 + min(1.0, self._grip_limb_damage(a, hs) / 150.0)
        ch = base * rel * grip * limb + float(cfg.get("per_beat", 0.015)) * max(0, max(h.turns_active for h in hs) - 1)
        if d.health <= 0:
            ch *= float(cfg.get("below_zero_mult", 0.25))
        ch *= self._break_mods(a, d, hs)
        return round(max(0.0, min(float(cfg.get("max", 0.6)), ch)), 3)

    def _break_mods(self, a, d, hs):
        """What her state and the grip's kind do to any break-free chance: paralyzed, adrenaline, a grab or a coil,
        wet fur on either side."""
        cfg = self.rules.get("holds", {}).get("break", {})
        m = 1.0
        if self.has(d, "paralyzed"):
            m *= 0.5
        if self.has(d, "adrenaline"):
            m *= 1.5
        if all(h.grab for h in hs):
            m *= float(cfg.get("grab_mult", 1.6))   # a grab holds her close; it doesn't lock her
        if any(h.coil for h in hs):
            m *= float((self.rules.get("holds", {}).get("coil") or {}).get("break_mult", 0.75))   # coils give nothing to push against
        if any(h.coil and body_region(h.part) in self.MIDDLE_REGIONS for h in hs) and self.coil_dwarfs(a.name, d.name):
            # (holds.coil.size) wound in the coils of something many times her size: nothing to lever them off with
            m *= float((self.coil_size_cfg() or {}).get("escape_mult", 0.6))
        sc = self._cfg("status_effects")
        if self.has(d, "soaked"):
            m *= float(sc.get("soaked_slip_mult", 1.2))     # wet fur slides out of a grip
        if self.has(a, "soaked"):
            m *= float(sc.get("soaked_grip_mult", 1.1))     # and a wet paw holds worse
        return m

    def shake_grips(self, name, health_lost, why="the hit"):
        """A hard enough hit can shake loose what she is holding on with. `name` has just lost `health_lost`
        health to one attack; if she has plain holds on anyone (a pin is not shaken this way: it ends when its
        pinner is knocked down or thrown), one roll decides whether she keeps them. The chance is the share of
        her full health that the attack cost, times holds.shaken.per_health_share: 10% of her health = 25%, 20%
        = 50%, 38% or more = almost certain. Hits under min_share don't roll. Returns the holds that ended."""
        cfg = self.rules.get("holds", {}).get("shaken", {})
        k = float(cfg.get("per_health_share", 2.5))
        f = self.fighters.get(str(name).lower())
        if k <= 0 or f is None or f.eliminated or not health_lost or f.max_health <= 0:
            return []
        pinning = set(self.pinning(f.name))
        mine = [h for h in self.holds.values() if h.attacker == f.name and h.defender not in pinning]
        share = float(health_lost) / f.max_health
        if not mine or share < float(cfg.get("min_share", 0.03)):
            return []
        ch = round(min(float(cfg.get("max", 0.95)), k * share), 3)
        if not self._chance(ch, f"{f.name} losing her grip to {why} ({share * 100:.0f}% of her health at once)",
                            "she loses it", "she holds on"):
            return []
        out = []
        for h in mine:
            self.holds.pop(h.id, None)
            out.append({"type": "hold_end", "shaken": True, "hold_id": h.id, "attacker": h.attacker,
                        "defender": h.defender, "part": h.part, "with": h.with_part, "beats_held": h.turns_active,
                        "chance": ch, "flavor": h.flavor,
                        "reason": f"{why} shook it loose", "share": round(share, 3)})
        return out

    def coil_contest_cfg(self):
        cfg = ((self.rules.get("holds") or {}).get("coil") or {}).get("contest") or {}
        return cfg if cfg.get("enabled", True) else None

    def coil_strength(self, f):
        """How hard she can work her coils in a contest of coils (holds.coil.contest): her strength, her size
        (size_weight: a bigger serpent's coils carry more), how much energy she has left, a surge of adrenaline."""
        cfg = self.coil_contest_cfg() or {}
        size = max(0.1, float(self.size_m(f) or 1.0))
        s = (0.25 + max(0.0, min(100.0, self.strength(f))) / 100.0) * size ** float(cfg.get("size_weight", 0.5))
        s *= 0.5 + max(0.0, min(100.0, float(f.energy))) / 200.0
        if self.has(f, "adrenaline"):
            s *= float(cfg.get("adrenaline_mult", 1.25))
        q = self.quirk(f, "patient_constrictor")
        if q:
            s *= float(q.get("contest_mult", 1.2))
        return s

    def _coil_contest_tick(self, skip_hold_ids=()):
        """holds.coil.contest (since build 279): two fighters coiled round each other at once fight it out. Each beat
        (once both coils have been on for a beat) they strain against each other: stall_chance of the time both
        coils hold and it costs them both; otherwise one out-coils the other, with the chance of coil_strength
        against coil_strength (strength, size, energy). The loser's coils are shed and the winner's tighten
        (tighten power) and take over: her grip gets no break-free roll from the loser this beat."""
        cfg = self.coil_contest_cfg()
        if not cfg:
            return []
        events, seen = [], set()
        coils = [h for h in self.holds.values() if h.coil]
        for h in coils:
            a, d = h.attacker, h.defender
            if (d, a) in seen or (a, d) in seen:
                continue
            mine = [x for x in coils if x.attacker == a and x.defender == d]
            theirs = [x for x in coils if x.attacker == d and x.defender == a]
            if not theirs:
                continue
            seen.add((a, d))
            if all(x.id in skip_hold_ids for x in mine) or all(x.id in skip_hold_ids for x in theirs):
                continue      # one of the coils only closed this beat: the contest starts next beat
            fa, fd = self.fighters.get(a.lower()), self.fighters.get(d.lower())
            if not fa or not fd or fa.eliminated or fd.eliminated:
                continue
            cost = float(cfg.get("energy_cost", 4))
            for f in (fa, fd):
                f.energy = max(0.0, f.energy - cost)
            sa, sd = self.coil_strength(fa), self.coil_strength(fd)
            p_a = sa / (sa + sd) if sa + sd > 0 else 0.5
            stall = float(cfg.get("stall_chance", 0.35))
            ev = {"type": "coil_contest", "fighters": [a, d], "chance": {a: round(p_a, 3), d: round(1 - p_a, 3)},
                  "parts": {a: [x.part for x in theirs], d: [x.part for x in mine]},
                  "with": {a: [x.with_part for x in mine if x.with_part], d: [x.with_part for x in theirs if x.with_part]}}
            if self._chance(stall, f"{a} and {d} both holding on in the contest of coils", "both hold",
                            "one gives"):
                ev["result"] = "stall"
                events.append(ev)
                continue
            r = self.rng.random()
            self.note_roll(f"{a} out-coiling {d} ({sa:.2f} against {sd:.2f})", p_a, r,
                           f"{a} wins it" if r < p_a else f"{d} wins it")
            win, lose = (fa, fd) if r < p_a else (fd, fa)
            won = mine if win is fa else theirs
            lost = theirs if win is fa else mine
            ended = []
            for x in lost:
                if x.id in self.holds:
                    why = f"out-coiled: {win.name}'s coils forced hers off"
                    ended.append(dict(self.release(x.id, why), type="hold_end", hold_ids=[x.id], parts=[x.part],
                                      contest=True))
            bump = float(cfg.get("tighten", 3))
            for x in won:
                x.power = round(x.power + bump, 2)
            if self.quirk(win, "patient_constrictor"):
                self.quirk_moment(win, "patient_constrictor", f"{win.name} never hurried: she waited for the other to "
                                                              f"spend herself, and then she took the knot")
            ev.update(result="won", winner=win.name, loser=lose.name, winner_holds=[x.id for x in won],
                      shed=[x.part for x in lost], shed_ids=[x.id for x in lost], tighten=bump)
            events.append(ev)
            events += ended
        return events

    def _hold_break_tick(self, skip_hold_ids=()):
        """Once a beat, after the pressure has landed, each fighter in a plain hold gets one roll to break it.
        Holds that only started this beat don't roll yet; a fighter who is pinned breaks nothing but the pin."""
        events = []
        pinned_pairs = {(m, p["defender"]) for p in self.pins.values() for m in self.pin_members(p)}
        pinned = {p["defender"] for p in self.pins.values()}
        pairs = {}
        for h in self.holds.values():
            if (h.attacker, h.defender) in pinned_pairs or h.defender in pinned:
                continue
            pairs.setdefault((h.attacker, h.defender), []).append(h)
        for (a, d), hs in pairs.items():
            if all(h.id in skip_hold_ids for h in hs):
                continue
            fa, fd = self.fighters.get(a.lower()), self.fighters.get(d.lower())
            if not fa or not fd or fa.eliminated or fd.eliminated:
                continue
            ch = self.hold_break_chance(a, d)
            esc = (self.rules.get("submissions") or {}).get("escape") or {}
            if any(h.sub for h in hs) or (self.submission_match() and esc.get("enabled", False)
                                          and esc.get("match_holds", True) and not all(h.grab for h in hs)):
                # (in a submission match any hold that hurts can make her tap: she breaks it the same way)
                ch, _ = self.sub_break_chance(ch, fd, hs)
            ch *= self.dominated(fd.name) * self.trait(fd, "escape") / self.trait(fa, "hold")
            q = self.quirk(fa, "weak_paw_grip")
            if q and any(re.search(r"\bpaws?\b|forepaws?|claws?", str(h.with_part or ""), re.I) for h in hs):
                ch *= float(q.get("break_mult", 1.35))   # (her paws aren't made for gripping)
            ch = min(0.95, ch)
            pas = getattr(self, "_passive", None)
            if pas and pas[0] == self.turn and fd.name in pas[1]:
                continue   # (since build 278) her player has her do nothing: she doesn't try to break it
            if self.has(fd, "stunned"):
                continue   # (since build 293) stunned: nothing in her answers yet
            cc_ = self.compress_cfg()
            if cc_ and any(h.coil and self.coil_scope(h.part) == "body" for h in hs):
                # (since build 294) squeezed in, she has no room left to work with
                ch *= max(0.0, 1.0 - float(cc_.get("escape_mult", 0.5)) * self.compression_on(fd, fa.name) / 100.0)
            if fd.name in self.lucky and fa.name not in self.lucky:
                ch = 1.0   # /play dice free: she breaks any hold on her at once (not one a dice-free holder has)
            if ch <= 0:
                continue
            cfg = self.rules.get("holds", {}).get("break", {})
            tr_ = self.trait(fd, "escape") / self.trait(fa, "hold")
            ok, r = self._chance_r(ch, f"{d} breaking {poss_word(a)} hold on her"
                                   + (f" (her escape against the grip ×{tr_:.2g})" if abs(tr_ - 1) > 0.01 else ""),
                                   "she breaks free", "it holds")
            if ok:
                for h in hs:
                    self.holds.pop(h.id, None)
                # she just tore loose: the same grip can't simply close on her again next beat
                self.__dict__.setdefault("broke_free_at", {})[f"{a}>{d}"] = self.turn   # ("A>B": a save can hold it)
                events.append({"type": "hold_end", "broke_free": True, "attacker": a, "defender": d,
                               "submission": next((h.sub for h in hs if h.sub), ""),
                               "hold_ids": [h.id for h in hs], "parts": [h.part for h in hs],
                               "with": [h.with_part for h in hs if h.with_part],
                               "beats_held": max(h.turns_active for h in hs), "chance": ch,
                               "manner": self.vary("hold_break", skip=(
                                   ("shove",) if cfg.get("shove_needs_standing", True)
                                   and (a in self.downed or d in self.downed) else ())),
                               "reason": f"{d} wrenched free"})
            elif r < ch * (1.0 + float(cfg.get("loosen_band", 0.6))):
                # a near miss: she doesn't get out, but she works it looser. It presses less from the next beat on.
                mult = float(cfg.get("loosen_mult", 0.75))
                was = [h.power for h in hs]
                for h in hs:
                    h.power = round(max(min(1.0, h.power), h.power * mult), 2)
                events.append({"type": "hold_loosened", "attacker": a, "defender": d, "hold_ids": [h.id for h in hs],
                               "parts": [h.part for h in hs], "with": [h.with_part for h in hs if h.with_part],
                               "power_from": was, "power_to": [h.power for h in hs], "chance": ch, "roll": round(r, 3),
                               "manner": self.vary("hold_strain")})
            elif r < ch * (1.0 + float(cfg.get("loosen_band", 0.6)) + float(cfg.get("strain_band", 1.4))):
                # close enough to show: she fights the grip and it holds exactly as it was
                events.append({"type": "hold_strain", "attacker": a, "defender": d, "parts": [h.part for h in hs],
                               "with": [h.with_part for h in hs if h.with_part], "manner": self.vary("hold_strain")})
        return events

    def _hold(self, hold_id):
        if hold_id not in self.holds:
            raise ValueError(f"No active hold #{hold_id}. Active: {list(self.holds) or 'none'}")
        return self.holds[hold_id]

    def beat(self, skip_hold_ids=()):
        self._ticking = True       # (the clock has moved on to this beat: long_match_ramp counts it as now)
        try:
            return self._beat(skip_hold_ids)
        finally:
            self._ticking = False

    def _beat(self, skip_hold_ids=()):
        """One story beat passes: active holds deal damage, then time effects
        (resistance wear, exhaustion, pain drain). Holds started this beat don't tick yet."""
        r = self.rules
        self.turn += 1
        events, self._pending_events = list(self._pending_events), []
        had_grip = bool(self.pins or self.holds)   # a beat with a pin or a hold in it stays about that

        pinned_pairs = {(m, p["defender"]) for p in self.pins.values() for m in self.pin_members(p)}
        time_factor = self.pin_time_factor()
        # a grip that closes this beat already hurts: the clamp itself is its first beat of pressure
        # (holds.first_beat_damage; a pin's presses have their own setting, pin.first_beat_damage)
        first_hold = max(0.0, float(self.rules.get("holds", {}).get("first_beat_damage", 1.0)))
        first_pin = max(0.0, float(self.rules.get("pin", {}).get("first_beat_damage", 1.0)))
        for h in list(self.holds.values()):
            in_pin = (h.attacker, h.defender) in pinned_pairs
            fresh = h.id in skip_hold_ids
            first = (first_pin if in_pin else first_hold) if fresh else 1.0
            if fresh and first <= 0:
                continue
            d = self.get(h.defender)
            # during a pin, pressure is per reference_seconds and scales with the length of the beat
            ramp = 1.0
            if in_pin:
                rcfg = self.rules.get("pin", {}).get("ramp") or {}
                if rcfg.get("enabled", True):
                    # held pressure builds: each beat the press stays on, it bites a little deeper (pin.ramp)
                    ramp = min(float(rcfg.get("max", 1.6)), 1.0 + float(rcfg.get("per_beat", 0.12)) * h.turns_active)
            # a submission that has become a pin (h.locked) keeps its own wrench (no lighter pin pressure), but it is
            # a pin now: its bite into a worn part is capped like any pin's. A submission still on is capped too, more
            # loosely (submissions.damage_cap): a wrench hurts more than being held down, but it doesn't run away
            as_pin = in_pin and not h.locked
            bcfg = self.rules.get("holds", {}).get("build") or {}
            health_scale = 1.0
            if not in_pin and not fresh and h.change_per_turn >= 0 and bcfg.get("enabled", True):
                # a hold kept on without breaking bites deeper each beat (holds.build), whatever its own ramp: into the
                # part at per_beat, into her overall health more slowly (health_per_beat; the pain at pain_per_beat)
                ramp = min(float(bcfg.get("max", 1.25)), 1.0 + float(bcfg.get("per_beat", 0.04)) * h.turns_active)
                h_ramp = min(float(bcfg.get("health_max", 1.1)),
                             1.0 + float(bcfg.get("health_per_beat", 0.02)) * h.turns_active)
                health_scale = h_ramp / ramp
            power = (h.power * time_factor * float(self.rules.get("pin", {}).get("damage_mult", 1.0)) * ramp
                     if as_pin else h.power * ramp) * first
            # (a coil made of tails is her tails: a Buizel's Tail Bind is not "Nerine's coils")
            coil_word = "tails" if re.search(r"\btails?\b", str(h.with_part or ""), re.I) else "coils"
            self._source = (f"{poss_word(h.attacker)} {h.locked or ('pin' if in_pin else h.sub or (coil_word if h.coil else 'hold'))}")
            cap = self.pin_cap() if in_pin else self.sub_cap() if h.sub else None
            if cap:
                cap = dict(cap, kind="pin" if in_pin else "submission")    # (what the stat line calls the cap)
            hc = self.rules.get("holds", {}).get("health_cap") or {}
            if not in_pin and hc.get("enabled", True):
                # a hold kept on a worn part wrecks the part, but costs her overall health only so much more for the
                # wear (holds.health_cap.health_mult): the limb goes long before she is emptied
                hm = float(hc.get("health_mult", 1.1))
                cap = dict(cap or {"health_only": True})
                if cap.get("health_mult") is None or float(cap["health_mult"]) > hm:
                    cap["health_mult"] = hm
            gcfg = (self.rules.get("submissions") or {}).get("grind") or {}
            grind = gcfg if (h.sub or h.locked) and gcfg.get("enabled", True) else None
            scfg = self.rules.get("holds", {}).get("slow_bite") or {}
            slow = scfg if scfg.get("enabled", True) and not in_pin else None
            # (since build 297, constriction.compression.ring_wear) a coil round her body presses on the whole band it
            # goes round, so its wear goes round with it: ring_wear of the pressure shared over the rest of that band
            # (her flanks, her back...), the rest on the part it was put on
            cc_r = self.compress_cfg() or {}
            share = float(cc_r.get("ring_wear", 0.5)) if h.coil and cc_r.get("ring", True) and not in_pin \
                and self.coil_scope(h.part) == "body" else 0.0
            others = [p for p in self.coil_ring(d, h.part)[1] if p != h.part and p in d.parts] if share > 0 else []
            if not others:
                share = 0.0
            wf = ((self.rules.get("holds") or {}).get("coil") or {}).get("wear_first") or {}
            wf = wf if h.coil and not in_pin and wf.get("enabled", True) else None
            if wf:
                slow = grind = None     # (the coil's own curve, in place of slow_bite or a submission's grind)
            hit = self._apply_damage(d, h.part, round(power * (1.0 - share), 2), cap=cap, grind=grind,
                                     health_scale=health_scale, slow=slow, wear_first=wf)
            ring_hits = [self._apply_damage(d, p, round(power * share / len(others), 2), cap=cap, grind=grind,
                                            health_scale=health_scale, slow=slow, wear_first=wf) for p in others]
            h.turns_active += 1
            if h.coil and not d.eliminated:
                # coils tighten every beat (holds.coil: tighten, max_power). Round her body or throat they squeeze her
                # breath and blood (CONSTRICTED); round one limb they bind it (BOUND: that limb numb and weak)
                ccfg = self.rules.get("holds", {}).get("coil") or {}
                h.power = round(min(float(ccfg.get("max_power", 30)), h.power + float(ccfg.get("tighten", 2))), 2)
                if self.coil_scope(h.part) == "limb":
                    self.set_status(d, "bound", 2)
                    d.learned["bound_part"] = h.part
                else:
                    self.set_status(d, "constricted", 2)
            events.append({"type": "hold_ongoing", "hold_id": h.id, "attacker": h.attacker, "hold_power": h.power,
                           "pin_mult": (round(time_factor * float(self.rules.get("pin", {}).get("damage_mult", 1.0)) * ramp, 4)
                                        if as_pin else None),
                           "first": fresh, "first_mult": first if fresh else None,
                           "defender": h.defender, "flavor": h.flavor, "with": h.with_part, "grab": bool(h.grab),
                           "coil": bool(h.coil), "sub": h.sub or h.locked,
                           "choke_kind": self._hold_choke_kind(h),
                           "beats_held": h.turns_active, "hits": [hit] + ring_hits,
                           "tags": self._tags([hit] + ring_hits)})
            if not fresh:
                # a tightening grip climbs to holds.max_power and no further (coils have their own cap above); an easing
                # grip that has nothing left in it lets go (inside a pin a contact stays on, at its lightest)
                hp = h.power + h.change_per_turn
                if not h.coil and not h.sub and not h.locked and h.change_per_turn > 0:   # submissions keep building
                    hp = min(hp, max(h.power, float(self.rules.get("holds", {}).get("max_power", 35))))
                h.power = round(max(0, hp), 2)
                if h.power <= 0 and h.change_per_turn < 0:
                    if in_pin:
                        h.power, h.change_per_turn = 1.0, 0.0
                    elif h.id in self.holds:
                        ended = self.release(h.id, "eased off until nothing was left of the grip")
                        events.append(dict(ended, type="hold_end", hold_ids=[h.id], parts=[h.part],
                                           reason="eased off until nothing was left of the grip"))

        events += self._advance_pins(skip_hold_ids)
        contest = self._coil_contest_tick(skip_hold_ids)
        events += contest
        events += self._hold_break_tick(set(skip_hold_ids) | {i for e in contest for i in e.get("winner_holds", [])})
        events += self._tap_out_tick()
        events += self._upright_sub_tick()
        events += self._submission_tick()
        events += self._free_blow_tick(skip_hold_ids)
        events += self._wing_strain_tick()
        if not self.winner():
            # once the fight is decided nothing drives her any more: she can sit or lie down in the story, but her
            # body doesn't give out on its own behind it (a collapse the aftermath never told)
            events += self._crumple_tick()
            events += self._collapse_tick()
            events += self._ruined_tick()
            events += self._below_zero_tick()
        else:
            self.pressed.clear()
        events += self.get_up_tick()
        if not self.winner():
            events += self._low_health_tick(events)
        events += self._scene_event_tick(busy=had_grip)

        fighters = {}
        aw_cfg = (r["health"].get("after_win_drain") or {})
        won_since = None
        if self.winner() and aw_cfg.get("enabled", True):
            won_since = self.__dict__.setdefault("won_turn", self.turn)
        for f in self.active():
            before = f.health
            tier_b = tier_for(self._health_pct(f), r["health_tiers"])["label"]
            drain = 0.0
            for p in f.parts.values():
                p.resistance = max(r["resistance"]["minimum"], p.resistance - r["resistance"]["loss_per_beat"])
                for d in r["health"]["pain_drain"]:
                    if p.damage >= d["min_damage"]:
                        drain += d["per_beat"] * self.part_weight(p.name)   # a ruined ear drains less than a ruined chest
            if won_since is not None:
                # the fight is over: the hurts still ache, but less and less drags at her as she settles
                # (health.after_win_drain: the drain is multiplied by `each` for every beat since the win)
                drain *= float(aw_cfg.get("each", 0.5)) ** (self.turn - won_since + 1)
            in_hold = any(f.name in (h.attacker, h.defender) for h in self.holds.values())
            tiring = f.name in self.involved or in_hold
            exhaustion = r["health"]["exhaustion_per_beat"] if tiring else 0.0
            f.health = self._floor(f.health - drain - exhaustion)
            ht = tier_for(self._health_pct(f), r["health_tiers"])
            fighters[f.name] = {"health_before": round(before, 2), "health_after": round(f.health, 2),
                                "max_health": f.max_health,
                                "exhaustion": exhaustion, "pain_drain": drain,
                                "health_tier": ht["label"], "health_tier_changed": ht["label"] != tier_b and won_since is None,
                                "reaction_guide": self.tier_reaction(f, ht)}
        events += self.recover_tick()
        events += self._tick_status_energy()
        events += self._weather_tick()
        events += self._alliance_tick()
        self.pin_window = {}  # openings are rolled fresh for every beat
        self.sub_window = {}
        events.append({"type": "time_passes", "beat": self.turn, "fighters": fighters})
        self.involved = set()
        self.beat_loss = {}   # health.soft_cap counts each beat on its own
        self._pain_tick()
        return events

    def _pain_tick(self):
        """window.pain_gauge: the pain she FEELS overall, carried from beat to beat: each beat what she felt fades
        (decay of it is left), and this beat's blows and grips add their sting. Shown, never used to decide."""
        cfg = ((self.rules.get("window") or {}).get("pain_gauge") or {})
        if not cfg.get("enabled", True):
            return
        for f in self.fighters.values():
            st = f.learned.get("sting") or [None, 0.0]
            now = float(st[1]) if st[0] == self.turn else 0.0
            felt = float(f.learned.get("pain_felt", 0.0)) * float(cfg.get("decay", 0.5)) \
                + float(cfg.get("sting", 1.0)) * now
            if felt < 0.5:
                f.learned.pop("pain_felt", None)
            else:
                f.learned["pain_felt"] = round(felt, 2)

    advance_turn = beat

    def _weather_tick(self):
        """End of a beat: hail stings everyone who isn't Ice-type (weather.hail.chip, on an exposed part); the weather
        counts down and clears."""
        w = getattr(self, "weather", {}) or {}
        if not w:
            return []
        events = []
        cfg = (self.rules.get("weather") or {}).get(w["kind"], {})
        chip = float(cfg.get("chip", 0) or 0)
        if chip:
            for f in self.fighters.values():
                if f.eliminated or any(t in (cfg.get("immune_types") or []) for t in f.types):
                    continue
                up = [p for p in f.parts if body_region(p) in ("head", "back_up", "back_low", "shoulder", "fore_up", "tail")]
                self._source = f"the {cfg.get('word', w['kind'])}"
                hit = self._apply_damage(f, self.rng.choice(up or list(f.parts)), chip)
                events.append({"type": "status_tick", "fighter": f.name, "status": w["kind"], "hits": [hit]})
        w["beats"] -= 1
        if w["beats"] <= 0:
            events.append({"type": "weather_end", "kind": w["kind"]})
            self.weather = {}
        return events

    def _tick_status_energy(self):
        """End of a beat: statuses count down, everyone gets some breath back, and a fighter whose strength just
        fell below the adrenaline threshold gets her one-time surge."""
        events = []
        en = self._cfg("energy")
        ad = self._cfg("adrenaline")
        events += self.numb_tick()
        for f in self.fighters.values():
            # bound and constricted come from coils: once no coil of that kind is on her, they end with this beat
            scopes = {self.coil_scope(h.part) for h in self.holds.values() if h.coil and h.defender == f.name}
            for st, keep in (("bound", {"limb"}), ("constricted", {"throat", "body"})):
                if st in f.status and not scopes & keep:
                    f.status[st] = 1
                    self._fresh_status.discard((f.name, st))
            for st in list(f.status):
                if (f.name, st) in self._fresh_status:
                    continue
                f.status[st] -= 1
                if f.status[st] <= 0:
                    del f.status[st]
                    if not f.eliminated:
                        events.append({"type": "status_end", "fighter": f.name, "status": st})
            if f.eliminated:
                continue
            cfg_s = self._cfg("status_effects")
            if self.has(f, "burned"):
                spots = self.__dict__.setdefault("burn_spot", {})
                if spots.get(f.name) not in f.parts:     # (no spot known: one is chosen once, and the burn stays there)
                    hurt = [p for p in f.parts.values() if p.damage > 0] or list(f.parts.values())
                    spots[f.name] = self.rng.choice(hurt).name
                self._source = "the burn"
                hit = self._apply_damage(f, spots[f.name], float(cfg_s.get("burn_power", 5)))
                events.append({"type": "status_tick", "fighter": f.name, "status": "burned", "hits": [hit]})
            if self.has(f, "poisoned"):
                loss = f.max_health * float(cfg_s.get("poison_health_pct", 1.0)) / 100
                f.health = self._floor(f.health - loss)
                events.append({"type": "status_tick", "fighter": f.name, "status": "poisoned",
                               "health_loss": round(loss, 2), "health_after": round(f.health, 2)})
            regen = float(en.get("regen_per_beat", 5)) + (0 if f.name in self.involved else float(en.get("rest_bonus", 10)))
            if self.has(f, "constricted"):      # the coils squeeze her breath: she gets none back, and loses some
                regen = -float(cfg_s.get("constricted_energy_loss", 4))
                if self.compress_cfg():
                    # (since build 294) the further she is squeezed in, the less breath she gets: x0.5 to x1.5
                    regen *= 0.5 + self.compression_on(f) / 100.0
            elif self.has(f, "sputtering"):     # coughing water up: no breath to get back
                regen = 0.0
            elif self.has(f, "breathless"):     # winded: half the breath comes back (resting still helps)
                regen *= float(cfg_s.get("breathless_regen_mult", 0.5))
            f.energy = max(0.0, min(100.0, f.energy + regen))
            if (ad.get("enabled", True) and not f.adrenaline_used and not self.winner()
                    and self.strength(f) < float(ad.get("below_strength", 25))):
                f.adrenaline_used = True
                self.set_status(f, "adrenaline", ad.get("beats", 3))
                f.energy = min(100.0, f.energy + float(ad.get("energy", 30)))
                events.append({"type": "adrenaline", "fighter": f.name, "beats": int(ad.get("beats", 3))})
        self._fresh_status = set()
        return events

    IN_WATER = re.compile(r"\b(?:(?:in|into|through|under|beneath|half in|waist-deep in|ankle-deep in|"
                          r"knee-deep in|chest-deep in)\s+(?:the\s+|a\s+)?(?:[a-z-]+\s+){0,2}(?:pool|water|channel|"
                          r"shallows|stream|creek|rapids|sump|surf|spring|flooded \w+)|submerged|wading|swimming|"
                          r"half-submerged)\b", re.I)

    # ("ankle-deep" and "knee-deep" are shallow, and so is "the shallow channel")
    DEEP = re.compile(r"(?<!shallow )\b(?:channel|plunge pool|lake|rapids|creek|swimming|submerged)\b|(?<![\w-])deep\b|"
                      r"\b(?:chest|waist)-deep\b", re.I)
    SLICK = re.compile(r"\b(?:algae|slick|slippery|wet stone|ice|icy|frozen|mud|muddy|moss|mossy|spray|oil)\b", re.I)

    def _where(self, name):
        """What the director last said about where this fighter is ("Ripples: in the shallow pool")."""
        m = re.search(re.escape(name) + r"\s*:\s*([^;]*)", self.positions or "", re.I)
        return m.group(1) if m else ""

    def in_water(self, name):
        """None, "shallow" or "deep": whether she is IN the water where she stands."""
        where = self._where(name)
        if not self.IN_WATER.search(where):
            return None
        return "deep" if self.DEEP.search(where) else "shallow"

    def on_slick(self, name):
        """Is she standing on slick footing (algae, ice, mud, wet stone)?"""
        where = self._where(name)
        return bool(self.SLICK.search(where) or (self.in_water(name) == "shallow"))

    def set_positions(self, text):
        """Store where the director says everyone is (posture is the engine's call: see positions_now). Anyone
        actually IN the water gets soaked (Electric hits them harder); standing near or beside it doesn't count."""
        self.positions = text
        for f in self.active():
            m = re.search(re.escape(f.name) + r"\s*:\s*([^;]*)", text, re.I)
            where = self._place_checked(f.name, m.group(1)) if m else ""
            if m and self.IN_WATER.search(where):
                if not self.has(f, "soaked"):
                    # (said, so a soaked fighter's electric hit later has a cause anyone can see; the place only,
                    # not a pin or a hold the director added that the engine may not have: "pinned face-down by )")
                    said = (self.POS_PLACE.search(where) or self.IN_WATER.search(where)).group(0)
                    print(f"💧 {f.name} is soaked: she is standing in the water ({said.strip()[:60]})")
                if f.status.get("soaked", 0) < 2:   # (topped up, never held: out of the water it still counts down)
                    self.set_status(f, "soaked", 2)
                self._knock_on = []

    # ---------- posture: the one true account of who is up, down, pinned, or holding whom ----------
    UPRIGHT = {"biped": "ON HER FEET (standing upright)", "quadruped": "ON HER FEET (standing on all fours)",
               "serpent": "UP (coils under her, head and neck raised)",
               "avian": "ON HER FEET (standing on her talons, wings folded)"}
    POS_UP = re.compile(r"\b(stand\w*|stood|on (?:her|his|their|all) (?:feet|fours|paws)|upright|circl\w*|stalk\w*|"
                        r"pac(?:ing|es|ed)|rear\w*|crouch\w*|loom\w*|pounc\w*|perch\w*|poised|advanc\w*|"
                        r"back(?:s|ing|ed) (?:away|off)|leap\w*|charg\w*|straddl\w*|atop|on top of|coiled)\b", re.I)
    POS_DOWN = re.compile(r"\b(l(?:ying|ies|ay)|sprawl\w*|prone|supine|face-?(?:down|up|first)|"
                          r"on (?:her|his|their) (?:back|side|belly|stomach|front)|flat (?:on|against)|downed|"
                          r"on the ground|collapsed|crumpled|curled|slumped|underneath)\b", re.I)
    POS_PIN = re.compile(r"\b(pin(?:s|ned|ning)?|held down|holding (?:her|him) down|trapped under)\b", re.I)
    POS_PLACE = re.compile(r"\b((?:at the edge of|at the foot of|half in|in|at|by|near|beside|against|along|behind|"
                           r"below|on|inside)\s+(?:the|a|an)\s+(?:[a-z'-]+\s+){0,3}(?:pool|water|channel|wall|ledge|"
                           r"boulder|stalagmite|stalactite|floor|entrance|shallows|stream|stone|rocks?|cave|cent(?:er|re)|"
                           r"edge|bank|sand|mud|mouth|pillar|slope|shelf))\b", re.I)

    def posture(self, name):
        """Everything certain about how a fighter is placed right now, as a dict."""
        f = self.get(name)
        return {"out": f.eliminated, "down": f.name in self.downed or self.lying_out(f), "facing": self.facing_of(f.name),
                "pinned_by": self.pinned_by(f.name), "pinning": self.pinning(f.name),
                "held_by": [(h.attacker, h.part) for h in self.holds.values() if h.defender == f.name
                            and h.attacker not in self.pinned_by(f.name)],
                "holding": [(h.defender, h.part) for h in self.holds.values() if h.attacker == f.name
                            and h.defender not in self.pinning(f.name)],
                "asleep": self.has(f, "asleep"), "frozen": self.has(f, "frozen")}

    @staticmethod
    def a_an(noun):
        """'a camel clutch', 'an armbar'."""
        return ("an " if re.match(r"(?i)[aeiou]", str(noun)) else "a ") + str(noun)

    def posture_text(self, name, short=False):
        """The same, in words: ON HER FEET / ON THE GROUND and how she lies / PINNED under whom / on top of whom."""
        f = self.get(name)
        p = self.posture(name)
        lie = p["facing"] or "down"
        if p["out"]:
            text = (f"out of the fight, lying {lie}" if p["down"] else "out of the fight, back on her feet")
        elif p["pinned_by"]:
            text = f"ON THE GROUND, {lie}, PINNED under {' and '.join(p['pinned_by'])}"
        elif p["down"]:
            text = f"ON THE GROUND, {lie}, not pinned"
        elif p["pinning"]:
            text = f"ON TOP of {' and '.join(p['pinning'])}, pinning her down"
        elif any(h.sub and h.attacker == f.name for h in self.holds.values()):
            h = next(h for h in self.holds.values() if h.sub and h.attacker == f.name)
            held_up = h.defender not in self.downed       # (an upright hold: both still standing)
            how = ("holding her on her feet, close against her; not standing free" if held_up else
                   "down with her on the ground, wrapped round her; not standing free" if f.name in self.downed else
                   "down on her, wrapped round her; not standing free")
            text = (f"LOCKED ONTO {h.defender} in {self.a_an(h.sub.replace('_', ' '))} ({how})" if not short
                    else f"LOCKED ONTO {h.defender} in {self.a_an(h.sub.replace('_', ' '))}")
        elif self.has(f, "airborne"):
            text = "IN THE AIR (wings beating, above the ground)" if not short else "IN THE AIR"
        else:
            text = self.UPRIGHT[self.body_plan(f)] if not short else self.UPRIGHT[self.body_plan(f)].split(" (")[0]
        if not short:
            if p["held_by"]:
                text += "; " + ", ".join(f"{a} has a grip on her {part}" for a, part in p["held_by"][:3])
            if p["holding"]:
                text += "; " + ", ".join(f"she has a grip on {poss_word(d)} {part}" for d, part in p["holding"][:3])
            grabs = [h for h in self.holds.values() if h.grab and f.name in (h.attacker, h.defender)
                     and self.grab_between(h.attacker, h.defender)]
            if grabs:
                h = grabs[0]
                text += ("; LOCKED TOGETHER at point-blank with " + (h.defender if h.attacker == f.name else h.attacker)
                         + " by that grab (neither can dodge the other)")
        if p["asleep"]:
            text += ", ASLEEP"
        if p["frozen"]:
            text += ", FROZEN in ice"
        return text

    def positions_now(self, include_out=True):
        """Where everyone is, with posture taken from the engine. The director writes its positions line BEFORE the
        beat's end-of-beat rolls (get-ups, escapes), so its claims about standing, lying, facing, or pins are kept
        only when they agree with what actually happened; a clause that disagrees is cut down to the place it names."""
        out = []
        names = [f.name for f in self.fighters.values()]
        for f in self.fighters.values():
            m = re.search(re.escape(f.name) + r"\s*:\s*([^;]*)", self.positions or "", re.I)
            clause = " ".join(m.group(1).split()).strip(" .") if m else ""
            p = self.posture(f.name)
            sure = self.posture_text(f.name, short=True)
            if f.eliminated and not include_out:
                continue  # out of the fight and out of the story until it's over
            if f.eliminated and not clause:
                out.append(f"{f.name}: {sure}")
                continue
            under = re.search(r"\b(?:under(?:neath)?|beneath|below) (?:" + "|".join(map(re.escape, names)) + r")\b",
                              clause, re.I)
            says_up, says_down = self.POS_UP.search(clause), self.POS_DOWN.search(clause) or under
            on_top = re.search(r"\b(?:on top of|astride|straddling|sitting on|lying (?:on|across)|kneeling on) (?:"
                               + "|".join(map(re.escape, names)) + r")\b", clause, re.I)
            says_pin = self.POS_PIN.search(clause) or under or on_top   # "on top of Ripples" after the pin has ended
            wrong = ((p["down"] and says_up and not says_down) or (not p["down"] and says_down)
                     or (says_pin and not (p["pinned_by"] or p["pinning"]))
                     or (p["pinned_by"] and re.search(r"\bpinning\b", clause, re.I))
                     or (p["facing"] == "face-down" and re.search(r"\b(?:on (?:her|his) back|face-?up|supine)\b", clause, re.I))
                     or (p["facing"] == "face-up" and re.search(r"\b(?:face-?down|face-first|on (?:her|his) (?:belly|stomach|front)|prone)\b", clause, re.I))
                     or (p["facing"] in ("face-down", "face-up") and re.search(r"\bon (?:her|his) (?:left |right )?side\b", clause, re.I))
                     or (p["out"] and (says_up or says_pin) and p["down"]))
            if wrong:
                place = self.POS_PLACE.search(clause)
                clause = place.group(1) if place else ""
            clause = self._place_checked(f.name, clause)
            if clause:
                # a grip the director named that has ended since (a tap-out, an escape, a release): its piece goes
                held = {n for h in self.holds.values() for n in (h.attacker, h.defender) if f.name in (h.attacker, h.defender)}
                keep = []
                for piece in re.split(r",\s*", clause):
                    other = [n for n in names if n != f.name and re.search(r"\b" + re.escape(n) + r"\b", piece)]
                    if other and self.GRIP_WORDS.search(piece) and not any(n in held for n in other):
                        continue
                    if piece.strip().upper().startswith("ON HER FEET") or piece.strip() == sure:
                        continue      # (the engine's own posture is already said)
                    keep.append(piece)
                clause = ", ".join(keep)
            out.append(f"{f.name}: {sure}" + (f", {clause}" if clause else ""))
        return "; ".join(out)

    def _broken_heads(self):
        """The last word of each thing that has broken in this fight ("boulder", "pine"): what a position can no
        longer be on, against or beside."""
        gone = list(getattr(self, "broken_props", []) or []) + [m.split(" lies broken")[0] for m in
                                                                   getattr(self, "arena_marks", []) or [] if " lies broken" in m]
        heads = set()
        for g in gone:
            words = re.findall(r"[a-z]{3,}", self._TRAIL.sub("", str(g).lower()))
            if words:
                heads.add(words[-1])
        return heads

    def _place_checked(self, name, clause):
        """The director's words for where she is, put right against what the engine knows (narration.positions_check,
        since build 251): a piece that has her on, against or by something that has broken in this fight goes (Nerine
        stood "on the boulder" every beat after it broke); and while she is down, held or holding at the foot of what
        a charge drove her into, a piece putting her somewhere else (Ripples "in the shallows" while held against the
        oak) becomes "by" that thing."""
        cfg = (self.rules.get("narration") or {}).get("positions_check") or {}
        if not clause or not cfg.get("enabled", True):
            return clause
        heads = self._broken_heads()
        spot = (getattr(self, "lying_at", None) or {}).get(name)
        stuck = spot and (name in self.downed or any(name in (h.attacker, h.defender) for h in self.holds.values()))
        spot_head = (re.findall(r"[a-z]{3,}", self._TRAIL.sub("", str(spot or "").lower())) or [""])[-1]
        keep, moved = [], False
        for piece in re.split(r",\s*", clause):
            low = piece.lower()
            if heads and any(re.search(r"\b(?:on|atop|against|beside|by|near|at|behind|onto|from|top of)\s+(?:the |a |an )?"
                                       r"(?:[a-z'-]+ ){0,2}" + re.escape(h) + r"s?\b", low) for h in heads):
                continue
            if stuck and spot_head and spot_head not in low and (self.IN_WATER.search(piece) or self.POS_PLACE.search(piece)):
                if not moved:
                    keep.append(f"by {spot}")
                    moved = True
                continue
            keep.append(piece)
        return ", ".join(k for k in keep if k.strip())

    GRIP_WORDS = re.compile(r"(?i)\b(jaws?|teeth|bit(e|ing)|grip\w*|grasp\w*|clamp\w*|coil\w*|wrapp?\w*|bound|binding|"
                            r"pinch\w*|squeez\w*|hold\w*|held|lock\w*|choke\w*|crank\w*|twist\w*)\b")

    RECOVERY_DEFAULT = [
        {"label": "out cold", "look": "unconscious and limp, but breathing slow and steady; unresponsive"},
        {"label": "stirring", "look": "twitching, groaning softly, eyelids fluttering; not yet aware of anything"},
        {"label": "awake but down", "look": "conscious and dazed, lifting her head, trying to push herself up, "
                                            "too weak to stand yet"},
        {"label": "back on her feet", "look": "standing shakily, favoring her injuries, breathing hard, aware the "
                                              "match is lost"},
    ]

    def recovery_stage(self, f):
        stages = self.rules.get("recovery", {}).get("stages") or self.RECOVERY_DEFAULT
        return stages[max(0, min(len(stages) - 1, f.recovery))]

    def zone_parts(self, fighter, zones):
        """The fighter's body parts inside the named zones (rules.json body_zones), in body order."""
        cfg = self.rules.get("body_zones", {})
        f = self.get(fighter)
        regions, words, seen = set(), set(), set()

        def add(z):
            z = str(z).lower()
            if z in seen or z not in cfg or z.startswith("_"):
                return
            seen.add(z)
            regions.update(cfg[z].get("regions", []))
            words.update(w.lower() for w in cfg[z].get("words", []))
            for sub in cfg[z].get("zones", []):
                add(sub)
        for z in zones:
            add(z)
        hurt = self.injured_targets(f.name)[0] if any(str(z).lower() in self.INJURED_WORDS for z in zones) else {}
        return [p for p in f.parts if p in hurt or body_region(p) in regions
                or any(re.search(r"\b" + re.escape(w) + r"(?:s|es)?\b", p.lower()) for w in words)]

    INJURED_WORDS = ("injured", "hurt", "wounded", "weakened", "weak")

    def injured_targets(self, name):
        """For the 'injured' focus: the parts of this fighter worth going back to, with a weight each. Parts that
        are already hurt weigh most (more, the worse they are), the parts right next to them come next, and if one
        side of her body is badly hurt, everything on that side is in play too. Returns ({part: weight}, side)."""
        cfg = self.rules.get("director", {}).get("injured_focus", {})
        f = self.get(name)
        names = list(f.parts)
        floor = float(cfg.get("min_damage", 30))
        hurt = {p.name: p.damage for p in f.parts.values() if p.damage >= floor}
        if not hurt:
            return {}, None
        weights = {}
        for n, dmg in hurt.items():
            weights[n] = 40.0 + min(300.0, dmg) / 3.0
        for n in hurt:
            same, near = neighbor_parts(names, n)
            for x in same + near:
                weights.setdefault(x, float(cfg.get("around_weight", 20)))
        total = {"left": 0.0, "right": 0.0}
        for p in f.parts.values():
            if _side(p.name):
                total[_side(p.name)] += p.damage
        bad = max(total, key=total.get)
        other = "right" if bad == "left" else "left"
        side = None
        if (total[bad] >= float(cfg.get("side_damage", 200))
                and total[bad] >= float(cfg.get("side_ratio", 1.5)) * max(1.0, total[other])):
            side = bad
            for x in names:
                if _side(x) == side:
                    weights[x] = max(weights.get(x, 0.0), float(cfg.get("side_weight", 35))) * (1.5 if x in hurt else 1.0)
        return weights, side

    def focus_for(self, attacker):
        """The zones this attacker should aim at (/focus), or []."""
        focus = self.rules.get("director", {}).get("focus", {}) or {}
        name = self.get(attacker).name
        return list(focus[name]) if name in focus else (focus.get("*") or [])   # [] of her own = off for her

    def game_plan(self, name):
        """director.game_plan: the part of her opponent this fighter decided on before the fight began, and means to
        take apart: a zone of the other's body (rolled once, at the start; her /focus decides it when she has one).
        Returns {"against", "zone", "parts", "finish", "since"} or None (off, or no one to plan against)."""
        cfg = self.rules.get("director", {}).get("game_plan") or {}
        if not cfg.get("enabled", True):
            return None
        f = self.get(name)
        plans = self.__dict__.setdefault("game_plans", {})
        plan = plans.get(f.name)
        foes = [o for o in self.active() if o.team != f.team]
        focus = "/".join(str(z) for z in self.focus_for(f.name) if str(z).lower() not in self.INJURED_WORDS)
        if plan and any(o.name == plan["against"] for o in foes) and (not focus or plan["zone"] == focus):
            # (the finish follows the match as it is now: a /set during the fight changes it)
            plan["finish"] = "hold" if self.submission_match() else "wear"
            return plan
        if not foes:
            return None     # (the one it was against is gone: she makes a new one against whoever is left)
        o = foes[0]
        import random as _random
        import zlib
        # (a copy of the dice, nudged by the names: the plan never moves the fight's own rolls)
        r = _random.Random(zlib.crc32(f"{f.name}>{o.name}|{self.rng.getstate()[1][:3]}".encode()))
        zones = [z for z in self.focus_for(f.name) if str(z).lower() not in self.INJURED_WORDS]
        if not zones:
            weights = dict(cfg.get("zones") or {"legs": 3, "neck": 2, "head": 2, "core": 2, "arms": 1.5, "tail": 1})
            if self.submission_match():
                for z, m in (cfg.get("match_weights") or {"legs": 2, "arms": 1.5, "neck": 1.5}).items():
                    weights[z] = weights.get(z, 1) * float(m)
            weights = {z: w for z, w in weights.items() if w > 0 and self.zone_parts(o.name, [z])}
            if not weights:
                return None
            zones = [r.choices(list(weights), list(weights.values()))[0]]
        parts = self.zone_parts(o.name, zones)
        if not parts:
            return None
        plans[f.name] = plan = {"against": o.name, "zone": "/".join(map(str, zones)), "parts": parts,
                                "finish": "hold" if self.submission_match() else "wear", "since": self.turn}
        return plan

    def force_recover(self, name, to=None):
        """Your command, after the match: move a knocked-out fighter up to a recovery stage now (default: one
        stage; 'up' or the last stage = back on her feet). Returns the recovery event."""
        f = self.get(name)
        if not f.eliminated:
            raise ValueError(f"{f.name} isn't out, so there's nothing to recover from (use /getup during a fight)")
        stages = self.rules.get("recovery", {}).get("stages") or self.RECOVERY_DEFAULT
        if to is None:
            target = f.recovery + 1
        else:
            target = int(to)
        target = max(0, min(len(stages) - 1, target))
        if target == f.recovery:
            raise ValueError(f"{f.name} is already {self.recovery_stage(f)['label']}")
        before = self.recovery_stage(f)["label"]
        f.recovery, f.out_beats = target, 0
        st = self.recovery_stage(f)
        return {"type": "recovery", "fighter": f.name, "from": before, "to": st["label"], "look": st["look"],
                "forced": True, "rising": target == len(stages) - 1}

    def recover_tick(self):
        """Fighters who are out slowly come around: each beat they may move up a recovery stage. The chance
        halves for every halves_every points of health lost (so a badly beaten fighter stays down far longer)."""
        cfg = self.rules.get("recovery", {})
        stages = cfg.get("stages") or self.RECOVERY_DEFAULT
        events = []
        for f in self.fighters.values():
            if not f.eliminated or f.recovery >= len(stages) - 1:
                continue
            f.out_beats += 1
            if f.out_beats < int(cfg.get("min_beats_per_stage", 2)):
                continue
            lost = 100.0 * (1.0 - f.health / f.max_health) if f.max_health else 100.0
            chance = float(cfg.get("chance", 0.5)) * 0.5 ** (max(0.0, lost) / max(1.0, float(cfg.get("halves_every", 50))))
            chance = max(float(cfg.get("min_chance", 0.03)), chance)
            if self._chance(chance, f"{f.name} coming round", "a stage better", "no change"):
                before = self.recovery_stage(f)["label"]
                f.recovery += 1
                f.out_beats = 0
                st = self.recovery_stage(f)
                events.append({"type": "recovery", "fighter": f.name, "from": before, "to": st["label"],
                               "look": st["look"], "chance": round(chance, 3)})
        return events

    def default_pin_parts(self, defender, count=3):
        """Most-damaged parts first; for an unhurt fighter, their core (chest, neck, stomach...)."""
        d = self.get(defender)
        hurt = [p.name for p in sorted(d.parts.values(), key=lambda p: -p.damage) if p.damage >= 1][:count]
        if len(hurt) >= count:
            return hurt
        # unhurt (or barely): the core of the body, one part per region, no near-duplicates like Chest + Chest Ruff
        picked = list(hurt)
        for region in ("chest", "neck", "stomach", "belly", "midsection", "upper back", "back", "throat"):
            for p in d.parts.values():
                words = p.name.lower()
                if (words == region or words.endswith(" " + region) or words.startswith(region + " ") and
                        not any(x in words for x in ("ruff", "scales", "fin"))) and p.name not in picked:
                    picked.append(p.name)
                    break
            if len(picked) >= count:
                break
        return picked[:count] or [next(iter(d.parts))]

    def request_struggle(self, pinned, pinner=None):
        """The pinned fighter WILL try to break free on the pin's next beat (the outcome is still rolled)."""
        d = self.get_active(pinned)
        pins = [p for p in self.pins.values() if p["defender"] == d.name
                and (pinner is None or str(pinner).lower() in [m.lower() for m in self.pin_members(p)])]
        if not pins:
            raise ValueError(f"{d.name} isn't pinned right now")
        for st in ("asleep", "frozen"):
            if self.has(d, st):
                raise ValueError(f"{d.name} is {st}: she can't struggle until she comes round")
        for p in pins:
            p["force_attempt"] = True
        return {"type": "struggle_request", "fighter": d.name, "pinner": pins[0]["attacker"],
                "seconds": pins[0]["seconds"]}

    def pin_shape(self, p):
        """What kind of pin this is, for learning: the body regions pressed (a pin on the chest, thigh and arm is the
        same pin whoever does it and whichever side)."""
        regions = sorted({body_region(h.part) for h in self._pin_holds(p)})
        return "+".join(r for r in regions if r)

    def _after_escape(self, ev, pinner, p=None, dfn=None, forced=False):
        """A pin has just been broken. Usually the pinner is shoved off and keeps her feet; sometimes she is thrown
        down beside the fighter she was pinning (pin.struggle.pinner_down_chance; never on your own /pinescape).
        What it leaves behind (pin.aftereffects): the one who was pinned comes out STIFF (trapped limbs numb and
        slow for a beat); a pinner who held on for a long time comes off CRAMPED. And the one who got out remembers
        how (learning)."""
        if p is not None and dfn is not None:
            shape = self.pin_shape(p) or p.get("shape", "")
            if shape:
                got = dfn.learned.setdefault("pins", {})
                got[shape] = got.get(shape, 0) + 1
            acfg = self.rules.get("pin", {}).get("aftereffects") or {}
            if acfg.get("enabled", True):
                after = []
                if int(p.get("beats", 0)) >= int(acfg.get("stiff_after_beats", 2)):
                    self.set_status(dfn, "stiff", int(acfg.get("stiff_beats", 1)))
                    after.append({"fighter": dfn.name, "status": "stiff", "beats": int(acfg.get("stiff_beats", 1))})
                pf = self.fighters.get(str(pinner).lower())
                if pf and int(p.get("beats", 0)) >= int(acfg.get("cramped_after_beats", 4)):
                    self.set_status(pf, "cramped", int(acfg.get("cramped_beats", 1)))
                    after.append({"fighter": pf.name, "status": "cramped", "beats": int(acfg.get("cramped_beats", 1))})
                fcfg = self.rules.get("pin", {}).get("second_wind") or {}
                if (fcfg.get("enabled", True) and int(p.get("beats", 0)) >= int(fcfg.get("after_beats", 3))
                        and self._chance(float(fcfg.get("chance", 0.3)), f"{dfn.name} coming out of the pin furious",
                                         "FURY", "no")):
                    # out of a long pin with a cold, hard anger: harder blows for a beat (stiff or not)
                    self.set_status(dfn, "fury", int(fcfg.get("beats", 1)))
                    after.append({"fighter": dfn.name, "status": "fury", "beats": int(fcfg.get("beats", 1))})
                if after:
                    ev["aftereffects"] = after
        s = self.rules.get("pin", {}).get("struggle", {})
        f = self.fighters.get(str(pinner).lower())
        if forced or f is None or f.eliminated or f.name in self.downed:
            return
        if self._chance(float(s.get("pinner_down_chance", 0.25)), f"{f.name} thrown down by the escape",
                        "she goes down too", "she keeps her feet"):
            facing = self.knock_down(f.name, why=f"{f.name} was thrown off the pin")
            ev["pinner_down"] = {"fighter": f.name, "facing": facing}
            ev["knock_on"] = list(ev.get("knock_on") or []) + list(self._knock_on or [])
            self._knock_on = []

    # ---------- forced pin outcomes (testing / storytelling) ----------
    def force_pin(self, attacker, defender, outcome, contacts=None, flavor=""):
        """outcome 'success': finish the pin now (the remaining seconds of pressure are applied) and the pinned
        fighter faints. 'escape': the pinned fighter breaks free now. With no pin running, 'success' first
        pins the defender (on `contacts`, or their three most-damaged parts)."""
        a, d = self.get_active(attacker), self.get_active(defender)
        key = f"{a.name}>{d.name}"
        host = self.pin_on(d.name)
        if host is not None and a.name in self.pin_members(host):
            key = f"{host['attacker']}>{d.name}"  # she is part of the pin already (maybe as the second pinner)
        cfg = self.rules.get("pin", {})
        started_now = False
        if key not in self.pins:
            if outcome == "escape":
                raise ValueError(f"{a.name} isn't pinning {d.name}")
            if not contacts:
                firm = self.rules["severity"]["hold"].get("firm", 15)
                contacts = [(p, firm, 0.0, "") for p in self.default_pin_parts(d.name, 3)]
            self.start_holds(a.name, d.name, contacts, flavor or "pins them down", pin=True)
            started_now = True
        p = self.pin_on(d.name)  # the pin she is under now (this fighter may have joined someone else's)
        key = f"{p['attacker']}>{d.name}"
        frm, dur = p["seconds"], p["duration"]
        ev = {"type": "pin_forced", "attacker": a.name, "defender": d.name, "seconds_from": frm,
              "duration": dur, "forced": outcome, "started_now": started_now, "flavor": flavor,
              "pressed": [h.part for h in self._pin_holds(p)], "punish_hits": [], "hits_on_pinner": [],
              "pressure_hits": [], "escape_chance": 0.0, "partial_chance": 0.0}
        ev["helpers"] = list(p.get("helpers") or [])
        if outcome == "escape":
            ev["hits_on_pinner"] = self._escape_hit(a, d)
            for h in self._pin_holds(p):  # free of everyone pressing on her
                self.holds.pop(h.id, None)
            self.pins.pop(key, None)
            self.last_pin_end = {"pinner": a.name, "pinned": d.name, "how": "broke free", "second": frm,
                                 "turn": self.turn}
            ev.update(seconds_to=frm, struggle="escape", fight_left="fighting hard")
            return ev
        # success: the rest of the clock's pressure lands in reference-length steps (so it escalates as resistance
        # collapses, just like the real pin would), every struggle is overpowered, and they faint
        ref = max(0.001, cfg.get("reference_seconds", 10))
        if self.fade_mode():
            # no fixed clock: the beats it would still have taken at the usual pace, pressed one after another
            typical = max(1.0, float(cfg.get("fade", {}).get("typical_beats", 6)))
            f0 = float(p.get("fade", 0.0))
            beats = max(1, int(-(-(100.0 - f0) // (100.0 / typical))))
            spb = cfg.get("seconds_per_beat", 10)
            dur = frm + beats * spb
            ev.update(fade_mode=True, fade_from=round(f0, 1), fade_to=100.0, fade_gain=round(100.0 - f0, 1),
                      beats=int(p.get("beats", 0)) + beats, fade_words=self.fade_words(100.0))
            p["fade"], p["beats"] = 100.0, int(p.get("beats", 0)) + beats
        t = frm
        while t < dur - 1e-9:
            step = min(ref, dur - t)
            for h in self._pin_holds(p):
                ev["pressure_hits"].append(self._apply_damage(
                    d, h.part, round(h.power * step / ref * float(cfg.get("damage_mult", 1.0)), 2), cap=self.pin_cap()))
            t += step
        p["seconds"] = dur
        ev["out_cause"] = self.out_cause(p)
        ev.update(seconds_to=dur, struggle="overpowered", fight_left="nearly gone", complete=True,
                  elimination=self.eliminate(d.name, (f"held down for {dur} seconds until she passes out"
                                                      if self.fade_mode() else
                                                      f"held down for the full {dur} seconds and faints")))
        return ev

    # ---------- pins: clock + struggle ----------
    def _pin_when(self, p):
        """When in a pin something happened: 'after N beats' (pins without a clock) or 'at second N' (the old clock)."""
        if self.fade_mode():
            b = max(1, int(p.get("beats") or 0))
            return f"after {b} beat{'s' if b != 1 else ''}"
        return f"at second {p['seconds']}"

    def fade_mode(self):
        """True (the default): a pin has no fixed length. Every beat brings the pinned fighter closer to passing
        out by a varying amount, so it usually takes about pin.fade.typical_beats beats, sometimes fewer, sometimes
        more, and nobody can count toward the end. False: the old rule, a clock that ends at duration_seconds."""
        return bool(self.rules.get("pin", {}).get("fade", {}).get("enabled", True))

    def fade_gain(self, p, dfn, crew, partial=False, roll=None):
        """How much closer to passing out (out of 100) one beat of this pin brings her. The spread is what makes
        the length unknowable: typical_beats on average, with each beat worth more or less than the last."""
        cfg = self.rules.get("pin", {}).get("fade", {})
        typical = max(1.0, float(cfg.get("typical_beats", 6)))
        spread = max(0.0, min(0.95, float(cfg.get("spread", 0.55))))
        r = self.rng.random() if roll is None else roll
        gain = (100.0 / typical) * (1 - spread + 2 * spread * r) * self.pin_time_factor()
        notes = []
        if partial:           # she broke loose for a moment and got air: the pin has to start wearing her down again
            gain *= float(cfg.get("break_loose_mult", 0.4)); notes.append(f"broke loose ×{cfg.get('break_loose_mult', 0.4)}")
        if len(crew) > 1:     # two bodies on her
            gain *= float(cfg.get("double_pin_mult", 1.25)); notes.append(f"double pin ×{cfg.get('double_pin_mult', 1.25)}")
        share = dfn.health / dfn.max_health if dfn.max_health else 0
        if share <= 0:
            gain *= float(cfg.get("below_zero_mult", 1.15)); notes.append(f"health below zero ×{cfg.get('below_zero_mult', 1.15)}")
        elif share >= 0.5:
            gain *= float(cfg.get("strong_mult", 0.8)); notes.append(f"still above half strength ×{cfg.get('strong_mult', 0.8)}")
        # the worse the parts under the press are hurt, the sooner the pain itself takes her under
        on_her = self._pin_holds(p) if p.get("defender") else []
        worst = max([dfn.parts[h.part].damage for h in on_her if h.part in dfn.parts] or [0.0])
        pm = float(cfg.get("pain_mult", 1.15))
        if pm != 1.0 and worst >= 150:
            k = 1.0 + (pm - 1.0) * min(1.0, (worst - 150.0) / 150.0 + 0.4)
            gain *= k; notes.append(f"the pressed parts are in agony ×{k:.2f}")
        gain = min(gain, 100.0 / max(1.0, float(cfg.get("min_beats", 3))))
        if on_her and any(h.coil and self.coil_scope(h.part) != "limb" for h in on_her):
            cm = float((self.rules.get("holds", {}).get("coil") or {}).get("pin_fade_mult", 1.2))
            gain *= cm; notes.append(f"coiled, her blood held back ×{cm:g}")
        return round(gain, 1), round(r, 3), notes

    def out_cause(self, p):
        """Why a fighter held to the end of a pin goes out: {"cause": "choking" | "pain" | "constriction", "part", "with"}. It is one
        or the other. With no grip on her neck or throat it is the pain. With one, it is usually the choke, but
        pin.fade.pain_out_share of the time (less when nothing under the press is badly hurt) the pain gets there
        first. It is colour, decided without touching the fight's dice."""
        import zlib
        dfn = self.get(p["defender"])
        holds = self._pin_holds(p)
        # coils: the constriction cuts off her circulation and slows her heart until she goes under. When coils are
        # part of the pin, that is what takes her (a constrictor's pin is about the squeeze, not the pain)
        # tails or coils wound round her THROAT choke her: that is her air going, told as a choke (by the coils)
        throat_coils = [h for h in holds if h.coil and self.coil_scope(h.part) == "throat"]
        if throat_coils:
            h = max(throat_coils, key=lambda x: x.power)
            return {"cause": "choking", "part": h.part, "with": h.with_part, "coil": True, "kind": "blood"}
        coils = [h for h in holds if h.coil and self.coil_scope(h.part) != "limb"]
        if coils:
            h = max(coils, key=lambda x: (body_region(x.part) in ("chest", "belly", "neck"), x.power))
            return {"cause": "constriction", "part": h.part, "with": h.with_part}
        choke = [h for h in holds if body_region(h.part) == "neck"]
        hurt = sorted((h for h in holds if h.part in dfn.parts and h not in choke),
                      key=lambda h: -dfn.parts[h.part].damage)
        worst = dfn.parts[hurt[0].part].damage if hurt else 0.0
        share = float(self.rules.get("pin", {}).get("fade", {}).get("pain_out_share", 0.22)) * max(0.0, min(1.0, worst / 90.0))
        pick = random.Random(zlib.crc32((f"{getattr(self, '_seed0', 0)}|{self.turn}|{p['attacker']}|{dfn.name}|"
                                         f"{self.times('pinned', dfn.name)}|{worst:.2f}").encode())).random()
        if choke and (not hurt or pick >= share):
            # a grip round the sides of the neck takes her before one pressing the front: that one counts first
            kinds = [(h, self.choke_kind(p["attacker"], h.with_part, h.coil)) for h in choke]
            h, kind = next(((h, k) for h, k in kinds if k == "blood"), next(((h, k) for h, k in kinds if k == "both"),
                                                                                kinds[0]))
            return {"cause": "choking", "part": h.part, "with": h.with_part, "kind": kind}
        h = hurt[0] if hurt else (holds[0] if holds else None)
        return {"cause": "pain", "part": h.part if h else "", "with": h.with_part if h else ""}

    @staticmethod
    def fade_words(fade, strength=None):
        """How far gone she is, in words the story can use (never a number, never a time). Her overall strength
        counts too: a fighter who is nearly spent before the pin has worn her down is never "plenty of fight"."""
        if strength is not None:
            fade = max(fade, 55 if strength <= 5 else 30 if strength < 25 else 0)
        return ("still has plenty of fight in her" if fade < 30 else
                "weakening: her struggles are slower and her breath shorter" if fade < 55 else
                "fading: her limbs are heavy, her sight is greying at the edges, sounds come from far away" if fade < 80
                else "nearly out: barely moving, her eyes sliding shut and dragging open again")

    def _fade_clause(self, fade, strength=None):
        """fade_words as the end of a sentence that starts with her name: "Ripples still has plenty of fight in
        her", "Ripples is weakening: ..." (not "is still has")."""
        words = self.fade_words(fade, strength)
        return words if words.startswith("still has") else "is " + words

    def pin_time_factor(self):
        cfg = self.rules.get("pin", {})
        return cfg.get("seconds_per_beat", 10) / max(0.001, cfg.get("reference_seconds", 10))

    @staticmethod
    def _per_beat(p10, factor):
        """Convert a chance written per reference beat into the chance for a beat `factor` times as long."""
        p10 = max(0.0, min(0.999, p10))
        return 1 - (1 - p10) ** factor
    def escape_base(self, dfn):
        """The chance that ONE escape attempt works, from the pinned fighter's health alone (before the pinner's
        condition, the clock's fade, and statuses). With pin.struggle.escape_easy_above set (default 50), it stays
        high while she has that much of her health left, sliding from escape_chance at full health to
        escape_chance_at_edge at the edge, then halves for every escape_halves_every points she loses below it,
        on into negative health. With escape_easy_above 0 it is the old curve: halving from full health."""
        s = self.rules.get("pin", {}).get("struggle", {})
        full = float(s.get("escape_chance", 0.65))
        hp = 100.0 * max(-3.0, min(1.0, dfn.health / dfn.max_health)) if dfn.max_health else 0.0
        every = max(1.0, float(s.get("escape_halves_every", 20)))
        edge = float(s.get("escape_easy_above", 0) or 0)
        if edge <= 0:
            lost = 100.0 - hp
            return full * 0.5 ** ((lost // every) if s.get("escape_steps", False) else (lost / every))
        at_edge = float(s.get("escape_chance_at_edge", full))
        if hp >= edge:
            return at_edge + (full - at_edge) * (hp - edge) / max(1.0, 100.0 - edge)
        pts = sorted((float(a), float(b)) for a, b in (s.get("escape_points") or []) if a < edge)
        if pts:
            # below the edge, the chance follows these points ([health %, chance], straight lines between them, flat
            # past the last one): harder and harder, never nothing
            pts = pts + [(edge, at_edge)]
            if hp <= pts[0][0]:
                return pts[0][1]
            for (h0, c0), (h1, c1) in zip(pts, pts[1:]):
                if h0 <= hp <= h1:
                    return c0 + (c1 - c0) * (hp - h0) / max(0.001, h1 - h0)
            return at_edge
        below = edge - min(hp, edge) if hp >= 0 else edge
        base = at_edge * 0.5 ** ((below // every) if s.get("escape_steps", False) else (below / every))
        if hp < 0:
            # past nothing left: every escape_halves_every_below_zero points under zero halves it again, so a pin on a
            # fighter far below zero is close to final
            deep = max(0.5, float(s.get("escape_halves_every_below_zero", 5)))
            base *= 0.5 ** (-hp / deep)
        return base

    def pin_chance(self, target):
        """How likely an opening for a NEW pin on this fighter is in any one beat. A pin can come at any point, but
        the more hurt she is, the likelier: rare against a fresh fighter on her feet, rising smoothly as she wears down,
        much likelier under half strength and toward certain as she nears nothing. Each badly hurt part adds a little
        (her opponent knows where they are). A knockdown makes it likelier at every level. It rises over a fight only
        because she gets more hurt."""
        cfg = self.rules.get("director", {}).get("pin_urge")
        cfg = cfg if isinstance(cfg, dict) else {}
        weak_below = float(cfg.get("weak_below", 50))
        s = self.strength(target)
        down = target.name in self.downed
        # on the ground at full strength is only a little likelier than standing (she is up again in a moment); the
        # knockdown counts for more and more as she wears down
        fresh = float(cfg.get("downed_fresh", cfg.get("downed", 0.30)) if down else cfg.get("standing", 0.06))
        weak = float(cfg.get("weak_downed", 0.85) if down else cfg.get("weak_standing", 0.45))
        if s < weak_below:
            base = weak + (float(cfg.get("max", 0.95)) - weak) * max(0.0, min(1.0, (weak_below - s) / max(1.0, weak_below)))
        else:
            # the more hurt she is, the likelier: from `fresh` at full strength up to `weak` at weak_below (a curve:
            # a little worn changes little, badly worn a lot)
            t = max(0.0, min(1.0, (100.0 - s) / max(1.0, 100.0 - weak_below)))
            base = fresh + (weak - fresh) * t ** float(cfg.get("curve", 1.5))
        # badly hurt parts make her easier to get down and hold, and her opponent knows where they are: each part at
        # hurt_at %+ damage adds hurt_bonus (up to hurt_cap)
        bad = sum(1 for p in target.parts.values() if p.damage >= float(cfg.get("hurt_at", 150)))
        base += min(float(cfg.get("hurt_cap", 0.2)), float(cfg.get("hurt_bonus", 0.02)) * bad)
        if self.has(target, "asleep") or self.has(target, "frozen"):
            base = max(base, float(cfg.get("helpless", 0.9)))  # she can't defend herself at all
        if any(h.coil and h.defender == target.name and self.coil_scope(h.part) != "limb" for h in self.holds.values()):
            # wrapped in coils already: the coiler only has to bear her down inside them (holds.coil.pin_opening)
            base = max(base, float((self.rules.get("holds", {}).get("coil") or {}).get("pin_opening", 0.5)))
        # your own dial on how often pins come (/pins): 0.5 = half as many openings, 2 = twice, 0 = the director
        # never starts one (your /pin and typed directions still can)
        base *= float(cfg.get("scale", 1.0) if cfg.get("scale") is not None else 1.0)
        return max(0.0, min(1.0, base))

    def roll_pin_windows(self, open_all=False):
        """Once per beat, before the director chooses: is there an opening to start a pin on each fighter? The
        director can only start a pin where there is one (your own /commands and typed directions always can)."""
        self.pin_window = {}
        for f in self.active():
            if self.pinned_by(f.name):
                continue
            if self.no_pins():
                self.pin_window[f.name] = False     # no pins at all in this fight (finish.no_pins)
                continue
            first = int((self.rules.get("pin") or {}).get("openings_from_beat", 2))
            if not open_all and self.turn + 1 < first:
                self.pin_window[f.name] = False   # nobody has traded a blow yet: no opening to pin anyone
                continue
            self.pin_window[f.name] = bool(open_all) or self._chance(self.pin_chance(f), f"pin opening on {f.name}",
                                                                     "OPEN", "none")
        self.roll_sub_windows(open_all)
        for f in self.active():   # /play dice free: every opening is there for her
            if f.name in self.lucky:
                for o in self.active():
                    if o is not f and not (f.team and o.team == f.team) and not self.pinned_by(o.name):
                        self.pin_window[o.name] = True
                        self.sub_window[o.name] = True
        self.tactics_before()
        for name in [f.name for f in self.active()]:
            hs = [h for h in self.holds.values() if h.defender == name and h.sub]
            scale = float(((self.rules.get("director") or {}).get("pin_urge") or {}).get("scale", 1.0) or 0)
            if hs and scale > 0 and self.sub_stuck(self.get(name), hs):
                self.pin_window[name] = True    # she can't break it: the holder can let go and pin her (not with /pins off)
        return self.pin_window

    PIN_REACH = ("muzzle", "nose", "jaw", "cheek", "ear", "head", "neck", "throat", "chest", "ruff", "shoulder",
                 "foreleg", "forepaw", "arm", "paw", "fin", "belly", "stomach", "flank", "ribs")

    def _escape_hit(self, att, dfn, key="escape_severity", always=False):
        """The blow that gets a pinned fighter out (or partly out): a pinned fighter can only reach what's above her:
        the pinner's face, neck, chest, belly, forelimbs. pin.struggle.escape_hit false turns the escape blow off."""
        s = self.rules.get("pin", {}).get("struggle", {})
        if not always and not s.get("escape_hit", True):
            return []
        near = [p for p in att.parts if any(k in p.lower() for k in self.PIN_REACH)]
        target = self.rng.choice(near or list(att.parts))
        power = self.power_for("instant", s.get(key) or s.get("counter_severity", "solid"))
        self._source = f"{poss_word(dfn.name)} {'escape' if key == 'escape_severity' else 'struggle'}"
        return [self._apply_damage(att, target, power)]

    def _pin_holds(self, p):
        who = self.pin_members(p)
        return [h for h in self.holds.values() if h.attacker in who and h.defender == p["defender"]]

    def _advance_pins(self, skip_hold_ids=()):
        """Each beat of a pin runs the clock and rolls the pinned fighter's struggle."""
        cfg = self.rules.get("pin", {})
        s = cfg.get("struggle", {})
        spb = cfg.get("seconds_per_beat", 10)
        events = []
        for key, p in list(self.pins.items()):
            if key not in self.pins:
                continue  # ended earlier this beat (e.g. someone fainted in another pin)
            holds = self._pin_holds(p)
            att, dfn = self.fighters.get(p["attacker"].lower()), self.fighters.get(p["defender"].lower())
            if not holds or not att or not dfn or att.eliminated or dfn.eliminated:
                self.pins.pop(key, None)  # released, broken, or someone is out
                continue
            crew = [self.fighters[m.lower()] for m in self.pin_members(p)]  # one pinner, or two in a double pin
            if all(h.id in skip_hold_ids for h in holds) or p.get("started_turn") == self.turn - 1:
                # the pin was only just established this beat (a grip she already had may be part of it: that
                # grip keeps pressing, but the clock and the first struggle start next beat)
                continue
            fm = self.fade_mode()
            frm = p["seconds"]
            p["seconds"] = frm + spb if fm else min(p["duration"], frm + spb)
            f0 = float(p.get("fade", 0.0))
            p["beats"] = int(p.get("beats", 0)) + 1
            self.involved.update({dfn.name} | {m.name for m in crew})

            # how much fight the pinned one has left, relative to the pinner, fading as the clock runs
            # The pinned fighter's OWN condition decides most of it: a critically hurt fighter can barely
            # buck anyone off, even a hurt pinner. The pinner's injuries only loosen the pin a little.
            d_str = max(0.03, min(1.0, dfn.health / dfn.max_health))
            a_weak = 1.0 - max(0.0, min(1.0, max(m.health / m.max_health for m in crew)))  # the freshest pinner counts
            escape_mult = (d_str ** 2) * (0.8 + 0.6 * a_weak)
            partial_mult = (0.35 + 0.65 * d_str) * (0.8 + 0.6 * a_weak)
            # how far along the pin is: the old clock's share of its length, or how close she is to going under
            typical = max(1.0, float(cfg.get("fade", {}).get("typical_beats", 6)))
            progress = min(1.0, (f0 + 100.0 / typical) / 100.0) if fm else p["seconds"] / max(1, p["duration"])
            fade_from = s.get("fade_from", 0.5)
            fade = 1.0 if progress <= fade_from else max(0.15, 1 - 0.85 * (progress - fade_from) / (1 - fade_from))
            tf = self.pin_time_factor()
            attempt_p = self._per_beat(s.get("attempt_chance", 0.85) * (0.4 + 0.6 * fade), tf)
            # chance that an attempt (if it happens) escapes: escape_chance at full health, halved for every
            # escape_halves_every points of health lost (smooth, or in whole steps), on into negative health
            base = self.escape_base(dfn)
            curve = base / max(0.001, float(s.get("escape_chance", 0.65)))  # 1.0 at full health, falling as she weakens
            crowd = float(cfg.get("double_pin_escape_mult", 0.5)) ** (len(crew) - 1)  # two on one: far harder to shift
            esc_try = base * (1 + 0.6 * a_weak) * fade * crowd
            buff = float(s.get("break_loose_buff", 1.5) or 1.0) if p.get("buff_beats", 0) > 0 else 1.0
            if buff != 1.0:  # she broke loose recently: momentum makes the next escape likelier
                esc_try *= buff
                p["buff_beats"] -= 1
            sec_cfg = cfg.get("secure", {})
            unmet = (sec_cfg.get("enabled", False) and not self.pin_securable(dfn)[0]) or self.ko_only()
            if unmet:  # not worn down enough to be held: every escape attempt is likelier
                esc_try *= float(sec_cfg.get("unmet_escape_mult", 2.0))
            if self.has(dfn, "paralyzed"):
                esc_try *= float(self._cfg("status_effects").get("paralyzed_escape_mult", 0.5))
            if self.has(dfn, "restrained"):
                # barely matters to a healthy fighter; full effect only once she's badly hurt
                rcfg = cfg.get("restrain", {})
                full_below = float(rcfg.get("full_effect_below", 30))
                worn = max(0.0, min(1.0, (100 - self.strength(dfn)) / max(1.0, 100 - full_below)))
                esc_try *= 1 - (1 - float(rcfg.get("escape_mult", 0.6))) * worn
            if self.has(dfn, "asleep") or self.has(dfn, "frozen"):
                esc_try *= 0.1  # can barely fight back
            if self.has(dfn, "sputtering"):
                esc_try *= float(self._cfg("status_effects").get("sputtering_escape_mult", 0.75))
            if self.has(dfn, "breathless"):
                esc_try *= float(self._cfg("status_effects").get("breathless_escape_mult", 0.8))
            if self.has(dfn, "soaked"):     # wet fur: the grips slide
                esc_try *= float(self._cfg("status_effects").get("soaked_escape_mult", 1.1))
            esc_try *= self.dominated(dfn.name) * self.trait(dfn, "escape") / max(
                0.05, sum(self.trait(m, "hold") for m in crew) / max(1, len(crew)))
            if self.has(dfn, "adrenaline"):
                esc_try *= float(self._cfg("adrenaline").get("escape_mult", 1.5))
            if any(h.coil and h.defender == dfn.name and h.attacker in {m.name for m in crew}
                   and body_region(h.part) in self.MIDDLE_REGIONS and self.coil_dwarfs(h.attacker, dfn.name)
                   for h in self.holds.values()):
                # (holds.coil.size) pinned inside the coils of something many times her size: hard to buck off
                esc_try *= float((self.coil_size_cfg() or {}).get("escape_mult", 0.6))
            if p.get("against"):   # jammed against something solid: nowhere to bridge or roll to on that side
                esc_try *= float(cfg.get("against_escape_mult", 0.85))
            # holding a pin is work: every beat costs the pinner breath, and a pinner who is running out of it holds
            # less surely (pin.pinner_energy_per_beat, pin.tired_pinner_escape_mult)
            per = float(cfg.get("pinner_energy_per_beat", 3) or 0)
            for m in crew:
                m.energy = max(0.0, m.energy - per)
            tired_pinner = att.energy < float(self._cfg("energy").get("tired_below", 25))
            if tired_pinner:
                esc_try *= float(cfg.get("tired_pinner_escape_mult", 1.2))
            # she has broken out of a pin like this before: she knows where it gives (learning.pin_escape_per_time)
            lcfg = self.rules.get("learning") or {}
            p["shape"] = self.pin_shape(p) or p.get("shape", "")   # kept: the holds are gone by the time she's out
            known = (dfn.learned.get("pins") or {}).get(p["shape"], 0) if lcfg.get("enabled", True) else 0
            if known:
                esc_try *= min(float(lcfg.get("pin_escape_cap", 1.45)), 1 + float(lcfg.get("pin_escape_per_time", 0.15)) * known)
            # never impossible: however hurt she is and however long it has run, an attempt can still work
            # (pin.struggle.escape_floor; break_loose_floor for breaking loose for a moment)
            esc_try = max(float(s.get("escape_floor", 0.05)), esc_try)
            esc = self._per_beat(min(0.95, esc_try), tf)
            # if the escape fails: the chance to break loose for a moment and land a hit, same curve
            part_try = s.get("partial_chance", 0.50) * curve * (1 + 0.6 * a_weak) * fade * crowd
            part_try = max(float(s.get("break_loose_floor", 0.05)), part_try)
            part = self._per_beat(min(0.95, part_try), tf)
            if self.has(dfn, "asleep") or self.has(dfn, "frozen"):
                # asleep or frozen under the pin: no struggle at all, no breaking loose, no blow on the pinner
                attempt_p, esc, part = 0.0, 0.0, 0.0
                p.pop("force_attempt", None)

            ev = {"type": "pin_progress", "attacker": att.name, "defender": dfn.name,
                  "seconds_from": frm, "seconds_to": p["seconds"], "duration": p["duration"],
                  "struggle": "none", "escape_chance": round(esc, 3), "partial_chance": round(part, 3),
                  "buffed": buff if buff != 1.0 else None,
                  # how much fight shows: the clock's fade AND the pinned fighter's own condition
                  "fight_left": (lambda v: "fighting hard" if v > 0.7 else "weakening" if v > 0.45
                                 else "fading" if v > 0.2 else "nearly gone")(fade * (0.25 + 0.75 * d_str)),
                  "hits_on_pinner": [], "punish_hits": [], "pressed": [h.part for h in holds],
                  "helpers": [m.name for m in crew[1:]], "pinner_tired": tired_pinner, "knows_pin": known}
            if p.get("against"):
                ev["against"] = p["against"]
            forced_try = p.pop("force_attempt", False)  # the story asked for an escape attempt this beat
            pas = getattr(self, "_passive", None)
            if pas and pas[0] == self.turn and dfn.name in pas[1]:
                attempt_p, forced_try = 0.0, False      # (since build 278) her player has her do nothing
            if self.has(dfn, "stunned"):
                attempt_p, forced_try = 0.0, False      # (since build 293) stunned: she can't try
            if forced_try or self._chance(attempt_p, f"{dfn.name} making an escape attempt", "she tries",
                                          "no real attempt"):
                roll = self.rng.random()
                ev["roll"] = round(roll, 3)
                ev["try_how"] = self.vary("struggle")
                if roll < esc or (dfn.name in self.lucky and not any(m.name in self.lucky for m in crew)):
                    # (/play dice free: every try of hers gets her out, unless her pinner is dice-free too)
                    ev["struggle"] = "escape"
                    ev["hits_on_pinner"] = self._escape_hit(self.rng.choice(crew), dfn)
                    # now and then the pinner's jaws don't come off with the rest: she is thrown off the pin but
                    # keeps her bite, and that one grip goes on as an ordinary hold (pin.struggle.keep_jaws)
                    bite = next((h for h in holds if re.search(r"\b(jaws?|teeth|fangs?|bite)\b", str(h.with_part or "").lower())),
                                None)
                    keep = None
                    if bite is not None and self._chance(float(s.get("keep_jaws", 0.08)),
                                                         f"{bite.attacker} keeping her jaws on {poss_word(dfn.name)} "
                                                         f"{bite.part.lower()} through the escape", "she hangs on",
                                                         "they come off too"):
                        keep = bite
                    for h in holds:  # free of everyone who was pressing on her
                        if h is not keep:
                            self.holds.pop(h.id, None)
                    self.pins.pop(key, None)
                    self.last_pin_end = {"pinner": att.name, "pinned": dfn.name, "how": "broke free",
                                         "second": p["seconds"], "turn": self.turn}
                    self._after_escape(ev, att.name, p, dfn)
                    if keep is not None and isinstance(ev.get("pinner_down"), dict) \
                            and ev["pinner_down"].get("fighter") == keep.attacker:
                        self.holds.pop(keep.id, None)      # thrown down off her: the bite is torn loose too
                    elif keep is not None:
                        keep.change_per_turn = 0.0
                        ev["kept_grip"] = {"hold_id": keep.id, "attacker": keep.attacker, "part": keep.part,
                                           "with": keep.with_part}
                elif (ev.__setitem__("roll2", round(self.rng.random(), 3)) or ev["roll2"]) < part:
                    ev["struggle"] = "partial"
                    p["buff_beats"] = int(s.get("break_loose_buff_beats", 1) or 0)  # momentum for the next try
                    # a pinned fighter can only reach what's above them: the pinner's face, neck, chest, forelimbs
                    ev["hits_on_pinner"] = self._escape_hit(self.rng.choice(crew), dfn, key="counter_severity", always=True)
                else:
                    ev["struggle"] = "fail"
                    h = self.rng.choice(holds)
                    power = round(self.power_for("instant", s.get("punish_severity", "solid"))
                                  * float(cfg.get("damage_mult", 1.0)), 2)
                    ev["punish_hits"] = [self._apply_damage(dfn, h.part, power, cap=self.pin_cap())]
                    ev["punish_with"] = h.with_part
            if fm and key in self.pins:
                gain, gr, gnotes = self.fade_gain(p, dfn, crew, partial=ev["struggle"] == "partial")
                p["fade"] = round(min(100.0, f0 + gain), 1)
                ev.update(fade_mode=True, fade_from=round(f0, 1), fade_to=p["fade"], fade_gain=gain, fade_roll=gr,
                          fade_notes=gnotes, beats=p["beats"], fade_words=self.fade_words(p["fade"], self.strength(dfn)))
            elif fm:
                ev.update(fade_mode=True, fade_from=round(f0, 1), fade_to=round(f0, 1), fade_gain=0.0, beats=p["beats"])
            done = (float(p.get("fade", 0.0)) >= 100.0) if fm else (p["seconds"] >= p["duration"])
            if (key in self.pins and done and unmet
                    and self._chance(1.0 if self.ko_only() else float(sec_cfg.get("final_kickout_chance", 0.85)),
                                     f"{dfn.name} kicking out at the last second", "she kicks out", "no")):
                # the pin can't be won yet: she kicks out at the last second
                ev.update(struggle="escape", last_second=True,
                          why_not="only a knockout ends a fight (finish.knockout_only)" if self.ko_only()
                          else self.pin_securable(dfn)[1])
                ev["hits_on_pinner"] = ev.get("hits_on_pinner", []) + self._escape_hit(self.rng.choice(crew), dfn)
                for h in self._pin_holds(p):
                    self.holds.pop(h.id, None)
                self.pins.pop(key, None)
                self.last_pin_end = {"pinner": att.name, "pinned": dfn.name, "how": "kicked out at the last second",
                                     "second": p["seconds"], "turn": self.turn}
                ev.setdefault("try_how", self.vary("struggle"))
                self._after_escape(ev, att.name, p, dfn)
            if key in self.pins and done:
                ev["complete"] = True
                ev["out_cause"] = self.out_cause(p)
                if cfg.get("faint_at_end", True):
                    ev["elimination"] = self.eliminate(
                        dfn.name, (f"held down until she passes out from "
                                   f"{ {'choking': 'the choke', 'constriction': 'the constriction'}.get(ev['out_cause']['cause'], 'the pain')}" if fm else
                                   f"held down for the full {p['duration']} seconds and faints"))
                self.pins.pop(key, None)
            events.append(ev)
        return events

    def pinfall(self, attacker, defender):
        a, d = self.get_active(attacker), self.get_active(defender)
        base = max(0.0, d.health / d.max_health)
        counts = []
        for i, factor in enumerate(self.rules["pinfall"]["count_factors"], start=1):
            chance = max(0.0, min(1.0, base * factor))
            roll = self.rng.random()
            kicked = roll < chance
            counts.append({"count": i, "kickout_chance": round(chance, 3),
                           "roll": round(roll, 3), "kicked_out": kicked})
            if kicked:
                break
        result = "kickout" if counts[-1]["kicked_out"] else "pinned"
        released = []
        if result == "pinned":
            released = self._put_out(d)
        return {"type": "pinfall", "attacker": a.name, "defender": d.name,
                "eliminated": d.name if result == "pinned" else None,
                "holds_ended": released, "winner": self.winner(),
                "defender_health": round(d.health, 2), "max_health": d.max_health, "counts": counts, "result": result,
                "kicked_out_at": counts[-1]["count"] if result == "kickout" else None}

    def no_pins(self):
        """No pins at all: finish.no_pins (with finish.knockout_only), so the fight is won by a knockout blow; or a
        submission match with finish.submission.no_pins (on by default), won only by a tap-out or a pass-out."""
        cfg = self.rules.get("finish") or {}
        sub = cfg.get("submission") if isinstance(cfg.get("submission"), dict) else {}
        return bool((cfg.get("knockout_only", False) and cfg.get("no_pins", False))
                    or (sub.get("enabled", False) and sub.get("no_pins", True)))

    def traits_cfg(self):
        cfg = self.rules.get("traits") or {}
        return cfg if cfg.get("enabled", True) else None

    def quirk_moment(self, f, quirk, note):
        """(since build 281, narration.character.moments) a quirk of hers decided something this beat: said once to
        the story (play.py puts it with the beat's other events), so her character shows where it matters."""
        name = f.name if hasattr(f, "name") else str(f)
        got = self.__dict__.setdefault("_quirks_now", [])
        if not any(x[0] == name and x[1] == quirk for x in got):
            got.append((name, quirk, note))

    def quirk(self, f, name):
        """(since build 280) traits.quirks.<name> for this fighter, when she has that quirk and it is switched on
        (its settings, a dict); None otherwise."""
        cfg = self.traits_cfg()
        f = self.get(f) if isinstance(f, str) else f
        if not cfg or f is None or name not in (getattr(f, "quirks", None) or []):
            return None
        q = (cfg.get("quirks") or {}).get(name) or {}
        return q if q.get("enabled", True) else None

    def trait(self, f, name):
        """(since build 280) traits: how she fights, as a multiplier on today's rolls (1.0 = as before): speed (her
        dodge, her counter, meeting a move with her own), hold (how hard her grips bite and how hard they are to
        break), escape (breaking holds, escaping pins), toughness (being staggered or rocked), stamina (what moves
        cost her), striking (landing where she aims, devastating blows), learning (reading a move she has seen).
        Her quirks move some of them where they fit (water_born, hates_water, out_of_depth)."""
        cfg = self.traits_cfg()
        f = self.get(f) if isinstance(f, str) else f
        if not cfg or f is None:
            return 1.0
        v = float((getattr(f, "traits", None) or {}).get(name, 1.0))
        wet = self.in_water(f.name) or self.has(f, "soaked")
        q = self.quirk(f, "water_born")
        if q and self.in_water(f.name) and name in ("speed", "escape"):
            v *= float(q.get("mult", 1.15))
        q = self.quirk(f, "hates_water")
        if q and wet and name in ("speed", "striking"):
            v *= float(q.get("mult", 0.88))
        q = self.quirk(f, "out_of_depth")
        if q and name == "escape":
            seen = int((f.learned or {}).get("held_count", 0))
            v *= min(1.0, float(q.get("start", 0.75)) + float(q.get("per_hold", 0.08)) * seen)
        q = self.quirk(f, "unshakeable")
        if q and name == "toughness":
            v *= float(q.get("mult", 1.3))
        return max(0.05, v)

    def dominated(self, name):
        """(since build 277) director.plan_dominate: under /plan dominate, how much of her usual chance the one being
        dominated gets to fight back (a dodge, a counter, meeting a move with her own, breaking a hold or a pin):
        1.0 for anyone else, or with the switch off."""
        cfg = (self.rules.get("director") or {}).get("plan_dominate") or {}
        win = (self.plan or {}).get("winner")
        if (self.plan or {}).get("shape") != "dominate" or not win or not cfg.get("enabled", True):
            return 1.0
        f, w = self.fighters.get(str(name).lower()), self.fighters.get(str(win).lower())
        if not f or not w or f.name == w.name or f.team == w.team:
            return 1.0
        return max(0.0, float(cfg.get("defence_mult", 0.4)))

    def sub_knockouts(self):
        """finish.submission.allow_knockouts (since build 282, off by default): a submission match where a knockout
        blow ends it too (the /preset anything match: a knockout, a pin held to its end or a tap-out)."""
        return bool(((self.rules.get("finish") or {}).get("submission") or {}).get("allow_knockouts", False))

    def submission_match(self):
        """finish.submission.enabled: a submission match. Only a tap-out or a pass-out ends it: no knockouts from blows.
        Each beat a submission (or a choke, or a coil round her) has been on, the one in it may TAP OUT; in a choke
        she may PASS OUT instead; and a pin held to its end still puts her out (she passes out under it)."""
        return bool(((self.rules.get("finish") or {}).get("submission") or {}).get("enabled", False))

    def _tap_out_tick(self):
        """finish.submission: after the pressure lands, everyone held in a submission, a choke, a coil or any other hold
        that hurts (for at least two beats; not a pin, and a grab only on a badly hurt part or once her health is gone: tap.grabs) may tap out, and a choke may make her pass out. A tap-out is resisted while she can: the pain she
        must resist (the gripped part's damage, a share of the other gripped parts, and more each beat it stays on)
        against her resistance (tap.resist, scaled by her overall strength; an adrenaline surge raises it). Only pain
        past her resistance can make her tap, likelier the further past it. A choke builds air hunger every beat
        against her endurance (her strength again). Close to her limit without giving in is a tap_resist event. A pin
        has its own pass-out (its clock), so a pinned fighter doesn't roll here."""
        cfg = (self.rules.get("finish") or {}).get("submission") or {}
        if not cfg.get("enabled", False) or self.winner():
            return []
        tcfg, ccfg = cfg.get("tap") or {}, cfg.get("choke") or {}
        events, pairs = [], {}
        gcfg = tcfg.get("grabs") or {}
        for h in self.holds.values():
            if h.locked:
                continue      # (a pin has its own pass-out)
            if h.grab:
                # a grab only holds her there, unless (tap.grabs) it is clamped on a part already hurt past
                # min_damage, or she has no health left: then the grip itself is what she can't bear
                gd = self.fighters.get(str(h.defender).lower())
                if not gcfg.get("enabled", True) or not gd or not (
                        (h.part in gd.parts and gd.parts[h.part].damage >= float(gcfg.get("min_damage", 100)))
                        or gd.health <= 0):
                    continue
            pairs.setdefault((h.attacker, h.defender), []).append(h)
        for (a, dn), hs in pairs.items():
            d = self.fighters.get(dn.lower())
            holder = self.fighters.get(str(a).lower())
            if self.winner() or (holder is not None and holder.eliminated):
                continue      # (the match ended a moment ago, or the one holding her is out: that grip is gone)
            if not d or d.eliminated or self.pinned_by(dn):
                continue
            # (the hold's first beat: nobody taps yet, but in a submission the urge is already there: tap.urge)
            first = max(h.turns_active for h in hs) < 2
            urge_first = any(h.sub for h in hs) and ((tcfg.get("urge") or {}).get("enabled", True)
                                                     and (tcfg.get("urge") or {}).get("submissions", True))
            # (tap.meter_all, since build 274) any other hold that hurts counts toward a tap too: on its first beat
            # the window's tap meter shows it already (she can't tap yet), with no struggle told
            if first and not urge_first and not tcfg.get("meter_all", True):
                continue
            beats = max(h.turns_active for h in hs)
            # finish.submission.taps: a gripped part her taps have used up adds nothing toward the next tap: the
            # pain, the pressure and the choke all come from the parts that still count (a ruined thigh already
            # spent can't carry a tap that is then credited to a fresh grip beside it)
            spent_now = set(self.spent_tap_parts(d)) if self._taps_rule() else set()
            hs = [h for h in hs if h.part not in spent_now] or hs
            # THE PAIN SHE MUST RESIST: how hurt the gripped part is (the worst one, and a share of the others), and
            # worse every beat the hold stays on and cranks. HER RESISTANCE: her will, which her overall strength
            # carries: fresh, she can bear a great deal; worn down, much less. She holds on while she can.
            dmg = sorted((d.parts[h.part].damage for h in hs if h.part in d.parts), reverse=True) or [0.0]
            pain = (dmg[0] + float(tcfg.get("second_part", 0.4)) * sum(dmg[1:])
                    + float(tcfg.get("per_beat", 15)) * (beats - 1))
            # and the grip itself: how hard it is pressing right now, which climbs the longer it stays on (its own
            # tightening and holds.build), on top of what the part already carries (tap.press of that pressure)
            bcfg = self.rules.get("holds", {}).get("build") or {}
            presses = sorted((h.power * (min(float(bcfg.get("pain_max", 1.5)), 1.0 + float(bcfg.get("pain_per_beat", 0.08))
                                             * max(0, h.turns_active - 1)) if bcfg.get("enabled", True) else 1.0)
                              for h in hs), reverse=True)
            pain += float(tcfg.get("press", 1.5)) * (presses[0] + float(tcfg.get("second_part", 0.4)) * sum(presses[1:]))
            rcfg_ = self.rules.get("ruined") or {}
            if rcfg_.get("enabled", True):
                # a grip on a RUINED part: past anything she can brace against (ruined.tap_pain for each one)
                pain += float(rcfg_.get("tap_pain", 30)) * sum(1 for h in hs if h.part in d.parts
                                                                  and self.is_ruined(d.parts[h.part]))
            s_ = max(0.0, min(100.0, self._health_pct(d)))   # (her overall health: what she has left to resist with)
            power = float(tcfg.get("resist_power", 0.8))
            surge = float(tcfg.get("surge_resist", 1.5)) if self.has(d, "adrenaline") else 1.0
            resist = max(10.0, float(tcfg.get("resist", 130)) * (s_ / 100.0) ** power * surge)
            over = pain - resist
            ceiling = float(tcfg.get("max", 0.85))
            ccl = tcfg.get("climb") or {}
            if ccl.get("enabled", True):
                # THE CEILING CLIMBS: the longer the hold stays on, the likelier giving in can get (start, then
                # per_beat more each beat after the second), and the more strength she has left, the lower it stays
                ceiling = min(ceiling, float(ccl.get("start", 0.2)) + float(ccl.get("per_beat", 0.1)) * max(0, beats - 2))
                ceiling *= max(0.0, 1.0 - float(ccl.get("health_hold", 0.6)) * s_ / 100.0)
            top = float(tcfg.get("max", 0.85))
            tap = min(ceiling, max(0.0, over / float(tcfg.get("span", 120))))
            # (tap.blend, since build 264) THE TAP CHANCE FROM BOTH: how hurt the gripped part is and how hurt she is
            # overall. Fresh, she can fight even a ruined part off (a fair chance, not a sure one); worn down, she
            # gives in far more easily, and even a healthy part in the grip is harder to bear than when she was
            # fresh. Then THE BUILD-UP: the chance starts near nothing and climbs over the hold's first beats, so a
            # tap within two beats is rare and there is nearly always a visible struggle first
            bl = tcfg.get("blend") or {}
            blended, base = bool(bl.get("enabled", True)), 0.0
            why_low = []    # (since build 283) what is keeping this beat's chance down, for the tap meter
            if blended:
                pd = dmg[0] + float(tcfg.get("second_part", 0.4)) * sum(dmg[1:])
                P = max(0.0, min(1.0, pd / max(1.0, float(bl.get("part_full", 300))))) ** float(bl.get("part_power", 1.5))
                Hh = 1.0 - s_ / 100.0
                base = min(float(bl.get("max", 0.85)), float(bl.get("part", 0.3)) * P + float(bl.get("health", 0.08)) * Hh
                           + float(bl.get("both", 0.47)) * P * Hh)
                if surge > 1.0:
                    base *= float(bl.get("surge", 0.6))
                    why_low.append(("an adrenaline surge", float(bl.get("surge", 0.6))))
                ramp = min(1.0, max(0, beats - 1) / max(1.0, float(bl.get("ramp_beats", 8))))
                tap = base * ramp ** float(bl.get("ramp_power", 2))
                if ramp < 1.0:
                    why_low.append((f"beat {beats} of the hold, still building", ramp ** float(bl.get("ramp_power", 2))))
            st0 = self.zero_stage(d)
            if st0 and tap > 0 and not blended:
                # below_zero: the further below zero, the less of her is left to refuse with (stage tap_mult)
                tap = min(top, tap * float(st0.get("tap_mult", 1.0)))
            choke = any(re.search(r"(?i)neck|throat", h.part) for h in hs)
            name = next((h.sub for h in hs if h.sub), "") or ("choke" if choke else "hold")
            how, po, air, endure = None, 0.0, 0.0, 0.0
            if choke:
                # A CHOKE runs out her air and blood, not her will: it builds every beat it is on, and her strength
                # decides how long she stays conscious under it
                air = float(ccfg.get("air_per_beat", 22)) * beats
                endure = float(ccfg.get("endurance", 110)) * (s_ / 100.0) ** power * surge
                # (choke.endure_min, since build 265) even with nothing left she has some breath in her: without it a
                # fighter at zero health had no endurance at all, read "air 2200% gone" on the choke's first beat
                endure = max(endure, float(ccfg.get("endure_min", 30)))
                po = min(float(ccfg.get("max", 0.85)), max(0.0, (air - endure) / float(ccfg.get("span", 70))))
                if blended and bl.get("chokes", True):
                    # (blend.chokes: the dark builds up the same way, so she doesn't black out on its second beat)
                    po *= min(1.0, max(0, beats - 1) / max(1.0, float(bl.get("ramp_beats", 8)))) ** float(
                        bl.get("ramp_power", 2))
            # CONSTRICTION (finish.submission.constriction, since build 283): coils round her chest or middle press
            # so hard that blood can't get back to her heart: her blood pressure falls, her heart slows and stumbles,
            # and the blood to her head runs short. It is mostly the blood, not her breath (each breath out is
            # taken up by the coils, so her breaths grow shallow, but she goes under from the circulation long before
            # she would from the air). It builds like a choke's air, from the coils' count and how hard they
            # press, against her endurance (her strength, her energy left, a surge); past it she may black out,
            # and as the grey closes in panic may make her tap
            kcfg = cfg.get("constriction") or {}
            body_coils = [h for h in hs if h.coil and self.coil_scope(h.part) == "body"] if kcfg.get("enabled", True) \
                else []
            circ, circ_end, pc, constrict = 0.0, 0.0, 0.0, False
            if body_coils:
                tight = max(0.5, min(2.0, max(h.power for h in body_coils) / max(1.0, float(kcfg.get("power_ref", 16)))))
                # what sets it apart from a submission: it goes by the SQUEEZE (the coils, how hard, how big the
                # coiler is against her) and her breath and energy left to fight it, more than by her pain. Her
                # health and the coiled parts still count, only less than in a submission
                sa, sd = self.size_m(self.get(a)), self.size_m(d)
                big = max(float(kcfg.get("size_min", 0.75)), min(float(kcfg.get("size_max", 1.4)),
                          (sa / sd) ** float(kcfg.get("size_weight", 0.2)))) if sa and sd else 1.0
                hid = min(h.id for h in body_coils)
                circ = self._compress_tick(d, a, hid, body_coils, tight, big, kcfg, s_)
                comp = float((d.learned.get("compress") or {}).get("c", 0.0))
                ew = float(kcfg.get("energy_weight", 0.4))
                worst = max((d.parts[p].damage for p in (self.coil_ring_parts(d, body_coils) if self.compress_cfg()
                                                          else [h.part for h in body_coils]) if p in d.parts),
                            default=0.0)
                part_f = 1.0 - float(kcfg.get("part_weight", 0.25)) * min(1.0, worst / 300.0)
                circ_end = max(float(kcfg.get("endure_min", 30)), float(kcfg.get("endurance", 110))
                               * (s_ / 100.0) ** float(kcfg.get("health_power", 0.5)) * surge * part_f
                               * (1.0 - ew + ew * max(0.0, min(100.0, d.energy)) / 100.0))
                # (no tap.blend build-up on top: the gauge itself builds beat by beat, from nothing)
                pc = min(float(kcfg.get("max", 0.85)), max(0.0, (circ - circ_end) / float(kcfg.get("span", 70))))
                near_k = float(kcfg.get("near", 0.75))
                if circ >= near_k * circ_end and float(kcfg.get("grey_tap", 0.25)) > 0:
                    # the grey closing in: panic as much as pain may make her give in
                    tap = max(tap, float(kcfg.get("grey_tap", 0.25)) * min(1.0, (circ - near_k * circ_end)
                                                                         / max(1.0, circ_end * (1 - near_k)
                                                                               + float(kcfg.get("span", 70)))))
                if pc > po:
                    po, constrict = pc, True
                order = ("pounding", "slowing", "greying")
                frac = min(0.99, circ / max(1.0, circ_end + float(kcfg.get("span", 70))))
                # (the stages follow the same curve as the numbers: racing to vitals.peak_at, then slowing, and the
                # grey from stage_grey of the way)
                stage = ("pounding" if frac < float((kcfg.get("vitals") or {}).get("peak_at", 0.25)) + 0.05 else
                         "slowing" if frac < float(kcfg.get("stage_grey", 0.65)) else "greying")
                # (a heart that has begun to slow doesn't race again while the same coils stay on: the stage holds)
                pk = d.learned.get("circ_peak") or ["", 0, -1]
                if pk[0] == a and len(pk) > 2 and pk[2] == hid and order.index(stage) < int(pk[1]):
                    stage = order[int(pk[1])]
                d.learned["circ_peak"] = [a, order.index(stage), hid]
                vit = self.constriction_vitals(d, frac, stage)
                d.learned["circ_vitals"] = [self.turn, vit]      # (for the tap meter)
                vit["squeeze"] = round(comp)
                vit["where"] = (d.learned.get("compress") or {}).get("where", "")
                vit["coils"] = len(body_coils)
                vit["ring"] = bool((d.learned.get("compress") or {}).get("ring"))
                events.append(dict({"type": "constriction", "attacker": a, "defender": dn, "stage": stage,
                                    "pct": round(100 * frac), "coils": len(body_coils), "compress": round(comp),
                                    "where": (d.learned.get("compress") or {}).get("where", ""),
                                    "ring_parts": list((d.learned.get("compress") or {}).get("ring") or []),
                                    "struggled": bool((d.learned.get("compress") or {}).get("struggled")),
                                    "parts": [h.part for h in body_coils]}, **vit))
            # she holds on the first beat it goes past her limit, whatever it costs her: only after that can she
            # give in (d.learned keeps which grip she has already fought through once)
            # finish.submission.taps: a body part her taps have already used may no longer count toward the tally;
            # a grip on such a part (and nothing new besides) can't make her give in, so it doesn't roll
            # (for the window's pain gauge: the very numbers this check weighed, this beat)
            d.learned["sub_gauge"] = {"turn": self.turn, "pain": round(pain), "resist": round(resist),
                                      "air": round(max(air, circ)),
                                      "endure": round(circ_end if body_coils and circ >= air else endure),
                                      "circ": bool(body_coils) and circ >= air, "sub": name, "by": a,
                                      "base": round(base, 3) if blended else None}
            if first:
                if urge_first:
                    events += self._tap_urge(d, a, name, hs, pain, resist, beats, tcfg)
                # (since build 289 with its gauge: the constriction's blood flow and her heart show from the first beat)
                self._note_tap_state(d, a, name, events, 0.0, pain, resist, first=True,
                                     air=(circ, circ_end, "circ") if body_coils and circ >= air else
                                     (air, endure) if choke and air else None)
                continue
            ucfg = (self.rules.get("submissions") or {}).get("upright") or {}
            sub_ = next((h.sub for h in hs if h.sub), "")
            if tap > 0 and dn not in self.downed and not self.has(d, "airborne") \
                    and sub_ not in (ucfg.get("supporting") or ()):
                # (since build 249) still on her own feet, she has her legs to fight it with, and the hold is more
                # likely to bear her down first than to make her give in standing (upright.standing_tap_mult; a hold
                # that carries her weight, upright.supporting, isn't damped)
                tap *= float(ucfg.get("standing_tap_mult", 0.35))
                why_low.append(("still on her feet", float(ucfg.get("standing_tap_mult", 0.35))))
            key_ = f"{a}|{name}|{min(h.id for h in hs)}"
            # THE BREAKING POINT (tap.overwhelm, since build 254): a gripped part in horrible condition (devastated or
            # worse) with the pain past what she can bear is a tap that is coming. She holds out hold_out beats
            # first, fighting it with everything (no tap at all, so the pain, the struggle and the refusals get told),
            # and after that it is all but certain (chance). It keeps counting while the same fighter holds her.
            ocfg = tcfg.get("overwhelm") or {}
            breaking, stage_ = None, None
            if not blended and ocfg.get("enabled", True) and over > 0 and dmg[0] >= float(ocfg.get("part_damage", 300)):
                br = d.learned.get("breaking")
                if not br or br[0] != a or int(br[2]) < self.turn - 1 or len(br) < 4:
                    # how long she can hold out comes from her: the more of her strength is left (and an adrenaline
                    # surge), the longer, with a little luck in it (hold_min to hold_max beats)
                    lo, hi = int(ocfg.get("hold_min", 2)), int(ocfg.get("hold_max", 4))
                    will = min(1.0, (s_ / 100.0) * surge + (0.25 if s_ > 0 else 0.0))
                    n_ = lo + (hi - lo) * will + self.rng.uniform(-0.6, 0.6)
                    br = [a, self.turn, self.turn, max(lo, min(hi, int(round(n_))))]
                br[2] = self.turn
                d.learned["breaking"] = br
                held_ = self.turn - int(br[1])
                breaking = max(0, int(br[3]) - held_)     # beats she still holds out
                if breaking > 0:
                    # how far her resistance has broken down: the first beat of it, the last, or in between
                    stage_ = "first" if held_ == 0 else "last" if breaking == 1 else "cracking"
                    tap = 0.0
                    d.learned["tap_limit"] = key_      # (the beats she holds out are her beat of holding on)
                else:
                    tap = max(tap, float(ocfg.get("chance", 0.95)))
            else:
                d.learned.pop("breaking", None)
            tap_part = self._tap_part(d, sorted(hs, key=lambda h: -(d.parts[h.part].damage if h.part in d.parts
                                                                   else 0.0)))
            spent = tap_part is None
            if spent:
                tap = po = 0.0
            # (tap.spent_no_grace: with no health left there is nothing to hold on through: no grace beat)
            first_over = tap > 0 and not blended and d.learned.get("tap_limit") != key_ and not (
                d.health <= 0 and tcfg.get("spent_no_grace", True))
            if first_over:
                d.learned["tap_limit"] = key_
                tap = 0.0
            q = self.quirk(d, "stubborn")
            if tap > 0 and q:
                tap *= float(q.get("tap_mult", 0.6))     # (since build 280) she holds out longer than she should
                why_low.append(("stubborn", float(q.get("tap_mult", 0.6))))
                if tap >= 0.15:
                    self.quirk_moment(d, "stubborn", f"{d.name} is past her limit and should be giving in, and she "
                                                     f"won't: pure stubbornness, more than sense, keeps her from tapping")
            if tap > 0 and self._chance(tap, f"{dn} tapping out to {poss_word(a)} {name} (pain {pain:.0f} against "
                                        f"her resistance {resist:.0f})", "SHE TAPS", "she holds on"):
                how = "tap"
            elif po > 0 and self._chance(po, (f"{dn} blacking out in {poss_word(a)} coils (the constriction has built to "
                                              f"{circ:.0f} against her endurance {circ_end:.0f})") if constrict else
                                         (f"{dn} passing out in {poss_word(a)} choke (it has built to {air:.0f} "
                                          f"against her endurance {endure:.0f})"), "SHE PASSES OUT", "she stays awake"):
                how = "pass_out"
            if not how:
                near = float(tcfg.get("near", 0.75))
                if pain >= near * resist or (choke and air >= near * endure) or (body_coils and circ >= float(
                        kcfg.get("near", 0.75)) * circ_end) or (
                        blended and base >= float(bl.get("near", 0.2)) and beats >= 2):
                    # close to her limit: she is fighting the urge to give in (or the dark), and holding. How many
                    # times she has refused her (in this grip or an earlier one) lets the telling climb toward the tap
                    prev = d.learned.get("tap_refused") or ["", 0]
                    refusals = (prev[1] + 1) if prev[0] == a else 1
                    d.learned["tap_refused"] = [a, refusals]
                    ev_ = {"type": "tap_resist", "attacker": a, "defender": dn, "submission": name,
                           "parts": [h.part for h in hs], "choke": choke and air >= near * endure,
                           "constrict": bool(body_coils) and circ >= float(kcfg.get("near", 0.75)) * circ_end,
                           "over": over >= 0, "pain": round(pain), "resist": round(resist),
                           "beats_held": beats, "refusals": refusals, "spent": spent, "breaking": stage_ if breaking else None}
                    ev_.update(self._tap_tells(d, refusals, over, resist, ev_["choke"]))
                    events.append(ev_)
                else:
                    # (tap.urge, since build 256) nowhere near her limit, but it hurts: she is shown fighting the
                    # urge all the same, lighter (it doesn't count as a refusal)
                    events += self._tap_urge(d, a, name, hs, pain, resist, beats, tcfg)
                self._note_tap_state(d, a, name, events, tap, pain, resist, held_on=first_over, spent=spent, out=po,
                                     breaking=stage_ if breaking else None,
                                     air=(circ, circ_end, "circ") if body_coils and circ >= air else
                                     (air, endure) if choke else None,
                                     why_low=why_low if tap > 0 else ())
            if not how:
                continue
            if how == "pass_out":
                # (since build 266) she blacked out from the choke: the pass-out is the neck's, not the worst-hurt
                # part beside it (the build-264 log credited a tail strangle's pass-out to her upper back)
                spent_ = set(self.spent_tap_parts(d))
                tap_part = next((h.part for h in (body_coils if constrict else hs)
                                 if (constrict or re.search(r"(?i)neck|throat", h.part)) and h.part not in spent_),
                                tap_part)
                hs_cfg = kcfg.get("heart_stop") or {}
                if constrict and hs_cfg.get("enabled", True) and self._chance(
                        float(hs_cfg.get("chance", 0.35)), f"{poss_word(dn)} heart stopping as she goes under in the "
                        f"coils (it starts again once they come off)", "IT STOPS, for a moment", "it keeps beating"):
                    # (since build 293) her heart stops a moment as she goes under: never a death, it starts again
                    d.learned["heart_stopped"] = self.turn
                    d.learned["circ_vitals"] = [self.turn, {"heart": 0, "irregular": False, "stopped": True,
                                                            "bp": [30, 15]}]
                    ts_ = d.learned.get("tap_state")
                    if isinstance(ts_, dict) and ts_.get("turn") == self.turn:
                        ts_["vitals"] = d.learned["circ_vitals"][1]
            parts = [h.part for h in hs]
            with_ = list(dict.fromkeys(h.with_part for h in hs if h.with_part))
            taps_ = self._taps_rule()
            if taps_ and (how == "tap" or taps_.get("pass_out_counts", True)):
                given = list(d.learned.get("taps_given") or []) + [tap_part]
                d.learned["taps_given"] = given
                need = self.taps_needed()
                if len(given) < need:
                    # NOT YET THE END: she tapped (or blacked out), so the grip comes off and the match goes on;
                    # her limit and her refusals start again for the next hold
                    d.learned.pop("tap_limit", None)
                    d.learned.pop("tap_refused", None)
                    d.learned.pop("tap_target", None)       # (the signs she showed are kept: none again so soon)
                    if d.learned.get("tap_next"):
                        d.learned["tap_target"] = d.learned.pop("tap_next")   # (the part already softened)
                    rsp = taps_.get("respite") or {}
                    if rsp.get("enabled", True) and int(rsp.get("beats", 1)) > 0:
                        # taps.respite: the holder lets go and steps back; next beat nobody strikes or grips her, so
                        # she gets a clear try at getting up before the next hold
                        d.learned["tap_respite"] = [a, self.turn + int(rsp.get("beats", 1))]
                    ev = {"type": "tap_count", "how": how, "attacker": a, "defender": dn, "submission": name,
                          "parts": parts, "with": with_, "part": tap_part, "tap_no": len(given), "needed": need,
                          "beats_held": beats, "chance": round(tap if how == "tap" else po, 3),
                          "pain": round(pain), "resist": round(resist), "air": round(air), "endure": round(endure),
                          "spent_parts": self.spent_tap_parts(d),
                          "cause": "constriction" if how == "pass_out" and constrict else "",
                  "heart_stopped": d.learned.get("heart_stopped") == self.turn,
                  "circ": round(circ), "circ_end": round(circ_end)}
                    if how == "tap" and self._tap_vary_on():
                        ev["way"] = self.vary("tap_way_trapped" if self.arms_trapped(d) else "tap_way")
                    events.append(ev)
                    try:
                        events.append(self.release_between(a, dn, "let go after she tapped"))
                    except ValueError as exc:
                        self.note_failure("tap_count release", exc)
                    continue
            reason = (f"taps out to {poss_word(a)} {name}" if how == "tap" else
                      f"passes out in {poss_word(a)} {name}")
            ev = {"type": "tap_out", "how": how, "attacker": a, "defender": dn, "submission": name, "parts": parts,
                  "part": tap_part,
                  "with": with_, "beats_held": beats, "chance": round(tap if how == "tap" else po, 3),
                  "tap_no": len(d.learned.get("taps_given") or []) or 1,
                  "pain": round(pain), "resist": round(resist), "air": round(air), "endure": round(endure),
                  "cause": "constriction" if how == "pass_out" and constrict else "",
                  "heart_stopped": d.learned.get("heart_stopped") == self.turn,
                  "circ": round(circ), "circ_end": round(circ_end)}
            if how == "tap" and self._tap_vary_on():
                ev["way"] = self.vary("tap_way_trapped" if self.arms_trapped(d) else "tap_way")
            ev["elimination"] = self.eliminate(dn, reason)
            if how == "tap" and cfg.get("tap_awake", True):
                # she gave up: she is awake, beaten and hurting, not knocked out (the recovery stage before "up")
                stages = self.rules.get("recovery", {}).get("stages") or self.RECOVERY_DEFAULT
                d.recovery = max(0, len(stages) - 2)
            events.append(ev)
        return events

    def _taps_rule(self):
        """finish.submission.taps (when on): how many tap-outs end the match, and how many of them must come from a
        body part no earlier tap used. None when off (the first tap-out ends it)."""
        t = (((self.rules.get("finish") or {}).get("submission") or {}).get("taps") or {})
        return t if t.get("enabled", False) else None

    def taps_needed(self):
        t = self._taps_rule()
        return max(1, int(t.get("needed", 1))) if t else 1

    def taps_distinct_needed(self, who=None):
        """How many different body parts her taps must come from: different_parts (a percentage) of the taps
        needed, rounded up, and never fewer than one. With 3 taps: up to 33% = any parts, 34-66% = at least two
        different parts, 67-100% = all three different. (since build 277) A serpent (`who`), with no limbs to put
        in a hold, goes by serpent_different_parts when that is lower."""
        t = self._taps_rule()
        if not t:
            return 1
        pct = max(0.0, min(100.0, float(t.get("different_parts", 0))))
        f = (self.get(who) if isinstance(who, str) else who) if who is not None else None
        if f is not None and t.get("serpent_different_parts") is not None and self.body_plan(f) == "serpent":
            pct = min(pct, max(0.0, float(t.get("serpent_different_parts"))))
        return max(1, min(self.taps_needed(), math.ceil(pct / 100.0 * self.taps_needed() - 1e-9)))

    def tap_respite(self, who):
        """finish.submission.taps.respite: the fighter who just gave a tap that wasn't the last is left alone this
        beat (no blow, no grip on her) so she can get up: the name of the one who let her go, or None."""
        f = self.get(who) if isinstance(who, str) else who
        r = (f.learned.get("tap_respite") if f else None) or None
        if not r or self.winner():
            return None
        if self.turn >= int(r[1]):
            f.learned.pop("tap_respite", None)
            return None
        return r[0]

    def pain_gauge(self, f):
        """window.pain_gauge (since build 249): two gauges for the window, each a share of how much she can bear (her
        resistance: finish.submission.tap.resist, scaled by her strength; an adrenaline surge raises it). Nothing
        reads them to decide anything.
        - overall: the pain she feels right now: the sting of each blow, fading every beat (_pain_tick: decay), over
          a low floor her injuries keep up (chronic x her worst part and second_part of the next two).
        - part: the part being held, pinned or struck this beat. Held in a submission (the tap check weighed it this
          beat) it is that check's own pain, from the gripped parts only, and a choke's air hunger beside it; held
          otherwise, the gripped part's damage and the grip pressing on it; struck, the struck part's damage and the
          sting of the blow. None when nothing is on or at any part of her this beat.
        Returns {"overall": {...}, "part": {...} or None}, or None when it is off."""
        cfg = ((self.rules.get("window") or {}).get("pain_gauge") or {})
        if not cfg.get("enabled", True) or f.eliminated:
            return None
        tcfg = (((self.rules.get("finish") or {}).get("submission") or {}).get("tap") or {})
        cuts = cfg.get("labels") or [[40, "bearable"], [70, "hurting badly"], [100, "near her limit"],
                                     [9e9, "past what she can bear"]]
        s_ = max(0.0, min(100.0, self._health_pct(f)))
        surge = float(tcfg.get("surge_resist", 1.5)) if self.has(f, "adrenaline") else 1.0
        bear = max(10.0, float(tcfg.get("resist", 130)) * (s_ / 100.0) ** float(tcfg.get("resist_power", 0.8)) * surge)

        top = float(cfg.get("show_max", 300) or 0)

        def gauge(pain, bear_, **more):
            share = pain / max(1.0, bear_) * 100.0
            label = next((str(w) for c, w in cuts if share < float(c)), str(cuts[-1][1]))
            # (show_max: worn to nothing, what she can bear sinks to its floor and the share runs into the thousands;
            # past show_max it is shown as "300%+", far past what she can bear)
            over = bool(top) and share > top
            return dict({"pct": round(min(share, top) if over else share), "pain": round(pain), "bear": round(bear_),
                         "label": ("far " + label if over and label.startswith("past") else label),
                         "shown": f"{top:.0f}%+" if over else f"{share:.0f}%"}, **more)

        held = [h for h in self.holds.values() if h.defender == f.name]
        pin_ = self.pinned_by(f.name)
        sec = float(cfg.get("second_part", 0.4))
        dmg = sorted((p.damage for p in f.parts.values()), reverse=True) + [0.0, 0.0, 0.0]
        chronic = float(cfg.get("chronic", 0.15)) * (dmg[0] + sec * (dmg[1] + dmg[2]))
        felt = float(f.learned.get("pain_felt", 0.0))
        where = (f"pinned under {' and '.join(pin_)}" if pin_ else
                 f"in {poss_word(held[0].attacker)} {held[0].sub or 'grip'}" if held else "")
        overall = gauge(chronic + felt, bear, where=where, fresh=round(felt))
        part = None
        sg = f.learned.get("sub_gauge") or {}
        sp = f.learned.get("sting_parts") or [None, {}]
        if sg and int(sg.get("turn", -9)) == self.turn and held:
            names = list(dict.fromkeys(h.part for h in held))
            part = gauge(float(sg["pain"]), float(sg["resist"]), parts=names[:3],
                         why=f"{poss_word(sg.get('by', ''))} {sg.get('sub') or 'hold'}",
                         air=(min(99, round(float(sg["air"]) / max(1.0, float(sg["endure"]) + float(
                             (((self.rules.get("finish") or {}).get("submission") or {}).get("choke") or {}).get(
                                 "span", 70))) * 100.0)) if sg.get("air") else None))
            if part is not None and sg.get("circ"):
                part["circ"] = True       # (since build 287) the gauge is the constriction's blood flow, not air
        elif held:
            worst = max(held, key=lambda h: f.parts[h.part].damage if h.part in f.parts else 0.0)
            pain = (f.parts[worst.part].damage if worst.part in f.parts else 0.0) \
                + float(tcfg.get("press", 1.5)) * max(h.power for h in held)
            part = gauge(pain, bear, parts=list(dict.fromkeys(h.part for h in held))[:3],
                         why=("pinned" if pin_ else f"{poss_word(worst.attacker)} {worst.sub or 'grip'}"), air=None)
        elif sp[0] == self.turn and sp[1]:
            name = max(sp[1], key=lambda n: (f.parts[n].damage if n in f.parts else 0.0) + sp[1][n])
            pain = (f.parts[name].damage if name in f.parts else 0.0) + float(sp[1][name])
            part = gauge(pain, bear, parts=[name], why=f"struck (+{float(sp[1][name]):.0f})", air=None)
        return {"overall": overall, "part": part}

    def taps_given(self, who):
        f = self.get(who) if isinstance(who, str) else who
        return list(f.learned.get("taps_given") or []) if f else []

    def spent_tap_parts(self, who):
        """The body parts a tap on would no longer count for her: the parts her earlier taps used, once only as
        many repeats are left as the different-parts rule allows."""
        given = self.taps_given(who)
        if not self._taps_rule() or not given:
            return []
        repeats_left = (self.taps_needed() - self.taps_distinct_needed(who)) - (len(given) - len(set(given)))
        return [] if repeats_left > 0 else list(dict.fromkeys(given))

    def tap_steer(self, kind):
        """finish.submission.taps.steer: how hard the fight is pushed toward a body part that still counts for a
        tap (kind "strikes" or "holds": the chance a blow or a hold is moved onto it). 0 when off."""
        t = self._taps_rule()
        st = (t or {}).get("steer") or {}
        if not t or not st.get("enabled", True):
            return 0.0
        return max(0.0, min(1.0, float(st.get(kind, {"strikes": 0.6, "holds": 0.9}.get(kind, 0.0)))))

    # where a hold can make her tap: a limb, the shoulders, the back, the body, the tail (not her head; her neck
    # only as a choke, and chokes are the rare finish)
    TAP_TARGET_REGIONS = ("fore_up", "fore_low", "hind_up", "hind_low", "shoulder", "back_up", "back_low", "belly",
                          "chest", "tail")

    def tap_target(self, who):
        """finish.submission.taps.steer: the body part of hers the fight is working toward the next tap on. It
        sticks from beat to beat (so the damage builds on one part), and is chosen again when it stops counting:
        the worst-hurt part that still counts, a limb before the body. None when the steer is off."""
        d = self.get(who) if isinstance(who, str) else who
        if not d or not (self.tap_steer("strikes") or self.tap_steer("holds")):
            return None
        spent = set(self.spent_tap_parts(d))
        cur = d.learned.get("tap_target")
        if cur in d.parts and cur not in spent:
            return cur
        pick = self._tap_candidate(d, spent)
        if pick:
            d.learned["tap_target"] = pick
        return pick

    def _tap_candidate(self, d, skip):
        """The worst-hurt part (a limb first) not in skip that a hold could make her tap on, or None."""
        cands = [p for p in d.parts.values() if p.name not in skip and "base" not in p.name.lower()
                 and body_region(p.name) in self.TAP_TARGET_REGIONS]
        if not cands:
            return None
        limb = ("fore_up", "fore_low", "hind_up", "hind_low", "tail")
        return max(cands, key=lambda p: (p.damage + (25 if body_region(p.name) in limb else 0), self.rng.random())).name

    def tap_ready(self, who):
        """finish.submission.taps.steer.ready: True once her target part is hurt past ready (%): more blows there
        are wasted on it, so they go to the next part (tap_next) while the holds still go to the target."""
        d = self.get(who) if isinstance(who, str) else who
        aim = self.tap_target(d) if d else None
        st = (self._taps_rule() or {}).get("steer") or {}
        ready = float(st.get("ready", 150) or 0)
        return bool(aim) and ready > 0 and d.parts[aim].damage >= ready and self.taps_needed() > len(self.taps_given(d)) + 1

    def tap_next(self, who):
        """The part to soften with blows after the target (the next tap's), chosen afresh and not kept: None when
        there is no other part that still counts."""
        d = self.get(who) if isinstance(who, str) else who
        aim = self.tap_target(d) if d else None
        if not aim:
            return None
        skip = set(self.spent_tap_parts(d)) | {aim}
        if self.taps_distinct_needed(d) > 1:
            skip |= set(self.taps_given(d))      # (the next tap should be somewhere new where it can be)
        cur = d.learned.get("tap_next")
        if cur in d.parts and cur not in skip:
            return cur                           # (it sticks too, so the softening builds on one part)
        pick = self._tap_candidate(d, skip) or self._tap_candidate(d, set(self.spent_tap_parts(d)) | {aim})
        if pick:
            d.learned["tap_next"] = pick
        return pick

    def _tap_part(self, d, hs):
        """The body part a tap in these holds (worst-hurt first) would count for: the first one that still counts,
        or None when every gripped part is spent. With the taps rule off, simply the worst-hurt part."""
        spent = set(self.spent_tap_parts(d))
        return next((h.part for h in hs if h.part not in spent), None)

    def _tap_vary_on(self):
        return bool(((self.rules.get("narration") or {}).get("tap_build") or {}).get("vary", True))

    def _note_tap_state(self, d, a, name, events, chance, pain, resist, first=False, held_on=False, spent=False,
                        breaking=None, air=None, why_low=(), out=0.0):
        """For the window (window.hold_panel): how near she is to tapping, as the tap check left it this beat. level
        is the narrator's ladder (1-5: tap.urge's lighter signs, then the refusals near and past her limit), chance
        the tap chance this beat's roll was made at (0 on a beat she can't tap: her first beat in it, the first
        beat past her limit she holds on through, or holding out at her breaking point)."""
        ev = next((e for e in reversed(events) if e.get("defender") == d.name and e.get("attacker") == a
                   and e.get("type") in ("tap_resist", "tap_urge")), None) or {}
        if ev.get("type") == "tap_urge":
            level = int(ev.get("level") or 1)
        elif ev.get("type") == "tap_resist":
            level = 5 if breaking in ("cracking", "last") else min(5, 2 + int(ev.get("stage")
                                                                            or min(3, int(ev.get("refusals") or 1))))
        else:
            level = 0
        d.learned["tap_state"] = {"turn": self.turn, "by": a, "sub": name,
                                  # (since build 283) the chance it ENDS this beat: a tap, or blacking out (out)
                                  "chance": round(1.0 - (1.0 - float(chance)) * (1.0 - float(out or 0)), 4),
                                  "tap_only": round(float(chance), 4), "out": round(float(out or 0), 4),
                                  "pain": round(pain), "resist": round(resist), "level": level,
                                  "refusals": int((d.learned.get("tap_refused") or ["", 0])[1])
                                  if (d.learned.get("tap_refused") or [""])[0] == a else 0,
                                  "first": first, "held_on": bool(held_on), "spent": bool(spent),
                                  # (since build 283) what keeps the chance down: [(why, multiplier)]
                                  "why_low": [[w, round(float(m_), 3)] for w, m_ in why_low],
                                  "breaking": breaking, "choke": bool(ev.get("choke")),
                                  "air": min(99, round(air[0] / max(1.0, air[1] + float(
                                      (((self.rules.get("finish") or {}).get("submission") or {}).get(
                                          "constriction" if len(air) > 2 else "choke") or {})
                                      .get("span", 70))) * 100)) if air and air[0] else None,
                                  # (since build 283) the gauge is a constriction's blood flow, not a choke's air
                                  "circ": bool(air and len(air) > 2),
                                  "vitals": ((d.learned.get("circ_vitals") or [None, None])[1]
                                             if (d.learned.get("circ_vitals") or [None])[0] == self.turn else None),
                                  # (since build 265) the chance it is building toward (tap.blend), for the meter
                                  "toward": (sg_.get("base") if (sg_ := d.learned.get("sub_gauge") or {}).get("turn")
                                             == self.turn and sg_.get("by") == a else None)}

    def card_state(self, f):
        """window.hold_panel (since build 257): what is going on around her for the window and exported fights,
        as plain data: the grips on her (who, what hold, which of her parts, with what, how many beats), the grips
        she has on others, a pin on her or by her (its count against its length), how near she is to tapping (from
        the tap check this beat: _note_tap_state) and how far she is from each other fighter. None when it is off."""
        cfg = ((self.rules.get("window") or {}).get("hold_panel") or {})
        if not cfg.get("enabled", True):
            return None
        if f.eliminated:
            # (since build 293) the beat she blacked out in the coils: the card still shows her heart (stopped, or
            # slow), and the meter says how it ended
            ts, cv = f.learned.get("tap_state") or {}, f.learned.get("circ_vitals") or [None, None]
            if cv[0] == self.turn and cv[1] and ts:
                return {"held": [], "holding": [], "pin": None, "pinning": [], "gaps": [],
                        "tap": dict(ts, circ=True, vitals=cv[1], done="blacked out in the coils")}
            return None

        def kind(h):
            return h.sub or ("coils" if h.coil else "grab" if h.grab else "hold")

        def grips(hs, who_key, who):
            out = {}
            for h in sorted(hs, key=lambda h: h.id):
                g = out.setdefault((getattr(h, who), kind(h)), {
                    who_key: getattr(h, who), "what": kind(h), "parts": [], "with": [], "beats": 0,
                    "choke": False, "locked": False})
                g["parts"].append(h.part)
                if h.with_part and h.with_part not in g["with"]:
                    g["with"].append(h.with_part)
                g["beats"] = max(g["beats"], int(h.turns_active))
                g["choke"] = g["choke"] or bool(re.search(r"(?i)neck|throat", h.part))
                g["locked"] = g["locked"] or bool(h.locked)
            return list(out.values())

        on_her = [h for h in self.holds.values() if h.defender == f.name]
        held = grips(on_her, "by", "attacker")
        holding = grips([h for h in self.holds.values() if h.attacker == f.name], "on", "defender")
        pin = None
        p_ = self.pinned_by(f.name)
        if p_:
            pr = next((p for p in self.pins.values() if p["defender"] == f.name), {})
            pin = {"by": p_, "seconds": round(float(pr.get("seconds", 0))), "of": round(float(pr.get("duration", 60)))}
        pinning = []
        for p in self.pins.values():
            if f.name in self.pin_members(p):
                pinning.append({"on": p["defender"], "seconds": round(float(p.get("seconds", 0))),
                                "of": round(float(p.get("duration", 60)))})
        ts = f.learned.get("tap_state") or {}
        tap = dict(ts) if (self.submission_match() and ts and int(ts.get("turn", -9)) == self.turn
                           and any(h.attacker == ts.get("by") for h in on_her)) else None
        # (since build 283) what the meter's steps follow: this beat's real chance (meter_by "chance") or how the
        # pain feels against what she can bear (the narrator's ladder: "pain")
        mby = str(cfg.get("meter_by", "chance")).lower()
        steps = [float(x) for x in (cfg.get("chance_steps") or (3, 10, 25, 50))][:4]
        if tap is not None:
            tap["meter_by"], tap["chance_steps"] = mby, steps
        gcfg = ((((self.rules.get("finish") or {}).get("submission") or {}).get("tap") or {}).get("grabs") or {})
        if self.submission_match() and gcfg.get("enabled", True) and f.health > 0:
            for g in held:
                # (since build 274) a grab only counts toward a tap once the part it holds is hurt past
                # tap.grabs.min_damage: the panel says how far off that is, so a grab with no tap meter isn't a puzzle
                if g["what"] == "grab":
                    low = [(p, f.parts[p].damage) for p in g["parts"] if p in f.parts
                           and f.parts[p].damage < float(gcfg.get("min_damage", 100))]
                    if low and len(low) == len(g["parts"]):
                        g["tap_from"] = [round(float(gcfg.get("min_damage", 100))), round(max(x[1] for x in low))]
        if self.submission_match():
            for g in holding:
                # (on the holder's card too: how near the one she holds is to tapping)
                o = self.fighters.get(str(g["on"]).lower())
                ot = (o.learned.get("tap_state") or {}) if o else {}
                if ot and int(ot.get("turn", -9)) == self.turn and ot.get("by") == f.name:
                    g["tap"] = [int(ot.get("level") or 0), round(100 * float(ot.get("chance") or 0), 1), mby, steps]
        gaps = []
        if cfg.get("distance", True) and self._gap_on():
            for o in self.active():
                if o.name != f.name:
                    gaps.append([o.name, self.GAP_SHORT.get(self.gap_of(f.name, o.name), "")])
        return {"held": held, "holding": holding, "pin": pin, "pinning": pinning, "tap": tap, "gaps": gaps}

    # the signs of fighting the tap that need a free paw (narrator.TAP_TELLS, TAP_URGE)
    PAW_TELLS = ("fist", "claws", "reach", "yank", "fist_shake", "yank_back", "shake_hard", "twitch", "curl", "touch",
                 "hover", "pin_paw", "grab_ground", "flat", "hangs")

    def compress_cfg(self):
        """finish.submission.constriction.compression (since build 294), or None when it is off."""
        c = ((((self.rules.get("finish") or {}).get("submission") or {}).get("constriction") or {})
             .get("compression"))
        return c if isinstance(c, dict) and c.get("enabled", True) else None

    def compression_on(self, d, holder=None):
        """How far coils round her body have squeezed her in right now (0-100), or 0."""
        cp = d.learned.get("compress") or {}
        if not cp or (holder and cp.get("by") != holder):
            return 0.0
        if not any(h.coil and h.id == cp.get("hid") for h in self.holds.values()):
            return 0.0
        return float(cp.get("c", 0.0))

    def coil_ring(self, d, part):
        """(since build 296, constriction.compression.ring) A coil round her body goes all the way round her, so it lies
        on every part of that band, not just the one it was aimed at: round her chest, her chest (and ruff), her ribs on
        both sides and her upper back; round her middle, her belly, both flanks and her lower back (her one back, when
        she has no lower back of her own). Returns ("chest" or "belly", [her parts in it])."""
        band = "belly" if body_region(part) in ("belly", "back_low") else "chest"
        want = ("chest", "back_up") if band == "chest" else ("belly", "back_low")
        ring = [p for p in d.parts if body_region(p) in want]
        if band == "belly" and not any(body_region(p) == "back_low" for p in d.parts):
            ring += [p for p in d.parts if body_region(p) == "back_up"]
        return band, ring or [part]

    def coil_ring_parts(self, d, coils):
        """Every part the body coils on her touch (coil_ring), or just the parts they were put on when ring is off."""
        if not (self.compress_cfg() or {}).get("ring", True):
            return [h.part for h in coils]
        return list(dict.fromkeys(p for h in coils for p in self.coil_ring(d, h.part)[1]))

    def _compress_tick(self, d, a, hid, coils, tight, big, kcfg, s_):
        """finish.submission.constriction.compression (since build 294): how far the coils have squeezed her chest
        and middle in, kept from beat to beat while the same coils hold, and the constriction gauge it builds.
        Each beat the coils gain on her: gain x how hard they press (tight) x how much bigger the coiler is (big) x
        each coil past the first; less, the sturdier the parts they are on (her resistance there) and the more strength
        she has to brace with. Each breath out the coils take up the room she gave up (ratchet), and struggling spends
        breath faster (struggle_ratchet), so fighting it tightens it. The gauge then builds by per_beat x how far she
        is squeezed in (nothing much under floor %, full at floor + span %, more past it). Returns the gauge.
        Off: the gauge builds as before, per_beat x the beats held x tight x big x the coils."""
        cc = self.compress_cfg()
        n = len(coils)
        per = float(kcfg.get("per_beat", 4)) * (1.0 + float(kcfg.get("extra_coil", 0.35)) * (n - 1))
        if not cc:
            return per * tight * big * max(h.turns_active for h in coils)
        cp = d.learned.get("compress") or {}
        if cp.get("by") != a or cp.get("hid") != hid:
            cp = {"by": a, "hid": hid, "c": 0.0, "circ": 0.0, "turn": -1}
        if cp.get("turn") == self.turn:
            return float(cp.get("circ", 0.0))        # (once a beat, however many tap checks look at it)
        # (ring: she braces with the whole band the coils go round, front, sides and back, not one part)
        ring = self.coil_ring_parts(d, coils)
        res = [d.parts[p].resistance for p in ring if p in d.parts] or [100.0]
        brace = (float(cc.get("brace_base", 0.6)) + float(cc.get("brace_res", 0.4)) * (sum(res) / len(res)) / 100.0) \
            * (float(cc.get("brace_base", 0.6)) + (1.0 - float(cc.get("brace_base", 0.6))) * max(0.0, s_) / 100.0)
        gain = float(cc.get("gain", 10)) * tight * big * (1.0 + float(kcfg.get("extra_coil", 0.35)) * (n - 1)) \
            / max(0.3, brace)
        pas = getattr(self, "_passive", None)
        struggled = not (pas and pas[0] == self.turn and d.name in pas[1]) and not self.has(d, "stunned") \
            and d.energy > 5
        gain += float(cc.get("ratchet", 3)) + (float(cc.get("struggle_ratchet", 3)) if struggled else 0.0)
        cp["c"] = min(float(cc.get("max", 92)), float(cp.get("c", 0.0)) + gain)
        floor, span = float(cc.get("floor", 15)), float(cc.get("span", 50))
        f = max(0.0, min(float(cc.get("over", 1.6)), (cp["c"] - floor) / max(1.0, span)))
        # where it squeezes: round her chest it bears straight on her heart and lungs; round her belly it drives her
        # gut up under her ribs (the breath pushed out from below, less on the heart); both, or her back
        if cc.get("ring", True):
            # (ring) each coil goes all the way round her, so a coil on her back or flank is round her chest or her
            # middle like any other
            bands = {self.coil_ring(d, h.part)[0] for h in coils}
            cp["where"] = "both" if len(bands) > 1 else bands.pop()
            cp["ring"] = ring
        else:
            regs = {body_region(h.part) for h in coils}
            chest = "chest" in regs or any(re.search(r"ribs", h.part, re.I) for h in coils)
            belly = "belly" in regs
            cp["where"] = "both" if chest and belly else "chest" if chest else "belly" if belly else "back"
            cp.pop("ring", None)
        wm = cc.get("where_mult") or {}
        cp["circ"] = float(cp.get("circ", 0.0)) + float(cc.get("per_beat", 9)) * f * float(
            wm.get(cp["where"], {"chest": 1.1, "belly": 0.9, "both": 1.05, "back": 0.95}[cp["where"]]))
        cp["turn"], cp["struggled"] = self.turn, struggled
        d.learned["compress"] = cp
        return cp["circ"]

    def constriction_vitals(self, d, frac, stage):
        """finish.submission.constriction.vitals (since build 283): rough numbers for the screen while coils hold back
        her blood: {"heart": beats a minute, "irregular", "bp": [systolic, diastolic]}, or {} when off. As in
        constricted prey: at first fear and effort drive her heart and her blood pressure UP; then, with blood unable
        to get back to her heart, her blood pressure falls and her heart SLOWS, beats skipping as it goes. Her
        resting rate is fighters.json heart_rest (else vitals.heart_rest); the rest of the curve is vitals'.
        Approximate by design: they are the story's numbers, never rolled against."""
        v = (((self.rules.get("finish") or {}).get("submission") or {}).get("constriction") or {}).get("vitals") or {}
        if not v.get("enabled", True):
            return {}
        rest = float(getattr(d, "heart_rest", 0) or v.get("heart_rest", 100))
        peak_at, peak, low = float(v.get("peak_at", 0.25)), float(v.get("peak_mult", 1.6)), float(v.get("low_mult", 0.45))
        if frac <= peak_at:
            hr = rest * (1.25 + (peak - 1.25) * frac / max(0.01, peak_at))
        else:
            hr = rest * (peak + (low - peak) * (frac - peak_at) / max(0.01, 1.0 - peak_at))
        sys0, dia0 = (float(x) for x in (v.get("bp_rest") or (120, 80)))
        rise = float(v.get("bp_rise", 1.15))
        if frac <= peak_at:
            m = 1.0 + (rise - 1.0) * frac / max(0.01, peak_at)
        else:
            m = rise + (float(v.get("bp_low", 0.45)) - rise) * (frac - peak_at) / max(0.01, 1.0 - peak_at)
        return {"heart": int(round(hr / 5.0) * 5), "irregular": stage != "pounding",
                "bp": [int(round(sys0 * m / 5.0) * 5), int(round(dia0 * m / 5.0) * 5)]}

    def arms_trapped(self, d):
        """(since build 275) coils wound round her body, her arms pinned inside them: no paw is free to tap."""
        return self.has(d, "constricted") and any(h.coil and h.defender == d.name and self.coil_scope(h.part) == "body"
                                                  for h in self.holds.values())

    def _tell(self, key, d, used):
        """One sign of fighting the tap from the set `key`, not one she showed lately, and none that needs a free paw
        while her arms are trapped in coils."""
        skip = list(used)
        if self.arms_trapped(d):
            table = dict(self.VARIETY.get(key, {}))
            free = [k for k in table if k not in self.PAW_TELLS]
            skip += [k for k in table if k in self.PAW_TELLS]
            if not [k for k in free if k not in used]:
                skip = [k for k in table if k in self.PAW_TELLS]
        return self.vary(key, skip=skip)

    def _tap_urge(self, d, a, name, hs, pain, resist, beats, tcfg):
        """finish.submission.tap.urge: a hold that hurts but is nowhere near her limit (below tap.near) still shows
        her fighting the urge to tap: in a SUBMISSION every beat it is on, from the first (urge.submissions); in any
        other hold that hurts, from urge.from of her resistance, urge.chance of the beats. Level 1 (under half her
        resistance): felt and held easily; level 2: it is getting to her. A list with the tap_urge event, or empty."""
        ucfg = tcfg.get("urge") or {}
        if not ucfg.get("enabled", True):
            return []
        sub = any(h.sub for h in hs) and ucfg.get("submissions", True)
        if not sub and (beats < 2 or pain < float(ucfg.get("from", 0.3)) * resist or not self._chance(
                float(ucfg.get("chance", 0.5)), f"{d.name} showing the urge to tap (pain {pain:.0f} against her "
                                                f"resistance {resist:.0f})", "a sign of it", "nothing shows")):
            return []
        level = 1 if pain < 0.5 * resist else 2
        ev = {"type": "tap_urge", "attacker": a, "defender": d.name, "submission": name,
              "parts": [h.part for h in hs], "pain": round(pain), "resist": round(resist), "beats_held": beats,
              "level": level}
        if self._tap_vary_on():
            used = list(d.learned.get("tap_ways") or [])
            ev["tell"] = self._tell("tap_tell_urge" if level == 1 else "tap_tell_urge2", d, used)
            ev["arms_trapped"] = self.arms_trapped(d)
            d.learned["tap_ways"] = (used + [ev["tell"]])[-15:]
        return [ev]

    def _tap_tells(self, d, refusals, over, resist, choke):
        """narration.tap_build.vary: HOW she is shown fighting the urge to tap this beat, picked from the variety
        sets (never the sign she showed last time). How near she is goes mostly by how often she has refused, but
        pain far past what she can bear pushes it a step nearer, and now and then she finds a little more in herself
        and it comes a step back. Past her limit, a reason she is still holding on; and what the holder feels."""
        if not self._tap_vary_on():
            return {}
        used = list(d.learned.get("tap_ways") or [])
        out = {}
        if choke:
            out["dark"] = self.vary("tap_dark", skip=used)
            pick = [out["dark"]]
        else:
            stage = min(3, refusals)
            if over >= 0.25 * resist:
                stage = min(3, stage + 1)
            elif stage > 1 and self.rng.random() < 0.2:
                stage -= 1
            out["stage"] = stage
            out["tell"] = self._tell(("tap_tell_first", "tap_tell_closer", "tap_tell_edge")[stage - 1], d, used)
            out["arms_trapped"] = self.arms_trapped(d)
            pick = [out["tell"]]
            if over >= 0:
                # the longer she refuses, the less of a reason she has left: stubbornness and a plea climb
                late = {"stubborn": 1.0 + refusals, "plea": 1.0 + refusals} if refusals >= 3 else None
                early = ("stubborn", "plea") if refusals < 2 else ()
                out["reason"] = self.vary("tap_reason", skip=list(used) + list(early), scale=late)
                out["holder"] = self.vary("tap_holder", skip=used)
                pick += [out["reason"], out["holder"]]
        d.learned["tap_ways"] = (used + pick)[-15:]     # (most of each set: no sign shown again for a while)
        return out

    def ko_only(self):
        """finish.knockout_only: a fight ends only when someone is KNOCKED OUT by a blow. A pin run to its end can't
        finish her (she kicks out at the last second, spent), and knockouts come more often the lower she is."""
        return bool((self.rules.get("finish") or {}).get("knockout_only", False))

    def _ko_only_chance(self, d, loss, devastating):
        """The knockout chance in knockout-only fights: nothing above finish.start_pct of her full health, rising
        to finish.chance (for a decent blow: decent_loss_pct of her health at once) at full_pct and below; a bigger
        blow more, a glancing one less; further below zero a little more still."""
        cfg = (self.rules.get("finish") or {})
        pct = self._health_pct(d)
        start, full = float(cfg.get("start_pct", 40)), float(cfg.get("full_pct", 10))
        if pct > start or loss <= 0:
            return 0.0
        low = 1.0 if pct <= full else (start - pct) / max(1e-9, start - full)
        low = low ** 1.5                 # creeps in slowly at first, then quickly near the bottom
        blow = max(0.15, min(1.6, loss / max(0.1, float(cfg.get("decent_loss_pct", 4)))))
        deep = 1.0 + float(cfg.get("below_zero_per_50", 0.15)) * max(0.0, -pct) / 50.0
        ch = float(cfg.get("chance", 0.30)) * low * blow * deep
        if devastating:
            ch *= float(cfg.get("devastating_mult", 1.5))
        if self.has(d, "adrenaline"):
            ch *= 0.5
        return min(float(cfg.get("max", 0.6)), ch)

    KO_STYLES = ("instant", "scream", "crumple", "fade")

    def knockout_style(self, d, loss, kinds, devastating):
        """How she goes out (the dice pick, weighted by what happened; rules finish.styles): "instant" (lights out on
        the impact, before or as she lands: more likely from a slam into the scenery, a charge, a spike or a
        devastating blow), "scream" (a raw cry from the blow, cut off as she goes: a big blow), "crumple" (her knees
        fold, she tries once to stay up, then sags out: still on her feet but barely), "fade" (going under slowly,
        from inside: a lighter last blow, or already down or held)."""
        cfg = ((self.rules.get("finish") or {}).get("styles") or {})
        w = {k: float(cfg.get(k, 1.0)) for k in self.KO_STYLES}
        hard = set(kinds or ()) & {"slam", "charge", "spike", "drop", "blow in mid-air"}
        if hard:
            w["instant"] *= 3.0
        if devastating:
            w["instant"] *= 2.0
            w["scream"] *= 1.5
        if loss >= 6:
            w["scream"] *= 2.0
        down = d.name in self.downed or bool(self.pinned_by(d.name))
        if down:
            w["crumple"] *= 0.2
            w["fade"] *= 2.0
        else:
            w["crumple"] *= 1.5
        if set(kinds or ()) & {"held stream", "pummel"} or loss < 3:
            w["fade"] *= 1.8
        total = sum(w.values()) or 1.0
        roll = self.rng.random() * total
        for k in self.KO_STYLES:
            roll -= w[k]
            if roll <= 0:
                return k
        return "fade"

    def knockout_roll(self, name, lost, kinds, devastating=False):
        """Very rarely a big enough beat simply knocks her OUT, no pin needed (moves.knockout): only when she is
        already very low (max_health_pct of her full health or less), the beat cost her at least min_loss_pct of
        it, and it came from something that piles up or hits all at once (a held stream, a pummel, a chain, a charge
        into the scenery, a spike or a catch in mid-air, a drop from a height, a slam), or landed devastatingly.
        Returns the elimination result, or None."""
        cfg = (self.rules.get("moves") or {}).get("knockout") or {}
        d = self.get(name)
        if self.submission_match() and not self.sub_knockouts():
            return None          # (a submission match: no blow puts her out, only a tap-out or a pass-out)
        if self.ko_only() and not d.eliminated and d.max_health:
            loss = lost / d.max_health * 100.0
            ch = self._ko_only_chance(d, loss, devastating)
            if ch <= 0:
                return None
            how = " and ".join(kinds) if kinds else "blow" if not devastating else "devastating blow"
            if not self._chance(ch, f"{d.name} knocked out by the {how}", "KNOCKED OUT", "she stays conscious"):
                return None
            style = self.knockout_style(d, loss, kinds, devastating)
            out = self.eliminate(d.name, f"knocked out cold by the {how}")
            out.update(knockout=True, how=how, chance=round(ch, 3), loss_pct=round(loss, 1), style=style)
            return out
        if not cfg.get("enabled", True) or d.eliminated or not d.max_health or not (kinds or devastating):
            return None
        pct = self._health_pct(d)
        loss = lost / d.max_health * 100.0
        if pct > float(cfg.get("max_health_pct", 15)) or loss < float(cfg.get("min_loss_pct", 6)):
            return None
        ch = (float(cfg.get("base", 0.03)) + float(cfg.get("per_loss_pct", 0.008)) * (loss - float(cfg.get("min_loss_pct", 6)))
              + float(cfg.get("below_zero_per_10", 0.01)) * max(0.0, -pct) / 10.0)
        if devastating:
            ch *= float(cfg.get("devastating_mult", 2.0))
        if self.has(d, "adrenaline"):
            ch *= 0.5
        ch = min(float(cfg.get("max", 0.25)), ch)
        how = " and ".join(kinds) if kinds else "devastating blow"
        if not self._chance(ch, f"{d.name} knocked out by the {how}", "KNOCKED OUT", "she stays conscious"):
            return None
        style = self.knockout_style(d, loss, kinds, devastating)
        out = self.eliminate(d.name, f"knocked out cold by the {how}")
        out.update(knockout=True, how=how, chance=round(ch, 3), loss_pct=round(loss, 1), style=style)
        return out

    def eliminate(self, name, reason=""):
        """The story decides a fighter is out (pinned for the full count, knocked out, submitted)."""
        d = self.get_active(name)
        was_down = d.name in self.downed
        self.__dict__.setdefault("out_reason", {})[d.name] = reason
        ended = self._put_out(d)
        if self.facing.get(d.name) == "sitting up":   # nobody stays sitting once she's out: she slumps over
            self.facing[d.name] = self.rng.choice(["on her side", "face-up"])
        return {"type": "eliminated", "fighter": d.name, "reason": reason,
                "unhurt": all(p.damage < 1 for p in d.parts.values()),
                "facing": self.facing.get(d.name), "was_down": was_down,
                "holds_ended": ended, "winner": self.winner()}

    def _put_out(self, d):
        """A fighter leaves the fight: every hold and pin by or on her ends, and she lies where she is (the way she
        was lying, or however she drops). Returns the ids of the holds that ended."""
        d.eliminated = True
        d.recovery, d.out_beats = 0, 0
        self.pressed.pop(d.name, None)
        ended = []
        for h in list(self.holds.values()):
            if d.name in (h.attacker, h.defender):
                ended.append(h.id)
                del self.holds[h.id]
        for k, p in list(self.pins.items()):
            if k not in self.pins:
                continue
            if p["defender"] == d.name:
                del self.pins[k]
            elif d.name in self.pin_members(p):
                self._leave_pin(k, d.name, f"{d.name} is out")  # a double pin carries on with whoever is left
        if self.facing.get(d.name) == "sitting up":   # nobody stays sitting once she's out: she slumps over
            self.facing[d.name] = self.rng.choice(["on her side", "face-up"])
        if self.facing.get(d.name) not in self.FACING_LOOK:
            self.facing[d.name] = self._guess_facing(d.name)
        self.downed.pop(d.name, None)
        self._fresh_down.discard(d.name)
        # an alliance against her (or one with nobody left to fight) is over the moment she is out, before anyone
        # asks who has won
        self._pending_events += self._alliance_tick(count=False)
        return ended

    def revive(self, name):
        """Bring a knocked-out fighter back INTO the fight (undoes an elimination). If she hadn't got back to her
        feet yet, she rejoins it on the ground, lying as she was."""
        f = self.get(name)
        if not f.eliminated:
            raise ValueError(f"{f.name} is already in the fight")
        lying = self.lying_out(f)
        f.eliminated, f.recovery, f.out_beats = False, 0, 0
        if lying:
            self.downed[f.name] = 0
            if self.facing.get(f.name) not in self.FACING_LOOK:
                self.facing[f.name] = self._guess_facing(f.name)
        else:
            self.facing.pop(f.name, None)

    # ---------- views ----------
    def _tags(self, hits):
        tags = []
        if any(h["pain_tier_changed"] for h in hits):
            tags.append("crossed_pain_threshold")
        if any(h["pain_tier"] == "excruciating" for h in hits):
            tags.append("excruciating")
        if any(h["health_tier_changed"] for h in hits):
            tags.append("health_tier_dropped")
        if len(hits) >= 3:
            tags.append("flurry")
        if hits and max(h["damage_taken"] for h in hits) >= 20:
            tags.append("big_hit")
        return tags

    def pin_end_note(self):
        e = self.last_pin_end
        if not e or self.turn - e.get("turn", -99) > 2:
            return ""
        if e.get("note"):
            return (f" {e['note'][0].upper() + e['note'][1:]}: THAT PIN IS OVER. They are apart now, no clock is "
                    f"running, and {e['pinner']} would need a brand-new pin.")
        return (f" {e['pinned']} {e['how']} from {poss_word(e['pinner'])} pin"
                + ("" if self.fade_mode() else f" at second {e['second']}") + ": THAT PIN IS OVER. "
                f"They are apart now, no clock is running, and {e['pinner']} would need a brand-new pin.")

    # what a badly hurt part of each region costs her, in the fight (for her thoughts: narration.rich.inner)
    WOUND_COST = {"head": "a ringing head, a beat slower to read what comes at her",
                  "neck": "every breath scraping past it, never a full one",
                  "shoulder": "that side slow to lift or guard",
                  "fore_up": "a weaker limb: blows from it, and her guard on that side, cost more",
                  "fore_low": "a weaker limb: blows from it, and her guard on that side, cost more",
                  "chest": "deep breaths hurting, so shallow breathing and sooner tired",
                  "belly": "every twist and bend pulling at it",
                  "back_up": "turning and rising pulling at it", "back_low": "turning and rising pulling at it",
                  "hind_up": "worse footing, slower to push off or spring away",
                  "hind_low": "worse footing, slower to push off or spring away",
                  "tail": "balance off, the tail answering slower"}
    JAW_COST = "biting or opening her mouth hurting her own jaw"

    def record_inner(self, results):
        """Keep what each fighter has learned this fight (her moves that land and miss, the ones that hit her, the
        attacks she has dodged, how much the last beat cost her). Called once a beat after the clock; it only reads."""
        rec = self.__dict__.setdefault("fight_record", {})
        for f in self.fighters.values():
            r = rec.setdefault(f.name, {"landed": {}, "missed": {}, "hit_by": {}, "dodged": 0, "track": []})
            r["track"] = (list(r.get("track") or []) + [round(self.strength(f), 1)])[-30:]
        for a in results or []:
            if not isinstance(a, dict) or a.get("type") != "instant" or a.get("environment"):
                continue
            att, dfn = a.get("attacker") or "", str(a.get("defender") or "").split(",")[0].strip()
            mv = (a.get("move") or {}).get("name")
            if not att or not dfn or not mv or att not in rec or dfn not in rec or a.get("self_move") \
                    or a.get("confused_self_hit") or att == dfn:
                continue        # (a stance or weather move, or a hit on herself: neither lands nor misses)
            status_landed = a.get("status_applied") and not a.get("missed") and not a.get("dodged")
            if status_landed or any((h.get("defender") or dfn) == dfn for h in a.get("hits") or []):
                rec[att]["landed"][mv] = rec[att]["landed"].get(mv, 0) + 1
                rec[dfn]["hit_by"][mv] = rec[dfn]["hit_by"].get(mv, 0) + 1
            else:
                rec[att]["missed"][mv] = rec[att]["missed"].get(mv, 0) + 1
                if a.get("dodged"):
                    rec[dfn]["dodged"] = int(rec[dfn].get("dodged", 0)) + 1

    def inner_state(self, name):
        """True things she knows from the fight so far, for her thoughts and plans (narration.rich.inner): what has
        worked for her and what hasn't, what keeps hurting her, what her worst wounds now stop her doing, how tired
        she is, what she can see is wrong with her opponent, and what the last beat cost her. Plain sentences about
        her ('she'), never decisions: nothing here changes the fight."""
        f = self.fighters.get(str(name).lower())
        if not f or f.eliminated:
            return []
        cfg = ((self.rules.get("narration") or {}).get("rich") or {})
        hurt_at = float(cfg.get("wound_from", 90))
        r = (getattr(self, "fight_record", None) or {}).get(f.name) or {}
        rivals = [o for o in self.active() if o is not f]
        rv = rivals[0].name if len(rivals) == 1 else "her opponent"
        out = []
        landed, missed = r.get("landed") or {}, r.get("missed") or {}
        best = max(landed, key=lambda m: (landed[m], -missed.get(m, 0)), default=None)
        if best and landed[best] >= 2:
            tries = landed[best] + missed.get(best, 0)
            out.append(f"her {best} has found {rv} {landed[best]} times out of {tries}: it keeps getting through")
        worst = max(missed, key=lambda m: (missed[m] - landed.get(m, 0), missed[m]), default=None)
        if worst and missed[worst] >= 2 and missed[worst] > landed.get(worst, 0):
            out.append(f"her {worst} has missed {missed[worst]} times" + (
                f" and landed only {landed[worst]}" if landed.get(worst) else "") + f": {rv} has its measure")
        hit_by = r.get("hit_by") or {}
        top = max(hit_by, key=hit_by.get, default=None)
        if top and hit_by[top] >= 2:
            out.append(f"{poss_word(rv)} {top} has hit her {hit_by[top]} times now: she knows its shape, and dreads it")
        if int(r.get("dodged") or 0) >= 2:
            out.append(f"she has slipped {int(r['dodged'])} of {poss_word(rv)} attacks: she trusts her eyes")
        # the whole fight's tally, for the early beats before any one move has a pattern
        n_land, n_try = sum(landed.values()), sum(landed.values()) + sum(missed.values())
        if n_try >= 2 and not out:
            out.append(f"she has landed {n_land} of her {n_try} attacks so far" + (
                ": everything she throws is getting through" if n_land == n_try else
                ": nothing she throws is getting through" if n_land == 0 else ""))
        if not hit_by and self.turn > 1 and rivals and not any(p.damage > 0 for p in f.parts.values()):
            out.append(f"nothing of {poss_word(rv)} has touched her yet")
        # what her worst wounds stop her doing (one line a region, the worst first)
        seen = set()
        for p in sorted(f.parts.values(), key=lambda p: -p.damage):
            if p.damage < hurt_at or len(seen) >= int(cfg.get("wounds_listed", 2)):
                break
            reg = body_region(p.name)
            cost = self.JAW_COST if re.search(r"\b(?:jaw|muzzle|snout|mouth)\b", p.name, re.I) else self.WOUND_COST.get(reg)
            if cost and cost not in seen:
                seen.add(cost)
                out.append(f"her {p.name.lower()} badly hurt (in note form, never copied: {cost})")
        en = float(getattr(f, "energy", 100) or 0)
        if en < float(cfg.get("low_energy", 30)):
            out.append("she is running low on energy: every big move now costs more than she has to spare")
        elif en < float(cfg.get("tired_energy", 60)):
            out.append("she is tiring: her moves are starting to cost her")
        for o in rivals[:1]:
            op = max(o.parts.values(), key=lambda p: p.damage, default=None)
            if op and op.damage >= hurt_at:
                out.append(f"she can see {o.name} favouring her {op.name.lower()}: it is the place to go for")
        track = r.get("track") or []
        if len(track) >= 2:
            lost = track[-2] - track[-1]
            if lost >= float(cfg.get("big_loss", 8)):
                out.append(f"that beat took a real piece out of her (about {lost:.0f}% of her strength)")
            elif lost <= 0.5 and len(track) >= 3 and track[-3] - track[-2] >= float(cfg.get("big_loss", 8)):
                out.append("she got through that beat without fresh harm, after the beat before took so much")
        return out[:int(cfg.get("max_lines", 6))]

    def is_ruined(self, p):
        """ruined (since build 242): a part past ruined.min (500%) damage: past devastated, it has stopped working."""
        rc = self.rules.get("ruined") or {}
        return rc.get("enabled", True) and p.damage >= float(rc.get("min", 500))

    def ruined_parts(self, f):
        return [p.name for p in f.parts.values() if self.is_ruined(p)]

    def _leg_regions(self, f):
        return ("hind_up", "hind_low") + (("fore_up", "fore_low") if self.body_plan(f) == "quadruped" else ())

    def _ruined_getup(self, f, regions):
        rc = self.rules.get("ruined") or {}
        legs = [p for p in f.parts.values() if self.is_ruined(p) and body_region(p.name) in regions]
        return float(rc.get("getup_penalty", 0.15)) * min(2, len(legs))

    def _ruined_tick(self):
        """ruined: what a part past devastated does to her by itself each beat. A ruined LEG folds under her when
        she puts weight on it (buckle_chance: she catches herself, off balance for a beat; she doesn't go down). Any
        ruined part is jarred by her own movement, her breathing, a turn (jar_chance: told, no damage). One of the
        two a beat at most."""
        rc = self.rules.get("ruined") or {}
        if not rc.get("enabled", True):
            return []
        events = []
        for f in self.active():
            ruined = [p for p in f.parts.values() if self.is_ruined(p)]
            if not ruined:
                continue
            legs = [p for p in ruined if body_region(p.name) in self._leg_regions(f)]
            free = (f.name not in self.downed and not self.has(f, "airborne") and not self.pinned_by(f.name)
                    and not any(h.defender == f.name for h in self.holds.values()))
            if legs and free and self._chance(float(rc.get("buckle_chance", 0.25)),
                                              f"{poss_word(f.name)} ruined {legs[0].name.lower()} folding under her",
                                              "it FOLDS", "it holds her"):
                self.set_status(f, "off_balance", 1)
                events.append({"type": "ruined_buckle", "fighter": f.name, "part": legs[0].name})
                continue
            p = max(ruined, key=lambda x: x.damage)
            last = f.learned.get("jar_turn")
            if last is not None and self.turn - int(last) < int(rc.get("jar_cooldown", 3)):
                continue    # (jar_cooldown: told at most once every few beats, so it doesn't fill every passage)
            if self._chance(float(rc.get("jar_chance", 0.3)), f"{poss_word(f.name)} own movement jarring her ruined "
                            f"{p.name.lower()}", "it jars it", "no"):
                f.learned["jar_turn"] = self.turn
                events.append({"type": "ruined_jar", "fighter": f.name, "part": p.name,
                               "how": self.rng.choice(("a breath too deep", "turning to keep her eyes on the other",
                                                       "shifting her weight", "her own heartbeat", "a flinch at nothing"))})
        return events

    def _low_cfg(self, key=None):
        """low_health (since build 246), or one of its parts (idle, squirm, tells, last_stand, foe_read); {} when it
        is off."""
        lc = self.rules.get("low_health") or {}
        if not lc.get("enabled", True):
            return {}
        if key is None:
            return lc
        sub = lc.get(key) or {}
        return sub if sub.get("enabled", True) else {}

    def low_now(self, f, at=None):
        """Is she at the very end of her strength (low_health.at_pct % of full health or less)?"""
        lc = self._low_cfg()
        return bool(lc) and self._health_pct(f) <= float(at if at is not None else lc.get("at_pct", 10))

    _LIMB_OF = {"fore_up": "arm", "fore_low": "arm", "hind_up": "leg", "hind_low": "leg", "tail": "tail"}

    def dead_limb(self, a, move):
        """low_health.tells: the part of hers that isn't answering this beat, if this move is thrown with it."""
        dl = a.learned.get("dead_limb") or {}
        if not dl or int(dl.get("turn", -1)) != self.turn or not move:
            return None
        text = f"{move.get('name', '')} {move.get('about', '')}".lower()
        kind = "charge" if move.get("charge") else next((k for k, rx in self.LIMB_KINDS if rx and re.search(rx, text)),
                                                        None)
        want = dl.get("kind")
        if kind == want or (kind == "charge" and want == "leg") or (kind == "wing" and want == "wing"):
            return dl.get("part")
        return None

    def _low_health_tick(self, events_so_far=()):
        """low_health: what a fighter at the very end of her strength (at_pct % of full health or less) does by
        herself, a told event each, never more than one of each kind a beat:
        - idle: on her feet and left alone this beat, she sways, leans on something, blinks blood away, spits, tests
          a bad leg, fights for breath; the other one sees it (closes in, waits, circles);
        - squirm: down and free, she drags herself toward the other or away, claws at the ground, curls round her
          worst part;
        - tells: her body gives her away (shaking, ragged breath) and now and then a hurt limb doesn't answer: moves
          thrown with it can't be used next beat;
        - last_stand: after her once-a-fight last-stand blow (moves.last_stand), she is wide open the beat after
          (dodge x open_dodge_mult);
        - foe_read: the other one reads her state (she's done, finish it; careful, she has one more in her; why is
          she still standing), and the director is told."""
        lc = self._low_cfg()
        if not lc:
            return []
        events, rose = [], {e.get("fighter") for e in events_so_far if e.get("type") == "get_up"}
        # (get_up_tick has already emptied _fresh_down: who only just went down is in its "stays down" events)
        fresh = {e.get("fighter") for e in events_so_far if e.get("type") == "stays_down" and e.get("why") == "fresh"}
        for f in self.active():
            free = not self.pinned_by(f.name) and not any(f.name in (h.attacker, h.defender) for h in self.holds.values())
            out = self.has(f, "asleep") or self.has(f, "frozen")
            foe = next((x for x in self.active() if x is not f and (not x.team or x.team != f.team)), None)
            # last stand (moves.last_stand, her one all-in blow): the beat after it, she is wide open
            if self._low_cfg("last_stand") and f.learned.get("last_stand_turn") == self.turn - 1 \
                    and not self.has(f, "overextended"):
                self.set_status(f, "overextended", 1)
                events.append({"type": "overextended", "fighter": f.name})
            if out or not self.low_now(f):
                continue
            cfg = self._low_cfg("idle")
            if cfg and f.name not in self.downed and free and f.name not in self.involved and not self.has(f, "airborne") \
                    and self._cool(f, "low_idle", cfg) and self._chance(float(cfg.get("chance", 0.35)),
                                                                     f"{f.name} showing it, left alone", "yes", "no"):
                skip = set()
                if not self.scene_props():
                    skip.add("lean")
                legs = [p for p in f.parts.values() if self._LIMB_OF.get(body_region(p.name)) == "leg"]
                bad = max(legs, key=lambda p: p.damage, default=None)
                if not bad or bad.damage < 150:
                    skip.add("test_leg")
                ev = {"type": "low_idle", "fighter": f.name, "way": self.vary("low_idle", skip),
                      "prop": self.rng.choice(self.scene_props()) if self.scene_props() else "",
                      "leg": bad.name if bad else "", "watcher": foe.name if foe else "",
                      "watch": self.vary("low_watch") if foe else ""}
                f.learned["low_idle"] = self.turn
                events.append(ev)
            cfg = self._low_cfg("squirm")
            if cfg and f.name in self.downed and f.name not in rose and free and f.name not in fresh \
                    and self._cool(f, "low_squirm", cfg) and self._chance(float(cfg.get("chance", 0.4)),
                                                                       f"{f.name} squirming where she lies", "yes", "no"):
                worst = max(f.parts.values(), key=lambda p: p.damage)
                f.learned["low_squirm"] = self.turn
                events.append({"type": "low_squirm", "fighter": f.name, "way": self.vary("low_squirm"),
                               "part": worst.name, "toward": foe.name if foe else "",
                               "prop": self.rng.choice(self.scene_props()) if self.scene_props() else ""})
            cfg = self._low_cfg("tells")
            if cfg and self._cool(f, "low_tell", cfg) and self._chance(float(cfg.get("chance", 0.25)),
                                                                     f"{poss_word(f.name)} body giving her away", "yes", "no"):
                limbs = [p for p in f.parts.values() if (self._LIMB_OF.get(body_region(p.name))
                                                         or ("wing" if "wing" in p.name.lower() else None))
                         and p.damage >= float(cfg.get("dead_limb_damage", 100))]
                way = self.vary("low_tell", () if limbs else ("dead_limb",))
                ev = {"type": "low_tell", "fighter": f.name, "way": way}
                if way == "dead_limb":
                    p = max(limbs, key=lambda x: x.damage)
                    kind = "wing" if "wing" in p.name.lower() else self._LIMB_OF.get(body_region(p.name))
                    f.learned["dead_limb"] = {"part": p.name, "kind": kind, "turn": self.turn}
                    ev.update(part=p.name, kind=kind)
                f.learned["low_tell"] = self.turn
                events.append(ev)
            cfg = self._low_cfg("foe_read")
            if cfg and foe and not (self.has(foe, "asleep") or self.has(foe, "frozen")) \
                    and self._cool(foe, "read_turn", cfg) and self._chance(float(cfg.get("chance", 0.3)),
                                                                        f"{foe.name} reading {poss_word(f.name)} state",
                                                                        "yes", "no"):
                skip = () if f.health <= 0 and f.name not in self.downed else ("still_standing",)
                kind = self.vary("foe_read", skip)
                foe.learned["read_turn"] = self.turn
                foe.learned["foe_read"] = {"of": f.name, "kind": kind, "turn": self.turn}
                events.append({"type": "foe_read", "fighter": foe.name, "of": f.name, "kind": kind})
        return events

    def _cool(self, f, key, cfg):
        """A low_health event of this kind is told at most once every cooldown beats."""
        last = f.learned.get(key)
        return last is None or self.turn - int(last) >= int(cfg.get("cooldown", 3))

    def long_match_ramp(self):
        """finish.submission.long_ramp (since build 247): in a submission match that has run past `after` beats, the
        damage blows and grips do to body PARTS is multiplied by 1 + per_10 for every 10 beats past it, never above
        max (health loss unchanged), so a long match wears its fighters down faster and comes to an end. `only`:
        "taps" (a match needing more than one tap, the default) or "submission" (every submission match)."""
        sub = ((self.rules.get("finish") or {}).get("submission") or {})
        lr = sub.get("long_ramp") or {}
        if not lr.get("enabled", True) or not self.submission_match():
            return 1.0
        if str(lr.get("only", "taps")).lower() == "taps" and self.taps_needed() <= 1:
            return 1.0
        # (the beat being played: during its actions the clock still shows the last one; the end-of-beat tick has
        # already moved it on)
        past = self.turn + (0 if getattr(self, "_ticking", False) else 1) - int(lr.get("after", 40))
        if past <= 0:
            return 1.0
        return min(float(lr.get("max", 2.5)), 1.0 + float(lr.get("per_10", 0.15)) * past / 10.0)

    def zero_part_ramp(self, f):
        """below_zero.part_ramp (since build 244): with her health below zero, the damage her PARTS take from each
        blow or grip is multiplied, more the deeper she goes: 1 + per_10 for every 10% of her full health below zero,
        never above max. Her health loss is untouched. `only` says where: "taps" (a submission match needing more
        than one tap: worn-down parts give way faster, so the next tap comes sooner), "submission" (any submission
        match), "all" (every fight)."""
        pr = (self.rules.get("below_zero") or {}).get("part_ramp") or {}
        if not pr.get("enabled", True) or f is None or f.health >= 0:
            return 1.0
        only = str(pr.get("only", "taps")).lower()
        if only == "taps" and not (self.submission_match() and self.taps_needed() > 1):
            return 1.0
        if only == "submission" and not self.submission_match():
            return 1.0
        below = -f.health / max(1.0, f.max_health) * 100
        return min(float(pr.get("max", 3.0)), 1.0 + float(pr.get("per_10", 0.08)) * below / 10.0)

    def zero_stage(self, f):
        """below_zero (since build 242): the stage her health has fallen to below zero (health as a share of her
        full: 0, -20%, -50% by default), as its rules entry, or None while she is above zero."""
        bz = self.rules.get("below_zero") or {}
        if not bz.get("enabled", True) or f is None:
            return None
        pct = self._health_pct(f)
        if pct > 0:
            return None
        hit = [st for st in (bz.get("stages") or []) if pct <= float(st.get("at", 0))]
        return min(hit, key=lambda st: float(st.get("at", 0))) if hit else None

    def _below_zero_tick(self):
        """below_zero: once a beat, for a fighter at or below zero health. The first time she gets there, her
        refusal (refuse_moment: one passage of her refusing to go down, once a fight). After that, by stage: her
        sight may grey out for a beat (grey_chance: she sways, dodges poorly, hits softer), and, with her one
        adrenaline surge long spent, a second one may still come (second_surge, once a fight)."""
        bz = self.rules.get("below_zero") or {}
        if not bz.get("enabled", True):
            return []
        events = []
        for f in self.active():
            st = self.zero_stage(f)
            if not st:
                continue
            idx = sorted((float(x.get("at", 0)) for x in bz.get("stages") or []), reverse=True).index(float(st.get("at", 0)))
            if "refused_fall" not in f.learned and bz.get("refuse_moment", True):
                f.learned["refused_fall"] = self.turn
                plan = (getattr(self, "game_plans", None) or {}).get(f.name) or {}
                foe = next((o for o in self.active() if o.team != f.team), None)
                worst = max(f.parts.values(), key=lambda p_: p_.damage)
                events.append({"type": "refuses_to_fall", "fighter": f.name, "stage": st.get("label"),
                               "down": f.name in self.downed,
                               "against": foe.name if foe else "", "plan_zone": plan.get("zone", ""),
                               "worst": worst.name})
                continue
            if f.learned.get("zero_stage_seen", -1) < idx:
                f.learned["zero_stage_seen"] = idx
                events.append({"type": "zero_stage", "fighter": f.name, "stage": st.get("label"), "at": st.get("at")})
            if (float(st.get("second_surge", 0)) > 0 and f.adrenaline_used and "second_surge" not in f.learned
                    and not self.has(f, "adrenaline")
                    and self._chance(float(st["second_surge"]), f"{f.name} finding a second wind below zero",
                                     "SECOND WIND", "no")):
                f.learned["second_surge"] = self.turn
                beats = int(bz.get("second_surge_beats", 2))
                self.set_status(f, "adrenaline", beats)
                events.append({"type": "adrenaline", "fighter": f.name, "beats": beats, "second": True})
                continue
            last = f.learned.get("grey_turn")
            if last is not None and self.turn - int(last) < int(bz.get("grey_cooldown", 3)):
                continue    # (grey_cooldown: her sight greys at most once every few beats)
            if float(st.get("grey_chance", 0)) > 0 and not self.has(f, "adrenaline") and self._chance(
                    float(st["grey_chance"]), f"{poss_word(f.name)} sight greying out", "it GREYS", "she stays clear"):
                self.set_status(f, "greyed", 1)
                f.learned["grey_turn"] = self.turn
                events.append({"type": "grey_out", "fighter": f.name})
        return events

    def strength(self, f):
        """Overall condition as a share of this fighter's OWN full health (fighters start at different totals)."""
        return self._health_pct(f)

    STORY_MOODS = {
        "confident": ["confident, in no hurry", "sure of herself, and enjoying it a little",
                      "calm, almost lazy: she thinks she has the measure of this"],
        "pressing": ["she smells a chance and means to take it", "eager, leaning in, wanting to finish what she started",
                     "hungry now; she will not let the other breathe"],
        "wary": ["alert, measuring, giving nothing away", "careful: she has learned to respect what the other can do",
                 "watchful, saving herself, waiting to be shown a mistake"],
        "worried": ["worried about where this is going, and hiding it", "uneasy: the fight is slipping and she can feel it",
                    "afraid of the next exchange, and angry at being afraid"],
        "desperate": ["desperate: she needs something to change, and soon", "cornered, and at her most dangerous for it",
                      "running out of fight and willing to try anything"],
        "grim": ["grim and careful: she is ahead in a fight that is hurting her", "set, unsmiling, paying for every bit of it",
                 "tired of this and determined to see it through"],
        "stubborn": ["stubborn: she has been hurt and has decided it changes nothing", "bloody-minded; pain has only made her ruder",
                     "sore, cross, and nowhere near done"],
        "shaken": ["shaken: that last one went in deeper than she will admit", "rattled, and trying to cover it with anger",
                   "badly jolted; she needs a moment she is not going to be given"],
        "relieved": ["just out of a pin: shaky, furious, breathing as if she had been under water",
                     "free again and half disbelieving it, with a score to settle"],
        "pinned_fighting": ["pinned and furious, and far from done", "under the other's weight and already planning the way out"],
        "pinned_weakening": ["pinned and frightened, and fighting the fright as hard as the hold",
                             "pinned, tiring, and refusing to think about what that means"],
        "pinned_fading": ["pinned and slipping, and still refusing", "nearly gone under the pin, holding on by stubbornness alone"],
        "pinning": ["holding a pin and finding out how much it costs to hold", "on top, straining, willing the other to stop"],
    }

    def story_peek(self):
        """story_state() for a look BEFORE the beat (the director's): it leaves the beat-to-beat memory untouched."""
        names = ("_story_prev", "_story_now", "_story_pinned", "_story_turned")
        keep = {k: self.__dict__.get(k) for k in names if k in self.__dict__}
        try:
            return self.story_state()
        finally:
            for k in names:
                self.__dict__.pop(k, None)
            self.__dict__.update(keep)

    def story_state(self):
        """Where the fight stands as a STORY, in plain words, worked out from what the engine already tracks: how far
        along it is, how each fighter is doing and who has been pressing whom, how it sits with her, and whether it
        has just turned. Nothing here decides anything; it is for the narrator's (and the director's) sense of the
        whole. Returns {"stage": str, "fighters": {name: str}, "mood": {name: key}, "turned": str or None,
        "tense": bool}."""
        act = [f for f in self.active()]
        if len(act) < 2:
            return None
        st = {f.name: self.strength(f) for f in act}
        prev = getattr(self, "_story_prev", None)
        if not prev or prev[0] != self.turn:      # strengths as they stood when the previous beat ended
            self._story_prev = (self.turn, getattr(self, "_story_now", st))
            self._story_now = dict(st)
        before = self._story_prev[1]
        low, high = min(st.values()), max(st.values())
        pinned = {p["defender"]: p for p in self.pins.values()}
        pinners = {m for p in self.pins.values() for m in self.pin_members(p)}
        far = any(float(p.get("fade", 0) or 0) >= 50 for p in pinned.values())
        if low < 25 or far:
            stage = "near the end: one of them has very little left"
        elif low < 50:
            stage = "late: the damage is telling, and every exchange costs something that will not come back"
        elif high < 92 or (self.turn > 4 and (high < 97 or self.turn > 8 or not (self._gap_cfg().get("enabled", True)
                                                                 and self._gap_cfg().get("fresh_is_early", True)))):
            # (a few beats in with both of them all but untouched is still the opening, not the middle:
            # narration.match_state.fresh_is_early)
            stage = "the middle: both have been hurt, neither is close to finished"
        else:
            stage = "early: both are close to fresh and still finding each other out"
        mom = [m.split(">")[0] for m in self.momentum if ">" in m]
        recent, prior = mom[-4:], mom[-8:-4]
        hurt = {f.name: sum(1 for p in f.parts.values() if p.damage >= 90) for f in act}     # "very painful" or worse
        out, moods = {}, {}
        for f in act:
            me = st[f.name]
            rival = max((o for o in act if o is not f), key=lambda o: st[o.name])
            share = recent.count(f.name) / len(recent) if recent else 0.5
            streak = 0
            for who in reversed(mom):
                if who != f.name:
                    break
                streak += 1
            # ahead or behind: strength, how many parts are badly hurt on each side, and who has been pressing
            # late on, a few points of strength are a big share of what is left: 9% against 15% is not level
            gap = (me - st[rival.name]) * max(1.0, 50.0 / max(me, st[rival.name], 10.0))
            score = (gap + 2.5 * max(-6, min(6, hurt[rival.name] - hurt[f.name]))
                     + (12.0 * (share - 0.5) if len(recent) >= 3 else 0.0))
            bits = []
            if score >= 18:
                bits.append("has had much the better of it" + (" and is barely marked" if me >= 85 and hurt[f.name] == 0 else
                                                               ", though getting there has cost her" if hurt[f.name] >= 3 else "")
                            if st[rival.name] < 80 or self.turn > 6 else "has had the better of it so far")
            elif score >= 7:
                bits.append("is ahead, though not by much")
            elif score <= -18:
                # (at a high damage scale parts are in real pain long before strength goes: "badly hurt" is for a
                # fighter who has lost real strength)
                bits.append("is well behind and badly hurt, and she knows it" if me < 55 or (hurt[f.name] >= 3 and me < 72) else
                            "has had the worse of it so far, and several parts of her know it" if hurt[f.name] >= 3 else
                            "is clearly behind and feeling it")
            elif score <= -7:
                bits.append("is behind, though not by much")
            else:
                bits.append("is level with her opponent: neither has an edge worth the name")
            if streak >= 3:
                bits.append(f"she has made the last {streak} attacks and is pressing")
            elif recent and share == 0 and len(recent) >= 3:
                bits.append(f"she has been on the back foot for the last {len(recent)} exchanges, defending and giving ground")
            elif score <= -7 and share >= 0.75 and len(recent) >= 3:
                bits.append("but she has started to turn it: the last exchanges have been hers")
            elif score >= 7 and share <= 0.25 and len(recent) >= 3:
                bits.append("but the last exchanges have gone against her")
            if hurt[f.name] >= 4:
                bits.append(f"{hurt[f.name]} parts of her are in real pain, and it shows in everything she does")
            elif hurt[f.name] == 0 and self.turn > 2:
                bits.append("nothing on her is badly hurt yet")
            downs, pins = self.times("down", f.name), self.times("pinned", f.name)
            was_pinned = f.name in (getattr(self, "_story_pinned", None) or ())
            if f.name in pinned:
                bits.append("she is pinned right now" + (", for the second time" if pins == 2 else
                                                         f", for the {ordinal(pins)} time" if pins > 2 else ""))
            elif pins >= 1:
                bits.append(f"she has already fought her way out of {'a pin' if pins == 1 else str(pins) + ' pins'}")
            if downs >= 3:
                bits.append(f"she has been put on the ground "
                            + ({3: "three times", 4: "four times", 5: "five times"}.get(downs) or "again and again"))
            lost = float(before.get(f.name, me)) - me
            fade = float((pinned.get(f.name) or {}).get("fade", 0) or 0)
            fade = max(fade, 55 if me <= 5 else 30 if me < 25 else 0)     # (her own strength counts: fade_words)
            mood = ("pinned_fading" if f.name in pinned and fade >= 55 else
                    "pinned_weakening" if f.name in pinned and fade >= 30 else
                    "pinned_fighting" if f.name in pinned else
                    "pinning" if f.name in pinners else
                    "relieved" if was_pinned else
                    "desperate" if me < 30 or score <= -30 else
                    "shaken" if lost >= 4.0 and score < 7 else
                    "worried" if score <= -14 else
                    "pressing" if streak >= 3 and score >= 0 else
                    "confident" if score >= 18 and hurt[f.name] <= 1 else
                    "grim" if score >= 7 and hurt[f.name] >= 3 else
                    "stubborn" if hurt[f.name] >= 2 else
                    "wary")
            moods[f.name] = mood
            words = self.STORY_MOODS[mood]
            out[f.name] = "; ".join(bits) + ". How it sits with her: " + words[(self.turn + len(f.name)) % len(words)] + "."
        if not prev or prev[0] != self.turn:
            self._story_pinned = set(pinned)      # who was pinned when this beat ended, for "just out of a pin" next beat
        # the fight TURNS when the pressing changes hands outright: the last four attacks all one fighter's, after
        # three of the four before them were the other's. It is said once, not on every beat that follows
        turned = None
        if len(recent) == 4 and len(prior) >= 3:
            a_, b_ = max(set(recent), key=recent.count), max(set(prior), key=prior.count)
            told = getattr(self, "_story_turned", None)
            if a_ != b_ and recent.count(a_) == 4 and prior.count(b_) >= 3 and not (
                    told and told[0] == a_ and self.turn - told[1] < 6 and told[1] != self.turn):
                turned = f"the fight has just turned: {b_} was doing the pressing, and now it is {a_}"
                if not told or told[1] != self.turn:
                    self._story_turned = (a_, self.turn)
        return {"stage": stage, "fighters": out, "mood": moods, "turned": turned, "tense": far,
                "pins": {f.name: self.times("pinned", f.name) for f in act}}

    def strength_words(self, f):
        s = self.strength(f)
        ht = tier_for(s, self.rules["health_tiers"])
        return f"{s:.0f}% of full strength ({ht['label']})", ht

    STATUS_LOOK = {
        "paralyzed": "PARALYZED: muscles locking up, sparks crawling over her, stiff and jerky, slow to react",
        "chilled": "CHILLED: frost in her fur, shivering, limbs stiff and slow",
        "bound": "BOUND: a limb wrapped tight and held: it goes numb and tingling, weak and slow to answer, and she can't "
                 "move freely; the rest of her is untouched",
        "constricted": "CONSTRICTED: coils wound round her, tightening, cutting off her circulation: her trapped limbs go "
                       "cold, heavy and tingling, her pulse pounds in her ears and then slows, her sight greys at the "
                       "edges, every breath is short; she gets no strength back while they hold (her heart slows, it "
                       "never stops)",
        "sputtering": "SPUTTERING: water forced into her mouth and up her nose: coughing, choking it up, eyes and nose "
                      "burning, short of breath (never drowning)",
        "fury": "FURIOUS after breaking the pin: a cold, hard anger behind every blow",
        "breathless": "the WIND KNOCKED OUT of her: she can't get a full breath; every movement is short of air",
        "dazed": "DAZED from the blow to the head: her vision swims, sounds come late, she is slow to react",
        # (since build 293: moves.head, moves.body_jolts)
        "rattled": "RATTLED by the blow to her head: a hard blink, a shake of the head; a beat slow to dodge",
        "stunned": "STUNNED by the blow to her head: the lights flickered; she CAN'T ACT this beat at all (no attack, no "
                   "grab, no dodge, no escape, no get-up): she sways where she is, eyes unfocused, arms or tail not "
                   "answering, and her opponent can do as she likes with her",
        "wobbly": "her LEGS ARE GONE after the stun: knees dipping, feet not where she puts them; she can barely dodge, "
                  "her blows have nothing under them, getting up or staying up is hard",
        "seeing_double": "SEEING DOUBLE: two of everything; her blows go to the wrong one and slide off",
        "eyes_watering": "her EYES STREAMING from the blow to the nose: blinking through the water, her aim gone soft",
        "ears_ringing": "her EARS RINGING: a high whine over everything, sound muffled and late; she reacts a beat slow",
        "jaw_rattled": "her JAW RATTLED: it aches to close, her teeth don't meet right; her bites are weak",
        "whiplash": "WHIPLASH: her neck stiff and hot from the wrench; she can't turn her head fast",
        "concussed": "CONCUSSED (for the rest of the fight): a dull headache behind her eyes, the light too bright, a "
                     "half-beat fog over her thinking; every blow to the head now rattles her far more easily",
        "dead_leg": "a DEAD LEG: the thigh gone numb and heavy, the knee folding when she puts weight on it",
        "limping": "LIMPING: the knee or foot won't take her weight properly; she hops and favours it, slow to move",
        "dead_arm": "a DEAD ARM: numb from the shoulder down, tingling, her paw slow to close; her blows with it are weak",
        "ribs_aching": "her RIBS ACHING: every breath catches on that side; she holds it close and moves carefully",
        "back_spasm": "her BACK IN SPASM: the muscles locked tight across it; twisting, rising and striking all hurt",
        "tail_numb": "her TAIL NUMB at the base: her balance off without it, every turn a little wide",
        "swollen_eye": "an EYE SWELLING SHUT: the cheek and brow puffed up, her sight narrowed on that side",
        "doubled_over": "DOUBLED OVER by the pain: folded round the hurt, guard down for a moment",
        "staggered": "STAGGERED: knocked a step or more by the last blow and still finding her feet; slow to dodge, open "
                   "to the next one, her own blows weaker",
        "off_balance": "OFF BALANCE: her last blow was turned aside and she is still recovering her footing; slower to "
                       "dodge, weaker on the next strike",
        "protecting": "behind a PROTECT barrier (Protect/Detect): braced and shielded; the next attack on her stops "
                      "against it",
        "countering": "set to COUNTER: braced, weight back, waiting for a close blow to return it twice as hard",
        "mirroring": "set to MIRROR COAT: a sheen over her body, waiting for a blast or beam to send back",
        "airborne": "IN THE AIR: wings beating, above the ground; only blasts, beams and streams can reach her up there, "
                    "and she comes down on her opponent in dives",
        "stiff": "STIFF from the pin she just broke: the limbs that were trapped are numb and slow to answer, pins and "
                 "needles coming back into them; her blows are weaker and she can barely dodge",
        "cramped": "CRAMPED from holding a long pin: her legs and shoulders locked up from bearing down so long, slow "
                   "to move and stiff to turn",
        "soaked": "SOAKED: drenched and dripping, heavier, and badly exposed to Electric attacks",
        "flinched": "FLINCHED: rattled and a half-second behind, she can't launch an attack this beat",
        "reeling": "REELING: just crushed against the scenery, breath not back and legs unsteady; she can still strike, "
                   "but she can't wrestle anyone down or pin",
        "restrained": "RESTRAINED: a limb trapped or a nerve pinched in the pin, her struggles have less to work with",
        "asleep": "ASLEEP: slumped and limp, breathing slow, unable to defend herself or act",
        "frozen": "FROZEN: locked in a shell of ice, unable to move",
        "confused": "CONFUSED: dizzy and disoriented, swaying, her attacks wild (she may hurt herself)",
        "burned": "BURNED: a hot, stinging burn that flares with every movement and saps her strength",
        "poisoned": "POISONED: weak and shaky, the poison sapping her a little every moment",
        "adrenaline": "ADRENALINE SURGE: pain pushed to the back of her mind, eyes sharp, faster and hitting harder "
                      "than she should be able to",
        "greyed": "GREYING OUT: for a moment the edges of her sight go grey and the sound goes far away; she sways, "
                  "a beat behind everything, and drags herself back",
        "overextended": "WIDE OPEN after her last stand: she threw everything and has nothing left to cover with, "
                        "off balance, slow, gasping",
    }

    # the same status from a move that is not cold: CHILLED is the engine's word for any slowing
    STATUS_LOOK_NOT_COLD = {
        "chilled": "SLOWED: her limbs heavy and stiff, slow to answer, every movement a beat behind",
    }
    OVERBALANCED_LOOK = ("OFF BALANCE: she threw too much into her last blow and it carried her past her footing; she "
                         "is still recovering it; slower to dodge, weaker on the next strike")

    def status_look(self, name, status):
        """How a status looks on her: STATUS_LOOK, or the slow of a move that is not cold (Rock Tomb's boulders)."""
        if name in (getattr(self, "_slow_not_cold", None) or ()) and status in self.STATUS_LOOK_NOT_COLD:
            return self.STATUS_LOOK_NOT_COLD[status]
        if status == "off_balance" and name in (getattr(self, "_overbalanced", None) or ()):
            return self.OVERBALANCED_LOOK      # she overcommitted: nothing turned her blow aside
        f = (getattr(self, "fighters", None) or {}).get(str(name).lower())
        look = self.STATUS_LOOK.get(status, status.upper())
        return self.in_her_covering(f, look) if f is not None else look     # (frost in her feathers, on her scales)

    def status_words(self, f):
        bits = [self.status_look(f.name, s) + f" ({n} beat{'s' if n != 1 else ''})" for s, n in f.status.items()]
        e = f.energy
        tired = float(self._cfg("energy").get("tired_below", 25))
        stamina = ("fresh breath" if e >= 70 else "breathing hard" if e >= tired else "gasping, running out of energy")
        s = self.strength(f)
        if s < 0:
            stamina = "gasping, running out of energy"   # past her limit: her breath never reads better than this
        elif any(self.has(f, st) for st in ("breathless", "sputtering")):
            stamina = "no breath in her right now"       # (the wind knocked out of her is not a fresh breath)
        elif self.has(f, "constricted"):
            # (since build 275) the coils squeeze each breath short; they don't knock the wind out of her
            stamina = "short of breath: the coils squeeze every breath short" if e >= tired else stamina
        elif e >= 70 and s < float(self._cfg("energy").get("breath_back_below_strength", 40)):
            stamina = "her breath is back, but not her strength: the body under it is worn out"
        elif e >= 70 and s < float(self._cfg("energy").get("fresh_breath_min_strength", 80)):
            stamina = "breathing hard"                   # (not fresher than the overall word: winded, tired)
        return (" Status: " + "; ".join(bits) + "." if bits else "") + f" Stamina: {stamina}."

    def tier_reaction(self, f, ht):
        """What a fighter at this strength can still do (health_tiers' reaction), fitted to where she is: one up in
        the air has no feet to stand on (reaction_air), one lying down or lying on top in a pin has no ground to
        drop to between efforts (reaction_down)."""
        if self.has(f, "airborne") and ht.get("reaction_air"):
            return ht["reaction_air"]
        if (f.name in self.downed or self.pinning(f.name)) and ht.get("reaction_down"):
            return ht["reaction_down"]
        return ht["reaction"]

    def favoring(self, f):
        """How badly hurt limbs and tails change the way she moves, so it stays consistent from beat to beat."""
        out = []
        for p in sorted(f.parts.values(), key=lambda p: -p.damage):
            region = body_region(p.name)
            if p.damage < 90 or region not in ("fore_up", "fore_low", "hind_up", "hind_low", "shoulder", "tail"):
                continue
            biped = any("arm" in x.lower() for x in f.parts)  # upright fighters guard arms instead of limping
            arm = biped and region in ("fore_up", "fore_low", "shoulder")
            name = p.name.lower()
            air = self.has(f, "airborne")
            if "wing" in name:
                out.append(self._wing_way(f, p))
            elif region == "shoulder" and not biped and any("wing" in x.lower() for x in f.parts):
                # a bird's shoulder is the root of her wing: she guards it, she doesn't limp on it
                out.append(f"favors her {name}, the wing on that side held a little stiff" if p.damage < 300 else
                           f"guards her {name}, the wing on that side dragging")
            elif air and not arm and region != "tail":
                # up in the air there is no weight to keep off a leg: she holds it up out of the way
                out.append(f"holds her {name} tucked up stiffly under her as she flies" if p.damage < 300 else
                           f"her {name} hangs stiff under her as she flies, held clear of everything")
            elif region == "tail" and "flame" in name:
                # a flame on the tail's tip is not a limb to hold close: it burns low
                out.append(f"keeps her tail low and still, the flame on it burning small" if p.damage < 300 else
                           f"her tail drags, the flame on it shrunk to a weak, sputtering flicker")
            elif region == "tail":
                out.append(f"keeps her {name} stiff and close" if p.damage < 300 else f"her {name} drags, barely moving")
            elif p.damage < 150:
                out.append(f"favors her {name}" + (" (guards it close)" if arm else " (a slight limp)"))
            elif p.damage < 300:
                out.append(f"guards her {name}, using it only when she must" if arm else f"limps badly, keeping weight "
                                                                                   f"off her {name}")
            else:
                out.append(f"keeps her {name} tucked in, unusable" if arm else f"won't put any weight on her {name}")
        return out[:3 if self._decay("origin_beats", 4) else 5]

    def _big_wounds(self, f):
        """The few wounds that matter most: the biggest single hits she has taken (narration.notes_decay.big_hit),
        so the story gives them more weight than the rest. A short line in the notes; no check depends on it."""
        cfg = (self.rules.get("narration") or {}).get("big_wounds") or {}
        if not cfg.get("enabled", True):
            return ""
        big = sorted(((n, v) for n, v in (f.learned.get("big_hits") or {}).items() if n in f.parts),
                     key=lambda kv: -kv[1][1])[:int(cfg.get("max", 3))]
        if not big:
            return ""
        return ("\n   the wounds that matter most (the hardest single hits she has taken; they weigh on her more than the "
                "rest, in how she moves, what she guards and what she thinks about): "
                + ", ".join(f"{n} ({src})" for n, (src, _) in big))

    def breakable_parts(self, f):
        """Parts whose bones may break: devastated, on a fighter whose overall health is below the limit."""
        cfg = self.rules.get("narration", {}).get("bone_break", {})
        if f.eliminated or f.health >= float(cfg.get("max_health", 0)):
            return []
        need = float(cfg.get("min_part_damage", 300))
        soft = [str(w).lower() for w in cfg.get("boneless", [])]     # (no bone in a stomach or a fin to break)
        return [p.name for p in f.parts.values() if p.damage >= need and not self.BONELESS.search(p.name)
                and not any(re.search(r"\b" + re.escape(w) + r"s?\b", p.name.lower()) for w in soft)]

    # parts with no bone in them to break (soft belly, the throat's cartilage, ears, fins, a nose)
    BONELESS = re.compile(r"\b(?:belly|stomach|midsection|throat|ears?|eyes?|nose|fins?|lips?|sac|wattle)\b", re.I)

    def condition_summary(self):
        """Words-plus-numbers summary for the narrator. Overall strength is relative to each fighter's own max,
        and it decides what they can still DO; part pain decides how each part feels."""
        lines = []
        for f in self.fighters.values():
            if f.eliminated:
                st = self.recovery_stage(f)
                fc = self.facing_of(f.name)
                lies = (f" She is {self.FACING_LOOK[fc]}; she stays {'that way' if fc == 'sitting up' else 'lying that way'} until she's moved or gets up."
                        if fc in self.FACING_LOOK else "")
                if self.winner():
                    lines.append(f"{f.name}: lost the match. Now {st['label'].upper()}: {st['look']}.{lies}")
                else:
                    lines.append(f"{f.name}: OUT of the fight ({st['label']}), off to one side. She plays no part in the "
                                 f"fight now: nobody watches for her, worries about her, or mentions her.")
                continue
            ob = self._decay("origin_beats", 4)

            def _origin(p, f=f):
                # how it was done matters while it is fresh; a part left alone for a while is just its pain level
                # (narration.notes_decay.origin_beats)
                if self._stale(f, p.name, ob):
                    big = (f.learned.get("big_hits") or {}).get(p.name)
                    return f"; the worst of it from {big[0]}" if big else ""
                src = self.injury_causes(f"{f.name}|{p.name}")
                return f"; from {', then '.join(src)}" if src else ""
            # a part gone NUMB (numbness) is still wrecked, but for now she barely feels it: the story must know
            hurt = [f"{p.name} ({tier_for(p.damage, pain_tiers(self.rules))['label']}"
                    + (", but NUMB for now: she can barely feel it, and the pain will come back" if int(getattr(p, "numb", 0) or 0) > 0 else "")
                    + f"{_origin(p)})"
                    for p in sorted(f.parts.values(), key=lambda p: -p.damage) if p.damage >= 30]
            fresh = [p.name for p in f.parts.values() if p.damage < 10]
            words, ht = self.strength_words(f)
            fc = self.facing_of(f.name)
            ground = " Right now she is " + self.posture_text(f.name)
            if f.name in self.downed:
                ground += (f": {self.FACING_LOOK[fc]}" if fc in self.FACING_LOOK else "") + "."
            elif self.pinning(f.name):
                ground += "."
            else:
                ground += ": she is NOT on the ground, not lying down, not under anyone, and nobody is standing over her."
            ground += self.status_words(f)
            favor = self.favoring(f)
            if favor:
                ground += " MOVES LIKE THIS EVERY BEAT: " + "; ".join(favor) + "."
            breakable = self.breakable_parts(f)
            if breakable:
                ground += (f" Past her limit, so these devastated parts CAN BREAK (broken bones allowed): "
                           f"{', '.join(breakable)}.")
            react = self.tier_reaction(f, ht)
            if self.winner():
                # the match is over: what could still put her out in the fight no longer applies
                react = re.sub(r"\s*Only a completed pin puts her out\.", "", react)
            elif self.submission_match():
                # (a submission match: no pin ends it, a tap-out or a pass-out does)
                react = re.sub(r"Only a completed pin puts her out\.", "Only a tap-out or a pass-out ends it.", react)
            lines.append(f"{f.name}: OVERALL {words} -> what this fighter can still do: {react}{ground}\n"
                         f"   painful parts (they hurt and get favored, but do NOT override overall strength): "
                         f"{', '.join(hurt[:10]) or 'nothing serious'}"
                         + (f"\n   barely touched so far: {', '.join(fresh[:6 if self._decay('origin_beats', 4) else 12])}" if hurt and fresh else "")
                         + self._big_wounds(f))
        if not self.pins:
            lines.append("PINS: none. Nobody is pinned or held down for a count right now." + self.pin_end_note())
        for p in self.pins.values():
            who = self.pin_members(p)
            lines.append(f"PIN: {' and '.join(who)} {'is' if len(who) == 1 else 'are BOTH'} pinning {p['defender']} "
                         + (f"(no clock: {p['defender']} {self._fade_clause(float(p.get('fade', 0.0)), self.strength(self.get(p['defender'])))})"
                            if self.fade_mode() else f"({p['seconds']} of {p['duration']} seconds)")
                         + (": a double pin, both pressing at once." if len(who) > 1 else "."))
        if self.holds:
            lines.append("HOLDS (still gripping): " + "; ".join(f"{h.attacker} has {poss_word(h.defender)} {h.part}"
                                                               + (f" ({h.with_part})" if h.with_part else "")
                                                               for h in self.holds.values())
                         + ". No other grip is on: nothing else is wrapped around, clamped on, or holding anyone.")
        else:
            lines.append("HOLDS: none. Nobody is biting, gripping, or holding anyone right now; earlier bites let go.")
        if self.sides_text():
            lines.append("SIDES: " + self.sides_text())
        return "\n".join(lines)

    def weather_text(self):
        w = getattr(self, "weather", {}) or {}
        if not w:
            return ""
        word = (self.rules.get("weather") or {}).get(w["kind"], {}).get("word", w["kind"])
        return (f"WEATHER: {word.upper()} over the arena ({w['beats']} more beat{'s' if w['beats'] != 1 else ''}; "
                f"called by {w['by']}): it is part of every moment until it clears.")

    def hurt_where_text(self, n=6):
        """WHAT HURT WHERE: each fighter's worst parts and what did it, so a remembered hurt lands on the part it
        really hit (not "where her kick had landed" on a forearm the kick never touched)."""
        rows = []
        for f in self.active():
            bad = sorted((p for p in f.parts.values() if p.damage >= 30), key=lambda p: -p.damage)[:n]
            bits = []
            for p in bad:
                srcs = self.injury_causes(f"{f.name}|{p.name}")
                srcs = [re.sub(r"(\S+) (escape|struggle)$", r"\1 blow breaking out of a hold", c) for c in srcs]
                if srcs:
                    bits.append(f"{p.name.lower()} ({' and '.join(srcs)})")
            if bits:
                rows.append(f"{f.name}: " + "; ".join(bits))
        return ("WHAT HURT WHERE (a memory of an old hurt goes on the part it really hit, by what really hit it): "
                + " | ".join(rows)) if rows else ""

    def narrator_condition(self):
        text = self.condition_summary() + ("\n" + self.weather_text() if getattr(self, "weather", None) else "")
        for extra in (self.wear_text(), self.movement_text(), self.hurt_where_text(), self.gap_text()):
            if extra:
                text += "\n" + extra
        if getattr(self, "arena_marks", None):
            text += ("\nTHE PLACE NOW (what the fight has done to it; it stays this way): "
                     + "; ".join(self.arena_marks))
        if self.winner():
            text += "\n" + self.injury_report()
            summary = self.fight_summary(for_story=True)
            if summary:
                text += "\n" + summary
        return text + (f"\nPOSITIONS (where everyone is after this beat; the CAPITALS are certain): "
                       f"{self.positions_now(include_out=bool(self.winner()))}")

    snapshot = condition_summary

    def momentum_counts(self, last=8):
        recent = [m.split(">")[0] for m in self.momentum[-last:]]
        return {f.name: recent.count(f.name) for f in self.active()}, len(recent)

    def director_view(self):
        """Full numbers for the director, so it can pick smart targets. It still never calculates."""
        lines = [self.weather_text()] if getattr(self, "weather", None) else []
        multi_team = any(f.team != f.name for f in self.fighters.values())
        for f in self.fighters.values():
            if f.eliminated:
                lines.append(f"{f.name} — ELIMINATED (cannot act or be targeted; {self.recovery_stage(f)['label']})")
                continue
            words, ht = self.strength_words(f)
            team = f" [team {f.team}]" if multi_team else ""
            lines.append(f"{f.name}{team} [{'/'.join(f.types) or 'no type'}] — OVERALL: {words}. "
                         f"(Compare fighters by this percentage only: each fighter's full strength is 100%.) "
                         f"— {f.description}")
            if f.moves:
                def _m(m, f=f):
                    left = f.move_uses.get(m["name"])
                    tag = "" if left is None else (", USED UP" if left <= 0 else f", {left} left")
                    if m.get("target") not in ("self",) and self.energy_cost(m) > f.energy:
                        tag += f", TOO TIRED for it now (costs {self.energy_cost(m):.0f} energy, she has {f.energy:.0f})"
                    fx = []
                    for x in m.get("effects", []):
                        fx.append(f"{x['status'] if x.get('status') else x.get('launch')} {x.get('chance', 1) * 100:.0f}%")
                    learned = ", lent for this fight" if m.get("learned") else ""
                    rng_word = ("on herself or the arena" if m.get("target") == "self" else
                                "ranged" if self.is_ranged(m) else "close")
                    if m.get("carry"):
                        rng_word += ", needs her in the air"
                    if m.get("sustainable"):
                        rng_word += ", sustainable"
                    return (f"{m['name']} ({m['type']}, {m.get('target', 'targeted')}, {rng_word}{tag}"
                            + (f"; {', '.join(fx)}" if fx else "") + f"{learned})")
                lines.append("   moves: " + "; ".join(_m(m) for m in f.moves))
            lines.append("   body (resistance%/damage%): " + ", ".join(
                f"{p.name} {p.resistance:.0f}/{p.damage:.0f}" for p in f.parts.values()))
            st = ", ".join(f"{k} ({v})" for k, v in f.status.items())
            lines.append(f"   energy {f.energy:.0f}/100" + (f"; status: {st}" if st else "")
                         + ("; FLINCHED: cannot attack this beat" if self.has(f, "flinched") else "")
                         + ("; REELING from the charge: cannot start or join a pin this beat" if self.has(f, "reeling") else "")
                         + f"; dodges about {self.dodge_chance(f, f) * 100:.0f}% of single-target attacks")
            ok, why = self.pin_allowed(f.name)
            fc = self.facing_of(f.name)
            ground = ("ON THE GROUND" + (f" ({self.FACING_LOOK[fc]}; pin contacts must match: "
                                         + ("press her back, hips, back of the neck, not her chest" if fc == "face-down"
                                            else "press her chest, belly, throat, not her back" if fc == "face-up"
                                            else "press the exposed side") + ")" if fc else "")
                      if f.name in self.downed else self.posture_text(f.name, short=True))
            on_top = self.pinned_by(f.name)
            if on_top:
                ground += (f", PINNED under {on_top[0]} (she can only 'struggle' or strike {on_top[0]}; she can't be "
                           f"thrown, launched, picked up, or knocked down while pinned)")
            lines.append(f"   {ground}; can be pinned now: " + ("YES" if ok else f"NO ({why})")
                         + f"; if pinned, she'd break out on about {self.escape_base(f) * 100:.0f}% of her tries")
            if self._health_pct(f) < 0 and ((self.rules.get("health") or {}).get("collapse") or {}).get("enabled", True):
                lines.append(f"   BELOW ZERO ({self._health_pct(f):.0f}%): running on nothing; at the end of a beat on her "
                             f"feet her body may give out and collapse on its own (rolled), and she can get up again")
            gw = self.guarded_wound(f)
            if gw:
                ow = self.open_side_word(gw[0])
                lines.append(f"   GUARDING her {gw[0]} (blows there land lighter)"
                             + (f"; her {ow}{' side' if ow in ('left', 'right') else ''} is open (blows there land harder)"
                                if ow else ""))
            opn = [st.replace("_", " ") for st in ("doubled_over", "off_balance", "staggered", "dazed", "flinched")
                   if self.has(f, st)]
            if opn:
                lines.append(f"   CAUGHT OPEN ({', '.join(opn)}): anything that lands on her now lands harder")
            if any("wing" in p.lower() for p in f.parts):
                lines.append("   IN THE AIR (only ranged moves reach her from the ground, but another flyer up there "
                             "can strike her with close moves as they pass; her close moves on a fighter below are "
                             "dives; she can't be held or pinned)" if self.has(f, "airborne") else
                             ("   can take off ('reposition': 'take off' on her own action)"
                              + (f", but her wing is badly hurt: it costs {self.takeoff_cost(f):.0f} energy and tears "
                                 f"worse every beat she stays up" if self.wing_damage(f) >= float(
                                     ((self.rules.get('flight') or {}).get('strain') or {}).get('from', 100)) else "")
                              ) if self.can_fly(f) else
                             f"   grounded: {self.can_fly(f, why=True)}")
            if self.ko_only() and not f.eliminated:
                kc = self._ko_only_chance(f, float((self.rules.get("finish") or {}).get("decent_loss_pct", 4)), False)
                lines.append(f"   ONLY A KNOCKOUT ENDS THIS FIGHT: "
                             + ("no pins at all in this fight" if self.no_pins() else
                                "a pin wears her down but can't finish her")
                             + (f"; she is low enough now that a hard blow may knock her out cold (about "
                                f"{kc * 100:.0f}% for a solid hit)" if kc > 0 else
                                "; she is too strong yet to be knocked out"))
            sec, why_not = self.pin_securable(f)
            if not sec and not self.ko_only():
                lines.append(f"   a pin on {f.name} probably can't be WON yet ({why_not}): she escapes far more easily "
                             f"and usually kicks out at the last second. "
                             f"Wear her down more (spread the damage) before pinning for the win.")
        counts, n = self.momentum_counts()
        if n:
            lines.append(f"MOMENTUM (who made the last {n} attacks): "
                         + ", ".join(f"{k} {v}" for k, v in counts.items()))
        if self.holds:
            lines.append("ACTIVE HOLDS:")
            for h in self.holds.values():
                in_pin = any(p["defender"] == h.defender for p in self.pins.values())
                odds = self.hold_break_chance(h.attacker, h.defender) if not in_pin else 0
                lines.append(f"   hold_id {h.id}: {h.attacker} has {poss_word(h.defender)} {h.part} — "
                             f"\"{h.flavor}\" (power {h.power}, held {h.turns_active} beats"
                             + (f"; the engine rolls each beat whether {h.defender} breaks it: about {odds * 100:.0f}% now"
                                if odds > 0 else "") + ")"
                             + (f" — a GRAB: both on their feet at point-blank, NEITHER can dodge the other. {h.attacker} "
                                f"can pummel her (a strike with \"count\" 2-4 and a close move), hold a stream on her "
                                f"(\"sustain\"), or throw or slam her with no slip; {h.defender} can hit back just as "
                                f"surely. Don't start the grab again: it is already on."
                                if h.grab and self.grab_between(h.attacker, h.defender) else ""))
        else:
            lines.append("ACTIVE HOLDS: none")
        if self.sides_text():
            lines.append("SIDES (the engine refuses attacks between fighters on one side): " + self.sides_text())
        lines.append(f"POSITIONS NOW (the CAPITALS come from the engine and are certain): {self.positions_now(include_out=False)}")
        if not self.pins:
            lines.append("PINS: NONE in progress. Nobody is pinned, so nobody can 'struggle', and there is no pin to "
                         "maintain." + self.pin_end_note())
        for p in self.pins.values():
            crew = self.pin_members(p)
            free = [f.name for f in self.active() if f.name not in crew and f.name != p["defender"]
                    and f.name not in self.downed and not self.pinned_by(f.name) and not self.pinning(f.name)]
            if len(crew) > 1:
                lines.append(f"DOUBLE PIN: {' and '.join(crew)} are both pinning {p['defender']} (one clock; she can "
                             f"barely move).")
            elif free and len(crew) < int(self.rules.get("pin", {}).get("max_pinners", 2)):
                lines.append(f"A SECOND PINNER MAY JOIN: {' or '.join(free)} can pile onto {p['defender']} too (action "
                             f"'pin' with her as attacker and {p['defender']} as defender, pressing parts that are "
                             f"still free): a DOUBLE PIN on the same clock, twice as hard to escape.")
            lines.append(f"PIN IN PROGRESS: {p['attacker']} is pinning {p['defender']} — "
                         + (f"beat {int(p.get('beats', 0)) + 1} of it; she is about {float(p.get('fade', 0.0)):.0f}% of "
                            f"the way to passing out (it usually takes about "
                            f"{self.rules.get('pin', {}).get('fade', {}).get('typical_beats', 6)} beats, sometimes "
                            f"more, sometimes fewer; nobody in the story knows). The engine rolls {poss_word(p['defender'])} "
                            if self.fade_mode() else
                            f"{p['seconds']} of {p['duration']} seconds. The engine runs the clock and rolls "
                            f"{poss_word(p['defender'])} ")
                         + f"struggles every beat. Keep it going with 'breather' (or 'hold_adjust' to bear down); "
                         f"the pinner does NOT start another pin. {p['defender']} may also strike {' or '.join(crew)} with a free limb.")
        gap = self.gap_text(now_only=True)
        if gap:
            lines.append(gap)
        return "\n".join(lines)

    # ---------- save / load ----------
    def save(self, path, extra=None):
        data = {"turn": self.turn, "next_hold_id": self.next_hold_id, "scene": self.scene,
                "scene_name": self.scene_name, "last_event": self._last_event, "pins": self.pins,
                "positions": self.positions, "downed": self.downed, "since_pin": self.since_pin,
                "last_pin_end": self.last_pin_end, "injury_log": self.injury_log, "plan": self.plan,
                "injury_amt": self.__dict__.get("injury_amt") or {},
                "tally": self.tally, "momentum": self.momentum, "facing": self.facing, "move_log": self.move_log,
                "last_reposition": getattr(self, "_last_reposition", {}), "alliances": self.alliances,
                "weather": getattr(self, "weather", {}), "arena_marks": getattr(self, "arena_marks", []),
                "broken_props": list(getattr(self, "broken_props", []) or []),
                "chronicle": getattr(self, "chronicle", None) or self.new_chronicle(),
                "setups": self.__dict__.get("setups") or [],
                "more": self._saveable_extra(),
                "event_rng": _to_json(self.event_rng.getstate()),
                "extra": extra or {},
                "fighters": {k: {**asdict(f), "parts": {n: asdict(p) for n, p in f.parts.items()}}
                             for k, f in self.fighters.items()},
                "holds": {i: asdict(h) for i, h in self.holds.items()}}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    def _saveable_extra(self):
        """The state kept outside the main fields (_SNAP_EXTRA: who is encouraged, how a fighter went out...) that
        can go into a save (sets written so they come back as sets). Anything that still can't is left out, and said:
        a loaded fight starts without it."""
        out = {}
        for k in self._SNAP_EXTRA:
            if k in self.__dict__:
                try:
                    v = _to_json(self.__dict__[k])
                    json.dumps(v)
                    out[k] = v
                except (TypeError, ValueError) as e:
                    print(f"[save: {k} could not be written ({e}); a loaded fight starts without it]")
        return out

    @staticmethod
    def _known(cls, d):
        """Only the fields this build's dataclass has: a save from a newer build (or a hand-edited one) still loads."""
        names = set(cls.__dataclass_fields__)
        return {k: v for k, v in d.items() if k in names}

    def load(self, path):
        data = load_json(path)
        self.turn, self.next_hold_id = data["turn"], data["next_hold_id"]
        self.scene = data.get("scene", self.scene)
        saved = data.get("scene_name")
        if saved and saved in self.scenes:
            self.set_scene(saved)
        elif saved == "custom" or (not saved and self.scene != self.scene_cfg.get("text")):
            keep = self.scene
            same = next((k for k, v in self.scenes.items() if v.get("text") == keep), None)
            self.set_scene(same or keep)   # an older save: the arena it was fought in, by its text
        self._last_event = data.get("last_event")
        self.fighters = {}
        for k, fd in data["fighters"].items():
            parts = {n: BodyPart(**self._known(BodyPart, p)) for n, p in fd.pop("parts").items()}
            self.fighters[k] = Fighter(**self._known(Fighter, fd), parts=parts)
        self.holds = {int(i): Hold(**self._known(Hold, h)) for i, h in data["holds"].items()}
        self.pins = data.get("pins", {})
        self.positions = data.get("positions", "")
        self.downed = data.get("downed", {})
        self.facing = data.get("facing", {})
        self.move_log = [tuple(x) for x in data.get("move_log", [])]
        self._last_reposition = data.get("last_reposition", {})
        self._fresh_down, self._fresh_status, self._knock_on = set(), set(), []
        self.repair_state()  # a save from an older build may hold a posture this build wouldn't allow
        self.since_pin = data.get("since_pin", {})
        self.momentum = data.get("momentum", [])
        self.last_pin_end = data.get("last_pin_end", {})
        self.injury_log = data.get("injury_log", {})
        self.injury_amt = data.get("injury_amt", {})
        self.tally = {k: int(v) for k, v in (data.get("tally") or {}).items()}
        self.plan = data.get("plan", {})
        self.alliances = data.get("alliances", [])
        self.weather = data.get("weather", {})
        self.arena_marks = data.get("arena_marks", [])
        if data.get("broken_props"):
            self.broken_props = list(data["broken_props"])
        else:
            self.__dict__.pop("broken_props", None)   # (none broken: as a fight that never broke one)
        self.chronicle = {**self.new_chronicle(), **(data.get("chronicle") or {})}
        self.setups = list(data.get("setups") or [])
        self.pressed, self._pending_events, self.pin_window = {}, [], {}
        # put back what the save kept; drop what this fight had that the save didn't (an older save: last_event and
        # broken_props have fields of their own, read above)
        self._put_back_extra(data.get("more") or {}, keep=("broken_props", "_last_event"))
        if data.get("event_rng"):
            st = data["event_rng"]
            try:
                self.event_rng.setstate((st[0], tuple(st[1]), st[2]))
            except (TypeError, ValueError, IndexError):
                pass     # (a hand-edited save: the arena's dice simply start fresh)
        return data.get("extra", {})
