SOURCEDIR = binobj
SOURCEFILES = $(wildcard $(SOURCEDIR)/*.py) $(wildcard $(SOURCEDIR)/fields/*.py)
TESTDIR = tests
TESTFILES = $(wildcard $(TESTDIR)/*.py) $(wildcard $(TESTDIR)/fields/*.py)
DOCSDIR = docs
DOCSSOURCE = $(DOCSDIR)/source
DOCSTARGET = $(DOCSDIR)/build
TOX_ENV = $(shell python3 -c "import sys;print('py%d%d' % sys.version_info[:2])")
PIP := python3 -m pip


poetry.lock: pyproject.toml
	poetry lock --no-update
	touch $@

# Coverage file gets changed on every test run so we can use it to see when the
# last time tests were run. Don't rerun the tests if the source code, test code,
# or environment hasn't changed.
.coverage: poetry.lock tox.ini $(SOURCEFILES) $(TESTFILES)
	tox -e $(TOX_ENV)

$(DOCSTARGET): $(SOURCEFILES) $(DOCSSOURCE)
	PYTHONPATH=. sphinx-apidoc --ext-autodoc --ext-intersphinx -M -f -o $(DOCSSOURCE) -e $(SOURCEDIR)
	PYTHONPATH=. sphinx-build $(DOCSSOURCE) $(DOCSTARGET)

.PHONY: setup
setup:
	$(PIP) install -U pip setuptools wheel
	$(PIP) install -U -rdev-requirements.txt

.PHONY: lint
lint: $(SOURCEFILES)
	tox -e lint

.PHONY: clean
clean:
	-$(MAKE) -C $(DOCSDIR) clean
	$(RM) $(DOCSSOURCE)/binobj.*.rst  $(DOCSSOURCE)/binobj.rst  $(DOCSSOURCE)/modules.rst
	$(RM) -r .tox .cache .pytest_cache *.egg-info *.eggs .coverage dist build .mypy_cache
	find . -name '__pycache__' -type d -exec $(RM) -r '{}' \+

# Run the unit tests if the source code has changed.
.PHONY: test
test: .coverage

# Build the Sphinx documentation for the library.
.PHONY: docs
docs: $(DOCSTARGET)


.PHONY: deploy
deploy: clean
	poetry check
	poetry build
	poetry publish
