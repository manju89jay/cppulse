# Licensing and local diagnostic bundles

cppulse's first-party local core is MIT-licensed, including use on public,
private and commercial projects. Core analysis requires no cppulse account or
subscription. Install the required dependencies and analysis packs before using
the offline runtime. An analyzed project's license and ownership do not change
when cppulse reads it.

Third-party dependencies retain their own copyrights and licenses. The Python
distribution includes cppulse's `LICENSE`; its bundled dashboard also includes
`cppulse/data/dashboard/assets/third-party-notices.txt` with complete retained
license texts for the locked production dependency closure. That inventory is
conservative and may include packages omitted by optimization. External Python,
native and optional dependencies are installed separately and keep their own
license files. The dashboard notice does not relicense those dependencies or an
analyzed project.

Read the installed dashboard notices without contacting a service:

```python
from importlib.resources import files

print(files("cppulse").joinpath(
    "data/dashboard/assets/third-party-notices.txt"
).read_text(encoding="utf-8"))
```

## Create a local bundle

```sh
cppulse diagnostics --output cppulse-diagnostics.zip
```

The implemented command is `diagnostics`; the specification's “bug-report
bundle” describes this workflow. There is no `bugreport` command alias or
automatic upload. The command creates a new local ZIP and refuses to overwrite
an existing file. Sharing that file is a separate explicit action.

The default ZIP contains one `diagnostics.json` with cppulse/Python/platform
information, optional capability status, safe native availability/startup status,
and its creation time. It excludes source excerpts, configuration contents,
credentials, tokens, environment dumps, arguments, local paths and raw logs or
native error messages. Optional distribution version strings are omitted because
valid local version tags can contain private identifiers or tokens. The export
uses explicit fields, so future diagnostic information is not automatically
added to the bundle.

`cppulse doctor` is an interactive inspection command and can show local paths
and detailed version metadata. Its raw output has a different disclosure scope
from the default bundle. Inspect any additional material before choosing to
share it. This command provides no opt-in source/environment/log collection;
adding richer collection requires a separate explicit design and choice.

The source-bound qualification uses authored secret sentinels, actual failing
native probes, actual optional-distribution metadata and kernel-denied networking.
Those tests qualify bundle contents and local operation; they do not authenticate
a producer, qualify a complete release/platform matrix, or assert that a
particular project satisfies every third-party license obligation.
