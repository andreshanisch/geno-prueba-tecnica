"""Transformacion de un remito de LogiSur al formato de envio de Expreso Andino.
Cada remito se convierte en el cuerpo que espera POST /v1/shipments.
Si algun dato no se puede corregir de forma segura, el remito no se envia y devuelve la lista de motivos, para que operaciones lo corriga en origen."""
import unicodedata

SERVICIOS = {"normal": "standard", "urgente": "express"}

# Abreviaturas que aparecen en el export y no se resuelven solo con quitar tildes y mayusculas.
# "BA" y "Bs. As" se toman como provincia de Buenos Aires


ALIAS_PROVINCIAS = {
    "ba": "Buenos Aires",
    "bs as": "Buenos Aires",
    "bsas": "Buenos Aires",
    "pba": "Buenos Aires",
    "caba": "Ciudad Autónoma de Buenos Aires",
    "capital federal": "Ciudad Autónoma de Buenos Aires",
    "cap fed": "Ciudad Autónoma de Buenos Aires",
    "cba": "Córdoba",
}


def _clave(texto:str) -> str:
    """Forma comparable de un texto: 'Bs. As' -> 'bs as', 'Tucumán' -> 'tucuman'."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.replace("."," ").lower().split())


def normalizar_provincia(valor, provincias_validas):
    """Devuelve el nombre exacto que acepta la API, o None si no se reconoce."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    clave = _clave(valor)
    for provincia in provincias_validas:
        if _clave(provincia) == clave:
            return provincia
    alias = ALIAS_PROVINCIAS.get(clave)
    return alias if alias in provincias_validas else None


def parsear_numero(valor):
    """Acepta 12.5, 12, '12,5', '1.234,5'. Devuelve float o None si no es un numero."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        texto = valor.strip()
        if "," in texto:
            # punto separa miles y coma decimales.
            texto = texto.replace(".", "").replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return None
    return None


def parsear_entero(valor):
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def _texto(valor) -> str:
    return " ".join(valor.split()) if isinstance(valor, str) else ""


def transformar_remito(remito: dict, provincias_validas):
    """Convierte un remito al cuerpo de POST /v1/shipments.
    Devuelve (envio, errores). Si errores no esta vacio, envio es none.
    """
    errores = []
    dest = remito.get("destinatario") or {}

    ref = _texto(remito.get("nro_remito"))
    if not ref:
        errores.append("Falta el numero de remito")

    recipient = {
        "name": _texto(dest.get("razon_social")),
        "street": _texto(dest.get("direccion")),
        "city": _texto(dest.get("localidad")),
        "zip_code": _texto(dest.get("codigo_postal")),
    }
    etiquetas = {"name": "razón social", "street": "dirección", "city": "localidad", "zip_code": "código postal"}
    for campo, etiqueta in etiquetas.items():
        if not recipient[campo]:
            errores.append(f"Falta {etiqueta} del destinatario")

    provincia_original = dest.get("provincia")
    provincia = normalizar_provincia(provincia_original, provincias_validas)
    if provincia is None:
        errores.append(f"Provincia no reconocida: {provincia_original!r}")
    recipient["province"] = provincia

    telefono = _texto(dest.get("telefono"))
    if telefono:
        recipient["phone"] = telefono

    bultos = parsear_entero(remito.get("bultos"))
    if bultos is None or bultos < 1:
        errores.append(f"Cantidad de bultos inválida: {remito.get('bultos')!r} (minimo 1)")

    peso = parsear_numero(remito.get("peso_kg"))
    if peso is None or peso <= 0:
        errores.append(f"Peso inválido: {remito.get('peso_kg')!r} (debe ser mayor a 0)")

    servicio = SERVICIOS.get(_texto(remito.get("servicio")).lower())
    if servicio is None:
        errores.append(f"Servicio desconocido: {remito.get('servicio')!r}")

    envio = {
        "external_ref": ref,
        "recipient": recipient,
        "packages": bultos,
        "weight_kg": peso,
        "service": servicio,
    }

    # El valor declarado es opcional para la API. Si viene mal, se informa pero no se inventa un valor. Se prefiere no cargar a cargar con un seguro erroneo.
    if remito.get("valor_declarado") is not None:
        valor = parsear_numero(remito.get("valor_declarado"))
        if valor is None or valor < 0:
            errores.append(f"Valor declarado inválido: {remito.get('valor_declarado')!r}")
        else:
            envio["declared_value"] = valor

    if errores:
        return None, errores
    return envio, []