SOURCEDIR=binobj
SOURCEFILES=$(SOURCEDIR)/*.py
TESTDIR=tests
TESTFILES=$(TESTDIR)/*.py tox.ini setup.py
DOCSDIR=docs
DOCSSOURCE=$(DOCSDIR)/source
DOCSTARGET=$(DOCSDIR)/build

PYTHON_VERSIONS=3.6.5 3.5.5 3.4.8 3.7.0b4 pypy3.5-6.0.0

# The presence of .python-version indicates whether we have a virtualenv set up
# or not.
.python-version:
	pyenv update || brew upgrade pyenv || true
	$(foreach version,$(PYTHON_VERSIONS),pyenv install -s $(version);)
	pyenv local $(PYTHON_VERSIONS)

.tox: .python-version setup.py tox.ini
	detox -r --notest

# Coverage file gets changed on every test run so we can use it to see when the
# last time tests were run. Don't rerun the tests if the source code, test code,
# or environment hasn't changed.
.coverage: .tox $(SOURCEFILES) $(TESTFILES)
	detox

$(DOCSTARGET): $(SOURCEFILES) $(DOCSSOURCE)
	PYTHONPATH=. sphinx-apidoc --ext-autodoc --ext-intersphinx -M -f -o $(DOCSSOURCE) -e $(SOURCEDIR)
	PYTHONPATH=. sphinx-build $(DOCSSOURCE) $(DOCSTARGET)

.PHONY: setup
setup: .python-version setup.py
	pip3 install -Ue .[dev]

.PHONY: lint
lint: $(SOURCEFILES)
	pylint --disable=fixme,too-many-ancestors $(SOURCEDIR) || true
	pylint --disable=missing-docstring,blacklisted-name,too-few-public-methods,invalid-name,redefined-outer-name,too-many-ancestors,no-self-use $(TESTDIR) || true

# TODO (dargueta): Make `clean` work on Windows. Windows doesn't have `rm`.
.PHONY: clean
clean:
	git clean -fd $(DOCSSOURCE)
	rm -rf .tox .cache .pytest_cache *.egg-info *.eggs .coverage $(DOCSTARGET) dist build
	find . -name '__pycache__' -type d -exec rm -rf '{}' \+

# Run the unit tests if the source code has changed.
.PHONY: test
test: .coverage

# Build the Sphinx documentation for the library.
.PHONY: docs
docs: $(DOCSTARGET)
