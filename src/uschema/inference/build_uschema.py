"""``BuildUSchema`` — a fachada do pipeline doc2uschema (Fase 1.7).

Porte da costura que o Guice fazia: instancia as estratégias e injeta por
construtor, expondo um ponto de entrada único. A orquestração real é uma linha
(``JSON2Schema.fromJSONArray:97``)::

    builder.build(factory, schemaName, si.infer(rows))

— ``infer`` (Fase 1.2) produz as árvores raw, ``build`` (Fase 1.4) as converte
em ``USchema``. Esta fachada só amarra as duas.

Qual wiring? O do gerador dos XMIs-oráculo (``MongoDB2USchemaMain``)
-------------------------------------------------------------------
Há **dois** entry-points no Java com wiring diferente, e a escolha importa para
a fidelidade:

- ``DefaultBuildUSchema`` (``doc2uschema/main``, usado pelos JUnit) — liga o
  **``NullStructuralVariationSorter``** (``configure:68``): não ordena.
- ``MongoDB2USchemaMain`` (``mongodb2uschema/main``, **o que o oráculo roda para
  gerar os XMIs** — ``oracle/entrypoint.sh``) — liga o
  **``DefaultStructuralVariationSorter``** (``configure``).

Como os XMIs de referência (``model_*.xmi``) vêm do ``MongoDB2USchemaMain``, esta
fachada mirra **esse** wiring: sorter **``Default``**, que já é o default do
:class:`~uschema.inference.builder.USchemaModelBuilder` — daí não haver override.

.. note::
   O sorter, na prática, **não altera o resultado do golden-master**: o harness
   da 0.3 casa variações por **estrutura**, não por posição
   (``_compare_schema_type_variations``, bag matching), e ignora ``variationId``.
   Null vs Default muda só a ordem/numeração, invisíveis ao ``compare``. A
   escolha do Default é por fidelidade ao gerador, não por necessidade.

Resto do wiring, tudo ``Default`` (implícito nos defaults do builder e do
``SchemaInference``): ``FeatureAnalyzer``→``set_optional_properties``,
``ReferenceMatcherCreator``→``create_reference_matcher``,
``OptionalTagger`` (código morto), ``AliasedAggregatedEntityJoiner``→
``join_aggregated_entities``, ``EVariationMerger``→``merge_equivalent_evs``,
``SchemaInferenceConfig`` default (``_type`` ignorado + marcador).
"""

from __future__ import annotations

from pathlib import Path

from pyecore.ecore import EObject, EPackage

from uschema.extractors.triple import SchemaTriple
from uschema.inference.builder import USchemaModelBuilder
from uschema.inference.schema_inference import SchemaInference
from uschema.metamodel.xmi import save_model

__all__ = ["BuildUSchema"]


class BuildUSchema:
    """Pipeline doc2uschema ponta a ponta: triplas → ``USchema``.

    Parameters
    ----------
    pkg : EPackage
        Metamodelo carregado (:func:`~uschema.metamodel.registry.load_metamodel`).

    Notes
    -----
    Cada :meth:`build_from_rows` cria instâncias **novas** de
    :class:`~uschema.inference.schema_inference.SchemaInference` e
    :class:`~uschema.inference.builder.USchemaModelBuilder` — as duas carregam
    estado mutável por execução (``_raw_entities``, ``_m_structural_variations``)
    que não é resetado entre chamadas. É o equivalente à instância nova que o
    Guice injetava por build.
    """

    def __init__(self, pkg: EPackage) -> None:
        self._pkg = pkg

    def build_from_rows(self, name: str, triples: list[SchemaTriple]) -> EObject:
        """Construir o ``USchema`` a partir das triplas (a costura completa).

        Porte de ``JSON2Schema.fromJSONArray`` (``:97``) com o wiring de
        ``DefaultBuildUSchema``.

        Parameters
        ----------
        name : str
            Nome do ``USchema`` resultante.
        triples : list of SchemaTriple
            Saída dos extratores (Fase 2), no contrato compartilhado.

        Returns
        -------
        EObject
            O ``USchema`` inferido e construído.
        """
        inference = SchemaInference()
        raw_entities = inference.infer(triples)

        # Wiring do `MongoDB2USchemaMain` (o gerador dos XMIs-oráculo): tudo
        # `Default`, que já são os defaults do builder — sorter `Default`
        # inclusive. Ver a docstring do módulo sobre por que não é o `Null`.
        builder = USchemaModelBuilder(self._pkg)
        return builder.build(name, raw_entities)

    def build_and_write(self, name: str, triples: list[SchemaTriple], xmi_path: Path) -> EObject:
        """:meth:`build_from_rows` + serializar o ``USchema`` para XMI.

        Porte de ``BuildUSchema.writeToFile`` (``:74-77``).

        Parameters
        ----------
        name : str
            Nome do ``USchema``.
        triples : list of SchemaTriple
            As triplas de entrada.
        xmi_path : Path
            Onde gravar o XMI.

        Returns
        -------
        EObject
            O ``USchema`` construído (também gravado em ``xmi_path``).
        """
        schema = self.build_from_rows(name, triples)
        save_model(schema, xmi_path)
        return schema
