"""
인터랙티브 캔버스 컴포넌트

캐릭터 드래그 앤 드롭 + 크기 조정 기능
Streamlit Components API 사용
"""
import streamlit as st
import streamlit.components.v1 as components
import json
import base64
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    from PIL import Image
    from io import BytesIO
except ImportError:
    Image = None


@dataclass
class CanvasObject:
    """캔버스 오브젝트 (캐릭터)"""
    id: str
    name: str
    image_url: str
    x: float  # 0.0 ~ 1.0 (비율)
    y: float  # 0.0 ~ 1.0 (비율)
    width: float  # 0.0 ~ 1.0 (비율)
    height: float  # 0.0 ~ 1.0 (비율)
    rotation: float = 0  # 회전 각도
    flip_x: bool = False  # 좌우 반전
    z_index: int = 1  # 레이어 순서
    opacity: float = 1.0  # 투명도


def _image_to_data_uri(image_path: str) -> str:
    """이미지 경로를 Data URI로 변환"""
    try:
        path = Path(image_path)
        if path.exists():
            with open(path, "rb") as f:
                data = f.read()
            ext = path.suffix.lower().replace(".", "")
            if ext == "jpg":
                ext = "jpeg"
            return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
    except Exception as e:
        print(f"[Canvas] 이미지 로드 실패: {e}")
    return image_path  # fallback


def interactive_composite_canvas(
    background_url: str,
    characters: List[Dict],
    canvas_width: int = 800,
    canvas_height: int = 450,
    key: str = "composite_canvas"
) -> Optional[Dict]:
    """
    인터랙티브 합성 캔버스

    Args:
        background_url: 배경 이미지 URL 또는 경로
        characters: 캐릭터 정보 리스트 [{id, name, image_url, x, y, width, height}]
        canvas_width: 캔버스 너비
        canvas_height: 캔버스 높이
        key: 컴포넌트 키

    Returns:
        조정된 캐릭터 위치/크기 정보
    """

    # 이미지 경로를 Data URI로 변환 (로컬 파일 지원)
    bg_uri = _image_to_data_uri(background_url)

    # 캐릭터 이미지도 Data URI로 변환
    chars_with_uri = []
    for char in characters:
        char_copy = char.copy()
        if char_copy.get("image_url"):
            char_copy["image_url"] = _image_to_data_uri(char_copy["image_url"])
        chars_with_uri.append(char_copy)

    # 캐릭터 데이터를 JSON으로 변환
    characters_json = json.dumps(chars_with_uri, ensure_ascii=False)

    # HTML/JavaScript 컴포넌트
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

            .canvas-container {{
                position: relative;
                width: {canvas_width}px;
                height: {canvas_height}px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                overflow: hidden;
                background: #f5f5f5;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}

            .background-layer {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}

            .character {{
                position: absolute;
                cursor: move;
                user-select: none;
                transition: box-shadow 0.15s;
            }}

            .character:hover {{
                box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.7);
            }}

            .character.selected {{
                box-shadow: 0 0 0 3px #2196F3;
            }}

            .character img {{
                width: 100%;
                height: 100%;
                object-fit: contain;
                pointer-events: none;
            }}

            .resize-handle {{
                position: absolute;
                width: 14px;
                height: 14px;
                background: #2196F3;
                border: 2px solid white;
                border-radius: 50%;
                box-shadow: 0 1px 3px rgba(0,0,0,0.3);
                z-index: 10;
            }}

            .resize-handle.top-left {{ top: -7px; left: -7px; cursor: nwse-resize; }}
            .resize-handle.top-right {{ top: -7px; right: -7px; cursor: nesw-resize; }}
            .resize-handle.bottom-left {{ bottom: -7px; left: -7px; cursor: nesw-resize; }}
            .resize-handle.bottom-right {{ bottom: -7px; right: -7px; cursor: nwse-resize; }}

            .character-label {{
                position: absolute;
                bottom: -24px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0,0,0,0.75);
                color: white;
                padding: 3px 10px;
                border-radius: 4px;
                font-size: 11px;
                white-space: nowrap;
                font-weight: 500;
            }}

            .toolbar {{
                position: absolute;
                top: 10px;
                right: 10px;
                display: flex;
                gap: 6px;
                z-index: 1000;
            }}

            .toolbar button {{
                padding: 6px 12px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 500;
                transition: all 0.15s;
                display: flex;
                align-items: center;
                gap: 4px;
            }}

            .btn-primary {{
                background: #2196F3;
                color: white;
            }}

            .btn-primary:hover {{
                background: #1976D2;
                transform: translateY(-1px);
            }}

            .btn-secondary {{
                background: rgba(255,255,255,0.9);
                color: #333;
                border: 1px solid #ddd;
            }}

            .btn-secondary:hover {{
                background: white;
                border-color: #bbb;
            }}

            .btn-danger {{
                background: #f44336;
                color: white;
            }}

            .btn-danger:hover {{
                background: #d32f2f;
            }}

            .info-panel {{
                position: absolute;
                bottom: 10px;
                left: 10px;
                background: rgba(0,0,0,0.75);
                color: white;
                padding: 8px 14px;
                border-radius: 6px;
                font-size: 11px;
                z-index: 1000;
                max-width: 300px;
            }}

            .char-controls {{
                position: absolute;
                top: -35px;
                left: 50%;
                transform: translateX(-50%);
                display: none;
                gap: 4px;
                background: rgba(0,0,0,0.8);
                padding: 4px 8px;
                border-radius: 6px;
            }}

            .character.selected .char-controls {{
                display: flex;
            }}

            .char-controls button {{
                padding: 4px 8px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 10px;
                background: #555;
                color: white;
            }}

            .char-controls button:hover {{
                background: #777;
            }}
        </style>
    </head>
    <body>
        <div class="canvas-container" id="canvas">
            <img class="background-layer" src="{bg_uri}" alt="Background" />

            <div class="toolbar">
                <button class="btn-secondary" onclick="resetPositions()" title="초기화">
                    <span>↩</span> 초기화
                </button>
                <button class="btn-secondary" onclick="flipSelected()" title="좌우반전">
                    <span>↔</span> 반전
                </button>
                <button class="btn-secondary" onclick="bringToFront()" title="앞으로">
                    <span>⬆</span> 앞
                </button>
                <button class="btn-secondary" onclick="sendToBack()" title="뒤로">
                    <span>⬇</span> 뒤
                </button>
                <button class="btn-primary" onclick="savePositions()" title="적용">
                    <span>✓</span> 적용
                </button>
            </div>

            <div class="info-panel" id="infoPanel">
                드래그로 위치 조정 | 모서리로 크기 조정
            </div>
        </div>

        <script>
            const characters = {characters_json};
            let selectedCharacter = null;
            let isDragging = false;
            let isResizing = false;
            let resizeHandle = null;
            let startX, startY, startWidth, startHeight, startLeft, startTop;

            const canvas = document.getElementById('canvas');
            const canvasWidth = {canvas_width};
            const canvasHeight = {canvas_height};

            function createCharacterElements() {{
                characters.forEach((char, index) => {{
                    const div = document.createElement('div');
                    div.className = 'character';
                    div.id = 'char_' + char.id;
                    div.dataset.index = index;

                    const width = char.width * canvasWidth;
                    const height = char.height * canvasHeight;
                    const left = char.x * canvasWidth - width / 2;
                    const top = char.y * canvasHeight - height / 2;

                    div.style.width = width + 'px';
                    div.style.height = height + 'px';
                    div.style.left = Math.max(0, Math.min(left, canvasWidth - width)) + 'px';
                    div.style.top = Math.max(0, Math.min(top, canvasHeight - height)) + 'px';
                    div.style.zIndex = char.z_index || (index + 1);

                    if (char.flip_x) {{
                        div.style.transform = 'scaleX(-1)';
                        div.dataset.flipped = 'true';
                    }}

                    const img = document.createElement('img');
                    img.src = char.image_url;
                    img.alt = char.name;
                    img.draggable = false;
                    div.appendChild(img);

                    const label = document.createElement('div');
                    label.className = 'character-label';
                    label.textContent = char.name;
                    div.appendChild(label);

                    ['top-left', 'top-right', 'bottom-left', 'bottom-right'].forEach(pos => {{
                        const handle = document.createElement('div');
                        handle.className = 'resize-handle ' + pos;
                        handle.dataset.handle = pos;
                        handle.style.display = 'none';
                        div.appendChild(handle);
                    }});

                    div.addEventListener('mousedown', onCharacterMouseDown);
                    div.addEventListener('click', (e) => {{
                        e.stopPropagation();
                        selectCharacter(div);
                    }});

                    canvas.appendChild(div);
                }});
            }}

            function selectCharacter(element) {{
                document.querySelectorAll('.character').forEach(el => {{
                    el.classList.remove('selected');
                    el.querySelectorAll('.resize-handle').forEach(h => h.style.display = 'none');
                }});

                element.classList.add('selected');
                element.querySelectorAll('.resize-handle').forEach(h => h.style.display = 'block');
                selectedCharacter = element;

                updateInfoPanel();
            }}

            function updateInfoPanel() {{
                const panel = document.getElementById('infoPanel');
                if (selectedCharacter) {{
                    const index = parseInt(selectedCharacter.dataset.index);
                    const char = characters[index];

                    const x = ((selectedCharacter.offsetLeft + selectedCharacter.offsetWidth/2) / canvasWidth * 100).toFixed(0);
                    const y = ((selectedCharacter.offsetTop + selectedCharacter.offsetHeight/2) / canvasHeight * 100).toFixed(0);
                    const w = (selectedCharacter.offsetWidth / canvasWidth * 100).toFixed(0);

                    panel.textContent = char.name + ' | 위치: (' + x + '%, ' + y + '%) | 크기: ' + w + '%';
                }} else {{
                    panel.textContent = '드래그로 위치 조정 | 모서리로 크기 조정';
                }}
            }}

            function onCharacterMouseDown(e) {{
                const target = e.target;

                if (target.classList.contains('resize-handle')) {{
                    isResizing = true;
                    resizeHandle = target.dataset.handle;
                    const charElement = target.parentElement;
                    startX = e.clientX;
                    startY = e.clientY;
                    startWidth = charElement.offsetWidth;
                    startHeight = charElement.offsetHeight;
                    startLeft = charElement.offsetLeft;
                    startTop = charElement.offsetTop;
                    selectedCharacter = charElement;
                    e.stopPropagation();
                    e.preventDefault();
                    return;
                }}

                const charElement = target.closest('.character');
                if (charElement) {{
                    isDragging = true;
                    selectedCharacter = charElement;
                    startX = e.clientX - charElement.offsetLeft;
                    startY = e.clientY - charElement.offsetTop;
                    selectCharacter(charElement);
                    e.preventDefault();
                }}
            }}

            document.addEventListener('mousemove', (e) => {{
                if (isDragging && selectedCharacter) {{
                    let newLeft = e.clientX - startX;
                    let newTop = e.clientY - startY;

                    const maxLeft = canvasWidth - selectedCharacter.offsetWidth;
                    const maxTop = canvasHeight - selectedCharacter.offsetHeight;

                    newLeft = Math.max(0, Math.min(newLeft, maxLeft));
                    newTop = Math.max(0, Math.min(newTop, maxTop));

                    selectedCharacter.style.left = newLeft + 'px';
                    selectedCharacter.style.top = newTop + 'px';

                    updateInfoPanel();
                }}

                if (isResizing && selectedCharacter) {{
                    const dx = e.clientX - startX;
                    const dy = e.clientY - startY;

                    let newWidth = startWidth;
                    let newHeight = startHeight;
                    let newLeft = startLeft;
                    let newTop = startTop;

                    const aspectRatio = startWidth / startHeight;
                    const minSize = 40;

                    switch(resizeHandle) {{
                        case 'bottom-right':
                            newWidth = Math.max(minSize, startWidth + dx);
                            newHeight = newWidth / aspectRatio;
                            break;
                        case 'bottom-left':
                            newWidth = Math.max(minSize, startWidth - dx);
                            newHeight = newWidth / aspectRatio;
                            newLeft = startLeft + (startWidth - newWidth);
                            break;
                        case 'top-right':
                            newWidth = Math.max(minSize, startWidth + dx);
                            newHeight = newWidth / aspectRatio;
                            newTop = startTop + (startHeight - newHeight);
                            break;
                        case 'top-left':
                            newWidth = Math.max(minSize, startWidth - dx);
                            newHeight = newWidth / aspectRatio;
                            newLeft = startLeft + (startWidth - newWidth);
                            newTop = startTop + (startHeight - newHeight);
                            break;
                    }}

                    // 경계 체크
                    if (newLeft >= 0 && newTop >= 0 &&
                        newLeft + newWidth <= canvasWidth &&
                        newTop + newHeight <= canvasHeight) {{
                        selectedCharacter.style.width = newWidth + 'px';
                        selectedCharacter.style.height = newHeight + 'px';
                        selectedCharacter.style.left = newLeft + 'px';
                        selectedCharacter.style.top = newTop + 'px';
                    }}

                    updateInfoPanel();
                }}
            }});

            document.addEventListener('mouseup', () => {{
                isDragging = false;
                isResizing = false;
                resizeHandle = null;
            }});

            canvas.addEventListener('click', (e) => {{
                if (e.target === canvas || e.target.classList.contains('background-layer')) {{
                    document.querySelectorAll('.character').forEach(el => {{
                        el.classList.remove('selected');
                        el.querySelectorAll('.resize-handle').forEach(h => h.style.display = 'none');
                    }});
                    selectedCharacter = null;
                    updateInfoPanel();
                }}
            }});

            function resetPositions() {{
                document.querySelectorAll('.character').forEach(el => {{
                    const index = parseInt(el.dataset.index);
                    const char = characters[index];

                    const width = char.width * canvasWidth;
                    const height = char.height * canvasHeight;
                    const left = char.x * canvasWidth - width / 2;
                    const top = char.y * canvasHeight - height / 2;

                    el.style.width = width + 'px';
                    el.style.height = height + 'px';
                    el.style.left = Math.max(0, left) + 'px';
                    el.style.top = Math.max(0, top) + 'px';
                    el.style.transform = char.flip_x ? 'scaleX(-1)' : '';
                    el.dataset.flipped = char.flip_x ? 'true' : 'false';
                }});
                updateInfoPanel();
            }}

            function flipSelected() {{
                if (selectedCharacter) {{
                    const isFlipped = selectedCharacter.dataset.flipped === 'true';
                    selectedCharacter.style.transform = isFlipped ? '' : 'scaleX(-1)';
                    selectedCharacter.dataset.flipped = isFlipped ? 'false' : 'true';
                }}
            }}

            function bringToFront() {{
                if (selectedCharacter) {{
                    const maxZ = Math.max(...Array.from(document.querySelectorAll('.character')).map(el => parseInt(el.style.zIndex) || 1));
                    selectedCharacter.style.zIndex = maxZ + 1;
                }}
            }}

            function sendToBack() {{
                if (selectedCharacter) {{
                    const minZ = Math.min(...Array.from(document.querySelectorAll('.character')).map(el => parseInt(el.style.zIndex) || 1));
                    selectedCharacter.style.zIndex = Math.max(1, minZ - 1);
                }}
            }}

            function savePositions() {{
                const result = [];

                document.querySelectorAll('.character').forEach(el => {{
                    const index = parseInt(el.dataset.index);
                    const char = characters[index];

                    const centerX = (el.offsetLeft + el.offsetWidth / 2) / canvasWidth;
                    const centerY = (el.offsetTop + el.offsetHeight / 2) / canvasHeight;
                    const width = el.offsetWidth / canvasWidth;
                    const height = el.offsetHeight / canvasHeight;
                    const flipped = el.dataset.flipped === 'true';

                    result.push({{
                        id: char.id,
                        name: char.name,
                        image_url: char.image_url,
                        x: centerX,
                        y: centerY,
                        width: width,
                        height: height,
                        z_index: parseInt(el.style.zIndex) || 1,
                        flip_x: flipped
                    }});
                }});

                // Streamlit으로 데이터 전송
                const jsonData = JSON.stringify(result);

                // 세션 스토리지에 저장 (Streamlit에서 읽을 수 있도록)
                sessionStorage.setItem('canvas_placements_{key}', jsonData);

                // 부모 창에 메시지 전송
                window.parent.postMessage({{
                    type: 'streamlit:setComponentValue',
                    data: result
                }}, '*');

                // 시각적 피드백
                const btn = document.querySelector('.btn-primary');
                const originalText = btn.innerHTML;
                btn.innerHTML = '<span>✓</span> 적용됨!';
                btn.style.background = '#4CAF50';
                setTimeout(() => {{
                    btn.innerHTML = originalText;
                    btn.style.background = '#2196F3';
                }}, 1500);
            }}

            createCharacterElements();
        </script>
    </body>
    </html>
    """

    # 컴포넌트 렌더링 (key 파라미터는 지원되지 않음)
    components.html(
        html_code,
        height=canvas_height + 60
    )

    # components.html()은 값을 반환하지 않음
    # 위치 정보는 localStorage/sessionStorage를 통해 관리
    return None


def render_composite_preview(
    background_url: str,
    characters: List[Dict],
    width: int = 1280,
    height: int = 720
) -> "Image.Image":
    """
    합성 미리보기 이미지 생성 (PIL 사용)

    Args:
        background_url: 배경 이미지 URL 또는 경로
        characters: 캐릭터 위치 정보
        width: 출력 너비
        height: 출력 높이

    Returns:
        합성된 PIL Image
    """
    if Image is None:
        raise ImportError("PIL/Pillow가 필요합니다. pip install Pillow")

    from io import BytesIO
    import requests

    # 배경 로드
    if background_url.startswith('http'):
        response = requests.get(background_url, timeout=30)
        bg_image = Image.open(BytesIO(response.content))
    else:
        bg_image = Image.open(background_url)

    # 배경 리사이즈
    bg_image = bg_image.resize((width, height), Image.Resampling.LANCZOS)
    bg_image = bg_image.convert('RGBA')

    # z_index 순으로 정렬
    sorted_chars = sorted(characters, key=lambda c: c.get('z_index', 1))

    # 각 캐릭터 합성
    for char in sorted_chars:
        try:
            # 캐릭터 이미지 로드
            char_url = char.get('image_url') or char.get('image_path')
            if not char_url:
                continue

            if char_url.startswith('http'):
                response = requests.get(char_url, timeout=30)
                char_image = Image.open(BytesIO(response.content))
            else:
                char_image = Image.open(char_url)

            char_image = char_image.convert('RGBA')

            # 크기 계산
            char_width = int(char['width'] * width)
            char_height = int(char['height'] * height)

            # 리사이즈
            char_image = char_image.resize(
                (char_width, char_height),
                Image.Resampling.LANCZOS
            )

            # 좌우 반전
            if char.get('flip_x'):
                char_image = char_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

            # 위치 계산 (중심 기준 -> 좌상단 기준)
            paste_x = int(char['x'] * width - char_width / 2)
            paste_y = int(char['y'] * height - char_height / 2)

            # 경계 체크
            paste_x = max(0, min(paste_x, width - char_width))
            paste_y = max(0, min(paste_y, height - char_height))

            # 합성 (알파 채널 사용)
            bg_image.paste(char_image, (paste_x, paste_y), char_image)

        except Exception as e:
            print(f"[Composite] 캐릭터 합성 오류 ({char.get('name', 'unknown')}): {e}")

    return bg_image


def save_composite_image(
    image: "Image.Image",
    output_path: str,
    format: str = "PNG"
) -> str:
    """합성 이미지 저장"""
    if format.upper() == "JPEG":
        image = image.convert("RGB")
    image.save(output_path, format.upper())
    return output_path
