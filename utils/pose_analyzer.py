# -*- coding: utf-8 -*-
"""
AI 기반 캐릭터 포즈 분석기

기능:
1. 씬 내용을 분석하여 적절한 캐릭터 포즈 추천
2. 다중 AI 프로바이더 지원 (Gemini, Claude, GPT)
3. 배치 분석으로 효율적인 API 호출

Problem 56: AI 자동 포즈 분석 기능 추가
"""

import json
import re
import os
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass


# 사용 가능한 포즈 목록 (prompt 필드 추가 - 이미지 생성용)
AVAILABLE_POSES = {
    "standing": {
        "name": "서있기",
        "emoji": "🧍",
        "description": "기본 서있는 자세",
        "keywords": ["발표", "연설", "인터뷰", "대화", "기자회견", "서있", "일어서"],
        "prompt": "standing pose, front view, neutral expression, arms at sides"
    },
    "sitting": {
        "name": "앉아있기",
        "emoji": "🪑",
        "description": "의자에 앉은 자세",
        "keywords": ["회의", "식사", "인터뷰", "사무실", "왕좌", "앉아", "책상"],
        "prompt": "sitting pose, relaxed posture, hands on lap or armrest"
    },
    "walking": {
        "name": "걷기",
        "emoji": "🚶",
        "description": "걸어가는 자세",
        "keywords": ["이동", "산책", "행진", "도착", "출발", "걸어", "향하"],
        "prompt": "walking pose, mid-stride, dynamic movement, one foot forward"
    },
    "talking": {
        "name": "대화",
        "emoji": "💬",
        "description": "대화하는 자세",
        "keywords": ["대화", "논쟁", "협상", "토론", "설명", "말하", "이야기"],
        "prompt": "talking pose, mouth slightly open, hand gesture, expressive face"
    },
    "thinking": {
        "name": "생각",
        "emoji": "🤔",
        "description": "생각하는 자세",
        "keywords": ["고민", "계획", "결정", "숙고", "분석", "생각", "고려"],
        "prompt": "thinking pose, hand on chin, contemplative expression, looking thoughtful"
    },
    "pointing": {
        "name": "가리키기",
        "emoji": "👆",
        "description": "손가락으로 가리키는 자세",
        "keywords": ["지시", "설명", "발표", "프레젠테이션", "가리키", "지적"],
        "prompt": "pointing pose, arm extended, index finger pointing, confident expression"
    },
    "greeting": {
        "name": "인사",
        "emoji": "👋",
        "description": "인사하는 자세",
        "keywords": ["만남", "환영", "소개", "인사", "악수"],
        "prompt": "greeting pose, waving hand, friendly smile, welcoming gesture"
    },
    "angry": {
        "name": "화남",
        "emoji": "😠",
        "description": "화난 자세",
        "keywords": ["분노", "격분", "항의", "비난", "화내", "분개"],
        "prompt": "angry pose, furrowed brows, clenched fists, tense posture, fierce expression"
    },
    "happy": {
        "name": "기쁨",
        "emoji": "😊",
        "description": "기쁜 자세",
        "keywords": ["축하", "성공", "기쁨", "환호", "웃", "기뻐"],
        "prompt": "happy pose, big smile, cheerful expression, arms relaxed or raised slightly"
    },
    "sad": {
        "name": "슬픔",
        "emoji": "😢",
        "description": "슬픈 자세",
        "keywords": ["슬픔", "비극", "죽음", "이별", "눈물", "우울"],
        "prompt": "sad pose, downcast eyes, drooping shoulders, melancholy expression"
    },
    "surprised": {
        "name": "놀람",
        "emoji": "😲",
        "description": "놀란 자세",
        "keywords": ["놀람", "충격", "예상치못한", "깜짝", "발견"],
        "prompt": "surprised pose, wide eyes, raised eyebrows, open mouth, startled expression"
    },
    "portrait": {
        "name": "초상화",
        "emoji": "🖼️",
        "description": "얼굴 클로즈업",
        "keywords": ["초상화", "얼굴", "클로즈업", "인물", "소개"],
        "prompt": "portrait, upper body close-up, facing camera, neutral background"
    },
    "action": {
        "name": "액션",
        "emoji": "🏃",
        "description": "동적인 액션 자세",
        "keywords": ["달리", "뛰", "싸움", "전투", "공격", "액션"],
        "prompt": "action pose, dynamic movement, running or fighting stance, energetic"
    }
}


def create_pose_analysis_prompt(scenes: List[Dict], characters: List[str]) -> str:
    """
    AI 포즈 분석 프롬프트 생성

    Args:
        scenes: 씬 데이터 리스트
        characters: 분석할 캐릭터 이름 리스트

    Returns:
        AI 프롬프트 문자열
    """
    # 사용 가능한 포즈 설명
    pose_descriptions = []
    for pose_id, pose_info in AVAILABLE_POSES.items():
        keywords = ', '.join(pose_info['keywords'][:3])
        pose_descriptions.append(
            f"- {pose_id}: {pose_info['description']} (키워드: {keywords})"
        )

    poses_text = "\n".join(pose_descriptions)

    # 씬 정보 정리
    scenes_text = []
    for scene in scenes:
        scene_id = scene.get("scene_id", scene.get("id", 0))
        script = scene.get("script_text", scene.get("narration", ""))
        scene_chars = scene.get("characters", [])

        # 분석 대상 캐릭터만 필터
        relevant_chars = []
        for c in scene_chars:
            char_name = c if isinstance(c, str) else c.get("name", "")
            # 유연한 매칭
            char_normalized = char_name.strip().lower().replace(" ", "")
            for target in characters:
                target_normalized = target.strip().lower().replace(" ", "")
                if (char_normalized in target_normalized or
                    target_normalized in char_normalized or
                    char_normalized == target_normalized):
                    relevant_chars.append(char_name)
                    break

        if relevant_chars:
            scenes_text.append(f"""
씬 {scene_id}:
- 내용: {script[:300]}
- 등장 캐릭터: {', '.join(relevant_chars)}
""")

    prompt = f"""다음 영상의 각 씬에서 캐릭터들의 적절한 포즈를 분석해주세요.

## 사용 가능한 포즈:
{poses_text}

## 씬 정보:
{''.join(scenes_text)}

## 분석 대상 캐릭터:
{', '.join(characters)}

## 응답 형식 (반드시 유효한 JSON으로만 응답):
{{
  "pose_assignments": [
    {{
      "scene_id": 1,
      "character": "캐릭터명",
      "pose": "포즈ID",
      "reason": "선택 이유 (한 문장)"
    }}
  ]
}}

## 분석 지침:
1. 각 씬의 내용과 분위기를 고려하여 가장 적절한 포즈 선택
2. 캐릭터의 행동이나 상태를 잘 표현하는 포즈 선택
3. 사용 가능한 포즈 목록에 있는 ID만 사용
4. 한 캐릭터가 여러 씬에 등장하면 각 씬별로 분석

반드시 유효한 JSON 형식으로만 응답해주세요. 다른 설명 없이 JSON만 출력하세요.
"""

    return prompt


@dataclass
class PoseAssignment:
    """포즈 할당 결과"""
    scene_id: int
    character: str
    pose: str
    reason: str

    def to_dict(self) -> Dict:
        return {
            "scene_id": self.scene_id,
            "character": self.character,
            "pose": self.pose,
            "reason": self.reason
        }


class PoseAnalyzer:
    """AI 기반 포즈 분석기"""

    def __init__(self, model_id: str = "gemini-2.0-flash-exp"):
        """
        Args:
            model_id: 사용할 AI 모델 ID
        """
        self.model_id = model_id
        self.provider = None
        self.model = None
        self.client = None
        self._init_client()

    def _init_client(self):
        """AI 클라이언트 초기화"""
        model_lower = self.model_id.lower()

        if "gemini" in model_lower:
            try:
                import google.generativeai as genai
                api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY 또는 GEMINI_API_KEY가 설정되지 않았습니다")
                genai.configure(api_key=api_key)
                self.provider = "google"
                self.model = genai.GenerativeModel(self.model_id)
                print(f"[PoseAnalyzer] ✅ Google Gemini 초기화: {self.model_id}")
            except ImportError:
                raise ImportError("google-generativeai 패키지가 설치되지 않았습니다")

        elif "claude" in model_lower:
            try:
                from anthropic import Anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다")
                self.provider = "anthropic"
                self.client = Anthropic(api_key=api_key)
                print(f"[PoseAnalyzer] ✅ Anthropic Claude 초기화: {self.model_id}")
            except ImportError:
                raise ImportError("anthropic 패키지가 설치되지 않았습니다")

        elif "gpt" in model_lower or "openai" in model_lower:
            try:
                from openai import OpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다")
                self.provider = "openai"
                self.client = OpenAI(api_key=api_key)
                print(f"[PoseAnalyzer] ✅ OpenAI 초기화: {self.model_id}")
            except ImportError:
                raise ImportError("openai 패키지가 설치되지 않았습니다")

        else:
            raise ValueError(f"지원하지 않는 모델: {self.model_id}")

    def analyze_poses(
        self,
        scenes: List[Dict],
        characters: List[str],
        progress_callback: Optional[Callable[[float], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> Dict:
        """
        씬별 캐릭터 포즈 분석

        Args:
            scenes: 씬 데이터 리스트
            characters: 분석할 캐릭터 이름 리스트
            progress_callback: 진행률 콜백 (0.0 ~ 1.0)
            status_callback: 상태 메시지 콜백

        Returns:
            {
                "success": True/False,
                "pose_assignments": [...],
                "error": "에러 메시지 (실패시)"
            }
        """
        if status_callback:
            status_callback("프롬프트 생성 중...")

        print(f"[PoseAnalyzer] 분석 시작: {len(scenes)}개 씬, {len(characters)}명 캐릭터")

        # 캐릭터가 등장하는 씬만 필터링
        relevant_scenes = []
        for scene in scenes:
            scene_chars = scene.get("characters", [])
            for c in scene_chars:
                char_name = c if isinstance(c, str) else c.get("name", "")
                char_normalized = char_name.strip().lower().replace(" ", "")
                for target in characters:
                    target_normalized = target.strip().lower().replace(" ", "")
                    if (char_normalized in target_normalized or
                        target_normalized in char_normalized):
                        relevant_scenes.append(scene)
                        break
                else:
                    continue
                break

        if not relevant_scenes:
            print(f"[PoseAnalyzer] ⚠️ 분석할 씬 없음 (캐릭터 매칭 실패)")
            return {
                "success": False,
                "pose_assignments": [],
                "error": "분석 대상 캐릭터가 등장하는 씬을 찾을 수 없습니다."
            }

        # 프롬프트 생성
        prompt = create_pose_analysis_prompt(relevant_scenes, characters)

        if progress_callback:
            progress_callback(0.2)

        if status_callback:
            status_callback(f"AI 분석 중... ({self.model_id})")

        try:
            # AI 호출
            if self.provider == "google":
                response = self.model.generate_content(prompt)
                response_text = response.text

            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model_id,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                response_text = response.content[0].text

            elif self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096
                )
                response_text = response.choices[0].message.content

            if progress_callback:
                progress_callback(0.8)

            if status_callback:
                status_callback("결과 파싱 중...")

            # JSON 파싱
            result = self._parse_response(response_text)

            if progress_callback:
                progress_callback(1.0)

            print(f"[PoseAnalyzer] ✅ 분석 완료: {len(result.get('pose_assignments', []))}개 포즈 할당")

            return {
                "success": True,
                "pose_assignments": result.get("pose_assignments", []),
                "raw_response": response_text
            }

        except Exception as e:
            print(f"[PoseAnalyzer] ❌ 분석 실패: {e}")
            return {
                "success": False,
                "pose_assignments": [],
                "error": str(e)
            }

    def _parse_response(self, response_text: str) -> Dict:
        """AI 응답 파싱"""
        # JSON 블록 추출 (```json ... ``` 또는 순수 JSON)
        json_match = None

        # 1. ```json ... ``` 블록 찾기
        code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response_text)
        if code_block_match:
            json_str = code_block_match.group(1).strip()
        else:
            # 2. 순수 JSON 객체 찾기
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                json_str = json_match.group()
            else:
                raise ValueError("JSON을 찾을 수 없습니다")

        # 파싱
        result = json.loads(json_str)

        # 유효성 검증
        if "pose_assignments" not in result:
            raise ValueError("pose_assignments 키가 없습니다")

        # 포즈 ID 유효성 확인
        valid_poses = set(AVAILABLE_POSES.keys())

        for assignment in result["pose_assignments"]:
            pose = assignment.get("pose", "standing")
            if pose not in valid_poses:
                print(f"[PoseAnalyzer] ⚠️ 유효하지 않은 포즈 '{pose}' → 'standing'으로 대체")
                assignment["pose"] = "standing"

            # scene_id를 정수로 변환
            scene_id = assignment.get("scene_id", 0)
            if isinstance(scene_id, str) and scene_id.isdigit():
                assignment["scene_id"] = int(scene_id)

        return result


def analyze_character_poses(
    scenes: List[Dict],
    characters: List[str],
    model_id: str = "gemini-2.0-flash-exp",
    progress_callback: Optional[Callable[[float], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None
) -> Dict:
    """
    캐릭터 포즈 분석 헬퍼 함수

    Args:
        scenes: 씬 데이터
        characters: 캐릭터 이름 리스트
        model_id: AI 모델 ID
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백

    Returns:
        분석 결과
    """
    analyzer = PoseAnalyzer(model_id=model_id)
    return analyzer.analyze_poses(
        scenes=scenes,
        characters=characters,
        progress_callback=progress_callback,
        status_callback=status_callback
    )


def simple_pose_detection(script_text: str) -> str:
    """
    간단한 키워드 기반 포즈 감지 (AI 폴백용)

    Args:
        script_text: 씬 스크립트 텍스트

    Returns:
        추천 포즈 ID
    """
    text_lower = script_text.lower()

    # 키워드 매칭으로 포즈 추천
    for pose_id, pose_info in AVAILABLE_POSES.items():
        for keyword in pose_info["keywords"]:
            if keyword in text_lower:
                return pose_id

    # 기본값
    return "standing"


def get_pose_info(pose_id: str) -> Dict:
    """포즈 정보 조회"""
    return AVAILABLE_POSES.get(pose_id, AVAILABLE_POSES["standing"])


def get_all_poses() -> Dict[str, Dict]:
    """모든 포즈 정보 반환"""
    return AVAILABLE_POSES.copy()


def get_pose_prompt(pose_id: str) -> str:
    """
    포즈 ID에 해당하는 이미지 생성 프롬프트 반환

    Args:
        pose_id: 포즈 ID (예: "standing", "talking")

    Returns:
        이미지 생성용 프롬프트 문자열
    """
    pose_info = AVAILABLE_POSES.get(pose_id, AVAILABLE_POSES["standing"])
    return pose_info.get("prompt", "standing pose, front view, neutral expression")
