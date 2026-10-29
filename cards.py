"""Fighter pictures and their body-part markings, shared by the window (window.py) and the fight export
(/exportfight): which picture, where each part sits on it, the damage glow, and a finished card image.

Needs Pillow for the glow and the exported card images; without it the window still works (plainer), and the export
falls back to tables."""
import io
import json
import math
import os
import random
import re
import urllib.request
import zlib

from engine import body_region, poss_word

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont, ImageEnhance
except Exception:              # pragma: no cover
    Image = ImageDraw = ImageFilter = ImageChops = ImageFont = ImageEnhance = None

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, "images")
ANCHORS = os.path.join(IMG_DIR, "anchors.json")
PIC = 300                      # picture box size (pixels)
COL, ROW = 158, 17             # label column width, label row height

# the console's own colour steps (display.py legend)
RES_STEPS = [(100.0001, "#3b82f6", "tough (over 100%)"), (70, "#22c55e", "70-100%"), (50, "#eab308", "50-70%"),
             (30, "#f97316", "30-50%"), (-1e9, "#ef4444", "under 30%")]
DMG_STEPS = [(500, "#78350f", "ruined (500%+)"), (300, "#1f2937", "devastated (300%+)"), (150, "#a855f7", "excruciating (150%+)"),
             (90, "#ef4444", "very painful (90%+)"), (60, "#f97316", "hurting (60%+)"), (30, "#eab308", "sore (30%+)"),
             (-1e9, "#22c55e", "minor")]
GLOW = {"sore": "#facc15", "hurting": "#fb923c", "very": "#ef4444", "excruciating": "#a855f7",
        "devastated": "#7f1d1d", "ruined": "#450a0a"}

# where each body region sits on a body (fractions of the picture), for species with no points placed
SPOTS = {"head": (0.5, 0.07), "neck": (0.5, 0.2), "shoulder": (0.5, 0.31), "chest": (0.5, 0.42),
         "back_up": (0.5, 0.31), "fore_up": (0.5, 0.45), "fore_low": (0.5, 0.62), "belly": (0.5, 0.57),
         "back_low": (0.5, 0.69), "hind_up": (0.5, 0.77), "hind_low": (0.5, 0.9), "tail": (0.5, 0.97),
         "other": (0.5, 0.5)}
SPREAD = {"shoulder": 0.3, "fore_up": 0.36, "fore_low": 0.38, "hind_up": 0.3, "hind_low": 0.32, "head": 0.3,
          "chest": 0.25, "belly": 0.28, "back_up": 0.28, "neck": 0.2, "tail": 0.25, "back_low": 0.28, "other": 0.3}

# National Pokédex numbers for the roster's species (the artwork is fetched by number; PokeAPI is only asked about
# a species missing here)
DEX = {"absol": 359, "arbok": 24, "arcanine": 59, "articuno": 144, "braviary": 628, "buizel": 418, "charizard": 6,
       "dragonite": 149, "fennekin": 653, "floatzel": 419, "goodra": 706, "lucario": 448, "lycanroc": 745,
       "milotic": 350, "moltres": 146, "ninetales": 38, "pidgeot": 18, "staraptor": 398, "swanna": 581,
       "swellow": 277, "talonflame": 663, "thievul": 828, "unfezant": 521, "vulpix": 37}

# where each part is on the official artwork (fractions of the picture), for the species played most; any other
# species is placed by a guess until you place its points yourself (in the window: click a label, then the picture)
ARTWORK_POINTS = {
    "absol": {"Head": (.63, .22), "Horn": (.52, .10), "Left Ear": (.70, .22), "Right Ear": (.57, .23),
              "Muzzle": (.64, .37), "Nose": (.66, .36), "Jaw": (.64, .42), "Neck": (.55, .44), "Throat": (.63, .47),
              "Chest Ruff": (.47, .38), "Chest": (.60, .55), "Belly": (.45, .60), "Back": (.38, .45),
              "Left Shoulder": (.70, .52), "Right Shoulder": (.50, .52), "Left Ribs": (.65, .60), "Right Ribs": (.42, .52),
              "Left Flank": (.52, .63), "Right Flank": (.33, .52), "Left Upper Foreleg": (.67, .67),
              "Right Upper Foreleg": (.56, .67), "Left Lower Foreleg": (.67, .77), "Right Lower Foreleg": (.57, .76),
              "Left Forepaw": (.66, .89), "Right Forepaw": (.56, .82), "Left Hip": (.44, .55), "Right Hip": (.31, .55),
              "Left Thigh": (.47, .66), "Right Thigh": (.27, .61), "Left Hock": (.50, .71), "Right Hock": (.25, .66),
              "Left Hind Paw": (.47, .72), "Right Hind Paw": (.28, .70), "Tail Base": (.33, .40),
              "Sickle Tail": (.25, .24)},
    "buizel": {"Head": (.24, .40), "Left Ear": (.31, .31), "Right Ear": (.25, .34), "Muzzle": (.16, .48),
               "Nose": (.12, .48), "Left Cheek": (.27, .50), "Right Cheek": (.19, .52), "Jaw": (.22, .54),
               "Neck": (.37, .44), "Throat": (.30, .55), "Chest": (.40, .58), "Stomach": (.52, .60),
               "Upper Back": (.50, .42), "Lower Back": (.62, .46), "Left Shoulder": (.40, .52),
               "Right Shoulder": (.45, .45), "Left Upper Arm": (.24, .60), "Right Upper Arm": (.46, .62),
               "Left Forearm Fin": (.14, .57), "Right Forearm Fin": (.50, .40), "Left Paw": (.08, .65),
               "Right Paw": (.55, .67), "Left Hip": (.62, .60), "Right Hip": (.65, .50), "Left Thigh": (.66, .62),
               "Right Thigh": (.60, .55), "Left Knee": (.69, .68), "Right Knee": (.55, .66), "Left Foot": (.73, .74),
               "Right Foot": (.56, .69), "Tail Base": (.72, .45), "Twin Tails": (.82, .32)},
}


# where each part is on the PokeAPI back sprite (cropped to the body), for the species played most
BACK_POINTS = {
    "buizel": {"Upper Back": (.68, .50), "Lower Back": (.70, .70), "Tail Base": (.50, .80), "Twin Tails": (.22, .60),
               "Neck": (.68, .38), "Head": (.70, .14), "Left Hip": (.52, .78), "Right Hip": (.84, .78),
               "Left Shoulder": (.55, .47), "Right Shoulder": (.85, .45)},
    "absol": {"Back": (.45, .47), "Tail Base": (.22, .45), "Sickle Tail": (.13, .27), "Head": (.80, .22),
              "Left Hip": (.25, .55), "Right Hip": (.38, .58)},
}
# the regions that go on the back picture unless you move a part (window.back_regions)
BACK_REGIONS = ("back_up", "back_low", "tail")
# how she looks as she weakens: the picture files tried, in order, for each state (images/<name>_<state>.png ...)
STATE_TRY = {"out": ("out", "down", "hurt"), "down": ("down", "hurt"), "hurt": ("hurt", "worn"), "worn": ("worn",)}
# how she is placed (window.poses): the picture files tried, in order, for each pose (images/<name>_<pose>.png ...),
# before the weakened ones; with none of them, her picture is posed by the program (window.pose_fallback)
POSE_TRY = {"pinned": ("pinned", "faceup", "down"), "faceup": ("faceup", "down"), "facedown": ("facedown", "down"),
            "side": ("side", "down"), "sitting": ("sitting",), "pinning": ("pinning",), "air": ("air",),
            "out": ("out", "down")}
LYING = ("pinned", "faceup", "facedown", "side", "down", "out")
EXTS = (".png", ".gif", ".webp", ".jpg", ".jpeg")


def opts_of(rules):
    """The window and card settings (rules.json "window"), with their defaults."""
    w = dict((rules or {}).get("window") or {})
    w.setdefault("back_view", True)
    w.setdefault("back_download", True)
    w.setdefault("back_regions", list(BACK_REGIONS))
    w.setdefault("weak_look", True)
    w.setdefault("worn_below", 60)
    w.setdefault("hurt_below", 30)
    w.setdefault("back_size", 220)
    w.setdefault("glow", True)
    w.setdefault("damage_marks", True)
    w.setdefault("marks_from", 30)
    w.setdefault("status_look", True)
    w.setdefault("poses", True)
    w.setdefault("pose_fallback", True)
    return w


def pose_of(f):
    """How she is placed, for the picture (window.poses): "pinned", "pinning", "air", "faceup", "facedown", "side",
    "sitting", "out", or None (on her feet). Read from her posture line, so fights saved before build 189 work too."""
    if f.get("out"):
        return "out"
    post = str(f.get("posture") or "").lower()
    if post.startswith("pinned by"):
        return "pinned"
    if post.startswith("pinning"):
        return "pinning"
    if post.startswith("in the air") or "airborne" in (f.get("status") or {}):
        return "air"
    if post.startswith("down"):
        face = str(f.get("facing") or post)
        return ("facedown" if "face-down" in face else "faceup" if "face-up" in face else
                "sitting" if "sitting" in face else "side")
    return None


def health_state(f, opts=None):
    """How she should look: None (fine), "worn", "hurt", "down" (on the ground or pinned) or "out"."""
    o = opts or opts_of(None)
    if f.get("out"):
        return "out"
    post = str(f.get("posture") or "").lower()
    if post.startswith("down") or post.startswith("pinned by"):
        return "down"
    pct = 100.0 * float(f.get("health", 0)) / max(1e-9, float(f.get("max", 1)))
    if pct < float(o.get("hurt_below", 30)):
        return "hurt"
    if pct < float(o.get("worn_below", 60)):
        return "worn"
    return None


def _file(stem):
    for ext in EXTS:
        path = os.path.join(IMG_DIR, stem + ext)
        if stem and os.path.exists(path):
            return path
    return None


def _download_back(species):
    """The species' back sprite from the PokeAPI sprite set, cropped to the body and kept as images/<species>_back.png."""
    key = re.sub(r"[^a-z0-9-]", "", (species or "").lower().replace(" ", "-"))
    pid = DEX.get(key)
    if pid is None or Image is None:
        return None
    try:
        url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/back/{pid}.png"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "FightSim"}), timeout=20) as r:
            im = Image.open(io.BytesIO(r.read())).convert("RGBA")
        im = im.crop(im.getbbox() or (0, 0, im.width, im.height))
        k = max(1, 288 // max(im.width, im.height))
        im = im.resize((im.width * k, im.height * k), Image.NEAREST)     # pixel art: kept crisp
        buf = io.BytesIO()
        im.save(buf, "PNG")
        os.makedirs(IMG_DIR, exist_ok=True)
        with open(os.path.join(IMG_DIR, key + "_back.png"), "wb") as fh:
            fh.write(buf.getvalue())
        return buf.getvalue()
    except Exception:
        return None


def _silhouette_back(front):
    """No back picture to be had: her front picture's outline, flipped and filled flat, as a stand-in seen from behind."""
    if Image is None or not front:
        return None
    im = Image.open(io.BytesIO(front)).convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)
    a = im.getchannel("A")
    rgb = im.convert("RGB").resize((1, 1), Image.BILINEAR).getpixel((0, 0)) if im.getbbox() else (160, 160, 160)
    flat = Image.new("RGBA", im.size, tuple(int(c * 0.8) for c in rgb) + (255,))
    flat.putalpha(a)
    buf = io.BytesIO()
    flat.save(buf, "PNG")
    return buf.getvalue()


class PictureBook:
    """Every picture a fighter has, found once and kept: her front and back views, and the pictures for how she looks
    as she weakens. Your own files in images/ come first: <name>.png, then <species>.png (the front), <name>_back.png,
    <species>_back.png (the back), and for each state <name>_<state>.png or <name>_back_<state>.png (state: worn,
    hurt, down, out; the species works too). Missing ones: the official artwork for the front, the PokeAPI back sprite
    for the back (window.back_download), else a flat outline of the front."""

    def __init__(self, name, species, opts=None, download=True):
        self.name, self.species = name, species or name
        self.opts = opts or opts_of(None)
        self.download = download
        self._base, self._state = {}, {}

    def stems(self, view, state=None):
        suf = ("_back" if view == "back" else "") + (f"_{state}" if state else "")
        return [(self.name + suf, True), (self.species + suf, False), (self.species.lower() + suf, False)]

    def base(self, view):
        """(bytes, own, key, builtin points) for this view."""
        if view in self._base:
            return self._base[view]
        got = None
        for stem, own in self.stems(view):
            path = _file(stem)
            if path:
                with open(path, "rb") as fh:
                    got = (fh.read(), own, stem.lower())
                break
        if got is None and view == "front":
            data, own = picture_bytes(self.name, self.species, self.download)
            got = (data, own, (self.name if own else self.species).lower()) if data else None
        if got is None and view == "back":
            data = _download_back(self.species) if (self.download and self.opts.get("back_download", True)) else None
            if data:
                got = (data, False, self.species.lower() + "_back")
            else:
                front = self.base("front")
                data = _silhouette_back(front[0]) if front and front[0] else None
                got = (data, False, (self.species.lower() + "_back")) if data else None
        sp = self.species.lower()
        builtin = {}
        if got and not got[1]:
            builtin = (ARTWORK_POINTS if view == "front" else BACK_POINTS).get(sp, {}) \
                if got[2] in (sp, sp + "_back") else {}
        self._base[view] = (got[0], got[1], got[2], builtin) if got else None
        return self._base[view]

    def pick(self, view, state, pose=None):
        """(bytes, own, key, fallback keys, builtin points, own_state, matched): her picture for this pose (pose files
        first, POSE_TRY) or state if you have one, else the view's own picture (own_state False: the window gives it
        the weakened look and the pose itself). matched: the file's pose or state word, or None."""
        base = self.base(view)
        if base is None:
            return None
        tries = list(POSE_TRY.get(pose or "", ()))
        # (with a pose, lying down is the pose's to choose: a _down picture is never used for her sitting or on top)
        tries += [st for st in STATE_TRY.get(state or "", ()) if st not in tries and not (pose and st in ("down", "out"))]
        for st in tries:
            ck = (view, st)
            if ck not in self._state:
                hit = None
                for stem, own in self.stems(view, st):
                    path = _file(stem)
                    if path:
                        with open(path, "rb") as fh:
                            hit = (fh.read(), own, stem.lower())
                        break
                self._state[ck] = hit
            hit = self._state[ck]
            if hit:
                if st in LYING:
                    # lying down, her parts are nowhere near where they are standing: no borrowed points (place
                    # them on this picture: click a label, then the picture)
                    return hit[0], hit[1], hit[2], [], {}, True, st
                return hit[0], hit[1], hit[2], [base[2]], base[3] if not hit[1] else {}, True, st
        return base[0], base[1], base[2], [], base[3], False, None


# colour for each state: (how much colour is left, brightness)
SHADE = {"worn": (0.8, 0.96), "hurt": (0.55, 0.85), "down": (0.65, 0.88), "out": (1.0, 1.0)}
# the program's own pose, when there is no picture of it (window.pose_fallback): the steps that bend her picture
# into it, where she sits in her box ("bottom": on the ground, "top": up in the air) and whether she casts a shadow
POSE_GEO = {
    "faceup":   {"ops": [("flip_v",), ("scale", 1.0, 0.8)], "at": "bottom", "shadow": True},
    "pinned":   {"ops": [("flip_v",), ("scale", 1.0, 0.75)], "at": "bottom", "shadow": True, "dim": 0.85},
    "facedown": {"ops": [("scale", 1.12, 0.55)], "at": "bottom", "shadow": True},
    "side":     {"ops": [("rotate", 90)], "at": "bottom", "shadow": True},
    "out":      {"ops": [("rotate", 90)], "at": "bottom", "shadow": True},
    "sitting":  {"ops": [("scale", 1.0, 0.82)], "at": "bottom", "shadow": True},
    "pinning":  {"ops": [("scale", 1.05, 0.9)], "at": "bottom", "shadow": True},
    "air":      {"ops": [("scale", 0.8, 0.8)], "at": "top", "shadow": True},
}
# the old weakened look's shapes (window.poses off): slumped when badly hurt, on her side when down or out
OLD_GEO = {"hurt": [("rotate", -7)], "down": [("rotate", 90)], "out": [("rotate", 90)]}


def _geo(im, ops):
    """Her picture put through ops (flip_v, scale sx sy, rotate degrees), and xf: where a point given as fractions of
    the old picture is, as fractions of the new one."""
    w0, h0 = im.size
    maps = []
    for op in ops:
        w, h = im.size
        if op[0] == "flip_v":
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
            maps.append(lambda x, y, h=h: (x, h - y))
        elif op[0] == "scale":
            sx, sy = op[1], op[2]
            im = im.resize((max(1, round(w * sx)), max(1, round(h * sy))), Image.LANCZOS)
            maps.append(lambda x, y, sx=sx, sy=sy: (x * sx, y * sy))
        elif op[0] == "rotate":
            a = op[1]
            if a == 90:
                # (by her body, not the picture: the artwork comes on a square canvas whatever her shape) a body
                # already lying along the picture (Buizel, Swellow) turned on end would look less down, so it tips over
                bb = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox() or (0, 0, w, h)
                if (bb[3] - bb[1]) < (bb[2] - bb[0]) * 0.9:
                    a = -16
            rot = im.rotate(a, expand=True, resample=Image.BICUBIC)
            W, H, t = rot.size[0], rot.size[1], math.radians(a)
            maps.append(lambda x, y, w=w, h=h, W=W, H=H, t=t: (W / 2 + (x - w / 2) * math.cos(t) + (y - h / 2) * math.sin(t),
                                                               H / 2 - (x - w / 2) * math.sin(t) + (y - h / 2) * math.cos(t)))
            im = rot
    W, H = im.size

    def xf(fx, fy):
        x, y = fx * w0, fy * h0
        for m in maps:
            x, y = m(x, y)
        return x / W, y / H
    return im, (xf if maps else None)


def pose_look(im, state=None, pose=None):
    """Her picture made to look the way she is when there is no picture of it: faded and dimmer as she weakens
    (state), and bent into her pose (pose: POSE_GEO) or, with no pose, the old slump or tip onto her side. Returns
    (image, xf, place): place says where she sits in her box and whether she casts a shadow."""
    if Image is None or im is None or not (state or pose):
        return im, None, {}
    fade, dim = SHADE.get(state, (1, 1))
    g = POSE_GEO.get(pose) if pose else None
    dim *= (g or {}).get("dim", 1)
    a = im.getchannel("A")
    rgb = im.convert("RGB")
    if fade != 1:
        rgb = ImageEnhance.Color(rgb).enhance(fade)
    if dim != 1:
        rgb = ImageEnhance.Brightness(rgb).enhance(dim)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    out, xf = _geo(out, g["ops"] if g else OLD_GEO.get(state, []) if pose is None else [])
    return out, xf, ({"at": g["at"], "shadow": g["shadow"]} if g else {})


def weak_look(im, state):
    """The weakened look alone (no pose): (image, xf). Kept for anything that still asks for it."""
    out, xf, _ = pose_look(im, state, None)
    return out, xf


def split_parts(parts, keys, opts=None):
    """(front parts, back parts): a part you placed on one picture stays there; the rest go by where they are on a
    body (window.back_regions on the back)."""
    o = opts or opts_of(None)
    book = load_anchors()
    fk, bk = keys
    mine_f, mine_b = book.get(fk, {}), book.get(bk, {})
    regs = set(o.get("back_regions") or BACK_REGIONS)
    front, back = [], []
    for t in parts:
        n = t[0]
        on_back = (n in mine_b) if (n in mine_b) != (n in mine_f) else body_region(n) in regs
        (back if on_back else front).append(t)
    return front, back


def res_color(v):
    return next(c for at, c, _ in RES_STEPS if v >= at)


def dmg_color(v):
    return next(c for at, c, _ in DMG_STEPS if v >= at)


def dmg_word(v):
    return next(n for at, c, n in DMG_STEPS if v >= at)


def res_word(v):
    return next(n for at, c, n in RES_STEPS if v >= at)


def text_on(bg):
    """Black or white text, whichever reads on this fill."""
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"


def glow_color(dmg):
    """The colour a part glows on the picture: none while it is minor."""
    return (GLOW["ruined"] if dmg >= 500 else GLOW["devastated"] if dmg >= 300 else GLOW["excruciating"] if dmg >= 150 else GLOW["very"] if dmg >= 90
            else GLOW["hurting"] if dmg >= 60 else GLOW["sore"] if dmg >= 30 else None)


def short(part):
    s = part.replace("Left ", "L ").replace("Right ", "R ").replace("Upper ", "Up ").replace("Lower ", "Lo ")
    return s if len(s) <= 14 else s[:13] + "…"


def load_anchors():
    try:
        with open(ANCHORS, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_anchors(book):
    try:
        os.makedirs(IMG_DIR, exist_ok=True)
        with open(ANCHORS, "w", encoding="utf-8") as fh:
            json.dump(book, fh, indent=1, sort_keys=True)
    except Exception as e:
        from engine import note_failure
        note_failure("saving the picture's part points (images/anchors.json)", e)


def picture_bytes(name, species, download=True):
    """(bytes or None, own): her own picture (images/<name>.png), her species' (images/<species>.png), or the
    official artwork, fetched once and kept in images/ for next time."""
    os.makedirs(IMG_DIR, exist_ok=True)
    for base in (name, species, (species or "").lower()):
        for ext in (".png", ".gif"):
            path = os.path.join(IMG_DIR, (base or "") + ext)
            if base and os.path.exists(path):
                with open(path, "rb") as fh:
                    return fh.read(), base == name
    key = re.sub(r"[^a-z0-9-]", "", (species or "").lower().replace(" ", "-"))
    if not key or not download:
        return None, False
    try:
        pid = DEX.get(key)
        if pid is None:
            req = urllib.request.Request(f"https://pokeapi.co/api/v2/pokemon-species/{key}/",
                                         headers={"User-Agent": "FightSim"})
            with urllib.request.urlopen(req, timeout=15) as r:
                pid = json.load(r)["id"]
        url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{pid}.png"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "FightSim"}), timeout=20) as r:
            data = r.read()
        with open(os.path.join(IMG_DIR, species.lower() + ".png"), "wb") as fh:
            fh.write(data)
        return data, False
    except Exception:
        return None, False


def prepare_picture(data, size=PIC, look=None):
    """(src, rect, box) for a picture: the picture fitted into a size x size square (RGBA), where it sits
    (x, y, w, h), and where the body is inside it (x0, y0, x1, y1). Needs Pillow; (None, ...) without it.
    look: a state, or (state, pose), for pose_look; then a fourth item, xf, moves points to where they are on the
    changed picture. A posed picture sits on the ground of its box (or high in it, flying) over a soft shadow."""
    if Image is None or not data:
        return (None, (4, 4, size - 8, size - 8), None) + ((None,) if look is not None else ())
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    xf, place = None, {}
    if look:
        state, pose = look if isinstance(look, tuple) else (look, None)
        im, xf, place = pose_look(im, state, pose)
    small = im.width < (size - 8) / 2 and im.height < (size - 8) / 2
    if small:       # a small sprite: grown in whole steps, kept crisp
        k = max(1, int((size - 8) // max(im.width, im.height)))
        im = im.resize((im.width * k, im.height * k), Image.NEAREST)
    im.thumbnail((size - 8, size - 8))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x, y = (size - im.width) // 2, (size - im.height) // 2
    body = im.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox() or (0, 0, im.width, im.height)
    if place.get("at") == "bottom":
        y = size - 10 - body[3]                 # her lowest point on the ground line, a little above the box's edge
    elif place.get("at") == "top":
        y = 4 - body[1]
    if place.get("shadow"):
        # (faint and blurred: under the body threshold, so no glow or mark ever lands on it)
        bw = (body[2] - body[0]) * (0.5 if place.get("at") == "top" else 0.85)
        cx, gy = x + (body[0] + body[2]) / 2, size - 9
        sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse((cx - bw / 2, gy - bw * 0.07, cx + bw / 2, gy + bw * 0.07),
                                   fill=(0, 0, 0, 20 if place.get("at") == "top" else 34))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)))
    canvas.paste(im, (x, y), im)
    box = canvas.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox() or (0, 0, size, size)
    return (canvas, (x, y, im.width, im.height), box) + ((xf,) if look is not None else ())


def _onto_body(alpha, x, y):
    """The nearest point of the body itself (not the empty background) to (x, y)."""
    px = alpha.load()
    S = alpha.size[0]
    xi, yi = int(min(S - 1, max(0, x))), int(min(S - 1, max(0, y)))
    if px[xi, yi] > 40:
        return x, y
    for r in range(3, 90, 3):
        for k in range(16):
            a = 2 * math.pi * k / 16
            xx, yy = int(xi + r * math.cos(a)), int(yi + r * math.sin(a))
            if 0 <= xx < S and 0 <= yy < S and px[xx, yy] > 40:
                return xx, yy
    return x, y


def point_key(f, own):
    return (f["name"] if own else f["species"] or f["name"]).lower()


def anchor_points(f, src=None, rect=(4, 4, PIC - 8, PIC - 8), box=None, own=False, has_picture=False, key=None,
                  fallback=(), builtin=None, parts=None, xf=None, size=PIC):
    """Where each part is on the picture (picture pixels): your own placements (images/anchors.json) first, then
    the built-in ones for this species' artwork, else a guess from where that part sits on a body, fitted to the
    picture's outline. key: the picture's own name in anchors.json (fallback: others to borrow from, e.g. a
    weakened picture borrowing its base's points); parts: only these; xf: moves a stored point onto a picture
    that was turned or tilted (weak_look)."""
    key = key or point_key(f, own)
    book = dict(builtin if builtin is not None else ({} if own or not has_picture else ARTWORK_POINTS.get(key, {})))
    every = load_anchors()
    for k in fallback or ():
        book.update(every.get(k, {}))
    book.update(every.get(key, {}))
    rx, ry, rw, rh = rect
    x0, y0, x1, y1 = box or (40, 20, size - 40, size - 20)
    alpha = src.getchannel("A") if src is not None and Image is not None and hasattr(src, "getchannel") else None
    out, groups = {}, {}
    for part, dmg, res in (f["parts"] if parts is None else parts):
        if part in book:
            fx, fy = book[part]
            if xf:
                fx, fy = xf(fx, fy)
            out[part] = (rx + fx * rw, ry + fy * rh)
            continue
        reg = body_region(part)
        side = -1 if part.lower().startswith("left ") else 1 if part.lower().startswith("right ") else 0
        groups.setdefault((reg, side), []).append(part)
    for (reg, side), parts in groups.items():
        fx, fy = SPOTS.get(reg, SPOTS["other"])
        fx += side * SPREAD.get(reg, 0.3) * 0.6
        if reg in ("back_up", "back_low") and not side:
            fx += 0.2
        for i, part in enumerate(parts):
            x = x0 + fx * (x1 - x0)
            y = y0 + (fy + (i - (len(parts) - 1) / 2) * 0.05) * (y1 - y0)
            if alpha is not None:
                x, y = _onto_body(alpha, x, y)
            out[part] = (x, y)
    return out


def _body_mask(src):
    return src.getchannel("A").point(lambda a: 255 if a > 40 else 0).filter(ImageFilter.GaussianBlur(2))


def _glow_layer(src, f, spots, alpha=190):
    layer = Image.new("RGBA", src.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for part, dmg, res in sorted(f["parts"], key=lambda t: t[1]):
        col = glow_color(dmg)
        if not col or part not in spots:
            continue
        x, y = spots[part]
        r = (16 + min(16, dmg / 25)) * src.size[0] / PIC
        rgb = tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))
        dr.ellipse((x - r, y - r, x + r, y + r), fill=rgb + (alpha,))
    return layer.filter(ImageFilter.GaussianBlur(9))


def mark_tier(dmg):
    """How bad the marks on a part look: 0 (none) up to 5 (ruined), on the damage steps the labels use."""
    return 5 if dmg >= 300 else 4 if dmg >= 150 else 3 if dmg >= 90 else 2 if dmg >= 60 else 1 if dmg >= 30 else 0


def _ragged(rng, x0, y0, x1, y1, n, jit):
    """A line from (x0, y0) to (x1, y1) as n+1 points, each nudged sideways by up to jit: a torn edge, not a ruler."""
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy) or 1
    nx, ny = -dy / ln, dx / ln
    pts = []
    for i in range(n + 1):
        t = i / n
        j = rng.uniform(-jit, jit) if 0 < i < n else 0
        pts.append((x0 + dx * t + nx * j, y0 + dy * t + ny * j))
    return pts


def _mark(kind, soft, sharp, x, y, u, tier, rng, fresh, age=None, swell=0.0, bleed=0.0):
    """One kind of mark at (x, y): soft (blurred later: bruising, soot, frost haze, blood seeping) and sharp (cuts,
    punctures, crystals). u: pixels per point at this picture's size; tier 1-5; fresh: made this beat or the last.
    (since build 318, body.tissue and body.blood) swell: how swollen the part is (0-100), the bruise spreading with
    it; age: beats since it was hit, a bruise going from angry red to purple to a dark, yellow-edged old one; bleed:
    how fast it is bleeding, more blood running from it."""
    r = (9 + 3.5 * tier) * u * (1.0 + 0.4 * max(0.0, min(100.0, swell)) / 100.0)
    u = u * 1.4          # (lines, dots and crystals a little heavier than the spacing, so they read on the card)
    pop = 1.15 if fresh else 1.0

    def A(v):
        return int(max(0, min(255, v * pop)))
    if kind == "claw":
        n = 4 if tier >= 4 else 3
        ang = rng.uniform(-1.15, -0.45)
        L, gap = r * (1.5 + 0.15 * tier), (2.2 + 0.35 * tier) * u
        w = (0.6 + 0.4 * tier) * u
        ca, sa = math.cos(ang), math.sin(ang)
        for j in range(n):
            off = (j - (n - 1) / 2) * gap + rng.uniform(-0.6, 0.6) * u
            cx, cy = x - sa * off, y + ca * off
            ln = L * rng.uniform(0.75, 1.05)
            pts = _ragged(rng, cx - ca * ln / 2, cy - sa * ln / 2, cx + ca * ln / 2, cy + sa * ln / 2, 6,
                          (0.3 + 0.25 * tier) * u)
            soft.line(pts, fill=(170, 20, 30, A(25 + 15 * tier)), width=int(w * 3))
            sharp.line(pts, fill=(105, 8, 18, A(150 + 20 * tier)), width=max(1, int(w)))
            if tier >= 2:
                sharp.line(pts[1:-1], fill=(205, 30, 40, A(170 + 10 * tier)), width=max(1, int(w * 0.5)))
            if tier >= 3 and rng.random() < 0.5 + 0.1 * tier:
                mx, my = pts[len(pts) // 2]
                sharp.line([(mx, my), (mx + rng.uniform(-1, 1) * u, my + r * rng.uniform(0.3, 0.8))],
                           fill=(150, 10, 20, A(170)), width=max(1, int(w * 0.6)))      # a trickle of blood
    elif kind == "bite":
        R, k = r * 0.85, 3 + min(2, tier // 2)
        d = (1.0 + 0.35 * tier) * u
        for side in (-1, 1):                       # the upper and the lower jaw
            for i in range(k):
                t = (i - (k - 1) / 2) / max(1, k - 1) * 1.6
                px = x + R * math.sin(t) + rng.uniform(-0.5, 0.5) * u
                py = y + side * (R * 0.45 + R * 0.25 * (1 - math.cos(t))) + rng.uniform(-0.5, 0.5) * u
                soft.ellipse((px - d * 2.4, py - d * 2.4, px + d * 2.4, py + d * 2.4), fill=(160, 20, 30, A(35 + 15 * tier)))
                sharp.ellipse((px - d, py - d, px + d, py + d), fill=(80, 0, 10, A(235)))
                if tier >= 3 and side == 1 and rng.random() < 0.35:
                    sharp.line([(px, py), (px, py + r * rng.uniform(0.3, 0.7))], fill=(150, 10, 20, A(170)),
                               width=max(1, int(d * 0.8)))
    elif kind == "burn":
        for i in range(2 + tier):
            ox, oy, rr = rng.uniform(-0.5, 0.5) * r, rng.uniform(-0.4, 0.4) * r, r * rng.uniform(0.45, 0.85)
            soft.ellipse((x + ox - rr, y + oy - rr * 0.8, x + ox + rr, y + oy + rr * 0.8), fill=(35, 20, 10, A(45 + 18 * tier)))
        if tier >= 2:
            soft.ellipse((x - r * 0.45, y - r * 0.35, x + r * 0.45, y + r * 0.35), fill=(200, 65, 20, A(50 + 18 * tier)))
        if tier >= 4:
            for i in range(4 + tier):
                px, py, s = x + rng.uniform(-0.8, 0.8) * r, y + rng.uniform(-0.6, 0.6) * r, rng.uniform(0.8, 1.8) * u
                sharp.ellipse((px - s, py - s, px + s, py + s), fill=(20, 10, 5, A(200)) if i % 2 else (235, 190, 150, A(170)))
    elif kind == "shock":
        soft.ellipse((x - r, y - r * 0.8, x + r, y + r * 0.8), fill=(60, 40, 10, A(35 + 15 * tier)))
        for i in range(2 + tier // 2):
            a = rng.uniform(0, 2 * math.pi)
            pts = [(x, y)]
            for s in range(1, 5):
                pts.append((x + math.cos(a) * r * 0.35 * s + rng.uniform(-1.5, 1.5) * u,
                            y + math.sin(a) * r * 0.35 * s + rng.uniform(-1.5, 1.5) * u))
            sharp.line(pts, fill=(40, 30, 10, A(190)), width=max(1, int((0.8 + 0.2 * tier) * u)))
            sharp.line(pts, fill=(255, 235, 110, A(190)), width=max(1, int(0.5 * u)))
    elif kind == "cold":
        soft.ellipse((x - r, y - r * 0.8, x + r, y + r * 0.8), fill=(170, 210, 255, A(50 + 15 * tier)))
        for i in range(3 + tier):
            px, py = x + rng.uniform(-0.8, 0.8) * r, y + rng.uniform(-0.6, 0.6) * r
            s = (2 + 0.6 * tier) * u * rng.uniform(0.7, 1.2)
            for k in range(3):
                a = math.pi / 3 * k + rng.uniform(-0.1, 0.1)
                sharp.line([(px - math.cos(a) * s, py - math.sin(a) * s), (px + math.cos(a) * s, py + math.sin(a) * s)],
                           fill=(230, 248, 255, A(220)), width=max(1, int(0.7 * u)))
    elif kind == "grip":
        ang = rng.uniform(0, math.pi)
        for i in range(4):
            t = ang + (i - 1.5) * 0.45
            px, py = x + math.cos(t) * r * 0.7, y + math.sin(t) * r * 0.7
            rw, rh = r * 0.38, r * 0.16
            soft.ellipse((px - rw, py - rh, px + rw, py + rh), fill=(130, 30, 60, A(45 + 18 * tier)))
            if tier >= 3:
                sharp.ellipse((px - u, py - u, px + u, py + u), fill=(110, 10, 20, A(200)))
    else:  # blunt: a bruise that darkens and swells
        # (since build 318) it ages: angry red-purple when fresh, purple, then dark with a yellowing edge
        old_ = 0 if age is None else int(age)
        body_c, core_c = (((150, 40, 75), (110, 20, 50)) if old_ <= 1 else ((70, 30, 90), (50, 15, 60)) if old_ <= 6
                          else ((55, 40, 80), (40, 30, 60)))
        if old_ > 10:
            soft.ellipse((x - r * 1.35, y - r * 1.0, x + r * 1.35, y + r * 1.0), fill=(150, 150, 60, A(30 + 6 * tier)))
        soft.ellipse((x - r * 1.1, y - r * 0.8, x + r * 1.1, y + r * 0.8), fill=body_c + (A(40 + 22 * tier),))
        if tier >= 3 or swell >= 50:
            soft.ellipse((x - r * 0.55, y - r * 0.4, x + r * 0.55, y + r * 0.4), fill=core_c + (A(60 + 15 * tier),))
        if tier >= 2 and rng.random() < 0.6:
            px = x + rng.uniform(-0.4, 0.4) * r
            sharp.line(_ragged(rng, px - r * 0.3, y, px + r * 0.3, y + rng.uniform(-0.2, 0.2) * r, 3, u),
                       fill=(140, 20, 30, A(110 + 15 * tier)), width=max(1, int(0.7 * u)))   # the skin split
    if bleed >= 0.15:
        # (since build 318, body.blood) bleeding now: fresh blood running from it, more the faster it bleeds
        for _i in range(min(4, 1 + int(bleed * 2.5))):
            px = x + rng.uniform(-0.5, 0.5) * r
            sharp.line([(px, y), (px + rng.uniform(-1, 1) * u, y + r * rng.uniform(0.5, 1.1))],
                       fill=(170, 10, 25, A(190)), width=max(1, int(1.1 * u)))
    if tier >= 5:
        # ruined: swollen and dark, blood under and around it, whatever did it
        soft.ellipse((x - r * 1.25, y - r, x + r * 1.25, y + r), fill=(90, 10, 25, A(105)))


def _marks_layer(src, f, spots, o):
    """Every hurt part's marks (window.damage_marks), drawn at twice the size and brought down, so the lines are
    smooth. Each part's marks come from her name and the part, so they stay put from beat to beat and only grow."""
    W, H = src.size
    S = 2
    soft_im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    sharp_im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    soft, sharp = ImageDraw.Draw(soft_im), ImageDraw.Draw(sharp_im)
    u = S * W / PIC
    least = float(o.get("marks_from", 30))
    marks = f.get("marks") or {}
    bd = f.get("body") or {}
    swell, bleed = bd.get("swell") or {}, bd.get("bleeding") or {}
    for part, dmg, res in sorted(f["parts"], key=lambda t: t[1]):
        tier = mark_tier(dmg)
        if dmg < least or not tier or part not in spots:
            continue
        info = marks.get(part) or {}
        kinds = list(info.get("kinds") or ["blunt"])[:2]
        age = info.get("age")
        fresh = age is not None and age <= 1
        rng = random.Random(zlib.crc32(f"{f.get('name')}|{part}".encode()))
        x, y = spots[part][0] * S, spots[part][1] * S
        for i, k in enumerate(kinds):
            # a second kind sits a little to one side of the first, a step lighter
            dx, dy = (rng.uniform(-6, 6) * u, rng.uniform(-4, 4) * u) if i else (0, 0)
            _mark(k, soft, sharp, x + dx, y + dy, u, max(1, tier - i), rng, fresh, age=age,
                  swell=float(swell.get(part, 0)), bleed=float(bleed.get(part, 0)) if i == 0 else 0.0)
    soft_im = soft_im.filter(ImageFilter.GaussianBlur(3 * u))
    soft_im.alpha_composite(sharp_im)
    return soft_im.resize((W, H), Image.LANCZOS)


# whole-body looks for statuses (window.status_look): a tint over her body, and what sparkles or drips on it
STATUS_TINT = {"frozen": ((120, 185, 255), 0.42), "chilled": ((200, 230, 255), 0.18), "soaked": ((90, 140, 220), 0.12),
               "poisoned": ((140, 60, 170), 0.14), "burned": ((90, 40, 20), 0.12), "paralyzed": ((255, 240, 120), 0.08)}


def _status_layer(src, f, mask):
    st = f.get("status") or {}
    have = [k for k in STATUS_TINT if k in st]
    if not have:
        return None
    W, H = src.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for k in have:
        col, share = STATUS_TINT[k]
        tint = Image.new("RGBA", (W, H), col + (0,))
        tint.putalpha(mask.point(lambda a, s=share: int(a * s)))
        layer.alpha_composite(tint)
    box = mask.point(lambda a: 255 if a > 128 else 0).getbbox()
    if box:
        rng = random.Random(zlib.crc32(f"{f.get('name')}|status".encode()))
        dr = ImageDraw.Draw(layer)
        u = W / PIC
        x0, y0, x1, y1 = box
        if "frozen" in st:
            for i in range(18):
                px, py, s = rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(3, 7) * u
                for a in (0, math.pi / 3, 2 * math.pi / 3):
                    dr.line([(px - math.cos(a) * s, py - math.sin(a) * s), (px + math.cos(a) * s, py + math.sin(a) * s)],
                            fill=(240, 250, 255, 235), width=max(1, int(1.2 * u)))
        if "soaked" in st:
            for i in range(7):
                px, py = rng.uniform(x0, x1), rng.uniform(y0, y0 + (y1 - y0) * 0.6)
                dr.ellipse((px - 1.5 * u, py - 2.5 * u, px + 1.5 * u, py + 2.5 * u), fill=(255, 255, 255, 120))
        if "paralyzed" in st:
            for i in range(8):
                px, py = rng.uniform(x0, x1), rng.uniform(y0, y1)
                pts = [(px + rng.uniform(-7, 7) * u, py + k * 6 * u) for k in range(5)]
                dr.line(pts, fill=(90, 70, 0, 200), width=max(1, int(3 * u)))
                dr.line(pts, fill=(255, 240, 90, 245), width=max(1, int(1.5 * u)))
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    return layer


def paint(src, f, spots, o=None):
    """Her picture with what the fight has done to her, each piece switchable (rules.json "window"): the damage glow
    (glow), the marks on each hurt part (damage_marks), the look of her statuses (status_look), all kept on her
    body; greyed out if she is out."""
    if Image is None or src is None:
        return None
    o = o or opts_of(None)
    mask = _body_mask(src)
    out = src.copy()
    # (with the marks on, the glow is half as strong: the colour says how bad, the marks show what it looks like)
    glow_a = 95 if o.get("damage_marks", True) else 190
    for on, make in ((o.get("glow", True), lambda: _glow_layer(src, f, spots, glow_a)),
                     (o.get("damage_marks", True), lambda: _marks_layer(src, f, spots, o))):
        if on:
            layer = make()
            layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
            out.alpha_composite(layer)
    if o.get("status_look", True):
        layer = _status_layer(src, f, mask)
        if layer is not None:
            out.alpha_composite(layer)
    if f.get("out"):
        grey = out.convert("LA").convert("RGBA")
        grey.putalpha(out.getchannel("A"))
        out = grey
    return out


def glow_image(src, f, spots):
    """The picture with each hurt part glowing in its damage colour (the glow alone; paint() does the rest too)."""
    return paint(src, f, spots, {"glow": True, "damage_marks": False, "status_look": False})


def columns(f, spots, rect, parts=None):
    """The parts split into the label column on each side of the picture (each on the side its point is on,
    evened up from the middle), each column top to bottom."""
    cx = rect[0] + rect[2] / 2
    every = f["parts"] if parts is None else parts
    left = [t for t in every if spots[t[0]][0] < cx]
    right = [t for t in every if spots[t[0]][0] >= cx]
    while abs(len(left) - len(right)) > 2:
        big, small = (left, right) if len(left) > len(right) else (right, left)
        t = min(big, key=lambda t: abs(spots[t[0]][0] - cx))
        big.remove(t)
        small.append(t)
    left.sort(key=lambda t: spots[t[0]][1])
    right.sort(key=lambda t: spots[t[0]][1])
    return left, right


def spread(want, H):
    """Label heights: each as near its part as it can be, never closer than a row to the next."""
    ys, last = [], -1e9
    for y in want:
        y = max(y, last + ROW, 9)
        ys.append(y)
        last = y
    over = (ys[-1] + 9 - H) if ys else 0
    if over > 0:
        nxt = H - 9 + ROW
        for i in range(len(ys) - 1, -1, -1):
            ys[i] = min(ys[i], nxt - ROW)
            nxt = ys[i]
    return ys


def _font(size, bold=False):
    if ImageFont is None:
        return None
    for name in (("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else
                 ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def card_panels(f, book, opts=None, plain=False, cache=None):
    """The pictures on one fighter's card, top to bottom: the front, then the back (her back, lower back and tails,
    and any part you moved there). Each is a dict: view, size, src (the prepared picture), pic (with the glow), rect,
    spots, parts, left, right (the label columns), key (where clicks store points), height, state, pose, look.
    plain: the picture as it is, never bent or faded by the program (while you place a point by hand: your own pose
    and state pictures are still the ones shown, so their points go on them). cache: prepared pictures are kept here."""
    o = opts or opts_of(None)
    state = health_state(f, o) if o.get("weak_look", True) else None
    pose = pose_of(f) if o.get("poses", True) else None
    views = ["front"] + (["back"] if o.get("back_view", True) and Image is not None else [])
    picked = {v: book.pick(v, state, pose) if book is not None else None for v in views}
    if "back" in picked and not picked["back"]:
        views.remove("back")
    if len(views) == 2:
        fb, bb = book.base("front"), book.base("back")
        front, back = split_parts(f["parts"], ((fb or (0, 0, ""))[2], (bb or (0, 0, ""))[2]), o)
        if not back:
            views, sets = ["front"], {"front": list(f["parts"])}
        else:
            sets = {"front": front, "back": back}
    else:
        sets = {"front": list(f["parts"])}
    out = []
    for v in views:
        got = picked.get(v)
        size = PIC if v == "front" else int(o.get("back_size", 220))
        look = None
        if got and not got[5] and not plain:
            # no picture of her like this: the program fades her (state) and bends her into the pose (window.poses
            # with pose_fallback; "" = poses on but not bent; None = the old tilt and tip onto her side)
            geo = (pose if o.get("pose_fallback", True) and pose in POSE_GEO else "") if o.get("poses", True) else None
            look = (state, geo) if (state or geo) else None
        if got and got[0]:
            ck = (v, got[2], look, size)
            prep = (cache or {}).get(ck)
            if prep is None:
                prep = prepare_picture(got[0], size, look=look or "")
                if cache is not None:
                    cache[ck] = prep
            src, rect, box, xf = prep
            own, key, fallback, builtin = got[1], got[2], got[3], got[4]
        else:
            src, rect, box, xf = None, (4, 4, size - 8, size - 8), None, None
            own, key, fallback, builtin = False, point_key(f, False) + ("_back" if v == "back" else ""), [], {}
        parts = sets[v]
        spots = anchor_points(f, src, rect, box, own, has_picture=src is not None, key=key, fallback=fallback,
                              builtin=builtin, parts=parts, xf=xf, size=size)
        left, right = columns(f, spots, rect, parts)
        H = max(size, ROW * max(len(left), len(right)) + 12)
        raw = paint(src, f, spots, o) if src is not None else None
        # (since build 306) the grey closing in on her as a choke or the coils near her black-out (window.alive):
        # still in an exported fight, and the window's own frames start from raw
        al = alive_opts({"window": o})
        grey = (body_signs(f, al)["grey"] if raw is not None and not plain and al.get("enabled", True)
                and al.get("grey_in", True) else 0.0)
        out.append({"view": v, "size": size, "src": src, "raw": raw, "grey": grey, "box": box,
                    "pic": grey_image(raw, grey, float(al.get("vignette", 0.75))) if grey else raw,
                    "rect": rect, "spots": spots, "parts": parts, "left": left, "right": right, "key": key,
                    "height": H, "state": state, "pose": pose, "look": look})
    return out


VIEW_CAPTION = {"front": "", "back": "from behind"}
STATE_CAPTION = {"worn": "worn", "hurt": "badly hurt", "down": "down", "out": "out"}


def render_card(f, data=None, own=False, book=None, opts=None):
    """The whole card as one image (Pillow): name, her pictures (front, then back) with each hurt part glowing, a
    line from every part to its label (damage on its colour, resistance in its colour's frame), and health and
    energy bars."""
    if Image is None:
        return None
    if book is None:
        book = PictureBook(f["name"], f.get("species") or f["name"], opts, download=False)
        if data:
            book._base["front"] = (data, own, (f["name"] if own else (f.get("species") or f["name"])).lower(),
                                   {} if own else ARTWORK_POINTS.get((f.get("species") or "").lower(), {}))
    panels = card_panels(f, book, opts)
    W = PIC + 2 * COL
    head, foot, gap = 30, 40, 16
    total = sum(p["height"] for p in panels) + gap * (len(panels) - 1)
    img = Image.new("RGB", (W, head + total + foot), "#ffffff")
    d = ImageDraw.Draw(img)
    big, small, tiny, tinyb = _font(16, True), _font(11), _font(10), _font(10, True)
    st = panels[0]["state"] if panels else None
    d.text((6, 6), f["name"] + ("   — OUT" if f.get("out") else f"   ({STATE_CAPTION[st]})" if st else ""),
           fill="#111827", font=big)
    d.text((W - 6, 9), f"{f.get('species', '')}  ·  {' / '.join(f.get('types') or [])}", fill="#6b7280", font=small,
           anchor="ra")
    y = head
    for pnl in panels:
        draw_panel_pil(d, img, f, pnl, y, big, tiny, tinyb)
        y += pnl["height"] + gap
    pct = 100.0 * f["health"] / max(1e-9, f["max"])
    yb = head + total + 6
    col = "#22c55e" if pct >= 60 else "#eab308" if pct >= 35 else "#f97316" if pct >= 15 else "#ef4444"
    d.rectangle((0, yb, W, yb + 16), fill="#e5e7eb")
    d.rectangle((0, yb, W * max(0.0, min(1.0, pct / 100.0)), yb + 16), fill=col)
    d.text((6, yb + 8), f"Health {f['health']:.0f}%  ({pct:.0f}% of full)", fill="#111827", font=tinyb, anchor="lm")
    d.rectangle((0, yb + 19, W, yb + 28), fill="#e5e7eb")
    d.rectangle((0, yb + 19, W * max(0.0, min(1.0, f.get("energy", 0) / 100.0)), yb + 28), fill="#60a5fa")
    d.text((6, yb + 23), f"energy {f.get('energy', 0):.0f}", fill="#111827", font=tiny, anchor="lm")
    return img


def panel_origin(pnl, top):
    """Where a panel's picture sits on the card: (x, y) of its top-left corner (a smaller picture is centred)."""
    H, size = pnl["height"], pnl["size"]
    return COL + (PIC - size) / 2, top + (H - size) / 2


def draw_panel_pil(d, img, f, pnl, top, big, tiny, tinyb):
    H = pnl["height"]
    ox, oy = panel_origin(pnl, top)
    if pnl["pic"] is not None:
        img.paste(pnl["pic"], (int(ox), int(oy)), pnl["pic"])
    else:
        d.ellipse((ox + 50, oy + 50, ox + pnl["size"] - 50, oy + pnl["size"] - 50), fill="#e5e7eb")
        d.text((ox + pnl["size"] / 2, oy + pnl["size"] / 2), (f.get("species") or f["name"])[:12], fill="#6b7280",
               font=big, anchor="mm")
    cap = VIEW_CAPTION.get(pnl["view"], "")
    if cap:
        d.text((COL + PIC / 2, top - 3), cap, fill="#6b7280", font=tiny, anchor="md")
    spots = pnl["spots"]
    for side, rows in (("L", pnl["left"]), ("R", pnl["right"])):
        ys = spread([oy + spots[p[0]][1] for p in rows], top + H)
        for (part, dmg, res), ly in zip(rows, ys):
            x, y = spots[part]
            ax, ay = ox + x, oy + y
            lx = COL - 4 if side == "L" else COL + PIC + 4
            d.line((lx, ly, ax, ay), fill="#9ca3af", width=1)
            d.ellipse((ax - 3, ay - 3, ax + 3, ay + 3), fill=dmg_color(dmg), outline="#111827")
            if part in held_parts(f):       # (window.hold_panel: a part in someone's grip, ringed)
                d.ellipse((ax - 9, ay - 9, ax + 9, ay + 9), outline="#7c3aed", width=2)
            widths = (76, 38, 40)
            x0 = lx - sum(widths) if side == "L" else lx
            if side == "L":
                d.text((x0 + widths[0] - 2, ly), short(part), fill="#111827", font=tiny, anchor="rm")
            else:
                d.text((x0 + 2, ly), short(part), fill="#111827", font=tiny, anchor="lm")
            bx = x0 + widths[0]
            fill = dmg_color(dmg)
            d.rectangle((bx, ly - 7, bx + widths[1] - 2, ly + 7), fill=fill)
            d.text((bx + (widths[1] - 2) / 2, ly), f"{dmg:.0f}%", fill=text_on(fill), font=tinyb, anchor="mm")
            rx = bx + widths[1]
            d.rectangle((rx, ly - 7, rx + widths[2] - 2, ly + 7), fill="#ffffff", outline=res_color(res), width=2)
            d.text((rx + (widths[2] - 2) / 2, ly), f"{res:.0f}%", fill="#111827", font=tiny, anchor="mm")


# ---- the hold panel and the tap meter (window.hold_panel), shared by the window and the export ----
TAP_LADDER = ("", "holding easily", "it's getting to her", "close to her limit", "very close to tapping",
              "at the edge of tapping")
TAP_COLORS = ("#e5e7eb", "#facc15", "#f59e0b", "#ea580c", "#dc2626", "#7f1d1d")
# (since build 283, window.hold_panel.meter_by "chance") the steps by this beat's real chance of a tap
CHANCE_LADDER = ("no chance of a tap yet", "a tap is far off", "a small chance of a tap", "a real chance of a tap",
                 "close to tapping", "at the edge of tapping")


def chance_level(pct, steps=(3, 10, 25, 50)):
    """The meter's step (0-5) for a tap chance in %: 0 = none at all, then one more step past each of `steps`."""
    pct = float(pct or 0)
    if pct <= 0:
        return 0
    return min(5, 1 + sum(1 for s in list(steps)[:4] if pct >= float(s)))


def pct_text(p):
    """A tap chance (%) for the screen: a small one isn't rounded to 0 (0.4%), a nil one is 0%."""
    p = float(p or 0)
    return "0%" if p <= 0 else "under 0.1%" if p < 0.1 else f"{p:.1f}%" if p < 10 else f"{p:.0f}%"


def _tap_words(t):
    """The hold panel's few words for how near the one she holds is to tapping: [feel level, chance %, meter_by,
    steps] (by this beat's chance unless meter_by is "pain")."""
    if len(t) > 2 and t[2] == "chance":
        return CHANCE_LADDER[chance_level(t[1], t[3] if len(t) > 3 else (3, 10, 25, 50))]
    return TAP_LADDER[max(0, min(5, int(t[0])))] or "not fighting it yet"


def ecg_points(heart, irregular, width, height, x0=0.0, y0=0.0, seconds=6.0):
    """(since build 287) A heartbeat trace for the vitals strip: [(x, y)] across `width`, which always shows about
    `seconds` of it (so a wide card doesn't crowd it with beats), a beat every 60/heart seconds, each a small bump, a
    sharp spike and a slower wave (narrower when the beats come close); irregular = the gaps uneven and now and then
    a beat missed. The same heart rate always draws the same trace."""
    import random as _r
    rng = _r.Random(int(heart) * 7 + (1 if irregular else 0))
    mid = y0 + height * 0.62
    if float(heart) <= 0:
        return [(x0, mid), (x0 + width, mid)]      # (since build 293) her heart stopped: a flat line
    amp = height * 0.5
    gap = max(6.0, (float(width) / max(1.0, seconds)) * 60.0 / max(20.0, float(heart)))
    k = min(1.0, gap / 20.0)       # the beat's own shape, squeezed when the beats come close
    pts, x = [(x0, mid)], x0 + gap * 0.4
    while x < x0 + width - 12:
        g = gap * (rng.uniform(0.65, 1.4) if irregular else 1.0)
        if irregular and rng.random() < 0.15:
            x += g             # a missed beat: the line runs on flat
            continue
        for dx, dy in ((0, 0), (2, -0.12), (4, 0), (6, 0.12), (7.5, -1.0), (9, 0.35), (10.5, 0), (14, -0.22),
                       (17, 0)):
            if x + dx * k < x0 + width:
                pts.append((x + dx * k, mid + dy * amp))
        x += g
    pts.append((x0 + width, mid))
    return pts


class EcgStream:
    """(since build 315, window.live_ecg) A heart trace that runs like a real monitor's instead of one pattern
    repeating: each beat is laid down as the time comes, from her rate now. A healthy heart's gaps vary a little (a
    few percent) and each beat is a touch taller or shorter; an irregular one's gaps are uneven, now and then a beat
    is skipped, and now and then one comes early, wide and odd-shaped, with a pause after it; a stopped one is a
    flat line with a faint wander. A new rate shows from the next beat on, never a jump. The baseline's small
    wander and noise follow the clock, so the trace slides without flickering. clench(t) is how far her heart is
    squeezed at t, on the same beats (for the beating heart picture and the card's throb)."""

    def __init__(self, heart, irregular=False, seed=0):
        import random as _r
        self.rng = _r.Random(seed)
        self.beats = []              # (start time, kind, height, length)
        self.next_t = None
        self.set(heart, irregular)

    def set(self, heart, irregular=False):
        self.heart, self.irregular = max(0.0, float(heart or 0)), bool(irregular)

    def _interval(self):
        base = 60.0 / max(20.0, self.heart)
        return base * (self.rng.uniform(0.62, 1.45) if self.irregular else 1.0 + self.rng.gauss(0.0, 0.03))

    def _fill(self, t_end):
        if self.next_t is None:
            self.next_t = t_end - 7.0
        while self.next_t <= t_end + 1.0:
            if self.heart <= 0:
                self.next_t = t_end + 0.5        # (stopped: nothing to lay down; a new rate starts it from here)
                break
            base = 60.0 / max(20.0, self.heart)
            length = min(1.0, (base / 0.6) ** 0.5)       # (each beat's shape squeezed when they come close)
            gap = self._interval()
            r = self.rng.random()
            if self.irregular and r < 0.12:
                self.next_t += gap                         # a skipped beat: the line runs on flat
                continue
            if self.irregular and r < 0.22:
                early = self.next_t - gap * 0.35 if self.beats and self.next_t - gap * 0.35 > self.beats[-1][0] \
                    + 0.3 else self.next_t
                self.beats.append((early, "early", self.rng.uniform(1.1, 1.35), length))
                self.next_t = early + gap * 1.6            # (the pause after it)
                continue
            self.beats.append((self.next_t, "normal", self.rng.uniform(0.9, 1.08) if not self.irregular
                               else self.rng.uniform(0.75, 1.1), length))
            self.next_t += gap
        self.beats = [b for b in self.beats if b[0] > t_end - 8.0]

    # a normal beat, in seconds from its start: P wave, a flat, Q, R, S, back, then the T wave (y up = negative)
    NORMAL = ((0.0, 0), (0.03, -0.1), (0.06, -0.12), (0.09, 0), (0.12, 0), (0.135, 0.1), (0.155, -1.0),
              (0.175, 0.32), (0.19, 0), (0.28, -0.08), (0.34, -0.24), (0.4, -0.08), (0.45, 0))
    EARLY = ((0.0, 0), (0.03, 0.15), (0.08, -1.0), (0.14, 0.55), (0.2, 0.1), (0.3, 0.3), (0.4, 0.05), (0.45, 0))

    @staticmethod
    def _wander(t):
        return 0.035 * math.sin(t * 0.83) + 0.015 * math.sin(t * 7.1 + 1.3) + 0.01 * math.sin(t * 17.9 + 0.4)

    def points(self, t, width, height, x0=0.0, y0=0.0, seconds=6.0):
        """The trace as [x, y, x, y, ...] for the last `seconds` up to time t, across `width`."""
        self._fill(t)
        mid, amp = y0 + height * 0.62, height * 0.5
        t0 = t - seconds
        sx = float(width) / seconds
        pts = []
        cur = t0
        for start, kind, h, length in self.beats:
            shape = self.EARLY if kind == "early" else self.NORMAL
            end = start + shape[-1][0] * length
            if end < t0 or start > t:
                continue
            while cur < start:                    # the baseline up to the beat
                if cur >= t0:
                    pts.append((cur, self._wander(cur)))
                cur += 0.05
            for dt, dy in shape:
                tt = start + dt * length
                if t0 <= tt <= t:
                    pts.append((tt, dy * h + self._wander(tt)))
            cur = max(cur, end)
        while cur <= t:
            pts.append((cur, self._wander(cur)))
            cur += 0.05
        out = []
        for tt, v in pts:
            out += [x0 + (tt - t0) * sx, mid + v * amp]
        return out if len(out) >= 4 else [x0, mid, x0 + width, mid]

    def clench(self, t):
        """How far her heart is squeezed at time t (0 to 1), on the trace's own beats."""
        if self.heart <= 0:
            return 0.0
        self._fill(t)
        last = max((b for b in self.beats if b[0] <= t), key=lambda b: b[0], default=None)
        if last is None:
            return 0.0
        ph = (t - last[0] - 0.15 * last[3]) / max(0.05, 60.0 / max(20.0, self.heart))
        if ph < 0:
            return 0.0
        if ph < 0.12:
            return ph / 0.12
        return max(0.0, math.exp(-(ph - 0.12) / 0.1))


def squeeze_shapes(squeeze, coils, x0, width, y0, height, ring=False):
    """(since build 294; drawn from the outside in since build 295) The squeeze bar: her chest or belly as a band that
    narrows from both ends as the coils close in (squeeze: 0-100, down to about a third of its width at 92%), with the
    coils OUTSIDE her: wrapped round the band, and pressing in from both ends, filling the room she has lost (one
    stripe a side for each coil round her). (since build 296) ring: a cross-section, the coils all the way round her,
    along the top and bottom too (her front and back), so they touch her on every side, her flanks at the ends.
    Returns (full outline box, squeezed body box, [coil boxes])."""
    full = (x0, y0, x0 + width, y0 + height)
    sq = min(100.0, max(0.0, float(squeeze)))
    cut = max(3.0, width * 0.35 * sq / 100.0)
    edge = round(1.5 + 1.5 * sq / 100.0, 1) if ring else 0.0      # front and back: thicker as she is pressed flat
    body = (x0 + cut, y0 + max(1.0, edge), x0 + width - cut, y0 + height - max(1.0, edge))
    n = max(1, min(4, int(coils or 1)))
    step = cut / n
    sides = []
    for k in range(n):
        sides.append((x0 + k * step, y0, x0 + (k + 1) * step - 1, y0 + height))                  # pressing in from the left
        sides.append((x0 + width - (k + 1) * step + 1, y0, x0 + width - k * step, y0 + height))  # and from the right
    if ring:
        sides.append((x0, y0, x0 + width, y0 + edge))                       # across her front
        sides.append((x0, y0 + height - edge, x0 + width, y0 + height))     # and her back
    return full, body, sides


# (since build 299) the squeeze figure: her torso from the front, a stylised shape of its own (her artwork may face any
# way), its half-width down its length (t: 0 at the base of her neck, 1 at her hips), as a share of the figure's width
TORSO_PROFILE = [(0.0, 0.17), (0.06, 0.30), (0.14, 0.42), (0.26, 0.42), (0.40, 0.39), (0.55, 0.34), (0.66, 0.34),
                 (0.78, 0.37), (0.90, 0.39), (1.0, 0.36)]


def _torso_hw(t):
    for (t0, w0), (t1, w1) in zip(TORSO_PROFILE, TORSO_PROFILE[1:]):
        if t0 <= t <= t1:
            k = (t - t0) / max(1e-6, t1 - t0)
            k = k * k * (3 - 2 * k)
            return w0 + (w1 - w0) * k
    return TORSO_PROFILE[-1][1]


def _tube(path, rad):
    """A thick band along a path of points (rad: its half-width at each point, or one number): its outline."""
    rads = rad if isinstance(rad, (list, tuple)) else [rad] * len(path)
    left, right = [], []
    for k, (x, y) in enumerate(path):
        xa, ya = path[max(0, k - 1)]
        xb, yb = path[min(len(path) - 1, k + 1)]
        dx, dy = xb - xa, yb - ya
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n, dx / n
        left.append((x + nx * rads[k], y + ny * rads[k]))
        right.append((x - nx * rads[k], y - ny * rads[k]))
    return left + list(reversed(right))


def squeeze_figure(squeeze, where, coils, x0, y0, w, h, ratio=None):
    """(since build 299) The squeeze drawn as a body: her torso from the front (head, shoulders, her arms pinned to
    her sides, a lighter belly) with the coils wound round it in a spiral, each loop pressing her in and the flesh
    between loops bulging out a little, more the harder she is squeezed (squeeze 0-100: a third of her width gone at
    92%); her ribs show through once it is crushing (her heart has its own picture: heart_shapes). where: chest,
    belly or both (back counts as chest). ratio: how many times her size the coiler is: a coiler much bigger than her
    winds fewer, far thicker loops (one loop of a Milotic is most of a Buizel's chest). Only the coils on her are drawn,
    not the rest of the coiler. Returns point lists: "head", "body", "shade" [left, right], "belly", "arms", "paws",
    "loops" [{"poly", "dark", "shine"}] (each loop's near side), "creases" (the flesh bulging at each loop's edges), "ribs"."""
    sq = max(0.0, min(100.0, float(squeeze or 0))) / 100.0
    where = where if where in ("chest", "belly", "both") else "chest"
    n = max(1, min(4, int(coils or 1)))
    t_top, t_bot = 0.16, 1.0
    span = {"chest": (0.25, 0.58), "belly": (0.55, 0.92), "both": (0.25, 0.92)}[where]
    # how thick her coils are against this body: a coiler her own size about a tenth of her torso, a giant far more
    big = max(0.6, min(10.0, float(ratio or 1.0)))
    th0 = max(0.04, min(0.17, 0.05 + 0.014 * big))
    loops_n = max(1, min(5, int(round((span[1] - span[0]) / (2.1 * th0))) + (n - 1) // 2))
    gap = (span[1] - span[0]) / loops_n
    centres = [span[0] + gap * (i + 0.5) for i in range(loops_n)]
    depth = 0.38 * sq
    th = min(0.5 * gap, th0) * (1.0 - 0.15 * sq)        # each loop's half-thickness (a little thinner, pulled tight)

    def pinch(t):
        # pressed in under each loop, the flesh between them bulging back out a little, eased off past the coils
        under = max((math.exp(-((t - c) / (0.55 * gap)) ** 2) for c in centres), default=0.0)
        out = min(abs(t - span[0]), abs(t - span[1])) if not span[0] <= t <= span[1] else 0.0
        return depth * (0.45 * math.exp(-(out / 0.07) ** 2) + 0.55 * under)

    def X(u):
        return x0 + w / 2 + u * w

    def Y(t):
        return y0 + h * t

    def hw(t):
        return 0.9 * _torso_hw((t - t_top) / (t_bot - t_top)) * (1 - pinch(t))

    ts = [t_top + (t_bot - t_top) * i / 48 for i in range(49)]
    body = [(X(hw(t)), Y(t)) for t in ts] + [(X(-hw(t)), Y(t)) for t in reversed(ts)]
    # the roundness of her: shadow down each side
    shade = [[(X(side * hw(t)), Y(t)) for t in ts] + [(X(side * hw(t) * 0.72), Y(t)) for t in reversed(ts)]
             for side in (-1, 1)]
    b_ts = [0.3 + 0.66 * i / 24 for i in range(25)]
    belly = [(X(hw(t) * 0.5 * math.sin(math.pi * (t - 0.3) / 0.66) ** 0.5), Y(t)) for t in b_ts] + \
            [(X(-hw(t) * 0.5 * math.sin(math.pi * (t - 0.3) / 0.66) ** 0.5), Y(t)) for t in reversed(b_ts)]
    head = [(X(0.27 * math.cos(a)), Y(0.095 + 0.095 * math.sin(a)))
            for a in (2 * math.pi * k / 36 for k in range(36))]
    # her arms, pinned to her sides from the shoulder down, her paws showing at the ends
    arms, paws = [], []
    a_ts = [0.25 + 0.36 * i / 14 for i in range(15)]
    for side in (-1, 1):
        path = [(X(side * (hw(t) - 0.01)), Y(t)) for t in a_ts]
        rads = [w * 0.05 * (1 - 0.3 * i / 14) for i in range(15)]
        arms.append(_tube(path, rads))
        # (the shoulder rounded over the top, the paw at the end)
        sx_, sy_ = path[0]
        paws.append([(sx_ + rads[0] * math.cos(a), sy_ + rads[0] * math.sin(a))
                     for a in (2 * math.pi * k / 16 for k in range(16))])
        px, py = path[-1]
        paws.append([(px + w * 0.05 * math.cos(a), py + w * 0.035 + w * 0.045 * math.sin(a))
                     for a in (2 * math.pi * k / 16 for k in range(16))])
    loops, creases = [], []
    for k, c in enumerate(centres):
        lw = hw(c) + 0.045 + th * 0.6         # the loop lies OUTSIDE her, over her arms; a thick one stands out further
        tilt = 0.3 * gap
        sag = 0.03
        top, bot, dark, shine = [], [], [], []
        for i in range(25):
            u = -1 + 2 * i / 24
            dy = sag * (1 - u * u) - tilt * u / 2
            r = th * math.sqrt(max(0.0, 1 - u ** 8))       # rounded off at the ends, where it turns behind her
            top.append((X(u * lw), Y(c - r + dy)))
            bot.append((X(u * lw), Y(c + r + dy)))
            dark.append((X(u * lw), Y(c + 0.3 * r + dy)))
            shine.append((X(u * lw * 0.9), Y(c - 0.5 * r + dy)))
        loops.append({"poly": top + list(reversed(bot)), "dark": dark + list(reversed(bot)), "shine": shine})
        if sq > 0.15:
            for sgn in (-1, 1):
                creases.append([(X(u * hw(c) * 0.9), Y(c + sgn * (th + 0.012) + sag * (1 - u * u) - tilt * u / 2))
                                for u in (-0.8, -0.4, 0.0, 0.4, 0.8)])
    ribs = []
    if sq >= 0.5 and where in ("chest", "both"):
        # crushing: her ribs show through between the loops
        for k in range(4):
            t = 0.27 + 0.065 * k
            w_ = hw(t)
            for side in (-1, 1):
                ribs.append([(X(side * w_ * 0.15), Y(t)), (X(side * w_ * 0.55), Y(t + 0.012)),
                             (X(side * w_ * 0.85), Y(t + 0.04))])
    return {"head": head, "body": body, "shade": shade, "belly": belly, "arms": arms, "paws": paws, "loops": loops,
            "creases": creases, "ribs": ribs, "sq": sq}


def heart_points(cx, cy, r, scale=1.0):
    """A heart shape round (cx, cy), r its half-width, as a point list (a canvas polygon or an SVG path)."""
    pts = []
    for i in range(36):
        a = 2 * math.pi * i / 36
        x = 16 * math.sin(a) ** 3
        y = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
        pts.append((cx + x / 16 * r * scale, cy + y / 16 * r * scale))
    return pts


def mix(c1, c2, k):
    """Colour c1 moved toward c2 by k (0-1), both "#rrggbb"."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    k = max(0.0, min(1.0, k))
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * k)) for x, y in zip(a, b))


def picture_colours(book, fallback="#c08457"):
    """Her colours, from her own front picture: (main, lighter or None): the biggest group of like colours among its
    opaque pixels (so a cream body with a few red spots reads as cream), and the next big group if it is clearly
    lighter (a Buizel's cream belly). Kept on the book once worked out; (fallback, None) with no picture."""
    if book is None or Image is None:
        return fallback, None
    got = getattr(book, "_main_colours", None)
    if got:
        return got
    out = (fallback, None)
    try:
        base = book.base("front")
        if base and base[0]:
            im = Image.open(io.BytesIO(base[0])).convert("RGBA").resize((48, 48))
            bins = {}
            for r, g, b, a in im.getdata():
                if a > 200:
                    bins.setdefault((r // 48, g // 48, b // 48), []).append((r, g, b))
            groups = sorted(bins.values(), key=len, reverse=True)
            if groups:
                avg = [tuple(sum(c[i] for c in grp) // len(grp) for i in range(3)) for grp in groups[:4]]
                main = avg[0]
                light = next((c for c, grp in zip(avg[1:], groups[1:4]) if sum(c) > sum(main) + 90
                              and len(grp) >= 0.12 * len(groups[0])), None)
                out = ("#%02x%02x%02x" % main, ("#%02x%02x%02x" % light) if light else None)
    except Exception as e:
        from engine import note_failure
        note_failure("working out a fighter's colours for the squeeze figure", e)
    try:
        book._main_colours = out
    except AttributeError:
        pass
    return out


def squeeze_svg(v, body="#c08457", coil="#5d8fcf", belly=None, width=440):
    """(since build 299) The squeeze figure as an SVG picture of its own (exported fights): her torso in the coils,
    and her heart beside it beating at her rate (an animation drawn from heart_beat), as in the window."""
    import html as _h
    where = v.get("where") if v.get("where") in ("chest", "belly", "both") else "chest"
    col = squeeze_colours(v, body, coil, belly)
    fg = squeeze_figure(v["squeeze"], where, v.get("coils"), 14, 6, 84, 140, v.get("coil_ratio"))

    def P(pts):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    def poly(pts, fill, stroke="none", sw=1):
        return f'<polygon points="{P(pts)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'

    def line(pts, stroke, sw=1):
        return (f'<polyline points="{P(pts)}" fill="none" stroke="{stroke}" stroke-width="{sw}" '
                f'stroke-linecap="round" stroke-linejoin="round"/>')
    out = [f'<svg class="squeeze" viewBox="0 0 {width} 150" width="100%" style="background:#111827;'
           f'border-radius:4px;max-width:520px;margin-top:2px">']
    out += [poly(fg["head"], col["body"], col["body_edge"]), poly(fg["body"], col["body"], col["body_edge"])]
    out += [poly(sh, col["shade"]) for sh in fg["shade"]] + [poly(fg["belly"], col["belly"])]
    out += [line(r, col["rib"]) for r in fg["ribs"]]
    out += [poly(a, col["arm"], col["body_edge"]) for a in fg["arms"] + fg["paws"]]
    out += [line(c, col["crease"]) for c in fg["creases"]]
    for lp in fg["loops"]:
        out += [poly(lp["poly"], col["coil"], col["coil_edge"]), poly(lp["dark"], col["coil_dark"]),
                line(lp["shine"], col["coil_shine"], 2)]
    hx, hy, hr = 160, 64, 22
    on_chest = where in ("chest", "both")
    hs = heart_shapes(hx, hy, hr, v["squeeze"], on_chest, v.get("blood", 0), 0.0, bool(v.get("stopped")))
    out += [poly(pr, col["coil"], col["coil_edge"]) for pr in hs["press"]]
    dark = mix(col["heart"], "#000000", 0.3)
    heart = ("".join(line(pts, dark, round(wd, 1)) for pts, wd in hs["vessels"])
             + poly(hs["heart"], col["heart"], mix(col["heart"], "#000000", 0.5)) + line(hs["split"], dark)
             + line(hs["shine"], mix(col["heart"], "#ffffff", 0.5), 2))
    hrate = 0 if v.get("stopped") else float(v.get("heart") or 0)
    if hrate > 0:
        # the beat as an animation: her heart clenching (smaller) on each beat, through a cycle of her own rhythm
        irr = bool(v.get("irregular"))
        cycle = 60.0 / hrate * (sum(IRREGULAR_GAPS) if irr else 1.0)
        steps = 40
        vals = ";".join(f"{1 - 0.2 * heart_beat(hrate, cycle * k / steps, irr):.3f}" for k in range(steps + 1))
        heart = (f'<g transform="translate({hx},{hy})"><g><animateTransform attributeName="transform" type="scale" '
                 f'values="{vals}" dur="{cycle:.2f}s" repeatCount="indefinite"/>'
                 f'<g transform="translate({-hx},{-hy})">{heart}</g></g></g>')
    out.append(heart)
    for sh in squeeze_readout(v, 200, 14, width - 206):
        if sh[0] == "text":
            _, tx, ty, text, colr, size, bold = sh
            weight = ' font-weight="bold"' if bold else ""
            out.append(f'<text x="{tx}" y="{ty + size}" fill="{colr}" font-size="{size + 1}"{weight}>'
                       f'{_h.escape(text)}</text>')
        elif sh[0] == "rect":
            _, a, b, c2, d2, fill, stroke = sh
            out.append(f'<rect x="{a:.1f}" y="{b}" width="{max(0.0, c2 - a):.1f}" height="{d2 - b}" fill="{fill}" '
                       f'stroke="{stroke or "none"}"/>')
        else:
            _, a, b, c2, d2, colr, dashed = sh
            dash = ' stroke-dasharray="2,2"' if dashed else ""
            out.append(f'<line x1="{a:.1f}" y1="{b}" x2="{c2:.1f}" y2="{d2}" stroke="{colr}" stroke-width="1.5"{dash}/>')
    out.append("</svg>")
    return "".join(out)


# (since build 304) the hold picture: which way a grip presses, from what it holds and what it is called
LOCK_WORDS = re.compile(r"(?i)\b(?:lock|bar|hammerlock|kimura|americana|crank|wrench|twist|nelson|hold|"
                        r"split|stretch|scissor|leglock|heel|ankle|knee|wrist|elbow|shoulder)")
CHOKE_WORDS = re.compile(r"(?i)\b(?:choke|sleeper|guillotine|strangle|triangle|throat)")
CRUSH_WORDS = re.compile(r"(?i)\b(?:bear hug|body lock|crush|squeeze|body scissors|waist)")
COIL_WORDS = re.compile(r"(?i)\b(?:coil|constrict|wrap)")
HEAD_WORDS = re.compile(r"(?i)\b(?:headlock|head lock|face lock|chancery|front lock)")


def _side_of(part):
    p = str(part).lower()
    return -1 if p.startswith("right ") else 1 if p.startswith("left ") else 0   # (her left is the viewer's right)


def grip_kind(g):
    """What a grip on her does, for the hold picture: "choke", "lock" (a limb's joint forced), "crush" (her body
    squeezed), "head", "bound" (coils round a limb), "grab" or "pin"."""
    what = str(g.get("what") or "")
    regs = [body_region(p) for p in g.get("parts") or ()]
    limbs = [r for r in regs if r in ("fore_up", "fore_low", "hind_up", "hind_low", "shoulder", "tail")]
    # (what the hold is called says it first: a full nelson holds her neck but cranks it; a sleeper chokes)
    if CHOKE_WORDS.search(what):
        return "choke"
    if HEAD_WORDS.search(what):
        return "head"
    if CRUSH_WORDS.search(what):
        return "crush"
    if what == "coils" or COIL_WORDS.search(what):
        # (since build 324) a coil submission (an upright coil, a constriction) squeezes: it never forces a joint
        # (the build-323 picture bent Ripples' hip in Seraphina's upright coil, round her ribs and hip)
        if "neck" in regs:
            return "choke"
        return "bound" if regs and len(limbs) == len(regs) else "crush"
    if what in ("grab", "hold") and not g.get("locked"):
        return "grab"
    if "neck" in regs and not limbs:
        return "choke"
    if regs and all(r == "head" for r in regs):
        return "head"
    return "lock" if limbs else "crush"


def _arrow(x0, y0, x1, y1, size=5.0):
    """An arrowhead at (x1, y1), pointing from (x0, y0): its three points."""
    a = math.atan2(y1 - y0, x1 - x0)
    return [(x1, y1), (x1 - size * math.cos(a - 0.45), y1 - size * math.sin(a - 0.45)),
            (x1 - size * math.cos(a + 0.45), y1 - size * math.sin(a + 0.45))]


def hold_shapes(f, x0, y0, w, h, tx, width, body="#c08457", belly=None, holders=None):
    """(since build 304) The grips on her as a picture of their own, for the window and exported fights: her body
    from the front (stylised, whatever way her artwork faces), each part in a grip outlined in the holder's colour,
    and what each grip does to her drawn on it: a joint lock bends her limb past where it should go (further the
    nearer the pain is to what she can bear) with an arrow round the joint; a choke presses in at her neck; a crush
    squeezes her body from both sides; a head hold clamps her head; coils wind round a limb; a grab leaves grip marks;
    a pin bears down on her. Beside it, each grip, a gauge (her pain against what she can bear, her air for a choke,
    a pin's count) and this beat's tap chance. Shapes: ("poly", pts, fill, outline, width), ("line", pts, colour,
    width), ("rect", x0, y0, x1, y1, fill, outline), ("text", x, y, text, colour, size, bold). Returns (shapes,
    height), or ([], 0) when nothing holds her (coils round her body have their own picture: squeeze_figure)."""
    gr = f.get("grips") or {}
    held = [g for g in gr.get("held") or () if not (g.get("what") == "coils"
                                                   and any(body_region(p) in ("chest", "belly", "back_up", "back_low")
                                                           for p in g.get("parts") or ()))]
    pin = gr.get("pin")
    if not held and not pin:
        return [], 0
    holders = holders or {}
    skin = mix(body, "#000000", 0.0)
    edge = mix(skin, "#000000", 0.45)
    out = []
    cx = x0 + w / 2.0

    def X(u):
        return cx + u * w

    def Y(t):
        return y0 + t * h

    def hw(t):
        return 0.62 * _torso_hw((t - 0.2) / 0.42)
    names = {p for g in held for p in g.get("parts") or ()}
    has_tail = any("tail" in str(n).lower() for n, *_ in f.get("parts") or ())
    # the joints of her limbs (shoulder, elbow, paw; hip, knee, foot), each side; a joint lock bends one past its range
    pain = {}
    t_ = gr.get("tap") or {}
    if t_.get("pain") is not None and t_.get("resist"):
        pain[t_.get("by")] = min(1.3, float(t_["pain"]) / max(1.0, float(t_["resist"])))
    bend = {}
    for g in held:
        if grip_kind(g) == "lock":
            k = 0.35 + 0.8 * pain.get(g.get("by"), 0.4)
            for p in g.get("parts") or ():
                r = body_region(p)
                sd = _side_of(p) or 1
                if r in ("fore_up", "fore_low", "shoulder"):
                    bend[("arm", sd)] = max(bend.get(("arm", sd), 0), k)
                elif r in ("hind_up", "hind_low"):
                    bend[("leg", sd)] = max(bend.get(("leg", sd), 0), k)

    def limb(kind, sd):
        if kind == "arm":
            a = (X(sd * (hw(0.25) + 0.02)), Y(0.25))
            b = (X(sd * (hw(0.25) + 0.08)), Y(0.42))
            down = (X(sd * (hw(0.25) + 0.1)), Y(0.58))
        else:
            a = (X(sd * 0.17), Y(0.62))
            b = (X(sd * 0.2), Y(0.8))
            down = (X(sd * 0.21), Y(0.98))
        k = bend.get((kind, sd), 0)
        if k:
            # forced the wrong way at the joint: the lower limb swung out and up past straight
            ang = math.atan2(down[1] - b[1], down[0] - b[0]) - sd * k * (1.4 if kind == "arm" else 1.1)
            ln = math.hypot(down[0] - b[0], down[1] - b[1])
            down = (b[0] + ln * math.cos(ang), b[1] + ln * math.sin(ang))
        return [a, b, down]
    joints = {(kd, sd): limb(kd, sd) for kd in ("arm", "leg") for sd in (-1, 1)}
    # her body
    if has_tail:
        tp = [(X(0.06), Y(0.64)), (X(0.3), Y(0.6)), (X(0.42), Y(0.46)), (X(0.44), Y(0.34))]
        out.append(("poly", _tube(tp, [w * 0.05, w * 0.045, w * 0.035, w * 0.02]), mix(skin, "#000000", 0.12), edge, 1))
    for (kd, sd), pts in joints.items():
        out.append(("poly", _tube(pts, w * (0.055 if kd == "arm" else 0.07)), mix(skin, "#000000", 0.08), edge, 1))
    ts = [0.2 + 0.42 * i / 30 for i in range(31)]
    out.append(("poly", [(X(hw(t)), Y(t)) for t in ts] + [(X(-hw(t)), Y(t)) for t in reversed(ts)], skin, edge, 1))
    if belly:
        bt = [0.3 + 0.3 * i / 16 for i in range(17)]
        out.append(("poly", [(X(hw(t) * 0.5), Y(t)) for t in bt] + [(X(-hw(t) * 0.5), Y(t)) for t in reversed(bt)],
                    belly, "", 0))
    out.append(("poly", [(X(0.07), Y(0.15)), (X(0.07), Y(0.21)), (X(-0.07), Y(0.21)), (X(-0.07), Y(0.15))],
                skin, edge, 1))
    head = [(X(0.17 * math.cos(a)), Y(0.09 + 0.085 * math.sin(a))) for a in (2 * math.pi * k / 32 for k in range(32))]
    out.append(("poly", head, skin, edge, 1))
    # each grip, drawn where it is and how it presses
    lines = []
    for g in held:
        col = holders.get(g.get("by")) or "#5d8fcf"
        dark = mix(col, "#000000", 0.4)
        kd = grip_kind(g)
        parts = g.get("parts") or []
        for p in parts:
            r, sd = body_region(p), _side_of(p) or 1
            if r == "shoulder":
                (sx_, sy_) = joints[("arm", sd)][0]
                ring = [(sx_ + w * 0.08 * math.cos(a), sy_ + w * 0.08 * math.sin(a))
                        for a in (2 * math.pi * k / 16 for k in range(16))]
            elif r in ("fore_up", "fore_low"):
                pts = joints[("arm", sd)]
                ring = _tube(pts[:2] if r == "fore_up" else pts[1:], w * 0.075)
            elif r in ("hind_up", "hind_low"):
                pts = joints[("leg", sd)]
                ring = _tube(pts[:2] if r == "hind_up" else pts[1:], w * 0.09)
            elif r == "head":
                ring = head
            elif r == "neck":
                ring = [(X(0.09), Y(0.14)), (X(0.09), Y(0.22)), (X(-0.09), Y(0.22)), (X(-0.09), Y(0.14))]
            elif r == "tail" and has_tail:
                ring = _tube([(X(0.3), Y(0.6)), (X(0.42), Y(0.46))], w * 0.06)
            else:
                lo, hi = (0.2, 0.42) if r in ("chest", "back_up") else (0.4, 0.62)
                tt = [lo + (hi - lo) * i / 10 for i in range(11)]
                ring = [(X(hw(t)), Y(t)) for t in tt] + [(X(-hw(t)), Y(t)) for t in reversed(tt)]
            out.append(("line", ring + ring[:1], col, 2.5))
        if kd == "lock":
            for (lk, sd), k in bend.items():
                if not any(body_region(p) in (("fore_up", "fore_low", "shoulder") if lk == "arm" else
                                              ("hind_up", "hind_low")) and (_side_of(p) or 1) == sd for p in parts):
                    continue
                bx, by_ = joints[(lk, sd)][1]
                arc = [(bx + 11 * math.cos(a), by_ + 11 * math.sin(a))
                       for a in (math.pi * (0.1 + 0.07 * i) * (1 if sd > 0 else -1) + (0 if sd > 0 else math.pi)
                                 for i in range(10))]
                out.append(("line", arc, "#fbbf24", 2))
                out.append(("poly", _arrow(*arc[-2], *arc[-1]), "#fbbf24", "", 0))
        elif kd == "choke":
            for sd in (-1, 1):
                a0, a1 = (X(sd * 0.32), Y(0.18)), (X(sd * 0.12), Y(0.18))
                out.append(("line", [a0, a1], "#fbbf24", 2))
                out.append(("poly", _arrow(*a0, *a1), "#fbbf24", "", 0))
            out.append(("poly", [(X(0.1), Y(0.16)), (X(0.1), Y(0.2)), (X(-0.1), Y(0.2)), (X(-0.1), Y(0.16))],
                        col, dark, 1))
        elif kd == "crush":
            for t in (0.33, 0.5):
                for sd in (-1, 1):
                    a0, a1 = (X(sd * (hw(t) + 0.22)), Y(t)), (X(sd * (hw(t) + 0.03)), Y(t))
                    out.append(("line", [a0, a1], "#fbbf24", 2))
                    out.append(("poly", _arrow(*a0, *a1), "#fbbf24", "", 0))
            out.append(("poly", [(X(hw(0.4) + 0.03), Y(0.37)), (X(hw(0.4) + 0.03), Y(0.44)),
                                 (X(-hw(0.4) - 0.03), Y(0.44)), (X(-hw(0.4) - 0.03), Y(0.37))], col, dark, 1))
        elif kd == "head":
            out.append(("poly", [(X(0.2), Y(0.07)), (X(0.2), Y(0.12)), (X(-0.2), Y(0.12)), (X(-0.2), Y(0.07))],
                        col, dark, 1))
        elif kd == "bound":
            for p in parts:
                r, sd = body_region(p), _side_of(p) or 1
                lk = "arm" if r in ("fore_up", "fore_low", "shoulder") else "leg"
                (ax, ay), (bx, by_), (dx, dy) = joints[(lk, sd)]
                for k in (0.3, 0.55, 0.8):
                    mx_, my_ = bx + (dx - bx) * k, by_ + (dy - by_) * k
                    out.append(("poly", [(mx_ - 7, my_ - 3), (mx_ + 7, my_ - 1), (mx_ + 7, my_ + 3), (mx_ - 7, my_ + 1)],
                                col, dark, 1))
        else:   # a grab: the marks of her grip on the part
            for p in parts[:2]:
                r, sd = body_region(p), _side_of(p) or 1
                if r in ("fore_up", "fore_low", "shoulder"):
                    mx_, my_ = joints[("arm", sd)][1]
                elif r in ("hind_up", "hind_low"):
                    mx_, my_ = joints[("leg", sd)][1]
                elif r == "head":
                    mx_, my_ = X(0), Y(0.09)
                else:
                    mx_, my_ = X(0), Y(0.4)
                for k in (-1, 0, 1):
                    out.append(("line", [(mx_ + 4 * k - 2, my_ - 4), (mx_ + 4 * k, my_), (mx_ + 4 * k - 2, my_ + 4)],
                                dark, 2))
        lines.append((g, kd, col))
    if pin:
        for xx in (-0.15, 0.15):
            for tt in (0.3, 0.6):
                a0, a1 = (X(xx), Y(tt - 0.16)), (X(xx), Y(tt - 0.03))
                out.append(("line", [a0, a1], "#fbbf24", 3))
                out.append(("poly", _arrow(*a0, *a1, 6), "#fbbf24", "", 0))
    # beside her: each grip, its gauge, the tap chance
    y = y0 + 2
    word = {"lock": "forcing a joint", "choke": "choking her", "crush": "crushing her", "head": "clamping her head",
            "bound": "binding a limb", "grab": "holding on"}
    for g, kd, col in lines[:3]:
        what = str(g.get("what") or "hold")
        on = ", ".join(str(p).lower() for p in (g.get("parts") or [])[:3])
        out.append(("text", tx, y, f"{what[:1].upper() + what[1:]} by {g.get('by')}: {word[kd]}",
                    mix(col, "#ffffff", 0.45), 9, True))
        y += 15
        out.append(("text", tx, y, f"on her {on} · beat {g.get('beats', 1)}", "#d1d5db", 8, False))
        y += 14
        if t_ and t_.get("by") == g.get("by"):
            gw = max(60.0, min(240.0, width - 8))
            if kd == "choke" and t_.get("air") is not None:
                val, label, top = float(t_["air"]), f"air {t_['air']}% gone", 100.0
                lim = None
            else:
                val = float(t_.get("pain") or 0)
                top = max(1.0, float(t_.get("resist") or 1)) * 1.5
                lim = float(t_.get("resist") or 0)
                label = f"pain {round(val)} · what she can bear {round(lim)}"
            frac = min(1.0, val / top)
            past = lim is not None and val > lim
            out.append(("rect", tx, y, tx + gw, y + 9, "#1f2937", "#4b5563"))
            out.append(("rect", tx, y, tx + gw * frac, y + 9, "#ef4444" if past else "#f59e0b", ""))
            if lim is not None:
                lx = tx + gw * min(1.0, lim / top)
                out.append(("line", [(lx, y - 3), (lx, y + 12)], "#f9fafb", 2))
            out.append(("text", tx + 4, y - 1, label, "#f9fafb", 7, False))
            y += 14
            ch = float(t_.get("chance") or 0) * 100
            out.append(("text", tx, y, ("past what she can bear: " if past else "") + f"tap or black-out this beat "
                        f"{pct_text(ch)}", "#fca5a5" if ch >= 10 else "#d1d5db", 8, past))
            y += 16
        y += 2
    if pin:
        gw = max(60.0, min(240.0, width - 8))
        out.append(("text", tx, y, f"Pinned by {pin.get('by')}", "#fbbf24", 9, True))
        y += 15
        sec, of = float(pin.get("seconds") or 0), max(1.0, float(pin.get("of") or 60))
        out.append(("rect", tx, y, tx + gw, y + 9, "#1f2937", "#4b5563"))
        out.append(("rect", tx, y, tx + gw * min(1.0, sec / of), y + 9, "#f59e0b", ""))
        out.append(("text", tx + 4, y - 1, f"held {sec:.0f} of {of:.0f} s", "#f9fafb", 7, False))
        y += 16
    return out, max(h + 6, y - y0 + 4)


def shapes_svg(shapes, width, height):
    """(since build 304) A list of shapes (hold_shapes) as an SVG picture of its own, for exported fights."""
    import html as _h

    def P(pts):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    out = [f'<svg class="holds" viewBox="0 0 {width} {height:.0f}" width="100%" style="background:#111827;'
           f'border-radius:4px;max-width:620px;margin-top:2px">']
    for sh in shapes:
        if sh[0] == "poly":
            out.append(f'<polygon points="{P(sh[1])}" fill="{sh[2] or "none"}" stroke="{sh[3] or "none"}" '
                       f'stroke-width="{sh[4] or 1}"/>')
        elif sh[0] == "line":
            out.append(f'<polyline points="{P(sh[1])}" fill="none" stroke="{sh[2]}" stroke-width="{sh[3]}" '
                       f'stroke-linecap="round" stroke-linejoin="round"/>')
        elif sh[0] == "rect":
            out.append(f'<rect x="{sh[1]:.1f}" y="{sh[2]:.1f}" width="{max(0.0, sh[3] - sh[1]):.1f}" '
                       f'height="{sh[4] - sh[2]:.1f}" fill="{sh[5] or "none"}" stroke="{sh[6] or "none"}"/>')
        else:
            weight = ' font-weight="bold"' if sh[6] else ""
            out.append(f'<text x="{sh[1]:.1f}" y="{sh[2] + sh[5]:.1f}" fill="{sh[4]}" font-size="{sh[5] + 1}"{weight}>'
                       f'{_h.escape(sh[3])}</text>')
    out.append("</svg>")
    return "".join(out)


def blackout_text(v):
    """(since build 302) How close she is to blacking out in the coils, and to her heart stopping, in a line:
    (text, colour). Before her limit on the blood-flow gauge (out_at) she can't black out yet; past it, this beat's
    chances."""
    if v.get("stopped"):
        return "Blacked out, her heart stopped (it starts again once the coils come off)", "#ef4444"
    at, blood = v.get("out_at"), float(v.get("blood", 0) or 0)
    o, h = float(v.get("out_chance") or 0) * 100, float(v.get("stop_chance") or 0) * 100
    if v.get("heart_reserve") is not None:
        # (since build 313, constriction.heart) her heart is what takes her: how far it has worn down, and where it
        # stops, so it can be watched coming
        hr, stop = v.get("heart", 0), v.get("stop_at", 0)
        r = float(v["heart_reserve"])
        extra = f" · black-out from the blood alone {pct_text(o)}" if o > 0 else ""
        if v.get("would_stop"):
            return f"Her heart is nearly gone: {hr}/min, it stops at about {stop}/min{extra}", "#ef4444"
        if v.get("irregular"):
            return f"Her heart is failing: {hr}/min and uneven; it stops at about {stop}/min{extra}", "#f97316"
        if r < 0.75:
            return f"Her heart is slowing: {hr}/min; it stops at about {stop}/min{extra}", "#f59e0b"
        return f"Her heart is racing ({hr}/min) against the squeeze; it holds for now{extra}", "#d1d5db"
    if at is None:
        return "", "#d1d5db"
    if blood < at and o <= 0:
        return f"Black-out: not yet ({at - blood:.0f}% more cut off before she can)", "#d1d5db"
    col = "#ef4444" if o >= 25 else "#f97316" if o >= 10 else "#f59e0b"
    return f"Past her limit: black-out {pct_text(o)}, heart stopping {pct_text(h)} this beat", col


def squeeze_readout(v, x, y, width):
    """(since build 299; real-world numbers since build 300) The words and gauge beside the squeeze picture, as
    shapes for the window or an SVG: ("text", x, y, text, colour, size, bold), ("rect", x0, y0, x1, y1, fill,
    outline), ("line", x0, y0, x1, y1, colour, dashed). How tight it is (the narrator's word and %), what the coils
    press with against her blood pressure (a gauge from 0 to 200 mmHg, her pressure marked on it), her girth before and
    now, the coils and the coiler, and her heart."""
    where = v.get("where") if v.get("where") in ("chest", "belly", "both") else "chest"
    on_chest = where in ("chest", "both")
    out = [("text", x, y, f"{squeeze_word(v['squeeze']).capitalize()}: squeezed in {v['squeeze']}%", "#f9fafb", 9,
            True)]
    y += 18
    bp = v.get("bp") or [120, 80]
    p = v.get("pressure")
    if p is not None:
        past = p > bp[0]
        rest = v.get("bp_rest")
        out.append(("text", x, y, f"Coils press ~{p} mmHg · her BP {bp[0]}/{bp[1]}"
                    + (f" (normal {rest[0]}/{rest[1]})" if rest else ""), "#fca5a5" if past else "#f9fafb", 8, False))
        y += 14
        gw = max(60.0, min(220.0, width - 8))
        top = 200.0

        def gx(val):
            return x + gw * min(1.0, max(0.0, float(val)) / top)
        out.append(("rect", x, y, x + gw, y + 8, "#1f2937", "#4b5563"))
        out.append(("rect", x, y, gx(p), y + 8, "#dc2626" if past else "#f59e0b" if p > bp[1] else "#22c55e", ""))
        out.append(("line", gx(bp[1]), y - 2, gx(bp[1]), y + 10, "#9ca3af", True))
        out.append(("line", gx(bp[0]), y - 3, gx(bp[0]), y + 11, "#f9fafb", False))
        y += 12
        out.append(("text", x, y, "past her blood pressure: blood can't get back to her heart" if past else
                    "past her lowest pressure: little blood gets back" if p > bp[1] else
                    "under her blood pressure: blood still gets through", "#d1d5db", 7, False))
        y += 14
    g = v.get("girth")
    if g:
        out.append(("text", x, y, f"{'Chest' if where == 'chest' else 'Middle' if where == 'belly' else 'Chest and middle'}"
                    f" {g[1]} cm (normal {g[0]} cm, {g[0] - g[1]} cm squeezed out)", "#f9fafb", 8, False))
        y += 14
    place = {"chest": "round her chest", "belly": "round her middle", "both": "round her chest and middle"}[where]
    ratio = v.get("coil_ratio")
    out.append(("text", x, y, f"{v.get('coils', 1)} coil{'s' if int(v.get('coils') or 1) > 1 else ''} {place}"
                + (f", {v['coiler']} {ratio:g}× her size" if v.get("coiler") and ratio and ratio >= 1.5 else ""),
                "#d1d5db", 8, False))
    y += 14
    out.append(("text", x, y, "her heart has stopped" if v.get("stopped") else
                "her heart " + ("squeezed between the coils, " if on_chest and v["squeeze"] >= 35 else "")
                + ("slow and skipping" if v.get("irregular") else "racing"), "#fca5a5", 8, False))
    return out


SQUEEZE_WORDS = ((35, "snug"), (60, "tight"), (80, "crushing"), (101, "held almost flat"))


def squeeze_word(sq):
    """How the squeeze feels, in a word or two (the narrator's own steps)."""
    return next(word for top, word in SQUEEZE_WORDS if float(sq or 0) < top)


def squeeze_colours(v, body="#c08457", coil="#5d8fcf", belly=None):
    """The squeeze figure's colours: her body paling toward a cold grey-blue as her blood flow is cut off, the coils
    in their own colour with a lighter shine and a darker edge, her heart red (dull and dark once stopped)."""
    blood = float(v.get("blood", 0) or 0) / 100.0
    skin = mix(body, "#8a9bb0", 0.55 * blood)
    return {"body": skin, "body_edge": mix(skin, "#000000", 0.45), "rib": mix(skin, "#000000", 0.35),
            "arm": mix(skin, "#000000", 0.1), "shade": mix(skin, "#000000", 0.2),
            "belly": mix(mix(belly or body, "#8a9bb0", 0.55 * blood), "#ffffff", 0.0 if belly else 0.35), "crease": mix(skin, "#000000", 0.5), "coil": coil,
            "coil_edge": mix(coil, "#000000", 0.55), "coil_dark": mix(coil, "#000000", 0.28),
            "coil_shine": mix(coil, "#ffffff", 0.5),
            "heart": "#4b5563" if v.get("stopped") else mix("#ef4444", "#7f1d1d", 0.6 * blood)}


# (an irregular heart: the gaps between beats, as shares of her rate's own gap; a long one is a skipped beat)
IRREGULAR_GAPS = (1.0, 0.85, 1.25, 1.0, 1.9, 0.9, 1.1, 1.0, 1.6, 0.95)


def heart_beat(heart, t, irregular=False):
    """How far her heart is clenched at time t (seconds): 0 relaxed and full, 1 at the height of a beat (a quick
    squeeze, a slower easing back), at her own rate; the gaps uneven, now and then a beat missing, when it is
    irregular; 0 always once it has stopped."""
    if not heart or heart <= 0:
        return 0.0
    base = 60.0 / float(heart)
    gaps = IRREGULAR_GAPS if irregular else (1.0,)
    cycle = base * sum(gaps)
    x = t % cycle
    for g in gaps:
        if x < base * g:
            break
        x -= base * g
    ph = x / base                      # seconds since this beat, in beats
    if ph < 0.12:
        return ph / 0.12
    return max(0.0, math.exp(-(ph - 0.12) / 0.1))


def heart_shapes(cx, cy, r, squeeze=0.0, on_chest=False, blood=0.0, beat=0.0, stopped=False):
    """(since build 299) Her heart, drawn on its own: the heart (both sides, the great vessels on top), clenching on
    each beat (beat 0-1: heart_beat), smaller the less blood is getting back to fill it (blood: % cut off), and with
    the coils on her chest, flattened from the sides, the coils pressing in on it from both sides, closer the harder
    she is squeezed (squeeze 0-100). Returns {"heart": points, "split": the line between its sides, "vessels":
    [(points, width)], "press": [left, right] coil shapes or [], "shine": points}."""
    sq = max(0.0, min(100.0, float(squeeze or 0))) / 100.0 if on_chest else 0.0
    fill = 1.0 - 0.3 * max(0.0, min(100.0, float(blood or 0))) / 100.0
    clench = 0.0 if stopped else 0.24 * beat
    sx = fill * (1.0 - 0.32 * sq) * (1.0 - clench)
    sy = fill * (1.0 + 0.1 * sq) * (1.0 - 0.55 * clench)
    rr = r * 0.95
    heart = [(cx + (x - cx) * sx, cy + (y - cy) * sy + r * 0.12) for x, y in heart_points(cx, cy, rr)]
    split = [(cx + rr * 0.08 * sx, cy - rr * 0.45 * sy), (cx - rr * 0.08 * sx, cy + rr * 0.25 * sy),
             (cx + rr * 0.05 * sx, cy + rr * 0.85 * sy)]
    top = cy - rr * 0.55 * sy
    vessels = [([(cx - rr * 0.12 * sx, top), (cx - rr * 0.1 * sx, top - r * 0.42)], max(2.0, r * 0.26)),
               ([(cx + rr * 0.28 * sx, top + r * 0.02), (cx + rr * 0.34 * sx, top - r * 0.3)], max(1.5, r * 0.18))]
    shine = [(cx - rr * 0.6 * sx, cy - rr * 0.1 * sy), (cx - rr * 0.52 * sx, cy - rr * 0.38 * sy),
             (cx - rr * 0.32 * sx, cy - rr * 0.52 * sy)]
    press = []
    if sq > 0:
        # the coils round her chest, pressing in on it from both sides (the gap between them closing)
        gap = r * (1.25 - 0.45 * sq)
        for side in (-1, 1):
            xin, xout = cx + side * gap, cx + side * (gap + r * 0.5)
            # its inner face rounded where it presses on her, flat outside
            face = [(xin - side * r * 0.12 * math.cos(a), cy + r * 1.05 * math.sin(a))
                    for a in (math.pi * (k / 12 - 0.5) for k in range(13))]
            press.append(face + [(xout, cy + r * 1.05), (xout, cy - r * 1.05)])
    return {"heart": heart, "split": split, "vessels": vessels, "press": press, "shine": shine}


def squeeze_label(v):
    """The squeeze bar's few words: where and how far ("chest 52%", "belly 30%", "both 92%")."""
    return f"{(v.get('where') or 'body')} {v.get('squeeze', 0)}%"


def vitals_colour(blood):
    """The colour of the vitals strip from how much blood flow is cut off (%)."""
    return "#22c55e" if blood < 30 else "#f59e0b" if blood < 60 else "#ea580c" if blood < 80 else "#dc2626"


def held_parts(f):
    """Her parts in someone's grip right now (for the rings on her picture)."""
    g = f.get("grips") or {}
    return {p for x in g.get("held") or () for p in x.get("parts") or ()}


def tap_meter(f):
    """How near she is to tapping (from the engine's tap check this beat): {"level" 0-5 (the narrator's ladder),
    "chance" (this beat's tap chance, %), "label", "note"}, or None when she isn't in a submission's tap check."""
    t = (f.get("grips") or {}).get("tap")
    if not t:
        return None
    feel = max(0, min(5, int(t.get("level") or 0)))
    pct = 100.0 * float(t.get("chance") or 0)
    by_chance = str(t.get("meter_by", "chance")) == "chance"
    lv = chance_level(pct, t.get("chance_steps") or (3, 10, 25, 50)) if by_chance else feel
    notes = []
    if t.get("first"):
        notes.append("first beat in it: she can't tap yet" + ("" if t.get("sub") not in ("hold", "choke") else
                                                              ", but this hold counts toward one"))
    elif t.get("spent"):
        notes.append("this part's taps are used up: it can't make her tap")
    elif t.get("breaking"):
        notes.append({"first": "breaking point: holding out", "cracking": "breaking point: cracking",
                      "last": "breaking point: the last of it"}.get(t["breaking"], "breaking point"))
    elif t.get("held_on"):
        notes.append("past her limit for the first time: holding on through it")
    if t.get("toward") and not t.get("first") and not t.get("spent") and 100.0 * float(t["toward"]) >= pct + 3:
        # (since build 265) tap.blend's build-up: early in a hold the chance is far below what it is climbing to
        notes.append(f"still building: up to {100.0 * float(t['toward']):.0f}% as it stays on")
    if by_chance and feel >= 3 and lv < 3:
        # the pain is near or past what she can bear, but the chance this beat is still small
        notes.append("the pain is " + ("past what she can bear" if feel >= 4 else "near what she can bear"))
    if float(t.get("out") or 0) > 0:
        # (since build 283) the chance shown is of it ending this beat: a tap, or blacking out
        notes.append(f"tap {pct_text(100 * float(t.get('tap_only') or 0))}, blacking out "
                     f"{pct_text(100 * float(t['out']))}")
    if t.get("why_low") and pct < 10:
        # (since build 283) the pain can be far past what she bears while the chance stays tiny: say what holds it down
        notes.append("kept down by: " + ", ".join(f"{w} x{float(m):.2f}" for w, m in t["why_low"]))
    if t.get("refusals"):
        notes.append(f"refused {t['refusals']}x")
    vit = None
    v = t.get("vitals") or {}
    if t.get("circ") and v.get("heart") is not None:
        # (since build 287) the constriction's numbers are drawn (vitals_strip), not written into the line
        vit = dict(v, blood=int(t.get("air") or 0))
    elif t.get("air") is not None:
        notes.append(f"blood flow {t['air']}% cut off" if t.get("circ") else f"air {t['air']}% gone")
    if t.get("done"):
        return {"level": 5, "chance": 100.0, "label": str(t["done"]), "note": "", "vitals": vit, "pain": t.get("pain"),
                "resist": t.get("resist"), "by": t.get("by"), "sub": t.get("sub")}
    if by_chance:
        label = CHANCE_LADDER[lv] if not (t.get("first") or t.get("breaking") or t.get("held_on")) or lv else \
            "can't tap this beat"
        if (t.get("choke") or t.get("circ")) and lv >= 3:
            label = "fighting the dark"
    else:
        label = "fighting the dark" if (t.get("choke") or t.get("circ")) and lv >= 3 else TAP_LADDER[lv] \
            or "not fighting it yet"
    return {"level": lv, "chance": pct, "label": label, "note": " · ".join(notes), "vitals": vit,
            "pain": t.get("pain"), "resist": t.get("resist"), "by": t.get("by"), "sub": t.get("sub")}


def _with_words(ws):
    """What grips her, in short (since build 265): each grip's limb without how it works ("both paws, bending it up
    behind her back" -> "both paws"), "the same grip" left out, no limb twice: "both paws, her twin tails and her
    knee" rather than every grip's whole description strung together with "and"."""
    out = []
    for w in ws or ():
        for bit in re.split(r"\s+and\s+", str(w)):
            head = bit.split(",")[0].strip()
            key = re.sub(r"(?i)^(?:her|both|the)\s+", "", head).lower()
            if head and not re.match(r"(?i)(?:the same\b|\w+ing\b|it\b|then\b)", head) and key not in (
                    re.sub(r"(?i)^(?:her|both|the)\s+", "", x).lower() for x in out):
                out.append(head)
    return ", ".join(out[:-1]) + " and " + out[-1] if len(out) > 1 else "".join(out)


def grip_lines(f):
    """The hold panel's lines: [(text, colour)]: the grips on her, the grips she has, a pin, and the distance."""
    g = f.get("grips") or {}
    out = []
    for x in g.get("held") or ():
        parts = ", ".join(str(p).lower() for p in x.get("parts") or ())
        with_ = _with_words(x.get("with"))
        out.append((f"Held: {poss_word(x['by'])} {x['what']} on her {parts}" + (f" ({with_})" if with_ else "")
                    + f", beat {x.get('beats', 0)}" + ("  · on her throat" if x.get("choke") else "")
                    + (f"  · a grab: no tap until it is {x['tap_from'][0]}% hurt (now {x['tap_from'][1]}%)"
                       if x.get("tap_from") else ""), "#7c3aed"))
    for x in g.get("holding") or ():
        parts = ", ".join(str(p).lower() for p in x.get("parts") or ())
        with_ = _with_words(x.get("with"))
        t = x.get("tap")
        out.append((f"Holding: {x['what']} on {poss_word(x['on'])} {parts}" + (f" ({with_})" if with_ else "")
                    + f", beat {x.get('beats', 0)}"
                    + (f"  · {x['on']}: {_tap_words(t)}, {pct_text(t[1])} to tap"
                       if t else ""), "#1d4ed8"))
    p = g.get("pin")
    if p:
        out.append((f"Pinned by {' and '.join(p['by'])}: {p['seconds']} of {p['of']} seconds", "#b91c1c"))
    for x in g.get("pinning") or ():
        out.append((f"Pinning {x['on']}: {x['seconds']} of {x['of']} seconds", "#1d4ed8"))
    gaps = [f"{n}: {w}" for n, w in g.get("gaps") or () if w]
    if gaps:
        out.append(("Distance  " + "  ·  ".join(gaps), "#4b5563"))
    return out


# ---- window.alive (since build 306): her real picture brought to life, and a heart monitor on every card ----
ALIVE = {"enabled": True, "breathing": True, "pulse": True, "impact": True, "grey_in": True, "grip_outline": True,
         "heart_monitor": True, "fps": 12, "breath_depth": 0.012, "breath_min_px": 3, "breath_rest": 16, "heart_rest": 100,
         "exert": 0.45, "pain": 0.3, "heart_max": 1.8, "throb_from": 20, "throb": 0.6, "jolt_px": 7,
         "jolt_seconds": 0.45, "grey_from": 0.55, "vignette": 0.75}

# what her statuses do to her heart (a share of her resting rate, up or down), her breathing, and the monitor's words
STATUS_SIGNS = {"adrenaline": (0.25, 0.3, "adrenaline"), "breathless": (0.1, 0.6, "breathless"),
                "burned": (0.1, 0.1, "burned"), "poisoned": (0.12, 0.1, "poisoned"),
                "frozen": (-0.3, -0.5, "frozen"), "chilled": (-0.12, -0.2, "chilled"),
                "asleep": (-0.3, -0.4, "asleep"), "paralyzed": (0.05, 0.0, "paralyzed"),
                "stunned": (0.05, 0.0, "stunned"), "dazed": (0.0, 0.0, "dazed"), "concussed": (0.0, 0.0, "concussed"),
                "ribs_aching": (0.05, 0.0, "ribs aching"), "greyed": (0.0, 0.0, "the grey at her edges")}
# (since build 308, moves.reactions) fear and panic race her heart; a sick stomach or a raw throat shows in her breath
STATUS_SIGNS.update({"panicking": (0.3, 0.6, "panicking"), "shaken": (0.12, 0.15, "shaken"),
                     "angry": (0.15, 0.15, "angry"), "head_rush": (0.1, 0.2, "head rush"),
                     "nauseous": (0.08, 0.15, "nauseous"), "throat_raw": (0.05, 0.25, "throat raw"),
                     "overheated": (0.15, 0.4, "overheated"), "nosebleed": (0.0, 0.1, "nosebleed")})
# (since build 314, body.air) short of air, she breathes fast and her heart works harder
STATUS_SIGNS.update({"short_of_air": (0.12, 0.6, "short of air"), "starved_of_air": (0.25, 0.9, "starved of air")})
# (since build 318: body.blood, body.adrenaline, body.tissue)
STATUS_SIGNS.update({"bleeding": (0.08, 0.15, "bleeding"), "pale": (0.15, 0.2, "pale from blood loss"),
                     "light_headed": (0.22, 0.3, "light-headed"), "keyed_up": (0.3, 0.3, "keyed up"),
                     "adrenaline_crash": (-0.05, 0.1, "the adrenaline crash"), "swollen": (0.03, 0.0, "swelling"),
                     "broken_bone": (0.12, 0.15, "a broken bone")})
# (since build 319, body.footing)
STATUS_SIGNS.update({"unsteady": (0.04, 0.1, "unsteady on her feet")})
# (since build 321, body.mind) unnerved, her heart is quicker and her breath a little shallow
STATUS_SIGNS.update({"unnerved": (0.1, 0.15, "unnerved")})
# (since build 320, body.heat) heat makes her pant and her heart race; cold slows her breathing a little
STATUS_SIGNS.update({"flushed": (0.06, 0.35, "hot"), "heat_exhausted": (0.12, 0.6, "overheated"),
                     "shivering": (0.03, 0.05, "shivering"), "numbed": (0.0, 0.0, "chilled through")})
TORSO_WORDS = ("chest", "rib", "stomach", "belly", "flank", "torso")


def alive_opts(rules):
    """window.alive with its defaults."""
    o = dict(ALIVE)
    o.update(((rules or {}).get("window") or {}).get("alive") or {})
    return o


def body_signs(f, o=None, rest=None):
    """(since build 306) How she is, as her body would show it: her heart rate (from exertion, the pain she is in,
    her statuses, a choke, and the coils' own numbers while they are on her), a blood pressure to go with it, her
    breathing (how fast, how deep), how far the grey has closed in on her (0 to 1: a choke or the coils nearing her
    black-out), how hard her hurt parts throb with each beat, and the words for the monitor. Rough numbers for the
    picture, never rolled against."""
    o = o or ALIVE
    t = (f.get("grips") or {}).get("tap") or {}
    v = t.get("vitals") or None
    rest = float(rest or f.get("heart_rest") or o.get("heart_rest", 100))
    energy = max(0.0, min(100.0, float(f.get("energy", 100) or 0)))
    exert = 1.0 - energy / 100.0
    pct = float(((f.get("pain") or {}).get("overall") or {}).get("pct") or 0)
    pain = min(1.5, pct / 100.0)
    st = f.get("status") or {}
    hm, bm, words = 0.0, 0.0, []
    for k in st:
        h_, b_, w_ = STATUS_SIGNS.get(k, (0.0, 0.0, None))
        hm, bm = hm + h_, bm + b_
        if w_:
            words.append(w_)
    air = float(t.get("air") or 0) if (t.get("choke") and not t.get("circ")) else 0.0
    torso = max([d for p, d, r in f.get("parts") or () if any(w in p.lower() for w in TORSO_WORDS)] or [0])
    out = bool(f.get("out"))
    if v:
        heart, irregular, stopped = float(v.get("heart") or 0), bool(v.get("irregular")), bool(v.get("stopped"))
        bp = list(v.get("bp") or [120, 80])
    else:
        heart = rest * (1.0 + float(o.get("exert", 0.45)) * exert + float(o.get("pain", 0.3)) * pain + hm)
        tracked = (f.get("body") or {}).get("heart")
        if tracked is not None:
            # (since build 316, body.heart) the engine keeps her heart rate from beat to beat now: that is the one
            heart = float(tracked)
        if air:
            heart *= 1.0 + 0.3 * min(air, 60) / 60.0
            if air > 60:
                heart *= 1.0 - 0.45 * (air - 60) / 40.0
        heart = max(rest * 0.4, min(rest * float(o.get("heart_max", 1.85)), heart)) if tracked is None or tracked > 0 \
            else 0.0
        if out and not (tracked == 0):
            heart = rest * 0.75
        irregular, stopped = "paralyzed" in st or air > 70, False
        up = heart / rest - 1.0
        # (since build 318, body.blood) the blood she has lost brings her pressure down, whatever her heart does
        bl = float((f.get("body") or {}).get("blood", 100) or 100)
        bk = 0.55 + 0.45 * max(0.0, min(1.0, (bl - 40.0) / 60.0)) if bl < 100 else 1.0
        bp = [int(round(120 * (1 + 0.35 * up) * bk / 5) * 5), int(round(80 * (1 + 0.2 * up) * bk / 5) * 5)]
    br_rest = float(o.get("breath_rest", 16))
    breath = br_rest * (1.0 + 1.3 * exert + 0.4 * pain + bm)
    depth = 1.0 + 0.5 * exert
    shallow = []
    if torso >= 150 or "ribs_aching" in st:
        depth *= 0.65
        shallow.append("guarding her ribs")
    grey = 0.0
    if v:
        s = max(0.0, min(1.0, float(v.get("squeeze") or 0) / 100.0))
        depth *= 1.0 - 0.85 * s
        breath *= 1.0 + 0.5 * s
        if s > 0.2:
            shallow.append("the coils let her breathe only shallowly")
        at, blood = float(v.get("out_at") or 0), float(v.get("blood") or 0)
        if at:
            near = blood / at
            gf = float(o.get("grey_from", 0.55))
            grey = max(0.0, min(1.0, (near - gf) / max(0.05, 1.0 - gf)))
            if near > 0.8:
                breath *= max(0.4, 1.0 - (near - 0.8))
    if air:
        depth *= max(0.05, 1.0 - air / 100.0)
        breath *= 1.3
        shallow.append("no air getting in")
        grey = max(grey, max(0.0, min(1.0, (air - 45) / 45.0)))
    if "greyed" in st:
        grey = max(grey, 0.35)
    if stopped:
        heart, breath, depth, grey = 0.0, 0.0, 0.0, 1.0
    elif out:
        breath, depth = br_rest * 0.6, 0.45
    breath = max(0.0, min(70.0, breath))
    if energy < 60 and not out:
        words.insert(0, "breathing hard" if energy >= 35 else "winded" if energy >= 15 else "spent")
    words += shallow
    if pct >= 40 and not out:
        words.append(str(((f.get("pain") or {}).get("overall") or {}).get("label") or "in pain"))
    if out:
        words.insert(0, "heart stopped" if stopped else "unconscious")
    ratio = heart / rest if rest else 1.0
    colour = ("#ef4444" if stopped or ratio >= 1.55 or grey >= 0.5 or (irregular and ratio < 0.8) else
              "#f59e0b" if ratio >= 1.3 or irregular or grey > 0 else "#22c55e")
    tf = float(o.get("throb_from", 20))
    return {"heart": int(round(heart / 2.0) * 2), "heart_rest": int(round(rest)), "irregular": irregular,
            "stopped": stopped, "bp": bp, "bp_rest": [120, 80], "breath": int(round(breath)),
            "breath_rest": int(br_rest), "depth": round(max(0.0, depth), 3), "grey": round(grey, 3),
            "throb": round(max(0.0, min(1.0, (pct - tf) / max(1.0, 100.0 - tf))), 3),
            "words": list(dict.fromkeys(words)), "colour": colour, "coiled": bool(v),
            "air": ((f.get("body") or {}).get("air")),
            "temp": (round(38.5 + float((f.get("body") or {}).get("heat")), 1)
                     if (f.get("body") or {}).get("heat") is not None else None)}


def breath_phase(rate, t):
    """How full her chest is at time t (seconds): 0 breathed out, 1 breathed in, at `rate` breaths a minute (a
    quicker breath in than out)."""
    if not rate or rate <= 0:
        return 0.0
    x = (t * rate / 60.0) % 1.0
    return math.sin(math.pi / 2 * x / 0.4) ** 2 if x < 0.4 else math.cos(math.pi * (x - 0.4) / 0.6 / 2) ** 2


def impacts(prev, f):
    """(since build 306) What landed on her since the card last showed her, a beat before: [(part, strength 0-1)],
    the hardest first, from how much each part's damage rose; and the whole jolt (0-1), the hardest hit or the health
    she lost, whichever is more."""
    if not prev:
        return [], 0.0
    before = {p: d for p, d, r in prev.get("parts") or ()}
    hits = sorted(((p, min(1.0, (d - before.get(p, d)) / 60.0)) for p, d, r in f.get("parts") or ()
                   if d - before.get(p, d) >= 2), key=lambda x: -x[1])
    lost = max(0.0, float(prev.get("health", 0)) - float(f.get("health", 0))) / max(1.0, float(f.get("max", 100)) * 0.12)
    return hits, round(min(1.0, max([s for p, s in hits] + [lost])), 3) if hits or lost > 0.05 else 0.0


def breathe_image(img, box, amount):
    """Her picture breathing in: stretched up from her feet (the bottom of her body, box) by `amount` of her
    height, and a hair wider, so her chest rises and falls; the picture's own size is kept."""
    if not amount or img is None:
        return img
    x0, y0, x1, y1 = box
    h = max(1, y1 - y0)
    nh = int(round(h * (1.0 + amount)))
    nw = int(round((x1 - x0) * (1.0 + amount * 0.35)))
    body = img.crop((x0, y0, x1, y1)).resize((max(1, nw), max(1, nh)), Image.BILINEAR)
    out = img.copy()
    out.paste((0, 0, 0, 0), (x0, y0, x1, y1))
    out.alpha_composite(body, (max(0, x0 - (nw - (x1 - x0)) // 2), max(0, y1 - nh)))
    return out


def grey_image(img, k, vignette=0.75):
    """The grey closing in on her (k 0-1): her picture losing its colour and dimming, and (vignette) a dark edge
    closing in round the picture."""
    if not k or img is None:
        return img
    k = max(0.0, min(1.0, k))
    a = img.getchannel("A")
    rgb = ImageEnhance.Color(img.convert("RGB")).enhance(1.0 - 0.8 * k)
    rgb = ImageEnhance.Brightness(rgb).enhance(1.0 - 0.15 * k)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    if vignette:
        w, h = img.size
        m = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(m)
        r = (1.05 - 0.35 * k) * min(w, h) / 2
        d.ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), fill=255)
        m = m.filter(ImageFilter.GaussianBlur(min(w, h) / 9))
        dark = Image.new("RGBA", (w, h), (8, 8, 12, 0))
        dark.putalpha(ImageChops.invert(m).point(lambda x: int(x * 0.7 * float(vignette) * k)))
        out.alpha_composite(dark)
    return out


def flash_layer(src, spots, hits, colour=(255, 214, 190)):
    """A blow's flash on the parts it struck: a bright bloom on each, as strong as the hit, kept on her body."""
    layer = Image.new("RGBA", src.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for part, s in hits:
        if part not in spots:
            continue
        x, y = spots[part]
        r = (14 + 14 * s) * src.size[0] / PIC
        dr.ellipse((x - r, y - r, x + r, y + r), fill=colour + (int(70 + 110 * s),))
    layer = layer.filter(ImageFilter.GaussianBlur(7))
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), _body_mask(src)))
    return layer


def throb_layer(src, f, spots):
    """The extra glow her hurt parts pulse with at each heartbeat (window.alive.pulse), kept on her body."""
    layer = _glow_layer(src, f, spots, 150)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), _body_mask(src)))
    return layer


def monitor_words(sg):
    """The heart monitor's reading on the card: [(text, colour, bold)]."""
    out = [("♥ stopped" if sg["stopped"] else f"♥ {sg['heart']}/min", sg["colour"], True),
           (f"normal {sg['heart_rest']}", "#9ca3af", False),
           (f"BP {sg['bp'][0]}/{sg['bp'][1]}", "#f9fafb" if sg["bp"][0] >= 90 else "#fca5a5", True),
           (f"normal {sg['bp_rest'][0]}/{sg['bp_rest'][1]}", "#9ca3af", False),
           (f"breathing {sg['breath']}/min" + (", shallow" if sg["depth"] < 0.6 and sg["breath"] else ""),
            "#f9fafb", True), (f"normal {sg['breath_rest']}" + (f" · air {sg['air']}%" if sg.get("air") is not None
                                                                and sg["air"] < 95 else ""),
                               "#fca5a5" if (sg.get("air") or 100) < 35 else "#9ca3af", False)]
    return out
