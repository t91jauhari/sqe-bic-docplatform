CREATE TABLE configuration_family_rule_scopes (
    publication_id VARCHAR(36) NOT NULL REFERENCES configuration_publications(id),
    family VARCHAR(80) NOT NULL,
    PRIMARY KEY (publication_id, family)
);
CREATE TABLE configuration_family_rule_members (
    publication_id VARCHAR(36) NOT NULL,
    family VARCHAR(80) NOT NULL,
    rule_id VARCHAR(100) NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    PRIMARY KEY (publication_id, family, rule_id),
    UNIQUE (publication_id, family, position),
    FOREIGN KEY (publication_id, family) REFERENCES configuration_family_rule_scopes(publication_id, family)
);
