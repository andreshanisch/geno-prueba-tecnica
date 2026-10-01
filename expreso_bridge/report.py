"""  Resumen de una corrida, pensado para el equipo de operaciones.
   Se generan dos archivos: 
   - detalle.csv: una fila por remito, para filtrar y ordenar en Excel.
   - resumen.md: el panorama general y la lista de lo que hay que revisar."""

import csv
from collections import Counter
from dataclasses import dataclass

from .client import CREADO, ERROR, RECHAZADO, YA_EXISTIA

ETIQUETAS = {
    CREADO: "Cargado",
    YA_EXISTIA: "Ya estaba cargado",
    RECHAZADO: "Rechazado (corregir datos)",
    ERROR: "Error técnico (reintentar)",
}


@dataclass
class Fila:
    nro_remito: str
    destinatario: str
    localidad: str
    estado: str 
    tracking_id: str = ""
    motivo: str = ""
    intentos: int = 0


def escribir_csv(filas, ruta):
    # utf-8-sig y ";" para que Excel en español lo abra con tildes y columnas bien separadas.
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["nro_remito", "estado", "tracking_id", "motivo", "destinatario", "localidad", "intentos"])
        for fila in filas:
            w.writerow([fila.nro_remito, ETIQUETAS.get(fila.estado, fila.estado), fila.tracking_id or "", fila.motivo, fila.destinatario, fila.localidad, fila.intentos])


def escribir_resumen(filas, lectura, archivo_export, momento, ruta):
    conteo = Counter(f.estado for f in filas)
    a_revisar = [f for f in filas if f.estado in (RECHAZADO, ERROR)]

    lineas = [
        "#Resumen de carga en Expreso Andino",
        "",
        f"- **Archivo:** '{archivo_export}'",
        f"- **Fecha de la corrida:** {momento:%Y-%m-%d %H:%M:%S}",
        f"- **Remitos en el export:** {lectura.total_export} "
        f"(de Expreso Andino: {len(lectura.remitos) + len(lectura.conflictos)} sin contar repetidos)",
        "",
        "| Resultado | Cantidad |",
        "| --- | ---: |",
    ]
    for estado in (CREADO, YA_EXISTIA, RECHAZADO, ERROR):
        lineas.append(f"| {ETIQUETAS[estado]} | {conteo.get(estado, 0)} |")

    lineas += ["", "## Para revisar", ""]
    if a_revisar:
        lineas += ["| Remito | Destinatario | Resultado | Motivo |", "| --- | --- | --- | --- |"]

        for f in a_revisar:
            lineas.append(f"| {f.nro_remito} | {f.destinatario} | {ETIQUETAS[f.estado]} | {f.motivo} |")
        if conteo.get(ERROR):
            lineas += ["", "Los errores técnicos se pueden reintentar volviendo a correr en el programa. Los envíos ya cargados no se duplican."]
    else:
        lineas.append("Nada pendiente. Todos los remitos quedaron cargados en Expreso Andino.")

    lineas += ["", "## Observaciones del export", ""]
    observaciones = []
    for ref in lectura.duplicados:
        observaciones.append(f"- {ref} aparece repetido con los mismos datos: se cargó una sola vez.")
    for ref in lectura.conflictos:
        observaciones.append(f"- {ref} aparece repetido con datos distintos: no se cargó.")
    lineas += observaciones or ["- Sin observaciones."]

    lineas += ["", "## Remitos por transportista (todo el export)", ""]
    for nombre, cantidad in lectura.transportistas.most_common():
        lineas.append(f"- {nombre or '(vacío)'}: {cantidad}")

    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")