# -*- coding: utf-8 -*-
"""
자막 포맷터 (SubtitleFormatter) v1.0

기능:
- 긴 자막을 지정된 글자수에서 줄바꿈
- 단어가 잘리지 않도록 단어 경계에서 줄바꿈
- SRT 파일 및 씬 리스트 일괄 처리

예시:
    원본 (65자):
    "그리고 7 시리즈 같은 최상의 모델에는 더 강력한 B920이 들어갈 거라는 얘기도 있어요."

    줄바꿈 결과 (43자 기준):
    "그리고 7 시리즈 같은 최상의 모델에는 더 강력한 B920이 들어갈
    거라는 얘기도 있어요."
"""

from typing import List, Dict, Optional


class SubtitleFormatter:
    """자막 줄바꿈 처리기"""

    def __init__(self, max_chars: int = 43):
        """
        Args:
            max_chars: 한 줄 최대 글자수 (공백 포함, 기본값 43)
        """
        self.max_chars = max_chars
        print(f"[SubtitleFormatter] 초기화: 최대 {max_chars}자/줄")

    def wrap_text(self, text: str) -> str:
        """
        텍스트를 지정된 글자수에서 줄바꿈

        규칙:
        1. max_chars 이하면 그대로 반환
        2. max_chars 초과 시 단어 경계에서 줄바꿈
        3. 줄바꿈 후 각 줄도 max_chars 초과 시 재귀적으로 줄바꿈

        Args:
            text: 원본 텍스트

        Returns:
            줄바꿈된 텍스트 (\\n으로 구분)
        """
        if not text:
            return text

        # 이미 줄바꿈이 있으면 각 줄을 개별 처리
        if '\n' in text:
            lines = text.split('\n')
            wrapped_lines = [self.wrap_text(line) for line in lines]
            return '\n'.join(wrapped_lines)

        # max_chars 이하면 그대로 반환
        if len(text) <= self.max_chars:
            return text

        lines = []
        remaining = text.strip()

        while remaining:
            if len(remaining) <= self.max_chars:
                lines.append(remaining)
                break

            # 줄바꿈 위치 찾기
            break_pos = self._find_break_position(remaining)

            if break_pos <= 0:
                # 단어 경계를 찾지 못하면 (매우 긴 단어) 강제로 자름
                lines.append(remaining[:self.max_chars])
                remaining = remaining[self.max_chars:].strip()
            else:
                lines.append(remaining[:break_pos].rstrip())
                remaining = remaining[break_pos:].strip()

        return '\n'.join(lines)

    def _find_break_position(self, text: str) -> int:
        """
        줄바꿈 위치 찾기 (단어가 잘리지 않는 위치)

        규칙:
        1. max_chars 위치에서 시작
        2. 해당 위치의 글자가 단어 중간이면, 그 단어의 시작 위치로 이동
        3. 즉, max_chars 위치에서 왼쪽으로 가장 가까운 공백 다음 위치

        Args:
            text: 텍스트 (max_chars보다 긴 것으로 가정)

        Returns:
            줄바꿈 위치 (이 위치 앞까지가 첫 번째 줄)
        """
        # max_chars 위치 확인
        if len(text) <= self.max_chars:
            return len(text)

        # max_chars 위치의 글자 확인 (0-indexed이므로 -1)
        char_at_max = text[self.max_chars - 1]

        # Case 1: max_chars 위치가 공백이면 그 위치에서 자름
        if char_at_max == ' ':
            return self.max_chars

        # Case 2: max_chars 바로 다음이 공백이면 max_chars에서 자름
        if len(text) > self.max_chars and text[self.max_chars] == ' ':
            return self.max_chars

        # Case 3: max_chars 위치가 단어 중간이면, 그 단어의 시작 위치 찾기
        # max_chars 위치에서 왼쪽으로 가장 가까운 공백 찾기
        search_start = self.max_chars - 1

        for i in range(search_start, -1, -1):
            if text[i] == ' ':
                # 공백 다음 위치가 아니라 공백까지 포함해서 자름
                # 그래야 첫 줄 끝에 공백이 안 붙음
                return i + 1

        # 공백을 찾지 못하면 (한 단어가 max_chars보다 긴 경우)
        # max_chars 이후에서 공백 찾기
        for i in range(self.max_chars, len(text)):
            if text[i] == ' ':
                return i

        # 공백이 전혀 없으면 전체 반환
        return len(text)

    def format_scenes(self, scenes: List[Dict]) -> List[Dict]:
        """
        씬 리스트의 모든 텍스트에 줄바꿈 적용

        Args:
            scenes: 씬 리스트 (각 씬은 'text' 키를 가짐)

        Returns:
            줄바꿈 적용된 씬 리스트 (원본 수정)
        """
        formatted_count = 0

        for scene in scenes:
            original_text = scene.get('text', '')

            if original_text and len(original_text) > self.max_chars:
                formatted_text = self.wrap_text(original_text)

                # 실제로 줄바꿈이 적용되었는지 확인
                if formatted_text != original_text:
                    scene['text'] = formatted_text
                    formatted_count += 1

                    # 디버깅: 줄바꿈된 씬 출력 (처음 5개만)
                    if formatted_count <= 5:
                        scene_id = scene.get('scene_id', '?')
                        print(f"[SubtitleFormatter] 씬 {scene_id}: {len(original_text)}자 → 줄바꿈")
                        print(f"  원본: {original_text[:50]}...")
                        preview = formatted_text.replace('\n', ' / ')[:50]
                        print(f"  결과: {preview}...")

        print(f"[SubtitleFormatter] ✅ {formatted_count}개 씬 줄바꿈 완료")

        return scenes

    def format_srt_content(self, srt_content: str) -> str:
        """
        SRT 파일 내용에 줄바꿈 적용

        Args:
            srt_content: SRT 파일 내용 (문자열)

        Returns:
            줄바꿈 적용된 SRT 내용
        """
        blocks = srt_content.strip().split('\n\n')
        result_blocks = []
        formatted_count = 0

        for block in blocks:
            lines = block.strip().split('\n')

            if len(lines) >= 3:
                # 표준 SRT 블록: 번호, 타임코드, 텍스트(1줄 이상)
                scene_num = lines[0]
                timecode = lines[1]
                subtitle_text = ' '.join(lines[2:])  # 여러 줄 텍스트 합치기

                # 줄바꿈 적용
                if len(subtitle_text) > self.max_chars:
                    formatted_text = self.wrap_text(subtitle_text)
                    formatted_count += 1
                else:
                    formatted_text = subtitle_text

                result_blocks.append(f"{scene_num}\n{timecode}\n{formatted_text}")

            elif len(lines) == 2:
                # 번호, 타임코드만 있는 경우 (비정상이지만 처리)
                result_blocks.append(block)
            else:
                # 기타 형식
                result_blocks.append(block)

        print(f"[SubtitleFormatter] ✅ SRT {formatted_count}개 자막 줄바꿈 완료")

        return '\n\n'.join(result_blocks)

    def get_stats(self, scenes: List[Dict]) -> Dict:
        """
        씬 리스트의 줄바꿈 필요 통계

        Args:
            scenes: 씬 리스트

        Returns:
            통계 정보 딕셔너리
        """
        total = len(scenes)
        need_wrap = sum(1 for s in scenes if len(s.get('text', '')) > self.max_chars)
        already_wrapped = sum(1 for s in scenes if '\n' in s.get('text', ''))
        max_length = max((len(s.get('text', '')) for s in scenes), default=0)
        avg_length = sum(len(s.get('text', '')) for s in scenes) / total if total > 0 else 0

        return {
            'total_scenes': total,
            'need_wrap': need_wrap,
            'already_wrapped': already_wrapped,
            'max_length': max_length,
            'avg_length': round(avg_length, 1),
            'max_chars': self.max_chars
        }


def wrap_subtitle_text(text: str, max_chars: int = 43) -> str:
    """
    편의 함수: 단일 텍스트 줄바꿈

    Args:
        text: 원본 텍스트
        max_chars: 최대 글자수 (기본값 43)

    Returns:
        줄바꿈된 텍스트
    """
    formatter = SubtitleFormatter(max_chars)
    return formatter.wrap_text(text)


def format_scenes_with_wrap(scenes: List[Dict], max_chars: int = 43) -> List[Dict]:
    """
    편의 함수: 씬 리스트 줄바꿈

    Args:
        scenes: 씬 리스트
        max_chars: 최대 글자수 (기본값 43)

    Returns:
        줄바꿈된 씬 리스트
    """
    formatter = SubtitleFormatter(max_chars)
    return formatter.format_scenes(scenes)


# 테스트 코드
if __name__ == "__main__":
    # 테스트 케이스
    test_cases = [
        "그리고 7 시리즈 같은 최상의 모델에는 더 강력한 B920이 들어갈 거라는 얘기도 있어요.",
        "대신 BMW, 테슬라, 현대차 같은 대형 고객한테 맞춤형으로 만들어주는 칩에 집중하기로 한 거죠.",
        "이건 철수가 아니라 전략적 선택과 집중이에요.",  # 43자 이하
        "삼성이 뭘 한 거냐면요.",  # 짧은 문장
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",  # 공백 없는 긴 문자열
    ]

    formatter = SubtitleFormatter(max_chars=43)

    print("\n" + "=" * 60)
    print("SubtitleFormatter 테스트")
    print("=" * 60)

    for i, text in enumerate(test_cases, 1):
        print(f"\n[테스트 {i}]")
        print(f"원본 ({len(text)}자): {text}")
        result = formatter.wrap_text(text)
        line_count = result.count('\n') + 1
        print(f"결과 ({line_count}줄):")
        for j, line in enumerate(result.split('\n'), 1):
            print(f"  {j}: ({len(line)}자) {line}")
        print("-" * 40)

    # 글자 수 검증
    print("\n" + "=" * 60)
    print("글자 수 검증")
    print("=" * 60)

    text = "그리고 7 시리즈 같은 최상의 모델에는 더 강력한 B920이 들어갈 거라는 얘기도 있어요."
    result = formatter.wrap_text(text)

    for i, line in enumerate(result.split('\n'), 1):
        status = "✅" if len(line) <= 43 else "❌"
        print(f"줄 {i}: {len(line)}자 {status}")
        print(f"  내용: {line}")
