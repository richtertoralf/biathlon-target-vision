// Vollständige Zustände lesen, niemals Befehle oder Eingabeentwürfe senden.
(() => {
  const lanes = document.getElementById('lanes'), connection = document.getElementById('connection');
  let socket, timer, retry, lastMessage = 0;
  function render(state) {
    lanes.replaceChildren();
    for (const lane of Object.values(state.lanes)) {
      const current = state.bouts[lane.current_bout_id], occupied = state.bouts[lane.occupied_bout_id];
      const card = document.createElement('section'); card.className = 'lane'; card.id = `lane-${lane.lane_id}`;
      const title = document.createElement('h2'); title.textContent = `Bahn ${lane.lane_id} · ${occupied ? 'belegt' : 'frei'}`;
      const bib = document.createElement('p');
      bib.textContent = `Startnummer: ${current?.bib ?? (occupied && !current ? occupied.bib : null) ?? '–'}`;
      if (occupied && current && occupied.bout_id !== current.bout_id) bib.textContent += ` · vorherige Belegung: ${occupied.bib ?? '–'}`;
      const targets = document.createElement('div'); targets.className = 'targets';
      lane.targets.forEach((value, index) => {
        const target = document.createElement('span'); target.className = `target ${value}`;
        target.dataset.state = value; target.textContent = value === 'unknown' ? '?' : value === 'fallen' ? '✓' : '○';
        target.title = `Ziel ${index + 1}: ${{standing:'aufgerichtet', fallen:'gefallen', unknown:'unbekannt'}[value]}`;
        targets.append(target);
      });
      const count = document.createElement('p'); count.className = 'fallen-count';
      count.textContent = `Gefallen in aktueller Einlage: ${current?.fallen_target_ids.length ?? 0}/5`;
      card.append(title, bib, targets, count); lanes.append(card);
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
      connection.textContent = state.health === 'error' ? 'Erfassung gestört – letzter Stand' : 'Live';
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
