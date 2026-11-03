"""Audio to transcript text for building agents from call recordings (A8).

NorthCX ships no speech model. The operator points it at any service that speaks the common transcription API
(`POST <url>/audio/transcriptions`, multipart with `file` and `model`, answering `{"text": ...}`): hosted, or one run inside the
company's own network. The recording is sent to that endpoint and nowhere else, is not stored, and is checked by its content
(not its name) and capped in size. The transcript comes back as text for a person to read; when it is used to draft an agent it
goes through the same personal-detail masking as any pasted transcript.
"""
from __future__ import annotations

import httpx

MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_TEXT = 60000
_MAGIC = ((b"ID3", "mp3"), (b"\xff\xfb", "mp3"), (b"\xff\xf3", "mp3"), (b"\xff\xf2", "mp3"), (b"RIFF", "wav"), (b"OggS", "ogg"), (b"fLaC", "flac"), (b"\x1a\x45\xdf\xa3", "webm"))


class TranscribeError(RuntimeError):
    """Safe to show: no address, key or response text."""


def sniff_audio(data: bytes) -> str:
    if not data:
        raise TranscribeError("The recording is empty")
    if data[4:8] == b"ftyp":
        return "m4a"
    for magic, kind in _MAGIC:
        if data.startswith(magic):
            if kind == "wav" and data[8:12] != b"WAVE":
                break
            return kind
    raise TranscribeError("Only mp3, wav, ogg, flac, m4a and webm recordings can be transcribed")


class HttpTranscriber:
    def __init__(self, url: str, model: str, api_key: str | None = None, client: httpx.AsyncClient | None = None, timeout: float = 120.0):
        u = httpx.URL(url)
        local = u.host in ("localhost", "127.0.0.1", "::1")
        if u.scheme not in ("https", "http") or not u.host or u.userinfo or u.query or u.fragment or (u.scheme == "http" and not local):
            raise ValueError("NORTHCX_TRANSCRIBE_URL must be an https address such as https://stt.example.com/v1 (http is allowed for localhost only)")
        if not model or len(model) > 200:
            raise ValueError("NORTHCX_TRANSCRIBE_MODEL is required")
        path = u.path.rstrip("/")
        self.url = str(u.copy_with(path=path if path.endswith("/audio/transcriptions") else path + "/audio/transcriptions"))
        self.model, self._key = model, api_key
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def transcribe(self, data: bytes, language: str | None = None) -> str:
        kind = sniff_audio(data)
        if len(data) > MAX_AUDIO_BYTES:
            raise TranscribeError(f"A recording can be at most {MAX_AUDIO_BYTES // 1024 // 1024} MB")
        headers = {"accept": "application/json"}
        if self._key:
            headers["authorization"] = f"Bearer {self._key}"
        form = {"model": self.model, "response_format": "json", **({"language": language} if language else {})}
        try:
            r = await self._client.post(self.url, headers=headers, data=form, files={"file": (f"recording.{kind}", data, "application/octet-stream")})
        except httpx.HTTPError as e:
            raise TranscribeError(f"the transcription service could not be reached ({type(e).__name__})") from e
        if r.status_code != 200:
            raise TranscribeError(f"the transcription service returned {r.status_code}")
        try:
            text = str(r.json()["text"]).strip()
        except (ValueError, KeyError, TypeError, AttributeError):
            raise TranscribeError("the transcription service answered in an unexpected form") from None
        if not text:
            raise TranscribeError("No speech was found in the recording")
        return text[:MAX_TEXT]
