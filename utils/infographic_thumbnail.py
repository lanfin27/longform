# -*- coding: utf-8 -*-
"""
인포그래픽 HTML 썸네일 생성 모듈 (Selenium 기반)

Python 3.13 + Windows + Streamlit 환경에서 안정적으로 동작
WinError 193 완전 해결 버전

변경사항 (v3.3):
- 원본 레이아웃 보존 모드 추가 (_show_specific_scene_exact_layout)
- 씬 내부 스타일 유지 (간격 벌어짐 문제 해결)
- preserve_layout 파라미터 추가 (기본값: True)
- PE 헤더 검증으로 손상된 ChromeDriver 감지
- 자동 캐시 삭제 및 재시도 로직
"""

import os
import tempfile
import time
import traceback
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
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


# ============================================================
# ChromeDriver 경로 해결 유틸리티
# ============================================================

def find_chrome_binary() -> Optional[str]:
    """Chrome 브라우저 실행 파일 찾기"""
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    chrome_in_path = shutil.which("chrome") or shutil.which("google-chrome")
    if chrome_in_path:
        return chrome_in_path

    return None


def _validate_executable(path: str) -> bool:
    """실행 파일이 유효한 Windows PE 파일인지 확인"""
    try:
        if not os.path.exists(path):
            return False

        if os.path.isdir(path):
            return False

        # 파일 크기 확인 (최소 1KB)
        if os.path.getsize(path) < 1024:
            return False

        # PE 헤더 확인 (MZ)
        with open(path, 'rb') as f:
            header = f.read(2)
            return header == b'MZ'

    except Exception:
        return False


def clear_webdriver_cache():
    """webdriver-manager 캐시 삭제"""
    cache_paths = [
        os.path.expanduser(r"~\.wdm"),
        os.path.expanduser(r"~\.cache\selenium"),
    ]

    for cache_path in cache_paths:
        if os.path.exists(cache_path):
            try:
                shutil.rmtree(cache_path)
                print(f"[Thumbnail] 캐시 삭제됨: {cache_path}")
            except Exception as e:
                print(f"[Thumbnail] 캐시 삭제 실패 {cache_path}: {e}")


def get_chromedriver_path() -> Optional[str]:
    """
    ChromeDriver 경로를 안전하게 가져오기
    여러 방법을 시도하여 가장 신뢰할 수 있는 경로 반환
    """

    # 방법 1: 환경 변수에서 직접 지정된 경로
    env_path = os.environ.get('CHROMEDRIVER_PATH')
    if env_path and os.path.exists(env_path) and _validate_executable(env_path):
        print(f"[Thumbnail] 환경 변수에서 ChromeDriver 발견: {env_path}")
        return env_path

    # 방법 2: 프로젝트 로컬 drivers 폴더
    project_root = Path(__file__).parent.parent
    local_driver = project_root / "drivers" / "chromedriver.exe"
    if local_driver.exists() and _validate_executable(str(local_driver)):
        print(f"[Thumbnail] 로컬 드라이버 발견: {local_driver}")
        return str(local_driver)

    # 방법 3: webdriver-manager
    if WEBDRIVER_MANAGER_AVAILABLE:
        try:
            driver_path = ChromeDriverManager().install()

            if driver_path and os.path.exists(driver_path):
                # 실제 chromedriver.exe 경로인지 확인
                if driver_path.endswith('.exe') and _validate_executable(driver_path):
                    print(f"[Thumbnail] webdriver-manager 드라이버: {driver_path}")
                    return driver_path

                # webdriver-manager가 폴더를 반환한 경우
                if not driver_path.endswith('.exe'):
                    # 폴더 내에서 chromedriver.exe 찾기
                    possible_exe = os.path.join(driver_path, "chromedriver.exe")
                    if os.path.exists(possible_exe) and _validate_executable(possible_exe):
                        return possible_exe

                    # 상위/하위 폴더 탐색
                    search_dir = os.path.dirname(driver_path)
                    for root, dirs, files in os.walk(search_dir):
                        for file in files:
                            if file == "chromedriver.exe":
                                full_path = os.path.join(root, file)
                                if _validate_executable(full_path):
                                    print(f"[Thumbnail] 폴더 탐색으로 드라이버 발견: {full_path}")
                                    return full_path

        except Exception as e:
            print(f"[Thumbnail] webdriver-manager 오류: {e}")

    # 방법 4: PATH에서 찾기
    chromedriver_in_path = shutil.which("chromedriver")
    if chromedriver_in_path and _validate_executable(chromedriver_in_path):
        print(f"[Thumbnail] PATH에서 드라이버 발견: {chromedriver_in_path}")
        return chromedriver_in_path

    return None


# ============================================================
# Selenium 사용 가능 여부 확인
# ============================================================

def check_selenium_available() -> Tuple[bool, str]:
    """Selenium + ChromeDriver 사용 가능 여부 확인"""
    if not SELENIUM_AVAILABLE:
        return False, "Selenium 미설치. pip install selenium"

    # Chrome 브라우저 확인
    chrome_path = find_chrome_binary()
    if not chrome_path:
        return False, "Chrome 브라우저 미설치. https://www.google.com/chrome/"

    # ChromeDriver 경로 확인
    driver_path = get_chromedriver_path()
    if not driver_path:
        return False, "ChromeDriver를 찾을 수 없습니다. python utils/install_chromedriver.py 실행 필요"

    # 실제 테스트
    try:
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.binary_location = chrome_path

        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        driver.quit()
        return True, "Selenium 사용 가능"

    except OSError as e:
        if hasattr(e, 'winerror') and e.winerror == 193:
            return False, f"ChromeDriver 손상 (WinError 193). python utils/install_chromedriver.py 실행 필요"
        return False, f"Selenium 초기화 실패: {e}"
    except Exception as e:
        return False, f"Selenium 초기화 실패: {e}"


def check_playwright_available() -> bool:
    """하위 호환성 - 항상 False 반환"""
    return False


def get_available_renderer() -> Tuple[Optional[str], str]:
    """사용 가능한 렌더러 확인"""
    selenium_ok, selenium_msg = check_selenium_available()
    if selenium_ok:
        return "selenium", selenium_msg
    return None, selenium_msg


# ============================================================
# 썸네일 생성기 클래스
# ============================================================

class SeleniumThumbnailGenerator:
    """Selenium 기반 썸네일 생성기 - WinError 193 해결 버전"""

    def __init__(
        self,
        output_dir: str = "outputs/infographic_thumbnails",
        width: int = 1280,
        height: int = 720,
        thumb_size: tuple = (320, 180)
    ):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.width = width
        self.height = height
        self.thumb_size = thumb_size

        self._driver = None
        self._initialized = False
        self._chrome_path = find_chrome_binary()
        self._driver_path = None

    def _create_driver(self) -> webdriver.Chrome:
        """Chrome WebDriver 생성 - WinError 193 방지 로직 포함"""
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-logging')
        options.add_argument('--log-level=3')
        options.add_argument(f'--window-size={self.width},{self.height}')

        # 🔴 v3.11: device-scale-factor 2로 상향 (화질 손실 문제 해결)
        options.add_argument('--force-device-scale-factor=2')
        options.add_argument('--high-dpi-support=2')

        options.add_argument('--lang=ko-KR')
        options.add_argument('--hide-scrollbars')

        # 🔴 v3.11: 추가 렌더링 품질 향상 옵션
        options.add_argument('--disable-gpu-vsync')
        options.add_argument('--run-all-compositor-stages-before-draw')

        if self._chrome_path:
            options.binary_location = self._chrome_path

        # ChromeDriver 경로 가져오기
        if self._driver_path is None:
            self._driver_path = get_chromedriver_path()

        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                if self._driver_path:
                    # 경로가 유효한지 확인
                    if not _validate_executable(self._driver_path):
                        print(f"[Thumbnail] 드라이버 경로 무효: {self._driver_path}")
                        if attempt == 0:
                            clear_webdriver_cache()
                            self._driver_path = get_chromedriver_path()
                            continue

                    service = Service(executable_path=self._driver_path)
                    driver = webdriver.Chrome(service=service, options=options)
                else:
                    # Selenium 4.6+ 자동 관리
                    driver = webdriver.Chrome(options=options)

                driver.set_window_size(self.width, self.height)
                return driver

            except OSError as e:
                last_error = e
                if hasattr(e, 'winerror') and e.winerror == 193:
                    print(f"[Thumbnail] WinError 193 발생, 캐시 삭제 후 재시도... ({attempt + 1}/{max_retries})")
                    clear_webdriver_cache()
                    self._driver_path = get_chromedriver_path()
                else:
                    raise

            except Exception as e:
                last_error = e
                if attempt == 0:
                    print(f"[Thumbnail] 드라이버 생성 실패, 재시도... ({attempt + 1}/{max_retries}): {e}")
                    clear_webdriver_cache()
                    self._driver_path = get_chromedriver_path()
                else:
                    raise

        # 모든 재시도 실패
        raise last_error or Exception("ChromeDriver 초기화 실패")

    def _ensure_driver(self) -> webdriver.Chrome:
        """드라이버 인스턴스 보장"""
        if not SELENIUM_AVAILABLE:
            raise ImportError(
                "Selenium이 설치되지 않았습니다.\n"
                "설치: pip install selenium webdriver-manager"
            )

        if self._driver is None:
            self._driver = self._create_driver()
            self._initialized = True
        return self._driver

    def _load_html_content(self, html_content: str) -> str:
        """HTML 콘텐츠를 임시 파일로 저장하고 경로 반환"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.html',
            delete=False, encoding='utf-8'
        ) as f:
            f.write(html_content)
            return f.name

    def _show_specific_scene(self, driver: webdriver.Chrome, scene_index: int, preserve_layout: bool = True) -> bool:
        """
        특정 씬만 표시

        Args:
            preserve_layout: True면 원본 레이아웃 보존 (권장), False면 강제 중앙 정렬
        """
        if preserve_layout:
            return self._show_specific_scene_exact_layout(driver, scene_index)
        else:
            return self._show_specific_scene_centered(driver, scene_index)

    def _show_specific_scene_exact_layout(self, driver: webdriver.Chrome, scene_index: int) -> bool:
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
                '.nav-btn', '.progress-outer', '.scene-counter',
                'button.nav-btn', '[class*="nav-btn"]', '[class*="progress"]'
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
                var rootStyle = getComputedStyle(document.documentElement);
                var cssW = parseInt(rootStyle.getPropertyValue('--canvas-width'));
                var cssH = parseInt(rootStyle.getPropertyValue('--canvas-height'));

                if (cssW && cssH) {{
                    canvasWidth = cssW;
                    canvasHeight = cssH;
                }} else {{
                    canvasWidth = canvas.offsetWidth || 1280;
                    canvasHeight = canvas.offsetHeight || 720;
                }}
            }}

            // === 4단계: 뷰포트 대비 스케일 계산 ===
            var vpWidth = window.innerWidth;
            var vpHeight = window.innerHeight;
            var scaleX = vpWidth / canvasWidth;
            var scaleY = vpHeight / canvasHeight;
            var scale = Math.min(scaleX, scaleY, 1.0);

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

            // === 7단계: video-canvas 중앙 배치 ===
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
                safeArea.style.width = '100%';
                safeArea.style.height = '100%';
                safeArea.style.position = 'relative';
            }}

            // === 9단계: 타겟 씬 - 원본 스타일 최대한 유지! ===
            var computedDisplay = window.getComputedStyle(targetScene).display;
            if (computedDisplay === 'none') {{
                targetScene.style.display = '';
            }}

            targetScene.style.position = 'absolute';
            targetScene.style.top = '0';
            targetScene.style.left = '0';
            targetScene.style.width = '100%';
            targetScene.style.height = '100%';
            targetScene.style.overflow = 'hidden';

            // === 10단계: 전역 update 호출 ===
            if (typeof currentIdx !== 'undefined' && typeof update === 'function') {{
                try {{ currentIdx = {scene_index}; update(); }} catch(e) {{}}
            }}

            return true;
        }})();
        """
        try:
            result = driver.execute_script(js_code)
            return result == True
        except Exception:
            return False

    def _show_specific_scene_centered(self, driver: webdriver.Chrome, scene_index: int) -> bool:
        """
        특정 씬만 표시 - 강제 중앙 정렬 (레거시)

        주의: flex-direction: column을 적용하여 원본 레이아웃이 변경될 수 있음
        """
        js_code = f"""
        (function() {{
            var allScenes = document.querySelectorAll('.scene');
            allScenes.forEach(function(scene) {{ scene.style.display = 'none'; }});

            var targetScene = null;
            if (allScenes.length > {scene_index}) {{ targetScene = allScenes[{scene_index}]; }}
            if (!targetScene) {{
                var sections = document.querySelectorAll('section, [class*="scene"]');
                if (sections.length > {scene_index}) {{ targetScene = sections[{scene_index}]; }}
            }}

            if (!targetScene) {{ return false; }}

            targetScene.style.cssText = `
                display: flex !important;
                position: fixed !important;
                top: 0 !important; left: 0 !important;
                width: 100vw !important; height: 100vh !important;
                justify-content: center !important;
                align-items: center !important;
                flex-direction: column !important;
                background: white !important;
                z-index: 9999 !important;
                padding: 5% !important;
                box-sizing: border-box !important;
                overflow: hidden !important;
            `;

            document.body.style.cssText = 'overflow:hidden;margin:0;padding:0;background:white;';

            ['.nav-btn','.progress-outer','.scene-counter'].forEach(function(sel) {{
                document.querySelectorAll(sel).forEach(function(el) {{
                    el.style.display = 'none';
                }});
            }});

            if (typeof currentIdx !== 'undefined' && typeof update === 'function') {{
                try {{ currentIdx = {scene_index}; update(); }} catch(e) {{}}
            }}

            return true;
        }})();
        """
        try:
            result = driver.execute_script(js_code)
            return result == True
        except Exception:
            return False

    def _create_thumbnail(self, source_path: str, thumb_path: str):
        """원본 이미지에서 썸네일 생성"""
        if not PIL_AVAILABLE:
            return

        try:
            with Image.open(source_path) as img:
                img.thumbnail(self.thumb_size, Image.Resampling.LANCZOS)
                img.save(thumb_path, "PNG")
        except Exception as e:
            print(f"[Thumbnail] 썸네일 생성 실패: {e}")

    def capture_first_frame(
        self,
        scene: InfographicScene,
        html_code: str
    ) -> bool:
        """단일 씬의 첫 프레임 캡처"""
        temp_html_path = None

        try:
            driver = self._ensure_driver()

            # HTML 파일로 저장
            temp_html_path = self._load_html_content(html_code)

            # 파일 로드
            driver.get(f'file:///{temp_html_path}')

            # 페이지 로드 대기
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )

            # 추가 렌더링 대기
            time.sleep(0.5)

            # 특정 씬 표시 (0-indexed)
            self._show_specific_scene(driver, scene.scene_id - 1)
            time.sleep(0.3)

            # 첫 프레임 저장
            first_frame_path = os.path.join(
                self.output_dir,
                f"scene_{scene.scene_id:03d}_first_frame.png"
            )

            # 스크린샷 캡처
            screenshot_data = driver.get_screenshot_as_png()

            if PIL_AVAILABLE:
                img = Image.open(BytesIO(screenshot_data))
                if img.size != (self.width, self.height):
                    img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
                # 🔴 v3.11: 무손실 PNG 저장 (compress_level=0)
                img.save(first_frame_path, 'PNG', optimize=False, compress_level=0)
            else:
                with open(first_frame_path, 'wb') as f:
                    f.write(screenshot_data)

            scene.first_frame_path = first_frame_path

            # 썸네일 생성
            thumb_path = os.path.join(
                self.output_dir,
                f"scene_{scene.scene_id:03d}_thumb.png"
            )
            self._create_thumbnail(first_frame_path, thumb_path)
            scene.thumbnail_path = thumb_path

            scene.is_thumbnail_ready = True
            scene.render_error = None

            print(f"✅ 씬 {scene.scene_id} 썸네일 생성 완료")
            return True

        except Exception as e:
            scene.render_error = str(e)
            print(f"❌ 씬 {scene.scene_id} 썸네일 생성 오류: {e}")
            traceback.print_exc()
            return False

        finally:
            if temp_html_path and os.path.exists(temp_html_path):
                try:
                    os.unlink(temp_html_path)
                except:
                    pass

    def generate_all_thumbnails(
        self,
        infographic_data: InfographicData,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[int, bool]:
        """모든 씬의 썸네일 일괄 생성"""
        results = {}
        total = len(infographic_data.scenes)
        html_code = infographic_data.html_code

        if not html_code:
            print("[Thumbnail] HTML 코드가 없습니다")
            return results

        try:
            for i, scene in enumerate(infographic_data.scenes):
                if progress_callback:
                    progress_callback(i + 1, total, f"씬 {scene.scene_id} 썸네일 생성 중...")

                success = self.capture_first_frame(scene, html_code)
                results[scene.scene_id] = success

        finally:
            self.close()

        success_count = sum(1 for v in results.values() if v)
        print(f"✅ 썸네일 생성 완료: {success_count}/{total}")

        return results

    def generate_selected_thumbnails(
        self,
        html_content: str,
        scene_indices: List[int],
        output_dir: str = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[str]:
        """
        선택된 씬들의 썸네일만 생성

        Args:
            html_content: HTML 콘텐츠
            scene_indices: 생성할 씬 인덱스 목록 (0-based)
            output_dir: 출력 디렉토리 (None이면 self.output_dir 사용)
            progress_callback: 진행 콜백 (current, total)

        Returns:
            생성된 썸네일 파일 경로 목록
        """
        target_dir = output_dir or self.output_dir
        os.makedirs(target_dir, exist_ok=True)
        results = []
        total = len(scene_indices)

        temp_html_path = None

        try:
            driver = self._ensure_driver()

            # HTML 파일로 저장
            temp_html_path = self._load_html_content(html_content)

            for i, scene_idx in enumerate(scene_indices):
                try:
                    # 파일 로드 (첫 번째 또는 새로고침 필요 시)
                    if i == 0:
                        driver.get(f'file:///{temp_html_path}')
                        from selenium.webdriver.support.ui import WebDriverWait
                        WebDriverWait(driver, 10).until(
                            lambda d: d.execute_script('return document.readyState') == 'complete'
                        )
                        time.sleep(0.5)

                    # 특정 씬 표시 (0-indexed)
                    self._show_specific_scene(driver, scene_idx)
                    time.sleep(0.3)

                    # 출력 경로
                    output_path = os.path.join(target_dir, f"scene_{scene_idx + 1:03d}.png")

                    # 스크린샷 캡처
                    screenshot_data = driver.get_screenshot_as_png()

                    if PIL_AVAILABLE:
                        img = Image.open(BytesIO(screenshot_data))
                        if img.size != (self.width, self.height):
                            img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
                        # 🔴 v3.11: 무손실 PNG 저장 (compress_level=0)
                        img.save(output_path, 'PNG', optimize=False, compress_level=0)
                    else:
                        with open(output_path, 'wb') as f:
                            f.write(screenshot_data)

                    results.append(output_path)
                    print(f"✅ 씬 {scene_idx + 1} 썸네일 생성 완료")

                except Exception as e:
                    print(f"❌ 씬 {scene_idx + 1} 썸네일 생성 실패: {e}")

                if progress_callback:
                    progress_callback(i + 1, total)

        except Exception as e:
            print(f"❌ 썸네일 생성 오류: {e}")
            traceback.print_exc()

        finally:
            if temp_html_path and os.path.exists(temp_html_path):
                try:
                    os.unlink(temp_html_path)
                except:
                    pass

        print(f"✅ 선택적 썸네일 생성 완료: {len(results)}/{total}")
        return results

    def close(self):
        """드라이버 종료"""
        if self._driver:
            try:
                self._driver.quit()
            except:
                pass
            self._driver = None
            self._initialized = False

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# 하위 호환성
InfographicThumbnailGenerator = SeleniumThumbnailGenerator


# ============================================================
# Streamlit 호출용 동기 래퍼 함수
# ============================================================

def generate_thumbnail_sync(
    scene: InfographicScene,
    html_code: str,
    output_dir: str = "outputs/infographic_thumbnails"
) -> bool:
    """단일 씬 썸네일 생성"""
    generator = SeleniumThumbnailGenerator(output_dir=output_dir)
    try:
        return generator.capture_first_frame(scene, html_code)
    finally:
        generator.close()


def generate_all_thumbnails_sync(
    infographic_data: InfographicData,
    output_dir: str = "outputs/infographic_thumbnails",
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[int, bool]:
    """전체 썸네일 생성 - Streamlit용"""
    generator = SeleniumThumbnailGenerator(output_dir=output_dir)
    return generator.generate_all_thumbnails(infographic_data, progress_callback)


def generate_selected_thumbnails_sync(
    html_content: str,
    scene_indices: List[int],
    output_dir: str = "outputs/infographic_thumbnails",
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[str]:
    """선택된 씬 썸네일 생성 - Streamlit용"""
    generator = SeleniumThumbnailGenerator(output_dir=output_dir)
    try:
        return generator.generate_selected_thumbnails(
            html_content, scene_indices, output_dir, progress_callback
        )
    finally:
        generator.close()


def get_thumbnail_generator(output_dir: str = None) -> SeleniumThumbnailGenerator:
    """썸네일 생성기 인스턴스 생성"""
    if output_dir:
        return SeleniumThumbnailGenerator(output_dir=output_dir)
    return SeleniumThumbnailGenerator()


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    print("=== 썸네일 생성기 테스트 ===")

    available, msg = check_selenium_available()
    print(f"Selenium 사용 가능: {available}")
    print(f"메시지: {msg}")

    if not available:
        print("\n해결 방법:")
        print("1. python utils/diagnose_selenium_env.py --clear-cache")
        print("2. python utils/install_chromedriver.py")
