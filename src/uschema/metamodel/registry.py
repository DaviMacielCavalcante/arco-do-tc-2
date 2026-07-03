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

# nsURI declarado no metamodelo; usado como chave no metamodel_registry.
USCHEMA_NS_URI = "http://www.modelum.es/USchema"


def load_metamodel(ecore_path: Path = DEFAULT_ECORE_PATH) -> EPackage:
    """Carregar o metamodelo U-Schema e registrá-lo para uso reflexivo.

    Parameters
    ----------
    ecore_path : Path, optional
        Caminho para o ``uschema.ecore``. Por padrão, o versionado em
        ``resources/``.

    Returns
    -------
    EPackage
        O pacote raiz do metamodelo (o ``USchema`` EPackage), já registrado
        no ``metamodel_registry`` do ``ResourceSet`` sob ``USCHEMA_NS_URI``.

    Raises
    ------
    FileNotFoundError
        Se ``ecore_path`` não existir.
    """
    resource_set = ResourceSet()

    str_ecore_path = str(ecore_path)

    resource: Resource = resource_set.get_resource(str_ecore_path)

    e_package: EPackage = resource.contents[0]

    resource_set.metamodel_registry[e_package.nsURI] = e_package

    return e_package
