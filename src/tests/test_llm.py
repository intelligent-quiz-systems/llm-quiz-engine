import json
import sys
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest