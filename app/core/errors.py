"""Domain exceptions.

These carry an HTTP status so the API layer can translate them without
knowing anything about the domain.
"""

from __future__ import annotations


class AIHelperError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class ConfigurationError(AIHelperError):
    status_code = 500
    code = "configuration_error"


class AuthenticationError(AIHelperError):
    status_code = 401
    code = "authentication_failed"


class PermissionDeniedError(AIHelperError):
    status_code = 403
    code = "permission_denied"


class RateLimitedError(AIHelperError):
    status_code = 429
    code = "rate_limited"


class ValidationError(AIHelperError):
    status_code = 422
    code = "validation_error"


class NotFoundError(AIHelperError):
    status_code = 404
    code = "not_found"


class ProviderUnavailableError(AIHelperError):
    """A provider could not be reached, or refused the request."""

    status_code = 503
    code = "provider_unavailable"


class ProviderTimeoutError(ProviderUnavailableError):
    code = "provider_timeout"


class BudgetExceededError(AIHelperError):
    status_code = 402
    code = "budget_exceeded"


class PrivacyViolationError(AIHelperError):
    """Raised when data would leave the system against its classification."""

    status_code = 403
    code = "privacy_violation"


class ToolError(AIHelperError):
    status_code = 400
    code = "tool_error"


class NoAnswerError(AIHelperError):
    """Every avenue was tried and none produced an acceptable answer."""

    status_code = 503
    code = "no_answer"
