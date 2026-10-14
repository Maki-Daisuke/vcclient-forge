from abc import ABC, abstractmethod


class Embedder(ABC):
    def extract_features(self=None, audio=None):
        """

        音声データから10msごとの特徴を抽出する

        Args:

            audio: np.array(np.float32 or np.float64) or torch.Tensor(torch.float32 or torch.float16) [n]



        Returns:

            feats: torch.Tensor or np.array [1, n, 768] or [1, n, 256]

        """

        pass

    extract_features = abstractmethod(extract_features)

    def get_info(self=None):

        pass

    get_info = abstractmethod(get_info)
