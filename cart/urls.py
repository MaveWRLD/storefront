from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.include_root_view = False
router.register('carts', views.CartViewSet)

carts_router = routers.NestedDefaultRouter(router, 'carts', lookup='cart')
carts_router.register('items', views.CartItemViewSet, basename='cart-items')

urlpatterns = router.urls + carts_router.urls
