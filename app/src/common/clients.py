"""AWS クライアントの生成。テストでは差し替え・キャッシュ破棄ができるようにする。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

# Bedrock の画像抽出は数秒〜十数秒かかるため、読み取り待ちを長めにする
_BEDROCK_CONFIG = Config(read_timeout=60, retries={"max_attempts": 2, "mode": "standard"})
# 署名付きURLは署名バージョン4を明示する
_S3_CONFIG = Config(signature_version="s3v4")


@lru_cache(maxsize=1)
def dynamodb_resource() -> Any:
    return boto3.resource("dynamodb")


@lru_cache(maxsize=1)
def s3_client() -> Any:
    return boto3.client("s3", config=_S3_CONFIG)


@lru_cache(maxsize=1)
def bedrock_client() -> Any:
    return boto3.client("bedrock-runtime", config=_BEDROCK_CONFIG)


@lru_cache(maxsize=1)
def ses_client() -> Any:
    return boto3.client("sesv2")


def reset_caches() -> None:
    """テスト用: キャッシュ済みクライアントを破棄する。"""
    for factory in (dynamodb_resource, s3_client, bedrock_client, ses_client):
        # テストで差し替え済み（キャッシュ機構なし）の場合は何もしない
        clear = getattr(factory, "cache_clear", None)
        if clear is not None:
            clear()
    from common import repo

    repo.get_repository.cache_clear()
