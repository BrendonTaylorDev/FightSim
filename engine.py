"""
Combat engine: the single source of truth for every number in the fight.
The models never calculate anything. The director picks moves, the narrator writes prose,
and the stat block you see is printed straight from here.
"""
import copy
import difflib
import json
import os
import random
import re
from dataclasses import dataclass, field, asdict


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
    (("neck", "throat", "collar", "sac"), ["neck", "throat", "flotation sac"]),
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
                self.settings_applied = merge_settings(self.rules, load_json(mine))
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
        self.plan = {}         # the author's nudges: shape (close/dominate/comeback), winner, targeting
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
                    move_uses={m["name"]: int(m["uses"]) for m in fd.get("moves", []) if m.get("uses")})
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
    def _apply_damage(self, defender, part_name, power, cap=None):
        """One instance of damage, using the bracket rules. Returns every number involved. cap: {"mult", "health_mult"}
        upper limits on the bracket's multipliers (a pin's steady pressure doesn't tear into a worn part the way a
        blow does: pin.pressure_cap)."""
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
        capped = False
        if cap:
            if cap.get("mult") is not None and bmult > float(cap["mult"]):
                bmult, capped = float(cap["mult"]), True
            if cap.get("health_mult") is not None and hmult > float(cap["health_mult"]):
                hmult, capped = float(cap["health_mult"]), True
        taken = power * bmult * scale
        p.damage = dmg_b + self._part_added(dmg_b, taken)
        was_numb = int(getattr(p, "numb", 0) or 0) > 0
        rscale = float(r.get("damage", {}).get("resistance_scale", 1.0))
        # resistance lost: by the blow's power, and (resistance.loss_per_damage, 0 = off) by the damage it really did,
        # so a part that takes a great deal of damage also softens faster
        wear = power * r["resistance"]["loss_per_power"] + taken * float(r["resistance"].get("loss_per_damage", 0) or 0)
        wear = wear * rscale
        cap_res = float(r["resistance"].get("max_loss_per_hit", 0) or 0)
        rel = r["resistance"].get("relative") or {}
        start_r, sound = float(getattr(p, "start_resistance", 0) or 0), float(rel.get("sound", 85))
        if rel.get("enabled", True) and 0 < start_r < sound:
            # a part that starts low wears in proportion to what it has: its CONDITION falls at much the pace of a
            # sound part's (a little faster, by wear_exp), and the per-hit cap counts in condition too
            share = start_r / sound
            wear *= share ** float(rel.get("wear_exp", 0.6))
            cap_res = cap_res * share if cap_res > 0 else 0.0
        if cap_res > 0 and wear > cap_res:
            wear = cap_res   # resistance.max_loss_per_hit: no single blow, however devastating, wears a part past this
        p.resistance = max(r["resistance"]["minimum"], res_b - wear)
        # health lost: damage x loss_per_damage_point x the bracket's health_mult (a soft, worn-down part costs more)
        # x how much the part matters to the whole body (health.part_weights: a throat far more than an ear)
        vital = self.part_weight(p.name)
        raw_loss = taken * r["health"]["loss_per_damage_point"] * hmult * vital
        health_loss = self._soften_loss(defender, raw_loss)
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
            log = self.injury_log.setdefault(f"{defender.name}|{p.name}", [])
            if not log or log[-1] != self._source:
                log.append(self._source)
                del log[:-4]
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
            "capped": capped,
            "scale": scale,
            "res_scale": rscale,
            "damage_taken": round(taken, 2),
            "damage_before": round(dmg_b, 2), "damage_after": round(p.damage, 2),
            "damage_added": round(p.damage - dmg_b, 2),
            "res_before": round(res_b, 2), "res_after": round(p.resistance, 2),
            "res_start": round(float(getattr(p, "start_resistance", res_b) or res_b), 2),
            "cond_before": round(cond_b, 2), "cond_after": round(self.condition(p), 2),
            "health_mult": hmult, "vital": vital, "health_loss": round(health_loss, 2),
            "health_raw": round(raw_loss, 2), "softened": round(raw_loss - health_loss, 2) > 0.01,
            "res_overflow": round(res_over, 2),
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

    def _soften_loss(self, defender, raw):
        """health.soft_cap: a hit on a ruined part costs a lot of health, but no single blow and no single beat swings
        wildly. Health lost past per_hit (a share of HER OWN full health) by one hit, and past per_beat by everything
        that lands on her in one beat, counts at `above` (0.3 = 30%). Smooth: nothing changes below the limits."""
        cfg = self.rules.get("health", {}).get("soft_cap") or {}
        if not cfg.get("enabled", True) or raw <= 0 or not defender.max_health:
            return raw
        k = max(0.0, min(1.0, float(cfg.get("above", 0.3))))
        dv = getattr(self, "_dev_active", None)
        dcfg = (self.rules.get("moves") or {}).get("devastating") or {}
        if dv:    # a devastating blow is ALLOWED to swing the fight: the cap is much looser for it
            k = max(k, float(dcfg.get("cap_above", 0.7)))
        squash = lambda x, cap: x if cap <= 0 or x <= cap else cap + (x - cap) * k
        loss = squash(raw, float(cfg.get("per_hit", 0.05)) * defender.max_health
                      * (float(dcfg.get("cap_mult", 3.0)) if dv else 1.0))
        tally = self.__dict__.setdefault("beat_loss", {})
        before = tally.get(defender.name, 0.0)
        cap = float(cfg.get("per_beat", 0.12)) * defender.max_health * (float(dcfg.get("cap_mult", 3.0)) if dv else 1.0)
        out = squash(before + loss, cap) - squash(before, cap)
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
                              {**getattr(self, "_last_reposition", {}),
                               **{"by:" + k: v for k, v in getattr(self, "_last_manhandle", {}).items()}},
                              self._fresh_down, self._fresh_status,
                              self.pressed, self.alliances, self._pending_events, list(getattr(self, "rolls", [])),
                              self.tally, getattr(self, "weather", {}), list(getattr(self, "arena_marks", [])),
                              getattr(self, "chronicle", None) or self.new_chronicle(),
                              list(self.__dict__.get("setups") or []), self.rng.getstate(),
                              {k: self.__dict__.get(k) for k in self._SNAP_EXTRA if k in self.__dict__}))

    # engine state that lives outside the main snapshot tuple but must be undone with it
    _SNAP_EXTRA = ("broken_props", "broke_free_at", "hit_turn", "hauled", "aim_log", "weak_aim")

    def restore_state(self, snap):
        self.beat_loss = {}   # a beat taken back takes its health.soft_cap tally with it
        (self.fighters, self.holds, self.next_hold_id, self.turn, self.involved,
         self.pins, self.positions, self.downed, self.since_pin, self.momentum, self.move_log, self.last_pin_end,
         self.injury_log, self.plan, self.facing, self._last_reposition, self._fresh_down, self._fresh_status,
         self.pressed, self.alliances, self._pending_events, self.rolls, self.tally, self.weather, self.arena_marks,
         self.chronicle, self.setups, rng, *more) = copy.deepcopy(snap)
        extra = more[0] if more else {}
        for k in self._SNAP_EXTRA:      # state added later than the tuple: put back what was there, drop what wasn't
            if k in extra:
                self.__dict__[k] = extra[k]
            else:
                self.__dict__.pop(k, None)
        self._last_manhandle = {k[3:]: v for k, v in self._last_reposition.items() if k.startswith("by:")}
        self._last_reposition = {k: v for k, v in self._last_reposition.items() if not k.startswith("by:")}
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
        "charge_falls": {"on her side": 30, "face-down": 25, "face-up": 15, "sitting up": 30},
        "dodge": {"sidestep": 4, "duck": 3, "spring_back": 3, "turn_aside": 2, "twist": 2},
        "hold_break": {"wrench": 3, "pry": 2, "slip": 2, "shove": 2},
        "tumble": {"rolling": 4, "skidding": 3, "bouncing": 2, "cartwheeling": 2},
        "hold_strain": {"pry": 3, "twist": 3, "claw": 2, "brace": 2},
        "struggle": {"buck": 3, "bridge": 3, "twist": 3, "limb": 3, "kick": 2, "squirm": 2, "headbutt": 2,
                     "bite": 2, "shrimp": 2, "roll": 2, "claw": 2, "pry": 2, "tuck": 2, "limp": 1, "reach": 1,
                     "power": 1},
        "getup_fail": {"gives_out": 4, "slips": 2, "dizzy": 2, "breath": 2},
        "getup_rise": {"push": 4, "roll": 2, "lean": 3, "lurch": 2},
        "takedown": {"tackle": 3, "leg_hook": 3, "sweep": 3, "hip_throw": 3, "shoulder_drive": 2, "drag_down": 2,
                     "spin_down": 2, "trip_back": 2, "pull_forward": 2, "ride_down": 2},
    }

    def vary(self, key):
        """Pick HOW an already-decided outcome plays out (one of several ways that are all true to the result)."""
        table = dict(self.VARIETY.get(key, {}))
        over = self.rules.get("variety", {}).get(key)
        if isinstance(over, dict):
            table = {k: float(v) for k, v in over.items() if not str(k).startswith("_") and float(v) > 0} or table
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
        extras = self.power_extras(a, d, move["type"])
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
            extras = extras + [("diving from above", float((self.rules.get("flight") or {}).get("dive_mult", 1.3)))]
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
                "extras": extras, "extra_mult": xm}

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

    def improvised_move(self, name, mtype, severity, target="targeted", about=""):
        """A move the director invents on the spot. Power comes from how hard it lands."""
        table = self.rules.get("moves", {}).get("improvised_power", {"light": 15, "solid": 25, "heavy": 35, "brutal": 45})
        sev = str(severity or "solid").lower()
        sev = {"firm": "solid", "crushing": "heavy"}.get(sev, sev)
        chart = self.rules.get("moves", {}).get("type_chart", {})
        mtype = next((t for t in chart if t.lower() == str(mtype or "Normal").lower()), "Normal")
        name = " ".join(str(name or "improvised strike").split()[:5]).title()
        return {"name": name, "type": mtype, "power": table.get(sev, table.get("solid", 25)),
                "target": target if target in ("targeted", "spread") else "targeted",
                "about": about or "an improvised attack", "improvised": True}

    def move_attack(self, attacker, defender, move_name, parts, count=1, flavor="", move=None, no_spill=False,
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
        busy = self.busy_with(a, move)
        if enforce and busy:
            raise ValueError(f"{poss_word(a.name)} {busy[0]} are clamped on {poss_word(busy[1])} {busy[2].lower()}: she "
                             f"can't {move['name']} with them while they hold. Strike with something free, or let go "
                             f"first (hold_release)")
        if enforce and move.get("charge") and (a.name in self.downed or self.pinned_by(a.name)):
            where = "PINNED" if self.pinned_by(a.name) else "ON THE GROUND"
            raise ValueError(f"{a.name} is {where}: {move['name']} is a running, full-body charge, and she can't launch one "
                             f"from there. Use something she can do where she lies (a bite, a kick, a tail strike, a "
                             f"blast), or let her get up first")
        self._no_friendly_fire(a, [d], enforce)
        self._pinned_reach(a, [d.name], enforce)
        if enforce and self.has(d, "airborne") and not self.has(a, "airborne") and not self.is_ranged(move) \
                and move.get("target") not in ("status", "self"):
            raise ValueError(f"{d.name} is IN THE AIR: {move['name']} can't reach her up there. Use a ranged move (a "
                             f"beam, a blast, a stream), or wait for her to dive")
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
        math = self.move_math(a.name, d.name, move)
        spiking = self.spike_ok(a, d, move)
        self._sustain_now = 0
        target = math["target"]
        if target == "self":   # a stance or a weather move: on herself or the whole arena, not on the opponent
            return self._self_move(a, d, move, flavor, energy_before)
        guard = self._guarded(a, d, move)
        if guard:
            guard["flavor"] = flavor
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
                res["status_applied"] = self._status_from_move(d, move, force_roll=True)
                res["missed"] = not res["status_applied"]
            return res
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
        dodge = None if (clash or fed) else (self.dodge_roll(a, d, target, move["name"]) if enforce else None)
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
            if hits and not move.get("improvised"):    # she remembers what has landed on her (learning)
                felt = d.learned.setdefault("moves", {})
                felt[f"{a.name}|{move['name']}"] = felt.get(f"{a.name}|{move['name']}", 0) + 1
                wcfg = (self.rules.get("learning") or {}).get("wary") or {}
                if any(h.get("damage_after", 0) >= float(wcfg.get("at_damage", 150)) for h in hits):
                    d.learned.setdefault("wary", {})[f"{a.name}|{move['name']}"] = True   # that one hurt her badly
        sustained = None
        if hits and int(sustain or 0) > 1 and move.get("sustainable"):
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
            ground = self._grind(a, d, behind, min(max(1, int(count or 1)) if pummel or int(count or 1) > 1 else 1, 4))
            hits = hits + ground["hits"]
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
        if fe:
            res["feint"] = fe
        if self._overcommit_now:
            res["overcommit"] = True
            self.set_status(a, "off_balance", 1)      # she overbalances on it
        self._overcommit_now = None
        if self._last_stand_now and hits:
            res["last_stand"] = True
            a.energy = 0.0          # everything she had left went into it
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
            if charged:
                res["charge"] = charged
                res["knock_on"] = (res.get("knock_on") or []) + (charged.get("knock_on") or [])
            if still_against:
                res["target_against"] = still_against
            mouth = self._into_mouth(a, d, move, hits, bool(sustained))
            if mouth:
                res["into_mouth"] = mouth
            blocked = bool(guard and guard.get("kind") == "block")   # a blocked blow passes on no status
            res["status_applied"] = ((self._status_from_move(d, move) if not blocked else [])
                                     + self._restrain(a, d) + (mouth or [])
                                     + list((res.get("charge") or {}).get("hazard_status") or [])
                                     + list((res.get("sustain") or {}).get("hazard_status") or []))
            launch = self._launch_from_move(move)
            if launch:
                res["auto_launch"] = launch
            fcfg = self.rules.get("flight") or {}
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
                        + float(kfa.get("per_damage", 0.004)) * sum(h.get("damage_taken", 0) for h in hits)
                        + float(kfa.get("per_wing_damage", 0.0025)) * self.wing_damage(d))
                    if self.has(d, "airborne") and not res.get("carried") and not d.eliminated else 0.0)
            if fall > 0 and self._chance(fall, f"{d.name} knocked out of the air", "she falls", "she stays up"):
                # hit in the air with nothing under her: the blow knocks her out of the sky (harder, the more it hurt
                # and the worse her wings are: flight.knock_from_air)
                d.status.pop("airborne", None)
                res["grounded"] = True
                res["grounded_wing"] = self.wing_damage(d) >= float((fcfg.get("strain") or {}).get("from", 100))
                res["auto_launch"], res["drop_severity"] = res.get("auto_launch") or "thrown", res.get("drop_severity") or "solid"
        if hits and not d.eliminated:
            jolt = self._jolts(d, hits)
            if jolt:
                res["status_applied"] = (res.get("status_applied") or []) + jolt
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
        elif self.has(a, "airborne") and not self.is_ranged(move) and not self.has(d, "airborne") \
                and move.get("target") not in ("status", "hold") and not move.get("carry"):
            if (getattr(self, "_juggle", None) or {}).get("who") == d.name:
                res["dive"], res["climbs"] = True, True    # she struck her in the air: there is no one to catch her
            else:
                self._after_dive(a, d, res, bool(hits))
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
        back = self.landing_parts(d.name, 3, avoid=struck)
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

    def scene_word(self, key, default=None):
        """A word the notes use for this arena: place, ground, rough, slick, ambience."""
        return self.scene_cfg.get(key) or default or {"place": "the arena", "ground": "the ground",
                                                       "rough": "the rough ground", "slick": "the ground",
                                                       "ambience": ""}.get(key, "")

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

    def _grind(self, a, d, against, blows):
        """Blows landed while she is held or pressed against the scenery (a pummel against a tree, a strike that pins
        her to the wall): each one also drives her back into it (moves.grind: power, break_mult). If it breaks, a heavy
        extra hit and she goes down with it."""
        cfg = (self.rules.get("moves") or {}).get("grind") or {}
        against = short_phrase(against)
        table = self.rules["severity"].get("environment") or self.rules["severity"]["instant"]
        back = self.landing_parts(d.name, 2)
        brk = self.break_chance(against, ((self.rules.get("moves") or {}).get("sustain") or {}).get("break_chance", {})) \
            * float(cfg.get("break_mult", 0.5))
        out = {"against": against, "blows": blows, "hits": [], "surface_hits": [], "break_hits": [], "broke": False,
               "hazard_status": self.hazard_effects(d, [against])}
        for i in range(1, blows + 1):
            self._source = f"being driven into {against}"
            sh = [self._apply_damage(d, p, float(table.get(cfg.get("power", "light"), 10))) for p in back[:1 + (i == 1)]]
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
        pulses = max(1, min(int(cfg.get("max_pulses", 4)), pulses))
        mult = float(cfg.get("pulse_mult", 0.6))
        against = short_phrase(against)
        if against and self.is_broken(against):
            against = ""          # it already lies broken: nothing behind her to grind her into
        table = self.rules["severity"].get("environment") or self.rules["severity"]["instant"]
        back = self.landing_parts(d.name, 3) if against else []
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
                sh = [self._apply_damage(d, p, float(table.get("solid", 15))) for p in back]
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
        fighter who falls asleep on her feet slumps to the ground. What that knocked loose is left in _knock_on."""
        f.status[status] = max(f.status.get(status, 0), int(beats))
        self._fresh_status.add((f.name, status))
        self._knock_on = []
        if status in ("asleep", "frozen") and not f.eliminated:
            word = "fell asleep" if status == "asleep" else "froze solid"
            loose = self._lose_grip(f.name, f"{f.name} {word}")
            if status == "asleep" and f.name not in self.downed:
                self.knock_down(f.name, why=f"{f.name} {word}")
                loose += self._knock_on + [{"type": "slumps", "fighter": f.name, "facing": self.facing.get(f.name)}]
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
                  ("leg", r"kick|stomp|stamp"))

    def busy_with(self, a, move):
        """Is the one mouth she'd attack with already locked in one of her own grips (a hold, a pin's press, a
        submission)? Then that move can't be thrown. Returns (her jaws, the held fighter, the part) or None."""
        if not move or move.get("target") in ("whole_body", "status", "hold", "self"):
            return None
        text = f"{move.get('name', '')} {move.get('about', '')}".lower()
        kind = next((k for k, rx in self.LIMB_KINDS if rx and re.search(rx, text)), None)
        if kind != "bite":
            return None
        for h in self.holds.values():
            if h.attacker == a.name and re.search(r"\b(jaws?|teeth|fangs?|mouth|bite)\b", str(h.with_part or "").lower()):
                return ("jaws", h.defender, h.part)
        return None

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
        worst = max(parts, key=lambda p: p.damage)
        steps = sorted(((float(k), float(v)) for k, v in (cfg.get("at") or {"150": 0.8, "300": 0.6}).items()),
                       reverse=True)
        mult = next((m for at, m in steps if worst.damage >= at), None)
        if mult is None or mult >= 1:
            return None
        return (f"her hurt {worst.name.lower()}", mult)

    def power_extras(self, a, d, move_type):
        """Status multipliers on a move's power: (label, multiplier) pairs."""
        cfg = self._cfg("status_effects")
        out = []
        if self.has(a, "stiff"):
            out.append(("stiff from the pin", float(cfg.get("stiff_power_mult", 0.85))))
        if self.has(a, "constricted") and any(h.coil and h.defender == a.name for h in self.holds.values()):
            out.append(("arms trapped in the coils", float(cfg.get("constricted_power_mult", 0.75))))
        if self.has(a, "bound"):
            out.append((f"her {str(a.learned.get('bound_part') or 'limb').lower()} bound",
                        float(cfg.get("bound_power_mult", 0.9))))
        if self.has(a, "sputtering"):
            out.append(("choking on water", float(cfg.get("sputtering_power_mult", 0.9))))
        if self.has(a, "off_balance"):
            out.append(("off balance", float(cfg.get("off_balance_power_mult", 0.85))))
        if self.has(a, "fury"):
            out.append(("fury after the pin", float(cfg.get("fury_power_mult", 1.15))))
        if self.has(a, "breathless"):
            out.append(("the wind knocked out of her", float(cfg.get("breathless_power_mult", 0.85))))
        if self.has(a, "dazed"):
            out.append(("dazed", float(cfg.get("dazed_power_mult", 0.9))))
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

    def _status_from_move(self, d, move, force_roll=False):
        """The move's own effects (moves.json), or else the default for its type (rules.json)."""
        if d.eliminated:
            return []
        if isinstance(move, str):
            move = {"type": move}
        effs = [x for x in move.get("effects", []) if x.get("status")]
        if not effs and not move.get("effects"):
            default = self._cfg("status_effects").get("from_move_type", {}).get(move.get("type"))
            effs = [default] if default else []
        out = []
        for eff in effs:
            if self._chance(float(eff.get("chance", 0)), f"{d.name} {eff['status']} by {move.get('name', 'the move')}",
                            eff["status"], "no"):
                self.set_status(d, eff["status"], eff.get("beats", 2))
                out.append({"fighter": d.name, "status": eff["status"], "beats": int(eff.get("beats", 2)),
                            "knock_on": self._knock_on})
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
        f.energy = max(0.0, f.energy - cost)

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
               (float(sc.get("dazed_dodge_mult", 0.4)) if self.has(d, "dazed") else 1.0) * \
               (float(sc.get("doubled_over_dodge_mult", 0.5)) if self.has(d, "doubled_over") else 1.0)
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
        ch = self.dodge_chance(a, d, target)
        lcfg = self.rules.get("learning") or {}
        seen = (d.learned.get("moves") or {}).get(f"{a.name}|{move_name}", 0) if move_name else 0
        if ch > 0 and seen >= 2 and lcfg.get("enabled", True):
            ch = min(float(self._cfg("evasion").get("max", 0.35)) * 1.3,
                     ch * min(float(lcfg.get("dodge_cap", 1.5)), 1 + float(lcfg.get("dodge_per_hit", 0.2)) * (seen - 1)))
        wcfg = (self.rules.get("learning") or {}).get("wary") or {}
        wary = bool(move_name and ch > 0 and wcfg.get("enabled", True)
                    and (d.learned.get("wary") or {}).get(f"{a.name}|{move_name}"))
        if wary:      # it hurt her badly before: she flinches away from it early
            ch = min(0.6, ch * float(wcfg.get("dodge_mult", 1.25)))
        forced, self._force_dodge = bool(getattr(self, "_force_dodge", False)) and ch > 0, False
        if not forced and (ch <= 0 or not self._chance(ch, f"{d.name} dodging {poss_word(a.name)} attack", "DODGED",
                                                       "it lands")):
            return None
        out = {"dodged": True, "dodge_chance": ch, "counter_hits": [], "manner": self.vary("dodge"), "wary": wary}
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
        if not self.has(d, "flinched") and self._chance(float(cfg.get("counter_chance", 0.35)),
                                                         f"{d.name} countering after the dodge", "she counters",
                                                         "no counter"):
            reach = [p for p in a.parts if body_region(p) in ("head", "neck", "chest", "shoulder", "fore_up", "fore_low",
                                                              "belly")] or list(a.parts)
            power = self.power_for("instant", cfg.get("counter_severity", "solid"))
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
        self.pressed.pop(n, None)  # she's off whatever a charge left her against
        self.get(n).status.pop("airborne", None)  # knocked out of the air: she's down, not flying
        if n not in self.downed:
            getattr(self, "lying_at", {}).pop(n, None)  # a new fall: not at the foot of whatever she fell by before
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
            if not self._chance(chance, f"{f.name}'s drop back down hurting", "it jars her", "it doesn't hurt"):
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
        for name in list(self.downed):
            f = self.fighters.get(name.lower())
            if f is None or f.eliminated:
                self.downed.pop(name, None)
                continue
            if any(p["defender"] == name for p in self.pins.values()):
                continue  # still pinned
            if any(h.defender == name and h.sub for h in self.holds.values()):
                continue  # locked in a submission hold: she can't rise until it's off
            if name in self._fresh_down:
                # just went down this beat: no get-up roll yet (said out loud, so nobody has to guess)
                events.append({"type": "stays_down", "fighter": name, "why": "fresh", "facing": self.facing.get(name)})
                continue
            if self.has(f, "asleep") or self.has(f, "frozen"):
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
            cuts = cfg.get("thresholds", [0.7, 0.45, 0.2])
            tries = next((i + 1 for i, c in enumerate(cuts) if score >= c), None)
            if tries is None and beats >= int(cfg.get("max_beats_down", 4)):
                tries = 3  # nobody stays down forever unless pinned out
            if f.name in self.lucky:
                tries = 1  # /play dice free: she gets up at the first try
            props = self.scene_props()
            grab = self.rng.choice(props)
            # (the dice are rolled as before; but a fighter lying at the foot of something uses THAT to get up)
            grab = (getattr(self, "lying_at", None) or {}).get(name) or grab
            natural = next((i + 1 for i, c in enumerate(cuts) if score >= c), None)
            ev = {"type": "get_up", "fighter": name, "plan": plan, "grab": grab, "beats_down": beats,
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
                self.facing.pop(name, None)
                ev["rise"] = self.vary("getup_rise")
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
            impacts = impacts or [(self.scene_word("rough"), [], "light")]
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
            why = f"{d.name} was {'thrown' if thrown else 'knocked down'}"
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
                h.power = max(h.power, power)
                h.change_per_turn = change_per_turn
                asked = with_part if (with_part and h.with_part and with_part.lower() != h.with_part.lower()) else ""
                # keep_with (the director's beats): jaws that are already on her neck stay jaws; they don't turn
                # into a horn because the new pin was worded that way. Your own commands may change it.
                h.with_part = (h.with_part or with_part) if keep_with else (with_part or h.with_part)
                return {"type": "hold_start", "hold_id": h.id, "attacker": a.name, "defender": d.name,
                        "part": pname, "power": h.power, "change_per_beat": h.change_per_turn,
                        "flavor": flavor, "with": h.with_part, "existing": True,
                        "asked_with": asked if keep_with else ""}
        h = Hold(self.next_hold_id, a.name, d.name, pname, power, change_per_turn, flavor, 0, with_part)
        self.holds[h.id] = h
        self.next_hold_id += 1
        return {"type": "hold_start", "hold_id": h.id, "attacker": a.name, "defender": d.name,
                "part": pname, "power": power, "change_per_beat": change_per_turn, "flavor": flavor,
                "with": with_part, "existing": False}

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
        return move.get("target") in ("spread", "whole_body")

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
        if not self._chance(float(cfg.get("chance", 0.15)), f"{d.name} meeting {poss_word(a.name)} {move['name']} "
                            f"with one of her own", "CLASH", "no"):
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
                         ("neck", "main", {"biped": "pulled back and round by it"}),
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
                         ("tail:base", "main", {"biped": "twisted from it", "quadruped": "twisted from it"}),
                         ("back_low|back_up", "second", {"biped": "her foot, planted on it", "quadruped": "her forepaw, planted on it"})],
            "free": {"biped": "her mouth and her tails", "quadruped": "her horn"},
            "strain": "the tail hauled up and twisted from its root, the base of it wrenched"},
        "limb wrench": {
            "facing": ("face-down", "face-up", "on her side"), "by": ("quadruped",), "needs": "arm",
            "look": {"quadruped": "one forelimb clamped in her jaws and twisted and shaken, a forepaw pinning her "
                                  "shoulder down"},
            "contacts": [("arm", "main", {"quadruped": "her jaws, twisting and shaking it"}),
                         ("shoulder", "second", {"quadruped": "her forepaw, pinning it"})],
            "free": {"quadruped": "her horn and her tail"},
            "strain": "the limb twisted and shaken in her jaws, the joint wrenched against itself"},
    }

    def _sub_part(self, d, spec, used=()):
        """The defender's part for one submission contact."""
        names = [n for n in d.parts if n not in used]
        def region_of(n):
            return body_region(n)
        if spec == "legs":
            legs = [n for n in names if region_of(n) == "hind_up" and "thigh" in n.lower()] or \
                   [n for n in names if region_of(n) in ("hind_up", "hind_low")]
            return legs[:2] if len(legs) >= 2 else None
        if spec == "arm":
            ups = [n for n in names if region_of(n) == "fore_up" and "wing" not in n.lower()]
            return ups[0] if ups else None
        if spec == "leg_joint":
            j = [n for n in names if region_of(n) == "hind_low" and any(k in n.lower() for k in ("knee", "hock"))]
            return j[0] if j else None
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
                    return hit[0]
            return None
        for reg in spec.split("|"):
            hit = [n for n in names if region_of(n) == reg and not (reg == "neck" and "throat" in n.lower()
                                                                     and any("neck" in m.lower() for m in names))]
            if hit:
                return hit[0]
        return None

    def submission_shapes(self, attacker, defender):
        """The submission holds THIS attacker could put on THIS defender as she lies now: {name: {"look",
        "contacts": [(part, role, with)], "free", "strain"}}."""
        a, d = self.get(attacker), self.get(defender)
        plan = self.body_plan(a)
        lie = self.facing_of(d.name) if d.name in self.downed else None
        out = {}
        for name, s in self.SUBMISSIONS.items():
            if plan not in s["by"] or lie not in s["facing"]:
                continue
            used, contacts, ok = [], [], True
            for spec, role, how in s["contacts"]:
                got = self._sub_part(d, spec, used)
                if not got:
                    ok = False
                    break
                for p in (got if isinstance(got, list) else [got]):
                    used.append(p)
                    contacts.append((p, role, how[plan]))
            if ok and contacts:
                out[name] = {"look": s["look"][plan], "contacts": contacts, "free": s["free"][plan],
                             "strain": s["strain"]}
        return out

    def sub_chance(self, f):
        """The chance of an opening to lock a submission on her this beat: only while she is down and not pinned or
        held, and very rare (submissions.chance; x weak_mult once she is under half strength)."""
        cfg = self.rules.get("submissions") or {}
        if not cfg.get("enabled", True) or f.name not in self.downed or self.pinned_by(f.name) \
                or any(h.defender == f.name for h in self.holds.values()):
            return 0.0
        cap = int(cfg.get("max_per_fight", 0) or 0)      # 0 = no cap: how often is the chance's job
        if cap and sum(self.times("submission", x.name) for x in self.fighters.values()) >= cap:
            return 0.0
        ch = float(cfg.get("chance", 0.03))
        if self.strength(f) < 50:
            ch *= float(cfg.get("weak_mult", 1.5))
        return ch

    def roll_sub_windows(self, open_all=False):
        self.sub_window = {}
        for f in self.active():
            ch = self.sub_chance(f)
            if ch > 0:
                self.sub_window[f.name] = bool(open_all) or self._chance(ch, f"submission opening on {f.name}",
                                                                         "OPEN", "none")
        return self.sub_window

    def sub_stuck(self, d, hs):
        """True when the one in a submission can't hope to break it: she is very weak (submissions.stuck_below % of
        her strength) or the parts it wrenches are ruined (submissions.stuck_damage)."""
        cfg = self.rules.get("submissions") or {}
        ruined = any(h.part in d.parts and d.parts[h.part].damage >= float(cfg.get("stuck_damage", 300)) for h in hs)
        return self.strength(d) < float(cfg.get("stuck_below", 25)) or ruined

    def sub_break_chance(self, ch, d, hs):
        """The break-free chance against a submission: the plain-hold chance x break_mult, and x (1 + grow per beat
        it has been on), so the longer it's on the likelier she gets out, up to max_break. Unless she is stuck
        (sub_stuck): then it does not grow (x stuck_mult), and the holder is pointed at a pin or other damage
        instead. Returns (chance, stuck)."""
        cfg = self.rules.get("submissions") or {}
        ch *= float(cfg.get("break_mult", 0.8))
        stuck = self.sub_stuck(d, hs)
        beats = max(h.turns_active for h in hs)
        if stuck:
            ch *= float(cfg.get("stuck_mult", 0.6))
        else:
            ch *= 1.0 + float(cfg.get("grow", 0.3)) * max(0, beats - 1)
        return round(min(float(cfg.get("max_break", 0.85)), ch), 3), stuck

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
        shapes = self.submission_shapes(a.name, d.name)
        if key not in self.SUBMISSIONS:
            raise ValueError(f"no submission hold called '{name}'. Holds: {', '.join(self.SUBMISSIONS)}")
        if enforce:
            if not cfg.get("enabled", True):
                raise ValueError("submission holds are off (rules.json submissions.enabled)")
            if d.name not in self.downed:
                raise ValueError(f"{d.name} is on her feet: a submission hold needs her on the ground first")
            if self.pinned_by(d.name):
                raise ValueError(f"{d.name} is pinned: finish the pin or release it before a submission hold")
            if a.name in self.downed or self.pinned_by(a.name) or self.pinning(a.name):
                raise ValueError(f"{a.name} isn't free to lock a hold on anyone right now")
            if self.__dict__.get("sub_window", {}).get(d.name) is not True:
                raise ValueError(f"no submission opening on {d.name} this beat (they are very rare). Choose another "
                                 f"action")
        if key not in shapes:
            lie = self.facing_of(d.name) if d.name in self.downed else "on her feet"
            raise ValueError(f"{a.name} can't put {d.name} in a {key} as she is ({lie}). She could: "
                             f"{', '.join(shapes) or 'none right now'}")
        s = shapes[key]
        main, second = float(cfg.get("power", 16)), float(cfg.get("second_power", 9))
        ramp, ramp2 = float(cfg.get("ramp", 3)), float(cfg.get("second_ramp", 1))
        contacts = [(p, main if role == "main" else second, ramp if role == "main" else ramp2, w)
                    for p, role, w in s["contacts"]]
        res = self.start_holds(a.name, d.name, contacts, flavor or s["look"], pin=False, enforce=enforce)
        for hid in res.get("hold_ids") or []:
            if hid in self.holds:
                self.holds[hid].sub = key
        self.__dict__.setdefault("sub_window", {})[d.name] = False
        self._count("submission", d.name)
        res["submission"] = {"name": key, "look": s["look"], "free": s["free"], "strain": s["strain"],
                             "max_beats": int(cfg.get("max_beats", 3))}
        return res

    def _submission_tick(self):
        """A submission hold that has run submissions.max_beats beats is let go: she can't keep it on any longer. One
        that has held submissions.becomes_pin_after beats first becomes a PIN: she is held down in it, the pin's clock
        and pass-out start, and the grips go on wrenching as hard as before, still building (no lighter pin pressure)."""
        cfg = self.rules.get("submissions") or {}
        cap = int(cfg.get("max_beats", 3))
        events, done = [], {}
        after = int(cfg.get("becomes_pin_after", 0) or 0)
        if after > 0:
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
            self.note_roll(f"{an} getting a free blow in on {dn} during the {what}", ch, r,
                           "she does" if r < ch else "no")
            if r >= ch:
                continue
            usable = [m for m in a.moves if m.get("target") in ("targeted", "spread") and not m.get("charge")
                      and not m.get("carry") and float(m.get("power", 0) or 0) > 0
                      and a.move_uses.get(m["name"], 1) > 0 and a.energy >= self.energy_cost(m)]
            gripped = [h.part for h in self.holds.values() if h.attacker == an and h.defender == dn]
            same, near = neighbor_parts(list(d.parts), self.rng.choice(gripped)) if gripped else ([], [])
            spots = [x for x in same + near if x not in gripped] or [x for x in d.parts if x not in gripped] or list(d.parts)
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

    def pin_cap(self):
        """How hard a pin's steady pressure (and the punishment for a failed struggle) can bite into a worn-down part:
        pin.pressure_cap {"mult", "health_mult"} (null = no limit). A pin wears her down; it doesn't wreck her."""
        c = self.rules.get("pin", {}).get("pressure_cap")
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
                or any(self.has(d, st) for st in ("asleep", "frozen", "paralyzed", "flinched", "constricted", "airborne"))
                or (self.pressed.get(d.name) or {}).get("surface")):
            return None
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
        for st, label, key, dflt in (("doubled_over", "doubled over in pain", "doubled_over", 1.2),
                                     ("off_balance", "caught off balance", "off_balance", 1.2),
                                     ("dazed", "dazed, slow to react", "dazed", 1.15),
                                     ("flinched", "caught flinching", "flinched", 1.15)):
            if self.has(d, st):
                opts.append((label, float(cfg.get(key, dflt))))
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

    def _jolts(self, d, hits):
        """What a hard hit can do beyond the damage: the wind knocked out of her (chest or belly), dazed (head), or
        doubled over by a blow on a part that was already devastated (moves.jolts). Returns status records."""
        cfg = (self.rules.get("moves") or {}).get("jolts") or {}
        if not cfg.get("enabled", True):
            return []
        out = []
        for h in sorted(hits, key=lambda h: -h.get("damage_taken", 0)):
            if h.get("defender", d.name) != d.name or h.get("damage_taken", 0) < float(cfg.get("min_damage", 40)):
                continue
            reg = body_region(h["part"])
            for st, ok, key, dflt in (
                    ("breathless", reg in ("chest", "belly") and h.get("damage_after", 0) >= 90, "breathless", 0.3),
                    ("dazed", reg == "head" and h.get("damage_after", 0) >= 150, "dazed", 0.25),
                    ("doubled_over", h.get("damage_before", 0) >= 300, "doubled_over", 0.15)):
                if not ok or self.has(d, st) or any(x["status"] == st for x in out):
                    continue
                if self._chance(float(cfg.get(key, dflt)), f"{d.name} {st.replace('_', ' ')} by the blow to her {h['part']}",
                                st.replace("_", " "), "no"):
                    self.set_status(d, st, 1)
                    out.append({"fighter": d.name, "status": st, "beats": 1})
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
                 ["deep raked lines, the fur torn away in strips", "the coat clawed ragged, whole tufts gone and the skin "
                  "welted", "gouged furrows, the fur hanging in torn clumps round them"]),
        "bite": (["tooth marks pressed into the fur", "a crescent of dents where teeth closed",
                  "the fur pinched up in a line of small tooth prints"],
                 ["a ring of tooth marks, puffy and red round each one", "bite marks swollen into a raised ring",
                  "a double row of tooth prints, the skin round them puffed"],
                 ["deep tooth marks, the fur matted and clumped round them", "a ragged bite mark, the fur torn and the "
                  "flesh round it swollen tight", "deep tooth marks gone dark, the fur round them stiff and matted"]),
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
        "shock": (["the fur frizzed and standing up", "the coat crackling, every hair on end",
                   "a static-fluffed patch of fur"],
                  ["the fur singed and frizzed", "scorched tips to the fur, smelling of burnt hair",
                   "the coat frizzed and darkened at the ends"],
                  ["the fur singed in patches, the skin beneath angry red", "burnt, brittle fur over reddened skin",
                   "singed bare in spots, the skin shiny and red beneath"]),
        "cold": (["frost-stiff fur", "the fur rimed white and crunchy", "a patch of fur stiff with ice"],
                 ["frost-burned patches, the fur dull and stiff", "the coat frozen into stiff spikes, the skin pale "
                  "beneath", "cold-burned patches gone numb and white"],
                 ["frost-burned patches gone red and raw-looking under stiff fur", "the skin blotched red and white "
                  "from the cold, the fur brittle", "cold-burned and swollen, the fur frozen into clumps"]),
    }
    # more wordings for each (merged into MARKS / CARTILAGE below): as much variety as the narrator can be given
    MARKS_MORE = {
        "claw": (["a light scoring of claw marks", "shallow nicks in the coat, the fur parted in thin lines"],
                 ["claw furrows crossing each other, the fur ragged", "long red scratches showing through the parted fur"],
                 ["deep claw tracks, the coat shredded round them", "the fur raked off in strips, the skin beneath "
                  "raw-looking"]),
        "bite": (["small dents in the coat where fangs pressed", "a faint arc of bite marks"],
                 ["bite marks raised and reddened", "the fur bunched and wet round a ring of tooth marks"],
                 ["a crushing bite mark, the flesh round it swollen out", "deep fang marks, the coat round them clumped "
                  "and torn"]),
        "blunt": (["the coat mussed where it landed", "a dull patch where the fur was knocked flat"],
                  ["a bruise blooming under the coat, plain when the fur lifts", "the fur raised over a bruised swelling"],
                  ["bruised deep and swollen tight, the fur standing up over it", "the swelling pushing the fur apart, "
                   "dark beneath"]),
        "grip": (["the shape of the grip pressed into her coat", "fur smoothed flat in a band where it held"],
                 ["the coat creased into folds that won't lie down, bruising beneath", "grip-shaped bruises showing "
                  "through the flattened fur"],
                 ["the fur ground flat and the flesh puffed up dark round the grip lines", "crushed and swollen where "
                  "the hold was, the coat matted down hard"]),
        "shock": (["the fur puffed out and twitching", "hairs standing up in a crackling halo"],
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

    def visible_marks(self, f, p):
        """What the damage to one part LOOKS like by now: the marks of what did it (claws, teeth, blows, grips,
        lightning, cold), how deep, and cartilage (ears, nose, fins) creased or bent out of shape for now."""
        lvl = 2 if p.damage >= 300 else 1 if p.damage >= 150 else 0
        srcs = [c for c in self.injury_log.get(f"{f.name}|{p.name}", []) if c][-2:]
        kinds = list(dict.fromkeys(self._mark_kind(c) for c in srcs)) or ["blunt"]
        import zlib
        pick = lambda lst, salt: lst[zlib.crc32(f"{f.name}|{p.name}|{salt}".encode()) % len(lst)]
        marks = [pick(self.MARKS[k][lvl], k) for k in kinds[:2]]
        cart = next((pick(v, "c") for k, v in self.CARTILAGE.items() if k in p.name.lower() and v), "")
        if cart and lvl >= 1:
            marks.append(cart + " for now")
        if lvl == 2 and "swollen" not in " ".join(marks):
            marks.append("swollen")
        return f"her {p.name.lower()}: " + ", ".join(marks)

    def wear_text(self):
        """VISIBLE WEAR: how each fighter looks by now, so the narrator keeps it the same from beat to beat."""
        rows = []
        for f in self.active():
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
                bits.append("frost in her fur, shivering")
            bad = sorted((p for p in f.parts.values() if p.damage >= 90), key=lambda p: -p.damage)[:4]
            # a mark on a part nobody has touched for a while is given in short: the first thing that shows
            ob = self._decay("origin_beats", 4)
            bits += [(self.visible_marks(f, p).split(", ")[0] if self._stale(f, p.name, ob) else self.visible_marks(f, p))
                     for p in bad]
            if bits:
                rows.append(f"{f.name}: " + "; ".join(dict.fromkeys(bits)))
        return ("VISIBLE WEAR (how they look by now; keep it the same unless this beat changes it): "
                + " | ".join(rows)) if rows else ""

    def _overcommit(self, a, move):
        """A very tired fighter sometimes overcommits (moves.exhaustion_mistakes): the blow lands weak and she
        overbalances on it (off balance for a beat)."""
        cfg = (self.rules.get("moves") or {}).get("exhaustion_mistakes") or {}
        if not cfg.get("enabled", True) or move.get("target") in ("status", "self", "hold"):
            return None
        if a.energy >= float(cfg.get("below_energy", 20)) and self.strength(a) >= float(cfg.get("below_strength", 25)):
            return None
        if not self._chance(float(cfg.get("chance", 0.12)), f"{a.name} overcommitting, sloppy with tiredness",
                            "SLOPPY", "no"):
            return None
        return a.name

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
                if reg in ("hind_low", "hind_up") or (reg in ("fore_low", "fore_up") and self.body_plan(f) == "quadruped"):
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
        if low in ("hold", "coils"):
            return f"{who} {low}"
        if low == "escape":
            return f"the blow {who[:-2] if who.endswith(chr(39) + 's') else who.rstrip(chr(39))} struck breaking free"
        if low == "struggle":
            return f"{who} struggling"
        if low in self.SUBMISSIONS:
            return f"{who} {low}"
        mv = self.dex_move(what)
        about = str((mv or {}).get("about") or "")
        if about[:2].lower() in ("a ", "an") or about[:4].lower() == "the ":
            noun = re.split(r"\s+(?:across|into|from|that|with|to|which)\b|[,:;(]", about, maxsplit=1)[0].strip()
            noun = re.sub(r"^(?:a|an|the)\s+", "", noun, flags=re.I)
        else:
            noun = {"Normal": "blow", "Fighting": "blow"}.get((mv or {}).get("type"), "blow") if mv else low
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
            lead = f"{f.name} {pick(self.REPORT_LEAD[lead_key], 'lead')}"
            worst = sorted((p for p in f.parts.values() if p.damage >= 90), key=lambda p: -p.damage)[:4]
            if not worst:
                rows.append(f"{lead}: bruised here and there, nothing that will last")
                continue
            bits = []
            for i, p in enumerate(worst):
                causes = [c for c in self.injury_log.get(f"{f.name}|{p.name}", []) if c]
                causes = list(dict.fromkeys(self._cause_words(c, f.name) for c in causes[-2:]))
                cause = " and ".join(causes) or "the fight"
                sev = "deep" if p.damage >= 300 else "sore" if p.damage >= 150 else "light"
                hurt = pick(self.REPORT_HURT[sev], p.name)
                frame = self.REPORT_FRAMES[(zlib.crc32(f"{f.name}|{p.name}".encode()) + i) % len(self.REPORT_FRAMES)]
                bits.append(frame.format(part=p.name.lower(), cause=cause, hurt=hurt))
            bits[0] = bits[0][0].upper() + bits[0][1:]
            rows.append(f"{lead}. " + "; ".join(bits))
        return "INJURY REPORT (what each will feel when it's over): " + " | ".join(rows)

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
            if r.get("type") != "instant":
                continue
            mv = (r.get("move") or {}).get("name") or "a blow"
            land = bool(r.get("environment"))
            if land:
                mv = "the landing"
            whose = f"{poss_word(dfn)} landing" if land else f"{poss_word(att)} {mv}"
            lost = deal(att, r.get("hits"), dfn)
            deal(dfn, r.get("counter_hits"), att)
            loss = pct(dfn, lost.get(dfn, 0.0))
            hits = r.get("hits") or []
            part = max(hits, key=lambda h: float(h.get("health_loss") or 0))["part"].lower() if hits else ""
            if loss > 0 and (ch["biggest"] is None or loss > ch["biggest"]["pct"]):
                ch["biggest"] = {"beat": self.turn, "who": att, "to": dfn, "move": mv, "part": part,
                                 "pct": round(loss, 1)}
            if r.get("devastating") and hits:
                dp = next((h["part"].lower() for h in hits if h.get("devastating")), part)
                self._moment("devastating", (f"{whose} comes down DEVASTATINGLY on her {dp}" if land else
                                             f"{whose} lands DEVASTATINGLY on {poss_word(dfn)} {dp}"),
                             att, dfn, loss, 3)
            elif loss >= big_at:
                self._moment("big", (f"{whose} slams her {part} into the ground" if land else
                                     f"{whose} hammers {poss_word(dfn)} {part}"), att, dfn, loss, 1.5)
            if r.get("juggle") and hits:
                self._moment("juggle", f"{att} catches {dfn} helpless in the air with {mv}", att, dfn, loss, 2)
            if (r.get("feint") or {}).get("bit") and hits:
                self._moment("feint", f"{dfn} bites on {poss_word(att)} feint and eats the {mv}", att, dfn, loss, 1)
            if r.get("last_stand"):
                self._moment("last_stand", f"{att} throws everything she has left into one last {mv}", att, dfn, loss, 2)
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
        lose = max(losers, key=lambda f: ch.get("dealt", {}).get(win, 0)).name
        moments = [m for m in ch.get("moments", []) if m["kind"] != "finish"]
        cap = int((self.rules.get("summary") or {}).get("moments", 10))
        per_kind = int((self.rules.get("summary") or {}).get("per_kind", 3))
        keep, kinds = [], {}
        for m in sorted(moments, key=lambda m: -(m["weight"] + m["loss"] / 10.0)):
            k = "pin" if m["kind"] in ("pin", "escape") else m["kind"]
            if kinds.get(k, 0) < (per_kind + 1 if k == "pin" else per_kind) and len(keep) < cap:
                kinds[k] = kinds.get(k, 0) + 1
                keep.append(m)
        keep.sort(key=lambda m: m["beat"])
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
                        + (f"{max(0.0, fin['strength']):.0f}% strength" if fin.get("strength") is not None else "the end"))
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
        ch = min(float(cfg.get("max_chance", 0.1)), ch)
        if not self._chance(ch, f"{poss_word(a.name)} {move['name']} landing devastatingly", "DEVASTATING", "no"):
            return None
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
        """A fighter with wings, free to take off. A hurt wing still lifts her, at a cost (flight.strain); only a shredded
        one (strain.max_wing) can't."""
        cfg = self.rules.get("flight") or {}
        reason = None
        if not any("wing" in p.lower() for p in f.parts):     # a bird, or a winged dragon with arms too
            reason = f"{f.name} has no wings"
        elif self.wing_damage(f) >= float((cfg.get("strain") or {}).get("max_wing", 600)):
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
        return float(cfg.get("takeoff_energy", 8)) * (1 + float(st.get("energy_per_100", 1.0)) * over / 100)

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
            power = round(float(st.get("power", 6)) * worst.damage / 100, 2)
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
        for h in [h for h in self.holds.values() if h.attacker == f.name]:
            self.holds.pop(h.id, None)
        self.set_status(f, "airborne", int(cfg.get("airborne_beats", 3)))
        self.involved.add(f.name)
        return {"type": "take_off", "fighter": f.name, "beats": int(cfg.get("airborne_beats", 3)), "energy": round(cost, 1),
                "hurt_wing": self.wing_damage(f) >= float((cfg.get("strain") or {}).get("from", 100))}

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
        if self._chance(float(cfg.get("climb_chance", 0.55)), f"{a.name} climbing back up after the dive", "back up", "she lands"):
            self.set_status(a, "airborne", max(a.status.get("airborne", 0), 2))
            res["climbs"] = True
        else:
            a.status.pop("airborne", None)
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
        if enforce and (self.has(d, "airborne") or self.has(a, "airborne")):
            raise ValueError(f"{(d if self.has(d, 'airborne') else a).name} is in the air: no grabbing until she comes down")
        if enforce and a.name in self.pressed:
            raise ValueError(f"{a.name} is still pressed against the scenery: she can't grab anyone this beat")
        if self.grabbed_by(a.name, d.name):
            raise ValueError(f"{a.name} already has hold of {d.name}: strike her, throw her, or let go")
        if enforce:
            self._regrab_check(a, d)
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
        pname = d.part(part).name
        # the grab she already had on her from the other side ends: you can't be held by her and holding her at once
        for h in [h for h in list(self.holds.values()) if h.grab and h.attacker == d.name and h.defender == a.name]:
            self.release(h.id, "reversed: the grab turned round on her")
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
                "part": pname, "with": st.get("with", ""), "power": st["power"], "hold_id": st["hold_id"],
                "hold_ids": [] if st.get("existing") else [st["hold_id"]], "existing": bool(st.get("existing")),
                "flavor": flavor, "energy": [round(before), round(a.energy)],
                "break_chance": self.hold_break_chance(a.name, d.name)}

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
        if not text or not jaw_parts:
            return text
        names = sorted({str(p).lower() for p in getattr(d, "parts", {})}, key=len, reverse=True)
        wrong = False
        for clause in re.split(r",|;|\band\b", text):
            if not re.search(jaw_rx, clause, re.I):
                continue
            low = clause.lower()
            named = [p for p in names if re.search(r"\b" + re.escape(p) + r"\b", low)]
            if named and not any(p in jaw_parts for p in named):
                wrong = True
        if not wrong:
            return text
        bits = [f"{st.get('with') or 'pressure'} on her {str(st['part']).lower()}" for st in started]
        return ", ".join(bits[:-1]) + (" and " if len(bits) > 1 else "") + bits[-1]

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
            if h is not None and self.is_coil(move, h.with_part, flavor):
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
            fits = ({"drag_down", "spin_down", "sweep", "leg_hook", "pull_forward", "ride_down"} if lies == "face-down" else
                    {"tackle", "shoulder_drive", "trip_back", "sweep", "leg_hook", "hip_throw", "drag_down", "spin_down"}
                    if lies == "face-up" else set(table))
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
                           "asked_with": h.get("asked_with", "")} for h in started]}

    def regrab_wait(self, a, d):
        """Beats left before `a` may grip `d` again after `d` tore free of her (holds.break.regrab_after); 0 = free."""
        wait = int((self.rules.get("holds", {}).get("break", {}) or {}).get("regrab_after", 2))
        broke = (getattr(self, "broke_free_at", {}) or {}).get((a.name, d.name))
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
        if self.has(d, "paralyzed"):
            ch *= 0.5
        if self.has(d, "adrenaline"):
            ch *= 1.5
        if all(h.grab for h in hs):
            ch *= float(cfg.get("grab_mult", 1.6))   # a grab holds her close; it doesn't lock her
        if any(h.coil for h in hs):
            ch *= float((self.rules.get("holds", {}).get("coil") or {}).get("break_mult", 0.75))   # coils give nothing to push against
        sc = self._cfg("status_effects")
        if self.has(d, "soaked"):
            ch *= float(sc.get("soaked_slip_mult", 1.2))     # wet fur slides out of a grip
        if self.has(a, "soaked"):
            ch *= float(sc.get("soaked_grip_mult", 1.1))     # and a wet paw holds worse
        return round(max(0.0, min(float(cfg.get("max", 0.6)), ch)), 3)

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
                        "reason": f"{why} shook it loose: it cost her {share * 100:.0f}% of her health at once"})
        return out

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
            if any(h.sub for h in hs):
                ch, _ = self.sub_break_chance(ch, fd, hs)
            if fd.name in self.lucky:
                ch = 1.0   # /play dice free: she breaks any hold on her at once
            if ch <= 0:
                continue
            cfg = self.rules.get("holds", {}).get("break", {})
            ok, r = self._chance_r(ch, f"{d} breaking {poss_word(a)} hold on her", "she breaks free", "it holds")
            if ok:
                for h in hs:
                    self.holds.pop(h.id, None)
                # she just tore loose: the same grip can't simply close on her again next beat
                self.__dict__.setdefault("broke_free_at", {})[(a, d)] = self.turn
                events.append({"type": "hold_end", "broke_free": True, "attacker": a, "defender": d,
                               "submission": next((h.sub for h in hs if h.sub), ""),
                               "hold_ids": [h.id for h in hs], "parts": [h.part for h in hs],
                               "with": [h.with_part for h in hs if h.with_part],
                               "beats_held": max(h.turns_active for h in hs), "chance": ch,
                               "manner": self.vary("hold_break"), "reason": f"{d} wrenched free"})
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
            # a submission that has become a pin (h.locked) keeps its own wrench: no lighter pin pressure, no cap
            as_pin = in_pin and not h.locked
            power = (h.power * time_factor * float(self.rules.get("pin", {}).get("damage_mult", 1.0)) * ramp
                     if as_pin else h.power) * first
            self._source = (f"{poss_word(h.attacker)} {h.locked or ('pin' if in_pin else h.sub or ('coils' if h.coil else 'hold'))}")
            hit = self._apply_damage(d, h.part, round(power, 2), cap=self.pin_cap() if as_pin else None)
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
                           "beats_held": h.turns_active, "hits": [hit], "tags": self._tags([hit])})
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
        events += self._hold_break_tick(skip_hold_ids)
        events += self._submission_tick()
        events += self._free_blow_tick(skip_hold_ids)
        events += self._wing_strain_tick()
        events += self._crumple_tick()
        events += self.get_up_tick()
        events += self._scene_event_tick(busy=had_grip)

        fighters = {}
        for f in self.active():
            before = f.health
            tier_b = tier_for(self._health_pct(f), r["health_tiers"])["label"]
            drain = 0.0
            for p in f.parts.values():
                p.resistance = max(r["resistance"]["minimum"], p.resistance - r["resistance"]["loss_per_beat"])
                for d in r["health"]["pain_drain"]:
                    if p.damage >= d["min_damage"]:
                        drain += d["per_beat"] * self.part_weight(p.name)   # a ruined ear drains less than a ruined chest
            in_hold = any(f.name in (h.attacker, h.defender) for h in self.holds.values())
            tiring = f.name in self.involved or in_hold
            exhaustion = r["health"]["exhaustion_per_beat"] if tiring else 0.0
            f.health = self._floor(f.health - drain - exhaustion)
            ht = tier_for(self._health_pct(f), r["health_tiers"])
            fighters[f.name] = {"health_before": round(before, 2), "health_after": round(f.health, 2),
                                "max_health": f.max_health,
                                "exhaustion": exhaustion, "pain_drain": drain,
                                "health_tier": ht["label"], "health_tier_changed": ht["label"] != tier_b,
                                "reaction_guide": ht["reaction"]}
        events += self.recover_tick()
        events += self._tick_status_energy()
        events += self._weather_tick()
        events += self._alliance_tick()
        self.pin_window = {}  # openings are rolled fresh for every beat
        self.sub_window = {}
        events.append({"type": "time_passes", "beat": self.turn, "fighters": fighters})
        self.involved = set()
        self.beat_loss = {}   # health.soft_cap counts each beat on its own
        return events

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
                hurt = [p for p in f.parts.values() if p.damage > 0] or list(f.parts.values())
                self._source = "the burn"
                hit = self._apply_damage(f, self.rng.choice(hurt).name, float(cfg_s.get("burn_power", 5)))
                events.append({"type": "status_tick", "fighter": f.name, "status": "burned", "hits": [hit]})
            if self.has(f, "poisoned"):
                loss = f.max_health * float(cfg_s.get("poison_health_pct", 1.0)) / 100
                f.health = self._floor(f.health - loss)
                events.append({"type": "status_tick", "fighter": f.name, "status": "poisoned",
                               "health_loss": round(loss, 2), "health_after": round(f.health, 2)})
            regen = float(en.get("regen_per_beat", 5)) + (0 if f.name in self.involved else float(en.get("rest_bonus", 10)))
            if self.has(f, "constricted"):      # the coils squeeze her breath: she gets none back, and loses some
                regen = -float(cfg_s.get("constricted_energy_loss", 4))
            elif self.has(f, "sputtering"):     # coughing water up: no breath to get back
                regen = 0.0
            elif self.has(f, "breathless"):     # winded: half the breath comes back (resting still helps)
                regen *= float(cfg_s.get("breathless_regen_mult", 0.5))
            f.energy = max(0.0, min(100.0, f.energy + regen))
            if (ad.get("enabled", True) and not f.adrenaline_used
                    and self.strength(f) < float(ad.get("below_strength", 25))):
                f.adrenaline_used = True
                self.set_status(f, "adrenaline", ad.get("beats", 3))
                f.energy = min(100.0, f.energy + float(ad.get("energy", 30)))
                events.append({"type": "adrenaline", "fighter": f.name, "beats": int(ad.get("beats", 3))})
        self._fresh_status = set()
        return events

    IN_WATER = re.compile(r"\b(?:(?:in|into|through|under|beneath|across|half in|waist-deep in|ankle-deep in|"
                          r"knee-deep in|chest-deep in)\s+(?:the\s+|a\s+)?(?:[a-z-]+\s+){0,2}(?:pool|water|channel|"
                          r"shallows|stream|creek|rapids|sump|surf|spring|flooded \w+)|submerged|wading|swimming|"
                          r"half-submerged)\b", re.I)

    DEEP = re.compile(r"\b(?:channel|deep|plunge pool|lake|rapids|creek|chest-deep|waist-deep|swimming|submerged)\b", re.I)
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
            if m and self.IN_WATER.search(m.group(1)):
                self.set_status(f, "soaked", max(f.status.get("soaked", 0), 2))
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
            text = (f"LOCKED ONTO {h.defender} in a {h.sub.replace('_', ' ')} (down on her, wrapped round her; "
                    f"not standing free)" if not short else f"LOCKED ONTO {h.defender} in a {h.sub.replace('_', ' ')}")
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
            out.append(f"{f.name}: {sure}" + (f", {clause}" if clause else ""))
        return "; ".join(out)

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
            unmet = sec_cfg.get("enabled", False) and not self.pin_securable(dfn)[0]
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
            if self.has(dfn, "adrenaline"):
                esc_try *= float(self._cfg("adrenaline").get("escape_mult", 1.5))
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
            esc = self._per_beat(min(0.95, esc_try), tf)
            # if the escape fails: the chance to break loose for a moment and land a hit, same halving curve
            part_try = s.get("partial_chance", 0.50) * curve * (1 + 0.6 * a_weak) * fade * crowd
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
            if forced_try or self._chance(attempt_p, f"{dfn.name} making an escape attempt", "she tries",
                                          "no real attempt"):
                roll = self.rng.random()
                ev["roll"] = round(roll, 3)
                ev["try_how"] = self.vary("struggle")
                if roll < esc or dfn.name in self.lucky:   # /play dice free: every try of hers gets her out
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
                    and self._chance(float(sec_cfg.get("final_kickout_chance", 0.85)),
                                     f"{dfn.name} kicking out at the last second", "she kicks out", "no")):
                # the pin can't be won yet: she kicks out at the last second
                ev.update(struggle="escape", last_second=True, why_not=self.pin_securable(dfn)[1])
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

    def eliminate(self, name, reason=""):
        """The story decides a fighter is out (pinned for the full count, knocked out, submitted)."""
        d = self.get_active(name)
        was_down = d.name in self.downed
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
        elif high < 92 or self.turn > 4:
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
                bits.append(f"she has been put on the ground {downs} times")
            lost = float(before.get(f.name, me)) - me
            fade = float((pinned.get(f.name) or {}).get("fade", 0) or 0)
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
        "chilled": "CHILLED: frost in her fur or on her scales, shivering, limbs stiff and slow",
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
        "doubled_over": "DOUBLED OVER by the pain: folded round the hurt, guard down for a moment",
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
        "poisoned": "POISONED: nauseous and shaky, the poison sapping her a little every moment",
        "adrenaline": "ADRENALINE SURGE: pain pushed to the back of her mind, eyes sharp, faster and hitting harder "
                      "than she should be able to",
    }

    def status_words(self, f):
        bits = [self.STATUS_LOOK.get(s, s.upper()) + f" ({n} beat{'s' if n != 1 else ''})" for s, n in f.status.items()]
        e = f.energy
        tired = float(self._cfg("energy").get("tired_below", 25))
        stamina = ("fresh breath" if e >= 70 else "breathing hard" if e >= tired else "gasping, running out of energy")
        return (" Status: " + "; ".join(bits) + "." if bits else "") + f" Stamina: {stamina}."

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
            if region == "tail":
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
        return [p.name for p in f.parts.values() if p.damage >= need]

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
                src = self.injury_log.get(f"{f.name}|{p.name}", [])
                return f"; from {', then '.join(src[-2:])}" if src else ""
            hurt = [f"{p.name} ({tier_for(p.damage, pain_tiers(self.rules))['label']}{_origin(p)})"
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
            lines.append(f"{f.name}: OVERALL {words} -> what this fighter can still do: {ht['reaction']}{ground}\n"
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
            lines.append("HOLDS (still gripping): " + "; ".join(f"{h.attacker} has {h.defender}'s {h.part}"
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

    def narrator_condition(self):
        text = self.condition_summary() + ("\n" + self.weather_text() if getattr(self, "weather", None) else "")
        for extra in (self.wear_text(), self.movement_text()):
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
                                "close" if (m.get("target", "targeted") in ("targeted", "hold") and not m.get("ranged"))
                                or m.get("ranged") is False else "ranged")
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
            gw = self.guarded_wound(f)
            if gw:
                ow = self.open_side_word(gw[0])
                lines.append(f"   GUARDING her {gw[0]} (blows there land lighter)"
                             + (f"; her {ow}{' side' if ow in ('left', 'right') else ''} is open (blows there land harder)"
                                if ow else ""))
            opn = [st.replace("_", " ") for st in ("doubled_over", "off_balance", "dazed", "flinched") if self.has(f, st)]
            if opn:
                lines.append(f"   CAUGHT OPEN ({', '.join(opn)}): anything that lands on her now lands harder")
            if any("wing" in p.lower() for p in f.parts):
                lines.append("   IN THE AIR (only ranged moves reach her; her close moves are dives; she can't be held "
                             "or pinned)" if self.has(f, "airborne") else
                             ("   can take off ('reposition': 'take off' on her own action)"
                              + (f", but her wing is badly hurt: it costs {self.takeoff_cost(f):.0f} energy and tears "
                                 f"worse every beat she stays up" if self.wing_damage(f) >= float(
                                     ((self.rules.get('flight') or {}).get('strain') or {}).get('from', 100)) else "")
                              ) if self.can_fly(f) else
                             f"   grounded: {self.can_fly(f, why=True)}")
            sec, why_not = self.pin_securable(f)
            if not sec:
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
                lines.append(f"   hold_id {h.id}: {h.attacker} has {h.defender}'s {h.part} — "
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
                            f"more, sometimes fewer; nobody in the story knows). The engine rolls {p['defender']}'s "
                            if self.fade_mode() else
                            f"{p['seconds']} of {p['duration']} seconds. The engine runs the clock and rolls "
                            f"{p['defender']}'s ")
                         + f"struggles every beat. Keep it going with 'breather' (or 'hold_adjust' to bear down); "
                         f"the pinner does NOT start another pin. {p['defender']} may also strike {' or '.join(crew)} with a free limb.")
        return "\n".join(lines)

    # ---------- save / load ----------
    def save(self, path, extra=None):
        data = {"turn": self.turn, "next_hold_id": self.next_hold_id, "scene": self.scene,
                "scene_name": self.scene_name, "last_event": self._last_event, "pins": self.pins,
                "positions": self.positions, "downed": self.downed, "since_pin": self.since_pin,
                "last_pin_end": self.last_pin_end, "injury_log": self.injury_log, "plan": self.plan,
                "tally": self.tally, "momentum": self.momentum, "facing": self.facing, "move_log": self.move_log,
                "last_reposition": getattr(self, "_last_reposition", {}), "alliances": self.alliances,
                "weather": getattr(self, "weather", {}), "arena_marks": getattr(self, "arena_marks", []),
                "broken_props": list(getattr(self, "broken_props", []) or []),
                "chronicle": getattr(self, "chronicle", None) or self.new_chronicle(),
                "setups": self.__dict__.get("setups") or [],
                "extra": extra or {},
                "fighters": {k: {**asdict(f), "parts": {n: asdict(p) for n, p in f.parts.items()}}
                             for k, f in self.fighters.items()},
                "holds": {i: asdict(h) for i, h in self.holds.items()}}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

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
            parts = {n: BodyPart(**p) for n, p in fd.pop("parts").items()}
            self.fighters[k] = Fighter(**fd, parts=parts)
        self.holds = {int(i): Hold(**h) for i, h in data["holds"].items()}
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
        self.tally = {k: int(v) for k, v in (data.get("tally") or {}).items()}
        self.plan = data.get("plan", {})
        self.alliances = data.get("alliances", [])
        self.weather = data.get("weather", {})
        self.arena_marks = data.get("arena_marks", [])
        self.broken_props = list(data.get("broken_props", []) or [])
        self.chronicle = {**self.new_chronicle(), **(data.get("chronicle") or {})}
        self.setups = list(data.get("setups") or [])
        self.pressed, self._pending_events, self.pin_window = {}, [], {}
        return data.get("extra", {})
