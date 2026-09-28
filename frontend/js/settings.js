// account settings, forgot/reset password, and email verification

async function renderSettings() {
  const s = await api("/api/account/settings");
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [s.timezone];
  app.innerHTML = `
    <section class="settings">
      <a class="back" href="#/profile">← Profile</a>
      <h1>Settings</h1>

      <div class="card">
        <h3>Email</h3>
        <p style="margin-top:0">${esc(s.email)} ${s.email_verified ? `<span class="good">✓ verified</span>` : `<span class="warn">not verified yet</span>`}</p>
        ${s.email_verified ? "" : `<button class="btn ghost small" id="verify-send">Send verification email again</button>
          ${s.email_sending ? "" : `<p class="tip">Email isn't set up on this server yet, so the link prints in the Terminal window running Callcade.</p>`}`}
      </div>

      <form class="card" id="pw-form">
        <h3>Change password</h3>
        <label class="field">Current password<input id="pw-cur" type="password" autocomplete="current-password" required></label>
        <label class="field">New password<input id="pw-new" type="password" autocomplete="new-password" placeholder="At least 8 characters" required></label>
        <div class="form-error" id="pw-err"></div>
        <button class="btn primary" type="submit">Change password</button>
      </form>

      <div class="card">
        <h3>Timezone</h3>
        <p class="muted" style="margin-top:0">Your daily limits and streaks reset at midnight here.</p>
        <div class="row">
          <select id="tz">${zones.map((z) => `<option ${z === s.timezone ? "selected" : ""}>${esc(z)}</option>`).join("")}</select>
          <button class="btn ghost" id="tz-save" style="flex:0">Save</button>
        </div>
      </div>

      <div class="card">
        <h3>Sound effects</h3>
        <label class="check"><input type="checkbox" id="sfx-on" ${sfxOn ? "checked" : ""}> Arcade sounds on</label>
      </div>

      <div class="card">
        <h3>Sessions</h3>
        <p class="muted" style="margin-top:0">Signed in on a computer you don't use anymore? This logs you out everywhere, including here.</p>
        <button class="btn ghost" id="logout-all">Log out everywhere</button>
      </div>

      <form class="card danger-zone" id="del-form">
        <h3 class="bad">Delete account</h3>
        <p class="muted" style="margin-top:0">This deletes your account, scores, and history for good. It can't be undone.</p>
        <label class="field">Type your password to confirm<input id="del-pw" type="password" required></label>
        <div class="form-error" id="del-err"></div>
        <button class="btn danger" type="submit">Delete my account</button>
      </form>
    </section>`;

  if ($("verify-send")) {
    $("verify-send").onclick = async () => {
      try {
        await api("/api/account/verify/send", {});
        toast("Verification email sent.");
      } catch (err) {
        toast(err.message);
      }
    };
  }
  $("pw-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/account/password", { current: $("pw-cur").value, new: $("pw-new").value });
      $("pw-form").reset();
      $("pw-err").textContent = "";
      toast("Password changed. Other devices were logged out.");
    } catch (err) {
      $("pw-err").textContent = err.message;
    }
  };
  $("tz-save").onclick = async () => {
    try {
      await api("/api/account/timezone", { timezone: $("tz").value });
      await refreshCategories();
      toast("Timezone saved.");
    } catch (err) {
      toast(err.message);
    }
  };
  $("sfx-on").onchange = (e) => {
    setSfx(e.target.checked);
    if (e.target.checked) sfx.coin();
  };
  $("logout-all").onclick = async () => {
    await api("/api/account/logout-everywhere", {});
    state.user = null;
    await refreshCategories();
    renderAccount();
    toast("Logged out everywhere.");
    go("#/");
  };
  $("del-form").onsubmit = async (e) => {
    e.preventDefault();
    if (!confirmDelete()) return;
    try {
      await api("/api/account/delete", { password: $("del-pw").value });
      state.user = null;
      await refreshCategories();
      renderAccount();
      toast("Your account was deleted.");
      go("#/");
    } catch (err) {
      $("del-err").textContent = err.message;
    }
  };
}

function confirmDelete() {
  // a second click on the button confirms, instead of a popup
  const btn = document.querySelector("#del-form .btn");
  if (btn.dataset.sure) return true;
  btn.dataset.sure = "1";
  btn.textContent = "Click again to delete forever";
  return false;
}

function renderForgot() {
  app.innerHTML = `
    <section class="auth">
      <h1>Forgot your password?</h1>
      <p>Enter your email and we'll send you a link to reset it.</p>
      <form class="card" id="f-form">
        <label class="field">Email<input id="f-email" type="email" required></label>
        <button class="btn primary" type="submit">Send reset link</button>
      </form>
      <div class="switch"><a href="#/login">Back to log in</a></div>
    </section>`;
  $("f-email").focus();
  $("f-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/account/forgot", { email: $("f-email").value });
      $("f-form").innerHTML = `<p style="margin:0">If there's an account with that email, a reset link is on its way. It works for 1 hour.
        ${state.config.email_sending ? "" : `<br><br><span class="muted">(Email isn't set up on this server, so the link prints in the Terminal running Callcade.)</span>`}</p>`;
    } catch (err) {
      toast(err.message);
    }
  };
}

function renderReset(params) {
  const token = params.get("token") || "";
  app.innerHTML = `
    <section class="auth">
      <h1>Pick a new password</h1>
      <p>You'll be logged in right after.</p>
      <form class="card" id="r-form">
        <label class="field">New password<input id="r-pw" type="password" autocomplete="new-password" placeholder="At least 8 characters" required></label>
        <label class="field">Confirm<input id="r-pw2" type="password" autocomplete="new-password" required></label>
        <div class="form-error" id="r-err"></div>
        <button class="btn primary" type="submit">Save password</button>
      </form>
    </section>`;
  $("r-form").onsubmit = async (e) => {
    e.preventDefault();
    if ($("r-pw").value !== $("r-pw2").value) {
      $("r-err").textContent = "Passwords don't match.";
      return;
    }
    try {
      state.user = await api("/api/account/reset", { token, password: $("r-pw").value });
      await afterAuth("Password updated. You're logged in.");
    } catch (err) {
      $("r-err").textContent = err.message;
    }
  };
}

async function renderVerify(params) {
  app.innerHTML = `<div class="empty">Verifying…</div>`;
  try {
    await api("/api/account/verify", { token: params.get("token") || "" });
    if (state.user) state.user = await api("/api/auth/me");
    sfx.coin();
    app.innerHTML = `<section class="auth"><h1>✓ Email verified</h1><p>You're all set and your scores count on the leaderboard.</p>
      <a class="btn primary" href="#/play">Go to the arcade</a></section>`;
  } catch (err) {
    app.innerHTML = `<section class="auth"><h1>Hmm, that didn't work</h1><p>${esc(err.message)}</p>
      <a class="btn ghost" href="#/settings">Go to settings</a></section>`;
  }
}
