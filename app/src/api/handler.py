"""api Lambda: アイテム CRUD・/summary・/uploads（HTTP API payload v2）。"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from api.summary import build_summary, sort_by_expiry
from api.uploads import InvalidUploadError, create_upload
from common import dates
from common.auth import UnauthorizedError, user_id_from_event
from common.models import (
    KIND_POINTS,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_DRAFT,
    STATUS_USED,
    ValidationError,
    validate_item_fields,
)
from common.repo import ItemNotFoundError, get_repository
from common.responses import BadRequestError, error, parse_body, respond

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# PATCH で更新を許す項目（kind は変更不可）
_PATCHABLE = ("service", "points", "amount", "expiryDate", "cycle", "isLimited")
# 種別ごとに許す状態遷移の操作
_STATUS_ACTIONS = {KIND_POINTS: STATUS_USED, "subscription": STATUS_CANCELLED}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _list_items(user_id: str, _event: dict[str, Any]) -> dict[str, Any]:
    items = [i for i in get_repository().list_all(user_id) if i.get("status") != STATUS_DRAFT]
    return respond(200, {"items": sort_by_expiry(items)})


def _summary(user_id: str, _event: dict[str, Any]) -> dict[str, Any]:
    return respond(200, build_summary(get_repository().list_all(user_id), dates.jst_today()))


def _uploads(user_id: str, event: dict[str, Any]) -> dict[str, Any]:
    try:
        return respond(200, create_upload(user_id, parse_body(event)))
    except InvalidUploadError as exc:
        return error(400, str(exc))


def _create_item(user_id: str, event: dict[str, Any]) -> dict[str, Any]:
    payload = parse_body(event)
    fields = validate_item_fields(payload)
    repo = get_repository()
    now = _now()
    draft_id = payload.get("draftId")

    item: dict[str, Any] = {
        "userId": user_id,
        "itemId": str(uuid.uuid4()),
        **fields,
        "status": STATUS_ACTIVE,
        "createdAt": now,
        "updatedAt": now,
    }
    if draft_id is None:
        repo.put(item)
        return respond(201, item)

    # 確認画面からの確定: 同じ itemId の下書きを active で置き換える（ttl は消える）
    draft = repo.get(user_id, draft_id) if isinstance(draft_id, str) else None
    if draft is None or draft.get("status") != STATUS_DRAFT:
        return error(404, "下書きが見つかりません")
    item["itemId"] = draft["itemId"]
    item["createdAt"] = draft.get("createdAt", now)
    if draft.get("sourceImageKey"):
        item["sourceImageKey"] = draft["sourceImageKey"]
    repo.replace(item)
    return respond(201, item)


def _update_item(user_id: str, event: dict[str, Any]) -> dict[str, Any]:
    item_id = (event.get("pathParameters") or {}).get("id", "")
    payload = parse_body(event)
    repo = get_repository()
    existing = repo.get(user_id, item_id)
    if existing is None:
        return error(404, "アイテムが見つかりません")
    if existing.get("status") != STATUS_ACTIVE:
        return error(409, "有効（active）なアイテムのみ更新できます")

    new_status = payload.get("status")
    if new_status is not None and new_status != _STATUS_ACTIONS.get(existing.get("kind")):
        return error(400, "この種別では指定された状態に変更できません", fields=["status"])

    merged = {**existing, **{k: payload[k] for k in _PATCHABLE if k in payload}}
    fields = validate_item_fields(merged)

    updated = {**existing, **fields, "updatedAt": _now()}
    if fields["expiryDate"] != existing.get("expiryDate"):
        updated.pop("lastNotifiedStage", None)  # 期限が変われば通知ステージを最初から
    if new_status is not None:
        updated["status"] = new_status
    repo.replace(updated)
    return respond(200, updated)


def _delete_item(user_id: str, event: dict[str, Any]) -> dict[str, Any]:
    item_id = (event.get("pathParameters") or {}).get("id", "")
    get_repository().delete(user_id, item_id)
    return respond(204)


_ROUTES = {
    "GET /summary": _summary,
    "GET /items": _list_items,
    "POST /uploads": _uploads,
    "POST /items": _create_item,
    "PATCH /items/{id}": _update_item,
    "DELETE /items/{id}": _delete_item,
}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    route = _ROUTES.get(event.get("routeKey", ""))
    if route is None:
        return error(404, "ルートが見つかりません")
    try:
        return route(user_id_from_event(event), event)
    except UnauthorizedError as exc:
        return error(401, str(exc))
    except BadRequestError as exc:
        return error(400, str(exc))
    except ValidationError as exc:
        return error(400, exc.message, fields=exc.fields)
    except ItemNotFoundError:
        return error(404, "アイテムが見つかりません")
    except Exception:
        # 詳細はログにのみ残し、利用者には内部情報を返さない
        logger.exception("unexpected error")
        return error(500, "サーバーエラーが発生しました")
