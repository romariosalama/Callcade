"""
Buyer voices.

CALLCADE_VOICE in .env picks where voices come from:
  groq    = Orpheus on Groq. Free with your Groq key, very expressive (can sound annoyed,
            warm, deadpan...). Only 6 voices, so every buyer also gets their own speaking style.
  polly   = Amazon Polly (needs AWS). Lots of voices.
  browser = the browser's built-in voices (robotic, but always works).

If the server voice fails for any reason (limit hit, not set up), this returns None and
the browser quietly falls back to its own voice, so a call never breaks.
"""

import logging
import os
import re
from collections import OrderedDict

import httpx

log = logging.getLogger("callcade")

PROVIDER = os.getenv("CALLCADE_VOICE", "browser").lower()
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ORPHEUS_MODEL = os.getenv("ORPHEUS_MODEL", "canopylabs/orpheus-v1-english")
ENABLED = PROVIDER in ("groq", "polly")

_client = None
_cache = OrderedDict()  # replaying a line shouldn't cost another request
CACHE_SIZE = 300
STATS = {"groq": 0, "polly": 0, "failed": 0, "last_error": ""}

# Orpheus has 3 women's and 3 men's voices
ORPHEUS_VOICES = {"female": ["hannah", "diana", "autumn"], "male": ["austin", "daniel", "troy"]}


def orpheus_voice(voice):
    # the Orpheus voice + speaking style for a character (set in the data files)
    if voice.get("orpheus"):
        return voice["orpheus"], voice.get("style", "")
    options = ORPHEUS_VOICES["female" if voice.get("gender") == "female" else "male"]
    return options[sum(map(ord, voice.get("polly", "x"))) % len(options)], voice.get("style", "")


def mood_style(base, mood):
    # real people sound different when they're annoyed vs. warming up to you
    if mood is None:
        return base
    if mood < 25:
        return "[irritated]"
    if mood >= 70:
        return "[warm]"
    return base


def clean(text):
    text = re.sub(r"\*[^*]*\*", "", text)       # no *sighs* stage directions
    text = re.sub(r"\[[^\]]*\]", "", text)      # no [brackets] from the AI
    return re.sub(r"\s+", " ", text).strip()


def chunks(text, limit=180):
    # Orpheus takes up to 200 characters, so split longer lines at sentence breaks
    parts, cur = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > limit:  # one giant sentence: split at a comma or space
            cut = max(sentence.rfind(",", 0, limit), sentence.rfind(" ", 0, limit)) or limit
            parts.append(sentence[:cut + 1].strip())
            sentence = sentence[cut + 1:].strip()
        if cur and len(cur) + len(sentence) + 1 > limit:
            parts.append(cur)
            cur = sentence
        else:
            cur = (cur + " " + sentence).strip()
    if cur:
        parts.append(cur)
    return parts


def wav_parts(blob):
    # (format chunk, audio bytes) from a WAV file. done by hand because streamed WAVs
    # say their length is 'unknown' (0xFFFFFFFF), which Python's wave module chokes on
    fmt, data, i = None, b"", 12
    while i + 8 <= len(blob):
        cid, size = blob[i:i + 4], int.from_bytes(blob[i + 4:i + 8], "little")
        if cid == b"fmt ":
            fmt = blob[i + 8:i + 8 + size]
        if cid == b"data":
            data = blob[i + 8:] if size in (0, 0xFFFFFFFF) or i + 8 + size > len(blob) else blob[i + 8:i + 8 + size]
            break
        i += 8 + size + (size % 2)
    return fmt, data


def join_wavs(blobs):
    # glue several WAV clips into one clean WAV file
    fmt, audio = None, b""
    for b in blobs:
        f, d = wav_parts(b)
        fmt = fmt or f
        audio += d
    if fmt is None:
        return blobs[0]
    body = b"WAVE" + b"fmt " + len(fmt).to_bytes(4, "little") + fmt + b"data" + len(audio).to_bytes(4, "little") + audio
    return b"RIFF" + len(body).to_bytes(4, "little") + body


def groq_speak(text, voice, mood=None):
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing")
    name, style = orpheus_voice(voice)
    style = mood_style(style, mood)
    blobs = []
    for part in chunks(text):
        res = httpx.post("https://api.groq.com/openai/v1/audio/speech", timeout=30,
                         headers={"Authorization": "Bearer " + key},
                         json={"model": ORPHEUS_MODEL, "voice": name, "response_format": "wav",
                               "input": (style + " " + part).strip()})
        if res.status_code != 200:
            raise RuntimeError(f"Groq voice {res.status_code}: {res.text[:200]}")
        blobs.append(res.content)
    return join_wavs(blobs), "audio/wav"  # also fixes the 'unknown length' header on single clips


def polly():
    global _client
    if _client is None:
        import boto3
        _client = boto3.client("polly", region_name=AWS_REGION)
    return _client


def polly_speak(text, voice):
    for engine in ("generative", "neural", "standard"):  # generative sounds the most human
        try:
            res = polly().synthesize_speech(Text=text, VoiceId=voice["polly"], OutputFormat="mp3", Engine=engine)
            return res["AudioStream"].read(), "audio/mpeg"
        except Exception as e:
            msg = str(e)
            if "EngineNotSupported" in msg or "ValidationException" in msg or "not supported" in msg.lower():
                continue
            raise
    return None


def speak(text, voice, mood=None):
    # returns (audio bytes, mime type), or None so the browser uses its own voice
    if not ENABLED:
        return None
    text = clean(text)
    if not text:
        return None
    key = (PROVIDER, voice.get("polly"), voice.get("orpheus"), mood_style(voice.get("style", ""), mood), text)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

    audio = None
    try:
        if PROVIDER == "groq":
            audio = groq_speak(text, voice, mood)
            STATS["groq"] += 1
        else:
            audio = polly_speak(text, voice)
            STATS["polly"] += 1
    except Exception as e:
        STATS["failed"] += 1
        STATS["last_error"] = str(e)[:300]
        if "terms" in str(e).lower():
            log.warning("Groq voice needs its terms accepted once: open "
                        "https://console.groq.com/playground?model=canopylabs/orpheus-v1-english and accept them.")
        log.warning("Voice failed, browser voice will be used: %s", e)
        return None
    if audio:
        _cache[key] = audio
        if len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return audio
