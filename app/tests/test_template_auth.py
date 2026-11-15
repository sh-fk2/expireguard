"""template.yaml の認証設定を検証する（IaC のリグレッション防止）。

sam validate --lint では「全ルートが認証必須」などの意図までは確認できないため、
テンプレートを読み込んで設定値を直接検査する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

TEMPLATE = Path(__file__).resolve().parent.parent / "template.yaml"
EXPECTED_ROUTES = {
    ("POST", "/uploads"),
    ("POST", "/extract"),
    ("GET", "/items"),
    ("POST", "/items"),
    ("PATCH", "/items/{id}"),
    ("DELETE", "/items/{id}"),
    ("GET", "/summary"),
    ("POST", "/notify/test"),
}


class _Loader(yaml.SafeLoader):
    """CloudFormation の短縮記法（!Ref など）を素のデータとして読む。"""


def _construct(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {tag_suffix: value}


_Loader.add_multi_constructor("!", _construct)


@pytest.fixture(scope="module")
def tpl() -> dict[str, Any]:
    return yaml.load(TEMPLATE.read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506


def _resources(tpl: dict[str, Any], rtype: str) -> list[dict[str, Any]]:
    return [r for r in tpl["Resources"].values() if r["Type"] == rtype]


def test_ユーザープールはセルフサインアップ無効でメールをユーザー名にする(tpl):
    pool = tpl["Resources"]["UserPool"]["Properties"]
    assert pool["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"] is True
    assert pool["UsernameAttributes"] == ["email"]


def test_パスワードポリシーは12文字以上で全文字種を要求する(tpl):
    policy = tpl["Resources"]["UserPool"]["Properties"]["Policies"]["PasswordPolicy"]
    assert policy["MinimumLength"] >= 12
    for key in ("RequireLowercase", "RequireUppercase", "RequireNumbers", "RequireSymbols"):
        assert policy[key] is True


def test_ユーザープールは置き換え時と削除時に保持される(tpl):
    pool = tpl["Resources"]["UserPool"]
    assert pool["DeletionPolicy"] == "Retain"
    assert pool["UpdateReplacePolicy"] == "Retain"


def test_アプリクライアントはシークレットなしで必要なフローだけ許す(tpl):
    client = tpl["Resources"]["UserPoolClient"]["Properties"]
    assert client["GenerateSecret"] is False
    assert sorted(client["ExplicitAuthFlows"]) == [
        "ALLOW_REFRESH_TOKEN_AUTH",
        "ALLOW_USER_PASSWORD_AUTH",
    ]
    assert client["PreventUserExistenceErrors"] == "ENABLED"


def test_HTTP_APIは既定オーソライザーがCognitoのJWT(tpl):
    auth = tpl["Resources"]["HttpApi"]["Properties"]["Auth"]
    assert auth["DefaultAuthorizer"] == "CognitoJwt"
    jwt = auth["Authorizers"]["CognitoJwt"]
    assert jwt["IdentitySource"] == "$request.header.Authorization"
    assert jwt["JwtConfiguration"]["audience"] == [{"Ref": "UserPoolClient"}]
    assert "UserPool" in str(jwt["JwtConfiguration"]["issuer"])


def test_全ルートが認証必須でオーソライザー無効化がない(tpl):
    routes: set[tuple[str, str]] = set()
    for func in _resources(tpl, "AWS::Serverless::Function"):
        for event in func["Properties"].get("Events", {}).values():
            if event["Type"] != "HttpApi":
                continue
            props = event["Properties"]
            routes.add((props["Method"], props["Path"]))
            # Auth.Authorizer: NONE などで個別に認証を外していないこと
            assert "Auth" not in props, f"認証設定の上書き: {props}"
    assert routes == EXPECTED_ROUTES


def test_CORSは既存オリジンを維持しAuthorizationヘッダーを許可する(tpl):
    cors = tpl["Resources"]["HttpApi"]["Properties"]["CorsConfiguration"]
    assert "Authorization" in cors["AllowHeaders"]
    assert "OPTIONS" in cors["AllowMethods"]
    assert "http://localhost:8080" in cors["AllowOrigins"]
    assert len(cors["AllowOrigins"]) == 2


def test_Outputsにユーザープール情報がある(tpl):
    assert tpl["Outputs"]["UserPoolId"]["Value"] == {"Ref": "UserPool"}
    assert tpl["Outputs"]["UserPoolClientId"]["Value"] == {"Ref": "UserPoolClient"}


def test_テンプレートに固定ユーザーの権限や認証情報が残っていない():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "demo-user" not in text
