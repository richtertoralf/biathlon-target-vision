// Read complete states only; never send commands or input drafts.
(() => {
  const lanes = document.getElementById('lanes');
  let socket, timer, retry, lastMessage = 0;
  function render(state) {
    document.getElementById('session-name').textContent = state.session?.name || '';
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
    // Only the first attempt is "connecting"; retries keep the interrupted state visible.
    if (!socket) BTVShell.connection('connecting');
    if (socket) { socket.onclose = null; socket.close(); }
    const current = socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
    lastMessage = Date.now();
    current.onmessage = event => {
      if (socket !== current) return;
      const state = JSON.parse(event.data); if (state.type !== 'state') return;
      lastMessage = Date.now(); render(state);
      BTVShell.connection(state.health === 'error' ? 'fault' : 'online');
    };
    current.onclose = () => {
      clearInterval(timer); BTVShell.connection('offline', '○ Unterbrochen – letzter Stand');
      retry = setTimeout(connect, 1000);
    };
    timer = setInterval(() => { if (Date.now() - lastMessage > 12000) current.close(); }, 1000);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) connect(); });
  connect();
})();
