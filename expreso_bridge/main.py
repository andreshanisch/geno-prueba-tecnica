""" Puente LogiSur -> Expreso Andino.

Uso:
    python -m expreso_bridge.main data/remitos_2026-09-30.json
    python -m expreso_bridge.main data/remitos_2026-09-30.json --atrasados --hoy 2026-10-03
    
Configuración por variables de entorno (con valores por defecto para el entorno de prueba):
    EXPRESO_API_URL    URL base de la API    (default: http://localhost:8000)
    EXPRESO_API_KEY    API key               (default: la del entorno de prueba)"""

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests

from .atrasados import buscar_atrasados, informar_atrasados
from .client import CREADO, ERROR, RECHAZADO, ErrorAutenticacion, ExpresoAndinoClient
from .loader import leer_export, seleccionar_remitos_andino
from .report import Fila, escribir_csv, escribir_resumen
from .transform import transformar_remito

API_URL_PRUEBA = "http://localhost:8000"
API_KEY_PRUEBA = "andino-test-7f3a91"


def ejecutar(ruta_export, cliente, carpeta_salida, momento=None, hoy_atrasados=None):
    """ Corre el proceso completo y devuelve la lista de filas del resumen.
    Si se pasa hoy_atrasados (una fecha), ademas consulta el estado de los envios cargados y la lista los atrasados a esa fecha."""
    momento = momento or datetime.now()
    lectura = seleccionar_remitos_andino(leer_export(ruta_export))
    provincias = cliente.obtener_provincias()
    print(f"{lectura.total_export} remitos en el export, "
          f"{len(lectura.remitos)} de Expreso Andino para procesar.")

    filas = []
    for remito in lectura.remitos:
        dest = remito.get("destinatario") or {}
        fila = Fila(nro_remito=remito.get("nro_remito"), destinatario=dest.get("razon_social") or "", localidad=dest.get("localidad") or "", estado="")

        envio, errores = transformar_remito(remito, provincias)
        if errores:
            fila.estado, fila.motivo = RECHAZADO, "; ".join(errores)
        else:
            resultado = cliente.crear_envio(envio)
            fila.estado = resultado.estado
            fila.tracking_id = resultado.tracking_id
            fila.motivo = resultado.detalle
            fila.intentos = resultado.intentos

        print(f"  {fila.nro_remito}: {fila.estado} {fila.motivo}".rstrip())
        filas.append(fila)

    for ref in lectura.conflictos:
        filas.append(Fila(ref, "", "", RECHAZADO, motivo="Remito repetido en el export con datos distintos"))

    carpeta = Path(carpeta_salida) / f"corrida_{momento:%Y%m%d_%H%M%S}"
    carpeta.mkdir(parents=True, exist_ok=True)
    escribir_csv(filas, carpeta / "detalle.csv")
    escribir_resumen(filas, lectura, Path(ruta_export).name, momento, carpeta / "resumen.md")
    if hoy_atrasados:
        atrasados, no_consultados = buscar_atrasados(cliente, filas, hoy_atrasados)
        informar_atrasados(atrasados, no_consultados, hoy_atrasados, carpeta)
        print(f"Envíos atrasados al {hoy_atrasados:%d/%m/%Y}: {len(atrasados)}")
    print(f"Resumen guardado en {carpeta}")
    return filas


def main(argv=None):
    parser = argparse.ArgumentParser(description="Carga en Expreso Andino los remitos del export de LogiSur.")
    parser.add_argument("export", help="Ruta al JSON exportado por LogiSur")
    parser.add_argument("--salida", default="output", help="Carpeta donde guardar el resumen (default: output)")
    parser.add_argument("--atrasados", action="store_true", help="Además, listar los envíos cargados que están atrasados")
    parser.add_argument("--hoy", type=date.fromisoformat, default=date.today(), help="Fecha de referencia para los atrasados, AAAA-MM-DD (default: hoy)")
    args = parser.parse_args(argv)

    cliente = ExpresoAndinoClient(os.environ.get("EXPRESO_API_URL", API_URL_PRUEBA),
                                  os.environ.get("EXPRESO_API_KEY", API_KEY_PRUEBA))
    try:
        filas = ejecutar(args.export, cliente, args.salida, hoy_atrasados=args.hoy if args.atrasados else None)
    except ErrorAutenticacion as exc:
        print(f"ERROR: {exc}. Revisar EXPRESO_API_KEY.", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f"ERROR: no se pudo conectar con la API ({exc}). ¿Está levantada?", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"ERROR: no se pudo leer el export ({exc}).", file=sys.stderr)
        return 2

    creados = sum(f.estado == CREADO for f in filas)
    errores = sum(f.estado == ERROR for f in filas)
    print(f"Listo: {creados} cargados en esta corrida, {errores} con error técnico.")
    # Codigo de salida 1 si quedaron errores tecnicos, para que un scheduler pueda alertar.
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())