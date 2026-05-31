# Trarou — Frontend Implementation Guide

## Overview

The Trarou backend exposes a REST API at `http://10.0.0.1:8000`.  
All endpoints are documented interactively at `/docs` (Swagger UI).

The frontend runs separately (e.g. SvelteKit, Next.js, or plain HTML/JS)  
and should be served on port **3000** at `http://10.0.0.1:3000`.

---

## Tech-stack recommendation

| Layer | Recommendation | Why |
|---|---|---|
| Framework | **SvelteKit** | Lightweight, SSR optional, fast on a Pi |
| Styling | Tailwind CSS | Utility-first, tiny output |
| HTTP client | `fetch` / `ky` | Native, no overhead |
| Media player | Video.js or native `<video>` / `<audio>` | Streams from `/media-files/` |
| State | Svelte stores / Zustand | Auth token, network status |

---

## Authentication flow

### 1. Captive-portal splash page

When a new device connects to the Trarou Wi-Fi and opens a browser,  
every HTTP request is redirected (via iptables DNAT) to `http://10.0.0.1:8000`.

The backend's `/` route (or a static splash HTML served by your frontend)  
should show a **login form** that POSTs to:

```
POST /api/auth/captive-login
Content-Type: application/json

{
  "username": "admin",
  "password": "yourpassword",
  "mac": "aa:bb:cc:dd:ee:ff"   // optional — read from ?mac= query param injected by iptables
}
```

On `200 OK`, the response contains `{ "redirect": "http://10.0.0.1:3000" }`.  
The JS should then `window.location.href = response.redirect`.

**How to get the MAC address:**  
Most captive-portal setups inject the client MAC into the redirect URL as a query parameter.  
In the iptables rule you can use `--mac-source` to pass it, or read it  
from the `X-Forwarded-For` / custom header you inject via a Lua/nginx rule.  
The simplest approach: omit MAC and rely on the IP→MAC mapping in `/proc/net/arp`.  
(The backend handles the iptables ACCEPT rule either way.)

---

### 2. Admin login

For full admin access (upload, network config, VNC):

```js
const res = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({ username: 'admin', password: 'yourpassword' })
})
const { access_token } = await res.json()
// Store in memory or sessionStorage (NOT localStorage in a shared-device context)
```

Include the token in subsequent requests:

```js
headers: { Authorization: `Bearer ${access_token}` }
```

---

## Pages / routes to implement

### `/` — Splash / captive-portal login
- Simple login form (username + password)
- POST to `/api/auth/captive-login`
- Redirect to `/home` on success

### `/home` — Media browser (public after captive login)
- Fetch `GET /api/media/tree` → renders folder/file tree
- Display files with icons by MIME type (video, audio, image, document)
- Click file → stream from its `.url` field (`/media-files/relative/path`)
- Use `<video controls src="...">` or `<audio controls src="...">` inline

#### Media tree JSON shape
```json
{
  "folders": [
    { "name": "Movies", "path": "Movies", "children_count": 12 }
  ],
  "files": [
    {
      "name": "intro.mp4",
      "path": "intro.mp4",
      "url": "/media-files/intro.mp4",
      "size_bytes": 104857600,
      "mime_type": "video/mp4",
      "modified_at": "2025-01-15T10:30:00"
    }
  ],
  "total_files": 42,
  "total_size_bytes": 8589934592
}
```

### `/admin` — Admin dashboard (requires Bearer token)
Tabs or sidebar sections:

#### Media Management
- Show the same file tree
- **Upload** button → multipart POST to `/api/media/upload`
  ```
  POST /api/media/upload
  Content-Type: multipart/form-data
  Authorization: Bearer <token>
  
  files[]: <file1>
  files[]: <file2>
  folder: "Movies"      // optional subfolder
  ```
- **Delete file**: `DELETE /api/media/file?path=Movies/intro.mp4`
- **New folder**: `POST /api/media/folder` body `folder=Movies/Classics`
- Show upload progress using `XMLHttpRequest` with `upload.onprogress`

#### Network
- `GET /api/network/status` → show AP status, client connection
- **Scan button** → `GET /api/network/scan` → list SSIDs with signal bars
- **Connect form** → select SSID + enter password → `POST /api/network/connect`
- **Disconnect** → `POST /api/network/disconnect`

#### Remote Desktop (noVNC)
- `GET /api/vnc/status` → show if running
- **Start** → `POST /api/vnc/start` → returns `{ novnc_url: "http://10.0.0.1:6080/vnc.html?..." }`
- Open the URL in a new tab or embed in an `<iframe>` (full-screen recommended)
- **Stop** → `POST /api/vnc/stop`

#### System
- `GET /api/system/info` → CPU %, RAM bar, disk bar, uptime
- **Reboot** / **Shutdown** buttons with confirmation dialog
- **Change password** form → `POST /api/system/set-password` `{ "new_password": "..." }`

---

## Embedding noVNC

The easiest approach is opening the URL in a new tab:

```js
const { novnc_url } = await startVnc() // POST /api/vnc/start
window.open(novnc_url, '_blank')
```

To embed inline, use an iframe:

```html
<iframe
  src="http://10.0.0.1:6080/vnc.html?autoconnect=true&resize=scale"
  style="width:100%;height:80vh;border:none"
/>
```

> **Note:** noVNC's WebSocket uses the same IP/port — no extra CORS config needed
> as long as the frontend origin is `10.0.0.1`.

---

## Captive-portal detection tips

Modern OSes (Android, iOS, macOS, Windows) auto-detect captive portals by making
requests to known check URLs (e.g. `connectivitycheck.gstatic.com`).
Because the Trarou DNS server returns `10.0.0.1` for all domains, these checks
will hit your backend. Respond to any unknown route with a `302` redirect to
your splash page:

```python
# Add to app.py after all routers
@app.exception_handler(404)
async def captive_redirect(request, exc):
    from fastapi.responses import RedirectResponse
    # If it looks like a connectivity check, redirect to splash
    return RedirectResponse(url=f"http://{settings.CAPTIVE_PORTAL_IP}:{settings.API_PORT}/")
```

Or serve the splash `index.html` directly from FastAPI:

```python
from fastapi.responses import FileResponse

@app.get("/")
async def splash():
    return FileResponse("/opt/trarou/frontend/dist/index.html")

app.mount("/", StaticFiles(directory="/opt/trarou/frontend/dist"), name="frontend")
```

---

## Running the frontend alongside the backend

```bash
# On the router device:
cd /opt/trarou/frontend
npm run build            # SvelteKit static build
# Then serve dist/ on port 3000:
npx serve -s dist -l 3000
# Or configure nginx to serve it
```

Alternatively, let FastAPI serve the built frontend as static files (see above).

---

## Quick-reference: all API endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | — | Admin JWT login |
| POST | `/api/auth/captive-login` | — | Captive portal splash login |
| GET | `/api/auth/captive-check?mac=` | — | Check if MAC is authorised |
| GET | `/api/media/tree` | — | Full recursive media tree |
| GET | `/api/media/list?folder=` | — | Files in a folder |
| POST | `/api/media/upload` | Admin | Upload files |
| DELETE | `/api/media/file?path=` | Admin | Delete a file |
| POST | `/api/media/folder` | Admin | Create folder |
| DELETE | `/api/media/folder?path=` | Admin | Delete folder |
| GET | `/api/network/status` | — | AP + client status |
| GET | `/api/network/scan` | Admin | Scan Wi-Fi networks |
| POST | `/api/network/connect` | Admin | Connect to upstream Wi-Fi |
| POST | `/api/network/disconnect` | Admin | Disconnect client |
| GET | `/api/network/ap` | Admin | AP config |
| POST | `/api/network/ap/restart` | Admin | Restart AP |
| GET | `/api/system/info` | — | CPU/RAM/disk/uptime |
| POST | `/api/system/reboot` | Admin | Reboot device |
| POST | `/api/system/shutdown` | Admin | Shutdown device |
| POST | `/api/system/set-password` | Admin | Change admin password |
| GET | `/api/vnc/status` | Admin | noVNC status |
| POST | `/api/vnc/start` | Admin | Start noVNC proxy |
| POST | `/api/vnc/stop` | Admin | Stop noVNC proxy |
| GET | `/api/vnc/url` | Admin | Get noVNC URL |
| GET | `/media-files/{path}` | — | Stream / download media |
| GET | `/docs` | — | Swagger UI |

---

## Hardware requirements

- Raspberry Pi 4 (or similar SBC) running Raspberry Pi OS / Ubuntu
- Two Wi-Fi interfaces:
  - `wlan0` — built-in, used as the upstream client
  - `wlan1` — USB Wi-Fi adapter (must support AP mode; e.g. Alfa AWUS036ACS)
- Check AP mode support: `iw list | grep "Supported interface modes" -A 10`
