# SPDX-License-Identifier: GPL-3.0-or-later
"""A file only sets the properties the cards set (model.prop_refusal, and maxlink.py on a fake 3ds Max).

A change names the property it sets. The setups and the base state travel inside the .max, so a file from someone
else can name any property, or a path through other objects to one, such as the script of a script controller."""

import contextlib
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "package", "OpenManager"))
import fake_max  # noqa: E402

rt = fake_max.install()
from openmanager import maxlink, model  # noqa: E402

CODE = "OM_PAYLOAD_RAN = true"
VALUES = {
    "BooleanClass": True,
    "Float": 1.5,
    "Integer": 2,
    "Color": "#ff0000",
    "Texturemap": "Checker|m",
    "Pipeline": [],
    "Date": 3.0,
    "Filename": "D:/x.hdr",
    "String": "x",
    "Matrix3": "x",
    "Material": "x",
}
ENGINES = {"vray": "V-Ray", "corona": "Corona", "fstorm": "FStorm", "arnold": "Arnold", None: "Scanline"}
# what a file could put where the name of a property belongs
NOT_NAMES = [
    "a b",
    "a;b",
    "fov()",
    'fov"',
    "fov = 1; x",
    "a..b",
    ".fov",
    "fov.",
    "a.b c",
    "1fov",
    "fov[1]",
    "$.fov",
    "",
    "café",
]
CODE_NAMES = [
    "script",
    "Script",
    "SCRIPT",
    "Proceed_Script",
    "Every_Step_Update_Script",
    "preRenderScript",
    "scriptFile",
    "script_file",
    "MAXScriptCode",
    "maxscript",
    "OSLCode",
    "oslcode",
]


def table(card):
    return sorted(set(p["name"] for t in model.all_tabs() if t["id"] == card for p in t["props"]))


def built_by_the_cards():
    """The property of every change maxlink.actions builds when every setting of every card is ticked and has a
    value, for every renderer and every class of camera, sun, dome and map the table knows: {kind: paths}."""
    out = {"node": set(), "layer": set(), "map": set(), "rs": set(), "pipeline": set()}
    for eng, eng_name in ENGINES.items():

        def ticked(card, eng=eng):
            return [(t, p) for t in model.tabs_for(card, eng) for p in t["props"]]

        def setup(card=None):
            s = model.empty_setup(1)
            s["resolution"]["enabled"] = s["camera"]["enabled"] = False
            for t, p in ticked(card) if card else []:
                s["props"]["%d|%s|%s" % (card, t["v_class"], p["name"])] = VALUES[p["class"]]
            return s

        def collect(s, eng_name=eng_name, **scene):
            for a in maxlink.actions(
                s, maxlink.Scene(dict(scene, engine=eng_name)), ticked, None, False, None, {"gi_default": 1}
            ):
                if a[0] in maxlink.PROP_AT:
                    out[a[0]].add(a[maxlink.PROP_AT[a[0]]])
                    if a[0] == "node" and isinstance(a[3], tuple) and a[3][0] == "$pipeline":
                        out["pipeline"].add(a[2])

        for card, block in ((1, "camera"), (3, "sun"), (4, "dome")):  # one node of each class the tabs are for
            for cls in sorted(set(c for t in model.tabs_for(card, eng) for c in t.get("classes") or [])):
                for inside_daylight in (False, True) if card == 3 else (False,):
                    node = {"handle": 7, "name": "n", "class": cls, "kind": block, "locked": False}
                    if inside_daylight:
                        node.update({"class": "DaylightAssemblyHead", "sun_class": cls})
                    s = setup(card)
                    s[block].update(enabled=True, handle=7)
                    collect(s, cameras=[node] if card == 1 else [], lights=[node] if card != 1 else [])
        for cls in sorted(set(c for t in model.tabs_for(6, eng) for c in t.get("classes") or [])):  # one map of each
            s = setup()
            s["environment"].update(enabled=True, cls=cls, name="m")
            for _t, p in ticked(6):
                s["props"]["6|%s|%s" % (cls, p["name"])] = VALUES[p["class"]]
            collect(
                s,
                maps=[
                    {
                        "name": "m",
                        "class": cls,
                        "path": "",
                        "offer": True,
                        "chain": [{"name": "m", "class": cls, "path": ""}],
                    }
                ],
            )
        s = setup(25)  # everything else in one setup
        s["render_custom"]["enabled"] = True
        s["layers"].update(
            enabled=True, set=[dict(model.layer_entry("0"), extra={p["name"]: True for _, p in ticked(14)})]
        )
        s["objects"].update(
            enabled=True, set=[dict(model.object_entry(7, "o"), extra={p["name"]: True for _, p in ticked(23)})]
        )
        s["lights"].update(enabled=True, set=[7])
        for _, p in ticked(26):
            s["props"]["26|7|%s" % p["name"]] = VALUES[p["class"]]
        s["variants"].update(enabled=True, set=[{"value": 1, "layers": ["a", "b"]}])
        s["rs_override"].update(enabled=True, set={"gi_on": True, "progressive_passLimit": 5, "lut_path": "D:/a.cube"})
        s["post"].update(enabled=True, cats={k: {"props": {n: True for n in names}} for k, _, names in model.POST_CATS})
        collect(s)
    return out


def run(acts):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        maxlink.run(acts)
    return out.getvalue()


def called(*names):
    return [c for c in rt.calls if c[0] in names]


class Rules(unittest.TestCase):
    def test_everything_the_cards_build_can_be_set(self):
        built = built_by_the_cards()
        for kind, paths in built.items():
            self.assertTrue(paths, kind)
            for path in sorted(paths):
                self.assertIsNone(model.prop_refusal(kind, path), "%s: %s" % (kind, path))
        # the cards were all there: settings of every kind, with the ones they write in their own way
        self.assertGreater(len(built["node"]), 150)
        self.assertLessEqual(
            {"isHidden", "renderable", "controller.solar_date.controller.value", "sun." + table(3)[0]}, built["node"]
        )
        self.assertLessEqual({"on", "isfrozen", "renderable"}, built["layer"])
        self.assertLessEqual({"uAngle", "output.output_amount", "uvwOffset.y"}, built["map"])
        self.assertLessEqual(
            {"gi_on", "gi_default", "lut_path", "bloomGlare_enabled", "sharpening_amount"}, built["rs"]
        )
        self.assertEqual(built["pipeline"], {"colorMappingPipeline"})

    def test_and_nothing_else_of_an_object_a_layer_or_a_map(self):
        built = built_by_the_cards()
        for kind in ("node", "layer", "map", "pipeline"):
            self.assertEqual(model.card_props()[kind], built[kind], kind)

    def test_the_lists_of_the_lightmix(self):
        for name in model.LIGHTMIX_ARRAYS:
            self.assertIsNone(model.prop_refusal("lightmix", name), name)

    def test_what_the_table_lists_but_no_card_sets(self):
        # names, transforms and materials are in the table for the Property Selector; no change is built from them
        for kind, name in (
            ("node", "name"),
            ("node", "transform"),
            ("node", "material"),
            ("node", "isNodeHidden"),
            ("layer", "name"),
        ):
            self.assertEqual(model.prop_refusal(kind, name), "no card of OpenManager sets it", (kind, name))

    def test_paths_of_the_table_are_the_only_paths(self):
        self.assertIsNone(model.prop_refusal("node", "controller.solar_date.controller.value"))
        self.assertIsNone(model.prop_refusal("map", "output.output_amount"))
        for kind, path in (
            ("node", "controller.script"),
            ("node", "controller.solar_date.controller.script"),
            ("node", "pos.controller.value"),
            ("node", "sun.controller.script"),
            ("node", "target.fov"),
            ("map", "coords.controller.script"),
            ("map", "output.anything"),
            ("layer", "on.x"),
            ("rs", "a.b"),
            ("rs", "bg_texmap.coords.U_Offset"),
            ("operator", "a.b"),
            ("lightmix", "a.b"),
        ):
            self.assertEqual(
                model.prop_refusal(kind, path),
                "no card of OpenManager sets it" if "script" not in path else "it holds code",
                (kind, path),
            )

    def test_a_node_layer_or_map_only_takes_what_its_cards_set(self):
        for kind, name in (
            ("node", "Proceed_Script"),
            ("node", "wirecolor"),
            ("node", "parent"),
            ("node", "FOV"),
            ("layer", "wirecolor"),
            ("map", "anything"),
            ("pipeline", "directOverrideTexmap"),
            ("lightmix", "any_renderer_property"),
            ("other", "fov"),
        ):
            self.assertIsNotNone(model.prop_refusal(kind, name), (kind, name))

    def test_the_renderer_takes_any_plain_setting(self):
        # Render Settings - Override keeps whichever settings of the renderer differ from the default
        for name in ("gi_on", "progressive_passLimit", "system_frameStamp_description", "output_on", "x"):
            self.assertIsNone(model.prop_refusal("rs", name), name)

    def test_an_operator_takes_plain_names_but_not_its_link(self):
        self.assertIsNone(model.prop_refusal("operator", "colorMappingOperator_simpleExposure"))
        self.assertIsNone(model.prop_refusal("operator", "colorMappingOperator_id"))
        self.assertIsNotNone(model.prop_refusal("operator", "colorMappingOperator_nextOperator"))

    def test_text_that_is_not_a_property_name(self):
        for kind in ("node", "layer", "map", "rs", "operator", "lightmix", "pipeline"):
            for name in NOT_NAMES + [None, 5, ["fov"], {"fov": 1}]:
                self.assertEqual(model.prop_refusal(kind, name), "it is not the name of a property", (kind, name))

    def test_a_property_that_holds_code_is_never_set(self):
        for kind in ("node", "layer", "map", "rs", "operator", "lightmix", "pipeline"):
            for name in CODE_NAMES:
                self.assertEqual(model.prop_refusal(kind, name), "it holds code", (kind, name))
                self.assertEqual(model.prop_refusal(kind, "a." + name), "it holds code", (kind, name))

    def test_code_is_told_by_the_word_not_by_letters_inside_one(self):
        for name in CODE_NAMES:
            self.assertTrue(model.holds_code(name), name)
        for name in (
            "description",
            "imageDescription",
            "descriptor_size",
            "colorMappingOperator_simpleExposure",
            "scr_ipt",
        ):
            self.assertFalse(model.holds_code(name), name)

    def test_nothing_in_the_table_holds_code(self):
        for t in model.all_tabs():
            for p in t["props"]:
                self.assertFalse(any(model.holds_code(part) for part in p["name"].split(".")), p["name"])


class Base(unittest.TestCase):
    def setUp(self):
        rt.reset()
        maxlink.take_rejected()
        maxlink.take_refused()
        self.cam = rt.add_node(7, "CoronaCam", "Cam")

    def assert_refused(self, listener, entries):
        self.assertEqual(rt.executed, [])
        self.assertEqual(maxlink.take_refused(), entries)
        self.assertEqual(maxlink.take_refused(), [], "told once")
        self.assertEqual(listener.count("OpenManager: left out the"), len(entries), listener)


class Changes(Base):
    """maxlink.run and maxlink.capture: every change that names a property."""

    SETS = ("omgr_setNode", "omgr_setRS", "omgr_setLayer", "omgr_setMap")
    READS = ("omgr_getRawNode", "omgr_getRawRS", "omgr_getRawLayer", "omgr_getRawMap")

    def test_the_script_of_a_script_controller(self):
        act = ("node", 7, "controller.script", CODE)
        self.assertIsNone(maxlink.capture(act))
        listener = run([act])
        self.assertEqual(called(*self.SETS + self.READS), [])
        self.assert_refused(listener, ["node controller.script"])
        self.assertIn(
            'OpenManager: left out the object setting "controller.script": it holds code '
            "(settings stored in a file are checked before they are applied)",
            listener,
        )

    def test_changes_no_card_makes(self):
        acts = [
            ("node", 7, "Proceed_Script", CODE),
            ("node", 7, "pos.controller.value", 1.0),
            ("node", 7, "wirecolor", 1),
            ("rs", "a.b", 1),
            ("rs", "environment_map.script", CODE),
            ("layer", "0", "x.y", True),
            ("map", "Checker", "m", "coords.script", CODE),
            ("map", "Checker", "m", "anything", 1),
        ]
        for a in acts:
            self.assertIsNone(maxlink.capture(a), a)
        listener = run(acts)
        self.assertEqual(called(*self.SETS + self.READS), [])
        self.assert_refused(
            listener,
            [
                "node Proceed_Script",
                "node pos.controller.value",
                "node wirecolor",
                "rs a.b",
                "rs environment_map.script",
                "layer x.y",
                "map coords.script",
                "map anything",
            ],
        )
        self.assertIn('the renderer setting "a.b": no card of OpenManager sets it', listener)
        self.assertIn('the layer setting "x.y": no card of OpenManager sets it', listener)
        self.assertIn('the map setting "coords.script": it holds code', listener)

    def test_text_that_is_not_a_property_name(self):
        for name in NOT_NAMES:
            rt.reset()
            listener = run(
                [("node", 7, name, 1), ("rs", name, 1), ("layer", "0", name, True), ("map", "Checker", "m", name, 1)]
            )
            self.assertEqual(called(*self.SETS + self.READS), [], repr(name))
            self.assert_refused(listener, ["%s %s" % (k, name) for k in ("node", "rs", "layer", "map")])
            self.assertIn("it is not the name of a property", listener)

    def test_the_changes_of_the_cards_still_run(self):
        acts = [
            ("node", 7, table(1)[0], 45.0),
            ("node", 7, "sun." + table(3)[0], 1.0),
            ("node", 7, "isHidden", True),
            ("node", 7, "controller.solar_date.controller.value", 10.0),
            ("layer", "0", "on", False),
            ("layer", "0", table(14)[0], True),
            ("map", "CoronaBitmap", "hdr", "uAngle", 90.0),
            ("map", "CoronaBitmap", "hdr", "output.output_amount", 2.0),
            ("rs", table(25)[0], 5),
            ("rs", "any_setting_the_override_card_kept", 3),
            ("rs", "bloomGlare_enabled", True),
        ]
        rt.returns.update(omgr_getRawNode=1.0, omgr_getRawRS=1, omgr_getRawLayer=True, omgr_getRawMap=1.0)
        for a in acts:
            self.assertIsNotNone(maxlink.capture(a), a)
        del rt.calls[:]
        listener = run(acts)
        self.assertEqual(
            [c[:-1] for c in called(*self.SETS)],
            [
                ("omgr_set" + {"node": "Node", "rs": "RS", "layer": "Layer", "map": "Map"}[a[0]],) + a[1:-1]
                for a in acts
            ],
        )
        self.assert_refused(listener, [])

    def test_a_chain_of_operators_only_goes_where_a_card_puts_one(self):
        chain = ("$pipeline", json.dumps([{"class": "FilmicOperatorPlugin", "props": {}}]))
        self.assertIsNone(maxlink.capture(("node", 7, "directOverrideTexmap", chain)))
        listener = run([("node", 7, "directOverrideTexmap", chain)])
        self.assertIsNone(self.cam.props["directOverrideTexmap"])
        self.assertEqual(rt.created, [])
        self.assert_refused(listener, ["pipeline directOverrideTexmap"])
        run([("node", 7, "colorMappingPipeline", chain)])
        self.assertEqual([str(o.cls) for o in rt.chain(self.cam, "colorMappingPipeline")], ["FilmicOperatorPlugin"])
        self.assertEqual(maxlink.take_refused(), [])


class Operators(Base):
    """The values of tone-mapping operators (Post-Production card, and the chain of a Corona camera)."""

    PROPS = {
        "colorMappingOperator_highlightCompression": 2.5,
        "colorMappingOperator_enabled": False,
        "colorMappingOperator_nextOperator": 5,
        "a.b": 1,
        "weird name": 1,
        "script": CODE,
        "Proceed_Script": CODE,
    }
    REFUSED = [
        "operator colorMappingOperator_nextOperator",
        "operator a.b",
        "operator weird name",
        "operator script",
        "operator Proceed_Script",
    ]

    def assert_only_its_values(self, op):
        self.assertEqual(
            op.props,
            {
                "colorMappingOperator_nextOperator": None,
                "colorMappingOperator_enabled": False,
                "colorMappingOperator_id": 0,
                "colorMappingOperator_highlightCompression": 2.5,
            },
        )

    def test_the_vfb(self):
        listener = run([("posttone", json.dumps([{"class": "FilmicOperatorPlugin", "props": self.PROPS}]))])
        self.assert_only_its_values(rt.chain()[0])
        self.assert_refused(listener, self.REFUSED)
        self.assertIn('the tone-mapping operator setting "a.b": no card of OpenManager sets it', listener)

    def test_the_chain_of_a_camera(self):
        listener = run(
            [
                (
                    "node",
                    7,
                    "colorMappingPipeline",
                    ("$pipeline", json.dumps([{"class": "FilmicOperatorPlugin", "props": self.PROPS}])),
                )
            ]
        )
        self.assert_only_its_values(rt.chain(self.cam, "colorMappingPipeline")[0])
        self.assert_refused(listener, self.REFUSED)

    def test_only_the_lists_of_the_lightmix(self):
        r = rt.renderers.current
        r.props.update(
            colorMap_lightmixIntensities=None, colorMap_lightmixColors=None, any_renderer_property=None, script=None
        )
        listener = run(
            [
                (
                    "postlm",
                    json.dumps(
                        {
                            "colorMap_lightmixIntensities": [1.0, 2.0],
                            "colorMap_lightmixColors": [[255, 0, 0]],
                            "colormap_lightselect_elementNames": ["a"],
                            "any_renderer_property": [1],
                            "script": CODE,
                        }
                    ),
                )
            ]
        )
        self.assertEqual(r.props["colorMap_lightmixIntensities"], [1.0, 2.0])
        self.assertEqual(len(r.props["colorMap_lightmixColors"]), 1)
        self.assertIsNone(r.props["any_renderer_property"])
        self.assertIsNone(r.props["script"])
        self.assert_refused(listener, ["lightmix any_renderer_property", "lightmix script"])

    def test_post_production_stored_by_an_older_version(self):
        r = rt.renderers.current
        r.props.update(colorMap_lightmixIntensities=None, script=None)
        listener = run([("post", "", json.dumps({"colorMap_lightmixIntensities": [1.0], "script": CODE, "a.b": 1}))])
        self.assertEqual(r.props["colorMap_lightmixIntensities"], [1.0])
        self.assertIsNone(r.props["script"])
        self.assert_refused(listener, ["rs script", "rs a.b"])


class Reports(Base):
    def test_what_omgr_core_refused_is_told_too(self):
        run([("rs", "a.b", 1)])
        rt.bad_props = ["a.b", "controller.script"]
        self.assertEqual(maxlink.take_refused(), ["rs a.b", "a.b", "controller.script"])
        self.assertEqual(rt.bad_props, [])
        self.assertEqual(maxlink.take_refused(), [])

    def test_a_long_text_is_cut_and_the_same_one_is_told_once(self):
        name = "x;" * 100
        run([("rs", name, 1), ("rs", name, 2)])
        self.assertEqual(maxlink.take_refused(), ["rs " + name[:80] + "..."])


if __name__ == "__main__":
    unittest.main()
