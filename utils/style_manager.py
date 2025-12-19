"""
스타일 관리 시스템 - 실시간 동기화 버전

핵심:
1. 싱글톤 제거 - 매번 파일에서 로드
2. 함수 기반 API - 간단하고 명확
3. 항상 최신 데이터 보장
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Style:
    """스타일 정의"""
    id: str
    name: str
    name_ko: str
    segment: str
    prompt_prefix: str = ""
    prompt_suffix: str = ""
    negative_prompt: str = ""
    description: str = ""
    preview_image: str = ""
    created_at: str = ""
    updated_at: str = ""
    is_default: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Style":
        return cls(
            id=data.get('id', ''),
            name=data.get('name', ''),
            name_ko=data.get('name_ko', ''),
            segment=data.get('segment', ''),
            prompt_prefix=data.get('prompt_prefix', ''),
            prompt_suffix=data.get('prompt_suffix', ''),
            negative_prompt=data.get('negative_prompt', ''),
            description=data.get('description', ''),
            preview_image=data.get('preview_image', ''),
            created_at=data.get('created_at', ''),
            updated_at=data.get('updated_at', ''),
            is_default=data.get('is_default', False)
        )


# ========================================
# 상수
# ========================================

SEGMENTS = {
    "character": {
        "name": "캐릭터 스타일",
        "icon": "👤",
        "description": "캐릭터 이미지 생성에 사용"
    },
    "background": {
        "name": "배경 스타일",
        "icon": "🖼️",
        "description": "배경 이미지 생성에 사용"
    },
    "scene_composite": {
        "name": "씬 합성 스타일",
        "icon": "🎬",
        "description": "씬 기반 이미지 생성에 사용"
    }
}


# ========================================
# 내부 함수
# ========================================

def _get_storage_path() -> str:
    """스타일 저장 파일 경로"""
    base_dir = Path(__file__).parent.parent
    return str(base_dir / "data" / "styles.json")


def _get_default_styles() -> Dict[str, List[dict]]:
    """기본 스타일 데이터"""
    return {
        "character": [
            {
                "id": "char_animation",
                "name": "Animation",
                "name_ko": "애니메이션",
                "segment": "character",
                "prompt_prefix": "animation style character, full body,",
                "prompt_suffix": "standing pose, simple solid gray background",
                "negative_prompt": "complex background, realistic",
                "description": "깔끔한 애니메이션 캐릭터",
                "is_default": True
            },
            {
                "id": "char_realistic",
                "name": "Realistic",
                "name_ko": "실사",
                "segment": "character",
                "prompt_prefix": "photorealistic portrait,",
                "prompt_suffix": "professional studio lighting, high detail",
                "negative_prompt": "cartoon, anime, drawing",
                "description": "실사 스타일의 캐릭터",
                "is_default": False
            },
            {
                "id": "char_illustration",
                "name": "Illustration",
                "name_ko": "일러스트",
                "segment": "character",
                "prompt_prefix": "digital illustration character,",
                "prompt_suffix": "detailed artwork, vibrant colors",
                "negative_prompt": "photo, 3d render",
                "description": "디지털 일러스트레이션 스타일",
                "is_default": False
            },
            {
                "id": "char_minimal",
                "name": "Minimal",
                "name_ko": "미니멀",
                "segment": "character",
                "prompt_prefix": "minimalist character design,",
                "prompt_suffix": "simple shapes, limited palette, clean",
                "negative_prompt": "complex, detailed, realistic",
                "description": "간결한 미니멀 스타일",
                "is_default": False
            }
        ],
        "background": [
            {
                "id": "bg_animation",
                "name": "Animation",
                "name_ko": "애니메이션",
                "segment": "background",
                "prompt_prefix": "animation style background,",
                "prompt_suffix": "vibrant colors, cinematic composition, no characters",
                "negative_prompt": "people, characters, realistic",
                "description": "애니메이션 스타일의 배경",
                "is_default": True
            },
            {
                "id": "bg_realistic",
                "name": "Realistic",
                "name_ko": "실사",
                "segment": "background",
                "prompt_prefix": "photorealistic environment,",
                "prompt_suffix": "natural lighting, detailed scenery, cinematic",
                "negative_prompt": "cartoon, anime, people",
                "description": "실사 스타일의 배경",
                "is_default": False
            },
            {
                "id": "bg_painterly",
                "name": "Painterly",
                "name_ko": "페인터리",
                "segment": "background",
                "prompt_prefix": "painterly background, digital painting,",
                "prompt_suffix": "impressionistic, artistic, atmospheric",
                "negative_prompt": "photo, sharp, characters",
                "description": "회화적인 배경 스타일",
                "is_default": False
            },
            {
                "id": "bg_infographic",
                "name": "Infographic",
                "name_ko": "인포그래픽",
                "segment": "background",
                "prompt_prefix": "infographic style background,",
                "prompt_suffix": "modern design, clean visuals, minimal",
                "negative_prompt": "realistic, complex, people",
                "description": "인포그래픽 스타일의 배경",
                "is_default": False
            }
        ],
        "scene_composite": [
            {
                "id": "scene_animation",
                "name": "Animation",
                "name_ko": "애니메이션",
                "segment": "scene_composite",
                "prompt_prefix": "animation style scene,",
                "prompt_suffix": "vibrant colors, clean composition, cinematic",
                "negative_prompt": "realistic, photo",
                "description": "애니메이션 스타일의 씬",
                "is_default": True
            },
            {
                "id": "scene_realistic",
                "name": "Realistic",
                "name_ko": "실사",
                "segment": "scene_composite",
                "prompt_prefix": "photorealistic scene,",
                "prompt_suffix": "natural lighting, cinematic, high detail",
                "negative_prompt": "cartoon, anime, drawing",
                "description": "실사 스타일의 씬",
                "is_default": False
            },
            {
                "id": "scene_cinematic",
                "name": "Cinematic",
                "name_ko": "시네마틱",
                "segment": "scene_composite",
                "prompt_prefix": "cinematic scene, movie still,",
                "prompt_suffix": "dramatic lighting, film grain, widescreen",
                "negative_prompt": "cartoon, flat",
                "description": "영화적인 시네마틱 스타일",
                "is_default": False
            },
            {
                "id": "scene_illustration",
                "name": "Illustration",
                "name_ko": "일러스트",
                "segment": "scene_composite",
                "prompt_prefix": "illustrated scene,",
                "prompt_suffix": "detailed artwork, vivid colors, professional",
                "negative_prompt": "photo, 3d",
                "description": "일러스트레이션 스타일의 씬",
                "is_default": False
            }
        ]
    }


def _ensure_file_exists():
    """파일이 없으면 기본값으로 생성"""
    storage_path = _get_storage_path()

    if not os.path.exists(storage_path):
        print(f"[StyleManager] 파일 없음 → 기본 스타일 생성: {storage_path}")
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)

        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(_get_default_styles(), f, ensure_ascii=False, indent=2)


def _load_all_data() -> Dict[str, List[dict]]:
    """파일에서 전체 데이터 로드"""
    _ensure_file_exists()
    storage_path = _get_storage_path()

    try:
        with open(storage_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[StyleManager] 로드 오류: {e}")
        return _get_default_styles()


def _save_all_data(data: Dict[str, List[dict]]) -> bool:
    """전체 데이터를 파일에 저장"""
    storage_path = _get_storage_path()

    try:
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)

        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        total = sum(len(styles) for styles in data.values())
        print(f"[StyleManager] ✅ 저장 완료: {storage_path} ({total}개 스타일)")
        return True

    except Exception as e:
        print(f"[StyleManager] ❌ 저장 실패: {e}")
        return False


# ========================================
# 공개 함수 API
# ========================================

def load_all_styles() -> Dict[str, List[Style]]:
    """
    모든 스타일 로드 (항상 파일에서 읽음)

    Returns:
        {segment: [Style, ...]}
    """
    data = _load_all_data()

    result = {
        "character": [],
        "background": [],
        "scene_composite": []
    }

    for segment in result.keys():
        if segment in data:
            for style_data in data[segment]:
                try:
                    result[segment].append(Style.from_dict(style_data))
                except Exception as e:
                    print(f"[StyleManager] 스타일 파싱 오류: {e}")

    return result


def get_styles_by_segment(segment: str) -> List[Style]:
    """
    세그먼트별 스타일 목록 (매번 파일에서 로드)

    Args:
        segment: "character", "background", "scene_composite"

    Returns:
        스타일 목록
    """
    all_styles = load_all_styles()
    return all_styles.get(segment, [])


def get_style_by_id(style_id: str) -> Optional[Style]:
    """ID로 스타일 찾기"""
    all_styles = load_all_styles()

    for styles in all_styles.values():
        for style in styles:
            if style.id == style_id:
                return style

    return None


def get_default_style(segment: str) -> Optional[Style]:
    """세그먼트의 기본 스타일 반환"""
    styles = get_styles_by_segment(segment)

    for style in styles:
        if style.is_default:
            return style

    return styles[0] if styles else None


def add_style(style: Style) -> bool:
    """
    스타일 추가

    Args:
        style: 추가할 Style 객체

    Returns:
        성공 여부
    """
    data = _load_all_data()

    segment = style.segment
    if segment not in data:
        data[segment] = []

    # 중복 ID 체크
    for s in data[segment]:
        if s.get('id') == style.id:
            print(f"[StyleManager] 중복 ID: {style.id}")
            return False

    # 타임스탬프
    now = datetime.now().isoformat()
    style.created_at = now
    style.updated_at = now

    # 추가
    data[segment].append(style.to_dict())

    # 저장
    if _save_all_data(data):
        print(f"[StyleManager] ✅ 스타일 추가됨: {style.name_ko} ({style.id})")
        return True

    return False


def update_style(style_id: str, updates: dict) -> bool:
    """
    스타일 수정

    Args:
        style_id: 수정할 스타일 ID
        updates: 수정할 필드들

    Returns:
        성공 여부
    """
    data = _load_all_data()

    found = False
    for segment, styles in data.items():
        if not isinstance(styles, list):
            continue

        for style in styles:
            if style.get('id') == style_id:
                for key, value in updates.items():
                    if key not in ['id', 'segment']:
                        style[key] = value
                style['updated_at'] = datetime.now().isoformat()
                found = True
                break

        if found:
            break

    if not found:
        print(f"[StyleManager] 스타일 찾지 못함: {style_id}")
        return False

    if _save_all_data(data):
        print(f"[StyleManager] ✅ 스타일 수정됨: {style_id}")
        return True

    return False


def delete_style(style_id: str) -> bool:
    """
    스타일 삭제 (기본 스타일 제외)

    Args:
        style_id: 삭제할 스타일 ID

    Returns:
        성공 여부
    """
    data = _load_all_data()

    deleted = False
    deleted_name = ""

    for segment, styles in data.items():
        if not isinstance(styles, list):
            continue

        for i, style in enumerate(styles):
            if style.get('id') == style_id:
                if style.get('is_default'):
                    print(f"[StyleManager] 기본 스타일은 삭제 불가: {style_id}")
                    return False

                deleted_name = style.get('name_ko', style_id)
                styles.pop(i)
                deleted = True
                break

        if deleted:
            break

    if not deleted:
        print(f"[StyleManager] 스타일 찾지 못함: {style_id}")
        return False

    if _save_all_data(data):
        print(f"[StyleManager] ✅ 스타일 삭제됨: {deleted_name}")
        return True

    return False


def set_default_style(style_id: str) -> bool:
    """
    기본 스타일 설정

    Args:
        style_id: 기본으로 설정할 스타일 ID

    Returns:
        성공 여부
    """
    data = _load_all_data()

    # 대상 스타일의 세그먼트 찾기
    target_segment = None
    for segment, styles in data.items():
        if not isinstance(styles, list):
            continue
        for style in styles:
            if style.get('id') == style_id:
                target_segment = segment
                break
        if target_segment:
            break

    if not target_segment:
        print(f"[StyleManager] 스타일 찾지 못함: {style_id}")
        return False

    # 해당 세그먼트의 모든 스타일 기본값 해제, 대상만 설정
    for style in data[target_segment]:
        style['is_default'] = (style.get('id') == style_id)

    if _save_all_data(data):
        print(f"[StyleManager] ✅ 기본 스타일 설정됨: {style_id}")
        return True

    return False


def build_prompt(style: Style, base_prompt: str) -> str:
    """
    스타일 적용 프롬프트 생성

    Args:
        style: 적용할 스타일
        base_prompt: 기본 프롬프트

    Returns:
        조합된 프롬프트
    """
    parts = []

    if style.prompt_prefix:
        parts.append(style.prompt_prefix.strip())

    if base_prompt:
        parts.append(base_prompt.strip())

    if style.prompt_suffix:
        parts.append(style.prompt_suffix.strip())

    return " ".join(parts)


def get_segment_info(segment: str) -> Optional[Dict]:
    """세그먼트 정보 반환"""
    return SEGMENTS.get(segment)


def get_all_segments() -> List[str]:
    """모든 세그먼트 목록"""
    return list(SEGMENTS.keys())


# ========================================
# 호환성을 위한 클래스 래퍼
# ========================================

class StyleManager:
    """
    호환성을 위한 클래스 래퍼

    기존 코드에서 StyleManager 클래스를 사용하는 경우를 위해 유지.
    내부적으로는 모두 함수를 호출함.
    """

    SEGMENTS = SEGMENTS

    def __init__(self, project_path: str = None):
        # 아무것도 캐시하지 않음
        self._project_path = project_path

    @property
    def storage_path(self):
        return _get_storage_path()

    def get_styles_by_segment(self, segment: str) -> List[Style]:
        return get_styles_by_segment(segment)

    def get_style_by_id(self, style_id: str) -> Optional[Style]:
        return get_style_by_id(style_id)

    def get_default_style(self, segment: str) -> Optional[Style]:
        return get_default_style(segment)

    def add_style(self, style: Style) -> bool:
        return add_style(style)

    def update_style(self, style_id: str, updates: dict) -> bool:
        return update_style(style_id, updates)

    def delete_style(self, style_id: str) -> bool:
        return delete_style(style_id)

    def set_default_style(self, style_id: str) -> bool:
        return set_default_style(style_id)

    def build_prompt(self, style: Style, base_prompt: str) -> str:
        return build_prompt(style, base_prompt)

    def get_segment_info(self, segment: str) -> Optional[Dict]:
        return get_segment_info(segment)

    def get_all_segments(self) -> List[str]:
        return get_all_segments()


def get_style_manager(project_path: str = None) -> StyleManager:
    """
    StyleManager 인스턴스 반환

    매번 새 인스턴스 생성 (캐시 없음)
    """
    return StyleManager(project_path)


def invalidate_style_cache():
    """
    스타일 캐시 무효화

    더 이상 캐시가 없으므로 아무것도 하지 않음.
    호환성을 위해 유지.
    """
    print("[StyleManager] 캐시 무효화 호출됨 (캐시 없음, 무시)")
