# Excloud PyPI Deployment Guide

This guide walks you through deploying the `excloud` Python package to PyPI so users can install it with `pip install excloud`.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Deployment](#quick-deployment)
- [Manual Deployment](#manual-deployment)
- [Post-Deployment](#post-deployment)
- [Version Management](#version-management)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### 1. PyPI Accounts

You'll need accounts on both Test PyPI and production PyPI:

- **Test PyPI**: https://test.pypi.org/account/register/
- **Production PyPI**: https://pypi.org/account/register/

### 2. API Tokens (Recommended)

Instead of using passwords, create API tokens for secure authentication:

#### For Test PyPI:
1. Go to https://test.pypi.org/manage/account/token/
2. Create a new token with scope "Entire account"
3. Save the token securely

#### For Production PyPI:
1. Go to https://pypi.org/manage/account/token/
2. Create a new token with scope "Entire account" 
3. Save the token securely

### 3. Configure Authentication

Create a `~/.pypirc` file with your credentials:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-your-production-api-token-here

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-your-test-api-token-here
```

## Quick Deployment

We've provided a deployment script that automates the entire process:

### Test PyPI Deployment

```bash
# Deploy to Test PyPI (recommended first)
python scripts/deploy.py --target test --clean

# Test the installation
pip install -i https://test.pypi.org/simple/ excloud
python -c "from excloud import Client; print('Success!')"
```

### Production PyPI Deployment

```bash
# Deploy to production PyPI
python scripts/deploy.py --target prod --clean
```

### Deploy to Both

```bash
# Deploy to both Test PyPI and production PyPI
python scripts/deploy.py --target both --clean
```

## Manual Deployment

If you prefer to do it manually or need more control:

### 1. Clean Previous Builds

```bash
rm -rf dist/ build/ *.egg-info/
find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find . -name '*.pyc' -delete 2>/dev/null || true
```

### 2. Install Build Tools

```bash
pip install build twine
```

### 3. Build the Package

```bash
python -m build
```

This creates two files in the `dist/` directory:
- `excloud-0.1.0-py3-none-any.whl` (wheel distribution)
- `excloud-0.1.0.tar.gz` (source distribution)

### 4. Check the Package

```bash
python -m twine check dist/*
```

### 5. Test Local Installation

```bash
pip install -e .
python -c "from excloud import Client; print('Import successful!')"
```

### 6. Upload to Test PyPI

```bash
python -m twine upload --repository testpypi dist/*
```

### 7. Test Installation from Test PyPI

```bash
# Create a new virtual environment for testing
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# Install from Test PyPI
pip install -i https://test.pypi.org/simple/ excloud

# Test the installation
python -c "from excloud import Client; print('Test PyPI installation successful!')"

# Clean up
deactivate
rm -rf test_env
```

### 8. Upload to Production PyPI

```bash
python -m twine upload dist/*
```

## Post-Deployment

### Verify Installation

After deploying to production PyPI, verify that users can install the package:

```bash
# Test in a fresh environment
python -m venv verify_env
source verify_env/bin/activate

# Install from PyPI
pip install excloud

# Test the expected usage
python -c "
from excloud import Client
client = Client(api_key='test_key')
print('✅ Package installed and working correctly!')
print(f'✅ Client class available: {Client}')
"

# Clean up
deactivate
rm -rf verify_env
```

### Update Documentation

1. Update the main README.md with installation instructions
2. Update any documentation that references installation
3. Consider creating a changelog entry

## Version Management

### Updating the Version

Before each release, update the version in `pyproject.toml`:

```toml
[project]
name = "excloud"
version = "0.1.1"  # Update this
```

### Version Naming Convention

Follow semantic versioning (semver):
- `0.1.0` - Initial release
- `0.1.1` - Patch release (bug fixes)
- `0.2.0` - Minor release (new features, backward compatible)
- `1.0.0` - Major release (breaking changes)

### Git Tags

Tag releases in git:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Troubleshooting

### Common Issues

#### 1. Authentication Errors

```
Error: HTTP Error 403: The user 'username' isn't allowed to upload to project 'excloud'
```

**Solution**: Make sure you're using the correct API token and have the right permissions.

#### 2. Package Already Exists

```
Error: File already exists
```

**Solution**: You cannot overwrite existing versions on PyPI. Increment the version number.

#### 3. Import Errors After Installation

```
ImportError: No module named 'excloud'
```

**Solutions**:
- Check that the package structure is correct
- Verify `__init__.py` exports are correct
- Ensure dependencies are properly specified

#### 4. Missing Dependencies

```
ModuleNotFoundError: No module named 'requests'
```

**Solution**: Check that dependencies are listed in `pyproject.toml`:

```toml
dependencies = ["requests>=2.25.0", "websockets>=11.0"]
```

### Debug Package Contents

To see what's included in your package:

```bash
# For wheel files
python -m zipfile -l dist/excloud-0.1.0-py3-none-any.whl

# For source distribution
tar -tzf dist/excloud-0.1.0.tar.gz
```

### Test with Different Python Versions

```bash
# Test with Python 3.8
python3.8 -m venv test_py38
source test_py38/bin/activate
pip install excloud
python -c "from excloud import Client; print('Python 3.8 OK')"
deactivate

# Test with Python 3.11
python3.11 -m venv test_py311
source test_py311/bin/activate
pip install excloud
python -c "from excloud import Client; print('Python 3.11 OK')"
deactivate
```

## Security Best Practices

1. **Never commit API tokens** to version control
2. **Use API tokens** instead of passwords
3. **Limit token scope** to what's necessary
4. **Rotate tokens** regularly
5. **Use Test PyPI first** before production

## Monitoring

After deployment, monitor:

- Download statistics on PyPI
- User feedback and issues
- Compatibility with new Python versions
- Security vulnerabilities in dependencies

## Resources

- [Python Packaging User Guide](https://packaging.python.org/)
- [PyPI Help](https://pypi.org/help/)
- [Test PyPI](https://test.pypi.org/)
- [Twine Documentation](https://twine.readthedocs.io/)
- [setuptools Documentation](https://setuptools.pypa.io/)

---

## Summary

Your package is now ready for deployment! The key steps are:

1. ✅ Package structure is correct (`excloud/` directory with `__init__.py`)
2. ✅ Configuration files are set up (`pyproject.toml`, `setup.py`)
3. ✅ Import works as expected: `from excloud import Client`
4. ✅ Build and deployment scripts are ready
5. ✅ Documentation is complete

Users will be able to install your package with:

```bash
pip install excloud
```

And use it with:

```python
from excloud import Client

client = Client(api_key="your_api_key")
# ... rest of your code
```
