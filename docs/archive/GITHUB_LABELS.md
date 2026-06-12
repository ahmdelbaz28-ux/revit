# GitHub Labels Strategy for FireAI

## Overview

This document outlines the comprehensive labeling strategy for the FireAI repository to ensure consistent issue and pull request management, improve triage efficiency, and enhance contributor experience.

## Label Categories

### Type Labels
These labels indicate the nature of the issue or pull request:

- `bug` - Reports a bug or unexpected behavior
- `enhancement` - Requests a new feature or improvement
- `documentation` - Related to documentation updates
- `maintenance` - Routine maintenance tasks
- `question` - Questions or clarifications needed
- `security` - Security-related issues
- `performance` - Performance improvements or issues
- `refactor` - Code restructuring without functional changes

### Priority Labels
These labels indicate the urgency and importance:

- `priority-critical` - Critical issues requiring immediate attention
- `priority-high` - Important issues to address soon
- `priority-medium` - Standard priority items
- `priority-low` - Nice-to-have improvements

### Status Labels
These labels indicate the current state of the issue:

- `status-needs-triage` - Needs initial assessment
- `status-in-progress` - Being actively worked on
- `status-on-hold` - Temporarily paused
- `status-review-needed` - Awaiting review
- `status-blocked` - Blocked by other issues
- `status-duplicate` - Duplicate of another issue
- `status-wontfix` - Won't be addressed
- `status-invalid` - Invalid or not reproducible

### Component Labels
These labels indicate which part of the system is affected:

- `component-core` - Core FireAI engine
- `component-ui` - User interface components
- `component-api` - API layer
- `component-security` - Security components
- `component-etap` - ETAP integration
- `component-gis` - GIS integration
- `component-database` - Database layer
- `component-ml` - Machine learning components
- `component-infrastructure` - Infrastructure and deployment

### Effort Labels
These labels indicate the estimated effort required:

- `effort-xs` - Extra small (less than 1 hour)
- `effort-s` - Small (1-4 hours)
- `effort-m` - Medium (4-8 hours)
- `effort-l` - Large (1-2 days)
- `effort-xl` - Extra large (2+ days)

### Experience Level Labels
These labels indicate the difficulty level for contributors:

- `good-first-issue` - Suitable for newcomers
- `beginner-friendly` - Good for beginner contributors
- `intermediate` - Requires some experience
- `advanced` - Requires significant expertise

## Label Colors

| Label | Color |
|-------|-------|
| bug | e11d21 |
| enhancement | 006b75 |
| documentation | 0052cc |
| maintenance | fbca04 |
| question | cc317c |
| security | ee0701 |
| performance | 5319e7 |
| refactor | 1d76db |
| priority-critical | b60205 |
| priority-high | d93f0b |
| priority-medium | fbca04 |
| priority-low | fef2c0 |
| status-needs-triage | d4c5f9 |
| status-in-progress | 5319e7 |
| status-on-hold | fef2c0 |
| status-review-needed | fbca04 |
| status-blocked | e11d21 |
| status-duplicate | cccccc |
| status-wontfix | ffffff |
| status-invalid | eeeeee |
| component-core | 009800 |
| component-ui | 207de5 |
| component-api | 5319e7 |
| component-security | ee0701 |
| component-etap | 006b75 |
| component-gis | 0052cc |
| component-database | 5319e7 |
| component-ml | 1d76db |
| component-infrastructure | fbca04 |
| effort-xs | f9d0c4 |
| effort-s | fbca04 |
| effort-m | fef2c0 |
| effort-l | f9d0c4 |
| effort-xl | e11d21 |
| good-first-issue | 7057ff |
| beginner-friendly | 7057ff |
| intermediate | 009800 |
| advanced | e11d21 |

## Label Management Guidelines

### Creating Issues
- Assign appropriate type label (bug, enhancement, etc.)
- Add component label if known
- Add priority label if clear
- Add any relevant experience level labels

### Triaging Issues
- Apply status-needs-triage to all new issues
- Within 24-48 hours, assign:
  - Correct type label
  - Component label
  - Priority label
  - Effort estimate (if clear)
  - Remove status-needs-triage

### Assigning Issues
- Assign component experts to issues in their area
- Encourage first-time contributors to tackle good-first-issue labeled items
- Ensure priority-critical issues are assigned immediately

### Pull Request Labels
- Use the same type labels as issues
- Add `status-review-needed` when submitted
- Add component labels as appropriate
- Remove when merged

## Automation Recommendations

Consider implementing the following automations:

1. **New Issue Automation**:
   - Automatically add `status-needs-triage` to new issues
   - Automatically label issues based on content patterns
   - Apply `good-first-issue` to appropriate new issues

2. **Stale Issue Automation**:
   - Mark issues as stale after 30 days of inactivity
   - Close stale issues after 14 additional days without response

3. **PR Automation**:
   - Automatically add `status-review-needed` to new PRs
   - Require specific labels before merging

## Team Workflow Integration

### Daily Standup
- Review issues with `status-needs-triage`
- Address `priority-critical` items
- Assign blocked items to appropriate team members

### Sprint Planning
- Filter by priority labels
- Consider effort estimates
- Balance workload across components

### Code Reviews
- Check that PR labels match issue labels
- Ensure appropriate labels are applied before merging

## Maintaining Label Consistency

### Regular Audits
- Monthly review of label usage
- Clean up unused or inconsistent labels
- Update this strategy based on team feedback

### Training
- New team member orientation on label usage
- Regular reminders about label best practices
- Document common label combinations

## Benefits of This Strategy

1. **Improved Visibility**: Clear understanding of issue types and priorities
2. **Better Triage**: Faster assignment and resolution of issues
3. **Enhanced Collaboration**: Clear communication about work focus
4. **Efficient Filtering**: Easy to find issues by type, priority, or component
5. **Contributor Friendly**: Clear guidance for external contributors
6. **Metrics Tracking**: Ability to measure team performance by label categories

## Implementation Checklist

- [ ] Create all labels in the repository
- [ ] Update issue templates to mention labeling
- [ ] Train team members on label usage
- [ ] Implement automation where appropriate
- [ ] Document this strategy in the repository
- [ ] Schedule regular label audits

---

*This labeling strategy should be reviewed quarterly and updated based on team feedback and changing project needs.*