from dataclasses import dataclass
import os
from pathlib import Path
import typing as ty

from dotenv import dotenv_values


frozen = dataclass(frozen=True, slots=True, kw_only=True)


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid bool value: {value}")


def _parse_value(value: str, target_type: type) -> ty.Any:
    if target_type is bool:
        return _parse_bool(value)
    if target_type is Path:
        return Path(value)
    return target_type(value)


@frozen
class Config:
    DOWNLOAD_CONCURRENT_MAX: int = 200
    COMPUTE_PROCESS_MAX: int = os.cpu_count() or 1
    COMPUTE_PROCESS_TIMEOUT: int = 300
    DOWNLOAD_CONTENT_RETRY: int = 6
    PDF_CONVERTION_MAX_RETRY: int = 3
    BOOK_NAME: str = "learncpp.pdf"
    REMOVE_CACHE_ON_SUCCESS: bool = False

    LEARNCPP: str = "https://www.learncpp.com"
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    CACHE_FOLDER: Path = PROJECT_ROOT / ".tmp"
    ERROR_LOG: Path = CACHE_FOLDER / "error"
    HTML_FOLDER: Path = CACHE_FOLDER / "html"
    HTML_CHAPTER: Path = HTML_FOLDER / "chapters"
    CHAPTER_OUTLINE: Path = HTML_FOLDER / "outline.html"
    PDF_FOLDER: Path = CACHE_FOLDER / "pdf"
    PDF_CHAPTER: Path = PDF_FOLDER / HTML_CHAPTER.name
    PDF_MERGED_CHAPTER_FOLDER: Path = PDF_FOLDER / "learncpp"

    PLAYWRIGHT_TIMEOUT_MS: int = 120_000
    PDF_FORMAT: str = "A4"
    PDF_SCALE: float = 1.0

    @property
    def BOOK_PATH(self) -> Path:
        return self.PROJECT_ROOT / self.BOOK_NAME

    @classmethod
    def from_env(cls, env_file: Path = Path.cwd() / ".env") -> "Config":
        raw_values = dotenv_values(env_file)
        parsed_values: dict[str, ty.Any] = {}

        for key, value in raw_values.items():
            if value is None:
                continue

            target_type = cls.__annotations__.get(key)
            if target_type is None:
                continue

            try:
                parsed_values[key] = _parse_value(value, target_type)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid value for {key}, make sure it can be parsed as {target_type}"
                ) from exc

        return cls(**parsed_values)