import os
import re
import yt_dlp
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow frontend to call this API from any origin

# ─── Helpers ──────────────────────────────────────────────────────────────────

def format_duration(seconds):
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def safe_filesize(fmt):
    fs = fmt.get('filesize') or fmt.get('filesize_approx')
    if not fs:
        return None
    mb = fs / (1024 * 1024)
    if mb >= 1000:
        return f"~{mb/1024:.1f} GB"
    return f"~{mb:.0f} MB"

def platform_from_url(url):
    mapping = {
        'youtube.com': 'YouTube', 'youtu.be': 'YouTube',
        'instagram.com': 'Instagram',
        'tiktok.com': 'TikTok',
        'twitter.com': 'Twitter/X', 'x.com': 'Twitter/X',
        'facebook.com': 'Facebook', 'fb.watch': 'Facebook',
    }
    for pat, label in mapping.items():
        if pat in url:
            return label
    return 'Unknown'

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/info', methods=['GET'])
def get_info():
    """
    GET /info?url=<video_url>
    Returns video metadata + available formats.
    """
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to fetch video info: {str(e)}'}), 500

    # Build video formats list (combined video+audio streams only, sorted by quality)
    video_formats = []
    audio_formats = []
    seen_res = set()
    seen_abr = set()

    for fmt in reversed(info.get('formats', [])):
        vcodec = fmt.get('vcodec', 'none')
        acodec = fmt.get('acodec', 'none')
        ext = fmt.get('ext', '')
        fid = fmt.get('format_id', '')

        # Video formats — must have both video and audio
        if vcodec != 'none' and acodec != 'none':
            height = fmt.get('height')
            if height and height not in seen_res:
                seen_res.add(height)
                label = f"{height}p"
                icon = '4K' if height >= 2160 else ('HD' if height >= 1080 else str(height))
                video_formats.append({
                    'format_id': fid,
                    'quality': label,
                    'icon': icon,
                    'ext': ext,
                    'size': safe_filesize(fmt),
                    'label': f"{label} · {ext.upper()}",
                })

        # Audio-only formats
        elif vcodec == 'none' and acodec != 'none':
            abr = fmt.get('abr') or 0
            abr_key = round(abr / 32) * 32  # bucket into 32kbps steps
            if abr_key and abr_key not in seen_abr:
                seen_abr.add(abr_key)
                audio_formats.append({
                    'format_id': fid,
                    'quality': f"{int(abr_key)}kbps",
                    'icon': str(int(abr_key)),
                    'ext': ext,
                    'size': safe_filesize(fmt),
                    'label': f"{ext.upper()} · {int(abr_key)}kbps",
                })

    # Sort: video descending by resolution, audio descending by bitrate
    video_formats.sort(key=lambda x: int(x['quality'].replace('p', '')), reverse=True)
    audio_formats.sort(key=lambda x: int(x['quality'].replace('kbps', '')), reverse=True)

    # Fallback: if no merged formats found, offer best overall
    if not video_formats:
        video_formats = [{
            'format_id': 'bestvideo+bestaudio/best',
            'quality': 'Best',
            'icon': 'HD',
            'ext': 'mp4',
            'size': None,
            'label': 'Best Available · MP4',
        }]
    if not audio_formats:
        audio_formats = [{
            'format_id': 'bestaudio',
            'quality': 'Best',
            'icon': 'AAC',
            'ext': 'm4a',
            'size': None,
            'label': 'Best Audio · M4A',
        }]

    thumbnail = info.get('thumbnail') or ''
    # Prefer a smaller thumbnail if available
    thumbs = info.get('thumbnails') or []
    if thumbs:
        medium = [t for t in thumbs if t.get('width', 9999) <= 480]
        if medium:
            thumbnail = medium[-1].get('url', thumbnail)

    return jsonify({
        'title': info.get('title', 'Untitled'),
        'duration': format_duration(info.get('duration')),
        'thumbnail': thumbnail,
        'platform': platform_from_url(url),
        'uploader': info.get('uploader') or info.get('channel') or '',
        'video_formats': video_formats,
        'audio_formats': audio_formats,
    })


@app.route('/download', methods=['GET'])
def download():
    """
    GET /download?url=<video_url>&format_id=<id>&filename=<name>
    Streams the file directly to the browser.
    """
    url = request.args.get('url', '').strip()
    format_id = request.args.get('format_id', 'bestvideo+bestaudio/best').strip()
    filename = request.args.get('filename', 'video').strip()
    # Sanitize filename
    filename = re.sub(r'[^\w\s\-.]', '', filename)[:80] or 'video'

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    import tempfile, os

    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, '%(title)s.%(ext)s')

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': format_id,
        'outtmpl': output_template,
        'noplaylist': True,
        'merge_output_format': 'mp4',
        # Prefer ffmpeg merge but fall back gracefully
        'postprocessors': [],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared = ydl.prepare_filename(info)
            # Find the actual output file (may differ in ext after merge)
            out_file = None
            for f in os.listdir(tmp_dir):
                out_file = os.path.join(tmp_dir, f)
                break
            if not out_file or not os.path.exists(out_file):
                return jsonify({'error': 'Download failed — file not found after processing.'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    ext = os.path.splitext(out_file)[1] or '.mp4'
    mime = 'audio/mpeg' if ext in ('.mp3',) else \
           'audio/mp4'  if ext in ('.m4a',) else \
           'video/mp4'

    def generate():
        try:
            with open(out_file, 'rb') as f:
                while chunk := f.read(1024 * 256):  # 256 KB chunks
                    yield chunk
        finally:
            # Clean up temp files after streaming
            try:
                os.remove(out_file)
                os.rmdir(tmp_dir)
            except Exception:
                pass

    dl_name = f"{filename}{ext}"
    return Response(
        stream_with_context(generate()),
        mimetype=mime,
        headers={
            'Content-Disposition': f'attachment; filename="{dl_name}"',
            'Content-Length': str(os.path.getsize(out_file)),
        }
    )


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'VaultDL API'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
