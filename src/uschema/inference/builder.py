"""``USchemaModelBuilder.build`` + ``fillEV`` — árvores raw → EMF (Fase 1.4).

Porte de ``USchemaModelBuilder.java``. É a **fase 2 do pipeline interno**:
consome o ``rawEntities`` que a :class:`~uschema.inference.schema_inference.SchemaInference`
produziu (mapa entidade → variações :class:`~uschema.intermediate.raw.ObjectSC`)
e devolve o modelo U-Schema em ``EObject`` do PyEcore, pronto pro XMI da
Fase 0.2.

.. warning::
   Toda citação ``:linha`` deste módulo é do **commit pinado** ``0f8f58c``
   (``oracle/Dockerfile``), obtida por ``git show``. O arquivo em disco do
   clone ``~/Documents/GitHub/uschema-inference`` está com o patch ``0007``
   aplicado na *working tree* e tem numeração diferente da ``:249`` em diante —
   ler o disco direto engana justamente no trecho do bug #7.

A ordem dos passos está verificada em ``USchemaModelBuilder.java:89-148`` —
**não reordenar**:

1. criar ``USchema`` e, por entidade, ``EntityType`` (``root`` se **alguma**
   variação for raiz, ``:105``);
2. por variação, ``StructuralVariation`` com ``variationId`` a partir de 1,
   ``count`` e timestamps (``:117-121``), registrando nos índices reversos e
   no ``optTagger`` (``:124-127``);
3. ``createReferenceMatcher`` sobre as entidades já criadas (``:137``);
4. ``fillEV`` por variação (``:140-141``);
5. por entidade, ``sort`` das variações + ``setOptionalProperties``
   (``:144-148``).

Notas de fidelidade
-------------------
**Bug #7 — array vazio.** O Java materializa ``inner = sc.getInners().get(0)``
na ``:255``, **antes** do guarda ``sc.size() == 0`` da ``:256`` — o ``||``
faria short-circuit, mas a variável já foi avaliada, então um array vazio
estoura com ``IndexOutOfBoundsException``. É o patch ``0007`` do oráculo; aqui
é corrigido **por construção**: não materializar ``inners[0]`` antes do guarda.
O próprio autor já suspeitava (comentário na ``:256``: *"si sc.size() == 0
entonces el inner de antes excepciona"*).

**``opposite`` nunca é setado.** O cálculo inteiro está comentado no original
(``:150-172``, "no easy way to infer these"). Não preencher: o harness da 0.3
compara ``opposite`` e um porte que o preenchesse divergiria de propósito.

**``optTagger`` é código morto.** Só ``put()`` roda (``:127``);
``calcOptionality()`` (``:134``) e ``isOptional()`` (``:187``) estão
comentados no original ("TODO: Remove until recode"). Portado por "fiel e
completo" — chamar ``put`` e nada mais.

**Fronteira mypy.** Todo acesso a campo de ``EObject`` neste módulo é ``Any``
(PyEcore não distribui ``py.typed``) — ver o aviso no CLAUDE.md. Cada campo
tocado aqui precisa ser exercitado por teste ao menos uma vez, inclusive nos
caminhos de erro.
"""

from __future__ import annotations

from collections.abc import Callable

from pyecore.ecore import EObject, EPackage

from uschema.inference.strategies import (
    OptionalTagger,
    ReferenceMatcher,
    create_reference_matcher,
    set_optional_properties,
    sort_structural_variations,
)
from uschema.intermediate.raw import (
    ArraySC,
    BooleanSC,
    NullSC,
    NumberSC,
    ObjectIdSC,
    ObjectSC,
    SchemaComponent,
    StringSC,
)
from uschema.naming.inflector import get_instance as get_inflector

__all__ = ["USchemaModelBuilder"]

#: Wiring que o Guice fazia (``USchemaModelBuilder.java:52-65``). Em Python é
#: injeção por construtor — o original já tem o construtor de 4 argumentos
#: (``:74``) além do ``@Inject``.
_Sorter = Callable[[list[EObject]], None]
_Analyzer = Callable[[list[EObject]], None]
_MatcherCreator = Callable[[list[EObject]], ReferenceMatcher]


def _primitive_type_name(sc: SchemaComponent) -> str:
    """Nome do ``PrimitiveType`` correspondente a uma folha raw.

    Porte de ``primitiveTypeFromSchemaComponent`` (``:344-362``).

    Parameters
    ----------
    sc : SchemaComponent
        Folha da árvore raw.

    Returns
    -------
    str
        ``"Boolean"``, ``"Number"``, ``"String"``, ``"ObjectId"``, ``"Null"``
        ou ``""`` (o fallback do original, ``:361`` — não levantar exceção).
    """
    if isinstance(sc, BooleanSC):
        name = "Boolean"
    elif isinstance(sc, NumberSC):
        name = "Number"
    elif isinstance(sc, StringSC):
        name = "String"
    elif isinstance(sc, ObjectIdSC):
        name = "ObjectId"
    elif isinstance(sc, NullSC):
        name = "Null"
    else:
        name = ""

    return name


class USchemaModelBuilder:
    """Constrói o modelo U-Schema (PyEcore) a partir das árvores raw.

    Parameters
    ----------
    pkg : EPackage
        Metamodelo carregado (:func:`~uschema.metamodel.registry.load_metamodel`).
        Faz o papel da ``USchemaFactory`` do EMF: na API reflexiva do PyEcore
        ``pkg.getEClassifier("Aggregate")()`` **é** a criação da instância.
    rm_creator : callable, optional
        Cria o ``ReferenceMatcher`` a partir das entidades (Fase 1.3b).
    var_sorter : callable, optional
        Ordena as variações de uma entidade (Fase 1.3b).
    opt_tagger : OptionalTagger, optional
        Bookkeeping de opcionalidade — código morto no pipeline, ver o módulo.
    analyzer : callable, optional
        Marca as features opcionais (Fase 1.3b).

    Notes
    -----
    ``_m_structural_variations`` é um dict com **chave de hash estrutural**
    (``:124,245,280`` — ``ObjectSC``/``ArraySC`` como chave). Duas variações
    estruturalmente iguais colidem e o ``Aggregate`` apontaria para a errada;
    quem garante unicidade é o merge de 1.2/1.3a, rodado **antes** daqui.
    """

    def __init__(
        self,
        pkg: EPackage,
        *,
        rm_creator: _MatcherCreator = create_reference_matcher,
        var_sorter: _Sorter = sort_structural_variations,
        opt_tagger: OptionalTagger | None = None,
        analyzer: _Analyzer = set_optional_properties,
    ) -> None:
        self._pkg = pkg
        self._rm_creator = rm_creator
        self._var_sorter = var_sorter
        self._opt_tagger = opt_tagger if opt_tagger is not None else OptionalTagger()
        self._analyzer = analyzer

        # `_init()` (`:83-87`) — os dois índices reversos.
        self._m_structural_variations: dict[SchemaComponent, EObject] = {}
        self._variations_per_entity: dict[str, list[tuple[SchemaComponent, EObject]]] = {}
        self._ref_matcher: ReferenceMatcher | None = None

    def _create(self, class_name: str) -> EObject:
        """Instanciar uma EClass do metamodelo pelo nome (papel da factory).

        Parameters
        ----------
        class_name : str
            Nome da EClass (``"USchema"``, ``"EntityType"``, ``"Aggregate"``…).

        Returns
        -------
        EObject
            Instância vazia.
        """
        eclass: EObject = self._pkg.getEClassifier(class_name)
        instance: EObject = eclass()
        return instance

    def build(self, name: str, raw_entities: dict[str, list[SchemaComponent]]) -> EObject:
        """Construir o ``USchema`` completo.

        Porte de ``build`` (``:89-174``).

        Parameters
        ----------
        name : str
            Nome do ``USchema`` resultante.
        raw_entities : dict of str to list of SchemaComponent
            Saída da :class:`~uschema.inference.schema_inference.SchemaInference`.

        Returns
        -------
        EObject
            O ``USchema`` com entidades, variações e features preenchidas.
        """
        uschema = self._create("USchema")
        uschema.name = name

        for entity_name, raw_variations in raw_entities.items():
            entity = self._create("EntityType")

            entity.name = entity_name

            entity.root = any(isinstance(v, ObjectSC) and v.is_root for v in raw_variations)

            uschema.entities.append(entity)

            pairs: list[tuple[SchemaComponent, EObject]] = []

            for i, variation in enumerate(raw_variations):
                assert isinstance(variation, ObjectSC)
                # `meta` é `ObjectMetadata | None` na classe, mas a 1.2 sempre
                # o atribui no `infer` — nunca chega None aqui. Prova nossa, não
                # infidelidade: o Java não tem o problema porque o campo não é
                # Optional (ver nota da 1.3 no todolist).
                assert variation.meta is not None

                structural_variation = self._create("StructuralVariation")

                structural_variation.variationId = i + 1

                structural_variation.count = variation.meta.count

                structural_variation.firstTimestamp = variation.meta.first_timestamp

                structural_variation.lastTimestamp = variation.meta.last_timestamp

                entity.variations.append(structural_variation)

                self._m_structural_variations[variation] = structural_variation

                pairs.append((variation, structural_variation))

                self._opt_tagger.put(entity_name, variation)

            self._variations_per_entity[entity_name] = pairs

        self._ref_matcher = self._rm_creator(uschema.entities)

        for entity_name, pairs in self._variations_per_entity.items():
            for variation, ev in pairs:
                self._fill_ev(entity_name, variation, ev)

        for entity in uschema.entities:
            # `entity.variations` é um `EOrderedSet` do PyEcore, sem `.sort()`;
            # o `var_sorter` (1.3b) ordena `list` in-place e renumera
            # `variationId` pela posição. O Java usa `ECollections.sort`, que
            # ordena a coleção EMF no lugar — então a ordem tem de voltar pra
            # coleção, não só o `variationId`: o XMI compara a ordem das
            # variações. Snapshot → sort → reescreve a ordem.
            ordered = list(entity.variations)
            self._var_sorter(ordered)
            entity.variations.clear()
            entity.variations.extend(ordered)

            self._analyzer(ordered)

        return uschema

    def _fill_ev(self, ev_name: str, schema: SchemaComponent, ev: EObject) -> None:
        """Preencher uma ``StructuralVariation`` com suas features.

        Porte de ``fillEV`` (``:176-213``). O ``reduce`` do original é só um
        laço sobre ``inners`` — o acumulador (``ev2``) nunca muda, e o
        combinador ``(e,e2) -> e`` da ``:212`` nunca roda (stream sequencial).

        Parameters
        ----------
        ev_name : str
            Nome da entidade dona da variação. Só o ``optTagger`` o usaria, e
            ele é código morto (``:187``) — o parâmetro fica por fidelidade de
            assinatura.
        schema : SchemaComponent
            A variação em forma raw; o original assume ``ObjectSC`` (``:178``,
            um `assert`).
        ev : EObject
            A ``StructuralVariation`` a preencher, mutada no lugar.
        """
        assert isinstance(schema, ObjectSC)

        for field, sc in schema.inners:
            feature = self._structural_feature(field, sc)

            assert feature is not None

            ev.features.append(feature)

            ev.structuralFeatures.append(feature)

            if feature.eClass.name == "Attribute":
                singularized = get_inflector().singularize(field)

                assert singularized is not None

                reference = self._maybe_reference(singularized, feature)

                if reference is not None:
                    ev.features.append(reference)
                    ev.logicalFeatures.append(reference)

                if feature.name == "_id":
                    key = self._create("Key")

                    feature.key = key

                    ev.features.append(key)

                    ev.logicalFeatures.append(key)

    def _structural_feature(self, name: str, sc: SchemaComponent) -> EObject | None:
        """Despachar a criação da feature pelo tipo do componente raw.

        Porte de ``structuralFeatureFromSchemaComponent`` (``:215-228``), onde
        a sobrecarga de método do Java vira despacho por ``isinstance`` — o
        original também usa ``instanceof`` (``:217,220,223-224``).

        Parameters
        ----------
        name : str
            Nome do campo.
        sc : SchemaComponent
            Valor do campo, em forma raw.

        Returns
        -------
        EObject or None
            ``Aggregate`` (objeto/array de objetos) ou ``Attribute``
            (escalar/array de escalares). ``None`` no fallback do original
            (``:227``).
        """
        if isinstance(sc, ObjectSC):
            return self._feature_from_object(sc=sc, name=name)

        if isinstance(sc, ArraySC):
            return self._feature_from_array(sc=sc, name=name)

        if isinstance(sc, BooleanSC | NumberSC | NullSC | StringSC | ObjectIdSC):
            type_name = _primitive_type_name(sc)

            return self._feature_from_primitive(name, type_name)

        return None

    def _feature_from_object(self, name: str, sc: ObjectSC) -> EObject:
        """Objeto aninhado → ``Aggregate`` de multiplicidade 1..1.

        Porte de ``structuralFeatureFromSchemaComponent(String, ObjectSC)``
        (``:235-247``). Não precisa recursão: a 1.2 já promoveu todo objeto
        interno ao nível raiz (comentário do autor, ``:239-240``).

        Parameters
        ----------
        name : str
            Nome do campo.
        sc : ObjectSC
            O objeto aninhado.

        Returns
        -------
        EObject
            ``Aggregate`` apontando para a ``StructuralVariation`` de ``sc``.
        """
        aggregate = self._create("Aggregate")

        aggregate.name = name

        aggregate.lowerBound = 1

        aggregate.upperBound = 1

        # Indexação direta, não `.get()`: o Java (`:245`) anexa `null` em
        # silêncio quando a chave falta, mas o PyEcore não aceita None numa
        # EReference (`AttributeError` sobre `_inverse_rels`). Já que estourar
        # é inevitável, o `KeyError` ao menos aponta a chave ausente.
        variation = self._m_structural_variations[sc]

        aggregate.aggregates.append(variation)

        return aggregate

    def _feature_from_array(self, name: str, sc: ArraySC) -> EObject:
        """Array → ``Aggregate`` (de objetos) ou ``Attribute`` de ``PList``/``PTuple``.

        Porte de ``structuralFeatureFromSchemaComponent(String, ArraySC)``
        (``:249-305``).

        Parameters
        ----------
        name : str
            Nome do campo.
        sc : ArraySC
            O array em forma raw.

        Returns
        -------
        EObject
            ``Aggregate`` (0..*) se os elementos são objetos, senão
            ``Attribute`` tipado por ``PList``/``PTuple``.

        Notes
        -----
        **Bug #7** — no ramo homogêneo, o guarda ``size() == 0`` tem de vir
        **antes** de qualquer acesso a ``inners[0]``. O original materializa o
        ``inner`` na ``:255`` e só testa na ``:256``; aqui a ordem correta é
        por construção.
        """
        if sc.homogeneous:
            if sc.size() == 0 or not isinstance(sc.inners[0], ObjectSC):
                attribute = self._create("Attribute")

                attribute.name = name

                attribute.type = self._plist_or_ptuple_for_array(sc)

                return attribute
            else:
                aggregate = self._create("Aggregate")

                aggregate.name = name

                aggregate.lowerBound = 0

                aggregate.upperBound = -1

                variation = self._m_structural_variations[sc.inners[0]]

                aggregate.aggregates.append(variation)

                return aggregate
        else:
            # `.get()` e não indexação: aqui a ausência da chave é a resposta
            # ("os elementos não são objetos"), não um erro — é o `ev != null`
            # da `:281`.
            variation = self._m_structural_variations.get(sc.inners[0])

            if variation is not None:
                aggregate = self._create("Aggregate")

                aggregate.name = name

                aggregate.lowerBound = 0

                aggregate.upperBound = -1

                for inner in sc.inners:
                    aggregate.aggregates.append(self._m_structural_variations[inner])

                return aggregate
            else:
                attribute = self._create("Attribute")

                attribute.name = name

                attribute.type = self._plist_or_ptuple_for_array(sc)

                return attribute

    def _feature_from_primitive(self, name: str, primitive_name: str) -> EObject:
        """Folha → ``Attribute`` tipado por ``PrimitiveType``.

        Porte de ``structuralFeatureFromPrimitive`` (``:388-396``).

        Parameters
        ----------
        name : str
            Nome do campo.
        primitive_name : str
            Nome do tipo primitivo (ver :func:`_primitive_type_name`).

        Returns
        -------
        EObject
            ``Attribute`` com ``type`` sendo um ``PrimitiveType`` nomeado.
        """
        attribute = self._create("Attribute")
        attribute.name = name

        primitive_type = self._create("PrimitiveType")
        primitive_type.name = primitive_name

        attribute.type = primitive_type

        return attribute

    def _plist_or_ptuple_for_array(self, sc: ArraySC) -> EObject:
        """Tipo de um array de escalares: ``PList`` (homogêneo) ou ``PTuple``.

        Porte de ``PListOrPTupleForArray`` (``:307-328``).

        Parameters
        ----------
        sc : ArraySC
            O array em forma raw.

        Returns
        -------
        EObject
            ``PList`` vazio se o array é vazio (``:310-311``), ``PList`` com
            ``elementType`` se homogêneo, senão ``PTuple`` com um elemento por
            inner.
        """
        if sc.size() == 0:
            return self._create("PList")

        if sc.homogeneous:
            plist = self._create("PList")

            plist.elementType = self._recursive_type(sc.inners[0])

            return plist
        else:
            ptuple = self._create("PTuple")

            for inner in sc.inners:
                ptuple.elements.append(self._recursive_type(inner))

            return ptuple

    def _recursive_type(self, sc: SchemaComponent) -> EObject:
        """Tipo de um elemento de array, descendo em arrays aninhados.

        Porte de ``recursiveTypeFromSchemaComponent`` (``:330-342``).

        Parameters
        ----------
        sc : SchemaComponent
            Elemento do array.

        Returns
        -------
        EObject
            ``PList``/``PTuple`` se ``sc`` é array, senão ``PrimitiveType``.

        Notes
        -----
        Um ``ObjectSC`` que chegue aqui cai no ramo primitivo e vira
        ``PrimitiveType`` de nome ``""`` — é o ``TODO: Consider Objects?`` do
        autor (``:336``), não um caso a tratar melhor no porte.
        """
        if isinstance(sc, ArraySC):
            return self._plist_or_ptuple_for_array(sc)
        else:
            type_name = _primitive_type_name(sc)
            primitive = self._create("PrimitiveType")
            primitive.name = type_name
            return primitive

    def _maybe_reference(self, name: str, referenced: EObject) -> EObject | None:
        """Criar a ``Reference`` se o nome do campo casar com uma entidade raiz.

        Porte de ``maybeReference`` (``:364-386``).

        Parameters
        ----------
        name : str
            Nome do campo já singularizado pelo Inflector (``:194``).
        referenced : EObject
            O ``Attribute`` que carrega o id.

        Returns
        -------
        EObject or None
            A ``Reference`` criada, ou ``None`` se o matcher não casou.
        """
        # MELHORIA FUTURA: este `assert` só existe pra estreitar
        # `ReferenceMatcher | None` pro mypy. A causa é o `_ref_matcher` nascer
        # `None` e só ser populado no passo 3 do `build`. Passar o matcher como
        # parâmetro de `_fill_ev`/`_maybe_reference` (em vez de campo de `self`)
        # elimina o `Optional` na origem e dispensa o assert — o matcher só
        # atravessa do passo 3 pro 4, não é estado real do builder.
        assert self._ref_matcher is not None

        matched = self._ref_matcher.maybe_match(name)

        if matched is None:
            return None

        reference = self._create("Reference")

        reference.refsTo = matched

        if referenced.type.eClass.name == "PList":
            reference.lowerBound = 0
            reference.upperBound = -1
        else:
            reference.lowerBound = 1
            reference.upperBound = 1

        reference.attributes.append(referenced)

        return reference
