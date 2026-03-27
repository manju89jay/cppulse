import type {
  Summary,
  FindingsResponse,
  Hotspot,
  RiskScores,
  KnowledgeSilo,
  RoadmapItem,
} from "../types";

const BASE_URL = "/api/v1";

async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchSummary(): Promise<Summary> {
  return apiFetch<Summary>("/summary");
}

export async function fetchFindings(
  page?: number,
  category?: string
): Promise<FindingsResponse> {
  const params = new URLSearchParams();
  if (page !== undefined) params.set("page", String(page));
  if (category) params.set("category", category);
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<FindingsResponse>(`/findings${query}`);
}

export async function fetchHotspots(): Promise<Hotspot[]> {
  return apiFetch<Hotspot[]>("/hotspots");
}

export async function fetchRisks(): Promise<RiskScores> {
  return apiFetch<RiskScores>("/risks");
}

export async function fetchSilos(): Promise<KnowledgeSilo[]> {
  return apiFetch<KnowledgeSilo[]>("/silos");
}

export async function fetchRoadmap(): Promise<RoadmapItem[]> {
  return apiFetch<RoadmapItem[]>("/roadmap");
}
