from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import threading
import time
from datetime import datetime
import uvicorn

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CONFIGURACIÓN
configuracion = {
    "hora_apertura": "08:00",
    "hora_cierre": "18:00",
    "tiempo_atencion_min": 3,
}

# SEGMENTOS (cada cámara es un segmento de la fila)
_segmentos = {}  # segmento_num -> {camera_id, personas_count, personas, timestamp}
_segmentos_lock = threading.Lock()

# FRAMES DE CÁMARAS
_frames = {}
_frames_lock = threading.Lock()
_camera_last_seen = {}

# ESTADÍSTICAS
_estadisticas = {
    'fecha': datetime.now().strftime('%Y-%m-%d'),
    'personas_atendidas': 0,
    'tiempo_promedio_espera': 0,
    'pico_fila': 0,
}
_stats_lock = threading.Lock()

# RANKING
_queue_ranking = {}
_ranking_lock = threading.Lock()


# MODELOS
class PersonaSegmento(BaseModel):
    local_pos: int
    centro_y: float

class DatosSegmento(BaseModel):
    camera_id: str
    segmento: int
    personas_count: int
    personas: List[PersonaSegmento] = []
    timestamp: float

class DatoCamara(BaseModel):
    conteo: int
    en_entrada: int = 0
    en_preventanilla: int = 0
    ids_activos: int = 0
    max_fila: int = 0


@app.get("/")
def home():
    return {"mensaje": "API Sistema de Filas - Multi-Cámara"}


# RECIBIR DATOS DE UN SEGMENTO
@app.post("/segmento-fila")
def recibir_segmento(datos: DatosSegmento):
    with _segmentos_lock:
        _segmentos[datos.segmento] = {
            "camera_id": datos.camera_id,
            "personas_count": datos.personas_count,
            "personas": [p.dict() for p in datos.personas],
            "timestamp": datos.timestamp,
            "last_update": time.time()
        }
    
    # Actualizar pico
    total = _calcular_total_personas()
    with _stats_lock:
        if total > _estadisticas['pico_fila']:
            _estadisticas['pico_fila'] = total
    
    print(f"Segmento {datos.segmento} ({datos.camera_id}): {datos.personas_count} personas")
    return {"status": "ok", "segmento": datos.segmento}


# COMPATIBILIDAD CON DETECTOR ORIGINAL 
@app.post("/actualizar-fila")
def actualizar_fila(dato: DatoCamara):
    datos_seg = DatosSegmento(
        camera_id="cam_default",
        segmento=1,
        personas_count=dato.conteo,
        personas=[],
        timestamp=time.time()
    )
    return recibir_segmento(datos_seg)


def _calcular_total_personas():
    """Suma personas de todos los segmentos activos"""
    with _segmentos_lock:
        ahora = time.time()
        total = 0
        for datos in _segmentos.values():
            if ahora - datos.get('last_update', 0) < 10:
                total += datos['personas_count']
        return total


# ESTADO UNIFICADO (suma de todos los segmentos)
@app.get("/estado-actual")
def obtener_estado():
    with _segmentos_lock:
        ahora = time.time()
        segmentos_activos = {}
        
        for seg_num, datos in _segmentos.items():
            if ahora - datos.get('last_update', 0) < 10:
                segmentos_activos[seg_num] = datos
        
        total_personas = sum(s['personas_count'] for s in segmentos_activos.values())
    
    tiempo_espera = total_personas * configuracion['tiempo_atencion_min']
    
    return {
        "personas": total_personas,
        "tiempo_espera_min": tiempo_espera,
        "alerta": total_personas > 10,
        "segmentos_activos": len(segmentos_activos),
        "detalle_segmentos": {str(k): v['personas_count'] for k, v in segmentos_activos.items()},
        "max_fila": _estadisticas['pico_fila'],
        "en_entrada": 0,
        "ids_activos": total_personas
    }


# FILA COMPLETA CON POSICIONES GLOBALES
@app.get("/fila-completa")
def obtener_fila_completa():
    with _segmentos_lock:
        ahora = time.time()
        segmentos_activos = {}
        
        for seg_num, datos in _segmentos.items():
            if ahora - datos.get('last_update', 0) < 10:
                segmentos_activos[seg_num] = datos
        
        fila_global = []
        offset = 0
        
        for seg_num in sorted(segmentos_activos.keys()):
            datos = segmentos_activos[seg_num]
            for persona in datos['personas']:
                posicion_global = offset + persona['local_pos']
                fila_global.append({
                    'id': posicion_global,
                    'posicion': posicion_global - 1,
                    'segmento': seg_num,
                    'camera_id': datos['camera_id'],
                    'tiempo_espera_min': (posicion_global - 1) * configuracion['tiempo_atencion_min']
                })
            offset += datos['personas_count']
    
    return {"total": len(fila_global), "personas": fila_global}


# RANKING (compatible con frontend)
@app.post("/queue-ranking")
async def recibir_ranking(data: dict):
    try:
        camera_id = data.get('camera_id', 'default')
        personas = data.get('personas', [])
        
        with _ranking_lock:
            _queue_ranking[camera_id] = personas
        
        return {"status": "ok", "count": len(personas)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/queue-ranking")
def obtener_ranking(camera_id: str = None):
    # Primero intentar desde fila-completa (multi-cámara)
    fila = obtener_fila_completa()
    
    if fila['total'] > 0:
        if camera_id:
            personas = [p for p in fila['personas'] if p['camera_id'] == camera_id]
        else:
            personas = fila['personas']
        return {"camera_id": camera_id or "global", "personas": personas, "total": len(personas)}
    
    # Fallback al ranking tradicional
    with _ranking_lock:
        if not camera_id:
            camera_id = list(_queue_ranking.keys())[0] if _queue_ranking else None
        ranking = _queue_ranking.get(camera_id, [])
    
    return {"camera_id": camera_id, "personas": ranking, "total": len(ranking)}


# LISTAR SEGMENTOS/CÁMARAS
@app.get("/segmentos")
def listar_segmentos():
    with _segmentos_lock:
        ahora = time.time()
        resultado = []
        
        for seg_num, datos in _segmentos.items():
            activo = ahora - datos.get('last_update', 0) < 10
            resultado.append({
                "segmento": seg_num,
                "camera_id": datos['camera_id'],
                "personas": datos['personas_count'],
                "activo": activo
            })
        
        resultado.sort(key=lambda x: x['segmento'])
    
    return {"segmentos": resultado}


# CONFIGURACIÓN
@app.get("/config")
def obtener_config():
    estado = obtener_estado()
    
    ahora = datetime.now()
    try:
        hora_cierre = datetime.strptime(configuracion['hora_cierre'], '%H:%M').time()
        cierre_dt = datetime.combine(ahora.date(), hora_cierre)
        minutos_hasta_cierre = max(0, (cierre_dt - ahora).total_seconds() / 60)
    except:
        minutos_hasta_cierre = 0
    
    tiempo_por_persona = configuracion['tiempo_atencion_min']
    personas_en_cola = estado['personas']
    personas_estimadas = int(minutos_hasta_cierre / tiempo_por_persona) if tiempo_por_persona > 0 else 0
    
    return {
        "config": configuracion,
        "estimado": {
            "minutos_hasta_cierre": round(minutos_hasta_cierre, 0),
            "personas_en_cola": personas_en_cola,
            "personas_estimadas_atendidas": personas_estimadas,
            "alerta_nueva_ventanilla": personas_estimadas < personas_en_cola
        }
    }


@app.post("/config/schedule")
def actualizar_schedule(data: dict):
    try:
        apertura = data.get('apertura')
        cierre = data.get('cierre')
        
        if not apertura or not cierre:
            return {"status": "error", "message": "Faltan parámetros"}
        
        datetime.strptime(apertura, '%H:%M')
        datetime.strptime(cierre, '%H:%M')
        
        configuracion['hora_apertura'] = apertura
        configuracion['hora_cierre'] = cierre
        
        print(f"Horarios actualizados: {apertura} - {cierre}")
        return {"status": "ok", "config": configuracion}
    except ValueError as e:
        return {"status": "error", "message": f"Formato inválido: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/config/service-time")
def actualizar_tiempo_atencion(data: dict):
    try:
        minutos = data.get('minutos')
        
        if minutos is None:
            return {"status": "error", "message": "Falta parámetro minutos"}
        
        minutos = int(minutos)
        if minutos <= 0:
            return {"status": "error", "message": "El tiempo debe ser > 0"}
        
        configuracion['tiempo_atencion_min'] = minutos
        
        print(f"Tiempo de atención: {minutos} min")
        return {"status": "ok", "config": configuracion}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ESTADÍSTICAS
@app.get("/estadisticas")
def obtener_estadisticas():
    with _stats_lock:
        stats = _estadisticas.copy()
    
    ahora = datetime.now()
    hora_apertura = datetime.strptime(configuracion['hora_apertura'], '%H:%M').time()
    hora_cierre = datetime.strptime(configuracion['hora_cierre'], '%H:%M').time()
    
    apertura_dt = datetime.combine(ahora.date(), hora_apertura)
    cierre_dt = datetime.combine(ahora.date(), hora_cierre)
    
    if ahora >= apertura_dt:
        tiempo_transcurrido = (min(ahora, cierre_dt) - apertura_dt).total_seconds() / 3600
        stats['horas_operacion'] = round(tiempo_transcurrido, 2)
        
        if tiempo_transcurrido > 0:
            stats['velocidad_atencion'] = round(stats['personas_atendidas'] / tiempo_transcurrido, 1)
        else:
            stats['velocidad_atencion'] = 0
    else:
        stats['horas_operacion'] = 0
        stats['velocidad_atencion'] = 0
    
    if ahora < apertura_dt:
        stats['estado_ventanilla'] = 'CERRADA (antes de apertura)'
    elif ahora >= cierre_dt:
        stats['estado_ventanilla'] = 'CERRADA'
    else:
        stats['estado_ventanilla'] = 'ABIERTA'
        stats['minutos_hasta_cierre'] = int((cierre_dt - ahora).total_seconds() / 60)
    
    estado = obtener_estado()
    stats['personas_actuales'] = estado['personas']
    stats['segmentos_activos'] = estado['segmentos_activos']
    
    return stats


@app.post("/estadisticas/reset")
def resetear_estadisticas():
    global _estadisticas
    with _stats_lock:
        _estadisticas = {
            'fecha': datetime.now().strftime('%Y-%m-%d'),
            'personas_atendidas': 0,
            'tiempo_promedio_espera': 0,
            'pico_fila': 0,
        }
    
    with _segmentos_lock:
        _segmentos.clear()
    
    print("Estadísticas reseteadas")
    return {"status": "ok"}


# CÁMARAS - FRAMES
@app.post("/upload-frame")
async def upload_frame(request: Request):
    # Leer multipart/form-data completo para depuración y compatibilidad
    form = await request.form()
    # Mostrar keys/valores recibidos (no imprimas contenido binario grande)
    try:
        keys = list(form.keys())
        print(f"[upload-frame] form-keys={keys}")
    except Exception:
        pass

    # Intentar obtener camera_id
    camera_id = form.get('camera_id') or form.get('cameraId') or 'default'

    # Obtener el archivo (puede ser UploadFile o SpooledTemporaryFile)
    file_field = form.get('frame') or form.get('file')
    contents = b''
    if file_field is not None:
        # Si es UploadFile de Starlette
        if hasattr(file_field, 'read'):
            contents = await file_field.read()
        else:
            try:
                # si es bytes-like
                contents = file_field
            except Exception:
                contents = b''

    with _frames_lock:
        _frames[camera_id] = contents
        _camera_last_seen[camera_id] = time.time()

    try:
        print(f"[upload-frame] camera_id={camera_id} bytes={len(contents)} last_seen={_camera_last_seen[camera_id]}")
    except Exception:
        pass

    return {"status": "ok", "camera_id": camera_id}


@app.get('/stream/{camera_id}.mjpg')
def mjpeg_stream(camera_id: str):
    print(f"[stream] client requested stream for: {camera_id}")
    def gen():
        while True:
            with _frames_lock:
                frame = _frames.get(camera_id)
            if frame:
                yield b'--frame\r\n'
                yield b'Content-Type: image/jpeg\r\n'
                yield f'Content-Length: {len(frame)}\r\n\r\n'.encode()
                yield frame
                yield b'\r\n'
            time.sleep(0.05)
    
    return StreamingResponse(gen(), media_type='multipart/x-mixed-replace; boundary=frame')


@app.get('/cameras')
def list_cameras():
    with _frames_lock:
        ahora = time.time()
        cameras = [
            {
                "camera_id": cam,
                "activo": ahora - _camera_last_seen.get(cam, 0) < 5,
                "last_seen": _camera_last_seen.get(cam)
            }
            for cam in _frames.keys()
        ]
    return {"cameras": cameras}


if __name__ == "__main__":
    print(f"Configuración: {configuracion}")
    uvicorn.run(app, host="0.0.0.0", port=8000)