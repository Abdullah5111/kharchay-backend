import os
import uuid
from django.core.files.storage import default_storage

ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 8 * 1024 * 1024


def _sniff_is_image(head: bytes) -> bool:
    # Verify by magic bytes — the multipart content_type is client-supplied and
    # can be spoofed (e.g. an SVG/HTML payload labelled image/jpeg).
    return (
        head.startswith(b"\xff\xd8\xff")  # JPEG
        or head.startswith(b"\x89PNG\r\n\x1a\n")  # PNG
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")  # WebP
    )


def validate_image(f):
    if f.size > MAX_BYTES:
        raise ValueError("Image too large (max 8 MB).")
    if (f.content_type or "").lower() not in ALLOWED_TYPES:
        raise ValueError("Unsupported image type. Use JPEG, PNG, or WebP.")
    head = f.read(12)
    f.seek(0)
    if not _sniff_is_image(head):
        raise ValueError("File is not a valid JPEG, PNG, or WebP image.")


def save_proof(group_id, f):
    ext = os.path.splitext(f.name or "")[1].lower()
    if ext not in ALLOWED_EXT:
        ext = ".jpg"
    key = f"proofs/{group_id}/{uuid.uuid4().hex}{ext}"
    return default_storage.save(key, f)
