
from setuptools import find_packages, setup

setup(
    name="ate",
    version="0.1.0",
    description="",
    author="",
    author_email="",
    license="GPL2",
    keywords="",
    packages=find_packages(),
    # package_data={LIBNAME: get_package_data(LIBNAME, EXTLIST)},
    entry_points={
        "spyder.plugins": [
            "ate = ate.spyder.plugin:ATE",
        ]
    }
)