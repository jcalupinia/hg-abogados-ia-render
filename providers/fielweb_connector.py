def consultar_fielweb(payload):
    # Simulación de consulta real en FielWeb
    texto = payload.get("texto", "")
    return {"fuente": "FielWeb", "consulta": texto, "resultado": "Normativa encontrada y procesada."}
