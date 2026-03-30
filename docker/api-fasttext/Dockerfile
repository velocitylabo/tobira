FROM python:3.12-slim AS builder

WORKDIR /build

# Install tobira with fasttext + serving
COPY python/ /tmp/tobira-python/
RUN pip install --no-cache-dir "/tmp/tobira-python[serving,fasttext]" && \
    rm -rf /tmp/tobira-python

# Train FastText model from sample data at build time
COPY docs/handson/sample_train.csv /build/sample_train.csv
RUN python3 -c "\
import csv, fasttext; \
lines = []; \
[lines.append(f'__label__{r[\"label\"]} {r[\"text\"]}') for r in csv.DictReader(open('sample_train.csv'))]; \
open('train.txt','w').write('\n'.join(lines)+'\n'); \
model = fasttext.train_supervised('train.txt', epoch=25, lr=1.0, wordNgrams=2); \
model.save_model('fasttext-spam.bin'); \
print(f'Model trained: {len(lines)} samples')" && \
    rm -f train.txt sample_train.csv

# --- Runtime stage ---
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/tobira /usr/local/bin/tobira
COPY --from=builder /build/fasttext-spam.bin /app/fasttext-spam.bin
COPY docker/api-fasttext/config.toml /app/config.toml

EXPOSE 8000

CMD ["tobira", "serve", "--config", "/app/config.toml", "--host", "0.0.0.0", "--port", "8000"]
