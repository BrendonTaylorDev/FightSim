"""(since build 329, window.sounds) Sounds for the fighters' bodies: the gasp of a light hit, the grunt and the cry of
harder ones, the scream when something is ruined, straining and whimpering in a hold, choking in coils, the breath
coming back when her heart starts again, panting when she is spent. No impact sounds: only her.

The sound files are yours: put .wav files (or .mp3) in sounds/<kind>/ (any number; one is picked at random each
time). A fighter's own voice goes in sounds/<her name>/<kind>/ or sounds/<species>/<kind>/ and is used first. Kinds
with no files are simply silent. The window plays each beat's sounds as the beat lands; an exported fight carries
them too (window.sounds.export).

Nothing here changes the fight: it only reads the cards' data, beat to beat."""
import os
import random
import subprocess
import sys

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
            "export": True, "export_max_mb": 8}


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


def play_file(path, volume=0.8):
    """Play one sound file without waiting for it (several can overlap). Windows: the system's media player (MCI);
    a Mac: afplay; Linux: paplay or aplay. Nothing happens where none of these is there."""
    if not path:
        return
    try:
        if sys.platform.startswith("win"):
            import ctypes
            mci = ctypes.windll.winmm.mciSendStringW
            alias = f"fs{random.randrange(10 ** 9)}"
            kind = "mpegvideo" if path.lower().endswith((".mp3", ".ogg")) else "waveaudio"
            mci(f'open "{path}" type {kind} alias {alias}', None, 0, None)
            mci(f"setaudio {alias} volume to {int(max(0.0, min(1.0, volume)) * 1000)}", None, 0, None)
            mci(f"play {alias}", None, 0, None)
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", "-v", str(max(0.0, min(1.0, volume))), path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            for player in (["paplay"], ["aplay", "-q"]):
                try:
                    subprocess.Popen(player + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except FileNotFoundError:
                    continue
    except Exception as e:
        if "play" not in _FAILED:
            _FAILED.add("play")
            from engine import note_failure
            note_failure("playing a sound (window.sounds)", e)


def play_beat(prev_by_name, fighters, rules, turn=0):
    """The window: each fighter's sounds for this beat, played now."""
    c = cfg(rules)
    if not c.get("enabled", True):
        return
    for f in fighters:
        for kind in cues(prev_by_name.get(f.get("name")), f, rules, turn):
            play_file(pick(f, kind), float(c.get("volume", 0.8)))


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
