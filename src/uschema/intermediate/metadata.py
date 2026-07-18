"""Metadados de ocorrência de uma variação estrutural (Fase 1.1).

Porte de ``ObjectMetadata.java``. Carrega o que a tripla trouxe — quantas
ocorrências e a janela de tempo — e sabe **combinar** duas dessas janelas, que é
a operação no centro da correção do bug **#8**.

Por que ``combine_metadata`` é load-bearing
-------------------------------------------
O ``SchemaInference``, ao reencontrar uma variação estruturalmente igual a uma já
vista, faz ``retSchema = foundSchema.get()`` e **descarta o ``meta`` da nova**
(``SchemaInference.java:204-212``) — a contagem daquela tripla simplesmente
some. É o bug #8. A correção do porte é combinar em vez de descartar, e é este
módulo que fornece a operação.

Ele dispara quando ``ArraySC.__eq__`` colapsa duas triplas de **tamanho de array
diferente** (a igualdade que ignora o tamanho, ``ArraySC.java:82-101``) — a única
forma de duas triplas distintas do map-reduce virarem "iguais".
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
