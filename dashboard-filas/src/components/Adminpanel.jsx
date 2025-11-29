// PANEL DE ADMINISTRACIÓN 

import React, { useState, useEffect, useRef } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './AdminPanel.css';

const API_URL = 'http://127.0.0.1:8000';

// COMPONENTE: TARJETA MÉTRICA

const MetricCard = ({ title, value, unit, color }) => (
    <div className={`metric-card ${color}`}>
    <div className="metric-header">
        <span className="metric-title">{title}</span>
    </div>
    <div className="metric-value">
        {value}
        {unit && <span className="metric-unit">{unit}</span>}
    </div>
    </div>
);

// COMPONENTE: ALERTA
const Alert = ({ type, message }) => (
    <div className={`alert alert-${type}`}>
    <span>{message}</span>
    </div>
);

// PANEL DE ADMINISTRACIÓN
function AdminPanel({ onClose }) {
    const [datos, setDatos] = useState({
    personas: 0,
    tiempo_espera_min: 0,
    alerta: false,
    en_entrada: 0,
    en_preventanilla: 0,
    ids_activos: 0,
    max_fila: 0
    });

    const [config, setConfig] = useState({
    hora_apertura: "09:00",
    hora_cierre: "17:00",
    tiempo_atencion_min: 3
    });

    const [editandoConfig, setEditandoConfig] = useState(false);
    const [guardandoConfig, setGuardandoConfig] = useState(false);
    const [mensajeConfig, setMensajeConfig] = useState('');
    const [estimado, setEstimado] = useState({});
    const [estadisticas, setEstadisticas] = useState({});
    const [historico, setHistorico] = useState([]);
    const [camaraCounts, setCamaraCounts] = useState({ interior: 0, exterior: 0 });
    const lastAlertRef = useRef(false);

  // Obtener datos
    useEffect(() => {
    const fetchData = async () => {
        try {
        const response = await fetch(`${API_URL}/estado-actual`);
        const data = await response.json();
        setDatos(data);
        
        setHistorico(prev => {
            const nuevo = [...prev, {
            tiempo: new Date().toLocaleTimeString(),
            personas: data.personas,
            tiempo_espera: data.tiempo_espera_min
            }];
            return nuevo.slice(-20);
        });
        } catch (error) {
        console.error('Error:', error);
        }
    };
    fetchData();
    const interval = setInterval(fetchData, 1000);
    return () => clearInterval(interval);
    }, []);

    // Obtener conteos por cámara (interior/exterior) desde /segmentos
    useEffect(() => {
    const fetchCamaras = async () => {
        try {
        const resp = await fetch(`${API_URL}/segmentos`);
        const j = await resp.json();
        const segmentos = j.segmentos || [];

        let interior = 0;
        let exterior = 0;

        segmentos.forEach(s => {
            const cam = (s.camera_id || '').toLowerCase();
            const personas = s.personas || 0;
            if (cam.includes('inter') || cam.includes('cam_interior')) interior += personas;
            else if (cam.includes('exter') || cam.includes('cam_exterior')) exterior += personas;
        });

        setCamaraCounts({ interior, exterior });
        } catch (error) {
        console.error('Error al obtener segmentos:', error);
        }
    };
    fetchCamaras();
    const t = setInterval(fetchCamaras, 1500);
    return () => clearInterval(t);
    }, []);

  // Obtener configuración
    useEffect(() => {
    const fetchConfig = async () => {
        try {
        const response = await fetch(`${API_URL}/config`);
        const data = await response.json();
        if (!editandoConfig) {
            setConfig(data.config || config);
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

    // Notificaciones cuando el estimado indique abrir nueva ventanilla
    useEffect(() => {
    if (!estimado) return;

    const alerta = !!estimado.alerta_nueva_ventanilla;

    if (alerta && !lastAlertRef.current) {
        // Notificación del navegador
        try {
        if ("Notification" in window) {
            if (Notification.permission === 'granted') {
            new Notification('ALERTA: Abrir ventanilla', {
                body: `Se estiman ${estimado.personas_estimadas_atendidas || 0} atendidas, pero hay ${estimado.personas_en_cola || 0} en cola.`
            });
            } else if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(p => {
                if (p === 'granted') {
                new Notification('ALERTA: Abrir ventanilla', {
                    body: `Se estiman ${estimado.personas_estimadas_atendidas || 0} atendidas, pero hay ${estimado.personas_en_cola || 0} en cola.`
                });
                }
            });
            }
        }
        } catch (e) {
        console.error('Notification error', e);
        }

        // Beep corto con WebAudio
        try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
            const ctx = new AudioCtx();
            const o = ctx.createOscillator();
            const g = ctx.createGain();
            o.type = 'sine';
            o.frequency.value = 880;
            o.connect(g);
            g.connect(ctx.destination);
            g.gain.value = 0.0001;
            o.start();
            g.gain.exponentialRampToValueAtTime(0.1, ctx.currentTime + 0.02);
            setTimeout(() => {
            g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.12);
            o.stop(ctx.currentTime + 0.13);
            try { ctx.close(); } catch { /* ignore close error */ }
            }, 120);
        }
        } catch {
        // ignore
        }

        lastAlertRef.current = true;
    }

    if (!alerta) {
        lastAlertRef.current = false;
    }
    }, [estimado]);

  // Obtener estadísticas
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

    const handleConfigChange = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
    };

    const handleGuardarConfig = async () => {
    setGuardandoConfig(true);
    
    try {
        const resp1 = await fetch(`${API_URL}/config/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            apertura: config.hora_apertura,
            cierre: config.hora_cierre
        })
        });
        
        const data1 = await resp1.json();
        
        const resp2 = await fetch(`${API_URL}/config/service-time`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            minutos: parseInt(config.tiempo_atencion_min)
        })
        });
        
        const data2 = await resp2.json();
        
        if (resp1.ok && resp2.ok) {
        setMensajeConfig('Configuración guardada correctamente');
        setEditandoConfig(false);
        setTimeout(() => setMensajeConfig(''), 3000);
        } else {
        setMensajeConfig(`Error: ${data1.message || data2.message}`);
        setTimeout(() => setMensajeConfig(''), 5000);
        }
    } catch (error) {
        setMensajeConfig(`Error de conexión: ${error.message}`);
        setTimeout(() => setMensajeConfig(''), 5000);
    }
    setGuardandoConfig(false);
    };

    const handleCancelarConfig = async () => {
    setEditandoConfig(false);
    try {
        const response = await fetch(`${API_URL}/config`);
        const data = await response.json();
        if (data.config) setConfig(data.config);
    } catch (error) {
        console.error('Error:', error);
    }
    };

    const nivelOcupacion = () => {
    if (datos.personas === 0) return 'Vacío';
    if (datos.personas < 5) return 'Bajo';
    if (datos.personas < 15) return 'Moderado';
    return 'Alto';
    };

    const estadoSemaforo = () => {
    if (datos.tiempo_espera_min < 30) return 'verde';
    if (datos.tiempo_espera_min < 90) return 'amarillo';
    return 'rojo';
    };

    return (
    <div className="admin-overlay">
        <div className="admin-panel">
        
        {/* Header */}
        <div className="admin-header">
            <h1>Panel de Administración</h1>
            <button className="close-button" onClick={onClose}>Cerrar</button>
        </div>

        <div className="admin-content">
            
          {/* Alertas */}
            <div className="alerts-section">
            {estimado.alerta_nueva_ventanilla && (
                <div className="alert-ventanilla active">
                <h4>ALERTA: INSUFICIENCIA DE VENTANILLAS</h4>
                <p>
                    Se puede atender aproximadamente <strong>{estimado.personas_estimadas_atendidas}</strong> personas,
                    pero hay <strong>{estimado.personas_en_cola}</strong> en cola.
                </p>
                <div className="recomendacion">
                    Se recomienda abrir una ventanilla adicional
                </div>
                </div>
            )}
            {datos.alerta ? (
                <Alert type="danger" message="ALTA DEMANDA: Se recomienda habilitar ventanilla adicional" />
            ) : (
                <Alert type="success" message="Flujo Normal: Tiempo de espera aceptable" />
            )}
            </div>

          {/* Panel de Configuración */}
            <div className="config-panel">
            <div className="config-header">
                <h3>Configuración de Ventanilla</h3>
                {!editandoConfig ? (
                <button className="config-button" onClick={() => setEditandoConfig(true)}>
                    Editar
                </button>
                ) : (
                <div className="config-actions">
                    <button 
                    className="config-button config-button-success" 
                    onClick={handleGuardarConfig}
                    disabled={guardandoConfig}
                    >
                    {guardandoConfig ? 'Guardando...' : 'Guardar'}
                    </button>
                    <button 
                    className="config-button config-button-cancel" 
                    onClick={handleCancelarConfig}
                    disabled={guardandoConfig}
                    >
                    Cancelar
                    </button>
                </div>
                )}
            </div>

            {mensajeConfig && (
                <div className={`config-mensaje ${mensajeConfig.includes('correctamente') ? 'success' : 'error'}`}>
                {mensajeConfig}
                </div>
            )}

            <div className="config-grid">
                <div className="config-item">
                <label>Hora de Apertura</label>
                <input
                    type="time"
                    value={config.hora_apertura}
                    onChange={(e) => handleConfigChange('hora_apertura', e.target.value)}
                    disabled={!editandoConfig}
                    className={editandoConfig ? 'editing' : ''}
                />
                </div>
                <div className="config-item">
                <label>Hora de Cierre</label>
                <input
                    type="time"
                    value={config.hora_cierre}
                    onChange={(e) => handleConfigChange('hora_cierre', e.target.value)}
                    disabled={!editandoConfig}
                    className={editandoConfig ? 'editing' : ''}
                />
                </div>
                <div className="config-item">
                <label>Tiempo de Atención (minutos)</label>
                <input
                    type="number"
                    min="1"
                    max="30"
                    value={config.tiempo_atencion_min}
                    onChange={(e) => handleConfigChange('tiempo_atencion_min', parseInt(e.target.value))}
                    disabled={!editandoConfig}
                    className={editandoConfig ? 'editing' : ''}
                />
                </div>
            </div>
            </div>

          {/* Estimados */}
            <div className="estimado-section">
            <h2 className="section-title">Estimado de Capacidad</h2>
            <div className="estimado-grid-2">
                <div className="estimado-item">
                <div className="label">Minutos Hasta Cierre</div>
                <div className="value">{Math.floor(estimado.minutos_hasta_cierre || 0)}</div>
                </div>
                <div className="estimado-item">
                <div className="label">Estimado Atendidas</div>
                <div className="value">{estimado.personas_estimadas_atendidas || 0}</div>
                </div>
            </div>
            </div>

          {/* Métricas */}
            <div className="metrics-grid">
            <MetricCard title="Personas en Fila" value={datos.personas} color="blue" />
            <MetricCard title="Tiempo Estimado" value={datos.tiempo_espera_min} unit="min" color="purple" />
            <MetricCard title="Nivel de Ocupación" value={nivelOcupacion()} color={estadoSemaforo()} />
            <MetricCard title="Máximo del Día" value={datos.max_fila || 0} color="orange" />
            </div>

          {/* Métricas Secundarias */}
            <div className="secondary-metrics">
            <div className="metric-item">
                <span className="label">Interior:</span>
                <span className="value">{camaraCounts.interior || 0}</span>
            </div>
            <div className="metric-item">
                <span className="label">Exterior:</span>
                <span className="value">{camaraCounts.exterior || 0}</span>
            </div>
            <div className="metric-item">
                <span className="label">IDs Rastreados:</span>
                <span className="value">{datos.ids_activos || 0}</span>
            </div>
            </div>

          {/* Gráfico */}
            <div className="chart-section">
            <h2 className="section-title">Tendencia en Tiempo Real</h2>
            <ResponsiveContainer width="100%" height={300}>
                <LineChart data={historico}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="tiempo" stroke="#999" />
                <YAxis stroke="#999" />
                <Tooltip contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }} />
                <Legend />
                <Line type="monotone" dataKey="personas" stroke="#3b82f6" strokeWidth={2} name="Personas en Fila" />
                <Line type="monotone" dataKey="tiempo_espera" stroke="#8b5cf6" strokeWidth={2} name="Tiempo de Espera (min)" />
                </LineChart>
            </ResponsiveContainer>
            </div>

          {/* Estadísticas */}
            <div className="info-section">
            <div className="info-card">
                <h3>Estadísticas de Atención</h3>
                {estadisticas.estado_ventanilla === 'ABIERTA' ? (
                <div className="stats-open">
                    <p>Ventanilla abierta</p>
                    <small>Estadísticas disponibles después del cierre</small>
                </div>
                ) : (
                <ul className="stats-list">
                    <li>Personas atendidas: <strong>{estadisticas.personas_atendidas || 0}</strong></li>
                    <li>Tiempo promedio: <strong>{Math.round(estadisticas.tiempo_promedio_espera || 0)} min</strong></li>
                    <li>Personas que entraron: <strong>{estadisticas.personas_entrada || 0}</strong></li>
                    <li>Pico máximo: <strong>{estadisticas.pico_fila || 0} personas</strong></li>
                    <li>Velocidad: <strong>{estadisticas.velocidad_atencion || 0} personas/hora</strong></li>
                </ul>
                )}
            </div>
            </div>

        </div>
        </div>
    </div>
    );
}

export default AdminPanel;