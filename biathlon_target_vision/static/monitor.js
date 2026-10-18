// Vollständige Zustände lesen, niemals Befehle oder Eingabeentwürfe senden.
(() => {
  const lanes = document.getElementById('lanes'), connection = document.getElementById('connection');
  let socket, timer, retry, lastMessage = 0;
  function render(state) {
    lanes.replaceChildren();
    for (const lane of Object.values(state.lanes)) {
      const occupied = state.bouts[lane.occupied_bout_id];
      const card = document.createElement('section'); card.className = 'lane'; card.dataset.status = lane.status; card.id = `lane-${lane.lane_id}`;
      const title = document.createElement('h2'); title.textContent = `Bahn ${lane.lane_id}`;
      const badge = document.createElement('span'); badge.className = 'status';
      badge.textContent = {occupied:'Belegt',ready:'Frei – bereit',reset_required:'Frei – Rückstellung ausstehend'}[lane.status]; title.append(badge);
      const bib = document.createElement('p');
      bib.textContent = `Startnummer: ${occupied?.bib ?? '–'}`;
      const targets = document.createElement('div'); targets.className = 'targets';
      lane.targets.forEach((value, index) => {
        const target = document.createElement('span'); target.className = `target ${value}`;
        target.dataset.state = value; target.textContent = value === 'unknown' ? '?' : value === 'fallen' ? '✓' : '';
        target.title = `Scheibe ${index + 1}: ${{standing:'aufgerichtet', fallen:'gefallen', unknown:'unbekannt'}[value]}`;
        targets.append(target);
      });
      const warning = document.createElement('p'); warning.className = 'capture-status';
      const camera = state.capture?.cameras.find(item => item.lane_ids.includes(lane.lane_id));
      if (lane.mode !== 'manual' && camera && (!state.capture.running || !camera.connected || lane.automatic_targets.includes('unknown')))
        warning.textContent = 'Scheiben manuell prüfen';
      card.append(title, bib, targets, warning); lanes.append(card);
    }
  }
  function connect() {
    clearTimeout(retry); clearInterval(timer);
    if (socket) { socket.onclose = null; socket.close(); }
    connection.textContent = 'Verbinden …'; connection.className = 'offline';
    const current = socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
    lastMessage = Date.now();
    current.onmessage = event => {
      if (socket !== current) return;
      const state = JSON.parse(event.data); if (state.type !== 'state') return;
      lastMessage = Date.now(); render(state);
      connection.textContent = state.health === 'error' ? 'Erfassung gestört' : 'Live';
      connection.className = state.health === 'error' ? 'offline' : '';
    };
    current.onclose = () => {
      clearInterval(timer); connection.textContent = 'Verbindung unterbrochen – letzter Stand'; connection.className = 'offline';
      retry = setTimeout(connect, 1000);
    };
    timer = setInterval(() => { if (Date.now() - lastMessage > 12000) current.close(); }, 1000);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) connect(); });
  connect();
})();
