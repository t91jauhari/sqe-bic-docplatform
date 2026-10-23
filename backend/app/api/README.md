# HTTP boundaries

`app.main` composes the application, lifecycle, middleware and exception handlers.
Feature routers own their HTTP paths and authorization dependencies. They must
not import `app.main` or call another HTTP endpoint as a service.

| Module | Responsibility |
|---|---|
| authentication | Login, session, logout |
| administration | Organization branches and users |
| intake | Upload batches and customer grouping |
| documents | Document listing, correction and retries |
| cases | Case detail, context, review and assignments |
| comparisons | Reference comparison requests and exports |
| evidence | Source files, pages, bounding boxes and crops |
| field_processing | Selected-field extraction and prompt guidance |
| reports | Authorized report browsing and downloads |
| exports | Configuration and extraction exports |
| notifications | User notification state |
| operations | Overview and worker capacity |

`contracts` contains request models; `views` contains existing response projections;
`dependencies` contains shared role dependencies. Configuration and provider
administration retain their own package routers and application services.

This first split deliberately preserves existing endpoint bodies and transaction
boundaries. Some routers still orchestrate database queries directly. Further
service extraction must preserve organization/branch authorization, immutable case
configuration pins, audit writes and provider receipt semantics. Moving a handler
does not by itself complete that service separation.

Keep public paths and request/response contracts compatible. API tests should
exercise behavior through the composed application; patch a dependency in the
module that consumes it rather than relying on exports from `app.main`.
