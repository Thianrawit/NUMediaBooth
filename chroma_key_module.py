import numpy as np
from scipy import ndimage
from PIL import Image
import logging

logger = logging.getLogger(__name__)

def remove_color_background(image: Image.Image, target_rgb: tuple[int, int, int], tolerance: int, edge_crop: int, roi_rect: tuple[int, int, int, int] | None = None) -> Image.Image:
    """
    ลบพื้นหลังตามสีที่ระบุ โดยใช้ Tolerance (ความคลาดเคลื่อนสี) และ Edge Crop (กัดขอบ)
    
    Args:
        image: รูปภาพต้นฉบับ (PIL.Image) โหมด RGBA หรือ RGB
        target_rgb: สีที่ต้องการลบ (R, G, B)
        tolerance: ค่าความคลาดเคลื่อนที่ยอมรับได้ (0-255)
        edge_crop: จำนวนพิกเซลที่ต้องการกัดขอบ (erosion) เพื่อลดขอบสีเขียวที่ติดมา
        roi_rect: (x, y, w, h) พื้นที่ที่ต้องการลบสี ถ้า None = ลบทั้งภาพ
        
    Returns:
        รูปภาพที่ตัดพื้นหลังให้โปร่งใสแล้ว (PIL.Image โหมด RGBA)
    """
    # ทำให้มั่นใจว่าเป็น RGBA
    if image.mode != "RGBA":
        image = image.convert("RGBA")
        
    # แปลงเป็น Numpy Array
    img_array = np.array(image)
    
    # ดึงเฉพาะช่องสี R, G, B (ไม่เอา Alpha มาคำนวณระยะห่างสี)
    r, g, b, a = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2], img_array[:,:,3]
    
    tr, tg, tb = target_rgb
    
    # คำนวณความแตกต่างของสีแบบง่าย (หรือจะใช้ Euclidean distance ก็ได้)
    # ใช้ Euclidean distance ค่อนข้างแม่นยำกว่า
    color_diff = np.sqrt(
        (r.astype(np.float32) - tr)**2 +
        (g.astype(np.float32) - tg)**2 +
        (b.astype(np.float32) - tb)**2
    )
    
    # สร้าง Mask ของส่วนที่ "ต้องถูกลบ" (สีใกล้เคียงกับ target_rgb ภายใน tolerance)
    # ถ้าค่า diff <= tolerance ถือว่าเป็นพื้นหลังที่จะลบ
    # แปลว่า mask_to_remove เป็น True ตรงที่เป็นพื้นหลัง
    mask_to_remove = color_diff <= tolerance
    
    # ถ้ามี ROI (Region of Interest) ให้จำกัดการลบเฉพาะในกรอบ
    if roi_rect is not None:
        rx, ry, rw, rh = roi_rect
        h_img, w_img = img_array.shape[:2]
        
        # Clamp ค่าให้อยู่ในขอบเขตภาพ
        rx = max(0, min(rx, w_img))
        ry = max(0, min(ry, h_img))
        rw = max(0, min(rw, w_img - rx))
        rh = max(0, min(rh, h_img - ry))
        
        # สร้าง ROI mask (เปิดเฉพาะพื้นที่สี่เหลี่ยมที่กำหนด)
        roi_mask = np.zeros(mask_to_remove.shape, dtype=bool)
        roi_mask[ry:ry+rh, rx:rx+rw] = True
        
        # AND กับ chroma mask → ลบสีเฉพาะในกรอบ
        mask_to_remove = mask_to_remove & roi_mask
    
    # ถ้ามีการกัดขอบ (Edge Crop/Erosion) ให้ขยายขนาดของ Mask พื้นหลังเข้าไปในตัวภาพ
    if edge_crop > 0:
        # ใช้ binary_dilation ขยายพื้นที่ mask_to_remove เข้าไปกินตัวภาพจริง
        # กัด 1 px = iterations 1
        mask_to_remove = ndimage.binary_dilation(mask_to_remove, iterations=edge_crop)
        
    # อัปเดตช่อง Alpha (A) ให้เป็น 0 (โปร่งใส) ตรงที่ mask_to_remove เป็น True
    img_array[mask_to_remove, 3] = 0
    
    # คืนค่ากลับเป็น PIL.Image
    return Image.fromarray(img_array, mode="RGBA")


def apply_multi_layer_chroma(image: Image.Image, layers: list[dict]) -> Image.Image:
    """
    ประมวลผลลบพื้นหลังหลาย Layer พร้อมกัน อย่างมีประสิทธิภาพ
    โดยสะสม Mask รวมจากทุก Layer แล้ว Apply ทีเดียว
    
    Args:
        image: รูปภาพต้นฉบับ (PIL.Image)
        layers: รายการ Layer แต่ละตัวเป็น dict:
            {
                "color": (r, g, b),
                "rect": (x, y, w, h) or None,  
                "tolerance": int,
                "edge_crop": int
            }
            
    Returns:
        รูปภาพที่ตัดพื้นหลังให้โปร่งใสแล้ว (PIL.Image โหมด RGBA)
    """
    if not layers:
        return image.copy()
        
    # ทำให้มั่นใจว่าเป็น RGBA
    if image.mode != "RGBA":
        image = image.convert("RGBA")
        
    img_array = np.array(image)
    h_img, w_img = img_array.shape[:2]
    
    # สร้าง Mask รวม (False ทั้งหมด = ยังไม่ลบอะไร)
    combined_mask = np.zeros((h_img, w_img), dtype=bool)
    
    r, g, b = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2]
    
    for layer in layers:
        color = layer.get("color")
        if color is None:
            continue
            
        tr, tg, tb = color
        tolerance = layer.get("tolerance", 30)
        edge_crop = layer.get("edge_crop", 0)
        roi_rect = layer.get("rect")
        
        # คำนวณ Euclidean distance
        color_diff = np.sqrt(
            (r.astype(np.float32) - tr)**2 +
            (g.astype(np.float32) - tg)**2 +
            (b.astype(np.float32) - tb)**2
        )
        
        layer_mask = color_diff <= tolerance
        
        # จำกัดการลบเฉพาะ ROI ถ้ามี
        if roi_rect is not None:
            rx, ry, rw, rh = roi_rect
            rx = max(0, min(rx, w_img))
            ry = max(0, min(ry, h_img))
            rw = max(0, min(rw, w_img - rx))
            rh = max(0, min(rh, h_img - ry))
            
            roi_mask = np.zeros(layer_mask.shape, dtype=bool)
            roi_mask[ry:ry+rh, rx:rx+rw] = True
            layer_mask = layer_mask & roi_mask
        
        # กัดขอบ (Edge Crop) ถ้ามี
        if edge_crop > 0:
            layer_mask = ndimage.binary_dilation(layer_mask, iterations=edge_crop)
        
        # สะสม Mask รวม (OR) — ถ้า layer ไหนบอกลบ ก็ลบ
        combined_mask = combined_mask | layer_mask
    
    # Apply Mask รวมทีเดียว
    img_array[combined_mask, 3] = 0
    
    return Image.fromarray(img_array, mode="RGBA")
