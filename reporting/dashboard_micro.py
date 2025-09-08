# dashboard_micro.py (Versión 5.0 - Asistente de IA Estratégica)
# Integra IA Generativa de Google para ofrecer análisis y recomendaciones.

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from urllib.parse import quote_plus
import google.generativeai as genai

# -----------------------------------------------------------------------------
# FUNCIONES DE CONEXIÓN Y CARGA DE DATOS
# -----------------------------------------------------------------------------

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
def load_data(tabla_crudos: str):
    """Carga los datos crudos de los últimos 30 días."""
    engine = get_engine()
    try:
        query = f"SELECT * FROM {tabla_crudos} WHERE fecha_extraccion >= CURRENT_DATE - INTERVAL '30 days' ORDER BY fecha_extraccion DESC"
        df = pd.read_sql(query, engine)
        df['fecha_extraccion'] = pd.to_datetime(df['fecha_extraccion']).dt.date
        return df
    except Exception as e:
        st.error(f"Error al cargar datos de la tabla '{tabla_crudos}': {e}.")
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# NUEVA FUNCIÓN DE INTELIGENCIA ARTIFICIAL
# -----------------------------------------------------------------------------

@st.cache_data
def obtener_sugerencia_ia(producto, nuestro_seller, nuestro_precio, posicion, precio_lider, competidores_contexto, total_competidores, pct_full):
    """
    Genera un análisis y sugerencias CONCISAS utilizando la IA Generativa de Google.
    """
    try:
        genai.configure(api_key=st.secrets.google_ai["api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        return f"Error al configurar la API de IA: {e}."

    # --- INICIO DE LA MODIFICACIÓN DEL PROMPT ---
    if posicion == "N/A" or posicion == "Fuera de Filtro":
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
    else: # Estamos compitiendo
        prompt = f"""
        **Rol:** Eres un asesor de estrategia e-commerce para Mercado Libre, experto en dar insights rápidos y accionables.
        **Tarea:** Analiza nuestra posición para el producto "{producto}" y da recomendaciones.
        **Datos Clave de Nuestra Empresa ({nuestro_seller}):**
        - Nuestro Precio: ${nuestro_precio:,.2f}.
        - Nuestra Posición: #{posicion}.
        - Precio del Líder: ${precio_lider:,.2f}.
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
        return ['color: green; font-weight: bold;'] * len(row)
    return [''] * len(row)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN E INTERFAZ DEL DASHBOARD
# -----------------------------------------------------------------------------

st.set_page_config(layout="wide", page_title="Análisis Táctico con IA")

# --- Lógica de Selección de Cliente (sin cambios) ---
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

# --- Carga de datos y Filtros (sin cambios) ---
df_crudo = load_data(tabla_crudos=TABLA_CRUDOS)

if not df_crudo.empty:
    st.sidebar.header("Filtros Principales")
    productos_disponibles = sorted(df_crudo['nombre_producto'].unique())
    producto_seleccionado = st.sidebar.selectbox("Seleccione un Producto", productos_disponibles)
    df_producto = df_crudo[df_crudo['nombre_producto'] == producto_seleccionado]
    fecha_maxima = df_producto['fecha_extraccion'].max()
    fecha_seleccionada = st.sidebar.date_input("Seleccione una Fecha", value=fecha_maxima, min_value=df_producto['fecha_extraccion'].min(), max_value=fecha_maxima, format="DD/MM/YYYY")
    st.sidebar.header("Filtros de Contexto de Mercado")
    filtro_full = st.sidebar.checkbox("Solo con Envío FULL", value=False)
    filtro_gratis = st.sidebar.checkbox("Solo con Envío Gratis", value=False)
    filtro_factura_a = st.sidebar.checkbox("Solo con Factura A", value=False)
    filtro_cuotas = st.sidebar.slider("Mínimo de cuotas sin interés", 0, 12, 0)

    # --- Lógica de Filtrado (sin cambios) ---
    df_dia = df_producto[df_producto['fecha_extraccion'] == fecha_seleccionada].copy()
    nuestra_oferta = df_dia[df_dia['nombre_vendedor'] == NUESTRO_SELLER_NAME].copy()
    df_contexto = df_dia.copy()
    if filtro_full: df_contexto = df_contexto[df_contexto['envio_full'] == True]
    if filtro_gratis: df_contexto = df_contexto[df_contexto['envio_gratis'] == True]
    if filtro_factura_a: df_contexto = df_contexto[df_contexto['factura_a'] == True]
    if filtro_cuotas > 0: df_contexto = df_contexto[df_contexto['cuotas_sin_interes'] >= filtro_cuotas]
    df_contexto_sorted = df_contexto.sort_values(by='precio', ascending=True).reset_index(drop=True)

    # --- Visualización de Título y Métricas (sin cambios) ---
    if not df_contexto_sorted.empty:
        link_lider = df_contexto_sorted.iloc[0]['link_publicacion']
        st.header(f"[{producto_seleccionado}]({link_lider})")
    else:
        st.header(f"Análisis para: {producto_seleccionado}")
    st.caption(f"Fecha de análisis: {fecha_seleccionada.strftime('%d/%m/%Y')}")
    st.markdown("---")

    col1, col2, col3, col4 = st.columns(4)
    nuestro_precio = nuestra_oferta['precio'].iloc[0] if not nuestra_oferta.empty else 0
    precio_min_contexto = df_contexto_sorted['precio'].min() if not df_contexto_sorted.empty else 0
    
    posicion_str = "N/A"
    if nuestro_precio > 0 and not df_contexto_sorted.empty and NUESTRO_SELLER_NAME in df_contexto_sorted['nombre_vendedor'].values:
        posicion_num = df_contexto_sorted.index[df_contexto_sorted['nombre_vendedor'] == NUESTRO_SELLER_NAME][0] + 1
        posicion_str = f"#{posicion_num}"
    elif nuestro_precio > 0:
        posicion_str = "Fuera de Filtro"

    with col1:
        st.metric(label="🏆 Nuestra Posición (contexto)", value=posicion_str)
    with col2:
        st.metric(label="💲 Nuestro Precio", value=f"${nuestro_precio:,.2f}" if nuestro_precio > 0 else "N/A")
    with col3:
        st.metric(label="🥇 Precio Líder (contexto)", value=f"${precio_min_contexto:,.2f}" if precio_min_contexto > 0 else "N/A")
    with col4:
        if nuestro_precio > 0 and precio_min_contexto > 0:
            dif_vs_lider = nuestro_precio - precio_min_contexto
            st.metric(label="💰 Diferencia vs. Líder", value=f"${dif_vs_lider:,.2f}", delta_color="inverse")
        else:
            st.metric(label="💰 Diferencia vs. Líder", value="N/A")

    st.markdown("---")

    # --- NUEVA SECCIÓN: ANÁLISIS CON IA ---
    st.subheader("🤖 Asistente de Estrategia IA")
    if not df_contexto_sorted.empty:
        with st.spinner("La IA está analizando la situación..."):
            pct_full_contexto = (df_contexto_sorted['envio_full'].sum() / len(df_contexto_sorted)) * 100 if len(df_contexto_sorted) > 0 else 0
            
            # Extraemos el número de la posición para pasarlo a la IA
            posicion_para_ia = int(posicion_str.replace("#", "")) if '#' in posicion_str else posicion_str

            sugerencia = obtener_sugerencia_ia(
                producto=producto_seleccionado,
                nuestro_seller=NUESTRO_SELLER_NAME,
                nuestro_precio=nuestro_precio,
                posicion=posicion_para_ia,
                precio_lider=precio_min_contexto,
                competidores_contexto=len(df_contexto_sorted),
                total_competidores=len(df_dia),
                pct_full=pct_full_contexto
            )
            st.markdown(sugerencia)
    else:
        st.info("No hay competidores en el contexto seleccionado para realizar un análisis de IA.")


    # --- TABLA DE DATOS DETALLADA ---
    with st.expander("Ver tabla de competidores en el contexto filtrado", expanded=True):
        if not df_contexto_sorted.empty:
            st.dataframe(
                df_contexto_sorted[[
                    'nombre_vendedor', 'precio', 'cuotas_sin_interes', 'envio_full',
                    'envio_gratis', 'factura_a', 'reputacion_vendedor', 'link_publicacion'
                ]].style.apply(highlight_nuestro_seller, seller_name_to_highlight=NUESTRO_SELLER_NAME, axis=1),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.write("Tabla vacía para el contexto actual.")

else:
    st.warning(f"No se encontraron datos en la tabla '{TABLA_CRUDOS}' en los últimos 30 días.")
    st.info(f"Verifique que el pipeline para el cliente '{empresa_seleccionada}' se haya ejecutado correctamente.")