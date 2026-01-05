# -*- coding: utf-8 -*-
"""
RTX 5070 GPU 지원을 위한 PyTorch 업그레이드 스크립트

사용법:
    python scripts/upgrade_pytorch.py
"""

import subprocess
import sys
import os
import re


def print_header(title):
    """헤더 출력"""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def check_current_pytorch():
    """현재 PyTorch 상태 확인"""
    print_header("현재 PyTorch 환경 확인")

    try:
        import torch
        print(f"PyTorch 버전: {torch.__version__}")
        print(f"CUDA 사용 가능: {torch.cuda.is_available()}")

        if torch.cuda.is_available():
            cuda_version = torch.version.cuda or "Unknown"
            print(f"CUDA 버전: {cuda_version}")
            print(f"GPU: {torch.cuda.get_device_name(0)}")
            major, minor = torch.cuda.get_device_capability(0)
            print(f"Compute Capability: {major}.{minor}")

            # RTX 50xx 감지 (sm_120)
            if major >= 12:
                print("\n[!] RTX 50xx 시리즈 (Blackwell) 감지됨!")
                print("현재 PyTorch가 sm_120을 지원하는지 테스트합니다...")

                try:
                    x = torch.randn(10, 10).cuda()
                    y = torch.matmul(x, x)
                    _ = y.cpu()
                    del x, y
                    torch.cuda.empty_cache()
                    print("[OK] GPU 연산 테스트 성공!")
                    return True, "working"
                except RuntimeError as e:
                    print(f"[FAIL] GPU 연산 실패: {e}")
                    return False, "rtx50xx_incompatible"
            else:
                # 일반 GPU 테스트
                try:
                    x = torch.randn(10, 10).cuda()
                    y = torch.matmul(x, x)
                    _ = y.cpu()
                    del x, y
                    torch.cuda.empty_cache()
                    print("[OK] GPU 연산 테스트 성공!")
                    return True, "working"
                except RuntimeError as e:
                    print(f"[FAIL] GPU 연산 실패: {e}")
                    return False, "gpu_error"
        else:
            print("CUDA를 사용할 수 없습니다.")
            return False, "no_cuda"

    except ImportError:
        print("PyTorch가 설치되지 않았습니다.")
        return False, "no_pytorch"


def get_system_cuda_version():
    """시스템 CUDA 버전 확인"""
    try:
        result = subprocess.run(
            ["nvcc", "--version"],
            capture_output=True,
            text=True,
            shell=True
        )
        if result.returncode == 0:
            match = re.search(r"release (\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass

    # nvidia-smi로 시도
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            shell=True
        )
        if result.returncode == 0:
            match = re.search(r"CUDA Version: (\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass

    return None


def run_pip_command(args, description=""):
    """pip 명령 실행"""
    if description:
        print(f"\n{description}...")

    cmd = [sys.executable, "-m", "pip"] + args
    print(f"  실행: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def upgrade_pytorch(choice):
    """PyTorch 업그레이드"""
    print_header("PyTorch 업그레이드")

    # 기존 제거
    print("\n[1/3] 기존 PyTorch 제거 중...")
    run_pip_command(["uninstall", "torch", "torchvision", "torchaudio", "-y"])

    # 새 버전 설치
    print("\n[2/3] 새 PyTorch 설치 중...")

    install_commands = {
        "1": {
            "name": "CUDA 13.0 (RTX 50xx 공식 지원)",
            "args": ["install", "torch", "torchvision", "torchaudio",
                    "--index-url", "https://download.pytorch.org/whl/cu130"]
        },
        "2": {
            "name": "CUDA 12.4 Nightly (최신 개발 버전)",
            "args": ["install", "--pre", "torch", "torchvision", "torchaudio",
                    "--index-url", "https://download.pytorch.org/whl/nightly/cu124"]
        },
        "3": {
            "name": "CUDA 12.4 Stable (안정 버전)",
            "args": ["install", "torch", "torchvision", "torchaudio",
                    "--index-url", "https://download.pytorch.org/whl/cu124"]
        },
        "4": {
            "name": "CUDA 12.1 Stable",
            "args": ["install", "torch", "torchvision", "torchaudio",
                    "--index-url", "https://download.pytorch.org/whl/cu121"]
        },
        "5": {
            "name": "CPU 전용",
            "args": ["install", "torch", "torchvision", "torchaudio",
                    "--index-url", "https://download.pytorch.org/whl/cpu"]
        }
    }

    if choice not in install_commands:
        print("[ERROR] 잘못된 선택입니다.")
        return False

    cmd_info = install_commands[choice]
    print(f"  선택: {cmd_info['name']}")

    success = run_pip_command(cmd_info["args"])

    if not success:
        print(f"\n[WARN] {cmd_info['name']} 설치 실패!")

        # 폴백 시도
        if choice == "1":
            print("cu130이 없을 수 있습니다. Nightly 버전으로 시도합니다...")
            success = run_pip_command(install_commands["2"]["args"])

        if not success:
            print("[ERROR] 설치에 실패했습니다.")
            return False

    # stable-ts 재설치
    print("\n[3/3] stable-ts 재설치 중...")
    run_pip_command(["install", "--force-reinstall", "stable-ts"])

    return True


def test_installation():
    """설치 테스트"""
    print_header("설치 테스트")

    test_code = '''
import sys
try:
    import torch
    print(f"PyTorch 버전: {torch.__version__}")
    print(f"CUDA 사용 가능: {torch.cuda.is_available()}")

    if torch.cuda.is_available():
        print(f"CUDA 버전: {torch.version.cuda}")
        print(f"GPU: {torch.cuda.get_device_name(0)}")

        # GPU 테스트
        x = torch.randn(100, 100).cuda()
        y = torch.matmul(x, x)
        _ = y.cpu()
        print("[OK] GPU 연산 테스트 성공!")
        sys.exit(0)
    else:
        print("[INFO] CPU 모드로 설치됨")
        sys.exit(0)
except Exception as e:
    print(f"[ERROR] 테스트 실패: {e}")
    sys.exit(1)
'''

    result = subprocess.run([sys.executable, "-c", test_code])
    return result.returncode == 0


def main():
    print_header("RTX 5070 GPU 지원 PyTorch 업그레이드 도구")

    # 현재 상태 확인
    gpu_works, status = check_current_pytorch()

    if gpu_works:
        print("\n[OK] 현재 환경에서 GPU가 정상 작동합니다!")
        print("업그레이드가 필요하지 않습니다.")
        return

    # 시스템 CUDA 버전 확인
    system_cuda = get_system_cuda_version()
    if system_cuda:
        print(f"\n시스템 CUDA 버전: {system_cuda}")

    # 업그레이드 옵션 제시
    print("\n" + "-" * 40)
    print("PyTorch 업그레이드 옵션:")
    print("-" * 40)
    print("1. CUDA 13.0 (RTX 50xx 공식 지원) [권장]")
    print("2. CUDA 12.4 Nightly (최신 개발 버전)")
    print("3. CUDA 12.4 Stable (안정 버전)")
    print("4. CUDA 12.1 Stable")
    print("5. CPU 전용 (GPU 사용 안 함)")
    print("0. 취소")
    print("-" * 40)

    if status == "rtx50xx_incompatible":
        print("\n[!] RTX 50xx GPU가 감지되었습니다.")
        print("    옵션 1 (CUDA 13.0) 또는 옵션 2 (Nightly)를 권장합니다.")

    choice = input("\n선택 (0-5): ").strip()

    if choice == "0":
        print("취소됨.")
        return

    if choice not in ["1", "2", "3", "4", "5"]:
        print("[ERROR] 잘못된 선택입니다.")
        return

    # 확인
    print(f"\n선택: {choice}")
    confirm = input("업그레이드를 진행하시겠습니까? (y/n): ").strip().lower()

    if confirm != 'y':
        print("취소됨.")
        return

    # 업그레이드 실행
    if upgrade_pytorch(choice):
        print_header("업그레이드 완료")

        # 테스트
        if test_installation():
            print("\n[OK] 모든 업그레이드가 완료되었습니다!")
            print("\n다음 단계:")
            print("  1. 앱을 재시작하세요: streamlit run app.py")
            print("  2. GPU 상태를 확인하세요")
        else:
            print("\n[WARN] 테스트에 실패했습니다.")
            print("수동으로 확인해 주세요:")
            print("  python -c \"import torch; print(torch.cuda.is_available())\"")
    else:
        print("\n[ERROR] 업그레이드에 실패했습니다.")


if __name__ == "__main__":
    main()
