import requests
import pandas as pd
import os
from datetime import datetime


def scrape_top():

    productos = []

    desde = 0
    lote = 10
    print("ENTRO AL WHILE")
    while True:

        hasta = desde + lote - 1

        url = (
            "https://www.supertop.com.ar/"
            "api/catalog_system/pub/products/search/"
            f"bebidas/cervezas?_from={desde}&_to={hasta}"
        )

        print(f"📄 Productos {desde} a {hasta}")

        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=60
        )

        data = response.json()

        if not data:
            print("✅ Fin de páginas")
            break

        print(f"✅ Encontrados: {len(data)}")

        for p in data:
            try:

                item = p["items"][0]

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
                        ) * 100,
                        2
                    )
                if not productos:
                    import json
                    print(json.dumps(p, indent=2, ensure_ascii=False))

                productos.append({

                    "cadena": "TOP",

                    "fecha_scraping":
                        datetime.now().strftime("%Y-%m-%d"),

                    "ean":
                        item.get("ean"),

                    "marca":
                        p.get("brand"),

                    "nombre":
                        p.get("productName"),

                    "precio_oferta":
                        precio_oferta,

                    "precio_lista":
                        precio_lista,

                    "descuento_pct":
                        descuento_pct,

                    "stock":
                        offer.get("IsAvailable"),

                    "stock_disponible":
                        offer.get("AvailableQuantity"),

                    "product_id":
                        p.get("productId"),

                    "item_id":
                        item.get("itemId"),

                    "url":
                        p.get("link")

                })
            
            except Exception as e:
                print(f"⚠️ Error: {e}")

        desde += lote
        print(f"SIGUIENTE DESDE = {desde}")

    df = pd.DataFrame(productos)

    return df

    if __name__ == "__main__":

        df = scrape_top()

        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "Output"
        )

        os.makedirs(output_dir, exist_ok=True)

        archivo = os.path.join(
            output_dir,
            "cervezas_top.xlsx"
        )

        df.to_excel(
            archivo,
            index=False
        )

        print(f"\n📦 Total productos: {len(df)}")
        print(f"✅ Excel generado: {archivo}")