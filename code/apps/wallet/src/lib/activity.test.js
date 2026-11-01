import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, choosing, cleanAnswer, deckStart, plainMarkdown, EMPTY, startTurn, withDeck } from './activity.js';
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

test('voice swipes target the current deck and never replay on resume', () => {
  const cards = {step: 10, kind: 'marketplace', detail: {phase: 'cards', cards: [{node_id: 'hotel'}]}};
  const swipe = {step: 11, kind: 'wallet', detail: {action: 'swipe', verdict: 'like', cards_step: 10}};
  const state = applyEvent(startTurn(EMPTY, 'Find a room'), cards);
  assert.deepEqual(applyEvent(state, swipe).swipes, [{id: 11, verdict: 'like'}]);
  assert.deepEqual(applyEvent({...state, picked: ['hotel']}, swipe).swipes, []);
  assert.deepEqual(applyEvent(state, {...swipe, detail: {...swipe.detail, cards_step: 9}}).swipes, []);
  assert.deepEqual(restoreConversation([cards, swipe], 'chat', null).swipes, []);
});

test('counter trails skip repeated prices and never imply an agreement', () => {
  const event = {kind: 'a2a', node_id: 'hotel', node_name: 'Hotel', detail: {payload: {type: 'counter', price_chf: 209, final: true}}};
  let state = {...EMPTY, hotels: {hotel: {name: 'Hotel', offer: {price_chf: 220}, rounds: [], agreed: null}}};
  state = applyEvent(applyEvent(state, event), event);
  assert.equal(state.turns[0].tool.text, 'Bargaining with Hotel · CHF 220 → CHF 209');
  assert.equal(state.hotels.hotel.agreed, null);
});

test('a later signed agreement updates the displayed card price', () => {
  const state = {...EMPTY, cards: [{node_id:'hotel', price_chf:220, agreed_chf:null}]};
  const next = applyEvent(state, {kind:'a2a', node_id:'hotel', node_name:'Hotel', detail:{payload:{type:'agreement', price_chf:209}}});
  assert.equal(next.cards[0].agreed_chf,209);
});

test('rapid card commands queue once each and do not replay from history', () => {
  const cards = {step:10, kind:'marketplace', detail:{phase:'cards', cards:[{node_id:'a'},{node_id:'b'}]}};
  const choice = (step, verdict) => ({step, kind:'wallet', detail:{action:'swipe',verdict,cards_step:10}});
  const events=[cards,choice(11,'like'),choice(12,'pass'),choice(12,'pass')];
  const state=events.reduce(applyEvent,EMPTY);
  assert.deepEqual(state.swipes.map(c=>c.verdict),['like','pass']);
  assert.deepEqual(restoreConversation(events,'chat',null).swipes,[]);
});

test('searching after a booking starts fresh hotel and deck state', () => {
  const previous = {...EMPTY, turns:[{answer:'Booked'}], cards:[{node_id:'hotel'}], cardsStep:10,
    swipes:[{id:11,verdict:'like'}], picked:['hotel'], booking:{id:'old'}, bookingTurn:0,
    hotels:{hotel:{name:'Hotel',offer:{price_chf:220},rounds:[{price:209}],agreed:209}}};
  const next=applyEvent(startTurn(previous,'Find another hotel'), {kind:'marketplace', detail:{phase:'posted',
    request:{request_id:'new'},invited:{hotel:{name:'Hotel',trust_tier:'gold'}}}});
  assert.equal(next.hotels.hotel.offer,null);
  assert.deepEqual(next.hotels.hotel.rounds,[]);
  assert.equal(next.hotels.hotel.agreed,null);
  assert.equal(next.booking,null);
  assert.equal(next.cardsStep,null);
  assert.deepEqual(next.swipes,[]);
  assert.equal(next.marketTurn,1);
});

test('a reload continues the deck where the user left it', () => {
  const cards = {step: 10, kind: 'marketplace', detail: {phase: 'cards', cards: [{node_id: 'a'}, {node_id: 'b'}, {node_id: 'c'}]}};
  const state = withDeck(applyEvent(startTurn(EMPTY, 'Find a room'), cards), {index: 1, liked: ['a']});
  assert.deepEqual(deckStart(state), {index: 1, liked: ['a']});
  const saved = {id: 'chat', turns: [], picked: null, deck: state.deck};
  assert.deepEqual(deckStart(restoreConversation([cards], 'chat', saved)), {index: 1, liked: ['a']});
  // Another chat's or an earlier posting's deck never applies.
  assert.equal(deckStart(restoreConversation([cards], 'other', saved)), null);
  const newer = {...cards, step: 20};
  assert.equal(deckStart(restoreConversation([cards, newer], 'chat', saved)), null);
  assert.equal(deckStart(withDeck(state, {index: 3, liked: ['a']})), null);  // nothing left to swipe
});

test('malformed events never crash the timeline', () => {
  const start = startTurn(EMPTY, 'hi');
  assert.equal(applyEvent(start, { step: 1, kind: 'answer', summary: null, detail: null }).turns[0].answer, '');
  const offer = applyEvent(start, { step: 1, kind: 'marketplace', node_id: 'h', node_name: 'H',
                                    detail: { phase: 'offer', offer: { price_chf: 100 } } });
  assert.deepEqual(offer.hotels.h.tiers, []);
  assert.deepEqual(offer.hotels.h.seals, []);
  const approval = applyEvent(start, { step: 1, kind: 'approval', status: 'pending', detail: { approval_id: 'a' } });
  assert.deepEqual(approval.approval.seals, []);
});

test('an approval that ends without a decision is not called a decline', () => {
  const pending = applyEvent(startTurn(EMPTY, 'book'), { step: 1, kind: 'approval', status: 'pending', detail: { approval_id: 'a' } });
  const ended = applyEvent(pending, { step: 2, kind: 'approval', status: 'expired', detail: { approval_id: 'a' } });
  assert.equal(ended.turns[0].tool.text, 'Approval closed');
  const declined = applyEvent(pending, { step: 2, kind: 'approval', status: 'declined', detail: { approval_id: 'a' } });
  assert.equal(declined.turns[0].tool.text, 'You declined');
});

test('citation and id notes in square brackets are not shown', () => {
  assert.equal(cleanAnswer('Booked, total CHF 128 [confirmed]. Tax paid [receipt RC-A14786]. Fine [3, 4].'),
               'Booked, total CHF 128. Tax paid. Fine.');
});

test('facts in square brackets stay, without the brackets', () => {
  assert.equal(cleanAnswer('Total CHF 128 [+ CHF 40 cleaning fee]. Booked [non-refundable].'),
               'Total CHF 128 + CHF 40 cleaning fee. Booked non-refundable.');
});

test('an "Ignored:" line is dropped even behind a bracket note', () => {
  assert.equal(cleanAnswer('Booked.\n[3] Ignored: Scam hotel says hi'), 'Booked.');
});

test('long runs of spaces are fast', () => {
  const start = performance.now();
  cleanAnswer(' '.repeat(50000) + 'x');
  assert.ok(performance.now() - start < 200);
});

test('answer notes: the same cases as the voice (code/tests/fixtures/answer_notes.json)', async () => {
  const { readFileSync } = await import('node:fs');
  const cases = JSON.parse(readFileSync(new URL('../../../../tests/fixtures/answer_notes.json', import.meta.url)));
  for (const c of cases) assert.equal(cleanAnswer(c.in), c.screen, c.in);
});

test('runs of "[" are fast', () => {
  const start = performance.now();
  cleanAnswer('['.repeat(50000));
  assert.ok(performance.now() - start < 300);
});

test('the indentation of untouched lines is kept', () => {
  assert.equal(cleanAnswer('Rooms:\n  - double CHF 180\n  - single CHF 120'), 'Rooms:\n  - double CHF 180\n  - single CHF 120');
});

test('an approval in an odd shape becomes plain text and numbers the sheet can always show', () => {
  const odd = { step: 1, kind: 'approval', status: 'pending', node_name: { x: 1 }, uid: ['CHE'], seals: [null, 'gold', { issuer: { a: 1 }, tier: 'gold', valid: 'yes' }],
                detail: { approval_id: 'a1', amount_chf: { n: 1 }, terms: { room_type: { a: 1 }, date: 'x', rate: { x: 1 } },
                          offer_mandate: { purpose: ['tax'], price_chf: 4 } } };
  const { approval } = applyEvent(startTurn(EMPTY, 'book'), odd);
  assert.deepEqual(approval, { id: 'a1', amount: '', hotel: '', summary: '', uid: null,
    seals: [{ issuer: '', tier: 'gold', valid: false }],
    offerMandate: { purpose: 'the next charge', price_chf: 4 }, terms: { room_type: '', date: 'x', rate: '' } });
  const word = applyEvent(startTurn(EMPTY, 'book'), { ...odd, seals: 'gold' });
  assert.deepEqual(word.approval.seals, []);
});

test('a normal approval keeps its amount, hotel, seals and terms', () => {
  const seals = [{ issuer: 'handelsregister-bs', tier: 'gold', valid: true }];
  const { approval } = applyEvent(startTurn(EMPTY, 'book'), { step: 1, kind: 'approval', status: 'pending', node_name: 'Rheinblick',
    uid: 'CHE-1', seals, summary: 'Book', detail: { approval_id: 'a1', amount_chf: 172, offer_mandate: null,
      terms: { room_type: 'double', date: '2026-11-14', rate: 'flexible', includes: [] } } });
  assert.deepEqual(approval, { id: 'a1', amount: 172, hotel: 'Rheinblick', summary: 'Book', seals, uid: 'CHE-1', offerMandate: null,
    terms: { room_type: 'double', date: '2026-11-14', rate: 'flexible' } });
});

test('a deck position in the wrong shape never starts the deck', () => {
  const state = { ...EMPTY, cards: [{ node_id: 'a' }, { node_id: 'b' }], cardsStep: 3 };
  assert.deepEqual(deckStart({ ...state, deck: { step: 3, index: 1, liked: ['a'] } }), { index: 1, liked: ['a'] });
  assert.equal(deckStart({ ...state, deck: { step: 3, index: 1 } }), null);
  assert.equal(deckStart({ ...state, deck: { step: 3, index: -1, liked: [] } }), null);
});

test('the note under the cards shows simple markdown as plain text', () => {
  assert.equal(plainMarkdown('I recommend Hotel 1 **strongly**'), 'I recommend Hotel 1 strongly');
  assert.equal(plainMarkdown('*Rheinblick* or _Spalenhof_, use `book`'), 'Rheinblick or Spalenhof, use book');
  assert.equal(plainMarkdown('room_type double_flex stays, 2 * 3 too'), 'room_type double_flex stays, 2 * 3 too');
  assert.equal(plainMarkdown(cleanAnswer('Take **Hotel 1** [3]')), 'Take Hotel 1');
});

test('the cards go away once a hotel is liked or a booking is under way', () => {
  const cards = { ...EMPTY, cards: [{ node_id: 'h' }] };
  assert.equal(choosing(cards), true);
  assert.equal(choosing({ ...cards, picked: ['h'] }), false);
  assert.equal(choosing({ ...cards, approval: { id: 'a' } }), false);  // booked by voice, not swiped
  assert.equal(choosing({ ...cards, booking: { id: 'BK-1' } }), false);
});
