# Owner view (issue #5) — React + Vite

A page where a business owner sees what their agent offers and changes it: profile and
location, rooms and prices, add-ons and charges, policies, the agent's persona, whether it
answers new postings, and the private negotiation limits. Desktop first (sidebar + content,
collapses below 860 px), English.

**Edit, review, deploy.** Every field is editable. Changes are a *draft* kept in this browser
(`localStorage`, cleared on sign-out); guests' agents keep using the live version until the
owner presses **Review and deploy**, reads the list of changes in words and deploys. The node
checks the settings again, stores them as the next numbered version and its agent uses them
from the next request on. **Versions** lists every deploy with its changes; going back means
"Restore as draft" and deploying it again (history is never rewritten). A draft started on an
older version cannot be deployed over a newer one (the node answers 409); the page asks to
discard it first. The page also refreshes the live state every 5 s.

What the owner **cannot** change here: UID, seals, tags, capabilities, the agent's tools and its
boundaries ("Never …": they protect the private limits). Those need new seals or APS work.

## How it talks to the node

`code/node/owner.py`, all with `Authorization: Bearer <OWNER_TOKEN>` (set `OWNER_TOKEN` in
`code/.env`; the page asks for it on sign-in and keeps it in `sessionStorage`; no token
configured → the node refuses everyone, 503). A stand-in until owners authorise with their own key.

| Call | What |
| --- | --- |
| `GET /owner/overview` | the live business, the editable `settings`, the live `version` |
| `GET /owner/versions` | every version, newest first (version 0 = the committed config) |
| `POST /owner/deploy` | `{base_version, settings, note}` → new overview; 422 `{errors: [{path, message}]}`, 409 stale |

What may change and the checks (prices are whole francs, ids and room types are slugs, the lowest
price cannot be above the standard room's price, …) live in `code/node/settings.py`; versions are
stored in `code/data/deployments/<node_id>.json` (git-ignored) by `code/node/deployments.py`.

Which node: `?node=<url>` in the page address, else `VITE_NODE_URL`, else the Gästehaus am
Rhein's node (port 4009) on the host serving the page.

## Code

```
index.html                 entry page
vite.config.js             base /owner/, dev server on 4042
src/main.jsx               loads the styles and renders <App/>
src/App.jsx                sign-in, sidebar, header, deploy bar; ties draft, editor and dialog together
src/components/            sections.jsx (one form per section), inputs.jsx (path-based inputs),
                           editor.jsx (context), DeployDialog, Changes, Versions, Login, ui.jsx
src/hooks/useOverview.js   reads the business now and every 5 s
src/hooks/useDraft.js      the draft: stored in the browser, stale when the live version moved on
src/lib/api.js             node URL, token, overview / versions / deploy calls
src/lib/settings.js        read and change settings by path, "same setting?", the changes in words
src/lib/format.js          CHF, readable ids, "x s ago"
src/lib/settings.test.js   tests of the helpers (`npm test`)
src/owner.css              layout; brand colours and fonts come from apps/shared/tuttie.css
```

## Run

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

- A preview of what the agent would offer for a sample request.
- A business switcher, if one owner has several businesses.
- Real owner authorisation (the owner's key instead of one shared token) and a record of who deployed.
- Editing tags, tools and boundaries (needs new seals).
