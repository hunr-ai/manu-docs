from pydantic import BaseModel, Field, field_validator


class PasswordlessLoginRequestDTO(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: str) -> str:
        normalized_email = email.strip().lower()
        if "@" not in normalized_email:
            raise ValueError("email must be valid")
        return normalized_email


class PasswordlessLoginResponseDTO(BaseModel):
    success: bool
    message: str


class PasswordlessVerifyRequestDTO(PasswordlessLoginRequestDTO):
    otp: str = Field(min_length=1)


class SignupRequestDTO(PasswordlessLoginRequestDTO):
    pass


class SignupVerifyRequestDTO(SignupRequestDTO):
    otp: str = Field(min_length=1)


class RefreshTokenRequestDTO(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPairResponseDTO(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
