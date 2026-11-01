import test from 'node:test';
import assert from 'node:assert/strict';
import { catchUp, linkStatus, parseFrame, retryDelay } from './stream.js';

const timeline = n => Array.from({ length: n }, (_, i) => ({ step: i + 1, kind: 'context' }));

test('after a dropped stream only the missed events are applied', () => {
  const plan = catchUp(timeline(5), 'c1', 'c1', 3);
  assert.equal(plan.reload, false);
  assert.deepEqual(plan.missed.map(e => e.step), [4, 5]);
  assert.deepEqual(catchUp(timeline(3), 'c1', 'c1', 3).missed, []);
});

test('another conversation, a first load or a reset timeline is loaded instead', () => {
  assert.equal(catchUp(timeline(5), 'c2', 'c1', 3).reload, true);   // another tab started a new chat
  assert.equal(catchUp(timeline(5), 'c1', null, 0).reload, true);   // nothing loaded yet
  assert.equal(catchUp(timeline(2), 'c1', 'c1', 3).reload, true);   // reset or server restart
});

test('reconnecting backs off to 10 s and says so under the eyes', () => {
  assert.deepEqual([0, 1, 2, 3, 10].map(retryDelay), [500, 1000, 2000, 4000, 10000]);
  assert.equal(linkStatus('live'), '');
  assert.equal(linkStatus('reconnecting'), 'Reconnecting…');
  assert.match(linkStatus('offline'), /lost/);
});

test('a broken stream frame is ignored, not thrown', () => {
  assert.deepEqual(parseFrame('{"step":1,"kind":"answer"}'), { step: 1, kind: 'answer' });
  for (const bad of ['{oops', '', 'null', '5', '"x"', '[1]']) assert.equal(parseFrame(bad), null, bad);
});
