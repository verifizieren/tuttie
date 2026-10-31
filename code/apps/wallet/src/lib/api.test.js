import test from 'node:test';
import assert from 'node:assert/strict';
import { errorText, UNREACHABLE } from './api.js';

test("the server's own reason is shown as it is", () => {
  assert.equal(errorText(409, { detail: 'Decide the waiting approval first' }), 'Decide the waiting approval first');
});

test('raw failures become plain sentences', () => {
  const list = errorText(422, { detail: [{ loc: ['body', 'message'], msg: 'Field required' }] });
  assert.doesNotMatch(list, /object|HTTP|422/);
  assert.doesNotMatch(errorText(500, {}), /HTTP|500|failed/);
  assert.equal(errorText(undefined, undefined), UNREACHABLE);
});
