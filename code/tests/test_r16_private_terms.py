"""Round 16: a question to a hotel never names private places or people (Tuttie wrote "after the
last train from Milan"; the home city is private context)."""

import asyncio

from assistant.tools import GUEST_FIRST_NAME
from tests.test_tools import RHEINBLICK, make_toolbox


def test_private_places_and_people_are_known():
    toolbox, _, _ = make_toolbox()
    terms = toolbox.private_terms()
    assert {"milan", "milano", "lukas", "sara"} <= terms
    assert not {"basel", "luna", GUEST_FIRST_NAME.lower()} & terms  # what the hotel needs, and the guest's own name


def test_ask_agent_refuses_a_question_naming_private_context():
    toolbox, _, _ = make_toolbox()
    result = asyncio.run(toolbox.ask_agent(RHEINBLICK, "Late arrival after the last train from Milan, ok?"))
    assert "error" in result and "private" in result["error"]


def test_private_train_and_time_are_private_terms_too():
    toolbox, _, _ = make_toolbox()
    terms = toolbox.private_terms()
    assert {"ec 52", "00:52"} <= terms


def test_requirements_naming_private_context_are_not_posted():
    toolbox, _, _ = make_toolbox()
    kept = toolbox.public_needs(["quiet", "arriving on the EC 52 from Milan at 00:52", "dog-friendly"])
    assert kept == ["quiet", "dog-friendly"]
