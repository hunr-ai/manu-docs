from dataclasses import dataclass, replace


@dataclass
class SendEmailRequestDTO:
    to: str
    subject: str
    html_body: str
    text_body: str
    from_email: str | None = None
    tracking_token: str | None = None
    debug_code: str | None = None

    def require_tracking_token(self) -> str:
        if not self.tracking_token:
            raise ValueError("tracking_token is required")
        return self.tracking_token

    def with_tracking_token(self, tracking_token: str) -> "SendEmailRequestDTO":
        return replace(self, tracking_token=tracking_token)


@dataclass(frozen=True)
class EmailTrackStateDTO:
    tracking_token: str
    status: str
    email_track_id: int | None = None


@dataclass(frozen=True)
class SendEmailProviderResultDTO:
    tracking_token: str
    provider: str
    sent: bool


@dataclass(frozen=True)
class SendEmailFailureDTO:
    tracking_token: str
    failure_reason: str


@dataclass(frozen=True)
class SendEmailResultDTO:
    tracking_token: str
    status: str
    provider: str
    sent: bool
    email_track_id: int | None = None
