// Administration: cameras, lanes and sessions on one page with three tabs.
// RTSP credentials are write-only; the server only returns a redacted address.
(() => {
  const el = id => document.getElementById(id);
  const STATES = {standing: 'aufgerichtet', fallen: 'gefallen', unknown: 'unbekannt'};
  const CAPTURE = {active: 'Automatik aktiv', uncertain: 'Erkennung läuft / unsicher', unavailable: 'Nur manuell'};
  let state = null, cameras = [], selectedCamera = '', pickedLanes = new Set(), idEdited = false;
  let selectedLane = null, calibrationInfo = {}, sourceBusy = false, sessionBusy = false, sessionId = null;
  let previewBusy = false, removeTimer = null;

  // Small DOM builder: user-provided names are always inserted as text.
  function h(tag, attributes = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attributes)) {
      if (value === false || value === null || value === undefined) continue;
      if (key === 'text') node.textContent = value; else node.setAttribute(key, value === true ? '' : value);
    }
    node.append(...children);
    return node;
  }
  async function request(url, options) {
    const response = await fetch(url, {cache: 'no-store', ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : `Anfrage fehlgeschlagen (${response.status})`);
    return data;
  }
  function message(id, text, error = false) {
    el(id).textContent = text;
    el(id).toggleAttribute('data-error', error);
  }
  const time = value => new Date(value).toLocaleString('de-DE');
  const laneIds = () => state ? Object.values(state.lanes).map(lane => lane.lane_id) : [];
  const cameraForLane = laneId => state?.capture.cameras.find(camera => camera.lane_ids.includes(laneId));

  // Tabs follow the URL hash so reloading keeps the current area.
  function showTab() {
    const tab = ['cameras', 'lanes', 'sessions'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'cameras';
    for (const link of document.querySelectorAll('[data-tab]')) {
      if (link.dataset.tab === tab) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    }
    for (const section of document.querySelectorAll('.area')) section.hidden = section.id !== tab;
    if (tab === 'sessions') loadArchives().catch(error => message('session-status', error.message, true));
  }
  window.addEventListener('hashchange', showTab);

  // ---- Cameras ----
  function slug(name) {
    const base = name.toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
      .normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'kamera';
    let candidate = base;
    for (let n = 2; cameras.some(camera => camera.id === candidate); n++) candidate = `${base}-${n}`;
    return candidate;
  }
  function renderCameraList() {
    const live = Object.fromEntries((state?.capture.cameras || []).map(camera => [camera.id, camera.connected]));
    el('camera-list').replaceChildren(...cameras.map(camera => {
      const connected = live[camera.id] ?? camera.connected;
      const lanes = camera.lane_ids.length ? `Bahnen ${camera.lane_ids.join(', ')}` : 'keine Bahn';
      const button = h('button', {type: 'button', 'data-camera': camera.id, 'aria-current': camera.id === selectedCamera ? 'true' : false},
        h('span', {}, h('strong', {text: camera.name}), h('br'), h('small', {text: `${camera.id} · ${lanes}`})),
        h('span', {class: 'dot', 'data-connected': String(connected), title: connected ? 'verbunden' : 'getrennt'}));
      return h('li', {}, button);
    }));
  }
  function renderLanePicker() {
    const owners = {};
    for (const camera of cameras) if (camera.id !== selectedCamera) for (const lane of camera.lane_ids) owners[lane] = camera.name;
    const buttons = laneIds().map(lane => h('button', {
      type: 'button', 'data-lane': lane, 'aria-pressed': String(pickedLanes.has(lane)), disabled: lane in owners,
      title: lane in owners ? `Bereits ${owners[lane]} zugeordnet` : `Bahn ${lane}`, text: String(lane)}));
    const key = buttons.map(button => button.outerHTML).join('');
    if (el('camera-lanes').dataset.key !== key) { el('camera-lanes').replaceChildren(...buttons); el('camera-lanes').dataset.key = key; }
  }
  function renderCameraLive() {
    const camera = cameras.find(item => item.id === selectedCamera);
    el('camera-live').hidden = !camera;
    if (!camera) return;
    const connected = state?.capture.cameras.find(item => item.id === camera.id)?.connected ?? camera.connected;
    el('connection').textContent = connected ? 'Kamera verbunden' : 'Kein aktuelles Kamerabild – Verbindung wird erneut versucht';
    el('connection').dataset.connected = String(connected);
    const links = camera.lane_ids.map(lane => h('a', {href: `/calibration?lane=${lane}`, text: `Bahn ${lane} kalibrieren`}));
    const key = camera.lane_ids.join(',');
    if (el('calibrations').dataset.key !== key) { el('calibrations').replaceChildren(...links); el('calibrations').dataset.key = key; }
  }
  // Fill the form only when the selection changes, never while the user types.
  function fillCameraForm() {
    const camera = cameras.find(item => item.id === selectedCamera);
    el('camera-form-title').textContent = camera ? `Kamera „${camera.name}“ bearbeiten` : 'Neue Kamera';
    el('camera-name').value = camera?.name || '';
    el('camera-id').value = camera?.id || '';
    el('camera-id').readOnly = !!camera;
    el('camera-id-hint').textContent = camera ? 'Feste Kennung; Kalibrierungen hängen daran.' :
      'Wird aus dem Namen vorgeschlagen. Kalibrierungen hängen an dieser Kennung; sie kann später nicht geändert werden.';
    el('camera-address').hidden = !camera;
    el('camera-address-value').textContent = camera?.address || '';
    el('camera-url').value = '';
    el('camera-url').required = !camera;
    el('camera-url-label').textContent = camera ? 'Neue RTSP-Adresse (optional)' : 'RTSP-Adresse';
    el('camera-url-hint').textContent = camera ? 'Nur ausfüllen, um die gespeicherte Adresse vollständig zu ersetzen.' :
      'Vollständige Adresse einschließlich Benutzer und Passwort, falls nötig. Gespeicherte Zugangsdaten werden nicht wieder angezeigt.';
    pickedLanes = new Set(camera?.lane_ids || []);
    idEdited = !!camera;
    resetRemove();
    el('remove').disabled = !camera;
    el('preview').hidden = true;
    renderLanePicker(); renderCameraList(); renderCameraLive();
  }
  async function loadCameras() {
    cameras = (await request('/api/cameras')).cameras;
    if (selectedCamera && !cameras.some(camera => camera.id === selectedCamera)) { selectedCamera = ''; fillCameraForm(); }
    renderCameraList(); renderLanePicker(); renderCameraLive();
  }
  el('camera-list').onclick = event => {
    const button = event.target.closest('[data-camera]');
    if (!button) return;
    selectedCamera = button.dataset.camera; message('status', ''); fillCameraForm();
  };
  el('new-camera').onclick = () => { selectedCamera = ''; message('status', ''); fillCameraForm(); el('camera-name').focus(); };
  el('camera-name').oninput = () => { if (!idEdited) el('camera-id').value = slug(el('camera-name').value); };
  el('camera-id').oninput = () => { idEdited = true; };
  el('camera-lanes').onclick = event => {
    const lane = Number(event.target.closest('[data-lane]')?.dataset.lane);
    if (!lane) return;
    if (pickedLanes.has(lane)) pickedLanes.delete(lane); else pickedLanes.add(lane);
    renderLanePicker();
  };
  el('camera-form').onsubmit = async event => {
    event.preventDefault();
    const form = el('camera-form');
    if (!form.checkValidity()) {
      const invalid = form.querySelector(':invalid');
      message('status', invalid === el('camera-id') ? 'Kennung: nur Buchstaben, Ziffern, - und _ (höchstens 64 Zeichen).' :
        invalid === el('camera-url') ? 'RTSP-Adresse eingeben, z. B. rtsp://192.168.95.43/1/h264major.' : 'Name eingeben.', true);
      invalid.focus();
      return;
    }
    const id = el('camera-id').value.trim();
    try {
      await request(selectedCamera ? `/api/cameras/${encodeURIComponent(selectedCamera)}` : '/api/cameras', {
        method: selectedCamera ? 'PUT' : 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id, name: el('camera-name').value.trim(), url: el('camera-url').value.trim(),
          lane_ids: [...pickedLanes].sort((a, b) => a - b)})});
      selectedCamera = id;
      await loadCameras(); fillCameraForm(); await refresh();
      message('status', 'Kamera gespeichert.');
    } catch (error) { message('status', error.message, true); }
  };
  // Two-step removal instead of a modal dialog: protects against accidental taps.
  function resetRemove() {
    clearTimeout(removeTimer);
    el('remove').removeAttribute('data-confirm');
    el('remove').textContent = 'Entfernen';
  }
  el('remove').onclick = async () => {
    if (!el('remove').hasAttribute('data-confirm')) {
      el('remove').setAttribute('data-confirm', '');
      el('remove').textContent = 'Wirklich entfernen?';
      removeTimer = setTimeout(resetRemove, 5000);
      return;
    }
    resetRemove();
    try {
      await request(`/api/cameras/${encodeURIComponent(selectedCamera)}`, {method: 'DELETE'});
      selectedCamera = ''; await loadCameras(); fillCameraForm(); await refresh();
      message('status', 'Kamera entfernt.');
    } catch (error) { message('status', error.message, true); }
  };
  setInterval(async () => {
    if (!selectedCamera || previewBusy || el('cameras').hidden) return;
    previewBusy = true;
    try {
      const response = await fetch(`/api/cameras/${encodeURIComponent(selectedCamera)}/frame`, {cache: 'no-store'});
      if (response.ok) {
        const url = URL.createObjectURL(await response.blob());
        const old = el('preview').src;
        el('preview').src = url; el('preview').hidden = false;
        if (old.startsWith('blob:')) URL.revokeObjectURL(old);
      } else el('preview').hidden = true;
    } catch { el('preview').hidden = true; } finally { previewBusy = false; }
  }, 1000);

  // ---- Lanes ----
  function laneSummary(lane) {
    const camera = cameraForLane(lane.lane_id);
    if (!camera) return {kind: 'unavailable', text: 'Nur manuell', camera: 'Keine Kamera'};
    if (lane.mode === 'manual') return {kind: 'unavailable', text: 'Automatik gesperrt', camera: camera.name};
    if (!state.capture.running) return {kind: 'fault', text: 'Erfassung gestoppt', camera: camera.name};
    if (!camera.connected) return {kind: 'fault', text: 'Kamera getrennt', camera: camera.name};
    if (state.capture.calibration_errors[lane.lane_id]) return {kind: 'fault', text: 'Kalibrierung fehlerhaft', camera: camera.name};
    const status = state.capture.lanes[lane.lane_id] || 'unavailable';
    return {kind: status, text: CAPTURE[status], camera: camera.name};
  }
  function renderLanes() {
    const tiles = Object.values(state.lanes).map(lane => {
      const summary = laneSummary(lane);
      return h('button', {type: 'button', class: 'lane-tile', 'data-lane': lane.lane_id, 'data-capture': summary.kind,
        'aria-pressed': String(lane.lane_id === selectedLane)},
        h('strong', {text: `Bahn ${lane.lane_id}`}), h('span', {text: summary.camera}), h('span', {text: summary.text}));
    });
    const key = tiles.map(tile => tile.outerHTML).join('');
    if (el('lane-grid').dataset.key !== key) { el('lane-grid').replaceChildren(...tiles); el('lane-grid').dataset.key = key; }
    renderLaneDetail();
  }
  function discs(values) {
    return h('div', {class: 'targets'}, ...values.map((value, index) =>
      h('span', {class: `disc ${value}`, role: 'img', 'aria-label': `Scheibe ${index + 1}: ${STATES[value]}`, title: STATES[value], text: value === 'unknown' ? '?' : ''})));
  }
  function renderLaneDetail() {
    const lane = selectedLane && state.lanes[String(selectedLane)];
    el('lane-detail').hidden = !lane;
    if (!lane) return;
    const summary = laneSummary(lane), camera = cameraForLane(lane.lane_id), info = calibrationInfo[lane.lane_id];
    const corrections = lane.manual_targets.map((value, index) => value === null ? '' : `Scheibe ${index + 1}: ${STATES[value]}`).filter(Boolean);
    const calibration = !camera ? 'Keine Kamera zugeordnet' : info === undefined ? 'wird geladen …' :
      !info.calibration ? 'Noch nicht kalibriert' : info.valid_for_camera === false ? 'Gehört zu einer anderen Kamera oder Adresse – neu kalibrieren' :
      `Kalibriert am ${time(info.calibration.created_at)}`;
    const content = [
      h('h3', {text: `Bahn ${lane.lane_id}`}),
      h('dl', {}, h('dt', {text: 'Kamera'}), h('dd', {text: camera ? `${camera.name} (${camera.connected ? 'verbunden' : 'getrennt'})` : 'Keine Kamera'}),
        h('dt', {text: 'Erfassung'}), h('dd', {text: summary.text}), h('dt', {text: 'Kalibrierung'}), h('dd', {text: calibration})),
      h('label', {class: 'switch'}, h('input', {type: 'checkbox', 'data-source-lane': lane.lane_id, checked: lane.mode !== 'manual', disabled: sourceBusy}),
        'Automatische Beobachtungen verwenden'),
      h('p', {class: 'hint', text: 'Manuelle Eingaben am Tablet sind immer möglich und haben Vorrang. Sperren nur bei fehlerhafter Kamera nötig.'}),
      h('p', {text: 'Automatische Zielzustände'}), discs(lane.automatic_targets),
      h('p', {text: `Manuelle Korrekturen: ${corrections.join(' · ') || 'keine'}`}),
      h('div', {class: 'link-row'}, ...(camera ? [h('a', {href: `/calibration?lane=${lane.lane_id}`, text: `Bahn ${lane.lane_id} kalibrieren`})] : []),
        h('button', {type: 'button', 'data-close': true, text: 'Schließen'})),
    ];
    const key = content.map(node => node.outerHTML).join('');
    if (el('lane-detail').dataset.key !== key) { el('lane-detail').replaceChildren(...content); el('lane-detail').dataset.key = key; }
  }
  async function loadCalibration(laneId) {
    try { calibrationInfo[laneId] = await request(`/api/lanes/${laneId}/calibration`); }
    catch (error) { calibrationInfo[laneId] = {calibration: null}; message('lane-status', error.message, true); }
    renderLaneDetail();
  }
  el('lane-grid').onclick = event => {
    const tile = event.target.closest('[data-lane]');
    if (!tile) return;
    selectedLane = Number(tile.dataset.lane); message('lane-status', '');
    delete calibrationInfo[selectedLane];
    renderLanes(); loadCalibration(selectedLane);
    el('lane-detail').scrollIntoView({block: 'nearest'});
  };
  el('lane-detail').onclick = event => {
    if (event.target.closest('[data-close]')) { selectedLane = null; renderLanes(); }
  };
  // Existing source command stays administrative; no second configuration.
  el('lane-detail').onchange = async event => {
    const id = event.target.dataset.sourceLane;
    if (!id || sourceBusy) return;
    sourceBusy = true; event.target.disabled = true;
    try {
      await request(`/api/lanes/${id}/mode`, {method: 'PUT', headers: {'Content-Type': 'application/json', 'X-Session-ID': state.session_id},
        body: JSON.stringify({lane_id: Number(id), mode: event.target.checked ? 'automatic' : 'manual',
          expected_control_revision: state.lanes[id].control_revision})});
      message('lane-status', event.target.checked ? `Bahn ${id}: automatische Beobachtungen zugelassen.` : `Bahn ${id}: automatische Beobachtungen gesperrt.`);
    } catch (error) { message('lane-status', error.message, true); }
    // Rebuild the switch from the server state, also after a rejected change.
    finally { sourceBusy = false; delete el('lane-detail').dataset.key; await refresh(); }
  };

  // ---- Sessions ----
  // The session ID binds confirmation and source settings to the displayed
  // state. A second administrator may have switched it in the meantime.
  function renderSession() {
    if (sessionBusy) return;
    if (sessionId !== state.session_id) { el('session-name').value = state.session.name; el('confirm-session').checked = false; }
    sessionId = state.session_id;
    el('current-session').textContent = `${state.session.name} · seit ${time(state.session.started_at)} · ID ${sessionId}`;
    const active = Object.values(state.lanes).filter(lane => lane.occupied_bout_id || lane.current_bout_id).map(lane => lane.lane_id);
    el('session-warning').textContent = active.length ? `Achtung: Belegte Bahnen oder offene Schießeinlagen: ${active.join(', ')}.` :
      'Keine belegten Bahnen oder offenen Schießeinlagen.';
  }
  async function loadArchives() {
    const data = await request('/api/sessions');
    const archived = data.sessions.filter(item => item.ended_at);
    el('session-archives').replaceChildren(...(archived.length ? archived.map(item =>
      h('li', {}, h('a', {href: `/api/events?session_id=${encodeURIComponent(item.session_id)}`,
        text: `${item.name} · ${time(item.started_at)} – ${time(item.ended_at)} (Journal-API)`}))) : [h('li', {text: 'Noch keine abgeschlossenen Sitzungen.'})]));
  }
  el('rename-session').onsubmit = async event => {
    event.preventDefault();
    if (sessionBusy) return;
    sessionBusy = true;
    try {
      await request('/api/sessions/current', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({expected_session_id: sessionId, name: el('session-name').value})});
      message('session-status', 'Name gespeichert.');
    } catch (error) { message('session-status', error.message, true); }
    finally { sessionBusy = false; await refresh(); }
  };
  el('start-session').onsubmit = async event => {
    event.preventDefault();
    if (sessionBusy || !el('confirm-session').checked) {
      if (!el('confirm-session').checked) message('session-status', 'Bitte den Abschluss der aktuellen Sitzung ausdrücklich bestätigen.', true);
      return;
    }
    sessionBusy = true; el('start-session-button').disabled = true;
    // crypto.randomUUID is not available everywhere in an unencrypted tablet LAN.
    const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
    try {
      await request('/api/sessions/start', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({session_id: id, expected_session_id: sessionId, name: el('new-session-name').value, confirm_active: true})});
      el('new-session-name').value = ''; el('confirm-session').checked = false;
      message('session-status', 'Neue Sitzung gestartet. Bahnen erneut vorbereiten.');
    } catch (error) { message('session-status', error.message, true); }
    finally { sessionBusy = false; el('start-session-button').disabled = false; await refresh(); await loadArchives().catch(() => {}); }
  };

  // ---- Polling: one state request keeps all areas and the server badge current ----
  async function refresh() {
    try {
      state = await request('/api/state');
      el('server').dataset.status = 'online';
      el('server').textContent = state.health === 'error' ? 'Verbunden – Störung gemeldet' : 'Server verbunden';
      if (state.health === 'error') el('server').dataset.status = 'offline';
    } catch {
      el('server').dataset.status = 'offline';
      el('server').textContent = 'Server nicht erreichbar';
      return;
    }
    // A camera change by another administrator also updates this page.
    const known = cameras.map(camera => `${camera.id}:${camera.lane_ids}`).join('|');
    const current = state.capture.cameras.map(camera => `${camera.id}:${camera.lane_ids}`).join('|');
    if (known !== current) await loadCameras().catch(error => message('status', error.message, true));
    renderCameraList(); renderLanePicker(); renderCameraLive(); renderLanes(); renderSession();
  }

  showTab();
  refresh().then(() => loadCameras()).then(fillCameraForm).catch(error => message('status', error.message, true));
  setInterval(refresh, 2000);
})();
