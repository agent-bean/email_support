"""Redact Google callback query values from Uvicorn access records."""

import logging
from typing import cast


class AuthQueryRedactionFilter(logging.Filter):
    callback_paths = {
        "/api/auth/google/callback",
        "/api/google/connection/callback",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.args, tuple) or len(record.args) < 3:
            return True
        args = list(record.args)
        path = cast(str, args[2])
        callback_path = path.split("?", maxsplit=1)[0]
        if callback_path in self.callback_paths:
            args[2] = f"{callback_path}?[redacted]"
            record.args = tuple(args)
        return True


def install_auth_query_redaction() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(
        isinstance(item, AuthQueryRedactionFilter) for item in access_logger.filters
    ):
        access_logger.addFilter(AuthQueryRedactionFilter())
