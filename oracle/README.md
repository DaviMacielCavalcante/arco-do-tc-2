# oracle/ — Java oracle in Docker (Phase 0.5)

**Reduced, optional role**: it is **not part of the deliverable** (the ported
tool is pure Python). It serves to (a) run the original extractor reproducibly,
without depending on the Eclipse IDE or any particular machine; and (b) generate
the reference XMI for datasets that have no ready golden-master (Sakila, size
variations). It adds **reproducibility**, not functionality.

Every design rationale, patch decision and known limitation lives in
**[`docker_explain.md`](docker_explain.md)** — this README keeps only the
essentials for using and building the image.

## Image contents

- Base `maven:3.9-eclipse-temurin-8` (JDK 8, required by Spark 3.0.1).
- Sources of `modelum/uschema` and `modelum/uschema-inference`, cloned at a
  pinned commit, with the `patches/` applied on top.
- A single Maven build (`oracle/uschema-build/runner`), no Eclipse — Mongo and
  Neo4j on the same classpath, Spark 3.0.1/Scala 2.12 for both (unified;
  detail/validation in `docker_explain.md`).
- No *fat jar*: it runs via `mvn exec:java -Dexec.mainClass=...`, offline after
  the build.

## Why an entrypoint is needed

The two Java `main`s do not accept `--db`/`--kind` directly — Mongo reads a
`config.properties` from the classpath, Neo4j has bolt/user/password fixed in the
code. `entrypoint.sh` translates `--db`/`--kind` (command-line arguments) and,
for Mongo, `MONGO_URL`/`MONGO_COLLECTIONS` (environment variables) into that
interface. Full detail in `docker_explain.md`.

## Usage

```bash
# MongoDB
docker run --network=host --memory=6g -v "$PWD/out:/output" \
  -e MONGO_URL=mongodb://localhost:27017 \
  -e MONGO_COLLECTIONS=customers,employees,orders,... \
  extrator-uschema --db northwind --kind mongodb

# Neo4j
docker run --network=host --memory=6g -v "$PWD/out:/output" \
  extrator-uschema --db movies_min --kind neo4j
```

> **The Neo4j `--db` is the name of the SCHEMA, not of the database to connect
> to.** Verified in `Neo4j2USchema.java` (pinned SHA): `databaseName` goes only
> to `Json2USchemaModel(databaseName)`; `SparkProcess` receives just
> `(samplingRatio, bolt, user, password)` and always reads the **default
> database**. Two consequences: (1) Neo4j **Community**, which has only one user
> database, is not an obstacle; (2) the value passed must **match the schema name
> the port uses** (`movies_min`, `up_medium`, `up_large`, `up_larger`) — a
> `SCHEMA_NAME` mismatch is **fatal** in the Phase 0.3 harness.
>
> **The Neo4j path has only been exercised on a minimal graph.** The 0.5
> checklist (below) marks it as tested end to end, but against a handful of nodes
> created with `cypher-shell` — never against the 100k–800k of the User Profiles
> sizes. It is volume, not the path, that remains unproven. The output should go
> to `out/oraculo/` (see `resources/README.md`, "Onde cada XMI mora").

`--network=host` because the container connects to a database **already running
and already populated** on the host — the oracle is an extractor, it packages no
data. `DATABASE_BOLT` is a constant (`bolt://localhost:7687`) in the original
source, so without `--network=host` the container would look for the database
inside itself. Preparing the database is a separate step, outside this
Dockerfile. Memory ≥ ~5–6 GB for the larger size datasets.

**Windows/Git Bash:** prefix the commands above with `MSYS_NO_PATHCONV=1`.
Without it, MSYS2 rewrites the `/output` side of `-v` as a Windows path — the
container runs and reports success, but the `.xmi` never appears in the host
folder (mount silently broken, with no error at all). Discovered by running it
for real — detail in `docker_explain.md`.

**Original JUnit suite** (baseline, manual command — does not go through
`entrypoint.sh`/`--db`/`--kind`):

```bash
docker run --rm --entrypoint sh extrator-uschema \
  -c "cd /app/uschema-build/runner && mvn -q -B -o test"
```

It needs neither `--network=host` nor `MONGO_URL`/`MONGO_COLLECTIONS` — the
covered tests connect to no database. Detail/coverage/result in
`docker_explain.md`, "Suíte JUnit original" section.

## Build

```bash
docker build -t extrator-uschema oracle/
```

The two upstream commits are pinned as the `ARG` default in the `Dockerfile` —
they are the SHAs this oracle was validated against (patches applying cleanly,
JUnit baseline 65/76, `northwind.xmi` equivalent to the reference):

| Repository | Pinned SHA |
|---|---|
| `modelum/uschema` | `6dfd6b4a6c04c67e49a80fb6cb6da9dd0f0f0f8c` |
| `modelum/uschema-inference` | `0f8f58c31f7661ce9be7333a1f34b9a05321a993` |

Building without `--build-arg` reproduces exactly the oracle cited in the thesis.
To advance the pin (deliberately, revalidating the set), override it:

```bash
docker build \
  --build-arg USCHEMA_COMMIT=<sha> \
  --build-arg USCHEMA_INFERENCE_COMMIT=<sha> \
  -t extrator-uschema oracle/
```

## Tasks (Phase 0.5)

- [x] `Dockerfile` + `entrypoint.sh` + `patches/` (patches #1/#4/#5/#6/#7
      verified, #2/#3 satisfied structurally, #8 deliberately left out —
      detail in `docker_explain.md`).
- [x] Run the real `docker build` and validate that the image builds.
- [x] Run the extraction inside the container against a real test database
      (Northwind, MongoDB) — `out/northwind.xmi` generated successfully.
- [x] Validate `out/northwind.xmi` against the reference
      `resources/mongodb/model_northwind.xmi` via `compare()`
      (`uschema.validation.equivalence`, Phase 0.3): `equivalent: True`, zero
      fatal divergences (the 8 non-fatal ones match the bug #8 signature,
      as expected). Detail in `docker_explain.md`.
- [x] Test the Neo4j path (`--kind neo4j`) end to end — minimal graph
      (User/Movie, `WATCHED`/`FAVORITE`) via `cypher-shell`, `neo4j.xmi`
      generated successfully.
- [x] Run the original JUnit suite inside the image — 65/76 pass; the 11
      that fail have an identified root cause and are pre-existing defects
      of the original repo (not of the packaging). Detail in `docker_explain.md`.
