from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    adcm_base_url: str = os.getenv(
        "ADCM_BASE_URL", "https://backend.adcm.airborne-division.de"
    ).rstrip("/")
    adcm_root_unit_id: int = int(os.getenv("ADCM_ROOT_UNIT_ID", "13378"))
    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite:///./data/lineup-analyzer.db"
    )
    app_timezone: str = os.getenv("APP_TIMEZONE", "Europe/Berlin")
    sync_timeout_seconds: float = float(os.getenv("SYNC_TIMEOUT_SECONDS", "15"))
    auto_import_enabled: bool = os.getenv("AUTO_IMPORT_ENABLED", "true").lower() in {
        "1", "true", "yes", "on"
    }
    auto_import_initial_max_id: int = int(os.getenv("AUTO_IMPORT_INITIAL_MAX_ID", "1000"))
    auto_import_request_delay_ms: int = int(os.getenv("AUTO_IMPORT_REQUEST_DELAY_MS", "100"))


settings = Settings()
