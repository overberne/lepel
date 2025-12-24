from lepel.config_ import ensure_required_config_values
from lepel import PipelineStep


class EnsureRequiredConfigValues(PipelineStep):
    def run(self) -> None:
        ensure_required_config_values()
