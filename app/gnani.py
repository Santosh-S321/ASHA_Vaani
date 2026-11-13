"""Gnani API Platform clients: Prisma v3.0 streaming STT and Timbre v3.0 TTS."""
import asyncio
import hashlib
import json
import logging
from typing import Awaitable, Callable

import httpx
import websockets

from . import config

log = logging.getLogger("gnani")

EventHandler = Callable[[dict], Awaitable[None]]


class PrismaStream:
    """One WebSocket session to Prisma v3.0. Browser PCM frames are relayed as-is.

    Expected audio: 16-bit little-endian mono PCM at 16 kHz, 1,024-byte frames, real-time cadence.
    Server events: connected, speech_start, processing, transcript (always final), error.
    """

    RETRY_GAP_S = 3.0   # never reconnect faster than this

    def __init__(self, language_codes: str, on_event: EventHandler):
        self.language_codes = language_codes
        self.on_event = on_event
        self.ws = None
        self._reader: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._last_attempt = 0.0
        self._last_error: str | None = None
        self.fatal: str | None = None   # set when Gnani rejects our settings; stops all retries

    def _headers(self) -> dict:
        h = {
            "x-api-key-id": config.GNANI_API_KEY,
            "model": config.STT_MODEL,
            "language_code": self.language_codes,
            "x-sample-rate": "16000",
            "format": config.STT_FORMAT,
            "x-min-silence-ms": config.STT_MIN_SILENCE_MS,
            "x-vad-threshold": config.STT_VAD_THRESHOLD,
            "x-idle-timeout-sec": "300",
        }
        if config.STT_KEYTERMS:
            h["keyterms"] = config.STT_KEYTERMS
        return h

    @property
    def is_open(self) -> bool:
        return self.ws is not None and self._reader is not None and not self._reader.done()

    async def ensure_open(self) -> bool:
        """Open the stream if needed. Returns False if we should drop audio for now."""
        async with self._lock:
            if self.is_open:
                return True
            if self.fatal:
                return False
            now = asyncio.get_running_loop().time()
            if now - self._last_attempt < self.RETRY_GAP_S:
                return False
            self._last_attempt = now
            self.ws = await websockets.connect(
                config.GNANI_STT_URL, additional_headers=self._headers(), max_size=2**22
            )
            self._reader = asyncio.create_task(self._read())
            return True

    async def _read(self):
        try:
            async for raw in self.ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "error":
                    self._last_error = event.get("message")
                try:
                    await self.on_event(event)
                except Exception:  # noqa: BLE001 - browser gone; keep reading so the stream closes cleanly
                    log.debug("on_event failed", exc_info=True)
        except websockets.ConnectionClosed as e:
            log.info("Prisma stream closed: %s", e)
            if e.rcvd and e.rcvd.code == 1008:   # policy violation = our settings were rejected
                self.fatal = self._last_error or "Gnani rejected the connection settings"
                log.error("Prisma rejected the settings, not retrying: %s", self.fatal)
        except Exception:  # noqa: BLE001
            log.exception("Prisma reader failed")

    async def send_audio(self, frame: bytes):
        if not await self.ensure_open():
            return   # drop the frame: waiting to retry, or settings rejected
        try:
            await self.ws.send(frame)
        except websockets.ConnectionClosed:
            self.ws = None

    async def commit(self):
        """Close the open utterance right away (e.g. when she taps stop)."""
        if self.is_open:
            await self.ws.send(json.dumps({"type": "commit"}))

    async def close(self):
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:  # noqa: BLE001
                pass
        if self._reader:
            self._reader.cancel()


class TimbreTTS:
    """Timbre v3.0 over REST. Replies are fixed templates, so audio is cached on disk:
    repeated prompts cost no credits and come back instantly."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=20)
        self.cache_dir = config.CACHE_DIR / "tts"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return config.gnani_enabled()

    async def synthesize(self, text: str, language: str = "auto") -> bytes | None:
        if not self.enabled or not text.strip():
            return None
        key = hashlib.sha1(f"{config.TTS_VOICE}|{language}|{config.TTS_SAMPLE_RATE}|{text}".encode()).hexdigest()
        path = self.cache_dir / f"{key}.wav"
        if path.exists():
            return path.read_bytes()
        body = {
            "text": text,
            "voice": config.TTS_VOICE,
            "model": config.TTS_MODEL,
            "language": language,
            "speed": 1.0,
            "audio_config": {
                "sample_rate": config.TTS_SAMPLE_RATE,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }
        r = await self.client.post(
            config.GNANI_TTS_URL,
            json=body,
            headers={"X-API-Key-ID": config.GNANI_API_KEY, "Content-Type": "application/json"},
        )
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("audio"):
            log.error("Timbre TTS failed (%s): %s", r.status_code, r.text[:300])
            return None
        path.write_bytes(r.content)
        return r.content