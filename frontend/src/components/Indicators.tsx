import React from 'react';
import { GeneralIndicators } from '../types';

interface IndicatorsProps {
  indicators: GeneralIndicators | null;
  isLoading: boolean;
}

export const Indicators: React.FC<IndicatorsProps> = ({ indicators, isLoading }) => {
  const cards = [
    {
      title: 'Total Eventos Registrados',
      value: indicators ? indicators.events_count.toLocaleString() : '-',
      subtext: 'En el periodo consultado',
      color: 'text-slate-900',
      badge: 'Gold',
      icon: (
        <svg className="w-5 h-5 text-sky-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
      ),
    },
    {
      title: 'Magnitud Máxima',
      value: indicators && indicators.max_magnitude !== null ? `M ${indicators.max_magnitude.toFixed(1)}` : '-',
      subtext: 'Mayor sismo detectado',
      color: 'text-amber-600',
      badge: 'Pico',
      icon: (
        <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      ),
    },
    {
      title: 'Magnitud Promedio',
      value: indicators && indicators.avg_magnitude !== null ? `M ${indicators.avg_magnitude.toFixed(2)}` : '-',
      subtext: 'Media aritmética',
      color: 'text-slate-900',
      badge: 'Media',
      icon: (
        <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
    },
    {
      title: 'Alertas de Tsunami',
      value: indicators ? indicators.tsunami_alerts_count.toString() : '-',
      subtext: 'Eventos con bandera activa',
      color: indicators && indicators.tsunami_alerts_count > 0 ? 'text-rose-600 font-bold' : 'text-slate-900',
      badge: 'Alerta',
      icon: (
        <svg className="w-5 h-5 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      ),
    },
    {
      title: 'Puntaje de Calidad',
      value: indicators ? `${indicators.quality_score.toFixed(1)}%` : '-',
      subtext: 'Validado por PySpark',
      color: indicators && indicators.quality_score >= 90 ? 'text-emerald-600' : 'text-amber-600',
      badge: 'Reglas',
      icon: (
        <svg className="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      title: 'Última Disponibilidad',
      value: indicators && indicators.last_update
        ? new Date(indicators.last_update).toLocaleTimeString('es-ES', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit' }) + ' UTC'
        : 'N/A',
      subtext: indicators && indicators.last_update
        ? new Date(indicators.last_update).toLocaleDateString('es-ES', { timeZone: 'UTC', dateStyle: 'short' })
        : 'Sin ingesta',
      color: 'text-slate-900',
      badge: 'Sync',
      icon: (
        <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
      {cards.map((c, i) => (
        <div
          key={i}
          className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden"
        >
          <div className="flex items-center justify-between mb-2">
            <div className="p-2 rounded-lg bg-slate-50 border border-slate-100">{c.icon}</div>
            <span className="text-[10px] font-medium tracking-wide uppercase px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">
              {c.badge}
            </span>
          </div>
          <p className="text-xs font-medium text-slate-500 truncate" title={c.title}>
            {c.title}
          </p>
          <div className="mt-1">
            {isLoading && !indicators ? (
              <div className="h-7 bg-slate-100 animate-pulse rounded w-20"></div>
            ) : (
              <p className={`text-xl font-bold tracking-tight ${c.color}`}>{c.value}</p>
            )}
          </div>
          <p className="text-[11px] text-slate-400 mt-1 truncate">{c.subtext}</p>
        </div>
      ))}
    </div>
  );
};
