# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in for 3ds Max, so the code that talks to it (maxlink.py) runs in the tests without it.

    import fake_max
    rt = fake_max.install()   # before openmanager.maxlink is imported: this is its pymxs.runtime
    rt.reset()                # in setUp: an empty scene again

It only knows what the tests need: a few classes of several kinds, a Corona-like renderer with a chain of
tone-mapping operators, and the omgr_ functions of omgr_core.ms as recorders (rt.calls). `execute` never runs
anything: it keeps the text it was given in rt.executed, where a test can see that nothing got there.
"""

import contextlib
import sys
import types

OPERATOR = {
    "colorMappingOperator_nextOperator": None,
    "colorMappingOperator_enabled": True,
    "colorMappingOperator_id": 0,
}


class Kind(object):
    """What classOf gives for a class (its superclass: GeometryClass, textureMap...) or for a plain value
    (Integer...)."""

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class MaxClass(object):
    """A class of 3ds Max: calling it makes an object, which rt.created keeps."""

    def __init__(self, rt, name, kind, props=None):
        self.rt, self.name, self.kind, self.props = rt, name, kind, dict(props or {})

    def __call__(self, *args, **kwargs):
        obj = MaxObject(self, self.props)
        self.rt.created.append(obj)
        return obj

    def __str__(self):
        return self.name


class MaxObject(object):
    def __init__(self, cls, props=None, name=""):
        self.cls, self.props, self.name = cls, dict(props or {}), name


class MaxFunction(object):
    """A function of 3ds Max: a call is kept in rt.called (the tests expect none)."""

    def __init__(self, rt, name):
        self.rt, self.name = rt, name

    def __call__(self, *args, **kwargs):
        self.rt.called.append(self.name)


class Color(object):
    def __init__(self, r, g, b):
        self.r, self.g, self.b = r, g, b


class Holder(object):
    def __init__(self, **values):
        self.__dict__.update(values)


class Runtime(object):
    def __init__(self, operator_kind="ReferenceTarget"):
        self.executed = []  # every text given to execute
        self.created = []  # every object made by calling a class
        self.called = []  # every 3ds Max function called by name
        self.calls = []  # every omgr_ function called: (name, arguments...)
        self.returns = {}  # what an omgr_ function gives back: {name: value, or a function of its arguments}
        self.bad_classes = []  # what omgr_core.ms would have in omgr_badClasses
        self.bad_props = []  # and in omgr_badProps
        # Render Setup > Scripts: usePreRendScript, preRendScript, usePostRendScript, postRendScript
        self.render_setup_scripts = [False, "", False, ""]
        self.nodes = {}  # handle -> object
        self._kinds = {}
        self._globals = {}
        self.operator_kind = self.kind(operator_kind)
        for name, prop in (
            ("SimpleExposureOperatorPlugin", "simpleExposure"),
            ("FilmicOperatorPlugin", "highlightCompression"),
            ("ContrastOperatorPlugin", "contrast"),
        ):
            self.define(name, self.operator_kind, dict(OPERATOR, **{"colorMappingOperator_" + prop: 0.0}))
        self.define("NotAnOperator", self.operator_kind, {"value": 0})  # same kind of class, but no operator
        self.define("Box", self.kind("GeometryClass"), {"height": 10.0})
        self.define("Checker", self.kind("textureMap"), {})
        self.define("CoronaCam", self.kind("camera"), {"colorMappingPipeline": None, "directOverrideTexmap": None})
        self._globals["resetMaxFile"] = MaxFunction(self, "resetMaxFile")  # a function
        self._globals["someText"] = 'Box(); messageBox "x"'  # a variable that holds text
        self._globals["nothingYet"] = None  # a variable with no value
        self._globals.update(
            renderWidth=1920,
            renderHeight=1080,
            rendSaveFile=False,
            rendOutputFilename="",
            omgr_oldDat="PuzlesSM_Dat",
            omgr_cancel=False,
        )
        renderer = MaxClass(self, "CoronaRenderer", self.kind("RendererClass"))
        self.renderers = Holder(current=MaxObject(renderer, {"colorMap_pipeline": None}))
        self.maxOps = Holder(getNodeByHandle=lambda h: self.nodes.get(h))
        self.renderSceneDialog = Holder(isOpen=lambda: False, commit=lambda: None, update=lambda: None)
        self.Color = Color

    def reset(self, **options):
        self.__dict__.clear()
        self.__init__(**options)

    def kind(self, name):
        return self._kinds.setdefault(name, Kind(name))

    def define(self, name, kind, props=None):
        self._globals[name] = MaxClass(self, name, kind, props)
        return self._globals[name]

    def add_node(self, handle, class_name, name=""):
        cls = self._globals[class_name]
        self.nodes[handle] = MaxObject(cls, cls.props, name)
        return self.nodes[handle]

    def chain(self, obj=None, prop="colorMap_pipeline"):
        """The operators linked from obj.prop (the renderer's VFB chain by default), first to last."""
        op = (obj or self.renderers.current).props[prop]
        out = []
        while op is not None:
            out.append(op)
            op = op.props["colorMappingOperator_nextOperator"]
        return out

    def __getattr__(self, name):
        g = self.__dict__.get("_globals", {})
        if name in g:
            return g[name]
        if name.startswith("omgr_"):

            def recorder(*args, **kwargs):
                self.calls.append((name,) + args)
                value = self.returns.get(name)
                return value(*args, **kwargs) if callable(value) else value

            return recorder
        raise AttributeError(name)  # an unknown name

    # ---- functions of 3ds Max
    def execute(self, text):
        self.executed.append(text)
        raise RuntimeError("the tests never let execute run anything")

    def classOf(self, v):
        if isinstance(v, MaxObject):
            return v.cls
        if isinstance(v, MaxClass):
            return v.kind
        if isinstance(v, Color):
            return self.kind("Color")
        for t, n in ((bool, "BooleanClass"), (int, "Integer"), (float, "Float"), (str, "String")):
            if isinstance(v, t):
                return self.kind(n)
        return self.kind("UndefinedClass" if v is None else "MAXScriptFunction")

    def getProperty(self, obj, name):
        if not isinstance(obj, MaxObject) or name not in obj.props:
            raise RuntimeError("Unknown property: %s" % name)
        return obj.props[name]

    def setProperty(self, obj, name, value):
        if not isinstance(obj, MaxObject) or name not in obj.props:
            raise RuntimeError("Unknown property: %s" % name)
        obj.props[name] = value

    def getPropNames(self, obj):
        return list(obj.props)

    def Name(self, text):
        return text

    def redrawViews(self):
        pass

    def omgr_takeBadClasses(self):
        out, self.bad_classes = self.bad_classes, []
        return out

    def omgr_takeBadProps(self):
        out, self.bad_props = self.bad_props, []
        return out

    def omgr_renderSetupScripts(self):
        self.calls.append(("omgr_renderSetupScripts",))
        return list(self.render_setup_scripts)

    def omgr_setRenderSetupScripts(self, values):
        self.calls.append(("omgr_setRenderSetupScripts",) + tuple(values))
        self.render_setup_scripts = list(values)
        return True


def install():
    """Puts the fake in place of pymxs (once) and returns its runtime."""
    mod = sys.modules.get("pymxs")
    if mod is None or not isinstance(getattr(mod, "runtime", None), Runtime):
        mod = types.ModuleType("pymxs")
        mod.runtime = Runtime()
        mod.undo = lambda *args, **kwargs: contextlib.nullcontext()
        sys.modules["pymxs"] = mod
    return mod.runtime
