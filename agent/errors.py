"""Stable error codes for agent routes. Human /submit keeps its own messages."""

from __future__ import annotations

HTTP_STATUS = {
    "invalid_input": 400,
    "unsupported_platform": 400,
    "episode_too_long": 422,
    "episode_not_found": 404,
    "upstream_unavailable": 502,
    "timeout": 504,
    "rate_limited": 429,
    "approval_required": 202,
    "approval_expired": 409,
    "idempotency_conflict": 409,
    "not_found": 404,
    "internal": 500,
    "audio_missing": 422,
}

PERMANENT_CODES = {
    "invalid_input",
    "unsupported_platform",
    "episode_too_long",
    "episode_not_found",
    "idempotency_conflict",
    "not_found",
    "audio_missing",
    "approval_expired",
}

MESSAGES = {
    "invalid_input": "The request body is not valid.",
    "unsupported_platform": "Only Apple Podcasts and Spotify episode URLs are supported.",
    "episode_too_long": "Episodes longer than 30 minutes are not supported.",
    "episode_not_found": "The episode could not be found.",
    "upstream_unavailable": "An upstream service was unavailable.",
    "timeout": "The job exceeded its deadline.",
    "rate_limited": "The language-model cooldown is longer than the time left on this job.",
    "approval_required": "Approval is required before this operation can run.",
    "approval_expired": "The approval expired before a decision arrived.",
    "idempotency_conflict": "This idempotency key was already used with a different request.",
    "not_found": "No job or summary exists for that id.",
    "internal": "Unexpected error.",
    "audio_missing": "Audio file not found.",
}

HUMAN_URL_REQUIRED = "URL is required"
HUMAN_BAD_SUMMARY = "Invalid summary type. Must be 'ts', 'ns', or 'bs'"
HUMAN_BAD_PLATFORM = "Unsupported podcast platform. Only Apple Podcasts and Spotify are supported."
HUMAN_PUBLISH_FAILED = "Failed to start processing. Please try again."
HUMAN_PROCESS_FAILED = "Failed to process podcast URL. Please check the URL and try again."
HUMAN_AUDIO_MISSING = "Audio file not found or could not be downloaded."
HUMAN_METADATA_MISSING = "Episode metadata not found."
HUMAN_INTERNAL = "Internal server error. Please try again later."
HUMAN_IDEMPOTENCY = "Idempotency key was already used with a different request."
HUMAN_APPROVAL = "Approval required before this uncached summary can start."


class AgentError(Exception):
    def __init__(self, code: str, message: str | None = None, *, retryable: bool | None = None,
                 retry_after_seconds: int | None = None, human_detail: str | None = None):
        self.code = code
        self.message = message or MESSAGES.get(code, MESSAGES["internal"])
        self.retryable = (code not in PERMANENT_CODES) if retryable is None else retryable
        self.retry_after_seconds = retry_after_seconds
        self.status_code = HTTP_STATUS.get(code, 500)
        self.human_detail = human_detail or self.message
        super().__init__(self.message)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
        }

    def as_body(self) -> dict:
        return {"error": self.as_dict()}


def error_dict(code: str, message: str | None = None, *, retryable: bool | None = None,
               retry_after_seconds: int | None = None) -> dict:
    return AgentError(code, message, retryable=retryable, retry_after_seconds=retry_after_seconds).as_dict()


def classify_resolver_message(message: str | None) -> str:
    text = (message or "").lower()
    if "30 minutes" in text or "longer than 30" in text:
        return "episode_too_long"
    if any(needle in text for needle in (
        "not found",
        "no episodes",
        "no audio file",
        "could not extract",
        "invalid apple",
        "no audio",
    )):
        return "episode_not_found"
    return "upstream_unavailable"


def is_transient_exception(exc: BaseException) -> bool:
    """True for upstream 429/5xx that should be retried. Token-limit errors are not."""
    if isinstance(exc, RuntimeError) and "Failed to process after" in str(exc):
        return False
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status in (429, 500, 502, 503, 504):
        return True
    text = str(exc).lower()
    if any(token in text for token in ("request too large", "tokens per minute", "413")):
        return False
    return any(token in text for token in (
        "429",
        "500",
        "502",
        "503",
        "504",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "bad gateway",
        "service unavailable",
    ))
