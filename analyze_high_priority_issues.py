#!/usr/bin/env python3

import json
from collections import defaultdict

def analyze_high_priority_issues():
    """Analyze high priority security issues from DSR report"""
    
    # Load the issues file
    with open('.dsr/issues.json', 'r') as f:
        issues = json.load(f)
    
    # Filter high priority issues (case insensitive)
    high_priority_issues = [
        issue for issue in issues 
        if issue.get('priority', '').lower() == 'high'
    ]
    
    # Categorize by check_id prefix
    categories = defaultdict(list)
    
    for issue in high_priority_issues:
        check_id = issue.get('check_id', 'UNKNOWN')
        prefix = check_id.split('-')[0] if '-' in check_id else check_id.split('_')[0]
        categories[prefix].append(issue)
    
    # Print summary
    print("HIGH PRIORITY SECURITY ISSUES ANALYSIS")
    print("=" * 50)
    print(f"Total High Priority Issues: {len(high_priority_issues)}")
    print()
    
    # Sort categories by count (descending)
    sorted_categories = sorted(categories.items(), key=lambda x: len(x[1]), reverse=True)
    
    for category, issues_list in sorted_categories:
        print(f"{category}: {len(issues_list)} issues")
        
        # Group by specific check_id within category
        check_ids = defaultdict(int)
        for issue in issues_list:
            check_ids[issue.get('check_id', 'UNKNOWN')] += 1
        
        for check_id, count in sorted(check_ids.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {check_id}: {count}")
        print()
    
    # Detailed breakdown by issue type
    print("DETAILED ISSUE BREAKDOWN")
    print("=" * 30)
    
    issue_types = defaultdict(int)
    for issue in high_priority_issues:
        issue_desc = issue.get('issue', 'Unknown issue')[:80] + "..." if len(issue.get('issue', '')) > 80 else issue.get('issue', 'Unknown issue')
        issue_types[issue_desc] += 1
    
    for issue_type, count in sorted(issue_types.items(), key=lambda x: x[1], reverse=True):
        if count > 1:
            print(f"{count}x: {issue_type}")

if __name__ == "__main__":
    analyze_high_priority_issues()
