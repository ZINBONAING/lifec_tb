import os
import subprocess
import zipfile
import sys
from datetime import datetime
import re

RELEASE_DIR = "release"
GITIGNORE_FILE = ".gitignore"

def get_git_branch():
    """Get the current Git branch name."""
    try:
        return subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip().decode('utf-8')
    except subprocess.CalledProcessError:
        return "unknown-branch"

def get_latest_git_tag():
    """Get the latest Git tag and extract the numeric version."""
    try:
        tag_version = subprocess.check_output(['git', 'describe', '--tags', '--abbrev=0'], stderr=subprocess.DEVNULL).strip().decode('utf-8')
        
        # Extract version part (e.g., v1.2.3 from "main-v1.2.3")
        match = re.search(r'v(\d+\.\d+\.\d+)', tag_version)
        return match.group(0) if match else "v1.0.0"  # Default if no valid version exists
    except subprocess.CalledProcessError:
        return "v1.0.0"  # Default if no tag exists

def increment_version(version, major_override=None):
    """Increment the version number. 
    If major_override is given, reset minor & patch to 0.
    """
    version = version.lstrip("v")  # Remove 'v' prefix
    parts = version.split(".")
    
    if len(parts) == 3:
        major, minor, patch = map(int, parts)
        if major_override is not None:
            major = major_override
            minor = 0
            patch = 0
        else:
            patch += 1  # Increment patch version
        return f"v{major}.{minor}.{patch}"
    
    return "v1.0.0"  # Fallback


def get_git_tracked_files():
    """Get the list of Git-tracked files, excluding files ignored by .gitignore."""
    try:
        # Get all tracked files
        tracked_files = subprocess.check_output(['git', 'ls-files']).decode('utf-8').splitlines()
        
        # Get ignored files from .gitignore
        ignored_files = set(subprocess.check_output(['git', 'ls-files', '--others', '--ignored', '--exclude-standard']).decode('utf-8').splitlines())

        # Filter out ignored files from tracked list
        filtered_files = [file for file in tracked_files if file not in ignored_files]
        return filtered_files
    except subprocess.CalledProcessError:
        return []

def parse_gitignore():
    """Parse the .gitignore file and return a list of patterns to exclude."""
    ignore_patterns = []
    if os.path.exists(GITIGNORE_FILE):
        with open(GITIGNORE_FILE, "r") as f:
            for line in f:
                # Exclude comments and blank lines
                line = line.strip()
                if line and not line.startswith("#"):
                    ignore_patterns.append(line)
    return ignore_patterns

def should_exclude(file_path, ignore_patterns):
    """Check if a file matches any .gitignore patterns."""
    for pattern in ignore_patterns:
        # Support wildcards and directory matching
        if re.match(pattern.replace("*", ".*").replace("?", "."), file_path):
            return True
    return False

def create_release_zip(branch, version, files, ignore_patterns):
    """Create a zip file containing all tracked files, while excluding .gitignore files."""
    os.makedirs(RELEASE_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y_%m_%d")
    zip_filename = os.path.join(RELEASE_DIR, f"{branch}-{version}-{date_str}.zip")
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            if not should_exclude(file, ignore_patterns):
                zipf.write(file, arcname=file)
                print(f"Added: {file}")
            else:
                print(f"Ignored: {file}")
    
    print(f"Created zip file: {zip_filename}")
    return zip_filename

def git_commit_and_push(branch, version):
    """Add, commit, tag, and push changes to GitHub, but ignore the zip file."""
    try:
        subprocess.run(["git", "add", "."], check=True)

        commit_message = f"Release {branch}-{version}"
        subprocess.run(["git", "commit", "-m", commit_message], check=True)

        # Create and push new tag
        new_tag = f"{branch}-{version}"
        subprocess.run(["git", "tag", new_tag], check=True)
        subprocess.run(["git", "push", "origin", branch], check=True)
        subprocess.run(["git", "push", "--tags"], check=True)

        print(f"Committed and pushed {new_tag} to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"Error in Git operations: {e}")

def main():
    branch = get_git_branch()
    latest_version = get_latest_git_tag()

    # Check if an integer argument was passed to reset major version
    major_override = None
    if len(sys.argv) > 1:
        try:
            major_override = int(sys.argv[1])  # Convert argument to int
        except ValueError:
            print("Invalid version number. Please provide an integer.")
            return

    new_version = increment_version(latest_version, major_override)

    tracked_files = get_git_tracked_files()
    if not tracked_files:
        print("No Git-tracked files found. Exiting.")
        return

    ignore_patterns = parse_gitignore()
    
    # Create zip file but DO NOT track it in Git
    zip_file = create_release_zip(branch, new_version, tracked_files, ignore_patterns)

    # Commit and push changes but ignore zip file
    git_commit_and_push(branch, new_version)

if __name__ == "__main__":
    main()
