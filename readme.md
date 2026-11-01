# Tuttie: your agent in your wallet

BaselHack 2026, Adobe challenge. **Live: <https://web4.mendes.dev>** (open it on your phone and
add it to the home screen). The page the pitch's QR code opens: <https://web4.mendes.dev/presentation/>.
Two pitch decks: `/keynote1/` (the illustrated pitch, `code/apps/keynote1/`) and `/keynote2/`
(clicker-driven, real wallet in a phone frame, `code/apps/keynote2/README.md`).

Tuttie lives in your phone's wallet. You say what you need, businesses' agents come to you
with signed offers, your agent picks the best few and negotiates for you, and you approve
with one tap. Small businesses get the same visibility as big platforms, because their agent
answers every matching request.

Underneath is an "agent web": every business is a **signed node**, and every message carries
an **APS seal** (Agent Protocol Secure) saying who sent it, which authorities vouch for them
and what they may do. Anything that does not verify is dropped, so scams become invisible.
The signatures are real Ed25519 and are really checked; nothing in the trust chain is mocked.

- Concept and demo strategy: [`documentation/concept.md`](documentation/concept.md)
- Architecture and work areas (mapped to the GitHub issues): [`documentation/architecture.md`](documentation/architecture.md)
- Message formats and trust rules: [`documentation/formats.md`](documentation/formats.md)
- **Project status** (done, pending, conventions, decisions; read first, keep it current): [`documentation/context/dev/status.md`](documentation/context/dev/status.md)
- For the team: [`documentation/context/`](documentation/context/) (dev: [start here](documentation/context/dev/README.md), [goals](documentation/context/dev/goals.md); research; pitch)

## Repository structure

This repo follows the BaselHack template:

| Folder | Contents |
| --- | --- |
| `code/` | all source code: `aps/` (signing), `registry/`, `node/` (business agents), `assistant/` (user's agent), `marketplace/`, `negotiation/` (bargaining), `sessions/` (agent memory), `services/` (weather, trains), `voice/`, `demo/`, `apps/` (`wallet/` React PWA, `owner/`, `presentation/`, `keynote1/, keynote2/`, `shared/`), `scripts/`, `tests/`, demo `data/` and `keys/` |
| `documentation/` | concept, architecture, formats, team context |
| `assets/` | presentation material |

## Run it

Requires Python 3.11+ and Node.js 20+ (for the wallet).

```bash
cd code
python3 -m venv .venv            # or: uv venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env             # add an LLM key: ANTHROPIC_API_KEY (default models) or OPENAI_API_KEY
./run.sh                         # builds the apps, starts registry :4000, nodes :4001-4009, marketplace :4010,
                                 # weather and trains :4011-4012, assistant + apps :4040 (voice too, if configured)
.venv/bin/pytest -q              # all Python tests (no network, no LLM)
```

<http://localhost:4040> opens the Tuttie wallet (phone-first), connected to Tuttie: type a
request, or talk to it when voice is configured (LiveKit and ElevenLabs keys in `.env`, see
[`code/voice/README.md`](code/voice/README.md)). The owner view is at `/owner/`. The same
flow also runs without a browser:

```bash
.venv/bin/python scripts/demo_headless.py approved   # or: declined
```

runs the whole flow in one process, with a real LLM, real signatures and a simulated phone:

1. Tuttie reads the user's context (calendar, messages, preferences) and posts a signed
   request on the marketplace; the budget stays private.
2. The marketplace wakes only verified hotels: the scam hotel (forged seal) and the unsigned
   one are never asked. The hotels' agents answer with signed offers; prices come from their
   configs, never from an LLM.
3. Tuttie's subagents bargain with each hotel in parallel, within the hotels' private limits
   and the user's private budget, and end with signed agreements.
4. The simulated phone likes the recommended hotels and approves the booking; the decision is
   signed with the user's key.
5. The hotel's action gate checks Tuttie's signed call, its delegation, the agreement and the
   user's approval before it confirms the booking; the city tax is paid with the user's mandate.

Or query the agent web directly:

```bash
curl "http://localhost:4000/search?tags=hotel,basel-sbb"
# every hotel serves its tools over MCP; any MCP client works, or plain JSON-RPC:
curl -X POST localhost:4001/mcp/ -H 'content-type: application/json' \
     -H 'accept: application/json, text/event-stream' \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": "get_availability", "arguments": {"date": "2026-11-14"}}}'
```

Hotel Rheinblick verifies as gold and Hotel Spalenhof as blue. `basel-cheap-hotels` claims
a government seal but signed it with its own key, so its seal is broken; Basel Budget Rooms
has no seal at all and stays untrusted.

To regenerate the demo keys and seals: `.venv/bin/python scripts/gen_keys.py && .venv/bin/python scripts/issue_seals.py`.
To keep everything running on a server, use the systemd user service in `deploy/tuttie.service`.

## Working on Tuttie

1. **Get it running:** clone, then follow "Run it" above. Working on the wallet UI:
   `cd code/apps/wallet && npm run dev` (hot reload on <http://localhost:4041/wallet/>).
2. **Pick your area:** [`documentation/architecture.md`](documentation/architecture.md)
   maps every folder to its GitHub issue; the dev goals and build order are in
   [`documentation/context/dev/goals.md`](documentation/context/dev/goals.md).
3. **Before every push:**
   ```bash
   cd code
   scripts/check.sh            # all tests, the wallet build and the real flow (demo_headless.py approved)
   scripts/check.sh --no-llm   # the same without the LLM step
   ```
4. **Rules:**
   - Pull before you start; small commits with clear messages, one concern each.
   - No secrets in git: keys go in `code/.env`, which is ignored.
   - A short docstring for every module, comments where the *why* is not obvious, tests for
     every feature.
   - Record what you finished, started or decided in
     [`documentation/context/dev/status.md`](documentation/context/dev/status.md), in the same change.
   - Signing only through `code/aps/`; prices only from node configs and signed messages.
   - Changing `documentation/formats.md`? Tell the whole team first.
   - Code in `code/`, docs in `documentation/`, presentation files in `assets/`.
   - Check in with the pitch and design team regularly
     ([`documentation/context/pitch/`](documentation/context/pitch/)); the demo is a run
     through the real app.

## Team

Every team member adds a short profile below. Copy the template, fill it in and keep it up
to date when your responsibilities change.

```markdown
### Your Name
- **Background:** what you study or work on, and what you bring to the team
- **Team:** dev / research / pitch
- **Working on:** areas and GitHub issues, e.g. wallet app (#2)
- **Responsible for:** what you own and decide, and what others can ask you about
- **Contact:** GitHub handle, how to reach you during the hackathon
```

<!-- Team profiles go here, one "### Name" block per person. -->

## License

MIT, see `license.txt`.
