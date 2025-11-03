from fastapi import FastAPI, Request, HTTPException
import os

# Importar módulos de los conectores (asegúrate de que existan)
try:
    from providers.fielweb_connector import consultar_fielweb
    from providers.judicial_connectors import consultar_jurisprudencia
except ModuleNotFoundError as e:
    consultar_fielweb = None
    consultar_jurisprudencia = None
    print(f"Error de importación: {e}")

app = FastAPI(title="H&G Abogados IA - Robot Jurídico")

# Seguridad API Key
API_KEY = os.getenv("X_API_KEY", "HYGABOGADOS-SECURE-2025")

@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # Permitir el endpoint de salud sin API key
    if request.url.path in ["/health", "/"]:
        return await call_next(request)

    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida o ausente.")
    
    return await call_next(request)

@app.get("/")
async def root():
    return {"message": "Servicio activo: H&G Abogados IA"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "H&G Abogados IA"}

@app.post("/consult_real_fielweb")
async def consult_fielweb_endpoint(payload: dict):
    if not consultar_fielweb:
        raise HTTPException(status_code=500, detail="Conector FielWeb no disponible.")
    try:
        return consultar_fielweb(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar FielWeb: {str(e)}")

@app.post("/consult_real_jurisprudencia")
async def consult_jurisprudencia_endpoint(payload: dict):
    if not consultar_jurisprudencia:
        raise HTTPException(status_code=500, detail="Conector de Jurisprudencia no disponible.")
    try:
        return consultar_jurisprudencia(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar jurisprudencia: {str(e)}")

@app.post("/consult_hybrid")
async def consult_hybrid(payload: dict):
    texto = payload.get("texto", "")
    tipo = payload.get("tipo_usuario", "")
    try:
        resultado = None
        if consultar_fielweb:
            resultado = consultar_fielweb(payload)
        if not resultado and consultar_jurisprudencia:
            resultado = consultar_jurisprudencia(payload)
        return {"texto": texto, "tipo": tipo, "resultado": resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en consulta híbrida: {str(e)}")
