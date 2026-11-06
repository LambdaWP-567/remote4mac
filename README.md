# remote4mac

Eine Fernbedienung im lokalen Netzwerk, die Streaming-Webseiten in Firefox auf einem Linux-Rechner öffnet. Firefox wird beim ersten Aufruf gestartet und verwendet das Profil des angemeldeten Linux-Benutzers.

## Streaming-Dienste

Netflix, Amazon Prime Video, ARD Mediathek und Joyn sind vorkonfiguriert. Weitere Ziele lassen sich in [`config/services.json`](config/services.json) ergänzen; erlaubt sind ausschließlich HTTPS-Adressen.

## Installation

Die vollständige Anleitung für Ubuntu/Xubuntu und Debian steht in [`docs/INSTALLATION.md`](docs/INSTALLATION.md). Der Dienst benötigt nur Python 3 und keine externen Python-Pakete.

## Entwicklung und Tests

```sh
python3 -m remote4mac.app
python3 -m unittest discover -s tests -v
```

Browsergestützte UI-Tests (separat, mit Firefox von Playwright):

```sh
python3 -m pip install -r requirements-test.txt
python3 -m playwright install firefox
python3 -m unittest discover -s tests/e2e -v
```

Standardmäßig lauscht der Dienst unverschlüsselt per HTTP auf Port `8765` an allen Netzwerkschnittstellen. Rufe `http://<server-ip>:8765` nur in einem vertrauenswürdigen, WPA2/WPA3-geschützten LAN auf. Eine PIN ist nicht eingerichtet: Jeder erreichbare Client kann Streaming-Ziele öffnen und nach Bestätigung den Rechner ausschalten. Keine Portweiterleitung ins Internet einrichten und den Port per Firewall auf das eigene LAN begrenzen.

## API

Der API-Vertrag steht in [`docs/openapi.yaml`](docs/openapi.yaml). Firefox- und Shutdown-Prozesse werden ausschließlich durch fest definierte Argumentlisten gestartet; Client-Anfragen können keine Shell-Befehle oder beliebigen URLs übergeben.