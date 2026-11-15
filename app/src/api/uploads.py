"""POST /uploads: スクショ用の S3 署名付き POST を発行する（要件 1.1, 1.3）。"""

from __future__ import annotations

import os
import uuid
from typing import Any

from common import clients
from common.images import ALLOWED_CONTENT_TYPES, MAX_IMAGE_BYTES, UPLOAD_KEY_PREFIX

UPLOAD_URL_EXPIRES_SECONDS = 300


class InvalidUploadError(Exception):
    """画像以外のアップロード要求。"""


def create_upload(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    content_type = payload.get("contentType")
    extension = ALLOWED_CONTENT_TYPES.get(content_type) if isinstance(content_type, str) else None
    if extension is None:
        raise InvalidUploadError("画像ファイル（PNG または JPEG）を選んでください")

    key = f"{UPLOAD_KEY_PREFIX}{user_id}/{uuid.uuid4()}.{extension}"
    post = clients.s3_client().generate_presigned_post(
        Bucket=os.environ["BUCKET_NAME"],
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, MAX_IMAGE_BYTES],
        ],
        ExpiresIn=UPLOAD_URL_EXPIRES_SECONDS,
    )
    return {"url": post["url"], "fields": post["fields"], "key": key, "maxBytes": MAX_IMAGE_BYTES}
