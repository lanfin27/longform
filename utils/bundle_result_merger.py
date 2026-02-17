# -*- coding: utf-8 -*-
"""
묶음 결과 병합 유틸리티 v1.0

묶음 단위로 생성된 분석 결과를 scenes.json에 병합
- 묶음 결과 → 묶음 내 모든 씬에 동일 적용
- 한 번에 저장 (I/O 최소화)

핵심 로직:
- 묶음 1 결과 → 씬 1, 2, 3에 동일 적용
- 묶음 2 결과 → 씬 4, 5, 6에 동일 적용
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime


# 병합할 출력 필드 (분석 결과)
OUTPUT_FIELDS = [
    "image_prompt",
    "image_prompt_en",
    "image_prompt_korean_text",
    "background_prompt",
    "background_prompt_en",
    "character_prompt",
    "character_prompt_en",
    "video_prompt_character",
    "video_prompt_full",
    "visual_elements",
    "direction_guide",
    "camera_suggestion",
    "location",
    "mood",
    "characters",
]


def load_bundle_output(batch_output_path: str) -> Tuple[List[Dict], Optional[str]]:
    """
    배치 출력 파일 로드

    Args:
        batch_output_path: 배치 출력 JSON 파일 경로

    Returns:
        (묶음 결과 리스트, 에러 메시지 또는 None)
    """
    path = Path(batch_output_path)

    if not path.exists():
        return [], f"파일 없음: {path}"

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 배열인지 확인
        if not isinstance(data, list):
            if isinstance(data, dict):
                data = [data]
            else:
                return [], f"잘못된 형식: {type(data)}"

        return data, None

    except json.JSONDecodeError as e:
        return [], f"JSON 파싱 오류: {e}"
    except Exception as e:
        return [], f"로드 오류: {e}"


def merge_bundle_results_to_scenes(
    scenes: List[Dict],
    bundle_results: List[Dict],
    save_path: Optional[str] = None
) -> int:
    """
    묶음 결과를 씬에 병합

    핵심: 묶음 결과를 묶음 내 모든 씬에 동일하게 적용

    Args:
        scenes: 전체 씬 목록 (수정됨)
        bundle_results: 묶음 분석 결과 리스트
        save_path: 저장 경로 (선택)

    Returns:
        업데이트된 씬 수
    """
    # scene_id로 빠른 검색을 위한 인덱스
    scene_index = {
        s.get("scene_id"): i
        for i, s in enumerate(scenes)
    }

    updated_count = 0
    updated_scene_ids: Set[int] = set()

    for bundle_result in bundle_results:
        bundle_id = bundle_result.get("bundle_id")
        scene_ids = bundle_result.get("scene_ids", [])

        if not scene_ids:
            print(f"[Merger] ⚠️ 묶음 {bundle_id}: scene_ids 없음")
            continue

        # 묶음 결과를 묶음 내 모든 씬에 적용 (핵심!)
        for scene_id in scene_ids:
            if scene_id not in scene_index:
                print(f"[Merger] ⚠️ 씬 {scene_id} 없음 (묶음 {bundle_id})")
                continue

            idx = scene_index[scene_id]

            # 결과 필드 복사
            for field in OUTPUT_FIELDS:
                if field in bundle_result and bundle_result[field] is not None:
                    scenes[idx][field] = bundle_result[field]

            # 메타데이터 추가
            scenes[idx]["analyzed_at"] = datetime.now().isoformat()
            scenes[idx]["analyzed_bundle_id"] = bundle_id

            updated_scene_ids.add(scene_id)
            updated_count += 1

        print(f"[Merger] 묶음 {bundle_id}: {len(scene_ids)}개 씬 업데이트")

    # 저장
    if save_path:
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        print(f"[Merger] 저장 완료: {save_path}")

    print(f"[Merger] ═══════════════════════════════════════════")
    print(f"[Merger] 총 업데이트: {updated_count}개 씬")
    print(f"[Merger] 고유 씬 ID: {len(updated_scene_ids)}개")
    print(f"[Merger] ═══════════════════════════════════════════")

    return updated_count


def merge_batch_outputs_to_scenes(
    scenes_json_path: str,
    batch_output_files: List[str],
    backup: bool = True
) -> Dict:
    """
    모든 배치 출력을 scenes.json에 병합

    Args:
        scenes_json_path: scenes.json 파일 경로
        batch_output_files: 배치 출력 파일 경로 리스트
        backup: 백업 생성 여부

    Returns:
        병합 결과 정보
    """
    scenes_path = Path(scenes_json_path)

    if not scenes_path.exists():
        return {
            "success": False,
            "error": f"scenes.json 없음: {scenes_path}"
        }

    # scenes.json 로드
    print(f"[Merger] scenes.json 로드: {scenes_path}")
    with open(scenes_path, 'r', encoding='utf-8') as f:
        scenes = json.load(f)

    original_count = len(scenes)

    # 백업
    if backup:
        backup_path = scenes_path.parent / f"scenes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        print(f"[Merger] 백업 생성: {backup_path}")

    # 통계
    total_merged = 0
    failed_batches = []
    all_bundle_results = []

    # 각 배치 파일 처리
    for batch_file in batch_output_files:
        batch_name = Path(batch_file).name
        print(f"[Merger] 처리 중: {batch_name}")

        bundle_results, error = load_bundle_output(batch_file)

        if error:
            print(f"[Merger]   ⚠️ {error}")
            failed_batches.append({
                "file": batch_file,
                "error": error
            })
            continue

        all_bundle_results.extend(bundle_results)
        print(f"[Merger]   ✅ {len(bundle_results)}개 묶음 로드")

    # 한 번에 병합
    if all_bundle_results:
        total_merged = merge_bundle_results_to_scenes(
            scenes=scenes,
            bundle_results=all_bundle_results,
            save_path=str(scenes_path)
        )

    # 결과
    result = {
        "success": len(failed_batches) == 0,
        "scenes_json_path": str(scenes_path),
        "original_scenes": original_count,
        "merged_scenes": total_merged,
        "total_bundles": len(all_bundle_results),
        "total_batches": len(batch_output_files),
        "failed_batches": failed_batches,
        "merged_at": datetime.now().isoformat()
    }

    print("\n" + "=" * 60)
    print("  📊 병합 완료")
    print("=" * 60)
    print(f"  원본 씬: {original_count}개")
    print(f"  업데이트된 씬: {total_merged}개")
    print(f"  처리된 묶음: {len(all_bundle_results)}개")
    print(f"  실패한 배치: {len(failed_batches)}개")
    print("=" * 60 + "\n")

    return result


def merge_from_bundle_meta(bundle_meta_path: str, backup: bool = True) -> Dict:
    """
    묶음 메타 파일을 사용하여 결과 병합

    Args:
        bundle_meta_path: bundle_meta.json 파일 경로
        backup: 백업 생성 여부

    Returns:
        병합 결과 정보
    """
    meta_path = Path(bundle_meta_path)

    if not meta_path.exists():
        return {
            "success": False,
            "error": f"메타 파일 없음: {meta_path}"
        }

    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    # 출력 파일 경로 생성
    batch_files = meta.get("batch_files", [])
    batch_output_files = [
        bf.replace("_input.json", "_output.json")
        for bf in batch_files
    ]

    # scenes.json 경로 추정
    batch_dir = meta_path.parent
    project_dir = batch_dir.parent.parent.parent  # logs/claude_code/batches → project
    scenes_json_path = project_dir / "analysis" / "scenes.json"

    if not scenes_json_path.exists():
        # 대안 경로 시도
        scenes_json_path = batch_dir.parent / "scenes.json"

    return merge_batch_outputs_to_scenes(
        scenes_json_path=str(scenes_json_path),
        batch_output_files=batch_output_files,
        backup=backup
    )


def get_bundle_merge_status(batch_dir: str) -> Dict:
    """
    묶음 병합 상태 확인

    Args:
        batch_dir: 배치 디렉토리 경로

    Returns:
        상태 정보 딕셔너리
    """
    batch_path = Path(batch_dir)
    meta_file = batch_path / "bundle_meta.json"

    if not meta_file.exists():
        return {"status": "not_prepared"}

    with open(meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    # 출력 파일 확인
    batch_files = meta.get("batch_files", [])
    completed = []
    pending = []

    for bf in batch_files:
        output_file = bf.replace("_input.json", "_output.json")
        output_path = Path(output_file)
        if output_path.exists():
            # 파일 크기 확인
            size = output_path.stat().st_size
            completed.append({
                "file": output_path.name,
                "size": size
            })
        else:
            pending.append(Path(bf).name.replace("_input.json", "_output.json"))

    return {
        "total_batches": len(batch_files),
        "completed": len(completed),
        "pending": len(pending),
        "completed_files": completed,
        "pending_files": pending,
        "ready_to_merge": len(pending) == 0 and len(completed) > 0,
        "config": meta.get("config", {})
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python bundle_result_merger.py <bundle_meta.json>")
        print("  python bundle_result_merger.py <scenes.json> <output1.json> <output2.json> ...")
        sys.exit(1)

    if "bundle_meta.json" in sys.argv[1]:
        # 메타 파일 사용
        result = merge_from_bundle_meta(sys.argv[1])
    else:
        # 직접 파일 지정
        scenes_path = sys.argv[1]
        output_files = sys.argv[2:]
        result = merge_batch_outputs_to_scenes(scenes_path, output_files)

    print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False)}")
