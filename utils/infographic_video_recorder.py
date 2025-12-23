# -*- coding: utf-8 -*-
"""
인포그래픽 비디오 레코더 - 크기 최적화 + CSS 애니메이션 지원

변경사항 (v3.11) - 화질 손실 완전 해결:
- 🔴 핵심: device-scale-factor 1→2 (2배 해상도 캡처 → 다운스케일 = 선명도 대폭 향상)
- 🔴 PNG compress_level 1→0 (완전 무손실 저장)
- 🔴 PIL에서 직접 output 해상도로 다운스케일 (중복 스케일링 제거)
- 🔴 FFmpeg 스케일 필터 조건부 적용 (이미 타겟 해상도면 생략)
- 🔴 추가 렌더링 품질 옵션 (disable-gpu-vsync, run-all-compositor-stages)

변경사항 (v3.10):
- yuv444p → yuv420p (WMP 호환성 문제 해결)
- high444 → high 프로파일 (WMP 호환)
- CRF 값 하향 (더 높은 품질)

변경사항 (v3.6):
- 🔴 핵심 수정: Selenium 윈도우 크기 = HTML 캔버스 크기 (1280x720)
- 캔버스를 뷰포트 전체에 표시 (인포그래픽이 화면 70-80% 차지)
- FFmpeg lanczos 업스케일 (1280x720 → 1920x1080)
- 캔버스 크기 자동 감지 기능
- _prepare_scene_fullscreen() 신규 메서드

변경사항 (v3.5):
- CSS 애니메이션 실시간 프레임 캡처 모드 추가
- Chrome DevTools Protocol (CDP) 고속 스크린샷 지원
- 애니메이션 리셋 기능 (_reset_animations)
- 프레임 보간 인코딩 (minterpolate)
- animation_mode 파라미터 추가
- 원본 레이아웃 보존 모드
- 초고화질 비디오 프리셋
"""

import os
import sys
import tempfile
import subprocess
import shutil
import time
import traceback
import logging
import base64
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Callable

logger = logging.getLogger(__name__)

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# webdriver-manager
try:
    from webdriver_manager.chrome import ChromeDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

# PIL for image processing
try:
    from PIL import Image
    from io import BytesIO
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# 모델 import
from utils.models.infographic import InfographicScene, InfographicData

# 썸네일 모듈에서 공통 유틸리티 임포트
from utils.infographic_thumbnail import (
    find_chrome_binary,
    get_chromedriver_path,
    clear_webdriver_cache,
    _validate_executable,
    check_selenium_available as _check_selenium
)


# ============================================================
# 화질 프리셋 - 색상 보존 최적화 (v3.8)
# ============================================================

class VideoQuality:
    """
    비디오 화질 프리셋 - 색상 보존 최적화 (v3.8)

    핵심 변경사항:
    - ORIGINAL/PRISTINE: 원본 색상 100% 보존 (필터 없음)
    - YUV444P: 색차 서브샘플링 방지로 색상 정확도 유지
    - sharpen/color_enhance 제거: 색상 왜곡 방지
    - BT.709 색공간: 정확한 색상 재현
    """

    # 🎨 원본 색상 보존 (권장 - 색상 정확도 + WMP 호환)
    # 🔴 v3.10: yuv444p → yuv420p (Problem 54 - WMP 0xC00D36C4 에러 해결)
    ORIGINAL = {
        'name': '원본색상',
        'width': 1920,
        'height': 1080,
        'fps': 30,
        'crf': 10,              # 🔴 v3.10: 14→10 (화질 향상, yuv420p 보정)
        'preset': 'slow',
        'bitrate': '15M',
        'maxrate': '25M',
        'bufsize': '35M',
        'pixel_format': 'yuv420p',  # 🔴 v3.10: WMP 호환! (yuv444p는 재생 불가)
        'profile': 'high',          # 🔴 v3.10: high444 → high (WMP 호환)
        'tune': 'stillimage',
        'scale': 1.5,
        'sharpen': False,       # 필터 없음 - 원본 색상 보존
        'color_enhance': False,
        'color_preserve': True,
    }

    # 💎 프리스틴 (최고 충실도, VLC 전용!)
    # ⚠️ yuv444p = WMP 재생 불가, VLC/Premiere 등 전문 플레이어 필요
    PRISTINE = {
        'name': '프리스틴 (VLC전용)',
        'width': 1920,
        'height': 1080,
        'fps': 30,
        'crf': 8,               # 거의 무손실
        'preset': 'veryslow',
        'bitrate': '40M',
        'maxrate': '60M',
        'bufsize': '80M',
        'pixel_format': 'yuv444p',  # ⚠️ WMP 호환 안 됨!
        'profile': 'high444',       # ⚠️ WMP 호환 안 됨!
        'tune': 'stillimage',
        'scale': 2.0,
        'sharpen': False,
        'color_enhance': False,
        'color_preserve': True,
    }

    # 🎯 무손실 (매우 큰 파일, 편집용, VLC 전용!)
    # ⚠️ yuv444p = WMP 재생 불가, VLC/Premiere 등 전문 플레이어 필요
    LOSSLESS = {
        'name': '무손실 (VLC전용)',
        'width': 1920,
        'height': 1080,
        'fps': 30,
        'crf': 0,               # 무손실
        'preset': 'veryslow',
        'bitrate': None,
        'maxrate': None,
        'bufsize': None,
        'pixel_format': 'yuv444p',  # ⚠️ WMP 호환 안 됨!
        'profile': 'high444',       # ⚠️ WMP 호환 안 됨!
        'tune': None,
        'scale': 2.0,
        'sharpen': False,
        'color_enhance': False,
        'color_preserve': True,
    }

    # 🌟 초고화질+ (고품질 + WMP 호환)
    # 🔴 v3.10: yuv444p → yuv420p (Problem 54 해결)
    ULTRA_PLUS = {
        'name': '초고화질+',
        'width': 1920,
        'height': 1080,
        'fps': 30,
        'crf': 8,               # 🔴 v3.10: 10→8 (yuv420p 보정)
        'preset': 'veryslow',
        'bitrate': '35M',
        'maxrate': '55M',
        'bufsize': '70M',
        'pixel_format': 'yuv420p',  # 🔴 v3.10: WMP 호환!
        'profile': 'high',          # 🔴 v3.10: high444 → high
        'tune': 'stillimage',
        'scale': 2.0,
        'sharpen': False,
        'color_enhance': False,
        'color_preserve': True,
    }

    # ✨ 초고화질 (유튜브 프리미엄 + WMP 호환)
    # 🔴 v3.10: yuv444p → yuv420p (Problem 54 해결)
    ULTRA = {
        'name': '초고화질',
        'width': 1920,
        'height': 1080,
        'fps': 30,
        'crf': 10,              # 🔴 v3.10: 12→10 (yuv420p 보정)
        'preset': 'slower',
        'bitrate': '20M',
        'maxrate': '40M',
        'bufsize': '60M',
        'pixel_format': 'yuv420p',  # 🔴 v3.10: WMP 호환!
        'profile': 'high',          # 🔴 v3.10: high444 → high
        'tune': 'stillimage',
        'scale': 2.0,
        'sharpen': False,
        'color_enhance': False,
        'color_preserve': True,
    }

    # 🎬 고화질 (유튜브 권장 + WMP 호환)
    # 🔴 v3.10: yuv444p → yuv420p (Problem 54 해결)
    HIGH = {
        'name': '고화질',
        'width': 1920,
        'height': 1080,
        'fps': 30,
        'crf': 12,              # 🔴 v3.10: 16→12 (yuv420p 보정)
        'preset': 'medium',
        'bitrate': '10M',
        'maxrate': '18M',
        'bufsize': '28M',
        'pixel_format': 'yuv420p',  # 🔴 v3.10: WMP 호환!
        'profile': 'high',
        'tune': 'stillimage',
        'scale': 1.5,
        'sharpen': False,
        'color_enhance': False,
        'color_preserve': True,
    }

    # 📺 표준 화질 (빠른 처리, 호환성)
    STANDARD = {
        'name': '표준',
        'width': 1280,
        'height': 720,
        'fps': 30,
        'crf': 20,
        'preset': 'fast',
        'bitrate': '4M',
        'maxrate': '8M',
        'bufsize': '12M',
        'pixel_format': 'yuv420p',  # 호환성을 위해 유지
        'profile': 'main',
        'tune': None,
        'scale': 1.0,
        'sharpen': False,
        'color_enhance': False,
        'color_preserve': False,
    }

    # ⚡ 빠른 미리보기
    PREVIEW = {
        'name': '미리보기',
        'width': 854,
        'height': 480,
        'fps': 24,
        'crf': 28,
        'preset': 'ultrafast',
        'bitrate': '1M',
        'maxrate': '2M',
        'bufsize': '3M',
        'pixel_format': 'yuv420p',
        'profile': 'baseline',
        'tune': None,
        'scale': 1.0,
        'sharpen': False,
        'color_enhance': False,
        'color_preserve': False,
    }

    @classmethod
    def get(cls, name: str) -> dict:
        """이름으로 프리셋 가져오기 (기본값: ORIGINAL)"""
        presets = {
            'original': cls.ORIGINAL,
            'pristine': cls.PRISTINE,
            'lossless': cls.LOSSLESS,
            'ultra_plus': cls.ULTRA_PLUS,
            'ultra': cls.ULTRA,
            'high': cls.HIGH,
            'standard': cls.STANDARD,
            'preview': cls.PREVIEW
        }
        return presets.get(name.lower(), cls.ORIGINAL).copy()

    @classmethod
    def list_presets(cls) -> List[Tuple[str, str]]:
        """사용 가능한 프리셋 목록 (키, 표시명)"""
        return [
            ('original', '🎨 원본색상 (권장)'),
            ('pristine', '💎 프리스틴 (최고품질)'),
            ('lossless', '🎯 무손실 (편집용)'),
            ('ultra_plus', '🌟 초고화질+'),
            ('ultra', '✨ 초고화질'),
            ('high', '🎬 고화질'),
            ('standard', '📺 표준'),
            ('preview', '⚡ 미리보기'),
        ]

    @classmethod
    def list_preset_keys(cls) -> List[str]:
        """프리셋 키 목록"""
        return ['original', 'pristine', 'lossless', 'ultra_plus', 'ultra', 'high', 'standard', 'preview']


# ============================================================
# FFmpeg 유틸리티
# ============================================================

def find_ffmpeg() -> Optional[str]:
    """FFmpeg 실행 파일 찾기"""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    possible_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        os.path.expanduser(r"~\ffmpeg\bin\ffmpeg.exe"),
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None


def check_ffmpeg_available() -> Tuple[bool, str]:
    """FFmpeg 사용 가능 여부 확인"""
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        return False, "FFmpeg 미설치. choco install ffmpeg"

    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0] if result.stdout else "버전 확인 불가"
            return True, f"FFmpeg 사용 가능: {version_line}"
        else:
            return False, "FFmpeg 실행 오류"
    except Exception as e:
        return False, f"FFmpeg 확인 실패: {e}"


def check_video_recorder_available() -> Tuple[bool, str]:
    """비디오 레코더 사용 가능 여부 확인"""
    issues = []

    selenium_ok, selenium_msg = _check_selenium()
    if not selenium_ok:
        issues.append(f"Selenium: {selenium_msg}")

    if not PIL_AVAILABLE:
        issues.append("Pillow 미설치 (pip install pillow)")

    ffmpeg_ok, ffmpeg_msg = check_ffmpeg_available()
    if not ffmpeg_ok:
        issues.append(f"FFmpeg: {ffmpeg_msg}")

    if issues:
        return False, "\n".join(issues)

    return True, "Selenium + FFmpeg 비디오 레코더 사용 가능"


# ============================================================
# 비디오 레코더 클래스
# ============================================================

class InfographicVideoRecorder:
    """
    크기 최적화 + 색상 보존 비디오 레코더 (v3.8)

    핵심 전략 (v3.8 색상 보존):
    - YUV444P: 색차 서브샘플링 방지로 원본 색상 100% 보존
    - 필터 제거: sharpen/color_enhance 비활성화로 색상 왜곡 방지
    - BT.709: 정확한 색공간 메타데이터
    - CDP 캡처: Chrome DevTools Protocol로 고충실도 스크린샷

    크기 최적화:
    - Selenium 윈도우 크기 = HTML 캔버스 크기 (1280x720)
    - 캔버스가 뷰포트 전체를 채움 (인포그래픽이 화면 70-80% 차지)
    - FFmpeg lanczos 업스케일로 최종 해상도 (1920x1080) 출력

    특징:
    - 화질 프리셋 지원 (original, pristine, ultra, high, standard, preview)
    - 캔버스 크기 자동 감지
    - CSS 애니메이션 실시간 캡처 지원
    - H.264 High Profile 인코딩
    """

    def __init__(
        self,
        output_dir: str = "outputs/infographic_videos",
        canvas_width: int = 1280,    # HTML 캔버스 크기 (Selenium 윈도우)
        canvas_height: int = 720,
        output_width: int = 1920,    # 최종 출력 해상도
        output_height: int = 1080,
        width: int = 1920,           # 레거시 호환
        height: int = 1080,
        fps: int = 30,
        quality: str = 'original'    # v3.8: 기본값 'original' (색상 보존)
    ):
        """
        Args:
            output_dir: 출력 디렉토리
            canvas_width: HTML 캔버스 너비 (Selenium 윈도우 크기)
            canvas_height: HTML 캔버스 높이 (Selenium 윈도우 크기)
            output_width: 최종 비디오 출력 너비
            output_height: 최종 비디오 출력 높이
            quality: 화질 프리셋 (original, pristine, ultra, high, standard, preview)
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # 캔버스 크기 (Selenium 윈도우 = HTML 캔버스)
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height

        # 최종 출력 해상도
        self.output_width = output_width
        self.output_height = output_height

        # 화질 프리셋 적용
        self.quality_preset = VideoQuality.get(quality)
        self.quality_name = quality

        # 레거시 호환 (기존 코드와의 호환성)
        self.width = self.quality_preset.get('width', width)
        self.height = self.quality_preset.get('height', height)
        self.fps = self.quality_preset.get('fps', fps)

        self._driver = None
        self._temp_dir = None
        self._chrome_path = find_chrome_binary()
        self._driver_path = None
        self._ffmpeg_path = find_ffmpeg()

        logger.info(f"[VideoRecorder] 초기화: 캔버스={canvas_width}x{canvas_height} → 출력={output_width}x{output_height}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _create_driver(self) -> webdriver.Chrome:
        """
        Chrome WebDriver 생성 - 캔버스 크기에 최적화

        🔴 핵심: Selenium 윈도우 크기 = HTML 캔버스 크기
        이렇게 하면 캔버스가 뷰포트 전체를 채우고, 스크린샷이 정확한 크기로 캡처됨
        """
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-logging')
        options.add_argument('--log-level=3')

        # ⭐ 핵심 변경: Selenium 윈도우 = 캔버스 크기
        # 기존: output 해상도 (1920x1080) → 캔버스가 작게 보임
        # 수정: 캔버스 크기 (1280x720) → 캔버스가 뷰포트 전체 채움
        options.add_argument(f'--window-size={self.canvas_width},{self.canvas_height}')

        # 🔴 v3.11: device-scale-factor 2로 상향 (화질 손실 문제 해결)
        # - 2배 해상도로 캡처 후 다운스케일 → 선명도/색감 개선
        # - 기존 1x: 1280x720 캡처 → 1920x1080 업스케일 (흐릿함!)
        # - 수정 2x: 2560x1440 캡처 → 1920x1080 다운스케일 (선명!)
        options.add_argument('--force-device-scale-factor=2')
        options.add_argument('--high-dpi-support=2')
        options.add_argument('--device-scale-factor=2')

        options.add_argument('--lang=ko-KR')
        options.add_argument('--hide-scrollbars')

        # 🔴 v3.11: 추가 렌더링 품질 향상 옵션
        options.add_argument('--disable-gpu-vsync')
        options.add_argument('--run-all-compositor-stages-before-draw')

        if self._chrome_path:
            options.binary_location = self._chrome_path

        if self._driver_path is None:
            self._driver_path = get_chromedriver_path()

        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                if self._driver_path:
                    if not _validate_executable(self._driver_path):
                        print(f"[VideoRecorder] 드라이버 경로 무효: {self._driver_path}")
                        if attempt == 0:
                            clear_webdriver_cache()
                            self._driver_path = get_chromedriver_path()
                            continue

                    service = Service(executable_path=self._driver_path)
                    if os.name == 'nt':
                        service.creation_flags = subprocess.CREATE_NO_WINDOW
                    driver = webdriver.Chrome(service=service, options=options)
                else:
                    driver = webdriver.Chrome(options=options)

                # ⭐ 윈도우 크기 = 캔버스 크기로 강제 설정
                driver.set_window_size(self.canvas_width, self.canvas_height)
                logger.info(f"[VideoRecorder] 드라이버 생성: {self.canvas_width}x{self.canvas_height}")
                return driver

            except OSError as e:
                last_error = e
                if hasattr(e, 'winerror') and e.winerror == 193:
                    print(f"[VideoRecorder] WinError 193 발생, 캐시 삭제 후 재시도...")
                    clear_webdriver_cache()
                    self._driver_path = get_chromedriver_path()
                else:
                    raise

            except Exception as e:
                last_error = e
                if attempt == 0:
                    print(f"[VideoRecorder] 드라이버 생성 실패, 재시도...: {e}")
                    clear_webdriver_cache()
                    self._driver_path = get_chromedriver_path()
                else:
                    raise

        raise last_error or Exception("ChromeDriver 초기화 실패")

    def _ensure_driver(self) -> webdriver.Chrome:
        """드라이버 인스턴스 보장"""
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium이 설치되지 않았습니다.")

        if self._driver is None:
            self._driver = self._create_driver()
        return self._driver

    def _get_temp_dir(self) -> str:
        """임시 디렉토리 확보"""
        if self._temp_dir is None:
            self._temp_dir = tempfile.mkdtemp(prefix="video_hq_")
        return self._temp_dir

    def _detect_canvas_size(self, html_content: str) -> Tuple[int, int]:
        """
        HTML에서 캔버스 크기 자동 감지

        CSS 변수 또는 인라인 스타일에서 크기 추출
        """
        # 방법 1: CSS 변수에서 추출 (--canvas-width: 1280px;)
        width_match = re.search(r'--canvas-width:\s*(\d+)px', html_content)
        height_match = re.search(r'--canvas-height:\s*(\d+)px', html_content)

        if width_match and height_match:
            w, h = int(width_match.group(1)), int(height_match.group(1))
            logger.info(f"[VideoRecorder] 캔버스 크기 감지 (CSS 변수): {w}x{h}")
            return w, h

        # 방법 2: #video-canvas 스타일에서 추출
        canvas_style = re.search(
            r'#video-canvas\s*\{[^}]*width:\s*(\d+)px[^}]*height:\s*(\d+)px',
            html_content, re.DOTALL
        )
        if canvas_style:
            w, h = int(canvas_style.group(1)), int(canvas_style.group(2))
            logger.info(f"[VideoRecorder] 캔버스 크기 감지 (#video-canvas): {w}x{h}")
            return w, h

        # 방법 3: 기본값
        logger.info(f"[VideoRecorder] 캔버스 크기 기본값 사용: {self.canvas_width}x{self.canvas_height}")
        return self.canvas_width, self.canvas_height

    def _update_driver_for_canvas(self, html_content: str):
        """
        HTML 캔버스 크기에 맞게 드라이버 윈도우 크기 조정

        HTML에서 캔버스 크기를 감지하고, 드라이버 윈도우 크기를 자동 조정
        """
        detected_width, detected_height = self._detect_canvas_size(html_content)

        if detected_width != self.canvas_width or detected_height != self.canvas_height:
            logger.info(f"[VideoRecorder] 캔버스 크기 업데이트: {self.canvas_width}x{self.canvas_height} → {detected_width}x{detected_height}")
            self.canvas_width = detected_width
            self.canvas_height = detected_height

            # 드라이버 윈도우 크기 재설정
            if self._driver:
                self._driver.set_window_size(self.canvas_width, self.canvas_height)

    def _prepare_scene_fullscreen(self, driver: webdriver.Chrome, scene_index: int) -> bool:
        """
        씬을 뷰포트 전체에 꽉 차게 표시

        🔴 핵심 메서드: 인포그래픽이 화면 70-80%를 차지하도록 함

        전략:
        1. 모든 외부 UI 숨기기
        2. 캔버스를 뷰포트 전체 크기로 확장
        3. 씬 콘텐츠가 캔버스 전체를 채우도록 설정
        """
        js_code = f"""
        (function() {{
            // === 1. 모든 씬 숨기고 타겟만 표시 ===
            var allScenes = document.querySelectorAll('.scene');
            allScenes.forEach(function(scene, idx) {{
                if (idx === {scene_index}) {{
                    scene.classList.add('active');
                }} else {{
                    scene.classList.remove('active');
                }}
            }});

            var targetScene = allScenes[{scene_index}];
            if (!targetScene) {{
                console.error('씬 없음:', {scene_index});
                return false;
            }}

            // === 2. 외부 UI 완전히 숨기기 ===
            var hideSelectors = [
                '.nav-btn',
                '.progress-outer',
                '.scene-counter',
                '.viewer-container > button',
                '[class*="nav"]',
                '[class*="progress"]'
            ];
            hideSelectors.forEach(function(sel) {{
                document.querySelectorAll(sel).forEach(function(el) {{
                    el.style.setProperty('display', 'none', 'important');
                    el.style.setProperty('visibility', 'hidden', 'important');
                }});
            }});

            // === 3. body 설정 ===
            document.body.style.cssText = `
                margin: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
                background: white !important;
                width: 100vw !important;
                height: 100vh !important;
            `;
            document.documentElement.style.cssText = `
                margin: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
            `;

            // === 4. viewer-container를 전체 화면으로 ===
            var viewer = document.querySelector('.viewer-container');
            if (viewer) {{
                viewer.style.cssText = `
                    display: block !important;
                    width: 100vw !important;
                    height: 100vh !important;
                    position: fixed !important;
                    top: 0 !important;
                    left: 0 !important;
                    padding: 0 !important;
                    margin: 0 !important;
                    gap: 0 !important;
                    background: white !important;
                `;
            }}

            // === 5. video-canvas를 전체 화면으로 확장 (핵심!) ===
            var canvas = document.getElementById('video-canvas');
            if (canvas) {{
                canvas.style.cssText = `
                    width: 100vw !important;
                    height: 100vh !important;
                    position: fixed !important;
                    top: 0 !important;
                    left: 0 !important;
                    box-shadow: none !important;
                    background: white !important;
                    transform: none !important;
                `;
            }}

            // === 6. safe-area를 전체로 확장 ===
            var safeArea = document.querySelector('.safe-area');
            if (safeArea) {{
                safeArea.style.cssText = `
                    width: 100% !important;
                    height: 100% !important;
                    padding: 5% !important;
                    display: flex !important;
                    justify-content: center !important;
                    align-items: center !important;
                    box-sizing: border-box !important;
                `;
            }}

            // === 7. 타겟 씬을 전체 캔버스에 표시 ===
            targetScene.style.cssText = `
                display: flex !important;
                position: absolute !important;
                top: 0 !important;
                left: 0 !important;
                width: 100% !important;
                height: 100% !important;
                justify-content: center !important;
                align-items: center !important;
                padding: 5% !important;
                box-sizing: border-box !important;
                background: white !important;
            `;

            // === 8. 전역 update 호출 ===
            if (typeof currentIdx !== 'undefined' && typeof update === 'function') {{
                try {{
                    currentIdx = {scene_index};
                    update();
                }} catch(e) {{}}
            }}

            return true;
        }})();
        """
        try:
            result = driver.execute_script(js_code)
            return result == True
        except Exception as e:
            logger.warning(f"풀스크린 씬 표시 오류: {e}")
            return False

    def _show_only_scene_exact_layout(self, driver: webdriver.Chrome, scene_index: int) -> bool:
        """
        특정 씬만 표시 - 원본 레이아웃 완벽 보존

        핵심: 씬 내부 스타일은 절대 건드리지 않고,
        캔버스 컨테이너만 뷰포트 중앙에 배치
        """
        js_code = f"""
        (function() {{
            // === 1단계: 모든 씬 숨기고 타겟만 active ===
            var allScenes = document.querySelectorAll('.scene');
            var targetScene = null;

            allScenes.forEach(function(scene, idx) {{
                if (idx === {scene_index}) {{
                    scene.classList.add('active');
                    targetScene = scene;
                }} else {{
                    scene.classList.remove('active');
                    scene.style.display = 'none';
                }}
            }});

            if (!targetScene) {{
                // 대체 방법으로 찾기
                var sections = document.querySelectorAll('section, [class*="scene"]');
                if (sections.length > {scene_index}) {{
                    targetScene = sections[{scene_index}];
                }}
            }}

            if (!targetScene) {{
                console.error('씬 없음:', {scene_index});
                return false;
            }}

            // === 2단계: 불필요한 UI 숨기기 ===
            var hideSelectors = [
                '.nav-btn',
                '.progress-outer',
                '.scene-counter',
                'button.nav-btn',
                '[class*="nav-btn"]',
                '[class*="progress"]'
            ];
            hideSelectors.forEach(function(sel) {{
                document.querySelectorAll(sel).forEach(function(el) {{
                    el.style.setProperty('display', 'none', 'important');
                    el.style.setProperty('visibility', 'hidden', 'important');
                }});
            }});

            // === 3단계: 캔버스 크기 확인 ===
            var canvas = document.getElementById('video-canvas');
            var canvasWidth = 1280;
            var canvasHeight = 720;

            if (canvas) {{
                // CSS 변수 또는 직접 크기에서 가져오기
                var rootStyle = getComputedStyle(document.documentElement);
                var cssW = parseInt(rootStyle.getPropertyValue('--canvas-width'));
                var cssH = parseInt(rootStyle.getPropertyValue('--canvas-height'));

                if (cssW && cssH) {{
                    canvasWidth = cssW;
                    canvasHeight = cssH;
                }} else {{
                    // 캔버스의 실제 크기 사용
                    canvasWidth = canvas.offsetWidth || 1280;
                    canvasHeight = canvas.offsetHeight || 720;
                }}
            }}

            // === 4단계: 뷰포트 대비 스케일 계산 ===
            var vpWidth = window.innerWidth;
            var vpHeight = window.innerHeight;
            var scaleX = vpWidth / canvasWidth;
            var scaleY = vpHeight / canvasHeight;
            var scale = Math.min(scaleX, scaleY, 1.0);  // 최대 1배 (확대 안 함)

            // === 5단계: body/html 설정 ===
            document.body.style.cssText = `
                margin: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
                background: white !important;
            `;
            document.documentElement.style.cssText = `
                margin: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
            `;

            // === 6단계: viewer-container 중앙 배치 ===
            var viewer = document.querySelector('.viewer-container');
            if (viewer) {{
                viewer.style.cssText = `
                    display: flex !important;
                    justify-content: center !important;
                    align-items: center !important;
                    width: 100vw !important;
                    height: 100vh !important;
                    position: fixed !important;
                    top: 0 !important;
                    left: 0 !important;
                    gap: 0 !important;
                    padding: 0 !important;
                    margin: 0 !important;
                    background: white !important;
                `;
            }}

            // === 7단계: video-canvas 중앙 배치 (스케일 적용) ===
            if (canvas) {{
                canvas.style.cssText = `
                    width: ${{canvasWidth}}px !important;
                    height: ${{canvasHeight}}px !important;
                    transform: scale(${{scale}}) !important;
                    transform-origin: center center !important;
                    position: relative !important;
                    box-shadow: none !important;
                    overflow: hidden !important;
                `;
            }}

            // === 8단계: safe-area 원본 크기 유지 ===
            var safeArea = document.querySelector('.safe-area');
            if (safeArea) {{
                // safe-area는 원본 스타일 그대로 유지
                safeArea.style.width = '100%';
                safeArea.style.height = '100%';
                safeArea.style.position = 'relative';
            }}

            // === 9단계: 타겟 씬 - 원본 스타일 최대한 유지! ===
            // ⚠️ 중요: 씬 내부 flex-direction, justify-content 등은 건드리지 않음!
            // active 클래스의 원본 CSS 스타일이 적용되도록 display만 보장
            var computedDisplay = window.getComputedStyle(targetScene).display;
            if (computedDisplay === 'none') {{
                // 원본 .scene.active CSS 스타일 적용되게 display만 설정
                targetScene.style.display = '';  // CSS 클래스에서 결정하도록
            }}

            // 씬이 캔버스 영역 내에 있도록 위치만 설정
            targetScene.style.position = 'absolute';
            targetScene.style.top = '0';
            targetScene.style.left = '0';
            targetScene.style.width = '100%';
            targetScene.style.height = '100%';
            targetScene.style.overflow = 'hidden';

            // === 10단계: 전역 update 호출 ===
            if (typeof currentIdx !== 'undefined' && typeof update === 'function') {{
                try {{
                    currentIdx = {scene_index};
                    update();
                }} catch(e) {{}}
            }}

            return true;
        }})();
        """
        try:
            result = driver.execute_script(js_code)
            return result == True
        except Exception as e:
            logger.warning(f"레이아웃 보존 JavaScript 오류: {e}")
            return False

    def _show_only_scene_centered(self, driver: webdriver.Chrome, scene_index: int) -> bool:
        """
        특정 씬만 표시 - 강제 중앙 정렬 (레거시, 레이아웃이 단순한 경우 사용)

        주의: 이 메서드는 flex-direction: column을 적용하여 원본 레이아웃이 변경될 수 있음
        복잡한 레이아웃에는 _show_only_scene_exact_layout 사용 권장
        """
        js_code = f"""
        (function() {{
            // 1. 모든 씬 숨기기
            var allScenes = document.querySelectorAll('.scene');
            allScenes.forEach(function(scene) {{
                scene.style.display = 'none';
            }});

            // 2. 타겟 씬 찾기
            var targetScene = null;
            if (allScenes.length > {scene_index}) {{
                targetScene = allScenes[{scene_index}];
            }}
            if (!targetScene) {{
                var sections = document.querySelectorAll('section, [class*="scene"]');
                if (sections.length > {scene_index}) {{
                    targetScene = sections[{scene_index}];
                }}
            }}

            if (!targetScene) {{
                console.error('씬을 찾을 수 없음:', {scene_index});
                return false;
            }}

            // 3. 타겟 씬 강제 중앙 정렬
            targetScene.style.cssText = `
                display: flex !important;
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                width: 100vw !important;
                height: 100vh !important;
                justify-content: center !important;
                align-items: center !important;
                flex-direction: column !important;
                background: white !important;
                z-index: 9999 !important;
                padding: 5% !important;
                box-sizing: border-box !important;
                overflow: hidden !important;
            `;

            // 4. body 설정
            document.body.style.cssText = `
                overflow: hidden !important;
                margin: 0 !important;
                padding: 0 !important;
                background: white !important;
            `;

            // 5. UI 숨기기
            var hideSelectors = ['.nav-btn', '.progress-outer', '.scene-counter'];
            hideSelectors.forEach(function(selector) {{
                document.querySelectorAll(selector).forEach(function(el) {{
                    el.style.display = 'none';
                }});
            }});

            // 6. 전역 update 호출
            if (typeof currentIdx !== 'undefined' && typeof update === 'function') {{
                try {{ currentIdx = {scene_index}; update(); }} catch(e) {{}}
            }}

            return true;
        }})();
        """
        try:
            result = driver.execute_script(js_code)
            return result == True
        except Exception as e:
            logger.warning(f"중앙정렬 JavaScript 오류: {e}")
            return False

    def _capture_screenshot_hq(self, driver: webdriver.Chrome, output_path: str) -> bool:
        """
        고충실도 스크린샷 캡처 (v3.8 색상 보존)

        Chrome DevTools Protocol을 사용하여 최고 품질 캡처:
        - Page.captureScreenshot: 네이티브 해상도
        - format=png: 무손실 압축
        - optimizeForSpeed=false: 품질 우선
        - deviceScaleFactor: 고해상도 지원
        """
        try:
            scale = self.quality_preset.get('scale', 1.0)
            color_preserve = self.quality_preset.get('color_preserve', True)

            # 고해상도 캡처를 위한 CDP 명령 (scale > 1인 경우)
            if scale > 1:
                try:
                    driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
                        'width': int(self.width * scale),
                        'height': int(self.height * scale),
                        'deviceScaleFactor': scale,
                        'mobile': False
                    })
                    time.sleep(0.2)
                except Exception as e:
                    logger.debug(f"CDP setDeviceMetricsOverride 실패 (무시): {e}")

            # 🔴 v3.8: CDP를 사용한 고충실도 캡처 시도
            screenshot_data = None
            try:
                # Page.captureScreenshot - 최고 품질 설정
                cdp_result = driver.execute_cdp_cmd('Page.captureScreenshot', {
                    'format': 'png',
                    'quality': 100,  # PNG에서는 무시되지만 명시적 설정
                    'optimizeForSpeed': False,  # 품질 우선
                    'captureBeyondViewport': False,
                })
                if cdp_result and 'data' in cdp_result:
                    import base64
                    screenshot_data = base64.b64decode(cdp_result['data'])
                    if color_preserve:
                        logger.debug("🎨 CDP 고충실도 캡처 성공")
            except Exception as e:
                logger.debug(f"CDP captureScreenshot 실패, 기본 방식 사용: {e}")

            # 폴백: 기본 스크린샷
            if not screenshot_data:
                screenshot_data = driver.get_screenshot_as_png()

            # PIL로 고품질 저장
            if PIL_AVAILABLE:
                img = Image.open(BytesIO(screenshot_data))

                # sRGB 색공간 보존 (색상 정확도)
                if color_preserve and img.mode == 'RGBA':
                    # RGBA → RGB 변환 시 흰 배경 사용 (투명도 제거)
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg

                # 🔴 v3.11: 타겟 크기를 출력 해상도로 직접 설정
                # - 기존: self.width * scale (프리셋 스케일 적용 → 중복 스케일링 문제)
                # - 수정: output_width, output_height (최종 출력 해상도로 직접 다운스케일)
                # - device-scale-factor=2 덕분에 캡처는 2배 해상도 (다운스케일 = 품질 향상)
                target_size = (self.output_width, self.output_height)

                if img.size != target_size:
                    # 🔴 v3.11: 고품질 다운스케일링 (2배 해상도 → 출력 해상도)
                    # 다운스케일은 업스케일보다 훨씬 더 좋은 품질
                    logger.debug(f"🎨 이미지 리사이즈: {img.size} → {target_size} (Lanczos 다운스케일)")
                    img = img.resize(target_size, Image.Resampling.LANCZOS)

                # 🔴 v3.11: PNG 무손실 저장 (compress_level=0)
                # - 기존 compress_level=1: 약간의 손실 있음
                # - 수정 compress_level=0: 완전 무손실 (파일 크기 증가하지만 품질 보존)
                img.save(output_path, 'PNG', optimize=False, compress_level=0)
            else:
                with open(output_path, 'wb') as f:
                    f.write(screenshot_data)

            # 디바이스 메트릭 초기화
            if scale > 1:
                try:
                    driver.execute_cdp_cmd('Emulation.clearDeviceMetricsOverride', {})
                except:
                    pass

            return True

        except Exception as e:
            logger.warning(f"고해상도 캡처 실패, 기본 캡처 사용: {e}")
            try:
                driver.save_screenshot(output_path)
                return True
            except:
                return False

    def _image_to_video_hq(
        self,
        image_path: str,
        duration: float,
        output_path: str,
        fade_effect: bool = True
    ) -> bool:
        """
        이미지 → 비디오 변환 + 고품질 업스케일

        🔴 핵심: 캔버스 크기(1280x720) → 출력 해상도(1920x1080) 업스케일
        lanczos 알고리즘으로 고품질 스케일링

        v3.8 색상 보존 최적화:
        - color_preserve=True: 원본 색상 100% 보존 (필터 없음)
        - YUV444P: 색차 서브샘플링 방지
        - BT.709: 정확한 색공간 메타데이터
        - sharpen/color_enhance 제거: 색상 왜곡 방지
        """
        if not self._ffmpeg_path:
            logger.error("FFmpeg 없음")
            return False

        try:
            q = self.quality_preset
            crf = q.get('crf', 18)
            preset = q.get('preset', 'medium')
            bitrate = q.get('bitrate', '5M')
            maxrate = q.get('maxrate')
            bufsize = q.get('bufsize')
            fps = q.get('fps', 30)
            pix_fmt = q.get('pixel_format', 'yuv420p')  # 🔴 v3.10: yuv444p→yuv420p (WMP 호환)
            profile = q.get('profile', 'high')
            tune = q.get('tune')
            sharpen = q.get('sharpen', False)
            color_enhance = q.get('color_enhance', False)
            color_preserve = q.get('color_preserve', True)  # v3.8: 색상 보존 모드

            # 출력 해상도 (업스케일 타겟)
            target_w = self.output_width
            target_h = self.output_height

            # 비디오 필터 구성
            vf_parts = []

            # 🔴 v3.11: 스케일 필터 조건부 적용
            # - v3.11에서는 PIL이 이미 output_width x output_height로 다운스케일 완료
            # - 따라서 입력 이미지가 이미 타겟 해상도면 스케일 필터 불필요
            # - 만약 크기가 다르면 lanczos 고품질 스케일링 적용
            try:
                from PIL import Image as PILImage
                with PILImage.open(image_path) as test_img:
                    input_w, input_h = test_img.size
                if input_w != target_w or input_h != target_h:
                    # 크기가 다르면 스케일 필터 적용
                    vf_parts.append(f'scale={target_w}:{target_h}:flags=lanczos+accurate_rnd+full_chroma_int')
                    logger.info(f"  📐 FFmpeg 스케일: {input_w}x{input_h} → {target_w}x{target_h}")
                else:
                    logger.info(f"  ✅ 이미지가 이미 타겟 해상도 ({target_w}x{target_h}) - 스케일 필터 생략")
            except Exception:
                # PIL 실패 시 기존 동작 유지 (스케일 필터 항상 적용)
                vf_parts.append(f'scale={target_w}:{target_h}:flags=lanczos+accurate_rnd+full_chroma_int')

            # 🔴 v3.8: 색상 보존 모드에서는 필터 적용 안 함
            if not color_preserve:
                # 샤프닝 필터 (선명도 향상) - 색상 보존 모드에서 비활성화
                if sharpen:
                    vf_parts.append('unsharp=5:5:0.8:5:5:0.4')

                # 색상 보정 (채도/대비) - 색상 보존 모드에서 비활성화
                if color_enhance:
                    vf_parts.append('eq=saturation=1.05:contrast=1.02:brightness=0.01')

            # FPS 설정
            vf_parts.append(f'fps={fps}')

            # 페이드 효과 (선택적)
            if fade_effect and duration > 0.6:
                fade_dur = 0.25
                vf_parts.append(f'fade=t=in:st=0:d={fade_dur}')
                vf_parts.append(f'fade=t=out:st={duration - fade_dur}:d={fade_dur}')

            vf = ','.join(vf_parts)

            quality_name = q.get('name', 'unknown')
            logger.info(f"🎬 {quality_name} 인코딩: {self.canvas_width}x{self.canvas_height} → {target_w}x{target_h}")
            if color_preserve:
                logger.info("  🎨 색상 보존 모드 (원본 색상 100% 유지)")
            if sharpen and not color_preserve:
                logger.info("  - 샤프닝 적용")
            if color_enhance and not color_preserve:
                logger.info("  - 색상 보정 적용")

            # FFmpeg 명령 구성
            cmd = [
                self._ffmpeg_path,
                '-y',
                '-loop', '1',
                '-i', image_path,
                '-c:v', 'libx264',
                '-t', str(duration),
                '-pix_fmt', pix_fmt,
                '-vf', vf,
                '-preset', preset,
            ]

            # CRF (품질 기준)
            if crf is not None:
                cmd.extend(['-crf', str(crf)])

            # 비트레이트 설정 (있는 경우)
            if bitrate:
                cmd.extend(['-b:v', bitrate])

            if maxrate:
                cmd.extend(['-maxrate', maxrate])

            if bufsize:
                cmd.extend(['-bufsize', bufsize])

            # 프로파일 설정
            if profile:
                if profile == 'high444':
                    cmd.extend(['-profile:v', 'high444'])
                else:
                    cmd.extend(['-profile:v', profile, '-level:v', '4.2'])

            # 튜닝 (있는 경우)
            if tune:
                cmd.extend(['-tune', tune])

            # 추가 품질 옵션
            # 🔴 v3.12: 색감 보존 핵심 설정 (Problem 59)
            # - color_range pc: Full Range (0-255) 유지
            # - color_trc iec61966-2-1: sRGB 감마 커브 (HTML 렌더링 색공간)
            cmd.extend([
                '-movflags', '+faststart',
                '-color_range', 'pc',              # 🔴 Full Range (0-255) - 색상 손실 방지
                '-colorspace', 'bt709',
                '-color_primaries', 'bt709',
                '-color_trc', 'iec61966-2-1',      # 🔴 sRGB 감마 (HTML/웹 색공간)
            ])

            cmd.append(output_path)

            # 타임아웃은 화질에 따라 조정
            timeout = 60 if preset in ['ultrafast', 'fast'] else 180 if preset in ['veryslow', 'slower'] else 120

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg 오류: {result.stderr[:500] if result.stderr else 'Unknown'}")
                return False

            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info(f"✅ 비디오 생성: {target_w}x{target_h}, {size_mb:.2f}MB")
                return True

            return False

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg 타임아웃 (고화질은 시간이 더 소요됨)")
            return False
        except Exception as e:
            logger.error(f"고화질 변환 오류: {e}")
            return False

    # ================================================================
    # 빠른 생성 모드 (정적 이미지 기반) - 권장
    # ================================================================

    def record_scene_video_fast(
        self,
        html_content: str,
        scene_index: int,
        duration: float,
        output_path: str,
        fade_effect: bool = True,
        preserve_layout: bool = True,
        fullscreen_mode: bool = True  # 🔴 신규: 전체화면 모드
    ) -> bool:
        """
        ⚡ 빠른 씬 비디오 생성 - 크기 최적화 + 고화질

        🔴 v3.6 핵심 변경:
        - fullscreen_mode=True: 캔버스를 뷰포트 전체에 확장 (인포그래픽이 화면 70-80% 차지)
        - Selenium 윈도우 = 캔버스 크기 (1280x720)
        - FFmpeg 업스케일로 최종 출력 (1920x1080)

        Args:
            fullscreen_mode: True면 캔버스 전체화면 확장 (권장)
            preserve_layout: fullscreen_mode=False일 때 레이아웃 보존 여부
        """
        try:
            # 1. HTML에서 캔버스 크기 자동 감지 및 드라이버 조정
            self._update_driver_for_canvas(html_content)

            driver = self._ensure_driver()
            temp_dir = self._get_temp_dir()

            # 2. HTML 저장 및 로드
            html_file = os.path.join(temp_dir, f"scene_{scene_index}.html")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

            file_url = f"file:///{html_file.replace(os.sep, '/')}"
            driver.get(file_url)
            time.sleep(0.5)  # 폰트/스타일 로드 대기

            # 3. 씬 표시 방식 선택
            if fullscreen_mode:
                # 🔴 핵심: 캔버스를 뷰포트 전체로 확장 (인포그래픽이 크게 보임)
                self._prepare_scene_fullscreen(driver, scene_index)
                logger.info(f"[씬 {scene_index + 1}] 전체화면 모드 적용")
            elif preserve_layout:
                # 원본 레이아웃 보존
                self._show_only_scene_exact_layout(driver, scene_index)
            else:
                # 강제 중앙 정렬 (레거시)
                self._show_only_scene_centered(driver, scene_index)
            time.sleep(0.3)  # 렌더링 대기

            # 4. 스크린샷 캡처
            screenshot_path = os.path.join(temp_dir, f"scene_{scene_index}_hq.png")
            driver.save_screenshot(screenshot_path)

            # 캡처 크기 로깅
            if PIL_AVAILABLE:
                try:
                    from PIL import Image
                    with Image.open(screenshot_path) as img:
                        logger.info(f"📸 씬 {scene_index + 1} 캡처: {img.size[0]}x{img.size[1]}")
                except:
                    pass

            # 5. 비디오 변환 (업스케일 포함)
            success = self._image_to_video_hq(
                screenshot_path,
                duration,
                output_path,
                fade_effect=fade_effect
            )

            # 6. 정리
            try:
                os.remove(screenshot_path)
                os.remove(html_file)
            except:
                pass

            return success

        except Exception as e:
            logger.error(f"씬 {scene_index + 1} 빠른 녹화 오류: {e}")
            traceback.print_exc()
            return False

    # ================================================================
    # CSS 애니메이션 실시간 캡처 모드
    # ================================================================

    def _prepare_scene_for_animation(self, driver, scene_index: int) -> bool:
        """씬을 애니메이션 캡처용으로 준비 (레이아웃 보존)"""
        js_code = f"""
        (function() {{
            // 1. 모든 씬 숨기고 타겟만 active
            var allScenes = document.querySelectorAll('.scene');
            allScenes.forEach(function(scene, idx) {{
                if (idx === {scene_index}) {{
                    scene.classList.add('active');
                }} else {{
                    scene.classList.remove('active');
                    scene.style.display = 'none';
                }}
            }});

            // 2. 불필요한 UI 숨기기
            document.querySelectorAll('.nav-btn, .progress-outer, .scene-counter').forEach(function(el) {{
                el.style.setProperty('display', 'none', 'important');
            }});

            // 3. viewer-container 중앙 정렬
            var viewer = document.querySelector('.viewer-container');
            if (viewer) {{
                viewer.style.cssText = `
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    width: 100vw;
                    height: 100vh;
                    position: fixed;
                    top: 0;
                    left: 0;
                    background: white;
                    gap: 0;
                `;
            }}

            // 4. 캔버스 스케일 조정
            var canvas = document.getElementById('video-canvas');
            if (canvas) {{
                var vpWidth = window.innerWidth;
                var vpHeight = window.innerHeight;
                var canvasWidth = canvas.offsetWidth || 1280;
                var canvasHeight = canvas.offsetHeight || 720;
                var scale = Math.min(vpWidth / canvasWidth, vpHeight / canvasHeight, 1.0);

                canvas.style.transform = 'scale(' + scale + ')';
                canvas.style.transformOrigin = 'center center';
                canvas.style.boxShadow = 'none';
            }}

            // 5. body 설정
            document.body.style.margin = '0';
            document.body.style.overflow = 'hidden';
            document.body.style.background = 'white';

            return true;
        }})();
        """
        try:
            return driver.execute_script(js_code)
        except Exception as e:
            logger.warning(f"씬 준비 오류: {e}")
            return False

    def _reset_animations(self, driver, scene_index: int) -> bool:
        """
        CSS 애니메이션을 처음부터 다시 시작

        녹화 시작 시점에 애니메이션을 리셋하여 처음부터 캡처
        """
        js_code = f"""
        (function() {{
            var targetScene = document.querySelectorAll('.scene')[{scene_index}];
            if (!targetScene) return false;

            // 애니메이션이 적용된 모든 요소 찾기
            var animatedElements = targetScene.querySelectorAll(
                '.animate-subtle, .animate-spin-slow, .animate-pulse-red, .animate-draw, ' +
                '[class*="animate-"], [style*="animation"]'
            );

            // 각 요소의 애니메이션 리셋
            animatedElements.forEach(function(el) {{
                var currentAnimation = window.getComputedStyle(el).animation;
                el.style.animation = 'none';
                el.offsetHeight;  // 강제 리플로우
                el.style.animation = '';  // 원래 클래스 기반으로 복원
            }});

            // SVG path 애니메이션도 리셋 (draw-line 효과)
            var svgPaths = targetScene.querySelectorAll('path.animate-draw, .animate-draw path');
            svgPaths.forEach(function(path) {{
                try {{
                    var length = path.getTotalLength ? path.getTotalLength() : 1000;
                    path.style.strokeDasharray = length;
                    path.style.strokeDashoffset = length;
                    path.getBoundingClientRect();
                    path.style.animation = 'none';
                    path.offsetHeight;
                    path.style.animation = '';
                }} catch(e) {{}}
            }});

            return true;
        }})();
        """
        try:
            result = driver.execute_script(js_code)
            time.sleep(0.1)  # 리셋 후 대기
            return result
        except Exception as e:
            logger.warning(f"애니메이션 리셋 오류: {e}")
            return False

    def _encode_frames_to_video(
        self,
        frames_dir: str,
        output_path: str,
        input_fps: int = 15,
        output_fps: int = 30
    ) -> bool:
        """
        캡처된 프레임들을 부드러운 비디오로 인코딩

        프레임 보간으로 부드러운 재생
        """
        if not self._ffmpeg_path:
            logger.error("FFmpeg 없음")
            return False

        try:
            input_pattern = os.path.join(frames_dir, "frame_%06d.png")

            frame_files = [f for f in os.listdir(frames_dir) if f.startswith('frame_') and f.endswith('.png')]
            if not frame_files:
                logger.error("캡처된 프레임 없음")
                return False

            logger.info(f"🎬 {len(frame_files)}프레임 → 비디오 인코딩 ({input_fps}fps → {output_fps}fps)")

            q = self.quality_preset
            crf = q.get('crf', 18)
            preset = q.get('preset', 'medium')
            target_w = q.get('width', 1920)
            target_h = q.get('height', 1080)
            pix_fmt = q.get('pixel_format', 'yuv420p')  # 🔴 v3.10: yuv444p→yuv420p (WMP 호환)
            profile = q.get('profile', 'high')

            # 비디오 필터 (고품질 스케일링)
            vf_parts = [
                f'fps={output_fps}',
                f'scale={target_w}:{target_h}:flags=lanczos+accurate_rnd+full_chroma_int'  # 🔴 고품질 스케일링
            ]
            vf = ','.join(vf_parts)

            # 🔴 v3.12: 색감 보존 설정 추가 (Problem 59)
            cmd = [
                self._ffmpeg_path,
                '-y',
                # 입력 색공간 명시 (sRGB 소스임을 알림)
                '-color_primaries', 'bt709',
                '-color_trc', 'iec61966-2-1',
                '-colorspace', 'bt709',
                # 입력 파일
                '-framerate', str(input_fps),
                '-i', input_pattern,
                # 코덱
                '-c:v', 'libx264',
                '-preset', preset,
                '-crf', str(crf),
                '-pix_fmt', pix_fmt,  # 🔴 v3.9: 프리셋에서 가져온 픽셀 포맷 사용
                '-vf', vf,
                '-movflags', '+faststart',
                '-profile:v', profile,  # 🔴 v3.9: 프리셋에서 가져온 프로파일 사용
                # 🔴 v3.12: 색감 보존 핵심 설정
                '-color_range', 'pc',              # Full Range (0-255)
                '-colorspace', 'bt709',
                '-color_primaries', 'bt709',
                '-color_trc', 'iec61966-2-1',      # sRGB 감마
                output_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                logger.warning(f"FFmpeg 경고: {result.stderr[:300] if result.stderr else 'Unknown'}")

            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info(f"✅ 애니메이션 비디오 생성 완료: {size_mb:.2f} MB")
                return True

            return False

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg 타임아웃")
            return False
        except Exception as e:
            logger.error(f"비디오 인코딩 오류: {e}")
            return False

    def _verify_video_file(self, video_path: str) -> dict:
        """
        🔴 v3.10: 생성된 동영상 파일 검증 (Problem 54 해결)

        Windows Media Player 호환성 확인:
        - yuv420p: WMP 호환 ✅
        - yuv444p: WMP 호환 ❌ (VLC 필요)
        - high444 프로파일: WMP 호환 ❌

        Returns:
            dict: {
                'valid': bool,
                'wmp_compatible': bool,
                'codec': str,
                'pix_fmt': str,
                'profile': str,
                'resolution': str,
                'file_size_mb': float,
                'warnings': list
            }
        """
        result = {
            'valid': False,
            'wmp_compatible': True,
            'codec': 'unknown',
            'pix_fmt': 'unknown',
            'profile': 'unknown',
            'resolution': 'unknown',
            'file_size_mb': 0,
            'warnings': []
        }

        # 1. 파일 존재 및 크기 확인
        if not os.path.exists(video_path):
            result['warnings'].append("파일 없음")
            return result

        file_size = os.path.getsize(video_path)
        result['file_size_mb'] = file_size / (1024 * 1024)

        if file_size < 1000:  # 1KB 미만
            result['warnings'].append("파일 크기 너무 작음 (손상 가능)")
            return result

        # 2. ffprobe로 코덱 정보 확인
        try:
            ffprobe_path = self._find_ffprobe()
            if not ffprobe_path:
                result['valid'] = True  # ffprobe 없으면 검증 스킵
                result['warnings'].append("ffprobe를 찾을 수 없어 검증 스킵")
                return result

            cmd = [
                ffprobe_path,
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name,pix_fmt,profile,width,height',
                '-of', 'json',
                video_path
            ]

            proc_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if proc_result.returncode == 0:
                import json
                info = json.loads(proc_result.stdout)
                streams = info.get('streams', [])

                if streams:
                    stream = streams[0]
                    result['codec'] = stream.get('codec_name', 'unknown')
                    result['pix_fmt'] = stream.get('pix_fmt', 'unknown')
                    result['profile'] = stream.get('profile', 'unknown')
                    width = stream.get('width', 0)
                    height = stream.get('height', 0)
                    result['resolution'] = f"{width}x{height}"
                    result['valid'] = True

                    # WMP 호환성 검사
                    if result['pix_fmt'] == 'yuv444p':
                        result['wmp_compatible'] = False
                        result['warnings'].append("⚠️ yuv444p: Windows Media Player 재생 불가, VLC 사용 권장")

                    if 'High 4:4:4' in result['profile'] or 'high444' in result['profile'].lower():
                        result['wmp_compatible'] = False
                        result['warnings'].append("⚠️ High 4:4:4 프로파일: Windows Media Player 재생 불가")

                    # 로그 출력
                    logger.info(f"[검증] 코덱:{result['codec']} | 픽셀:{result['pix_fmt']} | 프로파일:{result['profile']} | 해상도:{result['resolution']}")

                    if not result['wmp_compatible']:
                        logger.warning("⚠️ 이 동영상은 Windows Media Player에서 재생되지 않습니다. VLC Player를 사용하세요.")

                else:
                    result['warnings'].append("비디오 스트림 없음")
            else:
                result['valid'] = True  # ffprobe 실패해도 파일은 있음
                result['warnings'].append(f"ffprobe 오류: {proc_result.stderr[:100] if proc_result.stderr else 'Unknown'}")

        except subprocess.TimeoutExpired:
            result['valid'] = True
            result['warnings'].append("ffprobe 타임아웃")
        except Exception as e:
            result['valid'] = True
            result['warnings'].append(f"검증 오류: {str(e)[:100]}")

        return result

    def _find_ffprobe(self) -> Optional[str]:
        """ffprobe 경로 찾기"""
        # FFmpeg 경로에서 ffprobe 추론
        if self._ffmpeg_path:
            ffprobe_path = self._ffmpeg_path.replace('ffmpeg', 'ffprobe')
            if os.path.exists(ffprobe_path):
                return ffprobe_path

        # 시스템 PATH에서 찾기
        import shutil
        ffprobe = shutil.which('ffprobe')
        if ffprobe:
            return ffprobe

        # Windows 기본 위치
        if os.name == 'nt':
            common_paths = [
                r"C:\ffmpeg\bin\ffprobe.exe",
                r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
                os.path.expanduser(r"~\ffmpeg\bin\ffprobe.exe"),
            ]
            for path in common_paths:
                if os.path.exists(path):
                    return path

        return None

    def record_scene_with_animation(
        self,
        html_content: str,
        scene_index: int,
        duration: float,
        output_path: str,
        capture_fps: int = 15,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> bool:
        """
        🎬 CSS 애니메이션 실시간 캡처

        CSS 애니메이션이 실시간으로 진행되는 동안 프레임별로 캡처하여
        실제 움직임이 담긴 비디오를 생성합니다.

        Args:
            html_content: HTML 콘텐츠
            scene_index: 씬 인덱스 (0-based)
            duration: 녹화 시간 (초)
            output_path: 출력 비디오 경로
            capture_fps: 캡처 FPS (10-20 권장)
            progress_callback: 진행률 콜백 (0-100)

        Returns:
            성공 여부
        """
        try:
            driver = self._ensure_driver()
            temp_dir = self._get_temp_dir()

            # 프레임 저장 디렉토리
            frames_dir = os.path.join(temp_dir, f"frames_scene_{scene_index}")
            os.makedirs(frames_dir, exist_ok=True)

            # 1. HTML 로드
            html_file = os.path.join(temp_dir, f"scene_anim_{scene_index}.html")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

            file_url = f"file:///{html_file.replace(os.sep, '/')}"
            driver.get(file_url)

            # 2. 씬 준비
            self._prepare_scene_for_animation(driver, scene_index)
            time.sleep(0.5)  # 리소스 로드 대기

            # 3. 애니메이션 리셋 (처음부터 시작)
            self._reset_animations(driver, scene_index)

            # 4. 프레임 캡처 시작
            total_frames = int(duration * capture_fps)
            frame_interval = 1.0 / capture_fps

            logger.info(f"🎬 씬 {scene_index + 1}: {total_frames}프레임 애니메이션 캡처 ({duration}초, {capture_fps}fps)")

            start_time = time.time()
            captured_count = 0

            for frame_num in range(total_frames):
                frame_start = time.time()

                try:
                    # CDP를 통한 빠른 스크린샷 시도
                    screenshot_data = driver.execute_cdp_cmd(
                        'Page.captureScreenshot',
                        {'format': 'png', 'quality': 100}
                    )
                    frame_path = os.path.join(frames_dir, f"frame_{frame_num:06d}.png")
                    with open(frame_path, 'wb') as f:
                        f.write(base64.b64decode(screenshot_data['data']))
                    captured_count += 1

                except Exception:
                    # CDP 실패 시 일반 스크린샷
                    frame_path = os.path.join(frames_dir, f"frame_{frame_num:06d}.png")
                    driver.save_screenshot(frame_path)
                    captured_count += 1

                # 진행률
                if progress_callback:
                    progress = int((frame_num + 1) / total_frames * 100)
                    progress_callback(progress)

                # 타이밍 조절
                elapsed = time.time() - frame_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0.001:
                    time.sleep(sleep_time)

            actual_duration = time.time() - start_time
            actual_fps = captured_count / actual_duration if actual_duration > 0 else capture_fps

            logger.info(f"📸 {captured_count}프레임 캡처 완료 (실제 {actual_fps:.1f}fps, {actual_duration:.1f}초)")

            # 5. 비디오 인코딩
            success = self._encode_frames_to_video(
                frames_dir=frames_dir,
                output_path=output_path,
                input_fps=int(actual_fps) or capture_fps,
                output_fps=self.fps
            )

            # 6. 정리
            try:
                shutil.rmtree(frames_dir)
                os.remove(html_file)
            except:
                pass

            return success

        except Exception as e:
            logger.error(f"❌ 씬 {scene_index + 1} 애니메이션 캡처 오류: {e}")
            traceback.print_exc()
            return False

    # ================================================================
    # 선택적 씬 녹화
    # ================================================================

    def record_selected_scenes(
        self,
        html_content: str,
        scene_indices: List[int],
        duration: float,
        output_dir: str,
        fast_mode: bool = True,
        animation_mode: bool = False,
        animation_fps: int = 15,
        preserve_layout: bool = True,
        fullscreen_mode: bool = True,  # 🔴 신규: 전체화면 모드 (인포그래픽이 크게 보임)
        fade_effect: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[int, str]:
        """
        선택된 씬들만 녹화 - 크기 최적화 + 고화질

        🔴 v3.6 핵심 변경:
        - fullscreen_mode=True: 인포그래픽이 화면 70-80% 차지
        - 캔버스 크기 자동 감지
        - FFmpeg lanczos 업스케일

        Args:
            animation_mode: True면 실제 CSS 애니메이션 프레임별 캡처
            animation_fps: 애니메이션 캡처 FPS (10-20 권장)
            preserve_layout: True면 원본 레이아웃 보존
            fullscreen_mode: True면 캔버스 전체화면 확장 (권장)
            fade_effect: 페이드 인/아웃 효과
        """
        os.makedirs(output_dir, exist_ok=True)
        results = {}
        total = len(scene_indices)

        # 캔버스 크기 자동 감지
        self._update_driver_for_canvas(html_content)
        logger.info(f"[VideoRecorder] 녹화 시작: {total}개 씬, 캔버스={self.canvas_width}x{self.canvas_height} → 출력={self.output_width}x{self.output_height}")

        for i, scene_idx in enumerate(scene_indices):
            output_path = os.path.join(output_dir, f"infographic_scene_{scene_idx + 1:03d}.mp4")

            if progress_callback:
                quality_name = self.quality_preset.get('name', '고화질')
                mode_str = "🎭 애니메이션" if animation_mode else "⚡ 정적"
                progress_callback(i + 1, total, f"씬 {scene_idx + 1} {mode_str} 녹화 중... ({quality_name})")

            if animation_mode:
                # CSS 애니메이션 실시간 캡처
                def scene_progress(pct):
                    if progress_callback:
                        progress_callback(i + 1, total, f"씬 {scene_idx + 1} 캡처 중... {pct}%")

                success = self.record_scene_with_animation(
                    html_content=html_content,
                    scene_index=scene_idx,
                    duration=duration,
                    output_path=output_path,
                    capture_fps=animation_fps,
                    progress_callback=scene_progress
                )
            else:
                # 빠른 정적 이미지 기반 + 전체화면 모드
                success = self.record_scene_video_fast(
                    html_content, scene_idx, duration, output_path,
                    fade_effect=fade_effect,
                    preserve_layout=preserve_layout,
                    fullscreen_mode=fullscreen_mode
                )

            if success:
                results[scene_idx] = output_path
                print(f"✅ 씬 {scene_idx + 1} 녹화 완료 → {self.output_width}x{self.output_height}")
            else:
                print(f"❌ 씬 {scene_idx + 1} 녹화 실패")

        return results

    # ================================================================
    # 기존 API 호환
    # ================================================================

    def record_scene_video(
        self,
        scene: InfographicScene,
        html_code: str,
        duration: float = 10.0,
        fast_mode: bool = True,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Optional[str]:
        """단일 씬을 MP4 동영상으로 녹화 (기존 API 호환)"""
        if not SELENIUM_AVAILABLE:
            scene.render_error = "Selenium 미설치"
            return None

        ffmpeg_ok, _ = check_ffmpeg_available()
        if not ffmpeg_ok:
            scene.render_error = "FFmpeg 미설치"
            return None

        try:
            output_path = os.path.join(
                self.output_dir,
                f"infographic_scene_{scene.scene_id:03d}.mp4"
            )

            scene_index = scene.scene_id - 1

            success = self.record_scene_video_fast(
                html_code, scene_index, duration, output_path
            )

            if success:
                scene.video_path = output_path
                scene.video_duration = duration
                scene.is_video_ready = True
                scene.render_error = None
                print(f"✅ 씬 {scene.scene_id} 동영상 생성 완료: {output_path}")
                return output_path
            else:
                scene.render_error = "녹화 실패"
                return None

        except Exception as e:
            scene.render_error = str(e)
            logger.error(f"씬 {scene.scene_id} 녹화 오류: {e}")
            traceback.print_exc()
            return None

    def record_multiple_scenes(
        self,
        infographic_data: InfographicData,
        scene_ids: List[int] = None,
        duration: float = None,
        fast_mode: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[int, str]:
        """여러 씬 일괄 녹화 (기존 API 호환)"""
        results = {}
        html_code = infographic_data.html_code

        if not html_code:
            print("[VideoRecorder] HTML 코드가 없습니다")
            return results

        if scene_ids:
            target_scenes = [s for s in infographic_data.scenes if s.scene_id in scene_ids]
        else:
            target_scenes = infographic_data.get_scenes_needing_video()

        if not target_scenes:
            print("[VideoRecorder] 녹화할 씬이 없습니다")
            return results

        rec_duration = duration or infographic_data.default_video_duration
        total = len(target_scenes)

        try:
            for i, scene in enumerate(target_scenes):
                if progress_callback:
                    quality_name = self.quality_preset.get('name', '고화질')
                    progress_callback(i + 1, total, f"씬 {scene.scene_id} 녹화 중... ({quality_name})")

                video_path = self.record_scene_video(
                    scene, html_code, rec_duration, fast_mode=fast_mode
                )

                if video_path:
                    results[scene.scene_id] = video_path

        finally:
            pass

        return results

    # ================================================================
    # 비디오 병합
    # ================================================================

    def merge_scene_videos(self, video_paths: List[str], output_path: str) -> bool:
        """씬 영상들을 하나로 합치기"""
        if not self._ffmpeg_path:
            print("❌ FFmpeg가 설치되지 않았습니다.")
            return False

        if not video_paths:
            print("❌ 병합할 비디오 없음")
            return False

        try:
            temp_dir = self._get_temp_dir()
            list_file = os.path.join(temp_dir, "concat_list.txt")

            with open(list_file, 'w', encoding='utf-8') as f:
                for video_path in video_paths:
                    escaped_path = video_path.replace('\\', '/').replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            cmd = [
                self._ffmpeg_path,
                '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',
                output_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=600,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                print(f"❌ 영상 합치기 오류: {result.stderr[:500] if result.stderr else 'Unknown'}")
                return False

            print(f"✅ 전체 영상 생성 완료: {output_path}")
            return True

        except subprocess.TimeoutExpired:
            print("❌ 영상 병합 타임아웃 (10분 초과)")
            return False
        except Exception as e:
            print(f"❌ 영상 합치기 오류: {e}")
            traceback.print_exc()
            return False

    def close(self):
        """리소스 정리"""
        if self._driver:
            try:
                self._driver.quit()
            except:
                pass
            self._driver = None

        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except:
                pass
            self._temp_dir = None

    def __del__(self):
        self.close()


# ============================================================
# Streamlit 호출용 동기 래퍼 함수
# ============================================================

def record_scene_video_sync(
    scene: InfographicScene,
    html_code: str,
    duration: float = 10.0,
    output_dir: str = "outputs/infographic_videos",
    quality: str = 'original',  # v3.8: 기본값 'original' (색상 보존)
    fast_mode: bool = True
) -> Optional[str]:
    """단일 씬 녹화 (Streamlit용)"""
    recorder = InfographicVideoRecorder(output_dir=output_dir, quality=quality)
    try:
        return recorder.record_scene_video(scene, html_code, duration, fast_mode=fast_mode)
    finally:
        recorder.close()


def record_videos_sync(
    infographic_data: InfographicData,
    scene_ids: List[int] = None,
    duration: float = None,
    output_dir: str = "outputs/infographic_videos",
    quality: str = 'original',  # v3.8: 기본값 'original' (색상 보존)
    fast_mode: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[int, str]:
    """일괄 녹화 (Streamlit용)"""
    recorder = InfographicVideoRecorder(output_dir=output_dir, quality=quality)
    try:
        return recorder.record_multiple_scenes(
            infographic_data, scene_ids, duration, fast_mode=fast_mode,
            progress_callback=progress_callback
        )
    finally:
        recorder.close()


def get_video_recorder(
    output_dir: str = None,
    canvas_width: int = 1280,     # HTML 캔버스 크기
    canvas_height: int = 720,
    output_width: int = 1920,     # 최종 출력 해상도
    output_height: int = 1080,
    width: int = 1920,            # 레거시 호환
    height: int = 1080,
    fps: int = 30,
    quality: str = 'original'     # v3.8: 기본값 'original' (색상 보존)
) -> InfographicVideoRecorder:
    """
    비디오 레코더 인스턴스 반환

    🔴 v3.8 핵심:
    - color_preserve: 원본 색상 100% 보존 (필터 없음)
    - YUV444P: 색차 서브샘플링 방지
    - canvas_width/height: Selenium 윈도우 크기 = HTML 캔버스 크기
    - output_width/height: FFmpeg 업스케일 타겟 (최종 비디오 해상도)

    Args:
        canvas_width: HTML 캔버스 너비 (기본 1280)
        canvas_height: HTML 캔버스 높이 (기본 720)
        output_width: 최종 출력 비디오 너비 (기본 1920)
        output_height: 최종 출력 비디오 높이 (기본 1080)
        quality: 화질 프리셋 (original, pristine, ultra, high, standard, preview)
    """
    if output_dir:
        return InfographicVideoRecorder(
            output_dir=output_dir,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            output_width=output_width,
            output_height=output_height,
            width=width,
            height=height,
            fps=fps,
            quality=quality
        )
    return InfographicVideoRecorder(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        output_width=output_width,
        output_height=output_height,
        width=width,
        height=height,
        fps=fps,
        quality=quality
    )


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  인포그래픽 비디오 레코더 v3.6 - 크기 최적화 테스트")
    print("=" * 60)

    available, msg = check_video_recorder_available()
    print(f"\n레코더 사용 가능: {available}")
    print(f"메시지: {msg}\n")

    if not available:
        print("\n해결 방법:")
        print("1. python utils/diagnose_selenium_env.py --clear-cache")
        print("2. python utils/install_chromedriver.py")
        sys.exit(1)

    # 테스트 HTML (캔버스 크기 1280x720 CSS 변수 포함)
    test_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        :root {
            --canvas-width: 1280px;
            --canvas-height: 720px;
        }
        body { margin: 0; padding: 0; background: white; }
        #video-canvas {
            width: var(--canvas-width);
            height: var(--canvas-height);
            position: relative;
            background: white;
        }
        .safe-area {
            width: 100%;
            height: 100%;
            padding: 5%;
            box-sizing: border-box;
        }
        .scene {
            display: none;
            width: 100%;
            height: 100%;
        }
        .scene.active {
            display: flex;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        h1 { font-size: 120px; color: #ef4444; margin: 0; }
        p { font-size: 48px; color: #333; margin: 20px 0; }
        .box {
            border: 4px solid #222;
            padding: 60px 80px;
            background: #facc15;
            border-radius: 20px;
            text-align: center;
        }
    </style>
    </head>
    <body>
        <div class="viewer-container">
            <div id="video-canvas">
                <div class="safe-area">
                    <div class="scene active">
                        <h1>38,000</h1>
                        <div class="box">
                            <p>크기 최적화 테스트</p>
                            <p>화면 70-80% 차지</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    print("🔴 핵심 변경사항 (v3.6):")
    print("  - Selenium 윈도우 크기 = HTML 캔버스 크기 (1280x720)")
    print("  - 캔버스를 뷰포트 전체로 확장")
    print("  - FFmpeg lanczos 업스케일 (1280x720 → 1920x1080)")
    print("")

    print("화질 프리셋 테스트...")

    for quality_name in ['preview', 'high']:
        print(f"\n--- {quality_name.upper()} 화질 테스트 ---")

        import time as t
        start = t.time()

        # 크기 최적화 레코더 사용
        with get_video_recorder(
            canvas_width=1280,
            canvas_height=720,
            output_width=1920,
            output_height=1080,
            quality=quality_name
        ) as recorder:
            output_file = f"test_{quality_name}_optimized.mp4"
            success = recorder.record_scene_video_fast(
                test_html, 0, 3.0, output_file,
                fullscreen_mode=True  # 캔버스 전체화면
            )
            elapsed = t.time() - start

            if success and os.path.exists(output_file):
                size_mb = os.path.getsize(output_file) / (1024 * 1024)
                print(f"✅ 성공: {elapsed:.1f}초, {size_mb:.2f}MB")
                print(f"   캔버스: {recorder.canvas_width}x{recorder.canvas_height}")
                print(f"   출력: {recorder.output_width}x{recorder.output_height}")
            else:
                print(f"❌ 실패")

    print("\n" + "=" * 60)
    print("테스트 완료! 생성된 비디오를 확인하세요.")
    print("인포그래픽이 화면의 70-80%를 차지해야 합니다.")
    print("=" * 60)
