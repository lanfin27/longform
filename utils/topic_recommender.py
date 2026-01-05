# -*- coding: utf-8 -*-
"""
AI 영상 주제 추천 모듈 (v4.0)

변경사항:
- Claude CLI (Max Plan) 기본 + Gemini 자동 폴백
- Anthropic API 직접 호출 제거
- 폴백 모드 플래그로 불필요한 재시도 방지

지원 제공자:
1. google - Gemini API 직접 호출
2. claude_code_agent - Claude Code CLI (Max Plan) + Gemini 자동 폴백
"""

import os
import json
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from utils.channel_identity import ChannelIdentity, get_identity_manager


# =========================================================
# 모듈 레벨 Gemini 폴백 클라이언트
# =========================================================
GEMINI_FALLBACK_AVAILABLE = False
_gemini_fallback_client = None

try:
    import google.generativeai as genai
    _fallback_api_key = os.getenv("GOOGLE_API_KEY")
    if _fallback_api_key:
        genai.configure(api_key=_fallback_api_key)
        _gemini_fallback_client = genai.GenerativeModel("gemini-2.0-flash-exp")
        GEMINI_FALLBACK_AVAILABLE = True
        print("[TopicRecommender] ✅ Gemini 폴백 클라이언트 준비 완료")
except Exception as e:
    print(f"[TopicRecommender] ⚠️ Gemini 폴백 초기화 실패: {e}")


@dataclass
class VideoData:
    """영상 데이터"""
    title: str
    channel: str
    views: int
    likes: int = 0
    subscribers: int = 0
    surge_score: float = 0.0  # 급등점수
    published_date: str = ""
    video_id: str = ""

    def to_summary(self) -> str:
        return f"- {self.title} (조회수: {self.views:,}, 급등점수: {self.surge_score:.1f})"


@dataclass
class TopicRecommendation:
    """주제 추천 결과"""
    topic: str
    description: str
    reason: str
    target_audience: str
    estimated_views: str
    reference_videos: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    priority: int = 0  # 1-5 (높을수록 추천)


@dataclass
class RecommendationResult:
    """추천 결과 전체"""
    recommendations: List[TopicRecommendation]
    trend_analysis: str
    common_keywords: List[str]
    tokens_used: int = 0
    provider_used: str = ""
    model_used: str = ""  # UI에서 사용


# 제공자 정보
PROVIDERS = {
    "google": {
        "name": "Gemini API",
        "description": "Google Gemini API 직접 호출",
        "requires": "GOOGLE_API_KEY"
    },
    "claude_code_agent": {
        "name": "Claude Code Agent (Max Plan)",
        "description": "Claude CLI (Max Plan) + Gemini 자동 폴백",
        "requires": "claude CLI 설치 + GOOGLE_API_KEY (폴백용)"
    }
}


class AIPromptTemplate:
    """AI 프롬프트 템플릿 관리"""

    DEFAULT_SYSTEM_PROMPT = """당신은 유튜브 콘텐츠 전략 전문가입니다.

당신의 역할:
1. 급등하는 영상들의 트렌드를 분석합니다
2. 채널의 정체성에 맞는 영상 주제를 추천합니다
3. 각 주제에 대한 구체적인 기획 방향을 제시합니다

중요한 원칙:
- 채널 정체성과 일관성 유지
- 트렌드와 채널 특성의 교집합 찾기
- 실현 가능하고 구체적인 주제 제안
- 제외 주제는 절대 추천하지 않기

출력 형식: 반드시 JSON만 출력하세요."""

    DEFAULT_USER_PROMPT = """## 작업
아래 급등 영상들을 분석하고, 채널 정체성에 맞는 영상 주제를 추천해주세요.

{channel_identity}

## 급등 영상 목록 (급등점수 순)
{video_list}

## 출력 형식 (JSON만 출력)
```json
{{
  "trend_analysis": "현재 트렌드 분석 요약 (2-3문장)",
  "common_keywords": ["키워드1", "키워드2", "키워드3"],
  "recommendations": [
    {{
      "topic": "추천 주제 제목",
      "description": "주제에 대한 상세 설명 (2-3문장)",
      "reason": "이 주제를 추천하는 이유",
      "target_audience": "타겟 시청자",
      "estimated_views": "예상 조회수 범위",
      "reference_videos": ["참고 영상 제목1", "참고 영상 제목2"],
      "keywords": ["키워드1", "키워드2"],
      "priority": 5
    }}
  ]
}}
```

## 규칙
1. 5-10개의 주제를 추천하세요
2. priority는 1-5 (5가 가장 추천)
3. 채널 정체성의 "제외 주제"는 절대 추천하지 마세요
4. reference_videos는 입력된 급등 영상 제목 중에서 선택

JSON만 출력하세요:"""

    CONFIG_FILE = "data/config/ai_prompts/topic_recommendation.json"

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.config_path = self.base_path / self.CONFIG_FILE
        self._load()

    def _load(self):
        """프롬프트 로드"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.system_prompt = data.get("system_prompt", self.DEFAULT_SYSTEM_PROMPT)
                self.user_prompt_template = data.get("user_prompt_template", self.DEFAULT_USER_PROMPT)
                return
            except Exception as e:
                print(f"[AIPromptTemplate] 로드 실패: {e}")

        self.system_prompt = self.DEFAULT_SYSTEM_PROMPT
        self.user_prompt_template = self.DEFAULT_USER_PROMPT

    def save(self):
        """프롬프트 저장"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump({
                "system_prompt": self.system_prompt,
                "user_prompt_template": self.user_prompt_template
            }, f, ensure_ascii=False, indent=2)

        print(f"[AIPromptTemplate] 저장됨: {self.config_path}")

    def reset_to_default(self):
        """기본값으로 리셋"""
        self.system_prompt = self.DEFAULT_SYSTEM_PROMPT
        self.user_prompt_template = self.DEFAULT_USER_PROMPT
        self.save()

    def build_user_prompt(
        self,
        identity: ChannelIdentity,
        videos: List[VideoData]
    ) -> str:
        """사용자 프롬프트 생성"""

        # 채널 정체성 컨텍스트
        channel_context = identity.to_prompt_context()

        # 영상 목록
        video_lines = []
        for i, v in enumerate(videos[:20], 1):  # 상위 20개
            video_lines.append(
                f"{i}. {v.title}\n"
                f"   채널: {v.channel} | 조회수: {v.views:,} | "
                f"급등점수: {v.surge_score:.1f} | 날짜: {v.published_date}"
            )

        video_list = "\n".join(video_lines)

        return self.user_prompt_template.format(
            channel_identity=channel_context,
            video_list=video_list
        )


class TopicRecommender:
    """영상 주제 추천기 (v4.0 - Max Plan + Gemini 자동 폴백)"""

    def __init__(
        self,
        provider: str = "claude_code_agent",  # "google" or "claude_code_agent"
        model: str = None,
        api_key: str = None
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.client = None
        self.runner = None  # Claude CLI 용
        self._use_gemini = False  # ⭐ 폴백 모드 플래그

        self.prompt_template = AIPromptTemplate()

        # 제공자별 초기화
        if provider == "google":
            self._init_gemini()
        elif provider == "claude_code_agent":
            self._init_claude_code_agent()
        else:
            print(f"[TopicRecommender] ⚠️ 알 수 없는 provider: {provider}, claude_code_agent 사용")
            self.provider = "claude_code_agent"
            self._init_claude_code_agent()

        print(f"[TopicRecommender] 초기화 완료 (provider: {self.provider})")

    def _init_gemini(self):
        """Gemini API 초기화"""
        try:
            import google.generativeai as genai
            api_key = self.api_key or os.getenv("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                self.client = genai.GenerativeModel(self.model or "gemini-2.0-flash-exp")
                print(f"[TopicRecommender] Gemini 클라이언트 초기화 완료")
            else:
                print(f"[TopicRecommender] GOOGLE_API_KEY 없음")
        except ImportError:
            print(f"[TopicRecommender] google.generativeai 패키지 없음")
        except Exception as e:
            print(f"[TopicRecommender] Gemini 초기화 실패: {e}")

    def _init_claude_code_agent(self):
        """Claude Code Agent 초기화 (claude_code_runner 사용)"""
        try:
            from utils.claude_code_runner import get_claude_code_runner, is_claude_code_available

            # 올바른 CLI 체크 (하드코딩 경로 포함)
            if not is_claude_code_available():
                raise ValueError("Claude CLI를 찾을 수 없습니다")

            self.runner = get_claude_code_runner()
            self.client = self.runner  # 호환성 유지
            print(f"[TopicRecommender] Claude Code Agent 초기화 완료")
            print(f"[TopicRecommender]   경로: {self.runner.claude_path}")
        except ImportError:
            print(f"[TopicRecommender] claude_code_runner 모듈 없음")
        except Exception as e:
            print(f"[TopicRecommender] Claude Code Agent 초기화 실패: {e}")

    def recommend(
        self,
        identity: ChannelIdentity,
        videos: List[VideoData],
        custom_instructions: str = ""
    ) -> RecommendationResult:
        """
        주제 추천 실행

        Args:
            identity: 채널 정체성
            videos: 급등 영상 리스트 (급등점수 순 정렬)
            custom_instructions: 추가 지시사항

        Returns:
            RecommendationResult
        """

        if not videos:
            return RecommendationResult(
                recommendations=[],
                trend_analysis="분석할 영상이 없습니다",
                common_keywords=[],
                provider_used=self.provider
            )

        print(f"\n[TopicRecommender] 주제 추천 시작 (provider: {self.provider})")

        try:
            # 제공자별 처리
            if self.provider == "google":
                return self._recommend_gemini(identity, videos, custom_instructions)
            elif self.provider == "claude_code_agent":
                return self._recommend_claude_code_agent(identity, videos, custom_instructions)
            else:
                # 알 수 없는 provider는 claude_code_agent로 처리
                print(f"[TopicRecommender] ⚠️ 알 수 없는 provider: {self.provider}, claude_code_agent 사용")
                return self._recommend_claude_code_agent(identity, videos, custom_instructions)

        except Exception as e:
            print(f"[TopicRecommender] 오류: {e}")
            import traceback
            traceback.print_exc()
            return RecommendationResult(
                recommendations=[],
                trend_analysis=f"오류 발생: {str(e)}",
                common_keywords=[],
                provider_used=self.provider
            )

    def _recommend_gemini(
        self,
        identity: ChannelIdentity,
        videos: List[VideoData],
        custom_instructions: str
    ) -> RecommendationResult:
        """Gemini API로 추천"""

        if not self.client:
            raise ValueError("Gemini 클라이언트가 초기화되지 않았습니다")

        # 프롬프트 생성
        system_prompt = self.prompt_template.system_prompt
        user_prompt = self.prompt_template.build_user_prompt(identity, videos)

        if custom_instructions:
            user_prompt += f"\n\n## 추가 지시사항\n{custom_instructions}"

        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # API 호출
        response = self.client.generate_content(full_prompt)

        # 응답 파싱
        data = self._parse_response(response.text)
        model_name = self.model or "gemini-2.0-flash-exp"
        result = self._build_result(data, "google", model_name)

        print(f"[TopicRecommender] Gemini 추천 완료: {len(result.recommendations)}개")

        return result

    def _recommend_claude_code_agent(
        self,
        identity: ChannelIdentity,
        videos: List[VideoData],
        custom_instructions: str
    ) -> RecommendationResult:
        """
        Claude Code Agent로 추천 (v4.0 - Max Plan + Gemini 자동 폴백)

        핵심:
        1. Claude CLI (Max Plan) 먼저 시도
        2. 실패 시 (rate limit, credit 부족 등) Gemini 자동 폴백
        3. _use_gemini 플래그로 불필요한 재시도 방지
        """

        # 프롬프트 생성
        system_prompt = self.prompt_template.system_prompt
        user_prompt = self.prompt_template.build_user_prompt(identity, videos)

        if custom_instructions:
            user_prompt += f"\n\n## 추가 지시사항\n{custom_instructions}"

        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # ⭐ 1차: Claude CLI (Max Plan) - 폴백 모드가 아닐 때만
        if not self._use_gemini and self.runner and self.runner.available:
            print(f"[TopicRecommender] 🔵 Claude CLI 실행 중 (Max Plan)...")

            cli_result = self.runner.run(full_prompt, timeout=180)

            if cli_result.success:
                # 성공 - JSON 파싱
                data = self.runner.extract_json(cli_result.output)

                if not data:
                    try:
                        data = self._parse_response(cli_result.output)
                    except Exception as e:
                        print(f"[TopicRecommender] JSON 파싱 실패: {e}")
                        data = None

                if data:
                    result = self._build_result(data, "claude_code_agent")
                    result.model_used = "claude-code-agent (Max Plan)"
                    print(f"[TopicRecommender] ✅ Claude CLI 추천 완료: {len(result.recommendations)}개")
                    return result

            # 실패 - 폴백 필요 여부 확인
            if cli_result.should_fallback and GEMINI_FALLBACK_AVAILABLE:
                print(f"[TopicRecommender] ⚠️ Claude CLI 실패: {cli_result.error}")
                print(f"[TopicRecommender] 🔄 Gemini 폴백으로 전환")
                self._use_gemini = True  # ⭐ 폴백 모드 활성화
            elif not cli_result.success:
                # 폴백 불가 - 오류 반환
                print(f"[TopicRecommender] ❌ Claude CLI 오류 (폴백 불가): {cli_result.error}")
                return RecommendationResult(
                    recommendations=[],
                    trend_analysis=f"Agent 오류: {cli_result.error}",
                    common_keywords=[],
                    provider_used="claude_code_agent",
                    model_used="claude-code-agent"
                )

        # ⭐ 2차: Gemini 폴백
        if self._use_gemini or not (self.runner and self.runner.available):
            if GEMINI_FALLBACK_AVAILABLE and _gemini_fallback_client:
                print(f"[TopicRecommender] 🟡 Gemini 실행 중 (폴백)...")

                try:
                    response = _gemini_fallback_client.generate_content(full_prompt)
                    data = self._parse_response(response.text)

                    result = self._build_result(data, "gemini_fallback")
                    result.model_used = "gemini-2.0-flash-exp (폴백)"
                    print(f"[TopicRecommender] ✅ Gemini 폴백 추천 완료: {len(result.recommendations)}개")
                    return result

                except Exception as e:
                    print(f"[TopicRecommender] ❌ Gemini 폴백 오류: {e}")
                    return RecommendationResult(
                        recommendations=[],
                        trend_analysis=f"Gemini 폴백 오류: {str(e)}",
                        common_keywords=[],
                        provider_used="gemini_fallback",
                        model_used="gemini-2.0-flash-exp"
                    )

        # 모든 제공자 실패
        return RecommendationResult(
            recommendations=[],
            trend_analysis="사용 가능한 AI 제공자가 없습니다",
            common_keywords=[],
            provider_used="none",
            model_used="none"
        )

    def _parse_response(self, response_text: str) -> dict:
        """응답 파싱"""

        # JSON 추출
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            raise ValueError("JSON을 찾을 수 없습니다")

        return json.loads(json_match.group())

    def _build_result(self, data: dict, provider: str, model: str = "") -> RecommendationResult:
        """결과 객체 생성"""

        recommendations = []
        for rec in data.get("recommendations", []):
            recommendations.append(TopicRecommendation(
                topic=rec.get("topic", ""),
                description=rec.get("description", ""),
                reason=rec.get("reason", ""),
                target_audience=rec.get("target_audience", ""),
                estimated_views=rec.get("estimated_views", ""),
                reference_videos=rec.get("reference_videos", []),
                keywords=rec.get("keywords", []),
                priority=rec.get("priority", 3)
            ))

        # 우선순위 정렬
        recommendations.sort(key=lambda x: x.priority, reverse=True)

        return RecommendationResult(
            recommendations=recommendations,
            trend_analysis=data.get("trend_analysis", ""),
            common_keywords=data.get("common_keywords", []),
            provider_used=provider,
            model_used=model or provider
        )

    def get_prompt_template(self) -> AIPromptTemplate:
        """프롬프트 템플릿 반환 (UI 편집용)"""
        return self.prompt_template

    def update_prompt_template(
        self,
        system_prompt: str = None,
        user_prompt_template: str = None
    ):
        """프롬프트 템플릿 업데이트"""
        if system_prompt:
            self.prompt_template.system_prompt = system_prompt
        if user_prompt_template:
            self.prompt_template.user_prompt_template = user_prompt_template
        self.prompt_template.save()


# =========================================================
# 편의 함수
# =========================================================

def get_topic_recommender(
    provider: str = "google",
    model: str = None
) -> TopicRecommender:
    """추천기 생성"""
    return TopicRecommender(provider=provider, model=model)


def recommend_topics(
    project_name: str,
    videos: List[Dict],
    provider: str = "google",
    model: str = None,
    custom_instructions: str = ""
) -> RecommendationResult:
    """
    편의 함수: 주제 추천

    Args:
        project_name: 프로젝트명
        videos: 영상 데이터 리스트 [{title, channel, views, ...}, ...]
        provider: "google", "anthropic", or "claude_code_agent"
        model: 모델명
        custom_instructions: 추가 지시사항

    Returns:
        RecommendationResult
    """

    # 채널 정체성 로드
    manager = get_identity_manager()
    identity = manager.load(project_name)

    # 영상 데이터 변환
    video_data = []
    for v in videos:
        video_data.append(VideoData(
            title=v.get("title", ""),
            channel=v.get("channel", v.get("channel_name", "")),
            views=v.get("views", v.get("view_count", 0)),
            likes=v.get("likes", v.get("like_count", 0)),
            subscribers=v.get("subscribers", v.get("subscriber_count", 0)),
            surge_score=v.get("surge_score", 0),
            published_date=v.get("published_date", v.get("published_at", "")),
            video_id=v.get("video_id", "")
        ))

    # 급등점수 순 정렬
    video_data.sort(key=lambda x: x.surge_score, reverse=True)

    # 추천 실행
    recommender = get_topic_recommender(provider, model)
    return recommender.recommend(identity, video_data, custom_instructions)


def check_api_availability() -> Dict[str, bool]:
    """API 사용 가능 여부 확인"""
    result = {
        "google": bool(os.getenv("GOOGLE_API_KEY")),
        "claude_code_agent": False,
        "gemini_fallback": GEMINI_FALLBACK_AVAILABLE
    }

    # Claude Code Agent 확인
    try:
        from utils.claude_code_runner import is_claude_code_available
        result["claude_code_agent"] = is_claude_code_available()
    except Exception:
        pass

    return result
