"""
Pipeline Tracer & Checkpoint Logging Module for Context Warehouse.
Captures end-to-end execution telemetry, step-by-step payloads, prompts, schemas, and metrics.
"""

import time
from typing import Any, Dict, List, Optional


class Checkpoint:
    """Đại diện cho một Checkpoint log trong quá trình xử lý."""

    def __init__(
        self,
        step: int,
        id: str,
        name: str,
        description: str,
        status: str = "pending",
        payload: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0
    ) -> None:
        self.step = step
        self.id = id
        self.name = name
        self.description = description
        self.status = status  # 'pending', 'running', 'success', 'warning', 'error'
        self.payload = payload or {}
        self.duration_ms = duration_ms
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp,
            "payload": self.payload
        }


class PipelineTracer:
    """Bộ thu thập và theo dõi toàn bộ các Checkpoint trong chu trình Context Warehouse."""

    def __init__(self, query: str) -> None:
        self.query = query
        self.start_time = time.time()
        self.checkpoints: List[Checkpoint] = []
        self._current_step_start = time.time()

    def record_checkpoint(
        self,
        step: int,
        id: str,
        name: str,
        description: str,
        status: str = "success",
        payload: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None
    ) -> Checkpoint:
        """Ghi nhận một Checkpoint hoàn thành."""
        if duration_ms is None:
            duration_ms = (time.time() - self._current_step_start) * 1000

        cp = Checkpoint(
            step=step,
            id=id,
            name=name,
            description=description,
            status=status,
            payload=payload or {},
            duration_ms=duration_ms
        )
        self.checkpoints.append(cp)
        self._current_step_start = time.time()
        return cp

    def start_step_timer(self) -> None:
        """Bắt đầu đếm giờ cho bước hiện tại."""
        self._current_step_start = time.time()

    def get_summary(self) -> Dict[str, Any]:
        """Tổng hợp toàn bộ dữ liệu telemetry của pipeline."""
        total_duration_ms = (time.time() - self.start_time) * 1000
        has_errors = any(cp.status == "error" for cp in self.checkpoints)
        has_warnings = any(cp.status == "warning" for cp in self.checkpoints)

        overall_status = "error" if has_errors else ("warning" if has_warnings else "success")

        return {
            "query": self.query,
            "total_duration_ms": round(total_duration_ms, 2),
            "overall_status": overall_status,
            "checkpoint_count": len(self.checkpoints),
            "checkpoints": [cp.to_dict() for cp in self.checkpoints]
        }
