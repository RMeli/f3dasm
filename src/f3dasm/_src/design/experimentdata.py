"""
The ExperimentData object is the main object used to store implementations of a design-of-experiments,
keep track of results, perform optimization and extract data for machine learning purposes.
"""

#                                                                       Modules
# =============================================================================

from __future__ import annotations

# Standard
import json
import os
import sys
import traceback
from copy import deepcopy
from functools import wraps
from io import TextIOWrapper
from pathlib import Path
from time import sleep

if sys.version_info < (3, 8):  # NOQA
    from typing_extensions import Protocol  # NOQA
else:
    from typing import Protocol

from typing import (Any, Callable, Dict, Iterable, Iterator, List, Optional,
                    Tuple, Type, Union)

# Third-party
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from filelock import FileLock
from hydra.utils import get_original_cwd, instantiate
from omegaconf import DictConfig
from pathos.helpers import mp

# Local
from ..logger import logger
from ._data import _Data
from ._jobqueue import NoOpenJobsError, Status, _JobQueue
from .domain import Domain
from .experimentsample import ExperimentSample
from .parameter import Parameter

#                                                          Authorship & Credits
# =============================================================================
__author__ = 'Martin van der Schelling (M.P.vanderSchelling@tudelft.nl)'
__credits__ = ['Martin van der Schelling']
__status__ = 'Stable'
# =============================================================================
#
# =============================================================================

DataTypes = Union[pd.DataFrame, np.ndarray, Path, str, _Data]


class _OptimizerParameters(Protocol):
    maxiter: int
    population: int


class _Optimizer(Protocol):
    hyperparameters: _OptimizerParameters
    type: str

    def _callback(self, xk: np.ndarray) -> None:
        ...

    def run_algorithm(self, iterations: int, data_generator: _DataGenerator):
        ...

    def _check_number_of_datapoints(self) -> None:
        ...

    def update_step(self, data_generator: _DataGenerator) -> ExperimentData:
        ...

    def _construct_model(self, data_generator: _DataGenerator) -> None:
        ...

    def set_x0(self, experiment_data: ExperimentData) -> None:
        ...

    def set_data(self, data: ExperimentData) -> None:
        ...

    def reset(self) -> None:
        ...


class _DataGenerator(Protocol):
    def run(self, experiment_sample: ExperimentSample) -> ExperimentSample:
        ...


class _Sampler(Protocol):
    """Protocol class for sampling methods."""
    def get_samples(numsamples: int) -> ExperimentData:
        ...

    @classmethod
    def from_yaml(cls, domain_config: DictConfig, sampler_config: DictConfig) -> '_Sampler':
        """Create a sampler from a yaml configuration"""

        args = {**sampler_config, 'domain': None}
        sampler: _Sampler = instantiate(args)
        sampler.domain = Domain.from_yaml(domain_config)
        return sampler


class _ExperimentSampleCallable(Protocol):
    def __call__(experiment_sample: ExperimentSample, **kwargs) -> ExperimentSample:
        ...


class ExperimentData:
    """
    A class that contains data for experiments.
    """

    def __init__(self, domain: Optional[Domain] = None, input_data: Optional[DataTypes] = None,
                 output_data: Optional[DataTypes] = None, jobs: Optional[Path | str] = None,
                 filename: Optional[str] = 'experimentdata'):
        """
        Initializes an instance of ExperimentData.

        Parameters
        ----------
        domain : Domain, optional
            The domain of the experiment, by default None
        input_data : DataTypes, optional
            The input data of the experiment, by default None
        output_data : DataTypes, optional
            The output data of the experiment, by default None
        jobs : Path | str, optional
            The path to the jobs file, by default None
        filename : str, optional
            The filename of the experiment, by default 'experimentdata'
        """
        self.filename = filename

        self.input_data = self._construct_data(input_data)
        self.output_data = self._construct_data(output_data)

        if self.output_data.is_empty():
            self.output_data = _Data.from_indices(self.input_data.indices)
            job_value = Status.OPEN

        else:
            job_value = Status.FINISHED

        self.domain = self._construct_domain(domain)

        if self.input_data.is_empty():
            self.input_data = _Data.from_domain(domain)

        if isinstance(jobs, (Path, str)):
            self.jobs = _JobQueue.from_file(Path(jobs))

        self.jobs = _JobQueue.from_data(self.input_data, value=job_value)

    def _construct_data(self, data: DataTypes) -> _Data:
        if data is None:
            return _Data()

        elif isinstance(data, _Data):
            return data

        elif isinstance(data, pd.DataFrame):
            return _Data.from_dataframe(data)

        elif isinstance(data, (Path, str)):
            if data.suffix == '.csv':
                return _Data.from_csv(data)

            return _Data.from_file(data)

        elif isinstance(data, np.ndarray):
            return _Data.from_numpy(data)

        else:
            raise TypeError(
                f"Data must be of type _Data, pd.DataFrame, np.ndarray, Path or str, not {type(data)}")

    def _construct_domain(self, domain: Union[None, Domain]) -> Domain:
        if isinstance(domain, Domain):
            return domain

        elif isinstance(domain, (Path, str)):
            return Domain.from_file(Path(domain))

        elif self.input_data.is_empty() and domain is None:
            return Domain()

        elif domain is None:
            return Domain.from_data(self.input_data)

        else:
            raise TypeError(f"Domain must be of type Domain or None, not {type(domain)}")

    def __len__(self):
        """The len() method returns the number of datapoints"""
        return len(self.input_data)

    def __iter__(self) -> Iterator[Tuple[Dict[str, Any]]]:
        return self.input_data.__iter__()

    def __next__(self):
        return self.input_data.__next__()

    def __add__(self, other: ExperimentData | ExperimentSample) -> ExperimentData:
        """The + operator combines two ExperimentData objects"""
        # Check if the domains are the same

        if not isinstance(other, (ExperimentData, ExperimentSample)):
            raise TypeError(f"Can only add ExperimentData or ExperimentSample objects, not {type(other)}")

        if isinstance(other, ExperimentData) and self.domain != other.domain:
            raise ValueError("Cannot add ExperimentData objects with different domains")

        return ExperimentData._from_object(self.input_data + other.input_data,
                                           self.output_data + other.output_data,
                                           self.jobs + other.jobs, self.domain,
                                           self.filename)

    def __eq__(self, __o: ExperimentData) -> bool:
        return all([self.input_data == __o.input_data,
                    self.output_data == __o.output_data,
                    self.jobs == __o.jobs,
                    self.domain == __o.domain])

    def __getitem__(self, index: int | slice | Iterable[int]) -> _Data:
        """The [] operator returns a single datapoint or a subset of datapoints"""
        return ExperimentData._from_object(self.input_data[index], self.output_data[index],
                                           self.jobs[index], self.domain, self.filename)

    def _repr_html_(self) -> str:
        return self.input_data.combine_data_to_multiindex(self.output_data)._repr_html_()

    def _access_file(operation: Callable) -> Callable:
        """Wrapper for accessing a single resource with a file lock

        Returns
        -------
        decorator
        """
        @wraps(operation)
        def wrapper_func(self, *args, **kwargs) -> None:
            lock = FileLock(Path(self.filename).with_suffix('.lock'))
            with lock:
                self = ExperimentData.from_file(filename=Path(self.filename))
                value = operation(self, *args, **kwargs)
                self.store(filename=Path(self.filename))
            return value

        return wrapper_func

    #                                                      Alternative Constructors
    # =============================================================================

    @classmethod
    def from_file(cls: Type[ExperimentData], filename: str = 'experimentdata',
                  text_io: Optional[TextIOWrapper] = None) -> ExperimentData:
        """Create an ExperimentData object from .csv and .json files.

        Parameters
        ----------
        filename : str, optional
            Name of the file, excluding suffix, by default 'experimentdata'.
        text_io : TextIOWrapper or None, optional
            Text I/O wrapper object for reading the file, by default None.

        Returns
        -------
        ExperimentData
            ExperimentData object containing the loaded data.
        """
        try:
            return cls._from_file_attempt(filename, text_io)
        except FileNotFoundError:
            try:
                filename_with_path = Path(get_original_cwd()) / filename
            except ValueError:  # get_original_cwd() hydra initialization error
                raise FileNotFoundError(f"Cannot find the file {filename} !")

            return cls._from_file_attempt(filename_with_path, text_io)

    @classmethod
    def from_sampling(cls, sampler: _Sampler, filename: str = 'experimentdata') -> ExperimentData:
        """Create an ExperimentData object from a sampler.

        Parameters
        ----------
        sampler : Sampler
            Sampler object containing the sampling strategy.

        Returns
        -------
        ExperimentData
            ExperimentData object containing the sampled data.
        """
        experimentdata = sampler.get_samples()
        experimentdata.filename = filename
        return experimentdata

    @classmethod
    def from_dataframe(cls, dataframe_input: pd.DataFrame, dataframe_output: Optional[pd.DataFrame] = None,
                       domain: Optional[Domain] = None, filename: Optional[str] = 'experimentdata') -> ExperimentData:
        """Create an ExperimentData object from a pandas dataframe.

        Parameters
        ----------
        dataframe_input : pd.DataFrame
            Pandas dataframe containing the data with columns corresponding to the
            input parameter names
        dataframe_output : pd.DataFrame, optional
            Pandas dataframe containing the data with columns corresponding to the
            output parameter names, by default None
        domain : Domain, optional
            Domain object defining the input and output spaces of the experiment. If not given,
            the domain is inferred from the input data. By default None.
        filename : str, optional
            Name of the created experimentdata, excluding suffix, by default 'experimentdata'.

        Returns
        -------
        ExperimentData
            ExperimentData object containing the loaded data.
        """
        if domain is None:
            # Infer the domain from the input data
            domain = Domain.from_dataframe(dataframe_input)

        experimentdata = cls(domain=domain, filename=filename)
        experimentdata.input_data = _Data.from_dataframe(dataframe_input)

        if dataframe_output is not None:
            experimentdata.output_data = _Data.from_dataframe(dataframe_output)
            value = Status.FINISHED
        elif dataframe_output is None:
            experimentdata.output_data = _Data.from_indices(experimentdata.input_data.indices)
            value = Status.OPEN

        experimentdata.jobs = _JobQueue.from_data(experimentdata.input_data, value)

        return experimentdata

    @classmethod
    def from_csv(cls, filename_input: Path, filename_output: Optional[Path] = None,
                 domain: Optional[Domain] = None) -> ExperimentData:
        """Create an ExperimentData object from .csv files.

        Parameters
        ----------
        filename_input : Path
            filename of the input .csv file.
        filename_output : Path, optional
            filename of the output .csv file, by default None
        domain : Domain, optional
            Domain object, by default None

        Returns
        -------
        ExperimentData
            ExperimentData object containing the loaded data.
        """
        # Read the input datat csv file as a pandas dataframe
        df_input = pd.read_csv(filename_input.with_suffix('.csv'), index_col=0)

        # Read the output data csv file as a pandas dataframe
        if filename_output is not None:
            df_output = pd.read_csv(filename_output.with_suffix('.csv'), index_col=0)
        else:
            df_output = None

        return cls.from_dataframe(df_input, df_output, domain, filename_input.stem)

    @classmethod
    def from_numpy(cls, domain: Domain, input_array: np.ndarray,
                   output_array: Optional[np.ndarray] = None, output_names: Iterable[str] = ['y'],
                   filename: Optional[str] = 'experimentdata') -> ExperimentData:
        """Create an ExperimentData object from numpy arrays.

        Parameters
        ----------
        domain : Domain
            Domain of the search space
        input_array : np.ndarray
            2D numpy array containing the input data. The shape should be (n_samples, n_inputs)
        output_array : Optional[np.ndarray], optional
            2D numpy array containing the output data. The shape should be (n_samples, n_outputs)
        output_names : Iterable[str], optional
            Names of the output columns, by default ['y']
        filename : Optional[str], optional
            name of the created ExperimentData object, by default 'experimentdata'

        Returns
        -------
        ExperimentData
            ExperimentData object containing the loaded data.
        """

        dataframe_input = pd.DataFrame(input_array, columns=domain.names)
        if output_array is None:
            dataframe_output = None
        else:
            dataframe_output = pd.DataFrame(output_array, columns=output_names)
        return cls.from_dataframe(dataframe_input, dataframe_output, domain, filename)

    @classmethod
    def from_yaml(cls, config: DictConfig) -> ExperimentData:
        """Create an ExperimentData object from a hydra yaml configuration.

        Parameters
        ----------
        config : DictConfig
            A DictConfig object containing the configuration.

        Returns
        -------
        ExperimentData
            ExperimentData object containing the loaded data.
        """
        # Option 1: From exisiting ExperimentData files
        if 'from_file' in config.experimentdata:
            return cls.from_file(filename=config.experimentdata.from_file.filepath)

        # Option 2: Sample from the domain
        elif 'from_sampling' in config.experimentdata:
            sampler = _Sampler.from_yaml(config.domain, config.experimentdata.from_sampling)
            return sampler.get_samples()
            # return cls.from_sampling(sampler)

        # Option 3: Import the csv file
        elif 'from_csv' in config.experimentdata:
            if 'domain' in config:
                domain = Domain.from_yaml(config.domain)
            else:
                domain = None

            return cls.from_csv(filename_input=config.experimentdata.from_csv.input_filepath,
                                filename_output=config.experimentdata.from_csv.output_filepath, domain=domain)

        else:
            raise ValueError("No valid experimentdata option found in the config file!")

    @classmethod
    def _from_file_attempt(cls: Type[ExperimentData], filename: str,
                           text_io: Optional[TextIOWrapper]) -> ExperimentData:
        """Attempt to create an ExperimentData object from .csv and .json files.

        Parameters
        ----------
        filename : str
            Name of the file, excluding suffix.
        text_io : TextIOWrapper or None
            Text I/O wrapper object for reading the file.

        Returns
        -------
        ExperimentData
            ExperimentData object containing the loaded data.

        Raises
        ------
        FileNotFoundError
            If the file cannot be found.
        """

        try:
            domain = Domain.from_file(Path(f"{filename}_domain"))
            experimentdata = cls(domain=domain, filename=filename)
            experimentdata.input_data = _Data.from_file(Path(f"{filename}_data"), text_io)

            try:
                experimentdata.output_data = _Data.from_file(Path(f"{filename}_output"))
            except FileNotFoundError:
                experimentdata.output_data = _Data.from_indices(experimentdata.input_data.indices)

            experimentdata.jobs = _JobQueue.from_file(Path(f"{filename}_jobs"))
            return experimentdata
        except FileNotFoundError:
            raise FileNotFoundError(f"Cannot find the file {filename}_data.csv.")

    @classmethod
    def _from_object(cls: Type[ExperimentData], input_data: _Data, output_data: _Data,
                     jobs: _JobQueue, domain: Domain, filename: Optional[str] = 'experimentdata') -> ExperimentData:
        """Create an ExperimentData object from the given objects

        Parameters
        ----------
        cls : Type[ExperimentData]
            ExperimentData class
        input_data : _Data
            input_data
        output_data : _Data
            output_data
        jobs : _JobQueue
            jobs
        domain : Domain
            domain
        filename : str
            filename

        Returns
        -------
        ExperimentData
            ExperimentData object containing the loaded data and domain.
        """
        experimentdata = cls(domain=domain, filename=filename)
        experimentdata.input_data = input_data
        experimentdata.output_data = output_data
        experimentdata.jobs = jobs
        return experimentdata

    #                                                                        Export
    # =============================================================================

    def store(self, filename: str = None):
        """Store the ExperimentData to disk, with checking for a lock

        Parameters
        ----------
        filename : str, optional
            filename of the files to store, without suffix
        """
        if filename is None:
            filename = self.filename

        self.input_data.store(Path(f"{filename}_data"))
        self.output_data.store(Path(f"{filename}_output"))
        self.jobs.store(Path(f"{filename}_jobs"))
        self.domain.store(Path(f"{filename}_domain"))

    def to_numpy(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert the ExperimentData object to a tuple of numpy arrays.

        Returns
        -------
        tuple
            A tuple containing two numpy arrays, the first one for input columns, and the second for output columns.
        """
        return self.input_data.to_numpy(), self.output_data.to_numpy()

    def to_xarray(self) -> xr.Dataset:
        """
        Convert the ExperimentData object to an xarray Dataset.

        Returns
        -------
        xr.Dataset
            An xarray Dataset containing the data.
        """
        return xr.Dataset({'input': self.input_data.to_xarray('input_dim'),
                           'output': self.output_data.to_xarray('output_dim')})

    def get_n_best_output_samples(self, nosamples: int) -> pd.DataFrame:
        """
        Get the n best output samples from the ExperimentData object.

        Parameters
        ----------
        nosamples : int
            Number of samples to retrieve.

        Returns
        -------
        pd.DataFrame
            DataFrame containing the n best output samples.
        """
        df = self.output_data.n_best_samples(nosamples, self.output_data.names)
        return self.input_data.data.loc[df.index]

    def get_n_best_output(self, n_samples: int) -> ExperimentData:
        df = self.output_data.n_best_samples(n_samples, self.output_data.names)
        return self[df.index]

    def get_n_best_input_parameters_numpy(self, nosamples: int) -> np.ndarray:
        """
        Get the input parameters of the n best output samples from the ExperimentData object.

        Parameters
        ----------
        nosamples : int
            Number of samples to retrieve.

        Returns
        -------
        np.ndarray
            Numpy array containing the input parameters of the n best output samples.
        """
        return self.get_n_best_output_samples(nosamples).to_numpy()

    def get_input_data(self) -> pd.DataFrame:
        """
        Get the input data from the ExperimentData object.

        Returns
        -------
        pd.DataFrame
            DataFrame containing only the input data.
        """
        return self.input_data.data

    def get_output_data(self) -> pd.DataFrame:
        """
        Get the output data from the ExperimentData object.

        Returns
        -------
        pd.DataFrame
            DataFrame containing only the output data.
        """
        return self.output_data.data

    #                                                         Append or remove data
    # =============================================================================

    def add_experiments(self, experiment_sample: ExperimentSample | ExperimentData) -> None:
        """
        Add an ExperimentSample or ExperimentData to the ExperimentData attribute.

        Parameters
        ----------
        experiment_sample : ExperimentSample or ExperimentData
            Experiment(s) to add.
        """
        if isinstance(experiment_sample, ExperimentData):
            experiment_sample.reset_index()

        self.input_data += experiment_sample.input_data
        self.output_data += experiment_sample.output_data
        self.jobs += experiment_sample.jobs

    def add_new_input_column(self, name: str, parameter: Parameter) -> None:
        """Add a new input column to the ExperimentData object.

        Parameters
        ----------
        name
            name of the new input column
        parameter
            Parameter object of the new input column
        """
        self.input_data.add_column(name)
        self.domain.add(name, parameter)

    def add_new_output_column(self, name: str) -> None:
        """Add a new output column to the ExperimentData object.

        Parameters
        ----------
        name
            name of the new output column
        """
        self.output_data.add_column(name)

    def add(self, data: pd.DataFrame):
        """
        Append data to the ExperimentData object.

        Parameters
        ----------
        data : pd.DataFrame
            Data to append.
        """
        self.input_data.add(data)
        self.output_data.add_empty_rows(len(data))

        # Apparently you need to cast the types again
        # TODO: Breaks if values are NaN or infinite
        self.input_data.data = self.input_data.data.astype(
            self.domain._cast_types_dataframe())

        self.jobs.add(number_of_jobs=len(data))

    def add_numpy_arrays(self, input: np.ndarray, output: Optional[np.ndarray] = None):
        """
        Append a numpy array to the ExperimentData object.

        Parameters
        ----------
        input : np.ndarray
            2D numpy array to add to the input data.
        output : np.ndarray, optional
            2D numpy array to add to the output data. By default None.
        """
        self.input_data.add_numpy_arrays(input)

        if output is None:
            status = Status.OPEN
            self.output_data.add_empty_rows(len(input))
        else:
            status = Status.FINISHED
            self.output_data.add_numpy_arrays(output)

        self.jobs.add(number_of_jobs=len(input), status=status)

    def fill_output(self, output: np.ndarray, label: str = "y"):
        """
        Fill NaN values in the output data with the given array

        Parameters
        ----------
        output : np.ndarray
            Output data to fill
        label : str, optional
            Label of the output column to add to, by default "y".
        """
        if label not in self.output_data.names:
            self.output_data.add_column(label)

        filled_indices: Iterable[int] = self.output_data.fill_numpy_arrays(output)

        # Set the status of the filled indices to FINISHED
        self.jobs.mark_as_finished(filled_indices)

    def remove_rows_bottom(self, number_of_rows: int):
        """
        Remove a number of rows from the end of the ExperimentData object.

        Parameters
        ----------
        number_of_rows : int
            Number of rows to remove from the bottom.
        """
        if number_of_rows == 0:
            return  # Don't do anything if 0 rows need to be removed

        # get the last indices from data.data
        indices = self.input_data.data.index[-number_of_rows:]

        # remove the indices rows_to_remove from data.data
        self.input_data.remove(indices)
        self.output_data.remove(indices)
        self.jobs.remove(indices)

    def reset_index(self) -> None:
        """
        Reset the index of the ExperimentData object.
        """
        self.input_data.reset_index()
        self.output_data.reset_index()
        self.jobs.reset_index()

    #                                                                        ExperimentSample
    # =============================================================================

    def get_experiment_sample(self, index: int) -> ExperimentSample:
        """
        Gets the experiment_sample at the given index.

        Parameters
        ----------
        index : int
            The index of the experiment_sample to retrieve.

        Returns
        -------
        ExperimentSample
            The ExperimentSample at the given index.
        """
        return ExperimentSample(dict_input=self.input_data.get_data_dict(index),
                                dict_output=self.output_data.get_data_dict(index), jobnumber=index)

    def set_experiment_sample(self, experiment_sample: ExperimentSample) -> None:
        """
        Sets the ExperimentSample at the given index.

        Parameters
        ----------
        experiment_sample : ExperimentSample
            The ExperimentSample to set.
        """
        for column, value in experiment_sample.output_data.items():
            self.output_data.set_data(index=experiment_sample.job_number, value=value, column=column)

        self.jobs.mark_as_finished(experiment_sample._jobnumber)

    @_access_file
    def write_experiment_sample(self, experiment_sample: ExperimentSample) -> None:
        """
        Sets the ExperimentSample at the given index.

        Parameters
        ----------
        experiment_sample : ExperimentSample
            The ExperimentSample to set.
        """
        self.set_experiment_sample(experiment_sample)

    def access_open_job_data(self) -> ExperimentSample:
        """Get the data of the first available open job.

        Returns
        -------
        ExperimentSample
            The ExperimentSample object of the first available open job.
        """
        job_index = self.jobs.get_open_job()
        self.jobs.mark_as_in_progress(job_index)
        experiment_sample = self.get_experiment_sample(job_index)
        return experiment_sample

    @_access_file
    def get_open_job_data(self) -> ExperimentSample:
        """Get the data of the first available open job by
        accessing the ExperimenData on disk.

        Returns
        -------
        ExperimentSample
            The ExperimentSample object of the first available open job.
        """
        return self.access_open_job_data()

    #                                                                          Jobs
    # =============================================================================

    def set_error(self, index: int) -> None:
        """Mark the experiment_sample at the given index as error.

        Parameters
        ----------
        index
            index of the experiment_sample to mark as error
        """
        self.jobs.mark_as_error(index)
        self.output_data.set_data(index, value='ERROR')

    @_access_file
    def write_error(self, index: int):
        """Mark the experiment_sample at the given index as error and write to ExperimentData file.

        Parameters
        ----------
        index
            index of the experiment_sample to mark as error
        """
        self.set_error(index)

    @_access_file
    def is_all_finished(self) -> bool:
        """Check if all jobs are finished

        Returns
        -------
        bool
            True if all jobs are finished, False otherwise
        """
        return self.jobs.is_all_finished()

    def mark_all_open(self) -> None:
        """Mark all jobs as open"""
        self.jobs.mark_all_open()

    #                                                            Run datageneration
    # =============================================================================

    def run(self, data_generator: _DataGenerator, mode: str = 'sequential',
            kwargs: Optional[dict] = None) -> None:
        """Run any function over the entirery of the experiments

        Parameters
        ----------
        data_generator : DataGenerator
            data grenerator to use
        mode, optional
            operational mode, by default 'sequential'
        kwargs, optional
            Any keyword arguments that need to be supplied to the function, by default None

        Raises
        ------
        ValueError
            Raised when invalid parallelization mode is specified
        """
        if kwargs is None:
            kwargs = {}

        if mode.lower() == "sequential":
            return self._run_sequential(data_generator, kwargs)
        elif mode.lower() == "parallel":
            return self._run_multiprocessing(data_generator, kwargs)
        elif mode.lower() == "cluster":
            return self._run_cluster(data_generator, kwargs)
        else:
            raise ValueError("Invalid parallelization mode specified.")

    # create an alias for the self.run function called self.evaluate
    evaluate = run

    def _run_sequential(self, data_generator: _DataGenerator, kwargs: dict):
        """Run the operation sequentially

        Parameters
        ----------
        operation : ExperimentSampleCallable
            function execution for every entry in the ExperimentData object
        kwargs : dict
            Any keyword arguments that need to be supplied to the function

        Raises
        ------
        NoOpenJobsError
            Raised when there are no open jobs left
        """
        while True:
            try:
                experiment_sample = self.access_open_job_data()
                logger.debug(f"Accessed experiment_sample {experiment_sample._jobnumber}")
            except NoOpenJobsError:
                logger.debug("No Open Jobs left")
                break

            try:

                # If kwargs is empty dict
                if not kwargs:
                    logger.debug(f"Running experiment_sample {experiment_sample._jobnumber}")
                else:
                    logger.debug(
                        f"Running experiment_sample {experiment_sample._jobnumber} with kwargs {kwargs}")

                _experiment_sample = data_generator.run(experiment_sample, **kwargs)  # no *args!
                self.set_experiment_sample(_experiment_sample)
            except Exception as e:
                error_msg = f"Error in experiment_sample {experiment_sample._jobnumber}: {e}"
                error_traceback = traceback.format_exc()
                logger.error(f"{error_msg}\n{error_traceback}")
                self.set_error(experiment_sample._jobnumber)

    def _run_multiprocessing(self, data_generator: _DataGenerator, kwargs: dict):
        """Run the operation on multiple cores

        Parameters
        ----------
        operation : ExperimentSampleCallable
            function execution for every entry in the ExperimentData object
        kwargs : dict
            Any keyword arguments that need to be supplied to the function

        Raises
        ------
        NoOpenJobsError
            Raised when there are no open jobs left
        """
        # Get all the jobs
        options = []
        while True:
            try:
                experiment_sample = self.access_open_job_data()
                options.append(
                    ({'experiment_sample': experiment_sample, **kwargs},))
            except NoOpenJobsError:
                break

        def f(options: Dict[str, Any]) -> Any:
            logger.debug(f"Running experiment_sample {options['experiment_sample'].job_number}")
            return data_generator.run(**options)

        with mp.Pool() as pool:
            # maybe implement pool.starmap_async ?
            _experiment_samples: List[ExperimentSample] = pool.starmap(f, options)

        for _experiment_sample in _experiment_samples:
            self.set_experiment_sample(_experiment_sample)

    def _run_cluster(self, data_generator: _DataGenerator, kwargs: dict):
        """Run the operation on the cluster

        Parameters
        ----------
        operation : ExperimentSampleCallable
            function execution for every entry in the ExperimentData object
        kwargs : dict
            Any keyword arguments that need to be supplied to the function

        Raises
        ------
        NoOpenJobsError
            Raised when there are no open jobs left
        """
        # Retrieve the updated experimentdata object from disc
        try:
            self = self.from_file(self.filename)
        except FileNotFoundError:  # If not found, store current
            self.store()

        while True:
            try:
                experiment_sample = self.get_open_job_data()
            except NoOpenJobsError:
                logger.debug("No Open jobs left!")
                break

            try:
                _experiment_sample = data_generator.run(experiment_sample, **kwargs)
                self.write_experiment_sample(_experiment_sample)
            except Exception as e:
                error_msg = f"Error in experiment_sample {experiment_sample._jobnumber}: {e}"
                error_traceback = traceback.format_exc()
                logger.error(f"{error_msg}\n{error_traceback}")
                self.write_error(experiment_sample._jobnumber)
                continue

        self = self.from_file(self.filename)
        # Remove the lockfile from disk
        Path(self.filename).with_suffix('.lock').unlink(missing_ok=True)

    def optimize(self, optimizer: _Optimizer, data_generator: _DataGenerator, iterations: int) -> None:
        if optimizer.type == 'scipy':
            self._iterate_scipy(optimizer, data_generator, iterations)
        else:
            self._iterate(optimizer, data_generator, iterations)

    def _iterate(self, optimizer: _Optimizer, data_generator: _DataGenerator,
                 iterations: int, kwargs: Optional[dict] = None):

        optimizer.set_x0(self)
        optimizer._check_number_of_datapoints()

        optimizer._construct_model(data_generator)

        for _ in range(_number_of_updates(iterations, population=optimizer.hyperparameters.population)):
            new_samples = optimizer.update_step(data_generator)
            self.add_experiments(new_samples)

            # If applicable, evaluate the new designs:
            self.run(data_generator, mode='sequential', kwargs=kwargs)

            optimizer.set_data(self)

        # Remove overiterations
        self.remove_rows_bottom(_number_of_overiterations(
            iterations, population=optimizer.hyperparameters.population))

        # Reset the optimizer
        optimizer.reset()

    def _iterate_scipy(self, optimizer: _Optimizer, data_generator: _DataGenerator,
                       iterations: int, kwargs: Optional[dict] = None):

        optimizer.set_x0(self)
        n_data_before_iterate = len(self)
        optimizer._check_number_of_datapoints()

        optimizer.run_algorithm(iterations, data_generator)

        self.add_experiments(optimizer.data)

        # TODO: At the end, the data should have n_data_before_iterate + iterations amount of elements!
        # If x_new is empty, repeat best x0 to fill up total iteration
        if len(self) == n_data_before_iterate:
            repeated_last_element = self.get_n_best_input_parameters_numpy(
                nosamples=1).ravel()

            for repetition in range(iterations):
                self.add_experiments(ExperimentSample.from_numpy(repeated_last_element))

        # Repeat last iteration to fill up total iteration
        if len(self) < n_data_before_iterate + iterations:
            last_design = self.get_experiment_sample(len(self)-1)

            for repetition in range(iterations - (len(self) - n_data_before_iterate)):
                self.add_experiments(last_design)

        # Evaluate the function on the extra iterations
        self.run(data_generator, mode='sequential')

        # Reset the optimizer
        optimizer.reset()


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
