"""
스타일 관리 시스템 - 실시간 동기화 버전

핵심:
1. 싱글톤 제거 - 매번 파일에서 로드
2. 함수 기반 API - 간단하고 명확
3. 항상 최신 데이터 보장
4. 세션 스테이트 기반 캐시 무효화 (v2.1)
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

# Streamlit 세션 스테이트 (Streamlit 외부에서 실행 시 None)
try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False
    st = None

# 캐시 무효화 키
_STYLE_CACHE_VERSION_KEY = "_style_cache_version"


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
    },
    "infographic": {
        "name": "인포그래픽 스타일",
        "icon": "📊",
        "description": "인포그래픽용 이미지 생성에 사용 (모서리/가장자리 배치)"
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
    """기본 스타일 데이터 (v2.2: 텍스트 차단 강화)"""

    # 공통 텍스트 차단 네거티브 프롬프트
    TEXT_BLOCK_NEGATIVE = (
        "text, words, letters, writing, typography, signs, signage, logos, labels, "
        "captions, titles, subtitles, banners, watermarks, stamps, seals, inscriptions, "
        "Korean text, hangul, Japanese text, Chinese text, kanji, hiragana, katakana, "
        "CJK characters, Asian script, any script"
    )

    return {
        "character": [
            {
                "id": "char_animation",
                "name": "Animation",
                "name_ko": "애니메이션",
                "segment": "character",
                "prompt_prefix": "animation style character, full body,",
                "prompt_suffix": "standing pose, simple solid gray background, no text or signs",
                "negative_prompt": f"complex background, realistic, {TEXT_BLOCK_NEGATIVE}",
                "description": "깔끔한 애니메이션 캐릭터",
                "is_default": True
            },
            {
                "id": "char_realistic",
                "name": "Realistic",
                "name_ko": "실사",
                "segment": "character",
                "prompt_prefix": "photorealistic portrait,",
                "prompt_suffix": "professional studio lighting, high detail, clean background",
                "negative_prompt": f"cartoon, anime, drawing, {TEXT_BLOCK_NEGATIVE}",
                "description": "실사 스타일의 캐릭터",
                "is_default": False
            },
            {
                "id": "char_illustration",
                "name": "Illustration",
                "name_ko": "일러스트",
                "segment": "character",
                "prompt_prefix": "digital illustration character,",
                "prompt_suffix": "detailed artwork, vibrant colors, blank background",
                "negative_prompt": f"photo, 3d render, {TEXT_BLOCK_NEGATIVE}",
                "description": "디지털 일러스트레이션 스타일",
                "is_default": False
            },
            {
                "id": "char_minimal",
                "name": "Minimal",
                "name_ko": "미니멀",
                "segment": "character",
                "prompt_prefix": "minimalist character design,",
                "prompt_suffix": "simple shapes, limited palette, clean, no decorations",
                "negative_prompt": f"complex, detailed, realistic, {TEXT_BLOCK_NEGATIVE}",
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
                "prompt_prefix": "animation style background, blank surfaces,",
                "prompt_suffix": "vibrant colors, cinematic composition, no characters, no signage",
                "negative_prompt": f"people, characters, realistic, {TEXT_BLOCK_NEGATIVE}",
                "description": "애니메이션 스타일의 배경",
                "is_default": True
            },
            {
                "id": "bg_realistic",
                "name": "Realistic",
                "name_ko": "실사",
                "segment": "background",
                "prompt_prefix": "photorealistic environment, clean surfaces,",
                "prompt_suffix": "natural lighting, detailed scenery, cinematic, no visible text",
                "negative_prompt": f"cartoon, anime, people, {TEXT_BLOCK_NEGATIVE}",
                "description": "실사 스타일의 배경",
                "is_default": False
            },
            {
                "id": "bg_painterly",
                "name": "Painterly",
                "name_ko": "페인터리",
                "segment": "background",
                "prompt_prefix": "painterly background, digital painting,",
                "prompt_suffix": "impressionistic, artistic, atmospheric, unmarked surfaces",
                "negative_prompt": f"photo, sharp, characters, {TEXT_BLOCK_NEGATIVE}",
                "description": "회화적인 배경 스타일",
                "is_default": False
            },
            {
                "id": "bg_infographic",
                "name": "Infographic",
                "name_ko": "인포그래픽",
                "segment": "background",
                "prompt_prefix": "infographic style background, clean design, blank center,",
                "prompt_suffix": "modern design, clean visuals, minimal, blank areas for overlay, no built-in labels",
                "negative_prompt": f"realistic, complex, people, {TEXT_BLOCK_NEGATIVE}",
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
                "prompt_prefix": "animation style scene, blank surfaces without text,",
                "prompt_suffix": "vibrant colors, clean composition, cinematic, no signs or writing",
                "negative_prompt": f"realistic, photo, {TEXT_BLOCK_NEGATIVE}",
                "description": "애니메이션 스타일의 씬",
                "is_default": True
            },
            {
                "id": "scene_realistic",
                "name": "Realistic",
                "name_ko": "실사",
                "segment": "scene_composite",
                "prompt_prefix": "photorealistic scene, clean environment,",
                "prompt_suffix": "natural lighting, cinematic, high detail, no visible text or signs",
                "negative_prompt": f"cartoon, anime, drawing, {TEXT_BLOCK_NEGATIVE}",
                "description": "실사 스타일의 씬",
                "is_default": False
            },
            {
                "id": "scene_cinematic",
                "name": "Cinematic",
                "name_ko": "시네마틱",
                "segment": "scene_composite",
                "prompt_prefix": "cinematic scene, movie still, unmarked surfaces,",
                "prompt_suffix": "dramatic lighting, film grain, widescreen, no text overlays",
                "negative_prompt": f"cartoon, flat, {TEXT_BLOCK_NEGATIVE}",
                "description": "영화적인 시네마틱 스타일",
                "is_default": False
            },
            {
                "id": "scene_illustration",
                "name": "Illustration",
                "name_ko": "일러스트",
                "segment": "scene_composite",
                "prompt_prefix": "illustrated scene, clean artwork,",
                "prompt_suffix": "detailed artwork, vivid colors, professional, no text elements",
                "negative_prompt": f"photo, 3d, {TEXT_BLOCK_NEGATIVE}",
                "description": "일러스트레이션 스타일의 씬",
                "is_default": False
            }
        ],
        "infographic": [
            {
                "id": "infographic_minimal",
                "name": "Minimal",
                "name_ko": "미니멀",
                "segment": "infographic",
                "prompt_prefix": "minimal clean design, simple geometric shapes, flat colors, modern aesthetic, blank center,",
                "prompt_suffix": "professional infographic background, edge-focused decorative elements, space for text overlay, no built-in text",
                "negative_prompt": f"cluttered, busy, complex patterns, realistic photo, centered subject, {TEXT_BLOCK_NEGATIVE}",
                "description": "깔끔하고 단순한 인포그래픽 배경",
                "is_default": True
            },
            {
                "id": "infographic_corporate",
                "name": "Corporate",
                "name_ko": "비즈니스",
                "segment": "infographic",
                "prompt_prefix": "corporate business style, professional, clean lines, blue and gray tones, unmarked surfaces,",
                "prompt_suffix": "business presentation background, modern office aesthetic, subtle gradients, no labels",
                "negative_prompt": f"casual, playful, bright colors, cartoon, centered elements, {TEXT_BLOCK_NEGATIVE}",
                "description": "비즈니스/기업용 인포그래픽 배경",
                "is_default": False
            },
            {
                "id": "infographic_creative",
                "name": "Creative",
                "name_ko": "크리에이티브",
                "segment": "infographic",
                "prompt_prefix": "creative dynamic style, colorful abstract shapes, artistic elements, vibrant, blank areas,",
                "prompt_suffix": "creative infographic background, artistic flair, modern design, no writing",
                "negative_prompt": f"boring, monochrome, corporate, plain, centered focus, {TEXT_BLOCK_NEGATIVE}",
                "description": "창의적이고 역동적인 인포그래픽 배경",
                "is_default": False
            },
            {
                "id": "infographic_tech",
                "name": "Tech",
                "name_ko": "테크/IT",
                "segment": "infographic",
                "prompt_prefix": "technology style, digital elements, circuit patterns, futuristic, neon accents, abstract,",
                "prompt_suffix": "tech infographic background, cyber aesthetic, modern digital design, no text overlays",
                "negative_prompt": f"organic, natural, vintage, rustic, centered elements, {TEXT_BLOCK_NEGATIVE}",
                "description": "기술/IT 관련 인포그래픽 배경",
                "is_default": False
            },
            {
                "id": "infographic_education",
                "name": "Education",
                "name_ko": "교육/학습",
                "segment": "infographic",
                "prompt_prefix": "educational style, books, learning icons, friendly approachable design, warm colors, blank center,",
                "prompt_suffix": "educational infographic background, school theme, knowledge elements, no visible text",
                "negative_prompt": f"dark, scary, complex, corporate, centered subject, {TEXT_BLOCK_NEGATIVE}",
                "description": "교육/학습 콘텐츠용 인포그래픽 배경",
                "is_default": False
            },
            {
                "id": "infographic_webtoon",
                "name": "Webtoon",
                "name_ko": "웹툰/만화",
                "segment": "infographic",
                "prompt_prefix": "Korean webtoon manhwa style, comic illustration, bold outlines, cel shading, blank speech bubbles,",
                "prompt_suffix": "webtoon style infographic background, cartoon aesthetic, manga influence, no text",
                "negative_prompt": f"realistic, photo, 3D render, dark, cluttered center, {TEXT_BLOCK_NEGATIVE}",
                "description": "웹툰/만화 스타일 인포그래픽 배경",
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

    print(f"[StyleManager] _save_all_data 시작")
    print(f"[StyleManager] 저장 경로: {storage_path}")

    try:
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)

        # 저장 전 파일 크기
        before_size = os.path.getsize(storage_path) if os.path.exists(storage_path) else 0

        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 저장 후 파일 크기
        after_size = os.path.getsize(storage_path)

        total = sum(len(styles) for styles in data.values())
        print(f"[StyleManager] ✅ 저장 완료: {storage_path}")
        print(f"[StyleManager]   - 스타일 수: {total}개")
        print(f"[StyleManager]   - 파일 크기: {before_size} → {after_size} bytes")
        return True

    except PermissionError as e:
        print(f"[StyleManager] ❌ 권한 오류 - 파일 쓰기 불가: {e}")
        import traceback
        traceback.print_exc()
        return False

    except Exception as e:
        print(f"[StyleManager] ❌ 저장 실패: {e}")
        import traceback
        traceback.print_exc()
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

    # ✅ 모든 세그먼트 포함 (infographic 추가)
    result = {
        "character": [],
        "background": [],
        "scene_composite": [],
        "infographic": []
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


def get_style_by_id_in_segment(style_id: str, segment: str) -> Optional[Style]:
    """
    특정 세그먼트에서 ID로 스타일 찾기

    같은 ID가 여러 세그먼트에 존재할 수 있으므로, 특정 세그먼트에서만 찾을 때 사용.

    Args:
        style_id: 스타일 ID
        segment: 세그먼트 (character, background, scene_composite, infographic)

    Returns:
        Style 객체 또는 None
    """
    styles = get_styles_by_segment(segment)

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


def add_style(style: Style) -> tuple:
    """
    스타일 추가

    Args:
        style: 추가할 Style 객체

    Returns:
        (성공 여부, 메시지)
    """
    data = _load_all_data()

    segment = style.segment

    # 세그먼트 유효성 검사
    if segment not in SEGMENTS:
        msg = f"유효하지 않은 세그먼트: {segment}. 허용: {list(SEGMENTS.keys())}"
        print(f"[StyleManager] ❌ {msg}")
        return False, msg

    if segment not in data:
        data[segment] = []

    # ID 유효성 검사
    if not style.id or not style.id.strip():
        msg = "스타일 ID가 비어있습니다."
        print(f"[StyleManager] ❌ {msg}")
        return False, msg

    # 중복 ID 체크
    for s in data[segment]:
        if s.get('id') == style.id:
            msg = f"중복 ID: '{style.id}' (세그먼트: {segment})"
            print(f"[StyleManager] ❌ {msg}")
            return False, msg

    # 타임스탬프
    now = datetime.now().isoformat()
    style.created_at = now
    style.updated_at = now

    # 추가
    data[segment].append(style.to_dict())

    # 저장
    if _save_all_data(data):
        msg = f"스타일 추가 성공: {style.name_ko} (ID: {style.id})"
        print(f"[StyleManager] ✅ {msg}")
        return True, msg

    msg = "파일 저장 실패"
    print(f"[StyleManager] ❌ {msg}")
    return False, msg


def update_style(style_id: str, updates: dict, target_segment: str = None) -> bool:
    """
    스타일 수정

    Args:
        style_id: 수정할 스타일 ID
        updates: 수정할 필드들
        target_segment: 수정할 세그먼트 (None이면 첫 번째 발견된 것 수정)
                       ⭐ 같은 ID가 여러 세그먼트에 있을 때 필수!

    Returns:
        성공 여부
    """
    print(f"\n{'='*60}")
    print(f"[StyleManager] update_style 시작")
    print(f"[StyleManager] style_id: {style_id}")
    print(f"[StyleManager] target_segment: {target_segment}")  # ⭐ 세그먼트 로그 추가
    print(f"[StyleManager] updates keys: {list(updates.keys())}")
    for key, value in updates.items():
        preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
        print(f"[StyleManager]   {key}: {preview}")
    print(f"{'='*60}")

    data = _load_all_data()
    print(f"[StyleManager] 로드된 세그먼트: {list(data.keys())}")

    # 같은 ID가 여러 세그먼트에 있는지 확인
    found_in_segments = []
    for seg, styles_list in data.items():
        if isinstance(styles_list, list):
            for s in styles_list:
                if s.get('id') == style_id:
                    found_in_segments.append(seg)

    if len(found_in_segments) > 1:
        print(f"[StyleManager] ⚠️ 같은 ID가 여러 세그먼트에 존재: {found_in_segments}")
        if target_segment:
            print(f"[StyleManager] → target_segment={target_segment} 사용")
        else:
            print(f"[StyleManager] → target_segment 미지정, 첫 번째({found_in_segments[0]}) 수정")

    found = False
    found_segment = None

    # target_segment가 지정된 경우 해당 세그먼트만 검색
    segments_to_search = [target_segment] if target_segment else data.keys()

    for segment in segments_to_search:
        if segment not in data:
            continue

        styles = data[segment]
        if not isinstance(styles, list):
            continue

        for style in styles:
            if style.get('id') == style_id:
                print(f"[StyleManager] ✅ 스타일 발견: {segment}/{style_id}")
                print(f"[StyleManager] 수정 전 prompt_prefix: {style.get('prompt_prefix', '')[:30]}...")

                for key, value in updates.items():
                    if key not in ['id', 'segment']:
                        style[key] = value
                style['updated_at'] = datetime.now().isoformat()
                found = True
                found_segment = segment

                print(f"[StyleManager] 수정 후 prompt_prefix: {style.get('prompt_prefix', '')[:30]}...")
                break

        if found:
            break

    if not found:
        print(f"[StyleManager] ❌ 스타일 찾지 못함: {style_id}")
        # 모든 스타일 ID 출력
        all_ids = []
        for seg, styles_list in data.items():
            if isinstance(styles_list, list):
                for s in styles_list:
                    all_ids.append(f"{seg}/{s.get('id', '?')}")
        print(f"[StyleManager] 사용 가능한 스타일: {all_ids}")
        return False

    # 저장
    save_result = _save_all_data(data)
    if save_result:
        print(f"[StyleManager] ✅ 스타일 수정 완료: {style_id}")

        # 검증: 다시 읽어서 확인
        verify_data = _load_all_data()
        for style in verify_data.get(found_segment, []):
            if style.get('id') == style_id:
                saved_prefix = style.get('prompt_prefix', '')[:30]
                print(f"[StyleManager] 검증 - 저장된 prompt_prefix: {saved_prefix}...")
                break

        return True

    print(f"[StyleManager] ❌ 저장 실패")
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

    def get_style_by_id_in_segment(self, style_id: str, segment: str) -> Optional[Style]:
        """특정 세그먼트에서 ID로 스타일 찾기"""
        return get_style_by_id_in_segment(style_id, segment)

    def get_default_style(self, segment: str) -> Optional[Style]:
        return get_default_style(segment)

    def add_style(self, style: Style) -> tuple:
        """스타일 추가 - (성공여부, 메시지) 반환"""
        return add_style(style)

    def update_style(self, style_id: str, updates: dict, target_segment: str = None) -> bool:
        """스타일 수정 - target_segment로 특정 세그먼트 지정 가능"""
        return update_style(style_id, updates, target_segment)

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
    스타일 캐시 무효화 (v2.2)

    세션 스테이트의 스타일 관련 캐시를 무효화합니다.
    다른 페이지에서 스타일 변경을 감지할 수 있도록 버전을 갱신합니다.

    v2.2: 더 포괄적인 패턴 + 파일 mtime 기반 검증
    """
    if not _HAS_STREAMLIT:
        print("[StyleManager] Streamlit 없음 - 캐시 무효화 스킵")
        return

    try:
        # 버전 업데이트 (타임스탬프 기반)
        new_version = time.time()
        st.session_state[_STYLE_CACHE_VERSION_KEY] = new_version

        # 파일 mtime도 저장 (파일 기반 검증용)
        storage_path = _get_storage_path()
        if os.path.exists(storage_path):
            st.session_state["_style_file_mtime"] = os.path.getmtime(storage_path)

        # 스타일 관련 세션 키 클리어 (v2.2: 더 포괄적인 패턴)
        # 모든 스타일 관련 위젯 키를 클리어
        keys_to_clear = []
        for key in list(st.session_state.keys()):
            # 스타일 선택 관련 키 찾기
            if any(pattern in key.lower() for pattern in [
                'selected_style',      # selected_style_*
                'style_select',        # style_select*
                'bg_style',            # bg_style_* (배경 스타일)
                'scene_style',         # scene_style_* (씬 스타일)
                'char_style',          # char_style_* (캐릭터 스타일)
                'composite_style',     # composite_style_* (합성 스타일)
                'infographic_style',   # infographic_style_* (인포그래픽 스타일)
                '_style_radio',        # *_style_radio
                '_style_selectbox',    # *_style_selectbox
                'style_radio',         # style_radio_*
                'style_selectbox',     # style_selectbox_*
            ]):
                keys_to_clear.append(key)

        for key in keys_to_clear:
            del st.session_state[key]

        print(f"[StyleManager] ✅ 캐시 무효화 완료 (버전: {new_version:.2f}, 클리어된 키: {len(keys_to_clear)}개)")
        if keys_to_clear:
            print(f"[StyleManager] 클리어된 키: {keys_to_clear[:10]}{'...' if len(keys_to_clear) > 10 else ''}")

    except Exception as e:
        print(f"[StyleManager] 캐시 무효화 오류: {e}")


def get_style_cache_version() -> float:
    """
    현재 스타일 캐시 버전 조회

    Returns:
        캐시 버전 (타임스탬프). 없으면 0.0
    """
    if not _HAS_STREAMLIT:
        return 0.0

    try:
        return st.session_state.get(_STYLE_CACHE_VERSION_KEY, 0.0)
    except Exception:
        return 0.0


def check_and_clear_stale_style_cache(page_key: str = "default", clear_keys: bool = True) -> bool:
    """
    스타일 캐시가 변경되었는지 확인하고 필요시 로컬 캐시 클리어 (v2.2)

    각 페이지에서 호출하여 스타일 변경 감지

    v2.2: 파일 mtime 기반 추가 검증 + 세션 키 클리어 옵션

    Args:
        page_key: 페이지 고유 키
        clear_keys: True면 스타일 관련 세션 키도 클리어 (기본: True)

    Returns:
        True if cache was invalidated (스타일이 변경됨)
    """
    if not _HAS_STREAMLIT:
        return False

    try:
        is_stale = False

        # 1. 버전 기반 체크
        current_version = get_style_cache_version()
        last_seen_key = f"_style_version_seen_{page_key}"
        last_seen = st.session_state.get(last_seen_key, 0.0)

        if current_version > last_seen:
            is_stale = True
            st.session_state[last_seen_key] = current_version

        # 2. 파일 mtime 기반 체크 (추가 안전장치)
        storage_path = _get_storage_path()
        if os.path.exists(storage_path):
            file_mtime = os.path.getmtime(storage_path)
            last_mtime_key = f"_style_file_mtime_seen_{page_key}"
            last_mtime = st.session_state.get(last_mtime_key, 0.0)

            if file_mtime > last_mtime:
                is_stale = True
                st.session_state[last_mtime_key] = file_mtime

        if is_stale:
            # ⭐ v2.3: 실제 파일 변경 시에만 로그 출력 (첫 방문은 제외)
            if last_seen > 0 or last_mtime > 0:
                print(f"[StyleManager] 📢 스타일 변경 감지 (페이지: {page_key})")
            else:
                # 첫 방문 시에는 로그 출력 안함
                pass

            # 스타일 관련 세션 키 클리어 (요청 시)
            if clear_keys:
                keys_to_clear = []
                for key in list(st.session_state.keys()):
                    if any(pattern in key.lower() for pattern in [
                        'selected_style',
                        'style_select',
                        'bg_style',
                        'scene_style',
                        'char_style',
                        'composite_style',
                        'infographic_style',
                        '_style_radio',
                        '_style_selectbox',
                        'style_radio',
                        'style_selectbox',
                    ]):
                        # 버전 관련 키는 제외
                        if '_version_seen_' not in key and '_mtime_seen_' not in key:
                            keys_to_clear.append(key)

                for key in keys_to_clear:
                    try:
                        del st.session_state[key]
                    except Exception:
                        pass

                if keys_to_clear:
                    print(f"[StyleManager] 클리어된 키 ({page_key}): {len(keys_to_clear)}개")

            return True

        return False
    except Exception as e:
        print(f"[StyleManager] 캐시 체크 오류: {e}")
        return False


# ========================================
# 씬 합성 스타일 헬퍼 함수 (Problem 60)
# ========================================

def get_scene_composite_styles() -> List[Style]:
    """
    씬 합성 스타일 목록 반환

    Returns:
        씬 합성 스타일 Style 객체 리스트
    """
    return get_styles_by_segment("scene_composite")


def get_scene_composite_style_by_name(name: str) -> Optional[Style]:
    """
    이름으로 씬 합성 스타일 조회

    Args:
        name: 스타일 이름 (한글 또는 영문)

    Returns:
        Style 객체 또는 None
    """
    styles = get_scene_composite_styles()

    for style in styles:
        if style.name_ko == name or style.name == name or style.id == name:
            return style

    return None


def get_default_scene_composite_style() -> Optional[Style]:
    """기본 씬 합성 스타일 반환"""
    return get_default_style("scene_composite")


def build_scene_composite_prompt(
    scene_prompt: str,
    style: Style,
    include_negative: bool = True
) -> Dict[str, str]:
    """
    씬 합성 프롬프트 조합

    Args:
        scene_prompt: 씬별 이미지 프롬프트
        style: 씬 합성 스타일 Style 객체
        include_negative: 네거티브 프롬프트 포함 여부

    Returns:
        {
            "positive": "Prefix + scene_prompt + Suffix",
            "negative": "negative prompt..."
        }
    """
    prefix = style.prompt_prefix.strip() if style.prompt_prefix else ""
    suffix = style.prompt_suffix.strip() if style.prompt_suffix else ""
    negative = style.negative_prompt.strip() if style.negative_prompt else ""

    # 프롬프트 조합
    parts = []

    if prefix:
        parts.append(prefix.rstrip(",").strip())

    if scene_prompt:
        parts.append(scene_prompt.strip())

    if suffix:
        parts.append(suffix.lstrip(",").strip())

    positive_prompt = ", ".join(filter(None, parts))

    return {
        "positive": positive_prompt,
        "negative": negative if include_negative else ""
    }
