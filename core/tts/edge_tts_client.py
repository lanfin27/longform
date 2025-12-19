"""
Edge TTS 클라이언트

Edge TTS를 활용한 음성 생성
문단별 무음 패딩 자동 삽입
"""
import edge_tts
import asyncio
from pathlib import Path
import json
import re
from typing import Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import TTS_VOICES, TTS_DEFAULT_RATE, TTS_DEFAULT_SILENCE_MS
from core.tts.silence_padder import SilencePadder, ms_to_srt_time, srt_time_to_ms


class EdgeTTSClient:
    """
    Edge TTS 클라이언트

    특징:
    - 무료 고품질 TTS
    - 다양한 음성 지원 (한국어, 일본어)
    - 문단별 무음 패딩 자동 삽입
    - SRT 자막 자동 생성
    """

    def __init__(self):
        self.silence_padder = SilencePadder()

    def _feed_submaker(self, submaker, chunk: Dict):
        """
        SubMaker에 WordBoundary 데이터 추가 (버전 호환)

        edge-tts API 버전에 따라 다른 메서드 사용:
        - 구버전: submaker.feed(chunk)
        - 신버전: submaker.create_sub((offset, duration), text)
        """
        try:
            # 방법 1: feed() 메서드 (구버전)
            if hasattr(submaker, 'feed'):
                try:
                    submaker.feed(chunk)
                    return
                except (TypeError, AttributeError):
                    pass

            # 방법 2: create_sub() 메서드 (신버전)
            if hasattr(submaker, 'create_sub'):
                try:
                    offset = chunk.get("offset", 0)
                    duration = chunk.get("duration", 0)
                    text = chunk.get("text", "")
                    submaker.create_sub((offset, duration), text)
                    return
                except (TypeError, AttributeError):
                    pass

            # 방법 3: add() 메서드
            if hasattr(submaker, 'add'):
                try:
                    submaker.add(chunk)
                    return
                except (TypeError, AttributeError):
                    pass

        except Exception as e:
            print(f"[EdgeTTS] SubMaker.feed 실패: {e}")

    def _get_srt_content(self, submaker) -> str:
        """
        SubMaker에서 SRT/VTT 내용 추출 (버전 호환)

        여러 API 버전에 대응:
        - generate_subs() (구버전)
        - get_srt() / get_vtt()
        - __str__()
        - subs 속성 직접 접근
        """
        # 방법 1: generate_subs() 메서드 (구버전)
        if hasattr(submaker, 'generate_subs'):
            try:
                result = submaker.generate_subs()
                if result:
                    return result
            except Exception as e:
                print(f"[EdgeTTS] generate_subs() 실패: {e}")

        # 방법 2: get_srt() 메서드
        if hasattr(submaker, 'get_srt'):
            try:
                result = submaker.get_srt()
                if result:
                    return result
            except Exception as e:
                print(f"[EdgeTTS] get_srt() 실패: {e}")

        # 방법 3: get_vtt() 메서드
        if hasattr(submaker, 'get_vtt'):
            try:
                result = submaker.get_vtt()
                if result:
                    return result
            except Exception as e:
                print(f"[EdgeTTS] get_vtt() 실패: {e}")

        # 방법 4: __str__() 메서드
        try:
            result = str(submaker)
            if result and result.strip() and result != "<SubMaker>":
                return result
        except Exception as e:
            print(f"[EdgeTTS] str(submaker) 실패: {e}")

        # 방법 5: subs 속성에서 직접 생성
        if hasattr(submaker, 'subs') and submaker.subs:
            try:
                return self._build_srt_from_submaker_subs(submaker.subs)
            except Exception as e:
                print(f"[EdgeTTS] subs 속성 접근 실패: {e}")

        # 방법 6: _subs 속성 (내부)
        if hasattr(submaker, '_subs') and submaker._subs:
            try:
                return self._build_srt_from_submaker_subs(submaker._subs)
            except Exception as e:
                print(f"[EdgeTTS] _subs 속성 접근 실패: {e}")

        print("[EdgeTTS] 자막 생성 실패 - SubMaker에서 데이터를 추출할 수 없음")
        return ""

    def _build_srt_from_submaker_subs(self, subs: list) -> str:
        """
        SubMaker의 subs 리스트에서 SRT 형식 문자열 생성
        """
        srt_lines = []

        for i, sub in enumerate(subs, 1):
            try:
                # sub 형식: ((start_time, duration), text) 또는 유사 구조
                if isinstance(sub, tuple) and len(sub) >= 2:
                    timing = sub[0]
                    text = sub[1]

                    if isinstance(timing, tuple) and len(timing) >= 2:
                        # 100ns 단위를 ms로 변환
                        start_ms = timing[0] / 10000
                        duration_ms = timing[1] / 10000
                        end_ms = start_ms + duration_ms

                        start_time = ms_to_srt_time(start_ms)
                        end_time = ms_to_srt_time(end_ms)

                        srt_lines.append(str(i))
                        srt_lines.append(f"{start_time} --> {end_time}")
                        srt_lines.append(str(text))
                        srt_lines.append("")
            except Exception as e:
                print(f"[EdgeTTS] sub 파싱 실패: {e}")
                continue

        return "\n".join(srt_lines)

    @classmethod
    def get_voices(cls, language: str) -> List[Dict]:
        """
        언어별 사용 가능한 음성 목록 반환

        Args:
            language: 언어 코드 ("ko" 또는 "ja")

        Returns:
            음성 정보 딕셔너리 리스트
        """
        return TTS_VOICES.get(language, TTS_VOICES["ko"])

    async def generate_audio_with_silence(
        self,
        text: str,
        voice: str,
        output_path: str,
        rate: str = None,
        pitch: str = "+0Hz",
        volume: str = "+0%",
        add_silence: bool = True,
        silence_ms: int = None
    ) -> Dict:
        """
        TTS 생성 + 문단별 무음 패딩 추가

        Args:
            text: 스크립트 텍스트
            voice: 음성 ID (예: "ko-KR-SunHiNeural")
            output_path: 출력 파일 경로
            rate: 속도 (예: "-10%")
            pitch: 피치 (예: "+0Hz")
            volume: 볼륨 (예: "+0%")
            add_silence: 문단 무음 패딩 추가 여부
            silence_ms: 무음 길이 (밀리초)

        Returns:
            {
                "audio_path": str,
                "srt_path": str,
                "paragraph_count": int (무음 패딩 시),
                "total_silence_ms": int (무음 패딩 시)
            }
        """
        rate = rate or TTS_DEFAULT_RATE
        silence_ms = silence_ms or TTS_DEFAULT_SILENCE_MS

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        srt_path = output_path.with_suffix(".srt")

        # 1. Edge TTS로 기본 오디오 생성
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=volume
        )

        # 자막 생성기
        submaker = edge_tts.SubMaker()
        word_boundaries = []

        # 오디오 생성
        with open(output_path, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    # WordBoundary 데이터 저장
                    word_boundaries.append({
                        "offset": chunk.get("offset", 0),
                        "duration": chunk.get("duration", 0),
                        "text": chunk.get("text", "")
                    })
                    # SubMaker에 데이터 추가 (버전 호환)
                    self._feed_submaker(submaker, chunk)

        # SRT 저장 (버전 호환)
        vtt_content = self._get_srt_content(submaker)

        if vtt_content and vtt_content.strip():
            # VTT를 SRT로 변환
            srt_content = self._vtt_to_srt(vtt_content)
            with open(srt_path, "w", encoding="utf-8") as srt_file:
                srt_file.write(srt_content)
        elif word_boundaries:
            # WordBoundary에서 직접 SRT 생성
            srt_content = self._create_srt_from_boundaries(word_boundaries, text)
            with open(srt_path, "w", encoding="utf-8") as srt_file:
                srt_file.write(srt_content)
        else:
            # 기본 SRT 생성 (텍스트를 문장 단위로 분할)
            srt_content = self._create_fallback_srt(text)
            with open(srt_path, "w", encoding="utf-8") as srt_file:
                srt_file.write(srt_content)

        result = {
            "audio_path": str(output_path),
            "srt_path": str(srt_path)
        }

        # 2. 무음 패딩 추가 (옵션)
        if add_silence:
            self.silence_padder.silence_duration = silence_ms

            # 문단 구분점 감지
            breaks = self.silence_padder.detect_paragraph_breaks(text)

            if breaks:
                # SRT 파싱
                srt_segments = self._parse_srt(srt_path)

                # 문단 구분점의 타이밍 찾기
                paragraph_timings = self._find_paragraph_timings(
                    text, srt_segments, breaks
                )

                if paragraph_timings:
                    # 오디오에 무음 삽입
                    self.silence_padder.add_silence_to_audio(
                        str(output_path),
                        paragraph_timings
                    )

                    # SRT 타임스탬프 조정
                    adjusted_segments = self.silence_padder.adjust_srt_for_silence(
                        srt_segments,
                        paragraph_timings
                    )
                    self._write_srt(adjusted_segments, srt_path)

                    # 문단 정보 저장
                    paragraph_info = {
                        "silence_duration_ms": silence_ms,
                        "breaks": paragraph_timings,
                        "total_silence_ms": self.silence_padder.calculate_total_silence(paragraph_timings)
                    }

                    paragraph_info_path = output_path.parent / "paragraph_breaks.json"
                    with open(paragraph_info_path, "w", encoding="utf-8") as f:
                        json.dump(paragraph_info, f, ensure_ascii=False, indent=2)

                    result["paragraph_count"] = len(paragraph_timings)
                    result["total_silence_ms"] = paragraph_info["total_silence_ms"]

        return result

    def _parse_srt(self, srt_path: Path) -> List[Dict]:
        """
        SRT 파일 파싱

        Args:
            srt_path: SRT 파일 경로

        Returns:
            세그먼트 딕셔너리 리스트
        """
        segments = []

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        blocks = content.strip().split("\n\n")

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) >= 3:
                try:
                    index = int(lines[0])
                    time_line = lines[1]
                    text = " ".join(lines[2:])

                    # 시간 파싱
                    start_str, end_str = time_line.split(" --> ")
                    start_ms = srt_time_to_ms(start_str)
                    end_ms = srt_time_to_ms(end_str)

                    segments.append({
                        "index": index,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "start_time": start_str,
                        "end_time": end_str,
                        "text": text
                    })
                except (ValueError, IndexError):
                    continue

        return segments

    def _find_paragraph_timings(
        self,
        text: str,
        srt_segments: List[Dict],
        breaks: List[Dict]
    ) -> List[Dict]:
        """
        문단 구분점의 오디오 타이밍 찾기

        Args:
            text: 원본 스크립트
            srt_segments: SRT 세그먼트 리스트
            breaks: 문단 구분점 리스트

        Returns:
            타이밍 정보 딕셔너리 리스트
        """
        timings = []

        # 각 자막 세그먼트의 누적 문자 위치 계산
        char_positions = []
        current_pos = 0

        for seg in srt_segments:
            char_positions.append({
                "start_char": current_pos,
                "end_char": current_pos + len(seg["text"]),
                "end_ms": seg["end_ms"]
            })
            current_pos += len(seg["text"]) + 1  # +1 for space

        # 각 문단 구분점에 해당하는 시간 찾기
        for brk in breaks:
            break_pos = brk["position"]

            # 가장 가까운 세그먼트 끝 찾기
            for pos in char_positions:
                if pos["start_char"] <= break_pos <= pos["end_char"] + 50:
                    timings.append({
                        "time_ms": pos["end_ms"],
                        "type": brk.get("type", "paragraph"),
                        "silence_ms": brk.get("silence_ms", self.silence_padder.silence_duration)
                    })
                    break

        # 중복 제거 (비슷한 시간의 타이밍)
        filtered_timings = []
        for t in timings:
            if not any(abs(t["time_ms"] - ft["time_ms"]) < 1000 for ft in filtered_timings):
                filtered_timings.append(t)

        return filtered_timings

    def _write_srt(self, segments: List[Dict], srt_path: Path):
        """
        SRT 파일 저장

        Args:
            segments: 세그먼트 딕셔너리 리스트
            srt_path: 출력 경로
        """
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                start_time = ms_to_srt_time(seg["start_ms"])
                end_time = ms_to_srt_time(seg["end_ms"])

                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{seg['text']}\n\n")

    def _vtt_to_srt(self, vtt_content: str) -> str:
        """
        VTT 형식을 SRT 형식으로 변환

        Args:
            vtt_content: VTT 형식 문자열

        Returns:
            SRT 형식 문자열
        """
        lines = vtt_content.strip().split('\n')
        srt_lines = []
        index = 1
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # WEBVTT 헤더 건너뛰기
            if line.startswith('WEBVTT') or line.startswith('NOTE') or not line:
                i += 1
                continue

            # 타임코드 라인 찾기
            if '-->' in line:
                # VTT 타임코드를 SRT 형식으로 변환 (. → ,)
                timecode = line.replace('.', ',')

                # 다음 줄들이 텍스트
                text_lines = []
                i += 1
                while i < len(lines) and lines[i].strip() and '-->' not in lines[i]:
                    text_lines.append(lines[i].strip())
                    i += 1

                if text_lines:
                    srt_lines.append(str(index))
                    srt_lines.append(timecode)
                    srt_lines.append(' '.join(text_lines))
                    srt_lines.append('')
                    index += 1
            else:
                i += 1

        return '\n'.join(srt_lines)

    def _create_srt_from_boundaries(self, boundaries: List[Dict], text: str) -> str:
        """
        WordBoundary 데이터에서 SRT 생성

        Args:
            boundaries: WordBoundary 리스트
            text: 원본 텍스트

        Returns:
            SRT 형식 문자열
        """
        if not boundaries:
            return self._create_fallback_srt(text)

        # 문장 단위로 그룹화
        sentences = re.split(r'(?<=[.!?。！？])\s*', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        srt_lines = []
        current_offset = 0

        for i, sentence in enumerate(sentences, 1):
            # 문장 길이에 비례하여 시간 배분
            word_count = len(sentence.split())
            duration = max(2000, word_count * 500)  # 최소 2초, 단어당 0.5초

            start_ms = current_offset
            end_ms = current_offset + duration

            start_time = ms_to_srt_time(start_ms)
            end_time = ms_to_srt_time(end_ms)

            srt_lines.append(str(i))
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(sentence)
            srt_lines.append('')

            current_offset = end_ms + 100  # 100ms 간격

        return '\n'.join(srt_lines)

    def _create_fallback_srt(self, text: str) -> str:
        """
        텍스트에서 기본 SRT 생성 (문장 단위)

        Args:
            text: 원본 텍스트

        Returns:
            SRT 형식 문자열
        """
        # 문장 분리
        sentences = re.split(r'(?<=[.!?。！？])\s*', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        srt_lines = []
        current_ms = 0

        for i, sentence in enumerate(sentences, 1):
            # 글자 수 기반 예상 시간 (분당 약 250자 기준)
            char_count = len(sentence)
            duration_ms = max(2000, int(char_count * 100))  # 최소 2초

            start_time = ms_to_srt_time(current_ms)
            end_time = ms_to_srt_time(current_ms + duration_ms)

            srt_lines.append(str(i))
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(sentence)
            srt_lines.append('')

            current_ms += duration_ms + 200  # 문장 간 200ms 간격

        return '\n'.join(srt_lines)


def run_async(coro):
    """
    비동기 코루틴을 동기적으로 실행

    Args:
        coro: 코루틴

    Returns:
        코루틴 결과
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)
