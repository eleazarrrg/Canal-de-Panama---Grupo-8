# Dashboard Compartido — Canal de Panamá

Este archivo tiene dos partes:

1. **Cómo abrir y hacer funcionar `powerbi/base.pbix` desde otra computadora** (para cualquiera del equipo que clone el repo).
2. **Qué se cambió/editó respecto al `.pbix` original y por qué**, para que quede documentado el criterio detrás de cada decisión.

---

## 1. Paso a paso para trabajar desde otra computadora

### 1.1 Cloná el repositorio

```bash
git clone https://github.com/eleazarrrg/Canal-de-Panama---Grupo-8.git
```

Anotá la ruta completa donde quedó la carpeta `data/powerbi/` dentro de tu clon. La vas a necesitar en el paso 1.3. Por ejemplo:

```
C:\Users\TUUSUARIO\Documents\Canal-de-Panama---Grupo-8\data\powerbi
```

### 1.2 Abrí el archivo

Abrí `powerbi/base.pbix` con Power BI Desktop. **Al abrirlo, casi seguro te va a tirar un error de acceso a los datos** — es esperado, no está roto. Esto pasa porque el modelo usa un parámetro (`RutaDatos`) que todavía apunta a la carpeta local de la computadora donde se armó el archivo originalmente, no a la tuya.

### 1.3 Actualizá el parámetro `RutaDatos`

1. Pestaña **Inicio → Transformar datos → Editar parámetros**.
2. Vas a ver el parámetro `RutaDatos` (tipo Texto).
3. Reemplazá el valor actual por la ruta de **tu** carpeta `data/powerbi/` (la del paso 1.1), **sin barra `\` al final**. Ejemplo:
   ```
   C:\Users\TUUSUARIO\Documents\Canal-de-Panama---Grupo-8\data\powerbi
   ```
4. Aceptar.
5. **Inicio → Actualizar** para que las 6 consultas vuelvan a leer los CSV desde tu ruta.

Si el refresh anda bien, el error inicial desaparece y ves los datos normalmente en la vista de Datos/Modelo.

### 1.4 Si vas a regenerar los CSV vos mismo (opcional)

Los 6 CSV de `data/powerbi/` se generan corriendo, **en este orden exacto**, desde la raíz del repo:

```bash
python src/pipeline/export_powerbi.py
python src/ingesta/scraper_tarifas.py
python src/pricing/calculo_ingresos.py
```

El orden importa: `export_powerbi.py` crea `DimFecha`/`DimEsclusa` primero, y `calculo_ingresos.py` reutiliza esos mismos `fecha_id`/`esclusa_id` para que `FactIngresos` calce con el resto. Si no vas a tocar el pipeline, no hace falta correr nada de esto — los CSV que ya están en el repo alcanzan.

### 1.5 Qué NO hace falta tocar

- Las **relaciones** entre tablas ya están armadas en el modelo — no hay que rehacerlas.
- Las **medidas DAX** (tabla `Medidas`) ya están todas cargadas — no hay que copiarlas de nuevo.
- No hace falta marcar ninguna tabla como "tabla de fechas" (ver sección 2.3, quedó decidido no usar esa opción).

### 1.6 Cómo trabajar tu página sin pisar el trabajo de otros

Como un `.pbix` es un archivo binario (Git no puede fusionar cambios de dos personas editándolo a la vez), la mecánica acordada es:

1. Hacé una copia local de `powerbi/base.pbix` y renombrala según la página que te toca, por ejemplo `powerbi/pagina3_agua_transitos.pbix`.
2. Armá **solo** los visuales de esa página ahí (ver `POWERBI_DASHBOARDS.md` para el detalle de qué lleva cada página).
3. Subí tu copia al repo con ese nombre — no sobrescribas `base.pbix`.
4. La consolidación final en un solo archivo se hace después, copiando/pegando los visuales de cada página individual dentro de `base.pbix`.

---

## 2. Qué se cambió/editó y por qué

### 2.1 Carga de los 6 CSV — uno por uno, no "Combine"

**Qué se hizo:** en vez de usar el botón "Combine" del diálogo de carga por carpeta, cada uno de los 6 CSV se cargó individualmente con **Obtener datos → Texto/CSV**.

**Por qué:** "Combine" está pensado para archivos con la misma estructura de columnas (ej. reportes mensuales idénticos) y los apila en una sola tabla. Acá los 6 archivos son tablas distintas (`DimFecha`, `DimEsclusa`, `FactClima`, `FactIngresos`, `FactPronostico`, `FactTransitos`), así que combinarlos las hubiera mezclado incorrectamente.

### 2.2 Parametrización de la ruta de origen (`RutaDatos`)

**Qué se hizo:** se creó un parámetro de texto llamado `RutaDatos`, y se editó el paso "Source" de las 6 consultas para que usen `RutaDatos & "\NombreArchivo.csv"` en vez de la ruta absoluta fija que Power BI puso por default al cargar los archivos.

**Por qué:** la ruta original (`C:\Users\...\OneDrive\Desktop\...`) es específica de una sola computadora. Sin este cambio, el archivo no cargaría datos en la máquina de ningún otro compañero. Con el parámetro, cada persona solo tiene que pegar su propia ruta una vez (ver sección 1.3) y el resto del modelo — relaciones, limpieza, medidas — sigue funcionando igual.

### 2.3 `DimFecha` — se descartó marcarla como "tabla de fechas" oficial

**Qué se hizo:** se intentó usar Modelado → Marcar como tabla de fechas, pero Power BI rechazó la columna `fecha` porque exige un calendario **diario** continuo sin huecos, y `DimFecha` tiene una fila por **mes**. Se decidió no forzar una tabla de calendario diaria aparte (hubiera agregado ~4.000 filas sin necesidad real, dado que todos los datos del proyecto están agregados a nivel mensual).

**Por qué:** el costo de armar y mantener una tabla de calendario diaria no se justifica cuando ninguna otra parte del modelo usa granularidad diaria.

**Consecuencia directa — medida `Tránsitos Año Anterior` reescrita:** la versión original del `.md` usaba `SAMEPERIODLASTYEAR()`, que requiere una tabla de fechas marcada oficialmente. Se reemplazó por una versión con aritmética sobre `fecha_id` (formato `YYYYMM`):

```dax
Tránsitos Año Anterior =
VAR FechaActual = SELECTEDVALUE(DimFecha[fecha_id])
VAR FechaAnterior = FechaActual - 100
RETURN
CALCULATE(
    [Total Tránsitos],
    ALL(DimFecha),
    DimFecha[fecha_id] = FechaAnterior
)
```

Restar 100 a un `fecha_id` tipo `202409` da `202309` — el mismo mes, un año antes. El resto de las medidas del `.md` no se tocó, porque ninguna otra depende del marcado de tabla de fechas.

**Para mostrar fechas en los visuales:** se usa la columna `DimFecha[etiqueta]` (no `fecha_id`) en ejes y tablas, con **"Ordenar por columna"** configurado para que ordene según `fecha_id` — si no, al ser texto, se ordenaría alfabéticamente en vez de cronológicamente.

### 2.4 Tabla `Medidas` separada

**Qué se hizo:** se creó una tabla auxiliar vacía (`Medidas = {1}`, con la columna resultante oculta) para alojar todas las medidas DAX en un solo lugar del panel de campos, organizadas en carpetas de visualización (`Tránsitos`, `Clima`, `Pronóstico`, `Ingresos`).

**Por qué:** evita que las medidas se mezclen visualmente con las columnas reales de las tablas de hechos/dimensiones, y facilita que cualquiera del equipo encuentre rápido la medida que necesita.

### 2.5 Auditoría de calidad de datos — sin cambios en los CSV

Se revisaron a fondo los nulls y valores repetidos visibles en `FactClima`, `FactIngresos` y `FactTransitos`. Conclusión: **no se modificó ningún dato**, porque cada caso tenía una explicación válida dentro del pipeline existente:

| Observación | Explicación | ¿Se tocó algo? |
|---|---|---|
| Nulls en `FactClima[lluvia_acum_12m]` (primeros 11 meses) | No hay suficiente historia para calcular un acumulado de 12 meses hasta el mes 12 de la serie | No |
| Filas con valores repetidos en `FactIngresos` | Coincidencia numérica entre meses/esclusas distintas con el mismo conteo de tránsitos; se confirmó que no hay duplicados por clave `fecha_id + esclusa_id` | No |
| `FactTransitos[tonelaje] = None` en todas las filas de `esclusa_id = 2` (Neopanamax) | Decisión de diseño documentada en `export_powerbi.py`: la fuente solo reporta tonelaje a nivel de canal completo, no por esclusa. El valor total del canal se guarda en la fila de Panamax; el `None` en Neopanamax evita sumar el total dos veces | No |
| `FactTransitos[transitos] = 0` en Neopanamax antes de junio 2016 | Correcto — las esclusas Neopanamax se inauguraron el 26 de junio de 2016, no existían tránsitos antes de esa fecha | No |
| `FactIngresos[prima_subasta_usd] = 0` en septiembre 2024 | La prima se reparte proporcional al déficit de tránsitos vs. el promedio histórico de cada mes calendario; septiembre 2024 (1.140 tránsitos) superó su propio promedio histórico (1.114), por lo que el déficit calculado es 0 y no le corresponde prima ese mes | No |

**Nota para las páginas del reporte:** como el tonelaje se reporta a nivel de canal (no por esclusa), cualquier visual que intente desglosar `Tonelaje Total (M)` por `esclusa_nombre` va a mostrar el 100% concentrado en "Panamax" y "0%" en "Neopanamax" — esto es esperado dado cómo vienen los datos, no un error. Conviene aclararlo con una nota de texto en la Página 2 del reporte, similar a la que ya está planeada en la Página 6 sobre la prima de subasta.

### 2.6 Relaciones del modelo

Se crearon las 6 relaciones indicadas en `POWERBI_DASHBOARDS.md` (`DimFecha`/`DimEsclusa` hacia las 4 tablas de hechos correspondientes), todas con cardinalidad **Uno a varios (1:*)** y estado **Activa**. No se activó filtro cruzado en ambas direcciones para `FactIngresos` ni `FactTransitos` (quedaron en una sola dirección), porque esas dos tablas se conectan a las dos dimensiones a la vez y el filtro bidireccional podría generar ambigüedad entre ellas a través de la dimensión compartida.

---

*Última actualización: ver historial de commits de este archivo en GitHub.*
