# SPDX-License-Identifier: GPL-3.0-or-later
"""Where text becomes code, read from the sources (no 3ds Max).

Setups travel inside the .max file, so text from a setup must only reach `execute` / `fileIn` through the scripts
the person has reviewed (model.py, "scripts that come with a file"). These tests list every such place in the
package, so a new one can't slip in unnoticed: add it here only after checking where its text comes from."""

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "package", "OpenManager")
sys.path.insert(0, TOOL)

# classes 3ds Max may not have (a renderer that is not installed), made from fixed text written in omgr_core.ms
FIXED = {"CoronaCam()", "VRayPhysicalCamera()", "CoronaBitmap()", "VRayBitmap()", "CoronaSky()", "VRaySky()"}


def code_of(source):
    """MAXScript with comments and the inside of strings blanked (same length, so positions match the source)."""
    out = list(source)
    i, n = 0, len(source)
    while i < n:
        c = source[i]
        if c == '"':
            j = i + 1
            while j < n and source[j] != '"':
                j += 2 if source[j] == "\\" else 1
            for k in range(i + 1, min(j, n)):
                out[k] = " "
            i = j + 1
        elif source.startswith("--", i):
            j = source.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif source.startswith("/*", i):
            j = source.find("*/", i)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def calls(source, word):
    """[(function it is in, its argument: the text of a string literal, or None for anything else)]."""
    code = code_of(source)
    found = []
    for m in re.finditer(r"(?<![\w.])%s\b" % re.escape(word), code, re.I):
        inside = re.findall(r"^fn\s+(\w+)", code[: m.start()], re.M)
        literal = re.match(r'\s*\(?\s*"((?:[^"\\]|\\.)*)"', source[m.end() :])
        found.append((inside[-1] if inside else None, literal.group(1) if literal else None))
    return found


def read(*parts):
    with open(os.path.join(TOOL, *parts), encoding="utf-8-sig") as f:
        return f.read()


class Scanner(unittest.TestCase):
    def test_strings_and_comments_are_not_code(self):
        src = 'fn a =\n(\n\tx = "execute this" -- execute that\n\t/* execute */ execute "Box()"\n\texecute y\n)\n'
        self.assertEqual(calls(src, "execute"), [("a", "Box()"), ("a", None)])


class CoreMs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read("omgr_core.ms")

    def test_execute_only_runs_fixed_text_or_reviewed_scripts(self):
        found = calls(self.src, "execute")
        fixed = [text for _, text in found if text is not None]
        self.assertEqual(set(fixed), FIXED)
        # the one place that runs text it is given: scripts, which only get here once trusted (model.filter_scripts)
        self.assertEqual([fn for fn, text in found if text is None], ["omgr_runCode"])

    def test_filein_only_runs_the_render_script_files(self):
        self.assertEqual(calls(self.src, "fileIn"), [("omgr_preRender", None), ("omgr_postRender", None)])

    def test_nothing_else_that_runs_text_or_programs(self):
        for word in (
            "python.Execute",
            "python.ExecuteFile",
            "DOSCommand",
            "HiddenDOSCommand",
            "ShellLaunch",
            "readValue",
            "readExpr",
            "include",
        ):
            self.assertEqual(calls(self.src, word), [], word)

    def test_a_map_class_is_found_by_name_not_run(self):
        code = code_of(self.src)
        body = code[code.index("fn omgr_findMap") : code.index("fn omgr_isDome")]
        self.assertNotIn("execute", body.lower())
        self.assertIn("omgr_mapClass cls", body)
        finder = code[code.index("fn omgr_mapClass") : code.index("global omgr_mapCache")]
        self.assertIn("omgr_isClassName cls", finder)
        self.assertIn("textureMap.classes", finder)
        self.assertIn("omgr_badClass cls", finder)

    def test_a_property_named_by_a_change_is_checked_where_it_is_used(self):
        # a property is set by a name that is not fixed text in omgr_setPath only (omgr_setIf gets fixed names) ...
        self.assertEqual(sorted(set(fn for fn, _ in calls(self.src, "setProperty"))), ["omgr_setIf", "omgr_setPath"])
        code = code_of(self.src)
        # ... which, like omgr_getPath, is only reached through the three functions that check the name first
        for name, end in (
            ("omgr_set", "fn omgr_get "),
            ("omgr_get", "fn omgr_node "),
            ("omgr_getRaw", "fn omgr_getRawNode "),
        ):
            body = code[code.index("fn %s obj prop" % name) : code.index(end)]
            self.assertIn("omgr_propOk prop", body, name)
            self.assertLess(body.index("omgr_propOk prop"), body.index("omgr_getPath obj"), name)
        bodies = re.findall(r"^fn[ \t]+(\w+)[^\n]*\n((?:(?!fn[ \t]|global[ \t]).*\n)*)", code, re.M)
        users = set(name for name, body in bodies if re.search(r"\bomgr_(?:set|get)Path\b", body))
        self.assertEqual(users, {"omgr_setPath", "omgr_getPath", "omgr_set", "omgr_get", "omgr_getRaw"})
        check = self.src[self.src.index("fn omgr_propOk") : self.src.index("global omgr_setPath")]
        for piece in (
            "omgr_isClassName part",
            'pattern:"script*"',
            'pattern:"*script"',
            '"oslcode"',
            "append omgr_badProps",
        ):
            self.assertIn(piece, check)

    def test_a_render_preset_is_loaded_in_one_place(self):
        # a preset also keeps the scripts of Render Setup: maxlink.load_preset puts them back after the load
        self.assertEqual(calls(self.src, "renderPresets.LoadAll"), [("omgr_loadPreset", None)])
        code = code_of(self.src)
        scripts = ("usePreRendScript", "preRendScript", "usePostRendScript", "postRendScript")
        self.assertIn("fn omgr_renderSetupScripts = #(%s)" % ", ".join(scripts), code)
        bodies = re.findall(r"^fn[ \t]+(\w+)[^\n]*\n((?:(?!fn[ \t]|global[ \t]).*\n)*)", code, re.M)
        setters = set(name for name, body in bodies if re.search(r"\b(?:%s)[ \t]*=(?!=)" % "|".join(scripts), body))
        self.assertEqual(setters, {"omgr_setRenderSetupScripts"})
        setter = dict(bodies)["omgr_setRenderSetupScripts"]
        for i, name in enumerate(scripts, 1):
            self.assertRegex(setter, r"\b%s = \(.*v\[%d\]" % (name, i))
        link = read("openmanager", "maxlink.py")
        self.assertEqual(len(re.findall(r"omgr_loadPreset", link)), 1)
        loader = link[link.index("def load_preset(path):") : link.index("def run_code(code):")]
        for piece in (
            "kept = list(rt.omgr_renderSetupScripts())",
            "return bool(rt.omgr_loadPreset(path))",
            "finally:",
            "rt.omgr_setRenderSetupScripts(kept)",
        ):
            self.assertIn(piece, loader)
        self.assertLess(loader.index("rt.omgr_renderSetupScripts()"), loader.index("rt.omgr_loadPreset(path)"))
        self.assertLess(loader.index("finally:"), loader.index("rt.omgr_setRenderSetupScripts(kept)"))
        for name in sorted(os.listdir(os.path.join(TOOL, "openmanager"))):
            if name.endswith(".py") and name != "maxlink.py":
                self.assertNotIn("omgr_loadPreset", read("openmanager", name), name)


class OtherMs(unittest.TestCase):
    def test_start_up_scripts_run_no_text_from_a_scene(self):
        for name in ("OpenManager_startup.ms", "omgr_setup.ms"):
            src = read(name)
            self.assertEqual(calls(src, "execute"), [], name)
            self.assertEqual(calls(src, "fileIn"), [], name)
            # python.Execute: only fixed text that closes the window of the version before OpenManager
            self.assertTrue(all(text is not None for _, text in calls(src, "python.Execute")), name)


class Python(unittest.TestCase):
    def test_the_package_runs_no_text(self):
        folder = os.path.join(TOOL, "openmanager")
        banned = re.compile(
            r"rt\.execute|\.executeScriptFile|python\.Execute|(?<![\w.])(?:eval|exec|compile|__import__)\s*\("
            r"|\bsubprocess\b|os\.(?:system|popen|startfile|spawn\w*|exec\w*)\b|\bQProcess\b|\bShellLaunch\b|\bDOSCommand\b"
        )
        for name in sorted(os.listdir(folder)):
            if name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    for n, line in enumerate(f, 1):
                        self.assertIsNone(banned.search(line), "%s:%d: %s" % (name, n, line.strip()))

    def test_scripts_reach_3ds_max_through_two_functions_only(self):
        src = read("openmanager", "maxlink.py")
        self.assertEqual(len(re.findall(r"rt\.omgr_runCode\(", src)), 2)  # the "code" change and run_code()
        self.assertEqual(len(re.findall(r"rt\.omgr_setRenderScripts\(", src)), 1)  # the "renderscripts" change
        self.assertEqual(len(re.findall(r"rt\.fileIn\(", src)), 1)  # omgr_core.ms itself
        self.assertIn("rt.fileIn(CORE)", src)


if __name__ == "__main__":
    unittest.main()
