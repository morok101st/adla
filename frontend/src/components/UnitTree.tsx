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

function UnitNode({ unit }: { unit: Unit }) {
  const filled = unit.positions.filter((item) => item.assignment_state !== "vacant").length;
  return (
    <section className="unit-node">
      <header className="unit-heading">
        <div>
          <span className="unit-kicker">{unit.short_name ?? unit.call_sign ?? "Einheit"}</span>
          <h3>{unit.name}</h3>
        </div>
        <span className="staffing-count">
          {filled}/{unit.positions.length} Positionen
        </span>
      </header>
      {unit.positions.length > 0 && (
        <ul className="position-list">
          {unit.positions.map((position) => (
            <PositionRow key={position.id} position={position} />
          ))}
        </ul>
      )}
      {unit.children.length > 0 && (
        <div className="unit-children">
          {unit.children.map((child) => (
            <UnitNode key={child.id} unit={child} />
          ))}
        </div>
      )}
    </section>
  );
}

export function UnitTree({ units }: { units: Unit[] }) {
  return (
    <div className="unit-tree">
      {units.map((unit) => (
        <UnitNode key={unit.id} unit={unit} />
      ))}
    </div>
  );
}
