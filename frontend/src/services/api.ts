import {
  ChatResponse,
  FilterState,
  GeneralIndicators,
  MagnitudeDistributionItem,
  MapEvent,
  QualitySummary,
  RegionalRankingItem,
  TimeSeriesPoint,
} from '../types';


const API_BASE = '/api/v1';

function buildQueryString(filters?: Partial<FilterState>, limit?: number): string {
  const params = new URLSearchParams();
  if (filters?.startDate) params.append('start_date', filters.startDate);
  if (filters?.endDate) {
    const endValue = filters.endDate.includes('T')
      ? filters.endDate
      : `${filters.endDate}T23:59:59Z`;
    params.append('end_date', endValue);
  }
  if (filters?.minMagnitude && !isNaN(Number(filters.minMagnitude))) {

    params.append('min_magnitude', filters.minMagnitude);
  }
  if (filters?.region && filters.region.trim() !== '') {
    params.append('region', filters.region.trim());
  }
  if (limit) params.append('limit', limit.toString());

  const str = params.toString();
  return str ? `?${str}` : '';
}

export async function fetchIndicators(filters?: FilterState): Promise<GeneralIndicators> {
  const res = await fetch(`${API_BASE}/metrics/indicators${buildQueryString(filters)}`);
  if (!res.ok) throw new Error(`Error ${res.status}: No se pudieron obtener los indicadores`);
  return res.json();
}

export async function fetchTimeSeries(filters?: FilterState): Promise<TimeSeriesPoint[]> {
  const res = await fetch(`${API_BASE}/events/timeseries${buildQueryString(filters)}`);
  if (!res.ok) throw new Error(`Error ${res.status}: No se pudo obtener la serie temporal`);
  return res.json();
}

export async function fetchMagnitudeDistribution(filters?: FilterState): Promise<MagnitudeDistributionItem[]> {
  const res = await fetch(`${API_BASE}/metrics/magnitude-distribution${buildQueryString(filters)}`);
  if (!res.ok) throw new Error(`Error ${res.status}: No se pudo obtener la distribución`);
  return res.json();
}

export async function fetchRegionalRanking(limit = 10): Promise<RegionalRankingItem[]> {
  const res = await fetch(`${API_BASE}/metrics/regional-ranking?limit=${limit}`);
  if (!res.ok) throw new Error(`Error ${res.status}: No se pudo obtener el ranking`);
  return res.json();
}

export async function fetchMapEvents(filters?: FilterState, limit = 500): Promise<MapEvent[]> {
  const res = await fetch(`${API_BASE}/events/map${buildQueryString(filters, limit)}`);
  if (!res.ok) throw new Error(`Error ${res.status}: No se pudieron obtener los eventos del mapa`);
  return res.json();
}

export async function fetchQualitySummary(): Promise<QualitySummary> {
  const res = await fetch(`${API_BASE}/quality/summary`);
  if (!res.ok) throw new Error(`Error ${res.status}: No se pudo obtener la calidad`);
  return res.json();
}

export async function sendChatMessage(
  message: string,
  history?: { role: string; content: string }[]
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/ai/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      history: history || [],
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new Error(errorData?.detail || `Error ${res.status}: No se pudo comunicar con el asistente de IA`);
  }

  return res.json();
}

