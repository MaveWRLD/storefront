web: python manage.py collectstatic --noinput && exec gunicorn storefront.wsgi --bind 0.0.0.0:$PORT --workers 3 --threads 2 --worker-class gthread --timeout 60 --access-logfile - --error-logfile -
