#!/usr/bin/env python3
"""Vertex AI 的 OAuth2 token —— 纯标准库，不依赖 google-auth SDK。

本环境里 `import google.auth` 会失败（没装），`gcloud` 也不在 PATH 上
（SDK 在 /usr/lib/google-cloud-sdk 但没链接过去）。所以自己拿 token。

三条路径，按顺序尝试：
  1. ADC 文件里的 refresh_token 去 oauth2.googleapis.com 换 access_token
  2. GCE/Cloudtop metadata server
  3. gcloud 二进制（会去常见安装路径找，不只看 PATH）

token 在内存里缓存到过期前 60 秒，避免每条请求都换一次。
"""

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

ADC_PATH = os.path.expanduser(
    "~/.config/gcloud/application_default_credentials.json")
TOKEN_URL = "https://oauth2.googleapis.com/token"
METADATA_URL = ("http://metadata.google.internal/computeMetadata/v1/"
                "instance/service-accounts/default/token")
GCLOUD_CANDIDATES = [
    "/usr/lib/google-cloud-sdk/bin/gcloud",
    os.path.expanduser("~/google-cloud-sdk/bin/gcloud"),
    "/opt/google-cloud-sdk/bin/gcloud",
    "gcloud",
]


class AuthError(RuntimeError):
    pass


class TokenProvider(object):
    """线程安全的 access token 缓存。"""

    def __init__(self, adc_path: str = ADC_PATH):
        self.adc_path = adc_path
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._expires_at = 0.0
        self.source = "?"

    def token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            tok, ttl, src = self._fetch()
            self._token = tok
            self._expires_at = time.time() + ttl
            self.source = src
            return tok

    # ---- 具体获取方式 ----
    def _fetch(self):
        errors = []
        for fn in (self._from_adc, self._from_metadata, self._from_gcloud):
            try:
                return fn()
            except Exception as exc:          # noqa: BLE001 逐个降级
                errors.append("%s: %s" % (fn.__name__, exc))
        raise AuthError("拿不到 Vertex 的 access token。尝试过：\n  %s"
                        % "\n  ".join(errors))

    def _from_adc(self):
        if not os.path.exists(self.adc_path):
            raise AuthError("没有 ADC 文件 %s" % self.adc_path)
        with open(self.adc_path, encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("type") == "service_account":
            # 服务账号要签 JWT，标准库做不了 RS256。这种情况交给 gcloud。
            raise AuthError("ADC 是 service_account，标准库签不了 JWT，改用 gcloud")
        if not d.get("refresh_token"):
            raise AuthError("ADC 里没有 refresh_token")
        body = urllib.parse.urlencode({
            "client_id": d["client_id"],
            "client_secret": d["client_secret"],
            "refresh_token": d["refresh_token"],
            "grant_type": "refresh_token",
        }).encode("utf-8")
        req = urllib.request.Request(
            TOKEN_URL, data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as fh:
            tok = json.loads(fh.read().decode("utf-8"))
        return tok["access_token"], float(tok.get("expires_in", 3600)), "adc"

    def _from_metadata(self):
        req = urllib.request.Request(METADATA_URL,
                                     headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(req, timeout=5) as fh:
            tok = json.loads(fh.read().decode("utf-8"))
        return tok["access_token"], float(tok.get("expires_in", 3600)), "metadata"

    def _from_gcloud(self):
        for exe in GCLOUD_CANDIDATES:
            try:
                out = subprocess.run([exe, "auth", "print-access-token"],
                                     capture_output=True, text=True, timeout=60)
            except (OSError, subprocess.SubprocessError):
                continue
            if out.returncode == 0 and out.stdout.strip():
                # gcloud 不告诉我们有效期，按最短的 1 小时算
                return out.stdout.strip(), 3600.0, "gcloud(%s)" % exe
        raise AuthError("找不到可用的 gcloud")


def adc_quota_project(adc_path: str = ADC_PATH) -> Optional[str]:
    """ADC 里记的 quota project。

    Vertex 用本地 ADC 调用时必须带 x-goog-user-project，否则 403
    （报错原文：Your application is authenticating by using local
    Application Default Credentials... requires a quota project）。
    """
    try:
        with open(adc_path, encoding="utf-8") as fh:
            return json.load(fh).get("quota_project_id")
    except Exception:
        return None


_DEFAULT = TokenProvider()


def token() -> str:
    return _DEFAULT.token()


def source() -> str:
    return _DEFAULT.source


if __name__ == "__main__":
    t = token()
    print("token 前缀 %s… 长度 %d  来源 %s" % (t[:12], len(t), source()))
    print("ADC quota project:", adc_quota_project())
