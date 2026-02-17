# -*- coding: utf-8 -*-
"""
동적 묶음 생성 v1.0

사용자가 선택한 묶음 크기에 따라 씬 그룹화
- 하드코딩 금지!
- 모든 설정값은 claude_code_config에서 동적으로 읽음

주요 기능:
1. 사용자 설정 묶음 크기로 씬 그룹화
2. 묶음 내 스크립트 합본
3. 배치 분할 (동적 크기)
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from .claude_code_config import (
    get_bundle_size,
    get_use_bundle_mode,
    calculate_dynamic_batch_size,
    get_claude_code_config
)


# ═══════════════════════════════════════════════════════════════════
# 묶음 생성
# ═══════════════════════════════════════════════════════════════════

def create_bundles_dynamic(scenes: List[Dict]) -> List[Dict]:
    """
    사용자 설정에 따라 동적으로 묶음 생성

    Args:
        scenes: 전체 씬 목록

    Returns:
        묶음 목록 (각 묶음에 scene_ids, combined_script 포함)
    """
    # 사용자가 선택한 묶음 크기 읽기 (핵심!)
    bundle_size = get_bundle_size()

    # 씬 정렬 (scene_id 순)
    sorted_scenes = sorted(scenes, key=lambda x: x.get("scene_id", 0))

    # 묶음 생성
    bundles = []
    bundle_id = 1

    for i in range(0, len(sorted_scenes), bundle_size):
        bundle_scenes = sorted_scenes[i:i + bundle_size]

        # 묶음 내 모든 씬의 스크립트 합본 (핵심!)
        combined_script_parts = []
        for scene in bundle_scenes:
            script = _get_scene_script(scene)
            if script:
                scene_id = scene.get("scene_id", "?")
                combined_script_parts.append(f"[씬 {scene_id}] {script}")

        # 총 재생 시간 계산
        total_duration = sum(
            _get_scene_duration(s) for s in bundle_scenes
        )

        bundle = {
            "bundle_id": bundle_id,
            "scene_ids": [s.get("scene_id") for s in bundle_scenes],
            "scene_count": len(bundle_scenes),
            "total_duration": total_duration,
            "combined_script": "\n".join(combined_script_parts),
            "primary_scene_id": bundle_scenes[0].get("scene_id"),
        }

        bundles.append(bundle)
        bundle_id += 1

    print(f"[Bundle] ═══════════════════════════════════════════")
    print(f"[Bundle] 묶음 크기: {bundle_size} (사용자 선택)")
    print(f"[Bundle] {len(scenes)}개 씬 → {len(bundles)}개 묶음")
    print(f"[Bundle] ═══════════════════════════════════════════")

    return bundles


def _get_scene_script(scene: Dict) -> str:
    """씬에서 스크립트 텍스트 추출 (여러 필드 지원)"""
    for field in ["script", "script_ko", "script_text", "narration", "text"]:
        if scene.get(field):
            return str(scene[field])
    return ""


def _get_scene_duration(scene: Dict) -> float:
    """씬 재생 시간 추출"""
    for field in ["srt_duration", "duration", "length"]:
        if scene.get(field):
            try:
                return float(scene[field])
            except:
                pass
    return 0.0


# ═══════════════════════════════════════════════════════════════════
# 묶음별 입력 데이터 생성
# ═══════════════════════════════════════════════════════════════════

def create_bundle_inputs(
    scenes: List[Dict],
    bundles: List[Dict]
) -> List[Dict]:
    """
    묶음별 입력 데이터 생성 (Claude Code 실행용)

    Args:
        scenes: 전체 씬 목록
        bundles: 묶음 목록

    Returns:
        묶음별 입력 데이터 리스트
    """
    # scene_id로 빠른 검색을 위한 맵
    scene_map = {s.get("scene_id"): s for s in scenes}

    bundle_inputs = []

    for bundle in bundles:
        scene_ids = bundle["scene_ids"]

        # 묶음 내 씬 데이터 수집
        individual_scenes = []
        for sid in scene_ids:
            scene = scene_map.get(sid, {})
            individual_scenes.append({
                "scene_id": sid,
                "script": _get_scene_script(scene),
                "start_time": scene.get("srt_start_time", scene.get("start_time", "")),
                "end_time": scene.get("srt_end_time", scene.get("end_time", "")),
                "duration": _get_scene_duration(scene),
            })

        bundle_input = {
            "bundle_id": bundle["bundle_id"],
            "scene_ids": scene_ids,
            "scene_count": bundle["scene_count"],
            "total_duration": bundle["total_duration"],
            "combined_script": bundle["combined_script"],
            "primary_scene_id": bundle["primary_scene_id"],
            "scenes": individual_scenes,
        }

        bundle_inputs.append(bundle_input)

    return bundle_inputs


# ═══════════════════════════════════════════════════════════════════
# 배치 분할
# ═══════════════════════════════════════════════════════════════════

def create_batches_dynamic(bundle_inputs: List[Dict]) -> List[List[Dict]]:
    """
    묶음을 배치로 분할 (동적 배치 크기)

    Args:
        bundle_inputs: 묶음 입력 데이터 리스트

    Returns:
        배치 리스트 (각 배치는 묶음 리스트)
    """
    total_bundles = len(bundle_inputs)

    # 동적 배치 크기 결정 (사용자 설정 우선)
    batch_size = calculate_dynamic_batch_size(total_bundles)

    # 배치 생성
    batches = []
    for i in range(0, total_bundles, batch_size):
        batch = bundle_inputs[i:i + batch_size]
        batches.append(batch)

    print(f"[Batch] ═══════════════════════════════════════════")
    print(f"[Batch] 묶음 수: {total_bundles}개")
    print(f"[Batch] 배치 크기: {batch_size}개 (동적 결정)")
    print(f"[Batch] 배치 수: {len(batches)}개")
    print(f"[Batch] ═══════════════════════════════════════════")

    return batches


# ═══════════════════════════════════════════════════════════════════
# 배치 파일 생성
# ═══════════════════════════════════════════════════════════════════

def save_batch_input_files(
    batches: List[List[Dict]],
    output_dir: Path
) -> List[str]:
    """
    배치별 입력 파일 저장

    Args:
        batches: 배치 리스트
        output_dir: 출력 디렉토리

    Returns:
        생성된 파일 경로 리스트
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    batch_files = []

    for idx, batch in enumerate(batches):
        # 파일 경로
        input_file = output_dir / f"batch_{idx:03d}_input.json"

        # 저장
        with open(input_file, 'w', encoding='utf-8') as f:
            json.dump(batch, f, ensure_ascii=False, indent=2)

        batch_files.append(str(input_file))

        # 통계
        total_scenes = sum(b["scene_count"] for b in batch)
        print(f"[Batch {idx}] {len(batch)}개 묶음, {total_scenes}개 씬 → {input_file.name}")

    return batch_files


# ═══════════════════════════════════════════════════════════════════
# 통합 준비 함수
# ═══════════════════════════════════════════════════════════════════

def prepare_bundle_analysis(
    scenes: List[Dict],
    output_dir: str
) -> Dict[str, Any]:
    """
    묶음 기반 분석 준비 (메인 함수)

    사용자 설정을 동적으로 읽어 묶음 및 배치 생성

    Args:
        scenes: 전체 씬 목록
        output_dir: 출력 디렉토리

    Returns:
        준비 결과 정보
    """
    # 사용자 설정 로드
    config = get_claude_code_config()

    print("\n" + "=" * 60)
    print("  묶음 기반 분석 준비")
    print("=" * 60)
    print(f"  묶음 크기: {config['bundle_size']} (사용자 선택)")
    print(f"  프롬프트: {config['prompt_template_id']}")
    print("=" * 60 + "\n")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 1. 묶음 생성 (사용자 설정 반영!)
    bundles = create_bundles_dynamic(scenes)

    # 2. 묶음별 입력 데이터 생성
    bundle_inputs = create_bundle_inputs(scenes, bundles)

    # 3. 배치 분할 (동적 크기)
    batches = create_batches_dynamic(bundle_inputs)

    # 4. 배치 파일 저장
    batch_files = save_batch_input_files(batches, output_path)

    # 5. 메타 정보 저장
    meta = {
        "prepared_at": datetime.now().isoformat(),
        "config": config,
        "total_scenes": len(scenes),
        "bundle_size": config["bundle_size"],
        "total_bundles": len(bundles),
        "total_batches": len(batches),
        "batch_files": batch_files,
        "bundles_per_batch": [len(b) for b in batches],
        "scenes_per_bundle": [b["scene_count"] for b in bundles],
    }

    meta_file = output_path / "bundle_meta.json"
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # 예상 시간 계산 (배치당 ~3분)
    estimated_time = len(batches) * 3

    print("\n" + "=" * 60)
    print("  📊 준비 완료")
    print("=" * 60)
    print(f"  총 씬: {len(scenes)}개")
    print(f"  묶음 크기: {config['bundle_size']} (사용자 선택)")
    print(f"  총 묶음: {len(bundles)}개")
    print(f"  총 배치: {len(batches)}개")
    print(f"  예상 시간: ~{estimated_time}분")
    print(f"  메타 파일: {meta_file}")
    print("=" * 60 + "\n")

    return meta


def load_bundle_meta(output_dir: str) -> Optional[Dict]:
    """배치 메타 정보 로드"""
    meta_file = Path(output_dir) / "bundle_meta.json"
    if meta_file.exists():
        with open(meta_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    import sys

    # 테스트용 더미 씬
    test_scenes = [
        {"scene_id": i, "script": f"씬 {i}의 대사입니다.", "srt_duration": 3.5}
        for i in range(1, 51)
    ]

    if len(sys.argv) > 1:
        output_dir = sys.argv[1]
    else:
        output_dir = "./test_batches"

    result = prepare_bundle_analysis(test_scenes, output_dir)
    print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False, default=str)}")
