# -*- coding: utf-8 -*-
"""
디바이스 관리 모듈

GPU/CPU 자동 감지, 호환성 체크, 자동 폴백 지원
RTX 5070 (sm_120) 등 최신 GPU 호환성 문제 자동 처리
"""

import os
import warnings
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from enum import Enum

# 경고 필터링
warnings.filterwarnings("ignore", message=".*sm_120.*")
warnings.filterwarnings("ignore", message=".*CUDA.*")
warnings.filterwarnings("ignore", message=".*not compatible.*")


class DeviceMode(Enum):
    """디바이스 모드"""
    AUTO = "auto"       # 자동 감지 (권장)
    GPU = "gpu"         # GPU 강제
    CPU = "cpu"         # CPU 강제


@dataclass
class GPUInfo:
    """GPU 정보"""
    available: bool
    name: str
    compute_capability: str
    memory_gb: float
    pytorch_compatible: bool
    cuda_version: str = "N/A"
    error_message: Optional[str] = None


@dataclass
class DeviceResult:
    """디바이스 선택 결과"""
    device: str                    # "cuda" 또는 "cpu"
    device_name: str               # 실제 디바이스 이름
    gpu_info: Optional[GPUInfo]    # GPU 정보 (있는 경우)
    fallback_used: bool            # 폴백 사용 여부
    message: str                   # 상태 메시지


class DeviceManager:
    """디바이스 관리자"""

    # PyTorch가 지원하는 CUDA compute capability (현재 버전 기준)
    SUPPORTED_COMPUTE_CAPABILITIES = [
        "5.0", "5.2",           # Maxwell
        "6.0", "6.1",           # Pascal
        "7.0", "7.5",           # Volta, Turing
        "8.0", "8.6", "8.9",    # Ampere
        "9.0",                  # Ada Lovelace (RTX 40xx)
        # sm_120 (Blackwell/RTX 50xx)는 아직 미지원
    ]

    def __init__(self):
        self._gpu_info: Optional[GPUInfo] = None
        self._checked = False

    def check_gpu(self, force_recheck: bool = False) -> GPUInfo:
        """
        GPU 상태 확인

        Args:
            force_recheck: 강제 재확인

        Returns:
            GPUInfo
        """
        if self._checked and not force_recheck:
            return self._gpu_info

        try:
            import torch

            if not torch.cuda.is_available():
                self._gpu_info = GPUInfo(
                    available=False,
                    name="N/A",
                    compute_capability="N/A",
                    memory_gb=0,
                    pytorch_compatible=False,
                    cuda_version="N/A",
                    error_message="CUDA를 사용할 수 없습니다"
                )
                self._checked = True
                return self._gpu_info

            # GPU 정보 수집
            gpu_name = torch.cuda.get_device_name(0)

            # Compute capability 확인
            major, minor = torch.cuda.get_device_capability(0)
            compute_cap = f"{major}.{minor}"

            # 메모리
            memory_bytes = torch.cuda.get_device_properties(0).total_memory
            memory_gb = memory_bytes / (1024 ** 3)

            # CUDA 버전
            cuda_version = torch.version.cuda or "Unknown"

            # PyTorch 호환성 확인
            is_compatible = self._check_pytorch_compatibility(compute_cap)

            # 실제 테스트 연산
            test_result, test_error = self._test_gpu_operation()

            if not test_result:
                is_compatible = False
                error_msg = test_error
            else:
                error_msg = None if is_compatible else f"Compute capability {compute_cap}는 현재 PyTorch에서 지원하지 않습니다. PyTorch 업그레이드가 필요합니다."

            self._gpu_info = GPUInfo(
                available=True,
                name=gpu_name,
                compute_capability=compute_cap,
                memory_gb=round(memory_gb, 1),
                pytorch_compatible=is_compatible and test_result,
                cuda_version=cuda_version,
                error_message=error_msg
            )

        except Exception as e:
            self._gpu_info = GPUInfo(
                available=False,
                name="N/A",
                compute_capability="N/A",
                memory_gb=0,
                pytorch_compatible=False,
                cuda_version="N/A",
                error_message=str(e)
            )

        self._checked = True
        return self._gpu_info

    def _check_pytorch_compatibility(self, compute_cap: str) -> bool:
        """PyTorch 호환성 확인"""
        major = compute_cap.split(".")[0]

        # sm_120 (12.0)은 현재 미지원
        if int(major) >= 12:
            return False

        # 지원 목록 확인
        for supported in self.SUPPORTED_COMPUTE_CAPABILITIES:
            if compute_cap.startswith(supported.split(".")[0]):
                return True

        return False

    def _test_gpu_operation(self) -> Tuple[bool, Optional[str]]:
        """실제 GPU 연산 테스트"""
        try:
            import torch

            # 간단한 텐서 연산 테스트
            x = torch.randn(10, 10).cuda()
            y = torch.randn(10, 10).cuda()
            z = torch.matmul(x, y)
            _ = z.cpu()  # 결과를 CPU로 가져오기

            # 메모리 정리
            del x, y, z
            torch.cuda.empty_cache()

            return True, None

        except RuntimeError as e:
            error_msg = str(e)
            if "no kernel image" in error_msg:
                return False, "GPU 커널이 이 GPU 아키텍처를 지원하지 않습니다"
            elif "out of memory" in error_msg:
                return False, "GPU 메모리 부족"
            else:
                return False, error_msg
        except Exception as e:
            return False, str(e)

    def select_device(self, mode: DeviceMode = DeviceMode.AUTO) -> DeviceResult:
        """
        디바이스 선택

        Args:
            mode: DeviceMode.AUTO, DeviceMode.GPU, DeviceMode.CPU

        Returns:
            DeviceResult
        """
        gpu_info = self.check_gpu()

        # CPU 강제 모드
        if mode == DeviceMode.CPU:
            return DeviceResult(
                device="cpu",
                device_name="CPU",
                gpu_info=gpu_info,
                fallback_used=False,
                message="CPU 모드로 실행합니다"
            )

        # GPU 강제 모드
        if mode == DeviceMode.GPU:
            if not gpu_info.available:
                return DeviceResult(
                    device="cpu",
                    device_name="CPU (GPU 없음)",
                    gpu_info=gpu_info,
                    fallback_used=True,
                    message=f"GPU를 사용할 수 없습니다. CPU로 폴백합니다. ({gpu_info.error_message})"
                )

            if not gpu_info.pytorch_compatible:
                return DeviceResult(
                    device="cpu",
                    device_name="CPU (GPU 호환 불가)",
                    gpu_info=gpu_info,
                    fallback_used=True,
                    message=f"{gpu_info.name}은(는) 현재 PyTorch와 호환되지 않습니다. CPU로 폴백합니다."
                )

            return DeviceResult(
                device="cuda",
                device_name=gpu_info.name,
                gpu_info=gpu_info,
                fallback_used=False,
                message=f"GPU 모드: {gpu_info.name}"
            )

        # AUTO 모드 (권장)
        if gpu_info.available and gpu_info.pytorch_compatible:
            return DeviceResult(
                device="cuda",
                device_name=gpu_info.name,
                gpu_info=gpu_info,
                fallback_used=False,
                message=f"GPU 자동 감지: {gpu_info.name} (compute {gpu_info.compute_capability})"
            )
        else:
            reason = gpu_info.error_message or "GPU 호환성 문제"
            return DeviceResult(
                device="cpu",
                device_name="CPU",
                gpu_info=gpu_info,
                fallback_used=gpu_info.available,  # GPU는 있지만 호환 안 되는 경우
                message=f"CPU 모드로 실행합니다 ({reason})"
            )

    def get_device_for_whisper(self, mode: DeviceMode = DeviceMode.AUTO) -> Tuple[str, str]:
        """
        Whisper용 디바이스 선택

        Returns:
            (device, message)
        """
        result = self.select_device(mode)
        return result.device, result.message

    def get_status_display(self) -> Dict:
        """UI 표시용 상태 정보"""
        gpu_info = self.check_gpu()

        # RTX 50xx 감지 (업그레이드 필요 여부)
        needs_upgrade = (
            gpu_info.available and
            not gpu_info.pytorch_compatible and
            gpu_info.compute_capability.startswith("12")
        )

        return {
            "gpu_available": gpu_info.available,
            "gpu_name": gpu_info.name,
            "gpu_memory": f"{gpu_info.memory_gb} GB" if gpu_info.available else "N/A",
            "compute_capability": gpu_info.compute_capability,
            "cuda_version": gpu_info.cuda_version,
            "pytorch_compatible": gpu_info.pytorch_compatible,
            "recommended_mode": "GPU" if gpu_info.pytorch_compatible else "CPU",
            "warning": gpu_info.error_message,
            "needs_upgrade": needs_upgrade
        }

    def get_upgrade_instructions(self) -> str:
        """PyTorch 업그레이드 안내 (RTX 50xx용)"""
        gpu_info = self.check_gpu()

        if gpu_info.pytorch_compatible:
            return ""

        if not gpu_info.available:
            return ""

        # RTX 50xx 감지
        if gpu_info.compute_capability.startswith("12"):
            return f"""### RTX 50xx GPU PyTorch 업그레이드 안내

**현재 상태:**
- GPU: {gpu_info.name}
- Compute Capability: {gpu_info.compute_capability} (Blackwell)
- PyTorch CUDA: {gpu_info.cuda_version}

**문제:** 현재 PyTorch가 sm_120 (RTX 50xx)을 지원하지 않습니다.

**해결 방법 1: CUDA 13.0 설치 (권장)**
```bash
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
pip install --force-reinstall stable-ts
```

**해결 방법 2: Nightly 빌드**
```bash
pip uninstall torch torchvision torchaudio -y
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu124
pip install --force-reinstall stable-ts
```

**해결 방법 3: 업그레이드 스크립트**
```bash
python scripts/upgrade_pytorch.py
```

업그레이드 후 앱을 재시작하세요.
"""

        return f"GPU 호환성 문제: {gpu_info.error_message}"


# 전역 싱글톤 인스턴스
_device_manager: Optional[DeviceManager] = None


def get_device_manager() -> DeviceManager:
    """디바이스 매니저 싱글톤"""
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager


def select_device(mode: str = "auto") -> DeviceResult:
    """
    디바이스 선택 헬퍼 함수

    Args:
        mode: "auto", "gpu", "cpu"

    Returns:
        DeviceResult
    """
    mode_map = {
        "auto": DeviceMode.AUTO,
        "gpu": DeviceMode.GPU,
        "cuda": DeviceMode.GPU,
        "cpu": DeviceMode.CPU
    }
    device_mode = mode_map.get(mode.lower(), DeviceMode.AUTO)
    return get_device_manager().select_device(device_mode)


def get_gpu_status() -> Dict:
    """GPU 상태 조회 헬퍼"""
    return get_device_manager().get_status_display()


def get_upgrade_instructions() -> str:
    """PyTorch 업그레이드 안내 헬퍼"""
    return get_device_manager().get_upgrade_instructions()
