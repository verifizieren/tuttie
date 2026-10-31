# Tuttie: your agent in your wallet

BaselHack 2026, Adobe challenge.

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
- For the team: [`documentation/context/`](documentation/context/) (dev: [start here](documentation/context/dev/README.md), [goals](documentation/context/dev/goals.md); research; pitch)

## Repository structure

This repo follows the BaselHack template:

| Folder | Contents |
| --- | --- |
| `code/` | all source code: `aps/` (signing), `registry/`, `node/` (business agents), `assistant/` (user's agent), `marketplace/`, `voice/`, `demo/`, `apps/` (console, wallet, owner, presentation, shared), `scripts/`, `tests/`, demo `data/` and `keys/` |
| `documentation/` | concept, architecture, formats |
| `assets/` | presentation material |

## Run it

Requires Python 3.11+.

```bash
cd code
python3 -m venv .venv            # or: uv venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env             # add your OPENAI_API_KEY
./run.sh                         # registry :4000, nodes :4001-4007, assistant + apps :4040
.venv/bin/pytest -q              # tests for APS, the trust gate and booking (no network, no LLM)
```

<http://localhost:4040> opens the new Tuttie wallet (phone-first; the agent is not connected
yet). The first working prototype is at <http://localhost:4040/old/console/>: press
**Dog + 1am arrival** and the timeline on the right shows what happens:

1. The scam hotel is rejected in red; Hotel Rheinblick verifies as gold.
2. Signed availability and policies are fetched (A2T).
3. The assistant asks the hotel's own agent about the 1am arrival with a dog (A2A) and gets
   a signed, priced commitment.
4. An approval appears. Press **Phone** and scan the QR code, or open `/old/wallet/`, then
   tap Approve. The decision is signed with the user's key.
5. The hotel checks the signature, recomputes the total from its own signed commitment and
   confirms the booking. Each claim in the answer carries a seal badge citing its source.

Without a browser: `.venv/bin/python scripts/demo_headless.py [approved|declined]` runs the
same flow in one process with a simulated phone.

To keep it running on a server, use the systemd user service in `deploy/tuttie.service`.

Or query the agent web directly:

```bash
curl "http://localhost:4000/search?tags=hotel,basel-sbb"
curl -X POST localhost:4001/tools/get_availability -H 'content-type: application/json' \
     -d '{"date": "2026-11-14", "guests": 1}'
```

Hotel Rheinblick verifies as gold and Hotel Spalenhof as blue. `basel-cheap-hotels` claims
a government seal but signed it with its own key, so its seal is broken; Basel Budget Rooms
has no seal at all and stays untrusted.

To regenerate the demo keys and seals: `.venv/bin/python scripts/gen_keys.py && .venv/bin/python scripts/issue_seals.py`.

## License

MIT, see `license.txt`.
