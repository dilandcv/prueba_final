import React from 'react';
import { ConnectionStatus } from '../types';

interface NavbarProps {
  status: ConnectionStatus;
  lastUpdate: string | null;
  onRefresh: () => void;
  isLoading: boolean;
  onToggleChat?: () => void;
  isChatOpen?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  status,
  lastUpdate,
  onRefresh,
  isLoading,
  onToggleChat,
  isChatOpen,
}) => {

  const getStatusBadge = () => {
    switch (status) {
      case 'connected':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            En vivo (SSE activo)
          </span>
        );
      case 'connecting':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping"></span>
            Reconectando SSE...
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
            <span className="w-2 h-2 rounded-full bg-rose-500"></span>
            Sin conexión en vivo
          </span>
        );
    }
  };

  const formattedDate = lastUpdate
    ? new Date(lastUpdate).toLocaleString('es-ES', {
        timeZone: 'UTC',
        dateStyle: 'medium',
        timeStyle: 'medium',
      }) + ' UTC'
    : 'Pendiente';

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-sky-600 flex items-center justify-center text-white shadow-md shadow-sky-600/20">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 leading-tight">
              Plataforma de Análisis Sísmico
            </h1>
            <p className="text-xs text-slate-500 font-mono">
              Arquitectura Medallón (Bronze &rarr; Silver &rarr; Gold) &bull; USGS
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {getStatusBadge()}
          <span className="text-xs text-slate-500 hidden sm:inline">
            Actualizado: <strong className="text-slate-700">{formattedDate}</strong>
          </span>
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="p-2 text-slate-600 hover:text-sky-600 hover:bg-slate-100 rounded-lg transition disabled:opacity-50"
            title="Actualizar datos manualmente"
          >
            <svg
              className={`w-4 h-4 ${isLoading ? 'animate-spin text-sky-600' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          {onToggleChat && (
            <button
              onClick={onToggleChat}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition shadow-sm ${
                isChatOpen
                  ? 'bg-sky-600 text-white shadow-sky-600/30'
                  : 'bg-slate-900 hover:bg-slate-800 text-white hover:text-sky-300 border border-slate-700'
              }`}
              title="Abrir Asistente de IA"
              aria-label="Abrir Asistente de IA"
            >
              <svg className="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                />
              </svg>
              <span>Asistente IA</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
