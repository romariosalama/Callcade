# Turning on the AI buyers

Without AI, Callcade uses a simple practice bot that only reacts to keywords. To get buyers that actually understand you, pick one of these. The first two are free.

| Option | Cost | Setup | Quality |
| --- | --- | --- | --- |
| **Ollama** (runs on your computer) | Free | ~10 min, one big download | Good |
| **Groq** (free online tier) | Free, with daily limits | ~5 min, free account | Good |
| **Claude API** | Pay per use, a few cents a call | ~5 min, needs a card | Best |
| **Amazon Bedrock** | Pay per use through AWS | ~30 min | Best |

## Option 1: Ollama (free, runs on your Mac)

The AI model runs on your own computer, so there's no account, no key, and no cost. It works best on an Apple Silicon Mac (M1 or newer) with 16GB of RAM. With 8GB it works, but it's slow.

1. Download Ollama from [ollama.com/download](https://ollama.com/download), install it, and open it. You'll see a llama icon in your menu bar.
2. In Terminal, download a model (about 5GB, one time only):

   ```bash
   ollama pull llama3.1:8b
   ```

3. In `.env`, set:

   ```
   CALLCADE_MODE=ollama
   ```

4. Restart Callcade. The badge in the top right should say **AI buyers on**.

Keep the Ollama app open while you play. The first reply of a session takes a few extra seconds while the model loads.

**Other models to try** (set `OLLAMA_MODEL=` in `.env` after pulling them): `qwen2.5:7b` is good at following rules and returning clean JSON, and `llama3.2:3b` is much faster but less smart, for older Macs.

## Option 2: Groq (free online tier)

Groq runs open models in the cloud for free, with daily limits. You don't need a credit card.

1. Make an account at [console.groq.com](https://console.groq.com).
2. Go to **API Keys** → **Create API Key**, and copy it.
3. In `.env`, set:

   ```
   CALLCADE_MODE=groq
   GROQ_API_KEY=gsk_...your key...
   ```

4. Restart Callcade.

The free tier has per-minute and per-day limits, and each model has its own. When one model hits its limit, Callcade moves on to the next one in `GROQ_MODELS` (see `backend/llm.py` for the default list) and comes back to it once it frees up. The admin page shows how many replies each model has handled. Check which free models Groq currently offers under **Models** in their console if one stops working.

**Voices:** with `CALLCADE_VOICE=groq`, the buyers also talk with Groq's Orpheus voices using the same key. The first time, open the Orpheus model in the Groq playground and accept its terms, or the app will quietly fall back to the browser voice.

## Option 3: Claude API (paid, best quality)

1. Make an account at [console.anthropic.com](https://console.anthropic.com), add a little credit under **Billing**, and create a key under **API Keys**.
2. In `.env`: `CALLCADE_MODE=claude` and `ANTHROPIC_API_KEY=sk-ant-...`
3. Restart Callcade.

## Option 4: Amazon Bedrock

See [AWS_SETUP.md](AWS_SETUP.md), then set `CALLCADE_MODE=bedrock`.

## Keep keys secret

API keys only go in `.env`, which is in `.gitignore` so it never ends up on GitHub. Never paste a key into the code or a screenshot. If one leaks, delete it in that site's console and make a new one.

## How to tell it's working

Say something random like "Sunderland". A real AI buyer will be confused in their own words instead of giving a canned line, and the scorecard coaching will quote what you actually said.
