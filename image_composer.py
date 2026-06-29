"""
Image Composition Module สำหรับ Photobooth
============================================
โมดูลนี้ใช้สำหรับรวมรูปถ่ายจากกล้องเข้ากับกรอบ Template จาก Canva
โดยจะนำรูปถ่ายมา Resize ให้พอดี Slot, วางไว้เลเยอร์ล่าง,
แล้วเอากรอบ PNG (โปร่งใส) ทับด้านบน

Usage:
    from image_composer import merge_photobooth

    layout = {
        "total_photos": 2,
        "slots": [
            {"x": 100, "y": 150, "width": 400, "height": 300},
            {"x": 550, "y": 150, "width": 400, "height": 300},
        ]
    }
    result = merge_photobooth("frame.png", ["p1.jpg", "p2.jpg"], layout)
"""

import os
import logging
from datetime import datetime
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error Classes
# ---------------------------------------------------------------------------

class ImageComposerError(Exception):
    """Base exception สำหรับ Image Composer ทุก error ในโมดูลนี้สืบทอดจาก class นี้"""
    pass


class TemplateNotFoundError(ImageComposerError):
    """Template image file ไม่เจอ หรือเปิดไม่ได้"""
    pass


class PhotoNotFoundError(ImageComposerError):
    """Photo file ไม่เจอ หรือเปิดไม่ได้"""
    pass


class LayoutConfigError(ImageComposerError):
    """Layout config ไม่ถูกต้อง (key หาย, จำนวนไม่ตรง, ค่าผิด)"""
    pass


class ExportError(ImageComposerError):
    """เซฟไฟล์ output ไม่ได้"""
    pass


# ---------------------------------------------------------------------------
# Config Validation
# ---------------------------------------------------------------------------

_REQUIRED_SLOT_KEYS = {"x", "y", "width", "height"}


def validate_layout_config(layout_config: dict, photo_count: int) -> None:
    """ตรวจสอบ layout_config ว่าถูกต้องและสมบูรณ์หรือไม่

    Args:
        layout_config: Dictionary ที่บอก total_photos และ slots
        photo_count: จำนวนรูปถ่ายจริงที่ส่งเข้ามา

    Raises:
        LayoutConfigError: ถ้า config ไม่ถูกต้อง
    """
    # --- ต้องเป็น dict ---
    if not isinstance(layout_config, dict):
        raise LayoutConfigError(
            f"layout_config ต้องเป็น dict แต่ได้รับ {type(layout_config).__name__}"
        )

    # --- ต้องมี total_photos ---
    if "total_photos" not in layout_config:
        raise LayoutConfigError("layout_config ขาด key 'total_photos'")

    total_photos = layout_config["total_photos"]
    if not isinstance(total_photos, int) or total_photos < 1:
        raise LayoutConfigError(
            f"'total_photos' ต้องเป็น int >= 1 แต่ได้รับ {total_photos!r}"
        )

    # --- ต้องมี slots ---
    if "slots" not in layout_config:
        raise LayoutConfigError("layout_config ขาด key 'slots'")

    slots = layout_config["slots"]
    if not isinstance(slots, list):
        raise LayoutConfigError(
            f"'slots' ต้องเป็น list แต่ได้รับ {type(slots).__name__}"
        )

    # --- จำนวน slots ต้องตรงกับ total_photos ---
    if len(slots) != total_photos:
        raise LayoutConfigError(
            f"จำนวน slots ({len(slots)}) ไม่ตรงกับ total_photos ({total_photos})"
        )

    # --- จำนวนรูปถ่ายต้องตรงกับ total_photos ---
    if photo_count != total_photos:
        raise LayoutConfigError(
            f"จำนวนรูปถ่าย ({photo_count}) ไม่ตรงกับ total_photos ({total_photos})"
        )

    # --- ตรวจแต่ละ slot ---
    for i, slot in enumerate(slots):
        if not isinstance(slot, dict):
            raise LayoutConfigError(
                f"slot[{i}] ต้องเป็น dict แต่ได้รับ {type(slot).__name__}"
            )

        missing = _REQUIRED_SLOT_KEYS - slot.keys()
        if missing:
            raise LayoutConfigError(
                f"slot[{i}] ขาด key: {', '.join(sorted(missing))}"
            )

        for key in _REQUIRED_SLOT_KEYS:
            val = slot[key]
            if not isinstance(val, (int, float)) or val < 0:
                raise LayoutConfigError(
                    f"slot[{i}]['{key}'] ต้องเป็นตัวเลข >= 0 แต่ได้รับ {val!r}"
                )

        if slot["width"] <= 0 or slot["height"] <= 0:
            raise LayoutConfigError(
                f"slot[{i}] width/height ต้อง > 0 "
                f"(ได้ width={slot['width']}, height={slot['height']})"
            )


# ---------------------------------------------------------------------------
# Image Helpers
# ---------------------------------------------------------------------------

def _load_image(path: str, label: str = "image") -> Image.Image:
    """โหลดรูปภาพจาก path พร้อม error handling

    Args:
        path: path ของไฟล์รูปภาพ
        label: ชื่อเรียกสำหรับ error message (เช่น 'template', 'photo[0]')

    Returns:
        PIL Image object

    Raises:
        TemplateNotFoundError / PhotoNotFoundError
    """
    ErrorClass = TemplateNotFoundError if label == "template" else PhotoNotFoundError

    if not os.path.isfile(path):
        raise ErrorClass(f"ไม่เจอไฟล์ {label}: {path}")

    try:
        img = Image.open(path)
        img.load()  # Force load เพื่อจับ error ตั้งแต่ตอนนี้
        return img
    except Exception as e:
        raise ErrorClass(f"เปิดไฟล์ {label} ไม่ได้: {path} — {e}") from e


def _fit_photo_to_slot(
    photo: Image.Image,
    slot_width: int,
    slot_height: int,
    fit_mode: str = "cover",
) -> Image.Image:
    """Resize + Crop รูปถ่ายให้พอดี slot

    fit_mode:
        - "cover"   : ขยายให้เต็ม slot แล้ว crop ส่วนเกิน (ไม่มีขอบดำ) — Default
        - "contain" : ย่อให้อยู่ใน slot ทั้งรูป (อาจมีขอบดำ/padding)
        - "stretch" : ยืดให้พอดี slot ตรงๆ (อาจบิดเบี้ยว)

    Args:
        photo: PIL Image ของรูปถ่าย
        slot_width: ความกว้าง slot (px)
        slot_height: ความสูง slot (px)
        fit_mode: วิธี fit รูป ("cover" | "contain" | "stretch")

    Returns:
        PIL Image ที่มีขนาดพอดี slot_width x slot_height
    """
    slot_width = int(slot_width)
    slot_height = int(slot_height)

    if fit_mode == "stretch":
        return photo.resize((slot_width, slot_height), Image.LANCZOS)

    if fit_mode == "contain":
        # ย่อให้อยู่ใน slot ทั้งรูป แล้ววางกึ่งกลาง
        photo.thumbnail((slot_width, slot_height), Image.LANCZOS)
        canvas = Image.new("RGBA", (slot_width, slot_height), (0, 0, 0, 255))
        offset_x = (slot_width - photo.width) // 2
        offset_y = (slot_height - photo.height) // 2
        canvas.paste(photo, (offset_x, offset_y))
        return canvas

    # --- "cover" mode (default) ---
    # คำนวณ scale ratio ที่ทำให้รูปเต็ม slot
    src_w, src_h = photo.size
    scale = max(slot_width / src_w, slot_height / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)

    photo = photo.resize((new_w, new_h), Image.LANCZOS)

    # Crop จากกึ่งกลาง
    left = (new_w - slot_width) // 2
    top = (new_h - slot_height) // 2
    return photo.crop((left, top, left + slot_width, top + slot_height))


# ---------------------------------------------------------------------------
# Main Function
# ---------------------------------------------------------------------------

def merge_photobooth(
    template_image_path: str,
    photo_paths: list[str],
    layout_config: dict,
    output_dir: str = "output",
    output_filename: Optional[str] = None,
    fit_mode: str = "cover",
    output_format: str = "PNG",
    jpeg_quality: int = 95,
) -> str:
    """รวมรูปถ่ายจากกล้องเข้ากับกรอบ Template แล้ว Export เป็นไฟล์ใหม่

    ขั้นตอนการทำงาน:
        1. Validate layout_config
        2. สร้าง canvas (RGBA) ขนาดเท่า template
        3. โหลดรูปถ่ายแต่ละรูป → Resize ให้พอดี slot → วางบน canvas (เลเยอร์ล่าง)
        4. วาง template frame ทับบน canvas (เลเยอร์บนสุด — overlay)
        5. Export เซฟไฟล์ลง output_dir

    Args:
        template_image_path: Path ไปยังรูปกรอบ PNG (พื้นโปร่งใส) จาก Canva
        photo_paths: List ของ path รูปถ่ายจากกล้อง
        layout_config: Dictionary ที่บอกจำนวนรูปและพิกัดการวาง
            ตัวอย่าง:
            {
                "total_photos": 2,
                "slots": [
                    {"x": 100, "y": 150, "width": 400, "height": 300},
                    {"x": 550, "y": 150, "width": 400, "height": 300},
                ]
            }
        output_dir: โฟลเดอร์สำหรับเซฟไฟล์ output (default: "output")
        output_filename: ชื่อไฟล์ output (ถ้าไม่ระบุจะ auto-generate จาก timestamp)
        fit_mode: วิธี fit รูปถ่ายลง slot — "cover" | "contain" | "stretch"
        output_format: ฟอร์แมตไฟล์ output — "PNG" | "JPEG" (default: "PNG")
        jpeg_quality: คุณภาพ JPEG 1-100 (default: 95, ใช้เฉพาะ format JPEG)

    Returns:
        str — absolute path ของไฟล์ output ที่เซฟเรียบร้อย

    Raises:
        TemplateNotFoundError: template file หาไม่เจอ
        PhotoNotFoundError: รูปถ่ายหาไม่เจอ
        LayoutConfigError: layout_config ไม่ถูกต้อง
        ExportError: เซฟไฟล์ไม่ได้
    """
    # ========== 1. Validate ==========
    logger.info("เริ่มต้น merge_photobooth")
    logger.info("Template: %s", template_image_path)
    logger.info("Photos: %s", photo_paths)

    validate_layout_config(layout_config, len(photo_paths))

    slots = layout_config["slots"]

    # Validate fit_mode
    valid_fit_modes = ("cover", "contain", "stretch")
    if fit_mode not in valid_fit_modes:
        raise LayoutConfigError(
            f"fit_mode ต้องเป็น {valid_fit_modes} แต่ได้รับ '{fit_mode}'"
        )

    # Validate output_format
    output_format = output_format.upper()
    if output_format not in ("PNG", "JPEG"):
        raise ExportError(f"output_format ต้องเป็น 'PNG' หรือ 'JPEG' แต่ได้รับ '{output_format}'")

    # ========== 2. Load Template ==========
    template = _load_image(template_image_path, label="template")
    template = template.convert("RGBA")
    canvas_width, canvas_height = template.size
    logger.info("Template size: %dx%d", canvas_width, canvas_height)

    # ========== 3. สร้าง Canvas (เลเยอร์ล่าง) ==========
    # พื้นหลังสีขาวทึบ เพื่อไม่ให้เห็นเป็นสีดำตรงส่วนที่ไม่มีรูป
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))

    # ========== 4. วางรูปถ่ายลง Slot ==========
    for i, (photo_path, slot) in enumerate(zip(photo_paths, slots)):
        logger.info(
            "กำลังวางรูป [%d/%d]: %s → slot(%d, %d, %dx%d)",
            i + 1, len(photo_paths), photo_path,
            slot["x"], slot["y"], slot["width"], slot["height"],
        )

        photo = _load_image(photo_path, label=f"photo[{i}]")
        photo = photo.convert("RGBA")

        # Resize + Crop ให้พอดี slot
        fitted = _fit_photo_to_slot(
            photo,
            slot_width=slot["width"],
            slot_height=slot["height"],
            fit_mode=fit_mode,
        )

        # หมุนภาพ (ถ้าระบุ)
        angle = slot.get("angle", 0)
        if angle != 0:
            # Pillow: positive angle is counter-clockwise. QGraphicsItem: positive is clockwise.
            # So rotate by -angle
            fitted = fitted.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
            
            # คำนวณพิกัดมุมบนซ้ายใหม่ เพื่อให้จุดกึ่งกลางของภาพที่หมุน ตรงกับจุดกึ่งกลางของ Slot พอดี
            center_x = slot["x"] + slot["width"] / 2
            center_y = slot["y"] + slot["height"] / 2
            pos_x = int(center_x - fitted.width / 2)
            pos_y = int(center_y - fitted.height / 2)
        else:
            pos_x = int(slot["x"])
            pos_y = int(slot["y"])

        # วางลง canvas โดยใช้ mask ให้รักษาขอบที่โปร่งใสจากการหมุน
        canvas.paste(fitted, (pos_x, pos_y), mask=fitted)

        # ปิด image เพื่อปล่อย memory
        photo.close()
        fitted.close()

    # ========== 5. Overlay Template Frame ทับด้านบน ==========
    # ใช้ alpha_composite เพื่อรักษาความโปร่งใสของ template
    canvas = Image.alpha_composite(canvas, template)
    template.close()
    
    # บังคับปรับขนาดไฟล์สุดท้ายให้เป็น 1200x1800 เพื่อความคมชัดสูงสุดในการพิมพ์
    if canvas.size != (1200, 1800):
        logger.info("ปรับขนาดรูปผลลัพธ์เป็น 1200x1800 พิกเซล")
        canvas = canvas.resize((1200, 1800), Image.Resampling.LANCZOS)
        
    logger.info("Overlay template frame เรียบร้อย")

    # ========== 6. Export ==========
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        raise ExportError(f"สร้างโฟลเดอร์ output ไม่ได้: {output_dir} — {e}") from e

    # Auto-generate filename ถ้าไม่ได้ระบุ
    if not output_filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        ext = "png" if output_format == "PNG" else "jpg"
        output_filename = f"photobooth_{timestamp}.{ext}"

    output_path = os.path.join(output_dir, output_filename)

    try:
        if output_format == "JPEG":
            # JPEG ไม่รองรับ alpha → แปลงเป็น RGB ก่อน
            rgb_canvas = canvas.convert("RGB")
            rgb_canvas.save(output_path, format="JPEG", quality=jpeg_quality)
            rgb_canvas.close()
        else:
            canvas.save(output_path, format="PNG")

        canvas.close()
    except Exception as e:
        raise ExportError(f"เซฟไฟล์ output ไม่ได้: {output_path} — {e}") from e

    abs_output = os.path.abspath(output_path)
    logger.info("✅ เซฟไฟล์เรียบร้อย: %s", abs_output)
    return abs_output


# ---------------------------------------------------------------------------
# CLI / Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # ตัวอย่างการใช้งาน — รันจาก command line:
    #   python image_composer.py template.png photo1.jpg photo2.jpg layout.json
    #
    # layout.json:
    # {
    #     "total_photos": 2,
    #     "slots": [
    #         {"x": 100, "y": 150, "width": 400, "height": 300},
    #         {"x": 550, "y": 150, "width": 400, "height": 300}
    #     ]
    # }

    if len(sys.argv) < 4:
        print("Usage: python image_composer.py <template.png> <photo1> [photo2 ...] <layout.json>")
        print()
        print("  template.png  — กรอบรูป PNG (พื้นโปร่งใส)")
        print("  photo1, ...   — รูปถ่ายจากกล้อง")
        print("  layout.json   — ไฟล์ JSON ที่บอกพิกัด slots")
        sys.exit(1)

    template_path = sys.argv[1]
    layout_json_path = sys.argv[-1]
    photo_list = sys.argv[2:-1]

    with open(layout_json_path, "r", encoding="utf-8") as f:
        layout = json.load(f)

    result = merge_photobooth(template_path, photo_list, layout)
    print(f"Output: {result}")
