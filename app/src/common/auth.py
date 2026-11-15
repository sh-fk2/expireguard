"""認証情報の取り出し（HTTP API の JWT オーソライザー通過後の claims）。

署名・期限・audience の検証は API Gateway の JWT オーソライザーが行う。
Lambda 側は多層防御として、検証済み claims の sub が無いリクエストを拒否する。
"""

from __future__ import annotations

import re
from typing import Any

# Cognito の sub は UUID。S3 キーの一部にもなるため、区切り文字（/ や ..）を含む値は拒否する
_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class UnauthorizedError(Exception):
    """認証済みユーザーを特定できないリクエスト。"""


def user_id_from_event(event: dict[str, Any]) -> str:
    """requestContext.authorizer.jwt.claims.sub をユーザー ID として返す。"""
    context = event.get("requestContext") or {}
    authorizer = context.get("authorizer") or {}
    jwt = authorizer.get("jwt") or {}
    claims = jwt.get("claims") or {}
    sub = claims.get("sub") if isinstance(claims, dict) else None
    if not isinstance(sub, str) or not _USER_ID_PATTERN.fullmatch(sub):
        raise UnauthorizedError("認証が必要です")
    return sub
