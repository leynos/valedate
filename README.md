# valedate

Reusable Vale testing harness and pytest assertions for rule authors. The
package bundles the `Valedate` sandbox first introduced in `concordat-vale` so
you can lint fixtures against isolated, temporary styles trees without touching
your global Vale configuration.

## Requirements

- Python 3.10+
- A `vale` binary available on `PATH` (no mocks or stubs are provided)

## Quick start

```python
from valedate import Valedate, assert_has_diagnostic

ini = {
    "__root__": {"MinAlertLevel": "suggestion"},
    "[*.md]": {"BasedOnStyles": "Test"},
}

styles = {
    "Test/NoFoo.yml": """
        extends: existence
        message: "Avoid 'foo'."
        level: warning
        tokens:
          - foo
    """,
}

with Valedate(ini, styles=styles) as env:
    diags = env.lint("foo is discouraged")
    assert_has_diagnostic(diags, check="Test.NoFoo")
```

Run the test suite with `make test` to validate that your rules behave as Vale
reports them.
