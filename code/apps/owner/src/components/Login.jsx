// Asks for the owner token before anything private is read from the node.
import { useState } from "react";
import { nodeUrl } from "../lib/api.js";

export default function Login({ onSubmit, problem }) {
  const [token, setToken] = useState("");
  return (
    <main className="login">
      <form className="login-card" onSubmit={event => { event.preventDefault(); if (token.trim()) onSubmit(token.trim()); }}>
        <h1>Tuttie <span>for business</span></h1>
        <p className="muted">See what your agent offers to customers. Enter your owner token to continue.</p>
        <label htmlFor="token">Owner token</label>
        <input id="token" type="password" autoFocus autoComplete="current-password"
               value={token} onChange={event => setToken(event.target.value)} />
        {problem && <p className="problem">{problem}</p>}
        <button type="submit" disabled={!token.trim()}>Open my business</button>
        <p className="muted small">Reading from <span className="mono">{nodeUrl()}</span></p>
      </form>
    </main>
  );
}
