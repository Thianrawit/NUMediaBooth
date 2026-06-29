"""
FinishWidget — หน้าเสร็จสิ้นการถ่ายภาพ
========================================
แสดงโลโก้, คำขอบคุณ, และ QR Code ที่นำไปสู่ Google Drive Folder
เพื่อให้ผู้ใช้สามารถสแกนรับภาพได้
"""

import os
import qrcode
from PIL import ImageQt
from path_manager import get_resource_path

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QFrame
)

import logging

logger = logging.getLogger(__name__)

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
        self.lbl_qr = QLabel()
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr.setFixedSize(300, 300)
        self.lbl_qr.setStyleSheet("background: white;")
        qr_layout.addWidget(self.lbl_qr)
        
        # 4. ข้อความลิงก์สำรองเผื่อสแกนไม่ได้
        self.lbl_link = QLabel("Google Drive Folder")
        self.lbl_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_link.setStyleSheet("color: #666666; font-size: 14px; margin-top: 10px;")
        self.lbl_link.setWordWrap(True)
        qr_layout.addWidget(self.lbl_link)
        
        # ห่อ QFrame ไว้ตรงกลาง
        qr_container = QVBoxLayout()
        qr_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_container.addWidget(qr_frame)
        layout.addLayout(qr_container)
        
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

    def setup_finish(self, folder_id: str) -> None:
        """ตั้งค่า QR Code ตาม Folder ID"""
        if folder_id:
            drive_url = f"https://drive.google.com/drive/folders/{folder_id}"
            self.lbl_link.setText(drive_url)
            self.lbl_link.setVisible(False)  # ซ่อนลิงก์ไว้ถ้ายาวไป QR ก็พอ
            
            # สร้าง QR Code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=2,
            )
            qr.add_data(drive_url)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # ดึงข้อมูลภาพจริงออกมาเป็นโหมด RGB เพื่อให้ PyQt แปลงได้ง่ายๆ
            pil_image = img.get_image().convert("RGB")
            
            # แปลง PIL Image เป็น QPixmap
            qimage = ImageQt.ImageQt(pil_image)
            pixmap = QPixmap.fromImage(qimage)
            
            # ปรับขนาดให้พอดี
            scaled_pixmap = pixmap.scaled(
                self.lbl_qr.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_qr.setPixmap(scaled_pixmap)
        else:
            self.lbl_qr.setText("❌ ไม่ได้ตั้งค่า Google Drive Folder ID")
            self.lbl_qr.setStyleSheet("color: #FF5252; font-size: 16px; font-weight: bold;")
            self.lbl_link.setVisible(False)
