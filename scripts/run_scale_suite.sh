#!/usr/bin/env bash
# Encadeia as baterias de escala da Fase 3.2 para N sementes, SEQUENCIALMENTE.
#
# Por que sequencial: os dois clientes Python não disputam entre si, mas o
# mongod e o Neo4j disputam CPU e disco. Os tempos medidos aqui vão para o
# capítulo de avaliação — medi-los sob carga variável do outro paradigma
# invalidaria a comparação de curvas, que é o objeto da fase.
#
# DESTRUTIVO: começa esvaziando os bancos das baterias (`up_*` no MongoDB e
# o grafo do Neo4j) e depois cada corrida dropa e regera o seu. Com a semente
# no CSV, o dado é reconstruível — é para isso que a semente existe.
# O `northwind` NÃO é tocado (ver scripts/clean_databases.py).
#
# Uso:
#   ./scripts/run_scale_suite.sh                 # sementes padrão: 23 69 207
#   ./scripts/run_scale_suite.sh 11 22 33        # exatamente 3 sementes
#   nohup ./scripts/run_scale_suite.sh > /dev/null 2>&1 &   # e ir dormir
#
# Pré-requisitos: mongod e neo4j ativos.
#   systemctl is-active mongod neo4j
# Lembrete: o mongod não sobe em kernel >= 6.19 com MongoDB 8.0.28 — ver
# `todolist_fase3.md`, riscos da fase.

set -euo pipefail

cd "$(dirname "$0")/.."

DEFAULT_SEEDS=(23 69 207)

if [ $# -eq 0 ]; then
    SEEDS=("${DEFAULT_SEEDS[@]}")
elif [ $# -eq 3 ]; then
    SEEDS=("$@")
else
    echo "erro: forneça exatamente 3 sementes, ou nenhuma para usar as padrão" >&2
    echo "  padrão : ${DEFAULT_SEEDS[*]}" >&2
    echo "  recebido: $# argumento(s) — $*" >&2
    exit 2
fi

mkdir -p resultados logs
LOG="logs/baterias_$(date +%Y%m%d_%H%M%S).log"

echo "sementes : ${SEEDS[*]}" | tee -a "$LOG"
echo "log      : $LOG" | tee -a "$LOG"
echo "início   : $(date --iso-8601=seconds)" | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "########## limpeza inicial  $(date +%H:%M:%S) ##########" | tee -a "$LOG"
uv run python scripts/clean_databases.py 2>&1 | tee -a "$LOG"

for seed in "${SEEDS[@]}"; do
    for suite in mongo neo4j; do
        echo "" | tee -a "$LOG"
        echo "########## seed=$seed  suite=$suite  $(date +%H:%M:%S) ##########" | tee -a "$LOG"
        # `tee` sem pipefail mascararia a falha; o `set -o pipefail` acima evita.
        uv run python "scripts/run_scale_${suite}.py" --seed "$seed" 2>&1 | tee -a "$LOG"
    done
done

echo "" | tee -a "$LOG"
echo "fim      : $(date --iso-8601=seconds)" | tee -a "$LOG"
echo "CSVs     : resultados/escala_mongo.csv resultados/escala_neo4j.csv" | tee -a "$LOG"
