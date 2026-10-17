// Echte Browserbedienung: Gesamt-ROI, Speicherung, Nachführung und Fehlermeldung.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const {spawn, spawnSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || '@playwright/test');

(async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'btv-browser-'));
  const python = path.resolve('.venv/bin/python');
  const generated = spawnSync(python, ['-c', `
import cv2, json, sys
from pathlib import Path
from tests.synthetic import scene
directory = Path(sys.argv[1])
for name, options in [('base', {'mask':10, 'perspective':1}), ('moved', {'mask':21, 'perspective':1, 'shift':(5,3)}), ('missing', {'missing':2, 'perspective':1})]:
    image, quad, _, _ = scene(**options)
    cv2.imwrite(str(directory / (name + '.png')), image)
    if name == 'base': print(json.dumps({'quad':quad, 'width':image.shape[1], 'height':image.shape[0]}))
`, directory], {encoding: 'utf8'});
  assert.equal(generated.status, 0, generated.stderr);
  const reference = JSON.parse(generated.stdout);
  const reservation = net.createServer();
  await new Promise(resolve => reservation.listen(0, '127.0.0.1', resolve));
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const server = spawn(python, ['-m', 'biathlon_target_vision', '--port', String(port), '--data-dir', directory]);
  let serverLog = '';
  server.stderr.on('data', data => { serverLog += data.toString(); });
  let browser;
  try {
    for (let i = 0; i < 100; i++) {
      try { if ((await fetch(url + '/api/state')).ok) break; } catch {}
      if (server.exitCode !== null) throw new Error(serverLog);
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({headless: true});
    const page = await browser.newPage({viewport: {width: 1100, height: 900}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url + '/calibration');
    await page.waitForFunction(() => document.querySelector('#lane').options.length === 20 && !document.querySelector('#file').disabled);
    await page.locator('#file').setInputFiles(path.join(directory, 'base.png'));
    await page.locator('#image').waitFor({state: 'visible'});
    await page.waitForFunction(() => !document.querySelector('#clear').disabled);
    const bounds = await page.locator('#image').boundingBox();
    for (const [x, y] of reference.quad) {
      await page.mouse.click(bounds.x + x * bounds.width / reference.width, bounds.y + y * bounds.height / reference.height);
    }
    await page.locator('#detect').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent.includes('erkannt und gespeichert'));
    const saved = await (await fetch(url + '/api/lanes/1/calibration')).json();
    assert.equal(saved.calibration.targets.length, 5);
    fs.mkdirSync('.test-artifacts', {recursive: true});
    await page.screenshot({path: '.test-artifacts/calibration-browser.png', fullPage: true});
    await page.reload();
    await page.waitForFunction(() => !document.querySelector('#file').disabled);
    await page.locator('#file').setInputFiles(path.join(directory, 'moved.png'));
    await page.locator('#align').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent.includes('Fünf Ziele bestätigt'));
    assert.deepEqual(await (await fetch(url + '/api/lanes/1/calibration')).json(), saved);
    await page.locator('#file').setInputFiles(path.join(directory, 'missing.png'));
    await page.locator('#detect').click();
    await page.waitForFunction(() => document.querySelector('#status').classList.contains('error'));
    assert.match(await page.locator('#status').textContent(), /fünf sichtbaren Zielen/);
    assert.deepEqual(await (await fetch(url + '/api/lanes/1/calibration')).json(), saved);
    assert.deepEqual(errors, []);
    console.log('Browserprüfung erfolgreich: ROI, fünf Zielbereiche, Wiederladen, Nachführung, Fehlerfall.');
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve => server.exitCode !== null ? resolve() : server.on('exit', resolve));
    fs.rmSync(directory, {recursive: true, force: true});
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
