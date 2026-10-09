"""/exportfight: a whole fight saved beat by beat, so nothing is lost when the program closes.

Writes two files into the exports folder (or where you say):
  <name>.html  a page for your browser: every beat's story and stat lines, and beside it each fighter as she stood
               after that beat (her picture with each hurt part glowing, a line from every part to its damage and
               resistance, health and energy), plus a table of every part.
  <name>.json  the same data, plain (the text of each beat and every fighter's numbers)."""
import base64
import datetime
import html
import io
import json
import os
import re

import cards

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


def _split(text):
    """A beat's text as (story paragraphs, stat lines)."""
    story, mech = [], []
    para = []
    in_stats = False
    for line in (text or "").splitlines():
        s = line.strip()
        if PROGRESS.match(line):
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
    return story, mech


def _card_img(f, pics):
    data, own = pics.get(f["name"], (None, False))
    img = cards.render_card(f, data, own)
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
.bar.thin{height:12px}.bar span{position:absolute;left:0;top:0;bottom:0}.bar em{position:relative;padding-left:6px;
font:600 11px/18px system-ui,sans-serif;font-style:normal;color:#111}.bar.thin em{line-height:12px;font-size:10px}
details{margin-top:8px;font:13px system-ui,sans-serif}summary{cursor:pointer;color:#2563eb}
pre{white-space:pre-wrap;font:12px/1.45 Consolas,monospace;color:var(--dim);margin:6px 0 0}
table{border-collapse:collapse;width:100%;margin-top:6px}td,th{padding:2px 6px;border-bottom:1px solid var(--line);text-align:left}
td.n{text-align:right}.chip{display:inline-block;min-width:58px;padding:0 4px;border-radius:3px;text-align:center;font-weight:600}
.chip.res{border:2px solid;background:transparent;font-weight:400}
"""


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
    pics = {}
    for r in recs:
        for f in r["snapshot"]["fighters"]:
            if f["name"] not in pics:
                pics[f["name"]] = cards.picture_bytes(f["name"], f.get("species") or f["name"])
    title = " vs ".join(recs[0].get("lineup") or [])
    arena = (getattr(s.eng, "scene_cfg", None) or {}).get("title", "")
    nav, body = [], []
    for k, r in enumerate(recs):
        fight = r.get("fight")
        label = r.get("label") or f"beat {r.get('turn')}"
        head = (f"Fight {fight}: " if fights is None or len(fights or []) > 1 else "") + label[:1].upper() + label[1:]
        nav.append(f'<a href="#b{k}">{html.escape(label)}</a>')
        story, mech = _split(r.get("text", ""))
        st = "".join(f'<div class="pov">{html.escape(x[1])}</div>' if isinstance(x, tuple) else f"<p>{_md(x)}</p>"
                     for x in story)
        mech_html = (f'<details><summary>stat lines and rolls</summary><pre>{_md(chr(10).join(mech))}</pre></details>'
                     if mech else "")
        side = ""
        for f in r["snapshot"]["fighters"]:
            img = _card_img(f, pics)
            sts = ", ".join(f"{k.replace('_', ' ')} ({v})" if isinstance(v, (int, float)) and not isinstance(v, bool)
                            else k.replace("_", " ") for k, v in (f.get("status") or {}).items()) or "no statuses"
            side += (f'<div class="fighter">{img}<div class="dim">{html.escape(f.get("posture", ""))} · '
                     f'{html.escape(sts)}</div>{_table(f)}</div>' if img else
                     f'<div class="fighter">{_bars(f)}{_table(f)}</div>')
        body.append(f'<section id="b{k}"><h2>{html.escape(head)}</h2><div class="story">{st or "<p class=dim>(no story text for this beat)</p>"}'
                    f'{mech_html}</div><div class="side">{side}</div></section>')
    page = (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>{html.escape(title or "Fight")}</title><style>{CSS}</style></head><body>'
            f'<header><h1>{html.escape(title)}</h1><div class="dim">{html.escape(arena)} · saved '
            f'{datetime.datetime.now():%Y-%m-%d %H:%M} · {len(recs)} beats</div></header>'
            f'<nav>{"".join(nav)}</nav>{"".join(body)}</body></html>')
    with open(base + ".html", "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump({"title": title, "arena": arena, "beats": recs}, fh, ensure_ascii=False, indent=1)
    return base + ".html"
