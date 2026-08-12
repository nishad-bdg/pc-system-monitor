import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("SYSTEM_INFO_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("SYSTEM_INFO_MONGO_DB", "system_info")
MONGO_COLLECTION = "reports"
MONGO_USERS = "users"
MONGO_API_KEYS = "api_keys"

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-32bytes-min")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
