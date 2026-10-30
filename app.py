import streamlit as st
import pandas as pd
import numpy as np
import html
from datetime import datetime

# ==============================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="EstadiApp · Analítica para decidir",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Parche preventivo: elimina sangrías en bloques HTML para que Streamlit nunca muestre cuadros negros de código
_st_markdown_orig = st.markdown
def _st_markdown_safe(body, unsafe_allow_html=False, **kwargs):
    if unsafe_allow_html and isinstance(body, str) and "<style>" not in body:
        body = "\n".join(line.lstrip() for line in body.splitlines())
    return _st_markdown_orig(body, unsafe_allow_html=unsafe_allow_html, **kwargs)
st.markdown = _st_markdown_safe

# Inicializar estado de sesión para navegación y persistencia
if "modulo_activo" not in st.session_state:
    st.session_state.modulo_activo = "M1"
if "mostrar_rechazo_demo" not in st.session_state:
    st.session_state.mostrar_rechazo_demo = False
if "hora_carga" not in st.session_state:
    st.session_state.hora_carga = None
if "ultimo_archivo_nombre" not in st.session_state:
    st.session_state.ultimo_archivo_nombre = None

# ==============================================================================
# 2. ESQUEMAS OFICIALES (SECCIÓN 4 Y 5 DE LA GUÍA DEL PROYECTO 259G8F)
# ==============================================================================
COLUMNAS_MOTOEXPRES = [
    "id_servicio", "fecha", "hora_llegada", "dia_semana", "sede",
    "mecanico", "id_cliente", "tipo_cliente", "tipo_vehiculo", "tipo_servicio",
    "tiempo_diagnostico_min", "tiempo_reparacion_h", "repuestos_usados",
    "costo_repuestos_usd", "costo_mano_obra_usd", "costo_total_usd",
    "satisfaccion", "recomendaria", "requirio_garantia", "metodo_pago",
    "canal_reserva"
]

COLUMNAS_NOVAAPP = [
    "id_sesion", "id_usuario", "fecha_hora", "dia_semana", "plataforma",
    "version_app", "pais", "plan", "rango_edad", "tipo_red",
    "duracion_min", "paginas_vistas", "tiempo_carga_s", "crashes",
    "calificacion", "realizo_compra", "contacto_soporte"
]

# ==============================================================================
# 3. FUNCIONES DE LECTURA, VALIDACIÓN Y CÁLCULO (SEPARADAS DE LA INTERFAZ)
# ==============================================================================
def render_html(texto_html):
    """Renderiza HTML en Streamlit eliminando sangrías que Markdown interpretaría como bloque de código."""
    limpio = "\n".join(linea.lstrip() for linea in texto_html.splitlines())
    st.markdown(limpio, unsafe_allow_html=True)


def fmt_num(val, dec=2):
    """Formatea números con coma decimal y punto de miles (estándar es-CO)."""
    if val is None or pd.isna(val):
        return "N/A"
    s = f"{float(val):,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int(val):
    """Formatea enteros con punto de miles."""
    if val is None or pd.isna(val):
        return "0"
    return f"{int(val):,}".replace(",", ".")


def cargar_archivo(archivo_subido):
    """
    Lee dinámicamente un archivo CSV (UTF-8, coma, punto decimal) o XLSX (hoja 'datos').
    Retorna: (DataFrame, mensaje_error)
    """
    nombre = archivo_subido.name.lower()
    try:
        archivo_subido.seek(0)
        if nombre.endswith(".csv"):
            try:
                df = pd.read_csv(archivo_subido, encoding="utf-8", sep=",", decimal=".")
            except UnicodeDecodeError:
                archivo_subido.seek(0)
                df = pd.read_csv(archivo_subido, encoding="latin-1", sep=",", decimal=".")
            return df, None
        elif nombre.endswith(".xlsx") or nombre.endswith(".xls"):
            xls = pd.ExcelFile(archivo_subido)
            if "datos" in xls.sheet_names:
                df = pd.read_excel(archivo_subido, sheet_name="datos")
            else:
                df = pd.read_excel(archivo_subido, sheet_name=xls.sheet_names[0])
            return df, None
        else:
            return None, "Formato no válido. El archivo debe ser .csv o .xlsx."
    except Exception as e:
        return None, f"No se pudo leer el archivo ({archivo_subido.name}): {str(e)}"


def validar_y_resumir_m1(df):
    """
    M1 · Carga y validación (E1):
    Revisa columnas (faltantes, sobrantes, orden), celdas vacías por columna,
    filas duplicadas, identificadores repetidos, tipos de datos legibles y rangos.
    Extrae dinámicamente todos los indicadores sin valores quemados.
    """
    n_filas, n_cols = df.shape
    cols_reales = [str(c).strip() for c in df.columns]
    cols_lower = [c.lower() for c in cols_reales]

    # Detectar caso de negocio según las columnas del archivo
    coinc_me = sum(1 for c in cols_lower if c in COLUMNAS_MOTOEXPRES)
    coinc_na = sum(1 for c in cols_lower if c in COLUMNAS_NOVAAPP)
    if coinc_me >= coinc_na and ("id_servicio" in cols_lower or n_cols >= 19):
        caso = "MotoExpres"
        esquema = COLUMNAS_MOTOEXPRES
    else:
        caso = "NovaApp"
        esquema = COLUMNAS_NOVAAPP

    cols_esperadas = len(esquema)
    errores_detalle = []

    # 1. Revisión de columnas (faltantes, sobrantes y orden exacto)
    faltantes = [c for c in esquema if c not in cols_lower]
    sobrantes = [cols_reales[i] for i, c in enumerate(cols_lower) if c not in esquema]
    orden_exacto = (cols_lower == esquema)
    cols_coinciden = len(esquema) - len(faltantes)

    if faltantes:
        errores_detalle.append(
            f"Faltan columnas obligatorias: {', '.join(faltantes)}"
            + (f" (llegó como: {', '.join(sobrantes)})" if sobrantes else ".")
        )
    elif sobrantes:
        errores_detalle.append(f"Sobran columnas no reconocidas: {', '.join(sobrantes)}.")
    elif not orden_exacto:
        errores_detalle.append("Las columnas están presentes pero no siguen el orden exacto del diccionario.")

    # 2. Revisión de celdas vacías (nulos o cadenas en blanco)
    vacias_por_col = {}
    for col in df.columns:
        n_na = int(df[col].isna().sum())
        if df[col].dtype == object:
            n_blank = int((df[col].dropna().astype(str).str.strip() == "").sum())
        else:
            n_blank = 0
        tot_vac = n_na + n_blank
        if tot_vac > 0:
            vacias_por_col[str(col)] = tot_vac

    celdas_vacias = sum(vacias_por_col.values())
    if celdas_vacias > 0:
        det_vac = ", ".join([f"{c} ({v} vacías)" for c, v in vacias_por_col.items()])
        errores_detalle.append(f"Se encontraron {celdas_vacias} celdas vacías en: {det_vac}.")

    # 3. Revisión de filas duplicadas e identificadores únicos
    filas_duplicadas = int(df.duplicated().sum())
    col_id_esperada = esquema[0]
    col_id_real = df.columns[cols_lower.index(col_id_esperada)] if col_id_esperada in cols_lower else df.columns[0]
    ids_unicos = int(df[col_id_real].dropna().nunique())
    ids_repetidos = int(n_filas - ids_unicos)

    if filas_duplicadas > 0:
        errores_detalle.append(f"Se encontraron {filas_duplicadas} filas duplicadas en el archivo.")
    if ids_repetidos > 0 and filas_duplicadas == 0:
        errores_detalle.append(f"La columna identificadora «{col_id_real}» tiene {ids_repetidos} códigos repetidos.")

    # 4. Revisión de tipos de datos legibles (números y fechas)
    if caso == "MotoExpres":
        cols_num = [
            "tiempo_diagnostico_min", "tiempo_reparacion_h", "repuestos_usados",
            "costo_repuestos_usd", "costo_mano_obra_usd", "costo_total_usd", "satisfaccion"
        ]
        cols_fecha = ["fecha"]
        cols_binarias = ["recomendaria", "requirio_garantia"]
    else:
        cols_num = ["duracion_min", "paginas_vistas", "tiempo_carga_s", "crashes", "calificacion"]
        cols_fecha = ["fecha_hora"]
        cols_binarias = ["realizo_compra", "contacto_soporte"]

    errores_tipo = []
    col_map = {str(c).strip().lower(): c for c in df.columns}

    for cn in cols_num:
        if cn in col_map:
            s_orig = df[col_map[cn]].dropna()
            s_orig = s_orig[s_orig.astype(str).str.strip() != ""]
            s_num = pd.to_numeric(s_orig, errors="coerce")
            fallos = int(s_num.isna().sum())
            if fallos > 0:
                errores_tipo.append(f"{cn} ({fallos} valores no numéricos)")

    for cf in cols_fecha:
        if cf in col_map:
            s_orig = df[col_map[cf]].dropna()
            s_orig = s_orig[s_orig.astype(str).str.strip() != ""]
            s_dt = pd.to_datetime(s_orig, errors="coerce")
            fallos = int(s_dt.isna().sum())
            if fallos > 0:
                errores_tipo.append(f"{cf} ({fallos} fechas ilegibles)")

    for cb in cols_binarias:
        if cb in col_map:
            s_orig = df[col_map[cb]].dropna().astype(str).str.strip()
            s_orig = s_orig[s_orig != ""]
            invalidos = int((~s_orig.isin(["Sí", "No", "Si", "sí", "no"])).sum())
            if invalidos > 0:
                errores_tipo.append(f"{cb} ({invalidos} valores distintos de Sí/No)")

    if errores_tipo:
        errores_detalle.append("Errores de tipo de dato en: " + ", ".join(errores_tipo) + ".")

    # 5. Revisión de rangos de valores
    errores_rango = {}
    if caso == "MotoExpres":
        reglas_rango = [
            ("tiempo_diagnostico_min", lambda x: x > 0),
            ("tiempo_reparacion_h", lambda x: x > 0),
            ("repuestos_usados", lambda x: x >= 0),
            ("costo_repuestos_usd", lambda x: x >= 0),
            ("costo_mano_obra_usd", lambda x: x > 0),
            ("costo_total_usd", lambda x: x > 0),
            ("satisfaccion", lambda x: x.isin([1, 2, 3, 4, 5]))
        ]
    else:
        reglas_rango = [
            ("duracion_min", lambda x: x > 0),
            ("paginas_vistas", lambda x: x >= 1),
            ("tiempo_carga_s", lambda x: x > 0),
            ("crashes", lambda x: x >= 0),
            ("calificacion", lambda x: x.isin([1, 2, 3, 4, 5]))
        ]

    for col_r, cond in reglas_rango:
        if col_r in col_map:
            s_num = pd.to_numeric(df[col_map[col_r]], errors="coerce").dropna()
            if not s_num.empty:
                fuera = int((~cond(s_num)).sum())
                if fuera > 0:
                    errores_rango[col_r] = fuera

    total_fuera_rango = sum(errores_rango.values())
    if total_fuera_rango > 0:
        det_rango = ", ".join([f"{k} ({v} filas)" for k, v in errores_rango.items()])
        errores_detalle.append(f"Valores fuera del rango permitido en: {det_rango}.")

    # Rango de fechas dinámico
    desde, hasta = "N/A", "N/A"
    for cand_f in ["fecha", "fecha_hora"]:
        if cand_f in col_map:
            fechas = pd.to_datetime(df[col_map[cand_f]], errors="coerce").dropna()
            if not fechas.empty:
                desde = fechas.min().strftime("%Y-%m-%d")
                hasta = fechas.max().strftime("%Y-%m-%d")
            break

    # Indicadores y categorías dinámicas según el caso
    if caso == "MotoExpres":
        n_mecanicos = int(df[col_map["mecanico"]].nunique()) if "mecanico" in col_map else 0
        n_clientes = int(df[col_map["id_cliente"]].nunique()) if "id_cliente" in col_map else 0
        kpi5_titulo, kpi5_val, kpi5_sub = "MECÁNICOS", fmt_int(n_mecanicos), "Personal activo"
        kpi6_titulo, kpi6_val, kpi6_sub = "CLIENTES DISTINTOS", fmt_int(n_clientes), "Base de clientes"
        col_grupo = col_map.get("sede")
        titulo_grupos = "Sedes encontradas en el archivo"
        badge_grupos_txt = "centros operacionales"
        unidad_grupo = "servicios"
        versiones_lista = []
    else:
        versiones_lista = sorted([str(v) for v in df[col_map["version_app"]].dropna().unique()]) if "version_app" in col_map else []
        n_usuarios = int(df[col_map["id_usuario"]].nunique()) if "id_usuario" in col_map else 0
        kpi5_titulo = "VERSIONES"
        kpi5_val = ", ".join(versiones_lista) if versiones_lista else "0"
        kpi5_sub = f"{len(versiones_lista)} versiones en el paquete"
        kpi6_titulo, kpi6_val, kpi6_sub = "USUARIOS DISTINTOS", fmt_int(n_usuarios), "Base de usuarios"
        col_grupo = col_map.get("pais")
        titulo_grupos = "Países y versiones encontrados en el archivo"
        badge_grupos_txt = "mercados activos"
        unidad_grupo = "sesiones"

    grupos_dict = {}
    if col_grupo and col_grupo in df.columns:
        # Ordenar alfabéticamente o por conteo manteniendo lectura limpia
        conteos = df[col_grupo].value_counts()
        grupos_dict = conteos.to_dict()

    grupos_alfabeticos = sorted([str(k) for k in grupos_dict.keys()])

    es_valido = (
        orden_exacto
        and (celdas_vacias == 0)
        and (filas_duplicadas == 0)
        and (ids_repetidos == 0)
        and (len(errores_tipo) == 0)
        and (total_fuera_rango == 0)
    )

    return {
        "caso": caso,
        "esquema_nombre": "MotoExpres S.A.S. · 21 columnas" if caso == "MotoExpres" else "NovaApp · 17 columnas",
        "n_filas": n_filas,
        "n_filas_fmt": fmt_int(n_filas),
        "n_cols": n_cols,
        "cols_esperadas": cols_esperadas,
        "cols_coinciden": cols_coinciden,
        "orden_exacto": orden_exacto,
        "nombres_columnas": cols_reales,
        "celdas_vacias": celdas_vacias,
        "vacias_por_col": vacias_por_col,
        "filas_duplicadas": filas_duplicadas,
        "ids_unicos": ids_unicos,
        "ids_unicos_fmt": fmt_int(ids_unicos),
        "ids_repetidos": ids_repetidos,
        "errores_tipo": errores_tipo,
        "total_fuera_rango": total_fuera_rango,
        "errores_rango": errores_rango,
        "errores_detalle": errores_detalle,
        "desde": desde,
        "hasta": hasta,
        "kpi5_titulo": kpi5_titulo,
        "kpi5_val": kpi5_val,
        "kpi5_sub": kpi5_sub,
        "kpi6_titulo": kpi6_titulo,
        "kpi6_val": kpi6_val,
        "kpi6_sub": kpi6_sub,
        "titulo_grupos": titulo_grupos,
        "badge_grupos_txt": badge_grupos_txt,
        "unidad_grupo": unidad_grupo,
        "grupos_dict": grupos_dict,
        "grupos_alfabeticos": grupos_alfabeticos,
        "versiones_lista": versiones_lista,
        "es_valido": es_valido
    }


def calcular_medidas_variable(serie):
    """
    Calcula las 10 medidas descriptivas obligatorias con las convenciones de la Sección 7:
    - Desviación estándar muestral (ddof=1)
    - Cuartiles con interpolación lineal
    - Sesgo ajustado (.skew())
    - Atípicos con regla 1.5 * IQR
    """
    s = pd.to_numeric(serie, errors="coerce").dropna()
    n = int(len(s))
    if n == 0:
        return None
    media = float(s.mean())
    mediana = float(s.median())
    desv = float(s.std(ddof=1)) if n > 1 else 0.0
    cv = float((desv / media) * 100.0) if media != 0 else 0.0
    q1 = float(s.quantile(0.25, interpolation="linear"))
    q3 = float(s.quantile(0.75, interpolation="linear"))
    iqr = float(q3 - q1)
    minimo = float(s.min())
    maximo = float(s.max())
    sesgo = float(s.skew()) if n > 2 else 0.0
    lim_inf = q1 - 1.5 * iqr
    lim_sup = q3 + 1.5 * iqr
    atipicos = int(((s < lim_inf) | (s > lim_sup)).sum())

    return {
        "n": n,
        "media": media,
        "mediana": mediana,
        "desv": desv,
        "cv": cv,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "min": minimo,
        "max": maximo,
        "sesgo": sesgo,
        "atipicos": atipicos,
        "lim_inf": lim_inf,
        "lim_sup": lim_sup,
        "serie": s
    }


def analizar_descriptivo_m2(df, caso, var_seleccionada):
    """
    M2 · Análisis descriptivo (E2–E4):
    Calcula medidas principales, medidas de apoyo, frecuencias, análisis por grupo
    y variable ordinal directamente del DataFrame filtrado.
    """
    medidas_sel = calcular_medidas_variable(df[var_seleccionada])

    # Medidas de apoyo según el caso
    apoyo = []
    if caso == "MotoExpres":
        for v_ap, u_ap in [("costo_total_usd", "USD"), ("tiempo_reparacion_h", "h"), ("tiempo_diagnostico_min", "min")]:
            if v_ap in df.columns:
                m = calcular_medidas_variable(df[v_ap])
                if m:
                    apoyo.append({"variable": v_ap, "unidad": u_ap, **m})
        col_freq = "tipo_servicio" if "tipo_servicio" in df.columns else df.columns[4]
        col_box_num = "costo_total_usd" if "costo_total_usd" in df.columns else var_seleccionada
        col_box_cat = "tipo_servicio" if "tipo_servicio" in df.columns else col_freq
        titulo_box = "Costo por tipo de servicio (USD)"
        col_ordinal = "satisfaccion"
        # Grupo 1: Sede con mayor costo medio
        if "sede" in df.columns and "costo_total_usd" in df.columns:
            medias_sede = df.groupby("sede")["costo_total_usd"].mean()
            sede_max = str(medias_sede.idxmax())
            val_sede_max = float(medias_sede.max())
            grupo1_info = ("SEDE CON MAYOR COSTO MEDIO", sede_max, f"{fmt_num(val_sede_max, 2)} USD")
        else:
            grupo1_info = ("SEDE CON MAYOR COSTO MEDIO", "N/A", "-")

        # Grupo 2: Mecánico más consistente (menor CV del costo)
        if "mecanico" in df.columns and "costo_total_usd" in df.columns:
            g_mec = df.groupby("mecanico")["costo_total_usd"].agg(["mean", lambda x: x.std(ddof=1)])
            g_mec.columns = ["mean", "std"]
            g_mec = g_mec[g_mec["mean"] > 0].dropna()
            if not g_mec.empty:
                g_mec["cv"] = (g_mec["std"] / g_mec["mean"]) * 100.0
                mec_min = str(g_mec["cv"].idxmin())
                cv_min = float(g_mec["cv"].min())
                grupo2_info = ("MECÁNICO MÁS CONSISTENTE (MENOR CV)", mec_min, f"CV {fmt_num(cv_min, 2)} %")
            else:
                grupo2_info = ("MECÁNICO MÁS CONSISTENTE (MENOR CV)", "N/A", "-")
        else:
            grupo2_info = ("MECÁNICO MÁS CONSISTENTE (MENOR CV)", "N/A", "-")

    else:
        for v_ap, u_ap in [("duracion_min", "min"), ("tiempo_carga_s", "s"), ("paginas_vistas", "págs")]:
            if v_ap in df.columns:
                m = calcular_medidas_variable(df[v_ap])
                if m:
                    apoyo.append({"variable": v_ap, "unidad": u_ap, **m})
        col_freq = "plataforma" if "plataforma" in df.columns else df.columns[4]
        col_box_num = "tiempo_carga_s" if "tiempo_carga_s" in df.columns else var_seleccionada
        col_box_cat = "plataforma" if "plataforma" in df.columns else col_freq
        titulo_box = "Tiempo de carga por plataforma (s)"
        col_ordinal = "calificacion"

        # Grupo 1: Plataforma con carga más estable (menor CV de tiempo_carga_s)
        if "plataforma" in df.columns and "tiempo_carga_s" in df.columns:
            g_plat = df.groupby("plataforma")["tiempo_carga_s"].agg(["mean", lambda x: x.std(ddof=1)])
            g_plat.columns = ["mean", "std"]
            g_plat = g_plat[g_plat["mean"] > 0].dropna()
            if not g_plat.empty:
                g_plat["cv"] = (g_plat["std"] / g_plat["mean"]) * 100.0
                plat_min = str(g_plat["cv"].idxmin())
                cv_min = float(g_plat["cv"].min())
                grupo1_info = ("PLATAFORMA CON CARGA MÁS ESTABLE (MENOR CV)", plat_min, f"CV {fmt_num(cv_min, 2)} %")
            else:
                grupo1_info = ("PLATAFORMA CON CARGA MÁS ESTABLE (MENOR CV)", "N/A", "-")
        else:
            grupo1_info = ("PLATAFORMA CON CARGA MÁS ESTABLE", "N/A", "-")

        # Grupo 2: Plan o País con más sesiones
        if "plan" in df.columns:
            vc_plan = df["plan"].value_counts()
            plan_top = str(vc_plan.index[0])
            pct_top = (vc_plan.iloc[0] / len(df)) * 100.0
            grupo2_info = ("PLAN CON MAYOR USO", plan_top, f"{fmt_num(pct_top, 1)} % ({fmt_int(vc_plan.iloc[0])} sesiones)")
        else:
            grupo2_info = ("PLAN CON MAYOR USO", "N/A", "-")

    # Frecuencias
    frecuencias_lista = []
    if col_freq in df.columns:
        vc = df[col_freq].value_counts()
        total_f = len(df)
        for cat, cnt in vc.items():
            frecuencias_lista.append({
                "categoria": str(cat),
                "conteo": int(cnt),
                "porcentaje": (float(cnt) / total_f) * 100.0 if total_f > 0 else 0.0
            })

    # Datos para Boxplot por grupo
    box_datos = []
    if col_box_cat in df.columns and col_box_num in df.columns:
        for cat, grp in df.groupby(col_box_cat):
            s_b = pd.to_numeric(grp[col_box_num], errors="coerce").dropna()
            if len(s_b) > 0:
                q1_b = float(s_b.quantile(0.25, interpolation="linear"))
                med_b = float(s_b.median())
                q3_b = float(s_b.quantile(0.75, interpolation="linear"))
                iqr_b = q3_b - q1_b
                w_low = float(s_b[s_b >= (q1_b - 1.5 * iqr_b)].min()) if len(s_b) > 0 else float(s_b.min())
                w_high = float(s_b[s_b <= (q3_b + 1.5 * iqr_b)].max()) if len(s_b) > 0 else float(s_b.max())
                n_out = int(((s_b < (q1_b - 1.5 * iqr_b)) | (s_b > (q3_b + 1.5 * iqr_b))).sum())
                box_datos.append({
                    "categoria": str(cat),
                    "min": w_low,
                    "q1": q1_b,
                    "mediana": med_b,
                    "q3": q3_b,
                    "max": w_high,
                    "abs_min": float(s_b.min()),
                    "abs_max": float(s_b.max()),
                    "outliers": n_out
                })
        box_datos.sort(key=lambda x: x["mediana"])

    # Variable ordinal (satisfaccion o calificacion)
    ord_moda, ord_media = "N/A", 0.0
    if col_ordinal in df.columns:
        s_ord = pd.to_numeric(df[col_ordinal], errors="coerce").dropna()
        if not s_ord.empty:
            modas = s_ord.mode()
            ord_moda = str(int(modas.iloc[0])) if not modas.empty else "N/A"
            ord_media = float(s_ord.mean())

    return {
        "medidas_sel": medidas_sel,
        "apoyo": apoyo,
        "col_freq": col_freq,
        "frecuencias": frecuencias_lista,
        "titulo_box": titulo_box,
        "col_box_num": col_box_num,
        "col_box_cat": col_box_cat,
        "box_datos": box_datos,
        "grupo1_info": grupo1_info,
        "grupo2_info": grupo2_info,
        "col_ordinal": col_ordinal,
        "ord_moda": ord_moda,
        "ord_media": ord_media
    }


def analizar_probabilidad_m3(df, caso):
    """
    M3 · Probabilidad, condicional y Bayes (E6–E7):
    Calcula probabilidades básicas con regla de la suma, tabla de contingencia,
    condicionales para TODOS los grupos del archivo, teorema de Bayes e independencia
    con la regla |P(A|B) - P(A)| < 0,02.
    """
    n_total = len(df)
    if n_total == 0:
        return None

    if caso == "MotoExpres":
        cond_a = df["tipo_vehiculo"].astype(str).str.strip() == "Moto"
        cond_b = pd.to_numeric(df["satisfaccion"], errors="coerce") >= 4
        nombre_a = "Moto"
        nombre_b = "Satisfacción ≥ 4"

        col_grupo_cont = "mecanico"
        col_evento_cont = "requirio_garantia"
        es_evento = df[col_evento_cont].astype(str).str.strip().isin(["Sí", "Si"])
        nombre_evento = "Garantía"
        titulo_cont = "mecanico × requirio_garantia"
    else:
        cond_a = df["plataforma"].astype(str).str.strip() == "Android"
        cond_b = pd.to_numeric(df["crashes"], errors="coerce") >= 1
        nombre_a = "Android"
        nombre_b = "Crash ≥ 1"

        col_grupo_cont = "plataforma"
        col_evento_cont = "crashes"
        es_evento = pd.to_numeric(df["crashes"], errors="coerce") >= 1
        nombre_evento = "Crash"
        titulo_cont = "plataforma × crash (sí/no)"

    p_a = float(cond_a.mean())
    p_b = float(cond_b.mean())
    p_ab = float((cond_a & cond_b).mean())
    p_union_formula = p_a + p_b - p_ab
    p_union_directa = float((cond_a | cond_b).mean())

    # Tabla de contingencia y condicionales para TODOS los grupos del archivo
    df_temp = pd.DataFrame({
        "grupo": df[col_grupo_cont].astype(str).str.strip(),
        "evento": es_evento
    })
    filas_contingencia = []
    for grp, sub in df_temp.groupby("grupo"):
        tot_g = int(len(sub))
        si_g = int(sub["evento"].sum())
        no_g = tot_g - si_g
        p_cond = float(si_g / tot_g) if tot_g > 0 else 0.0
        p_prior = float(tot_g / n_total)
        filas_contingencia.append({
            "grupo": str(grp),
            "si": si_g,
            "no": no_g,
            "total": tot_g,
            "pct_total": (tot_g / n_total) * 100.0,
            "p_cond": p_cond,
            "p_prior": p_prior
        })

    # Ordenar por nombre de grupo para presentación consistente, pero identificar mayor y menor
    filas_contingencia.sort(key=lambda x: x["grupo"])
    grupo_mayor = max(filas_contingencia, key=lambda x: x["p_cond"]) if filas_contingencia else None
    grupo_menor = min(filas_contingencia, key=lambda x: x["p_cond"]) if filas_contingencia else None

    # Teorema de Bayes
    p_evento_total = float(es_evento.mean())
    if caso == "MotoExpres" and grupo_mayor:
        # En MotoExpres: P(mecánico con más garantías | garantía) frente a P(ese mecánico)
        target_bayes = grupo_mayor
    elif caso == "NovaApp":
        # En NovaApp: P(Android | crash) frente a P(Android)
        cand_and = [r for r in filas_contingencia if r["grupo"].lower() == "android"]
        target_bayes = cand_and[0] if cand_and else (grupo_mayor if grupo_mayor else None)
    else:
        target_bayes = grupo_mayor

    if target_bayes and p_evento_total > 0:
        b_grupo = target_bayes["grupo"]
        b_prior = target_bayes["p_prior"]
        b_lik = target_bayes["p_cond"]
        b_post = (b_lik * b_prior) / p_evento_total
        b_factor = (b_post / b_prior) if b_prior > 0 else 1.0
    else:
        b_grupo, b_prior, b_lik, b_post, b_factor = "N/A", 0.0, 0.0, 0.0, 1.0

    # Evaluación de Independencia: regla |P(A|B) - P(A)| < 0,02
    pares_indep = []
    if caso == "MotoExpres":
        # 1. P(Satisf ≥ 4 | Moto) vs P(Satisf ≥ 4)
        p_sat_moto = float(cond_b[cond_a].mean()) if cond_a.sum() > 0 else 0.0
        pares_indep.append(("P(Satisf ≥ 4 | Moto)", p_sat_moto, "P(Satisf ≥ 4)", p_b, "ser vehículo Moto", "la satisfacción ≥ 4"))

        # 2. P(Recomienda | Nequi) vs P(Recomienda)
        es_rec = df["recomendaria"].astype(str).str.strip().isin(["Sí", "Si"])
        es_nequi = df["metodo_pago"].astype(str).str.strip() == "Nequi"
        p_rec = float(es_rec.mean())
        p_rec_nequi = float(es_rec[es_nequi].mean()) if es_nequi.sum() > 0 else 0.0
        pares_indep.append(("P(Recomienda | Nequi)", p_rec_nequi, "P(Recomienda)", p_rec, "pagar con Nequi", "recomendar el taller"))

        # 3. P(Satisf ≥ 4 | Garantía) vs P(Satisf ≥ 4)
        p_sat_gar = float(cond_b[es_evento].mean()) if es_evento.sum() > 0 else 0.0
        pares_indep.append(("P(Satisf ≥ 4 | Garantía)", p_sat_gar, "P(Satisf ≥ 4)", p_b, "requerir garantía", "la satisfacción ≥ 4"))
    else:
        # 1. P(Compra | Android) vs P(Compra)
        es_compra = df["realizo_compra"].astype(str).str.strip().isin(["Sí", "Si"])
        p_compra = float(es_compra.mean())
        p_compra_and = float(es_compra[cond_a].mean()) if cond_a.sum() > 0 else 0.0
        pares_indep.append(("P(Compra | Android)", p_compra_and, "P(Compra)", p_compra, "usar Android", "realizar una compra"))

        # 2. P(Crash | Android) vs P(Crash)
        p_crash_and = float(cond_b[cond_a].mean()) if cond_a.sum() > 0 else 0.0
        pares_indep.append(("P(Crash | Android)", p_crash_and, "P(Crash)", p_b, "usar Android", "sufrir un crash"))

    resultados_indep = []
    for lbl_cond, val_cond, lbl_base, val_base, ctx_cond, ctx_ev in pares_indep:
        diff = abs(val_cond - val_base)
        es_indep = diff < 0.02
        if es_indep:
            veredicto = "Prácticamente independientes"
            explicacion = f"|{fmt_num(val_cond, 4)} − {fmt_num(val_base, 4)}| = {fmt_num(diff, 4)} < 0,02: {ctx_cond} no altera significativamente la probabilidad de {ctx_ev}."
        else:
            veredicto = "Dependientes"
            sentido = "aumenta" if val_cond > val_base else "reduce"
            explicacion = f"|{fmt_num(val_cond, 4)} − {fmt_num(val_base, 4)}| = {fmt_num(diff, 4)} ≥ 0,02: {ctx_cond} {sentido} la probabilidad de {ctx_ev} (de {fmt_num(val_base*100, 1)} % a {fmt_num(val_cond*100, 1)} %)."
        resultados_indep.append({
            "lbl_cond": lbl_cond,
            "val_cond": val_cond,
            "lbl_base": lbl_base,
            "val_base": val_base,
            "diff": diff,
            "es_indep": es_indep,
            "veredicto": veredicto,
            "explicacion": explicacion
        })

    return {
        "nombre_a": nombre_a,
        "nombre_b": nombre_b,
        "p_a": p_a,
        "p_b": p_b,
        "p_ab": p_ab,
        "p_union_formula": p_union_formula,
        "p_union_directa": p_union_directa,
        "titulo_cont": titulo_cont,
        "col_grupo_cont": col_grupo_cont,
        "nombre_evento": nombre_evento,
        "filas_contingencia": filas_contingencia,
        "grupo_mayor": grupo_mayor,
        "grupo_menor": grupo_menor,
        "p_evento_total": p_evento_total,
        "b_grupo": b_grupo,
        "b_prior": b_prior,
        "b_lik": b_lik,
        "b_post": b_post,
        "b_factor": b_factor,
        "resultados_indep": resultados_indep
    }


# ==============================================================================
# 4. GENERADORES VISUALES SOFT UI (TABLAS Y GRÁFICOS SVG FIELES AL MOCKUP)
# ==============================================================================
def generar_tabla_preview_html(df, max_filas=10):
    """Genera la tabla HTML de vista previa con estilo Soft UI y píldoras de color."""
    sub_df = df.head(max_filas)
    ths = "".join([f"<th>{html.escape(str(c).upper())}</th>" for c in sub_df.columns])

    trs = []
    for _, fila in sub_df.iterrows():
        tds = []
        for col_name, val in fila.items():
            col_low = str(col_name).lower()
            texto = html.escape(str(val))
            if col_low in ["id_servicio", "id_sesion"]:
                tds.append(f'<td class="td-id">{texto}</td>')
            elif col_low in ["sede", "pais", "plataforma"]:
                tds.append(f'<td><span class="pill-lavender">{texto}</span></td>')
            elif col_low in ["tipo_cliente", "plan"]:
                clase_p = "pill-mint"
                if "nuevo" in texto.lower() or "free" in texto.lower():
                    clase_p = "pill-amber"
                elif "recurrente" in texto.lower() or "pro" in texto.lower() or "frecuente" in texto.lower():
                    clase_p = "pill-lavender"
                tds.append(f'<td><span class="{clase_p}">{texto}</span></td>')
            elif col_low in ["recomendaria", "requirio_garantia", "realizo_compra", "contacto_soporte"]:
                clase_b = "pill-mint" if texto.lower() in ["sí", "si"] else "pill-slate"
                tds.append(f'<td><span class="{clase_b}">{texto}</span></td>')
            else:
                tds.append(f"<td>{texto}</td>")
        trs.append(f"<tr>{''.join(tds)}</tr>")

    return f'<div class="table-scroll"><table class="soft-table"><thead><tr>{ths}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def generar_histograma_svg(serie, nombre_var, unidad=""):
    """
    Genera el histograma Soft UI en SVG con ejes rotulados, conteos sobre barras,
    barra modal resaltada en violeta intenso y pie de resumen como en Sin título-1-3.pdf (pág. 2).
    """
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if len(s) == 0:
        return "<div>Sin datos numéricos para graficar.</div>", "N/A"

    counts, edges = np.histogram(s, bins=8)
    max_c = int(counts.max()) if len(counts) > 0 else 1
    idx_max = int(np.argmax(counts))
    moda_aprox = f"{fmt_num(edges[idx_max], 1)} – {fmt_num(edges[idx_max+1], 1)} {unidad}".strip()

    w, h = 620, 265
    pad_l, pad_r, pad_t, pad_b = 48, 18, 24, 48
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b
    bw = plot_w / len(counts)

    lineas_grid = []
    for i in range(5):
        val_y = int(round(max_c * i / 4))
        y = pad_t + plot_h * (1 - i / 4)
        lineas_grid.append(
            f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{y:.1f}" y2="{y:.1f}" stroke="#eef0f6" stroke-width="1"/>'
            f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" fill="#94a3b8" font-size="10.5" font-family="Inter, sans-serif">{fmt_int(val_y)}</text>'
        )

    barras = []
    for i, c in enumerate(counts):
        bh = (c / max_c) * (plot_h - 14) if max_c > 0 else 0
        x = pad_l + i * bw + bw * 0.14
        bar_w = bw * 0.72
        y = pad_t + plot_h - bh
        color_fill = "#5b4bc4" if i == idx_max else "#a599f9"
        lbl_rango = f"{edges[i]:.0f}-{edges[i+1]:.0f}" if (edges[-1] - edges[0]) >= 15 else f"{edges[i]:.1f}-{edges[i+1]:.1f}"
        barras.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="5" fill="{color_fill}"/>'
            f'<text x="{x + bar_w/2:.1f}" y="{y - 6:.1f}" text-anchor="middle" fill="#475569" font-size="10.5" font-weight="700" font-family="JetBrains Mono, monospace">{fmt_int(c)}</text>'
            f'<text x="{x + bar_w/2:.1f}" y="{pad_t + plot_h + 18:.1f}" text-anchor="middle" fill="#64748b" font-size="10" font-family="JetBrains Mono, monospace">{lbl_rango}</text>'
        )

    # Títulos de ejes
    eje_x_lbl = f'<text x="{pad_l + plot_w/2:.1f}" y="{h - 6}" text-anchor="middle" fill="#64748b" font-size="11" font-weight="600" font-family="Inter, sans-serif">Intervalos de {html.escape(nombre_var)} ({html.escape(unidad)})</text>'
    eje_y_lbl = f'<text x="14" y="{pad_t + plot_h/2:.1f}" text-anchor="middle" fill="#64748b" font-size="11" font-weight="600" font-family="Inter, sans-serif" transform="rotate(-90 14 {pad_t + plot_h/2:.1f})">Frecuencia (n)</text>'

    svg = f'<svg viewBox="0 0 {w} {h}" style="width:100%; height:auto; display:block;">{"".join(lineas_grid)}{"".join(barras)}{eje_x_lbl}{eje_y_lbl}</svg>'
    return svg, moda_aprox


def generar_boxplot_svg(box_datos, nombre_num, nombre_cat):
    """
    Genera el Boxplot horizontal por grupo en SVG con estilo Soft UI idéntico al mockup
    (cajas lavanda con borde morado, línea de mediana ámbar y bigotes).
    """
    if not box_datos:
        return "<div>Sin datos suficientes para el boxplot por grupo.</div>"

    rh = 32
    pad_l, pad_r, pad_t, pad_b = 135, 24, 14, 42
    w = 600
    h = len(box_datos) * rh + pad_t + pad_b
    mn = min(d["min"] for d in box_datos)
    mx = max(d["max"] for d in box_datos)
    if mx <= mn:
        mx = mn + 1.0

    def pos_x(val):
        return pad_l + (w - pad_l - pad_r) * ((val - mn) / (mx - mn))

    grid_svg = []
    for i in range(5):
        v = mn + (mx - mn) * (i / 4)
        gx = pos_x(v)
        dec_tick = 0 if (mx - mn) >= 20 else 1
        grid_svg.append(
            f'<line x1="{gx:.1f}" x2="{gx:.1f}" y1="{pad_t}" y2="{h - pad_b}" stroke="#eef0f6" stroke-width="1"/>'
            f'<text x="{gx:.1f}" y="{h - pad_b + 16}" text-anchor="middle" fill="#94a3b8" font-size="10.5" font-family="JetBrains Mono, monospace">{fmt_num(v, dec_tick)}</text>'
        )

    filas_svg = []
    for i, d in enumerate(box_datos):
        cy = pad_t + i * rh + rh / 2
        x_min, x_q1, x_med, x_q3, x_max = pos_x(d["min"]), pos_x(d["q1"]), pos_x(d["mediana"]), pos_x(d["q3"]), pos_x(d["max"])
        bw_box = max(3.0, x_q3 - x_q1)
        filas_svg.append(
            f'<text x="{pad_l - 10}" y="{cy + 4:.1f}" text-anchor="end" fill="#334155" font-size="11.5" font-weight="600" font-family="Inter, sans-serif">{html.escape(d["categoria"][:18])}</text>'
            f'<line x1="{x_min:.1f}" x2="{x_max:.1f}" y1="{cy:.1f}" y2="{cy:.1f}" stroke="#6c5ce7" stroke-width="1.5"/>'
            f'<line x1="{x_min:.1f}" x2="{x_min:.1f}" y1="{cy - 5:.1f}" y2="{cy + 5:.1f}" stroke="#6c5ce7" stroke-width="1.5"/>'
            f'<line x1="{x_max:.1f}" x2="{x_max:.1f}" y1="{cy - 5:.1f}" y2="{cy + 5:.1f}" stroke="#6c5ce7" stroke-width="1.5"/>'
            f'<rect x="{x_q1:.1f}" y="{cy - 8:.1f}" width="{bw_box:.1f}" height="16" rx="3" fill="#dcd6ff" stroke="#6c5ce7" stroke-width="1.4"/>'
            f'<line x1="{x_med:.1f}" x2="{x_med:.1f}" y1="{cy - 8:.1f}" y2="{cy + 8:.1f}" stroke="#f59e0b" stroke-width="3"/>'
        )

    eje_x_lbl = f'<text x="{pad_l + (w - pad_l - pad_r)/2:.1f}" y="{h - 6}" text-anchor="middle" fill="#64748b" font-size="11" font-weight="600" font-family="Inter, sans-serif">{html.escape(nombre_num)} por {html.escape(nombre_cat)}</text>'
    return f'<svg viewBox="0 0 {w} {h}" style="width:100%; height:auto; display:block;">{"".join(grid_svg)}{"".join(filas_svg)}{eje_x_lbl}</svg>'


# ==============================================================================
# 5. ESTILOS CSS SOFT UI (FIEL AL MOCKUP DEL USUARIO: SIN TÍTULO-1-3.PDF)
# ==============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

    /* Fondo general Soft UI Lavanda/Gris muy claro */
    .stApp {
        background-color: #f6f7fb !important;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        color: #1e293b !important;
    }
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 1.2rem !important;
    }
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 2.8rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }

    /* ---------------- BARRA LATERAL CLARA (SOFT UI) ---------------- */
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #eef0f6 !important;
        min-width: 255px !important;
        max-width: 255px !important;
        box-shadow: 4px 0 20px rgba(108, 92, 231, 0.03) !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    .sb-brand-wrap {
        display: flex;
        align-items: center;
        gap: 11px;
        padding-bottom: 14px;
        margin-bottom: 10px;
        border-bottom: 1px solid #f1f5f9;
    }
    .sb-logo-circle {
        width: 38px;
        height: 38px;
        border-radius: 12px;
        background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%);
        color: #6c5ce7;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 1.1rem;
        box-shadow: 0 2px 6px rgba(108, 92, 231, 0.12);
    }
    .sb-brand-title {
        font-size: 1.25rem;
        font-weight: 800;
        color: #1e293b;
        line-height: 1.1;
    }
    .sb-brand-sub {
        font-size: 0.72rem;
        color: #94a3b8;
        font-weight: 500;
    }
    .sb-hito-hdr {
        font-size: 0.66rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.9px;
        color: #6c5ce7;
        margin: 14px 0 6px 4px;
        display: flex;
        align-items: center;
        gap: 5px;
    }
    .sb-hito-hdr-muted {
        font-size: 0.66rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.9px;
        color: #10b981;
        margin: 14px 0 6px 4px;
    }
    .sb-hito-hdr-amber {
        font-size: 0.66rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.9px;
        color: #f59e0b;
        margin: 14px 0 6px 4px;
    }

    /* Botones de navegación en Sidebar estilo Soft UI */
    [data-testid="stSidebar"] .stButton > button {
        width: 100% !important;
        justify-content: flex-start !important;
        text-align: left !important;
        border-radius: 11px !important;
        padding: 9px 13px !important;
        font-size: 0.83rem !important;
        font-weight: 600 !important;
        border: none !important;
        margin-bottom: 3px !important;
        transition: all 0.18s ease !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #6c5ce7 0%, #5b4bc4 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 12px rgba(108, 92, 231, 0.28) !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
        background-color: transparent !important;
        color: #475569 !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
        background-color: #f3f0ff !important;
        color: #6c5ce7 !important;
    }

    .sb-locked-item {
        display: flex;
        align-items: center;
        gap: 9px;
        padding: 7px 12px;
        border-radius: 10px;
        font-size: 0.8rem;
        color: #94a3b8;
        font-weight: 500;
        margin-bottom: 2px;
    }
    .sb-dataset-soft {
        background-color: #f3f1ff;
        border: 1px solid #e4dfff;
        border-radius: 14px;
        padding: 13px 14px;
        margin-top: 18px;
    }
    .sb-ds-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.68rem;
        color: #64748b;
        font-weight: 700;
    }
    .sb-ds-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        display: inline-block;
    }
    .sb-ds-file {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.77rem;
        font-weight: 700;
        color: #1e293b;
        margin: 4px 0 2px 0;
        word-break: break-all;
    }
    .sb-ds-obs {
        font-size: 0.72rem;
        color: #64748b;
        font-weight: 500;
    }

    /* ---------------- TOPBAR SUPERIOR SOFT UI ---------------- */
    .soft-topbar {
        background-color: #ffffff;
        border: 1px solid #eef0f6;
        border-radius: 16px;
        padding: 9px 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 18px;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.03);
        flex-wrap: wrap;
        gap: 10px;
    }
    .tb-file-pill {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 6px 14px;
        display: inline-flex;
        align-items: center;
        gap: 10px;
        font-size: 0.8rem;
        color: #475569;
    }
    .tb-file-name {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        color: #0f172a;
    }
    .tb-right-group {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .tb-seg-box {
        background-color: #f1f5f9;
        padding: 3px;
        border-radius: 12px;
        display: inline-flex;
        gap: 3px;
    }
    .tb-seg-on {
        background-color: #ffffff;
        color: #5b4bc4;
        font-size: 0.76rem;
        font-weight: 700;
        padding: 5px 14px;
        border-radius: 9px;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.06);
    }
    .tb-seg-off {
        color: #64748b;
        font-size: 0.76rem;
        font-weight: 600;
        padding: 5px 14px;
        border-radius: 9px;
    }
    .tb-mint-btn {
        background-color: #6ee7b7;
        color: #064e3b;
        font-size: 0.75rem;
        font-weight: 800;
        padding: 6px 14px;
        border-radius: 12px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .tb-avatar {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        background-color: #5b4bc4;
        color: #ffffff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        font-weight: 700;
    }

    /* ---------------- ENCABEZADO DE MÓDULO ---------------- */
    .soft-eyebrow-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background-color: #ede9fe;
        color: #5b4bc4;
        font-size: 0.7rem;
        font-weight: 800;
        padding: 4px 12px;
        border-radius: 999px;
        letter-spacing: 0.6px;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .soft-h1-row {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        flex-wrap: wrap;
        gap: 10px;
        margin-bottom: 16px;
    }
    .soft-h1 {
        font-size: 1.95rem;
        font-weight: 800;
        color: #0f172a;
        margin: 0;
        letter-spacing: -0.4px;
        line-height: 1.15;
    }
    .soft-sub {
        font-size: 0.88rem;
        color: #64748b;
        margin-top: 4px;
    }
    .engine-badge {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 999px;
        padding: 5px 14px;
        font-size: 0.75rem;
        color: #475569;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.02);
    }

    /* ---------------- BANNER "SE EVALÚA" SOFT LAVENDER ---------------- */
    .soft-eval-box {
        background-color: #f3f1ff;
        border: 1px solid #e4dfff;
        border-radius: 18px;
        padding: 16px 20px;
        margin-bottom: 20px;
    }
    .soft-eval-hdr {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.9rem;
        font-weight: 800;
        color: #1e293b;
        margin-bottom: 12px;
    }
    .soft-eval-tag {
        background-color: #e0dbff;
        color: #5b4bc4;
        font-size: 0.65rem;
        font-weight: 800;
        padding: 3px 9px;
        border-radius: 6px;
        letter-spacing: 0.6px;
        text-transform: uppercase;
    }
    .soft-eval-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
    }
    .soft-eval-item {
        background-color: #ffffff;
        border: 1px solid #ebe8ff;
        border-radius: 12px;
        padding: 11px 14px;
        font-size: 0.8rem;
        color: #475569;
        line-height: 1.4;
        display: flex;
        align-items: flex-start;
        gap: 8px;
    }
    .soft-eval-check {
        color: #10b981;
        font-weight: 800;
        font-size: 0.9rem;
        flex-shrink: 0;
    }

    /* ---------------- TARJETAS CONTENEDORAS SOFT UI ---------------- */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff !important;
        border: 1px solid #eef0f6 !important;
        border-radius: 20px !important;
        padding: 20px 22px !important;
        box-shadow: 0 8px 24px rgba(108, 92, 231, 0.04) !important;
    }
    .soft-card {
        background-color: #ffffff;
        border: 1px solid #eef0f6;
        border-radius: 20px;
        padding: 20px 22px;
        margin-bottom: 18px;
        box-shadow: 0 8px 24px rgba(108, 92, 231, 0.04);
    }
    .soft-card-hdr {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 14px;
    }
    .soft-step-title {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 1rem;
        font-weight: 800;
        color: #1e293b;
    }
    .step-badge-lav {
        width: 26px;
        height: 26px;
        border-radius: 50%;
        background-color: #ede9fe;
        color: #6c5ce7;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.78rem;
        font-weight: 800;
    }
    .step-badge-mint {
        width: 26px;
        height: 26px;
        border-radius: 50%;
        background-color: #d1fae5;
        color: #059669;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.78rem;
        font-weight: 800;
    }

    /* Dropzone lavanda punteada estilo Soft UI */
    [data-testid="stFileUploader"] label {
        display: none !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background-color: #f8f7ff !important;
        border: 2px dashed #c4b5fd !important;
        border-radius: 16px !important;
        padding: 24px 16px !important;
    }
    [data-testid="stFileUploaderDropzone"] button {
        background-color: #ffffff !important;
        border: 1px solid #a78bfa !important;
        color: #5b4bc4 !important;
        font-weight: 700 !important;
        border-radius: 10px !important;
    }
    .dz-soft-box {
        text-align: center;
        margin-bottom: 8px;
    }
    .dz-cloud-circle {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        background-color: #ffffff;
        color: #5b4bc4;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 1.35rem;
        box-shadow: 0 4px 12px rgba(108, 92, 231, 0.12);
        margin-bottom: 8px;
    }
    .dz-title {
        font-size: 0.95rem;
        font-weight: 800;
        color: #1e293b;
    }
    .dz-desc {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: 2px;
    }
    .dz-schema-pill {
        display: inline-block;
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 999px;
        padding: 4px 14px;
        font-size: 0.73rem;
        font-weight: 700;
        color: #334155;
        margin-top: 8px;
        box-shadow: 0 2px 5px rgba(15, 23, 42, 0.03);
    }

    /* ---------------- VALIDACIÓN (TARJETA 2) ---------------- */
    .val-row-soft {
        background-color: #f8fafc;
        border-radius: 12px;
        padding: 9px 14px;
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.82rem;
        font-weight: 600;
        color: #334155;
    }
    .val-icon-ok {
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background-color: #bbf7d0;
        color: #059669;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.72rem;
        font-weight: 800;
        margin-right: 9px;
    }
    .val-icon-err {
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background-color: #fecaca;
        color: #dc2626;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.72rem;
        font-weight: 800;
        margin-right: 9px;
    }
    .pill-mint {
        background-color: #d1fae5;
        color: #065f46;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 999px;
    }
    .pill-lavender {
        background-color: #ede9fe;
        color: #5b4bc4;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 999px;
    }
    .pill-amber {
        background-color: #fef3c7;
        color: #b45309;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 999px;
    }
    .pill-red {
        background-color: #fee2e2;
        color: #b91c1c;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 999px;
    }
    .pill-slate {
        background-color: #f1f5f9;
        color: #475569;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 999px;
    }
    .val-banner-ok {
        background-color: #d1fae5;
        color: #065f46;
        border-radius: 12px;
        padding: 11px 16px;
        font-size: 0.83rem;
        font-weight: 700;
        margin-top: 10px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .val-banner-err {
        background-color: #fee2e2;
        border: 1px solid #fecaca;
        color: #991b1b;
        border-radius: 12px;
        padding: 12px 16px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-top: 10px;
    }

    /* ---------------- 6 TARJETAS KPI SOFT UI ---------------- */
    .soft-kpi-grid6 {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 14px;
        margin: 18px 0;
    }
    .soft-kpi-grid4 {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 14px;
        margin: 16px 0;
    }
    .soft-kpi-grid3 {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 14px;
        margin: 16px 0;
    }
    .soft-kpi-card {
        background-color: #ffffff;
        border: 1px solid #eef0f6;
        border-radius: 18px;
        padding: 16px 18px;
        box-shadow: 0 6px 18px rgba(108, 92, 231, 0.03);
    }
    .soft-kpi-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.68rem;
        font-weight: 800;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }
    .soft-kpi-val {
        font-size: 1.55rem;
        font-weight: 800;
        color: #0f172a;
        margin: 8px 0 4px 0;
        line-height: 1.1;
    }
    .soft-kpi-date {
        font-size: 1.15rem;
        font-weight: 800;
        color: #0f172a;
        margin: 8px 0 4px 0;
        line-height: 1.2;
    }
    .soft-kpi-sub {
        font-size: 0.73rem;
        color: #94a3b8;
        font-weight: 500;
    }

    /* ---------------- SEDES PÍLDORAS Y TABLAS SOFT UI ---------------- */
    .soft-sede-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background-color: #f3f1ff;
        border: 1px solid #e4dfff;
        color: #4c1d95;
        border-radius: 14px;
        padding: 8px 16px;
        margin-right: 10px;
        margin-top: 8px;
        font-size: 0.82rem;
        font-weight: 700;
    }
    .table-scroll {
        overflow-x: auto;
        margin-top: 8px;
        border-radius: 14px;
        border: 1px solid #f1f5f9;
    }
    .soft-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.81rem;
        text-align: left;
        white-space: nowrap;
    }
    .soft-table th {
        background-color: #f8fafc;
        color: #64748b;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 700;
        padding: 11px 14px;
        border-bottom: 1px solid #eef0f6;
        text-transform: uppercase;
    }
    .soft-table td {
        padding: 11px 14px;
        border-bottom: 1px solid #f8fafc;
        color: #334155;
    }
    .soft-table td.num, .soft-table th.num {
        text-align: right;
        font-family: 'JetBrains Mono', monospace;
    }
    .td-id {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        color: #5b4bc4;
    }

    /* ---------------- INTERPRETACIÓN ESTADÍSTICA SOFT UI ---------------- */
    .soft-interp-box {
        background-color: #f3f1ff;
        border-left: 4px solid #6c5ce7;
        border-radius: 12px;
        padding: 13px 16px;
        margin-top: 12px;
        font-size: 0.82rem;
        color: #334155;
        line-height: 1.45;
    }
    .soft-interp-hdr {
        font-size: 0.68rem;
        font-weight: 800;
        color: #5b4bc4;
        text-transform: uppercase;
        letter-spacing: 0.7px;
        margin-bottom: 4px;
    }

    /* Barras de frecuencia horizontales en M2 y M3 */
    .freq-row {
        margin-bottom: 11px;
    }
    .freq-top {
        display: flex;
        justify-content: space-between;
        font-size: 0.81rem;
        font-weight: 600;
        color: #334155;
        margin-bottom: 4px;
    }
    .freq-mono {
        font-family: 'JetBrains Mono', monospace;
        color: #475569;
        font-size: 0.77rem;
    }
    .freq-track {
        width: 100%;
        height: 7px;
        background-color: #f1f5f9;
        border-radius: 999px;
        overflow: hidden;
    }
    .freq-fill {
        height: 100%;
        border-radius: 999px;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. CONTENEDORES PRINCIPALES Y ESTADO DE CARGA EN MEMORIA
# ==============================================================================
topbar_placeholder = st.empty()

# Mantener el archivo en session_state para que al cambiar entre M1, M2 y M3 siga disponible
if "df_cargado" not in st.session_state:
    st.session_state.df_cargado = None
if "nombre_archivo" not in st.session_state:
    st.session_state.nombre_archivo = "Sin archivo cargado"
if "error_lectura" not in st.session_state:
    st.session_state.error_lectura = None

# ==============================================================================
# 7. BARRA LATERAL SOFT UI CON NAVEGACIÓN FUNCIONAL (M1, M2, M3)
# ==============================================================================
with st.sidebar:
    st.markdown("""
    <div class="sb-brand-wrap">
        <div class="sb-logo-circle">📈</div>
        <div>
            <div class="sb-brand-title">EstadiApp</div>
            <div class="sb-brand-sub">Analítica para decidir</div>
        </div>
    </div>
    <div class="sb-hito-hdr">● HITO 1 · E9</div>
    """, unsafe_allow_html=True)

    if st.button("📄  M1 Cargar datos", type="primary" if st.session_state.modulo_activo == "M1" else "secondary", use_container_width=True):
        st.session_state.modulo_activo = "M1"
        st.rerun()

    if st.button("📊  M2 Análisis descriptivo", type="primary" if st.session_state.modulo_activo == "M2" else "secondary", use_container_width=True):
        st.session_state.modulo_activo = "M2"
        st.rerun()

    if st.button("🎲  M3 Probabilidades", type="primary" if st.session_state.modulo_activo == "M3" else "secondary", use_container_width=True):
        st.session_state.modulo_activo = "M3"
        st.rerun()

    st.markdown("""
    <div class="sb-hito-hdr-muted">● HITO 2 · E15</div>
    <div class="sb-locked-item"><span>🧮</span><span>M4 Binomial y Poisson</span></div>
    <div class="sb-locked-item"><span>🔔</span><span>M5 Normal y Exponencial</span></div>
    <div class="sb-locked-item"><span>📏</span><span>M6 Intervalos de confianza</span></div>
    <div class="sb-locked-item"><span>⚖️</span><span>M7 Pruebas de hipótesis</span></div>
    <div class="sb-locked-item"><span>🔬</span><span>M8 Comparar grupos</span></div>

    <div class="sb-hito-hdr-amber">● ENTREGA FINAL · E16</div>
    <div class="sb-locked-item"><span>📋</span><span>M9 Informe y decisiones</span></div>
    """, unsafe_allow_html=True)

    sb_dataset_placeholder = st.empty()

# ==============================================================================
# 8. PANTALLA M1 · CARGAR DATOS Y VALIDACIÓN
# ==============================================================================
if st.session_state.modulo_activo == "M1":
    st.markdown("""
    <div class="soft-eyebrow-pill">● M1 · HITO 1 (E9)</div>
    <div class="soft-h1-row">
        <div>
            <h1 class="soft-h1">Cargar datos</h1>
            <div class="soft-sub">Sube el archivo del periodo. La app revisa el formato antes de calcular cualquier cosa.</div>
        </div>
        <div class="engine-badge"><span class="sb-ds-dot"></span>Motor de verificación: <b>Activo v1.4</b></div>
    </div>
    <div class="soft-eval-box">
        <div class="soft-eval-hdr">☑️ Se evalúa <span class="soft-eval-tag">CRITERIOS DE ENTREGA</span></div>
        <div class="soft-eval-grid">
            <div class="soft-eval-item"><span class="soft-eval-check">✔</span><span>Que la carga sea desde una pantalla (no una ruta fija en el código).</span></div>
            <div class="soft-eval-item"><span class="soft-eval-check">✔</span><span>Que la validación diga qué está mal y no deje continuar sin cerrarse.</span></div>
            <div class="soft-eval-item"><span class="soft-eval-check">✔</span><span>Que el resumen cambie con cada paquete: periodo, filas y sedes/países.</span></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1.05, 1], gap="medium")

    with col1:
        with st.container(border=True):
            c_hdr1, c_hdr2 = st.columns([1.2, 1])
            with c_hdr1:
                st.markdown('<div class="soft-step-title"><span class="step-badge-lav">1</span>1 · Seleccionar el archivo</div>', unsafe_allow_html=True)
            with c_hdr2:
                if st.button("👁 Ver cómo se ve un archivo rechazado", use_container_width=True):
                    st.session_state.mostrar_rechazo_demo = not st.session_state.mostrar_rechazo_demo

            st.markdown("""
            <div class="dz-soft-box" style="margin-top:8px;">
                <div class="dz-cloud-circle">☁️</div>
                <div class="dz-title">Arrastre aquí el archivo o haga clic para elegirlo</div>
                <div class="dz-desc">CSV (UTF-8, coma, punto decimal) o XLSX con hoja «datos»</div>
            </div>
            """, unsafe_allow_html=True)

            archivo_subido = st.file_uploader(
                "Seleccionar archivo CSV o XLSX",
                type=["csv", "xlsx", "xls"],
                label_visibility="collapsed",
                key="uploader_m1"
            )

            if archivo_subido is not None:
                df_leido, err_msg = cargar_archivo(archivo_subido)
                st.session_state.df_cargado = df_leido
                st.session_state.nombre_archivo = archivo_subido.name
                st.session_state.error_lectura = err_msg
                if st.session_state.ultimo_archivo_nombre != archivo_subido.name:
                    st.session_state.hora_carga = datetime.now().strftime("%H:%M:%S")
                    st.session_state.ultimo_archivo_nombre = archivo_subido.name
                st.session_state.mostrar_rechazo_demo = False

            placeholder_esquema_m1 = st.empty()

            if st.session_state.mostrar_rechazo_demo:
                st.markdown("""
                <div class="val-banner-err">
                    <b>✗ Demostración de archivo rechazado («archivo_con_errores.csv»):</b>
                    <ul style="margin:6px 0 4px 18px; padding:0;">
                        <li><b>Columna renombrada / faltante:</b> Falta la columna <code>costo_total_usd</code> (llegó como <code>costo</code>).</li>
                        <li><b>Celdas vacías detectadas:</b> 1 celda vacía en la columna <code>sede</code> (fila 6).</li>
                        <li><b>Filas duplicadas:</b> 1 fila duplicada (la fila 61 repite exactamente la fila 11).</li>
                    </ul>
                    <span style="font-size:0.76rem;">La aplicación detecta los fallos, informa la causa exacta, bloquea el cálculo y permanece abierta sin cerrarse.</span>
                </div>
                """, unsafe_allow_html=True)

# Procesar información del DataFrame activo en memoria
df_activo = st.session_state.df_cargado
if df_activo is not None:
    info = validar_y_resumir_m1(df_activo)
else:
    info = {
        "caso": "MotoExpres",
        "esquema_nombre": "MotoExpres S.A.S. · 21 columnas / NovaApp · 17 columnas",
        "n_filas": 0,
        "n_filas_fmt": "0",
        "n_cols": 0,
        "cols_esperadas": 21,
        "cols_coinciden": 0,
        "orden_exacto": False,
        "nombres_columnas": [],
        "celdas_vacias": 0,
        "vacias_por_col": {},
        "filas_duplicadas": 0,
        "ids_unicos": 0,
        "ids_unicos_fmt": "0",
        "ids_repetidos": 0,
        "errores_tipo": [],
        "total_fuera_rango": 0,
        "errores_rango": {},
        "errores_detalle": [],
        "desde": "----/--/--",
        "hasta": "----/--/--",
        "kpi5_titulo": "MECÁNICOS",
        "kpi5_val": "0",
        "kpi5_sub": "Personal activo",
        "kpi6_titulo": "CLIENTES DISTINTOS",
        "kpi6_val": "0",
        "kpi6_sub": "Base de clientes",
        "titulo_grupos": "Sedes encontradas en el archivo",
        "badge_grupos_txt": "centros operacionales",
        "unidad_grupo": "servicios",
        "grupos_dict": {},
        "grupos_alfabeticos": [],
        "versiones_lista": [],
        "es_valido": False
    }

# Actualizar Topbar y Sidebar Dataset Card (visibles en todas las pantallas con nombre y hora)
hora_str = f" · Cargado {st.session_state.hora_carga}" if st.session_state.hora_carga else ""
seg_me = "tb-seg-on" if info["caso"] == "MotoExpres" else "tb-seg-off"
seg_na = "tb-seg-on" if info["caso"] == "NovaApp" else "tb-seg-off"

topbar_placeholder.markdown(f"""
<div class="soft-topbar">
    <div class="tb-file-pill">
        <span class="sb-ds-dot" style="background-color:{'#10b981' if info['es_valido'] else '#f59e0b'};"></span>
        <span class="tb-file-name">{html.escape(st.session_state.nombre_archivo)}</span>
        <span>•</span>
        <span><b>{info['n_filas_fmt']}</b> filas</span>
        <span>•</span>
        <span>{info['desde']} / {info['hasta']}{html.escape(hora_str)}</span>
    </div>
    <div class="tb-right-group">
        <div class="tb-seg-box">
            <span class="{seg_me}">MotoExpres</span>
            <span class="{seg_na}">NovaApp</span>
        </div>
        <span class="tb-mint-btn">🎓 Modo clase</span>
        <span class="tb-avatar">👤</span>
    </div>
</div>
""", unsafe_allow_html=True)

sb_dataset_placeholder.markdown(f"""
<div class="sb-dataset-soft">
    <div class="sb-ds-top"><span>Dataset Actual</span><span class="sb-ds-dot" style="background-color:{'#10b981' if info['es_valido'] else '#f59e0b'};"></span></div>
    <div class="sb-ds-file">{html.escape(st.session_state.nombre_archivo)}</div>
    <div class="sb-ds-obs">{info['n_filas_fmt']} observaciones{html.escape(hora_str)}</div>
</div>
""", unsafe_allow_html=True)

# Continuar renderizado de M1 si estamos en M1
if st.session_state.modulo_activo == "M1":
    placeholder_esquema_m1.markdown(f"""
    <div style="text-align:center; margin-top:-4px; margin-bottom:10px;">
        <span class="dz-schema-pill"><span style="color:#10b981;">✔</span> Esquema: {info['esquema_nombre']}</span>
    </div>
    <div style="display:flex; justify-content:space-between; font-size:0.73rem; color:#94a3b8; border-top:1px solid #f1f5f9; padding-top:8px;">
        <span>🔒 Carga en memoria cliente (sin persistencia no autorizada)</span>
        <span>Máx. 50 MB</span>
    </div>
    """, unsafe_allow_html=True)

    with col2:
        with st.container(border=True):
            st.markdown('<div class="soft-card-hdr"><div class="soft-step-title"><span class="step-badge-mint">2</span>2 · Validación del formato</div></div>', unsafe_allow_html=True)

            if df_activo is not None:
                ok_cols = info["orden_exacto"]
                ok_vac = info["celdas_vacias"] == 0
                ok_dup = info["filas_duplicadas"] == 0
                ok_id = info["ids_repetidos"] == 0
                ok_tipo = len(info["errores_tipo"]) == 0
                ok_rng = info["total_fuera_rango"] == 0

                html_val = f"""
                <div class="val-row-soft">
                    <span><span class="{'val-icon-ok' if ok_cols else 'val-icon-err'}">{'✓' if ok_cols else '✗'}</span>Columnas con el nombre y el orden exactos</span>
                    <span class="{'pill-mint' if ok_cols else 'pill-red'}">{info['cols_coinciden']} de {info['cols_esperadas']}</span>
                </div>
                <div class="val-row-soft">
                    <span><span class="{'val-icon-ok' if ok_vac else 'val-icon-err'}">{'✓' if ok_vac else '✗'}</span>Sin celdas vacías</span>
                    <span class="{'pill-mint' if ok_vac else 'pill-red'}">{info['celdas_vacias']} vacías</span>
                </div>
                <div class="val-row-soft">
                    <span><span class="{'val-icon-ok' if ok_dup else 'val-icon-err'}">{'✓' if ok_dup else '✗'}</span>Sin filas duplicadas</span>
                    <span class="{'pill-mint' if ok_dup else 'pill-red'}">{info['filas_duplicadas']} duplicadas</span>
                </div>
                <div class="val-row-soft">
                    <span><span class="{'val-icon-ok' if ok_id else 'val-icon-err'}">{'✓' if ok_id else '✗'}</span>Identificador único</span>
                    <span class="{'pill-mint' if ok_id else 'pill-red'}">{info['ids_unicos_fmt']} únicos</span>
                </div>
                <div class="val-row-soft">
                    <span><span class="{'val-icon-ok' if ok_tipo else 'val-icon-err'}">{'✓' if ok_tipo else '✗'}</span>Tipos correctos (números, fechas, Sí/No)</span>
                    <span class="{'pill-mint' if ok_tipo else 'pill-red'}">{'todas las columnas' if ok_tipo else f"{len(info['errores_tipo'])} con error"}</span>
                </div>
                <div class="val-row-soft">
                    <span><span class="{'val-icon-ok' if ok_rng else 'val-icon-err'}">{'✓' if ok_rng else '✗'}</span>Valores dentro del rango</span>
                    <span class="{'pill-mint' if ok_rng else 'pill-red'}">{info['total_fuera_rango']} fuera de rango</span>
                </div>
                """
                st.markdown(html_val, unsafe_allow_html=True)

                if info["es_valido"]:
                    st.markdown('<div class="val-banner-ok">✔ Archivo válido. Puede continuar al análisis.</div>', unsafe_allow_html=True)
                else:
                    items_err = "".join([f"<li>{html.escape(e)}</li>" for e in info["errores_detalle"]])
                    st.markdown(
                        f'<div class="val-banner-err"><b>✗ Archivo rechazado ({html.escape(st.session_state.nombre_archivo)}):</b>'
                        f'<ul style="margin:6px 0 4px 18px; padding:0;">{items_err}</ul>'
                        f'<span>Corrija el archivo y vuelva a cargarlo. La aplicación no permite continuar con datos inválidos.</span></div>',
                        unsafe_allow_html=True
                    )
            else:
                if st.session_state.error_lectura:
                    st.markdown(f'<div class="val-banner-err"><b>✗ Error de lectura:</b> {html.escape(st.session_state.error_lectura)}</div>', unsafe_allow_html=True)
                st.markdown("""
                <div class="val-row-soft"><span>Columnas con el nombre y el orden exactos</span><span class="pill-amber">Pendiente</span></div>
                <div class="val-row-soft"><span>Sin celdas vacías</span><span class="pill-amber">Pendiente</span></div>
                <div class="val-row-soft"><span>Sin filas duplicadas</span><span class="pill-amber">Pendiente</span></div>
                <div class="val-row-soft"><span>Identificador único</span><span class="pill-amber">Pendiente</span></div>
                <div class="val-row-soft"><span>Tipos correctos (números, fechas, Sí/No)</span><span class="pill-amber">Pendiente</span></div>
                <div class="val-row-soft"><span>Valores dentro del rango</span><span class="pill-amber">Pendiente</span></div>
                <div class="val-banner-ok" style="background:#f3f1ff; color:#5b4bc4;">Sube un paquete CSV o XLSX a la izquierda para validar su estructura.</div>
                """, unsafe_allow_html=True)

    # Fila de 6 tarjetas KPI (idénticas al mockup Sin título-1-3.pdf pág. 1)
    st.markdown(f"""
    <div class="soft-kpi-grid6">
        <div class="soft-kpi-card">
            <div class="soft-kpi-top"><span>FILAS</span><span style="color:#6c5ce7;">▤</span></div>
            <div class="soft-kpi-val">{info['n_filas_fmt']}</div>
            <div class="soft-kpi-sub">Registros cargados</div>
        </div>
        <div class="soft-kpi-card">
            <div class="soft-kpi-top"><span>COLUMNAS</span><span style="color:#6c5ce7;">⊞</span></div>
            <div class="soft-kpi-val">{info['n_cols']}</div>
            <div class="soft-kpi-sub">Campos requeridos</div>
        </div>
        <div class="soft-kpi-card">
            <div class="soft-kpi-top"><span>DESDE</span><span style="color:#10b981;">📅</span></div>
            <div class="soft-kpi-date">{info['desde']}</div>
            <div class="soft-kpi-sub">Inicio de ventana</div>
        </div>
        <div class="soft-kpi-card">
            <div class="soft-kpi-top"><span>HASTA</span><span style="color:#10b981;">📅</span></div>
            <div class="soft-kpi-date">{info['hasta']}</div>
            <div class="soft-kpi-sub">Cierre del periodo</div>
        </div>
        <div class="soft-kpi-card">
            <div class="soft-kpi-top"><span>{info['kpi5_titulo']}</span><span style="color:#f59e0b;">🔧</span></div>
            <div class="soft-kpi-val">{html.escape(str(info['kpi5_val']))}</div>
            <div class="soft-kpi-sub">{info['kpi5_sub']}</div>
        </div>
        <div class="soft-kpi-card">
            <div class="soft-kpi-top"><span>{info['kpi6_titulo']}</span><span style="color:#6c5ce7;">👥</span></div>
            <div class="soft-kpi-val">{info['kpi6_val']}</div>
            <div class="soft-kpi-sub">{info['kpi6_sub']}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if df_activo is not None and info["es_valido"]:
        # Sedes / Países encontrados dinámicamente en el archivo
        pills_grupos = "".join([
            f'<span class="soft-sede-pill">🏪 {html.escape(str(k))} <span style="font-weight:500; color:#64748b;">• {fmt_int(v)} {info["unidad_grupo"]}</span></span>'
            for k, v in info["grupos_dict"].items()
        ])
        extra_ver_html = ""
        if info["caso"] == "NovaApp" and info["versiones_lista"]:
            ver_pills = "".join([f'<span class="pill-mint" style="margin-right:6px;">v{html.escape(v)}</span>' for v in info["versiones_lista"]])
            extra_ver_html = f'<div style="margin-top:10px; font-size:0.8rem; color:#475569;"><b>Versiones detectadas en el paquete:</b> {ver_pills}</div>'

        st.markdown(f"""
        <div class="soft-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                    <div style="font-size:1rem; font-weight:800; color:#0f172a;">{info['titulo_grupos']}</div>
                    <div style="font-size:0.78rem; color:#64748b;">Se leen de los datos ({', '.join(info['grupos_alfabeticos'])}). Con otro paquete aparecen otras.</div>
                </div>
                <span class="pill-lavender">❈ {len(info['grupos_dict'])} {info['badge_grupos_txt']}</span>
            </div>
            <div style="margin-top:6px;">{pills_grupos}</div>
            {extra_ver_html}
        </div>
        """, unsafe_allow_html=True)

        # Vista previa de las primeras 10 filas (Guía Hito 1 Parte 1)
        tabla_prev = generar_tabla_preview_html(df_activo, max_filas=10)
        st.markdown(f"""
        <div class="soft-card">
            <div class="soft-card-hdr">
                <div class="soft-step-title"><span class="step-badge-lav">3</span>3 · Vista previa (primeras 10 filas)</div>
                <span style="font-size:0.76rem; color:#64748b; font-family:'JetBrains Mono', monospace;">Total columnas: <b>{info['n_cols']}</b> • Mostrando {min(10, info['n_filas'])} de {info['n_filas_fmt']}</span>
            </div>
            {tabla_prev}
            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:14px; padding-top:10px; border-top:1px solid #f1f5f9; font-size:0.79rem; color:#059669; font-weight:600;">
                <span>✔ Estructura tabular verificada para procesamiento en M2 (Descriptivo) y M3 (Probabilidades).</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        c_b1, c_b2, c_b3 = st.columns([3, 1, 1.2])
        with c_b2:
            csv_muestra = df_activo.head(10).to_csv(index=False).encode("utf-8")
            st.download_button("⬇ Descargar muestra", data=csv_muestra, file_name=f"muestra_{st.session_state.nombre_archivo}", mime="text/csv", use_container_width=True)
        with c_b3:
            if st.button("Ir a M2 Análisis descriptivo  →", type="primary", use_container_width=True):
                st.session_state.modulo_activo = "M2"
                st.rerun()


# ==============================================================================
# 9. PANTALLA M2 · ANÁLISIS DESCRIPTIVO (E2–E4)
# ==============================================================================
elif st.session_state.modulo_activo == "M2":
    st.markdown('<div class="soft-eyebrow-pill">● M2 · HITO 1 (E9)</div>', unsafe_allow_html=True)

    if df_activo is None or not info["es_valido"]:
        st.markdown('<h1 class="soft-h1">Análisis descriptivo</h1><div class="soft-sub">Cómo son los datos: centro, dispersión, forma y grupos.</div>', unsafe_allow_html=True)
        st.warning("Primero debes cargar un archivo válido en el módulo **M1 Cargar datos** para ejecutar el análisis descriptivo.")
        if st.button("← Ir a M1 Cargar datos", type="primary"):
            st.session_state.modulo_activo = "M1"
            st.rerun()
    else:
        caso = info["caso"]
        if caso == "MotoExpres":
            vars_num_disp = [c for c in ["costo_total_usd", "tiempo_reparacion_h", "tiempo_diagnostico_min", "repuestos_usados", "costo_repuestos_usd", "costo_mano_obra_usd", "satisfaccion"] if c in df_activo.columns]
            col_filtro = "sede" if "sede" in df_activo.columns else None
            lbl_todas = "Todas las Sedes"
        else:
            vars_num_disp = [c for c in ["duracion_min", "tiempo_carga_s", "paginas_vistas", "crashes", "calificacion"] if c in df_activo.columns]
            col_filtro = "plataforma" if "plataforma" in df_activo.columns else None
            lbl_todas = "Todas las Plataformas"

        # Encabezado y selector de variable numérica (como en pág. 2 de Sin título-1-3.pdf)
        c_title, c_sel = st.columns([2.2, 1])
        with c_title:
            st.markdown('<h1 class="soft-h1">Análisis descriptivo</h1><div class="soft-sub">Cómo son los datos: centro, dispersión, forma y grupos.</div>', unsafe_allow_html=True)
        with c_sel:
            var_elegida = st.selectbox("⇄ Variable numérica:", options=vars_num_disp, index=0)

        # Barra de control y filtro por sede o plataforma en vivo
        with st.container(border=True):
            cf1, cf2 = st.columns([1.1, 2.2])
            with cf1:
                unidades_map = {
                    "costo_total_usd": "USD", "costo_repuestos_usd": "USD", "costo_mano_obra_usd": "USD",
                    "tiempo_reparacion_h": "h", "tiempo_diagnostico_min": "min", "duracion_min": "min",
                    "tiempo_carga_s": "s", "repuestos_usados": "unid.", "paginas_vistas": "págs", "crashes": "eventos"
                }
                u_var = unidades_map.get(var_elegida, "")
                st.markdown(f"""
                <div style="display:flex; align-items:center; gap:12px;">
                    <div class="sb-logo-circle" style="background:#5b4bc4; color:#fff;">📊</div>
                    <div>
                        <div style="font-size:0.66rem; font-weight:800; color:#64748b; text-transform:uppercase;">VARIABLE ANALIZADA</div>
                        <div style="font-size:1.05rem; font-weight:800; color:#0f172a;">{html.escape(var_elegida)} {f'({u_var})' if u_var else ''} <span class="pill-lavender">Numérica</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with cf2:
                if col_filtro:
                    opciones_f = [lbl_todas] + sorted([str(x) for x in df_activo[col_filtro].dropna().unique()])
                    filtro_sel = st.radio(
                        f"Filtrar por {col_filtro}:",
                        options=opciones_f,
                        horizontal=True
                    )
                else:
                    filtro_sel = lbl_todas

        # Aplicar filtro dinámico si se eligió una sede o plataforma específica
        if col_filtro and filtro_sel != lbl_todas:
            df_m2 = df_activo[df_activo[col_filtro].astype(str) == filtro_sel].copy()
        else:
            df_m2 = df_activo.copy()

        res_m2 = analizar_descriptivo_m2(df_m2, caso, var_elegida)
        m = res_m2["medidas_sel"]

        # 6 Tarjetas KPI de la variable seleccionada (Idénticas a Sin título-1-3.pdf pág. 2)
        disp_txt = "Alta dispersión" if m["cv"] >= 50 else ("Dispersión moderada" if m["cv"] >= 25 else "Baja dispersión")
        disp_cls = "pill-red" if m["cv"] >= 50 else ("pill-amber" if m["cv"] >= 25 else "pill-mint")
        sesgo_txt = "Asimetría der." if m["sesgo"] > 0.5 else ("Asimetría izq." if m["sesgo"] < -0.5 else "Simétrica")

        st.markdown(f"""
        <div class="soft-kpi-grid6">
            <div class="soft-kpi-card">
                <div class="soft-kpi-top"><span>MEDIA</span><span style="color:#6c5ce7;">📊</span></div>
                <div class="soft-kpi-val">{fmt_num(m['media'], 2)} <span style="font-size:0.8rem; font-weight:600; color:#64748b;">{u_var}</span></div>
                <div><span class="pill-lavender">Muestral</span></div>
            </div>
            <div class="soft-kpi-card">
                <div class="soft-kpi-top"><span>MEDIANA</span><span style="color:#10b981;">↕</span></div>
                <div class="soft-kpi-val">{fmt_num(m['mediana'], 2)} <span style="font-size:0.8rem; font-weight:600; color:#64748b;">{u_var}</span></div>
                <div><span class="pill-mint">P50 (Típico)</span></div>
            </div>
            <div class="soft-kpi-card">
                <div class="soft-kpi-top"><span>DESV. ESTÁNDAR</span><span style="color:#6c5ce7;">⚖️</span></div>
                <div class="soft-kpi-val">{fmt_num(m['desv'], 2)} <span style="font-size:0.8rem; font-weight:600; color:#64748b;">{u_var}</span></div>
                <div><span class="pill-slate">s (n-1)</span></div>
            </div>
            <div class="soft-kpi-card">
                <div class="soft-kpi-top"><span>CV</span><span style="color:#ef4444;">%</span></div>
                <div class="soft-kpi-val">{fmt_num(m['cv'], 2)}<span style="font-size:0.95rem;"> %</span></div>
                <div><span class="{disp_cls}">{disp_txt}</span></div>
            </div>
            <div class="soft-kpi-card">
                <div class="soft-kpi-top"><span>SESGO</span><span style="color:#6c5ce7;">📈</span></div>
                <div class="soft-kpi-val">{fmt_num(m['sesgo'], 2)}</div>
                <div><span class="pill-lavender">{sesgo_txt}</span></div>
            </div>
            <div class="soft-kpi-card">
                <div class="soft-kpi-top"><span>ATÍPICOS</span><span style="color:#f59e0b;">⚠️</span></div>
                <div class="soft-kpi-val">{fmt_int(m['atipicos'])}</div>
                <div><span class="pill-amber">1,5·IQR</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Fila central: Gráfico 1 (Histograma) | Tabla de todas las medidas + Interpretación
        ch1, ch2 = st.columns([1.25, 1], gap="medium")

        with ch1:
            svg_hist, moda_int = generar_histograma_svg(df_m2[var_elegida], var_elegida, u_var)
            st.markdown(f"""
            <div class="soft-card">
                <div class="soft-card-hdr">
                    <div>
                        <div style="font-size:1.05rem; font-weight:800; color:#0f172a;">Histograma de {html.escape(var_elegida)}</div>
                        <div style="font-size:0.77rem; color:#64748b;">Frecuencia por intervalo ({html.escape(u_var) if u_var else 'unidades'}) · Filtro: {html.escape(filtro_sel)}</div>
                    </div>
                    <span class="pill-lavender">● 8 intervalos · Sturges mod.</span>
                </div>
                {svg_hist}
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px; padding-top:8px; border-top:1px solid #f1f5f9; font-size:0.76rem; color:#64748b;">
                    <span><b style="color:#5b4bc4;">●</b> Intervalo modal: <b>{html.escape(moda_int)}</b></span>
                    <span class="pill-slate">Σ = {fmt_int(m['n'])} casos observados</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with ch2:
            if m["sesgo"] > 0.5:
                frase_interp = (
                    f"La variable <b>{html.escape(var_elegida)}</b> es sesgada a la derecha (sesgo {fmt_num(m['sesgo'], 4)} y CV {fmt_num(m['cv'], 2)} %): "
                    f"la mediana (<b>{fmt_num(m['mediana'], 2)} {u_var}</b>) representa mejor el caso típico que la media ({fmt_num(m['media'], 2)} {u_var}), "
                    f"la cual se ve arrastrada por {fmt_int(m['atipicos'])} valores altos atípicos."
                )
            elif m["sesgo"] < -0.5:
                frase_interp = (
                    f"La variable <b>{html.escape(var_elegida)}</b> presenta asimetría hacia la izquierda (sesgo {fmt_num(m['sesgo'], 4)}): "
                    f"la mediana ({fmt_num(m['mediana'], 2)} {u_var}) supera a la media ({fmt_num(m['media'], 2)} {u_var})."
                )
            else:
                frase_interp = (
                    f"La variable <b>{html.escape(var_elegida)}</b> es prácticamente simétrica (sesgo {fmt_num(m['sesgo'], 4)} y CV {fmt_num(m['cv'], 2)} %): "
                    f"la media ({fmt_num(m['media'], 2)} {u_var}) y la mediana ({fmt_num(m['mediana'], 2)} {u_var}) coinciden de cerca, siendo candidata al modelo Normal."
                )

            st.markdown(f"""
            <div class="soft-card">
                <div class="soft-card-hdr">
                    <div style="font-size:1.05rem; font-weight:800; color:#0f172a;">Todas las medidas ({html.escape(var_elegida)})</div>
                    <span class="pill-lavender">Resumen tabular (4 dec.)</span>
                </div>
                <table class="soft-table">
                    <tbody>
                        <tr><td>n (muestra válida)</td><td class="num"><b>{fmt_int(m['n'])}</b></td></tr>
                        <tr><td>Media</td><td class="num"><b>{fmt_num(m['media'], 4)}</b></td></tr>
                        <tr style="background-color:#f3f1ff;"><td><b style="color:#5b4bc4;">● Mediana (P50)</b></td><td class="num"><b style="color:#5b4bc4;">{fmt_num(m['mediana'], 4)}</b></td></tr>
                        <tr><td>Desviación estándar (s)</td><td class="num"><b>{fmt_num(m['desv'], 4)}</b></td></tr>
                        <tr><td>Coeficiente de variación (CV)</td><td class="num"><b style="color:#dc2626;">{fmt_num(m['cv'], 4)} %</b></td></tr>
                        <tr><td>Q1 · Q3 (cuartiles lineales)</td><td class="num">{fmt_num(m['q1'], 2)} · {fmt_num(m['q3'], 2)}</td></tr>
                        <tr><td>IQR (Rango intercuartílico)</td><td class="num"><b>{fmt_num(m['iqr'], 4)}</b></td></tr>
                        <tr><td>Mínimo · Máximo</td><td class="num">{fmt_num(m['min'], 2)} · {fmt_num(m['max'], 2)}</td></tr>
                        <tr><td>Sesgo (asimetría ajustada)</td><td class="num"><b style="color:#5b4bc4;">{fmt_num(m['sesgo'], 4)}</b></td></tr>
                        <tr><td>Atípicos (regla 1,5·IQR)</td><td class="num"><b style="color:#d97706;">{fmt_int(m['atipicos'])}</b></td></tr>
                    </tbody>
                </table>
                <div class="soft-interp-box">
                    <div class="soft-interp-hdr">💡 INTERPRETACIÓN ESTADÍSTICA</div>
                    <div><b>Lectura:</b> {frase_interp}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Fila de gráficos 2 y 3: Frecuencias (Barras) | Boxplot por grupo
        cg1, cg2 = st.columns([1, 1.15], gap="medium")

        with cg1:
            f_list = res_m2["frecuencias"]
            max_cnt = max([x["conteo"] for x in f_list]) if f_list else 1
            colores_bar = ["#059669", "#0d9488", "#10b981", "#34d399", "#6c5ce7", "#8b5cf6", "#a78bfa", "#c4b5fd"]
            barras_freq_html = []
            for idx_f, item_f in enumerate(f_list):
                w_pct = (item_f["conteo"] / max_cnt) * 100.0 if max_cnt > 0 else 0
                c_bar = colores_bar[idx_f % len(colores_bar)]
                barras_freq_html.append(f"""
                <div class="freq-row">
                    <div class="freq-top">
                        <span>{html.escape(item_f['categoria'])}</span>
                        <span class="freq-mono"><b>{fmt_int(item_f['conteo'])}</b> • {fmt_num(item_f['porcentaje'], 1)} %</span>
                    </div>
                    <div class="freq-track"><div class="freq-fill" style="width:{w_pct:.1f}%; background-color:{c_bar};"></div></div>
                </div>
                """)
            mas_frec = f_list[0] if f_list else {"categoria": "N/A", "conteo": 0, "porcentaje": 0.0}

            st.markdown(f"""
            <div class="soft-card">
                <div class="soft-card-hdr">
                    <div>
                        <div style="font-size:1.05rem; font-weight:800; color:#0f172a;">Frecuencias de {html.escape(res_m2['col_freq'])}</div>
                        <div style="font-size:0.77rem; color:#64748b;">Distribución operativa sobre {fmt_int(len(df_m2))} registros</div>
                    </div>
                    <span class="pill-mint">{len(f_list)} categorías</span>
                </div>
                <div style="margin-top:10px;">{"".join(barras_freq_html)}</div>
                <div class="soft-interp-box" style="margin-top:14px;">
                    <b>Categoría más frecuente:</b> <b>{html.escape(mas_frec['categoria'])}</b> concentra el mayor volumen con <b>{fmt_int(mas_frec['conteo'])}</b> registros ({fmt_num(mas_frec['porcentaje'], 1)} % del total).
                </div>
            </div>
            """, unsafe_allow_html=True)

        with cg2:
            svg_box = generar_boxplot_svg(res_m2["box_datos"], res_m2["col_box_num"], res_m2["col_box_cat"])
            top_box_cat = res_m2["box_datos"][-1]["categoria"] if res_m2["box_datos"] else "N/A"
            low_box_cat = res_m2["box_datos"][0]["categoria"] if res_m2["box_datos"] else "N/A"

            st.markdown(f"""
            <div class="soft-card">
                <div class="soft-card-hdr">
                    <div>
                        <div style="font-size:1.05rem; font-weight:800; color:#0f172a;">{html.escape(res_m2['titulo_box'])}</div>
                        <div style="font-size:0.77rem; color:#64748b;">Caja = Q1 a Q3 • línea ámbar = mediana • bigotes = rango 1,5·IQR</div>
                    </div>
                    <span class="pill-amber">IQR + Mediana</span>
                </div>
                {svg_box}
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px; padding-top:8px; border-top:1px solid #f1f5f9; font-size:0.77rem; color:#475569;">
                    <span>Mayor mediana: <b>{html.escape(top_box_cat)}</b> · Menor mediana: <b>{html.escape(low_box_cat)}</b></span>
                    <span class="pill-mint">{fmt_int(m['atipicos'])} outliers en variable activa</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # 3 Tarjetas inferiores: Análisis por grupo + Variable Ordinal (Idénticas a pág. 2 de Sin título-1-3.pdf)
        g1_t, g1_v, g1_s = res_m2["grupo1_info"]
        g2_t, g2_v, g2_s = res_m2["grupo2_info"]
        estrellas = "★" * int(round(res_m2["ord_media"])) + "☆" * max(0, 5 - int(round(res_m2["ord_media"])))

        st.markdown(f"""
        <div class="soft-kpi-grid3">
            <div class="soft-kpi-card" style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div class="soft-kpi-top">{html.escape(g1_t)}</div>
                    <div style="font-size:1.3rem; font-weight:800; color:#0f172a; margin:5px 0 2px 0;">{html.escape(g1_v)}</div>
                    <div style="font-size:0.8rem; font-weight:700; color:#5b4bc4; font-family:'JetBrains Mono', monospace;">{html.escape(g1_s)}</div>
                </div>
                <div class="sb-logo-circle">🏪</div>
            </div>
            <div class="soft-kpi-card" style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div class="soft-kpi-top">{html.escape(g2_t)}</div>
                    <div style="font-size:1.3rem; font-weight:800; color:#0f172a; margin:5px 0 2px 0;">{html.escape(g2_v)}</div>
                    <div><span class="pill-mint">{html.escape(g2_s)}</span></div>
                </div>
                <div class="sb-logo-circle" style="background:#d1fae5; color:#059669;">🛡️</div>
            </div>
            <div class="soft-kpi-card" style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div class="soft-kpi-top">{html.escape(res_m2['col_ordinal'].upper())} (VARIABLE ORDINAL)</div>
                    <div style="font-size:1.3rem; font-weight:800; color:#0f172a; margin:5px 0 2px 0;">moda {html.escape(res_m2['ord_moda'])} • <span style="color:#5b4bc4;">media {fmt_num(res_m2['ord_media'], 2)}</span></div>
                    <div style="font-size:0.82rem; color:#f59e0b; font-weight:700;">{estrellas} <span style="color:#64748b; font-weight:500;">Escala 1 a 5</span></div>
                </div>
                <div class="sb-logo-circle" style="background:#fef3c7; color:#d97706;">😊</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Tabla resumen de todas las variables numéricas (Principal + Medidas de apoyo obligatorias de la Guía)
        filas_apoyo_html = "".join([
            f"<tr>"
            f"<td class='td-id'>{html.escape(ap['variable'])} ({html.escape(ap['unidad'])})</td>"
            f"<td class='num'>{fmt_int(ap['n'])}</td>"
            f"<td class='num'><b>{fmt_num(ap['media'], 4)}</b></td>"
            f"<td class='num'><b>{fmt_num(ap['mediana'], 4)}</b></td>"
            f"<td class='num'>{fmt_num(ap['desv'], 4)}</td>"
            f"<td class='num'>{fmt_num(ap['cv'], 2)} %</td>"
            f"<td class='num'>{fmt_num(ap['iqr'], 2)}</td>"
            f"<td class='num'>{fmt_num(ap['sesgo'], 4)}</td>"
            f"<td class='num'>{fmt_int(ap['atipicos'])}</td>"
            f"</tr>"
            for ap in res_m2["apoyo"]
        ])

        st.markdown(f"""
        <div class="soft-card">
            <div class="soft-card-hdr">
                <div style="font-size:1rem; font-weight:800; color:#0f172a;">📋 Comparativa de variable principal y medidas de apoyo (Sección 6 · M2)</div>
                <span class="pill-slate">Convenciones Sección 7</span>
            </div>
            <div class="table-scroll">
                <table class="soft-table">
                    <thead>
                        <tr>
                            <th>Variable numérica</th>
                            <th class="num">n</th>
                            <th class="num">Media</th>
                            <th class="num">Mediana</th>
                            <th class="num">Desv. Estándar (s)</th>
                            <th class="num">CV %</th>
                            <th class="num">IQR</th>
                            <th class="num">Sesgo</th>
                            <th class="num">Atípicos</th>
                        </tr>
                    </thead>
                    <tbody>{filas_apoyo_html}</tbody>
                </table>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ==============================================================================
# 10. PANTALLA M3 · PROBABILIDAD, CONDICIONAL Y BAYES (E6–E7)
# ==============================================================================
elif st.session_state.modulo_activo == "M3":
    st.markdown('<div class="soft-eyebrow-pill">● M3 · HITO 1 (E9)</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="soft-h1">Probabilidad, condicional y Bayes</h1><div class="soft-sub">Qué tan probable es cada evento y cómo cambia cuando conocemos evidencia adicional.</div>', unsafe_allow_html=True)

    if df_activo is None or not info["es_valido"]:
        st.warning("Primero debes cargar un archivo válido en el módulo **M1 Cargar datos** para calcular probabilidades y Bayes.")
        if st.button("← Ir a M1 Cargar datos", type="primary"):
            st.session_state.modulo_activo = "M1"
            st.rerun()
    else:
        st.markdown("""
        <div class="soft-eval-box">
            <div class="soft-eval-hdr">☑️ Se evalúa <span class="soft-eval-tag">MÓDULO M3 · ENCUENTROS 6 Y 7</span></div>
            <div class="soft-eval-grid">
                <div class="soft-eval-item"><span class="soft-eval-check">✔</span><span>Probabilidades básicas como frecuencias relativas y regla de la suma verificada.</span></div>
                <div class="soft-eval-item"><span class="soft-eval-check">✔</span><span>Tabla de contingencia y condicionales para TODOS los grupos del archivo, más Bayes.</span></div>
                <div class="soft-eval-item"><span class="soft-eval-check">✔</span><span>Veredicto de independencia con la regla <b>|P(A|B) − P(A)| &lt; 0,02</b> y explicación.</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        p3 = analizar_probabilidad_m3(df_activo, info["caso"])

        # 4 Tarjetas KPI de Probabilidades Básicas + Regla de la Suma
        st.markdown(f"""
        <div class="soft-kpi-grid4">
            <div class="soft-kpi-card">
                <div class="soft-kpi-top"><span>P(A) · {html.escape(p3['nombre_a'])}</span><span style="color:#6c5ce7;">🎲</span></div>
                <div class="soft-kpi-val">{fmt_num(p3['p_a'], 4)}</div>
                <div class="soft-kpi-sub">{fmt_num(p3['p_a']*100, 2)} % del archivo</div>
            </div>
            <div class="soft-kpi-card">
                <div class="soft-kpi-top"><span>P(B) · {html.escape(p3['nombre_b'])}</span><span style="color:#10b981;">🎯</span></div>
                <div class="soft-kpi-val">{fmt_num(p3['p_b'], 4)}</div>
                <div class="soft-kpi-sub">{fmt_num(p3['p_b']*100, 2)} % del archivo</div>
            </div>
            <div class="soft-kpi-card">
                <div class="soft-kpi-top"><span>INTERSECCIÓN · P(A ∩ B)</span><span style="color:#f59e0b;">∩</span></div>
                <div class="soft-kpi-val">{fmt_num(p3['p_ab'], 4)}</div>
                <div class="soft-kpi-sub">Ambos eventos simultáneos</div>
            </div>
            <div class="soft-kpi-card" style="border: 1.5px solid #c4b5fd; background-color:#fcfbff;">
                <div class="soft-kpi-top"><span style="color:#5b4bc4;">UNIÓN · P(A ∪ B)</span><span style="color:#5b4bc4;">∪</span></div>
                <div class="soft-kpi-val" style="color:#5b4bc4;">{fmt_num(p3['p_union_formula'], 4)}</div>
                <div class="soft-kpi-sub">= {fmt_num(p3['p_a'], 4)} + {fmt_num(p3['p_b'], 4)} − {fmt_num(p3['p_ab'], 4)} (✔ Regla suma)</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Fila central: Tabla de Contingencia | Barras de Probabilidades Condicionales
        cc1, cc2 = st.columns([1.15, 1], gap="medium")

        with cc1:
            filas_cont_html = []
            for r in p3["filas_contingencia"]:
                es_max = (p3["grupo_mayor"] and r["grupo"] == p3["grupo_mayor"]["grupo"])
                es_min = (p3["grupo_menor"] and r["grupo"] == p3["grupo_menor"]["grupo"])
                badge_ext = '<span class="pill-red" style="margin-left:6px;">Mayor</span>' if es_max else ('<span class="pill-mint" style="margin-left:6px;">Menor</span>' if es_min else '')
                filas_cont_html.append(
                    f"<tr>"
                    f"<td><b>{html.escape(r['grupo'])}</b>{badge_ext}</td>"
                    f"<td class='num'>{fmt_int(r['si'])}</td>"
                    f"<td class='num'>{fmt_int(r['no'])}</td>"
                    f"<td class='num'>{fmt_int(r['total'])} ({fmt_num(r['pct_total'], 1)} %)</td>"
                    f"<td class='num'><b style='color:#5b4bc4;'>{fmt_num(r['p_cond'], 4)}</b></td>"
                    f"</tr>"
                )

            st.markdown(f"""
            <div class="soft-card">
                <div class="soft-card-hdr">
                    <div>
                        <div style="font-size:1.05rem; font-weight:800; color:#0f172a;">Tabla de contingencia: {html.escape(p3['titulo_cont'])}</div>
                        <div style="font-size:0.77rem; color:#64748b;">Conteos, porcentaje de participación y condicional para todos los grupos</div>
                    </div>
                    <span class="pill-lavender">{len(p3['filas_contingencia'])} grupos</span>
                </div>
                <div class="table-scroll">
                    <table class="soft-table">
                        <thead>
                            <tr>
                                <th>{html.escape(p3['col_grupo_cont'])}</th>
                                <th class="num">Sí ({html.escape(p3['nombre_evento'])})</th>
                                <th class="num">No</th>
                                <th class="num">Total (% archivo)</th>
                                <th class="num">P({html.escape(p3['nombre_evento'])} | grupo)</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(filas_cont_html)}</tbody>
                    </table>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with cc2:
            max_pcond = max([r["p_cond"] for r in p3["filas_contingencia"]]) if p3["filas_contingencia"] else 1.0
            barras_cond_html = []
            for r in p3["filas_contingencia"]:
                w_bar = (r["p_cond"] / max_pcond) * 100.0 if max_pcond > 0 else 0
                es_max = (p3["grupo_mayor"] and r["grupo"] == p3["grupo_mayor"]["grupo"])
                color_b = "#ef4444" if es_max else "#6c5ce7"
                barras_cond_html.append(f"""
                <div class="freq-row">
                    <div class="freq-top">
                        <span>{html.escape(r['grupo'])}</span>
                        <span class="freq-mono"><b>{fmt_num(r['p_cond'], 4)}</b> ({fmt_num(r['p_cond']*100, 2)} %)</span>
                    </div>
                    <div class="freq-track"><div class="freq-fill" style="width:{w_bar:.1f}%; background-color:{color_b};"></div></div>
                </div>
                """)

            g_may = p3["grupo_mayor"]
            g_men = p3["grupo_menor"]
            st.markdown(f"""
            <div class="soft-card">
                <div class="soft-card-hdr">
                    <div>
                        <div style="font-size:1.05rem; font-weight:800; color:#0f172a;">Probabilidad condicional P({html.escape(p3['nombre_evento'])} | grupo)</div>
                        <div style="font-size:0.77rem; color:#64748b;">Comparación de tasa de {html.escape(p3['nombre_evento'].lower())} entre grupos</div>
                    </div>
                    <span class="pill-amber">Tasa global: {fmt_num(p3['p_evento_total'], 4)}</span>
                </div>
                <div style="margin-top:10px;">{"".join(barras_cond_html)}</div>
                <div class="soft-interp-box">
                    <b>Extremos observados:</b> Mayor riesgo en <b>{html.escape(g_may['grupo'])} ({fmt_num(g_may['p_cond'], 4)})</b> y menor en <b>{html.escape(g_men['grupo'])} ({fmt_num(g_men['p_cond'], 4)})</b>.
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Fila inferior: Teorema de Bayes | Veredicto de Independencia
        cb1, cb2 = st.columns([1, 1.15], gap="medium")

        with cb1:
            st.markdown(f"""
            <div class="soft-card">
                <div class="soft-card-hdr">
                    <div>
                        <div style="font-size:1.05rem; font-weight:800; color:#0f172a;">Teorema de Bayes: ¿de dónde viene { 'un crash' if info['caso']=='NovaApp' else 'una garantía' }?</div>
                        <div style="font-size:0.77rem; color:#64748b;">Actualización de probabilidad para <b>{html.escape(p3['b_grupo'])}</b> dada la evidencia</div>
                    </div>
                    <span class="pill-lavender">Bayes E7</span>
                </div>
                <div class="soft-kpi-grid3" style="grid-template-columns: repeat(2, 1fr); margin: 10px 0;">
                    <div class="soft-kpi-card" style="background:#f8fafc;">
                        <div class="soft-kpi-top">ANTES · P({html.escape(p3['b_grupo'])})</div>
                        <div class="soft-kpi-val">{fmt_num(p3['b_prior'], 4)}</div>
                        <div class="soft-kpi-sub">{fmt_num(p3['b_prior']*100, 2)} % (a priori sin evidencia)</div>
                    </div>
                    <div class="soft-kpi-card" style="border: 1.5px solid #f59e0b; background:#fffbeb;">
                        <div class="soft-kpi-top" style="color:#b45309;">DESPUÉS · P({html.escape(p3['b_grupo'])} | {html.escape(p3['nombre_evento'])})</div>
                        <div class="soft-kpi-val" style="color:#b45309;">{fmt_num(p3['b_post'], 4)}</div>
                        <div class="soft-kpi-sub">{fmt_num(p3['b_post']*100, 2)} % (a posteriori con evidencia)</div>
                    </div>
                </div>
                <div class="soft-interp-box">
                    <div class="soft-interp-hdr">💡 LECTURA DE NEGOCIO (BAYES)</div>
                    <div>
                        Saber que ocurrió <b>{html.escape(p3['nombre_evento'].lower())}</b> multiplica por <b>{fmt_num(p3['b_factor'], 2)}x</b> la probabilidad de que provenga de <b>{html.escape(p3['b_grupo'])}</b>:
                        aunque atiende el <b>{fmt_num(p3['b_prior']*100, 1)} %</b> del total, concentra el <b>{fmt_num(p3['b_post']*100, 2)} %</b> de los casos de {html.escape(p3['nombre_evento'].lower())}
                        (P = {fmt_num(p3['b_post'], 4)}).
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with cb2:
            filas_ind_html = []
            frases_ind_html = []
            for r_i in p3["resultados_indep"]:
                cls_v = "pill-mint" if r_i["es_indep"] else "pill-amber"
                filas_ind_html.append(
                    f"<tr>"
                    f"<td><b>{html.escape(r_i['lbl_cond'])}</b></td>"
                    f"<td class='num'><b>{fmt_num(r_i['val_cond'], 4)}</b></td>"
                    f"<td>{html.escape(r_i['lbl_base'])}</td>"
                    f"<td class='num'>{fmt_num(r_i['val_base'], 4)}</td>"
                    f"<td class='num'>{fmt_num(r_i['diff'], 4)}</td>"
                    f"<td><span class='{cls_v}'>{html.escape(r_i['veredicto'])}</span></td>"
                    f"</tr>"
                )
                frases_ind_html.append(f"<li style='margin-bottom:4px;'>{html.escape(r_i['explicacion'])}</li>")

            st.markdown(f"""
            <div class="soft-card">
                <div class="soft-card-hdr">
                    <div>
                        <div style="font-size:1.05rem; font-weight:800; color:#0f172a;">¿Son independientes los eventos?</div>
                        <div style="font-size:0.77rem; color:#64748b;">Regla oficial: si |P(A|B) − P(A)| &lt; 0,02 son «Prácticamente independientes»</div>
                    </div>
                    <span class="pill-mint">Umbral 0,02</span>
                </div>
                <div class="table-scroll">
                    <table class="soft-table">
                        <thead>
                            <tr>
                                <th>Condicional P(A|B)</th>
                                <th class="num">Valor</th>
                                <th>Marginal P(A)</th>
                                <th class="num">Valor</th>
                                <th class="num">|Dif.|</th>
                                <th>Veredicto</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(filas_ind_html)}</tbody>
                    </table>
                </div>
                <div class="soft-interp-box">
                    <div class="soft-interp-hdr">💡 INTERPRETACIÓN DE INDEPENDENCIA</div>
                    <ul style="margin:4px 0 0 16px; padding:0;">{"".join(frases_ind_html)}</ul>
                </div>
            </div>
            """, unsafe_allow_html=True)