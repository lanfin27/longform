# -*- coding: utf-8 -*-
"""
TTS 직접 생성기 - 청크 분할 없음

청크 분할로 인한 오버헤드 제거:
- 128자 씬 → 3개 청크 → 3번 API 호출 → 38초 (기존)
- 128자 씬 → 1번 API 호출 → ~12초 (최적화)

200자 이하는 분할하지 않고 직접 생성
"""

import os
import time
import requests
from typing import Dict, List, Optional, Callable

# 세션 재사용으로 연결 오버헤드 감소
_session = requests.Session()
_session.headers.update({
    "Content-Type": "application/json",
    "Connection": "keep-alive"
})

CHATTERBOX_URL = "http://localhost:8100"


def generate_scene_direct(
    text: str,
    params: Dict,
    timeout: int = 180
) -> Dict:
    """
    청크 분할 없이 직접 생성

    Args:
        text: 생성할 텍스트 (200자 이하 권장)
        params: TTS 파라미터
        timeout: 요청 타임아웃 (초)

    Returns:
        {success, audio_data, duration, generation_time, ...}
    """

    if not text.strip():
        return {"success": False, "error": "빈 텍스트"}

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
        response = _session.post(
            f"{CHATTERBOX_URL}/generate",
            json=request_data,
            timeout=timeout
        )

        if response.status_code == 200:
            result = response.json()

            if result.get("success"):
                # 오디오 다운로드
                audio_url = result.get("audio_url", "")
                audio_data = None

                if audio_url:
                    try:
                        audio_resp = _session.get(
                            f"{CHATTERBOX_URL}{audio_url}",
                            timeout=30
                        )
                        if audio_resp.status_code == 200:
                            audio_data = audio_resp.content
                    except Exception as e:
                        print(f"  ⚠️ 오디오 다운로드 실패: {e}")

                elapsed = time.time() - start_time

                return {
                    "success": True,
                    "audio_data": audio_data,
                    "duration": result.get("duration_seconds", 0),
                    "generation_time": elapsed,
                    "audio_url": audio_url
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "생성 실패")
                }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}"
            }

    except requests.exceptions.Timeout:
        return {"success": False, "error": f"타임아웃 ({timeout}초)"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "서버 연결 실패"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_all_scenes_direct(
    scenes: List[Dict],
    params: Dict,
    timeout_per_scene: int = 180,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    모든 씬 직접 생성 (청크 분할 없음!)

    Args:
        scenes: 씬 리스트 [{scene_id, text, ...}, ...]
        params: TTS 파라미터
        timeout_per_scene: 씬당 타임아웃
        progress_callback: (current, total, message) 콜백

    Returns:
        생성 결과 리스트
    """

    print("\n" + "=" * 60)
    print(f"[DirectGen] 🚀 {len(scenes)}개 씬 직접 생성 시작")
    print(f"[DirectGen] ⚡ 청크 분할 비활성화 - 최대 속도!")
    print("=" * 60)

    results = []
    total = len(scenes)
    total_start = time.time()

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", idx + 1)
        text = scene.get("text", "")

        if progress_callback:
            progress_callback(idx, total, f"씬 {scene_id} 생성 중...")

        char_count = len(text.replace(" ", "").replace("\n", ""))
        print(f"\n[Scene {scene_id}] {char_count}자 직접 생성...")

        if not text.strip():
            results.append({
                "scene_id": scene_id,
                "text": text,
                "success": False,
                "error": "빈 텍스트",
                "status": "failed"
            })
            continue

        # 직접 생성 (청크 분할 없음!)
        result = generate_scene_direct(text, params, timeout_per_scene)

        if result.get("success"):
            results.append({
                "scene_id": scene_id,
                "text": text,
                "text_preview": text[:50] + "..." if len(text) > 50 else text,
                "char_count": char_count,
                "audio_data": result.get("audio_data"),
                "duration": result.get("duration", 0),
                "generation_time": result.get("generation_time", 0),
                "chunks_count": 1,  # 청크 분할 없음
                "status": "success",
                "success": True
            })
            print(f"[Scene {scene_id}] ✅ {result.get('generation_time', 0):.1f}초, {result.get('duration', 0):.1f}초 오디오")
        else:
            results.append({
                "scene_id": scene_id,
                "text": text,
                "text_preview": text[:50] + "..." if len(text) > 50 else text,
                "char_count": char_count,
                "audio_data": None,
                "status": "failed",
                "success": False,
                "error": result.get("error", "생성 실패")
            })
            print(f"[Scene {scene_id}] ❌ {result.get('error')}")

    total_time = time.time() - total_start
    success_count = sum(1 for r in results if r.get("success"))

    print(f"\n[DirectGen] 완료: {success_count}/{total}개 성공")
    print(f"[DirectGen] 총 시간: {total_time:.1f}초 (씬당 평균: {total_time/total:.1f}초)")
    print("=" * 60 + "\n")

    if progress_callback:
        progress_callback(total, total, f"생성 완료 ({success_count}/{total})")

    return results


def generate_with_smart_chunking(
    text: str,
    params: Dict,
    max_chars: int = 200,
    timeout: int = 180
) -> Dict:
    """
    스마트 청크 분할 (200자 초과시에만)

    - 200자 이하: 직접 생성
    - 200자 초과: 문장 경계에서 분할

    Args:
        text: 생성할 텍스트
        params: TTS 파라미터
        max_chars: 분할 기준 (기본 200자)
        timeout: 타임아웃

    Returns:
        생성 결과
    """

    char_count = len(text.replace(" ", "").replace("\n", ""))

    # 200자 이하는 직접 생성
    if char_count <= max_chars:
        return generate_scene_direct(text, params, timeout)

    # 200자 초과: 문장 경계에서 분할
    print(f"[SmartChunk] {char_count}자 → 문장 경계 분할")

    sentences = _split_by_sentences(text)

    if len(sentences) <= 1:
        # 분할 불가 → 직접 생성 시도
        return generate_scene_direct(text, params, timeout)

    # 청크로 묶기
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chars:
            current_chunk += sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    print(f"[SmartChunk] {len(chunks)}개 청크 생성")

    # 각 청크 생성 및 병합
    from pydub import AudioSegment
    import io

    audio_segments = []

    for idx, chunk in enumerate(chunks):
        print(f"  청크 {idx+1}/{len(chunks)}: {len(chunk)}자")
        result = generate_scene_direct(chunk, params, timeout // len(chunks) + 30)

        if result.get("success") and result.get("audio_data"):
            try:
                audio = AudioSegment.from_file(
                    io.BytesIO(result["audio_data"]), format="wav"
                )
                audio_segments.append(audio)
            except:
                pass

    if not audio_segments:
        return {"success": False, "error": "모든 청크 생성 실패"}

    # 병합
    combined = audio_segments[0]
    pause = AudioSegment.silent(duration=100)  # 100ms 무음

    for audio in audio_segments[1:]:
        combined = combined + pause + audio

    # 바이트 변환
    output = io.BytesIO()
    combined.export(output, format="wav")
    output.seek(0)

    return {
        "success": True,
        "audio_data": output.read(),
        "duration": len(combined) / 1000,
        "chunks": len(chunks)
    }


def _split_by_sentences(text: str) -> List[str]:
    """문장 단위로 분할"""

    import re

    # 한국어/영어 문장 종결 패턴
    # 마침표, 물음표, 느낌표 뒤에서 분할 (단, 숫자 뒤 마침표 제외)
    pattern = r'(?<=[.!?])\s+'

    sentences = re.split(pattern, text)

    # 빈 문장 제거 및 정리
    result = []
    for s in sentences:
        s = s.strip()
        if s:
            result.append(s + " ")

    return result


# ============================================================
# 호환성을 위한 별칭
# ============================================================

generate_scenes_direct = generate_all_scenes_direct
