from fastapi import FastAPI, Request, HTTPException
import os
from providers.fielweb_connector import consultar_fielweb
from providers.judicial_connectors import consultar_jurisprudencia

app = FastAPI(title="H&G Abogados IA - Robot Jurídico")

# Seguridad API Key
API_KEY = os.getenv("X_API_KEY", "HYGABOGADOS-SECURE-2025")

@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida o ausente.")
    return await call_next(request)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "H&G Abogados IA"}

@app.post("/consult_real_fielweb")
async def consult_fielweb(payload: dict):
    return consultar_fielweb(payload)

@app.post("/consult_real_jurisprudencia")
async def consult_jurisprudencia(payload: dict):
    return consultar_jurisprudencia(payload)

@app.post("/consult_hybrid")
async def consult_hybrid(payload: dict):
    texto = payload.get("texto", "")
    tipo = payload.get("tipo_usuario", "")
    resultado = consultar_fielweb(payload)
    if not resultado:
        resultado = consultar_jurisprudencia(payload)
    return {"texto": texto, "tipo": tipo, "resultado": resultado}
