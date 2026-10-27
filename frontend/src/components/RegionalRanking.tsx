import React from 'react';
import { RegionalRankingItem } from '../types';

interface RegionalRankingProps {
  data: RegionalRankingItem[];
  isLoading?: boolean;
  onSelectRegion?: (region: string) => void;
}

export const RegionalRanking: React.FC<RegionalRankingProps> = ({
  data,
  isLoading,
  onSelectRegion,
}) => {
  if (isLoading && (!data || data.length === 0)) {
    return (
      <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 shadow-lg backdrop-blur flex items-center justify-center h-80">
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <svg className="animate-spin h-6 w-6 text-emerald-400" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span className="text-sm">Cargando ranking regional...</span>
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 shadow-lg backdrop-blur flex flex-col justify-center items-center h-80 text-center">
        <svg className="w-10 h-10 text-slate-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
        </svg>
        <p className="text-slate-300 font-medium">Sin datos de ranking regional</p>
        <p className="text-xs text-slate-500 mt-1">No hay actividad registrada en las últimas 24 horas.</p>
      </div>
    );
  }

  const getBadgeStyle = (pos: number) => {
    switch (pos) {
      case 1:
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold';
      case 2:
        return 'bg-slate-300/20 text-slate-200 border-slate-400/40 font-bold';
      case 3:
        return 'bg-amber-700/25 text-amber-400 border-amber-700/40 font-bold';
      default:
        return 'bg-slate-900/40 text-slate-400 border-slate-700/50';
    }
  };

  return (
    <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 shadow-lg backdrop-blur">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
            Ranking de Regiones Más Activas
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">Top zonas sísmicas en las últimas 24 horas</p>
        </div>
        <span className="text-xs font-mono bg-slate-900/60 text-slate-300 px-2.5 py-1 rounded border border-slate-700/50">
          Top {data.length}
        </span>
      </div>

      <div className="space-y-2 overflow-y-auto max-h-72 pr-1 custom-scrollbar">
        {data.map((item) => (
          <div
            key={item.region}
            onClick={() => onSelectRegion && onSelectRegion(item.region)}
            className={`flex items-center justify-between p-2.5 rounded-lg border transition-all ${
              onSelectRegion ? 'cursor-pointer hover:bg-slate-700/50 hover:border-slate-600' : ''
            } bg-slate-900/40 border-slate-800/80`}
          >
            <div className="flex items-center gap-3 min-w-0">
              <span
                className={`w-7 h-7 flex items-center justify-center rounded-md border text-xs font-mono shrink-0 ${getBadgeStyle(
                  item.rank_position
                )}`}
              >
                #{item.rank_position}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-200 truncate" title={item.region}>
                  {item.region}
                </p>
                <p className="text-[11px] text-slate-400">
                  Mag. máx:{' '}
                  <span className="text-amber-400 font-mono font-medium">
                    {item.max_magnitude_24h !== null ? item.max_magnitude_24h.toFixed(1) : 'N/D'}
                  </span>
                </p>
              </div>
            </div>

            <div className="text-right shrink-0 pl-2">
              <span className="text-sm font-semibold font-mono text-emerald-400">
                {item.total_events_24h}
              </span>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider">sismos</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-3 border-t border-slate-700/40 text-[11px] text-slate-400 flex justify-between items-center">
        <span>Haz clic en una región para filtrar</span>
        <span className="text-slate-500">Últimas 24h</span>
      </div>
    </div>
  );
};
