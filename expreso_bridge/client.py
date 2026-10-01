""" Cliente de la API de Expreso Andino"""
import time
from dataclasses import dataclass

import requests

# Codigos que indican un problema transitorio del lado del expreso: vale la pena reintentar
CODIGOS_REINTENTABLES = {500, 502, 503, 504}

# Posibles resultados de cargar un envio
CREADO = "creado"   # Se creo en esta corrida
YA_EXISTIA = "ya existia"   # Ya estaba cargado de antes (ejemplo, una corrida anterior)
RECHAZADO = "rechazado" # La API no acepta los datos. Hay que corregirlos en orden
ERROR = "error" # No se pudo cargar por un problema tecnico. reintentar mas tarde


class ErrorAutenticacion(Exception):
    """La API rechazó la API key. No tiene sentido seguir con la corrida."""


@dataclass
class ResultadoCarga:
    estado: str
    tracking_id: str = None
    detalle: str = ""
    intentos: int = 0


class ExpresoAndinoClient:
    def __init__(self, base_url, api_key, timeout=10, max_intentos=4, espera_base=0.5, session=None, dormir=time.sleep):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_intentos = max_intentos
        self.espera_base = espera_base
        self.session = session or requests.Session()
        self.session.headers.update({"X-Api-Key": api_key})
        self._dormir = dormir   

    def _get(self, ruta, **kwargs):
        resp = self.session.get(self.base_url + ruta, timeout=self.timeout, **kwargs)
        if resp.status_code == 401:
            raise ErrorAutenticacion("La API rechazó la API key (401)")
        resp.raise_for_status()
        return resp.json()

    def obtener_provincias(self):
        return self._get("/v1/provinces") ["provinces"]

    def buscar_por_ref(self, external_ref):
        """Devuelve el tracking_id del envío con esa referencia, o None si no existe."""
        items = self._get("/v1/shipments", params={"external_ref": external_ref})["items"]
        return items[0]["tracking_id"] if items else None

    def obtener_estado(self, tracking_id):
        return self._get(f"/v1/shipments/{tracking_id}")

    def crear_envio(self, envio) -> ResultadoCarga:
        """Carga un envío, reintentando ante errores transitorios.
        Punto clave: un 500 o un timeput no garantizan que el envio NO se haya creado. Por eso, si un reintento recibe 409, el envío quedó
        creado por nuestro intento anterior y lo contamos como creado, no como error."""
        ultimo_problema = ""
        for intento in range(1, self.max_intentos + 1):
            if intento > 1:
                self._dormir(self.espera_base * 2 ** (intento - 2))     # 0.5s, 1s, 2s...

            try:
                resp = self.session.post(self.base_url + "/v1/shipments", json=envio, timeout=self.timeout)
            except requests.RequestException as exc:
                ultimo_problema = f"sin respuesta de la API ({type(exc).__name__})"
                continue

            cuerpo = _json_o_vacio(resp)
            codigo = resp.status_code

            if codigo == 201:
                return ResultadoCarga(CREADO, cuerpo.get("tracking_id"), "", intento)

            if codigo == 409:
                if intento == 1:
                    return ResultadoCarga(YA_EXISTIA, cuerpo.get("tracking_id"), "Ya estaba cargado en Expreso Andino", intento)
                return ResultadoCarga(CREADO, cuerpo.get("tracking_id"), f"Creado; confirmado tras reintento ({ultimo_problema})", intento)

            if codigo == 422:
                detalles = "; ".join(f"{d.get('field')}: {d.get('message')}" for d in cuerpo.get("details", []))
                return ResultadoCarga(RECHAZADO, None, f"La API rechazó los datos: {detalles}", intento)

            if codigo == 401:
                raise ErrorAutenticacion("La API rechazó la API key (401)")

            if codigo in CODIGOS_REINTENTABLES:
                ultimo_problema = f"HTTP {codigo} {cuerpo.get('error', '')}".strip()
                continue

            # Cualquier otro codigo es inesperado. No reintentamos a ciegas.
            return ResultadoCarga(ERROR, None, f"Respuesta inesperada HTTP {codigo}: {resp.text[:200]}", intento)

        # Se agotaron los reintentos. Antes de darlo por fallido, consultamos si alguno de los intentos llego a crearlo.
        try:
            tracking = self.buscar_por_ref(envio["external_ref"])
        except (requests.RequestException, ValueError):
            tracking = None
        if tracking:
            return ResultadoCarga(CREADO, tracking, f"Creado; confirmado por consulta ({ultimo_problema})", self.max_intentos)
        return ResultadoCarga(ERROR, None, f"No se pudo cargar tras {self.max_intentos} intentos: {ultimo_problema}", self.max_intentos)


def _json_o_vacio(resp):
    try: 
        cuerpo = resp.json()
        return cuerpo if isinstance(cuerpo, dict) else {}
    except ValueError:
        return {}