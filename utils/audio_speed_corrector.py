# -*- coding: utf-8 -*-
"""
발화속도 가속 보정기 v3.0 - 고정 패턴 기반

문제점 (v1.0~v2.0):
- 에너지 기반 분석이 부정확 (밀도 비율이 음수로 나옴)
- 에너지 ≠ 발화속도 (실제와 반대로 판단)
- 정규화에 의해 효과가 상쇄됨

해결책 (v3.0):
- TTS 모델 특성 기반 고정 감속 패턴 적용
- 에너지 분석 대신 위치 기반 감속
- ⭐ 정규화 "후"에 호출하여 효과 유지
"""

import os
import io
import subprocess
import tempfile
import warnings
from typing import List, Dict, Tuple, Optional
from pydub import AudioSegment
import numpy as np

warnings.filterwarnings("ignore")


class SpeedAccelerationCorrector:
    """
    발화속도 가속 보정기 v3.0 - 고정 패턴 기반

    핵심 원리:
    - TTS 모델은 항상 후반부가 빨라지는 특성이 있음
    - 에너지 분석 대신 고정 감속 패턴 적용
    - 위치에 따라 점진적으로 감속

    감속 패턴 (moderate):
    - 구간 1: atempo=1.00 (유지)
    - 구간 2: atempo=0.975 (2.5% 감속)
    - 구간 3: atempo=0.950 (5.0% 감속)
    - 구간 4: atempo=0.925 (7.5% 감속)
    """

    def __init__(
        self,
        correction_profile: str = "moderate",  # mild, moderate, strong
        min_duration_for_correction: float = 3.0,
        num_segments: int = 4,
    ):
        # 보정 프로파일별 설정
        profiles = {
            "mild": {
                "max_slowdown": 0.06,  # 최대 6% 감속
                "description": "약한 보정"
            },
            "moderate": {
                "max_slowdown": 0.10,  # 최대 10% 감속
                "description": "중간 보정"
            },
            "strong": {
                "max_slowdown": 0.15,  # 최대 15% 감속
                "description": "강한 보정"
            }
        }

        self.profile = profiles.get(correction_profile, profiles["moderate"])
        self.correction_profile = correction_profile
        self.min_duration_for_correction = min_duration_for_correction
        self.num_segments = num_segments

        self.ffmpeg_available = self._check_ffmpeg()

        print(f"\n[SpeedCorrector] 초기화 (v3.0 - 고정 패턴)")
        print(f"  보정 프로파일: {correction_profile} ({self.profile['description']})")
        print(f"  최대 감속: {self.profile['max_slowdown']*100:.0f}%")
        print(f"  구간 수: {num_segments}")
        print(f"  최소 보정 길이: {min_duration_for_correction}초")

    def _check_ffmpeg(self) -> bool:
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False

    def correct_scene_bytes(
        self,
        audio_data: bytes,
        text: str,
        scene_id: int = 0
    ) -> Tuple[bytes, float]:
        """
        바이트 데이터로 씬 보정 (고정 패턴 기반)
        """

        if not audio_data:
            return audio_data, 0

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
        except Exception as e:
            print(f"  [Scene {scene_id}] ❌ 오디오 로드 실패: {e}")
            return audio_data, 0

        total_duration = len(audio) / 1000

        # 짧은 오디오는 보정 불필요
        if total_duration < self.min_duration_for_correction:
            print(f"[SpeedCorrector] 씬 {scene_id}: ⏭️ 짧음 ({total_duration:.1f}초), 스킵")
            return audio_data, total_duration

        print(f"\n[SpeedCorrector] 씬 {scene_id} 가속 보정 시작")
        print(f"  원본: {total_duration:.2f}초")
        print(f"  프로파일: {self.correction_profile}")

        # 고정 감속 패턴 적용
        corrected_audio = self._apply_fixed_slowdown(audio)

        # 결과 반환
        output = io.BytesIO()
        corrected_audio.export(output, format="wav", parameters=["-ar", "24000", "-ac", "1"])
        output.seek(0)

        new_duration = len(corrected_audio) / 1000
        diff_pct = ((new_duration - total_duration) / total_duration) * 100
        print(f"  → 보정 완료: {total_duration:.2f}초 → {new_duration:.2f}초 ({diff_pct:+.1f}%)")

        return output.read(), new_duration

    def _apply_fixed_slowdown(self, audio: AudioSegment) -> AudioSegment:
        """
        고정 감속 패턴 적용

        원리:
        - 오디오를 N개 구간으로 분할
        - 각 구간에 위치 기반 감속 적용
        - 후반부일수록 더 많이 감속 (첫 구간은 유지)
        """

        total_duration = len(audio)
        segment_duration = total_duration // self.num_segments

        corrected_segments = []
        max_slowdown = self.profile["max_slowdown"]

        for i in range(self.num_segments):
            start = i * segment_duration
            end = start + segment_duration if i < self.num_segments - 1 else total_duration

            seg = audio[start:end]

            # 첫 구간은 변경 없음
            if i == 0:
                corrected_segments.append(seg)
                continue

            # 위치 기반 감속 계수 계산 (선형: 0 → max_slowdown)
            position = i / (self.num_segments - 1)
            slowdown_factor = position * max_slowdown

            # atempo 계산 (1.0 미만 = 느리게)
            atempo = 1.0 - slowdown_factor
            atempo = max(0.85, min(1.0, atempo))  # 0.85 ~ 1.0 범위

            # atempo 적용
            if atempo < 0.98:  # 2% 이상 차이날 때만
                seg = self._apply_atempo(seg, atempo)
                print(f"    구간 {i+1}/{self.num_segments}: atempo={atempo:.3f} ({slowdown_factor*100:.1f}% 감속)")

            corrected_segments.append(seg)

        # 크로스페이드로 합치기
        return self._merge_with_crossfade(corrected_segments)

    def _apply_atempo(self, audio: AudioSegment, atempo: float) -> AudioSegment:
        """FFmpeg atempo 적용"""

        if not self.ffmpeg_available:
            return audio

        try:
            temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

            audio.export(temp_in, format="wav")

            cmd = [
                "ffmpeg", "-y", "-i", temp_in,
                "-af", f"atempo={atempo}",
                "-ar", "24000", "-ac", "1",
                temp_out
            ]

            subprocess.run(cmd, capture_output=True, timeout=30)

            if os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
                result = AudioSegment.from_file(temp_out)
            else:
                result = audio

            for f in [temp_in, temp_out]:
                try:
                    os.remove(f)
                except:
                    pass

            return result

        except Exception as e:
            print(f"    ⚠️ atempo 실패: {e}")
            return audio

    def _merge_with_crossfade(self, segments: List[AudioSegment]) -> AudioSegment:
        """크로스페이드로 자연스럽게 합치기"""

        if not segments:
            return AudioSegment.empty()

        result = segments[0]

        for seg in segments[1:]:
            # 25ms 크로스페이드
            crossfade_ms = min(25, len(result) // 4, len(seg) // 4)
            if crossfade_ms > 5:
                result = result.append(seg, crossfade=crossfade_ms)
            else:
                result = result + seg

        return result


# ============================================================
# 전체 씬 처리 함수
# ============================================================

def correct_all_speed_acceleration(
    scenes: List[Dict],
    correction_profile: str = "moderate",  # mild, moderate, strong
    progress_callback: Optional[callable] = None
) -> List[Dict]:
    """
    모든 씬의 발화속도 가속 보정 (v3.0 - 고정 패턴)

    ⭐ 중요: 이 함수는 정규화 "후"에 호출해야 효과가 유지됩니다!

    Args:
        scenes: 씬 리스트 [{scene_id, text, audio_data, ...}, ...]
        correction_profile: 보정 강도 (mild/moderate/strong)
        progress_callback: 진행 콜백

    Returns:
        보정된 씬 리스트
    """

    corrector = SpeedAccelerationCorrector(
        correction_profile=correction_profile,
        min_duration_for_correction=3.0,
        num_segments=4
    )

    results = []
    total = len(scenes)
    valid_scenes = [s for s in scenes if s.get("audio_data") and s.get("success")]

    if not valid_scenes:
        print("[SpeedCorrector] 보정할 씬 없음")
        return scenes

    print(f"\n{'='*60}")
    print(f"[SpeedCorrector] {len(valid_scenes)}개 씬 가속 보정 시작")
    print(f"  방식: 고정 패턴 기반 (v3.0)")
    print(f"  프로파일: {correction_profile}")
    print(f"{'='*60}")

    corrected_count = 0

    for idx, scene in enumerate(scenes):
        if progress_callback:
            try:
                progress_callback(idx, total, f"가속 보정: 씬 {scene.get('scene_id', idx+1)}")
            except:
                pass

        # 오디오가 없거나 실패한 씬은 그대로 유지
        if not scene.get("audio_data") or not scene.get("success"):
            results.append(scene)
            continue

        text = scene.get("text", "")
        scene_id = scene.get("scene_id", idx + 1)

        # 가속 보정
        corrected_audio, new_duration = corrector.correct_scene_bytes(
            scene.get("audio_data"),
            text,
            scene_id
        )

        # 보정 여부 확인
        original_duration = scene.get("duration", 0)
        was_corrected = abs(new_duration - original_duration) > 0.1 if original_duration else True

        if was_corrected:
            corrected_count += 1

        results.append({
            **scene,
            "audio_data": corrected_audio,
            "duration": new_duration,
            "speed_corrected": was_corrected
        })

    print(f"\n{'='*60}")
    print(f"[SpeedCorrector] 가속 보정 완료!")
    print(f"  보정된 씬: {corrected_count}/{len(valid_scenes)}개")
    print(f"{'='*60}")

    if progress_callback:
        try:
            progress_callback(total, total, "가속 보정 완료")
        except:
            pass

    return results
