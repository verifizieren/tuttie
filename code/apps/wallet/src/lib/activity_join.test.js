// The server joins the same words sent twice (two tabs, a retype) into one turn id: the wallet's
// second local turn for those words must go, or it stays open (no answer) forever.
import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, bindTurn, EMPTY, finished, startTurn } from './activity.js';

test('a send the server joined to a running turn leaves no turn open', () => {
  let s = startTurn(EMPTY, 'Find me a hotel');
  s = startTurn(s, 'Find me a hotel');          // impatient retype while turn 1 runs
  s = bindTurn(s, 'Find me a hotel', 't1');
  s = bindTurn(s, 'Find me a hotel', 't1');     // server joined: same id
  s = applyEvent(s, { step: 1, kind: 'turn', turn: 't1', status: 'pending', summary: '', detail: { turn_id: 't1', said: 'Find me a hotel' } });
  s = applyEvent(s, { step: 2, kind: 'answer', turn: 't1', summary: 'Here are three hotels.', status: 'verified', detail: { mood: 'happy' } });
  assert.deepEqual(s.turns.filter(t => !t.answer), []);
  assert.equal(finished(s), true);
});

test('two different sends still get their own turns', () => {
  let s = startTurn(EMPTY, 'Find me a hotel');
  s = startTurn(s, 'And the weather?');
  s = bindTurn(s, 'Find me a hotel', 't1');
  s = bindTurn(s, 'And the weather?', 't2');
  assert.deepEqual(s.turns.map(t => t.id), ['t1', 't2']);
});
