# Windows test compatibility

Windows may return `WinError 1314` when a non-elevated process attempts to create symbolic links.
The three symlink-specific tests skip **only** for this OS error on Windows. All other errors still fail.
Secret exclusion is tested separately and never skipped.

Run:

```cmd
python -m pip install -e .
gaiaforge --help
python -m unittest discover -s tests -v
```

On Windows without symlink privilege, expect **29 tests, OK (skipped=3)**.
In environments permitting symlinks, all 29 assertions run.
Skipping a test is not equivalent to verifying the behavior: use Linux CI or Windows Developer Mode to exercise actual symlinks.

The CLI `stage` command generates a review workspace, not a secure execution sandbox.
