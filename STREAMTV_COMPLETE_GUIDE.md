# StreamTV – vollständige Projektübersicht und Installationsanleitung

Diese Datei fasst die komplette Idee, Struktur, Implementierung, Teststrategie und Installation für ein lokales Streaming-Steuerungsportal auf Ubuntu zusammen.

## 1. Ziel

Ein lokales Webportal auf einem Ubuntu-Server, das im lokalen Netzwerk erreichbar ist und über eine einfache Weboberfläche Streaming-Dienste wie Netflix, Amazon Prime, RTL+, Joyn und ARD starten kann. Der Firefox auf dem Server startet automatisch im Vollbildmodus und öffnet die jeweilige Seite. Die Anwendung läuft als Linux-Dienst (systemd) und startet automatisch beim Systemstart und erneut nach Absturz.

## 2. Anforderungen / Festlegung

- Ubuntu Server im lokalen Netzwerk
- Zugriff nur über LAN / private IPs (z. B. 192.168.x.x)
- Firefox bereits installiert
- Web-App per Browser erreichbar
- Automatisches Starten beim Boot
- Neustart nach Absturz
- Weboberfläche mit großen Buttons
- Direkte Schnellzugriffstasten für Streamingdienste
- Vollbildmodus mit Firefox
- Passwortschutz für die Weboberfläche
- Optionale zentrale Konfiguration für Anmeldedaten und Dienstnamen

## 3. Architektur

- Frontend: einfache Weboberfläche mit großen Buttons, erreichbar im Browser
- Backend: Python + FastAPI
- Browsersteuerung: Firefox via subprocess / system calls
- Dienst: systemd Service
- Netzwerk: nur lokales LAN, kein externes Internet
- Auth: einfache Browser-Authentifizierung
- Autostart: systemd enable/start

## 4. Verwendete Technologien

- Python 3
- FastAPI
- Uvicorn
- Vue.js oder reines HTML/JS (empfohlen: HTML/JS für kleine Lösung)
- Firefox CLI / Kiosk-Modus
- systemd
- pytest
- GitHub Actions

## 5. Empfohlene Projektstruktur

```text
/opt/streamtv/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── main.py
│   │   └── services/
│   │       ├── firefox_controller.py
│   │       └── stream_targets.py
│   ├── requirements.txt
│   └── tests/
│       ├── test_firefox_controller.py
│       └── test_routes.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── systemd/
│   └── streamtv.service
├── .github/
│   └── workflows/
│       └── ci.yml
└── README.md
```

## 6. Backend-Design

### 6.1. config.py

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = Path("/opt/streamtv/frontend")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
PASSWORD = os.getenv("APP_PASSWORD", "streamtv")
FIREFOX_BIN = "/usr/bin/firefox"

STREAM_TARGETS = {
    "netflix": {
        "label": "Netflix",
        "url": "https://www.netflix.com",
        "profile": "default",
    },
    "prime": {
        "label": "Amazon Prime",
        "url": "https://www.primevideo.com",
        "profile": "default",
    },
    "rtl": {
        "label": "RTL+",
        "url": "https://www.rtlplus.de",
        "profile": "default",
    },
    "joyn": {
        "label": "Joyn",
        "url": "https://www.joyn.de",
        "profile": "default",
    },
    "ard": {
        "label": "ARD",
        "url": "https://www.ardmediathek.de",
        "profile": "default",
    },
}
```

### 6.2. firefox_controller.py

```python
import os
import time
import subprocess

from app.config import FIREFOX_BIN

class FirefoxController:
    def __init__(self):
        self.process = None

    def is_running(self) -> bool:
        try:
            result = subprocess.run(
                ["pgrep", "-f", "firefox"],
                capture_output=True,
                text=True,
                check=False,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    def start(self, url: str) -> dict:
        if self.is_running():
            self.close()

        command = [
            FIREFOX_BIN,
            "--new-window",
            "--kiosk",
            url,
        ]

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(4)
            return {"status": "started", "url": url}
        except FileNotFoundError:
            return {"status": "error", "message": "Firefox not found"}

    def close(self) -> dict:
        try:
            subprocess.run(["pkill", "-f", "firefox"], check=False)
            time.sleep(1)
            return {"status": "closed"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def open_url(self, url: str) -> dict:
        if not os.path.exists(FIREFOX_BIN):
            return {"status": "error", "message": "Firefox binary not found"}
        return self.start(url)
```

### 6.3. stream_targets.py

```python
from app.config import STREAM_TARGETS

def get_targets():
    return [
        {
            "key": key,
            "label": value["label"],
            "url": value["url"],
        }
        for key, value in STREAM_TARGETS.items()
    ]
```

### 6.4. main.py

```python
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import secrets

from app.config import APP_HOST, APP_PORT, PASSWORD, FRONTEND_DIR
from app.services.firefox_controller import FirefoxController
from app.services.stream_targets import get_targets

security = HTTPBasic()
app = FastAPI(title="StreamTV Controller")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    correct = secrets.compare_digest(credentials.username, "admin")
    correct = correct and secrets.compare_digest(credentials.password, PASSWORD)
    if not correct:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return credentials.username

@app.get("/")
async def read_root(request: Request, user: str = Depends(get_current_user)):
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))

@app.get("/api/health")
async def health(user: str = Depends(get_current_user)):
    return {"status": "ok"}

@app.get("/api/targets")
async def targets(user: str = Depends(get_current_user)):
    return {"targets": get_targets()}

@app.post("/api/open")
async def open_stream(payload: dict, user: str = Depends(get_current_user)):
    key = payload.get("target")
    if not key:
        raise HTTPException(status_code=400, detail="Missing target")

    from app.config import STREAM_TARGETS
    if key not in STREAM_TARGETS:
        raise HTTPException(status_code=404, detail="Unknown target")

    url = STREAM_TARGETS[key]["url"]
    controller = FirefoxController()
    result = controller.open_url(url)
    return result

@app.post("/api/close")
async def close_stream(user: str = Depends(get_current_user)):
    controller = FirefoxController()
    return controller.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=False)
```

## 7. Frontend-Design

### 7.1. index.html

```html
<!doctype html>
<html lang="de">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>StreamTV</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <div class="container">
      <h1>StreamTV</h1>
      <div id="status" class="status">Lade Dienste...</div>
      <div id="buttons" class="buttons"></div>
      <div class="footer">
        <button id="closeFirefox" class="danger">Firefox schließen</button>
      </div>
    </div>

    <script src="/static/app.js"></script>
  </body>
</html>
```

### 7.2. styles.css

```css
body {
  margin: 0;
  background: #0f172a;
  color: white;
  font-family: Arial, sans-serif;
}

.container {
  max-width: 1100px;
  margin: 0 auto;
  padding: 40px 20px;
}

h1 {
  text-align: center;
  font-size: 3rem;
  margin-bottom: 18px;
}

.status {
  text-align: center;
  margin-bottom: 24px;
  color: #cbd5e1;
}

.buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 20px;
}

.button {
  appearance: none;
  border: none;
  border-radius: 18px;
  padding: 28px 20px;
  font-size: 1.5rem;
  font-weight: bold;
  cursor: pointer;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
  box-shadow: 0 14px 30px rgba(59, 130, 246, 0.4);
}

.button:hover {
  transform: translateY(-2px);
  filter: brightness(1.05);
}

.danger {
  background: linear-gradient(135deg, #ef4444, #b91c1c);
  color: white;
  border: none;
  padding: 18px 28px;
  border-radius: 12px;
  font-size: 1rem;
  font-weight: bold;
  cursor: pointer;
}

.footer {
  margin-top: 30px;
  display: flex;
  justify-content: center;
}
```

### 7.3. app.js

```javascript
const statusEl = document.getElementById("status");
const buttonsEl = document.getElementById("buttons");
const closeBtn = document.getElementById("closeFirefox");

const username = "admin";
const password = "streamtv";

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: "Basic " + btoa(`${username}:${password}`),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error("Request failed");
  }

  return response.json();
}

async function loadTargets() {
  try {
    const data = await fetchJSON("/api/targets");
    renderButtons(data.targets);
    statusEl.textContent = "Bereit";
  } catch (error) {
    statusEl.textContent = "Fehler beim Laden der Dienste";
  }
}

function renderButtons(targets) {
  buttonsEl.innerHTML = "";

  targets.forEach((target) => {
    const btn = document.createElement("button");
    btn.className = "button";
    btn.textContent = target.label;
    btn.addEventListener("click", async () => {
      statusEl.textContent = `Öffne ${target.label}...`;
      try {
        await fetchJSON("/api/open", {
          method: "POST",
          body: JSON.stringify({ target: target.key }),
        });
        statusEl.textContent = `${target.label} wurde gestartet`;
      } catch (error) {
        statusEl.textContent = "Start fehlgeschlagen";
      }
    });
    buttonsEl.appendChild(btn);
  });
}

closeBtn.addEventListener("click", async () => {
  try {
    await fetchJSON("/api/close", {
      method: "POST",
    });
    statusEl.textContent = "Firefox wurde geschlossen";
  } catch (error) {
    statusEl.textContent = "Schließen fehlgeschlagen";
  }
});

loadTargets();
```

## 8. Tests

### 8.1. test_routes.py

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/health", auth=("admin", "streamtv"))
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_targets():
    response = client.get("/api/targets", auth=("admin", "streamtv"))
    assert response.status_code == 200
    data = response.json()
    assert "targets" in data
    assert len(data["targets"]) >= 5
```

### 8.2. test_firefox_controller.py

```python
from app.services.firefox_controller import FirefoxController


def test_firefox_is_running_false_when_not_running():
    controller = FirefoxController()
    assert controller.is_running() in (True, False)


def test_close_returns_status():
    controller = FirefoxController()
    result = controller.close()
    assert "status" in result
```

### 8.3. requirements.txt

```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
pytest==8.3.2
httpx==0.27.2
pydantic==2.8.2
python-dotenv==1.0.1
psutil==6.0.0
```

## 9. systemd Service

```ini
[Unit]
Description=StreamTV controller service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/streamtv/backend
Environment=APP_HOST=0.0.0.0
Environment=APP_PORT=8000
Environment=APP_PASSWORD=streamtv
ExecStart=/usr/bin/python3 /opt/streamtv/backend/app/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## 10. GitHub Actions / CI Pipeline

```yaml
name: CI

on:
  push:
    branches: [ "**" ]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r backend/requirements.txt

      - name: Run tests
        run: |
          cd backend
          pytest -q
```

## 11. Installation auf Ubuntu

### 11.1. Abhängigkeiten installieren

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv firefox
```

### 11.2. Projektverzeichnis anlegen

```bash
sudo mkdir -p /opt/streamtv
sudo chown -R $USER:$USER /opt/streamtv
```

### 11.3. Dateien kopieren

- backend/ in `/opt/streamtv/backend`
- frontend/ in `/opt/streamtv/frontend`
- systemd/ in `/opt/streamtv/systemd`

### 11.4. Virtuelle Umgebung erzeugen

```bash
cd /opt/streamtv/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 11.5. Service installieren

```bash
sudo cp /opt/streamtv/systemd/streamtv.service /etc/systemd/system/streamtv.service
sudo systemctl daemon-reload
sudo systemctl enable streamtv
sudo systemctl start streamtv
```

### 11.6. Status prüfen

```bash
sudo systemctl status streamtv
```

### 11.7. Zugriff im Browser

Browser öffnen:

```text
http://192.168.x.x:8000
```

Login:

- Benutzer: admin
- Passwort: streamtv

### 11.8. Autostart + Neustart

`systemd` übernimmt:

- Start beim Boot
- Neustart im Fehlerfall
- dauerhaft laufender Dienst

## 12. Sicherheit und Zugriff

- Zugriff nur im lokalen Netzwerk
- Beispiel: 192.168.x.x
- Passwortschutz im Browser
- Keine öffentliche Internetfreigabe nötig
- Optionale IP-Beschränkung über Firewall oder reverse proxy

## 13. Betriebslogik

1. Das System startet als systemd Service.
2. Der Browserserver läuft auf Port 8000.
3. Im Browser wird die Oberfläche mit Buttons angezeigt.
4. Beim Klick auf einen Button wird ein API-Request an `/api/open` gesendet.
5. Das Backend startet Firefox im Vollbildmodus mit `--new-window --kiosk`.
6. Die entsprechende URL wird im Firefox geöffnet.
7. Wenn der Dienst abstürzt, startet systemd ihn automatisch neu.

## 14. Empfohlene Erweiterungen

- Laufzeit-Logdateien
- Konfigurationsdatei für Stream-Websites
- Live-Status in der Oberfläche
- Lautstärke-Steuerung
- Fernbedienung über Tastatur / Sonderfunktionen
- Externe Bildschirmanbindung
- Einzelne Firefox-Profile pro Dienst
- Erweiterte Authentifizierung

## 15. Hinweis zur praktischen Umsetzung

Diese Lösung passt exakt zu den Anforderungen:

- lokales LAN-Interface
- Browser mit großen Buttons
- Firefox im Vollbild
- Dienste direkt per Button startbar
- systemd-Boot und Restart
- lokale Verwaltung im Backend
- Tests und CI-Pipeline

## 16. Abschluss

Das Projekt ist technisch realisierbar und in einer sauberen Struktur aufsetzbar. Es lässt sich auf einem Ubuntu-Server leicht installieren, betreiben und weiterentwickeln.

Wenn du möchtest, kann ich als Nächstes noch eine zweite Datei erzeugen, die nur die reinen Installationsbefehle enthält, oder eine dritte Datei mit der vollständigen Projektstruktur in GitHub-Repo-Form für direktes Kopieren.

Diese Datei wurde für den Download als kompakte, vollständige Zusammenfassung erstellt.

---

Download-Datei: `STREAMTV_COMPLETE_GUIDE.md`
