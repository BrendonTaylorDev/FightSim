"""Run scripted director beats through the real engine, dice and narrator notes, without Ollama.
The narrator's prompts are captured (sim/out/prompts_<beat>.txt) and a placeholder is returned as its prose."""
import argparse, io, json, os, re, sys, contextlib, shutil, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
# work in a throwaway copy, so settings commands never touch your rules.json or my_settings.json
ROOT = os.path.join(tempfile.gettempdir(), "fightsim_simrun")
shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(SRC, ROOT, ignore=shutil.ignore_patterns("sim", ".git", "__pycache__", "my_settings.json",
                                                         "blocks_memory.json", "autosave.json"))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import llm, play

CAPTURE = []

def fake_chat(model, messages, **kw):
    CAPTURE.append(messages)
    llm.last_done_reason = "stop"
    return ("Placeholder prose. " * 5).strip()

llm.chat = fake_chat
import narrator as _n, director as _d
_n.llm.chat = fake_chat
_d.llm.chat = fake_chat


def session(seed, scene="1", settings=()):
    args = argparse.Namespace(model="stand-in", director_model=None, narrator_model=None, host="", no_llm=False,
                              hide_math=False, json=False, seed=seed, no_autosave=True, fighters="Nocturne,Ripples",
                              scene=scene)
    s = play.Session(args)
    s.story = ["(opening)"]           # skip the arena intro
    for cmd in [f"/scene {scene}"] + list(settings):
        play.handle_command(s, cmd)
    return s


def beat(s, actions, log, roll=True):
    if roll:
        s.eng.roll_pin_windows()
    CAPTURE.clear()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        s.play_beat(manual=actions)
    log.append(buf.getvalue())
    return buf.getvalue(), list(CAPTURE)
