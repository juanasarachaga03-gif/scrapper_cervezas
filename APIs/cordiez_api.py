import requests
import pandas as pd
from datetime import datetime


def scrape_cordiez():

    print("🚀 Iniciando Cordiez")

    productos = []

    desde = 0
    lote = 50

    while True:

        hasta = desde + lote - 1

        url = (
            "https://www.cordiez.com.ar/api/catalog_system/pub/products/search/"
            f"bebidas/cervezas/?&_from={desde}&_to={hasta}"
            "&O=OrderByScoreDESC"
        )

        print(f"\n📄 Productos {desde} a {hasta}")
        print(url)

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        print("STATUS:", response.status_code)

        try:
            data = response.json()
        except Exception as e:
            print("❌ Error JSON:", e)
            print(response.text[:500])
            break

        print("TIPO:", type(data))

        if not isinstance(data, list):
            print("❌ La API no devolvió una lista")
            print(data)
            break

        print("PRODUCTOS RECIBIDOS:", len(data))

        if len(data) == 0:
            print("✅ Fin de páginas")
            break

        # DEBUG DEL PRIMER PRODUCTO
        if desde == 0:
            print("\n🔍 ESTRUCTURA PRIMER PRODUCTO:")
            print(data[0].keys())

        for p in data:

            try:

                item = p["items"][0]

                print("\n✅ Producto encontrado")
                print("Nombre:", p.get("productName"))

                print("Keys item:")
                print(item.keys())

                ean = item.get("ean")
                seller = item["sellers"][0]

                offer = seller["commertialOffer"]

                precio_oferta = offer.get("Price")
                precio_lista = offer.get("ListPrice")

                descuento_pct = None

                if (
                    precio_lista
                    and precio_oferta
                    and precio_lista > 0
                ):
                    descuento_pct = round(
                        (
                            (precio_lista - precio_oferta)
                            / precio_lista
                        ),
                        2
                    )

                productos.append({
                    "fecha_scraping":
                        datetime.now().strftime("%Y-%m-%d"),

                    "cadena": "Cordiez",

                    "ean":
                        ean,

                    "nombre":
                        p.get("productName"),
                    
                    "precio_lista":
                        precio_lista,

                    "precio_oferta":
                        precio_oferta,

                    "descuento_pct":
                        descuento_pct,

                    "stock":
                        offer.get("IsAvailable"),


                    })

            except Exception as e:
                print("⚠️ ERROR PRODUCTO:")
                print(e)

        desde += lote
    df = pd.DataFrame(productos)

    print(
        df[
            [
                "nombre",
                "precio_oferta",
                "precio_lista"
            ]
        ].head(10)
    )

    return df

    return pd.DataFrame(productos)


if __name__ == "__main__":

    df = scrape_cordiez()

    print("\n====================")
    print(df.head())
    print("====================")

    print(f"\n📦 Total productos: {len(df)}")