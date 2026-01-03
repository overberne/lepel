from lepel import DependencyManager, PipelineStep, run_pipeline, run_step
from lepel.cli import cli_args_to_config, default_argparser


class FooStep(PipelineStep[str]):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def run(self, foo: int) -> str:
        return str(foo)


def pipeline(dependencies: DependencyManager) -> None:
    dependencies.update_context_variables(foo=42)
    foo = run_step(FooStep('Foo'))
    print(foo)


if __name__ == '__main__':
    argparser = default_argparser()
    namespace, rest_args = argparser.parse_known_args()

    run_pipeline(
        pipeline,
        output_dir=namespace.output_dir,
        config_file=namespace.config,
        checkpoint=namespace.checkpoint,
        **cli_args_to_config(rest_args),
    )
