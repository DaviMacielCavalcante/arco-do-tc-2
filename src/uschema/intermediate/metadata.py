"""Metadados de ocorrência de uma variação estrutural (Fase 1.1).

Porte de ``ObjectMetadata.java``. Carrega o que a tripla trouxe — quantas
ocorrências e a janela de tempo — e sabe **combinar** duas dessas janelas.

Onde ``combine_metadata`` é chamado (e onde **não** é)
--------------------------------------------------------
É chamado em ``innerCountAndTimestampsAdjust`` (``SchemaInference.java:100-104``
— propaga meta das ocorrências-raiz pras entidades internas, ver **M2** em
``bugs_originais.md``) e em ``EVariationMerger.mergeEquivalentEVs``
(``DefaultEVariationMerger.java:36`` — Fase 1.3a). **Não** é chamado no colapso
de variações dentro do próprio ``infer`` (``SchemaInference.java:207-211``):
ali o original só faz ``retSchema = foundSchema.get();`` e mais nada — o
``meta`` inteiro da ocorrência nova (count **e** timestamps) é descartado, sem
combinar. Isso é o bug **#8** (ver ``bugs_originais.md``).

``combine_metadata`` (em ``innerCountAndTimestampsAdjust``/``EVariationMerger``)
continua disparando mesmo quando ``ArraySC.__eq__`` colapsa duas árvores de
**tamanho de array diferente** (a igualdade que ignora o tamanho,
``ArraySC.java:82-101``) — só que isso é irrelevante pro #8: o #8 acontece
**antes**, no colapso inline de ``infer``, onde nenhuma combinação roda.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ObjectMetadata"]


@dataclass
class ObjectMetadata:
    """Contagem e janela de timestamps de uma variação.

    Parameters
    ----------
    count : int, default 0
        Número de ocorrências.
    first_timestamp : int, default 0
        Menor timestamp visto. ``0`` é **sentinela de "não sei"**, não um
        instante — ver :meth:`combine_metadata`.
    last_timestamp : int, default 0
        Maior timestamp visto; mesma sentinela.

    Notes
    -----
    Os defaults em ``0`` replicam o construtor sem argumentos do Java
    (``ObjectMetadata.java:10-12``), que deixa os três campos no zero-value dos
    ``long``. É esse construtor que o ``infer`` usa para todo objeto **não-raiz**
    (``SchemaInference.java:198``), e é por isso que as entidades internas
    nascem zeradas e precisam do ``innerCountAndTimestampsAdjust`` depois.

    O objeto é **mutável** de propósito: o Java muta o ``meta`` no lugar
    (``combineMetadata`` altera ``this``), e 1.2/1.3a dependem disso.
    """

    count: int = 0
    first_timestamp: int = 0
    last_timestamp: int = 0

    def combine_metadata(self, orig: ObjectMetadata) -> None:
        """Absorver ``orig`` neste metadado, no lugar.

        Porte de ``ObjectMetadata.combineMetadata`` (``:50-60``).

        Parameters
        ----------
        orig : ObjectMetadata
            O metadado a absorver. Não é modificado.
        """
        self.count += orig.count

        if self.first_timestamp == 0 or orig.first_timestamp < self.first_timestamp:
            self.first_timestamp = orig.first_timestamp

        if self.last_timestamp == 0 or orig.last_timestamp > self.last_timestamp:
            self.last_timestamp = orig.last_timestamp
