"""DynamoDB アイテムテーブルのアクセス層。"""

from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from common import clients

_CONDITION_FAILED = "ConditionalCheckFailedException"


class ItemNotFoundError(Exception):
    """対象アイテムが存在しない。"""


def _plain(value: Any) -> Any:
    """DynamoDB の Decimal を int / float に戻す。"""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


class ItemRepository:
    def __init__(self, table: Any) -> None:
        self._table = table

    def list_all(self, user_id: str) -> list[dict[str, Any]]:
        """ユーザーの全アイテムを取得する（件数が少ない前提で全ページ読む）。"""
        return self._read_all(
            {"KeyConditionExpression": Key("userId").eq(user_id), "ConsistentRead": True},
            self._table.query,
        )

    def scan_all(self) -> list[dict[str, Any]]:
        """全ユーザーの全アイテムを取得する。日次通知バッチ専用（API からは使わない）。"""
        return self._read_all({"ConsistentRead": True}, self._table.scan)

    @staticmethod
    def _read_all(kwargs: dict[str, Any], read_page: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            page = read_page(**kwargs)
            items.extend(_plain(i) for i in page.get("Items", []))
            last = page.get("LastEvaluatedKey")
            if not last:
                return items
            kwargs = {**kwargs, "ExclusiveStartKey": last}

    def get(self, user_id: str, item_id: str) -> dict[str, Any] | None:
        res = self._table.get_item(Key={"userId": user_id, "itemId": item_id}, ConsistentRead=True)
        item = res.get("Item")
        return _plain(item) if item else None

    def put(self, item: dict[str, Any]) -> None:
        self._table.put_item(Item=item)

    def replace(self, item: dict[str, Any]) -> None:
        """既存アイテムを丸ごと置き換える。無ければ ItemNotFoundError。"""
        try:
            self._table.put_item(Item=item, ConditionExpression="attribute_exists(itemId)")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == _CONDITION_FAILED:
                raise ItemNotFoundError(item.get("itemId")) from exc
            raise

    def delete(self, user_id: str, item_id: str) -> None:
        try:
            self._table.delete_item(
                Key={"userId": user_id, "itemId": item_id},
                ConditionExpression="attribute_exists(itemId)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == _CONDITION_FAILED:
                raise ItemNotFoundError(item_id) from exc
            raise

    def set_notified_stage(self, user_id: str, item_id: str, stage: str) -> None:
        self._table.update_item(
            Key={"userId": user_id, "itemId": item_id},
            UpdateExpression="SET lastNotifiedStage = :s",
            ExpressionAttributeValues={":s": stage},
        )

    def set_renewal_date(self, user_id: str, item_id: str, expiry_date: str) -> None:
        """更新日を繰り上げ、通知ステージをリセットする。"""
        self._table.update_item(
            Key={"userId": user_id, "itemId": item_id},
            UpdateExpression="SET expiryDate = :d REMOVE lastNotifiedStage",
            ExpressionAttributeValues={":d": expiry_date},
        )


@lru_cache(maxsize=1)
def get_repository() -> ItemRepository:
    table = clients.dynamodb_resource().Table(os.environ["TABLE_NAME"])
    return ItemRepository(table)
