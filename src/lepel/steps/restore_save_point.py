from typing import Any

from lepel import PipelineStep


class RegisterCliArgsToConfig(PipelineStep):
    """Registers CLI arguments as configuration values.

    Supports forms: `--a 1 --b.c 2 --d=3 --flag (becomes True)`.
    """

    def run(self, file: Any) -> None:
        pass
