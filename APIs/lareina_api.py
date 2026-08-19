import requests
import pandas as pd
import re
import os
from bs4 import BeautifulSoup
from datetime import datetime


def limpiar_precio(texto):

    if not texto:
        return None

    texto = (
        texto.replace("$", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )

    try:
        return float(texto)
    except:
        return None


def scrape_lareina():

    productos = []
    vistos = set()

    for pagina in range(1, 20):

        url = (
            "https://www.lareinaonline.com.ar/"
            f"productosnl.asp?pg={pagina}&nl=02070000"
        )

        print(f"\n📄 Página {pagina}")

        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=30
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        cards = soup.select("li.cuadProd")

        print(f"✅ Productos encontrados: {len(cards)}")

        for card in cards:

            try:

                link = card.select_one(
                    "a[href*='productosdet.asp']"
                )

                if not link:
                    continue

                href = link.get("href")

                nombre_tag = card.select_one("div.desc")

                nombre = (
                    nombre_tag.get_text(strip=True)
                    if nombre_tag
                    else None
                )

                precio_tag = card.select_one("div.precio")

                precio = None

                if precio_tag:
                    precio = limpiar_precio(
                        precio_tag.get_text(strip=True)
                    )

                # EAN
               # EAN desde la URL
                ean = None

                ean_match = re.search(
                    r"Pr=(\d{13})",
                    href
                )

                if ean_match:
                    ean = ean_match.group(1)

                url_producto = (
                    "https://www.lareinaonline.com.ar/"
                    + href.lstrip("/")
                )

                clave = f"{ean}_{nombre}"

                if clave in vistos:
                    continue

                vistos.add(clave)

                productos.append({

                    "cadena": "La Reina",

                    "fecha_scraping":
                        datetime.now().strftime("%Y-%m-%d"),

                    "ean":
                        ean,

                    "nombre":
                        nombre,

                    "precio_oferta":
                        precio,

                    "url":
                        url_producto

                })

            except Exception as e:
                print(f"⚠️ Error: {e}")

    return pd.DataFrame(productos)


if __name__ == "__main__":

    df = scrape_lareina()

    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "Output"
    )

    os.makedirs(output_dir, exist_ok=True)

    archivo = os.path.join(
        output_dir,
        "cervezas_lareina.xlsx"
    )

    df.to_excel(
        archivo,
        index=False
    )

    print("\n====================")
    print(df.head())
    print("====================")

    print(f"\n📦 Total productos: {len(df)}")
    print(f"✅ Excel generado: {archivo}")