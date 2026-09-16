"""
rappi_api.py — Rappi Turbo, tienda Nuñez / Monroe (store_id 166964)
-----------------------------------------------------------------------
Puerto del scraper probado en producción en el repo
ramiro2004mazur-coder/rappi-nunez (scraper/scrape.py).

Usa Playwright (headless=True alcanza, a diferencia de PedidosYa esta
tienda es SSR pública y no hace falta navegador visible ni stealth). La
carga inicial de cada subcategoría trae ~24 productos; el resto se
consigue clickeando "Ver más" y capturando las respuestas de red reales
del endpoint interno dynamic/context/content (requiere un device id que
genera el propio navegador, no se puede replicar solo con requests).
"""

import re
import time
from datetime import datetime

import pandas as pd
from playwright.sync_api import sync_playwright

BASE_RAPPI = "https://www.rappi.com.ar"
STORE_ID_RAPPI = 166964  # Belgrano 1 / Monroe 1616 ("Nuñez")
CATEGORY_SLUG_RAPPI = "cervezas"
MAX_VER_MAS_CLICKS = 25
CADENA_RAPPI = "Rappi"
TIPO_CADENA_RAPPI = "Last Millers"
DESCUENTO_MAX_VALIDO = 0.95  # >= a esto se descarta como error de carga de la API

PACK_NAME_RE = re.compile(r"^\s*\d+\s*x\s+|pack|combo|sixpack|six\s*pack", re.I)

# Respaldo para productos sin "trademark" en el JSON de Rappi. Orden
# importa: patrones mas especificos primero.
NAME_BRAND_PATTERNS = [
    ("Salta Cautiva", r"salta\s+cautiva"), ("Quilmes", r"quilmes"),
    ("Stella Artois", r"stella\s*artois"), ("Budweiser", r"budweiser"),
    ("Corona", r"corona"), ("Michelob Ultra", r"michelob"),
    ("Patagonia", r"patagonia"), ("Andes Origen", r"andes\s*origen"),
    ("Andes", r"andes"), ("Brahma", r"brahma"), ("Heineken", r"heineken"),
    ("Amstel", r"amstel"), ("Schneider", r"schneider"), ("Imperial", r"imperial"),
    ("Salta", r"\bsalta\b"), ("Kunstmann", r"kunstmann"), ("Antares", r"antares"),
    ("Pampa", r"pampa"), ("Rabieta", r"rabieta"), ("Estrella Galicia", r"estrella\s*galicia"),
    ("Estrella Damm", r"estrella\s*damm"), ("Grolsch", r"grolsch"),
    ("Guinness", r"guinness|guinnes"), ("Bitburger", r"bitburger"),
    ("Kostritzer", r"k[oö]stritzer"), ("Warsteiner", r"warsteiner"),
    ("Peroni", r"peroni"), ("Miller", r"miller"), ("Blue Moon", r"blue\s*moon"),
    ("Asahi", r"asahi"), ("1890", r"\b1890\b"), ("Temple", r"\btemple\b"),
    ("Goose Island", r"goose\s*island"), ("Starberg", r"starberg"),
    ("Santa Fe", r"santa\s*fe"), ("Sol", r"\bsol\b"),
]

COLUMNAS_ORDENADAS = [
    "Tipo de Cadena", "Fecha extracción", "Cadena", "Sucursal", "NODO", "EAN",
    "Descripcion", "Marca", "Precio Fleje", "Precio Dinamizado", "Promocion Desc",
    "Inicio Promo", "Fin Promo"
]


def _marca_de(product):
    tm = (product.get("trademark") or "").strip()
    if tm:
        return tm
    nombre = (product.get("name") or "").lower()
    for marca, pattern in NAME_BRAND_PATTERNS:
        if re.search(pattern, nombre):
            return marca
    return ""


def _slugify(text):
    text = text.lower()
    for a, b in {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}.items():
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _es_pack(product, attrs):
    pack_size = (attrs.get("pack_size") or "").strip().lower()
    if pack_size:
        return pack_size not in ("x1", "1", "")
    return bool(PACK_NAME_RE.search(product.get("name") or ""))


def _producto_a_fila(p, nombre_suc, nodo):
    attrs = p.get("attributes") or {}
    if _es_pack(p, attrs):
        return None

    descripcion = (p.get("name") or "").strip()
    fleje = p.get("real_price")
    precio = p.get("price")
    if not descripcion or precio is None:
        return None
    if fleje is None:
        fleje = precio

    discount = p.get("discount")
    if discount is None:
        discount = round(max(1 - (precio / fleje if fleje else 1), 0.0), 4)
    if discount >= DESCUENTO_MAX_VALIDO:
        # "100% OFF" (y descuentos >=95% en general) son placeholders/errores
        # de carga de Rappi para "sin dinámica activa", no un descuento real
        # (nunca hay cerveza gratis o casi gratis).
        discount = 0.0
        precio = fleje
    descuento_pct = int(round(discount * 100))
    promo_desc = f"{descuento_pct}%" if descuento_pct > 0 else ""

    return {
        "Tipo de Cadena": TIPO_CADENA_RAPPI,
        "Fecha extracción": datetime.now().strftime("%d/%m/%Y"),
        "Cadena": CADENA_RAPPI,
        "Sucursal": nombre_suc,
        "NODO": nodo,
        "EAN": "",
        "Descripcion": descripcion,
        "Marca": _marca_de(p),
        "Precio Fleje": fleje,
        "Precio Dinamizado": precio,
        "Promocion Desc": promo_desc,
        # Rappi no expone fecha de inicio/fin de promo.
        "Inicio Promo": "",
        "Fin Promo": "",
    }


def _scrape_store(page, store_id, category_slug, status_box):
    url = f"{BASE_RAPPI}/tiendas/{store_id}-turbo-express/{category_slug}"
    page.goto(url, wait_until="networkidle", timeout=45000)

    next_data = page.evaluate(
        "() => JSON.parse(document.getElementById('__NEXT_DATA__').textContent)"
    )
    pageProps = next_data["props"]["pageProps"]
    fallback = pageProps.get("fallback", {})
    fbkey = next(iter(fallback), None)

    all_products = {}
    subcats = []
    if fbkey:
        sar = fallback[fbkey].get("sub_aisles_response", {}).get("data", {})
        for h in sar.get("headers", []):
            for c in h.get("resource", {}).get("categories", []):
                subcats.append({"id": c["id"], "name": c["name"]})
        for comp in sar.get("components", []):
            for p in comp.get("resource", {}).get("products", []):
                all_products[p["product_id"]] = p

    status_box.info(f"PedidosYa/Rappi store {store_id}: {len(subcats)} subcategorías encontradas.")

    for sub in subcats:
        slug = _slugify(sub["name"])
        sub_url = f"{url}/{slug}"

        def handle_response(response, _bucket=all_products):
            if "dynamic/context/content" not in response.url:
                return
            try:
                req_body = response.request.post_data or ""
                if '"aisle_detail"' not in req_body:
                    return
                data = response.json()
                for comp in data.get("data", {}).get("components", []):
                    for p in comp.get("resource", {}).get("products", []):
                        _bucket[p["product_id"]] = p
            except Exception:
                pass

        page.on("response", handle_response)
        try:
            page.goto(sub_url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            status_box.warning(f"⚠️ Rappi: no se pudo cargar subcategoría '{sub['name']}': {e}")
            page.remove_listener("response", handle_response)
            continue

        try:
            sub_next_data = page.evaluate(
                "() => JSON.parse(document.getElementById('__NEXT_DATA__').textContent)"
            )
            sub_fallback = sub_next_data["props"]["pageProps"].get("fallback", {})
            sub_fbkey = next(iter(sub_fallback), None)
            if sub_fbkey:
                ad = sub_fallback[sub_fbkey].get("aisle_detail_response", {}).get("data", {})
                for comp in ad.get("components", []):
                    for p in comp.get("resource", {}).get("products", []):
                        all_products[p["product_id"]] = p
        except Exception:
            pass

        for _ in range(MAX_VER_MAS_CLICKS):
            count_before = page.locator('a[href^="/p/"]').count()
            clicked = page.evaluate(
                """() => {
                    const btn = Array.from(document.querySelectorAll('button, a'))
                        .find(el => /ver\\s*m[aá]s/i.test(el.textContent || ''));
                    if (!btn) return false;
                    btn.click();
                    return true;
                }"""
            )
            if not clicked:
                break
            grew = False
            for _ in range(16):
                page.wait_for_timeout(500)
                if page.locator('a[href^="/p/"]').count() > count_before:
                    grew = True
                    break
            if not grew:
                break

        page.remove_listener("response", handle_response)
        time.sleep(1.2)

    return list(all_products.values())


def fetch_and_process_rappi_prices(nombre_suc, nodo, provincia, status_box, progress_bar):
    """
    Firma idéntica a toledo_api/libertad_api para enchufar directo en
    main.py. Devuelve un DataFrame con las columnas finales ya armadas.
    """
    status_box.info(f"🚀 Procesando Rappi: {nombre_suc} (vía Playwright)...")

    products = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="es-AR")
            page = context.new_page()

            for attempt in range(1, 4):
                try:
                    products = _scrape_store(page, STORE_ID_RAPPI, CATEGORY_SLUG_RAPPI, status_box)
                    break
                except Exception as e:
                    status_box.warning(f"⚠️ Rappi: error scrapeando la tienda (intento {attempt}/3): {e}")
                    try:
                        page.close()
                    except Exception:
                        pass
                    time.sleep(4 * attempt)
                    page = context.new_page()

            browser.close()
    except Exception as e:
        status_box.error(f"❌ Rappi: no se pudo iniciar Playwright/Chromium: {e}")
        return pd.DataFrame()

    if not products:
        status_box.warning(f"⚠️ Rappi devolvió 0 productos para {nombre_suc}.")
        return pd.DataFrame()

    filas = [f for f in (_producto_a_fila(p, nombre_suc, nodo) for p in products) if f is not None]
    if not filas:
        status_box.warning(f"⚠️ Rappi: 0 filas válidas (todo pack/combo o sin precio) para {nombre_suc}.")
        return pd.DataFrame()

    df = pd.DataFrame(filas)
    progress_bar.progress(1.0, text=f"Rappi {nombre_suc}: Finalizado.")
    return df.reindex(columns=COLUMNAS_ORDENADAS)
