"""
Prints the stat blocks in your format, straight from engine numbers.
Resistance uses colored squares, damage uses colored circles, and the heart is only ever health.
"""
from engine import tier_for, pain_tiers, poss_word


def num(x):
    """40 -> '40', 6.0 -> '6', 5.55 -> '5.55', 12.8 -> '12.8'."""
    s = f"{float(x):.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def pct(health, max_health=None):
    """Health is itself a percentage (1800%, -1003%), so show the raw value."""
    return num(health) + "%"


# short words for HOW an outcome played out (the engine's pick; see rules.json "variety"), by kind of outcome
WAYS = {
    "charge_stands": {"staggers": "staggers clear", "leans": "sags upright against it, then pushes off",
                      "knee": "a knee touches down; she shoves back up", "rebounds": "rebounds off it and stumbles forward"},
    "dodge": {"sidestep": "slips aside", "duck": "ducks under it", "spring_back": "springs back",
              "turn_aside": "turns it aside", "twist": "twists out of its line"},
    "hold_break": {"wrench": "one hard wrench", "pry": "pries it open", "slip": "slips out as it shifts",
                   "shove": "shoves her back"},
    "hold_strain": {"pry": "pries at it", "twist": "twists against it", "claw": "claws at it and the ground",
                    "brace": "braces and strains"},
    "struggle": {"buck": "bucks", "bridge": "bridges", "twist": "twists to one side", "limb": "wrenches at a trapped limb",
                 "kick": "kicks out", "squirm": "tries to slide out"},
    "getup_fail": {"gives_out": "a hurt limb gives out", "slips": "her footing slips", "dizzy": "everything tilts",
                   "breath": "no air for it"},
    "getup_rise": {"push": "pushes straight up", "roll": "rolls onto her front first", "lean": "climbs what she leans on",
                   "lurch": "one ugly heave"},
}


def way(kind, key, lead=" · how: "):
    text = WAYS.get(kind, {}).get(key)
    return f"{lead}{text}" if text else ""


def poss_name(n):
    return n + ("'" if n.endswith("s") else "'s")


class Display:
    def __init__(self, rules):
        self.rules = rules
        self.heart = rules["health"].get("icon", "❤️")

    STATUS_WORD = {"fury": "furious", "doubled_over": "doubled over", "off_balance": "off balance",
                   "protecting": "protected", "countering": "set to counter", "mirroring": "coated in a mirror sheen"}

    @staticmethod
    def _grip_words(oc):
        """" (her jaws, closed on the throat)" or " (her knees on her Chest)": the part only when the grip doesn't
        already name it."""
        part, w = str(oc.get("part") or ""), str(oc.get("with") or "")
        if not part:
            return ""
        if not w:
            return f" (her {part})"
        return f" ({w})" if part.lower() in w.lower() else f" ({w} on her {part})"

    def sw(self, status):
        """A status as words ("doubled over", not "doubled_over")."""
        return self.STATUS_WORD.get(status, str(status).replace("_", " "))

    STATUS_ICON = {"bound": "🪢", "fury": "😤", "breathless": "😮", "dazed": "💫", "doubled_over": "🤕", "off_balance": "🌀", "protecting": "🛡️", "countering": "↩️", "mirroring": "🪞", "stiff": "🪵", "cramped": "🦵", "sputtering": "💦", "constricted": "🐍", "airborne": "🪽",
                   "paralyzed": "⚡", "chilled": "❄️", "soaked": "💧", "flinched": "😵", "reeling": "🌀", "adrenaline": "🔥",
                   "asleep": "💤", "restrained": "🔗", "frozen": "🧊", "confused": "💫", "burned": "♨️", "poisoned": "☠️"}

    def _status_tag(self, f):
        bits = [f"{self.STATUS_ICON.get(s, '')}{s} {n}" for s, n in f.status.items()]
        return f" · energy {num(round(f.energy))}" + (" · " + ", ".join(bits) if bits else "")

    def layout(self):
        """console.layout: 'clear' (two labelled lines per hit, blocks spaced out), 'tight' (one row per hit, no
        labels) or 'classic' (the long Before / Calculations / After blocks)."""
        word = str(self.rules.get("console", {}).get("layout", "clear")).lower()
        return word if word in ("clear", "tight", "classic") else "clear"

    def tight(self):
        return self.layout() == "tight"

    def clear(self):
        return self.layout() == "clear"

    KEY_TIGHT = ("Stat rows: part | resistance before → after | damage before → after | power × resistance multiplier "
                 "× damage scale = damage dealt | health lost (× the part's health multiplier)")
    KEY_CLEAR = ("How to read a hit: three rows under the part's name, each as before → after, then the change and "
                 "where it comes from.\n  damage: power × the part's resistance multiplier (🟦 0.20 … weaker parts take "
                 "more) × your damage scale.\n  resistance: power × the resistance loss rate (× your resistance scale)."
                 "\n  health: the damage added × health per damage point × the part's health multiplier.")

    @property
    def KEY(self):
        return self.KEY_CLEAR if self.clear() else self.KEY_TIGHT

    def move_lines_clear(self, m, every_beat=False):
        """The power of a move, one step per line."""
        lpp = self._lpp()
        verdict = {"super effective": ", super effective!", "not very effective": ", not very effective",
                   "no effect": ", no effect!"}.get(m["effectiveness"], "")
        bits = [f"base {num(m['base'])}", f"{num(m['type_mult'])} ({m['vs']}{verdict})",
                f"{num(m['target_mult'])} ({m['target'].replace('_', '-')})"]
        if m.get("stab", 1) != 1:
            bits.append(f"{num(m['stab'])} (same type)")
        bits += [f"{num(x)} ({label})" for label, x in m.get("extras", [])]
        out = [f"  Power **{num(m['effective'])}**" + (" every beat" if every_beat else "") + " = " + " × ".join(bits)]
        if m.get("spillover_parts"):
            out.append(f"  Carry-over to {', '.join(m['spillover_parts'])}: power {num(m['spillover_effective'])}")
        if m.get("auto_spill_parts"):
            out.append(f"  Jarred next to it ({', '.join(m['auto_spill_parts'])}): power "
                       f"{num(m['auto_spill_effective'])} (×{num(m.get('auto_spill_factor', 0.5))})")
        return out

    def clear_block(self, defender, hits, move=None, tags=None, every_beat=False):
        """The clear layout: each hit on two labelled lines (what changed, then the math), grouped under what
        caused it (the charge, the slam, pulse 2...), with a blank line between groups."""
        out = self.move_lines_clear(move, every_beat) if move else []
        order = list(dict.fromkeys(h["part"] for h in hits))
        per_part = {p: sum(1 for h in hits if h["part"] == p) for p in order}
        total = sum(h["damage_taken"] for h in hits)
        lost = hits[0]["health_before"] - hits[-1]["health_after"]
        foot = (f"  Total: +{num(total)}% damage  ·  {self.heart} {defender} {pct(hits[0]['health_before'])} → "
                f"**{pct(hits[-1]['health_after'])}** (-{num(lost)})")
        if len(order) > 8 and all(v == 1 for v in per_part.values()) and not tags:
            return (out + ["", f"  {len(order)} parts of {defender} hit:"]
                    + ["  " + x for x in self.grouped_block(defender, hits)[1:]] + ["", foot])
        groups, seen = {}, {}
        for h in hits:
            groups.setdefault((tags or {}).get(id(h), ""), []).append(h)
        lpp0 = float(self.rules["resistance"]["loss_per_power"])
        hpd = float(self.rules["health"].get("loss_per_damage_point", 1.0))
        cells = []   # (before → after) texts, to line the working up in one column
        for h in hits:
            cells += [f"{self.dmg_icon(h['damage_before'])} {num(h['damage_before'])}% → "
                      f"{self.dmg_icon(h['damage_after'])} {num(h['damage_after'])}%",
                      f"{self.res_icon(h['res_before'])} {num(h['res_before'])}% → {self.res_icon(h['res_after'])} "
                      f"{num(h['res_after'])}%",
                      f"{self.heart} {pct(h['health_before'])} → {self.heart} {pct(h['health_after'])}"]

        def wide(c):  # width on screen: the ** marks aren't printed, and the coloured icons take two columns
            return sum(0 if ch in "*\ufe0f" else 2 if (ord(ch) >= 0x1F000 or ch in "⚫⚪❤") else 1 for ch in c)

        def pad(c):
            return c + " " * max(0, col - wide(c))
        col = min(40, max(wide(c) for c in cells))
        k = 0
        for tag, hs in groups.items():
            if out:
                out.append("")
            if tag:
                out.append(f"  ▸ {tag}")
            for h in hs:
                seen[h["part"]] = seen.get(h["part"], 0) + 1
                label = h["part"] if per_part[h["part"]] == 1 else f"{h['part']} (hit {seen[h['part']]})"
                sc = "" if h.get("scale", 1) == 1 else f" × scale {num(h['scale'])}"
                rs = h.get("res_scale", 1)
                loss = h["res_before"] - h["res_after"]
                lpd0 = float(self.rules["resistance"].get("loss_per_damage", 0) or 0)   # wear by the damage done (/wear)
                ro = float(h.get("res_overflow") or 0)
                full = (h["power"] * lpp0 + h["damage_taken"] * lpd0) * rs + ro
                how_res = ((f"= power {num(h['power'])} × {num(lpp0)}" if not lpd0 else
                            f"= (power {num(h['power'])} × {num(lpp0)} + damage {num(h['damage_taken'])} × {num(lpd0)})")
                           + ("" if rs == 1 else f" × {num(rs)} resistance scale")
                           + (f" + {num(ro)} from the softened health" if ro > 0.005 else "")
                           if abs(full - loss) < 0.03 else "(it can't go lower)")
                dmg, res, hp = cells[k:k + 3]
                k += 3
                out.append(f"    {label}")
                out.append(f"        damage      {pad(dmg)}   +{num(h['damage_taken'])} = power {num(h['power'])} × "
                           f"{h['mult']:.2f}{' (pin cap)' if h.get('capped') else ''}{sc}")
                out.append(f"        resistance  {pad(res)}   -{num(loss)} {how_res}")
                if "health_loss" in h:
                    out.append(f"        health      {pad(hp)}   -{num(h['health_loss'])} = damage "
                               f"{num(h['damage_taken'])} × {num(hpd)} × {num(h['health_mult'])}"
                               + (f" × vital {num(h['vital'])}" if h.get("vital", 1.0) != 1.0 else "")
                               + (f" (softened from {num(h['health_raw'])})" if h.get("softened") else ""))
        out += ["", foot]
        return out

    @staticmethod
    def _wrap(items, width=112, indent="  ", sep="  ·  "):
        """Pack short items onto as few lines as fit."""
        lines, cur = [], ""
        for it in items:
            if cur and len(cur) + len(sep) + len(it) > width:
                lines.append(indent + cur)
                cur = it
            else:
                cur = it if not cur else cur + sep + it
        if cur:
            lines.append(indent + cur)
        return lines

    def soft_wrap(self, text, width=100):
        """Clear layout: a line too long for the window is broken at a word, with the rest indented under it, so
        the console doesn't chop it mid-word."""
        if not self.clear() or not text:
            return text
        import textwrap
        out = []
        for line in text.split("\n"):
            if len(line) <= width:
                out.append(line)
                continue
            lead = len(line) - len(line.lstrip())
            out += textwrap.wrap(line, width=width, subsequent_indent=" " * (lead + 6), break_long_words=False,
                                 break_on_hyphens=False) or [line]
        return "\n".join(out)

    def part_item(self, name, res, dmg):
        return f"{name} {self.res_icon(res)}{num(res)}% {self.dmg_icon(dmg)}{num(dmg)}%"

    def move_line_tight(self, m):
        """Slash: base 30 × Normal vs Water 1 × targeted 2 = power 60 (res loss 15) · jarred Chest, Neck ×0.5 = 15 ..."""
        lpp = self._lpp()
        verdict = {"super effective": " (super effective!)", "not very effective": " (not very effective)",
                   "no effect": " (no effect!)"}.get(m["effectiveness"], "")
        bits = [f"base {num(m['base'])}", f"{m['vs']} ×{num(m['type_mult'])}{verdict}",
                f"{m['target'].replace('_', '-')} ×{num(m['target_mult'])}"]
        if m.get("stab", 1) != 1:
            bits.append(f"same type ×{num(m['stab'])}")
        bits += [f"{label} ×{num(x)}" for label, x in m.get("extras", [])]
        out = (f"  Power: " + " · ".join(bits) + f" → **{num(m['effective'])}** (res loss {num(m['effective'] * lpp)}"
               f" = power × {num(lpp)})")
        if m.get("spillover_parts"):
            out += (f" · carry-over to {', '.join(m['spillover_parts'])} ×1 → {num(m['spillover_effective'])} "
                    f"(res loss {num(m['spillover_effective'] * lpp)})")
        if m.get("auto_spill_parts"):
            out += (f" · jarred {', '.join(m['auto_spill_parts'])} ×{num(m.get('auto_spill_factor', 0.5))} → "
                    f"{num(m['auto_spill_effective'])} (res loss {num(m['auto_spill_effective'] * lpp)})")
        return out

    def rows_block(self, defender, hits, move=None, tags=None):
        """The tight layout: every hit on one row, with what it was before, what it is after, and the math.
        tags: optional {id(hit): label} for rows that need saying where they came from (slam, crush, pulse 2...)."""
        out = [self.move_line_tight(move)] if move else []
        order = list(dict.fromkeys(h["part"] for h in hits))
        per_part = {p: sum(1 for h in hits if h["part"] == p) for p in order}
        total = sum(h["damage_taken"] for h in hits)
        lost = hits[0]["health_before"] - hits[-1]["health_after"]
        foot = (f"  Σ +{num(total)}% damage · {self.heart} {defender} {pct(hits[0]['health_before'])} → "
                f"**{pct(hits[-1]['health_after'])}** (-{num(lost)})")
        if len(order) > 8 and all(v == 1 for v in per_part.values()) and not tags:
            return out + [f"  {len(order)} parts of {defender} hit:"] + self.grouped_block(defender, hits)[1:] + [foot]
        rows, seen = [], {}
        for h in hits:
            seen[h["part"]] = seen.get(h["part"], 0) + 1
            label = h["part"] if per_part[h["part"]] == 1 else f"{h['part']} (hit {seen[h['part']]})"
            rs = "" if h.get("res_scale", 1) == 1 else f" (×{num(h['res_scale'])} res scale)"
            sc = "" if h.get("scale", 1) == 1 else f" × {num(h['scale'])}"
            rows.append((
                label,
                f"{self.res_icon(h['res_before'])} {num(h['res_before'])} → {self.res_icon(h['res_after'])} "
                f"{num(h['res_after'])}%{rs}",
                f"{self.dmg_icon(h['damage_before'])} {num(h['damage_before'])} → {self.dmg_icon(h['damage_after'])} "
                f"**{num(h['damage_after'])}%**",
                f"{num(h['power'])} × {h['mult']:.2f}{sc} = +{num(h['damage_taken'])}%",
                (f"{self.heart} -{num(h['health_loss'])} (×{num(h['health_mult'])}"
                 + (f", vital ×{num(h['vital'])}" if h.get("vital", 1.0) != 1.0 else "") + ")" if "health_loss" in h else ""),
                (tags or {}).get(id(h), "")))
        widths = [max(len(r[i]) for r in rows) for i in range(6)]
        for r in rows:
            out.append(("  " + "   ".join(c.ljust(w) for c, w in zip(r, widths))).rstrip())
        out.append(foot)
        return out

    def rolls_line(self, rolls, nudges=()):
        """Every chance the dice decided this beat (a roll under the chance succeeds), and what the director was
        pointed at."""
        out = []
        if rolls:
            items = [f"{r['what']} → {r['result']}" if r.get("plain") else
                     f"{r['what']} {r['chance'] * 100:.0f}%, rolled {r['roll'] * 100:.0f} → {r['result']}" for r in rolls]
            if self.tight():
                lines = self._wrap(items, width=118, indent="   ", sep=" · ")
                out += ["🎲 Rolls: " + lines[0].strip()] + lines[1:]
            elif self.clear():
                out += ["🎲 **Rolls** (a roll under the chance succeeds)"] + ["    " + x for x in items]
            else:
                out += ["🎲 **Rolls** (a roll under the chance succeeds):"] + ["- " + x for x in items]
        if nudges and self.clear():
            out += ["💡 **Director was pointed at**"] + ["    " + x for x in nudges]
        elif nudges:
            out.append("💡 Director was pointed at: " + " · ".join(nudges))
        return self.soft_wrap("\n".join(out))

    def _lpp(self):
        """Resistance lost per point of power, including the resistance scale."""
        return self.rules["resistance"]["loss_per_power"] * float(self.rules.get("damage", {}).get("resistance_scale", 1.0))

    def res_icon(self, res):
        return tier_for(res, self.rules["resistance"]["brackets"])["icon"]

    def dmg_icon(self, dmg):
        return tier_for(dmg, pain_tiers(self.rules))["icon"]

    def part_line(self, name, res, dmg):
        return f"- {name}: {self.res_icon(res)} {num(res)}% | {self.dmg_icon(dmg)} {num(dmg)}%"

    def calc_line(self, h, label):
        loss = h["res_before"] - h["res_after"]
        return (f"- {label}: Res {num(h['res_before'])}% ({h['bracket']} bracket, {h['mult']:.2f}× mult). "
                f"Damage: {num(h['power'])} × {h['mult']:.2f}"
                f"{'' if h.get('scale', 1) == 1 else ' × ' + num(h['scale']) + ' scale'} = {num(h['damage_taken'])}%. "
                f"New damage: {num(h['damage_before'])} + {num(h['damage_taken'])} = **{num(h['damage_after'])}%**. "
                f"Res: {num(h['res_before'])} - {num(loss)}"
                f"{'' if h.get('res_scale', 1) == 1 else ' (×' + num(h['res_scale']) + ' res scale)'} = **{num(h['res_after'])}%**"
                + (f". Health -{num(h['health_loss'])}% (×{num(h['health_mult'])} for a {h['bracket']} part"
                   + (f", ×{num(h['vital'])} for how vital it is" if h.get("vital", 1.0) != 1.0 else "") + ")"
                   if "health_loss" in h else ""))

    def move_line(self, m):
        """Base 40, Water vs Dark ×1, spread ×1 → Effective 40. Res loss 32 each."""
        loss = num(m["effective"] * self._lpp())
        stab = f", same type ×{num(m['stab'])}" if m.get("stab", 1) != 1 else ""
        verdict = {"super effective": " (super effective!)", "not very effective": " (not very effective)",
                   "no effect": " (no effect!)"}.get(m["effectiveness"], "")
        spill = ""
        if m.get("spillover_parts"):
            spill = (f" Carry-over to {', '.join(m['spillover_parts'])}: ×1 → Effective "
                     f"{num(m['spillover_effective'])}, res loss "
                     f"{num(m['spillover_effective'] * self._lpp())}.")
        if m.get("auto_spill_parts"):
            spill += (f" Jarred next to it: {', '.join(m['auto_spill_parts'])}: ×{num(m.get('auto_spill_factor', 0.5))} "
                      f"→ Effective {num(m['auto_spill_effective'])}, res loss "
                      f"{num(m['auto_spill_effective'] * self._lpp())}.")
        xs = "".join(f" × {num(x)} ({label})" for label, x in m.get("extras", []))
        return (f"Calculations: Base {num(m['base'])}, {m['vs']} ×{num(m['type_mult'])}{verdict}, "
                f"{m['target'].replace('_', '-')} ×{num(m['target_mult'])}{stab}{xs} → Effective {num(m['effective'])}. "
                f"Res loss {loss}{'' if spill else ' each'} (power × {num(self._lpp())}; the damage scale doesn't change it).{spill}")

    def grouped_block(self, defender, hits):
        """Whole-body attacks: group the parts that shared the same starting resistance."""
        groups = {}
        for h in hits:
            groups.setdefault((h["res_before"], h["mult"], h["damage_taken"], h["res_after"]), []).append(h)
        out = ["**Grouped by resistance:**"]
        for (rb, mult, taken, ra), hs in sorted(groups.items(), key=lambda kv: -kv[0][0]):
            sc = hs[0].get("scale", 1)
            out.append(f"- Res {num(rb)}% {self.res_icon(rb)} → {num(ra)}% {self.res_icon(ra)} ({len(hs)}), {mult:.2f}×"
                       f"{'' if sc == 1 else ' ×' + num(sc) + ' scale'}, +{num(taken)}% each: "
                       + ", ".join(f"{h['part']} {num(h['damage_before'])}→{num(h['damage_after'])}%"
                                   f"{self.dmg_icon(h['damage_after'])}" for h in hs))
        return out

    def hits_block(self, defender, hits, move=None, tags=None):
        if self.tight():
            return self.rows_block(defender, hits, move, tags)
        if self.clear():
            return self.clear_block(defender, hits, move, tags)
        first, last, order = {}, {}, []
        for h in hits:
            if h["part"] not in first:
                first[h["part"]] = h
                order.append(h["part"])
            last[h["part"]] = h
        per_part = {p: sum(1 for h in hits if h["part"] == p) for p in order}
        total = sum(h["damage_taken"] for h in hits)
        mx = hits[0]["max_health"]
        health_line = (f"- Total inflicted: {num(total)}% → Health loss {num(hits[0]['health_before'] - hits[-1]['health_after'])}%"
                       f"\n- {self.heart} {defender} Health: {pct(hits[0]['health_before'], mx)} → "
                       f"**{pct(hits[-1]['health_after'], mx)}**")
        if len(order) > 8 and all(v == 1 for v in per_part.values()):
            out = [f"**Before:** ({defender}) {len(order)} parts hit"]
            if move:
                out.append(self.move_line(move))
            out += self.grouped_block(defender, hits)
            out.append(health_line)
            return out

        out = [f"**Before:** ({defender})"]
        out += [self.part_line(p, first[p]["res_before"], first[p]["damage_before"]) for p in order]
        out.append("")
        out.append(self.move_line(move) if move else "**Calculations:**")
        seen = {}
        for h in hits:
            seen[h["part"]] = seen.get(h["part"], 0) + 1
            label = h["part"] if per_part[h["part"]] == 1 else f"{h['part']} (hit {seen[h['part']]})"
            out.append(self.calc_line(h, label))
        out.append("")
        out.append("**After:**")
        out += [self.part_line(p, last[p]["res_after"], last[p]["damage_after"]) for p in order]
        out.append(health_line)
        return out

    @staticmethod
    def knock_on_lines(events):
        """What a fall, a throw, a takedown, or falling asleep knocked loose."""
        out = []
        for k in events:
            if k["type"] == "pin_broken":
                out.append(f"💥 **{k['attacker']}'s pin on {k['defender']} is broken** after {num(k['seconds'])} s: "
                           f"{k['why']}")
            elif k["type"] == "pin_left":
                out.append(f"💥 **{k['attacker']} is off the pin on {k['defender']}** ({k['why']}); "
                           f"{' and '.join(k['still'])} still {'has' if len(k['still']) == 1 else 'have'} her pinned at "
                           f"{num(k['seconds'])} s")
            elif k["type"] == "flattened":
                out.append(f"⬇️ **{k['fighter']} is knocked flat** from sitting: now {k['facing']}")
            elif k["type"] == "hold_end" and k.get("shaken"):
                out.append(f"💥 **The hit breaks {k['attacker']}'s hold** on {k['defender']}'s {k['part']} "
                           f"(#{k['hold_id']}) after {k['beats_held']} beat{'s' if k['beats_held'] != 1 else ''} — "
                           f"{k['reason']} (chance to lose it {k['chance'] * 100:.0f}%)")
            elif k["type"] == "hold_end":
                out.append(f"🔓 **{k['attacker']} loses her grip** on {k['defender']}'s {k['part']} "
                           f"(#{k['hold_id']}): {k['reason']}")
            elif k["type"] == "slumps":
                out.append(f"💤 **{k['fighter']} slumps to the ground**" + (f" ({k['facing']})" if k.get("facing") else ""))
        return out

    def pin_block(self, e):
        a, d = e["attacker"], e["defender"]
        if e.get("helpers"):
            a = " and ".join([a] + list(e["helpers"]))
        if e.get("fade_mode"):
            notes = "; ".join(e.get("fade_notes") or [])
            out = [f"📌 **Pin: {a} on {d}** — beat {e.get('beats', '?')} of it ({num(e['seconds_to'])} s held) · "
                   f"going under {num(e.get('fade_from', 0))}% → **{num(e.get('fade_to', 0))}%** "
                   f"(+{num(e.get('fade_gain', 0))} this beat" + (f": {notes}" if notes else "")
                   + f"; she passes out at 100%) ({e['fight_left']})"]
        else:
            out = [f"📌 **Pin clock: {a} on {d}** — {num(e['seconds_from'])} → **{num(e['seconds_to'])}** / "
                   f"{num(e['duration'])} s ({e['fight_left']})"]
        odds = ("forced" if e.get("forced") else
                f"escape {e['escape_chance'] * 100:.0f}%"
                + (f" (×{num(e['buffed'])} from breaking loose)" if e.get("buffed") else "")
                + f", else break loose {e['partial_chance'] * 100:.0f}%")
        roll = (f", roll {e['roll'] * 100:.0f}" if "roll" in e else "") + (f" / {e['roll2'] * 100:.0f}" if "roll2" in e else "")
        if e.get("try_how") in WAYS["struggle"] and e["struggle"] in ("fail", "partial", "escape"):
            roll += f"; she {WAYS['struggle'][e['try_how']]}"
        verdict = {"overpowered": f"- {d} struggles, but every attempt is overpowered (forced success)",
                   "none": f"- {d} doesn't make a real attempt this stretch",
                   "fail": f"- {d} struggles ({odds}{roll}) → **fails**; {a} punishes it:",
                   "partial": f"- {d} struggles ({odds}{roll}) → **breaks loose for a moment** and hits {a}:",
                   "escape": (f"- **{d} kicks out at the last second!** The pin can't be won yet ({e.get('why_not', '')})"
                              if e.get("last_second") else
                              f"- {d} struggles ({odds}{roll}) → **ESCAPES!** The pin is broken"
                              + (f"; the blow that frees her lands on {a}:" if e.get("hits_on_pinner") else ""))}[e["struggle"]]
        if self.tight():
            out = [out[0] + " · " + verdict[2:]]
        else:
            out.append(verdict)
        if e.get("pressure_hits"):
            out += self.hits_block(d, e["pressure_hits"])
        if e.get("punish_hits"):
            out += self.hits_block(d, e["punish_hits"])
        if e.get("hits_on_pinner"):
            out += self.hits_block(e["hits_on_pinner"][0].get("defender", e["attacker"]), e["hits_on_pinner"])
        for x in e.get("aftereffects") or []:
            out.append(f"- {self.STATUS_ICON.get(x['status'], '✳️')} **{x['fighter']} is {self.sw(x['status'])}** ({x['beats']} "
                       f"beat{'s' if x['beats'] != 1 else ''})"
                       + {"stiff": ": trapped limbs numb and slow after the pin",
                          "fury": ": a cold, hard anger after being held down so long (harder blows)"}.get(
                           x["status"], ": locked up from holding the pin so long"))
        if e.get("knows_pin"):
            out.append(f"- 🧠 {d} has broken out of a pin like this before (escape ×"
                       f"{num(min(1.45, 1 + 0.15 * e['knows_pin']))})")
        if e.get("pinner_tired"):
            out.append(f"- 😮‍💨 {a} is running out of breath holding the pin: it holds less surely")
        if isinstance(e.get("pinner_down"), dict):
            out.append(f"- ⬇️ **{e['pinner_down']['fighter']} is thrown off and goes down too** "
                       f"({e['pinner_down'].get('facing') or 'down'}); she can try to get up from the next beat")
        if e.get("complete"):
            out.append((f"- ⏱️ **She goes under after {e.get('beats', '?')} beats ({num(e['seconds_to'])} s).**"
                        if e.get("fade_mode") else f"- ⏱️ **Full {num(e['duration'])} seconds held.**")
                       + (f" ❌ **{d} faints and is out.**" if e.get("elimination") else "")
                       + ({"choking": " It was the " + {"blood": "blood choke", "air": "choke on her windpipe", "both": "choke (air and blood)"}.get(
                                          (e.get("out_cause") or {}).get("kind"), "choke") + " that took her under"
                                      + self._grip_words(e.get("out_cause") or {}) + ".",
                           "constriction": " It was the constriction that took her under"
                                           + (f" ({(e.get('out_cause') or {}).get('with')} round her {(e.get('out_cause') or {}).get('part')})"
                                              if (e.get('out_cause') or {}).get('part') else "") + ": her circulation cut off, her heart slowing.",
                           "pain": " It was the pain that took her under"
                                   + (f" (her {(e.get('out_cause') or {}).get('part')})" if (e.get('out_cause') or {}).get('part') else "")
                                   + "."}.get((e.get("out_cause") or {}).get("cause"), "") if e.get("elimination") else ""))
            w = (e.get("elimination") or {}).get("winner")
            if w:
                out.append(f"- 🏆 **Winner: {w}**")
        return out

    def compact(self, bundle):
        """One-line stat summary, like: Chest 445→457 · Neck 304→310 · ❤️ Ripples 1003% → 990%"""
        hits = []
        for a in bundle.get("actions", []):
            hits += a.get("hits", []) + a.get("counter_hits", [])
        for e in bundle.get("also_this_beat", []):
            if e["type"] == "hold_ongoing":
                hits += e["hits"]
            elif e["type"] == "pin_progress":
                hits += e.get("punish_hits", []) + e.get("hits_on_pinner", [])
        for a in bundle.get("actions", []):
            if a.get("type") == "pin_forced":
                hits += a.get("pressure_hits", [])
        if not hits:
            return ""
        per = {}
        for h in hits:
            who = per.setdefault(h["defender"], {"parts": {}, "hp": [h["health_before"], h["health_after"]]})
            p = who["parts"].setdefault(h["part"], [h["damage_before"], h["damage_after"]])
            p[1] = h["damage_after"]
            who["hp"][1] = h["health_after"]
        out = []
        for name, w in per.items():
            parts = " · ".join(f"{part} {num(round(b))}→{num(round(a))}{self.dmg_icon(a)}"
                               for part, (b, a) in w["parts"].items())
            out.append(f"{name}: {parts} · {self.heart} {num(w['hp'][0])}% → {num(w['hp'][1])}%")
        return "\n".join(out)

    def header(self, bundle, number):
        return self.soft_wrap(self._header(bundle, number) or "") or None

    def _header(self, bundle, number):
        """Attack 3 — Nocturne → Ripples: THUNDERBOLT (whole body)"""
        a = bundle["action"]
        if a["type"] != "instant":
            return None
        if a.get("environment"):
            return f"Impact — {a['defender']} {a.get('flavor', '')}"
        m = a.get("move")
        if m:
            if m["target"] == "whole_body":
                aim = "whole body"
            else:
                parts = []
                for h in a["hits"]:
                    if h["part"] not in parts:
                        parts.append(h["part"])
                aim = f"{m['target']} — {', '.join(parts)}" if parts else m["target"]
            tag = ", improvised" if m.get("improvised") else ""
            if a.get("dodged"):
                tag += ", DODGED"
            if a.get("energy"):
                tag += f", energy {a['energy'][0]}→{a['energy'][1]}"
            left = a.get("uses_left")
            if left is not None:
                tag += f", {left} left" if left > 0 else ", last one"
            return f"Attack {number} — {a['attacker']} → {a['defender']}: {m['name'].upper()} ({aim}{tag})"
        return (f"Attack {number} — {a['attacker']} → {a['defender']}: {a.get('flavor', '') or 'improvised hit'}"
                + (" (DODGED)" if a.get("dodged") else ""))

    def tumble_note(self, a):
        tb = a.get("tumble")
        if not tb:
            return []
        how = {"rolling": "rolling over and over", "skidding": "skidding on her side", "bouncing": "bouncing",
               "cartwheeling": "end over end"}.get(tb.get("manner"), "rolling")
        return [f"🌀 **She tumbles on** across {tb['across']}, {how}"
                + (f", and fetches up against {tb['into']}" if tb.get("into") else ", and rolls to a stop in the open")]

    def beat(self, bundle):
        a = bundle["action"]
        t = a["type"]
        out = []
        ch = a.get("chain")
        if ch:
            out.append(f"🔗 **Chain, link {ch['link']} of {ch['of']}**"
                       + ("" if ch["link"] == 1 else " — at point-blank in the grab: no dodging it" if (a.get("point_blank") or a.get("from_grab"))
                          else " — the link before it landed: her chance to dodge this one is halved")
                       + (" — she slips it: the chain ends here" if ch.get("ended") == "dodged" else
                          " — nothing left to follow it with: the chain ends here" if ch.get("ended") else ""))
        for dr in a.get("chain_dropped") or []:
            why = str(dr.get("why") or "")
            out.append(f"- (the director also asked for {dr.get('move')} in this sequence; it was left out: "
                       + ("the same move can't be used a third time running" if "times in a row" in why else why[:160])
                       + ")")
        if t == "grapple_start":
            with_ = f" with {a['with']}" if a.get("with") else ""
            out.append(f"🤼 **{a['attacker']} takes hold of {a['defender']}** (her {a['part']}{with_}"
                       + (f"; energy {a['energy'][0]}→{a['energy'][1]}" if a.get("energy") else "") + ")"
                       + (" — she already had it; the grip tightens" if a.get("existing") else ""))
            out.append(f"- While the grab holds, neither can dodge the other. {a['defender']} rolls to wrench free each "
                       f"beat (about {a.get('break_chance', 0) * 100:.0f}% now) and can hit back.")
        elif t == "instant" and a.get("environment") and a.get("manhandle"):
            kind = a["manhandle"]
            head = {"throw": f"🤾 **{a['attacker']} throws {a['defender']}**",
                    "slam": f"🏋️ **{a['attacker']} lifts {a['defender']} and slams her down**",
                    "drag": f"⛓️ **{a['attacker']} drags {a['defender']} across the ground**"}[kind]
            notes = []
            if a.get("from_ground"):
                notes.append("hauled up from the ground first")
            if kind == "drag":
                notes.append("she stays down" + (f", {a['facing']}" if a.get("facing") else ""))
            elif a.get("kept_feet"):
                notes.append("she ROLLS THROUGH the landing and comes up on her feet")
            elif a.get("ends"):
                notes.append(f"ends up {a['ends']}")
            elif a.get("facing"):
                notes.append(f"ends up {a['facing']}")
            if a.get("energy"):
                notes.append(f"energy {a['energy'][0]}→{a['energy'][1]}")
            if a.get("from_grab"):
                notes.append("out of the grab: no slipping it")
            out.append(head + (f" ({'; '.join(notes)})" if notes else ""))
            out += self.tumble_note(a)
            for l in a.get("landings", []):
                out.append(f"- {'↪ tumbling on: ' if l.get('tumble') else ''}{l['surface']} ({l['severity']}, power "
                           f"{num(l['power'])} each): {', '.join(l['parts'])}")
            out += self.hits_block(a["defender"], a["hits"])
        elif t == "instant" and a.get("environment"):
            if a.get("in_place"):
                out.append(f"🪨 **{a['defender']} is {a.get('flavor', 'driven into the ground')}** where she lies"
                           + (f" (still {a['facing']})" if a.get("facing") else "") + ": no new fall")
            else:
                if a.get("devastating"):
                    out.append(f"💥💥 **DEVASTATING LANDING** (×{num(a['devastating']['mult'])}): the ground finds every "
                               f"sore spot at once")
                out.append(f"🪨 **{a['defender']} lands hard**{' — smashed down out of the air' if a.get('spiked_by') else ''} ({a.get('flavor', '')}"
                           + (", from the ground" if a.get("from_ground") else "") + ")"
                           + (", **rolls through it and comes up on her feet**" if a.get("kept_feet") else
                              f", ends up {a['ends']}" if a.get("ends") else
                              f", ends up {a['facing']}" if a.get("facing") else ""))
            out += self.tumble_note(a)
            for l in a.get("landings", []):
                out.append(f"- {'↪ tumbling on: ' if l.get('tumble') else ''}{l['surface']} ({l['severity']}, power "
                           f"{num(l['power'])} each): {', '.join(l['parts'])}")
            out += self.hits_block(a["defender"], a["hits"])
        elif t == "instant" and a.get("confused_self_hit"):
            out.append(f"💫 **{a['attacker']} is confused** and {a.get('flavor', 'hurts herself')}")
            out += self.hits_block(a["attacker"], a["hits"])
        elif t == "instant" and a.get("status_move") and not a.get("dodged"):
            out.append(f"✨ **{a['attacker']} → {a['defender']}**: {a['move']['name'].upper()} (status move, no damage)"
                       + ("" if a.get("status_applied") else " — it doesn't take hold"))
        elif t == "instant" and a.get("dodged") and not a.get("hits"):
            who = ", ".join(a.get("dodged_by") or [a["defender"]])
            mv = a["move"]["name"].upper() if a.get("move") else (a.get("flavor") or "attack")
            owner = a['attacker'] + ("'" if a['attacker'].endswith("s") else "'s")
            if a.get("resisted"):
                out.append(f"💪 **{who} fights off** {owner} grab ({a.get('manhandle') or 'move'}) where she lies: she is "
                           f"not moved (chance {a.get('dodge_chance', 0) * 100:.0f}%{way('hold_strain', a.get('manner'))})")
            elif a.get("grapple"):
                out.append(f"💨 **{who} slips** {owner} grab (dodge chance {a.get('dodge_chance', 0) * 100:.0f}%"
                           f"{way('dodge', a.get('manner'))}): no grip closes")
            elif (a.get("guard") or {}).get("kind") == "deflect":
                g = a["guard"]
                out.append(f"🤚 **{who} turns {owner} {mv} aside** ({g['how']}; chance {g['chance'] * 100:.1f}%): nothing lands"
                           + (f" — **{a['attacker']} is off balance** (1 beat: slower to dodge, weaker next blow)"
                              if g.get("off_balance") else ""))
            else:
                out.append(f"💨 **{who} dodges** {owner} {mv} (dodge chance {a.get('dodge_chance', 0) * 100:.0f}%"
                           f"{way('dodge', a.get('manner'))}" + ("; wary of it: it hurt her before" if a.get("wary") else "")
                           + ")")
            if a.get("slipped"):
                out.append(f"🧊 **{who} slips** on the slick footing as she dodges and goes down"
                           + (f" ({a['slipped'].get('facing')})" if a["slipped"].get("facing") else "")
                           + ": the attack still misses her")
            if a.get("move"):
                out.append(self.move_line(a["move"]) + " (no hit)")
            if a.get("counter_hits"):
                out.append(f"↩️ **{who} counters!**")
                out += self.hits_block(a["attacker"], a["counter_hits"])
            mc = a.get("missed_charge")
            if mc:
                out.append(f"💥 **{a['attacker']}'s charge carries her on into {mc['surface']}** (power {num(mc['power'])})"
                           + (f" — she goes down ({mc.get('facing')})" if mc.get("down") else " — she stays up"))
                out += self.hits_block(a["attacker"], mc["hits"])
        elif t == "instant":
            out.append(f"⚔️ **{a['attacker']} → {a['defender']}**: {a.get('flavor', '')}")
            cl = a.get("clash")
            if cl:
                ps = lambda n: n + ("'" if n.endswith("s") else "'s")
                out.append(f"💥 **CLASH**: {a['defender']} meets it with {cl['move'].upper()} (force with luck: "
                           f"{num(cl['rolled'][1])} against {num(cl['rolled'][0])}) — "
                           + {"through": f"{ps(a['attacker'])} pushes THROUGH, landing at ×{num(cl['share'])}",
                              "cancel": "they CANCEL OUT: nothing lands",
                              "back": f"{ps(a['defender'])} TURNS IT BACK onto {a['attacker']} at ×{num(cl['share'])}"}[cl["outcome"]])
                if cl.get("hits_on_attacker"):
                    out += self.hits_block(a["attacker"], cl["hits_on_attacker"])
            if a.get("devastating"):
                dv = a["devastating"]
                out.append(f"💥💥 **DEVASTATING** (×{num(dv['mult'])}; the health cap is looser for it) — "
                           + {"position": "caught open, no way to soften it", "weak_point": f"a weak point in a weak point ({dv.get('part')})",
                              "angle": "the perfect angle and timing"}.get(dv.get("reason"), dv.get("reason", "")))
            if a.get("feint"):
                fe = a["feint"]
                out.append(f"🎭 **Feint** ({a['defender']} bites {fe['chance'] * 100:.0f}%): "
                           + ("she BITES — no dodge, the real blow lands on her caught open" if fe["bit"]
                              else "she READS it — an ordinary attack"))
            if a.get("juggled_up"):
                out.append(f"🎯 **{a['defender']} is knocked up into the air** — the next blow catches her there")
            if a.get("juggle"):
                out.append(f"🎯 **JUGGLE**: caught helpless in the air, and smashed back down")
            if a.get("overcommit"):
                out.append(f"😩 **{a['attacker']} overcommits**, sloppy with tiredness (×0.6) — off balance after it")
            if a.get("last_stand"):
                out.append(f"🔥 **LAST STAND**: {a['attacker']} puts everything she has left into it (×{num(float((self.rules.get('moves') or {}).get('last_stand', {}).get('mult', 1.3)))}; energy → 0)")
            if a.get("guarding"):
                gd = a["guarding"]
                out.append(f"🩹 {a['defender']} is guarding her {gd['part']} (blows there ×0.85"
                           + (f"; her {gd['open_side']}{' side' if gd['open_side'] in ('left', 'right') else ''} is open, ×1.1"
                              if gd.get("open_side") else "") + ")")
            if (a.get("guard") or {}).get("kind") == "block":
                g = a["guard"]
                out.append(f"🛡️ **{a['defender']} blocks** with her {g['part']} (chance {g['chance'] * 100:.1f}%): it lands "
                           f"there instead, at ×{num(g['share'])}")
            if a.get("protected"):
                out.append(f"🛡️ **{a['defender']} is behind {a['protected'] if isinstance(a['protected'], str) else 'Protect'}**: "
                           f"the attack stops against it, nothing lands")
            st = a.get("stance")
            if st:
                out.append({"protecting": "🛡️", "countering": "↩️", "mirroring": "🪞"}[st["kind"]]
                           + f" **{(a.get('move') or {}).get('name') or 'Stance'}**"
                           + (f" ({a['attacker']}, chance {st['chance'] * 100:.0f}%): " if st["chance"] < 1 else f" ({a['attacker']}): ")
                           + ("set — it lasts until the next attack on her or the end of next beat" if st["ok"] else "it FAILS"))
            if a.get("weather"):
                out.append(f"🌦️ **{a['weather']['kind'].upper()}** over the arena for {a['weather']['beats']} beats")
            if a.get("dive"):
                out.append(f"🪽 **Dive from above** (×{num(float(a.get('dive_mult') or 1.3))} power)" + (
                    f" — **{a['dragged_down']['by']} catches her and drags her out of the air**" if a.get("dragged_down")
                    else " — she climbs back up" if a.get("climbs") else " — she comes down to land"))
            if a.get("carried"):
                out.append(f"🦅 **{a['attacker']} carries {a['defender']} up** ({a['carried']['height']}) and drops her")
            if a.get("grounded"):
                out.append(f"🪶 **{a['defender']}'s wing gives out**: she falls out of the air")
            if a.get("pummel"):
                pm = a["pummel"]
                where = {"grab": "in the grab", "pin": "from on top, in the pin", "down": "on her where she is down",
                         "against": f"against {pm.get('against') or 'the scenery'}"}.get(pm.get("where") or "grab", "in the grab")
                if pm.get("frenzy"):
                    out.append(f"🌪️ **FRENZY**: {a['attacker']} doesn't stop (blows keep landing on the same spot or two)")
                out.append(f"👊 Pummel {where}: {pm['count']} short blows, each ×{pm['each']:g} of one full blow "
                           f"(power {num(pm['power'])} each)"
                           + {"spoiled": " — it ends when she twists enough to spoil the next one",
                              "out of breath": " — it ends when the attacker has to breathe",
                              "limit": " — as many as she can throw",
                              "answered": " — it ends when the one being hit ANSWERS with a blow of her own"
                              }.get(pm.get("ended") or "", ""))
                if pm.get("answer"):
                    out.append(f"↩️ **{a['defender']} answers{' from inside the grab' if (pm.get('where') or 'grab') == 'grab' else ''}:**")
                    out += self.hits_block(a["attacker"], pm["answer"])
            if a.get("point_blank"):
                out.append(f"- (point-blank: {a['point_blank']} has hold of her opponent, so no dodge either way)")
            if a.get("sustain"):
                su = a["sustain"]
                out.append(f"🌊 Held for {su['held']} pulses (each extra pulse ×"
                           f"{self.rules.get('moves', {}).get('sustain', {}).get('pulse_mult', 0.6)})"
                           + (f", pressing her into {su['against']}" if su["against"] else "")
                           + (f" — **{su['against']} BREAKS** on pulse {su['pulses'][-1]['n']}!" if su["broke"] else ""))
            ch = a.get("charge")
            if ch and ch.get("skipped"):
                out.append(f"- (no charge into {ch['into']}: {ch['skipped']})")
            elif ch and self.layout() != "classic":
                out.append(f"🐏 **Charge** {ch['distance']} into {ch['into']}: "
                           + (f"carried inside the {ch['sheath']} the whole way ({len(ch.get('drive_hits') or [])} more "
                              f"contacts), " if ch.get("sheath") else "")
                           + f"slam power {num(ch['slam_power'])}, then "
                           f"{a['attacker']}{chr(39) if a['attacker'].endswith('s') else chr(39) + 's'} body crushes her "
                           f"against it"
                           + (f" — **{ch['into']} BREAKS**" + (", and the charge goes on" if ch.get("onward") else
                                                                   ", she goes down with it"
                                                                   + (f" ({ch['facing']})" if ch.get("facing") else ""))
                              if ch.get("went_through", ch["broke"]) else " — pressed against it, still up"))
            elif ch:
                n_first = len(a["hits"]) - len(ch["hits"])
                out.append(f"🐏 **Charge**: drives {a['defender']} {ch['distance']} into {ch['into']} (slam power "
                           f"{num(ch['slam_power'])} on {', '.join(h['part'] for h in ch['surface_hits'])}), then "
                           f"{a['attacker']}{chr(39) if a['attacker'].endswith('s') else chr(39) + 's'} body crushes her against it"
                           + (f" — **{ch['into']} BREAKS**" + (", and the charge goes on" if ch.get("onward") else
                                                                   ", she goes down with it"
                                                                   + (f" ({ch['facing']})" if ch.get("facing") else ""))
                              if ch.get("went_through", ch["broke"]) else " — she is pressed against it, still up")
                           + f". The first {n_first} line{'s' if n_first != 1 else ''} below are the charge itself; the "
                             f"rest are the slam and the crush."
                           + (f" Wrapped in {ch['sheath']}, it never leaves her: {len(ch.get('drive_hits') or [])} more "
                              f"contacts while she is carried." if ch.get("sheath") else ""))
            if ch and not ch.get("skipped") and ch.get("shook_loose"):
                out.append("🪨 The slam shakes the arena: something is coming down (end of the beat)")
            if ch and not ch.get("skipped") and ch.get("onward"):
                for st in ch["onward"]:
                    out.append(f"🐏 **The charge carries on** THROUGH {st['through']} into {st['into']} (slam power "
                               f"{num(st['slam_power'])})"
                               + (f" — **{st['into']} BREAKS** too" + (
                                   (", she goes down with it" + (f" ({ch['facing']})" if ch.get("facing") else ""))
                                   if st is ch["onward"][-1] else "") if st["broke"]
                                  else " — it holds: pressed against it, still up"))
            if a.get("target_against"):
                out.append(f"- ({a['defender']} is still pressed against {a['target_against']}: no dodge)")
            if a.get("move") and a["move"]["effectiveness"] == "no effect" and a["move"].get("target") != "self":
                out.append(self.move_line(a["move"]))
                out.append(f"- It has no effect on {a['defender']}.")
            groups = {}
            for h in a["hits"]:
                groups.setdefault(h.get("defender", a["defender"]), []).append(h)
            by_def = a.get("move_by_defender") or {}
            tags = {}
            if ch and not ch.get("skipped"):
                tags.update({id(h): f"slam: {ch['into']}" for h in ch.get("surface_hits", [])})
                tags.update({id(h): "crush" for h in ch.get("crush_hits", [])})
                tags.update({id(h): f"carried inside the {ch['sheath']}" for h in ch.get("drive_hits", [])})
                tags.update({id(h): f"{ch['into']} breaks" for h in ch.get("break_hits", [])})
                for st in ch.get("onward") or []:      # carried on THROUGH what broke, into the next thing
                    tags.update({id(h): f"driven on into {st['into']}" for h in st.get("surface_hits", [])})
                    tags.update({id(h): f"{st['into']} breaks" for h in st.get("break_hits", [])})
                tags.update({id(h): "the charge" for h in a["hits"] if id(h) not in tags})
            if a.get("sustain"):
                for p in a["sustain"]["pulses"]:
                    tags.update({id(h): f"pulse {p['n']}" for h in p.get("move_hits", [])})
                    tags.update({id(h): f"pulse {p['n']}: {a['sustain']['against']}" for h in p.get("surface_hits", [])})
                    tags.update({id(h): f"{a['sustain']['against']} breaks" for h in p.get("break_hits", [])})
                tags.update({id(h): "pulse 1" for h in a["hits"] if id(h) not in tags})
            for i, (who, hs) in enumerate(groups.items()):
                if i and not self.tight():
                    out.append("")
                out += self.hits_block(who, hs, by_def.get(who, a.get("move")), tags or None)
            if a.get("recoil"):
                rc = a["recoil"]
                out.append(f"💢 **Recoil**: {poss_name(a['attacker'])} own {a['move']['name']} jars back into her (power {num(rc['power'])})")
                out += self.hits_block(a["attacker"], rc["hits"])
            if a.get("reflected"):
                rf = a["reflected"]
                ps = rf["by"] + ("'" if rf["by"].endswith("s") else "'s")
                out.append(f"↩️ **{ps} {rf['kind']}**: she takes it and sends it back onto {a['attacker']} "
                           f"(power {num(rf['power'])} each)")
                out += self.hits_block(a["attacker"], rf["hits"])
        elif t in ("hold_start", "pin_start"):
            icon, word = ("📌", "PIN") if t == "pin_start" else ("🔒", "Hold")
            mv = f" ({a['move']['name'].upper()})" if a.get("move") else ""
            if a.get("submission"):
                icon, word = "🔐", "SUBMISSION HOLD"
                mv = f" ({a['submission']['name'].upper()})"
            if a.get("joined"):
                out.append(f"📌 **DOUBLE PIN{mv}: {a['attacker']} joins {' and '.join(a['joined'])} on {a['defender']}** — "
                           f"{a.get('flavor', '')}")
            else:
                kept = t == "hold_start" and a.get("parts") and all(p.get("existing") for p in a["parts"])
                out.append(f"{icon} **{word}{' kept' if kept else ''}{mv}: {a['attacker']} on {a['defender']}** — "
                           f"{a.get('flavor', '')}")
            mark = len(out)
            if a.get("move") and self.tight():
                out.append(self.move_line_tight(a["move"]) + ", every beat")
            elif a.get("move") and self.clear():
                out += self.move_lines_clear(a["move"], every_beat=True)
            elif a.get("move"):
                out.append(self.move_line(a["move"]).replace("Res loss", "Per beat; res loss"))
            if self.tight():
                out += self._wrap([f"{p['part']}" + (f" ← {p['with']}" if p.get("with") else "")
                                   + f": power {num(p['power'])}, {p['change_per_beat']:+g}/beat" for p in a["parts"]])
            elif self.clear():
                out.append("  Pressing on:")
                for p in a["parts"]:
                    ramp = ("steady" if not p["change_per_beat"] else
                            f"{'tightening' if p['change_per_beat'] > 0 else 'easing'} {p['change_per_beat']:+g} a beat")
                    out.append(f"    {p['part']}" + (f" ← with {p['with']}" if p.get("with") else "")
                               + f"  ·  power {num(p['power'])} each beat, {ramp}")
            else:
                for p in a["parts"]:
                    with_ = f" ← {p['with']}" if p.get("with") else ""
                    out.append(f"- {p['part']}{with_}: power {num(p['power'])}, {p['change_per_beat']:+g}/beat")
            notes_from = len(out)
            if t == "pin_start" and a.get("joined"):
                out.append((f"- Same pin, {num(a.get('seconds') or 0)} s in (two on her: she goes under faster). Her presses start "
                            if self.rules.get("pin", {}).get("fade", {}).get("enabled", True) else
                            f"- Same clock: {num(a.get('seconds') or 0)} / {a.get('duration', 60)} s. Her presses start ")
                           + f"next beat; {a['defender']}'s escape odds are halved while both hold her.")
            elif t == "pin_start" and not a.get("continuing"):
                pf = float(self.rules.get("pin", {}).get("first_beat_damage", 0.0))
                fcfg = self.rules.get("pin", {}).get("fade", {})
                out.append((f"- The pin is on. No fixed length: each beat brings her closer to passing out (about "
                            f"{num(fcfg.get('typical_beats', 6))} beats, sometimes more, sometimes fewer). "
                            if fcfg.get("enabled", True) else f"- Pin clock starts: 0 / {a.get('duration', 60)} s. ")
                           + ("Pressure starts next beat." if pf <= 0 else
                              f"The presses land now (×{num(pf)}, listed below) and every beat after."))
            elif t == "hold_start" and a.get("parts") and all(p.get("existing") for p in a["parts"]):
                out.append("- This grip was already on: it carries on (its pressure for this beat is listed below).")
            else:
                hf = float(self.rules.get("holds", {}).get("first_beat_damage", 1.0))
                out.append("- Pressure damage starts next beat and continues every beat until released." if hf <= 0 else
                           f"- The grip bites as it closes: its first pressure lands this beat"
                           + (f" (×{num(hf)})" if hf != 1 else "") + " (listed below), then every beat until released.")
            if a.get("woke"):
                out.append(f"- {a['attacker']} was {' and '.join(a['woke'])}: your command has her act, so she is "
                           f"{'awake' if 'asleep' in a['woke'] else 'free of the ice'} now")
            carried = [p for p in a.get("parts", []) if p.get("existing")] if t == "pin_start" else []
            if carried:
                out.append("- Already on from before, now part of the pin (it keeps pressing this beat, listed below): "
                           + ", ".join(p["part"] + (f" ← {p['with']}" if p.get("with") else "")
                                       + (f" (the beat asked for \"{p['asked_with']}\"; what is already on stays)"
                                          if p.get("asked_with") else "") for p in carried))
            if t == "pin_start" and a.get("absorbed"):
                out.append(f"- Grips {a['attacker']} already had on her join the pin: "
                           + ", ".join(f"#{x['hold_id']} {x['part']}" + (f" ({x['with']})" if x.get("with") else "")
                                       for x in a["absorbed"]))
            if a.get("taken_down"):
                td = a.get("takedown") or {}
                out.append(f"- {a['defender']} was on her feet: taken down into the pin"
                           + (f" ({str(td.get('how')).replace('_', ' ')})" if td.get("how") else "")
                           + (" — a HARD landing:" if td.get("hits") else ""))
                if td.get("hits"):
                    out += self.hits_block(a["defender"], td["hits"])
            if a.get("against"):
                out.append(f"- The pin is jammed against {a['against']}: harder to bridge out of")
            if a.get("facing"):
                note = str(a.get("facing_note") or "")
                same = f"{a['defender']} is {a['facing']}: "
                if note.startswith(same):   # "Ripples is face-down (Ripples is face-down: Stomach → Lower Back)"
                    note = "so the press moved to the side facing up: " + note[len(same):]
                out.append(f"- {a['defender']} is {a['facing']}" + (f" ({note})" if note else ""))
            if self.tight():  # the notes share lines instead of taking one each
                notes = [x[2:] if x.startswith("- ") else x for x in out[notes_from:]]
                out[notes_from:] = self._wrap([n.rstrip(".") for n in notes], sep=" · ")
        elif t == "hold_change":
            out.append(f"🔒 **Hold #{a['hold_id']} {a['direction']}**: power {num(a['power_before'])} → "
                       f"**{num(a['power_after'])}**, {a['change_per_beat']:+g}/beat")
        elif t == "hold_end":
            ids = a.get("hold_ids") or [a["hold_id"]]
            what = ", ".join(a["parts"]) if a.get("parts") else a.get("part", "")
            out.append(f"🔓 **Released** ({', '.join('#' + str(i) for i in ids)}: {what}) after "
                       f"{a['beats_held']} beats: {a['reason']}")
            if a.get("pin_ended"):
                pe = a["pin_ended"]
                out.append(f"- 📌 That ends {pe['attacker']}'s pin on {pe['defender']} at {num(pe['seconds'])} s.")
        elif t == "eliminated":
            out.append(f"❌ **{a['fighter']} is out**: {a.get('reason', '')}"
                       + (f" (lying {a['facing']})" if a.get("facing") else ""))
            if a.get("holds_ended"):
                out.append(f"- 🔓 Holds ended: {', '.join('#' + str(i) for i in a['holds_ended'])}")
            if a.get("winner"):
                out.append(f"- 🏆 **Winner: {a['winner']}**")
        elif t == "pin_forced":
            out += self.pin_block(a)
        elif t == "alliance":
            terms = (f"until {a['until']} is out" if a.get("until") else f"for {a['beats']} beats" if a.get("beats")
                     else "until nobody else is left to fight")
            out.append(f"🤝 **Alliance: {' and '.join(a['members'])}** against {' and '.join(a.get('against') or []) or 'the rest'}, "
                       f"{terms}. They don't attack each other while it lasts.")
        elif t == "team":
            out.append(f"🤝 **Team: {' and '.join(a['members'])}** ({a['team']})")
        elif t == "alliance_end":
            out.append(f"💔 **The alliance between {' and '.join(a['members'])} is over**: {a['why']}")
        elif t == "struggle_request":
            out.append(f"💢 **{a['fighter']} will try to break free** of {a['pinner']}'s pin this beat (outcome rolled).")
        elif t == "pinfall":
            out.append(f"📌 **{a['attacker']} covers {a['defender']}** "
                       f"({self.heart} {pct(a['defender_health'], a['max_health'])})")
            for c in a["counts"]:
                verdict = "KICKS OUT" if c["kicked_out"] else "no kickout"
                out.append(f"- Count {c['count']}: kickout chance {c['kickout_chance'] * 100:.0f}%, "
                           f"roll {c['roll'] * 100:.0f} → {verdict}")
            out.append(f"- Result: **{a['result'].upper()}**")
            if a.get("eliminated"):
                out.append(f"- ❌ **{a['eliminated']} is eliminated.**")
                for hid in a.get("holds_ended", []):
                    out.append(f"- 🔓 Hold #{hid} ends.")
            if a.get("winner"):
                out.append(f"- 🏆 **Winner: {a['winner']}**")
        elif t == "breather":
            out.append(f"⏸️ **Breather**: {a.get('flavor', '')}")
        elif t == "heal":
            out.append(f"💚 **{a['fighter']} recovers**" + (f": {a['flavor']}" if a.get("flavor") else ""))
            for c in a.get("parts", []):
                out.append(f"- {c['part']}: damage {num(c['damage_before'])}% → **{num(c['damage_after'])}%**"
                           + (f", res {num(c['res_before'])}% → **{num(c['res_after'])}%**"
                              if c["res_after"] != c["res_before"] else ""))
            if a["health_after"] != a["health_before"]:
                out.append(f"- {self.heart} {a['fighter']} Health: {pct(a['health_before'])} → **{pct(a['health_after'])}**")
        elif t == "get_up":
            ordinal = {1: "first", 2: "second", 3: "third"}.get(a["tries"], str(a["tries"]))
            out.append(f"🧗 **{a['fighter']} gets up** on the {ordinal} try (using {a['grab']})")
        elif t == "aftermath":
            out.append(f"🌅 **Aftermath** (the match is over; {a.get('winner')} won)"
                       + (f": {a['flavor']}" if a.get("flavor") else ""))
        elif t == "knockdown":
            out.append((f"⬇️ **{a['fighter']} was already down**" if a.get("already_down") else
                        f"⬇️ **{a['fighter']} is down**") + f": {a.get('flavor', '')}"
                       + (f" ({a['facing']})" if a.get("facing") else ""))
        elif t == "weather_end":
            out.append(f"🌤️ The {a['kind']} clears")
        elif t == "take_off":
            out.append(f"🪽 **{a['fighter']} takes to the air** (up for {a['beats']} beats; only ranged attacks reach her)")
        elif t == "land_flight":
            out.append(f"🪶 **{a['fighter']} comes down** out of the air and lands")
        elif t == "reposition" and a.get("resisted"):
            out.append(f"💪 **{a['defender']} fights off being moved** ({a['attacker']} tried: {a['how']}): she stays "
                       f"{a.get('before') or 'as she lay'} (chance {a.get('chance', 0) * 100:.0f}%{way('hold_strain', a.get('manner'))})")
        elif t == "reposition":
            if a["how"] == "pick up":
                out.append(f"🏋️ **{a['attacker']} hauls {a['defender']} up off the ground**")
            elif a["how"] == "stand her up":
                out.append(f"🏋️ **{a['attacker']} drags {a['defender']} up onto her feet** ({a.get('before') or 'down'} → up)")
            elif a["how"] == "sit her up":
                out.append(f"🪑 **{a['attacker']} hauls {a['defender']} up to sitting**: {a.get('before') or '?'} → "
                           f"**sitting up** (still on the ground; front and back both in reach; the next blow knocks "
                           f"her flat)")
            else:
                out.append(f"🔄 **{a['attacker']} rolls {a['defender']}** {a['how']}: {a.get('before') or '?'} → "
                           f"**{a['after']}**" + (f" (pin presses move: {', '.join(a['holds_moved'])})"
                                                  if a.get("holds_moved") else ""))

        for s in a.get("status_applied", []) or []:
            out.append(f"{self.STATUS_ICON.get(s['status'], '✳️')} **{s['fighter']} is {self.sw(s['status'])}** ({s['beats']} beat{'s' if s['beats'] != 1 else ''}"
                       + (f"; from {s['hazard']}" if s.get("hazard") else "") + ")")
        if a.get("launch_blocked"):
            out.append(f"- (no knockdown or throw: {a['launch_blocked']})")
        out += self.knock_on_lines(list(a.get("knock_on") or [])
                                   + [k for s in a.get("status_applied", []) or [] for k in s.get("knock_on") or []])

        # all ongoing pressure on the same fighter from the same attacker -> one block
        groups = {}
        for e in bundle["also_this_beat"]:
            if e["type"] == "hold_ongoing":
                g = groups.setdefault((e["attacker"], e["defender"], bool(e.get("first"))),
                                      {"ids": [], "hits": [], "beats": 0, "tags": {}, "mult": None,
                                       "first_mult": e.get("first_mult")})
                if e.get("pin_mult") is not None and e.get("hold_power") is not None:
                    g["mult"] = e["pin_mult"]
                    if e["pin_mult"] != 1:
                        for h in e["hits"]:  # where this beat's power comes from: the press × the pin damage setting
                            g["tags"][id(h)] = f"press {num(e['hold_power'])} × {num(e['pin_mult'])} pin damage"
                g["ids"].append(e["hold_id"])
                g["hits"] += e["hits"]
                g["beats"] = max(g["beats"], e["beats_held"])
        for (att, dfn, first), g in groups.items():
            if not self.tight():
                out.append("")
            out.append(f"🔒 **{att} on {dfn}** (holds {', '.join('#' + str(i) for i in g['ids'])}), "
                       + (f"the grip closing: beat 1 of the hold"
                          + (f" · first-beat damage ×{num(g['first_mult'])}" if g["first_mult"] not in (None, 1) else "")
                          if first else f"beat {g['beats']} of the hold")
                       + (f" · pin damage ×{num(g['mult'])}" if g["mult"] not in (None, 1) else ""))
            out += self.hits_block(dfn, g["hits"], None, g["tags"] or None)
        for e in bundle["also_this_beat"]:
            if e["type"] == "pin_progress":
                if not self.tight():
                    out.append("")
                out += self.pin_block(e)
        for e in bundle["also_this_beat"]:
            if e["type"] == "alliance_end":
                out.append(f"💔 **The alliance between {' and '.join(e['members'])} is over**: {e['why']}"
                           + (f". {' and '.join(e['still_in'])} are opponents again." if len(e.get("still_in") or []) > 1 else ""))
        for e in bundle["also_this_beat"]:
            if e["type"] == "hold_end" and e.get("broke_free"):
                if not self.tight():
                    out.append("")
                out.append(f"💥 **{e['defender']} breaks {poss_word(e['attacker'])} hold** on her {', '.join(e['parts'])} "
                           f"(#{', #'.join(str(i) for i in e['hold_ids'])}) after {e['beats_held']} "
                           f"beat{'s' if e['beats_held'] != 1 else ''} — break-free chance this beat "
                           f"{e['chance'] * 100:.0f}%{way('hold_break', e.get('manner'))}")
            elif e["type"] == "hold_end" and e.get("released") and e.get("submission"):
                out.append(f"🔓 **{e['attacker']} lets the {e['submission'].upper()} go** after {e['beats_held']} "
                           f"beat{'s' if e['beats_held'] != 1 else ''}: she can't keep it on any longer")
            elif e["type"] == "hold_loosened":
                if not self.tight():
                    out.append("")
                out.append(f"🫳 **{e['defender']} works {poss_word(e['attacker'])} hold looser** on her {', '.join(e['parts'])}: it "
                           f"stays on, pressing at {' / '.join(num(x) for x in e['power_to'])} from the next beat (was "
                           f"{' / '.join(num(x) for x in e['power_from'])}) — a near miss on the break-free roll "
                           f"({e['roll'] * 100:.0f} against {e['chance'] * 100:.0f}%{way('hold_strain', e.get('manner'))})")
            elif e["type"] == "hold_strain":
                out.append(f"💢 {e['defender']} fights {poss_word(e['attacker'])} hold on her {', '.join(e['parts'])}; it holds as "
                           f"it was{way('hold_strain', e.get('manner'))}")
        for e in bundle["also_this_beat"]:
            if e["type"] == "crumple":
                pct_ = f"crumple chance {e['chance'] * 100:.0f}%"
                out.append((f"🧱 **{e['fighter']} slides down {e['surface']} and ends sitting against it** — {pct_}"
                            if e.get("facing") == "sitting up" else
                            f"🧱 **{e['fighter']} crumples** at the foot of {e['surface']}"
                            + (f" ({e['facing']})" if e.get("facing") else "") + f" — {pct_}") if e["down"] else
                           f"🧱 **{e['fighter']} keeps her feet** at {e['surface']} — {pct_}{way('charge_stands', e.get('manner'))}")
                if e.get("reeling"):
                    out.append(f"🌀 {e['fighter']} is reeling ({e['reeling']} beat): she can strike, but can't start a pin")
                out += self.knock_on_lines(e.get("knock_on") or [])
        for e in bundle["also_this_beat"]:
            if e["type"] == "get_up":
                ordinal = {1: "first", 2: "second", 3: "third"}.get(e["tries"], str(e["tries"]))
                roll = ""
                if e.get("cuts") and e.get("score") is not None:
                    c = e["cuts"]
                    need = " / ".join(f"{x:g}" for x in c)
                    roll = ((f"\n      " if self.clear() else " — ")
                            + f"get-up roll {e['score']:g} (needs {need} to rise on try 1 / 2 / 3"
                            + ("; up anyway: nobody stays down this long unless pinned" if e.get("forced") else "") + ")")
                    grips = [f"{g['by']}'s grip on her {g['part']} stays on" for g in e.get("held") or []]
                    if grips:
                        roll += ("\n      " if self.clear() else " · ") + "; ".join(grips)
                out.append((f"🧗 **{e['fighter']} gets up** on the {ordinal} try (using {e['grab']}{way('getup_rise', e.get('rise'), '; ')})"
                            if e["stands"] else
                            f"🧗 **{e['fighter']} can't get up** this beat, but **gets as far as sitting up** "
                            f"({e['tries']} tries; down {e['beats_down']} beat{'s' if e['beats_down'] != 1 else ''})" if e.get("sits") else
                            f"🧗 **{e['fighter']} can't get up** this beat ({e['tries']} tries; down {e['beats_down']} beat{'s' if e['beats_down'] != 1 else ''})")
                           + roll)
            elif e["type"] == "stays_down":
                out.append(f"🧗 {e['fighter']} stays down this beat: she only just went down, so there is no get-up roll "
                           f"yet (the first one is next beat)")
        for e in bundle["also_this_beat"]:
            if e["type"] == "scene_event":
                if not self.tight():
                    out.append("")
                out.append(f"🌋 **{e.get('place', 'the arena').capitalize()} acts: {e['name']}** — on {' and '.join(e['fighters'])}"
                           + (" (your /hazard)" if e.get("forced") else f" (chance {e.get('chance', 0) * 100:.0f}% a beat)"))
                by = {}
                for h in e.get("hits") or []:
                    by.setdefault(h["defender"], []).append(h)
                for who, hs in by.items():
                    out += self.hits_block(who, hs)
                for s in e.get("status_applied") or []:
                    out.append(f"{self.STATUS_ICON.get(s['status'], '✳️')} **{s['fighter']} is {self.sw(s['status'])}** "
                               f"({s['beats']} beat{'s' if s['beats'] != 1 else ''})")
                if not e.get("hits") and not e.get("status_applied"):
                    out.append("- nobody is hurt by it")
        for e in bundle["also_this_beat"]:
            if e["type"] == "adrenaline":
                out.append(f"🔥 **{e['fighter']}: ADRENALINE SURGE!** ({e['beats']} beats: harder hits, better escapes "
                           f"and dodges, energy refill)")
            elif e["type"] == "status_tick" and e["status"] == "burned":
                h = e["hits"][0]
                out.append(f"🔥 {e['fighter']}'s burn: {h['part']} {num(h['damage_before'])}% → {num(h['damage_after'])}%")
            elif e["type"] == "weather_end":
                out.append(f"🌤️ The {e['kind']} clears")
            elif e["type"] == "status_tick" and e.get("hits"):
                h = e["hits"][0]
                out.append(f"🧊 The {e['status']} stings {e['fighter']}: {h['part']} {num(h['damage_before'])}% → "
                           f"{num(h['damage_after'])}%")
            elif e["type"] == "status_tick":
                out.append(f"☠️ {e['fighter']} is poisoned: {self.heart} -{num(e['health_loss'])}% → {pct(e['health_after'])}")
            elif e["type"] == "status_end":
                out.append(f"- {poss_word(e['fighter'])} adrenaline surge is over" if e["status"] == "adrenaline" else
                           f"- {e['fighter']} is no longer {self.sw(e['status'])}")
        for e in bundle["also_this_beat"]:
            if e["type"] == "recovery":
                out.append(f"💫 **{e['fighter']}**: {e['from']} → **{e['to']}** (chance {e['chance'] * 100:.0f}% per beat)")
        for e in bundle["also_this_beat"]:
            if e["type"] == "time_passes":
                parts = []
                for name, f in e["fighters"].items():
                    causes = []
                    if f.get("exhaustion"):
                        causes.append(f"-{num(f['exhaustion'])}% exertion")
                    if f.get("pain_drain"):
                        causes.append(f"-{num(f['pain_drain'])}% injuries")
                    note = f", now {f['health_tier']}" if f["health_tier_changed"] else ""
                    why = ", ".join(causes) if causes else "no change"
                    parts.append(f"{self.heart} {name} {pct(f['health_after'])} ({why}{note})")
                if parts:
                    if not self.tight():
                        out.append("")
                    out.append(f"⏳ Beat {e['beat']} health: " + " | ".join(parts))
        return self.soft_wrap("\n".join(out))

    @staticmethod
    def _posture_tag(engine, f, lead=""):
        """Up, down (and which way), pinned under whom, or on top of whom: straight from the engine."""
        p = engine.posture(f.name)
        if p["pinned_by"]:
            return f"{lead} ⬇️ down ({p['facing']}), 📌 pinned under {' and '.join(p['pinned_by'])}"
        if p["down"]:
            return f"{lead} ⬇️ {'lying' if p['out'] else 'down'} ({p['facing']})"
        if p["pinning"]:
            return f"{lead} 📌 on top of {' and '.join(p['pinning'])}"
        return f"{lead} 🧍 up"

    def status_brief(self, engine):
        """Everyone at a glance: health, worst injuries, limited moves, holds/pins, positions."""
        out = []
        for f in engine.fighters.values():
            out_tag = f" ❌ out ({engine.recovery_stage(f)['label']})" if f.eliminated else ""
            ht = tier_for(100 * f.health / f.max_health, self.rules["health_tiers"])["label"]
            worst = sorted((p for p in f.parts.values() if p.damage > 0), key=lambda p: -p.damage)[:5]
            hurt = " · ".join(f"{p.name} {self.dmg_icon(p.damage)}{num(round(p.damage))}%" for p in worst) or "unhurt"
            limited = ", ".join(f"{m} {n} left" for m, n in f.move_uses.items())
            share = num(round(100 * f.health / f.max_health)) if f.max_health else "0"
            down = self._posture_tag(engine, f) + self._status_tag(f)
            out.append(f"**{f.name}**{out_tag} {self.heart} {pct(f.health)} ({share}% of full, {ht}){down} — {hurt}"
                       + (f"  [{limited}]" if limited else ""))
        for p in engine.pins.values():
            out.append(f"📌 {' and '.join(engine.pin_members(p))} pinning {p['defender']}: "
                       + (f"{num(p['seconds'])} s held, going under {num(p.get('fade', 0))}%"
                          if engine.fade_mode() else f"{num(p['seconds'])}/{num(p['duration'])} s"))
        loose = [h for h in engine.holds.values() if h.defender not in engine.pinning(h.attacker)]
        for h in loose:
            out.append(f"🔒 #{h.id} {h.attacker} → {h.defender}'s {h.part}")
        out.append(f"📍 {engine.positions_now()}")
        out.append("(/status full for every body part, /status <name> for one fighter)")
        return "\n".join(out)

    def health(self, engine, name=None):
        """Health and every damaged body part (worst first), in the stat format."""
        fs = [engine.get(name)] if name else list(engine.fighters.values())
        out = []
        for f in fs:
            out_tag = f" ❌ out ({engine.recovery_stage(f)['label']})" if f.eliminated else ""
            share = 100 * f.health / f.max_health if f.max_health else 0
            ht = tier_for(share, self.rules["health_tiers"])["label"]
            down = self._posture_tag(engine, f, " ·") + self._status_tag(f)
            out.append(f"**{f.name}**{out_tag} {self.heart} Health {pct(f.health)} of {pct(f.max_health)} "
                       f"({num(round(share, 1))}% of full, {ht}){down}")
            hurt = sorted((p for p in f.parts.values() if p.damage > 0 or p.resistance < p.start_resistance),
                          key=lambda p: -p.damage)
            if self.layout() != "classic":
                out += self._wrap([self.part_item(p.name, p.resistance, p.damage) for p in hurt],
                                  width=112 if self.tight() else 96) or ["  no damage yet"]
            else:
                out += [self.part_line(p.name, p.resistance, p.damage) for p in hurt] or ["- no damage yet"]
            untouched = len(f.parts) - len(hurt)
            if hurt and untouched:
                out.append(f"- ({untouched} other part{'s' if untouched != 1 else ''} untouched)")
            out.append("")
        res_leg = " ".join(f"{b['icon']}{b['label']}" for b in self.rules["resistance"]["brackets"])
        dmg_leg = " ".join(f"{t['icon']}{t['min']}+" for t in pain_tiers(self.rules))
        out.append(f"Legend: resistance {res_leg} | damage {dmg_leg} | {self.heart} = health")
        if self.layout() != "classic":
            out.append(self.KEY)
        return "\n".join(out)

    def look_text(self, engine, name=None):
        """Plain summary of the scene right now (used by /look when the models are off)."""
        out = ["SCENE: " + engine.scene, ""]
        text = engine.narrator_condition()
        if name:
            who, keep, cur = engine.get(name).name, [], None
            for line in text.split("\n"):
                if not line.startswith(" "):
                    cur = line.split(":")[0]
                if cur == who or cur in ("PINS", "PIN", "HOLDS", "POSITIONS (where everyone is after this beat)"):
                    keep.append(line)
            text = "\n".join(keep)
        out.append(text)
        return "\n".join(out)

    def status(self, engine, name=None):
        fs = [engine.get(name)] if name else list(engine.fighters.values())
        out = []
        multi_team = any(f.team != f.name for f in engine.fighters.values())
        for f in fs:
            team = f" — team {f.team}" if multi_team else ""
            out_tag = f" ❌ out ({engine.recovery_stage(f)['label']})" if f.eliminated else ""
            ht = tier_for(100 * f.health / f.max_health, self.rules["health_tiers"])["label"]
            out.append(f"**{f.name}**{team}{out_tag} {self.heart} Health {pct(f.health, f.max_health)} ({ht})"
                       f"{self._status_tag(f)}")
            if self.layout() != "classic":
                out += self._wrap([self.part_item(p.name, p.resistance, p.damage) for p in f.parts.values()],
                                  width=112 if self.tight() else 96)
            else:
                out += [self.part_line(p.name, p.resistance, p.damage) for p in f.parts.values()]
            out.append("")
        if engine.holds:
            out.append("Active holds:")
            for h in engine.holds.values():
                out.append(f"- #{h.id} {h.attacker} → {h.defender}'s {h.part}: power {num(h.power)} "
                           f"({h.change_per_turn:+g}/beat) — {h.flavor}")
        res_leg = " ".join(f"{b['icon']}{b['label']}" for b in self.rules["resistance"]["brackets"])
        dmg_leg = " ".join(f"{t['icon']}{t['min']}+" for t in pain_tiers(self.rules))
        out.append(f"\nLegend: resistance {res_leg} | damage {dmg_leg} | {self.heart} = health")
        if self.layout() != "classic":
            out.append(self.KEY)
        return "\n".join(out)
