from uuid import uuid4

from config.settings.schemas import AuthSettings
from db.models import User, UserRole
from emails.email_service import EmailService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from utils.otp_utils import OTPUtil
from workflows.dto.emails.send_email_request_dto import SendEmailRequestDTO
from workflows.emails.send_email_workflow import SendEmailWorkflow

from .dto.auth_request_dto import (
    PasswordlessLoginRequestDTO,
    PasswordlessLoginResponseDTO,
    PasswordlessVerifyRequestDTO,
    SignupRequestDTO,
    SignupVerifyRequestDTO,
    TokenPairResponseDTO,
)
from .utils.jwt_utils import create_token_pair, decode_refresh_token


class AuthServiceError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class AuthService:
    def __init__(
        self,
        db_session: AsyncSession,
        otp_util: OTPUtil,
        auth_settings: AuthSettings,
        temporal_client: Client,
        task_queue: str,
    ):
        self._db_session = db_session
        self._otp_util = otp_util
        self._auth_settings = auth_settings
        self._temporal_client = temporal_client
        self._task_queue = task_queue

    async def _find_user_by_email(self, email: str) -> User | None:
        result = await self._db_session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _get_user_by_email(self, email: str) -> User:
        user = await self._find_user_by_email(email)
        if user is None:
            raise AuthServiceError("user not found")
        return user

    def _token_response(self, user: User) -> TokenPairResponseDTO:
        access_token, refresh_token = create_token_pair(user, self._auth_settings)
        return TokenPairResponseDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._auth_settings.access_expiration_minutes * 60,
            refresh_expires_in=self._auth_settings.refresh_expiration_minutes * 60,
        )

    async def _send_otp_email(self, email: str, otp: str) -> None:
        email_service = EmailService(self._db_session)
        rendered_email = await email_service.render_login_email(email, otp)
        tracking_token = f"passwordless-login-{uuid4()}"
        await self._temporal_client.start_workflow(
            SendEmailWorkflow.run,
            SendEmailRequestDTO(
                to=email,
                subject=rendered_email.subject,
                html_body=rendered_email.html_body,
                text_body=rendered_email.text_body,
                from_email=rendered_email.from_email,
                tracking_token=tracking_token,
                debug_code=otp,
            ),
            id=tracking_token,
            task_queue=self._task_queue,
        )

    async def passwordless_login(
        self, request: PasswordlessLoginRequestDTO
    ) -> PasswordlessLoginResponseDTO:
        await self._get_user_by_email(request.email)
        otp = await self._otp_util.generate_otp(request.email)
        await self._send_otp_email(request.email, otp)
        return PasswordlessLoginResponseDTO(
            success=True,
            message="passwordless login email queued",
        )

    async def resend_passwordless_login(
        self, request: PasswordlessLoginRequestDTO
    ) -> PasswordlessLoginResponseDTO:
        return await self.passwordless_login(request)

    async def signup(self, request: SignupRequestDTO) -> PasswordlessLoginResponseDTO:
        if await self._find_user_by_email(request.email) is not None:
            raise AuthServiceError("user already exists")
        otp = await self._otp_util.generate_otp(request.email)
        await self._send_otp_email(request.email, otp)
        return PasswordlessLoginResponseDTO(
            success=True,
            message="signup email queued",
        )

    async def verify_signup(
        self, request: SignupVerifyRequestDTO
    ) -> TokenPairResponseDTO:
        if await self._find_user_by_email(request.email) is not None:
            raise AuthServiceError("user already exists")
        if not await self._otp_util.verify_otp(request.email, request.otp):
            raise AuthServiceError("invalid otp")
        user = User(
            email=request.email,
            organization_id=None,
            role=UserRole.OWNER,
        )
        self._db_session.add(user)
        await self._db_session.flush()
        await self._db_session.commit()
        return self._token_response(user)

    async def verify_passwordless_login(
        self, request: PasswordlessVerifyRequestDTO
    ) -> TokenPairResponseDTO:
        user = await self._get_user_by_email(request.email)
        if not await self._otp_util.verify_otp(request.email, request.otp):
            raise AuthServiceError("invalid otp")
        return self._token_response(user)

    async def refresh_tokens(self, refresh_token: str) -> TokenPairResponseDTO:
        payload = decode_refresh_token(refresh_token, self._auth_settings)
        email = payload.get("email")
        if not isinstance(email, str):
            raise AuthServiceError("invalid refresh token")
        user = await self._get_user_by_email(email)
        return self._token_response(user)
