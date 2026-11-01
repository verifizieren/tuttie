import test from 'node:test';
import assert from 'node:assert/strict';
import { sendGuard } from './sendGuard.js';

test('the same text is not sent twice while it is on its way (a double tap)', () => {
  const guard = sendGuard();
  assert.equal(guard.begin('Yes, book that one.'), true);
  assert.equal(guard.begin('Yes, book that one.'), false);  // second tap before the first came back
  assert.equal(guard.begin('And the weather?'), true);       // other words go through
  guard.end('Yes, book that one.');
  assert.equal(guard.begin('Yes, book that one.'), true);    // sent again later on purpose: fine
});
