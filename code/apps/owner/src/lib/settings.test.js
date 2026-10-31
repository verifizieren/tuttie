// Tests for the settings helpers (run with `npm test`, Node's built-in test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { clean, describePath, diff, sameSettings, setIn } from "./settings.js";

const live = {
  facts: {
    rooms: [
      { room_type: "double", price_chf: 135, rate: "free cancellation", available: true },
      { room_type: "single", price_chf: 95, rate: "free cancellation", available: true },
    ],
    add_ons: [{ id: "breakfast", item: "breakfast", price_chf: 15, conditions: ["per night"] }],
    policies: { dogs_allowed: true, check_in: "16:00" },
    negotiation: { floor_chf: 125, max_rounds: 3 },
  },
  persona: { name: "Anna", priorities: ["quiet guests"] },
  respond_to_postings: true,
};

test("setIn changes a copy and removes a key when the value is undefined", () => {
  const next = setIn(live, "facts.rooms.0.price_chf", 150);
  assert.equal(next.facts.rooms[0].price_chf, 150);
  assert.equal(live.facts.rooms[0].price_chf, 135);
  assert.equal("note" in setIn({ a: { note: "x" } }, "a.note", undefined).a, false);
  assert.deepEqual(setIn({}, "facts.profile.about", "hi"), { facts: { profile: { about: "hi" } } });
});

test("an empty box and a missing value are the same setting", () => {
  assert.ok(sameSettings({ facts: { address: "", rooms: [], x: null } }, {}));
  assert.ok(sameSettings({ a: 1, b: 2 }, { b: 2, a: 1 }));
  assert.ok(!sameSettings(live, setIn(live, "persona.name", "Anni")));
  assert.deepEqual(clean({ a: "", b: { c: [] } }), undefined);
});

test("diff names a changed price in words", () => {
  const changes = diff(live, setIn(live, "facts.rooms.0.price_chf", 150));
  assert.deepEqual(changes, [{ kind: "changed", label: "Rooms › double › Price", before: "CHF 135", after: "CHF 150" }]);
});

test("diff reports whole rows as added or removed, not field by field", () => {
  const added = setIn(live, "facts.rooms.2", { room_type: "suite", price_chf: 200, rate: "x", available: true });
  assert.deepEqual(diff(live, added), [{ kind: "added", label: "Rooms › suite", before: "", after: "new" }]);
  assert.deepEqual(diff(added, live)[0].kind, "removed");
});

test("diff shows turning negotiation off, a policy and the postings switch", () => {
  const next = setIn(setIn(setIn(live, "facts.negotiation", undefined), "facts.policies.check_in", "15:00"), "respond_to_postings", false);
  const labels = diff(live, next).map(c => `${c.label}: ${c.before} → ${c.after}`);
  assert.deepEqual(labels.sort(), [
    "Agent › Respond to new postings: Yes → No",
    "Negotiation › Lowest price: CHF 125 → not set",
    "Negotiation › Rounds: 3 → not set",
    "Policies › Check in: 16:00 → 15:00",
  ].sort());
});

test("diff shows list values joined", () => {
  const [change] = diff(live, setIn(live, "persona.priorities", ["quiet guests", "dogs"]));
  assert.equal(change.after, "quiet guests, dogs");
});

test("a node error path reads as a place on the page", () => {
  assert.equal(describePath("facts.rooms.1.price_chf", live), "Rooms › single › Price");
  assert.equal(describePath("facts.negotiation.floor_chf", live), "Negotiation › Lowest price");
  assert.equal(describePath("persona.name", live), "Agent › Name");
  assert.equal(describePath("facts.address", live), "Address");
});
