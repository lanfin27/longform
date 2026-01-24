# -*- coding: utf-8 -*-
"""
대표 캐릭터 관리 시스템

채널/영상의 시그니처 캐릭터를 관리합니다.
등장인물이 없는 설명형 콘텐츠에서 일관된 캐릭터를 사용할 수 있습니다.

주요 기능:
1. 대표 캐릭터 정의 (이름, 프롬프트, 스타일)
2. 기본 이미지 생성 (정면, 측면, 다양한 표정)
3. 씬별 액션 프롬프트 관리
4. 씬별 캐릭터 이미지 일괄 생성
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any


# ============================================================
# 데이터 모델
# ============================================================

@dataclass
class RepresentativeCharacter:
    """대표 캐릭터 데이터 모델"""

    # 기본 정보
    id: str
    name: str  # 캐릭터 이름 (예: "채널 MC 마루")
    description: str  # 간단한 설명

    # 프롬프트
    base_prompt: str  # 기본 캐릭터 프롬프트 (외모, 스타일 등)
    style_preset: str = "animation"  # 스타일 프리셋
    style_suffix: str = ""  # v1.1: 스타일 suffix 추가 (라이브러리 동기화용)
    negative_prompt: str = "text, watermark, low quality, blurry, deformed"

    # 생성된 기본 이미지
    base_images: Dict[str, str] = field(default_factory=dict)
    # {"front": "path/to/front.png", "left": "path/to/left.png", ...}

    # 메타데이터
    created_at: str = ""
    updated_at: str = ""
    is_active: bool = True

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'RepresentativeCharacter':
        # 필드 호환성 처리
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class SceneCharacterAction:
    """씬별 캐릭터 액션 데이터"""

    scene_num: int
    scene_content: str  # 씬 내용 (스크립트) - 요약본

    # AI가 분석한 액션 정보
    expression: str = ""  # 표정 (예: "밝은 미소", "놀란 표정")
    pose: str = ""  # 포즈 (예: "손으로 가리키는 자세")
    mood: str = ""  # 분위기 (예: "긴장", "밝음")
    props: List[str] = field(default_factory=list)  # 소품

    # 생성된 프롬프트
    action_prompt: str = ""  # 영어 액션 프롬프트
    full_prompt: str = ""  # 대표 캐릭터 + 액션 결합 프롬프트

    # 생성된 이미지
    generated_image_path: str = ""
    generation_status: str = "pending"  # pending, generating, completed, failed
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'SceneCharacterAction':
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        # props가 None이면 빈 리스트로
        if 'props' in filtered and filtered['props'] is None:
            filtered['props'] = []
        return cls(**filtered)


# ============================================================
# 스타일 프리셋
# ============================================================

STYLE_PRESETS = {
    "animation": {
        "name": "애니메이션 (Korean Webtoon)",
        "suffix": "Korean webtoon manhwa illustration style, flat colors with bold black outlines, clean digital art",
        "negative": "realistic, photorealistic, 3d render, photograph"
    },
    "realistic": {
        "name": "실사 (Realistic)",
        "suffix": "photorealistic, ultra detailed, professional photography, studio lighting",
        "negative": "cartoon, anime, drawing, illustration, painting"
    },
    "illustration": {
        "name": "일러스트 (Illustration)",
        "suffix": "digital illustration, vibrant colors, detailed artwork, professional illustration",
        "negative": "photo, realistic, 3d"
    },
    "cinematic": {
        "name": "시네마틱 (Cinematic)",
        "suffix": "cinematic lighting, dramatic, movie still, high quality, 4k",
        "negative": "cartoon, anime, low quality"
    },
    "minimal": {
        "name": "미니멀 (Minimal)",
        "suffix": "minimalist style, simple, clean design, white background",
        "negative": "complex, busy, cluttered"
    }
}

# 기본 이미지 타입 및 프롬프트 변형
BASE_IMAGE_TYPES = {
    "front": {
        "name": "정면 기본",
        "prompt_prefix": "front view, facing camera, looking at viewer, "
    },
    "left": {
        "name": "좌측면",
        "prompt_prefix": "side view from left, profile view, looking left, "
    },
    "right": {
        "name": "우측면",
        "prompt_prefix": "side view from right, profile view, looking right, "
    },
    "smile": {
        "name": "밝은 미소",
        "prompt_prefix": "front view, smiling happily, cheerful expression, warm smile, "
    },
    "serious": {
        "name": "진지한 표정",
        "prompt_prefix": "front view, serious expression, professional look, focused, "
    },
    "thinking": {
        "name": "생각하는 표정",
        "prompt_prefix": "front view, thinking expression, contemplative, hand on chin, "
    },
    "surprised": {
        "name": "놀란 표정",
        "prompt_prefix": "front view, surprised expression, wide eyes, amazed, "
    }
}


# ============================================================
# 매니저 클래스
# ============================================================

class RepresentativeCharacterManager:
    """대표 캐릭터 매니저"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.data_dir = self.project_path / "data"
        self.data_file = self.data_dir / "representative_character.json"
        self.images_folder = self.project_path / "images" / "representative_character"
        self.scene_images_folder = self.project_path / "images" / "character_scenes"

        # 디렉토리 생성
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_folder.mkdir(parents=True, exist_ok=True)
        self.scene_images_folder.mkdir(parents=True, exist_ok=True)

        self.character: Optional[RepresentativeCharacter] = None
        self.scene_actions: List[SceneCharacterAction] = []

        self._load()

    def _load(self):
        """저장된 데이터 로드"""
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                    if data.get("character"):
                        self.character = RepresentativeCharacter.from_dict(data["character"])

                    if data.get("scene_actions"):
                        self.scene_actions = [
                            SceneCharacterAction.from_dict(sa)
                            for sa in data["scene_actions"]
                        ]

                    print(f"[RepCharManager] 로드 완료: 캐릭터={bool(self.character)}, 액션={len(self.scene_actions)}개")

            except Exception as e:
                print(f"[RepCharManager] 로드 오류: {e}")
                self.character = None
                self.scene_actions = []

    def save(self):
        """데이터 저장"""
        try:
            data = {
                "character": self.character.to_dict() if self.character else None,
                "scene_actions": [sa.to_dict() for sa in self.scene_actions],
                "saved_at": datetime.now().isoformat()
            }

            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"[RepCharManager] 저장 완료")

        except Exception as e:
            print(f"[RepCharManager] 저장 오류: {e}")

    # ============================================================
    # 캐릭터 관리
    # ============================================================

    def set_character(self, character: RepresentativeCharacter):
        """대표 캐릭터 설정"""
        character.updated_at = datetime.now().isoformat()
        self.character = character
        self.save()

    def get_character(self) -> Optional[RepresentativeCharacter]:
        """대표 캐릭터 조회"""
        return self.character

    def has_character(self) -> bool:
        """대표 캐릭터 존재 여부"""
        return self.character is not None

    def delete_character(self):
        """대표 캐릭터 삭제"""
        self.character = None
        self.scene_actions = []
        self.save()

    def add_base_image(self, image_type: str, image_path: str):
        """기본 이미지 추가"""
        if self.character:
            self.character.base_images[image_type] = image_path
            self.character.updated_at = datetime.now().isoformat()
            self.save()

    # ============================================================
    # 씬별 액션 관리
    # ============================================================

    def set_scene_actions(self, actions: List[SceneCharacterAction]):
        """씬별 액션 설정"""
        self.scene_actions = actions
        self.save()

    def get_scene_actions(self) -> List[SceneCharacterAction]:
        """모든 씬 액션 조회"""
        return self.scene_actions

    def get_scene_action(self, scene_num: int) -> Optional[SceneCharacterAction]:
        """특정 씬 액션 조회"""
        for action in self.scene_actions:
            if action.scene_num == scene_num:
                return action
        return None

    def update_scene_action(self, scene_num: int, **kwargs) -> bool:
        """특정 씬 액션 업데이트"""
        for action in self.scene_actions:
            if action.scene_num == scene_num:
                for key, value in kwargs.items():
                    if hasattr(action, key):
                        setattr(action, key, value)
                self.save()
                return True
        return False

    def get_pending_actions(self) -> List[SceneCharacterAction]:
        """대기 중인 액션 목록"""
        return [a for a in self.scene_actions if a.generation_status == "pending"]

    def get_completed_actions(self) -> List[SceneCharacterAction]:
        """완료된 액션 목록"""
        return [a for a in self.scene_actions if a.generation_status == "completed"]

    def get_failed_actions(self) -> List[SceneCharacterAction]:
        """실패한 액션 목록"""
        return [a for a in self.scene_actions if a.generation_status == "failed"]

    # ============================================================
    # 프롬프트 빌더
    # ============================================================

    def build_full_prompt(
        self,
        action_prompt: str,
        include_style: bool = True
    ) -> str:
        """
        최종 이미지 생성 프롬프트 조합

        구조: [캐릭터 기본] + [액션] + [스타일]
        """
        if not self.character:
            return action_prompt

        parts = []

        # 캐릭터 기본 프롬프트
        if self.character.base_prompt:
            parts.append(self.character.base_prompt.strip().rstrip(','))

        # 액션 프롬프트
        if action_prompt:
            parts.append(action_prompt.strip().rstrip(','))

        # 스타일 suffix
        if include_style and self.character.style_preset in STYLE_PRESETS:
            style_suffix = STYLE_PRESETS[self.character.style_preset]["suffix"]
            parts.append(style_suffix)

        return ", ".join(parts)

    def get_negative_prompt(self) -> str:
        """네거티브 프롬프트 반환"""
        if not self.character:
            return ""

        negatives = []

        # 캐릭터 네거티브
        if self.character.negative_prompt:
            negatives.append(self.character.negative_prompt)

        # 스타일 네거티브
        if self.character.style_preset in STYLE_PRESETS:
            style_neg = STYLE_PRESETS[self.character.style_preset].get("negative", "")
            if style_neg:
                negatives.append(style_neg)

        return ", ".join(negatives)

    def get_base_image_prompt(self, image_type: str) -> str:
        """기본 이미지 타입별 프롬프트 생성"""
        if not self.character:
            return ""

        if image_type not in BASE_IMAGE_TYPES:
            return self.character.base_prompt

        prefix = BASE_IMAGE_TYPES[image_type]["prompt_prefix"]
        return self.build_full_prompt(prefix)

    # ============================================================
    # 통계
    # ============================================================

    def get_stats(self) -> Dict[str, Any]:
        """통계 정보"""
        return {
            "has_character": self.has_character(),
            "character_name": self.character.name if self.character else None,
            "base_images_count": len(self.character.base_images) if self.character else 0,
            "total_scenes": len(self.scene_actions),
            "pending": len(self.get_pending_actions()),
            "completed": len(self.get_completed_actions()),
            "failed": len(self.get_failed_actions())
        }


# ============================================================
# 헬퍼 함수
# ============================================================

def get_rep_char_manager(project_path: str) -> RepresentativeCharacterManager:
    """매니저 인스턴스 가져오기 (세션 캐시)"""
    import streamlit as st

    cache_key = f"rep_char_manager_{project_path}"

    if cache_key not in st.session_state:
        st.session_state[cache_key] = RepresentativeCharacterManager(project_path)

    return st.session_state[cache_key]


def clear_rep_char_manager(project_path: str):
    """매니저 캐시 제거"""
    import streamlit as st

    cache_key = f"rep_char_manager_{project_path}"
    if cache_key in st.session_state:
        del st.session_state[cache_key]
