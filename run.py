#!/usr/bin/env python3
"""Запуск Kryo из исходников: python run.py

Перед импортом приложения готовим окружение: папка со своими библиотеками
попадает в sys.path, а недостающие зависимости ставятся туда же. Так запуск
работает на любом устройстве и без прав администратора.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if sys.version_info < (3, 10):
        sys.exit(f"нужен Python 3.10 или новее, а здесь {sys.version.split()[0]}")
    from kryonyx import bootstrap

    bootstrap.ensure()
    from kryonyx.main import main

    sys.exit(main())
