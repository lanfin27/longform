# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/scene_status.py
씬 처리 상태 정의 (v1.0)

5단계 워크플로우에서 각 씬의 처리 상태를 정의합니다.
"""

from enum import Enum
from typing import Dict, Any


class SceneStatus(Enum):
    """씬 처리 상태 열거형"""
    PENDING = "pending"                      # 미처리
    STEP1_KOREAN_TEXT = "step1_korean_text"  # Step 1 완료 (한글 텍스트)
    STEP2_CHARACTER = "step2_character"      # Step 2 완료 (캐릭터 합성)
    STEP3_REALSHOT = "step3_realshot"        # Step 3 완료 (실사 이미지)
    STEP4_VIDEO = "step4_video"              # Step 4 완료 (비디오)
    STEP5_INFOGRAPHIC = "step5_infographic"  # Step 5 완료 (인포그래픽)
    EXCLUDED = "excluded"                    # 수동 제외
    COMPLETED = "completed"                  # 처리 완료


# 상태별 설정
SCENE_STATUS_CONFIG: Dict[SceneStatus, Dict[str, Any]] = {
    SceneStatus.PENDING: {
        "label": "대기",
        "emoji": "⏳",
        "color": "#6B7280",
        "bg_color": "#6B728020",
        "description": "아직 처리되지 않은 씬",
        "step": 0
    },
    SceneStatus.STEP1_KOREAN_TEXT: {
        "label": "한글 텍스트",
        "emoji": "🔤",
        "color": "#3B82F6",
        "bg_color": "#3B82F620",
        "description": "한글 텍스트 씬으로 대체됨",
        "step": 1
    },
    SceneStatus.STEP2_CHARACTER: {
        "label": "캐릭터 합성",
        "emoji": "🎭",
        "color": "#F59E0B",
        "bg_color": "#F59E0B20",
        "description": "배경+캐릭터 합성됨",
        "step": 2
    },
    SceneStatus.STEP3_REALSHOT: {
        "label": "실사 이미지",
        "emoji": "📷",
        "color": "#10B981",
        "bg_color": "#10B98120",
        "description": "실사 이미지로 대체됨",
        "step": 3
    },
    SceneStatus.STEP4_VIDEO: {
        "label": "비디오",
        "emoji": "🎬",
        "color": "#EF4444",
        "bg_color": "#EF444420",
        "description": "비디오로 대체됨",
        "step": 4
    },
    SceneStatus.STEP5_INFOGRAPHIC: {
        "label": "인포그래픽",
        "emoji": "📊",
        "color": "#8B5CF6",
        "bg_color": "#8B5CF620",
        "description": "인포그래픽으로 대체됨",
        "step": 5
    },
    SceneStatus.EXCLUDED: {
        "label": "제외됨",
        "emoji": "❌",
        "color": "#9CA3AF",
        "bg_color": "#9CA3AF20",
        "description": "워크플로우에서 제외됨",
        "step": -1
    },
    SceneStatus.COMPLETED: {
        "label": "완료",
        "emoji": "✅",
        "color": "#059669",
        "bg_color": "#05966920",
        "description": "처리 완료",
        "step": 99
    }
}


# Step 정보
STEP_CONFIG = {
    1: {
        "name": "한글 텍스트 씬",
        "emoji": "🔤",
        "color": "#3B82F6",
        "description": "한글 텍스트가 포함된 씬",
        "unit": "bundle",  # 묶음 단위 처리
        "status": SceneStatus.STEP1_KOREAN_TEXT
    },
    2: {
        "name": "캐릭터 합성",
        "emoji": "🎭",
        "color": "#F59E0B",
        "description": "배경+캐릭터 합성",
        "unit": "bundle",  # 묶음 단위 처리
        "status": SceneStatus.STEP2_CHARACTER
    },
    3: {
        "name": "실사 이미지",
        "emoji": "📷",
        "color": "#10B981",
        "description": "실사 이미지로 대체",
        "unit": "scene_with_prefix",  # 씬 단위 + Prefix 규칙
        "status": SceneStatus.STEP3_REALSHOT
    },
    4: {
        "name": "비디오",
        "emoji": "🎬",
        "color": "#EF4444",
        "description": "비디오로 대체 (≤4초)",
        "unit": "bundle",  # 묶음 단위 처리
        "status": SceneStatus.STEP4_VIDEO
    },
    5: {
        "name": "인포그래픽",
        "emoji": "📊",
        "color": "#8B5CF6",
        "description": "인포그래픽으로 대체",
        "unit": "scene",  # 씬 단위 처리
        "status": SceneStatus.STEP5_INFOGRAPHIC
    }
}


def get_status_from_string(status_str: str) -> SceneStatus:
    """문자열에서 SceneStatus 반환"""
    try:
        return SceneStatus(status_str)
    except ValueError:
        return SceneStatus.PENDING


def get_status_config(status: SceneStatus) -> Dict[str, Any]:
    """상태별 설정 반환"""
    return SCENE_STATUS_CONFIG.get(status, SCENE_STATUS_CONFIG[SceneStatus.PENDING])


def get_step_config(step: int) -> Dict[str, Any]:
    """Step별 설정 반환"""
    return STEP_CONFIG.get(step, {})


def get_status_badge_html(status: SceneStatus) -> str:
    """상태 배지 HTML 반환"""
    config = get_status_config(status)
    return f"""<span style="
        background: {config['bg_color']};
        color: {config['color']};
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        border: 1px solid {config['color']}40;
    ">{config['emoji']} {config['label']}</span>"""
