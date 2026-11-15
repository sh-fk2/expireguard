"""画像まわりの共通定義。"""

from __future__ import annotations

# Bedrock Converse の画像上限（3.75MB）に合わせる。アップロード時と抽出時の両方で検査する
MAX_IMAGE_BYTES = 3_750_000

# アップロードを許可する Content-Type と拡張子
ALLOWED_CONTENT_TYPES = {"image/png": "png", "image/jpeg": "jpg"}

UPLOAD_KEY_PREFIX = "uploads/"


def detect_image_format(data: bytes) -> str | None:
    """先頭のマジックバイトから Converse 用の形式名（png/jpeg）を判定する。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None
