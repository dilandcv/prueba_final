import React from 'react';
import { ConnectionStatus } from '../types';

interface StatusBannerProps {
  status: ConnectionStatus;
  errorMessage?: string | null;
}

export const StatusBanner: React.FC<StatusBannerProps> = ({ status, errorMessage }) => {
  if (status === 'connected' && !errorMessage) return null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
      {errorMessage && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-sm flex items-center justify-between mb-3 shadow-sm">
          <div className="flex items-center gap-2.5">
            <svg className="w-5 h-5 text-rose-600 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <span>{errorMessage} (se conservan los últimos datos cargados)</span>
          </div>
        </div>
      )}

      {status === 'connecting' && (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 text-xs flex items-center gap-2">
          <svg className="w-4 h-4 text-amber-600 animate-spin flex-shrink-0" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
          </svg>
          <span>Reconectando canal de eventos SSE con el servidor...</span>
        </div>
      )}
    </div>
  );
};
