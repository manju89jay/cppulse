# cppulse Makefile — showcase refresh targets
#
# Usage:
#   make showcase            # full refresh: clone repos, analyze, regenerate
#   make showcase-quick      # regenerate from existing JSON (no re-analysis)
#   make showcase-project PROJECT=poco  # single project full refresh

PYTHON ?= python
SCRIPTS := scripts

.PHONY: showcase showcase-quick showcase-project

## Full showcase refresh: clone/update all 6 repos, run analysis, regenerate everything
showcase:
	$(PYTHON) $(SCRIPTS)/refresh_showcase.py

## Regenerate derived files from existing JSON (no re-analysis)
showcase-quick:
	$(PYTHON) $(SCRIPTS)/refresh_showcase.py --skip-analysis

## Single project refresh (set PROJECT=poco, etc.)
showcase-project:
ifndef PROJECT
	$(error PROJECT is not set. Usage: make showcase-project PROJECT=poco)
endif
	$(PYTHON) $(SCRIPTS)/refresh_showcase.py --project $(PROJECT)
