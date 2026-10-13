"""Drive the real FightSim window (window.py) under a virtual display for a test fight.

The game runs exactly as it would for the user (window, game thread, routed input, beat history, export), with two
test hooks: "/script N" plays beat N of script.json (the actions I chose as director), and the narrator's text for a
beat is the passage I wrote for it (narration/beatNN.md) instead of a model's. Everything happens in a throwaway copy
of the program, so no setting touches the real rules.json.

    xvfb-run -s "-screen 0 1600x1000x24" python3.12 wdrive.py <seed> <ui-plan.json>
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/home/user/FightSim"
ROOT = os.path.join(tempfile.mkdtemp(prefix="fightsim_window_"), "repo")
import atexit
atexit.register(shutil.rmtree, os.path.dirname(ROOT), True)
shutil.copytree(SRC, ROOT, ignore=shutil.ignore_patterns(".git", "__pycache__", "my_settings.json", "blocks_memory.json",
                                                         "lines_memory.json", "autosave.json", "exports", "sim"))
# PLAYED_BEFORE_REBALANCE: this fight was played with Ripples' Brick Break at power 35 (build 182); keep it so
# the window replays the same fight the narration was written for
_fj = os.path.join(ROOT, "fighters.json")
_t = open(_fj).read()
_i = _t.index('"name": "Ripples"'); _j = _t.index('"name": "Brick Break"', _i)
_k = _t.index('"power": 28', _j)
open(_fj, "w").write(_t[:_k] + '"power": 35' + _t[_k + len('"power": 28'):])
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import llm  # noqa: E402
import play  # noqa: E402
import narrator  # noqa: E402

SEED = int(sys.argv[1])
UI = json.load(open(os.path.join(HERE, sys.argv[2])))
SCRIPT = json.load(open(os.path.join(HERE, "script.json")))
SHOTS = os.path.join(HERE, "shots")
os.makedirs(SHOTS, exist_ok=True)


def fake_chat(model, messages, **kw):
    llm.last_done_reason = "stop"
    return "…"


llm.chat = fake_chat
narrator.llm.chat = fake_chat

_beat = {"n": 0}


def my_narration(self, bundle, *a, **k):
    """The passage written for this beat (the scene intro is beat 0): the nth beat told is beatNN.md."""
    _beat["told"] = _beat.get("told", 0) + 1
    n = _beat["told"]
    path = os.path.join(HERE, "narration", f"beat{n:02d}.md")
    if os.path.exists(path):
        return open(path, encoding="utf-8").read().strip()
    return f"(no narration written for beat {n})"


narrator.Narrator.narrate = my_narration
narrator.Narrator.intro = lambda self, *a, **k: (open(os.path.join(HERE, "narration", "beat00.md"), encoding="utf-8").read().strip()
                                                 if os.path.exists(os.path.join(HERE, "narration", "beat00.md")) else "")
def _intro(self):
    """The opening (narration/beat00.md) without building the fighter notes: the planner that played this fight
    never rolled the fight's reason, so the window doesn't either (the dice stay in step)."""
    self.push_history()
    text = narrator.Narrator.intro(self.narrator)
    self.out("\n" + text + "\n")
    self.story.append(text)


play.Session.intro = _intro
play.Session._interlude_due = lambda self: False   # no surprise interludes: the narration is written beat by beat
_orig_cmd = play.handle_command


def handle_command(s, line):
    if line.startswith("/script "):
        n = int(line.split()[1])
        _beat["n"] = n
        b = SCRIPT[n - 1]
        s.eng.roll_pin_windows()      # where the planner (sim/harness.beat) rolled them, so the dice stay in step
        s.play_beat(manual=b["actions"] if isinstance(b, dict) else b)
        return None
    return _orig_cmd(s, line)


play.handle_command = handle_command

import window  # noqa: E402

_orig_ask = window.GameThread.ask


def _ask(self, prompt=""):
    self._waiting = True
    try:
        return _orig_ask(self, prompt)
    finally:
        self._waiting = False


window.GameThread.ask = _ask

args = play.build_args(["--seed", str(SEED), "--fighters", "Nocturne,Ripples", "--scene", "14", "--model", "stand-in"])
app = window.App(args)
root = app.root


def shot(name):
    root.update()
    time.sleep(0.4)
    root.update()
    subprocess.run(["import", "-window", "root", os.path.join(SHOTS, name + ".png")], check=False)


def card(name):
    return app.cards.get(name)


def wait_idle(timeout=900):
    """Until the game thread is blocked waiting for the next line, and everything it printed is on screen."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        root.update()
        time.sleep(0.05)
        if (getattr(app.game, "_waiting", False) or not app.game.is_alive()) and app.out_q.empty():
            time.sleep(0.3)
            root.update()
            if app.out_q.empty():
                return


def send(line):
    app.entry.delete(0, "end")
    app.entry.insert(0, line)
    app.send()
    time.sleep(0.3)
    wait_idle()


def do(step):
    k = step[0]
    if k == "send":
        send(step[1])
    elif k == "shot":
        shot(step[1])
    elif k == "slider":
        app.set_slider(step[1])
        app.slid(step[1])
        root.update()
    elif k == "step":
        app.step(step[1])
        root.update()
    elif k == "follow":
        app.follow.set(step[1])
        app.follow_changed()
        root.update()
    elif k == "back_view":
        app.back_view.set(step[1])
        app.redraw_cards()
    elif k == "weak_look":
        app.weak_look.set(step[1])
        app.redraw_cards()
    elif k == "pick":        # click a part's label: it is then placed by the next click on a picture
        c = card(step[1])
        c.pick(step[2])
        root.update()
    elif k == "click":       # click a fighter's picture: ("click", fighter, view, fx, fy)
        c = card(step[1])
        pn = next(p for p in c.panels if p["view"] == step[2])
        rx, ry, rw, rh = pn["rect"]

        class E:
            pass
        e = E()
        e.x, e.y = pn["ox"] + rx + step[3] * rw, pn["oy"] + ry + step[4] * rh
        c.clicked(e)
        root.update()
    elif k == "tip":         # hover over a part's label
        c = card(step[1])
        app.tip.show(c.winfo_rootx() + 40, c.winfo_rooty() + 120,
                     f"{step[2]}\n(hover: damage and resistance, and how to move its point)")
        root.update()
    elif k == "untip":
        app.tip.hide()
    elif k == "scroll_cards":
        app.cards_canvas.yview_moveto(step[1])
        root.update()
    elif k == "copy_export":
        ex = os.path.join(ROOT, "exports")
        dst = os.path.join(HERE, "export")
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(ex) if os.path.isdir(ex) else []:
            shutil.copy(os.path.join(ex, f), dst)
    elif k == "copy_anchors":
        a = os.path.join(ROOT, "images", "anchors.json")
        if os.path.exists(a):
            shutil.copy(a, os.path.join(HERE, "anchors_after.json"))


def runner():
    try:
        wait_idle(120)
        for st in UI:
            do(st)
        with open(os.path.join(HERE, "window_text.txt"), "w", encoding="utf-8") as fh:
            fh.write(app.text.get("1.0", "end"))
        print("done; window text saved;", len(app.beats), "beats recorded", flush=True)
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        root.after(200, app.close)
        root.after(400, root.quit)


root.after(300, runner)
root.mainloop()
