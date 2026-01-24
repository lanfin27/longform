# -*- coding: utf-8 -*-
"""
utils/pipeline_state.py
씬 타입 변환 파이프라인 상태 관리

AI 소모량 최소화를 위한 순차적 소거 방식 파이프라인:
1. 실사이미지 대체 (AI 소모: 낮음)
2. 인포그래픽 대체 (AI 소모: 중간)
3. 캐릭터 합성 (AI 소모: 중간)
4. 비디오 변환 (AI 소모: 높음)

각 단계에서 이전 단계 결과를 제외하여 다음 단계의 모집단을 축소합니다.

작성: 2025-01
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Set, Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime
from pathlib import Path


class PipelineStep(Enum):
    """파이프라인 단계"""
    INITIAL = "initial"              # 초기 상태
    REAL_IMAGE = "real_image"        # Step 1: 실사이미지 대체
    INFOGRAPHIC = "infographic"      # Step 2: 인포그래픽 대체
    CHARACTER = "character"          # Step 3: 캐릭터 합성
    VIDEO = "video"                  # Step 4: 비디오 변환
    COMPLETED = "completed"          # 완료


# 단계별 AI 소모량 정보
STEP_CONFIG = {
    PipelineStep.REAL_IMAGE: {
        "name": "실사이미지 대체",
        "emoji": "📷",
        "color": "#10B981",
        "ai_cost": 1,  # 낮음
        "ai_cost_label": "⚡ 낮음",
        "description": "스톡 이미지로 대체 가능한 씬",
        "excludes_from_next": True
    },
    PipelineStep.INFOGRAPHIC: {
        "name": "인포그래픽 대체",
        "emoji": "📊",
        "color": "#8B5CF6",
        "ai_cost": 2,  # 중간
        "ai_cost_label": "⚡⚡ 중간",
        "description": "데이터/통계/프로세스 시각화 씬",
        "excludes_from_next": True
    },
    PipelineStep.CHARACTER: {
        "name": "캐릭터 합성",
        "emoji": "🎭",
        "color": "#F59E0B",
        "ai_cost": 2,  # 중간
        "ai_cost_label": "⚡⚡ 중간",
        "description": "대표 캐릭터 오버레이 (모든 타입 대상)",
        "excludes_from_next": False  # 다른 타입과 병행 가능
    },
    PipelineStep.VIDEO: {
        "name": "비디오 변환",
        "emoji": "🎬",
        "color": "#EF4444",
        "ai_cost": 3,  # 높음
        "ai_cost_label": "⚡⚡⚡ 높음",
        "description": "이미지→비디오 생성 (가장 비용 높음)",
        "excludes_from_next": True
    }
}


@dataclass
class StepResult:
    """단계 처리 결과"""
    step: PipelineStep
    processed_scenes: Set[int] = field(default_factory=set)
    skipped_scenes: Set[int] = field(default_factory=set)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "step": self.step.value,
            "processed_scenes": list(self.processed_scenes),
            "skipped_scenes": list(self.skipped_scenes),
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'StepResult':
        return cls(
            step=PipelineStep(data.get("step", "initial")),
            processed_scenes=set(data.get("processed_scenes", [])),
            skipped_scenes=set(data.get("skipped_scenes", [])),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at")
        )


@dataclass
class PipelineState:
    """파이프라인 상태 관리"""

    # 전체 씬 풀
    total_scenes: Set[int] = field(default_factory=set)

    # 한글텍스트 씬 (기존, 파이프라인 제외)
    korean_text_scenes: Set[int] = field(default_factory=set)

    # 각 단계별 결과
    real_image_scenes: Set[int] = field(default_factory=set)
    infographic_scenes: Set[int] = field(default_factory=set)
    video_scenes: Set[int] = field(default_factory=set)
    character_composite_scenes: Set[int] = field(default_factory=set)

    # 현재 단계
    current_step: PipelineStep = PipelineStep.INITIAL

    # 단계별 결과 기록
    step_results: Dict[str, StepResult] = field(default_factory=dict)

    # Step 1 상세 정보 (우선 대상 기능)
    step1_details: Dict = field(default_factory=lambda: {
        'priority_bundle': set(),      # 묶음 대표 씬
        'priority_korean': set(),      # 한글 텍스트 씬
        'priority_total': set(),       # 1차 대상 합계
        'ai_recommended': set(),       # AI 추천 씬
        'final_targets': set()         # 최종 대상
    })

    # 타임스탬프
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    def initialize_from_scenes(self, scenes: List[Dict]):
        """씬 데이터에서 초기화"""
        self.total_scenes = set()
        self.korean_text_scenes = set()

        for i, scene in enumerate(scenes):
            scene_id = scene.get('scene_id') or scene.get('id', i + 1)
            self.total_scenes.add(scene_id)

            # 한글 텍스트 씬 감지
            korean_prompt = scene.get('image_prompt_korean_text', '')
            if korean_prompt and korean_prompt.strip():
                self.korean_text_scenes.add(scene_id)

        self.current_step = PipelineStep.REAL_IMAGE
        self.updated_at = datetime.now().isoformat()

        print(f"[Pipeline] 초기화: 전체 {len(self.total_scenes)}개, 한글텍스트 {len(self.korean_text_scenes)}개")

    def get_base_pool(self) -> Set[int]:
        """기본 처리 풀 (한글텍스트 제외)"""
        return self.total_scenes - self.korean_text_scenes

    def get_remaining_pool(self, step: PipelineStep) -> Set[int]:
        """
        특정 단계에서 처리 가능한 씬 풀 반환 (소거법 적용)

        핵심 로직:
        - Step 1 (실사이미지): 전체 - 한글텍스트
        - Step 2 (인포그래픽): 전체 - 한글텍스트 - 실사이미지
        - Step 3 (캐릭터): 전체 - 한글텍스트 (모든 타입 대상)
        - Step 4 (비디오): 전체 - 한글텍스트 - 실사이미지 - 인포그래픽
        """
        base_pool = self.get_base_pool()

        if step == PipelineStep.REAL_IMAGE:
            # Step 1: 전체 씬 (한글텍스트만 제외)
            return base_pool

        elif step == PipelineStep.INFOGRAPHIC:
            # Step 2: 실사이미지 제외
            return base_pool - self.real_image_scenes

        elif step == PipelineStep.CHARACTER:
            # Step 3: 모든 완성된 씬 대상 (한글텍스트만 제외)
            # 캐릭터 합성은 다른 타입과 병행 가능
            return base_pool

        elif step == PipelineStep.VIDEO:
            # Step 4: 실사이미지 + 인포그래픽 제외 (가장 좁은 풀)
            return base_pool - self.real_image_scenes - self.infographic_scenes

        return base_pool

    def get_pool_reduction_info(self, step: PipelineStep) -> Dict:
        """단계별 풀 축소 정보 반환"""
        base_pool = self.get_base_pool()
        remaining_pool = self.get_remaining_pool(step)

        excluded = base_pool - remaining_pool
        reduction_rate = len(excluded) / len(base_pool) * 100 if base_pool else 0

        # 어떤 타입이 제외되었는지
        excluded_types = []
        if step in [PipelineStep.INFOGRAPHIC, PipelineStep.VIDEO]:
            if self.real_image_scenes:
                excluded_types.append(f"📷 실사이미지 {len(self.real_image_scenes)}개")
        if step == PipelineStep.VIDEO:
            if self.infographic_scenes:
                excluded_types.append(f"📊 인포그래픽 {len(self.infographic_scenes)}개")

        return {
            "base_count": len(base_pool),
            "remaining_count": len(remaining_pool),
            "excluded_count": len(excluded),
            "reduction_rate": reduction_rate,
            "excluded_types": excluded_types
        }

    def get_normal_image_scenes(self) -> Set[int]:
        """일반 이미지 씬 반환 (모든 특수 타입 제외)"""
        return (
            self.total_scenes
            - self.korean_text_scenes
            - self.real_image_scenes
            - self.infographic_scenes
            - self.video_scenes
        )

    def mark_step_complete(self, step: PipelineStep, processed: Set[int]):
        """단계 완료 표시"""
        now = datetime.now().isoformat()

        if step == PipelineStep.REAL_IMAGE:
            self.real_image_scenes = processed
            self.current_step = PipelineStep.INFOGRAPHIC
        elif step == PipelineStep.INFOGRAPHIC:
            self.infographic_scenes = processed
            self.current_step = PipelineStep.CHARACTER
        elif step == PipelineStep.CHARACTER:
            self.character_composite_scenes = processed
            self.current_step = PipelineStep.VIDEO
        elif step == PipelineStep.VIDEO:
            self.video_scenes = processed
            self.current_step = PipelineStep.COMPLETED

        # 결과 기록
        self.step_results[step.value] = StepResult(
            step=step,
            processed_scenes=processed,
            completed_at=now
        )

        self.updated_at = now
        print(f"[Pipeline] {step.value} 완료: {len(processed)}개 처리")

    def add_to_step(self, step: PipelineStep, scene_ids: Set[int]):
        """특정 단계에 씬 추가"""
        if step == PipelineStep.REAL_IMAGE:
            self.real_image_scenes.update(scene_ids)
        elif step == PipelineStep.INFOGRAPHIC:
            self.infographic_scenes.update(scene_ids)
        elif step == PipelineStep.CHARACTER:
            self.character_composite_scenes.update(scene_ids)
        elif step == PipelineStep.VIDEO:
            self.video_scenes.update(scene_ids)

        self.updated_at = datetime.now().isoformat()

    def remove_from_step(self, step: PipelineStep, scene_ids: Set[int]):
        """특정 단계에서 씬 제거"""
        if step == PipelineStep.REAL_IMAGE:
            self.real_image_scenes -= scene_ids
        elif step == PipelineStep.INFOGRAPHIC:
            self.infographic_scenes -= scene_ids
        elif step == PipelineStep.CHARACTER:
            self.character_composite_scenes -= scene_ids
        elif step == PipelineStep.VIDEO:
            self.video_scenes -= scene_ids

        self.updated_at = datetime.now().isoformat()

    def get_statistics(self) -> Dict:
        """파이프라인 전체 통계 반환"""
        total = len(self.total_scenes)

        if total == 0:
            return {"total": 0}

        normal_count = len(self.get_normal_image_scenes())

        return {
            "total": total,
            "korean_text": {
                "count": len(self.korean_text_scenes),
                "percentage": len(self.korean_text_scenes) / total * 100
            },
            "real_image": {
                "count": len(self.real_image_scenes),
                "percentage": len(self.real_image_scenes) / total * 100
            },
            "infographic": {
                "count": len(self.infographic_scenes),
                "percentage": len(self.infographic_scenes) / total * 100
            },
            "video": {
                "count": len(self.video_scenes),
                "percentage": len(self.video_scenes) / total * 100
            },
            "normal": {
                "count": normal_count,
                "percentage": normal_count / total * 100
            },
            "character_composite": {
                "count": len(self.character_composite_scenes),
                "percentage": len(self.character_composite_scenes) / total * 100
            },
            "current_step": self.current_step.value
        }

    def get_ai_cost_savings(self) -> Dict:
        """AI 비용 절감 효과 계산"""
        base_pool = len(self.get_base_pool())

        if base_pool == 0:
            # 모든 필수 키를 포함한 기본값 반환
            return {
                "base_pool": 0,
                "video_pool": 0,
                "saved_scenes": 0,
                "savings_rate": 0,
                "excluded_by_real_image": len(self.real_image_scenes),
                "excluded_by_infographic": len(self.infographic_scenes)
            }

        # 비디오 단계에서 제외된 씬 수 (가장 비용 높은 작업)
        video_pool = len(self.get_remaining_pool(PipelineStep.VIDEO))
        saved_from_video = base_pool - video_pool

        # 비용 가중치 적용 (비디오는 3배 비용)
        video_cost_weight = 3
        potential_cost = base_pool * video_cost_weight
        actual_cost = video_pool * video_cost_weight + saved_from_video * 1  # 대체된 씬은 낮은 비용

        savings_rate = (1 - actual_cost / potential_cost) * 100 if potential_cost > 0 else 0

        return {
            "base_pool": base_pool,
            "video_pool": video_pool,
            "saved_scenes": saved_from_video,
            "savings_rate": savings_rate,
            "excluded_by_real_image": len(self.real_image_scenes),
            "excluded_by_infographic": len(self.infographic_scenes)
        }

    def is_step_completed(self, step: PipelineStep) -> bool:
        """
        특정 단계가 완료되었는지 확인

        Args:
            step: PipelineStep 열거형

        Returns:
            bool: 완료 여부
        """
        # step_results에서 확인
        if step.value in self.step_results:
            result = self.step_results[step.value]
            return result.completed_at is not None

        # current_step 기반 확인 (이미 지나간 단계)
        step_order = [
            PipelineStep.REAL_IMAGE,
            PipelineStep.INFOGRAPHIC,
            PipelineStep.CHARACTER,
            PipelineStep.VIDEO
        ]

        if step not in step_order:
            return False

        step_idx = step_order.index(step)

        # 현재 단계가 COMPLETED면 모든 단계 완료
        if self.current_step == PipelineStep.COMPLETED:
            return True

        # 현재 단계 인덱스 확인
        if self.current_step in step_order:
            current_idx = step_order.index(self.current_step)
            return step_idx < current_idx

        return False

    @property
    def processed_scenes(self) -> Dict[str, Set[int]]:
        """
        단계별 처리된 씬 딕셔너리 반환

        Returns:
            Dict[str, Set[int]]: {step_value: processed_scene_ids}
        """
        result = {}

        # step_results에서 추출
        for step_value, step_result in self.step_results.items():
            if hasattr(step_result, 'processed_scenes'):
                result[step_value] = step_result.processed_scenes
            else:
                result[step_value] = set()

        # step_results에 없는 경우 각 속성에서 추출
        if PipelineStep.REAL_IMAGE.value not in result:
            result[PipelineStep.REAL_IMAGE.value] = self.real_image_scenes

        if PipelineStep.INFOGRAPHIC.value not in result:
            result[PipelineStep.INFOGRAPHIC.value] = self.infographic_scenes

        if PipelineStep.CHARACTER.value not in result:
            result[PipelineStep.CHARACTER.value] = self.character_composite_scenes

        if PipelineStep.VIDEO.value not in result:
            result[PipelineStep.VIDEO.value] = self.video_scenes

        return result

    def get_step1_summary(self) -> Dict:
        """Step 1 요약 정보 반환"""
        details = self.step1_details

        priority_bundle = details.get('priority_bundle', set())
        priority_korean = details.get('priority_korean', set())
        ai_recommended = details.get('ai_recommended', set())
        final_targets = details.get('final_targets', set())

        # set이 아닌 경우 변환
        if isinstance(priority_bundle, list):
            priority_bundle = set(priority_bundle)
        if isinstance(priority_korean, list):
            priority_korean = set(priority_korean)
        if isinstance(ai_recommended, list):
            ai_recommended = set(ai_recommended)
        if isinstance(final_targets, list):
            final_targets = set(final_targets)

        return {
            'priority_total': len(priority_bundle | priority_korean),
            'priority_bundle': len(priority_bundle),
            'priority_korean': len(priority_korean),
            'ai_recommended': len(ai_recommended),
            'final_total': len(final_targets) if final_targets else len(self.real_image_scenes)
        }

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        # step1_details 직렬화 (set -> list)
        step1_details_serialized = {}
        for key, value in self.step1_details.items():
            if isinstance(value, set):
                step1_details_serialized[key] = list(value)
            else:
                step1_details_serialized[key] = value

        return {
            "version": "1.1",
            "total_scenes": list(self.total_scenes),
            "korean_text_scenes": list(self.korean_text_scenes),
            "real_image_scenes": list(self.real_image_scenes),
            "infographic_scenes": list(self.infographic_scenes),
            "video_scenes": list(self.video_scenes),
            "character_composite_scenes": list(self.character_composite_scenes),
            "current_step": self.current_step.value,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "step1_details": step1_details_serialized,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PipelineState':
        """딕셔너리에서 생성"""
        state = cls()
        state.total_scenes = set(data.get("total_scenes", []))
        state.korean_text_scenes = set(data.get("korean_text_scenes", []))
        state.real_image_scenes = set(data.get("real_image_scenes", []))
        state.infographic_scenes = set(data.get("infographic_scenes", []))
        state.video_scenes = set(data.get("video_scenes", []))
        state.character_composite_scenes = set(data.get("character_composite_scenes", []))
        state.current_step = PipelineStep(data.get("current_step", "initial"))

        step_results = data.get("step_results", {})
        state.step_results = {k: StepResult.from_dict(v) for k, v in step_results.items()}

        # step1_details 역직렬화 (list -> set)
        step1_data = data.get("step1_details", {})
        state.step1_details = {
            'priority_bundle': set(step1_data.get('priority_bundle', [])),
            'priority_korean': set(step1_data.get('priority_korean', [])),
            'priority_total': set(step1_data.get('priority_total', [])),
            'ai_recommended': set(step1_data.get('ai_recommended', [])),
            'final_targets': set(step1_data.get('final_targets', []))
        }

        state.created_at = data.get("created_at")
        state.updated_at = data.get("updated_at")

        return state

    def reset(self):
        """파이프라인 초기화"""
        self.real_image_scenes = set()
        self.infographic_scenes = set()
        self.video_scenes = set()
        self.character_composite_scenes = set()
        self.current_step = PipelineStep.INITIAL
        self.step_results = {}
        self.step1_details = {
            'priority_bundle': set(),
            'priority_korean': set(),
            'priority_total': set(),
            'ai_recommended': set(),
            'final_targets': set()
        }
        self.updated_at = datetime.now().isoformat()


# ============================================================
# 파이프라인 저장/로드
# ============================================================

def save_pipeline_state(state: PipelineState, project_path: Path) -> bool:
    """파이프라인 상태 저장"""
    try:
        save_path = project_path / "data" / "pipeline_state.json"
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)

        print(f"[Pipeline] 저장 완료: {save_path}")
        return True
    except Exception as e:
        print(f"[Pipeline] 저장 실패: {e}")
        return False


def load_pipeline_state(project_path: Path) -> Optional[PipelineState]:
    """파이프라인 상태 로드"""
    load_path = project_path / "data" / "pipeline_state.json"

    if not load_path.exists():
        return None

    try:
        with open(load_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        state = PipelineState.from_dict(data)
        print(f"[Pipeline] 로드 완료: {len(state.total_scenes)}개 씬")
        return state
    except Exception as e:
        print(f"[Pipeline] 로드 실패: {e}")
        return None


def get_step_config(step: PipelineStep) -> Dict:
    """단계 설정 정보 반환"""
    return STEP_CONFIG.get(step, {})


def get_all_steps() -> List[PipelineStep]:
    """모든 처리 단계 반환 (순서대로)"""
    return [
        PipelineStep.REAL_IMAGE,
        PipelineStep.INFOGRAPHIC,
        PipelineStep.CHARACTER,
        PipelineStep.VIDEO
    ]
