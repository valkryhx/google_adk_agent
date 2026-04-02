class UltraplanError(Exception):
    """Base exception for the ULTRAPLAN prototype."""


class UltraplanPollError(UltraplanError):
    def __init__(self, message: str, reason: str, reject_count: int, cause: Exception | None = None):
        super().__init__(message)
        self.reason = reason
        self.reject_count = reject_count
        self.cause = cause


class UltraplanPreconditionError(UltraplanError):
    """Raised when local prerequisites for remote launch are not met."""


class UltraplanAlreadyActiveError(UltraplanError):
    """Raised when a launch is attempted while another session is active."""


class RemoteSessionError(UltraplanError):
    def __init__(self, message: str, *, status_code: int | None = None, cause: Exception | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.cause = cause


class RemoteSessionTransportError(RemoteSessionError):
    """Raised for network and generic HTTP transport failures."""


class RemoteSessionAuthError(RemoteSessionError):
    """Raised when the remote API rejects authentication or authorization."""


class RemoteSessionNotFoundError(RemoteSessionError):
    """Raised when the requested remote session does not exist."""


class RemoteSessionRateLimitError(RemoteSessionError):
    """Raised when the remote API rate-limits the caller."""


class RemoteSessionServerError(RemoteSessionError):
    """Raised when the remote API returns a server-side failure."""


class RemoteSessionResponseError(RemoteSessionError):
    """Raised when the remote API returns an unexpected JSON shape."""
