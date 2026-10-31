import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, EMPTY, startTurn } from './activity.js';
import { restoreConversation } from './conversation.js';

const bye = [{ step: 1, kind: 'close', summary: 'Closing the card', detail: {} },
             { step: 2, kind: 'answer', summary: 'Bye, see you soon!', detail: {} }];

test('a goodbye is ready to close the card once Tuttie has answered', () => {
  const asked = applyEvent(startTurn(EMPTY, 'bye'), bye[0]);
  assert.equal(asked.closing, 'asked');
  assert.equal(applyEvent(asked, bye[1]).closing, 'ready');
});

test('a new message cancels the goodbye', () => {
  const ready = bye.reduce(applyEvent, startTurn(EMPTY, 'bye'));
  assert.equal(startTurn(ready, 'wait, one more thing').closing, null);
});

test('a loaded or resumed chat never closes the card by itself', () => {
  assert.equal(restoreConversation(bye, 'chat-1', null).closing, null);
});
