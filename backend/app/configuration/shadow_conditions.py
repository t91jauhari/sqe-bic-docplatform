"""Read-only applicability migration rehearsal against pinned case inputs."""
import argparse
import json
import os
from collections import Counter

from sqlalchemy import create_engine, text
from .account_policies import captured_conditions, parse_policy, propose_conditions


def verify_record(configuration, template, documents, context, *, compatibility=False):
    from app.sop import evaluate
    from app.sop_scoring import point_summary
    from app.transaction_flows import scope_configuration, score_configuration
    selected = [rule['id'] for rule in configuration.get('sop_rules', []) if rule.get('operator') == 'account_check'
                and parse_policy(rule['comparison_policy'])['kind'] in captured_conditions()]
    if not selected:
        return None
    candidate = configuration
    compatible = False
    if compatibility:
        from .compatibility import missing_settings, propose_compatibility
        additions = missing_settings(configuration)['additions']
        if additions:
            candidate = propose_compatibility(configuration, [item['key'] for item in additions])['payload']
            compatible = True
    proposal = propose_conditions(candidate, selected)
    before = evaluate(documents, scope_configuration(configuration, template), context)
    after = evaluate(documents, scope_configuration(proposal['payload'], template), context)
    def states(findings):
        return [(finding['rule_id'], finding['result'], finding.get('eligible'), finding.get('category')) for finding in findings]
    return {'findings': len(before), 'changed_rules': len(proposal['changed_rule_ids']), 'compatibility_applied': compatible,
            'equal': states(before) == states(after) and point_summary(before) == point_summary(after)
                     and score_configuration(configuration, template, before) == score_configuration(proposal['payload'], template, after)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-database', required=True)
    parser.add_argument('--compatibility', action='store_true')
    args = parser.parse_args()
    url = os.environ.get('REFACTOR_DATABASE_URL')
    if not url:
        parser.error('Set REFACTOR_DATABASE_URL explicitly.')
    engine = create_engine(url)
    checked = findings = converted = differences = compatibility_cases = 0
    blocked = Counter()
    try:
        with engine.begin() as connection:
            if engine.dialect.name != 'postgresql' or connection.scalar(text('SELECT current_database()')) != args.expected_database:
                raise ValueError('Expected an explicitly named PostgreSQL database.')
        with engine.begin() as connection:
            connection.execute(text('SET TRANSACTION READ ONLY'))
            cases = connection.execution_options(stream_results=True).execute(text(
                'SELECT c.id,c.template,cfg.payload,ctx.payload AS context FROM cases c JOIN configurations cfg ON cfg.id=c.config_id '
                'LEFT JOIN case_contexts ctx ON ctx.case_id=c.id')).mappings()
            for case in cases:
                documents = [dict(row) for row in connection.execute(text(
                    'SELECT id,doc_type,status,normalized,validation FROM documents WHERE case_id=:case ORDER BY created_at'), {'case': case['id']}).mappings()]
                try:
                    result = verify_record(case['payload'], case['template'], documents, case['context'] or {}, compatibility=args.compatibility)
                except ValueError as exc:
                    blocked[type(exc).__name__] += 1
                    continue
                if result:
                    checked += 1
                    findings += result['findings']
                    converted += result['changed_rules']
                    differences += not result['equal']
                    compatibility_cases += result['compatibility_applied']
        print(json.dumps({'cases_checked': checked, 'findings_checked': findings, 'converted_rules': converted,
                          'case_or_score_differences': differences, 'compatibility_applied_cases': compatibility_cases,
                          'blocked': dict(blocked), 'writes': False}))
        if not checked or differences:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
