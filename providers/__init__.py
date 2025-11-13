"""
📦 Paquete: providers
Módulos de conexión externa para H&G Abogados IA
-------------------------------------------------
Incluye conectores seguros para:
- FielWeb (consulta de normas, códigos y concordancias)
- Portales Judiciales (SATJE, Corte Constitucional y Corte Nacional)
-------------------------------------------------
Compatible con entornos:
- Render Cloud (modo sin sandbox)
- Local / VSCode (modo interactivo con depuración)
"""

import os
import sys
import traceback

# ================================
# 🔍 CONFIGURACIÓN DE IMPORTACIÓN
# ================================
PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
if PACKAGE_ROOT not in sys.path:
    sys.path.append(PACKAGE_ROOT)

# ================================
# 🧩 IMPORTACIÓN SEGURA DE MÓDULOS
# ================================
consultar_fielweb = None
consultar_jurisprudencia = None

try:
    from .fielweb_connector import consultar_fielweb
except Exception as e:
    print("⚠️ [INIT] Error al importar conector FielWeb:")
    traceback.print_exc()
    consultar_fielweb = lambda *args, **kwargs: {
        "error": f"No se pudo importar conector FielWeb: {e}",
        "nivel_consulta": "FielWeb"
    }

try:
    from .judicial_connectors import consultar_jurisprudencia
except Exception as e:
    print("⚠️ [INIT] Error al importar conector Judicial:")
    traceback.print_exc()
    consultar_jurisprudencia = lambda *args, **kwargs: {
        "error": f"No se pudo importar conector Judicial: {e}",
        "nivel_consulta": "Jurisprudencia"
    }

# ================================
# 🧠 DIAGNÓSTICO AUTOMÁTICO
# ================================
def check_providers_status() -> dict:
    """
    Verifica el estado de los módulos de conectores.
    Retorna un resumen útil para diagnóstico en /check_fielweb_status.
    """
    status = {}

    # --- Estado FielWeb ---
    try:
        from playwright.async_api import async_playwright
        status["playwright"] = "✅ Instalado"
    except Exception as e:
        status["playwright"] = f"❌ No disponible: {str(e)}"

    status["fielweb_connector"] = (
        "✅ Importado correctamente"
        if callable(consultar_fielweb)
        else "❌ No cargado"
    )

    status["judicial_connector"] = (
        "✅ Importado correctamente"
        if callable(consultar_jurisprudencia)
        else "❌ No cargado"
    )

    # Variables de entorno críticas
    env_keys = [
        "FIELWEB_LOGIN_URL",
        "FIELWEB_USERNAME",
        "FIELWEB_PASSWORD",
        "X_API_KEY",
    ]
    missing_env = [k for k in env_keys if not os.getenv(k)]
    status["variables_entorno"] = (
        "✅ Completas" if not missing_env else f"⚠️ Faltan: {', '.join(missing_env)}"
    )

    # Entorno de ejecución
    if os.getenv("RENDER"):
        status["entorno"] = "Render Cloud"
    elif "VSCODE" in os.getenv("TERM_PROGRAM", ""):
        status["entorno"] = "Visual Studio Code (Local)"
    else:
        status["entorno"] = "Local/Manual"

    return status


# ================================
# 🧾 PRUEBA LOCAL OPCIONAL
# ================================
if __name__ == "__main__":
    print("🧠 Verificando estado de los conectores...")
    estado = check_providers_status()
    for k, v in estado.items():
        print(f"{k}: {v}")
    print("✅ Diagnóstico completado.")

