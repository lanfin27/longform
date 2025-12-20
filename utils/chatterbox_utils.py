# -*- coding: utf-8 -*-
"""
Chatterbox TTS 유틸리티 - 안정성 우선 버전

순차 처리 + 긴 타임아웃 + 재시도 로직으로 타임아웃 문제 해결
"""

import os
import time
import requests
import tempfile
from typing import List, Dict, Optional, Callable
from pydub import AudioSegment

CHATTERBOX_URL = "http://localhost:8100"


def call_api_with_retry(
    text: str,
    params: Dict,
    timeout: int = 180,
    max_retries: int = 2
) -> Dict:
    """
    재시도 로직 포함 API 호출

    Args:
        text: 생성할 텍스트
        params: TTS 파라미터
        timeout: 요청 타임아웃 (초)
        max_retries: 최대 재시도 횟수

    Returns:
        {"success": bool, "audio_data": bytes, "duration": float, ...}
    """

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

    for attempt in range(max_retries + 1):
        try:
            print(f"  [API] 시도 {attempt + 1}/{max_retries + 1}, 타임아웃: {timeout}초")

            response = requests.post(
                f"{CHATTERBOX_URL}/generate",
                json=request_data,
                timeout=timeout
            )

            if response.status_code == 200:
                result = response.json()

                if result.get("success"):
                    # 오디오 파일 다운로드
                    audio_url = result.get("audio_url", "")
                    audio_data = None

                    if audio_url:
                        full_url = f"{CHATTERBOX_URL}{audio_url}"
                        try:
                            audio_resp = requests.get(full_url, timeout=30)
                            if audio_resp.status_code == 200:
                                audio_data = audio_resp.content
                        except:
                            pass

                    return {
                        "success": True,
                        "audio_data": audio_data,
                        "duration": result.get("duration_seconds", 0),
                        "audio_url": audio_url
                    }
                else:
                    error_msg = result.get("error", "생성 실패")
                    print(f"  [API] 서버 오류: {error_msg}")

                    # 재시도 가능한 오류인지 확인
                    if attempt < max_retries:
                        print(f"  [API] 재시도 중...")
                        time.sleep(2)
                        continue

                    return {"success": False, "error": error_msg}
            else:
                print(f"  [API] HTTP 오류: {response.status_code}")

        except requests.exceptions.Timeout:
            print(f"  [API] ⚠️ 타임아웃 ({timeout}초)")
            if attempt < max_retries:
                print(f"  [API] 재시도 중...")
                time.sleep(2)
                continue

        except requests.exceptions.ConnectionError:
            print(f"  [API] ⚠️ 연결 오류 - 서버 확인 필요")
            return {"success": False, "error": "서버 연결 실패"}

        except Exception as e:
            print(f"  [API] ⚠️ 오류: {e}")
            if attempt < max_retries:
                time.sleep(2)
                continue

    return {"success": False, "error": "모든 재시도 실패"}


def generate_scenes_sequential_safe(
    scenes: List[Dict],
    params: Dict,
    timeout_per_scene: int = 180,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    안전한 순차 처리 (타임아웃 방지)

    - 병렬 처리 대신 순차 처리로 GPU 경쟁 방지
    - 긴 타임아웃으로 안정성 확보
    - 실패 시 자동 재시도

    Args:
        scenes: 씬 리스트 [{"scene_id": 1, "text": "..."}, ...]
        params: TTS 파라미터
        timeout_per_scene: 씬당 타임아웃 (초)
        progress_callback: 진행 콜백 (current, total, message)

    Returns:
        생성 결과 리스트
    """

    print("=" * 60)
    print(f"[Sequential] {len(scenes)}개 씬 순차 생성 시작")
    print(f"[Sequential] 타임아웃: {timeout_per_scene}초/씬")
    print("=" * 60)

    results = []
    total = len(scenes)
    total_start = time.time()

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", idx + 1)
        text = scene.get("text", "")

        if not text.strip():
            results.append({
                "scene_id": scene_id,
                "success": False,
                "error": "빈 텍스트"
            })
            continue

        if progress_callback:
            progress_callback(idx, total, f"씬 {scene_id} 생성 중... ({idx + 1}/{total})")

        print(f"\n[Scene {scene_id}] 텍스트: '{text[:40]}...' ({len(text)}자)")

        start_time = time.time()

        # API 요청 (긴 타임아웃 + 재시도)
        result = call_api_with_retry(
            text=text,
            params=params,
            timeout=timeout_per_scene,
            max_retries=2
        )

        elapsed = time.time() - start_time

        if result.get("success"):
            results.append({
                "scene_id": scene_id,
                "text": text,
                "text_preview": text[:50] + "..." if len(text) > 50 else text,
                "char_count": len(text),
                "audio_data": result.get("audio_data"),
                "duration": result.get("duration", 0),
                "generation_time": elapsed,
                "status": "success",
                "success": True
            })
            print(f"[Scene {scene_id}] ✅ 성공: {elapsed:.1f}초, {result.get('duration', 0):.1f}초 오디오")
        else:
            results.append({
                "scene_id": scene_id,
                "text": text,
                "audio_data": None,
                "status": "failed",
                "success": False,
                "error": result.get("error", "생성 실패")
            })
            print(f"[Scene {scene_id}] ❌ 실패: {result.get('error')}")

    total_time = time.time() - total_start
    success_count = sum(1 for r in results if r.get("success"))

    print(f"\n[Sequential] 완료: {success_count}/{total}개 성공, 총 {total_time:.1f}초")

    if progress_callback:
        progress_callback(total, total, f"생성 완료 ({success_count}/{total})")

    return results


# ============================================================
# 청크 분할 생성 (긴 텍스트용)
# ============================================================

def generate_with_chunking(
    text: str,
    params: Dict,
    max_chunk_chars: int = 70,
    chunk_timeout: int = 60,
    pause_ms: int = 100
) -> Dict:
    """
    청크 분할 + 생성 + 병합

    긴 텍스트를 작은 청크로 나눠 생성 후 병합

    Args:
        text: 원본 텍스트
        params: TTS 파라미터
        max_chunk_chars: 청크당 최대 글자 수
        chunk_timeout: 청크당 타임아웃
        pause_ms: 청크 간 무음 길이

    Returns:
        {"success": bool, "audio_data": bytes, "duration": float, "chunks": int}
    """
    from utils.tts_utils import split_text_for_tts

    # 텍스트가 짧으면 분할 불필요
    if len(text) <= max_chunk_chars:
        return call_api_with_retry(text, params, timeout=chunk_timeout * 2)

    # 1. 텍스트 분할
    chunks_info = split_text_for_tts(text, max_chars=max_chunk_chars)
    chunks = [c["text"] for c in chunks_info]

    print(f"[Chunked] {len(text)}자 → {len(chunks)}개 청크로 분할")
    for i, chunk in enumerate(chunks):
        print(f"  청크 {i+1}: '{chunk[:25]}...' ({len(chunk)}자)")

    # 2. 각 청크 생성
    audio_segments = []
    chunk_durations = []

    for idx, chunk in enumerate(chunks):
        print(f"[Chunked] 청크 {idx + 1}/{len(chunks)} 생성 중...")

        result = call_api_with_retry(
            text=chunk,
            params=params,
            timeout=chunk_timeout,
            max_retries=2
        )

        if result.get("success") and result.get("audio_data"):
            try:
                import io
                audio = AudioSegment.from_file(io.BytesIO(result["audio_data"]), format="wav")
                audio_segments.append(audio)
                chunk_durations.append(result.get("duration", len(audio) / 1000))
                print(f"  청크 {idx + 1} ✅ 완료")
            except Exception as e:
                print(f"  청크 {idx + 1} ⚠️ 오디오 로드 실패: {e}")
        else:
            print(f"  청크 {idx + 1} ❌ 실패")

    # 3. 오디오 병합
    if not audio_segments:
        return {"success": False, "error": "모든 청크 생성 실패"}

    if len(audio_segments) == 1:
        import io
        output = io.BytesIO()
        audio_segments[0].export(output, format="wav")
        output.seek(0)
        return {
            "success": True,
            "audio_data": output.read(),
            "duration": chunk_durations[0] if chunk_durations else 0,
            "chunks": 1
        }

    # 병합
    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=pause_ms)

    for idx, audio in enumerate(audio_segments):
        if idx > 0:
            combined += pause
        combined += audio

    # 바이트로 변환
    import io
    output = io.BytesIO()
    combined.export(output, format="wav")
    output.seek(0)

    total_duration = sum(chunk_durations) + (len(audio_segments) - 1) * (pause_ms / 1000)

    print(f"[Chunked] 병합 완료: {len(audio_segments)}개 청크 → {total_duration:.2f}초")

    return {
        "success": True,
        "audio_data": output.read(),
        "duration": total_duration,
        "chunks": len(chunks)
    }


def generate_scenes_with_chunking(
    scenes: List[Dict],
    params: Dict,
    max_chunk_chars: int = 70,
    timeout_per_scene: int = 180,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    청크 분할 + 순차 처리 통합

    Args:
        scenes: 씬 리스트
        params: TTS 파라미터
        max_chunk_chars: 청크당 최대 글자 수
        timeout_per_scene: 씬당 타임아웃
        progress_callback: 진행 콜백

    Returns:
        생성 결과 리스트
    """

    print("=" * 60)
    print(f"[ChunkedSeq] {len(scenes)}개 씬 청크 분할 생성 시작")
    print(f"[ChunkedSeq] 청크 크기: {max_chunk_chars}자, 타임아웃: {timeout_per_scene}초")
    print("=" * 60)

    results = []
    total = len(scenes)
    total_start = time.time()

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", idx + 1)
        text = scene.get("text", "")

        if not text.strip():
            results.append({
                "scene_id": scene_id,
                "success": False,
                "error": "빈 텍스트"
            })
            continue

        if progress_callback:
            progress_callback(idx, total, f"씬 {scene_id} 생성 중... ({idx + 1}/{total})")

        print(f"\n[Scene {scene_id}] 텍스트: '{text[:40]}...' ({len(text)}자)")

        start_time = time.time()

        # 청크 분할 생성 또는 직접 생성
        if len(text) > max_chunk_chars:
            result = generate_with_chunking(
                text=text,
                params=params,
                max_chunk_chars=max_chunk_chars,
                chunk_timeout=60,
                pause_ms=100
            )
        else:
            result = call_api_with_retry(
                text=text,
                params=params,
                timeout=timeout_per_scene,
                max_retries=2
            )

        elapsed = time.time() - start_time

        if result.get("success"):
            results.append({
                "scene_id": scene_id,
                "text": text,
                "text_preview": text[:50] + "..." if len(text) > 50 else text,
                "char_count": len(text),
                "audio_data": result.get("audio_data"),
                "duration": result.get("duration", 0),
                "generation_time": elapsed,
                "chunks_count": result.get("chunks", 1),
                "status": "success",
                "success": True
            })
            print(f"[Scene {scene_id}] ✅ 성공: {elapsed:.1f}초")
        else:
            results.append({
                "scene_id": scene_id,
                "text": text,
                "audio_data": None,
                "status": "failed",
                "success": False,
                "error": result.get("error", "생성 실패")
            })
            print(f"[Scene {scene_id}] ❌ 실패: {result.get('error')}")

    total_time = time.time() - total_start
    success_count = sum(1 for r in results if r.get("success"))

    print(f"\n[ChunkedSeq] 완료: {success_count}/{total}개 성공, 총 {total_time:.1f}초")

    if progress_callback:
        progress_callback(total, total, f"생성 완료 ({success_count}/{total})")

    return results
