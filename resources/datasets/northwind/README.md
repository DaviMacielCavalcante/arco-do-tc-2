# Northwind (MongoDB) — dataset de entrada

Os 17 arquivos JSONL que alimentam o gate de equivalência do paradigma documento
(Fase 3.1). São **entrada** do porte, não saída: o XMI-oráculo correspondente é
`resources/mongodb/model_northwind.xmi`.

## Proveniência

| | |
|---|---|
| Origem | <https://github.com/jasny/mongodb-northwind> |
| Commit | `967bfec` (o único do repositório) |
| Autoria | Arnold Daniels, 2020 |
| Licença | **BSD 2-Clause** — ver `LICENSE`, copiado junto conforme exigido |
| SHA-256 do conjunto | `3700157bd0bcca944b5a869dbfdd2065ae180bc538ec1e816a94e0f86c7271ae` |

O digest cobre os 17 `.json` em ordem de nome (nome + conteúdo) e é impresso por
`scripts/run_northwind.py` a cada corrida — é o que prende um resultado a uma
versão do dataset.

É a versão MongoDB do banco de exemplo **Northwind** do Microsoft Access 2010,
derivada do [MyWind](https://github.com/dalers/mywind), que é a versão MySQL do
mesmo banco.

## Formato

JSONL — um documento por linha, em **extended JSON**
(`"order_date":{"$date":"2006-01-15T00:00:00Z"}`). A leitura tem de usar
`bson.json_util.loads`: com `json.load` puro o `$date` vira um objeto aninhado e
o modelo ganha uma entidade que o oráculo não tem.

## Por que estes dados importam para a fase

As transformações relacional → documento são **do repositório de origem**, não
do U-Schema, e são exatamente o que a Fase 3.1 mede:

- `_id` é a chave primária de todas as coleções
- `order_details` embutido como `details` em `orders`
- `purchase_order_details` embutido como `details` em `purchase_order`
- `products.supplier_ids` é lista de `int`

A entidade não-raiz `Detail` do invariante **19 `EntityType` / 17 raiz** nasce
do embutimento de `details`.

## Como usar

```bash
uv run python scripts/run_northwind.py                    # lê daqui, sem banco
uv run python scripts/check_northwind_invariants.py       # invariantes do XMI
```

Para carregar num MongoDB local, o repositório de origem traz um
`mongo-import.sh`; o equivalente direto é um `mongoimport` por arquivo, usando o
nome do arquivo como nome da coleção.
