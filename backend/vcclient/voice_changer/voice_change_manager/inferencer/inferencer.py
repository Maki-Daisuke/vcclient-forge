from abc import ABC, abstractmethod


class Inferencer(ABC):
    @abstractmethod
    def get_info(self):
        pass
