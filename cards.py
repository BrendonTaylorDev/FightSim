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
    from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont
except Exception:              # pragma: no cover
    Image = ImageDraw = ImageFilter = ImageChops = ImageFont = None

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
    except Exception:
        pass


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


def prepare_picture(data):
    """(src, rect, box) for a picture: the picture fitted into a PIC x PIC square (RGBA), where it sits
    (x, y, w, h), and where the body is inside it (x0, y0, x1, y1). Needs Pillow; (None, ...) without it."""
    if Image is None or not data:
        return None, (4, 4, PIC - 8, PIC - 8), None
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    im.thumbnail((PIC - 8, PIC - 8))
    canvas = Image.new("RGBA", (PIC, PIC), (0, 0, 0, 0))
    x, y = (PIC - im.width) // 2, (PIC - im.height) // 2
    canvas.paste(im, (x, y), im)
    box = canvas.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox() or (0, 0, PIC, PIC)
    return canvas, (x, y, im.width, im.height), box


def _onto_body(alpha, x, y):
    """The nearest point of the body itself (not the empty background) to (x, y)."""
    px = alpha.load()
    xi, yi = int(min(PIC - 1, max(0, x))), int(min(PIC - 1, max(0, y)))
    if px[xi, yi] > 40:
        return x, y
    for r in range(3, 90, 3):
        for k in range(16):
            a = 2 * math.pi * k / 16
            xx, yy = int(xi + r * math.cos(a)), int(yi + r * math.sin(a))
            if 0 <= xx < PIC and 0 <= yy < PIC and px[xx, yy] > 40:
                return xx, yy
    return x, y


def point_key(f, own):
    return (f["name"] if own else f["species"] or f["name"]).lower()


def anchor_points(f, src=None, rect=(4, 4, PIC - 8, PIC - 8), box=None, own=False, has_picture=False):
    """Where each part is on the picture (picture pixels): your own placements (images/anchors.json) first, then
    the built-in ones for this species' artwork, else a guess from where that part sits on a body, fitted to the
    picture's outline."""
    key = point_key(f, own)
    book = dict({} if own or not has_picture else ARTWORK_POINTS.get(key, {}))
    book.update(load_anchors().get(key, {}))
    rx, ry, rw, rh = rect
    x0, y0, x1, y1 = box or (40, 20, PIC - 40, PIC - 20)
    alpha = src.getchannel("A") if src is not None and Image is not None and hasattr(src, "getchannel") else None
    out, groups = {}, {}
    for part, dmg, res in f["parts"]:
        if part in book:
            out[part] = (rx + book[part][0] * rw, ry + book[part][1] * rh)
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
    layer = Image.new("RGBA", (PIC, PIC), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for part, dmg, res in sorted(f["parts"], key=lambda t: t[1]):
        col = glow_color(dmg)
        if not col or part not in spots:
            continue
        x, y = spots[part]
        r = 16 + min(16, dmg / 25)
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


def columns(f, spots, rect):
    """The parts split into the label column on each side of the picture (each on the side its point is on,
    evened up from the middle), each column top to bottom."""
    cx = rect[0] + rect[2] / 2
    left = [t for t in f["parts"] if spots[t[0]][0] < cx]
    right = [t for t in f["parts"] if spots[t[0]][0] >= cx]
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


def render_card(f, data=None, own=False):
    """The whole card as one image (Pillow): name, the picture with each hurt part glowing, a line from every
    part to its label (damage on its colour, resistance in its colour's frame), and health and energy bars."""
    if Image is None:
        return None
    src, rect, box = prepare_picture(data) if data else (None, (4, 4, PIC - 8, PIC - 8), None)
    spots = anchor_points(f, src, rect, box, own, has_picture=src is not None)
    left, right = columns(f, spots, rect)
    H = max(PIC, ROW * max(len(left), len(right)) + 12)
    W = PIC + 2 * COL
    head, foot = 30, 40
    img = Image.new("RGB", (W, head + H + foot), "#ffffff")
    d = ImageDraw.Draw(img)
    big, small, tiny, tinyb = _font(16, True), _font(11), _font(10), _font(10, True)
    d.text((6, 6), f["name"] + ("   — OUT" if f.get("out") else ""), fill="#111827", font=big)
    d.text((W - 6, 9), f"{f.get('species', '')}  ·  {' / '.join(f.get('types') or [])}", fill="#6b7280", font=small,
           anchor="ra")
    top = head + (H - PIC) / 2
    pic = glow_image(src, f, spots)
    if pic is not None:
        img.paste(pic, (COL, int(top)), pic)
    else:
        d.ellipse((COL + 50, top + 50, COL + PIC - 50, top + PIC - 50), fill="#e5e7eb")
        d.text((COL + PIC / 2, top + PIC / 2), (f.get("species") or f["name"])[:12], fill="#6b7280", font=big,
               anchor="mm")
    for side, rows in (("L", left), ("R", right)):
        ys = spread([top + spots[p[0]][1] for p in rows], head + H)
        for (part, dmg, res), ly in zip(rows, ys):
            x, y = spots[part]
            ax, ay = COL + x, top + y
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
    pct = 100.0 * f["health"] / max(1e-9, f["max"])
    yb = head + H + 6
    col = "#22c55e" if pct >= 60 else "#eab308" if pct >= 35 else "#f97316" if pct >= 15 else "#ef4444"
    d.rectangle((0, yb, W, yb + 16), fill="#e5e7eb")
    d.rectangle((0, yb, W * max(0.0, min(1.0, pct / 100.0)), yb + 16), fill=col)
    d.text((6, yb + 8), f"Health {f['health']:.0f}%  ({pct:.0f}% of full)", fill="#111827", font=tinyb, anchor="lm")
    d.rectangle((0, yb + 19, W, yb + 28), fill="#e5e7eb")
    d.rectangle((0, yb + 19, W * max(0.0, min(1.0, f.get("energy", 0) / 100.0)), yb + 28), fill="#60a5fa")
    d.text((6, yb + 23), f"energy {f.get('energy', 0):.0f}", fill="#111827", font=tiny, anchor="lm")
    return img
