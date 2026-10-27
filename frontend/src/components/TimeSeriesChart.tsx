import React from 'react';
import { TimeSeriesPoint } from '../types';

interface TimeSeriesChartProps {
  data: TimeSeriesPoint[];
  isLoading?: boolean;
}

export const TimeSeriesChart: React.FC<TimeSeriesChartProps> = ({ data, isLoading }) => {
  if (isLoading && (!data || data.length === 0)) {
    return (
      <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 shadow-lg backdrop-blur flex items-center justify-center h-80">
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <svg className="animate-spin h-6 w-6 text-sky-400" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span className="text-sm">Cargando serie temporal...</span>
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 shadow-lg backdrop-blur flex flex-col justify-center items-center h-80 text-center">
        <svg className="w-10 h-10 text-slate-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
        <p className="text-slate-300 font-medium">Sin datos para la serie temporal</p>
        <p className="text-xs text-slate-500 mt-1">Ajusta los filtros de fecha o magnitud para ver resultados.</p>
      </div>
    );
  }

  // Ordenar cronológicamente si vienen desordenados
  const sorted = [...data].sort((a, b) => new Date(a.hour_bucket).getTime() - new Date(b.hour_bucket).getTime());

  // Limitar a los últimos 36 puntos para visualización limpia
  const displayPoints = sorted.slice(-36);
  const maxEvents = Math.max(...displayPoints.map((d) => d.total_events), 1);

  // Dimensiones SVG
  const width = 640;
  const height = 220;
  const paddingLeft = 36;
  const paddingRight = 16;
  const paddingTop = 20;
  const paddingBottom = 40;

  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;

  const barWidth = Math.max(4, Math.min(24, (chartWidth / displayPoints.length) * 0.7));

  const formatHour = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return `${String(d.getUTCHours()).padStart(2, '0')}:00`;
    } catch {
      return '';
    }
  };

  const formatDateLabel = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return `${d.getUTCDate()}/${d.getUTCMonth() + 1}`;
    } catch {
      return '';
    }
  };

  return (
    <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 shadow-lg backdrop-blur">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-sky-400"></span>
            Serie Temporal de Eventos por Hora
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">Frecuencia horaria en el período seleccionado (UTC)</p>
        </div>
        <div className="text-xs font-mono bg-slate-900/60 text-slate-300 px-2.5 py-1 rounded border border-slate-700/50">
          {displayPoints.length} intervalos
        </div>
      </div>

      <div className="w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-56 select-none"
          preserveAspectRatio="none"
        >
          {/* Líneas de cuadrícula horizontales */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = paddingTop + chartHeight * (1 - ratio);
            const val = Math.round(maxEvents * ratio);
            return (
              <g key={ratio}>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={width - paddingRight}
                  y2={y}
                  stroke="#334155"
                  strokeDasharray="3 3"
                  strokeWidth="0.8"
                />
                <text
                  x={paddingLeft - 6}
                  y={y + 3}
                  textAnchor="end"
                  fontSize="10"
                  fill="#94a3b8"
                  fontFamily="monospace"
                >
                  {val}
                </text>
              </g>
            );
          })}

          {/* Barras */}
          {displayPoints.map((point, idx) => {
            const x =
              paddingLeft +
              (idx / (displayPoints.length - 1 || 1)) * (chartWidth - barWidth);
            const barHeight = (point.total_events / maxEvents) * chartHeight;
            const y = paddingTop + chartHeight - barHeight;

            // Etiquetas cada N barras
            const step = Math.ceil(displayPoints.length / 6);
            const showLabel = idx % step === 0 || idx === displayPoints.length - 1;

            return (
              <g key={point.hour_bucket} className="group cursor-pointer">
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={Math.max(barHeight, 2)}
                  rx="2"
                  className="fill-sky-500 hover:fill-sky-400 transition-colors"
                >
                  <title>{`${formatDateLabel(point.hour_bucket)} ${formatHour(point.hour_bucket)} UTC: ${point.total_events} sismos (Mag máx: ${point.max_magnitude ?? 'N/D'})`}</title>
                </rect>

                {showLabel && (
                  <text
                    x={x + barWidth / 2}
                    y={height - paddingBottom + 16}
                    textAnchor="middle"
                    fontSize="9"
                    fill="#94a3b8"
                    fontFamily="monospace"
                  >
                    {formatHour(point.hour_bucket)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="flex justify-between items-center text-xs text-slate-400 mt-2 pt-2 border-t border-slate-700/40">
        <span>Inicio: {displayPoints[0] ? formatDateLabel(displayPoints[0].hour_bucket) : '-'}</span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 bg-sky-500 rounded-sm"></span> Conteo horario
        </span>
        <span>Fin: {displayPoints[displayPoints.length - 1] ? formatDateLabel(displayPoints[displayPoints.length - 1].hour_bucket) : '-'}</span>
      </div>
    </div>
  );
};
