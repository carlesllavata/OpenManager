# SPDX-License-Identifier: GPL-3.0-or-later
"""A variant decides the on/off of its layers (maxlink.actions on a fake 3ds Max, see fake_max.py).

The Layers card and the Variants card can both turn a layer on or off, and the variant wins. When a card of the
active setup is edited, the window sends only the changes that are new (window._apply), so a setup holds one change
of the on/off of each layer: with two, an edit of the Layers card alone would win over the variant."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "package", "OpenManager"))
import fake_max  # noqa: E402

rt = fake_max.install()
from openmanager import maxlink, model  # noqa: E402


def ticked(card):
    """The settings of the Layers card ticked by default, and none of the other cards."""
    return model.enabled_rows(card, "corona", model.default_enabled(card)) if card == 14 else []


def layer_changes(visible, pick, variants=True):
    """The changes of layers of a setup whose Layers card turns layers A, B and C on (visible) or off, and whose
    variant of A and B shows the one in place `pick`."""
    s = model.empty_setup(1)
    s["resolution"]["enabled"] = False
    s["layers"].update(enabled=True, set=[model.layer_entry(n, visible=visible) for n in ("A", "B", "C")])
    s["variants"].update(enabled=variants, set=[{"name": "Floors", "value": pick, "layers": ["A", "B"]}])
    acts = maxlink.actions(s, maxlink.Scene({"engine": "Corona"}), ticked, None, False)
    return [a for a in acts if a[0] == "layer"]


def on_off(acts):
    return [a for a in acts if a[2] == "on"]


class LayersAndVariants(unittest.TestCase):
    def test_one_change_of_the_on_off_of_each_layer_the_variants(self):
        self.assertEqual(
            on_off(layer_changes(True, 1)),
            [("layer", "C", "on", True), ("layer", "A", "on", True), ("layer", "B", "on", False)],
        )

    def test_the_layers_card_still_sets_the_rest_of_a_variants_layer(self):
        acts = layer_changes(True, 2)
        for name in ("A", "B", "C"):
            self.assertIn(("layer", name, "isfrozen", False), acts)
            self.assertIn(("layer", name, "renderable", True), acts)

    def test_with_the_variants_card_off_the_layers_card_turns_them_on_or_off(self):
        self.assertEqual(
            on_off(layer_changes(False, 1, variants=False)),
            [("layer", "A", "on", False), ("layer", "B", "on", False), ("layer", "C", "on", False)],
        )


if __name__ == "__main__":
    unittest.main()
