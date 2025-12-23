# -*- coding: utf-8 -*-
"""
렌더러 환경 점검 스크립트

인포그래픽 썸네일/동영상 생성에 필요한 의존성 확인
"""

import sys
import subprocess


def check_all():
    """전체 환경 점검"""
    print("=" * 60)
    print("인포그래픽 렌더러 환경 점검")
    print("=" * 60)

    # 1. Python 버전
    print(f"\n[Python 버전]")
    print(f"  {sys.version}")

    issues = []

    # 2. Selenium
    print("\n[Selenium 확인]")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        print("  ✅ Selenium 패키지 설치됨")

        try:
            from webdriver_manager.chrome import ChromeDriverManager
            print("  ✅ webdriver-manager 설치됨")

            # 드라이버 테스트
            print("  🔍 Chrome WebDriver 테스트 중...")
            options = Options()
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.quit()
            print("  ✅ Chrome WebDriver 정상 작동")

        except ImportError:
            print("  ❌ webdriver-manager 미설치")
            issues.append("pip install webdriver-manager")
        except Exception as e:
            print(f"  ❌ WebDriver 오류: {e}")
            issues.append("Chrome 브라우저 설치 필요")

    except ImportError as e:
        print(f"  ❌ Selenium 미설치: {e}")
        issues.append("pip install selenium webdriver-manager")

    # 3. Pillow
    print("\n[Pillow 확인]")
    try:
        from PIL import Image
        print("  ✅ Pillow 설치됨")
    except ImportError:
        print("  ❌ Pillow 미설치")
        issues.append("pip install pillow")

    # 4. FFmpeg
    print("\n[FFmpeg 확인]")
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"  ✅ FFmpeg 설치됨")
            print(f"     {version_line}")
        else:
            print("  ❌ FFmpeg 실행 오류")
            issues.append("FFmpeg 설치 필요")
    except FileNotFoundError:
        print("  ❌ FFmpeg 미설치")
        issues.append("choco install ffmpeg (Windows 관리자 권한)")
    except subprocess.TimeoutExpired:
        print("  ❌ FFmpeg 실행 타임아웃")
        issues.append("FFmpeg 재설치 필요")
    except Exception as e:
        print(f"  ❌ FFmpeg 오류: {e}")
        issues.append("FFmpeg 설치 필요")

    # 5. BeautifulSoup (파서용)
    print("\n[BeautifulSoup 확인]")
    try:
        from bs4 import BeautifulSoup
        print("  ✅ BeautifulSoup 설치됨")
    except ImportError:
        print("  ⚠️ BeautifulSoup 미설치 (선택사항)")
        print("     HTML 요소 파싱에 필요")

    # 6. 종합 결과
    print("\n" + "=" * 60)

    if not issues:
        print("✅ 모든 의존성이 설치되어 있습니다!")
        print("   인포그래픽 썸네일/동영상 생성을 사용할 수 있습니다.")
    else:
        print("⚠️ 다음 항목을 설치해야 합니다:")
        print()
        for issue in issues:
            print(f"   {issue}")

    print("\n" + "=" * 60)
    print("설치 명령어 종합:")
    print("=" * 60)
    print("""
# Python 패키지 설치
pip install selenium webdriver-manager pillow beautifulsoup4

# Windows (관리자 권한 PowerShell):
choco install ffmpeg

# 또는 FFmpeg 수동 설치:
# https://ffmpeg.org/download.html 에서 다운로드 후 PATH에 추가
""")

    return len(issues) == 0


def quick_test():
    """빠른 테스트"""
    print("=" * 60)
    print("빠른 렌더러 테스트")
    print("=" * 60)

    try:
        from utils.infographic_thumbnail import check_selenium_available, get_available_renderer
        from utils.infographic_video_recorder import check_video_recorder_available

        print("\n[썸네일 생성기]")
        selenium_ok, selenium_msg = check_selenium_available()
        print(f"  Selenium: {'✅' if selenium_ok else '❌'} {selenium_msg}")

        renderer, msg = get_available_renderer()
        print(f"  사용 가능한 렌더러: {renderer or '없음'}")

        print("\n[동영상 녹화기]")
        video_ok, video_msg = check_video_recorder_available()
        print(f"  상태: {'✅' if video_ok else '❌'}")
        if not video_ok:
            for line in video_msg.split('\n'):
                print(f"    - {line}")

        return selenium_ok and video_ok

    except ImportError as e:
        print(f"\n❌ 모듈 import 오류: {e}")
        print("   먼저 check_all()을 실행하여 의존성을 확인하세요.")
        return False


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='렌더러 환경 점검')
    parser.add_argument('--quick', '-q', action='store_true', help='빠른 테스트만 실행')
    args = parser.parse_args()

    if args.quick:
        quick_test()
    else:
        check_all()
