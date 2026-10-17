# Verhalten und technische Grenzen

Version 0.2.1, Zielversion Home Assistant 2025.4.2.

## Zeitplan

Je konfigurierter climate-Entität ein täglich wiederholter Plan mit maximal
48 Zeilen. Eine Zeile enthält `id`, `time` (HH:MM), `temperature`, `enabled`
und `locked`. Doppelte Uhrzeiten und IDs, ungültige Temperaturen sowie Werte
außerhalb der aktuellen Gerätegrenzen werden abgelehnt. Alte gespeicherte
Zeilen ohne `locked` gelten als entsperrt. Pausierte Zeilen bleiben erhalten.

Die HA-Zeitzone gilt. Im Frühjahr nicht existierende Uhrzeiten werden
übersprungen, im Herbst doppelte Uhrzeiten nur beim ersten Auftreten ausgeführt.
Vergleiche erfolgen in UTC. Neustart, Bearbeitung und Aktivierung lösen keine
Nachholung aus; manuelle Sollwerte bleiben bis zur nächsten Schaltzeit wirksam.

Die optionale Heizungsfreigabe muss exakt `on` sein. `off`, unbekannt oder
nicht verfügbar verhindern den Schaltpunkt. Der Zustand wird vor und nach
dem Temperaturbefehl geprüft. Bestehende Freigabe-/Frostschutzautomationen
bleiben aktiv. Das optionale Setter-Skript erhält `climate_entity` und
`temperature`; ohne Skript wird `climate.set_temperature` aufgerufen.

Ein Serviceaufruf läuft höchstens 90 Sekunden. Timer dürfen bis zu 60 Sekunden
verspätet starten. Laufende Schaltaktionen überlappen nicht. `last_result`
enthält `sent`, `failed`, `blocked`, `busy` oder `missed`. `sent` bestätigt den
abgeschlossenen HA-Serviceaufruf; es ist keine unabhängige Temperaturmessung.
Die Gerätesperre wird dagegen nach dem Setzen frisch vom TRV zurückgelesen.

## Gerätesperre

Shelly BLU TRV über das registrierte Shelly BLU Gateway Gen3:
`BluTrv.Call` → `Sys.SetConfig` mit ausschließlich `config.ui.lock`, danach
`Sys.GetConfig`. Helligkeit, Einheit und Displayausrichtung bleiben erhalten.
Der Adapter nutzt die vorhandenen Gateway-Zugangsdaten und SHA-256-Digest-Auth.
Browser und Logs erhalten keine Zugangsdaten. Ein Gateway-Lock serialisiert
Sperr-RPCs; pro Thermostat sind Planänderungen und Aktionen ebenfalls serialisiert.
Langsame oder unerreichbare Geräte können die Abfrage bis etwa eine Minute
verzögern; Schreibbefehl plus Bestätigung sind zwei getrennte RPCs.

Das Schloss der ausgeführten Zeile gilt bis zum nächsten aktiven Schaltpunkt,
auch über Mitternacht und HA-Neustarts. Eine pausierte Zeile wirkt nicht.
Geschlossen sperrt den Drehring; Fernsteuerung über HA bleibt möglich. Der
Dialog unterscheidet geplante Sperren von zuletzt bestätigtem Gerätestatus.
„Status prüfen“ fragt das Gerät frisch ab, „Jetzt entsperren“ entsperrt sofort.
Beide Aktionen sind unabhängig davon, ob gerade ein Schaltpunkt ansteht.

Vor einem Sperrbefehl wird die Verantwortung dafür dauerhaft gespeichert.
Bei verlorener Antwort bleibt damit eine mögliche Sperre bekannt. Plan aus,
keine aktiven Zeilen oder Freigabe aus lösen das Entsperren aus; bei Fehlern
folgen minütliche Wiederholungen, auch nach einem Neustart. Eine von außen
manuell gesetzte Sperre wird beim Pausieren nicht ungefragt aufgehoben.
Eine reguläre aktive Zeile mit offenem Schloss entsperrt sie hingegen ausdrücklich.

Ein aktiver Plan nur mit geschlossenen Schlössern sperrt fortlaufend. Wird die
letzte Entsperrzeile entfernt, bleibt diese Bedeutung bestehen. Zum Freigeben
„Jetzt entsperren“, Plan pausieren oder eine aktive offene Zeile verwenden.
Scheitert die Temperaturaktion einer offenen Zeile, wird das Entsperren trotzdem
versucht. Scheitert eine geschlossene Zeile, zeigt der Dialog den Fehler; es
gibt keine automatische Wiederholung des Temperaturbefehls nach diesem Punkt.

Entladen wartet eine laufende Aktion ab und entsperrt eine eigene Sperre,
bevor Timer entfernt werden. Ohne Bestätigung bricht das Entladen ab. Beim
normalen HA-Prozessneustart bleibt die geräteseitige Sperre bestehen; Eigentum
und Plan werden wieder geladen. Ein physisch unerreichbares Gerät lässt sich
auch durch Software nicht sofort entsperren.

## Speicherung und API

HA Store, Version 1, atomar mit anschließender Prüfung der geschriebenen Datei.
Erst nach erfolgreicher Speicherung wird die Revision im Arbeitsspeicher
veröffentlicht. Keine Änderungen an `automations.yaml`. Daten liegen separat
unter `.storage`; Modulupdates ersetzen nur Code.

WebSocket-Befehle mit `entity_id`:

- `trv_scheduler/get`: Plan, Revision, Grenzen, nächste Zeit und Laufzeitstatus.
- `trv_scheduler/replace`: `expected_revision`, `enabled`, vollständige `rows`.
- `trv_scheduler/lock_status`: frischer geräteseitiger Sperrstatus.
- `trv_scheduler/unlock`: sofortiger bestätigter Entsperrversuch.

Lesen verlangt HA-Leserecht auf der climate-Entität, Schreiben und Entsperren
Steuerungsrecht. Einrichtung läuft über den Admin-Config-Flow. Es gibt keine
freien Serviceziele oder RPC-Parameter in der öffentlichen API.

Fehlercodes: `revision_conflict`, `invalid_schedule`, `unauthorized`,
`not_found`, `save_failed`, `unlock_failed`. Bei Konflikten bleibt die Eingabe
im Dialog; explizites Neuladen verwirft sie. Kein automatisches Überschreiben.
Pausieren und Löschen funktionieren auch ohne aktuelle Gerätegrenzen;
neue Werte oder Aktivierung erfordern ein verfügbares climate-Gerät.

## Bestandsmigration

Büro/TRV1: kein vorhandener Zeitplan. Schlafzimmer/TRV2: 08:00 17 °C,
17:30 22 °C. Kinderzimmer/TRV3: 07:00 22,5 °C, 20:00 17 °C.
Quelle: Bestandsaufnahme am 17.10.2026; vor Migration erneut prüfen.
Import startet deaktiviert und mit offenen Schlössern. Erst nach geprüfter
Installation die vier alten Zeitautomationen deaktivieren und die neuen
Pläne aktivieren. Die alten Automationen bleiben für Rollback erhalten;
Freigabe-, Frostschutz- und Sollwertspeicher-Automationen bleiben aktiv.

## Kompatibilität und Testgrenzen

Die gebündelte Karte wird in Storage-Dashboards als versionierte Modulressource
registriert und bei Updates ohne Duplikat aktualisiert. So hängt das Laden nicht
von der möglicherweise zwischengespeicherten Startseite der App ab. Fremde
Ressourcen bleiben unverändert; YAML-Ressourcen werden nicht automatisch editiert.

Custom Card mit eigenem HTML-Dialog, standardmäßige HA-WebSocket- und
Frontend-Erweiterungspunkte. Keine Patches an HA-Core oder anderen Integrationen.
Custom Components und separate Store-Dateien überleben normale Updates;
Kompatibilität mit zukünftigen HA-Versionen ist nicht pauschal garantiert.
Kein öffentliches HACS-Repository, keine automatischen Modulupdates.

Automatisierte Browserprüfung in Chromium bei 320, 390 und 1280 Pixel Breite.
Ein reales iPhone mit Companion-App sowie das physische Drehen am gesperrten
TRV können damit nicht abgenommen werden. Hardwaretests prüfen Sperrkonfiguration,
Fernsteuerung trotz Sperre und Wiederherstellung über frische RPC-Antworten.

Quellen: [Shelly BLU TRV](https://shelly-api-docs.shelly.cloud/docs-ble/Devices/BLU_ZB/trv/),
[Gateway RPC](https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen3/ShellyBluGwG3/),
[HA Custom Cards](https://developers.home-assistant.io/docs/frontend/custom-ui/custom-card/).
