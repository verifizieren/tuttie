# Tuttie: architecture and work areas

Each work area has its own folder, its own issue and a contract with the others, so people
can work in parallel without stepping on each other. Contracts live in
`documentation/formats.md`; change them only after telling the team.

## Components

```
            presentation site (apps/presentation)        owner view (apps/owner)
                         | scroll into demo                      | edits agent presence
                         v                                       v
  phone: wallet (apps/wallet) + voice (code/voice)        business nodes (code/node)
                         |                                  ^  signed offers, A2A,
                         v                                  |  negotiation, booking
         user's agent (code/assistant) <--> marketplace (code/marketplace) <--> registry
                         |                                        (code/registry)
                         v
              console (apps/console): every signed step, live over SSE
                                   all signing: code/aps
             scripted demo (code/demo) drives the same real components
```

## Work areas

| Area | Folder | Issue | Status | Talks to others through |
| --- | --- | --- | --- | --- |
| Protocol and signing | `code/aps/` | #10 | done, tested | Python API; formats: envelope, seals, approval |
| Registry | `code/registry/` | #9 | done | `GET /search`, `GET /nodes/{id}` |
| Business nodes | `code/node/`, `code/data/nodes/` | #10 | done for direct booking; offers and negotiation to add | signed envelopes; formats: offer, counter-offer |
| Marketplace (requests, offers, shortlist, negotiation) | `code/marketplace/` | #8, #9, #10 | to build | formats: request, offer, counter-offer, agreement |
| User's agent | `code/assistant/` | #10 | done for direct booking; marketplace flow to add | UI events over SSE, approvals API |
| Wallet app (phone) | `code/apps/wallet/` | #2 | approvals page only; wallet UI to build | approvals API, UI events |
| Voice agent | `code/voice/` | #2, #3 | to build | text in/out of the user's agent |
| Owner view | `code/apps/owner/` | #5 | to build | owner API (to define) that edits `data/nodes/*.json` facts |
| Presentation site and QR | `code/apps/presentation/` | #1, #6 | to build | links into the wallet and console |
| Scripted demo (director) | `code/demo/` | #3, #2 | to build | drives the user's agent and the apps |
| Console | `code/apps/console/` | — | done | UI events over SSE |
| Shared UI pieces | `code/apps/shared/` | — | seal badges | — |
| Pitch, storyline, tech check, numbers | `assets/`, `documentation/` | #1, #3, #4, #7 | team | — |

## Rules that keep the areas independent

- **Signing stays in `code/aps/`.** No other folder creates or checks signatures by hand.
- **Prices never come from an LLM.** They come from node configs and signed messages.
- **The scripted demo calls the real components**; it never fakes verification
  (`documentation/concept.md`).
- **Apps are static pages** (HTML + vanilla JS, no build step) served by the assistant at
  `/<app>/`; shared code goes in `apps/shared/`.
- **Ports** (team server allows 4000-4049): registry 4000, nodes 4001-4007, assistant and
  apps 4040. The marketplace takes 4010 when it exists.
