import json

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


SUCURSAL = "184"  # Neuquen


def extraer_producto_jsonld(html):

    with open(
        "debug_producto.html",
        "w",
        encoding="utf-8"
    ) as f:
        f.write(html)

    print("HTML guardado: debug_producto.html")

    print("GTIN:", "gtin" in html)
    print("SKU:", "sku" in html)
    print("Product:", '"@type"' in html)

    return None

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
    )

    context = browser.new_context()

    context.add_cookies([
        {
            "name":
                "Id-Sucursal-Super",

            "value":
                SUCURSAL,

            "domain":
                ".laanonima.com.ar",

            "path":
                "/"
        }
    ])

    page = context.new_page()

    page.goto(
        "https://www.laanonima.com.ar/",
        wait_until="domcontentloaded"
    )

    print(
        "\nBUSCANDO ANDES...\n"
    )

    data = page.evaluate("""
        async () => {
            const r =
                await fetch(
                    '/catalogo/buscador/andes'
                );

            return await r.json();
        }
    """)

    articulos = data.get(
        "articulos",
        []
    )

    print(
        f"Articulos encontrados: "
        f"{len(articulos)}"
    )

    for art in articulos[:5]:
        print(art)

    print(
        "\nABRIENDO PRODUCTO TEST..."
    )

    page.goto(
        "https://www.laanonima.com.ar/cerveza-andes-origen-rubia-lata-473cc-x6/art_2389861/",
        wait_until="domcontentloaded"
    )

    html = page.content()

    producto = (
        extraer_producto_jsonld(
            html
        )
    )

    if not producto:

        print(
            "\nERROR: no se encontró Product JSON-LD"
        )

    else:

        print("\nPRODUCTO:")

        print(
            "EAN:",
            producto.get("gtin")
        )

        print(
            "SKU:",
            producto.get("sku")
        )

        print(
            "DESCRIPCION:",
            producto.get("name")
        )

        print(
            "MARCA:",
            producto.get(
                "brand",
                {}
            ).get(
                "name"
            )
        )

        offers = producto.get(
            "offers",
            {}
        )

        print(
            "PRECIO DI:",
            offers.get("price")
        )

        price_spec = offers.get(
            "priceSpecification",
            {}
        )

        print(
            "PRECIO FLE:",
            price_spec.get("price")
        )

    input(
        "\nENTER PARA CERRAR..."
    )

    browser.close()