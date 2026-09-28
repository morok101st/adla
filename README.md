# Airborne Division Lineup Analyzer

ADLA importiert Missionsaufstellungen read-only aus ADCM, speichert unveränderliche historische Snapshots in SQLite und visualisiert Besetzung, Vakanzen und Ersatzbesetzungen.

Projekt-URL: <https://adla.tog.wan64.de>

## Funktionsumfang des ersten MVP

- einmaliger, fortsetzbarer Initialscan der ADCM-IDs `0` bis `1000`
- zusätzlicher manueller Import über eine ADCM-Mission-ID
- rekursive Übernahme der dynamischen Unit-Hierarchie
- idempotente, hashbasierte Snapshots in SQLite
- klare Trennung von Standardmitglied, tatsächlicher Besetzung, Gast und Vakanz
- Einzelmissions-Dashboards mit Organisationsbaum
- missionsübergreifendes Dashboard mit Besetzungs- und Vakanztrend
- Personensuche nach Name und Rolle mit Datumsfilter sowie Monats- und Jahresauswertung
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

Der automatische Initiallauf prüft genau einmal die IDs `0` bis `1000`. Der Fortschritt wird in SQLite gespeichert und nach Neustarts fortgesetzt. Sobald der Initiallauf abgeschlossen ist, finden keine automatischen ADCM-Abrufe mehr statt; weitere Missionen werden ausschließlich manuell über ihre Mission-ID importiert. Missionen mit 0 % Besetzung und als „Clantreffen“ bezeichnete Einträge werden nicht gespeichert.

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
```

Ein fehlgeschlagener ADCM-Abruf wird vor Beginn eines neuen Snapshots abgebrochen. Bestehende Snapshots bleiben erhalten.

Eine fehlende Zuweisung wird in der Personenauswertung nicht als Absage oder Abwesenheit interpretiert. Die angezeigte Personenquote bezeichnet ausschließlich den Anteil gespeicherter Missionen, in denen eine konkrete Positionszuweisung vorliegt.

## Tests

```bash
docker compose run --rm backend-test
docker compose run --rm frontend npm run build
```

Die Backend-Tests verwenden ausschließlich synthetische Daten und greifen nicht auf die Live-ADCM-API zu.
