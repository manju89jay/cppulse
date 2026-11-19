# Local candidate preparation

A candidate is a reviewable set of local artifacts. Preparing it does not publish,
install, deploy, sign, certify or establish production readiness. Keep source
changes uncommitted while reviewing this prototype.

First prepare a native analyzer archive with `scripts/package_native.py`. Its
manifest identifies the tested target, analyzer hash, bundled libraries and
Clang resources, required host libraries/headers and remaining limitations.
Retain its build/relocation logs with the review. Then run the candidate builder
using the Python interpreter whose platform-specific dependency closure you want:

```bash
python scripts/package_candidate.py \
  --native-archive PATH/TO/cppulse-native-ARCHIVE.tar.gz \
  --wheelhouse review/autonomous/wheelhouse \
  --output-dir review/candidates
```

The builder reads the version from `pyproject.toml` (`0.2.0.dev2` currently).
`--version 0.2.0.dev2` additionally checks the expected value. It builds a pure
Python wheel with `python -m build --wheel --no-isolation`; the declared build
backend and development tools must already be installed. It then resolves the
core dependency closure from the supplied local wheelhouse using pip
`--isolated download --no-index --only-binary=:all:`. It performs no package
installation and rejects direct/URL requirements before resolution. Supply all
transitive wheels for the current Python/platform. Optional ML, PDF, web and
development packages are excluded from the core lock and SBOM.

The prepared directory contains:

| File or directory | Review evidence |
| --- | --- |
| `candidate.json` | Actual version/platform, source HEAD, tracked diff hash, untracked source hashes, exact commands and explicitly scoped verification |
| `core-wheelhouse/` | Built cppulse wheel and resolved core dependency wheels |
| `core-requirements.lock` | Exact core versions and SHA-256 hashes for this Python/platform |
| `core-dependencies.json`, `core-sbom.cdx.json` | Resolved distribution metadata and dependency graph, including declared license text |
| `native/` | Unchanged native archive and its embedded target/host declarations |
| `notices/core/`, `LICENSE` | Wheel-provided license/notice files and project license; native notices remain inside its archive |
| `files.json`, `SHA256SUMS` | File sizes/hashes and a checksum inventory |
| `logs/` | Actual wheel-build and offline dependency-resolution output |
| `SUPPORT.md`, `INSTALL_UPGRADE_ROLLBACK.md` | Platform scope and side-by-side installation/recovery instructions |

The source identity covers HEAD, the binary tracked diff and untracked source
bytes. Generated review/output directories are excluded. Source changes during
preparation fail the candidate rather than attaching an inaccurate source hash.
Native source binding is reviewed separately against its build evidence; a hash
records bytes and does not authenticate authorship. Existing candidate directories
are never overwritten. The output directory cannot be the checkout root or its
ancestor, because that would exclude source files from the source identity. A failed preparation retains its temporary directory and
logs for diagnosis and does not mark that directory prepared.

Verify checksums before use. In a new virtual environment, install the exact core
closure from inside the candidate directory:

```bash
python -m pip install --no-index --find-links core-wheelhouse \
  --require-hashes -r core-requirements.lock
```

Extract the native archive to a versioned prefix, satisfy its declared host
requirements and set `CPPULSE_NATIVE_PREFIX`. Run `cppulse doctor` and a real
analysis/report smoke outside the source checkout. The candidate builder explicitly
records installed-smoke and Compose checks as not run by the builder; keep the
separate installed verification evidence. Core-only installation uses the
experimental heuristic ranking when optional ML dependencies are absent. PDF and
API serving require their corresponding extras.

Upgrade alongside the old environment/prefix and verify before selecting the new
one. Roll back by selecting the retained previous environment/prefix and outputs.
Do not overwrite old run data or assume cross-version contracts migrate
implicitly. The package has no remote publication or automatic self-update step.

The cloud verification environment is Python 3.12.14 on Linux x86_64, glibc
2.41, GCC 14.2 and libclang 19. Python 3.11 is in the declared package range but
has not been qualified on this host. The installed smoke must still establish
behavior for the actual candidate bytes. Declared Python compatibility is not
evidence that every Python minor, operating system, libclang/compiler
combination or optional extra was exercised. Docker, Windows,
macOS and unsupported analyzer build variants require their own observed checks.
