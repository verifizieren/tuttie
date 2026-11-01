// The owner's settings as plain data: reading and changing them by path, telling whether a
// draft differs from what is live, and listing the differences in words for the owner.
// Paths are dotted like the node's error paths: "facts.rooms.0.price_chf".
import { chf, words } from "./format.js";

const parts = path => (Array.isArray(path) ? path : String(path).split("."));

export function getIn(value, path) {
  return parts(path).reduce((node, key) => (node === undefined || node === null ? undefined : node[key]), value);
}

/** A copy of `value` with `path` set; an `undefined` value removes the key. Missing parents are created. */
export function setIn(value, path, next) {
  const [key, ...rest] = parts(path);
  const copy = Array.isArray(value) ? [...value] : { ...(value || {}) };
  const child = rest.length ? setIn(copy[key] ?? (/^\d+$/.test(rest[0]) ? [] : {}), rest, next) : next;
  if (child === undefined) {
    if (Array.isArray(copy)) copy.splice(Number(key), 1);
    else delete copy[key];
  } else copy[key] = child;
  return copy;
}

/** Drops what means "not set" (empty text, null, empty lists and objects), so a blank box and a
 *  missing key compare equal. */
export function clean(value) {
  if (Array.isArray(value)) {
    const items = value.map(clean).filter(item => item !== undefined);
    return items.length ? items : undefined;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value).map(([key, item]) => [key, clean(item)]).filter(([, item]) => item !== undefined);
    return entries.length ? Object.fromEntries(entries) : undefined;
  }
  if (value === "" || value === null || value === undefined) return undefined;
  return value;
}

const sameJson = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
export const sameSettings = (a, b) => sameJson(sortKeys(clean(a)), sortKeys(clean(b)));

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map(key => [key, sortKeys(value[key])]));
  return value;
}

// ---- the differences, in words ----

const FIELD_LABELS = {
  about: "Description", rooms_total: "Number of rooms", distance_to_basel_sbb_m: "Distance to Basel SBB (m)",
  how_to_get_there: "How to get there", quiet_note: "About the noise", room_type: "Room", price_chf: "Price",
  floor_chf: "Lowest price", max_rounds: "Rounds", respond_to_postings: "Respond to new postings",
  rate: "Rate", item: "Extra", conditions: "Conditions", purpose: "Charge",
};
const SECTION_LABELS = {
  profile: "Profile", rooms: "Rooms", policies: "Policies", charges: "Charges", add_ons: "Add-ons",
  negotiation: "Negotiation",
};
// Lists of objects are matched by this field, so removing one row is not "everything moved".
const ROW_KEYS = { rooms: "room_type", add_ons: "id", charges: "purpose" };

const fieldLabel = key => FIELD_LABELS[key] || words(key);
const sectionLabel = key => SECTION_LABELS[key] || fieldLabel(key);
const isObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);

/** A value as the owner reads it. */
export function show(key, value) {
  if (value === undefined) return "not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return key.includes("_chf") ? chf(value) : String(value);
  if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
  return String(value);
}

function leaf(key, before, after, labels, out) {
  if (sameJson(before, after)) return;
  const kind = before === undefined ? "added" : after === undefined ? "removed" : "changed";
  out.push({ kind, label: [...labels, fieldLabel(key)].join(" › "), before: show(key, before), after: show(key, after) });
}

function walkObject(before, after, labels, out) {
  for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
    walkValue(key, before[key], after[key], labels, out);
  }
}

function walkValue(key, before, after, labels, out) {
  if (ROW_KEYS[key] && (Array.isArray(before) || Array.isArray(after))) {
    const byName = list => Object.fromEntries((list || []).map(row => [row[ROW_KEYS[key]], row]));
    const [was, now] = [byName(before), byName(after)];
    for (const name of new Set([...Object.keys(was), ...Object.keys(now)])) {
      if (!was[name]) out.push({ kind: "added", label: `${sectionLabel(key)} › ${name}`, before: "", after: "new" });
      else if (!now[name]) out.push({ kind: "removed", label: `${sectionLabel(key)} › ${name}`, before: "removed", after: "" });
      else walkObject(was[name], now[name], [...labels, sectionLabel(key), name], out);
    }
  } else if (isObject(before) || isObject(after)) {
    walkObject(before || {}, after || {}, [...labels, sectionLabel(key)], out);
  } else leaf(key, before, after, labels, out);
}

/** What differs between two settings, for the owner: [{kind, label, before, after}]. */
export function diff(before, after) {
  const [a, b] = [clean(before) || {}, clean(after) || {}];
  const out = [];
  walkObject(a.facts || {}, b.facts || {}, [], out);
  walkObject(a.persona || {}, b.persona || {}, ["Agent"], out);
  leaf("respond_to_postings", a.respond_to_postings, b.respond_to_postings, ["Agent"], out);
  return out;
}

/** A node error path such as "facts.rooms.0.price_chf" in words, using the draft to name rows. */
export function describePath(path, settings) {
  if (!path) return "";
  const [root, ...rest] = path.split(".");
  if (root === "persona") return ["Agent", ...rest.map(fieldLabel)].join(" › ");
  if (root !== "facts") return fieldLabel(root);
  const [section, index, ...field] = rest;
  if (ROW_KEYS[section] && /^\d+$/.test(index || "")) {
    const name = getIn(settings, ["facts", section, index, ROW_KEYS[section]]) || `#${Number(index) + 1}`;
    return [sectionLabel(section), name, ...field.map(fieldLabel)].join(" › ");
  }
  const rows = ["profile", "policies", "negotiation"].includes(section);
  return [rows ? sectionLabel(section) : fieldLabel(section), ...[index, ...field].filter(Boolean).map(fieldLabel)].join(" › ");
}
