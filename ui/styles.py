"""
Shared Stylesheet สำหรับ NUMediaBooth
======================================
รวม QSS (Qt Style Sheet) ไว้ที่เดียว เพื่อให้ทุก Widget ใช้ร่วมกัน
แก้ตรงนี้ที่เดียว = เปลี่ยน theme ทั้งแอป
"""

import os

# ==================== สี Theme (ส้ม ดำ ขาว เทา) ====================
# สีหลัก (Primary - ส้มสดใส มีพลัง)
PRIMARY = "#FF6B2B"          # ส้มเอกลักษณ์
PRIMARY_HOVER = "#E85A1F"    # ส้มเข้มตอน hover
PRIMARY_PRESSED = "#D04C16"  # ส้มเข้มตอนกด

# สีเสริม (Accent - ส้มสว่าง / Amber)
ACCENT = "#FFA040"           # ส้มอ่อน / สว่าง
ACCENT_HOVER = "#FF8F20"

# สีพื้นหลัง (ดำ / เทาเข้ม)
BG_DARK = "#121214"          # ดำลึก สบายตา
BG_CARD = "#1C1C1F"          # การ์ดเทาเข้ม
BG_INPUT = "#26262B"         # input field
BG_HOVER = "#2F2F36"         # พื้นหลัง hover

# สีข้อความ (ขาว / เทา)
TEXT_PRIMARY = "#FFFFFF"     # ขาว
TEXT_SECONDARY = "#B0B0BC"   # เทากลาง สะอาดตา
TEXT_MUTED = "#767682"       # เทาหม่น

# สีขอบ
BORDER = "#3E3E46"
BORDER_FOCUS = PRIMARY       # สีส้มตอน focus

# สี Status
SUCCESS = "#22C55E"
WARNING = "#F59E0B"
DANGER = "#EF4444"


# ==================== Global Stylesheet ====================

GLOBAL_STYLESHEET = f"""
/* ===== Base ===== */
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: "Google Sans", "Segoe UI", sans-serif;
    font-size: 14px;
}}

/* ===== QPushButton — ปุ่มปกติ ===== */
QPushButton {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: {PRIMARY};
}}

QPushButton:pressed {{
    background-color: {PRIMARY_PRESSED};
}}

/* ===== ปุ่ม Primary ===== */
QPushButton[cssClass="primary"] {{
    background-color: {PRIMARY};
    color: {TEXT_PRIMARY};
    border: none;
    font-weight: 700;
}}

QPushButton[cssClass="primary"]:hover {{
    background-color: {PRIMARY_HOVER};
}}

QPushButton[cssClass="primary"]:pressed {{
    background-color: {PRIMARY_PRESSED};
}}

/* ===== ปุ่ม Accent ===== */
QPushButton[cssClass="accent"] {{
    background-color: {ACCENT};
    color: {BG_DARK};
    border: none;
    font-weight: 700;
}}

QPushButton[cssClass="accent"]:hover {{
    background-color: {ACCENT_HOVER};
}}

/* ===== ปุ่ม Danger ===== */
QPushButton[cssClass="danger"] {{
    background-color: {DANGER};
    color: {TEXT_PRIMARY};
    border: none;
    font-weight: 700;
}}

/* ===== ปุ่ม Nav (สำหรับ navigation bar) ===== */
QPushButton[cssClass="nav"] {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    color: {TEXT_SECONDARY};
}}

QPushButton[cssClass="nav"]:hover {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}

QPushButton[cssClass="nav-active"] {{
    background-color: {PRIMARY};
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    font-weight: 700;
}}

/* ===== QLabel ===== */
QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

QLabel[cssClass="title"] {{
    font-size: 28px;
    font-weight: 800;
    color: {TEXT_PRIMARY};
}}

QLabel[cssClass="subtitle"] {{
    font-size: 16px;
    color: {TEXT_SECONDARY};
}}

QLabel[cssClass="muted"] {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}

QLabel[cssClass="section-title"] {{
    font-size: 16px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    padding-bottom: 4px;
}}

/* ===== QLineEdit ===== */
QLineEdit {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    selection-background-color: {PRIMARY};
}}

QLineEdit:focus {{
    border-color: {BORDER_FOCUS};
}}

QLineEdit:disabled {{
    color: {TEXT_MUTED};
    background-color: {BG_DARK};
}}

/* ===== QComboBox ===== */
QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
}}

QComboBox:hover {{
    border-color: {PRIMARY};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {TEXT_SECONDARY};
    margin-right: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {PRIMARY};
    outline: none;
}}

/* ===== QScrollArea ===== */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background-color: {BG_DARK};
    width: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: {BORDER};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {TEXT_MUTED};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ===== QGroupBox ===== */
QGroupBox {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 12px;
    padding: 20px 16px 16px 16px;
    font-size: 14px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    background-color: {BG_CARD};
    border-radius: 6px;
    color: {PRIMARY};
}}

/* ===== QCheckBox ===== */
QCheckBox {{
    background: transparent;
    color: {TEXT_PRIMARY};
    spacing: 8px;
    font-size: 14px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {BORDER};
    border-radius: 4px;
    background-color: {BG_INPUT};
}}

QCheckBox::indicator:checked {{
    background-color: {PRIMARY};
    border-color: {PRIMARY};
}}

QCheckBox::indicator:hover {{
    border-color: {PRIMARY};
}}

/* ===== QSpinBox ===== */
QSpinBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
}}

QSpinBox:focus {{
    border-color: {BORDER_FOCUS};
}}

/* ===== QListWidget ===== */
QListWidget {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}

QListWidget::item {{
    padding: 8px 12px;
    border-radius: 6px;
}}

QListWidget::item:hover {{
    background-color: {BG_HOVER};
}}

QListWidget::item:selected {{
    background-color: {PRIMARY};
    font-weight: 600;
}}

/* ===== QMenu ===== */
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

/* ===== QSlider ===== */
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

/* ===== Template Card (สำหรับหน้าเลือก Template) ===== */
QPushButton[cssClass="template-card"] {{
    background-color: {BG_CARD};
    border: 2px solid {BORDER};
    border-radius: 12px;
    padding: 8px;
}}

QPushButton[cssClass="template-card"]:hover {{
    border-color: {PRIMARY};
    background-color: {BG_HOVER};
}}

QPushButton[cssClass="template-card-selected"] {{
    background-color: {BG_CARD};
    border: 3px solid {PRIMARY};
    border-radius: 12px;
    padding: 8px;
}}
"""


def init_app_font_and_locale(app=None) -> str:
    """ตั้งค่า Font (Google Sans), Locale (บังคับใช้เลขอารบิก), และคืนชื่อ Font family ที่โหลดได้"""
    from PyQt6.QtCore import QLocale
    from PyQt6.QtGui import QFontDatabase, QFont
    from path_manager import get_resource_path
    import logging

    _logger = logging.getLogger(__name__)

    # 1. บังคับใช้เลขอารบิกทั่วทั้งโปรแกรม (ป้องกัน Windows th_TH แปลงตัวเลขเป็นเลขไทย)
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))

    # 2. โหลด Google Sans Font
    font_path = get_resource_path(os.path.join("Font", "GoogleSans-VariableFont_GRAD,opsz,wght.ttf"))
    family_name = "Google Sans"

    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                family_name = families[0]
                _logger.info("โหลด Google Sans Font สำเร็จ: %s", family_name)
        else:
            _logger.warning("ไม่สามารถโหลด Font จาก: %s", font_path)
    else:
        _logger.warning("ไม่พบไฟล์ Font ที่: %s", font_path)

    # 3. ตั้งค่า Font เริ่มต้นให้กับ QApplication
    if app is not None:
        app_font = QFont(family_name, 10)
        app.setFont(app_font)

    return family_name

