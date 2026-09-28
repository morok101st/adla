import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "./lib/api";
import { UnitTree } from "./components/UnitTree";
import type {
  Lineup,
  MemberDetail,
  MemberStatistic,
  Mission,
  Overall,
  Overview,
  SyncStatus,
} from "./types/api";

type View = "overall" | "missions" | "people";

const formatDate = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" }).format(
        new Date(value),
      )
    : "Nicht bekannt";

const stateLabel: Record<string, string> = {
  regular: "Stammbesetzung",
  replacement: "Ersatz",
  assigned: "Ohne Standardposition",
  guest: "Gast",
  vacant: "Vakant",
};

export default function App() {
  const [view, setView] = useState<View>("overall");
  const [missions, setMissions] = useState<Mission[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [missionInput, setMissionInput] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [lineup, setLineup] = useState<Lineup | null>(null);
  const [overall, setOverall] = useState<Overall | null>(null);
  const [members, setMembers] = useState<MemberStatistic[]>([]);
  const [personSearch, setPersonSearch] = useState("");
  const [person, setPerson] = useState<MemberDetail | null>(null);
  const [personDateFrom, setPersonDateFrom] = useState("");
  const [personDateTo, setPersonDateTo] = useState("");
  const [personYear, setPersonYear] = useState("");
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCore = useCallback(async () => {
    const [missionResult, overallResult, statusResult] = await Promise.all([
      api.missions(),
      api.overall(),
      api.syncStatus(),
    ]);
    setMissions(missionResult);
    setOverall(overallResult);
    setSyncStatus(statusResult);
    setSelectedId((current) => current ?? missionResult[0]?.id ?? null);
  }, []);

  useEffect(() => {
    void loadCore()
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [loadCore]);

  useEffect(() => {
    if (syncStatus?.initial_scan_complete) return;
    const timer = window.setInterval(() => {
      void api.syncStatus().then((status) => {
        setSyncStatus((previous) => {
          if (status.imported_count !== previous?.imported_count) {
            setMembers([]);
            setPerson(null);
            void loadCore();
          }
          return status;
        });
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loadCore, syncStatus?.initial_scan_complete]);

  useEffect(() => {
    if (view !== "people" || members.length > 0) return;
    setLoading(true);
    void api.members()
      .then(setMembers)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [view, members.length]);

  useEffect(() => {
    if (selectedId === null || view !== "missions") return;
    setLoading(true);
    setError(null);
    void Promise.all([api.overview(selectedId), api.lineup(selectedId)])
      .then(([overviewResult, lineupResult]) => {
        setOverview(overviewResult);
        setLineup(lineupResult);
      })
      .catch((reason: Error) => {
        setOverview(null);
        setLineup(null);
        setError(reason.message);
      })
      .finally(() => setLoading(false));
  }, [selectedId, view]);

  const filteredMembers = useMemo(() => {
    const needle = personSearch.trim().toLocaleLowerCase("de");
    if (!needle) return members;
    return members.filter(
      (member) =>
        member.name.toLocaleLowerCase("de").includes(needle) ||
        member.roles.some((role) => role.toLocaleLowerCase("de").includes(needle)),
    );
  }, [members, personSearch]);

  async function handleSync(event: FormEvent) {
    event.preventDefault();
    const missionId = Number(missionInput);
    if (!Number.isInteger(missionId) || missionId <= 0) {
      setError("Bitte eine gültige positive Mission-ID eingeben.");
      return;
    }
    setSyncing(true);
    setError(null);
    try {
      await api.sync(missionId);
      setMembers([]);
      setPerson(null);
      await loadCore();
      setSelectedId(missionId);
      setMissionInput("");
      setView("missions");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Synchronisierung fehlgeschlagen");
    } finally {
      setSyncing(false);
    }
  }

  async function openPerson(memberId: number, dateFrom = personDateFrom, dateTo = personDateTo) {
    setLoading(true);
    setError(null);
    try {
      setPerson(await api.member(memberId, dateFrom, dateTo));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Person konnte nicht geladen werden");
    } finally {
      setLoading(false);
    }
  }

  function filterPerson(event: FormEvent) {
    event.preventDefault();
    if (person) void openPerson(person.member_id, personDateFrom, personDateTo);
  }

  function selectPersonYear(value: string) {
    const dateFrom = value ? `${value}-01-01` : "";
    const dateTo = value ? `${value}-12-31` : "";
    setPersonDateFrom(dateFrom);
    setPersonDateTo(dateTo);
    setPersonYear(value);
    if (person) void openPerson(person.member_id, dateFrom, dateTo);
  }

  function openMission(missionId: number) {
    setSelectedId(missionId);
    setView("missions");
  }

  const missionCards = overview
    ? [
        ["Teilnehmende", overview.participants],
        ["Besetzt", `${overview.filled} / ${overview.positions}`],
        ["Vakant", overview.vacant],
        ["Stammbesetzung", overview.regular],
        ["Ersatz", overview.replacement],
        ["Gäste", overview.guest],
      ]
    : [];

  const overallCards = overall
    ? [
        ["Missionen", overall.mission_count],
        ["Snapshots", overall.snapshot_count],
        ["Ø Teilnehmende", overall.average_participants],
        ["Ø Besetzung", `${overall.average_staffing_rate} %`],
        ["Vakanzen gesamt", overall.total_vacant_observations],
        ["Ersatzbesetzungen", overall.total_replacement_observations],
      ]
    : [];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">AD</div>
        <div className="brand-copy">
          <strong>Lineup Analyzer</strong>
          <span>Airborne Division</span>
        </div>
        <nav className="primary-nav" aria-label="Hauptnavigation">
          <button className={view === "overall" ? "active" : ""} onClick={() => setView("overall")}>
            <span>01</span> Gesamt
          </button>
          <button className={view === "missions" ? "active" : ""} onClick={() => setView("missions")}>
            <span>02</span> Missionen
          </button>
          <button className={view === "people" ? "active" : ""} onClick={() => setView("people")}>
            <span>03</span> Personen
          </button>
        </nav>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <p className="eyebrow">Operational readiness</p>
            <h1>
              {view === "overall" && "Gesamtauswertung"}
              {view === "missions" && (overview?.mission.name ?? "Missionsdashboard")}
              {view === "people" && "Personenauswertung"}
            </h1>
            <p className="muted">
              {view === "missions" && overview
                ? formatDate(overview.mission.mission_date)
                : "Historische Analyse gespeicherter ADCM-Missionen"}
            </p>
          </div>
          <form className="sync-form" onSubmit={handleSync}>
            <label htmlFor="mission-id">Mission gezielt importieren</label>
            <div>
              <input
                id="mission-id"
                inputMode="numeric"
                placeholder="Mission-ID"
                value={missionInput}
                onChange={(event) => setMissionInput(event.target.value)}
              />
              <button disabled={syncing}>{syncing ? "Import …" : "Importieren"}</button>
            </div>
          </form>
        </header>

        {syncStatus && !syncStatus.initial_scan_complete && (
          <section className={`scan-status scan-${syncStatus.status}`}>
            <div>
              <span className="status-dot" />
              <strong>Einmaliger Initialimport: {syncStatus.status === "error" ? "Fehler" : "läuft"}</strong>
              <small>Geprüft bis ID {syncStatus.next_mission_id - 1} von 1000</small>
            </div>
          </section>
        )}

        {error && <div className="notice notice-error">{error}</div>}
        {loading && <div className="notice">Daten werden geladen …</div>}

        {view === "overall" && overall && (
          <>
            <section className="metric-grid" aria-label="Gesamtkennzahlen">
              {overallCards.map(([label, value]) => (
                <article className="metric-card" key={label}>
                  <span>{label}</span><strong>{value}</strong>
                </article>
              ))}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div><p className="eyebrow">Historie</p><h2>Missionen im Vergleich</h2></div>
                <small>Jeweils neuester Snapshot</small>
              </div>
              {overall.trends.length ? (
                <div className="table-scroll">
                  <table className="data-table">
                    <thead><tr><th>Mission</th><th>Datum</th><th>Teiln.</th><th>Besetzt</th><th>Vakant</th><th>Ersatz</th><th>Quote</th></tr></thead>
                    <tbody>
                      {[...overall.trends].reverse().map((item) => (
                        <tr key={item.mission_id} onClick={() => openMission(item.mission_id)}>
                          <td><strong>{item.name}</strong><small>ID {item.mission_id}</small></td>
                          <td>{formatDate(item.mission_date)}</td><td>{item.participants}</td>
                          <td>{item.filled}/{item.positions}</td><td>{item.vacant}</td><td>{item.replacement}</td>
                          <td><div className="rate"><span style={{ width: `${item.staffing_rate}%` }} /></div>{item.staffing_rate} %</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div className="empty-inline">Der automatische Import sucht nach verfügbaren Missionen.</div>}
            </section>
          </>
        )}

        {view === "missions" && (
          <>
            {missions.length > 0 && (
              <nav className="mission-nav" aria-label="Gespeicherte Missionen">
                {missions.map((mission) => (
                  <button className={mission.id === selectedId ? "active" : ""} key={mission.id} onClick={() => setSelectedId(mission.id)}>
                    <span>{mission.name}</span><small>{formatDate(mission.mission_date)}</small>
                  </button>
                ))}
              </nav>
            )}
            {!loading && missions.length === 0 && <div className="empty-state"><span className="empty-icon">↻</span><h2>Missionen werden gesucht</h2><p>Der automatische Import scannt ADCM ab Mission-ID 0.</p></div>}
            {overview && (
              <>
                <section className="metric-grid">
                  {missionCards.map(([label, value]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong></article>)}
                </section>
                <section className="panel lineup-panel">
                  <div className="panel-heading"><div><p className="eyebrow">Organisation</p><h2>Lineup-Struktur</h2></div><small>Stand: {formatDate(overview.retrieved_at)}</small></div>
                  {lineup && <UnitTree units={lineup.units} />}
                </section>
              </>
            )}
          </>
        )}

        {view === "people" && (
          <div className="people-layout">
            <section className="panel people-index">
              <div className="panel-heading"><div><p className="eyebrow">Suche</p><h2>Registrierte Personen</h2></div><span className="result-count">{filteredMembers.length}</span></div>
              <div className="search-box"><input placeholder="Name oder Rolle suchen …" value={personSearch} onChange={(event) => setPersonSearch(event.target.value)} /></div>
              <div className="people-list">
                {filteredMembers.map((member) => (
                  <button className={person?.member_id === member.member_id ? "active" : ""} key={member.member_id} onClick={() => void openPerson(member.member_id)}>
                    <div><strong>{member.name}</strong><small>{member.roles.slice(0, 3).join(" · ")}</small></div>
                    <span>{member.missions_with_assignment}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="panel person-detail">
              {person ? (
                <>
                  <div className="person-hero"><p className="eyebrow">Personenprofil</p><h2>{person.name}</h2><p className="muted">Die Quote beschreibt Missionen mit Zuweisung, nicht bestätigte Anwesenheit oder Abwesenheit.</p></div>
                  <form className="period-filter" onSubmit={filterPerson}>
                    <label>Jahr<select value={personYear} onChange={(event) => selectPersonYear(event.target.value)}><option value="">Alle Jahre</option>{person.available_years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
                    <label>Von<input type="date" value={personDateFrom} onChange={(event) => { setPersonDateFrom(event.target.value); setPersonYear(""); }} /></label>
                    <label>Bis<input type="date" value={personDateTo} onChange={(event) => { setPersonDateTo(event.target.value); setPersonYear(""); }} /></label>
                    <button>Zeitraum anwenden</button>
                  </form>
                  <div className="person-metrics">
                    <article><span>Missionen mit Zuweisung</span><strong>{person.missions_with_assignment}</strong></article>
                    <article><span>Anteil beobachteter Missionen</span><strong>{person.assignment_share} %</strong></article>
                    <article><span>Stammbesetzungen</span><strong>{person.regular_assignments}</strong></article>
                    <article><span>Ersatzbesetzungen</span><strong>{person.replacement_assignments}</strong></article>
                  </div>
                  <div className="role-cloud">{person.roles.map((role) => <span key={role}>{role}</span>)}</div>
                  <div className="period-sections">
                    <section>
                      <h3>Jahresauswertung</h3>
                      <div className="table-scroll"><table className="data-table period-table"><thead><tr><th>Jahr</th><th>Zuweisungen</th><th>Stamm</th><th>Ersatz</th><th>Ja</th><th>Vielleicht</th></tr></thead><tbody>
                        {person.yearly.map((item) => <tr key={item.period}><td><strong>{item.period}</strong></td><td>{item.missions_with_assignment}</td><td>{item.regular}</td><td>{item.replacement}</td><td>{item.decision_counts.yes ?? 0}</td><td>{item.decision_counts.maybe ?? 0}</td></tr>)}
                      </tbody></table></div>
                    </section>
                    <section>
                      <h3>Monatsauswertung</h3>
                      <div className="table-scroll month-table"><table className="data-table period-table"><thead><tr><th>Monat</th><th>Zuweisungen</th><th>Stamm</th><th>Ersatz</th><th>Ja</th><th>Vielleicht</th></tr></thead><tbody>
                        {person.monthly.map((item) => <tr key={item.period}><td><strong>{item.period}</strong></td><td>{item.missions_with_assignment}</td><td>{item.regular}</td><td>{item.replacement}</td><td>{item.decision_counts.yes ?? 0}</td><td>{item.decision_counts.maybe ?? 0}</td></tr>)}
                      </tbody></table></div>
                    </section>
                  </div>
                  <div className="table-scroll">
                    <table className="data-table"><thead><tr><th>Mission</th><th>Rolle</th><th>Typ</th><th>Entscheidung</th></tr></thead>
                      <tbody>{person.history.map((item) => <tr key={`${item.mission_id}-${item.role}`} onClick={() => openMission(item.mission_id)}><td><strong>{item.mission_name}</strong><small>{formatDate(item.mission_date)}</small></td><td>{item.role}</td><td>{stateLabel[item.assignment_state]}</td><td>{item.decision ?? "Nicht übermittelt"}</td></tr>)}</tbody>
                    </table>
                  </div>
                </>
              ) : <div className="empty-state compact"><span className="empty-icon">⌕</span><h2>Person auswählen</h2><p>Suche links nach Namen oder ausgeübter Rolle.</p></div>}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
