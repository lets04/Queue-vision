from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# --- CONFIGURACIÓN DE NEGOCIO ---
TIEMPO_ATENCION_PROMEDIO = 3  # Minutos que tarda la ventanilla por persona

# --- BASE DE DATOS EN MEMORIA ---
# (Para el prototipo, guardaremos el estado aquí. 
# En producción, esto sería SQLite o PostgreSQL)
estado_fila = {
    "personas": 0,
    "tiempo_espera_min": 0,
    "alerta": False
}

# Modelo de datos que esperamos recibir de la cámara
class DatoCamara(BaseModel):
    conteo: int

@app.get("/")
def home():
    return {"mensaje": "API del Sistema de Filas funcionando"}

# 1. ENDPOINT PARA LA CÁMARA (Recibe datos)
@app.post("/actualizar-fila")
def actualizar_fila(dato: DatoCamara):
    global estado_fila
    
    cantidad = dato.conteo
    
    # LÓGICA DE NEGOCIO: Calcular tiempo
    tiempo_estimado = cantidad * TIEMPO_ATENCION_PROMEDIO
    
    # LÓGICA DE ALERTA: Si hay más de 10 personas, activar alerta
    alerta = True if cantidad > 10 else False

    # Actualizar "Base de Datos"
    estado_fila = {
        "personas": cantidad,
        "tiempo_espera_min": tiempo_estimado,
        "alerta": alerta
    }
    
    print(f"📡 DATO RECIBIDO: {cantidad} personas. Tiempo estimado: {tiempo_estimado} min.")
    return {"status": "ok", "calculo": estado_fila}

# 2. ENDPOINT PARA LA WEB/APP (Entrega datos)
@app.get("/estado-actual")
def obtener_estado():
    # Esto es lo que consultará la página web de los estudiantes
    return estado_fila

if __name__ == "__main__":
    # Correr el servidor en el puerto 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)