// Shared page frame: header with server clock and connection state, footer with the
// installed version and navigation. Page scripts keep their own connection logic and
// report its state through BTVShell.connection(); a page without one (calibration)
// uses the periodic time synchronisation as reachability check.
(() => {
  const SYNC_INTERVAL = 15000, STALE_AFTER = 40000, MAX_ROUND_TRIP = 2000;
  // BTV is used at German and Czech venues; both follow Central European Time.
  const TIME_ZONE = 'Europe/Berlin';
  const PAGES = [['tablet', '/', 'navOperator'], ['monitor', '/monitor', 'navMonitor'],
    ['admin', '/admin', 'navAdmin'], ['calibration', '/calibration', 'navCalibration']];
  const format = new Intl.DateTimeFormat('de-DE', {timeZone: TIME_ZONE, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'});
  const text = key => {
    const all = window.BTV_I18N || {};
    return (all[document.documentElement.lang] || all.de || {})[key] || key;
  };

  const header = document.createElement('header');
  header.className = 'shell-header';
  header.innerHTML = '<span class="shell-brand"><span class="shell-brand-long">BIATHLON TARGET VISION</span><span class="shell-brand-short">BTV</span></span>'
    + '<div class="shell-state"><span id="clock" class="shell-clock" role="timer" data-synced="false">--:--:--</span>'
    + '<span id="connection" role="status" data-status="connecting"></span></div>';
  const footer = document.createElement('footer');
  footer.className = 'shell-footer';
  document.body.prepend(header);
  document.body.append(footer);
  const clock = header.querySelector('#clock'), connectionLabel = header.querySelector('#connection');

  let build = null, renderedFooter = '';
  function renderFooter() {
    const version = build ? `BTV v${build.version}${build.commit ? ` · ${build.commit}` : ''}` : 'BTV';
    const key = version + document.documentElement.lang;
    if (key === renderedFooter) return;
    renderedFooter = key;
    const nav = document.createElement('nav');
    nav.setAttribute('aria-label', text('navigation'));
    for (const [page, href, label] of PAGES) {
      const link = document.createElement('a');
      link.href = href;
      link.textContent = text(label);
      if (page === document.body.dataset.page) link.setAttribute('aria-current', 'page');
      nav.append(link);
    }
    const versionLabel = document.createElement('span');
    versionLabel.textContent = version;
    footer.replaceChildren(versionLabel, nav);
  }

  // Connection: a page that reports its state owns the label; otherwise the sync does.
  let connection = 'connecting', customText = null, owned = false;
  const DEFAULT_TEXT = {online: 'connected', connecting: 'connecting', fault: 'connectionFault', offline: 'disconnected'};
  function setConnection(state, label = null) {
    const reconnected = state === 'online' && connection !== 'online';
    connection = state;
    customText = label;
    connectionLabel.dataset.status = state;
    connectionLabel.textContent = label || text(DEFAULT_TEXT[state]);
    if (reconnected) sync();
    tick();
  }

  // Clock: server time from /api/health, counted on with the monotonic performance
  // clock, so a wrong or changed browser clock does not matter. The server stamps the
  // time somewhere during the request; assuming the middle limits the error to half
  // the round trip. Slow answers are not used. The display shows whole seconds only.
  let reference = null, lastSync = -Infinity, lastAttemptFailed = false, syncing = false, timer = null;
  async function sync() {
    if (syncing) return;
    syncing = true;
    const start = performance.now();
    try {
      const response = await fetch('/api/health', {cache: 'no-store'});
      const end = performance.now();
      const data = await response.json();
      const serverTime = Date.parse(data.server_time);
      lastAttemptFailed = !Number.isFinite(serverTime) || end - start > MAX_ROUND_TRIP;
      if (!lastAttemptFailed) {
        reference = {server: serverTime + (end - start) / 2, at: end};
        lastSync = end;
      }
      build = {version: data.version, commit: data.commit};
      renderFooter();
      if (!owned) setConnection(data.status === 'ok' ? 'online' : 'fault');
    } catch {
      lastAttemptFailed = true;
      if (!owned) setConnection('offline');
    } finally {
      syncing = false;
      tick();
    }
  }
  function tick() {
    clearTimeout(timer);
    if (!reference) {
      timer = setTimeout(tick, 1000);
      return;
    }
    const now = reference.server + performance.now() - reference.at;
    const synced = connection !== 'offline' && !lastAttemptFailed && performance.now() - lastSync < STALE_AFTER;
    clock.textContent = format.format(now);
    clock.dataset.synced = String(synced);
    clock.title = text(synced ? 'clockSynced' : 'clockUnsynced');
    // Wake shortly after the next full server second instead of drifting.
    timer = setTimeout(tick, 1000 - (now % 1000) + 20);
  }

  // The tablet switches its language at runtime; follow it in footer and default label.
  let language = document.documentElement.lang;
  new MutationObserver(() => {
    if (document.documentElement.lang === language) return;
    language = document.documentElement.lang;
    renderFooter();
    if (!customText) setConnection(connection);
    tick();
  }).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});

  window.BTVShell = {
    connection(state, label) {
      owned = true;
      if (state !== connection || (label || null) !== customText) setConnection(state, label);
    },
  };
  window.addEventListener('online', sync);
  window.addEventListener('offline', sync);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) sync(); });
  setInterval(sync, SYNC_INTERVAL);
  renderFooter();
  setConnection('connecting');
  sync();
})();
