"""平台 HTTP 客户端：生成器与 mydatama 平台的唯一耦合点。

只依赖平台公开 HTTP 契约（登录页 + /api/**），不读平台源码、不连数据库。
兼容平台版本：v0.1.0（见 README 兼容矩阵）。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests


class PlatformError(RuntimeError):
    pass


class PlatformClient:
    def __init__(self, base_url: str, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.timeout = timeout
        self.token: str | None = None
        self.user: dict[str, Any] = {}

    # ---------- 基础 ----------
    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        if not resp.content:
            return None
        body = resp.json()
        if body.get("code", 0) != 0:
            raise PlatformError(f"{method} {path} -> code={body.get('code')} message={body.get('message')}")
        return body.get("data")

    def wait_healthy(self, attempts: int = 60) -> None:
        """探测门户首页（portal nginx 托管，返回 HTML 即视为平台已起）。"""
        last = None
        for _ in range(attempts):
            try:
                r = self.session.get(f"{self.base_url}/", timeout=5)
                if r.status_code in (200, 304):
                    return
            except requests.RequestException as exc:
                last = exc
            time.sleep(2)
        raise PlatformError(f"平台不可达 {self.base_url}: {last}")

    def login(self, username: str, password: str) -> None:
        data = self._request("POST", "/api/auth/login",
                             json={"username": username, "password": password})
        self.token = data["accessToken"]
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        # 登录响应已包含用户信息（前端同样直接使用，避免依赖额外的 /me 接口）
        self.user = data.get("user") or {}

    def auth_state(self) -> dict[str, Any]:
        """供 Playwright 注入 localStorage（键名 mydatama_auth 与前端约定一致）。"""
        return {"accessToken": self.token, "refreshToken": "", "user": self.user}

    # ---------- PROC ----------
    def upload_file(self, file_path: Path, biz_domain: str, secret_level: int) -> int:
        with file_path.open("rb") as fh:
            data = self._request(
                "POST", "/api/processing/files",
                files={"file": (file_path.name, fh, "application/octet-stream")},
                data={"bizDomain": biz_domain, "secretLevel": str(secret_level)},
            )
        return data["fileId"]

    def file_detail(self, file_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/processing/files/{file_id}")

    def wait_ready(self, file_id: int, timeout: int | None = None) -> dict[str, Any]:
        deadline = time.time() + (timeout or 300)
        while time.time() < deadline:
            detail = self.file_detail(file_id)
            status = detail.get("status")
            if status == "READY":
                return detail
            if status == "FAILED":
                raise PlatformError(f"文件 {file_id} 处理失败: {detail.get('errorMsg') or detail}")
            time.sleep(3)
        raise PlatformError(f"文件 {file_id} 在 {timeout}s 内未 READY")

    def repair(self, file_id: int) -> None:
        try:
            self._request("POST", f"/api/processing/files/{file_id}/repair")
            self.wait_ready(file_id)
        except PlatformError as exc:
            print(f"[scenario]  修复重跑跳过（不影响主流程）: {exc}")

    # ---------- GOV ----------
    def list_assets(self, keyword: str = "") -> list[dict[str, Any]]:
        data = self._request("GET", "/api/governance/assets",
                             params={"keyword": keyword, "page": 1, "size": 100})
        return data.get("list", [])

    # ---------- DS ----------
    def create_dataset(self, name: str, scenario: str, filter_cond: dict,
                       description: str = "") -> int:
        data = self._request("POST", "/api/dataset/datasets", json={
            "name": name, "scenario": scenario,
            "description": description, "filterCond": filter_cond,
        })
        return data["id"]

    def create_version(self, dataset_id: int, change_note: str) -> dict[str, Any]:
        return self._request("POST", f"/api/dataset/datasets/{dataset_id}/versions",
                             json={"changeNote": change_note})

    # ---------- PROD ----------
    def templates(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/product/templates")

    def template_id_by_code(self, code: str) -> int:
        for tpl in self.templates():
            if tpl.get("code") == code:
                return tpl["id"]
        raise PlatformError(f"产品模板不存在: {code}")

    def create_product(self, payload: dict) -> int:
        return self._request("POST", "/api/product/products", json=payload)["id"]

    def product_action(self, product_id: int, action: str) -> Any:
        return self._request("POST", f"/api/product/products/{product_id}/{action}")
