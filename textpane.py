"""The story pane of the window (window.py): which lines are the story and which are the numbers, how each is
styled, and the pointers that say where the numbers come from (rules.json window.text). No Tk here, so the tests can
run it: the window asks kind_of / spans / terms / tip for each line, and a Pointers object for the notes to add."""
import re

DEFAULTS = {"numbers": True, "pointers": "occasional", "pointer_gap": 6, "hover": True, "unwrap": True,
            "font_size": 12, "progress": True}


def opts(rules):
    """window.text, over the defaults."""
    o = dict(DEFAULTS)
    o.update(((rules or {}).get("window") or {}).get("text") or {})
    return o


def _get(rules, path, default):
    """One number from the rules by its dotted path, or the default."""
    cur = rules or {}
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    return f"{x:.2f}".rstrip("0").rstrip(".") if abs(x) < 1000 else f"{x:.0f}"


# ---- what each line is ----
MECH_START = re.compile(r"^[⚔🔒📌🎲⏳💡🧗🪽🔗💥💢🪨🌀🌊🔐🤾🏋⛓⏸🩹📜⏱💨🛡🫳🫥↩🧱🌅🔥⚡💧😵🧠🌦🦅🪶🤚🧊🎯😖🏳👊🫠☠💫🏆]")
NUM_ROW = re.compile(r"^\s+(damage|resistance|health)\s{2,}")
PART_ROW = re.compile(r"^ {4}[A-Z][A-Za-z' ]+(?: \(hit \d+\))?$")


def kind_of(line):
    """"pov" (a "— Ripples —" heading), "progress" ([narrator is writing...]), "rule" (a dashed line), "input" (what
    was typed), "head" (the first line of a block of numbers), "row" (a damage / resistance / health row), "part"
    (the part a set of rows is about), "total", "mech" (any other line of numbers), "blank" or "story"."""
    body = line.rstrip("\n")
    s = body.strip()
    if not s:
        return "blank"
    if re.match(r"^—\s.+\s—$", s):
        return "pov"
    if re.match(r"^\s*\[.*\]\s*$", body):
        return "progress"
    if re.match(r"^-{8,}$|^={8,}$|^─{8,}$|^═{8,}$", s):
        return "rule"
    if re.match(r"^[^>]*> ", body) and s.endswith(tuple("abcdefghijklmnopqrstuvwxyz0123456789")) and len(s) < 80 \
            and body.startswith(tuple("> ABCDEFGHIJKLMNOPQRSTUVWXYZ")) and "> " in body[:20]:
        return "input"
    if NUM_ROW.match(body):
        return "row"
    if re.match(r"^\s*Total:", body):
        return "total"
    if PART_ROW.match(body):
        return "part"
    if MECH_START.match(body) or re.match(r"^Attack \d+ — ", body):
        return "head"
    if re.match(r"^\s{2,}\S", body) or re.match(r"^\s*(Calculations|Power|Rolls|Beat \d|- )", body):
        return "mech"
    return "story"


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def spans(line):
    """[(start, end, tag)] to colour inside one line of numbers: the row's name and its change, the outcome of a
    roll, the figure a roll had to beat."""
    out = []
    m = NUM_ROW.match(line)
    if m:
        tag = {"damage": "dmg", "resistance": "res", "health": "hp"}[m.group(1)]
        out.append((m.start(1), m.end(1), tag))
        d = re.search(r"\s([+-]\d[\d.]*)\s", line[m.end():])
        if d:
            out.append((m.end() + d.start(1), m.end() + d.end(1), tag + "bold"))
    for r in re.finditer(r"(\d+(?:\.\d+)?)%, rolled (\d+) → (.+)$", line):
        # (it happened when the roll came in under the chance)
        out.append((r.start(2), r.end(2), "mechbold"))
        out.append((r.start(3), r.end(3), "hit" if float(r.group(2)) < float(r.group(1)) else "miss"))
    return out


# ---- hover tips: the word under the mouse, and where its number comes from ----
TERMS = [
    ("roll", re.compile(r"\(rolled ×\d[\d.]*\)")),
    ("scale", re.compile(r"× scale \d[\d.]*")),
    ("vital", re.compile(r"× vital \d[\d.]*")),
    ("res_scale", re.compile(r"× \d[\d.]* resistance scale")),
    ("grind", re.compile(r"\(a submission grinds it down\)|\(a hold wears it first\)|\(a part that starts soft wears in proportion\)")),
    ("res_cap", re.compile(r"\(capped: at most [\d.]+ a hit\)")),
    ("floor", re.compile(r"\(it can't go lower\)")),
    ("curve", re.compile(r"past 300% its number climbs slowly")),
    ("pin_cap", re.compile(r"\(pin cap\)")),
    ("softened", re.compile(r"\(softened from [\d.]+\)")),
    ("pain", re.compile(r"pain \d+ against her resistance \d+")),
    ("air", re.compile(r"the choke built to \d+ against her endurance \d+|it has built to \d+ against her endurance \d+")),
    ("exertion", re.compile(r"-[\d.]+% exertion")),
    ("injuries", re.compile(r"-[\d.]+% injuries")),
    ("roll_rule", re.compile(r"a roll under the chance succeeds")),
    ("ramp", re.compile(r"power [\d.]+ each beat, (?:tightening|easing) [+-][\d.]+ a beat|power [\d.]+ each beat, steady")),
    ("move_power", re.compile(r"Power \*{0,2}\d[\d.]*\*{0,2} = base [\d.]+")),
    ("break_roll", re.compile(r"breaking \S+ hold on her [\d.]+%")),
]


def terms(line):
    """[(start, end, key)] for the words in a line of numbers that have a hover tip."""
    out = []
    for key, rx in TERMS:
        for m in rx.finditer(line):
            out.append((m.start(), m.end(), key))
    m = NUM_ROW.match(line)
    if m:
        out.append((m.start(1), m.end(1), "row_" + m.group(1)))
    return out


def term_key(word):
    """Which tip a term's own words belong to (the window knows the underlined words, not where they sat)."""
    w = (word or "").strip()
    if w in ("damage", "resistance", "health"):
        return "row_" + w
    return next((k for k, rx in TERMS if rx.fullmatch(w)), None)


def curve_mults(rules, res):
    """(damage mult, health mult) at this resistance, from resistance.smooth.points (as the engine works it out)."""
    pts = sorted((float(a), float(b), float(c)) for a, b, c in
                 (_get(rules, "resistance.smooth.points", None) or [[15, 0.9, 2.6], [120, 0.1, 0.47]]))
    x = float(res)
    if x <= pts[0][0]:
        return pts[0][1], pts[0][2]
    if x >= pts[-1][0]:
        return pts[-1][1], pts[-1][2]
    for (x0, m0, h0), (x1, m1, h1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return m0 + (m1 - m0) * t, h0 + (h1 - h0) * t
    return pts[-1][1], pts[-1][2]


def tip(key, line, rules):
    """The hover tip for one term: what the number is and which setting it comes from."""
    g = lambda p, d: _get(rules, p, d)
    tap = "finish.submission.tap"
    tips = {
        "row_damage": "How hurt the part is (0% = unhurt; past 300% devastated). The change is this hit: its power × "
                      "how much the part takes at its resistance × the damage scale.",
        "row_resistance": "How tough the part still is. Every hit wears it down, and the lower it gets, the more each "
                          "later hit does to the part and to her health (resistance.smooth.points).",
        "row_health": "Her overall health, the sum of everything she has taken. The change is the part's damage × "
                      f"{g('health.loss_per_damage_point', 1.84)} (health.loss_per_damage_point) × how much the worn part "
                      "costs × how vital the part is.",
        "roll": f"The damage dice: every hit lands a little harder or softer than its number, up to "
                f"±{num(100 * float(g('damage.roll', 0.17)))}% (damage.roll).",
        "scale": f"The damage scale for every hit in the game (damage.damage_scale = {g('damage.damage_scale', 3)}).",
        "vital": "How much this part matters to the whole body (health.part_weights): the neck 1.6, the chest 1.4, a "
                 "knee 0.5, a paw or the tail 0.4.",
        "res_scale": f"How fast resistance wears for every hit in the game (damage.resistance_scale = "
                     f"{g('damage.resistance_scale', 0.7)}), after power × {g('resistance.loss_per_power', 0.3)} "
                     f"(resistance.loss_per_power).",
        "grind": f"A submission wears the part ×{g('submissions.grind.wear_mult', 2)} as fast (submissions.grind); any "
                 f"other hold ×{g('holds.slow_bite.wear_mult', 1.4)} (holds.slow_bite): holds soften the part before "
                 "they tear into it. A part that starts soft wears in proportion to what it has (resistance.relative).",
        "res_cap": f"No single hit wears a part more than {g('resistance.max_loss_per_hit', 35)} "
                   "(resistance.max_loss_per_hit, scaled the same way as the wear).",
        "floor": f"Resistance never goes below {g('resistance.minimum', 0)} (resistance.minimum).",
        "curve": f"Up to {g('damage.part_curve.knee', 300)}% the part's number takes a hit in full; past it, ever more "
                 "slowly (damage.part_curve), so a ruined part's number doesn't run away. Her health still takes the "
                 "full hit.",
        "pin_cap": "A pin's steady pressure (or a submission) doesn't tear into a worn part the way a blow does: its "
                   "multiplier is capped (pin.pressure_cap, submissions.damage_cap).",
        "softened": f"The soft cap: no single hit takes more than about {num(100 * float(g('health.soft_cap.per_hit', 0.05)))}% "
                    f"of her full health, and no beat more than {num(100 * float(g('health.soft_cap.per_beat', 0.12)))}%, "
                    "before it is softened (health.soft_cap). Part of what is softened wears the part instead.",
        "pain": f"PAIN = the gripped part's damage + {g(tap + '.second_part', 0.4)} × the other gripped parts + "
                f"{g(tap + '.per_beat', 15)} for each beat after the first + {g(tap + '.press', 1.5)} × the grip's "
                f"pressure. HER RESISTANCE = {g(tap + '.resist', 160)} × her health share ^ "
                f"{g(tap + '.resist_power', 0.8)} (×{g(tap + '.surge_resist', 1.5)} on an adrenaline surge). Only pain "
                "past it can make her tap, and never on the first beat it gets there.",
        "air": f"AIR = {g('finish.submission.choke.air_per_beat', 22)} for every beat of the choke. ENDURANCE = "
               f"{g('finish.submission.choke.endurance', 110)} × her health share ^ {g(tap + '.resist_power', 0.8)}. "
               f"Past it: chance = how far past ÷ {g('finish.submission.choke.span', 70)}, at most "
               f"{num(100 * float(g('finish.submission.choke.max', 0.85)))}% (finish.submission.choke).",
        "exertion": f"Fighting costs {g('health.exhaustion_per_beat', 0.5)} health every beat (health.exhaustion_per_beat).",
        "injuries": "Badly hurt parts drain her every beat: 0.4 for a part past 60% damage, 0.9 past 90%, 2.0 past "
                    "150% (health.pain_drain).",
        "roll_rule": "Every chance is rolled from 0 to 99: under the chance, it happens. The dice are the fight's own, "
                     "so /undo and /reroll can replay or change them.",
        "ramp": "The grip's pressure, before the part's resistance and the damage scale. Each beat it changes by its "
                "ramp; a hold kept on also bites a little deeper (holds.build), and a near-miss escape works it looser.",
        "move_power": "The move's power: its base (moves.json) × the type matchup × how it was aimed (targeted, spread, "
                      "whole body) × anything else listed. It is then rolled and split across the parts it hits.",
        "break_roll": "Her chance of breaking out: it goes by her health share (submissions.escape.points), grows the "
                      "longer she tries (grow), and drops while the hold is fresh and tight.",
    }
    return tips.get(key, "")


# ---- the pointers: a short note under a set of numbers, now and then ----
class Pointers:
    """Notes saying where the numbers just shown come from, with those numbers in them. "occasional" (the default):
    each kind of note once, then again only when pointer_gap beats have passed; "always": every time; "off": none.
    feed(line) -> the notes to put under that line."""

    def __init__(self, rules):
        self.rules = rules or {}
        o = opts(self.rules)
        self.mode = str(o.get("pointers", "occasional")).lower()
        self.gap = int(o.get("pointer_gap", 6) or 0)
        self.beat, self.last, self.rows = 0, {}, {}

    def _due(self, key):
        if self.mode in ("off", "false", "none", "0"):
            return False
        if self.mode != "always" and key in self.last and self.beat - self.last[key] < self.gap:
            return False
        self.last[key] = self.beat
        return True

    def feed(self, line):
        g = lambda p, d: _get(self.rules, p, d)
        out = []
        m = re.match(r"^⏳ Beat (\d+) health", line.strip())
        if m:
            self.beat = int(m.group(1))
            if ("exertion" in line or "injuries" in line) and self._due("beat_health"):
                out.append(f"Health each beat: -{g('health.exhaustion_per_beat', 0.5)} for fighting, and a drain from "
                           "every badly hurt part (health.pain_drain).")
            return out
        if PART_ROW.match(line):
            self.rows = {}
            return out
        r = NUM_ROW.match(line)
        if r:
            self.rows[r.group(1)] = line
            if r.group(1) == "health" and "damage" in self.rows and "resistance" in self.rows:
                note = self._part_note()
                if note and self._due("part_rows"):
                    out += note
            return out
        if re.search(r"refuses to tap in|fights the dark in", line) and self._due("tap_resist"):
            out += self._tap_note(line)
        elif re.search(r"TAPS OUT\*{0,2}(?: \(tap \d+ of \d+[^)]*\))? in", line) and self._due("tap_out"):
            out += self._tap_note(line)
        elif re.search(r"PASSES OUT\*{0,2} in", line) and self._due("pass_out"):
            m2 = re.search(r"built to (\d+) against her endurance (\d+): chance (\d+)%", line)
            if m2:
                out.append(f"The choke: air {m2.group(1)} = {g('finish.submission.choke.air_per_beat', 22)} a beat; "
                           f"her endurance {m2.group(2)} = {g('finish.submission.choke.endurance', 110)} × her health "
                           f"share ^ {g('finish.submission.tap.resist_power', 0.8)}. Chance = ({m2.group(1)} - "
                           f"{m2.group(2)}) ÷ {g('finish.submission.choke.span', 70)} = {m2.group(3)}%.")
        elif "a roll under the chance succeeds" in line and self._due("rolls"):
            out.append("Each line below is one chance and its roll (0-99): under the chance, it happens.")
        elif re.match(r"^\s+Power \*{0,2}\d", line) and self._due("move_power"):
            out.append("A blow's power: the move's base power (moves.json) × the type matchup × how it was aimed; the "
                       "rows below roll it and run it through each part's resistance.")
        elif re.search(r"each beat, (?:tightening|easing|steady)", line) and self._due("hold_power"):
            out.append("A grip's power: a submission starts at 16 on its main grip and 9 on the others, climbing +3 / "
                       "+1 a beat (submissions.power, ramp); other holds go by their severity (light 8, firm 15, "
                       "crushing 25: severity.hold).")
        elif re.search(r"hold looser\*{0,2} on", line) and self._due("loosen"):
            out.append(f"A near miss on the break-free roll: the grip presses at ×{g('holds.break.loosen_mult', 0.75)} "
                       "from the next beat.")
        return out

    def _part_note(self):
        g = lambda p, d: _get(self.rules, p, d)
        d, rs, h = self.rows["damage"], self.rows["resistance"], self.rows["health"]
        md = re.search(r"\+([\d.]+) = power ([\d.]+)(?: \(rolled ×([\d.]+)\))? × ([\d.]+)(?: \(pin cap\))?(?: × scale ([\d.]+))?", d)
        mr = re.search(r"([\d.]+)% → \S* ?([\d.]+)%", rs)
        mh = re.search(r"-([\d.]+) = damage ([\d.]+) × ([\d.]+) × ([\d.]+)(?: × vital ([\d.]+))?", h)
        if not (md and mr and mh):
            return []
        add, power, roll, mult, scale = md.groups()
        res_b = float(mr.group(1))
        base, hbase = curve_mults(self.rules, res_b)
        why = (f" (the curve gives ×{num(base)} at that resistance; the kind of hit changed it: a submission's grind "
               f"starts low on a sound part, a hold bites slowly, a soft part takes more, a pin is capped)"
               if abs(base - float(mult)) > 0.015 else "")
        lines = [f"Damage +{add} = the hit's power {power}" + (f" (the dice moved it ×{roll})" if roll else "")
                 + f" × {mult}, what this part takes at its resistance of {num(res_b)}%{why}"
                 + (f" × the damage scale {scale}" if scale else "") + "."]
        loss = re.search(r"-([\d.]+)", rs[mr.end():])
        if loss:
            lines.append(f"Resistance -{loss.group(1)}: the part wears by power × {g('resistance.loss_per_power', 0.3)} × "
                         f"{g('damage.resistance_scale', 0.7)}, faster in a hold; the lower it falls, the harder the "
                         "next hit lands.")
        hl, dd, hpd, hm, vital = mh.groups()
        lines.append(f"Health -{hl} = damage {dd} × {hpd} per point × {hm} (a worn part costs more: ×{num(hbase)} at "
                     f"this resistance" + (f", at most ×{g('holds.health_cap.health_mult', 1.1)} in a hold"
                                           if abs(hbase - float(hm)) > 0.015 else "") + ")"
                     + (f" × {vital} for how vital the part is" if vital else "") + ".")
        return lines

    def _tap_note(self, line):
        g = lambda p, d: _get(self.rules, p, d)
        t = "finish.submission.tap"
        m = re.search(r"pain (\d+) against her resistance (\d+)", line)
        if not m:
            return []
        out = [f"Pain {m.group(1)} = the gripped part's damage + {g(t + '.second_part', 0.4)} × the other gripped parts "
               f"+ {g(t + '.per_beat', 15)} a beat + {g(t + '.press', 1.5)} × the grip's pressure. Her resistance "
               f"{m.group(2)} = {g(t + '.resist', 160)} × her health share ^ {g(t + '.resist_power', 0.8)}."]
        c = re.search(r"tap-out chance (\d+)%", line)
        out.append(f"The chance: (pain - resistance) ÷ {g(t + '.span', 160)}, under a ceiling that starts at "
                   f"{num(100 * float(g(t + '.climb.start', 0.2)))}% and rises "
                   f"{num(100 * float(g(t + '.climb.per_beat', 0.1)))}% a beat, kept lower while she is strong"
                   + (f": {c.group(1)}% this time." if c else "; never on the first beat past her limit."))
        return out
