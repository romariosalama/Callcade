// simple hash router: #/play, #/category/tech, #/call/easy-eddie, #/leaderboard, ...

async function route() {
  cleanupCall();
  cleanupGauntlet();
  cleanupMistake();
  cleanupClutch();
  stopSpeaking();
  window.scrollTo(0, 0);

  const [path, query] = location.hash.replace(/^#/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const params = new URLSearchParams(query || "");
  let page = parts[0] || "";

  // new visitors get the landing page, everyone else goes straight to the arcade
  if (page === "") page = state.user ? "play" : "landing";

  document.body.classList.toggle("in-call", page === "call");
  const navFor = { play: "play", category: "play", call: "play", results: "play", daily: "play",
    challenge: "play", gauntlet: "gauntlet", mistake: "play", build: "build", clutch: "play", leaderboard: "leaderboard", pricing: "pricing" };
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === navFor[page]));

  const pages = {
    landing: () => renderLanding(),
    play: () => renderHome(),
    category: () => renderCategory(parts[1]),
    call: () => renderPreCall(parts[1]),
    results: () => renderResults(),
    daily: () => renderDaily(),
    challenge: () => renderChallenge(parts[1]),
    gauntlet: () => renderGauntletMenu(),
    mistake: () => renderMistakeMenu(),
    clutch: () => renderClutchMenu(),
    leaderboard: () => renderLeaderboard(params),
    pricing: () => renderPricing(),
    profile: () => (state.user ? renderProfile() : go("#/login")),
    settings: () => (state.user ? renderSettings() : go("#/login")),
    u: () => renderProfile(decodeURIComponent(parts[1] || "")),
    login: () => renderLogin(),
    signup: () => renderSignup(),
    forgot: () => renderForgot(),
    reset: () => renderReset(params),
    verify: () => renderVerify(params),
    admin: () => renderAdmin(),
    build: () => (parts[1] ? renderCustomPreCall(parts[1]) : renderBuild()),
  };

  try {
    if (pages[page]) await pages[page]();
    else go("#/play");
  } catch (err) {
    console.error(err);
    app.innerHTML = `<div class="empty">Couldn't load this page: ${esc(err.message)}<br><br><a href="#/play">Back to the arcade</a></div>`;
  }
}

async function start() {
  try {
    const [config, user] = await Promise.all([api("/api/config"), api("/api/auth/me")]);
    state.config = config;
    state.user = user;
    await refreshCategories();
  } catch (err) {
    app.innerHTML = `<div class="empty">Can't reach the Callcade server. Is it running?<br>${esc(err.message)}</div>`;
    return;
  }
  renderAccount();
  window.addEventListener("hashchange", route);
  route();
}

start();
