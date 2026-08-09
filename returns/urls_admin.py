from rest_framework import routers
from . import views

router = routers.DefaultRouter()
router.include_root_view = False
router.register('returns', views.ReturnAdminViewSet, basename='admin-returns')

urlpatterns = router.urls
