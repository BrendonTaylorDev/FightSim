"""/exportfight: a whole fight saved beat by beat, so nothing is lost when the program closes.

Writes two files into the exports folder (or where you say):
  <name>.html  a page for your browser: every beat's story and stat lines, and beside it each fighter as she stood
               after that beat (her pictures, front and back, looking as worn as she was, with each hurt part glowing
               and a line from every part to its damage and resistance, health and energy), plus a table of every part.
  <name>.json  the same data, plain (the text of each beat and every fighter's numbers)."""
import base64
import datetime
import html
import io
import json
import os
import re

import cards
import sounds
from engine import poss_word

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exports")

POV = re.compile(r"^—\s.+\s—$")
PROGRESS = re.compile(r"^\s*\[.*\]\s*$")
RULE = re.compile(r"^(?:-{8,}|={8,}|─{8,}|═{8,})$")
MECH = re.compile(r"^\s{2,}\S|^[⚔🔒📌🎲⏳💡🧗🪽🔗💥💢🪨🌀🌊🔐🤾🏋⛓⏸🩹📜⏱💨🛡🫳🫥↩🧱🌅🔥⚡💧😵🧠🌦🦅🪶🤚🧊🫨]"
                  r"|^\s*(?:Total|Calculations|Power|Rolls|Beat \d|Attack \d|Impact —|- )")


def _md(text):
    """**bold** and *thoughts and sounds* as HTML (after escaping)."""
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"\*(?!\s)([^*\n]+?)\*", r"<i>\1</i>", t)


# the game's own announcements ("*** Winner: Nocturne ***") and what it tells you to do next at the keyboard
RESULT = re.compile(r"\*\*\*\s*(.+?)\s*\*\*\*")
CONSOLE_HINT = re.compile(r"^\((?:The match is over|Stopped|rerolled|A previous fight)|^Still in the fight:|"
                          r"Keep pressing Enter|^\(type /help\)|^Press Enter", re.I)


def _split(text):
    """A beat's text as (story paragraphs, stat lines, results): the game's announcements (who is out, who won)
    come out as results, and its hints about what to type next are left out."""
    story, mech, results = [], [], []
    para = []
    in_stats = False
    for line in (text or "").splitlines():
        s = line.strip()
        if PROGRESS.match(line):
            continue
        if RESULT.search(s) and not in_stats:
            results += [m.group(1).strip() for m in RESULT.finditer(s)]
            rest = CONSOLE_HINT.sub("", RESULT.sub("", s)).strip()
            if rest and not CONSOLE_HINT.search(rest) and not rest.startswith("("):
                mech.append(rest)
            continue
        if CONSOLE_HINT.search(s):
            continue
        if RULE.match(s):
            in_stats = not in_stats if s.startswith("-") else in_stats
            if para:
                story.append(" ".join(para)); para = []
            continue
        if in_stats or MECH.match(line):
            mech.append(line)
            continue
        if not s:
            if para:
                story.append(" ".join(para)); para = []
            continue
        if POV.match(s):
            if para:
                story.append(" ".join(para)); para = []
            story.append(("pov", s))
            continue
        para.append(s)
    if para:
        story.append(" ".join(para))
    return story, mech, results


def _card_img(f, books, opts=None):
    img = cards.render_card(f, book=books.get(f["name"]), opts=opts)
    if img is None:
        return ""
    buf = io.BytesIO()
    try:
        img.save(buf, "WEBP", quality=82)
        mime = "image/webp"
    except Exception:
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        mime = "image/png"
    return (f'<img class="card" alt="{html.escape(f["name"])}" '
            f'src="data:{mime};base64,{base64.b64encode(buf.getvalue()).decode()}">')


def _bars(f):
    pct = 100.0 * f["health"] / max(1e-9, f["max"])
    col = "#22c55e" if pct >= 60 else "#eab308" if pct >= 35 else "#f97316" if pct >= 15 else "#ef4444"
    sts = ", ".join(f"{k.replace('_', ' ')} ({v})" if isinstance(v, (int, float)) and not isinstance(v, bool)
                    else k.replace("_", " ") for k, v in (f.get("status") or {}).items()) or "no statuses"
    return (f'<div class="who"><b>{html.escape(f["name"])}</b> <span class="dim">{html.escape(f.get("species", ""))}'
            f' · {html.escape(" / ".join(f.get("types") or []))}</span></div>'
            f'<div class="bar"><span style="width:{max(0, min(100, pct)):.0f}%;background:{col}"></span>'
            f'<em>Health {f["health"]:.0f}% ({pct:.0f}% of full)</em></div>'
            f'<div class="bar thin"><span style="width:{max(0, min(100, f.get("energy", 0))):.0f}%;background:#60a5fa">'
            f'</span><em>energy {f.get("energy", 0):.0f}</em></div>'
            f'<div class="dim">{html.escape(f.get("posture", ""))} · {html.escape(sts)}</div>')


def _gauges(f, books=None, opts=None):
    """The window's tap tally and two pain gauges, as on screen (export.gauges): taps given against those needed,
    then overall pain and the part held or struck, each a share of what she can bear (full width 150%, a mark at
    100%). Beats saved before build 249 have no pain gauge, and a fight that isn't a submission match no tally."""
    out = ""
    t = f.get("taps")
    if t:
        given, need = list(t.get("given") or []), max(1, int(t.get("needed") or 1))
        pips = "".join(f'<span class="pip{" on" if i < len(given) else ""}"></span>'
                       for i in range(max(need, len(given))))
        parts = ", ".join(str(p).lower() for p in given)
        out += (f'<div class="taps"><b>Taps</b> {pips} {len(given)} of {need}'
                f'{html.escape(f"  ({parts})") if parts else ""}</div>')
    g = f.get("pain")
    if g:
        def bar(x, text):
            share = max(0.0, float(x.get("pct") or 0))
            col = "#a3a3a3" if share < 40 else "#f59e0b" if share < 70 else "#ea580c" if share < 100 else "#b91c1c"
            return (f'<div class="bar pain"><span style="width:{min(100.0, share / 1.5):.0f}%;background:{col}"></span>'
                    f'<i class="limit"></i><em>{html.escape(text)}</em></div>')
        o, pt = g.get("overall") or {}, g.get("part")
        out += bar(o, f"Pain {o.get('shown') or str(o.get('pct', 0)) + '%'}: {o.get('label', '')}" + (f"  ({o['where']})" if o.get("where") else ""))
        if pt:
            parts = ", ".join(str(p).lower() for p in pt.get("parts") or [])
            out += bar(pt, f"{parts.capitalize() or 'Part'} {pt.get('shown') or str(pt.get('pct', 0)) + '%'}: {pt.get('label', '')}"
                           + (f"  ({pt['why']})" if pt.get("why") else "")
                           + (f"  · {'blood flow' if pt.get('circ') else 'air'} {pt['air']}% "
                           f"{'cut off' if pt.get('circ') else 'gone'}" if pt.get("air") is not None else ""))
        else:
            out += '<div class="dim">nothing held or struck this beat</div>'
    m = cards.tap_meter(f)
    if m:
        # (window.hold_panel) how near she is to tapping: five steps and this beat's chance, as in the window
        steps = "".join(f'<span class="step" style="background:{cards.TAP_COLORS[i] if i <= m["level"] else "#fff"}">'
                        f'</span>' for i in range(1, 6))
        out += (f'<div class="taps"><b>Tap</b> {steps} {html.escape(m["label"])} · {cards.pct_text(m["chance"])} chance this '
                f'beat</div><div class="dim">{html.escape(poss_word(str(m["by"])))} {html.escape(str(m["sub"]))}: pain '
                f'{m["pain"]} against what she can bear {m["resist"]}'
                + (f' · {html.escape(m["note"])}' if m["note"] else "") + '</div>')
        v = m.get("vitals")
        if v:
            # (since build 287) the constriction drawn, as in the window: her heart as a trace, the blood flow cut
            # off, her blood pressure
            col, w = cards.vitals_colour(v.get("blood", 0)), 300
            # (since build 293) the trace runs like a monitor's: six seconds drawn twice end to end, slid along
            base = cards.ecg_points(v["heart"], v.get("irregular"), w - 90, 22, 0, 2)
            base = base + [(x + w - 90, y) for x, y in base[1:]]
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in base)
            cid = f"ecg{abs(hash((v['heart'], v.get('blood'), id(f)))) % 10**8}"
            bp = v.get("bp") or [120, 80]
            # (since build 299, window.squeeze_figure) the squeeze as a picture of its own, after the monitor
            figure = v.get("squeeze") is not None and (opts or {}).get("squeeze_figure", True)
            odds = cards.blackout_text(v)
            vh = 60 if v.get("squeeze") is not None and not figure else 44
            # (since build 302) the monitor and the squeeze picture side by side where the page is wide enough
            out += '<div style="display:flex;flex-wrap:wrap;gap:4px;align-items:flex-start">'
            out += (f'<svg class="vitals" viewBox="0 0 {w + 90} {vh + (14 if odds[0] else 0)}" width="100%" style="flex:1 1 300px;background:#111827;'
                    f'border-radius:4px;max-width:520px">'
                    f'<text x="6" y="16" fill="{"#ef4444" if v.get("stopped") else col}" font-size="11" '
                    f'font-weight="bold">{"♥ stopped" if v.get("stopped") else "♥ " + str(v["heart"]) + "/min"}</text>'
                    + ('<text x="6" y="29" fill="#fca5a5" font-size="8">irregular</text>' if v.get("irregular") else "")
                    + (f'<text x="6" y="41" fill="#9ca3af" font-size="7">normal {v["heart_rest"]}/min</text>'
                       if v.get("heart_rest") else "")
                    + (f'<text x="{w}" y="26" fill="#9ca3af" font-size="7">normal {v["bp_rest"][0]}/{v["bp_rest"][1]}</text>'
                       if v.get("bp_rest") else "")
                    + ((lambda sh: f'<rect x="{sh[0][0]}" y="{sh[0][1]}" width="{sh[0][2] - sh[0][0]:.1f}" height="10" '
                       f'fill="none" stroke="#4b5563" stroke-dasharray="2,2"/>'
                       + "".join(f'<rect x="{b[0]:.1f}" y="{b[1]}" width="{max(1.0, b[2] - b[0]):.1f}" height="{b[3] - b[1]:.1f}" '
                                 f'fill="#3b82f6" stroke="#1f2937"/>' for b in sh[2])
                       + f'<rect x="{sh[1][0]:.1f}" y="{sh[1][1]}" width="{sh[1][2] - sh[1][0]:.1f}" height="{sh[1][3] - sh[1][1]:.1f}" '
                       f'fill="#c08457" stroke="#60a5fa" stroke-width="1.5"/>'
                       + f'<text x="6" y="54" fill="#f9fafb" font-size="9">{html.escape(cards.squeeze_label(v))}</text>')
                       (cards.squeeze_shapes(v["squeeze"], v.get("coils"), 84, w - 90, 46, 10, ring=bool(v.get("ring"))))
                       if v.get("squeeze") is not None and not figure else "")
                    + f'<clipPath id="{cid}"><rect x="84" y="0" width="{w - 90}" height="28"/></clipPath>'
                    f'<g clip-path="url(#{cid})"><g transform="translate(84,0)"><polyline points="{pts}" fill="none" '
                    f'stroke="{col}" stroke-width="1.5"><animateTransform attributeName="transform" type="translate" '
                    f'from="0 0" to="-{w - 90} 0" dur="6s" repeatCount="indefinite"/></polyline></g></g>'
                    f'<rect x="84" y="30" width="{w - 90}" height="10" fill="#1f2937" stroke="#4b5563"/>'
                    f'<rect x="84" y="30" width="{(w - 90) * min(1.0, v.get("blood", 0) / 100.0):.0f}" height="10" '
                    f'fill="{col}"/><text x="88" y="38" fill="#f9fafb" font-size="8">blood flow {v.get("blood", 0)}% '
                    f'cut off</text>'
                    f'<text x="{w}" y="16" fill="{"#f9fafb" if bp[0] >= 90 else "#fca5a5"}" font-size="11" '
                    f'font-weight="bold">BP {bp[0]}/{bp[1]}</text>'
                    f'<rect x="{w}" y="30" width="80" height="10" fill="#1f2937" stroke="#4b5563"/>'
                    f'<rect x="{w}" y="30" width="{80 * min(1.0, bp[0] / 160.0):.0f}" height="10" fill="{col}"/>'
                    f'<line x1="{w + 60}" y1="28" x2="{w + 60}" y2="42" stroke="#9ca3af" stroke-dasharray="2,2"/>'
                    f'<text x="{w + 3}" y="38" fill="#f9fafb" font-size="8">pressure</text>'
                    # (since build 302) her limit on the blood-flow gauge, and how near she is to blacking out
                    + (f'<line x1="{84 + (w - 90) * min(1.0, v["out_at"] / 100.0):.1f}" y1="27" '
                       f'x2="{84 + (w - 90) * min(1.0, v["out_at"] / 100.0):.1f}" y2="43" stroke="#f9fafb" '
                       f'stroke-width="2"/>' if v.get("out_at") is not None else "")
                    + (f'<text x="6" y="{vh + 9}" fill="{odds[1]}" font-size="9" font-weight="bold">'
                       f'{html.escape(odds[0])}</text>' if odds[0] else "")
                    + '</svg>')
            if figure:
                body, belly = cards.picture_colours((books or {}).get(f["name"]), "#c08457")
                coil = cards.picture_colours((books or {}).get(v.get("coiler")), "#5d8fcf")[0]
                out += cards.squeeze_svg(v, body, coil, belly).replace('style="', 'style="flex:1 1 300px;', 1)
            out += '</div>'
    if (opts or {}).get("hold_picture", True):
        # (since build 304) the grips on her as a picture beside their gauges, as in the window
        gr = f.get("grips") or {}
        pby = (gr.get("pin") or {}).get("by")      # (one pinner, or a list of them: a double pin)
        who = {g.get("by") for g in gr.get("held") or ()} | ({pby} if isinstance(pby, str) else set(pby or ()))
        holders = {n: cards.picture_colours((books or {}).get(n), "#5d8fcf")[0] for n in who}
        body, belly = cards.picture_colours((books or {}).get(f["name"]), "#c08457")
        shapes, hh = cards.hold_shapes(f, 4, 6, 90, 150, 108, 500, body, belly, holders)
        if shapes:
            out += cards.shapes_svg(shapes, 616, hh + 4)
    for text, col in cards.grip_lines(f):
        out += f'<div class="grip" style="color:{col}">{html.escape(text)}</div>'
    return out


def _table(f):
    rows = "".join(
        f'<tr><td>{html.escape(p)}</td><td class="n"><span class="chip" style="background:{cards.dmg_color(d)};'
        f'color:{cards.text_on(cards.dmg_color(d))}">{d:.1f}%</span></td><td class="n"><span class="chip res" '
        f'style="border-color:{cards.res_color(r)}">{r:.1f}%</span></td></tr>'
        for p, d, r in sorted(f["parts"], key=lambda t: -t[1]))
    return (f'<details><summary>{html.escape(f["name"])}: every body part</summary><table><tr><th>Part</th>'
            f'<th>Damage</th><th>Resistance</th></tr>{rows}</table></details>')


CSS = """
:root{--bg:#f6f4ef;--ink:#1f2937;--dim:#6b7280;--card:#fff;--line:#e5e7eb}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15171c;--ink:#e5e7eb;--dim:#9ca3af;--card:#1f232b;--line:#2f3540}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 Georgia,serif}
.editbar{padding:8px 16px;border-bottom:1px solid var(--line);font:13px system-ui,sans-serif}
.editbar button{font:13px system-ui,sans-serif;padding:5px 10px;margin:3px 4px 3px 0;border:1px solid var(--line);
border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}.editbar button:hover{border-color:#2563eb}
.editbar textarea,.tbox{width:100%;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px;
padding:10px;font:15px/1.55 Georgia,serif;resize:vertical}.tbox{min-height:320px}#fsNote{color:#2563eb}
header{padding:20px 16px;border-bottom:1px solid var(--line)}h1{margin:0;font:600 26px system-ui,sans-serif}
nav{position:sticky;top:0;background:var(--bg);padding:8px 16px;border-bottom:1px solid var(--line);z-index:2;
overflow-x:auto;white-space:nowrap;font:13px system-ui,sans-serif}nav a{margin-right:10px;color:#2563eb;text-decoration:none}
section{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,640px);gap:20px;padding:20px 16px;
border-bottom:1px solid var(--line)}@media (max-width:1100px){section{grid-template-columns:1fr}}
h2{grid-column:1/-1;margin:0;font:600 18px system-ui,sans-serif}.pov{font:600 15px system-ui,sans-serif;color:#b45309;margin:18px 0 6px}
.story p{margin:0 0 12px}i{color:#7c3aed}.side{display:flex;flex-direction:column;gap:14px}
.fighter{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}
.card{max-width:100%;height:auto;display:block;border-radius:4px;background:#fff}
.who{font:14px system-ui,sans-serif}.dim{color:var(--dim);font:13px system-ui,sans-serif}
.bar{position:relative;height:18px;background:var(--line);border-radius:3px;margin:6px 0 2px;overflow:hidden}
.bar.thin{height:12px}.bar span{position:absolute;left:0;top:0;bottom:0}.bar em{position:relative;display:block;
padding:0 6px;font:600 11px/18px system-ui,sans-serif;font-style:normal;color:#111;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}.bar.thin em{line-height:12px;font-size:10px}
.bar.pain{height:auto;min-height:18px}.bar.pain em{white-space:normal;line-height:15px;padding:2px 6px}
details{margin-top:8px;font:13px system-ui,sans-serif}summary{cursor:pointer;color:#2563eb}
pre{white-space:pre-wrap;font:12px/1.45 Consolas,monospace;color:var(--dim);margin:6px 0 0}
table{border-collapse:collapse;width:100%;margin-top:6px}td,th{padding:2px 6px;border-bottom:1px solid var(--line);text-align:left}
td.n{text-align:right}.chip{display:inline-block;min-width:58px;padding:0 4px;border-radius:3px;text-align:center;font-weight:600}
.chip.res{border:2px solid;background:transparent;font-weight:400}
.taps{font:13px system-ui,sans-serif;margin:6px 0 2px}.step{display:inline-block;width:22px;height:10px;border:1px solid #9ca3af;margin-right:2px}.grip{font:12px system-ui,sans-serif;margin:1px 0}.pip{display:inline-block;width:12px;height:12px;
border-radius:50%;border:1.5px solid #7f1d1d;background:#fff;margin-right:3px;vertical-align:-2px}.pip.on{background:#dc2626}
.bar.pain i.limit{position:absolute;left:66.7%;top:0;bottom:0;border-left:1px dashed #111827}
.sndre{font-size:14px;margin-left:8px;padding:0 6px;cursor:pointer;vertical-align:middle}
.result{margin:14px 0 4px;padding:8px 12px;border-left:4px solid #b45309;background:var(--card);
font:600 15px system-ui,sans-serif}
"""


MINOR_SOUND = sounds.MINOR


def _sound_bar(beat_sounds):
    """The switch at the top of an exported fight: browsers play nothing until you allow it with a click."""
    if not beat_sounds:
        return ""
    return ('<div class="dim" style="margin:6px 0"><button id="sndbtn" onclick="fsSound()">&#128264; Sounds off: '
            'click to hear the fighters as you scroll</button></div>')


def _sound_script(beat_sounds, files, sc):
    """Each beat's sounds, played once as it scrolls into view (after the switch above is turned on), and again from
    the beat's speaker button. (since build 330) Each fighter has one voice, as in the window (window.sounds.overlap):
    her sounds play one after another, a long one to its end, and a new beat's sound cuts off the last unless it is
    a minor one (strain, pant) no bigger than what she is still making. beat_sounds: {beat: [[file, who, priority]]}"""
    if not beat_sounds:
        return ""
    mode = str(sc.get("overlap", "voice")).lower()
    return ("<script>const FS_FILES=" + json.dumps(files) + ";const FS_BEATS=" + json.dumps(beat_sounds)
            + ";const FS_VOL=" + json.dumps(max(0.0, min(1.0, float(sc.get("volume", 0.8)))))
            + ";const FS_MODE=" + json.dumps(mode) + ";const FS_MAX=" + json.dumps(float(sc.get("max_seconds", 0) or 0))
            + ";const FS_QMAX=" + json.dumps(int(sc.get("queue_max", 3))) + ";const FS_MINOR=" + json.dumps(MINOR_SOUND)
            + """;let fsOn=false;const fsDone=new Set();const FS_CH={};
function fsStop(ch){if(ch.a){ch.a.onended=null;ch.a.pause();ch.a=null;}clearTimeout(ch.t);}
function fsNext(ch){fsStop(ch);const n=ch.q.shift();if(n===undefined)return;const a=new Audio(FS_FILES[n[0]]);
a.volume=FS_VOL;ch.a=a;ch.p=n[2];a.onended=()=>{if(ch.a===a)fsNext(ch);};
if(FS_MAX>0)ch.t=setTimeout(()=>{if(ch.a===a)fsNext(ch);},FS_MAX*1000);a.play().catch(()=>{if(ch.a===a)fsNext(ch);});}
function fsPlay(id){const by={};(FS_BEATS[id]||[]).forEach(c=>(by[c[1]]=by[c[1]]||[]).push(c));
for(const w in by){const it=by[w];if(FS_MODE==='mix'){it.forEach(c=>{const a=new Audio(FS_FILES[c[0]]);
a.volume=FS_VOL;a.play().catch(()=>{});});continue;}
const ch=FS_CH[w]=FS_CH[w]||{q:[],a:null,p:0,t:0};
if(FS_MODE==='queue'){ch.q=ch.q.concat(it).slice(0,FS_QMAX);if(!ch.a)fsNext(ch);continue;}
const top=Math.max(...it.map(c=>c[2]));if(ch.a&&top<=Math.min(FS_MINOR,ch.p))continue;
ch.q=it.slice();fsNext(ch);}}
function fsReplay(id){for(const w in FS_CH){FS_CH[w].q=[];fsStop(FS_CH[w]);}fsPlay(id);}
function fsSound(){fsOn=!fsOn;if(!fsOn)for(const w in FS_CH){FS_CH[w].q=[];fsStop(FS_CH[w]);}
document.getElementById('sndbtn').textContent=fsOn?'Sounds on (click to turn off)'
:'Sounds off: click to hear the fighters as you scroll';}
const fsObs=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting&&fsOn&&!fsDone.has(e.target.id)){
fsDone.add(e.target.id);fsPlay(e.target.id);}}),{threshold:0.35});
document.querySelectorAll('section[id^=b]').forEach(x=>fsObs.observe(x));</script>""")


def write(s, path=None, fights=None):
    """Write the fight(s) to an .html page and a .json file; returns the .html path."""
    recs = [r for r in getattr(s, "beat_records", []) if fights is None or r.get("fight") in fights]
    if not recs:
        raise ValueError("there is nothing to export yet: play a beat first")
    if not path:
        os.makedirs(OUT_DIR, exist_ok=True)
        names = "_vs_".join(recs[0].get("lineup") or ["fight"])
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
        tag = f"fight{recs[0].get('fight')}" if fights and len(fights) == 1 else "fights"
        path = os.path.join(OUT_DIR, f"{tag}_{names}_{stamp}.html")
    base = os.path.splitext(path)[0]
    rules = getattr(getattr(s, "eng", None), "rules", None) or {}
    opts = cards.opts_of(rules)
    gauges = (rules.get("export") or {}).get("gauges", True)
    pics = {}
    for r in recs:
        for f in r["snapshot"]["fighters"]:
            if f["name"] not in pics:
                pics[f["name"]] = cards.PictureBook(f["name"], f.get("species") or f["name"], opts)
    title = " vs ".join(recs[0].get("lineup") or [])
    arena = (getattr(s.eng, "scene_cfg", None) or {}).get("title", "")
    nav, body = [], []
    # (since build 329, window.sounds.export) each beat's sounds, the files they use carried in the page
    sc = sounds.cfg(rules)
    beat_sounds, sound_files, sound_bytes = {}, {}, 0
    cap = float(sc.get("export_max_mb", 8)) * 1024 * 1024
    prev_by = {}
    for k, r in enumerate(recs):
        cues = []
        for f in r["snapshot"]["fighters"]:
            if sc.get("enabled", True) and sc.get("export", True):
                for kind in sounds.cues(prev_by.get(f["name"]), f, rules, r.get("turn") or k):
                    pth = sounds.pick(f, kind, sc.get("starters", True))
                    if not pth:
                        continue
                    if pth not in sound_files:
                        try:
                            size = os.path.getsize(pth)
                            if sound_bytes + size > cap:
                                continue
                            with open(pth, "rb") as fh:
                                mime = "audio/mpeg" if pth.lower().endswith(".mp3") else (
                                    "audio/ogg" if pth.lower().endswith(".ogg") else "audio/wav")
                                sound_files[pth] = f"data:{mime};base64," + base64.b64encode(fh.read()).decode()
                            sound_bytes += size
                        except OSError as e:
                            from engine import note_failure
                            note_failure("putting a sound in the exported fight", e)
                            continue
                    cues.append([list(sound_files).index(pth), f["name"], sounds.PRIORITY.get(kind, 3)])
            prev_by[f["name"]] = f
        if cues:
            beat_sounds[f"b{k}"] = cues
    stories = {}
    for k, r in enumerate(recs):
        fight = r.get("fight")
        label = r.get("label") or f"beat {r.get('turn')}"
        head = (f"Fight {fight}: " if fights is None or len(fights or []) > 1 else "") + label[:1].upper() + label[1:]
        nav.append(f'<a href="#b{k}">{html.escape(label)}</a>')
        story, mech, results = _split(r.get("text", ""))
        st = "".join(f'<div class="pov">{html.escape(x[1])}</div>' if isinstance(x, tuple) else f"<p>{_md(x)}</p>"
                     for x in story)
        res_html = "".join(f'<div class="result">{html.escape(x)}</div>' for x in results)
        mech_html = res_html + (f'<details><summary>stat lines and rolls</summary><pre>{_md(chr(10).join(mech))}</pre>'
                                f'</details>' if mech else "")
        side = ""
        for f in r["snapshot"]["fighters"]:
            img = _card_img(f, pics, opts)
            sts = ", ".join(f"{k.replace('_', ' ')} ({v})" if isinstance(v, (int, float)) and not isinstance(v, bool)
                            else k.replace("_", " ") for k, v in (f.get("status") or {}).items()) or "no statuses"
            gz = _gauges(f, pics, opts) if gauges else ""
            side += (f'<div class="fighter">{img}<div class="dim">{html.escape(f.get("posture", ""))} · '
                     f'{html.escape(sts)}</div>{gz}{_table(f)}</div>' if img else
                     f'<div class="fighter">{_bars(f)}{gz}{_table(f)}</div>')
        if not st:
            # (since build 266) say why: a narration that failed (Ollama down) and was never rerolled
            fail = re.search(r"\[narration failed: ([^\]]+)\]", r.get("text", ""))
            st = (f"<p class=dim>(no story for this beat: the narration failed ({html.escape(fail.group(1))}) and "
                  f"was never rerolled)</p>" if fail else "<p class=dim>(no story text for this beat)</p>")
        # (since build 330) a beat's sounds play once as it scrolls into view; this button plays them again
        replay = (f' <button class="sndre" title="Play this beat\'s sounds again" onclick="fsReplay(\'b{k}\')">'
                  f'&#128266;</button>' if f"b{k}" in beat_sounds else "")
        stories[k] = story_text(r.get("text", ""))
        body.append(f'<section id="b{k}"><h2>{html.escape(head)}{replay}</h2><div class="story">'
                    f'<div class="tale" data-k="{k}" data-label="{html.escape(label, quote=True)}">{st}</div>'
                    f'{mech_html}</div><div class="side">{side}</div></section>')
    page = (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>{html.escape(title or "Fight")}</title><style>{CSS}</style></head><body>'
            f'<header><h1>{html.escape(title)}</h1><div class="dim">{html.escape(arena)} · saved '
            f'{datetime.datetime.now():%Y-%m-%d %H:%M} · {len(recs)} beats</div></header>'
            f'<nav>{"".join(nav)}</nav>{_edit_bar(rules)}{_sound_bar(beat_sounds)}{"".join(body)}'
            f'{_sound_script(beat_sounds, list(sound_files.values()), sc)}{_edit_script(rules, stories, base)}'
            f'</body></html>')
    with open(base + ".html", "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump({"title": title, "arena": arena, "beats": recs}, fh, ensure_ascii=False, indent=1)
    if (rules.get("export") or {}).get("editor", True):
        try:
            write_editor(base, title, arena, recs)
        except Exception as e:
            from engine import note_failure
            note_failure("writing the story editor page (export.editor)", e)
    return base + ".html"


def _edit_on(rules):
    return bool((rules.get("export") or {}).get("editor", True))


def _edit_bar(rules):
    """(since build 344, export.editor) The story tools at the top of an exported fight: edit the story in place,
    copy it all out for Venice and paste its rewrite back, and save the page (pictures, gauges and all) with it in."""
    if not _edit_on(rules):
        return ""
    return ('<div class="editbar"><button onclick="fsEdit()" id="fsEditBtn">Edit the story</button>'
            '<button onclick="fsCopyAll()">Copy the whole fight for Venice</button>'
            '<button onclick="fsTxt()">Download it as a .txt file</button>'
            '<button onclick="fsSave()">Save the page</button> <span id="fsNote"></span>'
            '<details><summary>what Venice is asked (put above the text when you copy it; edit it freely)</summary>'
            f'<textarea id="fsAsk" rows="3">{html.escape(EDITOR_ASK)}</textarea></details>'
            '<details><summary>paste the whole fight back (Venice\'s answer, with its "=== BEAT n ===" lines)</summary>'
            '<textarea id="fsBulk" rows="8" placeholder="Paste the whole rewritten fight here"></textarea>'
            '<button onclick="fsApply()">Put it into the beats</button></details></div>')


EDIT_PAGE_JS = r"""
const FS_STORY = JSON.parse(document.getElementById('fs-story').textContent || '{}');
let fsEditing = false;
function fsNote(t){ const n = document.getElementById('fsNote'); n.textContent = t; clearTimeout(n._t);
  n._t = setTimeout(() => n.textContent = '', 3000); }
function fsEsc(t){ return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function fsHtml(t){ return t.trim().split(/\n\s*\n/).filter(x => x.trim()).map(x => { x = x.trim();
  if (/^—\s.+\s—$/.test(x)) return '<div class="pov">' + fsEsc(x) + '</div>';
  return '<p>' + fsEsc(x).replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>') + '</p>'; }).join('') || '<p class=dim>(no story text for this beat)</p>'; }
function fsTales(){ return Array.from(document.querySelectorAll('.tale')); }
function fsText(d){ const b = d.querySelector('textarea'); return b ? b.value : (FS_STORY[d.dataset.k] || ''); }
function fsEdit(){ fsEditing = !fsEditing;
  fsTales().forEach(d => { if (fsEditing) { const t = FS_STORY[d.dataset.k] || '';
      d.innerHTML = '<textarea class="tbox" rows="14"></textarea>'; d.querySelector('textarea').value = t;
      d.querySelector('textarea').addEventListener('input', e => { FS_STORY[d.dataset.k] = e.target.value; fsStash(); }); }
    else { FS_STORY[d.dataset.k] = fsText(d); d.innerHTML = fsHtml(FS_STORY[d.dataset.k]); } });
  document.getElementById('fsEditBtn').textContent = fsEditing ? 'Done editing' : 'Edit the story'; }
function fsAll(){ return fsTales().map(d => '=== BEAT ' + d.dataset.k + ' (' + d.dataset.label + ') ===\n'
  + fsText(d).trim()).join('\n\n') + '\n'; }
function fsAsk(){ const a = document.getElementById('fsAsk'); return a && a.value.trim() ? a.value.trim() + '\n\n' : ''; }
function fsCopy(t){ const done = () => fsNote('copied');
  const fb = () => { const a = document.createElement('textarea'); a.value = t; document.body.appendChild(a); a.select();
    try { document.execCommand('copy'); done(); } catch(e) { fsNote('select and copy by hand'); } a.remove(); };
  if (navigator.clipboard) navigator.clipboard.writeText(t).then(done, fb); else fb(); }
function fsCopyAll(){ fsCopy(fsAsk() + fsAll()); }
function fsDownload(name, text, type){ const b = new Blob([text], {type: type || 'text/plain'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000); }
function fsTxt(){ fsDownload(FS_PAGE + '_story.txt', fsAsk() + fsAll()); }
function fsApply(){ const t = document.getElementById('fsBulk').value; const re = /^=== BEAT (\d+)[^=\n]*===\s*$/gm;
  const marks = []; let m; while ((m = re.exec(t))) marks.push([m[1], m.index, m.index + m[0].length]);
  if (!marks.length) { fsNote('no "=== BEAT n ===" lines found in it'); return; }
  let n = 0; marks.forEach((mk, i) => { const end = i + 1 < marks.length ? marks[i + 1][1] : t.length;
    if (FS_STORY[mk[0]] !== undefined) { FS_STORY[mk[0]] = t.slice(mk[2], end).trim(); n++; } });
  fsTales().forEach(d => { const b = d.querySelector('textarea');
    if (b) b.value = FS_STORY[d.dataset.k]; else d.innerHTML = fsHtml(FS_STORY[d.dataset.k]); });
  fsStash(); fsNote(n + ' beats put in'); }
function fsStash(){ try { localStorage.setItem('fsstory:' + FS_PAGE, JSON.stringify(FS_STORY)); } catch(e) {} }
function fsSave(){ if (fsEditing) fsEdit();
  document.getElementById('fs-story').textContent = JSON.stringify(FS_STORY);
  const bulk = document.getElementById('fsBulk'); if (bulk) bulk.value = '';
  const ask = document.getElementById('fsAsk'); if (ask) ask.textContent = ask.value;
  fsDownload(FS_PAGE + '.html', '<!doctype html>\n' + document.documentElement.outerHTML, 'text/html');
  try { localStorage.removeItem('fsstory:' + FS_PAGE); } catch(e) {}
  fsNote('saved: keep the downloaded page in place of this one (it has your edits in it)'); }
window.addEventListener('load', () => { try { const o = JSON.parse(localStorage.getItem('fsstory:' + FS_PAGE) || 'null');
  if (o) { Object.assign(FS_STORY, o); fsTales().forEach(d => d.innerHTML = fsHtml(FS_STORY[d.dataset.k] || ''));
    fsNote('your unsaved edits are back'); } } catch(e) {} });
"""


def _edit_script(rules, stories, base):
    if not _edit_on(rules):
        return ""
    blob = json.dumps({str(k): v for k, v in stories.items()}, ensure_ascii=False).replace("</", "<\\/")
    return (f'<script id="fs-story" type="application/json">{blob}</script>'
            f'<script>const FS_PAGE={json.dumps(os.path.basename(base))};{EDIT_PAGE_JS}</script>')


MARK = re.compile(r"^=== BEAT (\d+)(?: [^=]*)?===\s*$", re.M)


def story_text(text):
    """A beat's story alone, as plain text: its paragraphs (a fighter's heading, "— Ripples —", on a line of its own)
    with a blank line between them; no stat lines, no rolls, no announcements."""
    story, _m, _r = _split(text)
    return "\n\n".join(x[1] if isinstance(x, tuple) else x for x in story)


def with_story(text, new_story):
    """A beat's full text with its story swapped for new_story: the lines above the story (the attack headings)
    and everything from the stat lines on are kept as they were."""
    lines = (text or "").splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip() and not PROGRESS.match(ln) and not RULE.match(ln.strip())
                  and not MECH.match(ln) and not CONSOLE_HINT.search(ln.strip())), len(lines))
    end = next((i for i in range(start, len(lines)) if RULE.match(lines[i].strip()) and lines[i].strip().startswith("-")),
               len(lines))
    return "\n".join(lines[:start] + [""] + new_story.strip().splitlines() + [""] + lines[end:])


def whole_story(recs, stories=None):
    """The whole fight's story as one text, each beat under a line of its own ("=== BEAT 3 (beat 3) ==="): what
    Venice (or anyone) gets to rewrite, and splits back into beats by those lines."""
    out = []
    for k, r in enumerate(recs):
        st = (stories or {}).get(k, story_text(r.get("text", "")))
        out.append(f"=== BEAT {k} ({r.get('label') or 'beat ' + str(r.get('turn'))}) ===\n{st.strip()}")
    return "\n\n".join(out) + "\n"


def split_story(text):
    """The beats back out of a whole-fight text: {beat number: its story}."""
    marks = list(MARK.finditer(text or ""))
    return {int(m.group(1)): text[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(text))].strip()
            for i, m in enumerate(marks)}


EDITOR_JS = r"""
const KEY = 'fsedit:' + document.title + ':' + FS_SAVED;
const boxes = () => Array.from(document.querySelectorAll('textarea.beat'));
function allText(){ return boxes().map(b => '=== BEAT ' + b.dataset.k + ' (' + b.dataset.label + ') ===\n'
  + b.value.trim()).join('\n\n') + '\n'; }
function header(){ return document.getElementById('ask').value.trim(); }
function stash(){ try { const o = {}; boxes().forEach(b => o[b.dataset.k] = b.value);
  localStorage.setItem(KEY, JSON.stringify(o)); } catch(e) {} note('saved in this browser'); }
function note(t){ const n = document.getElementById('note'); n.textContent = t; clearTimeout(n._t);
  n._t = setTimeout(() => n.textContent = '', 2500); }
function copy(t){ if (navigator.clipboard && window.isSecureContext !== false) {
    navigator.clipboard.writeText(t).then(() => note('copied'), () => fallback(t)); } else fallback(t); }
function fallback(t){ const a = document.createElement('textarea'); a.value = t; document.body.appendChild(a);
  a.select(); try { document.execCommand('copy'); note('copied'); } catch(e) { note('select and copy by hand'); }
  a.remove(); }
function download(name, text, type){ const b = new Blob([text], {type: type || 'text/plain'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
function copyAll(withAsk){ copy((withAsk && header() ? header() + '\n\n' : '') + allText()); }
function copyOne(k){ const b = boxes().find(x => x.dataset.k == k);
  copy((header() ? header() + '\n\n' : '') + '=== BEAT ' + k + ' (' + b.dataset.label + ') ===\n' + b.value.trim()); }
async function pasteOne(k){ const b = boxes().find(x => x.dataset.k == k);
  try { b.value = stripMark(await navigator.clipboard.readText()); stash(); }
  catch(e) { b.focus(); b.select(); note('press Ctrl+V to paste'); } }
function stripMark(t){ return t.replace(/^\s*=== BEAT \d+[^=]*===\s*\n?/, '').trim(); }
function applyAll(){ const t = document.getElementById('bulk').value; const re = /^=== BEAT (\d+)[^=\n]*===\s*$/gm;
  const marks = []; let m; while ((m = re.exec(t))) marks.push([+m[1], m.index, m.index + m[0].length]);
  if (!marks.length) { note('no "=== BEAT n ===" lines found in it'); return; }
  let n = 0; marks.forEach((mk, i) => { const end = i + 1 < marks.length ? marks[i + 1][1] : t.length;
    const b = boxes().find(x => x.dataset.k == mk[0]); if (b) { b.value = t.slice(mk[2], end).trim(); n++; } });
  stash(); note(n + ' beats put in'); }
function saveAll(){ boxes().forEach(b => { b.textContent = b.value; });
  const a = document.getElementById('ask'); a.textContent = a.value;
  document.getElementById('bulk').textContent = '';
  download(FS_NAME + '_editor.html', '<!doctype html>\n' + document.documentElement.outerHTML, 'text/html');
  stash(); note('saved: keep the downloaded page (it has your edits in it)'); }
function resetAll(){ if (!confirm('Put every beat back to the story the game wrote?')) return;
  boxes().forEach(b => b.value = FS_ORIG[b.dataset.k] || ''); try { localStorage.removeItem(KEY); } catch(e) {} }
window.addEventListener('load', () => { try { const o = JSON.parse(localStorage.getItem(KEY) || '{}');
  boxes().forEach(b => { if (o[b.dataset.k] !== undefined) b.value = o[b.dataset.k]; }); } catch(e) {}
  boxes().forEach(b => b.addEventListener('input', () => { clearTimeout(b._t); b._t = setTimeout(stash, 800); })); });
"""

EDITOR_CSS = """
:root{--bg:#f8fafc;--fg:#111827;--dim:#6b7280;--box:#ffffff;--line:#d1d5db;--acc:#2563eb}
@media (prefers-color-scheme: dark){:root{--bg:#111827;--fg:#e5e7eb;--dim:#9ca3af;--box:#1f2937;--line:#374151;--acc:#60a5fa}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 Georgia,serif;margin:0 auto;max-width:980px;padding:16px}
header{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:2}
h1{font-size:22px;margin:0}.dim{color:var(--dim);font-size:13px}
button{font:13px system-ui,sans-serif;padding:5px 10px;margin:3px 4px 3px 0;border:1px solid var(--line);
 border-radius:6px;background:var(--box);color:var(--fg);cursor:pointer}button:hover{border-color:var(--acc)}
textarea{width:100%;box-sizing:border-box;background:var(--box);color:var(--fg);border:1px solid var(--line);
 border-radius:6px;padding:10px;font:15px/1.55 Georgia,serif;resize:vertical}
textarea.beat{min-height:260px}section{margin:22px 0}h2{font-size:17px;margin:0 0 4px}
details{margin:6px 0}summary{cursor:pointer;color:var(--dim);font:13px system-ui,sans-serif}
.res{font:13px system-ui,sans-serif;color:var(--dim)}#note{color:var(--acc);font:13px system-ui,sans-serif}
"""

EDITOR_ASK = ("Rewrite the prose of each beat below so it reads better. Keep every '=== BEAT n (...) ===' line exactly "
              "as it is, in the same order, with that beat's story under it. Keep what happens, who does what to "
              "which body part, and the order of events; change only the writing. Past tense. No new events.")


def write_editor(base, title, arena, recs):
    """(since build 344, export.editor) <fight>_editor.html: every beat's story in a box you can edit, to copy out to
    Venice.ai (one beat, or the whole fight as one text with an "=== BEAT n ===" line over each beat) and paste its
    rewrite straight back in (each box, or the whole fight at once: it is split back into the beats by those lines).
    Edits are kept in the browser as you type; Save downloads the page itself with the edits written into it (keep
    it in place of the old one). Returns its path."""
    name = os.path.basename(base)
    orig = {k: story_text(r.get("text", "")) for k, r in enumerate(recs)}
    secs = []
    for k, r in enumerate(recs):
        label = r.get("label") or f"beat {r.get('turn')}"
        _st, _m, results = _split(r.get("text", ""))
        res = "".join(f"<div class=res>{html.escape(x)}</div>" for x in results)
        heads = [ln.strip() for ln in (r.get("text") or "").splitlines() if re.match(r"^\s*(?:Attack \d|Impact —)", ln)]
        what = (f"<details><summary>what happened</summary><div class=res>"
                f"{'<br>'.join(html.escape(h) for h in heads) or 'no attack (a pause, a hold, a pin)'}</div></details>")
        secs.append(f'<section><h2>{html.escape(label[:1].upper() + label[1:])}</h2>{what}{res}'
                    f'<button onclick="copyOne({k})">Copy this beat</button>'
                    f'<button onclick="pasteOne({k})">Paste over it</button>'
                    f'<textarea class="beat" data-k="{k}" data-label="{html.escape(label, quote=True)}" spellcheck="true">'
                    f'{html.escape(orig[k])}</textarea></section>')
    saved = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    page = (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>{html.escape(title or "Fight")} (story editor)</title><style>{EDITOR_CSS}</style>'
            f'</head><body><header><h1>{html.escape(title or "Fight")}: the story</h1>'
            f'<div class=dim>{html.escape(arena)} · {len(recs)} beats · saved {saved}. Edits are kept in this browser '
            f'as you type.</div>'
            f'<button onclick="copyAll(true)">Copy the whole fight for Venice</button>'
            f'<button onclick="download(FS_NAME + \'_story.txt\', (header() ? header() + \'\\n\\n\' : \'\') + allText())">'
            f'Download it as a .txt file</button>'
            f'<button onclick="saveAll()">Save the page</button><button onclick="resetAll()">Undo all edits</button> '
            f'<span id=note></span></header>'
            f'<details><summary>what Venice is asked (put above the text when you copy it; edit it freely)</summary>'
            f'<textarea id=ask rows=3>{html.escape(EDITOR_ASK)}</textarea></details>'
            f'<details><summary>paste the whole fight back (Venice\'s answer with its "=== BEAT n ===" lines)</summary>'
            f'<textarea id=bulk rows=8 placeholder="Paste the whole rewritten fight here"></textarea>'
            f'<button onclick="applyAll()">Put it into the beats</button></details>'
            f'{"".join(secs)}<script>const FS_NAME={json.dumps(name)};const FS_SAVED={json.dumps(saved)};'
            f'const FS_ORIG={json.dumps(orig, ensure_ascii=False)};'
            f'{EDITOR_JS}</script></body></html>')
    path = base + "_editor.html"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return path
