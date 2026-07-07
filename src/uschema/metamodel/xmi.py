"""Leitura e escrita de modelos U-Schema em XMI (Fase 0.2).

Diferente de ``registry.load_metamodel`` (que carrega o *metamodelo*, o
``.ecore``), aqui carregamos *instâncias* — os modelos U-Schema (``model_*.xmi``)
gerados pelo oráculo. Para o PyEcore interpretar o XMI, o metamodelo tem de estar
**registrado no mesmo ResourceSet** que lê o modelo.
"""

from __future__ import annotations

from pathlib import Path

from pyecore.ecore import EObject, EPackage
from pyecore.resources import URI, Resource, ResourceSet


def load_model(xmi_path: Path, pkg: EPackage) -> EObject:
    """Carregar um modelo U-Schema (instância XMI) contra o metamodelo.

    Parameters
    ----------
    xmi_path : Path
        Caminho para o ``.xmi`` (ex.: ``resources/mongodb/model_northwind.xmi``).
    pkg : EPackage
        Metamodelo já carregado (saída de ``load_metamodel``).

    Returns
    -------
    EObject
        A raiz ``USchema`` do modelo carregado.

    Raises
    ------
    FileNotFoundError
        Se ``xmi_path`` não existir.
    """
    # Ponto-chave (diferente do load_metamodel): o registro do metamodelo é
    # POR ResourceSet e NÃO atravessa de um rset pra outro. Então este rset
    # novo precisa registrar `pkg` ANTES de ler o XMI — senão o PyEcore não
    # sabe interpretar os elementos do modelo.
    #

    resource_set = ResourceSet()

    resource_set.metamodel_registry[pkg.nsURI] = pkg

    resource: Resource = resource_set.get_resource(str(xmi_path))

    e_object: EObject = resource.contents[0]

    return e_object


def save_model(schema: EObject, xmi_path: Path) -> None:
    """Serializar um modelo U-Schema (raiz USchema) para um arquivo XMI.

    Parameters
    ----------
    schema : EObject
        A raiz ``USchema`` do modelo a ser salvo.
    xmi_path : Path
        Caminho onde ``.xmi`` será criado (ex.: ``output/mongodb/model_northwind.xmi``).

    Raises
    ------
    FileNotFoundError
        Se o diretório de ``xmi_path`` não existir.

    Examples
    --------
    >>> from uschema.metamodel.registry import load_metamodel
    >>> pkg = load_metamodel()
    >>> schema = load_model(Path("resources/mongodb/model_northwind.xmi"), pkg)
    >>> save_model(schema, Path("output/model_northwind.xmi"))
    """
    resource_set = ResourceSet()

    resource: Resource = resource_set.create_resource(URI(str(xmi_path)))

    resource.append(schema)

    resource.save()
