import React from 'react';
import { FilterState } from '../types';

interface FiltersProps {
  filters: FilterState;
  onChange: (newFilters: FilterState) => void;
  onReset: () => void;
}

export const Filters: React.FC<FiltersProps> = ({ filters, onChange, onReset }) => {
  const handleChange = (field: keyof FilterState, value: string) => {
    onChange({
      ...filters,
      [field]: value,
    });
  };

  const hasActiveFilters = Boolean(
    filters.startDate || filters.endDate || filters.minMagnitude || filters.region
  );

  return (
    <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm">
      <div className="flex flex-wrap items-end gap-3 sm:gap-4">
        {/* Fecha Inicio */}
        <div className="flex-1 min-w-[140px]">
          <label className="block text-xs font-semibold text-slate-600 mb-1">
            Desde (Fecha UTC)
          </label>
          <input
            type="date"
            value={filters.startDate}
            onChange={(e) => handleChange('startDate', e.target.value)}
            className="w-full text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 text-slate-800"
          />
        </div>

        {/* Fecha Fin */}
        <div className="flex-1 min-w-[140px]">
          <label className="block text-xs font-semibold text-slate-600 mb-1">
            Hasta (Fecha UTC)
          </label>
          <input
            type="date"
            value={filters.endDate}
            onChange={(e) => handleChange('endDate', e.target.value)}
            className="w-full text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 text-slate-800"
          />
        </div>

        {/* Magnitud Mínima */}
        <div className="flex-1 min-w-[120px]">
          <label className="block text-xs font-semibold text-slate-600 mb-1">
            Magnitud Mínima
          </label>
          <select
            value={filters.minMagnitude}
            onChange={(e) => handleChange('minMagnitude', e.target.value)}
            className="w-full text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 text-slate-800"
          >
            <option value="">Todas (≥ 2.5)</option>
            <option value="3.0">≥ 3.0 (Leve)</option>
            <option value="4.0">≥ 4.0 (Moderado)</option>
            <option value="5.0">≥ 5.0 (Fuerte)</option>
            <option value="6.0">≥ 6.0 (Severo)</option>
          </select>
        </div>

        {/* Región */}
        <div className="flex-1 min-w-[150px]">
          <label className="block text-xs font-semibold text-slate-600 mb-1">
            Región Geográfica
          </label>
          <input
            type="text"
            placeholder="Ej: Alaska, Indonesia, Japan"
            value={filters.region}
            onChange={(e) => handleChange('region', e.target.value)}
            className="w-full text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 text-slate-800 placeholder:text-slate-400"
          />
        </div>

        {/* Botón Limpiar */}
        {hasActiveFilters && (
          <button
            onClick={onReset}
            className="px-3 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-lg transition flex items-center gap-1.5 h-[34px]"
            title="Restablecer todos los filtros"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
            Limpiar
          </button>
        )}
      </div>
    </div>
  );
};
