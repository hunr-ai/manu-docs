# Backend OTP Utility

The OTP utility lives in `backend/utils/otp_utils.py`. It creates counter-based HOTP codes with `pyotp`, stores the active OTP state in Redis, and deletes that state after a successful verification.

## Settings

OTP behavior is configured by `OTPSettings` in `backend/config/settings/schemas/otp_settings.py`.

```yaml
otp:
  cooldown-seconds: 300
  expiry-seconds: 900
  max-attempts-per-day: 5
```

These values are regular configuration, not secrets. They belong in environment YAML such as `dev.yaml` or `prod.yaml`, not in `secrets.yaml`.

## Redis Keys

The utility normalizes email addresses by trimming whitespace and lowercasing before building Redis keys.

- `otp:{email}` stores the active OTP, HOTP counter, and send timestamp.
- `otp-counter:{email}` stores the next HOTP counter.
- `otp-attempts:{email}` stores the number of OTP sends in the current 24-hour window.

The `otp:{email}` key expires after `OTPSettings.expiry_seconds`. The `otp-attempts:{email}` key expires after 24 hours.

## Error Codes

`generate_otp()` raises `OTPUtilError` for expected business-rule failures. The exception exposes a stable `code` value through `OTPErrorCode`.

| Code | Meaning |
| --- | --- |
| `cooldown_not_elapsed` | A previous OTP is still inside the configured cooldown window. |
| `attempt_limit_reached` | The email has reached `max_attempts_per_day` for the current 24-hour window. |

Example:

```python
from utils.otp_utils import OTPErrorCode, OTPUtilError

try:
    otp = await otp_util.generate_otp(email)
except OTPUtilError as error:
    if error.code is OTPErrorCode.COOLDOWN_NOT_ELAPSED:
        ...
```

## Verification

`verify_otp(email, otp)` returns `True` only when the provided code matches the active Redis state. On success, the utility deletes `otp:{email}` so the OTP cannot be reused. Incorrect or expired OTPs return `False`.
