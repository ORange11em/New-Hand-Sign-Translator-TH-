"""Application-specific errors that can be shown safely in the GUI."""


class HandVoxError(Exception):
    """Base class for expected, user-facing HandVox errors."""


class ConfigurationError(HandVoxError):
    pass


class DataFileError(HandVoxError):
    pass


class LaunchError(HandVoxError):
    pass
