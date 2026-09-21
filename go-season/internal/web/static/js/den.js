(function () {
  const root = document.getElementById("den");
  if (!root) return;

  const matchId = root.dataset.matchId;
  const feed = document.getElementById("feed");
  const scoreEl = document.getElementById("score");
  const minuteEl = document.getElementById("minute");
  const phaseEl = document.getElementById("phase-label");
  const rulesEl = document.getElementById("rules-summary");
  const statusEl = document.getElementById("ws-status");
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/den/${matchId}`;

  let socket;

  function setStatus(text, ok) {
    statusEl.textContent = text;
    statusEl.classList.toggle("ok", !!ok);
    statusEl.classList.toggle("bad", ok === false);
  }

  function pushEvent(ev) {
    if (!ev || !ev.message) return;
    const li = document.createElement("li");
    li.className = ev.type || "";
    li.textContent = ev.message;
    feed.prepend(li);
  }

  function applyState(state) {
    if (!state) return;
    scoreEl.textContent = `${state.home_score}-${state.away_score}`;
    minuteEl.textContent = `${state.minute || 0}'`;
    phaseEl.textContent = state.phase || "";
    if (state.rules_summary) rulesEl.textContent = state.rules_summary;
  }

  function connect() {
    socket = new WebSocket(url);
    socket.addEventListener("open", () => setStatus("live socket", true));
    socket.addEventListener("close", () => {
      setStatus("disconnected — retrying", false);
      setTimeout(connect, 1500);
    });
    socket.addEventListener("error", () => setStatus("socket error", false));
    socket.addEventListener("message", (msg) => {
      let data;
      try { data = JSON.parse(msg.data); } catch { return; }
      if (data.state) applyState(data.state);
      if (data.type === "state" || !data.message) return;
      pushEvent(data);
    });
  }

  document.getElementById("btn-start").addEventListener("click", () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action: "start" }));
    }
  });
  document.getElementById("btn-stop").addEventListener("click", () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action: "stop" }));
    }
  });

  connect();
})();
