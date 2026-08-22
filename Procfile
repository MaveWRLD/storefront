web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn storefront.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 60 --access-logfile - --error-logfile -
