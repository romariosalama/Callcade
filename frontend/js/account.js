// sign up, log in, log out, and the account area in the top bar

function renderAccount() {
  const box = $("account");
  const pill = state.config.ai
    ? `<span id="mode-pill" class="pill live" title="Buyers are played by AI">AI buyers on</span>`
    : `<span id="mode-pill" class="pill" title="AI isn't connected, buyers are a simple practice bot">Practice bot (no AI)</span>`;
  if (state.user) {
    box.innerHTML = `
      ${pill}
      ${state.user.is_admin ? `<a class="btn ghost small" href="#/admin">Admin</a>` : ""}
      <a class="me-chip" href="#/profile">${avatar(state.user.display_name, state.user.color, "sm")}
        <span>${esc(state.user.display_name)}<small>@${esc(state.user.username)}</small></span></a>`;
  } else {
    box.innerHTML = `
      ${pill}
      <a class="btn ghost small" href="#/login">Log in</a>
      <a class="btn primary small" href="#/signup">Sign up</a>`;
  }
}

function renderLogin() {
  if (state.user) return go("#/profile");
  app.innerHTML = `
    <section class="auth">
      <h1>Welcome back</h1>
      <p>Log in to keep climbing the leaderboard.</p>
      <form class="card" id="login-form">
        <label class="field">Username or email<input id="l-login" autocomplete="username" required></label>
        <label class="field">Password<input id="l-pass" type="password" autocomplete="current-password" required></label>
        <p style="margin:-6px 0 12px;font-size:13px"><a href="#/forgot">Forgot your password?</a></p>
        <div class="form-error" id="l-err"></div>
        <button class="btn primary" type="submit">Log in</button>
      </form>
      <div class="switch">New here? <a href="#/signup">Make an account</a></div>
    </section>`;
  $("l-login").focus();
  $("login-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      state.user = await api("/api/auth/login", { login: $("l-login").value, password: $("l-pass").value });
      await afterAuth("Welcome back, " + state.user.display_name + "!");
    } catch (err) {
      $("l-err").textContent = err.message;
    }
  };
}

function renderSignup() {
  if (state.user) return go("#/profile");
  app.innerHTML = `
    <section class="auth">
      <h1>Make your account</h1>
      <p>Save your progress, unlock levels, and get your name on the leaderboard.</p>
      <form class="card" id="signup-form">
        <label class="field">Username<input id="s-user" autocomplete="username" placeholder="3-20 letters, numbers, _" required></label>
        <label class="field">Display name <span class="muted">(optional)</span><input id="s-name" maxlength="30" placeholder="What people see on the leaderboard"></label>
        <label class="field">Email<input id="s-email" type="email" autocomplete="email" required></label>
        <label class="field">Your free industry <span class="muted">(3 free levels, Pro unlocks the rest)</span>
          <select id="s-industry" style="margin-top:6px">${state.categories.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select></label>
        <label class="field">Password<input id="s-pass" type="password" autocomplete="new-password" placeholder="At least 8 characters" required></label>
        <label class="field">Confirm password<input id="s-pass2" type="password" autocomplete="new-password" required></label>
        <div class="form-error" id="s-err"></div>
        <button class="btn primary" type="submit">Create account</button>
      </form>
      <div class="switch">Already have one? <a href="#/login">Log in</a></div>
    </section>`;
  $("s-user").focus();
  $("signup-form").onsubmit = async (e) => {
    e.preventDefault();
    if ($("s-pass").value !== $("s-pass2").value) {
      $("s-err").textContent = "Passwords don't match.";
      return;
    }
    try {
      state.user = await api("/api/auth/signup", {
        username: $("s-user").value,
        display_name: $("s-name").value,
        email: $("s-email").value,
        free_category: $("s-industry").value,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        password: $("s-pass").value,
      });
      await afterAuth("Account created! Check your email to verify it.");
      sfx.coin();
    } catch (err) {
      $("s-err").textContent = err.message;
    }
  };
}

async function afterAuth(msg) {
  await refreshCategories();
  renderAccount();
  toast(msg);
  go("#/play");
}

async function logout() {
  await api("/api/auth/logout", {});
  state.user = null;
  await refreshCategories();
  renderAccount();
  toast("Logged out");
  go("#/");
}
