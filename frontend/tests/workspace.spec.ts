import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

// Explicit synthetic HTTP fixtures. These test UI behavior, never model quality.
const id = '11111111-1111-4111-8111-111111111111';
const meeting = { id, title: 'Synthetic planning fixture', filename: 'fixture.wav', glossary: 'Docker', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), stage: 'complete', duration_seconds: 60, processed_audio_seconds: 60, failed_stage: null, error: null, retryable: false, llm_completed_calls: 4, target: 'complete' };
const rawSegments = [
  { id: 's00001', start: 0, end: 30, text: 'We agreed to use dock her. <script>window.injected = true</script>' },
  { id: 's00002', start: 30, end: 60, text: 'Action item: check the logs. Alex will send the draft by Monday. Withdraw the earlier release decision.' },
];
const segments = rawSegments.map(s => ({ ...s, text: s.text.replace('dock her', 'Docker') }));
const evidence = (quote: string, segment_id = 's00002') => [{ quote, segment_id }];
const record = {
  summary: [{ text: 'Synthetic source-backed meeting summary.', evidence: evidence('Action item: check the logs.') }],
  topics: [{ title: 'Release planning', points: [{ text: 'The earlier decision was withdrawn.', evidence: evidence('Withdraw the earlier release decision.') }] }],
  decisions: [],
  tasks: [{ text: 'Check the logs.', owner: null, deadline: null, evidence: evidence('Action item: check the logs.') }, { text: 'Send the draft.', owner: 'Alex', deadline: 'Monday', evidence: evidence('Alex will send the draft by Monday.') }],
  uncertainties: ['Confirm release timing.'],
};
const refined = {
  segments,
  accepted: [{ segment_id: 's00001', start: 17, end: 25, original: 'dock her', replacement: 'Docker', reason: 'Explicit test glossary alias.' }],
  rejected: [{ edit: { segment_id: 's00002', original: 'Monday', replacement: 'Tuesday', reason: 'Explicit invalid fixture proposal.' }, rejection: 'Protected commitment change' }],
  warnings: ['Explicit synthetic audit warning.'],
};
const document = { record, revision_audit: [{ text: 'The earlier release decision was withdrawn.', evidence: evidence('Withdraw the earlier release decision.') }], warnings: [] };
const view = { meeting, raw: { segments: rawSegments, warnings: [] }, refined, document };
const health = { transcription_ready: true, conversion_ready: true, llm_ready: true, llm_error: null, limits: { upload_bytes: 209715200, audio_seconds: 7200, pending_jobs: 3 } };
const screenshots = resolve('..', '.cache', 'ui-qa');
function wav(seconds = 60) {
  const frames = seconds * 16000; const bytes = Buffer.alloc(44 + frames * 2);
  bytes.write('RIFF'); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write('WAVEfmt ', 8); bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22); bytes.writeUInt32LE(16000, 24); bytes.writeUInt32LE(32000, 28); bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34); bytes.write('data', 36); bytes.writeUInt32LE(frames * 2, 40);
  return bytes;
}
async function mock(page: Page, detail: () => unknown = () => view, library = true) {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/health') return route.fulfill({ json: health });
    if (url.pathname === '/api/meetings' && route.request().method() === 'GET') return route.fulfill({ json: { meetings: library ? [meeting] : [] } });
    if (url.pathname === `/api/meetings/${id}`) return route.fulfill({ json: detail() });
    if (url.pathname.endsWith('/audio')) {
      const bytes = wav();
      const range = route.request().headers().range?.match(/^bytes=(\d+)-(\d*)$/);
      if (range) {
        const start = Number(range[1]), end = range[2] ? Math.min(Number(range[2]), bytes.length - 1) : bytes.length - 1;
        return route.fulfill({ status: 206, contentType: 'audio/wav', headers: { 'Accept-Ranges': 'bytes', 'Content-Range': `bytes ${start}-${end}/${bytes.length}` }, body: bytes.subarray(start, end + 1) });
      }
      return route.fulfill({ contentType: 'audio/wav', headers: { 'Accept-Ranges': 'bytes' }, body: bytes });
    }
    if (url.pathname.endsWith('/export/meeting.json')) return route.fulfill({ contentType: 'application/json', headers: { 'Content-Disposition': 'attachment; filename="fixture-meeting.json"' }, json: { record } });
    return route.fulfill({ status: 404, json: { detail: 'Explicit unhandled UI fixture request' } });
  });
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}
async function accessible(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations).toEqual([]);
}

test('empty upload, validation, real form fields and ordered polling (synthetic API)', async ({ page }) => {
  let stage = 0;
  const stages = ['queued', 'refining', 'documenting', 'complete'];
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
  await mock(page, () => { const current = stages[Math.min(stage++, 3)]; return { ...view, meeting: { ...meeting, stage: current }, document: current === 'complete' ? document : null }; }, false);
  await page.route('**/api/meetings', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { meetings: [] } });
    const body = route.request().postDataBuffer()!.toString();
    expect(body).toContain('Synthetic upload'); expect(body).toContain('dock her => Docker'); expect(body).toContain('filename="fixture.wav"');
    return route.fulfill({ status: 202, json: { ...meeting, stage: 'queued' } });
  });
  await page.goto('/');
  await expect(page.getByText('Your recordings will live here.')).toBeVisible();
  await page.getByRole('button', { name: 'Create the meeting record' }).click();
  await expect(page.getByRole('alert')).toHaveText('Choose a recording first.');
  await page.getByLabel('Choose recording', { exact: true }).setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('invalid') });
  await expect(page.getByRole('alert')).toContainText('Choose a WAV');
  await page.getByLabel('Choose recording', { exact: true }).setInputFiles({ name: 'fixture.wav', mimeType: 'audio/wav', buffer: wav(1) });
  await page.getByRole('textbox', { name: 'Meeting title' }).fill('Synthetic upload');
  await page.getByText('Add terminology', { exact: false }).click();
  await page.getByLabel('Words worth getting right').fill('dock her => Docker');
  await page.getByRole('button', { name: 'Create the meeting record' }).click();
  await expect(page.getByRole('heading', { name: 'In the queue' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Refining terminology' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Writing the record' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ready for review' })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`meeting=${id}`));
  expect(errors).toEqual([]);
});

test('desktop review, null assignments, exact raw text, revisions, keyboard tabs and exports', async ({ page }) => {
  await mock(page);
  await page.goto(`/?meeting=${id}`);
  await expect(page.getByRole('heading', { name: 'Ready for review' })).toBeVisible();
  await page.getByRole('tab', { name: 'Tasks' }).click();
  await expect(page.locator('.unspecified')).toHaveCount(2);
  await expect(page.getByText('Monday', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Open source 1: Action item: check the logs.' }).click();
  await expect(page.locator('blockquote')).toHaveText('Action item: check the logs.');
  await expect.poll(() => page.locator('audio').evaluate((el: HTMLAudioElement) => el.currentTime)).toBeCloseTo(30, 1);
  await expect(page.getByRole('complementary', { name: 'Source audio and evidence' })).toBeFocused();
  await page.screenshot({ path: resolve(screenshots, 'desktop-review-fixture.png'), fullPage: true });
  await accessible(page); await noOverflow(page);
  await page.getByRole('tab', { name: 'Tasks' }).focus(); await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Transcript' })).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('button', { name: 'Raw', exact: true }).click();
  await expect(page.locator('.transcript-segment').first().locator('p')).toHaveText(rawSegments[0].text);
  expect(await page.evaluate(() => (window as Window & { injected?: boolean }).injected)).toBeUndefined();
  await page.locator('.audit summary').filter({ hasText: 'Correction history' }).click();
  await expect(page.locator('del').first()).toHaveText('dock her');
  await expect(page.locator('ins').first()).toHaveText('Docker');
  await expect(page.getByText('Rejected · Protected commitment change')).toBeVisible();
  await page.getByRole('tab', { name: 'Transcript' }).focus(); await page.keyboard.press('Home');
  await page.getByText('Revision history', { exact: false }).click();
  await expect(page.getByText('The earlier release decision was withdrawn.', { exact: true })).toBeVisible();
  await page.locator('.exports summary').click();
  await page.keyboard.press('Escape');
  await expect(page.locator('.exports')).not.toHaveAttribute('open', '');
  await expect(page.locator('.exports summary')).toBeFocused();
  await page.locator('.exports summary').click();
  // Chromium downloads bypass page.route interception. Validate the fixture's
  // link here; the opt-in genuine-server test checks downloaded canonical bytes.
  await expect(page.getByRole('link', { name: 'Meeting record · JSON' })).toHaveAttribute('href', `/api/meetings/${id}/export/meeting.json`);
  await expect(page.getByRole('link', { name: 'All artifacts · ZIP' })).toHaveAttribute('download', '');
});

test('failed stage retains transcript, resumes from explicit retry and handles a polling outage', async ({ page }) => {
  let resumed = false;
  await mock(page, () => resumed ? view : { ...view, document: null, meeting: { ...meeting, stage: 'failed', failed_stage: 'documenting', retryable: true, error: 'Explicit synthetic local model failure.' } });
  await page.route(`**/api/meetings/${id}/retry`, route => { resumed = true; return route.fulfill({ status: 202, json: { ...meeting, stage: 'queued' } }); });
  await page.goto(`/?meeting=${id}`);
  await expect(page.getByRole('alert')).toContainText('Explicit synthetic local model failure');
  await page.getByRole('tab', { name: 'Transcript' }).click();
  await expect(page.locator('.transcript-segment')).toHaveCount(2);
  await page.getByRole('button', { name: 'Retry from saved progress' }).click();
  await expect(page.getByRole('heading', { name: 'Ready for review' })).toBeVisible();
  let unavailable = true;
  await page.route(`**/api/meetings/${id}`, route => route.fulfill(unavailable ? { status: 503, json: { detail: 'Explicit synthetic service outage.' } } : { json: view }));
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('Explicit synthetic service outage');
  await expect(page.getByRole('link', { name: 'download the saved raw transcript' })).toBeVisible();
  unavailable = false; await page.getByRole('button', { name: 'Reload recording' }).click();
  await expect(page.getByRole('heading', { name: 'Ready for review' })).toBeVisible();
});

test('phone upload and review remain accessible, fit the viewport and reach source audio', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mock(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Start with a recording' })).toBeVisible();
  await page.screenshot({ path: resolve(screenshots, 'phone-upload.png'), fullPage: true });
  await accessible(page); await noOverflow(page);
  await page.getByRole('button', { name: 'Meeting library', exact: true }).click();
  await page.getByRole('link', { name: /Synthetic planning fixture/ }).click();
  await page.getByRole('tab', { name: 'Tasks' }).click();
  await page.getByRole('button', { name: 'Open source 1: Alex will send the draft by Monday.' }).click();
  await expect(page.locator('blockquote')).toHaveText('Alex will send the draft by Monday.');
  await expect(page.locator('audio')).toBeInViewport();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: resolve(screenshots, 'phone-review-fixture.png'), fullPage: true });
  await accessible(page); await noOverflow(page);
  await page.setViewportSize({ width: 360, height: 800 }); await noOverflow(page);
});

test('desktop upload visual and accessibility check', async ({ page }) => {
  await mock(page, () => view, false);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Start with a recording' })).toBeVisible();
  await page.screenshot({ path: resolve(screenshots, 'desktop-upload.png'), fullPage: true });
  await accessible(page); await noOverflow(page);
});

test('library, focus mode and partial sections preserve summary and sources', async ({ page }) => {
  await mock(page, () => ({ ...view, document: { ...document, unavailable_sections: ['tasks', 'decisions'], record: { ...record, tasks: [], decisions: [] } } }));
  await page.goto(`/?meeting=${id}`);
  await expect(page.getByText('Synthetic source-backed meeting summary.')).toBeVisible();
  await expect(page.getByText(/Partial record: tasks and decisions/)).toBeVisible();
  await page.getByRole('button', { name: 'Focus mode', exact: true }).click();
  await expect(page.getByRole('complementary', { name: 'Meeting library', exact: true })).toBeHidden();
  await page.getByRole('button', { name: 'Open source 1: Action item: check the logs.' }).click();
  await expect(page.locator('blockquote')).toHaveText('Action item: check the logs.');
  await page.getByRole('tab', { name: 'Tasks' }).click();
  await expect(page.getByText('Unavailable: task generation or validation failed.')).toBeVisible();
  await page.getByRole('tab', { name: 'Decisions' }).click();
  await expect(page.getByText('Unavailable: decision generation or validation failed.')).toBeVisible();
  await page.getByRole('button', { name: 'Exit focus mode', exact: true }).click();
  await page.getByRole('button', { name: 'Meeting library', exact: true }).click();
  await expect(page.getByRole('complementary', { name: 'Meeting library', exact: true })).toBeHidden();
  await page.getByRole('button', { name: 'Meeting library', exact: true }).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Meeting library', exact: true })).toBeFocused();
  await expect.poll(() => page.evaluate(() => document.fonts.check('14px Inter'))).toBe(true);
  await accessible(page); await noOverflow(page);
});

test('genuine saved record and browser upload through installed models', async ({ page }) => {
  test.skip(!process.env.METAWISPR_SMOKE_AUDIO || !process.env.METAWISPR_SMOKE_ID, 'Opt-in real local pipeline compatibility check; needs installed models and authored audio.');
  test.setTimeout(240000);
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(`/?meeting=${process.env.METAWISPR_SMOKE_ID}`);
  await expect(page.getByRole('heading', { name: 'Ready for review' })).toBeVisible();
  await page.getByRole('tab', { name: 'Tasks' }).click();
  await expect(page.getByText('Maya', { exact: true })).toBeVisible();
  await expect(page.getByText('Friday', { exact: true })).toBeVisible();
  await page.screenshot({ path: resolve(screenshots, 'desktop-genuine-record.png'), fullPage: true });
  await accessible(page);
  await page.getByRole('button', { name: 'New recording' }).click();
  await page.getByLabel('Choose recording', { exact: true }).setInputFiles(process.env.METAWISPR_SMOKE_AUDIO!);
  await page.getByRole('textbox', { name: 'Meeting title' }).fill('Synthetic browser compatibility check');
  await page.getByText('Add terminology', { exact: false }).click();
  await page.getByLabel('Words worth getting right').fill('Docker');
  await page.getByRole('button', { name: 'Create the meeting record' }).click();
  await expect(page.getByRole('heading', { name: 'Ready for review' })).toBeVisible({ timeout: 180000 });
  const created = new URL(page.url()).searchParams.get('meeting')!;
  const result = await (await page.request.get(`/api/meetings/${created}`)).json();
  expect(result.meeting.stage).toBe('complete');
  expect(result.raw.model.runtime).not.toBe('test-double');
  expect(result.refined.calls[0].model.tag).toBe('qwen3.5:4b');
  expect(result.document.calls[0].model).toEqual(result.refined.calls[0].model);
  expect(result.document.record.decisions).toHaveLength(1);
  expect(result.document.record.tasks).toHaveLength(1);
  expect(result.document.record.tasks[0].owner).toBe('Maya');
  expect(result.document.record.tasks[0].deadline).toBe('by Friday');
  await page.locator('.exports summary').click();
  const downloaded = page.waitForEvent('download'); await page.getByRole('link', { name: 'Meeting record · JSON' }).click();
  const download = await downloaded;
  await expect(page.locator('.exports')).not.toHaveAttribute('open', '');
  expect(JSON.parse(await readFile((await download.path())!, 'utf-8')).record).toEqual(result.document.record);
  await page.getByRole('tab', { name: 'Decisions' }).click();
  await page.getByRole('button', { name: 'Open source 1: We agreed to use Docker for the release.' }).click();
  await expect(page.locator('blockquote')).toHaveText('We agreed to use Docker for the release.');
  await expect.poll(() => page.locator('audio').evaluate((el: HTMLAudioElement) => el.readyState)).toBeGreaterThan(0);
  await page.screenshot({ path: resolve(screenshots, 'desktop-genuine-browser-upload.png'), fullPage: true });
  console.log(`Genuine browser-created meeting: ${created}`);
  expect(errors).toEqual([]);
});

test('saved pipeline record plays source audio and downloads canonical artifacts without inference', async ({ page }) => {
  const savedId = process.env.METAWISPR_REVIEW_ID;
  test.skip(!savedId, 'Opt-in read-only check of an existing pipeline record.');
  const result = await (await page.request.get(`/api/meetings/${savedId}`)).json();
  await page.goto(`/?meeting=${savedId}`);
  await expect(page.getByRole('heading', { name: 'Ready for review' })).toBeVisible();
  await expect(page.getByText(result.document.record.summary[0].text, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: /^Open source/ }).first().click();
  const supporting = result.document.record.summary[0].evidence[0];
  await expect(page.locator('blockquote')).toHaveText(supporting.quote);
  const segment = (result.refined?.segments ?? result.raw.segments).find((s: { id: string }) => s.id === supporting.segment_id);
  await expect.poll(() => page.locator('audio').evaluate((el: HTMLAudioElement) => el.currentTime)).toBeCloseTo(segment.start, 1);
  await accessible(page); await noOverflow(page);
  await page.screenshot({ path: resolve(screenshots, `saved-${savedId}.png`), fullPage: true });
  for (const format of ['meeting.md', 'meeting.json', 'bundle.zip', 'provenance.json', 'refined.txt', 'refined.json', 'edits.json', 'raw.txt', 'raw.json']) {
    await page.locator('.exports summary').click();
    const pending = page.waitForEvent('download');
    await page.locator(`.export-menu a[href$="/${format}"]`).click();
    const download = await pending;
    expect(await download.failure()).toBeNull();
    const bytes = await readFile((await download.path())!);
    expect(bytes.length).toBeGreaterThan(0);
    if (format === 'meeting.json') expect(JSON.parse(bytes.toString()).record).toEqual(result.document.record);
    if (format === 'bundle.zip') expect(bytes.subarray(0, 2).toString()).toBe('PK');
  }
  if (result.document.unavailable_sections?.length) {
    await expect(page.getByRole('status').filter({ hasText: 'Partial record:' })).toBeVisible();
    await page.getByRole('tab', { name: 'Tasks' }).click();
    await expect(page.getByText('Unavailable: task generation or validation failed.')).toBeVisible();
  }
});
