# -*- coding: utf-8 -*-
"""
Selenium을 이용한 ImageFX 쿠키 자동 추출 모듈

브라우저를 자동화하여 ImageFX 사이트에 접속하고 쿠키를 추출합니다.
기존 Chrome 프로필을 사용하여 로그인 상태를 유지합니다.

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
from typing import Dict, Optional, Tuple
from pathlib import Path

# Selenium imports
SELENIUM_AVAILABLE = False
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    print("[SeleniumCookie] selenium 또는 webdriver-manager 미설치")
    print("[SeleniumCookie] 설치: pip install selenium webdriver-manager")


# ImageFX URL
IMAGEFX_URL = "https://labs.google.com/fx/ko/tools/image-fx"
IMAGEFX_URL_EN = "https://labs.google.com/fx/tools/image-fx"


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

        # WebDriver 초기화
        print("[SeleniumCookie] ChromeDriver 초기화 중...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

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

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get("https://www.google.com")

        title = driver.title
        driver.quit()

        return True, f"Selenium 정상 작동 (Google 페이지 제목: {title})"

    except Exception as e:
        return False, f"Selenium 오류: {e}"


# 테스트용
if __name__ == "__main__":
    print("=" * 60)
    print("Selenium 쿠키 추출 테스트")
    print("=" * 60)

    # Selenium 확인
    available, msg = check_selenium_available()
    print(f"\nSelenium 상태: {msg}")

    if not available:
        print("\n설치 방법:")
        print("  pip install selenium webdriver-manager")
        exit(1)

    # 빠른 테스트
    print("\n빠른 테스트 중...")
    ok, msg = quick_test_selenium()
    print(f"결과: {msg}")

    if not ok:
        exit(1)

    # 실제 쿠키 추출 테스트
    print("\n쿠키 추출 테스트 (브라우저 창이 열립니다)...")
    print("필요시 Google 계정으로 로그인하세요.")

    cookies = extract_imagefx_cookies_with_selenium(
        use_existing_profile=True,
        headless=False,
        timeout=120
    )

    if cookies:
        print("\n추출된 쿠키:")
        for name, value in cookies.items():
            print(f"  {name}: {value[:30]}...")

        print("\nHeader String 형식:")
        header = cookies_to_header_string(cookies)
        print(f"  {header[:100]}...")
    else:
        print("\n쿠키 추출 실패")
