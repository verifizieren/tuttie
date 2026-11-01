"""Round 9: a sealed hotel's huge or non-number price never crashes Tuttie's booking path
(math and f"{x:g}" raise OverflowError on a 400-digit integer)."""

from assistant.tools import chf, finite_price


def test_finite_price_takes_only_real_positive_numbers():
    assert finite_price(128) and finite_price(12.5)
    for bad in (10 ** 400, -(10 ** 400), 0, -5, True, "128", None, float("nan"), float("inf")):
        assert not finite_price(bad), bad


def test_chf_formats_any_value_without_raising():
    assert chf(128) == "128" and chf(12.5) == "12.5"
    assert chf(10 ** 400) == "?" and chf("x") == "?" and chf(None) == "?"


def test_the_night_is_given_with_its_weekday_so_the_model_never_guesses_it():
    """The model said "Friday 14 November" for 2026-11-14, a Saturday."""
    from assistant.tools import night_said
    assert night_said("2026-11-14") == "Saturday 14 November"
    assert night_said("2026-11-01") == "Sunday 1 November"
    assert night_said("not a date") is None and night_said(None) is None
