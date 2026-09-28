// admin page: see users, change plans, remove bad scores

async function renderAdmin() {
  if (!state.user || !state.user.is_admin) return go("#/play");
  const data = await api("/api/admin/overview");
  app.innerHTML = `
    <section class="hero" style="padding-bottom:10px"><h1>Callcade admin</h1></section>
    <div class="card" style="margin-bottom:16px">
      <h3>AI usage since the server started</h3>
      <p class="muted" style="margin-top:0">Mode: <b>${esc(data.ai.mode)}</b>${data.ai.models.length ? ` · backup order: ${data.ai.models.map(esc).join(" → ")}` : ""}</p>
      <table class="admin-table">
        <tr><th>Model</th><th>Replies</th><th>Times it hit the limit</th><th>Status</th></tr>
        ${data.ai.models.map((m) => `<tr><td>${esc(m)}</td><td>${data.ai.replies[m] || 0}</td><td>${data.ai.limited[m] || 0}</td>
          <td>${data.ai.cooling_down.includes(m) ? '<span class="warn">maxed out, cooling down</span>' : '<span class="good">ready</span>'}</td></tr>`).join("")}
      </table>
      <p class="muted">Replies that failed because every model was busy: <b class="${data.ai.failed ? "bad" : ""}">${data.ai.failed}</b></p>
      <p class="muted" style="margin-bottom:0">Voices (${esc(data.ai.voice.provider)}): ${data.ai.voice.groq + data.ai.voice.polly} spoken lines,
        <b class="${data.ai.voice.failed ? "warn" : ""}">${data.ai.voice.failed}</b> fell back to the browser voice
        ${data.ai.voice.last_error ? `<br><small>Last voice error: ${esc(data.ai.voice.last_error)}</small>` : ""}</p>
    </div>
    <div class="card" style="margin-bottom:16px;overflow-x:auto">
      <h3>Users (${data.users.length})</h3>
      <table class="admin-table">
        <tr><th>User</th><th>Email</th><th>Plan</th><th>Verified</th><th>Points</th><th>Plays</th><th>Joined</th></tr>
        ${data.users.map((u) => `<tr>
          <td><a href="#/u/${encodeURIComponent(u.username)}">${esc(u.username)}</a>${u.admin ? " (admin)" : ""}</td>
          <td>${esc(u.email)}</td>
          <td><select data-user="${u.id}">${["free", "pro"].map((p) => `<option ${p === u.plan ? "selected" : ""}>${p}</option>`).join("")}</select></td>
          <td>${u.verified ? "✓" : ""}</td><td>${fmt(u.points)}</td><td>${u.plays}</td><td class="muted">${timeAgo(u.created_at)}</td></tr>`).join("")}
      </table>
    </div>
    <div class="card" style="overflow-x:auto">
      <h3>Latest 50 scores</h3>
      <table class="admin-table">
        <tr><th>User</th><th>Mode</th><th>Buyer</th><th>Outcome</th><th>Points</th><th>When</th><th></th></tr>
        ${data.results.map((r) => `<tr>
          <td>${esc(r.username)}</td><td>${esc(r.mode)}</td><td>${esc(r.character_id || "")}</td><td>${esc(r.outcome)}</td>
          <td>${fmt(r.points)}</td><td class="muted">${timeAgo(r.created_at)}</td>
          <td><button class="btn ghost small" data-result="${r.id}">Remove</button></td></tr>`).join("")}
      </table>
    </div>`;

  app.querySelectorAll("select[data-user]").forEach((sel) => {
    sel.onchange = async () => {
      await api(`/api/admin/users/${sel.dataset.user}/plan`, { plan: sel.value });
      toast("Plan updated.");
    };
  });
  app.querySelectorAll("[data-result]").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/admin/results/${b.dataset.result}`, null, "DELETE");
      b.closest("tr").remove();
      toast("Score removed.");
    };
  });
}
