# -*- coding: utf-8 -*-
"""
강제 오디오 정규화 모듈

핵심 목표:
- 정규화가 반드시 실행되도록 보장
- 발화속도 편차: ±5% 이내 (8.075 ~ 8.925 글자/초)
- 음량 편차: ±2dB 이내
"""

import os
import io
import tempfile
import subprocess
from typing import List, Dict, Tuple, Optional, Callable
import numpy as np

try:
    from pydub import AudioSegment
    from pydub.effects import normalize as pydub_normalize
    from pydub.silence import detect_leading_silence
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("[ForcedNormalizer] ⚠️ pydub 미설치")


def _check_ffmpeg() -> bool:
    """FFmpeg 설치 확인"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


class ForcedAudioNormalizer:
    """
    강제 오디오 정규화 클래스

    기존 AudioNormalizer와 달리 조건 없이 항상 실행됨
    """

    def __init__(
        self,
        target_rate: float = 8.5,
        target_dbfs: float = -20.0,
        max_speed_adjust: float = 0.15,
        silence_ms: Tuple[int, int] = (80, 80)
    ):
        """
        Args:
            target_rate: 목표 발화속도 (글자/초)
            target_dbfs: 목표 음량 (dBFS)
            max_speed_adjust: 최대 속도 조정 비율 (0.15 = ±15%)
            silence_ms: (앞 무음, 뒤 무음) 밀리초
        """
        self.target_rate = target_rate
        self.target_dbfs = target_dbfs
        self.max_speed_adjust = max_speed_adjust
        self.silence_ms = silence_ms
        self.ffmpeg_available = _check_ffmpeg()

        print(f"\n{'='*60}")
        print("[ForcedNormalizer] 초기화")
        print(f"  목표 발화속도: {target_rate} 글자/초 (±5% = {target_rate*0.95:.2f} ~ {target_rate*1.05:.2f})")
        print(f"  목표 음량: {target_dbfs} dBFS")
        print(f"  FFmpeg: {'✅ 사용 가능' if self.ffmpeg_available else '❌ 미설치'}")
        print(f"{'='*60}\n")

    def normalize_all_scenes(
        self,
        scenes: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """
        모든 씬 강제 정규화

        Args:
            scenes: 씬 리스트 (audio_data 필수)
            progress_callback: (current, total, message) 콜백

        Returns:
            정규화된 씬 리스트
        """

        if not PYDUB_AVAILABLE:
            print("[ForcedNormalizer] ❌ pydub 미설치 - 정규화 불가")
            return scenes

        print("\n" + "=" * 60)
        print("[ForcedNormalizer] 🔧 강제 정규화 시작")
        print("=" * 60)

        # 1단계: 분석
        print("\n[Step 1/4] 📊 씬 분석")
        analysis = self._analyze_all(scenes)

        if not analysis:
            print("[ForcedNormalizer] ⚠️ 분석할 씬 없음")
            return scenes

        self._print_analysis_summary(analysis, "정규화 전")

        # 2단계: 개별 정규화
        print("\n[Step 2/4] 🔄 개별 씬 정규화")
        normalized = self._normalize_each(analysis, progress_callback)

        # 3단계: 결과 검증
        print("\n[Step 3/4] ✅ 결과 검증")
        self._verify_results(normalized)

        # 4단계: 원본에 반영
        print("\n[Step 4/4] 💾 결과 반영")
        result_map = {n["scene_id"]: n for n in normalized}

        for scene in scenes:
            scene_id = scene.get("scene_id")
            if scene_id in result_map:
                norm = result_map[scene_id]
                scene["audio_data"] = norm.get("audio_data", scene.get("audio_data"))
                scene["final_duration"] = norm.get("final_duration")
                scene["final_rate"] = norm.get("final_rate")
                scene["final_dbfs"] = norm.get("final_dbfs")
                scene["speed_ratio"] = norm.get("speed_ratio", 1.0)
                scene["volume_change"] = norm.get("volume_change", 0)
                scene["normalized"] = True
                scene["normalizer_version"] = "forced_v1"

        print("\n" + "=" * 60)
        print("[ForcedNormalizer] ✅ 강제 정규화 완료")
        print("=" * 60 + "\n")

        return scenes

    def _analyze_all(self, scenes: List[Dict]) -> List[Dict]:
        """모든 씬 분석"""

        analysis = []

        for scene in scenes:
            audio_data = scene.get("audio_data")
            if not audio_data:
                continue

            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
                duration = len(audio) / 1000

                text = scene.get("text", "")
                # 공백과 줄바꿈 제거하고 글자 수 계산
                char_count = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))

                if duration <= 0 or char_count == 0:
                    continue

                rate = char_count / duration
                dbfs = audio.dBFS if audio.dBFS != float('-inf') else -60

                analysis.append({
                    **scene,
                    "audio": audio,
                    "original_duration": duration,
                    "char_count": char_count,
                    "original_rate": rate,
                    "original_dbfs": dbfs
                })

                print(f"  씬 {scene['scene_id']:02d}: {rate:.2f} 글자/초, {dbfs:.1f} dBFS, {duration:.2f}초, {char_count}자")

            except Exception as e:
                print(f"  씬 {scene.get('scene_id', '?')}: ❌ 분석 실패 - {e}")

        return analysis

    def _print_analysis_summary(self, analysis: List[Dict], label: str):
        """분석 요약 출력"""

        rates = [a["original_rate"] for a in analysis]
        dbfs_values = [a["original_dbfs"] for a in analysis]

        rate_min, rate_max = min(rates), max(rates)
        rate_mean = np.mean(rates)
        rate_deviation = (rate_max - rate_min) / 2 / rate_mean * 100 if rate_mean > 0 else 0

        dbfs_min, dbfs_max = min(dbfs_values), max(dbfs_values)
        dbfs_range = dbfs_max - dbfs_min

        print(f"\n  📊 {label} 통계:")
        print(f"     발화속도: {rate_min:.2f} ~ {rate_max:.2f} 글자/초 (편차 ±{rate_deviation:.1f}%)")
        print(f"     음량: {dbfs_min:.1f} ~ {dbfs_max:.1f} dBFS (범위 {dbfs_range:.1f}dB)")

    def _normalize_each(
        self,
        analysis: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """각 씬 정규화"""

        results = []
        total = len(analysis)

        for idx, item in enumerate(analysis):
            scene_id = item["scene_id"]

            if progress_callback:
                progress_callback(idx, total, f"씬 {scene_id} 정규화 중...")

            print(f"\n  [씬 {scene_id:02d}] 정규화 시작")

            audio = item["audio"]
            current_rate = item["original_rate"]
            char_count = item["char_count"]

            speed_ratio = 1.0
            volume_change = 0.0

            # 1. 속도 조정 (발화속도 일관성)
            audio, speed_ratio = self._adjust_speed_forced(
                audio, current_rate, self.target_rate
            )

            # 2. 무음 표준화
            audio = self._standardize_silence(audio)

            # 3. 음량 정규화
            audio, volume_change = self._normalize_volume(audio)

            # 4. 피크 제한
            audio = pydub_normalize(audio, headroom=1.0)

            # 최종 분석
            final_duration = len(audio) / 1000
            final_rate = char_count / final_duration if final_duration > 0 else 0
            final_dbfs = audio.dBFS if audio.dBFS != float('-inf') else -60

            print(f"     → {final_rate:.2f} 글자/초, {final_dbfs:.1f} dBFS")

            # 바이트 변환
            output = io.BytesIO()
            audio.export(output, format="wav")
            output.seek(0)

            results.append({
                **item,
                "audio_data": output.read(),
                "audio": None,
                "final_duration": final_duration,
                "final_rate": final_rate,
                "final_dbfs": final_dbfs,
                "speed_ratio": speed_ratio,
                "volume_change": volume_change
            })

        if progress_callback:
            progress_callback(total, total, "정규화 완료")

        return results

    def _adjust_speed_forced(
        self,
        audio: AudioSegment,
        current_rate: float,
        target_rate: float
    ) -> Tuple[AudioSegment, float]:
        """속도 강제 조정 (FFmpeg atempo) - 방향 수정됨!"""

        # ⭐ 핵심 수정: atempo 계산 방향!
        # atempo = target / current
        # - current < target (너무 느림) → atempo > 1 → 오디오 빠르게 재생 → 발화속도 증가
        # - current > target (너무 빠름) → atempo < 1 → 오디오 느리게 재생 → 발화속도 감소
        #
        # 예시: current=7.47, target=8.5
        #   atempo = 8.5 / 7.47 = 1.138
        #   오디오를 1.138배 빠르게 재생 → 발화속도 7.47 * 1.138 = 8.5 글자/초
        atempo = target_rate / current_rate

        # 범위 제한 (0.85 ~ 1.20, 즉 ±15~20% 조정)
        atempo = max(0.85, min(1.20, atempo))

        deviation_pct = abs(atempo - 1.0) * 100

        # 3% 미만 차이는 무시 (거의 목표에 도달)
        if deviation_pct < 3.0:
            print(f"     속도: 조정 불필요 (차이 {deviation_pct:.1f}%)")
            return audio, 1.0

        # 방향 표시
        direction = "⬆️ 빠르게" if atempo > 1.0 else "⬇️ 느리게"
        expected_rate = current_rate * atempo
        print(f"     속도: {atempo:.3f}x ({direction})")
        print(f"            {current_rate:.2f} → {expected_rate:.2f} 글자/초 (목표: {target_rate:.2f})")

        if not self.ffmpeg_available:
            print(f"     ⚠️ FFmpeg 미설치 - 속도 조정 스킵")
            return audio, 1.0

        try:
            # 임시 파일
            temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

            audio.export(temp_in, format="wav")

            # atempo 범위: 0.5 ~ 2.0 (이미 0.85~1.20으로 제한됨)
            atempo_value = max(0.5, min(2.0, atempo))

            cmd = [
                "ffmpeg", "-y", "-i", temp_in,
                "-af", f"atempo={atempo_value}",
                "-ar", "24000",
                "-ac", "1",
                temp_out
            ]

            # Windows에서 콘솔 창 숨김
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                creationflags=creationflags,
                timeout=30
            )

            result = AudioSegment.from_file(temp_out, format="wav")

            # 정리
            for f in [temp_in, temp_out]:
                try:
                    os.remove(f)
                except:
                    pass

            return result, atempo

        except subprocess.TimeoutExpired:
            print(f"     ⚠️ FFmpeg 타임아웃")
            return audio, 1.0
        except Exception as e:
            print(f"     ⚠️ 속도 조정 실패: {e}")
            return audio, 1.0

    def _standardize_silence(self, audio: AudioSegment) -> AudioSegment:
        """무음 표준화"""

        try:
            # 앞쪽 무음 감지
            start_trim = detect_leading_silence(audio, silence_threshold=-50)
            start_trim = min(start_trim, 500)

            # 뒤쪽 무음 감지
            end_trim = detect_leading_silence(audio.reverse(), silence_threshold=-50)
            end_trim = min(end_trim, 500)

            # 트리밍
            if start_trim + end_trim < len(audio) - 100:
                audio = audio[start_trim:len(audio) - end_trim]

            # 표준 무음 추가
            leading = AudioSegment.silent(duration=self.silence_ms[0], frame_rate=audio.frame_rate)
            trailing = AudioSegment.silent(duration=self.silence_ms[1], frame_rate=audio.frame_rate)

            return leading + audio + trailing

        except Exception as e:
            print(f"     ⚠️ 무음 표준화 실패: {e}")
            return audio

    def _normalize_volume(self, audio: AudioSegment) -> Tuple[AudioSegment, float]:
        """음량 정규화"""

        current_dbfs = audio.dBFS

        if current_dbfs == float('-inf'):
            return audio, 0.0

        change = self.target_dbfs - current_dbfs

        # 최대 ±15dB 제한
        change = max(-15, min(15, change))

        if abs(change) > 0.5:
            audio = audio.apply_gain(change)
            print(f"     음량: {change:+.1f} dB ({current_dbfs:.1f} → {audio.dBFS:.1f} dBFS)")

        return audio, change

    def _verify_results(self, results: List[Dict]):
        """결과 검증"""

        rates = [r["final_rate"] for r in results if r.get("final_rate")]
        dbfs_values = [r["final_dbfs"] for r in results if r.get("final_dbfs")]

        if rates:
            rate_min, rate_max = min(rates), max(rates)
            rate_mean = np.mean(rates)
            rate_deviation = (rate_max - rate_min) / 2 / rate_mean * 100 if rate_mean > 0 else 0

            print(f"\n  📊 발화속도 결과:")
            print(f"     범위: {rate_min:.2f} ~ {rate_max:.2f} 글자/초")
            print(f"     평균: {rate_mean:.2f} 글자/초")
            print(f"     편차: ±{rate_deviation:.1f}%")

            if rate_deviation <= 5:
                print(f"     ✅ 목표 달성! (±5% 이내)")
            elif rate_deviation <= 8:
                print(f"     ⚠️ 양호 (±8% 이내)")
            else:
                print(f"     ❌ 추가 조정 필요 (±{rate_deviation:.1f}%)")

        if dbfs_values:
            dbfs_min, dbfs_max = min(dbfs_values), max(dbfs_values)
            dbfs_range = dbfs_max - dbfs_min

            print(f"\n  📊 음량 결과:")
            print(f"     범위: {dbfs_min:.1f} ~ {dbfs_max:.1f} dBFS")
            print(f"     편차: {dbfs_range:.1f} dB")

            if dbfs_range <= 4:
                print(f"     ✅ 목표 달성! (±2dB 이내)")
            else:
                print(f"     ⚠️ 추가 조정 필요")


# ============================================================
# 편의 함수
# ============================================================

def normalize_scenes_forced(
    scenes: List[Dict],
    target_rate: float = 8.5,
    target_dbfs: float = -20.0,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    강제 정규화 편의 함수

    Args:
        scenes: 씬 리스트
        target_rate: 목표 발화속도 (기본 8.5 글자/초)
        target_dbfs: 목표 음량 (기본 -20 dBFS)
        progress_callback: 진행 콜백

    Returns:
        정규화된 씬 리스트
    """

    normalizer = ForcedAudioNormalizer(
        target_rate=target_rate,
        target_dbfs=target_dbfs
    )

    return normalizer.normalize_all_scenes(scenes, progress_callback)


def analyze_normalization_stats(scenes: List[Dict]) -> Dict:
    """
    정규화 상태 분석

    Args:
        scenes: 씬 리스트

    Returns:
        통계 정보
    """

    if not PYDUB_AVAILABLE:
        return {"error": "pydub not installed"}

    rates = []
    dbfs_values = []
    durations = []

    for scene in scenes:
        audio_data = scene.get("audio_data")
        if not audio_data:
            continue

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
            duration = len(audio) / 1000

            text = scene.get("text", "")
            char_count = len(text.replace(" ", "").replace("\n", ""))

            if duration > 0 and char_count > 0:
                rate = char_count / duration
                dbfs = audio.dBFS if audio.dBFS != float('-inf') else -60

                rates.append(rate)
                dbfs_values.append(dbfs)
                durations.append(duration)
        except:
            pass

    if not rates:
        return {"error": "no valid scenes"}

    rate_mean = np.mean(rates)
    rate_deviation = (max(rates) - min(rates)) / 2 / rate_mean * 100 if rate_mean > 0 else 0

    return {
        "scene_count": len(rates),
        "rate_min": min(rates),
        "rate_max": max(rates),
        "rate_mean": rate_mean,
        "rate_std": np.std(rates),
        "rate_deviation_pct": rate_deviation,
        "dbfs_min": min(dbfs_values),
        "dbfs_max": max(dbfs_values),
        "dbfs_range": max(dbfs_values) - min(dbfs_values),
        "total_duration": sum(durations),
        "needs_normalization": rate_deviation > 5 or (max(dbfs_values) - min(dbfs_values)) > 4
    }
