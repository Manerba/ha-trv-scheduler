# Verhalten der ersten Version

Technische Spezifikation zu Tareas 76 / Teilaufgabe 380.

- Je konfigurierter climate-Entität ein täglich wiederholter Plan.
- Zeilen enthalten stabile ID, lokale Uhrzeit HH:MM und Zieltemperatur in der
  Einheit der climate-Entität. Maximal 48 Zeilen; doppelte Uhrzeiten werden
  abgelehnt. Die Oberfläche sortiert nach Uhrzeit.
- Jede Zeile hat zusätzlich einen Aktivierungsschalter neben dem Löschen.
  Deaktivierte Zeilen behalten ihre Werte, lösen aber keine Aktion aus.
- Neu angelegte Pläne sind leer und deaktiviert. Aktivierung ist unabhängig
  von der bestehenden Heizungsfreigabe. Leere Pläne schalten nie.
- Die Uhrzeit richtet sich nach der HA-Zeitzone, nicht nach dem iPhone.
- Zu einem Schaltpunkt muss die Freigabe exakt `on` sein. `off`, fehlende oder
  nicht verfügbare Freigaben sperren die Ausführung. Ohne konfigurierte
  Freigabe gilt nur die Aktivierung des Zeitplans.
- Manuelle Temperaturen bleiben bis zum nächsten Schaltpunkt erhalten.
- Neustart, Planänderung, Aktivierung oder erneute Freigabe lösen **keinen
  sofortigen Sollwertwechsel** aus. Es zählt der nächste zukünftige Schaltpunkt.
  Damit wird das Verhalten der vorhandenen HA-Zeitautomationen beibehalten;
  die bestehende Freigabe-Automation darf ihren gemerkten Sollwert herstellen.
- Bei Sommerzeitbeginn werden nicht existierende Uhrzeiten ausgelassen.
  Bei Winterzeitbeginn wird eine doppelte Uhrzeit nur beim ersten Auftreten
  ausgeführt. Vergleiche erfolgen in UTC; diese Regeln werden separat getestet.
- Offline-Zeiträume werden nicht nachträglich abgespielt. Timer dürfen maximal
  60 Sekunden verspätet sein. Nicht erreichbare TRVs werden für diesen
  Schaltpunkt ausgelassen; das Ergebnis steht als `failed` in der API.
  Eine noch laufende Aktion blockiert die nächste Aktion (`busy`), damit sich
  Skriptausführungen nicht überlagern. Fehlerdarstellung folgt in der Karte.
- Ein optionales Setter-Skript erhält `climate_entity` und `temperature`.
  Ohne Skript wird später `climate.set_temperature` aufgerufen. Die vorhandene
  Freigabe-Automation behält die Frostschutz-/Ausschaltfunktion.

## Speicherung und API

Ein HA Store je Config Entry, Version 1, atomare Dateiaktualisierung. Kein
Schreiben in automations.yaml. Schaltzeiten liegen unter `.storage`, getrennt
vom Integration-Code; HA-Konfigurationsbackups müssen beide enthalten.

Lesen liefert Planrevision und Gerätegrenzen. Schreiben ersetzt den gesamten
Plan mit erwarteter Revision. Ein veralteter Client erhält `revision_conflict`
und darf nicht automatisch überschreiben. Erst nach erfolgreichem Speichern
wird die neue Revision im Arbeitsspeicher veröffentlicht. Gerätedaten werden
bei jedem Schreiben neu geprüft; keine stillen Temperaturkorrekturen.

Nur angemeldete Benutzer mit Steuerungsrecht auf die konfigurierte
climate-Entität dürfen den Plan ändern; Leserecht reicht zum Anzeigen.
Die API erlaubt keine Änderung der Gerätezuordnung oder freie Serviceaufrufe.
Einrichtung und optionale Skript-/Freigabezuordnung laufen über den Admin-Config-Flow.

## Migration

TRV1 Büro: leer. TRV2 Schlafzimmer: 08:00 17 °C, 17:30 22 °C.
TRV3 Kinderzimmer: 07:00 22,5 °C, 20:00 17 °C.
Diese Werte sind eine am 17.10.2026 gelesene Bestandsaufnahme, kein automatischer
Import. Vor Umschaltung Bestand erneut lesen und sichern. Alte vier
Zeitautomationen erst nach geprüfter Übernahme deaktivieren, nicht löschen.

## Kompatibilität

Erste Zielversion: HA 2025.4.2. Spätere Versionen benötigen eigene Prüfungen.
Die Custom Card verwendet eigene HTML-Dialogelemente und die HA-Karten-API;
keine internen Thermostat- oder More-Info-Dialoge patchen. HACS-Struktur und
Veröffentlichung folgen der Paketaufgabe; es gibt noch kein veröffentlichtes Repository.
