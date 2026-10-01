"""
Photo + MP3 + Title → 720p Video
+ Split audio into 15-min parts
"""
import os
import glob
import subprocess
import logging
from PIL import Image, ImageDraw, ImageFont
from moviepy import AudioFileClip, ImageClip
from config import (
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, VIDEO_PRESET, VIDEO_CRF,
    VIDEO_AUDIO_BITRATE, TITLE_FONT_SIZE, EPISODE_FONT_SIZE,
    TEXT_COLOR, BOX_COLOR, BOX_PADDING, LINE_GAP, TEXT_MAX_W, FONT_PATH,
)

log = logging.getLogger(__name__)


def _cover_crop(img):
    iw, ih = img.size
    scale = max(VIDEO_WIDTH / iw, VIDEO_HEIGHT / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    iw, ih = img.size
    left = (iw - VIDEO_WIDTH) // 2
    top = (ih - VIDEO_HEIGHT) // 2
    return img.crop((left, top, left + VIDEO_WIDTH, top + VIDEO_HEIGHT))


def _load_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words = text.split()
    if not words:
        return [text]
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [text]


def _build_composite(photo_path, title, episode, work_dir):
    img = Image.open(photo_path).convert("RGB")
    img = _cover_crop(img)

    dark = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.blend(img, dark, alpha=0.15)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_t = _load_font(TITLE_FONT_SIZE)
    font_e = _load_font(EPISODE_FONT_SIZE)

    title_lines = _wrap(draw, title or "", font_t, TEXT_MAX_W)
    ep_text = f"Episode {episode}" if episode else ""

    line_h_t = TITLE_FONT_SIZE + 12
    line_h_e = EPISODE_FONT_SIZE + 10
    total_h = len(title_lines) * line_h_t + (LINE_GAP + line_h_e if ep_text else 0)

    box_w = 0
    for line in title_lines:
        bb = draw.textbbox((0, 0), line, font=font_t)
        box_w = max(box_w, bb[2] - bb[0])
    if ep_text:
        bb = draw.textbbox((0, 0), ep_text, font=font_e)
        box_w = max(box_w, bb[2] - bb[0])
    box_w += BOX_PADDING * 2
    box_h = total_h + BOX_PADDING * 2

    bx = (VIDEO_WIDTH - box_w) // 2
    by = (VIDEO_HEIGHT - box_h) // 2

    draw.rectangle([(bx, by), (bx + box_w, by + box_h)], fill=BOX_COLOR)

    cy = by + BOX_PADDING
    for line in title_lines:
        bb = draw.textbbox((0, 0), line, font=font_t)
        w = bb[2] - bb[0]
        x = (VIDEO_WIDTH - w) // 2
        draw.text((x, cy), line, font=font_t, fill=TEXT_COLOR + (255,))
        cy += line_h_t

    if ep_text:
        cy += LINE_GAP
        bb = draw.textbbox((0, 0), ep_text, font=font_e)
        w = bb[2] - bb[0]
        x = (VIDEO_WIDTH - w) // 2
        draw.text((x, cy), ep_text, font=font_e, fill=TEXT_COLOR + (255,))

    final = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    out = os.path.join(work_dir, "_composite.jpg")
    final.save(out, quality=95, optimize=True, subsampling=0)
    return out


def build_video(photo_path, audio_path, out_path, title, episode, work_dir=None):
    if work_dir is None:
        work_dir = os.path.dirname(out_path) or "."

    log.info(f"[video] Build: {out_path}")

    composite = _build_composite(photo_path, title or "", episode or "", work_dir)

    audio = AudioFileClip(audio_path)
    duration = audio.duration
    log.info(f"[video] Duration: {duration / 60:.2f} min")

    clip = ImageClip(composite).with_duration(duration)
    clip = clip.with_audio(audio)

    clip.write_videofile(
        out_path,
        fps=VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        preset=VIDEO_PRESET,
        audio_bitrate=VIDEO_AUDIO_BITRATE,
        ffmpeg_params=[
            "-crf", str(VIDEO_CRF),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ],
        threads=4,
    )

    try: clip.close()
    except Exception: pass
    try: audio.close()
    except Exception: pass

    log.info(f"[video] ✅ Done")
    return out_path


def get_audio_duration(path):
    a = AudioFileClip(path)
    d = a.duration
    try: a.close()
    except Exception: pass
    return d


def split_audio(input_path, part_sec, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for f in glob.glob(os.path.join(out_dir, "part_*.mp3")):
        try: os.remove(f)
        except Exception: pass

    pattern = os.path.join(out_dir, "part_%03d.mp3")
    cmd = ["ffmpeg", "-y", "-i", input_path, "-f", "segment",
           "-segment_time", str(part_sec), "-c", "copy", pattern]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        cmd = ["ffmpeg", "-y", "-i", input_path, "-f", "segment",
               "-segment_time", str(part_sec),
               "-c:a", "libmp3lame", "-q:a", "5", pattern]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"[split] fail: {result.stderr[:300]}")
            return []

    parts = sorted(glob.glob(os.path.join(out_dir, "part_*.mp3")))
    log.info(f"[split] {len(parts)} parts")
    return parts
