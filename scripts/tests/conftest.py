"""The marker of the generated-file checks (EXEC-GEN-CHECK, ERRORS M434): `.github/workflows/generated-files.yml` runs
every test marked `generated_file` on each push and pull request."""


def pytest_configure(config):
    config.addinivalue_line('markers', 'generated_file: a generated file equals what its generator writes now '
                                       '(run by .github/workflows/generated-files.yml)')
