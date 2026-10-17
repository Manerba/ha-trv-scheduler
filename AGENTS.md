# TRV Scheduler

Eigenständige Home-Assistant-Integration, Zielversion zunächst HA 2025.4.2.
Quellcode und Tests lokal entwickeln; produktive Zeitautomationen erst nach
geprüfter Migration umschalten. Keine Zugangsdaten in Dateien oder Tareas.

## Tareas-Projektplanung

Tareas ist die verbindliche Planung und Fortschrittsdokumentation.
- Web-UI: http://10.0.12.7:8504/
- Projekt: Home Assistant – TRV-Zeitsteuerung, ID 76
- MCP: tareas_codex, erwarteter User: Codex @ Tareas (28)
- Teilaufgaben: 380 Spezifikation, 381 Modell/Speicherung/API,
  382 Ausführung, 383 Oberfläche, 384 Paket/Kompatibilität, 385 Migration.
- Vor Tareas-Schreiboperationen `get_project_status` lesen.
- Beschreibungsänderungen mit gelesener Revision; Fortschritt und Testbelege
  mit `handoff_add` dokumentieren. Keine Schatten-Aufgabenliste pflegen.
- Nur direkte, notwendige Vorgänger modellieren; IDs sind stabil.

## Entwicklung

- Zeitberechnung und Validierung unabhängig von HA halten.
- Neue Pläne sind deaktiviert. Kein impliziter Import produktiver Automationen.
- Programmcode und gespeicherte Zeitpläne getrennt halten.
- Änderungen an Speicherung, Berechtigungen und Ausführung gezielt testen.
- Keine HA-internen Dateien oder fremden Integrationen patchen.
