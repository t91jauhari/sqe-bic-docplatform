FROM temporalio/temporal:1.6.2
USER root
RUN mkdir -p /var/lib/temporal && chown 1000:1000 /var/lib/temporal
USER 1000:1000
