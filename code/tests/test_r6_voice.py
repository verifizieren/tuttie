"""Round 6 (voice): the turn budget, ids read aloud, clock times, a mute room, fillers on swipes.

From the red team's round 6 (conversations and voice). No LiveKit, ElevenLabs or LLM call.
"""

import asyncio
import json
import os

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test")  # the app builds an LLM client; these tests never call it

from assistant import voice  # noqa: E402
from assistant.app import app  # noqa: E402
from assistant.conversations import Conversation  # noqa: E402
from voice.agent import UPDATES, Tuttie, follow, spoken, update_for  # noqa: E402

AGENT = {"Authorization": "Bearer secret-for-tests"}


def configure(monkeypatch):
    monkeypatch.setattr(voice, "API_KEY", "key")
    monkeypatch.setattr(voice, "API_SECRET", "secret-for-tests")
    monkeypatch.setattr(Conversation, "start", lambda self, *a, **k: "t0")  # no LLM: only the doors


def test_voice_card_swipes_do_not_run_out_the_turn_budget(monkeypatch):
    """H2: a realistic voice minute (a request, room fragments, four "next", the wallet's booking
    turn, a few more words) must not leave a spoken "like" with 429 ("One moment please.")."""
    configure(monkeypatch)
    with TestClient(app) as wallet:
        room = wallet.post("/voice/token").json()["room"]
        say = lambda text: wallet.post("/voice/say", json={"room": room, "text": text}, headers=AGENT).status_code
        codes = [say("I want to book something"), say("as you can see"), say("it is asking the hotels"),
                 *[say("next") for _ in range(4)]]
        conv_id = wallet.get("/history").headers["X-Conversation-ID"]
        codes.append(wallet.post("/chat", json={"message": "Book Hotel Rheinblick (ch.basel.hotel-rheinblick).",
                                                "first_tool": "book", "conversation_id": conv_id}).status_code)
        codes += [say("thank you"), say("that was quick"), say("like")]
        assert 429 not in codes, codes


def test_spoken_turns_have_their_own_allowance_but_floods_still_stop(monkeypatch):
    """Voice gets more turns a minute than typing (fragments count), yet a flood gets 429. Its
    count is its own: room noise never blocks the wallet's typed or swiped turns, nor the reverse."""
    configure(monkeypatch)
    with TestClient(app) as wallet:
        room = wallet.post("/voice/token").json()["room"]
        say = lambda text: wallet.post("/voice/say", json={"room": room, "text": text}, headers=AGENT).status_code
        codes = [say(f"tell me more {i}") for i in range(voice.VOICE_TURNS_PER_SESSION_PER_MIN + 1)]
        assert codes == [202] * voice.VOICE_TURNS_PER_SESSION_PER_MIN + [429], codes
        assert wallet.post("/chat", json={"message": "hi"}).status_code == 202  # typing has its own count


def test_card_commands_are_capped_on_their_own(monkeypatch):
    """Exact card commands need no LLM while cards are shown, so they do not use the turn budget;
    they still have a cap of their own."""
    configure(monkeypatch)
    with TestClient(app) as wallet:
        room = wallet.post("/voice/token").json()["room"]
        show_cards(wallet)
        say = lambda text: wallet.post("/voice/say", json={"room": room, "text": text}, headers=AGENT).status_code
        codes = [say("next") for _ in range(voice.CARD_COMMANDS_PER_SESSION_PER_MIN + 1)]
        assert codes == [202] * voice.CARD_COMMANDS_PER_SESSION_PER_MIN + [429]
        assert say("I want to book something") == 202  # the turn budget is untouched


def show_cards(wallet):
    """The hotel cards are on screen in this browser's conversation (swipeable)."""
    from assistant.app import SESSION_COOKIE
    conv = app.state.conversations.get(wallet.cookies[SESSION_COOKIE])
    conv.bus.emit("marketplace", "verified", "Cards", detail={"phase": "cards"})


def test_room_fragments_do_not_lock_out_the_wallets_book_swipe(monkeypatch):
    """Ten two-word fragments from a noisy room, then the user's swipe-to-book (/chat,
    first_tool book): it must not get 429."""
    configure(monkeypatch)
    with TestClient(app) as wallet:
        room = wallet.post("/voice/token").json()["room"]
        say = lambda text: wallet.post("/voice/say", json={"room": room, "text": text}, headers=AGENT).status_code
        assert all(say(f"oh nice {i}") == 202 for i in range(10))
        conv_id = wallet.get("/history").headers["X-Conversation-ID"]
        book = wallet.post("/chat", json={"message": "Book Hotel Rheinblick (ch.basel.hotel-rheinblick).",
                                          "first_tool": "book", "conversation_id": conv_id})
        assert book.status_code == 202


def test_card_commands_without_cards_count_as_voice_turns(monkeypatch):
    """Without swipeable cards "next" falls through to the LLM, so it is a normal voice turn:
    the card cap is no second LLM budget."""
    started = []
    monkeypatch.setattr(voice, "API_KEY", "key")
    monkeypatch.setattr(voice, "API_SECRET", "secret-for-tests")
    monkeypatch.setattr(Conversation, "start", lambda self, message, *a, **k: started.append(message) or "t0")
    with TestClient(app) as wallet:
        room = wallet.post("/voice/token").json()["room"]
        say = lambda text: wallet.post("/voice/say", json={"room": room, "text": text}, headers=AGENT).status_code
        for i in range(voice.CARD_COMMANDS_PER_SESSION_PER_MIN):
            say(["next", "Next.", "skip", "like", "no thanks"][i % 5])
        for i in range(voice.VOICE_TURNS_PER_SESSION_PER_MIN):
            say(f"tell me more {i}")
    assert len(started) <= voice.VOICE_TURNS_PER_SESSION_PER_MIN, len(started)


def test_spoken_never_reads_a_node_id_in_parentheses_or_bare():
    """H3: node ids (and approval, offer, mandate ids) are never read aloud."""
    assert "ch.basel" not in spoken("Booked Hotel Rheinblick (ch.basel.hotel-rheinblick) for CHF 128.")
    assert "ch.basel" not in spoken("Booked ch.basel.gaestehaus-am-rhein for CHF 128.")
    said = spoken("Approve ap-1a2b3c4d for offer of-hotel-alpina-0f9e8d under md-12ab34cd.")
    assert "ap-" not in said and "of-" not in said and "md-" not in said, said


def test_a_late_arrival_and_swiss_thousands_are_said_right():
    """H4: "for 00:52" is a time unless "hrs" follows; "CHF 1'280" is 1280 francs."""
    assert "12:52 am" in spoken("I asked them to hold the room for 00:52.")
    assert spoken("It takes 01:15 hrs.") == "It takes 01:15 hrs."
    assert spoken("That is CHF 1'280 in total.") == "That is 1280 francs in total."


class Session:
    agent_state = "listening"

    def __init__(self, lines):
        self.lines = lines

    def say(self, text):
        self.lines.append(text)


class Participant:
    attributes = {"voice": "on"}


class Room:
    name = "tuttie-x"
    remote_participants = {"p": Participant()}


class QuietAgent:
    asked = None

    def filler(self):
        return None


def frames(*events) -> str:
    return "".join(f"event: message\ndata: {json.dumps(e)}\n\n" for e in events)


ANSWER = {"kind": "answer", "status": "verified", "summary": "Booked, CHF 128.", "turn": "t1", "detail": {}}


def test_voice_follow_reconnects_after_its_event_stream_ends(monkeypatch):
    """H5: when GET /voice/events ends (a restart, a dropped connection), follow() connects again
    instead of leaving the room mute."""
    import voice.agent as voice_agent

    monkeypatch.setattr(voice_agent, "RECONNECT_S", (0.01, 0.02))
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, text="")  # the stream ends at once
        if calls["n"] == 2:
            return httpx.Response(503)  # the assistant is still starting
        return httpx.Response(200, text=frames(ANSWER))

    lines = []

    async def run():
        async with httpx.AsyncClient(base_url="http://a", transport=httpx.MockTransport(handler)) as http:
            try:
                await asyncio.wait_for(follow(Session(lines), QuietAgent(), http, Room()), 2)
            except asyncio.TimeoutError:
                pass
    asyncio.run(run())
    assert lines and lines[0] == "Booked, 128 francs.", (calls, lines)


def test_voice_follow_stops_for_an_inactive_conversation(monkeypatch):
    """404 (unknown room) or 409 (the chat changed): follow() stops for good, no hot loop."""
    import voice.agent as voice_agent

    monkeypatch.setattr(voice_agent, "RECONNECT_S", (0.01, 0.02))
    for status in (404, 409):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(status)

        async def run():
            async with httpx.AsyncClient(base_url="http://a", transport=httpx.MockTransport(handler)) as http:
                await asyncio.wait_for(follow(Session([]), QuietAgent(), http, Room()), 2)
        asyncio.run(run())
        assert calls["n"] == 1


def test_a_voice_card_swipe_gets_no_filler(monkeypatch):
    """H6: a spoken "next" moves the card without the LLM: no "Sure, one moment." before it."""
    events = [
        {"kind": "turn", "status": "pending", "summary": "next", "turn": "t2", "detail": {"source": "voice", "said": "next"}},
        {"kind": "wallet", "status": "verified", "summary": "Pass the visible hotel", "turn": "t2",
         "detail": {"action": "swipe", "verdict": "pass"}},
        {"kind": "answer", "status": "verified", "summary": "Passing this card.", "turn": "t2", "detail": {}},
    ]
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=frames(*events)) if calls["n"] == 1 else httpx.Response(409)

    lines = []
    monkeypatch.setattr(Tuttie, "session", property(lambda self: Session(lines)), raising=False)

    async def run():
        async with httpx.AsyncClient(base_url="http://a", transport=httpx.MockTransport(handler)) as http:
            agent = Tuttie("tuttie-x", http)
            agent.asked = "next"  # what on_user_turn_completed sets for "next"
            agent.turns = 2
            await asyncio.wait_for(follow(Session(lines), agent, http, Room()), 2)
    asyncio.run(run())
    assert lines == ["Passing this card."], lines


def test_a_second_approval_in_the_same_turn_is_announced_too():
    """The booking's Face ID prompt and then the city tax's (no mandate) in one turn: both said."""
    said = set()
    first = {"kind": "approval", "status": "pending", "detail": {"approval_id": "ap-00000001"}}
    second = {"kind": "approval", "status": "pending", "detail": {"approval_id": "ap-00000002"}}
    assert update_for(first, said) == UPDATES["approval"]
    assert update_for(first, said) is None  # the same approval again: once
    assert update_for(second, said) == UPDATES["approval"]


def test_voice_diag_logs_one_clean_line_and_is_throttled(capsys):
    """/voice/diag is open to anyone: a report is one line (no forged log lines) and a flood is cut."""
    with TestClient(app) as client:
        assert client.post("/voice/diag", content=b'{"state":"ok"}\nvoice: forged line\r\x1b[2J').status_code == 204
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1 and "\x1b" not in out[0] and out[0].startswith('voice diag: {"state":"ok"}')
        for _ in range(voice.DIAGS_PER_CLIENT_PER_MIN + 5):
            client.post("/voice/diag", content=b"x")
        assert len(capsys.readouterr().out.strip().splitlines()) == voice.DIAGS_PER_CLIENT_PER_MIN - 1


def test_while_the_phone_asks_spoken_lines_wait_for_the_decision(monkeypatch):
    """While the Face ID sheet is up, a spoken line (also "yes, book it" or a goodbye) is not
    passed on (it would queue behind the running turn for minutes and could run after the
    decision): the voice says to decide on the phone, at most once every few seconds. After the
    decision (or a reset) lines go through again."""
    from livekit.agents import StopResponse

    pending = {"kind": "approval", "status": "pending", "summary": "Waiting for your phone.", "turn": "t1",
               "detail": {"approval_id": "ap-0000000a", "amount_chf": 128}}
    decided = {"kind": "approval", "status": "declined", "summary": "You declined CHF 128", "turn": "t1",
               "detail": {"decision": {"approval_id": "ap-0000000a", "decision": "declined"}}}
    streams = [frames(pending)]
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=streams.pop(0)) if streams else httpx.Response(409)

    lines, sent = [], []
    monkeypatch.setattr(Tuttie, "session", property(lambda self: Session(lines)), raising=False)

    class Message:
        def __init__(self, text):
            self.text_content = text

    async def turn(agent, text):
        try:
            await agent.on_user_turn_completed(None, Message(text))
        except StopResponse:
            pass

    async def run():
        async with httpx.AsyncClient(base_url="http://a", transport=httpx.MockTransport(handler)) as http:
            agent = Tuttie("tuttie-x", http)

            async def pass_on(text):
                sent.append(text)
            agent.pass_on = pass_on
            await asyncio.wait_for(follow(Session(lines), agent, http, Room()), 2)
            assert agent.pending_approvals
            await turn(agent, "yes book it")
            await turn(agent, "ok thanks bye")
            assert sent == [] and lines == [UPDATES["approval"], "Please approve or decline on your phone first."], lines
            streams.append(frames(decided))
            await asyncio.wait_for(follow(Session(lines), agent, http, Room()), 2)
            assert not agent.pending_approvals
            await turn(agent, "ok thanks bye")
            assert sent == ["ok thanks bye"]
    asyncio.run(run())


def test_a_reconnect_clears_a_pending_approval_whose_decision_was_missed(monkeypatch):
    """The stream drops while the Face ID sheet is up; the decision lands in the gap (the new
    stream replays no history). Pending is cleared on every (re)connect: at worst a spoken line
    queues as before, the voice never says "decide first" forever."""
    import voice.agent as voice_agent
    from livekit.agents import StopResponse

    monkeypatch.setattr(voice_agent, "RECONNECT_S", (0.01, 0.02))
    monkeypatch.setattr(voice_agent, "DECIDE_FIRST_EVERY_S", 0)
    pending = {"kind": "approval", "status": "pending", "summary": "Waiting for your phone.", "turn": "t1",
               "detail": {"approval_id": "ap-0000000a", "amount_chf": 128}}
    streams = [frames(pending), ": keepalive\n\n"]

    def handler(request):
        return httpx.Response(200, text=streams.pop(0)) if streams else httpx.Response(404)

    lines, sent = [], []
    monkeypatch.setattr(Tuttie, "session", property(lambda self: Session(lines)), raising=False)

    class Message:
        def __init__(self, text):
            self.text_content = text

    async def run():
        async with httpx.AsyncClient(base_url="http://a", transport=httpx.MockTransport(handler)) as http:
            agent = Tuttie("tuttie-x", http)

            async def pass_on(text):
                sent.append(text)
            agent.pass_on = pass_on
            await asyncio.wait_for(follow(Session(lines), agent, http, Room()), 2)
            assert not agent.pending_approvals
            try:
                await agent.on_user_turn_completed(None, Message("find me a hotel please"))
            except StopResponse:
                pass
    asyncio.run(run())
    assert lines[0] == UPDATES["approval"] and sent == ["find me a hotel please"], (lines, sent)


def test_spoken_never_reads_ids_or_urls():
    """Ids in any case (ap-, of-, md-, rq-, node ids) and web addresses are not read aloud."""
    for answer, leak in [
        ("Approval AP-1A2B3C4D is waiting on your phone.", "AP-1A2B3C4D"),
        ("Your offer of-alpina-0F9E8D is the best.", "of-alpina-0F9E8D"),
        ("I posted request rq-1a2b3c4d to the marketplace.", "rq-1a2b3c4d"),
        ("Mandate MD-12AB34CD is signed.", "MD-12AB34CD"),
        ("Pay the deposit at https://evil.example/pay now.", "evil.example"),
        ("Details at www.evil.example today.", "evil.example"),
        ("Node CH.BASEL.HOTEL-RHEINBLICK answered.", "BASEL"),
    ]:
        said = spoken(answer)
        assert leak not in said, (answer, said)


def test_spoken_keeps_ordinary_dotted_words_and_hosts():
    """Only the real node id shape goes; hosts and dotted words stay."""
    assert spoken("Timetable at de.sbb.ch, it is quick.") == "Timetable at de.sbb.ch, it is quick."
    assert spoken("Details at en.wikipedia.org.") == "Details at en.wikipedia.org."
    assert "basically" in spoken("Breakfast is ok.so.basically included, CHF 12.")


def test_spoken_says_a_space_grouped_price_as_one_amount():
    """"CHF 1 280" with a space, a no-break space or a narrow no-break space is 1280 francs."""
    for answer in ("The suite is CHF 1 280 in total.", "The suite is CHF 1\u00a0280 in total.",
                   "The suite is CHF 1\u202f280 in total.", "The suite is 1 280 CHF in total."):
        said = spoken(answer)
        assert "1280 francs" in said and "1 franc" not in said, said
    assert spoken("Rooms 2 and 3 cost CHF 128 each.") == "Rooms 2 and 3 cost 128 francs each."


def test_spoken_leaves_no_dangling_parenthesis_after_an_id():
    """An id first in a parenthesis with more inside goes with its separator."""
    assert spoken("Rheinblick (ch.basel.hotel-rheinblick, CHF 128) is free tonight.") == \
        "Rheinblick (128 francs) is free tonight."
