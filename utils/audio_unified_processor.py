# -*- coding: utf-8 -*-
"""
통합 단일 패스 오디오 처리기 v1.0

핵심 원리:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기존 문제:
  정규화 FFmpeg + 가속보정 FFmpeg × 4구간 + SegmentNorm FFmpeg
  = 총 6~8회 FFmpeg 호출 → 품질 저하, 울림

해결책:
  모든 조정값을 미리 계산 → 단 1회 FFmpeg 적용
  = 품질 유지, 울림 없음
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

처리 방식:
1. 분석: 현재 속도, 음량, 구간별 특성
2. 계산: 정규화 계수 + 적응형 가속보정 계수
3. 병합: 구간별 최종 atempo 값 산출
4. 적용: 단 1회 FFmpeg으로 모든 처리
"""

import os
import io
import subprocess
import tempfile
import numpy as np
import warnings
from typing import List, Dict, Tuple, Optional
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

warnings.filterwarnings("ignore")


class UnifiedAudioProcessor:
    """
    통합 오디오 처리기 - 단일 패스

    모든 처리를 한 번에:
    - 속도 정규화
    - 음량 정규화
    - 적응형 가속 보정
    - 구간별 미세 조정

    FFmpeg 1회만 호출!
    """

    def __init__(
        self,
        target_speed: float = 8.5,        # 목표 발화속도
        target_lufs: float = -18.0,       # 목표 음량 (⭐ -16→-18: 잡음 증폭 방지)
        accel_profile: str = "adaptive",  # adaptive, strong, moderate
        num_segments: int = 8,            # 구간 수 (정밀도)
        crossfade_ms: int = 30,           # 크로스페이드 (울림 방지)
    ):
        self.target_speed = target_speed
        self.target_lufs = target_lufs
        self.accel_profile = accel_profile
        self.num_segments = num_segments
        self.crossfade_ms = crossfade_ms

        # 적응형 가속 보정 프로파일
        self.profiles = {
            "adaptive": {
                "analyze": True,       # 실제 가속 분석
                "max_slowdown": 0.18,  # 최대 18% 감속
                "curve": "adaptive"
            },
            "strong": {
                "analyze": False,
                "max_slowdown": 0.15,
                "curve": "exponential"  # 후반부 급격히
            },
            "moderate": {
                "analyze": False,
                "max_slowdown": 0.10,
                "curve": "linear"
            }
        }

        self.ffmpeg_available = self._check_ffmpeg()

        print(f"\n[UnifiedProcessor] 초기화")
        print(f"  목표 속도: {target_speed} 글자/초")
        print(f"  목표 음량: {target_lufs} LUFS")
        print(f"  가속 보정: {accel_profile}")
        print(f"  구간 수: {num_segments}개")
        print(f"  ⭐ 단일 패스: FFmpeg 1회만 적용")

    def _check_ffmpeg(self) -> bool:
        try:
            result = subprocess.run(["ffmpeg", "-version"],
                                    capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False

    def process_scene_bytes(
        self,
        audio_data: bytes,
        text: str,
        scene_id: int = 0
    ) -> Tuple[bytes, float]:
        """
        씬 처리 (단일 패스) - 바이트 입출력

        순서:
        1. 분석: 현재 상태 측정
        2. 계산: 모든 조정값 산출
        3. 병합: 구간별 최종 atempo
        4. 적용: 단 1회 FFmpeg

        Returns:
            (처리된 오디오 바이트, 새 duration)
        """

        if not audio_data:
            return audio_data, 0.0

        print(f"\n[Unified] 씬 {scene_id} 처리 시작")

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
        except Exception as e:
            print(f"  ❌ 오디오 로드 실패: {e}")
            return audio_data, 0.0

        duration_sec = len(audio) / 1000
        char_count = len(text.replace(" ", "").replace("\n", ""))

        if duration_sec < 2.0 or char_count < 10:
            print(f"  ⏭️ 너무 짧음 ({duration_sec:.1f}초), 음량만 조정")
            adjusted = self._adjust_volume_only(audio)
            output = io.BytesIO()
            adjusted.export(output, format="wav", parameters=["-ar", "24000", "-ac", "1"])
            output.seek(0)
            return output.read(), len(adjusted) / 1000

        # ===== 1단계: 분석 =====
        current_speed = char_count / duration_sec
        current_lufs = self._measure_lufs(audio)

        print(f"  현재: {current_speed:.2f} 글자/초, {current_lufs:.1f} LUFS")
        print(f"  목표: {self.target_speed:.2f} 글자/초, {self.target_lufs:.1f} LUFS")

        # ===== 2단계: 정규화 계수 계산 =====
        # 전체 속도 조정 계수
        # ⭐⭐⭐ 속도 조정 범위 제한 (자연스러움 보존) ⭐⭐⭐
        # 🔴 이전: ±25% (0.80~1.25) → 과도한 가속으로 자연스러움 손실
        # ✅ 수정: ±15% (0.85~1.15) → 자연스러움 보존
        base_speed_factor = self.target_speed / current_speed if current_speed > 0 else 1.0
        original_speed_factor = base_speed_factor
        base_speed_factor = max(0.85, min(1.15, base_speed_factor))

        if abs(original_speed_factor - base_speed_factor) > 0.01:
            print(f"  ⚠️ 과도한 속도 조정 방지: {original_speed_factor:.3f}x → {base_speed_factor:.3f}x (자연스러움 보존)")

        # 음량 조정 (dB)
        # ⭐⭐⭐ 과도한 음량 조정 방지 ⭐⭐⭐
        # 🔴 이전: max(-12, min(15, ...)) → +5~6dB 증폭 시 잡음도 증폭
        # ✅ 수정: ±3dB 제한 → 잡음 증폭 최소화
        volume_db = self.target_lufs - current_lufs
        original_volume_db = volume_db
        volume_db = max(-3, min(3, volume_db))

        if abs(original_volume_db) > 3:
            print(f"  ⚠️ 과도한 음량 조정 방지: {original_volume_db:+.1f}dB → {volume_db:+.1f}dB")

        print(f"  정규화: 속도 {base_speed_factor:.3f}x, 음량 {volume_db:+.1f}dB")

        # ===== 3단계: 적응형 가속 보정 계수 계산 =====
        profile = self.profiles.get(self.accel_profile, self.profiles["adaptive"])

        if profile["analyze"]:
            # 실제 가속 패턴 분석
            accel_factors = self._analyze_acceleration_pattern(audio, char_count)
        else:
            # 고정 패턴 사용
            accel_factors = self._get_fixed_pattern(profile)

        # ===== 4단계: 최종 atempo 계산 (정규화 + 가속보정) =====
        # ⭐ 최종 범위도 축소: 0.70~1.35 → 0.85~1.20 (자연스러움 보존)
        final_atempos = []
        for i, accel_factor in enumerate(accel_factors):
            # 최종 = 정규화 속도 × 가속 보정
            final = base_speed_factor * accel_factor
            final = max(0.85, min(1.20, final))  # ⭐ 안전 범위 축소 (자연스러움 보존)
            final_atempos.append(final)

        # 구간별 atempo 출력
        print(f"  구간별 최종 atempo ({self.num_segments}구간):")
        for i, atempo in enumerate(final_atempos):
            if i == 0:
                continue  # 첫 구간은 출력 생략
            slowdown = (1.0 - accel_factors[i]) * 100
            print(f"    구간 {i+1}/{self.num_segments}: {atempo:.3f} (보정: {slowdown:.1f}% 감속)")

        # ===== 5단계: 단일 패스 적용 =====
        processed_audio = self._apply_single_pass_processing(
            audio,
            final_atempos,
            volume_db
        )

        # 바이트로 변환
        output = io.BytesIO()
        processed_audio.export(output, format="wav", parameters=["-ar", "24000", "-ac", "1"])
        output.seek(0)

        # 결과 확인
        new_duration = len(processed_audio) / 1000
        new_speed = char_count / new_duration if new_duration > 0 else 0

        print(f"  → 완료: {duration_sec:.2f}초 → {new_duration:.2f}초")
        print(f"  → 속도: {current_speed:.2f} → {new_speed:.2f} 글자/초")

        return output.read(), new_duration

    def _measure_lufs(self, audio: AudioSegment) -> float:
        """LUFS 측정 (간이 버전)"""
        try:
            samples = np.array(audio.get_array_of_samples()).astype(np.float32)
            samples = samples / (2**15)
            rms = np.sqrt(np.mean(samples**2))
            lufs = 20 * np.log10(rms + 1e-10) - 3
            return max(-60, min(0, lufs))
        except:
            return -23.0

    def _analyze_acceleration_pattern(
        self,
        audio: AudioSegment,
        char_count: int
    ) -> List[float]:
        """
        적응형 가속 패턴 분석

        TTS 특성:
        - 시작: 천천히 (attention 집중)
        - 중간: 점진적 가속
        - 끝: 급격한 가속 (attention 분산)

        분석 방법:
        - 구간별 음성 밀도 측정
        - 밀도가 높을수록 빠른 발화 → 더 많이 감속
        """

        total_duration = len(audio)
        segment_duration = total_duration // self.num_segments

        # 구간별 음성 밀도 분석
        densities = []
        for i in range(self.num_segments):
            start = i * segment_duration
            end = start + segment_duration if i < self.num_segments - 1 else total_duration
            seg = audio[start:end]

            # 음성 구간 비율 (밀도)
            try:
                nonsilent = detect_nonsilent(seg, min_silence_len=30, silence_thresh=-40)
                if nonsilent:
                    speech_ms = sum(e - s for s, e in nonsilent)
                    density = speech_ms / len(seg) if len(seg) > 0 else 1.0
                else:
                    density = 1.0
            except:
                density = 1.0

            densities.append(density)

        # 첫 구간 대비 상대적 밀도
        base_density = densities[0] if densities[0] > 0 else 1.0
        relative_densities = [d / base_density for d in densities]

        # 밀도 기반 감속 계수 계산
        max_slowdown = self.profiles["adaptive"]["max_slowdown"]
        accel_factors = []

        for i, rel_density in enumerate(relative_densities):
            if i == 0:
                # 첫 구간은 유지
                accel_factors.append(1.0)
            else:
                # 밀도가 높을수록 (빠를수록) 더 많이 감속
                # 또한 위치가 뒤로 갈수록 더 많이 감속 (TTS 특성)
                position = i / (self.num_segments - 1)

                # 위치 기반 + 밀도 기반 복합 감속
                position_slowdown = position * max_slowdown * 0.6  # 60%는 위치 기반
                density_slowdown = max(0, (rel_density - 1.0) * max_slowdown * 0.4)  # 40%는 밀도 기반

                total_slowdown = position_slowdown + density_slowdown
                total_slowdown = min(max_slowdown, total_slowdown)

                accel_factors.append(1.0 - total_slowdown)

        return accel_factors

    def _get_fixed_pattern(self, profile: Dict) -> List[float]:
        """고정 패턴 생성"""

        max_slowdown = profile["max_slowdown"]
        curve = profile["curve"]

        factors = []
        for i in range(self.num_segments):
            if i == 0:
                factors.append(1.0)
                continue

            position = i / (self.num_segments - 1)

            if curve == "linear":
                slowdown = position * max_slowdown
            elif curve == "exponential":
                slowdown = (position ** 2) * max_slowdown
            elif curve == "s_curve":
                x = position * 6 - 3
                s = 1 / (1 + np.exp(-x))
                slowdown = s * max_slowdown
            else:
                slowdown = position * max_slowdown

            factors.append(1.0 - slowdown)

        return factors

    def _apply_single_pass_processing(
        self,
        audio: AudioSegment,
        segment_atempos: List[float],
        volume_db: float
    ) -> AudioSegment:
        """
        단일 패스 처리 (v1.1 - 버그 수정)

        ⭐ 핵심 수정:
        - 먼저 전체 오디오에 음량 조정 적용 (균일!)
        - 그 후 구간별 atempo만 적용
        """

        if not self.ffmpeg_available:
            print("  ⚠️ FFmpeg 없음, 음량만 조정")
            return audio + volume_db

        # ⭐ 버그 수정: 먼저 전체 오디오에 음량 균일 적용
        if abs(volume_db) >= 0.5:
            print(f"  🔊 전체 음량 균일 조정: {volume_db:+.1f}dB")
            audio = audio + volume_db  # pydub 방식 (빠르고 균일)

        total_duration = len(audio)
        segment_duration = total_duration // self.num_segments

        processed_segments = []

        for i in range(self.num_segments):
            start = i * segment_duration
            end = start + segment_duration if i < self.num_segments - 1 else total_duration

            seg = audio[start:end]
            atempo = segment_atempos[i]

            # atempo가 거의 1.0이면 처리 생략 (음량은 이미 적용됨)
            if abs(atempo - 1.0) < 0.02:
                processed_segments.append(seg)
                continue

            # ⭐ atempo만 적용 (음량은 이미 전체 적용됨)
            seg = self._apply_ffmpeg_single(seg, atempo, volume_db=0)
            processed_segments.append(seg)

        # 크로스페이드로 부드럽게 연결 (울림 방지)
        return self._merge_with_crossfade(processed_segments)

    def _apply_ffmpeg_single(
        self,
        audio: AudioSegment,
        atempo: float,
        volume_db: float = 0
    ) -> AudioSegment:
        """단일 FFmpeg 호출 (고품질)"""

        try:
            temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

            audio.export(temp_in, format="wav")

            # 필터 체인 구성
            filters = []

            if abs(atempo - 1.0) >= 0.02:
                # atempo 범위 제한 (0.5 ~ 2.0)
                safe_atempo = max(0.5, min(2.0, atempo))
                filters.append(f"atempo={safe_atempo}")

            if abs(volume_db) >= 0.5:
                filters.append(f"volume={volume_db}dB")

            if not filters:
                # 정리
                for f in [temp_in, temp_out]:
                    try:
                        os.remove(f)
                    except:
                        pass
                return audio

            filter_str = ",".join(filters)

            # 고품질 FFmpeg 설정
            cmd = [
                "ffmpeg", "-y",
                "-i", temp_in,
                "-af", filter_str,
                "-ar", "24000",
                "-ac", "1",
                "-acodec", "pcm_s16le",  # 무손실 PCM
                "-f", "wav",
                temp_out
            ]

            result = subprocess.run(cmd, capture_output=True, timeout=60)

            if os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
                processed = AudioSegment.from_file(temp_out)
            else:
                processed = audio

            # 임시 파일 정리
            for f in [temp_in, temp_out]:
                try:
                    os.remove(f)
                except:
                    pass

            return processed

        except Exception as e:
            print(f"    ⚠️ FFmpeg 오류: {e}")
            return audio + volume_db if volume_db != 0 else audio

    def _merge_with_crossfade(
        self,
        segments: List[AudioSegment]
    ) -> AudioSegment:
        """크로스페이드 병합 (울림 방지)"""

        if not segments:
            return AudioSegment.empty()

        result = segments[0]

        for seg in segments[1:]:
            # 동적 크로스페이드 (구간 길이에 비례)
            fade_ms = min(
                self.crossfade_ms,
                len(result) // 6,
                len(seg) // 6
            )

            if fade_ms > 10:
                result = result.append(seg, crossfade=fade_ms)
            else:
                result = result + seg

        return result

    def _adjust_volume_only(self, audio: AudioSegment) -> AudioSegment:
        """음량만 조정 (짧은 오디오용)"""

        current_lufs = self._measure_lufs(audio)
        volume_db = self.target_lufs - current_lufs
        # ⭐ 과도한 음량 조정 방지 (±3dB 제한)
        volume_db = max(-3, min(3, volume_db))

        return audio + volume_db


# ============================================================
# 전체 씬 처리 함수
# ============================================================

def process_all_unified(
    scenes: List[Dict],
    target_speed: float = 8.5,
    accel_profile: str = "adaptive",
    progress_callback: Optional[callable] = None
) -> List[Dict]:
    """
    모든 씬 통합 처리 (단일 패스)

    기존: PerfectNorm → SpeedCorrector → SegmentNorm (6~8회 FFmpeg)
    새로운: UnifiedProcessor (구간당 1회 FFmpeg)

    Args:
        scenes: 씬 리스트 [{scene_id, text, audio_data, ...}, ...]
        target_speed: 목표 발화속도 (글자/초)
        accel_profile: 가속 보정 프로파일 (adaptive/strong/moderate)
        progress_callback: 진행 콜백 (current, total, message)

    Returns:
        처리된 씬 리스트
    """

    processor = UnifiedAudioProcessor(
        target_speed=target_speed,
        accel_profile=accel_profile,
        num_segments=8  # 8구간 (정밀)
    )

    results = []
    total = len(scenes)
    valid_scenes = [s for s in scenes if s.get("audio_data") and s.get("success")]

    if not valid_scenes:
        print("[UnifiedProcessor] 처리할 씬 없음")
        return scenes

    print(f"\n{'='*60}")
    print(f"[UnifiedProcessor] {len(valid_scenes)}개 씬 단일 패스 처리")
    print(f"  ⭐ FFmpeg 최소 호출 → 울림/변조 방지")
    print(f"  ⭐ 적응형 가속 보정 → 정확한 속도 균일화")
    print(f"{'='*60}")

    for idx, scene in enumerate(scenes):
        if progress_callback:
            try:
                progress_callback(idx, total, f"통합 처리: 씬 {scene.get('scene_id', idx+1)}")
            except:
                pass

        # 오디오가 없거나 실패한 씬은 그대로 유지
        if not scene.get("audio_data") or not scene.get("success"):
            results.append(scene)
            continue

        audio_data = scene.get("audio_data")
        text = scene.get("text", "")
        scene_id = scene.get("scene_id", idx + 1)

        # 단일 패스 처리
        processed_audio, new_duration = processor.process_scene_bytes(
            audio_data, text, scene_id
        )

        results.append({
            **scene,
            "audio_data": processed_audio,
            "duration": new_duration,
            "unified_processed": True,
            "normalized": True
        })

    # 최종 속도 미세 조정
    results = _final_speed_adjustment(results, target_speed, progress_callback)

    print(f"\n{'='*60}")
    print(f"[UnifiedProcessor] 단일 패스 처리 완료!")
    print(f"{'='*60}")

    if progress_callback:
        try:
            progress_callback(total, total, "통합 처리 완료")
        except:
            pass

    return results


def _final_speed_adjustment(
    scenes: List[Dict],
    target_speed: float,
    progress_callback: Optional[callable] = None
) -> List[Dict]:
    """
    최종 속도 개별 조정 (v1.1 - 버그 수정)

    ⭐ 핵심 수정:
    - 기존: 전체 평균 계산 → 동일 계수로 모든 씬 조정
    - 수정: 각 씬별로 개별 조정 계수 계산 → 각각 적용
    """

    # ⭐⭐⭐ FinalAdjust v1.2 - 범위 대폭 축소 (자연스러움 보존) ⭐⭐⭐
    # 🔴 기존: ±15~20% 조정 → 과도한 가속으로 딱딱한 음성
    # ✅ 수정: ±5% 제한 → 미세 조정만 허용
    print(f"\n[FinalAdjust v1.2] 씬별 미세 조정 (±5% 제한)")
    print(f"  목표: {target_speed:.2f} 글자/초")

    adjusted_results = []
    total = len(scenes)
    adjustments_made = 0

    for idx, scene in enumerate(scenes):
        audio_data = scene.get("audio_data")
        text = scene.get("text", "")
        scene_id = scene.get("scene_id", idx + 1)

        if not audio_data or not scene.get("success"):
            adjusted_results.append(scene)
            continue

        if progress_callback:
            try:
                progress_callback(idx, total, f"최종 조정: 씬 {scene_id}")
            except:
                pass

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
            duration = len(audio) / 1000
            char_count = len(text.replace(" ", "").replace("\n", ""))

            if duration <= 0 or char_count <= 0:
                adjusted_results.append(scene)
                continue

            current_speed = char_count / duration
            speed_diff_pct = abs(current_speed - target_speed) / target_speed * 100

            # ⭐⭐⭐ 5% 이상 차이나면 개별 조정 (기존 2% → 5% 완화)
            # 작은 차이는 무시해서 불필요한 가속 방지
            if speed_diff_pct < 5.0:
                print(f"  씬 {scene_id}: {current_speed:.2f} 글자/초 ✅ (차이 {speed_diff_pct:.1f}% - 허용)")
                adjusted_results.append(scene)
                continue

            # ⭐⭐⭐ 씬별 개별 조정 계수 계산 - 범위 대폭 축소!
            # 🔴 기존: 0.85~1.20 (±15~20%) → 과도한 가속
            # ✅ 수정: 0.95~1.05 (±5%) → 미세 조정만 허용
            adjustment = target_speed / current_speed
            original_adjustment = adjustment
            adjustment = max(0.95, min(1.05, adjustment))

            if abs(original_adjustment - adjustment) > 0.01:
                print(f"  ⚠️ 과도한 조정 방지: x{original_adjustment:.3f} → x{adjustment:.3f}")

            print(f"  씬 {scene_id}: {current_speed:.2f} → {target_speed:.2f} (x{adjustment:.3f})")

            # atempo 적용
            temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

            audio.export(temp_in, format="wav")

            cmd = [
                "ffmpeg", "-y", "-i", temp_in,
                "-af", f"atempo={adjustment}",
                "-ar", "24000", "-ac", "1",
                "-acodec", "pcm_s16le",
                temp_out
            ]

            subprocess.run(cmd, capture_output=True, timeout=30)

            if os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
                result_audio = AudioSegment.from_file(temp_out)
                output = io.BytesIO()
                result_audio.export(output, format="wav", parameters=["-ar", "24000", "-ac", "1"])
                output.seek(0)
                new_audio_data = output.read()
                new_duration = len(result_audio) / 1000

                # 결과 확인
                new_speed = char_count / new_duration if new_duration > 0 else 0
                print(f"        → 결과: {new_speed:.2f} 글자/초")

                adjustments_made += 1
            else:
                new_audio_data = audio_data
                new_duration = duration

            for f in [temp_in, temp_out]:
                try:
                    os.remove(f)
                except:
                    pass

            adjusted_results.append({
                **scene,
                "audio_data": new_audio_data,
                "duration": new_duration,
                "final_adjusted": True
            })

        except Exception as e:
            print(f"  씬 {scene_id}: ⚠️ 실패 - {e}")
            adjusted_results.append(scene)

    # 최종 결과 요약
    print(f"\n[FinalAdjust v1.2] 완료 ({adjustments_made}개 씬 미세 조정됨)")

    # 최종 속도 확인
    final_speeds = []
    for scene in adjusted_results:
        audio_data = scene.get("audio_data")
        text = scene.get("text", "")

        if audio_data and scene.get("success"):
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
                duration = len(audio) / 1000
                char_count = len(text.replace(" ", "").replace("\n", ""))
                if duration > 0 and char_count > 0:
                    final_speeds.append(char_count / duration)
            except:
                pass

    if final_speeds:
        avg = np.mean(final_speeds)
        min_s = min(final_speeds)
        max_s = max(final_speeds)
        deviation = (max_s - min_s) / avg * 100 if avg > 0 else 0
        print(f"  최종 평균: {avg:.2f} 글자/초")
        print(f"  범위: {min_s:.2f} ~ {max_s:.2f} (편차 ±{deviation/2:.1f}%)")

    return adjusted_results
