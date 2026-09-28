// Daily Challenge page and the "a friend challenged you" page

async function renderDaily() {
  const d = await api("/api/daily");
  const c = findCharacter(d.character.id) || d.character;
  const board = d.top.length
    ? `<table class="lb">${d.top.map((r, i) => `<tr><td class="place p${i + 1}">${i + 1}</td>
        <td><a class="player" href="#/u/${encodeURIComponent(r.username)}">${avatar(r.display_name, r.color, "sm")}<span>${esc(r.display_name)}</span></a></td>
        <td class="num pixel" style="font-size:12px">${fmt(r.score)}</td></tr>`).join("")}</table>`
    : `<div class="empty">Nobody has played today's challenge yet. Be first.</div>`;

  if (d.played || !state.user) {
    app.innerHTML = `
      <a class="back" href="#/play">← Arcade</a>
      <section class="hero" style="padding-bottom:18px">
        <h1>${esc(c.nickname)}</h1>
        <p class="lede">Daily challenge for ${esc(d.date)}. ${esc(d.category)}, "${esc(c.tagline)}" Same buyer for everyone today, one scored try.</p>
      </section>
      ${d.played ? `<div class="banner">✓ You scored <b>${fmt(d.played.points)}</b> today (${esc(OUTCOME_TEXT[d.played.outcome] || d.played.outcome)}). A new buyer drops at midnight Pacific.</div>`
        : `<div class="banner info">You can play as a guest, but your score won't count. <a href="#/signup">Sign up</a> to get on today's board.</div>
           <div class="actions"><button class="btn gold big" id="daily-go">Play as guest</button></div>`}
      <div class="section-title"><h2>Today's top 10</h2></div>
      <div class="card">${board}</div>`;
    if ($("daily-go")) $("daily-go").onclick = () => dailyPreCall(c);
    return;
  }
  dailyPreCall(c, board);
}

function dailyPreCall(c, board) {
  preCallScreen(c, {
    start: () => api("/api/daily/start", {}),
    back: ["#/play", "Arcade"],
    banner: `<div class="banner" style="margin-bottom:20px"><b>Daily Challenge.</b> One scored try, so make it count.</div>`,
  });
  if (board) {
    const extra = document.createElement("div");
    extra.innerHTML = `<div class="section-title"><h2>Today's top 10</h2></div><div class="card">${board}</div>`;
    app.appendChild(extra);
  }
}

async function renderChallenge(code) {
  let ch;
  try {
    ch = await api("/api/challenges/" + encodeURIComponent(code));
  } catch (err) {
    app.innerHTML = `<div class="empty">${esc(err.message)}<br><br><a href="#/play">Go to the arcade</a></div>`;
    return;
  }
  const c = findCharacter(ch.character.id) || ch.character;
  app.innerHTML = `
    <section class="card challenge-card">
      ${avatar(ch.from.display_name, ch.from.color, "lg")}
      <h1>${esc(ch.from.display_name)} scored ${fmt(ch.points)}</h1>
      <p class="lede">against <b>${esc(c.nickname)}</b> (${esc(ch.category)}). Same buyer, one call. Can you beat it?</p>
      <div class="actions" style="justify-content:center"><button class="btn gold big" id="accept">Accept the challenge</button></div>
      ${state.user ? "" : `<p class="tip">You can play as a guest. <a href="#/signup">Sign up</a> to save your score.</p>`}
    </section>`;
  $("accept").onclick = () => preCallScreen(c, {
    start: () => api(`/api/challenges/${encodeURIComponent(code)}/start`, {}),
    back: ["#/play", "Arcade"],
    banner: `<div class="banner" style="margin-bottom:20px">Beat <b>${fmt(ch.points)}</b> points to win.</div>`,
  });
}
