-- New publications use entity tables. Immutable v1 publications remain readable.
DO $$
DECLARE entity_table TEXT;
BEGIN
    FOREACH entity_table IN ARRAY ARRAY[
        'configuration_families', 'configuration_profiles',
        'configuration_profile_variants', 'configuration_flows',
        'configuration_report_definitions', 'configuration_sop_rules',
        'configuration_generic_sop_rules'
    ] LOOP
        EXECUTE format('CREATE TABLE %I (
            publication_id VARCHAR(36) NOT NULL REFERENCES configuration_publications(id),
            entry_key VARCHAR(200) NOT NULL,
            position INTEGER NOT NULL CHECK (position >= 0),
            value JSON NOT NULL,
            PRIMARY KEY (publication_id, entry_key),
            UNIQUE (publication_id, position)
        )', entity_table);
        EXECUTE format('CREATE TRIGGER configuration_no_rewrite BEFORE UPDATE OR DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION configuration_reject_revision_mutation()', entity_table);
        EXECUTE format('CREATE TRIGGER configuration_same_transaction BEFORE INSERT ON %I FOR EACH ROW EXECUTE FUNCTION configuration_guard_new_entry()', entity_table);
    END LOOP;
END;
$$;
