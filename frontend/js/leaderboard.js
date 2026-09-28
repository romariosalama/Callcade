// leaderboard page

async function renderLeaderboard(params) {
  const MODES = [["call", "Career"], ["daily", "Today's daily"], ["gauntlet", "Gauntlet"],
    ["mistake", "Spot the Mistake"], ["clutch", "Clutch Call"]];
  const mode = MODES.some(([m]) => m === params.get("mode")) ? params.get("mode") : "call";
  const period = params.get("period") === "week" ? "week" : "all";
  const category = params.get("category") || "";

  const catOptions = [["", "All industries"]].concat(state.categories.map((c) => [c.id, c.name]));
  if (mode === "gauntlet") catOptions.splice(1, 0, ["mixed", "Mixed"], ["general", "Any industry"]);

  app.innerHTML = `
    <section class="hero" style="padding-bottom:10px">
      <h1>Who's closing the most?</h1>
    </section>
    <div class="lb-controls">
      <div class="mode-switch" style="flex-wrap:wrap">
        ${MODES.map(([m, label]) => `<button data-mode="${m}" class="${mode === m ? "on" : ""}">${label}</button>`).join("")}
      </div>
      ${mode === "daily" ? "" : `<div class="mode-switch">
        <button data-period="all" class="${period === "all" ? "on" : ""}">All time</button>
        <button data-period="week" class="${period === "week" ? "on" : ""}">This week</button>
      </div>`}
      ${["call", "gauntlet"].includes(mode) ? `<select id="lb-cat">${catOptions.map(([id, name]) => `<option value="${id}" ${id === category ? "selected" : ""}>${esc(name)}</option>`).join("")}</select>` : ""}
    </div>
    <div class="card" id="lb-body"><div class="empty">Loading…</div></div>`;

  const update = (changes) => {
    const p = new URLSearchParams({ mode, period, category });
    for (const k in changes) p.set(k, changes[k]);
    if (!p.get("category")) p.delete("category");
    go("#/leaderboard?" + p.toString());
  };
  app.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => update({ mode: b.dataset.mode, category: "" })));
  app.querySelectorAll("[data-period]").forEach((b) => (b.onclick = () => update({ period: b.dataset.period })));
  if ($("lb-cat")) $("lb-cat").onchange = () => update({ category: $("lb-cat").value });

  const rows = await api(`/api/leaderboard?mode=${mode}&period=${period}&category=${encodeURIComponent(category)}`);
  if (!rows.length) {
    $("lb-body").innerHTML = `<div class="empty">Nobody's on the board yet. ${state.user ? `<a href="#/">Go make a call</a> and take first place.` : `<a href="#/signup">Sign up</a> and be the first.`}</div>`;
    return;
  }

  $("lb-body").innerHTML = `
    <table class="lb">
      <thead><tr>
        <th>#</th><th>Player</th>
        <th class="num">${mode === "call" ? "Points" : "Best"}</th>
        ${mode === "call" ? `<th class="num hide-sm">Revenue closed</th><th class="num hide-sm">Wins</th>` : ""}
        <th class="num hide-sm">${mode === "call" ? "Calls" : "Plays"}</th>
      </tr></thead>
      <tbody>
        ${rows.map((r) => `
          <tr class="${r.is_me ? "me" : ""}">
            <td class="place p${r.place}">${r.place}</td>
            <td><a class="player" href="#/u/${encodeURIComponent(r.username)}">${avatar(r.display_name, r.color, "sm")}
              <span>${esc(r.display_name)}${r.is_me ? " (you)" : ""}<small>@${esc(r.username)} · ${esc(r.rank)}</small></span></a></td>
            <td class="num pixel" style="font-size:13px">${fmt(r.score)}</td>
            ${mode === "call" ? `<td class="num hide-sm good">${money(r.revenue)}</td><td class="num hide-sm">${r.wins}</td>` : ""}
            <td class="num hide-sm">${r.plays}</td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}
