from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PIL import Image


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


class ComposerCoreTest(unittest.TestCase):
    def test_canvas_uses_maximum_dimensions_including_hidden_layers(self):
        foreground = make_layer(Image.new("RGBA", (8, 3), "red"), "foreground", "File")
        hidden = make_layer(Image.new("RGBA", (2, 11), "blue"), "hidden", "File")
        hidden["visible"] = False

        self.assertEqual((8, 11), canvas_size([foreground, hidden]))
        self.assertEqual((8, 11), compose_layers([foreground, hidden]).size)

    def test_front_layer_is_alpha_composited_over_back_layer(self):
        front = make_layer(Image.new("RGBA", (1, 1), (0, 0, 255, 128)), "front", "File")
        back = make_layer(Image.new("RGBA", (1, 1), (255, 0, 0, 255)), "back", "File")

        result = compose_layers([front, back])

        self.assertEqual((127, 0, 128, 255), result.getpixel((0, 0)))

    def test_layer_opacity_multiplies_source_alpha(self):
        front = make_layer(Image.new("RGBA", (1, 1), (0, 255, 0, 255)), "front", "File")
        front["opacity"] = 0.5

        result = compose_layers([front])

        self.assertEqual((0, 255, 0, 128), result.getpixel((0, 0)))

    def test_reorder_requires_every_layer_id_once(self):
        first = make_layer(Image.new("RGBA", (1, 1)), "first", "File")
        second = make_layer(Image.new("RGBA", (1, 1)), "second", "File")

        reordered = reorder_layers([first, second], [second["layer_id"], first["layer_id"]])
        ignored = reorder_layers([first, second], [second["layer_id"]])

        self.assertEqual([second["layer_id"], first["layer_id"]], [layer["layer_id"] for layer in reordered])
        self.assertEqual([first["layer_id"], second["layer_id"]], [layer["layer_id"] for layer in ignored])

    def test_delete_selects_neighbor_and_restore_uses_original_position(self):
        layers = [
            make_layer(Image.new("RGBA", (1, 1)), "top", "File"),
            make_layer(Image.new("RGBA", (1, 1)), "middle", "File"),
            make_layer(Image.new("RGBA", (1, 1)), "bottom", "File"),
        ]

        remaining, deleted, selected_id = delete_layer(layers, layers[1]["layer_id"])
        restored, restored_id = restore_layer(remaining, deleted)

        self.assertEqual(layers[2]["layer_id"], selected_id)
        self.assertEqual(layers[1]["layer_id"], restored_id)
        self.assertEqual([layer["layer_id"] for layer in layers], [layer["layer_id"] for layer in restored])


if __name__ == "__main__":
    unittest.main()
