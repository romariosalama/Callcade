// Clutch Call: 6 high-pressure moments, 4 lines each, 15 seconds to pick

let cRun = null;
let cTimer = null;

function cleanupClutch() {
  clearInterval(cTimer);
  if (cRun) document.onkeydown = null;
  cRun = null;
}

async function renderClutchMenu() {
  cleanupClutch();
  const list = await api("/api/clutch");
  let best = 0;
  if (state.user) best = (await api("/api/profile/me")).stats.best.clutch;
  app.innerHTML = `
    <a class="back" href="#/play">← Arcade</a>
    <section class="hero">
      <h1>Clutch Call</h1>
      <p class="lede">A full call with 6 make-or-break moments. Every time, you get 4 lines that all sound reasonable,
        and 15 seconds to pick the one a top rep would say. Pick wrong and the deal slips. Let it drop too low and they hang up.</p>
    </section>
    <div class="rules">
      <div><b>6</b>moments per call. The options shuffle every time.</div>
      <div><b>15s</b>to pick. The best line scores 200 plus speed and streak bonuses.</div>
      <div><b>70+</b>Keep deal health above 70 to win the call and get +400.</div>
    </div>
    <div class="section-title"><h2>Pick a call</h2><span class="muted">${state.user ? `Your best: ${fmt(best)}` : "Guest scores aren't saved"}</span></div>
    <section class="clutch-list">
      ${list.map((s) => {
        const cat = findCategory(s.category);
        return `<button class="clutch-pick" data-id="${s.id}" style="--c1:${s.buyer.color[0]}">
          ${buyerAvatar(s.buyer.name, s.buyer.color)}
          <div class="grow"><div class="muted small-note">${cat ? `<span class="cat-dot" style="--c:${cat.color[0]}"></span>` + esc(cat.name) : ""}</div>
            <h3>${esc(s.title)}</h3><p>${esc(s.buyer.name)} · ${esc(s.buyer.title)}</p></div>
          <div>${stars(s.stars)}</div>
        </button>`;
      }).join("")}
    </section>`;
  app.querySelectorAll("[data-id]").forEach((b) => {
    b.onclick = async () => {
      ctx();
      sfx.coin();
      const data = await api(`/api/clutch/${b.dataset.id}/start`, {});
      cRun = { id: data.run_id, s: data.scenario, m: data.moment, log: [] };
      showBrief();
    };
  });
}

function showBrief() {
  const s = cRun.s;
  app.innerHTML = `
    <section class="precall">
      ${buyerAvatar(s.buyer.name, s.buyer.color)}
      <h1>${esc(s.title)}</h1>
      <div class="role">${esc(s.buyer.name)} · ${esc(s.buyer.title)}</div>
      <div class="card"><dl class="brief">
        <dt>You are</dt><dd>${esc(s.you)}</dd>
        <dt>Your goal</dt><dd>${esc(s.goal)}</dd>
        <dt>How it works</dt><dd>6 moments. Pick the best of 4 lines in 15 seconds. Deal health starts at 45.</dd>
      </dl></div>
      <button class="btn go big" id="c-go" style="margin-top:22px">Start the call</button>
    </section>`;
  $("c-go").onclick = () => showMoment();
}

function healthBar(h) {
  const color = h >= 70 ? "var(--good)" : h >= 40 ? "var(--warn)" : "var(--bad)";
  return `<div class="health"><span>Deal health</span><div class="meter"><div class="fill" style="width:${h}%;background:${color}"></div>
    <div class="line" style="left:70%"></div></div><b>${h}</b></div>`;
}

async function showMoment() {
  const m = cRun.m;
  const s = cRun.s;
  app.innerHTML = `
    <section class="clutch">
      <div class="m-top"><span class="pixel tiny">MOMENT ${m.moment}/${m.of}</span>
        <span class="pixel" id="c-score" style="font-size:12px;color:var(--gold)">${fmt(m.score)}</span></div>
      ${healthBar(m.health)}
      <div class="clutch-chat" id="c-chat">
        ${cRun.log.map(([who, text]) => `<div class="bubble ${who === "you" ? "rep" : "buyer"}"><div class="who">${who === "you" ? "You" : esc(s.buyer.name)}</div>${esc(text)}</div>`).join("")}
        ${m.context.map(([, text]) => `<div class="bubble buyer now"><div class="who">${esc(s.buyer.name)}</div>${esc(text)}</div>`).join("")}
      </div>
      <div class="clutch-timer"><div id="c-bar"></div></div>
      <div class="clutch-opts" id="c-opts">
        ${m.options.map((o, k) => `<button class="copt" data-k="${o.i}"><b class="pixel">${"ABCD"[k]}</b><span>${esc(o.text)}</span></button>`).join("")}
      </div>
      <div id="c-feedback"></div>
    </section>`;
  m.context.forEach(([, text]) => cRun.log.push(["buyer", text]));
  $("c-chat").scrollTop = $("c-chat").scrollHeight;

  await api(`/api/clutch-runs/${cRun.id}/ready`, {});
  const started = Date.now();
  const limit = m.time_limit * 1000;
  clearInterval(cTimer);
  cTimer = setInterval(() => {
    const left = Math.max(0, limit - (Date.now() - started));
    if ($("c-bar")) {
      $("c-bar").style.width = (100 * left) / limit + "%";
      $("c-bar").style.background = left < 5000 ? "var(--bad)" : left < 9000 ? "var(--warn)" : "var(--good)";
    }
    if (left <= 0) choose(null);
  }, 100);
  app.querySelectorAll(".copt").forEach((b) => (b.onclick = () => choose(Number(b.dataset.k), b)));
  document.onkeydown = (e) => {
    const k = "abcd".indexOf(e.key.toLowerCase());
    const btns = [...app.querySelectorAll(".copt")];
    if (k >= 0 && btns[k] && !cRun.picked) choose(Number(btns[k].dataset.k), btns[k]);
  };
}

async function choose(k, btn) {
  if (!cRun || cRun.picked) return;
  cRun.picked = true;
  clearInterval(cTimer);
  document.onkeydown = null;
  app.querySelectorAll(".copt").forEach((b) => (b.disabled = true));
  try {
    const data = await api(`/api/clutch-runs/${cRun.id}/pick`, { choice: k });
    const r = data.result;
    const good = r.grade === "best";
    if (btn) btn.classList.add(good ? "win" : r.grade === "good" ? "ok" : "lose");
    if (good) (r.streak >= 2 ? sfx.combo(r.streak) : sfx.good()); else if (r.grade !== "good") sfx.bad();
    if (r.you_said) cRun.log.push(["you", r.you_said]);
    cRun.log.push(["buyer", r.reaction]);
    const label = { best: "Clutch!", good: "Okay, not great.", bad: "That hurt the deal.", worst: "Ouch. That nearly killed it.", froze: "You froze." }[r.grade];
    $("c-feedback").innerHTML = `
      <div class="c-fb card g-${r.grade}">
        <div class="c-fb-top"><b>${label}</b><span class="pixel">${r.points > 0 ? "+" : ""}${r.points}</span></div>
        <div class="bubble buyer" style="margin:10px 0"><div class="who">${esc(cRun.s.buyer.name)}</div>${esc(r.reaction)}</div>
        <p>${esc(r.why)}</p>
        ${r.best ? `<div class="model"><b>The clutch line</b>${esc(r.best.text)}<br><span class="muted">${esc(r.best.why)}</span></div>` : ""}
        ${r.speed ? `<span class="bonus">speed +${r.speed}</span>` : ""} ${r.streak >= 2 ? `<span class="bonus">streak ×${r.streak}</span>` : ""}
        <div class="actions"><button class="btn primary" id="c-next">${data.summary ? "See how it ended →" : "Next moment →"}</button></div>
      </div>`;
    document.querySelector(".health").outerHTML = healthBar(r.health);
    $("c-score").textContent = fmt(r.score);
    $("c-feedback").scrollIntoView({ behavior: "smooth", block: "nearest" });
    const next = () => {
      document.onkeydown = null;
      cRun.picked = false;
      if (data.summary) return showClutchEnd(data.summary);
      cRun.m = data.next;
      showMoment();
    };
    $("c-next").onclick = next;
    document.onkeydown = (e) => { if (e.key === "Enter") next(); };
  } catch (err) {
    toast(err.message);
  }
}

function showClutchEnd(s) {
  document.onkeydown = null;
  const win = s.outcome === "win";
  if (win) { sfx.win(); confetti(); } else if (s.outcome === "ok") sfx.coin(); else sfx.lose();
  app.innerHTML = `
    <section class="res-head">
      <div class="grade pixel ${win ? "good" : s.outcome === "ok" ? "warn" : "bad"}">${s.bests}/6</div>
      <div>
        <span class="outcome ${win ? "closed" : s.outcome === "ok" ? "follow_up" : "hung_up"}">${win ? "Won the call" : s.outcome === "ok" ? "Still in play" : "Lost them"}</span>
        <div class="bigpoints pixel">${fmt(s.score)} PTS ${s.new_best ? '<span class="newbest pixel">NEW BEST</span>' : ""}</div>
        <h2>${esc(s.ending)}</h2>
        <p class="muted">Clutch lines: ${s.bests}/${s.moments} · best streak ×${s.best_streak} · final deal health ${s.health}${s.bonus ? ` · outcome bonus +${s.bonus}` : ""}</p>
        ${state.user ? "" : `<div class="banner info">Guest run, not saved. <a href="#/signup">Sign up</a> to get on the leaderboard.</div>`}
        <div class="actions"><a class="btn primary" href="#/clutch">Play another call</a>
          <a class="btn ghost" href="#/leaderboard?mode=clutch">Leaderboard</a></div>
      </div>
    </section>
    <div class="card"><h3>Every moment</h3>
      ${s.picks.map((p) => `<details style="border-bottom:1px solid var(--line);padding:12px 0">
        <summary><b class="${p.grade === "best" ? "good" : p.grade === "good" ? "warn" : "bad"}">${p.grade === "best" ? "✓" : "✗"} Moment ${p.moment}</b> · ${esc(p.you_said || "(froze)")}</summary>
        <p class="muted">${esc(p.why)}</p>${p.best ? `<div class="model"><b>The clutch line</b>${esc(p.best.text)}</div>` : ""}</details>`).join("")}
    </div>`;
}
