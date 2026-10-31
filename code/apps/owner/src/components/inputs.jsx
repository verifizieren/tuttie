// Form inputs that read and write the settings by path (see editor.jsx). Each draws only the
// control (and its problem); `Row` adds the label for the card layouts.
import { useState } from "react";
import { useEditor, useField } from "./editor.jsx";

const Problem = ({ error }) => (error ? <span className="problem-text">{error}</span> : null);

/** A label next to an input, like a read-only `Field`. */
export function Row({ label, hint, children }) {
  return (
    <div className="field">
      <dt>{label}{hint && <span className="hint">{hint}</span>}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function TextBox({ path, multiline, placeholder, label }) {
  const { set } = useEditor();
  const { value, error } = useField(path);
  const props = {
    className: error ? "input invalid" : "input", value: value ?? "", placeholder, "aria-label": label || path,
    onChange: event => set(path, event.target.value === "" ? undefined : event.target.value),
  };
  return (
    <span className="control">
      {multiline ? <textarea rows={3} {...props} /> : <input type="text" {...props} />}
      <Problem error={error} />
    </span>
  );
}

/** A whole number; `unit` goes before it (CHF), `suffix` after it (m). */
export function NumberBox({ path, unit, suffix, label, min = 0 }) {
  const { set } = useEditor();
  const { value, error } = useField(path);
  return (
    <span className="control narrow">
      <span className="with-unit">
        {unit && <span className="unit">{unit}</span>}
        <input type="number" min={min} step={1} className={error ? "input invalid" : "input"} value={value ?? ""}
               aria-label={label || path}
               onChange={event => set(path, event.target.value === "" ? undefined : Number(event.target.value))} />
        {suffix && <span className="unit">{suffix}</span>}
      </span>
      <Problem error={error} />
    </span>
  );
}

export function Switch({ path, label, onText = "Yes", offText = "No" }) {
  const { set } = useEditor();
  const { value, error } = useField(path);
  return (
    <span className="control">
      <label className="switch">
        <input type="checkbox" checked={Boolean(value)} onChange={event => set(path, event.target.checked)} aria-label={label || path} />
        <i /> <span>{value ? onText : offText}</span>
      </label>
      <Problem error={error} />
    </span>
  );
}

export function Choice({ path, options, label }) {
  const { set } = useEditor();
  const { value, error } = useField(path);
  return (
    <span className="control narrow">
      <select className={error ? "input invalid" : "input"} value={value ?? ""} aria-label={label || path}
              onChange={event => set(path, event.target.value || undefined)}>
        <option value="">Choose…</option>
        {options.map(([id, text]) => <option key={id} value={id}>{text}</option>)}
      </select>
      <Problem error={error} />
    </span>
  );
}

/** A list of short texts shown as chips: remove with ×, add by typing and pressing Enter. */
export function ListBox({ path, placeholder = "Add…", tone, label }) {
  const { set } = useEditor();
  const { value, error } = useField(path);
  const [typed, setTyped] = useState("");
  const items = value || [];
  const add = () => {
    const text = typed.trim();
    if (text) set(path, [...items, text]);
    setTyped("");
  };
  return (
    <span className="control">
      <ul className="chips editable">
        {items.map((item, index) => (
          <li key={`${item}-${index}`} className={`chip ${tone || ""}`}>
            {item}
            <button type="button" className="chip-x" aria-label={`Remove ${item}`}
                    onClick={() => set(path, items.filter((_, at) => at !== index))}>×</button>
          </li>
        ))}
        <li>
          <input className="chip-input" value={typed} placeholder={placeholder} aria-label={label || path}
                 onChange={event => setTyped(event.target.value)} onBlur={add}
                 onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); add(); } }} />
        </li>
      </ul>
      <Problem error={error} />
    </span>
  );
}

export function RemoveButton({ onClick, what }) {
  return <button type="button" className="icon-button" aria-label={`Remove ${what}`} title={`Remove ${what}`} onClick={onClick}>×</button>;
}
