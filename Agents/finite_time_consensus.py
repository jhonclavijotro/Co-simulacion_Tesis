"""
Módulo de compatibilidad retrocompatible para Agents.fixed_time_consensus.

ADVERTENCIA: Este módulo ha sido renombrado a Agents.fixed_time_consensus para
reflejar rigurosamente la ley de control secundario en tiempo fijo (FxTS) implementada.
Se conserva este shim para no romper scripts, despliegues ni referencias heredadas.
"""

import warnings
from Agents.fixed_time_consensus import (
    FixedTimeConsensusAgent,
    FiniteTimeConsensusAgent,
    sig_pow,
)

warnings.warn(
    "Agents.finite_time_consensus está obsoleto y ha sido renombrado a Agents.fixed_time_consensus. "
    "Por favor actualice sus importaciones a Agents.fixed_time_consensus.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "FixedTimeConsensusAgent",
    "FiniteTimeConsensusAgent",
    "sig_pow",
]
