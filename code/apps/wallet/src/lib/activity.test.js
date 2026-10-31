import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, deckStart, EMPTY, startTurn, withDeck } from './activity.js';
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
