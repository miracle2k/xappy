"""settings.py: Base settings

"""

# Path to directory holding xappy databases
XAPPY_DATABASE_DIR = 'xappydbs'

# Base URL of service
BASEURL = 'search/'

try:
    from local_settings import *
except ImportError:
    pass
