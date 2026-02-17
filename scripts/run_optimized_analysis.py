# -*- coding: utf-8 -*-
"""
최적화된 씬 분석 실행 스크립트 v1.0

배치 처리를 통한 대량 씬 분석 최적화:
- 기존: 318개 씬 → 318회 Update → ~2시간
- 최적화: 318개 씬 → 7배치 → 7회 저장 → ~20분

사용법:
    python scripts/run_optimized_analysis.py <video_path> [--batch-size 50] [--template <path>]

예시:
    python scripts/run_optimized_analysis.py "data/projects/시니어/videos/test15"
    python scripts/run_optimized_analysis.py "data/projects/시니어/videos/test15" --batch-size 30
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# 프로젝트 루트 추가
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.scene_analysis_optimizer import (
    prepare_batch_analysis,
    get_batch_status,
    SceneAnalysisOptimizer
)
from utils.batch_prompt_generator import (
    generate_all_batch_prompts,
    generate_master_prompt
)
from utils.batch_result_merger import (
    merge_batch_results_to_scenes,
    merge_from_batch_meta,
    get_merge_status,
    partial_merge
)


def print_header(title: str):
    """섹션 헤더 출력"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def run_prepare(args) -> dict:
    """1단계: 배치 준비"""
    print_header("Step 1/4: 배치 준비")

    project_path = Path(args.video_path)
    scenes_json = project_path / "analysis" / "scenes.json"
    batch_dir = project_path / "logs" / "claude_code" / "batches"

    if not scenes_json.exists():
        print(f"[Error] scenes.json 없음: {scenes_json}")
        return {"status": "error", "error": "scenes.json not found"}

    batch_info = prepare_batch_analysis(
        str(scenes_json),
        str(batch_dir),
        batch_size=args.batch_size
    )

    return batch_info


def run_generate_prompts(args, batch_info: dict) -> list:
    """2단계: 배치별 프롬프트 생성"""
    print_header("Step 2/4: 배치별 프롬프트 생성")

    if batch_info.get("status") == "already_complete":
        print("[Skip] 모든 씬이 이미 분석됨")
        return []

    output_dir = batch_info.get("output_dir")

    # 프롬프트 생성
    prompt_files = generate_all_batch_prompts(
        batch_info=batch_info,
        template_path=args.template or "",
        output_dir=output_dir
    )

    # 마스터 프롬프트 생성
    generate_master_prompt(
        batch_info=batch_info,
        output_dir=output_dir,
        template_path=args.template or ""
    )

    return prompt_files


def run_batch_analysis(args, batch_info: dict, prompt_files: list) -> dict:
    """3단계: Claude Code 배치 실행"""
    print_header("Step 3/4: Claude Code 배치 실행")

    if not prompt_files:
        print("[Skip] 실행할 프롬프트 없음")
        return {"status": "skipped"}

    project_path = Path(args.video_path)
    results = {
        "total": len(prompt_files),
        "success": 0,
        "failed": 0,
        "details": []
    }

    for idx, prompt_file in enumerate(prompt_files):
        print(f"\n[Batch {idx + 1}/{len(prompt_files)}] 실행 중...")
        print(f"  프롬프트: {Path(prompt_file).name}")

        if args.dry_run:
            print(f"  [Dry Run] 실제 실행 스킵")
            results["details"].append({
                "batch": idx,
                "status": "dry_run",
                "prompt_file": prompt_file
            })
            continue

        # Claude Code 실행
        cmd = f'claude --dangerously-skip-permissions "@{prompt_file}"'

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=args.timeout * 60  # 분 → 초
            )

            if result.returncode == 0:
                print(f"  ✅ 완료")
                results["success"] += 1
                results["details"].append({
                    "batch": idx,
                    "status": "success",
                    "prompt_file": prompt_file
                })
            else:
                print(f"  ⚠️ 오류: {result.stderr[:200] if result.stderr else 'Unknown error'}")
                results["failed"] += 1
                results["details"].append({
                    "batch": idx,
                    "status": "failed",
                    "error": result.stderr[:500] if result.stderr else "Unknown error"
                })

        except subprocess.TimeoutExpired:
            print(f"  ⚠️ 타임아웃 ({args.timeout}분)")
            results["failed"] += 1
            results["details"].append({
                "batch": idx,
                "status": "timeout"
            })

        except Exception as e:
            print(f"  ❌ 예외: {e}")
            results["failed"] += 1
            results["details"].append({
                "batch": idx,
                "status": "exception",
                "error": str(e)
            })

    return results


def run_merge(args, batch_info: dict) -> dict:
    """4단계: 결과 병합"""
    print_header("Step 4/4: 결과 병합")

    if batch_info.get("status") == "already_complete":
        print("[Skip] 이미 완료됨")
        return {"status": "skipped"}

    batch_dir = batch_info.get("output_dir")
    meta_file = Path(batch_dir) / "batch_meta.json"

    if not meta_file.exists():
        print(f"[Error] 메타 파일 없음: {meta_file}")
        return {"status": "error", "error": "Meta file not found"}

    # 병합 상태 확인
    status = get_merge_status(batch_dir)
    print(f"[Merger] 완료된 배치: {status['completed']}/{status['total_batches']}")

    if status["pending"]:
        print(f"[Merger] 대기 중인 배치: {status['pending_files']}")

        if args.partial_merge:
            print("[Merger] 부분 병합 실행...")
            batch_files = batch_info.get("batch_files", [])
            output_files = [
                bf.replace("_input.json", "_output.json")
                for bf in batch_files
            ]
            return partial_merge(
                batch_info.get("scenes_json_path"),
                output_files,
                backup=True
            )
        else:
            print("[Merger] 모든 배치 완료 후 병합하세요 (--partial-merge 옵션 사용 가능)")
            return {"status": "pending", "pending_batches": status["pending_files"]}

    # 전체 병합
    return merge_from_batch_meta(str(meta_file), backup=True)


def run_full_pipeline(args):
    """전체 파이프라인 실행"""
    start_time = datetime.now()

    print_header("최적화된 씬 분석 시작")
    print(f"프로젝트: {args.video_path}")
    print(f"배치 크기: {args.batch_size}")
    print(f"타임아웃: {args.timeout}분/배치")
    if args.dry_run:
        print("모드: Dry Run (실제 실행 안함)")

    # 1. 배치 준비
    batch_info = run_prepare(args)

    if batch_info.get("status") == "error":
        print(f"\n[Error] 배치 준비 실패: {batch_info.get('error')}")
        return 1

    if batch_info.get("status") == "already_complete":
        print("\n✅ 모든 씬이 이미 분석되었습니다!")
        return 0

    # 2. 프롬프트 생성
    prompt_files = run_generate_prompts(args, batch_info)

    # 3. 배치 실행 (선택적)
    if not args.prepare_only:
        analysis_results = run_batch_analysis(args, batch_info, prompt_files)

        # 4. 결과 병합
        if not args.dry_run:
            merge_result = run_merge(args, batch_info)

    # 완료 요약
    elapsed = datetime.now() - start_time
    print_header("완료 요약")
    print(f"총 소요 시간: {elapsed}")
    print(f"처리된 씬: {batch_info.get('unanalyzed_scenes', 0)}개")
    print(f"배치 수: {batch_info.get('batches', 0)}개")

    if args.prepare_only:
        print("\n[Info] --prepare-only 모드: 배치 파일만 생성됨")
        print(f"배치 디렉토리: {batch_info.get('output_dir')}")
        print("\n다음 단계:")
        print(f"  1. Claude Code에서 각 배치 실행")
        print(f"  2. python scripts/run_optimized_analysis.py {args.video_path} --merge-only")

    return 0


def run_status(args):
    """배치 상태 확인"""
    project_path = Path(args.video_path)
    batch_dir = project_path / "logs" / "claude_code" / "batches"

    status = get_batch_status(str(batch_dir))

    print_header("배치 처리 상태")
    print(json.dumps(status, indent=2, ensure_ascii=False))


def run_merge_only(args):
    """병합만 실행"""
    project_path = Path(args.video_path)
    batch_dir = project_path / "logs" / "claude_code" / "batches"
    meta_file = batch_dir / "batch_meta.json"

    if not meta_file.exists():
        print(f"[Error] 메타 파일 없음: {meta_file}")
        print("먼저 --prepare-only로 배치를 준비하세요.")
        return 1

    with open(meta_file, 'r', encoding='utf-8') as f:
        batch_info = json.load(f)

    result = run_merge(args, batch_info)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if result.get("success", False) else 1


def main():
    parser = argparse.ArgumentParser(
        description="최적화된 씬 분석 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 전체 파이프라인 실행
  python scripts/run_optimized_analysis.py "data/projects/시니어/videos/test15"

  # 배치 준비만 (Claude Code에서 수동 실행)
  python scripts/run_optimized_analysis.py "data/projects/시니어/videos/test15" --prepare-only

  # 상태 확인
  python scripts/run_optimized_analysis.py "data/projects/시니어/videos/test15" --status

  # 병합만 실행
  python scripts/run_optimized_analysis.py "data/projects/시니어/videos/test15" --merge-only

  # Dry Run (실제 실행 없이 테스트)
  python scripts/run_optimized_analysis.py "data/projects/시니어/videos/test15" --dry-run
        """
    )

    parser.add_argument(
        "video_path",
        help="비디오 프로젝트 경로 (예: data/projects/시니어/videos/test15)"
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="배치당 씬 수 (기본값: 50)"
    )

    parser.add_argument(
        "--template",
        help="프롬프트 템플릿 파일 경로"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="배치당 타임아웃 (분, 기본값: 10)"
    )

    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="배치 파일만 생성 (Claude Code 실행 안함)"
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="배치 처리 상태만 확인"
    )

    parser.add_argument(
        "--merge-only",
        action="store_true",
        help="결과 병합만 실행"
    )

    parser.add_argument(
        "--partial-merge",
        action="store_true",
        help="완료된 배치만 부분 병합"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 실행 없이 테스트"
    )

    args = parser.parse_args()

    # 경로 정규화
    args.video_path = str(Path(args.video_path).resolve())

    # 실행 모드 선택
    if args.status:
        return run_status(args)
    elif args.merge_only:
        return run_merge_only(args)
    else:
        return run_full_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
