# -*- coding: utf-8 -*-
"""
HybridSRTGenerator v5.6 - WhisperV3 연동 버전 (VAD 극단적 민감도)

⭐ 핵심 기능:
1. WhisperTimestampV3 사용 (정확도 최적화)
2. 오디오 전처리 자동 적용
3. 갭 자동 감지 및 재분석
4. 원문 기반 검증
5. 기존 tts_to_srt_hybrid.py와 호환

사용법:
    from utils.hybrid_srt_generator import HybridSRTGenerator

    generator = HybridSRTGenerator(whisper_model="small")
    result = generator.process(audio_path, original_script, style="잘게")
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

# WhisperV3 및 오디오 전처리
from utils.whisper_timestamp import (
    WhisperTimestampV3,
    WhisperConfigV3,
    WhisperResult,
    create_optimized_whisper
)
from utils.audio_preprocessor import (
    AudioPreprocessor,
    preprocess_audio_for_whisper,
    analyze_audio_for_whisper
)
from utils.srt_validator import (
    SRTValidator,
    get_srt_validator
)


@dataclass
class HybridSceneV55:
    """HybridV5.5 씬"""
    scene_id: int
    text: str
    start_time: float
    end_time: float
    duration: float
    timecode: str
    is_recovered: bool = False  # 갭 복구 여부

    @property
    def char_count(self) -> int:
        return len(self.text)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class HybridResultV55:
    """HybridV5.5 결과"""
    scenes: List[HybridSceneV55]
    audio_duration: float
    whisper_segments: int
    recovered_segments: int
    gaps_found: int
    audio_was_enhanced: bool
    success: bool
    error: str = ""

    @property
    def scene_count(self) -> int:
        return len(self.scenes)

    def to_srt(self) -> str:
        """SRT 형식 문자열 생성"""
        srt_blocks = []
        for i, scene in enumerate(self.scenes):
            start_tc = self._format_timecode(scene.start_time)
            end_tc = self._format_timecode(scene.end_time)
            srt_blocks.append(f"{i + 1}\n{start_tc} --> {end_tc}\n{scene.text}\n")
        return "\n".join(srt_blocks)

    def _format_timecode(self, seconds: float) -> str:
        """초를 SRT 타임코드로 변환"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        whole_secs = int(secs)
        millis = int((secs - whole_secs) * 1000)
        return f"{hours:02d}:{minutes:02d}:{whole_secs:02d},{millis:03d}"


class HybridSRTGenerator:
    """
    HybridV5.5 SRT 생성기 - WhisperV3 연동

    ⭐ 개선사항:
    1. WhisperTimestampV3 사용 (VAD 최적화)
    2. 오디오 전처리 자동 적용
    3. 갭 자동 감지 및 재분석
    4. 원문 기반 검증
    """

    def __init__(
        self,
        whisper_model: str = "small",
        vad_threshold: float = 0.05,
        min_speech_duration_ms: int = 30,
        reanalyze_gaps: bool = True,
        auto_enhance_audio: bool = True
    ):
        """
        초기화 (v5.6 - 극단적 VAD 민감도)

        Args:
            whisper_model: Whisper 모델 크기 (small 권장)
            vad_threshold: VAD 임계값 (0.05 권장, 극도로 민감)
            min_speech_duration_ms: 최소 음성 길이 (30ms 권장)
            reanalyze_gaps: 갭 자동 재분석 여부
            auto_enhance_audio: 저볼륨 구간 자동 향상 여부
        """
        # WhisperV3 설정
        self.whisper_config = WhisperConfigV3(
            model_size=whisper_model,
            vad_threshold=vad_threshold,
            min_speech_duration_ms=min_speech_duration_ms,
            word_timestamps=True,
            reanalyze_gaps=reanalyze_gaps
        )

        self.whisper = WhisperTimestampV3(self.whisper_config)
        self.audio_preprocessor = AudioPreprocessor()
        self.srt_validator = get_srt_validator()

        self.auto_enhance_audio = auto_enhance_audio

        print(f"\n{'='*60}")
        print(f"[HybridV5.6] 초기화 완료 (극단적 VAD 민감도)")
        print(f"{'='*60}")
        print(f"  Whisper 모델: {whisper_model}")
        print(f"  VAD threshold: {vad_threshold} (극도로 민감)")
        print(f"  min_speech: {min_speech_duration_ms}ms")
        print(f"  갭 재분석: {reanalyze_gaps}")
        print(f"  오디오 향상: {auto_enhance_audio}")
        print(f"{'='*60}")

    def process(
        self,
        audio_path: str,
        original_script: str = None,
        style: str = "잘게",
        language: str = "ko"
    ) -> HybridResultV55:
        """
        HybridV5.5 파이프라인

        Args:
            audio_path: 오디오 파일 경로
            original_script: 원문 스크립트 (갭 복구/검증용)
            style: 분리 스타일 (잘게, 기본, 크게)
            language: 언어 코드

        Returns:
            HybridResultV55 결과 객체
        """
        try:
            print(f"\n{'='*60}")
            print(f"[HybridV5.6] 파이프라인 시작")
            print(f"{'='*60}")
            print(f"  오디오: {Path(audio_path).name}")
            print(f"  스타일: {style}")

            # Step 0: 오디오 분석 및 전처리
            audio_was_enhanced = False
            analysis_audio = audio_path

            if self.auto_enhance_audio:
                print(f"\n📍 Step 0: 오디오 분석 및 전처리")
                analysis = analyze_audio_for_whisper(audio_path)

                audio_duration = analysis['info']['duration']
                print(f"  오디오 길이: {audio_duration:.1f}초 ({audio_duration/60:.1f}분)")
                print(f"  볼륨: {analysis['info']['volume_db']:.1f}dB")

                if analysis['has_potential_issues']:
                    low_gaps = analysis['low_volume_gaps']
                    print(f"  ⚠️ 저볼륨 구간: {len(low_gaps)}개 발견")
                    for gap in low_gaps:
                        print(f"    {gap[0]:.1f}초 ~ {gap[1]:.1f}초")

                    print(f"  🔊 오디오 향상 처리 중...")
                    enhanced_path = self.audio_preprocessor.normalize_and_enhance(audio_path)
                    analysis_audio = enhanced_path
                    audio_was_enhanced = True
                    print(f"  ✅ 향상 완료: {enhanced_path}")
                else:
                    print(f"  ✅ 오디오 상태 양호")
            else:
                audio_duration = self.audio_preprocessor.get_audio_duration(audio_path)

            # Step 1: WhisperV3 100% 커버리지 분석
            print(f"\n📍 Step 1: WhisperV3 100% 커버리지 분석")
            whisper_result = self.whisper.transcribe_with_full_coverage(
                analysis_audio,
                language=language,
                original_script=original_script
            )

            segments = whisper_result.get('segments', [])
            audio_duration = whisper_result.get('duration', audio_duration)
            coverage_percent = whisper_result.get('coverage_percent', 0)
            gaps_recovered = whisper_result.get('gaps_recovered', 0)

            whisper_segments = len(segments)
            recovered_count = sum(1 for s in segments if s.get('_recovered', False))

            print(f"  분석 완료: {whisper_segments}개 세그먼트")
            print(f"  커버리지: {coverage_percent:.1f}%")
            if recovered_count > 0:
                print(f"  복구된 세그먼트: {recovered_count}개")

            # Step 2: SRT 검증 및 수정
            print(f"\n📍 Step 2: SRT 검증")

            validated_scenes, fixes = self.srt_validator.validate_and_fix(
                segments,
                total_duration=audio_duration,
                original_script=original_script,
                audio_duration=audio_duration
            )

            gaps_found = sum(1 for f in fixes if f.get('type') == 'gap_recovered')

            print(f"  검증 완료: {len(validated_scenes)}개 씬")
            if fixes:
                print(f"  수정사항: {len(fixes)}개")

            # Step 3: 결과 변환
            print(f"\n📍 Step 3: 결과 변환")

            scenes = []
            for i, scene in enumerate(validated_scenes):
                start_sec = scene.get('_start_seconds', 0)
                end_sec = scene.get('_end_seconds', 0)

                # 타임코드 생성
                start_tc = self._format_timecode(start_sec)
                end_tc = self._format_timecode(end_sec)
                timecode = f"{start_tc} --> {end_tc}"

                scenes.append(HybridSceneV55(
                    scene_id=i + 1,
                    text=scene.get('text', ''),
                    start_time=start_sec,
                    end_time=end_sec,
                    duration=end_sec - start_sec,
                    timecode=timecode,
                    is_recovered=scene.get('_recovered', False)
                ))

            print(f"  최종 씬: {len(scenes)}개")

            # 결과 생성
            result = HybridResultV55(
                scenes=scenes,
                audio_duration=audio_duration,
                whisper_segments=whisper_segments,
                recovered_segments=recovered_count,
                gaps_found=gaps_found,
                audio_was_enhanced=audio_was_enhanced,
                success=True
            )

            print(f"\n{'='*60}")
            print(f"[HybridV5.6] ✅ 파이프라인 완료")
            print(f"{'='*60}")
            print(f"  총 씬: {result.scene_count}개")
            print(f"  복구 씬: {recovered_count}개")
            print(f"  오디오 향상: {'예' if audio_was_enhanced else '아니오'}")
            print(f"{'='*60}")

            return result

        except Exception as e:
            print(f"\n[HybridV5.6] ❌ 오류: {e}")
            import traceback
            traceback.print_exc()

            return HybridResultV55(
                scenes=[],
                audio_duration=0,
                whisper_segments=0,
                recovered_segments=0,
                gaps_found=0,
                audio_was_enhanced=False,
                success=False,
                error=str(e)
            )

    def _format_timecode(self, seconds: float) -> str:
        """초를 SRT 타임코드로 변환"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        whole_secs = int(secs)
        millis = int((secs - whole_secs) * 1000)
        return f"{hours:02d}:{minutes:02d}:{whole_secs:02d},{millis:03d}"

    def save_srt(self, result: HybridResultV55, output_path: str) -> str:
        """
        결과를 SRT 파일로 저장

        Args:
            result: HybridResultV55 결과
            output_path: 출력 파일 경로

        Returns:
            저장된 파일 경로
        """
        srt_content = result.to_srt()

        # 디렉토리 생성
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)

        print(f"[HybridV5.6] SRT 저장: {output_path}")
        return output_path


# ============================================================
# 팩토리 함수
# ============================================================

def get_hybrid_generator(
    whisper_model: str = "small",
    vad_threshold: float = 0.05,
    min_speech_duration_ms: int = 30,
    reanalyze_gaps: bool = True,
    auto_enhance_audio: bool = True
) -> HybridSRTGenerator:
    """
    HybridSRTGenerator 인스턴스 생성 (v5.6)

    Args:
        whisper_model: Whisper 모델 크기
        vad_threshold: VAD 임계값 (0.05 권장)
        min_speech_duration_ms: 최소 음성 길이 (30ms 권장)
        reanalyze_gaps: 갭 재분석 여부
        auto_enhance_audio: 오디오 향상 여부

    Returns:
        HybridSRTGenerator 인스턴스
    """
    return HybridSRTGenerator(
        whisper_model=whisper_model,
        vad_threshold=vad_threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        reanalyze_gaps=reanalyze_gaps,
        auto_enhance_audio=auto_enhance_audio
    )


def process_audio_to_srt(
    audio_path: str,
    output_path: str = None,
    original_script: str = None,
    style: str = "잘게",
    whisper_model: str = "small"
) -> Tuple[HybridResultV55, str]:
    """
    오디오를 SRT로 변환 (원스톱 함수)

    Args:
        audio_path: 오디오 파일 경로
        output_path: 출력 SRT 경로 (없으면 자동 생성)
        original_script: 원문 스크립트
        style: 분리 스타일
        whisper_model: Whisper 모델 크기

    Returns:
        (HybridResultV55, SRT 파일 경로)
    """
    # 출력 경로 자동 생성
    if output_path is None:
        base = Path(audio_path)
        output_path = str(base.parent / f"{base.stem}_v55.srt")

    # 생성기 생성
    generator = get_hybrid_generator(whisper_model=whisper_model)

    # 처리
    result = generator.process(
        audio_path=audio_path,
        original_script=original_script,
        style=style
    )

    # 저장
    if result.success:
        srt_path = generator.save_srt(result, output_path)
    else:
        srt_path = None

    return result, srt_path


# ============================================================
# 테스트/디버그 함수
# ============================================================

def test_whisper_v3(audio_path: str, language: str = "ko"):
    """
    WhisperV3 단독 테스트

    Args:
        audio_path: 오디오 파일 경로
        language: 언어 코드
    """
    print(f"\n{'='*60}")
    print(f"WhisperV3 테스트")
    print(f"{'='*60}")

    whisper = create_optimized_whisper(model_size="small")
    result = whisper.analyze(audio_path, language=language)

    print(f"\n결과: {len(result)}개 세그먼트")

    for i, seg in enumerate(result[:10]):  # 처음 10개만 출력
        print(f"  {i+1}. [{seg['start_time']}] {seg['text'][:50]}...")

    return result


if __name__ == "__main__":
    # 테스트
    import sys

    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        script_file = sys.argv[2] if len(sys.argv) > 2 else None

        script = None
        if script_file and os.path.exists(script_file):
            with open(script_file, 'r', encoding='utf-8') as f:
                script = f.read()

        result, srt_path = process_audio_to_srt(
            audio_file,
            original_script=script
        )

        print(f"\n결과: {result.scene_count}개 씬")
        if srt_path:
            print(f"SRT 저장: {srt_path}")
    else:
        print("사용법: python hybrid_srt_generator.py <audio_file> [script_file]")
