"""The sentences shown for a query parameter the framework refused.

The framework writes a sentence of its own when it refuses a value, and that
sentence was reaching a customer's screen. `app/api/field_messages.py` chooses
a plain one by the kind of refusal. These tests pin each sentence, and they
pin the two things that keep the framework's wording out. A kind nobody listed
gets the general sentence, and only a query parameter is reworded.
"""

from __future__ import annotations

import pytest

from app.api.field_messages import (
    CHOICE_MESSAGE,
    NOT_ACCEPTED_MESSAGE,
    plain_query_message,
    refused_fields,
)

FRAMEWORK_SENTENCE = "Input should be a valid date or datetime, input is too short"


class TestTheSentenceForEachKindOfRefusal:
    """Chosen by the kind the framework names, never by its sentence."""

    @pytest.mark.parametrize(
        ("kind", "limits", "sentence"),
        [
            ("missing", {}, "This is needed. Please fill it in."),
            ("date_from_datetime_parsing", {}, "Enter a valid date, in the form YYYY-MM-DD."),
            ("date_parsing", {}, "Enter a valid date, in the form YYYY-MM-DD."),
            ("int_parsing", {}, "Enter a whole number."),
            ("int_from_float", {}, "Enter a whole number."),
            ("enum", {"expected": "'name' or 'dailyRateAsc'"}, CHOICE_MESSAGE),
            ("greater_than_equal", {"ge": 1}, "Enter 1 or more."),
            ("less_than_equal", {"le": 10}, "Enter 10 or less."),
            ("string_too_short", {"min_length": 2}, "Enter at least 2 characters."),
            ("string_too_short", {"min_length": 1}, "Enter at least 1 character."),
            ("string_too_long", {"max_length": 120}, "Enter at most 120 characters."),
        ],
    )
    def test_a_kind_the_reads_can_meet_has_a_plain_sentence(
        self, kind: str, limits: dict[str, object], sentence: str
    ) -> None:
        assert plain_query_message(kind, limits) == sentence

    @pytest.mark.parametrize("kind", ["value_error", "uuid_parsing", "a_kind_added_next_year", ""])
    def test_a_kind_with_no_sentence_of_its_own_gets_the_general_one(self, kind: str) -> None:
        assert plain_query_message(kind, {}) == NOT_ACCEPTED_MESSAGE

    def test_a_limit_the_framework_did_not_state_gets_the_general_sentence(self) -> None:
        assert plain_query_message("greater_than_equal", {}) == NOT_ACCEPTED_MESSAGE


class TestReadingTheRefusalsOfARequest:
    """A sentence for the response and a kind for the log, for each field."""

    def test_a_query_parameter_is_reworded_and_its_kind_is_kept_for_the_log(self) -> None:
        sentences, kinds = refused_fields(
            [
                {
                    "type": "date_from_datetime_parsing",
                    "loc": ("query", "from"),
                    "msg": FRAMEWORK_SENTENCE,
                    "input": "banana",
                },
                {
                    "type": "less_than_equal",
                    "loc": ("query", "quantity"),
                    "msg": "Input should be less than or equal to 10",
                    "input": "11",
                    "ctx": {"le": 10},
                },
            ]
        )
        assert sentences == {
            "query.from": "Enter a valid date, in the form YYYY-MM-DD.",
            "query.quantity": "Enter 10 or less.",
        }
        assert kinds == {
            "query.from": "date_from_datetime_parsing",
            "query.quantity": "less_than_equal",
        }

    def test_what_was_sent_is_in_neither_the_sentence_nor_the_kind(self) -> None:
        sentences, kinds = refused_fields(
            [{"type": "string_too_short", "loc": ("query", "q"), "msg": "x", "input": "wacker"}]
        )
        assert "wacker" not in str(sentences) + str(kinds)

    def test_a_request_body_is_refused_in_the_words_of_the_framework_as_before(self) -> None:
        sentences, kinds = refused_fields(
            [{"type": "missing", "loc": ("body", "email"), "msg": "Field required"}]
        )
        assert sentences == {"body.email": "Field required"}
        assert kinds == {"body.email": "missing"}

    def test_a_refusal_with_no_location_and_no_kind_is_still_answered(self) -> None:
        sentences, kinds = refused_fields([{"msg": "Something was wrong."}])
        assert sentences == {"": "Something was wrong."}
        assert kinds == {"": ""}

    def test_a_location_that_is_not_a_sequence_is_read_as_no_location(self) -> None:
        sentences, _ = refused_fields([{"type": "missing", "loc": None, "msg": "Field required"}])
        assert sentences == {"": "Field required"}
