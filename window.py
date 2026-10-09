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

from cards import (IMG_DIR, PIC, COL, ROW, RES_STEPS, DMG_STEPS, res_color, dmg_color, text_on, short,
                   glow_color, load_anchors, save_anchors, picture_bytes, point_key, anchor_points, glow_image,
                   columns, spread)

try:                           # Pillow makes the pictures smoother when it is installed; Tk alone works too
    from PIL import Image, ImageTk
except Exception:              # pragma: no cover
    Image = ImageTk = None

snapshot = play.fight_snapshot


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


class GameThread(threading.Thread):
    """Runs the ordinary game loop (play._run), its printing and asking routed to the window."""

    def __init__(self, args, out_q, in_q):
        super().__init__(daemon=True)
        self.args, self.out_q, self.in_q = args, out_q, in_q
        self.session = None
        self.fightsim_game = True

    def ask(self, prompt=""):
        if self.session is not None:
            self.out_q.put(("live", snapshot(self.session, "now")))
        self.out_q.put(("prompt", str(prompt)))
        line = self.in_q.get()
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
        self.data = f
        pct = 100.0 * f["health"] / f["max"]
        self.head.configure(text=f["name"] + ("   — OUT" if f["out"] else ""))
        self.sub.configure(text=f"{f['species']}  ·  {' / '.join(f['types'])}")
        spots = self.anchors(f)
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
            ys = spread([top + spots[p[0]][1] for p in rows], H)
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
        self.root.report_callback_exception = lambda *exc: self.show_error(
            "".join(__import__("traceback").format_exception(*exc)))
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
        ttk.Button(bottom, text="Export", command=lambda: self.send_line("/exportfight")).pack(side="left", padx=2)
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
        for f in snap["fighters"]:
            self.cards[f["name"]].draw(f)
        self.when.configure(text=("Now" if live else
                                  f"Beat {index} of {len(self.beats)}: as it stood {snap['label']}" if index else
                                  f"As it stood {snap['label']}"))

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
