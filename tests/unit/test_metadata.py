"""ObjectMetadata e combine_metadata (Fase 1.1) — porte de ``ObjectMetadata.java``."""

import pytest

from uschema.intermediate.metadata import ObjectMetadata

pytestmark = pytest.mark.unit


def test_construtor_default_zera_tudo() -> None:
    # ObjectMetadata.java:10-12 — é o que o infer usa para todo objeto não-raiz
    # (SchemaInference.java:198), e por isso as entidades internas nascem em 0.
    meta = ObjectMetadata()
    assert (meta.count, meta.first_timestamp, meta.last_timestamp) == (0, 0, 0)


def test_combina_soma_contagem_e_abre_a_janela() -> None:
    meta = ObjectMetadata(count=5, first_timestamp=100, last_timestamp=200)
    meta.combine_metadata(ObjectMetadata(count=3, first_timestamp=50, last_timestamp=300))
    assert (meta.count, meta.first_timestamp, meta.last_timestamp) == (8, 50, 300)


def test_combina_nao_muta_o_argumento() -> None:
    meta = ObjectMetadata(count=5, first_timestamp=100, last_timestamp=200)
    orig = ObjectMetadata(count=3, first_timestamp=50, last_timestamp=300)
    meta.combine_metadata(orig)
    assert (orig.count, orig.first_timestamp, orig.last_timestamp) == (3, 50, 300)


def test_janela_nao_encolhe_com_valores_internos() -> None:
    meta = ObjectMetadata(count=1, first_timestamp=100, last_timestamp=300)
    meta.combine_metadata(ObjectMetadata(count=1, first_timestamp=150, last_timestamp=200))
    assert (meta.first_timestamp, meta.last_timestamp) == (100, 300)


def test_zero_a_esquerda_e_sentinela_de_nao_sei() -> None:
    # ObjectMetadata.java:55,58 — o `x == 0 ||` adota o valor do orig.
    meta = ObjectMetadata()
    meta.combine_metadata(ObjectMetadata(count=4, first_timestamp=100, last_timestamp=200))
    assert (meta.count, meta.first_timestamp, meta.last_timestamp) == (4, 100, 200)


def test_zero_a_direita_sobrescreve_o_first_timestamp() -> None:
    """Defeito **M1**, replicado de propósito (``ObjectMetadata.java:55``).

    A sentinela ``0`` só é reconhecida do lado esquerdo. Com um
    ``first_timestamp`` real e um ``orig`` zerado, a condição
    ``0 < first_timestamp`` é verdadeira e o valor real é **perdido**. Dispara
    no caminho do bug #6: documento sem ``ObjectId`` chega com timestamp 0 e
    contamina a janela de quem tem.
    """
    meta = ObjectMetadata(count=5, first_timestamp=100, last_timestamp=200)
    meta.combine_metadata(ObjectMetadata(count=1, first_timestamp=0, last_timestamp=0))
    assert meta.first_timestamp == 0, "se virar 100, o defeito M1 foi 'corrigido'"


def test_zero_a_direita_nao_afeta_o_last_timestamp() -> None:
    """A outra metade do M1: ``last_timestamp`` é imune, porque ``0 > x`` é falso."""
    meta = ObjectMetadata(count=5, first_timestamp=100, last_timestamp=200)
    meta.combine_metadata(ObjectMetadata(count=1, first_timestamp=0, last_timestamp=0))
    assert meta.last_timestamp == 200


def test_combina_em_cadeia() -> None:
    meta = ObjectMetadata()
    for ts in (300, 100, 200):
        meta.combine_metadata(ObjectMetadata(count=1, first_timestamp=ts, last_timestamp=ts))
    assert (meta.count, meta.first_timestamp, meta.last_timestamp) == (3, 100, 300)
