"""Failures the CLI can name without a stack trace."""


class CoverageError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        super().__init__(message)


def classify_provider_error(provider: str, exc: Exception) -> CoverageError:
    if isinstance(exc, CoverageError):
        return exc
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    text = f"{exc}".lower()
    if status == 429 or "rate limit" in text or "too many requests" in text:
        return CoverageError(
            "rate_limit", f"{provider} rate limit reached. Wait and retry, or switch LLM_PROVIDER."
        )
    if status in {401, 403} or "api key" in text or "unauthorized" in text:
        return CoverageError(
            "missing_key", f"{provider} rejected the credentials. Check the API key."
        )
    return CoverageError("provider_error", f"{provider} request failed: {exc}")
