"""
배경 이미지 생성기 (캐릭터 제외)

씬의 배경/환경만 생성하여 나중에 캐릭터와 합성
주인공 캐릭터는 제외하고 엑스트라/군중은 선택적으로 포함
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.image.together_client import TogetherImageClient


@dataclass
class BackgroundImageConfig:
    """배경 이미지 생성 설정"""
    style: str = "animation"
    include_extras: bool = True  # 엑스트라/보조 인물 포함 여부
    width: int = 1280
    height: int = 720
    model: str = "black-forest-labs/FLUX.1-schnell-Free"
    style_prefix: str = ""  # 스타일 프롬프트 앞에 추가
    style_suffix: str = ""  # 스타일 프롬프트 뒤에 추가


class BackgroundImageGenerator:
    """배경 이미지 생성기 (캐릭터 제외)"""

    # 스타일 프리셋
    STYLE_PRESETS = {
        "animation": "animation style, flat colors, clean lines, vibrant colors, cinematic composition",
        "illustration": "digital illustration, detailed environment, professional artwork",
        "infographic": "infographic style, modern design, clean visuals, minimal clutter",
        "realistic": "photorealistic environment, detailed scenery, natural lighting",
        "painterly": "painterly style, artistic, impressionistic background"
    }

    # 샷 타입
    SHOT_TYPES = {
        "wide": "wide establishing shot, full environment visible",
        "medium": "medium shot, partial environment",
        "close": "close-up on specific element",
        "panoramic": "panoramic view, expansive scenery"
    }

    def __init__(self, project_path: str = None):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path) if project_path else None
        self.image_client = TogetherImageClient()
        self._last_request_time = 0

        # 씬 데이터 로드
        self.scenes = self._load_scenes() if self.project_path else []

    def _load_scenes(self) -> List[Dict]:
        """씬 분석 결과 로드"""
        if not self.project_path:
            return []

        scenes_path = self.project_path / "analysis" / "scenes.json"
        if scenes_path.exists():
            with open(scenes_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _build_prompt(
        self,
        scene: Dict,
        style: str = "animation",
        include_extras: bool = True,
        shot_type: str = "wide",
        style_prefix: str = "",
        style_suffix: str = ""
    ) -> str:
        """배경 이미지 프롬프트 구성 - 씬 데이터 우선"""

        scene_id = scene.get("scene_id", 0)

        # === 핵심: 씬 분석 데이터에서 프롬프트 추출 (우선순위대로) ===

        # 1순위: image_prompt_en (영어 이미지 프롬프트)
        base_prompt = scene.get("image_prompt_en", "")

        # 2순위: direction_guide (연출 가이드)
        if not base_prompt:
            base_prompt = scene.get("direction_guide", "")

        # 3순위: visual_elements 조합
        visual_elements = scene.get("visual_elements", [])
        if not base_prompt and visual_elements:
            base_prompt = ", ".join(visual_elements)

        # 4순위: script_text에서 추출 (최후의 수단)
        if not base_prompt:
            script = scene.get("script_text", "")
            if script:
                # 스크립트 앞부분만 사용
                base_prompt = f"scene depicting: {script[:150]}"

        # 디버그 로그
        print(f"  [프롬프트 추출] 씬 {scene_id}:")
        print(f"    image_prompt_en: {scene.get('image_prompt_en', '')[:80]}...")
        print(f"    direction_guide: {scene.get('direction_guide', '')[:80]}...")
        print(f"    사용할 base_prompt: {base_prompt[:100]}...")

        # 분위기
        mood = scene.get("mood", "")

        # 카메라 제안
        camera = scene.get("camera_suggestion", "")

        # 스타일 텍스트 - 커스텀 prefix/suffix가 있으면 기본 프리셋 비활성화
        if style_prefix or style_suffix:
            style_text = ""  # 커스텀 스타일 사용
        else:
            style_text = self.STYLE_PRESETS.get(style, self.STYLE_PRESETS["animation"])

        shot_text = self.SHOT_TYPES.get(shot_type, self.SHOT_TYPES["wide"])

        # 엑스트라/군중 설정
        if include_extras:
            extras_text = "background people visible in distance"
        else:
            extras_text = "empty scene, no people"

        # 시각 요소 (base_prompt와 중복되지 않게)
        visual_text = ""
        if visual_elements and base_prompt != ", ".join(visual_elements):
            visual_text = ", ".join(visual_elements)

        # === 프롬프트 구성: 씬 내용을 가장 앞에! ===
        prompt_parts = []

        # 0. 스타일 prefix (맨 앞)
        if style_prefix:
            prompt_parts.append(style_prefix.strip())

        # 1. 씬 내용 (가장 중요!)
        if base_prompt:
            prompt_parts.append(base_prompt)

        # 2. 시각 요소
        if visual_text:
            prompt_parts.append(visual_text)

        # 3. 분위기
        if mood:
            prompt_parts.append(f"{mood} atmosphere")

        # 4. 카메라/샷 타입
        if camera:
            prompt_parts.append(camera)
        else:
            prompt_parts.append(shot_text)

        # 5. 스타일 (커스텀이 없을 때만)
        if style_text:
            prompt_parts.append(style_text)

        # 6. 배경 관련 지시
        prompt_parts.append("background environment scene")
        prompt_parts.append(extras_text)
        prompt_parts.append("no main character in foreground")
        prompt_parts.append("high quality")

        # 7. 스타일 suffix (맨 뒤)
        if style_suffix:
            prompt_parts.append(style_suffix.strip())

        # 최종 프롬프트 구성
        prompt = ", ".join(filter(None, [p.strip() for p in prompt_parts if p.strip()]))

        return prompt

    def generate_background(
        self,
        scene: Dict,
        config: BackgroundImageConfig = None,
        output_dir: Path = None,
        shot_type: str = "wide"
    ) -> Dict:
        """
        배경 이미지 생성 (주인공 캐릭터 제외)

        Args:
            scene: 씬 정보
            config: 생성 설정
            output_dir: 출력 디렉토리
            shot_type: 샷 타입 (wide, medium, close, panoramic)

        Returns:
            {
                "success": bool,
                "scene_id": int,
                "image_path": str,
                "image_url": str,
                "prompt": str,
                "is_background": True,
                "error": str (실패 시)
            }
        """
        if config is None:
            config = BackgroundImageConfig()

        scene_id = scene.get("scene_id", 0)

        # 프롬프트 생성
        prompt = self._build_prompt(
            scene=scene,
            style=config.style,
            include_extras=config.include_extras,
            shot_type=shot_type,
            style_prefix=config.style_prefix,
            style_suffix=config.style_suffix
        )

        # 원본 씬 프롬프트 저장 (디버깅용)
        original_scene_prompt = scene.get("image_prompt_en") or scene.get("direction_guide") or ""

        print(f"[BackgroundGenerator] 씬 {scene_id} 배경 생성")
        print(f"  원본 씬 프롬프트: {original_scene_prompt[:100]}...")
        print(f"  스타일: {config.style}")
        print(f"  엑스트라 포함: {config.include_extras}")
        print(f"  샷 타입: {shot_type}")
        print(f"  최종 프롬프트: {prompt[:150]}...")

        # 출력 디렉토리 설정
        if output_dir is None and self.project_path:
            output_dir = self.project_path / "images" / "backgrounds"
        elif output_dir is None:
            output_dir = Path("images/backgrounds")

        output_dir.mkdir(parents=True, exist_ok=True)

        # Rate limit 대기 (Free 모델)
        if "Free" in config.model:
            elapsed = time.time() - self._last_request_time
            if elapsed < 6:
                wait_time = 6 - elapsed
                print(f"  [Rate limit] {wait_time:.1f}초 대기...")
                time.sleep(wait_time)

        try:
            start_time = time.time()

            # 이미지 생성
            img_data = self.image_client.generate_image(
                prompt=prompt,
                model=config.model,
                width=config.width,
                height=config.height
            )

            self._last_request_time = time.time()
            gen_time = self._last_request_time - start_time

            # 파일명 생성
            timestamp = int(time.time() * 1000)
            filename = f"bg_scene_{scene_id:03d}_{timestamp}.png"
            filepath = output_dir / filename

            # 저장
            with open(filepath, "wb") as f:
                f.write(img_data)

            print(f"  완료! ({gen_time:.1f}초) -> {filepath}")

            return {
                "success": True,
                "scene_id": scene_id,
                "image_path": str(filepath),
                "image_url": str(filepath),
                "prompt": prompt,
                "original_scene_prompt": original_scene_prompt,
                "is_background": True,
                "include_extras": config.include_extras,
                "generation_time": gen_time
            }

        except Exception as e:
            print(f"  실패: {str(e)}")
            return {
                "success": False,
                "scene_id": scene_id,
                "prompt": prompt,
                "is_background": True,
                "error": str(e)
            }

    def generate_scene_background(
        self,
        scene_id: int,
        config: BackgroundImageConfig = None,
        output_dir: Path = None
    ) -> Dict:
        """
        씬 ID로 배경 이미지 생성

        Args:
            scene_id: 씬 ID
            config: 생성 설정
            output_dir: 출력 디렉토리

        Returns:
            생성 결과
        """
        # 씬 찾기
        scene = None
        for s in self.scenes:
            if s.get("scene_id") == scene_id:
                scene = s
                break

        if not scene:
            return {
                "success": False,
                "scene_id": scene_id,
                "error": f"씬 {scene_id}을 찾을 수 없습니다."
            }

        return self.generate_background(scene, config, output_dir)

    def generate_all_backgrounds(
        self,
        config: BackgroundImageConfig = None,
        start_scene: int = 1,
        end_scene: int = None,
        output_dir: Path = None,
        on_progress: Callable = None
    ) -> List[Dict]:
        """
        모든 씬 배경 배치 생성

        Args:
            config: 생성 설정
            start_scene: 시작 씬 ID
            end_scene: 종료 씬 ID
            output_dir: 출력 디렉토리
            on_progress: 진행 콜백 (current, total, result)

        Returns:
            결과 목록
        """
        if config is None:
            config = BackgroundImageConfig()

        # 씬 범위 필터링
        scenes_to_generate = [s for s in self.scenes
                             if s.get("scene_id", 0) >= start_scene]
        if end_scene:
            scenes_to_generate = [s for s in scenes_to_generate
                                 if s.get("scene_id", 0) <= end_scene]

        results = []
        total = len(scenes_to_generate)

        print(f"\n{'='*50}")
        print(f"배경 이미지 배치 생성: {total}개 씬")
        print(f"{'='*50}\n")

        for i, scene in enumerate(scenes_to_generate):
            result = self.generate_background(scene, config, output_dir)
            results.append(result)

            if on_progress:
                on_progress(i + 1, total, result)

        # 로그 저장
        if output_dir is None and self.project_path:
            output_dir = self.project_path / "images" / "backgrounds"
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            log_path = output_dir / "background_generation_log.json"
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        success_count = sum(1 for r in results if r.get("success"))
        print(f"\n완료: {success_count}/{total} 성공\n")

        return results
