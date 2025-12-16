import React, { useState, useEffect } from 'react';
import AdminPanel from './components/AdminPanel';
import './App.css';

const API_URL = 'http://192.168.0.17:8000';
const UPDATE_INTERVAL = 1000;

// 2 CÁMARAS FIJAS
const CAMARAS_FIJAS = [
  { camera_id: 'cam_interior', title: 'Cámara Interior' },
  { camera_id: 'cam_exterior', title: 'Cámara Exterior' }
];

// COMPONENTE: VISTA DE CÁMARA
const CameraView = ({ cameraId, title }) => {
  const [cameraOnline, setCameraOnline] = useState(false);
  const [imageKey, setImageKey] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => {
      setImageKey(Date.now());
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="camera-container">
      <div className="camera-header">
        <h3>{title}</h3>
        <span className={`camera-status ${cameraOnline ? 'online' : 'offline'}`}>
          {cameraOnline ? 'En línea' : 'Offline'}
        </span>
      </div>
      <div className="camera-frame">
        <img
          src={`${API_URL}/stream/${cameraId}.mjpg?t=${imageKey}`}
          alt={`Stream ${title}`}
          onLoad={() => setCameraOnline(true)}
          onError={() => setCameraOnline(false)}
          style={{
            width: '100%',
            height: 'auto',
            borderRadius: '8px',
            backgroundColor: '#000'
          }}
        />
      </div>
      <p className="camera-info">ID: {cameraId}</p>
    </div>
  );
};

// COMPONENTE PRINCIPAL: VISTA CLIENTE
function App() {
  const [setDatos] = useState({
    personas: 0,
    tiempo_espera_min: 0,
    alerta: false,
    en_entrada: 0,
    en_preventanilla: 0,
    ids_activos: 0,
    max_fila: 0
  });

  const [ultimaActualizacion, setUltimaActualizacion] = useState(null);
  const [conectado, setConectado] = useState(false);
  const [config, setConfig] = useState({
    hora_apertura: "09:00",
    hora_cierre: "17:00",
    segunda_ventanilla_activa: false,
    persona_corte_segunda_ventanilla: 0
  });
  const [estimado, setEstimado] = useState({});
  const [mostrarAdmin, setMostrarAdmin] = useState(false);
  const [ranking, setRanking] = useState([]);

  // Obtener datos
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(`${API_URL}/estado-actual`);
        const data = await response.json();
        setDatos(data);
        setUltimaActualizacion(new Date());
        setConectado(true);
      } catch (error) {
        console.error('Error al obtener datos:', error);
        setConectado(false);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, UPDATE_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  // Obtener configuración
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await fetch(`${API_URL}/config`);
        const data = await response.json();
        setConfig({
          hora_apertura: data.config?.hora_apertura || "09:00",
          hora_cierre: data.config?.hora_cierre || "17:00",
          segunda_ventanilla_activa: data.config?.segunda_ventanilla_activa || false,
          persona_corte_segunda_ventanilla: data.config?.persona_corte_segunda_ventanilla || 0
        });
        setEstimado(data.estimado || {});
      } catch (error) {
        console.error('Error al obtener configuracion:', error);
      }
    };
    fetchConfig();
    const interval = setInterval(fetchConfig, 3000);
    return () => clearInterval(interval);
  }, []);

  // Obtener ranking de personas en fila
  useEffect(() => {
    const fetchRanking = async () => {
      try {
        const response = await fetch(`${API_URL}/queue-ranking`);
        const data = await response.json();
        setRanking(data.personas || []);
      } catch (error) {
        console.error('Error al obtener ranking:', error);
      }
    };
    fetchRanking();
    const interval = setInterval(fetchRanking, 2000);
    return () => clearInterval(interval);
  }, []);

  const personaDesdeSegundaVentanilla = config.persona_corte_segunda_ventanilla + 1;

  return (
    <>
      <div className="app">
        {/* Header */}
        <header className="header">
          <div className="header-content">
            <div className="header-left">
              <h1>Monitor de Filas - Ventanilla</h1>
              <p className="subtitle">Seguro Social - Tiempo Real</p>
            </div>
            <div className="header-right">
              <button 
                className="admin-button"
                onClick={() => setMostrarAdmin(true)}
              >
                Panel Admin
              </button>
              <div className={`status-indicator ${conectado ? 'online' : 'offline'}`}>
                <div className="status-dot"></div>
              </div>
              {ultimaActualizacion && (
                <span className="last-update">
                  {ultimaActualizacion.toLocaleTimeString()}
                </span>
              )}
            </div>
          </div>
        </header>

        {/* Contenido Principal */}
        <main className="main-content">
          
          {/* Notificación cuando se activa la Segunda Ventanilla */}
          {config.segunda_ventanilla_activa && (
            <section style={{
              background: 'linear-gradient(135deg, rgba(34,197,94,0.15) 0%, rgba(16,185,129,0.15) 100%)',
              border: '2px solid #22c55e',
              borderRadius: '16px',
              padding: '2rem',
              marginBottom: '2rem',
              animation: 'pulse 2s ease-in-out infinite'
            }}>
              <style>{`
                @keyframes pulse {
                  0%, 100% { transform: scale(1); }
                  50% { transform: scale(1.02); }
                }
              `}</style>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '3rem', marginBottom: '1rem', color: '#22c55e' }}></div>
                <h2 style={{ color: '#22c55e', fontSize: '2rem', fontWeight: '700', marginBottom: '1rem' }}>
                  SEGUNDA VENTANILLA HABILITADA
                </h2>
                <div style={{ 
                  background: 'rgba(255,255,255,0.1)', 
                  borderRadius: '12px', 
                  padding: '1.5rem', 
                  marginTop: '1rem',
                  border: '1px solid rgba(255,255,255,0.2)'
                }}>
                  <p style={{ color: '#fff', fontSize: '1.4rem', marginBottom: '1rem', fontWeight: '600' }}>
                      Distribución de Atención:
                  </p>
                  <div style={{ display: 'flex', justifyContent: 'center', gap: '3rem', flexWrap: 'wrap' }}>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ 
                        background: '#3b82f6', 
                        color: 'white', 
                        padding: '1rem 2rem', 
                        borderRadius: '10px',
                        fontWeight: '700',
                        fontSize: '1.2rem',
                        marginBottom: '0.5rem'
                      }}>
                        VENTANILLA 1
                      </div>
                      <p style={{ color: '#d1d5db', fontSize: '1.1rem' }}>
                        Personas <strong>1 a {config.persona_corte_segunda_ventanilla}</strong>
                      </p>
                    </div>
                    
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      fontSize: '2rem',
                      color: '#6b7280'
                    }}>
                      →
                    </div>
                    
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ 
                        background: '#22c55e', 
                        color: 'white', 
                        padding: '1rem 2rem', 
                        borderRadius: '10px',
                        fontWeight: '700',
                        fontSize: '1.2rem',
                        marginBottom: '0.5rem',
                        animation: 'glow 2s ease-in-out infinite'
                      }}>
                        VENTANILLA 2
                      </div>
                      <p style={{ color: '#d1d5db', fontSize: '1.1rem' }}>
                        Desde persona <strong>#{personaDesdeSegundaVentanilla}</strong> en adelante
                      </p>
                    </div>
                  </div>
                  
                  <style>{`
                    @keyframes glow {
                      0%, 100% { box-shadow: 0 0 10px rgba(34,197,94,0.5); }
                      50% { box-shadow: 0 0 20px rgba(34,197,94,0.8); }
                    }
                  `}</style>
                  
                  <div style={{ 
                    marginTop: '1.5rem', 
                    padding: '1rem', 
                    background: 'rgba(34,197,94,0.2)',
                    borderRadius: '8px',
                    border: '1px solid #22c55e'
                  }}>
                    <p style={{ color: '#22c55e', fontSize: '1rem', fontWeight: '600', margin: 0 }}>
                        Persona #{personaDesdeSegundaVentanilla} y posterior, dirijase a la VENTANILLA 2
                    </p>
                  </div>
                </div>
              </div>
            </section>
          )}

          {/* 2 Camaras Fijas */}
          <section className="cameras-section">
            <h2 className="section-title">Camaras en Tiempo Real</h2>
            <div className="cameras-grid">
              {CAMARAS_FIJAS.map((cam) => (
                <CameraView
                  key={cam.camera_id}
                  cameraId={cam.camera_id}
                  title={cam.title}
                />
              ))}
            </div>
          </section>

          {/* Personas en Fila */}

          <section className="queue-section">
            <div className="ranking-section">
              <h3 className="ranking-title">Personas en Fila - Tiempo de Espera</h3>
                {ranking.length > 0 ? (
                  <div className="ranking-table">
                    <table>
                    <thead>
            <tr>
              <th>Posición Global</th>
              <th>Cámara</th>
              <th>Tiempo Espera</th>
              <th>Estado</th>
              {config.segunda_ventanilla_activa && <th>Ventanilla Asignada</th>}
            </tr>
          </thead>
          <tbody>
            {ranking.map((persona) => {
              const posicionGlobal = persona.posicion;
              
              const esInterior = persona.camera_id === 'cam_interior' || persona.segmento === 1;
              const nombreCamara = esInterior ? 'Interior' : 'Exterior';
              const colorCamara = esInterior ? '#22c55e' : '#3b82f6';  
              
              const ventanillaAsignada = config.segunda_ventanilla_activa
                ? (posicionGlobal <= config.persona_corte_segunda_ventanilla ? 1 : 2)
                : 1;
              
              return (
                <tr key={persona.id} className={`rank-${posicionGlobal}`}>
                  <td className="posicion">
                    <span style={{
                      fontSize: '1.5rem',
                      fontWeight: '700',
                      color: '#fff'
                    }}>
                      #{posicionGlobal}
                    </span>
                  </td>
                  
                  {/*  Cámara  */}
                  <td style={{ textAlign: 'left', paddingRight: '2rem' }}> 
                    <span style={{
                      display: 'inline-block',
                      padding: '0.5rem 1rem',
                      background: colorCamara,
                      color: 'white',
                      borderRadius: '8px',
                      fontWeight: '600',
                      fontSize: '0.9rem'
                    }}>
                        {nombreCamara}
                    </span>
                  </td>
                  
                  <td className="tiempo">
                    <span className="tiempo-badge">{persona.tiempo_espera_min} min</span>
                  </td>
                  
                  <td className="estado">
                    {posicionGlobal === 1 ? (
                      <span className="badge badge-atencion">SIENDO ATENDIDO</span>
                    ) : (
                      <span className="badge badge-espera">EN ESPERA</span>
                    )}
                  </td>
                  
                  {config.segunda_ventanilla_activa && (
                    <td style={{ textAlign: 'center' }}>
                      <span style={{
                        display: 'inline-block',
                        padding: '0.5rem 1rem',
                        background: ventanillaAsignada === 1 ? '#3b82f6' : '#22c55e',
                        color: 'white',
                        borderRadius: '8px',
                        fontWeight: '700',
                        fontSize: '0.9rem'
                      }}>
                        VENTANILLA {ventanillaAsignada}
                      </span>
                    </td>
                  )}
                </tr>
              );
            })}
              </tbody>
            </table>
          </div>
          ) : (
            <div className="no-ranking"><p>No hay personas en la fila</p></div>
            )}
          </div>
        </section>

          {/* Horario de Atencion */}
          <section className="schedule-section">
            <h2 className="section-title">Horario de Atencion</h2>
            <div className="schedule-card">
              <div className="schedule-content">
                <div className="schedule-item">
                  <span className="schedule-label">Apertura</span>
                  <span className="schedule-time">{config.hora_apertura}</span>
                </div>
                <div className="schedule-separator">-</div>
                <div className="schedule-item">
                  <span className="schedule-label">Cierre</span>
                  <span className="schedule-time">{config.hora_cierre}</span>
                </div>
              </div>
              {estimado.minutos_hasta_cierre > 0 && (
                <div className="schedule-info">
                  Cierra en: <strong>{Math.floor(estimado.minutos_hasta_cierre)} minutos</strong>
                </div>
              )}
            </div>
          </section>

        </main>

        {/* Footer */}
        <footer className="footer">
          <p>Sistema de Vision Artificial con YOLO</p>
        </footer>
      </div>

      {/* Panel Admin */}
      {mostrarAdmin && (
        <AdminPanel onClose={() => setMostrarAdmin(false)} />
      )}
    </>
  );
}

export default App;