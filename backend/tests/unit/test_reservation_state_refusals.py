"""Every move the state table does not list is refused (BR-11).

A reservation has eight statuses and can be asked to make seven moves, which is
fifty six pairings. Nine of them are legal. The other forty seven are generated
here from the table and not written out one by one, so a tenth legal move added
by mistake fails a test with its name on it.

A refusal has to say which status the reservation holds and which one the move
would have led to, it has to name BR-11 for the log, and it has to leave the
reservation exactly as it was. Its sentence is shown to a customer, so it is
plain words with no rule and no value in it.

The guards and the effects of the nine legal moves are in
test_reservation_hold_move.py and test_reservation_states.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final

import pytest

from app.domain.booking import Reservation
from app.domain.enums import ReservationStatus
from app.domain.errors import StateTransitionError
from app.domain.states import TerminalState, guards, state_for
from tests.support.reservations import (
    CATALOGUE,
    HOLD_EXPIRES_AT,
    NINTH,
    NOW,
    ONE_SECOND,
    TODAY,
    FakeAllocator,
    a_reservation_in,
    refused_and_untouched,
)

PERMITTED_TRANSITIONS_RULE: Final[str] = "BR-11"
REASON: Final[str] = "The job was postponed."
# The branch shuts at 17:00 in Cape Town on the first day of the hire, which is
# 15:00 UTC. The no show is asked about a second later.
BRANCH_CLOSED_AT: Final[datetime] = datetime(2026, 3, 9, 15, 0, tzinfo=UTC)

# The seven moves, each with the status it leads to.
MOVES: Final[Mapping[str, ReservationStatus]] = {
    "hold": ReservationStatus.HELD,
    "confirm": ReservationStatus.CONFIRMED,
    "cancel": ReservationStatus.CANCELLED,
    "collect": ReservationStatus.COLLECTED,
    "expire": ReservationStatus.EXPIRED,
    "mark_no_show": ReservationStatus.NO_SHOW,
    "close": ReservationStatus.RETURNED,
}
# The state table of the design document. Nothing else is a legal move.
LEGAL_MOVES: Final[frozenset[tuple[ReservationStatus, str]]] = frozenset(
    {
        (ReservationStatus.DRAFT, "hold"),
        (ReservationStatus.DRAFT, "cancel"),
        (ReservationStatus.HELD, "confirm"),
        (ReservationStatus.HELD, "cancel"),
        (ReservationStatus.HELD, "expire"),
        (ReservationStatus.CONFIRMED, "collect"),
        (ReservationStatus.CONFIRMED, "cancel"),
        (ReservationStatus.CONFIRMED, "mark_no_show"),
        (ReservationStatus.COLLECTED, "close"),
    }
)
EVERY_PAIRING: Final[list[tuple[ReservationStatus, str]]] = [
    (status, move) for status in ReservationStatus for move in MOVES
]
REFUSED_MOVES: Final[list[tuple[ReservationStatus, str]]] = [
    pairing for pairing in EVERY_PAIRING if pairing not in LEGAL_MOVES
]
TERMINAL_STATUSES: Final[frozenset[ReservationStatus]] = frozenset(
    {
        ReservationStatus.RETURNED,
        ReservationStatus.CANCELLED,
        ReservationStatus.NO_SHOW,
        ReservationStatus.EXPIRED,
    }
)
STATUS_COUNT: Final[int] = 8
MOVE_COUNT: Final[int] = 7
LEGAL_MOVE_COUNT: Final[int] = 9
# What a sentence shown to a customer never carries.
FORBIDDEN_IN_A_SENTENCE: Final[tuple[str, ...]] = ("BR-", "NFR-", "start=", "end=")
GUARD_SENTENCES: Final[list[str]] = [
    value for name, value in sorted(vars(guards).items()) if name.endswith("_MESSAGE")
]


def named(pairing: tuple[ReservationStatus, str]) -> str:
    """Return the name a pairing carries in the test report, for example HELD-collect."""
    status, move = pairing
    return f"{status.value}-{move}"


def ask(reservation: Reservation, move: str) -> None:
    """Ask a reservation to make a move, with everything a guard could want in order.

    Every argument is one a legal move would accept. A move that goes through
    here is therefore one the state permits, and never one that slipped past
    for want of a guard failing.
    """
    after_the_hold = HOLD_EXPIRES_AT + ONE_SECOND
    if move == "hold":
        reservation.hold(now=NOW, today=TODAY, models=CATALOGUE, allocator=FakeAllocator())
    elif move == "confirm":
        reservation.confirm(now=NOW, email_verified=True)
    elif move == "cancel":
        reservation.cancel(now=NOW, reason=REASON, by_owner_or_staff=True)
    elif move == "collect":
        reservation.collect(today=NINTH)
    elif move == "expire":
        reservation.expire(now=after_the_hold)
    elif move == "mark_no_show":
        reservation.mark_no_show(
            now=BRANCH_CLOSED_AT + ONE_SECOND, branch_closed_at=BRANCH_CLOSED_AT
        )
    else:
        reservation.close(now=after_the_hold)


def is_plain(sentence: str) -> bool:
    """Return True when a sentence names no rule, repeats no value and reads as prose."""
    return not sentence.startswith("Attempted") and not any(
        fragment in sentence for fragment in FORBIDDEN_IN_A_SENTENCE
    )


class TestTheTableItself:
    """The grid the cases below are generated from is the whole grid."""

    def test_eight_statuses_and_seven_moves_leave_forty_seven_refusals(self) -> None:
        assert (len(ReservationStatus), len(MOVES)) == (STATUS_COUNT, MOVE_COUNT)
        assert len(LEGAL_MOVES) == LEGAL_MOVE_COUNT
        assert len(REFUSED_MOVES) == STATUS_COUNT * MOVE_COUNT - LEGAL_MOVE_COUNT

    def test_every_legal_move_names_a_move_that_exists(self) -> None:
        assert {move for _, move in LEGAL_MOVES} == set(MOVES)

    @pytest.mark.parametrize("pairing", sorted(LEGAL_MOVES, key=named), ids=named)
    def test_a_legal_move_goes_through_and_lands_where_the_table_says(
        self, pairing: tuple[ReservationStatus, str]
    ) -> None:
        status, move = pairing
        reservation = a_reservation_in(status)
        ask(reservation, move)
        assert reservation.status is MOVES[move]


class TestAMoveTheTableDoesNotList:
    """Refused with the two statuses and the rule, and nothing changes."""

    @pytest.mark.parametrize("pairing", REFUSED_MOVES, ids=named)
    def test_it_is_refused_and_the_reservation_is_left_as_it_was(
        self, pairing: tuple[ReservationStatus, str]
    ) -> None:
        status, move = pairing
        reservation = a_reservation_in(status)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            ask(reservation, move)
        assert refused.value.from_status == status.value
        assert refused.value.to_status == MOVES[move].value
        assert refused.value.rule == PERMITTED_TRANSITIONS_RULE
        assert refused.value.detail == {
            "from_status": status.value,
            "to_status": MOVES[move].value,
        }

    @pytest.mark.parametrize("pairing", REFUSED_MOVES, ids=named)
    def test_its_sentence_is_plain_words(self, pairing: tuple[ReservationStatus, str]) -> None:
        status, move = pairing
        with pytest.raises(StateTransitionError) as refused:
            ask(a_reservation_in(status), move)
        assert str(refused.value) == refused.value.message
        assert refused.value.message.startswith("This reservation ")
        assert is_plain(refused.value.message)

    @pytest.mark.parametrize(
        ("status", "move", "sentence"),
        [
            (
                ReservationStatus.DRAFT,
                "confirm",
                "This reservation is still a draft, so it cannot be confirmed.",
            ),
            (
                ReservationStatus.CANCELLED,
                "hold",
                "This reservation has been cancelled, so it cannot be put on hold.",
            ),
            (
                ReservationStatus.COLLECTED,
                "cancel",
                "This reservation has been collected, so it cannot be cancelled.",
            ),
            (
                ReservationStatus.NO_SHOW,
                "collect",
                "This reservation was not collected, so it cannot be collected.",
            ),
            (
                ReservationStatus.EXPIRED,
                "mark_no_show",
                "This reservation has expired, so it cannot be marked as not collected.",
            ),
        ],
    )
    def test_the_sentence_says_where_the_reservation_stands_and_what_could_not_be_done(
        self, status: ReservationStatus, move: str, sentence: str
    ) -> None:
        with pytest.raises(StateTransitionError) as refused:
            ask(a_reservation_in(status), move)
        assert refused.value.message == sentence


class TestWhatAStatePermits:
    """`permits` answers for a move without making it, and agrees with the table."""

    @pytest.mark.parametrize("pairing", EVERY_PAIRING, ids=named)
    def test_a_state_permits_exactly_the_moves_the_table_lists(
        self, pairing: tuple[ReservationStatus, str]
    ) -> None:
        status, move = pairing
        assert state_for(status).permits(move) is (pairing in LEGAL_MOVES)

    @pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES))
    def test_a_finished_reservation_permits_nothing(self, status: ReservationStatus) -> None:
        assert not any(state_for(status).permits(move) for move in MOVES)


class TestTheStateOfAStatus:
    """`state_for` finds the one state that stands for a status."""

    @pytest.mark.parametrize("status", list(ReservationStatus))
    def test_every_status_has_a_state_that_carries_it(self, status: ReservationStatus) -> None:
        assert state_for(status).status is status
        assert a_reservation_in(status).state is state_for(status)

    @pytest.mark.parametrize("status", list(ReservationStatus))
    def test_the_four_endings_are_terminal_states_and_the_other_four_are_not(
        self, status: ReservationStatus
    ) -> None:
        assert isinstance(state_for(status), TerminalState) is (status in TERMINAL_STATUSES)


class TestTheSentencesOfAFailedGuard:
    """A guard that fails speaks to the same customer, in the same plain words."""

    def test_there_are_sentences_to_read(self) -> None:
        assert GUARD_SENTENCES

    @pytest.mark.parametrize("sentence", GUARD_SENTENCES)
    def test_a_guard_sentence_names_no_rule_and_repeats_no_value(self, sentence: str) -> None:
        assert is_plain(sentence)
        assert sentence.endswith(".")
