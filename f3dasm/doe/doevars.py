
#######################################################
# Data class for the manipulation and transformation  #
# of data within F3DASM                               #
#######################################################

"""
A dataclass for storing variables (features) during the DoE
"""

from dataclasses import dataclass, asdict
import numpy as np, array
# from data import DATA
from typing import Optional
from abc import ABC
import pandas as pd


## working example:
## Only parameters in the top level will be deserialized into a dataframe.
d = {'F11':[-0.15, 1], 
    'F12':[-0.1,0.15],
    'F22':[-0.15, 1], 
    'radius': [0.3, 5],  
    'material1': {'STEEL': {
                    'E': [0,100], 
                    'u': {0.1, 0.2, 0.3} 
                        }, 
                'CARBON': {
                    'E': 5, 
                    'u': 0.5, 
                    's': 0.1 
                    } 
                },
    'material2': {
                'CARBON': {
                    'x': 2
                    } 
                },
     }



class DoeVars:
    """Parameters for the design of experiments"""

    boundary_conditions: dict  # boundary conditions 
    rev: REV
    imperfections: Optional[Imperfection] = None

    def info(self):

        """ Overwrite print function"""

        print('-----------------------------------------------------')
        print('                       DOE INFO                      ')
        print('-----------------------------------------------------')
        print('\n')
        print('Boundary conditions:',self.boundary_conditions)
        print('REV dimensions:',self.rev.dimesionality)
        print('REV Lc:',self.rev.Lc)
        print('REV material:',self.rev.material.parameters)
        print('Microstructure shape:',self.rev.microstructure.shape)
        print('Microstructure material:',self.rev.microstructure.material.parameters)
        print('Imperfections:',self.imperfections)
        return '\n'

    # todo: convert values to array
    # todo: collect names for data colums
    # pass them on to data.py
    #TODO: implement own method to convert to pandas dataframe, use data.py as example
    
    def pandas_df(self, max_level=None):
        """
        Converts DoeVars into a normilized flat table.
        Args:
            max_level: Max number of levels(depth of dict) to normalize. if None, normalizes all levels.
        Returns:
            pandas dataframe
        """
        pd.set_option('display.max_columns', None) # show all colums in the dataframe
        normalized_dataframe = pd.json_normalize(asdict(self), max_level=max_level)
        return normalized_dataframe

    def as_dict(self):
        """
        Convert DoeVars into a nested dictionary
        """
        return asdict(self)


    def save(self,filename):

        """ Save doe-vars as pickle file
        
        Args:
            filename (string): filename for the pickle file
    
        Returns: 
            None
         """  

        data_frame = self.pandas_df()       # f3dasm data structure, numpy array
        data_frame.to_pickle(filename)




def main():

    from dataclasses import asdict
    import json
    import pandas as pd

    components= {'F11':[-0.15, 1], 'F12':[-0.1,0.15],'F22':[-0.15, 1]}
    mat1 = Material({'param1': 1, 'param2': 2})
    mat2 = Material({'elements': [{'name': 'CARBON', 'params': {'param1': 3, 'param2': 4, 'param3': 'value3'}}
                    ]
                })
    micro = CircleMicrostructure(material=mat2, diameter=[0.3, 0.5])
    rev = REV(Lc=4,material=mat1, microstructure=micro, dimesionality=2)
    doe = DoeVars(boundary_conditions=components, rev=rev)

    print(doe)

    # print(doe.info())
    # print(asdict(doe))
    # print(json.dumps(asdict(doe)))
     
    pd.set_option('display.max_columns', None)
    norm_pd = pd.json_normalize(asdict(doe), max_level=1)
    df = norm_pd.rename(columns= {"rev.Lc": "Lc"}, errors="raise")
    # print(df)
    print(doe.pandas_df())

    print(doe.as_dict())



if __name__ == "__main__":
    main()