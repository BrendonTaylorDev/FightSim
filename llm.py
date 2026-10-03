"""Minimal client for a local Ollama server. No API keys, no tokens billed."""
import json
import time
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    pass


last_done_reason = None   # why the last answer ended, as Ollama reports it ("stop" or "length"); None when unknown
last_prompt_tokens = None  # how many tokens Ollama counted in the last prompt (for the narrator's memory budget)
# Models that "think" before they answer (Gemma 4, Qwen 3 and others) spend the answer's word budget on thinking
# and can come back with half an answer or none. The first time a model is seen thinking, it is asked not to
# ("think": false) from then on. Models that don't think are never sent that field.
no_think = set()
_last_thinking = False
# running totals since the program started, for the "this beat took..." line: play.py reads the difference
stats = {"calls": 0, "seconds": 0.0, "out_tokens": 0, "out_seconds": 0.0, "in_tokens": 0, "in_seconds": 0.0,
         "load_seconds": 0.0}


def chat(model, messages, host="http://localhost:11434", temperature=0.8,
         fmt=None, num_ctx=8192, num_predict=None, timeout=600, extra_options=None):
    options = {"temperature": temperature, "num_ctx": num_ctx}
    if num_predict:
        options["num_predict"] = num_predict
    if extra_options:  # sampler settings such as repeat_penalty, top_p, min_p
        options.update({k: v for k, v in extra_options.items() if v is not None})
    body = {"model": model, "stream": False, "messages": messages, "options": options}
    if fmt is not None:
        body["format"] = fmt  # JSON schema -> Ollama constrains output to match it
    if model in no_think:
        body["think"] = False
    data = json.dumps(body).encode()
    for attempt in range(3):
        try:
            t0 = time.time()
            out = _post(host, data, timeout)
            stats["calls"] += 1
            stats["seconds"] += time.time() - t0
            if _last_thinking and model not in no_think:
                # this model thinks first: ask again without it, and never let it think again this session
                no_think.add(model)
                print(f"  [{model} thinks before it answers: turning that off so the whole word budget goes to the story]",
                      flush=True)
                body["think"] = False
                data = json.dumps(body).encode()
                out = _post(host, data, timeout)
            return out
        except LLMError as e:
            # Ollama's engine sometimes crashes (CUDA errors, "process has terminated") and restarts itself:
            # wait a moment and try again before giving up.
            transient = any(w in str(e).lower() for w in ("terminated", "cuda", "500", "connection reset",
                                                            "remote end closed", "timed out"))
            if attempt == 2 or not transient:
                raise
            print(f"  [model hiccup ({str(e)[:80]}...), retrying in {3 * (attempt + 1)}s]", flush=True)
            time.sleep(3 * (attempt + 1))


def _post(host, data, timeout):
    req = urllib.request.Request(f"{host}/api/chat", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out = json.loads(resp.read())
            global last_prompt_tokens, _last_thinking, last_done_reason
            last_prompt_tokens = out.get("prompt_eval_count")
            last_done_reason = out.get("done_reason")     # "stop": the model ended there itself; "length": it was cut off
            _last_thinking = bool((out.get("message") or {}).get("thinking"))
            # Ollama reports its own timings in nanoseconds
            stats["out_tokens"] += int(out.get("eval_count") or 0)
            stats["out_seconds"] += float(out.get("eval_duration") or 0) / 1e9
            stats["in_tokens"] += int(out.get("prompt_eval_count") or 0)
            stats["in_seconds"] += float(out.get("prompt_eval_duration") or 0) / 1e9
            stats["load_seconds"] += float(out.get("load_duration") or 0) / 1e9
            return out["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        # Ollama explains what went wrong in the response body; show it.
        try:
            detail = json.loads(e.read().decode("utf-8", "replace")).get("error", "")
        except Exception:
            detail = ""
        raise LLMError(f"Ollama returned HTTP {e.code}: {detail or e.reason}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Can't reach Ollama at {host} ({e.reason}). Is Ollama running?") from e
    except Exception as e:
        raise LLMError(f"{e}") from e
