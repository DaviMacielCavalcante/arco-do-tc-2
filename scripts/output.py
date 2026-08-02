"""Tabelas de resultado da Fase 3 — **um grão por arquivo**.

As baterias antes gravavam um CSV cada, misturando três granularidades no mesmo
arquivo: fatos da corrida (tempos, contagem de arquétipos) repetidos em cada
linha de entidade, e o veredito repetido em cada linha de divergência. Dava para
anexar linha a linha durante a corrida, mas obrigava a deduplicar na análise.

Aqui cada tabela tem um grão só, e todas se unem por ``corrida_id``:

===================  ======================================================
`corridas.csv`       uma linha por corrida — tempos e metadados
`entidades.csv`      uma linha por entidade medida — real contra modelo
`comparacoes.csv`    uma linha por confronto com um XMI de referência
`divergencias.csv`   uma linha por divergência
===================  ======================================================

Os nomes de coluna ficam em português, como o resto da evidência; os
identificadores do módulo seguem em inglês, como os demais scripts do diretório.
O módulo se chama `output` e não `results` porque o diretório de saída na raiz
é `results/`: um módulo homônimo vira namespace package e o mypy passa a
resolver o import para a pasta de dados.

Colunas derivadas **não** entram: `capturado` é `modelo / real` e é conta da
análise, não dado. Colunas que só um paradigma produz (`linhas_tripla` no
documento, `arquetipos` no grafo) ficam vazias no outro — fundi-las num nome só
esconderia que os dois não passam pelo mesmo núcleo de construção.
"""

import csv
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

RUNS = [
    "corrida_id",
    "bateria",
    "paradigma",
    "semente",
    "escala",
    "rota",
    "alvo",
    "origem",
    "t_limpeza",
    "t_geracao",
    "t_extracao",
    "t_inferencia",
    "t_oraculo",
    "linhas_tripla",
    "arquetipos",
]

ENTITIES = ["corrida_id", "entidade", "real", "modelo"]

COMPARISONS = ["corrida_id", "referencia", "equivalente", "n_divergencias"]

DIVERGENCES = ["corrida_id", "referencia", "categoria", "mensagem"]

TABLES = {
    "corridas": RUNS,
    "entidades": ENTITIES,
    "comparacoes": COMPARISONS,
    "divergencias": DIVERGENCES,
}


def run_id(
    battery: str,
    paradigm: str,
    target: str,
    seed: int | None = None,
    origin: str | None = None,
) -> str:
    """Montar o identificador determinístico de uma corrida.

    Determinístico de propósito: reconstruível a partir das colunas, sem
    depender da ordem das linhas. A bateria entra porque a mesma escala com a
    mesma semente é medida duas vezes — na bateria de escala e na cadeia do
    oráculo —, e são corridas distintas.

    Parameters
    ----------
    battery : str
        Quem produziu: ``escala``, ``oraculo`` ou ``corretude``.
    paradigm : str
        ``mongodb`` ou ``neo4j``.
    target : str
        Banco ou schema medido (``up_a_small``, ``movies_min``, ``northwind``).
    seed : int, optional
        Semente do gerador; ausente nos datasets que não são gerados.
    origin : str, optional
        ``arquivo`` ou ``banco``, quando o mesmo alvo é lido por mais de um
        caminho.

    Returns
    -------
    str
        Identificador com os campos presentes unidos por ``-``.

    Examples
    --------
    >>> run_id("escala", "mongodb", "up_a_small", seed=23)
    'escala-mongodb-up_a_small-23'
    >>> run_id("corretude", "mongodb", "northwind", origin="arquivo")
    'corretude-mongodb-northwind-arquivo'
    """
    parts = [battery, paradigm, target]

    if seed is not None:
        parts.append(str(seed))

    if origin is not None:
        parts.append(origin)

    return "-".join(parts)


def _check_header(path: Path, header: list[str]) -> bool:
    """Recusa append num CSV de esquema antigo; True se o arquivo é novo.

    Arquivo de zero byte conta como novo: não tem esquema com que conflitar, e é
    o que sobra de uma corrida interrompida antes do primeiro `flush`.
    """
    if not path.exists() or path.stat().st_size == 0:
        return True

    with open(path, newline="") as file:
        current = next(csv.reader(file), [])

    if current != header:
        raise SystemExit(
            f"{path} tem cabeçalho incompatível.\n"
            f"  esperado: {','.join(header)}\n"
            f"  achado:   {','.join(current)}\n"
            "Renomeie o arquivo antigo ou use outro diretório."
        )

    return False


class Results:
    """Escreve as quatro tabelas em append, num diretório.

    Abre os quatro arquivos de uma vez e mantém um ``DictWriter`` por tabela —
    estado real, daí ser classe. O `DictWriter` deixa cada bateria passar só as
    colunas que ela produz; o resto sai vazio, sem `None` espalhado no CSV.

    Cada linha é gravada com `flush` imediato: uma bateria de uma hora
    interrompida no meio preserva o que já mediu.

    Examples
    --------
    >>> with Results(Path("results")) as tables:  # doctest: +SKIP
    ...     tables.add_run({"corrida_id": "escala-neo4j-movies_min-23", ...})
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._files: dict[str, TextIO] = {}
        self._writers: dict[str, csv.DictWriter[str]] = {}

    def __enter__(self) -> "Results":
        """Abrir as quatro tabelas, escrevendo o cabeçalho nas que forem novas."""
        self.directory.mkdir(parents=True, exist_ok=True)

        for name, header in TABLES.items():
            path = self.directory / f"{name}.csv"

            is_new = _check_header(path, header)

            file = open(path, "a", newline="")
            writer = csv.DictWriter(file, fieldnames=header, restval="")

            if is_new:
                writer.writeheader()
                file.flush()

            self._files[name] = file
            self._writers[name] = writer

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Fechar os quatro arquivos."""
        for file in self._files.values():
            file.close()

    def _write(self, table: str, row: Mapping[str, Any]) -> None:
        """Gravar uma linha e descarregar no disco."""
        self._writers[table].writerow(row)
        self._files[table].flush()

    def add_run(self, row: Mapping[str, Any]) -> None:
        """Gravar a linha de uma corrida."""
        self._write("corridas", row)

    def add_entity(self, run: str, entity: str, actual: int, model: int) -> None:
        """Gravar o real contra o modelo de uma entidade."""
        self._write(
            "entidades",
            {"corrida_id": run, "entidade": entity, "real": actual, "modelo": model},
        )

    def add_comparison(self, run: str, reference: str, equivalent: bool, divergences: int) -> None:
        """Gravar o veredito de um confronto com um XMI de referência."""
        self._write(
            "comparacoes",
            {
                "corrida_id": run,
                "referencia": reference,
                "equivalente": equivalent,
                "n_divergencias": divergences,
            },
        )

    def add_divergence(self, run: str, reference: str, category: str, message: str) -> None:
        """Gravar uma divergência do relatório do harness."""
        self._write(
            "divergencias",
            {
                "corrida_id": run,
                "referencia": reference,
                "categoria": category,
                "mensagem": message,
            },
        )
