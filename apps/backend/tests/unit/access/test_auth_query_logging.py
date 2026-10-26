"""Provider callback query values never appear in Uvicorn access messages."""

import logging

from email_support.api.logging import AuthQueryRedactionFilter


def test_google_callback_query_is_redacted_before_formatting() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "server.py",
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1",
            "GET",
            "/api/auth/google/callback?code=secret&state=secret",
            "1.1",
            303,
        ),
        None,
    )

    assert AuthQueryRedactionFilter().filter(record)
    formatted = record.getMessage()

    assert "code=secret" not in formatted
    assert "state=secret" not in formatted
    assert "[redacted]" in formatted
