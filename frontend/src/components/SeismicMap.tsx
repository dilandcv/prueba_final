import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { MapEvent } from '../types';

interface SeismicMapProps {
  events: MapEvent[];
  isLoading: boolean;
}

export const SeismicMap: React.FC<SeismicMapProps> = ({ events, isLoading }) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const layerGroupRef = useRef<L.LayerGroup | null>(null);

  // Inicialización única del mapa Leaflet
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: [20, 0],
      zoom: 2,
      minZoom: 1.5,
      maxZoom: 14,
      worldCopyJump: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    const layerGroup = L.layerGroup().addTo(map);
    mapInstanceRef.current = map;
    layerGroupRef.current = layerGroup;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Actualización de marcadores al cambiar los eventos
  useEffect(() => {
    if (!mapInstanceRef.current || !layerGroupRef.current) return;

    layerGroupRef.current.clearLayers();

    const getColor = (mag: number): string => {
      if (mag >= 6.0) return '#ef4444'; // Rojo (Severo)
      if (mag >= 4.5) return '#f97316'; // Naranja (Fuerte)
      if (mag >= 3.0) return '#f59e0b'; // Ámbar (Moderado)
      return '#10b981'; // Esmeralda (Leve)
    };

    events.forEach((ev) => {
      const radius = Math.max(4, Math.min(18, (ev.magnitude - 1.5) * 3));
      const color = getColor(ev.magnitude);

      const marker = L.circleMarker([ev.latitude, ev.longitude], {
        radius,
        fillColor: color,
        color: '#ffffff',
        weight: 1.5,
        opacity: 0.9,
        fillOpacity: 0.75,
      });

      const dateStr = new Date(ev.time_utc).toLocaleString('es-ES', {
        timeZone: 'UTC',
        dateStyle: 'short',
        timeStyle: 'medium',
      });

      const popupContent = `
        <div class="p-1 font-sans text-xs">
          <div class="flex items-center gap-2 mb-1.5 border-b pb-1">
            <span style="background-color: ${color}; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold;">
              M ${ev.magnitude.toFixed(1)}
            </span>
            <strong style="color: #0f172a;">${ev.region}</strong>
          </div>
          <p style="margin: 2px 0; color: #334155;"><strong>Lugar:</strong> ${ev.place}</p>
          <p style="margin: 2px 0; color: #334155;"><strong>Fecha:</strong> ${dateStr} UTC</p>
          <p style="margin: 2px 0; color: #334155;"><strong>Profundidad:</strong> ${ev.depth_km !== null ? ev.depth_km.toFixed(1) + ' km' : 'N/A'}</p>
          ${
            ev.tsunami_alert
              ? '<p style="margin: 4px 0 0 0; color: #e11d48; font-weight: bold;">⚠️ Alerta de Tsunami Emitida</p>'
              : ''
          }
        </div>
      `;

      marker.bindPopup(popupContent);
      layerGroupRef.current?.addLayer(marker);
    });
  }, [events]);

  return (
    <div className="bg-white rounded-xl border border-slate-200/80 shadow-sm p-4 flex flex-col h-[480px]">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-sm font-bold text-slate-900">Mapa Global de Sismicidad</h2>
          <p className="text-xs text-slate-500">
            {events.length} sismos mostrados &bull; Tamaño y color proporcionales a la magnitud
          </p>
        </div>

        {/* Leyenda de colores */}
        <div className="hidden sm:flex items-center gap-3 text-[11px] text-slate-600">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> &lt; 3.0
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span> 3.0 - 4.4
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-orange-500"></span> 4.5 - 5.9
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span> &ge; 6.0
          </span>
        </div>
      </div>

      <div className="relative flex-1 w-full rounded-lg overflow-hidden border border-slate-200">
        <div ref={mapContainerRef} className="w-full h-full" />
        {isLoading && events.length === 0 && (
          <div className="absolute inset-0 bg-white/70 backdrop-blur-sm z-20 flex items-center justify-center">
            <div className="flex items-center gap-2 text-xs font-medium text-slate-600">
              <svg className="w-4 h-4 text-sky-600 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
              </svg>
              Cargando coordenadas...
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
