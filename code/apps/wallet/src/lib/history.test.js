import test from 'node:test';
import assert from 'node:assert/strict';
import { resumeFailure } from './history.js';

test('an expired chat (404 or 410) gets a clear expiry message', () => {
  for (const status of [404, 410]) {
    const message = resumeFailure(Object.assign(new Error('gone'), { status }));
    assert.match(message, /expired/);
  }
});

test('a refused resume (409) shows the server reason', () => {
  const error = Object.assign(new Error('Decide the waiting approval first'), { status: 409 });
  assert.equal(resumeFailure(error), 'Decide the waiting approval first');
});

test('other failures say the chat could not be continued', () => {
  assert.match(resumeFailure(new Error('Failed to fetch')), /^Could not continue this chat: Failed to fetch/);
  assert.match(resumeFailure(undefined), /unreachable/);
});
