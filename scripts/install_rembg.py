# -*- coding: utf-8 -*-
"""
rembg 설치 스크립트

Windows에서 rembg 설치 시 발생할 수 있는 문제 해결
"""

import subprocess
import sys
import os


def install_rembg():
    """rembg 설치"""
    print("=" * 50)
    print("rembg 배경 제거 라이브러리 설치")
    print("=" * 50)

    # Python 버전 확인
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"Python 버전: {py_version}")

    # pip 업그레이드
    print("\npip 업그레이드 중...")
    subprocess.run([
        sys.executable, "-m", "pip", "install", "--upgrade", "pip"
    ], check=False)

    # rembg 설치 시도
    print("\nrembg 설치 중... (약 170MB 모델 다운로드 포함)")

    # 방법 1: 기본 설치
    result = subprocess.run([
        sys.executable, "-m", "pip", "install",
        "rembg"
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"기본 설치 실패: {result.stderr[:200]}")

        # 방법 2: --break-system-packages 옵션
        print("\n대체 방법으로 설치 시도...")
        result = subprocess.run([
            sys.executable, "-m", "pip", "install",
            "rembg", "--break-system-packages"
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"설치 실패: {result.stderr[:200]}")
            return False

    # 설치 확인
    print("\n설치 확인 중...")
    try:
        import rembg
        version = getattr(rembg, '__version__', 'unknown')
        print(f"rembg 설치 완료! 버전: {version}")
        return True
    except ImportError as e:
        print(f"설치 실패: {e}")
        return False


def install_dependencies():
    """rembg 의존성 설치"""
    deps = [
        "numpy",
        "pillow",
        "onnxruntime",  # CPU 버전
        "pooch",
        "scipy",
    ]

    print("\n의존성 설치 중...")
    for dep in deps:
        print(f"  - {dep}")
        subprocess.run([
            sys.executable, "-m", "pip", "install", dep
        ], capture_output=True)


if __name__ == "__main__":
    # 의존성 먼저 설치
    install_dependencies()

    # rembg 설치
    success = install_rembg()

    if success:
        print("\n" + "=" * 50)
        print("설치 완료! Streamlit 앱을 재시작하세요.")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("설치 실패. 수동 설치를 시도하세요:")
        print("   pip install rembg")
        print("=" * 50)
