# Actual accepted shared commands

These command vectors and working directories were read from the accepted check-results.json. All fifteen returned zero. Long formatting file lists remain exact in that JSON.

## generated-check

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse`.

```bash
/workspace/scratch/b3d4e6fff494/cppulse/.venv/bin/python scripts/check_generated.py
```

## root-tests

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse`.

```bash
/workspace/scratch/b3d4e6fff494/cppulse/.venv/bin/python -m pytest -v tests/
```

## analyzer-configure

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse`.

```bash
cmake -S analyzer-core -B analyzer-core/build -DBUILD_TESTING=ON
```

## analyzer-build

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse`.

```bash
cmake --build analyzer-core/build -j 4
```

## analyzer-tests

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse`.

```bash
ctest --test-dir analyzer-core/build --output-on-failure --no-tests=error
```

## git-miner-tests

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse/git-miner`.

```bash
/workspace/scratch/b3d4e6fff494/cppulse/.venv/bin/python -m pytest -v --cov=src --cov=cppulse.git_miner --cov-report=term --cov-report=json:/workspace/scratch/b3d4e6fff494/cppulse/review/autonomous/logs/s7-final-shared/git-miner-coverage.json tests/
```

## predictor-tests

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse/predictor`.

```bash
/workspace/scratch/b3d4e6fff494/cppulse/.venv/bin/python -m pytest -v --cov=src --cov=cppulse.predictor --cov-report=term --cov-report=json:/workspace/scratch/b3d4e6fff494/cppulse/review/autonomous/logs/s7-final-shared/predictor-coverage.json tests/
```

## report-engine-tests

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse/report-engine`.

```bash
/workspace/scratch/b3d4e6fff494/cppulse/.venv/bin/python -m pytest -v --cov=src --cov=cppulse.report_engine --cov-report=term --cov-report=json:/workspace/scratch/b3d4e6fff494/cppulse/review/autonomous/logs/s7-final-shared/report-engine-coverage.json tests/
```

## dashboard-tests

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse/dashboard`.

```bash
npm test
```

## dashboard-build

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse/dashboard`.

```bash
npm run build
```

## cli-configure

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse`.

```bash
cmake -S cli -B cli/build -DBUILD_TESTING=ON
```

## cli-build

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse`.

```bash
cmake --build cli/build -j 4
```

## cli-tests

Working directory: `/workspace/scratch/b3d4e6fff494/cppulse`.

```bash
ctest --test-dir cli/build --output-on-failure --no-tests=error
```
