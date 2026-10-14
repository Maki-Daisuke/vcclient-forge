def parse_bool_arg(arg=None):
    if isinstance(arg, bool):
        return arg
    if isinstance(arg, str):
        return arg.lower() in ("true", "1", "yes", "y")
    return bool(arg)
