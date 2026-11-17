# SPDX-License-Identifier: GPL-3.0-or-later
"""Class names that come with a file are never run as code (maxlink.py on a fake 3ds Max, see fake_max.py).

A setup names the tone-mapping operators of a chain by their class. The setups travel inside the .max, so a file
from someone else can put anything there: every test here applies a manipulated setup and looks at what reached
3ds Max."""

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

# what a file could carry where the name of a class belongs
NOT_NAMES = [
    'Box(); messageBox "x"',
    "a;b",
    "Filmic OperatorPlugin",
    " FilmicOperatorPlugin",
    "FilmicOperatorPlugin ",
    "FilmicOperatorPlugin()",
    "(FilmicOperatorPlugin)",
    'Filmic"OperatorPlugin',
    "Filmic'OperatorPlugin",
    "rt.FilmicOperatorPlugin",
    "Box.height",
    "FilmicOperatorPlugin\n",
    "Filmic\tOperatorPlugin",
    "FilmicOperatorPlugin--",
    'Box name:"x"',
    "#Box",
    "$Box",
    "FilmicOperatorPluginé",
    "__class__",
    "",
]
NOT_TEXT = [None, 5, ["FilmicOperatorPlugin"], {"class": "FilmicOperatorPlugin"}]


def run(acts):
    """Applies changes as the window does; returns what was written to the MAXScript Listener."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        maxlink.run(acts)
    return out.getvalue()


def post_setup(ops):
    """A setup whose Post-Production / VFB card holds this tone-mapping chain."""
    s = model.empty_setup(1)
    s["resolution"]["enabled"] = False
    s["post"].update(enabled=True, cats={"tonemap": {"ops": ops}})
    return s


def apply_post(ops, through_file=True):
    s = post_setup(ops)
    if through_file:  # as it comes back from the text stored in the .max
        s = model.decode(model.encode([s]))["setups"][0]
    return run(maxlink.actions(s, maxlink.Scene({"engine": "Corona"}), lambda card: [], None, False))


def camera_setup(chain):
    """A setup whose Camera card sets the tone-mapping chain of a Corona camera (handle 7)."""
    s = model.empty_setup(1)
    s["resolution"]["enabled"] = False
    s["camera"].update(handle=7, name="Cam")
    s["props"]["1|CoronaCam|colorMappingPipeline"] = chain
    return s


def apply_camera(chain):
    scene = maxlink.Scene(
        {"engine": "Corona", "cameras": [{"handle": 7, "name": "Cam", "class": "CoronaCam", "locked": False}]}
    )

    def ticked(card):
        return model.enabled_rows(card, "corona", ["CoronaCam|colorMappingPipeline"]) if card == 1 else []

    return run(maxlink.actions(camera_setup(chain), scene, ticked, None, False))


def classes(ops):
    return [str(o.cls) for o in ops]


class Base(unittest.TestCase):
    def setUp(self):
        rt.reset()
        maxlink.take_rejected()
        self.cam = rt.add_node(7, "CoronaCam", "Cam")

    def assert_nothing_ran(self, made=0):
        self.assertEqual(rt.executed, [], "text reached execute")
        self.assertEqual(rt.called, [], "a function was called by its name")
        self.assertEqual(len(rt.created), made, "objects made: %s" % classes(rt.created))

    def assert_left_out(self, listener, names):
        self.assertEqual(maxlink.take_rejected(), names)
        self.assertEqual(maxlink.take_rejected(), [], "told once")
        self.assertEqual(listener.count("OpenManager: left out"), len(names), listener)
        for n in names:
            self.assertIn('left out "%s": it is not a tone-mapping operator class' % n, listener)


class IsClassName(unittest.TestCase):
    def test_class_names(self):
        for name in ("Box", "FilmicOperatorPlugin", "Physical_Sun___Sky_Environment", "VRayHDRI", "_x", "Map2"):
            self.assertTrue(model.is_class_name(name), name)

    def test_anything_else(self):
        for name in NOT_NAMES + NOT_TEXT:
            if name != "__class__":  # looks like a name; it is refused when it is looked up
                self.assertFalse(model.is_class_name(name), repr(name))


class PostProductionCard(Base):
    """apply_tone: the chain of the VFB."""

    def test_text_that_is_not_a_class_name(self):
        for name in NOT_NAMES:
            rt.reset()
            listener = apply_post([{"class": name, "props": {"colorMappingOperator_enabled": True}}])
            self.assert_nothing_ran()
            self.assertEqual(rt.chain(), [], repr(name))
            self.assert_left_out(listener, [name])

    def test_values_that_are_not_text(self):
        for name in NOT_TEXT:
            rt.reset()
            listener = apply_post([{"class": name, "props": {}}], through_file=False)
            self.assert_nothing_ran()
            self.assertEqual(rt.chain(), [])
            self.assertEqual(maxlink.take_rejected(), [repr(name)])
            self.assertIn("OpenManager: left out", listener)

    def test_a_function_is_not_called(self):
        listener = apply_post([{"class": "resetMaxFile", "props": {}}])
        self.assert_nothing_ran()
        self.assertEqual(rt.chain(), [])
        self.assert_left_out(listener, ["resetMaxFile"])

    def test_execute_itself_is_not_called(self):
        listener = apply_post([{"class": "execute", "props": {}}])
        self.assert_nothing_ran()
        self.assert_left_out(listener, ["execute"])

    def test_a_variable_is_not_used(self):
        for name in ("someText", "nothingYet"):
            rt.reset()
            listener = apply_post([{"class": name, "props": {}}])
            self.assert_nothing_ran()
            self.assertEqual(rt.chain(), [])
            self.assert_left_out(listener, [name])

    def test_a_name_3ds_max_does_not_know(self):
        listener = apply_post([{"class": "NoSuchOperatorPlugin", "props": {}}])
        self.assert_nothing_ran()
        self.assert_left_out(listener, ["NoSuchOperatorPlugin"])

    def test_a_class_of_another_kind_is_not_made(self):
        for name in ("Box", "Checker", "CoronaCam", "CoronaRenderer"):
            rt.reset()
            listener = apply_post([{"class": name, "props": {"height": 99.0}}])
            self.assert_nothing_ran()
            self.assertEqual(rt.chain(), [], name)
            self.assert_left_out(listener, [name])

    def test_a_class_of_the_same_kind_that_is_not_an_operator(self):
        listener = apply_post([{"class": "NotAnOperator", "props": {"value": 5}}])
        self.assert_nothing_ran(made=1)  # made to be looked at, then dropped: it never joins the chain
        self.assertEqual(rt.chain(), [])
        self.assertEqual(rt.created[0].props["value"], 0)
        self.assert_left_out(listener, ["NotAnOperator"])

    def test_no_operator_is_known_without_corona(self):
        for name in list(rt._globals):
            if name.endswith("OperatorPlugin"):
                del rt._globals[name]
        listener = apply_post([{"class": "NotAnOperator", "props": {}}])
        self.assert_nothing_ran()
        self.assert_left_out(listener, ["NotAnOperator"])

    def test_operators_are_added_as_before(self):
        listener = apply_post(
            [
                {"class": "FilmicOperatorPlugin", "props": {"colorMappingOperator_highlightCompression": 2.5}},
                {"class": "ContrastOperatorPlugin", "props": {"colorMappingOperator_contrast": 1.5}},
            ]
        )
        self.assert_nothing_ran(made=2)
        chain = rt.chain()
        self.assertEqual(classes(chain), ["FilmicOperatorPlugin", "ContrastOperatorPlugin"])
        self.assertEqual(chain[0].props["colorMappingOperator_highlightCompression"], 2.5)
        self.assertEqual(chain[1].props["colorMappingOperator_contrast"], 1.5)
        self.assert_left_out(listener, [])

    def test_whatever_kind_3ds_max_gives_operators(self):
        rt.reset(operator_kind="CoronaColorMappingOperator")
        apply_post([{"class": "SimpleExposureOperatorPlugin", "props": {}}, {"class": "Box", "props": {}}])
        self.assert_nothing_ran(made=1)
        self.assertEqual(classes(rt.chain()), ["SimpleExposureOperatorPlugin"])
        self.assertEqual(maxlink.take_rejected(), ["Box"])

    def test_operators_of_the_vfb_are_used_in_place(self):
        live = rt.FilmicOperatorPlugin()
        other = rt.SimpleExposureOperatorPlugin()
        live.props["colorMappingOperator_nextOperator"] = other
        rt.renderers.current.props["colorMap_pipeline"] = live
        del rt.created[:]
        listener = apply_post(
            [{"class": "FilmicOperatorPlugin", "props": {"colorMappingOperator_highlightCompression": 3.0}}]
        )
        self.assert_nothing_ran()
        self.assertEqual(rt.chain(), [live, other])
        self.assertEqual(live.props["colorMappingOperator_highlightCompression"], 3.0)
        self.assertFalse(other.props["colorMappingOperator_enabled"])  # not in the setup: switched off
        self.assert_left_out(listener, [])

    def test_the_rest_of_the_chain_still_applies(self):
        listener = apply_post(
            [
                {"class": "FilmicOperatorPlugin", "props": {}},
                {"class": 'Box(); messageBox "x"', "props": {}},
                {"class": "Box", "props": {}},
                {"class": "ContrastOperatorPlugin", "props": {}},
            ]
        )
        self.assert_nothing_ran(made=2)
        self.assertEqual(classes(rt.chain()), ["FilmicOperatorPlugin", "ContrastOperatorPlugin"])
        self.assert_left_out(listener, ['Box(); messageBox "x"', "Box"])

    def test_a_long_text_is_cut_in_the_report(self):
        name = "x;" * 100
        apply_post([{"class": name, "props": {}}])
        self.assertEqual(maxlink.take_rejected(), [name[:80] + "..."])

    def test_the_same_name_is_reported_once(self):
        apply_post([{"class": "a;b", "props": {}}, {"class": "a;b", "props": {}}])
        self.assertEqual(maxlink.take_rejected(), ["a;b"])


class CameraCard(Base):
    """write_pipeline: the chain of a Corona camera (Tone mapping operators in the Camera card)."""

    def test_text_that_is_not_a_class_name(self):
        for name in NOT_NAMES:
            rt.reset()
            cam = rt.add_node(7, "CoronaCam", "Cam")
            listener = apply_camera([{"class": name, "props": {}}])
            self.assert_nothing_ran()
            self.assertEqual(rt.chain(cam, "colorMappingPipeline"), [], repr(name))
            self.assert_left_out(listener, [name])

    def test_entries_that_are_not_operators_at_all(self):
        for item in ("FilmicOperatorPlugin", 5, None, {"props": {}}, ["class", "FilmicOperatorPlugin"]):
            rt.reset()
            cam = rt.add_node(7, "CoronaCam", "Cam")
            apply_camera([item])
            self.assert_nothing_ran()
            self.assertEqual(rt.chain(cam, "colorMappingPipeline"), [], repr(item))
            self.assertEqual(maxlink.take_rejected(), ["None"])

    def test_functions_variables_and_other_classes(self):
        for name in ("resetMaxFile", "execute", "someText", "nothingYet", "NoSuchOperatorPlugin", "Box", "Checker"):
            rt.reset()
            cam = rt.add_node(7, "CoronaCam", "Cam")
            listener = apply_camera([{"class": name, "props": {}}])
            self.assert_nothing_ran()
            self.assertEqual(rt.chain(cam, "colorMappingPipeline"), [], name)
            self.assert_left_out(listener, [name])

    def test_a_class_of_the_same_kind_that_is_not_an_operator(self):
        listener = apply_camera([{"class": "NotAnOperator", "props": {}}])
        self.assert_nothing_ran(made=1)
        self.assertEqual(rt.chain(self.cam, "colorMappingPipeline"), [])
        self.assert_left_out(listener, ["NotAnOperator"])

    def test_operators_are_made_as_before(self):
        listener = apply_camera(
            [
                {"class": "SimpleExposureOperatorPlugin", "props": {"colorMappingOperator_simpleExposure": -1.0}},
                {"class": "a;b", "props": {}},
                {"class": "FilmicOperatorPlugin", "props": {"colorMappingOperator_highlightCompression": 4.0}},
            ]
        )
        self.assert_nothing_ran(made=2)
        chain = rt.chain(self.cam, "colorMappingPipeline")
        self.assertEqual(classes(chain), ["SimpleExposureOperatorPlugin", "FilmicOperatorPlugin"])
        self.assertEqual(chain[0].props["colorMappingOperator_simpleExposure"], -1.0)
        self.assertEqual(chain[1].props["colorMappingOperator_highlightCompression"], 4.0)
        self.assert_left_out(listener, ["a;b"])

    def test_a_chain_read_from_the_scene_goes_back_as_it_was(self):
        apply_camera(
            [
                {"class": "FilmicOperatorPlugin", "props": {"colorMappingOperator_highlightCompression": 4.0}},
                {"class": "ContrastOperatorPlugin", "props": {"colorMappingOperator_contrast": 2.0}},
            ]
        )
        stored = maxlink.read_pipeline(self.cam, "colorMappingPipeline")
        rt.reset()
        cam = rt.add_node(7, "CoronaCam", "Cam")
        apply_camera(json.loads(json.dumps(stored)))
        self.assert_nothing_ran(made=2)
        self.assertEqual(maxlink.read_pipeline(cam, "colorMappingPipeline"), stored)
        self.assertEqual(maxlink.take_rejected(), [])


class StoredChanges(Base):
    """Changes kept in the file (the base state) go through the same look-up."""

    def test_tone_mapping_put_back(self):
        listener = run(
            [("posttone", json.dumps([{"class": 'Box(); messageBox "x"', "props": {}}, {"class": "Box", "props": {}}]))]
        )
        self.assert_nothing_ran()
        self.assertEqual(rt.chain(), [])
        self.assert_left_out(listener, ['Box(); messageBox "x"', "Box"])

    def test_camera_chain_put_back(self):
        listener = run(
            [("node", 7, "colorMappingPipeline", ("$pipeline", json.dumps([{"class": "a;b", "props": {}}])))]
        )
        self.assert_nothing_ran()
        self.assertEqual(rt.chain(self.cam, "colorMappingPipeline"), [])
        self.assert_left_out(listener, ["a;b"])


class Reports(Base):
    def test_names_left_out_by_omgr_core_are_told_too(self):
        apply_post([{"class": "a;b", "props": {}}])
        rt.bad_classes = ["a;b", 'Box(); messageBox "x"']
        self.assertEqual(maxlink.take_rejected(), ["a;b", 'Box(); messageBox "x"'])
        self.assertEqual(rt.bad_classes, [])
        self.assertEqual(maxlink.take_rejected(), [])

    def test_at_most_twenty_names_are_kept(self):
        apply_post([{"class": "bad name %d" % i, "props": {}} for i in range(30)])
        self.assertEqual(len(maxlink.take_rejected()), 20)


if __name__ == "__main__":
    unittest.main()
