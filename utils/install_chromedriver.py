# -*- coding: utf-8 -*-
"""
ChromeDriver 수동 설치 스크립트
WinError 193 문제 완전 해결을 위한 수동 설치
"""

import os
import sys
import zipfile
import urllib.request
import json
import shutil
from pathlib import Path


def get_chrome_version():
    """Chrome 버전 확인"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        version, _ = winreg.QueryValueEx(key, "version")
        return version
    except Exception:
        return None


def get_chromedriver_download_url(chrome_version: str) -> str:
    """Chrome 버전에 맞는 ChromeDriver 다운로드 URL 가져오기"""
    major_version = chrome_version.split('.')[0]

    # Chrome 115+ 는 새로운 JSON API 사용
    if int(major_version) >= 115:
        json_url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"

        print(f"Chrome {major_version}+ 감지, 새 API 사용...")

        try:
            with urllib.request.urlopen(json_url, timeout=30) as response:
                data = json.loads(response.read().decode())

            # 해당 major 버전에 맞는 가장 최신 버전 찾기
            matching_versions = [
                v for v in data['versions']
                if v['version'].startswith(f"{major_version}.")
            ]

            if matching_versions:
                latest = matching_versions[-1]

                # win64 드라이버 URL 찾기
                for download in latest.get('downloads', {}).get('chromedriver', []):
                    if download['platform'] == 'win64':
                        return download['url']

                # win64 없으면 win32
                for download in latest.get('downloads', {}).get('chromedriver', []):
                    if download['platform'] == 'win32':
                        return download['url']

        except Exception as e:
            print(f"새 API 오류: {e}")

    # 구버전 - Chrome 114 이하
    base_url = "https://chromedriver.storage.googleapis.com"

    try:
        latest_url = f"{base_url}/LATEST_RELEASE_{major_version}"
        with urllib.request.urlopen(latest_url, timeout=10) as response:
            driver_version = response.read().decode().strip()

        return f"{base_url}/{driver_version}/chromedriver_win32.zip"
    except Exception as e:
        print(f"구 API 오류: {e}")

    raise Exception(f"Chrome {chrome_version}에 맞는 ChromeDriver를 찾을 수 없습니다")


def download_and_extract(url: str, target_dir: str) -> str:
    """ChromeDriver 다운로드 및 추출"""
    print(f"다운로드 중: {url}")

    os.makedirs(target_dir, exist_ok=True)
    zip_path = os.path.join(target_dir, "chromedriver.zip")

    # 다운로드
    urllib.request.urlretrieve(url, zip_path)
    print(f"다운로드 완료: {os.path.getsize(zip_path):,} bytes")

    # 압축 해제
    print("압축 해제 중...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(target_dir)

    # zip 파일 삭제
    os.remove(zip_path)

    # chromedriver.exe 찾기
    for root, dirs, files in os.walk(target_dir):
        for file in files:
            if file == 'chromedriver.exe':
                exe_path = os.path.join(root, file)
                # 타겟 디렉토리 루트로 이동
                final_path = os.path.join(target_dir, 'chromedriver.exe')
                if exe_path != final_path:
                    shutil.move(exe_path, final_path)

                # 빈 하위 폴더 삭제
                for subdir in os.listdir(target_dir):
                    subdir_path = os.path.join(target_dir, subdir)
                    if os.path.isdir(subdir_path):
                        try:
                            shutil.rmtree(subdir_path)
                        except:
                            pass

                return final_path

    raise Exception("chromedriver.exe를 찾을 수 없습니다")


def verify_chromedriver(exe_path: str) -> bool:
    """ChromeDriver 실행 파일 검증"""
    if not os.path.exists(exe_path):
        print(f"❌ 파일 없음: {exe_path}")
        return False

    # 파일 크기 확인
    size = os.path.getsize(exe_path)
    if size < 1024:
        print(f"❌ 파일 크기 너무 작음: {size} bytes")
        return False

    # PE 헤더 확인
    with open(exe_path, 'rb') as f:
        header = f.read(2)
        if header != b'MZ':
            print(f"❌ 유효하지 않은 PE 헤더: {header}")
            return False

    print(f"✅ 유효한 실행 파일: {exe_path} ({size:,} bytes)")

    # 버전 확인
    import subprocess
    try:
        result = subprocess.run(
            [exe_path, '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        print(f"✅ ChromeDriver 버전: {result.stdout.strip()}")
        return True
    except Exception as e:
        print(f"⚠️ 버전 확인 실패 (하지만 파일은 유효): {e}")
        return True


def main():
    print("=" * 60)
    print("  ChromeDriver 수동 설치 스크립트")
    print("=" * 60)

    # Chrome 버전 확인
    chrome_version = get_chrome_version()
    if not chrome_version:
        print("❌ Chrome 브라우저를 찾을 수 없습니다")
        print("   https://www.google.com/chrome/ 에서 설치하세요")
        return False

    print(f"\n✅ Chrome 버전: {chrome_version}")

    # 프로젝트 drivers 폴더
    project_root = Path(__file__).parent.parent
    drivers_dir = project_root / "drivers"

    print(f"\n설치 경로: {drivers_dir}")

    # 기존 드라이버 삭제
    if drivers_dir.exists():
        print("기존 drivers 폴더 삭제 중...")
        shutil.rmtree(drivers_dir)

    # webdriver-manager 캐시도 삭제
    cache_paths = [
        os.path.expanduser(r"~\.wdm"),
        os.path.expanduser(r"~\.cache\selenium"),
    ]
    for cache_path in cache_paths:
        if os.path.exists(cache_path):
            print(f"캐시 삭제: {cache_path}")
            try:
                shutil.rmtree(cache_path)
            except Exception as e:
                print(f"  ⚠️ 삭제 실패: {e}")

    try:
        # 다운로드 URL 가져오기
        download_url = get_chromedriver_download_url(chrome_version)
        print(f"\n다운로드 URL: {download_url}")

        # 다운로드 및 추출
        exe_path = download_and_extract(download_url, str(drivers_dir))

        # 검증
        if verify_chromedriver(exe_path):
            print(f"\n✅ ChromeDriver 설치 완료!")
            print(f"   경로: {exe_path}")

            # 환경 변수 설정
            os.environ['CHROMEDRIVER_PATH'] = exe_path
            print(f"\n✅ 환경 변수 설정됨: CHROMEDRIVER_PATH={exe_path}")

            return True
        else:
            print("\n❌ ChromeDriver 검증 실패")
            return False

    except Exception as e:
        print(f"\n❌ 설치 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
