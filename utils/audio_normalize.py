# -*- coding: utf-8 -*-
"""
오디오 정규화 유틸리티

씬별 TTS 음성의 음량, 속도, 무음 구간을 일관되게 처리합니다.
- 음량 정규화 (RMS/LUFS)
- 발화 속도 계산 및 조정
- 무음 구간 표준화
- 피크 리미팅
"""

import os
import tempfile
import subprocess
import json
from typing import Optional, Tuple, List, Callable
from pathlib import Path


def _check_pydub():
    """pydub 사용 가능 여부 확인"""
    try:
        from pydub import AudioSegment
        return True
    except ImportError:
        return False


def _check_ffmpeg():
    """FFmpeg 사용 가능 여부 확인"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


# ============================================================
# 음량 정규화
# ============================================================

def normalize_loudness_rms(
    audio_data: bytes,
    target_dBFS: float = -20.0
) -> bytes:
    """
    RMS 기반 음량 정규화

    Args:
        audio_data: WAV 오디오 바이트 데이터
        target_dBFS: 목표 음량 (dBFS). -20이 일반적

    Returns:
        정규화된 WAV 바이트 데이터
    """
    if not _check_pydub():
        return audio_data

    from pydub import AudioSegment
    import io

    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
        current_dBFS = audio.dBFS

        if current_dBFS == float('-inf'):
            # 무음인 경우 그대로 반환
            return audio_data

        change_in_dBFS = target_dBFS - current_dBFS
        normalized = audio.apply_gain(change_in_dBFS)

        # BytesIO로 출력
        output = io.BytesIO()
        normalized.export(output, format="wav")
        output.seek(0)
        return output.read()

    except Exception as e:
        print(f"[Normalize] RMS 정규화 실패: {e}")
        return audio_data


def normalize_loudness_lufs(
    audio_path: str,
    target_lufs: float = -16.0,
    output_path: Optional[str] = None
) -> str:
    """
    LUFS 기반 음량 정규화 (방송 표준)
    FFmpeg loudnorm 필터 사용

    Args:
        audio_path: 입력 파일 경로
        target_lufs: 목표 LUFS (-16이 스트리밍 표준)
        output_path: 출력 파일 경로 (없으면 자동 생성)

    Returns:
        정규화된 파일 경로
    """
    if output_path is None:
        output_path = tempfile.NamedTemporaryFile(
            delete=False, suffix=".wav"
        ).name

    if not _check_ffmpeg():
        # FFmpeg 없으면 pydub RMS 폴백
        return _normalize_lufs_fallback(audio_path, output_path)

    try:
        # 2-pass loudnorm (더 정확함)
        # Pass 1: 분석
        analyze_cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-af", f"loudnorm=I={target_lufs}:print_format=json",
            "-f", "null", "-"
        ]

        result = subprocess.run(
            analyze_cmd,
            capture_output=True,
            text=True
        )

        # JSON 결과 파싱 (stderr에 출력됨)
        output = result.stderr
        json_start = output.rfind('{')
        json_end = output.rfind('}') + 1

        if json_start >= 0 and json_end > json_start:
            loudnorm_stats = json.loads(output[json_start:json_end])

            # Pass 2: 정규화 적용
            measured_i = loudnorm_stats.get("input_i", "-24")
            measured_tp = loudnorm_stats.get("input_tp", "-2")
            measured_lra = loudnorm_stats.get("input_lra", "7")
            measured_thresh = loudnorm_stats.get("input_thresh", "-34")

            normalize_cmd = [
                "ffmpeg", "-y", "-i", audio_path,
                "-af", (
                    f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:"
                    f"measured_I={measured_i}:measured_TP={measured_tp}:"
                    f"measured_LRA={measured_lra}:measured_thresh={measured_thresh}:"
                    "linear=true"
                ),
                "-ar", "24000",
                output_path
            ]

            subprocess.run(normalize_cmd, check=True, capture_output=True)
            return output_path

    except Exception as e:
        print(f"[Normalize] LUFS 정규화 실패, RMS 폴백: {e}")

    return _normalize_lufs_fallback(audio_path, output_path)


def _normalize_lufs_fallback(audio_path: str, output_path: str) -> str:
    """LUFS 정규화 실패 시 RMS 폴백"""
    if not _check_pydub():
        # pydub도 없으면 원본 복사
        import shutil
        shutil.copy(audio_path, output_path)
        return output_path

    from pydub import AudioSegment
    from pydub.effects import normalize

    try:
        audio = AudioSegment.from_file(audio_path)
        # RMS 정규화
        target_dBFS = -20.0
        if audio.dBFS != float('-inf'):
            change = target_dBFS - audio.dBFS
            audio = audio.apply_gain(change)
        # 피크 정규화
        audio = normalize(audio, headroom=1.0)
        audio.export(output_path, format="wav")
        return output_path
    except Exception as e:
        print(f"[Normalize] 폴백 정규화도 실패: {e}")
        import shutil
        shutil.copy(audio_path, output_path)
        return output_path


def normalize_peak(audio_data: bytes, headroom_dB: float = -1.0) -> bytes:
    """
    피크 정규화 (클리핑 방지)

    Args:
        audio_data: WAV 오디오 바이트 데이터
        headroom_dB: 피크에서 남길 여유 공간

    Returns:
        정규화된 WAV 바이트 데이터
    """
    if not _check_pydub():
        return audio_data

    from pydub import AudioSegment
    from pydub.effects import normalize
    import io

    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
        normalized = normalize(audio, headroom=abs(headroom_dB))

        output = io.BytesIO()
        normalized.export(output, format="wav")
        output.seek(0)
        return output.read()

    except Exception as e:
        print(f"[Normalize] 피크 정규화 실패: {e}")
        return audio_data


# ============================================================
# 발화 속도 계산 및 조정
# ============================================================

def calculate_speech_rate(audio_data: bytes, text: str) -> float:
    """
    발화 속도 계산 (초당 글자 수)

    Args:
        audio_data: WAV 오디오 바이트 데이터
        text: 원본 텍스트

    Returns:
        초당 글자 수
    """
    if not _check_pydub() or not audio_data or not text:
        return 0.0

    from pydub import AudioSegment
    import io

    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
        duration_sec = len(audio) / 1000

        if duration_sec <= 0:
            return 0.0

        # 공백 제외한 글자 수
        char_count = len(text.replace(" ", "").replace("\n", ""))
        return char_count / duration_sec

    except Exception as e:
        print(f"[Speed] 속도 계산 실패: {e}")
        return 0.0


def calculate_speech_rate_from_file(audio_path: str, text: str) -> float:
    """파일 경로로 발화 속도 계산"""
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        return calculate_speech_rate(audio_data, text)
    except:
        return 0.0


def adjust_speed(
    audio_data: bytes,
    speed_ratio: float,
    preserve_pitch: bool = True
) -> bytes:
    """
    오디오 속도 조정

    Args:
        audio_data: WAV 오디오 바이트 데이터
        speed_ratio: 속도 비율 (1.0 = 원본, 1.2 = 20% 빠르게, 0.8 = 20% 느리게)
        preserve_pitch: 피치 유지 여부

    Returns:
        조정된 WAV 바이트 데이터
    """
    # 5% 미만 차이는 무시
    if abs(speed_ratio - 1.0) < 0.05:
        return audio_data

    # 극단적인 조정 방지 (0.75x ~ 1.33x)
    speed_ratio = max(0.75, min(1.33, speed_ratio))

    if not _check_ffmpeg():
        return audio_data

    try:
        # 임시 파일로 저장
        input_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        input_file.write(audio_data)
        input_file.close()

        output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        output_file.close()

        if preserve_pitch:
            # atempo 필터 (피치 유지)
            # atempo는 0.5 ~ 2.0 범위만 지원
            atempo_filters = []
            remaining = speed_ratio

            while remaining > 2.0:
                atempo_filters.append("atempo=2.0")
                remaining /= 2.0
            while remaining < 0.5:
                atempo_filters.append("atempo=0.5")
                remaining *= 2.0

            atempo_filters.append(f"atempo={remaining}")
            filter_str = ",".join(atempo_filters)
        else:
            # setrate + asetrate (피치도 함께 변경)
            filter_str = f"asetrate=24000*{speed_ratio},aresample=24000"

        cmd = [
            "ffmpeg", "-y", "-i", input_file.name,
            "-af", filter_str,
            "-ar", "24000",
            output_file.name
        ]

        subprocess.run(cmd, check=True, capture_output=True)

        with open(output_file.name, "rb") as f:
            result = f.read()

        # 임시 파일 정리
        os.unlink(input_file.name)
        os.unlink(output_file.name)

        return result

    except Exception as e:
        print(f"[Speed] 속도 조정 실패: {e}")
        return audio_data


def normalize_speed_to_target(
    audio_data: bytes,
    text: str,
    target_rate: float
) -> Tuple[bytes, float, float]:
    """
    목표 발화 속도에 맞게 오디오 속도 조정

    Args:
        audio_data: WAV 오디오 바이트 데이터
        text: 원본 텍스트
        target_rate: 목표 발화 속도 (글자/초)

    Returns:
        (조정된 오디오, 원본 속도, 최종 속도)
    """
    original_rate = calculate_speech_rate(audio_data, text)

    if original_rate <= 0 or target_rate <= 0:
        return audio_data, original_rate, original_rate

    speed_ratio = original_rate / target_rate
    adjusted = adjust_speed(audio_data, speed_ratio, preserve_pitch=True)
    final_rate = calculate_speech_rate(adjusted, text)

    return adjusted, original_rate, final_rate


# ============================================================
# 무음 표준화
# ============================================================

def standardize_silence(
    audio_data: bytes,
    leading_ms: int = 100,
    trailing_ms: int = 100,
    silence_thresh_dB: float = -50.0
) -> bytes:
    """
    앞뒤 무음 구간 표준화

    Args:
        audio_data: WAV 오디오 바이트 데이터
        leading_ms: 앞에 추가할 무음 (밀리초)
        trailing_ms: 뒤에 추가할 무음 (밀리초)
        silence_thresh_dB: 무음 판정 임계값

    Returns:
        무음 표준화된 WAV 바이트 데이터
    """
    if not _check_pydub():
        return audio_data

    from pydub import AudioSegment
    from pydub.silence import detect_leading_silence
    import io

    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")

        # 앞쪽 무음 제거
        start_trim = detect_leading_silence(audio, silence_threshold=silence_thresh_dB)

        # 뒤쪽 무음 제거 (오디오 뒤집어서 앞쪽 무음 감지)
        end_trim = detect_leading_silence(
            audio.reverse(), silence_threshold=silence_thresh_dB
        )

        # 트리밍 (안전한 범위 내)
        start_trim = min(start_trim, len(audio) // 2)
        end_trim = min(end_trim, len(audio) // 2)

        if start_trim < len(audio) - end_trim:
            trimmed = audio[start_trim:len(audio) - end_trim]
        else:
            trimmed = audio

        # 표준 무음 추가
        leading_silence = AudioSegment.silent(duration=leading_ms, frame_rate=audio.frame_rate)
        trailing_silence = AudioSegment.silent(duration=trailing_ms, frame_rate=audio.frame_rate)

        result = leading_silence + trimmed + trailing_silence

        output = io.BytesIO()
        result.export(output, format="wav")
        output.seek(0)
        return output.read()

    except Exception as e:
        print(f"[Silence] 무음 표준화 실패: {e}")
        return audio_data


# ============================================================
# 통합 정규화 파이프라인
# ============================================================

def normalize_audio_full(
    audio_data: bytes,
    text: str,
    target_lufs: float = -16.0,
    target_speech_rate: Optional[float] = None,
    standardize_silence_ms: Tuple[int, int] = (100, 100),
    apply_peak_normalize: bool = True
) -> dict:
    """
    전체 오디오 정규화 파이프라인

    Args:
        audio_data: WAV 오디오 바이트 데이터
        text: 원본 텍스트 (속도 계산용)
        target_lufs: 목표 음량 (LUFS)
        target_speech_rate: 목표 발화 속도 (글자/초). None이면 속도 조정 안함
        standardize_silence_ms: (앞 무음, 뒤 무음) 밀리초
        apply_peak_normalize: 피크 정규화 적용 여부

    Returns:
        {
            "audio_data": bytes,
            "original_rate": float,
            "final_rate": float,
            "original_duration": float,
            "final_duration": float
        }
    """
    print(f"[Normalize] normalize_audio_full 호출")
    print(f"[Normalize] 입력: audio_data={len(audio_data)} bytes, text={len(text)}자")
    print(f"[Normalize] 설정: target_lufs={target_lufs}, target_speech_rate={target_speech_rate}")

    if not _check_pydub():
        print("[Normalize] ❌ pydub 미설치 - 정규화 스킵")
        return {
            "audio_data": audio_data,
            "original_rate": 0,
            "final_rate": 0,
            "original_duration": 0,
            "final_duration": 0
        }

    from pydub import AudioSegment
    import io

    try:
        # 원본 정보
        original_audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
        original_duration = len(original_audio) / 1000
        original_rate = calculate_speech_rate(audio_data, text)
        print(f"[Normalize] 원본: {original_duration:.2f}초, {original_rate:.2f}글자/초, {original_audio.dBFS:.1f}dBFS")

        current_audio = audio_data
        final_rate = original_rate

        # 1. 속도 조정 (필요한 경우)
        if target_speech_rate and original_rate > 0:
            current_audio, _, final_rate = normalize_speed_to_target(
                current_audio, text, target_speech_rate
            )

        # 2. 무음 표준화
        if standardize_silence_ms:
            current_audio = standardize_silence(
                current_audio,
                leading_ms=standardize_silence_ms[0],
                trailing_ms=standardize_silence_ms[1]
            )

        # 3. 피크 정규화
        if apply_peak_normalize:
            current_audio = normalize_peak(current_audio, headroom_dB=-1.0)

        # 4. LUFS 정규화 (파일 기반이므로 임시 파일 사용)
        temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_input.write(current_audio)
        temp_input.close()

        temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_output.close()

        normalize_loudness_lufs(temp_input.name, target_lufs, temp_output.name)

        with open(temp_output.name, "rb") as f:
            current_audio = f.read()

        # 임시 파일 정리
        os.unlink(temp_input.name)
        os.unlink(temp_output.name)

        # 최종 정보
        final_audio = AudioSegment.from_file(io.BytesIO(current_audio), format="wav")
        final_duration = len(final_audio) / 1000

        return {
            "audio_data": current_audio,
            "original_rate": original_rate,
            "final_rate": final_rate,
            "original_duration": original_duration,
            "final_duration": final_duration
        }

    except Exception as e:
        print(f"[Normalize] 전체 정규화 실패: {e}")
        return {
            "audio_data": audio_data,
            "original_rate": 0,
            "final_rate": 0,
            "original_duration": 0,
            "final_duration": 0,
            "error": str(e)
        }


# ============================================================
# 배치 정규화 (씬별 일괄 처리)
# ============================================================

def calculate_median_speech_rate(scene_audios: List[dict]) -> float:
    """여러 씬의 중간 발화 속도 계산"""
    rates = []

    for scene in scene_audios:
        audio_data = scene.get("audio_data")
        text = scene.get("text", "")

        if audio_data and text:
            rate = calculate_speech_rate(audio_data, text)
            if rate > 0:
                rates.append(rate)

    if not rates:
        return 0.0

    # 중간값 반환 (이상치 영향 최소화)
    rates.sort()
    mid = len(rates) // 2
    if len(rates) % 2 == 0:
        return (rates[mid - 1] + rates[mid]) / 2
    return rates[mid]


def normalize_scenes_batch(
    scene_audios: List[dict],
    target_lufs: float = -16.0,
    use_consistent_speed: bool = True,
    standardize_silence_ms: Tuple[int, int] = (100, 100),
    progress_callback: Optional[Callable] = None
) -> List[dict]:
    """
    여러 씬 오디오를 일괄 정규화

    Args:
        scene_audios: [{"scene_id": 1, "audio_data": bytes, "text": "..."}, ...]
        target_lufs: 목표 음량
        use_consistent_speed: True면 모든 씬의 평균 속도로 맞춤
        standardize_silence_ms: (앞 무음, 뒤 무음) 밀리초. None이면 무음 조정 안함
        progress_callback: 진행 콜백 (current, total, message)

    Returns:
        정규화된 씬 리스트
    """
    print(f"[Normalize] normalize_scenes_batch 시작")
    print(f"[Normalize] 입력 씬 수: {len(scene_audios)}")
    print(f"[Normalize] 설정: target_lufs={target_lufs}, use_consistent_speed={use_consistent_speed}")
    print(f"[Normalize] 무음 설정: {standardize_silence_ms}")

    if not scene_audios:
        print("[Normalize] ❌ 입력 씬 없음 - 빈 리스트 반환")
        return []

    # 1. 모든 씬의 발화 속도 계산 및 중간값 결정
    target_rate = None
    if use_consistent_speed:
        target_rate = calculate_median_speech_rate(scene_audios)
        if target_rate > 0:
            print(f"[Normalize] 목표 발화 속도: {target_rate:.2f} 글자/초")
        else:
            print("[Normalize] ⚠️ 발화 속도 계산 불가 - 속도 조정 스킵")

    # 2. 각 씬 정규화
    normalized_scenes = []
    total = len(scene_audios)

    for idx, scene in enumerate(scene_audios):
        scene_id = scene.get("scene_id", idx + 1)
        audio_data = scene.get("audio_data")
        text = scene.get("text", "")

        if progress_callback:
            progress_callback(idx, total, f"씬 {scene_id} 정규화 중...")

        if not audio_data:
            print(f"[Normalize] 씬 {scene_id}: ❌ 오디오 데이터 없음")
            normalized_scenes.append({
                **scene,
                "normalized": False,
                "error": "오디오 데이터 없음"
            })
            continue

        print(f"[Normalize] 씬 {scene_id}: 정규화 처리 중...")
        result = normalize_audio_full(
            audio_data=audio_data,
            text=text,
            target_lufs=target_lufs,
            target_speech_rate=target_rate,
            standardize_silence_ms=standardize_silence_ms
        )

        print(f"[Normalize] 씬 {scene_id}: ✅ 완료 (원본 {result['original_duration']:.1f}초 → 최종 {result['final_duration']:.1f}초)")

        normalized_scenes.append({
            **scene,
            "audio_data": result["audio_data"],
            "original_rate": result["original_rate"],
            "final_rate": result["final_rate"],
            "original_duration": result["original_duration"],
            "final_duration": result["final_duration"],
            "normalized": True
        })

    if progress_callback:
        progress_callback(total, total, "정규화 완료!")

    success_count = sum(1 for s in normalized_scenes if s.get("normalized"))
    print(f"[Normalize] 배치 정규화 완료: {success_count}/{total} 씬 성공")
    return normalized_scenes


# ============================================================
# 오디오 분석 (디버깅/표시용)
# ============================================================

def analyze_audio(audio_data: bytes, text: str = "") -> dict:
    """
    오디오 분석 정보 반환

    Args:
        audio_data: WAV 오디오 바이트 데이터
        text: 원본 텍스트

    Returns:
        분석 정보 dict
    """
    if not _check_pydub():
        return {"error": "pydub not available"}

    from pydub import AudioSegment
    import io

    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")

        info = {
            "duration_sec": len(audio) / 1000,
            "sample_rate": audio.frame_rate,
            "channels": audio.channels,
            "dBFS": audio.dBFS if audio.dBFS != float('-inf') else -100,
            "max_dBFS": audio.max_dBFS,
        }

        if text:
            info["char_count"] = len(text.replace(" ", ""))
            info["speech_rate"] = calculate_speech_rate(audio_data, text)

        return info

    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 완벽 정규화 (±5% 편차 목표)
# ============================================================

def normalize_scenes_perfect(
    scene_results: List[dict],
    target_rate: Optional[float] = None,
    target_lufs: float = -16.0,
    max_speed_adjustment: float = 0.15,
    progress_callback: Optional[Callable] = None
) -> List[dict]:
    """
    씬별 완벽 정규화 - 발화 속도 ±5% 이내, 음량 ±2dB 이내 목표

    1. 모든 씬의 발화 속도 분석
    2. 중간값 기준으로 속도 정규화
    3. LUFS 기반 음량 정규화
    4. 무음 표준화
    5. 결과 검증

    Args:
        scene_results: 생성 결과 리스트 (audio_data 포함)
        target_rate: 목표 발화 속도 (None이면 중간값 자동 계산)
        target_lufs: 목표 음량 (-16 LUFS 권장)
        max_speed_adjustment: 최대 속도 조정 비율 (0.15 = ±15%)
        progress_callback: 진행 콜백

    Returns:
        정규화된 결과 리스트
    """
    if not _check_pydub():
        print("[Normalize] pydub 미설치 - 정규화 스킵")
        return scene_results

    from pydub import AudioSegment
    from pydub.effects import normalize
    import io
    import numpy as np

    print("=" * 60)
    print("[Normalize] 완벽 정규화 시작")
    print("=" * 60)

    # 유효한 씬만 필터링
    valid_scenes = []
    for r in scene_results:
        if r.get("audio_data") and r.get("success", True):
            valid_scenes.append(r)

    if not valid_scenes:
        print("[Normalize] 정규화할 씬 없음")
        return scene_results

    print(f"\n[Step 1] 씬 분석 ({len(valid_scenes)}개)")

    # 1단계: 모든 씬 분석
    scene_stats = []
    for scene in valid_scenes:
        scene_id = scene.get("scene_id", 0)
        text = scene.get("text", "")
        audio_data = scene.get("audio_data")

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
            duration = len(audio) / 1000
            char_count = len(text.replace(" ", "").replace("\n", ""))
            rate = char_count / duration if duration > 0 else 0
            dbfs = audio.dBFS if audio.dBFS != float('-inf') else -100

            scene_stats.append({
                "scene_id": scene_id,
                "duration": duration,
                "char_count": char_count,
                "rate": rate,
                "dbfs": dbfs,
                "text": text,
                "audio_data": audio_data,
                "audio": audio
            })

            print(f"  씬 {scene_id}: {rate:.2f} 글자/초, {dbfs:.1f} dBFS, {duration:.1f}초")

        except Exception as e:
            print(f"  씬 {scene_id}: 분석 실패 - {e}")

    if not scene_stats:
        print("[Normalize] 분석된 씬 없음")
        return scene_results

    # 2단계: 목표값 계산
    print(f"\n[Step 2] 목표값 계산")

    rates = [s["rate"] for s in scene_stats if s["rate"] > 0]
    dbfs_values = [s["dbfs"] for s in scene_stats if s["dbfs"] > -100]

    if target_rate is None and rates:
        target_rate = float(np.median(rates))

    rate_std = float(np.std(rates)) if rates else 0
    rate_range = (max(rates) - min(rates)) if rates else 0
    rate_deviation = (rate_range / target_rate * 100) if target_rate else 0

    print(f"  발화속도 범위: {min(rates):.2f} ~ {max(rates):.2f} 글자/초")
    print(f"  발화속도 편차: ±{rate_deviation/2:.1f}% (목표: ±5%)")
    print(f"  목표 발화속도: {target_rate:.2f} 글자/초")
    print(f"  목표 음량: {target_lufs} LUFS (≈ -20 dBFS)")

    # 3단계: 각 씬 정규화
    print(f"\n[Step 3] 씬별 정규화")

    target_dbfs = -20.0  # -16 LUFS ≈ -20 dBFS
    normalized_count = 0

    for idx, stats in enumerate(scene_stats):
        scene_id = stats["scene_id"]

        if progress_callback:
            progress_callback(idx, len(scene_stats), f"씬 {scene_id} 정규화 중...")

        print(f"\n  [씬 {scene_id}]")

        audio = stats["audio"]
        text = stats["text"]
        current_rate = stats["rate"]
        original_duration = stats["duration"]

        speed_adjusted = False
        volume_adjusted = False

        # 3-1: 속도 정규화
        if current_rate > 0 and target_rate > 0:
            speed_ratio = current_rate / target_rate

            # 조정 필요 여부 (3% 이상 차이)
            if abs(speed_ratio - 1.0) > 0.03:
                # 조정 범위 제한
                speed_ratio = max(1 - max_speed_adjustment, min(1 + max_speed_adjustment, speed_ratio))

                print(f"    속도 조정: {speed_ratio:.3f}x ({current_rate:.2f} → {target_rate:.2f} 글자/초)")

                # atempo 범위 확인 (0.5 ~ 2.0)
                atempo = max(0.5, min(2.0, speed_ratio))

                # 임시 파일로 FFmpeg 처리
                try:
                    temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
                    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

                    audio.export(temp_input, format="wav")

                    cmd = [
                        "ffmpeg", "-y", "-i", temp_input,
                        "-af", f"atempo={atempo}",
                        "-ar", "24000",
                        temp_output
                    ]

                    subprocess.run(cmd, check=True, capture_output=True)
                    audio = AudioSegment.from_file(temp_output)
                    speed_adjusted = True

                    # 임시 파일 정리
                    for f in [temp_input, temp_output]:
                        try:
                            os.unlink(f)
                        except:
                            pass

                except Exception as e:
                    print(f"    ⚠️ 속도 조정 실패: {e}")
            else:
                print(f"    속도 조정 불필요 (차이 3% 미만)")

        # 3-2: 무음 표준화
        audio = standardize_silence(
            _audio_to_bytes(audio),
            leading_ms=80,
            trailing_ms=80
        )
        audio = AudioSegment.from_file(io.BytesIO(audio), format="wav")
        print(f"    무음 표준화: 앞뒤 80ms")

        # 3-3: 음량 정규화
        current_dbfs = audio.dBFS
        if current_dbfs != float('-inf'):
            change = target_dbfs - current_dbfs
            change = max(-12, min(12, change))  # 최대 ±12dB

            if abs(change) > 0.5:
                audio = audio.apply_gain(change)
                volume_adjusted = True
                print(f"    음량 조정: {current_dbfs:.1f} → {audio.dBFS:.1f} dBFS ({change:+.1f}dB)")
            else:
                print(f"    음량 조정 불필요 (차이 0.5dB 미만)")

        # 3-4: 피크 리미팅
        audio = normalize(audio, headroom=1.0)

        # 결과 저장
        final_duration = len(audio) / 1000
        final_rate = stats["char_count"] / final_duration if final_duration > 0 else 0

        print(f"    최종: {final_duration:.2f}초, {final_rate:.2f} 글자/초, {audio.dBFS:.1f} dBFS")

        # 원본 결과에 정규화 정보 추가
        for scene in scene_results:
            if scene.get("scene_id") == scene_id:
                scene["audio_data"] = _audio_to_bytes(audio)
                scene["original_duration"] = original_duration
                scene["final_duration"] = final_duration
                scene["original_rate"] = current_rate
                scene["final_rate"] = final_rate
                scene["final_dbfs"] = audio.dBFS
                scene["speed_adjusted"] = speed_adjusted
                scene["volume_adjusted"] = volume_adjusted
                scene["normalized"] = True
                normalized_count += 1
                break

    if progress_callback:
        progress_callback(len(scene_stats), len(scene_stats), "정규화 완료!")

    # 4단계: 결과 검증
    print(f"\n[Step 4] 결과 검증")

    final_rates = [s.get("final_rate", 0) for s in scene_results if s.get("final_rate")]
    final_dbfs = [s.get("final_dbfs", 0) for s in scene_results if s.get("final_dbfs")]

    if final_rates:
        final_rate_range = max(final_rates) - min(final_rates)
        final_rate_deviation = (final_rate_range / np.mean(final_rates)) * 100 if np.mean(final_rates) > 0 else 0

        status = "✅" if final_rate_deviation <= 10 else "⚠️"
        print(f"  {status} 발화속도 편차: ±{final_rate_deviation/2:.1f}% (목표: ±5%)")
        print(f"     범위: {min(final_rates):.2f} ~ {max(final_rates):.2f} 글자/초")

    if final_dbfs:
        dbfs_range = max(final_dbfs) - min(final_dbfs)

        status = "✅" if dbfs_range <= 4 else "⚠️"
        print(f"  {status} 음량 편차: {dbfs_range:.1f} dB (목표: ±2dB)")
        print(f"     범위: {min(final_dbfs):.1f} ~ {max(final_dbfs):.1f} dBFS")

    print(f"\n[Normalize] 완료: {normalized_count}/{len(valid_scenes)}개 씬 정규화됨")
    print("=" * 60)

    return scene_results


def _audio_to_bytes(audio) -> bytes:
    """AudioSegment를 bytes로 변환"""
    import io
    output = io.BytesIO()
    audio.export(output, format="wav")
    output.seek(0)
    return output.read()
