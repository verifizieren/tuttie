import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, bindTurn, dropTurn, EMPTY, startTurn } from './activity.js';
import { restoreConversation } from './conversation.js';

const opened = (step, turn, said, source = 'text') =>
  ({ step, turn, kind: 'turn', status: 'pending', summary: said, detail: { turn_id: turn, said, source } });
const answer = (step, turn, summary) => ({ step, turn, kind: 'answer', summary, detail: {} });
const booked = (step, turn, id) => ({ step, turn, kind: 'a2t', seals: [], detail: { payload: {
  tool: 'book', status: 'confirmed', booking_id: id, hotel: 'Hotel', total_chf: 128, date: '2026-11-14', room_type: 'double' } } });
const posted = (step, turn) => ({ step, turn, kind: 'marketplace', detail: { phase: 'posted', request: { request_id: `r${step}` },
  invited: { hotel: { name: 'Hotel', trust_tier: 'gold' } } } });

test('a typed message binds to the server turn instead of adding a second one', () => {
  const state = applyEvent(startTurn(EMPTY, 'Find a hotel'), opened(1, 't1', 'Find a hotel'));
  assert.deepEqual(state.turns.map(t => [t.id, t.said]), [['t1', 'Find a hotel']]);
  assert.equal(applyEvent(state, opened(1, 't1', 'Find a hotel')).turns.length, 1);
});

test('a spoken request is its own turn and never overwrites the previous answer', () => {
  const events = [opened(1, 't1', 'Hi'), answer(2, 't1', 'Hello!'),
                  opened(3, 't2', 'Find a hotel', 'voice'), answer(4, 't2', 'Found three')];
  const state = events.reduce(applyEvent, EMPTY);
  assert.deepEqual(state.turns.map(t => [t.said, t.answer, t.source]),
                   [['Hi', 'Hello!', 'text'], ['Find a hotel', 'Found three', 'voice']]);
  assert.equal(state.answer, 'Found three');
});

test('a late answer lands in its own turn and does not replace the newer one', () => {
  const events = [opened(1, 't1', 'First'), opened(2, 't2', 'Second', 'voice'),
                  answer(3, 't2', 'Second answer'), answer(4, 't1', 'First answer')];
  const state = events.reduce(applyEvent, EMPTY);
  assert.deepEqual(state.turns.map(t => t.answer), ['First answer', 'Second answer']);
  assert.equal(state.answer, 'Second answer');
});

test('a booking stays in its turn when a later request searches again', () => {
  const events = [opened(1, 't1', 'Book it'), booked(2, 't1', 'BK-1'), answer(3, 't1', 'Booked'),
                  opened(4, 't2', 'Find another'), posted(5, 't2')];
  const state = events.reduce(applyEvent, EMPTY);
  assert.equal(state.booking, null);
  assert.equal(state.turns[0].booking.id, 'BK-1');
  assert.equal(state.turns[0].answer, 'Booked');
  assert.equal(state.marketTurn, 1);
});

test('restoring from the server timeline rebuilds turns, answers and bookings without a snapshot', () => {
  const events = [opened(1, 't1', 'Book it'), booked(2, 't1', 'BK-1'), answer(3, 't1', 'Booked'),
                  opened(4, 't2', 'Thanks', 'voice'), answer(5, 't2', 'You are welcome')];
  const stale = { id: 'chat', turns: [{ said: 'something else' }] };
  const state = restoreConversation(events, 'chat', stale);
  assert.deepEqual(state.turns.map(t => [t.id, t.said, t.answer]),
                   [['t1', 'Book it', 'Booked'], ['t2', 'Thanks', 'You are welcome']]);
  assert.equal(state.turns[0].booking.id, 'BK-1');
});

test('a charge paid after the booking shows on the booking in its turn', () => {
  const paid = { step: 3, turn: 't1', kind: 'payment', detail: { payload: { status: 'paid', purpose: 'city tax', amount_chf: 4 } } };
  const state = [opened(1, 't1', 'Book it'), booked(2, 't1', 'BK-1'), paid].reduce(applyEvent, EMPTY);
  assert.equal(state.turns[0].booking.payments[0].amount, 4);
  assert.equal(state.booking.payments.length, 1);
});

test('a message that failed to send is dropped, so the next request gets its answer and Tuttie settles', () => {
  let state = { ...EMPTY, phase: 'done', answer: 'Hello!' };
  state = startTurn(state, 'Find a hotel');
  state = dropTurn(state, 'Find a hotel');
  assert.equal(state.turns.length, 0);
  assert.equal(state.phase, 'done');
  state = startTurn(state, 'Find a hotel');
  state = bindTurn(state, 'Find a hotel', 't1');
  state = [opened(1, 't1', 'Find a hotel'), answer(2, 't1', 'Found three')].reduce(applyEvent, state);
  assert.deepEqual(state.turns.map(t => [t.id, t.answer]), [['t1', 'Found three']]);
  assert.equal(state.phase, 'done');
  assert.equal(state.answer, 'Found three');
});

test('the /chat turn id binds the message even when its "turn" event never arrives', () => {
  let state = startTurn(startTurn(EMPTY, 'Hi'), 'Hi');
  state = bindTurn(state, 'Hi', 't2');
  assert.deepEqual(state.turns.map(t => t.id), [undefined, 't2']);  // the newest unsent copy
  state = applyEvent(state, answer(5, 't2', 'Hello again'));
  assert.equal(state.turns[1].answer, 'Hello again');
  // The same id again means the server joined a second send of these words to t2: its unsent
  // copy goes (it would stay open forever), and t2 is never bound twice.
  const joined = bindTurn(state, 'Hi', 't2');
  assert.deepEqual(joined.turns.map(t => t.id), ['t2']);
  assert.equal(bindTurn(joined, 'Hi', 't2'), joined);
});
