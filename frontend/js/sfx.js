// arcade sound effects (made with the Web Audio API, no sound files) and confetti

let sfxOn = localStorage.getItem("callcade.sfx") !== "off";

function setSfx(on) {
  sfxOn = on;
  localStorage.setItem("callcade.sfx", on ? "on" : "off");
}

function beep(freq, start, length, type = "square", volume = 0.05) {
  if (!sfxOn) return;
  const ac = ctx();
  const osc = ac.createOscillator();
  const gain = ac.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, ac.currentTime + start);
  gain.gain.setValueAtTime(volume, ac.currentTime + start);
  gain.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + start + length);
  osc.connect(gain).connect(ac.destination);
  osc.start(ac.currentTime + start);
  osc.stop(ac.currentTime + start + length + 0.02);
}

const sfx = {
  click: () => beep(660, 0, 0.05),
  coin: () => { beep(988, 0, 0.08); beep(1319, 0.08, 0.25); },
  combo: (n) => beep(440 + 80 * Math.min(n, 8), 0, 0.12),
  good: () => { beep(523, 0, 0.1); beep(784, 0.1, 0.18); },
  bad: () => { beep(220, 0, 0.15, "sawtooth"); beep(160, 0.15, 0.25, "sawtooth"); },
  win: () => [523, 659, 784, 1047].forEach((f, i) => beep(f, i * 0.12, 0.2)),
  lose: () => [392, 330, 262, 196].forEach((f, i) => beep(f, i * 0.15, 0.22, "triangle")),
  levelUp: () => [523, 659, 784, 1047, 1319].forEach((f, i) => beep(f, i * 0.09, 0.16, "square", 0.06)),
};

function confetti(ms = 2500) {
  const canvas = document.createElement("canvas");
  canvas.id = "confetti";
  document.body.appendChild(canvas);
  const c = canvas.getContext("2d");
  canvas.width = innerWidth;
  canvas.height = innerHeight;
  const colors = ["#ff6b35", "#f472b6", "#fbbf24", "#34d399", "#22d3ee", "#f87171"];
  const bits = [];
  for (let i = 0; i < 160; i++) {
    bits.push({
      x: Math.random() * canvas.width,
      y: -20 - Math.random() * canvas.height * 0.5,
      w: 6 + Math.random() * 6,
      h: 8 + Math.random() * 8,
      vy: 2 + Math.random() * 4,
      vx: -2 + Math.random() * 4,
      spin: Math.random() * 6,
      color: colors[i % colors.length],
    });
  }
  const start = Date.now();
  function frame() {
    c.clearRect(0, 0, canvas.width, canvas.height);
    for (const b of bits) {
      b.x += b.vx;
      b.y += b.vy;
      b.spin += 0.1;
      c.save();
      c.translate(b.x, b.y);
      c.rotate(b.spin);
      c.fillStyle = b.color;
      c.fillRect(-b.w / 2, -b.h / 2, b.w, b.h);
      c.restore();
    }
    if (Date.now() - start < ms) requestAnimationFrame(frame);
    else canvas.remove();
  }
  frame();
}
