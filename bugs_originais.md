# Defeitos herdados do U-Schema original

Catálogo dos defeitos encontrados na implementação Java de referência
([`modelum/uschema-inference`](https://github.com/modelum/uschema-inference) e
[`modelum/uschema`](https://github.com/modelum/uschema)) durante o porte para
Python.

**Por que existe.** O porte é *fiel*: reproduz o comportamento do oráculo, não o
comportamento ideal. Quando o oráculo erra, o porte precisa decidir — replicar,
corrigir, ou corrigir e documentar. Este arquivo registra cada decisão com
evidência, para que o capítulo de reprodutibilidade do TCC possa citá-la e para
que, **depois de concluído o porte**, seja possível propor correções upstream.

**Como ler.** Duas famílias, com numeração independente:

- **`#1`–`#8`** — a série de *patches do oráculo* (`oracle/patches/`), já
  estabelecida no projeto. `#1`–`#5` são compatibilidade de build; `#6`–`#8` são
  defeitos semânticos.
- **`C1`–`C7`** — achados **novos**, na árvore de comparadores
  (`es.um.uschema.utils/.../custom/compare/`), levantados ao portar o harness de
  equivalência (Fase 0.3). Não existiam catalogados.
- **`I1`–`I3`** — achados **novos**, no `Inflector` (`.../util/inflector/`),
  levantados ao portar a normalização de nomes (Fase 0.6). O `Inflector` é código
  vendorizado do **ModeShape**, então os defeitos são *upstream do upstream*.

Todas as citações de linha referem-se ao `HEAD` do upstream, salvo indicação em
contrário.

---

## Sumário

| Id | Sítio | Natureza | Severidade | Estado no porte |
|---|---|---|---|---|
| #1 | `MongoDB2USchemaMain` | binding Guice ausente | build | patch no oráculo |
| #2 | `pom.xml` (doc2uschema) | versão de Jackson | build | patch no oráculo |
| #3 | runtime | JDK 8 (bytecode do Spark) | build | patch no oráculo |
| #4 | `MongoDB2USchema` et al. | `Path.of` → `Paths.get` | build | patch no oráculo |
| #5 | `Neo4j2USchemaMain` | hardcode/caminho Hadoop | build | patch no oráculo |
| **#6** | `Helpers.java:66` | `_id` assumido `ObjectId` | **crash** | corrigido por construção |
| **#7** | `USchemaModelBuilder.java:255` | array vazio indexado | **crash** | corrigido por construção |
| **#8** | `SchemaInference.java:209` | `meta` descartado no colapso | **corretude** | corrigido por construção |
| **C1** | `CompareReference.java:38-41` | só compara `isFeaturedBy[0]` | corretude | replicado (fiel) |
| **C2** | `CompareReference.java:27` | recursão de `opposite` sem guarda | crash latente | replicado (fiel) |
| **C3** | `CompareSchemaType.java:95-96` | `compareNames` sem guarda de nulo | crash latente | replicado (fiel) |
| **C4** | `CompareKey`, `CompareStructuralVariation`, `CompareAggregate` | casamento guloso sobre relação não-transitiva | corretude | replicado (fiel) |
| C5 | `CompareSchemaType.java:98` | termo booleano morto | code smell | simplificado |
| C6 | `CompareReference.java:45` | guarda assimétrico de nulo | code smell | não portado |
| **C7** | `USchemaCompareMain.java:120` | casamento de variações não-injetivo | **falso positivo** | replicado + reporte |
| I1 | `Inflector.java:470-473` | guarda ordinal testa o número, não o resto | corretude | replicado (fiel) |
| I2 | `Inflector.java:454-459` | `titleCase` sem guarda de nulo (NPE) | crash latente | não replicado (devolve `None`) |
| I3 | `Inflector.java:445` | javadoc do `titleCase` promete o que o código não faz | documentação | replicado (fiel ao **código**) |

`C7` está numa família própria: os demais fazem o harness **reprovar** algo
válido ou explodir. `C7` faz o harness **aprovar** um modelo errado — o único
modo de falha que o instrumento de validação não pode ter.

Severidade: **crash** = exceção em dado real · **crash latente** = exceção
possível, não exercitada pelos dados do oráculo · **corretude** = resultado
silenciosamente errado · **code smell** = sem efeito observável.

---

## #6 — `_id` assumido como `ObjectId`

**Sítio:** `es.um.uschema.mongodb2uschema/.../utils/Helpers.java:66`, em
`generateDocumentPair`.

```java
long timestamp = doc.getObjectId("_id").getTimestamp();
```

**Sintoma.** `getObjectId` lança `ClassCastException` quando `_id` não é um
`ObjectId`. Coleções importadas de origem relacional — como o Northwind, cujos
`_id` são inteiros — derrubam a extração inteira.

**Correção (patch no oráculo, por construção no porte).** Ler `_id`
genericamente e extrair timestamp só quando o tipo permitir:

```java
Object id = doc.get("_id");
long timestamp = (id instanceof ObjectId) ? ((ObjectId) id).getTimestamp() : 0L;
```

**Consequência semântica.** Documentos sem `ObjectId` passam a ter
`firstTimestamp = lastTimestamp = 0`. Isso é *aceitável* porque o timestamp não
participa da equivalência estrutural (nem `CompareStructuralVariation` nem o
`USchemaCompareMain` o comparam), mas **deve ser dito**: para um dataset de
origem relacional, os timestamps do modelo U-Schema são vazios por construção,
não por ausência de dados.

---

## #7 — array vazio indexado antes do teste de tamanho

**Sítio:** `es.um.uschema.doc2uschema/.../process/USchemaModelBuilder.java:255`.

```java
SchemaComponent inner = sc.getInners().get(0);
if (sc.size() == 0 || !(inner instanceof ObjectSC)) //TODO: Sospecho que no se entra nunca aqui. Ademas, si sc.size() == 0 entonces el inner de antes excepciona.
```

**Sintoma.** `IndexOutOfBoundsException` em qualquer documento com um array
vazio. Na Rota B do plano de escala, ~15% dos documentos têm `[]` em algum
campo.

**O autor sabia.** O comentário é dele, no código, e diz exatamente isto:
*"Suspeito que nunca se entra aqui. Além disso, se `sc.size() == 0` então o
`inner` de antes lança exceção."* O defeito foi diagnosticado e não corrigido.
É o achado mais citável do catálogo: não é uma sutileza que passou despercebida,
é dívida técnica declarada.

**Correção.** O `||` do Java já faz short-circuit; basta não materializar o
`inner` antes dele:

```java
if (sc.size() == 0 || !(sc.getInners().get(0) instanceof ObjectSC))
```

**No porte Python:** checar `len(inners) == 0` **antes** de tocar em
`inners[0]`. Ver `fase1_nucleo_inferencia.md`, seção 1.3.

---

## #8 — `meta` descartado ao colapsar variações

**Sítio:** `es.um.uschema.doc2uschema/.../process/SchemaInference.java:201-211`.

```java
List<SchemaComponent> entityVariations = rawEntities.get(schema.entityName);
SchemaComponent retSchema = schema;

if (entityVariations != null)
{
    Optional<SchemaComponent> foundSchema =
            entityVariations.stream().filter(schema::equals).findFirst();
    if (foundSchema.isPresent())
        retSchema = foundSchema.get();   // <-- `schema.meta` é perdido aqui
    else
        entityVariations.add(schema);
}
```

**Sintoma.** Quando um documento produz uma forma estruturalmente igual a uma
variação já registrada, a variação existente é reusada e o `meta` do documento
recém-inferido (`count`, `firstTimestamp`, `lastTimestamp`) é **jogado fora**.
A contagem por variação fica menor que o volume real.

**Por que só aparece com array de tamanho variável.** O gatilho é o
`ArraySC.equals`, em `.../intermediate/raw/ArraySC.java:93-98`:

```java
// By ignoring the count we make all homogeneous arrays equivalent if the
// inner element is the same (checked in the next instruction)
// Another step is needed to reconcile zero size arrays with other lengths.
// Also, in this step, lower and upper bounds have to be reconciled.
//if (this.isHomogeneous() && this.homogeneous_size != otherA.homogeneous_size)
//    return false;
```

O check de tamanho está **comentado**. Dois documentos com `tags: [a]` e
`tags: [a, b, c]` produzem `ArraySC` iguais, colapsam na mesma variação, e o
segundo tem seu `count` descartado. Sem essa igualdade frouxa, o colapso quase
nunca ocorreria e o bug ficaria invisível.

De novo, o autor anotou o problema (*"Another step is needed to reconcile zero
size arrays with other lengths"*) sem resolvê-lo.

**Correção.** Combinar o `meta` ao reusar, em vez de descartar:

```java
if (foundSchema.isPresent()) {
    foundSchema.get().meta.combineMetadata(schema.meta);
    retSchema = foundSchema.get();
}
```

**A igualdade frouxa é load-bearing e deve ser preservada.** `ArraySC.__eq__`
ignorando o tamanho é decisão deliberada de design (é o que faz `[a]` e
`[a,b,c]` serem a mesma variação estrutural). O porte replica a igualdade **e**
aplica a correção do `combineMetadata` — as duas coisas juntas. Corrigir só a
igualdade explodiria o número de variações e divergiria do oráculo.

### Incerteza declarada, adjacente ao #8

`SchemaInference.java:94`, em `innerCountAndTimestampsAdjust`:

```java
// FIXME: I'm not sure this will work for n levels of aggregation
```

Não é um defeito confirmado — é um *known unknown* do autor sobre a propagação
de `count`/`timestamp` para entidades não-raiz com aninhamento profundo. Vale
construir um dataset com três níveis de agregação e comparar oráculo × porte
antes de afirmar qualquer coisa. **Não investigado.**

---

## C1 — `CompareReference` compara só o primeiro `isFeaturedBy`

**Sítio:** `es.um.uschema.utils/.../custom/compare/CompareReference.java:31-42`.

```java
if (r1.getIsFeaturedBy().isEmpty() ^ r2.getIsFeaturedBy().isEmpty())
  return false;

if (!r1.getIsFeaturedBy().isEmpty() && !r2.getIsFeaturedBy().isEmpty())
{
  if (r1.getIsFeaturedBy().size() != r2.getIsFeaturedBy().size())
    return false;

  if (r1.getIsFeaturedBy().get(0).getContainer() != null ^ r2.getIsFeaturedBy().get(0).getContainer() != null)
    return false;

  if (r1.getIsFeaturedBy().get(0).getContainer() != null && !CompareSchemaType.compareNames(r1.getIsFeaturedBy().get(0).getContainer(), r2.getIsFeaturedBy().get(0).getContainer()))
    return false;
}
```

**Sintoma.** Os tamanhos das listas são conferidos, mas apenas o elemento `[0]` é
comparado. Os elementos `1..n` são ignorados. Duas `Reference` cujos
`isFeaturedBy` são `[Order, Address]` e `[Order, Payment]` são declaradas
equivalentes.

Nos XMIs de referência do Neo4j, `isFeaturedBy` aparece 4 vezes por modelo — o
defeito é alcançável, embora não necessariamente exercitado com listas de
tamanho > 1.

**Correção proposta (Davi).** Trocar a comparação do `[0]` por um casamento de
multiset sobre a lista inteira, reusando o predicado que já existe:

```python
if not _match_bag(r1.isFeaturedBy, r2.isFeaturedBy, _same_container):
    return False
```

É order-insensitive (a ordem de `isFeaturedBy` não é semântica) e não desce nas
`features` — mantém a proteção contra ciclo que o `_same_container` dá. Torna o
check de tamanho redundante, como nos demais comparadores.

**Decisão no porte: replicar o `[0]`; a correção vai para o upstream.**

Vale ser preciso sobre o porquê, porque este caso é mais benigno que os outros.
Um harness *mais rígido* que o oráculo **não pode produzir falso positivo** — ele
nunca aprova um porte errado. Ele só reprova a mais, e só quando os
`isFeaturedBy[1..n]` de fato diferem, o que é uma diferença real entre os dois
modelos. Como **ferramenta de engenharia**, a versão com `_match_bag` é melhor.

O problema é outro: o harness é o **instrumento de medida** da tese. Se ele adota
uma noção de equivalência diferente da do oráculo, a afirmação "o porte é
equivalente ao original *no sentido em que o original define equivalência*" deixa
de ser verificável — vira "equivalente segundo um critério nosso", e o oráculo
deixa de ser oráculo. Fidelidade primeiro; correção depois, upstream.

*Se* quisermos visibilidade sem quebrar a premissa, o padrão já estabelecido
resolve: manter o veredito no `[0]` e emitir uma `Divergence(fatal=False)` quando
`1..n` divergirem — o mesmo "fiel + reporte extra" de `count`, `root` e das
variações órfãs.

Está travado por teste — ver `tests/unit/test_equivalence.py::test_compare_reference_only_compares_first_featured_by`,
que afirma `True` para `["Order", "Address"]` vs `["Order", "Payment"]`, e por
mutation testing (trocar o `[0]` por um casamento de multiset faz o teste falhar).

---

## C2 — recursão de `opposite` sem guarda de ciclo

**Sítio:** `CompareReference.java:27`.

```java
if (r1.getOpposite() != null && !new CompareFeature().compare(r1.getOpposite(), r2.getOpposite()))
  return false;
```

**Sintoma.** `Reference.opposite` é auto-referente (`Reference → Reference` no
`uschema.ecore`). Numa relação bidirecional bem-formada, `r.opposite.opposite ==
r`. A cadeia `CompareReference → CompareFeature → CompareLogicalFeature →
CompareReference` não tem conjunto de visitados: `StackOverflowError`.

Nenhum `Comparator` da árvore mantém estado entre chamadas — cada um instancia
`new CompareFeature()` a cada nível.

**Por que não explode.** Nenhum XMI de referência popula `opposite`:

```text
$ grep -c 'opposite=' resources/**/*.xmi
neo4j/*.xmi   : 0
mongodb/*.xmi : 0
```

O caminho existe no código e é inalcançável pelos dados que o oráculo produz.

**Decisão no porte: replicar, com o risco documentado** na docstring de
`compare_reference` (seção `Notes`). Inventar um guarda de visitados que o
oráculo não tem seria divergir por um caso que não ocorre — e mascararia o
defeito num eventual reporte upstream.

---

## C3 — `compareNames` desreferencia nome nulo

**Sítio:** `CompareSchemaType.java:94-100`.

```java
public static boolean compareNames(SchemaType e1, SchemaType e2) {
    String name1 = casec.apply(e1.getName());   // casec = n -> n.toLowerCase()
    String name2 = casec.apply(e2.getName());
    ...
}
```

**Sintoma.** `NullPointerException` se `getName()` for `null`.

O método é `static` e é chamado **diretamente** por `CompareAggregate`,
`CompareReference` e `USchemaCompareMain` — nenhum deles passa pelo guarda de
nome que existe em `CompareSchemaType.compare` (linhas 27-30).

`SchemaType.name` tem `lowerBound="1"` no `uschema.ecore`, ou seja, um
`SchemaType` sem nome é um modelo inválido. O EMF impõe isso na validação
explícita, não na atribuição; o PyEcore não impõe em lugar nenhum.

**Decisão no porte: replicar a falha, não mascará-la.** `compare_names` lê
`s1.name.lower()` sem `str()`, e levanta `AttributeError` no mesmo ponto em que
o Java levantaria `NullPointerException`. Documentado em `Raises`.

A alternativa rejeitada era `str(s1.name).lower()`, que converte `None` em
`"none"` — dois modelos inválidos passariam a casar entre si, silenciosamente.

---

## C4 — casamento guloso sobre uma relação não-transitiva

**Sítio:** o padrão `stream().filter(...).findFirst()` + remoção condicional, em
`CompareKey`, `CompareStructuralVariation`, `ComparePTuple` e `CompareAggregate`.
No porte, concentrado em `_match_bag`.

```java
for (StructuralVariation v1 : a1.getAggregates())
{
  Optional<StructuralVariation> toErase = s2Copy.stream()
      .filter(v2 -> ... CompareSchemaType.compareNames(v1.getContainer(), v2.getContainer()))
      .findFirst();
  if (toErase.isPresent())
    s2Copy.remove(toErase.get());
}
if (!s2Copy.isEmpty()) return false;
```

**Sintoma.** Isto é um pareamento bipartido resolvido por algoritmo guloso. Ele
só é correto quando o predicado é uma **relação de equivalência** (particiona os
elementos em classes), porque aí qualquer escolha serve.

`compareNames` **não** é uma relação de equivalência — não é transitiva:

```text
orderx ~ order   ->  True
order  ~ sorder  ->  True
orderx ~ sorder  ->  False
```

Logo, o guloso pode consumir um parceiro "errado" e falhar mesmo existindo um
pareamento perfeito. Reprodução, com o `_match_bag` do porte:

```text
items1 = [order, sorders]     items2 = [orders, orderx]

pareamento perfeito existe:  order ~ orderx  e  sorders ~ orders
_match_bag(items1, items2)  ->  False        <- falso negativo

_match_bag(items1, [orderx, orders])  ->  True   <- depende da ORDEM de items2
```

O resultado depende da ordem de serialização do XMI.

**Quais chamadores estão expostos.** Não basta olhar o predicado nominal: a
não-transitividade se propaga por despacho. `compare_feature` herda o defeito
sempre que compara dois `Aggregate` — verificado:

```text
addr(orderx) ~ addr(order)   ->  True
addr(order)  ~ addr(sorder)  ->  True
addr(orderx) ~ addr(sorder)  ->  False
```

O que salva `CompareKey`, `CompareStructuralVariation` e o bloco `attributes` de
`CompareReference` **não** é o predicado ser uma equivalência — é um invariante
dos dados. `CompareFeature` exige **nome idêntico** antes de despachar por tipo,
e os nomes de features dentro de uma variação são únicos (são as chaves do
documento). Cada elemento de `items1` tem, portanto, no máximo **um** candidato
em `items2`: o grafo bipartido tem grau ≤ 1 e o guloso é trivialmente ótimo.

Esse invariante não é imposto pelo `uschema.ecore` — `StructuralVariation.features`
não declara unicidade de nome. Ele vale porque o inferidor o produz assim.

`ComparePTuple` está a salvo de verdade: `compareDataType` é equalidade de forma
canônica (`Long≡Integer≡Number`), uma relação de equivalência legítima.

Sobra **`CompareAggregate`**: `aggregates` é uma lista de variações sem chave de
nome, casadas diretamente por `compareNames` sobre o `container`. Grau
arbitrário, predicado não-transitivo, guloso.

**Alcançabilidade.** Requer um `Aggregate` apontando para variações de duas ou
mais entidades cujos nomes se casem por substring e cujo pareamento guloso falhe.
Improvável com nomes de entidade reais (`Order`, `Address`, `Customer`), mas o
resultado ser **dependente da ordem** é, por si só, um defeito num instrumento de
validação: o mesmo par de modelos pode aprovar ou reprovar conforme a ordem em
que o XMI foi escrito.

**Decisão no porte: replicar.** A correção é trocar o guloso por um pareamento
máximo (Hopcroft–Karp, ou um Kuhn simples — as coleções são minúsculas). Isso
muda vereditos e portanto tem de ser proposto upstream, não introduzido
unilateralmente no porte.

---

## C5 — termo booleano morto em `compareNames`

`CompareSchemaType.java:98`:

```java
return (name1.equals(name2)) || name1.toLowerCase().equals(name2.toLowerCase()) || ...
```

`name1` e `name2` já vêm de `casec.apply(...)`, que é `n -> n.toLowerCase()`. O
segundo termo nunca pode ser verdadeiro quando o primeiro é falso.

Sem efeito observável. O porte colapsa os dois num `==` sobre nomes já
minusculizados, com comentário explicando a equivalência.

---

## C6 — guarda de nulo assimétrico em `CompareReference`

`CompareReference.java:45`:

```java
if (r1.getAttributes() != null && r2.getAttributes() != null)
{
    ... // compara
}
// se apenas UM for null, o bloco é pulado silenciosamente e o método segue
```

Todos os outros campos opcionais da mesma classe (`opposite`, `refsTo`) usam
`^` (XOR) e reprovam quando a presença difere. `attributes` usa `&&` e
simplesmente não compara.

Sem efeito observável: no EMF, uma `EList` de `upperBound="-1"` nunca é `null`.
O porte não traduz o guarda (coleções PyEcore também nunca são `None`).

---

## C7 — casamento de variações não-injetivo (falso positivo do harness)

**Sítio:** `es.um.uschema.doc2uschema.validation/.../main/USchemaCompareMain.java:106-133`,
no método privado `compareSchemaTypes`.

```java
private boolean compareSchemaTypes(SchemaType s1, SchemaType s2)
{
  boolean goodHit = true;

  if (s1.getVariations().size() != s2.getVariations().size())
  {
    warningLog.add("SchemaType warning: Variation lists sizes do not match: ...");
    goodHit = false;
  }

  for (StructuralVariation v1 : s1.getVariations())
  {
    Optional<StructuralVariation> varOption = s2.getVariations().stream()
        .filter(v2 -> varComparer.compare(v1, v2)).findAny();   // <-- sem remoção
    if (varOption.isPresent())
      hitLog.add("VariationType hit: ...");
    else
    {
      warningLog.add("VariationType warning: ...");
      goodHit = false;
    }
  }

  return goodHit;
}
```

**Sintoma.** O laço percorre apenas `s1 → s2`, e o `findAny` **não remove** a
variação casada do conjunto de candidatas. Duas variações de `s1` podem casar
com a **mesma** variação de `s2`. Como o único outro controle é a igualdade de
tamanhos, uma variação de `s2` pode nunca ser casada sem que nada seja
registrado.

**Reprodução** (simulando o algoritmo do Java sobre o `compare_variation` do
porte):

```text
s1 (porte)   = [A, A]      # duplicou a variação A, perdeu a B
s2 (oráculo) = [A, B]
tamanhos iguais? True
veredito              -> True

a variação B do oráculo nunca foi casada, e nenhum warning foi emitido.
```

**Por que é a pior categoria.** Todos os outros defeitos deste catálogo fazem o
harness reprovar algo válido, ou explodir. Este faz o harness **aprovar um
modelo errado**. Um porte que colapse variações a mais (ou a menos, desde que a
contagem final bata) passa na validação.

**Inconsistência interna.** A mesma base de código resolve o mesmo problema de
duas formas. `CompareStructuralVariation` casa `features` **com remoção** —
semântica de multiset, injetiva. `USchemaCompareMain.compareSchemaTypes` casa
variações **sem remoção** — semântica de conjunto. Não há comentário
justificando a diferença; parece descuido, não decisão.

**Decisão no porte: replicar o veredito, registrar a anomalia.** É a política
"fiel + reporte extra" já adotada para `count` e `root`. O
`_compare_schema_type_variations` reproduz o `findAny` sem remoção (o veredito
fatal continua idêntico ao do oráculo), **e** registra uma divergência
**não-fatal** quando o casamento não é injetivo — ou seja, quando alguma
variação de `s2` fica sem par. Assim o relatório mostra o buraco sem que o
harness passe a reprovar modelos que o Java aprova.

**Correção upstream.** Reusar a mesma mecânica do `CompareStructuralVariation`:
remover a variação casada de uma cópia de `s2.getVariations()` e exigir que a
cópia esvazie. Isso torna a comparação injetiva e sobrejetiva de uma vez, e
dispensa até o check de tamanho (que passa a ser consequência).

---

## I1 — `ordinalize` testa o número onde deveria testar o resto

`Inflector.java:468-483`:

```java
public String ordinalize(int number)
{
  int remainder = number % 100;            // calculado...
  String numberStr = Integer.toString(number);
  if (11 <= number && number <= 13)        // ...e ignorado: testa `number`
    return numberStr + "th";

  remainder = number % 10;                 // sobrescrito, sem nunca ter sido lido
  switch (remainder) { case 1: ... "st"; case 2: ... "nd"; case 3: ... "rd"; default: ... "th"; }
}
```

O `remainder` módulo 100 existe justamente para tratar a exceção do inglês:
11, 12 e 13 são `th` (`eleventh`, não `eleven-first`), e a regra vale para
**todas** as centenas — 111 é `111th`, 212 é `212th`. Mas o guarda testa
`number`, não `remainder`. A variável é escrita, nunca lida, e sobrescrita duas
linhas abaixo.

Resultado: a exceção só é aplicada aos números 11, 12 e 13 **literais**.

| entrada | `ordinalize` | correto |
|---|---|---|
| 11 | `11th` | `11th` |
| 111 | **`111st`** | `111th` |
| 112 | **`112nd`** | `112th` |
| 213 | **`213rd`** | `213th` |

O `InflectorTest` do upstream testa 1–39, 100–104, 200–204, 1000–1004,
10000–10004 e 100000–100004 — e **nenhum** `x11`–`x13` fora do primeiro. O bug
passa verde na suíte do próprio autor.

**Alcance.** Nenhum: `ordinalize` é código morto no pipeline. As três chamadas de
produção do Inflector usam só `capitalize` (`SchemaInference:183,188`;
`USchemaToDocumentDb:82,169`), `singularize` (`SchemaInference:233`;
`USchemaModelBuilder:194`; `ModelDirector:84,102`) e `pluralize`
(`DefaultReferenceMatcherCreator:26`). O defeito não toca nome de entidade
nenhum, e portanto não afeta a equivalência com o oráculo.

**Decisão no porte: replicar, com teste que fixa o valor errado.** Não porque
custe algo corrigir — não custa, é código morto —, mas porque a disciplina é a
mesma do resto do catálogo: o porte reproduz o oráculo e o desvio vai
documentado. Um teste afirma `ordinalize(111) == "111st"`, citando esta entrada;
se alguém "consertar" o método, o teste cai e obriga a leitura daqui.

**Correção upstream.** Trocar o guarda por `11 <= remainder && remainder <= 13`
(com `remainder` já sendo `number % 100`) e remover a reatribuição. Como o
`Inflector` é cópia vendorizada do ModeShape, a correção cabe **também** lá — e
o mesmo defeito deve estar em toda a linhagem de cópias dessa classe.

---

## I2 — `titleCase` é o único método da classe sem guarda de nulo

`Inflector.java:454-459`:

```java
public String titleCase(String words, String... removableTokens)
{
  String result = humanize(words, removableTokens);          // humanize(null) → null
  result = replaceAllWithUppercase(result, "\\b([a-z])", 1); // → Pattern.matcher(null) → NPE
  return result;
}
```

Todo método público da classe abre com o mesmo guarda — `pluralize`,
`singularize`, `camelCase`, `underscore`, `capitalize`, `humanize`,
`isUncountable` — e o contrato, uniforme, é **`null` entra, `null` sai**. O
`titleCase` é a única exceção, e não por decisão: ele não guarda porque delega ao
`humanize`, que guarda… e devolve o `null` que o `titleCase` então entrega ao
`replaceAllWithUppercase`. Lá, `Pattern.matcher(null)` estoura
`NullPointerException`.

Não é "entrada nula é erro" — se fosse, o método lançaria `IllegalArgumentException`
com mensagem, como faz o resto do ecossistema Java quando quer rejeitar nulo. É
uma linha faltando.

**Alcance.** Nenhum: `titleCase` é código morto no pipeline (ver o alcance de I1)
e o `InflectorTest` nunca o chama com `null` — a suíte do autor não exercita o
caminho.

**Decisão no porte: não replicar.** `title_case(None)` devolve `None`, alinhado
ao contrato uniforme dos outros nove métodos. É o único ponto do porte onde
**deliberadamente não se reproduz** o comportamento do oráculo, e a justificativa
é que não há comportamento a reproduzir: uma `NullPointerException` acidental não
é semântica, é ausência de semântica. Nenhuma equivalência estrutural depende
disso — o oráculo jamais chama `titleCase`, com nulo ou sem.

**Correção upstream.** Acrescentar ao `titleCase` o mesmo guarda dos irmãos:

```java
if (words == null)
  return null;
```

É a correção mais barata do catálogo: uma linha, sem mudança de comportamento em
nenhuma entrada válida, e fecha a única inconsistência de contrato da classe.

---

## I3 — o javadoc do `titleCase` documenta um método que não existe

`Inflector.java:444-445` (idêntico nas duas cópias vendorizadas):

```java
 *   inflector.titleCase("man from the boondocks")       #=> "Man From The Boondocks"
 *   inflector.titleCase("x-men: the last stand")        #=> "X Men: The Last Stand"
```

O segundo exemplo é **falso**. O `titleCase` delega ao `humanize`, e o `humanize`
não toca em hífen em passo nenhum: ele remove o `_id` final, remove os tokens
pedidos, troca `_+` por espaço e capitaliza. O `-` atravessa intacto. O valor real
é `"X-Men: The Last Stand"`.

**Causa.** O exemplo veio do `titleize` do Rails, que faz um passo a mais:

```ruby
def titleize(word)
  humanize(underscore(word)).gsub(/\b(?<!['’`])[a-z]/) { ... }
end
```

O `underscore` do Rails converte `-` em `_`, e só então o `humanize` o vira
espaço — daí `"X Men"`. O ModeShape copiou o **javadoc** do Rails mas escreveu o
método sem a chamada a `underscore`. A doc descreve o Rails; o código, outra
coisa.

**Alcance.** Nenhum em execução: `titleCase` é código morto no pipeline (ver o
alcance de I1) e o `InflectorTest` **não cobre o caso do hífen** — testa só
entradas com `_`, onde os dois comportamentos coincidem. Foi por isso que o
exemplo sobreviveu.

**Alcance como armadilha.** É o risco real deste achado, e o motivo de estar
catalogado apesar de não afetar comportamento: quem ler o javadoc e "consertar" o
`humanize` para tratar `-` **muda a nomeação de entidade**. O `humanize` não é
chamado pelo pipeline hoje, mas o `capitalize` — que é — compartilha com ele a
premissa de que separador não-`_` passa intacto. Uma coleção `order-details`
viraria `Order details` em vez de `Order-details`.

**Decisão no porte: replicar o código, não o javadoc.** `title_case("x-men: the
last stand")` devolve `"X-Men: The Last Stand"`, como o Java realmente faz. O
docstring do porte não repete o exemplo falso.

**Correção upstream.** Trocar o exemplo do javadoc pelo valor verdadeiro
(`"X-Men: The Last Stand"`) — **não** mexer no código para fazê-lo casar com a
doc: isso mudaria o comportamento de um método público por causa de um comentário
errado. Se alguém quiser a semântica do Rails, é `titleCase(underscore(word))`, no
chamador.

---

## O que **não** é defeito

Registrado para evitar que uma leitura futura os "corrija":

- **`Comparator.checkNulls(null, null)` faz `compare` devolver `false`.** Dois
  nulos não são equivalentes. Contraintuitivo, mas deliberado e travado por
  teste no próprio JUnit do upstream
  (`CompareUSchemaTest`: `assertFalse(cSchema.compare(null, null))`).
  **Isto não torna o comparador não-reflexivo**, apesar da aparência: um tipo
  *ausente* só ocorre dentro de um contêiner, e **todo** contêiner
  (`ComparePList`, `ComparePSet`, `ComparePMap`, `CompareAttribute`) guarda o caso
  "ausente dos dois lados" com um `(x == null && y == null) ||` **antes** de
  delegar ao `CompareDataType`. A guarda com `or` só é alcançada quando não há
  contêiner que a proteja — o que o modelo não produz. Replicar a assimetria **no
  lugar certo** é o que mantém o veredito idêntico ao do oráculo.
- **`CompareAggregate` casa variações agregadas só pelo nome do `container`**,
  ignorando as `features` delas. É o que impede recursão infinita em agregado
  cíclico — o análogo do guarda que falta em C2. Deliberado.
- **`CompareStructuralVariation` ignora `variationId`, `count` e `timestamp`.**
  Há comentário explícito no upstream: *"Please note we do not compare
  variationId, count nor timestamp."* É a definição de equivalência
  **estrutural** adotada pelo projeto.
- **`ArraySC.equals` ignora o tamanho do array.** Ver #8: é load-bearing.

---

## Depois do porte: contribuições propostas ao upstream

Ordem sugerida, do mais defensável ao mais invasivo:

1. **C7** — trocar o `findAny` sem remoção pela mecânica já usada em
   `CompareStructuralVariation`. Correção pequena, localizada num método
   privado, e é a única do catálogo que fecha um **falso positivo**. Deveria
   vir primeiro: enquanto ela não entra, o próprio harness de validação do
   upstream não sustenta as garantias que promete.
2. **#7** — correção trivial, o próprio autor diagnosticou no comentário, sem
   mudança de veredito em dado válido. Candidato óbvio a PR.
3. **I3** — corrigir o **exemplo do javadoc** do `titleCase` (o do hífen). Zero
   risco: não toca em código. Vem antes de I2 e I1 porque é a única do catálogo
   que, se ignorada, induz alguém a introduzir um defeito ao "consertar" o código
   para casar com a doc.
4. **I2** — guarda de nulo no `titleCase`. Uma linha, alinha o método ao contrato
   dos outros nove da classe, e não muda nenhuma entrada válida. A mais barata das
   que tocam em código.
5. **I1** — guarda ordinal sobre o resto, não sobre o número. Corrige valores
   objetivamente errados (`111st`), em método que ninguém do pipeline chama.
   Merece um teste novo: o `InflectorTest` do upstream não cobre `x11`–`x13` fora
   do primeiro. **Atenção ao alvo**: `I1`, `I2` e `I3` estão no `Inflector`, que é
   cópia vendorizada do **ModeShape** — o PR mais útil vai para lá, e o U-Schema só
   precisa reavaliar a cópia.
6. **C3** — guarda de nulo em `compareNames`, ou anotação `@NonNull`. Não muda
   comportamento em modelo válido.
7. **C6** — trocar `&&` por `^` em `attributes`, alinhando com os irmãos. Sem
   efeito hoje; previne regressão se a coleção puder ser nula no futuro.
8. **#6** — leitura genérica de `_id`. Muda o domínio de entrada aceito (aceita
   `_id` não-`ObjectId`), com o custo semântico de timestamps zerados. Requer
   discussão sobre o que o `firstTimestamp` deve significar aí.
9. **#8** — `combineMetadata` no colapso. **Muda números publicados.** Precisa
   vir acompanhado dos dados de antes/depois (é exatamente o que a Fase 3
   produz).
10. **C1** — comparar todos os `isFeaturedBy` via multiset (correção já escrita,
    ver a seção C1). Muda vereditos do harness de validação do próprio upstream,
    mas só na direção segura: reprova a mais, nunca aprova a mais.
11. **C2** — guarda de ciclo em `opposite`. Exige decidir a semântica de
    comparação de referências mutuamente opostas antes de implementar.
12. **C4** — pareamento máximo no lugar do guloso. O mais invasivo: toca quatro
    comparadores. Alternativa mais barata: tornar `compareNames` uma relação de
    equivalência (por exemplo, comparando formas canônicas singularizadas pelo
    Inflector), o que resolveria a causa em vez do sintoma.

Nada disso deve entrar no porte antes de a equivalência estrutural com o oráculo
estar demonstrada. Um porte que "melhora" o original não pode ser validado
contra ele.
