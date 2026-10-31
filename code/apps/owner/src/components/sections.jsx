// What the owner can change, in four short blocks: rooms and prices, extras, negotiation and
// the agent. Everything else about the business stays as it is (and is still kept by a deploy).
import { words } from "../lib/format.js";
import { getIn, setIn } from "../lib/settings.js";
import { useEditor } from "./editor.jsx";
import { Line, NumberBox, Switch, TextBox } from "./inputs.jsx";

function Block({ title, note, children }) {
  return (
    <section className="block">
      <h2>{title}</h2>
      {note && <p className="note">{note}</p>}
      {children}
    </section>
  );
}

/** The price of the room the lowest price is set for: the double, else the cheapest offered. */
function standardPrice(settings) {
  const open = (getIn(settings, "facts.rooms") || []).filter(room => room.available && room.price_chf);
  const standard = open.find(room => room.room_type === "double") || [...open].sort((a, b) => a.price_chf - b.price_chf)[0];
  return standard?.price_chf;
}

function Rooms() {
  const { settings } = useEditor();
  const rooms = getIn(settings, "facts.rooms") || [];
  return (
    <Block title="Rooms" note="Price per night. Your agent never offers a price that is not listed here.">
      {rooms.map((room, i) => (
        <Line key={i} label={words(room.room_type || "room")}>
          <NumberBox path={`facts.rooms.${i}.price_chf`} unit="CHF" min={1} label={`${room.room_type} price`} />
          <Switch path={`facts.rooms.${i}.available`} onText="Offered" offText="Hidden" label={`${room.room_type} offered`} />
        </Line>
      ))}
    </Block>
  );
}

function Extras() {
  const { settings } = useEditor();
  const addOns = getIn(settings, "facts.add_ons") || [];
  if (!addOns.length) return null;
  return (
    <Block title="Extras" note="Your agent can promise these to a guest at a fixed price.">
      {addOns.map((addOn, i) => (
        <Line key={i} label={addOn.item}>
          <NumberBox path={`facts.add_ons.${i}.price_chf`} unit="CHF" label={`${addOn.item} price`} />
        </Line>
      ))}
    </Block>
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
    <Block title="Negotiation" note="Private: no guest's agent ever sees these limits.">
      <Line label="Lower the price">
        <Switch checked={negotiating} onChange={toggle} onText="Your agent may bargain" offText="Listed prices only" label="Lower the price" />
      </Line>
      {negotiating && (
        <>
          <Line label="Lowest price" hint={price ? `Standard room: CHF ${price}` : undefined}>
            <NumberBox path="facts.negotiation.floor_chf" unit="CHF" min={1} label="Lowest price" />
          </Line>
          <Line label="Rounds">
            <NumberBox path="facts.negotiation.max_rounds" min={1} label="Rounds of bargaining" />
          </Line>
        </>
      )}
    </Block>
  );
}

function Agent() {
  return (
    <Block title="Agent">
      <Line label="Name"><TextBox path="persona.name" label="Agent name" /></Line>
      <Line label="Tone"><TextBox path="persona.tone" label="Tone" /></Line>
      <Line label="New requests">
        <Switch path="respond_to_postings" onText="Makes offers" offText="Paused" label="Respond to new requests" />
      </Line>
    </Block>
  );
}

export default function Sections() {
  return (
    <>
      <Rooms />
      <Extras />
      <Negotiation />
      <Agent />
    </>
  );
}
