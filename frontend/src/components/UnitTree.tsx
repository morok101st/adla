import { useMemo, useState } from "react";
import type { Position, Unit } from "../types/api";

const stateLabels: Record<Position["assignment_state"], string> = {
  vacant: "Vakant",
  regular: "Stammbesetzung",
  replacement: "Ersatz",
  guest: "Gast / unbekannt",
  assigned: "Besetzt (ohne Standard)",
};

function PositionRow({ position }: { position: Position }) {
  return (
    <li className="position-row">
      <div className="position-role">
        <span>{position.name}</span>
        {position.call_sign && <small>{position.call_sign}</small>}
      </div>
      <div className="position-person">
        <span>{position.participant?.name ?? "Nicht besetzt"}</span>
        {position.decision && <small>Entscheidung: {position.decision}</small>}
      </div>
      <span className={`state state-${position.assignment_state}`}>
        {stateLabels[position.assignment_state]}
      </span>
    </li>
  );
}

function unitStaffing(unit: Unit): { filled: number; positions: number } {
  const staffingPositions = unit.positions.filter((item) => item.counts_for_staffing);
  const ownFilled = staffingPositions.filter((item) => item.assignment_state !== "vacant").length;
  return unit.children.reduce(
    (total, child) => {
      const childStaffing = unitStaffing(child);
      return {
        filled: total.filled + childStaffing.filled,
        positions: total.positions + childStaffing.positions,
      };
    },
    { filled: ownFilled, positions: staffingPositions.length },
  );
}

function auxiliaryParticipants(unit: Unit): number {
  return unit.positions.filter(
    (item) => !item.counts_for_staffing && item.assignment_state !== "vacant",
  ).length + unit.children.reduce((total, child) => total + auxiliaryParticipants(child), 0);
}

function UnitNode({
  unit,
  expandedIds,
  onToggle,
}: {
  unit: Unit;
  expandedIds: ReadonlySet<number>;
  onToggle: (unitId: number) => void;
}) {
  const expanded = expandedIds.has(unit.id);
  const staffing = unitStaffing(unit);
  const auxiliary = auxiliaryParticipants(unit);
  const rate = staffing.positions ? Math.round((staffing.filled / staffing.positions) * 100) : 0;
  const expandable = unit.positions.length > 0 || unit.children.length > 0;
  return (
    <section className={`unit-node ${expanded ? "expanded" : "collapsed"}`}>
      <header className="unit-heading">
        <button
          className="unit-toggle"
          aria-expanded={expandable ? expanded : undefined}
          disabled={!expandable}
          onClick={() => expandable && onToggle(unit.id)}
        >
          <div className="unit-title">
            <span className="unit-chevron" aria-hidden="true">{expandable ? (expanded ? "−" : "+") : "·"}</span>
            <div>
              <h3>{unit.name}</h3>
            </div>
          </div>
          <div className="unit-staffing">
            {staffing.positions > 0 ? (
              <>
                <div className="unit-rate"><span style={{ width: `${rate}%` }} /></div>
                <strong>{rate} %</strong>
                <span className="staffing-count">{staffing.filled}/{staffing.positions} Positionen</span>
              </>
            ) : (
              <span className="staffing-count auxiliary-count">{auxiliary} anwesend</span>
            )}
          </div>
        </button>
      </header>
      {expanded && unit.positions.length > 0 && (
        <ul className="position-list">
          {unit.positions.map((position) => (
            <PositionRow key={position.id} position={position} />
          ))}
        </ul>
      )}
      {expanded && unit.children.length > 0 && (
        <div className="unit-children">
          {unit.children.map((child) => (
            <UnitNode key={child.id} unit={child} expandedIds={expandedIds} onToggle={onToggle} />
          ))}
        </div>
      )}
    </section>
  );
}

export function UnitTree({ units }: { units: Unit[] }) {
  const expandableIds = useMemo(() => {
    const result: number[] = [];
    const collect = (unit: Unit) => {
      if (unit.positions.length > 0 || unit.children.length > 0) result.push(unit.id);
      unit.children.forEach(collect);
    };
    units.forEach(collect);
    return result;
  }, [units]);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(
    () => new Set(units.filter((unit) => unit.positions.length > 0 || unit.children.length > 0).map((unit) => unit.id)),
  );
  const allExpanded = expandableIds.length > 0 && expandableIds.every((id) => expandedIds.has(id));

  const toggleUnit = (unitId: number) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(unitId)) next.delete(unitId);
      else next.add(unitId);
      return next;
    });
  };

  return (
    <div className="unit-tree">
      <div className="unit-tree-actions">
        <button
          type="button"
          disabled={expandableIds.length === 0}
          onClick={() => setExpandedIds(new Set(allExpanded ? [] : expandableIds))}
        >
          {allExpanded ? "Alle einklappen" : "Alle ausklappen"}
        </button>
      </div>
      {units.map((unit) => (
        <UnitNode key={unit.id} unit={unit} expandedIds={expandedIds} onToggle={toggleUnit} />
      ))}
    </div>
  );
}
