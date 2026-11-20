"""公共配置：把项目根目录和 tests 目录加进 import 路径。

测试文件里就不用各自再写一遍 sys.path 了；`case_loader` 也能直接被 import。
"""

from __future__ import annotations

import pathlib
import sys

_TESTS_DIR = pathlib.Path(__file__).resolve().parent

sys.path.insert(0, str(_TESTS_DIR.parent))
sys.path.insert(0, str(_TESTS_DIR))
