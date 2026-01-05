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
