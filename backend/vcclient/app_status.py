class AppStatus:
    _instance: AppStatus | None = None

    @classmethod
    def get_instance(cls) -> AppStatus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.end_flag = False

    def stop_app(self) -> None:
        self.end_flag = True
