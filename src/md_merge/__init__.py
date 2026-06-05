from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("pptmdmerge")
except PackageNotFoundError:
    __version__ = "unknown"
