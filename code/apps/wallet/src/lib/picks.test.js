import test from 'node:test';
import assert from 'node:assert/strict';
import { bookingRequest } from './picks.js';

const guesthouse = { name: 'Gästehaus am Rhein', node_id: 'ch.basel.gaestehaus-am-rhein', price_chf: 135, agreed_chf: 128 };
const rheinblick = { name: 'Hotel Rheinblick', node_id: 'ch.basel.hotel-rheinblick', price_chf: 220, agreed_chf: null };

test('the cheapest liked deal is booked, at its agreed price', () => {
  const { best, text, shown } = bookingRequest([rheinblick, guesthouse]);
  assert.equal(best, guesthouse);
  assert.match(text, /^Book Gästehaus am Rhein \(ch\.basel\.gaestehaus-am-rhein\) at the agreed price\./);
  assert.equal(shown, 'Book Gästehaus am Rhein');
});

test('the other liked hotels are named with their prices for after a decline', () => {
  const { text } = bookingRequest([guesthouse, rheinblick]);
  assert.match(text, /If I decline it, I also liked: Hotel Rheinblick \(ch\.basel\.hotel-rheinblick\) at CHF 220\.$/);
});

test('a single liked hotel names no others', () => {
  assert.doesNotMatch(bookingRequest([rheinblick]).text, /also liked/);
});
