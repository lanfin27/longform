# -*- coding: utf-8 -*-
"""
SRT 검증기 v5.4 - 빈 씬 디버깅 강화

⭐ 핵심 원칙 (v5.3+):
- 타임스탬프는 반드시 Whisper에서만 생성
- 원문은 오타 교정에만 사용 (타임스탬프 생성 금지!)
- 갭 복구 = Whisper 재분석 (원문 텍스트 삽입 절대 금지)

⭐ 기능:
1. 타임스탬프 역전 100% 수정
2. 중복 자막 100% 제거 (전역 중복 감지)
3. 최종 정렬 보장
4. 큰 갭 감지 및 경고만 (복구 안 함)
5. ⭐ v5.4: 빈 씬 상세 디버깅 (타임스탬프 출력)
"""

import re
from typing import List, Dict, Tuple, Set, Any, Optional
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass
class ValidationResult:
    """검증 결과"""
    empty_removed: int = 0
    reversed_fixed: int = 0
    overlaps_fixed: int = 0
    gaps_detected: int = 0
    gaps_recovered: int = 0      # v5.0 추가
    scenes_inserted: int = 0     # v5.0 추가
    duplicates_removed: int = 0
    reordered: bool = False


@dataclass
class SRTEntry:
    """SRT 항목"""
    index: int
    start_time: float  # 초 단위
    end_time: float
    text: str

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_srt_timecode(self, seconds: float) -> str:
        """초를 SRT 타임코드로 변환"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def to_srt_block(self) -> str:
        """SRT 블록 문자열 생성"""
        start_tc = self.to_srt_timecode(self.start_time)
        end_tc = self.to_srt_timecode(self.end_time)
        return f"{self.index}\n{start_tc} --> {end_tc}\n{self.text}\n"


class SRTValidator:
    """SRT 검증기 v5.3 - 원문 기반 갭 복구 완전 제거"""

    # 최소 자막 표시 시간
    MIN_DURATION = 0.3  # 0.3초

    # 최대 갭 (이 이상 차이나면 경고)
    MAX_GAP_WARNING = 5.0  # 5초

    # 최소 간격
    MIN_GAP = 0.001  # 1ms

    # v5.3: 갭 감지 임계값 (감지만, 복구 안 함)
    GAP_DETECTION_THRESHOLD = 5.0

    def __init__(self):
        print(f"[SRTValidator] v5.4 초기화 (빈 씬 디버깅 강화)")
        print(f"[SRTValidator] ℹ️ 갭 복구는 Whisper 재분석에서 처리됨")
        self.issues_found: List[Dict] = []
        self.fixes_applied: List[Dict] = []
        self.stats = {}

    def validate_and_fix(
        self,
        scenes: List[Any],
        total_duration: float = None,
        original_script: str = None,
        audio_duration: float = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        SRT 검증 및 수정 (v5.0)

        ⭐ 수정 순서 (순서 중요!):
        1. 빈 텍스트 씬 제거
        2. 타임스탬프 파싱 및 정규화
        3. 시간순 정렬 (⭐ 먼저 정렬!)
        4. 중복 텍스트 제거 (⭐ 전역 중복 감지!)
        5. ⭐ 큰 갭 감지 및 원문 기반 복구 (v5.0 NEW!)
        6. 타임스탬프 역전 수정
        7. 타임스탬프 겹침 수정
        8. scene_id 재할당
        9. 최종 검증

        Returns:
            (수정된 scenes 리스트, 수정 내역 리스트)
        """

        self.issues_found = []
        self.fixes_applied = []
        self.stats = {
            'input_count': len(scenes) if scenes else 0,
            'empty_removed': 0,
            'duplicates_removed': 0,
            'gaps_recovered': 0,      # v5.0 추가
            'scenes_inserted': 0,     # v5.0 추가
            'reversed_fixed': 0,
            'overlap_fixed': 0,
            'final_count': 0
        }

        if not scenes:
            return [], []

        print(f"\n{'='*60}")
        print(f"[SRTValidator] v5.4 검증 시작: {len(scenes)}개 씬")
        print(f"{'='*60}")

        # 씬을 dict 리스트로 변환
        working_scenes = self._to_dict_list(scenes)

        # ============================================================
        # Step 1: 빈 텍스트 씬 체크 (⭐ v5.4: 제거 대신 경고만!)
        # ============================================================
        empty_count = self._check_empty_scenes(working_scenes)
        self.stats['empty_count'] = empty_count

        if empty_count > 0:
            print(f"[SRTValidator] Step 1: ⚠️ 빈 씬 {empty_count}개 발견 (제거하지 않음!)")
            print(f"[SRTValidator] ℹ️ 이전 단계(AISceneMerger/TextCorrector)에서 빈 텍스트가 발생했습니다.")
            self.fixes_applied.append({
                "type": "empty_scenes_warning",
                "count": empty_count
            })
        else:
            print(f"[SRTValidator] Step 1: ✅ 빈 씬 없음")

        if not working_scenes:
            return [], self.fixes_applied

        # ============================================================
        # Step 2: 타임스탬프 파싱
        # ============================================================
        for scene in working_scenes:
            scene['_start_seconds'] = self._get_start_time(scene)
            scene['_end_seconds'] = self._get_end_time(scene)

        # ============================================================
        # Step 3: 시간순 정렬 (⭐ 핵심!)
        # ============================================================
        original_order = [s.get("scene_id", i) for i, s in enumerate(working_scenes)]
        working_scenes.sort(key=lambda x: x['_start_seconds'])
        new_order = [s.get("scene_id", i) for i, s in enumerate(working_scenes)]

        was_reordered = original_order != new_order
        if was_reordered:
            print(f"[SRTValidator] Step 3: 시간순 재정렬됨")
            self.stats['reordered'] = True

        # ============================================================
        # Step 4: 중복 텍스트 제거 (⭐ 전역 중복 감지!)
        # ============================================================
        before_count = len(working_scenes)
        working_scenes = self._remove_global_duplicates(working_scenes)
        self.stats['duplicates_removed'] = before_count - len(working_scenes)

        if self.stats['duplicates_removed'] > 0:
            print(f"[SRTValidator] Step 4: 중복 {self.stats['duplicates_removed']}개 제거 → {len(working_scenes)}개 남음")
            self.fixes_applied.append({
                "type": "duplicates_removed",
                "count": self.stats['duplicates_removed']
            })

        # ============================================================
        # ⭐ Step 5: 큰 갭 감지 및 경고 (v5.3 - 복구 안 함!)
        # ============================================================
        # 원문 기반 갭 복구 완전 제거 - 갭 감지 및 경고만 수행
        # 실제 갭 복구는 WhisperTimestamp의 Whisper 재분석에서 처리됨
        self._check_gaps_and_warn(
            working_scenes,
            audio_duration or total_duration
        )

        # ============================================================
        # Step 6: 타임스탬프 역전 수정
        # ============================================================
        working_scenes, reversed_count = self._fix_reversed_timestamps(working_scenes)
        self.stats['reversed_fixed'] = reversed_count

        if reversed_count > 0:
            print(f"[SRTValidator] Step 6: 역전 {reversed_count}개 수정")
            self.fixes_applied.append({
                "type": "reversed_fixed",
                "count": reversed_count
            })

        # ============================================================
        # Step 7: 타임스탬프 겹침 수정
        # ============================================================
        working_scenes, overlap_count = self._fix_overlaps(working_scenes)
        self.stats['overlap_fixed'] = overlap_count

        if overlap_count > 0:
            print(f"[SRTValidator] Step 7: 겹침 {overlap_count}개 수정")
            self.fixes_applied.append({
                "type": "overlaps_fixed",
                "count": overlap_count
            })

        # ============================================================
        # Step 8: scene_id 재할당 및 타임스탬프 정규화
        # ============================================================
        for i, scene in enumerate(working_scenes):
            scene['scene_id'] = i + 1

            # ⭐ v5.5: start_time/end_time 필드 보장 (hybrid_srt_generator가 사용)
            # _start_seconds/_end_seconds 값을 start_time/end_time에 복사
            if '_start_seconds' in scene:
                scene['start_time'] = scene['_start_seconds']
            if '_end_seconds' in scene:
                scene['end_time'] = scene['_end_seconds']

            # start/end 키만 있는 경우도 처리
            if 'start_time' not in scene and 'start' in scene:
                scene['start_time'] = self._ensure_float_time(scene['start'])
            if 'end_time' not in scene and 'end' in scene:
                scene['end_time'] = self._ensure_float_time(scene['end'])

            # 임시 필드 제거
            scene.pop('_start_seconds', None)
            scene.pop('_end_seconds', None)

        # ============================================================
        # Step 9: 최종 검증
        # ============================================================
        self.stats['final_count'] = len(working_scenes)

        # 최종 역전 체크
        final_reversals = 0
        for i in range(len(working_scenes) - 1):
            current_start = self._get_start_time(working_scenes[i])
            next_start = self._get_start_time(working_scenes[i+1])
            if current_start > next_start:
                final_reversals += 1

        print(f"\n{'='*60}")
        print(f"[SRTValidator] v5.3 검증 완료 (원문 기반 갭 복구: 비활성화)")
        print(f"{'='*60}")
        print(f"  입력: {self.stats['input_count']}개")
        print(f"  빈 씬 제거: {self.stats['empty_removed']}개")
        print(f"  중복 제거: {self.stats['duplicates_removed']}개")
        print(f"  ⚠️ 감지된 갭: {self.stats.get('gaps_detected', 0)}개 (Whisper 재분석 필요)")
        print(f"  역전 수정: {self.stats['reversed_fixed']}개")
        print(f"  겹침 수정: {self.stats['overlap_fixed']}개")
        print(f"  최종: {self.stats['final_count']}개")
        print(f"  남은 역전: {final_reversals}개")
        print(f"{'='*60}\n")

        if final_reversals > 0:
            print(f"[SRTValidator] ⚠️ 경고: 여전히 {final_reversals}개 역전 존재!")

        return working_scenes, self.fixes_applied

    def validate(self, scenes: List[Dict], original_script: str = None,
                 audio_duration: float = None) -> Tuple[List[Dict], ValidationResult]:
        """
        v3 호환 인터페이스 - validate_and_fix 래핑
        """
        validated_scenes, fixes = self.validate_and_fix(
            scenes,
            original_script=original_script,
            audio_duration=audio_duration
        )

        result = ValidationResult(
            empty_removed=self.stats.get('empty_removed', 0),
            reversed_fixed=self.stats.get('reversed_fixed', 0),
            overlaps_fixed=self.stats.get('overlap_fixed', 0),
            gaps_detected=self.stats.get('gaps_detected', 0),
            gaps_recovered=self.stats.get('gaps_recovered', 0),      # v5.0 추가
            scenes_inserted=self.stats.get('scenes_inserted', 0),    # v5.0 추가
            duplicates_removed=self.stats.get('duplicates_removed', 0),
            reordered=self.stats.get('reordered', False)
        )

        return validated_scenes, result

    def _to_dict_list(self, scenes: List[Any]) -> List[Dict]:
        """씬 리스트를 dict 리스트로 변환 (새 객체 생성)"""
        result = []

        for i, scene in enumerate(scenes):
            if isinstance(scene, dict):
                # 새 딕셔너리로 복사 (원본 수정 방지)
                new_scene = {}
                for key in scene:
                    new_scene[key] = scene[key]
                result.append(new_scene)
            else:
                # dataclass나 객체인 경우
                scene_dict = {
                    "scene_id": getattr(scene, "scene_id", i + 1),
                    "start_time": getattr(scene, "start_time", 0),
                    "end_time": getattr(scene, "end_time", 0),
                    "text": getattr(scene, "text", ""),
                }
                # 추가 속성 복사
                for attr in ['start', 'end', 'sentence_ids', 'original_text', 'char_count']:
                    if hasattr(scene, attr):
                        scene_dict[attr] = getattr(scene, attr)
                result.append(scene_dict)

        return result

    def _get_start_time(self, scene: Dict) -> float:
        """씬의 시작 시간 가져오기 (타입 안전)"""
        value = scene.get("start_time", scene.get("start", 0))
        return self._ensure_float_time(value)

    def _get_end_time(self, scene: Dict) -> float:
        """씬의 종료 시간 가져오기 (타입 안전)"""
        value = scene.get("end_time", scene.get("end", 0))
        return self._ensure_float_time(value)

    def _ensure_float_time(self, time_value) -> float:
        """
        시간 값을 확실히 float으로 변환 (방어적 함수)

        Args:
            time_value: float, int, 또는 SRT 타임코드 문자열

        Returns:
            float 초 단위 시간
        """
        if time_value is None:
            return 0.0

        if isinstance(time_value, (int, float)):
            return float(time_value)

        if isinstance(time_value, str):
            return self._srt_time_to_seconds(time_value)

        # 알 수 없는 타입
        print(f"[SRTValidator] ⚠️ 알 수 없는 시간 타입: {type(time_value).__name__}")
        return 0.0

    def _srt_time_to_seconds(self, srt_time: str) -> float:
        """
        SRT 시간 포맷을 초(float)로 변환

        예: "00:10:16,570" -> 616.57
            "01:23,456" -> 83.456
        """
        if not srt_time or not isinstance(srt_time, str):
            return 0.0

        try:
            # "00:10:16,570" 형식 파싱
            srt_time = srt_time.replace(',', '.')
            parts = srt_time.split(':')

            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                minutes = int(parts[0])
                seconds = float(parts[1])
                return minutes * 60 + seconds
            else:
                return float(srt_time)
        except (ValueError, IndexError) as e:
            print(f"[SRTValidator] ⚠️ 시간 파싱 오류: '{srt_time}' - {e}")
            return 0.0

    def _set_start_time(self, scene: Dict, value: float):
        """씬의 시작 시간 설정"""
        if "start_time" in scene:
            scene["start_time"] = value
        if "start" in scene:
            scene["start"] = value
        if "start_time" not in scene and "start" not in scene:
            scene["start_time"] = value

    def _set_end_time(self, scene: Dict, value: float):
        """씬의 종료 시간 설정"""
        if "end_time" in scene:
            scene["end_time"] = value
        if "end" in scene:
            scene["end"] = value
        if "end_time" not in scene and "end" not in scene:
            scene["end_time"] = value

    def _check_empty_scenes(self, scenes: List[Dict]) -> int:
        """
        빈 텍스트 씬 체크 (⭐ v5.4: 제거하지 않고 경고만!)

        원칙: 빈 씬이 있으면 이전 단계에 문제가 있는 것!
        제거하면 갭이 발생하므로 근본 원인을 수정해야 함.
        """
        empty_scenes = []

        for scene in scenes:
            text = scene.get("text", "")
            if text is None:
                text = ""
            text = str(text).strip()

            if not text or len(text) == 0:
                empty_scenes.append(scene)

        # ⭐ v5.4: 빈 씬 디버깅 로그
        if empty_scenes:
            print(f"[SRTValidator] ⚠️ 빈 씬 {len(empty_scenes)}개 상세 (타임스탬프 정보):")
            for i, scene in enumerate(empty_scenes[:10]):
                start = self._get_start_time(scene)
                end = self._get_end_time(scene)
                scene_id = scene.get('scene_id', '?')
                print(f"  [{i+1}] scene_id={scene_id}, {start:.2f}~{end:.2f}초")
            if len(empty_scenes) > 10:
                print(f"  ... 외 {len(empty_scenes) - 10}개")

        return len(empty_scenes)

    def _remove_empty_scenes(self, scenes: List[Dict]) -> List[Dict]:
        """
        빈 텍스트 씬 제거 (⚠️ DEPRECATED - 사용하지 마세요!)

        v5.4: 이 메서드는 더 이상 사용되지 않습니다.
        빈 씬 제거는 갭을 발생시키므로 _check_empty_scenes로 대체됨.
        """
        print(f"[SRTValidator] ⚠️ _remove_empty_scenes는 deprecated입니다!")
        return scenes  # 제거하지 않고 그대로 반환

    def _normalize_text(self, text: str) -> str:
        """텍스트 정규화 (비교용)"""
        if not text:
            return ""
        # 소문자 변환, 공백 제거, 특수문자 제거
        normalized = text.lower()
        normalized = re.sub(r'\s+', '', normalized)
        normalized = re.sub(r'[^\w가-힣]', '', normalized)
        return normalized

    def _text_similarity(self, text1: str, text2: str) -> float:
        """두 텍스트의 유사도 (0.0 ~ 1.0)"""
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1, text2).ratio()

    def _remove_global_duplicates(self, scenes: List[Dict]) -> Tuple[List[Dict], int]:
        """
        전역 중복 텍스트 제거 (v4.0 핵심!)

        이전 버전은 연속 중복만 제거했지만,
        v4.0은 전체 리스트에서 중복을 감지하고 첫 번째만 유지합니다.
        """
        if not scenes:
            return scenes

        deduplicated = []
        seen_texts: Set[str] = set()
        removed_count = 0

        for scene in scenes:
            text = scene.get('text', '').strip()
            normalized = self._normalize_text(text)

            # 빈 텍스트 스킵
            if not normalized:
                continue

            # 완전 중복 체크
            if normalized in seen_texts:
                removed_count += 1
                if removed_count <= 10:
                    text_preview = text[:40] + "..." if len(text) > 40 else text
                    print(f"  [SRTValidator] 🗑️ 중복 제거: {text_preview}")
                continue

            # 유사 중복 체크 (85% 이상 유사)
            is_similar = False
            for seen in seen_texts:
                if self._text_similarity(normalized, seen) > 0.85:
                    is_similar = True
                    removed_count += 1
                    if removed_count <= 10:
                        text_preview = text[:40] + "..." if len(text) > 40 else text
                        print(f"  [SRTValidator] 🗑️ 유사 중복 제거: {text_preview}")
                    break

            if not is_similar:
                seen_texts.add(normalized)
                deduplicated.append(scene)

        if removed_count > 10:
            print(f"  [SRTValidator] ... 외 {removed_count - 10}개 중복 제거됨")

        return deduplicated

    def _fix_reversed_timestamps(self, scenes: List[Dict]) -> Tuple[List[Dict], int]:
        """타임스탬프 역전 수정"""
        fixed_count = 0

        for scene in scenes:
            start = scene.get('_start_seconds', self._get_start_time(scene))
            end = scene.get('_end_seconds', self._get_end_time(scene))
            scene_id = scene.get("scene_id", "?")

            # 음수 수정
            if start < 0:
                self._set_start_time(scene, 0)
                scene['_start_seconds'] = 0
                fixed_count += 1
                start = 0

            if end < 0:
                new_end = start + self.MIN_DURATION
                self._set_end_time(scene, new_end)
                scene['_end_seconds'] = new_end
                fixed_count += 1
                end = new_end

            # start > end 수정
            if start >= end:
                # 텍스트 길이 기반 duration 추정
                text_len = len(scene.get('text', ''))
                estimated_duration = max(1.0, min(5.0, text_len * 0.08))
                new_end = start + estimated_duration

                self._set_end_time(scene, new_end)
                scene['_end_seconds'] = new_end
                fixed_count += 1

                if fixed_count <= 10:
                    print(f"  [SRTValidator] 🔧 역전 수정: 씬 #{scene_id}")

        return scenes, fixed_count

    def _fix_overlaps(self, scenes: List[Dict]) -> Tuple[List[Dict], int]:
        """겹침 수정"""
        fixed_count = 0

        for i in range(len(scenes) - 1):
            current = scenes[i]
            next_scene = scenes[i + 1]

            current_end = current.get('_end_seconds', self._get_end_time(current))
            next_start = next_scene.get('_start_seconds', self._get_start_time(next_scene))

            if current_end > next_start:
                # 겹침 수정: current.end를 next.start 직전으로
                new_end = next_start - self.MIN_GAP
                current_start = current.get('_start_seconds', self._get_start_time(current))

                # 최소 duration 보장
                min_end = current_start + self.MIN_DURATION
                if new_end < min_end:
                    new_end = min_end

                self._set_end_time(current, new_end)
                current['_end_seconds'] = new_end
                fixed_count += 1

        return scenes, fixed_count

    # ================================================================
    # ⭐ v5.1: 갭 감지 경고 메서드 (복구는 Whisper 단계에서 처리)
    # ================================================================

    def _check_gaps_and_warn(self, scenes: List[Dict],
                             audio_duration: float = None) -> None:
        """
        Step 5: 큰 갭 감지 및 경고만 출력 (v5.3)

        ⭐ 원문 기반 갭 복구 완전 제거!
        - 이 단계에서는 갭 감지 및 경고만 출력
        - 실제 갭 복구는 WhisperTimestamp에서 Whisper 재분석으로 처리
        - 타임스탬프는 반드시 Whisper에서만 생성되어야 함
        """
        if len(scenes) < 2:
            print(f"[SRTValidator] Step 5: 씬 수 부족, 갭 검사 스킵")
            return

        # 갭 감지
        gaps_found = []

        for i in range(len(scenes) - 1):
            current_end = scenes[i].get('_end_seconds', self._get_end_time(scenes[i]))
            next_start = scenes[i + 1].get('_start_seconds', self._get_start_time(scenes[i + 1]))
            gap = next_start - current_end

            if gap >= self.GAP_DETECTION_THRESHOLD:
                gaps_found.append({
                    'start_time': current_end,
                    'end_time': next_start,
                    'gap_seconds': gap
                })

        if not gaps_found:
            print(f"[SRTValidator] Step 5: ✅ 큰 갭 없음 (>{self.GAP_DETECTION_THRESHOLD}초)")
            return

        # 경고만 출력 (복구하지 않음 - Whisper 재분석에서 처리)
        total_gap = sum(g['gap_seconds'] for g in gaps_found)
        print(f"\n[SRTValidator] Step 5: ⚠️ {len(gaps_found)}개 빈 구간 감지됨 (총 {total_gap:.1f}초)")
        print(f"[SRTValidator] ℹ️ 갭 복구는 Whisper 재분석에서 처리됨 (원문 기반 삽입 안 함)")

        for i, gap in enumerate(gaps_found):
            start_str = self._format_time_full(gap['start_time'])
            end_str = self._format_time_full(gap['end_time'])
            print(f"  [{i+1}] {start_str} ~ {end_str} ({gap['gap_seconds']:.1f}초)")

        self.stats['gaps_detected'] = len(gaps_found)

    # ================================================================
    # ❌ v5.3: 갭 복구 메서드 완전 비활성화
    # ================================================================
    #
    # ⚠️ 아래 메서드들은 v5.3에서 완전 비활성화됨
    # 원문 기반 타임스탬프 생성은 싱크 문제를 일으킴
    # 갭 복구는 WhisperTimestamp에서 Whisper 재분석으로 처리해야 함
    #
    # ================================================================

    def _recover_gaps(self, scenes: List[Dict], original_script: str,
                      audio_duration: float = None) -> List[Dict]:
        """
        ❌ [DEPRECATED] v5.3에서 완전 비활성화

        원문 기반 갭 복구는 싱크 문제를 일으키므로 사용하지 않음!
        갭 복구는 WhisperTimestamp에서 Whisper 재분석으로 처리해야 함

        이 메서드는 호출되지 않지만 레거시 호환성을 위해 유지됨
        """
        print(f"[SRTValidator] ⚠️ _recover_gaps 호출됨 - v5.3에서 비활성화됨!")
        print(f"[SRTValidator] ℹ️ 갭 복구는 Whisper 재분석에서 처리됨")
        return scenes  # 아무것도 하지 않고 반환

    # ❌ v5.3: 아래 헬퍼 메서드들은 비활성화됨 (레거시 호환성 유지)

    def _find_missing_texts(self, original_sentences: List[str],
                            prev_text: str, next_text: str) -> List[str]:
        """❌ [DEPRECATED] v5.3에서 비활성화 - 원문 기반 갭 복구 제거"""
        print(f"[SRTValidator] ⚠️ _find_missing_texts 호출됨 - v5.3에서 비활성화!")
        return []  # 빈 리스트 반환

    def _create_scenes_for_gap(self, texts: List[str],
                               start_time: float, end_time: float) -> List[Dict]:
        """❌ [DEPRECATED] v5.3에서 비활성화 - 원문 기반 씬 생성 제거"""
        print(f"[SRTValidator] ⚠️ _create_scenes_for_gap 호출됨 - v5.3에서 비활성화!")
        return []  # 빈 리스트 반환

    def _split_sentences(self, text: str) -> List[str]:
        """텍스트를 문장 단위로 분리"""
        # 줄바꿈으로 먼저 분리
        lines = text.split('\n')

        result = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 마침표, 물음표, 느낌표로 분리
            sentences = re.split(r'(?<=[.?!。])\s*', line)
            for sent in sentences:
                sent = sent.strip()
                if sent and len(sent) > 5:
                    result.append(sent)

        return result

    def _format_time_full(self, seconds: float) -> str:
        """초를 HH:MM:SS,mmm 형식으로 변환"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _format_time(self, seconds: float) -> str:
        """초를 MM:SS 형식으로 변환"""
        if seconds < 0:
            seconds = 0
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def generate_srt(self, scenes: List[Any]) -> str:
        """씬 리스트에서 SRT 텍스트 생성 (최종 정렬 포함)"""

        dict_scenes = self._to_dict_list(scenes)

        # ⭐ 최종 정렬!
        dict_scenes.sort(key=lambda x: self._get_start_time(x))

        srt_blocks = []
        for i, scene in enumerate(dict_scenes):
            entry = SRTEntry(
                index=i + 1,
                start_time=self._get_start_time(scene),
                end_time=self._get_end_time(scene),
                text=scene.get("text", "")
            )
            srt_blocks.append(entry.to_srt_block())

        return "\n".join(srt_blocks)


# ============================================================
# 팩토리 함수
# ============================================================

# 싱글톤 인스턴스
_validator = None

def get_srt_validator() -> SRTValidator:
    """SRTValidator 싱글톤 인스턴스 반환"""
    global _validator
    if _validator is None:
        _validator = SRTValidator()
    return _validator


def validate_and_fix_srt(scenes: List[Any], total_duration: float = None,
                         original_script: str = None) -> Tuple[List[Any], List[Dict]]:
    """편의 함수: SRT 검증 및 수정"""
    validator = get_srt_validator()
    return validator.validate_and_fix(scenes, total_duration, original_script=original_script)


# ============================================================
# 독립 실행용 함수
# ============================================================

def parse_srt_file(path: str) -> List[Dict]:
    """SRT 파일 파싱"""
    scenes = []

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # SRT 블록 분리
    blocks = re.split(r'\n\n+', content.strip())

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            try:
                scene_id = int(lines[0])
                time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
                if time_match:
                    start_time_str = time_match.group(1)
                    end_time_str = time_match.group(2)

                    # 타임스탬프를 초로 변환
                    def parse_ts(ts):
                        ts = ts.replace(',', '.')
                        parts = ts.split(':')
                        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

                    start_time = parse_ts(start_time_str)
                    end_time = parse_ts(end_time_str)
                    text = '\n'.join(lines[2:])

                    scenes.append({
                        'scene_id': scene_id,
                        'start_time': start_time,
                        'end_time': end_time,
                        'text': text
                    })
            except:
                continue

    return scenes


def save_srt_file(scenes: List[Dict], path: str):
    """SRT 파일 저장 (⭐ 최종 정렬 포함)"""

    def ensure_float(time_val) -> float:
        """시간 값을 float으로 변환 (로컬 헬퍼)"""
        if time_val is None:
            return 0.0
        if isinstance(time_val, (int, float)):
            return float(time_val)
        if isinstance(time_val, str):
            try:
                time_val = time_val.replace(',', '.')
                parts = time_val.split(':')
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                elif len(parts) == 2:
                    return int(parts[0]) * 60 + float(parts[1])
                else:
                    return float(time_val)
            except:
                return 0.0
        return 0.0

    # 시간순 정렬 (타입 안전)
    sorted_scenes = sorted(scenes, key=lambda x: ensure_float(x.get('start_time', x.get('start', 0))))

    def ts(seconds: float) -> str:
        seconds = ensure_float(seconds)  # 안전 변환
        if seconds < 0:
            seconds = 0
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(path, 'w', encoding='utf-8') as f:
        for i, scene in enumerate(sorted_scenes):
            start = ensure_float(scene.get('start_time', scene.get('start', 0)))
            end = ensure_float(scene.get('end_time', scene.get('end', 0)))
            text = scene.get('text', '')

            f.write(f"{i + 1}\n")
            f.write(f"{ts(start)} --> {ts(end)}\n")
            f.write(f"{text}\n")
            f.write("\n")

    print(f"[SRTValidator] SRT 저장 완료: {path} ({len(sorted_scenes)}개 씬)")


def fix_srt_file(input_path: str, output_path: str = None) -> str:
    """
    SRT 파일 직접 수정

    Args:
        input_path: 입력 SRT 파일 경로
        output_path: 출력 경로 (없으면 원본 덮어쓰기)

    Returns:
        출력 파일 경로
    """
    import os

    if not output_path:
        output_path = input_path

    # SRT 파싱
    scenes = parse_srt_file(input_path)
    print(f"[fix_srt_file] 입력: {len(scenes)}개 씬")

    # 검증 및 수정
    validator = SRTValidator()
    fixed_scenes, stats = validator.validate_and_fix(scenes)

    # 저장
    save_srt_file(fixed_scenes, output_path)
    print(f"[fix_srt_file] 출력: {output_path}")

    return output_path
