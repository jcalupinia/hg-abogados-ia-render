import os
import asyncio
import base64
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, quote
import requests
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ================================
# ⚙️ CONFIGURACIÓN GLOBAL Y DEBUG
# ================================
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

def debug_log(msg: str):
    if DEBUG:
        print(f"[DEBUG] {msg}")

# ================================
# 🧩 COMPATIBILIDAD CON RENDER
# ================================
def aplicar_nest_asyncio_si_es_necesario():
    """Permite compatibilidad entre Render y entornos locales."""
    try:
        import nest_asyncio
        loop = asyncio.get_event_loop()
        if "uvloop" not in str(type(loop)).lower():
            nest_asyncio.apply()
            debug_log("nest_asyncio aplicado correctamente (modo local).")
        else:
            debug_log("uvloop detectado, no se aplica nest_asyncio (modo Render).")
    except Exception as e:
        print(f"⚠️ No se aplicó nest_asyncio: {e}")

aplicar_nest_asyncio_si_es_necesario()

# ================================
# ⚙️ CONFIGURACIÓN DE ENTORNO
# ================================
URLS = {
    "satje": os.getenv("SATJE_URL", "https://satje.funcionjudicial.gob.ec/busquedaSentencias.aspx").strip(),
    "corte_constitucional": os.getenv("CORTE_CONSTITUCIONAL_URL", "http://buscador.corteconstitucional.gob.ec/buscador-externo/principal").strip(),
    # Se utiliza el buscador nuevo como URL principal de la Corte Nacional
    "corte_nacional": os.getenv("CORTE_NACIONAL_URL", "https://busquedasentencias.cortenacional.gob.ec/").strip(),
    "procesos_judiciales": os.getenv("PROCESOS_JUDICIALES_URL", "https://procesosjudiciales.funcionjudicial.gob.ec/busqueda").strip(),
    "juriscopio_base": os.getenv("JURISCOPIO_BASE", "https://buscador.corteconstitucional.gob.ec").strip(),
    "procesos_api": "https://api.funcionjudicial.gob.ec/EXPEL-CONSULTA-CAUSAS-SERVICE/api/consulta-causas",
    "procesos_api_clex": "https://api.funcionjudicial.gob.ec/EXPEL-CONSULTA-CAUSAS-CLEX-SERVICE/api/consulta-causas-clex",
    "procesos_resueltos_api": "https://api.funcionjudicial.gob.ec/MANTICORE-SERVICE/api/manticore/consulta",
}

PAGE_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS  = 35_000
MAX_ITEMS       = 10

# ================================
# Proxy opcional desde entorno
# ================================
def _proxy_config() -> Optional[dict]:
    """
    Construye la configuración de proxy si se definen:
    HTTP_PROXY/HTTPS_PROXY (server) y HTTP_PROXY_USER/HTTP_PROXY_PASS (auth opcional).
    """
    proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if not proxy:
        return None
    cfg = {"server": proxy}
    user = os.getenv("HTTP_PROXY_USER")
    pwd = os.getenv("HTTP_PROXY_PASS")
    if user:
        cfg["username"] = user
        if pwd:
            cfg["password"] = pwd
    return cfg

# ================================
# 🔧 UTILIDADES INTERNAS
# ================================
async def _first_selector(page, selectors: List[str]) -> Optional[str]:
    for sel in selectors:
        try:
            if await page.query_selector(sel):
                return sel
        except Exception:
            continue
    return None

async def _safe_inner_text(node, default="") -> str:
    try:
        txt = (await node.inner_text()).strip()
        return txt or default
    except Exception:
        return default

def _abs_url(base: str, href: str) -> str:
    try:
        return urljoin(base, href or "")
    except Exception:
        return href or ""

def _dedup(items: List[Dict[str, Any]], key: str = "url") -> List[Dict[str, Any]]:
    seen, out = set(), []
    for i in items:
        val = i.get(key)
        if val and val not in seen:
            seen.add(val)
            out.append(i)
    return out

def _norm_fecha(valor: Any) -> str:
    """
    Convierte timestamps en ms o strings a un formato ISO corto YYYY-MM-DD.
    """
    if valor is None:
        return ""
    try:
        # epoch en ms o s
        if isinstance(valor, (int, float)):
            if valor > 10_000_000_000:  # ms
                valor = valor / 1000.0
            return datetime.utcfromtimestamp(valor).strftime("%Y-%m-%d")
        if isinstance(valor, str):
            return valor.strip()
    except Exception:
        return ""
    return ""

def _headers_juriscopio(referer: str) -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": URLS["juriscopio_base"],
        "Referer": referer,
        "User-Agent": "Mozilla/5.0 (H&G Abogados IA)",
    }

def _post_juriscopio(url: str, body: Dict[str, Any], referer: str) -> Dict[str, Any]:
    encoded = base64.b64encode(json.dumps(body, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    payload = {"dato": encoded}
    resp = requests.post(url, json=payload, headers=_headers_juriscopio(referer), timeout=25)
    try:
        data = resp.json()
    except Exception:
        data = {"error": f"Respuesta no JSON (HTTP {resp.status_code})", "text": resp.text[:500]}
    if resp.status_code >= 400:
        raise RuntimeError(f"Juriscopio respondió {resp.status_code}: {data}")
    return data

def _pick(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return ""

async def _click_recaptcha_checkbox(page) -> bool:
    """
    Intenta clicar el checkbox de reCAPTCHA si está presente (no resuelve retos avanzados).
    """
    try:
        iframe = await page.wait_for_selector(
            "iframe[src*='recaptcha'], iframe[title*='reCAPTCHA']", timeout=5000
        )
    except Exception:
        return False

    try:
        frame = await iframe.content_frame()
        if not frame:
            return False
        debug_log("Intentando click en checkbox reCAPTCHA...")
        await frame.click("div.recaptcha-checkbox-border, span.recaptcha-checkbox", timeout=4000)
        try:
            await frame.wait_for_selector(
                "div.recaptcha-checkbox-checked, span[aria-checked='true']", timeout=3000
            )
            debug_log("reCAPTCHA marcado (checkbox en estado checked).")
        except Exception:
            debug_log("No se detectó estado 'checked' en reCAPTCHA (puede requerir reto adicional).")
        await page.wait_for_timeout(1200)
        return True
    except Exception:
        return False

# ================================
# 🔎 FUNCIONES DE BÚSQUEDA
# ================================
async def _buscar_satje(page, texto: str) -> List[Dict[str, Any]]:
    """SATJE – Función Judicial"""
    debug_log(f"Consultando SATJE con: {texto}")
    resultados = []
    await page.goto(URLS["satje"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, ["#txtBuscar", 'input[id*="Buscar"]'])
    b_sel = await _first_selector(page, ["#btnBuscar", 'button[id*="btnBuscar"]'])
    if not q_sel or not b_sel:
        return []

    await page.fill(q_sel, texto)
    await page.click(b_sel)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    nodes = await page.query_selector_all(".DataGridItemStyle, .card, tr, .resultado")
    for n in nodes[:MAX_ITEMS]:
        txt = await _safe_inner_text(n)
        for a in await n.query_selector_all("a"):
            href = await a.get_attribute("href")
            if href:
                resultados.append({
                    "fuente": "SATJE",
                    "titulo": txt.split("\n")[0][:140],
                    "descripcion": "Sentencia registrada en SATJE",
                    "url": _abs_url(page.url, href)
                })
    return _dedup(resultados)

async def _buscar_corte_constitucional(page, texto: str) -> List[Dict[str, Any]]:
    """Corte Constitucional - buscador externo"""
    debug_log(f"Consultando Corte Constitucional con: {texto}")
    resultados = []
    await page.goto(URLS["corte_constitucional"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    # Input principal y botón de búsqueda (ícono de lupa)
    q_sel = await _first_selector(page, [
        'input[placeholder*="Digite el texto"]',
        'input[placeholder*="Buscar"]',
        'input[name*="texto"]',
        'input[type="text"]'
    ])
    b_sel = await _first_selector(page, [
        'button:has-text("Buscar")',
        'button[aria-label*="Buscar"]',
        'button[type="submit"]',
        'button:has(svg)'
    ])
    if not q_sel or not b_sel:
        return []

    await page.fill(q_sel, texto[:250])
    await page.click(b_sel)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    # Tarjetas de resultado: anclas a detalles/PDF
    nodes = await page.query_selector_all("div, article, li, tr")
    for n in nodes[:MAX_ITEMS]:
        txt = await _safe_inner_text(n)
        for a in await n.query_selector_all("a"):
            href = await a.get_attribute("href")
            if href:
                resultados.append({
                    "fuente": "Corte Constitucional",
                    "titulo": txt.split("\n")[0][:140],
                    "descripcion": "Relatoría o sentencia Corte Constitucional",
                    "url": _abs_url(page.url, href)
                })
    return _dedup(resultados)

def _tipo_busqueda_corte_nacional(payload: Dict[str, Any]) -> str:
    """
    Determina el modo de búsqueda: aproximada (default) o por número de proceso.
    """
    modo = (payload.get("tipo_busqueda") or payload.get("modo") or "").lower()
    if "exact" in modo or "frase" in modo:
        return "exacta"
    if "proceso" in modo:
        return "numeroProceso"
    return "aproximada"


async def _buscar_corte_nacional(page, texto: str, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Corte Nacional - buscador nuevo (busquedasentencias.cortenacional.gob.ec)"""
    debug_log(f"Consultando Corte Nacional (nuevo) con: {texto}")
    resultados = []
    # Intento directo vía API pública (evita scraping)
    api_url = "https://api.funcionjudicial.gob.ec/BUSCADOR-SENTENCIAS-SERVICES/api/buscador-sentencias/query/sentencia/busqueda/buscarPorTipoBusqueda"
    tipo_busqueda = _tipo_busqueda_corte_nacional(payload or {})
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://busquedasentencias.cortenacional.gob.ec",
        "Referer": "https://busquedasentencias.cortenacional.gob.ec/",
        "User-Agent": "Mozilla/5.0 (compatible; H&G Abogados IA)"
    }
    recaptcha_token = os.getenv("CN_RECAPTCHA_TOKEN") or os.getenv("X_RECAPTCHA_TOKEN")
    if recaptcha_token:
        headers["X-reCAPTCHA-Token"] = recaptcha_token
    body = {
        "query": texto,
        "orden": "SCORE",
        "pageNumber": 0,
        "pageSize": MAX_ITEMS,
        "tipoBusqueda": tipo_busqueda,
        "subBusqueda": "",
        "sala": [],
        "juezPonente": []
    }
    try:
        resp = requests.post(api_url, json=body, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("content") or []
        for it in items[:MAX_ITEMS]:
            numero_proceso = (it.get("numeroProceso") or "").strip()
            juez = (it.get("juezPonente") or "").strip()
            sala = (it.get("nombreSala") or "").strip()
            fecha = (it.get("fechaProvidencia") or "").split("T")[0] if it.get("fechaProvidencia") else ""
            pdf_url = it.get("urlPdf")
            resumen_list = it.get("resumen") or []
            descripcion = " ".join(resumen_list) if resumen_list else (it.get("descripcion") or "")
            resultados.append({
                "fuente": "Corte Nacional de Justicia (API)",
                "titulo": numero_proceso or it.get("numeroResolucion") or "Sentencia Corte Nacional",
                "descripcion": descripcion[:400],
                "url": pdf_url or "",
                "pdf_url": pdf_url,
                "numero_proceso": numero_proceso,
                "juez": juez,
                "sala": sala,
                "fecha": fecha,
                "estado": it.get("nombreEstadoProceso"),
                "materia": it.get("nombreMateria"),
            })
        return _dedup(resultados)
    except Exception as e:
        debug_log(f"API Corte Nacional falló: {e}; se intentará scraping (puede fallar por captcha/spa).")
    base = URLS["corte_nacional"].rstrip("/")
    query = quote(texto[:50])
    tipo_busqueda = _tipo_busqueda_corte_nacional(payload or {})
    resultados_url = f"{base}/resultados?query={query}&tipoBusqueda={tipo_busqueda}"
    debug_log(f"Corte Nacional: navegando directo a resultados {resultados_url}")
    await page.goto(resultados_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_selector("app-resultado, a[href*='Proceso'], a[href*='proceso'], a[href*='.pdf'], .card, article, div.result-card", timeout=8000)
        if DEBUG:
            try:
                html_preview = (await page.content())[:1200]
                debug_log(f"Corte Nacional HTML preview: {html_preview}")
            except Exception:
                debug_log("Corte Nacional: no se pudo obtener HTML preview.")
    except PWTimeout:
        await page.wait_for_timeout(1500)

    # Extraer datos en el contexto de la página para capturar campos (proceso, juez, sala, fecha, pdf)
    try:
        raw_cards = await page.evaluate("""
        () => {
            const cards = Array.from(document.querySelectorAll(".resultado-item.card"));
            if (!cards.length) {
                // fallback a otras tarjetas genéricas
                return Array.from(document.querySelectorAll(".card.shadow-sm, .result-card, mat-card, div[role='listitem']")).map(c=>({cardHTML:c.innerHTML}));
            }
            return cards.map(card => {
                const q = (sel) => card.querySelector(sel);
                const qt = (sel) => {
                    const el = q(sel);
                    return el ? (el.textContent || "").trim() : "";
                };
                const qa = (sel) => {
                    const el = q(sel);
                    if (!el) return "";
                    return el.href || el.getAttribute("href") || "";
                };

                const numero = qt("strong.text-truncate, a[href*='Proceso'], a[href*='proceso']");
                const href = qa("a[href*='Proceso'], a[href*='proceso']");

                let pdfHref = qa("a[href$='.pdf'], a[href*='.pdf']");
                if (!pdfHref) {
                    const img = q("img[src*='pdf'], img[alt*='pdf']");
                    if (img) {
                        const a = img.closest("a");
                        if (a) pdfHref = a.href || a.getAttribute("href") || "";
                    }
                }

                const inner = card.innerText || card.textContent || "";
                const juezMatch = inner.match(/Juez\\/a:\\s*([^\\n]+)/i);
                const salaMatch = inner.match(/Sala:\\s*([^\\n]+)/i);
                const fechaMatch = inner.match(/\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+\\d{4}/);

                const descNode = q("p");
                const descripcion = descNode ? (descNode.textContent || "").trim() : inner.trim();

            return {
                numero,
                href,
                pdfHref,
                juez: juezMatch ? juezMatch[1].trim() : qt("span.text-secondary.text-truncate"),
                sala: salaMatch ? salaMatch[1].trim() : (qt("span.text-secondary.text-wrap") || ""),
                fecha: fechaMatch ? fechaMatch[0].trim() : "",
                descripcion
            };
        });
        }
        """)
    except Exception:
        raw_cards = []

    # Intento adicional: extracción directa de tarjetas reales (.resultado-item.card)
    try:
        raw_cards = await page.evaluate("""
        () => {
            const cards = Array.from(document.querySelectorAll(".resultado-item.card"));
            if (!cards.length) return [];
            return cards.map(card => {
                const q = sel => card.querySelector(sel);
                const qt = sel => {
                    const el = q(sel);
                    return el ? (el.textContent || "").trim() : "";
                };

                const numero = qt("strong.text-truncate, a[href*='Proceso'], a[href*='proceso']");
                const inner  = (card.innerText || card.textContent || "").replace(/\\s+/g, " ").trim();
                const juezMatch  = inner.match(/Juez\\/?a?:\\s*([^\\n]+)/i);
                const salaMatch  = inner.match(/Sala:\\s*([^\\n]+)/i);
                const fechaMatch = inner.match(/\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+\\d{4}/);
                const descNode = q("p");

                return {
                    numero,
                    href: "",
                    pdfHref: "",
                    juez: juezMatch ? juezMatch[1].trim() : qt("span.text-secondary.text-truncate"),
                    sala: salaMatch ? salaMatch[1].trim() : (qt("span.text-secondary.text-wrap") || ""),
                    fecha: fechaMatch ? fechaMatch[0].trim() : "",
                    descripcion: descNode ? (descNode.textContent || "").trim() : inner
                };
            });
        }
        """)
    except Exception:
        pass

    # Intento final: extraer directamente de .resultado-item.card sin fallback
    if not raw_cards:
        try:
            raw_cards = await page.evaluate("""
            () => {
                const cards = Array.from(document.querySelectorAll(".resultado-item.card"));
                if (!cards.length) return [];
                return cards.map(card => {
                    const q  = (sel) => card.querySelector(sel);
                    const qt = (sel) => {
                        const el = q(sel);
                        return el ? (el.textContent || "").trim() : "";
                    };
                    const numero = qt("strong.text-truncate, a[href*='Proceso'], a[href*='proceso']");
                    const inner  = (card.innerText || card.textContent || "").replace(/\\s+/g, " ").trim();
                    const juezMatch  = inner.match(/Juez\\/?a?:\\s*([^\\n]+)/i);
                    const salaMatch  = inner.match(/Sala:\\s*([^\\n]+)/i);
                    const fechaMatch = inner.match(/\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+\\d{4}/);
                    const descNode   = q("p");
                    return {
                        numero,
                        href: "",
                        pdfHref: "",
                        juez: juezMatch ? juezMatch[1].trim() : qt("span.text-secondary.text-truncate"),
                        sala: salaMatch ? salaMatch[1].trim() : (qt("span.text-secondary.text-wrap") || ""),
                        fecha: fechaMatch ? fechaMatch[0].trim() : "",
                        descripcion: descNode ? (descNode.textContent || "").trim() : inner
                    };
                });
            }
            """)
        except Exception:
            raw_cards = []

    if not raw_cards:
        try:
            body_txt = (await page.inner_text("body"))[:400]
            debug_log(f"Corte Nacional: sin nodos de resultado, body preview: {body_txt}")
        except Exception:
            debug_log("Corte Nacional: sin nodos de resultado y no se pudo leer body.")

    for rc in raw_cards:
        numero_proceso = (rc.get("numero") or "").strip()
        href = rc.get("href") or ""
        descripcion = rc.get("descripcion") or ""
        pdf_href = rc.get("pdfHref") or ""
        juez = (rc.get("juez") or "").strip()
        sala = (rc.get("sala") or "").strip()
        fecha = (rc.get("fecha") or "").strip()

        # Fallbacks por regex sobre la descripción
        import re
        if not numero_proceso:
            m = re.search(r"Nro\\s*Proceso\\s*([0-9]+)", descripcion, re.IGNORECASE)
            if m:
                numero_proceso = m.group(1)
            else:
                m2 = re.search(r"(\\d{7,})", descripcion)
                if m2:
                    numero_proceso = m2.group(1)

        if not juez:
            m = re.search(r"Juez/a:\\s*([^\\n]+)", descripcion, re.IGNORECASE)
            if m:
                juez = m.group(1).strip()
        if not sala:
            m = re.search(r"Sala:\\s*([^\\n]+)", descripcion, re.IGNORECASE)
            if m:
                sala = m.group(1).strip()
        if not fecha:
            m = re.search(r"(\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+\\d{4})", descripcion, re.IGNORECASE)
            if m:
                fecha = m.group(1).strip()

        resultados.append({
            "fuente": "Corte Nacional de Justicia (nuevo)",
            "titulo": (numero_proceso or descripcion.split("\\n")[0] if descripcion else "Sentencia Corte Nacional").strip()[:180],
            "descripcion": descripcion.split("\\n")[0][:400],
            "url": _abs_url(page.url, pdf_href or href or page.url),
            "pdf_url": _abs_url(page.url, pdf_href) if pdf_href else None,
            "numero_proceso": numero_proceso.strip(),
            "juez": juez,
            "sala": sala,
            "fecha": fecha
        })
    return _dedup(resultados)


async def _buscar_procesos_judiciales(page, texto: str) -> List[Dict[str, Any]]:
    """Buscador E-SATJE Procesos Judiciales vía API (evita captcha)."""
    debug_log(f"Consultando Procesos Judiciales (API) con: {texto}")
    resultados = []
    proxy_url = os.getenv("PROCESOS_PROXY_URL")
    if proxy_url:
        debug_log(f"Proxy Procesos Judiciales URL: {proxy_url}")
        try:
            resp = requests.post(proxy_url, json={"texto": texto}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            items = data if isinstance(data, list) else (data.get("content") or [])
            debug_log(f"Proxy Procesos Judiciales items: {len(items)}")
            for it in items[:MAX_ITEMS]:
                numero_proceso = (it.get("idJuicio") or "").strip()
                uid = numero_proceso or str(it.get("idIncidenteJudicatura") or it.get("idMovimientoJuicioIncidente") or it.get("idTablaReferencia") or f"tmp-{len(resultados)}")
                url_val = f"{proxy_url}?uid={uid}" if proxy_url else f"proxy://{uid}"
                fecha = (it.get("fechaActividad") or "").split(" ")[0] if it.get("fechaActividad") else ""
                titulo = (it.get("nombreProvidencia") or "").strip() or "Proceso judicial"
                descripcion = (it.get("texto") or "").strip()
                resultados.append({
                    "fuente": "Procesos Judiciales (proxy)",
                    "titulo": titulo[:180],
                    "descripcion": descripcion[:400],
                    "url": url_val or "",
                    "numero_proceso": numero_proceso,
                    "fecha": fecha,
                    "id_judicatura": it.get("idJudicatura"),
                    "estado": it.get("estado"),
                    "tabla_referencia": it.get("tablaReferencia"),
                    "id_incidente": it.get("idIncidenteJudicatura")
                })
            return _dedup(resultados)
        except Exception as e:
            debug_log(f"Proxy Procesos Judiciales falló: {e}; se intentará API directa.")

    api_url = "https://api.funcionjudicial.gob.ec/MANTICORE-SERVICE/api/manticore/consulta/coincidencias"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Accept-Language": "es-419,es;q=0.9",
        "Origin": "https://procesosjudiciales.funcionjudicial.gob.ec",
        "Referer": "https://procesosjudiciales.funcionjudicial.gob.ec/busqueda",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Sec-GPC": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    }
    cookie = os.getenv("PJ_COOKIE")
    if cookie:
        headers["Cookie"] = cookie

    recaptcha = os.getenv("PJ_RECAPTCHA_TOKEN") or os.getenv("X_RECAPTCHA_TOKEN") or "verdad"
    body = {
        "texto": texto,
        "recaptcha": recaptcha
    }
    params = {"page": 1, "size": MAX_ITEMS}

    try:
        resp = requests.post(api_url, json=body, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        items = resp.json() or []
        for it in items[:MAX_ITEMS]:
            numero_proceso = (it.get("idJuicio") or "").strip()
            uid = numero_proceso or str(it.get("idIncidenteJudicatura") or it.get("idMovimientoJuicioIncidente") or it.get("idTablaReferencia") or f"tmp-{len(resultados)}")
            url_val = f"https://procesosjudiciales.funcionjudicial.gob.ec/coincidencias?uid={uid}"
            fecha = (it.get("fechaActividad") or "").split(" ")[0] if it.get("fechaActividad") else ""
            titulo = (it.get("nombreProvidencia") or "").strip() or "Proceso judicial"
            descripcion = it.get("texto") or ""
            resultados.append({
                "fuente": "Procesos Judiciales (API)",
                "titulo": titulo[:180],
                "descripcion": descripcion[:400],
                "url": url_val,
                "numero_proceso": numero_proceso,
                "fecha": fecha,
                "id_judicatura": it.get("idJudicatura"),
                "estado": it.get("estado"),
                "tabla_referencia": it.get("tablaReferencia"),
                "id_incidente": it.get("idIncidenteJudicatura")
            })
        return _dedup(resultados)
    except Exception as e:
        debug_log(f"API Procesos Judiciales falló: {e}")
        return [{"error": f"No se pudo consultar Procesos Judiciales vía API: {e}", "nivel_consulta": "Procesos Judiciales"}]

# ================================
# 🚀 FUNCIÓN ASÍNCRONA PRINCIPAL
# ================================
async def _buscar_juris_async(texto: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not texto:
        return {"error": "Debe ingresar un texto de búsqueda."}

    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-setuid-sandbox",
        "--disable-web-security"
    ]
    proxy_cfg = _proxy_config()
    if proxy_cfg:
        debug_log(f"Usando proxy: {proxy_cfg.get('server')}")

    debug_log("Lanzando navegador Chromium para consultas judiciales...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args, proxy=proxy_cfg)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        resultados = []
        try:
            # Consulta secuencial y controlada
            for fuente, funcion in [
                ("SATJE", _buscar_satje),
                ("Corte Constitucional", _buscar_corte_constitucional),
                ("Corte Nacional de Justicia", lambda p, t=texto: _buscar_corte_nacional(p, t, payload)),
                ("Procesos Judiciales", _buscar_procesos_judiciales),
            ]:
                try:
                    res = await funcion(page, texto)
                    resultados.extend(res)
                except Exception as e:
                    resultados.append({
                        "fuente": fuente,
                        "error": f"No disponible: {e}"
                    })

            resultados = _dedup(resultados)
            return {
                "mensaje": f"Consulta completada para '{texto}'.",
                "nivel_consulta": "Jurisprudencia",
                "resultado": resultados[:MAX_ITEMS]
            }

        finally:
            await context.close()
            await browser.close()
            debug_log("Cierre limpio del navegador Chromium completado.")

# ================================
# ⚙️ UTILIDAD DE EJECUCIÓN BLOQUEANTE
# ================================
def _run_async_blocking(coro):
    """
    Ejecuta la corrutina en un bucle nuevo y aislado para evitar conflictos con uvloop/nest_asyncio.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)

# ================================
# 🌐 INTERFACES INDIVIDUALES
# ================================
async def _buscar_fuente_individual(func, texto: str, fuente: str) -> Dict[str, Any]:
    """
    Reutiliza la lógica de navegación para una sola fuente (evita duplicar browsers).
    """
    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-setuid-sandbox",
        "--disable-web-security"
    ]
    proxy_cfg = _proxy_config()
    resultados = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args, proxy=proxy_cfg)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)
        try:
            res = await func(page, texto)
            resultados.extend(res)
            resultados = _dedup(resultados)
            return {
                "mensaje": f"Consulta completada para '{texto}'.",
                "nivel_consulta": fuente,
                "resultado": resultados[:MAX_ITEMS]
            }
        finally:
            await context.close()
            await browser.close()
            debug_log("Cierre limpio del navegador Chromium (individual) completado.")

def consultar_corte_nacional(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("palabras_clave") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto válido para búsqueda.", "nivel_consulta": "Corte Nacional"}
    try:
        return _run_async_blocking(_buscar_fuente_individual(lambda p, t=texto: _buscar_corte_nacional(p, t, payload), texto, "Corte Nacional"))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {te}", "nivel_consulta": "Corte Nacional"}
    except Exception as e:
        return {"error": f"Error general al consultar Corte Nacional: {e}", "nivel_consulta": "Corte Nacional"}

def consultar_procesos_judiciales(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("palabras_clave") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto válido para búsqueda.", "nivel_consulta": "Procesos Judiciales"}
    try:
        return _run_async_blocking(_buscar_fuente_individual(_buscar_procesos_judiciales, texto, "Procesos Judiciales"))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {te}", "nivel_consulta": "Procesos Judiciales"}
    except Exception as e:
        return {"error": f"Error general al consultar Procesos Judiciales: {e}", "nivel_consulta": "Procesos Judiciales"}

# ================================
# 🧠 INTERFAZ PÚBLICA PARA FASTAPI
# ================================
def consultar_jurisprudencia(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("palabras_clave") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto válido para búsqueda."}

    try:
        return _run_async_blocking(_buscar_juris_async(texto, payload))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {te}", "nivel_consulta": "Jurisprudencia"}
    except Exception as e:
        return {"error": f"Error general al consultar jurisprudencia: {e}", "nivel_consulta": "Jurisprudencia"}

# ================================
# Juriscopio (API directa)
# ================================
def _paginacion_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    page = int(payload.get("page") or payload.get("pageNumber") or 1)
    size = int(payload.get("page_size") or payload.get("pageSize") or 20)
    return {"page": page, "pageSize": size, "total": 0, "contar": True}


def _map_causa_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    resultados = []
    for it in items:
        causa = it.get("causa") or {}
        h_text = " ".join(it.get("highlight", {}).get("textogeneral", []) or [])
        resultados.append({
            "fuente": "Juriscopio - Causas",
            "numero_caso": causa.get("numerocausa") or "",
            "fecha": _norm_fecha(causa.get("fechaingreso")),
            "juez": causa.get("nombrejuez") or causa.get("loginjuez") or "",
            "accion": causa.get("accion") or causa.get("tipoaccion") or "",
            "pdf_url": causa.get("urlauto"),
            "descripcion": causa.get("textogeneral") or h_text or "",
            "score": it.get("score"),
            "id_causa": causa.get("idcausa"),
            "id": causa.get("id"),
        })
    return resultados


def _map_sentencia_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    resultados = []
    for it in items:
        sentencia = it.get("sentencia") or it
        h_text = " ".join(it.get("highlight", {}).get("textogeneral", []) or [])
        numero_sentencia = _pick(sentencia, ["numeroSentencia", "numSentencia", "numerosentencia", "numero"])
        numero_causa = _pick(sentencia, ["numeroCausa", "numCausa", "numerocausa"])
        resultados.append({
            "fuente": "Juriscopio - Sentencias",
            "numero_sentencia": numero_sentencia,
            "numero_caso": numero_causa,
            "fecha": _norm_fecha(_pick(sentencia, ["fechaDecision", "fechaNotificacion", "fecha", "fechaIngreso"])),
            "juez": _pick(sentencia, ["nombrejuez", "juez", "juezPonente", "loginjuez"]),
            "materia": sentencia.get("materia") or "",
            "decision": _pick(sentencia, ["decision", "resolucion"]),
            "pdf_url": _pick(sentencia, ["urlPdf", "urlpdf", "urlSentencia", "urlauto"]),
            "descripcion": sentencia.get("textogeneral") or h_text or sentencia.get("descripcion") or "",
            "score": it.get("score"),
        })
    return resultados


def _map_seleccion_items(items: List[Dict[str, Any]], etiqueta: str) -> List[Dict[str, Any]]:
    resultados = []
    for it in items:
        nodo = it.get("causa") or it.get("auto") or it.get("seleccion") or it
        h_text = " ".join(it.get("highlight", {}).get("textogeneral", []) or [])
        resultados.append({
            "fuente": f"Juriscopio - {etiqueta}",
            "numero_caso": _pick(nodo, ["numeroCausa", "numerocausa"]),
            "numero_caso_auto": _pick(nodo, ["numeroCausaAuto", "numerocausaauto"]),
            "caso_judicatura": nodo.get("casoJudicatura") or "",
            "fecha": _norm_fecha(_pick(nodo, ["fechaIngreso", "fechaingreso", "fecha"])),
            "juez": _pick(nodo, ["nombrejuez", "juez"]),
            "pronunciamiento": _pick(nodo, ["pronunciamientoDelInferior", "pronunciamientoInferior", "pronunciamiento"]),
            "estado": _pick(nodo, ["estadoProcesal", "estado", "estadoProceso"]),
            "pdf_url": _pick(nodo, ["urlPdf", "urlauto", "urlAuto", "url"]),
            "descripcion": nodo.get("textogeneral") or h_text or "",
            "score": it.get("score"),
        })
    return resultados


def _map_admision_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    resultados = []
    for it in items:
        nodo = it.get("admision") or it
        h_text = " ".join(it.get("highlight", {}).get("textogeneral", []) or [])
        resultados.append({
            "fuente": "Juriscopio - Admisión",
            "numero_caso": _pick(nodo, ["numeroCausa", "numerocausa"]),
            "fecha": _norm_fecha(_pick(nodo, ["fechaDecision", "fecha", "fechaIngreso"])),
            "juez": _pick(nodo, ["juez", "nombrejuez"]),
            "tipo_accion": _pick(nodo, ["tipoaccion", "tipoAccion"]),
            "decision": nodo.get("decision") or "",
            "pdf_url": _pick(nodo, ["urlPdf", "url"]),
            "descripcion": nodo.get("textogeneral") or h_text or "",
            "score": it.get("score"),
        })
    return resultados


def _build_causa_payload(texto: str, numero: str, modo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    base = {
        "textoSubconsulta": "",
        "legitimados": "",
        "paginacion": _paginacion_from_payload(payload),
        "textoCausa": texto or numero,
        "contexto": None,
        "accion": None,
        "juez": None,
        "jueces": [],
        "tipoAcciones": None,
        "idProvincia": "",
        "provincia": None,
        "fechaDesde": None,
        "fechaHasta": None,
        "sort": payload.get("sort", "relevancia"),
        "porFraseExacta": bool(payload.get("por_frase_exacta", False)),
        "opcionBusqueda": 3,
        "contextoSearch": None
    }
    if modo == "numero":
        base["textoCausa"] = numero or texto
        base["contexto"] = "CAUSA"
        base["opcionBusqueda"] = 4
    elif modo == "judicatura":
        base["textoCausa"] = numero or texto
        base["contexto"] = "CAUSA"
        base["opcionBusqueda"] = 5
    else:
        base["opcionBusqueda"] = 3
        base["porFraseExacta"] = bool(payload.get("por_frase_exacta", False))
    return base


def _build_sentencia_payload(texto: str, numero: str, modo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    base = {
        "numSentencia": "",
        "numeroCausa": "",
        "textoSentencia": "",
        "motivo": "",
        "metadata": "",
        "subBusqueda": "",
        "tipoLegitimado": 0,
        "legitimados": "",
        "tipoAcciones": [],
        "materias": [],
        "intereses": [],
        "decisiones": [],
        "jueces": [],
        "derechoDemandado": [],
        "derechosTratado": [],
        "derechosVulnerado": [],
        "temaEspecificos": [],
        "conceptos": [],
        "fechaNotificacion": "",
        "fechaDecision": "",
        "sort": payload.get("sort", "relevancia"),
        "precedenteAprobado": "",
        "precedentePropuesto": "",
        "tipoNormas": [],
        "asuntos": [],
        "analisisMerito": "",
        "novedad": "",
        "merito": "",
        "paginacion": _paginacion_from_payload(payload)
    }
    if modo == "numero_sentencia":
        base["numSentencia"] = numero or texto
        base["sort"] = payload.get("sort", "desc")
    elif modo == "numero_caso":
        base["numeroCausa"] = numero or texto
        base["sort"] = payload.get("sort", "desc")
    else:
        base["textoSentencia"] = texto
    return base


def _build_seleccion_payload(tipo: str, texto: str, numero: str, modo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    base = {
        "textoGeneral": "",
        "numeroCausa": "",
        "numeroCausaAuto": "",
        "sort": payload.get("sort", "relevancia"),
        "paginacion": _paginacion_from_payload(payload),
        "subBusqueda": "",
        "textoAuto": "",
        "tipoAcciones": [],
        "jueces": [],
        "derechoDemandado": [],
        "derechosTratado": [],
        "derechosVulnerado": [],
        "juridico": [],
        "pronunciamientos": [],
        "casoJudicatura": "",
        "fechaIngreso": "",
        "legitimados": "",
        "gruposAtencion": [],
        "estadosProcesal": [],
        "contexto": [],
    }
    if tipo == "autos":
        if modo == "numero":
            base["numeroCausaAuto"] = numero or texto
            base["contexto"] = [1]
            base["sort"] = payload.get("sort", "desc")
        else:
            base["textoAuto"] = texto
            base["contexto"] = [2]
    else:
        if modo == "numero":
            base["numeroCausa"] = numero or texto
            base["contexto"] = [1]
            base["sort"] = payload.get("sort", "desc")
        elif modo == "judicatura":
            base["casoJudicatura"] = numero or texto
        else:
            base["textoGeneral"] = texto
    return base


def _build_admision_payload(texto: str, numero: str, modo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    base = {
        "textoGeneral": texto if modo == "texto" else "",
        "numeroCausa": numero if modo == "numero" else "",
        "sort": payload.get("sort", "relevancia" if modo == "texto" else "desc"),
        "paginacion": _paginacion_from_payload(payload),
        "subBusqueda": "",
        "tipoAcciones": payload.get("tipoAcciones") or [],
        "decisiones": payload.get("decisiones") or [],
        "formaTerminacion": payload.get("formaTerminacion") or [],
        "resolucion": payload.get("resolucion") or [],
        "jueces": payload.get("jueces") or [],
        "fechaDecision": payload.get("fechaDecision") or "",
        "legitimados": payload.get("legitimados") or "",
    }
    return base


def _buscar_juriscopio_http(payload: Dict[str, Any]) -> Dict[str, Any]:
    seccion = (payload.get("seccion") or payload.get("tab") or "causas").lower()
    modo = (payload.get("modo") or payload.get("tipo") or "texto").lower()
    texto = (payload.get("texto") or payload.get("query") or payload.get("texto_general") or "").strip()
    numero = (payload.get("numero") or payload.get("numero_caso") or payload.get("numSentencia") or "").strip()

    base_url = URLS["juriscopio_base"].rstrip("/")
    referer_base = f"{base_url}/buscador-externo/principal"

    if seccion in ("causa", "causas", "sentencias/causas"):
        body = _build_causa_payload(texto, numero, modo, payload)
        url = f"{base_url}/buscador-causa-juridico/rest/api/causa/buscar"
        referer = f"{base_url}/buscador-externo/causa/resultado"
        parser = _map_causa_items
        etiqueta = "Causas"
    elif seccion in ("sentencia", "sentencias"):
        body = _build_sentencia_payload(texto, numero, modo, payload)
        url = f"{base_url}/buscador-externo/rest/api/sentencia/100_BUSCR_SNTNCIA"
        referer = f"{referer_base}/resultadoSentencia"
        parser = _map_sentencia_items
        etiqueta = "Sentencias"
    elif seccion in ("seleccion_autos", "autos_seleccion", "autos"):
        body = _build_seleccion_payload("autos", texto, numero, modo, payload)
        url = f"{base_url}/buscador-seleccion/rest/api/seleccion/100_BUSCR_SELECCION"
        referer = f"{referer_base}/resultadoSeleccion"
        parser = lambda items: _map_seleccion_items(items, "Autos de selección")
        etiqueta = "Selección - Autos"
    elif seccion in ("seleccion_casos", "casos_ingresados", "seleccion"):
        body = _build_seleccion_payload("casos", texto, numero, modo, payload)
        url = f"{base_url}/buscador-seleccion/rest/api/seleccion/100_BUSCR_SELECCION"
        referer = f"{referer_base}/resultadoSeleccion"
        parser = lambda items: _map_seleccion_items(items, "Casos ingresados a selección")
        etiqueta = "Selección - Casos"
    elif seccion in ("admision", "admisión"):
        body = _build_admision_payload(texto, numero, "numero" if modo.startswith("numero") else "texto" if modo.startswith("texto") else modo, payload)
        url = f"{base_url}/buscador-admision/rest/api/admision/100_BUSCR_ADMISION"
        referer = f"{referer_base}/resultadoAdmision"
        parser = _map_admision_items
        etiqueta = "Admisión"
    else:
        return {"error": f"Sección Juriscopio desconocida: {seccion}", "nivel_consulta": "Juriscopio"}

    try:
        data = _post_juriscopio(url, body, referer)
        items = data.get("dato") or []
        parsed = parser(items)
        total = data.get("totalFilas", len(parsed))
        return {
            "mensaje": data.get("mensaje", f"Consulta Juriscopio completada ({etiqueta})."),
            "nivel_consulta": "Juriscopio",
            "seccion": etiqueta,
            "total": total,
            "resultado": parsed[:MAX_ITEMS]
        }
    except Exception as e:
        return {"error": f"Juriscopio no disponible: {e}", "nivel_consulta": "Juriscopio", "seccion": seccion}


def consultar_juriscopio(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("query") or payload.get("texto_general") or "").strip()
    seccion = (payload.get("seccion") or payload.get("tab") or "causas").lower()
    if not texto and seccion not in ("admision", "admisión") and not payload.get("numero"):
        return {"error": "Debe proporcionar un texto o número para la consulta.", "nivel_consulta": "Juriscopio"}
    try:
        return _buscar_juriscopio_http(payload)
    except Exception as e:
        return {"error": f"Error general al consultar Juriscopio: {e}", "nivel_consulta": "Juriscopio"}


# ============================================================
# Procesos Judiciales - Búsqueda avanzada (API directa)
# ============================================================
def _headers_procesos_api() -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Accept-Language": "es-419,es;q=0.9",
        "Origin": "https://procesosjudiciales.funcionjudicial.gob.ec",
        "Referer": "https://procesosjudiciales.funcionjudicial.gob.ec/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, como Gecko) Chrome/143.0.0.0 Safari/537.36",
    }


def _buscar_causas_avanzado(filtros: Dict[str, Any], page: int = 1, size: int = 10) -> Dict[str, Any]:
    body = {
        "actor": {
            "cedulaActor": filtros.get("cedula_actor", ""),
            "nombreActor": filtros.get("nombre_actor", ""),
        },
        "demandado": {
            "cedulaDemandado": filtros.get("cedula_demandado", ""),
            "nombreDemandado": filtros.get("nombre_demandado", ""),
        },
        "first": 1,
        "numeroCausa": filtros.get("numero_causa", ""),
        "numeroFiscalia": filtros.get("numero_fiscalia", ""),
        "pageSize": size,
        "provincia": filtros.get("provincia", ""),
        "recaptcha": filtros.get("recaptcha") or os.getenv("PJ_RECAPTCHA_TOKEN") or "verdad",
    }
    headers = _headers_procesos_api()
    cookie = os.getenv("PJ_COOKIE")
    if cookie:
        headers["Cookie"] = cookie

    url = f"{URLS['procesos_api']}/informacion/buscarCausas"
    params = {"page": page, "size": size}
    resp = requests.post(url, json=body, params=params, headers=headers, timeout=25)
    resp.raise_for_status()
    items = resp.json() or []
    mapped = []
    for it in items:
        mapped.append(
            {
                "id": it.get("id"),
                "idJuicio": it.get("idJuicio"),
                "numero_causa": it.get("idJuicio"),
                "estado": it.get("estadoActual"),
                "materia": it.get("nombreMateria"),
                "tipo_accion": it.get("nombreTipoAccion"),
                "delito": it.get("nombreDelito"),
                "fecha_ingreso": _norm_fecha(it.get("fechaIngreso")),
                "tiene_documento": it.get("iedocumentoAdjunto"),
            }
        )
    return {"resultado": mapped}


def _get_informacion_juicio(id_juicio: str) -> Dict[str, Any]:
    headers = _headers_procesos_api()
    cookie = os.getenv("PJ_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    url = f"{URLS['procesos_api']}/informacion/getInformacionJuicio/{id_juicio}"
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.json() or {}


def _get_incidente_judicatura(id_juicio: str) -> List[Dict[str, Any]]:
    headers = _headers_procesos_api()
    cookie = os.getenv("PJ_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    url = f"{URLS['procesos_api_clex']}/informacion/getIncidenteJudicatura/{id_juicio}"
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.json() or []


def _get_actuaciones(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    headers = _headers_procesos_api()
    cookie = os.getenv("PJ_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    url = f"{URLS['procesos_api']}/informacion/actuacionesJudiciales"
    resp = requests.post(url, json=payload, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.json() or []


def _existe_ingreso_directo(id_juicio: str, id_movimiento: int) -> Dict[str, Any]:
    headers = _headers_procesos_api()
    cookie = os.getenv("PJ_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    url = f"{URLS['procesos_api_clex']}/informacion/existeIngresoDirecto"
    body = {"idJuicio": id_juicio, "idMovimientoJuicioIncidente": id_movimiento}
    resp = requests.post(url, json=body, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json() or {}


def consultar_procesos_avanzada(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Búsqueda avanzada en procesosjudiciales.funcionjudicial.gob.ec (API directa).
    Campos: numero_causa, cedula_actor, nombre_actor, cedula_demandado, nombre_demandado,
    numero_fiscalia, provincia, recaptcha (por defecto 'verdad').
    Opciones:
      - detalle: True para traer informacion + incidencias.
      - actuaciones: True para traer actuaciones (usa primer incidente).
      - ingreso_directo: True para consultar existeIngresoDirecto (usa primer incidente).
    """
    try:
        page = int(payload.get("page") or 1)
        size = int(payload.get("size") or 10)
    except Exception:
        page, size = 1, 10

    try:
        res_busqueda = _buscar_causas_avanzado(payload, page, size)
    except Exception as e:
        return {"error": f"No se pudo buscar causas (avanzada): {e}"}

    if not payload.get("detalle"):
        return res_busqueda

    id_juicio = payload.get("idJuicio") or payload.get("id_juicio") or payload.get("numero_causa")
    if not id_juicio:
        return {**res_busqueda, "warning": "Para detalle envíe idJuicio o numero_causa"}

    detalle: Dict[str, Any] = {}
    try:
        detalle["informacion"] = _get_informacion_juicio(id_juicio)
    except Exception as e:
        detalle["informacion_error"] = str(e)
    try:
        incidencias = _get_incidente_judicatura(id_juicio)
        detalle["incidencias"] = incidencias
        if payload.get("actuaciones") and incidencias:
            inc = incidencias[0]
            act_payload = {
                "aplicativo": "web",
                "idIncidenteJudicatura": inc.get("idIncidenteJudicatura"),
                "idJudicatura": inc.get("idJudicatura"),
                "idJuicio": id_juicio,
                "idMovimientoJuicioIncidente": inc.get("idMovimientoJuicioIncidente"),
                "incidente": inc.get("incidente") or 1,
                "nombreJudicatura": inc.get("nombreJudicatura"),
            }
            try:
                detalle["actuaciones"] = _get_actuaciones(act_payload)
            except Exception as e:
                detalle["actuaciones_error"] = str(e)
        if payload.get("ingreso_directo") and incidencias:
            inc = incidencias[0]
            try:
                detalle["ingreso_directo"] = _existe_ingreso_directo(id_juicio, inc.get("idMovimientoJuicioIncidente"))
            except Exception as e:
                detalle["ingreso_directo_error"] = str(e)
    except Exception as e:
        detalle["incidencias_error"] = str(e)

    return {**res_busqueda, "detalle": detalle}


# ============================================================
# Procesos resueltos por juez (API Manticore)
# ============================================================
def consultar_procesos_resueltos(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Consulta procesos resueltos por juez.
    Campos:
      - identificacion_juez (str) o nombre_juez (si el backend lo acepta, aquí usamos identificación)
      - id_materia (int) o lista idMateria (por defecto [1])
      - fechaInicio, fechaFin, idProvincia opcionales
    """
    headers = _headers_procesos_api()
    cookie = os.getenv("PJ_COOKIE")
    if cookie:
        headers["Cookie"] = cookie

    ident = payload.get("identificacion_juez") or payload.get("identificacionJuez") or ""
    materia = payload.get("id_materia") or payload.get("idMateria") or [1]
    if isinstance(materia, int):
        materia = [materia]
    body = {
        "resultadoSearch": {
            "idMateria": materia or [1],
            "identificacionJuez": ident,
            "fechaInicio": payload.get("fechaInicio") or "",
            "fechaFin": payload.get("fechaFin") or "",
            "idProvincia": payload.get("idProvincia") or "",
        },
        "idMateria": materia or [1],
        "idProvincia": payload.get("idProvincia") or "",
        "identificacionJuez": ident,
    }
    page = int(payload.get("page") or 1)
    size = int(payload.get("size") or 10)
    params = {"page": page, "size": size}

    url = f"{URLS['procesos_resueltos_api']}/procesos-judiciales-resueltos"
    try:
        resp = requests.post(url, json=body, params=params, headers=headers, timeout=25)
        resp.raise_for_status()
        data = resp.json() or {}
        items = data.get("resultadoProcesosResueltos") or []
        mapped = []
        for it in items:
            mapped.append(
                {
                    "idJuicio": it.get("idJuicio"),
                    "fecha_ingreso": it.get("fechaIngreso"),
                    "delito": it.get("nombreDelito"),
                    "estado": it.get("estadoActual"),
                }
            )
        return {"total": data.get("totalRegistros"), "resultado": mapped}
    except Exception as e:
        return {"error": f"No se pudo consultar procesos resueltos: {e}"}


def consultar_incidente_judicatura(id_incidente: str) -> Dict[str, Any]:
    """
    Consulta detalle de incidentes/litigantes para un incidente dado (endpoint getIncidenteJudicatura/{id})
    """
    headers = _headers_procesos_api()
    cookie = os.getenv("PJ_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    url = f"{URLS['procesos_api_clex']}/informacion/getIncidenteJudicatura/{id_incidente}"
    try:
        resp = requests.get(url, headers=headers, timeout=25)
        resp.raise_for_status()
        return resp.json() or {}
    except Exception as e:
        return {"error": f"No se pudo obtener incidenteJudicatura {id_incidente}: {e}"}
