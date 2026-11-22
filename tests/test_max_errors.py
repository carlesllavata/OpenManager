# SPDX-License-Identifier: GPL-3.0-or-later
"""What the link to 3ds Max catches and what it lets through (maxlink.py and model.import_pulze, on a fake 3ds Max).

Each block that guards a call into 3ds Max catches what pymxs raises for that call (top of maxlink.py): RuntimeError
for a MAXScript error, AttributeError for a name or a property that isn't there. Every test here gives one of those
and sees it handled, then gives an error nobody expects (Unexpected) and sees it reach the caller instead of being
swallowed."""

import base64
import contextlib
import io
import json
import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "package", "OpenManager"))
import fake_max  # noqa: E402

rt = fake_max.install()
from openmanager import maxlink, model  # noqa: E402

# what pymxs gives for a MAXScript error (as probed in 3ds Max 2027)
MAX_ERROR = 'MAXScript exception raised.\n-- Unknown property: "x" in undefined'


class Unexpected(Exception):
    """An error 3ds Max never gives: it must reach the caller."""


def fails(ex):
    """A function that raises `ex`, whatever it is called with."""

    def fn(*args, **kwargs):
        raise ex

    return fn


def max_error():
    return RuntimeError(MAX_ERROR)


def listener(fn, *args, **kwargs):
    """Runs fn; returns (what it returned, what it wrote to the MAXScript Listener)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args, **kwargs)
    return value, out.getvalue()


def lookup_failing(name, ex):
    """The runtime of 3ds Max with looking up `name` raising `ex` (the rest is looked up as before)."""
    real = fake_max.Runtime.__getattr__

    def lookup(self, n):
        if n == name:
            raise ex
        return real(self, n)

    return mock.patch.object(fake_max.Runtime, "__getattr__", lookup)


def property_failing(name, ex, setting=False):
    """getProperty (or setProperty) raising `ex` for the property `name` only."""
    real = rt.setProperty if setting else rt.getProperty

    def call(obj, n, *value):
        if n == name:
            raise ex
        return real(obj, n, *value)

    return mock.patch.object(rt, "setProperty" if setting else "getProperty", call)


def chain_of(*classes):
    """Operators of these classes, each linked to the next; the first one."""
    ops = [getattr(rt, c)() for c in classes]
    for a, b in zip(ops, ops[1:], strict=False):
        a.props["colorMappingOperator_nextOperator"] = b
    return ops[0] if ops else None


class Base(unittest.TestCase):
    def setUp(self):
        rt.reset()
        maxlink.take_rejected()
        maxlink.take_refused()


class Reports(Base):
    """take_rejected and take_refused: the lists omgr_core.ms keeps."""

    def test_a_list_maxscript_can_not_give(self):
        listener(maxlink._reject, "a;b", "a tone-mapping operator class")
        with mock.patch.object(rt, "omgr_takeBadClasses", fails(max_error())):
            self.assertEqual(maxlink.take_rejected(), ["a;b"])
        listener(maxlink._prop_ok, "operator", "a.b")
        with mock.patch.object(rt, "omgr_takeBadProps", fails(max_error())):
            self.assertEqual(maxlink.take_refused(), ["operator a.b"])

    def test_an_unexpected_error_is_not_swallowed(self):
        with mock.patch.object(rt, "omgr_takeBadClasses", fails(Unexpected())), self.assertRaises(Unexpected):
            maxlink.take_rejected()
        with mock.patch.object(rt, "omgr_takeBadProps", fails(Unexpected())), self.assertRaises(Unexpected):
            maxlink.take_refused()


class Lookups(Base):
    """_global, _kind and new_operator: class names are looked up, never run."""

    def test_a_name_3ds_max_does_not_know(self):
        self.assertIsNone(maxlink._global("NoSuchOperatorPlugin"))

    def test_an_unexpected_error_while_looking_up(self):
        with lookup_failing("FilmicOperatorPlugin", Unexpected()), self.assertRaises(Unexpected):
            maxlink._global("FilmicOperatorPlugin")

    def test_a_class_maxscript_can_not_tell(self):
        with mock.patch.object(rt, "classOf", fails(max_error())):
            self.assertIsNone(maxlink._kind(rt.FilmicOperatorPlugin))
        with mock.patch.object(rt, "classOf", fails(Unexpected())), self.assertRaises(Unexpected):
            maxlink._kind(rt.FilmicOperatorPlugin)

    def test_an_operator_3ds_max_can_not_make(self):
        with property_failing("colorMappingOperator_nextOperator", max_error()):
            op, out = listener(maxlink.new_operator, "FilmicOperatorPlugin")
        self.assertIsNone(op)
        self.assertEqual(maxlink.take_rejected(), ["FilmicOperatorPlugin"])
        self.assertIn('left out "FilmicOperatorPlugin"', out)

    def test_an_unexpected_error_while_making_one(self):
        with property_failing("colorMappingOperator_nextOperator", Unexpected()), self.assertRaises(Unexpected):
            maxlink.new_operator("FilmicOperatorPlugin")


class Chains(Base):
    """read_pipeline and write_pipeline: the tone-mapping chain of a Corona camera."""

    def setUp(self):
        super().setUp()
        self.cam = rt.add_node(7, "CoronaCam", "Cam")

    def test_an_object_without_a_chain_reads_as_none(self):
        self.assertEqual(maxlink.read_pipeline(rt.add_node(8, "Box"), "colorMappingPipeline"), [])

    def test_a_property_3ds_max_can_not_give_is_left_out(self):
        self.cam.props["colorMappingPipeline"] = chain_of("FilmicOperatorPlugin")
        with property_failing("colorMappingOperator_highlightCompression", max_error()):
            chain = maxlink.read_pipeline(self.cam, "colorMappingPipeline")
        self.assertEqual([c["class"] for c in chain], ["FilmicOperatorPlugin"])
        self.assertNotIn("colorMappingOperator_highlightCompression", chain[0]["props"])
        self.assertIn("colorMappingOperator_enabled", chain[0]["props"])

    def test_an_unexpected_error_while_reading(self):
        self.cam.props["colorMappingPipeline"] = chain_of("FilmicOperatorPlugin")
        with property_failing("colorMappingPipeline", Unexpected()), self.assertRaises(Unexpected):
            maxlink.read_pipeline(self.cam, "colorMappingPipeline")
        with property_failing("colorMappingOperator_enabled", Unexpected()), self.assertRaises(Unexpected):
            maxlink.read_pipeline(self.cam, "colorMappingPipeline")

    def test_values_3ds_max_refuses_are_told_and_the_rest_is_set(self):
        chain = [
            {
                "class": "FilmicOperatorPlugin",
                "props": {
                    "colorMappingOperator_noSuchSetting": 1.0,  # 3ds Max: unknown property
                    "colorMappingOperator_highlightCompression": {"$color": 5},  # a colour that isn't a list
                    "colorMappingOperator_enabled": False,
                },
            },
            {"class": "ContrastOperatorPlugin", "props": {"colorMappingOperator_contrast": 2.0}},
        ]
        _, out = listener(maxlink.write_pipeline, self.cam, "colorMappingPipeline", chain)
        ops = rt.chain(self.cam, "colorMappingPipeline")
        self.assertEqual([str(o.cls) for o in ops], ["FilmicOperatorPlugin", "ContrastOperatorPlugin"])
        self.assertFalse(ops[0].props["colorMappingOperator_enabled"])
        self.assertEqual(ops[0].props["colorMappingOperator_highlightCompression"], 0.0)
        self.assertEqual(ops[1].props["colorMappingOperator_contrast"], 2.0)
        self.assertIn("FilmicOperatorPlugin.colorMappingOperator_noSuchSetting -> ", out)
        self.assertIn("FilmicOperatorPlugin.colorMappingOperator_highlightCompression -> ", out)

    def test_a_link_3ds_max_refuses_is_told(self):
        chain = [{"class": "FilmicOperatorPlugin", "props": {}}, {"class": "ContrastOperatorPlugin", "props": {}}]
        with property_failing("colorMappingOperator_nextOperator", max_error(), setting=True):
            _, out = listener(maxlink.write_pipeline, self.cam, "colorMappingPipeline", chain)
        self.assertEqual([str(o.cls) for o in rt.chain(self.cam, "colorMappingPipeline")], ["FilmicOperatorPlugin"])
        self.assertIn("ContrastOperatorPlugin can't follow the operator before it -> ", out)

    def test_an_unexpected_error_while_writing(self):
        chain = [{"class": "FilmicOperatorPlugin", "props": {"colorMappingOperator_enabled": False}}]
        with property_failing("colorMappingOperator_enabled", Unexpected(), setting=True):
            with self.assertRaises(Unexpected):
                maxlink.write_pipeline(self.cam, "colorMappingPipeline", chain)
        chain.append({"class": "ContrastOperatorPlugin", "props": {}})
        with property_failing("colorMappingOperator_nextOperator", Unexpected(), setting=True):
            with self.assertRaises(Unexpected):
                maxlink.write_pipeline(self.cam, "colorMappingPipeline", chain)


class PostProduction(Base):
    """apply_tone, apply_lightmix and read_post: the VFB of Corona."""

    def test_values_3ds_max_refuses_are_told_and_the_rest_is_set(self):
        _, out = listener(
            maxlink.apply_tone,
            [
                {
                    "class": "FilmicOperatorPlugin",
                    "props": {
                        "colorMappingOperator_noSuchSetting": 1.0,
                        "colorMappingOperator_highlightCompression": {"$color": None},
                        "colorMappingOperator_enabled": False,
                    },
                }
            ],
        )
        (op,) = rt.chain()
        self.assertFalse(op.props["colorMappingOperator_enabled"])
        self.assertIn("FilmicOperatorPlugin.colorMappingOperator_noSuchSetting -> ", out)
        self.assertIn("FilmicOperatorPlugin.colorMappingOperator_highlightCompression -> ", out)

    def test_an_operator_that_can_not_be_switched_off_stays(self):
        rt.renderers.current.props["colorMap_pipeline"] = chain_of("FilmicOperatorPlugin", "ContrastOperatorPlugin")
        with property_failing("colorMappingOperator_enabled", max_error(), setting=True):
            listener(maxlink.apply_tone, [{"class": "FilmicOperatorPlugin", "props": {}}])
        self.assertTrue(rt.chain()[1].props["colorMappingOperator_enabled"])

    def test_an_unexpected_error_in_the_tone_mapping(self):
        with property_failing("colorMappingOperator_enabled", Unexpected(), setting=True):
            with self.assertRaises(Unexpected):
                maxlink.apply_tone([{"class": "FilmicOperatorPlugin", "props": {"colorMappingOperator_enabled": 1}}])
        rt.reset()
        rt.renderers.current.props["colorMap_pipeline"] = chain_of("FilmicOperatorPlugin", "ContrastOperatorPlugin")
        with property_failing("colorMappingOperator_enabled", Unexpected(), setting=True):
            with self.assertRaises(Unexpected):
                maxlink.apply_tone([{"class": "FilmicOperatorPlugin", "props": {}}])

    def test_a_renderer_without_lightmix(self):
        # the renderer of the fake has no LightMix arrays, as 3ds Max's Scanline
        _, out = listener(
            maxlink.apply_lightmix, {"colorMap_lightmixIntensities": [1.0], "colorMap_lightmixColors": []}
        )
        self.assertIn("OpenManager: colorMap_lightmixIntensities -> ", out)
        self.assertIn("OpenManager: colorMap_lightmixColors -> ", out)
        self.assertEqual(maxlink.read_post("lightmix"), {"arrays": {}})
        self.assertIsNone(maxlink.read_post("lightmix", only_active=True))

    def test_an_unexpected_error_in_lightmix(self):
        with mock.patch.object(rt, "setProperty", fails(Unexpected())), self.assertRaises(Unexpected):
            maxlink.apply_lightmix({"colorMap_lightmixIntensities": [1.0]})
        with mock.patch.object(rt, "getProperty", fails(Unexpected())), self.assertRaises(Unexpected):
            maxlink.read_post("lightmix")

    def test_an_older_post_production_on_a_renderer_without_it(self):
        listener(maxlink._run_one, ("post", "", json.dumps({"colorMap_lightmixIntensities": [1.0]})))
        self.assertNotIn("colorMap_lightmixIntensities", rt.renderers.current.props)
        with mock.patch.object(rt, "setProperty", fails(Unexpected())), self.assertRaises(Unexpected):
            maxlink._run_one(("post", "", json.dumps({"colorMap_lightmixIntensities": [1.0]})))


class Run(Base):
    """run: the Render Setup dialog around the changes, and each change on its own."""

    def dialog(self, **calls):
        rt.renderSceneDialog = fake_max.Holder(
            **dict({"isOpen": lambda: True, "commit": lambda: True, "update": lambda: True}, **calls)
        )

    def test_render_setup_that_can_not_be_asked(self):
        for name in ("isOpen", "commit", "update"):
            rt.reset()
            self.dialog(**{name: fails(max_error())})
            listener(maxlink.run, [("res", 640, 480)])
            self.assertEqual([c for c in rt.calls if c[0] == "omgr_setRes"], [("omgr_setRes", 640, 480)], name)

    def test_an_unexpected_error_of_render_setup(self):
        for name in ("isOpen", "commit", "update"):
            rt.reset()
            self.dialog(**{name: fails(Unexpected())})
            with self.assertRaises(Unexpected):
                listener(maxlink.run, [("res", 640, 480)])

    def test_one_change_that_fails_does_not_stop_the_others(self):
        # the boundary of run: whatever a change raises, it is told and the next one is applied
        for ex in (max_error(), Unexpected("broken")):
            rt.reset()
            rt.returns["omgr_setRes"] = fails(ex)
            _, out = listener(maxlink.run, [("res", 640, 480), ("mkdir", "c:/renders")])
            self.assertIn(("omgr_makeDir", "c:/renders"), rt.calls)
            self.assertIn("OpenManager: ('res', 640, 480) -> %s" % ex, out)


class BaseState(Base):
    """_stored and capture: the value a change is about to replace."""

    def test_a_value_that_is_not_a_colour(self):
        like = ("$color", "#000000")
        for v in (5, None, "red", fake_max.Color("a", "b", "c")):
            self.assertIsNone(maxlink._stored(v, like), repr(v))
        self.assertEqual(maxlink._stored(fake_max.Color(255, 0, 16), like), ("$color", "#ff0010"))

    def test_a_value_that_is_not_a_map(self):
        like = ("$texmap", "")
        for v in (5, "Checker", fake_max.Color(1, 2, 3)):
            self.assertIsNone(maxlink._stored(v, like), repr(v))
        self.assertEqual(maxlink._stored(None, like), ("$texmap", ""))

    def test_an_unexpected_error_while_reading_a_value(self):
        class Broken(object):
            @property
            def r(self):
                raise Unexpected()

            name = property(r.fget)

        with self.assertRaises(Unexpected):
            maxlink._stored(Broken(), ("$color", "#000000"))
        with self.assertRaises(Unexpected):
            maxlink._stored(Broken(), ("$texmap", ""))

    def test_what_can_not_be_read_is_not_put_back(self):
        rt.returns["omgr_getRawRS"] = fails(max_error())
        v, out = listener(maxlink.capture, ("rs", "gi_primarySolver", 1))
        self.assertIsNone(v)
        self.assertIn("OpenManager: can't read ('rs', 'gi_primarySolver', 1) to put it back later -> ", out)
        rt.returns["omgr_getTime"] = None  # not a list: TypeError
        self.assertIsNone(listener(maxlink.capture, ("time", 0, 0, 0, 100, 1, "", False))[0])
        rt.returns["omgr_getEnvRaw"] = ["Checker", "x"]  # one value short: ValueError
        self.assertIsNone(listener(maxlink.capture, ("envoff",))[0])

    def test_a_stored_change_in_a_shape_openmanager_never_writes(self):
        for change in (("lightson", "sun"), ("lightson", "sun", 5), ("lightson", "sun", [[1, True, 3]])):
            self.assertIsNotNone(model.action_key(change))  # the stored base keeps it
            self.assertIsNone(listener(maxlink.capture, change)[0], repr(change))

    def test_an_unexpected_error_while_capturing(self):
        rt.returns["omgr_getRawRS"] = fails(Unexpected())
        with self.assertRaises(Unexpected):
            maxlink.capture(("rs", "gi_primarySolver", 1))


class SpecialValues(Base):
    """read_special: colours, maps and chains read from a node or the renderer."""

    def setUp(self):
        super().setUp()
        self.box = rt.add_node(8, "Box", "Box")

    def test_what_can_not_be_read(self):
        self.assertIsNone(maxlink.read_special("node", 8, "wireColor", "Color"))  # no such property
        self.assertIsNone(maxlink.read_special("node", 9, "wireColor", "Color"))  # no such node
        self.assertIsNone(maxlink.read_special("node", 8, "height", "Color"))  # a number, not a colour
        self.assertIsNone(maxlink.read_special("node", 8, "height", "Texturemap"))  # a number, not a map
        self.box.props["wireColor"] = fake_max.Color(255, 128, 0)
        self.assertEqual(maxlink.read_special("node", 8, "wireColor", "Color"), "#ff8000")

    def test_an_unexpected_error(self):
        with mock.patch.object(rt, "getProperty", fails(Unexpected())), self.assertRaises(Unexpected):
            maxlink.read_special("node", 8, "height", "Color")


class Interactive(Base):
    """Corona's interactive render, stopped while a setup is applied and started again."""

    def corona(self, ex=None):
        call = fails(ex) if ex else (lambda: 1)
        rt._globals["CoronaRenderer"] = fake_max.Holder(
            CoronaFp=fake_max.Holder(stopRender=call, startInteractive=call)
        )

    def test_is_it_rendering(self):
        rt.returns["omgr_isRendering"] = 2
        self.assertTrue(maxlink.interactive_running())
        rt.returns["omgr_isRendering"] = fails(max_error())
        self.assertFalse(maxlink.interactive_running())
        rt.returns["omgr_isRendering"] = fails(Unexpected())
        with self.assertRaises(Unexpected):
            maxlink.interactive_running()

    def test_without_corona(self):
        maxlink.interactive_stop()  # rt.CoronaRenderer: a name this 3ds Max doesn't know
        maxlink.interactive_start()

    def test_when_corona_refuses(self):
        self.corona(max_error())
        maxlink.interactive_stop()
        maxlink.interactive_start()

    def test_an_unexpected_error(self):
        self.corona(Unexpected())
        with self.assertRaises(Unexpected):
            maxlink.interactive_stop()
        with self.assertRaises(Unexpected):
            maxlink.interactive_start()


class Viewport(Base):
    def view(self, get_camera):
        rt._globals["viewport"] = fake_max.Holder(getCamera=get_camera)

    def test_the_camera_of_the_view(self):
        self.view(lambda: fake_max.Holder(inode=fake_max.Holder(handle=7)))
        self.assertEqual(maxlink.viewport_camera(), 7)
        self.view(lambda: None)
        self.assertIsNone(maxlink.viewport_camera())

    def test_what_can_not_be_read(self):
        self.view(lambda: fake_max.Holder())  # not a node: no inode
        self.assertIsNone(maxlink.viewport_camera())
        self.view(fails(max_error()))
        self.assertIsNone(maxlink.viewport_camera())

    def test_an_unexpected_error(self):
        self.view(fails(Unexpected()))
        with self.assertRaises(Unexpected):
            maxlink.viewport_camera()


class RenderOutput(Base):
    def test_the_file_a_render_saves(self):
        rt._globals.update(rendSaveFile=True, rendOutputFilename="c:/renders/a.png")
        self.assertEqual(maxlink.render_output(), "c:/renders/a.png")
        rt._globals.update(rendSaveFile=False)
        self.assertEqual(maxlink.render_output(), "")

    def test_what_can_not_be_read_is_not_saving(self):
        rt._globals.update(rendSaveFile=True, rendOutputFilename="c:/renders/a.png")
        with lookup_failing("rendOutputFilename", max_error()):
            self.assertEqual(maxlink.render_output(), "")
        with lookup_failing("rendOutputFilename", Unexpected()), self.assertRaises(Unexpected):
            maxlink.render_output()


class MainWindow(Base):
    def test_outside_3ds_max(self):
        with mock.patch.dict(sys.modules, {"qtmax": None}):  # import qtmax: ImportError
            self.assertIsNone(maxlink.main_window())

    def test_an_unexpected_error(self):
        qtmax = types.SimpleNamespace(GetQMaxMainWindow=fails(Unexpected()))
        with mock.patch.dict(sys.modules, {"qtmax": qtmax}), self.assertRaises(Unexpected):
            maxlink.main_window()


class PulzeData(unittest.TestCase):
    """model.import_pulze: Pulze's SceneManager_Dat is base64 JSON."""

    def test_text_that_is_not_its_data(self):
        for text in ("!!!!", "not base64 at all", base64.b64encode(b"not json").decode(), "é" * 30):
            self.assertIsNone(model.import_pulze(text, 1), text)
        self.assertIsNone(model.import_pulze(base64.b64encode(b"\xff\xfe\x00").decode(), 1))  # not UTF-8
        self.assertIsNone(model.import_pulze(base64.b64encode(b'{"a": 1}').decode(), 1))  # not a list

    def test_its_data(self):
        data = base64.b64encode(json.dumps([{"scenename": {"text": "Day"}}]).encode()).decode()
        self.assertEqual([s["scenename"] for s in model.import_pulze(data, 1)], ["Day"])

    def test_something_that_is_not_text_is_not_swallowed(self):
        with self.assertRaises(TypeError):
            model.import_pulze(None, 1)


if __name__ == "__main__":
    unittest.main()
