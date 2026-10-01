from expreso_bridge.transform import normalizar_provincia, parsear_numero, transformar_remito

PROVINCIAS = ["Buenos Aires", "Ciudad Autónoma de Buenos Aires", "Córdoba", "Entre Ríos", "Neuquén", "Santa Fe", "Tucumán"]


def remito_valido(**cambios):
    base = {
        "nro_remito": "R-1",
        "destinatario": {
            "razon_social": "Ferretería El Tornillo",
            "direccion": "Av. San Martín 1234",
            "localidad": "San Isidro",
            "provincia": "Buenos Aires",
            "codigo_postal": "1642",
            "telefono": "1145678901",
        },
        "bultos": 3,
        "peso_kg": 25.4,
        "valor_declarado": 150000.0,
        "transportista": "EXPRESO ANDINO",
        "servicio": "NORMAL",
    }
    Destinatario = cambios.pop("destinatario", {})
    base["destinatario"].update(Destinatario)
    base.update(cambios)
    return base


def test_provincias_con_variantes():
    casos = {
        "Tucuman": "Tucumán", "Neuquen": "Neuquén", "BA": "Buenos Aires", "Bs. As.": "Buenos Aires", "Cba": "Córdoba", "CABA": "Ciudad Autónoma de Buenos Aires", "Capital Federal": "Ciudad Autónoma de Buenos Aires", "  santa fe ": "Santa Fe",
    }
    for entrada, esperado in casos.items():
        assert normalizar_provincia(entrada, PROVINCIAS) == esperado, entrada


def test_provincia_desconocida():
    assert normalizar_provincia("Narnia", PROVINCIAS) is None
    assert normalizar_provincia("", PROVINCIAS) is None


def test_numeros_con_coma_decimal():
    assert parsear_numero("123,45") == 123.45
    assert parsear_numero("1.234,5") == 1234.5
    assert parsear_numero(12.5) == 12.5
    assert parsear_numero("abc") is None


def test_remito_valido_se_transforma_completo():
    envio, errores = transformar_remito(remito_valido(peso_kg="25,4", servicio="URGENTE"), PROVINCIAS)
    assert errores == []
    assert envio == {
        "external_ref" :"R-1",
        "recipient": {
            "name" : "Ferretería El Tornillo",
            "street": "Av. San Martín 1234",
            "city": "San Isidro",
            "province": "Buenos Aires",
            "zip_code": "1642",
            "phone": "1145678901",
        },
        "packages": 3,
        "weight_kg": 25.4,
        "declared_value": 150000.0,
        "service": "express"
    }


def test_codigo_postal_vacio_se_rechaza():
    envio, errores = transformar_remito(remito_valido(destinatario={"codigo_postal": ""}), PROVINCIAS)
    assert envio is None
    assert errores == ["Falta código postal del destinatario"]


def test_direccion_en_blanco_se_rechaza():
    envio, errores = transformar_remito(remito_valido(destinatario={"direccion": "  "}), PROVINCIAS)
    assert envio is None
    assert errores == ["Falta dirección del destinatario"]


def test_cero_bultos_se_rechaza():
    envio, errores = transformar_remito(remito_valido(bultos=0), PROVINCIAS)
    assert envio is None
    assert "bultos" in errores[0]


def test_informa_todos_los_errores_juntos():
    remito = remito_valido(bultos=0, servicio= "EXPRESS PLUS", destinatario={"provincia": "Narnia"})
    _, errores = transformar_remito(remito, PROVINCIAS)
    assert len(errores)== 3 