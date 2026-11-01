// atk11o: the deploy dialog's change list keys add-ons by `item`, the node keys them by `id`.
// Two add-ons with the same item text (allowed by node/settings.py) hide a price change from the owner.
import test from "node:test";
import assert from "node:assert/strict";
import { diff } from "./settings.js";

test("a changed add-on price is listed even when two add-ons share the item text", () => {
  const a = { facts: { add_ons: [{ id: "dog", item: "Pet", price_chf: 15 }, { id: "cat", item: "Pet", price_chf: 10 }] } };
  const b = { facts: { add_ons: [{ id: "dog", item: "Pet", price_chf: 0 }, { id: "cat", item: "Pet", price_chf: 10 }] } };
  assert.ok(diff(a, b).length > 0, "deploy dialog shows no change, the node deploys the dog fee drop");
});
