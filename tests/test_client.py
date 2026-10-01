import pytest
import requests

from expreso_bridge.client import (CREADO, ERROR, RECHAZADO, YA_EXISTIA, ErrorAutenticacion, ExpresoAndinoClient)

ENVIO = {"external_ref": "R-1"}


class RespuestaFalsa:
    def __init__(self, status_code, cuerpo=None):
        self.status_code = status_code
        self._cuerpo = cuerpo if cuerpo is not None else {}
        self.text = str(self._cuerpo)

    def json(self):
        return self._cuerpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class SesionFalsa:
    """Devuelve en oredn las respuestas que le programamos para cada POST"""

    def __init__(self, respuestas_post, respuestas_get=None):
        self.headers = {}
        self.respuestas_post = list(respuestas_post)
        self.respuestas_get = list(respuestas_get or [])
        self.posts = 0

    def post(self, url, json, timeout):
        self.posts += 1
        r = self.respuestas_post.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def get(self, url, timeout, params=None):
        return self.respuestas_get.pop(0)


def cliente(sesion):
    return ExpresoAndinoClient("http://api", "clave", session=sesion, dormir=lambda s: None)


def test_creado_al_primer_intento():
    sesion = SesionFalsa([RespuestaFalsa(201, {"tracking_id": "AND1"})])
    r = cliente(sesion).crear_envio(ENVIO)
    assert (r.estado, r.tracking_id, r.intentos) == (CREADO, "AND1", 1)


def test_409_al_primer_intento_es_que_ya_existia():
    sesion = SesionFalsa([RespuestaFalsa(409, {"error": "duplicate", "tracking_id": "AND1"})])
    r = cliente(sesion).crear_envio(ENVIO)
    assert (r.estado, r.tracking_id) == (YA_EXISTIA, "AND1")


def test_reintenta_ante_503_hasta_crearlo():
    sesion = SesionFalsa([RespuestaFalsa(503), RespuestaFalsa(503), RespuestaFalsa(201, {"tracking_id": "AND1"})])
    r = cliente(sesion).crear_envio(ENVIO)
    assert (r.estado, r.intentos) == (CREADO, 3)


def test_500_que_si_creo_el_envio_no_se_reporta_como_error():
    # El primer intento da 500 pero el envio quedo creado. el reintento recibe 409.
    sesion = SesionFalsa([RespuestaFalsa(500), RespuestaFalsa(409, {"error": "duplicate", "tracking_id": "AND1"})])
    r = cliente(sesion).crear_envio(ENVIO)
    assert (r.estado, r.tracking_id) == (CREADO, "AND1")
    assert "reintento" in r.detalle


def test_timeout_se_reintenta():
    sesion = SesionFalsa([requests.Timeout(), RespuestaFalsa(201, {"tracking_id": "AND1"})])
    assert cliente(sesion).crear_envio(ENVIO).estado == CREADO


def test_422_no_se_reintenta_y_muestra_el_detalle():
    detalle = {"details": [{"field": "packages", "message": "integer >=1"}]}
    sesion = SesionFalsa([RespuestaFalsa(422, detalle)])
    r = cliente(sesion).crear_envio(ENVIO)
    assert r.estado == RECHAZADO
    assert "packages" in r.detalle
    assert sesion.posts == 1


def test_agota_reintentos_y_confirma_por_consulta_que_no_existe():
    sesion = SesionFalsa([RespuestaFalsa(503)] * 4, [RespuestaFalsa(200, {"items": []})])
    r = cliente(sesion).crear_envio(ENVIO)
    assert r.estado == ERROR
    assert sesion.posts == 4


def test_agota_reintentos_pero_la_consulta_muestra_que_se_creo():
    sesion = SesionFalsa([RespuestaFalsa(500)] * 4, [RespuestaFalsa(200, {"items": [{"tracking_id": "AND1"}]})])
    r = cliente(sesion).crear_envio(ENVIO)
    assert (r.estado, r.tracking_id) == (CREADO, "AND1")


def test_api_key_invalida_corta_la_corrida():
    sesion = SesionFalsa([RespuestaFalsa(401)])
    with pytest.raises(ErrorAutenticacion):
        cliente(sesion).crear_envio(ENVIO)