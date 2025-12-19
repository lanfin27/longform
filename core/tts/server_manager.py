"""
Chatterbox TTS Server Manager
Longform 툴에서 서버를 자동으로 시작/중지하는 기능

사용법:
    from core.tts.server_manager import get_server_manager

    manager = get_server_manager()

    # 서버 시작
    result = manager.start_server()

    # 서버 중지
    manager.stop_server()
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import queue
import logging
import requests

logger = logging.getLogger(__name__)

# ============================================================
# 설정
# ============================================================

# Chatterbox 서버 경로
CHATTER_DIR = Path(r"C:\Users\KIMJAEHEON\chatter")
CHATTER_RUN_SCRIPT = CHATTER_DIR / "run.py"
CHATTER_RUN_BAT = CHATTER_DIR / "run.bat"
CHATTER_VENV_PYTHON = CHATTER_DIR / "venv" / "Scripts" / "python.exe"

# 서버 설정
SERVER_HOST = "localhost"
SERVER_PORT = 8100
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# PID 파일
PID_FILE = CHATTER_DIR / ".server.pid"

# 로그 설정
MAX_LOG_LINES = 500


@dataclass
class ServerStatus:
    """서버 상태 정보"""
    running: bool
    pid: Optional[int] = None
    uptime_seconds: Optional[float] = None
    url: str = SERVER_URL
    error: Optional[str] = None


# 싱글톤 인스턴스
_manager_instance = None


def get_server_manager() -> "ChatterboxServerManager":
    """서버 매니저 싱글톤 인스턴스 반환"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ChatterboxServerManager()
    return _manager_instance


class ChatterboxServerManager:
    """
    Chatterbox TTS 서버 프로세스 관리자

    Streamlit 앱에서 서버를 시작/중지하고 상태를 모니터링
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 서버 경로 설정
        self.server_dir = CHATTER_DIR
        self.venv_python = CHATTER_VENV_PYTHON
        self.run_script = CHATTER_RUN_SCRIPT
        self.run_bat = CHATTER_RUN_BAT

        # 서버 설정
        self.host = SERVER_HOST
        self.port = SERVER_PORT
        self.base_url = SERVER_URL

        # 프로세스 관리
        self.process: Optional[subprocess.Popen] = None
        self.pid_file = PID_FILE

        # 시작 시간
        self._start_time: Optional[datetime] = None

        # 로그 큐
        self._log_queue: queue.Queue = queue.Queue(maxsize=MAX_LOG_LINES)

        self._initialized = True

        # 기존 프로세스 확인
        self._check_existing_process()

    def _check_existing_process(self):
        """기존에 실행 중인 서버 프로세스 확인"""
        # PID 파일 확인
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                # 프로세스가 살아있는지 확인
                if self._is_process_running(pid):
                    logger.info(f"[ServerManager] 기존 서버 프로세스 발견: PID {pid}")
                    return
            except Exception:
                pass
            # PID 파일 삭제
            try:
                self.pid_file.unlink(missing_ok=True)
            except Exception:
                pass

        # 서버가 응답하는지 확인
        if self._check_server_health():
            logger.info("[ServerManager] 서버가 이미 실행 중입니다.")

    def _is_process_running(self, pid: int) -> bool:
        """프로세스가 실행 중인지 확인"""
        try:
            if sys.platform == "win32":
                # Windows
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                # Unix
                os.kill(pid, 0)
                return True
        except Exception:
            return False

    def _check_server_health(self, timeout: float = 2.0) -> bool:
        """서버 연결 확인"""
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=timeout
            )
            return response.status_code == 200
        except Exception:
            return False

    def check_connection(self, timeout: float = 2.0) -> bool:
        """서버 연결 확인 (외부 호출용)"""
        return self._check_server_health(timeout)

    def get_api_status(self) -> Dict[str, Any]:
        """서버 API 상태 조회"""
        try:
            response = requests.get(
                f"{self.base_url}/status",
                timeout=3.0
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {"loaded": False, "error": "Connection failed"}

    # ============================================================
    # 의존성 관리
    # ============================================================

    def check_dependencies(self) -> Dict[str, Any]:
        """서버 의존성 확인"""
        result = {
            "server_dir_exists": self.server_dir.exists(),
            "venv_exists": self.venv_python.exists(),
            "run_script_exists": self.run_script.exists(),
            "run_bat_exists": self.run_bat.exists(),
            "installed": False,
            "missing": []
        }

        if not result["server_dir_exists"]:
            result["missing"].append("server_dir")
            return result

        if not result["venv_exists"]:
            result["missing"].append("venv")
            return result

        # 패키지 확인
        try:
            check_cmd = [
                str(self.venv_python), "-c",
                "import torch; import chatterbox; import fastapi; print('OK')"
            ]
            proc = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.server_dir)
            )
            result["installed"] = proc.returncode == 0 and "OK" in proc.stdout
            if not result["installed"]:
                result["missing"].append("packages")
        except Exception as e:
            result["missing"].append(f"check_error: {e}")

        return result

    # ============================================================
    # 서버 프로세스 관리
    # ============================================================

    def start_server(self, wait_for_ready: bool = True, timeout: int = 60) -> Dict[str, Any]:
        """
        서버 시작

        Args:
            wait_for_ready: 서버가 준비될 때까지 대기할지 여부
            timeout: 대기 시간 (초)

        Returns:
            {"success": bool, "message": str, "pid": int (optional)}
        """
        # 이미 실행 중인지 확인
        if self._check_server_health():
            return {
                "success": True,
                "message": "서버가 이미 실행 중입니다.",
                "already_running": True
            }

        # 의존성 확인
        deps = self.check_dependencies()

        if not deps.get("server_dir_exists"):
            return {
                "success": False,
                "message": f"서버 폴더가 없습니다: {self.server_dir}",
                "error": "server_dir_not_found"
            }

        if not deps.get("venv_exists"):
            return {
                "success": False,
                "message": "가상환경이 없습니다. setup_venv.bat을 먼저 실행하세요.",
                "error": "venv_not_found"
            }

        if not deps.get("installed"):
            return {
                "success": False,
                "message": "필수 패키지가 설치되지 않았습니다. install.bat을 실행하세요.",
                "error": "packages_not_installed",
                "missing": deps.get("missing", [])
            }

        pid = None

        try:
            logger.info(f"[ServerManager] 서버 시작 중... ({self.server_dir})")

            # 방법 1: venv의 python으로 직접 실행 (권장)
            if self.venv_python.exists() and self.run_script.exists():
                cmd = [str(self.venv_python), str(self.run_script)]

                # Windows에서 백그라운드 실행
                if sys.platform == "win32":
                    # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
                    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                    self.process = subprocess.Popen(
                        cmd,
                        cwd=str(self.server_dir),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        creationflags=creation_flags
                    )
                else:
                    # Unix
                    self.process = subprocess.Popen(
                        cmd,
                        cwd=str(self.server_dir),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True
                    )

                pid = self.process.pid
                logger.info(f"[ServerManager] 프로세스 시작됨: PID {pid}")

                # PID 파일 저장
                try:
                    self.pid_file.write_text(str(pid))
                except Exception as e:
                    logger.warning(f"[ServerManager] PID 파일 저장 실패: {e}")

            # 방법 2: run.bat 실행 (fallback)
            elif self.run_bat.exists():
                if sys.platform == "win32":
                    # start /B로 백그라운드 실행
                    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                    self.process = subprocess.Popen(
                        ["cmd", "/c", str(self.run_bat)],
                        cwd=str(self.server_dir),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        creationflags=creation_flags
                    )
                    pid = self.process.pid
                    logger.info(f"[ServerManager] run.bat으로 시작됨: PID {pid}")

                    try:
                        self.pid_file.write_text(str(pid))
                    except Exception:
                        pass
                else:
                    return {
                        "success": False,
                        "message": "run.bat은 Windows에서만 지원됩니다.",
                        "error": "unsupported_platform"
                    }
            else:
                return {
                    "success": False,
                    "message": "실행 스크립트를 찾을 수 없습니다.",
                    "error": "script_not_found"
                }

            self._start_time = datetime.now()

            # 서버 준비 대기
            if wait_for_ready:
                logger.info(f"[ServerManager] 서버 준비 대기 중... (최대 {timeout}초)")
                start_time = time.time()

                while time.time() - start_time < timeout:
                    if self._check_server_health():
                        elapsed = time.time() - start_time
                        logger.info(f"[ServerManager] 서버 준비 완료! ({elapsed:.1f}초)")
                        return {
                            "success": True,
                            "message": f"서버가 시작되었습니다. ({elapsed:.1f}초)",
                            "pid": pid,
                            "url": self.base_url
                        }
                    time.sleep(1)

                # 타임아웃
                return {
                    "success": False,
                    "message": f"서버 시작 타임아웃 ({timeout}초). 로그를 확인하세요.",
                    "error": "timeout",
                    "pid": pid
                }

            return {
                "success": True,
                "message": "서버 시작 요청됨 (백그라운드)",
                "pid": pid
            }

        except Exception as e:
            logger.error(f"[ServerManager] 서버 시작 실패: {e}")
            return {
                "success": False,
                "message": f"서버 시작 실패: {str(e)}",
                "error": str(e)
            }

    def stop_server(self) -> Dict[str, Any]:
        """서버 중지"""
        try:
            # 방법 1: API로 종료 요청
            try:
                requests.post(f"{self.base_url}/shutdown", timeout=5)
                time.sleep(1)
            except Exception:
                pass

            # 방법 2: PID로 프로세스 종료
            pid = None
            if self.pid_file.exists():
                try:
                    pid = int(self.pid_file.read_text().strip())
                except Exception:
                    pass

            if pid:
                if sys.platform == "win32":
                    # Windows: taskkill 사용
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid), "/T"],
                        capture_output=True
                    )
                else:
                    # Unix: kill 사용
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass

            # 방법 3: 포트로 프로세스 종료 (Windows)
            if sys.platform == "win32":
                try:
                    # 포트를 사용하는 프로세스 찾기
                    result = subprocess.run(
                        ["netstat", "-ano"],
                        capture_output=True,
                        text=True
                    )
                    for line in result.stdout.split("\n"):
                        if f":{self.port}" in line and "LISTENING" in line:
                            parts = line.split()
                            if parts:
                                found_pid = parts[-1]
                                subprocess.run(
                                    ["taskkill", "/F", "/PID", found_pid],
                                    capture_output=True
                                )
                except Exception:
                    pass

            # 프로세스 객체 정리
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                self.process = None

            # PID 파일 삭제
            try:
                self.pid_file.unlink(missing_ok=True)
            except Exception:
                pass

            self._start_time = None

            # 종료 확인
            time.sleep(1)
            if not self._check_server_health():
                return {
                    "success": True,
                    "message": "서버가 중지되었습니다."
                }
            else:
                return {
                    "success": False,
                    "message": "서버가 여전히 실행 중입니다."
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"서버 중지 실패: {str(e)}",
                "error": str(e)
            }

    def restart_server(self) -> Dict[str, Any]:
        """서버 재시작"""
        logger.info("서버 재시작 중...")
        self.stop_server()
        time.sleep(2)
        return self.start_server()

    # ============================================================
    # 상태 확인
    # ============================================================

    def is_running(self) -> bool:
        """서버 실행 중 여부"""
        # 헬스 체크로 확인
        if self._check_server_health():
            return True

        # 내부 프로세스 확인
        if self.process and self.process.poll() is None:
            return True

        # PID 파일로 확인
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                if self._is_process_running(pid):
                    return True
            except Exception:
                pass

        # 포트 확인 (외부에서 실행된 경우)
        return self._find_process_on_port(self.port) is not None

    def get_status(self) -> ServerStatus:
        """서버 상태 정보"""
        # 포트에서 프로세스 찾기
        pid = self._get_current_pid()

        if pid or self._check_server_health():
            uptime = None
            if self._start_time:
                uptime = (datetime.now() - self._start_time).total_seconds()

            return ServerStatus(
                running=True,
                pid=pid,
                uptime_seconds=uptime,
                url=SERVER_URL
            )

        return ServerStatus(running=False, url=SERVER_URL)

    def _get_current_pid(self) -> Optional[int]:
        """현재 서버 PID 반환"""
        # 내부 프로세스
        if self.process and self.process.poll() is None:
            return self.process.pid

        # PID 파일
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                if self._is_process_running(pid):
                    return pid
            except Exception:
                pass

        # 포트 기반
        return self._find_process_on_port(self.port)

    def get_logs(self, max_lines: int = 100) -> List[str]:
        """최근 로그 가져오기"""
        logs = []
        try:
            while not self._log_queue.empty() and len(logs) < max_lines:
                logs.append(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        return logs[-max_lines:]

    # ============================================================
    # 내부 유틸리티
    # ============================================================

    def _find_process_on_port(self, port: int) -> Optional[int]:
        """특정 포트를 사용하는 프로세스 PID 찾기"""
        try:
            import psutil
            for conn in psutil.net_connections():
                if conn.laddr.port == port and conn.status == "LISTEN":
                    return conn.pid
        except (ImportError, Exception) as e:
            # psutil이 없거나 권한 문제
            logger.debug(f"포트 확인 실패 (psutil): {e}")

            # Windows에서 netstat로 대체
            if sys.platform == "win32":
                try:
                    result = subprocess.run(
                        ["netstat", "-ano"],
                        capture_output=True,
                        text=True
                    )
                    for line in result.stdout.split("\n"):
                        if f":{port}" in line and "LISTENING" in line:
                            parts = line.split()
                            if parts:
                                return int(parts[-1])
                except Exception:
                    pass
        return None

    # ============================================================
    # 유틸리티
    # ============================================================

    def open_server_folder(self):
        """서버 폴더 열기"""
        try:
            if sys.platform == "win32":
                os.startfile(str(self.server_dir))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(self.server_dir)])
            else:
                subprocess.run(["xdg-open", str(self.server_dir)])
        except Exception as e:
            logger.error(f"폴더 열기 실패: {e}")

    def open_server_logs(self):
        """서버 로그 폴더/파일 열기"""
        log_dir = self.server_dir / "logs"
        if log_dir.exists():
            if sys.platform == "win32":
                os.startfile(str(log_dir))
        else:
            self.open_server_folder()

    def get_server_dir(self) -> Path:
        """서버 디렉토리 경로"""
        return self.server_dir

    def get_server_url(self) -> str:
        """서버 URL"""
        return self.base_url

    def install_dependencies(
        self,
        cuda_version: str = "cu124",
        progress_callback=None
    ) -> Dict[str, Any]:
        """의존성 설치 (install.bat 실행)"""
        install_bat = self.server_dir / "install.bat"

        if not install_bat.exists():
            return {
                "success": False,
                "message": "install.bat 파일이 없습니다.",
                "logs": []
            }

        logs = []

        def log(msg):
            logs.append(msg)
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        try:
            # 새 CMD 창에서 install.bat 실행
            if sys.platform == "win32":
                log("install.bat 실행 중...")
                subprocess.Popen(
                    ["cmd", "/c", "start", "cmd", "/k", str(install_bat)],
                    cwd=str(self.server_dir)
                )
                return {
                    "success": True,
                    "message": "설치가 새 창에서 시작되었습니다. 완료 후 서버를 시작하세요.",
                    "logs": logs
                }
            else:
                return {
                    "success": False,
                    "message": "Windows에서만 지원됩니다.",
                    "logs": logs
                }
        except Exception as e:
            log(f"설치 실패: {e}")
            return {
                "success": False,
                "message": f"설치 실행 실패: {str(e)}",
                "logs": logs
            }

    def setup_venv(self) -> Dict[str, Any]:
        """가상환경 설정 (setup_venv.bat 실행)"""
        setup_bat = self.server_dir / "setup_venv.bat"

        if not setup_bat.exists():
            return {
                "success": False,
                "message": "setup_venv.bat 파일이 없습니다."
            }

        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    ["cmd", "/c", "start", "cmd", "/k", str(setup_bat)],
                    cwd=str(self.server_dir)
                )
                return {
                    "success": True,
                    "message": "가상환경 설정이 새 창에서 시작되었습니다."
                }
            else:
                return {
                    "success": False,
                    "message": "Windows에서만 지원됩니다."
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"설정 실행 실패: {str(e)}"
            }
