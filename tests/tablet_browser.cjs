// Zwei unabhängige Tablet-Profile: Bedienung, Konflikte, WLAN-Ausfall und Sprachen.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const {spawn} = require('node:child_process');
const {chromium, expect} = require(process.env.PLAYWRIGHT_MODULE || '@playwright/test');

async function startServer(directory, simulation) {
  const reservation = net.createServer();
  await new Promise((resolve, reject) => { reservation.once('error', reject); reservation.listen(0, '127.0.0.1', resolve); });
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  const args = ['-m', 'biathlon_target_vision', '--port', String(port), '--data-dir', directory];
  if (simulation) args.push('--simulation');
  const process = spawn(path.resolve('.venv/bin/python'), args);
  let log = '';
  process.stderr.on('data', data => { log += data; });
  const url = `http://127.0.0.1:${port}`;
  for (let attempt = 0; attempt < 100; attempt++) {
    try { if ((await fetch(url + '/api/state')).ok) return {process, url}; } catch {}
    if (process.exitCode !== null) throw new Error(log);
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  process.kill();
  throw new Error(`Serverstart fehlgeschlagen: ${log}`);
}

async function stop(server) {
  if (server && server.process.exitCode === null) {
    server.process.kill('SIGTERM');
    await new Promise(resolve => server.process.on('exit', resolve));
  }
}

(async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'btv-tablet-'));
  let server, normal, browser;
  const errors = [];
  try {
    server = await startServer(path.join(directory, 'simulation'), true);
    browser = await chromium.launch({headless: true});
    const firstContext = await browser.newContext({viewport: {width: 1024, height: 768}, hasTouch: true});
    const secondContext = await browser.newContext({viewport: {width: 768, height: 1024}, hasTouch: true});
    const first = await firstContext.newPage(), second = await secondContext.newPage();
    for (const page of [first, second]) {
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(server.url);
      await expect(page.locator('#connection')).toHaveAttribute('data-status', 'online');
      await expect(page.locator('.lane-card')).toHaveCount(20);
      await expect(page.locator('html')).toHaveAttribute('lang', 'en');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
    const getState = async () => (await fetch(server.url + '/api/state')).json();
    const card = (page, lane = 1) => page.locator(`#lane-${lane}`);
    const typeBib = async (page, value) => {
      await page.locator('[data-key="clear"]').click();
      for (const digit of String(value)) await page.locator(`[data-key="${digit}"]`).click();
    };
    const assign = async (page, lane, bib) => {
      await card(page, lane).locator('[data-action="bib"]').click();
      await typeBib(page, bib);
      await page.locator('#confirm-bib').click();
      await expect(page.locator('#editor')).not.toBeVisible();
    };
    const target = async (page, lane, number, value) => {
      await card(page, lane).locator(`[data-target="${number}"]`).click();
      await page.locator(`[data-target-state="${value}"]`).click();
      await expect(page.locator('#editor')).not.toBeVisible();
    };
    const action = async (page, lane, name) => {
      const button=card(page,lane).locator(`[data-action="${name}"]`);
      if (!await button.isVisible()) await card(page,lane).locator('summary').click();
      await button.click();
      if (name !== 'release') await page.locator('#confirm-action').click();
      await expect(page.locator('#editor')).not.toBeVisible();
    };

    // Sprachen und lokale Bahnauswahl wirken nicht auf den zweiten Bedienplatz.
    await first.locator('#language').selectOption('de');
    await expect(first.locator('h1')).toHaveText('Schießbahnen');
    await first.locator('#choose-lanes').click();
    await first.locator('#select-none').click();
    for (const lane of [1, 3]) await first.locator(`.lane-choices input[value="${lane}"]`).check();
    await first.locator('#apply-selection').click();
    await expect(first.locator('.lane-card')).toHaveCount(2);
    assert.deepEqual(await first.locator('.lane-card').evaluateAll(nodes => nodes.map(node => node.dataset.lane)), ['1', '3']);
    await first.reload();
    await expect(first.locator('#connection')).toHaveAttribute('data-status', 'online');
    await expect(first.locator('.lane-card')).toHaveCount(2);
    await expect(first.locator('html')).toHaveAttribute('lang', 'de');
    await expect(second.locator('.lane-card')).toHaveCount(20);
    await first.locator('#language').selectOption('cs');
    await expect(first.locator('h1')).toHaveText('Střelecké stavy');
    const dictionariesValid = await first.evaluate(() => {
      const dictionaries = window.BTV_I18N;
      const keys = Object.keys(dictionaries.en).sort();
      return ['de','cs'].every(language => JSON.stringify(Object.keys(dictionaries[language]).sort()) === JSON.stringify(keys)
        && keys.every(key => dictionaries[language][key] && JSON.stringify(dictionaries[language][key].match(/\{\w+\}/g)?.sort()) === JSON.stringify(dictionaries.en[key].match(/\{\w+\}/g)?.sort())));
    });
    assert.equal(dictionariesValid, true);
    await first.locator('#language').selectOption('en');

    // Treffer vor Startnummer, alle drei Zielzustände, anschließend Zuordnung.
    await action(first, 1, 'reset');
    await target(first, 1, 2, 'fallen');
    await target(first, 1, 5, 'unknown');
    await expect(card(second).locator('[data-target="2"]')).toHaveAttribute('data-state', 'fallen');
    await expect(card(second).locator('[data-target="5"]')).toHaveAttribute('data-state', 'unknown');
    let state = await getState();
    const oldBout = state.lanes['1'].current_bout_id;
    assert.equal(state.bouts[oldBout].bib, null);
    await assign(first, 1, 42);
    await expect(card(second).locator('.bib')).toHaveText('42');
    state = await getState();
    assert.equal(state.lanes['1'].current_bout_id, oldBout);
    assert.equal(state.bouts[oldBout].observations.length, 2);
    await assign(second, 1, 43);
    await expect(card(first).locator('.bib')).toHaveText('43');

    // Gleiche Nummer für dieselbe Einlage ist kein widersprüchlicher Entwurf.
    await card(first).locator('[data-action="bib"]').click();
    await typeBib(first, 144);
    await assign(second, 1, 144);
    await expect(card(first).locator('.bib')).toHaveText('144');
    await expect(first.locator('#confirm-bib')).toBeEnabled();
    await expect(first.locator('#review-edit')).not.toBeVisible();
    await first.locator('#close-dialog').click();
    await assign(second, 1, 43);

    // Entwürfe bleiben unterscheidbar und beeinflussen weder Belegung noch Journal.
    const beforeDrafts = (await getState()).sequence;
    await card(first).locator('[data-action="bib"]').click();
    await typeBib(first, 44);
    await expect(card(second).locator('.draft-row strong')).toHaveText('44');
    await card(second).locator('[data-action="bib"]').click();
    await typeBib(second, 45);
    await expect(first.locator('#dialog-drafts .draft-row strong')).toHaveText('45');
    await expect(second.locator('#dialog-drafts .draft-row strong')).toHaveText('44');
    const firstLabel = await first.locator('#editor-label').textContent();
    const secondLabel = await second.locator('#editor-label').textContent();
    assert.notEqual(firstLabel, secondLabel);
    await expect(first.locator('#bib-input')).toHaveValue('44');
    assert.equal((await getState()).sequence, beforeDrafts);
    assert.equal((await getState()).bouts[oldBout].bib, 43);
    await second.locator('#confirm-bib').click();
    await expect(second.locator('#editor')).not.toBeVisible();
    await expect(first.locator('#confirm-bib')).toBeDisabled();
    await expect(first.locator('#dialog-error')).toContainText('official assignment changed');
    await expect(first.locator('#bib-input')).toBeEnabled();
    await expect(first.locator('#bib-input')).toHaveValue('44');
    assert.equal((await getState()).bouts[oldBout].bib, 45);
    // Prüfung und erneute Bestätigung sind getrennt; kein erzwungenes Neuöffnen.
    await first.locator('#review-edit').click();
    await expect(first.locator('#confirm-bib')).toBeEnabled();
    assert.equal((await getState()).bouts[oldBout].bib, 45);
    await first.locator('#close-dialog').click();
    await expect(card(second).locator('.draft-row')).toHaveCount(0);
    assert.equal((await getState()).sequence, beforeDrafts + 1);

    // Derselbe Sportler darf nicht unbemerkt auf zwei Bahnen gebucht werden.
    await card(first, 3).locator('[data-action="bib"]').click();
    await typeBib(first, 45);
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#dialog-error')).toContainText('already occupies another lane');
    assert.equal((await getState()).lanes['3'].current_bout_id, null);
    await first.locator('#close-dialog').click();

    // Zweite Einlage beginnt vor Freigabe der ersten; alte Freigabe bleibt eindeutig.
    await action(first, 1, 'reset');
    await target(first, 1, 3, 'fallen');
    state = await getState();
    const nextBout = state.lanes['1'].current_bout_id;
    assert.notEqual(nextBout, oldBout);
    assert.equal(state.bouts[nextBout].bib, null);
    await expect(card(first).locator('[data-action="bib"]')).toBeDisabled();
    await action(first, 1, 'release');
    assert.equal((await getState()).lanes['1'].current_bout_id, nextBout);
    await assign(first, 1, 46);
    await expect(card(second).locator('.bib')).toHaveText('46');

    // Historische Korrektur verändert die aktuelle Belegung nicht.
    if (!await card(first).locator('.lane-options').evaluate(node=>node.open)) await card(first).locator('summary').click();
    await card(first).locator('[data-action="history"]').click();
    await first.locator(`[data-bout="${oldBout}"]`).click();
    await typeBib(first, 47);
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#editor')).not.toBeVisible();
    state = await getState();
    assert.equal(state.bouts[oldBout].bib, 47);
    assert.equal(state.bouts[nextBout].bib, 46);
    await expect(card(first).locator('.bib')).toHaveText('46');

    // Abbruch während der Eingabe: keine Offline-Buchung oder automatische Wiederholung.
    await card(first).locator('[data-action="bib"]').click();
    await typeBib(first, 48);
    await firstContext.setOffline(true);
    await expect(first.locator('#connection')).toHaveAttribute('data-status', 'offline');
    await expect(first.locator('#confirm-bib')).toBeDisabled();
    await assign(second, 1, 49);
    await firstContext.setOffline(false);
    await expect(first.locator('#connection')).toHaveAttribute('data-status', 'online');
    await expect(card(first).locator('.bib')).toHaveText('49');
    await expect(first.locator('#confirm-bib')).toBeDisabled();
    await first.locator('#close-dialog').click();
    assert.equal((await getState()).bouts[nextBout].bib, 49);

    // Unbestätigte Antwort: gespeicherte Änderung nach Neuverbindung anzeigen, nicht duplizieren.
    let intercepted = false;
    await first.route('**/api/lanes/1/bib', async route => {
      intercepted = true;
      await route.fetch();
      await route.abort('failed');
    });
    await card(first).locator('[data-action="bib"]').click();
    await typeBib(first, 50);
    const before = (await getState()).sequence;
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#notice')).toContainText('No confirmation received');
    await expect(first.locator('#connection')).toHaveAttribute('data-status', 'online');
    await expect(card(first).locator('.bib')).toHaveText('50');
    assert.equal(intercepted, true);
    assert.equal((await getState()).sequence, before + 1);
    await first.locator('#close-dialog').click();
    await first.unroute('**/api/lanes/1/bib');

    // Vollständig verspätete Eingabe nach Rückstellung braucht die konkrete Historie.
    await action(first, 3, 'reset');
    await target(first, 3, 1, 'fallen');
    const unassignedBout = (await getState()).lanes['3'].current_bout_id;
    await action(first, 3, 'reset');
    await card(first, 3).locator('[data-action="bib"]').click();
    await expect(first.locator('#dialog-context')).toContainText('Select the bout');
    await first.locator(`[data-bout="${unassignedBout}"]`).click();
    await typeBib(first, 77);
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#editor')).not.toBeVisible();
    state = await getState();
    assert.equal(state.bouts[unassignedBout].bib, 77);
    assert.equal(state.lanes['3'].occupied_bout_id, null);
    await card(first, 3).locator('[data-action="bib"]').click();
    await typeBib(first, 0);
    const beforeInvalid = (await getState()).sequence;
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#dialog-error')).toContainText('positive whole bib');
    assert.equal((await getState()).sequence, beforeInvalid);
    await typeBib(first, 78);
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#editor')).not.toBeVisible();
    await expect(card(second, 3).locator('.bib')).toHaveText('78');
    await action(first, 3, 'release');
    await expect(card(second, 3).locator('.bib')).toHaveText('Enter');

    // Eine schon offene Eingabe überlebt mehrere Treffer, auch während HTTP unterwegs ist.
    await action(second, 3, 'reset');
    await card(first, 3).locator('[data-action="bib"]').click();
    await typeBib(first, 80);
    const beforeHits = (await getState()).sequence;
    for (const number of [1, 2, 4]) {
      await target(second, 3, number, 'fallen');
      await expect(first.locator('#bib-input')).toHaveValue('80');
      await expect(first.locator('#confirm-bib')).toBeEnabled();
    }
    await expect(card(first, 3).locator('[data-target="4"]')).toHaveAttribute('data-state', 'fallen');
    const hitBout = (await getState()).lanes['3'].current_bout_id;
    await first.route('**/api/lanes/3/bib', async route => {
      await target(second, 3, 5, 'fallen');
      await route.continue();
    });
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#editor')).not.toBeVisible();
    await first.unroute('**/api/lanes/3/bib');
    state = await getState();
    assert.equal(state.sequence, beforeHits + 5);
    assert.equal(state.bouts[hitBout].bib, 80);
    assert.equal(state.bouts[hitBout].observations.length, 4);

    // Ohne Belegungskonflikt bleibt Offline-Text erhalten und wird wieder bestätigbar.
    await card(first, 3).locator('[data-action="bib"]').click();
    await typeBib(first, 81);
    await expect(card(second, 3).locator('.draft-row strong')).toHaveText('81');
    await firstContext.setOffline(true);
    await expect(first.locator('#connection')).toHaveAttribute('data-status', 'offline');
    await expect(first.locator('#confirm-bib')).toBeDisabled();
    await typeBib(first, 82);
    await expect(first.locator('#bib-input')).toHaveValue('82');
    await expect(card(second, 3).locator('.draft-row')).toHaveCount(0);
    await target(second, 3, 3, 'fallen');
    await firstContext.setOffline(false);
    await expect(first.locator('#connection')).toHaveAttribute('data-status', 'online');
    await expect(first.locator('#bib-input')).toHaveValue('82');
    await expect(first.locator('#confirm-bib')).toBeEnabled();
    assert.equal((await getState()).bouts[hitBout].bib, 80);
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#editor')).not.toBeVisible();
    await expect(card(second, 3).locator('.bib')).toHaveText('82');
    // Zieländerung während des HTTP-Transports der direkten Abreisebestätigung.
    await second.route('**/api/lanes/3/release', async route => {
      await target(first,3,1,'unknown');
      await route.continue();
    }, {times:1});
    await card(second,3).locator('[data-action="release"]').click();
    await expect(card(second,3)).toHaveAttribute('data-status','reset_required');

    // Rückstellung und nächste Einlage dürfen eine offene Eingabe nicht umleiten.
    await action(second, 3, 'reset');
    await card(first, 3).locator('[data-action="bib"]').click();
    await typeBib(first, 83);
    await target(second, 3, 1, 'fallen');
    const pendingBout = (await getState()).lanes['3'].current_bout_id;
    await action(second, 3, 'reset');
    await target(second, 3, 2, 'fallen');
    const laterBout = (await getState()).lanes['3'].current_bout_id;
    await expect(first.locator('#confirm-bib')).toBeEnabled();
    await expect(first.locator('#dialog-context')).toContainText('Completed');
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#editor')).not.toBeVisible();
    state = await getState();
    assert.equal(state.bouts[pendingBout].bib, 83);
    assert.equal(state.bouts[laterBout].bib, null);
    assert.equal(state.lanes['3'].occupied_bout_id, null);

    // Verlassen des Eingabefeldes und Schließen verwerfen nur die Entwurfsanzeige.
    await card(first, 3).locator('[data-action="bib"]').click();
    await typeBib(first, 84);
    await expect(card(second, 3).locator('.draft-row strong')).toHaveText('84');
    const beforeBlur = (await getState()).sequence;
    await first.locator('#close-dialog').focus();
    await expect(card(second, 3).locator('.draft-row')).toHaveCount(0);
    await expect(first.locator('#bib-input')).toHaveValue('84');
    await first.locator('#close-dialog').click();
    assert.equal((await getState()).sequence, beforeBlur);
    assert.equal((await getState()).bouts[laterBout].bib, null);

    // Auch Freigabe einer noch unzugeordneten Einlage ist eine echte Bedienänderung.
    await card(first, 3).locator('[data-action="bib"]').click();
    await typeBib(first, 85);
    const unoccupied = (await getState()).lanes['3'];
    const released = await fetch(server.url+'/api/lanes/3/release', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({lane_id:3,bout_id:unoccupied.current_bout_id,expected_revision:unoccupied.revision,expected_assignment_revision:unoccupied.assignment_revision})});
    assert.equal(released.status,200);
    await expect(first.locator('#confirm-bib')).toBeDisabled();
    await expect(first.locator('#bib-input')).toHaveValue('85');
    await expect(first.locator('#dialog-context')).toContainText('Completed');
    await first.locator('#review-edit').click();
    await first.locator('#confirm-bib').click();
    await expect(first.locator('#editor')).not.toBeVisible();
    assert.equal((await getState()).bouts[laterBout].bib, 85);
    assert.equal((await getState()).lanes['3'].occupied_bout_id, null);

    // Leere Auswahl ist erlaubt und bleibt gespeichert; spätere Auswahl bleibt sortiert.
    await first.locator('#choose-lanes').click();
    await first.locator('#select-none').click();
    await first.locator('#apply-selection').click();
    await expect(first.locator('.lane-card')).toHaveCount(0);
    await first.reload();
    await expect(first.locator('#connection')).toHaveAttribute('data-status', 'online');
    await expect(first.locator('.lane-card')).toHaveCount(0);
    await first.locator('#choose-lanes').click();
    await first.locator('#select-all').click();
    await first.locator('#apply-selection').click();
    await expect(first.locator('.lane-card')).toHaveCount(20);
    fs.mkdirSync('.test-artifacts', {recursive: true});
    await first.screenshot({path: '.test-artifacts/tablet-landscape.png', fullPage: true});
    await second.locator('#language').selectOption('cs');
    await second.screenshot({path: '.test-artifacts/tablet-portrait.png', fullPage: true});
    await card(second).locator('[data-action="bib"]').click();
    assert.equal(await second.evaluate(() => document.querySelector('#editor').scrollWidth > document.querySelector('#editor').clientWidth), false);
    await second.locator('#close-dialog').click();

    // Reguläre Scheibenbedienung braucht keine Simulation; deren Quelle bleibt gesperrt.
    normal = await startServer(path.join(directory, 'normal'), false);
    const normalPage = await browser.newPage();
    normalPage.on('pageerror', error => errors.push(error.message));
    await normalPage.goto(normal.url);
    await expect(normalPage.locator('#connection')).toHaveAttribute('data-status', 'online');
    await expect(normalPage.locator('#simulation-banner')).not.toBeVisible();
    await expect(normalPage.locator('button.target')).toHaveCount(100);
    await expect(normalPage.locator('.simulate-reset')).toHaveCount(0);
    const denied = await fetch(normal.url + '/api/observations', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({kind: 'reset', lane_id: 1, source: 'simulator', observed_at: new Date().toISOString()})});
    assert.equal(denied.status, 403);
    assert.equal((await (await fetch(normal.url + '/api/state')).json()).sequence, 0);
    assert.deepEqual(errors, []);
    console.log('Tablet-Browsertest erfolgreich: 2 Profile, 3 Sprachen, Auswahl, Zahlentasten, Korrektur, Historie, Freigabe, Zielsimulation, getrennte Live-Entwürfe, Treffer während Eingabe und HTTP, Rückstellung während Eingabe, Belegungskonflikte, Offline-Text, Wiederverbindung, unbestätigte Antwort, Hoch-/Querformat, Wettkampfmodus.');
  } finally {
    if (browser) await browser.close();
    await stop(server); await stop(normal);
    fs.rmSync(directory, {recursive: true, force: true});
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
