"""
MainWindow — หน้าต่างหลักที่ใช้ QStackedWidget สลับหน้า
=========================================================
จัดการ Navigation ระหว่าง 3 หน้า:
    0 = HomeWidget
    1 = TemplateSelectWidget
    2 = SettingWidget

Signal จากแต่ละ Widget จะถูก connect ไว้ที่นี่
เพื่อให้ MainWindow เป็น "ผู้ควบคุม" การสลับหน้าจอเพียงจุดเดียว
"""

import os
import logging

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
    QMessageBox,
)

from image_composer import merge_photobooth
from config_manager import ConfigManager
from printer_module import silent_print_photo
from printer_monitor import check_printer_status
from gdrive_module import GoogleDriveUploadThread

from ui.home_widget import HomeWidget
from ui.template_select_widget import TemplateSelectWidget
from ui.setting_widget import SettingWidget
from ui.capture_widget import CameraCaptureWidget
from ui.finish_widget import FinishWidget
from ui.printer_alert_dialog import PrinterAlertDialog
from ui.styles import GLOBAL_STYLESHEET
from path_manager import get_resource_path

logger = logging.getLogger(__name__)


# ==================== Page Index Constants ====================
PAGE_HOME = 0
PAGE_TEMPLATE_SELECT = 1
PAGE_SETTINGS = 2
PAGE_CAPTURE = 3
PAGE_FINISH = 4


class MainWindow(QMainWindow):
    """หน้าต่างหลักของ NUMediaBooth

    ใช้ QStackedWidget ในการสลับระหว่าง 3 หน้า:
        - Home (index 0)
        - Template Select (index 1)
        - Settings (index 2)

    Attributes:
        home_widget: หน้า Home
        template_widget: หน้าเลือก Template
        setting_widget: หน้าตั้งค่า
        stacked: QStackedWidget สำหรับสลับหน้า
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("NU Media Booth — Photobooth")
        self.setMinimumSize(1024, 700)
        self.resize(1200, 800)

        # ตั้ง stylesheet ทั้งแอป
        self.setStyleSheet(GLOBAL_STYLESHEET)

        logger.info("Initializing MainWindow")

        self._templates_dir = get_resource_path(os.path.join("assets", "templates"))
        
        # โหลดการตั้งค่า
        self.config_manager = ConfigManager()
        
        if self.config_manager.get("fullscreen", False):
            self.showFullScreen()

        self._init_pages()
        
        # นำการตั้งค่าไปใส่ใน SettingWidget
        self.setting_widget.set_settings(self.config_manager.get_all())
        
        # ส่งรหัสผ่านจาก config ให้ HomeWidget เผื่อต้องการเปลี่ยน
        self.home_widget.admin_password = self.config_manager.get("admin_password", "1234")

        self._connect_signals()

        # เริ่มที่หน้า Home
        self.navigate_to(PAGE_HOME)
        logger.info("MainWindow พร้อมใช้งาน")

    # ------------------------------------------------------------------
    # Page Initialization
    # ------------------------------------------------------------------

    def _init_pages(self) -> None:
        """สร้าง QStackedWidget และเพิ่ม 3 หน้าเข้าไป"""
        self.stacked = QStackedWidget()
        self.setCentralWidget(self.stacked)

        # Page 0: Home
        self.home_widget = HomeWidget()
        self.stacked.addWidget(self.home_widget)  # index 0

        # Page 1: Template Select
        self.template_widget = TemplateSelectWidget(
            templates_dir=self._templates_dir,
        )
        self.stacked.addWidget(self.template_widget)  # index 1

        # Page 2: Settings
        self.setting_widget = SettingWidget(
            templates_dir=self._templates_dir,
        )
        self.stacked.addWidget(self.setting_widget)  # index 2

        # Page 3: Capture
        self.capture_widget = CameraCaptureWidget()
        self.stacked.addWidget(self.capture_widget)  # index 3

        # Page 4: Finish
        self.finish_widget = FinishWidget(self)
        self.stacked.addWidget(self.finish_widget)  # index 4

    # ------------------------------------------------------------------
    # Signal Connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """เชื่อม Signal จากทุก Widget กับ navigation logic"""

        # ----- Home -----
        self.home_widget.start_clicked.connect(
            lambda: self.navigate_to(PAGE_TEMPLATE_SELECT)
        )
        self.home_widget.settings_clicked.connect(
            lambda: self.navigate_to(PAGE_SETTINGS)
        )
        self.home_widget.logo_clicked.connect(
            self._on_home_logo_clicked
        )

        # ----- Template Select -----
        self.template_widget.back_clicked.connect(
            lambda: self.navigate_to(PAGE_HOME)
        )
        self.template_widget.template_selected.connect(
            self._on_template_selected
        )

        # ----- Settings -----
        self.setting_widget.back_clicked.connect(
            lambda: self.navigate_to(PAGE_HOME)
        )
        self.setting_widget.settings_saved.connect(
            self._on_settings_saved
        )
        self.setting_widget.template_added.connect(
            self._on_template_added
        )

        # ----- Capture -----
        self.capture_widget.cancel_clicked.connect(
            lambda: self.navigate_to(PAGE_TEMPLATE_SELECT)
        )
        self.capture_widget.capture_finished.connect(
            self._on_capture_finished
        )
        
        # ----- Finish -----
        self.finish_widget.back_home_clicked.connect(
            lambda: self.navigate_to(PAGE_HOME)
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate_to(self, page_index: int) -> None:
        """สลับไปหน้าที่กำหนด

        Args:
            page_index: ใช้ค่า PAGE_HOME, PAGE_TEMPLATE_SELECT, PAGE_SETTINGS
        """
        if page_index < 0 or page_index >= self.stacked.count():
            logger.warning("หน้า index %d ไม่มีอยู่", page_index)
            return

        # Refresh data เมื่อเข้าหน้า
        if page_index == PAGE_TEMPLATE_SELECT:
            self.template_widget.refresh_templates()

        self.stacked.setCurrentIndex(page_index)

        page_names = {
            PAGE_HOME: "Home",
            PAGE_TEMPLATE_SELECT: "Template Select",
            PAGE_SETTINGS: "Settings",
            PAGE_CAPTURE: "Capture",
            PAGE_FINISH: "Finish",
        }
        logger.info("สลับไปหน้า: %s (index %d)", page_names.get(page_index), page_index)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    
    def keyPressEvent(self, event):
        """กด F12 เพื่อสลับหน้าจอ Fullscreen"""
        if event.key() == Qt.Key.Key_F12:
            self._toggle_fullscreen()
        super().keyPressEvent(event)
        
    def _toggle_fullscreen(self):
        is_fullscreen = not self.isFullScreen()
        if is_fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
        self.config_manager.set("fullscreen", is_fullscreen)
        self.setting_widget.chk_fullscreen.setChecked(is_fullscreen)

    def _on_home_logo_clicked(self) -> None:
        """เมื่อกดโลโก้ในหน้าแรก ให้ข้ามไปหน้า QR Code ทันที (สำหรับคนที่ต้องการสแกนย้อนหลัง)"""
        gdrive_folder_id = self.config_manager.get("gdrive_folder_id", "")
        self.finish_widget.setup_finish(gdrive_folder_id)
        self.navigate_to(PAGE_FINISH)

    def _on_template_selected(self, template_path: str, layout_config) -> None:
        """เมื่อเลือก Template แล้วกด Next"""
        logger.info("เลือก Template: %s", template_path)
        logger.info("Layout Config: %s", layout_config)

        # เก็บ path template เอาไว้ไปใช้ตอนรวมภาพ
        self._current_template_path = template_path
        self._current_layout_config = layout_config

        total_photos = 1
        if layout_config and "total_photos" in layout_config:
            total_photos = layout_config["total_photos"]

        # ตั้งค่าจำนวนรูปที่จะถ่าย
        camera_name = self.config_manager.get("camera_name", "")
        self.capture_widget.setup_capture(
            total_photos=total_photos, 
            countdown_seconds=3,
            camera_name=camera_name,
            template_path=self._current_template_path,
            layout_config=self._current_layout_config
        )
        self.navigate_to(PAGE_CAPTURE)

    def _on_capture_finished(self, taken_photos: list[str]) -> None:
        """เมื่อถ่ายภาพครบทุกรูป
        
        Args:
            taken_photos: list ของ path รูปภาพที่ถ่ายเสร็จ
        """
        logger.info("ถ่ายภาพครบแล้ว: %s", taken_photos)
        
        if not hasattr(self, '_current_template_path') or not self._current_template_path:
            logger.error("ไม่มีข้อมูล Template ปัจจุบัน")
            QMessageBox.critical(self, "ข้อผิดพลาด", "ไม่พบข้อมูล Template กรุณากลับไปเลือกใหม่")
            self.navigate_to(PAGE_HOME)
            return
            
        if not hasattr(self, '_current_layout_config') or not self._current_layout_config:
            logger.error("ไม่มีข้อมูล Layout Config")
            QMessageBox.critical(self, "ข้อผิดพลาด", "ไม่พบข้อมูล Layout Config สำหรับ Template นี้")
            self.navigate_to(PAGE_HOME)
            return

        # ดึงโฟลเดอร์สำหรับ Export จาก Config
        export_dir = self.config_manager.get("export_path", "")
        
        if not export_dir:
            # ใช้ default ถ้าไม่ได้ตั้งค่า
            export_dir = os.path.join(os.path.expanduser("~"), "Pictures", "NUMediaBooth_Export")
            
        try:
            # 5. ส่ง List ของ Path รูปภาพที่ถ่ายเสร็จทั้งหมดไปยังฟังก์ชันรวมภาพในเฟส 1
            output_path = merge_photobooth(
                template_image_path=self._current_template_path,
                photo_paths=taken_photos,
                layout_config=self._current_layout_config,
                output_dir=export_dir
            )
            
            logger.info("รวมภาพเสร็จสิ้น! เซฟไว้ที่: %s", output_path)
            
            # --- 6. ส่งพิมพ์อัตโนมัติ (Silent Print) ---
            printer_name = self.config_manager.get("printer_name", "")
            if printer_name:
                # ลูปเช็คสถานะปริ้นเตอร์
                while True:
                    is_ok, err_msg = check_printer_status(printer_name)
                    if is_ok:
                        logger.info("สถานะปริ้นเตอร์ปกติ ส่งรูปภาพไปพิมพ์ที่: %s", printer_name)
                        success = silent_print_photo(output_path, self.config_manager.get_all())
                        if not success:
                            logger.warning("ไม่สามารถส่งข้อมูลไปปริ้นเตอร์ได้")
                        break
                    else:
                        # แสดงหน้าต่างแจ้งเตือนปริ้นเตอร์
                        alert_dialog = PrinterAlertDialog(err_msg, self)
                        result = alert_dialog.exec()
                        if result == QDialog.DialogCode.Rejected:
                            # ผู้ใช้กด Skip
                            logger.info("ผู้ใช้เลือกข้ามการพิมพ์")
                            break
                        # ถ้ากด Retry ก็จะวนลูปกลับไปเช็คสถานะใหม่
                    
            # --- 7. อัปโหลดไป Google Drive ---
            gdrive_folder_id = self.config_manager.get("gdrive_folder_id", "")
            
            if gdrive_folder_id:
                # เก็บค่าไว้เผื่อกด Retry
                self.last_upload_path = output_path
                self.last_folder_id = gdrive_folder_id
                self._start_gdrive_upload(output_path, gdrive_folder_id)
                
            # ไปหน้า Finish และส่ง folder_id ให้ไปเจน QR Code
            self.navigate_to(PAGE_FINISH)
            self.finish_widget.setup_finish(gdrive_folder_id)
            
        except Exception as e:
            logger.error("เกิดข้อผิดพลาดในการรวมภาพ: %s", e)
            QMessageBox.critical(self, "ข้อผิดพลาดในการรวมภาพ", str(e))
            self.navigate_to(PAGE_HOME)

    # ------------------------------------------------------------------
    # Upload Callbacks
    # ------------------------------------------------------------------
    def _start_gdrive_upload(self, file_path: str, folder_id: str) -> None:
        """เริ่มกระบวนการอัปโหลดไฟล์ไป GDrive"""
        self.uploader_thread = GoogleDriveUploadThread(
            file_path=file_path,
            folder_id=folder_id
        )
        self.uploader_thread.upload_success.connect(self._on_upload_success)
        self.uploader_thread.upload_failed.connect(self._on_upload_failed)
        self.uploader_thread.start()
        logger.info("กำลังอัปโหลดไฟล์ไปที่ Google Drive ในเบื้องหลัง...")

    def _on_upload_success(self, file_url: str) -> None:
        """ทำงานเมื่อ Google Drive อัปโหลดเสร็จสมบูรณ์"""
        logger.info("อัปโหลดสำเร็จแล้วลิงก์คือ: %s", file_url)
        # ไม่แสดง popup แจ้งเตือนแล้ว เพราะจะรบกวนหน้า Finish

    def _on_upload_failed(self, error_msg: str) -> None:
        """ทำงานเมื่อ Google Drive อัปโหลดไม่สำเร็จ"""
        logger.error("อัปโหลดพลาด: %s", error_msg)
        
        reply = QMessageBox.warning(
            self,
            "⚠️ การอัปโหลดไม่สำเร็จ",
            "การอัปโหลดไม่สำเร็จ โปรดตรวจสอบอินเทอร์เน็ต\nคุณต้องการลองใหม่อีกครั้งหรือไม่?",
            QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Retry
        )
        
        if reply == QMessageBox.StandardButton.Retry:
            logger.info("พยายามอัปโหลดไฟล์อีกครั้ง...")
            if hasattr(self, 'last_upload_path') and hasattr(self, 'last_folder_id'):
                self._start_gdrive_upload(self.last_upload_path, self.last_folder_id)
            else:
                logger.error("ไม่พบข้อมูลไฟล์ล่าสุดสำหรับ Retry")

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _on_settings_saved(self, settings: dict) -> None:
        """เมื่อบันทึก Settings
        Args:
            settings: dict จาก SettingWidget.get_settings()
        """
        logger.info("Settings saved: %s", settings)
        
        # บันทึกลงไฟล์ config.json
        self.config_manager.update(settings)
        
        # ปรับหน้าจอตามที่ตั้ง
        if settings.get("fullscreen", False):
            self.showFullScreen()
        else:
            self.showNormal()

    def _on_template_added(self, templates_dir: str) -> None:
        """เมื่อเพิ่ม Template ใหม่สำเร็จ → refresh หน้า Template Select"""
        logger.info("Template ถูกเพิ่มที่: %s", templates_dir)
        # refresh จะทำตอน navigate_to(PAGE_TEMPLATE_SELECT) อยู่แล้ว
