// The call itself: pre-call briefing, ringing, talking, hanging up.

let call = null;
let callTimer = null;

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem("callcade.prefs")) || {};
  } catch (e) {
    return {}; // saved prefs got mangled somehow, start over
  }
}

function savePrefs(p) {
  localStorage.setItem("callcade.prefs", JSON.stringify(p));
}

function firstName(c) {
  const parts = c.buyer.name.split(" ");
  if (parts[0] === "Dr.") return "Dr. " + parts[parts.length - 1];
  return parts[0];
}

function waysToWin(c, cat) {
  return `
    <details class="ways">
      <summary class="t">How scoring works</summary>
      <div class="way"><span>${esc(cat.labels.meeting)}</span><b>+150</b><small>${esc(c.goal)}</small></div>
      <div class="way"><span>${esc(cat.labels.close)}</span><b>+300</b><small>${esc(c.close_condition)} (${money(c.deal_value.close)})</small></div>
      <div class="way"><span>${esc(cat.labels.upsell)}</span><b>+150</b><small>${esc(c.upsell)} (+${money(c.deal_value.upsell)})</small></div>
      <div class="note">${c.max_discount_pct ? `Discount more than ${c.max_discount_pct}% and it costs you.` : "No discounts allowed in this industry."}</div>
    </details>`;
}

// ---------------- pre-call screen ----------------

function renderPreCall(id) {
  const c = findCharacter(id);
  if (!c) return go("#/play");
  if (!c.unlocked) return go("#/category/" + c.category);
  const cat = findCategory(c.category);
  preCallScreen(c, {
    start: () => api("/api/calls", { character_id: c.id }),
    back: ["#/category/" + cat.id, cat.name],
  });
}

// used by career calls, the daily challenge, and friend challenges.
// options: { start: function that starts the call on the server, back: [link, label], banner: extra html }
function preCallScreen(c, options) {
  cleanupCall();
  const cat = categoryFor(c);
  const door = cat.call_type === "door";
  const prefs = loadPrefs();
  let mode = prefs.mode || (canListen ? "voice" : "text");
  if (!canListen) mode = "text";

  app.innerHTML = `
    <a class="back" href="${options.back[0]}">← ${esc(options.back[1])}</a>
    <section class="precall">
      ${options.banner || ""}
      ${buyerAvatar(c.nickname, c.color)}
      <h1>${esc(c.nickname)}</h1>
      <div>${stars(c.stars)} <span class="muted">· ${c.custom ? "practice only, no points" : "×" + c.multiplier + " points"}</span></div>
      <div class="role">${esc(c.buyer.name)} · ${esc(c.buyer.title)}${c.buyer.company ? ", " + esc(c.buyer.company) : ""}</div>
      ${c.bio ? `<p class="precall-bio">${esc(c.bio)}</p>` : ""}

      <div class="card">
        <dl class="brief">
          ${c.custom ? "" : `<dt>You are</dt><dd>${esc(cat.you_are)}</dd>`}
          <dt>You're selling</dt><dd>${esc(c.you_are_selling)}</dd>
          <dt>How it starts</dt><dd>${door ? `You knock and they open the door. They have no idea who you are. Say who you are and why you're there.`
            : c.inbound ? `Your phone rings. It's a customer calling the dealership, and they'll talk first. Answer like a pro.`
            : `Like a real call: they pick up with "Hello?" and have no idea who you are. Say who you are and why you're calling.`}</dd>
          ${c.context ? `<dt>The situation</dt><dd>${esc(c.context)}</dd>` : ""}
          <dt>Heads up</dt><dd>${esc(c.traits)}. ${esc(c.tagline)}. They won't agree to anything until you've turned around
            <b>${c.objections_to_win} objection${c.objections_to_win > 1 ? "s" : ""}</b> and found a real problem they have.</dd>
        </dl>
        <div style="margin-top:16px">${waysToWin(c, cat)}</div>
      </div>

      <div class="options">
        <div class="mode-switch">
          <button data-mode="voice" class="${mode === "voice" ? "on" : ""}" ${canListen ? "" : "disabled title='Your browser does not support voice. Try Chrome.'"}>Talk out loud</button>
          <button data-mode="text" class="${mode === "text" ? "on" : ""}">Type</button>
        </div>
      </div>
      <details class="call-settings">
        <summary>Call settings</summary>
        <div class="options">
          <label class="check"><input type="checkbox" id="opt-meter" ${prefs.meter !== false ? "checked" : ""}> Show interest meter</label>
          <label class="check"><input type="checkbox" id="opt-phone" ${prefs.phone !== false ? "checked" : ""}> Phone line sound</label>
          <label class="check"><input type="checkbox" id="opt-voice" ${prefs.voice !== false ? "checked" : ""}> Buyer talks out loud</label>
        </div>
      </details>

      ${state.config.ai ? "" : `<div class="banner info" style="text-align:left;margin-bottom:18px"><b>AI isn't connected yet.</b>
        Right now ${esc(firstName(c))} is a simple practice bot that only reacts to keywords. Connect AI to get a real buyer
        who actually understands you (see <b>docs/AI_SETUP.md</b> in the project).</div>`}
      <button class="btn go big" id="dial">${door ? "Knock on the door" : c.inbound ? "Answer the call" : "Call " + esc(firstName(c))}</button>
      <div class="ringing" id="ringing" hidden></div>
      <p class="tip" id="tip"></p>
    </section>`;

  const tips = [];
  if (!state.config.server_voice) {
    tips.push("Tip: on a Mac, download a better free voice in System Settings → Accessibility → Spoken Content → System Voice → Manage Voices (grab a Premium or Enhanced one). The buyer will sound way more real.");
  }
  if (canListen) tips.push("Wear headphones in voice mode so the buyer's voice doesn't get picked up by your mic.");
  $("tip").textContent = tips.join(" ");

  app.querySelectorAll(".mode-switch button").forEach((b) => {
    b.onclick = () => {
      if (b.disabled) return;
      mode = b.dataset.mode;
      app.querySelectorAll(".mode-switch button").forEach((x) => x.classList.toggle("on", x === b));
    };
  });

  $("dial").onclick = async () => {
    const opts = {
      mode,
      meter: $("opt-meter").checked,
      phone: $("opt-phone").checked,
      voice: $("opt-voice").checked,
    };
    savePrefs({ ...loadPrefs(), ...opts });
    $("dial").disabled = true;
    $("ringing").hidden = false;
    $("ringing").textContent = door ? "Knocking…" : c.inbound ? "Incoming call…" : "Ringing…";
    unlockAudio(); // phones only allow sound that starts from a tap, so unlock it here

    try {
      const [data] = await Promise.all([
        options.start(),
        opts.voice ? (door ? knock() : ringTone(3)) : sleep(700),
      ]);
      startCallScreen(c, cat, data, opts);
    } catch (err) {
      $("dial").disabled = false;
      $("ringing").hidden = true;
      toast(err.message);
    }
  };
}

// ---------------- the call ----------------

function startCallScreen(c, cat, data, opts) {
  call = {
    recordings: {},  // rep turn number -> audio url, for the replay
    id: data.call_id,
    character: c,
    category: cat,
    status: "live",
    opts,
    turns: 0,
    busy: false,
  };
  const door = cat.call_type === "door";

  app.innerHTML = `
    <div class="call-layout">
      <aside class="side">
        <div class="buyer-card">
          ${buyerAvatar(c.nickname, c.color)}
          <div><div class="name">${esc(c.nickname)}</div><div class="role">${esc(c.buyer.name)} · ${esc(c.buyer.title)}</div></div>
        </div>
        <div class="status" id="status"><span class="dot"></span><span id="status-text">${door ? "At the door" : "On the call"}</span><span class="timer" id="timer">0:00</span></div>
        <div class="hud">
          <div><div class="l">Points</div><div class="v pixel" id="hud-points">0</div></div>
          <div><div class="l">Combo</div><div class="v pixel" id="hud-combo">–</div></div>
          <div><div class="l">Turns left</div><div class="v pixel" id="hud-turns">${c.max_turns}</div></div>
        </div>
        <div class="meter-wrap ${opts.meter ? "" : "blind"}">
          <div class="meter-head"><span>Buyer interest</span><b id="mood">${data.mood}</b></div>
          <div class="meter"><div class="fill" id="mood-fill"></div><div class="line" style="left:${c.hang_up_below}%"></div></div>
          <div class="meter-scale"><span>${door ? "Closing the door" : "Hanging up"}</span><span>Ready to buy</span></div>
        </div>
        <div class="checklist">
          <div id="chk-obj"><span>Objections turned around</span><b>0 / ${c.objections_to_win}</b></div>
          <div id="chk-pain"><span>Real problems found</span><b>0</b></div>
        </div>
        ${waysToWin(c, cat)}
      </aside>

      <section class="convo">
        <div class="transcript" id="transcript"></div>
        <div class="mic-bar" id="mic-bar" ${opts.mode === "voice" ? "" : "hidden"}>
          <span class="mic-dot"></span><span id="mic-text">Connecting…</span>
          <span class="hint"><kbd>Space</kbd> to interrupt</span>
        </div>
        <form class="composer" id="composer">
          ${canListen ? `<button type="button" class="icon-btn" id="mic-toggle" title="Talk out loud">Mic</button>` : ""}
          <input id="say" autocomplete="off" placeholder="${opts.mode === "voice" ? "Talk, or type here…" : "Say something…"}">
          <button class="btn primary" id="send" type="submit">Send</button>
          <button class="btn danger" id="hangup" type="button">${door ? "Walk away" : "Hang up"}</button>
        </form>
      </section>
    </div>`;

  setMood(data.mood);
  const started = Date.now();
  callTimer = setInterval(() => {
    const s = Math.floor((Date.now() - started) / 1000);
    $("timer").textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
  }, 1000);

  $("composer").onsubmit = (e) => {
    e.preventDefault();
    sendLine($("say").value);
  };
  $("hangup").onclick = hangUp;
  if ($("mic-toggle")) {
    $("mic-toggle").onclick = () => {
      call.opts.mode = call.opts.mode === "voice" ? "text" : "voice";
      $("mic-bar").hidden = call.opts.mode !== "voice";
      $("mic-toggle").classList.toggle("on", call.opts.mode === "voice");
      if (call.opts.mode === "voice" && !isSpeaking() && !call.busy) startListening();
      else stopListening();
    };
    $("mic-toggle").classList.toggle("on", opts.mode === "voice");
  }
  document.addEventListener("keydown", onCallKey);

  buyerTalks(data.buyer_says);
}

function onCallKey(e) {
  if (!call || e.code !== "Space") return;
  if (document.activeElement && document.activeElement.id === "say") return; // they're typing
  e.preventDefault();
  if (isSpeaking()) stopSpeaking(); // interrupt the buyer
}

function setMood(m) {
  if (call) call.mood = m; // the voice uses this to sound annoyed or warm
  $("mood").textContent = m;
  const fill = $("mood-fill");
  fill.style.width = m + "%";
  fill.style.background = m < 30 ? "var(--bad)" : m < 60 ? "var(--warn)" : "var(--good)";
}

function addBubble(who, text) {
  const el = document.createElement("div");
  el.className = "bubble " + who;
  const label = who === "rep" ? "You" : call.character.nickname;
  el.innerHTML = `<div class="who">${esc(label)}</div>${esc(text)}`;
  $("transcript").appendChild(el);
  $("transcript").scrollTop = $("transcript").scrollHeight;
  return el;
}

function addSys(text, kind = "") {
  const el = document.createElement("div");
  el.className = "sysline " + kind;
  el.textContent = text;
  $("transcript").appendChild(el);
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

function micStatus(text, listening) {
  if (!$("mic-bar")) return;
  $("mic-text").textContent = text;
  $("mic-bar").classList.toggle("listening", !!listening);
}

async function buyerTalks(text) {
  addBubble("buyer", text);
  if (!call.opts.voice) {
    afterBuyer();
    return;
  }
  const face = document.querySelector(".buyer-card .avatar");
  micStatus(call.character.nickname + " is talking…", false);
  await speak(text, {
    ...voiceOf(call.character),
    mood: call.mood,
    phoneLine: call.opts.phone && call.category.call_type !== "door",
    onStart: () => face.classList.add("talking"),
  });
  face.classList.remove("talking");
  afterBuyer();
}

function afterBuyer() {
  if (!call) return;
  if (call.status !== "live") {
    finishCall();
    return;
  }
  if (call.opts.mode === "voice") startListening();
  else $("say").focus();
  if (call.turns === 0) waitForHello();
}

// real people don't wait forever. if you say nothing after they pick up, they say hello again, then hang up
const NUDGES = ["Hello?", "...Hello? Anyone there?"];

function waitForHello(step = 0) {
  clearTimeout(call.silence);
  call.silence = setTimeout(async () => {
    if (!call || call.turns > 0 || call.busy || call.status !== "live") return;
    // they're typing or talking right now, so give them a second
    if (($("say") && $("say").value.trim()) || document.querySelector(".bubble.interim")) return waitForHello(step);
    if (step >= NUDGES.length) {
      addSys(call.category.call_type === "door" ? "They closed the door." : "They hung up.", "bad");
      return hangUp();
    }
    const listening = call.opts.mode === "voice";
    if (listening) stopListening();
    const text = NUDGES[step];
    addBubble("buyer", text);
    if (call.opts.voice) {
      await speak(text, { ...voiceOf(call.character), phoneLine: call.opts.phone && call.category.call_type !== "door" });
    }
    if (!call || call.turns > 0) return;
    if (listening) startListening();
    waitForHello(step + 1);
  }, step === 0 ? 7000 : 6000);
}

function startListening() {
  if (!call || call.status !== "live" || call.busy) return;
  micStatus("Listening… just talk", true);
  startRecording();
  let interim = null;
  listen({
    onUpdate: (words) => {
      if (!interim) {
        interim = addBubble("rep", words);
        interim.classList.add("interim");
      } else {
        interim.lastChild.textContent = words;
      }
      $("transcript").scrollTop = $("transcript").scrollHeight;
    },
    onDone: async (words) => {
      if (interim) interim.remove();
      const clip = await stopRecording();
      if (!call) return;
      if (words) {
        if (clip) call.recordings[call.turns] = URL.createObjectURL(clip);
        sendLine(words);
      } else startListening();
    },
  });
}

async function sendLine(text) {
  text = text.trim();
  if (!call || call.status !== "live" || call.busy || !text) return;
  call.busy = true;
  stopListening();
  stopSpeaking();
  $("say").value = "";
  addBubble("rep", text);
  micStatus("…", false);
  $("send").disabled = true;
  const typing = addBubble("buyer", "…");
  typing.classList.add("typing");

  try {
    const r = await api(`/api/calls/${call.id}/say`, { text });
    typing.remove();
    call.turns += 1;
    call.status = r.status;
    setMood(r.mood);
    updateHud(r);
    if (r.objection && r.status === "live") {
      addSys("Objection. Handle it before you ask for anything.", "objection");
      sfx.bad();
    }
    call.busy = false;
    $("send").disabled = false;
    await buyerTalks(r.buyer_says);
  } catch (err) {
    typing.remove();
    addSys(err.message, "lose");
    call.busy = false;
    $("send").disabled = false;
    if (call.opts.mode === "voice") startListening();
  }
}

function updateHud(r) {
  $("hud-points").textContent = fmt(r.call_points);
  $("hud-turns").textContent = Math.max(0, call.character.max_turns - call.turns);
  const combo = $("hud-combo");
  combo.textContent = r.combo >= 2 ? "×" + r.combo : "–";
  combo.classList.remove("hot");
  if (r.points_earned > 0) {
    void combo.offsetWidth;
    if (r.combo >= 2) combo.classList.add("hot");
    if (r.combo >= 2) sfx.combo(r.combo);
    else sfx.good();
    floatPoints("+" + r.points_earned + (r.combo >= 2 ? "  ×" + r.combo + " COMBO" : ""), r.combo >= 2);
  }
  $("chk-obj").querySelector("b").textContent = r.handled + " / " + r.need;
  $("chk-obj").classList.toggle("met", r.handled >= r.need);
  $("chk-pain").querySelector("b").textContent = r.pains;
  $("chk-pain").classList.toggle("met", r.pains >= 1);
}

function floatPoints(text, combo) {
  const box = $("hud-points").getBoundingClientRect();
  const el = document.createElement("div");
  el.className = "float-points pixel" + (combo ? " combo" : "");
  el.textContent = text;
  el.style.left = box.left + "px";
  el.style.top = box.top - 10 + "px";
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 1400);
}

function finishCall() {
  stopListening();
  clearInterval(callTimer);
  const nick = call.character.nickname;
  const door = call.category.call_type === "door";
  if (call.opts.voice && !door) hangupTone();
  const msgs = {
    closed: ["DEAL CLOSED! " + nick + " is buying.", "win"],
    meeting_booked: [call.category.labels.meeting + ": done!", "win"],
    hung_up: [door ? nick + " closed the door." : nick + " hung up.", "lose"],
    ended: ["The call ended.", ""],
  };
  const [msg, kind] = msgs[call.status] || ["The call ended.", ""];
  addSys(msg, kind);
  if (kind === "win") {
    sfx.win();
    confetti();
  } else if (kind === "lose") sfx.lose();
  $("status").classList.add("off");
  $("status-text").textContent = "Call ended";
  micStatus("Call ended", false);
  $("say").disabled = true;
  $("send").disabled = true;
  const btn = $("hangup");
  btn.textContent = "See results →";
  btn.className = "btn primary";
}

async function hangUp() {
  if (!call) return;
  const id = call.id;
  const c = call.character;
  const recordings = call.recordings;
  if (call.status === "live" && call.opts.voice && call.category.call_type !== "door") hangupTone();
  cleanupCall();
  try {
    const card = await api(`/api/calls/${id}/end`, {});
    state.lastResult = { card, characterId: c.id, recordings };
    await refreshCategories();
    go("#/results");
  } catch (err) {
    toast(err.message);
  }
}

// called by the router whenever we leave the call page
function cleanupCall() {
  if (call) clearTimeout(call.silence);
  stopListening();
  releaseMic();
  stopSpeaking();
  clearInterval(callTimer);
  document.removeEventListener("keydown", onCallKey);
  call = null;
}
