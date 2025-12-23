# -*- coding: utf-8 -*-
"""
Chatterbox TTS 비동기 병렬 생성 모듈

여러 씬을 동시에 생성하여 속도를 크게 향상시킵니다.
GPU 메모리 제한을 고려하여 동시 요청 수를 제한합니다.
"""

import asyncio
import aiohttp
import time
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests


CHATTERBOX_URL = "http://localhost:8100"


async def generate_single_scene_async(
    session: aiohttp.ClientSession,
    scene: Dict,
    params: Dict,
    semaphore: asyncio.Semaphore
) -> Dict:
    """
    단일 씬 비동기 생성

    Args:
        session: aiohttp 세션
        scene: 씬 정보 (scene_id, text)
        params: TTS 파라미터
        semaphore: 동시 요청 제한용 세마포어

    Returns:
        생성 결과 dict
    """
    async with semaphore:
        scene_id = scene.get("scene_id", 0)
        text = scene.get("text", "")

        if not text.strip():
            return {
                "scene_id": scene_id,
                "success": False,
                "error": "빈 텍스트"
            }

        request_data = {
            "text": text,
            "settings": {
                "language": params.get("language", "ko"),
                "voice_ref_path": params.get("voice_ref_path"),
                "exaggeration": params.get("exaggeration", 0.5),
                "cfg_weight": params.get("cfg_weight", 0.5),
                "temperature": params.get("temperature", 0.8),
                "speed": params.get("speed", 1.0),
                "repetition_penalty": params.get("repetition_penalty", 1.4),  # 1.3→1.4 토큰 반복 감소
                "seed": params.get("seed"),
            }
        }

        start_time = time.time()

        try:
            async with session.post(
                f"{CHATTERBOX_URL}/generate",
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status == 200:
                    result = await response.json()

                    if result.get("success"):
                        # 오디오 파일 다운로드
                        audio_url = result.get("audio_url", "")
                        if audio_url:
                            full_url = f"{CHATTERBOX_URL}{audio_url}"
                            async with session.get(full_url) as audio_resp:
                                if audio_resp.status == 200:
                                    audio_data = await audio_resp.read()
                                else:
                                    audio_data = None
                        else:
                            audio_data = None

                        elapsed = time.time() - start_time
                        duration = result.get("duration_seconds", 0)
                        chars_per_sec = len(text) / duration if duration > 0 else 0

                        print(f"[Async] 씬 {scene_id} 완료: {elapsed:.1f}초 생성, {duration:.1f}초 오디오, {chars_per_sec:.1f} 글자/초")

                        return {
                            "scene_id": scene_id,
                            "text": text,
                            "audio_data": audio_data,
                            "duration": duration,
                            "generation_time": elapsed,
                            "chars_per_second": chars_per_sec,
                            "success": True
                        }
                    else:
                        return {
                            "scene_id": scene_id,
                            "success": False,
                            "error": result.get("error", "알 수 없는 오류")
                        }
                else:
                    return {
                        "scene_id": scene_id,
                        "success": False,
                        "error": f"HTTP {response.status}"
                    }

        except asyncio.TimeoutError:
            print(f"[Async] 씬 {scene_id} 타임아웃")
            return {
                "scene_id": scene_id,
                "success": False,
                "error": "타임아웃 (120초)"
            }
        except Exception as e:
            print(f"[Async] 씬 {scene_id} 실패: {e}")
            return {
                "scene_id": scene_id,
                "success": False,
                "error": str(e)
            }


async def generate_all_scenes_parallel(
    scenes: List[Dict],
    params: Dict,
    max_concurrent: int = 2,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    모든 씬 병렬 생성

    Args:
        scenes: 씬 리스트 [{"scene_id": 1, "text": "..."}, ...]
        params: TTS 파라미터
        max_concurrent: 최대 동시 요청 수 (GPU 메모리 고려, 기본 2)
        progress_callback: 진행 콜백 (current, total, message)

    Returns:
        생성 결과 리스트
    """
    if not scenes:
        return []

    print(f"[Parallel] {len(scenes)}개 씬 병렬 생성 시작 (동시 {max_concurrent}개)")
    start_time = time.time()

    semaphore = asyncio.Semaphore(max_concurrent)
    completed_count = 0

    async def track_progress(task):
        nonlocal completed_count
        result = await task
        completed_count += 1
        if progress_callback:
            progress_callback(completed_count, len(scenes), f"씬 {result.get('scene_id')} 완료")
        return result

    connector = aiohttp.TCPConnector(limit=max_concurrent)
    timeout = aiohttp.ClientTimeout(total=180)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [
            track_progress(
                generate_single_scene_async(session, scene, params, semaphore)
            )
            for scene in scenes
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 예외 처리
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "scene_id": scenes[i].get("scene_id", i),
                "success": False,
                "error": str(result)
            })
        else:
            processed_results.append(result)

    # 씬 ID 순서로 정렬
    processed_results = sorted(processed_results, key=lambda x: x.get("scene_id", 0))

    elapsed = time.time() - start_time
    success_count = sum(1 for r in processed_results if r.get("success"))

    # 순차 대비 예상 시간 (씬당 평균 5초 가정)
    sequential_estimate = len(scenes) * 5

    print(f"[Parallel] 완료: {success_count}/{len(scenes)}개 성공")
    print(f"[Parallel] 총 소요: {elapsed:.1f}초 (순차 예상: ~{sequential_estimate}초)")
    print(f"[Parallel] 속도 향상: {sequential_estimate / elapsed:.1f}배")

    return processed_results


def run_parallel_generation(
    scenes: List[Dict],
    params: Dict,
    max_concurrent: int = 2,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    동기 래퍼 함수 (Streamlit에서 호출용)

    새 이벤트 루프를 생성하여 비동기 함수 실행
    """
    try:
        # 기존 이벤트 루프가 있으면 사용
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Streamlit에서 실행 중인 경우 ThreadPoolExecutor 사용
            return run_threaded_generation(scenes, params, max_concurrent, progress_callback)
    except RuntimeError:
        pass

    # 새 이벤트 루프 생성
    return asyncio.run(
        generate_all_scenes_parallel(scenes, params, max_concurrent, progress_callback)
    )


# ============================================================
# ThreadPoolExecutor 기반 병렬 처리 (대안)
# ============================================================

def generate_single_scene_sync(scene: Dict, params: Dict) -> Dict:
    """
    단일 씬 동기 생성 (스레드용)
    """
    scene_id = scene.get("scene_id", 0)
    text = scene.get("text", "")

    if not text.strip():
        return {"scene_id": scene_id, "success": False, "error": "빈 텍스트"}

    request_data = {
        "text": text,
        "settings": {
            "language": params.get("language", "ko"),
            "voice_ref_path": params.get("voice_ref_path"),
            "exaggeration": params.get("exaggeration", 0.5),
            "cfg_weight": params.get("cfg_weight", 0.5),
            "temperature": params.get("temperature", 0.8),
            "speed": params.get("speed", 1.0),
            "repetition_penalty": params.get("repetition_penalty", 1.3),
            "seed": params.get("seed"),
        }
    }

    start_time = time.time()

    try:
        response = requests.post(
            f"{CHATTERBOX_URL}/generate",
            json=request_data,
            timeout=120
        )

        if response.status_code == 200:
            result = response.json()

            if result.get("success"):
                # 오디오 다운로드
                audio_url = result.get("audio_url", "")
                if audio_url:
                    full_url = f"{CHATTERBOX_URL}{audio_url}"
                    audio_resp = requests.get(full_url, timeout=30)
                    audio_data = audio_resp.content if audio_resp.status_code == 200 else None
                else:
                    audio_data = None

                elapsed = time.time() - start_time
                duration = result.get("duration_seconds", 0)

                print(f"[Thread] 씬 {scene_id} 완료: {elapsed:.1f}초")

                return {
                    "scene_id": scene_id,
                    "text": text,
                    "audio_data": audio_data,
                    "duration": duration,
                    "generation_time": elapsed,
                    "success": True
                }
            else:
                return {"scene_id": scene_id, "success": False, "error": result.get("error")}
        else:
            return {"scene_id": scene_id, "success": False, "error": f"HTTP {response.status_code}"}

    except requests.exceptions.Timeout:
        return {"scene_id": scene_id, "success": False, "error": "타임아웃"}
    except Exception as e:
        return {"scene_id": scene_id, "success": False, "error": str(e)}


def run_threaded_generation(
    scenes: List[Dict],
    params: Dict,
    max_workers: int = 2,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    ThreadPoolExecutor로 병렬 생성

    GPU가 1개이므로 실제 TTS 생성은 순차지만,
    네트워크 I/O가 병렬화되어 약간의 속도 향상
    """
    if not scenes:
        return []

    print(f"[Threaded] {len(scenes)}개 씬 병렬 생성 (workers: {max_workers})")
    start_time = time.time()

    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_scene = {
            executor.submit(generate_single_scene_sync, scene, params): scene
            for scene in scenes
        }

        for future in as_completed(future_to_scene):
            result = future.result()
            results.append(result)
            completed += 1

            if progress_callback:
                progress_callback(completed, len(scenes), f"씬 {result.get('scene_id')} 완료")

    # 씬 ID 순서로 정렬
    results = sorted(results, key=lambda x: x.get("scene_id", 0))

    elapsed = time.time() - start_time
    success_count = sum(1 for r in results if r.get("success"))

    print(f"[Threaded] 완료: {success_count}/{len(scenes)}개, 총 {elapsed:.1f}초")

    return results


# ============================================================
# 서버 배치 엔드포인트 활용 (단일 요청으로 여러 씬 처리)
# ============================================================

def generate_batch_via_server(
    scenes: List[Dict],
    params: Dict,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    서버의 /generate/batch 엔드포인트를 활용한 배치 생성

    단일 HTTP 요청으로 여러 씬을 처리합니다.
    네트워크 오버헤드가 줄어들지만, 진행 상황 확인이 어렵습니다.

    Args:
        scenes: 씬 리스트 [{"scene_id": 1, "text": "..."}, ...]
        params: TTS 파라미터
        progress_callback: 진행 콜백 (배치 완료 후 한 번만 호출됨)

    Returns:
        생성 결과 리스트
    """
    if not scenes:
        return []

    print(f"[Batch] {len(scenes)}개 씬 배치 생성 시작")
    start_time = time.time()

    # 배치 요청 데이터 구성
    batch_items = []
    for scene in scenes:
        batch_items.append({
            "text": scene.get("text", ""),
            "voice_id": params.get("voice_ref_path", "default"),
            "exaggeration": params.get("exaggeration", 0.5),
            "language": params.get("language", "ko")
        })

    request_data = {
        "items": batch_items,
        "settings": {
            "language": params.get("language", "ko"),
            "cfg_weight": params.get("cfg_weight", 0.5),
            "temperature": params.get("temperature", 0.8),
            "speed": params.get("speed", 1.0),
            "repetition_penalty": params.get("repetition_penalty", 1.3),
            "seed": params.get("seed"),
        }
    }

    try:
        # 배치 생성 요청 (씬당 30초 타임아웃)
        timeout = max(120, len(scenes) * 30)
        response = requests.post(
            f"{CHATTERBOX_URL}/generate/batch",
            json=request_data,
            timeout=timeout
        )

        if response.status_code != 200:
            print(f"[Batch] HTTP 오류: {response.status_code}")
            return [{
                "scene_id": s.get("scene_id", i),
                "success": False,
                "error": f"HTTP {response.status_code}"
            } for i, s in enumerate(scenes)]

        batch_result = response.json()
        results_data = batch_result.get("results", [])

        # 결과 변환
        results = []
        for i, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", i)
            result_item = results_data[i] if i < len(results_data) else {}

            if result_item.get("success"):
                # 오디오 다운로드
                audio_url = result_item.get("audio_url", "")
                audio_data = None

                if audio_url:
                    try:
                        full_url = f"{CHATTERBOX_URL}{audio_url}"
                        audio_resp = requests.get(full_url, timeout=30)
                        if audio_resp.status_code == 200:
                            audio_data = audio_resp.content
                    except:
                        pass

                results.append({
                    "scene_id": scene_id,
                    "text": scene.get("text", ""),
                    "audio_data": audio_data,
                    "duration": result_item.get("duration", 0),
                    "success": True
                })
            else:
                results.append({
                    "scene_id": scene_id,
                    "success": False,
                    "error": result_item.get("error", "배치 생성 실패")
                })

        elapsed = time.time() - start_time
        success_count = sum(1 for r in results if r.get("success"))

        print(f"[Batch] 완료: {success_count}/{len(scenes)}개 성공, 총 {elapsed:.1f}초")

        if progress_callback:
            progress_callback(len(scenes), len(scenes), f"배치 생성 완료 ({success_count}개 성공)")

        return results

    except requests.exceptions.Timeout:
        print(f"[Batch] 타임아웃")
        return [{
            "scene_id": s.get("scene_id", i),
            "success": False,
            "error": "배치 요청 타임아웃"
        } for i, s in enumerate(scenes)]

    except Exception as e:
        print(f"[Batch] 실패: {e}")
        return [{
            "scene_id": s.get("scene_id", i),
            "success": False,
            "error": str(e)
        } for i, s in enumerate(scenes)]


def generate_scenes_optimal(
    scenes: List[Dict],
    params: Dict,
    max_concurrent: int = 2,
    use_batch_endpoint: bool = False,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    최적의 방법으로 씬 생성 (자동 선택)

    - 씬 수가 적으면 (<=3): 스레드 병렬 처리
    - 씬 수가 많으면 (>3): 배치 엔드포인트 또는 스레드 병렬

    Args:
        scenes: 씬 리스트
        params: TTS 파라미터
        max_concurrent: 최대 동시 요청 수
        use_batch_endpoint: 배치 엔드포인트 강제 사용 여부
        progress_callback: 진행 콜백

    Returns:
        생성 결과 리스트
    """
    if not scenes:
        return []

    # 배치 엔드포인트 사용 (진행 상황 확인 불필요한 경우)
    if use_batch_endpoint:
        return generate_batch_via_server(scenes, params, progress_callback)

    # 기본: 스레드 병렬 처리 (진행 상황 실시간 확인 가능)
    return run_threaded_generation(scenes, params, max_concurrent, progress_callback)
