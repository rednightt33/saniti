/* ERRORS M405 (2026-11-08): the image holds every module its start command loads. The deployed screener-worker stopped
   at start (ERR_MODULE_NOT_FOUND: calc/flow.ts imported data/brokerAgg.ts, outside the image's COPY lines) while every
   test passed in the full repository. scripts/check_image_imports.mjs walks the imports from this service's Dockerfile
   CMD and its --import loader, as the loader resolves them, against the Dockerfile's COPY sources. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkImage } from '../../../scripts/check_image_imports.mjs';

const SERVICE = new URL('..', import.meta.url).pathname.split('/').filter(Boolean).pop();
test(`${SERVICE}: every module the start command loads is copied into the image`, () => {
  const r = checkImage(`apps/${SERVICE}/Dockerfile`);
  assert.ok(r.modules > 5, `walked ${r.modules} modules from ${r.entries.join(', ')}`);
  assert.deepEqual(r.missing, [], r.missing.map(m => `${m.file}: ${m.why}`).join('\n'));
});
