"""
프로그레스 및 로그 추적 시스템

기능:
1. 작업 진행 상황 추적
2. 로그 기록 및 표시
3. 에러 로그 관리
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import queue


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


@dataclass
class LogEntry:
    """로그 엔트리"""
    timestamp: str
    level: str
    message: str
    step: str = ""
    details: str = ""


@dataclass
class ProgressState:
    """진행 상태"""
    task_name: str
    current_step: int
    total_steps: int
    step_name: str
    percent: float
    status: str  # running, completed, failed, paused
    started_at: str
    elapsed_seconds: float = 0
    estimated_remaining: float = 0


class ProgressTracker:
    """프로그레스 추적기"""

    def __init__(self, task_name: str, total_steps: int):
        self.task_name = task_name
        self.total_steps = total_steps
        self.current_step = 0
        self.step_name = ""
        self.status = "running"
        self.started_at = datetime.now()
        self.logs: List[LogEntry] = []
        self._lock = threading.Lock()
        self._callbacks: List[Callable] = []

    def add_callback(self, callback: Callable):
        """진행 상황 변경 시 호출될 콜백"""
        self._callbacks.append(callback)

    def _notify_callbacks(self):
        """콜백 호출"""
        state = self.get_state()
        for cb in self._callbacks:
            try:
                cb(state)
            except Exception:
                pass

    def update(self, step: int = None, step_name: str = None, increment: bool = False):
        """진행 상황 업데이트"""
        with self._lock:
            if increment:
                self.current_step += 1
            elif step is not None:
                self.current_step = step

            if step_name:
                self.step_name = step_name

        self._notify_callbacks()

    def log(self, message: str, level: LogLevel = LogLevel.INFO, details: str = ""):
        """로그 추가"""
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level.value,
            message=message,
            step=self.step_name,
            details=details
        )

        with self._lock:
            self.logs.append(entry)

        self._notify_callbacks()

    def info(self, message: str, details: str = ""):
        self.log(message, LogLevel.INFO, details)

    def warning(self, message: str, details: str = ""):
        self.log(message, LogLevel.WARNING, details)

    def error(self, message: str, details: str = ""):
        self.log(message, LogLevel.ERROR, details)

    def success(self, message: str, details: str = ""):
        self.log(message, LogLevel.SUCCESS, details)

    def complete(self, message: str = "완료"):
        """작업 완료"""
        with self._lock:
            self.status = "completed"
            self.current_step = self.total_steps
        self.success(message)
        self._notify_callbacks()

    def fail(self, message: str, details: str = ""):
        """작업 실패"""
        with self._lock:
            self.status = "failed"
        self.error(message, details)
        self._notify_callbacks()

    def get_state(self) -> ProgressState:
        """현재 상태 가져오기"""
        elapsed = (datetime.now() - self.started_at).total_seconds()

        # 남은 시간 추정
        if self.current_step > 0:
            time_per_step = elapsed / self.current_step
            remaining_steps = self.total_steps - self.current_step
            estimated_remaining = time_per_step * remaining_steps
        else:
            estimated_remaining = 0

        return ProgressState(
            task_name=self.task_name,
            current_step=self.current_step,
            total_steps=self.total_steps,
            step_name=self.step_name,
            percent=(self.current_step / self.total_steps * 100) if self.total_steps > 0 else 0,
            status=self.status,
            started_at=self.started_at.isoformat(),
            elapsed_seconds=elapsed,
            estimated_remaining=estimated_remaining
        )

    def get_logs(self, level: LogLevel = None, limit: int = None) -> List[LogEntry]:
        """로그 가져오기"""
        logs = self.logs

        if level:
            logs = [log for log in logs if log.level == level.value]

        if limit:
            logs = logs[-limit:]

        return logs

    def get_errors(self) -> List[LogEntry]:
        """에러 로그만 가져오기"""
        return [log for log in self.logs if log.level == LogLevel.ERROR.value]


class TaskLogManager:
    """전체 태스크 로그 관리"""

    def __init__(self):
        self.log_dir = Path("data/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.active_trackers: Dict[str, ProgressTracker] = {}

    def create_tracker(self, task_id: str, task_name: str, total_steps: int) -> ProgressTracker:
        """새 트래커 생성"""
        tracker = ProgressTracker(task_name, total_steps)
        self.active_trackers[task_id] = tracker
        return tracker

    def get_tracker(self, task_id: str) -> Optional[ProgressTracker]:
        """트래커 가져오기"""
        return self.active_trackers.get(task_id)

    def remove_tracker(self, task_id: str):
        """트래커 제거 및 로그 저장"""
        tracker = self.active_trackers.pop(task_id, None)
        if tracker:
            self._save_log(task_id, tracker)

    def _save_log(self, task_id: str, tracker: ProgressTracker):
        """로그 파일로 저장"""
        log_file = self.log_dir / f"{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        data = {
            "task_name": tracker.task_name,
            "status": tracker.status,
            "started_at": tracker.started_at.isoformat(),
            "total_steps": tracker.total_steps,
            "logs": [asdict(log) for log in tracker.logs]
        }

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_saved_logs(self, limit: int = 20) -> List[Dict]:
        """저장된 로그 목록"""
        log_files = sorted(self.log_dir.glob("*.json"), reverse=True)[:limit]

        logs = []
        for f in log_files:
            try:
                with open(f, "r", encoding="utf-8") as file:
                    logs.append(json.load(file))
            except Exception:
                pass

        return logs


# 싱글톤
_log_manager = None

def get_log_manager() -> TaskLogManager:
    global _log_manager
    if _log_manager is None:
        _log_manager = TaskLogManager()
    return _log_manager
