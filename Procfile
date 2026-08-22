web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn storefront.wsgi --bind 0.0.0.0:$PORT
