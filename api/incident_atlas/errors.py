from dataclasses import dataclass


@dataclass(slots=True)
class ApiError(Exception):
    status: int
    code: str
    detail: str
    retryable: bool = False


class ProviderTimeout(Exception):
    pass


class ProviderUnavailable(Exception):
    pass


class ProviderRefusal(Exception):
    pass


class ProviderInvalidOutput(Exception):
    pass
