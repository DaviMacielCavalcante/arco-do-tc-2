#!/usr/bin/env bash
# Encadeia TODAS as baterias da Fase 3, numa semente, SEQUENCIALMENTE.
#
# Substitui o `run_scale_suite.sh`, que orquestrava só as duas baterias de
# tamanho e existia para varrer três sementes. Com a semente única (padrão nos
# scripts, sobrescrevível), o que restava a orquestrar era a cadeia inteira —
# que é o que este script faz.
#
# Ordem: Northwind, cadeia do oráculo (documento e grafo) e as duas baterias de
# tamanho. É a ordem em que as evidências dependem umas das outras: o Northwind
# não precisa de dado gerado, e a cadeia do oráculo deixa os bancos no estado
# que o tamanho vai sobrescrever de qualquer forma.
#
# Por que sequencial: os dois clientes Python não disputam entre si, mas o
# mongod e o Neo4j disputam CPU e disco. Os tempos medidos aqui vão para a
# avaliação — medi-los sob carga variável do outro paradigma invalidaria a
# comparação de curvas, que é o objeto da fase.
#
# DESTRUTIVO: começa esvaziando os bancos das baterias (`up_*` no MongoDB e o
# grafo do Neo4j) e depois cada corrida dropa e regera o seu. Com a semente no
# `run_id`, o dado é reconstruível — é para isso que a semente existe.
# O `northwind` NÃO é tocado (ver scripts/clean_databases.py).
#
# Uso:
#   ./scripts/run_suite.sh              # semente padrão dos scripts (23)
#   ./scripts/run_suite.sh 69           # outra semente
#   nohup ./scripts/run_suite.sh > /dev/null 2>&1 &   # e ir dormir
#
# Pré-requisitos: mongod e neo4j ativos, imagem do oráculo buildada.
#   systemctl is-active mongod neo4j
#   docker image inspect extrator-uschema > /dev/null
# Lembrete: o mongod não sobe em kernel >= 6.19 (guarda do rseq) — ver
# `todolist_fase3.md`, riscos da fase.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ $# -gt 1 ]; then
    echo "erro: no máximo uma semente" >&2
    echo "  uso: $0 [semente]" >&2
    exit 2
fi

# Sem argumento, o `--seed` nem é passado: vale o DEFAULT_SEED de cada script,
# que é onde a semente padrão mora. Duplicá-la aqui abriria espaço para as duas
# divergirem.
SEED_ARGS=()
SEED_LABEL="padrão dos scripts"
if [ $# -eq 1 ]; then
    SEED_ARGS=(--seed "$1")
    SEED_LABEL="$1"
fi

# As baterias gravam em APPEND. Rodar duas vezes a mesma semente não sobrescreve
# nada — duplica, e a duplicata só aparece depois, num `uniq -d`. Já custou uma
# sessão inteira; a guarda é barata.
if [ -s results/runs.csv ]; then
    SEED_CHECK="${1:-23}"
    if grep -qE "^[^,]*-${SEED_CHECK}," results/runs.csv; then
        echo "erro: results/runs.csv já tem corridas da semente ${SEED_CHECK}." >&2
        echo "  Arquive o diretório antes de repetir:" >&2
        echo "    mv results results_\$(date +%d-%m)" >&2
        exit 3
    fi
fi

mkdir -p results logs
LOG="logs/baterias_$(date +%Y%m%d_%H%M%S).log"

echo "semente  : ${SEED_LABEL}" | tee -a "$LOG"
echo "log      : $LOG" | tee -a "$LOG"
echo "início   : $(date --iso-8601=seconds)" | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "########## limpeza inicial  $(date +%H:%M:%S) ##########" | tee -a "$LOG"
uv run python scripts/clean_databases.py 2>&1 | tee -a "$LOG"

# O Northwind não leva `--seed`: o dataset é real e versionado, não se regenera.
echo "" | tee -a "$LOG"
echo "########## northwind  $(date +%H:%M:%S) ##########" | tee -a "$LOG"
# `tee` sem pipefail mascararia a falha; o `set -o pipefail` acima evita.
uv run python scripts/run_northwind.py 2>&1 | tee -a "$LOG"

for bateria in run_oracle_mongo run_oracle_neo4j run_size_mongo run_size_neo4j; do
    echo "" | tee -a "$LOG"
    echo "########## ${bateria}  $(date +%H:%M:%S) ##########" | tee -a "$LOG"
    uv run python "scripts/${bateria}.py" "${SEED_ARGS[@]}" 2>&1 | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "fim      : $(date --iso-8601=seconds)" | tee -a "$LOG"
echo "tabelas  : results/{runs,oracle,comparisons,divergences}.csv" | tee -a "$LOG"
