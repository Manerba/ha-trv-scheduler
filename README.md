# TRV Zeitsteuerung

Home-Assistant-Erweiterung für tägliche Heizungszeitpläne. In Entwicklung;
noch nicht auf dem produktiven HA installiert.

Ziel ist ein Button unter jedem Thermostat, der einen Dialog mit Uhrzeit,
Zieltemperatur, Aktivierungsschalter und Löschen je Zeile öffnet. Neue Zeilen
werden über einen Plus-Button angelegt. Auch pausierte Zeilen bleiben gespeichert.

Planung und Fortschritt: **Tareas-Projekt 76**, [Tareas](http://10.0.12.7:8504/).
Die Teilaufgaben 380–385 enthalten Abnahmebedingungen und Abhängigkeiten.

## Erster Implementierungsstand

- Integration-Gerüst und Config Flow je Thermostat.
- Validierte, versionierte Pläne mit Schalter pro Zeile und Planaktivierung.
- HA Store mit atomarem Schreiben, zusätzlicher Speicherprüfung und
  Revisionskonflikten bei gleichzeitigen Änderungen.
- WebSocket-API mit HA-Entitätsberechtigungen.
- Erste serverseitige Ausführung, Freigabe und optionales Setter-Skript.
- Tests mit den tatsächlichen HA-2025.4.2-Python-Klassen für Store,
  Serviceaufrufe und Lebenszyklus; gezielte Unit-Tests für Modell und API.

**Noch offen:** Dashboard-Karte/Overlay, Browser- und iPhone-Prüfung, kompletter
HA-Start mit Installation über die Oberfläche, abschließende Laufzeitprüfung,
Installationspaket und Migration. Es gibt noch keine öffentliche HACS-Version.

## Entwicklung und Tests

Python 3.13 wird für Home Assistant 2025.4.2 benötigt. In einem separaten
virtuellen Environment:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Alle Gerätebefehle der Tests bleiben in der isolierten HA-Instanz oder werden
gezielt abgefangen. Die Tests kontaktieren keine realen TRVs.

## Verhalten

Neue Pläne sind deaktiviert. Die separate vorhandene Heizungsfreigabe wird
bei jedem Schaltpunkt geprüft. Es gibt kein automatisches Nachholen beim
Neustart oder Einschalten. Manuelle Sollwerte bleiben bis zur nächsten
Schaltzeit wirksam. Bei Sommerzeitbeginn entfallende Schaltzeiten werden
übersprungen; doppelte Uhrzeiten im Herbst gelten nur beim ersten Auftreten.

Details: [docs/behavior.md](docs/behavior.md).
Die Bestandszeiten für die drei TRVs stehen als deaktivierte Beispiele in
[examples/existing-plans.json](examples/existing-plans.json).

## API für die kommende Karte

Über die angemeldete HA-WebSocket-Verbindung:

```javascript
const result = await hass.callWS({
  type: "trv_scheduler/get",
  entity_id: "climate.trv2"
});

await hass.callWS({
  type: "trv_scheduler/replace",
  entity_id: "climate.trv2",
  expected_revision: result.schedule.revision,
  enabled: false,
  rows: [
    {id: "morning", time: "08:00", temperature: 17, enabled: true},
    {id: "evening", time: "17:30", temperature: 22, enabled: false}
  ]
});
```

Die API gibt `revision_conflict`, `invalid_schedule`, `unauthorized`,
`not_found` oder `save_failed` zurück. Veraltete Daten nicht blind erneut
senden; nach einem Konflikt neu laden. Zeitplanänderungen werden erst nach
bestätigter Speicherung wirksam. Pausieren und Löschen funktionieren auch
bei einem nicht erreichbaren Thermostat; neue Werte erfordern Gerätegrenzen.

## Installation und Datenhaltung

Die Integration liegt vollständig in `custom_components/trv_scheduler`.
Für spätere Testinstallation diesen Ordner nach `/config/custom_components/`
kopieren, HA neu starten und „TRV Zeitsteuerung“ unter Geräte & Dienste
hinzufügen. Die Dashboard-Karte ist in diesem Entwicklungsstand noch nicht
enthalten. Nicht zur produktiven Migration verwenden, bevor Aufgabe 384
abgeschlossen ist.

Daten: `/config/.storage/trv_scheduler.<config_entry_id>`. Diese Dateien
gehören mit den Config Entries ins HA-Konfigurationsbackup. Updates ersetzen
nur Programmdateien. Entladen/Entfernen eines Config Entry löscht keine
Zeitplandatei; erneutes Anlegen erzeugt eine neue ID, ein automatischer
Wiederimport ist noch nicht vorhanden. Für Rollback die neue Integration
deaktivieren und erst danach die alten Zeitautomationen wieder einschalten.

HA-Erweiterungspunkte: [Custom integrations](https://developers.home-assistant.io/docs/creating_component_index/),
[WebSocket-Kommandos](https://developers.home-assistant.io/docs/frontend/extending/websocket-api/),
[Custom cards](https://developers.home-assistant.io/docs/frontend/custom-ui/custom-card/).
