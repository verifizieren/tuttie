// Building blocks shared by the sections: a titled card, a label/value row, chips and a table.

export function Card({ title, note, children }) {
  return (
    <section className="card">
      {(title || note) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {note && <span className="card-note">{note}</span>}
        </header>
      )}
      {children}
    </section>
  );
}

/** One label with its value; nothing is drawn when the business has not set the value. */
export function Field({ label, children }) {
  if (children === undefined || children === null || children === "" || children === false) return null;
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export const Fields = ({ children }) => <dl className="fields">{children}</dl>;

export function Chips({ items, tone }) {
  if (!items?.length) return <span className="muted">None</span>;
  return (
    <ul className="chips">
      {items.map(item => <li key={item} className={`chip ${tone || ""}`}>{item}</li>)}
    </ul>
  );
}

export const Empty = ({ children }) => <p className="muted empty">{children}</p>;

/** A plain table: `columns` are [header, cell(row)] pairs. */
export function Table({ columns, rows }) {
  return (
    <table className="table">
      <thead>
        <tr>{columns.map(([header]) => <th key={header}>{header}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>{columns.map(([header, cell]) => <td key={header}>{cell(row)}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}
