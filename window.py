"""FightSim in its own window: the same game as play.py, with a picture of each fighter.

    python window.py            (takes the same options as play.py: --model, --fighters, --scene, --no-llm ...)
    In Spyder:  %runfile window.py

On the left, every fighter: her picture with each body part marked on it (the fill is how hurt the part is, the
border how tough it still is: the same colours as the stat lines), her overall health, energy, statuses and
posture, and a table of every part. On the right, the story and the stat lines exactly as the console shows them,
with the command box underneath (type a direction, a /command, or just press Enter for the next beat).

Scroll back through the story and the pictures follow: they show each fighter as she was at the end of the beat
you are reading. The slider at the top does the same; "Follow the fight" snaps back to the newest beat.

Pictures: put your own in the images folder as <fighter name>.png (Ripples.png) or <species>.png (buizel.png).
Otherwise the official artwork is fetched once from PokeAPI and kept there; with no internet, a plain badge is
drawn instead."""
import builtins
import io
import json
import math
import os
import queue
import re
import sys
import threading
import urllib.request

import tkinter as tk
from tkinter import ttk

import play
from engine import species_of, body_region

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, "images")
PIC = 300                      # picture box size (pixels)

try:                           # Pillow makes the pictures smoother when it is installed; Tk alone works too
    from PIL import Image, ImageTk
except Exception:              # pragma: no cover
    Image = ImageTk = None

# the console's own colour steps (display.py legend)
RES_STEPS = [(100.0001, "#3b82f6", "tough (over 100%)"), (70, "#22c55e", "70-100%"), (50, "#eab308", "50-70%"),
             (30, "#f97316", "30-50%"), (-1e9, "#ef4444", "under 30%")]
DMG_STEPS = [(300, "#1f2937", "devastated (300%+)"), (150, "#a855f7", "excruciating (150%+)"),
             (90, "#ef4444", "very painful (90%+)"), (60, "#f97316", "hurting (60%+)"), (30, "#eab308", "sore (30%+)"),
             (-1e9, "#22c55e", "minor")]


def res_color(v):
    return next(c for at, c, _ in RES_STEPS if v >= at)


def dmg_color(v):
    return next(c for at, c, _ in DMG_STEPS if v >= at)


def text_on(bg):
    """Black or white text, whichever reads on this fill."""
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"


# where each body region sits on the picture (fractions of the box); left/right parts go to either side
SPOTS = {"head": (0.5, 0.07), "neck": (0.5, 0.2), "shoulder": (0.5, 0.31), "chest": (0.5, 0.42),
         "back_up": (0.5, 0.31), "fore_up": (0.5, 0.45), "fore_low": (0.5, 0.62), "belly": (0.5, 0.57),
         "back_low": (0.5, 0.69), "hind_up": (0.5, 0.77), "hind_low": (0.5, 0.9), "tail": (0.5, 0.97),
         "other": (0.5, 0.5)}
SPREAD = {"shoulder": 0.3, "fore_up": 0.36, "fore_low": 0.38, "hind_up": 0.3, "hind_low": 0.32, "head": 0.3,
          "chest": 0.25, "belly": 0.28, "back_up": 0.28, "neck": 0.2, "tail": 0.25, "back_low": 0.28, "other": 0.3}


def short(part):
    s = part.replace("Left ", "L ").replace("Right ", "R ").replace("Upper ", "Up ").replace("Lower ", "Lo ")
    return s if len(s) <= 14 else s[:13] + "…"


def snapshot(s, label=None):
    """Everything the window shows about the fight right now (plain data: it is passed between threads)."""
    eng = s.eng
    out = []
    for f in eng.fighters.values():
        down = f.name in eng.downed
        try:
            pinned_by, pinning = eng.pinned_by(f.name), eng.pinning(f.name)
        except Exception:
            pinned_by, pinning = [], []
        try:
            facing = eng.facing_of(f.name) if down else ""
        except Exception:
            facing = ""
        posture = ("OUT" if f.eliminated else "in the air" if eng.has(f, "airborne") else
                   f"pinned by {', '.join(pinned_by)}" if pinned_by else f"pinning {', '.join(pinning)}" if pinning else
                   f"down ({facing})" if down else "on her feet")
        out.append({
            "name": f.name, "species": species_of(f.description, f.appearance), "types": list(f.types or []),
            "health": float(f.health), "max": float(f.max_health or 1), "energy": float(f.energy),
            "status": {k: v for k, v in (f.status or {}).items()}, "out": bool(f.eliminated), "posture": posture,
            "parts": [(p.name, float(p.damage), float(p.resistance)) for p in f.parts.values()],
        })
    return {"turn": int(getattr(eng, "turn", 0) or 0), "fighters": out,
            "label": label or f"after beat {getattr(eng, 'turn', 0)}"}


class GameThread(threading.Thread):
    """Runs the ordinary game loop (play._run) with its screen and keyboard pointed at the window."""

    def __init__(self, args, out_q, in_q):
        super().__init__(daemon=True)
        self.args, self.out_q, self.in_q = args, out_q, in_q
        self.session = None

    def run(self):
        out_q, in_q = self.out_q, self.in_q

        class Screen:
            encoding = "utf-8"

            def write(self, t):
                if t:
                    out_q.put(("text", str(t)))
                return len(t or "")

            def flush(self):
                pass

            def isatty(self):
                return False

        def ask(prompt=""):
            if self.session is not None:
                out_q.put(("live", snapshot(self.session, "now")))
            out_q.put(("prompt", str(prompt)))
            line = in_q.get()
            if line is None:
                raise EOFError
            out_q.put(("text", f"{prompt}{line}\n"))
            return line

        real_out, real_in = sys.stdout, builtins.input
        sys.stdout, builtins.input = Screen(), ask
        orig_beat = play.Session.play_beat

        def play_beat(sess, *a, **k):
            try:
                return orig_beat(sess, *a, **k)
            finally:
                out_q.put(("beat", snapshot(sess)))
        play.Session.play_beat = play_beat
        try:
            self.session = play.Session(self.args)
            out_q.put(("live", snapshot(self.session, "now")))
            play._run(self.session, self.args)
        except EOFError:
            pass
        except Exception as e:      # shown in the window rather than lost
            import traceback
            out_q.put(("text", "\n" + traceback.format_exc() + f"\n[the game stopped: {e}]\n"))
        finally:
            play.Session.play_beat = orig_beat
            sys.stdout, builtins.input = real_out, real_in
            out_q.put(("done", None))


# National Pokédex numbers for the roster's species (the artwork is fetched by number; PokeAPI is only asked about
# a species missing here)
DEX = {"absol": 359, "arbok": 24, "arcanine": 59, "articuno": 144, "braviary": 628, "buizel": 418, "charizard": 6,
       "dragonite": 149, "fennekin": 653, "floatzel": 419, "goodra": 706, "lucario": 448, "lycanroc": 745,
       "milotic": 350, "moltres": 146, "ninetales": 38, "pidgeot": 18, "staraptor": 398, "swanna": 581,
       "swellow": 277, "talonflame": 663, "thievul": 828, "unfezant": 521, "vulpix": 37}


def fetch_picture(name, species, done):
    """Bytes of a picture for this fighter (her own file, her species' file, or PokeAPI's artwork, saved to
    images/ for next time), handed to done(bytes or None) on a worker thread."""
    def work():
        os.makedirs(IMG_DIR, exist_ok=True)
        for base in (name, species, species.lower()):
            for ext in (".png", ".gif"):
                path = os.path.join(IMG_DIR, base + ext)
                if base and os.path.exists(path):
                    with open(path, "rb") as fh:
                        return done(fh.read(), base == name)
        key = re.sub(r"[^a-z0-9-]", "", species.lower().replace(" ", "-"))
        if not key:
            return done(None, False)
        try:
            pid = DEX.get(key)
            if pid is None:
                req = urllib.request.Request(f"https://pokeapi.co/api/v2/pokemon-species/{key}/",
                                             headers={"User-Agent": "FightSim"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    pid = json.load(r)["id"]
            url = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/"
                   f"official-artwork/{pid}.png")
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "FightSim"}),
                                        timeout=20) as r:
                data = r.read()
            with open(os.path.join(IMG_DIR, species.lower() + ".png"), "wb") as fh:
                fh.write(data)
            done(data, False)
        except Exception:
            done(None, False)
    threading.Thread(target=work, daemon=True).start()


class Tip:
    """A small hover label."""

    def __init__(self, root):
        self.win = None
        self.root = root

    def show(self, x, y, text):
        self.hide()
        self.win = tk.Toplevel(self.root)
        self.win.wm_overrideredirect(True)
        self.win.wm_geometry(f"+{x + 14}+{y + 10}")
        tk.Label(self.win, text=text, justify="left", bg="#111827", fg="#f9fafb", padx=6, pady=4,
                 font=("Segoe UI", 9)).pack()

    def hide(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None


ANCHORS = os.path.join(IMG_DIR, "anchors.json")
COL, ROW = 158, 17             # label column width, label row height
GLOW = {"sore": "#facc15", "hurting": "#fb923c", "very": "#ef4444", "excruciating": "#a855f7",
        "devastated": "#7f1d1d"}


# where each part is on the official artwork (fractions of the picture), for the species played most; any other
# species is placed by a guess until you place its points yourself (click a label, then the picture)
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


def glow_color(dmg):
    """The colour a part glows on the picture: none while it is minor."""
    return (GLOW["devastated"] if dmg >= 300 else GLOW["excruciating"] if dmg >= 150 else GLOW["very"] if dmg >= 90
            else GLOW["hurting"] if dmg >= 60 else GLOW["sore"] if dmg >= 30 else None)


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


class FighterCard(ttk.Frame):
    """One fighter: her picture in the middle, every body part marked on it and glowing in its damage colour, with a
    line out to a label on either side (damage on the coloured fill, resistance in the coloured frame)."""

    def __init__(self, master, app, name):
        super().__init__(master, padding=6, relief="groove")
        self.app, self.name = app, name
        self.src = None          # the picture (Pillow image, scaled to fit), or a Tk photo without Pillow
        self.photo = None
        self.box = None          # where the body is in the picture: (x0, y0, x1, y1)
        self.rect = (4, 4, PIC - 8, PIC - 8)   # where the picture itself sits: (x, y, width, height)
        self.own = False         # your own picture (images/<name>.png): the built-in points don't fit it
        self.data = None
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.head = ttk.Label(top, font=("Segoe UI", 12, "bold"))
        self.head.pack(side="left")
        self.sub = ttk.Label(top, foreground="#6b7280")
        self.sub.pack(side="left", padx=8)
        self.canvas = tk.Canvas(self, width=PIC + 2 * COL, height=PIC, bg="#ffffff", highlightthickness=0)
        self.canvas.pack(pady=(4, 4))
        self.canvas.bind("<Button-1>", self.clicked)
        self.hp = tk.Canvas(self, width=PIC + 2 * COL, height=18, highlightthickness=0, bg="#e5e7eb")
        self.hp.pack(fill="x")
        self.en = tk.Canvas(self, width=PIC + 2 * COL, height=10, highlightthickness=0, bg="#e5e7eb")
        self.en.pack(fill="x", pady=(2, 0))
        self.state = ttk.Label(self, wraplength=PIC + 2 * COL, justify="left")
        self.state.pack(anchor="w", pady=(4, 0))

    # ---- the picture ----
    def set_picture(self, data):
        try:
            if Image is not None:
                im = Image.open(io.BytesIO(data)).convert("RGBA")
                im.thumbnail((PIC - 8, PIC - 8))
                canvas = Image.new("RGBA", (PIC, PIC), (0, 0, 0, 0))
                canvas.paste(im, ((PIC - im.width) // 2, (PIC - im.height) // 2), im)
                self.rect = ((PIC - im.width) // 2, (PIC - im.height) // 2, im.width, im.height)
                self.src = canvas
                self.box = canvas.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox() or (0, 0, PIC, PIC)
            else:
                import base64
                photo = tk.PhotoImage(data=base64.b64encode(data))
                k = max(1, math.ceil(max(photo.width(), photo.height()) / (PIC - 8)))
                self.src = photo.subsample(k, k) if k > 1 else photo
                w, h = self.src.width(), self.src.height()
                self.box = ((PIC - w) // 2, (PIC - h) // 2, (PIC + w) // 2, (PIC + h) // 2)
                self.rect = ((PIC - w) // 2, (PIC - h) // 2, w, h)
        except Exception:
            self.src = None
        if self.data:
            self.draw(self.data)

    def anchors(self, f):
        """Where each part is on the picture (picture pixels): your own placements (images/anchors.json) first, else
        a guess from where that part sits on a body, fitted to the picture's outline."""
        key = (f["name"] if self.own else f["species"] or f["name"]).lower()
        book = dict({} if self.own or self.src is None else ARTWORK_POINTS.get(key, {}))
        book.update(load_anchors().get(key, {}))
        rx, ry, rw, rh = self.rect
        x0, y0, x1, y1 = self.box or (40, 20, PIC - 40, PIC - 20)
        alpha = self.src.getchannel("A") if (Image is not None and self.src is not None
                                             and not isinstance(self.src, tk.PhotoImage)) else None
        out = {}
        groups = {}
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
                    x, y = self._onto_body(alpha, x, y)
                out[part] = (x, y)
        return out

    @staticmethod
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

    def glowing(self, f, spots):
        """The picture with each hurt part glowing in its damage colour, kept on the body (Pillow), else None."""
        if Image is None or self.src is None or isinstance(self.src, tk.PhotoImage):
            return None
        from PIL import ImageDraw, ImageFilter, ImageChops
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
        body = self.src.getchannel("A").point(lambda a: 255 if a > 40 else 0).filter(ImageFilter.GaussianBlur(2))
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), body))
        out = self.src.copy()
        out.alpha_composite(layer)
        if f["out"]:
            grey = out.convert("LA").convert("RGBA")
            grey.putalpha(out.getchannel("A"))
            out = grey
        return ImageTk.PhotoImage(out)

    # ---- drawing ----
    def draw(self, f):
        self.data = f
        pct = 100.0 * f["health"] / f["max"]
        self.head.configure(text=f["name"] + ("   — OUT" if f["out"] else ""))
        self.sub.configure(text=f"{f['species']}  ·  {' / '.join(f['types'])}")
        spots = self.anchors(f)
        # each label on the side of the picture its point is on; if one side gets much longer, the points nearest
        # the middle move over
        cx = self.rect[0] + self.rect[2] / 2
        left = [t for t in f["parts"] if spots[t[0]][0] < cx]
        right = [t for t in f["parts"] if spots[t[0]][0] >= cx]
        while abs(len(left) - len(right)) > 2:
            big, small = (left, right) if len(left) > len(right) else (right, left)
            t = min(big, key=lambda t: abs(spots[t[0]][0] - cx))
            big.remove(t)
            small.append(t)
        left.sort(key=lambda t: spots[t[0]][1])
        right.sort(key=lambda t: spots[t[0]][1])
        H = max(PIC, ROW * max(len(left), len(right)) + 12)
        top = (H - PIC) / 2
        c = self.canvas
        c.configure(height=H)
        c.delete("all")
        self.photo = self.glowing(f, spots)
        if self.photo is not None:
            c.create_image(COL + PIC / 2, top + PIC / 2, image=self.photo)
        elif self.src is not None:
            self.photo = self.src
            c.create_image(COL + PIC / 2, top + PIC / 2, image=self.photo)
        else:
            c.create_oval(COL + 50, top + 50, COL + PIC - 50, top + PIC - 50, fill="#e5e7eb", outline="")
            c.create_text(COL + PIC / 2, top + PIC / 2, text=(f["species"] or f["name"])[:12],
                          font=("Segoe UI", 16, "bold"), fill="#6b7280")
        if self.photo is None or self.photo is self.src:
            # no Pillow: the glow is a soft disc on the canvas instead
            for part, dmg, res in f["parts"]:
                col = glow_color(dmg)
                if col:
                    x, y = spots[part]
                    r = 12 + min(12, dmg / 30)
                    c.create_oval(COL + x - r, top + y - r, COL + x + r, top + y + r, fill=col, outline="",
                                  stipple="gray50")
        for side, rows in (("L", left), ("R", right)):
            ys = self._spread([top + spots[p[0]][1] for p in rows], H)
            for (part, dmg, res), ly in zip(rows, ys):
                x, y = spots[part]
                ax, ay = COL + x, top + y
                lx = COL - 4 if side == "L" else COL + PIC + 4
                calib = self.app.calib == (self, part)
                line = "#2563eb" if calib else "#9ca3af"
                c.create_line(lx, ly, ax, ay, fill=line, width=2 if calib else 1)
                c.create_oval(ax - 3, ay - 3, ax + 3, ay + 3, fill=dmg_color(dmg), outline="#111827")
                self._label(c, side, lx, ly, part, dmg, res, calib)
        if f["out"]:
            c.create_text(COL + PIC / 2, top + 14, text="OUT", font=("Segoe UI", 14, "bold"), fill="#991b1b")
        if self.app.calib and self.app.calib[0] is self:
            c.create_text(COL + PIC / 2, H - 8, text=f"click the picture where her {self.app.calib[1].lower()} is",
                          font=("Segoe UI", 8, "italic"), fill="#2563eb")
        # health and energy
        w = PIC + 2 * COL
        self.hp.delete("all")
        share = max(0.0, min(1.0, pct / 100.0))
        col = "#22c55e" if pct >= 60 else "#eab308" if pct >= 35 else "#f97316" if pct >= 15 else "#ef4444"
        self.hp.create_rectangle(0, 0, w * share, 18, fill=col, outline="")
        self.hp.create_text(6, 9, anchor="w", text=f"Health {f['health']:.0f}%   ({pct:.0f}% of full)",
                            font=("Segoe UI", 9, "bold"))
        self.en.delete("all")
        self.en.create_rectangle(0, 0, w * max(0.0, min(1.0, f["energy"] / 100.0)), 10, fill="#60a5fa", outline="")
        self.en.create_text(6, 5, anchor="w", text=f"energy {f['energy']:.0f}", font=("Segoe UI", 7))
        sts = ", ".join(f"{k.replace('_', ' ')} ({v})" if isinstance(v, (int, float)) and not isinstance(v, bool) else
                        k.replace("_", " ") for k, v in f["status"].items()) or "no statuses"
        self.state.configure(text=f"{f['posture']}  ·  {sts}")

    @staticmethod
    def _spread(want, H):
        """Label heights: each as near its part as it can be, never closer than a row to the next."""
        ys, last = [], -1e9
        for y in want:
            y = max(y, last + ROW, 9)
            ys.append(y)
            last = y
        over = (ys[-1] + 9 - H) if ys else 0
        if over > 0:      # pushed off the bottom: slide the stack up, keeping the spacing
            nxt = H - 9 + ROW
            for i in range(len(ys) - 1, -1, -1):
                ys[i] = min(ys[i], nxt - ROW)
                nxt = ys[i]
        return ys

    def _label(self, c, side, lx, ly, part, dmg, res, calib):
        name = short(part)
        tip = (f"{part}\ndamage {dmg:.1f}%  ({next(n for at, cc, n in DMG_STEPS if dmg >= at)})\n"
               f"resistance {res:.1f}%  ({next(n for at, cc, n in RES_STEPS if res >= at)})\n"
               f"(click this, then the picture, to move its point)")
        d, r = f"{dmg:.0f}%", f"{res:.0f}%"
        # [name] [damage on its colour] [resistance in its colour's frame], laid out away from the picture
        widths = (76, 38, 40)
        x = lx - sum(widths) if side == "L" else lx
        items = []
        items.append(c.create_text(x + (widths[0] - 2 if side == "L" else 2), ly, text=name,
                                   anchor="e" if side == "L" else "w", font=("Segoe UI", 8, "bold" if calib else "normal"),
                                   fill="#2563eb" if calib else "#111827"))
        order = (1, 2) if side == "L" else (1, 2)
        bx = x + widths[0] if side == "L" else x + widths[0]
        if side == "R":
            bx = x + widths[0]
        fill = dmg_color(dmg)
        items.append(c.create_rectangle(bx, ly - 7, bx + widths[1] - 2, ly + 7, fill=fill, outline=""))
        items.append(c.create_text(bx + (widths[1] - 2) / 2, ly, text=d, fill=text_on(fill), font=("Segoe UI", 7, "bold")))
        rx = bx + widths[1]
        items.append(c.create_rectangle(rx, ly - 7, rx + widths[2] - 2, ly + 7, fill="#ffffff", outline=res_color(res),
                                        width=2))
        items.append(c.create_text(rx + (widths[2] - 2) / 2, ly, text=r, fill="#111827", font=("Segoe UI", 7)))
        for it in items:
            c.tag_bind(it, "<Enter>", lambda e, t=tip: self.app.tip.show(e.x_root, e.y_root, t))
            c.tag_bind(it, "<Leave>", lambda e: self.app.tip.hide())
            c.tag_bind(it, "<Button-1>", lambda e, p=part: self.pick(p))

    # ---- placing a part's point by hand ----
    def pick(self, part):
        self.app.calib = None if self.app.calib == (self, part) else (self, part)
        for card in self.app.cards.values():
            if card.data:
                card.draw(card.data)
        return "break"

    def clicked(self, e):
        if not self.app.calib or self.app.calib[0] is not self or not self.data:
            return
        H = int(self.canvas.cget("height"))
        top = (H - PIC) / 2
        x, y = e.x - COL, e.y - top
        if not (0 <= x <= PIC and 0 <= y <= PIC):
            return
        part = self.app.calib[1]
        book = load_anchors()
        key = (self.data["name"] if self.own else self.data["species"] or self.data["name"]).lower()
        rx, ry, rw, rh = self.rect
        book.setdefault(key, {})[part] = [round((x - rx) / max(1, rw), 4), round((y - ry) / max(1, rh), 4)]
        save_anchors(book)
        self.app.calib = None
        self.draw(self.data)


class App:
    def __init__(self, args):
        self.root = tk.Tk()
        self.root.title("FightSim")
        self.root.geometry("1600x950")
        self.tip = Tip(self.root)
        self.out_q, self.in_q = queue.Queue(), queue.Queue()
        self.beats = []            # [(text index where the beat's output ends, snapshot)]
        self.live = None           # the newest state
        self.shown = None
        self.cards = {}
        self.calib = None          # (card, part) while a part's point is being placed by hand
        self.pending = ""          # text waiting for the end of its line
        self._build()
        self.game = GameThread(args, self.out_q, self.in_q)
        self.game.start()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(50, self.pump)

    # ---- layout ----
    def _build(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, padding=6)
        right = ttk.Frame(panes, padding=6)
        panes.add(left, weight=3)
        panes.add(right, weight=4)

        top = ttk.Frame(left)
        top.pack(fill="x")
        self.when = ttk.Label(top, text="Waiting for the fight…", font=("Segoe UI", 10, "bold"))
        self.when.pack(side="left")
        self.follow = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Follow the fight", variable=self.follow, command=self.follow_changed).pack(side="right")
        ttk.Button(top, text="▶", width=3, command=lambda: self.step(1)).pack(side="right")
        ttk.Button(top, text="◀", width=3, command=lambda: self.step(-1)).pack(side="right")
        self.slider = ttk.Scale(left, from_=0, to=0, orient="horizontal", command=self.slid)
        self.slider.pack(fill="x", pady=(4, 6))
        legend = ttk.Frame(left)
        legend.pack(fill="x")
        ttk.Label(legend, text="fill: damage").pack(side="left")
        for at, c, n in reversed(DMG_STEPS):
            tk.Label(legend, text=" " + n.split(" ")[0] + " ", bg=c, fg=text_on(c), font=("Segoe UI", 7)).pack(side="left", padx=1)
        ttk.Label(legend, text="  border: resistance").pack(side="left")
        for at, c, n in RES_STEPS:
            tk.Label(legend, text=" " + n.split(" ")[0] + " ", bg="#ffffff", fg="#111827", font=("Segoe UI", 7),
                     highlightbackground=c, highlightthickness=2).pack(side="left", padx=1)

        holder = ttk.Frame(left)
        holder.pack(fill="both", expand=True, pady=(6, 0))
        self.cards_canvas = tk.Canvas(holder, highlightthickness=0)
        sb = ttk.Scrollbar(holder, orient="horizontal", command=self.cards_canvas.xview)
        sbv = ttk.Scrollbar(holder, orient="vertical", command=self.cards_canvas.yview)
        self.cards_canvas.configure(xscrollcommand=sb.set, yscrollcommand=sbv.set)
        sb.pack(side="bottom", fill="x")
        sbv.pack(side="right", fill="y")
        self.cards_canvas.pack(side="left", fill="both", expand=True)
        self.cards_frame = ttk.Frame(self.cards_canvas)
        self.cards_canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.cards_frame.bind("<Configure>", lambda e: self.cards_canvas.configure(
            scrollregion=self.cards_canvas.bbox("all")))

        self.text = tk.Text(right, wrap="word", font=("Georgia", 11), padx=10, pady=8, undo=False,
                            background="#fffdf8", foreground="#1f2937")
        tsb = ttk.Scrollbar(right, orient="vertical",
                            command=lambda *a: (self.text.yview(*a), self.user_scroll()))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Prior>", "<Next>", "<Up>", "<Down>"):
            self.text.bind(ev, self.user_scroll, add="+")
        self.text.configure(yscrollcommand=lambda a, b: (tsb.set(a, b), self.scrolled()))
        bottom = ttk.Frame(right)
        bottom.pack(side="bottom", fill="x", pady=(6, 0))
        tsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("bold", font=("Georgia", 11, "bold"))
        self.text.tag_configure("italic", font=("Georgia", 11, "italic"), foreground="#7c3aed")
        self.text.tag_configure("pov", font=("Georgia", 12, "bold"), foreground="#b45309", spacing1=8, spacing3=4)
        self.text.tag_configure("mech", font=("Consolas", 9), foreground="#4b5563")
        self.text.tag_configure("mechbold", font=("Consolas", 9, "bold"), foreground="#111827")
        self.text.tag_configure("progress", font=("Segoe UI", 9, "italic"), foreground="#9ca3af")
        self.text.tag_configure("input", font=("Consolas", 10, "bold"), foreground="#2563eb")
        self.text.tag_configure("rule", foreground="#d1d5db")
        self.text.configure(state="disabled")

        self.prompt = ttk.Label(bottom, text=">", font=("Consolas", 10, "bold"))
        self.prompt.pack(side="left")
        self.entry = ttk.Entry(bottom, font=("Consolas", 11))
        self.entry.pack(side="left", fill="x", expand=True, padx=4)
        self.entry.bind("<Return>", self.send)
        ttk.Button(bottom, text="Next beat", command=lambda: self.send_line("")).pack(side="left", padx=2)
        ttk.Button(bottom, text="Auto 5", command=lambda: self.send_line("/auto 5")).pack(side="left", padx=2)
        ttk.Button(bottom, text="Undo", command=lambda: self.send_line("/undo")).pack(side="left", padx=2)
        self.entry.focus_set()

    # ---- input ----
    def send(self, _e=None):
        line = self.entry.get()
        self.entry.delete(0, "end")
        self.send_line(line)

    def send_line(self, line):
        self.in_q.put(line)
        self.prompt.configure(text="…")

    def close(self):
        self.in_q.put(None)
        self.root.destroy()

    # ---- output ----
    def pump(self):
        try:
            while True:
                kind, data = self.out_q.get_nowait()
                if kind == "text":
                    self.add_text(data)
                elif kind == "prompt":
                    self.flush_pending()
                    self.prompt.configure(text=data.strip() or ">")
                elif kind == "beat":
                    self.flush_pending()
                    self.beats.append((self.text.index("end-1c"), data))
                    self.live = data
                    self.slider.configure(to=len(self.beats))
                    if self.follow.get():
                        self.slider.set(len(self.beats))
                        self.show(data, live=True)
                elif kind == "live":
                    self.live = data
                    if self.follow.get():
                        self.show(data, live=True)
                elif kind == "done":
                    self.flush_pending()
                    self.prompt.configure(text="(the game has ended: close the window)")
        except queue.Empty:
            pass
        self.root.after(60, self.pump)

    def add_text(self, t):
        self.pending += t
        if "\n" in self.pending:
            done, self.pending = self.pending.rsplit("\n", 1)
            self.write_lines(done + "\n")

    def flush_pending(self):
        if self.pending:
            self.write_lines(self.pending)
            self.pending = ""

    def write_lines(self, chunk):
        at_end = self.follow.get() or self.text.yview()[1] >= 0.999
        self._writing = True
        self.text.configure(state="normal")
        for line in chunk.splitlines(keepends=True):
            body = line.rstrip("\n")
            s = body.strip()
            if re.match(r"^—\s.+\s—$", s):
                self.text.insert("end", line, "pov")
            elif re.match(r"^\s*\[.*\]\s*$", body):
                self.text.insert("end", line, "progress")
            elif re.match(r"^-{8,}$|^={8,}$|^─{8,}$|^═{8,}$", s):
                self.text.insert("end", line, "rule")
            elif re.match(r"^[^>]*> ", body) and s.endswith(tuple("abcdefghijklmnopqrstuvwxyz0123456789")) and len(s) < 80 \
                    and body.startswith(tuple("> ABCDEFGHIJKLMNOPQRSTUVWXYZ")) and "> " in body[:20]:
                self.text.insert("end", line, "input")
            elif re.match(r"^\s{2,}\S|^[⚔🔒📌🎲⏳💡🧗🪽🔗💥💢🪨🌀🌊🔐🤾🏋⛓⏸🩹📜⏱💨🛡🫳🫥↩🧱🌅🔥⚡💧😵🧠🌦🦅🪶🤚🧊]", body) \
                    or re.match(r"^\s*(Total|Calculations|Power|Rolls|Beat \d)", body):
                self.styled(line, "mech")
            else:
                self.styled(line)
        self.text.configure(state="disabled")
        if at_end:
            self.text.see("end")
        self._writing = False

    def styled(self, line, base=None):
        """**bold** and *thoughts and sounds*, as the console shows them."""
        pos = 0
        extra = (base,) if base else ()
        for m in re.finditer(r"\*\*(.+?)\*\*|\*(?!\s)([^*\n]+?)\*", line):
            self.text.insert("end", line[pos:m.start()], extra)
            if m.group(1) is not None:
                self.text.insert("end", m.group(1), ("mechbold",) if base else ("bold",))
            else:
                self.text.insert("end", m.group(2), extra + ("italic",) if not base else extra)
            pos = m.end()
        self.text.insert("end", line[pos:], extra)

    # ---- which beat is shown ----
    def user_scroll(self, _e=None):
        self._user_scrolled = True
        self.root.after(30, self.scrolled)

    def scrolled(self):
        if getattr(self, "_writing", False) or not self.beats:
            return
        if self.follow.get():
            if not getattr(self, "_user_scrolled", False) or self.text.yview()[1] >= 0.999:
                return
        self._user_scrolled = False
        top = self.text.index("@0,0")
        for i, (mark, snap) in enumerate(self.beats):
            if self.text.compare(mark, ">", top):
                if self.text.yview()[1] < 0.999:
                    self.follow.set(False)
                self.slider.set(i + 1)
                self.show(snap)
                return
        if self.live is not None:
            self.show(self.live, live=True)

    def slid(self, value):
        i = int(round(float(value)))
        if not self.beats:
            return
        if i >= len(self.beats):
            self.show(self.live or self.beats[-1][1], live=True)
            return
        i = max(1, i)
        mark, snap = self.beats[i - 1]
        self.show(snap)
        start = self.beats[i - 2][0] if i >= 2 else "1.0"
        if self.text.compare("@0,0", "<", start) or self.text.compare("@0,0", ">", mark):
            self.text.see(start)

    def step(self, d):
        self.follow.set(False)
        self.slider.set(max(1, min(len(self.beats), int(round(float(self.slider.get()))) + d)))
        self.slid(self.slider.get())

    def follow_changed(self):
        if self.follow.get():
            self.slider.set(len(self.beats))
            self.text.see("end")
            if self.live:
                self.show(self.live, live=True)

    def show(self, snap, live=False):
        self.shown = snap
        names = [f["name"] for f in snap["fighters"]]
        if list(self.cards) != names:
            for c in self.cards.values():
                c.destroy()
            self.cards = {}
            for k, f in enumerate(snap["fighters"]):
                card = FighterCard(self.cards_frame, self, f["name"])
                card.grid(row=k, column=0, sticky="n", padx=4, pady=4)
                self.cards[f["name"]] = card
                self.load_picture(card, f)
        for f in snap["fighters"]:
            self.cards[f["name"]].draw(f)
        self.when.configure(text=("Now" if live else f"As it stood {snap['label']}")
                            + (f"  ·  beat {snap['turn']}" if snap.get("turn") else ""))

    def load_picture(self, card, f):
        def done(data, own):
            self.root.after(0, lambda: self.make_photo(card, data, own))
        fetch_picture(f["name"], f["species"] or f["name"], done)

    def make_photo(self, card, data, own=False):
        if data and card.winfo_exists():
            card.own = own
            card.set_picture(data)

    def run(self):
        self.root.mainloop()


def main(argv=None):
    args = play.build_args(argv)
    App(args).run()


if __name__ == "__main__":
    main()
