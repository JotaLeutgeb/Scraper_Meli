# dashboard_micro.py (Versión 7.0 - Dashboard Táctico Interactivo y Dinámico)
# Autor: PROYECTO MELI
# Descripción: Una herramienta de análisis táctico que permite a los usuarios
# visualizar su posición en el mercado, recibir insights de una IA estratégica
# y simular escenarios de precios en tiempo real para ver su impacto inmediato.

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from urllib.parse import quote_plus
import google.generativeai as genai
import altair as alt
import datetime

# -----------------------------------------------------------------------------
# FUNCIONES DE CONEXIÓN Y CARGA DE DATOS

@st.cache_resource
def get_engine():
    """Crea y cachea la conexión a la base de datos."""
    try:
        db_user = st.secrets["db_user"]
        db_password_raw = st.secrets["db_password"]
        db_host = st.secrets["db_host"]
        db_port = st.secrets["db_port"]
        db_name = st.secrets["db_name"]
        db_password_encoded = quote_plus(db_password_raw)
        conn_string = f"postgresql+psycopg://{db_user}:{db_password_encoded}@{db_host}:{db_port}/{db_name}"
        return create_engine(conn_string)
    except Exception as e:
        st.error(f"Error al configurar la conexión con la base de datos: {e}")
        st.stop()

@st.cache_data
def get_product_list(tabla_crudos: str):
    """Obtiene solo la lista de productos únicos de los últimos 30 días."""
    engine = get_engine()
    query = f"SELECT DISTINCT nombre_producto FROM {tabla_crudos} WHERE fecha_extraccion >= CURRENT_DATE - INTERVAL '30 days';"
    df_products = pd.read_sql(query, engine)
    if df_products.empty:
        return []
    return sorted(df_products['nombre_producto'].unique())

@st.cache_data
def get_product_data(tabla_crudos: str, producto: str):
    """Carga los datos de los últimos 30 días SOLO para el producto seleccionado."""
    engine = get_engine()
    # Parámetros para prevenir inyección SQL, aunque la data sea mía y todo eso, es una buena práctica
    query = f"SELECT * FROM {tabla_crudos} WHERE nombre_producto = %(producto)s AND fecha_extraccion >= CURRENT_DATE - INTERVAL '30 days' ORDER BY fecha_extraccion DESC"
    df = pd.read_sql(query, engine, params={'producto': producto})
    df['fecha_extraccion'] = pd.to_datetime(df['fecha_extraccion']).dt.date
    return df

# -----------------------------------------------------------------------------
# FUNCIÓN DE INTELIGENCIA ARTIFICIAL

@st.cache_data
def obtener_sugerencia_ia(producto, nuestro_seller, nuestro_precio, posicion, nombre_lider, precio_lider, competidores_contexto, total_competidores, pct_full):
    """Genera un análisis y sugerencias CONCISAS utilizando la IA Generativa de Google."""
    try:
        genai.configure(api_key=st.secrets.google_ai["api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        return f"Error al configurar la API de IA: {e}."

    if posicion in ["N/A", "Fuera de Filtro"]:
        prompt = f"""
        **Rol:** Eres un asesor de estrategia e-commerce para Mercado Libre, experto en dar insights rápidos y accionables.
        **Tarea:** Analiza por qué nuestra empresa, "{nuestro_seller}", no compite en este segmento específico del producto "{producto}" y da recomendaciones.
        **Datos Clave:**
        - Precio del líder: ${precio_lider:,.2f}.
        - Competidores en este segmento: {competidores_contexto} de {total_competidores}.
        - % de competidores con FULL: {pct_full:.0f}%.
        **Formato de Respuesta Obligatorio:**
        1.  **Diagnóstico (máximo 2 frases):** Un análisis breve de la situación.
        2.  **Recomendaciones (máximo 2 bullet points):** Dos acciones directas y concisas.
        **Restricciones:** Sé extremadamente breve. Sin introducciones, saludos ni conclusiones. Ve directo al punto.
        """
    else:
        prompt = f"""
        **Rol:** Eres un asesor de estrategia e-commerce para Mercado Libre, experto en dar insights rápidos y accionables.
        **Tarea:** Analiza nuestra posición para el producto "{producto}" y da recomendaciones.
        **Datos Clave de Nuestra Empresa ({nuestro_seller}):**
        - Nuestro Precio: ${nuestro_precio:,.2f}.
        - Nuestra Posición: #{posicion}.
        **Contexto del Mercado:**
        - Líder Actual: *{nombre_lider}* a ${precio_lider:,.2f}.
        - Competidores en este contexto: {competidores_contexto} de {total_competidores}.
        - % de competidores con FULL: {pct_full:.0f}%.
        **Formato de Respuesta Obligatorio:**
        1.  **Diagnóstico (máximo 3 frases):** Un análisis breve de nuestra posición actual.
        2.  **Recomendaciones (máximo 2 bullet points):** Dos acciones claras, directas y concisas.
        **Restricciones:** Sé extremadamente breve. Sin introducciones, saludos ni conclusiones. Ve directo al punto. Usa Markdown para negritas (*palabra*).
        """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error al generar la sugerencia de la IA: {e}"

def highlight_nuestro_seller(row, seller_name_to_highlight: str):
    """Función de estilo para resaltar nuestra fila en el DataFrame."""
    if row['nombre_vendedor'] == seller_name_to_highlight:
        return ['background-color: #1a3a2a; color: #2ECC71; font-weight: bold;'] * len(row)
    return [''] * len(row)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN E INTERFAZ DEL DASHBOARD

st.set_page_config(layout="wide", page_title="Análisis Táctico con IA")

st.title("🔬 Análisis Táctico con Asistente IA")
st.sidebar.header("Selección de Empresa")

try:
    lista_empresas = list(st.secrets.clients.keys())
except Exception:
    st.error("Error: No se encontró la configuración de clientes en los secretos (secrets.toml).")
    st.stop()

empresa_seleccionada = st.sidebar.selectbox("Seleccione la empresa", options=lista_empresas, format_func=lambda x: x.capitalize())
config_cliente = st.secrets.clients[empresa_seleccionada]
TABLA_CRUDOS = config_cliente['tabla_crudos']
NUESTRO_SELLER_NAME = config_cliente['seller_name']
st.markdown(f"Análisis para **{NUESTRO_SELLER_NAME}**. Use los filtros para explorar el mercado.")

productos_disponibles = get_product_list(TABLA_CRUDOS)

if productos_disponibles:
    # --- LÓGICA PRINCIPAL DEL DASHBOARD (SI HAY DATOS) ---
    st.sidebar.header("Filtros Principales")
    producto_seleccionado = st.sidebar.selectbox("Seleccione un Producto", productos_disponibles)
    df_producto = get_product_data(TABLA_CRUDOS, producto_seleccionado)
    
    fecha_maxima = df_producto['fecha_extraccion'].max() if not df_producto.empty else datetime.date.today()
    fecha_minima = df_producto['fecha_extraccion'].min() if not df_producto.empty else fecha_maxima
    
    fecha_seleccionada = st.sidebar.date_input("Seleccione una Fecha", value=fecha_maxima, min_value=fecha_minima, max_value=fecha_maxima, format="DD/MM/YYYY")
    
    st.sidebar.header("Filtros de Contexto de Mercado")
    filtro_full = st.sidebar.checkbox("Solo con Envío FULL", value=False)
    filtro_gratis = st.sidebar.checkbox("Solo con Envío Gratis", value=False)
    filtro_factura_a = st.sidebar.checkbox("Solo con Factura A", value=False)
    filtro_cuotas = st.sidebar.slider("Mínimo de cuotas sin interés", 0, 12, 0)

    # --- Filtrado y Creación del Estado de Datos "Real" ---
    df_dia = df_producto[df_producto['fecha_extraccion'] == fecha_seleccionada].copy()
    nuestra_oferta_real = df_dia[df_dia['nombre_vendedor'] == NUESTRO_SELLER_NAME].copy()
    
    df_contexto_real = df_dia.copy()
    if filtro_full: df_contexto_real = df_contexto_real[df_contexto_real['envio_full'] == True]
    if filtro_gratis: df_contexto_real = df_contexto_real[df_contexto_real['envio_gratis'] == True]
    if filtro_factura_a: df_contexto_real = df_contexto_real[df_contexto_real['factura_a'] == True]
    if filtro_cuotas > 0: df_contexto_real = df_contexto_real[df_contexto_real['cuotas_sin_interes'] >= filtro_cuotas]
    
    df_contexto_sorted_real = df_contexto_real.sort_values(by='precio', ascending=True).reset_index(drop=True)
    nuestro_precio_real = nuestra_oferta_real['precio'].iloc[0] if not nuestra_oferta_real.empty else 0

    # --- Simulador de Escenarios ---
    st.sidebar.header("🧪 Simulador de Escenarios")
    nuevo_precio_simulado = st.sidebar.number_input("Probar un nuevo precio para mi producto", value=None, placeholder=f"Actual: ${nuestro_precio_real:,.2f}")

    # --- Lógica de Estado de Visualización ---
    df_contexto_display = df_contexto_sorted_real.copy()
    nuestro_precio_display = nuestro_precio_real
    modo_simulacion = False

    if nuevo_precio_simulado and nuevo_precio_simulado > 0:
        modo_simulacion = True
        df_simulacion = df_contexto_sorted_real.copy()
        if NUESTRO_SELLER_NAME in df_simulacion['nombre_vendedor'].values:
            df_simulacion.loc[df_simulacion['nombre_vendedor'] == NUESTRO_SELLER_NAME, 'precio'] = nuevo_precio_simulado
        elif not nuestra_oferta_real.empty:
            nuestra_fila = nuestra_oferta_real.iloc[[0]].copy()
            nuestra_fila.loc[:, 'precio'] = nuevo_precio_simulado
            df_simulacion = pd.concat([df_simulacion, nuestra_fila], ignore_index=True)
        
        df_contexto_display = df_simulacion.sort_values(by='precio').reset_index(drop=True)
        nuestro_precio_display = nuevo_precio_simulado

    # A partir de acá, todo el dashboard usa las variables "_display" ya que pueden ser reales o simuladas
    if modo_simulacion:
        st.warning("**MODO SIMULACIÓN ACTIVADO** - Los datos mostrados reflejan el precio simulado.", icon="🧪")

    # --- Visualización de Título y Métricas ---
    if not df_contexto_display.empty:
        nombre_lider = df_contexto_display.iloc[0]['nombre_vendedor']
        precio_lider = df_contexto_display.iloc[0]['precio']
        link_lider = df_contexto_display.iloc[0].get('link_publicacion', '#')
        st.header(f"[{producto_seleccionado}]({link_lider})")
    else:
        nombre_lider, precio_lider = "N/A", 0
        st.header(f"Análisis para: {producto_seleccionado}")
    
    st.caption(f"Fecha de análisis: {fecha_seleccionada.strftime('%d/%m/%Y')}")
    st.markdown("---")

    col1, col2, col3, col4 = st.columns(4)
    posicion_str = "N/A"
    if nuestro_precio_display > 0 and not df_contexto_display.empty and NUESTRO_SELLER_NAME in df_contexto_display['nombre_vendedor'].values:
        posicion_num = df_contexto_display.index[df_contexto_display['nombre_vendedor'] == NUESTRO_SELLER_NAME][0] + 1
        posicion_str = f"#{posicion_num}"
    elif nuestro_precio_display > 0:
        posicion_str = "Fuera de Filtro"

    with col1: st.metric(label="🏆 Nuestra Posición (contexto)", value=posicion_str)
    with col2: st.metric(label="💲 Nuestro Precio", value=f"${nuestro_precio_display:,.2f}" if nuestro_precio_display > 0 else "N/A")
    with col3: st.metric(label="🥇 Precio Líder (contexto)", value=f"${precio_lider:,.2f}" if precio_lider > 0 else "N/A")
    with col4:
        if nuestro_precio_display > 0 and precio_lider > 0:
            dif_vs_lider = nuestro_precio_display - precio_lider
            delta_text = f"${(nuestro_precio_display - nuestro_precio_real):,.2f} vs. real" if modo_simulacion else None
            st.metric(label="💰 Diferencia vs. Líder", value=f"${dif_vs_lider:,.2f}", delta=delta_text, delta_color="off")
        else:
            st.metric(label="💰 Diferencia vs. Líder", value="N/A")

    st.markdown("---")

    # --- Gráfico Panorama de Precios ---
    st.subheader("Panorama de Precios")
    if not df_contexto_display.empty:
        df_plot = df_contexto_display[['nombre_vendedor', 'precio']].copy()
        
        df_plot['tipo'] = 'Competidor'
        df_plot['orden_render'] = 1
        lider_vendedor_nombre = df_plot.iloc[0]['nombre_vendedor']
        if NUESTRO_SELLER_NAME in df_plot['nombre_vendedor'].values:
            nuestra_empresa_mask = df_plot['nombre_vendedor'] == NUESTRO_SELLER_NAME
            df_plot.loc[nuestra_empresa_mask, 'tipo'] = 'Nuestra Empresa'
            df_plot.loc[nuestra_empresa_mask, 'orden_render'] = 3
        if lider_vendedor_nombre != NUESTRO_SELLER_NAME:
            lider_mask = df_plot['nombre_vendedor'] == lider_vendedor_nombre
            df_plot.loc[lider_mask, 'tipo'] = 'Líder'
            df_plot.loc[lider_mask, 'orden_render'] = 2
        
        # Ajuste dinámico del eje X para mejor visualización
        min_precio = df_plot['precio'].min()
        max_precio = df_plot['precio'].max()
        padding = (max_precio - min_precio) * 0.05
        if padding == 0: padding = min_precio * 0.05

        dominio_min = min_precio - padding
        dominio_max = max_precio + padding

        chart = alt.Chart(df_plot).mark_circle(size=120).encode(
            x=alt.X('precio:Q', title='Precio ($)', axis=alt.Axis(format='$,.0f'), scale=alt.Scale(domain=[dominio_min, dominio_max])),
            y=alt.Y('nombre_vendedor:N', title=None, sort='-x'),
            color=alt.Color('tipo:N', scale=alt.Scale(domain=['Líder', 'Nuestra Empresa', 'Competidor'], range=['#FF4B4B', '#2ECC71', '#3498DB']), legend=alt.Legend(title="Leyenda")),
            order=alt.Order('orden_render:Q', sort='ascending'),
            tooltip=['nombre_vendedor', alt.Tooltip('precio', format='$,.2f')]
        ).properties(height=300).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No hay datos para mostrar en el gráfico de panorama de precios para el contexto seleccionado.")

    st.markdown("---")

    # --- ANÁLISis CON IA ---
    st.subheader("🤖 Asistente de Estrategia IA")
    if not df_contexto_display.empty:
        with st.spinner("La IA está analizando la situación..."):
            pct_full_contexto = (df_contexto_display['envio_full'].sum() / len(df_contexto_display)) * 100 if len(df_contexto_display) > 0 else 0
            posicion_para_ia = int(posicion_str.replace("#", "")) if '#' in posicion_str else posicion_str
            sugerencia = obtener_sugerencia_ia(
                producto=producto_seleccionado, nuestro_seller=NUESTRO_SELLER_NAME, nuestro_precio=nuestro_precio_display,
                posicion=posicion_para_ia, nombre_lider=nombre_lider, precio_lider=precio_lider,
                competidores_contexto=len(df_contexto_display), total_competidores=len(df_dia), pct_full=pct_full_contexto)
            st.markdown(sugerencia)
    else:
        st.info("No hay competidores en el contexto seleccionado para realizar un análisis de IA.")

    st.markdown("---")
    
    # --- Gráfico de Tendencia ---
    st.subheader("Evolución de Precios (Últimos 15 días)")
    df_tendencia = df_producto[df_producto['fecha_extraccion'] >= (fecha_maxima - datetime.timedelta(days=15))]

    if not df_tendencia.empty:
        # 1. Obtenemos el precio del líder por día
        df_lider_diario = df_tendencia.groupby('fecha_extraccion')['precio'].min().reset_index()
        df_lider_diario['serie'] = 'Líder'

        # 2. Aislamos nuestras publicaciones
        df_nuestras_publicaciones = df_tendencia[df_tendencia['nombre_vendedor'] == NUESTRO_SELLER_NAME].copy()

        # 3. Verificamos si tenemos publicaciones para mostrar
        if not df_nuestras_publicaciones.empty:
            # Renombramos las publicaciones para que sean más legibles en la leyenda
            pubs_unicas = df_nuestras_publicaciones['link_publicacion'].unique()
            nombres_amigables = {link: f"Nuestra Pub. {i+1} ({link.split('/')[3].replace('-', ' ')})" for i, link in enumerate(pubs_unicas)}
            df_nuestras_publicaciones['serie'] = df_nuestras_publicaciones['link_publicacion'].map(nombres_amigables)

            # 4. Combinamos los datos del líder y los nuestros en un solo DataFrame (formato largo)
            df_plot_final = pd.concat([
                df_lider_diario[['fecha_extraccion', 'precio', 'serie']],
                df_nuestras_publicaciones[['fecha_extraccion', 'precio', 'serie']]
            ])

            # 5. LÓGICA CLAVE: Manejo de superposición cuando somos líderes
            # Creamos una columna para identificar si nuestra publicación es la líder del día
            df_plot_final = pd.merge(df_plot_final, df_lider_diario.rename(columns={'precio': 'precio_lider'}), on='fecha_extraccion')
            
            somos_lider_mask = (df_plot_final['serie'] != 'Líder') & (df_plot_final['precio'] == df_plot_final['precio_lider'])
            df_plot_final.loc[somos_lider_mask, 'serie'] = df_plot_final['serie'] + ' (Líder)'

            # Removemos la línea original "Líder" en los días que una de nuestras pubs ya es marcada como líder
            fechas_donde_somos_lider = df_plot_final[somos_lider_mask]['fecha_extraccion'].unique()
            df_plot_final = df_plot_final[~((df_plot_final['serie'] == 'Líder') & (df_plot_final['fecha_extraccion'].isin(fechas_donde_somos_lider)))]

        else:
            # Si no tenemos publicaciones, el DataFrame final solo contiene al líder
            df_plot_final = df_lider_diario
        
        # 6. Definimos los colores para mantener la consistencia
        domain = ['Líder'] + [s for s in df_plot_final['serie'].unique() if 'Nuestra' in s]
        range_ = ['#FF4B4B'] # Rojo para el líder
        for serie_name in domain:
            if serie_name == 'Líder': continue
            if '(Líder)' in serie_name:
                range_.append('#2ECC71') # Verde brillante si somos líderes
            else:
                range_.append('#00BFFF') # Otro color (ej. azul) para otras publicaciones nuestras

        # 7. Creamos el gráfico con ALTAIR
        chart_tendencia = alt.Chart(df_plot_final).mark_line(point=True).encode(
            # EJE X: Formateado para mostrar solo día/mes
            x=alt.X('fecha_extraccion:T', title='Fecha', axis=alt.Axis(format='%d/%m')),
            
            # EJE Y: El dominio NO empieza en cero, se ajusta a los datos
            y=alt.Y('precio:Q', title='Precio ($)', axis=alt.Axis(format='$,.0f'), scale=alt.Scale(zero=False)),
            
            # COLOR: Asignado por la columna 'serie' con nuestra paleta de colores
            color=alt.Color('serie:N', scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title="Publicación")),
            
            # TOOLTIP: Muestra información útil al pasar el mouse
            tooltip=[
                alt.Tooltip('fecha_extraccion:T', title='Fecha', format='%d/%m/%Y'),
                alt.Tooltip('serie:N', title='Publicación'),
                alt.Tooltip('precio:Q', title='Precio', format='$,.2f')
            ]
        ).properties(
            height=350
        ).interactive() # Permite pan y zoom, pero con la vista inicial ya corregida

        st.altair_chart(chart_tendencia, use_container_width=True)

    else:
        st.info("No hay suficientes datos históricos para mostrar una tendencia.")

    st.markdown("---")

    # --- TABLA DE DATOS DETALLADA ---
    with st.expander("Ver tabla de competidores en el contexto filtrado", expanded=False):
        if not df_contexto_display.empty:
            columnas_tabla = ['nombre_vendedor', 'precio', 'cuotas_sin_interes', 'envio_full', 'envio_gratis', 'factura_a', 'reputacion_vendedor', 'link_publicacion']
            columnas_existentes_tabla = [col for col in columnas_tabla if col in df_contexto_display.columns]
            st.dataframe(
                df_contexto_display[columnas_existentes_tabla].style.apply(highlight_nuestro_seller, seller_name_to_highlight=NUESTRO_SELLER_NAME, axis=1),
                use_container_width=True, hide_index=True)
        else:
            st.write("Tabla vacía para el contexto actual.")

else:
    # --- MENSAJE DE ADVERTENCIA (SI NO HAY DATOS) ---
    st.warning(f"No se encontraron datos en la tabla '{TABLA_CRUDOS}' en los últimos 30 días.")
    st.info(f"Verifique que el pipeline para el cliente '{empresa_seleccionada}' se haya ejecutado correctamente.")