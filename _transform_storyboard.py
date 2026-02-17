# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FILE_PATH = r"C:\Users\KIMJAEHEON\longform\pages\8_\U0001f4cb_\uc2a4\ud1a0\ub9ac\ubcf4\ub4dc.py"

NEW_HEADER = """                # === 3. \uc778\ud3ec\uadf8\ub798\ud53d \uc0dd\uc131 ===
                st.markdown("### \U0001f3ac 3. \uc778\ud3ec\uadf8\ub798\ud53d \uc0dd\uc131 (\ub0b4\ubcf4\ub0b4\uae30\uc6a9)")

                # \uc52c \uc218 \uacc4\uc0b0 (\uc774\ubbf8\uc9c0/\ub3d9\uc601\uc0c1 \ubaa8\ub4dc \uacf5\ud1b5)
                scene_count = infographic_data.total_scenes if hasattr(infographic_data, 'total_scenes') else len(infographic_data.scenes)

                output_format = st.radio(
                    "\U0001f4f7 \ucd9c\ub825 \ud615\uc2dd",
                    options=["\U0001f4f8 \uc774\ubbf8\uc9c0 (PNG)", "\U0001f3ac \ub3d9\uc601\uc0c1 (MP4)"],
                    index=0,
                    horizontal=True,
                    key="infographic_output_format",
                    help="\uc774\ubbf8\uc9c0: \uc989\uc2dc \uce90\uccd0 (\ube60\ub984)\n\ub3d9\uc601\uc0c1: CSS \uc560\ub2c8\uba54\uc774\uc158 \ub179\ud654 (\ub290\ub9bc)"
                )

                is_image_mode = "\uc774\ubbf8\uc9c0" in output_format

                if is_image_mode:
                    st.caption("Selenium \uae30\ubc18 PNG \uc774\ubbf8\uc9c0 \uce90\uccd0 (FFmpeg \ubd88\ud544\uc694)")

                    img_gen_mode = st.radio(
                        "\uc0dd\uc131 \ubc94\uc704", ["\uc804\uccb4", "\ubc94\uc704", "\uac1c\ubcc4"],
                        key="img_gen_mode", horizontal=True
                    )

                    if img_gen_mode == "\ubc94\uc704":
                        img_range = st.slider(
                            "\uc52c \ubc94\uc704", min_value=1, max_value=scene_count,
                            value=(1, min(5, scene_count)), key="img_range_slider"
                        )
                        selected_img_indices = list(range(img_range[0] - 1, img_range[1]))
                    elif img_gen_mode == "\uac1c\ubcc4":
                        img_options = [f"\uc52c {i+1}" for i in range(scene_count)]
                        selected_img_labels = st.multiselect(
                            "\uce90\uccd0\ud560 \uc52c \uc120\ud0dd", options=img_options,
                            default=[img_options[0]] if img_options else [],
                            key="img_scene_multiselect"
                        )
                        selected_img_indices = [int(s.replace("\uc52c ", "")) - 1 for s in selected_img_labels]
                    else:
                        selected_img_indices = list(range(scene_count))

                    st.info(f"\U0001f4ca \uc120\ud0dd: {len(selected_img_indices)}\uac1c \uc52c | \u26a1 \uc774\ubbf8\uc9c0 \ubaa8\ub4dc | \u23f1\ufe0f \uc608\uc0c1: ~{len(selected_img_indices)}\ucd08")

                    if st.button("\U0001f4f8 \uc778\ud3ec\uadf8\ub798\ud53d \uc774\ubbf8\uc9c0 \uc0dd\uc131", type="primary", use_container_width=True, key="capture_images"):
                        if not selected_img_indices:
                            st.error("\uce90\uccd0\ud560 \uc52c\uc744 \uc120\ud0dd\ud558\uc138\uc694.")
                        else:
                            try:
                                output_dir = str(project_path / "infographics" / "images")
                                os.makedirs(output_dir, exist_ok=True)

                                progress_bar = st.progress(0)
                                status_text = st.empty()

                                def img_progress(current, total, message):
                                    progress_bar.progress(current / total)
                                    status_text.text(message)

                                from utils.infographic_video_recorder import get_video_recorder

                                with get_video_recorder(output_dir=output_dir) as recorder:
                                    recording_html = (st.session_state.get("modified_infographic_html")
                                                      or st.session_state.get("infographic_html_content")
                                                      or infographic_data.html_code)

                                    results = recorder.capture_selected_scenes_as_images(
                                        html_content=recording_html,
                                        scene_indices=selected_img_indices,
                                        output_dir=output_dir,
                                        progress_callback=img_progress
                                    )

                                progress_bar.progress(1.0)
                                status_text.text(f"\uc644\ub8cc! {len(results)}\uac1c \uc774\ubbf8\uc9c0 \uc0dd\uc131")
                                st.success(f"\u2705 {len(results)}\uac1c \uc778\ud3ec\uadf8\ub798\ud53d \uc774\ubbf8\uc9c0 \uc0dd\uc131 \uc644\ub8cc!")
                                st.rerun()

                            except RuntimeError as e:
                                st.error(f"\uc774\ubbf8\uc9c0 \uce90\uccd0 \ucd08\uae30\ud654 \uc2e4\ud328: {str(e)}")
                                st.info("\ud544\uc218 \uc694\uc18c: Requirement already satisfied: selenium in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (4.15.2)
Requirement already satisfied: webdriver-manager in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (4.0.1)
Requirement already satisfied: pillow in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (11.3.0)
Requirement already satisfied: urllib3<3,>=1.26 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from urllib3[socks]<3,>=1.26->selenium) (2.5.0)
Requirement already satisfied: trio~=0.17 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from selenium) (0.30.0)
Requirement already satisfied: trio-websocket~=0.9 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from selenium) (0.12.2)
Requirement already satisfied: certifi>=2021.10.8 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from selenium) (2025.8.3)
Requirement already satisfied: attrs>=23.2.0 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from trio~=0.17->selenium) (25.3.0)
Requirement already satisfied: sortedcontainers in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from trio~=0.17->selenium) (2.4.0)
Requirement already satisfied: idna in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from trio~=0.17->selenium) (2.10)
Requirement already satisfied: outcome in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from trio~=0.17->selenium) (1.3.0.post0)
Requirement already satisfied: sniffio>=1.3.0 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from trio~=0.17->selenium) (1.3.1)
Requirement already satisfied: cffi>=1.14 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from trio~=0.17->selenium) (1.17.1)
Requirement already satisfied: wsproto>=0.14 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from trio-websocket~=0.9->selenium) (1.2.0)
Requirement already satisfied: pysocks!=1.5.7,<2.0,>=1.5.6 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from urllib3[socks]<3,>=1.26->selenium) (1.7.1)
Requirement already satisfied: requests in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from webdriver-manager) (2.32.4)
Requirement already satisfied: python-dotenv in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from webdriver-manager) (1.1.1)
Requirement already satisfied: packaging in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from webdriver-manager) (25.0)
Requirement already satisfied: pycparser in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from cffi>=1.14->trio~=0.17->selenium) (2.22)
Requirement already satisfied: h11<1,>=0.9.0 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from wsproto>=0.14->trio-websocket~=0.9->selenium) (0.16.0)
Requirement already satisfied: charset_normalizer<4,>=2 in c:\users\kimjaeheon\appdata\local\programs\python\python313\lib\site-packages (from requests->webdriver-manager) (3.4.2)")
                            except Exception as e:
                                st.error(f"\uce90\uccd0 \uc624\ub958: {str(e)}")

                    # \uc774\ubbf8\uc9c0 \ubbf8\ub9ac\ubcf4\uae30
                    images_dir = str(project_path / "infographics" / "images")
                    if os.path.exists(images_dir):
                        image_files = sorted([f for f in os.listdir(images_dir) if f.endswith('.png')])
                        if image_files:
                            st.markdown("#### \U0001f4f8 \uc0dd\uc131\ub41c \uc774\ubbf8\uc9c0")
                            img_cols_count = min(4, len(image_files))
                            for row_start in range(0, min(20, len(image_files)), img_cols_count):
                                img_cols = st.columns(img_cols_count)
                                for col_idx in range(img_cols_count):
                                    img_idx = row_start + col_idx
                                    if img_idx < len(image_files):
                                        with img_cols[col_idx]:
                                            img_path = os.path.join(images_dir, image_files[img_idx])
                                            st.image(img_path, caption=image_files[img_idx], use_container_width=True)

                else:
                    st.caption("Selenium + FFmpeg \uae30\ubc18 MP4 \ub3d9\uc601\uc0c1 \ub179\ud654 (\uc911\uc559\uc815\ub82c + \uace0\ud654\uc9c8)")
"""

print('Script written successfully.')
