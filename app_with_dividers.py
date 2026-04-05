# app_with_dividers.py
# FVTT Journal -> PDF (PySide6 GUI)
# Desktop app only: loads Foundry journal export ZIPs and generates a PDF.

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import traceback
from typing import List, Optional, Tuple, Any, Dict

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fvtt_parser_with_images_and_zip import parse_journal
from pdf_builder_with_images import build_pdf, Selection


def _ensure_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _extract_page_headings(page) -> List[str]:
    # For tree UI: show heading titles if present
    hs = getattr(page, "headings", None) or []
    out = []
    for h in hs:
        t = getattr(h, "title", None)
        if t:
            out.append(t)
    return out


def resource_path(*parts: str) -> str:
    """
    Resolve resource paths both from source and from a PyInstaller bundle.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def writable_cache_dir(*parts: str) -> str:
    """
    Return a user-writable cache directory. Avoid writing into a PyInstaller bundle
    or a protected install directory.
    """
    base = (
        os.getenv("LOCALAPPDATA")
        or os.getenv("APPDATA")
        or os.path.join(os.path.expanduser("~"), ".cache")
        or tempfile.gettempdir()
    )
    path = os.path.join(base, "FVTT_Journal_to_PDF", *parts)
    os.makedirs(path, exist_ok=True)
    return path


def discover_builtin_backgrounds() -> Dict[str, str]:
    bg_dir = resource_path("backgrounds")
    if not os.path.isdir(bg_dir):
        return {}
    out: Dict[str, str] = {}
    for name in sorted(os.listdir(bg_dir)):
        if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        label = os.path.splitext(name)[0].replace("_", " ").replace("-", " ").title()
        out[label] = os.path.join(bg_dir, name)
    return out


class BuildWorker(QThread):
    ok = Signal(str)
    fail = Signal(str)

    def __init__(
        self,
        out_path: str,
        title: str,
        journals: List[Any],
        selection: Selection,
        divider_pages: bool,
        background_path: Optional[str] = None,
        background_mode: str = "fill",
        background_opacity: float = 1.0,
        background_first_page_only: bool = False,
    ):
        super().__init__()
        self.out_path = out_path
        self.title = title
        self.journals = journals
        self.selection = selection
        self.divider_pages = divider_pages
        self.background_path = background_path
        self.background_mode = background_mode
        self.background_opacity = background_opacity
        self.background_first_page_only = background_first_page_only

    def run(self) -> None:
        try:
            build_pdf(
                out_path=self.out_path,
                title=self.title,
                journals=self.journals,
                selection=self.selection,
                divider_pages=self.divider_pages,
                background_path=self.background_path,
                background_mode=self.background_mode,
                background_opacity=self.background_opacity,
                background_first_page_only=self.background_first_page_only,
            )
            self.ok.emit(self.out_path)
        except Exception:
            self.fail.emit(traceback.format_exc())


class BusyDialog(QDialog):
    def __init__(self, parent=None, title="Working…", message="Building PDF…"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(message))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FVTT Journal → PDF")
        self.resize(1100, 700)

        self.journals: List[Any] = []
        self.divider_pages = True
        self.builtin_backgrounds = discover_builtin_backgrounds()
        self.custom_background_path: Optional[str] = None

        # UI
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        top = QHBoxLayout()
        self.btn_add = QPushButton("Open Journals (ZIP)…")
        self.btn_remove = QPushButton("Remove Selected Journal")
        self.btn_generate = QPushButton("Generate PDF…")
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_none = QPushButton("Select None")
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_remove)
        top.addStretch(1)
        top.addWidget(self.btn_select_all)
        top.addWidget(self.btn_select_none)
        top.addWidget(self.btn_generate)
        outer.addLayout(top)

        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel("PDF Background:"))
        self.cmb_background = QComboBox()
        self.cmb_background.setIconSize(QSize(96, 56))
        self.cmb_background.addItem("None", None)
        for label, path in self.builtin_backgrounds.items():
            self._add_background_item(f"Built-in: {label}", path)
        self.cmb_background.addItem("Custom image…", "__custom__")
        self.btn_browse_background = QPushButton("Browse…")
        self.btn_clear_background = QPushButton("Clear")
        self.lbl_background_preview = QLabel()
        self.lbl_background_preview.setFixedSize(120, 70)
        self.lbl_background_preview.setAlignment(Qt.AlignCenter)
        self.lbl_background_preview.setStyleSheet("border: 1px solid #888; background: #222;")
        self.lbl_background = QLabel("No background selected.")
        self.lbl_background.setTextInteractionFlags(Qt.TextSelectableByMouse)

        bg_row.addWidget(self.cmb_background, 1)
        bg_row.addWidget(self.btn_browse_background)
        bg_row.addWidget(self.btn_clear_background)
        bg_row.addWidget(self.lbl_background_preview)
        bg_row.addWidget(self.lbl_background, 2)
        outer.addLayout(bg_row)

        opts_row = QHBoxLayout()
        opts_row.addWidget(QLabel("Mode:"))
        self.cmb_background_mode = QComboBox()
        self.cmb_background_mode.addItem("Fill", "fill")
        self.cmb_background_mode.addItem("Fit", "fit")
        self.cmb_background_mode.addItem("Stretch", "stretch")
        self.cmb_background_mode.addItem("Tile", "tile")

        opts_row.addWidget(self.cmb_background_mode)
        opts_row.addSpacing(12)

        opts_row.addWidget(QLabel("Opacity:"))
        self.sld_background_opacity = QSlider(Qt.Horizontal)
        self.sld_background_opacity.setRange(0, 100)
        self.sld_background_opacity.setValue(100)
        self.sld_background_opacity.setFixedWidth(180)
        self.lbl_background_opacity = QLabel("100%")
        self.lbl_background_opacity.setMinimumWidth(40)

        opts_row.addWidget(self.sld_background_opacity)
        opts_row.addWidget(self.lbl_background_opacity)
        opts_row.addSpacing(12)

        self.chk_background_first_page_only = QCheckBox("Apply to first page only")
        opts_row.addWidget(self.chk_background_first_page_only)
        opts_row.addStretch(1)
        outer.addLayout(opts_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Table of Contents"])
        self.tree.setUniformRowHeights(True)
        outer.addWidget(self.tree, 1)

        self.lbl_status = QLabel("Load a ZIP export to begin.")
        outer.addWidget(self.lbl_status)

        # Wiring
        self.btn_add.clicked.connect(self.add_journals)
        self.btn_remove.clicked.connect(self.remove_selected_journal)
        self.btn_select_all.clicked.connect(lambda: self.set_all_checks(True))
        self.btn_select_none.clicked.connect(lambda: self.set_all_checks(False))
        self.btn_generate.clicked.connect(self.generate_pdf)
        self.cmb_background.currentIndexChanged.connect(self._on_background_changed)
        self.btn_browse_background.clicked.connect(self.browse_background)
        self.btn_clear_background.clicked.connect(self.clear_background)
        self.sld_background_opacity.valueChanged.connect(self._update_background_label)
        self.cmb_background_mode.currentIndexChanged.connect(self._update_background_label)
        self.chk_background_first_page_only.stateChanged.connect(self._update_background_label)

        self._update_background_label()

    def _thumbnail_cache_path(self, source_path: str) -> str:
        try:
            stat = os.stat(source_path)
            fingerprint = f"{os.path.abspath(source_path)}|{stat.st_mtime_ns}|{stat.st_size}"
        except Exception:
            fingerprint = os.path.abspath(source_path)
        name = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16] + ".png"
        return os.path.join(writable_cache_dir("thumbs"), name)

    def _make_background_icon(self, path: str) -> QIcon:
        cache_path = self._thumbnail_cache_path(path)
        pix = QPixmap(cache_path) if os.path.exists(cache_path) else QPixmap()
        if pix.isNull():
            original = QPixmap(path)
            if original.isNull():
                return QIcon()
            thumb = original.scaled(96, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            try:
                thumb.save(cache_path, "PNG")
            except Exception:
                pass
            pix = QPixmap(cache_path) if os.path.exists(cache_path) else thumb

        if pix.isNull():
            return QIcon()
        return QIcon(pix)

    def _add_background_item(self, label: str, path: str) -> None:
        self.cmb_background.addItem(self._make_background_icon(path), label, path)

    def _current_background_path(self) -> Optional[str]:
        data = self.cmb_background.currentData()
        if data == "__custom__":
            return self.custom_background_path
        return data

    def _current_background_mode(self) -> str:
        return str(self.cmb_background_mode.currentData() or "fill")

    def _current_background_opacity(self) -> float:
        return max(0.0, min(1.0, self.sld_background_opacity.value() / 100.0))

    def _update_background_label(self) -> None:
        path = self._current_background_path()
        self.lbl_background_opacity.setText(f"{self.sld_background_opacity.value()}%")

        if path:
            mode_label = self.cmb_background_mode.currentText()
            first_page_label = "first page only" if self.chk_background_first_page_only.isChecked() else "all pages"
            self.lbl_background.setText(f"{os.path.basename(path)}  •  {mode_label}  •  {self.sld_background_opacity.value()}%  •  {first_page_label}")
            self.lbl_background.setToolTip(path)
            pix = QPixmap(path)
            if not pix.isNull():
                preview = pix.scaled(118, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_background_preview.setPixmap(preview)
                self.lbl_background_preview.setText("")
                self.lbl_background_preview.setToolTip(path)
            else:
                self.lbl_background_preview.setPixmap(QPixmap())
                self.lbl_background_preview.setText("Preview\nunavailable")
                self.lbl_background_preview.setToolTip(path)
        else:
            self.lbl_background.setText("No background selected.")
            self.lbl_background.setToolTip("")
            self.lbl_background_preview.setPixmap(QPixmap())
            self.lbl_background_preview.setText("No\npreview")
            self.lbl_background_preview.setToolTip("")

    def _on_background_changed(self) -> None:
        if self.cmb_background.currentData() == "__custom__" and not self.custom_background_path:
            self.browse_background()
        self._update_background_label()

    def browse_background(self) -> None:
        start_dir = os.path.dirname(self.custom_background_path) if self.custom_background_path else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose background image",
            start_dir,
            "Images (*.png *.jpg *.jpeg *.webp);;All Files (*)",
        )
        if not path:
            if self.cmb_background.currentData() == "__custom__" and not self.custom_background_path:
                self.cmb_background.setCurrentIndex(0)
            self._update_background_label()
            return

        self.custom_background_path = path
        idx = self.cmb_background.findData("__custom__")
        if idx >= 0:
            self.cmb_background.setItemIcon(idx, self._make_background_icon(path))
            self.cmb_background.setItemText(idx, f"Custom: {os.path.basename(path)}")
            self.cmb_background.setCurrentIndex(idx)
        self._update_background_label()

    def clear_background(self) -> None:
        self.custom_background_path = None
        idx = self.cmb_background.findData("__custom__")
        if idx >= 0:
            self.cmb_background.setItemIcon(idx, QIcon())
            self.cmb_background.setItemText(idx, "Custom image…")
        self.cmb_background.setCurrentIndex(0)
        self._update_background_label()

    def add_journals(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add journal export(s)",
            "",
            "FVTT Export ZIP (*.zip);;All Files (*)",
        )
        if not paths:
            return

        errors: List[str] = []
        for path in paths:
            try:
                parsed = parse_journal(path)
                for j in _ensure_list(parsed):
                    self.journals.append(j)
            except Exception as e:
                errors.append(f"{path}\n{e}")

        self.populate_tree()

        if errors:
            QMessageBox.warning(self, "Some files failed to load", "These exports could not be parsed:\n\n" + "\n\n".join(errors))

    def populate_tree(self) -> None:
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            for j in self.journals:
                j_title = getattr(j, "title", "Journal")
                j_item = QTreeWidgetItem([j_title])
                j_item.setFlags(j_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                j_item.setCheckState(0, Qt.Checked)
                j_item.setData(0, Qt.UserRole, ("journal", j_title, None, None))
                self.tree.addTopLevelItem(j_item)

                for p in getattr(j, "pages", []) or []:
                    p_title = getattr(p, "title", "Page")
                    p_item = QTreeWidgetItem([p_title])
                    p_item.setFlags(p_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                    p_item.setCheckState(0, Qt.Checked)
                    p_item.setData(0, Qt.UserRole, ("page", j_title, p_title, None))
                    j_item.addChild(p_item)

                    for h in _extract_page_headings(p):
                        h_item = QTreeWidgetItem([h])
                        h_item.setFlags(h_item.flags() | Qt.ItemIsUserCheckable)
                        h_item.setCheckState(0, Qt.Checked)
                        h_item.setData(0, Qt.UserRole, ("heading", j_title, p_title, h))
                        p_item.addChild(h_item)

                j_item.setExpanded(True)

            self.lbl_status.setText(f"Loaded {len(self.journals)} journal(s).")
        finally:
            self.tree.blockSignals(False)

    def set_all_checks(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        self.tree.blockSignals(True)
        try:
            for i in range(self.tree.topLevelItemCount()):
                self.tree.topLevelItem(i).setCheckState(0, state)
        finally:
            self.tree.blockSignals(False)

    def _selected_top_journal_index(self) -> Optional[int]:
        item = self.tree.currentItem()
        if not item:
            return None
        while item.parent():
            item = item.parent()
        idx = self.tree.indexOfTopLevelItem(item)
        return idx if idx >= 0 else None

    def remove_selected_journal(self) -> None:
        idx = self._selected_top_journal_index()
        if idx is None:
            return
        if 0 <= idx < len(self.journals):
            self.journals.pop(idx)
        self.populate_tree()

    def _gather_selection(self) -> Selection:
        sel_items: List[Tuple[str, str, Optional[str]]] = []

        def walk(it: QTreeWidgetItem):
            data = it.data(0, Qt.UserRole)
            if data and it.checkState(0) == Qt.Checked:
                kind, j_title, p_title, heading = data
                if kind == "page":
                    sel_items.append((j_title, p_title, None))
                elif kind == "heading":
                    sel_items.append((j_title, p_title, heading))
            for k in range(it.childCount()):
                walk(it.child(k))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

        return Selection(items=sel_items)

    def generate_pdf(self) -> None:
        if not self.journals:
            QMessageBox.information(self, "Nothing loaded", "Load at least one ZIP export first.")
            return

        out_path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if not out_path:
            return
        if not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"

        title = self.journals[0].title if len(self.journals) == 1 else "FVTT Journals"
        selection = self._gather_selection()

        busy = BusyDialog(self)
        worker = BuildWorker(
            out_path,
            title,
            self.journals,
            selection,
            divider_pages=self.divider_pages,
            background_path=self._current_background_path(),
            background_mode=self._current_background_mode(),
            background_opacity=self._current_background_opacity(),
            background_first_page_only=self.chk_background_first_page_only.isChecked(),
        )

        def ok(p: str):
            busy.accept()
            QMessageBox.information(self, "PDF created", f"Saved:\n{p}")

        def fail(err: str):
            busy.accept()
            QMessageBox.critical(self, "Failed to build PDF", err)

        worker.ok.connect(ok)
        worker.fail.connect(fail)
        worker.start()
        busy.exec()

        # Keep the worker alive until the dialog closes / thread finishes.
        self._worker = worker


def main():
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
