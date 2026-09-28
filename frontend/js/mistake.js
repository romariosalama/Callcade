// Spot the Mistake: review real calls and find every mistake the rep made

let mRun = null;
let mTimer = null;

function cleanupMistake() {
  clearInterval(mTimer);
  mRun = null;
}

async function renderMistakeMenu() {
  cleanupMistake();
  let best = 0;
  if (state.user) best = (await api("/api/profile/me")).stats.best.mistake;
  const top = await api("/api/leaderboard?mode=mistake");
  app.innerHTML = `
    <a class="back" href="#/play">← Arcade</a>
    <section class="hero">
      <h1>Spot the Mistake</h1>
      <p class="lede">You're the sales manager reviewing call recordings. Each call hides 3 or 4 mistakes, but most of what
        the rep says is actually good. Find every mistake, then name what kind of mistake it was.</p>
    </section>
    <div class="rules">
      <div><b>3 calls</b>about 20 lines each, with real objections. 90 seconds per call.</div>
      <div><b>3 lives</b>Tap a line that's fine and you lose a life. You don't know how many mistakes there are.</div>
      <div><b>+150 / +100</b>for finding a mistake, then for naming it right. Every one you miss costs 75.</div>
    </div>
    <div class="actions"><button class="btn go big" id="m-start">Start reviewing</button></div>
    <p class="tip">${state.user ? `Your best: <b>${fmt(best)}</b>.` : `Playing as a guest, so your score won't be saved.`}
      ${top.length ? ` Top score: <b>${fmt(top[0].score)}</b> by ${esc(top[0].display_name)}.` : ""}</p>`;
  $("m-start").onclick = async () => {
    ctx();
    sfx.coin();
    const data = await api("/api/mistakes", {});
    mRun = { id: data.run_id, call: data.round };
    showMistakeCall();
  };
}

async function showMistakeCall() {
  const c = mRun.call;
  mRun.busy = false;
  mRun.naming = false;
  const cat = findCategory(c.category);
  app.innerHTML = `
    <section class="film">
      <div class="m-top">
        <span class="pixel tiny">CALL ${c.call_no}/${c.of}</span>
        <span class="hearts" id="m-lives">${hearts(c.lives)}</span>
        <span class="pixel" id="m-score" style="font-size:12px;color:var(--gold)">${fmt(c.score)}</span>
      </div>
      <div class="timebar"><div id="m-bar" style="width:100%"></div></div>
      <div class="film-head">
        <div><h2>${esc(c.title)}</h2>
          <p class="muted">Rep: ${esc(c.rep)} · Buyer: ${esc(c.buyer)}</p></div>
        <div class="film-count"><b id="m-found">0</b> found</div>
      </div>
      <p class="tip" style="margin-top:0">Tap the rep lines where they made a mistake. When you think you've got them all, lock it in.</p>
      <div class="film-lines" id="m-lines">
        ${c.lines.map(([who, text], i) => `
          <button class="fl ${who}" data-i="${i}" ${who === "buyer" ? "disabled" : ""}>
            <span class="who">${who === "rep" ? "Rep" : "Buyer"}</span><span class="txt">${esc(text)}</span>
            <span class="mark"></span>
          </button>`).join("")}
      </div>
      <div id="m-name"></div>
      <div class="film-foot"><button class="btn primary big" id="m-lock">Lock it in</button></div>
    </section>`;

  await api(`/api/mistakes/${mRun.id}/ready`, {});
  const started = Date.now();
  const limit = c.time_limit * 1000;
  clearInterval(mTimer);
  mTimer = setInterval(() => {
    const left = Math.max(0, limit - (Date.now() - started));
    if ($("m-bar")) {
      $("m-bar").style.width = (100 * left) / limit + "%";
      $("m-bar").style.background = left < 15000 ? "var(--bad)" : left < 40000 ? "var(--warn)" : "var(--good)";
    }
    if (left <= 0) lockCall();
  }, 200);

  app.querySelectorAll(".fl.rep").forEach((b) => (b.onclick = () => tapLine(Number(b.dataset.i))));
  $("m-lock").onclick = lockCall;
}

async function tapLine(i) {
  if (!mRun || mRun.busy || mRun.naming) return;
  const btn = document.querySelector(`.fl[data-i="${i}"]`);
  if (btn.classList.contains("hit") || btn.classList.contains("miss")) return;
  mRun.busy = true;
  try {
    const r = await api(`/api/mistakes/${mRun.id}/tap`, { index: i });
    mRun.busy = false;
    if (r.review) return showReview(r);
    $("m-score").textContent = fmt(r.score);
    if (r.hit) {
      sfx.good();
      btn.classList.add("hit");
      btn.querySelector(".mark").textContent = "+150";
      $("m-found").textContent = document.querySelectorAll(".fl.hit").length;
      askType(i, r.options);
    } else {
      sfx.bad();
      btn.classList.add("miss", "shake");
      btn.querySelector(".mark").textContent = "Not a mistake · −50";
      $("m-lives").innerHTML = hearts(r.lives);
    }
  } catch (err) {
    mRun.busy = false;
    toast(err.message);
  }
}

function askType(i, options) {
  mRun.naming = true;
  const btn = document.querySelector(`.fl[data-i="${i}"]`);
  $("m-name").innerHTML = `
    <div class="name-it card">
      <div class="pixel tiny accent">NAME THE MISTAKE · +100</div>
      <p>“${esc(btn.querySelector(".txt").textContent)}”</p>
      <div class="name-opts">${options.map((o) => `<button class="chip" data-t="${o.id}">${esc(o.label)}</button>`).join("")}</div>
    </div>`;
  $("m-name").scrollIntoView({ behavior: "smooth", block: "nearest" });
  $("m-name").querySelectorAll("[data-t]").forEach((b) => {
    b.onclick = async () => {
      const r = await api(`/api/mistakes/${mRun.id}/classify`, { index: i, type: b.dataset.t });
      mRun.naming = false;
      $("m-score").textContent = fmt(r.score);
      if (r.right) sfx.combo(2); else sfx.bad();
      btn.querySelector(".mark").textContent = r.right ? "+250 · " + r.label : "+150 · it was: " + r.label;
      btn.classList.add(r.right ? "named" : "misnamed");
      $("m-name").innerHTML = `<div class="name-it card ${r.right ? "right" : "wrong"}">
        <b>${r.right ? "✓ Nailed it." : "✗ Close. It was: " + esc(r.label)}</b>
        <p>${esc(r.why)}</p><div class="model"><b>Better</b>${esc(r.fix)}</div></div>`;
    };
  });
}

async function lockCall() {
  if (!mRun || mRun.locking) return;
  mRun.locking = true;
  clearInterval(mTimer);
  try {
    const r = await api(`/api/mistakes/${mRun.id}/lock`, {});
    showReview(r);
  } catch (err) {
    toast(err.message);
  }
}

function showReview(r) {
  clearInterval(mTimer);
  const rv = r.review;
  const byIndex = Object.fromEntries(rv.mistakes.map((m) => [m.index, m]));
  const found = rv.mistakes.filter((m) => m.found).length;
  if (rv.perfect) { sfx.win(); confetti(); } else if (found) sfx.coin(); else sfx.lose();
  app.innerHTML = `
    <section class="film">
      <div class="review-head card">
        <div class="pixel" style="font-size:34px;color:${rv.perfect ? "var(--good)" : found === rv.mistakes.length ? "var(--gold)" : "var(--bad)"}">${found}/${rv.mistakes.length}</div>
        <div>
          <h2>${rv.perfect ? "Perfect review." : found === rv.mistakes.length ? "Found them all." : `You missed ${rv.missed}.`}</h2>
          <p class="muted">${rv.wrong.length ? `${rv.wrong.length} wrong tap${rv.wrong.length > 1 ? "s" : ""} · ` : ""}
            ${rv.penalty ? `missed: ${rv.penalty} · ` : ""}${rv.bonus ? `bonus: +${rv.bonus} · ` : ""}score: <b>${fmt(rv.score)}</b></p>
        </div>
        <button class="btn primary" id="m-next">${r.done ? "See results →" : "Next call →"}</button>
      </div>
      <h3 class="section-h" style="margin-top:22px">The tape: ${esc(rv.title)}</h3>
      <div class="film-lines review">
        ${rv.lines.map(([who, text], i) => {
          const m = byIndex[i];
          const wrong = rv.wrong.includes(i);
          return `<div class="fl ${who} ${m ? (m.found ? "hit" : "missed") : wrong ? "miss" : ""}">
            <span class="who">${who === "rep" ? "Rep" : "Buyer"}</span><span class="txt">${esc(text)}</span>
            ${m ? `<div class="why"><b>${m.found ? "✓ Found" : "✗ Missed"} · ${esc(m.label)}</b>${esc(m.why)}<div class="model"><b>Better</b>${esc(m.fix)}</div></div>` : ""}
            ${wrong ? `<div class="why"><b>This line was fine.</b></div>` : ""}
          </div>`;
        }).join("")}
      </div>
    </section>`;
  window.scrollTo(0, 0);
  $("m-next").onclick = () => {
    if (r.done) return showMistakeSummary(r.summary);
    mRun.call = r.next;
    mRun.locking = false;
    showMistakeCall();
  };
}

function showMistakeSummary(s) {
  const pct = s.total ? Math.round((100 * s.found) / s.total) : 0;
  if (pct >= 80) { sfx.win(); confetti(); }
  app.innerHTML = `
    <section class="res-head">
      <div class="grade pixel ${pct >= 80 ? "good" : pct >= 50 ? "warn" : "bad"}">${pct}%</div>
      <div>
        <span class="outcome ${s.lives > 0 ? "closed" : "hung_up"}">${s.lives > 0 ? "Review complete" : "Out of lives"}</span>
        <div class="bigpoints pixel">${fmt(s.score)} PTS ${s.new_best ? '<span class="newbest pixel">NEW BEST</span>' : ""}</div>
        <h2>You caught ${s.found} of ${s.total} mistakes across ${s.calls} call${s.calls > 1 ? "s" : ""}.</h2>
        ${state.user ? "" : `<div class="banner info">Guest run, not saved. <a href="#/signup">Sign up</a> to get on the leaderboard.</div>`}
        <div class="actions">
          <a class="btn primary" href="#/mistake">Review more calls</a>
          <a class="btn ghost" href="#/leaderboard?mode=mistake">Leaderboard</a>
        </div>
      </div>
    </section>`;
}
