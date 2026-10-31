// Asks for the owner token before anything private is read from the node.
import { useState } from "react";

export default function Login({ onSubmit, problem }) {
  const [token, setToken] = useState("");
  return (
    <main className="page login">
      <form onSubmit={event => { event.preventDefault(); if (token.trim()) onSubmit(token.trim()); }}>
        <h1>Tuttie <span>for business</span></h1>
        <input type="password" autoFocus autoComplete="current-password" placeholder="Owner token" aria-label="Owner token"
               className="input" value={token} onChange={event => setToken(event.target.value)} />
        {problem && <p className="problem-text">{problem}</p>}
        <button type="submit" disabled={!token.trim()}>Open</button>
      </form>
    </main>
  );
}
