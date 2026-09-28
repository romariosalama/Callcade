"""
Talks to the AI model.

CALLCADE_MODE in .env picks where the AI comes from:
  ollama  = a free model running on your own computer (free, no account)
  groq    = Groq's free online tier (free account, has rate limits)
  claude  = Anthropic's API (paid, best buyers)
  bedrock = Claude through Amazon Bedrock (paid, uses your AWS account)
  demo    = no AI, buyers are the simple rule-based bot in demo.py
"""

import json
import logging
import os
import re
import time

import httpx

log = logging.getLogger("callcade")

MODE = os.getenv("CALLCADE_MODE", "demo").lower()

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# every Groq model has its OWN free limit, so when one is maxed out we move to the next one.
# first = best sounding. change the order in .env with GROQ_MODELS=a,b,c
GROQ_MODELS = [m.strip() for m in os.getenv(
    "GROQ_MODELS", f"{GROQ_MODEL},openai/gpt-oss-20b,llama-3.3-70b-versatile,qwen/qwen3.8-27b").split(",") if m.strip()]
GROQ_MODELS = list(dict.fromkeys(GROQ_MODELS))  # no duplicates

# simple usage counters for the admin page, so we can watch it if a post takes off
STATS = {"replies": {}, "limited": {}, "failed": 0}
COOLDOWN = {}  # model -> time it can be tried again

_client = None


def ai_on():
    return MODE in ("ollama", "groq", "claude", "bedrock")


def client():
    global _client
    if _client is None:
        if MODE == "claude":
            import anthropic
            _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        else:
            import boto3
            _client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _client


def ask_for_json(system_prompt, messages, max_tokens=800):
    # messages look like [{"role": "user", "content": "hi"}, ...]
    if MODE == "ollama":
        text = ask_ollama(system_prompt, messages, max_tokens)
    elif MODE == "groq":
        text = ask_groq(system_prompt, messages, max_tokens)
    elif MODE == "claude":
        response = client().messages.create(
            model=CLAUDE_MODEL,
            system=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.8,
        )
        text = response.content[0].text
    else:
        response = client().converse(
            modelId=BEDROCK_MODEL,
            system=[{"text": system_prompt}],
            messages=[{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.8},
        )
        text = response["output"]["message"]["content"][0]["text"]
    return parse_json(text)


def ask_ollama(system_prompt, messages, max_tokens):
    body = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "format": "json",  # makes the model answer with valid JSON
        "stream": False,
        # the buyer instructions are long, so give the model enough room to read all of it
        "options": {"temperature": 0.8, "num_predict": max_tokens, "num_ctx": 8192},
    }
    try:
        res = httpx.post(OLLAMA_URL + "/api/chat", json=body, timeout=120)
    except httpx.ConnectError:
        raise RuntimeError("Can't reach Ollama. Is the Ollama app open? (see docs/AI_SETUP.md)")
    if res.status_code == 404:
        raise RuntimeError(f"Ollama doesn't have {OLLAMA_MODEL} yet. Run: ollama pull {OLLAMA_MODEL}")
    res.raise_for_status()
    return res.json()["message"]["content"]


def ask_groq(system_prompt, messages, max_tokens):
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing from .env")

    def body_for(model, strict=True):
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            # reasoning models "think" before answering and that counts toward the limit,
            # so give them plenty of room or the JSON gets cut off halfway
            "max_completion_tokens": max(2000, max_tokens * 4),
            "temperature": 0.8,
        }
        if strict:
            body["response_format"] = {"type": "json_object"}
        if model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"  # faster, and a buyer doesn't need deep thinking
        if model.startswith("qwen/"):
            body["reasoning_format"] = "hidden"
        return body

    def send(body):
        return httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                          headers={"Authorization": "Bearer " + key}, timeout=60)

    shortest_wait = None
    for attempt in range(2):
        for model in GROQ_MODELS:
            if COOLDOWN.get(model, 0) > time.time():
                continue  # this one is maxed out right now, skip it
            res = send(body_for(model))
            if res.status_code == 400:
                # usually broken JSON: log why, then retry once without strict JSON mode
                log.warning("Groq 400 on %s: %s", model, res.text[:300])
                res = send(body_for(model, strict=False))
            if res.status_code == 429:
                wait = float(res.headers.get("retry-after", "10") or 10)
                COOLDOWN[model] = time.time() + wait
                STATS["limited"][model] = STATS["limited"].get(model, 0) + 1
                shortest_wait = wait if shortest_wait is None else min(shortest_wait, wait)
                log.info("Groq limit on %s for %.0fs, trying the next model", model, wait)
                continue
            if res.status_code in (403, 404):
                log.warning("Groq model %s isn't available on this account, skipping it", model)
                COOLDOWN[model] = time.time() + 3600
                continue
            res.raise_for_status()
            STATS["replies"][model] = STATS["replies"].get(model, 0) + 1
            STATS["last_model"] = model
            return res.json()["choices"][0]["message"]["content"]
        # every model is maxed out. if the soonest one frees up quickly, wait for it and go again
        if shortest_wait is None or shortest_wait > 20 or attempt == 1:
            break
        time.sleep(shortest_wait + 0.5)
    STATS["failed"] += 1
    raise RuntimeError("All the free AI models are busy right now. Wait a minute and try again.")


def parse_json(text):
    # models sometimes wrap the JSON in ``` or think out loud first, so grab the {...} part
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("Model didn't return JSON: " + text[:200])
