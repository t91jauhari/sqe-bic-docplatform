const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../node_modules/typescript');
const source = fs.readFileSync(path.join(__dirname, '../lib/document-family.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const exportsObject = {};
new Function('exports', compiled)(exportsObject);
const { familyProfiles, familyCatalog, inFamily, ruleInFamily } = exportsObject;
assert.equal(familyProfiles.account_opening.length, 7);
assert.equal(familyProfiles.forex.length, 7);
for (const type of ['ektp', 'riplay']) {
  assert(inFamily(type, 'account_opening'));
  assert(inFamily(type, 'forex'));
}
assert(inFamily('account_opening_form', 'account_opening'));
assert(!inFamily('application', 'account_opening'));
assert(!inFamily('account_opening_form', 'forex'));
assert(!inFamily('unknown', 'forex'));
const aoRules = JSON.parse(fs.readFileSync(path.join(__dirname, '../../backend/app/config_data/account_opening_rules.json')));
assert(aoRules.length > 0);
for (const r of aoRules) {
  assert(ruleInFamily(r, 'account_opening'), r.id);
  assert(!ruleInFamily(r, 'forex'), r.id);
  assert(inFamily(r.path.split('.')[0], 'account_opening'), r.path);
}
assert(ruleInFamily({source_ref:'SOP:1'}, 'forex'));
assert(!ruleInFamily({source_ref:'SOP:1'}, 'account_opening'));
assert(ruleInFamily({source_ref:'AO:custom'}, 'account_opening'));
const custom={templates:{},document_families:{loans:{label:'Loans',profiles:['ektp'],sop_rule_ids:['loan_check']}}};
assert(inFamily('ektp','loans',custom));
assert(!inFamily('application','loans',custom));
assert(!inFamily('ektp','missing',custom));
assert(ruleInFamily({id:'loan_check'},'loans',custom));
assert(!ruleInFamily({id:'unrelated',source_ref:'AO:custom'},'loans',custom));
console.log(`Family boundaries verified against ${aoRules.length} Account Opening SOP rules and shared profiles.`);

const explicit={...custom,family_catalog_mode:'explicit'};
assert.deepEqual(Object.keys(familyCatalog(explicit)),['loans']);
assert(!inFamily('ektp','forex',explicit));
assert(inFamily('ektp','loans',explicit));
