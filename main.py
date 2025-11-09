@app.post("/consult_hybrid")
async def consult_hybrid(payload: dict):
    texto = payload.get("texto", "")
    tipo = payload.get("tipo_usuario", "")
    try:
        print(f"Consulta recibida: {texto} ({tipo})")  # Log visible en Render
        return {
            "status": "ok",
            "mensaje": "El servicio está activo y recibe correctamente las consultas.",
            "texto": texto,
            "tipo_usuario": tipo
        }
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error general: {str(e)}")
