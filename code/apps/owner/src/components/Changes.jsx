// A list of changes in words: what was, what will be. Used by the deploy dialog and the history.

const SIGN = { added: "+", removed: "−", changed: "~" };

export default function Changes({ changes }) {
  if (!changes.length) return <p className="muted">No changes.</p>;
  return (
    <ul className="changes">
      {changes.map((change, index) => (
        <li key={index} className={change.kind}>
          <span className="sign">{SIGN[change.kind]}</span>
          <span className="what">{change.label}</span>
          <span className="values">
            {change.kind === "changed" && <><s>{change.before}</s> → <b>{change.after}</b></>}
            {change.kind === "added" && <b>{change.after}</b>}
            {change.kind === "removed" && <s>{change.before}</s>}
          </span>
        </li>
      ))}
    </ul>
  );
}
