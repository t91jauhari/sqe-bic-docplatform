CREATE TABLE configuration_publications (
    id VARCHAR(36) PRIMARY KEY,
    organization VARCHAR(80) NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    source_config_id VARCHAR(36) NOT NULL,
    digest VARCHAR(64) NOT NULL,
    extensions JSON NOT NULL,
    UNIQUE (organization, revision)
);
CREATE INDEX ix_configuration_publications_organization
    ON configuration_publications (organization);

CREATE TABLE configuration_entries (
    id VARCHAR(36) PRIMARY KEY,
    publication_id VARCHAR(36) NOT NULL REFERENCES configuration_publications(id),
    section VARCHAR(80) NOT NULL,
    entry_key VARCHAR(200) NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    value JSON NOT NULL,
    UNIQUE (publication_id, section, entry_key)
);
CREATE INDEX ix_configuration_entries_publication_id
    ON configuration_entries (publication_id);
