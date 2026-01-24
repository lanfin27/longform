# -*- coding: utf-8 -*-
"""
Selenium을 이용한 ImageFX 쿠키 자동 추출 모듈

브라우저를 자동화하여 ImageFX 사이트에 접속하고 쿠키를 추출합니다.
기존 Chrome 프로필을 사용하여 로그인 상태를 유지합니다.

v2.0: ChromeDriver 캐시 문제 해결 (WinError 193)
- 손상된 캐시 자동 감지 및 정리
- 여러 초기화 방법 순차 시도
- ChromeDriver 파일 유효성 검사

요구사항:
- selenium
- webdriver-manager

설치:
    pip install selenium webdriver-manager

사용법:
    from utils.selenium_cookie_extractor import extract_imagefx_cookies_with_selenium

    cookies = extract_imagefx_cookies_with_selenium()
    if cookies:
        cookie_header = cookies_to_header_string(cookies)
"""

import os
import json
import time
import shutil
import logging
from typing import Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Selenium imports
SELENIUM_AVAILABLE = False
WEBDRIVER_MANAGER_AVAILABLE = False
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import WebDriverException
    SELENIUM_AVAILABLE = True

    try:
        from webdriver_manager.chrome import ChromeDriverManager
        WEBDRIVER_MANAGER_AVAILABLE = True
    except ImportError:
        print("[SeleniumCookie] webdriver-manager 미설치 (선택사항)")
except ImportError:
    print("[SeleniumCookie] selenium 미설치")
    print("[SeleniumCookie] 설치: pip install selenium webdriver-manager")


# ImageFX URL
IMAGEFX_URL = "https://labs.google.com/fx/ko/tools/image-fx"
IMAGEFX_URL_EN = "https://labs.google.com/fx/tools/image-fx"


# ============================================================
# v2.0: ChromeDriver 캐시 관리 및 초기화 개선
# ============================================================

def clear_webdriver_cache() -> bool:
    """
    webdriver-manager 캐시 정리 (손상된 ChromeDriver 파일 삭제)

    Returns:
        성공 여부
    """
    cache_paths = [
        os.path.expanduser("~/.wdm"),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'webdriver'),
    ]

    cleared = False
    for cache_path in cache_paths:
        if os.path.exists(cache_path):
            try:
                shutil.rmtree(cache_path)
                print(f"[SeleniumCookie] 캐시 삭제됨: {cache_path}")
                cleared = True
            except Exception as e:
                print(f"[SeleniumCookie] 캐시 삭제 실패 ({cache_path}): {e}")

    return cleared


def validate_chromedriver_file(driver_path: str) -> bool:
    """
    ChromeDriver 파일 유효성 검사

    Args:
        driver_path: ChromeDriver 경로

    Returns:
        유효 여부
    """
    if not os.path.exists(driver_path):
        return False

    # 파일 크기 확인 (손상된 파일 감지)
    try:
        file_size = os.path.getsize(driver_path)
        # ChromeDriver는 보통 10MB 이상
        if file_size < 1000000:  # 1MB 미만이면 손상된 것으로 간주
            print(f"[SeleniumCookie] ChromeDriver 파일이 너무 작음 ({file_size} bytes), 손상 의심")
            return False
        return True
    except Exception as e:
        print(f"[SeleniumCookie] 파일 검사 오류: {e}")
        return False


def get_chrome_driver_robust(
    chrome_options: Options,
    max_retries: int = 2,
    auto_clear_cache: bool = True
) -> Optional[webdriver.Chrome]:
    """
    ChromeDriver 인스턴스 생성 (개선된 버전 - 여러 방법 순차 시도)

    Args:
        chrome_options: Chrome 옵션
        max_retries: 최대 재시도 횟수
        auto_clear_cache: 실패 시 자동 캐시 정리

    Returns:
        WebDriver 인스턴스 또는 None
    """
    driver = None
    last_error = None

    for attempt in range(max_retries):
        if attempt > 0:
            print(f"[SeleniumCookie] 재시도 {attempt + 1}/{max_retries}...")

        # 방법 1: webdriver-manager 사용 (권장)
        if WEBDRIVER_MANAGER_AVAILABLE:
            try:
                print("[SeleniumCookie] 방법 1: webdriver-manager로 ChromeDriver 설치...")
                driver_path = ChromeDriverManager().install()
                print(f"[SeleniumCookie] ChromeDriver 경로: {driver_path}")

                # 파일 유효성 검사
                if not validate_chromedriver_file(driver_path):
                    raise ValueError("ChromeDriver 파일이 손상되었습니다")

                service = Service(executable_path=driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                print("[SeleniumCookie] ✅ webdriver-manager로 초기화 성공")
                return driver

            except OSError as e:
                error_msg = str(e)
                print(f"[SeleniumCookie] webdriver-manager 실패: {e}")

                # WinError 193 처리 - ChromeDriver 파일 손상
                if "193" in error_msg or "올바른 Win32 응용 프로그램" in error_msg:
                    print("[SeleniumCookie] ChromeDriver 파일 손상 감지!")
                    if auto_clear_cache:
                        print("[SeleniumCookie] 캐시 정리 중...")
                        clear_webdriver_cache()
                        continue  # 재시도
                last_error = e

            except Exception as e:
                print(f"[SeleniumCookie] webdriver-manager 실패: {e}")
                last_error = e

        # 방법 2: Selenium 4 자동 드라이버 관리 사용
        try:
            print("[SeleniumCookie] 방법 2: Selenium 자동 드라이버 관리...")
            # Selenium 4.6+에서는 Service 없이도 자동으로 드라이버 관리
            driver = webdriver.Chrome(options=chrome_options)
            print("[SeleniumCookie] ✅ Selenium 자동 관리로 초기화 성공")
            return driver

        except OSError as e:
            error_msg = str(e)
            print(f"[SeleniumCookie] Selenium 자동 관리 실패: {e}")

            if "193" in error_msg or "올바른 Win32 응용 프로그램" in error_msg:
                if auto_clear_cache:
                    clear_webdriver_cache()
                    continue
            last_error = e

        except Exception as e:
            print(f"[SeleniumCookie] Selenium 자동 관리 실패: {e}")
            last_error = e

        # 방법 3: 시스템 PATH에서 chromedriver 찾기
        try:
            print("[SeleniumCookie] 방법 3: 시스템 PATH에서 ChromeDriver 검색...")
            service = Service()  # 기본값 사용
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print("[SeleniumCookie] ✅ 시스템 PATH의 ChromeDriver로 초기화 성공")
            return driver

        except Exception as e:
            print(f"[SeleniumCookie] 시스템 PATH 검색 실패: {e}")
            last_error = e

        # 방법 4: 수동 경로 지정 시도
        manual_paths = [
            r"C:\chromedriver\chromedriver.exe",
            r"C:\webdrivers\chromedriver.exe",
            os.path.join(os.getcwd(), "chromedriver.exe"),
            os.path.join(os.getcwd(), "drivers", "chromedriver.exe"),
        ]

        for path in manual_paths:
            if os.path.exists(path) and validate_chromedriver_file(path):
                try:
                    print(f"[SeleniumCookie] 방법 4: 수동 경로 시도 - {path}")
                    service = Service(executable_path=path)
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    print(f"[SeleniumCookie] ✅ 수동 경로로 초기화 성공: {path}")
                    return driver
                except Exception as e:
                    print(f"[SeleniumCookie] 수동 경로 실패 ({path}): {e}")
                    last_error = e

    # 모든 방법 실패
    print(f"[SeleniumCookie] ❌ 모든 ChromeDriver 초기화 방법 실패")
    if last_error:
        print(f"[SeleniumCookie] 마지막 오류: {last_error}")
    return None


def diagnose_chromedriver() -> Dict:
    """
    ChromeDriver 설치 상태 진단

    Returns:
        진단 결과 딕셔너리
    """
    result = {
        'selenium_available': SELENIUM_AVAILABLE,
        'webdriver_manager_available': WEBDRIVER_MANAGER_AVAILABLE,
        'selenium_version': None,
        'webdriver_manager_version': None,
        'chromedriver_path': None,
        'chromedriver_valid': False,
        'cache_exists': False,
        'errors': []
    }

    # Selenium 버전
    if SELENIUM_AVAILABLE:
        try:
            import selenium
            result['selenium_version'] = selenium.__version__
        except Exception as e:
            result['errors'].append(f"Selenium 버전 확인 실패: {e}")

    # webdriver-manager 버전
    if WEBDRIVER_MANAGER_AVAILABLE:
        try:
            import webdriver_manager
            result['webdriver_manager_version'] = webdriver_manager.__version__
        except Exception as e:
            result['errors'].append(f"webdriver-manager 버전 확인 실패: {e}")

        # ChromeDriver 경로 확인
        try:
            driver_path = ChromeDriverManager().install()
            result['chromedriver_path'] = driver_path
            result['chromedriver_valid'] = validate_chromedriver_file(driver_path)
        except Exception as e:
            result['errors'].append(f"ChromeDriver 경로 확인 실패: {e}")

    # 캐시 존재 여부
    cache_path = os.path.expanduser("~/.wdm")
    result['cache_exists'] = os.path.exists(cache_path)

    return result


def check_selenium_available() -> Tuple[bool, str]:
    """
    Selenium 사용 가능 여부 확인

    Returns:
        (available: bool, message: str)
    """
    if not SELENIUM_AVAILABLE:
        return False, "selenium 패키지가 설치되어 있지 않습니다.\n설치: pip install selenium webdriver-manager"

    return True, "Selenium 사용 가능"


def get_chrome_profile_path() -> Optional[str]:
    """
    기존 Chrome 프로필 경로 반환

    Returns:
        Chrome User Data 디렉토리 경로
    """
    if os.name == 'nt':
        # Windows
        user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
        if os.path.exists(user_data_dir):
            return user_data_dir

    elif os.name == 'posix':
        # macOS
        mac_path = os.path.expanduser("~/Library/Application Support/Google/Chrome")
        if os.path.exists(mac_path):
            return mac_path

        # Linux
        linux_path = os.path.expanduser("~/.config/google-chrome")
        if os.path.exists(linux_path):
            return linux_path

    return None


def extract_imagefx_cookies_with_selenium(
    use_existing_profile: bool = True,
    headless: bool = False,
    timeout: int = 120,
    wait_for_login: bool = True
) -> Optional[Dict[str, str]]:
    """
    Selenium으로 ImageFX 사이트 접속하여 쿠키 추출

    Args:
        use_existing_profile: 기존 Chrome 프로필 사용 여부 (로그인 상태 유지)
        headless: 브라우저 숨김 모드 (Google 로그인은 headless 불가할 수 있음)
        timeout: 로그인/페이지 로드 대기 시간 (초)
        wait_for_login: 로그인 완료까지 대기 여부

    Returns:
        {"cookie_name": "cookie_value", ...} 또는 None
    """
    if not SELENIUM_AVAILABLE:
        print("[SeleniumCookie] Selenium이 설치되어 있지 않습니다.")
        return None

    print("[SeleniumCookie] Selenium으로 쿠키 추출 시작...")

    driver = None

    try:
        # Chrome 옵션 설정
        chrome_options = Options()

        if headless:
            chrome_options.add_argument("--headless=new")
            print("[SeleniumCookie] Headless 모드 사용")

        # 기존 Chrome 프로필 사용 (로그인 상태 유지)
        if use_existing_profile:
            profile_path = get_chrome_profile_path()
            if profile_path:
                # 기존 프로필 복사 사용 (충돌 방지)
                # Chrome이 이미 실행 중이면 프로필 잠금이 걸릴 수 있음
                try:
                    chrome_options.add_argument(f"--user-data-dir={profile_path}")
                    chrome_options.add_argument("--profile-directory=Default")
                    print(f"[SeleniumCookie] Chrome 프로필 사용: {profile_path}")
                except Exception as e:
                    print(f"[SeleniumCookie] 프로필 사용 실패: {e}")
                    print("[SeleniumCookie] 새 프로필로 진행합니다.")

        # 자동화 감지 우회
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # User-Agent 설정
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # v2.0: 개선된 WebDriver 초기화 (여러 방법 순차 시도)
        print("[SeleniumCookie] ChromeDriver 초기화 중...")
        driver = get_chrome_driver_robust(
            chrome_options=chrome_options,
            max_retries=2,
            auto_clear_cache=True
        )

        if driver is None:
            print("[SeleniumCookie] ❌ ChromeDriver 초기화 실패")
            print("[SeleniumCookie] 해결 방법:")
            print("  1. 캐시 삭제: 사용자 홈 폴더/.wdm 삭제")
            print("  2. 패키지 재설치: pip install selenium webdriver-manager --upgrade --force-reinstall")
            print("  3. Chrome 브라우저 업데이트")
            return None

        # 자동화 감지 우회 스크립트
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })

        # ImageFX 접속
        print(f"[SeleniumCookie] ImageFX 접속: {IMAGEFX_URL}")
        driver.get(IMAGEFX_URL)

        # 페이지 로드 대기
        time.sleep(3)

        # 로그인 확인 (세션 토큰 쿠키 존재 여부)
        cookies = driver.get_cookies()
        session_cookie = _find_session_cookie(cookies)

        if not session_cookie and wait_for_login:
            print("[SeleniumCookie] 로그인이 필요합니다.")
            print(f"[SeleniumCookie] 브라우저에서 Google 계정으로 로그인하세요.")
            print(f"[SeleniumCookie] {timeout}초 내에 로그인을 완료하세요...")

            # 로그인 대기
            start_time = time.time()
            while time.time() - start_time < timeout:
                cookies = driver.get_cookies()
                session_cookie = _find_session_cookie(cookies)

                if session_cookie:
                    print("[SeleniumCookie] 로그인 감지!")
                    break

                time.sleep(2)

                # 진행 상황 표시
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0:
                    print(f"[SeleniumCookie] 로그인 대기 중... ({elapsed}/{timeout}초)")

        if not session_cookie:
            print("[SeleniumCookie] 로그인 시간 초과")
            return None

        # 로그인 후 페이지 새로고침하여 모든 쿠키 로드
        print("[SeleniumCookie] 페이지 새로고침하여 쿠키 로드...")
        driver.refresh()
        time.sleep(3)

        # 모든 쿠키 추출
        all_cookies = driver.get_cookies()

        # 필요한 쿠키 필터링
        cookie_dict = {}

        # ImageFX 핵심 쿠키
        target_cookies = [
            '__Secure-next-auth.session-token',
            '__Secure-next-auth.callback-url',
            '__Host-next-auth.csrf-token',
        ]

        # Google 인증 쿠키
        google_cookies = [
            'SID', 'HSID', 'SSID', 'APISID', 'SAPISID',
            '__Secure-1PSID', '__Secure-3PSID',
            '__Secure-1PAPISID', '__Secure-3PAPISID',
            'NID', 'AEC',
        ]

        for cookie in all_cookies:
            name = cookie['name']
            domain = cookie.get('domain', '')

            # 타겟 쿠키이거나 Google 관련 도메인
            if name in target_cookies or name in google_cookies:
                cookie_dict[name] = cookie['value']
                print(f"[SeleniumCookie] 쿠키 추출: {name} (도메인: {domain})")

            # labs.google.com 도메인의 모든 쿠키
            elif 'labs.google' in domain or 'google.com' in domain:
                if 'next-auth' in name.lower() or name.startswith('__Secure'):
                    cookie_dict[name] = cookie['value']
                    print(f"[SeleniumCookie] 쿠키 추출: {name} (도메인: {domain})")

        print(f"[SeleniumCookie] 총 {len(cookie_dict)}개 쿠키 추출 완료")

        return cookie_dict if cookie_dict else None

    except Exception as e:
        print(f"[SeleniumCookie] 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        if driver:
            try:
                driver.quit()
                print("[SeleniumCookie] 브라우저 종료")
            except:
                pass


def _find_session_cookie(cookies: list) -> Optional[dict]:
    """세션 토큰 쿠키 찾기"""
    for cookie in cookies:
        if 'session-token' in cookie['name'].lower():
            return cookie
        if cookie['name'] == '__Secure-next-auth.session-token':
            return cookie
    return None


def cookies_to_header_string(cookies: Dict[str, str]) -> str:
    """
    쿠키 딕셔너리를 HTTP Header String 형식으로 변환

    Returns:
        "name1=value1; name2=value2; ..."
    """
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])


def cookies_to_cookie_editor_format(cookies: Dict[str, str], domain: str = ".google.com") -> str:
    """
    쿠키를 Cookie-Editor Export 형식(JSON)으로 변환

    Args:
        cookies: 쿠키 딕셔너리
        domain: 쿠키 도메인

    Returns:
        JSON 문자열
    """
    cookie_list = []

    for name, value in cookies.items():
        # 도메인 추론
        if 'next-auth' in name.lower():
            cookie_domain = ".labs.google.com"
        else:
            cookie_domain = domain

        cookie_list.append({
            "name": name,
            "value": value,
            "domain": cookie_domain,
            "path": "/",
            "secure": True,
            "httpOnly": True if name.startswith('__Secure') or name.startswith('__Host') else False,
            "sameSite": "Lax"
        })

    return json.dumps(cookie_list, indent=2, ensure_ascii=False)


def quick_test_selenium() -> Tuple[bool, str]:
    """
    Selenium 빠른 테스트 (브라우저 열기만)

    Returns:
        (success: bool, message: str)
    """
    if not SELENIUM_AVAILABLE:
        return False, "Selenium이 설치되어 있지 않습니다."

    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # v2.0: 개선된 초기화 사용
        driver = get_chrome_driver_robust(
            chrome_options=chrome_options,
            max_retries=2,
            auto_clear_cache=True
        )

        if driver is None:
            return False, "ChromeDriver 초기화 실패. 캐시 삭제 후 재시도하세요: ~/.wdm 폴더 삭제"

        driver.get("https://www.google.com")

        title = driver.title
        driver.quit()

        return True, f"Selenium 정상 작동 (Google 페이지 제목: {title})"

    except OSError as e:
        error_msg = str(e)
        if "193" in error_msg or "Win32" in error_msg:
            clear_webdriver_cache()
            return False, f"ChromeDriver 파일 손상. 캐시를 정리했습니다. 다시 시도하세요."
        return False, f"Selenium OSError: {e}"

    except Exception as e:
        return False, f"Selenium 오류: {e}"


# 테스트용
if __name__ == "__main__":
    print("=" * 60)
    print("Selenium 쿠키 추출 테스트 v2.0")
    print("=" * 60)

    # 1. 진단 정보 출력
    print("\n📋 진단 정보:")
    diagnosis = diagnose_chromedriver()
    print(f"  Selenium: {diagnosis.get('selenium_version', '미설치')}")
    print(f"  webdriver-manager: {diagnosis.get('webdriver_manager_version', '미설치')}")
    print(f"  ChromeDriver 경로: {diagnosis.get('chromedriver_path', '없음')}")
    print(f"  ChromeDriver 유효: {'✅' if diagnosis.get('chromedriver_valid') else '❌'}")
    print(f"  캐시 존재: {'✅' if diagnosis.get('cache_exists') else '❌'}")

    if diagnosis.get('errors'):
        print(f"  오류: {', '.join(diagnosis['errors'])}")

    # Selenium 확인
    available, msg = check_selenium_available()
    print(f"\nSelenium 상태: {msg}")

    if not available:
        print("\n설치 방법:")
        print("  pip install selenium webdriver-manager")
        exit(1)

    # 2. 빠른 테스트
    print("\n🧪 빠른 테스트 중...")
    ok, msg = quick_test_selenium()
    print(f"결과: {msg}")

    if not ok:
        print("\n💡 해결 방법:")
        print("  1. 캐시 삭제: 사용자 홈 폴더/.wdm 삭제")
        print("  2. 패키지 재설치: pip install selenium webdriver-manager --upgrade --force-reinstall")
        print("  3. Chrome 브라우저 업데이트")
        exit(1)

    # 3. 실제 쿠키 추출 테스트
    print("\n🍪 쿠키 추출 테스트 (브라우저 창이 열립니다)...")
    print("필요시 Google 계정으로 로그인하세요.")

    cookies = extract_imagefx_cookies_with_selenium(
        use_existing_profile=True,
        headless=False,
        timeout=120
    )

    if cookies:
        print("\n✅ 추출된 쿠키:")
        for name, value in cookies.items():
            print(f"  {name}: {value[:30]}...")

        print("\nHeader String 형식:")
        header = cookies_to_header_string(cookies)
        print(f"  {header[:100]}...")
    else:
        print("\n❌ 쿠키 추출 실패")
