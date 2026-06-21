import os
import uuid
from django.core.files.storage import default_storage

ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 8 * 1024 * 1024


def validate_image(f):
    if f.size > MAX_BYTES:
        raise ValueError("Image too large (max 8 MB).")
    if (f.content_type or "").lower() not in ALLOWED_TYPES:
        raise ValueError("Unsupported image type. Use JPEG, PNG, or WebP.")


def save_proof(group_id, f):
    ext = os.path.splitext(f.name or "")[1].lower()
    if ext not in ALLOWED_EXT:
        ext = ".jpg"
    key = f"proofs/{group_id}/{uuid.uuid4().hex}{ext}"
    return default_storage.save(key, f)
