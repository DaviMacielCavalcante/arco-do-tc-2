#!/usr/bin/env bash
# Traduz --db/--kind (CLI args) pros dois `main` Java, que não aceitam isso
# direto. Por quê: docker_explain.md, "Por que precisa de entrypoint.sh".
set -euo pipefail

KIND=""
DB_NAME=""
OUTPUT_DIR="${OUTPUT_DIR:-/output}"

usage() {
  cat >&2 <<'USAGE'
Uso:
  docker run --network=host -v "$PWD/out:/output" \
    -e MONGO_URL=mongodb://localhost:27017 -e MONGO_COLLECTIONS=col1,col2,... \
    extrator-uschema --db <nome> --kind mongodb

  docker run --network=host -v "$PWD/out:/output" \
    extrator-uschema --db <nome> --kind neo4j

Argumentos:
  --db <nome>        (obrigatório) nome do banco/database a extrair
  --kind <tipo>       (obrigatório) mongodb | neo4j

Variáveis de ambiente:
  OUTPUT_DIR (opcional, default /output) onde o .xmi final é copiado

  MongoDB apenas (não viram flag — MONGO_COLLECTIONS é lista, MONGO_URL pode
  ter credenciais; ficam de fora do argv por isso):
    MONGO_URL         (obrigatória) ex.: mongodb://localhost:27017
    MONGO_COLLECTIONS (obrigatória) lista separada por vírgula, sem espaço

  Neo4j: usa bolt://localhost:7687, usuário "neo4j", senha "test" — fixos no
  código original. Detalhe: oracle/docker_explain.md, "Limitações conhecidas".
USAGE
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --db)   [ $# -ge 2 ] || usage; DB_NAME="$2"; shift 2 ;;
    --kind) [ $# -ge 2 ] || usage; KIND="$2"; shift 2 ;;
    *) echo "Argumento desconhecido: $1" >&2; usage ;;
  esac
done

[ -n "$KIND" ] || usage
[ -n "$DB_NAME" ] || usage

case "$DB_NAME" in
  *[$'\n\r/\\']*)
    echo "--db: nome de banco inválido (sem barra nem quebra de linha)" >&2
    exit 1
    ;;
esac

mkdir -p "$OUTPUT_DIR"

# Build único desde a unificação mongo+neo4j (Spark 3.0.1/Scala 2.12 pros
# dois) — antes eram dois RUNNERs separados. Detalhe: docker_explain.md,
# "Unificação mongo+neo4j num build único".
RUNNER=/app/uschema-build/runner

case "$KIND" in
  mongodb)
    : "${MONGO_URL:?defina MONGO_URL, ex.: mongodb://localhost:27017}"
    : "${MONGO_COLLECTIONS:?defina MONGO_COLLECTIONS, lista separada por vírgula}"

    mkdir -p "$RUNNER/target/classes"
    cat > "$RUNNER/target/classes/config.properties" <<PROPS
MONGO_URL=${MONGO_URL}
MONGO_DATABASE=${DB_NAME}
MONGO_COLLECTIONS=${MONGO_COLLECTIONS}
PROPS

    # O writer Mongo não cria essa pasta sozinho (diferente do Neo4j) — ver
    # docker_explain.md, "Pasta outputs/ ausente no caminho Mongo".
    mkdir -p "$RUNNER/outputs"

    ( cd "$RUNNER" && mvn -q -B -o exec:java -Dexec.mainClass=es.um.uschema.mongodb2uschema.main.MongoDB2USchemaMain )
    cp "$RUNNER/outputs/model.xmi" "$OUTPUT_DIR/${DB_NAME}.xmi"
    ;;

  neo4j)
    ( cd "$RUNNER" && mvn -q -B -o exec:java -Dexec.mainClass=es.um.uschema.neo4j2uschema.main.Neo4j2USchemaMain -Dexec.args="$DB_NAME" )
    cp "$RUNNER/outputs/${DB_NAME}.xmi" "$OUTPUT_DIR/${DB_NAME}.xmi"
    ;;

  *)
    echo "--kind inválido: '$KIND' (use mongodb ou neo4j)" >&2
    usage
    ;;
esac

echo "XMI gerado em $OUTPUT_DIR/${DB_NAME}.xmi"
