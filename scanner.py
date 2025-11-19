# Built for MAVEN

import os
import subprocess
import shutil
import requests
from typing import List, Set
import re

# GitHub API Configuration
GITHUB_TOKEN = os.environ.get("GITHUB_PAT")

# Code/Repo Search API URLs
# GITHUB_API_URL = "https://api.github.com/search/code"
GITHUB_API_URL = "https://api.github.com/search/repositories"

# GITHUB_SEARCH_QUERY = 'language:java path:**/test/ "assertEquals(" "toString()" AND "pom.xml")'
# GITHUB_SEARCH_QUERY = 'language:java path:test.js "assertEquals(" "toString()"'
GITHUB_SEARCH_QUERY = 'topic:maven'


#  Test Projects
# GITHUB_PROJECTS = [
#     "https://github.com/IBM/vpc-java-sdk",
# ]

GITHUB_PROJECTS = []
FLAKY_PROJECTS = []

SCANNED_REPOS_FILE = "scanned_repos.txt"
FLAKY_REPOS_FILE = "flaky_repos.txt"

NONDEX_MAVEN_COMMAND = [
    "mvn", "edu.illinois:nondex-maven-plugin:2.2.1:nondex",
]

CLEAN_INSTALL_COMMAND = [
    "mvn", "clean", "install",
    "-Dmaven.gpg.skip=true", 
    "-P-",
    "-DskipTests=true"
]

TEMP_DIR = "nondex_scan_temp"

NEW_LOMBOK_PLUGIN_VERSION = '1.18.24.0'
LOMBOK_PLUGIN_ARTIFACT_ID = 'lombok-maven-plugin'

# Load Scanned Repos
def load_scanned_repos() -> Set[str]:
    scanned_repos = set()
    if (not os.path.exists(SCANNED_REPOS_FILE)):
        with open(SCANNED_REPOS_FILE, "w") as f:
            pass
    else:
        try:
            with open(SCANNED_REPOS_FILE, 'r') as f:
                for line in f:
                    url = line.strip()
                    if url:
                        scanned_repos.add(url)
            print(f"Loaded {len(scanned_repos)} previously scanned repos.")
        except IOError as e:
            print(f"Warning: Could not read {SCANNED_REPOS_FILE} with Error: {e}")
    
    return scanned_repos

def save_scanned_repo(url: str):
    try:
        with open(SCANNED_REPOS_FILE, 'a') as f:
            f.write(url + '\n')
    except IOError as e:
        print(f"Error: Could not write to {SCANNED_REPOS_FILE} with Error: {e}")

# Search github
def search_github_for_java_projects(query: str, max_repos: int = 50) -> List[str]:
    print(f"--- Searching GiHub for projects matching: '{query}' ---")

    # Scanned repos:
    scanned_repos = load_scanned_repos()

    headers = {}
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
    
    params = {
        'q': query,
        'per_page': min(100, max_repos),
        # 'sort': 'indexed'
    }

    repo_urls = set()

    try:
        response = requests.get(GITHUB_API_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        # print(data['items'][0].keys())
        # print(data)

        # Extract repo url
        for item in data.get('items', []):
            # clone_url = item['repository']['html_url']
            clone_url = item['clone_url']
            if (clone_url not in scanned_repos):
                repo_urls.add(clone_url)
            
            if len(repo_urls) >= max_repos:
                break
        
        print(f"Found {len(repo_urls)} unique repositories to scan.")
        return list(repo_urls)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from GITHUB API: {e}")
        return []

# Clone Repository
def clone_repository(url: str, target_dir: str) -> bool:

    print(f"Cloning {url} into {target_dir}...")
    save_scanned_repo(url)

    try:
        os.makedirs(target_dir, exist_ok=True)
        subprocess.run(["git", "clone", url, target_dir], check=True, capture_output=True)
        print("Clone successful")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to clone repository: {e.stderr.decode()}")
        return False

# def fix_lombok_plugin_version(repo_path: str):
#     pom_path = os.path.join(repo_path, 'pom.xml')
#     print(f"Attempting to patch Lombok Plugin version in {pom_path}")

#     try:
#         with open(pom_path, 'r', encoding='utf-8') as f:
#             content = f.read()
        
#         version_pattern = r'(<artifactId>lombok-maven-plugin</artifactId>.*?<version>)(.*?)(</version>)'

#         # Replacement: \1 (preamble) + NEW_LOMBOK_PLUGIN_VERSION + \3 (suffix)
#         new_content, count = re.subn(
#             version_pattern, 
#             r'\g<1>' + NEW_LOMBOK_PLUGIN_VERSION + r'\g<3>', 
#             content, 
#             flags=re.DOTALL
#         )
        
#         if count > 0:
#             print(f"Successfully updated {count} instance(s) of {LOMBOK_PLUGIN_ARTIFACT_ID} version to {NEW_LOMBOK_PLUGIN_VERSION}.")
#             with open(pom_path, 'w', encoding='utf-8') as f:
#                 f.write(new_content)
#         else:
#             # If the direct replacement didn't work (e.g., version is defined in properties), 
#             # we skip the patch but log the warning.
#             print(f"Warning: Did not find a patchable version tag for {LOMBOK_PLUGIN_ARTIFACT_ID}. Continuing...")

#     except Exception as e:
#         print(f"Error patching pom.xml for Lombok: {e}")

# Comment out plugin
def comment_out_lombok_plugin(repo_path: str):
    pom_path = os.path.join(repo_path, 'pom.xml')
    if not os.path.exists(pom_path):
        return

    print(f"Attempting to comment out Lombok plugin in {pom_path}...")
    try:
        with open(pom_path, 'r', encoding='utf-8') as f:
            content = f.read()

        plugin_pattern = re.compile(
            r'(<plugin>\s*'
            r'<groupId>org\.projectlombok</groupId>\s*'
            r'<artifactId>lombok-maven-plugin</artifactId>.*?'
            r'</plugin>)',
            re.DOTALL | re.IGNORECASE
        )

        # Replacement: wrap the entire captured block in XML comments
        replacement = r'<!-- AUTOMATICALLY COMMENTED OUT BY SCANNER\n\1\n-->'
        
        new_content, count = plugin_pattern.subn(replacement, content)
        
        if count > 0:
            print(f"Successfully commented out {count} instance(s) of the Lombok plugin.")
            with open(pom_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        else:
            print("Lombok plugin not found or already commented out. Continuing.")

    except Exception as e:
        print(f"Error commenting out plugin in pom.xml: {e}")

# Clean install without running Nondex
def run_clean_install(repo_path: str) -> bool:
    print(f"\n --- First: Build the project without running Nondex --- ")

    # Check Maven
    if not os.path.exists(os.path.join(repo_path, 'pom.xml')):
        print("Skipping: pox.xml not found. Please check!")
        return False
    
    try:
        # comment_out_lombok_plugin(repo_path)
        result = subprocess.run(
            CLEAN_INSTALL_COMMAND,
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True
        )

        print(" ----- clean install result ----")
        print(result.stdout)
        print(result.returncode)

        if result.returncode == 0 and "BUILD SUCCESS" in result.stdout:
            print("MVN Clean and Install Successful!")
            return True
        else:
            return False
    except Exception as e:
        print(f"An error occurred during MVN Clean Install {e}")
    
# Nondex Scan
def run_nondex_scan(repo_path: str) -> bool:
    """_summary_

    Args:
        repo_path (str): _description_

    Returns:
        bool: _description_
    """
    print(f"\n --- Running Nondex on {repo_path} ---")

    # Check Maven
    if not os.path.exists(os.path.join(repo_path, 'pom.xml')):
        print("Skipping: pox.xml not found. Please check!")
        return False
    
    try:
        # Run Nondex
        result = subprocess.run(
            NONDEX_MAVEN_COMMAND,
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True
            
        )

        print(result.stdout)
        print(result.returncode)

        if result.returncode != 0 and "Unable to execute mojo: There are test failures." in result.stdout:
            print(">>> FLAKINESS DETECTED! <<<")
            FLAKY_PROJECTS.append(repo_path)
            return False 
        elif result.returncode == 0:
            print("Scan complete. No flakiness detected in 10 runs.")
            return True
        else:
            print(f"Build failed with exit code {result.returncode} (non-flakiness related).")
            return False
    except Exception as e:
        print(f"An error occurred during Nondex run:{e}")
        return False

def main():
    if (os.path.exists(TEMP_DIR)):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)

    global FLAKY_PROJECTS

    # Simple Run of github search query
    global GITHUB_PROJECTS
    GITHUB_PROJECTS = search_github_for_java_projects(GITHUB_SEARCH_QUERY, max_repos=100)

    if not GITHUB_PROJECTS:
        print("No projects found or API failed. Exiting...")
        return

    print(GITHUB_PROJECTS)

    for project in GITHUB_PROJECTS:
        repo_name = project.split('/')[-1].split('.')[0]
        repo_path = os.path.join(TEMP_DIR, f"{repo_name}")
        print(f"----------------------{repo_path}")

        clone_repository(project, repo_path)
        result_clean_install = run_clean_install(repo_path)
        if result_clean_install:
            # nondex scan if clean install successful
            result_nondex = run_nondex_scan(repo_path)
            print(f"Nondex Result: {result_nondex}")



    # result = run_nondex_scan(repo_path)
    # print(result)
    print(f"flaky project list: {FLAKY_PROJECTS}")

    with open(FLAKY_REPOS_FILE, 'a') as f: # Uses 'a' for both creating and appending
        for project in FLAKY_PROJECTS:
            f.write(project + '\n')

if __name__ == "__main__":
    main()