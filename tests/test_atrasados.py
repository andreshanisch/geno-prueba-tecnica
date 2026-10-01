from datetime import date

import requests

from expreso_bridge.atrasados import buscar_atrasados, es_atrasado
from expreso_bridge.client import CREADO, RECHAZADO, YA_EXISTIA
from expreso_bridge.report import Fila

HOY = date(2026, 10, 3)


def test_regla_de_atraso():
    assert es_atrasado("IN_TRANSIT", date(2026, 10, 1), HOY)
    assert es_atrasado("EXCEPTION", date(2026, 10, 2), HOY)
    assert not es_atrasado("DELIVERED", date(2026, 10, 1), HOY) # ya entregado
    assert not es_atrasado("IN_TRANSIT", date(2026, 10, 3), HOY) #vence hoy, todavia no
    assert not es_atrasado("CREATED", date(2026, 10, 5), HOY)


class ClienteFalso:
    def __init__(self, estados):
        self.estados = estados
        self.consultados = []

    def obtener_estado(self, tracking_id):
        self.consultados.append(tracking_id)
        estado = self.estados[tracking_id]
        if isinstance(estado, Exception):
            raise estado
        return estado


def test_busca_solo_entre_los_cargados_y_ordena_por_atraso():
    filas = [
        Fila("R-1", "", "", CREADO, tracking_id="T1"),
        Fila("R-2", "", "", YA_EXISTIA, tracking_id="T2"),
        Fila("R-3", "", "", CREADO, tracking_id="T3"),
        Fila("R-4", "", "", RECHAZADO),
    ]
    cliente = ClienteFalso({
        "T1": {"status": "IN_TRANSIT", "estimated_delivery": "2026-10-02"},
        "T2": {"status": "CREATED", "estimated_delivery": "2026-10-01"},
        "T3": {"status": "DELIVERED", "estimated_delivery": "2026-10-01"},
    })
    atrasados, no_consultados = buscar_atrasados(cliente, filas, HOY)

    assert[(a.nro_remito, a.dias_atraso) for a in atrasados] == [("R-2", 2), ("R-1", 1)]
    assert no_consultados == []
    assert cliente.consultados == ["T1", "T2", "T3"] # el rechazado no se consulta


def test_si_falla_una_consulta_sigue_con_los_demas():
    filas = [Fila("R-1", "", "", CREADO, tracking_id="T1"),
             Fila("R-2", "", "", CREADO, tracking_id="T2")]
    cliente = ClienteFalso({
        "T1": requests.ConnectionError(),
        "T2": {"status": "IN_TRANSIT", "estimated_delivery": "2026-10-01"},
    })
    atrasados, no_consultados = buscar_atrasados(cliente, filas, HOY)

    assert [a.nro_remito for a in atrasados] == ["R-2"]
    assert no_consultados == ["R-1"]