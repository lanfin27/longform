# -*- coding: utf-8 -*-
"""
utils/external_launcher.py
외부 프로젝트 실행 유틸리티 (v1.1)

v1.1: NanoWater 로컬 HTTP 서버 지원 추가
      - ES6 모듈 및 WASM은 file:// 프로토콜에서 작동하지 않음
      - local_server 타입 추가: HTTP 서버 자동 시작 후 브라우저 열기

기능:
- Streamlit 프로젝트 실행
- 로컬 HTTP 서버 기반 프로젝트 실행 (ES6/WASM)
- 브라우저 확장 프로그램 폴더/파일 열기
- 프로젝트 상태 확인
"""

import subprocess
import os
import sys
import socket
import webbrowser
import threading
import time
from pathlib import Path
from typing import Dict, Optional


# 외부 프로젝트 설정
EXTERNAL_PROJECTS = {
    "vrewauto": {
        "name": "VrewAuto",
        "icon": "🎬",
        "path": r"C:\Users\KIMJAEHEON\vrewauto",
        "entry_point": "app.py",
        "port": 8504,
        "type": "streamlit",
        "description": "Vrew 자동화 프로젝트"
    },
    "nanowater": {
        "name": "NanoWater",
        "icon": "🍌",
        "path": r"C:\Users\KIMJAEHEON\nanowater",
        "entry_point": "index.html",
        "port": 8765,
        "type": "local_server",  # v1.1: ES6/WASM 지원을 위해 로컬 HTTP 서버 사용
        "description": "나노바나나 워터마크 제거기 (LaMa AI 기반)"
    }
}


def is_port_in_use(port: int) -> bool:
    """포트 사용 중인지 확인"""
    if port is None:
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(('localhost', port)) == 0
    except Exception:
        return False


def get_project_status(project_id: str) -> Dict:
    """프로젝트 실행 상태 확인"""
    if project_id not in EXTERNAL_PROJECTS:
        return {"exists": False, "running": False, "port": None, "url": None}

    project = EXTERNAL_PROJECTS[project_id]
    project_path = Path(project["path"])

    # 프로젝트 경로 존재 확인
    if not project_path.exists():
        return {
            "exists": False,
            "running": False,
            "port": None,
            "url": None,
            "error": "경로 없음"
        }

    # Streamlit 또는 로컬 서버 프로젝트인 경우 포트 확인
    if project["type"] in ("streamlit", "local_server"):
        port = project.get("port")
        if port:
            running = is_port_in_use(port)
            return {
                "exists": True,
                "running": running,
                "port": port,
                "url": f"http://localhost:{port}" if running else None,
                "type": project["type"]
            }

    # 브라우저 확장 프로그램 등
    return {
        "exists": True,
        "running": False,
        "port": None,
        "url": None,
        "type": project["type"]
    }


def launch_streamlit_project(project_id: str, new_terminal: bool = True) -> Dict:
    """
    Streamlit 프로젝트 실행

    Args:
        project_id: 프로젝트 ID
        new_terminal: 새 터미널 창에서 실행할지

    Returns:
        실행 결과 딕셔너리
    """
    if project_id not in EXTERNAL_PROJECTS:
        return {
            "success": False,
            "message": f"알 수 없는 프로젝트: {project_id}",
            "port": None,
            "url": None
        }

    project = EXTERNAL_PROJECTS[project_id]

    if project["type"] != "streamlit":
        return {
            "success": False,
            "message": f"{project['name']}은(는) Streamlit 프로젝트가 아닙니다.",
            "port": None,
            "url": None
        }

    project_path = Path(project["path"])
    entry_point = project["entry_point"]
    port = project["port"]

    # 프로젝트 경로 확인
    if not project_path.exists():
        return {
            "success": False,
            "message": f"프로젝트 경로가 존재하지 않습니다: {project_path}",
            "port": None,
            "url": None
        }

    # 엔트리 포인트 확인
    entry_file = project_path / entry_point
    if not entry_file.exists():
        # 대체 엔트리 포인트 시도
        for alt in ["app.py", "main.py", "run.py", "streamlit_app.py"]:
            if (project_path / alt).exists():
                entry_point = alt
                entry_file = project_path / alt
                break
        else:
            return {
                "success": False,
                "message": f"실행 파일을 찾을 수 없습니다: {entry_point}",
                "port": None,
                "url": None
            }

    # 이미 실행 중인지 확인
    if is_port_in_use(port):
        return {
            "success": False,
            "message": f"포트 {port}가 이미 사용 중입니다. 이미 실행 중일 수 있습니다.",
            "port": port,
            "url": f"http://localhost:{port}",
            "already_running": True
        }

    try:
        if sys.platform == "win32" and new_terminal:
            # Windows: 새 터미널 창에서 실행
            terminal_cmd = f'start "{project["name"]}" cmd /k "cd /d {project_path} && streamlit run {entry_point} --server.port {port}"'
            subprocess.Popen(terminal_cmd, shell=True)
        else:
            # 백그라운드 실행
            cmd = [
                sys.executable, "-m", "streamlit", "run",
                str(entry_file),
                "--server.port", str(port),
                "--server.headless", "true"
            ]
            kwargs = {"cwd": str(project_path)}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(cmd, **kwargs)

        return {
            "success": True,
            "message": f"{project['name']} 실행 시작됨",
            "port": port,
            "url": f"http://localhost:{port}"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"실행 오류: {str(e)}",
            "port": port,
            "url": None
        }


def open_folder(path: str) -> bool:
    """폴더를 파일 탐색기로 열기"""
    try:
        path_obj = Path(path)
        if not path_obj.exists():
            print(f"[ExternalLauncher] 폴더 없음: {path}")
            return False

        if sys.platform == "win32":
            os.startfile(str(path_obj))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path_obj)])
        else:
            subprocess.run(["xdg-open", str(path_obj)])

        print(f"[ExternalLauncher] 폴더 열림: {path}")
        return True
    except Exception as e:
        print(f"[ExternalLauncher] 폴더 열기 실패: {e}")
        return False


def open_in_browser(url: str) -> bool:
    """브라우저에서 URL 열기"""
    try:
        webbrowser.open(url)
        print(f"[ExternalLauncher] 브라우저 열림: {url}")
        return True
    except Exception as e:
        print(f"[ExternalLauncher] 브라우저 열기 실패: {e}")
        return False


def open_html_file(file_path: str) -> bool:
    """HTML 파일을 브라우저에서 열기"""
    try:
        path_obj = Path(file_path)
        if not path_obj.exists():
            print(f"[ExternalLauncher] 파일 없음: {file_path}")
            return False

        file_url = f"file:///{path_obj.as_posix()}"
        return open_in_browser(file_url)
    except Exception as e:
        print(f"[ExternalLauncher] HTML 열기 실패: {e}")
        return False


def launch_browser_extension(project_id: str) -> Dict:
    """
    브라우저 확장 프로그램 프로젝트 열기

    Args:
        project_id: 프로젝트 ID

    Returns:
        결과 딕셔너리
    """
    if project_id not in EXTERNAL_PROJECTS:
        return {
            "success": False,
            "message": f"알 수 없는 프로젝트: {project_id}"
        }

    project = EXTERNAL_PROJECTS[project_id]
    project_path = Path(project["path"])

    if not project_path.exists():
        return {
            "success": False,
            "message": f"프로젝트 경로가 존재하지 않습니다: {project_path}"
        }

    # index.html 열기
    entry_file = project_path / project.get("entry_point", "index.html")
    if entry_file.exists():
        success = open_html_file(str(entry_file))
        if success:
            return {
                "success": True,
                "message": f"{project['name']} index.html 열림"
            }

    # index.html 없으면 폴더 열기
    success = open_folder(str(project_path))
    return {
        "success": success,
        "message": f"{project['name']} 폴더 열림" if success else "폴더 열기 실패"
    }


def launch_local_server_project(project_id: str) -> Dict:
    """
    v1.1: 로컬 HTTP 서버 기반 프로젝트 실행

    ES6 모듈 및 WASM을 사용하는 프로젝트는 file:// 프로토콜에서 작동하지 않음.
    로컬 HTTP 서버를 시작하고 브라우저를 열어야 함.

    Args:
        project_id: 프로젝트 ID

    Returns:
        결과 딕셔너리
    """
    if project_id not in EXTERNAL_PROJECTS:
        return {
            "success": False,
            "message": f"알 수 없는 프로젝트: {project_id}"
        }

    project = EXTERNAL_PROJECTS[project_id]
    project_path = Path(project["path"])
    port = project.get("port", 8765)

    if not project_path.exists():
        return {
            "success": False,
            "message": f"프로젝트 경로가 존재하지 않습니다: {project_path}"
        }

    url = f"http://localhost:{port}"

    # 이미 서버가 실행 중인지 확인
    if is_port_in_use(port):
        # 이미 실행 중이면 브라우저만 열기
        open_in_browser(url)
        return {
            "success": True,
            "message": f"{project['name']} 이미 실행 중 - 브라우저 열림",
            "port": port,
            "url": url,
            "already_running": True
        }

    # launch.py 스크립트가 있으면 사용
    launch_script = project_path / "launch.py"
    if launch_script.exists():
        try:
            if sys.platform == "win32":
                # Windows: 새 터미널 창에서 실행
                terminal_cmd = f'start "{project["name"]}" cmd /k "cd /d {project_path} && python launch.py"'
                subprocess.Popen(terminal_cmd, shell=True)
            else:
                # 백그라운드 실행
                subprocess.Popen(
                    [sys.executable, str(launch_script)],
                    cwd=str(project_path),
                    start_new_session=True
                )

            return {
                "success": True,
                "message": f"{project['name']} 서버 시작됨",
                "port": port,
                "url": url
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"launch.py 실행 오류: {str(e)}",
                "port": port,
                "url": None
            }

    # launch.py가 없으면 기본 HTTP 서버 시작
    try:
        def start_http_server():
            import http.server
            import socketserver
            os.chdir(str(project_path))

            class QuietHandler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, format, *args):
                    pass  # 로그 숨김

                def end_headers(self):
                    # CORS 헤더 추가
                    self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
                    self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
                    super().end_headers()

            with socketserver.TCPServer(("localhost", port), QuietHandler) as httpd:
                httpd.serve_forever()

        server_thread = threading.Thread(target=start_http_server, daemon=True)
        server_thread.start()

        # 서버 시작 대기
        time.sleep(0.5)

        # 브라우저 열기
        open_in_browser(url)

        return {
            "success": True,
            "message": f"{project['name']} 서버 시작됨 (기본 HTTP 서버)",
            "port": port,
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"HTTP 서버 시작 오류: {str(e)}",
            "port": port,
            "url": None
        }


def launch_project(project_id: str) -> Dict:
    """
    프로젝트 타입에 따라 적절한 방식으로 실행

    Args:
        project_id: 프로젝트 ID

    Returns:
        실행 결과 딕셔너리
    """
    if project_id not in EXTERNAL_PROJECTS:
        return {
            "success": False,
            "message": f"알 수 없는 프로젝트: {project_id}"
        }

    project = EXTERNAL_PROJECTS[project_id]
    project_type = project.get("type", "unknown")

    if project_type == "streamlit":
        return launch_streamlit_project(project_id)
    elif project_type == "local_server":
        # v1.1: ES6/WASM 프로젝트용 로컬 HTTP 서버
        return launch_local_server_project(project_id)
    elif project_type == "browser_extension":
        return launch_browser_extension(project_id)
    else:
        # 기본: 폴더 열기
        success = open_folder(project["path"])
        return {
            "success": success,
            "message": f"{project['name']} 폴더 열림" if success else "폴더 열기 실패"
        }


def get_all_projects_status() -> Dict[str, Dict]:
    """모든 프로젝트의 상태 조회"""
    statuses = {}
    for project_id in EXTERNAL_PROJECTS:
        statuses[project_id] = get_project_status(project_id)
    return statuses
