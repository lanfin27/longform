# -*- coding: utf-8 -*-
"""
PoseManager - 씬별 포즈 관리 모듈

Problem 56: 포즈 기반 씬 설정 및 랜덤 포즈 배정 기능

버전: 1.0.0
생성일: 2025-12-23
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import logging

# 로거 설정
logger = logging.getLogger(__name__)


@dataclass
class PoseTemplate:
    """포즈 템플릿 데이터 클래스"""
    id: str
    name_ko: str
    name_en: str
    description: str
    prompt_modifier: str
    suitable_moods: List[str]
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'id': self.id,
            'name_ko': self.name_ko,
            'name_en': self.name_en,
            'description': self.description,
            'prompt_modifier': self.prompt_modifier,
            'suitable_moods': self.suitable_moods,
            'weight': self.weight
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PoseTemplate':
        """딕셔너리에서 생성"""
        return cls(
            id=data.get('id', ''),
            name_ko=data.get('name_ko', ''),
            name_en=data.get('name_en', ''),
            description=data.get('description', ''),
            prompt_modifier=data.get('prompt_modifier', ''),
            suitable_moods=data.get('suitable_moods', []),
            weight=data.get('weight', 1.0)
        )


@dataclass
class ScenePoseAssignment:
    """씬별 포즈 배정 데이터"""
    scene_number: int
    scene_title: str
    mood: str
    assigned_pose_id: str
    assigned_pose_name: str
    is_manual: bool = False  # 수동 설정 여부

    def to_dict(self) -> Dict[str, Any]:
        return {
            'scene_number': self.scene_number,
            'scene_title': self.scene_title,
            'mood': self.mood,
            'assigned_pose_id': self.assigned_pose_id,
            'assigned_pose_name': self.assigned_pose_name,
            'is_manual': self.is_manual
        }


class PoseManager:
    """
    포즈 관리 클래스

    기능:
    - 포즈 템플릿 로드 및 관리
    - 씬 분위기에 맞는 포즈 추천
    - 가중치 기반 랜덤 포즈 선택
    - 씬별 포즈 일괄 배정
    """

    # 기본 포즈 템플릿 경로
    DEFAULT_TEMPLATE_PATH = Path(__file__).parent.parent / "data" / "config" / "pose_templates.json"

    def __init__(self, template_path: Optional[Path] = None):
        """
        초기화

        Args:
            template_path: 포즈 템플릿 JSON 파일 경로 (None이면 기본 경로 사용)
        """
        self.template_path = template_path or self.DEFAULT_TEMPLATE_PATH
        self.poses: Dict[str, PoseTemplate] = {}
        self.mood_to_pose_mapping: Dict[str, List[str]] = {}
        self.version: str = "1.0"

        # 포즈 로드
        self._load_poses()

        logger.info(f"[PoseManager] 초기화 완료 - {len(self.poses)}개 포즈 로드됨")

    def _load_poses(self) -> None:
        """포즈 템플릿 JSON 파일 로드"""
        try:
            if not self.template_path.exists():
                logger.warning(f"[PoseManager] 템플릿 파일 없음: {self.template_path}")
                self._create_default_poses()
                return

            with open(self.template_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.version = data.get('version', '1.0')

            # 포즈 로드
            for pose_data in data.get('poses', []):
                pose = PoseTemplate.from_dict(pose_data)
                self.poses[pose.id] = pose

            # 분위기-포즈 매핑 로드
            self.mood_to_pose_mapping = data.get('mood_to_pose_mapping', {})

            logger.info(f"[PoseManager] 템플릿 로드 성공 - 버전: {self.version}")

        except json.JSONDecodeError as e:
            logger.error(f"[PoseManager] JSON 파싱 오류: {e}")
            self._create_default_poses()
        except Exception as e:
            logger.error(f"[PoseManager] 템플릿 로드 실패: {e}")
            self._create_default_poses()

    def _create_default_poses(self) -> None:
        """기본 포즈 생성 (fallback)"""
        default_poses = [
            PoseTemplate(
                id="explaining",
                name_ko="설명하는",
                name_en="explaining",
                description="한 손을 들어 설명하는 포즈",
                prompt_modifier="explaining with one hand raised, professional presentation pose",
                suitable_moods=["informative", "educational", "neutral", "정보 전달"],
                weight=1.0
            ),
            PoseTemplate(
                id="standing",
                name_ko="서있는",
                name_en="standing",
                description="기본 서있는 포즈",
                prompt_modifier="standing pose, neutral stance, professional appearance",
                suitable_moods=["neutral", "default", "기본"],
                weight=1.0
            ),
            PoseTemplate(
                id="presenting",
                name_ko="발표하는",
                name_en="presenting",
                description="양손을 펼쳐 발표하는 포즈",
                prompt_modifier="presenting with both hands open, confident stance",
                suitable_moods=["confident", "enthusiastic", "promotional", "기대감 조성"],
                weight=1.0
            )
        ]

        for pose in default_poses:
            self.poses[pose.id] = pose

        # 기본 매핑
        self.mood_to_pose_mapping = {
            "default": ["explaining", "standing", "presenting"]
        }

        logger.info("[PoseManager] 기본 포즈 3개 생성됨")

    def get_all_poses(self) -> List[PoseTemplate]:
        """모든 포즈 템플릿 반환"""
        return list(self.poses.values())

    def get_pose_by_id(self, pose_id: str) -> Optional[PoseTemplate]:
        """ID로 포즈 조회"""
        return self.poses.get(pose_id)

    def get_suitable_poses_for_mood(self, mood: str) -> List[PoseTemplate]:
        """
        씬 분위기에 적합한 포즈 목록 반환

        Args:
            mood: 씬 분위기 (예: "기대감 조성", "정보 전달", "놀라움")

        Returns:
            적합한 포즈 템플릿 리스트
        """
        suitable_poses = []

        # 1. 먼저 mood_to_pose_mapping에서 검색
        if mood in self.mood_to_pose_mapping:
            pose_ids = self.mood_to_pose_mapping[mood]
            for pose_id in pose_ids:
                if pose_id in self.poses:
                    suitable_poses.append(self.poses[pose_id])

        # 2. 매핑에 없으면 각 포즈의 suitable_moods에서 검색
        if not suitable_poses:
            for pose in self.poses.values():
                if mood in pose.suitable_moods:
                    suitable_poses.append(pose)

        # 3. 그래도 없으면 default 사용
        if not suitable_poses:
            default_ids = self.mood_to_pose_mapping.get('default', ['explaining', 'standing'])
            for pose_id in default_ids:
                if pose_id in self.poses:
                    suitable_poses.append(self.poses[pose_id])

        # 4. 최후의 fallback
        if not suitable_poses and self.poses:
            suitable_poses = list(self.poses.values())[:3]

        return suitable_poses

    def select_random_pose(
        self,
        mood: str,
        exclude_poses: Optional[List[str]] = None,
        use_weights: bool = True
    ) -> Optional[PoseTemplate]:
        """
        분위기에 맞는 포즈 중 랜덤 선택 (가중치 기반)

        Args:
            mood: 씬 분위기
            exclude_poses: 제외할 포즈 ID 리스트 (연속 중복 방지용)
            use_weights: 가중치 사용 여부

        Returns:
            선택된 포즈 템플릿 (없으면 None)
        """
        suitable_poses = self.get_suitable_poses_for_mood(mood)

        if not suitable_poses:
            return None

        # 제외할 포즈 필터링
        if exclude_poses:
            filtered = [p for p in suitable_poses if p.id not in exclude_poses]
            if filtered:
                suitable_poses = filtered
            # 제외하면 포즈가 없는 경우 원래 리스트 사용 (최소 1개는 선택)

        if use_weights:
            # 가중치 기반 랜덤 선택
            weights = [p.weight for p in suitable_poses]
            total_weight = sum(weights)

            if total_weight <= 0:
                return random.choice(suitable_poses)

            # random.choices 대신 수동 구현 (더 정확한 가중치 적용)
            r = random.uniform(0, total_weight)
            cumulative = 0
            for pose, weight in zip(suitable_poses, weights):
                cumulative += weight
                if r <= cumulative:
                    return pose

            return suitable_poses[-1]  # fallback
        else:
            return random.choice(suitable_poses)

    def assign_random_poses_to_scenes(
        self,
        scenes: List[Dict[str, Any]],
        avoid_consecutive_duplicates: bool = True,
        max_consecutive: int = 2
    ) -> List[ScenePoseAssignment]:
        """
        여러 씬에 랜덤 포즈 일괄 배정

        Args:
            scenes: 씬 정보 리스트 [{'scene_number': 1, 'title': '...', 'mood': '...'}, ...]
            avoid_consecutive_duplicates: 연속 중복 포즈 방지
            max_consecutive: 최대 연속 허용 횟수

        Returns:
            씬별 포즈 배정 결과 리스트
        """
        assignments = []
        recent_poses = []  # 최근 배정된 포즈 ID 추적

        for scene in scenes:
            scene_number = scene.get('scene_number', len(assignments) + 1)
            scene_title = scene.get('title', f'씬 {scene_number}')
            mood = scene.get('mood', 'default')

            # 연속 중복 방지를 위한 제외 목록
            exclude = []
            if avoid_consecutive_duplicates and recent_poses:
                # 최근 포즈가 max_consecutive번 연속이면 제외
                if len(recent_poses) >= max_consecutive:
                    last_pose = recent_poses[-1]
                    consecutive_count = sum(1 for p in recent_poses[-max_consecutive:] if p == last_pose)
                    if consecutive_count >= max_consecutive:
                        exclude.append(last_pose)

            # 랜덤 포즈 선택
            selected_pose = self.select_random_pose(mood, exclude_poses=exclude)

            if selected_pose:
                assignment = ScenePoseAssignment(
                    scene_number=scene_number,
                    scene_title=scene_title,
                    mood=mood,
                    assigned_pose_id=selected_pose.id,
                    assigned_pose_name=selected_pose.name_ko,
                    is_manual=False
                )
                assignments.append(assignment)
                recent_poses.append(selected_pose.id)

                # 최근 포즈 기록 유지 (메모리 관리)
                if len(recent_poses) > max_consecutive * 2:
                    recent_poses = recent_poses[-max_consecutive:]
            else:
                # 포즈를 선택하지 못한 경우
                logger.warning(f"[PoseManager] 씬 {scene_number}에 적합한 포즈 없음")
                assignments.append(ScenePoseAssignment(
                    scene_number=scene_number,
                    scene_title=scene_title,
                    mood=mood,
                    assigned_pose_id="standing",
                    assigned_pose_name="서있는",
                    is_manual=False
                ))

        logger.info(f"[PoseManager] {len(assignments)}개 씬에 포즈 배정 완료")
        return assignments

    def get_pose_options_for_dropdown(self) -> List[Tuple[str, str]]:
        """
        드롭다운 UI용 포즈 옵션 반환

        Returns:
            [(display_name, pose_id), ...] 형태의 튜플 리스트
        """
        options = []
        for pose in self.poses.values():
            display_name = f"{pose.name_ko} ({pose.name_en})"
            options.append((display_name, pose.id))
        return sorted(options, key=lambda x: x[0])

    def get_pose_prompt_modifier(self, pose_id: str) -> str:
        """
        포즈 ID로 prompt modifier 반환

        Args:
            pose_id: 포즈 ID

        Returns:
            prompt_modifier 문자열 (없으면 빈 문자열)
        """
        pose = self.poses.get(pose_id)
        return pose.prompt_modifier if pose else ""

    def validate_scene_data(self, scenes: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        씬 데이터 유효성 검증

        Args:
            scenes: 씬 정보 리스트

        Returns:
            (유효 여부, 오류 메시지 리스트)
        """
        errors = []

        if not scenes:
            errors.append("씬 데이터가 비어있습니다.")
            return False, errors

        for i, scene in enumerate(scenes):
            if 'scene_number' not in scene and 'title' not in scene:
                errors.append(f"씬 {i+1}: scene_number 또는 title 필드 필요")

            if 'mood' not in scene:
                # mood가 없으면 기본값 사용 (경고만)
                logger.warning(f"씬 {i+1}: mood 필드 없음 - 기본값 사용")

        return len(errors) == 0, errors

    def export_assignments_to_json(
        self,
        assignments: List[ScenePoseAssignment],
        output_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        포즈 배정 결과를 JSON 파일로 저장

        Args:
            assignments: 포즈 배정 결과 리스트
            output_path: 저장 경로 (None이면 기본 경로 사용)

        Returns:
            저장된 파일 경로 (실패시 None)
        """
        if output_path is None:
            output_path = Path(__file__).parent.parent / "data" / "output" / "pose_assignments.json"

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'version': '1.0',
                'total_scenes': len(assignments),
                'assignments': [a.to_dict() for a in assignments]
            }

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"[PoseManager] 포즈 배정 결과 저장: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"[PoseManager] 저장 실패: {e}")
            return None

    def get_mood_statistics(self, assignments: List[ScenePoseAssignment]) -> Dict[str, int]:
        """
        포즈 배정 통계 반환

        Args:
            assignments: 포즈 배정 결과 리스트

        Returns:
            {'pose_id': count, ...} 형태의 통계
        """
        stats = {}
        for assignment in assignments:
            pose_id = assignment.assigned_pose_id
            stats[pose_id] = stats.get(pose_id, 0) + 1
        return stats


# 싱글톤 인스턴스 (선택적 사용)
_pose_manager_instance: Optional[PoseManager] = None


def get_pose_manager() -> PoseManager:
    """
    PoseManager 싱글톤 인스턴스 반환

    Returns:
        PoseManager 인스턴스
    """
    global _pose_manager_instance
    if _pose_manager_instance is None:
        _pose_manager_instance = PoseManager()
    return _pose_manager_instance


# 테스트/디버깅용
if __name__ == "__main__":
    # 테스트 실행
    pm = PoseManager()

    print(f"로드된 포즈 수: {len(pm.poses)}")
    print("\n포즈 목록:")
    for pose in pm.get_all_poses():
        print(f"  - {pose.name_ko} ({pose.id}): {pose.description}")

    print("\n분위기별 추천 포즈:")
    for mood in ["정보 전달", "놀라움", "기대감 조성", "마무리"]:
        suitable = pm.get_suitable_poses_for_mood(mood)
        names = [p.name_ko for p in suitable]
        print(f"  {mood}: {', '.join(names)}")

    print("\n랜덤 포즈 배정 테스트:")
    test_scenes = [
        {"scene_number": 1, "title": "인트로", "mood": "기대감 조성"},
        {"scene_number": 2, "title": "문제 제기", "mood": "정보 전달"},
        {"scene_number": 3, "title": "놀라운 사실", "mood": "놀라움"},
        {"scene_number": 4, "title": "분석", "mood": "분석/비교"},
        {"scene_number": 5, "title": "결론", "mood": "마무리"},
    ]

    assignments = pm.assign_random_poses_to_scenes(test_scenes)
    for a in assignments:
        print(f"  씬 {a.scene_number} ({a.mood}): {a.assigned_pose_name}")

    print("\n포즈 사용 통계:")
    stats = pm.get_mood_statistics(assignments)
    for pose_id, count in stats.items():
        print(f"  {pose_id}: {count}회")
