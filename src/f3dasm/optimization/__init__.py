"""
Some API information about the opitmizers
"""
#                                                                       Modules
# =============================================================================

# Standard
import sys
from itertools import chain
from os import path
from typing import List

# Local
from .._imports import try_import
from .cg import CG, CG_Parameters
from .lbfgsb import LBFGSB, LBFGSB_Parameters
from .neldermead import NelderMead, NelderMead_Parameters
from .optimizer import Optimizer
from .randomsearch import RandomSearch, RandomSearch_Parameters

# Try importing f3dasm_optimize package
with try_import('f3dasm_optimize') as _imports:
    import f3dasm_optimize


#                                                          Authorship & Credits
# =============================================================================
__author__ = 'Martin van der Schelling (M.P.vanderSchelling@tudelft.nl)'
__credits__ = ['Martin van der Schelling']
__status__ = 'Stable'
# =============================================================================
#
# =============================================================================

# List of available optimizers
OPTIMIZERS: List[Optimizer] = [RandomSearch, CG, LBFGSB, NelderMead]


__all__ = [
    'CG',
    'CG_Parameters',
    'LBFGSB',
    'LBFGSB_Parameters',
    'NelderMead',
    'NelderMead_Parameters',
    'Optimizer',
    'RandomSearch',
    'RandomSearch_Parameters',
    'OPTIMIZERS'
]

# Add the optimizers from f3dasm_optimize if applicable
if _imports.is_successful():
    OPTIMIZERS.extend(f3dasm_optimize.OPTIMIZERS)
    __all__.extend(f3dasm_optimize.__all__)
