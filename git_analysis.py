import streamlit as st
import git
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
from typing import Dict, List
import json

# Add page configuration
st.set_page_config(
    page_title="Git Repository Analysis",
    layout="wide"
)

def get_code_owners(repo_path: str) -> Dict[str, str]:
    """Extract CODEOWNERS file information."""
    codeowners_path = Path(repo_path) / 'CODEOWNERS'
    if not codeowners_path.exists():
        return {}
    
    owners_dict = {}
    with open(codeowners_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    pattern, *owners = parts
                    pattern = pattern.replace('*', '.*').replace('/', '\\/')
                    owners_dict[re.compile(pattern)] = owners[0]
    return owners_dict

def match_path_to_owner(file_path: str, owners_dict: Dict[re.Pattern, str]) -> str:
    """Match a file path to its code owner."""
    for pattern, owner in owners_dict.items():
        if pattern.match(file_path):
            return owner
    return 'Unknown'

def main():
    # Initialize session state
    if 'analysis_df' not in st.session_state:
        st.session_state.analysis_df = None
        st.session_state.since_date = None
        st.session_state.repo_path = None

    st.title('Git Repository Analysis')
    
    tab = st.tabs(["New Analysis"])[0]  # Get the first tab
    with tab:
        # Repository path input
        repo_path = st.text_input('Enter the path to your git repository:')
        
        if not repo_path:
            st.warning('Please enter a repository path')
            return
            
        if not os.path.exists(repo_path):
            st.error('Repository path does not exist')
            return
            
        try:
            git.Repo(repo_path)
        except git.InvalidGitRepositoryError:
            st.error('Invalid git repository')
            return
        
        # Time range selection with weeks
        weeks_ago = st.slider('Analyze commits from weeks ago:', 1, 52, 12)
        since_date = datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)
        
        st.write(f"Will analyze commits from {since_date.strftime('%Y-%m-%d')} to {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
        
        if st.button('Analyze Repository'):
            try:
                with st.spinner('Analyzing repository...'):
                    repo = git.Repo(repo_path)
                    commits = list(repo.iter_commits('master', since=since_date))
                    st.write(f"Found {len(commits)} commits to analyze")
                    
                    if not commits:
                        st.warning('No commits found in the specified time range')
                        return
                    
                    # Process commits
                    commit_data = []
                    progress_bar = st.progress(0)
                    progress_text = st.empty()  # Create a placeholder for the progress text
                    
                    # Get code owners mapping
                    owners_dict = get_code_owners(repo_path)
                    
                    for i, commit in enumerate(commits):
                        if commit.parents:  # Skip initial commit
                            diffs = commit.parents[0].diff(commit)
                            for diff in diffs:
                                if diff.a_path:
                                    commit_data.append({
                                        'date': commit.committed_datetime.astimezone(timezone.utc),
                                        'author': commit.author.email,
                                        'file': diff.a_path,
                                        'owner': match_path_to_owner(diff.a_path, owners_dict)
                                    })
                        
                        # Update progress
                        progress = (i + 1) / len(commits)
                        progress_bar.progress(progress)
                        progress_text.text(f"{i + 1}/{len(commits)} commits analyzed")
                    
                    # Convert to DataFrame
                    df = pd.DataFrame(commit_data)
                    
                    if df.empty:
                        st.warning('No file changes found in the commits')
                        return
                    
                    # Display overall statistics
                    st.header('Overall Statistics')
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric('Total Commits', len(df['date'].unique()))
                    with col2:
                        st.metric('Total Files Changed', len(df['file'].unique()))
                    
                    # Only show owner statistics if CODEOWNERS file exists and owners were found
                    if 'owner' in df.columns and not df['owner'].empty:
                        with st.columns(1)[0]:
                            st.metric('Total Code Owners', len(df['owner'].unique()))
                    
                    # Show file changes by owner
                    st.header('Most Changed Files by Owner')
                    
                    # Group by owner and file, count changes
                    file_changes = df.groupby(['owner', 'file']).size().reset_index(name='changes')
                    
                    # Get total changes per owner for sorting
                    owner_total_changes = file_changes.groupby('owner')['changes'].sum().sort_values(ascending=False)
                    
                    # Display each owner's files
                    for owner in owner_total_changes.index:
                        owner_files = (
                            file_changes[file_changes['owner'] == owner]
                            .sort_values('changes', ascending=False)
                            .head(30)
                        )
                        
                        total_changes = owner_total_changes[owner]
                        
                        with st.expander(f'Top Changed Files for {owner} ({total_changes} total changes)'):
                            # Format the table with index starting at 1
                            owner_files_display = owner_files.copy()
                            owner_files_display.index = range(1, len(owner_files_display) + 1)
                            owner_files_display.columns = ['Owner', 'File Path', 'Number of Changes']
                            st.dataframe(
                                owner_files_display[['File Path', 'Number of Changes']], 
                                use_container_width=True,
                                hide_index=False
                            )
                    
                    # Store in session state after creating DataFrame
                    st.session_state.analysis_df = df
                    st.session_state.since_date = since_date
                    st.session_state.repo_path = repo_path
                    
            except Exception as e:
                st.error(f"An error occurred during analysis: {str(e)}")
                st.exception(e)

if __name__ == '__main__':
    main()