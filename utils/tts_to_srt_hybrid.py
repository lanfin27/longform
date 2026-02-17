# -*- coding: utf-8 -*-
"""
TTS -> SRT 하이브리드 변환 모듈 (v5.4)

6단계 파이프라인:
1. Whisper 잘게 쪼개기 (스타일별: 잘게 3초/40자, 기본 5초/60자)
2. AI 스타일별 병합 (잘게 최대 50자, 기본 최대 80자) - Claude Agent 지원
3. 기본 텍스트 교정 (v5.1)
4. 원문 기반 후처리 교정 (v5.2)
5. SRT 타임스탬프 검증/수정 (v5.3) - 겹침/빈구간 자동 해결
6. 최종 SRT 검증 (v5.4 NEW!) - 원문과 완전 매칭 교정
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass, asdict

from utils.device_manager import get_gpu_status, select_device
from utils.whisper_timestamp import (
    WhisperTimestampExtractor,
    WhisperResult,
    SentenceSegment,
    get_whisper_extractor,
    SENTENCE_SPLIT_CONFIG
)
from utils.ai_scene_splitter import (
    AISceneMerger,
    SceneGroup,
    get_scene_merger,
    STYLE_CONFIG,
    MERGE_PROMPTS
)
from utils.text_corrector import (
    TextCorrector,
    TextCorrectorV3,
    SceneGroupCorrected,
    get_text_corrector,
    get_text_corrector_v3
)
from utils.srt_validator import (
    SRTValidator,
    get_srt_validator,
    validate_and_fix_srt
)
from utils.final_srt_validator import (
    FinalSRTValidator,
    get_final_validator,
    validate_srt_final
)

# Claude Agent (선택적 import)
try:
    from utils.claude_agent import (
        SceneSplitAgent,
        TextCorrectorAgent,
        get_scene_split_agent,
        get_text_corrector_agent,
        is_anthropic_available,
        check_api_key as check_anthropic_key
    )
    CLAUDE_AGENT_AVAILABLE = True
except ImportError:
    CLAUDE_AGENT_AVAILABLE = False
    print("[HybridV5.4] Claude Agent (API) 사용 불가 (anthropic 패키지 없음)")

# ✅ v5.4: Claude Code Runner (subprocess 방식)
try:
    from utils.claude_code_runner import get_claude_code_runner, is_claude_code_available
    CLAUDE_CODE_AVAILABLE = is_claude_code_available()
except ImportError:
    CLAUDE_CODE_AVAILABLE = False
    print("[HybridV5.4] Claude Code Runner 사용 불가")


@dataclass
class HybridSceneV5:
    """완벽한 씬 (v5.0)"""
    scene_id: int
    text: str  # 교정된 텍스트
    start_time: float
    end_time: float
    duration: float
    timecode: str
    sentence_ids: List[int]
    whisper_text: str  # 원본 Whisper 텍스트 (비교용)
    mood: str = ""
    scene_break_reason: str = ""

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    # 하위 호환성
    @property
    def script_text(self) -> str:
        return self.text

    @property
    def segment_ids(self) -> List[int]:
        return self.sentence_ids


class TTStoSRTHybridV5:
    """하이브리드 변환기 (v5.4 - 6단계 파이프라인)"""

    def __init__(
        self,
        whisper_model: str = "base",
        device_mode: str = "auto",
        ai_provider: str = "google",
        ai_model: str = "gemini-2.5-flash",
        whisper_engine: str = "auto",
        whisper_compute_type: str = "auto",
        whisper_vad_filter: bool = True,
        whisper_refine: bool = False
    ):
        """
        Args:
            whisper_model: Whisper 모델 크기
            device_mode: "auto", "gpu", "cpu"
            ai_provider: AI 제공자 ("google", "anthropic", "claude_code_agent")
            ai_model: AI 모델 ID 또는 "claude-agent"
            whisper_engine: Whisper 엔진 ("auto", "faster-whisper", "stable-ts")
            whisper_compute_type: 계산 타입 ("auto", "int8", "float16", "float32")
            whisper_vad_filter: VAD 필터 사용 여부 (faster-whisper)
            whisper_refine: 타임스탬프 미세 조정 (stable-ts)
        """
        self.whisper_model = whisper_model
        self.device_mode = device_mode
        self.whisper_engine = whisper_engine
        self.whisper_compute_type = whisper_compute_type
        self.whisper_vad_filter = whisper_vad_filter
        self.whisper_refine = whisper_refine

        # ✅ v5.4: Claude Agent 감지 및 올바른 provider 라우팅
        # "claude-agent" 선택 시 → claude_code_agent (subprocess 방식)
        if ai_model == "claude-agent" or ai_provider == "claude_code_agent":
            # ⭐ subprocess 방식으로 Claude CLI 실행
            self.use_claude_agent = True
            self.use_claude_code = True  # subprocess 방식
            self.ai_provider = "claude_code_agent"
            self.ai_model = None  # CLI는 모델 지정 불필요
            print(f"[HybridV5.4] ⭐ Claude Code Agent (subprocess) 모드")
        elif ai_provider == "anthropic":
            # Claude API 사용 (올바른 모델명 필요)
            self.use_claude_agent = True
            self.use_claude_code = False
            self.ai_provider = "anthropic"
            # ✅ "claude-agent" 같은 잘못된 모델명 방지
            if not ai_model or "agent" in ai_model.lower() or not ai_model.startswith("claude-"):
                self.ai_model = "claude-sonnet-4-20250514"
            else:
                self.ai_model = ai_model
        else:
            self.use_claude_agent = False
            self.use_claude_code = False
            self.ai_provider = ai_provider
            self.ai_model = ai_model

        self._whisper_extractor = None
        self._scene_merger = None
        self._text_corrector = None
        self._text_corrector_v3 = None
        self._srt_validator = None  # v5.3: SRT 검증기
        self._claude_scene_agent = None  # v5.3: Claude 씬 분할 에이전트
        self._claude_corrector_agent = None  # v5.3: Claude 텍스트 교정 에이전트
        self.device_used = None

        print(f"[HybridV5.4] 초기화")
        print(f"[HybridV5.4]   Whisper: {whisper_model} (mode: {device_mode})")
        if self.use_claude_code:
            print(f"[HybridV5.4]   AI: Claude Code Agent (subprocess)")
        elif self.use_claude_agent:
            print(f"[HybridV5.4]   AI: Claude API ({self.ai_model})")
        else:
            print(f"[HybridV5.4]   AI: {ai_provider}/{ai_model}")

    @property
    def whisper_extractor(self) -> WhisperTimestampExtractor:
        """Whisper 추출기 (지연 로딩)"""
        if self._whisper_extractor is None:
            self._whisper_extractor = WhisperTimestampExtractor(
                model_size=self.whisper_model,
                device=self.device_mode,
                engine=self.whisper_engine,
                compute_type=self.whisper_compute_type,
                vad_filter=self.whisper_vad_filter,
                refine=self.whisper_refine
            )
        return self._whisper_extractor

    @property
    def scene_merger(self) -> AISceneMerger:
        """AI 씬 병합기 (지연 로딩)"""
        if self._scene_merger is None:
            self._scene_merger = AISceneMerger(
                provider=self.ai_provider,
                model=self.ai_model
            )
        return self._scene_merger

    @property
    def text_corrector(self) -> TextCorrector:
        """텍스트 교정기 (지연 로딩)"""
        if self._text_corrector is None:
            self._text_corrector = TextCorrector(
                provider=self.ai_provider,
                model=self.ai_model
            )
        return self._text_corrector

    @property
    def text_corrector_v3(self) -> TextCorrectorV3:
        """v5.2: 원문 기반 교정기 (지연 로딩)"""
        if self._text_corrector_v3 is None:
            self._text_corrector_v3 = TextCorrectorV3(
                provider=self.ai_provider,
                model=self.ai_model
            )
        return self._text_corrector_v3

    @property
    def srt_validator(self) -> SRTValidator:
        """v5.3: SRT 검증기 (지연 로딩)"""
        if self._srt_validator is None:
            self._srt_validator = get_srt_validator()
        return self._srt_validator

    @property
    def claude_scene_agent(self):
        """v5.3: Claude 씬 분할 에이전트 (지연 로딩)"""
        if self._claude_scene_agent is None and CLAUDE_AGENT_AVAILABLE:
            self._claude_scene_agent = get_scene_split_agent()
        return self._claude_scene_agent

    @property
    def claude_corrector_agent(self):
        """v5.3: Claude 텍스트 교정 에이전트 (지연 로딩)"""
        if self._claude_corrector_agent is None and CLAUDE_AGENT_AVAILABLE:
            self._claude_corrector_agent = get_text_corrector_agent()
        return self._claude_corrector_agent

    def convert(
        self,
        audio_path: str,
        original_script: str,
        language: str = "ko",
        split_style: str = "기본",
        output_srt_path: str = None,
        output_json_path: str = None,
        enable_v3_correction: bool = True,
        enable_srt_validation: bool = True,  # v5.3: SRT 검증
        enable_final_validation: bool = True,  # v5.4: 최종 SRT 검증
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Tuple[str, List[HybridSceneV5], Dict]:
        """
        6단계 파이프라인 실행 (v5.4)

        Args:
            audio_path: TTS 오디오 파일
            original_script: 원본 스크립트 (필수!)
            language: 언어
            split_style: "잘게", "기본", "크게"
            output_srt_path: SRT 저장 경로
            output_json_path: JSON 저장 경로
            enable_v3_correction: 원문 기반 후처리 교정 활성화 (v5.2)
            enable_srt_validation: v5.3 SRT 타임스탬프 검증/수정 활성화
            enable_final_validation: v5.4 최종 SRT 검증 활성화
            progress_callback: 진행률 콜백 (percent, message)

        Returns:
            (SRT 텍스트, HybridSceneV5 리스트, 메타데이터 딕셔너리)
        """
        def report_progress(percent: int, message: str):
            print(f"[HybridV5] {percent}% - {message}")
            if progress_callback:
                progress_callback(percent, message)

        config = STYLE_CONFIG.get(split_style, STYLE_CONFIG["기본"])

        print(f"\n{'='*60}")
        print(f"[HybridV5.4] 6단계 파이프라인 시작")
        print(f"{'='*60}")
        print(f"  오디오: {Path(audio_path).name}")
        print(f"  원문: {len(original_script)}자")
        print(f"  스타일: {split_style} ({config['min_sentences']}-{config['max_sentences']}문장/씬)")
        print(f"  AI 모델: {'Claude Agent' if self.use_claude_agent else self.ai_model}")
        print(f"  후처리 교정: {'활성화' if enable_v3_correction else '비활성화'}")
        print(f"  SRT 검증: {'활성화' if enable_srt_validation else '비활성화'}")
        print(f"  최종 검증: {'활성화' if enable_final_validation else '비활성화'}")

        report_progress(5, "초기화 중...")

        # ============================================================
        # Step 1: Whisper 문장 단위 분리
        # ============================================================
        report_progress(10, "Whisper 모델 로딩 중...")
        print(f"\n📍 Step 1: Whisper 문장 단위 분리")

        def whisper_progress(p, m):
            report_progress(10 + int(p * 0.25), m)

        whisper_result = self.whisper_extractor.extract(
            audio_path,
            language,
            split_style=split_style,  # ✅ 스타일 전달
            progress_callback=whisper_progress
        )

        self.device_used = whisper_result.device_used
        print(f"[HybridV5]   문장: {len(whisper_result.sentences)}개")
        print(f"[HybridV5]   총 길이: {whisper_result.duration:.1f}초 ({int(whisper_result.duration//60)}분 {int(whisper_result.duration%60)}초)")
        print(f"[HybridV5]   사용된 디바이스: {self.device_used}")

        report_progress(40, f"Step 1 완료: {len(whisper_result.sentences)}개 문장 ({self.device_used})")

        # ============================================================
        # Step 2: AI 스타일별 병합 (Gemini 또는 Claude Agent)
        # ============================================================
        report_progress(45, f"AI 병합 중 ({split_style})...")

        if self.use_claude_agent and CLAUDE_AGENT_AVAILABLE:
            # Claude Agent 사용
            print(f"\n Step 2: Claude Agent 씬 분할 ({split_style})")

            # Whisper 결과를 Claude Agent 형식으로 변환
            sentences_for_claude = []
            for i, sent in enumerate(whisper_result.sentences):
                sentences_for_claude.append({
                    "id": i,
                    "text": sent.text,
                    "start": sent.start,  # SentenceSegment uses 'start' not 'start_time'
                    "end": sent.end       # SentenceSegment uses 'end' not 'end_time'
                })

            # Claude Agent로 씬 분할
            agent_result = self.claude_scene_agent.split_scenes(
                sentences_for_claude,
                split_style=split_style
            )

            if agent_result.success:
                # Claude Agent 결과를 SceneGroup으로 변환
                scene_groups = []
                for sd in agent_result.data:
                    scene_groups.append(SceneGroup(
                        scene_id=sd.get("scene_id", len(scene_groups) + 1),
                        sentence_ids=sd.get("sentence_ids", []),
                        text=sd.get("text", ""),
                        start_time=sd.get("start_time", 0),
                        end_time=sd.get("end_time", 0),
                        mood="",
                        scene_break_reason=sd.get("reasoning", "")
                    ))
                print(f"[HybridV5]   Claude Agent 씬: {len(scene_groups)}개")
            else:
                # 실패 시 Gemini로 폴백
                print(f"[HybridV5]   Claude Agent 실패, Gemini로 폴백: {agent_result.error}")
                scene_groups = self.scene_merger.merge_sentences(
                    whisper_result,
                    split_style=split_style
                )
        else:
            # 기존 Gemini 사용
            print(f"\n Step 2: AI 스타일별 병합 ({split_style})")
            scene_groups = self.scene_merger.merge_sentences(
                whisper_result,
                split_style=split_style
            )

        print(f"[HybridV5]   병합 후 씬: {len(scene_groups)}개")

        # ✅ 글자수 초과 검증 및 강제 분할
        max_chars = config.get("max_chars", 250)
        scene_groups = self._validate_and_fix_scenes(
            scene_groups, whisper_result, max_chars
        )
        print(f"[HybridV5]   검증 후 씬: {len(scene_groups)}개")

        report_progress(65, f"Step 2 완료: {len(scene_groups)}개 씬")

        # ============================================================
        # Step 3: 기본 텍스트 교정 (v5.1)
        # ============================================================
        report_progress(65, "기본 텍스트 교정 중...")
        print(f"\n📍 Step 3: 기본 텍스트 교정 (v5.1)")

        if original_script and len(original_script) >= 50:
            corrected_scenes = self.text_corrector.correct_scenes(
                scene_groups,
                original_script
            )
        else:
            print(f"[HybridV5.2]   원문 스크립트 없음, 교정 건너뜀")
            # 교정 없이 그대로 변환
            corrected_scenes = []
            for sg in scene_groups:
                corrected_scenes.append(SceneGroupCorrected(
                    scene_id=sg.scene_id,
                    sentence_ids=sg.sentence_ids,
                    text=sg.text,
                    start_time=sg.start_time,
                    end_time=sg.end_time,
                    original_whisper_text=sg.text,
                    mood=sg.mood if hasattr(sg, 'mood') else "",
                    scene_break_reason=sg.scene_break_reason if hasattr(sg, 'scene_break_reason') else ""
                ))

        report_progress(75, "Step 3 완료: 기본 교정됨")

        # ============================================================
        # Step 4: 원문 기반 후처리 교정 (Gemini 또는 Claude Agent)
        # ============================================================
        correction_changes = []  # 교정 변경 내역

        if enable_v3_correction and original_script and len(original_script) >= 50:
            report_progress(78, "원문 기반 후처리 교정 중...")

            if self.use_claude_agent and CLAUDE_AGENT_AVAILABLE:
                # Claude Agent 텍스트 교정
                print(f"\n Step 4: Claude Agent 텍스트 교정")

                # corrected_scenes를 dict로 변환
                scenes_for_claude = []
                for cs in corrected_scenes:
                    scenes_for_claude.append({
                        "scene_id": cs.scene_id,
                        "text": cs.text,
                        "start_time": cs.start_time,
                        "end_time": cs.end_time
                    })

                agent_result = self.claude_corrector_agent.correct_text(
                    scenes_for_claude,
                    original_script
                )

                if agent_result.success:
                    # 교정 결과 적용
                    corrections_data = agent_result.data
                    correction_changes = corrections_data.get("corrections", [])

                    # corrected_scenes 업데이트
                    corrected_dict = {
                        str(s.get("scene_id", "")): s.get("text", "")
                        for s in corrections_data.get("corrected_scenes", [])
                        if "text" in s
                    }

                    for cs in corrected_scenes:
                        scene_key = str(cs.scene_id)
                        if scene_key in corrected_dict:
                            cs.text = corrected_dict[scene_key]

                    print(f"[HybridV5.3]   Claude 교정: {len(correction_changes)}개")
                else:
                    print(f"[HybridV5.3]   Claude Agent 실패, Gemini로 폴백: {agent_result.error}")
                    corrected_scenes, correction_changes = self.text_corrector_v3.correct_srt_with_script(
                        corrected_scenes,
                        original_script
                    )
            else:
                # 기존 Gemini v3 교정기 사용
                print(f"\n Step 4: 원문 기반 후처리 교정 (v5.2)")
                corrected_scenes, correction_changes = self.text_corrector_v3.correct_srt_with_script(
                    corrected_scenes,
                    original_script
                )

            if correction_changes:
                print(f"[HybridV5.3]   교정된 씬: {len(correction_changes)}개")
                for change in correction_changes[:3]:
                    orig_preview = str(change.get('original', ''))[:30].replace('\n', ' ')
                    corr_preview = str(change.get('corrected', ''))[:30].replace('\n', ' ')
                    print(f"[HybridV5.3]     씬 {change.get('scene_id', '?')}: {orig_preview}... -> {corr_preview}...")
            else:
                print(f"[HybridV5.3]   교정 필요 없음")

            report_progress(82, f"Step 4 완료: {len(correction_changes)}개 교정")
        else:
            print(f"\n Step 4: 후처리 교정 스킵 (비활성화 또는 원문 없음)")
            report_progress(82, "Step 4 스킵")

        # ============================================================
        # Step 5: SRT 타임스탬프 검증/수정 (v5.3 NEW!)
        # ============================================================
        validation_fixes = []

        if enable_srt_validation:
            report_progress(85, "SRT 타임스탬프 검증 중...")
            print(f"\n Step 5: SRT 타임스탬프 검증/수정 (v5.3)")

            # corrected_scenes를 검증용 dict로 변환
            scenes_for_validation = []
            for cs in corrected_scenes:
                scenes_for_validation.append({
                    "scene_id": cs.scene_id,
                    "text": cs.text,
                    "start_time": cs.start_time,
                    "end_time": cs.end_time
                })

            # 검증 및 수정 (v5.0: 갭 복구 추가!)
            validated_scenes, validation_fixes = self.srt_validator.validate_and_fix(
                scenes_for_validation,
                total_duration=whisper_result.duration,
                original_script=original_script,  # ⭐ v5.0: 갭 복구용 원문 전달
                audio_duration=whisper_result.duration
            )

            # ⭐ v4.0: 검증 결과로 corrected_scenes 완전 재구성
            # (중복 제거, 재정렬 등이 반영됨)
            if len(validated_scenes) != len(corrected_scenes):
                print(f"[HybridV5.4]   씬 개수 변경: {len(corrected_scenes)} → {len(validated_scenes)}")

            # validated_scenes의 scene_id로 원본 찾기
            original_by_text = {cs.text.strip()[:50]: cs for cs in corrected_scenes}

            new_corrected_scenes = []
            for vs in validated_scenes:
                vs_text = vs.get("text", "").strip()[:50]

                # 원본에서 매칭되는 씬 찾기
                if vs_text in original_by_text:
                    orig = original_by_text[vs_text]
                    # 새로운 타임스탬프와 scene_id로 업데이트
                    new_scene = SceneGroupCorrected(
                        scene_id=vs.get("scene_id", orig.scene_id),
                        sentence_ids=orig.sentence_ids,
                        text=vs.get("text", orig.text),
                        start_time=vs.get("start_time", orig.start_time),
                        end_time=vs.get("end_time", orig.end_time),
                        original_whisper_text=orig.original_whisper_text,
                        mood=getattr(orig, 'mood', ''),
                        scene_break_reason=getattr(orig, 'scene_break_reason', '')
                    )
                    new_corrected_scenes.append(new_scene)
                else:
                    # 매칭 안 되면 새 씬 생성
                    new_scene = SceneGroupCorrected(
                        scene_id=vs.get("scene_id", 0),
                        sentence_ids=[],
                        text=vs.get("text", ""),
                        start_time=vs.get("start_time", 0),
                        end_time=vs.get("end_time", 0),
                        original_whisper_text="",
                        mood="",
                        scene_break_reason=""
                    )
                    new_corrected_scenes.append(new_scene)

            corrected_scenes = new_corrected_scenes

            if validation_fixes:
                print(f"[HybridV5.4]   타임스탬프 수정: {len(validation_fixes)}개")
                for fix in validation_fixes[:3]:
                    print(f"[HybridV5.4]     {fix.get('type', '?')}: 씬 {fix.get('index', '?')}")
            else:
                print(f"[HybridV5.4]   타임스탬프 문제 없음")

            report_progress(85, f"Step 5 완료: {len(validation_fixes)}개 수정")
        else:
            print(f"\n Step 5: SRT 검증 스킵 (비활성화)")
            report_progress(85, "Step 5 스킵")

        # ============================================================
        # Step 6: 최종 SRT 검증 (v5.4 NEW!)
        # ============================================================
        final_corrections = []

        if enable_final_validation and original_script and len(original_script) >= 50:
            report_progress(87, "최종 SRT 검증 중...")
            print(f"\n📍 Step 6: 최종 SRT 검증 (v5.4)")

            # corrected_scenes를 검증용 dict 리스트로 변환
            scenes_for_final = []
            for cs in corrected_scenes:
                scenes_for_final.append({
                    "scene_id": cs.scene_id,
                    "text": cs.text,
                    "start_time": cs.start_time,
                    "end_time": cs.end_time
                })

            # 최종 검증 및 교정
            validator = get_final_validator()
            result = validator.validate_and_correct(scenes_for_final, original_script)

            # 교정 결과 적용
            corrected_dict = {}
            for sc in result.corrected_scenes:
                if isinstance(sc, dict):
                    sid = sc.get('scene_id')
                    text = sc.get('text')
                else:
                    sid = getattr(sc, 'scene_id', None)
                    text = getattr(sc, 'text', None)
                if sid is not None and text is not None:
                    corrected_dict[sid] = text

            for cs in corrected_scenes:
                if cs.scene_id in corrected_dict:
                    cs.text = corrected_dict[cs.scene_id]

            final_corrections = result.corrections_made

            if final_corrections:
                print(f"[HybridV5.4]   최종 교정: {len(final_corrections)}개")
                for corr in final_corrections[:3]:
                    orig_preview = str(corr.get('original_srt', ''))[:25].replace('\n', ' ')
                    corr_preview = str(corr.get('corrected', ''))[:25].replace('\n', ' ')
                    print(f"[HybridV5.4]     씬 {corr.get('scene_id', '?')}: {orig_preview}... -> {corr_preview}...")
            else:
                print(f"[HybridV5.4]   추가 교정 필요 없음")

            report_progress(92, f"Step 6 완료: {len(final_corrections)}개 최종 교정")
        else:
            print(f"\n Step 6: 최종 검증 스킵 (비활성화 또는 원문 없음)")
            report_progress(92, "Step 6 스킵")

        # ============================================================
        # Step 7: 최종 씬 생성 및 SRT 출력
        # ============================================================
        report_progress(95, "SRT 생성 중...")
        print(f"\n Step 7: SRT 생성")

        final_scenes = []
        for cs in corrected_scenes:
            final_scenes.append(HybridSceneV5(
                scene_id=cs.scene_id,
                text=cs.text,
                start_time=cs.start_time,
                end_time=cs.end_time,
                duration=cs.duration,
                timecode=cs.timecode,
                sentence_ids=cs.sentence_ids,
                whisper_text=cs.original_whisper_text,
                mood=cs.mood if hasattr(cs, 'mood') else "",
                scene_break_reason=cs.scene_break_reason if hasattr(cs, 'scene_break_reason') else ""
            ))

        # SRT 생성
        srt_text = self._generate_srt(final_scenes, output_srt_path)

        # JSON 저장
        if output_json_path:
            self._save_json(final_scenes, whisper_result, output_json_path, correction_changes, validation_fixes, final_corrections)

        report_progress(100, "완료!")

        # 결과 출력
        audio_duration = whisper_result.duration
        final_end = final_scenes[-1].end_time if final_scenes else 0

        print(f"\n{'='*60}")
        print(f"[HybridV5.4] 6단계 파이프라인 완료!")
        print(f"  Whisper 문장: {len(whisper_result.sentences)}개")
        print(f"  최종 씬: {len(final_scenes)}개")
        print(f"  원문 교정: {len(correction_changes)}개 씬 수정됨")
        print(f"  타임스탬프 수정: {len(validation_fixes)}개")  # v5.3
        print(f"  최종 검증 교정: {len(final_corrections)}개")  # v5.4
        print(f"  오디오 길이: {audio_duration:.1f}초 ({int(audio_duration//60)}분 {int(audio_duration%60)}초)")
        print(f"  SRT 최종 시간: {final_end:.1f}초")
        print(f"  사용된 디바이스: {self.device_used}")
        print(f"  AI 모델: {'Claude Agent' if self.use_claude_agent else self.ai_model}")

        # 싱크 검증
        sync_diff = abs(final_end - audio_duration)
        if sync_diff < 1.0:
            print(f"  [OK] 싱크 정확! (차이: {sync_diff:.2f}초)")
        else:
            print(f"  [WARN] 싱크 차이: {sync_diff:.1f}초")

        print(f"{'='*60}\n")

        # v5.4: 메타데이터 딕셔너리 반환
        metadata = {
            "correction_changes": correction_changes,
            "validation_fixes": validation_fixes,
            "final_corrections": final_corrections,  # v5.4: 최종 검증 교정
            "ai_model": "claude-agent" if self.use_claude_agent else self.ai_model,
            "device_used": self.device_used
        }

        return srt_text, final_scenes, metadata

    def _generate_srt(
        self,
        scenes: List[HybridSceneV5],
        output_path: str = None
    ) -> str:
        """SRT 생성 (⭐ v4.0: 최종 정렬 포함)"""

        def ts(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        # ⭐ v4.0: 최종 시간순 정렬!
        sorted_scenes = sorted(scenes, key=lambda x: x.start_time)

        # ⭐ v4.0: 최종 중복 제거!
        seen_texts = set()
        final_scenes = []
        for scene in sorted_scenes:
            text_key = scene.text.strip().lower()[:50]
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                final_scenes.append(scene)

        if len(final_scenes) != len(sorted_scenes):
            print(f"[HybridV5] SRT 최종 중복 제거: {len(sorted_scenes)} → {len(final_scenes)}")

        lines = []
        for i, scene in enumerate(final_scenes):
            # scene_id를 순차적으로 재할당
            lines.append(str(i + 1))
            lines.append(f"{ts(scene.start_time)} --> {ts(scene.end_time)}")
            lines.append(scene.text.replace('\n', ' '))
            lines.append("")

        srt_text = "\n".join(lines)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(srt_text)
            print(f"[HybridV5] SRT 저장: {output_path}")

        return srt_text

    def _save_json(
        self,
        scenes: List[HybridSceneV5],
        whisper_result: WhisperResult,
        output_path: str,
        correction_changes: List[Dict] = None,
        validation_fixes: List[Dict] = None,
        final_corrections: List[Dict] = None
    ):
        """JSON 저장 (디버깅용)"""

        data = {
            "scenes": [asdict(s) for s in scenes],
            "statistics": {
                "total_scenes": len(scenes),
                "whisper_sentences": len(whisper_result.sentences),
                "audio_duration": whisper_result.duration,
                "device_used": self.device_used,
                "ai_model": "claude-agent" if self.use_claude_agent else self.ai_model,
                "corrections_made": len(correction_changes) if correction_changes else 0,
                "validation_fixes": len(validation_fixes) if validation_fixes else 0,
                "final_corrections": len(final_corrections) if final_corrections else 0
            },
            "correction_changes": correction_changes or [],
            "validation_fixes": validation_fixes or [],  # v5.3: 타임스탬프 수정 내역
            "final_corrections": final_corrections or [],  # v5.4: 최종 검증 교정 내역
            "version": "v5.4"
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[HybridV5] JSON 저장: {output_path}")

    def _validate_and_fix_scenes(
        self,
        scene_groups: List[SceneGroup],
        whisper_result: WhisperResult,
        max_chars: int
    ) -> List[SceneGroup]:
        """
        씬 글자수 검증 및 강제 분할 (최종 안전장치)

        Args:
            scene_groups: 씬 리스트
            whisper_result: WhisperResult
            max_chars: 최대 글자수

        Returns:
            검증/수정된 씬 리스트
        """
        validated = []
        split_count = 0

        for scene in scene_groups:
            if len(scene.text) > max_chars and len(scene.sentence_ids) > 1:
                # 글자수 초과 → 강제 분할
                split_scenes = self._force_split_scene(scene, whisper_result, max_chars)
                validated.extend(split_scenes)
                split_count += len(split_scenes) - 1
            else:
                validated.append(scene)

        if split_count > 0:
            print(f"[HybridV5] 📏 글자수 초과 씬 {split_count}개 추가 분할됨")

            # ID 재할당
            for i, scene in enumerate(validated):
                scene.scene_id = i + 1

        return validated

    def _force_split_scene(
        self,
        scene: SceneGroup,
        whisper_result: WhisperResult,
        max_chars: int
    ) -> List[SceneGroup]:
        """
        글자수 초과 씬을 강제로 분할

        Args:
            scene: 분할할 씬
            whisper_result: WhisperResult
            max_chars: 최대 글자수

        Returns:
            분할된 씬 리스트
        """
        result = []
        current_ids = []
        current_text = ""

        for sid in scene.sentence_ids:
            if sid >= len(whisper_result.sentences):
                continue

            sentence = whisper_result.sentences[sid]
            sentence_text = sentence.text

            # 현재 씬에 추가하면 초과하는지 체크
            test_text = (current_text + " " + sentence_text).strip() if current_text else sentence_text

            if len(test_text) > max_chars and current_ids:
                # 현재까지 모은 것으로 씬 생성
                text, start, end = whisper_result.merge_sentences(current_ids)
                result.append(SceneGroup(
                    scene_id=0,
                    sentence_ids=current_ids.copy(),
                    text=text,
                    start_time=start,
                    end_time=end,
                    mood=scene.mood if hasattr(scene, 'mood') else "",
                    scene_break_reason="글자수 초과 분할"
                ))
                # 새 씬 시작
                current_ids = [sid]
                current_text = sentence_text
            else:
                # 현재 씬에 추가
                current_ids.append(sid)
                current_text = test_text

        # 남은 문장 처리
        if current_ids:
            text, start, end = whisper_result.merge_sentences(current_ids)
            result.append(SceneGroup(
                scene_id=0,
                sentence_ids=current_ids,
                text=text,
                start_time=start,
                end_time=end,
                mood=scene.mood if hasattr(scene, 'mood') else "",
                scene_break_reason="글자수 초과 분할" if len(result) > 0 else (scene.scene_break_reason if hasattr(scene, 'scene_break_reason') else "")
            ))

        return result if result else [scene]


# ============================================================
# 레거시 호환성을 위한 클래스들
# ============================================================

# v4 호환성
class TTStoSRTHybridV4(TTStoSRTHybridV5):
    """레거시 호환 클래스 (v5.0으로 리다이렉트)"""
    pass


class TTStoSRTHybrid(TTStoSRTHybridV5):
    """레거시 호환 클래스"""
    pass


# v4 호환 데이터클래스
@dataclass
class HybridScene:
    """하이브리드 씬 (v4 호환)"""
    scene_id: int
    text: str
    start_time: float
    end_time: float
    duration: float
    timecode: str
    segment_ids: List[int]
    mood: str = ""
    scene_break_reason: str = ""

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def script_text(self) -> str:
        return self.text


# ============================================================
# 편의 함수
# ============================================================

def convert_tts_to_srt_v5(
    audio_path: str,
    original_script: str,
    language: str = "ko",
    split_style: str = "기본",
    whisper_model: str = "base",
    device_mode: str = "auto",
    ai_model: str = "gemini-2.5-flash",
    output_srt_path: str = None,
    output_json_path: str = None,
    progress_callback: Optional[Callable] = None
) -> Tuple[str, List[HybridSceneV5]]:
    """TTS -> SRT 변환 헬퍼 (v5.0 - 3단계 파이프라인)"""

    converter = TTStoSRTHybridV5(
        whisper_model=whisper_model,
        device_mode=device_mode,
        ai_provider="google",
        ai_model=ai_model
    )

    return converter.convert(
        audio_path=audio_path,
        original_script=original_script,
        language=language,
        split_style=split_style,
        output_srt_path=output_srt_path,
        output_json_path=output_json_path,
        progress_callback=progress_callback
    )


# v4 호환
def convert_tts_to_srt_v4(
    audio_path: str,
    language: str = "ko",
    split_style: str = "기본",
    whisper_model: str = "base",
    device_mode: str = "auto",
    ai_model: str = "gemini-2.5-flash",
    output_srt_path: str = None,
    output_json_path: str = None,
    progress_callback: Optional[Callable] = None
) -> Tuple[str, List[HybridScene]]:
    """TTS -> SRT 변환 헬퍼 (v4 호환 - 원문 없음)"""

    srt, scenes = convert_tts_to_srt_v5(
        audio_path=audio_path,
        original_script="",  # 원문 없음
        language=language,
        split_style=split_style,
        whisper_model=whisper_model,
        device_mode=device_mode,
        ai_model=ai_model,
        output_srt_path=output_srt_path,
        output_json_path=output_json_path,
        progress_callback=progress_callback
    )

    # v4 형식으로 변환
    v4_scenes = []
    for s in scenes:
        v4_scenes.append(HybridScene(
            scene_id=s.scene_id,
            text=s.text,
            start_time=s.start_time,
            end_time=s.end_time,
            duration=s.duration,
            timecode=s.timecode,
            segment_ids=s.sentence_ids,
            mood=s.mood,
            scene_break_reason=s.scene_break_reason
        ))

    return srt, v4_scenes


def convert_tts_to_srt_hybrid(
    audio_path: str,
    script_text: str = None,
    language: str = "ko",
    split_style: str = "기본",
    whisper_model: str = "base",
    device_mode: str = "auto",
    ai_model: str = "gemini-2.5-flash",
    output_srt_path: str = None,
    output_json_path: str = None,
    progress_callback: Optional[Callable] = None
) -> Tuple[str, List]:
    """TTS -> SRT 하이브리드 변환 헬퍼 함수 (레거시 호환)"""

    return convert_tts_to_srt_v5(
        audio_path=audio_path,
        original_script=script_text or "",
        language=language,
        split_style=split_style,
        whisper_model=whisper_model,
        device_mode=device_mode,
        ai_model=ai_model,
        output_srt_path=output_srt_path,
        output_json_path=output_json_path,
        progress_callback=progress_callback
    )
