# -*- coding: utf-8 -*-
"""
ImageFX 쿠키 상태 관리 모듈

쿠키 만료 감지, 상태 관리, 갱신 안내 기능 제공
"""

import os
import json
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CookieStatus(Enum):
    """쿠키 상태"""
    VALID = "valid"           # 유효함
    EXPIRED = "expired"       # 만료됨
    NOT_SET = "not_set"       # 설정되지 않음
    UNKNOWN = "unknown"       # 알 수 없음


@dataclass
class CookieState:
    """쿠키 상태 정보"""
    status: CookieStatus
    message: str
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    error_time: Optional[datetime] = None


# 프로젝트 루트 및 설정 경로
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "data" / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# 쿠키 상태 파일 경로
COOKIE_STATE_FILE = CONFIG_DIR / "imagefx_cookie_state.json"

# 쿠키 저장 경로
SECRETS_DIR = PROJECT_ROOT / "data" / ".secrets"
SECRETS_DIR.mkdir(parents=True, exist_ok=True)
COOKIE_FILE = SECRETS_DIR / "imagefx_cookie.txt"


def load_imagefx_cookie() -> str:
    """
    ImageFX 쿠키 로드

    Returns:
        쿠키 문자열 (없으면 빈 문자열)
    """
    # 1. 환경변수에서 먼저 확인
    env_cookie = os.getenv("IMAGEFX_COOKIE", "").strip()
    if env_cookie:
        return env_cookie

    # 2. 파일에서 확인
    if COOKIE_FILE.exists():
        try:
            cookie_value = COOKIE_FILE.read_text(encoding="utf-8").strip()
            if cookie_value:
                return cookie_value
        except Exception:
            pass

    return ""


def save_imagefx_cookie(cookie: str) -> bool:
    """
    ImageFX 쿠키 저장

    Args:
        cookie: 저장할 쿠키 문자열

    Returns:
        저장 성공 여부
    """
    try:
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        COOKIE_FILE.write_text(cookie.strip(), encoding="utf-8")
        print(f"[CookieManager] Cookie saved ({len(cookie)} chars)")
        return True
    except Exception as e:
        print(f"[CookieManager] Failed to save cookie: {e}")
        return False


def get_cookie_state() -> CookieState:
    """현재 쿠키 상태 조회"""

    # 쿠키 존재 확인
    cookie = load_imagefx_cookie()

    if not cookie:
        return CookieState(
            status=CookieStatus.NOT_SET,
            message="ImageFX cookie is not set."
        )

    # 상태 파일 로드
    state_data = _load_state_file()

    if state_data.get("expired"):
        error_time = None
        if state_data.get("error_time"):
            try:
                error_time = datetime.fromisoformat(state_data["error_time"])
            except:
                pass

        return CookieState(
            status=CookieStatus.EXPIRED,
            message="Cookie expired. Please enter a new cookie.",
            last_error=state_data.get("last_error"),
            error_time=error_time
        )

    last_success = None
    if state_data.get("last_success"):
        try:
            last_success = datetime.fromisoformat(state_data["last_success"])
        except:
            pass

    return CookieState(
        status=CookieStatus.VALID,
        message="Cookie is valid.",
        last_success=last_success
    )


def mark_cookie_expired(error_message: str):
    """쿠키를 만료 상태로 표시"""

    state_data = {
        "expired": True,
        "last_error": error_message,
        "error_time": datetime.now().isoformat()
    }

    _save_state_file(state_data)

    print(f"[CookieManager] Cookie marked as expired")


def mark_cookie_valid():
    """쿠키를 유효 상태로 표시 (성공 시 호출)"""

    state_data = {
        "expired": False,
        "last_success": datetime.now().isoformat(),
        "last_error": None,
        "error_time": None
    }

    _save_state_file(state_data)


def reset_cookie_state():
    """쿠키 상태 초기화 (새 쿠키 입력 시)"""

    state_data = {
        "expired": False,
        "last_success": None,
        "last_error": None,
        "error_time": None
    }

    _save_state_file(state_data)

    print(f"[CookieManager] Cookie state reset")


def is_auth_error(error_message: str) -> bool:
    """인증 관련 에러인지 확인"""

    auth_indicators = [
        "401",
        "UNAUTHENTICATED",
        "authentication credentials",
        "OAuth 2 access token",
        "login cookie",
        "invalid authentication",
        "expired",
        "unauthorized",
        "Request had invalid authentication"
    ]

    error_lower = error_message.lower()
    return any(indicator.lower() in error_lower for indicator in auth_indicators)


def _load_state_file() -> dict:
    """상태 파일 로드"""
    if COOKIE_STATE_FILE.exists():
        try:
            with open(COOKIE_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def _save_state_file(data: dict):
    """상태 파일 저장"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# 쿠키 갱신 안내 메시지
COOKIE_RENEWAL_GUIDE = """
## ImageFX Cookie Renewal Guide

Google cookies expire after a certain time for security reasons.
Follow the steps below to extract a new cookie.

### Step-by-Step Guide

**Step 1: Access ImageFX Page**
- Go to [labs.google/fx/tools/image-fx](https://labs.google/fx/tools/image-fx)
- Make sure you're logged in with your Google account

**Step 2: Open Cookie Editor Extension**
- Click the Cookie Editor icon in the top right of your browser
- (Not installed? [Install Chrome Extension](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm))

**Step 3: Export Cookies**
- Click **Export** button in Cookie Editor
- Select **Header String**
- Cookie is automatically copied to clipboard

**Step 4: Enter New Cookie**
- Paste the copied cookie in the input field below
- Click **Save Cookie** button

### Notes
- Cookies typically expire after **a few hours to 1 day**
- If cookies expire frequently, try refreshing (F5) the ImageFX page and re-extracting
- Logging out and back in will issue a new cookie
"""

COOKIE_RENEWAL_GUIDE_KO = """
## ImageFX 쿠키 갱신 방법

Google 쿠키는 보안상 일정 시간 후 만료됩니다. 아래 단계를 따라 새 쿠키를 추출해주세요.

### 단계별 안내

**1단계: ImageFX 페이지 접속**
- [labs.google/fx/tools/image-fx](https://labs.google/fx/tools/image-fx) 접속
- Google 계정으로 로그인 확인

**2단계: Cookie Editor 확장 프로그램 열기**
- 브라우저 우측 상단의 Cookie Editor 아이콘 클릭
- (설치 안 됨? [Chrome 확장 프로그램](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 설치)

**3단계: 쿠키 내보내기**
- Cookie Editor에서 **Export** 버튼 클릭
- **Header String** 선택
- 자동으로 클립보드에 복사됨

**4단계: 새 쿠키 입력**
- 아래 입력창에 복사한 쿠키 붙여넣기
- **쿠키 저장** 버튼 클릭

### 참고사항
- 쿠키는 보통 **몇 시간 ~ 1일** 후 만료됩니다
- 자주 만료되면 ImageFX 페이지에서 **새로고침(F5)** 후 쿠키 재추출
- 로그아웃 후 다시 로그인하면 새 쿠키 발급
"""


# ============================================================
# 자동 쿠키 갱신 기능 (v2.0)
# ============================================================

def auto_refresh_cookies(use_selenium_fallback: bool = True) -> tuple:
    """
    자동 쿠키 갱신 시도

    1차: Chrome 프로필에서 직접 추출 (빠르고 자동)
    2차: Selenium으로 추출 (브라우저 창 열림)

    Args:
        use_selenium_fallback: Chrome 추출 실패 시 Selenium 사용 여부

    Returns:
        (success: bool, message: str, method: str)
        - success: 갱신 성공 여부
        - message: 결과 메시지
        - method: 사용된 방법 ("chrome", "selenium", "failed")
    """
    print("[CookieManager] 자동 쿠키 갱신 시작...")

    # 방법 1: Chrome 프로필에서 직접 추출
    try:
        from utils.cookie_extractor import (
            extract_imagefx_cookies_from_chrome,
            cookies_to_header_string,
            validate_imagefx_cookies,
            CRYPTO_AVAILABLE
        )

        if CRYPTO_AVAILABLE:
            print("[CookieManager] Chrome 프로필에서 쿠키 추출 시도...")
            cookies = extract_imagefx_cookies_from_chrome()

            if cookies and validate_imagefx_cookies(cookies):
                # Header String 형식으로 변환
                cookie_header = cookies_to_header_string(cookies)

                # 쿠키 저장
                if save_imagefx_cookie(cookie_header):
                    reset_cookie_state()
                    print(f"[CookieManager] Chrome에서 쿠키 추출 성공 ({len(cookies)}개)")
                    return True, f"Chrome에서 쿠키 자동 추출 성공 ({len(cookies)}개 쿠키)", "chrome"
                else:
                    print("[CookieManager] 쿠키 저장 실패")
            else:
                print("[CookieManager] Chrome에서 유효한 쿠키를 찾지 못함")
        else:
            print("[CookieManager] Chrome 쿠키 추출 라이브러리 미설치")

    except ImportError as e:
        print(f"[CookieManager] Chrome 추출 모듈 import 실패: {e}")
    except Exception as e:
        print(f"[CookieManager] Chrome 추출 실패: {e}")

    # 방법 2: Selenium으로 추출
    if use_selenium_fallback:
        try:
            from utils.selenium_cookie_extractor import (
                extract_imagefx_cookies_with_selenium,
                cookies_to_header_string as selenium_to_header,
                check_selenium_available,
                SELENIUM_AVAILABLE
            )

            if SELENIUM_AVAILABLE:
                available, msg = check_selenium_available()
                if available:
                    print("[CookieManager] Selenium으로 쿠키 추출 시도...")
                    print("[CookieManager] 브라우저 창이 열립니다. 필요시 Google 로그인하세요.")

                    cookies = extract_imagefx_cookies_with_selenium(
                        use_existing_profile=True,
                        headless=False,
                        timeout=120,
                        wait_for_login=True
                    )

                    if cookies:
                        # Header String 형식으로 변환
                        cookie_header = selenium_to_header(cookies)

                        # 쿠키 저장
                        if save_imagefx_cookie(cookie_header):
                            reset_cookie_state()
                            print(f"[CookieManager] Selenium에서 쿠키 추출 성공 ({len(cookies)}개)")
                            return True, f"Selenium으로 쿠키 자동 추출 성공 ({len(cookies)}개 쿠키)", "selenium"
                        else:
                            print("[CookieManager] 쿠키 저장 실패")
                    else:
                        print("[CookieManager] Selenium에서 쿠키 추출 실패")
                else:
                    print(f"[CookieManager] Selenium 사용 불가: {msg}")
            else:
                print("[CookieManager] Selenium 미설치")

        except ImportError as e:
            print(f"[CookieManager] Selenium 모듈 import 실패: {e}")
        except Exception as e:
            print(f"[CookieManager] Selenium 추출 실패: {e}")

    print("[CookieManager] 자동 쿠키 갱신 실패")
    return False, "자동 쿠키 갱신 실패. 수동으로 갱신해주세요.", "failed"


def check_auto_refresh_available() -> dict:
    """
    자동 갱신 기능 사용 가능 여부 확인

    Returns:
        {
            "chrome_available": bool,
            "chrome_message": str,
            "selenium_available": bool,
            "selenium_message": str,
            "any_available": bool
        }
    """
    result = {
        "chrome_available": False,
        "chrome_message": "",
        "selenium_available": False,
        "selenium_message": "",
        "any_available": False
    }

    # Chrome 직접 추출 확인
    try:
        from utils.cookie_extractor import CRYPTO_AVAILABLE, check_chrome_installation

        if not CRYPTO_AVAILABLE:
            result["chrome_message"] = "필요 패키지 미설치 (pywin32, pycryptodome)"
        elif not check_chrome_installation():
            result["chrome_message"] = "Chrome 브라우저 미설치"
        else:
            result["chrome_available"] = True
            result["chrome_message"] = "Chrome 프로필에서 쿠키 추출 가능"

    except ImportError:
        result["chrome_message"] = "cookie_extractor 모듈 없음"
    except Exception as e:
        result["chrome_message"] = f"확인 오류: {e}"

    # Selenium 확인
    try:
        from utils.selenium_cookie_extractor import check_selenium_available, SELENIUM_AVAILABLE

        if not SELENIUM_AVAILABLE:
            result["selenium_message"] = "selenium 패키지 미설치"
        else:
            available, msg = check_selenium_available()
            result["selenium_available"] = available
            result["selenium_message"] = msg

    except ImportError:
        result["selenium_message"] = "selenium_cookie_extractor 모듈 없음"
    except Exception as e:
        result["selenium_message"] = f"확인 오류: {e}"

    result["any_available"] = result["chrome_available"] or result["selenium_available"]

    return result


def get_auto_refresh_status_message() -> str:
    """
    자동 갱신 상태 메시지 반환 (UI용)
    """
    status = check_auto_refresh_available()

    messages = []

    if status["chrome_available"]:
        messages.append("Chrome 직접 추출")
    if status["selenium_available"]:
        messages.append("Selenium 브라우저 자동화")

    if messages:
        return f"자동 갱신 가능 ({', '.join(messages)})"
    else:
        return "자동 갱신 불가 (수동 갱신만 가능)"
