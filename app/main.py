"""FastAPI server: serves the browser app and bridges its audio to Gnani over WebSockets.

Browser --(PCM 16 kHz frames)--> /ws --> Prisma v3.0 streaming STT
transcript --> Session (extraction, danger check, rules) --> template text --> Timbre v3.0 TTS --> browser
"""
import asyncio
import base64
import json
import logging
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, danger
from .dialogue import Session
from .extract import make_extractor
from .gnani import PrismaStream, TimbreTTS
from .store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")

app = FastAPI(title="ASHA Vaani")
app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")

store = Store()
extractor = make_extractor()
tts = TimbreTTS()


@app.get("/")
async def index():
    return FileResponse(config.BASE_DIR / "static" / "index.html")


@app.get("/api/status")
async def status():
    return {"gnani": config.gnani_enabled(), "llm": config.llm_enabled(),
            "stt_model": config.STT_MODEL, "tts_model": config.TTS_MODEL,
            "languages": {k: v["name"] for k, v in config.LANGUAGES.items()}}


@app.get("/api/followups")
async def followups():
    return {"items": store.followups()}


@app.get("/api/danger-signs")
async def danger_signs():
    return {"sources": danger.SOURCES, "signs": danger.SIGNS}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, lang: str = config.DEFAULT_LANG):
    await ws.accept()
    lang = lang if lang in config.LANGUAGES else config.DEFAULT_LANG
    session = Session(lang, extractor, store)
    send_lock, turn_lock = asyncio.Lock(), asyncio.Lock()
    tasks: set[asyncio.Task] = set()

    async def send(msg: dict):
        async with send_lock:
            await ws.send_json(msg)

    async def speak(lines: list[str], t0: float | None = None, stt_ms: int | None = None):
        first = True
        for line in lines:
            audio = await tts.synthesize(line, config.LANGUAGES[lang]["tts"])
            msg = {"type": "say", "text": line,
                   "audio": base64.b64encode(audio).decode() if audio else None}
            if first and t0 is not None:
                msg["agent_ms"] = round((time.perf_counter() - t0) * 1000)
                msg["stt_ms"] = stt_ms
                first = False
            await send(msg)
        await send({"type": "form", **session.snapshot()})
        if session.last_saved:
            await send({"type": "followups", "items": store.followups()})

    async def on_text(text: str, stt_ms: int | None = None, lang_code: str | None = None):
        async with turn_lock:   # one turn at a time
            t0 = time.perf_counter()
            await send({"type": "transcript", "text": text, "lang": lang_code})
            lines = await session.handle(text)
            await speak(lines, t0, stt_ms)

    def _done(task: asyncio.Task):
        tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("Turn failed", exc_info=task.exception())

    def spawn(coro):
        task = asyncio.create_task(coro)
        tasks.add(task)
        task.add_done_callback(_done)

    async def on_stt_event(ev: dict):
        kind = ev.get("type")
        if kind == "speech_start":
            await send({"type": "speech_start"})          # browser stops playback (barge-in)
        elif kind == "transcript" and ev.get("text", "").strip():
            spawn(on_text(ev["text"], ev.get("latency"), ev.get("detected_language_code")))
        elif kind == "error":
            log.warning("Prisma error: %s", ev.get("message"))
            await send({"type": "error", "message": f"STT: {ev.get('message')}"})

    stt = PrismaStream(config.LANGUAGES[lang]["stt"], on_stt_event) if config.gnani_enabled() else None
    if stt is None:
        await send({"type": "error", "message": "GNANI_API_KEY not set: voice is off, typed mode only."})

    await speak(session.start())
    await send({"type": "followups", "items": store.followups()})

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                if stt:
                    try:
                        await stt.send_audio(msg["bytes"])
                    except Exception as e:  # noqa: BLE001
                        log.warning("STT send failed: %s", e)
                        await send({"type": "error", "message": "Speech service unavailable. Retrying..."})
                        await asyncio.sleep(1)
            elif msg.get("text"):
                data = json.loads(msg["text"])
                if data.get("type") == "text" and data.get("text", "").strip():
                    spawn(on_text(data["text"]))
                elif data.get("type") == "commit" and stt:
                    await stt.commit()
    except WebSocketDisconnect:
        pass
    finally:
        if stt:
            await stt.close()
        for t in list(tasks):
            t.cancel()
