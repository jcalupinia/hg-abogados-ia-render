from fastapi import FastAPI, Request, HTTPException
import traceback
import os

# Inicializar la app principal de FastAPI
app = FastAPI(title="H&G Abogados IA - Robot Jurídico")

# Seguridad API Key
API_KEY = os.getenv("X_API_KEY", "HYGABOGADOS-SECURE-2025")

# Middleware para verificar autenticación
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # Permitir / y /health sin autenticación
    if request.url.path in ["/", "/health"]:
        return await call_next(request)
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida o ausente.")
    return await call_next(request)

# Endpoint raíz
@app.get("/")
async def root():
    return {"message": "Servicio activo: H&G Abogados IA"}

# Endpoint de salud
@app.get("/health")
async def health():
    return {"status": "ok", "service": "H&G Abogados IA"}

# Endpoint de prueba del flujo híbrido
@app.post("/consult_hybrid")
async def consult_hybrid(payload: dict):
    texto = payload.get("texto", "")
    tipo = payload.get("tipo_usuario", "")
    try:
        print(f"Consulta recibida: '{texto}' ({tipo})")  # Log visible en Render
        return {
            "status": "ok",
            "mensaje": "El servicio está activo y recibe correctamente las consultas.",
            "texto": texto,
            "tipo_usuario": tipo
        }
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error general: {str(e)}")
