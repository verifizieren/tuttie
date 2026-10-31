# Scripted demo (issues #3, #2) — not started

The director for the stage demo: a script of steps (user line, expected agent action,
timing) that drives the real components, so the demo is predictable but nothing is faked.

- Input: the storyline (issue #3).
- Drives: the user's agent (`assistant/`), the wallet and console apps, the voice layer.
- Rule: the script may fix what is said or chosen, never verification. A forged seal must
  fail in the scripted run exactly as in a live run.
- Reuse: `scripts/demo_headless.py` already runs the full current flow in one process with
  a simulated phone; a good starting point for a script runner.
