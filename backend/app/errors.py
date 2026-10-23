"""Application rejection codes, independent of HTTP and presentation."""

from enum import Enum


class ErrorCode(str, Enum):
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    TOO_LARGE = "too_large"
    INVALID_INPUT = "invalid_input"


class ApplicationError(Exception):
    def __init__(self, code: ErrorCode | str, detail):
        super().__init__(str(detail))
        self.code = ErrorCode(code)
        self.detail = detail
