"""OpenManager for 3ds Max.

Started by the OpenManager macro (category OpenManager). One window per 3ds Max session.
"""
import sys
import traceback

_win = None


def _set_open_flag(on):
    try:
        from pymxs import runtime as rt
        rt.omgr_isOpen = bool(on)
        rt.updateToolbarButtons()
    except Exception:
        pass


def _closed(w):
    global _win
    if _win is w:
        _win = None
    _set_open_flag(False)


def _alive(w):
    try:
        w.isVisible()
        return True
    except RuntimeError:
        return False


def _place(w, main):
    from PySide6 import QtCore, QtWidgets
    st = w.settings
    if main is not None and isinstance(main, QtWidgets.QMainWindow):
        area = QtCore.Qt.DockWidgetArea(st.get("area", int(QtCore.Qt.RightDockWidgetArea.value)))
        main.addDockWidget(area, w)
        if st.get("floating", True):
            w.setFloating(True)
    else:
        w.setFloating(True)
    w.show()
    if w.isFloating():
        screen = (main.screen() if main is not None else None) or QtWidgets.QApplication.primaryScreen()
        avail = screen.availableGeometry()
        g = st.get("geometry")
        if not (g and len(g) == 4 and g[2] >= 360 and g[3] >= 300
                and avail.adjusted(-50, -50, 50, 50).contains(QtCore.QPoint(g[0] + 40, g[1] + 20))):
            width = min(max(900, int(avail.width() * 0.32)), avail.width() - 40)
            height = min(max(1000, int(avail.height() * 0.8)), avail.height() - 60)
            g = [avail.x() + (avail.width() - width) // 2, avail.y() + (avail.height() - height) // 2, width, height]
        w.setGeometry(*g)
        # 3ds Max sizes a newly floated dock after it is shown: apply the size once more on the next turn
        QtCore.QTimer.singleShot(0, lambda: _alive(w) and w.setGeometry(*g))
    w.raise_()
    w.activateWindow()


def show():
    global _win
    if _win is not None and _alive(_win):
        _win.show()
        _win.raise_()
        _win.activateWindow()
        return _win
    try:
        from . import maxlink, window
        main = maxlink.main_window()
        _win = window.SceneManager(main)
        _place(_win, main)
        _set_open_flag(True)
    except Exception:
        traceback.print_exc()
        _win = None
        try:
            from pymxs import runtime as rt
            rt.messageBox("OpenManager could not start.\nSee the MAXScript Listener for details.",
                          title="OpenManager")
        except Exception:
            pass
    return _win


def close():
    global _win
    if _win is not None and _alive(_win):
        _win.close()
    _win = None
    _set_open_flag(False)


def toggle():
    if _win is not None and _alive(_win) and _win.isVisible():
        close()
    else:
        show()


def reload_package():
    """Development helper: close, forget every module of the package and open again."""
    close()
    for k in [k for k in sys.modules if k == __name__ or k.startswith(__name__ + ".")]:
        del sys.modules[k]
    import importlib
    return importlib.import_module(__name__).show()
