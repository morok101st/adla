# Airborne Division Lineup Analyzer

ADLA importiert Missionsaufstellungen read-only aus ADCM, speichert unveränderliche historische Snapshots in SQLite und visualisiert Besetzung, Vakanzen und Ersatzbesetzungen.

Projekt-URL: <https://adla.tog.wan64.de>

## Funktionsumfang des ersten MVP

- automatischer, fortsetzbarer Missionsscan ab ADCM-ID `0`
- zusätzlicher manueller Import über eine ADCM-Mission-ID
- rekursive Übernahme der dynamischen Unit-Hierarchie
- idempotente, hashbasierte Snapshots in SQLite
- klare Trennung von Standardmitglied, tatsächlicher Besetzung, Gast und Vakanz
- Einzelmissions-Dashboards mit Organisationsbaum
- missionsübergreifendes Dashboard mit Besetzungs- und Vakanztrend
- Personensuche nach Name und Rolle mit Zuweisungs-, Rollen- und Entscheidungshistorie
- FastAPI-Dokumentation unter `/docs` im Backend-Netz
- Docker-Compose-Deployment hinter Traefik

Die ADCM-Anbindung führt ausschließlich `GET`-Anfragen gegen folgende Endpunkte aus:

```text
GET /open-lineup?missionId={missionId}
GET /open-lineup-unit/{unitId}
```

## Start

```bash
cp .env.example .env
docker compose up -d --build
```

Die Compose-Datei verbindet das Frontend mit dem vorhandenen externen Docker-Netz `traefik_default`. Der Traefik-Router ist für `adla.tog.wan64.de`, TLS und den Certresolver `production` vorkonfiguriert.

SQLite wird unter `./data/lineup-analyzer.db` persistent gespeichert. Datenbankdateien und `.env` werden nicht versioniert.

Der erste automatische Lauf prüft standardmäßig die IDs `0` bis `1000`. Der Fortschritt wird in SQLite gespeichert und nach Neustarts fortgesetzt. Anschließend werden bekannte Missionen aktualisiert und täglich die nächsten 100 IDs hinter der zuletzt gefundenen Mission geprüft. Umfang, Pause und Intervall sind über die `AUTO_IMPORT_*`-Variablen in `.env.example` konfigurierbar.

## API

```text
GET  /api/health
GET  /api/missions
POST /api/missions/{missionId}/sync
GET  /api/lineup?mission_id={missionId}
GET  /api/statistics/overview?mission_id={missionId}
GET  /api/statistics/members
GET  /api/statistics/members/{memberId}
GET  /api/statistics/overall
GET  /api/sync/status
POST /api/sync/scan
```

Ein fehlgeschlagener ADCM-Abruf wird vor Beginn eines neuen Snapshots abgebrochen. Bestehende Snapshots bleiben erhalten.

Eine fehlende Zuweisung wird in der Personenauswertung nicht als Absage oder Abwesenheit interpretiert. Die angezeigte Personenquote bezeichnet ausschließlich den Anteil gespeicherter Missionen, in denen eine konkrete Positionszuweisung vorliegt.

## Tests

```bash
docker compose run --rm backend-test
docker compose run --rm frontend npm run build
```

Die Backend-Tests verwenden ausschließlich synthetische Daten und greifen nicht auf die Live-ADCM-API zu.
