"""narration.polish (since build 268): a second, stronger model improves the prose of a finished beat.

The local model writes the beat as always, with the engine's notes and every check behind it. Then the finished
beat, with a short fact sheet of what really happened, is sent to an online model (Venice.ai by default; any
service that speaks the OpenAI chat format works) to make the writing better without changing what happens. Its
version is kept only when the program's own checks find nothing in it that the local version had right, it keeps
every "— Name —" part label, every fighter, and no less than about half its length, and it is not a refusal (it may be
longer: since build 303 there is no upper limit unless max_ratio sets one). Otherwise the
local version stands. Nothing is sent anywhere unless you turn it on.

The same request can instead be copied out by hand (/polish copy) and the answer pasted back (/polish paste), so
the fight stays in the game and its window either way."""
import json
import os
import re
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(HERE, "polish_key.txt")
REQUEST_FILE = os.path.join(HERE, "polish_request.txt")
REPLY_FILE = os.path.join(HERE, "polish_reply.txt")
PROMPT_FILE = os.path.join(HERE, "polish_prompt.txt")   # (your own instructions for the editor: /polish prompt)

DEFAULTS = {"enabled": False, "when": "every", "base_url": "https://api.venice.ai/api/v1", "model": "",
            "temperature": 0.7, "timeout": 120, "min_ratio": 0.55, "max_ratio": 0, "allow_new_slips": 0,
            "expand": True,
            "extra_body": {"venice_parameters": {"include_venice_system_prompt": False}}}

SYSTEM = (
    "You are an expert fiction editor. You improve the prose of one beat of an ongoing story about a fight between "
    "two Pokemon. You are given FACTS (worked out by a game engine, never to be changed: WHO each fighter is and "
    "what her body has, WHERE they are, what really happened in this beat, and how each one is at the end of it) "
    "and the DRAFT (the beat as written). Rewrite the draft into better prose.\n"
    "BODIES: give each fighter only the body WHO describes (her fur, her tails, her fins, her paws, as they are "
    "there); nothing she lacks, nothing of the other's. The arena is as WHERE says.\n"
    "MAKE IT BETTER: vary the sentence length and rhythm; cut repetition, filler, stock phrases and anything that "
    "reads like notes or a list; make the senses, the effort and the pain vivid and specific; keep each fighter's "
    "inner voice (her thoughts in *italics*) and the sounds she makes; let the big moments breathe and the small "
    "ones move quickly; smooth anything clumsy or contradictory.\n"
    "NEVER CHANGE WHAT HAPPENS: every action, hit, body part, hold, tap, get-up, fall and outcome in the FACTS "
    "stays exactly as it is there, in the same order. Add no new moves, blows, injuries, falls, escapes, words "
    "spoken or events; remove none of those in the FACTS.\n"
    "PUT THE DRAFT'S MISTAKES RIGHT: the draft was written quickly and can be wrong. When it tells one blow twice, "
    "tell it once, where it happens. When it gives an attack to the wrong fighter or the wrong limb (a bite from "
    "one who only kneed, a fist in a knee strike), or says a grip let go that the FACTS say is still on, follow the "
    "FACTS. Anything the draft has happen that the FACTS don't support goes. Follow the FACTS on how fresh or worn "
    "each fighter is: a thought or a look that has a fresh fighter tiring or running out goes. Size every hurt to the condition the FACTS give (a sore part "
    "is not agony, an excruciating one is not a sting; a part at 100% damage or more is badly hurt). Left and "
    "right stay as they are. No gore beyond what the "
    "draft has.\n"
    "KEEP THE FORM: past tense, third person; each fighter is 'she'. Keep every line that looks like "
    "'— Name —' exactly as it is, on its own line, in the same order, with that fighter's part of the story "
    "under it. Cut filler and repetition freely, but keep every event and every concrete detail of what happened "
    "(which part was hit, with what, what she did after); don't go under about two thirds of the draft's length. "
    "Don't lean on dashes, and don't chop the prose into strings of fragments ('Ears flat. Clarity. Control.'): "
    "mostly full sentences, a short one now and then for weight. Answer with the revised beat only: no "
    "title, no notes, no explanation, nothing before or after it.")


def system_prompt():
    """The editor's instructions: yours from polish_prompt.txt when it has any (/polish prompt edit), else the
    built-in ones (/polish prompt reset goes back to them)."""
    try:
        with open(PROMPT_FILE, encoding="utf-8") as fh:
            mine = fh.read().strip()
        if mine:
            return mine
    except OSError:
        pass
    return SYSTEM


def prompt_is_custom():
    return system_prompt() is not SYSTEM


def cfg_of(rules):
    """narration.polish with its defaults filled in."""
    c = dict(DEFAULTS)
    c.update({k: v for k, v in ((rules.get("narration") or {}).get("polish") or {}).items() if not k.startswith("_")})
    return c


def api_key(rules):
    """The key for the online model: the POLISH_API_KEY or VENICE_API_KEY environment variable, then
    polish_key.txt next to the game (/polish key writes it; it is never committed), then narration.polish.api_key."""
    for var in ("POLISH_API_KEY", "VENICE_API_KEY"):
        if os.environ.get(var, "").strip():
            return os.environ[var].strip()
    try:
        with open(KEY_FILE, encoding="utf-8") as fh:
            k = fh.read().strip()
            if k:
                return k
    except OSError:
        pass
    return str(cfg_of(rules).get("api_key") or "").strip()


def save_key(key):
    with open(KEY_FILE, "w", encoding="utf-8") as fh:
        fh.write(key.strip() + "\n")
    return KEY_FILE


class PolishError(RuntimeError):
    pass


def _request(rules, path, body=None):
    c = cfg_of(rules)
    key = api_key(rules)
    if not key:
        raise PolishError("no API key: type /polish key <your key> (it is kept in polish_key.txt, never in rules.json)")
    url = str(c["base_url"]).rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Authorization": f"Bearer {key}",
                                                         "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=float(c.get("timeout", 120))) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        raise PolishError(f"the service answered HTTP {e.code}: {detail or e.reason}") from e
    except urllib.error.URLError as e:
        raise PolishError(f"can't reach {url} ({e.reason})") from e
    except (ValueError, OSError) as e:
        raise PolishError(f"{e}") from e


def list_models(rules):
    """The model names the service offers (for /polish models)."""
    out = _request(rules, "/models")
    return sorted(str(m.get("id")) for m in out.get("data") or [] if m.get("id"))


# (since build 303, narration.polish.expand) leave to make it longer: the editor is no longer held to the draft's length
EXPAND_NOTE = ("LENGTH: you are not held to the draft's length. Where it makes the beat better, make it longer: more of "
               "what each fighter sees, hears, feels and thinks, more of the effort, the pain and the moment between "
               "the blows, the big moments given room. Every word of it is still about what the FACTS have happen: "
               "nothing longer means nothing new happening.\n\n")


def messages(draft, facts, prior="", rules=None):
    """The request: the editor's instructions, the facts, the story just before this beat, and the draft. rules: with
    narration.polish.expand on (since build 303), the editor is told it may make the beat longer."""
    chars = [f for f in facts if f and str(f).startswith(("CHARACTER:", "(her character"))]
    user = ("FACTS (what really happened in this beat; never change them):\n"
            + "\n".join(f"- {f}" for f in facts if f) + "\n\n"
            # (since build 281, narration.character) who they are: the editor may give their prose that personality
            + ("CHARACTER: each fighter's CHARACTER line above is who she is. Give her thoughts, her manner and the way "
               "she moves that personality, let her history and what the other is to her colour what she thinks, and "
               "show each '(her character...)' note in how she does what the FACTS say she does. Character never adds "
               "an event, a blow, a word spoken aloud or a memory beyond her HISTORY.\n\n" if chars else "")
            + (f"THE STORY JUST BEFORE THIS BEAT (for continuity only; do not rewrite it or repeat it):\n"
               f"{prior.strip()[-1500:]}\n\n" if prior and prior.strip() else "")
            + (EXPAND_NOTE if rules is not None and cfg_of(rules).get("expand", True) else "")
            + "DRAFT (rewrite this):\n" + draft.strip())
    return [{"role": "system", "content": system_prompt()}, {"role": "user", "content": user}]


def call(rules, msgs):
    """One request to the online model. Returns its text."""
    c = cfg_of(rules)
    if not str(c.get("model") or "").strip():
        raise PolishError("no model chosen: /polish models lists them, then /polish model <name>")
    body = {"model": c["model"], "messages": msgs, "temperature": float(c.get("temperature", 0.7))}
    if "venice.ai" in str(c["base_url"]) and isinstance(c.get("extra_body"), dict):
        body.update(c["extra_body"])     # (Venice's own system prompt off: ours is the only one)
    out = _request(rules, "/chat/completions", body)
    try:
        return str(out["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as e:
        raise PolishError(f"an answer in a shape it doesn't know: {str(out)[:200]}") from e


REFUSAL = re.compile(r"^\s*(?:I'?m sorry|I am sorry|I can(?:'|no)t|I won'?t|I am unable|I'm unable|As an AI|"
                     r"Sorry,)", re.I)
PREFACE = re.compile(r"^\s*(?:here(?:'s| is) (?:the |your |a )?(?:revised|improved|edited|rewritten|polished)[^\n]*|"
                     r"(?:revised|improved|edited) (?:beat|version|draft)[^\n]*:)\s*\n", re.I)
LABEL = re.compile(r"(?m)^\s*—\s*[^—\n]+?\s*—\s*$")


def tidy(text, names=(), draft=""):
    """The model's answer as a beat: no "Here is the revised beat:" line, no code fences, no closing note. A part
    label that lost a dash ("Nerine —", "- Nerine -") is put back as "— Nerine —", and when the draft starts with a
    label, anything before the answer's first label goes (a chat page's own text copied along with it, "Worked for
    22s · 1 step")."""
    t = str(text or "").strip()
    for n in names or ():
        t = re.sub(r"(?m)^[ \t]*(?:[—–-]+[ \t]*)?" + re.escape(n) + r"(?:[ \t]*[—–-]+)?[ \t]*:?[ \t]*$",
                   f"— {n} —", t)
    if LABEL.match(str(draft or "").lstrip()):
        m = LABEL.search(t)
        if m and m.start() > 0:
            t = t[m.start():]
    t = re.sub(r"^```\w*\s*\n|\n```\s*$", "", t).strip()
    t = PREFACE.sub("", t, count=1).strip()
    t = re.sub(r"\n+\s*(?:---+\s*\n+)?(?:\*\*)?(?:Notes?|Changes(?: made)?|Edits?)(?:\*\*)?:[\s\S]*$", "", t).strip()
    return t


def judge(narrator, draft, polished, names, rules, facts=()):
    """(keep it?, why not). It is kept only when it is not a refusal, keeps every "— Name —" label in order and
    every fighter the draft names, is at least min_ratio of the draft's length (and at most max_ratio, when that is set:
    0, the default since build 303, is no upper limit), and the program's own
    sentence checks find no more in it than in the draft (allow_new_slips more at most)."""
    c = cfg_of(rules)
    if not polished.strip():
        return False, "it came back empty"
    if REFUSAL.search(polished):
        return False, "it refused"
    want = [re.sub(r"\s+", " ", x).strip() for x in LABEL.findall(draft)]
    got = [re.sub(r"\s+", " ", x).strip() for x in LABEL.findall(polished)]
    if want != got:
        return False, f"it changed the part labels ({' '.join(want) or 'none'} → {' '.join(got) or 'none'})"
    # (her name in a "— Name —" label doesn't count: she must still be in the story itself)
    bare_d, bare_p = LABEL.sub("", draft), LABEL.sub("", polished)
    missing = [n for n in names if re.search(r"\b" + re.escape(n) + r"\b", bare_d)
               and not re.search(r"\b" + re.escape(n) + r"\b", bare_p)]
    if missing:
        return False, f"it left out {', '.join(missing)}"
    # every body part the beat's blows landed on that the draft tells must still be told ("Left Forearm Fin": its
    # last word, "fin", is enough)
    hit = [p.strip() for f in facts or () for m_ in [re.search(r"\((?:targeted|spread|whole_body)\s*[—-]\s*([^)]*)\)",
                                                               str(f))] if m_ for p in m_.group(1).split(",")
           if p.strip()[:1].isupper() and "energy" not in p]
    for part in dict.fromkeys(hit):
        key = part.lower().split()[-1]
        if re.search(r"\b" + re.escape(key), draft.lower()) and not re.search(r"\b" + re.escape(key), polished.lower()):
            return False, f"it left out her {part.lower()}, which the blow landed on"
    wd, wp = len(draft.split()), len(polished.split())
    ratio = wp / max(1, wd)
    top = float(c.get("max_ratio", 0) or 0)       # (0: no upper limit, since build 303)
    if ratio < float(c.get("min_ratio", 0.7)):
        return False, f"it cut too much of it ({wd} → {wp} words)"
    if top > 0 and ratio > top:
        return False, f"it made it longer than max_ratio allows ({wd} → {wp} words, over {top:g}x)"
    if narrator is not None:
        try:
            before = narrator._bad_sentences(draft)
            after = narrator._bad_sentences(polished)
        except Exception as e:
            from engine import note_failure
            note_failure("the polish check (the narrator's sentence checks)", e)
            return True, ""
        extra = len(after) - len(before)
        if extra > int(c.get("allow_new_slips", 0)):
            worst = next(iter(w for s, w in after.items() if s not in before), "")
            return False, f"the checks found more wrong in it ({len(before)} → {len(after)}: {worst[:120]})"
    return True, ""


def request_text(draft, facts, prior="", rules=None):
    """The whole request as one block of text, to paste into a chat window by hand (/polish copy)."""
    m = messages(draft, facts, prior, rules)
    return (m[0]["content"] + "\n\n" + m[1]["content"] + "\n")


# (since build 271) several beats in one request, for pasting into a chat window by hand (/polish copy 4)
BATCH_NOTE = ("SEVERAL BEATS: below are {n} beats of the same fight, in order, each between a line '=== BEAT n ===' "
              "and a line '=== END BEAT n ===' (n is the beat's number). Edit each one by itself, by all the rules above, using only its own "
              "FACTS (each beat's FACTS are what is true at the end of THAT beat). Answer with every beat, in the "
              "same order, each between the same two marker lines with the same number, and nothing else.")
MARK = re.compile(r"(?m)^\s*\**\s*===\s*BEAT\s+(\d+)\s*===\s*\**\s*$")
END_MARK = re.compile(r"(?m)^\s*\**\s*===\s*END\s+BEAT\s+(\d+)\s*===\s*\**\s*$")


def batch_request(items, rules=None):
    """The whole request for several beats as one block of text: items = [(beat number, draft, facts, prior)],
    oldest first; only the first carries the story before it (the beats after follow on from each other)."""
    out = [system_prompt(), "", BATCH_NOTE.format(n=len(items)), ""]
    for i, (k, draft, facts, prior) in enumerate(items):
        user = messages(draft, facts, prior if i == 0 else "", rules)[1]["content"]
        out += [f"=== BEAT {k} ===", user, f"=== END BEAT {k} ===", ""]
    return "\n".join(out)


def split_batch(reply):
    """{k: that beat's answer} from a reply to batch_request, by its marker lines ({} when it has none)."""
    text = str(reply or "")
    starts = list(MARK.finditer(text))
    out = {}
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        body = text[m.end():end]
        e = END_MARK.search(body)
        out[int(m.group(1))] = (body[:e.start()] if e else body).strip()
    return out
