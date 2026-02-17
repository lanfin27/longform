# -*- coding: utf-8 -*-
"""
묶음 기반 Claude Code 씬 분석 실행 스크립트 v1.1

사용자 설정을 동적으로 반영하여 최적화된 분석 실행:
- 묶음 크기: 사용자 선택 (하드코딩 금지!)
- 프롬프트 템플릿: 사용자 선택
- 배치 크기: 동적 결정

v1.1 업데이트:
- 최적화 모드 추가 (--optimized)
- 토큰 초과 방지 규칙 강화
- bundle_info_claude_code.json 지원

사용법:
    python scripts/run_bundle_analysis.py <video_path> [options]

예시:
    python scripts/run_bundle_analysis.py "data/projects/시니어/videos/test15"
    python scripts/run_bundle_analysis.py "data/projects/시니어/videos/test15" --prepare-only
    python scripts/run_bundle_analysis.py "data/projects/시니어/videos/test15" --optimized
    python scripts/run_bundle_analysis.py "data/projects/시니어/videos/test15" --merge-only
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

from utils.claude_code_config import (
    get_claude_code_config,
    get_prompt_template_path,
    get_additional_instructions,
    print_config_summary
)
from utils.dynamic_bundle_creator import (
    prepare_bundle_analysis,
    load_bundle_meta
)
from utils.bundle_result_merger import (
    merge_batch_outputs_to_scenes,
    merge_from_bundle_meta,
    get_bundle_merge_status
)
from utils.claude_code_prompt_optimizer import (
    prepare_claude_code_analysis,
    generate_bundle_info_for_claude_code
)


# ═══════════════════════════════════════════════════════════════════
# Claude Code 프롬프트 템플릿
# ═══════════════════════════════════════════════════════════════════

CLAUDE_CODE_BATCH_PROMPT = '''# 🎬 Claude Code 씬 분석 - 배치 {batch_idx}/{total_batches}

## ⚡ 핵심 설정 (사용자 선택값!)

- **묶음 크기**: {bundle_size}개 씬/묶음
- **이 배치의 묶음 수**: {bundle_count}개
- **프롬프트 템플릿**: {prompt_template_info}

---

## 📋 실행 지침

### 1. 프롬프트 템플릿 읽기 (필수!)
{prompt_template_section}

### 2. 입력 데이터 읽기
묶음별로 정리된 씬 데이터:
```
{batch_input_file}
```

각 묶음에는 다음 정보가 포함되어 있습니다:
- `bundle_id`: 묶음 ID
- `scene_ids`: 묶음에 포함된 씬 ID 배열
- `combined_script`: 묶음 내 **모든 씬의 스크립트 합본** (핵심!)
- `scenes`: 개별 씬 정보

### 3. 분석 방식 (핵심!)
- 각 묶음의 `combined_script` 필드에서 **묶음 내 모든 씬의 내용**을 확인하세요
- 프롬프트 템플릿의 규칙에 따라 분석하고, **묶음 단위**로 결과 생성
- 묶음 내 모든 씬에 동일한 프롬프트가 적용됩니다

### 4. 출력 형식
```json
[
  {{
    "bundle_id": 1,
    "scene_ids": [1, 2, 3],
    "image_prompt": "...",
    "image_prompt_en": "...",
    "image_prompt_korean_text": "...",
    "background_prompt": "...",
    "background_prompt_en": "...",
    "character_prompt": "...",
    "character_prompt_en": "...",
    "video_prompt_character": "...",
    "video_prompt_full": "...",
    "visual_elements": [...],
    "direction_guide": "...",
    "camera_suggestion": "...",
    "location": "...",
    "mood": "...",
    "characters": [...]
  }},
  ...
]
```

### 5. 출력 파일
```
{batch_output_file}
```

{additional_instructions_section}

---

## ⚠️ 중요 규칙 (반드시 준수!)

### 필수 규칙
1. **프롬프트 템플릿 규칙 100% 준수** - 템플릿의 모든 규칙 적용
2. **묶음 내 모든 씬 분석** - combined_script 전체 내용 분석
3. **scenes.json 직접 수정 금지** - 출력 파일만 생성
4. **묶음 단위 출력** - 씬별 개별 출력 금지
5. **scene_ids 필드 필수** - 병합 시 필요

### 금지 사항 (토큰 초과 방지)
6. **scenes.json 전체 읽기 금지** - 입력 파일만 사용
7. **Task() / 백그라운드 에이전트 금지** - 직접 처리만
8. **Python 스크립트 생성/실행 금지** - Edit/Write tool만 사용
9. **추가 질문 금지** - 즉시 실행할 것

---

## 🎯 작업 시작

1. 프롬프트 템플릿 읽기 (있는 경우)
2. `{batch_input_file}` 읽기
3. 각 묶음의 combined_script를 템플릿 규칙에 따라 분석
4. 결과를 `{batch_output_file}`에 저장
'''


def generate_batch_prompt(
    batch_idx: int,
    total_batches: int,
    batch_input_file: str,
    batch_output_file: str,
    bundle_count: int,
    config: dict
) -> str:
    """
    배치 실행용 Claude Code 프롬프트 생성

    사용자 설정을 동적으로 반영
    """
    bundle_size = config.get("bundle_size", 5)
    prompt_template_path = config.get("prompt_template_path")
    additional_instructions = config.get("additional_instructions", "")

    # 프롬프트 템플릿 섹션
    if prompt_template_path and Path(prompt_template_path).exists():
        prompt_template_section = f"""아래 경로의 프롬프트 템플릿을 **먼저 읽고**, 그 규칙에 따라 분석하세요:
```
{prompt_template_path}
```"""
        prompt_template_info = prompt_template_path
    else:
        prompt_template_section = "프롬프트 템플릿이 지정되지 않았습니다. 기본 규칙을 사용합니다."
        prompt_template_info = "(기본 규칙 사용)"

    # 추가 지시사항 섹션
    additional_section = ""
    if additional_instructions:
        additional_section = f"""
---

## 📝 추가 지시사항 (사용자 입력)

{additional_instructions}
"""

    prompt = CLAUDE_CODE_BATCH_PROMPT.format(
        batch_idx=batch_idx + 1,
        total_batches=total_batches,
        bundle_size=bundle_size,
        bundle_count=bundle_count,
        prompt_template_info=prompt_template_info,
        prompt_template_section=prompt_template_section,
        batch_input_file=batch_input_file,
        batch_output_file=batch_output_file,
        additional_instructions_section=additional_section
    )

    return prompt


def print_header(title: str):
    """섹션 헤더 출력"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


# ═══════════════════════════════════════════════════════════════════
# 메인 실행 함수들
# ═══════════════════════════════════════════════════════════════════

def run_prepare(args) -> dict:
    """1단계: 묶음 및 배치 준비"""
    print_header("Step 1: 묶음 및 배치 준비")

    project_path = Path(args.video_path)
    scenes_json = project_path / "analysis" / "scenes.json"
    batch_dir = project_path / "logs" / "claude_code" / "bundles"

    if not scenes_json.exists():
        print(f"[Error] scenes.json 없음: {scenes_json}")
        return {"status": "error", "error": "scenes.json not found"}

    # scenes.json 로드
    with open(scenes_json, 'r', encoding='utf-8') as f:
        scenes = json.load(f)

    print(f"[Prepare] 씬 로드: {len(scenes)}개")

    # 묶음 준비 (사용자 설정 동적 반영!)
    meta = prepare_bundle_analysis(scenes, str(batch_dir))

    return meta


def run_generate_prompts(args, meta: dict) -> list:
    """2단계: 배치별 프롬프트 생성"""
    print_header("Step 2: 배치별 프롬프트 생성")

    config = meta.get("config", get_claude_code_config())
    batch_files = meta.get("batch_files", [])
    total_batches = len(batch_files)

    if total_batches == 0:
        print("[Skip] 생성할 배치 없음")
        return []

    batch_dir = Path(batch_files[0]).parent
    prompt_files = []

    for idx, input_file in enumerate(batch_files):
        output_file = input_file.replace("_input.json", "_output.json")

        # 배치 내 묶음 수 확인
        with open(input_file, 'r', encoding='utf-8') as f:
            batch_data = json.load(f)
        bundle_count = len(batch_data)

        # 프롬프트 생성
        prompt_content = generate_batch_prompt(
            batch_idx=idx,
            total_batches=total_batches,
            batch_input_file=input_file,
            batch_output_file=output_file,
            bundle_count=bundle_count,
            config=config
        )

        # 저장
        prompt_file = batch_dir / f"prompt_batch_{idx:03d}.md"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt_content)

        prompt_files.append(str(prompt_file))
        print(f"[Prompt {idx + 1}/{total_batches}] {prompt_file.name} ({bundle_count}개 묶음)")

    print(f"\n[Prompt] 총 {len(prompt_files)}개 프롬프트 생성 완료")
    return prompt_files


def run_batch_execution(args, meta: dict, prompt_files: list) -> dict:
    """3단계: Claude Code 배치 실행"""
    print_header("Step 3: Claude Code 배치 실행")

    if not prompt_files:
        print("[Skip] 실행할 프롬프트 없음")
        return {"status": "skipped"}

    config = meta.get("config", get_claude_code_config())
    timeout = config.get("timeout", 600)
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
                "status": "dry_run"
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
                timeout=timeout
            )

            if result.returncode == 0:
                print(f"  ✅ 완료")
                results["success"] += 1
                results["details"].append({
                    "batch": idx,
                    "status": "success"
                })
            else:
                error_msg = result.stderr[:200] if result.stderr else "Unknown error"
                print(f"  ⚠️ 오류: {error_msg}")
                results["failed"] += 1
                results["details"].append({
                    "batch": idx,
                    "status": "failed",
                    "error": error_msg
                })

        except subprocess.TimeoutExpired:
            print(f"  ⚠️ 타임아웃 ({timeout}초)")
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


def run_merge(args, meta: dict) -> dict:
    """4단계: 결과 병합"""
    print_header("Step 4: 결과 병합")

    batch_files = meta.get("batch_files", [])
    if not batch_files:
        print("[Skip] 병합할 배치 없음")
        return {"status": "skipped"}

    # 출력 파일 경로
    batch_output_files = [
        bf.replace("_input.json", "_output.json")
        for bf in batch_files
    ]

    # scenes.json 경로
    project_path = Path(args.video_path)
    scenes_json = project_path / "analysis" / "scenes.json"

    # 상태 확인
    batch_dir = Path(batch_files[0]).parent
    status = get_bundle_merge_status(str(batch_dir))

    print(f"[Merge] 완료된 배치: {status['completed']}/{status['total_batches']}")

    if status["pending"]:
        print(f"[Merge] 대기 중인 배치: {status['pending_files']}")

        if not args.partial_merge:
            print("[Merge] 모든 배치 완료 후 병합하세요 (--partial-merge 옵션 사용 가능)")
            return {"status": "pending", "pending_batches": status["pending_files"]}

    # 병합 실행
    return merge_batch_outputs_to_scenes(
        scenes_json_path=str(scenes_json),
        batch_output_files=batch_output_files,
        backup=True
    )


# ═══════════════════════════════════════════════════════════════════
# 전체 파이프라인
# ═══════════════════════════════════════════════════════════════════

def run_full_pipeline(args):
    """전체 파이프라인 실행"""
    start_time = datetime.now()

    print_header("🚀 묶음 기반 Claude Code 씬 분석")

    # 사용자 설정 출력
    print_config_summary()

    # 1. 준비
    meta = run_prepare(args)
    if meta.get("status") == "error":
        print(f"\n[Error] 준비 실패: {meta.get('error')}")
        return 1

    # 2. 프롬프트 생성
    prompt_files = run_generate_prompts(args, meta)

    # 3. 실행 (선택적)
    if not args.prepare_only:
        exec_results = run_batch_execution(args, meta, prompt_files)

        # 4. 병합
        if not args.dry_run:
            merge_result = run_merge(args, meta)

    # 완료 요약
    elapsed = datetime.now() - start_time

    print_header("📊 완료 요약")
    print(f"  총 소요 시간: {elapsed}")
    print(f"  묶음 크기: {meta.get('bundle_size', '?')} (사용자 선택)")
    print(f"  총 씬: {meta.get('total_scenes', '?')}개")
    print(f"  총 묶음: {meta.get('total_bundles', '?')}개")
    print(f"  총 배치: {meta.get('total_batches', '?')}개")

    if args.prepare_only:
        batch_dir = Path(meta.get("batch_files", [""])[0]).parent if meta.get("batch_files") else "?"
        print(f"\n[Info] --prepare-only 모드: 배치 파일만 생성됨")
        print(f"  배치 디렉토리: {batch_dir}")
        print(f"\n다음 단계:")
        print(f"  1. Claude Code에서 각 배치 실행")
        print(f"  2. python scripts/run_bundle_analysis.py {args.video_path} --merge-only")

    return 0


def run_status(args):
    """상태 확인"""
    project_path = Path(args.video_path)
    batch_dir = project_path / "logs" / "claude_code" / "bundles"

    status = get_bundle_merge_status(str(batch_dir))

    print_header("배치 처리 상태")
    print(json.dumps(status, indent=2, ensure_ascii=False))


def run_merge_only(args):
    """병합만 실행"""
    project_path = Path(args.video_path)
    batch_dir = project_path / "logs" / "claude_code" / "bundles"
    meta_file = batch_dir / "bundle_meta.json"

    if not meta_file.exists():
        print(f"[Error] 메타 파일 없음: {meta_file}")
        return 1

    result = merge_from_bundle_meta(str(meta_file), backup=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if result.get("success", False) else 1


def run_optimized(args):
    """최적화 모드 실행 (토큰 초과 방지)"""
    print_header("Claude Code 최적화 분석 준비")

    project_path = Path(args.video_path)
    scenes_json = project_path / "analysis" / "scenes.json"

    if not scenes_json.exists():
        print(f"[Error] scenes.json 없음: {scenes_json}")
        return 1

    # scenes.json 로드
    with open(scenes_json, 'r', encoding='utf-8') as f:
        scenes = json.load(f)

    print(f"[Optimized] 씬 로드: {len(scenes)}개")

    # 최적화된 분석 준비
    result = prepare_claude_code_analysis(
        scenes=scenes,
        project_path=str(project_path)
    )

    print("\n" + "=" * 60)
    print("  최적화 분석 준비 완료")
    print("=" * 60)
    print(f"  Bundle Info: {result['bundle_info_path']}")
    print(f"  프롬프트: {result['prompt_path']}")
    print(f"  총 씬: {result['summary']['total_scenes']}개")
    print(f"  총 묶음: {result['summary']['total_bundles']}개")
    print("=" * 60)

    print("\n[적용된 규칙]")
    rules = result.get('rules', {})
    for rule, value in rules.items():
        status = "O" if value else "X"
        print(f"  [{status}] {rule}")

    print(f"\n[다음 단계]")
    print(f"  1. Claude Code에서 최적화 프롬프트 실행:")
    print(f"     claude \"@{result['prompt_path']}\"")
    print(f"  2. 또는 bundle_info 파일 참조하여 수동 처리")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="묶음 기반 Claude Code 씬 분석 (사용자 설정 동적 반영)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 전체 파이프라인 실행
  python scripts/run_bundle_analysis.py "data/projects/시니어/videos/test15"

  # 배치 준비만 (수동 실행용)
  python scripts/run_bundle_analysis.py "..." --prepare-only

  # 상태 확인
  python scripts/run_bundle_analysis.py "..." --status

  # 병합만 실행
  python scripts/run_bundle_analysis.py "..." --merge-only

사용자 설정 동적 반영:
  - 묶음 크기: session_state['bundle_size'] 또는 settings
  - 프롬프트 템플릿: session_state['prompt_template_id']
  - 타임아웃: session_state['claude_code_timeout']
        """
    )

    parser.add_argument(
        "video_path",
        help="비디오 프로젝트 경로"
    )

    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="배치 파일만 생성 (실행 안함)"
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="상태만 확인"
    )

    parser.add_argument(
        "--merge-only",
        action="store_true",
        help="병합만 실행"
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

    parser.add_argument(
        "--optimized",
        action="store_true",
        help="최적화 모드: bundle_info_claude_code.json 및 토큰 제한 규칙 적용"
    )

    args = parser.parse_args()

    # 경로 정규화
    args.video_path = str(Path(args.video_path).resolve())

    # 실행 모드 선택
    if args.status:
        return run_status(args)
    elif args.merge_only:
        return run_merge_only(args)
    elif args.optimized:
        return run_optimized(args)
    else:
        return run_full_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
