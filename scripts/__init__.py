"""Claude 4-Layer Memory System — core scripts package.

This file MUST exist and be non-empty.

- ``tests/test_architecture.py::test_init_files_exist`` requires the
  package marker to be present.
- ``tests/test_architecture.py::test_modules_are_importable_independently``
  loads sibling modules via ``import scripts.<module>``; without this
  ``__init__.py`` those imports would fail.
- The release workflow (``.github/workflows/release.yml``) historically
  deleted ``__init__.py`` files matching ``-size 0``; a non-empty
  docstring is a belt-and-braces guard against that class of regression.
"""
