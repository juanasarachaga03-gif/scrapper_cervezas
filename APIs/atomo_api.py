import requests
import pandas as pd
import re
import os
from bs4 import BeautifulSoup
from datetime import datetime


def scrape_atomo():

    url = (
        "https://atomoconviene.com/"
        "atomo-ecommerce/90-cervezas?ajax=1"
    )

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=60
        )

    except Exception as e:

        print(f"⚠️ Error Atomo: {e}")

        return pd.DataFrame()

    data = response.json()

    html_productos = data["rendered_products"]

    soup = BeautifulSoup(html_productos, "html.parser")

    cards = soup.select("article.product-miniature")

    print(f"✅ Productos encontrados: {len(cards)}")

    productos = []

    for card in cards:

        try:

            product_id = card.get("data-id-product")

            link = card.select_one("h2 a")

            if not link:
                continue

            nombre = link.get_text(strip=True)

            url_producto = link.get("href")

            ean = None

            if url_producto:

                match = re.search(
                    r"(779\d{10})",
                    url_producto
                )

                if match:
                    ean = match.group(1)

            precio = None

            precio_tag = card.select_one("span.price")

            if precio_tag:

                texto_precio = (
                    precio_tag
                    .get_text(strip=True)
                    .replace("$", "")
                    .replace(".", "")
                    .replace(",", ".")
                    .strip()
                )

                try:
                    precio = float(texto_precio)
                except:
                    pass

            productos.append({
                "fecha_scraping":
                    datetime.now().strftime("%Y-%m-%d"),

                "cadena": "Atomo",

                "fecha_scraping":
                    datetime.now().strftime("%Y-%m-%d"),

                "ean":
                    ean,

                "nombre":
                    nombre,

                "precio_oferta":
                    precio,

            })

        except Exception as e:
            print(f"⚠️ Error: {e}")

    return pd.DataFrame(productos)


if __name__ == "__main__":

    df = scrape_atomo()

    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "Output"
    )

    os.makedirs(output_dir, exist_ok=True)

    archivo = os.path.join(
        output_dir,
        "cervezas_atomo.xlsx"
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