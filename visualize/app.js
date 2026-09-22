(function () {
  const board = document.getElementById("board");
  const layer = board.getContext("2d");
  const lens = document.getElementById("lens");
  const lensLayer = lens.getContext("2d");
  const vacant = document.getElementById("vacant");
  const note = document.getElementById("note");
  const list = document.getElementById("list");
  const tones = document.getElementById("tones");
  const chips = document.getElementById("chips");
  const verdict = document.getElementById("verdict");
  const why = document.getElementById("why");
  const exam = document.getElementById("exam");

  const trendCopy = {
    KEEP: ["Keep the last lesson", "Fail rate or time-to-green improved after that playbook bullet."],
    REVERT: ["Revert the last lesson", "The new lesson set is worse. Drop that bullet via promote.md."],
    INSUFFICIENT_N: ["Not enough runs yet", "Need at least 3 scored runs on the current lesson set before KEEP or REVERT."],
    PROBE_CHANGED: ["Probe changed", "The exam command is not the same across runs, so they cannot be compared."],
  };

  const palette = ["#6cffc8", "#5ce1ff", "#c8ff5c", "#ff5ec8", "#ff9a4a", "#b48cff"];
  const hueOf = {};
  function hue(hash) {
    if (!hueOf[hash]) hueOf[hash] = palette[Object.keys(hueOf).length % palette.length];
    return hueOf[hash];
  }

  let runs = [];
  let tally = { verdict: "INSUFFICIENT_N", groups: [], probe: null };
  let shown = [];
  let bonds = [];
  let chosen = null;
  let over = null;
  let find = "";
  const outcomeOn = new Set();
  const verbOn = new Set();
  const hashOn = new Set();
  let panX = 0, panY = 0, zoom = 1;
  let hold = false, moved = false, lastX = 0, lastY = 0;
  let focusX = 0, focusY = 0;
  let needPaint = true;

  function allowed(row) {
    if (outcomeOn.size && !outcomeOn.has(row.pass ? "pass" : "fail")) return false;
    if (verbOn.size && !(row.actions || []).some((v) => verbOn.has(v))) return false;
    if (hashOn.size && !hashOn.has(row.learned_hash)) return false;
    if (find && !JSON.stringify(row).toLowerCase().includes(find)) return false;
    return true;
  }

  function place(items) {
    let s = 20261;
    const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
    const ordered = items.slice().sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
    const n = ordered.length;
    const rad = n > 80 ? 0.85 : n > 20 ? 1.4 : 2.6;
    const nodes = ordered.map((row, i) => {
      const th = rnd() * Math.PI * 2;
      const r = n <= 1 ? 0 : Math.sqrt(rnd()) * (6 + Math.sqrt(n) * 2.2);
      return { row, x: Math.cos(th) * r, y: Math.sin(th) * r, vx: 0, vy: 0, rad };
    });
    bonds = [];
    for (let i = 0; i < n - 1; i++) bonds.push([i, i + 1]);
    for (let t = 0; t < 12; t++) {
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y;
          const d2 = dx * dx + dy * dy || 0.04;
          if (d2 > 64) continue;
          const d = Math.sqrt(d2);
          const push = (4.2 - d) * 0.22;
          nodes[i].x += (dx / d) * push;
          nodes[i].y += (dy / d) * push;
          nodes[j].x -= (dx / d) * push;
          nodes[j].y -= (dy / d) * push;
        }
      }
      bonds.forEach(([i, j]) => {
        const a = nodes[i], b = nodes[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.hypot(dx, dy) || 1;
        const pull = (d - 7) * 0.04;
        a.x += (dx / d) * pull;
        a.y += (dy / d) * pull;
        b.x -= (dx / d) * pull;
        b.y -= (dy / d) * pull;
      });
      nodes.forEach((node) => {
        node.x *= 0.98;
        node.y *= 0.98;
      });
    }
    return nodes;
  }

  function mapPointer(cx, cy) {
    const box = board.getBoundingClientRect();
    return {
      x: (cx - box.left - box.width / 2 - panX) / zoom,
      y: (cy - box.top - box.height / 2 - panY) / zoom,
    };
  }

  function hitRun(x, y) {
    let best = null, lim = 22 / zoom;
    shown.forEach((n, i) => {
      const d = Math.hypot(n.x - x, n.y - y);
      if (d < lim) { lim = d; best = i; }
    });
    return best;
  }

  function warpNear(x, y, cx, cy, R) {
    const dx = x - cx, dy = y - cy;
    const r = Math.hypot(dx, dy);
    if (r < 0.0001) return { x, y, t: 0 };
    const t = r / R;
    if (t > 1.2) return null;
    const mag = 1 + 0.4 * (1 - Math.min(t, 1)) * (1 - Math.min(t, 1));
    let nx = cx + dx * mag, ny = cy + dy * mag;
    const out = Math.hypot(nx - cx, ny - cy);
    if (out > R && out > 0) {
      const s = (R - 0.4) / out;
      nx = cx + (nx - cx) * s;
      ny = cy + (ny - cy) * s;
    }
    return { x: nx, y: ny, t: Math.min(t, 1) };
  }

  function sizeBoards() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const box = board.parentElement.getBoundingClientRect();
    board.width = box.width * dpr;
    board.height = box.height * dpr;
    layer.setTransform(dpr, 0, 0, dpr, 0, 0);
    const lb = lens.getBoundingClientRect();
    lens.width = lb.width * dpr;
    lens.height = lb.height * dpr;
    lensLayer.setTransform(dpr, 0, 0, dpr, 0, 0);
    needPaint = true;
  }

  function frameShown() {
    if (!shown.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    shown.forEach((n) => {
      minX = Math.min(minX, n.x);
      maxX = Math.max(maxX, n.x);
      minY = Math.min(minY, n.y);
      maxY = Math.max(maxY, n.y);
    });
    const pad = 10;
    const bw = Math.max(40, maxX - minX + pad * 2);
    const bh = Math.max(40, maxY - minY + pad * 2);
    const box = board.getBoundingClientRect();
    zoom = Math.min((box.width - 48) / bw, (box.height - 48) / bh, 12);
    panX = -((minX + maxX) / 2) * zoom;
    panY = -((minY + maxY) / 2) * zoom;
  }

  function strokePair(c, a, b, at, steps, style, width) {
    const pts = [];
    const pa = at(a.x, a.y);
    const pb = at(b.x, b.y);
    if (!pa || !pb) return;
    if (pa.t > 0.98 && pb.t > 0.98) return;
    pts.push(pa);
    for (let k = 1; k < steps; k++) {
      const t = k / steps;
      const p = at(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
      if (p) pts.push(p);
    }
    pts.push(pb);
    if (pts.length < 2) return;
    c.beginPath();
    c.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) c.lineTo(pts[i].x, pts[i].y);
    c.strokeStyle = style;
    c.lineWidth = width;
    c.lineCap = "round";
    c.lineJoin = "round";
    c.stroke();
  }

  function paintLayer(c, w, h, z, ox, oy, warped) {
    c.save();
    c.translate(w / 2 + ox, h / 2 + oy);
    c.scale(z, z);
    const R = (Math.min(w, h) / 2 - 2) / z;
    const cx = warped ? focusX : 0, cy = warped ? focusY : 0;
    const at = (x, y) => (warped ? warpNear(x, y, cx, cy, R) : { x, y, t: 0 });
    const steps = warped ? 28 : 1;
    bonds.forEach(([i, j]) => {
      const a = shown[i], b = shown[j];
      if (!a || !b) return;
      const hot = i === over || j === over || i === chosen || j === chosen;
      strokePair(c, a, b, at, steps,
        hot ? "rgba(160,240,230,0.7)" : (warped ? "rgba(170,210,210,0.5)" : "rgba(170,210,210,0.16)"),
        warped ? Math.max(1.8 / z, 0.2) : 0.11);
    });
    shown.forEach((n, i) => {
      const p = at(n.x, n.y);
      if (!p) return;
      const hot = i === over || i === chosen;
      const col = n.row.pass ? "#6cffc8" : "#ff5ec8";
      c.shadowColor = col;
      c.shadowBlur = warped ? 0 : (hot ? 8 : 2);
      const rad = warped
        ? Math.max(1.05 / z, n.rad) * (1.05 + 0.2 * (1 - p.t))
        : (hot ? n.rad + 0.28 : n.rad);
      c.beginPath();
      c.arc(p.x, p.y, rad, 0, Math.PI * 2);
      c.fillStyle = col;
      c.globalAlpha = hot ? 1 : 0.9;
      c.fill();
      c.globalAlpha = 1;
      c.shadowBlur = 0;
      if (hot || (warped && p.t < 0.28)) {
        c.font = (warped ? Math.max(11 / z, 0.7) : 11) + "px Outfit, Helvetica, Arial, sans-serif";
        c.fillStyle = col;
        c.fillText(n.row.pass ? "pass" : "fail", p.x + 7, p.y - 5);
      }
    });
    c.restore();
  }

  let fieldSpecks = [];
  let fieldKey = "";
  function fillField(c, w, h) {
    const key = w + "x" + h;
    if (key !== fieldKey) {
      fieldKey = key;
      fieldSpecks = [];
      let s = 9;
      const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
      const n = Math.round((w * h) / 4500);
      for (let i = 0; i < n; i++) {
        fieldSpecks.push({ x: rnd() * w, y: rnd() * h, a: 0.08 + rnd() * 0.35, r: rnd() * 1.2 });
      }
    }
    c.fillStyle = "#020309";
    c.fillRect(0, 0, w, h);
    fieldSpecks.forEach((p) => {
      c.fillStyle = "rgba(200,220,230," + p.a + ")";
      c.beginPath();
      c.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      c.fill();
    });
  }

  function paint() {
    if (!needPaint) return;
    needPaint = false;
    const w = board.clientWidth, h = board.clientHeight;
    layer.clearRect(0, 0, w, h);
    fillField(layer, w, h);
    paintLayer(layer, w, h, zoom, panX, panY, false);
    const mw = lens.clientWidth || 168;
    const mh = lens.clientHeight || 168;
    lensLayer.clearRect(0, 0, mw, mh);
    lensLayer.save();
    lensLayer.beginPath();
    lensLayer.arc(mw / 2, mh / 2, mw / 2 - 1, 0, Math.PI * 2);
    lensLayer.clip();
    lensLayer.fillStyle = "#03040a";
    lensLayer.fillRect(0, 0, mw, mh);
    const lz = zoom * 1.35;
    paintLayer(lensLayer, mw, mh, lz, -focusX * lz, -focusY * lz, true);
    lensLayer.restore();
  }

  function prettyWhen(ts) {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toLocaleString(undefined, {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function refillList() {
    list.replaceChildren();
    shown.forEach((n, k) => {
        const b = document.createElement("button");
        b.type = "button";
        const outcome = n.row.pass ? "passed" : "failed";
        const secs = n.row.seconds_to_green != null ? n.row.seconds_to_green + "s to green" : "";
        b.innerHTML = "Run " + (k + 1) + " · " + outcome
          + "<span class=\"silk-run-meta\">" + prettyWhen(n.row.ts) + (secs ? " · " + secs : "") + "</span>";
        b.addEventListener("click", () => {
          chosen = shown.indexOf(n);
          note.textContent = (n.row.pass ? "Passed" : "Failed") + " · "
            + (n.row.seconds_to_green != null ? n.row.seconds_to_green + "s" : "") + " · "
            + ((n.row.actions || []).join(", ") || "no actions");
          panX = -n.x * zoom;
          panY = -n.y * zoom;
          focusX = n.x;
          focusY = n.y;
          needPaint = true;
        });
        list.appendChild(b);
    });
    if (!shown.length && runs.length) {
      const empty = document.createElement("div");
      empty.className = "silk-branch";
      empty.textContent = "No matching runs";
      list.appendChild(empty);
    }
  }

  function refillTones() {
    tones.replaceChildren();
    [
      { key: "pass", label: "pass", color: "#6cffc8" },
      { key: "fail", label: "fail", color: "#ff5ec8" },
    ].forEach((item) => {
      const b = document.createElement("button");
      b.type = "button";
      b.innerHTML = `<span class="silk-pip" style="color:${item.color};background:${item.color}"></span>${item.label}`;
      b.addEventListener("click", () => {
        if (outcomeOn.has(item.key)) outcomeOn.delete(item.key);
        else outcomeOn.add(item.key);
        b.classList.toggle("is-on", outcomeOn.has(item.key));
        refresh();
      });
      tones.appendChild(b);
    });
    const hashes = [];
    runs.forEach((r) => {
      const h = r.learned_hash;
      if (h && !hashes.includes(h)) hashes.push(h);
    });
    if (hashes.length > 1) {
      hashes.forEach((h) => {
        const col = hue(h);
        const b = document.createElement("button");
        b.type = "button";
        b.innerHTML = `<span class="silk-pip" style="color:${col};background:${col}"></span>${h.slice(0, 8)}`;
        b.addEventListener("click", () => {
          if (hashOn.has(h)) hashOn.delete(h);
          else hashOn.add(h);
          b.classList.toggle("is-on", hashOn.has(h));
          refresh();
        });
        tones.appendChild(b);
      });
    }
    const verbs = new Set();
    runs.forEach((r) => (r.actions || []).forEach((v) => verbs.add(v)));
    chips.replaceChildren();
    [...verbs].forEach((v) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = v;
      b.addEventListener("click", () => {
        if (verbOn.has(v)) verbOn.delete(v);
        else verbOn.add(v);
        b.classList.toggle("is-on", verbOn.has(v));
        refresh();
      });
      chips.appendChild(b);
    });
  }

  function refresh() {
    shown = place(runs.filter(allowed));
    vacant.classList.toggle("is-on", runs.length === 0);
    frameShown();
    refillList();
    needPaint = true;
  }

  document.getElementById("q").addEventListener("input", (e) => {
    find = e.target.value.trim().toLowerCase();
    refresh();
  });

  board.addEventListener("pointerdown", (e) => {
    hold = true;
    moved = false;
    lastX = e.clientX;
    lastY = e.clientY;
    board.classList.add("is-hold");
  });
  addEventListener("pointerup", (e) => {
    if (hold && !moved) {
      const p = mapPointer(e.clientX, e.clientY);
      chosen = hitRun(p.x, p.y);
      needPaint = true;
    }
    hold = false;
    board.classList.remove("is-hold");
  });
  board.addEventListener("pointermove", (e) => {
    if (hold) {
      panX += e.clientX - lastX;
      panY += e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      moved = true;
    }
    const p = mapPointer(e.clientX, e.clientY);
    over = hitRun(p.x, p.y);
    focusX = p.x;
    focusY = p.y;
    needPaint = true;
  });
  board.parentElement.addEventListener("wheel", (e) => {
    e.preventDefault();
    const keep = mapPointer(e.clientX, e.clientY);
    zoom = Math.min(5, Math.max(0.2, zoom * (e.deltaY > 0 ? 0.88 : 1.14)));
    const box = board.getBoundingClientRect();
    panX = e.clientX - box.left - box.width / 2 - keep.x * zoom;
    panY = e.clientY - box.top - box.height / 2 - keep.y * zoom;
    needPaint = true;
  }, { passive: false });

  async function boot() {
    sizeBoards();
    const raw = await fetch("/scoreboard.jsonl", { cache: "no-store" }).then((r) => r.text());
    runs = raw.split("\n").filter(Boolean).map((line) => JSON.parse(line));
    tally = await fetch("/summary.json", { cache: "no-store" }).then((r) => r.json());
    const code = tally.verdict || "INSUFFICIENT_N";
    const copy = trendCopy[code] || [code, ""];
    verdict.textContent = copy[0];
    why.textContent = copy[1];
    const probe = tally.probe
      ? (Array.isArray(tally.probe) ? tally.probe.join(" | ") : tally.probe)
      : "";
    exam.textContent = probe ? "Probe (the exam): " + probe : "";
    refillTones();
    refresh();
  }

  addEventListener("resize", () => { sizeBoards(); refresh(); });
  function loop() {
    paint();
    requestAnimationFrame(loop);
  }
  loop();
  boot();
})();
