// results page after a call

function scoreRing(score) {
  const r = 62;
  const c = 2 * Math.PI * r;
  const color = score >= 75 ? "var(--good)" : score >= 45 ? "var(--warn)" : "var(--bad)";
  return `<svg class="ring" viewBox="0 0 150 150" role="img" aria-label="Skill score ${score} out of 100">
    <circle cx="75" cy="75" r="${r}" fill="none" stroke="var(--panel-2)" stroke-width="12"/>
    <circle cx="75" cy="75" r="${r}" fill="none" stroke="${color}" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${(c * score) / 100} ${c}" transform="rotate(-90 75 75)"/>
    <text x="75" y="80" text-anchor="middle" class="num">${score}</text>
    <text x="75" y="102" text-anchor="middle" class="of">skill score</text></svg>`;
}

function moodChart(points, hangLine) {
  const W = 600, H = 220, pad = 24;
  const n = points.length;
  const x = (i) => pad + (n <= 1 ? 0 : (i * (W - 2 * pad)) / (n - 1));
  const y = (v) => H - pad - (v / 100) * (H - 2 * pad);
  const path = points.map((v, i) => (i ? "L" : "M") + x(i) + "," + y(v)).join(" ");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Buyer interest during the call">
    <line class="axis" x1="${pad}" x2="${W - pad}" y1="${H - pad}" y2="${H - pad}"/>
    <line class="hang" x1="${pad}" x2="${W - pad}" y1="${y(hangLine)}" y2="${y(hangLine)}"/>
    <text x="${W - pad}" y="${y(hangLine) - 5}" text-anchor="end">hang-up line</text>
    <path class="ln" d="${path}"/>
    ${points.map((v, i) => `<circle class="dot" cx="${x(i)}" cy="${y(v)}" r="3.5"/>`).join("")}
  </svg>`;
}

function renderResults() {
  if (!state.lastResult) return go("#/");
  const card = state.lastResult.card;
  const c = findCharacter(state.lastResult.characterId);
  const cat = c ? categoryFor(c) : findCategory(card.category);
  const custom = card.kind === "custom";
  const m = card.metrics;
  const co = card.coaching || {};
  const p = card.points;
  const prog = card.progress;
  const earned = new Set(p.badges.map((b) => b.id));
  const penalties = p.badges.filter((b) => b.points < 0);
  const first = card.buyer.split(" ")[0] === "Dr." ? card.buyer : card.buyer.split(" ")[0];

  let outcome = OUTCOME_TEXT[m.outcome] || "No deal";
  if (m.outcome === "meeting_booked") outcome = cat.labels.meeting + " ✓";
  if (m.outcome === "closed") outcome = cat.labels.close + " ✓";
  if (m.upsold) outcome += " + upsell";

  // what to show under the score
  let banners = "";
  if (card.challenge) {
    const ch = card.challenge;
    banners += `<div class="card vs" style="margin-top:12px">
      <div><div class="muted">${esc(ch.their_name)}</div><div class="n pixel">${fmt(ch.their_points)}</div></div>
      <div class="x pixel">VS</div>
      <div><div class="muted">You</div><div class="n pixel ${ch.won ? "good" : "bad"}">${fmt(ch.your_points)}</div></div>
    </div><div class="banner ${ch.won ? "" : "info"}">${ch.won ? `You beat ${esc(ch.their_name)}!` : `${esc(ch.their_name)} wins this one. Run it back?`}</div>`;
  }
  if (card.kind === "daily") banners += `<div class="banner info">Daily Challenge ${card.result_id ? "score saved" : "done"}. <a href="#/daily">See today's leaderboard</a></div>`;
  if (custom) {
    banners += `<div class="banner info">Buyers you build are just for practice, so they don't add points or hit the leaderboard.</div>`;
  } else if (prog) {
    if (prog.new_best) banners += `<div class="banner">New personal best on ${esc(card.nickname)}!</div>`;
    for (const u of prog.unlocked) banners += `<div class="banner">Unlocked: <b>${esc(u.nickname)}</b>${u.boss ? ", the final boss" : ""}</div>`;
    for (const u of prog.pro_next || []) banners += `<div class="banner info">Next up is <b>${esc(u.nickname)}</b>, a Pro level. <a href="#/pricing">Go Pro</a> to keep climbing.</div>`;
    if (prog.rank_up) banners += `<div class="banner info">Rank up! You're now a <b>${esc(prog.rank_up)}</b>.</div>`;
  } else {
    banners += `<div class="banner info">You're a guest, so this score wasn't saved. <a href="#/signup">Sign up</a> to get on the leaderboard.</div>`;
  }

  const next = prog && prog.unlocked.length ? prog.unlocked[0] : null;

  app.innerHTML = `
    <section class="res-head">
      ${scoreRing(card.score.total)}
      <div>
        <span class="outcome ${esc(m.outcome)}">${esc(outcome)}</span>
        <div class="bigpoints pixel">${fmt(p.total)} PTS ${prog && prog.new_best ? '<span class="newbest pixel">NEW BEST</span>' : ""}</div>
        <h2>${esc(co.headline || "")}</h2>
        <p>${esc(card.nickname)} · ${m.rep_turns} turn${m.rep_turns === 1 ? "" : "s"} · best combo ×${m.best_combo || 0}
          ${p.revenue ? ` · <span class="good">${money(p.revenue)} closed</span>` : ""}</p>
        ${banners}
        <div class="actions">
          ${next ? `<a class="btn primary" href="#/call/${next.id}">Next: ${esc(next.nickname)} →</a>` : ""}
          ${card.kind === "call" ? `<a class="btn ${next ? "ghost" : "primary"}" href="#/call/${c.id}">Call ${esc(first)} again</a>` : ""}
          ${card.kind === "challenge" ? `<a class="btn primary" href="#/challenge/${card.challenge ? card.challenge.code : ""}">Run it back</a>` : ""}
          ${custom ? `<a class="btn primary" href="#/build/${c.id}">Call ${esc(first)} again</a>
            <a class="btn ghost" href="#/build">Build another buyer</a>`
            : `<a class="btn ghost" href="#/category/${cat.id}">${esc(cat.name)} levels</a>`}
        </div>
        <div class="share-row">
          <button class="btn ghost small" id="share-img">Save score card</button>
          <button class="btn ghost small" id="share-copy">Copy result</button>
          ${card.result_id && state.user && !custom ? `<button class="btn ghost small" id="challenge-btn">Challenge a friend</button>` : ""}
        </div>
      </div>
    </section>

    <section class="grid">
      <div class="card s6"><h3>Points</h3>
        <table class="ptable">
          ${p.lines.map((l) => `<tr class="${l.points < 0 ? "neg" : ""}"><td>${esc(l.label)}</td><td>${l.points > 0 ? "+" : ""}${fmt(l.points)}</td></tr>`).join("")}
          <tr><td>Difficulty multiplier</td><td>×${p.multiplier}</td></tr>
          <tr class="total"><td>Total</td><td>${fmt(p.total)}</td></tr>
          ${p.revenue ? `<tr class="rev"><td>Revenue closed</td><td>${money(p.revenue)}</td></tr>` : ""}
        </table>
      </div>
      <div class="card s6"><h3>Badges</h3>
        <div class="badges">
          ${p.all_badges.map((b) => `<div class="badge ${earned.has(b.id) ? "" : "missing"}" title="${esc(b.desc)}">
            <div><div class="n">${esc(b.name)}</div><div class="d">${esc(b.desc)}</div><div class="p">+${b.points}</div></div></div>`).join("")}
          ${penalties.map((b) => `<div class="badge neg"><div><div class="n">${esc(b.name)}</div>
            <div class="d">${esc(b.desc)}</div><div class="p">${b.points}</div></div></div>`).join("")}
        </div>
      </div>

      <div class="card s12"><div class="stats">
        <div class="stat"><div class="v ${m.talk_ratio <= 55 ? "good" : m.talk_ratio <= 65 ? "warn" : "bad"}">${m.talk_ratio}%</div><div class="l">You talked (top reps: under 50%)</div></div>
        <div class="stat"><div class="v">${m.objections_handled}<small> / ${m.objections_raised}</small></div><div class="l">Objections turned around</div></div>
        <div class="stat"><div class="v">${m.pains_uncovered}<small> / ${m.pains_total}</small></div><div class="l">Hidden problems found</div></div>
        <div class="stat"><div class="v">${m.open_questions}<small> / ${m.questions}</small></div><div class="l">Open-ended questions</div></div>
      </div></div>

      <div class="card s8"><h3>Buyer interest during the call</h3>${moodChart(m.mood_timeline, card.hang_up_below)}</div>
      <div class="card s4"><h3>Skill breakdown</h3>
        ${card.score.breakdown.map((b) => `<div class="bar-row"><span>${esc(b.label)}</span><span class="pts">${b.points}/${b.max}</span>
          <div class="bar"><div style="width:${(100 * b.points) / b.max}%"></div></div></div>`).join("")}
      </div>

      <div class="card s6"><h3>What you did well</h3><ul class="list">${(co.strengths || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>
      <div class="card s6"><h3>Fix this next time</h3><ul class="list">${(co.improvements || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>

      ${card.key_moments.length ? `<div class="card s12"><h3>Key moments</h3>
        ${card.key_moments.map((k) => `<div class="moment ${k.type}">
          <span class="tag ${k.type === "win" ? "good" : "bad"}">${k.type === "win" ? "▲ Won them over" : "▼ Lost them"} (${k.mood_change > 0 ? "+" : ""}${k.mood_change})</span>
          <q>${esc(k.you_said)}</q>
          <div class="reply">${esc(first)}: “${esc(k.buyer_said)}”</div>
          ${k.note ? `<div class="note">${esc(k.note)}</div>` : ""}</div>`).join("")}</div>` : ""}

      ${co.better_line ? `<div class="card s6 better"><h3>Say it better</h3>
        <div class="from">“${esc(co.better_line.original)}”</div><div class="to">“${esc(co.better_line.improved)}”</div></div>` : ""}
      ${(co.objection_handling || []).length ? `<div class="card s6"><h3>Objection handling</h3><ul class="list">
        ${co.objection_handling.map((o) => `<li><b>${esc(o.objection)}</b>: <span class="${o.grade === "strong" ? "good" : o.grade === "weak" ? "bad" : "warn"}">${esc(o.grade)}</span>. ${esc(o.tip)}</li>`).join("")}</ul></div>` : ""}

      <div class="card s12"><h3>What ${esc(first)} wasn't telling you</h3>
        ${card.revealed_pains.map((x) => `<div class="secret"><b class="good">✓ Found</b>${esc(x)}</div>`).join("")}
        ${card.missed_pains.map((x) => `<div class="secret"><b class="bad">✗ Missed</b>${esc(x)}</div>`).join("")}
      </div>

      <div class="card s12"><h3>Call replay</h3>
        <div class="actions" style="margin:0 0 8px"><button class="btn primary small" id="play-all">${PLAY_ALL}</button>
          <span class="muted" style="align-self:center;font-size:13px">${Object.keys(state.lastResult.recordings || {}).length
            ? "Your side was recorded in voice mode (it stays in your browser)." : "Your lines only get recorded in voice mode."}</span></div>
        <div id="replay">${replayRows(card)}</div>
        ${co.note ? `<p class="tip">${esc(co.note)}</p>` : ""}
      </div>
    </section>`;

  const won = ["closed", "meeting_booked"].includes(m.outcome) || (card.challenge && card.challenge.won);
  if (prog && (prog.rank_up || prog.unlocked.length)) sfx.levelUp();
  else if (won) sfx.coin();

  $("share-img").onclick = () => downloadScoreCard(card, outcome);
  $("share-copy").onclick = () => {
    const text = `I just played ${card.nickname} on Callcade: ${outcome}, ${fmt(p.total)} points (skill ${card.score.total}/100).`;
    navigator.clipboard.writeText(text).then(() => toast("Copied! Paste it anywhere."));
  };
  if ($("challenge-btn")) {
    $("challenge-btn").onclick = async () => {
      try {
        const r = await api("/api/challenges", { result_id: card.result_id });
        const link = location.origin + "/#/challenge/" + r.code;
        await navigator.clipboard.writeText(link).catch(() => {});
        $("challenge-btn").outerHTML = `<input class="small" style="max-width:340px" readonly value="${esc(link)}" onclick="this.select()">`;
        toast("Challenge link copied. Send it to a friend!");
      } catch (err) {
        toast(err.message);
      }
    };
  }
  setupReplay(card, c);
}

// ---------------- replay ----------------

const PLAY_ALL = "▶ Play the whole call";

function replayRows(card) {
  let repIndex = 0;
  let lastMood = card.transcript[0] ? card.transcript[0].mood : 0;
  const recs = state.lastResult.recordings || {};
  return card.transcript.map((t, i) => {
    let extra = "";
    let canPlay = true;
    if (t.speaker === "rep") {
      canPlay = !!recs[repIndex];
      t.rec = recs[repIndex];
      repIndex++;
    } else if (i > 0) {
      const d = t.mood - lastMood;
      extra = `<span class="delta ${d > 0 ? "good" : d < 0 ? "bad" : "muted"}">${d > 0 ? "+" : ""}${d}</span>`;
      lastMood = t.mood;
    }
    return `<div class="replay-row" data-i="${i}">
      <button class="play" data-i="${i}" ${canPlay ? "" : "disabled"} title="Play">▶</button>
      <div><div class="who">${t.speaker === "rep" ? "You" : esc(card.nickname)}</div>${esc(t.text)}
        ${t.note ? `<div class="note">${esc(t.note)}</div>` : ""}</div>
      ${extra}
    </div>`;
  }).join("");
}

async function playTurn(card, c, i) {
  const t = card.transcript[i];
  document.querySelectorAll(".replay-row").forEach((r) => r.classList.toggle("playing", r.dataset.i === String(i)));
  if (t.speaker === "rep") {
    if (!t.rec) return;
    await new Promise((resolve) => {
      const a = new Audio(t.rec);
      a.onended = resolve;
      a.onerror = resolve;
      a.play().catch(resolve);
    });
  } else {
    await speak(t.text, { ...voiceOf(c), phoneLine: false });
  }
}

function setupReplay(card, c) {
  let playingAll = false;
  document.querySelectorAll(".replay-row .play").forEach((b) => {
    b.onclick = () => {
      playingAll = false;
      stopSpeaking();
      unlockAudio();
      playTurn(card, c, Number(b.dataset.i));
    };
  });
  $("play-all").onclick = async () => {
    if (playingAll) {
      playingAll = false;
      stopSpeaking();
      $("play-all").textContent = PLAY_ALL;
      return;
    }
    playingAll = true;
    unlockAudio();
    $("play-all").textContent = "■ Stop";
    for (let i = 0; i < card.transcript.length && playingAll; i++) {
      if (card.transcript[i].speaker === "rep" && !card.transcript[i].rec) continue;
      await playTurn(card, c, i);
      await sleep(300);
    }
    playingAll = false;
    if ($("play-all")) $("play-all").textContent = PLAY_ALL;
  };
}

// ---------------- share card ----------------

function downloadScoreCard(card, outcome) {
  const W = 1200, H = 630;
  const cv = document.createElement("canvas");
  cv.width = W;
  cv.height = H;
  const g = cv.getContext("2d");
  g.fillStyle = "#111214";
  g.fillRect(0, 0, W, H);
  // orange frame, like the edge of an arcade screen
  g.strokeStyle = "#ff6b35";
  g.lineWidth = 12;
  g.strokeRect(24, 24, W - 48, H - 48);
  const pixel = '"Press Start 2P", monospace';
  g.textAlign = "center";
  g.fillStyle = "#ff6b35";
  g.font = `28px ${pixel}`;
  g.fillText("CALLCADE", W / 2, 80);
  g.fillStyle = "#ffffff";
  g.font = "bold 54px Rubik, sans-serif";
  g.fillText(card.nickname, W / 2, 180);
  g.fillStyle = ["closed", "meeting_booked"].includes(card.metrics.outcome) ? "#34d399" : "#fbbf24";
  g.font = "bold 34px Rubik, sans-serif";
  g.fillText(outcome.toUpperCase(), W / 2, 240);
  g.fillStyle = "#fcd34d";
  g.font = `64px ${pixel}`;
  g.fillText(fmt(card.points.total) + " PTS", W / 2, 350);
  g.fillStyle = "#b0b2ba";
  g.font = "28px Rubik, sans-serif";
  g.fillText(`Skill ${card.score.total}/100 · best combo x${card.metrics.best_combo || 0}` +
    (state.user ? ` · ${state.user.display_name}` : ""), W / 2, 410);
  g.fillStyle = "#ffd23f";
  g.font = `18px ${pixel}`;
  g.fillText("CAN YOU BEAT IT?", W / 2, 560);

  const a = document.createElement("a");
  a.download = `callcade-${card.character_id}.png`;
  a.href = cv.toDataURL("image/png");
  a.click();
}
