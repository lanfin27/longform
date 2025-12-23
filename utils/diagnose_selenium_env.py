# -*- coding: utf-8 -*-
"""
Selenium 환경 진단 스크립트
WinError 193 문제 해결을 위한 완전한 진단
"""

import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def diagnose():
    print_section("시스템 정보")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Python: {sys.version}")
    print(f"Python Arch: {platform.architecture()[0]}")

    print_section("Chrome 브라우저 확인")

    # Chrome 설치 경로 확인
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]

    chrome_found = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_found = path
            print(f"✅ Chrome 발견: {path}")
            break

    if not chrome_found:
        print("❌ Chrome 브라우저를 찾을 수 없습니다!")
        print("   설치 필요: https://www.google.com/chrome/")
        return False

    # Chrome 버전 확인
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        version, _ = winreg.QueryValueEx(key, "version")
        print(f"✅ Chrome 버전: {version}")
        chrome_major = version.split('.')[0]
        print(f"   Major 버전: {chrome_major}")
    except Exception as e:
        print(f"⚠️ Chrome 버전 확인 실패: {e}")
        try:
            result = subprocess.run(
                [chrome_found, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            version_str = result.stdout.strip()
            print(f"✅ Chrome 버전 (명령줄): {version_str}")
        except Exception as e2:
            print(f"⚠️ 명령줄 버전 확인도 실패: {e2}")

    print_section("webdriver-manager 캐시 확인")

    # webdriver-manager 캐시 경로
    wdm_cache_paths = [
        os.path.expanduser(r"~\.wdm"),
        os.path.expanduser(r"~\.cache\selenium"),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'selenium'),
    ]

    for cache_path in wdm_cache_paths:
        if os.path.exists(cache_path):
            print(f"\n📁 캐시 발견: {cache_path}")
            try:
                total_size = 0
                file_count = 0
                for root, dirs, files in os.walk(cache_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
                        file_count += 1
                        if file.endswith('.exe'):
                            print(f"   📦 {file}: {os.path.getsize(file_path):,} bytes")
                            # PE 헤더 확인
                            with open(file_path, 'rb') as f:
                                header = f.read(2)
                                if header == b'MZ':
                                    print(f"      ✅ 유효한 PE 헤더")
                                else:
                                    print(f"      ❌ 잘못된 헤더: {header}")
                print(f"   총 {file_count}개 파일, {total_size:,} bytes")
            except Exception as e:
                print(f"   캐시 탐색 오류: {e}")

    print_section("Selenium 패키지 확인")

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        import selenium
        print(f"✅ Selenium 버전: {selenium.__version__}")
    except ImportError as e:
        print(f"❌ Selenium 미설치: {e}")
        print("   pip install selenium")
        return False

    try:
        from webdriver_manager.chrome import ChromeDriverManager
        import webdriver_manager
        print(f"✅ webdriver-manager 버전: {webdriver_manager.__version__}")
    except ImportError as e:
        print(f"❌ webdriver-manager 미설치: {e}")
        print("   pip install webdriver-manager")
        return False

    print_section("ChromeDriver 경로 확인")

    try:
        driver_path = ChromeDriverManager().install()
        print(f"✅ ChromeDriverManager 반환 경로:")
        print(f"   {driver_path}")

        if os.path.exists(driver_path):
            size = os.path.getsize(driver_path)
            print(f"✅ 파일 존재: {size:,} bytes")

            if driver_path.endswith('.exe'):
                print("✅ .exe 확장자 확인")
            else:
                print(f"⚠️ 확장자가 .exe가 아님")
                # 폴더 내 exe 찾기
                parent_dir = os.path.dirname(driver_path)
                for root, dirs, files in os.walk(parent_dir):
                    for file in files:
                        if file == "chromedriver.exe":
                            print(f"   📍 발견: {os.path.join(root, file)}")

            # PE 헤더 확인
            with open(driver_path, 'rb') as f:
                header = f.read(2)
                if header == b'MZ':
                    print("✅ 유효한 Windows 실행 파일 (MZ 헤더)")
                else:
                    print(f"❌ 유효하지 않은 실행 파일 헤더: {header}")
                    print("   파일이 손상되었거나 잘못된 형식입니다")
                    print("   해결: 캐시 삭제 후 재시도")
                    return False
        else:
            print(f"❌ 파일이 존재하지 않음: {driver_path}")
            return False

    except Exception as e:
        print(f"❌ ChromeDriverManager 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

    print_section("WebDriver 초기화 테스트")

    try:
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.binary_location = chrome_found

        service = Service(driver_path)

        print("🔄 WebDriver 초기화 시도 중...")
        driver = webdriver.Chrome(service=service, options=options)
        print("✅ WebDriver 초기화 성공!")

        driver.get("data:text/html,<h1>Test</h1>")
        print("✅ 테스트 페이지 로드 성공!")

        driver.quit()
        print("✅ WebDriver 종료 성공!")

        return True

    except OSError as e:
        if hasattr(e, 'winerror') and e.winerror == 193:
            print(f"❌ WinError 193 발생!")
            print(f"   원인: ChromeDriver가 유효한 Win32 응용 프로그램이 아님")
            print(f"   해결책:")
            print(f"   1. python utils/diagnose_selenium_env.py --clear-cache")
            print(f"   2. python utils/install_chromedriver.py")
        else:
            print(f"❌ OSError: {e}")
        return False
    except Exception as e:
        print(f"❌ WebDriver 초기화 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def clear_cache():
    """webdriver-manager 캐시 삭제"""
    print_section("캐시 삭제")

    cache_paths = [
        os.path.expanduser(r"~\.wdm"),
        os.path.expanduser(r"~\.cache\selenium"),
    ]

    for cache_path in cache_paths:
        if os.path.exists(cache_path):
            try:
                shutil.rmtree(cache_path)
                print(f"✅ 삭제됨: {cache_path}")
            except Exception as e:
                print(f"❌ 삭제 실패 {cache_path}: {e}")
        else:
            print(f"ℹ️ 존재하지 않음: {cache_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Selenium 환경 진단')
    parser.add_argument('--clear-cache', action='store_true', help='캐시 삭제')
    args = parser.parse_args()

    if args.clear_cache:
        clear_cache()

    success = diagnose()

    print_section("결과")
    if success:
        print("✅ 모든 진단 통과! Selenium이 정상 작동합니다.")
    else:
        print("❌ 문제가 발견되었습니다. 위의 오류를 확인하세요.")
        print("\n권장 조치:")
        print("1. python utils/diagnose_selenium_env.py --clear-cache")
        print("2. python utils/install_chromedriver.py")
        print("3. 진단 다시 실행")

    sys.exit(0 if success else 1)
