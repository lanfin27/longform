# -*- coding: utf-8 -*-
"""
묶음 씬 이미지 생성 최적화 유틸리티 v1.0

동일한 프롬프트를 가진 연속 씬들을 그룹화하고,
첫 번째 씬만 이미지를 생성한 후 나머지는 복사하여 효율화

작성: 2026-01
"""

import os
import json
import shutil
import hashlib
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class SceneGroup:
    """프롬프트가 동일한 씬 그룹"""
    prompt: str
    prompt_hash: str
    scene_numbers: List[int]
    representative_scene: int  # 대표 씬 (첫 번째)
    follower_scenes: List[int]  # 복사 대상 씬들
    image_path: Optional[str] = None  # 생성된 이미지 경로


@dataclass
class OptimizationStats:
    """최적화 통계"""
    total_scenes: int = 0
    unique_prompts: int = 0
    to_generate: int = 0
    to_copy: int = 0
    estimated_time_without_opt: float = 0
    estimated_time_with_opt: float = 0
    time_saved: float = 0
    time_saved_percent: float = 0


class BatchImageOptimizer:
    """
    묶음 씬 이미지 생성 최적화기

    - 프롬프트 기준으로 씬 그룹화
    - 대표 씬만 이미지 생성
    - 나머지 씬은 이미지 복사
    """

    # 이미지 1개 생성 평균 시간 (초)
    AVG_GENERATION_TIME = 8
    # 이미지 복사 시간 (초)
    COPY_TIME = 0.1

    def __init__(self, project_path: str):
        """
        초기화

        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path)
        self.scenes_path = self.project_path / 'analysis' / 'scenes.json'
        self.backgrounds_dir = self.project_path / 'images' / 'backgrounds'
        self.characters_dir = self.project_path / 'images' / 'characters'
        self.optimization_log_path = self.project_path / 'data' / 'image_optimization_log.json'

        # 씬 데이터 로드
        self.scenes_data = self._load_scenes()

        # 실행 통계
        self.stats = {
            'total_scenes': 0,
            'generated': 0,
            'copied': 0,
            'time_saved_estimate': 0
        }

    def _load_scenes(self) -> List[dict]:
        """씬 데이터 로드"""
        if self.scenes_path.exists():
            try:
                with open(self.scenes_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data.get('scenes', [])
                    return data if isinstance(data, list) else []
            except Exception as e:
                print(f"[BatchOptimizer] 씬 데이터 로드 오류: {e}")
        return []

    def _get_prompt_hash(self, prompt: str) -> str:
        """프롬프트 해시 생성 (정규화 후)"""
        # 정규화: 소문자, 공백 정리
        normalized = ' '.join(prompt.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def _normalize_prompt(self, prompt: str) -> str:
        """프롬프트 정규화"""
        return ' '.join(prompt.lower().split())

    def group_scenes_by_prompt(
        self,
        scene_numbers: List[int],
        prompt_field: str = 'image_prompt_en'
    ) -> List[SceneGroup]:
        """
        프롬프트 기준으로 씬 그룹화

        Args:
            scene_numbers: 처리할 씬 번호 목록
            prompt_field: 프롬프트 필드명 (image_prompt_en, background_prompt_en 등)

        Returns:
            SceneGroup 목록
        """
        # 씬 번호 → 프롬프트 매핑
        scene_prompts: Dict[int, str] = {}

        for scene in self.scenes_data:
            scene_num = scene.get('scene_number') or scene.get('scene_id')

            if scene_num not in scene_numbers:
                continue

            # 프롬프트 추출 (여러 필드 시도)
            prompt = (
                scene.get(prompt_field) or
                scene.get('image_prompt_en') or
                scene.get('background_prompt_en') or
                ''
            ).strip()

            if prompt:
                scene_prompts[scene_num] = prompt

        # 프롬프트 해시 기준 그룹화
        hash_to_scenes: Dict[str, List[int]] = {}
        hash_to_prompt: Dict[str, str] = {}

        for scene_num in sorted(scene_prompts.keys()):
            prompt = scene_prompts[scene_num]
            prompt_hash = self._get_prompt_hash(prompt)

            if prompt_hash not in hash_to_scenes:
                hash_to_scenes[prompt_hash] = []
                hash_to_prompt[prompt_hash] = prompt

            hash_to_scenes[prompt_hash].append(scene_num)

        # SceneGroup 객체 생성
        groups = []

        for prompt_hash, scenes in hash_to_scenes.items():
            scenes_sorted = sorted(scenes)

            group = SceneGroup(
                prompt=hash_to_prompt[prompt_hash],
                prompt_hash=prompt_hash,
                scene_numbers=scenes_sorted,
                representative_scene=scenes_sorted[0],
                follower_scenes=scenes_sorted[1:] if len(scenes_sorted) > 1 else []
            )

            groups.append(group)

        # 대표 씬 번호 기준 정렬
        groups.sort(key=lambda g: g.representative_scene)

        return groups

    def get_optimization_plan(
        self,
        scene_numbers: List[int],
        prompt_field: str = 'image_prompt_en'
    ) -> Dict:
        """
        최적화 계획 생성 (미리보기용)

        Args:
            scene_numbers: 처리할 씬 번호 목록
            prompt_field: 프롬프트 필드명

        Returns:
            {
                'groups': [...],
                'stats': OptimizationStats,
                'scenes_to_generate': [...],
                'scenes_to_copy': {target: source, ...}
            }
        """
        groups = self.group_scenes_by_prompt(scene_numbers, prompt_field)

        total_scenes = len(scene_numbers)
        unique_prompts = len(groups)
        to_generate = len(groups)  # 각 그룹의 대표 씬
        to_copy = sum(len(g.follower_scenes) for g in groups)

        # 예상 시간 계산
        time_without_opt = total_scenes * self.AVG_GENERATION_TIME
        time_with_opt = (to_generate * self.AVG_GENERATION_TIME) + (to_copy * self.COPY_TIME)
        time_saved = time_without_opt - time_with_opt
        time_saved_percent = (time_saved / time_without_opt * 100) if time_without_opt > 0 else 0

        stats = OptimizationStats(
            total_scenes=total_scenes,
            unique_prompts=unique_prompts,
            to_generate=to_generate,
            to_copy=to_copy,
            estimated_time_without_opt=time_without_opt,
            estimated_time_with_opt=time_with_opt,
            time_saved=time_saved,
            time_saved_percent=time_saved_percent
        )

        # 그룹 정보 요약
        group_summaries = []
        for g in groups:
            group_summaries.append({
                'representative': g.representative_scene,
                'followers': g.follower_scenes,
                'scene_count': len(g.scene_numbers),
                'prompt_preview': g.prompt[:80] + '...' if len(g.prompt) > 80 else g.prompt,
                'prompt_hash': g.prompt_hash
            })

        # 생성/복사 분리
        scenes_to_generate = [g.representative_scene for g in groups]
        scenes_to_copy = {}
        for g in groups:
            for follower in g.follower_scenes:
                scenes_to_copy[follower] = g.representative_scene

        return {
            'groups': group_summaries,
            'stats': stats,
            'scenes_to_generate': scenes_to_generate,
            'scenes_to_copy': scenes_to_copy
        }

    def copy_image_for_scene(
        self,
        source_scene_num: int,
        target_scene_num: int,
        source_image_path: str,
        image_type: str = 'background'
    ) -> Optional[str]:
        """
        원본 씬의 이미지를 대상 씬으로 복사

        Args:
            source_scene_num: 원본 씬 번호
            target_scene_num: 대상 씬 번호
            source_image_path: 원본 이미지 경로
            image_type: 'background', 'composited', 또는 'character'

        Returns:
            복사된 이미지 경로 또는 None
        """
        if not source_image_path or not os.path.exists(source_image_path):
            print(f"[BatchOptimizer] ❌ 원본 이미지 없음: {source_image_path}")
            return None

        # 대상 디렉토리 결정
        if image_type == 'background':
            target_dir = self.backgrounds_dir
            prefix = 'bg'
        elif image_type == 'composited':
            target_dir = self.project_path / 'images' / 'composited'
            prefix = 'composited'
        else:
            target_dir = self.characters_dir
            prefix = 'char'

        target_dir.mkdir(parents=True, exist_ok=True)

        # 타임스탬프로 고유 파일명 생성
        timestamp = int(datetime.now().timestamp() * 1000)
        ext = os.path.splitext(source_image_path)[1]

        # 이미지 타입에 따른 파일명 패턴
        if image_type == 'composited':
            target_filename = f"composited_scene_{target_scene_num:03d}_{timestamp}{ext}"
        else:
            target_filename = f"{prefix}_scene_{target_scene_num:03d}_{timestamp}{ext}"

        target_path = str(target_dir / target_filename)

        try:
            # 파일 복사
            shutil.copy2(source_image_path, target_path)

            print(f"[BatchOptimizer] 📋 씬 {target_scene_num}: 씬 {source_scene_num} 이미지 복사됨")
            print(f"[BatchOptimizer]    원본: {os.path.basename(source_image_path)}")
            print(f"[BatchOptimizer]    복사: {os.path.basename(target_path)}")

            # 메타데이터 복사 및 수정
            self._copy_and_update_metadata(
                source_image_path, target_path,
                source_scene_num, target_scene_num
            )

            self.stats['copied'] += 1

            return target_path

        except Exception as e:
            print(f"[BatchOptimizer] ❌ 복사 실패: {e}")
            return None

    def _copy_and_update_metadata(
        self,
        source_image_path: str,
        target_image_path: str,
        source_scene_num: int,
        target_scene_num: int
    ):
        """메타데이터 파일 복사 및 수정"""
        source_meta_path = os.path.splitext(source_image_path)[0] + '.json'
        target_meta_path = os.path.splitext(target_image_path)[0] + '.json'

        metadata = {}

        if os.path.exists(source_meta_path):
            try:
                with open(source_meta_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except:
                pass

        # 메타데이터 수정
        metadata['scene_number'] = target_scene_num
        metadata['copied_from'] = {
            'scene_number': source_scene_num,
            'original_path': source_image_path
        }
        metadata['is_copied'] = True
        metadata['copied_at'] = datetime.now().isoformat()

        try:
            with open(target_meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[BatchOptimizer] ⚠️ 메타데이터 저장 실패: {e}")

    def print_optimization_plan(self, plan: Dict):
        """최적화 계획 출력"""
        stats = plan['stats']

        print(f"\n{'='*70}")
        print(f"[BatchOptimizer] 🚀 묶음 최적화 활성화")
        print(f"{'='*70}")
        print(f"[BatchOptimizer] 📊 최적화 계획:")
        print(f"[BatchOptimizer]    전체 씬: {stats.total_scenes}개")
        print(f"[BatchOptimizer]    고유 프롬프트: {stats.unique_prompts}개")
        print(f"[BatchOptimizer]    실제 생성: {stats.to_generate}개")
        print(f"[BatchOptimizer]    복사: {stats.to_copy}개")
        print(f"[BatchOptimizer]    예상 시간 (최적화 전): {stats.estimated_time_without_opt:.0f}초")
        print(f"[BatchOptimizer]    예상 시간 (최적화 후): {stats.estimated_time_with_opt:.0f}초")
        print(f"[BatchOptimizer]    ⏱️ 절약 시간: {stats.time_saved:.0f}초 ({stats.time_saved_percent:.1f}%)")
        print(f"{'='*70}")

        # 그룹별 상세 정보
        for group in plan['groups']:
            if group['followers']:
                followers_str = ', '.join(map(str, group['followers']))
                print(f"[BatchOptimizer] 📦 묶음: 씬 {group['representative']} → 복사 대상: [{followers_str}]")

        print()

    def save_optimization_log(self, plan: Dict, results: List[dict]):
        """최적화 로그 저장"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'stats': {
                'total_scenes': plan['stats'].total_scenes,
                'generated': sum(1 for r in results if r.get('generated')),
                'copied': sum(1 for r in results if not r.get('generated') and r.get('success')),
                'time_saved_percent': plan['stats'].time_saved_percent
            },
            'groups': plan['groups'],
            'results': results
        }

        self.optimization_log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.optimization_log_path, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            print(f"[BatchOptimizer] 📊 최적화 로그 저장됨: {self.optimization_log_path}")
        except Exception as e:
            print(f"[BatchOptimizer] ⚠️ 로그 저장 실패: {e}")


def get_scenes_to_generate_and_copy(
    scene_numbers: List[int],
    scenes_data: List[dict],
    prompt_field: str = 'image_prompt_en'
) -> Tuple[List[int], Dict[int, int]]:
    """
    실제 생성할 씬과 복사할 씬 분리 (간단한 버전)

    Args:
        scene_numbers: 처리할 씬 번호 목록
        scenes_data: 씬 데이터
        prompt_field: 프롬프트 필드명

    Returns:
        (생성할 씬 번호 목록, {복사할 씬: 원본 씬} 매핑)
    """
    # 씬 번호 → 프롬프트 매핑
    scene_prompts: Dict[int, str] = {}

    for scene in scenes_data:
        scene_num = scene.get('scene_number') or scene.get('scene_id')

        if scene_num not in scene_numbers:
            continue

        prompt = (
            scene.get(prompt_field) or
            scene.get('image_prompt_en') or
            scene.get('background_prompt_en') or
            ''
        ).strip()

        if prompt:
            scene_prompts[scene_num] = prompt

    # 프롬프트 → 첫 번째 씬 매핑
    prompt_to_first_scene: Dict[str, int] = {}
    scenes_to_generate: List[int] = []
    scenes_to_copy: Dict[int, int] = {}  # {복사할 씬: 원본 씬}

    for scene_num in sorted(scene_numbers):
        if scene_num not in scene_prompts:
            # 프롬프트 없으면 그냥 생성 목록에 추가
            scenes_to_generate.append(scene_num)
            continue

        prompt = scene_prompts[scene_num]
        prompt_normalized = ' '.join(prompt.lower().split())

        if prompt_normalized not in prompt_to_first_scene:
            # 첫 번째 등장 → 생성 대상
            prompt_to_first_scene[prompt_normalized] = scene_num
            scenes_to_generate.append(scene_num)
        else:
            # 이미 같은 프롬프트가 있음 → 복사 대상
            original_scene = prompt_to_first_scene[prompt_normalized]
            scenes_to_copy[scene_num] = original_scene

    return scenes_to_generate, scenes_to_copy


def print_optimization_summary(
    scenes_to_generate: List[int],
    scenes_to_copy: Dict[int, int],
    total_scenes: int
):
    """최적화 요약 출력"""
    to_copy_count = len(scenes_to_copy)

    if to_copy_count == 0:
        print(f"[BatchOptimizer] ℹ️ 모든 씬이 고유한 프롬프트를 가짐 - 최적화 없음")
        return

    avg_time = 8  # 초
    time_without = total_scenes * avg_time
    time_with = len(scenes_to_generate) * avg_time + to_copy_count * 0.1
    time_saved = time_without - time_with

    print(f"\n[BatchOptimizer] ✅ 생성 대상: {scenes_to_generate}")
    print(f"[BatchOptimizer] 📋 복사 대상: {list(scenes_to_copy.keys())}")
    print(f"[BatchOptimizer] ⏱️ 예상 시간 절약: {time_saved:.0f}초 ({time_saved/time_without*100:.1f}%)\n")


def get_latest_background_for_scene(project_path: str, scene_id: int) -> Optional[str]:
    """
    특정 씬의 가장 최신 배경 이미지 경로 반환

    Args:
        project_path: 프로젝트 경로
        scene_id: 씬 ID

    Returns:
        이미지 경로 또는 None
    """
    bg_dir = Path(project_path) / "images" / "backgrounds"

    if not bg_dir.exists():
        return None

    # 패턴: bg_scene_{scene_id:03d}_*.png
    pattern = f"bg_scene_{scene_id:03d}_*.png"
    matches = list(bg_dir.glob(pattern))

    if not matches:
        return None

    # 타임스탬프 기준 정렬 (파일명의 마지막 숫자가 타임스탬프)
    # 또는 파일 수정시간으로 정렬
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return str(matches[0])


def get_latest_composited_for_scene(project_path: str, scene_id: int) -> Optional[str]:
    """
    특정 씬의 가장 최신 합성 이미지 경로 반환

    Args:
        project_path: 프로젝트 경로
        scene_id: 씬 ID

    Returns:
        이미지 경로 또는 None
    """
    comp_dir = Path(project_path) / "images" / "composited"

    if not comp_dir.exists():
        return None

    pattern = f"composited_scene_{scene_id:03d}_*.png"
    matches = list(comp_dir.glob(pattern))

    if not matches:
        return None

    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(matches[0])


# 편의 함수
def create_optimizer(project_path: str) -> BatchImageOptimizer:
    """BatchImageOptimizer 인스턴스 생성"""
    return BatchImageOptimizer(project_path)
