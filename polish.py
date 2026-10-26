"""narration.polish (since build 268): a second, stronger model improves the prose of a finished beat.

The local model writes the beat as always, with the engine's notes and every check behind it. Then the finished
beat, with a short fact sheet of what really happened, is sent to an online model (Venice.ai by default; any
service that speaks the OpenAI chat format works) to make the writing better without changing what happens. Its
version is kept only when the program's own checks find nothing in it that the local version had right, it keeps
every "— Name —" part label, every fighter, and roughly the same length, and it is not a refusal. Otherwise the
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

DEFAULTS = {"enabled": False, "when": "every", "base_url": "https://api.venice.ai/api/v1", "model": "",
            "temperature": 0.7, "timeout": 120, "min_ratio": 0.7, "max_ratio": 1.5, "allow_new_slips": 0,
            "extra_body": {"venice_parameters": {"include_venice_system_prompt": False}}}

SYSTEM = (
    "You are an expert fiction editor. You improve the prose of one beat of an ongoing story about a fight between "
    "two Pokemon. You are given FACTS (what really happened in this beat, worked out by a game engine: these are "
    "never to be changed) and the DRAFT (the beat as written). Rewrite the draft into better prose.\n"
    "MAKE IT BETTER: vary the sentence length and rhythm; cut repetition, filler, stock phrases and anything that "
    "reads like notes or a list; make the senses, the effort and the pain vivid and specific; keep each fighter's "
    "inner voice (her thoughts in *italics*) and the sounds she makes; let the big moments breathe and the small "
    "ones move quickly; smooth anything clumsy or contradictory.\n"
    "NEVER CHANGE WHAT HAPPENS: every action, hit, body part, hold, tap, get-up, fall and outcome stays exactly "
    "as in the FACTS and the draft. Add no new moves, blows, injuries, falls, escapes, words spoken or events; "
    "remove none of those that are there; never move one before or after another. Where the draft contradicts "
    "the FACTS, follow the FACTS. Left and right stay as they are. No gore beyond what the draft has.\n"
    "KEEP THE FORM: past tense, third person; each fighter is 'she'. Keep every line that looks like "
    "'— Name —' exactly as it is, on its own line, in the same order, with that fighter's part of the story "
    "under it. Keep roughly the same length (within a fifth). Answer with the revised beat only: no title, no "
    "notes, no explanation, nothing before or after it.")


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


def messages(draft, facts, prior=""):
    """The request: the editor's instructions, the facts, the story just before this beat, and the draft."""
    user = ("FACTS (what really happened in this beat; never change them):\n"
            + "\n".join(f"- {f}" for f in facts if f) + "\n\n"
            + (f"THE STORY JUST BEFORE THIS BEAT (for continuity only; do not rewrite it or repeat it):\n"
               f"{prior.strip()[-1500:]}\n\n" if prior and prior.strip() else "")
            + "DRAFT (rewrite this):\n" + draft.strip())
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


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


def tidy(text):
    """The model's answer as a beat: no "Here is the revised beat:" line, no code fences, no closing note."""
    t = str(text or "").strip()
    t = re.sub(r"^```\w*\s*\n|\n```\s*$", "", t).strip()
    t = PREFACE.sub("", t, count=1).strip()
    t = re.sub(r"\n+\s*(?:---+\s*\n+)?(?:\*\*)?(?:Notes?|Changes(?: made)?|Edits?)(?:\*\*)?:[\s\S]*$", "", t).strip()
    return t


def judge(narrator, draft, polished, names, rules):
    """(keep it?, why not). It is kept only when it is not a refusal, keeps every "— Name —" label in order and
    every fighter the draft names, stays within min_ratio..max_ratio of the draft's length, and the program's own
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
    missing = [n for n in names if re.search(r"\b" + re.escape(n) + r"\b", draft)
               and not re.search(r"\b" + re.escape(n) + r"\b", polished)]
    if missing:
        return False, f"it left out {', '.join(missing)}"
    wd, wp = len(draft.split()), len(polished.split())
    ratio = wp / max(1, wd)
    if not float(c.get("min_ratio", 0.7)) <= ratio <= float(c.get("max_ratio", 1.5)):
        return False, f"it changed the length too much ({wd} → {wp} words)"
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


def request_text(draft, facts, prior=""):
    """The whole request as one block of text, to paste into a chat window by hand (/polish copy)."""
    m = messages(draft, facts, prior)
    return (m[0]["content"] + "\n\n" + m[1]["content"] + "\n")
