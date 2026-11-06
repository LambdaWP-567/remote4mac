# Installation unter Linux

Die Anleitung zielt auf Ubuntu/Xubuntu oder Debian mit einem angemeldeten Desktop-Benutzer, Firefox und systemd. Der Dienst läuft als dieser Benutzer, startet Firefox erst beim Aufruf eines Streaming-Dienstes und benötigt keine Python-Pakete von Drittanbietern.

## Voraussetzungen

- Python 3.10 oder neuer (`python3 --version`)
- Firefox im PATH (`command -v firefox`)
- Automatische Anmeldung des Desktop-Benutzers, falls die Fernbedienung nach einem Neustart ohne lokale Anmeldung bereitstehen soll
- Server und Handy im selben vertrauenswürdigen LAN

## Dateien installieren

Lege das Repository im Home-Verzeichnis des Desktop-Benutzers unter `~/remote4mac` ab. Zum Beispiel:

```sh
cd ~
git clone <repository-url> remote4mac
cd ~/remote4mac
```

Falls das Projekt bereits an einem anderen Ort liegt, passe `WorkingDirectory` in der Service-Datei unten entsprechend an.

Prüfe `config/services.json`. Die IDs müssen eindeutig sein; Namen werden in der Fernbedienung angezeigt und Ziele müssen HTTPS verwenden. Beispiel:

```json
{
  "id": "beispiel",
  "name": "Beispiel-Dienst",
  "url": "https://stream.example/"
}
```

Der Eintrag kommt als Objekt in das bestehende JSON-Array.

## User-Service einrichten

```sh
mkdir -p ~/.config/systemd/user
cp ~/remote4mac/systemd/remote4mac.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now remote4mac.service
```

Der User-Service startet nach der Anmeldung automatisch. Weil Firefox auf dem lokalen Desktop erscheinen soll, muss er in derselben grafischen Benutzersitzung laufen. Prüfe die Umgebungsvariablen der Sitzung bei Bedarf mit `systemctl --user show-environment`; insbesondere `DISPLAY` oder `WAYLAND_DISPLAY` und `XDG_RUNTIME_DIR` müssen für den Dienst verfügbar sein.

Status und Protokoll:

```sh
systemctl --user status remote4mac.service
journalctl --user -u remote4mac.service -f
```

Der Server wird beim ersten Dienstaufruf Firefox mit `--new-tab` starten. Ist Firefox bereits mit dem Benutzerprofil geöffnet, wird dessen Sitzung wiederverwendet. Das Profil darf nicht gleichzeitig von einer zweiten Firefox-Instanz geöffnet werden.

## LAN-Zugriff begrenzen

Die Oberfläche verwendet unverschlüsseltes HTTP und hat absichtlich keine PIN. Nutze sie deshalb nur in einem vertrauenswürdigen, WPA2/WPA3-geschützten LAN, niemals in einem Gastnetz oder über ein öffentliches WLAN. Jeder Client, der den HTTP-Port erreichen kann, darf Ziele öffnen und nach Bestätigung einen Shutdown anfordern. Keine Router-Portweiterleitung konfigurieren. Begrenze Port `8765` mit der Firewall auf das eigene LAN. Beispiel mit UFW; ersetze das Netz durch das tatsächliche Subnetz:

```sh
sudo ufw allow from 192.168.1.0/24 to any port 8765 proto tcp
```

Die Beispiel-Service-Datei lauscht auf allen Schnittstellen. Für zusätzliche Isolation kann `REMOTE4MAC_HOST` in der Unit auf die feste LAN-IP des Servers gesetzt werden; danach `systemctl --user daemon-reload` und `systemctl --user restart remote4mac.service` ausführen.

## Ausschalten erlauben

Der Shutdown läuft als angemeldeter Benutzer über `systemctl poweroff`; der Dienst erhält keine pauschalen Root-Rechte und verwendet kein `sudo`. Ob systemd-logind den Vorgang ohne Passwort zulässt, hängt von der aktiven Desktop-Sitzung und der lokalen Polkit-Konfiguration ab. Teste das zuerst lokal. Richte keine allgemeine `NOPASSWD`-sudo-Regel ein. Wenn die vorhandene Polkit-Richtlinie den Vorgang verweigert, muss eine eng auf den Desktop-Benutzer und die Aktion `org.freedesktop.login1.power-off` begrenzte Richtlinie separat geprüft werden.

Die UI muss vor dem Senden der Shutdown-Anfrage eine Bestätigung verlangen. Für automatisierte Tests wird der Systemaufruf gemockt; Tests schalten den Rechner niemals aus.

## Konfiguration

- `REMOTE4MAC_HOST`: Bind-Adresse, Standard `0.0.0.0`
- `REMOTE4MAC_PORT`: HTTP-Port, Standard `8765`
- `REMOTE4MAC_CONFIG`: Pfad zur JSON-Diensteliste
- `REMOTE4MAC_FIREFOX`: Firefox-Programm, Standard `firefox`

## Deinstallation

```sh
systemctl --user disable --now remote4mac.service
rm ~/.config/systemd/user/remote4mac.service
systemctl --user daemon-reload
```

Entferne anschließend bei Bedarf den Projektordner und die Firewall-Freigabe. Browserprofil und Login-Cookies bleiben erhalten.