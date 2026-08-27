"""Application configuration.

Values are read from environment variables, then from a `.env` file, then
fall back to the defaults below. See `.env.example` for the documented list.

Import the singleton, never construct Settings yourself:

    from app.config import settings
    settings.max_upload_bytes
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Typed configuration for the whole backend."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Server -----------------------------------------------------------
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000

    # Stored as a raw string so a comma-separated env var parses predictably.
    # Pydantic would otherwise try to read a list-typed env var as JSON.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Uploads ----------------------------------------------------------
    max_upload_mb: int = Field(default=5, ge=1, le=25)
    allowed_extensions: str = ".pdf,.docx,.txt"

    # --- Storage ----------------------------------------------------------
    database_path: str = "storage/app.db"

    # There is deliberately no upload directory setting.
    #
    # The uploaded file is read from the request into memory, analysed, and
    # dropped. Only the extracted text is persisted, inside the report. The
    # original PDF - which carries the candidate's name, phone number, email
    # address and often a home address - is never written to disk at all.
    #
    # This started as a `UPLOAD_DIR` setting that nothing ever wrote to, which
    # is worse than either alternative: the config, .env.example and README all
    # described a directory of stored resumes that did not exist, so anyone
    # auditing how this project handles personal data would have been told
    # something false. Removed rather than implemented - not storing the file
    # is the better behaviour, so the honest thing is to say so.
    #
    # If a future feature genuinely needs the original bytes (re-parsing with a
    # better extractor, say), add it back deliberately, and update the consent
    # wording in docs/Customer Testing Plan.md at the same time.

    # --- Matching ---------------------------------------------------------
    weight_semantic: float = Field(default=0.40, ge=0.0, le=1.0)
    weight_skill: float = Field(default=0.30, ge=0.0, le=1.0)
    weight_lexical: float = Field(default=0.20, ge=0.0, le=1.0)
    weight_fit: float = Field(default=0.10, ge=0.0, le=1.0)

    # --- Models -----------------------------------------------------------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    use_transformer_embeddings: bool = True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _weights_must_sum_to_one(self) -> "Settings":
        """Reject weight sets that do not sum to 1.0.

        Without this the score silently changes range - weights summing to 0.8
        cap the maximum match at 80 and nobody notices until the report is
        being written.
        """
        total = (
            self.weight_semantic + self.weight_skill
            + self.weight_lexical + self.weight_fit
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Match weights must sum to 1.0, got {total:.4f}. "
                f"Check WEIGHT_SEMANTIC / WEIGHT_SKILL / WEIGHT_LEXICAL / "
                f"WEIGHT_FIT in your .env file."
            )
        return self

    @field_validator("app_env")
    @classmethod
    def _known_env(cls, value: str) -> str:
        allowed = {"development", "test", "production"}
        if value not in allowed:
            raise ValueError(f"APP_ENV must be one of {sorted(allowed)}")
        return value

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------

    @cached_property
    def match_weights(self) -> dict[str, float]:
        """Weights in the shape matcher.match() expects."""
        return {
            "semantic": self.weight_semantic,
            "skill": self.weight_skill,
            "lexical": self.weight_lexical,
            "fit": self.weight_fit,
        }

    @cached_property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @cached_property
    def extensions(self) -> set[str]:
        """Allowed file extensions, lowercase, each with a leading dot."""
        return {
            ext.strip().lower() if ext.strip().startswith(".") else f".{ext.strip().lower()}"
            for ext in self.allowed_extensions.split(",")
            if ext.strip()
        }

    @cached_property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @cached_property
    def database_file(self) -> Path:
        """Absolute path to the SQLite file, parent directory created."""
        path = Path(self.database_path)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @cached_property
    def data_dir(self) -> Path:
        return BACKEND_ROOT / "data"

    @cached_property
    def artifacts_dir(self) -> Path:
        """Where trained model files live. Created so training can write here."""
        path = BACKEND_ROOT / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
