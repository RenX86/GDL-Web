import multiprocessing

# Worker Configuration
workers = 1
worker_class = 'gthread'
threads = 100
timeout = 120  # Increase timeout just in case
keepalive = 60

# Logging
loglevel = 'info'
accesslog = '-'
errorlog = '-'
