# Releasing

Agents do not publish. The maintainer does these steps by hand. The workflow is
`.github/workflows/release.yml`. It uses trusted publishing (OIDC), so no API
token is stored anywhere.

## One-time setup

1. Create an account on [PyPI](https://pypi.org) and on
   [TestPyPI](https://test.pypi.org). They are separate sites.
2. On each site, add a **pending publisher** (Account settings, Publishing) for the
   project `textual-console`:

   | Field             | PyPI          | TestPyPI      |
   | ----------------- | ------------- | ------------- |
   | Owner             | `thespicybyte` | `thespicybyte` |
   | Repository        | `textual-console` | `textual-console` |
   | Workflow filename | `release.yml` | `release.yml` |
   | Environment       | `pypi`        | `testpypi`    |

3. On GitHub (Settings, Environments), create the environments `pypi` and
   `testpypi`. Optionally add a required reviewer to `pypi`.

## Release steps

1. Make sure `version` in `pyproject.toml` and `CHANGELOG.md` are right, and CI is green on `main`.
2. Publish to TestPyPI: Actions, Release, **Run workflow** on `main`.
3. Check the TestPyPI upload in a clean venv:

   ```bash
   python -m venv /tmp/tc-check && . /tmp/tc-check/bin/activate
   pip install --index-url https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ textual-console
   python -m textual_console
   ```

   TestPyPI cannot replace a file. If you must fix something, raise the version.
4. Tag and push. The tag must be `v` plus the version, for example `v0.1.0`:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The workflow fails before it builds if the tag and `pyproject.toml` do not match.
5. Check the new release on <https://pypi.org/project/textual-console/>, then
   repeat the clean-venv check with `pip install textual-console`.
