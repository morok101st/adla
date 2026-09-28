# Airborne Division Lineup Analyzer

ADLA ist ein read-only Analyse-Dashboard für Missionsaufstellungen der Airborne Division. Die Anwendung importiert ADCM-Missionen, normalisiert die dynamische Organisationsstruktur und speichert den jeweils letzten gültigen Missionsstand in SQLite.

Produktiv: <https://adla.tog.wan64.de>

## Aktueller Funktionsumfang

### Gesamtübersicht

- Kennzahlen für Missionen, durchschnittliche Teilnahme und Besetzung
- Anteil der Missionen mit mindestens 80 % Besetzung
- durchschnittliche Ersatzquote
- jährliche Besetzungsquote der gesamten Company
- Besetzungsstruktur aus Stamm-, Ersatz- und weiteren Besetzungen sowie Vakanzen
- monatliche Entwicklung der letzten zwölf Monate
- Missionsverlauf als Liniendiagramm für 1, 6 oder 12 Monate, 2 oder 3 Jahre sowie den gesamten Zeitraum
- jährliche Besetzungswerte für Platoons und weitere Organisationseinheiten
- durchschnittliche Zeus-Anwesenheit insgesamt und pro Jahr
- Tabelle aller Missionen für den direkten Vergleich

### Missionen

- horizontaler Zeitstrahl mit Navigation über Jahr, Monat und Mission
- Missionssuche nach Name oder ADCM-ID
- Kennzahlen für Teilnehmende, Positionen, Vakanzen und Ersatzbesetzungen
- dynamischer Organisationsbaum aus den ADCM-Daten
- Besetzungsquote je Einheit einschließlich ihrer Untereinheiten
- einzeln sowie gesammelt ein- und ausklappbare Lineup-Bereiche
- visuelle Unterscheidung von Stamm-, Ersatz-, Gast- und vakanten Besetzungen
- eigener Bereich für die in ADCM geführten Zeuse

### Personen

- Suche nach Name und Funktion
- Anzeige der aktuellen Position in der Ergebnisliste
- historische Funktionsfilter, beispielsweise `AR`, `GR`, `TL`, `PL` oder `Zeus`
- frei wählbarer Datumsbereich sowie Jahres- und Monatsstatistiken
- Missionshistorie und Teilnahmeentscheidungen
- Unterscheidung zwischen regulärer Position, Ersatzbesetzung und sonstiger Funktion
- Anwesenheitsquote zwischen der ersten und letzten Mission einer Person

Die aktuelle Position stammt vorrangig aus der Stammposition des jüngsten Organisationsstands. Ist dort keine Stammposition vorhanden, wird die zuletzt ausgeübte Funktion verwendet. Dadurch können beispielsweise dauerhaft eingesetzte Hauptzeuse als `Zeus` geführt werden, obwohl ADCM für `zeusMembers` kein eigenes `defaultMemberId` liefert.

## Import und Datenhaltung

Beim ersten Start kann ADLA einmalig die ADCM-Missions-IDs `0` bis `1000` durchsuchen. Der Fortschritt wird in SQLite gespeichert und nach einem Neustart fortgesetzt. Nach Abschluss dieses Initialimports finden keine automatischen Suchläufe mehr statt. Weitere Missionen werden ausschließlich über den Menüpunkt **Mission importieren** anhand ihrer ADCM-ID übernommen.

Ein Import:

1. lädt Mission und Organisationsstruktur ausschließlich per HTTP `GET`;
2. validiert die externen Antworten;
3. speichert die ursprünglichen JSON-Daten zur Reproduzierbarkeit;
4. normalisiert Einheiten, Positionen, Mitglieder und Besetzungen;
5. ersetzt den vorherigen Stand derselben Mission erst nach einem erfolgreichen Abruf.

Unveränderte Reimporte erzeugen keine Duplikate. Pro Mission wird nur der letzte gültige Stand für die Analyse verwendet. Fehlgeschlagene Abrufe löschen keine vorhandenen Daten.

Nicht übernommen werden:

- Einträge mit `Clantreffen` im Missionsnamen;
- Einträge ohne eine besetzte reguläre Lineup-Position.

Die produktive SQLite-Datenbank liegt standardmäßig unter:

```text
./data/lineup-analyzer.db
```

Das Verzeichnis wird als Docker-Volume nach `/data` eingebunden. Datenbanken, Sicherungen und `.env` werden nicht versioniert.

## Statistikregeln

- Eine Position ist vakant, wenn keine `assignedMemberParticipation` vorhanden ist.
- Stammposition und tatsächlich eingesetzte Person bleiben getrennte Informationen.
- Eine Ersatzbesetzung liegt vor, wenn ein anderer registrierter ADCM-Nutzer als das `defaultMemberId` eingesetzt ist.
- Manuell eingetragene Personen ohne `memberId` werden nur bei eindeutigem Namensabgleich einem registrierten Mitglied zugeordnet.
- Eine vorhandene manuelle oder Zeus-Zuweisung gilt auch bei `Unknown` oder `maybe` als Anwesenheit.
- Eine fehlende Zuweisung ist keine ausdrücklich erklärte Absage.
- Zeus-Einsätze zählen zur Teilnahme und Personenhistorie, aber nicht als planmäßige Positionen. Sie verändern daher keine Besetzungs-, Vakanz- oder Ersatzquote.
- Die Personenquote betrachtet alle gespeicherten Missionen zwischen der ersten und letzten Teilnahme der Person.
- Historische Auswertungen verwenden den gespeicherten Missionsstand und nicht die heutige Organisationsstruktur.

## ADCM-Zugriff

Die externe ADCM-Schnittstelle wird ausschließlich gelesen:

```text
GET /open-lineup?missionId={missionId}
GET /open-lineup-unit/{unitId}
```

Basis-URL:

```text
https://backend.adcm.airborne-division.de
```

Die Anwendung implementiert keine ADCM-Schreiboperationen und übermittelt die gespeicherten Mitglieder- oder Lineup-Daten nicht an externe Analysedienste.

## Technik

- Backend: Python, FastAPI, SQLAlchemy und HTTPX
- Frontend: React, TypeScript und Vite
- Datenbank: SQLite
- Betrieb: Docker Compose mit Nginx und Traefik
- Standardzeitzone: `Europe/Berlin`

## Installation und Betrieb

Voraussetzungen:

- Docker mit Compose-Plugin
- vorhandenes externes Traefik-Netz, standardmäßig `traefik_default`
- DNS-Eintrag für `adla.tog.wan64.de`

Konfiguration anlegen und Anwendung starten:

```bash
cp .env.example .env
docker compose up -d --build
```

Wichtige Einstellungen:

```text
APP_ENV=production
ADCM_BASE_URL=https://backend.adcm.airborne-division.de
ADCM_ROOT_UNIT_ID=13378
DATABASE_URL=sqlite:////data/lineup-analyzer.db
APP_TIMEZONE=Europe/Berlin
SYNC_TIMEOUT_SECONDS=15
AUTO_IMPORT_ENABLED=true
AUTO_IMPORT_INITIAL_MAX_ID=1000
AUTO_IMPORT_REQUEST_DELAY_MS=100
PUBLIC_URL=https://adla.tog.wan64.de
TRAEFIK_NETWORK=traefik_default
```

Containerstatus und Logs:

```bash
docker compose ps
docker compose logs backend
docker compose logs frontend
```

## Interne API

```text
GET  /api/health
GET  /api/missions
POST /api/missions/{missionId}/sync
GET  /api/lineup?mission_id={missionId}
GET  /api/statistics/overview?mission_id={missionId}
GET  /api/statistics/members?search={text}
GET  /api/statistics/members/{memberId}?date_from={date}&date_to={date}&role={role}
GET  /api/statistics/overall
GET  /api/sync/status
```

`POST /api/missions/{missionId}/sync` schreibt ausschließlich in die lokale ADLA-Datenbank. Gegen ADCM werden dabei weiterhin nur `GET`-Anfragen ausgeführt.

## Tests

Backend-Tests:

```bash
docker compose run --rm backend-test
```

Frontend-Build und TypeScript-Prüfung:

```bash
docker compose build frontend
```

Die Backend-Tests verwenden synthetische Daten und greifen nicht auf die produktive ADCM-API zu.
