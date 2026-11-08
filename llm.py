"""A small, rate-limit-aware client for any OpenAI-compatible chat API. Standard library only.

Reads LLM_BASE_URL, LLM_API_KEY and LLM_MODEL from the environment (the scorer sets these to its
own key). Every real call appends its token counts to usage.jsonl.

    from llm import chat
    reply = chat([{"role": "user", "content": "Hello"}], json_mode=True)

Why this exists: free tiers (Gemini, Groq, OpenRouter...) cap requests per minute. The old client
fired many small calls and gave up on the second 429. This one:
  * paces calls client-side (LLM_RPM, default 12 requests/minute, shared across threads),
  * on 429/5xx waits for the server's Retry-After / Gemini "retryDelay" hint, then retries,
  * switches to LLM_FALLBACK_MODEL if the primary model stays rate-limited,
  * caches replies on disk (LLM_CACHE_DIR, default .llm_cache; LLM_CACHE=0 disables) so
    re-running on the same data during development costs no quota at all.
"""
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

_lock = threading.Lock()
_next_slot = [0.0]


def _pace():
    """Block until this thread may send its request (simple shared spacing, not a burst bucket)."""
    try:
        rpm = float(os.environ.get("LLM_RPM", "12"))
    except ValueError:
        rpm = 12.0
    gap = 60.0 / rpm if rpm > 0 else 0.0
    with _lock:
        now = time.time()
        wait = _next_slot[0] - now
        _next_slot[0] = max(now, _next_slot[0]) + gap
    if wait > 0:
        time.sleep(wait)


def _retry_after(err, text):
    """Seconds the server asks us to wait, from the header or Gemini's error body."""
    try:
        v = float(err.headers.get("Retry-After") or 0)
        if v > 0:
            return v
    except (TypeError, ValueError, AttributeError):
        pass
    mo = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', text or "")
    if mo:
        return float(mo.group(1))
    mo = re.search(r"(?:try again|retry) in (\d+(?:\.\d+)?)\s*s", text or "", re.I)
    return float(mo.group(1)) if mo else 0.0


def _cache_path(body):
    if os.environ.get("LLM_CACHE", "1") == "0":
        return None
    key = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return Path(os.environ.get("LLM_CACHE_DIR", ".llm_cache")) / (key[:32] + ".json")


def _log_usage(model, usage, seconds):
    try:
        with open(os.environ.get("LLM_USAGE_FILE", "usage.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"model": model, "prompt_tokens": usage.get("prompt_tokens"),
                                "completion_tokens": usage.get("completion_tokens"),
                                "seconds": round(seconds, 2)}) + "\n")
    except OSError:
        pass


def chat(messages, model=None, temperature=0, max_tokens=None, json_mode=False, timeout=180,
         max_wait=300, deadline=None):
    """Send one chat request and return the reply text.

    Retries rate limits and server errors until `max_wait` seconds of backoff have been spent (or
    the absolute `deadline` timestamp passes), then raises the last error.
    """
    base = os.environ["LLM_BASE_URL"].rstrip("/")
    body = {"model": model or os.environ["LLM_MODEL"], "messages": messages, "temperature": temperature}
    if max_tokens:
        body["max_tokens"] = max_tokens
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    effort = os.environ.get("LLM_REASONING_EFFORT")  # e.g. "low"/"none" to stop thinking models from thinking long
    if effort:
        body["reasoning_effort"] = effort

    cpath = _cache_path(body)
    if cpath and cpath.exists():
        try:
            return json.loads(cpath.read_text(encoding="utf-8"))["content"]
        except (OSError, ValueError, KeyError):
            pass
    cache_key_body = json.loads(json.dumps(body))  # the request as first asked, before any fallback

    waited, attempt, rate_limited, last = 0.0, 0, 0, None
    fallback = os.environ.get("LLM_FALLBACK_MODEL")
    while True:
        if deadline and time.time() > deadline:
            raise last or TimeoutError("LLM deadline passed")
        _pace()
        req = urllib.request.Request(
            base + "/chat/completions", data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"], "Content-Type": "application/json"})
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            _log_usage(body["model"], data.get("usage") or {}, time.time() - started)
            content = data["choices"][0]["message"]["content"] or ""
            if cpath:
                try:
                    cpath.parent.mkdir(parents=True, exist_ok=True)
                    cpath.write_text(json.dumps({"request": cache_key_body["model"], "content": content},
                                                ensure_ascii=False), encoding="utf-8")
                except OSError:
                    pass
            return content
        except urllib.error.HTTPError as e:
            last = e
            text = ""
            try:
                text = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            if e.code == 400 and "response_format" in body:
                body.pop("response_format")  # provider has no JSON mode: the prompt still asks for JSON
                continue
            if e.code not in (408, 429, 500, 502, 503, 504):
                raise RuntimeError("HTTP %d from LLM: %s" % (e.code, text[:300])) from e
            if e.code == 429:
                rate_limited += 1
                if "PerDay" in text or "per day" in text.lower():
                    # daily quota gone: waiting will not help, only another model will
                    if fallback and body["model"] != fallback:
                        body["model"] = fallback
                        continue
                    raise RuntimeError("daily quota exhausted for %s" % body["model"]) from e
                if rate_limited >= 3 and fallback and body["model"] != fallback:
                    body["model"] = fallback
            wait = max(_retry_after(e, text), min(60.0, 2.0 * 2 ** attempt))
        except Exception as e:  # connection reset, timeout, truncated or malformed response
            if "CERTIFICATE_VERIFY_FAILED" in str(e) or "Name or service not known" in str(e):
                raise  # permanent: retrying cannot fix a broken TLS setup or a wrong host
            last = e
            wait = min(30.0, 2.0 * 2 ** attempt)
        attempt += 1
        if waited + wait > max_wait:
            raise last
        waited += wait
        time.sleep(wait)
