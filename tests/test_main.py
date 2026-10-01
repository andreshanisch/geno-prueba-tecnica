import json 

from expreso_bridge.client import CREADO, RECHAZADO, YA_EXISTIA, ResultadoCarga
from expreso_bridge.main import ejecutar


class ClienteFalso:
    """Simula la API: recuerda lo cargado y responde 'ya existía' si se repite."""

    def __init__(self):
        self.cargados = {}

    def obtener_provincias(self):
        return ["Buenos Aires", "Córdoba"]

    def crear_envio(self, envio):
        ref = envio["external_ref"]
        if ref in self.cargados:
            return ResultadoCarga(YA_EXISTIA, self.cargados[ref], "Ya estaba cargado",1)
        self.cargados[ref] = "AND-" + ref
        return ResultadoCarga(CREADO, self.cargados[ref], "", 1)


def remito(ref, transportista="EXPRESO ANDINO", **cambios):
    base = {
        "nro_remito":ref, "transportista": transportista, "servicio": "NORMAL", "bultos": 1, "peso_kg": "10,5", "valor_declarado": 1000.0, "destinatario": {"razon_social": "Cliente", "direccion": "Calle 1", "localidad": "Pilar", "provincia": "BA", "codigo_postal": "1629", "telefono": ""},
    }
    base.update(cambios)
    return base


def escribir_export(tmp_path, remitos):
    ruta = tmp_path / "export.json"
    ruta.write_text(json.dumps(remitos), encoding="utf-8")
    return ruta


def test_corrida_completa_y_genera_archivos(tmp_path):
    ruta = escribir_export(tmp_path, [remito("R-1"), remito("R-2", bultos=0), remito("R-3", transportista="Cruz del Norte"),
    ])
    filas = ejecutar(ruta, ClienteFalso(), tmp_path / "out")

    assert [(f.nro_remito, f.estado) for f in filas] == [("R-1", CREADO), ("R-2", RECHAZADO)]
    carpeta = next((tmp_path / "out").iterdir())
    assert (carpeta / "detalle.csv").exists()
    assert "R-2" in (carpeta / "resumen.md").read_text(encoding="utf-8")


def test_volver_a_correr_no_duplica(tmp_path):
    ruta = escribir_export(tmp_path, [remito("R-1"), remito("R-2")])
    cliente = ClienteFalso()

    ejecutar(ruta, cliente, tmp_path / "out1")
    segunda = ejecutar(ruta, cliente, tmp_path / "out2")

    assert all(f.estado == YA_EXISTIA for f in segunda)
    assert len(cliente.cargados) == 2