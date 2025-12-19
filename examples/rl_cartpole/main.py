from lepel import PipelineRunner
from lepel.steps import BindConfigFromDisk, EnsureRequiredConfigValues, RegisterCliArgsToConfig


def main():
    pipeline = PipelineRunner()
    pipeline.run(RegisterCliArgsToConfig())
    pipeline.run(BindConfigFromDisk())
    pipeline.run(EnsureRequiredConfigValues())


if __name__ == '__main__':
    main()
