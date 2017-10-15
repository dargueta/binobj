import setuptools


setuptools.setup(
    name='binobj',
    version='0.1.0',
    description='A Python library for reading and writing structured binary data.',
    long_description='file: README.rst',
    author='Diego Argueta',
    author_email='dargueta@users.noreply.github.com',
    url='https://www.github.com/dargueta/binobj',
    license='BSD',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
    ],
    install_requires=[
        'bitstring>=3.1',
        'enum34>=1.1;python_version<"3.4"',
    ],
    python_requires='>=3.3',
    tests_require=[
        'bumpversion>=0.5.0',
        'tox>=2.0',
        'tox-pyenv>=1.0',
    ],
    packages=setuptools.find_packages(
        exclude=['tests', '*.tests', '*.tests.*', 'docs']),
)

