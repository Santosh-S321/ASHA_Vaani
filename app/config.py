"""All settings come from environment variables (.env file in development)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
CACHE_DIR = Path(os.getenv("CACHE_DIR", BASE_DIR / ".cache"))

# Gnani API Platform
GNANI_API_KEY = os.getenv("GNANI_API_KEY", "").strip()
GNANI_STT_URL = os.getenv("GNANI_STT_URL", "wss://api.vachana.ai/stt/v3/stream")
GNANI_TTS_URL = os.getenv("GNANI_TTS_URL", "https://api.vachana.ai/api/v1/tts/inference")
STT_MODEL = "prisma-v3.0"          # required by the hackathon
TTS_MODEL = "timbre-v3.0"          # required by the hackathon
STT_FORMAT = os.getenv("GNANI_STT_FORMAT", "codemix")      # verbatim | transcribe | codemix | transliterate
STT_MIN_SILENCE_MS = os.getenv("GNANI_MIN_SILENCE_MS", "800")  # endpointing: pause that ends an utterance
STT_VAD_THRESHOLD = os.getenv("GNANI_VAD_THRESHOLD", "0.7")
STT_KEYTERMS = os.getenv("GNANI_KEYTERMS", "").strip()     # optional, see README
TTS_VOICE = os.getenv("TTS_VOICE", "Shivani")              # a stock Timbre v3 voice (no cloning)
TTS_SAMPLE_RATE = int(os.getenv("TTS_SAMPLE_RATE", "24000"))

# LLM (any OpenAI-compatible endpoint). Optional: without it, rule-based extraction is used.
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "6"))

# Storage
DATA_ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY", "").strip()

# Languages offered in the UI. The live Prisma v3.0 stream accepts exactly ONE locale in
# language_code; format=codemix keeps the English words in Latin script.
# Optional override for both, e.g. GNANI_STT_LANGUAGE=indic-auto
_STT_OVERRIDE = os.getenv("GNANI_STT_LANGUAGE", "").strip()
LANGUAGES = {
    "hi": {"stt": _STT_OVERRIDE or "hi-IN", "tts": "auto", "name": "हिंदी + English"},
    "kn": {"stt": _STT_OVERRIDE or "kn-IN", "tts": "auto", "name": "ಕನ್ನಡ + English"},
}
DEFAULT_LANG = "hi"


def llm_enabled() -> bool:
    return bool(LLM_API_KEY and LLM_MODEL)


def gnani_enabled() -> bool:
    return bool(GNANI_API_KEY)