from __future__ import annotations

import random
import warnings
from argparse import ArgumentParser
from functools import partial
from pathlib import Path
from typing import NamedTuple

from reiz.db.connection import connect
from reiz.edgeql import EdgeQLSelect, EdgeQLSelector
from reiz.serialization.serializer import insert_file
from reiz.utilities import get_db_settings, get_executor, logger, read_config

FILE_CACHE = frozenset()


def sync_cache(connector):
    global FILE_CACHE
    with connector() as connection:
        selection = EdgeQLSelect(
            "Module", selections=[EdgeQLSelector("filename")]
        )
        result_set = connection.query(selection.construct())

    FILE_CACHE = frozenset(module.filename for module in result_set)


class Stats(NamedTuple):
    cached: int
    failed: int
    inserted: int

    def __add__(self, other):
        if isinstance(other, self.__class__):
            return self.__class__(
                cached=self.cached + other.cached,
                failed=self.failed + other.failed,
                inserted=self.inserted + other.inserted,
            )
        else:
            return NotImplemented

    def __radd__(self, other):
        if isinstance(other, int):
            return self
        elif isinstance(other, self.__class__):
            return self + other
        else:
            return NotImplemented


def insert_project(connector, directory):
    inserted, cached, failed = 0, 0, 0
    with connector() as connection:
        for file in directory.glob("**/*.py"):
            filename = str(file)
            if filename in FILE_CACHE:
                cached += 1
                continue

            try:
                insert_file(connection, file)
            except ArithmeticError:
                failed += 1
                logger.info(
                    "%s couldn't inserted due to an edgedb related failure",
                    file,
                )
            except Exception:
                failed += 1
                logger.exception("%s couldn't inserted", file)
            else:
                inserted += 1
                logger.info("%s successfully inserted", file)
    return directory, Stats(cached=cached, failed=failed, inserted=inserted)


def insert(clean_dir, workers, **db_opts):
    cache = read_config(clean_dir / "info.json")
    random.shuffle(cache)
    connector = partial(connect, **db_opts)
    bound_inserter = partial(insert_project, connector)

    stats = []
    sync_cache(connector)
    try:
        with get_executor(workers) as executor:
            for project_path, project_stats in executor.map(
                bound_inserter, map(clean_dir.joinpath, cache)
            ):
                stats.append(project_stats)
                logger.info(
                    "%s inserted, stats: %r", project_path.name, project_stats
                )
    finally:
        total_stats = sum(stats)
        logger.info("total stats: %r", total_stats)


def main():
    parser = ArgumentParser()
    parser.add_argument("clean_dir", type=Path)
    parser.add_argument("--dsn", default=get_db_settings()["dsn"])
    parser.add_argument("--database", default=get_db_settings()["database"])
    parser.add_argument("--workers", type=int, default=1)
    options = parser.parse_args()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        insert(**vars(options))


if __name__ == "__main__":
    main()
