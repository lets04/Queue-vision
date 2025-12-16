import React, { useState, useEffect, useRef } from 'react';

const API_URL = 'http://192.168.0.5:8000';

// Iconos SVG
const Icons = {
  Settings: () => (
    <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="10" cy="10" r="3"></circle>
      <path d="M10.458 1.667a1.042 1.042 0 0 0-1 0L3.125 5a1.042 1.042 0 0 0-.542.917v6.166c0 .375.2.722.542.917l6.333 3.333a1.042 1.042 0 0 0 1 0L16.792 13a1.042 1.042 0 0 0 .541-.917V5.917A1.042 1.042 0 0 0 16.792 5l-6.334-3.333z"></path>
    </svg>
  ),
  Camera: () => (
    <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
      <circle cx="12" cy="13" r="4"></circle>
    </svg>
  ),
  Check: () => (
    <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
  ),
  X: () => (
    <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"></line>
      <line x1="6" y1="6" x2="18" y2="18"></line>
    </svg>
  ),
  Plus: () => (
    <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"></line>
      <line x1="5" y1="12" x2="19" y2="12"></line>
    </svg>
  )
};

const StatusIndicator = ({ label, value, color }) => (
  <div className="status-indicator">
    <div className="status-dot" style={{ background: color }}></div>
    <div className="status-content">
      <div className="status-label">{label}</div>
      <div className="status-value">{value}</div>
    </div>
  </div>
);

function AdminPanel({ onClose }) {
  const [datos, setDatos] = useState({ personas: 0, tiempo_espera_min: 0 });
  const [config, setConfig] = useState({ hora_apertura: "09:00", hora_cierre: "17:00", tiempo_atencion_min: 3 });
  const [editandoConfig, setEditandoConfig] = useState(false);
  const [guardandoConfig, setGuardandoConfig] = useState(false);
  const [mensajeConfig, setMensajeConfig] = useState('');
  const [estimado, setEstimado] = useState({});
  const [estadisticas, setEstadisticas] = useState({});
  const [camaraCounts, setCamaraCounts] = useState({ interior: 0, exterior: 0 });
  const [notificacionesHabilitadas, setNotificacionesHabilitadas] = useState(false);
  const [alertaRechazadaManual, setAlertaRechazadaManual] = useState(false);
  const lastAlertRef = useRef(false);
  const lastAlertStateRef = useRef(false);

  // Estado de alerta rechazada 
  const alertaActiva = !!estimado?.alerta_nueva_ventanilla;
  const alertaRechazada = alertaActiva && alertaRechazadaManual;

  useEffect(() => {
    const solicitarPermisoNotificaciones = async () => {
      if ("Notification" in window) {
        if (Notification.permission === "granted") {
          setNotificacionesHabilitadas(true);
        } else if (Notification.permission !== "denied") {
          const permission = await Notification.requestPermission();
          setNotificacionesHabilitadas(permission === "granted");
        }
      }
    };
    solicitarPermisoNotificaciones();
  }, []);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(`${API_URL}/estado-actual`);
        const data = await response.json();
        setDatos(data);
      } catch (error) {
        console.error('Error:', error);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchCamaras = async () => {
      try {
        const resp = await fetch(`${API_URL}/segmentos`);
        const j = await resp.json();
        const segmentos = j.segmentos || [];
        let interior = 0, exterior = 0;
        segmentos.forEach(s => {
          const cam = (s.camera_id || '').toLowerCase();
          const personas = s.personas || 0;
          if (cam.includes('inter') || cam.includes('cam_interior')) interior += personas;
          else if (cam.includes('exter') || cam.includes('cam_exterior')) exterior += personas;
        });
        setCamaraCounts({ interior, exterior });
      } catch (error) {
        console.error('Error:', error);
      }
    };
    fetchCamaras();
    const t = setInterval(fetchCamaras, 1500);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await fetch(`${API_URL}/config`);
        const data = await response.json();
        if (!editandoConfig) {
          setConfig(data.config || { hora_apertura: "09:00", hora_cierre: "17:00", tiempo_atencion_min: 3 });
        }
        setEstimado(data.estimado || {});
      } catch (error) {
        console.error('Error:', error);
      }
    };
    fetchConfig();
    const interval = setInterval(fetchConfig, 3000);
    return () => clearInterval(interval);
  }, [editandoConfig]);

  useEffect(() => {
    const fetchEstadisticas = async () => {
      try {
        const response = await fetch(`${API_URL}/estadisticas`);
        const data = await response.json();
        setEstadisticas(data || {});
      } catch (error) {
        console.error('Error:', error);
      }
    };
    fetchEstadisticas();
    const interval = setInterval(fetchEstadisticas, 5000);
    return () => clearInterval(interval);
  }, []);

  // Notificacion del navegador cuando hay alerta
  useEffect(() => {
    if (
      notificacionesHabilitadas &&
      alertaActiva &&
      !lastAlertRef.current
    ) {
      new Notification(' ALERTA: Abrir ventanilla', {
        body: `${estimado.personas_en_cola || 0} personas en cola. Capacidad insuficiente.`,
        tag: 'alerta-ventanilla',
        requireInteraction: true
      });

      try {
        const audio = new Audio('data:audio/wav;base64,...');
        audio.play().catch(() => {});
      } catch(error) {
        console.error(error);
      }

      lastAlertRef.current = true;
    }

    if (!alertaActiva) {
      lastAlertRef.current = false;
    }
  }, [alertaActiva, estimado.personas_en_cola, notificacionesHabilitadas]);

  // Alerta desaparece
  useEffect(() => {
    if (!alertaActiva && lastAlertStateRef.current) {
      lastAlertStateRef.current = false;  
    }
      lastAlertStateRef.current = alertaActiva;
    }, [alertaActiva]);


  const handleActivarSegundaVentanilla = async (activar) => {
    const personaCorte = estimado.personas_estimadas_atendidas || 0;
    
    try {
      await fetch(`${API_URL}/config/segunda-ventanilla`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ activar, persona_corte: personaCorte })
      });
      
      if (!activar) {
        setAlertaRechazadaManual(true); 
      }
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const handleConfigChange = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const handleGuardarConfig = async () => {
    setGuardandoConfig(true);
    try {
      await fetch(`${API_URL}/config/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ apertura: config.hora_apertura, cierre: config.hora_cierre })
      });
      await fetch(`${API_URL}/config/service-time`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutos: parseInt(config.tiempo_atencion_min) })
      });
      setMensajeConfig('Configuración guardada');
      setEditandoConfig(false);
      setTimeout(() => setMensajeConfig(''), 3000);
    } catch (error) {
      setMensajeConfig(`Error: ${error.message}`);
    }
    setGuardandoConfig(false);
  };

  const nivelOcupacion = () => {
    if (datos.personas === 0) return { text: 'Vacío', color: '#6b7280' };
    if (datos.personas < 5) return { text: 'Bajo', color: '#22c55e' };
    if (datos.personas < 15) return { text: 'Moderado', color: '#fbbf24' };
    return { text: 'Alto', color: '#ef4444' };
  };

  const nivel = nivelOcupacion();

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.9)', zIndex: 1000, overflowY: 'auto', padding: '2rem' }}>
      <style>{`
        .status-indicator { display: flex; align-items: center; gap: 1rem; padding: 1rem; background: #0a0a0a; borderRadius: 12px; border: 1px solid #222; }
        .status-dot { width: 12px; height: 12px; borderRadius: 50%; animation: pulse 2s ease-in-out infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .status-content { flex: 1; }
        .status-label { color: #6b7280; fontSize: 0.875rem; marginBottom: 0.25rem; }
        .status-value { color: #fff; fontSize: 1.25rem; fontWeight: 700; fontFamily: monospace; }
      `}</style>
      
      <div style={{ maxWidth: '1600px', margin: '0 auto', background: '#0a0a0a', borderRadius: '24px', border: '1px solid #222' }}>
        <div style={{ padding: '2rem 3rem', borderBottom: '1px solid #222', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'linear-gradient(135deg, #1a1a1a 0%, #0a0a0a 100%)' }}>
          <div>
            <h1 style={{ fontSize: '2rem', fontWeight: '700', color: '#fff', marginBottom: '0.5rem' }}>Panel de Administracion</h1>
            <p style={{ color: '#6b7280', fontSize: '0.9rem' }}>Sistema de Gestion de Filas en Tiempo Real</p>
            <div style={{ marginTop: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: notificacionesHabilitadas ? '#22c55e' : '#ef4444' }}>
                {notificacionesHabilitadas ? '● Notificaciones: Activas' : '● Notificaciones: Desactivadas'}
              </span>
            </div>
          </div>
          <button onClick={onClose} style={{ padding: '0.75rem 2rem', background: '#ef4444', color: 'white', border: 'none', borderRadius: '12px', cursor: 'pointer', fontWeight: '600', fontSize: '1rem' }}>Cerrar</button>
        </div>

        <div style={{ padding: '2rem 3rem' }}>
          
          {/* Alerta principal */}
          {alertaActiva && !alertaRechazada && (
            <div style={{ background: 'linear-gradient(135deg, rgba(251,191,36,0.15) 0%, rgba(239,68,68,0.15) 100%)', border: '2px solid #fbbf24', borderRadius: '16px', padding: '1.5rem 2rem', marginBottom: '2rem' }}>
              <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
                <div style={{ fontSize: '3rem' }}>⚠️</div>
                <div style={{ flex: 1 }}>
                  <h3 style={{ color: '#fbbf24', fontSize: '1.2rem', marginBottom: '0.5rem', fontWeight: '700' }}>
                    ALERTA: INSUFICIENCIA DE CAPACIDAD
                  </h3>
                  <p style={{ color: '#fff', marginBottom: '0.5rem' }}>
                    Se estiman <strong>{estimado.personas_estimadas_atendidas}</strong> personas atendidas, pero hay <strong>{estimado.personas_en_cola}</strong> en cola.
                  </p>
                  <div style={{ background: 'rgba(251,191,36,0.2)', padding: '0.5rem 1rem', borderRadius: '8px', color: '#fbbf24', fontWeight: '600', display: 'inline-block', marginBottom: '1rem' }}>
                    ¿Desea abrir una segunda ventanilla?
                  </div>
                  
                  {/* Botones Si/NO */}
                  <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
                    <button 
                      onClick={() => handleActivarSegundaVentanilla(true)}
                      style={{ 
                        padding: '0.75rem 2rem', 
                        background: '#22c55e', 
                        color: 'white', 
                        border: 'none', 
                        borderRadius: '10px', 
                        cursor: 'pointer', 
                        fontWeight: '600',
                        fontSize: '1rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem'
                      }}
                    >
                      <Icons.Check /> SI, Abrir Segunda Ventanilla
                    </button>
                    <button 
                      onClick={() => handleActivarSegundaVentanilla(false)}
                      style={{ 
                        padding: '0.75rem 2rem', 
                        background: '#6b7280', 
                        color: 'white', 
                        border: 'none', 
                        borderRadius: '10px', 
                        cursor: 'pointer', 
                        fontWeight: '600',
                        fontSize: '1rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem'
                      }}
                    >
                      <Icons.X /> NO, Continuar con una
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Notificación sutil cuando se rechaza */}
          {alertaRechazada && (
            <div style={{ 
              background: 'rgba(59,130,246,0.1)', 
              border: '1px solid #3b82f6', 
              borderRadius: '12px', 
              padding: '1rem 1.5rem', 
              marginBottom: '2rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div style={{ fontSize: '1.5rem' }}></div>
                <div>
                  <p style={{ color: '#3b82f6', fontWeight: '600', margin: 0 }}>
                    Recomendación: Considerar abrir segunda ventanilla
                  </p>
                  <p style={{ color: '#9ca3af', fontSize: '0.875rem', margin: '0.25rem 0 0 0' }}>
                    La demanda continúa siendo alta. {estimado.personas_en_cola} personas esperando.
                  </p>
                </div>
              </div>
              <button 
                onClick={() => {
                  setAlertaRechazadaManual(false);
                  handleActivarSegundaVentanilla(true);
                }}
                style={{ 
                  padding: '0.6rem 1.2rem', 
                  background: '#3b82f6', 
                  color: 'white', 
                  border: 'none', 
                  borderRadius: '8px', 
                  cursor: 'pointer', 
                  fontWeight: '600',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem'
                }}
              >
                <Icons.Plus /> Abrir Ahora
              </button>
            </div>
          )}

          <div style={{ background: '#111', border: '1px solid #222', borderRadius: '16px', padding: '2rem', marginBottom: '2rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <h2 style={{ color: '#fff', fontSize: '1.25rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Icons.Settings /> Configuración de Ventanilla
              </h2>
              {!editandoConfig ? (
                <button onClick={() => setEditandoConfig(true)} style={{ padding: '0.6rem 1.5rem', background: '#3b82f6', color: 'white', border: 'none', borderRadius: '10px', cursor: 'pointer', fontWeight: '600' }}>Editar</button>
              ) : (
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button onClick={handleGuardarConfig} disabled={guardandoConfig} style={{ padding: '0.6rem 1.5rem', background: '#22c55e', color: 'white', border: 'none', borderRadius: '10px', cursor: 'pointer', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Icons.Check /> {guardandoConfig ? 'Guardando...' : 'Guardar'}
                  </button>
                  <button onClick={() => setEditandoConfig(false)} style={{ padding: '0.6rem 1.5rem', background: '#6b7280', color: 'white', border: 'none', borderRadius: '10px', cursor: 'pointer', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Icons.X /> Cancelar
                  </button>
                </div>
              )}
            </div>

            {mensajeConfig && (
              <div style={{ padding: '0.75rem 1rem', borderRadius: '10px', marginBottom: '1rem', background: mensajeConfig.includes('guardada') ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', border: `1px solid ${mensajeConfig.includes('guardada') ? '#22c55e' : '#ef4444'}`, color: mensajeConfig.includes('guardada') ? '#22c55e' : '#ef4444', fontWeight: '500' }}>
                {mensajeConfig}
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '2rem' }}>
              {['hora_apertura', 'hora_cierre', 'tiempo_atencion_min'].map((field, idx) => (
                <div key={field}>
                  <label style={{ color: '#9ca3af', fontSize: '0.875rem', fontWeight: '600', display: 'block', marginBottom: '0.5rem' }}>
                    {field === 'hora_apertura' ? 'Hora de Apertura' : field === 'hora_cierre' ? 'Hora de Cierre' : 'Tiempo de Atención (min)'}
                  </label>
                  <input type={idx < 2 ? 'time' : 'number'} value={config[field]} onChange={(e) => handleConfigChange(field, idx < 2 ? e.target.value : parseInt(e.target.value))} disabled={!editandoConfig} style={{ width: '100%', padding: '0.75rem 1rem', background: editandoConfig ? '#1a1a1a' : '#0a0a0a', border: `1px solid ${editandoConfig ? '#3b82f6' : '#333'}`, borderRadius: '10px', color: '#fff', fontSize: '1rem', fontFamily: 'monospace' }} />
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
            <div style={{ background: '#111', border: '1px solid #222', borderRadius: '16px', padding: '2rem' }}>
              <h2 style={{ color: '#fff', fontSize: '1.25rem', marginBottom: '1.5rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Icons.Camera /> Monitoreo por Camara
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <StatusIndicator label="Cámara Interior" value={`${camaraCounts.interior} personas`} color="#22c55e" />
                <StatusIndicator label="Cámara Exterior" value={`${camaraCounts.exterior} personas`} color="#3b82f6" />
                <StatusIndicator label="Personas en Fila" value={datos.personas} color="#8b5cf6" />
              </div>
            </div>

            <div style={{ background: '#111', border: '1px solid #222', borderRadius: '16px', padding: '2rem' }}>
              <h2 style={{ color: '#fff', fontSize: '1.25rem', marginBottom: '1.5rem', fontWeight: '600' }}>Capacidad Estimada</h2>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                <div style={{ background: '#0a0a0a', padding: '1.5rem', borderRadius: '12px', textAlign: 'center' }}>
                  <div style={{ color: '#6b7280', fontSize: '0.875rem', marginBottom: '0.5rem' }}>Minutos al Cierre</div>
                  <div style={{ color: '#fff', fontSize: '2.5rem', fontWeight: '700', fontFamily: 'monospace' }}>{Math.floor(estimado.minutos_hasta_cierre || 0)}</div>
                </div>
                <div style={{ background: '#0a0a0a', padding: '1.5rem', borderRadius: '12px', textAlign: 'center' }}>
                  <div style={{ color: '#6b7280', fontSize: '0.875rem', marginBottom: '0.5rem' }}>Estimado Atendidas</div>
                  <div style={{ color: '#fff', fontSize: '2.5rem', fontWeight: '700', fontFamily: 'monospace' }}>{estimado.personas_estimadas_atendidas || 0}</div>
                </div>
                <div style={{ background: '#0a0a0a', padding: '1.5rem', borderRadius: '12px', textAlign: 'center' }}>
                  <div style={{ color: '#6b7280', fontSize: '0.875rem', marginBottom: '0.5rem' }}>Tiempo de Espera</div>
                  <div style={{ color: '#fff', fontSize: '2.5rem', fontWeight: '700', fontFamily: 'monospace' }}>{datos.tiempo_espera_min} min</div>
                </div>
                <div style={{ background: '#0a0a0a', padding: '1.5rem', borderRadius: '12px', textAlign: 'center' }}>
                  <div style={{ color: '#6b7280', fontSize: '0.875rem', marginBottom: '0.5rem' }}>Nivel Ocupacion</div>
                  <div style={{ color: nivel.color, fontSize: '2rem', fontWeight: '700', fontFamily: 'monospace' }}>{nivel.text}</div>
                </div>
              </div>
            </div>
          </div>

          <div style={{ background: '#111', border: '1px solid #222', borderRadius: '16px', padding: '2rem' }}>
            <h2 style={{ color: '#fff', fontSize: '1.25rem', marginBottom: '1.5rem', fontWeight: '600' }}>Estadisticas de Atencion</h2>
            {estadisticas.estado_ventanilla === 'ABIERTA' ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#3b82f6' }}>
                <p style={{ fontSize: '1.1rem', fontWeight: '600' }}>Ventanilla Abierta</p>
                <small style={{ color: '#6b7280' }}>Estadisticas disponibles después del cierre</small>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.5rem' }}>
                {[
                  { label: 'Personas Atendidas', value: estadisticas.personas_atendidas || 0 },
                  { label: 'Tiempo Promedio', value: `${Math.round(estadisticas.tiempo_promedio_espera || 0)} min` },
                  { label: 'Pico Máximo', value: `${estadisticas.pico_fila || 0} personas` },
                  { label: 'Estado', value: estadisticas.estado_ventanilla || 'N/A' }
                ].map((stat, idx) => (
                  <div key={idx} style={{ background: '#0a0a0a', padding: '1.5rem', borderRadius: '12px', textAlign: 'center' }}>
                    <div style={{ color: '#6b7280', fontSize: '0.875rem', marginBottom: '0.5rem' }}>{stat.label}</div>
                    <div style={{ color: '#fff', fontSize: '1.5rem', fontWeight: '700', fontFamily: 'monospace' }}>{stat.value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default AdminPanel;