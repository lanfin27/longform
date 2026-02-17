# -*- coding: utf-8 -*-
"""
인포그래픽 AI 분석 프롬프트 관리자 (v1.0)
프롬프트 템플릿 관리, 채널별 기본값 저장
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class InfographicAnalysisPromptManager:
    """인포그래픽 분석용 프롬프트 템플릿 관리"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.prompts_dir = self.project_path / "data" / "prompts" / "infographic_analysis"
        self.index_file = self.prompts_dir / "prompts_index.json"

        # 디렉토리 생성
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

        # 인덱스 로드 또는 초기화
        self._index = self._load_index()

        # 기본 템플릿 확인 및 생성
        self._ensure_default_templates()

    def _load_index(self) -> Dict:
        """프롬프트 인덱스 로드"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[InfographicPromptManager] 인덱스 로드 실패: {e}")

        return {
            "version": "1.0",
            "prompts": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

    def _save_index(self):
        """프롬프트 인덱스 저장"""
        self._index["updated_at"] = datetime.now().isoformat()
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[InfographicPromptManager] 인덱스 저장 실패: {e}")

    def _ensure_default_templates(self):
        """기본 프롬프트 템플릿 확인 및 생성"""
        default_prompts = self._get_default_prompts()

        for prompt_id, prompt_data in default_prompts.items():
            if prompt_id not in self._index.get("prompts", {}):
                self.save_prompt(
                    prompt_id=prompt_id,
                    name=prompt_data["name"],
                    description=prompt_data["description"],
                    content=prompt_data["content"],
                    is_system=True
                )

    def _get_default_prompts(self) -> Dict[str, Dict]:
        """기본 프롬프트 정의"""
        return {
            "default": {
                "name": "기본 분석",
                "description": "표준 인포그래픽 대체 가능성 분석 프롬프트",
                "content": self._get_default_prompt_content()
            },
            "data_focused": {
                "name": "데이터 중심",
                "description": "숫자/통계 데이터 추출에 집중하는 프롬프트",
                "content": self._get_data_focused_prompt_content()
            },
            "comparison": {
                "name": "비교 분석",
                "description": "비교/대조 요소 추출에 집중하는 프롬프트",
                "content": self._get_comparison_prompt_content()
            },
            "timeline": {
                "name": "타임라인 분석",
                "description": "시간순/단계별 프로세스 추출에 집중하는 프롬프트",
                "content": self._get_timeline_prompt_content()
            }
        }

    def _get_default_prompt_content(self) -> str:
        """기본 프롬프트 내용"""
        return '''당신은 인포그래픽으로 대체 가능한 씬을 분석하는 전문가입니다.

## 분석 기준

### 인포그래픽 대체 적합 (suitable=true)
- 숫자, 통계, 비율 등 데이터가 언급되는 씬
- 여러 항목을 비교/대조하는 내용
- 단계별 프로세스나 순서를 설명하는 내용
- 목록이나 체크리스트 형태의 내용
- 타임라인이나 시간 흐름을 설명하는 내용

### 인포그래픽 대체 부적합 (suitable=false)
- 감정적인 스토리텔링이 중요한 씬
- 특정 캐릭터나 인물의 표정/행동이 중요한 씬
- 분위기나 배경 묘사가 핵심인 씬
- 추상적인 개념이나 철학적 내용

## 출력 형식

각 씬에 대해 JSON 배열로 응답:
```json
[
  {
    "scene_id": 1,
    "suitable": true,
    "confidence": 0.85,
    "reason": "통계 데이터 3개 포함 - 차트로 시각화 적합",
    "recommended_type": "chart",
    "extracted_data": {
      "type": "statistics",
      "items": ["항목1: 50%", "항목2: 30%", "항목3: 20%"]
    }
  }
]
```

## 인포그래픽 타입
- chart: 차트/그래프 (막대, 원형, 선)
- comparison: 비교 표/다이어그램
- timeline: 타임라인/흐름도
- process: 단계별 프로세스
- list: 목록/체크리스트
- mixed: 복합 타입

## 주의사항
- confidence는 0.0~1.0 사이 값
- 0.6 이상만 suitable=true로 판단
- extracted_data에 인포그래픽으로 표현할 핵심 데이터 추출'''

    def _get_data_focused_prompt_content(self) -> str:
        """데이터 중심 프롬프트"""
        return '''당신은 인포그래픽에 적합한 **데이터와 통계**를 추출하는 전문가입니다.

## 분석 기준

### 데이터 추출 대상
- 숫자, 퍼센트, 비율
- 금액, 수량, 기간
- 순위, 등급, 점수
- 측정값, 지표

### 특히 주목할 패턴
- "X%가...", "X명 중 Y명이..."
- "평균 X...", "최대 X..."
- "X배 증가/감소..."
- "A보다 B가 X% 더..."

## 출력 형식

```json
[
  {
    "scene_id": 1,
    "suitable": true,
    "confidence": 0.90,
    "reason": "구체적 통계 데이터 4개 포함",
    "recommended_type": "chart",
    "extracted_data": {
      "type": "statistics",
      "chart_type": "bar",
      "title": "추출된 제목",
      "items": [
        {"label": "항목A", "value": 50, "unit": "%"},
        {"label": "항목B", "value": 30, "unit": "%"}
      ]
    }
  }
]
```

## 주의사항
- 숫자가 없어도 비교 가능한 내용이면 추출
- 원본 스크립트의 맥락을 유지하며 데이터 정리
- confidence 0.7 이상만 suitable=true'''

    def _get_comparison_prompt_content(self) -> str:
        """비교 분석 프롬프트"""
        return '''당신은 인포그래픽에 적합한 **비교/대조 요소**를 추출하는 전문가입니다.

## 분석 기준

### 비교 추출 대상
- A vs B 형태의 비교
- 장점/단점, 찬성/반대
- 전/후 비교
- 옵션 비교

### 특히 주목할 패턴
- "A는 ~하지만, B는 ~"
- "~와 달리, ~는"
- "반면에, 한편으로는"
- "기존에는 ~ 이제는 ~"

## 출력 형식

```json
[
  {
    "scene_id": 1,
    "suitable": true,
    "confidence": 0.85,
    "reason": "A vs B 명확한 비교 구조",
    "recommended_type": "comparison",
    "extracted_data": {
      "type": "comparison",
      "comparison_type": "vs",
      "title": "A vs B 비교",
      "items": [
        {"category": "속도", "item_a": "빠름", "item_b": "느림"},
        {"category": "비용", "item_a": "비쌈", "item_b": "저렴"}
      ]
    }
  }
]
```

## 주의사항
- 비교 항목이 2개 이상일 때 적합
- 단순 나열이 아닌 대비되는 요소 추출
- confidence 0.65 이상만 suitable=true'''

    def _get_timeline_prompt_content(self) -> str:
        """타임라인 분석 프롬프트"""
        return '''당신은 인포그래픽에 적합한 **시간순/단계별 프로세스**를 추출하는 전문가입니다.

## 분석 기준

### 타임라인/프로세스 추출 대상
- 단계별 설명 (1단계, 2단계...)
- 시간 순서 (먼저, 그 다음, 마지막으로)
- 역사적 흐름 (년도별)
- 절차/방법 설명

### 특히 주목할 패턴
- "먼저 ~, 그 다음 ~, 마지막으로 ~"
- "첫 번째, 두 번째, 세 번째..."
- "~한 후에, ~하기 전에"
- "19XX년에 ~, 20XX년에 ~"

## 출력 형식

```json
[
  {
    "scene_id": 1,
    "suitable": true,
    "confidence": 0.88,
    "reason": "4단계 프로세스 명확히 설명",
    "recommended_type": "process",
    "extracted_data": {
      "type": "process",
      "process_type": "steps",
      "title": "프로세스 제목",
      "steps": [
        {"order": 1, "title": "단계1", "description": "설명"},
        {"order": 2, "title": "단계2", "description": "설명"}
      ]
    }
  }
]
```

## 주의사항
- 최소 3단계 이상일 때 적합
- 순서가 중요한 내용만 추출
- confidence 0.7 이상만 suitable=true'''

    def save_prompt(
        self,
        prompt_id: str,
        name: str,
        description: str,
        content: str,
        is_system: bool = False
    ) -> bool:
        """프롬프트 저장"""
        try:
            # 프롬프트 파일 저장
            prompt_file = self.prompts_dir / f"{prompt_id}.md"
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(content)

            # 인덱스 업데이트
            if "prompts" not in self._index:
                self._index["prompts"] = {}

            self._index["prompts"][prompt_id] = {
                "name": name,
                "description": description,
                "file": f"{prompt_id}.md",
                "is_system": is_system,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            self._save_index()
            return True

        except Exception as e:
            print(f"[InfographicPromptManager] 프롬프트 저장 실패: {e}")
            return False

    def get_prompt(self, prompt_id: str) -> Optional[Dict]:
        """프롬프트 조회"""
        if prompt_id not in self._index.get("prompts", {}):
            return None

        prompt_info = self._index["prompts"][prompt_id].copy()
        prompt_file = self.prompts_dir / prompt_info["file"]

        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_info["content"] = f.read()
            return prompt_info
        except Exception as e:
            print(f"[InfographicPromptManager] 프롬프트 로드 실패: {e}")
            return None

    def list_prompts(self) -> List[Dict]:
        """모든 프롬프트 목록"""
        prompts = []
        for prompt_id, info in self._index.get("prompts", {}).items():
            prompts.append({
                "id": prompt_id,
                "name": info["name"],
                "description": info["description"],
                "is_system": info.get("is_system", False),
                "updated_at": info.get("updated_at", "")
            })
        return prompts

    def delete_prompt(self, prompt_id: str) -> bool:
        """프롬프트 삭제 (시스템 프롬프트는 삭제 불가)"""
        if prompt_id not in self._index.get("prompts", {}):
            return False

        if self._index["prompts"][prompt_id].get("is_system", False):
            print(f"[InfographicPromptManager] 시스템 프롬프트는 삭제할 수 없습니다: {prompt_id}")
            return False

        try:
            # 파일 삭제
            prompt_file = self.prompts_dir / self._index["prompts"][prompt_id]["file"]
            if prompt_file.exists():
                prompt_file.unlink()

            # 인덱스에서 제거
            del self._index["prompts"][prompt_id]
            self._save_index()
            return True

        except Exception as e:
            print(f"[InfographicPromptManager] 프롬프트 삭제 실패: {e}")
            return False

    def duplicate_prompt(self, source_id: str, new_id: str, new_name: str) -> bool:
        """프롬프트 복제"""
        source = self.get_prompt(source_id)
        if not source:
            return False

        return self.save_prompt(
            prompt_id=new_id,
            name=new_name,
            description=f"{source['description']} (복제)",
            content=source["content"],
            is_system=False
        )


class InfographicChannelPreferences:
    """인포그래픽 채널별 설정 관리자"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.preferences_file = self.project_path / "data" / "infographic_channel_preferences.json"

        # 디렉토리 확인
        self.preferences_file.parent.mkdir(parents=True, exist_ok=True)

        # 설정 로드
        self._preferences = self._load_preferences()

    def _load_preferences(self) -> Dict:
        """설정 로드"""
        if self.preferences_file.exists():
            try:
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[InfographicChannelPreferences] 로드 실패: {e}")

        return {
            "version": "1.0",
            "channels": {},
            "global_defaults": {
                "infographic_analysis": {
                    "model": "gemini-2.5-flash",
                    "prompt_id": "default",
                    "auto_apply_threshold": 0.6,
                    "style": "modern_dark",
                    "color_scheme": "auto"
                }
            }
        }

    def _save_preferences(self):
        """설정 저장"""
        try:
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self._preferences, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[InfographicChannelPreferences] 저장 실패: {e}")

    def get_channel_preferences(self, channel_id: str) -> Dict:
        """채널별 설정 조회"""
        channel_prefs = self._preferences.get("channels", {}).get(channel_id, {})
        global_defaults = self._preferences.get("global_defaults", {})

        # 전역 기본값과 병합 (채널 설정 우선)
        result = {}
        for section, defaults in global_defaults.items():
            result[section] = defaults.copy()
            if section in channel_prefs:
                result[section].update(channel_prefs[section])

        # 채널에만 있는 설정 추가
        for section, values in channel_prefs.items():
            if section not in result:
                result[section] = values

        return result

    def save_infographic_analysis_settings(
        self,
        channel_id: str,
        model: str,
        prompt_id: str,
        auto_apply_threshold: float = 0.6,
        style: str = "modern_dark",
        color_scheme: str = "auto"
    ):
        """인포그래픽 분석 설정 일괄 저장"""
        if "channels" not in self._preferences:
            self._preferences["channels"] = {}

        if channel_id not in self._preferences["channels"]:
            self._preferences["channels"][channel_id] = {}

        self._preferences["channels"][channel_id]["infographic_analysis"] = {
            "model": model,
            "prompt_id": prompt_id,
            "auto_apply_threshold": auto_apply_threshold,
            "style": style,
            "color_scheme": color_scheme,
            "updated_at": datetime.now().isoformat()
        }

        self._save_preferences()

    def get_infographic_analysis_settings(self, channel_id: str) -> Dict:
        """인포그래픽 분석 설정 조회"""
        prefs = self.get_channel_preferences(channel_id)
        return prefs.get("infographic_analysis", {
            "model": "gemini-2.5-flash",
            "prompt_id": "default",
            "auto_apply_threshold": 0.6,
            "style": "modern_dark",
            "color_scheme": "auto"
        })

    def get_last_used_model(self, channel_id: str) -> str:
        """마지막 사용 모델 조회"""
        settings = self.get_infographic_analysis_settings(channel_id)
        return settings.get("model", "gemini-2.5-flash")

    def get_last_used_prompt(self, channel_id: str) -> str:
        """마지막 사용 프롬프트 ID 조회"""
        settings = self.get_infographic_analysis_settings(channel_id)
        return settings.get("prompt_id", "default")
