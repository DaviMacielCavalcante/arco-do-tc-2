# Oráculo Java do U-Schema (Fase 0.5) — gera XMIs de referência pra validar o
# porte Python. Opcional, não entra na entrega. Justificativas completas em
# oracle/docker_explain.md.

FROM maven:3.9-eclipse-temurin-8@sha256:b595d84453cef0567168b65c0566743114a6a47d2ad7e7a712a20cf4f4555fd4

# Commit pinado (não branch) por reprodutibilidade citável — ver
# docker_explain.md, "Commit pinado, não branch".
ARG USCHEMA_COMMIT
ARG USCHEMA_INFERENCE_COMMIT

RUN test -n "$USCHEMA_COMMIT" && test -n "$USCHEMA_INFERENCE_COMMIT" || \
    (echo "Build precisa de --build-arg USCHEMA_COMMIT=<sha> --build-arg USCHEMA_INFERENCE_COMMIT=<sha>" >&2 && exit 1)

RUN apt-get update \
 && apt-get install -y --no-install-recommends git patch \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- 1. Clona os fontes upstream, pinados ---
RUN git clone https://github.com/modelum/uschema.git uschema-src/uschema \
 && git -C uschema-src/uschema checkout "$USCHEMA_COMMIT"
RUN git clone https://github.com/modelum/uschema-inference.git uschema-src/uschema-inference \
 && git -C uschema-src/uschema-inference checkout "$USCHEMA_INFERENCE_COMMIT"

# --- 2. Aplica os patches (#1/#4/#5 build, #6/#7 crashes reais) ---
# #2/#3 não precisam de patch (pom original nunca é lido); #8 fica de fora
# de propósito. Detalhe completo: docker_explain.md, seção "Patches".
COPY patches/ /app/patches/
RUN cd uschema-src/uschema-inference \
 && patch -p1 < /app/patches/0001-mongo-guice-binding.patch \
 && patch -p1 < /app/patches/0004-path-of-to-paths-get-inference.patch \
 && patch -p1 < /app/patches/0005-neo4jmain-cli-arg-no-hardcode.patch \
 && patch -p1 < /app/patches/0006-helpers-generic-id.patch \
 && patch -p1 < /app/patches/0007-arraysc-empty-shortcircuit.patch
RUN cd uschema-src/uschema \
 && patch -p1 < /app/patches/0004-path-of-to-paths-get-uschema.patch

# --- 3. Build via um único projeto Maven "runner" (sem Eclipse) ---
# Substitui manualmente a resolução Require-Bundle do Eclipse. Por quê:
# docker_explain.md, "Maven puro (sem Eclipse)". Mongo e Neo4j num build só
# desde a unificação em Spark 3.0.1/Scala 2.12 — docker_explain.md,
# "Unificação mongo+neo4j num build único".
COPY uschema-build/ /app/uschema-build/

# Rede do build resolve dependências (Maven Central + Spark Packages pro
# neo4j-spark-connector); depois disso o container roda offline.
RUN cd uschema-build/runner && mvn -q -B dependency:go-offline

# Compila cedo, sem -o: go-offline é incompleto pra esse build agregado.
# Motivo: docker_explain.md, "dependency:go-offline incompleto".
RUN cd uschema-build/runner && mvn -q -B compile

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
