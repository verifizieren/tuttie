import test from 'node:test';
import assert from 'node:assert/strict';
import { restoreConversation } from './conversation.js';

const events = [
  { step: 1, kind: 'answer', summary: 'Quiet hotel for CHF 128', detail: {} },
  { step: 2, kind: 'answer', summary: 'Please approve the booking', detail: {} },
];
test('resuming a snapshot rebuilds each answer in its original turn', () => {
  const snapshot = { id: 'chat-1', turns: [
    { said: 'Find a hotel', answer: 'Old answer' },
    { said: 'Book it', answer: 'Old answer' },
  ], picked: ['hotel'] };
  const state = restoreConversation(events, 'chat-1', snapshot);
  assert.deepEqual(state.turns.map(t => [t.said, t.answer]), [
    ['Find a hotel', 'Quiet hotel for CHF 128'], ['Book it', 'Please approve the booking'],
  ]);
  assert.deepEqual(state.picked, ['hotel']);
});
test('a different conversation never inherits user messages, picks or signed facts', () => {
  const state = restoreConversation([], 'new-chat', { id: 'old-chat', turns: [{ said: 'Book it' }],
    picked: ['hotel'], approval: { id: 'old-approval' }, booking: { id: 'old-booking' } });
  assert.equal(state.id, 'new-chat');
  assert.deepEqual(state.turns, []);
  assert.equal(state.picked, null);
  assert.equal(state.approval, null);
  assert.equal(state.booking, null);
});
test('browser-only offers and approvals are not restored without server events', () => {
  const state = restoreConversation([], 'chat', { id: 'chat', turns: [{ said: 'Book it' }],
    hotels: { hotel: { agreed: 128 } }, approval: { id: 'stale' } });
  assert.deepEqual(state.hotels, {});
  assert.equal(state.approval, null);
});

test('a stored deck, pick or turns in the wrong shape are dropped, never crash the chat', () => {
  const cards = [{ step: 1, kind: 'marketplace', detail: { phase: 'cards', cards: [{ node_id: 'a' }, { node_id: 'b' }] } }];
  const keep = restoreConversation(cards, 'c1', { id: 'c1', turns: [], deck: { step: 1, index: 1, liked: ['a'] }, picked: ['a'] });
  assert.deepEqual(keep.deck, { step: 1, index: 1, liked: ['a'] });
  assert.deepEqual(keep.picked, ['a']);
  for (const deck of [{ step: 1, index: 1 }, { step: 1, index: -1, liked: [] }, { step: 1, index: 0.5, liked: [] },
                      { step: 1, index: 0, liked: [3] }, { step: 1, index: '1', liked: [] }, 'deck']) {
    assert.equal(restoreConversation(cards, 'c1', { id: 'c1', turns: [], deck }).deck, null, JSON.stringify(deck));
  }
  const odd = restoreConversation([], 'c1', { id: 'c1', turns: 'x', picked: 5 });
  assert.deepEqual(odd.turns, []);
  assert.equal(odd.picked, null);
  assert.deepEqual(restoreConversation([], 'c1', { id: 'c1', turns: [null, { said: 'hi' }, { said: {} }] }).turns, [{ said: 'hi' }]);
});
