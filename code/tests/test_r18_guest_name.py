"""Round 18: Tuttie never has to ask for the guest's name: book defaults to the user (it asked
"could you tell me the guest name for the booking?")."""

from assistant.tools import SCHEMAS


def test_book_does_not_require_a_guest_name():
    book = next(s["function"] for s in SCHEMAS if s["function"]["name"] == "book")
    assert "guest_name" not in book["parameters"]["required"]
    assert "user" in book["parameters"]["properties"]["guest_name"].get("description", "")
