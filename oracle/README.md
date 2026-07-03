# oracle/ — oráculo Java em Docker (Fase 0.5)

Papel **reduzido e opcional**: **não entra na entrega** (a ferramenta portada é
Python puro). Serve para (a) rodar a suíte JUnit existente e obter o *baseline
verde*; e (b) gerar o XMI-gabarito apenas para datasets **sem** golden-master
pronto (Sakila, variações de escala). Agrega **reprodutibilidade**, não
funcionalidade.

## Conteúdo da imagem

- Base **JDK 8** (Spark 2.4/3.0.1 não lê bytecode major > 52).
- Spark + conectores fixados: `mongo-spark-connector 3.0.1`,
  `neo4j-spark-connector 2.4.5-M2`.
- `uschema-inference` compilada **com os 8 patches aplicados no build**
  (ver `patches/`).

## Contrato

```bash
docker run --network=host --memory=6g \
  -v "$PWD/out:/output" extrator-uschema --db <nome> --kind <mongodb|neo4j>
# grava model.xmi em /output
```

`--network=host` (Linux) para alcançar bancos no host; memória ≥ ~5–6 GB.

## Tarefas (Fase 0.5)

- [ ] `Dockerfile` (JDK 8 + Spark + conectores + build com os 8 `.patch`).
- [ ] Rodar a suíte JUnit dentro da imagem → baseline verde + dados de teste.
- [ ] Validar que regenera `model_northwind.xmi` (e os XMIs de escala)
      estruturalmente idênticos.
- [ ] Versionar `Dockerfile` + `patches/` (artefato de reprodutibilidade do TCC).
