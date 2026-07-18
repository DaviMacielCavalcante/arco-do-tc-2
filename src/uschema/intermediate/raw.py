"""Modelo intermediário *raw* — a árvore Composite da inferência (Fase 1.1).

Porte de ``intermediate/raw/*.java``. É a representação que o
``SchemaInference`` constrói a partir da tripla e que o ``USchemaModelBuilder``
consome para emitir o modelo PyEcore. Fica **entre** os dois: nada aqui conhece
EMF.

Igualdade estrutural é *load-bearing*
-------------------------------------
Todo o colapso de variações do pipeline sai do ``__eq__`` destas classes. Se a
igualdade divergir do Java, variações que deveriam colapsar não colapsam (ou
vice-versa), o número de ``StructuralVariation`` muda e o XMI não bate com o
oráculo. Por isso cada ``__eq__``/``__hash__`` abaixo cita a linha do original —
e por isso eles são cobertos por teste antes de existir qualquer consumidor.

Três decisões do autor original que **replicamos de propósito**:

1. **A base compara o nome da classe** (``SchemaComponent.java:8``), então
   quaisquer dois ``StringSC`` são iguais — as folhas não têm estado.
2. **``ArraySC.__eq__`` ignora o tamanho** (``ArraySC.java:82-101``): a checagem
   de ``homogeneous_size`` está **comentada** na ``:97``, com o comentário do
   autor explicando que reconciliar tamanhos exigiria "another step". É
   deliberado, e é a origem do bug **#8** — sem essa igualdade frouxa o #8 nem
   dispara.
3. **``ObjectSC.__eq__`` inclui a ordem dos campos**, porque ``inners`` é lista,
   não mapa (``ObjectSC.java:33-34``). O ``infer`` ordena os campos antes de
   inserir (``SchemaInference.java:192-194``), então a ordem é estável — mas a
   igualdade depende dela, e trocar por ``dict`` faria variações colapsarem onde
   o Java não colapsa.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from uschema.intermediate.metadata import ObjectMetadata

__all__ = [
    "ArraySC",
    "BooleanSC",
    "NullSC",
    "NumberSC",
    "ObjectIdSC",
    "ObjectSC",
    "SchemaComponent",
    "StringSC",
]


class SchemaComponent:
    """Base do Composite: um nó qualquer da árvore raw.

    Porte de ``SchemaComponent.java``. A classe existe sobretudo pela igualdade:
    duas folhas do mesmo tipo são **sempre** iguais, porque não carregam estado.

    Notes
    -----
    O Java estoura ``NullPointerException`` se ``other`` for ``null``
    (``:8``, ``other.getClass()`` sem guarda). Não replicamos — é guarda
    faltando, não semântica, como o bug ``I2`` do Inflector (ver
    ``naming/inflector.py``). Registrar aqui se a decisão mudar.
    """

    def __eq__(self, other: object) -> bool:
        """Comparar pelo **nome da classe concreta** (``SchemaComponent.java:8``).

        Parameters
        ----------
        other : object
            O outro objeto. Não precisa ser ``SchemaComponent``.

        Returns
        -------
        bool
            ``True`` se as duas classes concretas têm o mesmo nome.
        """
        return type(self) is type(other)

    def __hash__(self) -> int:
        """Hash da classe concreta (``SchemaComponent.java:14``)."""
        # `type(self)`, não `self`: hashear o próprio objeto reentraria neste
        # mesmo método (RecursionError). O que o `__eq__` compara é a classe.
        return hash(type(self))


class StringSC(SchemaComponent):
    """Folha textual. Sem estado — ver :class:`SchemaComponent`."""


class NumberSC(SchemaComponent):
    """Folha numérica. Sem estado."""


class BooleanSC(SchemaComponent):
    """Folha booleana. Sem estado."""


class NullSC(SchemaComponent):
    """Folha nula. Sem estado."""


class ObjectIdSC(SchemaComponent):
    """Folha ``ObjectId``. Sem estado.

    Só é alcançada pelo caminho de extração **map-reduce**, onde o ``ObjectId``
    viaja como a string ``"oid"``. No caminho Spark — o do oráculo — ele chega
    como ``{"$oid": …}`` e vira ``ObjectSC``. Ver ``extractors/triple.py``.
    """


@dataclass(eq=False)
class ObjectSC(SchemaComponent):
    """Nó objeto: uma variação estrutural, com nome de entidade e metadados.

    Porte de ``ObjectSC.java``.

    Parameters
    ----------
    inners : list of tuple of (str, SchemaComponent)
        Campos, **em ordem**, como pares nome→componente. É lista e não dict de
        propósito: a ordem entra no ``__eq__`` (``ObjectSC.java:33-34``).
    is_root : bool, default False
        Se este objeto veio de um documento de topo. O Java inicializa em
        ``FALSE`` no construtor (``:19``).
    meta : ObjectMetadata or None, default None
        Contagem e janela de tempo. O Java deixa ``null`` no construtor e o
        ``infer`` atribui logo depois (``SchemaInference.java:187``); objetos
        não-raiz recebem um ``ObjectMetadata`` zerado.
    entity_name : str or None, default None
        Nome da entidade, já capitalizado pelo Inflector
        (``SchemaInference.java:183,188``). Fica ``None`` quando o objeto é
        construído fora do ``infer`` — é o caso do ``RawSchemaGen`` usado pelo
        ``J2SchemaSimpleTests``, e é por isso que a saída esperada lá começa com
        ``<null>``.
    """

    inners: list[tuple[str, SchemaComponent]] = field(default_factory=list)
    is_root: bool = False
    meta: ObjectMetadata | None = None
    entity_name: str | None = None

    def __eq__(self, other: object) -> bool:
        """Comparar por ``entity_name`` + ``is_root`` + ``inners`` (``:29-37``).

        Parameters
        ----------
        other : object
            O outro objeto.

        Returns
        -------
        bool
            ``True`` se os três componentes coincidem. Um objeto que não seja
            ``ObjectSC`` dá ``False``.
        """
        if self is other:
            return True

        if isinstance(other, ObjectSC):
            return (
                self.entity_name == other.entity_name
                and self.is_root == other.is_root
                and self.inners == other.inners
            )
        else:
            return False

    def __hash__(self) -> int:
        """XOR de ``entity_name``, ``is_root`` e ``inners`` (``ObjectSC.java:24``)."""
        return (hash(self.entity_name)) ^ hash(self.is_root) ^ hash(tuple(self.inners))

    def add(self, pair: tuple[str, SchemaComponent]) -> None:
        """Anexar um campo ao fim de ``inners`` (``ObjectSC.java:49-51``)."""
        self.inners.append(pair)

    def add_all(self, pairs: list[tuple[str, SchemaComponent]]) -> None:
        """Anexar vários campos, na ordem dada (``ObjectSC.java:39-47``)."""
        self.inners.extend(pairs)

    def size(self) -> int:
        """Número de campos (``ObjectSC.java:57-59``)."""
        return len(self.inners)


@dataclass(eq=False)
class ArraySC(SchemaComponent):
    """Nó array, com a otimização de array homogêneo do original.

    Porte de ``ArraySC.java``. Enquanto todos os elementos são iguais, guarda
    **um só** em ``inners`` e conta em ``homogeneous_size``; ao aparecer um
    diferente, vira heterogêneo e ``inners`` é reconstruído por extenso.

    Parameters
    ----------
    inners : list of SchemaComponent
        Um único elemento enquanto homogêneo; todos, quando heterogêneo.
    homogeneous : bool, default True
        Um array recém-criado (inclusive o vazio) é homogêneo.
    homogeneous_size : int, default 0
        Quantos elementos o array tem, enquanto homogêneo. **É o que faz o
        guarda do bug #7 funcionar**: array vazio ⇒ ``size() == 0`` *e*
        ``inners`` vazio.
    lower_bounds : int, default 0
        Nunca é incrementado pelo original — só existe o *setter*
        (``ArraySC.java:118-120``). Portado como está.
    upper_bounds : int, default 0
        Incrementado a cada ``add``, homogêneo ou não (``:65``).
    """

    inners: list[SchemaComponent] = field(default_factory=list)
    homogeneous: bool = True
    homogeneous_size: int = 0
    lower_bounds: int = 0
    upper_bounds: int = 0

    def add(self, sc: SchemaComponent) -> None:
        """Acrescentar um elemento, mantendo a otimização homogênea (``:38-67``).

        Parameters
        ----------
        sc : SchemaComponent
            O elemento a acrescentar.
        """
        if self.homogeneous:
            if self.inners == []:
                self.homogeneous_size += 1

                self.inners.append(sc)
            else:
                first = self.inners[0]

                if sc == first:
                    self.homogeneous_size += 1

                else:
                    self.homogeneous = False

                    self.inners = [first] * self.homogeneous_size + [sc]

            self.upper_bounds += 1
        else:
            self.inners.append(sc)

            self.upper_bounds += 1

    def add_all(self, elements: list[SchemaComponent]) -> None:
        """Acrescentar vários elementos, um a um (``ArraySC.java:69-73``)."""
        for element in elements:
            self.add(element)

    def size(self) -> int:
        """Número de elementos do array (``ArraySC.java:106-112``).

        Returns
        -------
        int
            ``homogeneous_size`` se homogêneo, senão ``len(inners)``.
        """
        if self.homogeneous:
            return self.homogeneous_size
        else:
            return len(self.inners)

    def __eq__(self, other: object) -> bool:
        """Comparar por ``homogeneous`` + ``inners``, **ignorando o tamanho**.

        Parameters
        ----------
        other : object
            O outro objeto.

        Returns
        -------
        bool
            ``True`` se ambos são ``ArraySC``, com a mesma homogeneidade e os
            mesmos ``inners``.

        Notes
        -----
        O tamanho **não** entra na comparação: a checagem de ``homogeneous_size``
        está comentada em ``ArraySC.java:96-97``. É deliberado — o comentário do
        autor nas ``:90-95`` explica que reconciliar tamanhos exigiria um passo
        a mais — e é a origem do bug **#8**: dois arrays homogêneos de tamanhos
        diferentes são iguais, as variações colapsam, e o ``meta`` da segunda é
        descartado pelo ``infer``. A correção do #8 vive em 1.2 (combinar em vez
        de descartar); **esta** igualdade fica como está.
        """
        if other is self:
            return True

        if isinstance(other, ArraySC):
            if self.homogeneous != other.homogeneous:
                return False

            return self.inners == other.inners
        else:
            return False

    def __hash__(self) -> int:
        """Hash de ``inners`` apenas (``ArraySC.java:74-78``)."""
        return hash(tuple(self.inners))
