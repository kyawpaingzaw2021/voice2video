"""
Voice → Video Bot Config
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", "0"))
AUDIOBOOK_BOT_USERNAME = os.getenv("AUDIOBOOK_BOT_USERNAME", "MyanmarAudioBook_bot")

# Video — 720p
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_FPS = 15
VIDEO_PRESET = "veryfast"
VIDEO_CRF = 34
VIDEO_AUDIO_BITRATE = "96k"

# Limits
MAX_DURATION_SEC = 3600
MAX_UPLOAD_MB = 49

# Title
TITLE_FONT_SIZE = 60
EPISODE_FONT_SIZE = 48
TEXT_COLOR = (255, 255, 255)
BOX_COLOR = (0, 0, 0, 180)
BOX_PADDING = 40
LINE_GAP = 20
TEXT_MAX_W = 900

# Paths
TEMP_DIR = "data/temp"
DB_PATH = "data/jobs.db"
FONT_PATH = "assets/fonts/NotoSansMyanmar.ttf"
PROMO_DIR = "assets/promo"
PROMO_CUSTOM = "assets/promo/custom_promo.jpg"

# Permissions
DEFAULT_PERMISSIONS = {
    "can_generate": True,
    "max_jobs_per_day": 10,
}

# Split Mode
PART_DURATION_SEC = 900
SPLIT_MODE_DEFAULT = True
