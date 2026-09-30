// Everything audio: ring tones, the buyer's voice, and listening to the player.
//
// Buyer voice: the server's voice (Groq Orpheus or Amazon Polly) if it's turned on,
// otherwise the best voice the browser has.
// Listening: the browser's speech recognition (works best in Chrome).

let audioCtx = null;
let currentAudio = null;
let speakingDone = null;

function ctx() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === "suspended") audioCtx.resume();
  return audioCtx;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ---------------- ring + knock sounds ----------------

function tone(freqs, start, length, volume = 0.08) {
  const ac = ctx();
  const gain = ac.createGain();
  gain.gain.setValueAtTime(0, ac.currentTime + start);
  gain.gain.linearRampToValueAtTime(volume, ac.currentTime + start + 0.03);
  gain.gain.setValueAtTime(volume, ac.currentTime + start + length - 0.05);
  gain.gain.linearRampToValueAtTime(0, ac.currentTime + start + length);
  gain.connect(ac.destination);
  for (const f of freqs) {
    const osc = ac.createOscillator();
    osc.frequency.value = f;
    osc.connect(gain);
    osc.start(ac.currentTime + start);
    osc.stop(ac.currentTime + start + length);
  }
}

async function ringTone(times = 3) {
  // US ringback tone is 440 + 480 Hz. they pick up right after the last ring
  for (let i = 0; i < times; i++) {
    tone([440, 480], 0, 1.4);
    await sleep(i === times - 1 ? 1600 : 2400);
  }
  tone([1400], 0, 0.05, 0.05); // little click when they pick up
  await sleep(250);
}

async function knock() {
  const ac = ctx();
  for (let i = 0; i < 3; i++) {
    const t = ac.currentTime + i * 0.22;
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(160, t);
    osc.frequency.exponentialRampToValueAtTime(60, t + 0.12);
    gain.gain.setValueAtTime(0.5, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.15);
    osc.connect(gain).connect(ac.destination);
    osc.start(t);
    osc.stop(t + 0.16);
  }
  await sleep(2200); // waiting for someone to come to the door
}

function hangupTone() {
  tone([480, 620], 0, 0.25, 0.05);
  tone([480, 620], 0.5, 0.25, 0.05);
}

// ---------------- buyer voice ----------------

const FEMALE = ["samantha", "ava", "allison", "susan", "victoria", "karen", "moira", "tessa", "zoe", "nicky", "serena",
  "kate", "fiona", "google us english", "female", "aria", "jenny", "michelle", "zira", "joanna", "salli", "kendra", "emma"];
const MALE = ["alex", "daniel", "fred", "tom", "evan", "nathan", "aaron", "arthur", "oliver", "lee", "male", "guy",
  "davis", "david", "mark", "matthew", "joey", "brian", "gordon", "james"];
// joke voices that come with macOS
const NOVELTY = ["albert", "bad news", "bells", "boing", "bubbles", "cellos", "good news", "jester", "organ", "superstar",
  "trinoids", "whisper", "wobble", "zarvox", "junior", "ralph", "kathy", "princess", "grandma", "grandpa", "eddy",
  "flo", "reed", "rocko", "sandy", "shelley", "hysterical", "deranged"];

function pickBrowserVoice(gender) {
  const voices = speechSynthesis.getVoices().filter((v) => v.lang.startsWith("en"));
  let best = null;
  let bestScore = -999;
  for (const v of voices) {
    const name = v.name.toLowerCase();
    let score = 0;
    if (/premium|enhanced|natural|neural/.test(name)) score += 6;
    if (v.lang === "en-US") score += 2;
    if (name.includes("google")) score += 1;
    const mine = gender === "female" ? FEMALE : MALE;
    const other = gender === "female" ? MALE : FEMALE;
    if (mine.some((n) => name.includes(n))) score += 3;
    if (other.some((n) => name.includes(n))) score -= 4;
    if (NOVELTY.some((n) => name.startsWith(n))) score -= 20;
    if (score > bestScore) {
      bestScore = score;
      best = v;
    }
  }
  return best;
}

if (window.speechSynthesis) {
  speechSynthesis.getVoices(); // chrome loads voices lazily
}

// speak() options for one of the buyers
function voiceOf(c) {
  return { characterId: c.id, gender: c.voice.gender, pitch: c.voice.pitch, rate: c.voice.rate };
}

// options: { characterId, voiceName, gender, pitch, rate, mood, phoneLine, onStart }
async function speak(text, options) {
  stopSpeaking();
  if (state.config.server_voice) {
    try {
      const res = await fetch("/api/voice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, character_id: options.characterId || "", voice: options.voiceName || "",
          gender: options.gender || "", mood: options.mood ?? null }),
      });
      if (res.status === 200) {
        const blob = await res.blob();
        return playAudio(URL.createObjectURL(blob), options);
      }
    } catch (e) {
      console.log("server voice failed, using the browser voice", e);
    }
  }
  return speakBrowser(text, options);
}

// iPhones only play sound from an audio element that already played once during a tap.
// the buyer's voice shows up a second after the tap, so we keep one player, unlock it
// with a tiny silent clip when the call starts, and reuse it for every line
const player = new Audio();
const SILENT = "data:audio/wav;base64,UklGRrQBAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YZABAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA";
let phoneFilter = null; // the phone-line filter, built once (an element can only be hooked up once)

function unlockAudio() {
  ctx();
  player.src = SILENT;
  player.play().catch(() => {});
  if (window.speechSynthesis) speechSynthesis.speak(new SpeechSynthesisUtterance(""));
}

function setPhoneLine(on) {
  const ac = ctx();
  if (!phoneFilter) {
    // make it sound like it's coming through a phone: cut the lows and highs
    const src = ac.createMediaElementSource(player);
    const low = ac.createBiquadFilter();
    low.type = "highpass";
    low.frequency.value = 350;
    const high = ac.createBiquadFilter();
    high.type = "lowpass";
    high.frequency.value = 3300;
    const squash = ac.createDynamicsCompressor();
    low.connect(high).connect(squash).connect(ac.destination);
    phoneFilter = { src, low };
  }
  phoneFilter.src.disconnect();
  phoneFilter.src.connect(on ? phoneFilter.low : ac.destination);
}

function playAudio(url, options) {
  return new Promise((resolve) => {
    // once the phone filter exists, all sound from the player goes through the audio context,
    // so it has to be told whether to filter this line or not
    if (options.phoneLine || phoneFilter) setPhoneLine(!!options.phoneLine);
    player.src = url;
    currentAudio = player;
    // real people on calls talk a bit faster than the AI voice does by default
    player.preservesPitch = true;
    player.playbackRate = Math.min(1.3, Math.max(1.0, 1.12 * (options.rate || 1)));
    speakingDone = resolve;
    player.onplay = () => options.onStart && options.onStart();
    player.onended = () => finishSpeaking();
    player.onerror = () => finishSpeaking();
    player.play().catch(() => finishSpeaking());
  });
}

function speakBrowser(text, options) {
  return new Promise((resolve) => {
    if (!window.speechSynthesis) return resolve();
    speakingDone = resolve;
    const u = new SpeechSynthesisUtterance(text);
    const v = pickBrowserVoice(options.gender || "male");
    if (v) u.voice = v;
    u.pitch = options.pitch || 1;
    u.rate = options.rate || 1;
    let started = false;
    u.onstart = () => {
      started = true;
      options.onStart && options.onStart();
    };
    u.onend = () => finishSpeaking();
    u.onerror = () => finishSpeaking();
    speechSynthesis.speak(u);

    // chrome sometimes never fires onend, so don't wait forever
    const words = text.split(" ").length;
    const done = speakingDone;
    setTimeout(() => { if (!started && speakingDone === done) finishSpeaking(); }, 2500);
    setTimeout(() => { if (speakingDone === done) finishSpeaking(); }, (words / 2.2 + 3) * 1000 / u.rate);
  });
}

function finishSpeaking() {
  currentAudio = null;
  if (speakingDone) {
    const done = speakingDone;
    speakingDone = null;
    done();
  }
}

function stopSpeaking() {
  if (currentAudio) currentAudio.pause();
  if (window.speechSynthesis) speechSynthesis.cancel();
  finishSpeaking();
}

function isSpeaking() {
  return speakingDone !== null;
}

// ---------------- listening ----------------

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const canListen = !!Recognition;

let recognizer = null;
let silenceTimer = null;

// Listens until you stop talking for a bit, then calls onDone with what you said.
// onUpdate gets called with the words as you say them.
// silenceMs: how long a pause means you're done. when Chrome already thinks your sentence
// ended, we only wait a short moment, so the buyer answers faster.
function listen({ onUpdate, onDone, silenceMs = 1300, afterSentenceMs = 650 }) {
  stopListening();
  if (!canListen) return;

  recognizer = new Recognition();
  recognizer.lang = "en-US";
  recognizer.continuous = true;
  recognizer.interimResults = true;
  let heard = "";
  let finished = false;

  const finish = () => {
    if (finished) return;
    finished = true;
    clearTimeout(silenceTimer);
    const text = heard.trim();
    stopListening();
    onDone(text);
  };

  recognizer.onresult = (e) => {
    heard = [...e.results].map((r) => r[0].transcript).join(" ");
    onUpdate && onUpdate(heard.trim());
    clearTimeout(silenceTimer);
    const sentenceDone = e.results[e.results.length - 1].isFinal;
    silenceTimer = setTimeout(finish, sentenceDone ? afterSentenceMs : silenceMs);
  };
  recognizer.onerror = (e) => {
    if (e.error === "no-speech" || e.error === "aborted") return;
    console.log("mic error", e.error);
    if (e.error === "not-allowed") toast("Microphone is blocked. Allow it in your browser's site settings.");
  };
  recognizer.onend = () => {
    // chrome stops on its own sometimes. if we didn't hear anything yet, keep going
    if (!finished && recognizer && !heard.trim()) {
      try { recognizer.start(); } catch (err) { /* already started */ }
    } else if (!finished && heard.trim()) {
      finish();
    }
  };
  try {
    recognizer.start();
  } catch (err) {
    console.log(err);
  }
}

function stopListening() {
  clearTimeout(silenceTimer);
  if (recognizer) {
    const r = recognizer;
    recognizer = null;
    r.onend = null;
    try { r.abort(); } catch (err) { /* ignore */ }
  }
}

// ---------------- recording (for call replay) ----------------
// records your side of the call so you can listen back afterwards. it never leaves your browser.

let micStream = null;
let recorder = null;
let recordChunks = [];

async function startRecording() {
  if (!window.MediaRecorder || !navigator.mediaDevices) return;
  try {
    if (!micStream) micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordChunks = [];
    recorder = new MediaRecorder(micStream);
    recorder.ondataavailable = (e) => recordChunks.push(e.data);
    recorder.start();
  } catch (e) {
    console.log("can't record", e);
    recorder = null;
  }
}

function stopRecording() {
  return new Promise((resolve) => {
    if (!recorder || recorder.state === "inactive") return resolve(null);
    const r = recorder;
    recorder = null;
    r.onstop = () => resolve(new Blob(recordChunks, { type: r.mimeType || "audio/webm" }));
    r.stop();
  });
}

function releaseMic() {
  if (recorder && recorder.state !== "inactive") recorder.stop();
  recorder = null;
  if (micStream) micStream.getTracks().forEach((t) => t.stop());
  micStream = null;
}
