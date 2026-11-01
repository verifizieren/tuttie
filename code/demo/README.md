# Demo (issues #3, #2) — not started

Runs the stage demo: the storyline as a list of steps (user line, expected agent action,
timing) that drives the real components, so the demo is predictable but nothing is faked.

- **No own UI.** The audience sees the real wallet app (`apps/wallet/`). The demo only
  supplies input and timing (e.g. the user's spoken lines, when to advance) to the same
  backend a real user talks to. The design example in `code/.context/` is a separate
  mock-up page; do not copy that pattern, fold its look into the real wallet instead.

- Input: the storyline (issue #3).
- Drives: the user's agent (`assistant/`), the wallet app, the voice layer.
- Rule: the demo may fix what is said or chosen, never verification. A forged seal must
  fail in the demo exactly as in real use.
- Reuse: `scripts/demo_headless.py` already runs the full current flow in one process with
  a simulated phone; a good starting point for the demo runner.
