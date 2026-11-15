"""extract Lambda: S3 の画像を Bedrock で読み取り、下書きとして保存する。

抽出に失敗した場合や空の場合は例外にせず、空の結果を返して手入力フォームに落とす（要件 2.5）。
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from common import clients
from common.auth import UnauthorizedError, user_id_from_event
from common.images import MAX_IMAGE_BYTES, UPLOAD_KEY_PREFIX, detect_image_format
from common.models import STATUS_DRAFT
from common.repo import get_repository
from common.responses import BadRequestError, error, parse_body, respond
from extract import prompts
from extract.parser import normalize_points, normalize_subscriptions, parse_model_json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DRAFT_TTL_SECONDS = 7 * 24 * 3600  # 確認されない下書きは7日で自動削除
MAX_OUTPUT_TOKENS = 2048
_MAX_KEY_LENGTH = 200


def _validate_key(user_id: str, key: object) -> str:
    """呼び出しユーザー自身のプレフィックス配下のキーだけを許す（他ユーザーの画像は読ませない）。"""
    if (
        not isinstance(key, str)
        or not key.startswith(f"{UPLOAD_KEY_PREFIX}{user_id}/")
        or ".." in key
        or len(key) > _MAX_KEY_LENGTH
    ):
        raise BadRequestError("画像キーが不正です")
    return key


def _ask_model(image: bytes, image_format: str, prompt: str) -> Any | None:
    """Bedrock に1回問い合わせ、応答 JSON を返す。読めなければ None。"""
    response = clients.bedrock_client().converse(
        modelId=os.environ["BEDROCK_MODEL_ID"],
        messages=[
            {
                "role": "user",
                "content": [
                    {"image": {"format": image_format, "source": {"bytes": image}}},
                    {"text": prompt},
                ],
            }
        ],
        inferenceConfig={"maxTokens": MAX_OUTPUT_TOKENS, "temperature": 0},
    )
    blocks = response["output"]["message"]["content"]
    text = "".join(b["text"] for b in blocks if "text" in b)
    return parse_model_json(text)


def _extract(image: bytes, image_format: str) -> list[dict[str, Any]]:
    """まずポイント用で試し、ロットが取れなければサブスク用で再試行する。"""
    lots = normalize_points(_ask_model(image, image_format, prompts.POINTS_PROMPT))
    if lots:
        return lots
    return normalize_subscriptions(_ask_model(image, image_format, prompts.SUBSCRIPTION_PROMPT))


def _save_drafts(user_id: str, parsed: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    repo = get_repository()
    now = datetime.now(UTC).isoformat()
    ttl = int(time.time()) + DRAFT_TTL_SECONDS
    drafts = []
    for fields in parsed:
        draft = {
            "userId": user_id,
            "itemId": str(uuid.uuid4()),
            **fields,
            "status": STATUS_DRAFT,
            "sourceImageKey": key,
            "createdAt": now,
            "updatedAt": now,
            "ttl": ttl,
        }
        repo.put(draft)
        drafts.append(draft)
    return drafts


def _load_image(key: str) -> bytes:
    """S3 から画像を取得する。サイズ超過は先頭を読まずに弾く。"""
    s3 = clients.s3_client()
    obj = s3.get_object(Bucket=os.environ["BUCKET_NAME"], Key=key)
    if obj["ContentLength"] > MAX_IMAGE_BYTES:
        raise BadRequestError("画像が大きすぎます")
    return obj["Body"].read()


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        user_id = user_id_from_event(event)
        key = _validate_key(user_id, parse_body(event).get("key"))
        try:
            image = _load_image(key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return error(404, "画像が見つかりません")
            raise
        image_format = detect_image_format(image)
        if image_format is None:
            return error(400, "PNG または JPEG の画像を選んでください")

        try:
            parsed = _extract(image, image_format)
        except (ClientError, BotoCoreError):
            # モデル未有効化・権限・一時障害でも、利用者は手入力へ進める
            logger.exception("bedrock extraction failed")
            parsed = []

        drafts = _save_drafts(user_id, parsed, key)
        return respond(200, {"items": drafts, "extracted": bool(drafts), "sourceImageKey": key})
    except UnauthorizedError as exc:
        return error(401, str(exc))
    except BadRequestError as exc:
        return error(400, str(exc))
    except Exception:
        logger.exception("unexpected error")
        return error(500, "サーバーエラーが発生しました")
