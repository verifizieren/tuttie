# Owner view (issue #5) — React + Vite

One calm page, like the wallet (black, one column), where a business owner changes what their
agent offers. Four blocks, only what a short demo needs:

- **Rooms:** price per night and whether a room is offered.
- **Extras:** the price of each add-on the agent may promise.
- **Negotiation (private):** whether the agent bargains, the lowest price, the rounds.
- **Agent:** its name, tone and whether it answers new requests.

The header shows the business, its seals (a dot per seal, by colour), its UID and the live state
(refreshed every 5 s).

**Edit, review, deploy.** Edits are a *draft* kept in this browser (`localStorage`, cleared on
sign-out); guests' agents keep using the live version until the owner presses **Review**, reads
the changes in words and presses **Deploy**. The node checks the settings again, stores them as the
next numbered version and its agent uses them from the next request on. A draft started on an
older version cannot be deployed over a newer one (the node answers 409); the page asks to
discard it first.

The node can change more than the page shows (profile, location, policies, charges, persona
priorities, adding and removing rooms or add-ons) and keeps a version history with
`GET /owner/versions`; the page leaves those out on purpose. Nobody can change UID, seals, tags,
capabilities, tools or the agent's boundaries here.

## How it talks to the node

`code/node/owner.py`, all with `Authorization: Bearer <OWNER_TOKEN>` (set `OWNER_TOKEN` in
`code/.env`; the page asks for it on sign-in and keeps it in `sessionStorage`; no token
configured → the node refuses everyone, 503). A stand-in until owners authorise with their own key.

| Call | What |
| --- | --- |
| `GET /owner/overview` | the live business, the editable `settings`, the live `version` |
| `GET /owner/versions` | every version, newest first (version 0 = the committed config); no page uses it yet |
| `POST /owner/deploy` | `{base_version, settings, note}` → new overview; 422 `{errors: [{path, message}]}`, 409 stale |

What may change and the checks (prices are whole francs, ids and room types are slugs, the lowest
price cannot be above the standard room's price, …) live in `code/node/settings.py`; versions are
stored in `code/data/deployments/<node_id>.json` (git-ignored) by `code/node/deployments.py`.

Which node: `?node=<url>` in the page address, else `VITE_NODE_URL`, else the Gästehaus am
Rhein's node (port 4009) on the host serving the page. `?node=` counts only for the page's own
host or localhost/127.0.0.1 (any port), since the owner token is sent there; any other value is ignored.

## Code

```
index.html                 entry page
vite.config.js             base /owner/, dev server on 4042
src/main.jsx               loads the styles and renders <App/>
src/App.jsx                the page: header, blocks, deploy bar; ties draft, editor and dialog together
src/components/            sections.jsx (the four blocks), inputs.jsx (path-based inputs), editor.jsx (context),
                           DeployDialog, Changes, Login
src/hooks/useOverview.js   reads the business now and every 5 s
src/hooks/useDraft.js      the draft: stored in the browser, stale when the live version moved on
src/lib/api.js             node URL, token, overview and deploy calls
src/lib/settings.js        read and change settings by path, "same setting?", the changes in words
src/lib/format.js          CHF, readable ids, "x s ago"
src/lib/settings.test.js   tests of the helpers (`npm test`)
src/owner.css              the layout; brand colours and fonts come from apps/shared/tuttie.css
```

## Try it

From `code/`, after the one-time setup in `documentation/context/dev/README.md` (venv and
`pip install -r requirements.txt`):

**On its own (no OpenAI key, nothing else running):**

```bash
./run_owner.sh          # the Gästehaus node on :4009 and this page on :4042
```

Open <http://localhost:4042/owner/> and sign in with the token `demo` (`OWNER_TOKEN=other
./run_owner.sh` to choose another). Ctrl+C stops both.

**With the whole stack** (the page is then served by the assistant at <http://localhost:4040/owner/>,
with `?node=http://localhost:4009`): put `OWNER_TOKEN=<your token>` in `code/.env` (copy
`.env.example`), then `./run.sh`. The stack needs `OPENAI_API_KEY` in `code/.env`: without it the
assistant stops at start-up ("Missing credentials") and `run.sh` stops everything with it.

**Resetting.** Deployed versions are saved in `code/data/deployments/` (git-ignored, local to your
machine): delete that folder to go back to the committed config. To keep experiments out of it,
start with `OWNER_DATA_DIR=/tmp/owner-data ./run_owner.sh`. An unfinished draft lives in the
browser: press Discard or Sign out.

## Develop

```bash
cd code/apps/owner
npm install
npm test         # the settings helpers
npm run dev      # http://localhost:4042/owner/?node=http://localhost:4009 (start ../../run.sh first)
npm run build    # production build in dist/, served by the assistant at /owner/
```

`run.sh` builds it together with the wallet; live at `<host>:4040/owner/`. The Python side is
tested in `code/tests/test_node_owner.py`.

## Not built yet

- A page for the version history and rolling back (the node already has it).
- Editing profile, location, policies, charges, adding rooms and add-ons.
- A preview of what the agent would offer for a sample request.
- Real owner authorisation (the owner's key instead of one shared token).
