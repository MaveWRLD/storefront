from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.include_root_view = False
router.register('customers', views.CustomerViewSet, basename='customers')

urlpatterns = router.urls
