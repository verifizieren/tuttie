// A list of changes in words: what was, what will be.

export default function Changes({ changes }) {
  return (
    <ul className="changes">
      {changes.map((change, index) => (
        <li key={index}>
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
