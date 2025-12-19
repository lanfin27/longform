"""
씬 합성기

배경 이미지 + 캐릭터 이미지 = 최종 씬 이미지
AI 분석 기반 자동 배치 지원
"""
import json
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from io import BytesIO
import requests

try:
    from PIL import Image
except ImportError:
    Image = None
    print("[SceneCompositor] PIL/Pillow가 설치되지 않았습니다. pip install Pillow")

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.image.ai_composition_analyzer import (
    AICompositionAnalyzer,
    CompositionAnalysis,
    CharacterPlacement
)


class SceneCompositor:
    """씬 이미지 합성기"""

    # 캐릭터 배치 위치 프리셋 (x비율, y비율 - 캐릭터 하단 기준)
    POSITION_PRESETS = {
        "center": (0.5, 0.85),
        "left": (0.25, 0.85),
        "right": (0.75, 0.85),
        "far_left": (0.15, 0.85),
        "far_right": (0.85, 0.85),
        "center_left": (0.35, 0.85),
        "center_right": (0.65, 0.85),
    }

    # 캐릭터 크기 프리셋 (배경 높이 대비 비율)
    SIZE_PRESETS = {
        "large": 0.7,
        "medium": 0.55,
        "small": 0.4,
        "tiny": 0.25,
    }

    # 레이아웃 프리셋
    LAYOUT_PRESETS = {
        "single_center": [(0.5, 0.85)],
        "dialogue": [(0.3, 0.85), (0.7, 0.85)],
        "three_chars": [(0.2, 0.85), (0.5, 0.85), (0.8, 0.85)],
        "group": [(0.15, 0.85), (0.38, 0.85), (0.62, 0.85), (0.85, 0.85)],
    }

    def __init__(self, project_path: str = None):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path) if project_path else None

        if self.project_path:
            self.output_dir = self.project_path / "images" / "composited"
        else:
            self.output_dir = Path("images/composited")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        if Image is None:
            raise ImportError("PIL/Pillow가 필요합니다. pip install Pillow")

        # AI 합성 분석기
        self.ai_analyzer = AICompositionAnalyzer()

    def _load_image(self, url_or_path: str) -> Image.Image:
        """이미지 로드 (URL 또는 로컬 경로)"""
        if url_or_path.startswith("http"):
            response = requests.get(url_or_path, timeout=30)
            return Image.open(BytesIO(response.content)).convert("RGBA")
        else:
            return Image.open(url_or_path).convert("RGBA")

    def _remove_solid_background(
        self,
        image: Image.Image,
        tolerance: int = 40,
        edge_blur: int = 2
    ) -> Image.Image:
        """
        단색 배경 제거 (크로마키 효과)

        모서리 픽셀을 기준으로 배경색을 감지하고 투명하게 변환

        Args:
            image: RGBA 이미지
            tolerance: 배경색 허용 오차 (높을수록 더 많이 제거)
            edge_blur: 가장자리 부드럽게 (미구현)

        Returns:
            배경이 제거된 RGBA 이미지
        """
        # 모서리 4곳에서 배경색 샘플링
        corners = [
            image.getpixel((5, 5)),
            image.getpixel((image.width - 6, 5)),
            image.getpixel((5, image.height - 6)),
            image.getpixel((image.width - 6, image.height - 6))
        ]

        # 가장 많이 나온 색을 배경색으로 추정
        # 간단히 첫 번째 모서리 색상 사용
        bg_color = corners[0][:3]

        # 모든 모서리가 비슷한 색인지 확인
        similar_count = sum(1 for c in corners
                          if abs(c[0] - bg_color[0]) + abs(c[1] - bg_color[1]) + abs(c[2] - bg_color[2]) < tolerance)

        if similar_count < 3:
            # 모서리가 다른 색이면 배경 제거 어려움 - 원본 반환
            print("  [배경제거] 모서리 색상이 달라 배경 제거 생략")
            return image

        print(f"  [배경제거] 배경색 감지: RGB({bg_color[0]}, {bg_color[1]}, {bg_color[2]})")

        # 배경색과 비슷한 픽셀을 투명하게
        data = list(image.getdata())
        new_data = []

        for pixel in data:
            r, g, b, a = pixel

            # 배경색과의 차이 계산
            diff = abs(r - bg_color[0]) + abs(g - bg_color[1]) + abs(b - bg_color[2])

            if diff < tolerance:
                # 배경색 - 완전 투명
                new_data.append((r, g, b, 0))
            elif diff < tolerance * 1.5:
                # 경계 - 반투명 (부드러운 전환)
                alpha = int(255 * (diff - tolerance) / (tolerance * 0.5))
                alpha = max(0, min(255, alpha))
                new_data.append((r, g, b, alpha))
            else:
                # 캐릭터 - 원본 유지
                new_data.append(pixel)

        result = Image.new("RGBA", image.size)
        result.putdata(new_data)
        return result

    def _resize_character(
        self,
        char_image: Image.Image,
        bg_height: int,
        size_preset: str = "medium"
    ) -> Image.Image:
        """캐릭터 크기 조정"""
        ratio = self.SIZE_PRESETS.get(size_preset, 0.55)
        target_height = int(bg_height * ratio)

        # 비율 유지
        aspect = char_image.width / char_image.height
        target_width = int(target_height * aspect)

        return char_image.resize((target_width, target_height), Image.LANCZOS)

    def _determine_layout(self, num_characters: int) -> str:
        """캐릭터 수에 따라 레이아웃 결정"""
        if num_characters == 0:
            return "none"
        elif num_characters == 1:
            return "single_center"
        elif num_characters == 2:
            return "dialogue"
        elif num_characters == 3:
            return "three_chars"
        else:
            return "group"

    def _get_positions_for_layout(
        self,
        layout: str,
        num_characters: int
    ) -> List[Tuple[float, float]]:
        """레이아웃에 따른 위치 목록 반환"""

        preset = self.LAYOUT_PRESETS.get(layout)
        if preset:
            return preset[:num_characters]

        # 동적 배치 (5명 이상)
        positions = []
        for i in range(num_characters):
            x = 0.1 + (0.8 / max(1, num_characters - 1)) * i if num_characters > 1 else 0.5
            positions.append((x, 0.85))
        return positions

    def composite_scene(
        self,
        background_path: str,
        characters: List[Dict],
        scene_id: int,
        layout: str = "auto",
        remove_bg: bool = True,
        output_path: str = None
    ) -> Dict:
        """
        씬 합성

        Args:
            background_path: 배경 이미지 경로 또는 URL
            characters: 캐릭터 정보 리스트
                [{"image_path": ..., "name": ..., "size": "medium", "position": "center"}, ...]
            scene_id: 씬 ID
            layout: 레이아웃 ("auto", "single_center", "dialogue", "three_chars", "group")
            remove_bg: 캐릭터 배경 제거 여부
            output_path: 출력 경로 (미지정 시 자동 생성)

        Returns:
            {
                "success": bool,
                "scene_id": int,
                "image_path": str,
                "characters_used": [...],
                "is_composited": True,
                "error": str (실패 시)
            }
        """
        print(f"[SceneCompositor] 씬 {scene_id} 합성 시작")
        print(f"  배경: {background_path[:60]}...")
        print(f"  캐릭터 수: {len(characters)}")

        try:
            # 1. 배경 이미지 로드
            background = self._load_image(background_path)
            bg_width, bg_height = background.size
            print(f"  배경 크기: {bg_width}x{bg_height}")

            # 2. 레이아웃 결정
            chars_with_images = [c for c in characters if c.get("image_path") or c.get("image_url")]

            if layout == "auto":
                layout = self._determine_layout(len(chars_with_images))
            print(f"  레이아웃: {layout}")

            positions = self._get_positions_for_layout(layout, len(chars_with_images))

            # 3. 결과 이미지 초기화
            result_image = background.copy()
            characters_used = []

            # 4. 각 캐릭터 합성
            for i, char in enumerate(chars_with_images):
                char_name = char.get("name", f"character_{i}")
                char_path = char.get("image_path") or char.get("image_url")

                if not char_path:
                    print(f"  캐릭터 '{char_name}': 이미지 없음, 스킵")
                    continue

                print(f"  캐릭터 '{char_name}' 합성 중...")

                try:
                    # 캐릭터 이미지 로드
                    char_image = self._load_image(char_path)

                    # 배경 제거
                    if remove_bg:
                        char_image = self._remove_solid_background(char_image)

                    # 크기 조정
                    size_preset = char.get("size", "medium")
                    char_image = self._resize_character(char_image, bg_height, size_preset)

                    # 위치 결정
                    if char.get("position"):
                        position = self.POSITION_PRESETS.get(
                            char["position"],
                            positions[i] if i < len(positions) else (0.5, 0.85)
                        )
                    elif i < len(positions):
                        position = positions[i]
                    else:
                        position = (0.5, 0.85)

                    # 좌표 계산 (캐릭터 하단 중앙 기준)
                    x = int(position[0] * bg_width - char_image.width / 2)
                    y = int(position[1] * bg_height - char_image.height)

                    # 범위 체크
                    x = max(0, min(x, bg_width - char_image.width))
                    y = max(0, min(y, bg_height - char_image.height))

                    # 합성
                    result_image.paste(char_image, (x, y), char_image)
                    characters_used.append(char_name)

                    print(f"    -> 위치: ({x}, {y}), 크기: {char_image.width}x{char_image.height}")

                except Exception as e:
                    print(f"    -> 실패: {str(e)}")

            # 5. 저장
            if output_path is None:
                timestamp = int(time.time() * 1000)
                filename = f"scene_{scene_id:03d}_composited_{timestamp}.png"
                output_path = str(self.output_dir / filename)

            # RGB로 변환 후 저장 (PNG는 RGBA 지원)
            result_image.save(output_path, "PNG")

            print(f"  합성 완료! -> {output_path}")
            print(f"  사용된 캐릭터: {', '.join(characters_used)}")

            return {
                "success": True,
                "scene_id": scene_id,
                "image_path": output_path,
                "image_url": output_path,
                "characters_used": characters_used,
                "is_composited": True,
                "layout": layout
            }

        except Exception as e:
            print(f"  합성 실패: {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                "success": False,
                "scene_id": scene_id,
                "is_composited": True,
                "error": str(e)
            }

    def composite_all_scenes(
        self,
        scenes: List[Dict],
        background_images: Dict[int, Dict],
        character_images: Dict[str, Dict],
        on_progress=None
    ) -> List[Dict]:
        """
        모든 씬 자동 합성

        Args:
            scenes: 씬 목록 (scene_id, characters 포함)
            background_images: {scene_id: {"image_path": ...}}
            character_images: {character_name: {"image_path": ...}}
            on_progress: 진행 콜백 (current, total, result)

        Returns:
            합성 결과 목록
        """
        results = []
        total = len(scenes)

        print(f"\n{'='*50}")
        print(f"씬 일괄 합성: {total}개 씬")
        print(f"{'='*50}\n")

        for i, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", i + 1)

            # 배경 이미지 확인
            bg_info = background_images.get(scene_id)
            if not bg_info:
                print(f"씬 {scene_id}: 배경 이미지 없음, 스킵")
                results.append({
                    "success": False,
                    "scene_id": scene_id,
                    "error": "배경 이미지 없음"
                })
                continue

            bg_path = bg_info.get("image_path") or bg_info.get("image_url")
            if not bg_path:
                continue

            # 씬에 등장하는 캐릭터 목록
            scene_char_names = scene.get("characters", [])

            # 캐릭터 정보 수집
            chars_for_scene = []
            for char_name in scene_char_names:
                char_info = character_images.get(char_name)
                if char_info and (char_info.get("image_path") or char_info.get("image_url")):
                    chars_for_scene.append({
                        "name": char_name,
                        **char_info
                    })

            # 합성
            result = self.composite_scene(
                background_path=bg_path,
                characters=chars_for_scene,
                scene_id=scene_id,
                layout="auto"
            )

            results.append(result)

            if on_progress:
                on_progress(i + 1, total, result)

        # 로그 저장
        log_path = self.output_dir / "compositing_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        success_count = sum(1 for r in results if r.get("success"))
        print(f"\n합성 완료: {success_count}/{total} 성공\n")

        return results

    # ==================== AI 합성 메서드 ====================

    def composite_scene_with_ai(
        self,
        background_path: str,
        characters: List[Dict],
        scene: Dict,
        background_prompt: str = "",
        api_provider: str = "anthropic",
        remove_bg: bool = True,
        output_path: str = None
    ) -> Dict:
        """
        AI 분석 기반 씬 합성

        Args:
            background_path: 배경 이미지 경로 또는 URL
            characters: 캐릭터 정보 리스트
            scene: 씬 정보 (direction_guide, camera_suggestion 등 포함)
            background_prompt: 배경 생성에 사용된 프롬프트
            api_provider: AI 제공자 ("anthropic" 또는 "gemini")
            remove_bg: 캐릭터 배경 제거 여부
            output_path: 출력 경로

        Returns:
            합성 결과 딕셔너리
        """
        scene_id = scene.get("scene_id", 0)
        print(f"\n[SceneCompositor] AI 합성 모드 - 씬 {scene_id}")

        # AI 분석 수행
        analysis = self.ai_analyzer.analyze_composition(
            scene=scene,
            background_prompt=background_prompt,
            characters=characters,
            use_ai=True,
            api_provider=api_provider
        )

        if analysis:
            print(f"  씬 타입: {analysis.scene_type}")
            print(f"  카메라: {analysis.camera_angle}")
            print(f"  배치된 캐릭터: {len(analysis.character_placements)}명")
            for p in analysis.character_placements:
                print(f"    - {p.character_name}: ({p.position_x:.2f}, {p.position_y:.2f}), scale={p.scale:.2f}")
        else:
            print("  AI 분석 실패, 기본 합성으로 전환")
            return self.composite_scene_manual(
                background_path=background_path,
                characters=characters,
                scene_id=scene_id,
                remove_bg=remove_bg,
                output_path=output_path
            )

        # AI 배치 정보로 합성 수행
        return self._composite_with_placements(
            background_path=background_path,
            characters=characters,
            placements=analysis.character_placements,
            scene_id=scene_id,
            analysis=analysis,
            remove_bg=remove_bg,
            output_path=output_path
        )

    def composite_scene_manual(
        self,
        background_path: str,
        characters: List[Dict],
        scene_id: int,
        layout: str = "auto",
        remove_bg: bool = True,
        output_path: str = None
    ) -> Dict:
        """
        수동 레이아웃 기반 씬 합성 (기존 방식)

        Args:
            background_path: 배경 이미지 경로
            characters: 캐릭터 정보 리스트
            scene_id: 씬 ID
            layout: 레이아웃 (auto, single_center, dialogue, 등)
            remove_bg: 배경 제거 여부
            output_path: 출력 경로

        Returns:
            합성 결과
        """
        print(f"\n[SceneCompositor] 수동 합성 모드 - 씬 {scene_id}")

        # 기존 composite_scene 메서드 호출
        return self.composite_scene(
            background_path=background_path,
            characters=characters,
            scene_id=scene_id,
            layout=layout,
            remove_bg=remove_bg,
            output_path=output_path
        )

    def _composite_with_placements(
        self,
        background_path: str,
        characters: List[Dict],
        placements: List[CharacterPlacement],
        scene_id: int,
        analysis: CompositionAnalysis = None,
        remove_bg: bool = True,
        output_path: str = None
    ) -> Dict:
        """
        CharacterPlacement 객체들을 사용하여 합성

        Args:
            background_path: 배경 이미지 경로
            characters: 캐릭터 정보
            placements: AI 분석된 배치 정보
            scene_id: 씬 ID
            analysis: 전체 분석 결과
            remove_bg: 배경 제거 여부
            output_path: 출력 경로

        Returns:
            합성 결과
        """
        print(f"[SceneCompositor] 배치 정보 기반 합성 - 씬 {scene_id}")

        try:
            # 1. 배경 이미지 로드
            background = self._load_image(background_path)
            bg_width, bg_height = background.size
            print(f"  배경 크기: {bg_width}x{bg_height}")

            # 2. 결과 이미지 초기화
            result_image = background.copy()
            characters_used = []

            # 3. 캐릭터 이름 -> 이미지 정보 매핑
            char_map = {}
            for char in characters:
                char_name = char.get("name", "")
                if char_name and (char.get("image_path") or char.get("image_url")):
                    char_map[char_name] = char

            # 4. z_order 순으로 정렬 (낮은 것부터 = 뒤에서부터)
            sorted_placements = sorted(placements, key=lambda p: p.z_order)

            # 5. 각 캐릭터 합성
            for placement in sorted_placements:
                char_name = placement.character_name
                char_info = char_map.get(char_name)

                if not char_info:
                    print(f"  캐릭터 '{char_name}': 이미지 정보 없음, 스킵")
                    continue

                char_path = char_info.get("image_path") or char_info.get("image_url")
                if not char_path:
                    print(f"  캐릭터 '{char_name}': 이미지 경로 없음, 스킵")
                    continue

                print(f"  캐릭터 '{char_name}' 합성 중...")
                print(f"    위치: ({placement.position_x:.2f}, {placement.position_y:.2f})")
                print(f"    스케일: {placement.scale:.2f}")
                print(f"    플립: {placement.flip_horizontal}")
                print(f"    이유: {placement.reasoning[:50]}...")

                try:
                    # 캐릭터 이미지 로드
                    char_image = self._load_image(char_path)

                    # 배경 제거
                    if remove_bg:
                        char_image = self._remove_solid_background(char_image)

                    # 스케일 적용 (배경 높이 기준)
                    target_height = int(bg_height * placement.scale)
                    aspect = char_image.width / char_image.height
                    target_width = int(target_height * aspect)
                    char_image = char_image.resize((target_width, target_height), Image.LANCZOS)

                    # 좌우 반전
                    if placement.flip_horizontal:
                        char_image = char_image.transpose(Image.FLIP_LEFT_RIGHT)

                    # 위치 계산 (캐릭터 하단 중앙 기준)
                    x = int(placement.position_x * bg_width - char_image.width / 2)
                    y = int(placement.position_y * bg_height - char_image.height)

                    # 범위 체크
                    x = max(0, min(x, bg_width - char_image.width))
                    y = max(0, min(y, bg_height - char_image.height))

                    # 합성
                    result_image.paste(char_image, (x, y), char_image)
                    characters_used.append(char_name)

                    print(f"    -> 완료: ({x}, {y}), {target_width}x{target_height}")

                except Exception as e:
                    print(f"    -> 실패: {str(e)}")

            # 6. 저장
            if output_path is None:
                timestamp = int(time.time() * 1000)
                filename = f"scene_{scene_id:03d}_ai_composited_{timestamp}.png"
                output_path = str(self.output_dir / filename)

            result_image.save(output_path, "PNG")

            print(f"  AI 합성 완료! -> {output_path}")
            print(f"  사용된 캐릭터: {', '.join(characters_used)}")

            result = {
                "success": True,
                "scene_id": scene_id,
                "image_path": output_path,
                "image_url": output_path,
                "characters_used": characters_used,
                "is_composited": True,
                "composition_mode": "ai"
            }

            # 분석 정보 추가
            if analysis:
                result["scene_type"] = analysis.scene_type
                result["camera_angle"] = analysis.camera_angle
                result["composition_notes"] = analysis.composition_notes

            return result

        except Exception as e:
            print(f"  AI 합성 실패: {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                "success": False,
                "scene_id": scene_id,
                "is_composited": True,
                "composition_mode": "ai",
                "error": str(e)
            }

    def composite_all_scenes_with_ai(
        self,
        scenes: List[Dict],
        background_images: Dict[int, Dict],
        character_images: Dict[str, Dict],
        api_provider: str = "anthropic",
        on_progress=None
    ) -> List[Dict]:
        """
        모든 씬을 AI 분석 기반으로 합성

        Args:
            scenes: 씬 목록
            background_images: {scene_id: {"image_path": ..., "prompt": ...}}
            character_images: {character_name: {"image_path": ...}}
            api_provider: AI 제공자
            on_progress: 진행 콜백

        Returns:
            합성 결과 목록
        """
        results = []
        total = len(scenes)

        print(f"\n{'='*50}")
        print(f"AI 기반 씬 일괄 합성: {total}개 씬")
        print(f"{'='*50}\n")

        for i, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", i + 1)

            # 배경 이미지 확인
            bg_info = background_images.get(scene_id)
            if not bg_info:
                print(f"씬 {scene_id}: 배경 이미지 없음, 스킵")
                results.append({
                    "success": False,
                    "scene_id": scene_id,
                    "error": "배경 이미지 없음"
                })
                continue

            bg_path = bg_info.get("image_path") or bg_info.get("image_url")
            bg_prompt = bg_info.get("prompt", "")
            if not bg_path:
                continue

            # 씬에 등장하는 캐릭터 목록
            scene_char_names = scene.get("characters", [])

            # 캐릭터 정보 수집
            chars_for_scene = []
            for char_name in scene_char_names:
                char_info = character_images.get(char_name)
                if char_info and (char_info.get("image_path") or char_info.get("image_url")):
                    chars_for_scene.append({
                        "name": char_name,
                        **char_info
                    })

            # AI 합성
            result = self.composite_scene_with_ai(
                background_path=bg_path,
                characters=chars_for_scene,
                scene=scene,
                background_prompt=bg_prompt,
                api_provider=api_provider
            )

            results.append(result)

            if on_progress:
                on_progress(i + 1, total, result)

        # 로그 저장
        log_path = self.output_dir / "ai_compositing_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        success_count = sum(1 for r in results if r.get("success"))
        print(f"\nAI 합성 완료: {success_count}/{total} 성공\n")

        return results
