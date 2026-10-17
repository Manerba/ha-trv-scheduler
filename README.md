# TRV Zeitsteuerung

Eigenständige Home-Assistant-Integration mit täglichem Zeitplan je Thermostat.
Ein Dashboard-Button öffnet einen Tabellen-Dialog: Uhrzeit und Solltemperatur
lassen sich direkt bearbeiten. Auf schmalen Bildschirmen und Touch-Geräten öffnet
ein Antippen Drehräder über die volle Tabellenbreite, mit verblassenden Nachbarwerten
und Einrasten beim Wischen. Stunden und Minuten sind getrennt einstellbar;
das Temperaturrad nutzt die Grenzen und Schrittweite des Geräts.
„Übernehmen“ speichert, „Abbrechen“ verwirft die Auswahl.
Jede Zeile hat Aktivierung, Gerätesperre und
Löschen. Neue Schaltzeiten starten pausiert. Änderungen werden automatisch
und mit Schutz gegen gleichzeitiges Überschreiben gespeichert.

Das Schloss gilt **ab der jeweiligen Schaltzeit bis zum nächsten aktiven
Schaltpunkt**. Es sperrt den Drehring eines Shelly BLU TRV; HA kann weiterhin
die Temperatur ändern. „Jetzt entsperren“ gibt den Drehring sofort frei.

Planung und Fortschritt: [Tareas, Projekt 76](http://10.0.12.7:8504/).

## Quellcode

Der Quellcode liegt in öffentlichen Repositories auf
[Gitea](https://10.0.12.17:3000/mir/ha-trv-scheduler) und
[GitHub](https://github.com/Manerba/ha-trv-scheduler).
Der Entwicklungsbranch heißt `master`; Änderungen werden auf beide Remotes gepusht.

```bash
git clone git@10.0.12.17:mir/ha-trv-scheduler.git
cd ha-trv-scheduler
git remote add github git@github.com:Manerba/ha-trv-scheduler.git
git push origin master
git push github master
```

## Installation

1. Das Release-ZIP entpacken und `custom_components/trv_scheduler` nach
   `/config/custom_components/trv_scheduler` kopieren.
2. Home Assistant neu starten.
3. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen**
   „TRV Zeitsteuerung“ auswählen, einmal für jedes Thermostat. Optional die
   vorhandene Heizungsfreigabe (`input_boolean`) und ein Setter-Skript zuordnen.
4. Im Dashboard je Thermostat diese Karte ergänzen:

```yaml
type: custom:trv-scheduler-card
entity: climate.trv2
name: Schlafzimmer
```

Die Integration registriert die Karte automatisch als versionierte JavaScript-Modulressource
im Dashboard. Kein zusätzlicher Download, Browser-Mod oder manuell angelegter
Ressourcen-Eintrag ist nötig. Nach einem Update das Dashboard neu laden.
Falls die Companion-App noch „Custom element doesn’t exist“ zeigt: zuerst
das Dashboard nach unten ziehen, bei Bedarf in den App-Einstellungen
„Frontend-Cache zurücksetzen“ wählen ([HA-Anleitung](https://www.home-assistant.io/faq/browser/)).
Bei YAML-verwalteten Ressourcen bleibt die Startseiten-Einbindung als Fallback;
für die explizite Registrierung dort `/trv_scheduler/trv-scheduler-card.js?v=0.3.1`
mit `type: module` ergänzen. Die gleiche Karte läuft im Browser und im
Dashboard der offiziellen Home-Assistant-Companion-App.

Die Sperrfunktion erkennt Shelly BLU TRVs anhand der HA-Geräteregistrierung
und verwendet das bereits konfigurierte Shelly-Gateway. Zugangsdaten bleiben
serverseitig in dessen bestehendem Config Entry. Andere climate-Geräte können
die Temperatursteuerung nutzen; die Sperrfunktion bleibt dort deaktiviert.

## Bedienung

- Der obere Schalter aktiviert den gesamten Plan; „Aktiv“ nur die einzelne Zeile.
- Uhrzeiten sind täglich und beziehen sich auf die HA-Zeitzone.
- Neue Pläne sind leer und deaktiviert, neue Zeilen pausiert und entsperrt.
- Löschen fragt mit Uhrzeit und Zieltemperatur nach Bestätigung; Abbrechen erhält die Zeile.
- Das Bearbeiten eines Schlosses speichert eine geplante Aktion. Es wirkt
  erst zur eingestellten Uhrzeit. Der bestätigte Gerätestatus steht darunter.
- Plan pausieren, alle Zeilen pausieren/löschen oder Heizungsfreigabe ausschalten
  löst eine von dieser Integration gesetzte Sperre. Bei Geräteausfall wird das
  Entsperren minütlich erneut versucht und als unbestätigt angezeigt.
- Nur geschlossene Schlösser in einem aktiven Plan bedeuten eine fortlaufende
  Sperre. Zum Beenden eine aktive Zeile mit offenem Schloss einplanen oder
  „Jetzt entsperren“ verwenden. Der nächste Schaltpunkt gilt danach wieder.
- Ein Neustart oder Einschalten holt keine vergangenen Schaltzeiten nach.
- Die vorhandene Heizungsfreigabe und deren Frostschutz bleiben zuständig.

## Updates, Daten und Rückbau

Updates ersetzen ausschließlich `/config/custom_components/trv_scheduler`.
Pläne liegen separat in `/config/.storage/trv_scheduler.<config_entry_id>`,
Sperrverantwortung in `trv_scheduler_lock.<config_entry_id>`. Diese Dateien
und die Config Entries gehören ins HA-Konfigurationsbackup. Normale HA-Updates
überschreiben Custom Integrations nicht; Änderungen an HA-APIs können dennoch
Anpassungen erforderlich machen. Getestete Zielversion: **HA 2025.4.2**.

Vor Entfernen die Pläne pausieren und einen bestätigten entsperrten Zustand
prüfen. Das Entladen eines Eintrags versucht ebenfalls zu entsperren und wird
bei fehlender Bestätigung abgebrochen. Zeitplandateien werden nicht gelöscht;
Neuanlegen erzeugt eine andere Entry-ID, ohne automatischen Wiederimport.
Für einen Rollback zuerst neue Pläne pausieren, dann alte Zeitautomationen
wieder aktivieren. So laufen keine zwei Zeitsteuerungen gleichzeitig.

Die Verzeichnisstruktur und `hacs.json` sind für eine spätere HACS-Veröffentlichung
vorbereitet. Dafür fehlen noch die zugehörigen Manifest-Links/Codeowner
([HACS-Anforderungen](https://www.hacs.xyz/docs/publish/start/)).
Es gibt noch keine automatischen Modulupdates. Ein installierbares ZIP lässt sich mit `python tools/build_release.py`
erzeugen. Core-Dateien und fremde Integrationen werden nicht verändert.

## Entwicklung und Tests

Python 3.13, getrennt von der produktiven HA-Installation:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/playwright install chromium
export TRV_BROWSER_EXECUTABLE=/pfad/zum/chromium
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
node --check custom_components/trv_scheduler/frontend/trv-scheduler-card.js
```

Die Tests verwenden tatsächliche HA-2025.4.2-Klassen für Store, API und
Lebenszyklus sowie einen simulierten WebSocket-Server für Browseraktionen.
Sie steuern keine realen TRVs. Ohne Chromium werden die Browsertests übersprungen.
`tools/live_gateway_test.py --control` ist ein separater, ausdrücklich steuernder
Installationstest für die drei Bestandsgeräte; er sichert Ausgangswerte und
stellt sie anschließend wieder her. Er benötigt SSH-Zugriff auf das Ziel-HA.

Details und API: [docs/behavior.md](docs/behavior.md).
Bestandspläne als deaktivierte Importvorlagen:
[examples/existing-plans.json](examples/existing-plans.json).

## Isolierter Starttest

Zusätzlich zur Testsuite kann HA ohne Gerätezugriff auf einem lokalen Port
starten. Den Modulordner in eine leere Testkonfiguration kopieren und diese
`configuration.yaml` anlegen:

```yaml
homeassistant:
  name: TRV isolated smoke test
  time_zone: Europe/Berlin
http:
  server_host: 127.0.0.1
  server_port: 18123
frontend:
trv_scheduler:
```

Mit `.venv/bin/python -m homeassistant -c /pfad/zur/testkonfiguration --skip-pip`
starten. `/api/onboarding` muss antworten und
`/trv_scheduler/trv-scheduler-card.js?v=0.3.1` die gebündelte Karte liefern.
Dies prüft den vollständigen Komponentenstart einschließlich HTTP/Frontend;
Config Flow, Speicherung und Entladen werden zusätzlich in den Integrationstests geprüft.

Die Browserprüfungen lassen sich auch mit WebKit ausführen:

```bash
.venv/bin/playwright install --with-deps webkit
TRV_BROWSER_ENGINE=webkit .venv/bin/python -m pytest -q tests/test_frontend.py
```

Der zusätzliche Test mit eingespeisten Touch-Wischbewegungen verwendet Chromium;
die übrigen Browserfälle laufen auch unter WebKit. Das ersetzt keinen Test
auf einem physischen iPhone in der Companion-App.
