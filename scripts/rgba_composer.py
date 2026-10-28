from __future__ import annotations

import base64
import html
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import gradio as gr
from PIL import Image, ImageDraw, ImageOps

import modules.infotext_utils as parameters_copypaste
from modules import script_callbacks
from modules.ui_components import ToolButton


EXTENSION_ROOT = Path(__file__).resolve().parents[1]
if str(EXTENSION_ROOT) not in sys.path:
    sys.path.insert(0, str(EXTENSION_ROOT))

from rgba_composer.core import (  # noqa: E402
    canvas_size,
    compose_layers,
    delete_layer,
    make_layer,
    reorder_layers,
    restore_layer,
)


UNDO_SECONDS = 5
THUMBNAIL_SIZE = 72


def _unique_name(layers: list[dict[str, object]], requested: str) -> str:
    requested = requested.strip()[:120] or "Layer"
    existing = {str(layer.get("name", "")) for layer in layers}
    if requested not in existing:
        return requested

    stem, suffix = os.path.splitext(requested)
    stem = stem or requested
    for number in range(2, 10000):
        candidate = f"{stem} ({number}){suffix}"
        if candidate not in existing:
            return candidate
    return f"{stem} ({time.time_ns()}){suffix}"


def _checker_thumbnail(image: Image.Image) -> str:
    thumb = ImageOps.contain(image.convert("RGBA"), (THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.Resampling.LANCZOS)
    checker = Image.new("RGBA", (THUMBNAIL_SIZE, THUMBNAIL_SIZE), "#d8d8d8")
    draw = ImageDraw.Draw(checker)
    tile = 8
    for y in range(0, THUMBNAIL_SIZE, tile):
        for x in range(0, THUMBNAIL_SIZE, tile):
            if (x // tile + y // tile) % 2:
                draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill="#f2f2f2")

    x = (THUMBNAIL_SIZE - thumb.width) // 2
    y = (THUMBNAIL_SIZE - thumb.height) // 2
    checker.alpha_composite(thumb, dest=(x, y))

    output = io.BytesIO()
    checker.convert("RGB").save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _render_layer_list(
    layers: list[dict[str, object]],
    selected_id: str | None,
    deleted: dict[str, object] | None,
) -> str:
    if not layers:
        cards = '<div class="rgba-composer-empty">画像を追加すると、ここにレイヤーが表示されます。</div>'
    else:
        rows = []
        for index, layer in enumerate(layers):
            layer_id = str(layer["layer_id"])
            name = html.escape(str(layer.get("name", "Layer")), quote=True)
            source = html.escape(str(layer.get("source", "File")))
            image = layer["image"]
            opacity = round(float(layer.get("opacity", 1.0)) * 100)
            visible = bool(layer.get("visible", True))
            selected_class = " selected" if layer_id == selected_id else ""
            hidden_class = " hidden-layer" if not visible else ""
            eye = "👁" if visible else "—"
            rows.append(
                f"""
                <div class="rgba-composer-layer{selected_class}{hidden_class}" draggable="true" data-layer-id="{layer_id}">
                    <button type="button" class="rgba-composer-drag" title="ドラッグして並べ替え" aria-label="ドラッグして並べ替え">≡</button>
                    <img class="rgba-composer-thumb" src="{_checker_thumbnail(image)}" alt="{name}のサムネイル">
                    <div class="rgba-composer-layer-body">
                        <input class="rgba-composer-name" data-layer-id="{layer_id}" value="{name}" maxlength="120" aria-label="レイヤー名">
                        <div class="rgba-composer-meta"><span>{source}</span><span>{image.width}×{image.height}</span><span>{opacity}%</span></div>
                        <input class="rgba-composer-opacity" data-layer-id="{layer_id}" type="range" min="0" max="100" step="1" value="{opacity}" title="不透明度">
                    </div>
                    <div class="rgba-composer-layer-actions">
                        <button type="button" data-action="toggle" data-layer-id="{layer_id}" title="表示／非表示">{eye}</button>
                        <button type="button" data-action="top" data-layer-id="{layer_id}" title="最前面へ">⇈</button>
                        <button type="button" data-action="up" data-layer-id="{layer_id}" title="1つ手前へ">↑</button>
                        <button type="button" data-action="down" data-layer-id="{layer_id}" title="1つ奥へ">↓</button>
                        <button type="button" data-action="bottom" data-layer-id="{layer_id}" title="最背面へ">⇊</button>
                        <button type="button" class="rgba-composer-delete" data-action="delete" data-layer-id="{layer_id}" title="削除">🗑</button>
                    </div>
                    <span class="rgba-composer-order" title="上ほど手前">{index + 1}</span>
                </div>
                """
            )
        cards = "".join(rows)

    undo_html = ""
    if deleted and float(deleted.get("expires_at", 0)) > time.time():
        deleted_layer = deleted.get("layer", {})
        deleted_name = html.escape(str(deleted_layer.get("name", "Layer"))) if isinstance(deleted_layer, dict) else "Layer"
        expires_ms = round(float(deleted["expires_at"]) * 1000)
        undo_html = (
            f'<div class="rgba-composer-undo" data-expires-at="{expires_ms}">'
            f'<span>「{deleted_name}」を削除しました。</span>'
            '<button type="button" data-action="undo">元に戻す</button></div>'
        )

    clear_disabled = " disabled" if not layers else ""
    return f"""
        <div class="rgba-composer-layer-header">
            <span>レイヤー（上ほど手前）</span>
            <button type="button" data-action="clear"{clear_disabled}>すべて削除</button>
        </div>
        <div class="rgba-composer-layer-cards">{cards}</div>
        {undo_html}
    """


def _status(layers: list[dict[str, object]]) -> str:
    size = canvas_size(layers)
    if size is None:
        return "画像がありません。外部ファイルを追加するか、他のタブから転送してください。"
    visible = sum(bool(layer.get("visible", True)) for layer in layers)
    return f"キャンバス: **{size[0]}×{size[1]}** ／ レイヤー: **{len(layers)}**（表示: {visible}）"


def _normalize_selection(layers: list[dict[str, object]], selected_id: str | None) -> str | None:
    ids = {str(layer.get("layer_id")) for layer in layers}
    if selected_id in ids:
        return selected_id
    return str(layers[0].get("layer_id")) if layers else None


def _result(layers, selected_id, deleted):
    layers = list(layers or [])
    selected_id = _normalize_selection(layers, selected_id)
    if deleted and float(deleted.get("expires_at", 0)) <= time.time():
        deleted = None
    return (
        layers,
        selected_id,
        deleted,
        _render_layer_list(layers, selected_id, deleted),
        compose_layers(layers),
        _status(layers),
    )


def _path_and_name(file_value) -> tuple[str, str]:
    path = os.fspath(getattr(file_value, "name", file_value))
    original_name = getattr(file_value, "orig_name", None)
    return path, os.path.basename(original_name or path)


def add_files(files, layers, selected_id, deleted):
    layers = list(layers or [])
    added = []
    errors = []
    for file_value in files or []:
        path, name = _path_and_name(file_value)
        try:
            with Image.open(path) as image:
                layer_name = _unique_name([*added, *layers], name)
                added.append(make_layer(image, layer_name, "File"))
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    if errors:
        gr.Warning("読み込めなかった画像があります: " + "; ".join(errors))
    if added:
        layers = [*added, *layers]
        selected_id = str(added[0]["layer_id"])
        deleted = None

    return (gr.update(value=None), *_result(layers, selected_id, deleted))


def add_transferred_image(image, source, layers, selected_id, deleted):
    layers = list(layers or [])
    if image is not None:
        source = (source or "Transfer").strip()[:40]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = _unique_name(layers, f"{source} {timestamp}")
        layer = make_layer(image, name, source)
        layers.insert(0, layer)
        selected_id = str(layer["layer_id"])
        deleted = None
    return (gr.update(value=None), *_result(layers, selected_id, deleted))


def _move(layers: list[dict[str, object]], layer_id: str, destination: str):
    index = next((i for i, layer in enumerate(layers) if layer.get("layer_id") == layer_id), None)
    if index is None:
        return layers
    target = {"top": 0, "up": max(0, index - 1), "down": min(len(layers) - 1, index + 1), "bottom": len(layers) - 1}[destination]
    layer = layers.pop(index)
    layers.insert(target, layer)
    return layers


def apply_action(action_json, layers, selected_id, deleted):
    layers = list(layers or [])
    try:
        action = json.loads(action_json or "{}")
    except json.JSONDecodeError:
        return _result(layers, selected_id, deleted)

    action_type = action.get("type")
    layer_id = str(action.get("layer_id", ""))

    if action_type == "select":
        selected_id = layer_id
    elif action_type in {"top", "up", "down", "bottom"}:
        layers = _move(layers, layer_id, action_type)
        selected_id = layer_id
    elif action_type == "reorder":
        layers = reorder_layers(layers, action.get("order", []))
        selected_id = layer_id or selected_id
    elif action_type == "toggle":
        for layer in layers:
            if str(layer.get("layer_id")) == layer_id:
                layer["visible"] = not bool(layer.get("visible", True))
                selected_id = layer_id
                break
    elif action_type == "opacity":
        try:
            opacity = max(0.0, min(1.0, float(action.get("value", 100)) / 100.0))
        except (TypeError, ValueError):
            opacity = 1.0
        for layer in layers:
            if str(layer.get("layer_id")) == layer_id:
                layer["opacity"] = opacity
                selected_id = layer_id
                break
    elif action_type == "rename":
        requested = str(action.get("value", "")).strip()[:120]
        for layer in layers:
            if str(layer.get("layer_id")) == layer_id:
                other_layers = [item for item in layers if item is not layer]
                layer["name"] = _unique_name(other_layers, requested or "Layer")
                selected_id = layer_id
                break
    elif action_type == "delete":
        layers, snapshot, selected_id = delete_layer(layers, layer_id)
        if snapshot:
            deleted = {**snapshot, "expires_at": time.time() + UNDO_SECONDS}
    elif action_type == "undo":
        if deleted and float(deleted.get("expires_at", 0)) > time.time():
            layers, restored_id = restore_layer(layers, deleted)
            selected_id = restored_id or selected_id
        deleted = None
    elif action_type == "clear":
        layers = []
        selected_id = None
        deleted = None

    return _result(layers, selected_id, deleted)


def select_layer_at_point(layers, selected_id, deleted, evt: gr.SelectData):
    layers = list(layers or [])
    if isinstance(evt.index, (list, tuple)) and len(evt.index) >= 2:
        x, y = int(evt.index[0]), int(evt.index[1])
        for layer in layers:
            if not bool(layer.get("visible", True)):
                continue
            image = layer.get("image")
            if not isinstance(image, Image.Image) or not (0 <= x < image.width and 0 <= y < image.height):
                continue
            alpha = image.convert("RGBA").getchannel("A").getpixel((x, y))
            alpha *= float(layer.get("opacity", 1.0))
            if alpha > 8:
                selected_id = str(layer.get("layer_id"))
                break
    return _result(layers, selected_id, deleted)


def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as interface:
        layers_state = gr.State([])
        selected_state = gr.State(None)
        deleted_state = gr.State(None)

        gr.Markdown("複数画像を左上揃えで重ね、透明度を保持したRGBA PNGを作成します。上のレイヤーほど手前です。")

        with gr.Row(equal_height=False):
            with gr.Column(scale=2, min_width=320):
                external_files = gr.File(
                    label="外部画像を追加",
                    file_count="multiple",
                    file_types=["image"],
                    type="filepath",
                    elem_id="rgba_composer_external_files",
                )
                with gr.Accordion("転送受信箱", open=False):
                    gr.Markdown("img2img、Extras、Cleanerから転送された画像は自動的に最前面へ追加されます。")
                    transfer_inbox = gr.Image(
                        label="Transferred image",
                        type="pil",
                        image_mode="RGBA",
                        format="png",
                        sources="upload",
                        elem_id="rgba_composer_transfer_inbox",
                    )
                    transfer_source = gr.Textbox(value="Transfer", visible=False, elem_id="rgba_composer_transfer_source")

                layer_html = gr.HTML(
                    value=_render_layer_list([], None, None),
                    elem_id="rgba_composer_layer_list",
                )

                action_json = gr.Textbox(value="", visible=False, elem_id="rgba_composer_action")
                action_button = gr.Button("Apply layer action", visible=False, elem_id="rgba_composer_action_button")

            with gr.Column(scale=3, min_width=400):
                output = gr.Image(
                    label="RGBA Composer output",
                    type="pil",
                    image_mode="RGBA",
                    format="png",
                    interactive=False,
                    show_download_button=True,
                    elem_id="rgba_composer_output",
                    height="60vh",
                )
                status = gr.Markdown(_status([]), elem_id="rgba_composer_status")

                with gr.Row(elem_id="rgba_composer_output_buttons"):
                    send_img2img = ToolButton("🖼️", elem_id="rgba_composer_send_to_img2img", tooltip="Send output to img2img.")
                    send_extras = ToolButton("📐", elem_id="rgba_composer_send_to_extras", tooltip="Send output to Extras Single Image.")
                    send_inpaint_anything = ToolButton("🏁", elem_id="rgba_composer_send_to_inpaint_anything", tooltip="Send an RGB copy to Inpaint Anything.")
                    matte_color = gr.ColorPicker(
                        label="Inpaint Anything背景色",
                        value="#000000",
                        elem_id="rgba_composer_inpaint_matte",
                        min_width=180,
                    )

        state_outputs = [layers_state, selected_state, deleted_state, layer_html, output, status]

        external_files.upload(
            fn=add_files,
            inputs=[external_files, layers_state, selected_state, deleted_state],
            outputs=[external_files, *state_outputs],
            show_progress="hidden",
        )
        transfer_inbox.upload(
            fn=add_transferred_image,
            inputs=[transfer_inbox, transfer_source, layers_state, selected_state, deleted_state],
            outputs=[transfer_inbox, *state_outputs],
            show_progress="hidden",
        )
        action_button.click(
            fn=apply_action,
            inputs=[action_json, layers_state, selected_state, deleted_state],
            outputs=state_outputs,
            show_progress="hidden",
        )
        output.select(
            fn=select_layer_at_point,
            inputs=[layers_state, selected_state, deleted_state],
            outputs=state_outputs,
            show_progress="hidden",
        )

        parameters_copypaste.register_paste_params_button(
            parameters_copypaste.ParamBinding(
                paste_button=send_img2img,
                tabname="img2img",
                source_image_component=output,
            )
        )
        parameters_copypaste.register_paste_params_button(
            parameters_copypaste.ParamBinding(
                paste_button=send_extras,
                tabname="extras",
                source_image_component=output,
            )
        )
        send_inpaint_anything.click(
            fn=lambda _matte: None,
            _js="rgbaComposerSendOutputToInpaintAnything",
            inputs=[matte_color],
            outputs=[],
        )

    return [(interface, "RGBA Composer", "rgba_composer")]


script_callbacks.on_ui_tabs(on_ui_tabs)
