import json
with open('sonar_issues.json', encoding='utf-8') as f:
    d = json.load(f)
    
print('Total:', d['total'])
print('Loaded:', len(d['issues']))

blockers = [i for i in d['issues'] if i['severity'] == 'BLOCKER']
print('BLOCKER count:', len(blockers))

for b in blockers:
    fp = b['component'].replace('ahmdelbaz28-ux_revit:', '')
    print(b['rule'] + ' | ' + fp + ' | L' + str(b.get('line','?')) + ' | ' + b['message'][:80])