"""
실사이미지 AI 분석 프롬프트 관리자
v1.0: 프롬프트 템플릿 관리, 채널별 기본값 저장
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class RealImageAnalysisPromptManager:
    """실사이미지 분석용 프롬프트 템플릿 관리"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.prompts_dir = self.project_path / "data" / "prompts" / "realimage_analysis"
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
                print(f"[PromptManager] 인덱스 로드 실패: {e}")

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
            print(f"[PromptManager] 인덱스 저장 실패: {e}")

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
                "description": "표준 실사이미지 대체 가능성 분석 프롬프트",
                "content": self._get_default_prompt_content()
            },
            "strict": {
                "name": "엄격 분석",
                "description": "높은 정확도 기준으로 신중하게 분석",
                "content": self._get_strict_prompt_content()
            },
            "lenient": {
                "name": "관대 분석",
                "description": "더 많은 씬을 실사 대체 가능으로 판단",
                "content": self._get_lenient_prompt_content()
            }
        }

    def _get_default_prompt_content(self) -> str:
        """기본 프롬프트 내용"""
        return '''당신은 실사 이미지로 대체 가능한 씬을 분석하는 전문가입니다.

## 분석 기준

### 실사 대체 적합 (suitable=true)
- 풍경, 건물, 자연 사진으로 표현 가능한 씬
- 일반적인 사물, 음식, 제품 사진
- 추상적/개념적이지 않은 구체적 시각 대상
- 스톡 이미지로 쉽게 찾을 수 있는 소재

### 실사 대체 부적합 (suitable=false)
- 특정 캐릭터나 인물이 등장하는 씬
- 애니메이션/만화 스타일이 필요한 씬
- 추상적 개념이나 감정 표현
- 현실에 존재하지 않는 판타지 요소
- 텍스트/인포그래픽이 포함된 씬

## 출력 형식

각 씬에 대해 JSON 배열로 응답:
```json
[
  {
    "scene_id": 1,
    "suitable": true,
    "confidence": 0.85,
    "reason": "도시 풍경 - 스톡 이미지로 대체 가능",
    "search_keywords": ["도시 야경", "스카이라인", "urban skyline"]
  }
]
```

## 주의사항
- confidence는 0.0~1.0 사이 값
- 0.7 이상만 suitable=true로 판단
- search_keywords는 영어 포함 2-3개 제공'''

    def _get_strict_prompt_content(self) -> str:
        """엄격 분석 프롬프트"""
        return '''당신은 실사 이미지 대체 가능성을 **매우 엄격하게** 분석하는 전문가입니다.

## 엄격 분석 기준

### 실사 대체 적합 (suitable=true) - 높은 기준
- **명확히** 실사 사진으로 표현 가능한 씬만 선택
- 고품질 스톡 이미지가 **확실히** 존재하는 소재
- 스타일 변경 없이 자연스럽게 대체 가능한 경우만

### 실사 대체 부적합 (suitable=false) - 확대 적용
- 약간이라도 캐릭터 요소가 있는 씬
- 애니메이션 스타일이 조금이라도 어울리는 씬
- 특정 스타일이나 분위기가 중요한 씬
- 맥락상 일관성이 깨질 수 있는 씬

## 출력 형식

```json
[
  {
    "scene_id": 1,
    "suitable": true,
    "confidence": 0.90,
    "reason": "순수 풍경 - 높은 확신도로 대체 가능",
    "search_keywords": ["keyword1", "keyword2"]
  }
]
```

## 주의사항
- confidence **0.85 이상**만 suitable=true
- 의심스러우면 false로 판단
- 품질 > 수량 원칙'''

    def _get_lenient_prompt_content(self) -> str:
        """관대 분석 프롬프트"""
        return '''당신은 실사 이미지 대체 가능성을 **유연하게** 분석하는 전문가입니다.

## 관대 분석 기준

### 실사 대체 적합 (suitable=true) - 확대 적용
- 배경이 실사로 표현 가능하면 적합
- 주요 요소가 실제 사물이면 적합
- 부분적으로라도 실사 대체 가치가 있으면 적합
- 창의적 해석으로 실사 표현 가능하면 적합

### 실사 대체 부적합 (suitable=false) - 최소 적용
- 캐릭터가 화면의 주요 요소인 경우만
- 완전히 추상적/판타지 요소만 있는 경우
- 텍스트가 핵심인 경우

## 출력 형식

```json
[
  {
    "scene_id": 1,
    "suitable": true,
    "confidence": 0.65,
    "reason": "배경 요소 실사 대체 가능",
    "search_keywords": ["keyword1", "keyword2"]
  }
]
```

## 주의사항
- confidence **0.5 이상**이면 suitable=true 고려
- 가능성이 있으면 true 방향으로
- 수량 > 엄격함 원칙'''

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
            print(f"[PromptManager] 프롬프트 저장 실패: {e}")
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
            print(f"[PromptManager] 프롬프트 로드 실패: {e}")
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
            print(f"[PromptManager] 시스템 프롬프트는 삭제할 수 없습니다: {prompt_id}")
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
            print(f"[PromptManager] 프롬프트 삭제 실패: {e}")
            return False


class ChannelPreferencesManager:
    """채널별 설정 관리자"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.preferences_file = self.project_path / "data" / "channel_preferences.json"

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
                print(f"[ChannelPreferences] 로드 실패: {e}")

        return {
            "version": "1.0",
            "channels": {},
            "global_defaults": {
                "realimage_analysis": {
                    "model": "gemini-2.5-flash",
                    "prompt_id": "default",
                    "auto_apply_threshold": 0.7
                }
            }
        }

    def _save_preferences(self):
        """설정 저장"""
        try:
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self._preferences, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ChannelPreferences] 저장 실패: {e}")

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

    def save_channel_preference(
        self,
        channel_id: str,
        section: str,
        key: str,
        value: Any
    ):
        """채널 설정 저장"""
        if "channels" not in self._preferences:
            self._preferences["channels"] = {}

        if channel_id not in self._preferences["channels"]:
            self._preferences["channels"][channel_id] = {}

        if section not in self._preferences["channels"][channel_id]:
            self._preferences["channels"][channel_id][section] = {}

        self._preferences["channels"][channel_id][section][key] = value
        self._save_preferences()

    def save_realimage_analysis_settings(
        self,
        channel_id: str,
        model: str,
        prompt_id: str,
        auto_apply_threshold: float = 0.7
    ):
        """실사이미지 분석 설정 일괄 저장"""
        if "channels" not in self._preferences:
            self._preferences["channels"] = {}

        if channel_id not in self._preferences["channels"]:
            self._preferences["channels"][channel_id] = {}

        self._preferences["channels"][channel_id]["realimage_analysis"] = {
            "model": model,
            "prompt_id": prompt_id,
            "auto_apply_threshold": auto_apply_threshold,
            "updated_at": datetime.now().isoformat()
        }

        self._save_preferences()

    def get_realimage_analysis_settings(self, channel_id: str) -> Dict:
        """실사이미지 분석 설정 조회"""
        prefs = self.get_channel_preferences(channel_id)
        return prefs.get("realimage_analysis", {
            "model": "gemini-2.5-flash",
            "prompt_id": "default",
            "auto_apply_threshold": 0.7
        })

    def get_last_used_model(self, channel_id: str) -> str:
        """마지막 사용 모델 조회"""
        settings = self.get_realimage_analysis_settings(channel_id)
        return settings.get("model", "gemini-2.5-flash")

    def get_last_used_prompt(self, channel_id: str) -> str:
        """마지막 사용 프롬프트 ID 조회"""
        settings = self.get_realimage_analysis_settings(channel_id)
        return settings.get("prompt_id", "default")
