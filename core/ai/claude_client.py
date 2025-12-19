"""
Claude API 클라이언트

시니어 타겟 스크립트 생성 및 Trans-creation(초월 번역) 지원
"""
from anthropic import Anthropic
from typing import Optional, List, Dict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS
from config.senior_style_guide import get_style_prompt


class ClaudeClient:
    """
    Claude API를 활용한 스크립트 생성 클라이언트

    특징:
    - 시니어 타겟 톤앤매너 자동 적용
    - 한국어/일본어 지원
    - Trans-creation(초월 번역) 지원
    """

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: Anthropic API 키 (기본: 환경변수에서 로드)
        """
        self.api_key = api_key or ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API Key가 필요합니다. .env 파일을 확인하세요.")

        self.client = Anthropic(api_key=self.api_key)
        self.model = CLAUDE_MODEL

    def generate_script(
        self,
        topic: str,
        language: str = "ko",
        target_length: int = 15,
        tone: str = "informative",
        benchmark_scripts: Optional[List[str]] = None,
        benchmark_comments: Optional[List[str]] = None,
        include_hook: bool = True,
        include_cta: bool = True,
        additional: str = ""
    ) -> Dict:
        """
        시니어 타겟 스크립트 생성

        Args:
            topic: 영상 주제
            language: 타겟 언어 ("ko" 또는 "ja")
            target_length: 목표 길이 (분)
            tone: 톤 ("informative", "storytelling", "tutorial" 등)
            benchmark_scripts: 벤치마킹 스크립트 리스트
            benchmark_comments: 벤치마킹 영상의 댓글 리스트
            include_hook: HOOK 섹션 포함 여부
            include_cta: CTA 섹션 포함 여부
            additional: 추가 지시사항

        Returns:
            {
                "script": str,
                "word_count": int,
                "tokens_used": int
            }
        """
        # 시니어 톤앤매너 가이드
        style_guide = get_style_prompt(language)

        # 목표 글자 수 계산 (분당 약 250자)
        target_words = target_length * 250

        # 언어 표시
        lang_name = "한국어" if language == "ko" else "일본어"

        # 프롬프트 구성
        prompt = f"""당신은 시니어 대상 유튜브 스크립트 작가입니다.

## 영상 정보
- 주제: {topic}
- 목표 길이: {target_length}분 (약 {target_words}자)
- 언어: {lang_name}
- 톤: {tone}

{style_guide}
"""

        # 벤치마킹 정보 추가
        if benchmark_scripts:
            prompt += f"""
## 벤치마킹 스크립트 (참고용)
다음 스크립트의 구조와 스타일을 참고하되, 내용은 새롭게 작성하세요:

{benchmark_scripts[0][:1500]}...
"""

        if benchmark_comments:
            comments_text = "\n".join(f"- {c}" for c in benchmark_comments[:10])
            prompt += f"""
## 시청자 관심사 (댓글 분석)
{comments_text}

위 댓글에서 나타난 시청자의 관심사와 궁금증을 스크립트에 반영하세요.
"""

        # 구조 지정
        prompt += """
## 스크립트 구조
다음 구조로 작성하세요:

"""
        if include_hook:
            prompt += """[HOOK]
(처음 30초 - 시청자 이탈 방지)
- 강렬한 질문이나 흥미로운 사실로 시작
- 이 영상을 끝까지 봐야 하는 이유 제시

"""

        prompt += """[INTRO]
(인트로 - 30초~1분)
- 자기소개 (필요시)
- 오늘 다룰 내용 간략 소개
- 시청자가 얻을 수 있는 가치 설명

[MAIN]
(본문 - 전체의 80%)
- 핵심 내용을 3~5개 포인트로 구성
- 각 포인트는 명확한 소제목과 설명
- 구체적인 예시와 실용적인 팁 포함
- 중요한 내용은 반복해서 강조

"""

        if include_cta:
            prompt += """[CTA]
(Call to Action - 30초)
- 구독과 좋아요 부탁
- 댓글로 의견 공유 유도
- 다음 영상 예고 (선택)

"""

        prompt += """[OUTRO]
(마무리 - 30초)
- 핵심 메시지 요약
- 따뜻한 인사로 마무리
"""

        if additional:
            prompt += f"""
## 추가 지시사항
{additional}
"""

        prompt += """
## 출력 형식
- 위 구조([HOOK], [INTRO] 등)를 그대로 사용하세요
- 각 섹션 마커 다음 줄부터 내용을 작성하세요
- 문단 사이에는 빈 줄을 넣어주세요
- 스크립트만 출력하세요 (설명이나 주석 제외)
"""

        # API 호출
        response = self.client.messages.create(
            model=self.model,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
        )

        script = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

        return {
            "script": script,
            "word_count": len(script),
            "tokens_used": tokens_used
        }

    def transcreate_to_japanese(
        self,
        korean_script: str,
        topic: str,
        additional_context: str = ""
    ) -> Dict:
        """
        한국어 스크립트를 일본어 시니어 타겟으로 Trans-creation

        Trans-creation: 단순 번역이 아닌 문화 적응형 재창작

        Args:
            korean_script: 한국어 원본 스크립트
            topic: 영상 주제
            additional_context: 추가 컨텍스트

        Returns:
            {
                "script": str,
                "method": "transcreation",
                "tokens_used": int
            }
        """
        style_guide = get_style_prompt("ja")

        prompt = f"""당신은 한국어 → 일본어 초월 번역(Trans-creation) 전문가입니다.

## 중요: Trans-creation 원칙
단순히 번역하는 것이 아니라, 일본 60대 이상 시니어가 자연스럽게 느낄 수 있도록 재창작해야 합니다.

### Trans-creation 체크리스트
1. **어휘 점검**
   - 어려운 한자어 → 쉬운 고유어(和語)로 변환
   - 카타카나 외래어에 읽는 법 병기

2. **말투 점검**
   - です/ます체 사용
   - ~ですよね?, ~しましょう 같은 공감/권유형 사용

3. **문화 적응 점검**
   - 한국 고유 예시 → 일본 청자가 공감할 수 있는 것으로 대체
   - 일본 시니어가 이해하기 어려운 한국 문화 요소 설명/대체

4. **구조 점검**
   - 문장 40자 이내
   - 문단 전환 자연스럽게

## 영상 주제
{topic}

## 원본 스크립트 (한국어)
{korean_script}

{style_guide}

{additional_context}

## 출력 형식
- [HOOK], [INTRO], [MAIN], [CTA], [OUTRO] 구조 유지
- 일본어 스크립트만 출력 (설명 제외)
- 각 문단 사이에 빈 줄 유지
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
        )

        japanese_script = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

        return {
            "script": japanese_script,
            "original_language": "ko",
            "target_language": "ja",
            "method": "transcreation",
            "tokens_used": tokens_used
        }

    def generate_image_prompts(
        self,
        segments: List[Dict],
        style: str = "animation",
        language: str = "ko"
    ) -> List[Dict]:
        """
        세그먼트 그룹 기반 이미지 프롬프트 생성

        Args:
            segments: 세그먼트 그룹 리스트
            style: 이미지 스타일
            language: 원본 언어

        Returns:
            프롬프트 딕셔너리 리스트
        """
        prompts = []

        for seg in segments:
            text = seg.get("combined_text", "")

            prompt_text = f"""Based on this narration: "{text[:200]}"

Generate an image prompt that:
1. Captures the main concept visually
2. Uses {style} style
3. Is suitable for YouTube video content
4. Contains NO text, NO letters, NO words

Output only the image prompt, nothing else."""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt_text}]
            )

            prompts.append({
                "group_id": seg.get("group_id"),
                "segment_indices": seg.get("segment_indices"),
                "text_content": text,
                "prompt": response.content[0].text.strip()
            })

        return prompts

    def generate_thumbnail_prompts(
        self,
        topic: str,
        style: str = "animation"
    ) -> Dict:
        """
        썸네일 프롬프트 생성 (이미지/텍스트 분리)

        Args:
            topic: 영상 주제
            style: 이미지 스타일

        Returns:
            썸네일 프롬프트 딕셔너리
        """
        prompt = f"""Generate 3 YouTube thumbnail concepts for this topic: "{topic}"

For each concept, provide:
1. Image prompt (NO TEXT in the image, only visual elements)
2. Overlay text (main title and subtitle to be added separately)
3. Font and color suggestions

Style: {style}

Output in this JSON format:
{{
  "thumbnail_prompts": [
    {{
      "version": "A",
      "type": "description",
      "image_prompt": "prompt without any text elements",
      "overlay_text": {{
        "main": "main title text",
        "sub": "subtitle text",
        "font_suggestion": "font name",
        "color_suggestion": "color code"
      }}
    }}
  ]
}}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        # JSON 파싱 시도
        import json
        try:
            result = json.loads(response.content[0].text)
        except json.JSONDecodeError:
            # 파싱 실패 시 기본 구조 반환
            result = {
                "thumbnail_prompts": [{
                    "version": "A",
                    "type": "generated",
                    "image_prompt": response.content[0].text[:500],
                    "overlay_text": {"main": topic[:20], "sub": ""}
                }]
            }

        result["note"] = "FLUX는 텍스트 생성이 불안정합니다. 이미지 생성 후 텍스트를 수동 합성하세요."

        return result
