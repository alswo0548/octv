# Background video

- Source: **Busy Night Traffic on City Highway**, Şeyhmus Kino / Pexels, video 34435020.
- Page: https://www.pexels.com/video/busy-night-traffic-on-city-highway-34435020/
- Download: https://www.pexels.com/download/video/34435020/
- License: https://www.pexels.com/license/ (free website use and modification; attribution optional; checked 2026-09-23).
- Used only as decorative, prerecorded footage. Not a live CCTV source or evidence of the displayed incidents.
- Local derivative: `dist/night-traffic.mp4`, silent H.264, 1280×720, 24 fps.
- Processing: landscape crop from the high-resolution original; camera stabilization with static crop; 0.6× scene speed; restrained cool/dark footage color matching; 1.2-second end/start crossfade for a continuous loop; compressed with fast-start metadata.
- `dist/road.jpg` is unchanged and remains the loading / unavailable-playback / reduced-motion background and the original incident CCTV image.

# Background-only overlay adjustment

`dist/style.css`, `.shade`: each existing nonzero dark gradient alpha reduced by exactly 0.03:

- horizontal: 0.76 → 0.73, 0.35 → 0.32, 0.45 → 0.42
- vertical: 0.69 → 0.66, 0.25 → 0.22
- existing transparent stop is unchanged.

No panel, logo, text, CCTV image, bounding-box or interaction styles were changed.

# Round 2 CCTV display attribution

CCTV mock display areas now use the shared caption `기존 위치 / 경찰청(UTIC) 제공`; existing timestamps remain. The decorative Pexels background described above is not CCTV and does not receive a UTIC label. The source label is requested UI copy; this change does not connect or verify a live UTIC feed. Current WEB assets are in `frontend/web/public/assets`, and MOBILE uses its existing local assets. The `dist` references above document the original asset preparation.
