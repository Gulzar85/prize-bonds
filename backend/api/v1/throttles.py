from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


class SignupRateThrottle(AnonRateThrottle):
    scope = "signup"


class PasswordResetRateThrottle(AnonRateThrottle):
    scope = "password_reset"


class MFARateThrottle(UserRateThrottle):
    scope = "mfa"
