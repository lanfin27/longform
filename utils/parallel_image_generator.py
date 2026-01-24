# -*- coding: utf-8 -*-
"""
병렬 이미지 생성기 v1.0

ImageFX 이미지를 병렬로 생성하여 배치 처리 속도 향상

기능:
- 워커 풀: 여러 Node.js 프로세스 관리
- ThreadPoolExecutor: Python 스레드에서 병렬 요청
- 자동 재시도: 실패 시 재시도
- 진행률 콜백: 실시간 진행 상황 보고

사용법:
    from utils.parallel_image_generator import ParallelImageGenerator

    generator = ParallelImageGenerator(max_workers=4)
    results = generator.generate_batch(tasks, progress_callback=update_progress)
"""

import os
import json
import time
import uuid
import subprocess
import threading
import atexit
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass


@dataclass
class GenerationTask:
    """이미지 생성 태스크"""
    task_id: str
    scene_id: int
    prompt: str
    output_path: str
    model: str = "IMAGEN_4"
    aspect_ratio: str = "LANDSCAPE"
    seed: Optional[int] = None
    negative_prompt: str = ""
    timeout: int = 180


@dataclass
class GenerationResult:
    """이미지 생성 결과"""
    task_id: str
    scene_id: int
    success: bool
    path: Optional[str] = None
    seed: Optional[int] = None
    error: Optional[str] = None
    elapsed_time: float = 0


class ImageFXWorkerPool:
    """
    ImageFX 워커 풀

    여러 Node.js 워커 프로세스를 관리하여 병렬 처리 지원
    """

    _instance: Optional['ImageFXWorkerPool'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, pool_size: int = 4):
        if self._initialized:
            return

        self.pool_size = pool_size
        self.workers: List[subprocess.Popen] = []
        self.available: List[subprocess.Popen] = []
        self.worker_lock = threading.Lock()
        self.cookie: Optional[str] = None
        self.project_root = str(Path(__file__).parent.parent)
        self.worker_script = str(Path(__file__).parent / "imagefx_worker.js")
        self.request_count = 0
        self._initialized = True

        # 종료 시 정리
        atexit.register(self._cleanup_all)

        print(f"[WorkerPool] ✅ 워커 풀 초기화됨 (최대 {pool_size}개)")

    def initialize(self, cookie: str) -> bool:
        """워커 풀 초기화 (쿠키 설정)"""
        if not cookie:
            print("[WorkerPool] ❌ 쿠키가 없습니다")
            return False

        self.cookie = cookie
        print(f"[WorkerPool] ✅ 쿠키 설정됨 (길이: {len(cookie)})")
        return True

    def _create_worker(self) -> Optional[subprocess.Popen]:
        """새 워커 프로세스 생성"""
        if not Path(self.worker_script).exists():
            print(f"[WorkerPool] ❌ 워커 스크립트 없음: {self.worker_script}")
            return None

        try:
            process = subprocess.Popen(
                ["node", self.worker_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.project_root,
                encoding='utf-8',
                errors='replace',
                bufsize=1
            )

            # 시작 대기
            time.sleep(0.3)

            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr else ""
                print(f"[WorkerPool] ❌ 워커 시작 실패: {stderr[:200]}")
                return None

            # 초기화
            if self.cookie:
                init_request = json.dumps({"type": "init", "cookie": self.cookie}) + "\n"
                process.stdin.write(init_request)
                process.stdin.flush()

                response_line = process.stdout.readline()
                if response_line:
                    response = json.loads(response_line.strip())
                    if not response.get("success"):
                        print(f"[WorkerPool] ❌ 워커 초기화 실패: {response.get('error')}")
                        process.kill()
                        return None

            print(f"[WorkerPool] ✅ 워커 생성됨 (PID: {process.pid})")
            return process

        except Exception as e:
            print(f"[WorkerPool] ❌ 워커 생성 오류: {e}")
            return None

    def get_worker(self) -> Optional[subprocess.Popen]:
        """사용 가능한 워커 반환 (없으면 생성)"""
        with self.worker_lock:
            # 사용 가능한 워커가 있으면 반환
            if self.available:
                worker = self.available.pop()
                # 워커가 살아있는지 확인
                if worker.poll() is None:
                    return worker
                # 죽은 워커면 버리고 새로 생성

            # 풀 크기 미만이면 새로 생성
            if len(self.workers) < self.pool_size:
                worker = self._create_worker()
                if worker:
                    self.workers.append(worker)
                    return worker

            # 풀이 가득 찼으면 대기 후 재시도
            return None

    def return_worker(self, worker: subprocess.Popen):
        """워커 반환"""
        with self.worker_lock:
            if worker.poll() is None:  # 살아있으면
                self.available.append(worker)
            else:
                # 죽은 워커는 리스트에서 제거
                if worker in self.workers:
                    self.workers.remove(worker)

    def generate_image(self, task: GenerationTask) -> GenerationResult:
        """단일 이미지 생성"""
        start_time = time.time()

        # 워커 획득 (최대 30초 대기)
        worker = None
        for _ in range(60):
            worker = self.get_worker()
            if worker:
                break
            time.sleep(0.5)

        if not worker:
            return GenerationResult(
                task_id=task.task_id,
                scene_id=task.scene_id,
                success=False,
                error="No available worker"
            )

        try:
            # 네거티브 적용
            final_prompt = task.prompt
            if task.negative_prompt:
                final_prompt = f"{task.prompt.rstrip('.')}. AVOID: {task.negative_prompt}"

            request = {
                "type": "generate",
                "prompt": final_prompt,
                "outputPath": task.output_path,
                "model": task.model,
                "aspectRatio": task.aspect_ratio,
                "count": 1
            }

            if task.seed is not None:
                request["seed"] = task.seed

            # 요청 전송
            request_json = json.dumps(request) + "\n"
            worker.stdin.write(request_json)
            worker.stdin.flush()

            # 응답 대기
            response_line = worker.stdout.readline()

            if not response_line:
                return GenerationResult(
                    task_id=task.task_id,
                    scene_id=task.scene_id,
                    success=False,
                    error="No response from worker",
                    elapsed_time=time.time() - start_time
                )

            response = json.loads(response_line.strip())
            elapsed = time.time() - start_time

            if response.get("success"):
                self.request_count += 1
                return GenerationResult(
                    task_id=task.task_id,
                    scene_id=task.scene_id,
                    success=True,
                    path=response.get("path"),
                    seed=response.get("seed"),
                    elapsed_time=elapsed
                )
            else:
                return GenerationResult(
                    task_id=task.task_id,
                    scene_id=task.scene_id,
                    success=False,
                    error=response.get("error", "Unknown error"),
                    elapsed_time=elapsed
                )

        except Exception as e:
            return GenerationResult(
                task_id=task.task_id,
                scene_id=task.scene_id,
                success=False,
                error=str(e),
                elapsed_time=time.time() - start_time
            )
        finally:
            self.return_worker(worker)

    def _cleanup_all(self):
        """모든 워커 정리"""
        with self.worker_lock:
            for worker in self.workers:
                if worker.poll() is None:
                    try:
                        worker.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
                        worker.stdin.flush()
                        worker.wait(timeout=3)
                    except:
                        worker.kill()

            self.workers.clear()
            self.available.clear()

        print(f"[WorkerPool] 워커 풀 종료됨 (총 요청: {self.request_count}개)")

    @classmethod
    def get_instance(cls, pool_size: int = 4) -> 'ImageFXWorkerPool':
        """싱글톤 인스턴스 반환"""
        instance = cls(pool_size)
        return instance


class ParallelImageGenerator:
    """
    병렬 이미지 생성기

    ThreadPoolExecutor를 사용하여 여러 이미지를 동시에 생성
    """

    def __init__(
        self,
        max_workers: int = 4,
        cookie: Optional[str] = None,
        api_delay: float = 0.5,  # API 요청 간 딜레이 (rate limit 방지)
        verbose: bool = True
    ):
        """
        Args:
            max_workers: 동시 처리할 최대 워커 수
            cookie: ImageFX 쿠키
            api_delay: API 요청 간 딜레이 (초)
            verbose: 상세 로그 출력 여부
        """
        self.max_workers = max_workers
        self.api_delay = api_delay
        self.verbose = verbose

        # 워커 풀 초기화
        self.worker_pool = ImageFXWorkerPool.get_instance(max_workers)

        # 쿠키 설정
        if cookie:
            self.worker_pool.initialize(cookie)
        else:
            # 캐시에서 쿠키 로드
            self._load_cookie_from_cache()

        # ThreadPoolExecutor
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # 요청 타이밍 제어
        self._last_request_time = 0
        self._request_lock = threading.Lock()

        print(f"[ParallelGen] ✅ 병렬 생성기 초기화됨 (워커 {max_workers}개)")

    def _load_cookie_from_cache(self):
        """캐시에서 쿠키 로드"""
        try:
            from utils.imagefx_client import ImageFXCache
            cookie = ImageFXCache.get_cookie()
            if cookie:
                self.worker_pool.initialize(cookie)
        except Exception as e:
            print(f"[ParallelGen] ⚠️ 쿠키 로드 실패: {e}")

    def _throttle_request(self):
        """API 요청 제한 (rate limit 방지)"""
        with self._request_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.api_delay:
                time.sleep(self.api_delay - elapsed)
            self._last_request_time = time.time()

    def _generate_single(self, task: GenerationTask) -> GenerationResult:
        """단일 태스크 처리 (스레드에서 실행)"""
        # Rate limit 방지
        self._throttle_request()

        if self.verbose:
            print(f"[ParallelGen] 🚀 씬 {task.scene_id} 생성 시작...")

        result = self.worker_pool.generate_image(task)

        if self.verbose:
            if result.success:
                print(f"[ParallelGen] ✅ 씬 {task.scene_id} 완료 ({result.elapsed_time:.1f}초)")
            else:
                print(f"[ParallelGen] ❌ 씬 {task.scene_id} 실패: {result.error}")

        return result

    def generate_batch(
        self,
        tasks: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[GenerationResult]:
        """
        배치 이미지 생성

        Args:
            tasks: 태스크 목록 [{"scene_id": 1, "prompt": "...", ...}, ...]
            progress_callback: 진행률 콜백 (completed, total)

        Returns:
            결과 목록
        """
        total = len(tasks)

        if total == 0:
            return []

        print(f"\n[ParallelGen] ========== 배치 생성 시작 ==========")
        print(f"[ParallelGen] 총 {total}개 이미지, 워커 {self.max_workers}개")

        start_time = time.time()

        # 태스크 객체 변환
        generation_tasks = []
        for task_data in tasks:
            task = GenerationTask(
                task_id=task_data.get("task_id", str(uuid.uuid4())),
                scene_id=task_data.get("scene_id", 0),
                prompt=task_data.get("prompt", ""),
                output_path=task_data.get("output_path", ""),
                model=task_data.get("model", "IMAGEN_4"),
                aspect_ratio=task_data.get("aspect_ratio", "LANDSCAPE"),
                seed=task_data.get("seed"),
                negative_prompt=task_data.get("negative_prompt", ""),
                timeout=task_data.get("timeout", 180)
            )
            generation_tasks.append(task)

        # Future 제출
        futures = {}
        for task in generation_tasks:
            future = self.executor.submit(self._generate_single, task)
            futures[future] = task

        # 결과 수집
        results = []
        completed = 0

        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result(timeout=task.timeout + 30)
                results.append(result)
            except Exception as e:
                results.append(GenerationResult(
                    task_id=task.task_id,
                    scene_id=task.scene_id,
                    success=False,
                    error=str(e)
                ))

            completed += 1

            if progress_callback:
                progress_callback(completed, total)

        # 결과 정렬 (scene_id 순)
        results.sort(key=lambda r: r.scene_id)

        # 요약
        elapsed = time.time() - start_time
        success_count = sum(1 for r in results if r.success)

        print(f"[ParallelGen] ========== 배치 완료 ==========")
        print(f"[ParallelGen] 성공: {success_count}/{total}")
        print(f"[ParallelGen] 총 소요 시간: {elapsed:.1f}초")
        print(f"[ParallelGen] 이미지당 평균: {elapsed/total:.1f}초")

        return results

    def shutdown(self):
        """생성기 종료"""
        self.executor.shutdown(wait=True)
        print("[ParallelGen] 생성기 종료됨")


# ═══════════════════════════════════════════════════════════════════════════════
# 편의 함수
# ═══════════════════════════════════════════════════════════════════════════════

_generator_instance: Optional[ParallelImageGenerator] = None
_generator_lock = threading.Lock()


def get_parallel_generator(
    max_workers: int = 4,
    cookie: Optional[str] = None
) -> ParallelImageGenerator:
    """
    싱글톤 병렬 생성기 반환

    Args:
        max_workers: 동시 처리 워커 수
        cookie: ImageFX 쿠키 (None이면 캐시에서 로드)

    Returns:
        ParallelImageGenerator 인스턴스
    """
    global _generator_instance

    if _generator_instance is None:
        with _generator_lock:
            if _generator_instance is None:
                _generator_instance = ParallelImageGenerator(
                    max_workers=max_workers,
                    cookie=cookie
                )

    return _generator_instance


def generate_backgrounds_parallel(
    scenes: List[Dict],
    style_config: Dict,
    api_config: Dict,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    max_workers: int = 4
) -> List[GenerationResult]:
    """
    배경 이미지 병렬 생성 (편의 함수)

    Args:
        scenes: 씬 목록
        style_config: 스타일 설정 {"prefix": "...", "suffix": "...", "negative": "..."}
        api_config: API 설정 {"model": "...", "seed": ..., "aspect_ratio": "..."}
        progress_callback: 진행률 콜백
        max_workers: 워커 수

    Returns:
        생성 결과 목록
    """
    generator = get_parallel_generator(max_workers)

    # 태스크 생성
    tasks = []
    project_root = str(Path(__file__).parent.parent)

    for scene in scenes:
        scene_id = scene.get("scene_id", scene.get("scene_num", 0))

        # 프롬프트 가져오기
        prompt = (
            scene.get("image_prompt_en", "") or
            scene.get("image_prompt_ko", "") or
            scene.get("background_prompt", "") or
            scene.get("description", "")
        )

        if not prompt:
            continue

        # 스타일 적용
        prefix = style_config.get("prefix", "")
        suffix = style_config.get("suffix", "")
        negative = style_config.get("negative", "")

        full_prompt = ", ".join(filter(None, [prefix, prompt, suffix]))

        # 출력 경로
        output_dir = Path(project_root) / "data" / "images" / "backgrounds"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)
        output_path = str(output_dir / f"bg_scene_{scene_id:03d}_{timestamp}.png")

        tasks.append({
            "scene_id": scene_id,
            "prompt": full_prompt,
            "output_path": output_path,
            "model": api_config.get("model", "IMAGEN_4"),
            "aspect_ratio": api_config.get("aspect_ratio", "LANDSCAPE"),
            "seed": api_config.get("seed"),
            "negative_prompt": negative
        })

    if not tasks:
        return []

    return generator.generate_batch(tasks, progress_callback)


# 테스트
if __name__ == "__main__":
    print("병렬 이미지 생성기 테스트")
    print("=" * 50)

    # 테스트 태스크
    test_tasks = [
        {
            "scene_id": 1,
            "prompt": "A beautiful sunset over mountains",
            "output_path": "./test_output/test_1.png",
            "model": "IMAGEN_4",
            "aspect_ratio": "LANDSCAPE"
        },
        {
            "scene_id": 2,
            "prompt": "A serene lake with reflections",
            "output_path": "./test_output/test_2.png",
            "model": "IMAGEN_4",
            "aspect_ratio": "LANDSCAPE"
        }
    ]

    def test_progress(completed, total):
        print(f"진행률: {completed}/{total}")

    try:
        generator = ParallelImageGenerator(max_workers=2)
        results = generator.generate_batch(test_tasks, progress_callback=test_progress)

        for result in results:
            print(f"씬 {result.scene_id}: {'성공' if result.success else '실패'}")
            if result.success:
                print(f"  경로: {result.path}")
            else:
                print(f"  에러: {result.error}")

    except Exception as e:
        print(f"테스트 실패: {e}")
