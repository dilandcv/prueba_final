// Definición de tipos para la Plataforma de Análisis Sísmico

export interface GeneralIndicators {
  events_count: number;
  max_magnitude: number | null;
  avg_magnitude: number | null;
  tsunami_alerts_count: number;
  quality_score: number | null;
  last_update: string | null;
}

export interface TimeSeriesPoint {
  hour_bucket: string;
  total_events: number;
  avg_magnitude: number | null;
  max_magnitude: number | null;
}

export interface MagnitudeDistributionItem {
  magnitude_bracket: string;
  event_count: number;
}

export interface RegionalRankingItem {
  region: string;
  total_events_24h: number;
  max_magnitude_24h: number | null;
  rank_position: number;
}

export interface MapEvent {
  event_id: string;
  magnitude: number;
  place: string;
  region: string;
  time_utc: string;
  latitude: number;
  longitude: number;
  depth_km: number | null;
  tsunami_alert: boolean;
}

export interface QualitySummary {
  quality_score: number | null;
  total_records: number;
  valid_records: number;
  invalid_records: number;
  failed_rules: Record<string, number>;
  evaluated_at: string | null;
}

export interface FilterState {
  startDate: string;
  endDate: string;
  minMagnitude: string;
  region: string;
}

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected' | 'error';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  model_name?: string;
  used_fallback?: boolean;
}

export interface ChatResponse {
  response: string;
  model_name: string;
  used_fallback: boolean;
  timestamp: string;
}

