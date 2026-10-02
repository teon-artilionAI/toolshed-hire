"""The shape every state changing use case shares.

A use case is a class that is handed what it needs through its constructor and
does its work in one `execute` call. The unit of work and the clock are common
to all of them, so they live here. Anything else a particular use case needs,
a pricing policy or a dispatcher, it takes through its own constructor.

The class is deliberately small. It exists so that every use case is built and
called the same way, which is what lets the API layer wire them without
knowing anything about what each one does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.clock import Clock
from app.application.unit_of_work import UnitOfWork


class UseCase[CommandT, ResultT](ABC):
    """One operation of the system, run inside one unit of work."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        """Keep the unit of work and the clock the use case runs with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant and business day come from.

        """
        self._uow = uow
        self._clock = clock

    @abstractmethod
    def execute(self, command: CommandT) -> ResultT:
        """Run the use case for one command and return its result."""
