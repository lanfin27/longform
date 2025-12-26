"""
Together.ai FLUX 이미지 생성 클라이언트 - 속도 최적화 버전

FLUX 모델을 활용한 고품질 이미지 생성
"""
import base64
import time
from pathlib import Path
from typing import List, Dict, Optional, Callable

from together import Together

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import TOGETHER_API_KEY, IMAGE_MODELS

# 모델별 가격 정보 (USD/장)
MODEL_PRICING = {
    "black-forest-labs/FLUX.2-dev": {"price": 0.0154, "name": "FLUX.2 Dev"},
    "black-forest-labs/FLUX.2-flex": {"price": 0.03, "name": "FLUX.2 Flex"},
    "black-forest-labs/FLUX.2-pro": {"price": 0.03, "name": "FLUX.2 Pro"},
    "black-forest-labs/FLUX.1-schnell": {"price": 0.02, "name": "FLUX.1 Schnell"},
    "black-forest-labs/FLUX.1.1-pro": {"price": 0.04, "name": "FLUX 1.1 Pro"},
    "black-forest-labs/FLUX.1-schnell-Free": {"price": 0.0, "name": "FLUX.1 Schnell Free"},
}


def get_model_price_info(model_id: str) -> dict:
    """모델 가격 정보 반환"""
    return MODEL_PRICING.get(model_id, {
        "price": 0.0,
        "name": model_id.split("/")[-1] if "/" in model_id else model_id
    })


class TogetherImageClient:
    """
    Together.ai FLUX 이미지 생성 클라이언트 - 속도 최적화

    특징:
    - FLUX 모델 (Free, Schnell, Pro) 지원
    - 배치 생성 지원
    - 스마트 rate limit 관리
    - 실시간 로깅
    """

    # FLUX 모델 크기 제한
    MAX_SIZE = 1792
    MIN_SIZE = 64

    # Rate limit: Free 모델은 분당 10개 = 6초 간격
    RATE_LIMIT_DELAY = 6.0

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: Together.ai API 키 (기본: 환경변수에서 로드)
        """
        self.api_key = api_key or TOGETHER_API_KEY
        if not self.api_key:
            raise ValueError("Together.ai API Key가 필요합니다. .env 파일을 확인하세요.")

        self.client = Together(api_key=self.api_key)
        self._last_request_time = 0

    @classmethod
    def get_models(cls) -> List[Dict]:
        """사용 가능한 모델 목록 반환"""
        return IMAGE_MODELS

    def _clamp_size(self, width: int, height: int) -> tuple:
        """크기를 FLUX 제한 범위로 조정"""
        width = max(self.MIN_SIZE, min(width, self.MAX_SIZE))
        height = max(self.MIN_SIZE, min(height, self.MAX_SIZE))
        return width, height

    def _wait_for_rate_limit(self, model: str):
        """Rate limit 대기 (필요한 경우에만)"""
        if "Free" not in model:
            return

        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            wait_time = self.RATE_LIMIT_DELAY - elapsed
            print(f"  [Rate limit] {wait_time:.1f}초 대기 중...")
            time.sleep(wait_time)

    def generate_image(
        self,
        prompt: str,
        model: str = "black-forest-labs/FLUX.2-dev",
        width: int = 1280,
        height: int = 720,
        steps: int = 4,
        seed: Optional[int] = None
    ) -> bytes:
        """
        단일 이미지 생성

        Args:
            prompt: 이미지 프롬프트
            model: 모델 ID
            width: 이미지 너비 (64~1792)
            height: 이미지 높이 (64~1792)
            steps: 생성 단계 (Free 모델은 4 고정)
            seed: 랜덤 시드 (재현성용)

        Returns:
            이미지 바이너리 데이터

        Raises:
            Exception: API 호출 실패 시
        """
        # 크기 조정
        width, height = self._clamp_size(width, height)

        # FLUX.2 모델은 기본 20 steps 권장 (Free 모델 호환 유지)
        if "Free" in model:
            steps = 4
        elif "FLUX.2" in model or "FLUX-2" in model:
            steps = max(steps, 20)  # FLUX.2는 20 steps 권장

        # 모델 정보 조회
        model_info = get_model_price_info(model)

        # 로그: 생성 시작
        print("=" * 60)
        print(f"[이미지 생성] 🚀 시작")
        print(f"[이미지 생성] 📌 API: Together.ai FLUX")
        print(f"[이미지 생성] 📌 모델: {model}")
        print(f"[이미지 생성] 📌 모델명: {model_info['name']}")
        if model_info['price'] > 0:
            print(f"[이미지 생성] 📌 예상 비용: ${model_info['price']:.4f}/장 (~{int(model_info['price'] * 1400)}원)")
        else:
            print(f"[이미지 생성] 📌 예상 비용: 무료")
        print(f"[이미지 생성] 📌 크기: {width}x{height}")
        print(f"[이미지 생성] 📌 프롬프트: {prompt[:80]}..." if len(prompt) > 80 else f"[이미지 생성] 📌 프롬프트: {prompt}")
        print("-" * 60)

        start_time = time.time()

        kwargs = {
            "model": model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "response_format": "b64_json",
            "n": 1
        }

        if seed is not None:
            kwargs["seed"] = seed

        try:
            response = self.client.images.generate(**kwargs)
            self._last_request_time = time.time()

            # b64_json 우선 사용
            if response.data and response.data[0].b64_json:
                image_data = base64.b64decode(response.data[0].b64_json)

                # 로그: 성공
                elapsed = time.time() - start_time
                print("-" * 60)
                print(f"[이미지 생성] ✅ 성공!")
                print(f"[이미지 생성]    ⏱️ 소요: {elapsed:.2f}초")
                print(f"[이미지 생성]    📦 크기: {len(image_data):,} bytes")
                if model_info['price'] > 0:
                    print(f"[이미지 생성]    💰 비용: ${model_info['price']:.4f} (~{int(model_info['price'] * 1400)}원)")
                else:
                    print(f"[이미지 생성]    💰 비용: 무료")
                print("=" * 60)

                return image_data
            else:
                elapsed = time.time() - start_time
                print("-" * 60)
                print(f"[이미지 생성] ❌ 실패!")
                print(f"[이미지 생성]    ⏱️ 소요: {elapsed:.2f}초")
                print(f"[이미지 생성]    🚫 오류: 이미지 데이터를 받지 못했습니다 (b64_json=None)")
                print("=" * 60)
                raise Exception("이미지 데이터를 받지 못했습니다 (b64_json=None)")

        except Exception as e:
            elapsed = time.time() - start_time
            print("-" * 60)
            print(f"[이미지 생성] ❌ 실패!")
            print(f"[이미지 생성]    ⏱️ 소요: {elapsed:.2f}초")
            print(f"[이미지 생성]    📌 모델: {model}")
            print(f"[이미지 생성]    🚫 오류: {str(e)}")
            print("=" * 60)
            raise Exception(f"이미지 생성 실패: {str(e)}")

    def generate_batch(
        self,
        prompts: List[Dict],
        output_dir: str,
        model: str = "black-forest-labs/FLUX.2-dev",
        style_prefix: str = "",
        width: int = 1280,
        height: int = 720,
        steps: int = 4,
        seed: Optional[int] = None,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> List[Dict]:
        """
        배치 이미지 생성 - 속도 최적화

        Args:
            prompts: 프롬프트 딕셔너리 리스트
                [{"filename": "001.png", "prompt": "..."}, ...]
            output_dir: 출력 디렉토리
            model: 모델 ID
            style_prefix: 스타일 프리픽스 (모든 프롬프트 앞에 추가)
            width: 이미지 너비
            height: 이미지 높이
            steps: 생성 단계
            seed: 랜덤 시드
            on_progress: 진행 상황 콜백 함수

        Returns:
            결과 딕셔너리 리스트
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        total = len(prompts)
        is_free_model = "Free" in model
        batch_start_time = time.time()

        # 모델 가격 정보
        model_info = get_model_price_info(model)

        print(f"\n{'='*60}")
        print(f"[배치 생성] 🚀 시작")
        print(f"[배치 생성] 📌 API: Together.ai FLUX")
        print(f"[배치 생성] 📌 모델: {model}")
        print(f"[배치 생성] 📌 모델명: {model_info['name']}")
        if model_info['price'] > 0:
            total_cost = model_info['price'] * total
            print(f"[배치 생성] 📌 예상 비용: ${total_cost:.4f} (~{int(total_cost * 1400)}원) ({total}개 x ${model_info['price']:.4f})")
        else:
            print(f"[배치 생성] 📌 예상 비용: 무료")
        print(f"[배치 생성] 📌 크기: {width}x{height}")
        print(f"[배치 생성] 📌 총 이미지: {total}개")
        print(f"{'='*60}\n")

        for i, p in enumerate(prompts):
            item_start_time = time.time()
            filename = p.get("filename", f"{i+1:03d}.png")

            # 프롬프트 구성
            prompt_text = p.get("prompt", "")
            if style_prefix:
                full_prompt = f"{style_prefix}, {prompt_text}"
            else:
                full_prompt = prompt_text

            print(f"[{i+1}/{total}] {filename}")

            # Rate limit 대기 (첫 번째 이미지 제외, Free 모델만)
            if i > 0 and is_free_model:
                self._wait_for_rate_limit(model)

            try:
                # 이미지 생성
                gen_start = time.time()
                img_data = self.generate_image(
                    prompt=full_prompt,
                    model=model,
                    width=width,
                    height=height,
                    steps=steps,
                    seed=seed
                )
                gen_time = time.time() - gen_start

                # 파일 저장
                filepath = output_dir / filename
                with open(filepath, "wb") as f:
                    f.write(img_data)

                item_total_time = time.time() - item_start_time
                print(f"  -> 성공! (API: {gen_time:.1f}s, 총: {item_total_time:.1f}s, 크기: {len(img_data):,} bytes)")

                results.append({
                    "filename": filename,
                    "status": "success",
                    "path": str(filepath),
                    "generation_time": gen_time,
                    "total_time": item_total_time
                })

            except Exception as e:
                item_total_time = time.time() - item_start_time
                print(f"  -> 실패! ({item_total_time:.1f}s): {str(e)}")

                results.append({
                    "filename": filename,
                    "status": "failed",
                    "error": str(e),
                    "total_time": item_total_time
                })

            # 진행 상황 콜백
            if on_progress:
                on_progress(i + 1, total)

        # 최종 요약
        batch_total_time = time.time() - batch_start_time
        success_count = sum(1 for r in results if r["status"] == "success")

        print(f"\n{'='*60}")
        print(f"[배치 생성] ✅ 완료")
        print(f"[배치 생성]    📊 결과: {success_count}/{total} 성공")
        print(f"[배치 생성]    ⏱️ 총 소요: {batch_total_time:.1f}초")
        print(f"[배치 생성]    📈 평균: {batch_total_time/total:.1f}초/개")
        if model_info['price'] > 0:
            actual_cost = model_info['price'] * success_count
            print(f"[배치 생성]    💰 실제 비용: ${actual_cost:.4f} (~{int(actual_cost * 1400)}원)")
        else:
            print(f"[배치 생성]    💰 비용: 무료")
        print(f"{'='*60}\n")

        return results

    def estimate_cost(self, num_images: int, model: str) -> float:
        """예상 비용 계산 (USD)"""
        model_info = next(
            (m for m in IMAGE_MODELS if m["id"] == model),
            None
        )
        if model_info:
            return num_images * model_info["price"]
        return 0.0

    def estimate_time(self, num_images: int, model: str) -> int:
        """
        예상 소요 시간 계산 (초)

        Free 모델: API ~15초 + rate limit 6초 = ~21초/개
        유료 모델: API ~10초
        """
        if "Free" in model:
            return num_images * 21  # 보수적 추정
        else:
            return num_images * 12

    def get_model_info(self, model: str) -> Optional[Dict]:
        """모델 정보 조회"""
        return next(
            (m for m in IMAGE_MODELS if m["id"] == model),
            None
        )
