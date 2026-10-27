import React, { useCallback, useEffect, useRef, useState } from 'react';
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

      setLastUpdate(ind.last_update || new Date().toISOString());
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
    </div>
  );
};

export default App;
