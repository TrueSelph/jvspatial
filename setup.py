from setuptools import setup, find_packages

setup(
    name='jvspatial',
    version='0.0.1',
    description='An asynchronous object-spatial Python library for persistence and business logic application layers.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='TrueSelph Inc.',
    author_email='adminh@trueselph.com',
    url='https://github.com/trueselph/jvspatial',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'pydantic>=2.0',
        'fastapi',
        'uvicorn',
        'python-multipart',
        'motor',
        'pymongo'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
    python_requires='>=3.8',
)