from setuptools import setup

setup(
    name="muninn-iers",
    version="1.0",
    description="Muninn extension for IERS files",
    url="https://github.com/stcorp/muninn-iers",
    author="S[&]T",
    license="BSD",
    py_modules=["muninn_iers"],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering",
        "Environment :: Plugins",
    ],
    install_requires=["muninn"],
)
