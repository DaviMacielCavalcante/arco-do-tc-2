# tests/datasets/ — golden-master por dataset (Fases 1.5 e 3)

Validação **ponta a ponta sem depender de Docker**: cada teste roda a inferência
sobre um dataset conhecido e compara o XMI resultante com o esperado, via
`uschema.validation.compare_uschemas`.

Portados do JUnit de dataset do repo: `UserProfileTest`, `EveryPoliticianTest`,
`CompaniesTest`, `FacebookTest`, `StackOverflowTest`, além do Northwind
(golden-master principal da Fase 1 e único dataset real da equivalência da
Fase 3 — o Sakila foi **descartado** em 02/08/2026, ver
`fase3_validacao_volume.md` §3.1).

Datasets **sem** golden-master pronto (as variações de volume) usam o oráculo em
Docker (`oracle/`) para gerar o gabarito.
