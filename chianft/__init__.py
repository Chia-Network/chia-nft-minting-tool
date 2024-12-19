from __future__ import annotations

from pkg_resources import DistributionNotFound, get_distribution

try:
    __version__ = get_distribution("chianft").version
except DistributionNotFound:
    # package is not installed
    __version__ = "unknown"
