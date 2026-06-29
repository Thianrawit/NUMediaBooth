"""
CameraCaptureWidget — หน้าจอถ่ายภาพด้วย Webcam (QCamera) พร้อม Live Preview
======================================================================
- รับค่าจำนวนรูปจาก Template
- แสดง Live Preview จาก Webcam ที่เสียบอยู่
- นับถอยหลัง (Countdown) กลางจอแบบ Overlay
- ถ่ายรูปและพรีวิวรูป + เลือก ถ่ายใหม่ / ถัดไป
"""

import os
import time
import logging

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QRectF, QSizeF
from PyQt6.QtGui import QPixmap, QFont, QColor, QPen, QBrush, QPainter
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QStackedWidget,
    QStackedLayout,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsTextItem,
    QGraphicsRectItem,
    QGraphicsItem
)
from PyQt6.QtMultimedia import QMediaDevices, QCamera, QMediaCaptureSession, QImageCapture
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from config_manager import ConfigManager
from chroma_key_module import remove_color_background
from path_manager import get_dynamic_path

logger = logging.getLogger(__name__)


class CameraCaptureWidget(QWidget):
    """หน้าจอควบคุมการถ่ายภาพด้วย Webcam
    
    Signals:
        capture_finished(list): เมื่อถ่ายครบทุกรูป จะส่ง list ของ path รูปถ่ายกลับไป
        cancel_clicked(): เมื่อผู้ใช้กดยกเลิกกลับไปหน้าเลือก Template
    """

    capture_finished = pyqtSignal(list)
    cancel_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CameraCaptureWidget")

        # ---------------- State Variables ----------------
        self.total_photos = 0
        self.current_photo_idx = 0
        self.countdown_seconds = 3
        self.current_countdown = 0
        self.taken_photos: list[str] = []
        self.camera_name = ""
        self._temp_last_photo = None
        
        # โฟลเดอร์พักไฟล์ (ย้ายจาก Pictures ของ User มาไว้ในตัวโปรแกรม)
        self.temp_dir = get_dynamic_path(".NUMediaBooth_Temp")
        os.makedirs(self.temp_dir, exist_ok=True)

        # Qt Multimedia Components
        self.camera = None
        self.capture_session = None
        self.image_capture = None

        # Timer สำหรับนับถอยหลัง
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_timer_tick)

        self._init_ui()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)

        # ---------- Top Bar ----------
        top_bar = QHBoxLayout()
        self.btn_cancel = QPushButton("✖ ยกเลิก / กลับ")
        self.btn_cancel.setProperty("cssClass", "nav")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel)
        top_bar.addWidget(self.btn_cancel)

        top_bar.addStretch()

        self.lbl_status = QLabel("กำลังเตรียมกล้อง...")
        self.lbl_status.setProperty("cssClass", "title")
        top_bar.addWidget(self.lbl_status)

        top_bar.addStretch()
        spacer = QWidget()
        spacer.setFixedWidth(self.btn_cancel.sizeHint().width())
        top_bar.addWidget(spacer)

        root_layout.addLayout(top_bar)

        # ---------- Main Content Area (Stacked) ----------
        # 0: หน้า Live Preview วิดีโอ + นับถอยหลัง
        # 1: หน้า Preview รูปที่ถ่ายเสร็จ
        self.content_stack = QStackedWidget()
        root_layout.addWidget(self.content_stack, stretch=1)

        # === Page 0: Live Video ===
        page_live = QWidget()
        layout_live = QVBoxLayout(page_live)
        layout_live.setContentsMargins(0, 0, 0, 0)
        
        # QGraphicsView for rendering template + camera
        self.graphics_scene = QGraphicsScene()
        self.graphics_view = QGraphicsView(self.graphics_scene)
        self.graphics_view.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.graphics_view.setStyleSheet("background-color: #12121A; border: none; border-radius: 12px;")
        
        # Camera Video Container (Z-value 0)
        self.video_container = QGraphicsRectItem()
        self.video_container.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
        self.video_container.setPen(QPen(Qt.PenStyle.NoPen))
        self.graphics_scene.addItem(self.video_container)
        self.video_container.setZValue(0)

        # Camera Video Item (Z-value 0, child of container)
        self.video_item = QGraphicsVideoItem(self.video_container)
        self.video_item.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        
        # Template Image Item (Z-value 1)
        self.template_item = QGraphicsPixmapItem()
        self.graphics_scene.addItem(self.template_item)
        self.template_item.setZValue(1)
        
        # Countdown Text Item (Z-value 3, on top of everything)
        self.countdown_item = QGraphicsTextItem("")
        font_countdown = QFont()
        font_countdown.setPointSize(120)
        font_countdown.setBold(True)
        self.countdown_item.setFont(font_countdown)
        self.countdown_item.setDefaultTextColor(QColor(0, 206, 201))
        self.countdown_item.setZValue(3)
        self.graphics_scene.addItem(self.countdown_item)
        self.countdown_item.hide()
        
        # Dictionary เก็บ placeholder และรูปที่ถ่ายแล้ว
        self.placeholder_items = {}
        self.taken_photo_items = {}
        
        layout_live.addWidget(self.graphics_view)
        self.content_stack.addWidget(page_live)

        # === Page 1: Image Preview ===
        page_preview = QWidget()
        layout_preview = QVBoxLayout(page_preview)
        layout_preview.setContentsMargins(0, 0, 0, 0)

        self.lbl_preview = QLabel()
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("background-color: #000; border-radius: 12px;")
        layout_preview.addWidget(self.lbl_preview, stretch=1)

        self.content_stack.addWidget(page_preview)

        # ---------- Bottom Bar (Buttons) ----------
        self.bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_start_capture = QPushButton("📸 เริ่มถ่ายรูป")
        self.btn_start_capture.setProperty("cssClass", "primary")
        self.btn_start_capture.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start_capture.setFixedSize(250, 60)
        font_btn = QFont()
        font_btn.setPointSize(14)
        font_btn.setBold(True)
        self.btn_start_capture.setFont(font_btn)
        self.btn_start_capture.clicked.connect(self.start_countdown)
        
        self.btn_retake = QPushButton("🔄 ถ่ายใหม่ (Retake)")
        self.btn_retake.setProperty("cssClass", "danger")
        self.btn_retake.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retake.setFixedSize(200, 60)
        self.btn_retake.setFont(font_btn)
        self.btn_retake.clicked.connect(self._on_retake)

        self.btn_next = QPushButton("✅ ถัดไป (Next)")
        self.btn_next.setProperty("cssClass", "primary")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setFixedSize(200, 60)
        self.btn_next.setFont(font_btn)
        self.btn_next.clicked.connect(self._on_next)

        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_start_capture)
        bottom_layout.addWidget(self.btn_retake)
        bottom_layout.addWidget(self.btn_next)
        bottom_layout.addStretch()

        root_layout.addWidget(self.bottom_bar)

    # ------------------------------------------------------------------
    # Public Methods
    # ------------------------------------------------------------------

    def setup_capture(
        self, 
        total_photos: int, 
        countdown_seconds: int = 3, 
        camera_name: str = "",
        template_path: str = "",
        layout_config: dict = None
    ) -> None:
        """เตรียมความพร้อมก่อนเริ่มถ่าย
        
        Args:
            total_photos: จำนวนรูปที่ต้องถ่ายทั้งหมด
            countdown_seconds: เวลานับถอยหลังต่อรูป (วินาที)
            camera_name: ชื่อกล้องที่เลือกจากหน้าตั้งค่า (ถ้าว่างจะใช้ตัวแรกที่เจอ)
            template_path: พาธไฟล์รูป Template
            layout_config: Dict การจัดเรียง (slots)
        """
        self.total_photos = total_photos
        self.countdown_seconds = countdown_seconds
        self.camera_name = camera_name
        self.template_path = template_path
        self.layout_config = layout_config or {}
        
        self.current_photo_idx = 1
        self.taken_photos = []

        self._setup_camera()
        self._setup_graphics_scene()
        self._show_ready_state()

    def _setup_camera(self) -> None:
        """เชื่อมต่อกับ Webcam ด้วย QCamera"""
        if self.camera:
            self.camera.stop()
            self.camera.deleteLater()
            
        cameras = QMediaDevices.videoInputs()
        selected_cam = None
        
        # หาชื่อกล้องที่ตรงกับ Config
        if self.camera_name:
            for cam in cameras:
                if cam.description() == self.camera_name:
                    selected_cam = cam
                    break
                    
        # ถ้าหาไม่เจอ ให้ใช้กล้องตัวแรกสุดเป็นค่าเริ่มต้น
        if not selected_cam and cameras:
            selected_cam = cameras[0]
            
        if selected_cam:
            logger.info("กำลังเชื่อมต่อ Webcam: %s", selected_cam.description())
            self.camera = QCamera(selected_cam)
            self.capture_session = QMediaCaptureSession()
            self.capture_session.setCamera(self.camera)
            self.capture_session.setVideoOutput(self.video_item)
            
            self.image_capture = QImageCapture()
            self.capture_session.setImageCapture(self.image_capture)
            
            self.image_capture.imageSaved.connect(self._on_image_saved)
            self.image_capture.errorOccurred.connect(self._on_image_error)
            
        else:
            logger.error("ไม่พบกล้อง Webcam ใดๆ")
            QMessageBox.warning(self, "ข้อผิดพลาด", "ไม่พบกล้อง Webcam กรุณาตรวจสอบการเชื่อมต่อ USB")

    def _setup_graphics_scene(self) -> None:
        """ตั้งค่า Scene โหลด Template วาด Placeholder และกำหนดกล้องให้ตรง Slot"""
        # เคลียร์ของเก่า (ยกเว้น video_item, template_item, countdown_item ที่มีอยู่แล้ว)
        for item in self.placeholder_items.values():
            self.graphics_scene.removeItem(item)
        for item in self.taken_photo_items.values():
            self.graphics_scene.removeItem(item)
        self.placeholder_items.clear()
        self.taken_photo_items.clear()
        
        # 1. โหลด Template
        if os.path.exists(self.template_path):
            pixmap = QPixmap(self.template_path)
            self.template_item.setPixmap(pixmap)
            self.graphics_scene.setSceneRect(QRectF(pixmap.rect()))
            # ย่อให้พอดีจอ
            self.graphics_view.fitInView(self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self.template_item.setPixmap(QPixmap())
            
        # 2. วาด Placeholder ลงทุกช่อง
        slots = self.layout_config.get("slots", [])
        for i, slot in enumerate(slots):
            idx = i + 1
            w = slot.get("width", 400)
            h = slot.get("height", 300)
            x = slot.get("x", 0)
            y = slot.get("y", 0)
            angle = slot.get("angle", 0)
            
            # วงกลมพื้นดำโปร่งใส พร้อมตัวเลขสีขาวตรงกลาง
            placeholder = QGraphicsRectItem(0, 0, w, h)
            placeholder.setPos(x, y)
            placeholder.setTransformOriginPoint(w/2, h/2)
            placeholder.setRotation(angle)
            placeholder.setBrush(QBrush(QColor(0, 0, 0, 150)))
            placeholder.setPen(QPen(Qt.PenStyle.NoPen))
            placeholder.setZValue(2)
            
            text_item = QGraphicsTextItem(str(idx), placeholder)
            font = QFont()
            font.setPointSize(60)
            font.setBold(True)
            text_item.setFont(font)
            text_item.setDefaultTextColor(QColor(255, 255, 255))
            # จัดกึ่งกลาง
            br = text_item.boundingRect()
            text_item.setPos(w/2 - br.width()/2, h/2 - br.height()/2)
            
            self.graphics_scene.addItem(placeholder)
            self.placeholder_items[idx] = placeholder
            
        self._update_scene_for_current_slot()

    def _update_scene_for_current_slot(self) -> None:
        """ย้ายกล้องไป Slot ปัจจุบัน ซ่อน Placeholder อันนั้น และจัดตำแหน่ง Countdown"""
        slots = self.layout_config.get("slots", [])
        if not slots or self.current_photo_idx > len(slots):
            self.video_container.hide()
            return
            
        self.video_container.show()
        
        # ปิด Placeholder ของช่องปัจจุบัน และช่องก่อนหน้า
        for idx, item in self.placeholder_items.items():
            if idx <= self.current_photo_idx:
                item.hide()
            else:
                item.show()
                
        # ดึงค่าพิกัด Slot ปัจจุบัน
        slot = slots[self.current_photo_idx - 1]
        w = slot.get("width", 400)
        h = slot.get("height", 300)
        x = slot.get("x", 0)
        y = slot.get("y", 0)
        angle = slot.get("angle", 0)
        
        # อัปเดต Video Container ให้หมุนและพอดีกับกล่อง
        self.video_container.setRect(0, 0, w, h)
        self.video_container.setPos(x, y)
        self.video_container.setTransformOriginPoint(w/2, h/2)
        self.video_container.setRotation(angle)
        
        # อัปเดต Video Item ให้มีขนาดเท่ากัน (มันจะถูกคลิปใน Container)
        self.video_item.setSize(QSizeF(w, h))
        self.video_item.setPos(0, 0)
        
        # ย้าย Countdown ไปตรงกลางของ Slot นี้
        br = self.countdown_item.boundingRect()
        cx = x + w/2 - br.width()/2
        cy = y + h/2 - br.height()/2
        self.countdown_item.setPos(cx, cy)


    # ------------------------------------------------------------------
    # Capture Logic
    # ------------------------------------------------------------------

    def _show_ready_state(self) -> None:
        """แสดงหน้าจอเตรียมพร้อม + โชว์วิดีโอสด"""
        if self.camera:
            self.camera.start()
            
        self.timer.stop()
        self.content_stack.setCurrentIndex(0)
        self.lbl_status.setText(f"📸 รูปที่ {self.current_photo_idx} / {self.total_photos}")
        self.countdown_item.hide()
        
        self._update_scene_for_current_slot()
        
        self.btn_start_capture.setVisible(False)
        self.btn_retake.setVisible(False)
        self.btn_next.setVisible(False)
        self.btn_cancel.setEnabled(True)
        
        # เริ่มนับถอยหลังถ่ายรูปอัตโนมัติ 
        self.start_countdown()

    def start_countdown(self) -> None:
        """เริ่มนับถอยหลัง (ซ้อนบนวิดีโอ)"""
        self.btn_start_capture.setVisible(False)
        self.btn_cancel.setEnabled(False)
        self.current_countdown = self.countdown_seconds
        self.countdown_item.setPlainText(str(self.current_countdown))
        
        # จัดตำแหน่งกึ่งกลางใหม่ตามขนาด Text ที่เปลี่ยนไป
        slots = self.layout_config.get("slots", [])
        if slots:
            slot = slots[self.current_photo_idx - 1]
            w = slot.get("width", 400)
            h = slot.get("height", 300)
            x = slot.get("x", 0)
            y = slot.get("y", 0)
            br = self.countdown_item.boundingRect()
            self.countdown_item.setPos(x + w/2 - br.width()/2, y + h/2 - br.height()/2)
            
        self.countdown_item.show()
        
        self.timer.start(1000)

    def _on_timer_tick(self) -> None:
        """อัปเดตตัวเลขนับถอยหลังทุกๆ 1 วินาที"""
        self.current_countdown -= 1
        
        if self.current_countdown > 0:
            self.countdown_item.setPlainText(str(self.current_countdown))
        else:
            self.timer.stop()
            self.countdown_item.setPlainText("📸")
            # หน่วงเวลาเล็กน้อยให้คนโพสค้างไว้ แล้วค่อยจับภาพ
            QTimer.singleShot(200, self._trigger_camera)

    def _trigger_camera(self) -> None:
        """สั่ง Webcam จับภาพ (Capture)"""
        if not self.image_capture:
            QMessageBox.critical(self, "ข้อผิดพลาด", "ไม่สามารถเข้าถึงระบบจับภาพได้")
            return
            
        filename = f"capture_{int(time.time())}.jpg"
        filepath = os.path.join(self.temp_dir, filename)
        
        self.countdown_item.hide()
        # สั่งจับภาพและเซฟลงไฟล์
        # เมื่อเซฟเสร็จ จะไป trigger สัญญาณ imageSaved -> เรียก _on_image_saved()
        self.image_capture.captureToFile(filepath)

    def _on_image_saved(self, request_id: int, fileName: str) -> None:
        """ทำงานเมื่อกล้องบันทึกรูปเสร็จสมบูรณ์"""
        logger.info("Webcam ถ่ายภาพสำเร็จ: %s", fileName)
        self._temp_last_photo = fileName
        
        # ปิดกล้องชั่วคราวเพื่อประหยัดทรัพยากร
        if self.camera:
            self.camera.stop()
            
        self.video_container.hide()
        
        # วาดรูปที่เพิ่งถ่ายลงใน Slot นั้นชั่วคราวให้ดู
        idx = self.current_photo_idx
        slots = self.layout_config.get("slots", [])
        if slots and idx <= len(slots):
            slot = slots[idx - 1]
            w = slot.get("width", 400)
            h = slot.get("height", 300)
            x = slot.get("x", 0)
            y = slot.get("y", 0)
            angle = slot.get("angle", 0)
            
            pixmap = QPixmap(fileName)
            # Resize and crop
            scaled = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            cw, ch = scaled.width(), scaled.height()
            crop_rect = QRectF((cw - w) / 2, (ch - h) / 2, w, h).toRect()
            cropped = scaled.copy(crop_rect)
            
            item = QGraphicsPixmapItem(cropped)
            item.setPos(x, y)
            item.setTransformOriginPoint(w/2, h/2)
            item.setRotation(angle)
            item.setZValue(0)
            
            self.graphics_scene.addItem(item)
            self.taken_photo_items[idx] = item

        self.btn_retake.setVisible(True)
        self.btn_next.setVisible(True)
        self.btn_cancel.setEnabled(True)
        
    def _on_image_error(self, request_id: int, error, errorString: str) -> None:
        """ทำงานเมื่อการจับภาพเกิดข้อผิดพลาด"""
        logger.error("Webcam Error: %s", errorString)
        QMessageBox.warning(self, "กล้องมีปัญหา", f"ไม่สามารถถ่ายภาพได้: {errorString}")
        self._show_ready_state()

    # ------------------------------------------------------------------
    # Button Actions
    # ------------------------------------------------------------------

    def _on_retake(self) -> None:
        """ทิ้งรูปเดิม แล้วกลับไปเปิดกล้องถ่ายใหม่"""
        self._temp_last_photo = None
        
        # ลบรูปที่เพิ่งวาดใส่ออกไป
        idx = self.current_photo_idx
        if idx in self.taken_photo_items:
            self.graphics_scene.removeItem(self.taken_photo_items[idx])
            del self.taken_photo_items[idx]
            
        self._show_ready_state()

    def _on_next(self) -> None:
        """เก็บรูปนี้ไว้ และไปลุยรูปถัดไป"""
        if self._temp_last_photo:
            self.taken_photos.append(self._temp_last_photo)
            
        # ไม่ต้องวาดรูปลง Scene แล้ว เพราะวาดไปตั้งแต่ตอน _on_image_saved แล้วรูปนั้นก็คาอยู่แบบนั้นเลย!
        
        if self.current_photo_idx < self.total_photos:
            # รูปยังไม่ครบ ถ่ายต่อ
            self.current_photo_idx += 1
            self._show_ready_state()
        else:
            # ถ่ายครบโควต้าเทมเพลตแล้ว
            if self.camera:
                self.camera.stop()
            self.lbl_status.setText("✅ ถ่ายภาพเสร็จสิ้น!")
            self.content_stack.setCurrentIndex(0)
            
            # ปรับตำแหน่งของ Countdown ให้อยู่กลางจอรวม (ฉากหลังคือ Scene)
            self.countdown_item.setPlainText("กำลังรวมภาพ...\nโปรดรอสักครู่")
            br = self.countdown_item.boundingRect()
            sr = self.graphics_scene.sceneRect()
            self.countdown_item.setPos(sr.width()/2 - br.width()/2, sr.height()/2 - br.height()/2)
            self.countdown_item.show()
            
            self.btn_retake.setVisible(False)
            self.btn_next.setVisible(False)
            self.btn_cancel.setEnabled(False)
            
            QTimer.singleShot(500, lambda: self.capture_finished.emit(self.taken_photos))

    def _on_cancel(self) -> None:
        """เมื่อกดยกเลิกกลางคัน ให้ปิดกล้องก่อนแล้วค่อยแจ้ง Signal"""
        if self.camera:
            self.camera.stop()
        self.cancel_clicked.emit()

    def hideEvent(self, event) -> None:
        """เมื่อหน้าต่างนี้ถูกซ่อน ให้ปิดกล้องด้วย"""
        super().hideEvent(event)
        if self.camera:
            self.camera.stop()

    def showEvent(self, event) -> None:
        """เมื่อหน้าต่างถูกเปิดขึ้นมาใหม่ ให้เปิดกล้อง (ถ้ามีรูปที่ต้องถ่าย)"""
        super().showEvent(event)
        if self.camera and self.content_stack.currentIndex() == 0:
            self.camera.start()
        # ทำการปรับขนาดให้พอดีจอทันทีที่เปิด
        if hasattr(self, 'graphics_view') and hasattr(self, 'graphics_scene'):
            self.graphics_view.fitInView(self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        """เมื่อหน้าต่างถูก Resize ให้ปรับขนาดของ Canvas ให้พอดีกับกรอบเสมอ"""
        super().resizeEvent(event)
        if hasattr(self, 'graphics_view') and hasattr(self, 'graphics_scene'):
            self.graphics_view.fitInView(self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
