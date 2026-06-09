// The Vault — a Fallout-Shelter-style live view of the agent team.
// Pixel-art drawn entirely in code (no image assets). Seeds from /api/state, then
// animates in real time off the same /ws events the dashboard uses.
(function () {
  "use strict";
  var canvas = document.getElementById("vault");
  if (!canvas) return;
  var ctx = canvas.getContext("2d");
  var VW = 480, VH = 300;
  canvas.width = VW; canvas.height = VH;   // low-res backing store; CSS upscales (pixelated)
  ctx.imageSmoothingEnabled = false;

  var COL = {
    bg: "#0a0d12", room: "#11161d", roomLit: "#16202b", border: "#2d3742",
    floor: "#202a36", text: "#e6edf3", muted: "#93a1b1", skin: "#e8b48a",
    accent: "#3fb950", warn: "#d29922", error: "#f85149", elevator: "#161d27"
  };
  var CATCOL = { overseer: "#a371f7", workshop: "#d29922", studio: "#58a6ff",
                 marketing: "#3fb950", vault: "#e3b341" };
  var MAP = {
    onboarding: "overseer", optimizer: "overseer",
    pod: "workshop", digital: "workshop", kdp: "workshop",
    video: "studio", blog: "studio",
    marketing: "marketing", newsletter: "marketing",
    bookkeeper: "vault"
  };
  var ITEM = { workshop: "📦", studio: "🎬", marketing: "📣", overseer: "📊", vault: "💰" };

  // --- layout (in 480x300 virtual space) ------------------------------------
  var rooms = {};
  (function buildRooms() {
    var top = 30, bot = 292, rL = 132, rR = 472;
    var fh = Math.floor((bot - top) / 4);
    rooms.quarters = { x: 8, y: top, w: 88, h: bot - top, label: "QUARTERS", key: "quarters" };
    rooms.elevator = { x: 100, y: top, w: 28, h: bot - top, label: "", key: "elevator" };
    rooms.overseer = { x: rL, y: top, w: rR - rL, h: fh - 4, label: "OVERSEER", key: "overseer" };
    rooms.workshop = { x: rL, y: top + fh, w: rR - rL, h: fh - 4, label: "WORKSHOP", key: "workshop" };
    rooms.studio = { x: rL, y: top + 2 * fh, w: rR - rL, h: fh - 4, label: "STUDIO", key: "studio" };
    rooms.marketing = { x: rL, y: top + 3 * fh, w: (rR - rL) / 2 - 4, h: fh - 4, label: "MARKETING BAY", key: "marketing" };
    rooms.vault = { x: rL + (rR - rL) / 2 + 4, y: top + 3 * fh, w: (rR - rL) / 2 - 4, h: fh - 4, label: "VAULT DOOR", key: "vault" };
  })();
  var elevatorX = rooms.elevator.x + rooms.elevator.w / 2;
  function walkY(r) { return r.y + r.h - 12; }

  // --- dwellers (one per agent) ---------------------------------------------
  var roster = window.VAULT_ROSTER || [];
  var dwellers = [], byName = {};
  var qIdx = 0, workIdx = {};
  roster.forEach(function (a) {
    var cat = MAP[a.name] || "overseer";
    var hx = rooms.quarters.x + 16 + (qIdx % 4) * 18;
    var hy = rooms.quarters.y + 34 + Math.floor(qIdx / 4) * 32;
    qIdx++;
    var wr = rooms[cat];
    workIdx[cat] = workIdx[cat] || 0;
    var wx = wr.x + 20 + workIdx[cat] * 22; workIdx[cat]++;
    var d = {
      name: a.name, display: a.display_name || a.name, cat: cat,
      color: CATCOL[cat] || "#888", status: a.status || "idle",
      enabled: !!a.enabled, message: a.last_message || "",
      home: { x: hx, y: hy }, work: { x: wx, y: walkY(wr) },
      x: hx, y: hy, path: [], frame: 0, anim: 0, flash: 0, moving: false
    };
    dwellers.push(d); byName[a.name] = d;
  });

  function targetFor(d) {
    if (d.status === "running") return d.work;
    if (d.status === "waiting_approval")
      return { x: rooms.vault.x + rooms.vault.w - 22, y: walkY(rooms.vault) };
    return d.home; // idle / error rest in Quarters (error also flashes)
  }
  function setPath(d) {
    var t = targetFor(d), p = [];
    if (Math.abs(d.x - t.x) > 2 || Math.abs(d.y - t.y) > 2) {
      p.push({ x: elevatorX, y: d.y });   // walk to the elevator
      p.push({ x: elevatorX, y: t.y });   // ride to the target floor
      p.push({ x: t.x, y: t.y });         // walk to the room
    }
    d.path = p;
  }

  // --- state ----------------------------------------------------------------
  var items = [], pending = 0, pulse = 0, selected = null, lastCat = null;

  function anyRunningIn(key) {
    return dwellers.some(function (d) { return d.cat === key && d.status === "running"; });
  }

  // --- update ---------------------------------------------------------------
  var SPEED = 58;
  function update(dt) {
    dwellers.forEach(function (d) {
      if (d.path.length) {
        var wp = d.path[0], dx = wp.x - d.x, dy = wp.y - d.y, dist = Math.hypot(dx, dy);
        var step = SPEED * dt;
        if (dist <= step) { d.x = wp.x; d.y = wp.y; d.path.shift(); }
        else { d.x += dx / dist * step; d.y += dy / dist * step; }
        d.moving = true;
      } else d.moving = false;
      d.anim += dt * (d.moving ? 8 : (d.status === "running" ? 6 : 2));
      d.frame = Math.floor(d.anim) % 2;
      if (d.flash > 0) d.flash -= dt;
    });
    items.forEach(function (it) {
      var dx = it.tx - it.x, dy = it.ty - it.y, dist = Math.hypot(dx, dy), step = 70 * dt;
      if (dist <= step) it.done = true; else { it.x += dx / dist * step; it.y += dy / dist * step; }
    });
    items = items.filter(function (it) { return !it.done; });
    pulse += dt;
  }

  // --- render ---------------------------------------------------------------
  function drawRoom(r) {
    ctx.fillStyle = anyRunningIn(r.key) ? COL.roomLit : COL.room;
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.strokeStyle = COL.border; ctx.lineWidth = 2;
    ctx.strokeRect(r.x + 1, r.y + 1, r.w - 2, r.h - 2);
    ctx.fillStyle = COL.floor; ctx.fillRect(r.x + 2, r.y + r.h - 6, r.w - 4, 4);
    if (r.label) {
      ctx.fillStyle = COL.muted; ctx.font = "8px monospace"; ctx.textBaseline = "top";
      ctx.fillText(r.label, r.x + 5, r.y + 4);
    }
  }
  function drawElevator() {
    var e = rooms.elevator;
    ctx.fillStyle = COL.elevator; ctx.fillRect(e.x, e.y, e.w, e.h);
    ctx.strokeStyle = COL.border; ctx.lineWidth = 2; ctx.strokeRect(e.x + 1, e.y + 1, e.w - 2, e.h - 2);
    ctx.fillStyle = COL.border; ctx.fillRect(e.x + e.w / 2 - 1, e.y, 2, e.h);
  }
  function drawDweller(d) {
    var x = Math.round(d.x), y = Math.round(d.y);
    var c = d.color;
    if (d.status === "error" && Math.floor(pulse * 4) % 2 === 0) c = COL.error;
    // legs (2-frame walk)
    ctx.fillStyle = "#1b2330";
    if (d.moving && d.frame) { ctx.fillRect(x - 3, y - 3, 2, 3); ctx.fillRect(x + 2, y - 4, 2, 4); }
    else { ctx.fillRect(x - 3, y - 3, 2, 3); ctx.fillRect(x + 1, y - 3, 2, 3); }
    ctx.fillStyle = c; ctx.fillRect(x - 4, y - 9, 8, 7);                  // jumpsuit body
    ctx.fillStyle = "#0d1117"; ctx.fillRect(x - 4, y - 4, 8, 1);          // belt
    ctx.fillStyle = COL.skin; ctx.fillRect(x - 3, y - 14, 6, 5);          // head
    ctx.fillStyle = "#0d1117"; ctx.fillRect(x - 3, y - 15, 6, 2);         // hair
    if (d.status === "running" && !d.moving) {                            // working spark
      ctx.fillStyle = d.frame ? COL.warn : COL.accent;
      ctx.fillRect(x + 4, y - 12, 2, 2);
    }
    if (d.status === "waiting_approval" && Math.floor(pulse * 3) % 2 === 0) {
      ctx.fillStyle = COL.warn; ctx.font = "bold 11px monospace"; ctx.textBaseline = "bottom";
      ctx.fillText("!", x - 2, y - 15);
    }
    if (selected === d) {
      ctx.strokeStyle = COL.accent; ctx.lineWidth = 1; ctx.strokeRect(x - 6, y - 17, 12, 17);
    }
  }
  function drawBubble(d) {
    if (d.status !== "running" || !d.message) return;
    var txt = d.message.length > 26 ? d.message.slice(0, 25) + "…" : d.message;
    ctx.font = "8px monospace";
    var w = ctx.measureText(txt).width + 8;
    var bx = Math.max(4, Math.min(Math.round(d.x - w / 2), VW - w - 4)), by = Math.round(d.y - 32);
    ctx.fillStyle = "#0d1117"; ctx.fillRect(bx, by, w, 12);
    ctx.strokeStyle = COL.border; ctx.lineWidth = 1; ctx.strokeRect(bx + 0.5, by + 0.5, w - 1, 11);
    ctx.fillStyle = COL.text; ctx.textBaseline = "top"; ctx.fillText(txt, bx + 4, by + 2);
  }
  function render() {
    ctx.fillStyle = COL.bg; ctx.fillRect(0, 0, VW, VH);
    drawRoom(rooms.quarters); drawElevator();
    ["overseer", "workshop", "studio", "marketing", "vault"].forEach(function (k) { drawRoom(rooms[k]); });
    if (pending > 0) {  // approvals airlock light
      ctx.fillStyle = Math.floor(pulse * 2) % 2 === 0 ? COL.warn : "#3a2d00";
      ctx.fillRect(rooms.vault.x + rooms.vault.w - 12, rooms.vault.y + 5, 6, 6);
    }
    var sorted = dwellers.slice().sort(function (a, b) { return a.y - b.y; });
    sorted.forEach(drawDweller);
    sorted.forEach(drawBubble);
    ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.font = "12px serif";
    items.forEach(function (it) { ctx.fillText(it.emoji, it.x, it.y); });
    ctx.textAlign = "left";
  }

  // --- live data ------------------------------------------------------------
  function applyState(s) {
    pending = s.pending_count || 0;
    var net = s.revenue && s.revenue.net != null ? Number(s.revenue.net) : 0;
    setText("hud-net", "$" + net.toFixed(2));
    setText("hud-pending", pending);
    var names = Object.keys(s.agents || {}), online = 0, running = 0;
    names.forEach(function (n) {
      var a = s.agents[n]; if (a.enabled) online++; if (a.status === "running") running++;
      var d = byName[n];
      if (d) {
        var changed = d.status !== a.status;
        d.status = a.status; d.enabled = a.enabled;
        if (a.last_message) d.message = a.last_message;
        if (changed) setPath(d);
      }
    });
    setText("hud-online", online + "/" + names.length);
    setText("hud-running", running);
    if (selected) refreshPanel();
  }
  function setText(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }
  function fetchState() { window.api("GET", "/api/state").then(applyState).catch(function () {}); }
  var hudT = null;
  function fetchSoon() { if (hudT) return; hudT = setTimeout(function () { hudT = null; fetchState(); }, 300); }

  function spawnItem(cat) {
    var from = rooms[cat] || rooms.overseer;
    items.push({ emoji: ITEM[cat] || "✨", x: from.x + from.w / 2, y: from.y + from.h / 2,
                 tx: rooms.vault.x + rooms.vault.w / 2, ty: rooms.vault.y + rooms.vault.h / 2 });
  }
  function onEvent(ev) {
    if (!ev || !ev.type) return;
    if (ev.type === "activity" && ev.agent) {
      var d = byName[ev.agent]; if (d) d.message = ev.message; lastCat = MAP[ev.agent] || lastCat;
    } else if (ev.type === "agent_status" && ev.agent) {
      var d2 = byName[ev.agent];
      if (d2 && d2.status !== ev.status) {
        d2.status = ev.status; if (ev.status === "error") d2.flash = 0.8; setPath(d2);
      }
      lastCat = MAP[ev.agent] || lastCat; fetchSoon();
    } else if (ev.type === "products_changed") {
      spawnItem(lastCat || "workshop"); fetchSoon();
    } else if (ev.type === "revenue_changed") {
      spawnItem("vault"); fetchSoon();
    } else if (ev.type === "approvals_changed") {
      fetchSoon();
    }
  }
  function connect() {
    var proto = location.protocol === "https:" ? "wss" : "ws";
    var sock = new WebSocket(proto + "://" + location.host + "/ws");
    sock.onmessage = function (m) { try { onEvent(JSON.parse(m.data)); } catch (e) {} };
    sock.onclose = function () { setTimeout(connect, 2500); };
  }

  // --- interactivity --------------------------------------------------------
  var panel = document.getElementById("panel");
  function pick(vx, vy) {
    var best = null, bd = 1e9;
    dwellers.forEach(function (d) {
      var dist = Math.hypot(vx - d.x, vy - (d.y - 8));
      if (dist < 14 && dist < bd) { bd = dist; best = d; }
    });
    return best;
  }
  function refreshPanel() {
    if (!selected) return;
    setText("panel-name", selected.display);
    setText("panel-status", selected.status.replace("_", " "));
    setText("panel-msg", selected.message || "—");
    var t = document.getElementById("panel-toggle"); if (t) t.textContent = selected.enabled ? "Disable" : "Enable";
  }
  canvas.addEventListener("click", function (e) {
    var rect = canvas.getBoundingClientRect();
    var vx = (e.clientX - rect.left) / rect.width * VW;
    var vy = (e.clientY - rect.top) / rect.height * VH;
    selected = pick(vx, vy);
    if (selected) { panel.hidden = false; refreshPanel(); } else panel.hidden = true;
  });
  document.getElementById("panel-close").addEventListener("click", function () {
    selected = null; panel.hidden = true;
  });
  document.getElementById("panel-run").addEventListener("click", function () {
    if (selected) window.api("POST", "/api/agents/" + selected.name + "/run").catch(function (e) { alert(e.message); });
  });
  document.getElementById("panel-toggle").addEventListener("click", function () {
    if (!selected) return;
    var ns = !selected.enabled;
    window.api("POST", "/api/agents/" + selected.name + "/toggle", { enabled: ns })
      .then(function () { selected.enabled = ns; refreshPanel(); fetchSoon(); })
      .catch(function (e) { alert(e.message); });
  });

  // --- boot -----------------------------------------------------------------
  var last = performance.now();
  function loop(now) {
    var dt = Math.min(0.05, (now - last) / 1000); last = now;
    update(dt); render(); requestAnimationFrame(loop);
  }
  fetchState();
  connect();
  requestAnimationFrame(loop);
})();
