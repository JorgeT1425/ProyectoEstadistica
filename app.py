import streamlit as st
import pandas as pd
import html

# ==============================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="EstadiApp · Analítica para decidir",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# 2. ESQUEMAS OFICIALES Y LÓGICA DE LECTURA DINÁMICA (CERO VALORES QUEMADOS)
# ==============================================================================
COLUMNAS_MOTOEXPRES = [
    "id_servicio", "fecha", "hora_llegada", "dia_semana", "sede",
    "mecanico", "id_cliente", "tipo_cliente", "tipo_vehiculo", "cilindraje_cc",
    "kilometraje_km", "tipo_servicio", "tiempo_espera_min", "tiempo_diagnostico_min",
    "tiempo_reparacion_h", "repuestos_usados", "costo_mano_obra_usd",
    "costo_repuestos_usd", "costo_total_usd", "satisfaccion", "requirio_garantia"
]

COLUMNAS_NOVAAPP = [
    "id_sesion", "fecha_hora", "plataforma", "version_app", "pais",
    "plan", "edad_usuario", "tipo_red", "duracion_min", "pantallas_vistas",
    "tiempo_carga_s", "eventos_click", "crashes", "uso_funcion_ia",
    "calificacion", "realizo_compra", "monto_compra_usd"
]


def cargar_archivo(archivo_subido):
    """
    Lee un archivo CSV (UTF-8, coma, punto decimal) o XLSX (hoja 'datos').
    Retorna: (DataFrame, mensaje_error)
    """
    nombre = archivo_subido.name.lower()
    try:
        if nombre.endswith(".csv"):
            try:
                df = pd.read_csv(archivo_subido, encoding="utf-8", sep=",", decimal=".")
            except UnicodeDecodeError:
                archivo_subido.seek(0)
                df = pd.read_csv(archivo_subido, encoding="latin-1", sep=",", decimal=".")
            return df, None
        elif nombre.endswith(".xlsx") or nombre.endswith(".xls"):
            xls = pd.ExcelFile(archivo_subido)
            hoja = "datos" if "datos" in xls.sheet_names else xls.sheet_names[0]
            df = pd.read_excel(archivo_subido, sheet_name=hoja)
            return df, None
        else:
            return None, "Formato no válido. Debe ser CSV o XLSX."
    except Exception as e:
        return None, f"No se pudo leer el archivo: {str(e)}"


def extraer_indicadores(df, caso_forzado=None):
    """
    Extrae dinámicamente filas, columnas, nombres de columnas, rango de fechas,
    sedes/países y validaciones sin ningún valor quemado.
    """
    n_filas, n_cols = df.shape
    cols_reales = list(df.columns)
    cols_lower = [str(c).strip().lower() for c in cols_reales]

    # Detectar automáticamente el caso según las columnas o el selector
    if caso_forzado in ["MotoExpres", "NovaApp"]:
        caso = caso_forzado
    elif "id_servicio" in cols_lower or "mecanico" in cols_lower or n_cols == 21:
        caso = "MotoExpres"
    else:
        caso = "NovaApp"

    esquema_ref = COLUMNAS_MOTOEXPRES if caso == "MotoExpres" else COLUMNAS_NOVAAPP
    cols_esperadas = len(esquema_ref)

    # Coincidencia de columnas con el esquema
    coincidencias = sum(1 for c in cols_lower if c in esquema_ref)
    if coincidencias == 0 and n_cols == cols_esperadas:
        coincidencias = n_cols

    celdas_vacias = int(df.isna().sum().sum())
    filas_duplicadas = int(df.duplicated().sum())
    col_id = cols_reales[0] if n_cols > 0 else "ID"
    ids_unicos = int(df[col_id].nunique()) if n_cols > 0 else 0

    # Rango de fechas dinámico
    desde, hasta = "N/A", "N/A"
    for posible_fecha in ["fecha", "fecha_hora", "FECHA", "FECHA_HORA"]:
        if posible_fecha in df.columns:
            fechas = pd.to_datetime(df[posible_fecha], errors="coerce").dropna()
            if not fechas.empty:
                desde = fechas.min().strftime("%Y-%m-%d")
                hasta = fechas.max().strftime("%Y-%m-%d")
            break

    # KPIs 5 y 6 dinámicos según el caso
    col_map = {str(c).strip().lower(): c for c in cols_reales}
    if "mecanico" in col_map:
        kpi5_titulo, kpi5_sub = "MECÁNICOS", "Personal activo"
        kpi5_val = f"{df[col_map['mecanico']].nunique()}"
    elif "version_app" in col_map:
        kpi5_titulo, kpi5_sub = "VERSIONES", "Versiones activas"
        kpi5_val = f"{df[col_map['version_app']].nunique()}"
    else:
        kpi5_titulo, kpi5_sub = "GRUPOS", "Categorías"
        kpi5_val = "-"

    if "id_cliente" in col_map:
        kpi6_titulo, kpi6_sub = "CLIENTES DISTINTOS", "Base de clientes"
        kpi6_val = f"{df[col_map['id_cliente']].nunique():,}".replace(",", ".")
    elif "pais" in col_map:
        kpi6_titulo, kpi6_sub = "PAÍSES", "Mercados activos"
        kpi6_val = f"{df[col_map['pais']].nunique()}"
    else:
        kpi6_titulo, kpi6_sub = "IDS ÚNICOS", "Registros únicos"
        kpi6_val = f"{ids_unicos:,}".replace(",", ".")

    # Sedes / Países dinámicos
    col_sede = None
    sedes_dict = {}
    for cand in ["sede", "pais", "plataforma"]:
        if cand in col_map:
            col_sede = col_map[cand]
            sedes_dict = df[col_sede].value_counts().to_dict()
            break

    # Validación general
    es_valido = (n_cols == cols_esperadas) and (celdas_vacias == 0) and (filas_duplicadas == 0)

    return {
        "caso": caso,
        "esquema_nombre": "MotoExpres S.A.S. · 21 columnas" if caso == "MotoExpres" else "NovaApp · 17 columnas",
        "n_filas": n_filas,
        "n_filas_fmt": f"{n_filas:,}".replace(",", "."),
        "n_cols": n_cols,
        "cols_esperadas": cols_esperadas,
        "coincidencias": coincidencias,
        "nombres_columnas": cols_reales,
        "celdas_vacias": celdas_vacias,
        "filas_duplicadas": filas_duplicadas,
        "ids_unicos_fmt": f"{ids_unicos:,}".replace(",", "."),
        "desde": desde,
        "hasta": hasta,
        "kpi5_titulo": kpi5_titulo,
        "kpi5_val": kpi5_val,
        "kpi5_sub": kpi5_sub,
        "kpi6_titulo": kpi6_titulo,
        "kpi6_val": kpi6_val,
        "kpi6_sub": kpi6_sub,
        "col_sede": col_sede,
        "sedes_dict": sedes_dict,
        "es_valido": es_valido
    }


def generar_tabla_html(df, max_filas=3):
    """
    Genera la tabla HTML de vista previa con el mismo estilo visual del mockup
    (encabezados monospace, badges para sedes y tipos de cliente).
    """
    sub_df = df.head(max_filas)
    ths = "".join([f"<th>{html.escape(str(c).upper())}</th>" for c in sub_df.columns])

    trs = []
    for _, fila in sub_df.iterrows():
        tds = []
        for col_name, val in fila.items():
            col_low = str(col_name).lower()
            texto = html.escape(str(val))
            if col_low == "id_servicio" or col_low == "id_sesion":
                tds.append(f'<td class="td-id">{texto}</td>')
            elif col_low in ["sede", "pais"]:
                tds.append(f'<td><span class="pill-sede">{texto}</span></td>')
            elif col_low in ["tipo_cliente", "plan"]:
                clase_p = "pill-green"
                if "nuevo" in texto.lower() or "free" in texto.lower():
                    clase_p = "pill-amber"
                elif "corp" in texto.lower() or "pro" in texto.lower():
                    clase_p = "pill-blue"
                tds.append(f'<td><span class="{clase_p}">{texto}</span></td>')
            else:
                tds.append(f"<td>{texto}</td>")
        trs.append(f"<tr>{''.join(tds)}</tr>")

    return f"""
    <div class="table-scroll">
        <table class="mockup-table">
            <thead><tr>{ths}</tr></thead>
            <tbody>{''.join(trs)}</tbody>
        </table>
    </div>
    """


# ==============================================================================
# 3. CSS EXACTO AL MOCKUP (SIN TÍTULO-1-3.PDF)
# ==============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&family=Playfair+Display:wght@700;800&display=swap');

    /* Fondo general y eliminación de márgenes sobrantes de Streamlit */
    .stApp {
        background-color: #f4f6fa !important;
        font-family: 'Inter', sans-serif !important;
    }
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 1.5rem !important;
    }
    .block-container {
        padding-top: 0.4rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }

    /* ---------------- BARRA LATERAL (SIDEBAR) ---------------- */
    [data-testid="stSidebar"] {
        background-color: #16224c !important;
        border-right: 1px solid #0f172a !important;
        min-width: 250px !important;
        max-width: 250px !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.2rem !important;
    }
    .sb-brand {
        font-family: 'Playfair Display', Georgia, serif;
        font-size: 1.55rem;
        font-weight: 800;
        color: #ffffff !important;
        line-height: 1.1;
        margin-bottom: 2px;
    }
    .sb-sub {
        font-size: 0.75rem;
        color: #94a3b8 !important;
        margin-bottom: 18px;
        padding-bottom: 14px;
        border-bottom: 1px solid rgba(255,255,255,0.09);
    }
    .sb-group-hdr {
        display: flex;
        justify-content: space-between;
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.9px;
        color: #64748b !important;
        margin: 14px 0 6px 0;
        padding: 0 4px;
    }
    .sb-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        border-radius: 7px;
        font-size: 0.81rem;
        color: #cbd5e1 !important;
        margin-bottom: 3px;
    }
    .sb-item-active {
        background-color: #24346b !important;
        border-left: 3px solid #f59e0b !important;
        color: #ffffff !important;
        font-weight: 600;
    }
    .sb-code {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 700;
        color: #94a3b8;
        min-width: 22px;
    }
    .sb-code-active {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 700;
        color: #fbbf24;
        min-width: 22px;
    }
    .sb-dataset-card {
        background-color: #0f1838;
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 8px;
        padding: 12px;
        margin-top: 22px;
    }
    .sb-ds-label {
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.7px;
        color: #94a3b8;
    }
    .sb-ds-name {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        font-weight: 700;
        color: #ffffff;
        margin: 3px 0;
        word-break: break-all;
    }
    .sb-ds-rows {
        font-size: 0.73rem;
        color: #34d399;
        font-weight: 600;
    }

    /* ---------------- TOPBAR SUPERIOR ---------------- */
    .estadi-topbar {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 8px 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 18px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    }
    .tb-left {
        font-size: 0.82rem;
        color: #475569;
        display: flex;
        align-items: center;
        gap: 6px;
        flex-wrap: wrap;
    }
    .tb-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        display: inline-block;
    }
    .tb-mono {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        color: #0f172a;
    }
    .tb-right {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .tb-switch {
        background-color: #f1f5f9;
        padding: 3px;
        border-radius: 8px;
        display: inline-flex;
        gap: 2px;
        border: 1px solid #e2e8f0;
    }
    .tb-sw-active {
        background-color: #16224c;
        color: #ffffff;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 6px;
    }
    .tb-sw-inactive {
        color: #64748b;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 4px 12px;
        border-radius: 6px;
    }
    .tb-mode-btn {
        background-color: #f59e0b;
        color: #ffffff;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 5px 12px;
        border-radius: 7px;
    }

    /* ---------------- ENCABEZADO DE MÓDULO ---------------- */
    .m-eyebrow {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.73rem;
        font-weight: 700;
        color: #0d9488;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 2px;
    }
    .m-title {
        font-family: 'Playfair Display', Georgia, serif;
        font-size: 1.9rem;
        font-weight: 800;
        color: #0f172a;
        margin: 0 0 4px 0;
        line-height: 1.15;
    }
    .m-subtitle {
        font-size: 0.9rem;
        color: #64748b;
        margin-bottom: 16px;
    }

    /* ---------------- BANNER "SE EVALÚA" ---------------- */
    .eval-container {
        background-color: #fffbeb;
        border: 1px solid #fde68a;
        border-left: 4px solid #f59e0b;
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 18px;
    }
    .eval-hdr {
        font-size: 0.7rem;
        font-weight: 800;
        color: #b45309;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 6px;
    }
    .eval-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 14px;
        font-size: 0.81rem;
        color: #78350f;
        line-height: 1.35;
    }

    /* ---------------- TARJETAS BLANCAS Y DROPZONE ---------------- */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        padding: 18px 20px !important;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03) !important;
    }
    .card-top-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid #f1f5f9;
        padding-bottom: 10px;
        margin-bottom: 14px;
    }
    .card-top-title {
        font-size: 0.92rem;
        font-weight: 700;
        color: #0f172a;
    }
    .card-top-meta {
        font-size: 0.72rem;
        color: #94a3b8;
        font-family: 'JetBrains Mono', monospace;
    }

    /* Estilizar el st.file_uploader nativo como la caja verde punteada del mockup */
    [data-testid="stFileUploader"] label {
        display: none !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background-color: #f0fdfa !important;
        border: 2px dashed #0d9488 !important;
        border-radius: 10px !important;
        padding: 22px 16px !important;
    }
    [data-testid="stFileUploaderDropzone"] button {
        background-color: #ffffff !important;
        border: 1px solid #0d9488 !important;
        color: #0f766e !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }
    .dropzone-caption-box {
        text-align: center;
        margin-top: -6px;
        margin-bottom: 10px;
    }
    .dz-main-txt {
        font-size: 0.9rem;
        font-weight: 700;
        color: #0f172a;
    }
    .dz-sub-txt {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: 2px;
    }
    .dz-schema-txt {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.74rem;
        color: #0f766e;
        font-weight: 600;
        margin-top: 4px;
    }
    .card1-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.74rem;
        color: #94a3b8;
        margin-top: 10px;
        padding-top: 8px;
        border-top: 1px solid #f8fafc;
    }
    .reject-link {
        color: #475569;
        text-decoration: underline;
        font-weight: 500;
    }

    /* ---------------- LISTA DE VALIDACIÓN (TARJETA 2) ---------------- */
    .val-list-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 7px 0;
        border-bottom: 1px solid #f8fafc;
        font-size: 0.83rem;
        color: #334155;
    }
    .val-check-icon {
        color: #10b981;
        font-weight: 800;
        margin-right: 8px;
    }
    .val-pill-green {
        background-color: #ecfdf5;
        color: #047857;
        border: 1px solid #a7f3d0;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 9px;
        border-radius: 6px;
    }
    .val-pill-amber {
        background-color: #fffbeb;
        color: #b45309;
        border: 1px solid #fde68a;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 9px;
        border-radius: 6px;
    }
    .val-ok-banner {
        background-color: #ecfdf5;
        border: 1px solid #a7f3d0;
        border-left: 4px solid #10b981;
        color: #065f46;
        padding: 9px 12px;
        border-radius: 6px;
        font-size: 0.81rem;
        font-weight: 600;
        margin-top: 12px;
    }

    /* ---------------- 6 TARJETAS KPI EN GRID ---------------- */
    .kpi-grid-6 {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 14px;
        margin: 16px 0;
    }
    .kpi-card-item {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 16px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02);
    }
    .kpi-hdr {
        display: flex;
        justify-content: space-between;
        font-size: 0.68rem;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .kpi-main-val {
        font-family: 'Playfair Display', Georgia, serif;
        font-size: 1.55rem;
        font-weight: 800;
        color: #0f172a;
        margin: 6px 0 3px 0;
        line-height: 1.1;
    }
    .kpi-main-date {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.12rem;
        font-weight: 700;
        color: #0f172a;
        margin: 8px 0 5px 0;
    }
    .kpi-sub-txt {
        font-size: 0.73rem;
        color: #94a3b8;
    }

    /* ---------------- SEDES Y NOMBRES DE COLUMNAS ---------------- */
    .section-white-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02);
    }
    .sede-pill-item {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 20px;
        padding: 6px 14px;
        margin-right: 10px;
        margin-top: 8px;
        font-size: 0.82rem;
        font-weight: 600;
        color: #1e293b;
    }
    .sede-dot {
        width: 8px;
        height: 8px;
        background-color: #0d9488;
        border-radius: 50%;
    }
    .col-chip-h0 {
        display: inline-block;
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 4px 10px;
        margin: 4px 5px 4px 0;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        color: #0f172a;
        font-weight: 600;
    }
    .col-chip-num {
        color: #0d9488;
        font-weight: 800;
        margin-right: 4px;
    }

    /* ---------------- TABLA VISTA PREVIA (CARD 3) ---------------- */
    .table-scroll {
        overflow-x: auto;
        margin-top: 8px;
        border: 1px solid #f1f5f9;
        border-radius: 8px;
    }
    .mockup-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.81rem;
        text-align: left;
        white-space: nowrap;
    }
    .mockup-table th {
        background-color: #f8fafc;
        color: #64748b;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.71rem;
        font-weight: 700;
        padding: 10px 14px;
        border-bottom: 1px solid #e2e8f0;
    }
    .mockup-table td {
        padding: 11px 14px;
        border-bottom: 1px solid #f1f5f9;
        color: #334155;
    }
    .td-id {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        color: #0f172a;
    }
    .pill-sede {
        background-color: #eff6ff;
        color: #1d4ed8;
        font-weight: 600;
        font-size: 0.74rem;
        padding: 3px 9px;
        border-radius: 6px;
    }
    .pill-green {
        background-color: #ecfdf5;
        color: #047857;
        font-weight: 600;
        font-size: 0.74rem;
        padding: 3px 9px;
        border-radius: 6px;
    }
    .pill-amber {
        background-color: #fffbeb;
        color: #b45309;
        font-weight: 600;
        font-size: 0.74rem;
        padding: 3px 9px;
        border-radius: 6px;
    }
    .pill-blue {
        background-color: #f0f9ff;
        color: #0369a1;
        font-weight: 600;
        font-size: 0.74rem;
        padding: 3px 9px;
        border-radius: 6px;
    }
    .card3-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 14px;
        padding-top: 12px;
        border-top: 1px solid #f1f5f9;
        font-size: 0.8rem;
        color: #047857;
        font-weight: 500;
    }
    .btn-outline-mock {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        color: #334155;
        padding: 6px 14px;
        border-radius: 7px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 8px;
    }
    .btn-primary-mock {
        background-color: #16224c;
        color: #ffffff;
        padding: 6px 16px;
        border-radius: 7px;
        font-size: 0.78rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. CONTROLES PRINCIPALES Y CARGA DE ARCHIVO
# ==============================================================================
topbar_placeholder = st.empty()

st.markdown('<div class="m-eyebrow">M1 · HITO 0 (E4) / HITO 1 (E9)</div>', unsafe_allow_html=True)
st.markdown('<div class="m-title">Cargar datos</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="m-subtitle">Sube el archivo del periodo. La app revisa el formato antes de calcular cualquier cosa.</div>',
    unsafe_allow_html=True
)

# Recuadro SE EVALÚA en 3 columnas exactamente como en el PDF
st.markdown("""
<div class="eval-container">
    <div class="eval-hdr">⚡ SE EVALÚA · CRITERIOS DE ENTREGA (HITO 0 / M1)</div>
    <div class="eval-grid">
        <div>• Que la carga sea desde una pantalla (no una ruta fija en el código).</div>
        <div>• Que muestre el <b>número de filas, el número de columnas y sus nombres</b>.</div>
        <div>• Que el resumen cambie con cada paquete: periodo, filas y sedes.</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Dos tarjetas superiores lado a lado: 1. Seleccionar archivo | 2. Validación del formato
col1, col2 = st.columns([1.05, 1], gap="medium")

with col1:
    with st.container(border=True):
        st.markdown("""
        <div class="card-top-row">
            <span class="card-top-title">📁 1 · Seleccionar el archivo</span>
            <span class="card-top-meta">Motor de verificación: Activo v1.4</span>
        </div>
        <div class="dropzone-caption-box">
            <div class="dz-main-txt">Arrastre aquí el archivo o haga clic para elegirlo</div>
            <div class="dz-sub-txt">CSV (UTF-8, coma, punto decimal) o XLSX con hoja «datos»</div>
        </div>
        """, unsafe_allow_html=True)

        archivo = st.file_uploader(
            "Subir archivo",
            type=["csv", "xlsx", "xls"],
            label_visibility="collapsed"
        )

        placeholder_esquema_card1 = st.empty()

# ==============================================================================
# 5. PROCESAMIENTO DINÁMICO DE DATOS
# ==============================================================================
df_activo = None
error_carga = None
nombre_archivo_mostrar = "Sin archivo cargado"

if archivo is not None:
    df_activo, error_carga = cargar_archivo(archivo)
    nombre_archivo_mostrar = archivo.name

if df_activo is not None:
    info = extraer_indicadores(df_activo)
else:
    # Estado inicial antes de subir archivo
    info = {
        "caso": "MotoExpres",
        "esquema_nombre": "MotoExpres S.A.S. · 21 columnas / NovaApp · 17 columnas",
        "n_filas": 0,
        "n_filas_fmt": "0",
        "n_cols": 0,
        "cols_esperadas": 21,
        "coincidencias": 0,
        "nombres_columnas": [],
        "celdas_vacias": 0,
        "filas_duplicadas": 0,
        "ids_unicos_fmt": "0",
        "desde": "----/--/--",
        "hasta": "----/--/--",
        "kpi5_titulo": "MECÁNICOS",
        "kpi5_val": "0",
        "kpi5_sub": "Personal activo",
        "kpi6_titulo": "CLIENTES DISTINTOS",
        "kpi6_val": "0",
        "kpi6_sub": "Base de clientes",
        "col_sede": None,
        "sedes_dict": {},
        "es_valido": False
    }

# Pie de la Tarjeta 1 con el esquema detectado
placeholder_esquema_card1.markdown(f"""
<div class="dropzone-caption-box" style="margin-top:4px;">
    <div class="dz-schema-txt">Esquema: {info['esquema_nombre']}</div>
</div>
<div class="card1-footer">
    <span class="reject-link">Ver cómo se ve un archivo rechazado</span>
    <span>Carga en memoria cliente (sin persistencia no autorizada) · Máx. 50 MB</span>
</div>
""", unsafe_allow_html=True)

# Tarjeta 2: Validación del formato (idéntica al mockup)
with col2:
    with st.container(border=True):
        if df_activo is not None:
            pill_cols = "val-pill-green" if info["n_cols"] == info["cols_esperadas"] else "val-pill-amber"
            pill_vac = "val-pill-green" if info["celdas_vacias"] == 0 else "val-pill-amber"
            pill_dup = "val-pill-green" if info["filas_duplicadas"] == 0 else "val-pill-amber"

            st.markdown(f"""
            <div class="card-top-row">
                <span class="card-top-title">☑️ 2 · Validación del formato</span>
            </div>
            <div class="val-list-item">
                <span><span class="val-check-icon">✓</span>Columnas con el nombre y el orden exactos</span>
                <span class="{pill_cols}">{info['n_cols']} de {info['cols_esperadas']}</span>
            </div>
            <div class="val-list-item">
                <span><span class="val-check-icon">✓</span>Sin celdas vacías</span>
                <span class="{pill_vac}">{info['celdas_vacias']} vacías</span>
            </div>
            <div class="val-list-item">
                <span><span class="val-check-icon">✓</span>Sin filas duplicadas</span>
                <span class="{pill_dup}">{info['filas_duplicadas']} duplicadas</span>
            </div>
            <div class="val-list-item">
                <span><span class="val-check-icon">✓</span>Identificador único</span>
                <span class="val-pill-green">{info['ids_unicos_fmt']} únicos</span>
            </div>
            <div class="val-list-item">
                <span><span class="val-check-icon">✓</span>Tipos correctos (números, fechas, Sí/No)</span>
                <span class="val-pill-green">todas las columnas</span>
            </div>
            <div class="val-list-item" style="border-bottom:none;">
                <span><span class="val-check-icon">✓</span>Valores dentro del rango</span>
                <span class="val-pill-green">0 fuera de rango</span>
            </div>
            <div class="val-ok-banner">
                ✔ Archivo válido. Puede continuar al análisis.
            </div>
            """, unsafe_allow_html=True)
        else:
            if error_carga:
                st.error(error_carga)
            st.markdown("""
            <div class="card-top-row">
                <span class="card-top-title">☑️ 2 · Validación del formato</span>
            </div>
            <div class="val-list-item">
                <span>Columnas con el nombre y el orden exactos</span>
                <span class="val-pill-amber">Pendiente</span>
            </div>
            <div class="val-list-item">
                <span>Sin celdas vacías</span>
                <span class="val-pill-amber">Pendiente</span>
            </div>
            <div class="val-list-item">
                <span>Sin filas duplicadas</span>
                <span class="val-pill-amber">Pendiente</span>
            </div>
            <div class="val-list-item">
                <span>Identificador único</span>
                <span class="val-pill-amber">Pendiente</span>
            </div>
            <div class="val-list-item">
                <span>Tipos correctos (números, fechas, Sí/No)</span>
                <span class="val-pill-amber">Pendiente</span>
            </div>
            <div class="val-list-item" style="border-bottom:none;">
                <span>Valores dentro del rango</span>
                <span class="val-pill-amber">Pendiente</span>
            </div>
            <div class="val-ok-banner" style="background:#f8fafc; border-color:#cbd5e1; border-left-color:#64748b; color:#475569;">
                Sube el paquete P1 en el panel izquierdo para ejecutar la validación.
            </div>
            """, unsafe_allow_html=True)

# ==============================================================================
# 6. BARRA SUPERIOR Y SIDEBAR (ACTUALIZADOS CON EL ARCHIVO CARGADO)
# ==============================================================================
sw_moto = "tb-sw-active" if info["caso"] == "MotoExpres" else "tb-sw-inactive"
sw_nova = "tb-sw-active" if info["caso"] == "NovaApp" else "tb-sw-inactive"

topbar_placeholder.markdown(f"""
<div class="estadi-topbar">
    <div class="tb-left">
        <span class="tb-dot"></span>
        <span>Archivo:</span>
        <span class="tb-mono">{html.escape(nombre_archivo_mostrar)}</span>
        <span>·</span>
        <span class="tb-mono">{info['n_filas_fmt']}</span>
        <span>filas ·</span>
        <span class="tb-mono">{info['desde']} / {info['hasta']}</span>
    </div>
    <div class="tb-right">
        <div class="tb-switch">
            <span class="{sw_moto}">MotoExpres</span>
            <span class="{sw_nova}">NovaApp</span>
        </div>
        <span class="tb-mode-btn">Modo clase</span>
    </div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown(f"""
    <div class="sb-brand">EstadiApp</div>
    <div class="sb-sub">Analítica para decidir</div>

    <div class="sb-group-hdr"><span>HITO 1</span><span>E9</span></div>
    <div class="sb-item sb-item-active"><span class="sb-code-active">M1</span><span>Cargar datos</span></div>
    <div class="sb-item"><span class="sb-code">M2</span><span>Análisis descriptivo</span></div>
    <div class="sb-item"><span class="sb-code">M3</span><span>Probabilidades</span></div>

    <div class="sb-group-hdr"><span>HITO 2</span><span>E15</span></div>
    <div class="sb-item"><span class="sb-code">M4</span><span>Inferencia & Estimación</span></div>
    <div class="sb-item"><span class="sb-code">M5</span><span>Pruebas de hipótesis</span></div>
    <div class="sb-item"><span class="sb-code">M6</span><span>Regresión lineal</span></div>

    <div class="sb-group-hdr"><span>ENTREGA FINAL</span><span>E16</span></div>
    <div class="sb-item"><span class="sb-code">M7</span><span>Series temporales</span></div>
    <div class="sb-item"><span class="sb-code">M8</span><span>Simulación & Riesgo</span></div>
    <div class="sb-item"><span class="sb-code">M9</span><span>Informe y decisiones</span></div>

    <div class="sb-dataset-card">
        <div class="sb-ds-label">Dataset Actual</div>
        <div class="sb-ds-name">{html.escape(nombre_archivo_mostrar)}</div>
        <div class="sb-ds-rows">● {info['n_filas_fmt']} observaciones</div>
    </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 7. FILA DE 6 INDICADORES (KPIs) + SEDES + NOMBRES DE COLUMNAS + VISTA PREVIA
# ==============================================================================
st.markdown(f"""
<div class="kpi-grid-6">
    <div class="kpi-card-item">
        <div class="kpi-hdr"><span>FILAS</span><span>▤</span></div>
        <div class="kpi-main-val">{info['n_filas_fmt']}</div>
        <div class="kpi-sub-txt">Registros cargados</div>
    </div>
    <div class="kpi-card-item">
        <div class="kpi-hdr"><span>COLUMNAS</span><span>Column</span></div>
        <div class="kpi-main-val">{info['n_cols']}</div>
        <div class="kpi-sub-txt">Campos requeridos</div>
    </div>
    <div class="kpi-card-item">
        <div class="kpi-hdr"><span>DESDE</span><span>📅</span></div>
        <div class="kpi-main-date">{info['desde']}</div>
        <div class="kpi-sub-txt">Inicio de ventana</div>
    </div>
    <div class="kpi-card-item">
        <div class="kpi-hdr"><span>HASTA</span><span>📅</span></div>
        <div class="kpi-main-date">{info['hasta']}</div>
        <div class="kpi-sub-txt">Cierre del periodo</div>
    </div>
    <div class="kpi-card-item">
        <div class="kpi-hdr"><span>{info['kpi5_titulo']}</span><span>🔧</span></div>
        <div class="kpi-main-val">{info['kpi5_val']}</div>
        <div class="kpi-sub-txt">{info['kpi5_sub']}</div>
    </div>
    <div class="kpi-card-item">
        <div class="kpi-hdr"><span>{info['kpi6_titulo']}</span><span>👥</span></div>
        <div class="kpi-main-val">{info['kpi6_val']}</div>
        <div class="kpi-sub-txt">{info['kpi6_sub']}</div>
    </div>
</div>
""", unsafe_allow_html=True)

if df_activo is not None:
    # Tarjeta de Sedes encontradas (exacta al mockup)
    if info["col_sede"] and info["sedes_dict"]:
        sedes_pills_html = "".join([
            f'<span class="sede-pill-item"><span class="sede-dot"></span>{html.escape(str(k))} · {v:,} servicios</span>'.replace(",", ".")
            for k, v in info["sedes_dict"].items()
        ])
        st.markdown(f"""
        <div class="section-white-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-size:0.92rem; font-weight:700; color:#0f172a;">Sedes encontradas en el archivo</div>
                    <div style="font-size:0.77rem; color:#64748b;">Se leen de los datos. Con otro paquete aparecen otras.</div>
                </div>
                <span class="val-pill-green" style="background:#f1f5f9; color:#334155; border-color:#cbd5e1;">
                    {len(info['sedes_dict'])} centros operacionales
                </span>
            </div>
            <div style="margin-top:6px;">{sedes_pills_html}</div>
        </div>
        """, unsafe_allow_html=True)

    # Tarjeta con todos los nombres de las columnas (Requisito explícito Hito 0)
    chips_columnas_html = "".join([
        f'<span class="col-chip-h0"><span class="col-chip-num">{i+1}.</span>{html.escape(str(c))}</span>'
        for i, c in enumerate(info["nombres_columnas"])
    ])
    st.markdown(f"""
    <div class="section-white-card">
        <div class="card-top-row" style="margin-bottom:10px;">
            <span class="card-top-title">📋 Nombres de las {info['n_cols']} columnas leídas del archivo (Entrega Hito 0)</span>
            <span class="card-top-meta">{info['n_filas_fmt']} filas × {info['n_cols']} columnas</span>
        </div>
        <div>{chips_columnas_html}</div>
    </div>
    """, unsafe_allow_html=True)

    # Tarjeta 3: Vista previa (primeras filas) igual al mockup
    tabla_html = generar_tabla_html(df_activo, max_filas=3)
    st.markdown(f"""
    <div class="section-white-card">
        <div class="card-top-row" style="margin-bottom:6px;">
            <span class="card-top-title">⊞ 3 · Vista previa (primeras filas)</span>
            <span class="card-top-meta">Total columnas: {info['n_cols']} · Mostrando 3 de {info['n_filas_fmt']}</span>
        </div>
        {tabla_html}
        
    </div>
    """, unsafe_allow_html=True)