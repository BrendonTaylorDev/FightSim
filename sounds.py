"""(since build 329, window.sounds) Sounds for the fighters' bodies: the gasp of a light hit, the grunt and the cry of
harder ones, the scream when something is ruined, straining and whimpering in a hold, choking in coils, the breath
coming back when her heart starts again, panting when she is spent. No impact sounds: only her.

The sound files are yours: put .wav files (or .mp3) in sounds/<kind>/ (any number; one is picked at random each
time). A fighter's own voice goes in sounds/<her name>/<kind>/ or sounds/<species>/<kind>/ and is used first. Kinds
with no files are simply silent. The window plays each beat's sounds as the beat lands; an exported fight carries
them too (window.sounds.export).

(since build 330) Each fighter has one voice, so her sounds never pile up on top of each other and a long file plays
to its end (see Mixer). A beat's sounds play once, when it lands; the Replay sounds button (the window) or the
speaker button on a beat (an exported fight) plays them again.

Nothing here changes the fight: it only reads the cards' data, beat to beat."""
import atexit
import os
import queue
import random
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOUND_DIR = os.path.join(HERE, "sounds")
EXTS = (".wav", ".mp3", ".ogg")

# the kinds of sound, and when each is used
KINDS = {
    "gasp": "a light hit: a sharp breath in",
    "grunt": "a solid hit: the breath knocked out of her",
    "cry": "a heavy hit: a cry of pain",
    "scream": "a devastating hit, or a part ruined",
    "strain": "fighting a hold or a grip: effort through her teeth",
    "whimper": "held near her limit, refusing to tap",
    "choke": "coils squeezing her in hard, or a choke on her",
    "breath_back": "her heart starting again, or coming round: a long shuddering breath in",
    "pant": "spent or short of air: hard breathing (now and then, not every beat)",
}

DEFAULTS = {"enabled": True, "volume": 0.8, "breathing": True, "breath_every": 3, "max_per_beat": 2,
            "export": True, "export_max_mb": 8, "overlap": "voice", "max_seconds": 0, "queue_max": 3}

# (since build 330) how much each kind matters: a new beat's minor sound (MINOR or less) doesn't cut off a bigger one
# she is still making, and doesn't restart one of its own size
PRIORITY = {"scream": 6, "choke": 5, "cry": 5, "breath_back": 5, "grunt": 4, "whimper": 3, "gasp": 3,
            "strain": 2, "pant": 1}
MINOR = 2


def cfg(rules):
    c = dict(DEFAULTS)
    c.update(((rules or {}).get("window") or {}).get("sounds") or {})
    return c


def _folder_files(folder):
    try:
        return sorted(os.path.join(folder, n) for n in os.listdir(folder) if n.lower().endswith(EXTS))
    except OSError:
        return []


def files_for(name, species, kind):
    """The files for this kind of sound for her: her own, her species', else everyone's."""
    for who in (name, species):
        if who:
            got = _folder_files(os.path.join(SOUND_DIR, str(who).lower(), kind))
            if got:
                return got
    return _folder_files(os.path.join(SOUND_DIR, kind))


def cues(prev, f, rules, turn=0):
    """The sounds she makes this beat, from her card a beat before (prev) and now (f): [kind], at most max_per_beat."""
    c = cfg(rules)
    if not c.get("enabled", True) or not f or f.get("out"):
        return []
    st, st0 = f.get("status") or {}, (prev or {}).get("status") or {}
    if "limp" in st:
        return []
    out = []
    if "limp" in st0:
        out.append("breath_back")
    if prev:
        import cards
        hits, jolt = cards.impacts(prev, f)
        before = {p: d for p, d, r in prev.get("parts") or ()}
        ruined = any(d >= 300 > before.get(p, d) for p, d, r in f.get("parts") or ())
        if hits or jolt > 0.05:
            s = max([x for p, x in hits] + [jolt])
            out.append("scream" if ruined or s >= 0.85 else "cry" if s >= 0.55 else "grunt" if s >= 0.25 else "gasp")
    g = f.get("grips") or {}
    if g.get("held"):
        t = g.get("tap") or {}
        v = t.get("vitals") or {}
        if (v.get("squeeze") is not None and float(v["squeeze"]) >= 60) or any(x.get("choke") for x in g["held"]):
            out.append("choke")
        elif not out:
            out.append("whimper" if int(t.get("level") or 0) >= 4 else "strain")
    if not out and c.get("breathing", True):
        b = f.get("body") or {}
        spent = float(f.get("energy", 100) or 0) < 35 or float(b.get("air", 100) or 100) < 40
        if spent and int(turn) % max(1, int(c.get("breath_every", 3))) == 0:
            out.append("pant")
    return out[:max(1, int(c.get("max_per_beat", 2)))]


def pick(f, kind):
    got = files_for(f.get("name"), f.get("species"), kind)
    return random.choice(got) if got else None


_FAILED = set()


def _failed(where, e):
    if where not in _FAILED:
        _FAILED.add(where)
        from engine import note_failure
        note_failure(where, e)


class Player:
    """Starts, checks and stops one sound file on this computer. Windows: the system's media player (MCI); a Mac:
    afplay; Linux: paplay or aplay. start() returns a handle, or None where nothing could play it."""

    def __init__(self):
        self.win = sys.platform.startswith("win")
        if self.win:
            import ctypes
            self._mci = ctypes.windll.winmm.mciSendStringW
            self._buf = ctypes.create_unicode_buffer(64)

    def start(self, path, volume):
        vol = max(0.0, min(1.0, volume))
        if self.win:
            alias = f"fs{random.randrange(10 ** 9)}"
            kind = "mpegvideo" if path.lower().endswith((".mp3", ".ogg")) else "waveaudio"
            if self._mci(f'open "{path}" type {kind} alias {alias}', None, 0, None):
                return None
            self._mci(f"setaudio {alias} volume to {int(vol * 1000)}", None, 0, None)
            self._mci(f"play {alias}", None, 0, None)
            return alias
        players = [["afplay", "-v", str(vol)]] if sys.platform == "darwin" else [["paplay"], ["aplay", "-q"]]
        for player in players:
            try:
                return subprocess.Popen(player + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                continue
        return None

    def done(self, h):
        if self.win:
            self._mci(f"status {h} mode", self._buf, 64, None)
            return self._buf.value != "playing"
        return h.poll() is not None

    def stop(self, h):
        if self.win:
            self._mci(f"stop {h}", None, 0, None)
            self._mci(f"close {h}", None, 0, None)
        elif h.poll() is None:
            h.terminate()


class Mixer:
    """(since build 330, window.sounds.overlap) Each fighter has one voice. Her sounds in a beat play one after
    another, not on top of each other, and a sound plays to its end however long the file is (max_seconds caps it).
    When the next beat brings a new sound while she is still making the last one:
      voice (default): the new one cuts the old one off, unless it is a minor sound (strain, pant) no bigger than
        the one still playing, which is skipped: she doesn't stop screaming to pant;
      queue: it waits its turn (at most queue_max waiting; the rest are dropped);
      mix: everything plays at once (the way build 329 did it).
    Every sound is started, checked and stopped from one background thread (the Windows player needs that)."""

    TICK = 0.05

    def __init__(self, player=None):
        self.player = player
        self.voices = {}          # who -> {"h", "kind", "t", "q": [(path, kind)], "max", "vol"}
        self.cmds = queue.Queue()
        self.thread = None
        self._n = 0

    def submit(self, who, items, c):
        """Her sounds for this beat: [(path, kind)], with the settings (cfg) in force."""
        if items:
            self._post(("beat", who, list(items), dict(c)))

    def stop_all(self, wait=0.0):
        if self.thread is None:
            return
        done = threading.Event()
        self._post(("stop", done))
        if wait:
            done.wait(wait)

    def _post(self, cmd):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, name="fight sounds", daemon=True)
            self.thread.start()
        self.cmds.put(cmd)

    def _run(self):
        if self.player is None:
            try:
                self.player = Player()
            except Exception as e:
                _failed("starting the sound player (window.sounds)", e)
                return
        while True:
            try:
                cmd = self.cmds.get(timeout=self.TICK)
            except queue.Empty:
                cmd = None
            try:
                if cmd:
                    self.apply(cmd)
                self.tick()
            except Exception as e:
                _failed("playing a sound (window.sounds)", e)

    # the two steps below run on the sound thread (or directly, in the tests)
    def apply(self, cmd):
        if cmd[0] == "stop":
            for v in self.voices.values():
                self._end(v)
                v["q"] = []
            self.voices.clear()
            cmd[1].set()
            return
        _, who, items, c = cmd
        mode = str(c.get("overlap", "voice")).lower()
        common = {"max": float(c.get("max_seconds", 0) or 0), "vol": float(c.get("volume", 0.8))}
        if mode == "mix":
            for path, kind in items:
                self._n += 1
                v = dict(common, h=None, kind=kind, t=0.0, q=[])
                self.voices[("mix", self._n)] = v
                self._start(v, path, kind)
            return
        v = self.voices.setdefault(who, dict(common, h=None, kind=None, t=0.0, q=[]))
        v.update(common)
        busy = v["h"] is not None
        if mode == "queue":
            v["q"] = (v["q"] + items)[:max(0, int(c.get("queue_max", 3)))]
            if not busy:
                self._next(v)
            return
        top = max(PRIORITY.get(k, 3) for p, k in items)
        if busy and top <= min(MINOR, PRIORITY.get(v["kind"], 3)):
            return
        self._end(v)
        v["q"] = list(items)
        self._next(v)

    def tick(self):
        now = time.monotonic()
        for key in list(self.voices):
            v = self.voices[key]
            if v["h"] is not None and ((v["max"] and now - v["t"] >= v["max"]) or self.player.done(v["h"])):
                self._end(v)
                self._next(v)
            if v["h"] is None and not v["q"] and isinstance(key, tuple):
                del self.voices[key]

    def _start(self, v, path, kind):
        try:
            v["h"] = self.player.start(path, v["vol"])
        except Exception as e:
            _failed("playing a sound (window.sounds)", e)
            v["h"] = None
        v["kind"], v["t"] = kind, time.monotonic()

    def _next(self, v):
        while v["h"] is None and v["q"]:
            path, kind = v["q"].pop(0)
            self._start(v, path, kind)

    def _end(self, v):
        if v["h"] is not None:
            try:
                self.player.stop(v["h"])
            except Exception as e:
                _failed("stopping a sound (window.sounds)", e)
            v["h"] = None


MIXER = Mixer()
atexit.register(lambda: MIXER.stop_all(wait=0.5))


def play_file(path, volume=0.8):
    """Play one sound file on its own, alongside anything else playing."""
    if path:
        MIXER.submit(("file", path), [(path, "gasp")], {"overlap": "mix", "volume": volume})


def beat_items(prev_by_name, fighters, rules, turn=0):
    """Each fighter's sounds for this beat, the files picked: {name: [(path, kind)]} (fighters with none left out).
    The window keeps this so the Replay sounds button plays the same files again."""
    c = cfg(rules)
    out = {}
    if not c.get("enabled", True):
        return out
    for f in fighters:
        items = [(p, k) for k in cues(prev_by_name.get(f.get("name")), f, rules, turn) for p in [pick(f, k)] if p]
        if items:
            out[f.get("name")] = items
    return out


def play_items(by_name, rules):
    """Play beat_items' sounds, each fighter through her voice (see Mixer)."""
    c = cfg(rules)
    if c.get("enabled", True):
        for who, items in (by_name or {}).items():
            MIXER.submit(who, items, c)


def play_beat(prev_by_name, fighters, rules, turn=0):
    """The window: each fighter's sounds for this beat, played now; returns what was played (beat_items)."""
    got = beat_items(prev_by_name, fighters, rules, turn)
    play_items(got, rules)
    return got


def stop_all():
    """Silence everything playing now (sounds turned off, the window closed)."""
    MIXER.stop_all()


def ensure_folders():
    """sounds/<kind>/ for every kind, and a note on what goes where (made once)."""
    try:
        for k in KINDS:
            os.makedirs(os.path.join(SOUND_DIR, k), exist_ok=True)
        note = os.path.join(SOUND_DIR, "README.txt")
        if not os.path.exists(note):
            with open(note, "w", encoding="utf-8") as fh:
                fh.write(__doc__.strip() + "\n\nThe kinds:\n" +
                         "".join(f"  {k}/  {v}\n" for k, v in KINDS.items()))
    except OSError as e:
        from engine import note_failure
        note_failure("making the sounds folders", e)
