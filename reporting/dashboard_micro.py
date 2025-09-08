# dashboard_micro.py (Versión 3.1 - Herramienta de Análisis Táctico Mejorada)
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Cargar las variables de entorno
load_dotenv()

# Variable clave para identificar nuestra empresa en los datos
NUESTRO_SELLER_NAME = "Delta Ferreteria Industrial"

@st.cache_resource
def get_engine():
    # Leemos las credenciales desde el gestor de secretos de Streamlit
    db_user = st.secrets["db_user"]
    db_password_raw = st.secrets["db_password"]
    db_host = st.secrets["db_host"]
    db_port = st.secrets["db_port"]
    db_name = st.secrets["db_name"]

    # Codificamos la contraseña para que sea segura en la URL
    db_password_encoded = quote_plus(db_password_raw)

    # Creamos la cadena de conexión
    conn_string = f"postgresql://{db_user}:{db_password_encoded}@{db_host}:{db_port}/{db_name}"
    
    engine = create_engine(conn_string)
    return engine


# Función para cargar los datos
@st.cache_data
def load_data(tabla_crudos):
    engine = get_engine()
    try:
        query = f"SELECT * FROM {tabla_crudos} ORDER BY fecha DESC"
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        st.error(f"Error al cargar los datos: {e}")
        return pd.DataFrame()

# Función para resaltar nuestra fila en el DataFrame
def highlight_nuestro_seller(row):
    """
    Aplica un estilo a la fila si el vendedor es el nuestro,
    cambiando el color del texto a azul y poniéndolo en negrita.
    """
    if row['nombre_vendedor'] == NUESTRO_SELLER_NAME:
        # CAMBIO: La propiedad CSS ahora es 'color: blue' y 'font-weight: bold'
        return ['color: green; font-weight: bold;'] * len(row)
    return [''] * len(row)

# --- Interfaz del Dashboard ---
st.set_page_config(layout="wide", page_title="Análisis Táctico")

st.title("🔬 Análisis Táctico de Competencia")
st.markdown("Use los filtros para analizar un segmento específico del mercado y comparar nuestra oferta.")

# Cargar los datos crudos
df_crudo = load_data(dias=30)

if df_crudo.empty:
    st.warning("No se encontraron datos. Verifique la ejecución del pipeline.")
else:
    # --- Barra Lateral de Filtros ---
    st.sidebar.header("Filtros Principales")
    productos_disponibles = sorted(df_crudo['nombre_producto'].unique())
    producto_seleccionado = st.sidebar.selectbox("Seleccione un Producto", productos_disponibles)
    
    df_producto = df_crudo[df_crudo['nombre_producto'] == producto_seleccionado]
    
    fecha_minima = df_producto['fecha_extraccion'].min()
    fecha_maxima = df_producto['fecha_extraccion'].max()
    fecha_seleccionada = st.sidebar.date_input(
        "Seleccione una Fecha", value=fecha_maxima, min_value=fecha_minima,
        max_value=fecha_maxima, format="DD/MM/YYYY"
    )

    st.sidebar.header("Filtros de Contexto de Mercado")
    filtro_full = st.sidebar.checkbox("Solo con Envío FULL", value=False)
    filtro_gratis = st.sidebar.checkbox("Solo con Envío Gratis", value=False)
    filtro_factura_a = st.sidebar.checkbox("Solo con Factura A", value=False)
    filtro_cuotas = st.sidebar.slider("Mínimo de cuotas sin interés", 0, 12, 0)

    # --- Lógica de Filtrado y Análisis ---
    df_dia = df_producto[df_producto['fecha_extraccion'] == fecha_seleccionada].copy()
    nuestra_oferta = df_dia[df_dia['nombre_vendedor'] == NUESTRO_SELLER_NAME].copy()

    df_contexto = df_dia.copy()
    if filtro_full: df_contexto = df_contexto[df_contexto['envio_full'] == True]
    if filtro_gratis: df_contexto = df_contexto[df_contexto['envio_gratis'] == True]
    if filtro_factura_a: df_contexto = df_contexto[df_contexto['factura_a'] == True]
    if filtro_cuotas > 0: df_contexto = df_contexto[df_contexto['cuotas_sin_interes'] >= filtro_cuotas]
    
    # Ordenamos el dataframe del contexto por precio para el ranking
    df_contexto_sorted = df_contexto.sort_values(by='precio', ascending=True).reset_index(drop=True)

    # --- Visualización ---
    if not df_contexto_sorted.empty:
    # Si hay datos en el contexto, el título es un link al producto líder.
        link_lider = df_contexto_sorted['link_publicacion'].iloc[0]
        st.header(f"[{producto_seleccionado}]({link_lider})")
    else:
        # Si no hay datos, mostramos un título simple para evitar el error.
        st.header(f"Análisis para: {producto_seleccionado}")

    st.caption(f"Fecha: {fecha_seleccionada.strftime('%d/%m/%Y')}")
    # --- MÉTRICAS PRINCIPALES ---
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    
    # Extraer nuestra info si existimos
    nuestro_precio = nuestra_oferta['precio'].iloc[0] if not nuestra_oferta.empty else 0
    
    with col1: # NUEVO: KPI de Posición
        nuestra_posicion_contexto = "N/A"
        if nuestro_precio > 0 and not df_contexto_sorted.empty:
            # Verificamos si estamos dentro del contexto filtrado
            if NUESTRO_SELLER_NAME in df_contexto_sorted['nombre_vendedor'].values:
                # Calculamos nuestra posición (índice + 1)
                nuestra_posicion_contexto = df_contexto_sorted.index[df_contexto_sorted['nombre_vendedor'] == NUESTRO_SELLER_NAME][0] + 1
                st.metric(label="🏆 Nuestra Posición (en contexto)", value=f"#{nuestra_posicion_contexto}")
            else:
                st.metric(label="🏆 Nuestra Posición (en contexto)", value="Fuera de Filtro")
        else:
            st.metric(label="🏆 Nuestra Posición (en contexto)", value="N/A")


    with col2:
        st.metric(label="💲 Nuestro Precio", value=f"${nuestro_precio:,.2f}" if nuestro_precio > 0 else "N/A")

    with col3:
        precio_min_contexto = df_contexto_sorted['precio'].min() if not df_contexto_sorted.empty else 0
        st.metric(label="🥇 Precio Líder (en contexto)", value=f"${precio_min_contexto:,.2f}" if precio_min_contexto > 0 else "N/A")
    
    with col4:
        if nuestro_precio > 0 and precio_min_contexto > 0:
            dif_vs_lider = nuestro_precio - precio_min_contexto
            st.metric(label="💰 Diferencia vs. Líder", value=f"${dif_vs_lider:,.2f}", delta_color="inverse",
                      help="Un valor negativo significa que somos más baratos que el líder del contexto.")
        else:
            st.metric(label="💰 Diferencia vs. Líder", value="N/A")


    st.markdown("---")

    # --- ANÁLISIS DETALLADO ---
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader(":blue[Nuestra Oferta (Detalle)]")
        if not nuestra_oferta.empty:
            nuestra_fila = nuestra_oferta.iloc[0]
            
            # Chequeo si cumplimos los filtros
            cumple_filtros = True
            if (filtro_full and not nuestra_fila['envio_full']) or \
               (filtro_gratis and not nuestra_fila['envio_gratis']) or \
               (filtro_factura_a and not nuestra_fila['factura_a']) or \
               (filtro_cuotas > nuestra_fila['cuotas_sin_interes']):
                cumple_filtros = False
            
            if not cumple_filtros:
                st.warning("Aviso: Nuestra oferta no cumple con los filtros de contexto seleccionados.")

            st.markdown(f"""
            - **Cuotas:** `{nuestra_fila['cuotas_sin_interes']}` sin interés
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
            st.metric("N° Total de Competidores del día", len(df_dia))
            
            # Otros KPIs del contexto
            precio_promedio_contexto = df_contexto_sorted['precio'].mean().round(2)
            st.markdown(f"- **Precio Promedio (contexto):** `${precio_promedio_contexto:,.2f}`")

            vendedor_lider = df_contexto_sorted.iloc[0]['nombre_vendedor']
            st.markdown(f"- **Vendedor Líder (contexto):** `{vendedor_lider}`")
        else:
            st.info("No hay competidores que cumplan con los filtros de contexto seleccionados.")
    
    # MEJORA: Aplicamos el resaltado a nuestra fila en el expander
    with st.expander("Ver tabla de competidores en el contexto filtrado", expanded=True):
        if not df_contexto_sorted.empty:
            st.dataframe(
                df_contexto_sorted[['nombre_vendedor', 'precio', 'cuotas_sin_interes', 'envio_full', 'envio_gratis', 'factura_a', 'link_publicacion']]
                .style.apply(highlight_nuestro_seller, axis=1),
                use_container_width=True
            )
        else:
            st.write("Tabla vacía para el contexto actual.")