from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres1:RrBVKWJuBLjwIyLuSU5qBOGIKpPGqQDI@dpg-d6s37lf5r7bs7387ntrg-a.frankfurt-postgres.render.com/volunteer_db_udj4")
    REDIS_URL: str = os.getenv("redis://default:LmfxjGzegWdQxQDBDuisdZGdwiETiqIp@interchange.proxy.rlwy.net:14241")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "OfjwqS25Hs1")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()