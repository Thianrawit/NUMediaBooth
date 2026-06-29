from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

class PrinterAlertDialog(QDialog):
    """
    หน้าต่างแจ้งเตือนสถานะปริ้นเตอร์แบบใหญ่พิเศษ เพื่อให้สตาฟมองเห็นจากระยะไกล
    (เช่น กระดาษหมด, หมึกหมด, เครื่องขัดข้อง)
    """
    def __init__(self, error_message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ แจ้งเตือนเครื่องปริ้นขัดข้อง")
        # ทำให้หน้าต่างอยู่ข้างหน้าเสมอแบบ Modal
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(800, 450)
        self.setStyleSheet("""
            QDialog {
                background-color: #F8D7DA;
                border: 4px solid #DC3545;
                border-radius: 12px;
            }
            QLabel#Title {
                color: #721C24;
                font-size: 60px;
                font-weight: bold;
            }
            QLabel#Message {
                color: #DC3545;
                font-size: 45px;
                font-weight: bold;
            }
            QPushButton {
                font-size: 28px;
                font-weight: bold;
                padding: 20px 40px;
                border-radius: 8px;
                color: white;
            }
            QPushButton#Retry {
                background-color: #28A745;
            }
            QPushButton#Retry:hover {
                background-color: #218838;
            }
            QPushButton#Skip {
                background-color: #6C757D;
            }
            QPushButton#Skip:hover {
                background-color: #5A6268;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(30)

        # Title
        title_label = QLabel("⚠️ กรุณาตรวจสอบปริ้นเตอร์!")
        title_label.setObjectName("Title")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Message
        msg_label = QLabel(error_message)
        msg_label.setObjectName("Message")
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(30)
        
        self.btn_skip = QPushButton("ข้ามการพิมพ์ (Skip)")
        self.btn_skip.setObjectName("Skip")
        self.btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip.clicked.connect(self.reject)
        
        self.btn_retry = QPushButton("ตรวจสอบใหม่ (Retry)")
        self.btn_retry.setObjectName("Retry")
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_skip)
        btn_layout.addWidget(self.btn_retry)
        
        layout.addLayout(btn_layout)
