"""
FinishWidget — หน้าเสร็จสิ้นการถ่ายภาพ
========================================
แสดงโลโก้, คำขอบคุณ, และ QR Code ที่นำไปสู่ Google Drive Folder
เพื่อให้ผู้ใช้สามารถสแกนรับภาพได้
"""

import os
from path_manager import get_resource_path

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QFrame
)

import logging

logger = logging.getLogger(__name__)

class ResponsiveImageLabel(QLabel):
    """QLabel ที่วาดรูปและรักษาสัดส่วนอัตโนมัติตามขนาดของหน้าต่างโดยไม่เสียสัดส่วน"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_pixmap = None
        self.setMinimumSize(150, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def setPixmap(self, pixmap: QPixmap):
        self._original_pixmap = pixmap
        self._update_pixmap()
        
    def clear(self):
        self._original_pixmap = None
        super().clear()

    def _update_pixmap(self):
        if self._original_pixmap and not self._original_pixmap.isNull():
            size = min(self.width(), self.height())
            if size <= 0:
                return
            scaled = self._original_pixmap.scaled(
                size, size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.FastTransformation
            )
            super().setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pixmap()


class FinishWidget(QWidget):
    """
    หน้าแสดงผลลัพธ์หลังถ่ายเสร็จ
    - มีโลโก้
    - คำขอบคุณ
    - QR Code
    - ปุ่มกลับหน้าหลัก
    """
    
    back_home_clicked = pyqtSignal()
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FinishWidget")
        self._init_ui()
        
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Spacer บนสุด
        layout.addStretch(1)
        
        # 1. โลโก้ชมรม
        self.lbl_logo = QLabel()
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = get_resource_path(os.path.join("image", "Nu media.png"))
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # ปรับขนาดโลโก้ให้สวยงาม (สูงสัก 150px)
            scaled_logo = pixmap.scaledToHeight(150, Qt.TransformationMode.SmoothTransformation)
            self.lbl_logo.setPixmap(scaled_logo)
        else:
            self.lbl_logo.setText("📷 NU Media")
            self.lbl_logo.setStyleSheet("font-size: 36px; font-weight: bold; color: #FFFFFF;")
        layout.addWidget(self.lbl_logo)
        
        # 2. คำขอบคุณ
        lbl_thank_you = QLabel("ขอบคุณที่ใช้บริการครับ/ค่ะ 💖")
        lbl_thank_you.setProperty("cssClass", "title")
        lbl_thank_you.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_thank_you.setStyleSheet("font-size: 32px; font-weight: bold; margin-top: 10px; margin-bottom: 20px;")
        layout.addWidget(lbl_thank_you)
        
        # กรอบสำหรับ QR Code
        qr_frame = QFrame()
        qr_frame.setObjectName("QRFrame")
        qr_frame.setStyleSheet("""
            #QRFrame {
                background: #FFFFFF;
                border-radius: 20px;
                padding: 20px;
            }
        """)
        qr_layout = QVBoxLayout(qr_frame)
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_layout.setContentsMargins(20, 20, 20, 20)
        
        lbl_instruction = QLabel("สามารถรับรูปได้ที่")
        lbl_instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_instruction.setStyleSheet("color: #333333; font-size: 32px; font-weight: bold; margin-bottom: 10px;")
        qr_layout.addWidget(lbl_instruction)
        
        # 3. ภาพ QR Code
        self.lbl_qr = ResponsiveImageLabel()
        self.lbl_qr.setStyleSheet("background: white;")
        qr_layout.addWidget(self.lbl_qr, stretch=1)
        
        # 4. ข้อความลิงก์สำรองเผื่อสแกนไม่ได้
        self.lbl_link = QLabel("Google Drive Folder")
        self.lbl_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_link.setStyleSheet("color: #666666; font-size: 14px; margin-top: 10px;")
        self.lbl_link.setWordWrap(True)
        qr_layout.addWidget(self.lbl_link)
        
        # ห่อ QFrame ไว้ตรงกลางแต่ให้สามารถขยายได้
        qr_container = QHBoxLayout()
        qr_container.addStretch(1)
        qr_container.addWidget(qr_frame, stretch=1)
        qr_container.addStretch(1)
        # ให้กรอบ QR Code ได้พื้นที่แนวตั้งเยอะๆ (ประมาณ 40-50% ของจอ)
        layout.addLayout(qr_container, stretch=10)
        
        # Spacer ล่าง
        layout.addStretch(1)
        
        # 5. ปุ่มกลับหน้าหลัก
        self.btn_back = QPushButton("←  กลับหน้าหลัก")
        self.btn_back.setProperty("cssClass", "primary")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setFixedSize(200, 60)
        
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.btn_back.setFont(font)
        
        self.btn_back.clicked.connect(self.back_home_clicked.emit)
        
        btn_layout = QVBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_layout.addWidget(self.btn_back)
        layout.addLayout(btn_layout)

    def setup_finish(self, qr_pixmap: QPixmap, folder_id: str) -> None:
        """ตั้งค่า QR Code ตามข้อมูลที่ได้รับ"""
        if folder_id and qr_pixmap and not qr_pixmap.isNull():
            drive_url = f"https://drive.google.com/drive/folders/{folder_id}"
            self.lbl_link.setText(drive_url)
            self.lbl_link.setVisible(False)  # ซ่อนลิงก์ไว้ถ้ายาวไป QR ก็พอ
            
            self.lbl_qr.setPixmap(qr_pixmap)
            # ลบการตั้งค่า text เพราะมันอาจค้างอยู่ถ้าตั้งค่าทีหลัง
            self.lbl_qr.setStyleSheet("background: white;")
        else:
            self.lbl_qr.clear()
            self.lbl_qr.setText("ยังไม่ได้ตั้งค่า Google Drive ในหน้า Setting")
            self.lbl_qr.setStyleSheet("color: #FF5252; font-size: 16px; font-weight: bold;")
            self.lbl_link.setVisible(False)
