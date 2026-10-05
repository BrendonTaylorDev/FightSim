"""Story building blocks: a large file of ideas (reactions, sensations, tells, movements, thoughts...) from which the
program hands the narrator a few that fit the fight as it stands, preferring the ones offered least.

The file (story_blocks.txt) is plain text; see its first lines for the format. Nothing here decides what happens:
the blocks are colour for events the engine has already resolved."""
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
HEAD = re.compile(r"^==+\s*(.+?)\s*=*\s*$")
SLOT = re.compile(r"\{(\w+)\}")
# engine body regions -> the zones a block can ask for
ZONE_OF = {"head": "head", "neck": "neck", "chest": "chest", "belly": "belly", "back_up": "back", "back_low": "back",
           "shoulder": "arm", "fore_up": "arm", "fore_low": "arm", "hind_up": "leg", "hind_low": "leg", "tail": "tail"}


def _conds(text):
    """'size: heavy, tremendous | has: tails' -> {'size': {'heavy', 'tremendous'}, 'has': {'tails'}}"""
    out = {}
    for bit in text.split("|"):
        if ":" not in bit:
            continue
        k, v = bit.split(":", 1)
        vals = {x.strip().lower() for x in v.split(",") if x.strip()}
        if k.strip() and vals:
            out[k.strip().lower()] = vals
    return out


def parse(text):
    """[(category, conditions, block text)] from the file's text."""
    out, cat, base = [], None, {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = HEAD.match(line)
        if m:
            bits = m.group(1).split("|", 1)
            cat = bits[0].strip().lower()
            base = _conds(bits[1]) if len(bits) > 1 else {}
            continue
        if cat is None:
            continue
        body, _, own = line.partition(" | ")
        conds = dict(base)
        for k, v in _conds(own).items():
            conds[k] = v
        if body.strip():
            out.append((cat, conds, body.strip()))
    return out


def features(part_names):
    """What a body has, read off its part names: the words a block's 'has:' condition can ask for."""
    low = " | ".join(p.lower() for p in part_names)
    has = set()
    if not low.strip():
        return has          # no body known: nothing body-specific is offered (and nobody is taken for a serpent)
    if re.search(r"\btails\b", low):
        has.add("tails")       # twin tails, six tails, nine tails
    if "crest" in low or "plume" in low:
        has.add("crest")
    if "flame" in low:
        has.add("flame")       # a burning tail tip, a crest or tail of living fire
    if "mane" in low:
        has.add("mane")
    if "wing" in low or "feather" in low:
        has.add("feathers" if "feather" in low or "beak" in low else "wings")
    if "tail" in low:
        has.add("tail")
    if "fin" in low or "fan" in low:
        has.add("fins")
    if "horn" in low:
        has.add("horn")
    if "ruff" in low:
        has.add("ruff")
    if "ear" in low.replace("forearm", ""):
        has.add("ears")
    if "antenna" in low:
        has.add("antennae")
    if "foreleg" in low or "forepaw" in low:
        has.add("forelegs")
    if re.search(r"\barm\b|upper arm|forearm", low):
        has.add("arms")
    if "wing" in low:
        has.add("wings")
    if "beak" in low:
        has.add("beak")
    if "talon" in low:
        has.add("talons")
    if "hood" in low:
        has.add("hood")
    if re.search(r"thigh|hip|knee|hock|foot|hind paw|talon", low):
        has.add("legs")
    else:
        has.add("coils")       # no legs at all: a serpent's body
    return has


def body_bans(has):
    """Words a block must not use for this body: a bird has a beak, not teeth, a jaw or fur; nothing without ears
    flattens them; a body with no arms or forelegs has no paws or hands; a serpent has no legs or feet."""
    has = set(has or ())
    if not has:
        return None
    bans = []
    if "beak" in has:
        bans += [r"\bteeth\b", r"\btooth\b", r"\bfangs?\b", r"\bjaws?\b", r"\blips?\b", r"\bmuzzle", r"\bsnout",
                 r"\bwhiskers?\b", r"\bgums?\b", r"\bcheeks?\b"]
    if "feathers" in has:
        bans += [r"\bfur\b", r"\bhackles\b", r"\bpelt\b", r"\bscruff\b"]
    if "ears" not in has:
        bans += [r"\bears?\b"]
    if "arms" not in has and "forelegs" not in has:
        bans += [r"\bpaws?\b", r"\bhands?\b", r"\bfists?\b", r"\bfingers?\b", r"\bforelegs?\b", r"\bknuckles?\b"]
    if "legs" not in has:
        bans += [r"\blegs?\b", r"\bfeet\b", r"\bfoot\b", r"\bknees?\b", r"\btoes\b", r"\bhind\b"]
    return re.compile("|".join(bans), re.I) if bans else None


def state_of(strength):
    """Overall condition as the words a block's 'state:' can ask for (from % of full strength)."""
    s = float(strength if strength is not None else 100)
    return {"fresh"} if s >= 80 else {"winded"} if s >= 60 else {"tired"} if s >= 40 else {"tired", "spent"} if s >= 20 else {"spent"}


def kind_of(move_name="", about="", with_part="", manhandle="", grab=False, close=False, ranged=False):
    """What kind of move this is, for 'kind:' (claw, bite, charge, tail, beam, punch, horn, throw, grab)."""
    if grab:
        return {"grab"}
    if close:
        return {"close"}     # inside a grab, a pummel: no room to wind anything up
    if manhandle in ("throw", "slam"):
        return {"throw"}
    t = f"{move_name} {about} {with_part}".lower()
    kinds = set()
    for k, rx in (("claw", r"claw|slash|scratch|rake|swipe"), ("bite", r"bite|fang|crunch|jaws?|teeth"),
                  ("charge", r"aqua jet|tackle|rush|charge|take down|\bram\b|body|headbutt|lunge"),
                  ("tail", r"\btails?\b"), ("beam", r"pulse|beam|gun|pump|bolt|ray|blast|stream|wave|surf|breath|wisp"),
                  ("punch", r"punch|break|chop|paw|cuff|jab|fist"), ("horn", r"horn|scythe"),
                  ("wing", r"\bwings?\b|aerial ace|air slash|gust|brave bird|sky attack|\bfly\b|acrobatics"),
                  ("beak", r"beak|peck|drill"), ("talon", r"talons?|sky drop"),
                  ("fire", r"\bfire\b|\bflames?\b|\bembers?\b|\bheat\b|\binferno|\bburn|blitz|\bflare|incinerat|\blava\b"),
                  ("ice", r"\bice\b|\bicy\b|blizzard|freeze|frost|hail|icicle"),
                  ("wind", r"hurricane|gust|twister|air slash|air cutter|\bwind\b|defog"),
                  ("rock", r"\brock\b|stone|accelerock|boulder")):
        if re.search(rx, t):
            kinds.add(k)
    if ranged and kinds & {"beam", "fire", "ice", "wind"}:
        # a discharge, a stream, a pulse: not a strike with the part it comes from (its element still counts)
        return {"beam"} | (kinds & {"fire", "ice", "wind", "rock"})
    return kinds


class Blocks:
    def __init__(self, rules, path=None, memory=None, rng=None):
        cfg = (rules.get("narration", {}) or {}).get("blocks", {}) or {}
        self.cfg = cfg
        self.enabled = bool(cfg.get("enabled", True))
        self.path = path or os.path.join(HERE, cfg.get("file", "story_blocks.txt"))
        self.memory = memory if memory is not None else os.path.join(HERE, cfg.get("memory_file", "blocks_memory.json"))
        self.rng = rng or random.Random()
        self.entries = []
        self.uses, self.last, self.turn = {}, {}, 0
        self._mtime = None
        self.load()

    # ---------- the file ----------
    def load(self):
        try:
            mt = os.path.getmtime(self.path)
        except OSError:
            self.entries, self._mtime = [], None
            return
        if mt == self._mtime:
            return
        with open(self.path, encoding="utf-8") as fh:
            self.entries = parse(fh.read())
        self._mtime = mt
        if not self.uses and self.cfg.get("remember", True):
            try:
                with open(self.memory, encoding="utf-8") as fh:
                    self.uses = {k: int(v) for k, v in json.load(fh).items()}
            except (OSError, ValueError):
                self.uses = {}

    def save(self):
        if not self.cfg.get("remember", True) or not self.uses:
            return
        try:
            with open(self.memory, "w", encoding="utf-8") as fh:
                json.dump(self.uses, fh)
        except OSError:
            pass

    def counts(self):
        out = {}
        for cat, _, _ in self.entries:
            out[cat] = out.get(cat, 0) + 1
        return out

    # ---------- choosing ----------
    @staticmethod
    def _fits(conds, ctx):
        for k, wanted in conds.items():
            have = ctx.get(k)
            if not have:
                return False
            if not (wanted & (have if isinstance(have, (set, frozenset)) else {str(have).lower()})):
                return False
        return True

    def next_turn(self):
        """Call once per beat: the cooldown is counted in beats."""
        self.turn += 1
        self.load()      # the file can be edited while the program runs

    def pick(self, category, n=1, fmt=None, need=(), exclude=None, **ctx):
        banned = body_bans(ctx.get("has")) if ctx.get("has") else None
        if banned is not None:      # nothing her body doesn't have: no teeth on a bird, no paws on a snake
            exclude = ([banned] + (list(exclude) if isinstance(exclude, (list, tuple)) else [exclude] if exclude is not None
                                   else []))
        """Up to n blocks of this category that fit ctx, least-offered first (with some chance in it), none that
        was offered in the last few beats while others are to be had. Returns their texts, placeholders filled.
        need: condition names a block must HAVE to be offered here (need=("zone",): only blocks written for a zone).
        exclude: a pattern (or several): blocks whose text matches are never offered here."""
        if not self.enabled or n <= 0:
            return []
        fmt = fmt or {}
        ctx = {k: ({str(x).lower() for x in v} if isinstance(v, (set, frozenset, list, tuple)) else {str(v).lower()})
               for k, v in ctx.items() if v}
        cool = int(self.cfg.get("cooldown_beats", 8))
        pool = []
        for cat, conds, text in self.entries:
            if cat != category or not self._fits(conds, ctx) or any(k not in conds for k in need):
                continue
            if any(s not in fmt for s in SLOT.findall(text)):
                continue
            if exclude is not None and any(rx.search(text) for rx in (exclude if isinstance(exclude, (list, tuple))
                                                                       else [exclude])):
                continue       # bigger than this fighter's injuries allow (the engine's pain ceiling)
            key = cat + "|" + text
            used = self.uses.get(key, 0)
            w = (1.0 + 0.6 * len(conds)) / (1.0 + used) ** 2      # the more exactly it fits, and the less used, the better
            if "fighter" in conds:
                w *= float(self.cfg.get("fighter_boost", 2.5))       # written for HER: her own way of doing it
            if key in self.last and self.turn - self.last[key] < cool:
                continue       # offered too lately: better to offer nothing than the same idea again so soon
            pool.append((key, text, w))
        out = []
        while pool and len(out) < n:
            total = sum(w for _, _, w in pool)
            r, acc = self.rng.random() * total, 0.0
            for i, (key, text, w) in enumerate(pool):
                acc += w
                if r <= acc:
                    break
            key, text, _ = pool.pop(i)
            self.uses[key] = self.uses.get(key, 0) + 1
            self.last[key] = self.turn
            out.append(SLOT.sub(lambda m: str(fmt[m.group(1)]), text))
        return out
