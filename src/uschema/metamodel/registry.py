"""Carregamento e registro do metamodelo U-Schema (Fase 0.1).

Carrega ``resources/uschema.ecore`` via PyEcore usando a **API reflexiva**
(manipular ``EObject`` dinamicamente, sem codegen), e registra o ``EPackage``
resultante no ``metamodel_registry`` para que instâncias XMI (Fase 0.2) possam
ser desserializadas contra ele.

O metamodelo é um **único** ``EPackage`` (nsURI ``http://www.modelum.es/USchema``,
19 EClasses), então não há gap de ``genmodel`` multi-arquivo a tratar.
"""

from __future__ import annotations

from pathlib import Path

from pyecore.ecore import EPackage
from pyecore.resources import Resource, ResourceSet

# Caminho do .ecore versionado em resources/ (raiz do repo → resources/uschema.ecore).
DEFAULT_ECORE_PATH = Path(__file__).resolve().parents[3] / "resources" / "uschema.ecore"


def load_metamodel(ecore_path: Path = DEFAULT_ECORE_PATH) -> EPackage:
    """Carregar o metamodelo U-Schema para uso reflexivo.

    Apenas carrega e devolve o ``EPackage`` raiz. Registrá-lo num
    ``metamodel_registry`` para desserializar instâncias é feito por quem lê os
    XMIs (ver ``xmi.load_model``), pois o registro é por ``ResourceSet``.

    Parameters
    ----------
    ecore_path : Path, optional
        Caminho para o ``uschema.ecore``. Por padrão, o versionado em
        ``resources/``.

    Returns
    -------
    EPackage
        O pacote raiz do metamodelo (o ``USchema`` EPackage).

    Raises
    ------
    FileNotFoundError
        Se ``ecore_path`` não existir.

    Examples
    --------
    >>> pkg = load_metamodel()
    >>> pkg.name
    'USchema'
    >>> len(list(pkg.eClassifiers))
    19
    """
    resource_set = ResourceSet()

    str_ecore_path = str(ecore_path)

    resource: Resource = resource_set.get_resource(str_ecore_path)

    e_package: EPackage = resource.contents[0]

    return e_package
