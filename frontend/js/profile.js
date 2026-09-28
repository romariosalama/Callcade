// profile pages: your own (#/profile) and other players' (#/u/username)

const PROFILE_COLORS = ["#ff6b35", "#34d399", "#f472b6", "#fbbf24", "#60a5fa", "#f87171", "#22d3ee", "#ffd23f", "#fb923c"];

async function renderProfile(username) {
  let data;
  try {
    data = username ? await api("/api/users/" + encodeURIComponent(username)) : await api("/api/profile/me");
  } catch (err) {
    app.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    return;
  }
  const u = data.user;
  const s = data.stats;
  const mine = state.user && state.user.id === u.id;
  const joined = new Date(u.created_at).toLocaleDateString("en-US", { month: "long", year: "numeric" });

  app.innerHTML = `
    <section class="p-head">
      ${avatar(u.display_name, u.color, "lg")}
      <div>
        <h1>${esc(u.display_name)}</h1>
        <div class="handle">@${esc(u.username)} · joined ${joined}</div>
        ${u.bio ? `<div class="bio">${esc(u.bio)}</div>` : ""}
      </div>
      ${mine ? `<div class="right"><button class="btn ghost small" id="edit-btn">Edit profile</button>
        <a class="btn ghost small" href="#/settings">Settings</a><button class="btn ghost small" id="logout-btn">Log out</button></div>` : ""}
    </section>
    ${mine && !u.email_verified ? `<div class="banner info" style="margin-bottom:16px">Verify your email so your scores count on the leaderboard. <a href="#/settings">Resend the link</a></div>` : ""}

    <div id="edit-box"></div>
    ${mine ? planCard(data.plan) : ""}

    <section class="grid">
      <div class="card s12 rank-box">
        <div><div class="muted title">Rank</div><div class="pixel" style="font-size:16px;margin-top:8px">${esc(s.rank.name)}</div></div>
        <div>
          <div class="xp-track"><div class="xp-fill" style="width:${s.rank.progress}%"></div></div>
          <div class="xp-label">${fmt(s.points)} career points${s.rank.next ? ` · ${fmt(s.rank.next_at - s.points)} to ${esc(s.rank.next)}` : ""}</div>
        </div>
      </div>

      <div class="card s8"><h3>Skill score, last ${s.progress.length} calls</h3>${progressChart(s.progress)}</div>
      <div class="card s4"><h3>Streak</h3>
        <div class="pixel streak-fire ${s.streak ? "" : "cold"}" style="font-size:28px">${s.streak}</div><div class="muted small-note">day streak</div>
        <p class="muted">${s.streak ? (s.played_today ? "Played today. Nice." : "Play today to keep it alive!") : "Play today to start a streak."}</p>
        <p class="muted">Best streak: <b style="color:var(--text)">${s.best_streak} day${s.best_streak === 1 ? "" : "s"}</b></p>
      </div>
      ${mine && s.weak_spot ? `<div class="card s12 weak-card" style="margin:0"><div><b>Coach's tip: ${esc(s.weak_spot.title)}</b>
        <p>${esc(s.weak_spot.tip)} (your average on ${esc(s.weak_spot.skill.toLowerCase())}: ${s.weak_spot.score}%)</p></div>
        <a class="btn ghost small" href="${s.weak_spot.link}">Practice it</a></div>` : ""}

      <div class="card s12"><div class="stats">
        <div class="stat"><div class="v good">${money(s.revenue)}</div><div class="l">Revenue closed</div></div>
        <div class="stat"><div class="v">${s.calls}</div><div class="l">Calls made</div></div>
        <div class="stat"><div class="v">${s.win_rate}%</div><div class="l">Win rate (${s.wins} win${s.wins === 1 ? "" : "s"}, ${s.closes} closed)</div></div>
        <div class="stat"><div class="v">${s.avg_skill}</div><div class="l">Average skill score</div></div>
        <div class="stat"><div class="v">×${s.best_combo}</div><div class="l">Best combo</div></div>
        <div class="stat"><div class="v">${fmt(s.gauntlet_best)}</div><div class="l">Best gauntlet run</div></div>
        <div class="stat"><div class="v">${fmt(s.best.mistake)} / ${fmt(s.best.clutch)}</div><div class="l">Best Mistake / Clutch Call</div></div>
        <div class="stat"><div class="v">${s.badges.filter((b) => b.count > 0).length}<small> / ${s.badges.length}</small></div><div class="l">Badges collected</div></div>
      </div></div>

      <div class="card s5"><h3>Industries</h3>
        <div class="cat-prog">
          ${s.categories.map((c) => `
            <div class="row"><span class="cat-dot" style="--c:${c.color[0]}"></span><span>${esc(c.name)}</span><span class="muted" style="text-align:right">${c.beaten}/${c.total}</span>
              <div class="bar"><div style="width:${(100 * c.beaten) / c.total}%"></div></div></div>`).join("")}
        </div>
      </div>

      <div class="card s7"><h3>Badge collection</h3>
        <div class="badges">
          ${s.badges.map((b) => `<div class="badge ${b.count ? "" : "missing"}">
            <div><div class="n">${esc(b.name)}${b.count ? ` ×${b.count}` : ""}</div><div class="d">${esc(b.desc)}</div></div></div>`).join("")}
        </div>
      </div>

      <div class="card s12"><h3>Recent activity</h3>
        ${s.recent.length ? `<table class="activity">
          ${s.recent.map((r) => `<tr>
            <td>${esc(r.buyer)}</td>
            <td><span class="outcome ${esc(r.outcome === "completed" ? "closed" : r.outcome)}">${esc(OUTCOME_TEXT[r.outcome] || r.outcome)}</span></td>
            <td class="muted">${timeAgo(r.created_at)}</td>
            <td>${fmt(r.points)} pts</td></tr>`).join("")}
        </table>` : `<div class="empty">No calls yet.${mine ? ` <a href="#/">Make your first one.</a>` : ""}</div>`}
      </div>
    </section>`;

  if (mine) {
    if ($("switch-btn")) {
      $("switch-btn").onclick = async () => {
        try {
          state.plan = await api("/api/plan/industry", { category: $("switch-cat").value });
          await refreshCategories();
          toast("Your free industry is now " + findCategory(state.plan.free_category).name);
          renderProfile();
        } catch (err) {
          toast(err.message);
        }
      };
    }
    $("logout-btn").onclick = logout;
    $("edit-btn").onclick = () => showEditForm(u);
  }
}

function showEditForm(u) {
  let color = u.color;
  $("edit-box").innerHTML = `
    <form class="card" id="edit-form" style="margin-bottom:16px;max-width:520px">
      <h3>Edit profile</h3>
      <label class="field">Display name<input id="e-name" maxlength="30" value="${esc(u.display_name)}"></label>
      <div class="muted" style="font-size:13px">Color</div>
      <div class="swatches">${PROFILE_COLORS.map((c) => `<span class="swatch ${c === color ? "on" : ""}" data-c="${c}" style="background:${c}"></span>`).join("")}</div>
      <label class="field">Bio<textarea id="e-bio" maxlength="160" rows="2" placeholder="What do you sell?">${esc(u.bio)}</textarea></label>
      <div class="form-error" id="e-err"></div>
      <div class="actions"><button class="btn primary" type="submit">Save</button><button class="btn ghost" type="button" id="e-cancel">Cancel</button></div>
    </form>`;
  document.querySelectorAll(".swatch").forEach((sw) => {
    sw.onclick = () => {
      color = sw.dataset.c;
      document.querySelectorAll(".swatch").forEach((x) => x.classList.toggle("on", x === sw));
    };
  });
  $("e-cancel").onclick = () => ($("edit-box").innerHTML = "");
  $("edit-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      state.user = await api("/api/profile", { display_name: $("e-name").value, color, bio: $("e-bio").value }, "PUT");
      renderAccount();
      renderProfile();
      toast("Profile saved");
    } catch (err) {
      $("e-err").textContent = err.message;
    }
  };
}

function planCard(p) {
  if (p.plan === "pro") {
    return `<section class="card plan-card" style="margin-bottom:16px"><div><h3>Your plan</h3>
      <b>Pro</b> · every industry, unlimited calls and gauntlet runs</div></section>`;
  }
  const cat = findCategory(p.free_category);
  const others = state.categories.filter((c) => c.id !== p.free_category);
  return `
    <section class="card plan-card" style="margin-bottom:16px">
      <div>
        <h3>Your plan</h3>
        <b>Free</b> · ${esc(cat.name)} levels 1-3 · ${p.calls_left}/10 calls and ${p.gauntlet_left}/3 gauntlet runs left today
        <div class="switch-row">
          ${p.can_switch ? `<select id="switch-cat">${others.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
            <button class="btn ghost small" id="switch-btn">Switch free industry</button>`
            : `<span class="muted">You can switch industries again on ${new Date(p.switch_after).toLocaleDateString()}.</span>`}
        </div>
      </div>
      <a class="btn primary" href="#/pricing">Go Pro · $${state.config.pro_price}/mo</a>
    </section>`;
}

function progressChart(points) {
  if (points.length < 2) return `<div class="empty" style="padding:30px">Play a couple of calls to see your progress here.</div>`;
  const W = 600, H = 180, pad = 26;
  const x = (i) => pad + (i * (W - 2 * pad)) / (points.length - 1);
  const y = (v) => H - pad - (v / 100) * (H - 2 * pad);
  const path = points.map((p, i) => (i ? "L" : "M") + x(i) + "," + y(p.skill)).join(" ");
  const area = path + ` L${x(points.length - 1)},${H - pad} L${x(0)},${H - pad} Z`;
  return `<svg class="progress-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Skill score over recent calls">
    <line class="axis" x1="${pad}" x2="${W - pad}" y1="${H - pad}" y2="${H - pad}"/>
    <line class="axis" x1="${pad}" x2="${W - pad}" y1="${y(50)}" y2="${y(50)}" stroke-dasharray="4 4"/>
    <text x="4" y="${y(50) + 4}">50</text><text x="4" y="${y(100) + 10}">100</text>
    <path class="area" d="${area}"/><path class="ln" d="${path}"/>
    ${points.map((p, i) => `<circle class="dot" cx="${x(i)}" cy="${y(p.skill)}" r="3.5"><title>${p.skill}/100 · ${esc(OUTCOME_TEXT[p.outcome] || p.outcome)}</title></circle>`).join("")}
  </svg>`;
}
