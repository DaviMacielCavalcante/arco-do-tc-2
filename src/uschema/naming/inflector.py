r"""Inflector — porte fiel do ``Inflector.java`` do U-Schema (Fase 0.6).

O Java vendoriza o Inflector do **ModeShape** (por sua vez inspirado no do Ruby
on Rails) em duas cópias **idênticas** — ``es.um.uschema.doc2uschema.util.
inflector`` e ``es.um.uschema.mongodb2uschema.spark.inflector`` (diferem só no
``package``). Este módulo porta as duas.

Por que ele é load-bearing: os nomes de ``EntityType`` saem daqui. O
``SchemaInference`` chama ``capitalize`` no nome da coleção (ou no valor do
*type marker*) para nomear a entidade raiz, e ``singularize`` no nome do array
para nomear a entidade agregada (``"details"`` → ``Detail``). Uma regra de
pluralização divergente renomeia entidades e o harness da Fase 0.3 acusa
divergência em **todas** elas.

Fidelidade
----------
- **Regexes com ``re.ASCII``.** O ``Pattern`` do Java, sem
  ``UNICODE_CHARACTER_CLASS``/``UNICODE_CASE``, é uma engine ASCII: ``\\d`` é
  ``[0-9]``, ``\\b`` se apoia em ``[a-zA-Z_0-9]``, e ``CASE_INSENSITIVE`` só dobra
  caixa de ``a-z``. O ``re`` do Python, sobre ``str``, é Unicode por padrão. Sem a
  flag, ``title_case("ação")`` daria ``"Ação"`` onde o Java dá ``"AçãO"`` — e o
  teste portado passaria verde afirmando um valor que o oráculo nunca produz.
- **Substituições transcritas na sintaxe do Java** (``$1``) e traduzidas em tempo
  de compilação da regra por ``_to_python_replacement``. Assim a tabela de regras
  em ``_initialize`` é comparável linha a linha com o ``initialize()`` do Java.

- **``ordinalize`` replica o bug I1** (``bugs_originais.md``): o guarda de 11 a 13
  testa o número, não o resto da divisão por 100 — então ``ordinalize(111)``
  devolve ``"111st"``. É o que o oráculo devolve, e é o que os testes fixam.
- **``humanize`` não toca em hífen**, e ``title_case("x-men")`` dá ``"X-Men"``. O
  javadoc do Java promete ``"X Men"``, mas o exemplo veio do ``titleize`` do Rails
  (que chama ``underscore`` antes) e o método não faz esse passo — bug I3. Portamos
  o **código**, não o javadoc: "consertar" o ``humanize`` para tratar ``-`` mudaria
  a nomeação de entidade.

Desvios
-------
- ``replace_all_with_uppercase`` substitui por **função**; o Java passa o texto do
  grupo como *template* de ``appendReplacement``, onde ``$`` e ``\\`` ainda são
  metacaracteres (e a chamada estoura se o grupo contiver um). Aqui o texto é
  literal — o Python é estritamente mais tolerante, e só em entrada que faria o
  Java falhar.
- ``title_case(None)`` devolve ``None``; o Java estoura ``NullPointerException``
  (bug I2). Único desvio semântico do porte — a exceção do Java é uma guarda
  faltando, não uma decisão.

TODO: completar com a decisão da ordem das regras (o ``addFirst``). Ver
``bugs_originais.md``.
"""

from __future__ import annotations

import math
import re
from typing import Final

# Semântica default do java.util.regex.Pattern — ver "Fidelidade".
_JAVA_FLAGS: Final = re.ASCII

_GROUP_REF: Final = re.compile(r"\$(\d)")


def _to_python_replacement(replacement: str) -> str:
    r"""Traduzir a string de substituição do Java para a sintaxe do ``re``.

    O Java escreve retrovisor de grupo como ``$1``; o ``re`` do Python, como
    ``\\1`` (ou ``\\g<1>``). As regras em ``Inflector._initialize`` são
    transcritas do Java **na sintaxe do Java**, então precisam passar por aqui
    antes de virar argumento de ``re.sub``.

    Parameters
    ----------
    replacement : str
        Substituição no formato do ``Matcher.replaceAll`` do Java (``"$1es"``).

    Returns
    -------
    str
        A substituição equivalente para ``re.sub``.

    Examples
    --------
    >>> _to_python_replacement("$1$2ves")
    '\\g<1>\\g<2>ves'
    """
    # A barra literal é escapada ANTES de introduzir os retrovisores — na ordem
    # inversa, o escape morderia a barra do `\g<N>` recém-criado.
    return _GROUP_REF.sub(r"\\g<\1>", replacement.replace("\\", "\\\\"))


class _Rule:
    """Uma regra de inflexão: uma regex e a substituição a aplicar quando ela casa.

    Espelha a classe interna ``Inflector.Rule`` do Java.
    """

    def __init__(self, expression: str, replacement: str | None) -> None:
        """Compilar a regra.

        Parameters
        ----------
        expression : str
            Regex da regra, na sintaxe do Java.
        replacement : str or None
            Substituição (``None`` vira string vazia, como no Java), na sintaxe
            do Java (``$1``).
        """
        self.expression = expression
        self.replacement = replacement if replacement is not None else ""
        self._pattern = re.compile(expression, re.IGNORECASE | _JAVA_FLAGS)
        self._replacement = _to_python_replacement(self.replacement)

    def apply(self, word: str) -> str | None:
        """Aplicar a regra à palavra.

        Parameters
        ----------
        word : str
            Palavra de entrada.

        Returns
        -------
        str or None
            A palavra modificada, ou ``None`` se a regra **não casou** — é o
            ``null`` do Java, e é o que faz o laço chamador seguir para a
            próxima regra.
        """
        # `search` + `sub` = o `find()` + `replaceAll()` do Java: procura em
        # qualquer posição e, se achou, substitui TODAS as ocorrências.
        if self._pattern.search(word) is None:
            return None
        return self._pattern.sub(self._replacement, word)

    def __repr__(self) -> str:
        return f"{self.expression}, {self.replacement}"


def replace_all_with_uppercase(text: str, regex: str, group_number_to_uppercase: int) -> str:
    """Substituir cada casamento de ``regex`` pelo grupo indicado, em maiúsculas.

    O que estiver no casamento mas **fora** do grupo é descartado — é assim que
    o ``camel_case`` come os ``_`` ao subir a letra seguinte.

    Parameters
    ----------
    text : str
        Texto de entrada.
    regex : str
        Regex a casar.
    group_number_to_uppercase : int
        Índice do grupo cujo conteúdo, em maiúsculas, vira o texto de substituição.

    Returns
    -------
    str
        O texto com os casamentos substituídos.

    Examples
    --------
    >>> replace_all_with_uppercase("hello", "([aeiou])", 1)
    'hEllO'
    """
    # A substituição é uma função, não uma string: o `re` a chama a cada
    # casamento e usa o que ela devolve, literalmente. É o equivalente do laço de
    # `appendReplacement`/`appendTail` do Java — com a diferença de que ali o
    # texto do grupo ainda passa por interpretação (`$` e `\` são especiais nele),
    # e aqui não. Ver "Desvios" no docstring do módulo.
    return re.sub(
        regex,
        lambda match: match.group(group_number_to_uppercase).upper(),
        text,
        flags=_JAVA_FLAGS,
    )


class Inflector:
    """Transforma palavras em singular, plural, camelCase, underscore, ordinal.

    Porte de ``es.um.uschema.doc2uschema.util.inflector.Inflector``.

    Examples
    --------
    >>> Inflector().pluralize("octopus")
    'octopi'
    >>> Inflector().singularize("details")
    'detail'
    >>> Inflector().capitalize("categories")
    'Categories'
    """

    def __init__(self, original: Inflector | None = None) -> None:
        """Construir o Inflector com as regras default, ou copiar as de ``original``.

        Funde os dois construtores do Java: o público (que chama ``initialize``)
        e o protegido de cópia (usado pelo ``clone``).

        Parameters
        ----------
        original : Inflector, optional
            Se dado, copia dele as regras. Se omitido, registra as default.
        """
        self._plurals: list[_Rule]
        self._singulars: list[_Rule]
        self._uncountables: set[str]
        if original is None:
            self._plurals = []
            self._singulars = []
            self._uncountables = set()
            self._initialize()
        else:
            self._plurals = list(original._plurals)
            self._singulars = list(original._singulars)
            self._uncountables = set(original._uncountables)

    def clone(self) -> Inflector:
        """Devolver uma cópia independente deste Inflector.

        Returns
        -------
        Inflector
            Cópia com as mesmas regras, desacoplada da original.
        """
        return Inflector(self)

    # ---------------------------------------------------------------- uso ---

    def pluralize(self, word: object, count: int | None = None) -> str | None:
        """Devolver a forma plural da palavra.

        Parameters
        ----------
        word : object
            Palavra a pluralizar (o Java aceita qualquer ``Object`` e chama
            ``toString()``).
        count : int, optional
            Sobrecarga ``pluralize(word, count)`` do Java: reveja o que ele faz
            quando ``count`` é 1 ou -1 — em particular, se ele ainda apara o
            branco da palavra nesse caminho.

        Returns
        -------
        str or None
            O plural, ou a própria palavra se nenhuma regra casou; ``None`` se
            ``word`` é ``None``.

        Examples
        --------
        >>> Inflector().pluralize("sheep")
        'sheep'
        >>> Inflector().pluralize("CamelOctopus")
        'CamelOctopi'
        """
        if word is None:
            return None

        if count in (1, -1):
            return str(word)

        word_str = str(word).strip()

        if word_str == "" or self.is_uncountable(word_str):
            return word_str

        for plural in self._plurals:
            rule_result = plural.apply(word_str)
            if rule_result is not None:
                return rule_result

        return word_str

    def singularize(self, word: object) -> str | None:
        """Devolver a forma singular da palavra.

        Parameters
        ----------
        word : object
            Palavra a singularizar.

        Returns
        -------
        str or None
            O singular, ou a própria palavra se nenhuma regra casou; ``None`` se
            ``word`` é ``None``.

        Examples
        --------
        >>> Inflector().singularize("the blue mailmen")
        'the blue mailman'
        """
        if word is None:
            return None

        word_str = str(word).strip()

        if word_str == "" or self.is_uncountable(word_str):
            return word_str

        for singular in self._singulars:
            rule_result = singular.apply(word_str)
            if rule_result is not None:
                return rule_result

        return word_str

    def lower_camel_case(self, word: str | None, *delimiter_chars: str) -> str | None:
        """Escrever a palavra em ``lowerCamelCase``.

        Parameters
        ----------
        word : str or None
            Palavra a converter.
        *delimiter_chars : str
            Caracteres extras que também delimitam palavras (além do ``_``).

        Returns
        -------
        str or None
            A palavra em lowerCamelCase.

        Examples
        --------
        >>> Inflector().lower_camel_case("the-first_name", "-")
        'theFirstName'
        """
        return self.camel_case(word, False, *delimiter_chars)

    def upper_camel_case(self, word: str | None, *delimiter_chars: str) -> str | None:
        """Escrever a palavra em ``UpperCamelCase``.

        Parameters
        ----------
        word : str or None
            Palavra a converter.
        *delimiter_chars : str
            Caracteres extras que também delimitam palavras (além do ``_``).

        Returns
        -------
        str or None
            A palavra em UpperCamelCase.

        Examples
        --------
        >>> Inflector().upper_camel_case("active_record")
        'ActiveRecord'
        """
        return self.camel_case(word, True, *delimiter_chars)

    def camel_case(
        self, word: str | None, uppercase_first_letter: bool, *delimiter_chars: str
    ) -> str | None:
        """Escrever a palavra em camelCase, com a primeira letra maiúscula ou não.

        Parameters
        ----------
        word : str or None
            Palavra a converter.
        uppercase_first_letter : bool
            ``True`` para UpperCamelCase, ``False`` para lowerCamelCase.
        *delimiter_chars : str
            Caracteres extras que também delimitam palavras (além do ``_``).

        Returns
        -------
        str or None
            A palavra em camelCase; ``None`` se ``word`` é ``None``.
        """
        if word is None:
            return None

        result = word.strip()
        if result == "":
            return ""

        # Os delimitadores extras viram `_` antes de subir a caixa: é o `_` que a
        # regex usa como marca de fronteira de palavra. (No Java isso está dentro do
        # ramo Upper — como o ramo lower delega ao Upper, dá no mesmo.)
        for delimiter_char in delimiter_chars:
            result = result.replace(delimiter_char, "_")

        # "(^|_)(.)" casa início-ou-underscore seguido de um caractere, e sobe esse
        # caractere; o `_` fica FORA do grupo 2, então some da saída.
        upper_camel = replace_all_with_uppercase(result, "(^|_)(.)", 2)

        if uppercase_first_letter:
            return upper_camel

        # Java, linha 330: abaixo de 2 caracteres o ramo lower devolve a palavra como
        # está — não minusculiza e não passa pelo Upper.
        if len(result) < 2:
            return result

        # O resto vem do ramo Upper, não da palavra original: é ele que já comeu os
        # `_` e subiu as iniciais internas. Só a primeira letra é rebaixada.
        return result[0].lower() + upper_camel[1:]

    def underscore(self, camel_case_word: str | None, *delimiter_chars: str) -> str | None:
        """Desfazer o camelCase, separando as palavras por ``_`` (inverso do ``camel_case``).

        Parameters
        ----------
        camel_case_word : str or None
            Palavra em camelCase.
        *delimiter_chars : str
            Caracteres que também delimitam palavras (além da capitalização e do ``-``).

        Returns
        -------
        str or None
            A palavra em minúsculas, com as palavras separadas por ``_``.

        Examples
        --------
        >>> Inflector().underscore("The.firstName", ".")
        'the_first_name'
        """
        if camel_case_word is None:
            return None

        result = camel_case_word.strip()
        if result == "":
            return ""

        # As duas regexes do Java entram SEM `IGNORECASE` (é `String.replaceAll`, não
        # uma `_Rule`): elas dependem justamente da distinção de caixa.
        result = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", result, flags=_JAVA_FLAGS)
        result = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", result, flags=_JAVA_FLAGS)

        # `str.replace`, não `re.sub`: no Java é `replace(char, char)`, que é literal.
        result = result.replace("-", "_")
        for delimiter_char in delimiter_chars:
            result = result.replace(delimiter_char, "_")

        return result.lower()

    def capitalize(self, words: str | None) -> str | None:
        """Devolver a palavra com a primeira letra em maiúscula e o resto em minúscula.

        É a regra de nomeação de ``EntityType`` do ``SchemaInference``.

        Parameters
        ----------
        words : str or None
            Texto a capitalizar.

        Returns
        -------
        str or None
            O texto capitalizado; ``None`` se ``words`` é ``None``.

        Examples
        --------
        >>> Inflector().capitalize("employee_salary")
        'Employee_salary'
        """
        if words is None:
            return None

        words_stripped = words.strip()

        if words_stripped == "":
            return ""

        # O `str.capitalize()` do Python já é "primeira maiúscula, resto minúsculo" —
        # cobre de uma vez os dois ramos do Java (o de 1 caractere, linha 393, e o
        # geral, 396). Diverge só em Unicode exótico (`ß`, dígrafos), que não alcança
        # nome de coleção. NÃO é `str.title()`, que subiria a letra após cada `_`.
        return words_stripped.capitalize()

    def humanize(self, words: str | None, *removable_tokens: str) -> str | None:
        """Capitalizar a primeira palavra, virar ``_`` em espaço e remover o ``_id`` final.

        Parameters
        ----------
        words : str or None
            Texto a humanizar.
        *removable_tokens : str
            Tokens a remover. Veja no Java **como** ele os remove — a assinatura
            diz "token", mas a chamada revela outra coisa.

        Returns
        -------
        str or None
            O texto humanizado; ``None`` se ``words`` é ``None``.

        Examples
        --------
        >>> Inflector().humanize("author_id")
        'Author'
        """
        if words is None:
            return None

        result = words.strip()
        if result == "":
            return ""

        result = re.sub("_id$", "", result, flags=_JAVA_FLAGS)

        # `re.sub` e não `str.replace`: o Java usa `replaceAll`, logo cada "token"
        # removível é uma REGEX, não texto literal.
        for removable_token in removable_tokens:
            result = re.sub(removable_token, "", result, flags=_JAVA_FLAGS)

        result = re.sub("_+", " ", result, flags=_JAVA_FLAGS)

        return self.capitalize(result)

    def title_case(self, words: str | None, *removable_tokens: str) -> str | None:
        """Capitalizar todas as palavras, para saída legível.

        Parameters
        ----------
        words : str or None
            Texto a converter.
        *removable_tokens : str
            Tokens a remover, repassados ao ``humanize``.

        Returns
        -------
        str or None
            O texto em Title Case.

        Examples
        --------
        >>> Inflector().title_case("the_first_name")
        'The First Name'
        """
        result = self.humanize(words, *removable_tokens)

        # Desvio deliberado (I2): o Java não testa o `null` aqui e estoura NPE em
        # `titleCase(null)`. Devolvemos `None` — é linha faltando, não semântica.
        if result is None:
            return None

        return replace_all_with_uppercase(result, r"\b([a-z])", 1)

    def ordinalize(self, number: int) -> str:
        """Escrever o número na forma ordinal (``1st``, ``2nd``, ``3rd``, ``4th``).

        Parameters
        ----------
        number : int
            O número.

        Returns
        -------
        str
            O número com o sufixo ordinal.

        Examples
        --------
        >>> Inflector().ordinalize(23)
        '23rd'
        """
        number_str = str(number)

        # Bug I1, replicado de propósito: o guarda testa o NÚMERO, não `number % 100`
        # (que o Java calcula e joga fora, linha 468). Logo 11..13 viram "th", mas
        # 111 escapa do guarda e cai no `% 10` → "111st". É o que o oráculo devolve.
        if 11 <= number <= 13:
            return number_str + "th"

        # `math.fmod` e não `%`: em negativo o resto do Java tem o sinal do dividendo
        # (-9), o do Python, o do divisor (1). O Java documenta "non-negative number",
        # mas transcrever o truncamento sai de graça.
        match int(math.fmod(number, 10)):
            case 1:
                return number_str + "st"
            case 2:
                return number_str + "nd"
            case 3:
                return number_str + "rd"
            case _:
                return number_str + "th"

    # ---------------------------------------------------------- gerência ---

    def is_uncountable(self, word: str | None) -> bool:
        """Dizer se a palavra é incontável (singular e plural coincidem).

        Parameters
        ----------
        word : str or None
            Palavra a testar.

        Returns
        -------
        bool
            ``True`` se a palavra está na lista de incontáveis.
        """
        if word is None:
            return False

        return word.strip().lower() in self._uncountables

    @property
    def uncountables(self) -> set[str]:
        """Conjunto de palavras não processadas pelo Inflector — **mutável** (como no Java).

        Returns
        -------
        set of str
            O conjunto vivo de incontáveis.
        """
        # O conjunto em si, NÃO uma cópia: o Java devolve a referência viva (o
        # javadoc diz "directly modifiable"). Copiar aqui seria "melhorar" o original.
        return self._uncountables

    def add_pluralize(self, rule: str, replacement: str) -> None:
        """Registrar uma regra de pluralização.

        Parameters
        ----------
        rule : str
            Regex da regra.
        replacement : str
            Substituição, na sintaxe do Java (``$1``).
        """
        self._plurals.insert(0, _Rule(rule, replacement))

    def add_singularize(self, rule: str, replacement: str) -> None:
        """Registrar uma regra de singularização.

        Parameters
        ----------
        rule : str
            Regex da regra.
        replacement : str
            Substituição, na sintaxe do Java (``$1``).
        """
        self._singulars.insert(0, _Rule(rule, replacement))

    def add_irregular(self, singular: str, plural: str) -> None:
        """Registrar um par irregular (``person``/``people``) nos dois sentidos.

        Parameters
        ----------
        singular : str
            Forma singular.
        plural : str
            Forma plural.
        """
        singular_remainder = singular[1:]
        plural_remainder = plural[1:]

        self.add_pluralize(
            "(" + singular[0] + ")" + singular_remainder + "$", "$1" + plural_remainder
        )
        self.add_singularize(
            "(" + plural[0] + ")" + plural_remainder + "$", "$1" + singular_remainder
        )

    def add_uncountable(self, *words: str | None) -> None:
        """Registrar palavras incontáveis.

        Parameters
        ----------
        *words : str or None
            Palavras a marcar como incontáveis.
        """
        for word in words:
            if word is not None:
                self._uncountables.add(word.strip().lower())

    def clear(self) -> None:
        """Apagar todas as regras deste Inflector."""
        # Esvaziar NO LUGAR, e não reatribuir (`= []`): quem tiver pego a referência
        # via a property `uncountables` precisa enxergar o esvaziamento.
        self._plurals.clear()
        self._singulars.clear()
        self._uncountables.clear()

    def _initialize(self) -> None:
        """Registrar as regras default.

        A ordem abaixo é transcrita **literalmente** do ``initialize()`` do Java
        (é braçal, não tem raciocínio — daí vir pronta). O que *tem* raciocínio,
        e é seu: como cada ``add_*`` insere a regra na **frente** da lista, a
        ordem de consulta é a **inversa** desta — os irregulares, registrados por
        último, são testados primeiro. Reordenar aqui muda a saída.
        """
        self.add_pluralize("$", "s")
        self.add_pluralize("s$", "s")
        self.add_pluralize("(ax|test)is$", "$1es")
        self.add_pluralize("(octop|vir)us$", "$1i")
        self.add_pluralize("(octop|vir)i$", "$1i")  # já é plural
        self.add_pluralize("(alias|status)$", "$1es")
        self.add_pluralize("(bu)s$", "$1ses")
        self.add_pluralize("(buffal|tomat)o$", "$1oes")
        self.add_pluralize("([ti])um$", "$1a")
        self.add_pluralize("([ti])a$", "$1a")  # já é plural
        self.add_pluralize("sis$", "ses")
        self.add_pluralize("(?:([^f])fe|([lr])f)$", "$1$2ves")
        self.add_pluralize("(hive)$", "$1s")
        self.add_pluralize("([^aeiouy]|qu)y$", "$1ies")
        self.add_pluralize("(x|ch|ss|sh)$", "$1es")
        self.add_pluralize("(matr|vert|ind)ix|ex$", "$1ices")
        self.add_pluralize("([m|l])ouse$", "$1ice")
        self.add_pluralize("([m|l])ice$", "$1ice")
        self.add_pluralize("^(ox)$", "$1en")
        self.add_pluralize("(quiz)$", "$1zes")
        # Palavras que já vêm no plural:
        self.add_pluralize("(people|men|children|sexes|moves|stadiums)$", "$1")  # irregulares
        self.add_pluralize("(oxen|octopi|viri|aliases|quizzes)$", "$1")  # regras especiais

        self.add_singularize("s$", "")
        self.add_singularize("(s|si|u)s$", "$1s")  # '-us' e '-ss' já são singulares
        self.add_singularize("(n)ews$", "$1ews")
        self.add_singularize("([ti])a$", "$1um")
        self.add_singularize(
            "((a)naly|(b)a|(d)iagno|(p)arenthe|(p)rogno|(s)ynop|(t)he)ses$", "$1$2sis"
        )
        self.add_singularize("(^analy)ses$", "$1sis")
        self.add_singularize("(^analy)sis$", "$1sis")  # já é singular, mas termina em 's'
        self.add_singularize("([^f])ves$", "$1fe")
        self.add_singularize("(hive)s$", "$1")
        self.add_singularize("(tive)s$", "$1")
        self.add_singularize("([lr])ves$", "$1f")
        self.add_singularize("([^aeiouy]|qu)ies$", "$1y")
        self.add_singularize("(s)eries$", "$1eries")
        self.add_singularize("(m)ovies$", "$1ovie")
        self.add_singularize("(x|ch|ss|sh)es$", "$1")
        self.add_singularize("([m|l])ice$", "$1ouse")
        self.add_singularize("(bus)es$", "$1")
        self.add_singularize("(o)es$", "$1")
        self.add_singularize("(shoe)s$", "$1")
        self.add_singularize("(cris|ax|test)is$", "$1is")  # já é singular, mas termina em 's'
        self.add_singularize("(cris|ax|test)es$", "$1is")
        self.add_singularize("(octop|vir)i$", "$1us")
        self.add_singularize("(octop|vir)us$", "$1us")  # já é singular, mas termina em 's'
        self.add_singularize("(alias|status)es$", "$1")
        self.add_singularize("(alias|status)$", "$1")  # já é singular, mas termina em 's'
        self.add_singularize("^(ox)en", "$1")
        self.add_singularize("(vert|ind)ices$", "$1ex")
        self.add_singularize("(matr)ices$", "$1ix")
        self.add_singularize("(quiz)zes$", "$1")

        self.add_irregular("person", "people")
        self.add_irregular("man", "men")
        self.add_irregular("child", "children")
        self.add_irregular("sex", "sexes")
        self.add_irregular("move", "moves")
        self.add_irregular("stadium", "stadiums")

        self.add_uncountable(
            "equipment", "information", "rice", "money", "species", "series", "fish", "sheep"
        )


# O `protected static final Inflector INSTANCE` do Java, construído uma vez no
# carregamento da classe: aqui, uma variável de módulo criada no import.
_INSTANCE: Final = Inflector()


def get_instance() -> Inflector:
    """Devolver o Inflector compartilhado (o ``Inflector.getInstance()`` do Java).

    É a instância que o pipeline usa (``SchemaInference``, ``USchemaModelBuilder``,
    ``DefaultReferenceMatcherCreator``). Mutável: ``add_*`` sobre ela afeta todo
    o processo, como no original — por isso a função devolve o singleton, e não
    um Inflector novo a cada chamada.

    Returns
    -------
    Inflector
        O singleton.
    """
    return _INSTANCE
