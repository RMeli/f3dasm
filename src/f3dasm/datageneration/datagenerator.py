"""
Interface class for data generators
"""

#                                                                       Modules
# =============================================================================

from ..design.design import Design
from ..logger import time_and_log

#                                                          Authorship & Credits
# =============================================================================
__author__ = "Martin van der Schelling (M.P.vanderSchelling@tudelft.nl)"
__credits__ = ["Martin van der Schelling"]
__status__ = "Alpha"
# =============================================================================
#
# =============================================================================


class DataGenerator:
    """Base class for a data generator"""

    def pre_process() -> None:
        """Function that handles the pre-processing"""
        ...
        # raise NotImplementedError("No pre-process function implemented!")

    def execute() -> None:
        """Function that calls the FEM simulator the pre-processing"""
        raise NotImplementedError("No execute function implemented!")

    def post_process() -> None:
        """Function that handles the post-processing"""
        ...

    @time_and_log
    def run(self, design: Design, **kwargs) -> Design:
        """Run the data generator

        Parameters
        ----------
        design : Design
            The design to run the data generator on

        Returns
        -------
        Design
            Processed design
        """
        # Cache the design
        self.design: Design = design

        self.pre_process(**kwargs)
        self.execute(**kwargs)
        self.post_process(**kwargs)

        return self.design
