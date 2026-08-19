import requests
import pandas as pd
from datetime import datetime

def scrape_depot():

    productos = []
    page = 1

    while True:

        url = (
            f"https://depotexpress.com.ar/wp-json/wc/store/v1/products"
            f"?category=31&per_page=100&page={page}"
        )

        print(f"📄 Consultando página {page}")

        response = requests.get(url, timeout=30)

        if response.status_code != 200:
            print("✅ Fin de páginas")
            break

        data = response.json()

        if not data:
            print("✅ No hay más productos")
            break

        for p in data:

            try:

                precio = float(
                    p["prices"]["price"]
                ) / 100

                productos.append({
                    "fecha_scraping": datetime.now().strftime("%Y-%m-%d"),
                    "cadena": "Depot",
                    "ean": p.get("sku"),
                    "nombre": p.get("name"),
                    "precio_oferta": precio,
                    "stock": p.get("is_in_stock"),
   
                })

            except Exception as e:
                print(f"⚠️ Error: {e}")

        page += 1

    return pd.DataFrame(productos)


if __name__ == "__main__":

    df = scrape_depot()

    print(df.head())

    archivo = "cervezas_depot.xlsx"

    df.to_excel(archivo, index=False)

    print(f"\n✅ Total productos: {len(df)}")
    print(f"✅ Excel generado: {archivo}")