from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://ims:ims_dev_change_me@localhost:5432/ims"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-change-me"
    jwt_access_expire_minutes: int = 60 * 24
    jwt_refresh_expire_days: int = 30
    # Set in production for dashboard / automation; protects /v1/admin/*.
    admin_api_token: str | None = None


settings = Settings()
