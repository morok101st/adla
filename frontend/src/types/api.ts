export type Mission = {
  id: number;
  name: string;
  mission_date: string | null;
  imported_at: string;
  snapshot_count: number;
  last_snapshot_at: string | null;
};

export type Overview = {
  mission: Pick<Mission, "id" | "name" | "mission_date">;
  snapshot_id: number;
  retrieved_at: string;
  participants: number;
  positions: number;
  filled: number;
  vacant: number;
  regular: number;
  replacement: number;
  guest: number;
  assigned_without_default: number;
  decision_counts: Record<string, number>;
};

export type Position = {
  id: number;
  name: string;
  call_sign: string | null;
  default_member_id: number | null;
  participant: { member_id: number | null; name: string | null } | null;
  decision: string | null;
  assignment_state: "vacant" | "regular" | "replacement" | "guest" | "assigned";
};

export type Unit = {
  id: number;
  name: string;
  short_name: string | null;
  call_sign: string | null;
  depth: number;
  positions: Position[];
  children: Unit[];
};

export type Lineup = {
  mission: Pick<Mission, "id" | "name" | "mission_date">;
  snapshot: { id: number; retrieved_at: string };
  units: Unit[];
};

export type MemberStatistic = {
  member_id: number;
  name: string;
  missions_with_assignment: number;
  assignment_share: number;
  observed_missions: number;
  regular_assignments: number;
  replacement_assignments: number;
  roles: string[];
  decision_counts: Record<string, number>;
  first_mission_date: string | null;
  last_mission_date: string | null;
  last_participation: string | null;
};

export type PersonHistory = {
  mission_id: number;
  mission_name: string;
  mission_date: string | null;
  role: string;
  call_sign: string | null;
  assignment_state: Position["assignment_state"];
  decision: string | null;
};

export type PeriodStatistic = {
  period: string;
  missions_with_assignment: number;
  regular: number;
  replacement: number;
  other_assignments: number;
  decision_counts: Record<string, number>;
};

export type MemberDetail = MemberStatistic & {
  available_years: number[];
  period: { date_from: string | null; date_to: string | null };
  yearly: PeriodStatistic[];
  monthly: PeriodStatistic[];
  history: PersonHistory[];
};

export type MissionTrend = {
  mission_id: number;
  name: string;
  mission_date: string | null;
  participants: number;
  positions: number;
  filled: number;
  vacant: number;
  regular: number;
  replacement: number;
  staffing_rate: number;
};

export type Overall = {
  mission_count: number;
  snapshot_count: number;
  average_participants: number;
  average_staffing_rate: number;
  total_filled_observations: number;
  total_vacant_observations: number;
  total_replacement_observations: number;
  trends: MissionTrend[];
};

export type SyncStatus = {
  status: "starting" | "idle" | "running" | "error";
  next_mission_id: number;
  last_found_id: number | null;
  scanned_count: number;
  imported_count: number;
  initial_scan_complete: boolean;
  last_error: string | null;
  updated_at: string | null;
  last_completed_at: string | null;
};
