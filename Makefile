SOURCEDIR=binobj
SOURCEFILES=$(SOURCEDIR)/*.py setup.py
TESTDIR=tests
TESTFILES=$(TESTDIR)/*.py tox.ini test_requirements.txt
DOCSDIR=docs
DOCSSOURCE=$(DOCSDIR)/source
DOCSTARGET=$(DOCSDIR)/build
TOXDIRS=.tox

# TODO (dargueta): OSX must install PyPy from source so this will break.
.PHONY: dev_setup
dev_setup:
	pyenv install -s 3.6.3
	pyenv install -s 3.5.4
	pyenv install -s 3.4.7
	pyenv install -s 3.3.6
	pyenv install -s pypy3.5-5.9.0
	pyenv local 3.6.3 3.5.4 3.4.7 3.3.6 pypy3.5-5.9.0
	pip3 install -U -r dev_requirements.txt

$(TOXDIRS): test_requirements.txt tox.ini
	tox -r --notest

test: $(TOXDIRS)
	tox

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

