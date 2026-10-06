"""Provider boundary: ephemeral URLs never belong to business records."""

from dataclasses import dataclass, field
from typing import Protocol


class CaptureError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class StopCapture(Exception):
    pass


@dataclass
class Source:
    live: bool
    url: str | None = field(default=None, repr=False)


class Provider(Protocol):
    def probe(self, reference: str, tick) -> Source: ...
    def acquire(self, reference: str, tick) -> Source: ...
    def health(self) -> dict: ...
