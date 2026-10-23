CREATE TABLE configuration_context_definitions (
    publication_id VARCHAR(36) NOT NULL REFERENCES configuration_publications(id),
    context_key VARCHAR(80) NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    definition JSON NOT NULL,
    PRIMARY KEY (publication_id, context_key),
    UNIQUE (publication_id, position)
);
CREATE TRIGGER configuration_no_rewrite
    BEFORE UPDATE OR DELETE OR TRUNCATE ON configuration_context_definitions
    FOR EACH STATEMENT EXECUTE FUNCTION configuration_reject_revision_mutation();
CREATE TRIGGER configuration_same_transaction
    BEFORE INSERT ON configuration_context_definitions
    FOR EACH ROW EXECUTE FUNCTION configuration_guard_new_entry();
