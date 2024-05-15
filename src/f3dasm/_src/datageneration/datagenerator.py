"""
Interface class for data generators
"""

#                                                                       Modules
# =============================================================================


from __future__ import annotations

# Standard
import inspect
import sys
from abc import abstractmethod
from functools import partial
from typing import Any, Callable, Dict, List, Optional

if sys.version_info < (3, 8):  # NOQA
    from typing_extensions import Protocol  # NOQA
else:
    from typing import Protocol

# Third-party
import numpy as np

# Local
from ..design.domain import Domain
from ..experimentdata.experimentsample import _experimentsample_factory
from ..logger import time_and_log

#                                                          Authorship & Credits
# =============================================================================
__author__ = "Martin van der Schelling (M.P.vanderSchelling@tudelft.nl)"
__credits__ = ["Martin van der Schelling"]
__status__ = "Alpha"
# =============================================================================
#
# =============================================================================


class ExperimentSample(Protocol):
    def get(self, key: str) -> Any:
        ...

    def store(self, object: Any, name: str, to_disk: bool) -> None:
        ...

    @property
    def job_number(self) -> int:
        ...


class DataGenerator:
    """Base class for a data generator"""

    def pre_process(
            self, experiment_sample: ExperimentSample, **kwargs) -> None:
        """Interface function that handles the pre-processing of
         the data generator

        Note
        ----
        If not implemented the function will be skipped.

        The experiment_sample is cached inside the data generator. This \
        allows the user to access the experiment_sample in the pre_process, \
        execute and post_process functions as a class variable called \
        self.experiment_sample.
        """
        ...

    @abstractmethod
    def execute(self, **kwargs) -> None:
        """Interface function that handles the execution of the data generator

        Raises
        ------
        NotImplementedError
            If the function is not implemented by the user

        Note
        ----
        The experiment_sample is cached inside the data generator. This \
        allows the user to access the experiment_sample in \
        the pre_process, execute and post_process functions as a class \
        variable called self.experiment_sample.
        """

        ...

    def post_process(
            self, experiment_sample: ExperimentSample, **kwargs) -> None:
        """Interface function that handles the post-processing \
        of the data generator

        Note
        ----
        If not implemented the function will be skipped.

        The experiment_sample is cached inside the data generator. This \
        allows the user to access the experiment_sample in the \
        pre_process, execute and post_process functions as a class variable \
        called self.experiment_sample.
        """
        ...

    @time_and_log
    def _run(
            self, experiment_sample: ExperimentSample | np.ndarray,
            domain: Optional[Domain] = None,
            **kwargs) -> ExperimentSample:
        """
        Run the data generator.
        This function chains the following methods together

        * pre_process(); to combine the experiment_sample and the parameters \
        of the data generator to an input file that can be used to run the \
        data generator.

        * execute(); to run the data generator and generate the response of \
        the experiment

        * post_process(); to process the response of the experiment and store \
        it back in the experiment_sample

        The function also caches the experiment_sample in the data generator. \
        This allows the user to access the experiment_sample in the \
        pre_process, execute and post_process functions as a class variable \
        called self.experiment_sample.

        Parameters
        ----------
        ExperimentSample : ExperimentSample
            The design to run the data generator on
        domain : Domain, optional
            The domain of the data generator, by default None

        kwargs : dict
            The keyword arguments to pass to the pre_process, execute \
            and post_process

        Returns
        -------
        ExperimentSample
            Processed design with the response of the data generator \
            saved in the experiment_sample
        """
        # Cache the design
        self.experiment_sample: ExperimentSample = _experimentsample_factory(
            experiment_sample=experiment_sample, domain=domain)

        self._pre_simulation()

        self.pre_process(self.experiment_sample, **kwargs)
        self.execute(**kwargs)
        self.post_process(self.experiment_sample, **kwargs)

        self._post_simulation()

        return self.experiment_sample

    def _pre_simulation(self) -> None:
        ...

    def _post_simulation(self) -> None:
        ...

    def add_pre_process(self, func: Callable, **kwargs):
        """Add a pre-processing function to the data generator

        Parameters
        ----------
        func : Callable
            The function to add to the pre-processing
        kwargs : dict
            The keyword arguments to pass to the pre-processing function
        """
        self.pre_process = partial(func, **kwargs)

    def add_post_process(self, func: Callable, **kwargs):
        """Add a post-processing function to the data generator

        Parameters
        ----------
        func : Callable
            The function to add to the post-processing
        kwargs : dict
            The keyword arguments to pass to the post-processing function
        """
        self.post_process = partial(func, **kwargs)


def convert_function(f: Callable,
                     output: Optional[List[str]] = None,
                     kwargs: Optional[Dict[str, Any]] = None,
                     to_disk: Optional[List[str]] = None) -> DataGenerator:
    """
    Converts a given function `f` into a `DataGenerator` object.

    Parameters
    ----------
    f : Callable
        The function to be converted.
    output : Optional[List[str]], optional
        A list of names for the return values of the function.
        Defaults to None.
    kwargs : Optional[Dict[str, Any]], optional
        Additional keyword arguments passed to the function. Defaults to None.
    to_disk : Optional[List[str]], optional
        The list of output names where the value needs to be stored on disk.
        Defaults to None.

    Returns
    -------
    DataGenerator
        A converted `DataGenerator` object.

    Notes
    -----

    The function `f` can have any number of arguments and any number of returns
    as long as they are consistent with the `input` and `output` arguments that
    are given to this function.
    """
    signature = inspect.signature(f)
    input = list(signature.parameters)
    kwargs = kwargs if kwargs is not None else {}
    to_disk = to_disk if to_disk is not None else []
    output = output if output is not None else []

    class TempDataGenerator(DataGenerator):
        def execute(self, **_kwargs) -> None:
            _input = {input_name: self.experiment_sample.get(input_name)
                      for input_name in input}
            _output = f(**_input, **kwargs)

            # check if output is empty
            if output is None:
                return

            if len(output) == 1:
                _output = (_output,)

            for name, value in zip(output, _output):
                if name in to_disk:
                    self.experiment_sample.store(name=name,
                                                 object=value,
                                                 to_disk=True)
                else:
                    self.experiment_sample.store(name=name,
                                                 object=value,
                                                 to_disk=False)

    return TempDataGenerator()
