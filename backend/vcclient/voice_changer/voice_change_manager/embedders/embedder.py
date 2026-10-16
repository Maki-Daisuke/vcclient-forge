from abc import ABC, abstractmethod


class Embedder(ABC):
    @abstractmethod
    def extract_features(self, audio):
        """
        音声データから10msごとの特徴を抽出する

        Args:
            audio: np.array(np.float32 or np.float64) or torch.Tensor(torch.float32 or torch.float16) [n]

        Returns:
            feats: torch.Tensor or np.array [1, n, 768] or [1, n, 256]
        """
        pass

    @abstractmethod
    def get_info(self):
        pass
