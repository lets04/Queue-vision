import streamlit as st
import requests
import time
import pandas as pd

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Monitor de Filas - Campus",
    page_icon="⏳",
    layout="centered"
)

# Estilos CSS para que se vea más moderno (Opcional)
st.markdown("""
    <style>
    .big-font { font-size: 80px !important; font-weight: bold; color: #1f77b4; }
    .alert { color: red; font-weight: bold; font-size: 24px; }
    .normal { color: green; font-weight: bold; font-size: 24px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🎓 Monitor de Filas - Ventanilla Única")
st.markdown("Consulta el tiempo de espera en tiempo real antes de acercarte.")

# Contenedores vacíos que actualizaremos en el bucle
col1, col2 = st.columns(2)
contenedor_metricas = st.empty()
contenedor_alerta = st.empty()
contenedor_grafico = st.empty()

# URL de tu backend
URL_API = "http://127.0.0.1:8000/estado-actual"

# Simulación de histórico para el gráfico (se llenará con el tiempo)
if "historico" not in st.session_state:
    st.session_state.historico = []

def obtener_datos():
    try:
        r = requests.get(URL_API)
        return r.json()
    except:
        return None

# --- BUCLE DE ACTUALIZACIÓN (AUTO-REFRESH) ---
while True:
    data = obtener_datos()
    
    if data:
        personas = data["personas"]
        tiempo = data["tiempo_espera_min"]
        alerta = data["alerta"]

        # Guardar en histórico para el gráfico
        st.session_state.historico.append({"minutos": tiempo})
        if len(st.session_state.historico) > 50: # Mantener solo los últimos 50 datos
            st.session_state.historico.pop(0)

        # 1. MOSTRAR MÉTRICAS PRINCIPALES
        with contenedor_metricas.container():
            kpi1, kpi2 = st.columns(2)
            
            kpi1.metric(
                label="👥 Personas en Fila", 
                value=f"{personas}",
                delta_color="inverse"
            )
            
            kpi2.metric(
                label="⏱️ Tiempo Estimado", 
                value=f"{tiempo} min",
                delta=f"{tiempo} min de espera",
                delta_color="inverse"
            )

        # 2. MOSTRAR ALERTA VISUAL
        with contenedor_alerta.container():
            if alerta:
                st.error("⚠️ ALTA DEMANDA: Se recomienda habilitar ventanilla 2")
            else:
                st.success("✅ Flujo Normal: Tiempo de espera aceptable")

        # 3. GRÁFICO DE TENDENCIA (Para Administrativos)
        with contenedor_grafico.container():
            st.markdown("### 📈 Tendencia de Espera")
            df = pd.DataFrame(st.session_state.historico)
            st.line_chart(df)

    else:
        st.warning("⚠️ No se puede conectar con el servidor central...")

    # Esperar 1 segundo antes de actualizar
    time.sleep(1)