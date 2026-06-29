#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path


class ConciliumClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.token = str(token)

    @classmethod
    def from_token_file(cls, path: str | Path) -> "ConciliumClient":
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        return cls(payload["base_url"], payload["token"])

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-Loop-Token": self.token,
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload or "{}")

    def status(self) -> dict:
        return self._request("GET", "/api/status")

    def preflight(self, request: dict) -> dict:
        return self._request("POST", "/api/preflight", request)

    def run(self, request: dict, confirmation: dict | None = None) -> dict:
        payload = dict(request)
        if confirmation is not None:
            payload["confirmation"] = confirmation
        return self._request("POST", "/api/run", payload)

    def events(self, run_id: str) -> str:
        query = urllib.parse.urlencode({"run": run_id})
        request = urllib.request.Request(
            self.base_url + "/api/events?" + query,
            method="GET",
            headers={"X-Loop-Token": self.token},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")

    def effective_config(self, repo: str) -> dict:
        query = urllib.parse.urlencode({"repo": repo})
        return self._request("GET", "/api/config/effective?" + query)

    def save_config(self, target: str, patch: dict) -> dict:
        del target, patch
        return {
            "status": "not_implemented",
            "reason": "Config writes are deferred to Phase 5.",
        }
