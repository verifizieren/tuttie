// The sections of the owner view. Each one shows part of the settings as a form (reading and
// changing the draft through editor.jsx) and, where the owner cannot change something, shows
// it as plain text with the reason. `data` is the live overview from the node.
import { Fragment } from "react";
import { chf, words } from "../lib/format.js";
import { appendTo, getIn, removeFrom, setIn, uniqueSlug } from "../lib/settings.js";
import { useEditor } from "./editor.jsx";
import { Choice, ListBox, NumberBox, RemoveButton, Row, Switch, TextBox } from "./inputs.jsx";
import { Card, Chips, Field, Fields, Table } from "./ui.jsx";

const SIZES = [["small", "Small"], ["medium", "Medium"], ["large", "Large"]];
const NEW_ROOM = { room_type: "", rate: "", available: true };
const NEW_CHARGE = { purpose: "" };
const NEW_ADD_ON = { conditions: [] };

/** The price of the room the lowest price is set for: the double, else the cheapest offered. */
function standardPrice(settings) {
  const open = (getIn(settings, "facts.rooms") || []).filter(room => room.available && room.price_chf);
  const standard = open.find(room => room.room_type === "double") || [...open].sort((a, b) => a.price_chf - b.price_chf)[0];
  return standard?.price_chf;
}

/** Lines under a table row for problems that belong to the whole row (e.g. a room listed twice). */
function RowProblem({ path, columns }) {
  const { errors } = useEditor();
  return errors[path] ? <tr className="row-problem"><td colSpan={columns}><span className="problem-text">{errors[path]}</span></td></tr> : null;
}

function EditableTable({ headers, children, empty }) {
  return (
    <table className="table editable">
      <thead>
        <tr>{headers.map(header => <th key={header}>{header}</th>)}<th /></tr>
      </thead>
      <tbody>{children}</tbody>
      {empty && <caption className="muted empty">{empty}</caption>}
    </table>
  );
}

function Overview({ data }) {
  const { settings } = useEditor();
  const rooms = getIn(settings, "facts.rooms") || [];
  const open = rooms.filter(room => room.available);
  const prices = open.map(room => room.price_chf).filter(Number.isFinite);
  const stats = [
    ["Rooms offered", open.length ? `${open.length} of ${rooms.length}` : "None"],
    ["Price from", prices.length ? chf(Math.min(...prices)) : "–"],
    ["Add-ons", (getIn(settings, "facts.add_ons") || []).length],
    ["Agent", getIn(settings, "persona.name") || "–"],
  ];
  return (
    <>
      <div className="stats">
        {stats.map(([label, value]) => (
          <div className="stat" key={label}>
            <span className="stat-value">{value}</span>
            <span className="stat-label">{label}</span>
          </div>
        ))}
      </div>
      <Card title="Verified identity" note="Issued by a trusted authority, so it cannot be edited here. Guests' agents check it before they trust you.">
        <Fields>
          <Field label="UID">{data.uid && <span className="mono">{data.uid}</span>}</Field>
          <Field label="Seals">
            <ul className="chips">
              {data.seals.map(seal => (
                <li key={seal.issuer} className={`chip seal-${seal.tier}`}>{seal.issuer}</li>
              ))}
              {!data.seals.length && <span className="muted">None: guests' agents will not trust this business</span>}
            </ul>
          </Field>
          <Field label="Allowed actions">
            <Chips items={data.capabilities.map(words)} />
          </Field>
          <Field label="Tags">
            <Chips items={data.tags} />
          </Field>
        </Fields>
      </Card>
    </>
  );
}

function Profile() {
  return (
    <>
      <Card title="About the business" note="Guests' agents read this to decide whether you fit">
        <dl className="fields">
          <Row label="Description"><TextBox path="facts.profile.about" multiline label="Description" /></Row>
          <Row label="Size"><Choice path="facts.profile.size" options={SIZES} label="Size" /></Row>
          <Row label="Number of rooms"><NumberBox path="facts.profile.rooms_total" min={1} label="Number of rooms" /></Row>
          <Row label="Chain" hint="Optional"><TextBox path="facts.profile.chain" label="Chain" /></Row>
        </dl>
      </Card>
      <Card title="Location">
        <dl className="fields">
          <Row label="Address"><TextBox path="facts.address" label="Address" /></Row>
          <Row label="Distance to Basel SBB"><NumberBox path="facts.distance_to_basel_sbb_m" suffix="m" label="Distance in metres" /></Row>
          <Row label="How to get there"><TextBox path="facts.how_to_get_there" multiline label="How to get there" /></Row>
          <Row label="Quiet"><Switch path="facts.quiet" label="Quiet" /></Row>
          <Row label="About the noise"><TextBox path="facts.quiet_note" multiline label="About the noise" /></Row>
          <Row label="Facilities"><ListBox path="facts.facilities" placeholder="Add a facility…" label="Facilities" /></Row>
        </dl>
      </Card>
    </>
  );
}

function Offers() {
  const { settings, update } = useEditor();
  const rooms = getIn(settings, "facts.rooms") || [];
  return (
    <Card title="Rooms and prices" note="Your agent never offers a price that is not listed here">
      <EditableTable headers={["Room", "Price per night", "Rate", "Status", "Note"]} empty={rooms.length ? null : "No rooms are listed yet."}>
        {rooms.map((_, i) => (
          <Fragment key={i}>
            <tr>
              <td><TextBox path={`facts.rooms.${i}.room_type`} placeholder="e.g. double" label="Room type" /></td>
              <td><NumberBox path={`facts.rooms.${i}.price_chf`} unit="CHF" min={1} label="Price per night" /></td>
              <td><TextBox path={`facts.rooms.${i}.rate`} placeholder="e.g. free cancellation" label="Rate" /></td>
              <td><Switch path={`facts.rooms.${i}.available`} onText="Offered" offText="Not offered" label="Offered" /></td>
              <td><TextBox path={`facts.rooms.${i}.note`} label="Note" /></td>
              <td><RemoveButton what="room" onClick={() => update(s => removeFrom(s, "facts.rooms", i))} /></td>
            </tr>
            <RowProblem path={`facts.rooms.${i}`} columns={6} />
          </Fragment>
        ))}
      </EditableTable>
      <button type="button" className="secondary add" onClick={() => update(s => appendTo(s, "facts.rooms", NEW_ROOM))}>Add a room</button>
    </Card>
  );
}

/** One add-on's name box. A new add-on's id follows its name (the id is what a promise to a guest
 *  refers to), but a deployed add-on keeps its id when it is renamed. */
function AddOnName({ index }) {
  const { settings, live, update, errors } = useEditor();
  const row = getIn(settings, `facts.add_ons.${index}`) || {};
  const deployedIds = (getIn(live, "facts.add_ons") || []).map(addOn => addOn.id);
  const rename = text => update(s => {
    let next = setIn(s, `facts.add_ons.${index}.item`, text === "" ? undefined : text);
    const current = getIn(next, `facts.add_ons.${index}.id`);
    if (!deployedIds.includes(current)) {
      const others = (getIn(next, "facts.add_ons") || []).filter((_, at) => at !== index).map(addOn => addOn.id);
      next = setIn(next, `facts.add_ons.${index}.id`, uniqueSlug(text, others));
    }
    return next;
  });
  const error = errors[`facts.add_ons.${index}.item`] || errors[`facts.add_ons.${index}.id`];
  return (
    <span className="control">
      <input className={error ? "input invalid" : "input"} value={row.item ?? ""} placeholder="e.g. breakfast" aria-label="Add-on"
             onChange={event => rename(event.target.value)} />
      {row.id && <span className="hint mono">{row.id}</span>}
      {error && <span className="problem-text">{error}</span>}
    </span>
  );
}

function AddOns() {
  const { settings, update } = useEditor();
  const addOns = getIn(settings, "facts.add_ons") || [];
  const charges = getIn(settings, "facts.charges") || [];
  return (
    <>
      <Card title="Add-ons" note="Extras your agent can promise to a guest, at these fixed prices">
        <EditableTable headers={["Extra", "Price", "Conditions"]} empty={addOns.length ? null : "No add-ons are listed."}>
          {addOns.map((_, i) => (
            <Fragment key={i}>
              <tr>
                <td><AddOnName index={i} /></td>
                <td><NumberBox path={`facts.add_ons.${i}.price_chf`} unit="CHF" label="Price" /></td>
                <td><ListBox path={`facts.add_ons.${i}.conditions`} placeholder="Add a condition…" label="Conditions" /></td>
                <td><RemoveButton what="add-on" onClick={() => update(s => removeFrom(s, "facts.add_ons", i))} /></td>
              </tr>
              <RowProblem path={`facts.add_ons.${i}`} columns={4} />
            </Fragment>
          ))}
        </EditableTable>
        <button type="button" className="secondary add" onClick={() => update(s => appendTo(s, "facts.add_ons", NEW_ADD_ON))}>Add an add-on</button>
      </Card>
      <Card title="Charges after booking" note="Collected once per booking, after the guest has booked">
        <EditableTable headers={["Charge", "Price", "Note"]} empty={charges.length ? null : "No charges are listed."}>
          {charges.map((_, i) => (
            <Fragment key={i}>
              <tr>
                <td><TextBox path={`facts.charges.${i}.purpose`} placeholder="e.g. city tax" label="Charge" /></td>
                <td><NumberBox path={`facts.charges.${i}.price_chf`} unit="CHF" label="Price" /></td>
                <td><TextBox path={`facts.charges.${i}.note`} label="Note" /></td>
                <td><RemoveButton what="charge" onClick={() => update(s => removeFrom(s, "facts.charges", i))} /></td>
              </tr>
              <RowProblem path={`facts.charges.${i}`} columns={4} />
            </Fragment>
          ))}
        </EditableTable>
        <button type="button" className="secondary add" onClick={() => update(s => appendTo(s, "facts.charges", NEW_CHARGE))}>Add a charge</button>
      </Card>
    </>
  );
}

// The policies every business has, with how each is edited; other policies a business already
// has are listed after them by the kind of value they hold.
const POLICIES = [
  ["dogs_allowed", "Dogs allowed", "yesno"], ["dog_fee_chf_per_night", "Dog fee per night", "chf"],
  ["children", "Children", "text"], ["check_in", "Check-in", "text"], ["late_arrival", "Late arrival", "text"],
  ["cancellation", "Cancellation", "text"],
];

function Policies() {
  const { settings } = useEditor();
  const present = Object.keys(getIn(settings, "facts.policies") || {});
  const known = POLICIES.map(([key]) => key);
  const fields = [...POLICIES, ...present.filter(key => !known.includes(key)).map(key => {
    const value = getIn(settings, `facts.policies.${key}`);
    return [key, words(key), typeof value === "boolean" ? "yesno" : typeof value === "number" ? "number" : "text"];
  })];
  return (
    <Card title="Policies" note="What your agent tells guests about stays. Leave a box empty to say nothing about it.">
      <dl className="fields">
        {fields.map(([key, label, kind]) => (
          <Row key={key} label={label}>
            {kind === "yesno" && <Switch path={`facts.policies.${key}`} label={label} />}
            {kind === "chf" && <NumberBox path={`facts.policies.${key}`} unit="CHF" label={label} />}
            {kind === "number" && <NumberBox path={`facts.policies.${key}`} label={label} />}
            {kind === "text" && <TextBox path={`facts.policies.${key}`} multiline label={label} />}
          </Row>
        ))}
      </dl>
    </Card>
  );
}

function Agent({ data }) {
  const { persona, tools } = data;
  return (
    <>
      <Card title="Your agent" note="How it speaks for you">
        <dl className="fields">
          <Row label="Name"><TextBox path="persona.name" label="Agent name" /></Row>
          <Row label="Role"><TextBox path="persona.role" label="Role" /></Row>
          <Row label="Tone"><TextBox path="persona.tone" label="Tone" /></Row>
          <Row label="Priorities"><ListBox path="persona.priorities" placeholder="Add a priority…" label="Priorities" /></Row>
          <Row label="Never" hint="Locked: protects your private limits">
            {persona.boundaries ? <Chips items={persona.boundaries} tone="warn" /> : <span className="muted">None</span>}
          </Row>
        </dl>
      </Card>
      <Card title="New requests" note="Guests post what they need on the marketplace; your agent can answer with an offer">
        <dl className="fields">
          <Row label="Respond to new postings">
            <Switch path="respond_to_postings" onText="Your agent makes offers" offText="Paused: no new offers" label="Respond to new postings" />
          </Row>
        </dl>
      </Card>
      <Card title="What it can do" note="Fixed by Tuttie; changing this needs a new seal">
        <Table
          rows={Object.entries(tools)}
          columns={[
            ["Tool", ([name]) => <span className="mono">{name}</span>],
            ["What it does", ([, tool]) => tool.description],
            ["Status", ([, tool]) => <span className={`status ${tool.status === "available" ? "on" : "off"}`}>{words(tool.status)}</span>],
          ]}
        />
      </Card>
    </>
  );
}

function Negotiation() {
  const { settings, update, set } = useEditor();
  const negotiating = Boolean(getIn(settings, "facts.negotiation"));
  const price = standardPrice(settings);
  const toggle = on => (on
    ? update(s => setIn(s, "facts.negotiation", { floor_chf: standardPrice(s), max_rounds: 3 }))
    : set("facts.negotiation", undefined));
  return (
    <Card title="Negotiation limits" note="Private: only your own agent knows these, no guest's agent ever sees them">
      <dl className="fields">
        <Row label="Negotiate prices">
          <label className="switch">
            <input type="checkbox" checked={negotiating} onChange={event => toggle(event.target.checked)} aria-label="Negotiate prices" />
            <i /> <span>{negotiating ? "Your agent may lower its prices" : "Your agent keeps its listed prices"}</span>
          </label>
        </Row>
        {negotiating && (
          <>
            <Row label="Lowest price" hint={price ? `Your standard room is CHF ${price}` : undefined}>
              <NumberBox path="facts.negotiation.floor_chf" unit="CHF" min={1} label="Lowest price" />
            </Row>
            <Row label="Rounds of bargaining"><NumberBox path="facts.negotiation.max_rounds" min={1} label="Rounds" /></Row>
          </>
        )}
      </dl>
      {negotiating && (
        <p className="muted small">
          The lowest price is for your standard double room (or your cheapest room if you have no double). Other rooms
          drop by the same share, and add-ons are never discounted. After the last round your agent's price is final.
        </p>
      )}
    </Card>
  );
}

export const SECTIONS = [
  { id: "overview", label: "Overview", component: Overview },
  { id: "profile", label: "Business profile", component: Profile },
  { id: "offers", label: "Rooms and prices", component: Offers },
  { id: "addons", label: "Add-ons and charges", component: AddOns },
  { id: "policies", label: "Policies", component: Policies },
  { id: "agent", label: "Agent", component: Agent },
  { id: "negotiation", label: "Negotiation", component: Negotiation, private: true },
];

