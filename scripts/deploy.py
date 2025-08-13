#!/usr/bin/env python3
"""
Deployment script for Excloud Python package.

This script automates the process of building and deploying the excloud package to PyPI.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_command(command, description, cwd=None):
    """Run a shell command and handle errors."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            cwd=cwd
        )
        if result.stdout:
            print(f"   ✓ {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error: {e}")
        if e.stdout:
            print(f"   Output: {e.stdout}")
        if e.stderr:
            print(f"   Error: {e.stderr}")
        return False


def clean_build():
    """Clean previous build artifacts."""
    commands = [
        ("rm -rf dist/", "Removing dist directory"),
        ("rm -rf build/", "Removing build directory"),
        ("rm -rf *.egg-info/", "Removing egg-info directories"),
        ("find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true", "Removing __pycache__ directories"),
        ("find . -name '*.pyc' -delete 2>/dev/null || true", "Removing .pyc files"),
    ]

    print("🧹 Cleaning build artifacts...")
    for command, description in commands:
        run_command(command, description)


def install_dependencies():
    """Install build dependencies."""
    dependencies = ["build", "twine"]
    for dep in dependencies:
        if not run_command(f"python -m pip install {dep}", f"Installing {dep}"):
            return False
    return True


def build_package():
    """Build the package."""
    return run_command("python -m build", "Building package")


def check_package():
    """Check the built package."""
    return run_command("python -m twine check dist/*", "Checking package")


def test_import():
    """Test that the package can be imported correctly."""
    print("🧪 Testing package import...")
    try:
        # Test basic import
        result = subprocess.run([
            sys.executable, "-c",
            "from excloud import Client; print('✓ Import successful!')"
        ], capture_output=True, text=True, check=True)
        print(f"   {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Import test failed: {e}")
        return False


def upload_to_testpypi():
    """Upload package to Test PyPI."""
    print("📦 Uploading to Test PyPI...")
    print("   Note: You'll need to enter your Test PyPI credentials")
    return run_command(
        "python -m twine upload --repository testpypi dist/*",
        "Uploading to Test PyPI"
    )


def upload_to_pypi():
    """Upload package to PyPI."""
    print("🚀 Uploading to PyPI...")
    print("   Note: You'll need to enter your PyPI credentials")
    return run_command(
        "python -m twine upload dist/*",
        "Uploading to PyPI"
    )


def get_package_info():
    """Get information about the current package."""
    try:
        # Read version from pyproject.toml
        pyproject_path = Path("pyproject.toml")
        if pyproject_path.exists():
            with open(pyproject_path, "r") as f:
                content = f.read()
                for line in content.split("\n"):
                    if line.startswith("version ="):
                        version = line.split("=")[1].strip().strip('"')
                        return version
        return "unknown"
    except Exception:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Deploy excloud package to PyPI")
    parser.add_argument(
        "--target",
        choices=["test", "prod", "both"],
        default="test",
        help="Deployment target (default: test)"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build artifacts before building"
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="Skip import tests"
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Only build the package, don't upload"
    )

    args = parser.parse_args()

    # Change to project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)

    print("🚀 Excloud Package Deployment Script")
    print("=" * 50)

    version = get_package_info()
    print(f"📋 Package: excloud v{version}")
    print(f"📁 Working directory: {os.getcwd()}")
    print()

    # Clean if requested
    if args.clean:
        clean_build()
        print()

    # Install dependencies
    print("📦 Installing dependencies...")
    if not install_dependencies():
        print("❌ Failed to install dependencies")
        sys.exit(1)
    print()

    # Build package
    if not build_package():
        print("❌ Build failed")
        sys.exit(1)
    print()

    # Check package
    if not check_package():
        print("❌ Package check failed")
        sys.exit(1)
    print()

    # Test import
    if not args.no_test:
        if not test_import():
            print("❌ Import test failed")
            sys.exit(1)
        print()

    if args.build_only:
        print("✅ Build completed successfully!")
        print("📁 Built packages are in the dist/ directory")
        return

    # Upload based on target
    success = True
    if args.target in ["test", "both"]:
        if not upload_to_testpypi():
            success = False
        print()

    if args.target in ["prod", "both"]:
        if args.target == "both":
            print("⚠️  Are you sure you want to upload to production PyPI?")
            confirm = input("Type 'yes' to continue: ")
            if confirm.lower() != "yes":
                print("❌ Production upload cancelled")
                return

        if not upload_to_pypi():
            success = False

    if success:
        print("✅ Deployment completed successfully!")
        if args.target == "test":
            print("🔗 Test installation: pip install -i https://test.pypi.org/simple/ excloud")
        elif args.target == "prod":
            print("🔗 Installation: pip install excloud")
        elif args.target == "both":
            print("🔗 Installation: pip install excloud")
    else:
        print("❌ Deployment failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
