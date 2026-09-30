"""Lectura del export de LogiSur y seleccion de los remitos de Expreso Andino."""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# formas en que aparece Expreso Andino en el export, ya noramlizadas
# (minusculas y espacios simples). Si aparece una variante nueva, se agrega aca.
ALIAS_EXPRESO_ANDINO = {"expreso andino", "exp. andino", "exp andino"}

@dataclass
class ResultadoLectura:
    total_export: int   #remitos en el archivo, de cualquier transportista
    remitos: list   #remitos en expreso andino, sin duplicados
    duplicados: list = field(default_factory=list)  #refs repetidas e identicas, se cargan una vez
    conflictos: list = field(default_factory=list)  #refs repetidas con datos distintos, no se cargan
    transportistas: Counter = field(default_factory=Counter)  #cuantos remitos por transportista


def normalizar_texto(texto) -> str: 
    """' EXPRESO Andino ' -> 'expreso andino'."""
    if not isinstance(texto, str):
        return ""
    return " ".join(texto.split()).lower()


def es_expreso_andino(transportista) -> bool:
    return normalizar_texto(transportista) in ALIAS_EXPRESO_ANDINO


def leer_export(ruta) -> list:
    with Path(ruta).open(encoding="utf-8") as f:
        datos = json.load(f)
    if not isinstance(datos, list):
        raise ValueError(f"Se esperaba una lista de remitos en {ruta}")
    return datos


def seleccionar_remitos_andino(remitos: list) -> ResultadoLectura:
    """Filtra los remitos de Expreso Andino y resuelve los repetidos.
    -Repetido identico: se queda uno solo (es un error del export, no dos envios).
    -Repetido con datos distintos: no se carga ninguno, porque no sabemos cual es el correcto; queda en el resumen para que operaciones lo revise.
    """
    transportistas = Counter(normalizar_texto(r.get("transportista")) for r in remitos)
    andino = [r for r in remitos if es_expreso_andino(r.get("transportista"))]

    por_ref = {}
    for remito in andino:
        por_ref.setdefault(remito.get("nro_remito"), []).append(remito)

    seleccionados, duplicados, conflictos = [], [], []
    for ref, copias in por_ref.items():
        if len(copias) == 1:
            seleccionados.append(copias[0])
        elif all(c == copias [0] for c in copias):
            seleccionados.append(copias[0])
            duplicados.append(ref)
        else:
            conflictos.append(ref)

    return ResultadoLectura(
        total_export=len(remitos),
        remitos=seleccionados,
        duplicados=duplicados,
        conflictos=conflictos,
        transportistas=transportistas,
    )