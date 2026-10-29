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
drawn instead. Each fighter also gets a picture from behind, under the first one, carrying her back, lower back and
tails (<name>_back.png or <species>_back.png, else the PokeAPI back sprite, else her outline), so the front isn't
crowded; click a part's label, then either picture, to place it there. As she weakens her pictures show it: your own
<name>_worn.png, _hurt, _down and _out (and _back_hurt and so on), and pose pictures (_pinned, _faceup, _side...: see
rules.json window.poses) if you have them, else her picture fades, slumps,
or tips over. "Back view" and "Weakened look" on the bar above the cards turn each off (rules.json "window")."""
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

import explain

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

import play
import display
import textpane
from engine import species_of, body_region, note_failure, poss_word

from cards import (IMG_DIR, PIC, COL, ROW, RES_STEPS, DMG_STEPS, res_color, dmg_color, text_on, short,
                   glow_color, load_anchors, save_anchors, picture_bytes, point_key, anchor_points, glow_image,
                   columns, spread, PictureBook, card_panels, panel_origin, opts_of, VIEW_CAPTION, STATE_CAPTION,
                   held_parts, tap_meter, grip_lines, TAP_COLORS, pct_text, ecg_points, vitals_colour,
                   squeeze_shapes, squeeze_label, squeeze_figure, squeeze_colours, heart_shapes, heart_beat,
                   picture_colours, squeeze_word, mix, squeeze_readout, blackout_text, hold_shapes, alive_opts,
                   body_signs, breath_phase, impacts, breathe_image, grey_image, flash_layer, throb_layer,
                   monitor_words)

try:                           # Pillow makes the pictures smoother when it is installed; Tk alone works too
    from PIL import Image, ImageTk
except Exception:              # pragma: no cover
    Image = ImageTk = None

snapshot = play.fight_snapshot


# window.dark (since build 258): the window in dark colours. Every colour the window draws goes through C(), which
# gives the light one its dark counterpart while dark mode is on: backgrounds go dark, text goes light, and the
# blues, reds and violets that mark things go a shade lighter so they still stand out. The bright marks (the
# damage fill, the bars, the tap steps) keep their colours.
DARK = {
    # backgrounds
    "#ffffff": "#1e2029", "#fffdf8": "#17181e", "#f3f4f6": "#252732", "#e5e7eb": "#3a3d4a", "#f3f5f9": "#21232c",
    "#e8ecf3": "#2b2e3a", "#ecfdf5": "#12302a", "#f9fafb": "#f9fafb",
    # text and lines
    "#111827": "#e5e7eb", "#1f2937": "#e5e7eb", "#4b5563": "#a1a1aa", "#6b7280": "#9ca3af", "#9ca3af": "#6b7280",
    "#d1d5db": "#4b5563",
    # the colours that mark things
    "#2563eb": "#60a5fa", "#1d4ed8": "#93c5fd", "#991b1b": "#f87171", "#b91c1c": "#f87171", "#7f1d1d": "#fca5a5",
    "#7c3aed": "#c4b5fd", "#c4b5fd": "#8b5cf6", "#b45309": "#fbbf24", "#15803d": "#4ade80", "#047857": "#34d399",
    "#0f766e": "#5eead4",
    # (since build 290) the pain gauge's grey bar: a dark grey, so the light words on it can be read
    "#a3a3a3": "#4b5563",
}
# (since build 290) the tap meter's words in its step colours, lighter on the dark background (the darkest steps were
# dark red on near-black)
DARK_TEXT = {"#ea580c": "#fb923c", "#dc2626": "#f87171", "#7f1d1d": "#fca5a5"}


def halo_text(c, x, y, **kw):
    """(since build 290) Words on a canvas that stay readable over a bright bar and over the dark background alike: in
    dark mode a dark edge is drawn round the light letters first."""
    if _THEME["dark"]:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            c.create_text(x + dx, y + dy, **dict(kw, fill="#0b0c10"))
    return c.create_text(x, y, **kw)
_THEME = {"dark": False}


def C(colour):
    """A colour as the window shows it: its dark-mode counterpart while window.dark is on (DARK), else itself."""
    return DARK.get(str(colour).lower(), colour) if _THEME["dark"] else colour


def dark_on(rules):
    """window.dark.enabled from these rules, with my_settings.json laid over them (the window may be built before the
    game has loaded its rules)."""
    on = ((rules.get("window") or {}).get("dark") or {}).get("enabled", True)
    try:
        if os.path.exists(play.MY_SETTINGS):
            with open(play.MY_SETTINGS, encoding="utf-8") as fh:
                mine = ((json.load(fh).get("window") or {}).get("dark") or {})
            on = mine.get("enabled", on)
    except Exception as e:
        note_failure("window.dark_on", e)
    return bool(on)


# Tk may only be torn down on the main thread. A closed window (or the one from an earlier run in Spyder) that is
# still tied up in reference cycles would otherwise be freed by whichever thread happens to trigger garbage
# collection, often the game thread finishing its last beat, and that kills the Spyder kernel ("Tcl_AsyncDelete:
# async handler deleted by the wrong thread"). So every window is kept alive for the rest of the session (a few
# megabytes at most), on builtins so a re-run in the same Spyder session doesn't drop the old list.
def _keep_alive(app):
    keep = getattr(builtins, "_fightsim_windows", None)
    if keep is None:
        keep = builtins._fightsim_windows = []
    keep.append(app)


class _Flag(tk.BooleanVar):
    """A BooleanVar whose clean-up is skipped off the main thread (the same crash, one variable at a time)."""

    def __del__(self):
        if threading.current_thread() is threading.main_thread():
            super().__del__()


# The game runs on its own thread, but print() and input() are shared by the whole program. They are routed, not
# swapped: whatever the game's thread prints or asks goes to the window that is open now, and everything else (the
# Spyder console, a window closed while its last beat was still finishing) keeps the real screen and keyboard. The
# routing state lives on the builtins module so a second run in the same Spyder session takes it over cleanly.
def _route():
    return getattr(builtins, "_fightsim_route", None) or {}


def _current_game():
    """The game thread that should get this print or input, or None for the real console."""
    t = threading.current_thread()
    if t is threading.main_thread():
        return None
    game = _route().get("game")
    if getattr(t, "fightsim_game", False):
        return t if t is game else None      # an old window's thread, still finishing: back to the console
    return game if game is not None and game.is_alive() else None



# the console's coloured squares (resistance) and dots (damage), and its heart: the same colours as the cards
GLYPHS = {"🟦": ("■", "#3b82f6"), "🟩": ("■", "#22c55e"), "🟨": ("■", "#eab308"), "🟧": ("■", "#f97316"),
          "🟥": ("■", "#ef4444"), "🟪": ("■", "#a855f7"), "⬛": ("■", "#1f2937"), "🟫": ("■", "#92400e"),
          "🟢": ("●", "#22c55e"), "🟡": ("●", "#eab308"), "🟠": ("●", "#f97316"), "🔴": ("●", "#ef4444"),
          "🟣": ("●", "#a855f7"), "⚫": ("●", "#1f2937"), "🔵": ("●", "#3b82f6"), "🟤": ("●", "#92400e"),
          "❤": ("♥", "#dc2626")}
GLYPH_RX = re.compile("(" + "|".join(map(re.escape, GLYPHS)) + ")\ufe0f?")

class _Screen:
    """Stands in for sys.stdout: the game's thread writes to its window, everyone else to the real screen."""

    def __init__(self, real):
        self._real = real
        self._fightsim = True

    def write(self, t):
        g = _current_game()
        if g is None:
            return self._real.write(t)
        if t:
            g.out_q.put(("text", str(t)))
        return len(t or "")

    def flush(self):
        if getattr(self._real, "pub_thread", None) is not None or getattr(self._real, "_pub_thread", None) is not None \
                or type(self._real).__module__.startswith("ipykernel") or type(self._real).__name__ == "OutStream":
            # (since build 278: newer ipykernels, IPython 9 in Spyder 6, are known by their stream's type too)
            # (since build 269) Spyder's console (an ipykernel stream) flushes itself every fraction of a second;
            # asking it to from the window's threads only made it wait and print "IOStream.flush timed out"
            return
        if _current_game() is None:
            try:
                self._real.flush()
            except Exception:
                pass

    def isatty(self):
        return False if _current_game() is not None else getattr(self._real, "isatty", lambda: False)()

    def __getattr__(self, name):
        return getattr(self._real, name)


def _install_routing():
    if not hasattr(builtins, "_fightsim_route"):
        builtins._fightsim_route = {"game": None}
    real_in = getattr(builtins.input, "_real", builtins.input)
    real_out = getattr(sys.stdout, "_real", sys.stdout)

    def routed_input(prompt=""):
        g = _current_game()
        return g.ask(prompt) if g is not None else real_in(prompt)
    routed_input._real = real_in
    builtins.input = routed_input
    sys.stdout = _Screen(real_out)
    beat = getattr(play.Session.play_beat, "_real", play.Session.play_beat)

    def play_beat(sess, *a, **k):
        try:
            return beat(sess, *a, **k)
        finally:
            g = _current_game()
            if g is not None:
                g.out_q.put(("beat", snapshot(sess)))
    play_beat._real = beat
    play.Session.play_beat = play_beat
    record = getattr(play.Session._record_beat, "_real", play.Session._record_beat)

    def record_beat(sess, tlen, label=None):
        # (since build 301) the start of a fight: a place of its own on the beat slider, before the first blow
        n = len(sess.beat_records)
        out = record(sess, tlen, label)
        g = _current_game()
        if g is not None and label == "the start" and len(sess.beat_records) > n:
            g.out_q.put(("beat", sess.beat_records[-1]["snapshot"]))
        return out
    record_beat._real = record
    play.Session._record_beat = record_beat
    for name in ("undo", "load"):
        real = getattr(getattr(play.Session, name), "_real", getattr(play.Session, name))

        def rebuilt(sess, *a, _real=real, **k):
            # (since build 301) after /undo or /load the window's story and beat history are rebuilt from the
            # session's own record of every beat (its text, and every fighter as she stood), so nothing undone
            # stays on the slider and a loaded fight comes back whole
            out = _real(sess, *a, **k)
            g = _current_game()
            if g is not None:
                g.out_q.put(("rebuild", ([(r.get("text", ""), r["snapshot"]) for r in sess.beat_records],
                                         snapshot(sess, "now"))))
            return out
        rebuilt._real = real
        setattr(play.Session, name, rebuilt)


class GameThread(threading.Thread):
    """Runs the ordinary game loop (play._run), its printing and asking routed to the window."""

    def __init__(self, args, out_q, in_q):
        super().__init__(daemon=True)
        self.args, self.out_q, self.in_q = args, out_q, in_q
        self.session = None
        self.fightsim_game = True
        self.waiting = False       # at the prompt (True), or busy writing a beat

    def ask(self, prompt=""):
        if self.session is not None:
            self.out_q.put(("live", snapshot(self.session, "now")))
        self.out_q.put(("prompt", str(prompt)))
        self.waiting = True
        line = self.in_q.get()
        self.waiting = False
        if line is None:
            raise EOFError
        self.out_q.put(("text", f"{prompt}{line}\n"))
        return line

    def run(self):
        _install_routing()
        _route()["game"] = self
        try:
            self.session = play.Session(self.args)
            self.out_q.put(("live", snapshot(self.session, "now")))
            play._run(self.session, self.args)
        except EOFError:
            pass
        except Exception as e:      # shown in the window rather than lost
            import traceback
            self.out_q.put(("text", "\n" + traceback.format_exc() + f"\n[the game stopped: {e}]\n"))
        finally:
            if _route().get("game") is self:
                _route()["game"] = None
            self.out_q.put(("done", None))


def fetch_book(name, species, opts, done):
    """Her pictures (cards.PictureBook: front, back, weakened ones), found or fetched on a worker thread and handed to
    done(book)."""
    def work():
        book = PictureBook(name, species, opts)
        book.base("front")
        if opts.get("back_view", True):
            book.base("back")
        done(book)
    threading.Thread(target=work, daemon=True).start()


def fetch_picture(name, species, done):
    """The picture (cards.picture_bytes), fetched on a worker thread and handed to done(bytes or None, own)."""
    threading.Thread(target=lambda: done(*picture_bytes(name, species)), daemon=True).start()



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
        # (since build 312) kept on the screen: a long tip near the right or bottom edge opens the other way
        self.win.update_idletasks()
        tw, th = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        nx = x + 14 if x + 14 + tw <= sw else max(0, x - 14 - tw)
        ny = y + 10 if y + 10 + th <= sh else max(0, y - 10 - th)
        self.win.wm_geometry(f"+{nx}+{ny}")

    def hide(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None


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
        self.book = None         # every picture she has (cards.PictureBook): front, back, weakened
        self.cache = {}          # pictures already prepared for a view and a look
        self.panels = []         # what is on the canvas now, top to bottom (cards.card_panels), with where each sits
        self.photos = []
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.head = ttk.Label(top, font=("Segoe UI", 12, "bold"))
        self.head.pack(side="left")
        self.sub = ttk.Label(top, foreground=C("#6b7280"))
        self.sub.pack(side="left", padx=8)
        self.canvas = tk.Canvas(self, width=PIC + 2 * COL, height=PIC, bg=C("#ffffff"), highlightthickness=0)
        self.canvas.pack(pady=(4, 4))
        self.canvas.bind("<Button-1>", self.clicked)
        self.hp = tk.Canvas(self, width=PIC + 2 * COL, height=18, highlightthickness=0, bg=C("#e5e7eb"))
        self.hp.pack(fill="x")
        self.en = tk.Canvas(self, width=PIC + 2 * COL, height=10, highlightthickness=0, bg=C("#e5e7eb"))
        self.en.pack(fill="x", pady=(2, 0))
        # (since build 306) her heart monitor, on every card (window.alive.heart_monitor): her heart rate, blood
        # pressure and breathing from how she is, a moving trace, and the words for her condition (always dark)
        self.hb = tk.Canvas(self, width=PIC + 2 * COL, height=46, highlightthickness=0, bg="#111827")
        self.hits = ([], 0.0)     # what landed on her since the beat before (cards.impacts), for the jolt and flash
        self._alive = None        # the picture's living frames (window.alive): see _alive_setup
        # a submission match: one pip per tap-out the match needs, filled for each she has given (with the part)
        self.tp = tk.Canvas(self, width=PIC + 2 * COL, height=20, highlightthickness=0, bg=C("#f3f4f6"))
        # her pain against what she can bear (window.pain_gauge): a bar with a mark at 100%, more in a submission
        self.pg = tk.Canvas(self, width=PIC + 2 * COL, height=34, highlightthickness=0, bg=C("#f3f4f6"))
        # how near she is to tapping (window.hold_panel): five steps (the narrator's ladder) and this beat's chance
        self.tm = tk.Canvas(self, width=PIC + 2 * COL, height=34, highlightthickness=0, bg=C("#f3f4f6"))
        # (since build 287) coils round her body: her heart as a trace, the blood flow cut off, her blood pressure
        # (a monitor: always dark, in either theme; build 290 ran it through C, which made it light in dark mode)
        self.vt = tk.Canvas(self, width=PIC + 2 * COL, height=60, highlightthickness=0, bg="#111827")
        # (since build 304) the grips on her as a picture: what each does to her body (window.hold_picture)
        self.hd = tk.Canvas(self, width=PIC + 2 * COL, height=160, highlightthickness=0, bg="#111827")
        # the grips on her and by her, a pin, and how far she is from the others (window.hold_panel)
        self.gp = tk.Canvas(self, width=PIC + 2 * COL, height=18, highlightthickness=0, bg=C("#ffffff"))
        self.state = ttk.Label(self, wraplength=PIC + 2 * COL, justify="left")
        self.state.pack(anchor="w", pady=(4, 0))
        # (since build 312, window.explain) hovering her status line explains every status on her
        self.state.bind("<Enter>", self._status_tip)
        self.state.bind("<Leave>", lambda _e: self.app.tip.hide())

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
        """Where each part is on the picture (cards.anchor_points)."""
        pil = self.src if (Image is not None and self.src is not None and not isinstance(self.src, tk.PhotoImage)) else None
        return anchor_points(f, pil, self.rect, self.box, self.own, has_picture=self.src is not None)

    def glowing(self, f, spots):
        """The picture with each hurt part glowing (cards.glow_image), as a Tk photo; None without Pillow."""
        if Image is None or self.src is None or isinstance(self.src, tk.PhotoImage):
            return None
        return ImageTk.PhotoImage(glow_image(self.src, f, spots))

    # ---- drawing ----
    def draw(self, f):
        if self.book is not None and Image is not None:
            return self.draw_panels(f)
        return self.draw_one(f)

    def draw_panels(self, f):
        """Her pictures stacked (front, then her back), each part's label beside the picture it is on."""
        self.data = f
        pct = 100.0 * f["health"] / f["max"]
        calib_here = bool(self.app.calib and self.app.calib[0] is self)
        z = self.app.card_zoom
        if abs(z - 1.0) > 1e-3 and not calib_here:
            return self.draw_scaled(f, pct, z)
        self.canvas.configure(width=PIC + 2 * COL)
        panels = card_panels(f, self.book, self.app.card_opts(), plain=calib_here, cache=self.cache)
        st = panels[0]["state"] if panels else None
        self.head.configure(text=f["name"] + ("   — OUT" if f["out"] else f"   ({STATE_CAPTION[st]})" if st else ""))
        self.sub.configure(text=f"{f['species']}  ·  {' / '.join(f['types'])}")
        gap = 16
        H = sum(pn["height"] for pn in panels) + gap * (len(panels) - 1)
        c = self.canvas
        c.configure(height=H)
        c.delete("all")
        self.photos, self.panels = [], []
        self._rings, live_pics = [], []
        self._grip_cols = self._grip_colours(f)
        top = 0
        for pn in panels:
            ox, oy = panel_origin(pn, top)
            self.panels.append(dict(pn, top=top, ox=ox, oy=oy))
            if pn["pic"] is not None:
                ph = ImageTk.PhotoImage(pn["pic"])
                self.photos.append(ph)
                item = c.create_image(ox, oy, image=ph, anchor="nw")
                live_pics.append(dict(pn, item=item, ox=ox, oy=oy))
            cap = VIEW_CAPTION.get(pn["view"], "")
            if cap:
                c.create_text(COL + PIC / 2, top - 3, text=cap, anchor="s", font=("Segoe UI", 7), fill=C("#6b7280"))
            spots = pn["spots"]
            for side, rows in (("L", pn["left"]), ("R", pn["right"])):
                ys = spread([oy + spots[q[0]][1] for q in rows], top + pn["height"])
                for (part, dmg, res), ly in zip(rows, ys):
                    x, y = spots[part]
                    ax, ay = ox + x, oy + y
                    lx = COL - 4 if side == "L" else COL + PIC + 4
                    calib = self.app.calib == (self, part)
                    c.create_line(lx, ly, ax, ay, fill=C("#2563eb") if calib else C("#9ca3af"), width=2 if calib else 1)
                    c.create_oval(ax - 3, ay - 3, ax + 3, ay + 3, fill=dmg_color(dmg), outline=C("#111827"))
                    self._ring(c, f, part, ax, ay)
                    self._label(c, side, lx, ly, part, dmg, res, calib)
            top += pn["height"] + gap
        if f["out"]:
            c.create_text(COL + PIC / 2, 14, text="OUT", font=("Segoe UI", 14, "bold"), fill=C("#991b1b"))
        if calib_here:
            c.create_text(COL + PIC / 2, H - 8, font=("Segoe UI", 8, "italic"), fill=C("#2563eb"),
                          text=f"click either picture where her {self.app.calib[1].lower()} is"
                               + (" (the back picture moves it there)" if len(panels) > 1 else ""))
        self._alive_setup(f, [] if calib_here else live_pics)
        self._bars(f, pct)

    def draw_scaled(self, f, pct, z):
        """(since build 273) the card at another size (the Cards − / + buttons): her pictures and their labels drawn
        as the exported fight draws them (cards.render_card), then made smaller or bigger to fit; the bars below are
        as wide as it. Placing a part's point by clicking goes back to full size for it."""
        from cards import render_card
        st = None
        try:
            img = render_card(f, book=self.book, opts=self.app.card_opts())
        except Exception as e:
            note_failure("drawing the card at another size (window.card_zoom)", e)
            img = None
        if img is None:
            self.app.card_zoom = 1.0
            return self.draw_panels(f)
        img = img.crop((0, 30, img.width, img.height - 40))      # (its own name line and bars: the window has them)
        w, h = max(1, int(img.width * z)), max(1, int(img.height * z))
        img = img.resize((w, h), Image.LANCZOS)
        ph = ImageTk.PhotoImage(img)
        try:
            st = card_panels(f, self.book, self.app.card_opts(), cache=self.cache)[0]["state"]
        except Exception:
            st = None
        self.head.configure(text=f["name"] + ("   — OUT" if f["out"] else f"   ({STATE_CAPTION[st]})" if st else ""))
        self.sub.configure(text=f"{f['species']}  ·  {' / '.join(f['types'])}")
        c = self.canvas
        c.configure(width=w, height=h)
        c.delete("all")
        self.photos, self.panels = [ph], []
        c.create_image(0, 0, image=ph, anchor="nw")
        self._rings, self._grip_cols = [], {}
        self._alive_setup(f, [])
        self._bars(f, pct)

    def _taps(self, f):
        """The tap tally under her energy bar (submission matches only): a pip per tap-out the match needs, red and
        filled for each she has given, with the parts they came from."""
        t = f.get("taps")
        if not t:
            if self.tp.winfo_ismapped():
                self.tp.pack_forget()
            return
        if not self.tp.winfo_ismapped():
            self.tp.pack(fill="x", pady=(2, 0), before=self.state)
        c = self.tp
        c.delete("all")
        given, need = list(t.get("given") or []), max(1, int(t.get("needed") or 1))
        c.create_text(6, 10, anchor="w", text="Taps", font=("Segoe UI", 8, "bold"), fill=C("#111827"))
        x = 40
        for i in range(max(need, len(given))):
            done = i < len(given)
            c.create_oval(x, 4, x + 12, 16, fill=C("#dc2626") if done else C("#ffffff"), outline=C("#7f1d1d"), width=1.5)
            x += 16
        parts = ", ".join(str(p).lower() for p in given)
        c.create_text(x + 6, 10, anchor="w", font=("Segoe UI", 8),
                      text=f"{len(given)} of {need}" + (f"  ({parts})" if parts else ""),
                      fill=C("#991b1b") if len(given) >= need else C("#111827"))

    def _ring(self, c, f, part, x, y):
        """A part in someone's grip gets a violet ring on her picture (window.hold_panel); with
        window.alive.grip_outline (since build 306) the ring is in the holder's own colours and pulses, tightening
        and easing like the grip."""
        if part not in held_parts(f):
            return
        col = (getattr(self, "_grip_cols", None) or {}).get(part)
        if col:
            a = c.create_oval(x - 9, y - 9, x + 9, y + 9, outline=col, width=3)
            b = c.create_oval(x - 13, y - 13, x + 13, y + 13, outline=mix(col, "#ffffff", 0.45), width=1, dash=(3, 2))
            self._rings.append((a, b, x, y))
            return
        c.create_oval(x - 9, y - 9, x + 9, y + 9, outline=C("#7c3aed"), width=2)
        c.create_oval(x - 13, y - 13, x + 13, y + 13, outline=C("#c4b5fd"), width=1, dash=(3, 2))

    # ---- window.alive (since build 306): her picture breathing, her hurts throbbing, blows landing, the grey ----
    def _alive_cfg(self):
        return alive_opts(self.app._rules() if hasattr(self.app, "_rules") else None)

    def _grip_colours(self, f):
        """{her gripped part: the colour of whoever holds it} (window.alive.grip_outline), {} when it is off."""
        o = self._alive_cfg()
        if not (o.get("enabled", True) and o.get("grip_outline", True)):
            return {}
        cards_ = getattr(self.app, "cards", None) or {}
        out = {}
        for g in (f.get("grips") or {}).get("held") or ():
            col = picture_colours(getattr(cards_.get(g.get("by")), "book", None), "#a78bfa")[0]
            # (a dark holder's colour would vanish on her picture: lifted toward white)
            col = mix(col, "#ffffff", 0.25)
            for p in g.get("parts") or ():
                out.setdefault(p, col)
        return out

    def _alive_setup(self, f, pics):
        """Get her picture's living frames ready for _alive_tick: her signs (cards.body_signs), each picture with
        what its frames are made from, and this beat's blows (self.hits, set by App.show) to jolt and flash."""
        o = self._alive_cfg()
        if not getattr(self, "_alive_running", False):
            self._alive_running = True        # (always ticking, so /effects turned on later is picked up)
            self.after(30, self._alive_tick)
        if not o.get("enabled", True):
            self._alive = None
            return
        import time as _time
        sg = body_signs(f, o)
        hits, jolt = self.hits if o.get("impact", True) else ([], 0.0)
        self.hits = ([], 0.0)
        for p in pics:
            p["frames"] = {}
            p["throb_l"] = (throb_layer(p["src"], f, p["spots"])
                            if o.get("pulse", True) and sg["throb"] > 0 and p.get("src") is not None else None)
            mine = [(q, s) for q, s in hits if q in p["spots"]]
            p["flash_l"] = flash_layer(p["src"], p["spots"], mine) if mine and p.get("src") is not None else None
        self._alive = {"sg": sg, "o": o, "pics": pics, "t0": _time.monotonic(), "jolt": jolt if hits else 0.0}

    def _alive_frame(self, p, bq, tq, fq):
        """One frame of a picture: her hurts glowing brighter by tq, a blow's flash by fq, breathed in by bq, the
        grey over it all (each a step, so the frames are made once and kept)."""
        key = (bq, tq, fq)
        ph = p["frames"].get(key)
        if ph is not None:
            return ph
        al = self._alive
        o, sg = al["o"], al["sg"]
        img = p["raw"]
        for layer, k in ((p["throb_l"], tq / 3.0 * sg["throb"] * float(o.get("throb", 0.6))), (p["flash_l"], fq / 3.0)):
            if layer is not None and k > 0:
                img = img.copy()
                lay = layer.copy()
                lay.putalpha(lay.getchannel("A").point(lambda a, k=k: int(a * min(1.0, k))))
                img.alpha_composite(lay)
        if bq and p.get("box"):
            img = breathe_image(img, p["box"], float(o.get("breath_depth", 0.012)) * sg["depth"] * bq / 5.0)
        if p.get("grey"):
            img = grey_image(img, p["grey"], float(o.get("vignette", 0.75)))
        ph = ImageTk.PhotoImage(img)
        p["frames"][key] = ph
        return ph

    def _alive_tick(self):
        """One step of the living card: each picture's frame for this moment (her breath, her heartbeat, a blow
        still landing), the jolt of a blow, the grip rings tightening and easing, and the heart monitor's trace."""
        import time as _time
        try:
            if not self.winfo_exists():
                self._alive_running = False
                return
            al = self._alive
            fps = 12
            self._tickn = getattr(self, "_tickn", 0) + 1
            o_now = self._alive_cfg() if self._tickn % 12 == 0 else None      # (about once a second)
            if o_now is not None and self.data \
                    and (al["o"] if al else None) != (o_now if o_now.get("enabled", True) else None):
                # (/effects or /set changed the effects: draw the card again with them)
                self.draw(self.data)
                al = self._alive
            if al:
                o, sg = al["o"], al["sg"]
                fps = max(4, min(30, int(o.get("fps", 12))))
                now = _time.monotonic()
                dt = now - al["t0"]
                bq = (int(round(5 * breath_phase(sg["breath"], now))) if o.get("breathing", True) and sg["depth"] > 0
                      else 0)
                tq = (int(round(3 * heart_beat(sg["heart"], now, sg["irregular"])))
                      if o.get("pulse", True) and sg["throb"] > 0 else 0)
                dur = float(o.get("jolt_seconds", 0.45))
                u = dt / dur if al["jolt"] else 1.0
                fq = max(0, int(math.ceil(3 * (1.0 - u)))) if u < 1.0 else 0
                dx = dy = 0.0
                if u < 1.0:
                    amp = float(o.get("jolt_px", 7)) * (0.35 + 0.65 * al["jolt"])
                    dx = amp * math.exp(-4.0 * u) * math.sin(u * math.pi * 6)
                    dy = 0.4 * amp * math.exp(-4.0 * u) * math.sin(u * math.pi * 4 + 1.0)
                for p in al["pics"]:
                    if p.get("raw") is None:
                        continue
                    want = (bq, tq, fq)
                    if p.get("shown") != want:
                        self.canvas.itemconfigure(p["item"], image=self._alive_frame(p, *want))
                        p["shown"] = want
                    self.canvas.coords(p["item"], p["ox"] + dx, p["oy"] + dy)
                r = 2.2 * math.sin(2 * math.pi * now * 0.9)
                for a, b, x, y in getattr(self, "_rings", None) or ():
                    self.canvas.coords(a, x - 9 - r, y - 9 - r, x + 9 + r, y + 9 + r)
                    self.canvas.coords(b, x - 13 - r, y - 13 - r, x + 13 + r, y + 13 + r)
            self._monitor_tick()
            self.after(int(1000 / fps), self._alive_tick)
        except tk.TclError:
            self._alive_running = False      # (the card was closed)

    def _monitor(self, f):
        """window.alive.heart_monitor (since build 306): her heart monitor under her bars, always there: her heart
        rate and a trace of it moving at that rate, her blood pressure and her breathing, each beside its normal,
        and what is doing it (winded, the pain, her statuses). While coils squeeze her the constriction's own
        monitor (the vitals strip) takes its place."""
        o = self._alive_cfg()
        sg = (self._alive or {}).get("sg") or body_signs(f, o)
        on = bool(o.get("enabled", True) and o.get("heart_monitor", True) and not sg["coiled"])
        self._show(self.hb, on)
        self._mon = None
        if not on:
            return
        c, w = self.hb, self.app.card_w()
        c.delete("all")
        rd = monitor_words(sg)
        # (since build 312, window.explain) each reading explains itself on hover
        tips = self._explain_on()
        heart_tip = explain.heart_text(sg["heart"], sg["heart_rest"], sg["irregular"], sg["stopped"])
        row_tips = (explain.bp_text(sg["bp"], sg["bp_rest"]),
                    explain.breath_text(sg["breath"], sg["breath_rest"], sg["depth"], sg["words"]))
        self._tip(c, c.create_text(6, 11, anchor="w", text=rd[0][0], font=("Segoe UI", 9, "bold"), fill=rd[0][1]),
                  heart_tip, tips)
        self._tip(c, c.create_text(6, 24, anchor="w", text=rd[1][0], font=("Segoe UI", 7), fill=rd[1][1]),
                  heart_tip, tips)
        sx = w - 175
        for k, (y, (t1, c1, _), (t2, c2, _)) in enumerate(((11, rd[2], rd[3]), (24, rd[4], rd[5]))):
            a = c.create_text(sx, y, anchor="w", text=t1, font=("Segoe UI", 8, "bold"), fill=c1)
            b = c.create_text(c.bbox(a)[2] + 5, y, anchor="w", text=t2, font=("Segoe UI", 7), fill=c2)
            self._tip(c, a, row_tips[k], tips)
            self._tip(c, b, row_tips[k], tips)
        bx, bw = 84, max(30, sx - 84 - 8)
        base = ecg_points(sg["heart"], sg["irregular"], bw, 22, 0, 3)
        base = base + [(x + bw, y) for x, y in base[1:]]
        line = c.create_line(*[q for x, y in base if x <= bw for q in (bx + x, y)], fill=sg["colour"], width=1.5)
        self._tip(c, line, heart_tip, tips)
        anim = bool(o.get("enabled", True)) and (self.app._rules().get("window") or {}).get("vitals_animate", True) \
            if hasattr(self.app, "_rules") else True
        self._mon = {"base": base, "line": line, "bx": bx, "bw": bw, "off": 0.0, "anim": anim}
        words = "  ·  ".join(sg["words"]) or ("steady" if not f.get("out") else "")
        t = c.create_text(6, 37, anchor="nw", text=words, width=w - 12, font=("Segoe UI", 8),
                          fill="#fca5a5" if sg["colour"] == "#ef4444" else "#d1d5db")
        c.configure(height=max(46, c.bbox(t)[3] + 3) if words else 34)

    def _monitor_tick(self):
        st = getattr(self, "_mon", None)
        if not st or not st["anim"] or not self.hb.winfo_ismapped():
            return
        st["off"] = (st["off"] + st["bw"] * (1.0 / max(4, int((self._alive or {}).get("o", {}).get("fps", 12))))
                     / 6.0) % st["bw"]
        off, bx, bw = st["off"], st["bx"], st["bw"]
        pts = [q for x, y in st["base"] if off <= x <= off + bw for q in (bx + x - off, y)]
        if len(pts) >= 4:
            self.hb.coords(st["line"], *pts)

    def _order(self):
        """The strips under her bars always in one order: taps, pain, tap meter, hold panel (each packs itself on
        when it has something, so one that appears later would otherwise land after the rest)."""
        shown = [x for x in (self.hb, self.tp, self.pg, self.tm, self.vt, self.gp) if x.winfo_ismapped()]
        for x in shown:
            x.pack_forget()
        for x in shown:
            x.pack(fill="x", pady=(2, 0), before=self.state)

    def _show(self, canvas, on):
        if on and not canvas.winfo_ismapped():
            canvas.pack(fill="x", pady=(2, 0), before=self.state)
        elif not on and canvas.winfo_ismapped():
            canvas.pack_forget()

    def _tap_meter(self, f):
        """How near she is to tapping, under the pain gauges (window.hold_panel; a submission match, while she is
        held): five steps, filled to how near the tap check puts her, coloured from easy to the edge, with this
        beat's tap chance and what is keeping it there."""
        m = tap_meter(f)
        self._show(self.tm, bool(m))
        self._vitals(m.get("vitals") if m else None, f)
        if not m:
            return
        c, w = self.tm, self.app.card_w()
        c.delete("all")
        c.create_text(6, 9, anchor="w", text="Tap", font=("Segoe UI", 8, "bold"), fill=C("#111827"))
        x0, seg = 34, 30
        for i in range(1, 6):
            on = i <= m["level"]
            c.create_rectangle(x0 + (i - 1) * (seg + 3), 2, x0 + i * seg + (i - 1) * 3, 16,
                               fill=TAP_COLORS[i] if on else C("#ffffff"), outline=C("#9ca3af"))
        c.create_text(x0 + 5 * (seg + 3) + 6, 9, anchor="w", font=("Segoe UI", 8, "bold"),
                      fill=((DARK_TEXT.get(TAP_COLORS[max(1, m["level"])], TAP_COLORS[max(1, m["level"])])
                             if _THEME["dark"] else TAP_COLORS[max(1, m["level"])]) if m["level"] >= 3
                            else C("#111827")),
                      text=f"{m['label']}  ·  {pct_text(m['chance'])} chance this beat")
        note = c.create_text(6, 19, anchor="nw", font=("Segoe UI", 8), fill=C("#4b5563"), width=w - 12,
                             text=(f"{poss_word(m['by'])} {m['sub']}: pain {m['pain']} against what she can bear "
                                   f"{m['resist']}" + (f"  ·  {m['note']}" if m["note"] else "")))
        # (since build 286) as tall as its words: the longer notes were cut off at two lines
        c.configure(height=max(34, c.bbox(note)[3] + 3))

    def _vitals(self, v, f=None):
        """(since build 287) The constriction drawn: her heart rate and a trace of it (the beats spreading out as it
        slows, uneven once it skips), a bar of how much of her blood flow the coils have cut off, her blood
        pressure against a resting 120/80, and (since build 311) her breathing, which the heart monitor showed
        before the coils took its place. Rough numbers for the story, never rolled against."""
        self._show(self.vt, bool(v))
        if not v:
            return
        c, w = self.vt, self.app.card_w()
        c.delete("all")
        col = vitals_colour(v.get("blood", 0))
        if v.get("stopped"):
            col = "#ef4444"
        wcfg = (self.app._rules().get("window") or {}) if hasattr(self.app, "_rules") else {}
        figure = v.get("squeeze") is not None and wcfg.get("squeeze_figure", True)
        odds = blackout_text(v)
        # (since build 302) with the squeeze picture, side by side: the picture and her heart on the left, the monitor
        # and the readings to the right of them; without it, the monitor across the card as before
        ox = 168 if figure else 0
        ww = w - ox
        tips = self._explain_on()
        t1 = c.create_text(ox + 6, 12, anchor="w", text="♥ stopped" if v.get("stopped") else f"♥ {v['heart']}/min",
                           font=("Segoe UI", 9, "bold"), fill=col)
        heart_tip = explain.heart_text(v.get("heart", 0), v.get("heart_rest") or 100, v.get("irregular"),
                                       v.get("stopped"), True)
        self._tip(c, t1, heart_tip, tips)
        if v.get("irregular"):
            self._tip(c, c.create_text(ox + 6, 25, anchor="w", text="irregular", font=("Segoe UI", 7),
                                       fill="#fca5a5"), heart_tip, tips)
        if v.get("heart_rest"):
            # (since build 300) her healthy numbers, to read these against
            self._tip(c, c.create_text(ox + 6, 37, anchor="w", text=f"normal {v['heart_rest']}/min",
                                       font=("Segoe UI", 7), fill="#9ca3af"), heart_tip, tips)
        self._fig = None
        if not figure and v.get("squeeze") is not None:
            # (since build 294) how far the coils have squeezed her in: her chest or belly as a band narrowing from
            # both sides, the coils across it
            full, body, bands = squeeze_shapes(v["squeeze"], v.get("coils"), 84, max(40, w - 84 - 96), 46, 10,
                                           ring=bool(v.get("ring")))
            sq_tip = explain.squeeze_text(v["squeeze"], v.get("where"), v.get("pressure"), v.get("girth"))
            self._tip(c, c.create_rectangle(*full, outline="#4b5563", dash=(2, 2)), sq_tip, tips)
            for b in bands:
                c.create_rectangle(*b, outline="#1f2937", fill="#3b82f6")       # the coils pressing in from outside
            c.create_rectangle(*body, outline="#60a5fa", width=1 if v.get("ring") else 2,   # her body, inside the coils
                               fill="#c08457" if v.get("where") != "back" else "#a16207")
            self._tip(c, c.create_text(6, 51, anchor="w", font=("Segoe UI", 8), fill="#f9fafb",
                                       text=squeeze_label(v)), sq_tip, tips)
        # (since build 312) the BP column as wide as its words really are, and the trace starting after her heart
        # rate, so neither runs off the card or into the other at a high display scaling
        bp = v.get("bp") or [120, 80]
        rw = max(80, max(tkfont.Font(font=fn).measure(t) for t, fn in (
            (f"BP {bp[0]}/{bp[1]}", ("Segoe UI", 9, "bold")), ("breath 00/min", ("Segoe UI", 9, "bold")),
            ("shallow · normal 00", ("Segoe UI", 7)), ("normal 120/80", ("Segoe UI", 7)))) + 2)
        sx = w - rw - 6
        bx = max(ox + 84, c.bbox(t1)[2] + 10)
        bw = max(40, sx - bx - 12)
        # (since build 293) the trace runs like a monitor's, at her own heart rate (window.vitals_animate): six seconds
        # of it, drawn twice end to end and slid along under a fixed window
        base = ecg_points(v["heart"], v.get("irregular"), bw, 22, 0, 2)
        base = base + [(x + bw, y) for x, y in base[1:]]
        line = c.create_line(*[q for x, y in base if x <= bw for q in (bx + x, y)], fill=col, width=1.5)
        self._tip(c, line, heart_tip, tips)
        self._ecg = {"base": base, "line": line, "bx": bx, "bw": bw, "off": 0.0}
        anim = ((self.app._rules().get("window") or {}).get("vitals_animate", True)
                if hasattr(self.app, "_rules") else True)
        if anim and not getattr(self, "_ecg_running", False):
            self._ecg_running = True
            self.after(60, self._ecg_tick)
        blood_tip = explain.blood_text(v.get("blood", 0), v.get("out_at"))
        for it in (c.create_rectangle(bx, 30, bx + bw, 40, outline="#4b5563", fill="#1f2937"),
                   c.create_rectangle(bx, 30, bx + bw * min(1.0, v.get("blood", 0) / 100.0), 40, outline="", fill=col),
                   c.create_text(bx + 4, 35, anchor="w", text=f"blood flow {v.get('blood', 0)}% cut off",
                                 font=("Segoe UI", 7), fill="#f9fafb")):
            self._tip(c, it, blood_tip, tips)
        if v.get("out_at") is not None:
            # (since build 302) her limit on the gauge: past this line she can black out (and her heart stop)
            lx = bx + bw * min(1.0, v["out_at"] / 100.0)
            c.create_line(lx, 26, lx, 44, fill="#f9fafb", width=2)
            c.create_text(lx, 25, anchor="s", text="limit", font=("Segoe UI", 6), fill="#f9fafb")
        bp_tip = explain.bp_text(bp, v.get("bp_rest") or (120, 80), True)
        self._tip(c, c.create_text(sx, 12, anchor="w", text=f"BP {bp[0]}/{bp[1]}", font=("Segoe UI", 9, "bold"),
                                   fill="#f9fafb" if bp[0] >= 90 else "#fca5a5"), bp_tip, tips)
        if v.get("bp_rest"):
            self._tip(c, c.create_text(sx, 23, anchor="w", text=f"normal {v['bp_rest'][0]}/{v['bp_rest'][1]}",
                                       font=("Segoe UI", 7), fill="#9ca3af"), bp_tip, tips)
        bar = c.create_rectangle(sx, 30, sx + rw, 40, outline="#4b5563", fill="#1f2937")
        self._tip(c, bar, bp_tip, tips)
        self._tip(c, c.create_rectangle(sx, 30, sx + rw * min(1.0, bp[0] / 160.0), 40, outline="", fill=col),
                  bp_tip, tips)
        c.create_line(sx + rw * 120 / 160.0, 28, sx + rw * 120 / 160.0, 42, fill="#9ca3af", dash=(2, 2))
        self._tip(c, c.create_text(sx + 3, 35, anchor="w", text="pressure", font=("Segoe UI", 7), fill="#f9fafb"),
                  bp_tip, tips)
        if f is not None:
            sg = body_signs(f, self._alive_cfg())
            br_tip = explain.breath_text(sg["breath"], sg["breath_rest"], sg["depth"], sg.get("words") or ())
            # (since build 312) each line placed under the one before it, as tall as it really is: at a high display
            # scaling the text is bigger than the fixed rows it used to sit on, and they ran into each other
            b1 = c.create_text(sx, c.bbox(bar)[3] + 4, anchor="nw", text=f"breath {sg['breath']}/min",
                               font=("Segoe UI", 9, "bold"), fill="#f9fafb" if sg["breath"] else "#fca5a5")
            b2 = c.create_text(sx, c.bbox(b1)[3], anchor="nw", font=("Segoe UI", 7), fill="#9ca3af",
                               text=("shallow · " if sg["depth"] < 0.6 and sg["breath"] else "") + f"normal {sg['breath_rest']}")
            self._tip(c, b1, br_tip, tips)
            self._tip(c, b2, br_tip, tips)
        # what is below the monitor starts under the lowest thing above it (the readings, the bars, the breath)
        low = max(c.bbox(i)[3] for i in c.find_all()) + 4
        if odds[0]:
            od = c.create_text(ox + 6, low, anchor="nw", text=odds[0], width=ww - 12, font=("Segoe UI", 8, "bold"),
                               fill=odds[1])
            self._tip(c, od, blood_tip, tips)
            low = c.bbox(od)[3] + 4
        if figure:
            self._squeeze_figure(c, v, w, ox, low)
        c.configure(height=max(150 if figure else 0, max(c.bbox(i)[3] for i in c.find_all()) + 6))

    def _status_tip(self, e):
        f = self.data or {}
        if not self._explain_on() or not f:
            return
        import textwrap
        text = explain.statuses_text(f.get("status") or {}, self.app._rules() if hasattr(self.app, "_rules") else {})
        self.app.tip.show(e.x_root, e.y_root, "\n".join("\n".join(textwrap.wrap(p, 70)) for p in text.split("\n")))

    def _explain_on(self):
        """window.explain (since build 312): hover tips on her statuses and her vitals."""
        return bool(((self.app._rules().get("window") or {}) if hasattr(self.app, "_rules") else {})
                    .get("explain", True))

    def _tip(self, c, item, text, on=True):
        """A hover tip on one canvas item (window.explain)."""
        if not on or not text:
            return
        import textwrap
        wrapped = "\n".join("\n".join(textwrap.wrap(p, 70)) or "" for p in text.split("\n"))
        c.tag_bind(item, "<Enter>", lambda e, t=wrapped: self.app.tip.show(e.x_root, e.y_root, t))
        c.tag_bind(item, "<Leave>", lambda e: self.app.tip.hide())

    def _squeeze_figure(self, c, v, w, ox=200, ry=66):
        """window.squeeze_figure (since build 299): under the monitor, the squeeze as a picture: her torso from the
        front in her own colours, the coiler's loops wound round it (as thick as the coiler is big against her; only the coils on her, not the rest of the coiler),
        pressing her in, her ribs showing once it is crushing, her body paling as the blood is cut off; and beside it
        her heart, beating at her rate (window.vitals_animate), squeezed from the sides when the coils are on her
        chest, smaller as it fills less, still once it stops."""
        y0 = 8
        them = (getattr(self.app, "cards", None) or {}).get(v.get("coiler"))
        body, belly = picture_colours(self.book, "#c08457")
        coil = picture_colours(getattr(them, "book", None), "#5d8fcf")[0]
        col = squeeze_colours(v, body, coil, belly)
        where = v.get("where") if v.get("where") in ("chest", "belly", "both") else "chest"
        fg = squeeze_figure(v["squeeze"], where, v.get("coils"), 2, y0, 84, 140, v.get("coil_ratio"))
        c.create_polygon(*[q for p in fg["head"] for q in p], fill=col["body"], outline=col["body_edge"], smooth=True)
        c.create_polygon(*[q for p in fg["body"] for q in p], fill=col["body"], outline=col["body_edge"])
        for sh in fg["shade"]:
            c.create_polygon(*[q for p in sh for q in p], fill=col["shade"], outline="")
        c.create_polygon(*[q for p in fg["belly"] for q in p], fill=col["belly"], outline="", smooth=True)
        for r in fg["ribs"]:
            c.create_line(*[q for p in r for q in p], fill=col["rib"], width=1, smooth=True)
        for a in fg["arms"] + fg["paws"]:
            c.create_polygon(*[q for p in a for q in p], fill=col["arm"], outline=col["body_edge"])
        for cr in fg["creases"]:
            c.create_line(*[q for p in cr for q in p], fill=col["crease"], width=1, smooth=True)
        for lp in fg["loops"]:
            c.create_polygon(*[q for p in lp["poly"] for q in p], fill=col["coil"], outline=col["coil_edge"])
            c.create_polygon(*[q for p in lp["dark"] for q in p], fill=col["coil_dark"], outline="")
            c.create_line(*[q for p in lp["shine"] for q in p], fill=col["coil_shine"], width=2, smooth=True)
        # her heart, on its own, beside her
        hx, hy, hr = 132, y0 + 64, 20
        on_chest = where in ("chest", "both")
        hs = heart_shapes(hx, hy, hr, v["squeeze"], on_chest, v.get("blood", 0), 0.0, bool(v.get("stopped")))
        for pr in hs["press"]:
            c.create_polygon(*[q for p in pr for q in p], fill=col["coil"], outline=col["coil_edge"])
        dark = mix(col["heart"], "#000000", 0.3)
        items = {"vessels": [c.create_line(*[q for p in pts for q in p], fill=dark, width=wd, capstyle="round")
                             for pts, wd in hs["vessels"]],
                 "heart": c.create_polygon(*[q for p in hs["heart"] for q in p], fill=col["heart"],
                                           outline=mix(col["heart"], "#000000", 0.5), smooth=True),
                 "split": c.create_line(*[q for p in hs["split"] for q in p], fill=dark, smooth=True),
                 "shine": c.create_line(*[q for p in hs["shine"] for q in p], fill=mix(col["heart"], "#ffffff", 0.5),
                                        width=2, smooth=True)}
        self._fig = {"items": items, "args": (hx, hy, hr, v["squeeze"], on_chest, v.get("blood", 0)),
                     "heart": 0 if v.get("stopped") else v.get("heart", 0), "irregular": bool(v.get("irregular")),
                     "stopped": bool(v.get("stopped"))}
        # how tight, in words and real-world numbers (cards.squeeze_readout, shared with exported fights)
        tips = self._explain_on()
        sq_tip = explain.squeeze_text(v["squeeze"], v.get("where"), v.get("pressure"), v.get("girth"))
        # (since build 312) the rows are pushed down as far as the ones above them really reach: at a high display
        # scaling the text is taller than the rows squeeze_readout spaces it on (and a long line wraps)
        shift, low, row_y = 0.0, -1e9, None
        for sh in squeeze_readout(v, ox + 6, ry, max(60, w - ox - 12)):
            top = sh[2] if sh[0] == "text" else min(sh[2], sh[4])
            if sh[0] != "line" and top != row_y:
                row_y = top
                if top + shift < low + 2:
                    shift = low + 2 - top
            dy = shift
            if sh[0] == "text":
                _, tx, ty, text, colr, size, bold = sh
                it = c.create_text(tx, ty + dy, anchor="nw", width=max(60, w - tx - 6), text=text, fill=colr,
                                   font=("Segoe UI", size, "bold" if bold else "normal"))
                self._tip(c, it, sq_tip, tips)
                low = max(low, c.bbox(it)[3])
            elif sh[0] == "rect":
                _, a, b, c2, d2, fill, stroke = sh
                low = max(low, c.bbox(c.create_rectangle(a, b + dy, c2, d2 + dy, fill=fill, outline=stroke))[3])
            else:
                _, a, b, c2, d2, colr, dashed = sh
                c.create_line(a, b + dy, c2, d2 + dy, fill=colr, width=1.5, dash=(2, 2) if dashed else None)

    def _heart_tick(self):
        """One step of the beating heart in the squeeze figure (driven by _ecg_tick)."""
        fg = getattr(self, "_fig", None)
        if not fg:
            return
        import time as _time
        beat = heart_beat(fg["heart"], _time.monotonic(), fg["irregular"])
        hs = heart_shapes(*fg["args"], beat=beat, stopped=fg["stopped"])
        it, c = fg["items"], self.vt
        c.coords(it["heart"], *[q for p in hs["heart"] for q in p])
        c.coords(it["split"], *[q for p in hs["split"] for q in p])
        c.coords(it["shine"], *[q for p in hs["shine"] for q in p])
        for item, (pts, _) in zip(it["vessels"], hs["vessels"]):
            c.coords(item, *[q for p in pts for q in p])

    def _ecg_tick(self):
        """One step of the moving heart trace: slide it on by as far as 60 ms of six seconds takes it, and keep going
        while the strip is shown."""
        st = getattr(self, "_ecg", None)
        try:
            if not st or not self.vt.winfo_ismapped():
                self._ecg_running = False
                return
            st["off"] = (st["off"] + st["bw"] * 0.06 / 6.0) % st["bw"]
            off, bx, bw = st["off"], st["bx"], st["bw"]
            pts = [q for x, y in st["base"] if off <= x <= off + bw for q in (bx + x - off, y)]
            if len(pts) >= 4:
                self.vt.coords(st["line"], *pts)
            self._heart_tick()
            self.after(60, self._ecg_tick)
        except tk.TclError:
            self._ecg_running = False     # (the card was closed or redrawn: the next strip starts its own)

    def _holds(self, f):
        """window.hold_picture (since build 304): the grips on her as a picture beside their gauges (cards.hold_shapes):
        each grip drawn on her body by what it does to her (a joint forced, her neck choked, her body crushed, her
        head clamped, a limb bound, a grab, a pin bearing down), in the holder's colours."""
        wcfg = (self.app._rules().get("window") or {}) if hasattr(self.app, "_rules") else {}
        shapes, hh = [], 0
        if wcfg.get("hold_picture", True):
            cards_ = getattr(self.app, "cards", None) or {}
            gr = f.get("grips") or {}
            who = {g.get("by") for g in gr.get("held") or ()} | ({(gr.get("pin") or {}).get("by")} - {None})
            holders = {n: picture_colours(getattr(cards_.get(n), "book", None), "#5d8fcf")[0] for n in who}
            body, belly = picture_colours(self.book, "#c08457")
            shapes, hh = hold_shapes(f, 4, 6, 90, 150, 108, self.app.card_w() - 114, body, belly, holders)
        self._show(self.hd, bool(shapes))
        if not shapes:
            return
        c = self.hd
        c.delete("all")
        c.configure(height=int(hh) + 4)
        for sh in shapes:
            if sh[0] == "poly":
                c.create_polygon(*[q for p in sh[1] for q in p], fill=sh[2] or "", outline=sh[3] or "",
                                 width=sh[4] or 1)
            elif sh[0] == "line":
                c.create_line(*[q for p in sh[1] for q in p], fill=sh[2], width=sh[3], capstyle="round",
                              joinstyle="round")
            elif sh[0] == "rect":
                c.create_rectangle(sh[1], sh[2], sh[3], sh[4], fill=sh[5] or "", outline=sh[6] or "")
            else:
                c.create_text(sh[1], sh[2], anchor="nw", text=sh[3], fill=sh[4], width=self.app.card_w() - sh[1] - 6,
                              font=("Segoe UI", sh[5], "bold" if sh[6] else "normal"))

    def _grips(self, f):
        """The hold panel: who holds which of her parts and with what, the grips she has, a pin's count, and how
        far she is from each other fighter (window.hold_panel)."""
        lines = grip_lines(f)
        self._show(self.gp, bool(lines))
        if not lines:
            return
        c, w = self.gp, self.app.card_w()
        c.delete("all")
        y = 2
        for text, col in lines:
            t = c.create_text(6, y, anchor="nw", text=text, fill=C(col), width=w - 12,
                              font=("Segoe UI", 8, "bold" if text.startswith(("Held", "Pinned by")) else "normal"))
            y = c.bbox(t)[3] + 2
        c.configure(height=y + 2)

    def _pain(self, f):
        """The two pain gauges under her energy bar (window.pain_gauge): overall (what she feels now: blows sting and
        fade) and the part being held, pinned or struck this beat. Each a share of what she can bear: the full width
        is 150%, with a dashed mark at 100%."""
        g = f.get("pain")
        if not g:
            if self.pg.winfo_ismapped():
                self.pg.pack_forget()
            return
        if not self.pg.winfo_ismapped():
            self.pg.pack(fill="x", pady=(2, 0), before=self.state)
        c, w = self.pg, self.app.card_w()
        c.delete("all")

        def bar(y, x, text):
            share = max(0.0, float(x.get("pct") or 0))
            col = C("#a3a3a3") if share < 40 else C("#f59e0b") if share < 70 else C("#ea580c") if share < 100 else C("#b91c1c")
            c.create_rectangle(0, y, w * min(1.0, share / 150.0), y + 16, fill=col, outline="")
            c.create_line(w * 100 / 150.0, y, w * 100 / 150.0, y + 16, fill=C("#111827"), dash=(2, 2))
            halo_text(c, 6, y + 8, anchor="w", font=("Segoe UI", 8, "bold"), text=text, fill=C("#111827"))

        o, pt = g.get("overall") or {}, g.get("part")
        bar(0, o, f"Pain {o.get('shown') or str(o.get('pct', 0)) + '%'}: {o.get('label', '')}"
                  + (f"  ({o['where']})" if o.get("where") else ""))
        if pt:
            parts = ", ".join(str(p).lower() for p in pt.get("parts") or [])
            bar(18, pt, f"{parts.capitalize() or 'Part'} {pt.get('shown') or str(pt.get('pct', 0)) + '%'}: {pt.get('label', '')}"
                        + (f"  ({pt['why']})" if pt.get("why") else "")
                        + (f"  · {'blood flow' if pt.get('circ') else 'air'} {pt['air']}% "
                           f"{'cut off' if pt.get('circ') else 'gone'}" if pt.get("air") is not None else ""))
        else:
            c.create_text(6, 26, anchor="w", font=("Segoe UI", 8), fill=C("#6b7280"),
                          text="nothing held or struck this beat")

    def _fit_width(self):
        """(since build 273) every bar under the picture as wide as the card at its size (the Cards − / + buttons)."""
        w = self.app.card_w()
        for cv in (self.hp, self.en, self.hb, self.tp, self.pg, self.tm, self.vt, self.gp):
            if int(float(cv.cget("width"))) != w:
                cv.configure(width=w)
        self.state.configure(wraplength=w)

    def _bars(self, f, pct):
        self._fit_width()
        w = self.app.card_w()
        self.hp.delete("all")
        share = max(0.0, min(1.0, pct / 100.0))
        col = C("#22c55e") if pct >= 60 else C("#eab308") if pct >= 35 else C("#f97316") if pct >= 15 else C("#ef4444")
        self.hp.create_rectangle(0, 0, w * share, 18, fill=col, outline="")
        halo_text(self.hp, 6, 9, anchor="w", text=f"Health {f['health']:.0f}%   ({pct:.0f}% of full)",
                            font=("Segoe UI", 9, "bold"), fill=C("#111827"))
        self.en.delete("all")
        self.en.create_rectangle(0, 0, w * max(0.0, min(1.0, f["energy"] / 100.0)), 10, fill=C("#60a5fa"), outline="")
        halo_text(self.en, 6, 5, anchor="w", text=f"energy {f['energy']:.0f}", font=("Segoe UI", 7), fill=C("#111827"))
        sts = ", ".join(f"{k.replace('_', ' ')} ({v})" if isinstance(v, (int, float)) and not isinstance(v, bool) else
                        k.replace("_", " ") for k, v in f["status"].items()) or "no statuses"
        self.state.configure(text=f"{f['posture']}  ·  {sts}")
        self._monitor(f)
        self._taps(f)
        self._pain(f)
        self._tap_meter(f)
        self._holds(f)
        self._grips(f)
        self._order()

    def draw_one(self, f):
        """Without Pillow (or before her pictures are in): one picture, every part on it."""
        self.data = f
        pct = 100.0 * f["health"] / f["max"]
        self.head.configure(text=f["name"] + ("   — OUT" if f["out"] else ""))
        self.sub.configure(text=f"{f['species']}  ·  {' / '.join(f['types'])}")
        spots = self.anchors(f)
        self._rings, self._grip_cols = [], self._grip_colours(f)
        self._alive_setup(f, [])
        left, right = columns(f, spots, self.rect)
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
            c.create_oval(COL + 50, top + 50, COL + PIC - 50, top + PIC - 50, fill=C("#e5e7eb"), outline="")
            c.create_text(COL + PIC / 2, top + PIC / 2, text=(f["species"] or f["name"])[:12],
                          font=("Segoe UI", 16, "bold"), fill=C("#6b7280"))
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
            ys = spread([top + spots[p[0]][1] for p in rows], H)
            for (part, dmg, res), ly in zip(rows, ys):
                x, y = spots[part]
                ax, ay = COL + x, top + y
                lx = COL - 4 if side == "L" else COL + PIC + 4
                calib = self.app.calib == (self, part)
                line = C("#2563eb") if calib else C("#9ca3af")
                c.create_line(lx, ly, ax, ay, fill=line, width=2 if calib else 1)
                c.create_oval(ax - 3, ay - 3, ax + 3, ay + 3, fill=dmg_color(dmg), outline=C("#111827"))
                self._ring(c, f, part, ax, ay)
                self._label(c, side, lx, ly, part, dmg, res, calib)
        if f["out"]:
            c.create_text(COL + PIC / 2, top + 14, text="OUT", font=("Segoe UI", 14, "bold"), fill=C("#991b1b"))
        if self.app.calib and self.app.calib[0] is self:
            c.create_text(COL + PIC / 2, H - 8, text=f"click the picture where her {self.app.calib[1].lower()} is",
                          font=("Segoe UI", 8, "italic"), fill=C("#2563eb"))
        # health and energy
        w = PIC + 2 * COL
        self.hp.delete("all")
        share = max(0.0, min(1.0, pct / 100.0))
        col = C("#22c55e") if pct >= 60 else C("#eab308") if pct >= 35 else C("#f97316") if pct >= 15 else C("#ef4444")
        self.hp.create_rectangle(0, 0, w * share, 18, fill=col, outline="")
        halo_text(self.hp, 6, 9, anchor="w", text=f"Health {f['health']:.0f}%   ({pct:.0f}% of full)",
                            font=("Segoe UI", 9, "bold"), fill=C("#111827"))
        self.en.delete("all")
        self.en.create_rectangle(0, 0, w * max(0.0, min(1.0, f["energy"] / 100.0)), 10, fill=C("#60a5fa"), outline="")
        halo_text(self.en, 6, 5, anchor="w", text=f"energy {f['energy']:.0f}", font=("Segoe UI", 7), fill=C("#111827"))
        sts = ", ".join(f"{k.replace('_', ' ')} ({v})" if isinstance(v, (int, float)) and not isinstance(v, bool) else
                        k.replace("_", " ") for k, v in f["status"].items()) or "no statuses"
        self.state.configure(text=f"{f['posture']}  ·  {sts}")
        self._monitor(f)
        self._taps(f)
        self._pain(f)
        self._tap_meter(f)
        self._holds(f)
        self._grips(f)
        self._order()

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
                                   fill=C("#2563eb") if calib else C("#111827")))
        order = (1, 2) if side == "L" else (1, 2)
        bx = x + widths[0] if side == "L" else x + widths[0]
        if side == "R":
            bx = x + widths[0]
        fill = dmg_color(dmg)
        items.append(c.create_rectangle(bx, ly - 7, bx + widths[1] - 2, ly + 7, fill=fill, outline=""))
        items.append(c.create_text(bx + (widths[1] - 2) / 2, ly, text=d, fill=text_on(fill), font=("Segoe UI", 7, "bold")))
        rx = bx + widths[1]
        items.append(c.create_rectangle(rx, ly - 7, rx + widths[2] - 2, ly + 7, fill=C("#ffffff"), outline=res_color(res),
                                        width=2))
        items.append(c.create_text(rx + (widths[2] - 2) / 2, ly, text=r, fill=C("#111827"), font=("Segoe UI", 7)))
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
        if self.panels:
            return self._clicked_panel(e)
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


    def _clicked_panel(self, e):
        """A click on one of her pictures while a part is picked: its point goes there, on that picture (so a part
        clicked onto the back picture moves to the back, and the other way round)."""
        pn = next((q for q in self.panels if q["oy"] <= e.y <= q["oy"] + q["size"]
                   and q["ox"] <= e.x <= q["ox"] + q["size"]), None)
        if pn is None:
            return
        part = self.app.calib[1]
        rx, ry, rw, rh = pn["rect"]
        x, y = e.x - pn["ox"], e.y - pn["oy"]
        book = load_anchors()
        book.setdefault(pn["key"], {})[part] = [round((x - rx) / max(1, rw), 4), round((y - ry) / max(1, rh), 4)]
        for q in self.panels:
            if q is not pn and self.book is not None:
                base = self.book.base(q["view"])
                for k in {q["key"], base[2] if base else None} - {None, pn["key"]}:
                    (book.get(k) or {}).pop(part, None)       # it lives on one picture at a time
        save_anchors(book)
        self.app.calib = None
        self.draw(self.data)


class App:
    def __init__(self, args):
        self.root = tk.Tk()
        _keep_alive(self)
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
        self.root.report_callback_exception = lambda *exc: self.show_error(
            "".join(__import__("traceback").format_exception(*exc)))
        self.root.after(50, self.pump)

    def _dark_style(self, style):
        """window.dark: the ttk widgets (frames, labels, switches, buttons, the entry, the scrollbars) and the plain
        Tk ones in dark colours."""
        bg, field, fg, line, hi = "#17181e", "#252732", "#e5e7eb", "#3a3d4a", "#33364a"
        self.root.configure(bg=bg)
        style.configure(".", background=bg, foreground=fg, fieldbackground=field, bordercolor=line,
                        darkcolor=bg, lightcolor=line, troughcolor=field, insertcolor=fg, selectbackground=hi,
                        selectforeground=fg)
        for w in ("TFrame", "TLabel", "TCheckbutton", "TPanedwindow"):
            style.configure(w, background=bg, foreground=fg)
        style.map("TCheckbutton", background=[("active", hi)], indicatorbackground=[("selected", "#60a5fa"),
                                                                                   ("!selected", field)])
        style.configure("TCheckbutton", indicatorbackground=field, indicatorforeground=bg)
        style.configure("TButton", background=field, foreground=fg)
        style.map("TButton", background=[("pressed", line), ("active", hi)])
        style.configure("TEntry", fieldbackground=field, foreground=fg, insertcolor=fg)
        style.configure("Vertical.TScrollbar", background=field, troughcolor=bg, arrowcolor=fg)
        style.configure("Horizontal.TScrollbar", background=field, troughcolor=bg, arrowcolor=fg)
        style.configure("Horizontal.TScale", background=field, troughcolor=bg)
        style.configure("Sash", background=line)
        # (since build 290) the Profiles window's tabs
        style.configure("TNotebook", background=bg, bordercolor=line)
        style.configure("TNotebook.Tab", background=field, foreground=fg, bordercolor=line, lightcolor=line)
        style.map("TNotebook.Tab", background=[("selected", hi), ("active", line)], foreground=[("selected", fg)])
        for opt, val in (("*Background", bg), ("*Foreground", fg), ("*Canvas.Background", bg),
                         ("*selectBackground", hi), ("*insertBackground", fg)):
            self.root.option_add(opt, val)

    # ---- layout ----
    def _build(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        _THEME["dark"] = dark_on(self._rules())
        if _THEME["dark"]:
            self._dark_style(style)
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
        o = opts_of(self._rules())
        self.back_view = _Flag(value=bool(o.get("back_view", True)))
        self.weak_look = _Flag(value=bool(o.get("weak_look", True)))
        self.damage_marks = _Flag(value=bool(o.get("damage_marks", True)))
        self.poses = _Flag(value=bool(o.get("poses", True)))
        self.follow = _Flag(value=True)
        # (since build 273) the cards' size, so both fit on one screen (window.card_zoom, kept between runs)
        try:
            self.card_zoom = max(0.4, min(1.6, float((self._rules().get("window") or {}).get("card_zoom", 1.0) or 1.0)))
        except (TypeError, ValueError):
            self.card_zoom = 1.0
        zoom_box = ttk.Frame(top)
        zoom_box.pack(side="right", padx=(8, 0))
        ttk.Button(zoom_box, text="Cards −", width=7, command=lambda: self.zoom_cards(-0.1)).pack(side="left")
        self.zoom_label = ttk.Label(zoom_box, text=f"{self.card_zoom * 100:.0f}%", width=5, anchor="center")
        self.zoom_label.pack(side="left")
        ttk.Button(zoom_box, text="Cards +", width=7, command=lambda: self.zoom_cards(0.1)).pack(side="left")
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
            tk.Label(legend, text=" " + n.split(" ")[0] + " ", bg=C("#ffffff"), fg=C("#111827"), font=("Segoe UI", 7),
                     highlightbackground=c, highlightthickness=2).pack(side="left", padx=1)
        # (since build 307) the picture switches on a row of their own under the legend (on the bar above they
        # pushed the beat arrows off it), with the Effects button
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(3, 0))
        ttk.Checkbutton(row, text="Weakened look", variable=self.weak_look, command=self.redraw_cards).pack(side="left")
        ttk.Checkbutton(row, text="Back view", variable=self.back_view, command=self.redraw_cards).pack(side="left")
        ttk.Checkbutton(row, text="Damage marks", variable=self.damage_marks, command=self.redraw_cards).pack(side="left")
        ttk.Checkbutton(row, text="Poses", variable=self.poses, command=self.redraw_cards).pack(side="left")
        # (since build 307) the living cards' pieces and the settling-in notes on or off (play.EFFECTS, as /effects)
        self.effects_btn = ttk.Menubutton(row, text="Effects")
        menu = tk.Menu(self.effects_btn, tearoff=False, postcommand=self._sync_effects)
        self.effects_btn["menu"] = menu
        self.effect_flags = {}
        names = {"all": "All of them", "breathing": "Breathing", "pulse": "Pain pulsing with her heart",
                 "impact": "Blows: flash and jolt", "grey": "The grey closing in", "grips": "Grip rings in the holder's "
                 "colours", "monitor": "Heart monitor", "settling": "Injuries settling in (the story)"}
        for k, on in play.effects_state(self._rules()):
            self.effect_flags[k] = _Flag(value=on)
            menu.add_checkbutton(label=names.get(k, k), variable=self.effect_flags[k],
                                 command=lambda k=k: self.effect_changed(k))
            if k == "all":
                menu.add_separator()
        self.effects_btn.pack(side="left", padx=(10, 0))

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

        # above the story: the switches for the numbers, their pointers, and the text size (rules.json window.text)
        to = textpane.opts(self._rules())
        if to.get("unwrap", True):
            display.WRAP_WIDTH = 0      # (the pane wraps the stat lines itself, indented under their start)
        self.pointers = textpane.Pointers(self._rules())
        self.font_size = int(to.get("font_size", 12) or 12)
        bar = ttk.Frame(right)
        bar.pack(side="top", fill="x", pady=(0, 4))
        self.show_numbers = _Flag(value=bool(to.get("numbers", True)))
        self.show_pointers = _Flag(value=str(to.get("pointers", "occasional")).lower() not in ("off", "false", "none"))
        ttk.Label(bar, text="The story", font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Button(bar, text="A+", width=3, command=lambda: self.text_size(1)).pack(side="right")
        ttk.Button(bar, text="A−", width=3, command=lambda: self.text_size(-1)).pack(side="right")
        ttk.Checkbutton(bar, text="Pointers (where the numbers come from)", variable=self.show_pointers,
                        command=self.text_switches).pack(side="right", padx=4)
        ttk.Checkbutton(bar, text="Numbers", variable=self.show_numbers,
                        command=self.text_switches).pack(side="right", padx=4)
        self.show_progress = _Flag(value=bool(to.get("progress", True)))
        ttk.Checkbutton(bar, text="Progress", variable=self.show_progress,
                        command=self.text_switches).pack(side="right", padx=4)
        self.text = tk.Text(right, wrap="word", font=("Georgia", 11), padx=12, pady=8, undo=False,
                            background=C("#fffdf8"), foreground=C("#1f2937"),
                            insertbackground=C("#1f2937"), highlightthickness=0)
        tsb = ttk.Scrollbar(right, orient="vertical",
                            command=lambda *a: (self.text.yview(*a), self.user_scroll()))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Prior>", "<Next>", "<Up>", "<Down>"):
            self.text.bind(ev, self.user_scroll, add="+")
        self.text.configure(yscrollcommand=lambda a, b: (tsb.set(a, b), self.scrolled()))
        bottom = ttk.Frame(right)
        bottom.pack(side="bottom", fill="x", pady=(6, 0))
        tsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self._glyph_tags, self._indent_tags = set(), set()
        self.style_text()
        if to.get("hover", True):
            self.text.tag_bind("term", "<Enter>", self.term_tip)
            self.text.tag_bind("term", "<Motion>", self.term_tip)
            self.text.tag_bind("term", "<Leave>", lambda _e: self.tip.hide())
        self.text.configure(state="disabled")

        self.prompt = ttk.Label(bottom, text=">", font=("Consolas", 10, "bold"))
        self.prompt.pack(side="left")
        self.entry = ttk.Entry(bottom, font=("Consolas", 11))
        self.entry.pack(side="left", fill="x", expand=True, padx=4)
        self.entry.bind("<Return>", self.send)
        ttk.Button(bottom, text="Next beat", command=lambda: self.send_line("")).pack(side="left", padx=2)
        ttk.Button(bottom, text="Auto 5", command=lambda: self.send_line("/auto 5")).pack(side="left", padx=2)
        ttk.Button(bottom, text="Undo", command=lambda: self.send_line("/undo")).pack(side="left", padx=2)
        ttk.Button(bottom, text="Export", command=lambda: self.send_line("/exportfight")).pack(side="left", padx=2)
        ttk.Button(bottom, text="Profiles", command=self.open_profiles).pack(side="left", padx=2)
        self.entry.focus_set()

    # ---- input ----
    def send(self, _e=None):
        line = self.entry.get()
        self.entry.delete(0, "end")
        self.send_line(line)

    # ---- profiles (since build 281): personality, history and relationships, one tab per fighter ----
    def open_profiles(self):
        """A window with a tab for each fighter in the fight: her personality, her history and what each of the
        others is to her (editable; Save writes them to fighters.json and the story uses them from the next beat),
        and her traits, quirks and style to read."""
        sess = getattr(self.game, "session", None)
        eng = getattr(sess, "eng", None)
        if eng is None:
            return
        top = tk.Toplevel(self.root, bg=C("#fffdf8"))
        top.title("Profiles")
        top.geometry("760x620")
        _keep_alive(top)       # (closed windows are kept: a Tk object freed off the main thread kills Spyder)
        book = ttk.Notebook(top)
        book.pack(fill="both", expand=True, padx=6, pady=6)
        fighters = [f for f in eng.fighters.values()]
        boxes = {}

        def area(parent, label, text, height):
            ttk.Label(parent, text=label, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 0))
            t = tk.Text(parent, height=height, wrap="word", font=("Segoe UI", 10), bg=C("#ffffff"), fg=C("#111827"),
                        insertbackground=C("#111827"))
            t.insert("1.0", text or "")
            t.pack(fill="x")
            return t
        for f in fighters:
            tab = ttk.Frame(book, padding=8)
            book.add(tab, text=f.name)
            b = {"personality": area(tab, "Personality", f.personality, 4),
                 "history": area(tab, "History", f.history, 4), "rel": {}}
            vet = _Flag(top, value=bool(f.veteran))
            ttk.Checkbutton(tab, text="Has fought before (may remember it)", variable=vet).pack(anchor="w")
            b["veteran"] = vet
            for o in fighters:
                if o is not f:
                    b["rel"][o.name] = area(tab, f"{o.name}, to her", (f.relationships or {}).get(o.name, ""), 2)
            tr = ", ".join(f"{k} ×{v:g}" for k, v in (f.traits or {}).items() if float(v) != 1.0) or "all as normal"
            info = (f"Traits: {tr}\nQuirks: {', '.join(f.quirks or []) or 'none'}"
                    + (f"\nStyle: {f.style}" if f.style else ""))
            ttk.Label(tab, text=info, wraplength=700, justify="left").pack(anchor="w", pady=(8, 0))
            boxes[f.name] = b

        def save():
            try:
                path = os.path.join(os.path.dirname(os.path.abspath(play.__file__)), "fighters.json")
                with open(path, encoding="utf-8") as fh:
                    raw = json.load(fh)
                roster = raw if isinstance(raw, list) else raw.get("fighters", raw)
                entries = roster.values() if isinstance(roster, dict) else roster
                for f in fighters:
                    b = boxes[f.name]
                    f.personality = b["personality"].get("1.0", "end").strip()
                    f.history = b["history"].get("1.0", "end").strip()
                    f.veteran = bool(b["veteran"].get())
                    for o, t in b["rel"].items():
                        v = t.get("1.0", "end").strip()
                        if v:
                            f.relationships[o] = v
                        else:
                            f.relationships.pop(o, None)
                    for x in entries:
                        if isinstance(x, dict) and x.get("name") == f.name:
                            x["personality"], x["history"], x["veteran"] = f.personality, f.history, f.veteran
                            x["relationships"] = dict(f.relationships)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(raw, indent=2, ensure_ascii=False) + "\n")
                status.configure(text="Saved to fighters.json: the story uses it from the next beat.")
            except Exception as e:
                note_failure("saving the profiles to fighters.json", e)
                status.configure(text=f"Couldn't save: {e}")
        bar = ttk.Frame(top)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(bar, text="Save", command=save).pack(side="right")
        status = ttk.Label(bar, text="")
        status.pack(side="left")

    def send_line(self, line):
        if line.strip().lower() in ("/stop", "stop") and not getattr(self.game, "waiting", True):
            # busy with /auto or /autofight: it ends after the beat being written (play.STOP), nothing is queued
            play.STOP.set()
            self.out_q.put(("text", "\n[/stop: the run ends once this beat is finished]\n"))
            return
        self.in_q.put(line)
        self.prompt.configure(text="…")

    def close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.in_q.put(None)
        self.root.destroy()

    # ---- output ----
    def pump(self):
        try:
            self._pump()
        except Exception:
            import traceback
            self.show_error(traceback.format_exc())
        finally:
            if not getattr(self, "_closed", False):
                try:
                    self.root.after(60, self.pump)
                except Exception:
                    pass

    def show_error(self, tb):
        """A drawing error is shown in the story pane instead of quietly stopping the window."""
        try:
            self.text.configure(state="normal")
            self.text.insert("end", "\n[window error, the game goes on]\n" + tb + "\n", "progress")
            self.text.configure(state="disabled")
            self.text.see("end")
        except Exception:
            pass

    def _pump(self):
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
                    if self.follow.get():
                        self.set_slider(len(self.beats) + 1)
                        self.show(data, live=True)
                    else:
                        self.slider.configure(to=len(self.beats) + 1)
                elif kind == "rebuild":
                    self.rebuild(*data)
                elif kind == "live":
                    self.live = data
                    if self.follow.get():
                        self.show(data, live=True)
                elif kind == "done":
                    self.flush_pending()
                    self.prompt.configure(text="(the game has ended: close the window)")
        except queue.Empty:
            pass

    def add_text(self, t):
        self.pending += t
        if "\n" in self.pending:
            done, self.pending = self.pending.rsplit("\n", 1)
            self.write_lines(done + "\n")

    def flush_pending(self):
        if self.pending:
            self.write_lines(self.pending)
            self.pending = ""

    def style_text(self):
        """The story pane's look, at the current text size: the story in a reading face with room between
        paragraphs, the numbers in a shaded block in a fixed face, their rows coloured by what they measure (damage
        red, resistance blue, health green), the pointers in a band of their own under them."""
        fs, t = self.font_size, self.text
        mono = max(7, fs - 3)
        t.configure(font=("Georgia", fs))
        t.tag_configure("story", font=("Georgia", fs), spacing1=1, spacing3=3, lmargin1=4, lmargin2=4)
        t.tag_configure("gap", font=("Georgia", max(4, fs // 2)))
        t.tag_configure("bold", font=("Georgia", fs, "bold"))
        t.tag_configure("italic", font=("Georgia", fs, "italic"), foreground=C("#7c3aed"))
        t.tag_configure("pov", font=("Georgia", fs + 1, "bold"), foreground=C("#b45309"), spacing1=10, spacing3=4)
        shade = C("#f3f5f9")
        t.tag_configure("mech", font=("Consolas", mono), foreground=C("#4b5563"), background=shade)
        t.tag_configure("head", font=("Consolas", mono + 1, "bold"), foreground=C("#111827"), background=shade,
                        spacing1=6)
        t.tag_configure("part", font=("Consolas", mono, "bold"), foreground=C("#111827"), background=shade, spacing1=3)
        t.tag_configure("total", font=("Consolas", mono, "bold"), foreground=C("#111827"), background=C("#e8ecf3"),
                        spacing1=2, spacing3=2)
        t.tag_configure("mechbold", font=("Consolas", mono, "bold"), foreground=C("#111827"), background=shade)
        for tag, col in (("dmg", C("#b91c1c")), ("res", C("#1d4ed8")), ("hp", C("#047857"))):
            t.tag_configure(tag, foreground=col)
            t.tag_configure(tag + "bold", foreground=col, font=("Consolas", mono, "bold"))
        t.tag_configure("hit", foreground=C("#15803d"), font=("Consolas", mono, "bold"))
        t.tag_configure("miss", foreground=C("#6b7280"))
        t.tag_configure("pointer", font=("Segoe UI", max(7, fs - 2), "italic"), foreground=C("#0f766e"),
                        background=C("#ecfdf5"), lmargin1=28, lmargin2=44, rmargin=12, spacing1=1, spacing3=3)
        t.tag_configure("progress", font=("Segoe UI", max(7, fs - 3), "italic"), foreground=C("#9ca3af"))
        t.tag_configure("input", font=("Consolas", fs - 1, "bold"), foreground=C("#2563eb"), spacing1=6)
        t.tag_configure("rule", foreground=C("#d1d5db"))
        try:
            t.tag_configure("term", underline=True, underlinefg=C("#9ca3af"))
        except tk.TclError:     # (an older Tk: plain underline)
            t.tag_configure("term", underline=True)
        # a wrapped stat line goes on indented under its own start: one tag for each depth of indent
        try:
            from tkinter import font as tkfont
            self._char_w = tkfont.Font(family="Consolas", size=mono).measure("0") or 7
        except Exception as exc:
            note_failure("the story pane's character width", exc)
            self._char_w = 7
        for tag in self._indent_tags:
            n = int(tag[3:])
            t.tag_configure(tag, lmargin1=0, lmargin2=self._char_w * (n + 4))
        self.text_switches()

    def text_switches(self):
        """The Numbers and Pointers switches: hidden lines stay in the pane (the beat slider still finds them)."""
        self.text.tag_configure("numbers", elide=not self.show_numbers.get())
        self.text.tag_configure("progress_hide", elide=not self.show_progress.get())
        self.text.tag_configure("pointer_hide", elide=not (self.show_pointers.get() and self.show_numbers.get()))

    def text_size(self, d):
        self.font_size = max(8, min(22, self.font_size + d))
        self.style_text()

    def _indent_tag(self, line):
        n = textpane.indent_of(line)
        tag = f"ind{n}"
        if tag not in self._indent_tags:
            self._indent_tags.add(tag)
            self.text.tag_configure(tag, lmargin1=0, lmargin2=self._char_w * (n + 4))
        return tag

    def write_lines(self, chunk):
        at_end = self.follow.get() or self.text.yview()[1] >= 0.999
        self._writing = True
        self.text.configure(state="normal")
        for line in chunk.splitlines(keepends=True):
            body = line.rstrip("\n")
            k = textpane.kind_of(body)
            # (a blank line inside or after a block of numbers goes with them when they are hidden)
            in_nums = getattr(self, "_last_kind", "") in ("head", "row", "part", "total", "mech", "rule")
            if k != "blank":
                self._last_kind = k
            if k in ("pov", "progress", "rule", "input"):
                self.text.insert("end", line, (k,) + (("numbers",) if k == "rule" else ("progress_hide",)
                                                      if k == "progress" else ()))
            elif k == "blank":
                self.text.insert("end", line, ("gap",) + (("numbers",) if in_nums else ()))
            elif k == "story":
                self.styled(line, None, ("story",))
            else:
                self.mech_line(line, k)
                for note in self.pointers.feed(body):
                    self.text.insert("end", "ⓘ " + note + "\n", ("pointer", "pointer_hide"))
        self.text.configure(state="disabled")
        if at_end:
            self.text.see("end")
        self._writing = False

    def mech_line(self, line, k):
        """One line of numbers: shaded, wrapped under its own indent, its row name and change coloured, the words
        with a hover tip underlined."""
        start = self.text.index("end-1c")
        base = {"head": "head", "part": "part", "total": "total"}.get(k, "mech")
        self.styled(line, base, ("numbers", self._indent_tag(line)))
        # (the line as it went in: no ** marks, the coloured icons drawn as one sign each. Each span is found by
        # its own words, so an icon Tk counts differently can't shift it)
        shown = self.text.get(start, "end-1c").rstrip("\n")
        found = sorted(textpane.spans(shown) + [(a, b, "term") for a, b, _ in textpane.terms(shown)])
        for a, b, tag in found:
            sub = shown[a:b]
            at = self.text.search(sub, start, stopindex=f"{start} lineend", exact=True) if sub.strip() else ""
            if at:
                self.text.tag_add(tag, at, f"{at}+{len(sub)}c")

    def term_tip(self, e):
        """The hover tip on an underlined term: what the number is and which setting it comes from."""
        idx = self.text.index(f"@{e.x},{e.y}")
        rng = self.text.tag_prevrange("term", f"{idx}+1c")
        word = self.text.get(*rng) if rng else ""
        line = self.text.get(f"{idx} linestart", f"{idx} lineend")
        key = textpane.term_key(word)
        text = textpane.tip(key, line, self._rules()) if key else ""
        if text:
            import textwrap
            self.tip.show(e.x_root, e.y_root, "\n".join(textwrap.wrap(text, 70)))
        else:
            self.tip.hide()

    def styled(self, line, base=None, more=()):
        """**bold** and *thoughts and sounds*, as the console shows them."""
        pos = 0
        extra = ((base,) if base else ()) + tuple(more)
        for m in re.finditer(r"\*\*(.+?)\*\*|\*(?!\s)([^*\n]+?)\*", line):
            self.put(line[pos:m.start()], extra)
            if m.group(1) is not None:
                self.put(m.group(1), extra + (("mechbold",) if base else ("bold",)))
            else:
                self.put(m.group(2), extra + ("italic",) if not base else extra)
            pos = m.end()
        self.put(line[pos:], extra)

    def put(self, text, tags=()):
        """Insert text, with the console's coloured squares and dots drawn in their colours: Tk on Windows draws
        emoji in one colour only, so each becomes a plain square or dot coloured by the window (GLYPHS)."""
        pos = 0
        for m in GLYPH_RX.finditer(text):
            self.text.insert("end", text[pos:m.start()], tags)
            ch, color = GLYPHS[m.group(1)]
            tag = "glyph" + color
            if tag not in self._glyph_tags:
                self.text.tag_configure(tag, foreground=C(color), font=("Segoe UI Symbol", 10))
                self._glyph_tags.add(tag)
            self.text.insert("end", ch, tuple(tags) + (tag,))
            pos = m.end()
        self.text.insert("end", text[pos:], tags)

    def rebuild(self, records, live):
        """(since build 301) The story pane and the beat slider written again from the session's record of every
        beat (after /undo or /load): each beat's text, and the fight as it stood after it."""
        self.flush_pending()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.beats = []
        for text, snap in records:
            if text:
                self.add_text(text.rstrip("\n") + "\n")
            self.flush_pending()
            self.beats.append((self.text.index("end-1c"), snap))
        self.live = live
        self.follow.set(True)
        self.set_slider(len(self.beats) + 1)
        self.show(live, live=True)
        self.text.see("end")

    # ---- which beat is shown ----
    # Positions on the slider: 1..N are the beats (each as it stood when that beat ended), N+1 is "now".
    def set_slider(self, pos):
        """Move the slider without it acting as if you had dragged it (Tk calls its command on every set)."""
        self._setting = True
        try:
            self.slider.configure(to=len(self.beats) + 1)
            self.slider.set(pos)
        finally:
            self._setting = False

    def user_scroll(self, _e=None):
        self._user_scrolled = True
        self.root.after(40, self.scrolled)

    def beat_at(self, index):
        """The beat whose text holds this text position (1-based), or None past the last beat."""
        for k, (mark, snap) in enumerate(self.beats):
            if self.text.compare(mark, ">", index):
                return k + 1
        return None

    def scrolled(self):
        """You scrolled the story: show the beat you are reading (the line a third of the way down the view)."""
        if getattr(self, "_writing", False) or getattr(self, "_navigating", False) or not self.beats:
            return
        if not getattr(self, "_user_scrolled", False):
            return
        self._user_scrolled = False
        if self.text.yview()[1] >= 0.999 and self.follow.get():
            return
        self.follow.set(False)
        h = max(1, self.text.winfo_height())
        k = self.beat_at(self.text.index(f"@0,{h // 3}"))
        if k is None:
            self.set_slider(len(self.beats) + 1)
            self.show(self.live or self.beats[-1][1], live=True)
        else:
            self.set_slider(k)
            self.show(self.beats[k - 1][1], index=k)

    def slid(self, value):
        """The slider or the arrows chose a beat: show it, and bring its text to the top of the story."""
        if getattr(self, "_setting", False) or not self.beats:
            return
        k = int(round(float(value)))
        self.go(k)

    def go(self, k):
        k = max(1, min(len(self.beats) + 1, k))
        self.set_slider(k)
        if k > len(self.beats):
            self.follow.set(True)
            self.follow_changed()
            return
        self.follow.set(False)
        mark, snap = self.beats[k - 1]
        self.show(snap, index=k)
        start = self.beats[k - 2][0] if k >= 2 else "1.0"
        # the beat's first line at the top of the view (as far as the story allows); the scrolling this causes
        # must not choose a beat of its own
        self._navigating = True
        self.text.yview(start)
        self.root.after(200, lambda: setattr(self, "_navigating", False))

    def step(self, d):
        cur = int(round(float(self.slider.get())))
        if self.follow.get():
            cur = len(self.beats) + 1
        self.go(cur + d)

    def follow_changed(self):
        if self.follow.get():
            self.set_slider(len(self.beats) + 1)
            self._navigating = True
            self.text.see("end")
            self.root.after(200, lambda: setattr(self, "_navigating", False))
            if self.live:
                self.show(self.live, live=True)

    def _repaint_cards(self):
        """(since build 292) Make the cards show what was just drawn on them. They sit inside a scrolling canvas, and
        on Windows a change inside one (a strip that appears, grows or shrinks) was only painted once the cards were
        scrolled: lay them out now, put the scroll area right, and nudge the view by nothing to repaint it."""
        cv = getattr(self, "cards_canvas", None)
        if cv is None:
            return
        try:
            self.cards_frame.update_idletasks()
            cv.configure(scrollregion=cv.bbox("all"))
            cv.xview_moveto(cv.xview()[0])
            cv.yview_moveto(cv.yview()[0])
        except tk.TclError as e:
            note_failure("repainting the cards", e)

    def show(self, snap, live=False, index=None):
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
        # (since build 306) a beat on from the one shown: what landed jolts and flashes on her card (window.alive)
        turn, last = snap.get("turn"), getattr(self, "_shown_turn", None)
        step = turn is not None and last is not None and turn == last + 1
        for f in snap["fighters"]:
            card = self.cards[f["name"]]
            card.hits = impacts(card.data, f) if step and card.data else ([], 0.0)
            card.draw(f)
        self._shown_turn = turn
        self._sync_effects()
        self._repaint_cards()
        self.when.configure(text=("Now" if live else
                                  f"Beat {index} of {len(self.beats)}: as it stood {snap['label']}" if index else
                                  f"As it stood {snap['label']}"))

    def _rules(self):
        s = getattr(getattr(self, "game", None), "session", None)
        if s is not None:
            return s.eng.rules
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json"), encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def card_opts(self):
        """The card settings (rules.json "window"), with the switches on the bar above the cards."""
        o = opts_of(self._rules())
        o["back_view"] = bool(self.back_view.get())
        o["weak_look"] = bool(self.weak_look.get())
        o["damage_marks"] = bool(self.damage_marks.get())
        o["poses"] = bool(self.poses.get())
        return o

    def card_w(self):
        """How wide a fighter card is at its size now (Cards − / +)."""
        return int((PIC + 2 * COL) * getattr(self, "card_zoom", 1.0))

    def zoom_cards(self, d):
        """Cards − / +: the fighter cards 10% smaller or bigger (40% to 160%), kept for next time."""
        self.card_zoom = round(max(0.4, min(1.6, self.card_zoom + d)), 2)
        self.zoom_label.configure(text=f"{self.card_zoom * 100:.0f}%")
        try:
            play._save_rule_path(["window", "card_zoom"], self.card_zoom)
        except Exception as e:
            note_failure("saving the card size (window.card_zoom)", e)
        self.redraw_cards()

    def _sync_effects(self):
        """The Effects menu's ticks as the settings are now (/effects typed in the game changes them too)."""
        try:
            for name, on in play.effects_state(self._rules()):
                if name in getattr(self, "effect_flags", {}):
                    self.effect_flags[name].set(on)
        except Exception as e:
            note_failure("showing which effects are on (the Effects button)", e)

    def effect_changed(self, k):
        """The Effects button: one effect on or off (play.set_effect, kept like /set), then the cards drawn again."""
        try:
            rules = self._rules()
            play.set_effect(rules, k, bool(self.effect_flags[k].get()))
            for name, on in play.effects_state(rules):
                self.effect_flags[name].set(on)
        except Exception as e:
            note_failure("turning an effect on or off (the Effects button)", e)
        self.redraw_cards()

    def redraw_cards(self):
        for card in self.cards.values():
            if card.data:
                card.draw(card.data)

    def load_picture(self, card, f):
        def done(data, own):
            self.root.after(0, lambda: self.make_photo(card, data, own))
        fetch_picture(f["name"], f["species"] or f["name"], done)

        def got(book):
            self.root.after(0, lambda: self.set_book(card, book))
        fetch_book(f["name"], f["species"] or f["name"], opts_of(self._rules()), got)

    def set_book(self, card, book):
        if card.winfo_exists() and book.base("front") is not None:
            card.book = book
            card.cache = {}
            if card.data:
                card.draw(card.data)

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
