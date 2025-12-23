# -*- coding: utf-8 -*-
"""
인포그래픽 렌더러 팩토리

Selenium WebDriver 기반 렌더러 제공
(Playwright는 Python 3.13 + Windows + Streamlit 환경에서 asyncio 충돌로 사용 불가)

변경사항 (v3.0):
- Playwright 완전 제거
- Selenium만 지원
"""

import os
import sys
import subprocess
from typing import Optional, Dict, Callable

from utils.models.infographic import InfographicData


def check_selenium() -> bool:
    """Selenium 사용 가능 여부 확인"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.quit()
        return True
    except Exception as e:
        print(f"[Factory] Selenium 사용 불가: {e}")
        return False


def check_ffmpeg() -> bool:
    """FFmpeg 사용 가능 여부 확인"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_thumbnail_generator(output_dir: str = "outputs/infographic_thumbnails"):
    """
    썸네일 생성기 반환 (Selenium 기반)

    Args:
        output_dir: 출력 디렉토리

    Returns:
        SeleniumThumbnailGenerator 인스턴스

    Raises:
        RuntimeError: 렌더러를 찾을 수 없을 때
    """
    try:
        from utils.infographic_thumbnail import (
            SeleniumThumbnailGenerator,
            check_selenium_available
        )

        ok, msg = check_selenium_available()
        if ok:
            print("✅ Selenium WebDriver 사용")
            return SeleniumThumbnailGenerator(output_dir)
        else:
            raise RuntimeError(f"Selenium 초기화 실패: {msg}")

    except ImportError as e:
        raise RuntimeError(f"썸네일 모듈 로드 실패: {e}")
    except Exception as e:
        raise RuntimeError(f"썸네일 생성기 초기화 실패: {e}")


def generate_thumbnails(
    infographic_data: InfographicData,
    output_dir: str = "outputs/infographic_thumbnails",
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[int, bool]:
    """
    썸네일 생성 (팩토리 패턴)

    Args:
        infographic_data: 인포그래픽 데이터
        output_dir: 출력 디렉토리
        progress_callback: 진행 콜백

    Returns:
        {scene_id: success, ...}
    """
    generator = get_thumbnail_generator(output_dir)
    return generator.generate_all_thumbnails(infographic_data, progress_callback)


def get_video_recorder(output_dir: str = "outputs/infographic_videos"):
    """
    동영상 녹화기 반환 (Selenium + FFmpeg 기반)

    Args:
        output_dir: 출력 디렉토리

    Returns:
        InfographicVideoRecorder 인스턴스

    Raises:
        RuntimeError: 녹화기를 초기화할 수 없을 때
    """
    try:
        from utils.infographic_video_recorder import (
            InfographicVideoRecorder,
            check_video_recorder_available
        )

        ok, msg = check_video_recorder_available()
        if ok:
            print("✅ Selenium + FFmpeg 비디오 레코더 사용")
            return InfographicVideoRecorder(output_dir)
        else:
            raise RuntimeError(f"비디오 레코더 초기화 실패:\n{msg}")

    except ImportError as e:
        raise RuntimeError(f"비디오 모듈 로드 실패: {e}")
    except Exception as e:
        raise RuntimeError(f"비디오 녹화기 초기화 실패: {e}")


def record_videos(
    infographic_data: InfographicData,
    duration: float = 10.0,
    output_dir: str = "outputs/infographic_videos",
    fast_mode: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[int, str]:
    """
    동영상 녹화 (팩토리 패턴)

    Args:
        infographic_data: 인포그래픽 데이터
        duration: 녹화 시간 (초)
        output_dir: 출력 디렉토리
        fast_mode: True=빠른 생성(정적 이미지 기반), False=프레임 캡처(CSS 애니메이션 반영)
        progress_callback: 진행 콜백

    Returns:
        {scene_id: video_path, ...}
    """
    recorder = get_video_recorder(output_dir)
    try:
        return recorder.record_multiple_scenes(
            infographic_data,
            duration=duration,
            fast_mode=fast_mode,
            progress_callback=progress_callback
        )
    finally:
        recorder.close()


# ============================================
# 환경 확인 유틸리티
# ============================================

def check_environment() -> Dict[str, any]:
    """렌더링 환경 확인"""
    results = {
        "python_version": sys.version,
        "platform": sys.platform,
        "selenium": False,
        "pillow": False,
        "ffmpeg": False,
        "recommended": None
    }

    # Selenium 확인
    try:
        from selenium import webdriver
        from webdriver_manager.chrome import ChromeDriverManager
        results["selenium"] = True
        results["selenium_version"] = "설치됨"
    except ImportError:
        results["selenium_version"] = "미설치"

    # Pillow 확인
    try:
        from PIL import Image
        results["pillow"] = True
        results["pillow_version"] = "설치됨"
    except ImportError:
        results["pillow_version"] = "미설치"

    # FFmpeg 확인
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            results["ffmpeg"] = True
            results["ffmpeg_version"] = result.stdout.split('\n')[0]
    except FileNotFoundError:
        results["ffmpeg_version"] = "미설치"

    # 권장 상태 결정
    if results["selenium"]:
        results["recommended"] = "selenium"

    return results


def print_environment_status():
    """환경 상태 출력"""
    env = check_environment()

    print("=" * 50)
    print("인포그래픽 렌더링 환경 확인")
    print("=" * 50)
    print(f"\nPython: {env['python_version'].split()[0]}")
    print(f"플랫폼: {env['platform']}")

    print("\n렌더러 상태:")
    print(f"  Selenium:   {'✅' if env['selenium'] else '❌'} ({env['selenium_version']})")
    print(f"  Pillow:     {'✅' if env['pillow'] else '❌'} ({env['pillow_version']})")

    print(f"\nFFmpeg: {'✅' if env['ffmpeg'] else '❌'}")
    if env['ffmpeg']:
        print(f"  {env['ffmpeg_version']}")

    print(f"\n권장 렌더러: {env['recommended'] or '없음'}")

    if not env['recommended']:
        print("\n⚠️ 렌더러가 설치되지 않았습니다!")
        print("설치 명령:")
        print("  pip install selenium webdriver-manager pillow")

    if not env['ffmpeg']:
        print("\n⚠️ FFmpeg이 설치되지 않았습니다!")
        print("동영상 생성을 위해 FFmpeg이 필요합니다.")
        print("  Windows: choco install ffmpeg")
        print("  또는: https://ffmpeg.org/download.html")

    print("=" * 50)


if __name__ == "__main__":
    print_environment_status()
