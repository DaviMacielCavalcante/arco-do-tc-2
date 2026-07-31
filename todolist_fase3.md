# TO-DO — Fase 3: ponta a ponta + escala + correções por construção

**Projeto:** Porte fiel e completo do U-Schema (Java/Spark/EMF) → Python — MongoDB e Neo4j
**Autores:** Davi Cavalcante · João — CESUPA
**Base:** `fase3_validacao_escala.md` · **Harness:** `validation/equivalence.py::compare` (Fase 0.3) · **Bugs:** `bugs_originais.md`
**Pré-requisito:** Fases 0, 1 e 2 ✅ (gates fechados; Northwind e os 4 XMIs Neo4j equivalentes ao oráculo)

> **Organização por entrega.** Tarefas agrupadas por **entregável** (3.0–3.4),
> não por autor. Cada bloco define uma **Saída** que serve de critério de
> "pronto".
>
> **Ideia central.** Esta fase não porta mais nada — ela **mede**. O produto é
> evidência: CSVs, curvas e tabelas que sustentam o capítulo de avaliação
> experimental do TCC. O código que entra é de **bateria** (orquestração,
> cronometragem, coleta), não de inferência.
>
> ⚠️ **Abrir o `.java` antes de afirmar** continua valendo (`~/Documents/GitHub/uschema{,-inference}`,
> commits pinados no `oracle/Dockerfile`). Mas o risco desta fase é outro:
> **afirmar número que não foi medido.** Todo valor do capítulo tem de sair de
> uma corrida registrada, não de um `.md` anterior.

---

## ⚠️ Correção da spec (já aplicada): **não há número-alvo "com a correção do #8"**

`fase3_validacao_escala.md` §3.3 listava o **#8** ao lado do #6/#7 como
"corrigido por construção" e fixava alvos *com a correção* (50/50 no User
Profiles; 17/17 no Northwind). **Contradizia a decisão de fidelidade do
projeto** — corrigido em 31/07/2026 no guia e em `scripts/README.md`.

Verificado:

- `bugs_originais.md` §#8 — **"Decisão no porte: replicar."** `combine_metadata` não é chamado no ponto de colapso, de propósito.
- `oracle/patches/` tem `0001`, `0004`(×2), `0005`, `0006`, `0007` — **não existe `0008`**. O oráculo também não corrige.
- `todolist_fase2.md` §2.3 — o Northwind fecha com `equivalent=True` e **15 divergências não-fatais**, justamente a assinatura do #8 nos dois lados.

**Regra da fase:** o critério é **casar com o oráculo**, não com o volume real.
O porte reproduz a subcontagem; a Fase 3 a **mede e documenta**, não a corrige.
Um resultado que "acertasse" o volume real no paradigma documento estaria
**fora** do gate.

O 50/50 e o 17/17 são resultados do experimento **original**, citáveis como
contexto do que o bug custa — nunca como alvo. Medir a correção exigiria uma
variante corrigida do pipeline, que **não entra nesta fase**.

---

## ⚠️ Achado: a maior lacuna herdada é o **Neo4j ponta a ponta** — e ela é fechável sem Docker

A 2.2 fechou com `compare()` zerado nos 4 XMIs, mas o teste
(`tests/datasets/test_movies_min_golden_master.py`, docstring) valida **só a
camada de construção**: os arquétipos foram **reconstruídos lendo a estrutura do
próprio XMI-oráculo**, não extraídos de um Neo4j real. A cadeia
`Neo4j real → extract → build → compare` nunca encontrou o oráculo.

**Isso é fechável agora**, e a Fase 2 até deixou as peças:

- `scripts/gen_userprofiles_neo4j.py` — o gerador **original** do dataset, localizado no clone Java e trazido pro repo.
- Os **4 XMIs-oráculo** estão versionados em `resources/neo4j/`.

**Verificado hoje** (contagens lidas dos próprios XMIs) — os quatro são o mesmo
dataset em escalas que **dobram exatamente**:

| XMI | `User` (soma das 5 variações) | `Movie` | Escala |
|---|---|---|---|
| `movies_min.xmi` | **100.000** | 50.000 | Small |
| `up_medium.xmi` | **200.000** | 100.000 | Medium |
| `up_large.xmi` | **400.000** | 200.000 | Large |
| `up_larger.xmi` | **800.000** | 400.000 | Larger |

Dois corolários:

1. **`movies_min.xmi` não é um "modelo mínimo"** — é o User Profiles **Small**. `resources/README.md` o descreve errado e nem lista os `up_*.xmi`. Corrigir.
2. **A soma dos `count` de `User` já bate o volume gerado no próprio oráculo** (o caminho grafo tem núcleo próprio, o #8 não passa por ele). Ou seja: a bateria de escala do grafo e o gate de corretude do grafo são **a mesma corrida**.

---

## Cadeia de desbloqueio

```text
Fases 1+2 ✅ ─→ 3.0 (infra de bateria: cronometragem + coleta) ─┬─→ 3.1 corretude ─┬─→ 3.4 análise
                                                                ├─→ 3.2 escala ────┤
                                                                └─→ 3.3 bugs ──────┘
```

| Etapa | Depende de | Libera | Bloqueio conhecido |
|---|---|---|---|
| **3.0** infra de bateria | — | 3.1, 3.2, 3.3 | nenhum |
| **3.1** corretude | 3.0 | 3.4 | Sakila: dataset não está no repo |
| **3.2** escala | 3.0 | 3.4 | `gen_userprofiles.py` (Mongo) não foi trazido |
| **3.3** bugs | 3.0, 3.2 | 3.4 | nenhum — o #8 é medido, não corrigido (acima) |
| **3.4** análise | 3.1–3.3 | capítulo | formato dos CSVs a redefinir (doc ausente) |

---

## 3.0 — Infra de bateria (não estava no guia)

> O guia assume "ler o tempo de inferência do log do Spark". **Não existe log
> de executor** — a 2.0 decidiu driver nativo, pura-Python. A medição tem de
> ser em processo.

- [ ] **Cronometragem em processo**, separando as duas metades que o artigo trata como uma: **extração** (I/O do driver) e **inferência+construção** (`BuildUSchema` / `build_uschema_from_archetypes`). O oráculo mede o pipeline Spark inteiro; registrar o que está sendo comparado com o quê.
- [ ] **Entry-point das baterias.** ⚠️ **Recomendação: um script por bateria em `scripts/`, com `argparse`, no mesmo padrão dos `verificar_extracao_*.py`** — e **não** criar `cli.py`/`[project.scripts]` agora. Motivo: a entrega do TCC é a equivalência demonstrada, não uma ferramenta de linha de comando; um CLI genérico adiciona superfície (subcomandos, validação de config, testes) que nenhuma tarefa desta fase exige. A dívida do `cli.py` fica registrada no `CLAUDE.md`, sem dono.
- [ ] **Formato de saída fixado antes da primeira corrida**: um CSV de escala (`dataset,paradigma,rota,tamanho,t_extracao,t_inferencia,soma_counts,volume_gerado,pico_memoria`) e um de equivalência (`dataset,paradigma,equivalente,n_divergencias,categoria,mensagem`). ⚠️ `roteiro_experimental.md` §6–7 — que definia esse formato — **não existe neste repositório** (nem em nenhum outro no disco); ou o documento é recuperado, ou o formato é redefinido aqui e vira a referência.
- [ ] Artefatos versionados: CSVs em `resultados/`, XMIs gerados **fora** do git (são grandes e reprodutíveis).
- [ ] Decidir a máquina de referência e registrá-la (o baseline do artigo é um i9; comparar **tendência**, nunca tempo absoluto).

**Saída:** script(s) de bateria com medição em processo e esquema de CSV congelado.

---

## 3.1 — Corretude (datasets reais)

### Northwind — ✅ herdado da 2.3, falta reprodutibilidade

- [x] `compare()` contra `model_northwind.xmi`: **`equivalent=True`, 15 divergências não-fatais** (todas na assinatura do #8), reconfirmado via `MongoClient` real. Ver `todolist_fase2.md` §2.3.
- [ ] **Reprodutibilidade.** Hoje o resultado é prosa: os JSONs não foram vendorizados (decisão registrada), então nada trava esse número em CI. Os dados estão em `~/Documents/GitHub/mongodb-northwind` (2,1 MB, 17 arquivos). ⚠️ **Recomendação: vendorizar** — 2,1 MB é barato perto de um número que sustenta o gate da fase, e sem isso o capítulo cita um resultado que ninguém re-executa. Se a decisão de não vendorizar for mantida, então **um script de carga** (`scripts/carregar_northwind.py`) com o SHA dos arquivos é o mínimo.
- [ ] Confirmar os invariantes que o guia lista: **19 `EntityType`** (17 raiz + `_id` + `Detail`), `Detail` ligada a `Orders`/`Purchase_orders` por `Aggregate` (`upperBound="-1"`, `optional="true"`).

### Neo4j / User Profiles — a lacuna real (ver o achado acima)

- [ ] Regenerar o dataset com `scripts/gen_userprofiles_neo4j.py` nas 4 escalas e carregar num Neo4j.
- [ ] Rodar a cadeia **real**: `extractors/neo4j.py::extract_database_archetype_counts` → `extractors/neo4j_model.py::build_uschema_from_archetypes` → `compare()` contra `movies_min`/`up_medium`/`up_large`/`up_larger.xmi`.
- [ ] **Isto é o que a 2.2 não fez** — lá os arquétipos vieram do próprio XMI. Aqui vêm do banco. É o primeiro teste de verdade da camada de **extração** do grafo contra o oráculo.
- [ ] ⚠️ **Esperar divergência em `N1`**: `node_archetype` ordena os labels próprios, `_relationship_archetype` não ordena `refsTo` (`bugs_originais.md` N1) — nenhum nó dos datasets-oráculo é multi-label, então o caso nunca apareceu. Se o gerador produzir multi-label, aparece aqui pela primeira vez. Não "corrigir" sem antes confirmar no `.java`.

### Sakila — segundo ponto de corretude, nada existe

- [ ] Obter o dataset (documento e/ou grafo). **É o único bloqueio externo da fase.**
- [ ] Gerar o XMI-oráculo pelo Docker: `oracle/entrypoint.sh --db <nome> --kind mongodb|neo4j`, com `MONGO_URL`/`MONGO_COLLECTIONS` no ambiente. O caminho está provado (Fase 0.5 regenera os XMIs de forma reproduzível).
- [ ] Rodar o porte e comparar. Objetivo declarado: reduzir *overfitting* ao Northwind — uma divergência **nova** aqui vale mais que a confirmação do que já se sabe.

**Saída:** CSV de equivalência cobrindo Northwind, User Profiles (4 escalas, grafo) e Sakila, com toda divergência fatal explicada por bug catalogado.

---

## 3.2 — Escala (datasets sintéticos)

- [ ] **Trazer `scripts/gen_userprofiles.py`** (MongoDB, Rotas A/B) do repositório original — `scripts/README.md` marca "ainda não trazido". **Bloqueia toda a bateria do paradigma documento.**
- [ ] Gerar os 4 tamanhos: **100k/200k/400k/800k `User`** (50k/100k/200k/400k `Movie`).
  - **Rota A**: `_id` ObjectId nativo.
  - **Rota B**: `_id` **inteiro** + ~15% arrays vazios (cenário relacional→NoSQL; é o que exercita #6 e #7).
- [ ] Rodar Mongo (A e B) e grafo nos 4 tamanhos, coletando o CSV da 3.0.
- [ ] **Leitura integral**: soma dos `count` == volume gerado. ⚠️ No paradigma **documento** isso **não vai fechar, e não deve** — é exatamente o #8, replicado (ver 3.3). No **grafo** fecha (núcleo próprio; verificado nos 4 XMIs-oráculo).
- [ ] Comparar a **tendência** de crescimento com a do oráculo, não o tempo absoluto. Referência i9 (ferramenta original): Mongo Rota A ~0,47→4,09 s; Rota B ~0,43→3,48 s; Neo4j inferência ~3,83→34,86 s.
- [ ] Registrar que a **geração** do grafo (~180 s no maior) custa mais que a inferência — assimetria do paradigma, é resultado, não problema.
- [ ] Sem `OutOfMemoryError` / `MemoryError`. ⚠️ **Risco novo do porte:** sendo pura-Python, os 800k passam por estruturas em memória do processo, não por executores Spark — o perfil de memória é **diferente** do oráculo. Se estourar, `mapPartitions` entra sem reescrever a lógica (o `reduce_pairs` é comutativo e associativo, provado na 2.0) — e aí os testes novos levam `@pytest.mark.spark`, fechando o item pendente da 2.0.

**Saída:** CSV de escala completo (3 baterias × 4 tamanhos) + a curva tempo × volume, porte vs. oráculo.

---

## 3.3 — Bugs: #6/#7 por construção, #8 replicado

| Bug | No oráculo | No porte | O que a fase mede |
|---|---|---|---|
| **#6** `_id` inteiro | corrigido por **patch** (`0006`) | corrigido **por construção** | roda os 800k da Rota B sem `ClassCastException`/`TypeError` |
| **#7** array vazio | corrigido por **patch** (`0007`) | corrigido **por construção** | roda os ~15% de `[]` sem `IndexError` |
| **#8** subcontagem | **não corrigido** (não há patch `0008`) | **replicado fielmente** | a subcontagem do porte casa com a do oráculo |

- [ ] **#6/#7 — a afirmação do TCC é sobre o mecanismo, não o resultado.** Os dois lados chegam ao mesmo modelo; o que muda é que o original precisou de patch e o porte não. Medir: a Rota B (800k) roda ponta a ponta no porte **sem nenhum patch**.
- [ ] Testes de regressão com dataset mínimo dedicado para #6, #7 e #8. ⚠️ Os três já têm cobertura unitária (`test_objectid.py` para #6, `test_builder.py` para #7, `test_schema_inference.py` para #8) — o que falta aqui é a confirmação **em escala**, não o teste unitário de novo.
- [ ] **#8 — medir e documentar a subcontagem** nos 4 tamanhos (Rotas A/B) e no Northwind, mostrando que é **a mesma** do oráculo. É resultado, não falha.
- [ ] ⚠️ **Não "consertar" o #8 no meio da bateria.** Se algum número do paradigma documento fechar com o volume real, isso é sinal de que o porte **divergiu** do oráculo — investigar como regressão, não comemorar.

**Saída:** tabela de contagens por bug, com #6/#7 rodando sem patch em escala e a subcontagem do #8 medida e casada com a do oráculo.

---

## 3.4 — Coleta e análise

- [ ] Consolidar os CSVs (equivalência + escala) no formato fixado na 3.0.
- [ ] Visualizações: tabela de equivalência por dataset/paradigma; curva tempo × volume (porte vs. oráculo); tabela de contagens por bug (o que o porte corrige por construção × o que replica).
- [ ] Redigir o capítulo de avaliação: **corretude** (equivalência estrutural), **escala** (tendência preservada), **correções por construção** (#6/#7 sem patch; #8 medido dos dois lados).
- [ ] ⚠️ Declarar as **limitações** com a mesma honestidade das fases anteriores: o Northwind não está travado em CI se não for vendorizado; o `$numberLong` não tem fixture-oráculo (nenhum dataset de referência tem campo `long`); a comparação é estrutural, não byte a byte.

**Saída:** material do capítulo de avaliação experimental, com todo número rastreável a uma corrida registrada.

---

## Housekeeping (dívidas que a fase encosta)

- [ ] `resources/README.md` — descreve `movies_min.xmi` como "modelo mínimo Neo4j" (é o User Profiles **Small**, 100.000 `User`) e não lista `up_medium`/`up_large`/`up_larger.xmi`.
- [ ] `cli.py` + `[project.scripts]` — previstos na 1.7, que fechou sem eles. Registrado no `CLAUDE.md`; a 3.0 recomenda **não** criar agora.
- [ ] Documentos referenciados pelos quatro guias de fase e ausentes do repo: `roteiro_experimental.md`, `resultado_mongodb.md`, `resultado_neo4j.md`, `resultado_bug8_subcontagem_user.md`, `analise_ferramenta_uschema.md`. Recuperar ou remover as referências penduradas.

---

## Gate de aceite da Fase 3

- [ ] **Corretude:** Northwind, User Profiles (grafo, 4 escalas, cadeia real) e Sakila estruturalmente equivalentes ao oráculo; toda divergência fatal explicada por bug catalogado.
- [ ] **Escala:** tendência de crescimento reproduzida nos 4 tamanhos nas 3 baterias; leitura integral confirmada onde ela é esperada (grafo) e a subcontagem **explicada** onde não é (documento, #8); sem estouro de memória.
- [ ] **Bugs:** #6/#7 rodando sem patch em 800k; #8 medido e casando com a subcontagem do oráculo. Um número que "acertasse" o volume real no paradigma documento estaria **fora** do gate.
- [ ] **Rastreabilidade:** todo número do capítulo sai de uma corrida registrada em CSV.

## Entregáveis

`scripts/` (geradores + baterias de corretude e escala), `resultados/` (CSVs), os gráficos, e o material do capítulo de avaliação experimental.

## Riscos da fase

- **Afirmar número não medido** — o risco dominante; os `.md` anteriores citam valores do experimento original, não do porte.
- **Alvo do #8 conflitante com a fidelidade** (achado do topo) — se passar batido, ou o gate de equivalência quebra ou o capítulo publica um número que o porte não produz.
- **Memória em pura-Python** nos 800k — perfil diferente do Spark; `mapPartitions` é a saída, não a reescrita.
- **Sakila indisponível** — único bloqueio externo; sem ele a corretude fica com um único dataset de documento e o *overfitting* ao Northwind não é descartado.
- **`N1` aparecendo pela primeira vez** na extração real do grafo (nós multi-label) — diagnosticar pelo `.java`, não pelo sintoma.
- **Custo de geração do grafo** dominando a bateria (~180 s no maior) — planejar a janela; é da materialização, não da inferência.
