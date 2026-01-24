# -*- coding: utf-8 -*-
"""
캐릭터 이미지 생성기 (합성용) - 병렬 처리 + 멀티 API 지원

캐릭터를 단색 배경으로 생성하여 나중에 배경과 합성할 수 있도록 함

지원 기능:
- 다중 API 지원 (Together.ai, OpenAI, Stability AI, Replicate)
- 병렬 처리 (동시 생성)
- 스마트 rate limit 관리
"""
import time
from pathlib import Path
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 기존 Together 클라이언트 (하위 호환성)
from core.image.together_client import TogetherImageClient

# 새 통합 API 매니저
try:
    from utils.image_api_manager import ImageAPIManager, get_image_api_manager, GenerationResult
except ImportError:
    ImageAPIManager = None
    get_image_api_manager = None


@dataclass
class CharacterImageConfig:
    """캐릭터 이미지 생성 설정"""
    style: str = "animation"
    pose: str = "standing"
    background: str = "solid_gray"
    width: int = 1024
    height: int = 1024
    model: str = "black-forest-labs/FLUX.2-dev"
    style_prefix: str = ""  # 스타일 프롬프트 앞에 추가
    style_suffix: str = ""  # 스타일 프롬프트 뒤에 추가

    # 새로 추가: API 선택 + 병렬 처리
    api_provider: str = "Together.ai FLUX"  # API 제공자
    parallel_count: int = 1  # 동시 생성 수 (1-5)

    # v2.0: 시드 잠금 및 네거티브 프롬프트 지원
    seed: Optional[int] = None  # 시드 값 (None이면 랜덤)
    negative_prompt: str = ""  # 네거티브 프롬프트
    seed_lock_enabled: bool = False  # 시드 잠금 활성화 (배치 생성 시 첫 이미지 시드 자동 잠금)


class CharacterImageGenerator:
    """캐릭터 이미지 생성기 (합성용) - 병렬 처리 지원"""

    # 스타일 프리셋
    STYLE_PRESETS = {
        "animation": "animation style, flat colors, clean lines, high quality illustration",
        "illustration": "digital illustration, detailed artwork, professional quality",
        "manga": "manga style, anime aesthetic, clean linework",
        "3d_render": "3D rendered character, Pixar style, high quality CGI",
        "realistic": "semi-realistic style, detailed features, professional artwork"
    }

    # 포즈 옵션
    POSE_OPTIONS = {
        "standing": "standing pose, front view, neutral expression",
        "standing_left": "standing pose, facing slightly left, three-quarter view",
        "standing_right": "standing pose, facing slightly right, three-quarter view",
        "sitting": "sitting pose, relaxed posture",
        "walking": "walking pose, side view, in motion",
        "action": "dynamic action pose, energetic",
        "portrait": "upper body portrait, shoulders up"
    }

    # 배경 옵션 (v3.33: HEX 코드 제거 - 이미지에 텍스트 표시 방지)
    BACKGROUND_OPTIONS = {
        "solid_gray": "simple solid light gray background, no shadows on background",
        "solid_white": "simple solid pure white background, no shadows",
        "solid_blue": "simple solid light blue background, no shadows",
        "gradient": "simple gradient background from light gray to white"
    }

    def __init__(self, project_path: str = None):
        """
        Args:
            project_path: 프로젝트 경로 (이미지 저장용)
        """
        self.project_path = Path(project_path) if project_path else None

        # 기존 Together 클라이언트 (하위 호환성)
        self.image_client = TogetherImageClient()
        self._last_request_time = 0

        # 새 통합 API 매니저
        self.api_manager = get_image_api_manager() if get_image_api_manager else None

    def _build_prompt(
        self,
        visual_prompt: str,
        style: str = "animation",
        pose: str = "standing",
        background: str = "solid_gray",
        style_prefix: str = "",
        style_suffix: str = ""
    ) -> str:
        """캐릭터 이미지 생성 프롬프트 구성"""

        # 커스텀 스타일 prefix/suffix가 있으면 사용, 없으면 기본 프리셋 사용
        if style_prefix or style_suffix:
            style_text = ""  # 커스텀 스타일 사용 시 기본 프리셋 비활성화
        else:
            style_text = self.STYLE_PRESETS.get(style, self.STYLE_PRESETS["animation"])

        pose_text = self.POSE_OPTIONS.get(pose, self.POSE_OPTIONS["standing"])
        bg_text = self.BACKGROUND_OPTIONS.get(background, self.BACKGROUND_OPTIONS["solid_gray"])

        # 프롬프트 구성
        prompt_parts = []

        # 1. 스타일 prefix (맨 앞)
        if style_prefix:
            prompt_parts.append(style_prefix.strip())

        # 2. 캐릭터 visual prompt
        prompt_parts.append(visual_prompt.strip())

        # 3. 포즈와 배경
        prompt_parts.append(f"full body character, {pose_text}, {bg_text}")

        # 4. 스타일 텍스트 (커스텀이 없을 때만)
        if style_text:
            prompt_parts.append(style_text)

        # 5. 합성용 공통 요소
        prompt_parts.append("clean edges suitable for compositing, centered in frame, single character only")

        # 6. 스타일 suffix (맨 뒤)
        if style_suffix:
            prompt_parts.append(style_suffix.strip())

        prompt = ", ".join(prompt_parts)

        return prompt

    def generate_character_image(
        self,
        character: Dict,
        config: CharacterImageConfig = None,
        output_dir: Path = None,
        seed: Optional[int] = None  # v2.0: 시드 파라미터 추가
    ) -> Dict:
        """
        캐릭터 이미지 생성 (통합 API 지원)

        Args:
            character: 캐릭터 정보 (name, visual_prompt 또는 character_prompt 등)
            config: 생성 설정
            output_dir: 출력 디렉토리 (미지정 시 project_path/images/characters)
            seed: 시드 값 (None이면 config.seed 또는 랜덤)

        Returns:
            {
                "success": bool,
                "character_name": str,
                "image_path": str,
                "prompt": str,
                "pose": str,
                "background": str,
                "generation_time": float,
                "api_provider": str,
                "seed": int (생성에 사용된 시드),
                "error": str (실패 시)
            }
        """
        if config is None:
            config = CharacterImageConfig()

        # v3.32: 익명화 필터 적용 시 원본 이름 우선 사용 (결과 데이터/로깅용)
        char_name = character.get("_original_name") or character.get("name", "unknown")

        # visual_prompt 또는 character_prompt 가져오기
        visual_prompt = (
            character.get("visual_prompt") or
            character.get("character_prompt") or
            character.get("prompt") or
            ""
        )

        if not visual_prompt:
            return {
                "success": False,
                "character_name": char_name,
                "error": f"캐릭터 '{char_name}'에 visual_prompt가 없습니다."
            }

        # 프롬프트 생성
        prompt = self._build_prompt(
            visual_prompt=visual_prompt,
            style=config.style,
            pose=config.pose,
            background=config.background,
            style_prefix=config.style_prefix,
            style_suffix=config.style_suffix
        )

        # 🔴 v3.12: 포즈 디버깅 로그 강화
        pose_text = self.POSE_OPTIONS.get(config.pose, self.POSE_OPTIONS["standing"])
        print(f"[CharacterImageGenerator] 캐릭터 '{char_name}' 이미지 생성")
        print(f"  API: {config.api_provider}")
        print(f"  스타일: {config.style}")
        print(f"  포즈: {config.pose} -> \"{pose_text}\"")
        print(f"  배경: {config.background}")
        print(f"  프롬프트 미리보기: ...{pose_text}, {self.BACKGROUND_OPTIONS.get(config.background, '')}...")

        # 출력 디렉토리 설정
        if output_dir is None and self.project_path:
            output_dir = self.project_path / "images" / "characters"
        elif output_dir is None:
            output_dir = Path("images/characters")

        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            start_time = time.time()

            # API 선택 분기
            if config.api_provider == "Together.ai FLUX" or not self.api_manager:
                # 기존 Together 클라이언트 사용 (하위 호환성)
                result = self._generate_with_together(prompt, config, output_dir, char_name)
            else:
                # 새 통합 API 매니저 사용 (v2.0: 시드 전달)
                result = self._generate_with_api_manager(prompt, config, output_dir, char_name, seed=seed)

            gen_time = time.time() - start_time
            result["generation_time"] = gen_time
            result["api_provider"] = config.api_provider

            if result.get("success"):
                print(f"  완료! ({gen_time:.1f}초) -> {result.get('image_path')}")
            else:
                print(f"  실패: {result.get('error')}")

            return result

        except Exception as e:
            print(f"  실패: {str(e)}")
            return {
                "success": False,
                "character_name": char_name,
                "prompt": prompt,
                "error": str(e)
            }

    def _generate_with_together(
        self,
        prompt: str,
        config: CharacterImageConfig,
        output_dir: Path,
        char_name: str
    ) -> Dict:
        """기존 Together.ai 클라이언트로 생성"""

        # Rate limit 대기 (Free 모델)
        if "Free" in config.model:
            elapsed = time.time() - self._last_request_time
            if elapsed < 6:
                wait_time = 6 - elapsed
                print(f"  [Rate limit] {wait_time:.1f}초 대기...")
                time.sleep(wait_time)

        # 이미지 생성
        img_data = self.image_client.generate_image(
            prompt=prompt,
            model=config.model,
            width=config.width,
            height=config.height
        )

        self._last_request_time = time.time()

        # 파일명 생성 (안전한 이름)
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in char_name)
        timestamp = int(time.time() * 1000)
        filename = f"char_{safe_name}_{config.pose}_{timestamp}.png"
        filepath = output_dir / filename

        # 저장
        with open(filepath, "wb") as f:
            f.write(img_data)

        return {
            "success": True,
            "character_name": char_name,
            "image_path": str(filepath),
            "image_url": str(filepath),
            "prompt": prompt,
            "pose": config.pose,
            "background": config.background
        }

    def _generate_with_api_manager(
        self,
        prompt: str,
        config: CharacterImageConfig,
        output_dir: Path,
        char_name: str,
        seed: Optional[int] = None  # v2.0: 시드 파라미터 추가
    ) -> Dict:
        """통합 API 매니저로 생성"""

        # v2.0: 시드 결정 - 명시적 전달 > config.seed
        use_seed = seed if seed is not None else config.seed

        # v2.0: 시드 및 네거티브 프롬프트 로깅
        if use_seed is not None:
            print(f"  [CharacterImageGenerator] 🔒 시드 전달: {use_seed}")
        else:
            print(f"  [CharacterImageGenerator] 🎲 랜덤 시드 사용")

        if config.negative_prompt:
            print(f"  [CharacterImageGenerator] ✅ 네거티브 프롬프트: {len(config.negative_prompt)}자")

        result = self.api_manager.generate_image(
            prompt=prompt,
            api_provider=config.api_provider,
            model=config.model,
            width=config.width,
            height=config.height,
            seed=use_seed,  # v2.0: 시드 전달
            negative_prompt=config.negative_prompt  # v2.0: 네거티브 프롬프트 전달
        )

        if not result.success:
            return {
                "success": False,
                "character_name": char_name,
                "prompt": prompt,
                "error": result.error
            }

        # 파일명 생성
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in char_name)
        timestamp = int(time.time() * 1000)
        filename = f"char_{safe_name}_{config.pose}_{timestamp}.png"
        filepath = output_dir / filename

        # 저장
        self.api_manager.save_image(result, str(filepath))

        # v2.0: 결과 시드 추출
        result_seed = getattr(result, 'seed', None) or use_seed

        return {
            "success": True,
            "character_name": char_name,
            "image_path": str(filepath),
            "image_url": str(filepath),
            "prompt": prompt,
            "pose": config.pose,
            "background": config.background,
            "seed": result_seed  # v2.0: 시드 반환
        }

    def generate_batch(
        self,
        characters: List[Dict],
        config: CharacterImageConfig = None,
        output_dir: Path = None,
        on_progress: Callable[[int, int, Dict], None] = None,
        on_start: Callable[[str], None] = None,
        on_complete: Callable[[str, float, bool, Optional[str]], None] = None,
        on_seed_locked: Callable[[int], None] = None  # v2.0: 시드 잠금 콜백
    ) -> List[Dict]:
        """
        여러 캐릭터 이미지 배치 생성 (병렬 처리 지원)

        Args:
            characters: 캐릭터 목록
            config: 생성 설정 (parallel_count로 동시 생성 수 설정)
            output_dir: 출력 디렉토리
            on_progress: 진행 콜백 (current, total, result)
            on_start: 캐릭터 생성 시작 콜백 (char_name)
            on_complete: 캐릭터 생성 완료 콜백 (char_name, elapsed, success, error)
            on_seed_locked: 시드 잠금 콜백 (seed) - 첫 이미지 시드 자동 잠금 시 호출

        Returns:
            결과 목록
        """
        if config is None:
            config = CharacterImageConfig()

        parallel_count = max(1, min(5, config.parallel_count))
        total = len(characters)

        # v2.0: 시드 잠금 상태 관리
        locked_seed = config.seed  # 초기 시드 (config에서 가져옴)
        seed_lock_enabled = config.seed_lock_enabled

        print(f"\n{'='*50}")
        print(f"캐릭터 이미지 배치 생성: {total}명")
        print(f"API: {config.api_provider}")
        print(f"동시 생성: {parallel_count}개")
        # v2.0: 시드 잠금 상태 로깅
        if seed_lock_enabled:
            print(f"🔒 시드 잠금: 활성화 (초기 시드: {locked_seed if locked_seed else '자동'})")
        if config.negative_prompt:
            print(f"✅ 네거티브 프롬프트: {len(config.negative_prompt)}자")
        print(f"{'='*50}\n")

        start_time = time.time()
        results = []

        if parallel_count <= 1:
            # ── 순차 처리 (시드 잠금 지원) ──
            for i, char in enumerate(characters):
                # v3.32: 익명화 필터 적용 시 원본 이름 사용 (콜백용)
                # _original_name이 있으면 원본 이름, 없으면 name 사용
                char_name = char.get("_original_name") or char.get("name", "unknown")

                # 시작 콜백
                if on_start:
                    on_start(char_name)

                char_start = time.time()

                # v2.0: 시드 잠금 시 잠긴 시드 전달
                current_seed = locked_seed if seed_lock_enabled else config.seed

                result = self.generate_character_image(char, config, output_dir, seed=current_seed)
                char_elapsed = time.time() - char_start

                # v2.0: 첫 번째 성공 시 시드 자동 잠금
                if seed_lock_enabled and locked_seed is None and result.get("success") and result.get("seed"):
                    locked_seed = result["seed"]
                    print(f"[시드 잠금] 🔒 첫 이미지 시드 자동 잠금: {locked_seed}")
                    if on_seed_locked:
                        on_seed_locked(locked_seed)

                results.append(result)

                # 완료 콜백
                if on_complete:
                    on_complete(
                        char_name,
                        char_elapsed,
                        result.get("success", False),
                        result.get("error")
                    )

                if on_progress:
                    on_progress(i + 1, total, result)
        else:
            # ── 병렬 처리 ──
            # v2.0: 병렬 처리 시 시드 잠금 경고
            if seed_lock_enabled:
                print(f"⚠️ [시드 잠금] 병렬 처리({parallel_count}개)에서는 '첫 이미지 자동 잠금' 기능이 지원되지 않습니다.")
                print(f"   모든 이미지에 동일한 시드({locked_seed})가 적용됩니다.")

            with ThreadPoolExecutor(max_workers=parallel_count) as executor:
                # 작업 제출
                future_to_char = {}
                for i, char in enumerate(characters):
                    # v3.32: 익명화 필터 적용 시 원본 이름 사용 (콜백용)
                    char_name = char.get("_original_name") or char.get("name", "unknown")

                    # 시작 콜백 (제출 시점)
                    if on_start:
                        on_start(char_name)

                    # v2.0: 시드 전달 (병렬 처리에서는 config.seed 또는 locked_seed 사용)
                    future = executor.submit(
                        self._generate_single_for_batch_with_timing,
                        char,
                        config,
                        output_dir,
                        i,
                        seed=locked_seed if seed_lock_enabled else config.seed  # v2.0: 시드 전달
                    )
                    future_to_char[future] = (i, char_name)

                # 결과 수집
                completed = 0
                for future in as_completed(future_to_char):
                    idx, char_name = future_to_char[future]
                    try:
                        result, elapsed = future.result()
                    except Exception as e:
                        result = {
                            "success": False,
                            "character_name": char_name,
                            "error": str(e)
                        }
                        elapsed = 0

                    results.append((idx, result))
                    completed += 1

                    # 완료 콜백
                    if on_complete:
                        on_complete(
                            char_name,
                            elapsed,
                            result.get("success", False),
                            result.get("error")
                        )

                    if on_progress:
                        on_progress(completed, total, result)

                # 원래 순서대로 정렬
                results.sort(key=lambda x: x[0])
                results = [r[1] for r in results]

        # 완료 통계
        total_time = time.time() - start_time
        success_count = sum(1 for r in results if r.get("success"))

        print(f"\n{'='*50}")
        print(f"완료: {success_count}/{total} 성공")
        print(f"총 소요 시간: {total_time:.1f}초")
        if total > 0:
            print(f"캐릭터당 평균: {total_time/total:.1f}초")
        print(f"{'='*50}\n")

        return results

    def _generate_single_for_batch(
        self,
        character: Dict,
        config: CharacterImageConfig,
        output_dir: Path,
        index: int,
        seed: Optional[int] = None  # v2.0: 시드 파라미터 추가
    ) -> Dict:
        """배치 생성용 단일 캐릭터 생성 (스레드에서 호출)"""

        # 병렬 처리 시 약간의 지연 추가 (동시 호출 방지)
        time.sleep(index * 0.5)

        # v2.0: 시드 전달 (병렬 처리에서는 config.seed 사용)
        return self.generate_character_image(character, config, output_dir, seed=seed or config.seed)

    def _generate_single_for_batch_with_timing(
        self,
        character: Dict,
        config: CharacterImageConfig,
        output_dir: Path,
        index: int,
        seed: Optional[int] = None  # v2.0: 시드 파라미터 추가
    ) -> tuple:
        """배치 생성용 단일 캐릭터 생성 (타이밍 포함)"""

        # 병렬 처리 시 약간의 지연 추가 (동시 호출 방지)
        time.sleep(index * 0.5)

        start_time = time.time()
        # v2.0: 시드 전달
        result = self.generate_character_image(character, config, output_dir, seed=seed or config.seed)
        elapsed = time.time() - start_time

        return result, elapsed

    def generate_multiple_poses(
        self,
        character: Dict,
        poses: List[str],
        config: CharacterImageConfig = None,
        output_dir: Path = None
    ) -> List[Dict]:
        """
        한 캐릭터의 여러 포즈 이미지 생성

        Args:
            character: 캐릭터 정보
            poses: 포즈 목록 ["standing", "walking", ...]
            config: 생성 설정
            output_dir: 출력 디렉토리

        Returns:
            결과 목록
        """
        if config is None:
            config = CharacterImageConfig()

        results = []

        for pose in poses:
            pose_config = CharacterImageConfig(
                style=config.style,
                pose=pose,
                background=config.background,
                width=config.width,
                height=config.height,
                model=config.model,
                style_prefix=config.style_prefix,
                style_suffix=config.style_suffix,
                api_provider=config.api_provider,
                parallel_count=1  # 포즈 생성은 순차
            )

            result = self.generate_character_image(character, pose_config, output_dir)
            results.append(result)

        return results

    @staticmethod
    def get_available_apis() -> List[str]:
        """사용 가능한 API 목록"""
        try:
            from utils.image_api_manager import API_MODELS
            return list(API_MODELS.keys())
        except ImportError:
            return ["Together.ai FLUX"]

    @staticmethod
    def get_models_for_api(api_provider: str) -> List[tuple]:
        """API별 모델 목록"""
        try:
            from utils.image_api_manager import API_MODELS
            return API_MODELS.get(api_provider, [])
        except ImportError:
            if api_provider == "Together.ai FLUX":
                return [
                    ("black-forest-labs/FLUX.2-dev", "FLUX.2 Dev (권장, ~20원)"),
                    ("black-forest-labs/FLUX.2-flex", "FLUX.2 Flex (~40원)"),
                    ("black-forest-labs/FLUX.2-pro", "FLUX.2 Pro (고품질, ~40원)"),
                ]
            return []

    @staticmethod
    def estimate_time(
        num_characters: int,
        api_provider: str = "Together.ai FLUX",
        model: str = "",
        parallel_count: int = 1
    ) -> int:
        """예상 소요 시간 (초)"""
        try:
            from utils.image_api_manager import API_GENERATION_TIME
            base_time = API_GENERATION_TIME.get(api_provider, 10)
        except ImportError:
            base_time = 15 if "Free" in model else 10

        # Lightning 모델은 더 빠름
        if "lightning" in model.lower():
            base_time = 3

        # Free 모델은 rate limit 추가
        if "Free" in model:
            base_time += 6

        # 병렬 처리 반영
        parallel_count = max(1, parallel_count)
        total_time = (num_characters * base_time) / parallel_count

        return int(total_time)
