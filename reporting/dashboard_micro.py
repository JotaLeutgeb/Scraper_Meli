# dashboard_micro.py (Versión 4.1 - Multi-Cliente, Producción)
# Este dashboard actúa como "El Microscopio", permitiendo un análisis táctico
# profundo para un producto y fecha específicos. Es multi-cliente y lee
# su configuración desde los secretos de Streamlit.

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from urllib.parse import quote_plus

# -----------------------------------------------------------------------------
# FUNCIONES DE CONEXIÓN Y CARGA DE DATOS (CACHEADAS PARA RENDIMIENTO)
# -----------------------------------------------------------------------------

@st.cache_resource
def get_engine():
    """
    Crea y cachea una única conexión a la base de datos por sesión de usuario.
    Lee las credenciales de forma segura desde los secretos de Streamlit.
    Utiliza @st.cache_resource porque el 'engine' es un objeto que no debe
    ser serializado.
    """
    try:
        db_user = st.secrets["db_user"]
        db_password_raw = st.secrets["db_password"]
        db_host = st.secrets["db_host"]
        db_port = st.secrets["db_port"]
        db_name = st.secrets["db_name"]

        db_password_encoded = quote_plus(db_password_raw)
        conn_string = f"postgresql://{db_user}:{db_password_encoded}@{db_host}:{db_port}/{db_name}"
        return create_engine(conn_string)
    except Exception as e:
        st.error(f"Error al configurar la conexión con la base de datos: {e}")
        st.stop()


@st.cache_data
def load_data(tabla_crudos: str):
    """
    Carga los datos de los últimos 30 días desde la tabla cruda especificada.
    Utiliza @st.cache_data porque devuelve un DataFrame, que es serializable.
    La caché se invalida y la función se re-ejecuta solo si el argumento
    'tabla_crudos' cambia.
    """
    engine = get_engine()
    try:
        query = f"""
            SELECT *
            FROM {tabla_crudos}
            WHERE fecha_extraccion >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY fecha_extraccion DESC
        """
        df = pd.read_sql(query, engine)
        # Aseguramos que la columna de fecha sea del tipo correcto para los filtros
        df['fecha_extraccion'] = pd.to_datetime(df['fecha_extraccion']).dt.date
        return df
    except Exception as e:
        st.error(f"Error al cargar los datos de la tabla '{tabla_crudos}': {e}. ¿La tabla existe y el pipeline ha corrido?")
        return pd.DataFrame()


def highlight_nuestro_seller(row, seller_name_to_highlight: str):
    """
    Función de estilo para resaltar nuestra fila en el DataFrame.
    Se aplica dinámicamente según el vendedor seleccionado.
    """
    if row['nombre_vendedor'] == seller_name_to_highlight:
        return ['color: green; font-weight: bold;'] * len(row)
    return [''] * len(row)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN E INTERFAZ DEL DASHBOARD
# -----------------------------------------------------------------------------

st.set_page_config(layout="wide", page_title="Análisis Táctico")

st.title("🔬 Análisis Táctico de Competencia")

# --- PASO 1: SELECTOR DE EMPRESA (CLIENTE) EN LA BARRA LATERAL ---
st.sidebar.header("Selección de Empresa")
try:
    lista_empresas = list(st.secrets.clients.keys())
except Exception:
    st.error("Error: No se encontró la configuración de clientes en los secretos (secrets.toml).")
    st.info("Asegúrate de tener una sección [clients] con tus clientes definidos en el archivo de secretos.")
    st.stop()

empresa_seleccionada = st.sidebar.selectbox(
    "Seleccione la empresa a analizar",
    options=lista_empresas,
    format_func=lambda x: x.capitalize()
)

# --- PASO 2: OBTENER CONFIGURACIÓN DINÁMICA DEL CLIENTE SELECCIONADO ---
config_cliente = st.secrets.clients[empresa_seleccionada]
TABLA_CRUDOS = config_cliente['tabla_crudos']
NUESTRO_SELLER_NAME = config_cliente['seller_name']

st.markdown(f"Análisis para **{NUESTRO_SELLER_NAME}**. Use los filtros para explorar el mercado.")

# --- PASO 3: CARGA DE DATOS Y RENDERIZADO CONDICIONAL ---
df_crudo = load_data(tabla_crudos=TABLA_CRUDOS)

if df_crudo.empty:
    st.warning(f"No se encontraron datos en la tabla '{TABLA_CRUDOS}' en los últimos 30 días.")
    st.info(f"Verifique que el pipeline para el cliente '{empresa_seleccionada}' se haya ejecutado correctamente.")
else:
    # --- FILTROS PRINCIPALES (PRODUCTO Y FECHA) ---
    st.sidebar.header("Filtros Principales")
    productos_disponibles = sorted(df_crudo['nombre_producto'].unique())
    producto_seleccionado = st.sidebar.selectbox("Seleccione un Producto", productos_disponibles)

    df_producto = df_crudo[df_crudo['nombre_producto'] == producto_seleccionado]

    fecha_maxima = df_producto['fecha_extraccion'].max()
    fecha_seleccionada = st.sidebar.date_input(
        "Seleccione una Fecha",
        value=fecha_maxima,
        min_value=df_producto['fecha_extraccion'].min(),
        max_value=fecha_maxima,
        format="DD/MM/YYYY"
    )

    # --- FILTROS DE CONTEXTO DE MERCADO ---
    st.sidebar.header("Filtros de Contexto de Mercado")
    filtro_full = st.sidebar.checkbox("Solo con Envío FULL", value=False)
    filtro_gratis = st.sidebar.checkbox("Solo con Envío Gratis", value=False)
    filtro_factura_a = st.sidebar.checkbox("Solo con Factura A", value=False)
    filtro_cuotas = st.sidebar.slider("Mínimo de cuotas sin interés", 0, 12, 0)

    # --- LÓGICA DE FILTRADO Y ANÁLISIS ---
    df_dia = df_producto[df_producto['fecha_extraccion'] == fecha_seleccionada].copy()
    nuestra_oferta = df_dia[df_dia['nombre_vendedor'] == NUESTRO_SELLER_NAME].copy()

    df_contexto = df_dia.copy()
    if filtro_full: df_contexto = df_contexto[df_contexto['envio_full'] == True]
    if filtro_gratis: df_contexto = df_contexto[df_contexto['envio_gratis'] == True]
    if filtro_factura_a: df_contexto = df_contexto[df_contexto['factura_a'] == True]
    if filtro_cuotas > 0: df_contexto = df_contexto[df_contexto['cuotas_sin_interes'] >= filtro_cuotas]

    df_contexto_sorted = df_contexto.sort_values(by='precio', ascending=True).reset_index(drop=True)

    # --- VISUALIZACIÓN ---
    # Título principal con link al producto líder del contexto
    if not df_contexto_sorted.empty:
        link_lider = df_contexto_sorted.iloc[0]['link_publicacion']
        st.header(f"[{producto_seleccionado}]({link_lider})")
    else:
        st.header(f"Análisis para: {producto_seleccionado}")

    st.caption(f"Fecha de análisis: {fecha_seleccionada.strftime('%d/%m/%Y')}")
    st.markdown("---")

    # --- MÉTRICAS PRINCIPALES (KPIS) ---
    col1, col2, col3, col4 = st.columns(4)
    nuestro_precio = nuestra_oferta['precio'].iloc[0] if not nuestra_oferta.empty else 0
    precio_min_contexto = df_contexto_sorted['precio'].min() if not df_contexto_sorted.empty else 0

    with col1:
        if nuestro_precio > 0 and not df_contexto_sorted.empty and NUESTRO_SELLER_NAME in df_contexto_sorted['nombre_vendedor'].values:
            posicion = df_contexto_sorted.index[df_contexto_sorted['nombre_vendedor'] == NUESTRO_SELLER_NAME][0] + 1
            st.metric(label="🏆 Nuestra Posición (contexto)", value=f"#{posicion}")
        elif nuestro_precio > 0:
            st.metric(label="🏆 Nuestra Posición (contexto)", value="Fuera de Filtro")
        else:
            st.metric(label="🏆 Nuestra Posición (contexto)", value="N/A")

    with col2:
        st.metric(label="💲 Nuestro Precio", value=f"${nuestro_precio:,.2f}" if nuestro_precio > 0 else "N/A")

    with col3:
        st.metric(label="🥇 Precio Líder (contexto)", value=f"${precio_min_contexto:,.2f}" if precio_min_contexto > 0 else "N/A")

    with col4:
        if nuestro_precio > 0 and precio_min_contexto > 0:
            dif_vs_lider = nuestro_precio - precio_min_contexto
            st.metric(label="💰 Diferencia vs. Líder", value=f"${dif_vs_lider:,.2f}",
                      delta=f"{((nuestro_precio / precio_min_contexto - 1) * 100):.1f}%",
                      delta_color="inverse", help="Un valor negativo significa que somos más baratos.")
        else:
            st.metric(label="💰 Diferencia vs. Líder", value="N/A")

    st.markdown("---")

    # --- ANÁLISIS DETALLADO (NUESTRA OFERTA vs MERCADO) ---
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Nuestra Oferta (Detalle)")
        if not nuestra_oferta.empty:
            nuestra_fila = nuestra_oferta.iloc[0]
            if not df_contexto_sorted.empty and NUESTRO_SELLER_NAME not in df_contexto_sorted['nombre_vendedor'].values:
                st.warning("Aviso: Nuestra oferta no cumple con los filtros de contexto seleccionados.")

            st.markdown(f"""
            - **Cuotas:** `{int(nuestra_fila['cuotas_sin_interes'])}` sin interés
            - **Envío FULL:** `{'Sí' if nuestra_fila['envio_full'] else 'No'}`
            - **Envío Gratis:** `{'Sí' if nuestra_fila['envio_gratis'] else 'No'}`
            - **Factura A:** `{'Sí' if nuestra_fila['factura_a'] else 'No'}`
            """)
        else:
            st.error("No se encontró nuestra oferta para este producto en la fecha seleccionada.")

    with col_b:
        st.subheader("Mercado (Resumen del Contexto)")
        if not df_contexto_sorted.empty:
            st.metric("N° de Competidores en este contexto", len(df_contexto_sorted))
            precio_promedio_contexto = df_contexto_sorted['precio'].mean()
            vendedor_lider = df_contexto_sorted.iloc[0]['nombre_vendedor']
            st.markdown(f"- **Precio Promedio (contexto):** `${precio_promedio_contexto:,.2f}`")
            st.markdown(f"- **Vendedor Líder (contexto):** `{vendedor_lider}`")
            st.caption(f"Total de competidores del día (sin filtros): {len(df_dia)}")
        else:
            st.info("No hay competidores que cumplan con los filtros de contexto seleccionados.")

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