from __future__ import annotations

from typing import Any

from codex_image.version import APP_VERSION, APP_VERSION_TAG


def app_version_payload() -> dict[str, Any]:
    return {
        "current_version": APP_VERSION,
        "current_version_label": APP_VERSION_TAG,
    }
