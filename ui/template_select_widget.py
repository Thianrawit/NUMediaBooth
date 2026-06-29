"""
TemplateSelectWidget — หน้าเลือก Template กรอบรูป
=====================================================
แสดง Grid ของ Template ที่มีให้เลือก (scan จากโฟลเดอร์ assets/templates/)
เมื่อจิ้มเลือก จะจำค่า path ไว้ แล้วกดปุ่ม "ถัดไป" ไปหน้าถ่ายรูป
มีการจัดเรียง Drag-and-drop และเปลี่ยนชื่อไฟล์
"""

import os
import json
import logging

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QFont, QIcon
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QListView,
    QMessageBox,
    QCheckBox,
)
from config_manager import ConfigManager
from path_manager import get_resource_path

logger = logging.getLogger(__name__)


class TemplateListWidget(QListWidget):
    """Custom QListWidget สำหรับรับ Event การลากวางเพื่อเรียงลำดับ"""
    order_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # ใช้ IconMode เพื่อให้รูปอยู่บน ข้อความอยู่ล่าง
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setSpacing(16)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
            }
            QListWidget::item {
                background: #353550;
                border-radius: 8px;
                padding: 10px;
                color: #FFFFFF;
            }
            QListWidget::item:selected {
                background: #4A4A6A;
                border: 3px solid #00E676;
            }
        """)

    def dropEvent(self, event):
        # Override dropEvent เพื่อให้ IconMode สามารถสลับตำแหน่ง (Reorder) ได้เหมือน ListMode
        if event.source() == self:
            drop_pos = event.position().toPoint()
            target_item = self.itemAt(drop_pos)
            dragged_item = self.currentItem()
            
            if dragged_item:
                if target_item and dragged_item != target_item:
                    target_row = self.row(target_item)
                    self.takeItem(self.row(dragged_item))
                    self.insertItem(target_row, dragged_item)
                    self.setCurrentItem(dragged_item)
                    event.accept()
                    self.order_changed.emit()
                    return
                elif not target_item:
                    # วางในที่ว่าง ให้ไปต่อท้าย
                    self.takeItem(self.row(dragged_item))
                    self.addItem(dragged_item)
                    self.setCurrentItem(dragged_item)
                    event.accept()
                    self.order_changed.emit()
                    return
        super().dropEvent(event)


class TemplateSelectWidget(QWidget):
    """หน้าเลือก Template — Grid Layout Responsive และรองรับ Drag & Drop"""

    back_clicked = pyqtSignal()
    template_selected = pyqtSignal(str, object)  # (path, layout_config or None)

    GRID_COLUMNS = 4

    def __init__(
        self,
        templates_dir: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TemplateSelectWidget")
        self.config_manager = ConfigManager()
        self.GRID_COLUMNS = self.config_manager.get("template_grid_columns", 4)

        # ตัวแปรสำหรับการกดปุ่มจัดเรียงซ้ำ 5 ครั้ง
        self._arrange_click_count = 0
        self._arrange_timer = QTimer(self)
        self._arrange_timer.setInterval(2000) # 2 วินาที
        self._arrange_timer.setSingleShot(True)
        self._arrange_timer.timeout.connect(self._reset_arrange_clicks)

        if templates_dir is None:
            self.templates_dir = get_resource_path(os.path.join("assets", "templates"))
        else:
            self.templates_dir = templates_dir

        self._arrange_mode = False

        self._init_ui()
        self.refresh_templates()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 16, 24, 24)
        root_layout.setSpacing(16)

        # ---------- Top Bar ----------
        top_bar = QHBoxLayout()

        self.btn_back = QPushButton()
        self.btn_back.setIcon(QIcon(get_resource_path(os.path.join("image", "back.png"))))
        self.btn_back.setIconSize(QSize(24, 24))
        self.btn_back.setFixedSize(40, 40)
        self.btn_back.setStyleSheet("background-color: white; border-radius: 8px;")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        top_bar.addWidget(self.btn_back)

        top_bar.addStretch()

        title = QLabel("🖼  เลือก Template กรอบรูป")
        title.setProperty("cssClass", "title")
        top_bar.addWidget(title)

        top_bar.addStretch()

        # Checkbox ซ่อนชื่อ Template (จะแสดงเฉพาะตอนกดจัดเรียง)
        self.chk_hide_name = QCheckBox("ซ่อนชื่อ Template")
        self.chk_hide_name.setProperty("cssClass", "nav")
        self.chk_hide_name.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_hide_name.setVisible(False)
        self.chk_hide_name.setChecked(self.config_manager.get("hide_template_names", False))
        self.chk_hide_name.stateChanged.connect(self._on_hide_name_changed)
        top_bar.addWidget(self.chk_hide_name)

        top_bar.addSpacing(10)

        # ปุ่ม จัดเรียง
        self.btn_arrange = QPushButton()
        self.btn_arrange.setIcon(QIcon(get_resource_path(os.path.join("image", "edit.png"))))
        self.btn_arrange.setIconSize(QSize(24, 24))
        self.btn_arrange.setFixedSize(40, 40)
        self.btn_arrange.setStyleSheet("background-color: white; border-radius: 8px;")
        self.btn_arrange.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_arrange.clicked.connect(self._on_arrange_clicked)
        top_bar.addWidget(self.btn_arrange)
        
        top_bar.addSpacing(10)

        # ปุ่ม Refresh
        self.btn_refresh = QPushButton()
        self.btn_refresh.setIcon(QIcon(get_resource_path(os.path.join("image", "refresh.png"))))
        self.btn_refresh.setIconSize(QSize(24, 24))
        self.btn_refresh.setFixedSize(40, 40)
        self.btn_refresh.setStyleSheet("background-color: white; border-radius: 8px;")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_templates)
        top_bar.addWidget(self.btn_refresh)

        root_layout.addLayout(top_bar)

        # ---------- Subtitle ----------
        hint = QLabel("จิ้มเลือก Template ที่ต้องการ แล้วกดปุ่ม \"ถัดไป\" ด้านล่าง")
        hint.setProperty("cssClass", "subtitle")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root_layout.addWidget(hint)

        # ---------- List Widget (Responsive Grid) ----------
        self.list_widget = TemplateListWidget()
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        self.list_widget.order_changed.connect(self._save_order)
        root_layout.addWidget(self.list_widget, stretch=1)

        # ---------- Empty State ----------
        self.empty_label = QLabel("📂  ยังไม่มี Template\nเพิ่ม Template ได้ที่หน้าตั้งค่า")
        self.empty_label.setProperty("cssClass", "subtitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setVisible(False)
        root_layout.addWidget(self.empty_label)

        # ---------- Bottom Bar ----------
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        self.label_selected = QLabel("ยังไม่ได้เลือก Template")
        self.label_selected.setProperty("cssClass", "muted")
        bottom_bar.addWidget(self.label_selected)

        bottom_bar.addSpacing(20)

        self.btn_next = QPushButton("ถัดไป  →")
        self.btn_next.setProperty("cssClass", "primary")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setFixedSize(160, 48)
        self.btn_next.setEnabled(False)
        next_font = QFont()
        next_font.setPointSize(14)
        next_font.setBold(True)
        self.btn_next.setFont(next_font)
        self.btn_next.clicked.connect(self._on_next_clicked)
        bottom_bar.addWidget(self.btn_next)

        root_layout.addLayout(bottom_bar)

    # ------------------------------------------------------------------
    # Template Management
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Equal or event.key() == Qt.Key.Key_Plus:
                self.zoom_in()
            elif event.key() == Qt.Key.Key_Minus:
                self.zoom_out()
            elif event.key() == Qt.Key.Key_0:
                self.GRID_COLUMNS = 4
                self.config_manager.set("template_grid_columns", self.GRID_COLUMNS)
                self.resizeEvent(None)
        super().keyPressEvent(event)
        
    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        super().wheelEvent(event)

    def zoom_in(self):
        """ซูมเข้า (แสดงรูปน้อยลง แต่รูปใหญ่ขึ้น)"""
        if self.GRID_COLUMNS > 1:
            self.GRID_COLUMNS -= 1
            self.config_manager.set("template_grid_columns", self.GRID_COLUMNS)
            self.resizeEvent(None)
            
    def zoom_out(self):
        """ซูมออก (แสดงรูปมากขึ้น แต่รูปลงเล็กลง)"""
        if self.GRID_COLUMNS < 10:
            self.GRID_COLUMNS += 1
            self.config_manager.set("template_grid_columns", self.GRID_COLUMNS)
            self.resizeEvent(None)

    def resizeEvent(self, event):
        """จัดการ Responsive ให้คงคอลัมน์ และขยายภาพตามขนาดจอ"""
        if event:
            super().resizeEvent(event)
        
        total_width = self.list_widget.viewport().width()
        spacing = self.list_widget.spacing()
        
        # พื้นที่ว่างสำหรับ 4 อัน (หักระยะห่าง)
        available_width = total_width - (spacing * (self.GRID_COLUMNS + 1))
        item_w = available_width // self.GRID_COLUMNS
        
        # สมมติ Aspect Ratio 3:4 สำหรับรูป
        item_h = int(item_w * 1.33)
        
        if item_w > 50:
            self.list_widget.setGridSize(QSize(item_w + spacing, item_h + spacing + 50))
            self.list_widget.setIconSize(QSize(item_w, item_h))

    def refresh_templates(self) -> None:
        """โหลดไฟล์และเรียงตาม template_order.json"""
        self.list_widget.clear()
        self.btn_next.setEnabled(False)
        self.label_selected.setText("ยังไม่ได้เลือก Template")
        self.label_selected.setStyleSheet("")
        
        os.makedirs(self.templates_dir, exist_ok=True)
        
        order_path = os.path.join(self.templates_dir, "template_order.json")
        order_list = []
        if os.path.exists(order_path):
            try:
                with open(order_path, "r", encoding="utf-8") as f:
                    order_list = json.load(f)
            except:
                pass

        valid_ext = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        files = [f for f in os.listdir(self.templates_dir) if os.path.splitext(f)[1].lower() in valid_ext]

        if not files:
            self.list_widget.setVisible(False)
            self.empty_label.setVisible(True)
            return

        self.list_widget.setVisible(True)
        self.empty_label.setVisible(False)

        # เรียงลำดับไฟล์ตาม order_list
        def sort_key(f):
            base = os.path.splitext(f)[0]
            try:
                return order_list.index(base)
            except ValueError:
                return 9999
        
        files.sort(key=sort_key)

        self.list_widget.blockSignals(True)
        for f in files:
            path = os.path.join(self.templates_dir, f)
            name = os.path.splitext(f)[0]
            
            icon = QIcon(path)
            item = QListWidgetItem(icon, name)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # โหลด layout config
            json_path = os.path.join(self.templates_dir, name + ".json")
            layout_config = None
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as jf:
                        layout_config = json.load(jf)
                except:
                    pass
                    
            item.setData(Qt.ItemDataRole.UserRole, layout_config)
            item.setData(Qt.ItemDataRole.UserRole + 1, path)
            item.setData(Qt.ItemDataRole.UserRole + 2, name) # เก็บชื่อจริงไว้เสมอ
            
            # อัปเดตการแสดงผลชื่อตาม config
            if self.chk_hide_name.isChecked():
                item.setText("")
                
            if self._arrange_mode:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
            self.list_widget.addItem(item)
            
        self.list_widget.blockSignals(False)
        self._save_order()

    def _on_arrange_clicked(self):
        """ตรวจสอบการกด 5 ครั้งติดกัน ก่อนเข้าโหมดจัดเรียง"""
        if self._arrange_mode:
            # ถ้าอยู่ในโหมดจัดเรียงอยู่แล้ว กดครั้งเดียวก็ออกได้เลย
            self._toggle_arrange_mode()
            return
            
        self._arrange_click_count += 1
        if self._arrange_click_count == 1:
            self._arrange_timer.start()
            
        if self._arrange_click_count >= 5:
            self._arrange_timer.stop()
            self._arrange_click_count = 0
            self._toggle_arrange_mode()

    def _reset_arrange_clicks(self):
        """รีเซ็ตจำนวนครั้งการกดถ้าเวลาหมด"""
        self._arrange_click_count = 0

    def _toggle_arrange_mode(self):
        """สลับโหมดจัดเรียงและแก้ไขชื่อ"""
        self._arrange_mode = not self._arrange_mode
        if self._arrange_mode:
            self.chk_hide_name.setVisible(True)
            self.btn_arrange.setStyleSheet("background-color: #28A745; border-radius: 8px;")
            self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            # อนุญาตให้แก้ไขชื่อได้ (ยกเว้นถ้าซ่อนชื่ออยู่)
            if not self.chk_hide_name.isChecked():
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        else:
            self.chk_hide_name.setVisible(False)
            self.btn_arrange.setStyleSheet("background-color: white; border-radius: 8px;")
            self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
            # ล็อคการแก้ไขชื่อ
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._save_order()

    def _on_hide_name_changed(self, state):
        """เมื่อติ๊กซ่อน/แสดงชื่อ"""
        is_hidden = (state == 2) # Qt.CheckState.Checked
        self.config_manager.set("hide_template_names", is_hidden)
        
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            real_name = item.data(Qt.ItemDataRole.UserRole + 2)
            if is_hidden:
                item.setText("")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                item.setText(real_name)
                if self._arrange_mode:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.list_widget.blockSignals(False)

    def _save_order(self):
        """บันทึกลำดับปัจจุบันลงไฟล์ template_order.json"""
        if self.list_widget.count() == 0:
            return
            
        order = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            path = item.data(Qt.ItemDataRole.UserRole + 1)
            name = os.path.splitext(os.path.basename(path))[0]
            order.append(name)
            
        order_path = os.path.join(self.templates_dir, "template_order.json")
        try:
            with open(order_path, "w", encoding="utf-8") as f:
                json.dump(order, f, ensure_ascii=False, indent=4)
            logger.info("บันทึกลำดับ Template สำเร็จ")
        except Exception as e:
            logger.error(f"ไม่สามารถบันทึกลำดับได้: {e}")

    def _on_item_changed(self, item: QListWidgetItem):
        """เมื่อผู้ใช้แก้ไขชื่อ Template ให้เปลี่ยนชื่อไฟล์จริงด้วย"""
        if self.chk_hide_name.isChecked():
            return
            
        new_name = item.text().strip()
        old_path = item.data(Qt.ItemDataRole.UserRole + 1)
        old_name = item.data(Qt.ItemDataRole.UserRole + 2)
        ext = os.path.splitext(old_path)[1]
        
        if not new_name or new_name == old_name:
            item.setText(old_name)
            return
            
        new_path = os.path.join(self.templates_dir, new_name + ext)
        if os.path.exists(new_path):
            QMessageBox.warning(self, "ชื่อซ้ำ", f"ชื่อ {new_name} มีอยู่แล้ว!")
            item.setText(old_name)
            return
            
        try:
            # เปลี่ยนชื่อไฟล์ภาพ
            os.rename(old_path, new_path)
            item.setData(Qt.ItemDataRole.UserRole + 1, new_path)
            item.setData(Qt.ItemDataRole.UserRole + 2, new_name)
            
            # เปลี่ยนชื่อไฟล์ json ถัามี
            old_json = os.path.join(self.templates_dir, old_name + ".json")
            new_json = os.path.join(self.templates_dir, new_name + ".json")
            if os.path.exists(old_json):
                os.rename(old_json, new_json)
                
            self._save_order()
            logger.info(f"เปลี่ยนชื่อ Template จาก {old_name} เป็น {new_name} สำเร็จ")
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถเปลี่ยนชื่อไฟล์ได้: {e}")
            item.setText(old_name)

    def _on_selection_changed(self):
        """เมื่อคลิกเลือกรายการ"""
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            item = selected_items[0]
            name = item.text()
            self.label_selected.setText(f"✅ เลือก: {name}")
            self.label_selected.setStyleSheet("color: #00E676; font-size: 13px;")
            self.btn_next.setEnabled(True)
        else:
            self.label_selected.setText("ยังไม่ได้เลือก Template")
            self.label_selected.setStyleSheet("")
            self.btn_next.setEnabled(False)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """เมื่อดับเบิ้ลคลิก ให้กด Next ทันที (ถ้าไม่ได้อยู่ในโหมดจัดเรียง)"""
        if not self._arrange_mode:
            self._on_next_clicked()

    def _on_next_clicked(self) -> None:
        """เมื่อกดปุ่ม ถัดไป"""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือก Template ก่อน")
            return

        item = selected_items[0]
        template_path = item.data(Qt.ItemDataRole.UserRole + 1)
        layout_config = item.data(Qt.ItemDataRole.UserRole)
        
        self.template_selected.emit(template_path, layout_config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_selected_template(self) -> tuple[str | None, dict | None]:
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            item = selected_items[0]
            template_path = item.data(Qt.ItemDataRole.UserRole + 1)
            layout_config = item.data(Qt.ItemDataRole.UserRole)
            return template_path, layout_config
        return None, None

    def set_templates_dir(self, path: str) -> None:
        self.templates_dir = path
        self.refresh_templates()

