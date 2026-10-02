import hashlib
import json
import os
from pathlib import Path
import subprocess
from PIL import Image

MAX_ASSET_BYTES = 1024 * 1024 * 1024


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_ASSET_BYTES:
        raise ValueError('Audio file missing, empty, or larger than 1 GiB')
    result = subprocess.run([os.getenv('FFPROBE_PATH', 'ffprobe'), '-v', 'error', '-show_streams',
        '-show_format', '-of', 'json', str(path)], capture_output=True, text=True, timeout=60, check=True)
    data = json.loads(result.stdout)
    streams = [s for s in data['streams'] if s['codec_type'] == 'audio']
    if len(streams) != 1:
        raise ValueError('Exactly one audio stream is required')
    s = streams[0]
    duration = float(s.get('duration') or data['format'].get('duration') or 0)
    if duration <= 0:
        raise ValueError('Audio duration must be positive')
    bits = int(s.get('bits_per_raw_sample') or s.get('bits_per_sample') or 0)
    return {'duration_seconds': duration, 'codec': s['codec_name'], 'channels': int(s['channels']),
            'sample_rate': int(s['sample_rate']), 'bit_depth': bits, 'sha256': digest(path),
            'bytes': path.stat().st_size}


def validate_master(path):
    result = probe(path)
    if Path(path).suffix.lower() not in {'.wav', '.flac', '.m4a'} or result['codec'] not in {'pcm_s16le', 'pcm_s24le', 'flac', 'alac'}:
        raise ValueError('Use original lossless PCM WAV, FLAC, or ALAC masters; MP3/AAC are not delivery masters')
    if result['channels'] != 2 or result['bit_depth'] not in {16, 24} or result['sample_rate'] not in {44100, 48000, 88200, 96000, 176400, 192000}:
        raise ValueError('Baseline master profile requires stereo, 16/24-bit and a supported sample rate')
    return result


def validate_artwork(path):
    if not Path(path).is_file() or not 0 < Path(path).stat().st_size <= 30 * 1024 * 1024:
        raise ValueError('Artwork missing, empty, or larger than 30 MiB')
    with Image.open(path) as img:
        if img.format not in {'JPEG', 'PNG'} or img.mode != 'RGB' or img.width != img.height or not 3000 <= img.width <= 6000:
            raise ValueError('Baseline artwork profile requires square RGB JPEG/PNG, 3000–6000 pixels')
        width, height = img.size
        img.verify()
    return {'width': width, 'height': height, 'sha256': digest(path), 'bytes': Path(path).stat().st_size}


def transcode(source, target):
    subprocess.run([os.getenv('FFMPEG_PATH', 'ffmpeg'), '-nostdin', '-v', 'error', '-y', '-i', str(source),
        '-map', '0:a:0', '-vn', '-c:a', 'libmp3lame', '-b:a', '320k', '-map_metadata', '-1', str(target)],
        capture_output=True, check=True, timeout=int(os.getenv('TRANSCODE_TIMEOUT_SECONDS', '480')))
