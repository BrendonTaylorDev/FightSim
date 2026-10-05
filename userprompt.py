"""Loads your plain-English story prompt and style sample. Read fresh every beat, so edits apply live."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def _read(name):
    if not name:
        return ""
    path = name if os.path.isabs(name) else os.path.join(HERE, name)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def story_prompt(rules):
    text = _read(rules.get("narration", {}).get("story_prompt_file", "story_prompt.txt"))
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#")).strip()


STAT_LINE = re.compile(
    r"(\d+\s*[→>-]+\s*\d+|·\s*-?\d|✓|✗|[🟢🟡🟠🔴🟣⚫💙💚💛🧡❤🟦🟩🟨🟧🟥]|^\s*(?:Before|After)\s*[:=(\d]|^\s*(?:Calculations|Pin conditions|"
    r"Total inflicted|Attack \d+)\b|^\s*[-•]\s*\w[\w ]*:\s*\S*\s*\d+%|^[\s\d·%|−+\-.,]+$)", re.I)


def strip_stats(text):
    """Remove stat/bookkeeping lines (numbers, arrows, check marks, tier icons) so the model only sees prose."""
    return "\n".join(l for l in text.splitlines() if not STAT_LINE.search(l))


SECTION = re.compile(r"(?m)^==+[ \t]*([^=\n]+?)[ \t]*=*[ \t]*$")


def sample_sections(text):
    """[(tags, passage)] for a style sample written in sections: a line "== pin hold, pin" starts a passage that
    shows that KIND of moment. Lines starting with # are notes. [] for a plain sample (no such lines)."""
    marks = list(SECTION.finditer(text or ""))
    out = []
    for i, m in enumerate(marks):
        body = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        body = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#")).strip()
        tags = [t.strip().lower() for t in m.group(1).split(",") if t.strip()]
        if body and tags:
            out.append((tags, body))
    return out


def _cut(text, limit):
    if len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        text = text[: cut if cut > limit // 2 else limit]
    return text


def sample_text(rules):
    """The whole style sample file as prose (every section of a sectioned one), for checking what was copied from it."""
    raw = strip_stats(_read(rules.get("narration", {}).get("style_sample_file", "style_sample.txt")))
    secs = sample_sections(raw)
    return "\n\n".join(body for _, body in secs) if secs else raw.strip()


def style_passages(rules, want=None, limit=None, rounds=None, skip=()):
    """The passages of the style sample to show the narrator for the part it is about to write.
    A plain sample: its first style_sample_chars characters, as always. A sample in sections: the sections whose
    tags are asked for in `want` (in that order: the first is the one that fits best), as many as fit in
    style_sample_chars; with nothing asked for, or nothing matching, its first section."""
    n = rules.get("narration", {})
    raw = strip_stats(_read(n.get("style_sample_file", "style_sample.txt")))
    cap = int(n.get("style_sample_chars", 3000))
    if limit is not None:
        cap = min(cap, int(limit))
    secs = sample_sections(raw)
    if not secs:
        text = _cut(raw.strip(), cap) if cap > 0 else ""
        return [text] if text else []
    if cap <= 0:
        return []
    # rounds: {tag: how many times a passage for that tag has been shown}: sections that share a tag take turns.
    # skip: words (a fighter who is not in this fight) whose passages are left out
    if skip:
        rx = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in skip if w) + r")\b")   # as a name: capitalized
        secs = [sec for sec in secs if not rx.search(sec[1])] or secs
    picked = []
    for w in [str(x).strip().lower() for x in (want or [])]:
        fits = [sec for sec in secs if w in sec[0] and sec not in picked]
        if fits:
            picked.append(fits[int((rounds or {}).get(w, 0)) % len(fits)])
    if not picked:
        picked = [secs[0]]
    out, used = [], 0
    for _, body in picked:
        if not out:
            body = _cut(body, cap)
        elif used + len(body) > cap:
            continue
        out.append(body)
        used += len(body)
    return out


def style_sample(rules):
    """The style sample as one text (a sectioned sample: its default passages)."""
    return "\n\n".join(style_passages(rules))
