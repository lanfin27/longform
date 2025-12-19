"""
AI 합성 분석 엔진

씬 분석 내용, 배경 프롬프트, 캐릭터 정보를 분석하여
최적의 캐릭터 배치(크기, 위치, 포즈)를 결정
"""
import json
import re
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class CharacterPlacement:
    """캐릭터 배치 정보"""
    character_name: str
    position_x: float        # 0.0 ~ 1.0 (왼쪽 ~ 오른쪽)
    position_y: float        # 0.0 ~ 1.0 (위 ~ 아래)
    scale: float             # 0.1 ~ 1.0 (배경 대비 크기)
    z_order: int             # 레이어 순서 (0이 가장 뒤)
    flip_horizontal: bool    # 좌우 반전 여부
    reasoning: str           # AI의 배치 이유

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterPlacement":
        return cls(**data)


@dataclass
class CompositionAnalysis:
    """합성 분석 결과"""
    scene_id: int
    scene_type: str              # "dialogue", "action", "establishing", "close-up" 등
    camera_angle: str            # "wide", "medium", "close-up" 등
    focal_point: Tuple[float, float]  # 시선 집중점
    character_placements: List[CharacterPlacement]
    composition_notes: str       # 전체 구도 설명

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "scene_type": self.scene_type,
            "camera_angle": self.camera_angle,
            "focal_point": list(self.focal_point),
            "character_placements": [cp.to_dict() for cp in self.character_placements],
            "composition_notes": self.composition_notes
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompositionAnalysis":
        placements = [CharacterPlacement.from_dict(p) for p in data.get("character_placements", [])]
        focal = data.get("focal_point", [0.5, 0.5])
        return cls(
            scene_id=data.get("scene_id", 0),
            scene_type=data.get("scene_type", "dialogue"),
            camera_angle=data.get("camera_angle", "medium"),
            focal_point=tuple(focal) if isinstance(focal, list) else focal,
            character_placements=placements,
            composition_notes=data.get("composition_notes", "")
        )


class AICompositionAnalyzer:
    """AI 합성 분석기"""

    # 씬 타입별 기본 레이아웃
    SCENE_TYPE_LAYOUTS = {
        "dialogue": {
            "description": "대화 장면 - 두 캐릭터가 서로 마주보는 구도",
            "positions": [(0.25, 0.80), (0.75, 0.80)],
            "scales": [0.55, 0.55],
            "flip": [False, True]
        },
        "monologue": {
            "description": "독백/나레이션 - 한 캐릭터 중앙 배치",
            "positions": [(0.5, 0.75)],
            "scales": [0.6],
            "flip": [False]
        },
        "group": {
            "description": "그룹 장면 - 여러 캐릭터 균등 배치",
            "positions": [(0.15, 0.80), (0.38, 0.80), (0.62, 0.80), (0.85, 0.80)],
            "scales": [0.45, 0.45, 0.45, 0.45],
            "flip": [False, False, True, True]
        },
        "confrontation": {
            "description": "대립 장면 - 긴장감 있는 양측 배치",
            "positions": [(0.2, 0.75), (0.8, 0.75)],
            "scales": [0.6, 0.6],
            "flip": [False, True]
        },
        "establishing": {
            "description": "전경 장면 - 배경 중심, 캐릭터 작게",
            "positions": [(0.5, 0.88)],
            "scales": [0.3],
            "flip": [False]
        },
        "close_up": {
            "description": "클로즈업 - 캐릭터 크게 중앙",
            "positions": [(0.5, 0.65)],
            "scales": [0.8],
            "flip": [False]
        },
        "action": {
            "description": "액션 장면 - 역동적 배치",
            "positions": [(0.3, 0.70), (0.7, 0.78)],
            "scales": [0.6, 0.5],
            "flip": [False, True]
        },
        "interview": {
            "description": "인터뷰 장면 - 한쪽에 치우친 배치",
            "positions": [(0.35, 0.75)],
            "scales": [0.65],
            "flip": [False]
        },
        "presentation": {
            "description": "프레젠테이션 - 중앙 아래 배치",
            "positions": [(0.5, 0.85)],
            "scales": [0.5],
            "flip": [False]
        }
    }

    # 카메라 앵글별 스케일 조정
    CAMERA_SCALE_ADJUSTMENTS = {
        "extreme_wide": 0.4,
        "wide": 0.6,
        "medium_wide": 0.75,
        "medium": 0.85,
        "medium_close": 0.95,
        "close_up": 1.1,
        "extreme_close_up": 1.3
    }

    def __init__(self, api_provider: str = "anthropic"):
        """
        Args:
            api_provider: "anthropic" 또는 "gemini"
        """
        self.api_provider = api_provider
        self.client = None
        self.model = None

    def _init_api(self):
        """API 클라이언트 초기화 (lazy)"""
        if self.client is not None:
            return

        if self.api_provider == "anthropic":
            try:
                import anthropic
                self.client = anthropic.Anthropic(
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
                self.model = "claude-sonnet-4-20250514"
            except ImportError:
                print("[AICompositionAnalyzer] anthropic 모듈이 없습니다.")
                self.client = None

        elif self.api_provider == "gemini":
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                self.client = genai.GenerativeModel('gemini-1.5-flash-latest')
                self.model = "gemini-1.5-flash-latest"
            except ImportError:
                print("[AICompositionAnalyzer] google-generativeai 모듈이 없습니다.")
                self.client = None

    def analyze_composition(
        self,
        scene: dict,
        background_prompt: str,
        characters: List[dict],
        use_ai: bool = True,
        api_provider: str = None
    ) -> CompositionAnalysis:
        """
        합성 구도 분석

        Args:
            scene: 씬 분석 결과
            background_prompt: 배경 이미지 생성에 사용된 프롬프트
            characters: 합성할 캐릭터 목록
            use_ai: AI 분석 사용 여부 (False면 규칙 기반)
            api_provider: AI 제공자 (None이면 인스턴스 기본값 사용)

        Returns:
            CompositionAnalysis: 합성 분석 결과
        """
        scene_id = scene.get("scene_id", 0)

        # api_provider가 전달되고 현재와 다르면 재초기화
        if api_provider and api_provider != self.api_provider:
            print(f"[AICompositionAnalyzer] API 제공자 변경: {self.api_provider} -> {api_provider}")
            self.api_provider = api_provider
            self.client = None  # 클라이언트 리셋
            self.model = None

        print(f"[AICompositionAnalyzer] 씬 {scene_id} 합성 분석 시작")
        print(f"  캐릭터 수: {len(characters)}")
        print(f"  AI 분석: {use_ai}")
        print(f"  API 제공자: {self.api_provider}")

        if use_ai:
            return self._analyze_with_ai(scene, background_prompt, characters)
        else:
            return self._analyze_with_rules(scene, background_prompt, characters)

    def _analyze_with_ai(
        self,
        scene: dict,
        background_prompt: str,
        characters: List[dict]
    ) -> CompositionAnalysis:
        """AI를 사용한 합성 분석"""
        scene_id = scene.get("scene_id", 0)

        # API 초기화
        self._init_api()

        if self.client is None:
            print("[AICompositionAnalyzer] API 클라이언트 없음, 규칙 기반으로 폴백")
            return self._analyze_with_rules(scene, background_prompt, characters)

        # 분석 프롬프트 구성
        prompt = self._build_analysis_prompt(scene, background_prompt, characters)

        try:
            if self.api_provider == "anthropic":
                response = self._call_anthropic(prompt)
            else:
                response = self._call_gemini(prompt)

            # 응답 파싱
            analysis = self._parse_ai_response(response, scene_id, characters)

            print(f"[AICompositionAnalyzer] AI 분석 완료")
            print(f"  씬 타입: {analysis.scene_type}")
            print(f"  카메라: {analysis.camera_angle}")

            return analysis

        except Exception as e:
            print(f"[AICompositionAnalyzer] AI 분석 실패: {e}")
            print(f"  규칙 기반 분석으로 폴백")
            return self._analyze_with_rules(scene, background_prompt, characters)

    def _build_analysis_prompt(
        self,
        scene: dict,
        background_prompt: str,
        characters: List[dict]
    ) -> str:
        """AI 분석용 프롬프트 생성"""
        # 씬 정보
        script_text = scene.get("script_text", "")
        direction_guide = scene.get("direction_guide", "")
        camera_suggestion = scene.get("camera_suggestion", "")
        mood = scene.get("mood", "")
        scene_characters = scene.get("characters", [])

        # 캐릭터 정보
        char_info = []
        for char in characters:
            name = char.get("name", "Unknown")
            role = char.get("role", "등장인물")
            visual = (char.get("visual_prompt") or char.get("character_prompt") or "")[:100]
            char_info.append(f"- {name} ({role}): {visual}")

        prompt = f"""당신은 영상/애니메이션 합성 전문가입니다.
아래 씬 정보를 분석하여 캐릭터들을 배경 이미지에 어떻게 배치할지 결정해주세요.

## 씬 정보

### 스크립트
{script_text[:500]}

### 연출 가이드
{direction_guide}

### 카메라 제안
{camera_suggestion}

### 분위기
{mood}

### 배경 이미지 프롬프트
{background_prompt}

## 합성할 캐릭터
{chr(10).join(char_info)}

## 분석 요청

위 정보를 바탕으로 각 캐릭터의 최적 배치를 JSON 형식으로 제공해주세요:

```json
{{
  "scene_type": "dialogue|monologue|group|confrontation|establishing|close_up|action|interview|presentation",
  "camera_angle": "wide|medium|close_up",
  "focal_point": [x, y],
  "composition_notes": "전체 구도에 대한 설명",
  "character_placements": [
    {{
      "character_name": "캐릭터 이름",
      "position_x": 0.0~1.0,
      "position_y": 0.0~1.0,
      "scale": 0.1~1.0,
      "z_order": 0~10,
      "flip_horizontal": true|false,
      "reasoning": "이 배치를 선택한 이유"
    }}
  ]
}}
```

### 배치 가이드라인
- position_x: 0.0(왼쪽) ~ 1.0(오른쪽), 0.5가 중앙
- position_y: 0.0(위) ~ 1.0(아래), 0.7~0.85가 일반적인 캐릭터 위치
- scale: 배경 대비 캐릭터 크기 (0.3=작게, 0.5=중간, 0.7=크게)
- z_order: 레이어 순서 (숫자가 클수록 앞에 배치)
- flip_horizontal: 오른쪽을 바라보게 할지 여부

### 고려 사항
1. 대화 장면은 캐릭터가 서로 마주보게
2. 주인공은 더 크게, 중앙에 가깝게
3. 카메라 앵글에 따라 크기 조정
4. 씬의 분위기와 긴장감 반영
5. 시선 흐름과 구도의 균형

JSON만 출력하세요."""

        return prompt

    def _call_anthropic(self, prompt: str) -> str:
        """Anthropic API 호출"""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text

    def _call_gemini(self, prompt: str) -> str:
        """Gemini API 호출"""
        response = self.client.generate_content(prompt)
        return response.text

    def _parse_ai_response(
        self,
        response: str,
        scene_id: int,
        characters: List[dict]
    ) -> CompositionAnalysis:
        """AI 응답 파싱"""
        # JSON 추출
        json_match = re.search(r'\{[\s\S]*\}', response)

        if not json_match:
            raise ValueError("JSON 응답을 찾을 수 없음")

        data = json.loads(json_match.group())

        # CharacterPlacement 생성
        placements = []

        for cp in data.get("character_placements", []):
            placement = CharacterPlacement(
                character_name=cp.get("character_name", ""),
                position_x=float(cp.get("position_x", 0.5)),
                position_y=float(cp.get("position_y", 0.75)),
                scale=float(cp.get("scale", 0.5)),
                z_order=int(cp.get("z_order", 0)),
                flip_horizontal=bool(cp.get("flip_horizontal", False)),
                reasoning=cp.get("reasoning", "")
            )
            placements.append(placement)

        # 누락된 캐릭터 기본 배치 추가
        placed_names = {p.character_name for p in placements}
        for i, char in enumerate(characters):
            name = char.get("name", f"character_{i}")
            if name not in placed_names:
                placements.append(CharacterPlacement(
                    character_name=name,
                    position_x=0.3 + 0.4 * i / max(len(characters), 1),
                    position_y=0.78,
                    scale=0.5,
                    z_order=i,
                    flip_horizontal=i % 2 == 1,
                    reasoning="기본 배치 (AI 분석에서 누락)"
                ))

        # 초점 처리
        focal = data.get("focal_point", [0.5, 0.5])
        if isinstance(focal, list) and len(focal) >= 2:
            focal_point = (float(focal[0]), float(focal[1]))
        else:
            focal_point = (0.5, 0.5)

        return CompositionAnalysis(
            scene_id=scene_id,
            scene_type=data.get("scene_type", "dialogue"),
            camera_angle=data.get("camera_angle", "medium"),
            focal_point=focal_point,
            character_placements=placements,
            composition_notes=data.get("composition_notes", "")
        )

    def _analyze_with_rules(
        self,
        scene: dict,
        background_prompt: str,
        characters: List[dict]
    ) -> CompositionAnalysis:
        """규칙 기반 합성 분석 (AI 대안)"""
        scene_id = scene.get("scene_id", 0)
        num_chars = len(characters)

        # 씬 타입 추론
        direction = (scene.get("direction_guide", "") or "").lower()
        camera = (scene.get("camera_suggestion", "") or "").lower()
        script = (scene.get("script_text", "") or "").lower()

        # 키워드 기반 씬 타입 결정
        if any(kw in direction for kw in ["대화", "dialogue", "말하", "대답", "묻"]):
            scene_type = "dialogue"
        elif any(kw in direction for kw in ["대립", "갈등", "confrontation", "마주"]):
            scene_type = "confrontation"
        elif any(kw in direction for kw in ["인터뷰", "interview"]):
            scene_type = "interview"
        elif any(kw in direction for kw in ["발표", "presentation", "설명"]):
            scene_type = "presentation"
        elif any(kw in camera for kw in ["wide", "와이드", "전경", "establishing"]):
            scene_type = "establishing"
        elif any(kw in camera for kw in ["close", "클로즈", "접사"]):
            scene_type = "close_up"
        elif any(kw in direction for kw in ["액션", "action", "싸움", "추격"]):
            scene_type = "action"
        elif num_chars == 1:
            scene_type = "monologue"
        elif num_chars == 2:
            scene_type = "dialogue"
        elif num_chars > 3:
            scene_type = "group"
        else:
            scene_type = "dialogue"

        # 카메라 앵글 추론
        if any(kw in camera for kw in ["wide", "와이드", "전경"]):
            camera_angle = "wide"
        elif any(kw in camera for kw in ["close", "클로즈", "접사"]):
            camera_angle = "close_up"
        elif any(kw in camera for kw in ["medium", "미디엄", "중간"]):
            camera_angle = "medium"
        else:
            camera_angle = "medium"

        # 레이아웃 가져오기
        layout = self.SCENE_TYPE_LAYOUTS.get(scene_type, self.SCENE_TYPE_LAYOUTS["dialogue"])

        # 캐릭터 배치 생성
        placements = []

        for i, char in enumerate(characters):
            if i < len(layout["positions"]):
                pos = layout["positions"][i]
                scale = layout["scales"][i]
                flip = layout["flip"][i]
            else:
                # 추가 캐릭터는 균등 분배
                pos = (0.15 + 0.7 * i / max(num_chars - 1, 1), 0.80)
                scale = 0.4
                flip = i % 2 == 1

            # 카메라 앵글에 따른 스케일 조정
            scale_adj = self.CAMERA_SCALE_ADJUSTMENTS.get(camera_angle, 1.0)
            adjusted_scale = min(scale * scale_adj, 0.9)

            # 역할에 따른 조정
            role = char.get("role", "").lower()
            if any(kw in role for kw in ["주연", "주인공", "main", "protagonist"]):
                adjusted_scale = min(adjusted_scale * 1.1, 0.95)

            placements.append(CharacterPlacement(
                character_name=char.get("name", f"character_{i}"),
                position_x=pos[0],
                position_y=pos[1],
                scale=adjusted_scale,
                z_order=i,
                flip_horizontal=flip,
                reasoning=f"{scene_type} 레이아웃의 {i+1}번째 위치"
            ))

        print(f"[AICompositionAnalyzer] 규칙 기반 분석 완료")
        print(f"  씬 타입: {scene_type}")
        print(f"  레이아웃: {layout['description']}")

        return CompositionAnalysis(
            scene_id=scene_id,
            scene_type=scene_type,
            camera_angle=camera_angle,
            focal_point=(0.5, 0.5),
            character_placements=placements,
            composition_notes=layout["description"]
        )


def get_composition_analyzer(api_provider: str = "anthropic") -> AICompositionAnalyzer:
    """AICompositionAnalyzer 인스턴스 가져오기"""
    return AICompositionAnalyzer(api_provider=api_provider)
