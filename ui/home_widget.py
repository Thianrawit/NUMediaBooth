"""
HomeWidget — หน้าแรกของ Photobooth
====================================
แสดงแค่ โลโก้ชมรม, ปุ่ม START ขนาดใหญ่ และ ปุ่ม Settings
เน้นความเรียบง่ายที่สุด (Minimalist)
"""

import os

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QFont, QIcon, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QGraphicsDropShadowEffect,
)
from path_manager import get_resource_path


class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class HomeWidget(QWidget):
    """หน้า Home Screen — จุดเริ่มต้นของ Photobooth แบบ Minimal"""

    start_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    logo_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HomeWidget")
        self.admin_password = "1234"
        
        # ตัวแปรสำหรับการกดปุ่มซ้ำ 5 ครั้ง
        self._setting_click_count = 0
        self._setting_timer = QTimer(self)
        self._setting_timer.setInterval(2000) # 2 วินาที
        self._setting_timer.setSingleShot(True)
        self._setting_timer.timeout.connect(self._reset_setting_clicks)
        
        # โทนสี: ส้ม เทา ขาว ดำ
        # เน้นความเรียบง่าย พื้นขาวสะอาดตา
        self.setStyleSheet("""
            QWidget#HomeWidget {
                background-color: #FFFFFF; /* พื้นหลังสีขาว */
            }
            QPushButton#SettingsBtn {
                background-color: #FFFFFF; /* ปุ่มตั้งค่าสีเทาเข้มเกือบดำ ตัดกับพื้นขาวชัดเจน */
                border: none;
                border-radius: 30px; /* ทำให้เป็นวงกลม (ขนาดปุ่ม 60x60) */
            }
            QPushButton#SettingsBtn:hover {
                background-color: #E8E8E8; /* สว่างขึ้นนิดหน่อยเวลานำเมาส์ไปชี้ */
            }
            QPushButton#StartBtn {
                background-color: #FF6B2B; /* ปุ่มสีส้ม */
                color: #FFFFFF; /* ตัวหนังสือสีขาว เห็นชัดเจน */
                border-radius: 50px;
                font-size: 60px; /* ตัวหนังสือใหญ่มาก */
                font-weight: bold;
                border: none;
                padding: 20px 40px;
            }
            QPushButton#StartBtn:hover {
                background-color: #E85A1F;
            }
            QPushButton#StartBtn:pressed {
                background-color: #D04C16;
            }
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(40, 30, 40, 40)

        # ---------- Top Bar (โลโก้บนซ้าย, Settings บนขวา) ----------
        top_bar = QHBoxLayout()
        
        # โลโก้ชมรม (มุมซ้ายบน)
        self.logo_label = ClickableLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.logo_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_label.setToolTip("คลิกเพื่อไปหน้า QR Code รับรูป")
        self.logo_label.clicked.connect(self.logo_clicked.emit)
        self._load_logo()
        top_bar.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignTop)

        # ดันให้ปุ่ม Settings ไปอยู่ขวาสุด
        top_bar.addStretch()

        self.btn_settings = QPushButton()
        self.btn_settings.setObjectName("SettingsBtn")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setFixedSize(60, 60) # ปุ่มตั้งค่าใหญ่พอดีๆ เป็นวงกลม
        
        self.btn_settings.setStyleSheet("background-color: white; border-radius: 12px;")
        
        # ใช้รูปภาพไอคอน Settings
        settings_icon_path = get_resource_path(os.path.join("image", "setting.png"))
        if os.path.exists(settings_icon_path):
            self.btn_settings.setIcon(QIcon(settings_icon_path))
            self.btn_settings.setIconSize(QSize(32, 32))
        else:
            self.btn_settings.setText("⚙")
            self.btn_settings.setStyleSheet("color: #FFFFFF; font-size: 24px;")
            
        self.btn_settings.clicked.connect(self._on_settings_clicked)
        top_bar.addWidget(self.btn_settings, alignment=Qt.AlignmentFlag.AlignTop)

        root_layout.addLayout(top_bar)

        # ---------- ดันปุ่ม Start ให้อยู่กึ่งกลางหน้าจอ ----------
        root_layout.addStretch(1)

        # ---------- ปุ่ม START ขนาดใหญ่ ----------
        self.btn_start = QPushButton("เริ่มถ่ายภาพ")
        self.btn_start.setObjectName("StartBtn")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setMinimumWidth(600)
        self.btn_start.setFixedHeight(300) # มึงแก้ไว้ให้ใหญ่สุดๆ
        
        # เพิ่มเงาสีส้มเรืองแสงให้ปุ่มดูโดดเด่นสุดๆ
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(255, 107, 43, 120))
        shadow.setOffset(0, 10)
        self.btn_start.setGraphicsEffect(shadow)

        self.btn_start.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.btn_start.clicked.connect(self.start_clicked.emit)

        # จัดกึ่งกลางปุ่ม (แนวนอน)
        start_row = QHBoxLayout()
        start_row.addStretch()
        start_row.addWidget(self.btn_start)
        start_row.addStretch()
        root_layout.addLayout(start_row)

        # ดันข้างล่างขึ้นมาให้ปุ่มอยู่ตรงกลางเป๊ะๆ
        root_layout.addStretch(1)

    def _on_settings_clicked(self) -> None:
        """ตรวจสอบการกด 5 ครั้งติดกัน ก่อนตรวจสอบรหัสผ่าน"""
        self._setting_click_count += 1
        if self._setting_click_count == 1:
            self._setting_timer.start()
            
        if self._setting_click_count >= 5:
            self._setting_timer.stop()
            self._setting_click_count = 0
            
            password, ok = QInputDialog.getText(
                self,
                "ยืนยันตัวตน",
                "กรุณากรอกรหัสผ่านผู้ดูแลระบบ:",
                QLineEdit.EchoMode.Password
            )
            if ok:
                if password == self.admin_password:
                    self.settings_clicked.emit()
                else:
                    QMessageBox.warning(self, "ผิดพลาด", "รหัสผ่านไม่ถูกต้อง!")

    def _reset_setting_clicks(self):
        """รีเซ็ตจำนวนครั้งการกดถ้าเวลาหมด"""
        self._setting_click_count = 0

    def _load_logo(self) -> None:
        """โหลดโลโก้จากไฟล์ที่กำหนด"""
        logo_path = get_resource_path(os.path.join("image", "Nu media.png"))

        if os.path.isfile(logo_path):
            pixmap = QPixmap(logo_path)
            # ขนาดโลโก้ปรับให้ใหญ่ขึ้นเพราะพื้นที่โล่ง
            scaled = pixmap.scaled(
                100, 100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.logo_label.setPixmap(scaled)
        else:
            self.logo_label.setText("🎓")
            placeholder_font = QFont()
            placeholder_font.setPointSize(100)
            self.logo_label.setFont(placeholder_font)

    def set_logo(self, path: str) -> None:
        """เปลี่ยนโลโก้แบบ dynamic"""
        if os.path.isfile(path):
            pixmap = QPixmap(path)
            scaled = pixmap.scaled(
                350, 350,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.logo_label.setPixmap(scaled)
