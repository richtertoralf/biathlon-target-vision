// Offizieller Zustand vom Server, flüchtige Entwürfe getrennt je WebSocket-Verbindung.
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const dialog = $('editor');
  let storageWarning = false;
  function readPreference(key, fallback) {
    try { const raw = localStorage.getItem(key); return raw === null ? fallback : JSON.parse(raw); }
    catch { storageWarning = true; return fallback; }
  }
  function savePreference(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); }
    catch { notify('storageUnavailable', true); }
  }
  let language = readPreference('btv.language', 'en');
  if (!Object.hasOwn(window.BTV_I18N, language)) language = 'en';
  let selection = readPreference('btv.lanes', null);
  if (!Array.isArray(selection) || !selection.every(id => Number.isInteger(id) && id > 0)) selection = null;
  let state = null, connected = false, busy = false, edit = null;
  let socket = null, retryTimer = null, retryDelay = 500, lastMessage = 0, notice = null;
  let drafts = [], editorId = null;

  const t = (key, values = {}) => window.BTV_I18N[language][key].replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ''));
  const escape = value => String(value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
  const boutsFor = laneId => Object.values(state.bouts).filter(bout => bout.lane_id === laneId).sort((a, b) => a.started_sequence - b.started_sequence);
  const boutName = bout => t('bout', {n: boutsFor(bout.lane_id).findIndex(item => item.bout_id === bout.bout_id) + 1});
  const targetSymbol = value => ({standing: '●', fallen: '✓', unknown: '?'})[value];
  // randomUUID ist auf Tablets über unverschlüsseltes LAN nicht überall verfügbar.
  function eventId() {
    return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
  }

  function notify(key, error = false) {
    notice = {key, error};
    $('notice').hidden = false;
    $('notice').textContent = t(key);
    $('notice').classList.toggle('error', error);
  }

  function clearDraft() {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type: 'draft_clear'}));
  }

  function sendDraft() {
    if (!connected || busy || edit?.action !== 'bib' || socket?.readyState !== WebSocket.OPEN) return;
    const input = $('bib-input');
    if (!input || !/^\d{0,15}$/.test(input.value)) { clearDraft(); return; }
    socket.send(JSON.stringify({type: 'draft', lane_id: edit.laneId, bout_id: edit.boutId, value: input.value}));
  }

  function draftsHTML(laneId) {
    const visible = drafts.filter(draft => draft.lane_id === laneId && draft.editor_id !== editorId);
    if (!visible.length) return '';
    return `<div class="draft-list"><h3>${t('drafts')}</h3>${visible.map(draft => {
      const bout = state.bouts[draft.bout_id];
      return `<p class="draft-row" data-editor="${draft.editor_id}">${t('tablet', {n: draft.editor_id})} · ${escape(bout ? boutName(bout) : t('newBout'))}: <strong>${escape(draft.value || t('typing'))}</strong></p>`;
    }).join('')}</div>`;
  }

  function renderDrafts() {
    for (const card of $('lanes').children) {
      const container = card.querySelector('.lane-drafts');
      const content = draftsHTML(Number(card.dataset.lane));
      if (container && container.innerHTML !== content) container.innerHTML = content;
    }
    $('dialog-drafts').innerHTML = edit?.laneId ? draftsHTML(edit.laneId) : '';
  }

  function render() {
    document.documentElement.lang = language;
    $('language').value = language;
    document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
    $('language').setAttribute('aria-label', t('language'));
    $('lanes').setAttribute('aria-label', t('overview'));
    document.querySelector('.legend').setAttribute('aria-label', [t('standing'), t('fallen'), t('unknown')].join(', '));
    $('connection').textContent = t(connected ? 'connected' : 'disconnected');
    $('connection').dataset.status = connected ? 'online' : 'offline';
    $('editor-label').textContent = editorId === null ? '' : t('ownTablet', {n: editorId});
    $('offline-banner').hidden = connected;
    $('simulation-banner').hidden = !state?.simulation;
    $('choose-lanes').disabled = !state;
    if (notice) notify(notice.key, notice.error);
    if (!state) return;
    const lanes = Object.values(state.lanes);
    const shown = lanes.filter(lane => selection === null || selection.includes(lane.lane_id));
    $('summary').textContent = t('summary', {shown: shown.length, total: lanes.length, occupied: shown.filter(lane => lane.occupied_bout_id).length});
    $('empty').hidden = shown.length > 0;
    const visibleIds = new Set(shown.map(lane => `lane-${lane.lane_id}`));
    for (const card of [...$('lanes').children]) if (!visibleIds.has(card.id)) card.remove();
    shown.forEach((lane, index) => {
      renderLane(lane);
      const card = $(`lane-${lane.lane_id}`);
      if ($('lanes').children[index] !== card) $('lanes').insertBefore(card, $('lanes').children[index] || null);
    });
    renderDrafts();
  }

  function renderLane(lane) {
    const current = state.bouts[lane.current_bout_id];
    const occupied = state.bouts[lane.occupied_bout_id];
    const chosen = current || occupied;
    const previous = occupied && lane.occupied_bout_id !== lane.current_bout_id;
    const badge = previous ? 'awaitingRelease' : occupied ? 'occupied' : current ? 'unassigned' : 'free';
    const disabled = !connected || busy ? 'disabled' : '';
    const button = (action, label, classes = '', extra = '') => `<button class="${classes}" data-action="${action}" ${disabled} ${extra}>${escape(label)}</button>`;
    const targets = lane.targets.map((value, index) => {
      const label = `${t('target', {n: index + 1})}: ${t(value)}`;
      const manual = lane.manual_targets[index] !== null;
      const automatic = lane.automatic_targets[index];
      const detail = lane.mode === 'manual' ? t('manualValue') : `${t('autoValue')}: ${t(automatic)}${manual ? ` · ${t('manualValue')}` : ''}`;
      const content = `<span class="disc ${value}" aria-hidden="true">${targetSymbol(value)}</span><span>${index + 1}</span>`;
      if (lane.mode !== 'automatic' || manual) {
        return `<div class="target-control ${manual ? 'overridden' : ''}" data-target-control="${index + 1}">
          ${lane.mode === 'automatic' ? `<span class="target" data-state="${value}" role="img" aria-label="${escape(label)}">${content}</span>` :
          `<button class="target" data-action="manual-target" data-target="${index + 1}" data-state="${value}" aria-label="${escape(label)}" ${disabled}>${content}</button>`}
          <small class="source-detail" data-automatic-state="${automatic}">${escape(detail)}</small>
          ${lane.mode === 'manual' ? '' : manual ? button('override-release', t('returnAuto'), 'return-auto', `data-target="${index + 1}"`) : `<span class="auto-label">${t('autoValue')}</span>`}
          ${lane.mode === 'automatic' ? '' : button('manual-unknown', '?', 'set-unknown', `data-target="${index + 1}" aria-label="${escape(t('setUnknown', {n: index + 1}))}"`)}
        </div>`;
      }
      return state.simulation
        ? `<button class="target" data-action="target" data-target="${index + 1}" data-state="${value}" aria-label="${escape(label)}" ${disabled}>${content}</button>`
        : `<span class="target" data-state="${value}" role="img" aria-label="${escape(label)}">${content}</span>`;
    }).join('');
    let context = current ? `${boutName(current)} · ${t('active')}${current.bib === null ? ` · ${t('noBib')}` : ''}` : t('noBout');
    if (previous) context += ` · ${t('previousOccupied', {bib: occupied.bib})}`;
    const content = `<div class="lane-heading"><h2>${t('lane', {n: lane.lane_id})}</h2><span class="badge">${t(badge)}</span></div>
      <div class="bib-line"><span>${t('bib')}</span><strong class="bib">${escape(occupied?.bib ?? '—')}</strong></div>
      <p class="bout-line">${escape(context)}</p>
      <div class="lane-drafts"></div>
      <label class="mode-label">${t('mode')} <select class="lane-mode" aria-label="${escape(t('mode'))}" ${disabled}>${['manual','automatic','mixed'].map(mode => `<option value="${mode}" ${lane.mode === mode ? 'selected' : ''}>${t(mode)}</option>`).join('')}</select></label>
      <p class="capture-status">${escape(captureStatus(lane))}</p>
      <div class="targets">${targets}</div>
      ${lane.mode === 'automatic' ? '' : `<p class="target-help">${t('targetHelp')}</p>`}
      <div class="card-actions">${button('bib', t(chosen?.bib != null ? 'correctBib' : 'enterBib'), 'primary', previous && current ? 'disabled' : '')}
      ${button('release', t('release'), 'release', occupied || current ? '' : 'disabled')}</div>
      ${button('history', t('history', {n: boutsFor(lane.lane_id).length}), 'history')}
      ${lane.mode !== 'automatic' ? button('manual-reset', t('confirmReset'), 'simulate-reset') : state.simulation ? button('reset', t('reset'), 'simulate-reset') : ''}`;
    let card = $(`lane-${lane.lane_id}`);
    if (!card) {
      card = document.createElement('article');
      card.id = `lane-${lane.lane_id}`;
      card.dataset.lane = lane.lane_id;
      $('lanes').append(card);
    }
    card.className = `lane-card ${previous || (current && !occupied) ? 'attention' : occupied ? 'occupied' : ''}`;
    // Unveränderte Karten behalten Fokus und Touch-Ziel auch bei anderen Bahnen.
    if (card._content !== content) { card.innerHTML = content; card._content = content; }
  }

  function captureStatus(lane) {
    if (lane.mode === 'manual') return t('manualSource');
    const camera = state.capture?.cameras.find(item => item.lane_ids.includes(lane.lane_id));
    if (!camera) return t('noCamera');
    if (!camera.connected) return t('cameraOffline');
    return `${camera.name} · ${t(lane.automatic_targets.includes('unknown') ? 'cameraUncertain' : 'cameraOnline')}`;
  }

  function invalidate(key) {
    if (!edit || edit.action === 'selection') return;
    edit.stale = true;
    edit.error = key;
    $('dialog-error').hidden = false;
    $('dialog-error').textContent = t(key);
    $('review-edit').hidden = false;
    $('review-edit').disabled = !connected || busy;
    if (edit.action === 'bib') updateBibControls();
    else $('dialog-body').querySelectorAll('button, input').forEach(node => { node.disabled = true; });
  }

  function bibContext() {
    const bout = state.bouts[edit.boutId];
    return `${bout ? `${boutName(bout)} · ${t(bout.closed ? 'closed' : 'active')}` : t('newBout')} · ${t('officialBib', {bib: bout?.bib ?? '—'})}`;
  }

  function updateBibControls() {
    if (edit?.action !== 'bib' || !$('bib-input')) return;
    $('bib-input').disabled = busy;
    document.querySelectorAll('.keypad button').forEach(button => { button.disabled = busy; });
    $('confirm-bib').disabled = !connected || busy || edit.stale;
    $('review-edit').hidden = !edit.stale;
    $('review-edit').disabled = !connected || busy;
    $('dialog-context').textContent = bibContext();
    if (!connected) {
      $('dialog-error').hidden = false;
      $('dialog-error').textContent = t('inputOffline');
    } else {
      $('dialog-error').hidden = !edit.error;
      if (edit.error) $('dialog-error').textContent = t(edit.error);
    }
  }

  function reconcileBib() {
    const lane = state.lanes[String(edit.laneId)];
    if (!lane) { invalidate('assignmentConflict'); return; }
    // Bei Eingabebeginn ohne Einlage gehört der Entwurf zur ersten danach
    // begonnenen Einlage, selbst wenn inzwischen zurückgestellt wurde.
    if (!edit.boutId) {
      const first = boutsFor(edit.laneId).find(bout => bout.started_sequence > edit.startSequence);
      if (first) edit.boutId = first.bout_id;
    }
    const bout = state.bouts[edit.boutId];
    const historical = bout?.closed && lane.occupied_bout_id !== edit.boutId;
    const released = bout?.close_reason === 'release' && edit.baseCloseReason !== 'release';
    // Zwei Bediener, die dieselbe Nummer derselben Einlage zuordnen, widersprechen
    // sich nicht. Die bestätigte Zuordnung darf als neuer Ausgangspunkt dienen.
    if (!edit.stale && !released && bout?.bib != null && bout.bib !== edit.baseBib
      && bout.bib === Number($('bib-input').value)
      && (edit.baseOccupancy !== edit.boutId || lane.occupied_bout_id === edit.boutId)
      && (historical || lane.occupied_bout_id === edit.boutId)) {
      edit.baseBib = bout.bib;
      edit.baseOccupancy = lane.occupied_bout_id;
    }
    const occupancyChanged = lane.occupied_bout_id !== edit.baseOccupancy
      && (!historical || edit.baseOccupancy === edit.boutId);
    if ((bout?.bib ?? null) !== edit.baseBib || occupancyChanged || released) {
      invalidate('assignmentConflict');
    }
    if (!edit.stale) {
      edit.revision = lane.revision;
      edit.assignmentRevision = lane.assignment_revision;
    }
    updateBibControls();
  }

  function acceptState(value, freshConnection = false) {
    if (value.type && value.type !== 'state') return;
    // Eine verspätete HTTP-Antwort darf einen neueren WebSocket-Stand nie ersetzen.
    if (!freshConnection && state && value.sequence < state.sequence) return;
    const changed = !state || value.sequence !== state.sequence || value.simulation !== state.simulation || !connected
      || JSON.stringify(value.capture) !== JSON.stringify(state?.capture);
    state = value;
    if (value.editor_id !== undefined) editorId = value.editor_id;
    if (value.drafts !== undefined) drafts = value.drafts;
    if (freshConnection) connected = true;
    if (edit?.action === 'bib') reconcileBib();
    else if (edit?.action === 'release') {
      const lane = state.lanes[String(edit.laneId)];
      if (lane.occupied_bout_id !== edit.baseOccupancy || state.bouts[edit.boutId]?.bib !== edit.baseBib
        || ![lane.occupied_bout_id, lane.current_bout_id].includes(edit.boutId)) invalidate('assignmentConflict');
      else if (!edit.stale) { edit.revision = lane.revision; edit.assignmentRevision = lane.assignment_revision; }
    } else if (edit?.action === 'manual-reset') {
      if (state.lanes[String(edit.laneId)].control_revision !== edit.controlRevision) invalidate('stale');
    } else if (edit?.action === 'history' && changed) openHistory(edit.laneId);
    else if (edit?.laneId && edit.action !== 'history' && state.lanes[String(edit.laneId)]?.revision !== edit.revision) invalidate('stale');
    $('review-edit').disabled = !connected || busy;
    if (changed || freshConnection) render();
    else renderDrafts();
  }

  function disconnect() {
    connected = false;
    drafts = [];
    if (edit?.action === 'bib') updateBibControls();
    else invalidate('lostDuringEdit');
    render();
  }

  function connect() {
    clearTimeout(retryTimer);
    if (socket) { socket.onclose = null; socket.close(); }
    disconnect();
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
    socket = ws;
    let first = true;
    lastMessage = performance.now();
    ws.onmessage = event => {
      if (socket !== ws) return;
      try {
        const value = JSON.parse(event.data);
        if (value.type !== 'state') return;
        lastMessage = performance.now();
        retryDelay = 500;
        acceptState(value, first);
        first = false;
      } catch { ws.close(); }
    };
    ws.onerror = () => ws.close();
    ws.onclose = () => {
      if (socket !== ws) return;
      disconnect();
      retryTimer = setTimeout(connect, retryDelay);
      retryDelay = Math.min(5000, retryDelay * 2);
    };
  }
  setInterval(() => {
    if (socket && performance.now() - lastMessage > 12000) connect();
  }, 1000);
  setInterval(() => {
    if (edit?.action === 'bib' && $('bib-form')?.contains(document.activeElement)) sendDraft();
  }, 5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) connect(); });
  window.addEventListener('online', connect);
  window.addEventListener('offline', () => { disconnect(); socket?.close(); });
  window.addEventListener('pageshow', event => { if (event.persisted) connect(); });

  function openDialog(action, laneId, title, context) {
    clearDraft();
    edit = {action, laneId, revision: laneId ? state.lanes[String(laneId)].revision : null, stale: false};
    $('dialog-title').textContent = title;
    $('dialog-context').textContent = context;
    $('dialog-error').hidden = true;
    $('review-edit').hidden = true;
    $('dialog-body').replaceChildren();
    if (!dialog.open) dialog.showModal();
    renderDrafts();
  }
  function closeDialog() { if (!busy) dialog.close(); }
  $('close-dialog').onclick = closeDialog;
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => {
    if (!dialog.open) { clearDraft(); edit = null; $('dialog-drafts').replaceChildren(); }
  });
  $('review-edit').onclick = () => {
    if (!connected || busy || !edit) return;
    if (edit.action === 'target') { openTarget(edit.laneId, edit.targetId); return; }
    if (edit.action === 'reset' || edit.action === 'release') { openConfirmation(edit.action, edit.laneId); return; }
    if (edit.action === 'history') { openHistory(edit.laneId); return; }
    if (edit.action === 'manual-reset') { dialog.close(); return; }
    if (edit.action !== 'bib') return;
    const lane = state.lanes[String(edit.laneId)];
    edit.baseBib = state.bouts[edit.boutId]?.bib ?? null;
    edit.baseCloseReason = state.bouts[edit.boutId]?.close_reason ?? null;
    edit.baseOccupancy = lane.occupied_bout_id;
    edit.assignmentRevision = lane.assignment_revision;
    edit.revision = lane.revision;
    edit.stale = false;
    edit.error = null;
    updateBibControls();
    $('bib-input').focus(); sendDraft();
  };

  function openBib(laneId, boutId = null) {
    if (!connected || busy) return;
    const bout = boutId ? state.bouts[boutId] : null;
    openDialog('bib', laneId, t('lane', {n: laneId}), `${bout ? boutName(bout) : t('newBout')} · ${t(bout?.bib != null ? 'correctBib' : 'enterBib')}`);
    edit.boutId = boutId;
    edit.startSequence = state.sequence;
    edit.baseBib = bout?.bib ?? null;
    edit.baseCloseReason = bout?.close_reason ?? null;
    edit.baseOccupancy = state.lanes[String(laneId)].occupied_bout_id;
    edit.assignmentRevision = state.lanes[String(laneId)].assignment_revision;
    $('dialog-body').innerHTML = `<form id="bib-form" class="bib-editor">
      <label><span class="sr-only">${t('bib')}</span><input id="bib-input" class="bib-input" type="text" inputmode="none" autocomplete="off" maxlength="15" value="${escape(bout?.bib ?? '')}"></label>
      <div class="keypad">${[1,2,3,4,5,6,7,8,9,'clear',0,'back'].map(key => `<button type="button" data-key="${key}" aria-label="${key === 'back' ? t('backspace') : key === 'clear' ? t('clear') : key}">${key === 'back' ? '⌫' : key === 'clear' ? 'C' : key}</button>`).join('')}</div>
      <button id="confirm-bib" class="primary wide" type="submit">${t('confirm')}</button><p class="draft-help">${t('draftHelp')}</p></form>`;
    const input = $('bib-input');
    input.focus(); input.select();
    updateBibControls(); sendDraft();
    input.addEventListener('input', sendDraft);
    $('bib-form').addEventListener('focusin', sendDraft);
    $('bib-form').addEventListener('focusout', event => {
      if (!$('bib-form').contains(event.relatedTarget)) clearDraft();
    });
    $('bib-form').addEventListener('click', event => {
      const key = event.target.closest('[data-key]')?.dataset.key;
      if (key === undefined || busy) return;
      if (key === 'clear') input.value = '';
      else if (key === 'back') input.value = input.value.slice(0, -1);
      else {
        const start = input.selectionStart ?? input.value.length;
        const end = input.selectionEnd ?? start;
        input.value = (input.value.slice(0, start) + key + input.value.slice(end)).slice(0, 15);
        input.setSelectionRange(Math.min(start + 1, input.value.length), Math.min(start + 1, input.value.length));
      }
      sendDraft();
    });
    $('bib-form').onsubmit = event => {
      event.preventDefault();
      const raw = input.value.trim();
      if (!/^\d{1,15}$/.test(raw) || Number(raw) <= 0) {
        edit.error = 'invalidBib';
        $('dialog-error').hidden = false; $('dialog-error').textContent = t('invalidBib'); return;
      }
      submit(`/api/lanes/${laneId}/bib`, 'PUT', {bib: Number(raw), bout_id: edit.boutId,
        bout_after_sequence: edit.boutId ? null : edit.startSequence,
        expected_revision: edit.revision, expected_assignment_revision: edit.assignmentRevision});
    };
  }

  function openHistory(laneId) {
    openDialog('history', laneId, t('lane', {n: laneId}), t('selectBout'));
    const bouts = boutsFor(laneId).reverse();
    $('dialog-body').innerHTML = bouts.length ? bouts.map(bout => `<div class="bout-row"><div><strong>${escape(boutName(bout))} · ${t(bout.closed ? 'closed' : 'active')}</strong><p>${bout.bib == null ? t('noBib') : `${t('bib')} ${escape(bout.bib)}`}</p></div><button data-bout="${escape(bout.bout_id)}">${t('edit')}</button></div>`).join('') : `<p>${t('noHistory')}</p>`;
    $('dialog-body').onclick = event => {
      const id = event.target.closest('[data-bout]')?.dataset.bout;
      if (id && !edit.stale && connected) openBib(laneId, id);
    };
  }

  function openConfirmation(action, laneId) {
    const lane = state.lanes[String(laneId)];
    const bout = state.bouts[lane.occupied_bout_id || lane.current_bout_id];
    if (action === 'release' && !bout) { dialog.close(); return; }
    openDialog(action, laneId, t('lane', {n: laneId}), action === 'reset' ? t('resetHelp') : t('releaseHelp', {bout: boutName(bout), bib: bout.bib ?? '—'}));
    edit.boutId = bout?.bout_id;
    edit.baseBib = bout?.bib;
    edit.baseOccupancy = lane.occupied_bout_id;
    edit.assignmentRevision = lane.assignment_revision;
    $('dialog-body').innerHTML = `<button id="confirm-action" class="${action === 'reset' ? 'simulate-reset' : 'primary'} wide">${t(action === 'reset' ? 'reset' : 'release')}</button>`;
    $('confirm-action').onclick = () => action === 'reset' ? simulate(laneId, null, null) : submit(`/api/lanes/${laneId}/release`, 'POST', {
      bout_id: bout.bout_id, expected_revision: edit.revision, expected_assignment_revision: edit.assignmentRevision});
  }

  function openTarget(laneId, targetId) {
    if (!state.simulation) return;
    openDialog('target', laneId, t('simulate', {target: `${t('lane', {n: laneId})} · ${t('target', {n: targetId})}`}), t('simulationHint'));
    edit.targetId = targetId;
    $('dialog-body').innerHTML = `<div class="choices">${['standing','fallen','unknown'].map(value => `<button data-target-state="${value}"><span class="disc ${value}" aria-hidden="true">${targetSymbol(value)}</span> ${t(value)}</button>`).join('')}</div>`;
    $('dialog-body').onclick = event => {
      const value = event.target.closest('[data-target-state]')?.dataset.targetState;
      if (value) simulate(laneId, targetId, value);
    };
  }

  function simulate(laneId, targetId, value) {
    if (!state.simulation) return;
    const lane = state.lanes[String(laneId)];
    // Simulationszeit bleibt auch bei unterschiedlichen Tablet-Uhren aufsteigend.
    const time = Math.max(Date.now(), (Date.parse(lane.last_observed_at) || 0) + 1);
    const body = {kind: targetId ? 'target' : 'reset', source: 'simulator', observed_at: new Date(time).toISOString()};
    if (targetId) Object.assign(body, {target_id: targetId, state: value});
    submit('/api/observations', 'POST', body, {'X-Lane-Revision': String(edit.revision)});
  }

  async function submit(url, method, fields, headers = {}) {
    if (!connected || busy || !edit || edit.stale) return;
    const context = edit;
    clearDraft();
    busy = true; render();
    $('close-dialog').disabled = true;
    $('dialog-body').querySelectorAll('button, input').forEach(node => { node.disabled = true; });
    try {
      const response = await fetch(url, {method, headers: {'Content-Type': 'application/json', ...headers},
        body: JSON.stringify({event_id: eventId(), lane_id: context.laneId, ...fields}), signal: AbortSignal.timeout(8000)});
      const result = await response.json();
      if (!response.ok) {
        const messages = {
          'Startnummer belegt bereits eine andere Bahn.': 'duplicateBib',
          'Vorherige Belegung zuerst ausdrücklich freigeben.': 'previousRelease',
          'Frühere Einlage ohne Startnummer vorhanden. Schießeinlage ausdrücklich auswählen.': 'chooseExplicit',
        };
        const key = messages[result.detail] || ({409: 'conflict', 403: 'simulationDisabled', 503: 'storageError'})[response.status] || 'invalidRequest';
        // Bei einem Revisionsrennen entscheidet der neue Zustand, ob die
        // betroffene Einlage tatsächlich widersprüchlich geändert wurde.
        if (context.action === 'bib' && result.detail === 'Bahn wurde zwischenzeitlich geändert. Zustand neu laden.') context.error = key;
        else invalidate(key);
        notify(key, true);
        // Nach einer Ablehnung ausschließlich den Zustand erneuern, nie den Befehl.
        const fresh = await fetch('/api/state', {cache: 'no-store', signal: AbortSignal.timeout(5000)});
        if (!fresh.ok) throw new Error('state unavailable');
        acceptState(await fresh.json());
      } else {
        acceptState(result.state);
        dialog.close();
        notify('saved');
      }
    } catch {
      notify('uncertain', true);
      connect();
    } finally {
      busy = false;
      $('close-dialog').disabled = false;
      $('review-edit').disabled = !connected;
      render();
      if (edit?.action === 'bib') updateBibControls();
    }
  }

  async function control(laneId, endpoint, fields = {}, method = 'POST') {
    if (!connected || busy) return;
    const revision = state.lanes[String(laneId)].control_revision;
    busy = true; render();
    try {
      const response = await fetch(`/api/lanes/${laneId}/${endpoint}`, {method,
        headers: {'Content-Type': 'application/json'}, signal: AbortSignal.timeout(8000),
        body: JSON.stringify({event_id: eventId(), lane_id: laneId,
          expected_control_revision: revision, ...fields})});
      const result = await response.json();
      if (response.ok) { acceptState(result.state); notify('saved'); }
      else {
        notify(response.status === 409 ? 'conflict' : response.status === 503 ? 'storageError' : 'invalidRequest', true);
        const fresh = await fetch('/api/state', {cache: 'no-store', signal: AbortSignal.timeout(5000)});
        if (!fresh.ok) throw new Error('state unavailable');
        acceptState(await fresh.json());
      }
    } catch { notify('uncertain', true); connect(); }
    finally { busy = false; render(); }
  }

  $('lanes').onchange = event => {
    if (!event.target.matches('.lane-mode')) return;
    control(Number(event.target.closest('[data-lane]').dataset.lane), 'mode', {mode: event.target.value}, 'PUT');
  };

  $('lanes').onclick = event => {
    const button = event.target.closest('button[data-action]');
    if (!button || button.disabled || !connected || busy) return;
    const laneId = Number(button.closest('[data-lane]').dataset.lane);
    const lane = state.lanes[String(laneId)];
    $('dialog-body').onclick = null;
    if (['manual-target','manual-unknown'].includes(button.dataset.action)) {
      const targetId = Number(button.dataset.target);
      control(laneId, 'manual-target', {target_id: targetId, state: button.dataset.action === 'manual-unknown' ? 'unknown' : lane.targets[targetId - 1] === 'fallen' ? 'standing' : 'fallen'});
    } else if (button.dataset.action === 'override-release') {
      control(laneId, 'override-release', {target_id: Number(button.dataset.target)});
    } else if (button.dataset.action === 'manual-reset') {
      openDialog('manual-reset', laneId, t('confirmReset'), t('resetHelp'));
      edit.controlRevision = lane.control_revision;
      $('dialog-body').innerHTML = `<button id="confirm-action" class="primary wide">${t('confirm')}</button>`;
      $('confirm-action').onclick = async () => {
        if (edit.stale) return;
        dialog.close();
        await control(laneId, 'reset');
      };
    } else if (button.dataset.action === 'bib') {
      const boutId = lane.current_bout_id || lane.occupied_bout_id;
      if (!boutId && boutsFor(laneId).some(bout => bout.bib === null)) openHistory(laneId);
      else openBib(laneId, boutId);
    } else if (button.dataset.action === 'history') openHistory(laneId);
    else if (button.dataset.action === 'target') openTarget(laneId, Number(button.dataset.target));
    else openConfirmation(button.dataset.action, laneId);
  };

  $('choose-lanes').onclick = () => {
    if (!state || busy) return;
    openDialog('selection', null, t('chooseLanes'), t('selectionHelp'));
    $('dialog-body').innerHTML = `<div class="selection-actions"><button id="select-all">${t('all')}</button><button id="select-none">${t('none')}</button></div>
      <div class="lane-choices">${Object.values(state.lanes).map(lane => `<label><input type="checkbox" value="${lane.lane_id}" ${selection === null || selection.includes(lane.lane_id) ? 'checked' : ''}>${t('lane', {n: lane.lane_id})}</label>`).join('')}</div>
      <button id="apply-selection" class="primary wide">${t('applySelection')}</button>`;
    const checkboxes = () => [...$('dialog-body').querySelectorAll('input')];
    $('select-all').onclick = () => checkboxes().forEach(input => { input.checked = true; });
    $('select-none').onclick = () => checkboxes().forEach(input => { input.checked = false; });
    $('apply-selection').onclick = () => {
      selection = checkboxes().filter(input => input.checked).map(input => Number(input.value));
      if (selection.length === Object.keys(state.lanes).length) selection = null;
      savePreference('btv.lanes', selection);
      dialog.close(); render();
    };
  };
  $('language').onchange = () => { language = $('language').value; savePreference('btv.language', language); render(); };
  render();
  if (storageWarning) notify('storageUnavailable', true);
  connect();
})();
