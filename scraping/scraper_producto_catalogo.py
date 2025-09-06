# scraper_producto_catalogo.py (Versión 5.1 - Corregida)
import asyncio
import json
import os
import re
import random
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
import sqlalchemy

def _parsear_vendedor(item: dict, full_filment_data: dict) -> dict:
    """
    Función auxiliar para procesar el JSON de un único vendedor.
    """
    item_id_actual = item.get("id")
    info_vendedor = {
        "item_id": item_id_actual,
        "texto_cuotas": "",
        "precio": None,
        "condicion_producto": "",
        "tipo_envio": "",
        "nombre_vendedor": "",
        "reputacion_vendedor": "Sin reputación",
        "link_publicacion": "",
        "envio_full": full_filment_data.get(item_id_actual, False),
        "seller_extra_info": [],
        "seller_thermometer_info": []
    }

    for componente in item.get("components", []):
        comp_id = componente.get("id")
        if comp_id == "price":
            info_vendedor["precio"] = float(componente.get("price", {}).get("value"))
        elif comp_id == "payment_summary":
            info_vendedor["texto_cuotas"] = componente.get("title", {}).get("text", "")
        elif comp_id == "condition_summary":
            info_vendedor["condicion_producto"] = componente.get("title", {}).get("text")
        elif comp_id == "shipping_summary":
            title_data = componente.get("title", {})
            valores = title_data.get("values", {})
            promesa = valores.get("promise", {}).get("text", "")
            resto_texto = title_data.get("text", "").replace("{promise}", "")
            info_vendedor["tipo_envio"] = f"{promesa}{resto_texto}".strip()
        elif comp_id == "seller":
            seller_data = componente.get("seller", {})
            seller_info = componente.get("seller_info", {})
            info_vendedor["nombre_vendedor"] = seller_data.get("name")
            reputacion = seller_data.get("reputation_level")
            if reputacion:
                info_vendedor["reputacion_vendedor"] = reputacion
            info_vendedor["seller_extra_info"] = seller_info.get("extra_info", [])
            info_vendedor["seller_thermometer_info"] = seller_info.get("thermometer", {}).get("info", [])

    if item_id_actual:
        item_id_numerico = item_id_actual.replace('MLA', '')
        info_vendedor["link_publicacion"] = f"https://articulo.mercadolibre.com.ar/MLA-{item_id_numerico}"
    
    return info_vendedor

def verificar_url(url_producto: str) -> str:
    match = re.search(r'(https://www.mercadolibre.com.ar/.*/p/MLA\d+)', url_producto)
    if not match:
        print(f"ADVERTENCIA: La URL '{url_producto}' no parece ser una URL de producto de catálogo válida.")
        return url_producto
    return match.group(1)

async def extraer_competidores_catalogo(url: str, modo_silencioso: bool = True) -> tuple[list[dict], str | None, str | None, str | None]:
    url_base = verificar_url(url)
    print(f"Iniciando Scraper de Catálogo para el producto: {url_base}")

    vendedores_totales = []
    cookies_path = 'cookies.json'
    numero_pagina = 1

    cat_principal, cat_secundaria, nombre_producto_catalogo = None, None, None

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(user_agents),
            viewport={'width': 1920, 'height': 1080},
            locale='es-AR',
            timezone_id='America/Argentina/Buenos_Aires',
        )

        if os.path.exists(cookies_path):
            with open(cookies_path, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            # Sanitización de cookies para compatibilidad
            for cookie in cookies:
                if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                    del cookie['sameSite']
            await context.add_cookies(cookies)
            if not modo_silencioso: print("Paso 1: Sesión cargada desde 'cookies.json'.")

        page = await context.new_page()
        
        # Seguridad adicional: Cabecera Referer
        await page.set_extra_http_headers({
            'Referer': 'https://www.mercadolibre.com.ar'
        })
        
        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        if not modo_silencioso: print("Paso 2: Stealth aplicado correctamente.")
        
        recursos_bloqueados = ['image', 'stylesheet', 'font', 'media', 'other']
        await page.route("**/*", lambda route: route.abort() if route.request.resource_type in recursos_bloqueados else route.continue_())
        if not modo_silencioso: print(f"Optimización activada: Bloqueando {recursos_bloqueados}")

        try:
            try:
                await page.goto(url_base, wait_until="domcontentloaded", timeout=60000)
                json_text_producto = await page.inner_text('script#__PRELOADED_STATE__', timeout=15000)
                datos_producto = json.loads(json_text_producto)
                initial_state_data = datos_producto.get("pageState", {}).get("initialState", {})

                nombre_producto_catalogo = initial_state_data.get("components", {}).get("header", {}).get("title")
                if not nombre_producto_catalogo:
                    nombre_producto_catalogo = initial_state_data.get("track", {}).get("melidata_event", {}).get("event_data", {}).get("productTitle")
                if not nombre_producto_catalogo:
                    nombre_producto_catalogo = initial_state_data.get("gtm_event", {}).get("productTitle")
                
                if nombre_producto_catalogo:
                    print(f"¡ÉXITO! Producto: '{nombre_producto_catalogo}'")

                nombres_categorias = []
                path_root = initial_state_data.get("analytics_event", {}).get("pathFromRoot", [])
                if path_root:
                    nombres_categorias = [cat.get("name") for cat in path_root if cat.get("name")]

                if not nombres_categorias:
                    breadcrumb_cats = initial_state_data.get("components", {}).get("breadcrumb", {}).get("categories", [])
                    if breadcrumb_cats:
                        nombres_categorias = [cat.get("label", {}).get("text") for cat in breadcrumb_cats if cat.get("label", {}).get("text")]
                
                if nombres_categorias:
                    cat_principal = nombres_categorias[0]
                    cat_secundaria = nombres_categorias[-1] if len(nombres_categorias) > 1 else nombres_categorias[0]
                    print(f"¡ÉXITO! Categorías: '{cat_principal}' > '{cat_secundaria}'")

            except Exception as e:
                print(f"Advertencia: No se pudieron extraer los datos iniciales del producto. Error: {e}")

            print("Iniciando escaneo de páginas de vendedores: ", end="", flush=True)
            while True:
                url_pagina_actual = f"{url_base}/s?page={numero_pagina}"
                
                try:
                    await page.goto(url_pagina_actual, wait_until="domcontentloaded", timeout=60000)
                    json_text = await page.inner_text('script#__PRELOADED_STATE__')
                except PlaywrightTimeoutError:
                    print(f"\nNo se pudo cargar la página {numero_pagina}. Finalizando paginación.")
                    break
                
                datos = json.loads(json_text)
                items_vendedores_pagina = datos.get("pageState", {}).get("initialState", {}).get("components", {}).get("results", {}).get("items", [])
                
                if not items_vendedores_pagina:
                    break

                track_items = datos.get("pageState", {}).get("initialState", {}).get("components", {}).get("track", {}).get("melidata_event", {}).get("event_data", {}).get("items", [])
                full_filment_data = {seller['item_id']: seller.get('has_full_filment', False) for seller in track_items}

                vendedores_pagina_actual = [_parsear_vendedor(item, full_filment_data) for item in items_vendedores_pagina]
                
                if modo_silencioso:
                    print(f".", end="", flush=True)

                vendedores_totales.extend(vendedores_pagina_actual)
                numero_pagina += 1
                await page.wait_for_timeout(random.uniform(2500, 5500))
                if (numero_pagina -1) % 5 == 0:
                    pausa_larga = random.uniform(8000, 15000) # Descanso de 8 a 15 segundos
                    print(f"\nTomando un descanso estratégico de {pausa_larga/1000:.1f} segundos...")
                    await page.wait_for_timeout(pausa_larga)
        
        except Exception as e:
            print(f"\n--- ERROR DURANTE LA EJECUCIÓN --- \nOcurrió un error: {e}")
        finally:
            await browser.close()
    
    print(f"\nProceso finalizado. Se extrajeron datos de un total de {len(vendedores_totales)} vendedores en {numero_pagina - 1} páginas.")
    return vendedores_totales, cat_principal, cat_secundaria, nombre_producto_catalogo