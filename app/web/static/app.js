// Live dashboard client: websocket feed + small action helpers.
(function () {
  "use strict";

  // ---- helpers -------------------------------------------------------------
  window.api = async function (method, url, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (!res.ok) throw new Error((data && data.error) || ("HTTP " + res.status));
    return data;
  };

  function fmtTime(iso) {
    try { return new Date(iso).toLocaleTimeString(); } catch (e) { return ""; }
  }

  // ---- live feed -----------------------------------------------------------
  function addEvent(ev) {
    const feed = document.getElementById("feed");
    if (!feed || ev.type !== "activity") return;
    const div = document.createElement("div");
    div.className = "event " + (ev.level || "info");
    div.innerHTML =
      '<span class="who">' + escapeHtml(ev.agent) + "</span> " +
      escapeHtml(ev.message) +
      ' <span class="ts">' + fmtTime(ev.created_at) + "</span>";
    feed.prepend(div);
    while (feed.children.length > 200) feed.removeChild(feed.lastChild);
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function updateBadge(n) {
    const badge = document.getElementById("pending-badge");
    if (!badge) return;
    if (n > 0) { badge.textContent = n; badge.style.display = "inline-block"; }
    else { badge.style.display = "none"; }
  }

  async function refreshState() {
    try {
      const s = await window.api("GET", "/api/state");
      updateBadge(s.pending_count);
      // Update agent status dots if present.
      Object.keys(s.agents || {}).forEach(function (name) {
        const dot = document.querySelector('.dot[data-agent="' + name + '"]');
        if (dot) dot.className = "dot " + s.agents[name].status;
        const st = document.querySelector('.status[data-agent="' + name + '"]');
        if (st) st.textContent = s.agents[name].status.replace("_", " ");
      });
    } catch (e) { /* ignore transient errors */ }
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const sock = new WebSocket(proto + "://" + location.host + "/ws");
    sock.onmessage = function (msg) {
      const ev = JSON.parse(msg.data);
      addEvent(ev);
      if (["approvals_changed", "agent_status", "products_changed",
           "revenue_changed", "tunnel_changed"].indexOf(ev.type) !== -1) {
        refreshState();
        // For approvals/revenue pages, reload to reflect the change simply & correctly.
        if ((ev.type === "approvals_changed" && location.pathname === "/approvals") ||
            (ev.type === "revenue_changed" && location.pathname === "/revenue")) {
          setTimeout(function () { location.reload(); }, 600);
        }
      }
    };
    // Only keep retrying while we're logged in (avoids 403 spam on the login page
    // or after logout/session expiry).
    sock.onclose = function () {
      if (document.body.dataset.authed === "1") setTimeout(connect, 2500);
    };
  }

  // ---- action wiring (event delegation) ------------------------------------
  document.addEventListener("click", async function (e) {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const action = el.getAttribute("data-action");
    try {
      if (action === "approve" || action === "reject") {
        el.disabled = true;
        await window.api("POST", "/api/approvals/" + el.dataset.id + "/" + action);
        const card = el.closest(".approval");
        if (card) card.remove();
      } else if (action === "run-agent") {
        el.disabled = true; el.textContent = "Working…";
        await window.api("POST", "/api/agents/" + el.dataset.agent + "/run");
        setTimeout(function () { el.disabled = false; el.textContent = "Run now"; }, 4000);
      } else if (action === "toggle-agent") {
        await window.api("POST", "/api/agents/" + el.dataset.agent + "/toggle",
                         { enabled: el.checked });
      }
    } catch (err) {
      alert("Something went wrong: " + err.message);
      el.disabled = false;
    }
  });

  // Toggle switches fire 'change', not 'click' reliably on mobile.
  document.addEventListener("change", async function (e) {
    const el = e.target;
    if (el.matches('input[data-action="toggle-agent"]')) {
      try {
        await window.api("POST", "/api/agents/" + el.dataset.agent + "/toggle",
                         { enabled: el.checked });
      } catch (err) { alert("Could not change agent: " + err.message); el.checked = !el.checked; }
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    // Don't open the live feed until the user is logged in — the login / set-PIN
    // pages share this script, and an unauthenticated /ws is correctly rejected.
    if (document.body.dataset.authed !== "1") return;
    connect();
    refreshState();
  });
})();
