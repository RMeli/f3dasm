"""
Module containing the interface class Optimizer
"""

#                                                                       Modules
# =============================================================================

# Standard
import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Tuple

# Third-party core
import numpy as np

# Locals
from ..datageneration.datagenerator import DataGenerator
from ..datageneration.functions.function import Function
from ..design.experimentdata import ExperimentData
from ..design.experimentsample import ExperimentSample

#                                                          Authorship & Credits
# =============================================================================
__author__ = 'Martin van der Schelling (M.P.vanderSchelling@tudelft.nl)'
__credits__ = ['Martin van der Schelling']
__status__ = 'Stable'
# =============================================================================
#
# =============================================================================


@dataclass
class OptimizerParameters:
    """Interface of a continuous benchmark function

    Parameters
    ----------
    population : int
        population of the optimizer update step
    force_bounds : bool
        force the optimizer to not exceed the boundaries of the domain
    """

    population: int = 1
    force_bounds: bool = True


@dataclass
class Optimizer:
    """Mainclass to inherit from to implement optimization algorithms

    Parameters
    -------
    data : f3dasm.base.data.Data
        Data-object
    hyperparameters : dict
        Dictionary with hyperparameteres
    seed : int
        seed to set the optimizer
    defaults : OptimizerParameters
        Default hyperparameter arguments
    name : str
        Name of the optimizer object. Default to classname. Optional.

    Raises
    ------
    NotImplementedError
        When no update step is implemented
    ValueError
        When number of datapoints is lower than the population
    """

    data: ExperimentData
    hyperparameters: Optional[Mapping[str, Any]] = field(default_factory=dict)
    seed: int = np.random.randint(low=0, high=1e5)
    algorithm: Any = field(init=False)
    parameter: OptimizerParameters = field(init=False)
    name: str = None

    def __post_init__(self):
        self._check_imports()

        if self.name is None:
            self.name = self.__class__.__name__

        if self.seed:
            self.set_seed(self.seed)

        self.init_parameters()
        self._set_hyperparameters()
        self.set_algorithm()

    def reset(self):
        """Reset the optimizer"""
        self.__post_init__()

    @staticmethod
    def set_seed(seed: int):
        """Set the seed of the optimizer. Needs to be inherited

        Parameters
        ----------
        seed
            seed for the random number generator
        """
        pass

    @staticmethod
    def _check_imports():
        ...

    def init_parameters(self):
        """Set the initialization parameters. This could be dynamic or static hyperparameters."""
        pass

    def set_algorithm(self):
        """If necessary, the algorithm needs to be set"""
        pass

    def update_step(self, function: DataGenerator) -> Tuple[np.ndarray, np.ndarray]:
        """One iteration of the algorithm.

        Parameters
        ----------
        function
            Objective function to evaluate

        Returns
        -------
            tuple of new input vector and resulting output vector


        Raises
        ------
        NotImplementedError
            You should implement an update step for your algorithm!
        """
        raise NotImplementedError(
            "You should implement an update step for your algorithm!")

    def set_data(self, data: ExperimentData):
        """Overwrite the data attribute

        Parameters
        ----------
        data
            data object
        """
        self.data = data

    def _set_hyperparameters(self):
        """New way of setting hyperparameters with dedicated class"""
        # if isinstance(self.hyperparameters, dict):
        #     # Create instance of the specific hyperparameter class
        self.parameter.__init__(**self.hyperparameters)

    def _check_number_of_datapoints(self):
        """Check if available data => population size"""
        if len(self.data) < self.parameter.population:
            raise ValueError(
                f'There are {len(self.data)} datapoints available, \
                     need {self.parameter.population} for update step!'
            )
        return

    def _force_bounds(self, x: np.ndarray) -> np.ndarray:
        """Force the input vector to be within the domain boundaries

        Parameters
        ----------
        x
            input vector

        Returns
        -------
            Input vector clipped to the bounds of the search space
        """
        if self.parameter.force_bounds:
            x = x.clip(min=self.data.domain.get_bounds()[
                       :, 0], max=self.data.domain.get_bounds()[:, 1])

        return x

    def _construct_model(self, function: DataGenerator):
        """Construct a model necessary for iteration with input of to be evaluated function

        Parameters
        ----------
        function
            function to be evaluated
        """
        pass

    def iterate(self, iterations: int, function: DataGenerator):
        """Calls the update_step function multiple times.

        Parameters
        ----------
        iterations
            number of iterations
        function
            objective function to evaluate
        """
        self._construct_model(function)

        self._check_number_of_datapoints()

        for _ in range(_number_of_updates(iterations, population=self.parameter.population)):
            x, y = self.update_step(function=function)

            experiment_samples_to_add = [(xi, yi) for xi, yi in zip(x, y)] if x.ndim > 1 else [(x, y)]

            for x_i, y_i in experiment_samples_to_add:
                self.data += ExperimentSample.from_numpy(x_i, y_i)

        # Remove overiterations
        self.data.remove_rows_bottom(_number_of_overiterations(
            iterations, population=self.parameter.population))

    def add_iteration_to_data(self, x: np.ndarray, y: np.ndarray):
        """Add the iteration to the dataframe

        Parameters
        ----------
        x
            input data
        y
            output data
        """
        self.data.add_numpy_arrays(input=x, output=y)

    def extract_data(self) -> ExperimentData:
        """Returns a copy of the data

        Returns
        -------
            copy of the data
        """
        return deepcopy(self.data)

    def get_name(self) -> str:
        """Retrieve the name of the optimizers

        Returns
        -------
            name of the optimizer
        """
        return self.name

    def get_info(self) -> List[str]:
        """Give a list of characteristic features of this optimizer

        Returns
        -------
            List of strings denoting the characteristics of this optimizer
        """
        return []


def _number_of_updates(iterations: int, population: int):
    """Calculate number of update steps to acquire the correct number of iterations

    Parameters
    ----------
    iterations
        number of desired iteration steps
    population
        the population size of the optimizer

    Returns
    -------
        number of consecutive update steps
    """
    return iterations // population + (iterations % population > 0)


def _number_of_overiterations(iterations: int, population: int) -> int:
    """Calculate the number of iterations that are over the iteration limit

    Parameters
    ----------
    iterations
        number of desired iteration steos
    population
        the population size of the optimizer

    Returns
    -------
        number of iterations that are over the limit
    """
    overiterations: int = iterations % population
    if overiterations == 0:
        return overiterations
    else:
        return population - overiterations
