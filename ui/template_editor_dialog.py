"""
Template Editor Dialog — หน้าต่างลากวางช่องรูป
==================================================
หน้าต่างที่ให้ผู้ใช้เลือกกรอบรูป แล้วสามารถลากกล่อง (Slot)
เพื่อกำหนดตำแหน่งและขนาดที่รูปจะไปแปะได้ด้วยเมาส์ (Visual Editor)
เมื่อกดเซฟ จะบันทึกไฟล์ภาพและสร้างไฟล์ .json อัตโนมัติ
"""

import os
import json
import copy
import shutil
import logging
import math

from PIL import Image, ImageQt
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QSize
from PyQt6 import sip
from PyQt6.QtGui import QPixmap, QPen, QColor, QBrush, QPainter, QFont, QShortcut, QKeySequence, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsObject, QMessageBox, QListWidget, QWidget,
    QGroupBox, QSlider, QGraphicsPixmapItem, QToolButton, QGraphicsRectItem, QListWidgetItem,
    QMenu, QStyledItemDelegate, QStyle
)
from chroma_key_module import apply_multi_layer_chroma
from ui.styles import (
    PRIMARY, PRIMARY_HOVER, PRIMARY_PRESSED,
    BG_DARK, BG_CARD, BG_INPUT, BG_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER, DANGER
)

def _make_tinted_icon(icon_path: str, color: QColor = QColor("white")) -> QIcon:
    """แปลงไอคอนทึบแสงสีดำเป็นสีที่ต้องการ (ค่าเริ่มต้นสีขาว)"""
    pixmap = QPixmap(icon_path)
    if pixmap.isNull():
        return QIcon()
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return QIcon(pixmap)

def _make_cross_icon(size: int = 14, color: QColor = QColor("white")) -> QIcon:
    """สร้างไอคอนกากบาทสีขาวคมชัด ป้องกันปัญหา Windows Emoji แสดงผลเป็นสีแดงกลืนกับปุ่ม"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    pad = 2
    painter.drawLine(pad, pad, size - pad, size - pad)
    painter.drawLine(size - pad, pad, pad, size - pad)
    painter.end()
    return QIcon(pixmap)

logger = logging.getLogger(__name__)


# ─────────────────── Tool State Constants ───────────────────
TOOL_NONE = 'none'
TOOL_PICKER = 'picker'
TOOL_ZONE = 'zone'

# ─────────────────── Color Palette for Linked Slots ───────────────────
# สีสำหรับแต่ละ photo_index group (ใช้วนซ้ำถ้าเกิน)
SLOT_GROUP_COLORS = [
    QColor(0, 230, 118),    # เขียว
    QColor(255, 107, 107),  # แดง
    QColor(100, 181, 246),  # ฟ้า
    QColor(255, 213, 79),   # เหลือง
    QColor(186, 104, 200),  # ม่วง
    QColor(255, 138, 101),  # ส้ม
    QColor(77, 208, 225),   # เทอร์ควอยซ์
    QColor(240, 98, 146),   # ชมพู
    QColor(129, 199, 132),  # เขียวอ่อน
    QColor(149, 117, 205),  # ม่วงอ่อน
]


class SlotListDelegate(QStyledItemDelegate):
    """Delegate สำหรับวาดข้อความใน list_slots ให้ใช้สีตาม ForegroundRole เสมอ (ไม่โดน QSS ทับ)"""
    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), 36))

    def paint(self, painter: QPainter, option, index) -> None:
        opt = option
        self.initStyleOption(opt, index)
        # ล้าง text ออก เพื่อให้ QStyle วาดเฉพาะพื้นหลัง/กรอบ/สถานะ hover และ selected
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
            
        # วาดข้อความด้วยตัวเองโดยดึงสีจาก ForegroundRole
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text:
            painter.save()
            fg = index.data(Qt.ItemDataRole.ForegroundRole)
            if fg and hasattr(fg, 'color'):
                painter.setPen(fg.color())
            elif isinstance(fg, QColor):
                painter.setPen(fg)
            else:
                painter.setPen(QColor(TEXT_PRIMARY))
                
            font = index.data(Qt.ItemDataRole.FontRole)
            if font and isinstance(font, QFont):
                painter.setFont(font)
                
            rect = option.rect.adjusted(10, 0, -10, 0)
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(text))
            painter.restore()


class TemplatePixmapItem(QGraphicsPixmapItem):
    """รูปภาพพื้นหลังที่สามารถดักจับการคลิกเพื่อดูดสีและวาดโซนได้"""
    def __init__(self, pixmap, dialog, parent=None):
        super().__init__(pixmap, parent)
        self.dialog = dialog
        self.setAcceptHoverEvents(True)
        # ไม่ set CrossCursor ตลอดเวลาแล้ว — ใช้ tool state แทน
        self._zone_start = None  # จุดเริ่มต้นสำหรับวาดโซน

    def hoverMoveEvent(self, event):
        """เปลี่ยน cursor ตาม tool state"""
        tool = self.dialog.current_tool
        if tool == TOOL_PICKER:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool == TOOL_ZONE:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        tool = self.dialog.current_tool
        if tool == TOOL_PICKER:
            pos = event.pos()
            x, y = int(pos.x()), int(pos.y())
            self.dialog.pick_color(x, y)
            event.accept()
            return
        elif tool == TOOL_ZONE:
            self._zone_start = event.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        tool = self.dialog.current_tool
        if tool == TOOL_ZONE and self._zone_start is not None:
            # อัปเดต rubber band preview
            self.dialog._update_zone_rubber_band(self._zone_start, event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        tool = self.dialog.current_tool
        if tool == TOOL_ZONE and self._zone_start is not None:
            end_pos = event.pos()
            self.dialog._finish_zone_draw(self._zone_start, end_pos)
            self._zone_start = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ResizableRectItem(QGraphicsObject):
    """กล่องสี่เหลี่ยมที่คลิกเลือก, ลาก (Move), ยืดหดขอบ (Resize) และหมุน (Rotate) ได้"""
    # Signal แจ้งเตือนเมื่อมีการเปลี่ยนตำแหน่ง/ขนาด/หมุนเสร็จ
    geometry_changed = pyqtSignal()
    # Signal แจ้งเมื่อต้องการ Link/Unlink (ส่ง item กับ target_photo_index)
    link_requested = pyqtSignal(object, int)   # (self, target_photo_index)
    unlink_requested = pyqtSignal(object)       # (self,)

    def __init__(self, rect: QRectF, slot_index: int, photo_index: int = -1, parent=None) -> None:
        super().__init__(parent)
        self.setFlags(
            QGraphicsObject.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsObject.GraphicsItemFlag.ItemIsMovable |
            QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.slot_index = slot_index
        self.photo_index: int = photo_index if photo_index >= 0 else slot_index - 1
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
        
        # เก็บ reference ไปยัง dialog เพื่อสร้าง context menu
        self._dialog = None

    def get_group_color(self) -> QColor:
        """คืนสีตาม photo_index group"""
        return SLOT_GROUP_COLORS[self.photo_index % len(SLOT_GROUP_COLORS)]

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
        # สีกล่อง: ใช้สี group ตาม photo_index
        group_color = self.get_group_color()
        if self.isSelected():
            # ถ้าถูกเลือก → สว่างขึ้น
            color = group_color.lighter(130)
        else:
            color = group_color
        
        # ── Dummy Preview Mode: วาดรูป dummy.jpg ลงใน Slot (crop-to-fill) ──
        show_dummy = False
        if self._dialog and getattr(self._dialog, '_preview_dummy', False):
            dummy_pm = getattr(self._dialog, '_dummy_pixmap', None)
            if dummy_pm and not dummy_pm.isNull():
                show_dummy = True
                r = self.rect
                slot_w, slot_h = r.width(), r.height()
                img_w, img_h = dummy_pm.width(), dummy_pm.height()
                
                # คำนวณ crop-to-fill (cover mode)
                scale = max(slot_w / img_w, slot_h / img_h)
                src_w = slot_w / scale
                src_h = slot_h / scale
                src_x = (img_w - src_w) / 2
                src_y = (img_h - src_h) / 2
                src_rect = QRectF(src_x, src_y, src_w, src_h)
                
                painter.setClipRect(r)
                painter.drawPixmap(r, dummy_pm, src_rect)
                painter.setClipping(False)
        
        painter.setPen(QPen(color, 4, Qt.PenStyle.DashLine))
        if not show_dummy:
            painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 50)))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect)
        
        # วาดข้อความ (Slot # + 📸 photo_index + องศา)
        painter.setPen(QPen(color))
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        
        angle = self.rotation()
        text = f"Slot {self.slot_index}\nช็อต {self.photo_index + 1}"
        if int(angle) != 0:
            text += f"\n{int(angle)}°"
        
        # แสดงไอคอน 🔗 ถ้ามี slot อื่นที่มี photo_index เดียวกัน
        if self._dialog:
            linked_count = sum(1 for s in self._dialog.slots if s.photo_index == self.photo_index)
            if linked_count > 1:
                text += f"\n🔗 x{linked_count}"
        
        # วาดข้อความพร้อม drop shadow เพื่อให้อ่านได้ชัดบน dummy image
        if show_dummy:
            painter.setPen(QPen(QColor(0, 0, 0, 180)))
            shadow_offset = 2
            shadow_rect = QRectF(self.rect.x() + shadow_offset, self.rect.y() + shadow_offset,
                                 self.rect.width(), self.rect.height())
            painter.drawText(shadow_rect, Qt.AlignmentFlag.AlignCenter, text)
            painter.setPen(QPen(color))
        
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

    def contextMenuEvent(self, event) -> None:
        """แสดง Context Menu สำหรับ Slot (คัดลอก, ทำซ้ำ, ลบ, Link/Unlink)"""
        if not self._dialog:
            return
        
        # เลือก slot นี้ทันทีเมื่อคลิกขวา
        if self.scene():
            self.scene().clearSelection()
        self.setSelected(True)
        if self in self._dialog.slots:
            idx = self._dialog.slots.index(self)
            self._dialog.list_slots.setCurrentRow(idx)
        
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 4px;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {PRIMARY};
                color: {TEXT_PRIMARY};
            }}
            QMenu::item:disabled {{
                color: {TEXT_MUTED};
            }}
            QMenu::separator {{
                height: 1px;
                background: {BORDER};
                margin: 4px 8px;
            }}
        """)
        
        # ─── Copy / Duplicate / Delete ───
        copy_action = menu.addAction("คัดลอก (Ctrl+C)")
        copy_action.triggered.connect(self._dialog.copy_selected_slot)

        dup_action = menu.addAction("ทำซ้ำ (Ctrl+D)")
        dup_action.triggered.connect(self._dialog.duplicate_selected_slot)

        del_action = menu.addAction("ลบ")
        del_action.triggered.connect(self._dialog._delete_slot)

        menu.addSeparator()

        # ─── Submenu: เชื่อมกับ Slot อื่น ───
        link_menu = menu.addMenu("เชื่อมกับ Slot อื่น...")
        link_menu.setStyleSheet(menu.styleSheet())
        
        has_other_slots = False
        for other_slot in self._dialog.slots:
            if other_slot is self:
                continue
            has_other_slots = True
            linked_text = " (linked)" if other_slot.photo_index == self.photo_index else ""
            action = link_menu.addAction(
                f"📷 Slot {other_slot.slot_index} [ช็อต {other_slot.photo_index + 1}]{linked_text}"
            )
            target_pi = other_slot.photo_index
            action.triggered.connect(lambda checked, pi=target_pi: self.link_requested.emit(self, pi))
        
        if not has_other_slots:
            link_menu.setEnabled(False)

        # ─── Unlink ───
        # ตรวจว่า Slot นี้ linked กับใครอยู่ไหม
        linked_slots = [s for s in self._dialog.slots if s.photo_index == self.photo_index and s is not self]
        if linked_slots:
            linked_names = ", ".join(f"Slot {s.slot_index}" for s in linked_slots)
            unlink_action = menu.addAction(f"ตัดการเชื่อม (Unlink จาก {linked_names})")
            unlink_action.triggered.connect(lambda: self.unlink_requested.emit(self))
        
        menu.addSeparator()
        
        # ─── Info ───
        info_text = f"ช็อต {self.photo_index + 1} (Photo Index: {self.photo_index})"
        info_action = menu.addAction(info_text)
        info_action.setEnabled(False)
        
        menu.exec(event.screenPos())

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
        had_handle = self.current_handle is not None
        self.current_handle = None
        # แจ้ง dialog ว่าเปลี่ยนตำแหน่ง/ขนาด/หมุนเสร็จแล้ว
        if had_handle or event.button() == Qt.MouseButton.LeftButton:
            self.geometry_changed.emit()

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
    """Custom View สำหรับ Zoom, Panning และ Context Menu ของ Canvas"""
    zoom_changed = pyqtSignal(int)

    def __init__(self, scene, dialog=None, parent=None):
        super().__init__(scene, parent)
        self.dialog = dialog
        self._clipboard_slot_data = None
        self.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.current_zoom = 1.0
        self._pan_start = None

    @property
    def clipboard_slot_data(self):
        if self.dialog:
            return getattr(self.dialog, "clipboard_slot_data", None)
        return self._clipboard_slot_data

    @clipboard_slot_data.setter
    def clipboard_slot_data(self, val):
        if self.dialog:
            self.dialog.clipboard_slot_data = val
        self._clipboard_slot_data = val

    def contextMenuEvent(self, event):
        """แสดง Context Menu เมื่อคลิกขวาบนพื้นที่ว่างของ Scene/Canvas"""
        # ตรวจสอบว่าคลิกบน ResizableRectItem หรือไม่ ถ้าใช่ให้ส่งต่อให้ item นั้น
        scene_pos = self.mapToScene(event.pos())
        items = self.scene().items(scene_pos)
        for it in items:
            curr = it
            while curr:
                if isinstance(curr, ResizableRectItem):
                    super().contextMenuEvent(event)
                    return
                curr = curr.parentItem()

        if not self.dialog:
            super().contextMenuEvent(event)
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 4px;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {PRIMARY};
                color: {TEXT_PRIMARY};
            }}
            QMenu::item:disabled {{
                color: {TEXT_MUTED};
            }}
            QMenu::separator {{
                height: 1px;
                background: {BORDER};
                margin: 4px 8px;
            }}
        """)

        paste_action = menu.addAction("วาง (Ctrl+V)")
        has_clipboard = getattr(self.dialog, "clipboard_slot_data", None) is not None
        paste_action.setEnabled(has_clipboard)
        paste_action.triggered.connect(lambda: self.dialog.paste_slot(target_pos=scene_pos))

        menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        # ให้ Dialog และ QShortcut ระดับหน้าต่างเป็นผู้จัดการคีย์ลัด Ctrl+C, Ctrl+V, Ctrl+D, Delete
        # เพื่อป้องกันการเรียกฟังก์ชันซ้ำซ้อน (Double Execution) และให้เคารพการ Focus ในช่องข้อความ
        super().keyPressEvent(event)

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
        self.clipboard_slot_data: dict | None = None  # In-Memory Clipboard สำหรับ Copy/Paste Slot
        
        self.target_rgb = None
        self.original_image = None
        self.processed_image = None
        self.bg_item = None
        
        # ─── Tool State ───
        self.current_tool = TOOL_NONE
        
        # ─── Dummy Preview Mode ───
        self._preview_dummy = False
        self._dummy_pixmap: QPixmap | None = None
        self._load_dummy_pixmap()
        
        # ─── Chroma Key Layer System ───
        self.chroma_layers: list[dict] = []
        self._active_layer_index = -1  # index ของ layer ที่กำลัง active
        self._rubber_band_item: QGraphicsRectItem | None = None  # กรอบ preview ขณะลาก
        self._updating_sliders = False  # ป้องกัน recursive signal
        
        # ─── Undo/Redo History ───
        self._history: list[dict] = []   # stack เก็บ state snapshots
        self._history_index = -1         # ตำแหน่งปัจจุบันใน history
        self._restoring_state = False    # ป้องกัน recursive save ขณะ restore
        self._max_history = 50           # จำกัดจำนวน history สูงสุด
        
        self.setObjectName("TemplateEditorDialog")
        # ใช้หน้าต่างแบบ Modal ทับ UI ตัวหลัก
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        
        self._init_ui()
        self._load_image()

    def _init_ui(self) -> None:
        self.setWindowTitle("Template Editor - ลากจัดเรียงช่องใส่รูป")
        self.resize(1200, 800)
        
        # ปรับแต่งสีพื้นหลังหลักและ Widgets ให้ตรงกับธีมส้ม/ดำ/เทา
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_DARK};
                color: {TEXT_PRIMARY};
                font-family: "Google Sans", "Segoe UI", sans-serif;
            }}
            QLabel {{
                color: {TEXT_PRIMARY};
                font-size: 14px;
            }}
            QPushButton {{
                background-color: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {PRIMARY_PRESSED};
            }}
            QPushButton[cssClass="primary"], QPushButton.primary {{
                background-color: {PRIMARY};
                color: {TEXT_PRIMARY};
                border: none;
            }}
            QPushButton[cssClass="primary"]:hover, QPushButton.primary:hover {{
                background-color: {PRIMARY_HOVER};
            }}
            QPushButton[cssClass="primary"]:pressed, QPushButton.primary:pressed {{
                background-color: {PRIMARY_PRESSED};
            }}
            QPushButton[cssClass="danger"], QPushButton.danger {{
                background-color: {DANGER};
                color: {TEXT_PRIMARY};
                border: none;
            }}
            QPushButton[cssClass="danger"]:hover, QPushButton.danger:hover {{
                background-color: #DC2626;
            }}
            QPushButton[cssClass="normal"], QPushButton.normal {{
                background-color: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
            }}
            QPushButton[cssClass="normal"]:hover, QPushButton.normal:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
            QToolButton {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 8px;
                font-weight: bold;
                font-size: 13px;
            }}
            QToolButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
            QToolButton:checked {{
                background-color: {PRIMARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {PRIMARY_HOVER};
            }}
            QToolButton:disabled {{
                background-color: {BG_DARK};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
            }}
            QGroupBox {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 10px;
                margin-top: 14px;
                padding: 16px 12px 12px 12px;
                font-size: 14px;
                font-weight: 700;
                color: {PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
                background-color: {BG_CARD};
                border-radius: 4px;
                color: {PRIMARY};
            }}
            QSlider {{
                min-height: 28px;
                max-height: 28px;
                background: transparent;
                padding-left: 4px;
                padding-right: 4px;
            }}
            QSlider::groove:horizontal {{
                height: 8px;
                background: {BG_INPUT};
                border: 1px solid {BORDER};
                border-radius: 4px;
            }}
            QSlider::sub-page:horizontal {{
                background: {PRIMARY};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #FFFFFF;
                border: 2px solid {PRIMARY};
                width: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #FFFFFF;
                border: 2px solid {PRIMARY_HOVER};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # ---------- Left Panel (Tools) ----------
        left_panel = QWidget()
        left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("เครื่องมือจัด Layout")
        font_title = QFont()
        font_title.setPointSize(18)
        font_title.setBold(True)
        title.setFont(font_title)
        title.setStyleSheet(f"color: {TEXT_PRIMARY};")
        left_layout.addWidget(title)
        
        hint = QLabel("• ลากกล่องสี่เหลี่ยมเพื่อย้ายตำแหน่ง\n• ดึงขอบเพื่อยืดหดขนาด\n• ลากจุดวงกลมด้านบนเพื่อหมุน (Rotate)")
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        left_layout.addWidget(hint)
        left_layout.addSpacing(15)

        # ปุ่มเพิ่ม/ลบ
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("เพิ่ม Slot")
        self.btn_add.setProperty("cssClass", "normal")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._add_slot)
        btn_layout.addWidget(self.btn_add)

        self.btn_del = QPushButton("ลบ Slot")
        self.btn_del.setProperty("cssClass", "danger")
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.clicked.connect(self._delete_slot)
        btn_layout.addWidget(self.btn_del)
        left_layout.addLayout(btn_layout)

        self.list_slots = QListWidget()
        self.list_slots.setItemDelegate(SlotListDelegate(self.list_slots))
        self.list_slots.setStyleSheet(f"""
            QListWidget {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 4px;
                font-size: 14px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-radius: 6px;
            }}
            QListWidget::item:hover {{
                background-color: {BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {BG_HOVER};
                border: 1px solid {PRIMARY};
            }}
        """)
        self.list_slots.currentRowChanged.connect(self._on_list_item_selected)
        left_layout.addWidget(self.list_slots)
        
        # ---------- Chroma Key Panel ----------
        grp_chroma = QGroupBox("ลบพื้นหลังสี (Chroma Key)")
        grp_chroma.setStyleSheet(f"QGroupBox {{ color: {PRIMARY}; font-weight: bold; }} QLabel {{ color: {TEXT_SECONDARY}; }}")
        chroma_layout = QVBoxLayout(grp_chroma)
        
        # ── ปุ่มเครื่องมือ ──
        tools_row = QHBoxLayout()
        
        # ปุ่ม Color Picker
        self.btn_tool_picker = QToolButton()
        self.btn_tool_picker.setCheckable(True)
        self.btn_tool_picker.setToolTip("เครื่องมือดูดสี (Color Picker)")
        # โหลด icon จากไฟล์และแปลงเป็นสีขาว
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image", "color-picker.png")
        if os.path.exists(icon_path):
            self.btn_tool_picker.setIcon(_make_tinted_icon(icon_path, QColor("white")))
            self.btn_tool_picker.setIconSize(self.btn_tool_picker.sizeHint())
        else:
            self.btn_tool_picker.setText("🎨")
        self.btn_tool_picker.setFixedSize(44, 44)
        self.btn_tool_picker.setStyleSheet(f"""
            QToolButton {{
                padding: 6px;
                border-radius: 6px;
                background-color: {BG_INPUT};
                border: 1px solid {BORDER};
            }}
            QToolButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
            QToolButton:checked {{
                background-color: {PRIMARY};
                border: 1px solid {PRIMARY_HOVER};
            }}
        """)
        self.btn_tool_picker.clicked.connect(self._on_tool_picker_clicked)
        tools_row.addWidget(self.btn_tool_picker)
        
        # ปุ่ม Draw Zone
        self.btn_tool_zone = QToolButton()
        self.btn_tool_zone.setCheckable(True)
        self.btn_tool_zone.setText("วาดโซน")
        self.btn_tool_zone.setToolTip("วาดพื้นที่ลบสี (Draw Zone)")
        self.btn_tool_zone.setFixedHeight(44)
        self.btn_tool_zone.setStyleSheet(f"""
            QToolButton {{
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
            }}
            QToolButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
            QToolButton:checked {{
                background-color: {PRIMARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {PRIMARY_HOVER};
            }}
        """)
        self.btn_tool_zone.clicked.connect(self._on_tool_zone_clicked)
        tools_row.addWidget(self.btn_tool_zone)
        
        # ปุ่ม Reset
        self.btn_chroma_reset = QToolButton()
        self.btn_chroma_reset.setText("ล้างค่า")
        self.btn_chroma_reset.setToolTip("ล้างการตั้งค่าลบสีทั้งหมด")
        self.btn_chroma_reset.setFixedHeight(44)
        self.btn_chroma_reset.setStyleSheet(f"""
            QToolButton {{
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                background-color: {DANGER};
                color: {TEXT_PRIMARY};
                border: none;
            }}
            QToolButton:hover {{
                background-color: #DC2626;
            }}
        """)
        self.btn_chroma_reset.clicked.connect(self._reset_chroma_key)
        tools_row.addWidget(self.btn_chroma_reset)
        
        chroma_layout.addLayout(tools_row)
        
        # ── แถวแสดงสีที่เลือก ──
        color_row = QHBoxLayout()
        color_label = QLabel("สีที่เลือก:")
        color_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self.lbl_color_indicator = QLabel()
        self.lbl_color_indicator.setFixedSize(30, 30)
        self.lbl_color_indicator.setStyleSheet(f"background-color: transparent; border: 1px solid {BORDER}; border-radius: 4px;")
        self.lbl_color_rgb = QLabel("(กดปุ่มดูดสี แล้วคลิกที่รูป)")
        self.lbl_color_rgb.setStyleSheet(f"color: {TEXT_MUTED};")
        color_row.addWidget(color_label)
        color_row.addWidget(self.lbl_color_indicator)
        color_row.addWidget(self.lbl_color_rgb, stretch=1)
        chroma_layout.addLayout(color_row)
        
        # ── Slider: Tolerance ──
        tol_layout = QHBoxLayout()
        tol_label = QLabel("Tolerance:")
        tol_label.setFixedWidth(70)
        tol_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self.slider_tolerance = QSlider(Qt.Orientation.Horizontal)
        self.slider_tolerance.setRange(0, 255)
        self.slider_tolerance.setValue(30)
        self.lbl_tol_val = QLabel("30")
        self.lbl_tol_val.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: bold;")
        self.slider_tolerance.valueChanged.connect(self._on_tolerance_changed)
        tol_layout.addWidget(tol_label)
        tol_layout.addWidget(self.slider_tolerance)
        tol_layout.addWidget(self.lbl_tol_val)
        chroma_layout.addLayout(tol_layout)
        
        # ── Slider: Edge Crop ──
        edge_layout = QHBoxLayout()
        edge_label = QLabel("Edge Crop:")
        edge_label.setFixedWidth(70)
        edge_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self.slider_edge = QSlider(Qt.Orientation.Horizontal)
        self.slider_edge.setRange(0, 10)
        self.slider_edge.setValue(0)
        self.lbl_edge_val = QLabel("0")
        self.lbl_edge_val.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: bold;")
        self.slider_edge.valueChanged.connect(self._on_edge_crop_changed)
        edge_layout.addWidget(edge_label)
        edge_layout.addWidget(self.slider_edge)
        edge_layout.addWidget(self.lbl_edge_val)
        chroma_layout.addLayout(edge_layout)
        
        # ── Chroma Layer List ──
        layer_header = QHBoxLayout()
        lbl_layers = QLabel("Layer สีที่ลบ:")
        lbl_layers.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: bold;")
        
        self.btn_del_layer = QPushButton()
        self.btn_del_layer.setIcon(_make_cross_icon(size=14, color=QColor("#FFFFFF")))
        self.btn_del_layer.setIconSize(QSize(14, 14))
        self.btn_del_layer.setFixedSize(30, 30)
        self.btn_del_layer.setToolTip("ลบ Layer ที่เลือก")
        self.btn_del_layer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del_layer.setStyleSheet(f"""
            QPushButton {{
                background-color: {DANGER};
                border-radius: 6px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #DC2626;
            }}
            QPushButton:pressed {{
                background-color: #B91C1C;
            }}
        """)
        self.btn_del_layer.clicked.connect(self._delete_active_layer)
        
        layer_header.addWidget(lbl_layers)
        layer_header.addStretch()
        layer_header.addWidget(self.btn_del_layer)
        chroma_layout.addLayout(layer_header)
        
        self.list_chroma_layers = QListWidget()
        self.list_chroma_layers.setStyleSheet(f"""
            QListWidget {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 4px;
                font-size: 13px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-radius: 6px;
                color: {TEXT_PRIMARY};
            }}
            QListWidget::item:hover {{
                background-color: {BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {BG_HOVER};
                border: 1px solid {PRIMARY};
            }}
        """)
        self.list_chroma_layers.setMaximumHeight(120)
        self.list_chroma_layers.currentRowChanged.connect(self._on_chroma_layer_selected)
        chroma_layout.addWidget(self.list_chroma_layers)
        
        left_layout.addWidget(grp_chroma)
        left_layout.addSpacing(20)
        
        # Zoom Controls
        zoom_layout = QHBoxLayout()
        zoom_label = QLabel("ซูม:")
        zoom_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: bold; font-size: 15px;")
        
        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedSize(30, 30)
        btn_zoom_out.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 0;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
        """)
        btn_zoom_out.clicked.connect(lambda: self.view.zoom_out())
        
        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(30, 30)
        btn_zoom_in.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 0;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
        """)
        btn_zoom_in.clicked.connect(lambda: self.view.zoom_in())
        
        zoom_layout.addWidget(zoom_label)
        zoom_layout.addWidget(btn_zoom_out)
        zoom_layout.addWidget(self.lbl_zoom)
        zoom_layout.addWidget(btn_zoom_in)
        zoom_layout.addStretch()
        left_layout.addLayout(zoom_layout)
        left_layout.addSpacing(10)

        # Undo/Redo Controls
        undo_redo_layout = QHBoxLayout()
        
        self.btn_undo = QToolButton()
        self.btn_undo.setToolTip("ย้อนกลับ (Ctrl+Z)")
        undo_icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image", "undo.png")
        if os.path.exists(undo_icon_path):
            self.btn_undo.setIcon(_make_tinted_icon(undo_icon_path, QColor("white")))
            self.btn_undo.setIconSize(self.btn_undo.sizeHint())
        else:
            self.btn_undo.setText("↩ Undo")
        self.btn_undo.setFixedSize(44, 44)
        self.btn_undo.setEnabled(False)
        self.btn_undo.setStyleSheet(f"""
            QToolButton {{
                padding: 6px;
                border-radius: 6px;
                background-color: {BG_INPUT};
                border: 1px solid {BORDER};
                color: {TEXT_PRIMARY};
            }}
            QToolButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
            QToolButton:disabled {{
                background-color: {BG_DARK};
                border: 1px solid {BORDER};
                color: {TEXT_MUTED};
            }}
        """)
        self.btn_undo.clicked.connect(self._undo)
        undo_redo_layout.addWidget(self.btn_undo)
        
        self.btn_redo = QToolButton()
        self.btn_redo.setToolTip("ย้อนคืน (Ctrl+Shift+Z)")
        redo_icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image", "redo.png")
        if os.path.exists(redo_icon_path):
            self.btn_redo.setIcon(_make_tinted_icon(redo_icon_path, QColor("white")))
            self.btn_redo.setIconSize(self.btn_redo.sizeHint())
        else:
            self.btn_redo.setText("↪ Redo")
        self.btn_redo.setFixedSize(44, 44)
        self.btn_redo.setEnabled(False)
        self.btn_redo.setStyleSheet(f"""
            QToolButton {{
                padding: 6px;
                border-radius: 6px;
                background-color: {BG_INPUT};
                border: 1px solid {BORDER};
                color: {TEXT_PRIMARY};
            }}
            QToolButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
            QToolButton:disabled {{
                background-color: {BG_DARK};
                border: 1px solid {BORDER};
                color: {TEXT_MUTED};
            }}
        """)
        self.btn_redo.clicked.connect(self._redo)
        undo_redo_layout.addWidget(self.btn_redo)
        
        # สลับมุมมอง Slot อยู่ขวาสุดในแถวเดียวกับ Undo/Redo
        undo_redo_layout.addStretch()
        
        self.btn_toggle_view = QToolButton()
        self.btn_toggle_view.setCheckable(True)
        self.btn_toggle_view.setToolTip("สลับมุมมอง Slot: โปร่งใส / รูปตัวอย่าง")
        self.btn_toggle_view.setFixedSize(44, 44)
        self.btn_toggle_view.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # โหลด icon ตามสถานะ
        self._icon_transparent = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image", "transparent.png")
        self._icon_dummy_view = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image", "dummy_view.png")
        
        if os.path.exists(self._icon_transparent):
            self.btn_toggle_view.setIcon(QIcon(self._icon_transparent))
            self.btn_toggle_view.setIconSize(QSize(28, 28))
        
        self.btn_toggle_view.setStyleSheet(f"""
            QToolButton {{
                padding: 6px;
                border-radius: 6px;
                background-color: {BG_INPUT};
                border: 1px solid {BORDER};
            }}
            QToolButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
            QToolButton:checked {{
                background-color: {PRIMARY};
                border: 1px solid {PRIMARY_HOVER};
            }}
        """)
        self.btn_toggle_view.clicked.connect(self._on_toggle_dummy_preview)
        undo_redo_layout.addWidget(self.btn_toggle_view)
        
        left_layout.addLayout(undo_redo_layout)
        left_layout.addSpacing(10)

        self.btn_save = QPushButton("บันทึก Template")
        self.btn_save.setProperty("cssClass", "primary")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_template)
        left_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("ยกเลิก")
        self.btn_cancel.setProperty("cssClass", "danger")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        left_layout.addWidget(self.btn_cancel)

        layout.addWidget(left_panel)

        # ---------- Right Panel (Canvas) ----------
        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        
        self.view = TemplateGraphicsView(self.scene, dialog=self)
        self.view.zoom_changed.connect(lambda p: self.lbl_zoom.setText(f"{p}%"))
        
        # Shortcuts for Zoom
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self.view.zoom_in)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.view.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.view.zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self.view.reset_zoom)
        # Shortcut Escape เพื่อยกเลิกเครื่องมือ
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._deactivate_tool)
        # Shortcuts for Undo/Redo — guard ไม่ให้ fire ถ้า focus อยู่ใน text input
        def _undo_guarded():
            if not self._is_text_input_focused():
                self._undo()
        def _redo_guarded():
            if not self._is_text_input_focused():
                self._redo()
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(_undo_guarded)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self).activated.connect(_redo_guarded)
        # Shortcuts for Slot Copy/Paste/Duplicate/Delete
        QShortcut(QKeySequence("Ctrl+C"), self).activated.connect(self._on_shortcut_copy)
        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(self._on_shortcut_paste)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._on_shortcut_duplicate)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self._on_shortcut_delete)
        QShortcut(QKeySequence("Backspace"), self).activated.connect(self._on_shortcut_delete)
        
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

    # ═══════════════════════════════════════════════════
    #  Dummy Preview Management
    # ═══════════════════════════════════════════════════

    def _load_dummy_pixmap(self) -> None:
        """โหลด dummy.jpg เป็น QPixmap แคชไว้ใช้ตอน preview"""
        dummy_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "image", "dummy.jpg"
        )
        if os.path.exists(dummy_path):
            self._dummy_pixmap = QPixmap(dummy_path)
        else:
            self._dummy_pixmap = None
            logger.warning("ไม่พบไฟล์ dummy.jpg ที่ %s", dummy_path)

    def _on_toggle_dummy_preview(self) -> None:
        """สลับโหมดมุมมอง Slot: โปร่งใส ↔ รูปตัวอย่าง"""
        self._preview_dummy = self.btn_toggle_view.isChecked()
        
        # สลับ icon ตามสถานะ
        if self._preview_dummy:
            if os.path.exists(self._icon_dummy_view):
                self.btn_toggle_view.setIcon(QIcon(self._icon_dummy_view))
                self.btn_toggle_view.setIconSize(QSize(28, 28))
        else:
            if os.path.exists(self._icon_transparent):
                self.btn_toggle_view.setIcon(QIcon(self._icon_transparent))
                self.btn_toggle_view.setIconSize(QSize(28, 28))
        
        # repaint ทุก Slot
        for slot in self.slots:
            slot.update()

    # ═══════════════════════════════════════════════════
    #  Tool State Management
    # ═══════════════════════════════════════════════════

    def _on_tool_picker_clicked(self):
        """สลับเครื่องมือ Color Picker"""
        if self.btn_tool_picker.isChecked():
            self.current_tool = TOOL_PICKER
            self.btn_tool_zone.setChecked(False)
            self._set_slots_interactive(False)
        else:
            self._deactivate_tool()

    def _on_tool_zone_clicked(self):
        """สลับเครื่องมือ Draw Zone — ต้องเคยดูดสีมาก่อนอย่างน้อย 1 ครั้ง"""
        if self.btn_tool_zone.isChecked():
            # ต้องมีสีที่เคยดูดไว้ (จาก active layer หรือ target_rgb)
            has_color = self.target_rgb is not None
            if not has_color and self.chroma_layers:
                has_color = True  # มี layer อยู่แล้ว ใช้สีจาก layer ได้
            if not has_color:
                QMessageBox.warning(self, "แจ้งเตือน", "กรุณาดูดสีก่อนอย่างน้อย 1 ครั้ง จึงจะวาดโซนได้\n(กดปุ่มดูดสี แล้วคลิกที่รูป)")
                self.btn_tool_zone.setChecked(False)
                return
            self.current_tool = TOOL_ZONE
            self.btn_tool_picker.setChecked(False)
            self._set_slots_interactive(False)
        else:
            self._deactivate_tool()

    def _deactivate_tool(self):
        """คืนสถานะเมาส์กลับเป็นปกติ"""
        self.current_tool = TOOL_NONE
        self.btn_tool_picker.setChecked(False)
        self.btn_tool_zone.setChecked(False)
        self._set_slots_interactive(True)
        # ลบ rubber band ถ้ามี
        if self._rubber_band_item:
            self.scene.removeItem(self._rubber_band_item)
            self._rubber_band_item = None

    def _set_slots_interactive(self, enabled: bool):
        """Toggle flags ของ Slot ทั้งหมด เพื่อป้องกัน event ตีกัน"""
        for item in self.slots:
            item.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, enabled)
            item.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, enabled)

    # ═══════════════════════════════════════════════════
    #  Image Loading & Pixmap Update
    # ═══════════════════════════════════════════════════

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
                
                # โหลด Slots
                for i, slot in enumerate(config.get("slots", [])):
                    self.slot_counter += 1
                    x = slot.get("x", 0)
                    y = slot.get("y", 0)
                    w = slot.get("width", 400)
                    h = slot.get("height", 300)
                    angle = slot.get("angle", 0)
                    # backward compatible: ถ้าไม่มี photo_index ให้ใช้ลำดับ i
                    pi = slot.get("photo_index", i)
                    
                    # x, y ที่เก็บไว้คือมุมบนซ้าย (ตอนยังไม่หมุน)
                    # สร้าง rect ด้วยพิกัดนี้ แล้ว ResizableRectItem จะนำ rect.center() ไปใช้เป็น pos()
                    rect = QRectF(x, y, w, h)
                    item = ResizableRectItem(rect, self.slot_counter, photo_index=pi)
                    item._dialog = self
                    item.setRotation(angle)
                    item.geometry_changed.connect(self._on_slot_geometry_changed)
                    item.link_requested.connect(self._on_link_requested)
                    item.unlink_requested.connect(self._on_unlink_requested)
                    
                    self.scene.addItem(item)
                    self.slots.append(item)
                
                self._refresh_slot_list()
                
                # โหลด Chroma Layers (ถ้ามี — backward compatible)
                for layer_data in config.get("chroma_layers", []):
                    color = tuple(layer_data.get("color", [0, 0, 0]))
                    rect_data = layer_data.get("rect")
                    roi = tuple(rect_data) if rect_data else None
                    tol = layer_data.get("tolerance", 30)
                    edge = layer_data.get("edge_crop", 0)
                    
                    layer = {
                        "color": color,
                        "rect": roi,
                        "tolerance": tol,
                        "edge_crop": edge,
                        "rect_item": None
                    }
                    
                    # สร้าง QGraphicsRectItem สำหรับ ROI ถ้ามี
                    if roi:
                        rect_item = self._create_roi_rect_item(roi)
                        layer["rect_item"] = rect_item
                    
                    self.chroma_layers.append(layer)
                    self._add_layer_list_item(layer)
                
                # Apply chroma layers ถ้ามี
                if self.chroma_layers:
                    self._apply_all_chroma_layers()
                    
            except Exception as e:
                logger.error("โหลดไฟล์ JSON เดิมไม่สำเร็จ: %s", e)
        
        # บันทึกสถานะเริ่มต้นสำหรับ Undo/Redo
        self._save_state()

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

    # ═══════════════════════════════════════════════════
    #  Slot Management + Linked Slots
    # ═══════════════════════════════════════════════════

    # ─── Keyboard Shortcut Guards ───
    def _is_text_input_focused(self) -> bool:
        """ตรวจสอบว่าขณะนี้ผู้ใช้กำลังโฟกัสอยู่ที่ช่องพิมพ์ข้อความหรือไม่"""
        from PyQt6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
        focus_w = self.focusWidget()
        return isinstance(focus_w, (QLineEdit, QTextEdit, QPlainTextEdit))

    def _on_shortcut_copy(self) -> None:
        focus_w = self.focusWidget()
        from PyQt6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
        if isinstance(focus_w, (QLineEdit, QTextEdit, QPlainTextEdit)):
            focus_w.copy()
            return
        self.copy_selected_slot()

    def _on_shortcut_paste(self) -> None:
        focus_w = self.focusWidget()
        from PyQt6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
        if isinstance(focus_w, (QLineEdit, QTextEdit, QPlainTextEdit)):
            focus_w.paste()
            return
        self.paste_slot()

    def _on_shortcut_duplicate(self) -> None:
        if not self._is_text_input_focused():
            self.duplicate_selected_slot()

    def _on_shortcut_delete(self) -> None:
        if not self._is_text_input_focused():
            self._delete_slot()

    def keyPressEvent(self, event) -> None:
        """ดักจับคีย์ลัดในระดับ Dialog — QShortcut จัดการ Ctrl+C/V/D/Delete แล้ว
        keyPressEvent นี้ใช้เพื่อรับ event ที่ QShortcut ไม่ครอบคลุมเท่านั้น"""
        super().keyPressEvent(event)

    # ─── Copy / Paste / Duplicate Logic ───
    def copy_selected_slot(self) -> None:
        """คัดลอกข้อมูล Slot ที่กำลังเลือกอยู่ (Active Slot) ลง In-Memory Clipboard"""
        selected_slot = None
        selected_items = self.scene.selectedItems()
        for item in selected_items:
            if isinstance(item, ResizableRectItem) and item in self.slots:
                selected_slot = item
                break
                
        if not selected_slot:
            row = self.list_slots.currentRow()
            if 0 <= row < len(self.slots):
                selected_slot = self.slots[row]
                
        if not selected_slot:
            return
            
        # ใช้ copy.deepcopy() ดึงเฉพาะคุณสมบัติ ไม่คัดลอก Pointer หรือ QGraphicsItem โดยตรง
        self.clipboard_slot_data = copy.deepcopy({
            "w": selected_slot.w,
            "h": selected_slot.h,
            "width": selected_slot.w,
            "height": selected_slot.h,
            "angle": selected_slot.rotation(),
            "rotation": selected_slot.rotation(),
            "photo_index": selected_slot.photo_index,
            "scale_mode": getattr(selected_slot, "scale_mode", "fit"),
            "cx": selected_slot.pos().x(),
            "cy": selected_slot.pos().y(),
        })
        logger.info("คัดลอก Slot %s ลง Clipboard เรียบร้อย: %s", selected_slot.slot_index, self.clipboard_slot_data)

    def paste_slot(self, target_pos: QPointF | None = None) -> None:
        """วาง Slot จาก Clipboard ลงบน Scene พร้อมคำนวณพิกัดใหม่และอัปเดต Undo Stack"""
        if not self.clipboard_slot_data:
            return
            
        w = self.clipboard_slot_data.get("width", self.clipboard_slot_data.get("w", 400))
        h = self.clipboard_slot_data.get("height", self.clipboard_slot_data.get("h", 300))
        angle = self.clipboard_slot_data.get("rotation", self.clipboard_slot_data.get("angle", 0))
        scale_mode = self.clipboard_slot_data.get("scale_mode", "fit")
        
        # คำนวณขอบเขต Canvas ของ Template
        canvas_w = self.pixmap.width() if (hasattr(self, "pixmap") and self.pixmap) else 1200
        canvas_h = self.pixmap.height() if (hasattr(self, "pixmap") and self.pixmap) else 800
        
        half_w = w / 2
        half_h = h / 2
        
        if target_pos is not None:
            cx = target_pos.x()
            cy = target_pos.y()
        else:
            # ขยับเยื้องจากตำแหน่ง Slot ต้นฉบับ (+25 px, +25 px) หรือจุดศูนย์กลาง viewport
            if "cx" in self.clipboard_slot_data and "cy" in self.clipboard_slot_data:
                cx = self.clipboard_slot_data["cx"] + 25
                cy = self.clipboard_slot_data["cy"] + 25
            else:
                viewport_center = self.view.mapToScene(self.view.viewport().rect().center())
                cx = viewport_center.x() + 25
                cy = viewport_center.y() + 25
            
            # อัปเดตพิกัดใน Clipboard เพื่อให้การกด Paste ซ้ำ ขยับเยื้องต่อเนื่อง (+25, +25)
            self.clipboard_slot_data["cx"] = cx
            self.clipboard_slot_data["cy"] = cy

        # ตรวจสอบไม่ให้พิกัดหลุดออกนอกขอบเขต Canvas ของ Template
        if cx + half_w > canvas_w or cy + half_h > canvas_h or cx - half_w < 0 or cy - half_h < 0:
            # ถ้าล้นขอบ ให้วนกลับมาเริ่มที่มุมบนซ้าย (+25, +25)
            if cx + half_w > canvas_w or cx - half_w < 0:
                cx = half_w + 25
            if cy + half_h > canvas_h or cy - half_h < 0:
                cy = half_h + 25
            self.clipboard_slot_data["cx"] = cx
            self.clipboard_slot_data["cy"] = cy

        # Clamp ค่าให้อยู่ภายใน Canvas อย่างแน่นอน
        cx = max(half_w, min(cx, canvas_w - half_w))
        cy = max(half_h, min(cy, canvas_h - half_h))

        # หาหมายเลข slot_index ใหม่ต่อท้ายลำดับสูงสุด
        max_slot_index = max((s.slot_index for s in self.slots), default=0)
        self.slot_counter = max(self.slot_counter + 1, max_slot_index + 1)
        
        # photo_index ใหม่ = ช็อตใหม่ที่เป็นอิสระตามค่าเริ่มต้น (ต่อจากค่าสูงสุดที่มี)
        new_photo_index = max((s.photo_index for s in self.slots), default=-1) + 1
        
        # สร้าง ResizableRectItem ชิ้นใหม่ขึ้นมาบน Scene
        rect = QRectF(cx - half_w, cy - half_h, w, h)
        item = ResizableRectItem(rect, self.slot_counter, photo_index=new_photo_index)
        item._dialog = self
        item.setRotation(angle)
        item.scale_mode = scale_mode
            
        item.geometry_changed.connect(self._on_slot_geometry_changed)
        item.link_requested.connect(self._on_link_requested)
        item.unlink_requested.connect(self._on_unlink_requested)
        
        self.scene.addItem(item)
        self.slots.append(item)
        
        # จัดเรียง photo_index ให้เป็นลำดับมาตรฐาน
        self.normalize_photo_indices()
        
        # ไฮไลต์และ Focus ไปที่ Slot ที่เพิ่งวางใหม่ทันที
        self.scene.clearSelection()
        item.setSelected(True)
        self.view.ensureVisible(item)
        self._refresh_slot_list()
        self.list_slots.setCurrentRow(len(self.slots) - 1)
        
        # บันทึกการเปลี่ยนแปลงลงใน Undo/Redo Stack
        self.push_undo()

    def duplicate_selected_slot(self) -> None:
        """ทำซ้ำ Slot ที่กำลังถูกเลือก (Copy + Paste ในขั้นตอนเดียว)"""
        self.copy_selected_slot()
        self.paste_slot()

    def push_undo(self) -> None:
        """บันทึก state ปัจจุบันลง Undo/Redo stack"""
        self._save_state()

    def _add_slot(self) -> None:
        """เพิ่มกล่อง (Slot) ใหม่ลงบนจอ"""
        # วางกล่องขนาดเริ่มต้นไว้ตรงกลางๆ
        cx = self.pixmap.width() / 2 - 200
        cy = self.pixmap.height() / 2 - 150
        rect = QRectF(cx, cy, 400, 300)
        
        self.slot_counter += 1
        # photo_index ใหม่ = max ที่มี + 1 (ไม่ซ้ำกับที่มีอยู่)
        new_photo_index = max((s.photo_index for s in self.slots), default=-1) + 1
        item = ResizableRectItem(rect, self.slot_counter, photo_index=new_photo_index)
        item._dialog = self
        item.geometry_changed.connect(self._on_slot_geometry_changed)
        item.link_requested.connect(self._on_link_requested)
        item.unlink_requested.connect(self._on_unlink_requested)
        
        self.scene.addItem(item)
        self.slots.append(item)
        
        # เลือกกล่องให้ทันที
        self.scene.clearSelection()
        item.setSelected(True)
        
        self._refresh_slot_list()
        self._save_state()
        
    def _delete_slot(self) -> None:
        """ลบกล่อง (Slot) ที่ถูกเลือกอยู่"""
        target_item = None
        selected_items = self.scene.selectedItems()
        for item in selected_items:
            if isinstance(item, ResizableRectItem) and item in self.slots:
                target_item = item
                break
                
        if not target_item:
            row = self.list_slots.currentRow()
            if 0 <= row < len(self.slots):
                target_item = self.slots[row]
                
        if not target_item:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาคลิกเลือก Slot ที่ต้องการลบก่อน")
            return
            
        idx = self.slots.index(target_item)
        self.scene.removeItem(target_item)
        self.slots.pop(idx)
        self.normalize_photo_indices()
        self._refresh_slot_list()
        self._save_state()

    def normalize_photo_indices(self) -> None:
        """จัดเรียง photo_index ให้เป็นลำดับต่อเนื่อง 0, 1, 2, ...
        
        Slot ที่มี photo_index เดียวกันจะยังคงเดียวกัน (linked)
        แต่ตัวเลขจะถูก remap ให้ไม่กระโดด
        """
        if not self.slots:
            return
        
        # รวบรวม unique photo_index ตามลำดับที่ปรากฏ
        seen = {}
        next_idx = 0
        for slot in self.slots:
            if slot.photo_index not in seen:
                seen[slot.photo_index] = next_idx
                next_idx += 1
        
        # Remap
        for slot in self.slots:
            old_pi = slot.photo_index
            slot.photo_index = seen[old_pi]
            slot.update()  # repaint

    def _refresh_slot_list(self) -> None:
        """อัปเดต QListWidget ให้แสดง photo_index + linked icon"""
        self.list_slots.clear()
        # นับจำนวน slot ต่อ photo_index เพื่อดูว่า linked กัน
        pi_counts = {}
        for s in self.slots:
            pi_counts[s.photo_index] = pi_counts.get(s.photo_index, 0) + 1
        
        for item in self.slots:
            linked = pi_counts.get(item.photo_index, 1) > 1
            icon = "🔗" if linked else "📷"
            text = f"{icon} Slot {item.slot_index} [ช็อต {item.photo_index + 1}]"
            list_item = QListWidgetItem(text)
            if linked:
                group_color = item.get_group_color()
                list_item.setForeground(group_color)
                font = list_item.font()
                font.setBold(True)
                list_item.setFont(font)
            self.list_slots.addItem(list_item)

    def _on_link_requested(self, source_item: ResizableRectItem, target_photo_index: int) -> None:
        """เมื่อ Slot ร้องขอ Link กับ photo_index อื่น"""
        source_item.photo_index = target_photo_index
        self.normalize_photo_indices()
        self._refresh_slot_list()
        # repaint all slots เพื่ออัปเดตสีและ linked count
        for s in self.slots:
            s.update()
        self._save_state()

    def _on_unlink_requested(self, source_item: ResizableRectItem) -> None:
        """เมื่อ Slot ร้องขอ Unlink ออกจาก group"""
        # กำหนด photo_index ใหม่ที่ไม่ซ้ำกับใคร
        max_pi = max((s.photo_index for s in self.slots), default=-1)
        source_item.photo_index = max_pi + 1
        self.normalize_photo_indices()
        self._refresh_slot_list()
        # repaint all slots
        for s in self.slots:
            s.update()
        self._save_state()

    def _on_scene_selection_changed(self) -> None:
        """เมื่อคลิกเลือกของใน scene ให้ไฮไลต์รายการใน list ด้วย"""
        try:
            if not hasattr(self, 'scene') or self.scene is None or sip.isdeleted(self.scene):
                return
            selected_items = self.scene.selectedItems()
            if selected_items and selected_items[0] in self.slots:
                idx = self.slots.index(selected_items[0])
                if hasattr(self, 'list_slots') and not sip.isdeleted(self.list_slots):
                    self.list_slots.setCurrentRow(idx)
        except RuntimeError:
            pass
            
    def _on_list_item_selected(self, row: int) -> None:
        """เมื่อจิ้มรายการใน list ให้ไฮไลต์กล่องใน scene ด้วย"""
        try:
            if not hasattr(self, 'scene') or self.scene is None or sip.isdeleted(self.scene):
                return
            if row >= 0 and row < len(self.slots):
                self.scene.clearSelection()
                if row < len(self.slots):
                    self.slots[row].setSelected(True)
            # ซ่อนกรอบ ROI ทั้งหมดเมื่อเลือก Slot
            self._hide_all_roi_rects()
        except RuntimeError:
            pass

    def closeEvent(self, event) -> None:
        """ตัดการเชื่อมต่อสัญญาณก่อนปิด dialog เพื่อป้องกัน C++ deleted object error"""
        try:
            if hasattr(self, 'scene') and self.scene is not None and not sip.isdeleted(self.scene):
                self.scene.selectionChanged.disconnect(self._on_scene_selection_changed)
        except Exception:
            pass
        super().closeEvent(event)

    def reject(self) -> None:
        """เมื่อยกเลิกหรือปิด dialog"""
        try:
            if hasattr(self, 'scene') and self.scene is not None and not sip.isdeleted(self.scene):
                self.scene.selectionChanged.disconnect(self._on_scene_selection_changed)
        except Exception:
            pass
        super().reject()

    def accept(self) -> None:
        """เมื่อบันทึกและปิด dialog"""
        try:
            if hasattr(self, 'scene') and self.scene is not None and not sip.isdeleted(self.scene):
                self.scene.selectionChanged.disconnect(self._on_scene_selection_changed)
        except Exception:
            pass
        super().accept()

    # ═══════════════════════════════════════════════════
    #  Chroma Key: Color Picking
    # ═══════════════════════════════════════════════════

    def pick_color(self, x: int, y: int):
        """ดูดสีจากตำแหน่ง x, y ของรูปต้นฉบับ แล้วสร้าง Layer ใหม่"""
        if self.original_image is None:
            return
            
        # เช็คขอบเขต
        if 0 <= x < self.original_image.width and 0 <= y < self.original_image.height:
            r, g, b, a = self.original_image.getpixel((x, y))
            self.target_rgb = (r, g, b)
            
            # อัปเดต UI แสดงสี
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            self.lbl_color_indicator.setStyleSheet(f"background-color: {hex_color}; border: 1px solid white;")
            self.lbl_color_rgb.setText(f"RGB: ({r}, {g}, {b})")
            
            # สร้าง Layer ใหม่
            layer = {
                "color": (r, g, b),
                "rect": None,        # None = ลบทั้งภาพ (default)
                "tolerance": self.slider_tolerance.value(),
                "edge_crop": self.slider_edge.value(),
                "rect_item": None
            }
            self.chroma_layers.append(layer)
            self._add_layer_list_item(layer)
            
            # เลือก layer ใหม่ทันที
            self.list_chroma_layers.setCurrentRow(len(self.chroma_layers) - 1)
            
            # คืนเครื่องมือเป็นปกติ
            self._deactivate_tool()
            
            # Real-time preview
            self._apply_all_chroma_layers()
            self._save_state()

    # ═══════════════════════════════════════════════════
    #  Chroma Key: Zone Drawing (ROI)
    # ═══════════════════════════════════════════════════

    def _update_zone_rubber_band(self, start: QPointF, current: QPointF):
        """แสดง rubber band preview ขณะลากวาดโซน"""
        x1, y1 = start.x(), start.y()
        x2, y2 = current.x(), current.y()
        rect = QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        
        if self._rubber_band_item is None:
            self._rubber_band_item = QGraphicsRectItem(rect)
            self._rubber_band_item.setPen(QPen(QColor(0, 200, 255, 180), 2, Qt.PenStyle.DashLine))
            self._rubber_band_item.setBrush(QBrush(QColor(0, 200, 255, 30)))
            self._rubber_band_item.setZValue(10)  # อยู่บนสุดขณะวาด
            self.scene.addItem(self._rubber_band_item)
        else:
            self._rubber_band_item.setRect(rect)

    def _finish_zone_draw(self, start: QPointF, end: QPointF):
        """วาดโซนเสร็จ — สร้าง Layer ใหม่ด้วยสีปัจจุบัน + ROI ที่วาด (วาดได้หลายโซน)"""
        # ลบ rubber band
        if self._rubber_band_item:
            self.scene.removeItem(self._rubber_band_item)
            self._rubber_band_item = None
        
        # คำนวณ ROI rect
        x1, y1 = start.x(), start.y()
        x2, y2 = end.x(), end.y()
        rx = int(min(x1, x2))
        ry = int(min(y1, y2))
        rw = int(abs(x2 - x1))
        rh = int(abs(y2 - y1))
        
        # ขนาดต้องไม่เล็กเกินไป
        if rw < 10 or rh < 10:
            self._deactivate_tool()
            return
        
        roi = (rx, ry, rw, rh)
        
        # หาสีที่จะใช้: จาก active layer หรือ target_rgb
        color = None
        if 0 <= self._active_layer_index < len(self.chroma_layers):
            color = self.chroma_layers[self._active_layer_index]["color"]
        elif self.target_rgb:
            color = self.target_rgb
        
        if color is None:
            self._deactivate_tool()
            return
        
        # สร้าง Layer ใหม่ด้วยสีเดียวกัน + ROI ที่วาด
        rect_item = self._create_roi_rect_item(roi)
        rect_item.setVisible(True)  # แสดงกรอบทันที เพราะเป็น layer ที่กำลัง active
        
        new_layer = {
            "color": color,
            "rect": roi,
            "tolerance": self.slider_tolerance.value(),
            "edge_crop": self.slider_edge.value(),
            "rect_item": rect_item
        }
        self.chroma_layers.append(new_layer)
        self._add_layer_list_item(new_layer)
        
        # เลือก layer ใหม่ทันที
        self.list_chroma_layers.setCurrentRow(len(self.chroma_layers) - 1)
        
        # ไม่ deactivate tool — ให้ยังอยู่ในโหมด zone เพื่อวาดต่อได้เลย!
        
        # Real-time preview
        self._apply_all_chroma_layers()

    def _create_roi_rect_item(self, roi: tuple) -> QGraphicsRectItem:
        """สร้าง QGraphicsRectItem สำหรับแสดงกรอบ ROI บน Canvas"""
        rx, ry, rw, rh = roi
        rect_item = QGraphicsRectItem(QRectF(rx, ry, rw, rh))
        rect_item.setPen(QPen(QColor(0, 180, 255, 200), 2, Qt.PenStyle.DashDotLine))
        rect_item.setBrush(QBrush(QColor(0, 180, 255, 20)))
        rect_item.setZValue(-0.5)  # อยู่ระหว่าง background กับ Slot
        rect_item.setVisible(False)  # ค่าเริ่มต้น: ซ่อน
        # ไม่ให้ลากหรือเลือกได้ — ป้องกันตีกับ Slot
        rect_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)
        rect_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        self.scene.addItem(rect_item)
        return rect_item

    # ═══════════════════════════════════════════════════
    #  Chroma Key: Layer Management
    # ═══════════════════════════════════════════════════

    def _add_layer_list_item(self, layer: dict):
        """เพิ่ม item ใน list_chroma_layers จาก layer data"""
        r, g, b = layer["color"]
        roi = layer["rect"]
        zone_text = "ทั้งภาพ" if roi is None else f"โซน ({roi[0]},{roi[1]})"
        text = f"■ RGB({r},{g},{b}) — {zone_text}"
        
        item = QListWidgetItem(text)
        item.setForeground(QColor(r, g, b))
        self.list_chroma_layers.addItem(item)

    def _update_layer_list_item_text(self, index: int, layer: dict):
        """อัปเดตข้อความของ item ใน list"""
        if 0 <= index < self.list_chroma_layers.count():
            r, g, b = layer["color"]
            roi = layer["rect"]
            zone_text = "ทั้งภาพ" if roi is None else f"โซน ({roi[0]},{roi[1]})"
            text = f"■ RGB({r},{g},{b}) — {zone_text}"
            self.list_chroma_layers.item(index).setText(text)

    def _on_chroma_layer_selected(self, row: int):
        """เมื่อเลือก layer ใน list → อัปเดต UI"""
        self._active_layer_index = row
        
        # ซ่อนกรอบ ROI ทั้งหมดก่อน
        self._hide_all_roi_rects()
        
        if 0 <= row < len(self.chroma_layers):
            layer = self.chroma_layers[row]
            
            # แสดงกรอบ ROI ของ layer ที่เลือก (ถ้ามี)
            if layer["rect_item"]:
                layer["rect_item"].setVisible(True)
            
            # อัปเดต Slider ให้ตรงกับค่าของ layer นี้
            self._updating_sliders = True
            self.slider_tolerance.setValue(layer["tolerance"])
            self.slider_edge.setValue(layer["edge_crop"])
            self._updating_sliders = False
            
            # อัปเดต color indicator
            r, g, b = layer["color"]
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            self.lbl_color_indicator.setStyleSheet(f"background-color: {hex_color}; border: 1px solid white;")
            self.lbl_color_rgb.setText(f"RGB: ({r}, {g}, {b})")

    def _delete_active_layer(self):
        """ลบ layer ที่กำลัง active"""
        idx = self._active_layer_index
        if idx < 0 or idx >= len(self.chroma_layers):
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือก Layer สีที่ต้องการลบก่อน")
            return
        
        layer = self.chroma_layers[idx]
        
        # ลบ graphics item ของ ROI (ถ้ามี)
        if layer["rect_item"]:
            self.scene.removeItem(layer["rect_item"])
        
        self.chroma_layers.pop(idx)
        self.list_chroma_layers.takeItem(idx)
        self._active_layer_index = -1
        
        # Real-time preview
        self._apply_all_chroma_layers()
        self._save_state()

    def _hide_all_roi_rects(self):
        """ซ่อนกรอบ ROI ทั้งหมด"""
        for layer in self.chroma_layers:
            if layer["rect_item"]:
                layer["rect_item"].setVisible(False)

    # ═══════════════════════════════════════════════════
    #  Chroma Key: Slider Events → Real-time
    # ═══════════════════════════════════════════════════

    def _on_tolerance_changed(self, value: int):
        """Slider Tolerance เปลี่ยน → อัปเดต active layer + real-time preview"""
        self.lbl_tol_val.setText(str(value))
        if self._updating_sliders:
            return
        if 0 <= self._active_layer_index < len(self.chroma_layers):
            self.chroma_layers[self._active_layer_index]["tolerance"] = value
            self._apply_all_chroma_layers()

    def _on_edge_crop_changed(self, value: int):
        """Slider Edge Crop เปลี่ยน → อัปเดต active layer + real-time preview"""
        self.lbl_edge_val.setText(str(value))
        if self._updating_sliders:
            return
        if 0 <= self._active_layer_index < len(self.chroma_layers):
            self.chroma_layers[self._active_layer_index]["edge_crop"] = value
            self._apply_all_chroma_layers()

    # ═══════════════════════════════════════════════════
    #  Chroma Key: Processing & Preview
    # ═══════════════════════════════════════════════════

    def _apply_all_chroma_layers(self):
        """ประมวลผลลบพื้นหลังจากทุก Layer แล้วอัปเดตภาพ Real-time"""
        if self.original_image is None:
            return
        
        if not self.chroma_layers:
            # ไม่มี layer → แสดงภาพต้นฉบับ
            self.processed_image = self.original_image.copy()
        else:
            # สร้าง list ของ layer data (ไม่รวม rect_item)
            layers_data = []
            for layer in self.chroma_layers:
                layers_data.append({
                    "color": layer["color"],
                    "rect": layer["rect"],
                    "tolerance": layer["tolerance"],
                    "edge_crop": layer["edge_crop"]
                })
            
            self.processed_image = apply_multi_layer_chroma(
                self.original_image, layers_data
            )
        
        self._update_pixmap()

    # ═══════════════════════════════════════════════════
    #  Undo/Redo History
    # ═══════════════════════════════════════════════════

    def _capture_snapshot(self) -> dict:
        """จับ snapshot ของสถานะปัจจุบัน (slots + chroma layers + photo_index)"""
        slots_data = []
        for item in self.slots:
            cx = item.pos().x()
            cy = item.pos().y()
            slots_data.append({
                "slot_index": item.slot_index,
                "photo_index": item.photo_index,
                "cx": cx,
                "cy": cy,
                "w": item.w,
                "h": item.h,
                "angle": item.rotation(),
                "scale_mode": getattr(item, "scale_mode", "fit")
            })
        
        layers_data = []
        for layer in self.chroma_layers:
            layers_data.append({
                "color": layer["color"],
                "rect": layer["rect"],
                "tolerance": layer["tolerance"],
                "edge_crop": layer["edge_crop"]
            })
        
        return {
            "slot_counter": self.slot_counter,
            "slots": slots_data,
            "chroma_layers": layers_data,
            "target_rgb": self.target_rgb
        }

    def _save_state(self):
        """บันทึก state ปัจจุบันลง history stack"""
        if self._restoring_state:
            return
        
        snapshot = self._capture_snapshot()
        
        # ตัด history หลัง index ปัจจุบันออก (เพราะ redo ไม่ใช้แล้ว)
        self._history = self._history[:self._history_index + 1]
        self._history.append(snapshot)
        
        # จำกัดขนาด history
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        self._history_index = len(self._history) - 1
        self._update_undo_redo_buttons()

    def _undo(self):
        """ย้อนกลับ 1 step"""
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._restore_state(self._history[self._history_index])

    def _redo(self):
        """ย้อนคืน 1 step"""
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._restore_state(self._history[self._history_index])

    def _restore_state(self, snapshot: dict):
        """คืนสถานะจาก snapshot"""
        self._restoring_state = True
        
        try:
            # --- คืนค่า Slots ---
            # ลบ slots เก่าทั้งหมด
            for item in self.slots:
                self.scene.removeItem(item)
            self.slots.clear()
            self.list_slots.clear()
            
            self.slot_counter = snapshot["slot_counter"]
            
            for s in snapshot["slots"]:
                rect = QRectF(
                    s["cx"] - s["w"] / 2,
                    s["cy"] - s["h"] / 2,
                    s["w"],
                    s["h"]
                )
                pi = s.get("photo_index", s["slot_index"] - 1)
                item = ResizableRectItem(rect, s["slot_index"], photo_index=pi)
                item._dialog = self
                item.setRotation(s["angle"])
                item.scale_mode = s.get("scale_mode", "fit")
                item.geometry_changed.connect(self._on_slot_geometry_changed)
                item.link_requested.connect(self._on_link_requested)
                item.unlink_requested.connect(self._on_unlink_requested)
                self.scene.addItem(item)
                self.slots.append(item)
            
            self._refresh_slot_list()
            
            # --- คืนค่า Chroma Layers ---
            # ลบ ROI graphics items เก่า
            for layer in self.chroma_layers:
                if layer["rect_item"]:
                    self.scene.removeItem(layer["rect_item"])
            self.chroma_layers.clear()
            self.list_chroma_layers.clear()
            
            self.target_rgb = snapshot["target_rgb"]
            
            for l_data in snapshot["chroma_layers"]:
                layer = {
                    "color": l_data["color"],
                    "rect": l_data["rect"],
                    "tolerance": l_data["tolerance"],
                    "edge_crop": l_data["edge_crop"],
                    "rect_item": None
                }
                if l_data["rect"]:
                    layer["rect_item"] = self._create_roi_rect_item(l_data["rect"])
                self.chroma_layers.append(layer)
                self._add_layer_list_item(layer)
            
            self._active_layer_index = -1
            
            # อัปเดต color indicator
            if self.target_rgb:
                r, g, b = self.target_rgb
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                self.lbl_color_indicator.setStyleSheet(f"background-color: {hex_color}; border: 1px solid white;")
                self.lbl_color_rgb.setText(f"RGB: ({r}, {g}, {b})")
            else:
                self.lbl_color_indicator.setStyleSheet(f"background-color: transparent; border: 1px solid {BORDER}; border-radius: 4px;")
                self.lbl_color_rgb.setText("(กดปุ่มดูดสี แล้วคลิกที่รูป)")
            
            # รีเซ็ต sliders
            self._updating_sliders = True
            self.slider_tolerance.setValue(30)
            self.slider_edge.setValue(0)
            self._updating_sliders = False
            
            # Re-apply chroma layers
            self._apply_all_chroma_layers()
        
        finally:
            self._restoring_state = False
            self._update_undo_redo_buttons()

    def _on_slot_geometry_changed(self):
        """เมื่อ Slot ถูกย้าย/ยืดหด/หมุนเสร็จ ให้บันทึก state"""
        self._save_state()

    def _update_undo_redo_buttons(self):
        """อัปเดตสถานะ enabled/disabled ของปุ่ม Undo/Redo"""
        self.btn_undo.setEnabled(self._history_index > 0)
        self.btn_redo.setEnabled(self._history_index < len(self._history) - 1)

    # ═══════════════════════════════════════════════════
    #  Chroma Key: Reset
    # ═══════════════════════════════════════════════════

    def _reset_chroma_key(self):
        """ล้างการตั้งค่าลบสีทั้งหมด คืนภาพต้นฉบับ"""
        # ลบ graphics items ของ ROI ทั้งหมด
        for layer in self.chroma_layers:
            if layer["rect_item"]:
                self.scene.removeItem(layer["rect_item"])
        
        # ล้าง data
        self.chroma_layers.clear()
        self.list_chroma_layers.clear()
        self._active_layer_index = -1
        self.target_rgb = None
        
        # รีเซ็ต Slider
        self._updating_sliders = True
        self.slider_tolerance.setValue(30)
        self.slider_edge.setValue(0)
        self._updating_sliders = False
        
        # รีเซ็ต color indicator
        self.lbl_color_indicator.setStyleSheet(f"background-color: transparent; border: 1px solid {BORDER}; border-radius: 4px;")
        self.lbl_color_rgb.setText("(กดปุ่มดูดสี แล้วคลิกที่รูป)")
        
        # คืนเครื่องมือเป็นปกติ
        self._deactivate_tool()
        
        # คืนภาพต้นฉบับ
        if self.original_image:
            self.processed_image = self.original_image.copy()
            self._update_pixmap()

    # ═══════════════════════════════════════════════════
    #  Save Template
    # ═══════════════════════════════════════════════════

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
            if self.chroma_layers and self.processed_image:
                # ถ้ามีการตัดสีแล้ว ให้เซฟเป็น PNG เสมอ (PNG รองรับ Alpha/โปร่งใส)
                png_filename = basename + ".png"
                dest_img_path = os.path.join(self.dest_dir, png_filename)
                dest_json_path = os.path.join(self.dest_dir, f"{basename}.json")
                self.processed_image.save(dest_img_path, format="PNG")
                
                # ถ้าไฟล์ต้นฉบับอยู่ใน dest_dir แต่เป็นนามสกุลอื่น (เช่น .jpg) ลบตัวเก่าออกเพื่อไม่ให้มีไฟล์ซ้ำในหน้ารายการ
                old_dest_img = os.path.join(self.dest_dir, filename)
                if old_dest_img != dest_img_path and os.path.exists(old_dest_img):
                    try:
                        os.remove(old_dest_img)
                    except OSError:
                        pass
            elif self.processed_image and filename.lower().endswith(".png"):
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
                    "angle": round(angle, 2),
                    "photo_index": item.photo_index
                })

            # 3. เก็บ Chroma Layers
            chroma_data = []
            for layer in self.chroma_layers:
                chroma_data.append({
                    "color": list(layer["color"]),
                    "rect": list(layer["rect"]) if layer["rect"] else None,
                    "tolerance": layer["tolerance"],
                    "edge_crop": layer["edge_crop"]
                })

            # 4. คำนวณ total_photos = จำนวน unique photo_index
            unique_photos = len(set(item.photo_index for item in self.slots))
            
            # 5. เซฟเป็นไฟล์ .json
            config = {
                "total_photos": unique_photos,
                "slots": slots_data
            }
            # เพิ่ม chroma_layers เฉพาะเมื่อมีข้อมูล
            if chroma_data:
                config["chroma_layers"] = chroma_data

            with open(dest_json_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)

            unique_text = f" ({unique_photos} ช็อตจริง)" if unique_photos < len(self.slots) else ""
            QMessageBox.information(self, "สำเร็จ", f"บันทึก Template สำเร็จ!\nเพิ่ม {len(self.slots)} ช่อง{unique_text}เรียบร้อยแล้ว")
            self.accept()
            
        except Exception as e:
            logger.error("เกิดข้อผิดพลาดในการเซฟ Template: %s", e)
            QMessageBox.critical(self, "ข้อผิดพลาด", str(e))
