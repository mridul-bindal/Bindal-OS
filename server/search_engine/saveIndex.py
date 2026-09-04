# Saves search indexes as JSON files so they can be reused between runs.
import json
from pathlib import Path
from typing import Any


def _make_json_serializable(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {
            key: _make_json_serializable(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [_make_json_serializable(item) for item in value]
    return value


def save_index(index_data: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    if output_path.exists():
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(_make_json_serializable(index_data), file, indent=2)
