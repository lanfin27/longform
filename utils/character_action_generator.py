# -*- coding: utf-8 -*-
"""
AI 기반 캐릭터 액션 프롬프트 생성기

대표 캐릭터의 씬별 표정/포즈/액션을 AI가 분석하여 생성합니다.

주요 기능:
1. 캐릭터 프롬프트 분석
2. 씬 내용 기반 액션 생성
3. 일괄 액션 프롬프트 생성
4. 키워드 기반 폴백 (AI 실패 시 다양한 액션 생성)
"""

import json
import re
from typing import List, Dict, Optional, Any

from utils.ai_client import UnifiedAIClient
from utils.representative_character import SceneCharacterAction


# ============================================================
# 키워드 기반 액션 매핑 (AI 폴백용)
# ============================================================

EXPRESSION_KEYWORDS = {
    "happy": ["기쁨", "행복", "좋은", "성공", "축하", "웃", "밝은", "긍정", "좋아"],
    "surprised": ["놀라", "충격", "갑자기", "급등", "급락", "돌파", "폭등", "폭락", "반전"],
    "serious": ["심각", "중요", "주의", "경고", "위험", "문제", "심각", "리스크"],
    "thinking": ["생각", "고민", "분석", "검토", "왜", "어떻게", "의문", "질문"],
    "explaining": ["설명", "소개", "알려", "말씀", "정보", "안내", "알아"],
    "worried": ["걱정", "우려", "불안", "위기", "하락", "손실", "어려"],
    "confident": ["확신", "자신", "분명", "틀림없", "확실", "강력", "무조건"],
    "excited": ["흥분", "대박", "놀라운", "믿기", "엄청", "최고", "최대"]
}

POSE_KEYWORDS = {
    "pointing": ["이것", "여기", "보세요", "차트", "그래프", "수치", "데이터", "이 부분"],
    "arms_crossed": ["결론", "요약", "정리", "마무리", "마지막으로"],
    "hands_open": ["환영", "소개", "처음", "시작", "여러분", "안녕"],
    "one_hand_up": ["중요", "포인트", "핵심", "주목", "기억", "명심"],
    "chin_touch": ["생각", "고민", "분석", "의문", "왜", "어떻게"],
    "both_hands_gesture": ["비교", "차이", "양쪽", "vs", "반면", "한편"]
}


class CharacterActionGenerator:
    """AI 기반 캐릭터 액션 프롬프트 생성기"""

    def __init__(self, model_id: str = None):
        """
        Args:
            model_id: AI 모델 ID (예: "gemini-2.0-flash-exp", "claude-sonnet-4-20250514")
        """
        self.model_id = model_id or "gemini-2.0-flash-exp"
        self._client = None

    def _get_client(self) -> UnifiedAIClient:
        """AI 클라이언트 가져오기 (지연 초기화)"""
        if self._client is None:
            self._client = UnifiedAIClient(model_id=self.model_id)
        return self._client

    def analyze_character_prompt(self, character_prompt: str) -> Dict:
        """
        대표 캐릭터 프롬프트 분석

        Returns:
            {
                "gender": "male",
                "age_group": "30s",
                "art_style": "korean webtoon",
                "key_features": ["glasses", "navy suit", "short hair"],
                "personality_vibe": "professional, friendly"
            }
        """
        if not character_prompt:
            return {}

        system_prompt = """You are an expert at analyzing character design prompts for AI image generation.
Analyze the given character prompt and extract key information.
Respond ONLY with valid JSON, no other text."""

        user_prompt = f"""Analyze this character prompt and extract:
1. gender (male/female/neutral)
2. age_group (child/teen/20s/30s/40s/50s+)
3. art_style (realistic/anime/webtoon/illustration/etc)
4. key_features (list of distinctive visual features)
5. personality_vibe (overall feeling/personality)

Character prompt:
"{character_prompt}"

Respond in JSON format only:
{{"gender": "", "age_group": "", "art_style": "", "key_features": [], "personality_vibe": ""}}"""

        try:
            client = self._get_client()
            response = client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=500,
                temperature=0.3
            )

            # JSON 파싱
            return self._parse_json_response(response)

        except Exception as e:
            print(f"[ActionGenerator] 캐릭터 분석 오류: {e}")
            return {
                "gender": "neutral",
                "age_group": "adult",
                "art_style": "illustration",
                "key_features": [],
                "personality_vibe": "neutral"
            }

    def generate_scene_action(
        self,
        character_info: Dict,
        scene_content: str,
        scene_num: int,
        options: Dict = None
    ) -> Dict:
        """
        씬 내용 기반 캐릭터 액션 프롬프트 생성

        Args:
            character_info: 캐릭터 분석 정보
            scene_content: 씬 스크립트/내용
            scene_num: 씬 번호
            options: 생성 옵션 (expression, pose, mood, props)

        Returns:
            {
                "expression_ko": "밝은 미소",
                "expression_en": "bright smile",
                "pose_ko": "양손을 모으고 설명",
                "pose_en": "hands clasped, explaining gesture",
                "mood": "positive",
                "props": ["none"],
                "action_prompt": "smiling warmly, hands clasped together..."
            }
        """
        options = options or {}

        # 내용이 너무 길면 잘라내기
        content_preview = scene_content[:500] if scene_content else "일반적인 설명"

        system_prompt = """You are an expert at creating character action prompts for AI image generation.
Based on the scene content and character information, determine appropriate:
- Facial expression (what emotion fits the content)
- Body pose/gesture (natural action for the context)
- Overall mood (atmosphere)
- Props if needed (objects the character might interact with)

The action prompt should be concise and work well with the base character prompt.
Respond ONLY with valid JSON, no other text."""

        # 옵션에 따른 프롬프트 조정
        option_hints = []
        if options.get("expression", True):
            option_hints.append("- Determine facial expression based on content emotion")
        if options.get("pose", True):
            option_hints.append("- Determine natural pose/gesture for the context")
        if options.get("mood", True):
            option_hints.append("- Consider overall mood/atmosphere")
        if options.get("props", False):
            option_hints.append("- Suggest relevant props if appropriate (chart, laptop, phone, etc.)")

        option_text = "\n".join(option_hints) if option_hints else ""

        user_prompt = f"""Character Information:
- Gender: {character_info.get('gender', 'neutral')}
- Age: {character_info.get('age_group', 'adult')}
- Style: {character_info.get('art_style', 'illustration')}
- Key features: {', '.join(character_info.get('key_features', []))}
- Vibe: {character_info.get('personality_vibe', 'neutral')}

Scene {scene_num} Content:
"{content_preview}"

Task:
{option_text}

Generate character action for this scene. Consider:
1. What facial expression fits? (happy, serious, surprised, thoughtful, concerned, excited, etc.)
2. What pose/gesture is natural? (pointing, explaining, arms crossed, holding something, etc.)
3. What's the mood? (positive, negative, neutral, tense, relaxed, energetic, etc.)
4. Any props needed? (chart, document, phone, laptop, or "none")

Respond in JSON only:
{{
    "expression_ko": "한국어 표정 설명",
    "expression_en": "English expression description",
    "pose_ko": "한국어 포즈/제스처 설명",
    "pose_en": "English pose/gesture description",
    "mood": "mood keyword",
    "props": ["prop1"] or ["none"],
    "action_prompt": "complete English action prompt for image generation, concise and descriptive"
}}"""

        try:
            client = self._get_client()
            response = client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=800,
                temperature=0.5
            )

            result = self._parse_json_response(response)

            # ✅ 개선: AI 응답이 유효한지 확인 (기본값이 아닌지)
            if self._is_valid_action_result(result):
                # 필수 필드 보완
                result = self._ensure_required_fields(result)
                return result
            else:
                # AI가 기본값을 반환했거나 파싱 실패 → 키워드 기반 폴백
                print(f"[ActionGenerator] 씬 {scene_num}: AI 응답 유효하지 않음, 키워드 기반 생성")
                return self._generate_from_keywords(scene_content, scene_num)

        except Exception as e:
            print(f"[ActionGenerator] 씬 {scene_num} 액션 생성 오류: {e}")
            # ✅ 개선: 오류 시 키워드 기반 다양한 폴백 (동일한 기본값 대신)
            return self._generate_from_keywords(scene_content, scene_num)

    def _is_valid_action_result(self, result: Dict) -> bool:
        """AI 응답이 유효한지 확인 (기본값이 아닌지)"""
        if not result:
            return False

        invalid_values = [
            "기본 표정", "기본 자세", "neutral expression",
            "standing pose", "neutral", "default", ""
        ]

        # 주요 필드 확인
        expression = str(result.get("expression_ko", "")).lower()
        pose = str(result.get("pose_ko", "")).lower()
        action = str(result.get("action_prompt", "")).lower()

        # 기본값만 있으면 유효하지 않음
        for invalid in invalid_values:
            if invalid.lower() in expression or invalid.lower() in pose:
                if "neutral expression, standing pose" in action:
                    return False

        # action_prompt가 비어있거나 너무 짧으면 유효하지 않음
        if len(result.get("action_prompt", "")) < 10:
            return False

        return True

    def _ensure_required_fields(self, result: Dict) -> Dict:
        """필수 필드 보완"""
        if not result.get("action_prompt"):
            result["action_prompt"] = "neutral expression, standing pose, looking at viewer"
        if not result.get("expression_ko"):
            result["expression_ko"] = "설명하는 표정"
        if not result.get("expression_en"):
            result["expression_en"] = "explaining expression"
        if not result.get("pose_ko"):
            result["pose_ko"] = "한 손을 든 자세"
        if not result.get("pose_en"):
            result["pose_en"] = "one hand raised"
        if not result.get("mood"):
            result["mood"] = "informative"
        if not result.get("props"):
            result["props"] = ["none"]
        return result

    def _generate_from_keywords(self, scene_content: str, scene_num: int) -> Dict:
        """
        키워드 기반 액션 생성 (AI 실패 시 폴백)

        씬 내용의 키워드를 분석하여 적절한 표정/포즈를 결정합니다.
        씬 번호에 따른 변형을 추가하여 다양성을 확보합니다.
        """
        content = scene_content if scene_content else ""

        # 표정 결정
        expression_ko = "설명하는 표정"
        expression_en = "explaining expression"

        expression_mapping = {
            "happy": ("밝은 미소", "bright smile"),
            "surprised": ("놀란 표정", "surprised expression"),
            "serious": ("진지한 표정", "serious expression"),
            "thinking": ("생각하는 표정", "thoughtful expression"),
            "explaining": ("설명하는 표정", "explaining expression"),
            "worried": ("걱정스러운 표정", "worried expression"),
            "confident": ("자신감 있는 표정", "confident expression"),
            "excited": ("흥분된 표정", "excited expression")
        }

        for expr_type, keywords in EXPRESSION_KEYWORDS.items():
            if any(kw in content for kw in keywords):
                expression_ko, expression_en = expression_mapping.get(
                    expr_type, ("설명하는 표정", "explaining expression")
                )
                break

        # 포즈 결정
        pose_ko = "한 손을 들어 설명하는 자세"
        pose_en = "one hand raised, explaining gesture"

        pose_mapping = {
            "pointing": ("손가락으로 가리키는 자세", "pointing gesture"),
            "arms_crossed": ("팔짱 낀 자세", "arms crossed"),
            "hands_open": ("양손을 펼친 자세", "open hands gesture"),
            "one_hand_up": ("한 손을 든 자세", "one hand raised"),
            "chin_touch": ("턱을 만지는 자세", "touching chin, thinking pose"),
            "both_hands_gesture": ("양손으로 설명하는 자세", "both hands gesturing")
        }

        for pose_type, keywords in POSE_KEYWORDS.items():
            if any(kw in content for kw in keywords):
                pose_ko, pose_en = pose_mapping.get(
                    pose_type, ("한 손을 들어 설명하는 자세", "one hand raised")
                )
                break

        # 분위기 결정
        mood = "informative"
        if any(kw in content for kw in ["급등", "폭등", "놀라", "충격", "대박"]):
            mood = "dramatic"
        elif any(kw in content for kw in ["하락", "위기", "걱정", "손실"]):
            mood = "tense"
        elif any(kw in content for kw in ["좋은", "성공", "기쁨", "축하"]):
            mood = "positive"
        elif any(kw in content for kw in ["분석", "검토", "생각", "고민"]):
            mood = "analytical"

        # 씬 번호에 따른 변형 추가 (다양성 확보)
        pose_variations = [
            "slightly tilted head",
            "leaning forward slightly",
            "standing straight",
            "relaxed posture",
            "engaged posture"
        ]
        variation = pose_variations[scene_num % len(pose_variations)]

        action_prompt = f"{expression_en}, {pose_en}, {variation}, {mood} mood, looking at viewer"

        return {
            "expression_ko": expression_ko,
            "expression_en": expression_en,
            "pose_ko": pose_ko,
            "pose_en": pose_en,
            "mood": mood,
            "props": ["none"],
            "action_prompt": action_prompt
        }

    def generate_batch_actions(
        self,
        character_prompt: str,
        scenes: List[Dict],
        options: Dict = None,
        progress_callback=None
    ) -> List[SceneCharacterAction]:
        """
        모든 씬에 대한 액션 프롬프트 일괄 생성

        Args:
            character_prompt: 대표 캐릭터 프롬프트
            scenes: 씬 목록 [{"scene_num": 1, "script": "..."}, ...]
            options: 생성 옵션
            progress_callback: 진행률 콜백 (current, total, message)

        Returns:
            SceneCharacterAction 목록
        """
        options = options or {}

        # 1. 캐릭터 분석
        if progress_callback:
            progress_callback(0, len(scenes), "캐릭터 프롬프트 분석 중...")

        character_info = self.analyze_character_prompt(character_prompt)
        print(f"[ActionGenerator] 캐릭터 분석 완료: {character_info}")

        results = []
        total = len(scenes)

        # 2. 각 씬별 액션 생성
        for idx, scene in enumerate(scenes):
            scene_num = (
                scene.get("scene_num") or
                scene.get("scene_number") or
                scene.get("scene_id") or
                scene.get("index", idx) + 1
            )

            # 씬 내용 추출
            scene_content = (
                scene.get("script") or
                scene.get("narration") or
                scene.get("대사") or
                scene.get("content") or
                scene.get("text") or
                ""
            )

            if progress_callback:
                progress_callback(idx, total, f"씬 {scene_num} 분석 중...")

            # 액션 생성
            action_data = self.generate_scene_action(
                character_info=character_info,
                scene_content=scene_content,
                scene_num=scene_num,
                options=options
            )

            # SceneCharacterAction 생성
            action = SceneCharacterAction(
                scene_num=scene_num,
                scene_content=scene_content[:100] + "..." if len(scene_content) > 100 else scene_content,
                expression=action_data.get("expression_ko", ""),
                pose=action_data.get("pose_ko", ""),
                mood=action_data.get("mood", ""),
                props=action_data.get("props", []),
                action_prompt=action_data.get("action_prompt", ""),
                generation_status="pending"
            )

            results.append(action)

        if progress_callback:
            progress_callback(total, total, "완료!")

        print(f"[ActionGenerator] {len(results)}개 씬 액션 생성 완료")
        return results

    def _parse_json_response(self, text: str) -> Dict:
        """JSON 응답 파싱"""
        if not text:
            return {}

        text = text.strip()

        # ```json ... ``` 형식 처리
        if '```' in text:
            parts = text.split('```')
            for part in parts:
                part = part.strip()
                if part.startswith('json'):
                    text = part[4:].strip()
                    break
                elif part.startswith('{') or part.startswith('['):
                    text = part
                    break

        # JSON 시작/끝 찾기
        start_idx = text.find('{')
        end_idx = text.rfind('}')

        if start_idx != -1 and end_idx != -1:
            text = text[start_idx:end_idx + 1]

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[ActionGenerator] JSON 파싱 오류: {e}")
            print(f"[ActionGenerator] 원본: {text[:200]}...")
            return {}


# ============================================================
# 헬퍼 함수
# ============================================================

def create_action_generator(model_id: str = None) -> CharacterActionGenerator:
    """액션 생성기 생성"""
    return CharacterActionGenerator(model_id=model_id)


def get_available_models() -> List[Dict]:
    """사용 가능한 AI 모델 목록"""
    return [
        {"id": "gemini-2.0-flash-exp", "name": "Gemini 2.0 Flash Exp (추천)", "provider": "Google"},
        {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash (빠름)", "provider": "Google"},
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "provider": "Anthropic"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini (빠름)", "provider": "OpenAI"},
        {"id": "gpt-4o", "name": "GPT-4o (고품질)", "provider": "OpenAI"},
    ]
