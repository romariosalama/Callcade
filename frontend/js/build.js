// Build your own buyer: describe what you sell and your toughest customer, then call them

const BUILD_EXAMPLES = [
  {
    label: "Software to a CFO",
    sell: "Expense management software for mid-size companies, about $8 per employee a month",
    customer: "A CFO at a 300-person construction company who thinks software is a waste of money, still uses spreadsheets, and only talks numbers",
  },
  {
    label: "Gym membership",
    sell: "A $59 a month gym membership with personal training add-ons",
    customer: "Someone who signed up for three gyms before and never went, is embarrassed about it, and thinks every gym just wants their money",
  },
  {
    label: "Roofing, door to door",
    sell: "Roof inspections and replacements, most roofs cost $12,000 to $18,000",
    customer: "A retired homeowner who got scammed by a contractor before, doesn't open the door for strangers, and says the roof is fine",
    door: true,
  },
];

const TOUGHNESS = ["Easy", "Friendly", "Tough", "Hard", "Brutal"];

async function renderBuild() {
  const mine = state.user ? await api("/api/custom-buyers") : [];
  mine.forEach((c) => (customBuyers[c.id] = c));
  let tough = 3;
  let where = "phone";

  app.innerHTML = `
    <section class="build">
      <div class="build-head">
        <h1>Build your own buyer</h1>
        <p class="lede">Tell us what you sell and describe the customer who gives you the hardest time.
          We'll turn them into a buyer you can actually call.</p>
      </div>

      <form class="card build-form" id="build-form">
        <div class="examples"><span class="muted">Try one:</span>
          ${BUILD_EXAMPLES.map((e, i) => `<button type="button" class="chip" data-ex="${i}">${e.label}</button>`).join("")}
        </div>
        <label class="field">What do you sell?
          <textarea id="b-sell" rows="2" maxlength="600" required
            placeholder="Commercial cleaning for office buildings, about $2,000 a month"></textarea></label>
        <label class="field">Who's your toughest customer?
          <textarea id="b-cust" rows="3" maxlength="800" required
            placeholder="An office manager who already has a cleaning company, thinks they're all the same, and only cares about price"></textarea></label>
        <div class="build-row">
          <div>
            <div class="small-label">How tough?</div>
            <div class="mode-switch" id="b-tough">
              ${TOUGHNESS.map((t, i) => `<button type="button" data-v="${i + 1}" class="${i + 1 === tough ? "on" : ""}">${t}</button>`).join("")}
            </div>
          </div>
          <div>
            <div class="small-label">Where?</div>
            <div class="mode-switch" id="b-where">
              <button type="button" data-v="phone" class="on">Phone call</button>
              <button type="button" data-v="door">Their door</button>
            </div>
          </div>
        </div>
        <div class="form-error" id="b-err"></div>
        <button class="btn primary big" id="b-go" type="submit">Build my buyer</button>
        ${state.config.ai ? "" : `<p class="tip">AI isn't connected, so your buyer is built from a simple template. Turn on AI for a much more real one.</p>`}
      </form>

      <div id="b-result"></div>

      ${mine.length ? `
        <h2 class="section-h">Your buyers</h2>
        <div class="my-buyers">${mine.map(buyerRow).join("")}</div>` : ""}
    </section>`;

  const pick = (group, value) => {
    group.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.v === String(value)));
  };
  $("b-tough").onclick = (e) => {
    if (!e.target.dataset.v) return;
    tough = Number(e.target.dataset.v);
    pick($("b-tough"), tough);
  };
  $("b-where").onclick = (e) => {
    if (!e.target.dataset.v) return;
    where = e.target.dataset.v;
    pick($("b-where"), where);
  };
  app.querySelectorAll("[data-ex]").forEach((b) => {
    b.onclick = () => {
      const ex = BUILD_EXAMPLES[b.dataset.ex];
      $("b-sell").value = ex.sell;
      $("b-cust").value = ex.customer;
      where = ex.door ? "door" : "phone";
      pick($("b-where"), where);
    };
  });
  app.querySelectorAll("[data-del]").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/custom-buyers/${b.dataset.del}`, null, "DELETE");
      b.closest(".buyer-row").remove();
    };
  });

  $("build-form").onsubmit = async (e) => {
    e.preventDefault();
    $("b-err").textContent = "";
    $("b-go").disabled = true;
    $("b-go").textContent = "Building your buyer…";
    try {
      const c = await api("/api/custom-buyers", {
        sell: $("b-sell").value, customer: $("b-cust").value, difficulty: tough, call_type: where,
      });
      customBuyers[c.id] = c;
      sfx.coin();
      showBuiltBuyer(c);
    } catch (err) {
      $("b-err").textContent = err.message;
    }
    $("b-go").disabled = false;
    $("b-go").textContent = "Build my buyer";
  };
}

function buyerRow(c) {
  return `
    <div class="buyer-row">
      ${buyerAvatar(c.nickname, c.color, "sm")}
      <div class="grow"><b>${esc(c.nickname)}</b><small>${esc(c.buyer.title)} · ${esc(TOUGHNESS[c.stars - 1])}</small></div>
      <a class="btn primary small" href="#/build/${c.id}">Call</a>
      ${state.user ? `<button class="btn ghost small" data-del="${c.id}" title="Delete">✕</button>` : ""}
    </div>`;
}

function showBuiltBuyer(c) {
  $("b-result").innerHTML = `
    <section class="card built" style="--c1:${c.color[0]};--c2:${c.color[1]}">
      ${buyerAvatar(c.nickname, c.color)}
      <div class="grow">
        <div class="muted small-label">Meet your buyer</div>
        <h2>${esc(c.nickname)}</h2>
        <div class="muted">${esc(c.buyer.name)} · ${esc(c.buyer.title)}${c.buyer.company ? ", " + esc(c.buyer.company) : ""}</div>
        <p>${esc(c.bio || c.tagline)}</p>
        <p class="muted" style="font-size:14px"><b style="color:var(--text)">${esc(c.traits)}.</b> They have 3 hidden problems and 3 objections waiting for you.</p>
        <div class="actions">
          <a class="btn go" href="#/build/${c.id}">${c.call_type === "door" ? "Go knock" : "Call " + esc(firstName(c))}</a>
          <button class="btn ghost" id="b-share">Copy link</button>
        </div>
      </div>
    </section>`;
  $("b-share").onclick = () => {
    const link = location.origin + "/#/build/" + c.id;
    navigator.clipboard.writeText(link).then(() => toast("Link copied. Anyone with it can call this buyer."));
  };
  $("b-result").scrollIntoView({ behavior: "smooth", block: "center" });
}

async function renderCustomPreCall(id) {
  let c = customBuyers[id];
  if (!c) {
    c = await api(`/api/custom-buyers/${encodeURIComponent(id)}`);
    customBuyers[c.id] = c;
  }
  preCallScreen(c, {
    start: () => api("/api/calls", { character_id: c.id }),
    back: ["#/build", "Build a buyer"],
  });
}
