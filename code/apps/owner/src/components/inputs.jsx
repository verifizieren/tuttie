// The few inputs the owner view needs. Each reads and writes the settings by path (editor.jsx)
// and shows the node's problem with its value, if there is one.
import { useEditor, useField } from "./editor.jsx";

const Problem = ({ error }) => (error ? <span className="problem-text">{error}</span> : null);

/** One line of a block: a label on the left, the control on the right. */
export function Line({ label, hint, children }) {
  return (
    <div className="line">
      <span className="line-label">{label}{hint && <span className="hint">{hint}</span>}</span>
      <span className="line-control">{children}</span>
    </div>
  );
}

export function TextBox({ path, label }) {
  const { set } = useEditor();
  const { value, error } = useField(path);
  return (
    <span className="control">
      <input type="text" className={error ? "input invalid" : "input"} value={value ?? ""} aria-label={label}
             onChange={event => set(path, event.target.value === "" ? undefined : event.target.value)} />
      <Problem error={error} />
    </span>
  );
}

/** A whole number; `unit` goes before it (CHF). */
export function NumberBox({ path, unit, label, min = 0 }) {
  const { set } = useEditor();
  const { value, error } = useField(path);
  return (
    <span className="control">
      <span className="with-unit">
        {unit && <span className="unit">{unit}</span>}
        <input type="number" min={min} step={1} className={error ? "input number invalid" : "input number"} value={value ?? ""}
               aria-label={label}
               onChange={event => set(path, event.target.value === "" ? undefined : Number(event.target.value))} />
      </span>
      <Problem error={error} />
    </span>
  );
}

/** An on/off switch for the boolean at `path`, or (with `checked` and `onChange`) for anything else. */
export function Switch({ path, label, onText = "On", offText = "Off", checked, onChange }) {
  const { set } = useEditor();
  const { value, error } = useField(path || "");
  const on = checked ?? Boolean(value);
  return (
    <span className="control">
      <label className="switch">
        <input type="checkbox" checked={on} aria-label={label}
               onChange={event => (onChange ? onChange(event.target.checked) : set(path, event.target.checked))} />
        <i /> <span>{on ? onText : offText}</span>
      </label>
      <Problem error={error} />
    </span>
  );
}
