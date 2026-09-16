"""
pedidosya_api.py — PedidosYa Market, tienda Nuñez (vendor 356102)
-----------------------------------------------------------------------
Puerto del motor "requests" probado en producción en el repo
ramiro2004mazur-coder/pedidosya-nunez (scraper/scraper.py + common.py):
corre 1x/dia desde una Mac con IP residencial y funciona sin navegador.

PedidosYa (PerimeterX) puede devolver 403 a este motor, tanto desde IPs
de datacenter como a veces desde IP residencial. Si eso pasa acá
también, hay que evaluar un motor con navegador real (Playwright +
stealth, canal Chrome, headless=False) como el que usa ese mismo repo
en scraper/scraper_playwright.py — pero probado en este proyecto el
requests puro ya alcanzó a pasar el bloqueo.
"""

import time
from datetime import datetime

import pandas as pd
import requests

# --- CONFIGURACIÓN (igual a scraper/common.py del repo pedidosya-nunez) ---
BASE_PEDIDOSYA = "https://www.pedidosya.com.ar/groceries/web/v1"
HOME_PEDIDOSYA = "https://www.pedidosya.com.ar/"
VENDOR_ID_PEDIDOSYA = "356102"  # PedidosYa Market - Nuñez
KEYWORD_PEDIDOSYA = "cerveza"
CADENA_PEDIDOSYA = "Pedidos Ya"  # con espacio: sobrevive el .str.title() que aplica main.py
TIPO_CADENA_PEDIDOSYA = "Last Millers"
DESCUENTO_MAX_VALIDO = 95  # >= a esto se descarta como error de carga de la API

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

COLUMNAS_ORDENADAS = [
    "Tipo de Cadena", "Fecha extracción", "Cadena", "Sucursal", "NODO", "EAN",
    "Descripcion", "Marca", "Precio Fleje", "Precio Dinamizado", "Promocion Desc",
    "Inicio Promo", "Fin Promo"
]


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.pedidosya.com.ar/",
        "Origin": "https://www.pedidosya.com.ar",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "sec-ch-ua": '"Chromium";v="126", "Not.A/Brand";v="24", "Google Chrome";v="126"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "X-PeYa-Application-Id": "web",
        "X-PeYa-Client": "web",
    })
    try:
        s.get(HOME_PEDIDOSYA, timeout=20)
        time.sleep(0.5)
    except Exception:
        pass
    return s


def _get_categories(s, vendor_id):
    r = s.get(f"{BASE_PEDIDOSYA}/vendors/{vendor_id}/categories", timeout=20)
    r.raise_for_status()
    out = []

    def walk(cats, parent=None):
        for c in cats:
            out.append({"id": c["id"], "name": c.get("name", ""), "parent": parent})
            if c.get("children"):
                walk(c["children"], c.get("name"))

    walk(r.json().get("categories", []))
    return out


def _get_products(s, vendor_id, category_id, limit=50, max_pages=30):
    items = []
    for page in range(max_pages):
        r = s.get(
            f"{BASE_PEDIDOSYA}/vendors/{vendor_id}/products",
            params={"categoryId": category_id, "limit": limit, "page": page},
            timeout=20,
        )
        r.raise_for_status()
        d = r.json()
        items += d.get("items", [])
        if d.get("lastPage") or not d.get("items"):
            break
        time.sleep(0.4)
    return items


def _get_all_beers(s, vendor_id, keyword):
    cats = _get_categories(s, vendor_id)
    target = [c for c in cats if keyword.lower() in (c["name"] or "").lower()]
    by_id = {}
    for c in target:
        for it in _get_products(s, vendor_id, c["id"]):
            by_id[str(it["id"])] = it
    return list(by_id.values())


def _calcular_precio_y_promo(producto):
    """
    Igual a to_row() de common.py del repo pedidosya-nunez: PedidosYa no
    tacha el precio para promos "llevá N pagá M" ni "2da unidad al X%dto"
    (a diferencia de un %OFF directo, que sí viene con beforePrice > price)
    hay que leerlas de 'campaigns'. Un producto puede traer varias
    campaigns a la vez -confirmado el caso real de Quilmes Clásica, que se
    leía como "20%" cuando el sitio aplicaba un 3x2 (33% efectivo)- así
    que se evalúan todas y se toma la de mayor descuento efectivo.
    """
    pr = producto.get("pricing") or {}
    precio = pr.get("price")
    fleje = pr.get("beforePrice") or precio

    candidatos = []  # (descuento_pct, precio_final, promo_nominal)
    for c in (producto.get("campaigns") or []):
        cfg = c.get("configuration") or {}
        ctype = c.get("type")
        cfg_type = cfg.get("type")
        tag = c.get("tag") or ""

        if ctype == "percentageDiscount" and cfg_type == "PERCENTAGE" and cfg.get("value"):
            d = int(round(cfg["value"]))
            candidatos.append((d, precio, tag or f"{d}%"))
            continue

        if cfg.get("maxRedemption") is not None:
            continue

        if ctype == "multi-buy" and cfg_type == "free_item" and cfg.get("take") and fleje:
            take, pay = cfg["take"], cfg.get("pay") or 0
            frac = 1 - pay / take
            d = int(round(frac * 100))
            candidatos.append((d, round(fleje * (1 - frac), 2), tag or f"{take}x{pay}"))
            continue

        if (ctype == "sameItemBundle" and cfg_type == "percentage"
                and cfg.get("take") and cfg.get("value") and fleje):
            take, pay, value = cfg["take"], cfg.get("pay") or 1, cfg["value"]
            frac = (pay / take) * (value / 100)
            d = int(round(frac * 100))
            candidatos.append((d, round(fleje * (1 - frac), 2), tag or f"{pay} ud. al {value}% dto"))
            continue

    d_final, precio_final, promo_nominal = 0, precio, ""
    if candidatos:
        d_final, precio_final, promo_nominal = max(candidatos, key=lambda x: x[0])
    elif fleje and precio and fleje > precio:
        d_final = int(round((1 - precio / fleje) * 100))
        promo_nominal = f"{d_final}%"

    # Descuentos >=95% son placeholders/errores de carga de la API (nunca
    # hay cerveza gratis o casi gratis) — se ignoran y se deja el precio
    # de lista, igual que el guard ya validado en el scraper de Rappi.
    if d_final >= DESCUENTO_MAX_VALIDO:
        precio_final, promo_nominal = fleje, ""

    return fleje, precio_final, promo_nominal


def _producto_a_fila(producto, nombre_suc, nodo):
    fleje, precio, promo_nominal = _calcular_precio_y_promo(producto)
    return {
        "Tipo de Cadena": TIPO_CADENA_PEDIDOSYA,
        "Fecha extracción": datetime.now().strftime("%d/%m/%Y"),
        "Cadena": CADENA_PEDIDOSYA,
        "Sucursal": nombre_suc,
        "NODO": nodo,
        "EAN": producto.get("gtin") or "",
        "Descripcion": producto.get("name", ""),
        "Marca": producto.get("defaultBrandName", ""),
        "Precio Fleje": fleje,
        "Precio Dinamizado": precio,
        "Promocion Desc": promo_nominal,
        # PedidosYa no expone fecha de inicio/fin de promo en este endpoint.
        "Inicio Promo": "",
        "Fin Promo": "",
    }


def fetch_and_process_pedidosya_prices(nombre_suc, nodo, provincia, status_box, progress_bar):
    """
    Firma idéntica a toledo_api/libertad_api para enchufar directo en
    main.py. Devuelve un DataFrame con las columnas finales ya armadas.
    """
    status_box.info(f"🚀 Procesando PedidosYa: {nombre_suc} (vía requests)...")

    try:
        s = _session()
        productos = _get_all_beers(s, VENDOR_ID_PEDIDOSYA, KEYWORD_PEDIDOSYA)
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        status_box.error(
            f"❌ PedidosYa: error HTTP {code}. Si persiste, puede que haya que "
            f"pasar a un motor con navegador real (ver scraper_playwright.py "
            f"del repo pedidosya-nunez)."
        )
        return pd.DataFrame()
    except requests.RequestException as e:
        status_box.error(f"❌ PedidosYa: error de red: {e}")
        return pd.DataFrame()

    if not productos:
        status_box.warning(f"⚠️ PedidosYa devolvió 0 productos para {nombre_suc}.")
        return pd.DataFrame()

    df = pd.DataFrame([_producto_a_fila(p, nombre_suc, nodo) for p in productos])
    progress_bar.progress(1.0, text=f"PedidosYa {nombre_suc}: Finalizado.")
    return df.reindex(columns=COLUMNAS_ORDENADAS)
