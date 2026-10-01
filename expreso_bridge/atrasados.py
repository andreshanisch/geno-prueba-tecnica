"""Consulta del estado de los envios cargados y deteccion de atrasados.
Un envio esta atrasado si todavia no fue entregado y su fecha estimada de entrega ya paso (es anterior a "hoy")."""
import csv
from dataclasses import dataclass
from datetime import date

import requests

from .client import CREADO, YA_EXISTIA

ENTREGADO = "DELIVERED"


@dataclass
class Atrasado:
    nro_remito: str
    tracking_id: str
    estado_envio: str
    fecha_estimada: date
    dias_atraso: int


def es_atrasado(estado_envio, fecha_estimada, hoy) -> bool:
    return estado_envio != ENTREGADO and fecha_estimada < hoy


def buscar_atrasados(cliente, filas, hoy):
    """Consulta cada envio cargado (en esta corrida o antes) y devuelve (atrasados, no_consultados). Un fallo al consultar uno no frena al resto."""
    atrasados, no_consultados = [], []
    for fila in filas:
        if fila.estado not in (CREADO, YA_EXISTIA) or not fila.tracking_id:
            continue
        try:
            info = cliente.obtener_estado(fila.tracking_id)
            fecha = date.fromisoformat(info["estimated_delivery"])
        except (requests.RequestException, KeyError, ValueError, TypeError):
            no_consultados.append(fila.nro_remito)
            continue
        if es_atrasado(info.get("status"),fecha, hoy):
            atrasados.append(Atrasado(fila.nro_remito, fila.tracking_id, info.get("status"), fecha, (hoy - fecha).days))
    atrasados.sort(key=lambda a: a.dias_atraso, reverse=True) # los mas atrasados primero
    return atrasados, no_consultados


def informar_atrasados(atrasados, no_consultados, hoy, carpeta):
    """Escribe atrasados.csv y agrega una seccion al resumen.md de la corrida."""
    with open(carpeta / "atrasados.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["nro_remito", "tracking_id", "estado_envio", "fecha_estimada", "dias_atraso"])
        for a in atrasados:
            w.writerow([a.nro_remito, a.tracking_id, a.estado_envio, a.fecha_estimada.isoformat(), a.dias_atraso])

    lineas = ["", f"## Envíos atrasados al {hoy:%d/%m/%Y}",""]
    if atrasados:
        lineas += ["| Remito | Tracking | Estado | Fecha estimada | Días de atraso |", "| --- | --- | --- | --- | ---: |"]
        for a in atrasados:
            lineas.append(f"| {a.nro_remito} | {a.tracking_id} | {a.estado_envio} | " f"{a.fecha_estimada:%d/%m/%Y} | {a.dias_atraso} |")
    else:
        lineas.append("No hay envíos atrasados.")
    if no_consultados:
        lineas += ["", "No se pudo consultar el estado de: " + ", ".join(no_consultados)]

    with open(carpeta / "resumen.md", "a", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")