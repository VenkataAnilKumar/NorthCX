"""Small helpers shared by every router."""
from __future__ import annotations

import re

from fastapi.responses import JSONResponse


def _pieces(reply: str, size: int = 40) -> list[str]:
    """Split a reply at word boundaries into pieces of about `size` characters; joining them gives the reply back exactly."""
    out, cur = [], ""
    for part in re.findall(r"\S+\s*|\s+", reply):
        if cur and len(cur) + len(part) > size:
            out.append(cur)
            cur = ""
        cur += part
    return out + ([cur] if cur else [])


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)
