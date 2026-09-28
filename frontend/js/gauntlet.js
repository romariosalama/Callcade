// Objection Gauntlet: 10 objections, 30 seconds each

let run = null;
let gTimer = null;

// a different voice reads each objection
const G_VOICES = [
  { name: "Matthew", gender: "male" },
  { name: "Joanna", gender: "female" },
  { name: "Gregory", gender: "male" },
  { name: "Ruth", gender: "female" },
  { name: "Stephen", gender: "male" },
  { name: "Danielle", gender: "female" },
];

function cleanupGauntlet() {
  clearInterval(gTimer);
  stopListening();
  stopSpeaking();
  document.removeEventListener("keydown", onGauntletKey);
  run = null;
}

async function renderGauntletMenu() {
  cleanupGauntlet();
  const prefs = loadPrefs();
  let pick = prefs.gauntletCategory || "mixed";
  let best = 0;
  if (state.user) {
    const p = await api("/api/profile/me");
    best = p.stats.gauntlet_best;
  }
  const top = await api("/api/leaderboard?mode=gauntlet");

  const options = [["mixed", "Mixed"], ["general", "Any industry"]]
    .concat(state.categories.map((c) => [c.id, c.name]));

  app.innerHTML = `
    <a class="back" href="#/play">← Arcade</a>
    <section class="hero g-menu">
      <h1>The Objection Gauntlet</h1>
      <p class="lede">Ten objections back to back, easy to brutal. The clock starts at 30 seconds and shrinks to 15.
        You've got 3 lives, and a weak answer costs one. Survive to the boss objection for double points.</p>
    </section>
    <div class="rules">
      <div><b>30→15s</b>the clock gets shorter every couple of rounds</div>
      <div><b>3 lives</b>score 4 or less (or run out of time) and you lose one</div>
      <div><b>8+</b>scores build your streak. Round 10 is the boss: double points</div>
    </div>
    <h3 class="muted" style="font-size:13px;text-transform:uppercase;letter-spacing:.07em">Pick your industry</h3>
    <div class="chips">${options.map(([id, name]) => `<button class="chip ${id === pick ? "on" : ""}" data-id="${id}">${esc(name)}</button>`).join("")}</div>
    <div class="options" style="justify-content:flex-start;display:flex;gap:20px;flex-wrap:wrap;margin-bottom:22px">
      <label class="check"><input type="checkbox" id="g-voice" ${prefs.gVoice !== false ? "checked" : ""}> Read objections out loud</label>
      ${canListen ? `<label class="check"><input type="checkbox" id="g-mic" ${prefs.gMic ? "checked" : ""}> Answer by talking</label>` : ""}
    </div>
    <div class="actions">
      ${state.user ? `<button class="btn go big" id="g-start" ${state.plan.gauntlet_left === 0 ? "disabled" : ""}>Start the gauntlet</button>`
        : `<a class="btn primary big" href="#/signup">Sign up free to play</a>`}
    </div>
    ${state.plan.plan === "free" ? `<p class="tip">${state.plan.gauntlet_left} of 3 free runs left today.${state.plan.gauntlet_left === 0 ? ` <a href="#/pricing">Go Pro</a> for unlimited runs.` : ""}</p>` : ""}
    <p class="tip">${state.user ? `Your best: <b>${fmt(best)}</b> points.` : `The gauntlet is free, you just need an account.`}
      ${top.length ? ` Top score: <b>${fmt(top[0].score)}</b> by ${esc(top[0].display_name)}.` : ""}</p>`;

  app.querySelectorAll(".chip").forEach((b) => {
    b.onclick = () => {
      pick = b.dataset.id;
      app.querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === b));
    };
  });

  if (!$("g-start")) return;
  $("g-start").onclick = async () => {
    const p = loadPrefs();
    p.gauntletCategory = pick;
    p.gVoice = $("g-voice").checked;
    p.gMic = $("g-mic") ? $("g-mic").checked : false;
    savePrefs(p);
    ctx();
    try {
      const data = await api("/api/gauntlet", { category: pick });
      state.plan = await api("/api/plan");
      run = { id: data.run_id, round: data.round, total: 0, results: [], voice: p.gVoice, mic: p.gMic };
      showRound();
    } catch (err) {
      toast(err.message);
    }
  };
}

function dots() {
  let html = "";
  for (let i = 0; i < 10; i++) {
    const r = run.results[i];
    let cls = "";
    if (r) cls = r.score >= 7 ? "g" : r.score >= 5 ? "m" : "b";
    else if (i === run.results.length) cls = "now";
    html += `<span class="${cls}"></span>`;
  }
  return `<div class="dots">${html}</div>`;
}

function timerSvg(left, total) {
  const r = 30;
  const c = 2 * Math.PI * r;
  const color = left > 10 ? "var(--good)" : left > 5 ? "var(--warn)" : "var(--bad)";
  return `<svg class="g-timer" viewBox="0 0 70 70">
    <circle cx="35" cy="35" r="${r}" fill="none" stroke="var(--panel-2)" stroke-width="6"/>
    <circle cx="35" cy="35" r="${r}" fill="none" stroke="${color}" stroke-width="6" stroke-linecap="round"
      stroke-dasharray="${(c * left) / total} ${c}" transform="rotate(-90 35 35)"/>
    <text x="35" y="43" text-anchor="middle">${left}</text></svg>`;
}

async function showRound() {
  const rd = run.round;
  const limit = rd.time_limit;
  app.innerHTML = `
    <section class="g-play">
      <div class="g-top"><span>Objection ${rd.round} of ${rd.of}</span>${dots()}<span class="g-lives">${hearts(rd.lives)}</span><span class="score pixel">${fmt(run.total)}</span></div>
      <div class="g-card ${rd.boss ? "boss" : ""}">
        ${rd.boss ? `<div class="g-boss pixel blink">BOSS OBJECTION · DOUBLE POINTS</div>` : ""}
        <div id="g-timer">${timerSvg(limit, limit)}</div>
        <div class="who">${esc(rd.who)} says:</div>
        <div class="obj">“${esc(rd.objection)}”</div>
        <div class="g-answer">
          <textarea id="g-text" placeholder="Your answer…" disabled></textarea>
          <div class="col">
            ${canListen ? `<button class="icon-btn" id="g-mic-btn" title="Answer by talking">Mic</button>` : ""}
            <button class="btn primary" id="g-send" disabled>Answer</button>
          </div>
        </div>
        <div class="g-feedback" id="g-feedback"></div>
      </div>
    </section>`;

  // read it out loud first, the clock starts after
  if (run.voice) {
    const v = G_VOICES[(rd.round - 1) % G_VOICES.length];
    await speak(rd.objection, { voiceName: v.name, gender: v.gender, phoneLine: false });
  }
  if (!run) return;

  await api(`/api/gauntlet/${run.id}/ready`, {});
  $("g-text").disabled = false;
  $("g-send").disabled = false;
  $("g-text").focus();

  let left = limit;
  const started = Date.now();
  clearInterval(gTimer);
  gTimer = setInterval(() => {
    left = Math.max(0, limit - Math.floor((Date.now() - started) / 1000));
    if ($("g-timer")) $("g-timer").innerHTML = timerSvg(left, limit);
    if (left <= 0) submitAnswer();
  }, 250);

  $("g-send").onclick = () => submitAnswer();
  $("g-text").onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitAnswer();
    }
  };
  if ($("g-mic-btn")) $("g-mic-btn").onclick = () => gListen();
  if (run.mic) gListen();
}

function gListen() {
  if (!run) return;
  $("g-mic-btn").classList.add("on");
  listen({
    silenceMs: 1800,
    onUpdate: (words) => ($("g-text").value = words),
    onDone: (words) => {
      if ($("g-mic-btn")) $("g-mic-btn").classList.remove("on");
      if (words) {
        $("g-text").value = words;
        submitAnswer();
      }
    },
  });
}

async function submitAnswer() {
  if (!run || run.submitting) return;
  run.submitting = true;
  clearInterval(gTimer);
  stopListening();
  $("g-send").disabled = true;
  $("g-text").disabled = true;

  try {
    const data = await api(`/api/gauntlet/${run.id}/answer`, { text: $("g-text").value });
    const r = data.result;
    run.results.push(r);
    run.total = data.total;
    run.submitting = false;
    showFeedback(r, data);
  } catch (err) {
    run.submitting = false;
    toast(err.message);
  }
}

function showFeedback(r, data) {
  const color = r.score >= 7 ? "good" : r.score >= 5 ? "warn" : "bad";
  if (r.score >= 7) (r.streak >= 2 ? sfx.combo(r.streak) : sfx.good());
  else if (r.score < 5) sfx.bad();
  const last = !!data.summary;
  $("g-feedback").innerHTML = `
    <div class="row">
      <div class="sc ${color}">${r.score}<small>/10</small></div>
      <div>
        <b>${esc(r.verdict)}</b> <span class="muted">+${r.points} points · ${r.seconds}s</span><br>
        ${r.speed_bonus ? `<span class="bonus">speed +${r.speed_bonus}</span>` : ""}
        ${r.streak_bonus ? `<span class="bonus">streak ×${r.streak} +${r.streak_bonus}</span>` : ""}
        ${r.boss ? `<span class="bonus">boss ×2</span>` : ""}
        ${r.lost_life ? `<span class="bonus lost">lost a life (${r.lives} left)</span>` : ""}
      </div>
    </div>
    ${r.good ? `<p class="good">${esc(r.good)}</p>` : ""}
    ${r.missed ? `<p>${esc(r.missed)}</p>` : ""}
    <div class="model"><b>How a top rep would say it</b>${esc(r.better)}</div>
    <div class="actions"><button class="btn primary" id="g-next">${last ? (data.summary.knocked_out ? "Game over. See results →" : "See results →") : "Next objection →"}</button>
      <span class="muted" style="align-self:center;font-size:13px">or press Enter</span></div>`;
  document.querySelector(".g-top .score").textContent = fmt(run.total);
  document.querySelector(".g-top .dots").outerHTML = dots();
  document.querySelector(".g-top .g-lives").innerHTML = hearts(r.lives);
  if (r.lost_life) document.querySelector(".g-card").classList.add("shake");

  const next = () => {
    document.removeEventListener("keydown", onGauntletKey);
    if (last) showSummary(data.summary);
    else {
      run.round = data.next;
      showRound();
    }
  };
  run.next = next;
  $("g-next").onclick = next;
  document.addEventListener("keydown", onGauntletKey);
}

function onGauntletKey(e) {
  if (e.key === "Enter" && run && run.next) {
    e.preventDefault();
    const n = run.next;
    run.next = null;
    n();
  }
}

function showSummary(s) {
  if (s.avg_score >= 8) {
    sfx.win();
    confetti();
  } else sfx.coin();
  const cat = findCategory(s.category);
  const name = cat ? cat.name : s.category === "mixed" ? "Mixed" : "Any industry";
  app.innerHTML = `
    <section class="res-head">
      <div class="grade pixel ${s.avg_score >= 8 ? "good" : s.avg_score >= 5 ? "warn" : "bad"}">${s.grade}</div>
      <div>
        <span class="outcome ${s.knocked_out ? "hung_up" : "closed"}">${s.knocked_out ? `Knocked out in round ${s.rounds_played}` : "Survived the gauntlet"} · ${esc(name)}</span>
        <div class="bigpoints pixel">${fmt(s.total)} PTS ${s.new_best ? '<span class="newbest pixel">NEW BEST</span>' : ""}</div>
        <h2>Average score ${s.avg_score}/10 · best streak ${s.best_streak}</h2>
        ${state.user ? "" : `<div class="banner info">Guest run, not saved. <a href="#/signup">Sign up</a> to get on the leaderboard.</div>`}
        <div class="actions">
          <button class="btn primary" id="g-again">Run it again</button>
          <a class="btn ghost" href="#/leaderboard?mode=gauntlet">Leaderboard</a>
        </div>
      </div>
    </section>
    <div class="card">
      <h3>Every answer</h3>
      ${s.answers.map((a) => `
        <details style="border-bottom:1px solid var(--line);padding:12px 0">
          <summary><b class="${a.score >= 7 ? "good" : a.score >= 5 ? "warn" : "bad"}">${a.score}/10</b> · “${esc(a.objection)}” <span class="muted">+${a.points}</span></summary>
          <p><b>You said:</b> ${esc(a.answer || "(nothing)")}</p>
          ${a.missed ? `<p class="muted">${esc(a.missed)}</p>` : ""}
          <p><b>Better:</b> ${esc(a.better)}</p>
        </details>`).join("")}
    </div>`;
  $("g-again").onclick = () => renderGauntletMenu();
  run = null;
}
