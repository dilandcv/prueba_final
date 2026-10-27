import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Chatbot } from './components/Chatbot';
import { Filters } from './components/Filters';
import { Indicators } from './components/Indicators';

import { MagnitudeChart } from './components/MagnitudeChart';
import { Navbar } from './components/Navbar';
import { RegionalRanking } from './components/RegionalRanking';
import { SeismicMap } from './components/SeismicMap';
import { StatusBanner } from './components/StatusBanner';
import { TimeSeriesChart } from './components/TimeSeriesChart';
import {
  fetchIndicators,
  fetchMagnitudeDistribution,
  fetchMapEvents,
  fetchRegionalRanking,
  fetchTimeSeries,
} from './services/api';
import {
  ConnectionStatus,
  FilterState,
  GeneralIndicators,
  MagnitudeDistributionItem,
  MapEvent,
  RegionalRankingItem,
  TimeSeriesPoint,
} from './types';

const INITIAL_FILTERS: FilterState = {
  startDate: '',
  endDate: '',
  minMagnitude: '',
  region: '',
};

export const App: React.FC = () => {
  // Filtros de búsqueda
  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);

  // Estados de datos
  const [indicators, setIndicators] = useState<GeneralIndicators | null>(null);
  const [timeSeries, setTimeSeries] = useState<TimeSeriesPoint[]>([]);
  const [magnitudeDistribution, setMagnitudeDistribution] = useState<MagnitudeDistributionItem[]>([]);
  const [regionalRanking, setRegionalRanking] = useState<RegionalRankingItem[]>([]);
  const [mapEvents, setMapEvents] = useState<MapEvent[]>([]);

  // Estados de control
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState<boolean>(false);


  // Ref para acceder a los filtros activos dentro del callback SSE sin stale closure
  const filtersRef = useRef<FilterState>(filters);
  filtersRef.current = filters;

  // Carga unificada de datos desde la API
  const loadAllData = useCallback(async (activeFilters: FilterState = filtersRef.current) => {
    setIsLoading(true);
    try {
      const [ind, ts, dist, rank, evts] = await Promise.all([
        fetchIndicators(activeFilters),
        fetchTimeSeries(activeFilters),
        fetchMagnitudeDistribution(activeFilters),
        fetchRegionalRanking(10),
        fetchMapEvents(activeFilters, 500),
      ]);

      setIndicators(ind);
      setTimeSeries(ts);
      setMagnitudeDistribution(dist);
      setRegionalRanking(rank);
      setMapEvents(evts);

      setLastUpdate(ind.last_update);
      setErrorMessage(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Error desconocido al consultar la API';
      setErrorMessage(message);
      // Nota: No vaciamos los datos existentes para preservar la visualización ante caídas transitorias
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Inicialización y conexión SSE en tiempo real
  useEffect(() => {
    // Carga inicial
    loadAllData(INITIAL_FILTERS);

    // Conexión Server-Sent Events
    let eventSource: EventSource | null = null;

    try {
      eventSource = new EventSource('/api/v1/events/sse');

      eventSource.addEventListener('connected', () => {
        setConnectionStatus('connected');
      });

      eventSource.addEventListener('data_update', (event) => {
        try {
          const payload = JSON.parse(event.data);
          // Actualizar datos automáticamente en segundo plano al llegar un nuevo lote
          loadAllData(filtersRef.current);
          if (payload.available_at) {
            setLastUpdate(payload.available_at);
          }
        } catch (e) {
          console.error('Error al parsear evento SSE:', e);
        }
      });

      eventSource.onopen = () => {
        setConnectionStatus('connected');
      };

      eventSource.onerror = () => {
        // El navegador reintenta la conexión SSE de forma automática
        setConnectionStatus('connecting');
      };
    } catch (e) {
      console.error('Error iniciando EventSource:', e);
      setConnectionStatus('disconnected');
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [loadAllData]);

  // Manejadores de interacción
  const handleFiltersChange = (newFilters: FilterState) => {
    setFilters(newFilters);
    loadAllData(newFilters);
  };

  const handleResetFilters = () => {
    setFilters(INITIAL_FILTERS);
    loadAllData(INITIAL_FILTERS);
  };

  const handleSelectRegionFromRanking = (region: string) => {
    const updated = { ...filters, region };
    setFilters(updated);
    loadAllData(updated);
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans selection:bg-sky-500 selection:text-white">
      {/* Barra de Navegación con estado SSE y botón de recarga */}
      <Navbar
        status={connectionStatus}
        lastUpdate={lastUpdate}
        onRefresh={() => loadAllData(filters)}
        isLoading={isLoading}
        onToggleChat={() => setIsChatOpen((prev) => !prev)}
        isChatOpen={isChatOpen}
      />


      {/* Banner de Estado / Notificaciones / Errores transitorios */}
      <StatusBanner status={connectionStatus} errorMessage={errorMessage} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6 flex-1 w-full">
        {/* Fila 1: Indicadores clave (KPIs de calidad y actividad sísmica) */}
        <section>
          <Indicators indicators={indicators} isLoading={isLoading} />
        </section>

        {/* Fila 2: Filtros de consulta consistentes */}
        <section>
          <Filters
            filters={filters}
            onChange={handleFiltersChange}
            onReset={handleResetFilters}
          />
        </section>

        {/* Fila 3: Mapa interactivo Leaflet y Ranking de Regiones */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-3">
            <SeismicMap events={mapEvents} isLoading={isLoading} />
          </div>
          <div className="space-y-3">
            <RegionalRanking
              data={regionalRanking}
              isLoading={isLoading}
              onSelectRegion={handleSelectRegionFromRanking}
            />
          </div>
        </section>

        {/* Fila 4: Gráficos Analíticos (Serie Temporal y Distribución por Magnitud) */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <TimeSeriesChart data={timeSeries} isLoading={isLoading} />
          <MagnitudeChart data={magnitudeDistribution} isLoading={isLoading} />
        </section>
      </main>

      {/* Pie de página */}
      <footer className="border-t border-slate-800 bg-slate-950/70 py-4 mt-8 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>Plataforma de Análisis Sísmico &bull; PySpark Medallion Architecture</span>
          <span className="font-mono text-slate-600">USGS Earthquake API &bull; PostgreSQL &bull; FastAPI</span>
        </div>
      </footer>

      {/* Botón flotante para acceso rápido al Asistente IA */}
      <button
        onClick={() => setIsChatOpen(true)}
        className="fixed bottom-6 right-6 z-40 p-3.5 bg-gradient-to-tr from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-white rounded-full shadow-lg shadow-sky-600/30 transition transform hover:scale-105 active:scale-95 focus:outline-none focus:ring-2 focus:ring-sky-400"
        title="Abrir Asistente de IA"
        aria-label="Abrir Asistente de IA"
      >
        <span className="relative flex items-center justify-center">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <span className="absolute -top-1 -right-1 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-300 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-sky-400"></span>
          </span>
        </span>
      </button>

      {/* Asistente Conversacional IA (Panel Lateral Desplegable) */}
      <Chatbot isOpen={isChatOpen} onClose={() => setIsChatOpen(false)} />
    </div>
  );
};


export default App;
