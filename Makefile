SOURCEDIR=binobj
SOURCEFILES=$(SOURCEDIR)/*.py
TESTDIR=tests
TESTFILES=$(TESTDIR)/*.py tox.ini test_requirements.txt
DOCSDIR=docs
DOCSSOURCE=$(DOCSDIR)/source
DOCSTARGET=$(DOCSDIR)/build

ifeq ($(OS),Windows_NT)
    OPERATING_SYSTEM=WINDOWS
else
    OPERATING_SYSTEM=$(shell uname -s)
endif

ifeq ($(OPERATING_SYSTEM),Darwin)
    # OSX doesn't provide a pre-built binary for PyPy3 so we have to build it
    # ourselves. Unfortunately, this can take over an hour even on a modern
    # system.
    PYPY3=pypy3.5-5.9.0-src
else
    PYPY3=pypy3.5-5.9.0
endif

PYTHON_VERSIONS=3.6.3 3.5.4 3.4.7 3.3.7 $(PYPY3)

# The presence of .python-version indicates whether we have a virtualenv set up
# or not.
.python-version:
	pyenv update || brew upgrade pyenv || true
	$(foreach version,$(PYTHON_VERSIONS),pyenv install -s $(version);)
	pyenv local $(PYTHON_VERSIONS)

.tox: .python-version setup.cfg dev_requirements.txt test_requirements.txt tox.ini
	detox -r --notest

# Coverage file gets changed on every test run so we can use it to see when the
# last time tests were run. Don't rerun the tests if the source code, test code,
# or environment hasn't changed.
.coverage: .tox $(SOURCEFILES) $(TESTFILES)
	detox

$(DOCSTARGET): $(SOURCEFILES) $(DOCSSOURCE)
	sphinx-apidoc --ext-autodoc --ext-intersphinx -M -f -o $(DOCSSOURCE) -e $(SOURCEDIR)
	sphinx-build $(DOCSSOURCE) $(DOCSTARGET)

.PHONY: setup
setup: .python-version dev_requirements.txt
	pip3 install -U -r dev_requirements.txt

.PHONY: lint
lint: $(SOURCEFILES)
	pylint --disable=fixme $(SOURCEDIR) $(TESTDIR)

# TODO (dargueta): Make `clean` work on Windows. Windows doesn't have `rm`.
.PHONY: clean
clean:
	git clean -fd $(DOCSSOURCE)
	rm -rf .tox .cache *.egg-info *.eggs .coverage $(DOCSTARGET)
	find . -name '__pycache__' -type d -exec rm -rf '{}' \+

# Run the unit tests if the source code has changed.
.PHONY: test
test: .coverage

# Build the Sphinx documentation for the library.
.PHONY: docs
docs: $(DOCSTARGET)

