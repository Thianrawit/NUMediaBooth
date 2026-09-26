import os
import logging

from PyQt6.QtCore import Qt, QSize, QUrl
from PyQt6.QtGui import QIcon, QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QListView,
)
from path_manager import get_resource_path
from ui.styles import BG_DARK, BG_CARD, BG_INPUT, BG_HOVER, BORDER, PRIMARY, TEXT_PRIMARY

logger = logging.getLogger(__name__)

class RawImagesDialog(QDialog):
    """หน้าต่างแสดงรูปภาพดิบที่ถ่ายเก็บไว้ใน .NUMediaBooth_Temp"""

    def __init__(self, temp_dir: str, parent=None):
        super().__init__(parent)
        self.temp_dir = temp_dir
        self.setWindowTitle("รูปดิบทั้งหมด")
        self.resize(800, 600)
        self.setStyleSheet(f"background-color: {BG_DARK}; color: {TEXT_PRIMARY}; font-family: 'Google Sans', sans-serif;")
        
        self._init_ui()
        self._load_images()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Top bar
        top_bar = QHBoxLayout()
        
        title = QLabel("📸 รูปดิบทั้งหมดในโฟลเดอร์ชั่วคราว")
        title_font = title.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        top_bar.addWidget(title)
        
        top_bar.addStretch()
        
        self.btn_open_folder = QPushButton()
        self.btn_open_folder.setIcon(QIcon(get_resource_path(os.path.join("image", "folder.png"))))
        self.btn_open_folder.setIconSize(QSize(24, 24))
        self.btn_open_folder.setFixedSize(40, 40)
        self.btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_folder.setStyleSheet("background-color: white; border-radius: 8px;")
        self.btn_open_folder.setToolTip("เปิดโฟลเดอร์")
        self.btn_open_folder.clicked.connect(self._open_folder)
        top_bar.addWidget(self.btn_open_folder)
        
        layout.addLayout(top_bar)
        
        # Image List
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListView.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_widget.setSpacing(16)
        self.list_widget.setIconSize(QSize(160, 120))
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            QListWidget::item {{
                background: {BG_INPUT};
                border-radius: 8px;
                padding: 10px;
                color: {TEXT_PRIMARY};
            }}
            QListWidget::item:selected {{
                background: {BG_HOVER};
                border: 2px solid {PRIMARY};
            }}
        """)
        layout.addWidget(self.list_widget, stretch=1)
        
        # Bottom bar
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        
        self.btn_close = QPushButton("ปิดหน้าต่าง")
        self.btn_close.setFixedSize(120, 40)
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 8px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
                border-color: {PRIMARY};
            }}
        """)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(self.btn_close)
        
        layout.addLayout(bottom_bar)

    def _load_images(self):
        self.list_widget.clear()
        if not os.path.exists(self.temp_dir):
            return
            
        valid_ext = {".png", ".jpg", ".jpeg", ".bmp"}
        files = [f for f in os.listdir(self.temp_dir) if os.path.splitext(f)[1].lower() in valid_ext]
        
        # เรียงตามเวลา สร้างล่าสุดขึ้นก่อน
        files.sort(key=lambda x: os.path.getctime(os.path.join(self.temp_dir, x)), reverse=True)
        
        for f in files:
            path = os.path.join(self.temp_dir, f)
            icon = QIcon(path)
            item = QListWidgetItem(icon, f)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_widget.addItem(item)

    def _open_folder(self):
        if os.path.exists(self.temp_dir):
            if hasattr(os, "startfile"):
                os.startfile(self.temp_dir)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.temp_dir))
