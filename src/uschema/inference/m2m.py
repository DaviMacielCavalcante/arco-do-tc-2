"""``USchemaToDocumentDb.adaptToDocumentDb`` — transformação m2m (Fase 1.4b).

Porte de ``doc2uschema/m2m/USchemaToDocumentDb.java``. Roda **depois** do
``USchemaModelBuilder``, sobre um ``USchema`` já construído, e o adapta ao
paradigma **documento** (MongoDB) em duas passadas:

1. ``relTypeToEntityType`` — todo ``RelationshipType`` vira um ``EntityType`` com
   prefixo ``Ref_``; as ``Reference`` que apontavam para variações do
   relacionamento passam a apontar para o novo ``EntityType``.
2. ``removePMap`` — todo ``Attribute`` de tipo ``PMap`` é extraído para uma
   entidade ``Map_<Attr>`` com uma variação ``{key, value}`` e um ``Aggregate``
   no lugar do mapa (bancos de documento não têm ``Map`` nativo, mas têm
   documentos embutidos). Recursivo em ``PMap`` de ``PMap``.

.. warning::
   Citações ``:linha`` do **commit pinado** ``0f8f58c`` (``oracle/Dockerfile``),
   via ``git show`` — não do arquivo em disco.

Reúsos e limites de plataforma (registrar, não reimplementar)
-------------------------------------------------------------
- **``CompareStructuralVariation``** (``:80,168,194``) já está portado como
  ``compare_variation`` na Fase 0.3 (``validation/equivalence.py:609``) — mesma
  relação que o ``FeatureAnalyzer`` tem com ``compare_feature``. Não reimplementar.
- **``EcoreUtil.copy(attr)``** (``:104``) **não tem equivalente pronto no
  PyEcore**: ``EcoreUtils.copy`` não existe e ``copy.deepcopy`` estoura
  ``BadValueError``. Resolvido em :meth:`_deep_copy`, que reconstrói a cópia
  **genericamente** percorrendo as ``eAllStructuralFeatures()`` do metamodelo —
  sem ramo por tipo, e cobrindo composto aninhado como o original faz.
- **Fronteira mypy/PyEcore**: ``EObject`` é ``Any``; checagem de tipo por
  ``eClass.name``, nunca ``isinstance`` (aviso do CLAUDE.md). Todo campo tocado
  precisa ser exercitado por teste ao menos uma vez.
"""

from __future__ import annotations

from itertools import chain

from pyecore.ecore import EObject, EPackage, EReference

from uschema.naming.inflector import get_instance as get_inflector
from uschema.validation.equivalence import compare_variation

__all__ = ["USchemaToDocumentDb"]

#: `USchemaToDocumentDb.java:29-30`.
_REF_ENTITY_PREFIX = "Ref_"
_PMAP_ENTITY_PREFIX = "Map_"


class USchemaToDocumentDb:
    """Adapta um ``USchema`` construído ao paradigma documento (MongoDB).

    Parameters
    ----------
    pkg : EPackage
        Metamodelo carregado (:func:`~uschema.metamodel.registry.load_metamodel`),
        no papel da ``USchemaFactory`` — ``pkg.getEClassifier(...)()`` cria a
        instância, como no :class:`~uschema.inference.builder.USchemaModelBuilder`.
    """

    def __init__(self, pkg: EPackage) -> None:
        self._pkg = pkg

    def _create(self, class_name: str) -> EObject:
        """Instanciar uma EClass do metamodelo pelo nome (papel da factory)."""
        eclass: EObject = self._pkg.getEClassifier(class_name)
        instance: EObject = eclass()
        return instance

    def adapt_to_document_db(self, schema: EObject) -> None:
        """Adaptar ``schema`` in-place: `RelationshipType`→`EntityType` e remove `PMap`.

        Porte de ``adaptToDocumentDb`` (``:49-69``).

        Parameters
        ----------
        schema : EObject
            O ``USchema`` a adaptar. Mutado no lugar.
        """
        rel_types = []
        map_attributes = []

        for schema_type in chain(schema.entities, schema.relationships):
            if schema_type.eClass.name == "RelationshipType":
                rel_types.append(schema_type)

            for var in schema_type.variations:
                for feat in var.features:
                    if feat.eClass.name == "Attribute" and feat.type.eClass.name == "PMap":
                        map_attributes.append(feat)

        for rel_type in rel_types:
            self._rel_type_to_entity_type(schema, rel_type)

        for attr in map_attributes:
            self._remove_pmap(schema, attr)

    def _rel_type_to_entity_type(self, schema: EObject, rel_type: EObject) -> None:
        """Traduzir um ``RelationshipType`` em ``EntityType`` com prefixo ``Ref_``.

        Porte de ``relTypeToEntityType`` (``:78-155``). As ``Reference`` que
        apontavam para variações do relacionamento passam a apontar para o novo
        ``EntityType``, e as variações featured recebem os atributos do
        relacionamento embutidos.

        Parameters
        ----------
        schema : EObject
            O ``USchema`` sendo processado.
        rel_type : EObject
            O ``RelationshipType`` a converter.
        """
        capitalized = get_inflector().capitalize(rel_type.name)

        assert capitalized is not None

        entity_name = "Ref_" + capitalized

        l_references = []

        for entity in chain(schema.entities, schema.relationships):
            for var in entity.variations:
                for feat in var.features:
                    if feat.eClass.name != "Reference":
                        continue
                    if any(v in rel_type.variations for v in feat.isFeaturedBy):
                        l_references.append(feat)

        for ref in l_references:
            for var in ref.isFeaturedBy:
                new_ref = self._create("Reference")
                new_ref.name = ref.name
                new_ref.lowerBound = ref.lowerBound
                new_ref.upperBound = ref.upperBound
                new_ref.refsTo = ref.refsTo
                new_ref.opposite = ref.opposite

                var.features.append(new_ref)
                var.logicalFeatures.append(new_ref)

                for attr in ref.attributes:
                    new_attr = self._deep_copy(attr)

                    var.features.append(new_attr)
                    var.structuralFeatures.append(new_attr)

                    new_ref.attributes.append(attr)

                if not any(f.name == "_id" for f in var.features):
                    attribute = self._create("Attribute")
                    attribute.name = "_id"
                    primitive_type = self._create("PrimitiveType")
                    primitive_type.name = "ObjectId"

                    attribute.type = primitive_type

                    var.features.append(attribute)

            ref.lowerBound = 1
            ref.upperBound = 1
            ref.isFeaturedBy.clear()

        ref_entity = next((v for v in schema.entities if v.name == entity_name), None)

        if ref_entity is None:
            ref_entity = self._create("EntityType")
            ref_entity.name = entity_name
            ref_entity.root = False
            ref_entity.parents.extend(rel_type.parents)

            schema.entities.append(ref_entity)

        for ref in l_references:
            ref.refsTo = ref_entity

        vaz_size = len(ref_entity.variations)

        if vaz_size == 0:
            ref_entity.variations = rel_type.variations.copy()
        else:
            vars_to_move = []

            for var in rel_type.variations:
                if any(compare_variation(inner, var) for inner in ref_entity.variations):
                    continue

                vaz_size += 1

                var.variationId = vaz_size

                vars_to_move.append(var)

            ref_entity.variations.extend(vars_to_move)

        schema.relationships.remove(rel_type)

    def _remove_pmap(self, schema: EObject, attr: EObject) -> None:
        """Extrair um ``Attribute`` de tipo ``PMap`` para uma entidade ``Map_<Attr>``.

        Porte de ``removePMap`` (``:166-220``). Substitui o mapa por um
        ``Aggregate`` que aponta para uma variação ``{key, value}``. Recursivo
        para ``PMap`` de ``PMap``.

        Parameters
        ----------
        schema : EObject
            O ``USchema`` sendo processado.
        attr : EObject
            O ``Attribute`` cujo ``type`` é um ``PMap``.
        """
        capitalized = get_inflector().capitalize(attr.name)

        assert capitalized is not None

        entity_name = "Map_" + capitalized

        attr_map = attr.type

        map_entity = next((e for e in schema.entities if e.name == entity_name), None)

        if map_entity is None:
            map_entity = self._create("EntityType")
            map_entity.name = entity_name
            map_entity.root = False
            schema.entities.append(map_entity)

        key = self._create("Attribute")
        key.name = "key"
        key.type = attr_map.keyType

        value = self._create("Attribute")
        value.name = "value"
        value.type = attr_map.valueType

        compare_var = self._create("StructuralVariation")
        compare_var.variationId = 1

        compare_var.features.append(key)
        compare_var.features.append(value)

        var = next(
            (v for v in map_entity.variations if compare_variation(compare_var, v)), compare_var
        )

        if var is compare_var:
            var.variationId = len(map_entity.variations) + 1

            map_entity.variations.append(var)

        agg = self._create("Aggregate")
        agg.name = attr.name
        agg.lowerBound = 1
        agg.upperBound = 1
        agg.aggregates = [var]
        agg.optional = attr.optional

        container = attr.eContainer()
        container.features.append(agg)
        container.features.remove(attr)

        # Recursão sobre o `value` LOCAL (não o da variação reutilizada) — fiel
        # ao Java (`:218-219`, `if (value.getType() instanceof PMap)
        # removePMap(schema, value)`). Recursar sobre a variação reutilizada
        # divergiria do original. Além disso não se manifesta: na 1ª ocorrência
        # de um `PMap` aninhado a recursão troca este `value` por um `Aggregate`,
        # então nenhuma `compare_var` futura (com `value` ainda `Attribute`)
        # casa com a variação já existente — a reutilização não ocorre neste
        # caminho.
        if value.type.eClass.name == "PMap":
            self._remove_pmap(schema, value)

    def _deep_copy(self, obj: EObject) -> EObject:
        """Copiar um ``EObject`` em profundidade (equivalente de ``EcoreUtil.copy``).

        Substitui o ``EcoreUtil.copy(attr)`` do original (``:104``), que o
        PyEcore não expõe pronto: ``EcoreUtils.copy`` não existe e
        ``copy.deepcopy`` estoura ``BadValueError``.

        A cópia é **genérica**: percorre as ``eAllStructuralFeatures()`` do
        próprio metamodelo, em vez de conhecer cada tipo. Serve para qualquer
        ``EObject`` do U-Schema — ``Attribute`` de ``PrimitiveType``, mas também
        de ``PList``/``PSet``/``PMap``/``PTuple``, com aninhamento arbitrário.

        Parameters
        ----------
        obj : EObject
            O objeto a copiar.

        Returns
        -------
        EObject
            Cópia nova e independente, **sem container** (pronta para anexar em
            outra variação). O original não é tocado.

        Notes
        -----
        Três regras, derivadas do metamodelo:

        1. ``EAttribute`` (``name``, ``optional``, …) — copia o valor.
        2. ``EReference`` **de containment** (``type``, ``elementType``,
           ``keyType``/``valueType``, ``elements``) — copia **recursivamente**;
           é o que torna o helper genérico, sem ramo por tipo.
        3. ``EReference`` **não-containment** (``key``, ``references``) —
           **pulada**. Não é omissão: essas features têm ``eOpposite``, então
           atribuí-las na cópia **muta o objeto original** — setar
           ``copia.key = orig.key`` insere a cópia em ``Key.attributes`` do
           ``Key`` original (verificado: a lista vai de 1 para 2 elementos). O
           ``EcoreUtil.copy`` do Java evita o mesmo problema com um ``Copier``,
           que remapeia referências internas à árvore copiada e deixa as
           externas de fora.

        ``isinstance`` aqui é legítimo, apesar do aviso do CLAUDE.md: ``feature``
        é objeto do **metamodelo Ecore** (``EReference``/``EAttribute`` são
        classes concretas e importáveis do PyEcore), não um ``EObject`` de
        domínio — a regra do ``eClass.name`` vale para o modelo, não para a
        metacamada.

        A classe concreta sai de ``obj.eClass()``: instanciar a EClass do próprio
        objeto evita o problema de ``DataType`` ser **abstrata** (criá-la pelo
        nome levantaria ``TypeError``).
        """
        copy = obj.eClass()

        for feature in obj.eClass.eAllStructuralFeatures():
            is_reference = isinstance(feature, EReference)

            # Regra 3 — ver Notes: religar ref cruzada mutaria o original.
            if is_reference and not feature.containment:
                continue

            value = obj.eGet(feature)

            if feature.many:
                target = copy.eGet(feature)
                for item in value:
                    target.append(self._deep_copy(item) if is_reference else item)
            elif value is not None:
                copy.eSet(feature, self._deep_copy(value) if is_reference else value)

        return copy
