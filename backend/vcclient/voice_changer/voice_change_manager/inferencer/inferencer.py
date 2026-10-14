from abc import ABC, abstractmethod


class Inferencer(ABC):
    def get_info(self=None):

        pass

    get_info = abstractmethod(get_info)
