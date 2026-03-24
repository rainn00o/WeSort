from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from paths import LOGS_DIR


@dataclass(slots=True)
class StepErrorSummary:
    step_name: str
    error_type: str
    error_message: str
    context: dict
    created_at: str

    def to_payload(self) -> dict:
        return {
            "step_name": self.step_name,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "context": self.context,
            "created_at": self.created_at,
        }

    def to_lines(self) -> list[str]:
        lines = [
            f"step_name: {self.step_name}",
            f"error_type: {self.error_type}",
            f"error_message: {self.error_message}",
            f"created_at: {self.created_at}",
        ]
        if self.context:
            lines.append("context:")
            lines.extend(f"- {key}: {value}" for key, value in self.context.items())
        return lines


class StepLogger:
    def __init__(self, root_dir: Path = LOGS_DIR) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_dir = root_dir / timestamp
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def write(self, step_name: str, payload: dict) -> tuple[Path, Path]:
        return self._write_files(step_name, payload, self._payload_to_lines(payload))

    def write_error(
        self,
        step_name: str,
        error: Exception,
        context: dict | None = None,
    ) -> tuple[Path, Path]:
        summary = StepErrorSummary(
            step_name=step_name,
            error_type=type(error).__name__,
            error_message=str(error),
            context=context or {},
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        return self._write_files(
            f"{step_name}_error",
            summary.to_payload(),
            summary.to_lines(),
        )

    def _write_files(self, file_stem: str, payload: dict, lines: list[str]) -> tuple[Path, Path]:
        json_path = self.session_dir / f"{file_stem}.json"
        txt_path = self.session_dir / f"{file_stem}.txt"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        txt_path.write_text("\n".join(lines), encoding="utf-8")
        return json_path, txt_path

    def _payload_to_lines(self, payload: dict) -> list[str]:
        lines: list[str] = []
        for key, value in payload.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                lines.extend(f"- {sub_key}: {sub_value}" for sub_key, sub_value in value.items())
                continue
            lines.append(f"{key}: {value}")
        return lines
