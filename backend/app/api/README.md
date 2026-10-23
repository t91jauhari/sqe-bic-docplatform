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

Feature routes delegate 43 operations to `app.application`. Application services
own transaction orchestration and use transport-independent errors, access checks,
DTOs and upload ports. Authentication cookies and binary HTTP responses stay at
the HTTP boundary. Configuration and provider administration have their own
services. Services do not import FastAPI, Starlette, API routers or `app.domain`.

`app.contracts` and `app.projections` own shared models and projections; the API
modules re-export them for compatibility. `app.domain` is a compatibility facade;
bootstrap, validation, auditing, routing and case lifecycle have separate owners.
This remains a modular monolith with SQLAlchemy transactions and asynchronous
workers. Registered algorithms, authentication and state transitions remain code.

Keep public paths and request/response contracts compatible. API tests should
exercise behavior through the composed application; patch a dependency in the
module that consumes it rather than relying on exports from `app.main`.
