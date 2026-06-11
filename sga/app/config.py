from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    environment: str = "development"
    debug: bool = True
    app_name: str = "SGA Aegis"
    app_version: str = "0.1.0"

    class Config:
        env_file = ".env"
        extra = "ignore"  # tolerate LOCAL_DATABASE_URL / CLOUD_DATABASE_URL used by sync_db.py


settings = Settings()
