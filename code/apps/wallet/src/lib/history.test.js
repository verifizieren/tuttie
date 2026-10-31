import test from 'node:test';
import assert from 'node:assert/strict';
import { resumeFailure, startsFresh, viewedChat } from './history.js';

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

test('the keyboard continues only the past chat open in the history', () => {
  const entries = [{ id: 'old-1' }, { id: 'old-2' }];
  assert.equal(viewedChat(entries, 'old-2', 'now'), entries[1]);
  assert.equal(viewedChat(entries, null, 'now'), null);         // the list: type into the current chat
  assert.equal(viewedChat(entries, 'old-1', 'old-1'), null);    // already the chat on screen
  assert.equal(viewedChat(entries, 'gone', 'now'), null);       // no longer in the history
});

test('reopening Tuttie starts fresh only after a finished chat', () => {
  const done = { turns: [{ said: 'hi', answer: 'Hello' }], answer: 'Hello', approval: null, cards: null, picked: null };
  assert.equal(startsFresh(done), true);
  assert.equal(startsFresh({ ...done, turns: [] }), false);                                         // nothing yet
  assert.equal(startsFresh({ ...done, turns: [...done.turns, { said: 'and?' }] }), false);           // still working
  assert.equal(startsFresh({ ...done, approval: { id: 'a1' } }), false);                             // waiting for the user
  assert.equal(startsFresh({ ...done, cards: [{ node_id: 'h' }] }), false);                          // cards to swipe
  assert.equal(startsFresh({ ...done, cards: [{ node_id: 'h' }], picked: ['h'] }), true);            // swiped and answered
});
