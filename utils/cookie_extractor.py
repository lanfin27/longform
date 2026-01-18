# -*- coding: utf-8 -*-
"""
Chrome 브라우저에서 ImageFX 쿠키 직접 추출 모듈

Chrome 프로필의 쿠키 데이터베이스에서 Google/ImageFX 관련 쿠키를 추출합니다.
Windows에서 Chrome 쿠키는 AES-GCM으로 암호화되어 있어 DPAPI로 복호화 필요.

요구사항:
- Windows: pywin32, pycryptodome
- Chrome 브라우저 설치

사용법:
    from utils.cookie_extractor import extract_imagefx_cookies_from_chrome

    cookies = extract_imagefx_cookies_from_chrome()
    if cookies:
        cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
"""

import sqlite3
import os
import json
import shutil
from pathlib import Path
from typing import Dict, Optional
import base64
import tempfile

# Windows에서 Chrome 쿠키 복호화에 필요
CRYPTO_AVAILABLE = False
try:
    import win32crypt
    from Cryptodome.Cipher import AES
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        # Crypto 대신 Cryptodome 사용
        from Crypto.Cipher import AES
        import win32crypt
        CRYPTO_AVAILABLE = True
    except ImportError:
        print("[CookieExtractor] win32crypt/pycryptodome 미설치 - Chrome 쿠키 직접 추출 불가")


def get_chrome_cookie_path() -> Optional[Path]:
    """
    Chrome 쿠키 데이터베이스 경로 반환

    Returns:
        쿠키 DB 파일 경로 또는 None
    """
    # Windows
    if os.name == 'nt':
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        paths = [
            Path(local_app_data) / 'Google' / 'Chrome' / 'User Data' / 'Default' / 'Network' / 'Cookies',
            Path(local_app_data) / 'Google' / 'Chrome' / 'User Data' / 'Default' / 'Cookies',
        ]

        for path in paths:
            if path.exists():
                print(f"[CookieExtractor] Chrome 쿠키 경로: {path}")
                return path

    # macOS
    elif os.name == 'posix':
        home = Path.home()
        mac_path = home / 'Library' / 'Application Support' / 'Google' / 'Chrome' / 'Default' / 'Cookies'
        if mac_path.exists():
            return mac_path

        # Linux
        linux_path = home / '.config' / 'google-chrome' / 'Default' / 'Cookies'
        if linux_path.exists():
            return linux_path

    print("[CookieExtractor] Chrome 쿠키 파일을 찾을 수 없습니다.")
    return None


def get_chrome_encryption_key() -> Optional[bytes]:
    """
    Chrome 쿠키 암호화 키 추출 (Windows)

    Chrome은 Local State 파일에 저장된 암호화 키를 DPAPI로 보호합니다.

    Returns:
        복호화 키 또는 None
    """
    if not CRYPTO_AVAILABLE:
        return None

    if os.name != 'nt':
        print("[CookieExtractor] 암호화 키 추출은 Windows에서만 지원됩니다.")
        return None

    try:
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        local_state_path = Path(local_app_data) / 'Google' / 'Chrome' / 'User Data' / 'Local State'

        if not local_state_path.exists():
            print(f"[CookieExtractor] Local State 파일 없음: {local_state_path}")
            return None

        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)

        encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
        encrypted_key = encrypted_key[5:]  # 'DPAPI' 접두사 제거

        # Windows DPAPI로 복호화
        decrypted_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]

        print("[CookieExtractor] 암호화 키 추출 성공")
        return decrypted_key

    except Exception as e:
        print(f"[CookieExtractor] 암호화 키 추출 실패: {e}")
        return None


def decrypt_chrome_cookie(encrypted_value: bytes, key: bytes) -> str:
    """
    Chrome 쿠키 값 복호화

    Chrome 80+ 버전은 AES-256-GCM 암호화 사용 (v10/v11 prefix)
    구버전은 DPAPI 직접 사용

    Args:
        encrypted_value: 암호화된 쿠키 값
        key: 복호화 키

    Returns:
        복호화된 쿠키 값
    """
    if not CRYPTO_AVAILABLE:
        return ""

    try:
        # v10, v11 등 버전 접두사 확인 (Chrome 80+)
        if encrypted_value[:3] == b'v10' or encrypted_value[:3] == b'v11':
            nonce = encrypted_value[3:15]  # 12 bytes nonce
            ciphertext = encrypted_value[15:-16]  # 암호문
            tag = encrypted_value[-16:]  # 16 bytes auth tag

            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)

            return decrypted.decode('utf-8')
        else:
            # 구버전 DPAPI 직접 복호화
            return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode('utf-8')

    except Exception as e:
        # 복호화 실패 (빈 쿠키거나 다른 형식)
        return ""


def extract_imagefx_cookies_from_chrome() -> Optional[Dict[str, str]]:
    """
    Chrome 브라우저에서 ImageFX 관련 쿠키 직접 추출

    Chrome이 실행 중이어도 쿠키 DB를 복사해서 읽으므로 안전합니다.

    Returns:
        {"cookie_name": "cookie_value", ...} 또는 None
    """
    print("[CookieExtractor] Chrome에서 ImageFX 쿠키 추출 시작...")

    if not CRYPTO_AVAILABLE:
        print("[CookieExtractor] 암호화 라이브러리 미설치")
        return None

    cookie_path = get_chrome_cookie_path()
    if not cookie_path:
        return None

    encryption_key = get_chrome_encryption_key()
    if not encryption_key:
        return None

    # 쿠키 DB 복사 (Chrome이 사용 중일 수 있음)
    temp_dir = tempfile.mkdtemp()
    temp_cookie_path = Path(temp_dir) / "Cookies"

    try:
        shutil.copy2(cookie_path, temp_cookie_path)
        print(f"[CookieExtractor] 쿠키 DB 복사: {temp_cookie_path}")
    except Exception as e:
        print(f"[CookieExtractor] 쿠키 DB 복사 실패: {e}")
        return None

    try:
        conn = sqlite3.connect(temp_cookie_path)
        cursor = conn.cursor()

        # ImageFX/Google 관련 도메인의 쿠키 조회
        cursor.execute("""
            SELECT name, encrypted_value, host_key, expires_utc
            FROM cookies
            WHERE host_key LIKE '%google%'
               OR host_key LIKE '%labs.google%'
               OR host_key LIKE '%aitestkitchen%'
            ORDER BY expires_utc DESC
        """)

        cookies = {}

        # ImageFX 인증에 필요한 주요 쿠키 목록
        target_cookies = [
            # Next-Auth 세션 (ImageFX 핵심)
            '__Secure-next-auth.session-token',
            '__Secure-next-auth.callback-url',
            '__Host-next-auth.csrf-token',
            # Google 인증
            'SID', 'HSID', 'SSID', 'APISID', 'SAPISID',
            '__Secure-1PSID', '__Secure-3PSID',
            '__Secure-1PAPISID', '__Secure-3PAPISID',
            '__Secure-1PSIDCC', '__Secure-3PSIDCC',
            '__Secure-1PSIDTS', '__Secure-3PSIDTS',
            # 기타 유용한 쿠키
            'NID', 'AEC', 'CONSENT',
        ]

        for name, encrypted_value, host, expires in cursor.fetchall():
            # 타겟 쿠키이거나 imagefx 관련 쿠키
            if name in target_cookies or 'imagefx' in name.lower() or 'next-auth' in name.lower():
                if encrypted_value:
                    decrypted = decrypt_chrome_cookie(encrypted_value, encryption_key)
                    if decrypted:
                        cookies[name] = decrypted
                        print(f"[CookieExtractor] 쿠키 추출: {name} (도메인: {host})")

        conn.close()

        if cookies:
            print(f"[CookieExtractor] 총 {len(cookies)}개 쿠키 추출 완료")
            return cookies
        else:
            print("[CookieExtractor] ImageFX 관련 쿠키를 찾을 수 없습니다.")
            return None

    except Exception as e:
        print(f"[CookieExtractor] 쿠키 추출 실패: {e}")
        return None

    finally:
        # 임시 파일 정리
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def cookies_to_header_string(cookies: Dict[str, str]) -> str:
    """
    쿠키 딕셔너리를 HTTP Header String 형식으로 변환

    Args:
        cookies: {name: value, ...}

    Returns:
        "name1=value1; name2=value2; ..."
    """
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])


def validate_imagefx_cookies(cookies: Dict[str, str]) -> bool:
    """
    추출된 쿠키가 ImageFX 인증에 유효한지 검증

    Returns:
        True if valid, False otherwise
    """
    if not cookies:
        return False

    # 필수 쿠키 확인
    required_patterns = [
        '__Secure-next-auth.session-token',  # ImageFX 세션 토큰 (핵심)
    ]

    # 필수 쿠키 중 하나라도 있으면 OK
    for pattern in required_patterns:
        if pattern in cookies:
            print(f"[CookieExtractor] 필수 쿠키 확인: {pattern}")
            return True

    # Google 인증 쿠키 확인 (대체)
    google_auth_cookies = ['SID', '__Secure-1PSID', '__Secure-3PSID', 'SAPISID']
    google_count = sum(1 for c in google_auth_cookies if c in cookies)

    if google_count >= 2:
        print(f"[CookieExtractor] Google 인증 쿠키 {google_count}개 확인")
        return True

    print("[CookieExtractor] 유효한 인증 쿠키를 찾을 수 없습니다.")
    return False


def check_chrome_installation() -> bool:
    """
    Chrome 브라우저 설치 여부 확인

    Returns:
        True if installed
    """
    if os.name == 'nt':
        chrome_paths = [
            Path(os.environ.get('PROGRAMFILES', '')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
            Path(os.environ.get('PROGRAMFILES(X86)', '')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
        ]
        return any(p.exists() for p in chrome_paths)

    elif os.name == 'posix':
        import subprocess
        try:
            result = subprocess.run(['which', 'google-chrome'], capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False

    return False


# 테스트용
if __name__ == "__main__":
    print("=" * 60)
    print("Chrome 쿠키 추출 테스트")
    print("=" * 60)

    if not CRYPTO_AVAILABLE:
        print("\n필요 패키지 설치:")
        print("  pip install pywin32 pycryptodome")
        exit(1)

    cookies = extract_imagefx_cookies_from_chrome()

    if cookies:
        print("\n추출된 쿠키:")
        for name, value in cookies.items():
            print(f"  {name}: {value[:30]}...")

        print(f"\n유효성 검사: {'통과' if validate_imagefx_cookies(cookies) else '실패'}")

        print("\nHeader String 형식:")
        header = cookies_to_header_string(cookies)
        print(f"  {header[:100]}...")
    else:
        print("\n쿠키 추출 실패")
