SOURCEDIR=binobj
SOURCEFILES=$(SOURCEDIR)/*.py setup.py
TESTDIR=tests
TESTFILES=$(TESTDIR)/*.py tox.ini test_requirements.txt
DOCSDIR=docs
DOCSSOURCE=$(DOCSDIR)/source
DOCSTARGET=$(DOCSDIR)/build
TOXDIRS=.tox
ENVFILE=.python-version

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

$(ENVFILE):
	pyenv update || brew upgrade pyenv || true
	$(foreach version,$(PYTHON_VERSIONS),pyenv install -s $(version);)
	pyenv local $(PYTHON_VERSIONS)
	pip3 install -U pip setuptools

.PHONY: setup
setup: $(ENVFILE) dev_requirements.txt
	pip3 install -U -r dev_requirements.txt

$(TOXDIRS): test_requirements.txt tox.ini
	detox -r --notest

test: $(TOXDIRS)
	detox

lint: $(SOURCEFILES)
	pylint --disable=fixme $(SOURCEDIR)

docs: $(SOURCEFILES) $(DOCSSOURCE)
	sphinx-apidoc --ext-autodoc --ext-intersphinx -M -f -o $(DOCSSOURCE) -e $(SOURCEDIR)
	sphinx-build $(DOCSSOURCE) $(DOCSTARGET)

# TODO (dargueta): Make `clean` work on Windows. Windows doesn't have `rm`.
.PHONY: clean
clean:
	git clean -fd $(DOCSSOURCE)
	rm -rf .tox .cache *.egg-info

