"""
Chatterbox TTS API 클라이언트
기존 Streamlit 툴에서 사용

사용법:
    from core.tts.chatterbox_client import chatterbox_client

    # 연결 확인
    if chatterbox_client.check_connection():
        # 모델 로드
        chatterbox_client.load_model()

        # TTS 생성
        result = chatterbox_client.generate_preview("안녕하세요")
"""

import os
import requests
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

# 텍스트 정규화기 (지연 로딩)
_text_normalizer = None

def get_text_normalizer():
    """텍스트 정규화기 지연 로딩"""
    global _text_normalizer
    if _text_normalizer is None:
        try:
            from utils.text_normalizer import normalize_for_tts
            _text_normalizer = normalize_for_tts
            logger.info("[TextNorm] 정규화기 로드 완료")
        except ImportError as e:
            logger.warning(f"[TextNorm] 정규화기 로드 실패: {e}")
            _text_normalizer = lambda x: x  # 패스스루
    return _text_normalizer

# longform 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


def resolve_voice_path(voice_path: str) -> str:
    """
    음성 파일 경로를 절대 경로로 변환

    Args:
        voice_path: 상대 또는 절대 경로

    Returns:
        절대 경로 문자열
    """
    if not voice_path:
        return voice_path

    # 이미 절대 경로인 경우
    if os.path.isabs(voice_path):
        if os.path.exists(voice_path):
            return voice_path
        logger.warning(f"[VoicePath] 절대 경로 파일 없음: {voice_path}")
        return voice_path

    # 상대 경로 → 절대 경로 변환
    absolute_path = PROJECT_ROOT / voice_path

    if absolute_path.exists():
        resolved = str(absolute_path.resolve())
        logger.info(f"[VoicePath] ✅ 상대→절대 변환: {voice_path} → {resolved}")
        return resolved

    # 대체 경로 탐색
    alternative_dirs = [
        PROJECT_ROOT / "data" / "voice_samples" / "default",
        PROJECT_ROOT / "data" / "voice_samples" / "optimized",
        PROJECT_ROOT / "data" / "voice_samples",
    ]

    filename = Path(voice_path).name
    stem = Path(voice_path).stem

    for alt_dir in alternative_dirs:
        if not alt_dir.exists():
            continue

        # 정확한 파일명 매칭
        exact_match = alt_dir / filename
        if exact_match.exists():
            resolved = str(exact_match.resolve())
            logger.info(f"[VoicePath] ✅ 대체 경로 발견: {resolved}")
            return resolved

        # stem 기반 매칭
        for file in alt_dir.glob("*.mp3"):
            if stem in file.stem:
                resolved = str(file.resolve())
                logger.info(f"[VoicePath] ✅ 유사 파일 발견: {resolved}")
                return resolved

    logger.warning(f"[VoicePath] ⚠️ 파일 없음: {voice_path}")
    return str(absolute_path.resolve())


class ChatterboxTTSClient:
    """TTS API 클라이언트"""

    def __init__(self, base_url: str = "http://localhost:8100"):
        self.base_url = base_url
        self._connected = False
        self._status_cache = None

        # Timeout settings
        self.timeout = 30              # 일반 요청
        self.load_timeout = 900        # 모델 로드: 15분 (첫 다운로드 포함)
        self.generate_timeout = 600    # TTS 생성: 10분

    def check_connection(self) -> bool:
        """서버 연결 확인"""
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            self._connected = r.status_code == 200
            if self._connected:
                logger.info("Chatterbox TTS 서버 연결됨")
            return self._connected
        except requests.exceptions.RequestException as e:
            logger.warning(f"Chatterbox TTS 서버 연결 실패: {e}")
            self._connected = False
            return False

    def get_status(self) -> Dict:
        """모델 상태 확인"""
        try:
            r = requests.get(f"{self.base_url}/status", timeout=5)
            r.raise_for_status()
            self._status_cache = r.json()
            return self._status_cache
        except requests.exceptions.RequestException as e:
            logger.error(f"상태 확인 실패: {e}")
            return {
                "loaded": False,
                "device": "unknown",
                "error": str(e)
            }

    def is_model_loaded(self) -> bool:
        """모델 로드 여부 확인"""
        status = self.get_status()
        return status.get("loaded", False)

    def load_model(self, multilingual: bool = True) -> Dict:
        """모델 로드 - 15분 타임아웃 (첫 다운로드 시 오래 걸림)"""
        try:
            logger.info(f"모델 로드 요청 (타임아웃: {self.load_timeout}초)")
            r = requests.post(
                f"{self.base_url}/load",
                params={"multilingual": multilingual},
                timeout=self.load_timeout  # 15분
            )
            r.raise_for_status()
            result = r.json()
            logger.info(f"모델 로드 완료: {result}")
            return result
        except requests.exceptions.Timeout:
            logger.error("모델 로드 타임아웃")
            return {
                "status": "timeout",
                "error": "모델 로딩 시간 초과. 서버 콘솔에서 진행 상황을 확인하세요."
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"모델 로드 실패: {e}")
            return {"status": "error", "error": str(e)}

    def unload_model(self) -> Dict:
        """모델 언로드 (이미지 생성 전 호출)"""
        try:
            r = requests.post(f"{self.base_url}/unload", timeout=30)
            r.raise_for_status()
            result = r.json()
            logger.info(f"모델 언로드 완료: {result}")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"모델 언로드 실패: {e}")
            return {"status": "error", "error": str(e)}

    def get_voices(self, language: str = None) -> List[Dict]:
        """음성 목록 조회"""
        try:
            if language:
                r = requests.get(f"{self.base_url}/voices/{language}", timeout=10)
            else:
                r = requests.get(f"{self.base_url}/voices", timeout=10)
            r.raise_for_status()
            return r.json().get("voices", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"음성 목록 조회 실패: {e}")
            return []

    def generate_preview(
        self,
        text: str,
        language: str = "ko",
        voice_name: str = "default",
        speed: float = 1.0,
        volume: float = 1.0,
        cfg_weight: float = None,
        exaggeration: float = None,
        temperature: float = None,
        seed: int = None,
        voice_ref_path: str = None,
        voice_id: str = None,  # 서버 음성 ID
        repetition_penalty: float = None  # 반복 패널티 (긴 텍스트는 1.0~1.1 권장)
    ) -> Dict:
        """프리뷰 TTS 생성"""
        try:
            # ⭐ 한국어 텍스트 정규화 (콤마 숫자, 영어 약어 등)
            original_text = text
            if language == "ko" and text:
                normalizer = get_text_normalizer()
                text = normalizer(text)
                if text != original_text:
                    print(f"[CLIENT] 텍스트 정규화: {original_text[:50]}... → {text[:50]}...")

            # ========== 디버깅 로그 ==========
            print("=" * 60)
            print("[CLIENT DEBUG] generate_preview() called")
            print(f"[CLIENT DEBUG] text: '{text}'")
            print(f"[CLIENT DEBUG] text type: {type(text)}")
            print(f"[CLIENT DEBUG] text length: {len(text) if text else 0}")
            print(f"[CLIENT DEBUG] language: {language}")
            print(f"[CLIENT DEBUG] voice_id: {voice_id}")
            print(f"[CLIENT DEBUG] speed: {speed}")
            print("=" * 60)
            # ================================

            payload = {
                "text": text,
                "settings": {
                    "language": language,
                    "voice_name": voice_name,
                    "speed": speed,
                    "volume": volume
                }
            }

            if cfg_weight is not None:
                payload["settings"]["cfg_weight"] = cfg_weight
            if exaggeration is not None:
                payload["settings"]["exaggeration"] = exaggeration
            if temperature is not None:
                payload["settings"]["temperature"] = temperature
            if seed is not None:
                payload["settings"]["seed"] = seed
            if repetition_penalty is not None:
                payload["settings"]["repetition_penalty"] = repetition_penalty
            if voice_id is not None:
                payload["settings"]["voice_id"] = voice_id
            elif voice_ref_path is not None:
                # ⭐ 상대 경로 → 절대 경로 변환 (Chatter 서버에서 인식하도록)
                resolved_path = resolve_voice_path(voice_ref_path)
                payload["settings"]["voice_ref_path"] = resolved_path
                print(f"[CLIENT DEBUG] voice_ref_path resolved: {voice_ref_path} → {resolved_path}")

            # 전송할 payload 로그
            print(f"[CLIENT DEBUG] Sending payload: {payload}")

            r = requests.post(
                f"{self.base_url}/generate",
                json=payload,
                timeout=self.generate_timeout  # 10분
            )
            r.raise_for_status()
            result = r.json()

            # 응답 로그
            print(f"[CLIENT DEBUG] Response: success={result.get('success')}, duration={result.get('duration_seconds')}")
            if not result.get('success'):
                print(f"[CLIENT DEBUG] Error: {result.get('error')}")

            return result
        except requests.exceptions.Timeout:
            logger.error("TTS 생성 타임아웃")
            return {"success": False, "error": "TTS 생성 시간 초과"}
        except requests.exceptions.RequestException as e:
            logger.error(f"프리뷰 생성 실패: {e}")
            return {"success": False, "error": str(e)}

    def generate_longform(
        self,
        scenes: List[Dict],
        settings: Dict,
        senior_friendly: Dict = None,
        project_id: str = None,
        project_name: str = None,
        generate_srt: bool = True,
        normalize_audio: bool = True,
        crossfade_ms: int = 100,
        generate_vrew_data: bool = True
    ) -> Dict:
        """롱폼 TTS 생성"""
        try:
            # ⭐ settings에서 voice_ref_path 절대 경로 변환
            resolved_settings = dict(settings)
            if resolved_settings.get("voice_ref_path"):
                resolved_path = resolve_voice_path(resolved_settings["voice_ref_path"])
                resolved_settings["voice_ref_path"] = resolved_path
                logger.info(f"[Longform] voice_ref_path resolved: {resolved_path}")

            # ⭐ 씬별 텍스트 정규화 적용 (콤마 숫자, 영어 약어 등)
            language = resolved_settings.get("language", "ko")
            if language == "ko":
                normalizer = get_text_normalizer()
                normalized_scenes = []
                for scene in scenes:
                    scene_copy = dict(scene)
                    original_text = scene_copy.get("text", "")
                    if original_text:
                        normalized_text = normalizer(original_text)
                        if normalized_text != original_text:
                            print(f"[Longform] 씬 {scene_copy.get('scene_id', '?')} 정규화: {original_text[:40]}... → {normalized_text[:40]}...")
                        scene_copy["text"] = normalized_text
                    normalized_scenes.append(scene_copy)
            else:
                normalized_scenes = scenes

            payload = {
                "scenes": normalized_scenes,
                "settings": resolved_settings,
                "senior_friendly": senior_friendly or {"enabled": False, "silence_duration": 1.5},
                "project_id": project_id,
                "project_name": project_name,
                "generate_srt": generate_srt,
                "normalize_audio": normalize_audio,
                "crossfade_ms": crossfade_ms,
                "generate_vrew_data": generate_vrew_data
            }

            r = requests.post(
                f"{self.base_url}/generate/longform",
                json=payload,
                timeout=600  # 10분 타임아웃 (롱폼용)
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"롱폼 TTS 생성 실패: {e}")
            return {"success": False, "error": str(e)}

    def download_file(self, file_url: str, save_to: str) -> bool:
        """파일 다운로드"""
        try:
            # file_url이 상대 경로인 경우 전체 URL로 변환
            if file_url.startswith("/"):
                full_url = f"{self.base_url}{file_url}"
            else:
                full_url = file_url

            r = requests.get(full_url, stream=True, timeout=60)
            r.raise_for_status()

            with open(save_to, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"파일 다운로드 완료: {save_to}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"파일 다운로드 실패: {e}")
            return False

    def get_audio_url(self, relative_path: str) -> str:
        """오디오 URL 생성"""
        if relative_path.startswith("/"):
            return f"{self.base_url}{relative_path}"
        return f"{self.base_url}/{relative_path}"

    def upload_voice(self, file_path: str, name: str, language: str = "ko") -> Dict:
        """음성 레퍼런스 파일 업로드"""
        try:
            with open(file_path, "rb") as f:
                files = {"file": (name, f, "audio/wav")}
                data = {"name": name, "language": language}
                r = requests.post(
                    f"{self.base_url}/voices/upload",
                    files=files,
                    data=data,
                    timeout=60
                )
                r.raise_for_status()
                result = r.json()
                logger.info(f"음성 업로드 완료: {name}")
                return result
        except requests.exceptions.RequestException as e:
            logger.error(f"음성 업로드 실패: {e}")
            return {"success": False, "error": str(e)}
        except FileNotFoundError:
            logger.error(f"파일을 찾을 수 없음: {file_path}")
            return {"success": False, "error": f"File not found: {file_path}"}

    def delete_voice(self, language: str, voice_name: str) -> Dict:
        """음성 레퍼런스 삭제"""
        try:
            r = requests.delete(
                f"{self.base_url}/voices/{language}/{voice_name}",
                timeout=10
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"음성 삭제 실패: {e}")
            return {"success": False, "error": str(e)}

    def get_languages(self) -> List[Dict]:
        """지원 언어 목록 (8개 언어)"""
        try:
            r = requests.get(f"{self.base_url}/languages", timeout=5)
            r.raise_for_status()
            return r.json().get("languages", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"언어 목록 조회 실패: {e}")
            return [
                {"code": "ko", "name": "Korean", "flag": "KR"},
                {"code": "en", "name": "English", "flag": "US"},
                {"code": "ja", "name": "Japanese", "flag": "JP"},
                {"code": "zh", "name": "Chinese", "flag": "CN"},
                {"code": "es", "name": "Spanish", "flag": "ES"},
                {"code": "fr", "name": "French", "flag": "FR"},
                {"code": "de", "name": "German", "flag": "DE"},
                {"code": "pt", "name": "Portuguese", "flag": "BR"},
            ]

    def get_preset(self, language: str = "ko") -> Dict[str, Any]:
        """
        언어별 프리셋 조회

        Returns:
            {
                "language": "ko",
                "cfg_weight": 0.3,
                "exaggeration": 0.5,
                "speed": 0.9,
                "name": "한국어",
                "description": "한국어 최적화"
            }
        """
        try:
            r = requests.get(f"{self.base_url}/presets/{language}", timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.warning(f"프리셋 조회 실패: {e}")

        # 기본값 반환 (에러 대신) - 8개 언어 지원
        defaults = {
            "ko": {"cfg_weight": 0.3, "exaggeration": 0.5, "speed": 0.9, "name": "Korean"},
            "ja": {"cfg_weight": 0.3, "exaggeration": 0.5, "speed": 0.9, "name": "Japanese"},
            "en": {"cfg_weight": 0.5, "exaggeration": 0.5, "speed": 1.0, "name": "English"},
            "zh": {"cfg_weight": 0.3, "exaggeration": 0.5, "speed": 0.9, "name": "Chinese"},
            "es": {"cfg_weight": 0.5, "exaggeration": 0.5, "speed": 1.0, "name": "Spanish"},
            "fr": {"cfg_weight": 0.5, "exaggeration": 0.5, "speed": 1.0, "name": "French"},
            "de": {"cfg_weight": 0.5, "exaggeration": 0.5, "speed": 1.0, "name": "German"},
            "pt": {"cfg_weight": 0.5, "exaggeration": 0.5, "speed": 1.0, "name": "Portuguese"},
        }
        return defaults.get(language, {"cfg_weight": 0.5, "exaggeration": 0.5, "speed": 1.0})

    # ============================================================
    # 확장 API (성별 필터, 감정 태그, 배치 생성)
    # ============================================================

    def get_voices_by_gender(self, language: str, gender: str) -> List[Dict]:
        """성별로 필터링된 음성 목록"""
        try:
            r = requests.get(f"{self.base_url}/voices/{language}/{gender}", timeout=10)
            r.raise_for_status()
            return r.json().get("voices", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"성별 필터 음성 조회 실패: {e}")
            return []

    def get_emotion_tags(self) -> Dict:
        """감정 태그 목록 조회"""
        try:
            r = requests.get(f"{self.base_url}/emotion-tags", timeout=5)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"감정 태그 조회 실패: {e}")
            # 기본 태그 반환
            return {
                "tags": {
                    "laugh": {"tag": "[laugh]", "description": "웃음 소리", "icon": "😂"},
                    "sigh": {"tag": "[sigh]", "description": "한숨", "icon": "😔"},
                    "cough": {"tag": "[cough]", "description": "기침", "icon": "😷"},
                    "hmm": {"tag": "[hmm]", "description": "생각", "icon": "🤔"},
                },
                "supported": False
            }

    def get_custom_voices(self) -> List[Dict]:
        """사용자 업로드 음성 목록"""
        try:
            r = requests.get(f"{self.base_url}/voices/custom/list", timeout=10)
            r.raise_for_status()
            return r.json().get("voices", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"커스텀 음성 조회 실패: {e}")
            return []

    def upload_voice_file(
        self,
        file_content: bytes,
        filename: str,
        name: str,
        language: str = "ko",
        gender: str = "neutral",
        description: str = ""
    ) -> Dict:
        """음성 파일 업로드 (바이트 데이터)"""
        try:
            files = {"file": (filename, file_content, "audio/wav")}
            data = {
                "name": name,
                "language": language,
                "gender": gender,
                "description": description
            }
            r = requests.post(
                f"{self.base_url}/voices/upload",
                files=files,
                data=data,
                timeout=60
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"음성 업로드 실패: {e}")
            return {"success": False, "error": str(e)}

    def delete_custom_voice(self, voice_name: str) -> Dict:
        """커스텀 음성 삭제"""
        try:
            r = requests.delete(
                f"{self.base_url}/voices/custom/{voice_name}",
                timeout=10
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"음성 삭제 실패: {e}")
            return {"success": False, "error": str(e)}

    def generate_batch(
        self,
        items: List[Dict],
        settings: Dict = None
    ) -> Dict:
        """배치 TTS 생성"""
        try:
            payload = {
                "items": items,
                "settings": settings or {}
            }

            r = requests.post(
                f"{self.base_url}/generate/batch",
                json=payload,
                timeout=self.generate_timeout * 2  # 배치는 더 오래 걸림
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            logger.error("배치 TTS 생성 타임아웃")
            return {"success": False, "error": "배치 생성 시간 초과"}
        except requests.exceptions.RequestException as e:
            logger.error(f"배치 TTS 생성 실패: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # Voice Analysis API (음성 분석 & 자동 파라미터 추천)
    # ============================================================

    def analyze_voice(self, audio_path: str) -> Dict:
        """
        음성 파일 분석 후 최적 TTS 파라미터 추천

        분석 항목:
        - 피치 (F0): 높낮이, 변동성
        - 에너지: 볼륨 변화
        - 발화 속도

        Returns:
            {
                "success": True,
                "analysis": {
                    "pitch_mean": 150.0,
                    "pitch_std": 25.0,
                    "energy_mean": 0.1,
                    "speaking_rate": 4.0,
                    "duration": 5.0
                },
                "recommended": {
                    "exaggeration": 0.5,
                    "cfg_weight": 0.3,
                    "temperature": 0.8,
                    "speed": 1.0
                },
                "confidence": 0.85,
                "characteristics": {
                    "pitch": "중음",
                    "expression": "자연스러운",
                    "speed": "보통"
                }
            }
        """
        try:
            # ⭐ 절대 경로로 변환
            resolved_path = resolve_voice_path(audio_path)
            logger.info(f"음성 분석 요청: {resolved_path}")

            r = requests.post(
                f"{self.base_url}/analyze_voice",
                json={"audio_path": resolved_path},
                timeout=30
            )
            r.raise_for_status()
            result = r.json()

            if result.get("success"):
                logger.info(f"음성 분석 완료: 신뢰도 {result.get('confidence', 0)*100:.0f}%")
            else:
                logger.warning(f"음성 분석 실패: {result.get('error')}")

            return result

        except requests.exceptions.Timeout:
            logger.error("음성 분석 타임아웃")
            return {"success": False, "error": "분석 시간 초과"}
        except requests.exceptions.RequestException as e:
            logger.error(f"음성 분석 실패: {e}")
            return {"success": False, "error": str(e)}

    def upload_and_analyze_voice(
        self,
        file_content: bytes,
        filename: str,
        name: str,
        language: str = "ko"
    ) -> Dict:
        """
        음성 파일 업로드 + 자동 분석 + 파라미터 추천

        Returns:
            {
                "success": True,
                "voice_id": "custom_myvoice",
                "name": "myvoice",
                "path": "...",
                "analysis": {...},
                "recommended": {...},
                "confidence": 0.85,
                "characteristics": {...}
            }
        """
        try:
            logger.info(f"음성 업로드 및 분석: {name}")

            files = {"file": (filename, file_content, "audio/wav")}
            data = {"name": name, "language": language}

            r = requests.post(
                f"{self.base_url}/voices/upload_and_analyze",
                files=files,
                data=data,
                timeout=120  # 분석 포함이라 더 오래 걸림
            )
            r.raise_for_status()
            result = r.json()

            if result.get("success"):
                logger.info(f"음성 업로드 및 분석 완료: {name}")
                if result.get("recommended"):
                    logger.info(f"추천 파라미터: {result['recommended']}")
            else:
                logger.warning(f"음성 업로드/분석 실패: {result.get('error')}")

            return result

        except requests.exceptions.Timeout:
            logger.error("음성 업로드/분석 타임아웃")
            return {"success": False, "error": "업로드/분석 시간 초과"}
        except requests.exceptions.RequestException as e:
            logger.error(f"음성 업로드/분석 실패: {e}")
            return {"success": False, "error": str(e)}

    def get_recommended_params(self, audio_path: str) -> Optional[Dict[str, float]]:
        """
        음성 분석 후 추천 파라미터만 반환 (간편 함수)

        Returns:
            {
                "exaggeration": 0.5,
                "cfg_weight": 0.3,
                "temperature": 0.8,
                "speed": 1.0
            }
            또는 None (실패 시)
        """
        result = self.analyze_voice(audio_path)

        if result.get("success") and result.get("recommended"):
            return result["recommended"]

        return None



# 싱글톤 인스턴스
chatterbox_client = ChatterboxTTSClient()

# 호환성 alias (ChatterboxClient로 import 가능)
ChatterboxClient = ChatterboxTTSClient
