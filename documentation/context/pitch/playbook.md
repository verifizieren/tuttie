# Tuttie Pitch Playbook: 3:00 hard, live wallet demo, BaselHack 2026 / Adobe

## 1. The 10 rules

| # | Rule | Why | Famous example | What Tuttie does |
|---|---|---|---|---|
| 1 | Say what it is in the first 10 seconds | The score is set in the opening (Kurbaitaev) | PG tip 1; Seibel: "no need to set up the problem" | The eyes open, then: "This is Tuttie. She lives in your wallet. Businesses send her signed offers, and fakes never reach you." |
| 2 | One throughline of 15 words or fewer, repeated word for word | Judges repeat it later in deliberation | Anderson TED2016; Jobs, "the world's thinnest notebook" (Macworld 2008) | Pick one line and freeze it. Say it at 0:10, after the forged offer drops, and as the last line. |
| 3 | Name a villain that is a situation, not a company | A hero needs something to beat | Jobs: "Who wants a stylus?" (2007) | Fifty open tabs, the small hotel on page nine, fake offers that look real. Never name a platform as the villain, and never present Adobe as a party to Tuttie (citing Adobe Analytics as a source is fine). |
| 4 | Three things that turn into one | Builds tension, then a reveal | iPhone 2007: three devices, then "one device" | "A shopper. A scam filter. A shop window. One card." Keep the structure but use your own words, because a tech jury spots copied Jobs lines (Anderson). |
| 5 | One S.T.A.R. moment, and keep quiet during it | One memorable peak beats five | Duarte, *Resonate*; the MacBook Air envelope | The forged business shows up, its seal fails, the eyes narrow, the card turns red and drops. Then 2 seconds of silence and one line: "That was a real signature check." |
| 6 | Golden path: fixed demo words, real mechanics | Removes doubt, and faking the judged claim loses everything | iPhone golden path; also its hard-coded five signal bars (Vogelstein, NYT 2013) | Voice lines can be fixed for the demo. Seals, registry lookups and the rejection stay real (concept.md). Adobe's brief says the prototype must "not be faked end to end." |
| 7 | Cut scope to one end-to-end story | "Overstuffed is under-explained" (Anderson) | YC Demo Day: 3–4 "vertebrae" | Ask → sealed offers arrive → forgery dropped → small hotel wins → one tap to approve. Everything else goes to Q&A. |
| 8 | Build from familiar pieces with metaphors | Jurors who are not crypto experts still follow | Anderson tip 3 | Wallet card, then eyes, then a wax seal, then a broken seal. Never say "Ed25519" on stage. |
| 9 | One continuous camera, no slide cuts | Apple's motion language | WWDC18 "Designing Fluid Interfaces": spatial consistency, 100% damping | One canvas. Zoom into the phone, then pull out along the same path. Springs of 0.5–0.8 s with no bounce. Offers fly in from the direction of their business. |
| 10 | End on a bang and an earned ask | Avoids the fade-out (YC) | Sivers' 3-minute TED talk ends on one plain instruction | Callback line, then the QR, then "Thank you." No "Questions?" slide. |

**Time budget, rehearsed to 2:45:**

| Time | Beat |
|---|---|
| 0:00–0:15 | Eyes open and the one-sentence "what it is" |
| 0:15–0:40 | Villain, plus one number |
| 0:40–1:00 | Three things become one |
| 1:00–2:20 | Live golden path, with the peak at about 1:50 |
| 2:20–2:45 | Vision 2033, owner beat, honesty line |
| 2:45–3:00 | Throughline and QR |

## 2. Judging criteria checklist

There is no official 2026 rubric online. **Ask the Adobe challenge mentor or the BaselHack Discord today whether Q&A falls inside the 3:00.**

| Criterion (source) | Where it is covered | Status |
|---|---|---|
| Vision of local business in 5–10 years, with why it is plausible (Adobe) | 2:20 beat: "2033: businesses come to your wallet," backed by +693% AI retail traffic (Adobe Analytics, holiday 2025) | Covered in storyline.md (pull-out after the demo); needs the plausibility sentence |
| Core mechanism really works (Adobe) | Live forged-seal rejection, with GET /events one tap away | Covered if nothing is hard-coded |
| Innovation beyond the minimal hotel-plus-MCP path (Adobe) | "Not a hotel with an API. The agents come to you." | Needs the line |
| Discovery & trust: "Why did the agent pick this one?" (Adobe) | Tap the winning offer to show its seals and a one-line reason | **MISSING** as a demo beat |
| Representation & fairness (Adobe) | The small hotel wins against the chain | Gästehaus am Rhein, owner Anna (node config) |
| Owner's experience / the business side (Adobe) | One sentence plus a short glimpse of the owner view | **MISSING.** The story is consumer-only right now. |
| Human in control and transaction (Adobe; AEM blog) | One-tap signed approval: "Nothing happens without you." | Covered |
| Code on GitHub with how-to; right tech; complexity; no reinvented wheel (BaselHack 2020) | QR to the repo; README tested on a clean machine | **MISSING:** license.txt says "© 2025 <copyright holders>" and the team section is empty |
| Wow factor (ETHGlobal used as a proxy) | The forged-offer drop | Covered |

## 3. Demo safety

- Two phones in the same pre-seeded state, already signed in, with a one-tap reset.
- Backend on localhost or a hotspot, never the venue wifi. No live speech recognition, no login or 2FA on stage (Eden).
- Test the phone-to-projector mirroring on the real stage cable.
- A muted recording of the exact golden path on the laptop, one keypress away. Switch line: "Same run, from an hour ago." Rehearse the switch at least once.
- Code freeze 2 hours before the pitch (Eden).
- Honesty line, said once right after the peak: "The hotels and the register are demo. My request was a button. The signatures are real."
- Q&A answer ready on what is mocked (cards, voice) and what is real (seals, registry, approvals).
- At least 10 timed runs out loud, including the zoom transitions, on the real hardware.
- If anything breaks, keep talking. Composure counts for more than the bug.

## 4. Delivery checklist for Thomas

- **First 10 seconds.** Feet planted. Hold up the phone in silence while the eyes open, then deliver the opening line word for word. No names, no agenda.
- **Pauses.** 1–2 seconds before the name "Tuttie", before the forgery drops, and after the throughline. If it feels too slow, it is probably right (PG tip 7).
- **Eyes.** One sentence per juror. Never turn to read the projector.
- **Hands.** Stay still. Move only on transitions: walk to the demo spot as the camera zooms into the phone, and step forward for the close.
- **Driving the phone.** Don't talk and drive (PG). A teammate runs the phone, or the run is auto-sequenced, and Thomas narrates in the present tense like a commentator ("three shops answer… this one's lying").
- **Voice.** Conversational, not recited. Memorise the beat list plus the first and last lines only.
- **Last 10 seconds.** Callback line, a pause, "Scan the code," then "Thank you." Stop.

## 5. Anti-patterns

- Opening with "In a post-website world…", a sad statistic, or team introductions.
- Touring every feature: A2A, the negotiation loop, the LLM tool loop.
- Saying "platform," "agentic ecosystem," or "cryptographic trust layer" instead of showing the moment.
- Hard-coding any verification result (the five-bars trap).
- **The AI-generated deck look:** gradient blobs, sparkle icons, bullet lists, stock "futuristic" art, emoji headers, several competing slogans, bouncy animations, text the presenter also reads aloud. Use one image or three words per frame, one accent colour (the seal colour), and black or white backgrounds.
- **"Adobe Business Registry" in authorities.json.** It is not a real Adobe product. Rename it to a neutral issuer. No Adobe or Content Credentials logos.
- Claiming C2PA compliance. Say instead that APS is "inspired by, mappable to" C2PA/CAWG.
- Unverified statistics: the 31% conversion uplift, the 13x trial growth, the "4% of sites" figure.
- Repeating the phrase "one more thing", or using it for a minor or fake reveal.
- Ending on "Thanks… questions?"

## 6. Five bold ideas the team probably hasn't considered

1. **Tuttie speaks first.** Copy the Macintosh 1984 structure, not its words: the card opens its eyes and greets the room before Thomas says anything.
2. **"Content Credentials told you who made a photo. Tuttie's seals tell you who made an offer."** One line puts APS inside Adobe's own trust lineage (CAI, the C2PA trust list). Back it with a 15-second Q&A answer to "why not C2PA?"
3. **Answer the jury's own question on screen.** Show "Why did the agent pick this one?" as two seal colours plus one reason. The jurors wrote that question.
4. **The jury becomes the user.** One more thing, used only if it is real: the QR opens a static stage build of the wallet (no /chat, no /reset), where each juror watches a demo business's sealed offer arrive. Even stronger: let a juror press "forge" and watch their fake get dropped on their own phone.
5. **The camera pulls back as the ending.** Zoom out from the one Basel booking to a map where dozens of small businesses' agents light up as they answer. This shows the vision without a sentence of text, and it closes the loop on the opening tab-chaos shot.

**Still open:** the official rubric and Q&A format, the owner beat, the license and team section, and the issuer rename. (Small hotel: Gästehaus am Rhein, Anna; throughline: storyline.md.)