from expreso_bridge.loader import es_expreso_andino, seleccionar_remitos_andino


def remito(ref, transportista="EXPRESO ANDINO", **extra):
    return {"nro_remito": ref, "transportista": transportista, **extra}


def test_reconoce_las_variantes_del_transportista():
    for variante in ["EXPRESO ANDINO", "Expreso Andino", "EXPRESO ANDINO", "expreso andino", "Exp. Andino", " expreso  andino"]:
        assert es_expreso_andino(variante), variante


def test_descarta_otros_transportistas():
    for otro in ["Cruz del Norte", "RETIRA CLIENTE", "TRANSPORTE LITORAL", "", None]:
        assert not es_expreso_andino(otro), otro


def test_repetido_identico_se_carga_una_vez():
    r = seleccionar_remitos_andino([remito("R-1"), remito("R-1"), remito("R-2")])
    assert [x["nro_remito"] for x in r.remitos] == ["R-1", "R-2"]
    assert r.duplicados == ["R-1"]
    assert r.conflictos == []


def test_repetido_con_datos_distintos_no_se_carga():
    r = seleccionar_remitos_andino([remito("R-1", bultos=2), remito("R-1", bultos=5)])
    assert r.remitos == []
    assert r.conflictos == ["R-1"]