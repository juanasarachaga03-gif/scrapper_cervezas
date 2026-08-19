import time
import requests
import pandas as pd
import os
import json
from bs4 import BeautifulSoup
from datetime import datetime


def scrape_supermami():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    productos = []
    urls_vistas = set()

    for offset in range(0, 120, 12):

        url_categoria = (
            "https://supermami.com.ar/super/categoria/"
            "supermami-bebidas-cervezas/_/N-1hxofrx"
            "?Nf=product.startDate%7CLTEQ+1.7852832E12"
            "%7C%7Cproduct.endDate%7CGTEQ+1.7852832E12"
            f"&No={offset}"
            "&Nr=AND%28product.disponible%3ADisponible%2Cproduct.language%3Aespa%C3%B1ol%2Cproduct.priceListPair%3AsalePrices_listPrices%2COR%28product.siteId%3AsuperSite%29%29"
            "&Nrpp=12"
        )


        response = session.get(
            url_categoria,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=120
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        links = soup.select(
            "a[href*='/super/producto/']"
        )

        if len(links) == 0:
            print("✅ Fin de páginas")
            break

        print(f"✅ Links encontrados: {len(links)}")

        for a in links:

            try:

                href = a.get("href")

                if not href:
                    continue

                if href in urls_vistas:
                    continue

                urls_vistas.add(href)

                if href.startswith("/"):
                    url_producto = (
                        "https://supermami.com.ar"
                        + href
                    )
                else:
                    url_producto = href

                try:

                    producto = session.get(
                        url_producto,
                        timeout=30
                    )

                except Exception as e:

                    print(f"⚠️ Error producto: {e}")

                    continue

                detalle = BeautifulSoup(
                    producto.text,
                    "html.parser"
                )

                scripts = detalle.find_all(
                    "script",
                    type="application/ld+json"
                )

                for script in scripts:

                    try:

                        data = json.loads(
                            script.string
                        )
                        print(type(data))

                        if isinstance(data, dict):
                            print(data.get("@type"))

                        if (
                            isinstance(data, dict)
                            and data.get("@type") == "Product"
                        ):

                            ean = data.get(
                                "productID"
                            )

                            nombre = data.get(
                                "name"
                            )

                            marca = data.get(
                                "brand"
                            )

                            stock = None
                            precio = None

                            offers = data.get(
                                "offers"
                            )

                            if offers:

                                if isinstance(
                                    offers,
                                    list
                                ):
                                    offer = offers[0]
                                else:
                                    offer = offers

                                precio = offer.get(
                                    "price"
                                )

                                stock = (
                                    "InStock"
                                    in str(
                                        offer.get(
                                            "availability"
                                        )
                                    )
                                )

                            productos.append({

                                "cadena":
                                    "Super Mami",

                                "fecha_scraping":
                                    datetime.now().strftime(
                                        "%Y-%m-%d"
                                    ),

                                "ean":
                                    ean,

                                "marca":
                                    marca,

                                "nombre":
                                    nombre,

                                "precio_oferta":
                                    precio,

                                "stock":
                                    stock,

                                "url":
                                    url_producto

                            })
                            time.sleep(1)
                            break

                    except:
                        pass

            except Exception as e:
                print(
                    f"⚠️ Error producto: {e}"
                )

    return pd.DataFrame(productos)

if __name__ == "__main__":


    df = scrape_supermami()

    output_dir = os.path.join(
        os.path.dirname(
            os.path.dirname(__file__)
        ),
        "Output"
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    archivo = os.path.join(
        output_dir,
        "cervezas_supermami.xlsx"
    )

    df.to_excel(
        archivo,
        index=False
    )

    print("\n====================")
    print(df.head())
    print("====================")

    print(
        f"\n📦 Total productos: {len(df)}"
    )

    print(
        f"✅ Excel generado: {archivo}"
    )