SOURCEDIR=binobj
SOURCEFILES=$(SOURCEDIR)/*.py $(SOURCEDIR)/fields/*.py
TESTDIR=tests
TESTFILES=$(TESTDIR)/*.py tox.ini setup.py
DOCSDIR=docs
DOCSSOURCE=$(DOCSDIR)/source
DOCSTARGET=$(DOCSDIR)/build

PYTHON_VERSIONS=3.7.2 3.6.8 3.5.6 3.8.0 pypy3.5-7.1.0 pypy3.6-7.1.0

# The presence of .python-version indicates whether we have a virtualenv set up
# or not.
.python-version:
	pyenv update || brew upgrade pyenv || true
	$(foreach version,$(PYTHON_VERSIONS),pyenv install -s $(version);)
	pyenv local $(PYTHON_VERSIONS)

.tox: .python-version setup.py tox.ini
	tox -r --notest

# Coverage file gets changed on every test run so we can use it to see when the
# last time tests were run. Don't rerun the tests if the source code, test code,
# or environment hasn't changed.
.coverage: .tox $(SOURCEFILES) $(TESTFILES)
	tox

$(DOCSTARGET): $(SOURCEFILES) $(DOCSSOURCE)
	PYTHONPATH=. sphinx-apidoc --ext-autodoc --ext-intersphinx -M -f -o $(DOCSSOURCE) -e $(SOURCEDIR)
	PYTHONPATH=. sphinx-build $(DOCSSOURCE) $(DOCSTARGET)

.PHONY: setup
setup: .python-version setup.cfg
	pip3 install -U pip setuptools
	pip3 install -Ue .[dev]

.PHONY: lint
lint: $(SOURCEFILES)
	tox -e lint

# TODO (dargueta): Make `clean` work on Windows. Windows doesn't have `rm`.
.PHONY: clean
clean:
	git clean -fd $(DOCSDIR)
	rm -rf .tox .cache .pytest_cache *.egg-info *.eggs .coverage dist build .mypy_cache
	find . -name '__pycache__' -type d -exec rm -rf '{}' \+

# Run the unit tests if the source code has changed.
.PHONY: test
test: .coverage

# Build the Sphinx documentation for the library.
.PHONY: docs
docs: $(DOCSTARGET)


.PHONY: deploy
deploy: clean
	python3 setup.py sdist bdist_wheel
	twine upload dist/*
