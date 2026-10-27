import React, { useEffect, useRef, useState } from 'react';
import { sendChatMessage } from '../services/api';
import { ChatMessage } from '../types';

interface ChatbotProps {
  isOpen: boolean;
  onClose: () => void;
}

const SUGGESTED_QUESTIONS = [
  '¿Cuántos sismos se han registrado en las últimas 24 horas?',
  '¿Cuál ha sido el sismo de mayor magnitud?',
  '¿Qué regiones presentan mayor actividad sísmica?',
  '¿Se han detectado anomalías en la actividad reciente?',
  '¿Cuál es el estado actual de la calidad de los datos?',
  'Genera un resumen de la actividad sísmica reciente',
];

const INITIAL_WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content: `¡Hola! Soy el **Asistente Inteligente** de la Plataforma de Análisis Sísmico.

Puedo ayudarte a consultar y comprender la información analítica consolidada en la capa **Gold**:
- Estadísticas de actividad de las últimas 24 horas y eventos destacados.
- Concentración y ranking de regiones sísmicas activas.
- Detección de anomalías estadísticas de frecuencia (Z-Score).
- Métricas de calidad y gobernanza de datos.

*Nota técnica: Todas las cifras proceden directamente de PostgreSQL Gold. Este asistente tiene fines exclusivamente observacionales y no realiza predicciones ni pronósticos de terremotos.*`,
  timestamp: new Date().toISOString(),
  model_name: 'llama3.2:1b',
};

// Formateador simple de Markdown para listas, negritas y encabezados sin librerías pesadas
const formatMarkdown = (text: string) => {
  return text.split('\n').map((line, idx) => {
    // Encabezados
    if (line.startsWith('### ')) {
      return (
        <h4 key={idx} className="text-sm font-semibold text-sky-400 mt-2 mb-1">
          {line.replace('### ', '')}
        </h4>
      );
    }
    if (line.startsWith('## ')) {
      return (
        <h3 key={idx} className="text-base font-bold text-sky-300 mt-3 mb-1.5 border-b border-slate-700/50 pb-0.5">
          {line.replace('## ', '')}
        </h3>
      );
    }
    if (line.startsWith('# ')) {
      return (
        <h2 key={idx} className="text-lg font-bold text-white mt-3 mb-2">
          {line.replace('# ', '')}
        </h2>
      );
    }

    // Viñetas / Listas
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      const content = line.trim().substring(2);
      return (
        <li key={idx} className="ml-4 list-disc text-slate-200 my-0.5">
          {renderFormattedInline(content)}
        </li>
      );
    }

    // Líneas vacías
    if (!line.trim()) {
      return <div key={idx} className="h-2" />;
    }

    // Texto estándar
    return (
      <p key={idx} className="text-slate-200 leading-relaxed my-1">
        {renderFormattedInline(line)}
      </p>
    );
  });
};

// Renderiza negritas (**texto**) y cursivas (*texto*) de forma segura
const renderFormattedInline = (text: string) => {
  const parts = text.split(/(\*\*.*?\*\*|\*.*?\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={i} className="font-semibold text-sky-200">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('*') && part.endsWith('*')) {
      return (
        <em key={i} className="italic text-slate-400">
          {part.slice(1, -1)}
        </em>
      );
    }
    return part;
  });
};

export const Chatbot: React.FC<ChatbotProps> = ({ isOpen, onClose }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([INITIAL_WELCOME_MESSAGE]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll hacia el último mensaje
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
      // Enfocar input al abrir
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen, messages, isLoading]);

  // Manejo de tecla ESC para cerrar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Envío del mensaje
  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || inputText).trim();
    if (!query || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setErrorMessage(null);
    setLastFailedMessage(null);
    setIsLoading(true);

    try {
      // Filtrar historial para no enviar el mensaje de bienvenida y limitar a los últimos 6 mensajes
      const historyPayload = messages
        .filter((m) => m.id !== 'welcome')
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));

      const res = await sendChatMessage(query, historyPayload);

      const agentMsg: ChatMessage = {
        id: `agent-${Date.now()}`,
        role: 'assistant',
        content: res.response,
        timestamp: res.timestamp,
        model_name: res.model_name,
        used_fallback: res.used_fallback,
      };

      setMessages((prev) => [...prev, agentMsg]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error desconocido al comunicar con el backend';
      setErrorMessage(msg);
      setLastFailedMessage(query);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    if (lastFailedMessage) {
      handleSendMessage(lastFailedMessage);
    }
  };

  const handleClearHistory = () => {
    setMessages([INITIAL_WELCOME_MESSAGE]);
    setErrorMessage(null);
    setLastFailedMessage(null);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
      {/* Backdrop semi-transparente */}
      <div
        className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel lateral deslizante (Drawer) */}
      <section
        className="relative w-full max-w-lg bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col h-full z-10 animate-slide-left text-slate-100"
        role="dialog"
        aria-modal="true"
        aria-label="Asistente de IA para análisis sísmico"
      >
        {/* Cabecera del Chatbot */}
        <header className="px-5 py-4 bg-slate-950/90 border-b border-slate-800 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-600 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-sky-500/20">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                />
              </svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-sm text-white">Asistente Sísmico IA</h3>
                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-sky-950 text-sky-300 border border-sky-800">
                  Gold &bull; Ollama
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">Consultas fundamentadas en datos reales</p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {messages.length > 1 && (
              <button
                onClick={handleClearHistory}
                className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition text-xs"
                title="Reiniciar conversación"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
              aria-label="Cerrar asistente"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </header>

        {/* Área de mensajes con scroll independiente */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.map((msg) => {
            const isUser = msg.role === 'user';
            return (
              <div
                key={msg.id}
                className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`max-w-[88%] sm:max-w-[82%] px-4 py-3 rounded-2xl text-sm shadow-sm ${
                    isUser
                      ? 'bg-sky-600 text-white rounded-tr-none'
                      : 'bg-slate-800/90 text-slate-100 border border-slate-700/60 rounded-tl-none'
                  }`}
                >
                  {isUser ? (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <div className="prose prose-invert prose-sm max-w-none">
                      {formatMarkdown(msg.content)}
                    </div>
                  )}
                </div>

                {/* Pie del mensaje con modelo / fallback / hora */}
                <div className="flex items-center gap-2 mt-1 px-1 text-[10px] text-slate-500">
                  <span>
                    {new Date(msg.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                  {!isUser && msg.model_name && (
                    <span className="font-mono text-slate-400">
                      &bull; {msg.used_fallback ? 'Respaldo determinista' : msg.model_name}
                    </span>
                  )}
                </div>
              </div>
            );
          })}

          {/* Indicador de procesamiento / pensamiento del agente */}
          {isLoading && (
            <div className="flex flex-col items-start">
              <div className="bg-slate-800/90 border border-slate-700/60 rounded-2xl rounded-tl-none px-4 py-3 text-sm text-slate-300 flex items-center gap-3">
                <span className="flex h-2.5 w-2.5 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-sky-500"></span>
                </span>
                <span className="text-xs font-medium text-slate-400">
                  Consultando datos en Gold y procesando respuesta...
                </span>
              </div>
            </div>
          )}

          {/* Banner de error si falla la petición */}
          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-200 text-xs flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-rose-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{errorMessage}</span>
              </div>
              {lastFailedMessage && (
                <button
                  onClick={handleRetry}
                  className="px-2.5 py-1 bg-rose-800 hover:bg-rose-700 text-white rounded-lg text-xs font-medium transition flex-shrink-0"
                >
                  Reintentar
                </button>
              )}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Preguntas sugeridas para arranque rápido */}
        {messages.length <= 2 && !isLoading && (
          <div className="px-4 py-2 border-t border-slate-800/60 bg-slate-950/40">
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Preguntas sugeridas:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTED_QUESTIONS.map((question, i) => (
                <button
                  key={i}
                  onClick={() => handleSendMessage(question)}
                  className="text-left text-xs bg-slate-800/80 hover:bg-slate-700 text-slate-200 hover:text-white px-2.5 py-1.5 rounded-lg border border-slate-700/60 transition"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Formulario de entrada de texto */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendMessage();
          }}
          className="p-3 bg-slate-950/90 border-t border-slate-800 flex items-center gap-2"
        >
          <input
            ref={inputRef}
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Pregunta sobre sismos, magnitudes, anomalías..."
            disabled={isLoading}
            className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-transparent transition disabled:opacity-50"
          />

          <button
            type="submit"
            disabled={isLoading || !inputText.trim()}
            className="p-2.5 bg-sky-600 hover:bg-sky-500 text-white rounded-xl transition shadow-md shadow-sky-600/20 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
            title="Enviar mensaje"
            aria-label="Enviar mensaje"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </button>
        </form>
      </section>
    </div>
  );
};
