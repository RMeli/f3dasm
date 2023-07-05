#                                                                       Modules
# =============================================================================

# Local
from .design import DesignSpace, make_nd_continuous_design
from .experimentdata import ExperimentData
from .parameter import (PARAMETERS, CategoricalParameter, ConstantParameter,
                        ContinuousParameter, DiscreteParameter, Parameter)
from .trial import Trial

#                                                          Authorship & Credits
# =============================================================================
__author__ = 'Martin van der Schelling (M.P.vanderSchelling@tudelft.nl)'
__credits__ = ['Martin van der Schelling']
__status__ = 'Stable'
# =============================================================================
#
# =============================================================================

__all__ = [
    'DesignSpace',
    'make_nd_continuous_design',
    'ExperimentData',
    'PARAMETERS',
    'CategoricalParameter',
    'ConstantParameter',
    'ContinuousParameter',
    'DiscreteParameter',
    'Parameter',
    'Trial'
]
