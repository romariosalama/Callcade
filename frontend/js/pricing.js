// pricing page

function renderPricing() {
  const plan = state.plan ? state.plan.plan : "guest";
  const price = state.config.pro_price.toFixed(2);
  const catCount = state.categories.length;
  const buyerCount = state.categories.reduce((n, c) => n + c.characters.length, 0);

  const check = (on, text) => `<li class="${on ? "" : "no"}">${on ? "✓" : "✕"} ${text}</li>`;

  app.innerHTML = `
    <section class="hero" style="text-align:center;margin:0 auto;padding-bottom:26px">
      <h1>Practice free. Go Pro to play everything.</h1>
      <p class="lede">Every level still has to be beaten to unlock the next one. Pro just opens up all of them.</p>
    </section>

    <section class="plans">
      <div class="plan">
        <div class="plan-name">Guest</div>
        <div class="price">$0<small> no account</small></div>
        <p class="muted">Try a call before you sign up.</p>
        <ul>
          ${check(true, "Level 1 of every industry")}
          ${check(false, "Scores and progress saved")}
          ${check(false, "Leaderboard")}
          ${check(false, "Objection Gauntlet")}
        </ul>
        <a class="btn ghost" href="#/">${plan === "guest" ? "Keep playing" : "Play"}</a>
      </div>

      <div class="plan">
        <div class="plan-name">Free</div>
        <div class="price">$0<small> forever</small></div>
        <p class="muted">For getting your reps in.</p>
        <ul>
          ${check(true, "<b>3 levels</b> of one industry you pick")}
          ${check(true, "10 calls a day")}
          ${check(true, "3 Objection Gauntlet runs a day")}
          ${check(true, "Scores, ranks, badges, and profile")}
          ${check(true, "Leaderboard")}
          ${check(false, "Other industries and the bosses")}
        </ul>
        ${plan === "guest" ? `<a class="btn primary" href="#/signup">Sign up free</a>`
          : `<button class="btn ghost" disabled>${plan === "free" ? "Your plan" : "Included in Pro"}</button>`}
      </div>

      <div class="plan pro">
        <div class="tag-best">Most popular</div>
        <div class="plan-name">Pro</div>
        <div class="price">$${price}<small> / month</small></div>
        <p class="muted">For people who want to get really good.</p>
        <ul>
          ${check(true, `<b>All ${buyerCount} buyers</b> in all ${catCount} industries`)}
          ${check(true, "Every final boss, including Victor")}
          ${check(true, "Unlimited calls")}
          ${check(true, "Unlimited Objection Gauntlet runs")}
          ${check(true, "Everything in Free")}
          ${check(true, "Cancel anytime")}
        </ul>
        ${plan === "pro" ? `<button class="btn go" disabled>You're Pro ✓</button>`
          : `<button class="btn primary" id="go-pro">Go Pro for $${price}/mo</button>`}
      </div>
    </section>

    <section class="faq">
      <h2>Questions</h2>
      <details><summary>Do I have to beat levels in order?</summary><p>Yes, on every plan. Beat a buyer (book the meeting or close the deal) to unlock the next one. Pro doesn't skip levels, it just removes the limits.</p></details>
      <details><summary>Can I change my free industry?</summary><p>Yes, once every 30 days from your profile. Your progress in the old one stays saved.</p></details>
      <details><summary>What counts as a call?</summary><p>Every time you dial a buyer. Free accounts get 10 a day and it resets at midnight in your timezone.</p></details>
    </section>`;

  if ($("go-pro")) {
    $("go-pro").onclick = async () => {
      if (!state.user) return go("#/signup");
      try {
        await api("/api/plan/upgrade", {});
      } catch (err) {
        toast(err.message);
      }
    };
  }
}
