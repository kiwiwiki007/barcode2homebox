"""运行时配置持久化。

把「用户可在界面填写」的配置（GS1 / Vision / Homebox Token）从环境变量里抽出来，
存到挂载卷 /app/data/config.json，重启不丢；文件为空字段回退到环境变量。

Homebox 地址（HOMEBOX_URL）、超时（HOMEBOX_TIMEOUT）、位置（HOMEBOX_LOCATION_ID）
仍写在 docker-compose 里，不在此处管理；只有长期 Token（HOMEBOX_TOKEN）自 v1.05 起
改为在「设置页」填写并持久化，应用启动时会自动把环境变量里的 Token 迁移进 config.json。
"""
import json
import os
import threading
from pathlib import Path

# 这些键可由界面设置（持久化到 config.json）
DEFAULTS = {
    "gs1_api_url": "",
    "gs1_secret_id": "",
    "gs1_secret_key": "",
    "vision_api_url": "",
    "vision_api_key": "",
    "vision_model": "gpt-4o-mini",
    # ===== Homebox 长期 Token（v1.05 起界面可配置）=====
    "homebox_token": "",
}

# 文件为空时的环境变量兜底：GS1/Vision 走这里；Homebox 的 URL/超时/位置也走这里
# （它们写在 docker-compose 里，不在 config.json 持久化），Token 既走这里也走 config.json。
ENV_MAP = {
    "gs1_api_url": "GS1_API_URL",
    "gs1_secret_id": "GS1_SECRET_ID",
    "gs1_secret_key": "GS1_SECRET_KEY",
    "vision_api_url": "VISION_API_URL",
    "vision_api_key": "VISION_API_KEY",
    "vision_model": "VISION_MODEL",
    "homebox_url": "HOMEBOX_URL",
    "homebox_timeout": "HOMEBOX_TIMEOUT",
    "homebox_location_id": "HOMEBOX_LOCATION_ID",
    "homebox_token": "HOMEBOX_TOKEN",
}

# 首次启动从环境变量迁移进 config.json 的键（仅持久化类配置，地址等仍留在 compose）
MIGRATE_ENV_PAIRS = (
    ("homebox_token", "HOMEBOX_TOKEN"),
)

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "/app/data/config.json"))
_lock = threading.Lock()


def load() -> dict:
    """合并：文件优先，文件为空字段回退环境变量。"""
    merged = dict(DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for k in DEFAULTS:
                if k in data and data[k] not in (None, ""):
                    merged[k] = data[k]
    except Exception:  # noqa: BLE001
        pass
    for k, envk in ENV_MAP.items():
        if not merged.get(k):
            v = os.getenv(envk)
            if v:
                merged[k] = v
    return merged


def save(cfg: dict) -> dict:
    """只持久化已知键；空值显式写为空串，便于「清空某配置」。

    凭据类字段（密钥/ID/API Key/Homebox Token）在保存时即去除首尾空白，
    避免从网页/剪贴板复制时带入的尾随空格导致签名失败（测试通过、实查回落的假阳性）。
    """
    _strip_keys = {
        "gs1_secret_id", "gs1_secret_key", "vision_api_key", "homebox_token",
    }
    data = {}
    for k in DEFAULTS:
        v = cfg.get(k) or ""
        if k in _strip_keys and isinstance(v, str):
            v = v.strip()
        data[k] = v
    with _lock:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return load()


def migrate_env_to_config() -> bool:
    """首次启动把 docker-compose 里的 HOMEBOX_TOKEN 迁移进 config.json。

    之后界面可改、重启不丢；已配置（config.json 有值）则不再覆盖。
    返回是否发生了迁移。
    """
    c = load()
    migrated = False
    for key, envk in MIGRATE_ENV_PAIRS:
        if not c.get(key) and os.getenv(envk):
            c[key] = os.getenv(envk)
            migrated = True
    if migrated:
        save(c)
        return True
    return False
