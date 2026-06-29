"""
Template Editor Dialog — หน้าต่างลากวางช่องรูป
==================================================
หน้าต่างที่ให้ผู้ใช้เลือกกรอบรูป แล้วสามารถลากกล่อง (Slot)
เพื่อกำหนดตำแหน่งและขนาดที่รูปจะไปแปะได้ด้วยเมาส์ (Visual Editor)
เมื่อกดเซฟ จะบันทึกไฟล์ภาพและสร้างไฟล์ .json อัตโนมัติ
"""

import os
import json
import shutil
import logging
import math

from PIL import Image, ImageQt
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPixmap, QPen, QColor, QBrush, QPainter, QFont, QTransform, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsObject, QMessageBox, QListWidget, QWidget,
    QGroupBox, QSlider, QGraphicsPixmapItem
)
from chroma_key_module import remove_color_background

logger = logging.getLogger(__name__)


class TemplatePixmapItem(QGraphicsPixmapItem):
    """รูปภาพพื้นหลังที่สามารถดักจับการคลิกเพื่อดูดสีได้"""
    def __init__(self, pixmap, dialog, parent=None):
        super().__init__(pixmap, parent)
        self.dialog = dialog
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        pos = event.pos()
        x, y = int(pos.x()), int(pos.y())
        self.dialog.pick_color(x, y)
        super().mousePressEvent(event)


class ResizableRectItem(QGraphicsObject):
    """กล่องสี่เหลี่ยมที่คลิกเลือก, ลาก (Move), ยืดหดขอบ (Resize) และหมุน (Rotate) ได้"""

    def __init__(self, rect: QRectF, slot_index: int, parent=None) -> None:
        super().__init__(parent)
        self.setFlags(
            QGraphicsObject.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsObject.GraphicsItemFlag.ItemIsMovable |
            QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.slot_index = slot_index
        self.handle_size = 12
        self.rotation_handle_size = 14
        
        # จัดเก็บขนาดกว้าง/ยาว และวางตำแหน่งให้จุดกำเนิดอยู่กึ่งกลาง
        self.w = rect.width()
        self.h = rect.height()
        self.setPos(rect.center())
        
        # จุดหมุน (Origin) อยู่ที่กึ่งกลาง (0,0) เสมอ
        self.setTransformOriginPoint(0, 0)
        
        # รหัส Handle 1-8 คือขอบ, 9 คือแกนหมุน
        self.handle_cursors = {
            1: Qt.CursorShape.SizeFDiagCursor, # top-left
            2: Qt.CursorShape.SizeVerCursor,   # top
            3: Qt.CursorShape.SizeBDiagCursor, # top-right
            4: Qt.CursorShape.SizeHorCursor,   # right
            5: Qt.CursorShape.SizeFDiagCursor, # bottom-right
            6: Qt.CursorShape.SizeVerCursor,   # bottom
            7: Qt.CursorShape.SizeBDiagCursor, # bottom-left
            8: Qt.CursorShape.SizeHorCursor,   # left
            9: Qt.CursorShape.CrossCursor      # rotation handle
        }
        self.current_handle = None
        self.setAcceptHoverEvents(True)

    @property
    def rect(self) -> QRectF:
        """กล่องสี่เหลี่ยมนี้จะมีจุดศูนย์กลางอยู่ที่ (0,0) เสมอ"""
        return QRectF(-self.w/2, -self.h/2, self.w, self.h)

    def boundingRect(self) -> QRectF:
        """ขอบเขตของไอเท็ม รวมขนาดของ Handle และแกนหมุนที่ยื่นออกมาด้วย"""
        r = self.rect.adjusted(
            -self.handle_size, -self.handle_size - 40,  # เผื่อความสูงของแกนหมุน 40px
            self.handle_size, self.handle_size
        )
        return r

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """วาดกล่องสี่เหลี่ยม Handle และแกนหมุน"""
        # สีกล่อง: เขียว (ถ้าถูกเลือก) หรือ เหลือง
        color = QColor(0, 230, 118) if self.isSelected() else QColor(255, 235, 59)
        
        painter.setPen(QPen(color, 4, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 50)))
        painter.drawRect(self.rect)
        
        # วาดข้อความ (Slot # และ องศา)
        painter.setPen(QPen(color))
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        
        angle = self.rotation()
        text = f"Slot {self.slot_index}"
        if int(angle) != 0:
            text += f"\n{int(angle)}°"
        painter.drawText(self.rect, Qt.AlignmentFlag.AlignCenter, text)

        # วาดมุมจับ (Handles) และแกนหมุน ถ้าถูกเลือก
        if self.isSelected():
            painter.setPen(QPen(QColor(0, 0, 0), 2))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            
            handles = self._get_handles()
            for h_id, r in handles.items():
                if h_id == 9:
                    # วาดก้านหมุน (เส้น)
                    top_center = handles[2].center()
                    painter.drawLine(top_center, r.center())
                    # วาดวงกลมจุดหมุน
                    painter.setBrush(QBrush(QColor(0, 230, 118)))
                    painter.drawEllipse(r)
                else:
                    painter.setBrush(QBrush(QColor(255, 255, 255)))
                    painter.drawRect(r)

    def _get_handles(self) -> dict:
        """คืนค่าตำแหน่งของปุ่มดึงขอบทั้ง 8 จุด และจุดหมุนจุดที่ 9"""
        r = self.rect
        s = self.handle_size
        rs = self.rotation_handle_size
        return {
            1: QRectF(r.left() - s/2, r.top() - s/2, s, s),
            2: QRectF(r.center().x() - s/2, r.top() - s/2, s, s),
            3: QRectF(r.right() - s/2, r.top() - s/2, s, s),
            4: QRectF(r.right() - s/2, r.center().y() - s/2, s, s),
            5: QRectF(r.right() - s/2, r.bottom() - s/2, s, s),
            6: QRectF(r.center().x() - s/2, r.bottom() - s/2, s, s),
            7: QRectF(r.left() - s/2, r.bottom() - s/2, s, s),
            8: QRectF(r.left() - s/2, r.center().y() - s/2, s, s),
            9: QRectF(r.center().x() - rs/2, r.top() - 40 - rs/2, rs, rs) # Rotation handle
        }

    def hoverMoveEvent(self, event) -> None:
        """เปลี่ยนเคอร์เซอร์เมาส์เมื่อวางบน Handle"""
        if self.isSelected():
            handle = None
            for h, r in self._get_handles().items():
                if r.contains(event.pos()):
                    handle = h
                    break
            if handle:
                self.setCursor(self.handle_cursors[handle])
            else:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        """จำว่ากำลังดึง Handle อันไหนอยู่"""
        self.current_handle = None
        if self.isSelected():
            for h, r in self._get_handles().items():
                if r.contains(event.pos()):
                    self.current_handle = h
                    break
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """ปรับขนาดกล่องตามเมาส์ที่ลาก หรือหมุนตามจุดหมุน"""
        if self.current_handle == 9:
            self._interactive_rotate(event.scenePos())
        elif self.current_handle:
            self._interactive_resize(event.pos())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.current_handle = None

    def _interactive_rotate(self, scene_mouse_pos: QPointF) -> None:
        """คำนวณองศาจากจุดกึ่งกลางกล่องถึงเมาส์ โดยอิงจากพิกัดของ Scene ป้องกันปัญหาหมุนแล้วกระตุก"""
        # จุดศูนย์กลางของกล่องใน Scene คือค่า pos() ของมันเอง
        center = self.scenePos()
        dx = scene_mouse_pos.x() - center.x()
        dy = scene_mouse_pos.y() - center.y()
        angle = math.degrees(math.atan2(dy, dx)) + 90
        self.setRotation(angle)

    def _interactive_resize(self, mouse_pos: QPointF) -> None:
        """อัปเดตขนาดของกล่องและการจัดวางเมื่อมีการลากเมาส์"""
        L = -self.w / 2
        R = self.w / 2
        T = -self.h / 2
        B = self.h / 2

        if self.current_handle in (1, 7, 8): # left
            L = mouse_pos.x()
        elif self.current_handle in (3, 4, 5): # right
            R = mouse_pos.x()
            
        if self.current_handle in (1, 2, 3): # top
            T = mouse_pos.y()
        elif self.current_handle in (5, 6, 7): # bottom
            B = mouse_pos.y()
            
        new_w = R - L
        new_h = B - T
        
        # ป้องกันไม่ให้ย่อกล่องจนแบนติดกัน (Min size = 50x50)
        if new_w < 50:
            if self.current_handle in (1, 7, 8): L = R - 50
            else: R = L + 50
            new_w = 50
        if new_h < 50:
            if self.current_handle in (1, 2, 3): T = B - 50
            else: B = T + 50
            new_h = 50
            
        # จุดศูนย์กลางใหม่ภายใน Local Space เดิม
        cx = (L + R) / 2
        cy = (T + B) / 2
        
        # หาพิกัดของจุดศูนย์กลางใหม่ใน Scene Space
        new_scene_center = self.mapToScene(QPointF(cx, cy))
        
        self.prepareGeometryChange()
        self.w = new_w
        self.h = new_h
        # ย้ายกล่องไปจุดกึ่งกลางใหม่ (Scene Space) เพื่อไม่ให้ภาพกระโดดเวลา Resize
        self.setPos(new_scene_center)
        self.update()


class TemplateGraphicsView(QGraphicsView):
    """Custom View สำหรับ Zoom และ Panning"""
    zoom_changed = pyqtSignal(int)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.current_zoom = 1.0
        self._pan_start = None

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            super().wheelEvent(event)

    def zoom_in(self):
        self.scale_view(1.25)

    def zoom_out(self):
        self.scale_view(0.8)
        
    def reset_zoom(self):
        self.resetTransform()
        self.current_zoom = 1.0
        self.zoom_changed.emit(100)

    def scale_view(self, scale_factor):
        new_zoom = self.current_zoom * scale_factor
        if 0.1 <= new_zoom <= 10.0:
            self.scale(scale_factor, scale_factor)
            self.current_zoom = new_zoom
            self.zoom_changed.emit(int(self.current_zoom * 100))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            self._pan_start = event.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_start = event.pos()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self._pan_start = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TemplateEditorDialog(QDialog):
    """หน้าต่างสำหรับตั้งค่าพิกัด Slot ก่อนเพิ่ม Template"""

    def __init__(self, image_path: str, dest_dir: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self.dest_dir = dest_dir
        self.slots: list[ResizableRectItem] = []
        self.slot_counter = 0
        
        self.target_rgb = None
        self.original_image = None
        self.processed_image = None
        self.bg_item = None
        
        self.setObjectName("TemplateEditorDialog")
        # ใช้หน้าต่างแบบ Modal ทับ UI ตัวหลัก
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        
        self._init_ui()
        self._load_image()

    def _init_ui(self) -> None:
        self.setWindowTitle("Template Editor - ลากจัดเรียงช่องใส่รูป")
        self.resize(1200, 800)
        
        # ปรับแต่งสีพื้นหลังหลักให้มืดๆ
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a24;
            }
            QLabel {
                color: #A0A0C0;
                font-size: 14px;
            }
            QPushButton {
                padding: 12px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton.primary {
                background-color: #00CEC9;
                color: #000;
            }
            QPushButton.primary:hover {
                background-color: #00B5B5;
            }
            QPushButton.danger {
                background-color: #FF5252;
                color: #FFF;
            }
            QPushButton.danger:hover {
                background-color: #FF3333;
            }
            QPushButton.normal {
                background-color: #353550;
                color: #FFF;
            }
            QPushButton.normal:hover {
                background-color: #404060;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # ---------- Left Panel (Tools) ----------
        left_panel = QWidget()
        left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("🖼 เครื่องมือจัด Layout")
        font_title = QFont()
        font_title.setPointSize(18)
        font_title.setBold(True)
        title.setFont(font_title)
        title.setStyleSheet("color: white;")
        left_layout.addWidget(title)
        
        hint = QLabel("• ลากกล่องสี่เหลี่ยมเพื่อย้ายตำแหน่ง\n• ดึงขอบเพื่อยืดหดขนาด\n• ลากจุดวงกลมด้านบนเพื่อหมุน (Rotate)")
        left_layout.addWidget(hint)
        left_layout.addSpacing(20)

        # ปุ่มเพิ่ม/ลบ
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("➕ เพิ่ม Slot")
        self.btn_add.setProperty("cssClass", "normal")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._add_slot)
        btn_layout.addWidget(self.btn_add)

        self.btn_del = QPushButton("🗑 ลบ Slot")
        self.btn_del.setProperty("cssClass", "danger")
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.clicked.connect(self._delete_slot)
        btn_layout.addWidget(self.btn_del)
        left_layout.addLayout(btn_layout)

        self.list_slots = QListWidget()
        self.list_slots.setStyleSheet("background-color: #242438; color: white; border: none; border-radius: 8px; padding: 8px; font-size: 16px;")
        self.list_slots.currentRowChanged.connect(self._on_list_item_selected)
        left_layout.addWidget(self.list_slots)
        
        # ---------- Chroma Key Panel ----------
        grp_chroma = QGroupBox("🧪 ลบพื้นหลังสี (Chroma Key)")
        grp_chroma.setStyleSheet("QGroupBox { color: white; font-weight: bold; } QLabel { color: #A0A0C0; }")
        chroma_layout = QVBoxLayout(grp_chroma)
        
        color_row = QHBoxLayout()
        color_label = QLabel("สีที่เลือก:")
        self.lbl_color_indicator = QLabel()
        self.lbl_color_indicator.setFixedSize(30, 30)
        self.lbl_color_indicator.setStyleSheet("background-color: transparent; border: 1px solid white;")
        self.lbl_color_rgb = QLabel("(คลิกที่รูปเพื่อดูดสี)")
        color_row.addWidget(color_label)
        color_row.addWidget(self.lbl_color_indicator)
        color_row.addWidget(self.lbl_color_rgb, stretch=1)
        chroma_layout.addLayout(color_row)
        
        tol_layout = QHBoxLayout()
        tol_label = QLabel("Tolerance:")
        tol_label.setFixedWidth(70)
        self.slider_tolerance = QSlider(Qt.Orientation.Horizontal)
        self.slider_tolerance.setRange(0, 255)
        self.slider_tolerance.setValue(30)
        self.lbl_tol_val = QLabel("30")
        self.slider_tolerance.valueChanged.connect(lambda v: self.lbl_tol_val.setText(str(v)))
        tol_layout.addWidget(tol_label)
        tol_layout.addWidget(self.slider_tolerance)
        tol_layout.addWidget(self.lbl_tol_val)
        chroma_layout.addLayout(tol_layout)
        
        edge_layout = QHBoxLayout()
        edge_label = QLabel("Edge Crop:")
        edge_label.setFixedWidth(70)
        self.slider_edge = QSlider(Qt.Orientation.Horizontal)
        self.slider_edge.setRange(0, 10)
        self.slider_edge.setValue(0)
        self.lbl_edge_val = QLabel("0")
        self.slider_edge.valueChanged.connect(lambda v: self.lbl_edge_val.setText(str(v)))
        edge_layout.addWidget(edge_label)
        edge_layout.addWidget(self.slider_edge)
        edge_layout.addWidget(self.lbl_edge_val)
        chroma_layout.addLayout(edge_layout)
        
        self.btn_preview = QPushButton("👀 พรีวิวตัดพื้นหลัง")
        self.btn_preview.setProperty("cssClass", "normal")
        self.btn_preview.clicked.connect(self._preview_chroma_key)
        chroma_layout.addWidget(self.btn_preview)
        
        left_layout.addWidget(grp_chroma)
        left_layout.addSpacing(20)
        
        # Zoom Controls
        zoom_layout = QHBoxLayout()
        zoom_label = QLabel("🔍 ซูม:")
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setStyleSheet("color: white; font-weight: bold; font-size: 16px;")
        
        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedSize(30, 30)
        btn_zoom_out.setStyleSheet("background-color: #353550; color: white; border-radius: 4px; padding: 0;")
        btn_zoom_out.clicked.connect(lambda: self.view.zoom_out())
        
        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(30, 30)
        btn_zoom_in.setStyleSheet("background-color: #353550; color: white; border-radius: 4px; padding: 0;")
        btn_zoom_in.clicked.connect(lambda: self.view.zoom_in())
        
        zoom_layout.addWidget(zoom_label)
        zoom_layout.addWidget(btn_zoom_out)
        zoom_layout.addWidget(self.lbl_zoom)
        zoom_layout.addWidget(btn_zoom_in)
        zoom_layout.addStretch()
        left_layout.addLayout(zoom_layout)
        left_layout.addSpacing(20)

        self.btn_save = QPushButton("💾 บันทึก Template")
        self.btn_save.setProperty("cssClass", "primary")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_template)
        left_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("✖ ยกเลิก")
        self.btn_cancel.setProperty("cssClass", "danger")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        left_layout.addWidget(self.btn_cancel)

        layout.addWidget(left_panel)

        # ---------- Right Panel (Canvas) ----------
        self.scene = QGraphicsScene()
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        
        self.view = TemplateGraphicsView(self.scene)
        self.view.zoom_changed.connect(lambda p: self.lbl_zoom.setText(f"{p}%"))
        
        # Shortcuts for Zoom
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self.view.zoom_in)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.view.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.view.zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self.view.reset_zoom)
        
        # Checkerboard background
        checker_size = 15
        bg_pixmap = QPixmap(checker_size * 2, checker_size * 2)
        bg_pixmap.fill(Qt.GlobalColor.white)
        painter = QPainter(bg_pixmap)
        painter.fillRect(0, 0, checker_size, checker_size, QColor(200, 200, 200))
        painter.fillRect(checker_size, checker_size, checker_size, checker_size, QColor(200, 200, 200))
        painter.end()
        self.view.setBackgroundBrush(QBrush(bg_pixmap))
        
        layout.addWidget(self.view, stretch=1)

    def _load_image(self) -> None:
        """โหลดรูปภาพ Template มาเป็นพื้นหลังของ Canvas และโหลดพิกัดเดิมถ้ามี"""
        try:
            self.original_image = Image.open(self.image_path).convert("RGBA")
            self.processed_image = self.original_image.copy()
            self._update_pixmap()
        except Exception as e:
            logger.error("โหลดรูปภาพไม่สำเร็จ: %s", e)
            return
        
        # กำหนดขนาด Scene ให้เท่ากับภาพจริงเป๊ะๆ เพื่อให้พิกัดตรงเวลาเซฟ
        self.scene.setSceneRect(QRectF(self.pixmap.rect()))
        
        # ตั้งค่า Zoom เริ่มต้นที่ 100%
        self.view.reset_zoom()

        # ตรวจสอบว่ามีไฟล์ JSON เดิมอยู่หรือไม่ (กรณี Edit)
        basename, _ = os.path.splitext(self.image_path)
        json_path = basename + ".json"
        
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                
                for slot in config.get("slots", []):
                    self.slot_counter += 1
                    x = slot.get("x", 0)
                    y = slot.get("y", 0)
                    w = slot.get("width", 400)
                    h = slot.get("height", 300)
                    angle = slot.get("angle", 0)
                    
                    # x, y ที่เก็บไว้คือมุมบนซ้าย (ตอนยังไม่หมุน)
                    # สร้าง rect ด้วยพิกัดนี้ แล้ว ResizableRectItem จะนำ rect.center() ไปใช้เป็น pos()
                    rect = QRectF(x, y, w, h)
                    item = ResizableRectItem(rect, self.slot_counter)
                    item.setRotation(angle)
                    
                    self.scene.addItem(item)
                    self.slots.append(item)
                    self.list_slots.addItem(f"📷 Slot {self.slot_counter}")
                    
            except Exception as e:
                logger.error("โหลดไฟล์ JSON เดิมไม่สำเร็จ: %s", e)

    def _add_slot(self) -> None:
        """เพิ่มกล่อง (Slot) ใหม่ลงบนจอ"""
        # วางกล่องขนาดเริ่มต้นไว้ตรงกลางๆ
        cx = self.pixmap.width() / 2 - 200
        cy = self.pixmap.height() / 2 - 150
        rect = QRectF(cx, cy, 400, 300)
        
        self.slot_counter += 1
        item = ResizableRectItem(rect, self.slot_counter)
        
        self.scene.addItem(item)
        self.slots.append(item)
        self.list_slots.addItem(f"📷 Slot {self.slot_counter}")
        
        # เลือกกล่องให้ทันที
        self.scene.clearSelection()
        item.setSelected(True)
        
    def _delete_slot(self) -> None:
        """ลบกล่อง (Slot) ที่ถูกเลือกอยู่"""
        selected_items = self.scene.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาคลิกเลือก Slot ที่ต้องการลบก่อน")
            return
            
        item = selected_items[0]
        if item in self.slots:
            idx = self.slots.index(item)
            self.scene.removeItem(item)
            self.slots.pop(idx)
            self.list_slots.takeItem(idx)

    def _on_scene_selection_changed(self) -> None:
        """เมื่อคลิกเลือกของใน scene ให้ไฮไลต์รายการใน list ด้วย"""
        selected_items = self.scene.selectedItems()
        if selected_items and selected_items[0] in self.slots:
            idx = self.slots.index(selected_items[0])
            self.list_slots.setCurrentRow(idx)
            
    def _on_list_item_selected(self, row: int) -> None:
        """เมื่อจิ้มรายการใน list ให้ไฮไลต์กล่องใน scene ด้วย"""
        if row >= 0 and row < len(self.slots):
            self.scene.clearSelection()
            self.slots[row].setSelected(True)

    def _update_pixmap(self):
        """อัปเดต QPixmap จาก self.processed_image"""
        qimage = ImageQt.ImageQt(self.processed_image)
        self.pixmap = QPixmap.fromImage(qimage)
        
        if self.bg_item:
            self.scene.removeItem(self.bg_item)
            
        self.bg_item = TemplatePixmapItem(self.pixmap, self)
        # ตรวจสอบว่ารูปถูกวางไว้ layer ต่ำสุด
        self.bg_item.setZValue(-1)
        self.scene.addItem(self.bg_item)

    def pick_color(self, x: int, y: int):
        """ดูดสีจากตำแหน่ง x, y ของรูปต้นฉบับ"""
        if self.original_image is None:
            return
            
        # เช็คขอบเขต
        if 0 <= x < self.original_image.width and 0 <= y < self.original_image.height:
            r, g, b, a = self.original_image.getpixel((x, y))
            self.target_rgb = (r, g, b)
            
            # อัปเดต UI
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            self.lbl_color_indicator.setStyleSheet(f"background-color: {hex_color}; border: 1px solid white;")
            self.lbl_color_rgb.setText(f"RGB: ({r}, {g}, {b})")

    def _preview_chroma_key(self):
        """ประมวลผลลบพื้นหลังชั่วคราว"""
        if not self.target_rgb:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาคลิกเลือกสีพื้นหลังที่ต้องการลบก่อน")
            return
            
        self.btn_preview.setText("กำลังประมวลผล...")
        self.btn_preview.setEnabled(False)
        self.repaint() # บังคับให้ UI อัปเดต
        
        try:
            tol = self.slider_tolerance.value()
            edge = self.slider_edge.value()
            
            # ลบพื้นหลังและอัปเดตบนหน้าจอ
            self.processed_image = remove_color_background(
                self.original_image, 
                self.target_rgb, 
                tol, 
                edge
            )
            self._update_pixmap()
            
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"ประมวลผลล้มเหลว: {e}")
        finally:
            self.btn_preview.setText("👀 พรีวิวตัดพื้นหลัง")
            self.btn_preview.setEnabled(True)

    def _save_template(self) -> None:
        """ดึงพิกัดกล่องทั้งหมด เซฟเป็น JSON และคัดลอกไฟล์รูปเข้าโปรเจกต์"""
        if not self.slots:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเพิ่มช่องรูป (Slot) อย่างน้อย 1 ช่อง")
            return

        os.makedirs(self.dest_dir, exist_ok=True)
        filename = os.path.basename(self.image_path)
        basename, _ = os.path.splitext(filename)
        
        dest_img_path = os.path.join(self.dest_dir, filename)
        dest_json_path = os.path.join(self.dest_dir, f"{basename}.json")

        try:
            # 1. คัดลอก/บันทึกภาพไปยัง assets/templates/
            if self.processed_image:
                # ถ้ามีการตัดสีแล้ว ให้เซฟภาพจาก processed_image เป็น PNG (มีช่องโหว่โปร่งใส)
                self.processed_image.save(dest_img_path, format="PNG")
            else:
                if self.image_path != dest_img_path:
                    shutil.copy2(self.image_path, dest_img_path)

            # 2. คำนวณพิกัดแต่ละกล่อง
            slots_data = []
            for item in self.slots:
                # พิกัด pos() คือจุดศูนย์กลางใน Scene Space
                # มุมบนซ้ายของกล่องที่ยังไม่หมุนคือ x - w/2 และ y - h/2
                cx = item.pos().x()
                cy = item.pos().y()
                w = int(item.w)
                h = int(item.h)
                
                # พิกัด x, y มุมบนซ้าย
                x = int(cx - w / 2)
                y = int(cy - h / 2)
                angle = float(item.rotation())
                
                slots_data.append({
                    "x": x, 
                    "y": y, 
                    "width": w, 
                    "height": h,
                    "angle": round(angle, 2)
                })

            # 3. เซฟเป็นไฟล์ .json
            config = {
                "total_photos": len(self.slots),
                "slots": slots_data
            }

            with open(dest_json_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)

            QMessageBox.information(self, "สำเร็จ", f"บันทึก Template สำเร็จ!\nเพิ่ม {len(self.slots)} ช่องเรียบร้อยแล้ว")
            self.accept()
            
        except Exception as e:
            logger.error("เกิดข้อผิดพลาดในการเซฟ Template: %s", e)
            QMessageBox.critical(self, "ข้อผิดพลาด", str(e))
