"""Harness de equivalência estrutural entre dois modelos U-Schema (Fase 0.3).

Instrumento central de validação do porte: compara dois modelos **no nível do
modelo** (não do texto), reproduzindo a noção de equivalência do
``USchemaCompareMain`` do Java (``es.um.uschema.doc2uschema.validation``) e da
árvore de comparadores em ``es.um.uschema.utils.custom.compare.*``.

Fidelidade
----------
- O **veredito** (``ComparisonResult.equivalent``) espelha o ``USchemaCompareMain``:
  nem mais rígido, nem mais frouxo que o oráculo Java. Como o ``startComparison``
  do Java é ``void``, "equivalente" traduz o seu ``warningLog`` vazio — toda
  divergência que o Java registraria como warning é **fatal** aqui.
- Nomes de ``EntityType``/``RelationshipType`` são casados em **minúsculo**
  (``LOWERCASE_NAMES=true`` no Java), com fallback fuzzy (``compare_names``). O
  nome do **schema**, porém, o Java compara com ``equals`` cru: é
  case-**sensitive**. Nomes de ``Feature`` também são case-sensitive (são chaves
  literais do documento).
- O Inflector (Fase 0.6) já foi aplicado a montante, então o harness **não**
  depende dele — só normaliza caixa.
- ``count``/``root`` são **ignorados** pelo veredito (o Java nunca os compara),
  mas entram no relatório como divergências **não-fatais** (decisão "fiel +
  reporte extra"), para dar visibilidade ao bug #8 sem virar fonte de falso
  alarme. O mesmo vale para o fallback fuzzy de entidade e para o casamento
  não-injetivo de variações (ver ``bugs_originais.md``, C7).
- Ignora: ``xmi:id``, ordem de serialização, formatação.
- **Um único desvio deliberado do oráculo** (bug C8): ``compare_datatype`` casa
  dois tipos **ausentes** (o ``elementType`` nulo de um ``PList`` vindo de array
  vazio), onde o Java reprova. Sem isso o comparador não é reflexivo — ele
  reprova o ``model_northwind.xmi`` contra si mesmo — e não serve de instrumento
  de validação. Justificativa completa em ``bugs_originais.md``.

O acesso ao modelo é **reflexivo** (PyEcore): o tipo concreto de um ``EObject``
vem de ``obj.eClass.name`` e as features são atributos Python homônimos aos do
``uschema.ecore`` (``obj.root``, ``obj.variations``, ``obj.features``,
``obj.type``, ``obj.upperBound``, ``obj.refsTo``, ...).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from pyecore.ecore import EObject

# Espelha ComparePrimitiveType.TYPES_MAP: chaves em minúsculo → tipo canônico.
# Um tipo AUSENTE do mapa é comparado como está (case-sensitive) — ver
# `compare_primitive_type`.
_PRIMITIVE_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "long": "number",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "double": "double",
    "float": "double",
}

# Espelha CompareSchemaType.MAX_DIFF_LETTERS_TO_MATCH (fallback fuzzy de nomes).
_MAX_DIFF_LETTERS_TO_MATCH = 3


class DivergenceCategory(StrEnum):
    """Categoria de uma divergência, para agrupar o relatório."""

    SCHEMA_NAME = "schema_name"
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    VARIATION = "variation"
    # Sem emissor: nenhum ponto do módulo produz uma Divergence(FEATURE). A
    # granularidade do oráculo para no nível da variação — os comparadores de
    # Feature devolvem `bool`, e quem registra a divergência é o
    # `_compare_schema_type_variations`, que só sabe "a variação não casou", não
    # *qual* feature discordou. Fica reservada caso as Fases 1-3 queiram um
    # relatório mais fino (o `_match_bag` teria de devolver o item que falhou, em
    # vez de um `bool`). **Se chegar ao fim do projeto sem uso, remover** — enum
    # com membro morto vira armadilha para quem mantém.
    FEATURE = "feature"
    COUNT = "count"
    ROOT = "root"


@dataclass(frozen=True)
class Divergence:
    """Uma diferença encontrada entre os dois modelos.

    Parameters
    ----------
    category : DivergenceCategory
        Em que nível a diferença apareceu.
    fatal : bool
        Se conta para o veredito (``True``) ou é só informativa (``False``).
        ``True`` equivale a um ``warningLog`` do ``USchemaCompareMain``. São
        **não-fatais** as categorias que o Java não registra (``COUNT``,
        ``ROOT``), as que ele registra como ``hit`` (fallback fuzzy de entidade)
        e as variações órfãs de ``schema2`` — decisão "fiel + reporte extra".
    message : str
        Descrição legível de onde e o que divergiu, numa única linha (o relatório
        é lido linha a linha). Identifica os dois lados: ``Schema1 Order.1`` /
        ``Schema2 Order.2``.
    """

    category: DivergenceCategory
    fatal: bool
    message: str


@dataclass
class ComparisonResult:
    """Resultado de uma comparação: o veredito e o relatório de divergências."""

    divergences: list[Divergence] = field(default_factory=list)

    @property
    def equivalent(self) -> bool:
        """``True`` sse não houve nenhuma divergência **fatal**.

        Returns
        -------
        bool
            Equivalência estrutural no sentido do ``USchemaCompareMain``:
            equivale ao ``warningLog`` dele estar vazio. As divergências
            não-fatais (informativas) não reprovam.
        """
        return not any(d.fatal for d in self.divergences)


def _match_bag(
    items1: Iterable[EObject],
    items2: Iterable[EObject],
    predicate: Callable[[EObject, EObject], bool],
) -> bool:
    """Casar duas coleções como multisets, ignorando ordem.

    Padrão que se repete em CompareStructuralVariation/CompareKey/ComparePTuple/
    CompareAggregate: para cada item de ``items1``, achar o **primeiro** item
    ainda não usado de ``items2`` que satisfaça ``predicate`` e removê-lo; ao
    final, ``items2`` tem de ter esvaziado.

    Parameters
    ----------
    items1, items2 : iterable of EObject
        As duas coleções a casar (mesmo tamanho é pré-condição do chamador).
    predicate : callable
        Comparador ``(a, b) -> bool`` aplicado par a par.

    Returns
    -------
    bool
        ``True`` se todo item de ``items1`` casou com um item distinto de
        ``items2`` e nada sobrou.
    """
    bag = list(items2)

    for a in items1:
        found = next((item for item in bag if predicate(a, item)), None)

        if found is None:
            return False

        bag.remove(found)

    return len(bag) == 0


def compare_primitive_type(p1: EObject, p2: EObject) -> bool:
    """Comparar dois ``PrimitiveType`` colapsando sinônimos.

    Espelha ``ComparePrimitiveType``: ``Long``, ``Integer`` e ``Number`` colapsam
    em ``number``; ``Double`` e ``Float`` em ``double``. Um tipo ausente de
    ``_PRIMITIVE_TYPE_MAP`` é comparado como está — e aí a comparação é
    case-**sensitive** (``Date`` != ``date``).

    Parameters
    ----------
    p1, p2 : EObject
        Os dois ``PrimitiveType`` a comparar.

    Returns
    -------
    bool
        ``True`` se os dois nomes mapeiam para o mesmo tipo canônico.
    """
    p1_name: str = p1.name
    p2_name: str = p2.name

    p1_name_mapped: str = _PRIMITIVE_TYPE_MAP.get(p1_name.lower(), p1_name)

    p2_name_mapped: str = _PRIMITIVE_TYPE_MAP.get(p2_name.lower(), p2_name)

    return p1_name_mapped == p2_name_mapped


def compare_datatype(t1: EObject | None, t2: EObject | None) -> bool:
    """Despachar a comparação de ``DataType`` pelo tipo concreto (``eClass.name``).

    Espelha ``CompareDataType``. Tipos concretos diferentes nunca casam; dois
    ``Null`` sempre casam.

    Parameters
    ----------
    t1, t2 : EObject or None
        Os dois ``DataType`` a comparar. ``None`` representa tipo **ausente** —
        tipicamente o ``elementType`` de um ``PList`` vindo de um array vazio,
        onde não há elemento do qual inferir tipo.

    Returns
    -------
    bool
        ``True`` se são do mesmo tipo concreto e o comparador específico aprova.
        Dois ``None`` casam; um ``None`` contra um tipo, não.

    Notes
    -----
    **Desvio deliberado do oráculo (bug C8, ver ``bugs_originais.md``).** O
    ``checkNulls`` do Java é ``or``, não XOR: lá, ``(null, null)`` reprova. Como
    ``ComparePList`` delega o ``elementType`` a este comparador, dois ``PList``
    vazios idênticos são declarados **diferentes** — e o comparador do Java passa
    a reprovar o ``model_northwind.xmi`` contra **si mesmo** (o atributo
    ``privileges`` de ``Employees`` é um array vazio). Um comparador de
    equivalência que não é reflexivo não mede nada, e nenhum porte fiel passaria
    por ele: os dois lados teriam o ``PList`` vazio.

    Divergimos aqui, e **só aqui**: ``(None, None)`` casa. O afrouxamento atinge
    exclusivamente o caso em que os dois lados **concordam**; a divergência real —
    um lado com tipo, o outro sem — continua reprovando. É a mesma decisão que o
    próprio original já toma em ``CompareAttribute``, que trata ``(null, null)``
    como igual antes de delegar.
    """
    if t1 is None and t2 is None:
        return True

    if t1 is None or t2 is None:
        return False

    t1_name = t1.eClass.name
    t2_name = t2.eClass.name

    if t1_name == t2_name:
        match t1_name:
            case "PrimitiveType":
                return compare_primitive_type(t1, t2)
            case "PList":
                return compare_plist(t1, t2)
            case "PMap":
                return compare_pmap(t1, t2)
            case "PTuple":
                return compare_ptuple(t1, t2)
            case "PSet":
                return compare_pset(t1, t2)
            case "Null":
                return True
            case _:
                return False

    else:
        return False


def compare_plist(l1: EObject, l2: EObject) -> bool:
    """Comparar dois ``PList`` pelo seu ``elementType``.

    Espelha ``ComparePList``. ``PList`` não tem campo de tamanho no ecore — só
    ``elementType``. (O tamanho ignorado que origina o bug #8 vive no
    ``ArraySC.equals`` do modelo intermediário, Fase 1.1, não aqui.)

    Parameters
    ----------
    l1, l2 : EObject
        Os dois ``PList`` a comparar.

    Returns
    -------
    bool
        ``True`` se os ``elementType`` casam.
    """
    element_type1 = l1.elementType
    element_type2 = l2.elementType
    return compare_datatype(element_type1, element_type2)


def compare_pset(s1: EObject, s2: EObject) -> bool:
    """Comparar dois ``PSet`` pelo seu ``elementType``.

    Parameters
    ----------
    s1, s2 : EObject
        Os dois ``PSet`` a comparar.

    Returns
    -------
    bool
        ``True`` se os ``elementType`` casam.
    """
    element_type1 = s1.elementType
    element_type2 = s2.elementType
    return compare_datatype(element_type1, element_type2)


def compare_pmap(m1: EObject, m2: EObject) -> bool:
    """Comparar dois ``PMap`` por ``keyType`` e ``valueType``.

    O ``keyType`` é sempre um ``PrimitiveType`` (por isso não passa pelo despacho
    de ``compare_datatype``); o ``valueType`` é um ``DataType`` qualquer.

    Parameters
    ----------
    m1, m2 : EObject
        Os dois ``PMap`` a comparar.

    Returns
    -------
    bool
        ``True`` se chave e valor casam.
    """
    keys_match = compare_primitive_type(m1.keyType, m2.keyType)
    values_match = compare_datatype(m1.valueType, m2.valueType)
    return keys_match and values_match


def compare_ptuple(t1: EObject, t2: EObject) -> bool:
    """Comparar dois ``PTuple`` como multiset dos seus ``elements``.

    A ordem dos elementos é ignorada — apesar do nome, ``PTuple`` é comparada
    como saco, não como sequência. É o que ``ComparePTuple`` faz.

    Parameters
    ----------
    t1, t2 : EObject
        Os dois ``PTuple`` a comparar.

    Returns
    -------
    bool
        ``True`` se os ``elements`` casam par a par, em qualquer ordem.
    """
    return _match_bag(t1.elements, t2.elements, compare_datatype)


def compare_attribute(a1: EObject, a2: EObject) -> bool:
    """Comparar dois ``Attribute`` pelo seu ``type``.

    O ``name`` e o ``optional`` **não** são comparados aqui — quem faz isso é a
    ``compare_feature``, antes de despachar.

    Parameters
    ----------
    a1, a2 : EObject
        Os dois ``Attribute`` a comparar.

    Returns
    -------
    bool
        ``True`` se os ``type`` casam, ou se ambos são ``None``.
    """
    type1 = a1.type
    type2 = a2.type

    if type1 is None and type2 is None:
        return True

    return compare_datatype(type1, type2)


def _same_container(v1: EObject, v2: EObject) -> bool:
    """Casar duas ``StructuralVariation`` só pelo **nome do seu ``container``**.

    Predicado compartilhado pelos dois pontos onde variações são casadas por
    identidade da entidade que as contém, e não por estrutura: o multiset de
    ``aggregates`` do ``CompareAggregate`` e o ``isFeaturedBy`` do
    ``CompareReference``. Nunca desce nas ``features`` da variação — é o que
    impede recursão infinita em agregados cíclicos.

    O ``container`` tem ``lowerBound=1`` no ecore, mas o PyEcore não impõe isso,
    então ``None`` é tratado explicitamente.

    Parameters
    ----------
    v1, v2 : EObject
        As duas ``StructuralVariation`` cujos containers se quer casar.

    Returns
    -------
    bool
        ``True`` se ambos os containers são ``None``, ou se seus nomes casam por
        ``compare_names``.
    """
    if (v1.container is None) != (v2.container is None):
        return False

    if v1.container is None and v2.container is None:
        return True

    return compare_names(v1.container, v2.container)


def compare_aggregate(a1: EObject, a2: EObject) -> bool:
    """Comparar dois ``Aggregate`` por cardinalidade e alvos agregados (por nome).

    Espelha ``CompareAggregate``. As variações em ``aggregates`` são casadas
    **só pelo nome do container** (ver ``_same_container``), nunca por
    ``compare_variation``.

    Parameters
    ----------
    a1, a2 : EObject
        Os dois ``Aggregate`` a comparar.

    Returns
    -------
    bool
        ``True`` se cardinalidade e multiset de containers agregados casam.
    """
    if a1 is None or a2 is None:
        return False

    if a1 is a2:
        return True

    if not ((a1.upperBound == a2.upperBound) and (a1.lowerBound == a2.lowerBound)):
        return False

    return _match_bag(a1.aggregates, a2.aggregates, _same_container)


def compare_reference(r1: EObject, r2: EObject) -> bool:
    """Comparar duas ``Reference`` (cardinalidade, ``opposite``, ``attributes``, ``refsTo``).

    Espelha ``CompareReference``. É o comparador mais longo do módulo: cinco
    blocos em sequência, qualquer um deles podendo reprovar.

    Parameters
    ----------
    r1, r2 : EObject
        As duas ``Reference`` a comparar.

    Returns
    -------
    bool
        ``True`` se cardinalidade, ``opposite``, ``isFeaturedBy``, ``attributes``
        e ``refsTo`` casam.

    Notes
    -----
    ``opposite`` é auto-referente (``Reference`` → ``Reference``) e o Java não
    tem guarda de ciclo: se ``r1.opposite.opposite is r1``, a recursão
    ``compare_reference`` → ``compare_feature`` → ``compare_reference`` não
    termina. Nenhum XMI de referência popula ``opposite``, então o caso nunca é
    exercitado; portamos fiel em vez de inventar um guarda de visitados que o
    oráculo não tem.
    """
    if r1 is None or r2 is None:
        return False

    if r1 is r2:
        return True

    if not ((r1.upperBound == r2.upperBound) and (r1.lowerBound == r2.lowerBound)):
        return False

    if (r1.opposite is None) != (r2.opposite is None):
        return False

    if (r1.opposite is not None) and (not compare_feature(r1.opposite, r2.opposite)):
        return False

    if (r1.isFeaturedBy == []) != (r2.isFeaturedBy == []):
        return False

    if (r1.isFeaturedBy != []) and (r2.isFeaturedBy != []):
        if len(r1.isFeaturedBy) != len(r2.isFeaturedBy):
            return False

        # Só o elemento [0] é comparado; 1..n são ignorados. É o defeito C1 do
        # oráculo, replicado de propósito — ver bugs_originais.md. A correção
        # (_match_bag sobre a lista inteira) está lá, para o upstream.
        if not _same_container(r1.isFeaturedBy[0], r2.isFeaturedBy[0]):
            return False

    if not _match_bag(r1.attributes, r2.attributes, compare_feature):
        return False

    if (r1.refsTo is None) != (r2.refsTo is None):
        return False

    if r1.refsTo is None and r2.refsTo is None:
        return True
    else:
        return compare_names(r1.refsTo, r2.refsTo)


def compare_key(k1: EObject, k2: EObject) -> bool:
    """Comparar duas ``Key`` pelo multiset de ``attributes``.

    Sem guardas de ``None`` nem de identidade: ``compare_key`` só é alcançável
    através de ``compare_feature``, que já os aplicou. Os guardas do
    ``CompareKey`` do Java seriam código morto aqui.

    Parameters
    ----------
    k1, k2 : EObject
        As duas ``Key`` a comparar.

    Returns
    -------
    bool
        ``True`` se os ``attributes`` casam par a par, em qualquer ordem.
    """
    return _match_bag(k1.attributes, k2.attributes, compare_feature)


def compare_feature(f1: EObject, f2: EObject) -> bool:
    """Comparar duas ``Feature`` (nome + despacho Structural/Logical).

    Espelha ``CompareFeature`` + ``CompareStructuralFeature`` +
    ``CompareLogicalFeature`` achatados num só despacho: as quatro Feature
    concretas (Attribute, Aggregate, Key, Reference) são folhas de ramos
    disjuntos, então o teste em dois níveis do Java é redundante.

    Parameters
    ----------
    f1, f2 : EObject
        As duas ``Feature`` a comparar.

    Returns
    -------
    bool
        ``True`` se nome e conteúdo casam.
    """
    if f1 is None or f2 is None:
        return False

    if f1 is f2:
        return True

    name1: str | None = f1.name
    name2: str | None = f2.name

    if (name1 is None) != (name2 is None):
        return False

    if name1 != name2:
        return False

    if f1.eClass.name != f2.eClass.name:
        return False

    feature_type: str = f1.eClass.name

    match feature_type:
        case "Attribute" | "Aggregate":
            optional1: bool = f1.optional
            optional2: bool = f2.optional

            if optional1 != optional2:
                return False

            if feature_type == "Attribute":
                return compare_attribute(f1, f2)
            else:
                return compare_aggregate(f1, f2)

        case "Key":
            return compare_key(f1, f2)
        case "Reference":
            return compare_reference(f1, f2)
        case _:
            return False


def compare_variation(v1: EObject, v2: EObject) -> bool:
    """Comparar duas ``StructuralVariation`` só pela assinatura de features.

    Espelha ``CompareStructuralVariation``: **não** compara ``variationId``,
    ``count`` nem ``timestamp`` — só o multiset de ``features``.

    Parameters
    ----------
    v1, v2 : EObject
        As duas ``StructuralVariation`` a comparar.

    Returns
    -------
    bool
        ``True`` se as duas têm o mesmo multiset de ``features``.
    """
    if v1 is None or v2 is None:
        return False

    if v1 == v2:
        return True

    return _match_bag(v1.features, v2.features, compare_feature)


def compare_names(s1: EObject, s2: EObject) -> bool:
    """Casar nomes de dois ``SchemaType`` de forma tolerante (fallback do Java).

    Espelha ``CompareSchemaType.compareNames``. A tolerância é **substring
    bidirecional** com diferença de comprimento menor que
    ``_MAX_DIFF_LETTERS_TO_MATCH``, não distância de edição: absorve divergência
    de caixa e de pluralização (``Order``/``Orders``), que são as decisões que o
    Inflector (Fase 0.6) pode legitimamente tomar de forma diferente. **Não**
    absorve typo — ``Address``/``Adress`` reprova, e deve reprovar: um nome
    errado no porte é defeito, não ruído de naming.

    Parameters
    ----------
    s1, s2 : EObject
        Os dois ``SchemaType`` (``EntityType`` ou ``RelationshipType``) cujos
        nomes se quer casar.

    Returns
    -------
    bool
        ``True`` se os nomes casam exatamente (ignorando caixa) ou pelo fallback
        de substring.

    Raises
    ------
    AttributeError
        Se algum dos ``SchemaType`` tiver ``name`` igual a ``None``. O ecore
        declara ``name`` com ``lowerBound=1``, mas o PyEcore não impõe isso —
        falhar aqui espelha o ``NullPointerException`` que o Java levanta no
        ``casec.apply(null)``, já que ``compareNames`` é chamada direto por
        ``CompareAggregate``/``CompareReference``/``USchemaCompareMain``, sem
        guarda de nome.
    """
    # O Java testa `equals` e depois `toLowerCase().equals()`, mas o `casec` já
    # minusculizou ambos os nomes — os dois termos são redundantes e colapsam
    # neste `==`.
    name1: str = s1.name.lower()
    name2: str = s2.name.lower()

    return (name1 == name2) or (
        (name1 in name2 or name2 in name1)
        and (abs(len(name1) - len(name2)) < _MAX_DIFF_LETTERS_TO_MATCH)
    )


class USchemaComparer:
    """Compara dois modelos U-Schema acumulando um relatório de divergências.

    Espelha o ``USchemaCompareMain``: fluxo assimétrico (itera as entidades de
    ``schema1`` procurando correspondente em ``schema2``), casamento por nome
    minúsculo com fallback fuzzy, e comparação profunda variação-a-variação.

    Mapeamento do veredito
    ----------------------
    O ``startComparison`` do Java é ``void``: ele acumula ``hitLog`` e
    ``warningLog``, e o ``main`` só imprime os dois. A única leitura possível de
    "equivalente" é **``warningLog`` vazio**. Logo:

    - **Fatal** = tudo que o Java escreveria no ``warningLog``, inclusive o
      mismatch de nome do schema e o de tamanho das listas.
    - **Não-fatal** = categorias que o Java **não registra em lugar nenhum**
      (``COUNT``, ``ROOT``) mais os casos que ele registra como ``hit``
      (o fallback fuzzy de entidade) ou que ele silencia (o casamento
      não-injetivo de variações, ver ``bugs_originais.md`` C7).

    Isto é a política "fiel + reporte extra": o veredito nunca é mais rígido nem
    mais frouxo que o oráculo; o relatório é mais informativo.
    """

    def __init__(self) -> None:
        """Iniciar um comparador com relatório vazio."""
        self.divergences: list[Divergence] = []

    def start_comparison(self, schema1: EObject, schema2: EObject) -> ComparisonResult:
        """Comparar ``schema1`` (oráculo) com ``schema2`` (porte) ponta a ponta.

        Parameters
        ----------
        schema1 : EObject
            Raiz ``USchema`` de referência (o oráculo).
        schema2 : EObject
            Raiz ``USchema`` do porte, a validar.

        Returns
        -------
        ComparisonResult
            Veredito (``.equivalent``) + lista de divergências por categoria.
        """
        if schema1.name != schema2.name:
            self.divergences.append(
                Divergence(
                    category=DivergenceCategory.SCHEMA_NAME,
                    fatal=True,
                    message=(
                        f"Schema names differ: Schema1 is {schema1.name}, Schema2 is {schema2.name}"
                    ),
                )
            )

        entities_quantity1 = len(schema1.entities)
        entities_quantity2 = len(schema2.entities)

        if entities_quantity1 != entities_quantity2:
            self.divergences.append(
                Divergence(
                    category=DivergenceCategory.ENTITY,
                    fatal=True,
                    message=(
                        f"Entity counts differ: Schema1 has {entities_quantity1}, "
                        f"Schema2 has {entities_quantity2}"
                    ),
                )
            )

        self._compare_entities(schema1, schema2)

        relationships_quantity1 = len(schema1.relationships)
        relationships_quantity2 = len(schema2.relationships)

        if relationships_quantity1 != relationships_quantity2:
            self.divergences.append(
                Divergence(
                    category=DivergenceCategory.RELATIONSHIP,
                    fatal=True,
                    message=(
                        f"Relationship counts differ: Schema1 has {relationships_quantity1}, "
                        f"Schema2 has {relationships_quantity2}"
                    ),
                )
            )

        self._compare_relationships(schema1, schema2)

        return ComparisonResult(self.divergences)

    def _compare_entities(self, schema1: EObject, schema2: EObject) -> None:
        """Casar cada ``EntityType`` de ``schema1`` com um de ``schema2``.

        Fluxo assimétrico: uma entidade a mais em ``schema2`` só é detectada pelo
        check de tamanho feito em ``start_comparison``.
        """
        for e1 in schema1.entities:
            e2 = next(
                (cand for cand in schema2.entities if e1.name.lower() == cand.name.lower()), None
            )

            if e2 is not None:
                self._compare_schema_type_variations(e1, e2)

                if e1.root != e2.root:
                    self.divergences.append(
                        Divergence(
                            category=DivergenceCategory.ROOT,
                            fatal=False,
                            message=(
                                f"Root flag differs for entity {e1.name}: "
                                f"Schema1 has root={e1.root}, Schema2 has root={e2.root}"
                            ),
                        )
                    )
            else:
                candidate = next(
                    (cand for cand in schema2.entities if compare_names(e1, cand)), None
                )

                if candidate is None:
                    self.divergences.append(
                        Divergence(
                            category=DivergenceCategory.ENTITY,
                            fatal=True,
                            message=(
                                f"Schema1 entity {e1.name} is not matched by any entity in Schema2"
                            ),
                        )
                    )

                else:
                    good = self._compare_schema_type_variations(e1, candidate)

                    if good:
                        self.divergences.append(
                            Divergence(
                                category=DivergenceCategory.ENTITY,
                                fatal=False,
                                message=(
                                    f"Schema1 entity {e1.name} not found by name in Schema2; "
                                    f"matched {candidate.name} instead"
                                ),
                            )
                        )

                    else:
                        self.divergences.append(
                            Divergence(
                                category=DivergenceCategory.ENTITY,
                                fatal=True,
                                message=(
                                    f"Schema1 entity {e1.name} was fuzzy-matched to Schema2 "
                                    f"{candidate.name}, but their variations differ"
                                ),
                            )
                        )

    def _compare_relationships(self, schema1: EObject, schema2: EObject) -> None:
        """Casar cada ``RelationshipType`` de ``schema1`` com um de ``schema2``.

        Igual ao laço de entidades, com duas diferenças: **não há fallback fuzzy**
        e não há campo ``root``.
        """
        for r1 in schema1.relationships:
            r2 = next(
                (cand for cand in schema2.relationships if r1.name.lower() == cand.name.lower()),
                None,
            )

            if r2 is not None:
                self._compare_schema_type_variations(r1, r2)
            else:
                self.divergences.append(
                    Divergence(
                        category=DivergenceCategory.RELATIONSHIP,
                        fatal=True,
                        message=(
                            f"Schema1 relationship {r1.name} is not matched by "
                            f"any relationship in Schema2"
                        ),
                    )
                )

    def _compare_schema_type_variations(self, s1: EObject, s2: EObject) -> bool:
        """Comparar as variações de dois ``SchemaType`` já casados por nome.

        Espelha o método privado ``compareSchemaTypes`` do ``USchemaCompareMain``
        (não a classe ``CompareSchemaType``).

        Returns
        -------
        bool
            O ``goodHit`` do Java: ``True`` se toda variação de ``s1`` achou par
            e os tamanhos batiam.

        Notes
        -----
        O Java casa variações com ``findAny`` **sem remover** a casada do conjunto
        de candidatas, e nunca verifica o sentido ``s2 → s1``. Duas variações de
        ``s1`` podem casar com a mesma de ``s2``, deixando uma variação de ``s2``
        órfã sem que nada seja registrado — um **falso positivo** do harness
        (``bugs_originais.md`` C7). Replicamos o veredito e registramos a anomalia
        como divergência não-fatal.
        """
        good = True

        if len(s1.variations) != len(s2.variations):
            good = False
            self.divergences.append(
                Divergence(
                    category=DivergenceCategory.VARIATION,
                    fatal=True,
                    message=(
                        f"Variation list sizes differ for schema type {s1.name}: "
                        f"Schema1 has {len(s1.variations)}, Schema2 has {len(s2.variations)}"
                    ),
                )
            )

        matched: list[EObject] = []

        for v1 in s1.variations:
            v2_found = next((item for item in s2.variations if compare_variation(v1, item)), None)

            if v2_found is None:
                good = False
                self.divergences.append(
                    Divergence(
                        category=DivergenceCategory.VARIATION,
                        fatal=True,
                        message=(
                            f"Schema1 {s1.name}.{v1.variationId} is not matched by "
                            f"any variation in Schema2 {s2.name}"
                        ),
                    )
                )
            else:
                matched.append(v2_found)
                if v1.count != v2_found.count:
                    self.divergences.append(
                        Divergence(
                            category=DivergenceCategory.COUNT,
                            fatal=False,
                            message=(
                                f"Count differs: Schema1 {s1.name}.{v1.variationId} "
                                f"has {v1.count}, Schema2 {s2.name}.{v2_found.variationId} "
                                f"has {v2_found.count}"
                            ),
                        )
                    )

        # `orphans` é um set: a ordem de iteração depende do id() dos EObject e
        # variaria entre execuções. Ordena por variationId — o relatório é
        # determinístico por contrato (ver CLAUDE.md).
        orphans = set(s2.variations) - set(matched)

        for orphan in sorted(orphans, key=lambda v: int(v.variationId)):
            self.divergences.append(
                Divergence(
                    category=DivergenceCategory.VARIATION,
                    fatal=False,
                    message=(
                        f"Schema2 {s2.name}.{orphan.variationId} was not matched by "
                        f"any variation in Schema1 {s1.name}"
                    ),
                )
            )

        return good


def compare(schema1: EObject, schema2: EObject) -> ComparisonResult:
    """Comparar dois modelos U-Schema (fachada sobre ``USchemaComparer``).

    Parameters
    ----------
    schema1 : EObject
        Raiz ``USchema`` de referência (oráculo).
    schema2 : EObject
        Raiz ``USchema`` do porte.

    Returns
    -------
    ComparisonResult
        Veredito + relatório de divergências.

    Examples
    --------
    >>> from pathlib import Path
    >>> from uschema.metamodel.registry import load_metamodel
    >>> from uschema.metamodel.xmi import load_model
    >>> pkg = load_metamodel()
    >>> oracle = load_model(Path("resources/mongodb/model_northwind.xmi"), pkg)
    >>> port = load_model(Path("output/model_northwind.xmi"), pkg)
    >>> result = compare(oracle, port)
    >>> result.equivalent
    True
    >>> for d in result.divergences:  # divergências não-fatais, se houver
    ...     print(d.category, d.message)
    """
    result: ComparisonResult = USchemaComparer().start_comparison(schema1, schema2)

    return result
