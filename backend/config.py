import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env file if available
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseModel):
    PROJECT_NAME: str = "AquaSense Smart Irrigation System"
    VERSION: str = "1.0.0"
    TAGLINE: str = "Smart Irrigation. Smarter Growing."
    
    # Server network
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
    
    # Database path
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "aquasense.db"))
    
    # Security: API Key for device and control endpoints
    # Can be configured via environment variable
    API_KEY: str = os.getenv("API_KEY", "aquasense_secret_key_2026")
    
    # Device offline timeout in seconds
    DEVICE_TIMEOUT_SECONDS: int = int(os.getenv("DEVICE_TIMEOUT_SECONDS", "45"))
    
    # Default agronomic & safety thresholds
    DEFAULT_DRY_THRESHOLD: float = float(os.getenv("DEFAULT_DRY_THRESHOLD", "15.0"))
    DEFAULT_WET_THRESHOLD: float = float(os.getenv("DEFAULT_WET_THRESHOLD", "25.0"))
    DEFAULT_MAX_RUNTIME_SEC: int = int(os.getenv("DEFAULT_MAX_RUNTIME_SEC", "20"))
    DEFAULT_COOLDOWN_SEC: int = int(os.getenv("DEFAULT_COOLDOWN_SEC", "60"))
    
    # FC-28 default ADC calibration points (ESP32 12-bit ADC: 0 - 4095)
    # Air/Dry: ~3500, Water/Wet: ~1400
    DEFAULT_SOIL_DRY_RAW: int = 3500
    DEFAULT_SOIL_WET_RAW: int = 1400

    # Firebase Realtime Database & Analytics Configuration
    FIREBASE_ENABLED: bool = os.getenv("FIREBASE_ENABLED", "True").lower() in ("true", "1", "yes")
    FIREBASE_DATABASE_URL: str = os.getenv(
        "FIREBASE_DATABASE_URL",
        "https://aquasense-62dda-default-rtdb.asia-southeast1.firebasedatabase.app"
    )
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "aquasense-62dda")
    FIREBASE_API_KEY: str = os.getenv("FIREBASE_API_KEY", "AIzaSyCfSBPlTeE9MJaXMmwngwHNQuthbRCFFrs")
    FIREBASE_AUTH_DOMAIN: str = os.getenv("FIREBASE_AUTH_DOMAIN", "aquasense-62dda.firebaseapp.com")
    FIREBASE_STORAGE_BUCKET: str = os.getenv("FIREBASE_STORAGE_BUCKET", "aquasense-62dda.firebasestorage.app")
    FIREBASE_MESSAGING_SENDER_ID: str = os.getenv("FIREBASE_MESSAGING_SENDER_ID", "811550760426")
    FIREBASE_APP_ID: str = os.getenv("FIREBASE_APP_ID", "1:811550760426:web:be7cf64f30fd21f5c16693")
    FIREBASE_MEASUREMENT_ID: str = os.getenv("FIREBASE_MEASUREMENT_ID", "G-ZKXDJ7KLWS")

settings = Settings()
