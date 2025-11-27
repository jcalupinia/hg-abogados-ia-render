import os
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List

UAFE_URL = os.getenv("UAFE_URL", "https://www.uafe.gob.ec/resoluciones-sujetos-obligados/").strip()
MAX_ITEMS = 50


def _fetch_uafe_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (H&G Abogados IA)"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.text


def _parse_rows(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return []

    rows_out = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(separator=" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 5:
            continue
        # Try to map columns: Sector, Nro Resolución, Fecha, Alcance/Contenido, Transacciones, Estado
        row = {
            "sector": cells[0],
            "resolucion": cells[1],
            "fecha": cells[2],
            "alcance_contenido": cells[3],
            "transacciones": cells[4] if len(cells) >= 5 else "",
        }
        if len(cells) >= 6:
            row["estado"] = cells[5]
        rows_out.append(row)
    return rows_out


def consultar_uafe(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("consulta") or "").strip().lower()
    try:
        html = _fetch_uafe_html(UAFE_URL)
        rows = _parse_rows(html)
        if texto:
            rows = [
                r for r in rows
                if any(texto in (str(v).lower()) for v in r.values())
            ]
        return {
            "mensaje": f"Resultados UAFE para '{texto}'" if texto else "Listado UAFE",
            "nivel_consulta": "UAFE",
            "resultado": rows[:MAX_ITEMS]
        }
    except Exception as e:
        return {
            "error": f"No se pudo consultar UAFE: {e}",
            "nivel_consulta": "UAFE"
        }
