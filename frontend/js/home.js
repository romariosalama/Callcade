// landing page, the arcade floor (home), and the level select for each industry

// ---------------- landing page (people who aren't logged in) ----------------

function renderLanding() {
  const buyerCount = state.categories.reduce((n, c) => n + c.characters.length, 0);
  app.innerHTML = `
    <section class="landing">
      <h1 class="logo pixel">CALLCADE</h1>
      <p class="sub">Call AI buyers out loud. They have budgets, bad days, hidden problems, and they <b>will</b> hang up on you.
        Handle the objections, book the meeting, and climb the leaderboard.</p>
      <div class="ctas">
        <a class="btn go big" href="#/play">Play free, no sign up</a>
        <a class="btn ghost big" href="#/signup">Make an account</a>
      </div>
    </section>
    <section class="theater" id="theater">
      <div class="screen-wrap">
        <video id="trailer" poster="/static/media/trailer-poster.jpg" autoplay muted loop playsinline preload="auto">
          <source src="/static/media/callcade-trailer-web.mp4" type="video/mp4"><source src="/static/media/callcade-trailer-web.webm" type="video/webm"></video>
        <button class="sound-pill" id="watch">Turn sound on</button>
        <div class="screen-controls" id="controls" hidden>
          <button id="mute">Mute</button>
          <button id="replay">Replay</button>
        </div>
      </div>
    </section>

    <section class="try card" id="try">
      <div class="try-head">
        <div class="avatar" style="background:#b45309;color:#fff">VH</div>
        <div><div class="pixel tiny gold">TRY ONE LINE</div><b>Victor, CEO (tech final boss)</b></div>
      </div>
      <p class="try-line">“We already have a vendor for that, and honestly, you're more expensive.”</p>
      <form id="try-form" class="try-form">
        <input id="try-text" maxlength="400" placeholder="What do you say back? (you get one shot)" autocomplete="off">
        <button class="btn primary" type="submit">Answer</button>
      </form>
      <div id="try-out"></div>
    </section>

    <section class="inside">
      <h2>What's in it</h2>
      <dl>
        <div class="row"><dt>Calls that feel real</dt><dd>It rings, they pick up with "Hello?", and you talk out loud. Every buyer has their own voice, mood and reasons to say no.</dd></div>
        <div class="row"><dt>${buyerCount} buyers, 5 industries</dt><dd>Tech, real estate, life insurance, car sales and door-to-door solar. 8 levels each, and the last one is a boss.</dd></div>
        <div class="row"><dt>Your own buyer</dt><dd>Describe the customer who keeps beating you, then call them before you call them for real.</dd></div>
        <div class="row"><dt>Coaching after the call</dt><dd>Where you won or lost them, what they were hiding, and what you could have said instead.</dd></div>
        <div class="row"><dt>Quick game modes</dt><dd>Objection Gauntlet, Spot the Mistake and Clutch Call when you only have five minutes.</dd></div>
      </dl>
      <p style="margin-top:24px"><a href="#/play">Go to the arcade →</a></p>
    </section>`;

  setupTheater();
  $("try-form").onsubmit = async (e) => {
    e.preventDefault();
    const text = $("try-text").value.trim();
    if (!text) return;
    $("try-form").querySelector("button").disabled = true;
    try {
      const r = await api("/api/try", { text });
      const color = r.score >= 7 ? "good" : r.score >= 5 ? "warn" : "bad";
      if (r.score >= 7) sfx.good(); else sfx.bad();
      $("try-out").innerHTML = `
        <div class="try-result">
          <div class="sc ${color} pixel">${r.score}/10</div>
          <div><b>${esc(r.verdict)}</b> ${r.good ? `<span class="good">${esc(r.good)}</span>` : ""}
            <p>${esc(r.missed || "")}</p>
            <div class="model"><b>How a top rep would say it</b>${esc(r.better)}</div>
            <a class="btn go" href="#/play">That was one line. Try the full call →</a>
          </div>
        </div>`;
    } catch (err) {
      toast(err.message);
    }
    $("try-form").querySelector("button").disabled = false;
  };
}

// the trailer on the landing page. starts muted (browsers block autoplay with sound)
function setupTheater() {
  const v = $("trailer");
  const withSound = () => {
    v.currentTime = 0;
    v.muted = false;
    v.play();
    $("watch").hidden = true;
    $("controls").hidden = false;
    $("mute").textContent = "Mute";
  };
  $("watch").onclick = withSound;
  $("replay").onclick = withSound;
  $("mute").onclick = () => {
    v.muted = !v.muted;
    $("mute").textContent = v.muted ? "Unmute" : "Mute";
  };
}

// ---------------- home (the arcade floor) ----------------

// the next buyer you should call: first unlocked one you haven't beaten yet
function nextBuyer(profile) {
  const cats = [...state.categories];
  const lastCall = profile && profile.stats.recent.find((r) => r.mode === "call");
  const prefer = state.plan.plan === "free" ? state.plan.free_category : lastCall ? lastCall.category : "tech";
  cats.sort((a, b) => (b.id === prefer) - (a.id === prefer));
  for (const cat of cats) {
    const c = cat.characters.find((x) => x.unlocked && !x.beaten);
    if (c) return c;
  }
  const home = cats[0];
  return home.characters.filter((x) => x.unlocked).pop() || home.characters[0];
}

const GAME_MODES = [
  { href: "#/gauntlet", cls: "m-gauntlet", title: "Objection Gauntlet", line: "10 objections. A shrinking clock. 3 lives.", tag: "Speed",
    screen: `<div class="g-ring"><span>15</span></div><div class="g-hearts hp">♥♥<span class="gone">♥</span></div>` },
  { href: "#/build", cls: "m-build", title: "Build a Buyer", line: "Describe your toughest customer, then call them.", tag: "Custom",
    screen: `<div class="mini-card"><b>?</b><i></i><i class="short"></i></div>` },
  { href: "#/mistake", cls: "m-mistake", title: "Spot the Mistake", line: "Review real calls. Find every mistake the rep made.", tag: "Hard",
    screen: `<div class="mini-chat"><i></i><i class="rep"></i><i class="rep bad"></i><i></i></div>` },
  { href: "#/clutch", cls: "m-clutch", title: "Clutch Call", line: "The deal is slipping. Pick the line that saves it.", tag: "Pressure",
    screen: `<div class="mini-opts"><i></i><i class="win"></i><i></i><i></i></div><div class="mini-meter"><b></b></div>` },
];

function untilMidnight() {
  const now = new Date();
  const end = new Date(now);
  end.setHours(24, 0, 0, 0);
  const mins = Math.max(0, Math.round((end - now) / 60000));
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

// 8 little pips per industry: beaten, open, locked
function levelPips(cat) {
  return `<div class="pips">${cat.characters.map((c) =>
    `<span class="${c.beaten ? "won" : c.unlocked ? "open" : ""} ${c.boss ? "boss" : ""}" title="${esc(c.nickname)}"></span>`).join("")}</div>`;
}

async function renderHome() {
  const [daily, profile, board] = await Promise.all([
    api("/api/daily"),
    state.user ? api("/api/profile/me") : Promise.resolve(null),
    api("/api/leaderboard?mode=call&period=week").catch(() => []),
  ]);
  const u = state.user;
  const s = profile ? profile.stats : null;

  const hud = u ? `
      <section class="hud-bar">
        <div class="p1">
          ${avatar(u.display_name, u.color)}
          <div>
            <div class="pixel tiny">PLAYER 1</div>
            <b>${esc(u.display_name)}</b>
          </div>
        </div>
        <div class="xp">
          <div class="xp-top"><span class="rank-name">${esc(s.rank.name)}</span>
            <span class="muted">${s.rank.next ? `${fmt(s.rank.next_at - s.points)} pts to ${esc(s.rank.next)}` : "Max rank"}</span></div>
          <div class="xp-track"><div class="xp-fill" style="width:${s.rank.progress}%"></div></div>
        </div>
        <div class="counters">
          <div><span class="pixel ${s.streak ? "fire" : ""}">${s.streak}</span><small>day streak</small></div>
          <div><span class="pixel">${fmt(s.points)}</span><small>points</small></div>
          <div><span class="pixel money">${money(s.revenue)}</span><small>closed</small></div>
        </div>
      </section>`
    : `
      <section class="hud-bar guest">
        <div>
          <div class="pixel tiny">INSERT COIN</div>
          <b>You're playing as a guest</b>
          <p>Level 1 of every industry is open. Sign up free to save progress, keep a streak, and hit the leaderboard.</p>
        </div>
        <a class="btn primary" href="#/signup">Sign up free</a>
      </section>`;

  const c = nextBuyer(profile);
  const cat = findCategory(c.category);
  const door = cat.call_type === "door";
  const upNext = `
    <section class="stage-card">
      <div class="stage-top">
        <span class="pixel tiny">${c.boss ? "FINAL BOSS" : `STAGE ${c.level}/${cat.characters.length}`}</span>
        <span class="muted"><span class="cat-dot" style="--c:${cat.color[0]}"></span>${esc(cat.name)}</span>
      </div>
      <div class="stage-body">
        <div class="portrait">${buyerAvatar(c.nickname, c.color)}</div>
        <div>
          <div class="pixel tiny accent">UP NEXT</div>
          <h2>${esc(c.nickname)}</h2>
          <div class="stage-meta">${stars(c.stars)} <span class="muted">${esc(c.traits)}</span></div>
          <p>${esc(c.bio || c.tagline)}</p>
          <div class="actions">
            <a class="btn go" href="#/call/${c.id}">${door ? "Knock on the door" : c.inbound ? "Take the call" : "Call " + esc(firstName(c))}</a>
            <a class="btn ghost" href="#/category/${cat.id}">Level select</a>
          </div>
        </div>
      </div>
    </section>`;

  const d = daily.character;
  const done = daily.played;
  const dailyCard = `
    <a class="daily-card" href="#/daily">
      <div class="pixel tiny gold">DAILY CHALLENGE</div>
      <div class="d-face">
        ${buyerAvatar(d.nickname, d.color)}
        <div><h3>${esc(d.nickname)}</h3><div class="muted">${esc(daily.category)}</div></div>
      </div>
      <p>${done ? `<span class="good">✓ You scored ${fmt(done.points)} today.</span>` : "Same buyer for everyone. One shot. Top score wins the day."}</p>
      <div class="d-foot">
        <span class="btn ${done ? "ghost" : "gold"} small">${done ? "See today's board" : "Play today's"}</span>
        <span class="muted small-note">new buyer in ${untilMidnight()}</span>
      </div>
    </a>`;

  const modes = GAME_MODES.map((m) => `
    <a class="mode ${m.cls}" href="${m.href}">
      <div class="screen">${m.screen}</div>
      <div class="mode-text">
        <h3>${m.title}${m.tag ? `<span class="mode-tag">${m.tag}</span>` : ""}</h3>
        <p>${m.line}</p>
      </div>
      <span class="press pixel">PRESS START ▸</span>
    </a>`).join("");

  const worlds = state.categories.map((w) => {
    const beaten = w.characters.filter((x) => x.beaten).length;
    const boss = w.characters.find((x) => x.boss);
    let tag = "";
    if (state.plan.plan === "free") tag = w.id === state.plan.free_category ? `<span class="w-tag free">Free</span>` : `<span class="w-tag pro">Pro</span>`;
    return `
      <a class="world" href="#/category/${w.id}" style="--c1:${w.color[0]};--c2:${w.color[1]}">
        <div class="w-top"><span class="cat-dot" style="--c:${w.color[0]}"></span>${tag}</div>
        <h3>${esc(w.name)}</h3>
        <div class="muted w-boss">Boss: ${esc(boss.nickname)}</div>
        ${levelPips(w)}
        <div class="muted w-count">${beaten}/${w.characters.length} beaten</div>
      </a>`;
  }).join("");

  const top = board.slice(0, 3);
  const scores = `
    <section class="hiscores">
      <div class="hs-head"><span class="pixel">HIGH SCORES</span><span class="muted">this week</span></div>
      ${top.length ? top.map((r) => `
        <a class="hs-row ${r.is_me ? "me" : ""}" href="#/u/${encodeURIComponent(r.username)}">
          <span class="pixel pos">${r.place}</span>
          <span class="nm">${esc(r.display_name)}</span>
          <span class="pixel pts">${fmt(r.score)}</span>
        </a>`).join("") : `<p class="muted hs-empty">No scores yet this week. First call takes the top spot.</p>`}
      <a class="hs-more" href="#/leaderboard">Full leaderboard →</a>
    </section>`;

  const tip = s && s.weak_spot
    ? `<p class="soft-tip"><b>Coach tip:</b> ${esc(s.weak_spot.tip)} <a href="${s.weak_spot.link}">Practice it →</a></p>` : "";
  const planLine = profile && profile.plan.plan === "free"
    ? `<p class="soft-tip center">Free plan: ${profile.plan.calls_left} of 10 calls left today · <a href="#/pricing">Go Pro</a> to unlock every industry</p>` : "";

  app.innerHTML = `
    <div class="arcade">
      ${hud}
      <section class="arcade-top">${upNext}<div class="side-col">${dailyCard}${scores}</div></section>
      ${tip}
      <div class="row-head"><h2>Game modes</h2></div>
      <section class="modes-grid">${modes}</section>
      <div class="row-head"><h2>Career</h2><span class="muted">Beat every level. Face the boss.</span></div>
      <section class="worlds">${worlds}</section>
      ${planLine}
    </div>`;
}

// ---------------- level select ----------------

// shown when someone tries to play a locked buyer
function lockMessage(c, cat) {
  if (c.lock === "signup") return "Sign up free to play";
  if (c.lock === "pro") return state.plan && state.plan.plan === "free" && c.category !== state.plan.free_category
    ? "Pro industry" : "Pro level. Go Pro to keep climbing";
  const prev = cat.characters.find((x) => x.level === c.level - 1);
  return "Beat " + (prev ? prev.nickname : "the last level") + " to unlock";
}

function renderCategory(id) {
  const cat = findCategory(id);
  if (!cat) return go("#/play");

  const levels = cat.characters.map((c) => `
      <button class="level ${c.unlocked ? "" : "locked"} ${c.boss ? "boss" : ""}" data-id="${c.id}" style="--c1:${c.color[0]}">
        <div class="lvl pixel"><span>${c.boss ? "FINAL BOSS" : "LEVEL " + c.level}</span>${c.beaten ? '<span class="done">✓ BEATEN</span>' : ""}</div>
        <div class="face">
          ${buyerAvatar(c.nickname, c.color)}
          <div><h3>${esc(c.nickname)}</h3>${stars(c.stars)}</div>
        </div>
        <div class="traits">${esc(c.traits)}</div>
        <div class="tag">"${esc(c.tagline)}"</div>
        ${c.bio ? `<div class="bio">${esc(c.bio)}</div>` : ""}
        <div class="foot"><span class="mult">×${c.multiplier} points</span>
          <span class="muted">${c.best ? "Best: " + fmt(c.best) : "Not played"}</span></div>
        <div class="lock ${c.lock}">${esc(lockMessage(c, cat))}</div>
      </button>`).join("");

  app.innerHTML = `
    <a class="back" href="#/play">← Arcade</a>
    <div class="cat-head" style="--c1:${cat.color[0]}">
      <div class="swatch-big"></div>
      <div><h1>${esc(cat.name)}</h1><p>You're ${esc(cat.you_are)}. ${esc(cat.blurb)}</p></div>
    </div>
    <section class="level-grid">${levels}</section>`;

  app.querySelectorAll(".level").forEach((el) => {
    el.addEventListener("click", () => {
      const c = findCharacter(el.dataset.id);
      sfx.click();
      if (c.unlocked) go("#/call/" + c.id);
      else if (c.lock === "signup") go("#/signup");
      else if (c.lock === "pro") go("#/pricing");
    });
  });
}
