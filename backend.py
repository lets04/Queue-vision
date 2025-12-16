from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import time
from datetime import datetime
import uvicorn
from collections import defaultdict
import math

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
    "segunda_ventanilla_activa": False,  
    "persona_corte_segunda_ventanilla": 0 
}

# USAR DICCIONARIOS THREAD-SAFE 
_segmentos = {}
_frames = {}
_camera_last_seen = {}
_estadisticas = {
    'fecha': datetime.now().strftime('%Y-%m-%d'),
    'personas_atendidas': 0,
    'tiempo_promedio_espera': 0,
    'pico_fila': 0,
    'tiempos_espera_acumulados': []
}
_queue_ranking = {}
_personas_historico = {}
_ultimo_reseteo = datetime.now()
_alerta_ventanilla_mostrada = False  

# LOCK PARA OPERACIONES CRÍTICAS
_global_lock = asyncio.Lock()


# MODELOS

class PersonaSegmento(BaseModel):
    local_pos: int
    centro_y: float
    confianza: Optional[float] = 1.0

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


# ENDPOINTS - DATOS

@app.get("/")
async def home():
    return {"mensaje": "API Sistema de Filas - Multi-Cámara (Optimizado)"}


@app.post("/segmento-fila")
async def recibir_segmento(datos: DatosSegmento):
    
    # Actualizar segmento 
    _segmentos[datos.segmento] = {
        "camera_id": datos.camera_id,
        "personas_count": datos.personas_count,
        "personas": [p.dict() for p in datos.personas],
        "timestamp": datos.timestamp,
        "last_update": time.time()
    }
    
    # Actualizar pico
    total = _calcular_total_personas()
    if total > _estadisticas['pico_fila']:
        _estadisticas['pico_fila'] = total
    
    asyncio.create_task(_actualizar_tracking_personas())
    
    # Calcular offset para numeración global
    ahora = time.time()
    segmentos_ordenados = sorted([s for s in _segmentos.keys() if ahora - _segmentos[s].get('last_update', 0) < 10])
    offset = 0
    for s in segmentos_ordenados:
        if s == datos.segmento:
            break
        offset += _segmentos[s]['personas_count']
    
    # Print asíncrono 
    asyncio.create_task(_log_async(
        f"Segmento {datos.segmento} ({datos.camera_id}): {datos.personas_count} personas, offset={offset}"
    ))
    
    # Devolver offset para numeración global
    return {"offset": offset}


@app.post("/actualizar-fila")
async def actualizar_fila(dato: DatoCamara):
    """Compatibilidad con detector original"""
    datos_seg = DatosSegmento(
        camera_id="cam_default",
        segmento=1,
        personas_count=dato.conteo,
        personas=[],
        timestamp=time.time()
    )
    return await recibir_segmento(datos_seg)


def _calcular_total_personas():
    ahora = time.time()
    total = 0
    for datos in _segmentos.values():
        if ahora - datos.get('last_update', 0) < 10:
            total += datos['personas_count']
    return total


# Sistema automático de detección de personas atendidas
async def _actualizar_tracking_personas():

    global _personas_historico, _estadisticas
    
    await _verificar_reseteo_diario()
    
    ahora = time.time()
    personas_actuales = {}
    
    # Obtener todas las personas actuales en fila
    for seg_num, datos in _segmentos.items():
        if ahora - datos.get('last_update', 0) < 10:
            for persona in datos['personas']:
                # Usar combinación de segmento + posición como ID único
                persona_id = f"{datos['camera_id']}_seg{seg_num}_pos{persona['local_pos']}"
                personas_actuales[persona_id] = {
                    'camera_id': datos['camera_id'],
                    'segmento': seg_num,
                    'posicion': persona['local_pos'],
                    'timestamp': ahora,
                    'centro_y': persona['centro_y']
                }
    
    # Registrar nuevas personas
    for pid, info in personas_actuales.items():
        if pid not in _personas_historico:
            _personas_historico[pid] = {
                'entrada': ahora,
                'info': info
            }
    
    # Detectar personas que salieron 
    personas_atendidas = []
    for pid, data in list(_personas_historico.items()):
        if pid not in personas_actuales:
            # Esta persona ya no está en la fila
            tiempo_espera = ahora - data['entrada']
            tiempo_espera_min = tiempo_espera / 60
            
            # Solo contar si estuvo al menos 30 segundos 
            if tiempo_espera > 30:
                personas_atendidas.append(tiempo_espera_min)
                await _log_async(f"✓ Persona atendida: {tiempo_espera_min:.1f} min de espera")
            
            # Eliminar del histórico
            del _personas_historico[pid]
    
    if personas_atendidas:
        _estadisticas['personas_atendidas'] += len(personas_atendidas)
        _estadisticas['tiempos_espera_acumulados'].extend(personas_atendidas)
        
        if _estadisticas['tiempos_espera_acumulados']:
            _estadisticas['tiempo_promedio_espera'] = sum(_estadisticas['tiempos_espera_acumulados']) / len(_estadisticas['tiempos_espera_acumulados'])


@app.get("/estado-actual")
async def obtener_estado():
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


@app.get("/fila-completa")
async def obtener_fila_completa():

    ahora = time.time()
    segmentos_activos = {}
    
    for seg_num, datos in _segmentos.items():
        if ahora - datos.get('last_update', 0) < 10:
            segmentos_activos[seg_num] = datos
    
    fila_global = []
    posicion_global = 1  # ← Empieza en 1
    
    # Procesar segmentos en orden 
    for seg_num in sorted(segmentos_activos.keys()):
        datos = segmentos_activos[seg_num]
        
        # Procesar cada persona del segmento
        for persona in datos['personas']:
            fila_global.append({
                'id': posicion_global,  
                'posicion': posicion_global,  
                'segmento': seg_num,
                'camera_id': datos['camera_id'],
                'local_pos': posicion_global,  # Cambiado para enumeración continua global
                'tiempo_espera_min': (posicion_global - 1) * configuracion['tiempo_atencion_min'],  
                'confianza': persona.get('confianza', 1.0),
                'centro_y': persona.get('centro_y', 0)
            })
            posicion_global += 1  
    
    return {
        "total": len(fila_global),
        "personas": fila_global,
        "segmentos": {
            str(seg): len([p for p in fila_global if p['segmento'] == seg])
            for seg in segmentos_activos.keys()
        }
    }

@app.get("/segmentos")
async def listar_segmentos():
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


# ENDPOINTS - FRAMES 

@app.post("/upload-frame")
async def upload_frame(request: Request):
    
    try:
        form = await request.form()
        camera_id = form.get('camera_id') or form.get('cameraId') or 'default'
        
        file_field = form.get('frame') or form.get('file')
        
        if file_field and hasattr(file_field, 'read'):
            contents = await file_field.read()
        else:
            contents = file_field if file_field else b''
        
        if len(contents) > 0:
            _frames[camera_id] = contents
            _camera_last_seen[camera_id] = time.time()

        return Response(status_code=202)  
        
    except Exception as e:
        return Response(status_code=400)


@app.get('/stream/{camera_id}.mjpg')
async def mjpeg_stream(camera_id: str):
    
    async def gen():
        """Generador asíncrono de frames"""
        last_frame = None
        no_frame_count = 0
        
        while True:
            frame = _frames.get(camera_id)
            
            if frame and frame != last_frame:
                last_frame = frame
                no_frame_count = 0
                
                yield b'--frame\r\n'
                yield b'Content-Type: image/jpeg\r\n'
                yield f'Content-Length: {len(frame)}\r\n\r\n'.encode()
                yield frame
                yield b'\r\n'
            
            elif no_frame_count > 10 and last_frame:
                yield b'--frame\r\n'
                yield b'Content-Type: image/jpeg\r\n'
                yield f'Content-Length: {len(last_frame)}\r\n\r\n'.encode()
                yield last_frame
                yield b'\r\n'
                no_frame_count = 0
            else:
                no_frame_count += 1
            
            await asyncio.sleep(0.033)  
    
    return StreamingResponse(
        gen(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )


@app.get('/cameras')
async def list_cameras():
    ahora = time.time()
    cameras = [
        {
            "camera_id": cam,
            "activo": ahora - _camera_last_seen.get(cam, 0) < 5,
            "last_seen": _camera_last_seen.get(cam),
            "ultimo_frame": f"{(ahora - _camera_last_seen.get(cam, 0)):.1f}s ago"
        }
        for cam in _frames.keys()
    ]
    return {"cameras": cameras, "total": len(cameras)}


# ENDPOINTS - RANKING

@app.post("/queue-ranking")
async def recibir_ranking(data: dict):
    try:
        camera_id = data.get('camera_id', 'default')
        personas = data.get('personas', [])
        
        _queue_ranking[camera_id] = personas
        
        return Response(status_code=202)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/queue-ranking")
async def obtener_ranking(camera_id: Optional[str] = None):
    fila = await obtener_fila_completa()
    
    if fila['total'] > 0:
        if camera_id:
            personas = [p for p in fila['personas'] if p['camera_id'] == camera_id]
        else:
            personas = fila['personas']
        return {"camera_id": camera_id or "global", "personas": personas, "total": len(personas)}
    
    if not camera_id:
        camera_id = list(_queue_ranking.keys())[0] if _queue_ranking else None
    ranking = _queue_ranking.get(camera_id, [])
    
    return {"camera_id": camera_id, "personas": ranking, "total": len(ranking)}


# Endpoint manual para atender persona
@app.post("/atender-persona")
async def atender_persona_manual(data: dict):
    """
    Endpoint manual para registrar una persona atendida
    Útil si quieres un botón en el frontend
    """
    global _estadisticas
    
    tiempo_espera = data.get('tiempo_espera_min', configuracion['tiempo_atencion_min'])
    
    _estadisticas['personas_atendidas'] += 1
    _estadisticas['tiempos_espera_acumulados'].append(tiempo_espera)
    
    # Recalcular promedio
    if _estadisticas['tiempos_espera_acumulados']:
        _estadisticas['tiempo_promedio_espera'] = sum(_estadisticas['tiempos_espera_acumulados']) / len(_estadisticas['tiempos_espera_acumulados'])
    
    await _log_async(f"✓ Persona atendida manualmente: {tiempo_espera} min")
    
    return {
        "status": "ok",
        "personas_atendidas": _estadisticas['personas_atendidas'],
        "tiempo_promedio": round(_estadisticas['tiempo_promedio_espera'], 2)
    }


# ENDPOINTS - CONFIGURACIÓN

@app.get("/config")
async def obtener_config():
    global _alerta_ventanilla_mostrada
    
    estado = await obtener_estado()
    
    ahora = datetime.now()
    try:
        hora_cierre = datetime.strptime(configuracion['hora_cierre'], '%H:%M').time()
        cierre_dt = datetime.combine(ahora.date(), hora_cierre)
        minutos_hasta_cierre = max(0, (cierre_dt - ahora).total_seconds() / 60)
    except:
        minutos_hasta_cierre = 0
    
    tiempo_por_persona = configuracion['tiempo_atencion_min']
    personas_en_cola = estado['personas']
    personas_estimadas = (
    math.ceil(minutos_hasta_cierre / tiempo_por_persona)
    if tiempo_por_persona > 0
    else 0
    )

    # Calcular si hay alerta
    alerta_nueva_ventanilla = personas_estimadas < personas_en_cola

    if alerta_nueva_ventanilla and not _alerta_ventanilla_mostrada:
        _alerta_ventanilla_mostrada = True
    
    if not alerta_nueva_ventanilla:
        _alerta_ventanilla_mostrada = False
    
    return {
        "config": configuracion,
        "estimado": {
            "minutos_hasta_cierre": round(minutos_hasta_cierre, 0),
            "personas_en_cola": personas_en_cola,
            "personas_estimadas_atendidas": personas_estimadas,
            "alerta_nueva_ventanilla": alerta_nueva_ventanilla,
            "personas_excedentes": max(0, personas_en_cola - personas_estimadas),  # ← NUEVO
            "persona_corte": personas_estimadas,  # ← NUEVO: desde qué # van a ventanilla 2
            "segunda_ventanilla_activa": configuracion['segunda_ventanilla_activa'],  # ← NUEVO
            "alerta_pendiente": _alerta_ventanilla_mostrada and alerta_nueva_ventanilla  # ← NUEVO
        }
    }


@app.post("/config/schedule")
async def actualizar_schedule(data: dict):
    try:
        apertura = data.get('apertura')
        cierre = data.get('cierre')
        
        if not apertura or not cierre:
            return {"status": "error", "message": "Faltan parámetros"}
        
        datetime.strptime(apertura, '%H:%M')
        datetime.strptime(cierre, '%H:%M')
        
        configuracion['hora_apertura'] = apertura
        configuracion['hora_cierre'] = cierre
        
        await _log_async(f"Horarios actualizados: {apertura} - {cierre}")
        return {"status": "ok", "config": configuracion}
    except ValueError as e:
        return {"status": "error", "message": f"Formato inválido: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/config/service-time")
async def actualizar_tiempo_atencion(data: dict):
    try:
        minutos = data.get('minutos')
        
        if minutos is None:
            return {"status": "error", "message": "Falta parámetro minutos"}
        
        minutos = int(minutos)
        if minutos <= 0:
            return {"status": "error", "message": "El tiempo debe ser > 0"}
        
        configuracion['tiempo_atencion_min'] = minutos
        
        await _log_async(f"Tiempo de atención: {minutos} min")
        return {"status": "ok", "config": configuracion}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Endpoint para activar/desactivar segunda ventanilla
@app.post("/config/segunda-ventanilla")
async def activar_segunda_ventanilla(data: dict):

    global _alerta_ventanilla_mostrada
    
    try:
        activar = data.get('activar', False)
        persona_corte = data.get('persona_corte', 0)
        
        configuracion['segunda_ventanilla_activa'] = activar
        configuracion['persona_corte_segunda_ventanilla'] = persona_corte
        
        # Marcar que la alerta fue atendida
        if activar:
            _alerta_ventanilla_mostrada = False
            await _log_async(f"✓ Segunda ventanilla ACTIVADA - Corte en persona #{persona_corte}")
        else:
            await _log_async(f"✓ Segunda ventanilla DESACTIVADA")
        
        return {
            "status": "ok",
            "segunda_ventanilla_activa": configuracion['segunda_ventanilla_activa'],
            "persona_corte": configuracion['persona_corte_segunda_ventanilla']
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ENDPOINTS - ESTADÍSTICAS

@app.get("/estadisticas")
async def obtener_estadisticas():
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
    
    estado = await obtener_estado()
    stats['personas_actuales'] = estado['personas']
    stats['segmentos_activos'] = estado['segmentos_activos']
    
    stats['tiempo_promedio_espera'] = round(stats['tiempo_promedio_espera'], 1)
    
    if 'tiempos_espera_acumulados' in stats:
        del stats['tiempos_espera_acumulados']
    
    return stats


@app.post("/estadisticas/reset")
async def resetear_estadisticas():
    global _estadisticas, _personas_historico
    
    _estadisticas = {
        'fecha': datetime.now().strftime('%Y-%m-%d'),
        'personas_atendidas': 0,
        'tiempo_promedio_espera': 0,
        'pico_fila': 0,
        'tiempos_espera_acumulados': []
    }
    
    _segmentos.clear()
    _personas_historico.clear()
    
    await _log_async("Estadísticas reseteadas")
    return {"status": "ok"}


# Verificación automática de reseteo diario
async def _verificar_reseteo_diario():

    global _estadisticas, _personas_historico, _ultimo_reseteo
    
    ahora = datetime.now()
    
    # Resetear a medianoche 
    if ahora.date() > _ultimo_reseteo.date():
        await _log_async(f" Nuevo día detectado: {ahora.date()}")
        await _resetear_estadisticas_interno()
        return
    
    # Resetear después de la hora de cierre
    try:
        hora_cierre = datetime.strptime(configuracion['hora_cierre'], '%H:%M').time()
        cierre_dt = datetime.combine(ahora.date(), hora_cierre)
        
        if ahora >= cierre_dt:
            ultimo_cierre_hoy = datetime.combine(ahora.date(), hora_cierre)
            
            if _ultimo_reseteo < ultimo_cierre_hoy:
                await _log_async(f" Hora de cierre alcanzada: {hora_cierre}")
                await _resetear_estadisticas_interno()
                return
    except:
        pass


async def _resetear_estadisticas_interno():
    """Resetear estadísticas internamente (llamado por verificación automática)"""
    global _estadisticas, _personas_historico, _ultimo_reseteo
    
    # Guardar estadísticas del día anterior 
    stats_anteriores = _estadisticas.copy()
    await _log_async(f"""

    RESUMEN DEL DÍA: {stats_anteriores['fecha']}

    Personas Atendidas: {stats_anteriores['personas_atendidas']}
    Tiempo Promedio: {stats_anteriores.get('tiempo_promedio_espera', 0):.1f} min
    Pico Máximo: {stats_anteriores['pico_fila']} personas
    """)
    
    # Resetear estadísticas
    _estadisticas = {
        'fecha': datetime.now().strftime('%Y-%m-%d'),
        'personas_atendidas': 0,
        'tiempo_promedio_espera': 0,
        'pico_fila': 0,
        'tiempos_espera_acumulados': []
    }
    
    _personas_historico.clear()
    _ultimo_reseteo = datetime.now()
    
    await _log_async("Estadísticas reseteadas automáticamente")


# UTILIDADES

async def _log_async(message: str):
    """Log asíncrono que no bloquea"""
    await asyncio.sleep(0) 
    print(message)


# SERVIDOR

if __name__ == "__main__":
    import sys
    import platform

    is_windows = platform.system() == 'Windows'
    
    if is_windows:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            limit_concurrency=100,
            timeout_keep_alive=5
        )
    else:
        uvicorn.run(
            "backend:app",  
            host="0.0.0.0",
            port=8000,
            workers=2,
            limit_concurrency=100,
            timeout_keep_alive=5
        )