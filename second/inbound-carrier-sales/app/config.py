from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Legacy TMS (TCP)
    tms_host: str = "localhost"
    tms_port: int = 9998
    tms_auth_token: str = ""
    tms_timeout_seconds: float = 5.0
    tms_max_retries: int = 3

    # FMCSA
    fmcsa_web_key: str = ""
    fmcsa_base_url: str = "https://mobile.fmcsa.dot.gov/qc/services"

    # Auth for our own endpoints (HappyRobot -> this API)
    api_key: str = ""

    # OTP
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
