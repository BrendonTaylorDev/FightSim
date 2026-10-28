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
            out += (f'<svg class="vitals" viewBox="0 0 {w + 90} {60 if v.get("squeeze") is not None and not figure else 44}" width="100%" style="background:#111827;'
                    f'border-radius:4px;max-width:520px">'
                    f'<text x="6" y="16" fill="{"#ef4444" if v.get("stopped") else col}" font-size="11" '
                    f'font-weight="bold">{"♥ stopped" if v.get("stopped") else "♥ " + str(v["heart"]) + "/min"}</text>'
                    + ('<text x="6" y="29" fill="#fca5a5" font-size="8">irregular</text>' if v.get("irregular") else "")
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
                    f'</svg>')
            if figure:
                body, belly = cards.picture_colours((books or {}).get(f["name"]), "#c08457")
                coil = cards.picture_colours((books or {}).get(v.get("coiler")), "#5d8fcf")[0]
                out += cards.squeeze_svg(v, body, coil, belly)
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
.result{margin:14px 0 4px;padding:8px 12px;border-left:4px solid #b45309;background:var(--card);
font:600 15px system-ui,sans-serif}
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
        body.append(f'<section id="b{k}"><h2>{html.escape(head)}</h2><div class="story">{st}'
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
