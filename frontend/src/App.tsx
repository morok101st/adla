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

type View = "overall" | "missions" | "people" | "import";
type TimelineLevel = "year" | "month" | "mission";
type MissionTrendRange = 1 | 6 | 12 | 24 | 36 | "all";

const missionYear = (mission: Mission) =>
  mission.mission_date ? new Date(mission.mission_date).getFullYear() : 0;

const missionMonth = (mission: Mission) =>
  mission.mission_date ? new Date(mission.mission_date).getMonth() : -1;

const monthLabel = (month: number) =>
  month >= 0
    ? new Intl.DateTimeFormat("de-DE", { month: "long" }).format(new Date(2024, month, 1))
    : "Ohne Datum";

function centeredSlots<T>(items: T[], activeIndex: number): Array<T | null> {
  const center = activeIndex >= 0 ? activeIndex : 0;
  return Array.from({ length: 5 }, (_, slot) => {
    const index = center + slot - 2;
    return index >= 0 && index < items.length ? items[index] : null;
  });
}

const formatDate = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" }).format(
        new Date(value),
      )
    : "Nicht bekannt";

const formatTimelineDate = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "short", year: "numeric" }).format(
        new Date(value),
      )
    : "Ohne Datum";

const formatMonth = (period: string) => {
  const [year, month] = period.split("-").map(Number);
  return new Intl.DateTimeFormat("de-DE", { month: "short", year: "2-digit" }).format(
    new Date(year, month - 1, 1),
  );
};

const splitIntoColumns = <T,>(items: T[]) => {
  const middle = Math.ceil(items.length / 2);
  return [items.slice(0, middle), items.slice(middle)];
};

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
  const [missionSearch, setMissionSearch] = useState("");
  const [timelineLevel, setTimelineLevel] = useState<TimelineLevel>("year");
  const [timelineYear, setTimelineYear] = useState<number | null>(null);
  const [timelineMonth, setTimelineMonth] = useState<number | null>(null);
  const [missionTrendRange, setMissionTrendRange] = useState<MissionTrendRange>(1);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [lineup, setLineup] = useState<Lineup | null>(null);
  const [overall, setOverall] = useState<Overall | null>(null);
  const [members, setMembers] = useState<MemberStatistic[]>([]);
  const [personSearch, setPersonSearch] = useState("");
  const [person, setPerson] = useState<MemberDetail | null>(null);
  const [personDateFrom, setPersonDateFrom] = useState("");
  const [personDateTo, setPersonDateTo] = useState("");
  const [personYear, setPersonYear] = useState("");
  const [personRole, setPersonRole] = useState("");
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [missionLoading, setMissionLoading] = useState(false);
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
    let cancelled = false;
    setMissionLoading(true);
    setError(null);
    void Promise.all([api.overview(selectedId), api.lineup(selectedId)])
      .then(([overviewResult, lineupResult]) => {
        if (cancelled) return;
        setOverview(overviewResult);
        setLineup(lineupResult);
      })
      .catch((reason: Error) => {
        if (cancelled) return;
        setOverview(null);
        setLineup(null);
        setError(reason.message);
      })
      .finally(() => {
        if (!cancelled) setMissionLoading(false);
      });
    return () => {
      cancelled = true;
    };
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

  const chronologicalMissions = useMemo(() => {
    return [...missions].sort((left, right) => {
      const leftTime = left.mission_date ? new Date(left.mission_date).getTime() : 0;
      const rightTime = right.mission_date ? new Date(right.mission_date).getTime() : 0;
      return leftTime - rightTime || left.id - right.id;
    });
  }, [missions]);

  const searchedMissions = useMemo(() => {
    const needle = missionSearch.trim().toLocaleLowerCase("de");
    return chronologicalMissions.filter(
        (mission) =>
          !needle ||
          mission.name.toLocaleLowerCase("de").includes(needle) ||
          String(mission.id).includes(needle) ||
          formatTimelineDate(mission.mission_date).toLocaleLowerCase("de").includes(needle),
      );
  }, [chronologicalMissions, missionSearch]);

  const selectedMission = missions.find((mission) => mission.id === selectedId) ?? null;
  const years = useMemo(
    () => [...new Set(chronologicalMissions.map(missionYear))],
    [chronologicalMissions],
  );
  const activeYear = timelineYear ?? (selectedMission ? missionYear(selectedMission) : years.at(-1) ?? 0);
  const months = useMemo(
    () => [...new Set(chronologicalMissions.filter((mission) => missionYear(mission) === activeYear).map(missionMonth))],
    [activeYear, chronologicalMissions],
  );
  const selectedMissionMonth = selectedMission && missionYear(selectedMission) === activeYear
    ? missionMonth(selectedMission)
    : null;
  const activeMonth = timelineMonth ?? selectedMissionMonth ?? months.at(-1) ?? -1;
  const timelineMissions = missionSearch.trim()
    ? searchedMissions
    : chronologicalMissions.filter(
        (mission) => missionYear(mission) === activeYear && missionMonth(mission) === activeMonth,
      );
  const yearIndex = years.indexOf(activeYear);
  const monthIndex = months.indexOf(activeMonth);
  const missionIndex = timelineMissions.findIndex((mission) => mission.id === selectedId);
  const timelineLength = timelineLevel === "year"
    ? years.length
    : timelineLevel === "month"
      ? months.length
      : timelineMissions.length;
  const timelineIndex = timelineLevel === "year"
    ? yearIndex
    : timelineLevel === "month"
      ? monthIndex
      : missionIndex;
  const yearSlots = centeredSlots(years, yearIndex);
  const monthSlots = centeredSlots(months, monthIndex);
  const missionSlots = centeredSlots(timelineMissions, missionIndex);
  const timelineResultLabel = missionSearch.trim()
    ? `${searchedMissions.length} / ${missions.length}`
    : timelineLevel === "year"
      ? `${years.length} Jahre`
      : timelineLevel === "month"
        ? `${months.length} Monate`
        : `${timelineMissions.length} Missionen`;

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
      setTimelineLevel("mission");
      setTimelineYear(null);
      setTimelineMonth(null);
      setView("missions");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Synchronisierung fehlgeschlagen");
    } finally {
      setSyncing(false);
    }
  }

  async function openPerson(
    memberId: number,
    dateFrom = personDateFrom,
    dateTo = personDateTo,
    role = personRole,
  ) {
    setLoading(true);
    setError(null);
    setPersonRole(role);
    try {
      setPerson(await api.member(memberId, dateFrom, dateTo, role));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Person konnte nicht geladen werden");
    } finally {
      setLoading(false);
    }
  }

  function filterPerson(event: FormEvent) {
    event.preventDefault();
    if (person) void openPerson(person.member_id, personDateFrom, personDateTo, personRole);
  }

  function selectPersonYear(value: string) {
    const dateFrom = value ? `${value}-01-01` : "";
    const dateTo = value ? `${value}-12-31` : "";
    setPersonDateFrom(dateFrom);
    setPersonDateTo(dateTo);
    setPersonYear(value);
    if (person) void openPerson(person.member_id, dateFrom, dateTo, personRole);
  }

  function selectPersonRole(role: string) {
    const nextRole = role === personRole ? "" : role;
    setPersonRole(nextRole);
    if (person) void openPerson(person.member_id, personDateFrom, personDateTo, nextRole);
  }

  function openMission(missionId: number) {
    const mission = missions.find((item) => item.id === missionId);
    if (mission) {
      setTimelineYear(missionYear(mission));
      setTimelineMonth(missionMonth(mission));
    }
    setTimelineLevel("mission");
    setSelectedId(missionId);
    setView("missions");
  }

  function chooseTimelineYear(year: number) {
    setTimelineYear(year);
    setTimelineMonth(null);
    setTimelineLevel("month");
  }

  function chooseTimelineMonth(month: number) {
    setTimelineMonth(month);
    setTimelineLevel("mission");
    const monthMissions = chronologicalMissions.filter(
      (mission) => missionYear(mission) === activeYear && missionMonth(mission) === month,
    );
    const latestMission = monthMissions.at(-1);
    if (latestMission) setSelectedId(latestMission.id);
  }

  function openMissionBrowser() {
    setMissionSearch("");
    setTimelineLevel("year");
    setTimelineYear(null);
    setTimelineMonth(null);
    setView("missions");
  }

  function showTimelineYears() {
    setMissionSearch("");
    setTimelineLevel("year");
    setTimelineMonth(null);
  }

  function showTimelineMonths() {
    setMissionSearch("");
    setTimelineLevel("month");
  }

  function updateMissionSearch(value: string) {
    setMissionSearch(value);
    if (value.trim()) {
      setTimelineLevel("mission");
    } else {
      setTimelineLevel("year");
      setTimelineYear(null);
      setTimelineMonth(null);
    }
  }

  function moveTimeline(direction: -1 | 1) {
    if (!timelineLength) return;
    const currentIndex = timelineIndex >= 0 ? timelineIndex : direction > 0 ? -1 : 1;
    const targetIndex = Math.min(
      timelineLength - 1,
      Math.max(0, currentIndex + direction),
    );
    if (timelineLevel === "year") {
      setTimelineYear(years[targetIndex]);
      setTimelineMonth(null);
    } else if (timelineLevel === "month") {
      setTimelineMonth(months[targetIndex]);
    } else {
      setSelectedId(timelineMissions[targetIndex].id);
    }
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
        ["Ø Teilnehmende", overall.average_participants],
        ["Ø Besetzung", `${overall.average_staffing_rate} %`],
        ["Missionen ≥ 80 %", `${overall.missions_at_least_80_percent} / ${overall.mission_count}`],
        ["Ø Ersatzquote", `${overall.average_replacement_rate} %`],
      ]
    : [];
  const recentMonths = overall?.monthly.slice(-12) ?? [];
  const recentMonthColumns = splitIntoColumns(recentMonths);
  const unitStatisticColumns = splitIntoColumns(overall?.unit_statistics ?? []);
  const recentMissionTrends = (() => {
    const dated = (overall?.trends ?? [])
      .filter((item) => item.mission_date)
      .sort((a, b) => new Date(a.mission_date!).getTime() - new Date(b.mission_date!).getTime());
    if (!dated.length) return [];
    if (missionTrendRange === "all") return dated;
    const cutoff = new Date(dated[dated.length - 1].mission_date!);
    cutoff.setMonth(cutoff.getMonth() - missionTrendRange);
    return dated.filter((item) => new Date(item.mission_date!).getTime() >= cutoff.getTime());
  })();
  const missionTrendRangeLabel = missionTrendRange === "all"
    ? "Gesamter Zeitraum"
    : missionTrendRange < 12
      ? `${missionTrendRange} ${missionTrendRange === 1 ? "Monat" : "Monate"}`
      : `${missionTrendRange / 12} ${missionTrendRange === 12 ? "Jahr" : "Jahre"}`;
  const recentMissionAverage = recentMissionTrends.length
    ? Math.round(
        (recentMissionTrends.reduce((sum, item) => sum + item.staffing_rate, 0)
          / recentMissionTrends.length) * 10,
      ) / 10
    : 0;
  const missionLinePoints = recentMissionTrends.map((item, index) => ({
    ...item,
    x: recentMissionTrends.length === 1 ? 490 : 55 + (index / (recentMissionTrends.length - 1)) * 875,
    y: 170 - item.staffing_rate * 1.5,
  }));
  const missionLabelStep = Math.max(1, Math.ceil(missionLinePoints.length / 10));
  const mixEntries = overall
    ? [
        { label: "Stammbesetzung", value: overall.assignment_mix.regular, color: "#a7d66f" },
        { label: "Ersatz", value: overall.assignment_mix.replacement, color: "#e8790f" },
        { label: "Weitere", value: overall.assignment_mix.other, color: "#8cbdda" },
        { label: "Vakant", value: overall.assignment_mix.vacant, color: "#ef7a72" },
      ]
    : [];
  const mixTotal = mixEntries.reduce((sum, item) => sum + item.value, 0);
  let mixOffset = 0;
  const mixGradient = mixTotal
    ? `conic-gradient(${mixEntries.map((item) => {
        const start = mixOffset;
        mixOffset += (item.value / mixTotal) * 100;
        return `${item.color} ${start}% ${mixOffset}%`;
      }).join(", ")})`
    : "#2e2e2e";

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
          <button className={view === "missions" ? "active" : ""} onClick={openMissionBrowser}>
            <span>02</span> Missionen
          </button>
          <button className={view === "people" ? "active" : ""} onClick={() => setView("people")}>
            <span>03</span> Personen
          </button>
          <button className={view === "import" ? "active" : ""} onClick={() => setView("import")}>
            <span>04</span> Import
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
              {view === "import" && "Mission importieren"}
            </h1>
            <p className="muted">
              {view === "missions" && overview
                ? formatDate(overview.mission.mission_date)
                : view === "import"
                  ? "Manueller, schreibgeschützter Abruf aus ADCM"
                  : "Historische Analyse gespeicherter ADCM-Missionen"}
            </p>
          </div>
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
            <section className="metric-grid overall-metrics" aria-label="Gesamtkennzahlen">
              {overallCards.map(([label, value]) => (
                <article className="metric-card" key={label}>
                  <span>{label}</span><strong>{value}</strong>
                </article>
              ))}
            </section>
            <div className="analytics-grid">
              <section className="panel analytics-panel">
                <div className="panel-heading">
                  <div><p className="eyebrow">Jahresvergleich</p><h2>Ø Besetzungsquote</h2></div>
                  <small>{overall.yearly.length} Jahre</small>
                </div>
                <div className="year-chart" aria-label="Durchschnittliche Besetzung nach Jahr">
                  {overall.yearly.map((item) => (
                    <article key={item.period} title={`${item.average_staffing_rate} % bei ${item.missions} Missionen`}>
                      <strong>{item.average_staffing_rate} %</strong>
                      <div><span style={{ height: `${item.average_staffing_rate}%` }} /></div>
                      <b>{item.period}</b>
                      <small>{item.missions} M</small>
                    </article>
                  ))}
                </div>
              </section>

              <section className="panel analytics-panel">
                <div className="panel-heading">
                  <div><p className="eyebrow">Besetzungsstruktur</p><h2>Alle Positionsbeobachtungen</h2></div>
                  <small>{mixTotal.toLocaleString("de-DE")}</small>
                </div>
                <div className="mix-chart">
                  <div className="donut" style={{ background: mixGradient }}>
                    <div><strong>{overall.average_staffing_rate} %</strong><span>Ø besetzt</span></div>
                  </div>
                  <div className="mix-legend">
                    {mixEntries.map((item) => (
                      <div key={item.label}>
                        <i style={{ background: item.color }} />
                        <span>{item.label}</span>
                        <strong>{mixTotal ? Math.round((item.value / mixTotal) * 1000) / 10 : 0} %</strong>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            </div>

            <section className="panel monthly-panel">
              <div className="panel-heading">
                <div><p className="eyebrow">Monatliche Entwicklung</p><h2>Letzte 12 Monate</h2></div>
                <small>Quote · Teilnehmende · Vakanzen</small>
              </div>
              <div className="monthly-chart">
                {recentMonthColumns.map((column, columnIndex) => (
                  <div className="monthly-chart-column" key={columnIndex}>
                    {column.map((item) => (
                      <article key={item.period}>
                        <div><strong>{formatMonth(item.period)}</strong><small>{item.missions} Missionen</small></div>
                        <div className="monthly-bar"><span style={{ width: `${item.average_staffing_rate}%` }} /></div>
                        <b>{item.average_staffing_rate} %</b>
                        <span>{item.average_participants} Teiln.</span>
                        <span>{item.average_vacancies} vakant</span>
                      </article>
                    ))}
                  </div>
                ))}
              </div>
            </section>

            <section className="panel mission-rate-panel">
              <div className="panel-heading">
                <div><p className="eyebrow">Missionen · {missionTrendRangeLabel}</p><h2>Besetzungsquote im Verlauf</h2></div>
                <div className="mission-rate-controls">
                  <div className="trend-range-selector" aria-label="Zeitraum auswählen">
                    {([
                      [1, "1 Monat"], [6, "6 Monate"], [12, "12 Monate"],
                      [24, "2 Jahre"], [36, "3 Jahre"], ["all", "Gesamt"],
                    ] as [MissionTrendRange, string][]).map(([value, label]) => (
                      <button className={missionTrendRange === value ? "active" : ""} key={value} onClick={() => setMissionTrendRange(value)}>{label}</button>
                    ))}
                  </div>
                  <div className="mission-period-average"><small>Durchschnitt</small><strong>{recentMissionAverage} %</strong></div>
                </div>
              </div>
              {missionLinePoints.length ? (
                <div className="mission-line-chart">
                  <svg viewBox="0 0 980 215" role="img" aria-label={`Besetzungsquoten der letzten zwei Monate, durchschnittlich ${recentMissionAverage} Prozent`}>
                    {[100, 75, 50, 25, 0].map((value) => {
                      const y = 170 - value * 1.5;
                      return <g key={value}><line className="chart-grid-line" x1="55" x2="930" y1={y} y2={y} /><text className="chart-axis-label" x="45" y={y + 4}>{value} %</text></g>;
                    })}
                    <line className="chart-average-line" x1="55" x2="930" y1={170 - recentMissionAverage * 1.5} y2={170 - recentMissionAverage * 1.5} />
                    <polyline className="chart-rate-line" points={missionLinePoints.map((item) => `${item.x},${item.y}`).join(" ")} />
                    {missionLinePoints.map((item) => (
                      <g key={item.mission_id}>
                        <circle className="chart-rate-point" cx={item.x} cy={item.y} r={missionLinePoints.length > 50 ? 2.5 : 5}><title>{item.name}: {item.staffing_rate} %</title></circle>
                        {missionLinePoints.length <= 14 && <text className="chart-value-label" x={item.x} y={item.y - 10}>{item.staffing_rate} %</text>}
                        {(item === missionLinePoints[missionLinePoints.length - 1] || missionLinePoints.indexOf(item) % missionLabelStep === 0) && (
                          <text className="chart-date-label" x={item.x} y="198">{new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: missionTrendRange === 1 ? undefined : "2-digit" }).format(new Date(item.mission_date!))}</text>
                        )}
                      </g>
                    ))}
                  </svg>
                </div>
              ) : <div className="empty-inline">Keine Missionen mit Datum vorhanden.</div>}
            </section>

            <section className="panel unit-analysis-panel">
              <div className="panel-heading">
                <div><p className="eyebrow">Organisation · Jahresvergleich</p><h2>Ø Besetzung nach Einheit / Platoon</h2></div>
                <small>je Jahr · inklusive Untereinheiten</small>
              </div>
              <div className="unit-analysis-grid">
                {unitStatisticColumns.map((column, columnIndex) => (
                  <div className="unit-analysis-column" key={columnIndex}>
                    {column.map((unit) => {
                      const attendanceMaximum = Math.max(
                        1,
                        ...unit.yearly.map((item) => item.average_participants ?? 0),
                      );
                      return (
                      <article className={unit.metric_type === "attendance" ? "attendance-analysis" : ""} key={unit.name}>
                        <div className="unit-analysis-summary">
                          {unit.metric_type === "attendance" ? (
                            <>
                              <div><strong>{unit.name}</strong><small>Funktion Zeus · alle Missionen</small></div>
                              <div className="unit-analysis-rate"><span style={{ width: `${Math.min(100, ((unit.average_participants ?? 0) / attendanceMaximum) * 100)}%` }} /></div>
                              <b>Ø {unit.average_participants}</b>
                              <dl><div><dt>Wert</dt><dd>Anwesende</dd></div></dl>
                            </>
                          ) : (
                            <>
                              <div><strong>{unit.name}</strong><small>{unit.missions} Missionen · Ø {unit.average_positions} Positionen</small></div>
                              <div className="unit-analysis-rate"><span style={{ width: `${unit.average_staffing_rate}%` }} /></div>
                              <b>{unit.average_staffing_rate} %</b>
                              <dl>
                                <div><dt>Vakant</dt><dd>{unit.average_vacancies}</dd></div>
                                <div><dt>Ersatz</dt><dd>{unit.average_replacements}</dd></div>
                              </dl>
                            </>
                          )}
                        </div>
                        <div className="unit-yearly-chart">
                          {overall.yearly.map((year) => {
                            const value = unit.yearly.find((item) => item.period === year.period);
                            const displayValue = unit.metric_type === "attendance"
                              ? value?.average_participants
                              : value?.average_staffing_rate;
                            const barHeight = unit.metric_type === "attendance"
                              ? ((value?.average_participants ?? 0) / attendanceMaximum) * 100
                              : (value?.average_staffing_rate ?? 0);
                            return (
                              <div key={year.period} title={value ? `${displayValue}${unit.metric_type === "staffing" ? " %" : " anwesend"} bei ${value.missions} Missionen` : "Keine Daten"}>
                                <strong>{value ? `${displayValue}${unit.metric_type === "staffing" ? " %" : ""}` : "–"}</strong>
                                <span><i style={{ height: `${barHeight}%` }} /></span>
                                <small>{year.period}</small>
                              </div>
                            );
                          })}
                        </div>
                      </article>
                    );})}
                  </div>
                ))}
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div><p className="eyebrow">Historie</p><h2>Missionen im Vergleich</h2></div>
                <small>Aktueller Datenstand je Mission</small>
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
              <section className="panel mission-timeline-panel" aria-label="Missionszeitstrahl">
                <div className="timeline-toolbar">
                  <div>
                    <p className="eyebrow">Zeitstrahl</p>
                    <h2>
                      {timelineLevel === "year" && "Jahr auswählen"}
                      {timelineLevel === "month" && `${activeYear || "Ohne Datum"}: Monat auswählen`}
                      {timelineLevel === "mission" && (missionSearch.trim() ? "Suchergebnisse" : `${monthLabel(activeMonth)} ${activeYear || ""}`)}
                    </h2>
                    <div className="timeline-breadcrumb">
                      <button onClick={showTimelineYears}>Jahre</button>
                      {timelineLevel !== "year" && !missionSearch.trim() && <><span>›</span><button onClick={showTimelineMonths}>{activeYear || "Ohne Datum"}</button></>}
                      {timelineLevel === "mission" && !missionSearch.trim() && <><span>›</span><strong>{monthLabel(activeMonth)}</strong></>}
                      {missionSearch.trim() && <><span>›</span><strong>Suche</strong></>}
                    </div>
                  </div>
                  <label className="mission-search">
                    <span>Mission suchen</span>
                    <input
                      type="search"
                      placeholder="Name, ID oder Datum …"
                      value={missionSearch}
                      onChange={(event) => updateMissionSearch(event.target.value)}
                    />
                  </label>
                  <span className="timeline-result-count">{timelineResultLabel}</span>
                </div>
                {timelineLength ? (
                  <div className="horizontal-timeline">
                    <button
                      className="timeline-arrow"
                      aria-label="Im Zeitstrahl zurück"
                      disabled={timelineIndex <= 0}
                      onClick={() => moveTimeline(-1)}
                    >‹</button>
                    <div className="timeline-track">
                      <span className="timeline-line" aria-hidden="true" />
                      {timelineLevel === "year" && yearSlots.map((year, slot) =>
                        year !== null ? (
                          <button
                            className={`timeline-node timeline-period timeline-slot-${slot} ${year === activeYear ? "active" : ""}`}
                            key={year}
                            onClick={() => chooseTimelineYear(year)}
                          >
                            <span className="timeline-dot" />
                            <strong>{year || "Ohne Datum"}</strong>
                            <em>{chronologicalMissions.filter((mission) => missionYear(mission) === year).length} Missionen</em>
                          </button>
                        ) : <span className={`timeline-spacer timeline-slot-${slot}`} key={`year-empty-${slot}`} />,
                      )}
                      {timelineLevel === "month" && monthSlots.map((month, slot) =>
                        month !== null ? (
                          <button
                            className={`timeline-node timeline-period timeline-slot-${slot} ${month === activeMonth ? "active" : ""}`}
                            key={month}
                            onClick={() => chooseTimelineMonth(month)}
                          >
                            <span className="timeline-dot" />
                            <strong>{monthLabel(month)}</strong>
                            <em>{chronologicalMissions.filter((mission) => missionYear(mission) === activeYear && missionMonth(mission) === month).length} Missionen</em>
                          </button>
                        ) : <span className={`timeline-spacer timeline-slot-${slot}`} key={`month-empty-${slot}`} />,
                      )}
                      {timelineLevel === "mission" && missionSlots.map((mission, slot) =>
                        mission ? (
                          <button
                            className={`timeline-node timeline-slot-${slot} ${mission.id === selectedId ? "active" : ""}`}
                            key={mission.id}
                            aria-current={mission.id === selectedId ? "true" : undefined}
                            onClick={() => setSelectedId(mission.id)}
                          >
                            <span className="timeline-dot" />
                            <small>{formatTimelineDate(mission.mission_date)}</small>
                            <strong>{mission.name}</strong>
                            <em>ID {mission.id}</em>
                          </button>
                        ) : <span className={`timeline-spacer timeline-slot-${slot}`} key={`empty-${slot}`} />,
                      )}
                    </div>
                    <button
                      className="timeline-arrow"
                      aria-label="Im Zeitstrahl weiter"
                      disabled={timelineIndex >= timelineLength - 1}
                      onClick={() => moveTimeline(1)}
                    >›</button>
                  </div>
                ) : <div className="empty-inline">Keine Mission entspricht der Suche.</div>}
              </section>
            )}
            {!loading && missions.length === 0 && <div className="empty-state"><span className="empty-icon">↻</span><h2>Missionen werden gesucht</h2><p>Der automatische Import scannt ADCM ab Mission-ID 0.</p></div>}
            {overview && (
              <div className={`mission-detail ${missionLoading ? "updating" : ""}`} aria-busy={missionLoading}>
                {missionLoading && <span className="mission-loading-badge">Mission wird aktualisiert …</span>}
                <section className="metric-grid">
                  {missionCards.map(([label, value]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong></article>)}
                </section>
                <section className="panel lineup-panel">
                  <div className="panel-heading"><div><p className="eyebrow">Organisation</p><h2>Lineup-Struktur</h2></div><small>Stand: {formatDate(overview.retrieved_at)}</small></div>
                  {lineup && <UnitTree key={lineup.snapshot.id} units={lineup.units} />}
                </section>
              </div>
            )}
            {!overview && missionLoading && <div className="notice">Mission wird geladen …</div>}
          </>
        )}

        {view === "import" && (
          <section className="panel import-panel">
            <div className="import-copy">
              <p className="eyebrow">ADCM · Read-only</p>
              <h2>Mission gezielt übernehmen</h2>
              <p className="muted">Gib die ADCM-Mission-ID ein. Ein vorhandener Datenstand wird bei Änderungen atomar ersetzt; ADCM selbst wird nicht verändert.</p>
            </div>
            <form className="sync-form import-form" onSubmit={handleSync}>
              <label htmlFor="mission-id">ADCM-Mission-ID</label>
              <div>
                <input
                  id="mission-id"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="z. B. 763"
                  value={missionInput}
                  onChange={(event) => setMissionInput(event.target.value)}
                />
                <button disabled={syncing}>{syncing ? "Import läuft …" : "Mission importieren"}</button>
              </div>
            </form>
            <div className="import-rules">
              <span>Nur HTTP GET gegen ADCM</span>
              <span>0-%-Missionen werden verworfen</span>
              <span>Clantreffen werden nicht gespeichert</span>
            </div>
          </section>
        )}

        {view === "people" && (
          <div className="people-layout">
            <section className="panel people-index">
              <div className="panel-heading"><div><p className="eyebrow">Suche</p><h2>Registrierte Personen</h2></div><span className="result-count">{filteredMembers.length}</span></div>
              <div className="search-box"><input placeholder="Name oder Rolle suchen …" value={personSearch} onChange={(event) => setPersonSearch(event.target.value)} /></div>
              <div className="people-list">
                {filteredMembers.map((member) => (
                  <button className={person?.member_id === member.member_id ? "active" : ""} key={member.member_id} onClick={() => void openPerson(member.member_id, personDateFrom, personDateTo, "")}>
                    <div><strong>{member.name}</strong><small>{member.current_role ?? "Keine aktuelle Position"}</small></div>
                    <span>{member.missions_with_assignment}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="panel person-detail">
              {person ? (
                <>
                  <div className="person-hero"><p className="eyebrow">Personenprofil</p><h2>{person.name}</h2><p className="muted">{person.selected_role ? `Anwesenheit und Historie für die Funktion ${person.selected_role}, gemessen von der ersten bis zur letzten Mission in dieser Funktion.` : "Die durchschnittliche Anwesenheit wird von der ersten bis zur letzten gespeicherten Mission der Person berechnet."}</p></div>
                  <form className="period-filter" onSubmit={filterPerson}>
                    <label>Jahr<select value={personYear} onChange={(event) => selectPersonYear(event.target.value)}><option value="">Alle Jahre</option>{person.available_years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
                    <label>Von<input type="date" value={personDateFrom} onChange={(event) => { setPersonDateFrom(event.target.value); setPersonYear(""); }} /></label>
                    <label>Bis<input type="date" value={personDateTo} onChange={(event) => { setPersonDateTo(event.target.value); setPersonYear(""); }} /></label>
                    <button>Zeitraum anwenden</button>
                  </form>
                  <div className="person-metrics">
                    <article><span>{person.selected_role ? "Missionen in Funktion" : "Missionen mit Zuweisung"}</span><strong>{person.missions_with_assignment}</strong></article>
                    <article><span>Ø Anwesenheit · {person.missions_in_active_period} Missionen</span><strong>{person.attendance_rate} %</strong></article>
                    <article><span>Stammbesetzungen</span><strong>{person.regular_assignments}</strong></article>
                    <article><span>Ersatzbesetzungen</span><strong>{person.replacement_assignments}</strong></article>
                  </div>
                  <div className="role-cloud" aria-label="Nach Funktion filtern">
                    <span className="role-filter-label">Funktion</span>
                    <button className={!personRole ? "active" : ""} onClick={() => selectPersonRole("")}>Alle</button>
                    {person.roles.map((role) => <button className={personRole === role ? "active" : ""} key={role} onClick={() => selectPersonRole(role)}>{role}</button>)}
                  </div>
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
