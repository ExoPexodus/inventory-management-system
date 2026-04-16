from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://platform:platform_dev_change_me@localhost:5433/platform"
    redis_url: str = "redis://localhost:6379/1"
    jwt_secret: str = "platform-dev-only-change-me"
    jwt_access_expire_minutes: int = 60 * 24
    main_api_url: str = "http://localhost:8001"
    storage_path: str = "./uploads"


settings = Settings()
