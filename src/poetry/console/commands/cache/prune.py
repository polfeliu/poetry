from __future__ import annotations

from typing import TYPE_CHECKING
from typing import ClassVar

from cleo.helpers import option

from poetry.config.config import Config
from poetry.console.commands.command import Command
from poetry.installation.unpacked_wheel_store import UnpackedWheelStore


if TYPE_CHECKING:
    from cleo.io.inputs.option import Option


class CacheGcCommand(Command):
    name = "cache gc"
    description = "Remove unreferenced entries from the unpacked wheel store."

    options: ClassVar[list[Option]] = [
        option(
            "dry-run",
            description="Show what would be removed without actually deleting anything.",
            flag=True,
        ),
    ]

    def handle(self) -> int:
        config = Config.create()
        cache_dir = config.artifacts_cache_directory
        store = UnpackedWheelStore(cache_dir)

        self.line(
            "<info>Checking unpacked wheel store for unreferenced entries...</info>"
        )

        if not store.cache_dir.exists():
            self.line("No unpacked wheel store found.")
            return 0

        tag = "comment" if self.option("dry-run") else "info"
        pruned = list(
            store.prune_unreferenced(dry_run=self.option("dry-run"))
        )

        if pruned:
            for entry in pruned:
                self.line(f"  <{tag}>Removed: {entry.name}</{tag}>")
        else:
            self.line("No unreferenced entries found.")

        return 0
