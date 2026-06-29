"""
SettingWidget — หน้าตั้งค่าหลัก
==================================
- เลือกโฟลเดอร์ Export Path
- ระบุ Google Drive Folder ID
- เลือกเครื่องปริ้นเตอร์ในระบบ
- อัปโหลด/เพิ่ม Template ใหม่
"""

import os
import shutil
import logging

from PyQt6.QtCore import Qt, pyqtSignal, QSizeF, QSize
from PyQt6.QtGui import QFont, QPageSize, QPainter, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QSizePolicy,
    QScrollArea,
    QListWidget,
    QSpinBox,
)
from PyQt6.QtMultimedia import QMediaDevices, QCamera, QMediaCaptureSession
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtPrintSupport import QPrinterInfo, QPrinter
from ui.template_editor_dialog import TemplateEditorDialog
from PyQt6.QtWidgets import QCheckBox, QApplication
from config_manager import ConfigManager
from ui.raw_images_dialog import RawImagesDialog
from path_manager import get_resource_path, get_dynamic_path

logger = logging.getLogger(__name__)

class NoScrollComboBox(QComboBox):
    """QComboBox ที่ป้องกันการเลื่อนลูกกลิ้งเมาส์แล้วเปลี่ยนค่าโดยไม่ตั้งใจ"""
    def wheelEvent(self, event):
        event.ignore()

def _get_system_printers() -> list[str]:
    """ดึงรายชื่อเครื่องปริ้นเตอร์ที่ติดตั้งในระบบโดยใช้ QPrinterInfo

    Returns:
        list ของชื่อ printer หรือ list ว่างถ้าหาไม่ได้
    """
    printers: list[str] = []
    try:
        available_printers = QPrinterInfo.availablePrinters()
        printers = [p.printerName() for p in available_printers]
    except Exception as e:
        logger.error("ดึงรายชื่อ printer ไม่ได้: %s", e)

    return printers


class SettingWidget(QWidget):
    """หน้าตั้งค่าหลัก

    Signals:
        back_clicked: กดปุ่ม ← กลับ → ไปหน้า Home
        settings_saved(dict): เมื่อกดบันทึก → emit dict ของ settings ทั้งหมด
        template_added(str): เมื่อเพิ่ม template ใหม่สำเร็จ → emit path
    """

    back_clicked = pyqtSignal()
    settings_saved = pyqtSignal(dict)
    template_added = pyqtSignal(str)

    def __init__(
        self,
        templates_dir: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SettingWidget")

        if templates_dir is None:
            templates_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "assets", "templates",
            )
        self.templates_dir = templates_dir
        
        self.config_manager = ConfigManager()
        self.active_camera = None

        self._init_ui()
        self._load_printers()
        self._load_cameras()
        self._refresh_template_list()

    def _add_group_header(self, layout, icon_path: str, title: str):
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            icon_label.setPixmap(pixmap.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        icon_label.setFixedSize(24, 24)
        
        title_label = QLabel(title)
        font = title_label.font()
        font.setBold(True)
        title_label.setFont(font)
        
        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        layout.addSpacing(5)

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
        self.btn_back.clicked.connect(self._on_back_clicked)
        top_bar.addWidget(self.btn_back)

        top_bar.addStretch()

        title = QLabel("⚙  ตั้งค่า")
        title.setProperty("cssClass", "title")
        top_bar.addWidget(title)

        top_bar.addStretch()
        # Spacer ให้ title อยู่กึ่งกลาง
        spacer = QWidget()
        spacer.setFixedWidth(self.btn_back.sizeHint().width())
        top_bar.addWidget(spacer)

        root_layout.addLayout(top_bar)

        # ---------- Scroll Area ----------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 12, 0)
        content_layout.setSpacing(20)

        # ========== Group 1: General Settings ==========
        grp_general = QGroupBox("")
        general_layout = QVBoxLayout(grp_general)
        self._add_group_header(general_layout, get_resource_path(os.path.join("image", "normalSetting.png")), "การตั้งค่าทั่วไป (General)")
        
        # Full Screen Checkbox
        fs_row = QHBoxLayout()
        self.chk_fullscreen = QCheckBox("แสดงผลเต็มจอ (Full Screen) - กด F12 เพื่อสลับหน้าจอได้")
        fs_row.addWidget(self.chk_fullscreen)
        fs_row.addStretch()
        general_layout.addLayout(fs_row)
        
        # Export Path
        export_row = QHBoxLayout()
        export_label = QLabel("โฟลเดอร์เซฟรูป:")
        export_row.addWidget(export_label)
        
        self.input_export_path = QLineEdit()
        self.input_export_path.setPlaceholderText("เลือกโฟลเดอร์สำหรับเซฟรูปที่ถ่ายเสร็จ...")
        self.input_export_path.setReadOnly(True)
        export_row.addWidget(self.input_export_path, stretch=1)

        self.btn_browse_export = QPushButton(" เลือกโฟลเดอร์")
        self.btn_browse_export.setIcon(QIcon(get_resource_path(os.path.join("image", "folder.png"))))
        self.btn_browse_export.setIconSize(QSize(20, 20))
        self.btn_browse_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse_export.setFixedHeight(40)
        self.btn_browse_export.setStyleSheet("background-color: white; color: black; border-radius: 8px; font-weight: bold; padding: 0 10px;")
        self.btn_browse_export.clicked.connect(self._browse_export_path)
        export_row.addWidget(self.btn_browse_export)
        
        general_layout.addLayout(export_row)

        # View Raw Images and Clear Cache
        self.btn_view_raw = QPushButton("📸 ดูรูปดิบทั้งหมดในโฟลเดอร์ชั่วคราว")
        self.btn_view_raw.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_raw.setFixedHeight(40)
        self.btn_view_raw.setProperty("cssClass", "accent")
        self.btn_view_raw.clicked.connect(self._view_raw_images)
        general_layout.addWidget(self.btn_view_raw)

        self.btn_clear_cache = QPushButton("🗑️ ล้างแคช (รูปชั่วคราวและ Logs)")
        self.btn_clear_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache.setFixedHeight(40)
        self.btn_clear_cache.setProperty("cssClass", "danger")
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        general_layout.addWidget(self.btn_clear_cache)

        content_layout.addWidget(grp_general)

        # ========== Group 2: Google Drive ==========
        grp_gdrive = QGroupBox("")
        gdrive_layout = QVBoxLayout(grp_gdrive)
        self._add_group_header(gdrive_layout, get_resource_path(os.path.join("image", "drive.png")), "Google Drive")

        gdrive_hint = QLabel(
            "ขั้นตอนการตั้งค่า Google Drive:<br>"
            "2.1. สร้างโฟลเดอร์ใน Google Drive ของคุณเอง<br>"
            "2.2. คลิกขวาแชร์โฟลเดอร์ แล้วเพิ่มอีเมล <a href='copy:photobooth.numedia@gmail.com' style='color: #FF9800; text-decoration: none;'>photobooth.numedia@gmail.com</a> ให้เป็น Editor (ผู้แก้ไข) <i>(คลิกเพื่อคัดลอก)</i><br>"
            "2.3. นำ ID ของโฟลเดอร์ หรือ Link ของโฟลเดอร์ที่ต้องการเก็บรูป มากรอกในช่องด้านล่าง"
        )
        gdrive_hint.setProperty("cssClass", "muted")
        gdrive_hint.setWordWrap(True)
        gdrive_hint.setTextFormat(Qt.TextFormat.RichText)
        gdrive_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        gdrive_hint.linkActivated.connect(self._copy_email_to_clipboard)
        gdrive_layout.addWidget(gdrive_hint)

        gdrive_form = QHBoxLayout()
        gdrive_label = QLabel("Folder ID:")
        gdrive_label.setFixedWidth(100)
        gdrive_form.addWidget(gdrive_label)

        self.input_gdrive_id = QLineEdit()
        self.input_gdrive_id.setPlaceholderText("เช่น 1aBcDeFgHiJkLmNoPqRsTuVwXyZ...")
        gdrive_form.addWidget(self.input_gdrive_id, stretch=1)

        gdrive_layout.addLayout(gdrive_form)
        
        content_layout.addWidget(grp_gdrive)

        # ========== Group 3: Printer ==========
        grp_printer = QGroupBox("")
        printer_layout = QVBoxLayout(grp_printer)
        self._add_group_header(printer_layout, get_resource_path(os.path.join("image", "printer.png")), "เครื่องปริ้นเตอร์")

        printer_row = QHBoxLayout()
        printer_label = QLabel("เลือก Printer:")
        printer_label.setFixedWidth(100)
        printer_row.addWidget(printer_label)

        self.combo_printer = NoScrollComboBox()
        self.combo_printer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        printer_row.addWidget(self.combo_printer, stretch=1)

        self.btn_refresh_printer = QPushButton()
        self.btn_refresh_printer.setIcon(QIcon(get_resource_path(os.path.join("image", "refresh.png"))))
        self.btn_refresh_printer.setIconSize(QSize(24, 24))
        self.btn_refresh_printer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_printer.setFixedSize(40, 40)
        self.btn_refresh_printer.setStyleSheet("background-color: white; border-radius: 8px;")
        self.btn_refresh_printer.setToolTip("รีเฟรชรายชื่อ Printer")
        self.btn_refresh_printer.clicked.connect(self._load_printers)
        printer_row.addWidget(self.btn_refresh_printer)

        printer_layout.addLayout(printer_row)
        
        # Paper Size
        paper_row = QHBoxLayout()
        paper_label = QLabel("ขนาดกระดาษ (Paper Size):")
        paper_label.setFixedWidth(160)
        paper_row.addWidget(paper_label)
        
        self.combo_paper_size = NoScrollComboBox()
        self.combo_paper_size.addItems([
            "2x6 นิ้ว (Photo Strip)", 
            "4x6 นิ้ว (4R)", 
            "5x7 นิ้ว (5R)", 
            "A4", 
            "A5", 
            "A6"
        ])
        self.combo_paper_size.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        paper_row.addWidget(self.combo_paper_size, stretch=1)
        printer_layout.addLayout(paper_row)
        
        # Media Type (ชนิดกระดาษ)
        media_row = QHBoxLayout()
        media_label = QLabel("ชนิดเนื้อกระดาษ (Media Type):")
        media_label.setFixedWidth(160)
        media_row.addWidget(media_label)
        
        self.combo_media_type = NoScrollComboBox()
        self.combo_media_type.addItems([
            "กระดาษธรรมดา",
            "Matte Photo Paper",
            "Photo Paper Pro Luster",
            "กระดาษการ์ด",
            "กระดาษภาพถ่ายเคลือบมันพิเศษ II",
            "กระดาษเคลือบมันภาพถ่าย"
        ])
        self.combo_media_type.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        media_row.addWidget(self.combo_media_type, stretch=1)
        printer_layout.addLayout(media_row)
        
        # Copies
        copies_row = QHBoxLayout()
        copies_label = QLabel("จำนวนแผ่นที่พิมพ์ (Copies):")
        copies_label.setFixedWidth(160)
        copies_row.addWidget(copies_label)
        
        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 10)
        self.spin_copies.setValue(1)
        self.spin_copies.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        copies_row.addWidget(self.spin_copies, stretch=1)
        printer_layout.addLayout(copies_row)
        
        # Test Print Button
        test_print_row = QHBoxLayout()
        test_print_row.addStretch()
        self.btn_test_print = QPushButton("🖨️ ทดสอบพิมพ์ (Test Print)")
        self.btn_test_print.setProperty("cssClass", "normal")
        self.btn_test_print.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_print.clicked.connect(self._test_print)
        test_print_row.addWidget(self.btn_test_print)
        printer_layout.addLayout(test_print_row)

        self.label_printer_status = QLabel("")
        self.label_printer_status.setProperty("cssClass", "muted")
        printer_layout.addWidget(self.label_printer_status)

        content_layout.addWidget(grp_printer)

        # ========== Group 4: Camera ==========
        grp_camera = QGroupBox("")
        camera_layout = QVBoxLayout(grp_camera)
        self._add_group_header(camera_layout, get_resource_path(os.path.join("image", "camera.png")), "กล้องถ่ายภาพ (Webcam)")

        camera_row = QHBoxLayout()
        camera_label = QLabel("เลือกกล้อง:")
        camera_label.setFixedWidth(100)
        camera_row.addWidget(camera_label)

        self.combo_camera = NoScrollComboBox()
        self.combo_camera.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.combo_camera.currentIndexChanged.connect(self._on_camera_changed)
        camera_row.addWidget(self.combo_camera, stretch=1)

        self.btn_refresh_camera = QPushButton()
        self.btn_refresh_camera.setIcon(QIcon(get_resource_path(os.path.join("image", "refresh.png"))))
        self.btn_refresh_camera.setIconSize(QSize(24, 24))
        self.btn_refresh_camera.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_camera.setFixedSize(40, 40)
        self.btn_refresh_camera.setStyleSheet("background-color: white; border-radius: 8px;")
        self.btn_refresh_camera.setToolTip("รีเฟรชรายชื่อกล้อง")
        self.btn_refresh_camera.clicked.connect(self._load_cameras)
        camera_row.addWidget(self.btn_refresh_camera)

        camera_layout.addLayout(camera_row)

        self.label_camera_status = QLabel("")
        self.label_camera_status.setProperty("cssClass", "muted")
        camera_layout.addWidget(self.label_camera_status)
        
        # เพิ่ม Video Widget สำหรับ Preview กล้อง
        self.video_widget = QVideoWidget()
        self.video_widget.setFixedSize(320, 240)
        self.video_widget.setStyleSheet("background-color: black; border-radius: 8px;")
        
        self.camera_session = QMediaCaptureSession()
        self.camera_session.setVideoOutput(self.video_widget)

        preview_row = QHBoxLayout()
        preview_row.addWidget(self.video_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        camera_layout.addLayout(preview_row)

        content_layout.addWidget(grp_camera)

        # ========== Group 5: Template Upload ==========
        grp_template = QGroupBox("")
        template_layout = QVBoxLayout(grp_template)
        self._add_group_header(template_layout, get_resource_path(os.path.join("image", "template.png")), "จัดการ Template")

        template_hint = QLabel(
            f"โฟลเดอร์เก็บ Template: {self.templates_dir}\n"
            "รองรับไฟล์ .png, .jpg, .jpeg — แนะนำ PNG พื้นโปร่งใส\n"
            "วาง .json ชื่อเดียวกัน (เช่น frame.json) คู่กับรูปเพื่อกำหนด layout"
        )
        template_hint.setProperty("cssClass", "muted")
        template_hint.setWordWrap(True)
        template_layout.addWidget(template_hint)

        template_btn_row = QHBoxLayout()

        self.btn_add_template = QPushButton("➕  เพิ่ม Template ใหม่")
        self.btn_add_template.setProperty("cssClass", "accent")
        self.btn_add_template.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_template.setFixedHeight(44)
        self.btn_add_template.clicked.connect(self._add_template)
        template_btn_row.addWidget(self.btn_add_template)

        self.btn_open_template_dir = QPushButton("📂  เปิดโฟลเดอร์ Template")
        self.btn_open_template_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_template_dir.setFixedHeight(44)
        self.btn_open_template_dir.clicked.connect(self._open_templates_dir)
        template_btn_row.addWidget(self.btn_open_template_dir)

        template_btn_row.addStretch()
        template_layout.addLayout(template_btn_row)

        # รายการ Template ที่มีอยู่
        self.list_templates = QListWidget()
        self.list_templates.setFixedHeight(150)
        self.list_templates.setStyleSheet("""
            QListWidget {
                background-color: #242438;
                border: 1px solid #353550;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #353550;
            }
            QListWidget::item:selected {
                background-color: #00CEC9;
                color: black;
            }
        """)
        
        # เพิ่มปุ่ม แก้ไข/ลบ ใต้ลิสต์
        manage_btn_row = QHBoxLayout()
        self.btn_edit_template = QPushButton("✏️ แก้ไข (Edit)")
        self.btn_edit_template.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_template.clicked.connect(self._edit_selected_template)
        manage_btn_row.addWidget(self.btn_edit_template)
        
        self.btn_delete_template = QPushButton("🗑 ลบ (Delete)")
        self.btn_delete_template.setProperty("cssClass", "danger")
        self.btn_delete_template.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_template.clicked.connect(self._delete_selected_template)
        manage_btn_row.addWidget(self.btn_delete_template)
        manage_btn_row.addStretch()

        template_layout.addWidget(self.list_templates)
        template_layout.addLayout(manage_btn_row)

        content_layout.addWidget(grp_template)

        # Spacer ด้านล่าง
        content_layout.addStretch()

        scroll.setWidget(scroll_content)
        root_layout.addWidget(scroll, stretch=1)

        # ---------- Bottom Bar (ปุ่มบันทึก) ----------
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        self.btn_save = QPushButton("💾  บันทึกการตั้งค่า")
        self.btn_save.setProperty("cssClass", "primary")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setFixedSize(200, 48)
        save_font = QFont()
        save_font.setPointSize(14)
        save_font.setBold(True)
        self.btn_save.setFont(save_font)
        self.btn_save.clicked.connect(self._on_save_clicked)
        bottom_bar.addWidget(self.btn_save)

        root_layout.addLayout(bottom_bar)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse_export_path(self) -> None:
        """เปิด Dialog เลือกโฟลเดอร์สำหรับเซฟรูปรวม"""
        directory = QFileDialog.getExistingDirectory(
            self, "เลือกโฟลเดอร์เซฟรูป", self.input_export_path.text() or ""
        )
        if directory:
            self.input_export_path.setText(directory)

    def _copy_email_to_clipboard(self, link: str) -> None:
        """คัดลอกอีเมลลง Clipboard เมื่อกดที่ลิงก์"""
        if link.startswith("copy:"):
            email = link.split("copy:")[1]
            QApplication.clipboard().setText(email)
            QMessageBox.information(self, "สำเร็จ", f"คัดลอกอีเมล {email} แล้ว!\nนำไปวางในช่องเพิ่มสิทธิ์ได้เลย")

    def _view_raw_images(self) -> None:
        """เปิดหน้าต่างดูรูปดิบทั้งหมด"""
        temp_dir = get_dynamic_path(".NUMediaBooth_Temp")
        
        dialog = RawImagesDialog(temp_dir, self)
        dialog.exec()

    def _clear_cache(self) -> None:
        """ล้างรูปภาพชั่วคราวและไฟล์ log เก่า"""
        temp_dir = get_dynamic_path(".NUMediaBooth_Temp")
        logs_dir = get_dynamic_path("logs")
        crash_dir = get_dynamic_path(os.path.join("logs", "crash_dumps"))
        
        deleted_temp = 0
        deleted_logs = 0
        deleted_crash = 0
        
        # ลบรูปใน temp_dir
        if os.path.exists(temp_dir):
            for f in os.listdir(temp_dir):
                fpath = os.path.join(temp_dir, f)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                        deleted_temp += 1
                except Exception as e:
                    logger.warning(f"Cannot delete {fpath}: {e}")
                    
        # ลบรูปใน crash_dumps
        if os.path.exists(crash_dir):
            for f in os.listdir(crash_dir):
                fpath = os.path.join(crash_dir, f)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                        deleted_crash += 1
                except Exception as e:
                    logger.warning(f"Cannot delete crash dump {fpath}: {e}")
                    
        # ลบไฟล์ log ยกเว้นไฟล์ที่ใช้งานอยู่
        if os.path.exists(logs_dir):
            for f in os.listdir(logs_dir):
                if f.endswith(".log"):
                    fpath = os.path.join(logs_dir, f)
                    try:
                        os.remove(fpath)
                        deleted_logs += 1
                    except Exception as e:
                        # ไฟล์ที่กำลังใช้งานอยู่ (เช่น appError.log หรือ app.log) ลบไม่ได้
                        # เลยจะเคลียร์ข้อมูลข้างในไฟล์แทน (Truncate)
                        try:
                            # วิธีนี้จะล้างข้อมูลข้างในให้ไฟล์ว่างเปล่า
                            for handler in logging.root.handlers:
                                if isinstance(handler, logging.FileHandler) and handler.baseFilename == os.path.abspath(fpath):
                                    handler.stream.seek(0)
                                    handler.stream.truncate()
                                    deleted_logs += 1
                                    break
                        except Exception:
                            pass
                        
        QMessageBox.information(self, "ล้างแคชสำเร็จ", f"ลบไฟล์รูปชั่วคราวไป {deleted_temp} ไฟล์\nลบรูป Crash Dump ไป {deleted_crash} ไฟล์\nเคลียร์ไฟล์ Log ไป {deleted_logs} ไฟล์")



    def _load_printers(self) -> None:
        """โหลดรายชื่อเครื่องปริ้นเตอร์ลง ComboBox"""
        self.combo_printer.clear()

        printers = _get_system_printers()

        if printers:
            self.combo_printer.addItems(printers)
            self.label_printer_status.setText(f"พบ {len(printers)} เครื่องปริ้นเตอร์")
            self.label_printer_status.setStyleSheet("color: #00E676;")
        else:
            self.combo_printer.addItem("— ไม่พบเครื่องปริ้นเตอร์ —")
            self.label_printer_status.setText(
                "ไม่พบ Printer (กรุณาติดตั้ง Printer ก่อน)"
            )
            self.label_printer_status.setStyleSheet("color: #FF5252;")

        logger.info("โหลด printer: %s", printers)

    def _load_cameras(self) -> None:
        """โหลดรายชื่อกล้อง Webcam ลง ComboBox"""
        self.combo_camera.clear()
        
        cameras = QMediaDevices.videoInputs()
        if cameras:
            for cam in cameras:
                # เซฟชื่อกล้องและ ID ไว้
                self.combo_camera.addItem(cam.description(), cam.id())
            self.label_camera_status.setText(f"พบกล้อง {len(cameras)} ตัว")
            self.label_camera_status.setStyleSheet("color: #00E676;")
        else:
            self.combo_camera.addItem("— ไม่พบกล้อง Webcam —")
            self.label_camera_status.setText("ไม่พบกล้อง (ตรวจสอบการเชื่อมต่อ USB)")
            self.label_camera_status.setStyleSheet("color: #FF5252;")
            
        logger.info("โหลดกล้อง Webcam พบ %d ตัว", len(cameras))
        
        # Trigger update
        if cameras:
            self._on_camera_changed(self.combo_camera.currentIndex())

    def _on_camera_changed(self, index: int):
        """เมื่อเปลี่ยนกล้อง ให้รัน Preview ใหม่"""
        self._stop_camera()
            
        cameras = QMediaDevices.videoInputs()
        if 0 <= index < len(cameras):
            cam_device = cameras[index]
            self.active_camera = QCamera(cam_device)
            self.camera_session.setCamera(self.active_camera)
            self.active_camera.start()
            
    def _stop_camera(self):
        """หยุดกล้องเพื่อคืนทรัพยากรให้หน้าอื่น"""
        if self.active_camera:
            self.active_camera.stop()
            self.active_camera = None
            
    def hideEvent(self, event):
        """เมื่อซ่อนหน้าต่างนี้ (ไปหน้าอื่น) ให้หยุดกล้อง"""
        self._stop_camera()
        super().hideEvent(event)
        
    def showEvent(self, event):
        """เมื่อแสดงหน้าต่างนี้ ให้เปิดกล้อง"""
        super().showEvent(event)
        if self.combo_camera.count() > 0:
            self._on_camera_changed(self.combo_camera.currentIndex())

    def _add_template(self) -> None:
        """เปิด dialog เลือกไฟล์รูป แล้วเข้าโหมด Editor"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "เลือกไฟล์ Template (รูปกรอบ)",
            os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )

        if not files:
            return

        templates_dir = get_resource_path(os.path.join("assets", "templates"))
        
        # เปิดหน้าจอ Editor เพื่อลากวาง
        for f in files:
            editor = TemplateEditorDialog(f, templates_dir, self)
            if editor.exec():
                # ถ้าเซฟสำเร็จ จะเกิดอะไรขึ้นในนั้นเรียบร้อยแล้ว
                logger.info("เพิ่ม Template สำเร็จ: %s", f)
            
        # รีเฟรชลิสต์และส่งสัญญาณให้อัปเดต UI 
        self._refresh_template_list()
        self.template_added.emit(templates_dir)

    def _open_templates_dir(self) -> None:
        """เปิดโฟลเดอร์ templates ใน File Explorer"""
        os.makedirs(self.templates_dir, exist_ok=True)
        os.startfile(self.templates_dir)  # Windows only

    def _on_save_clicked(self) -> None:
        """บันทึกการตั้งค่า → emit settings dict"""
        settings = self.get_settings()

        # Validate
        if not settings["export_path"]:
            QMessageBox.warning(
                self, "แจ้งเตือน", "กรุณาเลือกโฟลเดอร์สำหรับเซฟรูป"
            )
            return

        self._stop_camera()
        self.settings_saved.emit(settings)
        logger.info("บันทึกการตั้งค่า: %s", settings)

        QMessageBox.information(self, "สำเร็จ", "บันทึกการตั้งค่าเรียบร้อย ✅")

    def _test_print(self) -> None:
        """ฟังก์ชันทดสอบการพิมพ์"""
        printer_name = self.combo_printer.currentText()
        if not printer_name or printer_name.startswith("—"):
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือกเครื่องปริ้นเตอร์ก่อน")
            return
            
        printer_info = QPrinterInfo.printerInfo(printer_name)
        if not printer_info.isNull():
            printer = QPrinter(printer_info)
            # ตั้งค่า Paper Size จากตัวเลือก
            paper_text = self.combo_paper_size.currentText()
            if "A4" in paper_text:
                printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            elif "A5" in paper_text:
                printer.setPageSize(QPageSize(QPageSize.PageSizeId.A5))
            elif "A6" in paper_text:
                printer.setPageSize(QPageSize(QPageSize.PageSizeId.A6))
            elif "2x6" in paper_text:
                printer.setPageSize(QPageSize(QSizeF(2, 6), QPageSize.Unit.Inch))
            elif "4x6" in paper_text:
                printer.setPageSize(QPageSize(QSizeF(4, 6), QPageSize.Unit.Inch))
            elif "5x7" in paper_text:
                printer.setPageSize(QPageSize(QSizeF(5, 7), QPageSize.Unit.Inch))
            else:
                printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
                
            printer.setCopyCount(self.spin_copies.value())
            
            # เปิด QPainter เพื่อเขียนข้อความทดสอบลงปริ้นเตอร์
            painter = QPainter()
            if painter.begin(printer):
                font = QFont("Arial", 20, QFont.Weight.Bold)
                painter.setFont(font)
                painter.drawText(100, 100, "NUMedia Booth - Test Print")
                painter.drawText(100, 150, f"Printer: {printer_name}")
                painter.drawText(100, 200, f"Paper Size: {paper_text}")
                painter.drawText(100, 250, f"Media: {self.combo_media_type.currentText()}")
                painter.drawText(100, 300, f"Copies: {self.spin_copies.value()}")
                painter.end()
                QMessageBox.information(self, "สำเร็จ", f"ส่งคำสั่งทดสอบพิมพ์ไปที่ {printer_name} แล้ว!")
            else:
                QMessageBox.critical(self, "ผิดพลาด", "ไม่สามารถเริ่มงานพิมพ์ได้")
        else:
            QMessageBox.warning(self, "ข้อผิดพลาด", f"ไม่พบข้อมูลของเครื่องปริ้นเตอร์: {printer_name}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _on_back_clicked(self):
        self._stop_camera()
        self.back_clicked.emit()

    def _load_settings(self) -> None:
        """ดึงค่าจาก Config Manager มาแสดงบน UI"""
        self.chk_fullscreen.setChecked(self.config_manager.get("fullscreen", False))
        self.input_export_path.setText(self.config_manager.get("export_path", ""))
        self.input_gdrive_id.setText(self.config_manager.get("gdrive_folder_id", ""))
        
        printer_name = self.config_manager.get("printer_name", "")
        if printer_name and printer_name != "— ไม่มี Printer ที่พร้อมใช้งาน —":
            idx = self.combo_printer.findText(printer_name)
            if idx >= 0:
                self.combo_printer.setCurrentIndex(idx)
                
        paper_size = self.config_manager.get("paper_size", "A4")
        idx_paper = self.combo_paper_size.findText(paper_size)
        if idx_paper >= 0:
            self.combo_paper_size.setCurrentIndex(idx_paper)
            
        media_type = self.config_manager.get("media_type", "กระดาษธรรมดา")
        idx_media = self.combo_media_type.findText(media_type)
        if idx_media >= 0:
            self.combo_media_type.setCurrentIndex(idx_media)
            
        copies = self.config_manager.get("print_copies", 1)
        self.spin_copies.setValue(copies)
                
        camera_name = self.config_manager.get("camera_name", "")
        if camera_name and camera_name != "— ไม่พบกล้อง Webcam —":
            idx = self.combo_camera.findText(camera_name)
            if idx >= 0:
                self.combo_camera.setCurrentIndex(idx)

    def get_settings(self) -> dict:
        """ดึงค่า settings ปัจจุบันทั้งหมด

        Returns:
            dict ที่มี key: export_path, gdrive_folder_id, printer_name
        """
        printer_name = self.combo_printer.currentText()
        if printer_name.startswith("—"):
            printer_name = ""
            
        camera_name = self.combo_camera.currentText()
        if camera_name.startswith("—"):
            camera_name = ""

        # การดักจับ ID จากลิงก์ Google Drive
        import re
        gdrive_id_text = self.input_gdrive_id.text().strip()
        if "drive.google.com" in gdrive_id_text:
            match = re.search(r'/folders/([A-Za-z0-9_-]+)', gdrive_id_text)
            if match:
                gdrive_id_text = match.group(1)
            else:
                match = re.search(r'id=([A-Za-z0-9_-]+)', gdrive_id_text)
                if match:
                    gdrive_id_text = match.group(1)
            # อัปเดตในช่อง input เพื่อให้ผู้ใช้เห็นว่าโดนตัดเหลือแค่ ID
            self.input_gdrive_id.setText(gdrive_id_text)

        return {
            "fullscreen": self.chk_fullscreen.isChecked(),
            "export_path": self.input_export_path.text().strip(),
            "gdrive_folder_id": gdrive_id_text,
            "printer_name": printer_name,
            "paper_size": self.combo_paper_size.currentText(),
            "media_type": self.combo_media_type.currentText(),
            "print_copies": self.spin_copies.value(),
            "camera_name": camera_name,
        }

    def set_settings(self, settings: dict) -> None:
        """ใส่ค่า settings จาก dict (ใช้ตอนโหลดค่าจาก config file)

        Args:
            settings: dict ที่มี key ตรงกับ get_settings()
        """
        if "fullscreen" in settings:
            self.chk_fullscreen.setChecked(settings["fullscreen"])

        if "export_path" in settings:
            self.input_export_path.setText(settings["export_path"])

        if "gdrive_folder_id" in settings:
            self.input_gdrive_id.setText(settings["gdrive_folder_id"])

        if "printer_name" in settings:
            idx = self.combo_printer.findText(settings["printer_name"])
            if idx >= 0:
                self.combo_printer.setCurrentIndex(idx)
                
        if "paper_size" in settings:
            idx = self.combo_paper_size.findText(settings["paper_size"])
            if idx >= 0:
                self.combo_paper_size.setCurrentIndex(idx)
                
        if "media_type" in settings:
            idx = self.combo_media_type.findText(settings["media_type"])
            if idx >= 0:
                self.combo_media_type.setCurrentIndex(idx)
                
        if "print_copies" in settings:
            self.spin_copies.setValue(settings["print_copies"])
                
        if "camera_name" in settings:
            idx = self.combo_camera.findText(settings["camera_name"])
            if idx >= 0:
                self.combo_camera.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Template Management
    # ------------------------------------------------------------------
    def _refresh_template_list(self) -> None:
        self.list_templates.clear()
        if not os.path.exists(self.templates_dir):
            return
            
        for f in os.listdir(self.templates_dir):
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                self.list_templates.addItem(f)

    def _edit_selected_template(self) -> None:
        selected = self.list_templates.currentItem()
        if not selected:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือก Template จากรายการก่อน")
            return
            
        filename = selected.text()
        filepath = os.path.join(self.templates_dir, filename)
        
        editor = TemplateEditorDialog(filepath, self.templates_dir, self)
        if editor.exec():
            logger.info("แก้ไข Template สำเร็จ: %s", filename)
            self.template_added.emit(self.templates_dir)

    def _delete_selected_template(self) -> None:
        selected = self.list_templates.currentItem()
        if not selected:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือก Template จากรายการก่อน")
            return
            
        filename = selected.text()
        filepath = os.path.join(self.templates_dir, filename)
        
        reply = QMessageBox.question(
            self, "ยืนยันการลบ", f"คุณต้องการลบ '{filename}' และค่า Layout ทั้งหมดใช่หรือไม่?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # ลบไฟล์ภาพ
                if os.path.exists(filepath):
                    os.remove(filepath)
                # ลบไฟล์ JSON
                basename, _ = os.path.splitext(filename)
                json_path = os.path.join(self.templates_dir, f"{basename}.json")
                if os.path.exists(json_path):
                    os.remove(json_path)
                    
                self._refresh_template_list()
                self.template_added.emit(self.templates_dir)
                QMessageBox.information(self, "สำเร็จ", "ลบ Template เรียบร้อยแล้ว")
            except Exception as e:
                logger.error("ลบ Template ไม่สำเร็จ: %s", e)
                QMessageBox.critical(self, "ผิดพลาด", f"ไม่สามารถลบไฟล์ได้: {e}")
