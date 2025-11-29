# EyeFocusIA

Este repositorio contiene un sistema de gestión de filas con:

- Backend: `backend.py` (FastAPI)
- Detector de visión: `detector_segmento.py` (YOLO + OpenCV). El archivo duplicado original `vision_detector.py` se movió a `backup_detectors/vision_detector.py`.
- Frontend: `dashboard-filas` (React + Vite)

Instrucciones rápidas para arrancar todo junto en Windows:

1. Instala dependencias (Python y Node/npm) y crea el entorno si es necesario.

2. Desde PowerShell en la raíz del proyecto, ejecuta:

```powershell
./start_all.ps1
```

Esto abrirá tres ventanas de PowerShell y lanzará:

- `python backend.py` (FastAPI en `http://127.0.0.1:8000`)
	- `python detector_segmento.py` (intenta conectar a la cámara IP; si falla, usa la webcam local)
- `npm run dev` dentro de `dashboard-filas` (servidor Vite)

Frontend: cuando abras la página (normalmente `http://localhost:5173`) el navegador solicitará permiso de cámara y mostrará un preview local. El detector puede seguir corriendo localmente (Python) y enviar al backend.

Notas:

- `vision_detector.py` ahora hace fallback a la webcam local si la cámara IP no está disponible.
- Si prefieres ejecutar manualmente, puedes abrir tres terminales y lanzar los comandos:
	- `python backend.py`
	- `python detector_segmento.py` (puedes pasar `--camera-url "http://<ip_celular>:8080/video"`)
	- `cd dashboard-filas` && `npm run dev`

Ejemplo para iniciar todo y pasar la URL de la cámara del celular (PowerShell):

```powershell
./start_all.ps1 -cameraUrl "http://192.168.1.12:8080/video"
```

O ejecutar solo el detector con la cámara del celular:

```powershell
python detector_segmento.py --camera-url "http://192.168.1.8:8080/video"
# El archivo original `vision_detector.py` fue movido a `backup_detectors/vision_detector.py` por consolidación.
```