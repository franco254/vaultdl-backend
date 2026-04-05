# VaultDL — Deploy Guide

## What's included
- `app.py`             — Flask backend with yt-dlp (real video info + download)
- `requirements.txt`   — Python dependencies
- `render.yaml`        — Render.com deploy config
- `video-downloader.html` — Frontend (update API_BASE after deploy)

---

## Step 1 — Push backend to GitHub

```bash
git init
git add app.py requirements.txt render.yaml
git commit -m "VaultDL backend"
git remote add origin https://github.com/YOUR_USERNAME/vaultdl-backend.git
git push -u origin main
```

---

## Step 2 — Deploy on Render.com

1. Go to https://render.com → New → Web Service
2. Connect your GitHub repo
3. Render auto-detects `render.yaml` — just click **Deploy**
4. Wait ~2 min for build to finish
5. Copy your live URL, e.g.:
   `https://vaultdl-api.onrender.com`

---

## Step 3 — Connect the frontend

Open `video-downloader.html` and find line:

```js
const API_BASE = 'https://YOUR-RENDER-APP.onrender.com';
```

Replace with your real Render URL:

```js
const API_BASE = 'https://vaultdl-api.onrender.com';
```

Save the file. Done — it's now fully live.

---

## Step 4 — Host the frontend (optional)

Since it's a single HTML file you can host it on:
- **GitHub Pages** — free, just push to a repo with Pages enabled
- **Netlify** — drag and drop the HTML file at netlify.com/drop
- **Render Static Site** — add a second service in Render

---

## Notes

- **yt-dlp** handles YouTube, Instagram, TikTok, Twitter/X, Facebook automatically
- Render free tier **sleeps after 15 min** of inactivity — first request may take ~30s to wake up. Upgrade to paid ($7/mo) for always-on.
- For video+audio merging (e.g. 1080p YouTube), ffmpeg must be available. Render's Python runtime includes it.
- Keep `yt-dlp` updated regularly: `pip install -U yt-dlp` — sites change their formats often.
