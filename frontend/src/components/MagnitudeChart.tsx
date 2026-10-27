import React from 'react';
import { MagnitudeDistributionItem } from '../types';

interface MagnitudeChartProps {
  data: MagnitudeDistributionItem[];
  isLoading?: boolean;
}

const BRACKET_COLORS: Record<string, { bar: string; text: string; bg: string }> = {
  '2.5 - 2.9': { bar: 'bg-emerald-500', text: 'text-emerald-400', bg: 'bg-emerald-950/40' },
  '3.0 - 3.9': { bar: 'bg-amber-500', text: 'text-amber-400', bg: 'bg-amber-950/40' },
  '4.0 - 4.9': { bar: 'bg-orange-500', text: 'text-orange-400', bg: 'bg-orange-950/40' },
  '5.0 - 5.9': { bar: 'bg-red-500', text: 'text-red-400', bg: 'bg-red-950/40' },
  '6.0+': { bar: 'bg-purple-500', text: 'text-purple-400', bg: 'bg-purple-950/40' },
};

const DEFAULT_COLOR = { bar: 'bg-sky-500', text: 'text-sky-400', bg: 'bg-sky-950/40' };

export const MagnitudeChart: React.FC<MagnitudeChartProps> = ({ data, isLoading }) => {
  if (isLoading && (!data || data.length === 0)) {
    return (
      <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 shadow-lg backdrop-blur flex items-center justify-center h-80">
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <svg className="animate-spin h-6 w-6 text-amber-400" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span className="text-sm">Cargando distribución...</span>
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 shadow-lg backdrop-blur flex flex-col justify-center items-center h-80 text-center">
        <svg className="w-10 h-10 text-slate-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        <p className="text-slate-300 font-medium">Sin datos de distribución</p>
        <p className="text-xs text-slate-500 mt-1">No hay sismos para los filtros actuales.</p>
      </div>
    );
  }

  const totalEvents = data.reduce((acc, curr) => acc + curr.event_count, 0);
  const maxCount = Math.max(...data.map((d) => d.event_count), 1);

  return (
    <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 shadow-lg backdrop-blur">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
            Distribución por Rango de Magnitud
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">Clasificación de eventos según su intensidad</p>
        </div>
        <span className="text-xs font-mono bg-slate-900/60 text-slate-300 px-2.5 py-1 rounded border border-slate-700/50">
          Total: {totalEvents.toLocaleString()}
        </span>
      </div>

      <div className="space-y-3.5 mt-2">
        {data.map((item) => {
          const percentage = totalEvents > 0 ? (item.event_count / totalEvents) * 100 : 0;
          const barWidthPercent = (item.event_count / maxCount) * 100;
          const colors = BRACKET_COLORS[item.magnitude_bracket] || DEFAULT_COLOR;

          return (
            <div key={item.magnitude_bracket} className="space-y-1">
              <div className="flex justify-between items-center text-xs">
                <span className="font-medium text-slate-200 flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${colors.bar}`}></span>
                  Mag. {item.magnitude_bracket}
                </span>
                <div className="flex items-center gap-2 font-mono">
                  <span className="text-slate-100 font-semibold">
                    {item.event_count.toLocaleString()}
                  </span>
                  <span className="text-slate-400 text-[11px] w-12 text-right">
                    {percentage.toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Barra de progreso */}
              <div className="w-full bg-slate-900/70 rounded-full h-2.5 overflow-hidden p-0.5 border border-slate-700/40">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${colors.bar}`}
                  style={{ width: `${Math.max(barWidthPercent, 1)}%` }}
                ></div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-5 pt-3 border-t border-slate-700/40 text-[11px] text-slate-400 flex justify-between items-center">
        <span>Frecuencia por intervalos estándar USGS</span>
        <span className="text-slate-500">Gold Layer Analytics</span>
      </div>
    </div>
  );
};
