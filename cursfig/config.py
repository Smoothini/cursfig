"""App-level config: provider credentials and profile registry."""
from __future__ import annotations
import json
from pathlib import Path


APP_DIR = Path.home() / ".cursfig"
CONFIG_FILE = APP_DIR / "config.json"
PROFILES_DIR = APP_DIR / "profiles"
DEFAULT_COLLECTIONS_FILE = Path(__file__).parent.parent / "data" / "default_collections.yaml"


def ensure_dirs():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def load_app_config() -> dict:
    ensure_dirs()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"providers": {}, "active_profile": None}


def save_app_config(cfg: dict) -> None:
    ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def list_profiles() -> list[str]:
    ensure_dirs()
    return [p.stem for p in PROFILES_DIR.glob("*.yaml")]


def profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{name}.yaml"


def get_active_profile_name() -> str | None:
    cfg = load_app_config()
    return cfg.get("active_profile")


def set_active_profile(name: str) -> None:
    cfg = load_app_config()
    cfg["active_profile"] = name
    save_app_config(cfg)


def set_provider_config(provider_name: str, config: dict) -> None:
    cfg = load_app_config()
    cfg.setdefault("providers", {})[provider_name] = config
    save_app_config(cfg)


def get_provider_config(provider_name: str) -> dict:
    cfg = load_app_config()
    return cfg.get("providers", {}).get(provider_name, {})


def find_default_collections() -> Path:
    """Find default_collections.yaml - checks app dir, then package data dir."""
    # User-placed override
    user_override = APP_DIR / "default_collections.yaml"
    if user_override.exists():
        return user_override
    # Shipped with package
    pkg = DEFAULT_COLLECTIONS_FILE
    if pkg.exists():
        return pkg
    # Same directory as script
    local = Path("default_collections.yaml")
    if local.exists():
        return local.resolve()
    raise FileNotFoundError("default_collections.yaml not found. Place it in ~/.cursfig/ or the install directory.")
