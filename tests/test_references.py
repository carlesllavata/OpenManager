# SPDX-License-Identifier: GPL-3.0-or-later
"""References to nodes and layers survive merges and renames (model.py, no 3ds Max)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "package", "OpenManager"))
from openmanager import model  # noqa: E402


def setup_with_refs():
    s = model.empty_setup(1)
    s["camera"].update(handle=10, name="Cam", uid="u-cam")
    s["sun"].update(handle=20, name="Sun", uid="u-sun", extra=[{"handle": 21, "name": "Sun2", "props": {}}])
    s["objects"]["set"] = [model.object_entry(30, "Chair")]
    s["lights"]["set"] = [40, 41]
    s["lights"]["uids"] = {"40": "u-l40"}
    s["props"] = {"26|40|multiplier": 5.0, "26|41|multiplier": 2.0, "1|CoronaCam|fov": 45.0}
    s["layers"]["set"] = [model.layer_entry("Furniture"), dict(model.layer_entry("Walls"), uid="u-walls")]
    s["variants"]["set"] = [{"name": "Floors", "value": 1, "layers": ["Wood", "Tiles"]}]
    return s


class Query(unittest.TestCase):
    def test_every_reference_in_order(self):
        q = model.resolve_query([setup_with_refs()])
        self.assertEqual(q, [[10, "u-cam", "Cam"], [20, "u-sun", "Sun"], [21, "", "Sun2"], [-1, "", ""],
                             [30, "", "Chair"], [40, "u-l40", ""], [41, "", ""]])


class ApplyResolved(unittest.TestCase):
    def test_merged_nodes_move_and_light_settings_follow(self):
        s = setup_with_refs()
        results = [(110, "Cam"), (120, "Sun renamed"), (21, "Sun2"), (-1, ""), (130, "Chair"), (140, ""), (41, "")]
        self.assertTrue(model.apply_resolved([s], results))
        self.assertEqual((s["camera"]["handle"], s["sun"]["handle"], s["sun"]["name"]), (110, 120, "Sun renamed"))
        self.assertEqual(s["objects"]["set"][0]["handle"], 130)
        self.assertEqual(s["lights"]["set"], [140, 41])
        self.assertEqual(s["props"]["26|140|multiplier"], 5.0)
        self.assertNotIn("26|40|multiplier", s["props"])
        self.assertEqual(s["lights"]["uids"], {"140": "u-l40"})

    def test_missing_nodes_are_kept_for_when_they_come_back(self):
        s = setup_with_refs()
        results = [(-1, "Cam"), (20, "Sun"), (21, "Sun2"), (-1, ""), (-1, "Chair"), (-1, ""), (41, "")]
        self.assertFalse(model.apply_resolved([s], results))
        self.assertEqual((s["camera"]["handle"], s["objects"]["set"][0]["handle"], s["lights"]["set"]), (10, 30, [40, 41]))

    def test_handle_of_another_node_is_not_used(self):
        s = setup_with_refs()
        results = [(-2, "Cam"), (20, "Sun"), (21, "Sun2"), (-1, ""), (-2, "Chair"), (-2, ""), (41, "")]
        model.apply_resolved([s], results)
        self.assertIsNone(s["camera"]["handle"])
        self.assertEqual((s["camera"]["uid"], s["camera"]["name"]), ("u-cam", "Cam"))  # found again later
        self.assertIsNone(s["objects"]["set"][0]["handle"])
        self.assertEqual(s["lights"]["set"], [40, 41])  # not strict: left alone

    def test_imported_setups_drop_lights_of_other_nodes(self):
        s = setup_with_refs()
        results = [(10, "Cam"), (20, "Sun"), (21, "Sun2"), (-1, ""), (30, "Chair"), (-2, ""), (41, "")]
        model.apply_resolved([s], results, strict=True)
        self.assertEqual(s["lights"]["set"], [41])
        self.assertNotIn("26|40|multiplier", s["props"])
        self.assertEqual(s["props"]["1|CoronaCam|fov"], 45.0)


class Layers(unittest.TestCase):
    def test_layer_refs_cover_cards_and_variants(self):
        s = setup_with_refs()
        refs = model.layer_refs(s)
        self.assertEqual([model.layer_ref_get(r) for r in refs],
                         [("Furniture", ""), ("Walls", "u-walls"), ("Wood", ""), ("Tiles", "")])

    def test_rename_follows(self):
        s = setup_with_refs()
        refs = model.layer_refs(s)
        model.layer_ref_set(refs[1], name="Walls_v2")
        model.layer_ref_set(refs[3], name="Tiles_new", uid="u-tiles")
        self.assertEqual(s["layers"]["set"][1]["name"], "Walls_v2")
        self.assertEqual((s["variants"]["set"][0]["layers"], s["variants"]["set"][0]["uids"]),
                         (["Wood", "Tiles_new"], ["", "u-tiles"]))

    def test_variant_ids_follow_the_list_length(self):
        s = setup_with_refs()
        s["variants"]["set"][0]["uids"] = ["a", "b", "c"]
        model.layer_refs(s)
        self.assertEqual(s["variants"]["set"][0]["uids"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
