"""The stock-phrase memory (narration.phrase_memory): which stock phrases the story has used, kept across fights and
runs of the program in phrase_memory.json, so none of them turns up again and again.

Each phrase has a running total (uses) and a HEAT: every use adds one, and heat halves every half_life_beats beats.
Before a beat is written, the phrases that are still warm are RESTED: listed for the narrator as ones to leave alone
for now. A hot phrase (heat at always_rest or more) is always rested; a warm one (from rest_from) is rested by a roll
of the dice, more likely the warmer it is. So a phrase used a moment ago is nearly always kept out, and one that has
not been used for a long while drifts back in by itself. Nothing is ever offered for use: the list only rests
phrases, so it can never push the story towards one of them.

The phrases: the families in stock_phrases.txt (one per line: the phrase as it is shown, then optionally " | " and
a regular expression for all its forms), and the four-word runs a single fight leaned on (narration.worn_phrases),
which are learned and kept from then on."""
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_families(path):
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        label, _, rx = line.partition("|")
        label, rx = label.strip(), rx.strip()
        if not rx:
            rx = r"\b" + r"\s+".join(re.escape(w) for w in label.split()) + r"\b"
        try:
            out.append((label, re.compile(rx, re.I)))
        except re.error:
            continue
    return out


class PhraseMemory:
    def __init__(self, rules):
        cfg = (rules.get("narration", {}) or {}).get("phrase_memory") or {}
        self.cfg = cfg
        self.enabled = bool(cfg.get("enabled", True))
        self.path = cfg.get("file") or "phrase_memory.json"
        if not os.path.isabs(self.path):
            self.path = os.path.join(HERE, self.path)
        self.families = _load_families(os.path.join(HERE, cfg.get("list_file", "stock_phrases.txt")))
        self.clock, self.book = 0, {}
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.clock = int(data.get("clock", 0))
            self.book = {k: dict(v) for k, v in (data.get("phrases") or {}).items() if isinstance(v, dict)}
        except (OSError, ValueError, AttributeError):
            pass

    def _decay(self):
        return 0.5 ** (1.0 / max(1.0, float(self.cfg.get("half_life_beats", 12))))

    def note_beat(self, text, learned=()):
        """A finished beat: every stock phrase in it (and the fight's worn four-word runs) counted, heat cooled."""
        if not self.enabled:
            return
        self.clock += 1
        k = self._decay()
        for v in self.book.values():
            v["heat"] = round(float(v.get("heat", 0)) * k, 4)
        low = re.sub(r"[*_]", "", text or "")
        for label, rx in self.families:
            n = len(rx.findall(low))
            if n:
                self._add(label, n, "stock")
        words = " ".join(re.findall(r"[a-z']+", low.lower()))
        for g in learned or ():
            if g not in self.book:
                self.book[g] = {"uses": 0, "heat": 0.0, "last": self.clock, "kind": "learned"}
            n = len(re.findall(r"\b" + re.escape(g) + r"\b", words))
            if n:
                self._add(g, n, "learned")
        # the learned runs that have long gone cold are forgotten (the stock list is kept for good)
        cut = float(self.cfg.get("forget_below", 0.05))
        self.book = {g: v for g, v in self.book.items() if v.get("kind") != "learned" or float(v.get("heat", 0)) >= cut
                     or self.clock - int(v.get("last", 0)) < 3}
        self.save()

    def _add(self, label, n, kind):
        v = self.book.setdefault(label, {"uses": 0, "heat": 0.0, "last": self.clock, "kind": kind})
        v["uses"] = int(v.get("uses", 0)) + n
        v["heat"] = round(float(v.get("heat", 0)) + n, 4)
        v["last"] = self.clock

    def rested(self, seed=None):
        """The phrases to leave alone in the next beat, warmest first: always the hot ones, and the warm ones by a
        roll of the dice weighted by their heat (narration.phrase_memory.rest_from / always_rest / max_listed)."""
        if not self.enabled:
            return []
        soft = float(self.cfg.get("rest_from", 0.35))
        hard = max(soft + 0.01, float(self.cfg.get("always_rest", 1.5)))
        rng = random.Random(seed)
        out = []
        for g, v in sorted(self.book.items(), key=lambda kv: -float(kv[1].get("heat", 0))):
            h = float(v.get("heat", 0))
            if h >= hard or (h >= soft and rng.random() < (h - soft) / (hard - soft)):
                out.append(g)
            if len(out) >= int(self.cfg.get("max_listed", 8)):
                break
        return out

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump({"clock": self.clock, "phrases": self.book}, fh, indent=0, sort_keys=True)
        except OSError:
            pass

    def report(self, n=20):
        """The /phrases list: running totals and how warm each is now."""
        rows = sorted(self.book.items(), key=lambda kv: (-float(kv[1].get("heat", 0)), -int(kv[1].get("uses", 0))))
        return [(g, int(v.get("uses", 0)), float(v.get("heat", 0)), v.get("kind", "")) for g, v in rows[:n]]
