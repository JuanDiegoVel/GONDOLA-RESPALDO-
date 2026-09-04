"""Tests de la evaluacion (gondola/evaluate/evaluator.py).

Los casos estan calculados A MANO en los docstrings. Si un dia el codigo
cambia y estos numeros dejan de salir, el que se equivoco es el codigo: la
aritmetica de precision y recall no se negocia.
"""

import pytest

from gondola.errors import GondolaError
from gondola.evaluate.evaluator import (
    Anotacion,
    Puntaje,
    emparejar,
    evaluar,
    leer_groundtruth,
)


def a(t: float, event: str = "PICK_UP", zona: str = "gondola_A") -> Anotacion:
    return Anotacion(video_id="video_001", timestamp=t, zone_id=zona, event=event)


def puntaje_de(puntajes, etiqueta):
    return next(p for p in puntajes if p.etiqueta == etiqueta)


# --------------------------------------------------------------------------
# La aritmetica
# --------------------------------------------------------------------------

def test_precision_recall_y_f1_en_un_caso_calculado_a_mano():
    """TP=6, FP=2, FN=4:
        precision = 6/8  = 0.75
        recall    = 6/10 = 0.60
        F1        = 2*0.75*0.60 / 1.35 = 0.6667
    """
    p = Puntaje("PICK_UP", tp=6, fp=2, fn=4)
    assert p.precision == pytest.approx(0.75)
    assert p.recall == pytest.approx(0.60)
    assert p.f1 == pytest.approx(0.666666, abs=1e-5)


def test_un_sistema_perfecto_da_uno_en_todo():
    p = Puntaje("PICK_UP", tp=10, fp=0, fn=0)
    assert (p.precision, p.recall, p.f1) == (1.0, 1.0, 1.0)


def test_un_sistema_que_nunca_reporta_nada_tiene_recall_cero():
    """Y precision 0.0 por convenio: no dijo nada, no acerto nada."""
    p = Puntaje("PICK_UP", tp=0, fp=0, fn=10)
    assert p.recall == 0.0
    assert p.precision == 0.0
    assert p.f1 == 0.0


def test_un_sistema_que_se_lo_inventa_todo_tiene_precision_cero():
    p = Puntaje("PICK_UP", tp=0, fp=10, fn=0)
    assert p.precision == 0.0
    assert p.f1 == 0.0


def test_el_f1_castiga_que_una_de_las_dos_sea_mala():
    """precision 1.0 y recall 0.1 NO dan 0.55: dan 0.18. Esa es la gracia."""
    p = Puntaje("PICK_UP", tp=1, fp=0, fn=9)
    assert p.precision == 1.0
    assert p.recall == pytest.approx(0.1)
    assert p.f1 == pytest.approx(0.181818, abs=1e-5)


def test_no_hay_division_por_cero_con_todo_en_cero():
    p = Puntaje("PICK_UP", tp=0, fp=0, fn=0)
    assert (p.precision, p.recall, p.f1) == (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------
# Emparejamiento
# --------------------------------------------------------------------------

def test_un_evento_dentro_de_la_tolerancia_es_un_acierto():
    tp, fp, fn = emparejar([a(10.0)], [a(11.5)], tolerancia_s=2.0)
    assert (tp, fp, fn) == (1, 0, 0)


def test_un_evento_fuera_de_la_tolerancia_es_un_fallo_doble():
    """Ni lo encontro (FN) y ademas reporto uno que no era (FP)."""
    tp, fp, fn = emparejar([a(10.0)], [a(20.0)], tolerancia_s=2.0)
    assert (tp, fp, fn) == (0, 1, 1)


def test_justo_en_el_limite_de_la_tolerancia_cuenta_como_acierto():
    tp, _, _ = emparejar([a(10.0)], [a(12.0)], tolerancia_s=2.0)
    assert tp == 1


def test_un_evento_del_tipo_equivocado_no_empareja():
    """Detectar un PUT_BACK donde hubo un PICK_UP es equivocarse, no acertar."""
    tp, fp, fn = emparejar([a(10.0, "PICK_UP")], [a(10.0, "PUT_BACK")], 2.0)
    assert (tp, fp, fn) == (0, 1, 1)


def test_un_evento_en_la_zona_equivocada_no_empareja():
    tp, fp, fn = emparejar([a(10.0, zona="gondola_A")], [a(10.0, zona="gondola_B")], 2.0)
    assert (tp, fp, fn) == (0, 1, 1)


def test_contar_el_mismo_evento_dos_veces_se_penaliza():
    """Dos detecciones para una anotacion: una acierta, la otra es falso positivo."""
    tp, fp, fn = emparejar([a(10.0)], [a(10.1), a(10.2)], tolerancia_s=2.0)
    assert (tp, fp, fn) == (1, 1, 0)


def test_cada_deteccion_se_usa_una_sola_vez():
    """Dos anotaciones cercanas y una sola deteccion: un acierto y una perdida."""
    tp, fp, fn = emparejar([a(10.0), a(10.5)], [a(10.2)], tolerancia_s=2.0)
    assert (tp, fp, fn) == (1, 0, 1)


def test_se_empareja_con_la_deteccion_mas_cercana():
    tp, fp, fn = emparejar([a(10.0)], [a(11.9), a(10.05)], tolerancia_s=2.0)
    assert (tp, fp, fn) == (1, 1, 0)


def test_sin_anotaciones_todo_lo_detectado_es_falso_positivo():
    tp, fp, fn = emparejar([], [a(1.0), a(2.0)], tolerancia_s=2.0)
    assert (tp, fp, fn) == (0, 2, 0)


def test_sin_detecciones_todo_lo_anotado_se_perdio():
    tp, fp, fn = emparejar([a(1.0), a(2.0)], [], tolerancia_s=2.0)
    assert (tp, fp, fn) == (0, 0, 2)


def test_dos_listas_vacias_no_revientan():
    assert emparejar([], [], tolerancia_s=2.0) == (0, 0, 0)


# --------------------------------------------------------------------------
# Evaluacion por tipo
# --------------------------------------------------------------------------

def test_los_resultados_se_separan_por_tipo_de_evento():
    """No es lo mismo fallar en APPROACH que en PICK_UP."""
    anotados = [a(1.0, "APPROACH"), a(2.0, "PICK_UP"), a(3.0, "PICK_UP")]
    detectados = [a(1.1, "APPROACH"), a(2.1, "PICK_UP")]

    puntajes = evaluar(anotados, detectados, tolerancia_s=2.0)
    etiquetas = [p.etiqueta for p in puntajes]
    assert etiquetas == ["APPROACH", "PICK_UP", "TOTAL"]

    assert puntaje_de(puntajes, "APPROACH").recall == 1.0
    assert puntaje_de(puntajes, "PICK_UP").recall == pytest.approx(0.5)


def test_el_total_suma_todos_los_tipos():
    anotados = [a(1.0, "APPROACH"), a(2.0, "PICK_UP")]
    detectados = [a(1.1, "APPROACH"), a(2.1, "PICK_UP")]
    total = puntaje_de(evaluar(anotados, detectados, 2.0), "TOTAL")
    assert (total.tp, total.fp, total.fn) == (2, 0, 0)


def test_un_tipo_que_el_sistema_nunca_detecta_aparece_igual():
    """Si PUT_BACK se le escapa siempre, tiene que verse en la tabla, no desaparecer."""
    puntajes = evaluar([a(1.0, "PUT_BACK")], [], tolerancia_s=2.0)
    assert puntaje_de(puntajes, "PUT_BACK").recall == 0.0


def test_un_tipo_que_el_sistema_se_inventa_aparece_igual():
    puntajes = evaluar([], [a(1.0, "PICK_UP")], tolerancia_s=2.0)
    assert puntaje_de(puntajes, "PICK_UP").precision == 0.0


# --------------------------------------------------------------------------
# Lectura del CSV
# --------------------------------------------------------------------------

def csv_en(tmp_path, contenido: str):
    ruta = tmp_path / "gt.csv"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_se_lee_un_csv_bien_formado(tmp_path):
    ruta = csv_en(tmp_path, "video_id,timestamp,zone_id,event\n"
                            "video_001,12.5,gondola_A,PICK_UP\n")
    anotaciones = leer_groundtruth(ruta)
    assert len(anotaciones) == 1
    assert anotaciones[0] == Anotacion("video_001", 12.5, "gondola_A", "PICK_UP")


def test_el_ejemplo_del_repositorio_se_lee_sin_errores():
    """Si el ejemplo que le damos al equipo no se lee, mal empezamos."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[3]
    anotaciones = leer_groundtruth(raiz / "data" / "groundtruth" / "ejemplo.csv")
    assert len(anotaciones) >= 5
    assert {x.event for x in anotaciones} <= {"APPROACH", "PICK_UP", "PUT_BACK"}


def test_el_tipo_de_evento_se_normaliza_a_mayusculas(tmp_path):
    """Quien anota en una hoja de calculo escribe como puede."""
    ruta = csv_en(tmp_path, "video_id,timestamp,zone_id,event\n"
                            "video_001,1.0,gondola_A,pick_up\n")
    assert leer_groundtruth(ruta)[0].event == "PICK_UP"


def test_las_filas_en_blanco_se_ignoran(tmp_path):
    """Excel deja filas vacias al final constantemente."""
    ruta = csv_en(tmp_path, "video_id,timestamp,zone_id,event\n"
                            "video_001,1.0,gondola_A,PICK_UP\n"
                            ",,,\n\n")
    assert len(leer_groundtruth(ruta)) == 1


def test_un_csv_vacio_da_una_lista_vacia_y_no_un_error(tmp_path):
    ruta = csv_en(tmp_path, "video_id,timestamp,zone_id,event\n")
    assert leer_groundtruth(ruta) == []


def test_un_csv_sin_las_columnas_correctas_da_un_error_util(tmp_path):
    ruta = csv_en(tmp_path, "video,segundo,tipo\nvideo_001,1.0,PICK_UP\n")
    with pytest.raises(GondolaError) as error:
        leer_groundtruth(ruta)
    assert "timestamp" in str(error.value)


def test_un_timestamp_que_no_es_numero_dice_la_linea(tmp_path):
    """Quien anota trabaja en una hoja de calculo: necesita saber que fila corregir."""
    ruta = csv_en(tmp_path, "video_id,timestamp,zone_id,event\n"
                            "video_001,1.0,gondola_A,PICK_UP\n"
                            "video_001,mediodia,gondola_A,PICK_UP\n")
    with pytest.raises(GondolaError) as error:
        leer_groundtruth(ruta)
    assert "linea 3" in str(error.value)


def test_un_timestamp_negativo_se_rechaza(tmp_path):
    ruta = csv_en(tmp_path, "video_id,timestamp,zone_id,event\n"
                            "video_001,-5,gondola_A,PICK_UP\n")
    with pytest.raises(GondolaError):
        leer_groundtruth(ruta)


def test_un_archivo_que_no_existe_dice_como_crearlo(tmp_path):
    with pytest.raises(GondolaError) as error:
        leer_groundtruth(tmp_path / "no_existe.csv")
    assert "ejemplo.csv" in str(error.value)


# --------------------------------------------------------------------------
# Sin ground truth no se afirma nada
# --------------------------------------------------------------------------

def test_eval_sin_anotaciones_no_inventa_cifras(tmp_path, monkeypatch, capsys):
    """El resultado debe ser un aviso claro, nunca una tabla con numeros."""
    from gondola.cli import EXIT_FALTA_REQUISITO, main

    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("GROUNDTRUTH_DIR", str(tmp_path / "gt"))

    assert main(["eval"]) == EXIT_FALTA_REQUISITO
    salida = capsys.readouterr().out
    assert "SIN ANOTACIONES NO SE PUEDE AFIRMAR NADA" in salida
    assert "precision" not in salida.lower()
