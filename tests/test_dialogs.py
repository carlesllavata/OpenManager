# SPDX-License-Identifier: GPL-3.0-or-later
"""The question about scripts and render presets that came with a file: Enter must refuse (dialogs.py, real Qt).

The dialog is made and "shown" with the Qt that comes with the Python of 3ds Max, without drawing it on the screen
(WA_DontShowOnScreen): Qt decides which button is the default one when a dialog is shown, so that is what is looked
at, and the keys are real key events."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "package", "OpenManager"))
import fake_max  # noqa: E402

rt = fake_max.install()

try:
    from openmanager import dialogs, model, window
    from PySide6 import QtCore, QtGui, QtTest, QtWidgets
except ImportError as ex:  # PySide6 comes with the Python of 3ds Max
    raise unittest.SkipTest("the dialogs need PySide6 (%s)" % ex) from ex

import test_window as tw  # noqa: E402  (the window without widgets, and its helpers)


def platform_plugins():
    """The folder of Qt plug-ins that has a platform plug-in for this computer, "" when Qt finds its own, or None
    when there is none to be found. Qt stops the whole program with a message box when it has none, so it is only
    started when one is there."""
    if os.environ.get("QT_PLUGIN_PATH") or os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
        return ""
    import PySide6

    own = os.path.join(os.path.dirname(PySide6.__file__), "plugins")
    if os.path.isdir(os.path.join(own, "platforms")):
        return ""
    # the Python of 3ds Max: <3ds Max>\Python\python.exe, with Qt's plug-ins in <3ds Max>\qt\plugins
    folder = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "qt", "plugins")
    return folder if os.path.isfile(os.path.join(folder, "platforms", "qwindows.dll")) else None


PLUGINS = platform_plugins()
APP = []  # the one QApplication of the test run, made when the first test needs it

SCRIPT = ("#1 Cam", "Pre-Setup script", "code", "print 1")
PRESET = ("#1 Cam", "Render preset", "preset", "c:/windows/win.ini")
QUESTIONS = {"scripts": [SCRIPT], "render presets": [PRESET], "scripts and render presets": [SCRIPT, PRESET]}
ACCEPTED, REJECTED = QtWidgets.QDialog.Accepted, QtWidgets.QDialog.Rejected


def shown(rows):
    """The review dialog for these rows, shown as Qt shows a dialog but not drawn on the screen."""
    d = dialogs.ScriptReviewDialog(None, rows)
    d.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    d.show()
    QtWidgets.QApplication.processEvents()
    return d


def buttons(d):
    """(the accepting button, the refusing button) of a review dialog."""
    box = d.findChild(QtWidgets.QDialogButtonBox)
    by_role = {box.buttonRole(b): b for b in box.buttons()}
    return by_role[QtWidgets.QDialogButtonBox.AcceptRole], by_role[QtWidgets.QDialogButtonBox.RejectRole]


def focus(widget):
    """The keyboard focus goes to this widget, as with Tab."""
    widget.setFocus(QtCore.Qt.TabFocusReason)
    QtWidgets.QApplication.sendEvent(widget, QtGui.QFocusEvent(QtCore.QEvent.FocusIn, QtCore.Qt.TabFocusReason))
    QtWidgets.QApplication.processEvents()


def press(widget, key, modifier=QtCore.Qt.NoModifier):
    """A key pressed and released with the focus on this widget; what the widget does not take goes to the dialog."""
    QtTest.QTest.keyClick(widget, key, modifier)
    QtWidgets.QApplication.processEvents()


@unittest.skipIf(PLUGINS is None, "no Qt platform plug-in to be found: Qt is not started")
class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not APP:
            if PLUGINS:
                QtCore.QCoreApplication.addLibraryPath(PLUGINS)
            APP.append(QtWidgets.QApplication.instance() or QtWidgets.QApplication([]))

    def setUp(self):
        self.open = []

    def tearDown(self):
        for d in self.open:
            d.close()
            d.deleteLater()
        QtWidgets.QApplication.processEvents()

    def dialog(self, rows):
        d = shown(rows)
        self.open.append(d)
        return d


class EnterRefuses(Base):
    """Whatever has the focus, Enter is "don't": approving takes a click, or Space on the accepting button."""

    def test_the_refusing_button_is_the_default_once_the_dialog_is_shown(self):
        for what, rows in QUESTIONS.items():
            yes, no = buttons(self.dialog(rows))
            self.assertTrue(no.isDefault(), what)
            self.assertFalse(yes.isDefault(), what)
            self.assertFalse(yes.autoDefault(), what)  # or it would take the default as soon as the focus reaches it

    def test_enter_when_the_dialog_opens(self):
        # when it opens the focus is on the list of what would run (the first widget that takes it), or on nothing
        for what, rows in QUESTIONS.items():
            for where in ("the dialog", "the list"):
                d = self.dialog(rows)
                target = d if where == "the dialog" else d.findChild(QtWidgets.QPlainTextEdit)
                if target is not d:
                    focus(target)
                press(target, QtCore.Qt.Key_Return)
                self.assertEqual(d.result(), REJECTED, "%s, Enter on %s" % (what, where))
                self.assertFalse(d.isVisible())

    def test_enter_after_moving_the_focus_to_the_accepting_button(self):
        for what, rows in QUESTIONS.items():
            d = self.dialog(rows)
            yes, no = buttons(d)
            focus(yes)
            self.assertTrue(no.isDefault(), what)  # the focus did not take the default with it
            press(yes, QtCore.Qt.Key_Return)
            self.assertEqual(d.result(), REJECTED, what)
            self.assertFalse(d.isVisible())

    def test_the_enter_key_of_the_number_pad_too(self):
        for where in ("the dialog", "the accepting button"):
            d = self.dialog([PRESET])
            target = d if where == "the dialog" else buttons(d)[0]
            if target is not d:
                focus(target)
            press(target, QtCore.Qt.Key_Enter, QtCore.Qt.KeypadModifier)
            self.assertEqual(d.result(), REJECTED, where)

    def test_enter_on_the_refusing_button_and_escape_refuse(self):
        d = self.dialog([PRESET])
        focus(buttons(d)[1])
        press(buttons(d)[1], QtCore.Qt.Key_Return)
        self.assertEqual(d.result(), REJECTED)
        for where in ("the dialog", "the list", "the accepting button"):
            d = self.dialog([SCRIPT, PRESET])
            target = {
                "the dialog": d,
                "the list": d.findChild(QtWidgets.QPlainTextEdit),
                "the accepting button": buttons(d)[0],
            }[where]
            if target is not d:
                focus(target)
            press(target, QtCore.Qt.Key_Escape)
            self.assertEqual(d.result(), REJECTED, where)
            self.assertFalse(d.isVisible())

    def test_the_focus_coming_back_leaves_the_refusing_button_as_the_default(self):
        d = self.dialog([SCRIPT])
        yes, no = buttons(d)
        for widget in (yes, d.findChild(QtWidgets.QPlainTextEdit), no, yes):
            focus(widget)
            self.assertTrue(no.isDefault())
            self.assertFalse(yes.isDefault())

    def test_approving_still_works_with_a_click_or_with_space(self):
        for what, rows in QUESTIONS.items():
            d = self.dialog(rows)
            QtTest.QTest.mouseClick(buttons(d)[0], QtCore.Qt.LeftButton)
            QtWidgets.QApplication.processEvents()
            self.assertEqual(d.result(), ACCEPTED, "%s, click" % what)
            d = self.dialog(rows)
            focus(buttons(d)[0])
            press(buttons(d)[0], QtCore.Qt.Key_Space)
            self.assertEqual(d.result(), ACCEPTED, "%s, Space" % what)

    def test_the_dialog_reads_as_before(self):
        for rows in QUESTIONS.values():
            title, message, listed, yes_text, no_text = dialogs.review_text(rows)
            d = self.dialog(rows)
            box = d.findChild(QtWidgets.QDialogButtonBox)
            self.assertEqual([b.text() for b in d.findChildren(QtWidgets.QPushButton)], [yes_text, no_text])
            self.assertEqual(
                [box.buttonRole(b) for b in d.findChildren(QtWidgets.QPushButton)],
                [QtWidgets.QDialogButtonBox.AcceptRole, QtWidgets.QDialogButtonBox.RejectRole],
            )
            self.assertEqual(d.windowTitle(), title)
            self.assertEqual(d.findChild(QtWidgets.QLabel).text(), message)
            self.assertEqual(d.findChild(QtWidgets.QPlainTextEdit).toPlainText(), listed)


class EnterTrustsNothing(Base):
    """What the test in 3ds Max found: Enter on the question about a preset that points at c:/windows/win.ini put it
    in the list of trusted files. Here the window asks with its real dialog, and a key is pressed in it."""

    PRESET_PATH = "c:/windows/win.ini"

    def setUp(self):
        super(EnterTrustsNothing, self).setUp()
        tw.Base.setUp(self)

    def answer_with(self, key, on="the list"):
        """The review dialog as the window opens it, but instead of waiting for the person (exec) it is shown
        without being drawn and this key is pressed in it."""
        test = self

        def shown_and_pressed(dialog):
            dialog.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
            dialog.show()
            QtWidgets.QApplication.processEvents()
            test.open.append(dialog)
            target = {
                "the list": dialog.findChild(QtWidgets.QPlainTextEdit),
                "the accepting button": buttons(dialog)[0],
            }[on]
            focus(target)
            press(target, key)
            return dialog.result()

        return mock.patch.object(dialogs.ScriptReviewDialog, "exec", shown_and_pressed)

    def window_on_a_file_with_a_preset(self):
        w = tw.Window(tw.stored([tw.setup(1, preset=self.PRESET_PATH, pre_setup="print 1")]))
        # the real way of asking of the window (not the recorded answer of the other tests), with a widget that is
        # never shown in the place of the window, which has none here
        parent = QtWidgets.QWidget()
        self.open.append(parent)
        w.ask_scripts = lambda rows: window.SceneManager.ask_scripts(parent, rows)
        return w

    def test_enter_on_the_question_loads_and_trusts_nothing(self):
        for on in ("the list", "the accepting button"):
            tw.Base.setUp(self)
            w = self.window_on_a_file_with_a_preset()
            with self.answer_with(QtCore.Qt.Key_Return, on):
                tw.quiet(w.activate, 1)
            self.assertEqual(w.settings.get("trusted_scripts", []), [], on)
            self.assertEqual(tw.called("omgr_loadPreset") + tw.called("omgr_runCode"), [], on)
            self.assertEqual(w.toasts, [tw.SCRIPT_TOAST % 1 + "\n" + tw.PRESET_TOAST], on)

    def test_space_on_the_accepting_button_is_a_yes(self):
        w = self.window_on_a_file_with_a_preset()
        with self.answer_with(QtCore.Qt.Key_Space, "the accepting button"):
            tw.quiet(w.activate, 1)
        self.assertEqual(
            sorted(w.settings["trusted_scripts"]),
            sorted([model.script_key("preset", self.PRESET_PATH), model.script_key("code", "print 1")]),
        )
        self.assertEqual(tw.called("omgr_loadPreset"), [(self.PRESET_PATH,)])


class TitleBarClose(Base):
    """Dialog.nativeEvent: the X of the title bar, read from the message of Windows."""

    GENERIC = b"windows_generic_MSG"

    def setUp(self):
        super().setUp()
        self.d = dialogs.Dialog()
        self.open.append(self.d)
        patcher = mock.patch.object(QtWidgets.QDialog, "nativeEvent", return_value=(False, 0))
        self.qt = patcher.start()  # what Qt does with a message the dialog doesn't take
        self.addCleanup(patcher.stop)

    def test_the_x_does_what_cancel_does(self):
        import ctypes.wintypes

        msg = ctypes.wintypes.MSG()
        msg.message = dialogs.WM_CLOSE
        self.assertEqual(self.d.nativeEvent(self.GENERIC, ctypes.addressof(msg)), (True, 0))
        self.qt.assert_not_called()

    def test_a_message_it_can_not_read_goes_on_to_qt(self):
        for event_type, message in ((self.GENERIC, "not an address"), ("windows_generic_MSG", 0), (self.GENERIC, None)):
            self.assertEqual(self.d.nativeEvent(event_type, message), (False, 0), repr((event_type, message)))
        self.assertEqual(self.qt.call_count, 3)

    def test_an_unexpected_error_is_not_swallowed(self):
        class Unexpected(Exception):
            pass

        class Address(object):
            def __int__(self):
                raise Unexpected()

        with self.assertRaises(Unexpected):
            self.d.nativeEvent(self.GENERIC, Address())


if __name__ == "__main__":
    unittest.main()
