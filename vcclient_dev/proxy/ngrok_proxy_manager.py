import ngrok


class NgrokProxyManager:
    _instance = None

    def get_instance(cls):

        if cls._instance is None:
            cls._instance = cls()

            return cls._instance

        return cls._instance

    get_instance = classmethod(get_instance)

    def __init__(self):

        self.listener = None

    def start(self=None, port=None, token=None):

        self.listener = ngrok.forward(port, authtoken=token)

        return self.listener.url()

    def get_proxy_url(self):

        return self.listener.url()

    def stop(self):

        pass

    # WARNING: Decompyle incomplete
