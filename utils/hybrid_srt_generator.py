# -*- coding: utf-8 -*-
"""
HybridSRTGenerator v6.0 - 2단계 분리 SRT 생성기

⭐ 핵심 기능:
1. WhisperTimestampV3 사용 (정확도 최적화)
2. 오디오 전처리 자동 적용
3. 갭 자동 감지 및 재분석
4. 원문 기반 검증
5. ⭐ v6.0: 2단계 분리 생성
   - 1단계: generate_whisper_srt() - Whisper만으로 SRT 생성 (타임스탬프 정확!)
   - 2단계: apply_ai_original_correction() - AI 원문 교정 (선택적)

사용법:
    from utils.hybrid_srt_generator import HybridSRTGenerator

    generator = HybridSRTGenerator(whisper_model="small")

    # 1단계: Whisper SRT 생성 (타임스탬프 정확, 오타 있을 수 있음)
    result1 = generator.generate_whisper_srt(audio_path, style="잘게")

    # 2단계: AI 원문 교정 (선택적, 타임스탬프 유지!)
    result2 = generator.apply_ai_original_correction(
        scenes=result1['scenes'],
        original_script=script
    )
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
    HybridV6.0 SRT 생성기 - 2단계 분리

    ⭐ 개선사항:
    1. WhisperTimestampV3 사용 (VAD 최적화)
    2. 오디오 전처리 자동 적용
    3. 갭 자동 감지 및 재분석
    4. 원문 기반 검증
    5. ⭐ v6.0: 2단계 분리 (generate_whisper_srt + apply_ai_original_correction)
    """

    def __init__(
        self,
        whisper_model: str = "small",
        vad_threshold: float = 0.05,
        min_speech_duration_ms: int = 30,
        min_silence_duration_ms: int = 50,   # ⭐ v6.11: 사용자 조정 가능! 기본값 50ms
        speech_pad_ms: int = 30,             # ⭐ v6.11: 사용자 조정 가능! 기본값 30ms
        reanalyze_gaps: bool = True,
        auto_enhance_audio: bool = False     # ⭐ v6.10: 기본값 False (VAD 정확도 우선!)
    ):
        """
        초기화 (v6.11 - VAD 파라미터 사용자 조정 가능)

        Args:
            whisper_model: Whisper 모델 크기 (small 권장)
            vad_threshold: VAD 임계값 (0.05 권장, 극도로 민감)
            min_speech_duration_ms: 최소 음성 길이 (30ms 권장)
            min_silence_duration_ms: 무음 감지 최소 시간 (50ms 권장) ⭐ NEW!
            speech_pad_ms: 문장 앞뒤 패딩 (30ms 권장) ⭐ NEW!
            reanalyze_gaps: 갭 자동 재분석 여부
            auto_enhance_audio: 저볼륨 구간 자동 향상 여부 (False 권장!)
        """
        # WhisperV3 설정 (⭐ v6.11: 사용자 조정 가능한 VAD 파라미터)
        self.whisper_config = WhisperConfigV3(
            model_size=whisper_model,
            vad_threshold=vad_threshold,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms,   # ⭐ 사용자 조정 가능!
            speech_pad_ms=speech_pad_ms,                       # ⭐ 사용자 조정 가능!
            word_timestamps=True,
            reanalyze_gaps=reanalyze_gaps
        )

        self.whisper = WhisperTimestampV3(self.whisper_config)
        self.audio_preprocessor = AudioPreprocessor()
        self.srt_validator = get_srt_validator()

        self.auto_enhance_audio = auto_enhance_audio

        print(f"\n{'='*60}")
        print(f"[HybridV6.11] 초기화 완료 (2단계 분리 + VAD 조정 UI)")
        print(f"{'='*60}")
        print(f"  Whisper 모델: {whisper_model}")
        print(f"  VAD threshold: {vad_threshold} (극도로 민감)")
        print(f"  min_silence: {min_silence_duration_ms}ms")  # ⭐ 핵심 로그!
        print(f"  min_speech: {min_speech_duration_ms}ms")
        print(f"  speech_pad: {speech_pad_ms}ms")
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
            print(f"[HybridV6.0] 파이프라인 시작")
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

            # Step 2.5: 원문 기반 텍스트 교정 (NEW!)
            if original_script and len(original_script) > 50:
                print(f"\n📍 Step 2.5: 원문 기반 텍스트 교정")
                validated_scenes, corrections = self._apply_original_text_matching(
                    validated_scenes,
                    original_script
                )
                if corrections:
                    print(f"  교정 완료: {len(corrections)}개")
                else:
                    print(f"  교정 필요 없음")

            # Step 3: 결과 변환
            print(f"\n📍 Step 3: 결과 변환")

            # ⭐ 디버깅: 첫 번째 씬의 키 확인
            if validated_scenes:
                sample = validated_scenes[0]
                print(f"  [DEBUG] 첫 번째 씬 키: {list(sample.keys())}")
                print(f"  [DEBUG] start_time: {sample.get('start_time')}, start: {sample.get('start')}")
                print(f"  [DEBUG] end_time: {sample.get('end_time')}, end: {sample.get('end')}")

            scenes = []
            for i, scene in enumerate(validated_scenes):
                # ⭐ v6.1: 올바른 타임스탬프 키 사용 (srt_validator가 start_time/end_time 설정)
                # 우선순위: start_time > start > _start_seconds
                start_sec = scene.get('start_time')
                if start_sec is None:
                    start_sec = scene.get('start', 0)
                if not isinstance(start_sec, (int, float)):
                    start_sec = 0
                start_sec = float(start_sec)

                end_sec = scene.get('end_time')
                if end_sec is None:
                    end_sec = scene.get('end', 0)
                if not isinstance(end_sec, (int, float)):
                    end_sec = 0
                end_sec = float(end_sec)

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
            print(f"[HybridV6.0] ✅ 파이프라인 완료")
            print(f"{'='*60}")
            print(f"  총 씬: {result.scene_count}개")
            print(f"  복구 씬: {recovered_count}개")
            print(f"  오디오 향상: {'예' if audio_was_enhanced else '아니오'}")
            print(f"{'='*60}")

            return result

        except Exception as e:
            print(f"\n[HybridV6.0] ❌ 오류: {e}")
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

    def _apply_original_text_matching(
        self,
        scenes: List[Dict],
        original_script: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Step 2.5: 원문 기반 텍스트 교정 (v5.6)

        타임스탬프는 절대 변경하지 않음!
        텍스트만 원문과 일치시킴!

        Args:
            scenes: 씬 리스트 (dict)
            original_script: 원문 스크립트

        Returns:
            (교정된 씬 리스트, 교정 내역)
        """
        try:
            from utils.original_text_matcher import get_original_text_matcher

            matcher = get_original_text_matcher()
            corrected_scenes, corrections = matcher.match_and_correct(scenes, original_script)

            # 교정 내역 일부 출력
            if corrections:
                for c in corrections[:3]:
                    before = c['before'][:25] + '...' if len(c['before']) > 25 else c['before']
                    after = c['after'][:25] + '...' if len(c['after']) > 25 else c['after']
                    print(f"    씬 {c['scene_id']}: {before} → {after}")
                if len(corrections) > 3:
                    print(f"    ... 외 {len(corrections) - 3}개")

            return corrected_scenes, corrections

        except ImportError as e:
            print(f"  ⚠️ OriginalTextMatcher 로드 실패: {e}")
            return scenes, []
        except Exception as e:
            print(f"  ⚠️ 원문 매칭 오류: {e}")
            return scenes, []

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

        print(f"[HybridV6.0] SRT 저장: {output_path}")
        return output_path

    # ============================================================
    # v6.0: 2단계 분리 메서드
    # ============================================================

    def generate_whisper_srt(self,
                              audio_path: str,
                              style: str = "잘게",
                              language: str = "ko") -> Dict:
        """
        ⭐ 1단계: Whisper SRT 생성 (AI 교정 없이!)

        ⭐ 타임스탬프 100% 정확
        ⚠️ 텍스트에 오타 있을 수 있음 (나중에 AI 교정)

        Args:
            audio_path: 오디오 파일 경로
            style: 분리 스타일 (잘게, 기본, 크게)
            language: 언어 코드

        Returns:
            {
                'success': True,
                'scenes': [...],           # 씬 리스트 (dict)
                'srt_content': '...',      # SRT 파일 내용
                'srt_path': '...',         # SRT 파일 경로
                'stats': {...}             # 통계
            }
        """

        print(f"\n{'='*60}")
        print(f"[HybridV6.0] 1단계: Whisper SRT 생성 시작")
        print(f"{'='*60}")
        print(f"  오디오: {Path(audio_path).name}")
        print(f"  스타일: {style}")

        try:
            # 기존 process 메서드 활용 (원문 없이!)
            result = self.process(
                audio_path=audio_path,
                original_script=None,  # ⭐ 원문 없이 생성!
                style=style,
                language=language
            )

            if not result.success:
                return {
                    'success': False,
                    'error': result.error or '알 수 없는 오류'
                }

            # 씬을 dict 형태로 변환
            scenes_dict = [scene.to_dict() for scene in result.scenes]

            # SRT 내용 생성
            srt_content = result.to_srt()

            # 파일 저장
            audio_name = Path(audio_path).stem
            output_dir = Path(audio_path).parent / 'analysis'
            output_dir.mkdir(parents=True, exist_ok=True)

            srt_path = output_dir / f'{audio_name}_whisper.srt'
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)

            # JSON도 저장 (나중에 AI 교정용)
            import json
            json_path = output_dir / f'{audio_name}_whisper.json'
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(scenes_dict, f, ensure_ascii=False, indent=2)

            print(f"\n{'='*60}")
            print(f"[HybridV6.0] ✅ 1단계 완료: Whisper SRT 생성")
            print(f"{'='*60}")
            print(f"  씬: {len(scenes_dict)}개")
            print(f"  SRT: {srt_path}")
            print(f"  JSON: {json_path}")

            return {
                'success': True,
                'scenes': scenes_dict,
                'srt_content': srt_content,
                'srt_path': str(srt_path),
                'json_path': str(json_path),
                'stats': {
                    'whisper_segments': result.whisper_segments,
                    'merged_scenes': result.scene_count,
                    'recovered_segments': result.recovered_segments,
                    'audio_duration': result.audio_duration,
                    'style': style
                }
            }

        except Exception as e:
            print(f"[HybridV6.0] ❌ 1단계 오류: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def apply_ai_original_correction(self,
                                      scenes: List[Dict],
                                      original_script: str,
                                      output_path: str = None) -> Dict:
        """
        ⭐ 2단계: AI 원문 교정 (선택적!)

        ⭐ 타임스탬프는 절대 변경하지 않음!
        ⭐ 텍스트만 원문과 일치시킴!

        Args:
            scenes: 1단계에서 생성된 Whisper SRT 씬 리스트
            original_script: 사용자가 입력한 원문 스크립트
            output_path: 저장 경로 (없으면 자동 생성)

        Returns:
            {
                'success': True,
                'scenes': [...],           # 교정된 씬 리스트
                'srt_content': '...',      # 교정된 SRT 내용
                'srt_path': '...',         # 저장 경로
                'corrections': [...],      # 교정 내역
                'stats': {...}
            }
        """

        print(f"\n{'='*60}")
        print(f"[HybridV6.0] 2단계: AI 원문 교정 시작")
        print(f"{'='*60}")
        print(f"  입력 씬: {len(scenes)}개")
        print(f"  원문 길이: {len(original_script) if original_script else 0}자")

        # 디버깅: 입력 씬의 타임스탬프 확인
        if scenes:
            sample = scenes[0]
            print(f"  [DEBUG 입력] 첫 번째 씬 키: {list(sample.keys())}")
            print(f"  [DEBUG 입력] timecode: {sample.get('timecode')}")
            print(f"  [DEBUG 입력] start_time: {sample.get('start_time')}")
            print(f"  [DEBUG 입력] end_time: {sample.get('end_time')}")

        if not original_script or not original_script.strip():
            print(f"[HybridV6.0] ⚠️ 원문 스크립트가 없습니다!")
            return {'success': False, 'error': '원문 스크립트가 필요합니다.'}

        if not scenes:
            print(f"[HybridV6.0] ⚠️ 씬 데이터가 없습니다!")
            return {'success': False, 'error': '씬 데이터가 필요합니다.'}

        try:
            # AI 원문 교정기 생성
            from utils.ai_original_corrector import AIOriginalCorrector
            corrector = AIOriginalCorrector(provider='google')

            # AI 교정 실행
            corrected_scenes, corrections = corrector.correct_with_original(
                scenes=scenes,
                original_script=original_script,
                batch_size=5
            )

            # 디버깅: 교정 후 타임스탬프 확인
            if corrected_scenes:
                sample = corrected_scenes[0]
                print(f"  [DEBUG 교정후] 첫 번째 씬 키: {list(sample.keys())}")
                print(f"  [DEBUG 교정후] timecode: {sample.get('timecode')}")
                print(f"  [DEBUG 교정후] start_time: {sample.get('start_time')}")
                print(f"  [DEBUG 교정후] end_time: {sample.get('end_time')}")

            # SRT 내용 생성
            srt_content = self._generate_srt_from_dict(corrected_scenes)

            # 파일 저장
            if output_path:
                srt_path = output_path
            else:
                # 기본 경로 생성
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                srt_path = f"output/corrected_{timestamp}.srt"

            Path(srt_path).parent.mkdir(parents=True, exist_ok=True)

            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)

            print(f"\n{'='*60}")
            print(f"[HybridV6.0] ✅ 2단계 완료: AI 원문 교정")
            print(f"{'='*60}")
            print(f"  총 교정: {len(corrections)}개")
            print(f"  저장: {srt_path}")

            return {
                'success': True,
                'scenes': corrected_scenes,
                'srt_content': srt_content,
                'srt_path': srt_path,
                'corrections': corrections,
                'stats': {
                    'total_scenes': len(corrected_scenes),
                    'corrected_scenes': len(corrections)
                }
            }

        except Exception as e:
            print(f"[HybridV6.0] ❌ 2단계 오류: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def _generate_srt_from_dict(self, scenes: List[Dict]) -> str:
        """씬 딕셔너리 리스트를 SRT 문자열로 변환"""

        srt_blocks = []

        # 디버깅: 첫 번째 씬 구조 확인
        if scenes:
            sample = scenes[0]
            print(f"[_generate_srt_from_dict] 첫 번째 씬 키: {list(sample.keys())}")
            print(f"[_generate_srt_from_dict] timecode: {sample.get('timecode')}")
            print(f"[_generate_srt_from_dict] start_time: {sample.get('start_time')}")
            print(f"[_generate_srt_from_dict] end_time: {sample.get('end_time')}")

        for i, scene in enumerate(scenes, 1):
            # 타임코드 가져오기 (여러 형식 지원)
            timecode = None

            # 1순위: timecode 필드 (이미 포맷된 문자열)
            if 'timecode' in scene and scene['timecode'] and '-->' in str(scene['timecode']):
                timecode = scene['timecode']
            else:
                # 2순위: start_time, end_time에서 생성
                start = self._get_timestamp_value(scene, 'start')
                end = self._get_timestamp_value(scene, 'end')

                start_tc = self._format_timecode(start)
                end_tc = self._format_timecode(end)

                timecode = f"{start_tc} --> {end_tc}"

            text = scene.get('text', '')

            srt_blocks.append(f"{i}\n{timecode}\n{text}\n")

        return "\n".join(srt_blocks)

    def _get_timestamp_value(self, scene: Dict, prefix: str) -> float:
        """
        씬에서 타임스탬프 값 추출 (다양한 키 지원)

        Args:
            scene: 씬 딕셔너리
            prefix: 'start' 또는 'end'

        Returns:
            초 단위 float 값
        """
        # 1순위: start_time / end_time
        val = scene.get(f'{prefix}_time')
        if val is not None and isinstance(val, (int, float)):
            return float(val)

        # 2순위: start / end
        val = scene.get(prefix)
        if val is not None and isinstance(val, (int, float)):
            return float(val)

        # 3순위: start_sec / end_sec
        val = scene.get(f'{prefix}_sec')
        if val is not None and isinstance(val, (int, float)):
            return float(val)

        return 0.0


# ============================================================
# 팩토리 함수
# ============================================================

def get_hybrid_generator(
    whisper_model: str = "small",
    vad_threshold: float = 0.05,
    min_speech_duration_ms: int = 30,
    min_silence_duration_ms: int = 50,   # ⭐ v6.11: 사용자 조정 가능!
    speech_pad_ms: int = 30,             # ⭐ v6.11: 사용자 조정 가능!
    reanalyze_gaps: bool = True,
    auto_enhance_audio: bool = False     # ⭐ v6.10: 기본값 False (VAD 정확도 우선!)
) -> HybridSRTGenerator:
    """
    HybridSRTGenerator 인스턴스 생성 (v6.11)

    Args:
        whisper_model: Whisper 모델 크기
        vad_threshold: VAD 임계값 (0.05 권장)
        min_speech_duration_ms: 최소 음성 길이 (30ms 권장)
        min_silence_duration_ms: 무음 감지 최소 시간 (50ms 권장) ⭐ NEW!
        speech_pad_ms: 문장 앞뒤 패딩 (30ms 권장) ⭐ NEW!
        reanalyze_gaps: 갭 재분석 여부
        auto_enhance_audio: 오디오 향상 여부 (False 권장!)

    Returns:
        HybridSRTGenerator 인스턴스
    """
    return HybridSRTGenerator(
        whisper_model=whisper_model,
        vad_threshold=vad_threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
        speech_pad_ms=speech_pad_ms,
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
