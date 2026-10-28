from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from PIL import Image, ImageOps


Layer = dict[str, object]


def make_layer(image: Image.Image, name: str, source: str) -> Layer:
    """Create a session-local layer with an immutable identity."""

    normalized = ImageOps.exif_transpose(image).convert("RGBA").copy()
    return {
        "layer_id": uuid.uuid4().hex,
        "name": name,
        "source": source,
        "image": normalized,
        "opacity": 1.0,
        "visible": True,
    }


def canvas_size(layers: Sequence[Layer]) -> tuple[int, int] | None:
    """Return the smallest top-left-aligned canvas containing every layer.

    Hidden layers participate in sizing so toggling visibility never changes the
    output dimensions.
    """

    images = [layer.get("image") for layer in layers]
    images = [image for image in images if isinstance(image, Image.Image)]
    if not images:
        return None
    return max(image.width for image in images), max(image.height for image in images)


def _apply_opacity(image: Image.Image, opacity: float) -> Image.Image:
    opacity = max(0.0, min(1.0, float(opacity)))
    if opacity >= 1.0:
        return image

    adjusted = image.copy()
    alpha = adjusted.getchannel("A").point(lambda value: round(value * opacity))
    adjusted.putalpha(alpha)
    return adjusted


def compose_layers(layers: Sequence[Layer]) -> Image.Image | None:
    """Compose front-to-back layer state into an RGBA image.

    State and UI order are front-to-back, while Pillow source-over compositing
    must run from back-to-front.
    """

    size = canvas_size(layers)
    if size is None:
        return None

    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    for layer in reversed(layers):
        if not bool(layer.get("visible", True)):
            continue
        image = layer.get("image")
        if not isinstance(image, Image.Image):
            continue
        rgba = image.convert("RGBA")
        rgba = _apply_opacity(rgba, float(layer.get("opacity", 1.0)))
        canvas.alpha_composite(rgba, dest=(0, 0))
    return canvas


def reorder_layers(layers: Sequence[Layer], ordered_ids: Iterable[str]) -> list[Layer]:
    """Return layers in the requested front-to-back order.

    Invalid or incomplete order requests are ignored to avoid dropping a layer
    because of stale browser state.
    """

    order = list(ordered_ids)
    current_ids = [str(layer.get("layer_id")) for layer in layers]
    if len(order) != len(current_ids) or set(order) != set(current_ids):
        return list(layers)

    by_id = {str(layer.get("layer_id")): layer for layer in layers}
    return [by_id[layer_id] for layer_id in order]


def delete_layer(layers: Sequence[Layer], layer_id: str) -> tuple[list[Layer], dict[str, object] | None, str | None]:
    """Remove one layer and select the layer now occupying its list position."""

    result = list(layers)
    index = next((i for i, layer in enumerate(result) if layer.get("layer_id") == layer_id), None)
    if index is None:
        return result, None, None

    removed = result.pop(index)
    if result:
        selected_id = str(result[min(index, len(result) - 1)].get("layer_id"))
    else:
        selected_id = None

    return result, {"layer": removed, "index": index}, selected_id


def restore_layer(layers: Sequence[Layer], deleted: dict[str, object] | None) -> tuple[list[Layer], str | None]:
    """Restore a deleted layer to its original front-to-back position."""

    result = list(layers)
    if not deleted or not isinstance(deleted.get("layer"), dict):
        return result, None

    layer = deleted["layer"]
    layer_id = str(layer.get("layer_id"))
    if any(str(item.get("layer_id")) == layer_id for item in result):
        return result, layer_id

    index = max(0, min(int(deleted.get("index", 0)), len(result)))
    result.insert(index, layer)
    return result, layer_id
