import type {
  Lineup,
  MemberDetail,
  MemberStatistic,
  Mission,
  Overall,
  Overview,
  SyncStatus,
} from "../types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let message = `Anfrage fehlgeschlagen (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail ?? message;
    } catch {
      // Der Statuscode bleibt als verständlicher Fallback erhalten.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  missions: () => request<Mission[]>("/api/missions"),
  overview: (missionId: number) =>
    request<Overview>(`/api/statistics/overview?mission_id=${missionId}`),
  lineup: (missionId: number) => request<Lineup>(`/api/lineup?mission_id=${missionId}`),
  members: (search = "") =>
    request<MemberStatistic[]>(`/api/statistics/members?search=${encodeURIComponent(search)}`),
  member: (memberId: number) =>
    request<MemberDetail>(`/api/statistics/members/${memberId}`),
  overall: () => request<Overall>("/api/statistics/overall"),
  syncStatus: () => request<SyncStatus>("/api/sync/status"),
  startScan: () =>
    request<{ started: boolean; status: string }>("/api/sync/scan", { method: "POST" }),
  sync: (missionId: number) =>
    request<{ created: boolean }>(`/api/missions/${missionId}/sync`, { method: "POST" }),
};
