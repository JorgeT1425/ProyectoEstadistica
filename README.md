# EstadiApp · Analítica para Decidir (Proyecto Integrador 259G8F — Hito 1)

Aplicación web interactiva desarrollada en **Python + Streamlit** con interfaz **Soft UI** para el procesamiento dinámico de archivos CSV/XLSX, validación de esquemas, estadística descriptiva y modelos de probabilidad (Condicional, Teorema de Bayes e Independencia).

Proyecto desarrollado para la asignatura **Estadística y Probabilidad para Inteligencia de Negocio (259G8F)** — Programa de Ingeniería Informática, Facultad de Inteligencia Artificial e Ingenierías, **Universidad de Caldas**.

---

## 👥 Integrantes de la Dupla

* **Integrante 1:** [Nombre Completo Integrante 1] — Código: [Código Estudiantil]
* **Integrante 2:** [Nombre Completo Integrante 2] — Código: [Código Estudiantil]
* **Caso de Negocio Soportado:** MotoExpres S.A.S. (21 columnas) / NovaApp (17 columnas) — *Detección dinámica automática*.
* **Entrega:** Hito 1 · Primera versión del proyecto (Encuentro 9 — Módulos M1, M2 y M3).

---

## 🚀 Requisitos e Instalación

### 1. Clonar el repositorio o descargar los archivos
```bash
git clone <URL_DEL_REPOSITORIO>
cd <NOMBRE_DE_LA_CARPETA>
```

### 2. Instalar las dependencias necesarias
Asegúrate de tener Python 3.9+ instalado y ejecuta:
```bash
pip install -r requirements.txt
```
*(Librerías requeridas: `streamlit`, `pandas`, `numpy`, `openpyxl`).*

### 3. Ejecutar la aplicación
```bash
streamlit run app.py
```
Si en Windows el comando `streamlit` no está en el PATH global, ejecútalo con:
```bash
python -m streamlit run app.py
```
La aplicación se abrirá automáticamente en tu navegador en `http://localhost:8501`.

---

## 🧩 Arquitectura y Módulos Implementados (Hito 1)

El código sigue el principio de **separación entre cálculo e interfaz** y cumple estrictamente los **cinco mínimos no negociables** (cero rutas fijas y cero valores quemados):

1. **M1 · Carga y Validación (Encuentro 1):**
   * Carga interactiva de archivos `.csv` (UTF-8, separador coma, punto decimal) y `.xlsx` (lectura automática de la hoja `datos`).
   * Validación exhaustiva en 6 dimensiones: nombres y orden exacto de columnas (`21` en MotoExpres / `17` en NovaApp), celdas vacías por columna, filas duplicadas, unicidad del identificador (`id_servicio` / `id_sesion`), tipos de datos (números, fechas ISO 8601, binarias `Sí`/`No`) y rangos de valores.
   * Si se sube un archivo con errores, la aplicación detalla exactamente qué columna y cuántas filas fallan sin cerrarse.
   * Resumen dinámico (filas, columnas, fechas desde/hasta, mecánicos/versiones, clientes/usuarios distintos, sedes/países) y vista previa de las primeras 10 filas.
   * Indicador persistente en todas las pantallas con el nombre del archivo cargado y la hora exacta de carga.

2. **M2 · Análisis Descriptivo (Encuentros 2 a 4):**
   * Selector interactivo de variable numérica y filtro en vivo por `sede` (MotoExpres) o `plataforma` (NovaApp).
   * Cálculo exacto según las convenciones de la Sección 7: media, mediana, desviación estándar muestral ($s$ con $n-1$, `ddof=1`), coeficiente de variación ($\text{CV}\%$), cuartiles lineales ($Q_1, Q_3$), rango intercuartílico ($\text{IQR}$), mínimo, máximo, coeficiente de asimetría ajustado (`skew()`) y conteo de atípicos con la regla $1,5 \cdot \text{IQR}$.
   * Tres gráficos con título, ejes rotulados y lectura: Histograma de frecuencias por intervalo, Gráfico de barras horizontales de frecuencias categóricas (con conteo y %) y Boxplot horizontal por grupo.
   * Análisis por grupo (Sede con mayor costo medio, Mecánico más consistente con menor CV, o Plataforma con carga más estable) y estadísticos de la variable ordinal (`satisfaccion` / `calificacion`: moda y media).

3. **M3 · Probabilidad, Condicional y Bayes (Encuentros 6 y 7):**
   * Probabilidades básicas calculadas como frecuencias relativas y verificación explícita de la regla de la suma: $P(A \cup B) = P(A) + P(B) - P(A \cap B)$.
   * Tabla de contingencia completa y gráfico de probabilidades condicionales para **todos** los grupos presentes en el archivo cargado, identificando automáticamente el mayor y el menor.
   * Actualización de probabilidad mediante el **Teorema de Bayes** comparando la probabilidad *a priori* frente a la probabilidad *a posteriori* dada la evidencia (garantía o crash).
   * Evaluación automática de **independencia estadística** bajo la regla $|P(A \mid B) - P(A)| < 0,02$, clasificando entre «Prácticamente independientes» y «Dependientes» con interpretación de negocio dinámica.
