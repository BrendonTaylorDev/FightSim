"""Fighter pictures and their body-part markings, shared by the window (window.py) and the fight export
(/exportfight): which picture, where each part sits on it, the damage glow, and a finished card image.

Needs Pillow for the glow and the exported card images; without it the window still works (plainer), and the export
falls back to tables."""
import io
import json
import math
import os
import re
import urllib.request

from engine import body_region

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
DMG_STEPS = [(300, "#1f2937", "devastated (300%+)"), (150, "#a855f7", "excruciating (150%+)"),
             (90, "#ef4444", "very painful (90%+)"), (60, "#f97316", "hurting (60%+)"), (30, "#eab308", "sore (30%+)"),
             (-1e9, "#22c55e", "minor")]
GLOW = {"sore": "#facc15", "hurting": "#fb923c", "very": "#ef4444", "excruciating": "#a855f7",
        "devastated": "#7f1d1d"}

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
    return w


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

    def pick(self, view, state):
        """(bytes, own, key, fallback keys, builtin points, own_state): her picture for this state if you have one,
        else the view's own picture (own_state False: the window gives it the weakened look itself)."""
        base = self.base(view)
        if base is None:
            return None
        for st in STATE_TRY.get(state or "", ()):
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
                return hit[0], hit[1], hit[2], [base[2]], base[3] if not hit[1] else {}, True
        return base[0], base[1], base[2], [], base[3], False


def weak_look(im, state):
    """Her picture made to look the way she is when there is no picture of it: a little faded when worn; faded,
    dimmer and slumped when badly hurt; on her side when down or out. Returns (image, xf): xf moves a point given as
    fractions of the old picture to fractions of the new one."""
    if Image is None or im is None or not state:
        return im, None
    fade, dim, angle = {"worn": (0.8, 0.96, 0), "hurt": (0.55, 0.85, -7), "down": (0.65, 0.88, 90),
                        "out": (1.0, 1.0, 90)}.get(state, (1, 1, 0))
    a = im.getchannel("A")
    rgb = im.convert("RGB")
    if fade != 1:
        rgb = ImageEnhance.Color(rgb).enhance(fade)
    if dim != 1:
        rgb = ImageEnhance.Brightness(rgb).enhance(dim)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    if not angle:
        return out, None
    w, h = out.size
    if angle == 90 and h < w * 1.1:
        angle = -16          # already lying along the picture: turned on end it would look less down, so it tips over
    rot = out.rotate(angle, expand=True, resample=Image.BICUBIC)
    W, H = rot.size
    t = math.radians(angle)

    def xf(fx, fy):
        dx, dy = fx * w - w / 2, fy * h - h / 2
        return ((W / 2 + dx * math.cos(t) + dy * math.sin(t)) / W, (H / 2 - dx * math.sin(t) + dy * math.cos(t)) / H)
    return rot, xf


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
    return (GLOW["devastated"] if dmg >= 300 else GLOW["excruciating"] if dmg >= 150 else GLOW["very"] if dmg >= 90
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
    look: a state for weak_look; then a fourth item, xf, moves points to where they are on the changed picture."""
    if Image is None or not data:
        return (None, (4, 4, size - 8, size - 8), None) + ((None,) if look is not None else ())
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    xf = None
    if look:
        im, xf = weak_look(im, look)
    small = im.width < (size - 8) / 2 and im.height < (size - 8) / 2
    if small:       # a small sprite: grown in whole steps, kept crisp
        k = max(1, int((size - 8) // max(im.width, im.height)))
        im = im.resize((im.width * k, im.height * k), Image.NEAREST)
    im.thumbnail((size - 8, size - 8))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x, y = (size - im.width) // 2, (size - im.height) // 2
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


def glow_image(src, f, spots):
    """The picture with each hurt part glowing in its damage colour, kept on the body; greyed out if she is out."""
    if Image is None or src is None:
        return None
    layer = Image.new("RGBA", src.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for part, dmg, res in sorted(f["parts"], key=lambda t: t[1]):
        col = glow_color(dmg)
        if not col or part not in spots:
            continue
        x, y = spots[part]
        r = (16 + min(16, dmg / 25)) * src.size[0] / PIC
        rgb = tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))
        dr.ellipse((x - r, y - r, x + r, y + r), fill=rgb + (190,))
    layer = layer.filter(ImageFilter.GaussianBlur(9))
    body = src.getchannel("A").point(lambda a: 255 if a > 40 else 0).filter(ImageFilter.GaussianBlur(2))
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), body))
    out = src.copy()
    out.alpha_composite(layer)
    if f.get("out"):
        grey = out.convert("LA").convert("RGBA")
        grey.putalpha(out.getchannel("A"))
        out = grey
    return out


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
    spots, parts, left, right (the label columns), key (where clicks store points), height, state, look.
    plain: no weakened look (while you place a point by hand). cache: a dict to keep prepared pictures in."""
    o = opts or opts_of(None)
    state = None if plain or not o.get("weak_look", True) else health_state(f, o)
    views = ["front"] + (["back"] if o.get("back_view", True) and Image is not None else [])
    picked = {v: book.pick(v, state) if book is not None else None for v in views}
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
        look = state if (state and got and not got[5]) else None
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
        out.append({"view": v, "size": size, "src": src, "pic": glow_image(src, f, spots) if src is not None else None,
                    "rect": rect, "spots": spots, "parts": parts, "left": left, "right": right, "key": key,
                    "height": H, "state": state, "look": look})
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
