#!/usr/bin/env python3
"""
Development environment setup script for Excloud SDK.
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, check=True, capture_output=False):
    """Run a command and handle errors gracefully."""
    try:
        result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {' '.join(cmd)}")
        if capture_output and e.stderr:
            print(f"Error: {e.stderr.strip()}")
        elif not capture_output:
            print(f"Return code: {e.returncode}")
        return None
    except FileNotFoundError:
        print(f"❌ Command not found: {cmd[0]}")
        return None


def check_uv_available():
    """Check if uv is available on the system."""
    result = run_command(['which', 'uv'], check=False, capture_output=True)
    return result is not None and result.returncode == 0


def create_venv():
    """Create virtual environment using uv or standard venv."""
    venv_path = Path('.venv')
    
    if venv_path.exists():
        print("📁 Virtual environment already exists")
        return True
    
    print("🔧 Creating virtual environment...")
    
    # Try uv first
    if check_uv_available():
        print("📦 Using uv for faster setup")
        result = run_command(['uv', 'venv', '.venv'])
        if result:
            return True
        print("⚠️ uv failed, falling back to standard venv")
    
    # Fallback to standard venv
    print("📦 Using standard Python venv")
    result = run_command([sys.executable, '-m', 'venv', '.venv'])
    return result is not None


def install_dependencies():
    """Install the package and its dependencies."""
    venv_path = Path('.venv')
    
    # Use python -m pip instead of direct pip command for better compatibility
    if os.name == 'nt':  # Windows
        python_cmd = str(venv_path / 'Scripts' / 'python')
    else:  # Unix-like
        python_cmd = str(venv_path / 'bin' / 'python')
    
    # Use python -m pip instead of pip directly
    pip_cmd = [python_cmd, '-m', 'pip']
    
    # Check if pip is available in the venv
    print("🔍 Checking pip availability...")
    pip_check = run_command(pip_cmd + ['--version'], check=False, capture_output=True)
    if not pip_check or pip_check.returncode != 0:
        print("📦 Installing pip in virtual environment...")
        # Try to install pip using ensurepip
        ensurepip_result = run_command([python_cmd, '-m', 'ensurepip', '--upgrade'], check=False)
        if not ensurepip_result:
            print("❌ Failed to install pip in virtual environment")
            return False
    
    print("📦 Installing package in development mode...")
    result = run_command(pip_cmd + ['install', '-e', '.'])
    if not result:
        return False
    
    print("📦 Installing dependencies...")
    dependencies = ['websockets', 'requests']
    for dep in dependencies:
        print(f"  Installing {dep}...")
        result = run_command(pip_cmd + ['install', dep])
        if not result:
            return False
    
    return True


def show_completion_message():
    """Show completion message with next steps."""
    venv_path = Path('.venv')
    
    if os.name == 'nt':  # Windows
        activate_cmd = f".venv\\Scripts\\activate"
        python_cmd = ".venv\\Scripts\\python"
    else:  # Unix-like
        activate_cmd = "source .venv/bin/activate"
        python_cmd = ".venv/bin/python"
    
    print("\n✅ Setup complete!")
    print(f"💡 Activate with: {activate_cmd}")
    print("🚀 Run example: make example")
    print("🔧 Or manually:")
    print(f"   export EXCLOUD_API_KEY=your_api_key")
    print(f"   {python_cmd} example.py")


def main():
    """Main setup function."""
    print("🔧 Setting up Excloud SDK development environment...")
    
    # Create virtual environment
    if not create_venv():
        print("❌ Failed to create virtual environment")
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        print("❌ Failed to install dependencies")
        sys.exit(1)
    
    # Show completion message
    show_completion_message()


if __name__ == "__main__":
    main()
