FROM node:20-slim

RUN npm install -g Haraka@3 && \
    haraka -i /opt/haraka

WORKDIR /opt/haraka

# Install tobira JS client from local source
COPY js/ /tmp/tobira-js/
RUN cd /tmp/tobira-js && npm pack && \
    cd /opt/haraka && npm install --save /tmp/tobira-js/tobira-*.tgz && \
    rm -rf /tmp/tobira-js

# Install haraka-plugin-tobira from local source
COPY integrations/haraka/ /tmp/haraka-plugin/
RUN cp /tmp/haraka-plugin/plugins/tobira.js /opt/haraka/plugins/tobira.js && \
    rm -rf /tmp/haraka-plugin

# Copy test-environment plugins (accept all recipients, discard queue)
COPY docker/haraka/plugins/rcpt_to_any.js /opt/haraka/plugins/rcpt_to_any.js
COPY docker/haraka/plugins/queue_discard.js /opt/haraka/plugins/queue_discard.js

# Configure Haraka
COPY docker/haraka/config/ /opt/haraka/config/

EXPOSE 25

CMD ["haraka", "-c", "/opt/haraka"]
