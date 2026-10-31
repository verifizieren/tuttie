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
