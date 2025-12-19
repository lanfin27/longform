"""
프롬프트 프리셋 관리 시스템 - 고도화 버전

기능:
1. 스타일 CRUD (생성, 조회, 수정, 삭제)
2. 예시 이미지 관리
3. 이미지 기반 프롬프트 생성
4. 프리셋 내보내기/가져오기
"""
import json
import base64
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass, asdict, field


@dataclass
class StylePreset:
    """스타일 프리셋 데이터 클래스"""
    id: str
    name: str
    prompt: str
    category: str = "custom"
    description: str = ""
    example_images: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    is_default: bool = False

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()


class PromptPresetManager:
    """프롬프트 프리셋 관리자 - 고도화 버전"""

    DEFAULT_PRESETS = {
        "styles": [
            {
                "id": "animation",
                "name": "애니메이션 스타일",
                "prompt": "animation style, vibrant colors, clean lines, no text, simple background, smooth shading, anime-inspired illustration",
                "category": "styles",
                "description": "밝고 깔끔한 애니메이션 스타일. 선명한 윤곽선과 생동감 있는 색상이 특징입니다.",
                "tags": ["애니메이션", "컬러풀", "깔끔한"],
                "is_default": True
            },
            {
                "id": "3d_clay",
                "name": "3D 클레이 스타일",
                "prompt": "3D clay render style, soft lighting, pastel colors, cute chibi proportions, smooth surface, simple background, no text, studio lighting",
                "category": "styles",
                "description": "부드러운 점토 느낌의 3D 렌더링. 파스텔 톤과 귀여운 비율이 특징입니다.",
                "tags": ["3D", "클레이", "파스텔", "귀여운"],
                "is_default": True
            },
            {
                "id": "flat_illustration",
                "name": "플랫 일러스트",
                "prompt": "flat illustration style, minimal design, solid colors, geometric shapes, simple composition, vector art, no gradients, clean edges, no text",
                "category": "styles",
                "description": "미니멀한 플랫 디자인. 단순한 도형과 단색 사용이 특징입니다.",
                "tags": ["플랫", "미니멀", "벡터", "심플"],
                "is_default": True
            },
            {
                "id": "semoji_style",
                "name": "세모지 스타일",
                "prompt": "infographic animation style, educational illustration, clean simple lines, bright cheerful colors, solid background, professional quality, no text, informative visual, Korean YouTube style",
                "category": "styles",
                "description": "세상의 모든 지식 채널 스타일. 인포그래픽과 교육용 일러스트에 최적화되어 있습니다.",
                "tags": ["세모지", "인포그래픽", "교육", "유튜브"],
                "is_default": True
            },
            {
                "id": "pixel_art",
                "name": "픽셀아트",
                "prompt": "pixel art style, retro game aesthetic, 16-bit graphics, limited color palette, crisp pixels, nostalgic, no anti-aliasing",
                "category": "styles",
                "description": "레트로 게임 스타일의 픽셀아트. 16비트 게임 느낌이 특징입니다.",
                "tags": ["픽셀", "레트로", "게임", "8비트"],
                "is_default": True
            },
            {
                "id": "watercolor",
                "name": "수채화 스타일",
                "prompt": "watercolor painting style, soft edges, color bleeding, paper texture, artistic, delicate brushstrokes, pastel tones, dreamy atmosphere",
                "category": "styles",
                "description": "부드러운 수채화 느낌. 자연스러운 색 번짐과 종이 질감이 특징입니다.",
                "tags": ["수채화", "아트", "부드러운", "감성"],
                "is_default": True
            },
            {
                "id": "realistic_illustration",
                "name": "리얼리스틱 일러스트",
                "prompt": "realistic illustration, detailed digital art, cinematic lighting, professional quality, photorealistic elements, dramatic composition",
                "category": "styles",
                "description": "사실적인 디지털 일러스트. 영화적 조명과 디테일이 특징입니다.",
                "tags": ["리얼리스틱", "사실적", "시네마틱", "디테일"],
                "is_default": True
            }
        ],
        "characters": [
            {
                "id": "full_body",
                "name": "전신 캐릭터",
                "prompt": "full body character, standing pose, front view, simple solid color background, clear silhouette, visible from head to toe",
                "category": "characters",
                "description": "머리부터 발끝까지 보이는 전신 캐릭터. 기본 스탠딩 포즈입니다.",
                "tags": ["전신", "스탠딩", "정면"],
                "is_default": True
            },
            {
                "id": "half_body",
                "name": "상반신 캐릭터",
                "prompt": "upper body character, half body shot, portrait style, front view, simple background, focus on face and torso",
                "category": "characters",
                "description": "상반신만 보이는 캐릭터. 표정과 제스처에 집중합니다.",
                "tags": ["상반신", "포트레이트", "얼굴"],
                "is_default": True
            },
            {
                "id": "chibi",
                "name": "3등신 캐릭터",
                "prompt": "chibi style character, 3 head tall proportions, cute big head, small body, adorable, super deformed, kawaii",
                "category": "characters",
                "description": "귀여운 3등신 비율의 캐릭터. 머리가 크고 몸이 작습니다.",
                "tags": ["치비", "3등신", "귀여운", "SD"],
                "is_default": True
            },
            {
                "id": "icon_badge",
                "name": "아이콘/배지",
                "prompt": "icon style character, circular badge frame, portrait headshot, centered composition, clean edges, suitable for profile picture",
                "category": "characters",
                "description": "프로필 아이콘이나 배지 스타일. 원형 프레임에 얼굴이 들어갑니다.",
                "tags": ["아이콘", "배지", "프로필", "원형"],
                "is_default": True
            },
            {
                "id": "action_pose",
                "name": "액션 포즈",
                "prompt": "dynamic action pose, movement, energetic, dramatic angle, motion blur effect, exciting composition",
                "category": "characters",
                "description": "역동적인 액션 포즈. 움직임과 에너지가 느껴집니다.",
                "tags": ["액션", "다이나믹", "움직임"],
                "is_default": True
            }
        ],
        "backgrounds": [
            {
                "id": "news_desk",
                "name": "뉴스 데스크",
                "prompt": "professional news studio background, anchor desk, broadcast setting, multiple monitors showing graphics, blue lighting, modern design",
                "category": "backgrounds",
                "description": "뉴스 방송 스튜디오 배경. 앵커 데스크와 모니터가 있습니다.",
                "tags": ["뉴스", "스튜디오", "방송", "전문적"],
                "is_default": True
            },
            {
                "id": "office",
                "name": "사무실",
                "prompt": "modern office interior background, desk with computer, bookshelf, professional environment, natural lighting from window, clean organized space",
                "category": "backgrounds",
                "description": "현대적인 사무실 배경. 책상, 컴퓨터, 책장이 있습니다.",
                "tags": ["사무실", "오피스", "비즈니스", "현대적"],
                "is_default": True
            },
            {
                "id": "simple_gradient",
                "name": "단순 그라데이션",
                "prompt": "simple gradient background, smooth color transition, solid colors, minimal, clean, no distractions, professional",
                "category": "backgrounds",
                "description": "깔끔한 그라데이션 배경. 캐릭터에 집중할 수 있습니다.",
                "tags": ["그라데이션", "심플", "단색", "깔끔"],
                "is_default": True
            },
            {
                "id": "outdoor_city",
                "name": "도시 야외",
                "prompt": "urban outdoor background, city street, modern buildings, daytime, clear sky, busy metropolitan area",
                "category": "backgrounds",
                "description": "도시의 야외 배경. 건물과 거리가 보입니다.",
                "tags": ["도시", "야외", "거리", "건물"],
                "is_default": True
            },
            {
                "id": "nature",
                "name": "자연 배경",
                "prompt": "natural outdoor background, green trees, blue sky, peaceful atmosphere, park or forest setting, natural lighting",
                "category": "backgrounds",
                "description": "자연 속 배경. 나무와 하늘이 있는 평화로운 분위기입니다.",
                "tags": ["자연", "숲", "공원", "평화로운"],
                "is_default": True
            },
            {
                "id": "abstract",
                "name": "추상적 배경",
                "prompt": "abstract background, colorful shapes, modern art, geometric patterns, creative composition, artistic",
                "category": "backgrounds",
                "description": "추상적인 아트 배경. 다양한 도형과 색상이 특징입니다.",
                "tags": ["추상", "아트", "기하학", "모던"],
                "is_default": True
            }
        ],
        "negatives": [
            {
                "id": "no_text",
                "name": "텍스트 금지",
                "prompt": "no text, no words, no letters, no numbers, no watermark, no signature, no writing",
                "category": "negatives",
                "description": "이미지에 텍스트가 포함되지 않도록 합니다.",
                "tags": ["텍스트금지", "워터마크금지"],
                "is_default": True
            },
            {
                "id": "quality_negative",
                "name": "품질 네거티브",
                "prompt": "low quality, blurry, distorted, deformed, ugly, bad anatomy, bad proportions, extra limbs, cloned face, disfigured",
                "category": "negatives",
                "description": "저품질 결과물을 방지하는 네거티브 프롬프트입니다.",
                "tags": ["품질", "네거티브"],
                "is_default": True
            },
            {
                "id": "no_realistic",
                "name": "사실적 금지",
                "prompt": "no photorealistic, no photograph, no realistic, no real person, illustration only, drawn style only",
                "category": "negatives",
                "description": "사실적인 사진 스타일을 방지합니다.",
                "tags": ["사실적금지", "일러스트전용"],
                "is_default": True
            },
            {
                "id": "no_nsfw",
                "name": "성인 콘텐츠 금지",
                "prompt": "nsfw, nude, explicit, violence, gore, blood, inappropriate content",
                "category": "negatives",
                "description": "성인/폭력 콘텐츠를 방지합니다.",
                "tags": ["성인금지", "폭력금지"],
                "is_default": True
            }
        ],
        "compositions": [
            {
                "id": "centered",
                "name": "중앙 구도",
                "prompt": "centered composition, symmetrical, balanced, subject in center, stable framing",
                "category": "compositions",
                "description": "주제가 중앙에 위치하는 안정적인 구도입니다.",
                "tags": ["중앙", "대칭", "안정적"],
                "is_default": True
            },
            {
                "id": "rule_of_thirds",
                "name": "삼분할 구도",
                "prompt": "rule of thirds composition, dynamic placement, balanced asymmetry, professional framing",
                "category": "compositions",
                "description": "삼분할 법칙을 적용한 역동적인 구도입니다.",
                "tags": ["삼분할", "다이나믹", "프로페셔널"],
                "is_default": True
            },
            {
                "id": "wide_shot",
                "name": "와이드 샷",
                "prompt": "wide shot, full scene view, establishing shot, panoramic, environmental context",
                "category": "compositions",
                "description": "넓은 장면을 보여주는 와이드 샷입니다.",
                "tags": ["와이드", "파노라마", "전경"],
                "is_default": True
            },
            {
                "id": "close_up",
                "name": "클로즈업",
                "prompt": "close up shot, detailed focus, intimate framing, emphasis on subject, shallow depth of field",
                "category": "compositions",
                "description": "주제에 가까이 다가간 클로즈업 샷입니다.",
                "tags": ["클로즈업", "디테일", "집중"],
                "is_default": True
            }
        ]
    }

    def __init__(self, project_path: str = None):
        if project_path:
            self.base_dir = Path(project_path) / "presets"
        else:
            self.base_dir = Path("data/presets")

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.presets_file = self.base_dir / "presets.json"
        self.images_dir = self.base_dir / "images"
        self.images_dir.mkdir(exist_ok=True)

        self.presets: Dict[str, List[StylePreset]] = {}
        self._load_presets()

    def _load_presets(self):
        """프리셋 로드"""
        if self.presets_file.exists():
            try:
                with open(self.presets_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for category, presets in data.items():
                    self.presets[category] = []
                    for p in presets:
                        if isinstance(p, dict):
                            if "example_images" not in p:
                                p["example_images"] = []
                            if "tags" not in p:
                                p["tags"] = []
                            if "is_default" not in p:
                                p["is_default"] = False
                            self.presets[category].append(StylePreset(**p))
            except (json.JSONDecodeError, TypeError):
                self._init_default_presets()
        else:
            self._init_default_presets()

    def _init_default_presets(self):
        """기본 프리셋 초기화"""
        for category, presets in self.DEFAULT_PRESETS.items():
            self.presets[category] = []
            for p in presets:
                preset = StylePreset(
                    id=p["id"],
                    name=p["name"],
                    prompt=p["prompt"],
                    category=p.get("category", category),
                    description=p.get("description", ""),
                    tags=p.get("tags", []),
                    is_default=p.get("is_default", True)
                )
                self.presets[category].append(preset)

        self._save_presets()

    def _save_presets(self):
        """프리셋 저장"""
        data = {}
        for category, presets in self.presets.items():
            data[category] = [asdict(p) for p in presets]

        with open(self.presets_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # === CRUD 메서드 ===

    def get_all_categories(self) -> List[str]:
        """모든 카테고리 목록"""
        return list(self.presets.keys())

    def get_all_presets(self) -> List[StylePreset]:
        """모든 프리셋 반환"""
        all_presets = []
        for category in self.presets.values():
            all_presets.extend(category)
        return all_presets

    def get_presets_by_category(self, category: str) -> List[StylePreset]:
        """카테고리별 프리셋 조회"""
        return self.presets.get(category, [])

    def get_preset(self, preset_id: str) -> Optional[StylePreset]:
        """ID로 프리셋 조회"""
        for category in self.presets.values():
            for preset in category:
                if preset.id == preset_id:
                    return preset
        return None

    def add_preset(self, preset: StylePreset = None, **kwargs) -> StylePreset:
        """프리셋 추가 (StylePreset 객체 또는 키워드 인자)"""
        # 키워드 인자로 호출된 경우 StylePreset 생성
        if preset is None and kwargs:
            import uuid
            preset_id = kwargs.get("id", str(uuid.uuid4())[:8])
            preset = StylePreset(
                id=preset_id,
                name=kwargs.get("name", ""),
                prompt=kwargs.get("prompt", ""),
                category=kwargs.get("category", "custom"),
                description=kwargs.get("description", ""),
                example_images=kwargs.get("example_images", []),
                tags=kwargs.get("tags", []),
                is_default=False
            )

        category = preset.category
        if category not in self.presets:
            self.presets[category] = []

        existing_ids = [p.id for p in self.presets[category]]
        if preset.id in existing_ids:
            preset.id = f"{preset.id}_{len(existing_ids)}"

        preset.created_at = datetime.now().isoformat()
        preset.updated_at = datetime.now().isoformat()

        self.presets[category].append(preset)
        self._save_presets()
        return preset

    def update_preset(self, preset_id: str, updates: Dict = None, **kwargs) -> Optional[StylePreset]:
        """프리셋 수정 (dict 또는 키워드 인자)"""
        # 키워드 인자 지원
        if updates is None:
            updates = kwargs

        for category in self.presets.values():
            for i, preset in enumerate(category):
                if preset.id == preset_id:
                    if preset.is_default:
                        allowed_fields = ["prompt", "description", "example_images", "tags"]
                        updates = {k: v for k, v in updates.items() if k in allowed_fields}

                    for key, value in updates.items():
                        if hasattr(preset, key):
                            setattr(preset, key, value)

                    preset.updated_at = datetime.now().isoformat()
                    self._save_presets()
                    return preset
        return None

    def delete_preset(self, preset_id: str) -> bool:
        """프리셋 삭제 (기본 프리셋은 삭제 불가)"""
        for category in self.presets.values():
            for i, preset in enumerate(category):
                if preset.id == preset_id:
                    if preset.is_default:
                        return False
                    category.pop(i)
                    self._save_presets()
                    return True
        return False

    # === 예시 이미지 관리 ===

    def add_example_image(self, preset_id: str, image_path: str) -> bool:
        """프리셋에 예시 이미지 추가"""
        preset = self.get_preset(preset_id)
        if preset:
            if image_path not in preset.example_images:
                preset.example_images.append(image_path)
                self._save_presets()
            return True
        return False

    def remove_example_image(self, preset_id: str, image_path: str) -> bool:
        """프리셋에서 예시 이미지 제거"""
        preset = self.get_preset(preset_id)
        if preset and image_path in preset.example_images:
            preset.example_images.remove(image_path)
            self._save_presets()
            return True
        return False

    def save_uploaded_image(self, preset_id: str, uploaded_file) -> str:
        """업로드된 이미지 저장"""
        filename = f"{preset_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        save_path = self.images_dir / filename

        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        return str(save_path)

    # === 이미지 기반 프롬프트 생성 ===

    def generate_prompt_from_image(self, image_path: str, style_hint: str = "") -> str:
        """
        이미지를 분석하여 프롬프트 생성 (Claude Vision 사용)
        """
        from anthropic import Anthropic
        from config.settings import ANTHROPIC_API_KEY

        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        ext = Path(image_path).suffix.lower()
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }.get(ext, "image/png")

        prompt_text = f"""
이 이미지의 스타일을 분석하여 이미지 생성 AI (FLUX, Midjourney 등)에서 사용할 수 있는 영문 프롬프트를 생성해주세요.

{f'스타일 힌트: {style_hint}' if style_hint else ''}

다음 요소들을 포함해주세요:
1. 아트 스타일 (예: animation, 3D render, watercolor 등)
2. 색상 특징 (예: vibrant colors, pastel tones 등)
3. 선 스타일 (예: clean lines, soft edges 등)
4. 조명/분위기 (예: soft lighting, dramatic shadows 등)
5. 특수 효과나 기법 (있다면)

프롬프트만 출력해주세요. 설명은 필요 없습니다.
프롬프트는 쉼표로 구분된 영어 키워드 형태로 작성해주세요.
예시: "animation style, vibrant colors, clean lines, simple background, no text"
"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt_text
                        }
                    ]
                }
            ]
        )

        return response.content[0].text.strip()

    # === 유틸리티 ===

    def combine_presets(self, preset_ids: List[str]) -> str:
        """여러 프리셋 조합"""
        prompts = []
        for pid in preset_ids:
            preset = self.get_preset(pid)
            if preset:
                prompts.append(preset.prompt)
        return ", ".join(prompts)

    def search_presets(self, query: str) -> List[StylePreset]:
        """프리셋 검색 (이름, 설명, 태그)"""
        results = []
        query_lower = query.lower()

        for category in self.presets.values():
            for preset in category:
                if (query_lower in preset.name.lower() or
                    query_lower in preset.description.lower() or
                    any(query_lower in tag.lower() for tag in preset.tags)):
                    results.append(preset)

        return results

    def export_presets(self, filepath: str = None) -> Dict:
        """프리셋 내보내기 (파일 또는 dict 반환)"""
        data = {}
        for category, presets in self.presets.items():
            data[category] = [asdict(p) for p in presets]

        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        return data

    def import_presets(self, data_or_filepath, overwrite: bool = False) -> int:
        """프리셋 가져오기 (dict 또는 파일 경로)"""
        # dict인 경우 직접 사용, 문자열인 경우 파일 로드
        if isinstance(data_or_filepath, dict):
            data = data_or_filepath
        else:
            with open(data_or_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

        imported_count = 0
        for category, presets in data.items():
            if category not in self.presets:
                self.presets[category] = []

            for p in presets:
                existing = self.get_preset(p.get("id", ""))
                if existing and not overwrite:
                    continue

                preset = StylePreset(**p)
                preset.is_default = False

                if existing and overwrite:
                    self.update_preset(existing.id, asdict(preset))
                else:
                    self.presets[category].append(preset)
                imported_count += 1

        self._save_presets()
        return imported_count

    # === 호환성을 위한 레거시 메서드 ===

    def get_style_options(self) -> List[tuple]:
        """스타일 선택 옵션 (Streamlit selectbox용)"""
        styles = self.get_presets_by_category("styles")
        return [(s.name, s.prompt) for s in styles]

    def get_character_options(self) -> List[tuple]:
        """캐릭터 스타일 선택 옵션"""
        chars = self.get_presets_by_category("characters")
        return [(c.name, c.prompt) for c in chars]

    def get_background_options(self) -> List[tuple]:
        """배경 선택 옵션"""
        bgs = self.get_presets_by_category("backgrounds")
        return [(b.name, b.prompt) for b in bgs]

    def get_negative_options(self) -> List[tuple]:
        """네거티브 프롬프트 옵션"""
        negs = self.get_presets_by_category("negatives")
        return [(n.name, n.prompt) for n in negs]

    def build_full_prompt(
        self,
        style_id: str = None,
        character_id: str = None,
        background_id: str = None,
        custom_prompt: str = "",
        negative_ids: List[str] = None
    ) -> Dict[str, str]:
        """전체 프롬프트 빌드"""
        positive_parts = []
        negative_parts = []

        if style_id:
            style = self.get_preset(style_id)
            if style:
                positive_parts.append(style.prompt)

        if character_id:
            char = self.get_preset(character_id)
            if char:
                positive_parts.append(char.prompt)

        if background_id:
            bg = self.get_preset(background_id)
            if bg:
                positive_parts.append(bg.prompt)

        if custom_prompt:
            positive_parts.append(custom_prompt)

        if negative_ids:
            for neg_id in negative_ids:
                neg = self.get_preset(neg_id)
                if neg:
                    negative_parts.append(neg.prompt)

        return {
            "positive": ", ".join(positive_parts),
            "negative": ", ".join(negative_parts)
        }
