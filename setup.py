"""A setuptools based setup module.

See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""
import os
import sys

from setuptools import setup, find_packages

# pylint: disable=redefined-builtin

here = os.path.abspath(os.path.dirname(__file__))  # pylint: disable=invalid-name

with open(os.path.join(here, "README.rst"), encoding="utf-8") as fid:
    long_description = fid.read()  # pylint: disable=invalid-name

with open(os.path.join(here, "requirements.txt"), encoding="utf-8") as fid:
    install_requires = [line for line in fid.read().splitlines() if line.strip()]

setup(
    name="rasaeco",
    version="0.0.15",
    description="Analyze software requirements in AECO industry",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/mristin/rasaeco",
    author="Marko Ristin",
    author_email="marko@ristin.ch",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
    ],
    license="License :: OSI Approved :: MIT License",
    keywords="BIM architecture civil engineering construction software requirements",
    packages=find_packages(exclude=["tests"]),
    install_requires=install_requires,
    extras_require={
        "dev": [
            "black==20.8b1",
            "mypy==0.790",
            "pydocstyle>=2.1.1,<3",
            "coverage>=4.5.1,<5",
            "docutils>=0.14,<1",
            "pyinstaller>=4,<5",
        ],
    },
    py_modules=["rasaeco"],
    package_data={"rasaeco": ["py.typed"]},
    data_files=[(".", ["LICENSE", "README.rst", "requirements.txt"])],
    entry_points={
        "console_scripts": ["pyrasaeco-render = rasaeco.pyrasaeco_render:entry_point"]
    },
)
