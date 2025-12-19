"""
합성 후 편집기

합성 완료 후 캐릭터 위치/크기를 드래그로 조정하는 편집기
"""
import streamlit as st
import streamlit.components.v1 as components
import json
import base64
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import time


@dataclass
class CharacterLayer:
    """캐릭터 레이어 정보"""
    id: str
    name: str
    image_url: str
    x: float  # 중심 X (0.0 ~ 1.0)
    y: float  # 중심 Y (0.0 ~ 1.0)
    width: float  # 너비 비율 (0.0 ~ 1.0)
    height: float  # 높이 비율 (0.0 ~ 1.0)
    z_index: int = 1
    flip_x: bool = False
    opacity: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


def _ensure_transparent_image(image_path: str) -> str:
    """
    이미지의 투명 배경 버전 경로 반환

    rembg가 설치되어 있으면 배경 제거, 아니면 원본 반환
    """
    if not image_path:
        return image_path

    try:
        from utils.background_remover import ensure_transparent_background
        return ensure_transparent_background(image_path)
    except ImportError:
        print("[PostEditor] background_remover 모듈 없음, 원본 이미지 사용")
        return image_path
    except Exception as e:
        print(f"[PostEditor] 배경 제거 실패: {e}")
        return image_path


def _image_to_data_uri(image_path: str, ensure_transparent: bool = False) -> str:
    """
    이미지 경로를 Data URI로 변환

    Args:
        image_path: 이미지 파일 경로
        ensure_transparent: True이면 배경 제거 후 변환
    """
    try:
        # 투명 배경 처리가 필요하면 먼저 처리
        if ensure_transparent:
            image_path = _ensure_transparent_image(image_path)

        path = Path(image_path)
        if path.exists():
            with open(path, "rb") as f:
                data = f.read()
            ext = path.suffix.lower().replace(".", "")
            if ext == "jpg":
                ext = "jpeg"
            # PNG는 투명 배경 지원
            return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
    except Exception as e:
        print(f"[PostEditor] 이미지 로드 실패: {e}")
    return image_path  # fallback


def post_composite_editor(
    background_url: str,
    character_layers: List[Dict],
    canvas_width: int = 900,
    canvas_height: int = 506,  # 16:9 비율
    editor_id: str = "post_editor"
) -> None:
    """
    합성 후 편집기 렌더링

    Args:
        background_url: 배경 이미지 URL 또는 로컬 경로
        character_layers: 캐릭터 레이어 정보 리스트
        canvas_width: 캔버스 너비
        canvas_height: 캔버스 높이
        editor_id: 편집기 고유 ID
    """

    # 이미지 경로를 Data URI로 변환 (로컬 파일 지원)
    bg_uri = _image_to_data_uri(background_url, ensure_transparent=False)  # 배경은 투명 처리 안 함

    # 캐릭터 이미지도 Data URI로 변환 (투명 배경 처리!)
    chars_with_uri = []
    for char in character_layers:
        char_copy = char.copy()
        original_path = char_copy.get("image_url") or char_copy.get("image_path") or ""

        if original_path:
            # 캐릭터 이미지는 투명 배경 처리 후 Data URI 변환
            char_copy["image_url"] = _image_to_data_uri(original_path, ensure_transparent=True)

        chars_with_uri.append(char_copy)

    # 캐릭터 데이터 JSON
    characters_json = json.dumps(chars_with_uri, ensure_ascii=False)

    # 고유 ID
    unique_id = f"{editor_id}_{int(time.time() * 1000) % 100000}"
    storage_key = f"post_composite_{editor_id}"

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: transparent;
            }}

            .editor-wrapper {{
                display: flex;
                flex-direction: column;
                gap: 12px;
            }}

            .canvas-container {{
                position: relative;
                width: {canvas_width}px;
                height: {canvas_height}px;
                border: 3px solid #2196F3;
                border-radius: 12px;
                overflow: hidden;
                background: #1a1a1a;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            }}

            .background-layer {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                object-fit: cover;
                pointer-events: none;
            }}

            .character-layer {{
                position: absolute;
                cursor: move;
                user-select: none;
                transition: box-shadow 0.15s ease;
                /* 투명 배경 지원 */
                background: transparent !important;
            }}

            .character-layer:hover {{
                box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.8);
            }}

            .character-layer.selected {{
                box-shadow: 0 0 0 4px #2196F3, 0 0 20px rgba(33, 150, 243, 0.5);
            }}

            .character-layer img {{
                width: 100%;
                height: 100%;
                object-fit: contain;
                pointer-events: none;
                /* 이미지 배경도 투명 */
                background: transparent !important;
            }}

            .resize-handle {{
                position: absolute;
                width: 16px;
                height: 16px;
                background: #2196F3;
                border: 3px solid white;
                border-radius: 50%;
                opacity: 0;
                transition: opacity 0.2s;
                z-index: 100;
            }}

            .character-layer.selected .resize-handle {{
                opacity: 1;
            }}

            .resize-handle:hover {{
                background: #1976D2;
                transform: scale(1.2);
            }}

            .resize-handle.tl {{ top: -8px; left: -8px; cursor: nwse-resize; }}
            .resize-handle.tr {{ top: -8px; right: -8px; cursor: nesw-resize; }}
            .resize-handle.bl {{ bottom: -8px; left: -8px; cursor: nesw-resize; }}
            .resize-handle.br {{ bottom: -8px; right: -8px; cursor: nwse-resize; }}

            .char-label {{
                position: absolute;
                bottom: -28px;
                left: 50%;
                transform: translateX(-50%);
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
                white-space: nowrap;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            }}

            .toolbar {{
                display: flex;
                gap: 10px;
                justify-content: center;
                flex-wrap: wrap;
            }}

            .toolbar button {{
                padding: 10px 20px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 6px;
            }}

            .btn-primary {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}

            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            }}

            .btn-secondary {{
                background: #f0f0f0;
                color: #333;
            }}

            .btn-secondary:hover {{
                background: #e0e0e0;
            }}

            .btn-danger {{
                background: #ff5252;
                color: white;
            }}

            .btn-danger:hover {{
                background: #ff1744;
            }}

            .btn-success {{
                background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                color: white;
            }}

            .btn-success:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(56, 239, 125, 0.4);
            }}

            .info-bar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: white;
                padding: 10px 16px;
                border-radius: 8px;
                font-size: 13px;
            }}

            .info-bar .hint {{
                color: #aaa;
            }}

            .info-bar .selected-info {{
                color: #4CAF50;
                font-weight: 600;
            }}

            .flip-indicator {{
                position: absolute;
                top: 4px;
                right: 4px;
                background: rgba(0,0,0,0.7);
                color: white;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 10px;
                opacity: 0;
            }}

            .character-layer.selected .flip-indicator {{
                opacity: 1;
            }}
        </style>
    </head>
    <body>
        <div class="editor-wrapper">
            <!-- 정보 바 -->
            <div class="info-bar">
                <span class="hint">캐릭터를 드래그하여 이동 | 모서리를 드래그하여 크기 조정</span>
                <span class="selected-info" id="selectedInfo_{unique_id}">선택된 캐릭터 없음</span>
            </div>

            <!-- 캔버스 -->
            <div class="canvas-container" id="canvas_{unique_id}">
                <img class="background-layer" src="{bg_uri}" alt="배경" />
            </div>

            <!-- 툴바 -->
            <div class="toolbar">
                <button class="btn-secondary" onclick="resetAll_{unique_id}()">초기화</button>
                <button class="btn-secondary" onclick="flipSelected_{unique_id}()">좌우반전</button>
                <button class="btn-secondary" onclick="bringForward_{unique_id}()">앞으로</button>
                <button class="btn-secondary" onclick="sendBackward_{unique_id}()">뒤로</button>
                <button class="btn-success" onclick="saveAndApply_{unique_id}()">위치 저장 (재합성용)</button>
            </div>
        </div>

        <script>
            (function() {{
                // 초기 데이터
                const initialCharacters = {characters_json};
                let characters = JSON.parse(JSON.stringify(initialCharacters));
                let selectedElement = null;
                let isDragging = false;
                let isResizing = false;
                let activeHandle = null;
                let dragStartX, dragStartY, elemStartX, elemStartY, elemStartW, elemStartH;

                const canvas = document.getElementById('canvas_{unique_id}');
                const selectedInfo = document.getElementById('selectedInfo_{unique_id}');
                const CANVAS_W = {canvas_width};
                const CANVAS_H = {canvas_height};
                const STORAGE_KEY = '{storage_key}';

                // 저장된 위치 로드
                function loadSavedPositions() {{
                    try {{
                        const saved = localStorage.getItem(STORAGE_KEY);
                        if (saved) {{
                            const savedChars = JSON.parse(saved);
                            characters.forEach((char, i) => {{
                                const savedChar = savedChars.find(sc => sc.name === char.name || sc.id === char.id);
                                if (savedChar) {{
                                    char.x = savedChar.x;
                                    char.y = savedChar.y;
                                    char.width = savedChar.width;
                                    char.height = savedChar.height;
                                    char.z_index = savedChar.z_index;
                                    char.flip_x = savedChar.flip_x;
                                }}
                            }});
                        }}
                    }} catch(e) {{
                        console.warn('위치 로드 실패:', e);
                    }}
                }}

                // 캐릭터 요소 생성
                function createCharacterLayers() {{
                    // 기존 캐릭터 제거
                    canvas.querySelectorAll('.character-layer').forEach(el => el.remove());

                    characters.forEach((char, index) => {{
                        const layer = document.createElement('div');
                        layer.className = 'character-layer';
                        layer.dataset.index = index;
                        layer.dataset.name = char.name || char.id;

                        // 크기 계산
                        const w = char.width * CANVAS_W;
                        const h = char.height * CANVAS_H;
                        const left = char.x * CANVAS_W - w / 2;
                        const top = char.y * CANVAS_H - h / 2;

                        layer.style.width = w + 'px';
                        layer.style.height = h + 'px';
                        layer.style.left = Math.max(0, Math.min(left, CANVAS_W - w)) + 'px';
                        layer.style.top = Math.max(0, Math.min(top, CANVAS_H - h)) + 'px';
                        layer.style.zIndex = char.z_index || (index + 1);

                        if (char.flip_x) {{
                            layer.style.transform = 'scaleX(-1)';
                        }}

                        // 이미지
                        const img = document.createElement('img');
                        img.src = char.image_url;
                        img.alt = char.name || char.id;
                        img.draggable = false;
                        layer.appendChild(img);

                        // 라벨
                        const label = document.createElement('div');
                        label.className = 'char-label';
                        label.textContent = char.name || char.id;
                        if (char.flip_x) label.style.transform = 'scaleX(-1) translateX(50%)';
                        layer.appendChild(label);

                        // 반전 표시
                        const flipInd = document.createElement('div');
                        flipInd.className = 'flip-indicator';
                        flipInd.textContent = char.flip_x ? '반전' : '';
                        layer.appendChild(flipInd);

                        // 리사이즈 핸들
                        ['tl', 'tr', 'bl', 'br'].forEach(pos => {{
                            const handle = document.createElement('div');
                            handle.className = 'resize-handle ' + pos;
                            handle.dataset.handle = pos;
                            layer.appendChild(handle);
                        }});

                        // 이벤트
                        layer.addEventListener('mousedown', onMouseDown);

                        canvas.appendChild(layer);
                    }});
                }}

                // 선택
                function selectElement(elem) {{
                    canvas.querySelectorAll('.character-layer').forEach(el => {{
                        el.classList.remove('selected');
                    }});

                    selectedElement = elem;

                    if (elem) {{
                        elem.classList.add('selected');
                        const char = characters[parseInt(elem.dataset.index)];
                        const x = ((elem.offsetLeft + elem.offsetWidth/2) / CANVAS_W * 100).toFixed(0);
                        const y = ((elem.offsetTop + elem.offsetHeight/2) / CANVAS_H * 100).toFixed(0);
                        const w = (elem.offsetWidth / CANVAS_W * 100).toFixed(0);
                        selectedInfo.textContent = (char.name || char.id) + ' | 위치(' + x + '%, ' + y + '%) | 크기 ' + w + '%';
                    }} else {{
                        selectedInfo.textContent = '선택된 캐릭터 없음';
                    }}
                }}

                // 마우스 다운
                function onMouseDown(e) {{
                    e.preventDefault();
                    e.stopPropagation();

                    const target = e.target;

                    // 리사이즈 핸들
                    if (target.classList.contains('resize-handle')) {{
                        isResizing = true;
                        activeHandle = target.dataset.handle;
                        const layer = target.parentElement;
                        selectElement(layer);

                        dragStartX = e.clientX;
                        dragStartY = e.clientY;
                        elemStartW = layer.offsetWidth;
                        elemStartH = layer.offsetHeight;
                        elemStartX = layer.offsetLeft;
                        elemStartY = layer.offsetTop;
                        return;
                    }}

                    // 레이어 드래그
                    const layer = target.closest('.character-layer');
                    if (layer) {{
                        isDragging = true;
                        selectElement(layer);

                        dragStartX = e.clientX;
                        dragStartY = e.clientY;
                        elemStartX = layer.offsetLeft;
                        elemStartY = layer.offsetTop;
                    }}
                }}

                // 마우스 이동
                document.addEventListener('mousemove', (e) => {{
                    if (!selectedElement) return;

                    const dx = e.clientX - dragStartX;
                    const dy = e.clientY - dragStartY;

                    if (isDragging) {{
                        let newLeft = elemStartX + dx;
                        let newTop = elemStartY + dy;

                        // 경계
                        newLeft = Math.max(0, Math.min(newLeft, CANVAS_W - selectedElement.offsetWidth));
                        newTop = Math.max(0, Math.min(newTop, CANVAS_H - selectedElement.offsetHeight));

                        selectedElement.style.left = newLeft + 'px';
                        selectedElement.style.top = newTop + 'px';

                        updateInfo();
                    }}

                    if (isResizing) {{
                        const aspect = elemStartW / elemStartH;
                        let newW = elemStartW;
                        let newH = elemStartH;
                        let newLeft = elemStartX;
                        let newTop = elemStartY;

                        switch(activeHandle) {{
                            case 'br':
                                newW = Math.max(60, elemStartW + dx);
                                newH = newW / aspect;
                                break;
                            case 'bl':
                                newW = Math.max(60, elemStartW - dx);
                                newH = newW / aspect;
                                newLeft = elemStartX + elemStartW - newW;
                                break;
                            case 'tr':
                                newW = Math.max(60, elemStartW + dx);
                                newH = newW / aspect;
                                newTop = elemStartY + elemStartH - newH;
                                break;
                            case 'tl':
                                newW = Math.max(60, elemStartW - dx);
                                newH = newW / aspect;
                                newLeft = elemStartX + elemStartW - newW;
                                newTop = elemStartY + elemStartH - newH;
                                break;
                        }}

                        // 경계 체크
                        if (newLeft >= 0 && newTop >= 0 &&
                            newLeft + newW <= CANVAS_W && newTop + newH <= CANVAS_H) {{
                            selectedElement.style.width = newW + 'px';
                            selectedElement.style.height = newH + 'px';
                            selectedElement.style.left = newLeft + 'px';
                            selectedElement.style.top = newTop + 'px';
                        }}

                        updateInfo();
                    }}
                }});

                // 마우스 업
                document.addEventListener('mouseup', () => {{
                    if (isDragging || isResizing) {{
                        // 위치 업데이트
                        if (selectedElement) {{
                            const idx = parseInt(selectedElement.dataset.index);
                            const char = characters[idx];

                            char.x = (selectedElement.offsetLeft + selectedElement.offsetWidth/2) / CANVAS_W;
                            char.y = (selectedElement.offsetTop + selectedElement.offsetHeight/2) / CANVAS_H;
                            char.width = selectedElement.offsetWidth / CANVAS_W;
                            char.height = selectedElement.offsetHeight / CANVAS_H;
                            char.z_index = parseInt(selectedElement.style.zIndex) || 1;
                        }}
                    }}

                    isDragging = false;
                    isResizing = false;
                    activeHandle = null;
                }});

                // 캔버스 클릭 - 선택 해제
                canvas.addEventListener('click', (e) => {{
                    if (e.target === canvas || e.target.classList.contains('background-layer')) {{
                        selectElement(null);
                    }}
                }});

                // 정보 업데이트
                function updateInfo() {{
                    if (selectedElement) {{
                        const char = characters[parseInt(selectedElement.dataset.index)];
                        const x = ((selectedElement.offsetLeft + selectedElement.offsetWidth/2) / CANVAS_W * 100).toFixed(0);
                        const y = ((selectedElement.offsetTop + selectedElement.offsetHeight/2) / CANVAS_H * 100).toFixed(0);
                        const w = (selectedElement.offsetWidth / CANVAS_W * 100).toFixed(0);
                        selectedInfo.textContent = (char.name || char.id) + ' | 위치(' + x + '%, ' + y + '%) | 크기 ' + w + '%';
                    }}
                }}

                // 전역 함수들 (고유 이름)
                window['resetAll_{unique_id}'] = function() {{
                    characters = JSON.parse(JSON.stringify(initialCharacters));
                    localStorage.removeItem(STORAGE_KEY);
                    createCharacterLayers();
                    selectElement(null);
                }};

                window['flipSelected_{unique_id}'] = function() {{
                    if (!selectedElement) {{
                        alert('캐릭터를 먼저 선택하세요');
                        return;
                    }}

                    const idx = parseInt(selectedElement.dataset.index);
                    characters[idx].flip_x = !characters[idx].flip_x;

                    if (characters[idx].flip_x) {{
                        selectedElement.style.transform = 'scaleX(-1)';
                    }} else {{
                        selectedElement.style.transform = '';
                    }}

                    // 반전 표시 업데이트
                    const flipInd = selectedElement.querySelector('.flip-indicator');
                    if (flipInd) flipInd.textContent = characters[idx].flip_x ? '반전' : '';
                }};

                window['bringForward_{unique_id}'] = function() {{
                    if (!selectedElement) return;

                    let maxZ = 1;
                    canvas.querySelectorAll('.character-layer').forEach(el => {{
                        maxZ = Math.max(maxZ, parseInt(el.style.zIndex) || 1);
                    }});

                    selectedElement.style.zIndex = maxZ + 1;
                    const idx = parseInt(selectedElement.dataset.index);
                    characters[idx].z_index = maxZ + 1;
                }};

                window['sendBackward_{unique_id}'] = function() {{
                    if (!selectedElement) return;

                    let minZ = 999;
                    canvas.querySelectorAll('.character-layer').forEach(el => {{
                        minZ = Math.min(minZ, parseInt(el.style.zIndex) || 1);
                    }});

                    const newZ = Math.max(1, minZ - 1);
                    selectedElement.style.zIndex = newZ;
                    const idx = parseInt(selectedElement.dataset.index);
                    characters[idx].z_index = newZ;
                }};

                window['saveAndApply_{unique_id}'] = function() {{
                    const result = characters.map(char => ({{
                        id: char.id,
                        name: char.name,
                        image_url: char.image_url,
                        x: char.x,
                        y: char.y,
                        width: char.width,
                        height: char.height,
                        z_index: char.z_index,
                        flip_x: char.flip_x
                    }}));

                    localStorage.setItem(STORAGE_KEY, JSON.stringify(result));

                    // 콘솔에도 출력 (디버깅용)
                    console.log('저장된 위치:', result);

                    // 시각적 피드백
                    const btn = event.target;
                    const originalText = btn.textContent;
                    btn.textContent = '저장됨!';
                    btn.style.background = '#4CAF50';
                    setTimeout(() => {{
                        btn.textContent = originalText;
                        btn.style.background = '';
                    }}, 1500);
                }};

                // 위치 데이터 가져오기 (외부에서 호출용)
                window['getPositions_{unique_id}'] = function() {{
                    return characters.map(char => ({{
                        id: char.id,
                        name: char.name,
                        image_url: char.image_url,
                        x: char.x,
                        y: char.y,
                        width: char.width,
                        height: char.height,
                        z_index: char.z_index,
                        flip_x: char.flip_x
                    }}));
                }};

                // 초기화 실행
                loadSavedPositions();
                createCharacterLayers();
            }})();
        </script>
    </body>
    </html>
    """

    # 렌더링
    components.html(html_code, height=canvas_height + 130)


def get_editor_storage_key(editor_id: str) -> str:
    """편집기의 localStorage 키 반환"""
    return f"post_composite_{editor_id}"
