"""Rich, hand-built PyQt6 stand-ins for driving ``dialog.py``'s real logic.

Unlike ``conftest.py``'s blanket ``MagicMock`` MetaPathFinder (used by every
other test file so that import-level smoke tests stay cheap), these are
genuine pure-Python classes: signals actually call their connected
callbacks, ``QComboBox``/``QTableWidget`` hold real state, so the branch
logic inside ``BlenderExportDialog`` executes (and gets counted) instead of
being swallowed by a Mock.

Install with :func:`install` (idempotent) and tear down with :func:`remove`
so this never leaks into the other test files, which rely on the blanket
mock instead.
"""

from __future__ import annotations

import sys
import types

_MODULE_NAMES = ("PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets")


class _Signal:
    def __init__(self):
        self._fns = []

    def connect(self, fn):
        self._fns.append(fn)

    def emit(self, *args, **kwargs):
        for fn in list(self._fns):
            try:
                fn(*args, **kwargs)
            except TypeError:
                fn()


class _Base:
    def __init__(self, *a, **k):
        pass


# --------------------------------------------------------------------------
# QtCore / QtGui
# --------------------------------------------------------------------------
class Qt:
    class ItemFlag:
        NoItemFlags = 0
        ItemIsEditable = 2


class QCloseEvent:
    def __init__(self):
        self._ignored = False
        self._accepted = False

    def ignore(self):
        self._ignored = True

    def accept(self):
        self._accepted = True


class QColor:
    def __init__(self, *a):
        self.args = a


# --------------------------------------------------------------------------
# QtWidgets
# --------------------------------------------------------------------------
class QWidget(_Base):
    def __init__(self, parent=None):
        self._parent = parent
        self._layout = None
        self._visible = True
        self._tooltip = ""

    def setLayout(self, lay):
        self._layout = lay

    def setToolTip(self, t):
        self._tooltip = t

    def setVisible(self, v):
        self._visible = bool(v)

    def isVisible(self):
        return self._visible

    def setMinimumHeight(self, h):
        pass

    def setMinimumWidth(self, w):
        pass

    def adjustSize(self):
        pass

    def setWindowTitle(self, t):
        pass


class _LayoutBase(_Base):
    def __init__(self, parent=None):
        self._widgets = []
        self._parent = parent
        if parent is not None:
            parent._layout = self

    def addWidget(self, w, *a, **k):
        self._widgets.append(w)

    def addLayout(self, lay):
        self._widgets.append(lay)

    def addStretch(self, n=0):
        pass

    def addSpacing(self, n):
        pass

    def addRow(self, *args):
        # QFormLayout.addRow signatures: (label_text, widget) | (widget,) |
        # (label_widget, widget)
        for a in args:
            if isinstance(a, str):
                continue
            self._widgets.append(a)


class QVBoxLayout(_LayoutBase):
    pass


class QHBoxLayout(_LayoutBase):
    pass


class QFormLayout(_LayoutBase):
    pass


class QGroupBox(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.title = title


class QFrame(QWidget):
    class Shape:
        NoFrame = 0


class QScrollArea(QWidget):
    def setWidgetResizable(self, v):
        pass

    def setWidget(self, w):
        self._widget = w

    def setFrameShape(self, s):
        pass


class QLabel(QWidget):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text

    def setWordWrap(self, v):
        pass

    def setText(self, t):
        self._text = t

    def text(self):
        return self._text


class QLineEdit(QWidget):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self.editingFinished = _Signal()

    def setText(self, t):
        self._text = t

    def text(self):
        return self._text

    def setPlaceholderText(self, t):
        pass

    def setMaxLength(self, n):
        pass


class QCheckBox(QWidget):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self._checked = False
        self.toggled = _Signal()

    def setChecked(self, v):
        v = bool(v)
        changed = v != self._checked
        self._checked = v
        if changed:
            self.toggled.emit(v)

    def isChecked(self):
        return self._checked


class QPushButton(QWidget):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self._checkable = False
        self._checked = False
        self._default = False
        self.clicked = _Signal()
        self.toggled = _Signal()

    def setCheckable(self, v):
        self._checkable = bool(v)

    def setChecked(self, v):
        self._checked = bool(v)
        self.toggled.emit(self._checked)

    def isChecked(self):
        return self._checked

    def setDefault(self, v):
        self._default = bool(v)

    def setText(self, t):
        self._text = t

    def text(self):
        return self._text


class QComboBox(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._current = -1
        self.currentTextChanged = _Signal()
        self.currentIndexChanged = _Signal()

    def addItem(self, text):
        self._items.append(text)
        if self._current == -1:
            self._current = 0

    def addItems(self, items):
        for i in items:
            self.addItem(i)

    def findText(self, text):
        try:
            return self._items.index(text)
        except ValueError:
            return -1

    def setCurrentIndex(self, idx):
        if idx < 0 or idx >= len(self._items):
            return
        self._current = idx
        self.currentTextChanged.emit(self.currentText())
        self.currentIndexChanged.emit(idx)

    def currentIndex(self):
        return self._current

    def currentText(self):
        if 0 <= self._current < len(self._items):
            return self._items[self._current]
        return ""

    def setCurrentText(self, text):
        idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)


class QSpinBox(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._min = 0
        self._max = 100
        self.valueChanged = _Signal()

    def setRange(self, lo, hi):
        self._min, self._max = lo, hi

    def setValue(self, v):
        v = max(self._min, min(self._max, int(v)))
        self._value = v
        self.valueChanged.emit(v)

    def value(self):
        return self._value


class QDoubleSpinBox(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._min = 0.0
        self._max = 100.0
        self._decimals = 2
        self._step = 1.0
        self.valueChanged = _Signal()

    def setRange(self, lo, hi):
        self._min, self._max = float(lo), float(hi)

    def setSingleStep(self, s):
        self._step = s

    def setDecimals(self, n):
        self._decimals = n

    def setValue(self, v):
        v = max(self._min, min(self._max, float(v)))
        self._value = v
        self.valueChanged.emit(v)

    def value(self):
        return self._value


class QTableWidgetItem:
    def __init__(self, text=""):
        self._text = text
        self._flags = 3
        self._tooltip = ""

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t

    def flags(self):
        return self._flags

    def setFlags(self, f):
        self._flags = f

    def setToolTip(self, t):
        self._tooltip = t


class _VHeader:
    def setVisible(self, v):
        pass


class QTableWidget(QWidget):
    class SelectionBehavior:
        SelectRows = 1

    class SelectionMode:
        SingleSelection = 1

    def __init__(self, rows=0, cols=0, parent=None):
        super().__init__(parent)
        self._rows = rows
        self._cols = cols
        self._items = {}
        self._cell_widgets = {}
        self._current_row = -1
        self.currentCellChanged = _Signal()

    def setHorizontalHeaderLabels(self, labels):
        pass

    def setSelectionBehavior(self, b):
        pass

    def setSelectionMode(self, m):
        pass

    def verticalHeader(self):
        return _VHeader()

    def setRowCount(self, n):
        self._rows = n
        self._items = {k: v for k, v in self._items.items() if k[0] < n}
        self._cell_widgets = {
            k: v for k, v in self._cell_widgets.items() if k[0] < n}

    def rowCount(self):
        return self._rows

    def setItem(self, row, col, item):
        self._items[(row, col)] = item

    def item(self, row, col):
        return self._items.get((row, col))

    def setCellWidget(self, row, col, widget):
        self._cell_widgets[(row, col)] = widget

    def cellWidget(self, row, col):
        return self._cell_widgets.get((row, col))

    def resizeColumnsToContents(self):
        pass

    def currentRow(self):
        return self._current_row

    def selectRow(self, row):
        prev = self._current_row
        self._current_row = row
        self.currentCellChanged.emit(row, 0, prev, 0)


class QTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs = []

    def addTab(self, widget, label):
        self._tabs.append((widget, label))


class QAbstractItemView:
    class SelectionBehavior:
        SelectRows = 1

    class SelectionMode:
        SingleSelection = 1


class QMessageBox:
    calls: list = []

    @classmethod
    def information(cls, *a, **k):
        cls.calls.append(("information", a, k))

    @classmethod
    def warning(cls, *a, **k):
        cls.calls.append(("warning", a, k))

    @classmethod
    def critical(cls, *a, **k):
        cls.calls.append(("critical", a, k))

    @classmethod
    def reset(cls):
        cls.calls = []


class QFileDialog:
    open_return = ("", "")
    save_return = ("", "")

    @classmethod
    def getOpenFileName(cls, *a, **k):
        return cls.open_return

    @classmethod
    def getSaveFileName(cls, *a, **k):
        return cls.save_return


class QDialog(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shown = False
        self._hidden = False
        self._stylesheet = ""

    def setStyleSheet(self, s):
        self._stylesheet = s

    def show(self):
        self._shown = True

    def hide(self):
        self._hidden = True

    def raise_(self):
        pass

    def activateWindow(self):
        pass


def install():
    """Install the stub PyQt6 package tree into sys.modules (idempotent)."""
    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_core.Qt = Qt

    qt_gui = types.ModuleType("PyQt6.QtGui")
    qt_gui.QCloseEvent = QCloseEvent
    qt_gui.QColor = QColor

    qt_widgets = types.ModuleType("PyQt6.QtWidgets")
    qt_widgets.QAbstractItemView = QAbstractItemView
    qt_widgets.QCheckBox = QCheckBox
    qt_widgets.QComboBox = QComboBox
    qt_widgets.QDialog = QDialog
    qt_widgets.QDoubleSpinBox = QDoubleSpinBox
    qt_widgets.QFileDialog = QFileDialog
    qt_widgets.QFormLayout = QFormLayout
    qt_widgets.QGroupBox = QGroupBox
    qt_widgets.QHBoxLayout = QHBoxLayout
    qt_widgets.QLabel = QLabel
    qt_widgets.QLineEdit = QLineEdit
    qt_widgets.QMessageBox = QMessageBox
    qt_widgets.QPushButton = QPushButton
    qt_widgets.QScrollArea = QScrollArea
    qt_widgets.QFrame = QFrame
    qt_widgets.QSpinBox = QSpinBox
    qt_widgets.QTableWidget = QTableWidget
    qt_widgets.QTableWidgetItem = QTableWidgetItem
    qt_widgets.QTabWidget = QTabWidget
    qt_widgets.QVBoxLayout = QVBoxLayout
    qt_widgets.QWidget = QWidget

    pyqt6 = types.ModuleType("PyQt6")
    pyqt6.QtCore = qt_core
    pyqt6.QtGui = qt_gui
    pyqt6.QtWidgets = qt_widgets

    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtCore"] = qt_core
    sys.modules["PyQt6.QtGui"] = qt_gui
    sys.modules["PyQt6.QtWidgets"] = qt_widgets


def remove():
    for name in _MODULE_NAMES:
        sys.modules.pop(name, None)
