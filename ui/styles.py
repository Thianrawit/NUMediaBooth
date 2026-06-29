"""
Shared Stylesheet สำหรับ NUMediaBooth
======================================
รวม QSS (Qt Style Sheet) ไว้ที่เดียว เพื่อให้ทุก Widget ใช้ร่วมกัน
แก้ตรงนี้ที่เดียว = เปลี่ยน theme ทั้งแอป
"""

# ==================== สี Theme ====================
# สีหลัก (Primary)
PRIMARY = "#6C5CE7"          # ม่วงสดใส
PRIMARY_HOVER = "#5A4BD1"    # ม่วงเข้มตอน hover
PRIMARY_PRESSED = "#4834B5"  # ม่วงเข้มตอนกด

# สีเสริม (Accent)
ACCENT = "#00CEC9"           # เขียวมิ้นท์
ACCENT_HOVER = "#00B5B0"

# สีพื้นหลัง
BG_DARK = "#1E1E2E"          # พื้นหลังหลัก (เทาเข้มอมม่วง)
BG_CARD = "#2A2A3E"          # พื้นหลังการ์ด
BG_INPUT = "#353550"         # พื้นหลัง input field
BG_HOVER = "#3A3A55"         # พื้นหลัง hover

# สีข้อความ
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#A0A0C0"
TEXT_MUTED = "#6C6C8A"

# สีขอบ
BORDER = "#404060"
BORDER_FOCUS = PRIMARY

# สี Status
SUCCESS = "#00E676"
WARNING = "#FFD600"
DANGER = "#FF5252"


# ==================== Global Stylesheet ====================

GLOBAL_STYLESHEET = f"""
/* ===== Base ===== */
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Noto Sans Thai", sans-serif;
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
