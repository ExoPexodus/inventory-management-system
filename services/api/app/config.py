from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://ims:ims_dev_change_me@localhost:5432/ims"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-change-me"
    jwt_access_expire_minutes: int = 60 * 24
    jwt_refresh_expire_days: int = 30
    public_api_url: str = "http://localhost:8001"
    # Set in production for dashboard / automation; protects /v1/admin/*.
    admin_api_token: str | None = None
    # Platform service connection (billing / license control plane)
    platform_api_url: str = ""
    platform_api_secret: str = ""
    platform_base_url: str = "http://platform:8000"
    platform_web_url: str = "http://localhost:3200"
    ims_platform_sync_mode: str = "polling"  # "polling" or "offline"
    ims_platform_sync_interval_seconds: int = 300
    license_sync_interval_seconds: int = 300


settings = Settings()
