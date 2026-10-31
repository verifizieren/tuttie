# Dev team: start here

What is done, what is pending and our conventions: **[status.md](status.md)** (read it
first, update it with every change). What we build next: **[goals.md](goals.md)**.
Concept and demo strategy: `documentation/concept.md` · work areas: `documentation/architecture.md`
· message formats and trust rules: `documentation/formats.md`.

## Get the project running

```bash
git clone https://github.com/verifizieren/baselhack2026.git
cd baselhack2026/code
python3 -m venv .venv              # or: uv venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env               # add OPENAI_API_KEY (ask the team)
./run.sh                           # builds the wallet (needs Node.js 20+), then starts
                                   # registry :4000, nodes :4001-4007, assistant + apps :4040
```

- Wallet (the app): <http://localhost:4040/> (redirects to `/wallet/`); working on the UI:
  `cd apps/wallet && npm run dev` for hot reload on <http://localhost:4041/wallet/>
- Owner view (edit and deploy): on its own with `./run_owner.sh` (no OpenAI key; token `demo`) on
  <http://localhost:4042/owner/>; with the stack it needs `OWNER_TOKEN` in `.env` and is served at
  <http://localhost:4040/owner/?node=http://localhost:4009>. Details: `code/apps/owner/README.md`
- `./run.sh` needs `OPENAI_API_KEY` in `code/.env`: without it the assistant stops at start-up and
  `run.sh` stops all services with it
- Live team instance: <https://web4.mendes.dev> (shared server, ports 4000-4049)

## Before every push

```bash
scripts/check.sh                                  # tests, wallet build, and real flow; ~1 min
(cd apps/owner && npm test && npm run build)      # owner helpers pass and the app builds
scripts/check.sh --no-llm                         # skip the real flow when no key is available
```

It stops at the first failure and names the step. `./run.sh` prefixes every service's log
line with its name and warns at startup if there is no `OPENAI_API_KEY`.

## Working rules

- Pull before you start; small commits with clear messages; one concern per commit.
- No secrets in git: keys go in `code/.env`, which is ignored.
- Every module gets a short docstring; add tests with every feature.
- Signing only through `code/aps/`; prices only from node configs and signed messages.
- Changing `documentation/formats.md`? Tell the whole team first.
- Code stays in `code/`, docs in `documentation/`, presentation files in `assets/`
  (BaselHack template).
- Check in with the pitch and design team regularly (`documentation/context/pitch/`).

## Where to put things

| What | Where |
| --- | --- |
| Notes, links, design examples for devs | this folder |
| Backend and agents | `code/marketplace/`, `code/node/`, `code/assistant/`, `code/aps/` |
| Apps (wallet, owner view, presentation) | `code/apps/` |
| Hotel agents' data | `code/data/nodes/` |
