# Two Webs: an Agent Web prototype

BaselHack 2026, Adobe challenge.

A parallel "agent web" next to the human web: every business is a **signed node** that
AI agents can discover, query and transact with. Every response carries an **APS seal**
(Agent Protocol Secure) that says who answered, which authorities vouch for them and
what they are allowed to do. Agents drop anything that does not verify, so scams become
invisible to them.

The signatures are real Ed25519 and are really checked. Nothing in the trust chain is mocked.

## Repository structure

This repo follows the BaselHack template:

| Folder | Contents |
| --- | --- |
| `code/` | all source code: `aps/` library, `registry/`, `node/`, `assistant/`, `ui/`, `scripts/`, `tests/`, demo `data/` and `keys/` |
| `documentation/` | `formats.md`: the APS wire formats and trust rules |
| `assets/` | presentation material |

## Run it

Requires Python 3.11+.

```bash
cd code
python3 -m venv .venv            # or: uv venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env             # add your OPENAI_API_KEY
./run.sh                         # registry :4000, nodes :4001-4005, assistant + UI :4040
.venv/bin/pytest -q              # tests for the APS library and trust gate (no network, no LLM)
```

Open <http://localhost:4040>, send the prefilled request, and watch the timeline on the
right: the scam hotel is rejected in red, and every fact the assistant uses comes from a
signed, verified response.

Or query the agent web directly:

```bash
curl "http://localhost:4000/search?tags=hotel,basel-sbb"
curl -X POST localhost:4001/tools/get_availability -H 'content-type: application/json' \
     -d '{"date": "2026-11-14", "guests": 1}'
```

The registry returns three hotels. Hotel Rheinblick verifies as gold and Hotel Spalenhof
as blue. `basel-cheap-hotels` claims a government seal but signed it with its own key,
so its seal is broken.

To regenerate the demo keys and seals: `.venv/bin/python scripts/gen_keys.py && .venv/bin/python scripts/issue_seals.py`.

## License

MIT, see `license.txt`.
